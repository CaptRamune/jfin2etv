# frozen_string_literal: true

# Top-level entry for the jfin2etv DSL.
# Loading this file exposes the DSL verbs (channel, collection, filler,
# layout, schedule) at the top level of any Ruby script that `require`s it.

require "json"

module Jfin2etv
  PLAN_SCHEMA_VERSION = "jfin2etv-plan/1"
end

require_relative "jfin2etv/errors"
require_relative "jfin2etv/duration"
require_relative "jfin2etv/plan"
require_relative "jfin2etv/helpers"
require_relative "jfin2etv/validation"
require_relative "jfin2etv/dsl"
require_relative "jfin2etv/serializer"
require_relative "jfin2etv/runner"
require_relative "jfin2etv/selector"

# Install DSL verbs on `main` (top-level object) so scripts can call them
# without any prefix: `channel(...)`, `collection(...)`, etc.
include Jfin2etv::DSL

# Helpers (local/http/today/weekday?/env) likewise.
include Jfin2etv::Helpers
