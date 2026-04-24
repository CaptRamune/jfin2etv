# frozen_string_literal: true

module Jfin2etv
  # Singleton in-memory plan AST. All DSL verbs populate the current instance;
  # Runner swaps a fresh one in per channel evaluation.
  class Plan
    attr_accessor :channel
    attr_reader :collections, :fillers, :layouts, :schedule

    def self.current
      Thread.current[:jfin2etv_plan] ||= Plan.new
    end

    def self.current=(plan)
      Thread.current[:jfin2etv_plan] = plan
    end

    def self.reset!
      Thread.current[:jfin2etv_plan] = Plan.new
    end

    def initialize
      @channel = nil
      @collections = {}
      @fillers = {}
      @layouts = {}
      @schedule = nil
    end

    def add_collection(name, data)
      raise DSLError.new("collection #{name.inspect} already defined") if @collections.key?(name)

      @collections[name] = data
    end

    def add_filler(kind, data)
      raise DSLError.new("filler #{kind.inspect} already defined") if @fillers.key?(kind)

      @fillers[kind] = data
    end

    def add_layout(name, data)
      raise DSLError.new("layout #{name.inspect} already defined") if @layouts.key?(name)

      @layouts[name] = data
    end

    def schedule=(sched)
      raise DSLError.new("schedule declared more than once") if @schedule

      @schedule = sched
    end
  end
end
