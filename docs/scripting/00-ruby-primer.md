# 00 — A Ruby primer for non-Rubyists

This page covers only the Ruby features the jfin2etv DSL actually uses. If you've ever written Python, JavaScript, or another dynamic language, everything here will look familiar — Ruby just spells some things differently.

You can write a perfectly good channel script with nothing but the patterns shown below. There is no need to learn Ruby in the large.

## Comments

```ruby
# Anything after a # on a line is a comment.
channel number: "01", name: "Foo"   # trailing comments work too
```

There are no block comments worth worrying about; just use `#` on each line.

## Symbols (`:foo`)

A symbol is a tiny, immutable, self-describing name. Think of them as enum tokens. The DSL uses symbols anywhere a fixed set of values is expected.

```ruby
mode: :shuffle           # one of: :shuffle, :sequential, :chronological,
                         #         :random_with_memory, :weighted_random
on:   :weekdays          # day-of-week filter
filler :pre_roll, ...    # the filler kind is a symbol
```

A symbol is not a string. `:shuffle` and `"shuffle"` are different values, and the DSL specifically wants the symbol form. If you pass a string where a symbol is required, you'll see a `DSLError` saying so.

## Strings

Two flavors: single-quoted (literal) and double-quoted (interpolating).

```ruby
"hello"                  # plain string
"genre:Rock"             # plain string (no interpolation needed)
"#{artist} — #{title}"   # interpolated; #{...} evaluates inside double quotes
'no #{interpolation}'    # single quotes: literal, no interpolation
```

When a string contains lots of double quotes — common in Jellyfin query expressions — Ruby's `%q{...}` and `%Q{...}` forms keep the quoting tidy:

```ruby
"series:\"The Simpsons\""        # ok, but ugly
%q{series:"The Simpsons"}        # nicer; %q is single-quote-equivalent
%Q{series:"#{name}" AND year:1990} # %Q is double-quote-equivalent (allows interpolation)
```

You'll see `%q{...}` a lot in real scripts.

## Hashes and keyword arguments

A hash is a key-value map; in other languages you'd call it a dict, object, or map.

```ruby
{ number: "01", name: "Foo" }    # symbol keys (the common case)
{ "number" => "01" }              # string keys, "rocket" syntax (rare in DSL)
```

Almost every DSL verb takes **keyword arguments**, which look like trailing hash entries:

```ruby
channel(number: "01", name: "Classic Rock Videos", tuning: "01.1")
```

The parentheses and the trailing braces are both optional, so you'll usually see:

```ruby
channel number: "01", name: "Classic Rock Videos", tuning: "01.1"
```

Keyword arguments are positional only insofar as they all come after any non-keyword positional arguments. Their order among themselves doesn't matter.

## Nested hashes

Some DSL kwargs (notably `transcode:` on `channel` and `epg:` on `block`) take a nested hash:

```ruby
channel number: "01", name: "Foo",
        transcode: {
          video: { format: :hevc, width: 1920, height: 1080, accel: :vaapi },
          audio: { format: :aac, channels: 2 },
        }
```

Trailing commas inside hashes and argument lists are fine; in fact they're encouraged because diffs stay smaller when you add another entry.

## Blocks (`do ... end`)

A block is a chunk of code passed to a method. The DSL uses blocks for `layout` and `schedule`:

```ruby
layout :video_block do
  pre_roll count: 1
  main
  fill with: :fallback
end
```

Inside the block, you call DSL verbs that belong to the layout (`pre_roll`, `main`, `mid_roll`, `post_roll`, `slug`, `fill`, `epg`). They aren't available outside the block.

The same shape applies to `schedule`:

```ruby
schedule do
  block at: "08:00", collection: :foo, layout: :video_block
  default_block collection: :foo, layout: :video_block
end
```

You may also see `{ ... }` instead of `do ... end` for short single-line blocks; the DSL is fine with either, but `do ... end` is the convention here.

## Procs and lambdas (`->(x) { ... }`)

A proc is a callable value. The DSL accepts procs in two places:

- The `title:` and `description:` of a layout's `epg` (called once per item).
- The `variant:` selector of a `block` (called once per day).

The lambda syntax — `->(x) { ... }` — is the form the DSL expects. The arrow declares the parameter list; the braces wrap the body.

```ruby
# Per-item EPG title computed from the Jellyfin item hash.
video_title = ->(item) { "#{item['Artists']&.first || 'Unknown'} — #{item['Name']}" }

layout :video_block do
  # ...
  epg granularity: :per_item, title: video_title
end
```

```ruby
# Day-of-week variant selector.
block at: "20:00",
      collection: :simpsons,
      layout: :sitcom_block,
      variants: { weekdays: { collection: :simpsons,   layout: :sitcom_block },
                  weekends: { collection: :movie_pool, layout: :movie_night  } },
      variant: ->(d) { d.saturday? || d.sunday? ? :weekends : :weekdays }
```

The runner captures the lambda's **source code** (not its closure) and re-evaluates it later when the date is known. This means a lambda may not reliably refer to local variables defined elsewhere in the script — keep it self-contained, or only refer to top-level constants.

> If you need a constant inside a lambda, put it at the top of the file: `HOLIDAYS = [Date.new(2026,12,25), ...]`. Constants are visible from the re-evaluated source.

## Ranges (`(0..23)`, `(1..5)`)

A range is a pair of endpoints. They appear in two places:

```ruby
(0..23).each do |h|
  block at: "%02d:00" % h, collection: :simpsons, layout: :sitcom_block, count: 1
end
```

```ruby
on: (Date.new(2026,12,1)..Date.new(2026,12,25))    # block runs only during Advent
```

`(0..23)` includes both endpoints; `(0...23)` (three dots) excludes the upper one.

## Iteration: `each`, `map`, `times`

Looping in Ruby is method-based. `each` runs a block for each element; `times` runs it N times.

```ruby
(0..23).each do |h|
  block at: "%02d:00" % h, collection: :simpsons, layout: :sitcom_block, count: 1
end

3.times { |i| filler :"slug_#{i}", local: "/media/bumpers/black_#{i}s.mkv" }
```

The `|h|` between pipes is the block parameter — like the `for h in range(24):` variable in Python. You can iterate over arrays, ranges, hashes, and anything that responds to `each`.

## Arrays

Square brackets, comma-separated. The DSL uses arrays for ordered priority lists:

```ruby
fill with: [:mid_roll, :fallback]              # try :mid_roll first, fall through to :fallback
mid_roll wrap_with: [:to_mid, :from_mid]       # both bumpers
```

Single-element arrays are usually unnecessary — the DSL accepts a bare symbol where an array of one symbol would also be valid (`fill with: :fallback` and `fill with: [:fallback]` are equivalent).

## String formatting

Two patterns you'll see often:

```ruby
"%02d:00" % h            # printf-style: zero-padded 2-digit hour, e.g. "07:00"
"#{artist} — #{title}"   # interpolation inside double quotes
```

The `%`-form is the right tool for hour anchors in a `(0..23).each` loop.

## Booleans, nil, truthiness

```ruby
true  false  nil
```

Only `false` and `nil` are falsy in Ruby. Everything else (including `0` and `""`) is truthy.

`nil` is the absence-of-value, used by the DSL when you want to "leave a kwarg at its default":

```ruby
filler :slug, local: "/media/bumpers/black_1s.mkv"
# vs
filler :pre_roll, collection: "type:bumper", mode: :shuffle, sort: nil
```

In practice you just omit the kwarg.

## What you cannot do in a script

The Ruby runtime is real Ruby, but the DSL is meant to be **declarative**. A few things are intentionally constrained:

- **`ENV` is not exposed.** Use the [`env(name, default: nil)`](07-helpers-and-durations.md#env) helper, which only returns non-empty strings. Secrets like `JELLYFIN_API_KEY` are not visible to scripts at all (they live in the Python host).
- **No I/O.** Don't read files, open sockets, or shell out. The runner redirects stdout to stderr so any `puts` you add for debugging shows up in jfin2etv's logs without corrupting the plan AST, but that's the only I/O you should rely on.
- **No `require` of arbitrary gems.** The runner pre-loads `jfin2etv` and that's all you can count on.
- **Top-level constants don't leak between channels.** Each channel script is loaded with `wrap=true`, which gives it its own anonymous module. Defining `HOLIDAYS = [...]` in `/scripts/01/main.rb` does **not** make it visible from `/scripts/02/main.rb`. If you need shared logic, copy it.
- **A lambda's closure may not survive.** As noted above, lambda source is captured and re-evaluated; refer to top-level constants in the same file, not to local variables.

## What's next

You now know enough Ruby to read every example in this guide. Continue to [`01-channel.md`](01-channel.md) for the first DSL verb.
