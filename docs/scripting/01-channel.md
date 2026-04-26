# 01 — `channel`

`channel` declares the channel itself: its number, display name, IPTV tuning ID, optional logo, language, and the transcode profile that ErsatzTV-Next will use to encode the stream. Exactly one `channel(...)` call per script directory.

## Synopsis

```ruby
channel(
  number:    "01",
  name:      "Classic Rock Videos",
  tuning:    "01.1",                          # optional; defaults to number
  icon:      "/media/logos/classicrock.png",  # optional
  language:  "en",                            # optional; default "en"
  transcode: { ... }                          # optional; deep-merged with defaults
)
```

The parentheses are conventionally omitted:

```ruby
channel number: "01", name: "Classic Rock Videos", tuning: "01.1",
        icon: "/media/logos/classicrock.png"
```

## Required arguments

### `number:`

The channel number, as a string. Coerced from any value with `String(...)`, so `number: 1` becomes `"1"`, but the convention is to write it as a quoted, zero-padded string that matches the folder name (`number: "01"` for `/scripts/01/`). The folder name is what jfin2etv treats as canonical when it picks the channel up off disk; the `number:` you declare is what appears in M3U/XMLTV output.

> Mismatch is allowed but confusing. If your folder is `/scripts/01/` and your script says `number: "1"`, the M3U will list channel `1` while the playout JSON will be written under `/ersatztv-config/channels/01/`. Just match them.

### `name:`

The human-readable channel name, e.g. `"Classic Rock Videos"`. Shows up in the IPTV client's channel list.

## Optional arguments

### `tuning:`

The `tvg-chno` value emitted into the M3U. Defaults to the channel `number:`. Used by IPTV clients to display a "TV-style" channel number — `02.1`, `02.2`, etc. — that's distinct from the storage number. If you don't have a strong opinion, omit it.

### `icon:`

A `/media/...` path or a fully-qualified `http(s)://...` URL pointing at a logo image. Surfaces in IPTV client EPG views. Optional; omit it and clients will show no icon.

### `language:`

A BCP-47 language tag (e.g. `"en"`, `"fr"`, `"es"`). Default `"en"`. Used as the `lang=` attribute on the channel's XMLTV `<display-name>` element and on programme metadata where applicable.

### `transcode:`

A nested hash describing how ErsatzTV-Next should encode this channel's output. **You almost never need to touch this** — the default profile produces a valid 1080p H.264 channel on any host with CPU-only ffmpeg, which is what you want until you have a specific reason otherwise.

When you do override, you only specify the fields you want to change; jfin2etv deep-merges your hash with the default. See [Transcode hash](#transcode-hash) below for the full schema, the default, and worked examples.

## Examples

### Minimal

The bare minimum. Defaults take care of everything else.

```ruby
channel number: "01", name: "Classic Rock Videos"
```

### Typical

What most channel scripts look like:

```ruby
channel number: "02", name: "Toonz", tuning: "02.1"
```

### With icon

```ruby
channel number: "01", name: "Classic Rock Videos", tuning: "01.1",
        icon: "/media/logos/classicrock.png"
```

### Hardware-accelerated transcode override

This is a **partial** override; everything not mentioned (audio settings, ffmpeg paths, bit depth, etc.) is inherited from the default.

```ruby
channel number: "10", name: "Movies",
        transcode: {
          video: {
            format:       :hevc,
            bitrate_kbps: 6000,
            buffer_kbps:  12000,
            accel:        :vaapi,
            vaapi_device: "/dev/dri/renderD128",
            vaapi_driver: :ihd,
          },
        }
```

### Loudness normalization for a music channel

```ruby
channel number: "01", name: "Classic Rock Videos",
        transcode: {
          audio: {
            bitrate_kbps:       192,
            normalize_loudness: true,
            loudness: {
              integrated_target: -14.0,    # streaming-loud, not broadcast-loud
              range_target:       11.0,
              true_peak:          -1.0,
            },
          },
        }
```

## Transcode hash

The `transcode:` hash mirrors ErsatzTV-Next's `channel_config.json` schema one-for-one. Sub-hash names and field names match the schema; jfin2etv translates Ruby symbols (`:hevc`, `:vaapi`) to the schema's lower-case string enums at emission time.

### Top-level keys

| Key | Purpose |
|---|---|
| `:ffmpeg` | Paths to `ffmpeg` and `ffprobe` binaries; filter allow/block lists. |
| `:video` | Codec, resolution, bitrate, hardware acceleration. |
| `:audio` | Codec, channels, sample rate, optional loudness normalization. |
| `:playout` | Currently just `virtual_start:` (rarely used). |

Any other top-level key raises a `DSLError`. The same is true at every nested level — see [Validation](#validation) below.

### Default profile

If you omit `transcode:` entirely, this is what you get:

```ruby
{
  ffmpeg: {
    ffmpeg_path:       "ffmpeg",
    ffprobe_path:      "ffprobe",
    disabled_filters:  [],
    preferred_filters: [],
  },
  video: {
    format:            :h264,
    width:             1920,
    height:            1080,
    bitrate_kbps:      4000,
    buffer_kbps:       8000,
    bit_depth:         8,
    accel:             nil,         # CPU-only
    deinterlace:       false,
    tonemap_algorithm: nil,
    vaapi_device:      nil,
    vaapi_driver:      nil,
  },
  audio: {
    format:             :aac,
    bitrate_kbps:       160,
    buffer_kbps:        320,
    channels:           2,
    sample_rate_hz:     48_000,
    normalize_loudness: false,
    loudness:           nil,
  },
  playout: {
    virtual_start: nil,
  },
}
```

### Deep-merge rule

Your hash is deep-merged with the default. That means:

- Top-level keys you don't mention come from the default.
- Inside any sub-hash you mention, **only** the keys you list are overridden; siblings still come from the default.
- A leaf value you set to `nil` overrides the default with `nil` (used to disable a default — e.g. clear `accel:` back to CPU after enabling it elsewhere).

So `transcode: { video: { accel: :cuda } }` is equivalent to taking the full default hash and changing exactly one field.

### Allowed enum values

| Field | Allowed |
|---|---|
| `video.format` | `:h264`, `:hevc` |
| `video.accel` | `:cuda`, `:qsv`, `:vaapi`, `:videotoolbox`, `:vulkan`, or `nil` (CPU) |
| `video.vaapi_driver` | `:ihd`, `:i965`, `:radeonsi` |
| `audio.format` | `:aac`, `:ac3` |

Passing an unrecognized symbol raises a `DSLError` listing the allowed values.

### Loudness sub-hash

If `audio.normalize_loudness` is `true`, the `audio.loudness` sub-hash configures the EBU R 128 targets. All three keys are required when `loudness:` is given:

| Key | Typical | Purpose |
|---|---|---|
| `integrated_target` | `-23.0` (broadcast), `-14.0` (streaming) | LUFS target. |
| `range_target` | `7.0` (tight) to `11.0` (relaxed) | Loudness range in LU. |
| `true_peak` | `-2.0` (broadcast), `-1.0` (streaming) | dBTP ceiling. |

## Validation

`channel(...)` runs full validation at evaluation time, before any Jellyfin calls. The most common errors:

| Trigger | Error message (prefix) |
|---|---|
| Calling `channel(...)` twice in the same script directory | `channel declared more than once` |
| `transcode:` not a hash | `transcode must be a Hash, got <class>` |
| Unknown top-level key | `unknown key(s) [...] at transcode; allowed: [:ffmpeg, :video, :audio, :playout]` |
| Unknown sub-hash key | `unknown key(s) [...] at transcode.video; allowed: [...]` |
| Required field missing after merge | `transcode.video.format is required` (or `width`, `height`, `audio.format`, `audio.channels`) |
| Bad enum value | `transcode.video.accel must be one of [:cuda, :qsv, :vaapi, :videotoolbox, :vulkan], got :metal` |

A failed `channel(...)` aborts the channel for this run. Existing playout files are not touched (the immutability rule from [`DESIGN.md` §10.2](../../DESIGN.md#102-immutability-rule)). Use `jfin2etv validate --channel N` after every edit so you catch these before the next scheduled run.

## See also

- [`02-collections.md`](02-collections.md) — what to declare next.
- [`08-errors-and-validation.md`](08-errors-and-validation.md) — full DSL-error catalog and the `validate`/`plan` debug commands.
- [`DESIGN.md` §5.1](../../DESIGN.md#51-channel) — the formal `channel` spec.
- [`DESIGN.md` §4.2](../../DESIGN.md#42-channeljson-and-lineupjson-ownership) — how `channel.json` and `lineup.json` are generated from your `transcode:` hash.
