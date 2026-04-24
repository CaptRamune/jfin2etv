# frozen_string_literal: true

require "json"
require "stringio"

# The Python bridge invokes `ruby -r jfin2etv/runner ...` so this file must
# bootstrap the whole DSL library when loaded standalone.
require_relative "../jfin2etv" unless defined?(Jfin2etv::DSL)

module Jfin2etv
  # Called by the Python host (via `ruby -r jfin2etv/runner -e ...`).
  #
  # Responsibilities per DESIGN.md section 6.1–6.4:
  #   - Swap $stdout to a buffer so script `puts` goes to stderr.
  #   - Load each script in order into Plan.current.
  #   - Emit the Plan AST as JSON to the *real* stdout.
  #   - Honor VALIDATE_ONLY=1 (exit 0 if parse+validate is clean, no JSON).
  #   - Exit with codes:
  #       0  success
  #       2  DSLError
  #       1  any other uncaught exception
  module Runner
    module_function

    def run(script_paths, channel:)
      real_stdout = $stdout
      $stdout = $stderr # redirect script `puts` to stderr

      Plan.reset!

      script_paths.each do |path|
        load(path, true) # wrap=true gives the script its own anonymous module
      end

      # Assert that *this* script batch actually declared a channel and schedule.
      # Serializer will raise DSLError if not.
      if ENV["VALIDATE_ONLY"] == "1"
        Serializer.to_hash(Plan.current) # will raise DSLError if incomplete
        exit 0
      end

      json = Serializer.dump(Plan.current)
      real_stdout.write(json)
      real_stdout.write("\n")
      real_stdout.flush
      exit 0
    rescue DSLError => e
      $stderr.puts e.message
      exit 2
    rescue SystemExit
      raise
    rescue Exception => e # rubocop:disable Lint/RescueException
      $stderr.puts "#{e.class}: #{e.message}"
      $stderr.puts e.backtrace&.join("\n")
      exit 1
    ensure
      $stdout = real_stdout if real_stdout
    end
  end
end
