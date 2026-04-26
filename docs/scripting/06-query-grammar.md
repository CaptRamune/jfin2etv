# 06 — Jellyfin query grammar

The string passed to `collection :name, "..."` (and to `filler ..., collection: "..."`) is a small boolean expression that jfin2etv compiles into one or more Jellyfin `/Items` API queries plus a client-side filter. This page documents the full grammar.

## At a glance

```ruby
collection :rock_videos,
  "type:music_video AND (genre:Rock OR genre:\"Classic Rock\")", mode: :shuffle

collection :short_cartoons,
  "type:movie AND genre:Animation AND runtime:<00:15:00",        mode: :random_with_memory, memory_window: 50

collection :simpsons,
  %q{series:"The Simpsons"},                                     mode: :sequential, sort: :episode

collection :commercials_1990s,
  "type:commercial AND year:1990..1999",                         mode: :weighted_random, weight_field: "CommunityRating"
```

Whitespace is freely allowed between tokens. Operator keywords (`AND`, `OR`, `NOT`) are case-sensitive and must be uppercase. Field names (`type`, `genre`, etc.) are lowercase. Field **values** are case-insensitive when matched against Jellyfin metadata.

## Grammar (BNF)

```
expr        := term ( ( "AND" | "OR" ) term )*
             | "NOT" term
term        := "(" expr ")" | atom
atom        := field ":" value
field       := "type" | "genre" | "tag" | "series" | "studio" | "year"
             | "runtime" | "collection" | "library" | "rating" | "person"
value       := literal | quoted | range | comparison
literal     := /[A-Za-z0-9_.-]+/
quoted      := '"..."'             # supports spaces; escape " with \"
range       := /\d+\.\.\d+/        # e.g. 1990..1999
comparison  := "<" duration | ">" duration | "<=" duration | ">=" duration
             #   only for runtime:; duration is HH:MM:SS or PT… ISO 8601
```

Operator precedence (highest first): `NOT` > `AND` > `OR`. Use parentheses to override.

## Fields

Each row: the DSL field, what Jellyfin parameter it compiles to, and notes on the most common ways to use it.

### `type:` — item kind

```ruby
"type:movie"
"type:music_video"
"type:bumper"
```

The first thing every expression should pin down. Valid values:

| `type:` | Jellyfin item type | Typical use |
|---|---|---|
| `movie` | Movie | Films, animated shorts, anything packaged as a single file. |
| `episode` | Episode | A single episode of a series. |
| `series` | Series | The series record itself; rarely useful for playout — use `series:` instead. |
| `music_video` | MusicVideo | Music videos. |
| `audio` | Audio | Music tracks (audio-only). |
| `bumper` | (custom Jellyfin tag-mapped) | Channel idents, "next up" stings. |
| `commercial` | (custom) | Commercials, mid-roll ads. |
| `filler` | (custom) | Color bars, station idents. |
| `trailer` | Trailer | Movie trailers. |

The "custom" types map to whatever convention your Jellyfin library uses for those clip kinds — typically a tag and/or a folder structure under `/media/bumpers/`, `/media/commercials/`, etc. Set them up once in Jellyfin and the DSL grammar references them by their short name.

### `genre:`

```ruby
"genre:Rock"
"genre:\"Classic Rock\""        # quote when the value has spaces
%q{genre:"Classic Rock"}        # equivalent, easier to read
```

Matches Jellyfin's `Genres` field (case-insensitive). Items typically have multiple genres; matching one is enough.

### `tag:`

```ruby
"tag:preroll"
"tag:classicrock_pre"
%q{tag:"holiday special"}
```

Matches Jellyfin's `Tags` field. The most flexible mechanism for slicing your library — anything you can put in a tag, you can query.

### `series:`

```ruby
%q{series:"The Simpsons"}
%q{series:"Looney Tunes"}
```

Resolved by jfin2etv into the series's `Id` (via `/Items?SearchTerm=...&IncludeItemTypes=Series`), then used as a `ParentId` filter to fetch episodes. Quote series titles that contain spaces.

### `studio:`

```ruby
%q{studio:"HBO"}
%q{studio:"BBC"}
```

Matches Jellyfin's `Studios` field.

### `year:`

```ruby
"year:1990"            # exactly 1990
"year:1990..1999"      # any year in the range, inclusive
```

Matches `ProductionYear`. The `..` range form is expanded client-side into individual years.

### `runtime:`

```ruby
"runtime:<00:15:00"    # less than 15 minutes
"runtime:>00:30:00"    # more than 30 minutes
"runtime:<=01:00:00"   # at most 1 hour
"runtime:>=00:05:00"   # at least 5 minutes
```

Compares against `RunTimeTicks` (1 tick = 100 ns). The right-hand side is `HH:MM:SS`. Used to slice short cartoons out of your full Animation library, or to keep mid-roll commercials under a sane duration.

### `collection:`

```ruby
%q{collection:"Movies I Like"}
%q{collection:"Holiday Specials"}
```

Resolved into a Jellyfin BoxSet's `Id`. Matches items that belong to that BoxSet. Most Jellyfin users build a BoxSet by hand for "favorites" and similar curated lists.

### `library:`

```ruby
%q{library:"Cartoons"}
%q{library:"Music Videos"}
```

Resolved into a library's root `ParentId`. Limits the search to one library. Useful as a `NOT` boundary — see [NOT and the bounded-NOT rule](#not-and-the-bounded-not-rule) below.

### `rating:`

```ruby
"rating:>7.5"
"rating:>=8"
```

A client-side filter on Jellyfin's `CommunityRating` field. Items without a rating are excluded.

### `person:`

```ruby
%q{person:"Homer Simpson"}
```

Resolved into a `PersonIds` filter via Jellyfin's person lookup. Matches items that credit the person.

## Boolean operators

### `AND` — intersection

```ruby
"type:movie AND genre:Animation"            # animated movies
"type:music_video AND tag:holiday"          # holiday music videos
```

Both sides must match. Implemented as set intersection by `Id`.

### `OR` — union

```ruby
"genre:Rock OR genre:\"Classic Rock\""
"tag:bumper_a OR tag:bumper_b"
```

At least one side must match. Implemented as set union by `Id`.

### `NOT` — exclusion (with restrictions)

```ruby
%q{library:"Cartoons" AND NOT tag:adult_swim}
%q{collection:"Holiday Specials" AND NOT genre:"Documentary"}
```

`NOT term` matches items that don't match the term. **`NOT` requires a bounding `library:` or `collection:` atom elsewhere in the same expression** — see the next section.

### Parentheses

```ruby
"(genre:Rock OR genre:\"Classic Rock\") AND year:>=1980"
"type:movie AND (genre:Comedy OR genre:Romance)"
```

Standard precedence override. Without parens, `NOT` binds tightest, then `AND`, then `OR`.

## NOT and the bounded-NOT rule

A bare `NOT` would mean "every item in your entire Jellyfin library, minus the term's set" — typically tens of thousands of items, almost certainly not what you wanted. The DSL refuses to compile such expressions:

```ruby
collection :almost_nothing, "NOT tag:bumper_a", mode: :shuffle
# => unbounded NOT in expression "NOT tag:bumper_a";
#    bound with a library: or collection: atom
```

The fix is to add a `library:` or `collection:` atom that tells jfin2etv "search inside this set, not the whole world":

```ruby
# Good — search the Cartoons library, exclude the Adult Swim block:
collection :wholesome,
  %q{library:"Cartoons" AND NOT tag:adult_swim}, mode: :shuffle

# Good — anything in the curated Holiday Specials BoxSet that isn't a documentary:
collection :holiday_fun,
  %q{collection:"Holiday Specials" AND NOT genre:"Documentary"}, mode: :shuffle
```

The bound has to appear **somewhere in the same expression**, not necessarily next to the `NOT`. `(library:"X") AND foo AND NOT bar` works the same as `library:"X" AND NOT bar`.

## Query caching and performance

Each unique expression is hashed and cached for the duration of one generator run, so two collections using the same expression only cost one round-trip to Jellyfin. There's no need to factor a shared expression into a Ruby variable for performance.

If you do want it for readability:

```ruby
ROCK_FILTER = "type:music_video AND (genre:Rock OR genre:\"Classic Rock\")".freeze

collection :rock_videos,    ROCK_FILTER, mode: :shuffle
collection :rock_for_radio, ROCK_FILTER, mode: :weighted_random, weight_field: "CommunityRating"
```

Constants at the top of the file are visible everywhere in the same script. Per the [primer](00-ruby-primer.md#what-you-cannot-do-in-a-script), constants do **not** carry across to other channels' scripts.

## Recipes

### "All music videos except the holiday playlist"

```ruby
collection :rock_videos,
  %q{library:"Music Videos" AND NOT collection:"Holiday Music"},
  mode: :shuffle
```

### "Everything tagged X, but only in library Y"

```ruby
collection :late_night_movies,
  %q{library:"Movies" AND tag:late_night},
  mode: :shuffle
```

### "1990s commercials"

```ruby
filler :mid_roll,
  collection: "type:commercial AND year:1990..1999",
  mode: :random_with_memory, memory_window: 100
```

### "Long episodes only"

```ruby
collection :feature_episodes,
  %q{series:"Some Anthology Show" AND runtime:>=00:45:00},
  mode: :sequential, sort: :episode
```

### "All cartoons under 15 minutes"

```ruby
collection :short_cartoons,
  "type:movie AND genre:Animation AND runtime:<00:15:00",
  mode: :random_with_memory, memory_window: 50
```

### "Highly-rated weighted shuffle"

```ruby
collection :curator_pick,
  "type:music_video AND tag:weighted_pool AND rating:>=7.5",
  mode: :weighted_random, weight_field: "CommunityRating"
```

## Debugging an expression

When a block ends up empty or full of the wrong items, ask the planner what your expression actually matched:

```bash
docker compose exec jfin2etv jfin2etv resolve --channel 01 --collection rock_videos
```

This runs the expression against Jellyfin and prints the resolved item list — names, IDs, paths, runtimes — without writing any playout files. The most common surprises are:

- Genre or tag spelling mismatches (Jellyfin treats `Rock` and `rock` the same, but `Rock and Roll` ≠ `Rock & Roll`).
- A `series:` value that matches multiple series (the search returns the first hit).
- A `library:` name that doesn't exactly match what's in Jellyfin.
- A `runtime:` filter that excludes more items than you expected because Jellyfin's `RunTimeTicks` is missing for a chunk of your library.

## See also

- [`02-collections.md`](02-collections.md) — where these expressions are most often used.
- [`03-fillers.md`](03-fillers.md) — fillers also accept expressions via `collection:`.
- [`08-errors-and-validation.md`](08-errors-and-validation.md) — `jfin2etv resolve` and other debug commands.
- [`DESIGN.md` §5.8](../../DESIGN.md#58-jellyfin-query-expression-grammar) — formal spec including the per-field Jellyfin API mapping.
