# Channel 03 — Springfield / Simpsons All Day (DESIGN.md §18.3)
# Sequential episodic playback with mid-roll commercials and 30-minute alignment.

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
