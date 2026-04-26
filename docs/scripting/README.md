# Writing channel scripts

This directory is the scripting guide for **jfin2etv**'s Ruby DSL. If you're here, you want to add a channel — or fix one — by writing a small Ruby file.

## What a channel is

Each channel lives in its own folder under `/scripts/`:

```
/scripts/
  01/main.rb         # channel 01
  02/main.rb         # channel 02
  03/main.rb         # channel 03
```

The folder name **is** the channel number. Inside the folder, every `*.rb` file is loaded in alphabetical order; their declarations accumulate into a single plan. Most channels are a single `main.rb`, but you can split a complex channel into `main.rb` + `fillers.rb` + `layouts.rb` if it helps you stay organized — see [Pattern 7 in the cookbook](09-cookbook.md#pattern-7--multi-file-scripts).

Once a day (default 04:00 local) jfin2etv re-evaluates every channel script, asks Jellyfin what content matches each query, and writes 72 hours of playout JSON for ErsatzTV-Next to read. The full lifecycle is covered in the project's [`DESIGN.md`](../../DESIGN.md); this guide only covers what you write.

## Quick start

Here is a complete, working channel — a 24/7 music-video shuffle. Drop it at `/scripts/01/main.rb` and you have a channel.

```ruby
# /scripts/01/main.rb

channel number: "01", name: "Classic Rock Videos", tuning: "01.1"

collection :rock_videos,
  "type:music_video AND (genre:Rock OR genre:\"Classic Rock\")",
  mode: :shuffle

filler :slug,     local: "/media/bumpers/black_1s.mkv"
filler :pre_roll, collection: "type:bumper AND tag:classicrock_pre", mode: :shuffle
filler :fallback, collection: "type:bumper AND tag:classicrock_fill", mode: :shuffle

layout :video_block do
  pre_roll count: 1
  main
  slug     between_items: true, duration: 1.0
  fill     with: :fallback
  epg      granularity: :per_item, title: :from_main, category: "Music"
end

schedule do
  block at: "00:00", collection: :rock_videos, layout: :video_block
  default_block collection: :rock_videos, layout: :video_block
end
```

Reading top to bottom:

1. **`channel ...`** declares the channel itself — its number, display name, and tuning ID. (See [`01-channel.md`](01-channel.md).)
2. **`collection :rock_videos, "..."`** names a pool of items pulled from Jellyfin by a query expression. Here we pull music videos tagged Rock or Classic Rock and play them in random order. (See [`02-collections.md`](02-collections.md) and [`06-query-grammar.md`](06-query-grammar.md).)
3. **`filler :slug, :pre_roll, :fallback`** declares three filler pools used to make the channel feel like real broadcast TV: a slug between songs, a station bumper before each one, and a fallback used to plug any leftover gap before the next anchored block. (See [`03-fillers.md`](03-fillers.md).)
4. **`layout :video_block do ... end`** defines a reusable template: pre-roll, main item, 1-second slug between items, fallback to fill any tail-gap, and EPG metadata strategy. (See [`04-layouts.md`](04-layouts.md).)
5. **`schedule do ... end`** anchors the layout to the wall clock. The single `block at: "00:00"` runs from midnight forward; `default_block` covers any gap the schedule doesn't explicitly fill. (See [`05-schedule.md`](05-schedule.md).)

That's the whole vocabulary. Every other script in this codebase — including the 24/7 sitcom channel with hourly mid-roll commercials — is just more of the same five verbs.

## Reading order

If Ruby is new to you, read these in order:

1. [`00-ruby-primer.md`](00-ruby-primer.md) — symbols, blocks, procs, and the rest of the Ruby you'll meet.
2. [`01-channel.md`](01-channel.md) — `channel(...)` and the transcode hash.
3. [`02-collections.md`](02-collections.md) — `collection(...)` and the five playback modes.
4. [`03-fillers.md`](03-fillers.md) — the seven filler kinds.
5. [`04-layouts.md`](04-layouts.md) — `layout do ... end` and every inner verb.
6. [`05-schedule.md`](05-schedule.md) — `schedule do ... end`, `block`, `default_block`, `variants`, day-of-week filters.
7. [`06-query-grammar.md`](06-query-grammar.md) — the Jellyfin query expression grammar.
8. [`07-helpers-and-durations.md`](07-helpers-and-durations.md) — `local`, `http`, `today`, `weekday?`, `env`, and `30.minutes`/`1.hour`.
9. [`08-errors-and-validation.md`](08-errors-and-validation.md) — the catalog of DSL errors, what each one means, and the commands you use to debug.
10. [`09-cookbook.md`](09-cookbook.md) — eight worked patterns built from the three bundled examples plus common variations.

If you already know Ruby, skip the primer and read the per-verb pages in any order — each one is self-contained and cross-links to the others where they touch.

## Running and debugging your script

Three commands you'll use constantly while authoring. Each is explained in detail in [`08-errors-and-validation.md`](08-errors-and-validation.md).

```bash
# Parse + DSL-validate; no Jellyfin needed. Fast.
docker compose exec jfin2etv jfin2etv validate --channel 01

# Dump the plan AST as JSON. Shows what your script actually produced.
docker compose exec jfin2etv jfin2etv plan --channel 01

# Probe a collection: which Jellyfin items does the expression match?
docker compose exec jfin2etv jfin2etv resolve --channel 01 --collection rock_videos

# Full run for one channel, no disk writes.
docker compose exec jfin2etv jfin2etv once --channel 01 --dry-run
```

Use `validate` after every edit. Use `plan` when the validate is clean but the on-air result is wrong. Use `resolve` when a block is unexpectedly empty.

## A note on what's not here

This guide covers writing channel scripts and only that. The host-side configuration (`jfin2etv.yml`), the Docker stack, the Python planner, the ErsatzTV-Next playout JSON shape, and the XMLTV format internals are all in [`DESIGN.md`](../../DESIGN.md) and [`README.md`](../../README.md). Each page below links into DESIGN.md when a script-author decision depends on host-side behavior — but the prose is self-contained for routine authoring.
