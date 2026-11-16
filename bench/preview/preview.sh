#!/usr/bin/env bash
# Render one of the plugin's QML surfaces in a throwaway Quickshell, beside
# the live shell, and screenshot it with grim.
#
#   bench/preview/preview.sh [options] TARGET
#
# TARGET is a file in bench/preview/targets/ without the .qml: it becomes the
# throwaway shell's shell.qml, with Omarchy's Commons and Ui copied next to it
# (copies -- Quickshell does not resolve the singletons through a symlink) and
# this plugin's QML under plugin/.
#
# What it guards against, because the copy runs on the machine you are using:
#   - keyboard focus: every WlrKeyboardFocus.Exclusive in the copies becomes
#     None, so a preview never takes the keyboard from whoever is typing;
#   - settings: `omarchy` on PATH is a stub that logs `omarchy bar set ...` to
#     <out>.writes instead of writing shell.json, so clicking around a preview
#     changes nothing real. Everything else passes through to the real one.
#
# Options:
#   --theme NAME   a theme from /usr/share/omarchy/themes (default: current)
#   --out PATH     screenshot path; with --shots N, PATH-1.png ... PATH-N.png
#   --size WxH    crop to a box that size in the middle of the screen
#   --wait S       seconds before the first shot (default 3)
#   --shots N      how many screenshots (default 1)
#   --gap S        seconds between shots (default 1.5)
#   --arg STRING   handed to the target as PREVIEW_ARG
#   --keep         leave it running until Ctrl+C instead of exiting after the
#                  last shot (for poking at it by hand)
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
shell_src="${OMARCHY_PATH:-/usr/share/omarchy}/shell"
themes="${OMARCHY_PATH:-/usr/share/omarchy}/themes"

theme="" out="" size="" wait=3 shots=1 gap=1.5 arg="" keep=0
while [ $# -gt 0 ]; do
  case "$1" in
    --theme) theme=$2; shift 2 ;;
    --out) out=$2; shift 2 ;;
    --size) size=$2; shift 2 ;;
    --wait) wait=$2; shift 2 ;;
    --shots) shots=$2; shift 2 ;;
    --gap) gap=$2; shift 2 ;;
    --arg) arg=$2; shift 2 ;;
    --keep) keep=1; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *) break ;;
  esac
done
target=${1:-}
if [ -z "$target" ] || [ ! -f "$here/targets/$target.qml" ]; then
  echo "usage: $0 [options] TARGET   (one of: $(cd "$here/targets" && ls *.qml | sed 's/\.qml$//' | tr '\n' ' '))" >&2
  exit 2
fi
[ -n "$out" ] || out="${TMPDIR:-/tmp}/agentvoice-preview-$target"
out=${out%.png}

tmp=$(mktemp -d "${TMPDIR:-/tmp}/agentvoice-preview.XXXXXX")
pid=""
cleanup() {
  [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  rm -rf "$tmp"
}
trap cleanup EXIT INT TERM

cp -r "$shell_src/Commons" "$shell_src/Ui" "$tmp/"
mkdir -p "$tmp/plugin" "$tmp/bin"
cp "$repo"/*.qml "$tmp/plugin/"
[ -d "$repo/ui" ] && cp -r "$repo/ui" "$tmp/plugin/ui"
# Under qs -p a directory without a qmldir does not see its own siblings as
# types ("KnobRow is not a type" from inside Settings.qml), so give it one.
for f in "$tmp"/plugin/*.qml; do
  n=$(basename "$f" .qml); echo "$n 1.0 $n.qml"
done > "$tmp/plugin/qmldir"
sed -i 's/WlrKeyboardFocus\.Exclusive/WlrKeyboardFocus.None/g' \
  $(find "$tmp/plugin" "$tmp/Ui" -name '*.qml')
cp "$here/targets/$target.qml" "$tmp/shell.qml"
# Helpers the targets share (anything in targets/ starting with a capital).
for f in "$here"/targets/[A-Z]*.qml; do cp "$f" "$tmp/"; done

if [ -n "$theme" ]; then
  [ -d "$themes/$theme" ] || { echo "no theme: $themes/$theme" >&2; exit 2; }
  mkdir -p "$tmp/state/omarchy/current"
  ln -s "$themes/$theme" "$tmp/state/omarchy/current/theme"
  # Color.qml builds the theme path from $HOME rather than XDG_STATE_HOME.
  sed -i "s|home + \"/.local/state\"|\"$tmp/state\"|" "$tmp/Commons/Color.qml"
fi

real_omarchy=$(command -v omarchy || true)
: > "$out.writes"
cat > "$tmp/bin/omarchy" <<EOF
#!/usr/bin/env bash
if [ "\${1:-}" = bar ] && [ "\${2:-}" = set ]; then
  # PREVIEW_SET_DELAY: seconds a write takes, to imitate the real one.
  sleep "\${PREVIEW_SET_DELAY:-0}"
  printf '%s\n' "\$*" >> '$out.writes'
  exit 0
fi
exec ${real_omarchy:-false} "\$@"
EOF
chmod +x "$tmp/bin/omarchy"

PATH="$tmp/bin:$PATH" PREVIEW_ARG="$arg" PREVIEW_WRITES="$out.writes" \
  PREVIEW_WAIT="$wait" PREVIEW_GAP="$gap" \
  qs -p "$tmp" > "$out.log" 2>&1 &
pid=$!

sleep "$wait"
if ! kill -0 "$pid" 2>/dev/null; then
  echo "quickshell exited early; log follows" >&2
  cat "$out.log" >&2
  exit 1
fi

# --size WxH crops to that box in the middle of the focused monitor, which is
# where the overlays centre themselves.
region=()
if [ -n "$size" ]; then
  read -r mx my mw mh < <(hyprctl monitors -j | jq -r \
    '.[] | select(.focused) | "\(.x) \(.y) \((.width / .scale) | floor) \((.height / .scale) | floor)"')
  w=${size%x*} h=${size#*x}
  [ "$w" -gt "$mw" ] && w=$mw
  [ "$h" -gt "$mh" ] && h=$mh
  region=(-g "$((mx + (mw - w) / 2)),$((my + (mh - h) / 2)) ${w}x${h}")
fi

if [ "$shots" -eq 1 ]; then
  grim "${region[@]}" "$out.png"
  echo "$out.png"
else
  for i in $(seq 1 "$shots"); do
    grim "${region[@]}" "$out-$i.png"
    echo "$out-$i.png"
    [ "$i" -lt "$shots" ] && sleep "$gap"
  done
fi

if [ "$keep" -eq 1 ]; then
  echo "running; Ctrl+C to stop (log: $out.log, writes: $out.writes)" >&2
  wait "$pid"
fi
