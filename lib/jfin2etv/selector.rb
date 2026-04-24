# frozen_string_literal: true

require "date"
require "json"

module Jfin2etv
  # Helper invoked by the Python host to evaluate a variant Proc's captured
  # source for a given date. DESIGN.md §6.2 — the Python side never parses
  # Ruby itself; it calls back into Ruby with the source snippet and the
  # target date.
  #
  # Usage (by Python):
  #   ruby -I /app/lib -r jfin2etv/selector \
  #     -e 'Jfin2etv::Selector.run_proc(ENV.fetch("PROC_SOURCE"), ENV.fetch("DATE"))'
  #
  # The result (a Symbol-or-String) is printed as a single JSON string to
  # stdout, nothing else; exit 0 on success, 2 on eval error.
  module Selector
    module_function

    def run_proc(source, date_string)
      date = Date.parse(date_string)
      # rubocop:disable Security/Eval
      fn = eval(source)
      # rubocop:enable Security/Eval
      raise ArgumentError, "selector source did not evaluate to a Proc" unless fn.respond_to?(:call)

      result = fn.call(date)
      puts JSON.generate(result.to_s)
      0
    rescue StandardError => e
      warn "selector error: #{e.class}: #{e.message}"
      2
    end
  end
end
