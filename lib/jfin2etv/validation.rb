# frozen_string_literal: true

module Jfin2etv
  # Validation helpers used by DSL verbs. Every check raises DSLError with a
  # message that names the offending path, per DESIGN.md section 5.
  module Validation
    module_function

    VIDEO_FORMATS = %i[h264 hevc].freeze
    VIDEO_ACCELS = %i[cuda qsv vaapi videotoolbox vulkan].freeze
    VAAPI_DRIVERS = %i[ihd i965 radeonsi].freeze
    AUDIO_FORMATS = %i[aac ac3].freeze

    PLAYBACK_MODES = %i[shuffle sequential chronological random_with_memory weighted_random].freeze

    FILLER_KINDS = %i[slug pre_roll post_roll mid_roll to_mid from_mid fallback].freeze

    EPG_GRANULARITIES = %i[per_item per_block per_chapter].freeze

    DOW_KEYS = %i[mon tue wed thu fri sat sun weekdays weekends default].freeze

    FFMPEG_KEYS = %i[ffmpeg_path ffprobe_path disabled_filters preferred_filters].freeze
    VIDEO_KEYS = %i[
      format width height bitrate_kbps buffer_kbps bit_depth accel deinterlace
      tonemap_algorithm vaapi_device vaapi_driver
    ].freeze
    AUDIO_KEYS = %i[
      format bitrate_kbps buffer_kbps channels sample_rate_hz
      normalize_loudness loudness
    ].freeze
    PLAYOUT_KEYS = %i[virtual_start].freeze
    LOUDNESS_KEYS = %i[integrated_target range_target true_peak].freeze
    TRANSCODE_TOP_KEYS = %i[ffmpeg video audio playout].freeze

    def require_hash!(value, name)
      return if value.is_a?(Hash)

      raise DSLError.new("#{name} must be a Hash, got #{value.class}")
    end

    def require_symbol!(value, name, allowed = nil)
      unless value.is_a?(Symbol)
        raise DSLError.new("#{name} must be a Symbol, got #{value.inspect}")
      end

      return unless allowed && !allowed.include?(value)

      raise DSLError.new("#{name} must be one of #{allowed.inspect}, got #{value.inspect}")
    end

    def reject_unknown_keys!(hash, allowed, path)
      extras = hash.keys - allowed
      return if extras.empty?

      raise DSLError.new(
        "unknown key(s) #{extras.inspect} at #{path}; allowed: #{allowed.inspect}"
      )
    end

    # Deep-merge defaults into user-supplied transcode hash (§5.1).
    def deep_merge(base, over)
      base.merge(over) do |_k, v1, v2|
        v1.is_a?(Hash) && v2.is_a?(Hash) ? deep_merge(v1, v2) : v2
      end
    end

    def default_transcode
      {
        ffmpeg: {
          ffmpeg_path: "ffmpeg",
          ffprobe_path: "ffprobe",
          disabled_filters: [],
          preferred_filters: [],
        },
        video: {
          format: :h264,
          width: 1920,
          height: 1080,
          bitrate_kbps: 4000,
          buffer_kbps: 8000,
          bit_depth: 8,
          accel: nil,
          deinterlace: false,
          tonemap_algorithm: nil,
          vaapi_device: nil,
          vaapi_driver: nil,
        },
        audio: {
          format: :aac,
          bitrate_kbps: 160,
          buffer_kbps: 320,
          channels: 2,
          sample_rate_hz: 48_000,
          normalize_loudness: false,
          loudness: nil,
        },
        playout: {
          virtual_start: nil,
        },
      }
    end

    def validate_transcode!(transcode)
      require_hash!(transcode, "transcode")
      reject_unknown_keys!(transcode, TRANSCODE_TOP_KEYS, "transcode")

      if (ffmpeg = transcode[:ffmpeg])
        require_hash!(ffmpeg, "transcode.ffmpeg")
        reject_unknown_keys!(ffmpeg, FFMPEG_KEYS, "transcode.ffmpeg")
      end

      video = transcode[:video]
      require_hash!(video, "transcode.video")
      reject_unknown_keys!(video, VIDEO_KEYS, "transcode.video")
      validate_video!(video)

      audio = transcode[:audio]
      require_hash!(audio, "transcode.audio")
      reject_unknown_keys!(audio, AUDIO_KEYS, "transcode.audio")
      validate_audio!(audio)

      if (playout = transcode[:playout])
        require_hash!(playout, "transcode.playout")
        reject_unknown_keys!(playout, PLAYOUT_KEYS, "transcode.playout")
      end
    end

    def validate_video!(video)
      raise DSLError.new("transcode.video.format is required") if video[:format].nil?

      require_symbol!(video[:format], "transcode.video.format", VIDEO_FORMATS)
      raise DSLError.new("transcode.video.width is required") if video[:width].nil?
      raise DSLError.new("transcode.video.height is required") if video[:height].nil?

      if video.key?(:accel) && !video[:accel].nil?
        require_symbol!(video[:accel], "transcode.video.accel", VIDEO_ACCELS)
      end
      return unless video.key?(:vaapi_driver) && !video[:vaapi_driver].nil?

      require_symbol!(video[:vaapi_driver], "transcode.video.vaapi_driver", VAAPI_DRIVERS)
    end

    def validate_audio!(audio)
      raise DSLError.new("transcode.audio.format is required") if audio[:format].nil?

      require_symbol!(audio[:format], "transcode.audio.format", AUDIO_FORMATS)
      raise DSLError.new("transcode.audio.channels is required") if audio[:channels].nil?

      return unless audio[:loudness]

      require_hash!(audio[:loudness], "transcode.audio.loudness")
      reject_unknown_keys!(audio[:loudness], LOUDNESS_KEYS, "transcode.audio.loudness")
    end

    # Validate a Jellyfin query expression's NOT-boundedness (§5.8).
    # Rule: a NOT operator anywhere in the expression requires that a
    # `library:` or `collection:` atom appears elsewhere in the same expression.
    def validate_bounded_not!(expression)
      return unless expression.is_a?(String)

      upcase = expression.upcase
      return unless upcase.include?("NOT")

      return if /\b(?:library|collection)\s*:/i.match?(expression)

      raise DSLError.new(
        "unbounded NOT in expression #{expression.inspect}; " \
        "bound with a library: or collection: atom"
      )
    end

    # Parse an "HH:MM" or "HH:MM:SS" 24-hour clock string into seconds-since-midnight.
    def parse_clock!(text, context)
      unless text.is_a?(String) && /\A\d{2}:\d{2}(?::\d{2})?\z/.match?(text)
        raise DSLError.new("#{context}: expected HH:MM or HH:MM:SS, got #{text.inspect}")
      end

      parts = text.split(":").map(&:to_i)
      h, m, s = parts[0], parts[1], parts[2] || 0
      if h > 23 || m > 59 || s > 59
        raise DSLError.new("#{context}: out-of-range clock #{text.inspect}")
      end

      (h * 3600) + (m * 60) + s
    end

    # Validate a block's `on:` filter shape. Return it unchanged for later
    # evaluation by the Python side.
    def validate_on!(on)
      return nil if on.nil?

      case on
      when Symbol, Array, Range, Proc then on
      else
        raise DSLError.new("block on: expects Symbol | Array | Range | Proc, got #{on.class}")
      end
    end
  end
end
