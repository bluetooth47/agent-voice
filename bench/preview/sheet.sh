#!/usr/bin/env bash
# The whole preview set as contact sheets (master plan M29): every page and
# tab, wide and narrow, dark and light, an empty install and eight agents.
#
#   bench/preview/sheet.sh [--out DIR] [--themes "DARK LIGHT"] [--only REGEX]
#
# Each page is shot a screenful at a time (the settings target's Scroller)
# and the shots for one variant are tiled into DIR/sheet-<state>-<size>-<theme>.png
# with each page's name under its tiles. Every run uses a synthetic config,
# a scratch data folder and a stub service, so nothing real is drawn and
# nothing real is written; each run's write log is checked to be empty.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
out=/tmp/agentvoice-sheet themes="current flexoki-light" only=""
while [ $# -gt 0 ]; do
  case "$1" in
    --out) out=$2; shift 2 ;;
    --themes) themes=$2; shift 2 ;;
    --only) only=$2; shift 2 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
mkdir -p "$out/shots"

# name|payload|shots. Every page in sidebar order, then each tab.
pages=(
  'overview|{"page":"overview"}|3'
  'agents|{"page":"agents"}|4'
  'details-prompt|{"page":"agentdetails","agent":"main","tab":"prompt"}|3'
  'details-tools|{"page":"agentdetails","agent":"main","tab":"tools"}|3'
  'details-notes|{"page":"agentdetails","agent":"main","tab":"notes"}|2'
  'details-chats|{"page":"agentdetails","agent":"main","tab":"chats"}|2'
  'details-advanced|{"page":"agentdetails","agent":"main","tab":"advanced"}|3'
  'communal-rules|{"page":"communal","tab":"rules"}|2'
  'communal-who|{"page":"communal","tab":"who"}|2'
  'communal-preview|{"page":"communal","tab":"preview"}|2'
  'communal-tools|{"page":"communal","tab":"tools"}|2'
  'communal-skills|{"page":"communal","tab":"skills"}|2'
  'communal-notes|{"page":"communal","tab":"notes"}|2'
  'communal-chats|{"page":"communal","tab":"chats"}|2'
  'crew|{"page":"crew"}|3'
  'chats|{"page":"chats"}|2'
  'listening|{"page":"listening"}|4'
  'conversation|{"page":"conversation"}|5'
  'voice|{"page":"voice"}|3'
  'other|{"page":"other"}|4'
  'about|{"page":"about"}|3'
)

bad=0
for state in empty eight; do
  case $state in
    empty) cfg=$repo/bench/preview/configs/fresh.json; svc=(--service-off) ;;
    eight) cfg=$repo/bench/preview/configs/agents8.json; svc=(--state "$repo/bench/preview/states/showcase.json") ;;
  esac
  for size in wide narrow; do
    for theme in $themes; do
      tag=$state-$size-$theme
      [ -n "$only" ] && ! [[ $tag =~ $only ]] && continue
      themearg=(); [ "$theme" = current ] || themearg=(--theme "$theme")
      tiles=()
      for spec in "${pages[@]}"; do
        IFS='|' read -r name payload n <<<"$spec"
        if [ $size = narrow ]; then payload=${payload%\}},\"narrow\":true}; crop=640x760; else crop=1100x760; fi
        shot=$out/shots/$tag-$name
        "$here/preview.sh" --config "$cfg" "${svc[@]}" "${themearg[@]}" --scratch-data \
          --size "$crop" --wait 5 --shots "$n" --gap 1.6 --arg "$payload" --out "$shot" settings \
          >/dev/null 2>&1 || { echo "FAIL $tag $name" >&2; bad=1; continue; }
        if [ -s "$shot.writes" ]; then echo "WROTE $tag $name: $(head -c 200 "$shot.writes")" >&2; bad=1; fi
        for i in $(seq 1 "$n"); do
          [ -f "$shot-$i.png" ] && tiles+=(-label "$name $i" "$shot-$i.png")
        done
      done
      [ ${#tiles[@]} -gt 0 ] || continue
      montage "${tiles[@]}" -tile 6x -geometry +6+6 -resize 50% -pointsize 14 \
        -background '#222' -fill '#ddd' "$out/sheet-$tag.png"
      echo "$out/sheet-$tag.png"
    done
  done
done
exit $bad
