# 09 — Cookbook

A collection of patterns for the situations script authors hit most often. The first three are the bundled examples shipped under `examples/scripts/`; the rest are common variations.

Use these as starting points — copy, adjust, run `jfin2etv validate --channel N`, repeat.

## Pattern 1 — 24/7 single-pool shuffle channel

The simplest possible channel: one collection, shuffle order, a single layout, a single block plus a default. This is exactly Channel 01 from the bundled examples.

```ruby
# /scripts/01/main.rb

channel number: "01", name: "Classic Rock Videos", tuning: "01.1",
        icon: "/media/logos/classicrock.png"

collection :rock_videos,
  "type:music_video AND (genre:Rock OR genre:\"Classic Rock\")",
  mode: :shuffle

filler :slug,     local: "/media/bumpers/black_1s.mkv"
filler :pre_roll, collection: "type:bumper AND tag:classicrock_pre", mode: :shuffle
filler :fallback, collection: "type:bumper AND tag:classicrock_fill", mode: :shuffle

video_title = ->(item) { "#{item['Artists']&.first || 'Unknown'} — #{item['Name']}" }

layout :video_block do
  pre_roll count: 1
  main
  slug     between_items: true, duration: 1.0
  fill     with: :fallback
  epg      granularity: :per_item,
           title:       video_title,
           description: :from_main,
           category:    "Music"
end

schedule do
  block at: "00:00", collection: :rock_videos, layout: :video_block
  default_block      collection: :rock_videos, layout: :video_block
end
```

Why this works:

- `mode: :shuffle` is stateless — every run produces a fresh permutation, so the channel feels alive without any cursor management.
- The single anchored `block at: "00:00"` plus the `default_block` covers all 24 hours: the anchor takes effect at midnight; the default fills from then onward as needed.
- The custom `epg title:` lambda renders a music-video listing as `Queen — Bohemian Rhapsody` rather than just the file name.

## Pattern 2 — Branded multi-item block

You want 18 short cartoons across three hours to appear in the EPG as a single `Saturday Morning Cartoons` listing — not 18 individual entries. This is Channel 02's weekend block.

```ruby
collection :short_cartoons,
  "type:movie AND genre:Animation AND runtime:<00:15:00",
  mode: :random_with_memory, memory_window: 50

# ... fillers omitted for brevity ...

layout :saturday_bundle do
  pre_roll count: 1
  main
  slug      between_items: true, duration: 1.0
  post_roll count: 1
  fill      with: :fallback
  epg       granularity: :per_block,
            title:       :from_block,
            description: :from_block,
            category:    "Children"
end

schedule do
  block at: "08:00", collection: :short_cartoons, layout: :saturday_bundle,
        count: 18, on: :weekends,
        epg: { title:       "Saturday Morning Cartoons",
               description: "A rotating selection of classic animated shorts." }

  default_block collection: :short_cartoons, layout: :video_block
end
```

Two things to notice:

- `granularity: :per_block` plus `title: :from_block` says "make one EPG programme spanning the whole block; pull the title from the block's `epg:` override." The 18 cartoons all play, but viewers see one entry.
- `count: 18` puts an explicit cap on how many items the block draws. Without it, jfin2etv would draw items until the gap to the next anchor (11:00) was full — usually fine, but a fixed count makes the block predictable.

## Pattern 3 — Sequential episodic + commercial alignment

The full broadcast-TV pattern: a sitcom that plays one episode every hour, with mid-roll commercials filling the gap to the next 30-minute mark. This is Channel 03.

```ruby
channel number: "03", name: "Springfield", tuning: "03.1"

collection :simpsons,
  %q{series:"The Simpsons"},
  mode: :sequential, sort: :episode

filler :slug,       local: "/media/bumpers/black_1s.mkv"
filler :pre_roll,   collection: "type:bumper AND tag:ch03_pre",  mode: :shuffle
filler :post_roll,  collection: "type:bumper AND tag:ch03_post", mode: :shuffle
filler :mid_roll,   collection: "type:commercial AND decade:1990",
                    mode: :random_with_memory, memory_window: 100
filler :to_mid,     local: "/media/bumpers/brb.mkv"
filler :from_mid,   local: "/media/bumpers/back.mkv"
filler :fallback,   collection: "type:bumper AND tag:ch03_fill", mode: :shuffle

layout :sitcom_block do
  pre_roll  count: 1
  main
  mid_roll  every: :chapter, wrap_with: [:to_mid, :from_mid],
            count: :auto, per_break_target: 120
  post_roll count: 1
  slug      between_items: true, duration: 1.0
  fill      with: [:mid_roll, :fallback]
  epg       granularity: :per_item,
            title:       :from_main,
            description: :from_main,
            category:    "Comedy"
end

schedule do
  (0..23).each do |h|
    block at: "%02d:00" % h, collection: :simpsons, layout: :sitcom_block,
          count: 1, align: 30.minutes
  end
  default_block collection: :simpsons, layout: :sitcom_block, align: 30.minutes
end
```

This layout exercises every layout verb in service:

- `mode: :sequential, sort: :episode` keeps the cursor moving through episodes day after day.
- `(0..23).each do |h| block at: "%02d:00" % h, ..., count: 1 end` declares 24 anchors, one per hour.
- `align: 30.minutes` says each block should end on the next `:00` or `:30` mark.
- `count: :auto` distributes a computed commercial budget across chapter breaks; `per_break_target: 120` says "shoot for ~2 minutes per break."
- `fill with: [:mid_roll, :fallback]` absorbs any leftover slack with more commercials and trims the final filler to land exactly on the alignment target.

The result: a 22-minute episode in a 30-minute slot becomes ~22 minutes of content + ~8 minutes of period-appropriate commercials, with the fallback only ever providing the final sub-clip trim.

## Pattern 4 — Weekday/weekend split (two anchors, same time)

Two `block`s with the same `at:` are allowed if they have different `on:` filters. This is the standard way to give weekends and weekdays distinct content at a shared anchor:

```ruby
schedule do
  block at: "08:00", collection: :short_cartoons, layout: :saturday_bundle,
        count: 18, on: :weekends,
        epg: { title: "Saturday Morning Cartoons" }

  block at: "08:00", collection: :cartoon_reruns, layout: :cartoon_block,
        on: :weekdays
end
```

If the two `on:` clauses cover non-overlapping days, the duplicate-anchor validator is satisfied. (Two blocks at `08:00` with `on: nil` would raise — exactly one of them has to "claim" any given day.)

You can layer this further: `:mon`, `:tue`, etc., for fully day-specific programming, or a `Range` of `Date`s for "this special block runs only Dec 1 through Dec 25."

## Pattern 5 — Variant blocks (same anchor, content varies by day)

When you want to keep one stable EPG slot but rotate the content (and possibly the layout) across days of the week, use `variants:` with a hash selector:

```ruby
block at: "20:00",
      align: 30.minutes,
      count: 1,
      collection: :simpsons,        # default if selector returns a missing key
      layout:     :sitcom_block,
      variants: {
        weekdays: { collection: :simpsons,    layout: :sitcom_block },
        weekends: { collection: :movie_pool,  layout: :movie_night  },
      },
      variant: { weekdays: :weekdays, weekends: :weekends }
```

Or with a Proc selector for arbitrary logic:

```ruby
HOLIDAYS = [
  Date.new(2026, 12, 25),
  Date.new(2026, 7,  4),
].freeze

block at: "12:00",
      collection: :lunchtime_news,
      layout:     :news_block,
      variants: {
        standard: { collection: :lunchtime_news, layout: :news_block  },
        holiday:  { collection: :holiday_reel,   layout: :movie_night },
      },
      variant: ->(d) { HOLIDAYS.include?(d) ? :holiday : :standard }
```

Variants can override **only** `:collection` and `:layout`. If you need to vary `count:`, `align:`, or `epg:` across days, declare two separate blocks with different `on:` instead — that's Pattern 4's territory.

## Pattern 6 — Procedural EPG titles

The `title:` and `description:` keys of a layout's `epg` accept a lambda that's called once per item. The lambda receives the Jellyfin item Hash and returns a String.

The classic music-video example:

```ruby
video_title = ->(item) {
  artist = item['Artists']&.first || 'Unknown'
  "#{artist} — #{item['Name']}"
}

layout :video_block do
  # ...
  epg granularity: :per_item, title: video_title, description: :from_main
end
```

A date-aware variant for a daily programme:

```ruby
season_title = ->(item) {
  base = item['Name']
  d    = today
  if d.month == 12
    "#{base} (Holiday Edition)"
  else
    base
  end
}

layout :news_block do
  # ...
  epg granularity: :per_item, title: season_title
end
```

A few important constraints:

- The lambda's source is captured and re-evaluated outside the original script context — it must be source-capturable (literal `->(...) { ... }`, not built from `eval`).
- It can only refer to top-level constants, not to local variables defined in the surrounding script. `today` and `weekday?` (the [helpers](07-helpers-and-durations.md)) are available because they're injected as top-level methods.
- A common Jellyfin item Hash includes keys `'Name'`, `'Artists'`, `'SeriesName'`, `'Overview'`, `'ProductionYear'`, `'Genres'`. Use `jfin2etv resolve --channel N --collection NAME` to inspect a sample.

## Pattern 7 — Multi-file scripts

When a channel script gets long, split it across files. Every `*.rb` in the channel folder is loaded in alphabetical order; their declarations accumulate into the same `Plan`.

```
/scripts/03/
  01-channel.rb     # channel(...)
  02-collections.rb # all collection(...) calls
  03-fillers.rb     # all filler(...) calls
  04-layouts.rb     # all layout(...) blocks
  05-schedule.rb    # the schedule do ... end
```

Numeric prefixes guarantee the order; alphabetical names work too (`channel.rb` sorts before `collections.rb`, etc.). The five DSL verbs don't care which file they're called from — they all populate the same single-channel Plan.

A constraint to remember: **top-level constants don't leak across channels.** A `HOLIDAYS = [...]` at the top of `/scripts/03/01-channel.rb` is visible inside `/scripts/03/05-schedule.rb` (same channel, same Plan) but not from `/scripts/04/main.rb`. Each channel script is loaded with Ruby's `wrap=true`, giving it its own anonymous module.

## Pattern 8 — Holiday-aware programming

Combine a top-level constant of `Date`s with a Proc-based variant selector or `on:` filter:

```ruby
HOLIDAYS = [
  Date.new(2026, 1,  1),   # New Year's Day
  Date.new(2026, 7,  4),   # Independence Day
  Date.new(2026, 11, 26),  # Thanksgiving
  Date.new(2026, 12, 25),  # Christmas Day
].freeze

# Skip the regular sitcom on holidays:
block at: "20:00",
      collection: :simpsons,
      layout:     :sitcom_block,
      align:      30.minutes,
      count:      1,
      on:         ->(d) { !HOLIDAYS.include?(d) }

# A holiday-specific block that takes the slot on those days:
block at: "20:00",
      collection: :holiday_reel,
      layout:     :movie_night,
      align:      30.minutes,
      on:         ->(d) { HOLIDAYS.include?(d) }
```

This pattern is preferable to `variants:` when the holiday block needs a different `align:` or `count:` from the normal one — `variants:` can't override those.

For one-off date ranges (a "December specials" block running Dec 1–25), use a `Range` of `Date`s in `on:`:

```ruby
block at: "19:00",
      collection: :holiday_movies,
      layout:     :movie_night,
      align:      30.minutes,
      on:         (Date.new(2026, 12, 1)..Date.new(2026, 12, 25))
```

## Anti-patterns

A few things that look reasonable but cause problems:

### Don't read `ENV` directly

```ruby
# WRONG — ENV is not exposed to scripts:
api_key = ENV['JELLYFIN_API_KEY']

# Right — env() is the only sanctioned reader, and only for non-secrets:
tuning = env("CHANNEL_01_TUNING", default: "01.1")
```

`env()` filters out empty strings and applies defaults. Secrets like `JELLYFIN_API_KEY` aren't visible in the script context at all — that logic belongs in the Python host.

### Don't use raw Integers for `align:`

```ruby
# WRONG — raises a DSL error:
block at: "20:00", collection: :foo, layout: :bar, align: 1800

# Right — Duration helpers self-document the unit:
block at: "20:00", collection: :foo, layout: :bar, align: 30.minutes
```

If you really need a seconds value, use `1800.seconds`, but `30.minutes` is what real scripts use.

### Don't write `mid_roll every: 15.minutes`

The asymmetry between `align:` (`Duration`) and `every:` (`{ minutes: N }` Hash) is a wart in the DSL. Trying to use a `Duration` for `every:` raises a DSL error.

```ruby
# WRONG:
mid_roll every: 15.minutes, count: :auto

# Right:
mid_roll every: { minutes: 15 }, count: :auto
```

### Don't use unbounded `NOT`

```ruby
# WRONG — NOT with no library/collection bound:
collection :almost_nothing, "NOT tag:bumper_a", mode: :shuffle

# Right — bound the search inside a library:
collection :wholesome,
  %q{library:"Cartoons" AND NOT tag:adult_swim}, mode: :shuffle
```

See [`06-query-grammar.md`](06-query-grammar.md#not-and-the-bounded-not-rule).

### Don't rely on local variables inside captured Procs

```ruby
# WRONG — `prefix` may not be available when the planner re-evaluates:
prefix = "Episode: "
title  = ->(item) { "#{prefix}#{item['Name']}" }

# Right — top-level constants survive source capture:
PREFIX = "Episode: ".freeze
title  = ->(item) { "#{PREFIX}#{item['Name']}" }
```

The lambda's source is captured and re-evaluated in a fresh subprocess by the planner. Locals from the surrounding script aren't reliably visible; constants are.

## See also

- [`README.md`](README.md) — landing page with the Quick Start.
- The bundled examples themselves: [`examples/scripts/01/main.rb`](../../examples/scripts/01/main.rb), [`examples/scripts/02/main.rb`](../../examples/scripts/02/main.rb), [`examples/scripts/03/main.rb`](../../examples/scripts/03/main.rb).
- [`08-errors-and-validation.md`](08-errors-and-validation.md) — the validate/plan/resolve workflow you'll iterate with while adapting these patterns.
- [`DESIGN.md` §18](../../DESIGN.md#18-worked-examples) — the formal worked-examples section, including a sample generated playout JSON and XMLTV snippet.
