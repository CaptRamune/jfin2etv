# 03 — `filler`

A **filler** is a named pool of short clips — bumpers, slugs, commercials, station idents — that jfin2etv weaves around the main content to make a channel feel like real broadcast TV. There are seven well-known kinds. You declare which kinds your channel uses by calling `filler` once per kind; the corresponding `layout` step references it later.

## Synopsis

```ruby
filler(
  kind,                             # symbol; one of the seven kinds below
  local:         "/media/...",      # exclusive with collection:
  collection:    "type:bumper ...", # exclusive with local:
  mode:          :shuffle,          # required when collection: is given
  sort:          nil,
  memory_window: nil,               # required when mode: :random_with_memory
  weight_field:  nil                # required when mode: :weighted_random
)
```

Two shapes. Pick **exactly one**:

```ruby
# 1. A single local file:
filler :slug, local: "/media/bumpers/black_1s.mkv"

# 2. A pool drawn from Jellyfin by query expression:
filler :pre_roll, collection: "type:bumper AND tag:classicrock_pre", mode: :shuffle
```

Passing both, or neither, raises:

> `filler :pre_roll: exactly one of local: or collection: is required`

## The seven filler kinds

| Kind | Where it plays | Typical content |
|---|---|---|
| `:slug` | Between every two items in a block (when `slug between_items: true`) | Half-second to two-second black frame, channel-bug overlay |
| `:pre_roll` | Before the main content of a block | "Up next on Springfield…" |
| `:post_roll` | After the main content | "Thanks for watching" |
| `:mid_roll` | At chapter boundaries (or every N minutes) of the main item | Commercials |
| `:to_mid` | Right before each mid-roll group | "We'll be right back" |
| `:from_mid` | Right after each mid-roll group | "And now back to our show" |
| `:fallback` | Loops to fill any leftover gap before the next anchored block | Station ident loop, color bars, silent filler |

You only need to declare the kinds your layouts actually reference. A 24/7 music-video channel might use just `:slug`, `:pre_roll`, and `:fallback`; a sitcom channel will typically use all seven.

## Local files vs. collections

### `local: "/path/to/file.mkv"`

A single file. Plays exactly as-is (or trimmed/looped to a duration if a layout's `slug` step says so). No randomization, no rotation — the same file every time. Use this for short, opinionated clips that you want to be deterministic: a black slug between songs, a "BRB" bumper before commercial breaks.

```ruby
filler :slug,     local: "/media/bumpers/black_1s.mkv"
filler :to_mid,   local: "/media/bumpers/brb.mkv"
filler :from_mid, local: "/media/bumpers/back.mkv"
```

The path is what ErsatzTV-Next will see inside its container — typically under `/media/`, the read-only shared volume. If the file isn't there, the playout item will fail at transcode time, not at plan time.

### `collection: "type:bumper AND tag:..."`

A pool of files, queried from Jellyfin and selected by `mode:`. Same expression grammar, same five modes as a top-level `collection` (see [`02-collections.md`](02-collections.md)). Use this for pools of multiple bumpers or commercials where you want variation.

```ruby
filler :pre_roll,
  collection: "type:bumper AND tag:classicrock_pre",
  mode: :shuffle

filler :mid_roll,
  collection: "type:commercial AND decade:1990",
  mode: :random_with_memory, memory_window: 100

filler :fallback,
  collection: "type:bumper AND tag:classicrock_fill",
  mode: :shuffle
```

`:random_with_memory` and `:weighted_random` need their respective extras (`memory_window:`, `weight_field:`) just like top-level collections, and the bounded-`NOT` rule applies to the expression too. See [`02-collections.md`](02-collections.md) for the cross-cutting validation rules.

## Examples by channel type

### Minimal music-video channel

```ruby
filler :slug,     local: "/media/bumpers/black_1s.mkv"
filler :pre_roll, collection: "type:bumper AND tag:classicrock_pre", mode: :shuffle
filler :fallback, collection: "type:bumper AND tag:classicrock_fill", mode: :shuffle
```

No mid-roll, no `to_mid`/`from_mid`, no post-roll: short songs back-to-back with a black slug between them is enough.

### Cartoon block

```ruby
filler :slug,      local: "/media/bumpers/black_1s.mkv"
filler :pre_roll,  collection: "type:bumper AND tag:toonz_pre",  mode: :shuffle
filler :post_roll, collection: "type:bumper AND tag:toonz_post", mode: :shuffle
filler :fallback,  collection: "type:bumper AND tag:toonz_fill", mode: :shuffle
```

Pre/post bumpers around each cartoon, no commercials in the middle.

### Full sitcom-with-commercials channel

```ruby
filler :slug,       local: "/media/bumpers/black_1s.mkv"
filler :pre_roll,   collection: "type:bumper AND tag:ch03_pre",  mode: :shuffle
filler :post_roll,  collection: "type:bumper AND tag:ch03_post", mode: :shuffle
filler :mid_roll,   collection: "type:commercial AND decade:1990",
                    mode: :random_with_memory, memory_window: 100
filler :to_mid,     local: "/media/bumpers/brb.mkv"
filler :from_mid,   local: "/media/bumpers/back.mkv"
filler :fallback,   collection: "type:bumper AND tag:ch03_fill", mode: :shuffle
```

Every kind in service. The mid-roll commercials use `:random_with_memory` so the same ad doesn't appear twice in a single afternoon.

## Undefined fillers are no-ops

A layout that calls `pre_roll count: 1` when no `:pre_roll` filler has been declared simply skips that step. No error, no warning at plan time — the layout is silently shorter than you'd expect. (jfin2etv may log a debug message at run time, but it won't surface in your normal validation flow.)

This is convenient (you don't have to declare unused kinds) but means typos in filler names won't be caught for you. If a block looks short on air, double-check that your layout's filler kinds match what you declared. Use `jfin2etv plan --channel N` to inspect the resolved plan AST and see exactly which fillers were registered.

## Validation

| Trigger | Error |
|---|---|
| Declaring two fillers of the same kind | `filler :pre_roll already defined` |
| Neither `local:` nor `collection:` | `filler :pre_roll: exactly one of local: or collection: is required` |
| Both `local:` and `collection:` | (same message) |
| Unknown `kind` | `filler kind must be one of [:slug, :pre_roll, :post_roll, :mid_roll, :to_mid, :from_mid, :fallback], got :foo` |
| `mode:` invalid | `filler :pre_roll mode must be one of [...], got :foo` |
| `:random_with_memory` without `memory_window:` | `filler :pre_roll mode :random_with_memory requires memory_window` |
| Unbounded `NOT` in `collection:` expression | `unbounded NOT in expression "..."; bound with a library: or collection: atom` |

## See also

- [`02-collections.md`](02-collections.md) — the same query grammar and modes apply to filler `collection:` pools.
- [`04-layouts.md`](04-layouts.md) — how `pre_roll`, `mid_roll`, `slug`, etc. inside a layout consume the filler pools you declare here.
- [`06-query-grammar.md`](06-query-grammar.md) — the expression grammar.
- [`DESIGN.md` §5.3](../../DESIGN.md#53-filler) — formal spec.
- [`DESIGN.md` §8](../../DESIGN.md#8-filler-semantics) — how fillers compose into a block, including the `fill` step's two pool forms and the EPG absorption rule (fillers don't show up in the guide).
