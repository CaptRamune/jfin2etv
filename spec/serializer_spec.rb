# frozen_string_literal: true

require "json"

RSpec.describe Jfin2etv::Serializer do
  it "round-trips the §5.7 full skeleton to a well-formed plan AST" do
    channel number: "01", name: "Classic Rock Videos"
    collection :rock_videos, "type:music_video AND genre:Rock", mode: :shuffle
    filler :slug, local: "/media/bumpers/black_1s.mkv"
    filler :pre_roll, collection: "type:bumper AND tag:classicrock_pre"
    filler :fallback, collection: "type:bumper AND tag:classicrock_fill", mode: :shuffle
    layout :video_block do
      pre_roll count: 1
      main
      slug between_items: true
      fill with: :fallback
      epg granularity: :per_item, title: :from_main
    end
    schedule do
      block at: "00:00", collection: :rock_videos, layout: :video_block
      default_block collection: :rock_videos, layout: :video_block
    end

    ast = JSON.parse(described_class.dump(Jfin2etv::Plan.current))

    expect(ast["schema_version"]).to eq Jfin2etv::PLAN_SCHEMA_VERSION
    expect(ast["channel"]["number"]).to eq "01"
    expect(ast["channel"]["transcode"]["video"]["format"]).to eq "h264"
    expect(ast["collections"]["rock_videos"]["mode"]).to eq "shuffle"
    expect(ast["fillers"]).to include("slug", "pre_roll", "fallback")
    expect(ast["layouts"]["video_block"]["steps"].map { |s| s["op"] }).to eq(
      %w[pre_roll main slug fill]
    )
    expect(ast["schedule"]["blocks"].first["at"]).to eq "00:00"
    expect(ast["schedule"]["default_block"]["collection"]).to eq "rock_videos"
  end

  it "refuses to serialize a plan with no channel" do
    schedule do
      block at: "00:00", collection: :x, layout: :y
    end
    expect { described_class.dump(Jfin2etv::Plan.current) }.to raise_error(Jfin2etv::DSLError, /no channel/)
  end

  it "emits variant_selector with dow type for hash form" do
    channel number: "01", name: "X"
    schedule do
      block at: "20:00",
            collection: :a,
            layout: :l,
            variants: { weekdays: { collection: :a, layout: :l }, weekends: { collection: :b, layout: :l } },
            variant: { weekdays: :weekdays, weekends: :weekends }
    end
    ast = JSON.parse(described_class.dump(Jfin2etv::Plan.current))
    sel = ast["schedule"]["blocks"][0]["variant_selector"]
    expect(sel["type"]).to eq "dow"
    expect(sel["table"]).to eq({ "weekdays" => "weekdays", "weekends" => "weekends" })
  end
end
