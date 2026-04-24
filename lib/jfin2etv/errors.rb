# frozen_string_literal: true

module Jfin2etv
  # Raised when a Ruby script misuses the DSL in a way that can be detected
  # at evaluation time (unknown keys, duplicate anchors, etc.). Exit code 2
  # per DESIGN.md section 6.3.
  class DSLError < StandardError
    attr_reader :file, :line

    def initialize(message, file: nil, line: nil)
      @file = file
      @line = line
      prefix = file ? "#{file}:#{line}: " : ""
      super("jfin2etv: DSL error in #{prefix}#{message}")
    end
  end
end
