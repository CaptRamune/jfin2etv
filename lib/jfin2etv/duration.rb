# frozen_string_literal: true

# Integer refinement-free helpers so scripts can write `30.minutes`, `1.hour`,
# `2.hours`. We monkey-patch sparingly and only on Integer/Float; the methods
# return an integer number of seconds (which serializes to `align_seconds` in
# the plan AST).

module Jfin2etv
  # Tag object for duration values emitted by the DSL. Stored as seconds.
  class Duration
    include Comparable

    attr_reader :seconds

    def initialize(seconds)
      @seconds = Integer(seconds)
    end

    def <=>(other)
      return nil unless other.is_a?(Duration)

      @seconds <=> other.seconds
    end

    def to_i
      @seconds
    end

    def to_s
      "#{@seconds}s"
    end

    def inspect
      "#<Jfin2etv::Duration #{to_s}>"
    end
  end
end

class Integer
  def seconds
    Jfin2etv::Duration.new(self)
  end
  alias_method :second, :seconds

  def minutes
    Jfin2etv::Duration.new(self * 60)
  end
  alias_method :minute, :minutes

  def hours
    Jfin2etv::Duration.new(self * 3600)
  end
  alias_method :hour, :hours

  def days
    Jfin2etv::Duration.new(self * 86_400)
  end
  alias_method :day, :days
end
