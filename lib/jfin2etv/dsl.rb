# frozen_string_literal: true

module Jfin2etv
  # DSL verbs. Each method populates Plan.current.
  module DSL
    # ----- channel -------------------------------------------------------

    def channel(number:, name:, tuning: nil, icon: nil, language: "en", transcode: nil)
      raise DSLError.new("channel declared more than once") if Plan.current.channel

      tuning ||= number.to_s
      merged = if transcode.nil?
                 Validation.default_transcode
               else
                 Validation.require_hash!(transcode, "transcode")
                 Validation.deep_merge(Validation.default_transcode, transcode)
               end
      Validation.validate_transcode!(merged)

      Plan.current.channel = {
        number: String(number),
        name: String(name),
        tuning: String(tuning),
        icon: icon.nil? ? nil : String(icon),
        language: String(language),
        transcode: merged,
      }
    end

    # ----- collection ----------------------------------------------------

    def collection(name, expression, mode: :shuffle, sort: nil, memory_window: nil, weight_field: nil)
      Validation.require_symbol!(mode, "collection mode", Validation::PLAYBACK_MODES)
      Validation.validate_bounded_not!(expression)

      if mode == :random_with_memory && memory_window.nil?
        raise DSLError.new("collection #{name.inspect} mode :random_with_memory requires memory_window")
      end
      if mode == :weighted_random && weight_field.nil?
        raise DSLError.new("collection #{name.inspect} mode :weighted_random requires weight_field")
      end

      Plan.current.add_collection(
        name.to_sym,
        {
          expression: expression,
          mode: mode,
          sort: sort,
          memory_window: memory_window,
          weight_field: weight_field.nil? ? nil : String(weight_field),
        },
      )
    end

    # ----- filler --------------------------------------------------------

    def filler(kind, local: nil, collection: nil, mode: :shuffle, sort: nil, memory_window: nil, weight_field: nil)
      Validation.require_symbol!(kind, "filler kind", Validation::FILLER_KINDS)
      if (local.nil? && collection.nil?) || (!local.nil? && !collection.nil?)
        raise DSLError.new(
          "filler #{kind.inspect}: exactly one of local: or collection: is required"
        )
      end

      data =
        if local
          { kind: "local", path: String(local) }
        else
          Validation.require_symbol!(mode, "filler #{kind.inspect} mode", Validation::PLAYBACK_MODES)
          Validation.validate_bounded_not!(collection)
          if mode == :random_with_memory && memory_window.nil?
            raise DSLError.new(
              "filler #{kind.inspect} mode :random_with_memory requires memory_window"
            )
          end
          {
            kind: "collection",
            expression: collection,
            mode: mode,
            sort: sort,
            memory_window: memory_window,
            weight_field: weight_field.nil? ? nil : String(weight_field),
          }
        end

      Plan.current.add_filler(kind, data)
    end

    # ----- layout --------------------------------------------------------

    def layout(name, &block)
      raise DSLError.new("layout #{name.inspect} requires a block") unless block

      builder = LayoutBuilder.new(name)
      builder.instance_eval(&block)
      Plan.current.add_layout(name.to_sym, builder.to_h)
    end

    class LayoutBuilder
      def initialize(name)
        @name = name
        @steps = []
        @epg = nil
      end

      def pre_roll(count: 0)
        raise DSLError.new("layout #{@name.inspect}: pre_roll count must be >= 0") if count.negative?

        @steps << { op: "pre_roll", count: Integer(count) }
      end

      def main
        @steps << { op: "main" }
      end

      def mid_roll(every:, wrap_with: nil, count: 1, per_break_target: 120)
        every_val = normalize_every(every)
        wraps = Array(wrap_with).map(&:to_sym)
        if wraps.any? { |w| !%i[to_mid from_mid].include?(w) }
          raise DSLError.new("layout #{@name.inspect}: mid_roll wrap_with must be :to_mid and/or :from_mid")
        end
        count_val =
          if count == :auto
            "auto"
          elsif count.is_a?(Integer) && count.positive?
            count
          else
            raise DSLError.new("layout #{@name.inspect}: mid_roll count must be a positive Integer or :auto")
          end

        @steps << {
          op: "mid_roll",
          every: every_val,
          wrap_with: wraps.map(&:to_s),
          count: count_val,
          per_break_target: Integer(per_break_target),
        }
      end

      def post_roll(count: 0)
        raise DSLError.new("layout #{@name.inspect}: post_roll count must be >= 0") if count.negative?

        @steps << { op: "post_roll", count: Integer(count) }
      end

      def slug(between_items: true, duration: nil)
        @steps << {
          op: "slug",
          between_items: !!between_items,
          duration: duration.nil? ? nil : Float(duration),
        }
      end

      def fill(with:)
        pools =
          case with
          when Symbol then [with.to_s]
          when Array then with.map { |p| Validation.require_symbol!(p, "fill with entry", Validation::FILLER_KINDS); p.to_s }
          else
            raise DSLError.new("layout #{@name.inspect}: fill with: must be a Symbol or Array of Symbols")
          end
        @steps << { op: "fill", with: pools }
      end

      def epg(granularity:, title: nil, description: nil, category: nil)
        Validation.require_symbol!(granularity, "epg granularity", Validation::EPG_GRANULARITIES)
        @epg = {
          granularity: granularity.to_s,
          title: normalize_epg_field(title),
          description: normalize_epg_field(description),
          category: category.nil? ? nil : String(category),
        }
      end

      def to_h
        {
          steps: @steps,
          epg: @epg || { granularity: "per_item", title: "from_main", description: nil, category: nil },
        }
      end

      private

      def normalize_every(every)
        case every
        when :chapter then "chapter"
        when :never then "never"
        when Hash
          if every.size == 1 && every.key?(:minutes)
            { minutes: Integer(every[:minutes]) }
          else
            raise DSLError.new("layout #{@name.inspect}: mid_roll every: hash must be {minutes: N}")
          end
        else
          raise DSLError.new(
            "layout #{@name.inspect}: mid_roll every: must be :chapter, :never, or {minutes: N}"
          )
        end
      end

      def normalize_epg_field(val)
        case val
        when nil then nil
        when :from_main, :from_series, :from_block then val.to_s
        when String then { "kind" => "literal", "value" => val }
        when Proc
          src = capture_proc_source(val)
          { "kind" => "proc", "source" => src }
        else
          raise DSLError.new(
            "layout #{@name.inspect}: epg field must be :from_main, :from_series, :from_block, a String, or a Proc"
          )
        end
      end

      def capture_proc_source(proc)
        require "method_source"
        proc.source.strip
      rescue LoadError, MethodSource::SourceNotFoundError => e
        raise DSLError.new("layout #{@name.inspect}: cannot capture epg Proc source (#{e.class})")
      end
    end

    # ----- schedule ------------------------------------------------------

    def schedule(&block)
      raise DSLError.new("schedule requires a block") unless block

      builder = ScheduleBuilder.new
      builder.instance_eval(&block)
      Plan.current.schedule = builder.to_h
    end

    class ScheduleBuilder
      def initialize
        @blocks = []
        @default_block = nil
      end

      def block(at:, collection:, layout:, count: nil, on: nil, align: nil,
                epg: nil, variants: nil, variant: nil)
        at_seconds = Validation.parse_clock!(at, "block at:")
        align_seconds =
          case align
          when nil then nil
          when Duration then align.to_i
          when Integer
            raise DSLError.new("block align: must be a Duration (e.g. 30.minutes), got Integer seconds explicitly wrap with .seconds")
          else
            raise DSLError.new("block align: must be a Duration, got #{align.class}")
          end

        Validation.validate_on!(on)

        variant_selector = nil
        if variants
          Validation.require_hash!(variants, "block variants:")
          variants.each do |key, val|
            Validation.require_hash!(val, "block variants[#{key.inspect}]")
            extras = val.keys - %i[collection layout]
            unless extras.empty?
              raise DSLError.new(
                "block variants[#{key.inspect}]: only :collection and :layout are allowed, got extras #{extras.inspect}"
              )
            end
          end
          unless variant
            raise DSLError.new("block variants: requires a matching variant: selector")
          end

          variant_selector = normalize_variant_selector(variant, variants.keys.map(&:to_sym))
          variants = variants.transform_keys(&:to_sym).transform_values { |v| v.transform_keys(&:to_sym) }
        elsif variant
          raise DSLError.new("block variant: given without variants:")
        end

        @blocks << {
          at: at,
          at_seconds: at_seconds,
          collection: collection.to_sym,
          layout: layout.to_sym,
          count: normalize_count(count),
          on: on,
          align_seconds: align_seconds,
          epg_overrides: normalize_epg_overrides(epg),
          variants: variants,
          variant_selector: variant_selector,
        }
      end

      def default_block(collection:, layout:, align: nil)
        raise DSLError.new("default_block declared more than once") if @default_block

        align_seconds = align.is_a?(Duration) ? align.to_i : nil
        @default_block = {
          collection: collection.to_sym,
          layout: layout.to_sym,
          align_seconds: align_seconds,
        }
      end

      def to_h
        keys = @blocks.map { |b| [b[:at_seconds], b[:on]] }
        if keys.uniq.size != keys.size
          raise DSLError.new(
            "duplicate anchor times in schedule (same at: and on:): " \
            "#{keys.inspect}"
          )
        end

        sorted = @blocks.sort_by { |b| [b[:at_seconds], b[:on].to_s] }
        { blocks: sorted, default_block: @default_block }
      end

      private

      def normalize_count(count)
        case count
        when nil then nil
        when Integer
          raise DSLError.new("block count must be >= 0") if count.negative?

          count
        when :auto then "auto"
        else
          raise DSLError.new("block count must be nil, Integer, or :auto (got #{count.inspect})")
        end
      end

      def normalize_epg_overrides(epg)
        return nil if epg.nil?

        Validation.require_hash!(epg, "block epg:")
        allowed = %i[title description category]
        Validation.reject_unknown_keys!(epg, allowed, "block epg:")
        epg.transform_keys(&:to_sym).transform_values { |v| v.nil? ? nil : String(v) }
      end

      def normalize_variant_selector(selector, variant_keys)
        case selector
        when Hash
          Validation.require_hash!(selector, "block variant:")
          selector.each_key do |key|
            unless Validation::DOW_KEYS.include?(key)
              raise DSLError.new(
                "block variant: unknown day-of-week key #{key.inspect}; allowed: #{Validation::DOW_KEYS.inspect}"
              )
            end
          end
          selector.each_value do |v|
            unless variant_keys.include?(v.to_sym)
              raise DSLError.new(
                "block variant: value #{v.inspect} does not match any variants key (#{variant_keys.inspect})"
              )
            end
          end
          { type: "dow", table: selector.transform_keys(&:to_s).transform_values(&:to_s) }
        when Proc
          src = capture_proc_source(selector)
          { type: "proc", source: src }
        else
          raise DSLError.new("block variant: must be a Hash or Proc")
        end
      end

      def capture_proc_source(proc)
        require "method_source"
        proc.source.strip
      rescue LoadError, MethodSource::SourceNotFoundError => e
        raise DSLError.new("block variant: cannot capture Proc source (#{e.class})")
      end
    end
  end
end
