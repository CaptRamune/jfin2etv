# Channel 01 — Classic Rock Videos (DESIGN.md §18.1)
# A 24/7 music-video channel. One collection, shuffle, minimal layout.

channel number: "01", name: "Classic Rock Videos", tuning: "01.1",
        icon: "/media/logos/classicrock.png"

collection :rock_videos,
  "type:music_video AND (genre:Rock OR genre:\"Classic Rock\")",
  mode: :shuffle

filler :slug,     local: "/media/bumpers/black_1s.mkv"
filler :pre_roll, collection: "type:bumper AND tag:classicrock_pre", mode: :shuffle
filler :fallback, collection: "type:bumper AND tag:classicrock_fill", mode: :shuffle

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

schedule do
  block at: "00:00", collection: :rock_videos, layout: :video_block
  default_block collection: :rock_videos, layout: :video_block
end
