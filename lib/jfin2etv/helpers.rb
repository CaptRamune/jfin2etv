# frozen_string_literal: true

require "date"

module Jfin2etv
  # Script-facing helpers (§5.6).
  module Helpers
    def local(path)
      { kind: "local", path: String(path) }
    end

    def http(uri, headers: nil)
      h = { kind: "http", uri: String(uri) }
      h[:headers] = Array(headers).map(&:to_s) if headers
      h
    end

    def today
      Date.today
    end

    def weekday?(date = Date.today)
      (1..5).include?(date.wday)
    end

    def env(name, default: nil)
      val = ENV[String(name)]
      val.nil? || val.empty? ? default : val
    end
  end
end
