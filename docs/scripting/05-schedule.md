# 05 — `schedule`

`schedule` is where you anchor your collections and layouts to the wall clock. It's the last verb in every channel script and the only one that decides what airs at what time of day.

## Synopsis

```ruby
schedule do
  block at: "08:00", collection: :short_cartoons, layout: :saturday_bundle, on: :weekends, count: 18
  block at: "08:00", collection: :cartoon_reruns, layout: :cartoon_block,   on: :weekdays
  block at: "11:00", collection: :cartoon_reruns, layout: :cartoon_block
  block at: "19:00", collection: :short_cartoons, layout: :cartoon_block

  default_block collection: :short_cartoons, layout: :cartoon_block
end
```

The `do ... end` block is required. Inside, you call any number of `block ...` and at most one `default_block ...`. The schedule block is mandatory in every channel script — without one you'll see `no schedule do ... end declared` from the runner.

## How blocks fit together

Each `block` declares an **anchor**: an explicit `at:` time when something starts. jfin2etv sorts the blocks by `at:`, then plays each block from its anchor until the next block's anchor (wrapping at midnight). The `default_block` covers any gap longer than 1 hour where no anchored block applies (see [`DESIGN.md` §5.5](../../DESIGN.md#55-schedule)).

A schedule has no concept of "duration of a block" — duration is implicit: it's the gap between this block's anchor and the next one's. The `align:` and `count:` arguments described below are the levers you use to shape what fits inside that gap.

## `block`

### Synopsis

```ruby
block(
  at:         "20:00",      # required; "HH:MM" or "HH:MM:SS"
  collection: :simpsons,    # required; symbol naming a declared collection
  layout:     :sitcom_block,# required; symbol naming a declared layout
  count:      nil,          # optional; max main items
  on:         nil,          # optional; day-of-week filter
  align:      nil,          # optional; Duration to round target end to
  epg:        nil,          # optional; per-block EPG overrides
  variants:   nil,          # optional; alternative configurations
  variant:    nil           # optional; selector for variants
)
```

### Required arguments

#### `at:`

A 24-hour clock string in the channel's timezone. Format `"HH:MM"` or `"HH:MM:SS"`.

```ruby
block at: "08:00",    ...     # 8 AM
block at: "20:00",    ...     # 8 PM
block at: "23:30:00", ...     # 11:30 PM (the seconds are optional)
```

Validation:

- Out-of-range hours/minutes (e.g. `"25:00"` or `"08:99"`) raise `block at:: out-of-range clock "25:00"`.
- Non-string or wrong-format values raise `block at:: expected HH:MM or HH:MM:SS, got ...`.

#### `collection:`

A symbol naming a collection you've already declared with `collection :name, "..." `. The block draws its main items from this pool.

```ruby
collection :simpsons, %q{series:"The Simpsons"}, mode: :sequential, sort: :episode

schedule do
  block at: "20:00", collection: :simpsons, layout: :sitcom_block
end
```

Referencing an undeclared collection is not caught at evaluation time (the runner doesn't cross-check the schedule against the collection registry); it surfaces later when the Python planner tries to expand the block. Use `jfin2etv plan --channel N` to see the AST and confirm your symbols line up.

#### `layout:`

A symbol naming a layout declared with `layout :name do ... end`. Same caveat about cross-referencing as `collection:`.

### Optional arguments

#### `count:`

How many main items to draw from the collection.

| Value | Meaning |
|---|---|
| `nil` (default) | Fill the gap. Pull items until the layout overhead + main items reach the next anchor. |
| `Integer ≥ 0` | Draw exactly N main items. `count: 0` means filler-only. |
| `:auto` | Reserved for future flex behavior. Currently treated like `nil`. |

```ruby
block at: "20:00", collection: :simpsons, layout: :sitcom_block, count: 1
                  # exactly one episode per slot
block at: "08:00", collection: :short_cartoons, layout: :saturday_bundle, count: 18
                  # exactly 18 cartoons in the morning bundle
```

Validation: `count:` must be `nil`, a non-negative Integer, or `:auto`. `count: -1` raises `block count must be >= 0`. `count: 1.5` raises `block count must be nil, Integer, or :auto`.

#### `on:`

Day-of-week filter. The block is only active on matching days; on non-matching days, jfin2etv treats the slot as if the block weren't declared, which means the previous matching block's gap extends through it (or the `default_block` kicks in).

Five forms accepted:

| Form | Example | Meaning |
|---|---|---|
| Symbol (single day) | `on: :monday` (or `:mon`) | Mondays only. |
| Symbol (alias) | `on: :weekdays` / `on: :weekends` | Mon–Fri / Sat–Sun. |
| Array | `on: [:mon, :wed, :fri]` | Any listed day. |
| Range of `Date`s | `on: (Date.new(2026,12,1)..Date.new(2026,12,25))` | A specific date window. |
| Proc taking a `Date` | `on: ->(d) { d.month == 12 }` | Arbitrary logic. |

```ruby
# Two blocks at 08:00 — different audiences:
block at: "08:00", collection: :short_cartoons, layout: :saturday_bundle, on: :weekends, count: 18
block at: "08:00", collection: :cartoon_reruns, layout: :cartoon_block,   on: :weekdays
```

This is how Channel 02 carves Saturday morning out of the rest of the week without conflicting anchors. (See [duplicate anchors](#duplicate-anchors) below for the rule that makes this work.)

A Proc selector is captured by source like the EPG `title:` Proc — it must be source-capturable.

#### `align:`

Snaps the block's target end time to a clock-friendly boundary, expressed as a `Duration` from the [duration helpers](07-helpers-and-durations.md#integer-duration-helpers).

```ruby
block at: "20:00", collection: :simpsons, layout: :sitcom_block, count: 1, align: 30.minutes
```

Read `align: 30.minutes` as: "make this block end on the next `:00` or `:30` mark after the natural end of the main item." A 22-minute Simpsons episode in a 30-minute block leaves ~8 minutes of slack, which the layout's `mid_roll`s and `fill` step distribute as commercials and a final trim.

| Common `align:` values | Effect |
|---|---|
| `30.minutes` | `:00` and `:30` grid (sitcoms) |
| `1.hour` | top of the hour (dramas, hour-long shows) |
| `15.minutes` | quarter-hour grid (short news segments) |

The alignment target is **always capped at the next anchored block** — if the next block is at `21:00` and `align: 1.hour` would land at `21:30`, the cap wins and the target end is `21:00`.

The alignment is anchored to the top of the current hour, not to the block's `at:`. So `align: 30.minutes` always means the `:00`/`:30` grid regardless of when the block started.

> **Must be a `Duration`, not an Integer.** `align: 1800` (raw seconds) raises `block align: must be a Duration (e.g. 30.minutes), got Integer seconds explicitly wrap with .seconds`. Use `1800.seconds` if you really want seconds, or — better — `30.minutes`. This restriction exists because the helpers self-document the unit.

`align:` works on `default_block` too.

#### `epg:`

Per-block overrides for the layout's `epg`. Lets one layout (e.g. `:cartoon_block`) be reused across many blocks while each block supplies its own title and description for the EPG.

Allowed keys: `title:`, `description:`, `category:`. Any other key raises `unknown key(s) [...] at block epg:; allowed: [:title, :description, :category]`.

```ruby
block at: "08:00", collection: :short_cartoons, layout: :saturday_bundle,
      count: 18, on: :weekends,
      epg: { title:       "Saturday Morning Cartoons",
             description: "A rotating selection of classic animated shorts." }
```

Precedence (highest wins): per-block `epg:` override > layout's `epg ... title: "..."` > the layout's `:from_main`/`:from_block` resolution.

The override values are passed through as Strings (`epg: { title: nil }` is allowed and means "no override for title").

#### `variants:` and `variant:`

Same `at:`, same anchor — but different content depending on the day. Lets one slot host different shows on different days while keeping a single, stable EPG entry. See [Block variants](#block-variants) below.

## `default_block`

A fallback block used to fill any schedule gap longer than 1 hour where no anchored block applies. Most commonly the "dead of night" filler, but also useful for keeping a 24/7 channel running with one declaration:

```ruby
schedule do
  block at: "00:00", collection: :rock_videos, layout: :video_block
  default_block collection: :rock_videos, layout: :video_block
end
```

```ruby
default_block(
  collection: :foo,        # required
  layout:     :bar,        # required
  align:      30.minutes   # optional, same semantics as block align:
)
```

At most one `default_block` per schedule; declaring a second raises `default_block declared more than once`.

`default_block` does not accept `at:`, `count:`, `on:`, `epg:`, or `variants:`/`variant:` — those are block-level concerns.

## Block variants

A block with `variants:` declares **alternative configurations** chosen at plan time by the block's `variant:` selector. The selector is evaluated once per day-in-window. A variant can override **only** `:collection` and `:layout`; every other field (`at:`, `count:`, `on:`, `align:`, `epg:`) stays fixed at the outer block's value. This keeps the EPG's wall-clock grid stable regardless of which variant is active.

### Hash selector (day-of-week)

```ruby
block at: "20:00",
      align: 30.minutes,
      count: 1,
      collection: :simpsons,        # used when selector resolves to a missing key
      layout:     :sitcom_block,
      variants: {
        weekdays: { collection: :simpsons,    layout: :sitcom_block },
        weekends: { collection: :movie_pool,  layout: :movie_night  },
      },
      variant: { weekdays: :weekdays, weekends: :weekends }
```

Selector keys (right-hand side of `variant:`):

| Symbolic days | `:mon`, `:tue`, `:wed`, `:thu`, `:fri`, `:sat`, `:sun` |
| Aliases | `:weekdays`, `:weekends` |
| Catch-all | `:default` |

Resolution order: exact day symbol > `:weekdays`/`:weekends` > `:default`. A hash that maps no key to the date being planned and has no `:default` raises a DSL error at plan time.

### Proc selector (arbitrary logic)

```ruby
HOLIDAYS = [Date.new(2026, 12, 25), Date.new(2026, 7, 4)].freeze

block at: "12:00",
      collection: :lunchtime_news,
      layout:     :news_block,
      variants: {
        standard: { collection: :lunchtime_news, layout: :news_block  },
        holiday:  { collection: :holiday_reel,   layout: :movie_night },
      },
      variant: ->(d) { HOLIDAYS.include?(d) ? :holiday : :standard }
```

The lambda receives a `Date` in the channel's timezone and must return a Symbol that matches one of the `variants:` keys.

The Proc is captured by source and re-evaluated daily by a Ruby helper subprocess — same caveat as EPG title Procs. Refer only to top-level constants (`HOLIDAYS = [...]` declared at the file's top level) and not to local variables.

### Variant rules

- A variant entry may omit `:collection` or `:layout`; missing fields fall back to the outer block's value.
- A variant entry may **not** introduce keys other than `:collection` and `:layout`. Trying e.g. `weekdays: { collection: ..., count: 5 }` raises `block variants[:weekdays]: only :collection and :layout are allowed, got extras [:count]`.
- `variants:` requires `variant:` and vice versa. Either alone raises an error.
- An unknown variant key returned by the selector raises a DSL error at plan time.
- `on:` is applied **before** variant resolution. A block skipped by `on:` is skipped entirely; variants do not rescue it.

When you need to vary something other than collection/layout (say, different `count:` on weekends), declare two separate blocks with distinct `on:` filters instead — the typical Channel 02 pattern.

## Looping pattern

When you want one anchor per hour, use a Ruby loop:

```ruby
schedule do
  (0..23).each do |h|
    block at: "%02d:00" % h, collection: :simpsons, layout: :sitcom_block,
          count: 1, align: 30.minutes
  end
  default_block collection: :simpsons, layout: :sitcom_block, align: 30.minutes
end
```

This is what Channel 03 does to give every hour of the day its own anchor. The `"%02d:00" % h` is Ruby's printf-style formatting for a zero-padded 2-digit hour.

## Duplicate anchors

Two blocks may share the same `at:` only if they have different `on:` filters. The validator looks at the `(at_seconds, on)` pair and rejects collisions:

```ruby
# Allowed — different on:
block at: "08:00", collection: :short_cartoons, layout: :saturday_bundle, on: :weekends
block at: "08:00", collection: :cartoon_reruns, layout: :cartoon_block,   on: :weekdays

# Rejected — same at: with no on:
block at: "08:00", collection: :a, layout: :x
block at: "08:00", collection: :b, layout: :y
# => duplicate anchor times in schedule (same at: and on:): [...]
```

This is the rule that makes weekday/weekend splits work.

## Validation

| Trigger | Error |
|---|---|
| `schedule` without a block | `schedule requires a block` |
| `schedule` declared more than once | `schedule declared more than once` |
| Bad `at:` format | `block at:: expected HH:MM or HH:MM:SS, got ...` |
| Out-of-range time | `block at:: out-of-range clock "25:00"` |
| `count:` not nil/Integer/`:auto` | `block count must be nil, Integer, or :auto (got ...)` |
| Negative `count:` | `block count must be >= 0` |
| Bad `on:` type | `block on: expects Symbol \| Array \| Range \| Proc, got Hash` |
| `align:` is plain Integer | `block align: must be a Duration (e.g. 30.minutes), got Integer seconds explicitly wrap with .seconds` |
| `align:` is wrong type | `block align: must be a Duration, got String` |
| `variants:` not a Hash | `block variants: must be a Hash, got ...` |
| `variants:` without `variant:` | `block variants: requires a matching variant: selector` |
| `variant:` without `variants:` | `block variant: given without variants:` |
| Variant entry has extra keys | `block variants[:foo]: only :collection and :layout are allowed, got extras [:count]` |
| Unknown DOW key in selector | `block variant: unknown day-of-week key :funday; allowed: [...]` |
| Selector returns key not in variants | `block variant: value :foo does not match any variants key (...)` |
| `epg:` has unknown key | `unknown key(s) [...] at block epg:; allowed: [:title, :description, :category]` |
| Two `default_block`s | `default_block declared more than once` |
| Two blocks with same `(at:, on:)` | `duplicate anchor times in schedule (same at: and on:): [...]` |

## See also

- [`02-collections.md`](02-collections.md) — what `collection:` references.
- [`04-layouts.md`](04-layouts.md) — what `layout:` references, including the layout-level `epg` that block-level `epg:` overrides.
- [`07-helpers-and-durations.md`](07-helpers-and-durations.md) — the `30.minutes` / `1.hour` helpers used by `align:`.
- [`09-cookbook.md`](09-cookbook.md) — schedule patterns including weekday/weekend splits, hourly loops, and holiday-aware variants.
- [`DESIGN.md` §5.5](../../DESIGN.md#55-schedule) — formal spec.
- [`DESIGN.md` §5.5.1](../../DESIGN.md#551-block-variants) — the variants design and edge cases.
