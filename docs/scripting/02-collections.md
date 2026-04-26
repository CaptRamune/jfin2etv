# 02 — `collection`

A **collection** is a named pool of media drawn from Jellyfin by a query expression, plus a strategy for picking the next item to play. Collections are the "what plays" of your channel; layouts and schedule are "how" and "when."

## Synopsis

```ruby
collection(
  name,                     # symbol; how you'll refer to this pool elsewhere
  expression,               # string; Jellyfin query (see 06-query-grammar.md)
  mode:          :shuffle,  # :shuffle | :sequential | :chronological |
                            # :random_with_memory | :weighted_random
  sort:          nil,       # field name; only used by :sequential
  memory_window: nil,       # required when mode is :random_with_memory
  weight_field:  nil        # required when mode is :weighted_random
)
```

Conventionally:

```ruby
collection :rock_videos,
  "type:music_video AND (genre:Rock OR genre:\"Classic Rock\")",
  mode: :shuffle
```

The first two arguments are positional (the name and the expression); everything else is a keyword.

## Required arguments

### `name` (positional, symbol)

A symbol that names the pool. You'll reference it from `block` and `default_block` later: `block at: "20:00", collection: :rock_videos, layout: :video_block`. Names are local to the channel; two channels can both have a `:rock_videos` collection without colliding.

Declaring two collections with the same name in the same channel raises `collection :foo already defined`.

### `expression` (positional, string)

A Jellyfin query expression — a small boolean grammar like `"type:movie AND genre:Animation AND runtime:<00:15:00"`. The full grammar, every field, every operator, and the bounded-`NOT` rule are documented in [`06-query-grammar.md`](06-query-grammar.md).

For now, just know that the expression is a **string**, and that strings with embedded double quotes are most readable as `%q{...}`:

```ruby
collection :simpsons, %q{series:"The Simpsons"}, mode: :sequential, sort: :episode
```

## The five playback modes

All five accept the same `expression`; what differs is how items are picked from it.

### `:shuffle`

Stateless. A fresh random permutation each generator run. No two consecutive items repeat within a run, but two different runs are independent — Tuesday's run might pick Bohemian Rhapsody first; Wednesday's might pick it third.

Use for: music videos, station idents, anything where order doesn't matter and short-term repetition is fine.

```ruby
collection :rock_videos, "type:music_video AND genre:Rock", mode: :shuffle
```

### `:sequential`

Stateful. Items are sorted by `sort:` (a Jellyfin field name), and a per-channel cursor in `/state/channel-{N}.sqlite` remembers where you left off. The next run picks up at the next item; on reaching the end, the cursor wraps to the beginning.

Use for: episodic shows you want to play in order across days, like a sitcom where Monday plays Episode 1 and Wednesday's run continues from wherever Tuesday's run finished.

```ruby
collection :simpsons, %q{series:"The Simpsons"},
  mode: :sequential, sort: :episode
```

`sort:` is required to be meaningful for `:sequential`. Common values: `:episode` (season+episode order), `:premiere_date`, `:name`. If the cursor's stored item is no longer in the result set (e.g. you renamed the series), the cursor resets to the start and an info log explains why.

### `:chronological`

Stateful, like `:sequential`, but with `sort:` fixed to `PremiereDate` ascending. Shorthand for the common case of "play in original air order." `sort:` is ignored if you set it.

```ruby
collection :cartoon_reruns, %q{series:"Looney Tunes"}, mode: :chronological
```

### `:random_with_memory`

Stateful. Picks randomly, but excludes any item played within the last `memory_window:` picks. When the eligible set empties (e.g. small pool, large window), it falls back to least-recently-played. Memory persists across runs.

Use for: pools where you want randomness but care about not hearing the same song twice in an hour.

```ruby
collection :short_cartoons,
  "type:movie AND genre:Animation AND runtime:<00:15:00",
  mode: :random_with_memory, memory_window: 50
```

`memory_window:` is **required** when this mode is set; omitting it raises:

> `collection :short_cartoons mode :random_with_memory requires memory_window`

### `:weighted_random`

Stateless. Each item's probability is proportional to a numeric Jellyfin field named by `weight_field:`. Common choice: `"CommunityRating"`, so high-rated items play more often.

```ruby
collection :rated_videos,
  "type:music_video AND tag:weighted_pool",
  mode: :weighted_random, weight_field: "CommunityRating"
```

`weight_field:` is **required** for this mode:

> `collection :rated_videos mode :weighted_random requires weight_field`

Items missing the weight field are skipped silently.

## Mode summary

| Mode | Stateful | Required extra | Notes |
|---|---|---|---|
| `:shuffle` | no | none | Fresh permutation per run. |
| `:sequential` | yes | `sort:` (recommended) | Cursor wraps at end. |
| `:chronological` | yes | none (sort fixed) | Same as `:sequential` by `PremiereDate`. |
| `:random_with_memory` | yes | `memory_window:` | Excludes recent N picks. |
| `:weighted_random` | no | `weight_field:` | Probability ∝ field value. |

Stateful modes share `/state/channel-{N}.sqlite`; see [`DESIGN.md` §11](../../DESIGN.md#11-state-management) for the schema.

## Examples

```ruby
# Endless shuffle of music videos:
collection :rock_videos,
  "type:music_video AND (genre:Rock OR genre:\"Classic Rock\")",
  mode: :shuffle

# Sequential sitcom playback, cursor persists across days:
collection :simpsons, %q{series:"The Simpsons"},
  mode: :sequential, sort: :episode

# Original-air-date ordering for a vintage cartoon block:
collection :cartoon_reruns, %q{series:"Looney Tunes"}, mode: :chronological

# Random shorts but no repeats within the last 50 picks:
collection :short_cartoons,
  "type:movie AND genre:Animation AND runtime:<00:15:00",
  mode: :random_with_memory, memory_window: 50

# Filler commercials, weighted by Jellyfin community rating:
collection :commercials_1990s,
  "type:commercial AND year:1990..1999",
  mode: :weighted_random, weight_field: "CommunityRating"
```

## What changing the expression does to state

The expression is hashed (SHA-256) and stored alongside the cursor. If you edit your script and change a collection's expression, the hash mismatches and **the cursor is reset to the start** — sequential collections begin again at item one, `:random_with_memory`'s history is wiped. jfin2etv logs an info message explaining why.

This is usually what you want: changing the query means changing the pool, and a cursor into the old pool wouldn't make sense in the new one. If you need to preserve a cursor across an expression edit, you'd have to manually migrate `/state/channel-{N}.sqlite` — usually not worth it.

See [`DESIGN.md` §11.4](../../DESIGN.md#114-expression-hash) for the gritty detail.

## Validation

| Trigger | Error |
|---|---|
| Two collections with the same name | `collection :foo already defined` |
| Mode is not a known symbol | `collection mode must be one of [:shuffle, :sequential, :chronological, :random_with_memory, :weighted_random], got :random` |
| `:random_with_memory` without `memory_window:` | `collection :foo mode :random_with_memory requires memory_window` |
| `:weighted_random` without `weight_field:` | `collection :foo mode :weighted_random requires weight_field` |
| Expression contains `NOT` without a `library:` or `collection:` boundary | `unbounded NOT in expression "..."; bound with a library: or collection: atom` |

The bounded-`NOT` rule is the trickiest; see [`06-query-grammar.md`](06-query-grammar.md#not-and-the-bounded-not-rule) for an explanation and worked examples.

## See also

- [`03-fillers.md`](03-fillers.md) — fillers also accept a `collection:` expression and the same modes.
- [`05-schedule.md`](05-schedule.md) — how to anchor a collection to a wall-clock time with `block`.
- [`06-query-grammar.md`](06-query-grammar.md) — the full Jellyfin query expression grammar.
- [`08-errors-and-validation.md`](08-errors-and-validation.md) — `jfin2etv resolve --collection NAME` to inspect what your expression actually matches.
- [`DESIGN.md` §5.2](../../DESIGN.md#52-collection) — formal spec.
- [`DESIGN.md` §11.3](../../DESIGN.md#113-per-mode-semantics) — per-mode state semantics.
