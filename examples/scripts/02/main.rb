# Channel 02 — Saturday Morning Cartoons / Toonz (DESIGN.md §18.2)
# Demonstrates weekend-anchored branded blocks with :per_block EPG granularity.

channel number: "02", name: "Toonz", tuning: "02.1"

collection :short_cartoons,
  "type:movie AND genre:Animation AND runtime:<00:15:00",
  mode: :random_with_memory, memory_window: 50

collection :cartoon_reruns,
  %q{series:"Looney Tunes"},
  mode: :chronological

filler :slug,      local: "/media/bumpers/black_1s.mkv"
filler :pre_roll,  collection: "type:bumper AND tag:toonz_pre", mode: :shuffle
filler :post_roll, collection: "type:bumper AND tag:toonz_post", mode: :shuffle
filler :fallback,  collection: "type:bumper AND tag:toonz_fill", mode: :shuffle

layout :cartoon_block do
  pre_roll count: 1
  main
  slug     between_items: true, duration: 1.0
  post_roll count: 1
  fill     with: :fallback
  epg      granularity: :per_item, title: :from_main, category: "Children"
end

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

schedule do
  block at: "08:00", collection: :short_cartoons, layout: :saturday_bundle,
        count: 18, on: :weekends,
        epg: { title: "Saturday Morning Cartoons",
               description: "A rotating selection of classic animated shorts." }

  block at: "08:00", collection: :cartoon_reruns, layout: :cartoon_block,
        on: :weekdays

  block at: "11:00", collection: :cartoon_reruns, layout: :cartoon_block
  block at: "19:00", collection: :short_cartoons, layout: :cartoon_block

  default_block collection: :short_cartoons, layout: :cartoon_block
end
