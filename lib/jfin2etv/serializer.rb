# frozen_string_literal: true

require "json"

module Jfin2etv
  # Serialize a Plan to the JSON document described in DESIGN.md §6.2.
  module Serializer
    module_function

    def dump(plan)
      JSON.pretty_generate(to_hash(plan))
    end

    def to_hash(plan)
      raise DSLError.new("no channel() declared") unless plan.channel
      raise DSLError.new("no schedule do ... end declared") unless plan.schedule

      {
        "schema_version" => Jfin2etv::PLAN_SCHEMA_VERSION,
        "channel" => serialize_channel(plan.channel),
        "collections" => plan.collections.transform_keys(&:to_s).transform_values { |c| serialize_collection(c) },
        "fillers" => plan.fillers.transform_keys(&:to_s).transform_values { |f| serialize_filler(f) },
        "layouts" => plan.layouts.transform_keys(&:to_s).transform_values { |l| serialize_layout(l) },
        "schedule" => serialize_schedule(plan.schedule),
      }
    end

    def serialize_channel(ch)
      {
        "number" => ch[:number],
        "name" => ch[:name],
        "tuning" => ch[:tuning],
        "icon" => ch[:icon],
        "language" => ch[:language],
        "transcode" => serialize_transcode(ch[:transcode]),
      }
    end

    def serialize_transcode(t)
      {
        "ffmpeg" => {
          "ffmpeg_path" => t[:ffmpeg][:ffmpeg_path],
          "ffprobe_path" => t[:ffmpeg][:ffprobe_path],
          "disabled_filters" => Array(t[:ffmpeg][:disabled_filters]),
          "preferred_filters" => Array(t[:ffmpeg][:preferred_filters]),
        },
        "video" => {
          "format" => sym_to_s(t[:video][:format]),
          "width" => t[:video][:width],
          "height" => t[:video][:height],
          "bitrate_kbps" => t[:video][:bitrate_kbps],
          "buffer_kbps" => t[:video][:buffer_kbps],
          "bit_depth" => t[:video][:bit_depth],
          "accel" => sym_to_s(t[:video][:accel]),
          "deinterlace" => t[:video][:deinterlace] == true,
          "tonemap_algorithm" => t[:video][:tonemap_algorithm],
          "vaapi_device" => t[:video][:vaapi_device],
          "vaapi_driver" => sym_to_s(t[:video][:vaapi_driver]),
        },
        "audio" => {
          "format" => sym_to_s(t[:audio][:format]),
          "bitrate_kbps" => t[:audio][:bitrate_kbps],
          "buffer_kbps" => t[:audio][:buffer_kbps],
          "channels" => t[:audio][:channels],
          "sample_rate_hz" => t[:audio][:sample_rate_hz],
          "normalize_loudness" => t[:audio][:normalize_loudness] == true,
          "loudness" => t[:audio][:loudness].nil? ? nil : t[:audio][:loudness].transform_keys(&:to_s),
        },
        "playout" => {
          "virtual_start" => t[:playout][:virtual_start],
        },
      }
    end

    def serialize_collection(c)
      {
        "expression" => c[:expression],
        "mode" => c[:mode].to_s,
        "sort" => c[:sort].nil? ? nil : c[:sort].to_s,
        "memory_window" => c[:memory_window],
        "weight_field" => c[:weight_field],
      }
    end

    def serialize_filler(f)
      case f[:kind]
      when "local"
        { "kind" => "local", "path" => f[:path] }
      when "collection"
        {
          "kind" => "collection",
          "expression" => f[:expression],
          "mode" => f[:mode].to_s,
          "sort" => f[:sort].nil? ? nil : f[:sort].to_s,
          "memory_window" => f[:memory_window],
          "weight_field" => f[:weight_field],
        }
      else
        raise DSLError.new("unexpected filler kind #{f[:kind].inspect}")
      end
    end

    def serialize_layout(l)
      {
        "steps" => l[:steps].map { |s| serialize_step(s) },
        "epg" => serialize_epg(l[:epg]),
      }
    end

    def serialize_step(s)
      base = { "op" => s[:op] }
      case s[:op]
      when "pre_roll", "post_roll"
        base.merge("count" => s[:count])
      when "main"
        base
      when "mid_roll"
        base.merge(
          "every" => s[:every],
          "wrap_with" => s[:wrap_with],
          "count" => s[:count],
          "per_break_target" => s[:per_break_target],
        )
      when "slug"
        base.merge("between_items" => s[:between_items], "duration" => s[:duration])
      when "fill"
        base.merge("with" => s[:with])
      else
        raise DSLError.new("unexpected layout op #{s[:op].inspect}")
      end
    end

    def serialize_epg(epg)
      {
        "granularity" => epg[:granularity],
        "title" => serialize_epg_field(epg[:title]),
        "description" => serialize_epg_field(epg[:description]),
        "category" => epg[:category],
      }
    end

    def serialize_epg_field(val)
      case val
      when nil then nil
      when String then val
      when Hash then val.transform_keys(&:to_s)
      else val.to_s
      end
    end

    def serialize_schedule(sched)
      {
        "blocks" => sched[:blocks].map { |b| serialize_block(b) },
        "default_block" => serialize_default_block(sched[:default_block]),
      }
    end

    def serialize_block(b)
      {
        "at" => b[:at],
        "collection" => b[:collection].to_s,
        "layout" => b[:layout].to_s,
        "count" => b[:count],
        "on" => serialize_on(b[:on]),
        "align_seconds" => b[:align_seconds],
        "epg_overrides" => b[:epg_overrides].nil? ? nil : b[:epg_overrides].transform_keys(&:to_s),
        "variants" => serialize_variants(b[:variants]),
        "variant_selector" => serialize_selector(b[:variant_selector]),
      }
    end

    def serialize_default_block(d)
      return nil if d.nil?

      {
        "collection" => d[:collection].to_s,
        "layout" => d[:layout].to_s,
        "align_seconds" => d[:align_seconds],
      }
    end

    def serialize_on(on)
      case on
      when nil then nil
      when Symbol then { "type" => "symbol", "value" => on.to_s }
      when Array then { "type" => "list", "value" => on.map(&:to_s) }
      when Range then { "type" => "range", "begin" => on.begin.to_s, "end" => on.end.to_s, "exclude_end" => on.exclude_end? }
      when Proc
        require "method_source"
        { "type" => "proc", "source" => on.source.strip }
      else
        raise DSLError.new("cannot serialize on: #{on.class}")
      end
    end

    def serialize_variants(variants)
      return nil if variants.nil?

      variants.transform_keys(&:to_s).transform_values do |v|
        {
          "collection" => v[:collection]&.to_s,
          "layout" => v[:layout]&.to_s,
        }
      end
    end

    def serialize_selector(sel)
      return nil if sel.nil?

      case sel[:type]
      when "dow" then { "type" => "dow", "table" => sel[:table] }
      when "proc" then { "type" => "proc", "source" => sel[:source] }
      else raise DSLError.new("unexpected selector type #{sel[:type].inspect}")
      end
    end

    def sym_to_s(v)
      v.nil? ? nil : v.to_s
    end
  end
end
