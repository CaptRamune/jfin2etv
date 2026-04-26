# 04 — `layout`

A **layout** is a reusable template describing how a single block is built: what plays before the main content, what plays after, where commercials go, what fills any leftover gap, and how the block projects into the EPG. You declare a layout once and reference it by symbol from one or more `block`s in the schedule.

## Synopsis

```ruby
layout :video_block do
  pre_roll  count: 1
  main
  mid_roll  every: :chapter, wrap_with: [:to_mid, :from_mid], count: :auto
  post_roll count: 1
  slug      between_items: true, duration: 1.0
  fill      with: [:mid_roll, :fallback]
  epg       granularity: :per_item, title: :from_main, category: "Music"
end
```

The `do ... end` block is required; `layout :foo` without a block raises `layout :foo requires a block`. Inside the block, you call any subset of these inner verbs. Each is described below.

## Positional vs. configuration verbs

There are two flavors of inner verb, and the distinction matters once you read other people's scripts:

- **Positional verbs** describe what plays in what order: `pre_roll`, `main`, `mid_roll`, `post_roll`. Their order in the block reflects the on-air order. (`mid_roll` is special-cased — it interleaves with the main item at chapter or minute boundaries, not "after main" — but you still write it in the body where it logically belongs.)
- **Configuration verbs** modify the surrounding sequence rather than adding a step at a position: `slug` (controls inter-item slugs across the whole layout), `fill` (says how to absorb leftover gap at the end), `epg` (the EPG metadata strategy).

You'll see both orders in the wild — the [Channel 02 cartoon layout](../../examples/scripts/02/main.rb) puts `slug` between `main` and `post_roll`; the [Channel 03 sitcom layout](../../examples/scripts/03/main.rb) puts `slug` after `post_roll`. Both work identically. Pick whichever order reads best to you.

## Inner verbs

### `pre_roll count: N`

Plays N items from the `:pre_roll` filler pool at the start of the block.

```ruby
pre_roll count: 1   # one bumper before main
pre_roll count: 0   # explicitly none (same as omitting)
```

`count:` defaults to 0. Negative counts raise `layout :foo: pre_roll count must be >= 0`.

If no `:pre_roll` filler has been declared, this step is a silent no-op — see [`03-fillers.md`](03-fillers.md#undefined-fillers-are-no-ops).

### `main`

A marker for "the collection's items go here." Almost every layout has one. Omit it for a filler-only layout (rare, e.g. a "dead air" placeholder).

```ruby
main
```

`main` takes no arguments.

### `mid_roll every:, wrap_with:, count:, per_break_target:`

Inserts groups of mid-roll items inside the main item, at chapter boundaries or fixed minute marks. This is what makes a sitcom feel like a sitcom.

```ruby
mid_roll every:            :chapter,
         wrap_with:        [:to_mid, :from_mid],
         count:            :auto,
         per_break_target: 120
```

| Arg | Required | Values |
|---|---|---|
| `every:` | yes | `:chapter`, `:never`, or `{ minutes: N }` |
| `wrap_with:` | no | A single symbol (`:to_mid` / `:from_mid`) or an array of either or both. Defaults to none. |
| `count:` | no | A positive Integer (fixed items per break) or `:auto` (compute from block alignment). Defaults to `1`. |
| `per_break_target:` | no | Soft target seconds per break, used when `count: :auto`. Default `120`. |

Worth unpacking each argument:

- `every: :chapter` fires a break at every chapter boundary of the main item, as reported by Jellyfin's `ChapterInfo`. If the item has no chapters, no breaks fire (and a debug log is emitted at run time).
- `every: { minutes: 15 }` fires a break every 15 minutes of wall-clock airtime inside the main item, regardless of chapters. Useful for movies or any content without chapter metadata.
- `every: :never` disables mid-rolls entirely — useful when you want to declare a layout that's similar to a chapter-broken one but explicitly skips the breaks.
- `wrap_with: [:to_mid, :from_mid]` sandwiches each break group between a "we'll be right back" bumper (drawn from `:to_mid`) and an "and now back to our show" bumper (drawn from `:from_mid`). Either symbol may be omitted independently.
- `count: 2` plays exactly 2 items per break. `count: :auto` computes a budget from the block's `align:` target and packs each break to at least `per_break_target` seconds — see the [Block alignment and flexible padding](../../DESIGN.md#block-alignment-and-flexible-padding) section of DESIGN.md for the math.
- `per_break_target:` is a **soft** target. Items come in discrete sizes; jfin2etv may overshoot or undershoot by up to ~30 seconds per break. Leftover slack is absorbed by the layout's `fill` step.

Validation:

- `wrap_with:` must be `:to_mid`, `:from_mid`, or an array combining only those — anything else raises `mid_roll wrap_with must be :to_mid and/or :from_mid`.
- `count:` must be a positive Integer or `:auto` — `mid_roll count must be a positive Integer or :auto`.
- `every: { minutes: N }` is the only Hash form accepted. `every: { hours: 1 }` is not — convert to `{ minutes: 60 }`.

### `post_roll count: N`

Symmetric to `pre_roll`. Plays N items from `:post_roll` at the end of the block (before `fill`).

```ruby
post_roll count: 1
```

### `slug between_items: true, duration: 1.0`

Inserts a `:slug` filler between every two consecutive items in the block. Not emitted at the very start or very end (use `pre_roll` / `post_roll` for that).

```ruby
slug between_items: true, duration: 1.0   # 1-second slug between items
slug between_items: true                  # use slug filler's natural duration
slug between_items: false                 # explicitly disable
```

`duration:` is in seconds (Float). If set, the slug source is trimmed (with `out_point_ms`) or looped to exactly that length. Looping is implemented by emitting N consecutive playout items with the same source plus a final trimmed item, so even a 0.5-second slug source can fill a 5-second gap.

If no `:slug` filler is declared, the step is a no-op.

### `fill with: <pool or list>`

Pads the leftover time at the end of the block (after `pre_roll` + `main` + `mid_roll`s + `post_roll`) until the block's target end. Without `fill`, leftover gap goes to whatever ErsatzTV-Next does with empty time (silence/black) — usually not what you want.

`with:` accepts:

- A single Symbol — one filler pool: `fill with: :fallback`
- An Array of Symbols — ordered priority list: `fill with: [:mid_roll, :fallback]`

The Array form is how you produce broadcast-realistic output: jfin2etv tries to absorb the leftover gap with the first pool (commercials, in the typical case), scanning items from it in `mode:` order and emitting each one whole. An item that would overshoot the remaining gap is *skipped* — the scan keeps going so a shorter item later in the same pool can still play, instead of prematurely punting a big chunk of the gap to fallback. Once every item has been considered, any residual is handed to the next pool intact. Only the **last** pool in the list is allowed to take the final sub-item trim that lands exactly on the target end — every earlier pool's items always play in full.

```ruby
fill with: :fallback                  # simple: just fallback
fill with: [:mid_roll, :fallback]     # prefer mid-roll commercials, fall through to fallback
```

Validation:

- `with:` must be a Symbol or Array of Symbols. Each symbol must be a known filler kind. Anything else raises `fill with: must be a Symbol or Array of Symbols` or `fill with entry must be one of [...] (got :foo)`.

If a referenced filler kind is undefined, that pool is treated as empty and skipped — the next pool in the list takes over.

### `epg granularity:, title:, description:, category:`

Declares how this layout projects into the XMLTV electronic program guide.

```ruby
epg granularity: :per_item,
    title:       :from_main,
    description: :from_main,
    category:    "Music"
```

| Arg | Required | Values |
|---|---|---|
| `granularity:` | yes | `:per_item`, `:per_block`, or `:per_chapter` |
| `title:` | no | `:from_main`, `:from_series`, `:from_block`, a literal String, or a Proc |
| `description:` | no | same as `title:` |
| `category:` | no | a literal String, e.g. `"Comedy"` |

If you omit `epg` entirely, the layout defaults to `granularity: :per_item, title: :from_main`.

#### Granularity

- **`:per_item`** — one EPG `<programme>` per main item. Fillers (slugs, pre/post/mid-rolls) are absorbed into the adjacent programme's start/stop times — viewers see "Bohemian Rhapsody, 20:00–20:04" rather than a separate "Bumper, 20:00–20:00:12" entry. Use for individual songs, episodes, movies.
- **`:per_block`** — one programme spans the entire block. Title/description come from the block's `epg:` override or from the layout/collection name. Use this to brand a multi-item block as a single show ("Saturday Morning Cartoons, 08:00–11:00") even though 18 individual cartoons are airing inside.
- **`:per_chapter`** — one programme per chapter of each main item. Useful for anthology shows where each chapter is a logically separate skit.

#### Title and description sources

`title:` (and `description:`, with the same rules) accepts five forms:

| Form | Example | Resolves to |
|---|---|---|
| `:from_main` | `title: :from_main` | The main Jellyfin item's name (series + episode title for episodes; title for movies; artist + track for music videos). |
| `:from_series` | `title: :from_series` | Series name only. Useful for `:per_block` so the whole block reads as the series. |
| `:from_block` | `title: :from_block` | The block's `epg: { title: "..." }` override (or the collection name as fallback). Used with `:per_block`. |
| `String` | `title: "Late Night Movies"` | A static literal that overrides everything. |
| `Proc` | `title: ->(item) { "#{item['Artists']&.first} — #{item['Name']}" }` | A lambda taking the Jellyfin item Hash and returning a String. Called once per item at plan time. |

The Proc form is captured by source: jfin2etv reads the lambda's source code and re-evaluates it later in a Ruby subprocess. This means the Proc must be **source-capturable** — built from a literal `->(...) { ... }` in the script, not from `eval` or a programmatically-constructed `Proc.new`. If source capture fails, you get a DSL error at plan emission time.

A typical Jellyfin item Hash includes keys like `'Name'`, `'Artists'`, `'SeriesName'`, `'Overview'`, `'ProductionYear'`, `'Genres'`. The exact shape comes from Jellyfin's `/Items` API; use `jfin2etv resolve --channel N --collection NAME` to inspect a sample.

#### Category

A simple literal String emitted as the XMLTV `<category>` element. Standard values include `"Music"`, `"Children"`, `"Comedy"`, `"Drama"`, `"News"`, `"Movies"` — most clients render these into icons or filtering chips in their EPG view.

## Examples

### Minimal music-video layout

From [Channel 01](../../examples/scripts/01/main.rb):

```ruby
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
```

The lambda is assigned to a local variable for readability, then passed to `epg title:`. Each music video gets a custom `Artist — Track` title.

### Branded multi-item block

From [Channel 02 `:saturday_bundle`](../../examples/scripts/02/main.rb):

```ruby
layout :saturday_bundle do
  pre_roll count: 1
  main
  slug     between_items: true, duration: 1.0
  post_roll count: 1
  fill     with: :fallback
  epg      granularity: :per_block,
           title:       :from_block,
           description: :from_block,
           category:    "Children"
end
```

`granularity: :per_block` collapses 18 individual cartoons into a single EPG entry. The block-level `epg:` override (declared on the `block`, not here) supplies the title `"Saturday Morning Cartoons"` and a one-sentence description.

### Full sitcom-with-commercials layout

From [Channel 03 `:sitcom_block`](../../examples/scripts/03/main.rb):

```ruby
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
```

Every layout verb is in service. `count: :auto` distributes a computed commercial budget across chapter breaks, sized by the block's `align:` target. `fill with: [:mid_roll, :fallback]` says "absorb leftover slack with more commercials; only use the fallback pool for the final sub-clip trim."

## Validation

| Trigger | Error |
|---|---|
| `layout :foo` without a block | `layout :foo requires a block` |
| Two layouts with the same name | `layout :foo already defined` |
| Negative count on pre/post/mid roll | `layout :foo: pre_roll count must be >= 0` (etc.) |
| `mid_roll wrap_with:` with anything other than `:to_mid`/`:from_mid` | `layout :foo: mid_roll wrap_with must be :to_mid and/or :from_mid` |
| `mid_roll count:` not Integer or `:auto` | `layout :foo: mid_roll count must be a positive Integer or :auto` |
| `mid_roll every:` not `:chapter`/`:never`/`{ minutes: N }` | `layout :foo: mid_roll every: must be :chapter, :never, or {minutes: N}` |
| `fill with:` not Symbol/Array | `layout :foo: fill with: must be a Symbol or Array of Symbols` |
| `epg granularity:` not in allowed set | `epg granularity must be one of [:per_item, :per_block, :per_chapter], got :foo` |
| `epg title:`/`description:` invalid type | `layout :foo: epg field must be :from_main, :from_series, :from_block, a String, or a Proc` |
| Lambda source not capturable | `layout :foo: cannot capture epg Proc source (MethodSource::SourceNotFoundError)` |

## See also

- [`05-schedule.md`](05-schedule.md) — how to anchor a layout to a wall-clock time with `block`, including the `align:` and `epg:` overrides this page references.
- [`03-fillers.md`](03-fillers.md) — how the seven filler kinds map to layout steps.
- [`DESIGN.md` §5.4](../../DESIGN.md#54-layout) — formal spec.
- [`DESIGN.md` §8](../../DESIGN.md#8-filler-semantics) — how the playout pipeline composes pre-roll, main, mid-roll, post-roll, slug, and fill into a single sequence.
- [`DESIGN.md` §9](../../DESIGN.md#9-epg-strategy) — the full EPG strategy, including how filler airtime is absorbed for `:per_item`.
