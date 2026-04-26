# 08 — Errors, validation, and debugging

This page covers how the DSL reports errors, what every common error message means, and the four CLI commands you'll use to debug a script before it ever gets near a real Jellyfin run.

## Two failure shapes

When the Ruby runner evaluates your script, it can fail in one of two ways:

### 1. DSL errors (exit code 2)

Anything the DSL can detect at evaluation time without talking to Jellyfin: unknown keys, duplicate declarations, malformed clock strings, mode/`memory_window` mismatches, the bounded-NOT rule. The runner raises a `Jfin2etv::DSLError`, prints the message to stderr, and exits with code 2.

```
jfin2etv: DSL error in unknown key(s) [:framerate] at transcode.video; allowed: [:format, :width, ...]
```

These are the errors you can — and should — surface during authoring with `jfin2etv validate`.

### 2. Ruby exceptions (exit code 1)

Anything else: a syntax error in your script, a `NoMethodError` on a misspelled method, a `Date.new` that fails because you typed `Date.new(2026, 13, 1)`. The runner prints the exception class, message, and full backtrace to stderr and exits with code 1.

```
NoMethodError: undefined method `Foo' for nil:NilClass
/scripts/03/main.rb:12:in `block in <top (required)>'
...
```

The Python host surfaces both kinds of stderr in its logs verbatim, so a failed scheduled run shows you the same diagnostic you'd get running `validate` by hand.

## Author workflow: the four commands

In rough order of how often you'll use them:

### `jfin2etv validate --channel N`

Parse + DSL-validate one channel. No Jellyfin is touched. Fast (sub-second).

```bash
docker compose exec jfin2etv jfin2etv validate --channel 03
```

Run this after every edit. If it exits silently, your script is well-formed; if it complains, fix and re-run. Validate every channel without `--channel`:

```bash
docker compose exec jfin2etv jfin2etv validate
```

### `jfin2etv plan --channel N`

Run the full Ruby runner and dump the resolved plan AST as JSON. Useful when validation is clean but the on-air output isn't what you expected — the AST shows you what the runner actually built from your script (sorted block list, defaulted-in transcode fields, captured Proc sources, etc.).

```bash
docker compose exec jfin2etv jfin2etv plan --channel 03
```

The plan AST schema is documented in [`DESIGN.md` §6.2](../../DESIGN.md#62-plan-ast-schema-v1). Most useful sections to inspect:

- `schedule.blocks[]` — sorted by `at_seconds` then `on`. Confirms your loop generated the right anchors.
- `layouts.<name>.steps[]` — verifies the `slug` / `fill` / `epg` you wrote landed in the right shape.
- `collections.<name>` — confirms the expression text and mode arguments.

### `jfin2etv resolve --channel N --collection NAME`

Run the channel's Jellyfin queries and print the resolved item list. Use when a `block` is unexpectedly empty, a `:sequential` cursor isn't picking the items you expected, or you suspect a `library:` / `genre:` typo.

```bash
docker compose exec jfin2etv jfin2etv resolve --channel 01 --collection rock_videos
```

Drop `--collection` to resolve every collection on the channel.

### `jfin2etv once --channel N --dry-run`

Full pipeline — Ruby evaluation, Jellyfin queries, planner expansion, target file paths — but no disk writes. Best for smoke-testing a complex schedule without committing actual playout files. Combine with `--force` and `--from YYYY-MM-DD` to preview a specific day.

```bash
docker compose exec jfin2etv jfin2etv once --channel 03 --dry-run
docker compose exec jfin2etv jfin2etv once --channel 03 --dry-run --force --from 2026-04-25
```

When you're satisfied, drop `--dry-run` to actually write the files. (`--force` is needed only if you want to overwrite already-written days; see [`DESIGN.md` §10.4](../../DESIGN.md#104---force-mode).)

## DSL error catalog

Every `DSLError` the runtime can raise, grouped by verb. Each row gives the message body (after the `jfin2etv: DSL error in ...` prefix), the cause, and the fix.

### `channel`

| Message | Cause | Fix |
|---|---|---|
| `channel declared more than once` | Two `channel(...)` calls in the same script directory. | Use only one `channel` per channel; if you split your script into multiple `.rb` files, put `channel` in just one of them. |
| `transcode must be a Hash, got <class>` | Something other than `{...}` was passed to `transcode:`. | Wrap your settings in a Hash literal. |
| `unknown key(s) [...] at transcode; allowed: [:ffmpeg, :video, :audio, :playout]` | Top-level transcode key isn't recognized. | Move the field into the right sub-hash; check spelling. |
| `unknown key(s) [...] at transcode.video; allowed: [...]` | Same as above for nested keys (`transcode.ffmpeg`, `transcode.audio`, `transcode.audio.loudness`, `transcode.playout`). | Compare against the [allowed keys](01-channel.md#transcode-hash). |
| `transcode.video.format is required` | Required field is `nil` after the deep-merge (you set it to nil explicitly). | Don't override required fields with nil; just omit them. Same for `width`, `height`, `audio.format`, `audio.channels`. |
| `transcode.video.format must be one of [:h264, :hevc], got :av1` | Bad enum value. | Use one of the listed symbols. Same pattern for `video.accel`, `video.vaapi_driver`, `audio.format`. |

### `collection`

| Message | Cause | Fix |
|---|---|---|
| `collection :foo already defined` | Two `collection :foo, ...` calls. | Rename one. |
| `collection mode must be one of [:shuffle, :sequential, :chronological, :random_with_memory, :weighted_random], got :random` | Typo in the mode symbol. | Use one of the five valid modes. |
| `collection :foo mode :random_with_memory requires memory_window` | Missing required extra. | Add `memory_window: 50` (or whatever depth you want). |
| `collection :foo mode :weighted_random requires weight_field` | Missing required extra. | Add `weight_field: "CommunityRating"` (or another numeric Jellyfin field). |
| `unbounded NOT in expression "..."; bound with a library: or collection: atom` | A `NOT` appears with no `library:` or `collection:` boundary. | Add a `library:"..."` or `collection:"..."` atom. See [Bounded NOT](06-query-grammar.md#not-and-the-bounded-not-rule). |

### `filler`

| Message | Cause | Fix |
|---|---|---|
| `filler :foo already defined` | Two `filler :foo, ...` calls. | Combine them into one (typically by promoting the `local:` form to a `collection:` query). |
| `filler kind must be one of [:slug, :pre_roll, :post_roll, :mid_roll, :to_mid, :from_mid, :fallback], got :foo` | Unknown kind. | Use one of the seven kinds. |
| `filler :foo: exactly one of local: or collection: is required` | Both or neither given. | Pick one. |
| `filler :foo mode :random_with_memory requires memory_window` | Same pattern as collections. | Add `memory_window:`. |

### `layout`

| Message | Cause | Fix |
|---|---|---|
| `layout :foo requires a block` | Called as `layout :foo` with no `do ... end`. | Add the body block. |
| `layout :foo already defined` | Two layouts with the same name. | Rename one. |
| `layout :foo: pre_roll count must be >= 0` | Negative count. (Same for `post_roll`.) | Use 0 or a positive integer. |
| `layout :foo: mid_roll wrap_with must be :to_mid and/or :from_mid` | Wrap with a non-bumper symbol. | Only `:to_mid` and `:from_mid` are accepted (alone or as an array). |
| `layout :foo: mid_roll count must be a positive Integer or :auto` | Bad count. | Use a positive Integer or `:auto`. |
| `layout :foo: mid_roll every: must be :chapter, :never, or {minutes: N}` | Bad `every:` shape. | Use one of the three accepted forms. |
| `layout :foo: mid_roll every: hash must be {minutes: N}` | Wrong hash key (e.g. `{ hours: 1 }`). | Convert to minutes: `{ minutes: 60 }`. |
| `layout :foo: fill with: must be a Symbol or Array of Symbols` | Wrong type. | Pass a Symbol or an Array of Symbols. |
| `layout :foo: fill with entry must be one of [...]` | An entry in the array isn't a known filler kind. | Check spelling. |
| `epg granularity must be one of [:per_item, :per_block, :per_chapter], got :foo` | Bad granularity. | Use one of the three. |
| `layout :foo: epg field must be :from_main, :from_series, :from_block, a String, or a Proc` | Bad title/description type. | Use one of the listed forms. |
| `layout :foo: cannot capture epg Proc source (MethodSource::SourceNotFoundError)` | Lambda wasn't built from a literal `->...` (e.g. via `eval`). | Define the lambda as a literal `->(item) { ... }` in the script. |

### `schedule` and `block`

| Message | Cause | Fix |
|---|---|---|
| `schedule requires a block` | `schedule` called with no `do ... end`. | Add the body. |
| `schedule declared more than once` | Two `schedule do ... end`. | Combine them. |
| `no schedule do ... end declared` | Script omitted `schedule` entirely. | Every channel needs a schedule. |
| `no channel() declared` | Script omitted `channel(...)` entirely. | Every channel needs `channel(...)`. |
| `block at:: expected HH:MM or HH:MM:SS, got "8:00"` | Bad clock format (single-digit hour, missing colon, etc.). | Use two-digit zero-padded form: `"08:00"`. |
| `block at:: out-of-range clock "25:00"` | Hour > 23, minute > 59, etc. | Stay within `00:00..23:59:59`. |
| `block count must be nil, Integer, or :auto (got ...)` | Bad type. | Use one of the listed types. |
| `block count must be >= 0` | Negative. | Zero or positive. |
| `block on: expects Symbol \| Array \| Range \| Proc, got Hash` | Wrong type for the day-of-week filter. | Use one of the four forms. |
| `block align: must be a Duration (e.g. 30.minutes), got Integer seconds explicitly wrap with .seconds` | Passed a raw Integer. | `30.minutes`, `1.hour`, etc. (or `1800.seconds` if you must). |
| `block align: must be a Duration, got String` | Wrong type. | Use a Duration helper. |
| `block variants: must be a Hash, got ...` | Wrong type. | Pass a Hash mapping variant keys to `{ collection:, layout: }`. |
| `block variants[:foo]: must be a Hash, got ...` | A variant entry wasn't a Hash. | Each entry is `{ collection: ..., layout: ... }`. |
| `block variants[:foo]: only :collection and :layout are allowed, got extras [:count]` | Tried to override a non-content field in a variant. | Use two separate blocks with different `on:` instead. |
| `block variants: requires a matching variant: selector` | `variants:` given without `variant:`. | Add the selector. |
| `block variant: given without variants:` | `variant:` given without `variants:`. | Either add `variants:` or remove `variant:`. |
| `block variant: unknown day-of-week key :funday; allowed: [:mon, :tue, ..., :sun, :weekdays, :weekends, :default]` | Bad key in the hash selector. | Use one of the listed keys. |
| `block variant: value :foo does not match any variants key (...)` | Selector returns a key not in `variants:`. | Either add the variant or change the selector. |
| `block variant: must be a Hash or Proc` | Wrong type. | Use a Hash (DOW form) or a `->(date) { ... }` lambda. |
| `block variant: cannot capture Proc source (...)` | Same Proc-capture issue as EPG titles. | Use a literal `->(...) { ... }` in the script. |
| `unknown key(s) [...] at block epg:; allowed: [:title, :description, :category]` | Bad key in the per-block `epg:` override. | Move category-style fields into the layout's `epg`. |
| `default_block declared more than once` | Two `default_block`s. | Use only one. |
| `duplicate anchor times in schedule (same at: and on:): [...]` | Two `block`s with the same `(at:, on:)` pair. | Either change one's `at:` or differentiate them with `on:`. |

## Things that fail silently

Not every problem raises an error. A few common surprises produce a working-but-empty channel:

- **Block references an undeclared collection or layout.** The Ruby validator doesn't cross-check schedule symbols against the collection/layout registries — that happens later in the Python planner. The symptom is a `block` that produces no playout items. Fix by checking `jfin2etv plan --channel N` for the symbol you expect.
- **Layout uses an undeclared filler kind.** Per [`03-fillers.md`](03-fillers.md#undefined-fillers-are-no-ops), this is a no-op, not an error. The block looks short on air.
- **Collection expression matches zero items.** No error; the block's main slot becomes pure `:fallback` filler. Use `jfin2etv resolve --channel N --collection NAME` to see what's actually matching.
- **Main item is missing duration metadata in Jellyfin.** The planner drops the item and tries the next; if every item is missing a runtime, the block becomes filler-only. Check Jellyfin's library scan; sometimes a `RunTimeTicks` field needs a re-scan to populate.
- **Lambda refers to a local variable that doesn't survive source capture.** The lambda re-evaluates with only top-level constants visible. Symptom: `NoMethodError` on `nil` inside the lambda when the planner runs it. Move the data to a top-level constant (`HOLIDAYS = [...]`).

## See also

- [`DESIGN.md` §6.3](../../DESIGN.md#63-error-model) — the formal error model and exit codes.
- [`DESIGN.md` §6.4](../../DESIGN.md#64-validation-only-mode) — how `jfin2etv validate` works under the hood.
- [`DESIGN.md` §13](../../DESIGN.md#13-cli-surface) — full CLI reference.
- [`DESIGN.md` §15](../../DESIGN.md#15-error-and-failure-modes) — runtime failure modes (Jellyfin unreachable, empty pools, disk full).
