# frozen_string_literal: true

require "json"

RSpec.describe "DSL verbs" do
  describe "channel" do
    it "accepts minimal args and applies default transcode" do
      channel number: "01", name: "Classic Rock Videos"
      expect(Jfin2etv::Plan.current.channel[:number]).to eq "01"
      expect(Jfin2etv::Plan.current.channel[:tuning]).to eq "01"
      expect(Jfin2etv::Plan.current.channel[:transcode][:video][:format]).to eq :h264
    end

    it "deep-merges a partial transcode override" do
      channel number: "02", name: "HDR", transcode: { video: { accel: :cuda, width: 3840 } }
      vid = Jfin2etv::Plan.current.channel[:transcode][:video]
      expect(vid[:accel]).to eq :cuda
      expect(vid[:width]).to eq 3840
      expect(vid[:height]).to eq 1080 # from defaults
    end

    it "rejects an unknown top-level transcode key" do
      expect do
        channel number: "03", name: "Bad", transcode: { bogus: {} }
      end.to raise_error(Jfin2etv::DSLError, /unknown key.*bogus/)
    end

    it "rejects an unknown video sub-hash key" do
      expect do
        channel number: "04", name: "Bad", transcode: { video: { tom: :cruise } }
      end.to raise_error(Jfin2etv::DSLError, /unknown key.*tom/)
    end

    it "rejects an unknown video format enum" do
      expect do
        channel number: "05", name: "Bad", transcode: { video: { format: :xvid } }
      end.to raise_error(Jfin2etv::DSLError, /must be one of/)
    end

    it "rejects a double declaration" do
      channel number: "06", name: "A"
      expect { channel number: "07", name: "B" }.to raise_error(Jfin2etv::DSLError, /channel declared more than once/)
    end
  end

  describe "collection" do
    it "registers a shuffle collection" do
      collection :rock, "type:music_video AND genre:Rock", mode: :shuffle
      c = Jfin2etv::Plan.current.collections[:rock]
      expect(c[:expression]).to include "genre:Rock"
      expect(c[:mode]).to eq :shuffle
    end

    it "requires memory_window for :random_with_memory" do
      expect do
        collection :x, "type:movie", mode: :random_with_memory
      end.to raise_error(Jfin2etv::DSLError, /memory_window/)
    end

    it "requires weight_field for :weighted_random" do
      expect do
        collection :y, "type:movie", mode: :weighted_random
      end.to raise_error(Jfin2etv::DSLError, /weight_field/)
    end

    it "rejects an unbounded NOT" do
      expect do
        collection :bad, "NOT type:commercial", mode: :shuffle
      end.to raise_error(Jfin2etv::DSLError, /unbounded NOT/)
    end

    it "accepts a bounded NOT (library)" do
      expect do
        collection :ok, 'library:"Movies" AND NOT genre:Horror', mode: :shuffle
      end.not_to raise_error
    end
  end

  describe "filler" do
    it "registers a local filler" do
      filler :slug, local: "/media/bumpers/black.mkv"
      f = Jfin2etv::Plan.current.fillers[:slug]
      expect(f[:kind]).to eq "local"
      expect(f[:path]).to eq "/media/bumpers/black.mkv"
    end

    it "requires exactly one of local: or collection:" do
      expect { filler :slug }.to raise_error(Jfin2etv::DSLError, /exactly one of local: or collection:/)
      expect do
        filler :slug, local: "/a.mkv", collection: "type:bumper"
      end.to raise_error(Jfin2etv::DSLError, /exactly one of local: or collection:/)
    end

    it "rejects unknown filler kinds" do
      expect do
        filler :banana, local: "/a.mkv"
      end.to raise_error(Jfin2etv::DSLError, /must be one of/)
    end
  end

  describe "layout" do
    it "builds a layout with typical steps" do
      layout :lb do
        pre_roll count: 1
        main
        slug between_items: true, duration: 1.0
        fill with: :fallback
        epg granularity: :per_item, title: :from_main
      end
      l = Jfin2etv::Plan.current.layouts[:lb]
      ops = l[:steps].map { |s| s[:op] }
      expect(ops).to eq %w[pre_roll main slug fill]
    end

    it "accepts ordered list for fill with:" do
      layout :lb do
        main
        fill with: [:mid_roll, :fallback]
      end
      fill_step = Jfin2etv::Plan.current.layouts[:lb][:steps].last
      expect(fill_step[:with]).to eq %w[mid_roll fallback]
    end

    it "accepts :auto mid_roll count" do
      layout :sitcom do
        main
        mid_roll every: :chapter, wrap_with: [:to_mid, :from_mid], count: :auto, per_break_target: 120
      end
      step = Jfin2etv::Plan.current.layouts[:sitcom][:steps][1]
      expect(step[:count]).to eq "auto"
      expect(step[:wrap_with]).to eq %w[to_mid from_mid]
    end

    it "rejects unknown epg granularity" do
      expect do
        layout :bad do
          main
          epg granularity: :per_femtosecond
        end
      end.to raise_error(Jfin2etv::DSLError, /must be one of/)
    end
  end

  describe "schedule" do
    before do
      channel number: "01", name: "X"
    end

    it "sorts blocks by anchor time" do
      schedule do
        block at: "12:00", collection: :c, layout: :l
        block at: "08:00", collection: :c, layout: :l
      end
      ats = Jfin2etv::Plan.current.schedule[:blocks].map { |b| b[:at] }
      expect(ats).to eq %w[08:00 12:00]
    end

    it "rejects duplicate anchor times with the same on: tag" do
      expect do
        schedule do
          block at: "12:00", collection: :c, layout: :l
          block at: "12:00", collection: :c, layout: :l
        end
      end.to raise_error(Jfin2etv::DSLError, /duplicate anchor/)
    end

    it "allows duplicate anchor times when on: differs" do
      expect do
        schedule do
          block at: "08:00", collection: :c, layout: :l, on: :weekends
          block at: "08:00", collection: :c, layout: :l, on: :weekdays
        end
      end.not_to raise_error
    end

    it "rejects out-of-range clocks" do
      expect do
        schedule do
          block at: "25:00", collection: :c, layout: :l
        end
      end.to raise_error(Jfin2etv::DSLError, /out-of-range/)
    end

    it "accepts default_block" do
      schedule do
        block at: "08:00", collection: :c, layout: :l
        default_block collection: :c, layout: :l
      end
      expect(Jfin2etv::Plan.current.schedule[:default_block]).not_to be_nil
    end

    describe "variants" do
      it "accepts a day-of-week selector" do
        schedule do
          block at: "20:00",
                collection: :a,
                layout: :l,
                variants: { weekdays: { collection: :a, layout: :l }, weekends: { collection: :b, layout: :l } },
                variant: { weekdays: :weekdays, weekends: :weekends }
        end
        sel = Jfin2etv::Plan.current.schedule[:blocks][0][:variant_selector]
        expect(sel[:type]).to eq "dow"
      end

      it "rejects unknown dow keys" do
        expect do
          schedule do
            block at: "20:00",
                  collection: :a,
                  layout: :l,
                  variants: { mon: { collection: :a, layout: :l } },
                  variant: { martedi: :mon }
          end
        end.to raise_error(Jfin2etv::DSLError, /unknown day-of-week key/)
      end

      it "rejects variant values that do not reference a declared variant key" do
        expect do
          schedule do
            block at: "20:00",
                  collection: :a,
                  layout: :l,
                  variants: { weekdays: { collection: :a, layout: :l } },
                  variant: { weekends: :weekends }
          end
        end.to raise_error(Jfin2etv::DSLError, /does not match any variants key/)
      end

      it "rejects extra variant-entry keys beyond :collection and :layout" do
        expect do
          schedule do
            block at: "20:00",
                  collection: :a,
                  layout: :l,
                  variants: { weekdays: { collection: :a, layout: :l, count: 2 } },
                  variant: { weekdays: :weekdays }
          end
        end.to raise_error(Jfin2etv::DSLError, /only :collection and :layout/)
      end
    end
  end
end
