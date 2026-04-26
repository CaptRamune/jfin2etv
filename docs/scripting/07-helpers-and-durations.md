# 07 — Helpers and durations

Beyond the five DSL verbs, the runtime exposes a few small helpers that scripts can use anywhere — most often inside lambdas or to build expressions dynamically — plus duration shorthands like `30.minutes` and `1.hour`.

## Script-facing helpers

These are global at the top level of every channel script: just call them directly.

### `local(path)`

Constructs a single-file source descriptor. Mostly used internally; you'll rarely call it directly because `filler ..., local: "..."` accepts the path string and constructs the descriptor for you.

```ruby
local("/media/bumpers/black_1s.mkv")
# => { kind: "local", path: "/media/bumpers/black_1s.mkv" }
```

When you'd reach for it: building a list of local sources programmatically.

### `http(uri, headers: nil)`

Constructs an HTTP source descriptor.

```ruby
http("https://example.com/clip.mkv")
http("https://example.com/clip.mkv", headers: ["X-Auth: token"])
```

> **v1 caveat:** the DSL accepts `http(...)` and serializes it into the plan AST, but jfin2etv v1 does not yet emit `HttpSource` playout items — only `LocalSource` from Jellyfin and the lavfi safety-net are wired up. Tracking issue: [`DESIGN.md` §19.2](../../DESIGN.md#192-deferred). For now, treat `http()` as a placeholder for future remote-Jellyfin deployments.

### `today`

Returns `Date.today` in the channel's timezone.

```ruby
on: ->(d) { d > today + 7 }   # blocks scheduled more than a week ahead
```

Almost always used inside an `on:` or `variant:` lambda. The lambda itself is re-evaluated daily by the planner, so `today` always reflects the date being planned, not the date the script was loaded.

### `weekday?(date = Date.today)`

Returns `true` for Monday–Friday, `false` for Saturday/Sunday.

```ruby
on: ->(d) { weekday?(d) && d.month != 12 }   # weekdays except December
```

Equivalent to checking `(1..5).include?(date.wday)`. Use the symbolic `on: :weekdays` form when the rule is just "weekdays"; reach for `weekday?` when you're combining day-of-week with other conditions inside a lambda.

### `env(name, default: nil)`

Reads an environment variable, returning the default when the var is unset or empty.

```ruby
TUNING = env("CHANNEL_01_TUNING", default: "01.1")

channel number: "01", name: "Classic Rock Videos", tuning: TUNING
```

Important: `env` is the **only** way scripts can read environment variables — `ENV[...]` is not exposed. And it deliberately filters out empty strings: `env("FOO", default: "x")` returns `"x"` whether `FOO` is unset, set to `""`, or absent.

> **Secrets are not visible to scripts.** `JELLYFIN_API_KEY` and similar credentials are read by the Python host and never passed into the Ruby runner. If you find yourself wanting to read a secret in a script, you're probably in the wrong layer — that logic belongs in the Python planner.

## Integer duration helpers

The DSL extends `Integer` with four duration constructors. Each returns a `Jfin2etv::Duration` value whose `to_i` is the number of seconds.

```ruby
30.seconds   # 30 seconds
1.second     # 1 second (alias of seconds)
30.minutes   # 1800 seconds
1.minute     # 60 seconds
2.hours      # 7200 seconds
1.hour       # 3600 seconds
1.day        # 86 400 seconds
2.days       # 172 800 seconds
```

The singular and plural forms are aliases: `1.minute` and `1.minutes` produce the same `Duration`. Pick whichever reads better.

### Where Durations are accepted

Currently a `Duration` is required in exactly one place: the `align:` argument of `block` and `default_block`.

```ruby
block at: "20:00", collection: :simpsons, layout: :sitcom_block, align: 30.minutes
default_block collection: :simpsons, layout: :sitcom_block, align: 30.minutes
```

Passing a raw Integer is explicitly rejected:

```ruby
align: 1800
# => block align: must be a Duration (e.g. 30.minutes), got Integer
#    seconds explicitly wrap with .seconds
```

This is deliberate — `1800` is ambiguous (seconds? minutes? milliseconds?) and the helpers self-document. If you really need a raw seconds value, use `1800.seconds`.

### Why `every: { minutes: 15 }` is not a Duration

Layouts' `mid_roll every: { minutes: N }` is the one place the DSL takes a duration as a Hash, not a `Duration`:

```ruby
mid_roll every: { minutes: 15 }, count: :auto      # correct
mid_roll every: 15.minutes,      count: :auto      # WRONG — raises a DSL error
```

`every:` accepts only `:chapter`, `:never`, or a `{ minutes: N }` Hash. The asymmetry exists because `every:` historically only supported chapter-relative and minute-relative breaks, and the Hash form leaves room for future granularities (e.g. `{ chapters: 2 }`) without breaking parsing. It's a minor wart; keep the two forms straight and use `align: 30.minutes` for one and `every: { minutes: 15 }` for the other.

| Where | Form | Example |
|---|---|---|
| `block align:` / `default_block align:` | `Duration` | `align: 30.minutes` |
| `mid_roll every:` (minute mode) | Hash `{ minutes: N }` | `every: { minutes: 15 }` |
| `mid_roll per_break_target:` | plain Integer (seconds) | `per_break_target: 120` |

### Comparison and arithmetic

`Duration` instances are comparable (`>`, `<`, `==`, etc.) and convert to seconds via `to_i`:

```ruby
30.minutes < 1.hour          # => true
(2.hours).to_i               # => 7200
```

Arithmetic between Durations is not provided directly — convert to integers if you need it: `((1.hour).to_i + (15.minutes).to_i).seconds`. This rarely comes up in real scripts.

## Putting helpers together: a small variant lambda

A real-world example combining `today`, `weekday?`, and a top-level constant:

```ruby
HOLIDAYS = [
  Date.new(2026, 12, 24),
  Date.new(2026, 12, 25),
  Date.new(2026, 12, 31),
  Date.new(2027, 1, 1),
].freeze

block at: "20:00",
      collection: :simpsons,
      layout:     :sitcom_block,
      align:      30.minutes,
      count:      1,
      variants: {
        normal:  { collection: :simpsons,         layout: :sitcom_block },
        holiday: { collection: :christmas_movies, layout: :movie_night  },
      },
      variant: ->(d) { HOLIDAYS.include?(d) ? :holiday : :normal }
```

The lambda's source is captured and re-evaluated daily; `HOLIDAYS` (a top-level constant) is visible from the re-evaluation context, while local variables defined elsewhere in the script may not be.

## See also

- [`05-schedule.md`](05-schedule.md) — `align:` and `on:` are the two arguments that most often combine with these helpers.
- [`00-ruby-primer.md`](00-ruby-primer.md) — primer on lambdas, ranges, and constants.
- [`DESIGN.md` §5.6](../../DESIGN.md#56-dsl-level-helpers) — formal helper spec.
- [`DESIGN.md` §19.2](../../DESIGN.md#192-deferred) — why `http()` emission is deferred.
