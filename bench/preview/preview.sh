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
#     changes nothing real. Everything else passes through to the real one;
#   - agent folders: `agentvoice agents ...` runs this checkout's agentfs.py
#     with XDG_DATA_HOME in the scratch directory, so an instructions box
#     saved in a preview writes nothing any real agent reads. A target finds
#     that folder in PREVIEW_DATA, and an export lands in the scratch
#     directory, never in ~/Downloads.
#
# Options:
#   --theme NAME   a theme from /usr/share/omarchy/themes (default: current)
#   --out PATH     screenshot path; with --shots N, PATH-1.png ... PATH-N.png
#   --size WxH    crop to a box that size in the middle of the screen
#   --wait S       seconds before the first shot (default 3)
#   --shots N      how many screenshots (default 1)
#   --gap S        seconds between shots (default 1.5)
#   --arg STRING   handed to the target as PREVIEW_ARG
#   --state FILE   show the daemon as running with this state file: it is
#                  copied into a scratch runtime directory, and `agentvoice`
#                  on PATH becomes a stub that answers is-active with yes and
#                  does nothing else, so no real service is started or
#                  stopped. For screenshots of states the machine is not in.
#   --live-config  give it a scratch copy of shell.json (XDG_CONFIG_HOME points
#                  at it) and make the stub *apply* each `bar set` there with
#                  jq, so a write comes back through the store's reload the
#                  way it does on the real shell. The round trip is where
#                  rebuild bugs live (a card shutting on every save); the
#                  real shell.json is still never touched.
#   --scratch-data the overlay reads a scratch data folder (saved chats,
#                  agent folders) seeded by targets/TARGET.seed.py when there
#                  is one, so a screenshot holds no real conversation
#   --keep         leave it running until Ctrl+C instead of exiting after the
#                  last shot (for poking at it by hand)
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
shell_src="${OMARCHY_PATH:-/usr/share/omarchy}/shell"
themes="${OMARCHY_PATH:-/usr/share/omarchy}/themes"

theme="" out="" size="" wait=3 shots=1 gap=1.5 arg="" keep=0 state="" live=0 scratch=0
while [ $# -gt 0 ]; do
  case "$1" in
    --theme) theme=$2; shift 2 ;;
    --out) out=$2; shift 2 ;;
    --size) size=$2; shift 2 ;;
    --wait) wait=$2; shift 2 ;;
    --shots) shots=$2; shift 2 ;;
    --gap) gap=$2; shift 2 ;;
    --arg) arg=$2; shift 2 ;;
    --state) state=$(realpath "$2"); shift 2 ;;
    --keep) keep=1; shift ;;
    --live-config) live=1; shift ;;
    --scratch-data) scratch=1; shift ;;
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
cp "$repo/manifest.json" "$tmp/plugin/"
[ -d "$repo/ui" ] && cp -r "$repo/ui" "$tmp/plugin/ui"
[ -d "$repo/pages" ] && cp -r "$repo/pages" "$tmp/plugin/pages"
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
config_env=()
apply=""
if [ "$live" -eq 1 ]; then
  real_cfg="${XDG_CONFIG_HOME:-$HOME/.config}"
  mkdir -p "$tmp/config/omarchy"
  # Everything else under ~/.config/omarchy is read-only to a preview, so
  # linked; shell.json is the one file it writes, so copied.
  for f in "$real_cfg"/omarchy/*; do
    [ "$(basename "$f")" = shell.json ] || ln -s "$f" "$tmp/config/omarchy/"
  done
  cp "$real_cfg/omarchy/shell.json" "$tmp/config/omarchy/shell.json"
  cp "$tmp/config/omarchy/shell.json" "$out.shell.json.before"
  config_env=(XDG_CONFIG_HOME="$tmp/config")
  # `omarchy bar set ID KEY VALUE --json`: VALUE is JSON.
  apply="f='$tmp/config/omarchy/shell.json'
  jq --arg id \"\$3\" --arg k \"\$4\" --argjson v \"\$5\" \\
    '(.bar.layout[]?[]? | select(.id==\$id))[\$k] = \$v' \"\$f\" > \"\$f.new\" && mv \"\$f.new\" \"\$f\""
fi
cat > "$tmp/bin/omarchy" <<EOF
#!/usr/bin/env bash
if [ "\${1:-}" = bar ] && [ "\${2:-}" = set ]; then
  # PREVIEW_SET_DELAY: seconds a write takes, to imitate the real one.
  sleep "\${PREVIEW_SET_DELAY:-0}"
  printf '%s\n' "\$*" >> '$out.writes'
  $apply
  exit 0
fi
exec ${real_omarchy:-false} "\$@"
EOF
chmod +x "$tmp/bin/omarchy"

runtime_env=()
if [ -n "$state" ]; then
  mkdir -p "$tmp/run/agentvoice"
  chmod 700 "$tmp/run"
  cp "$state" "$tmp/run/agentvoice/state"
  # Quickshell then cannot find Hyprland's socket and says so once; the
  # surfaces previewed here do not use it.
  printf '#!/usr/bin/env bash\n[ "${1:-}" = is-active ] && echo yes\nexit 0\n' > "$tmp/bin/agentvoice.rest"
  chmod +x "$tmp/bin/agentvoice.rest"
  # The Wayland socket lives in the real runtime directory, so it is named
  # by its full path once XDG_RUNTIME_DIR points elsewhere.
  runtime_env=(XDG_RUNTIME_DIR="$tmp/run"
               WAYLAND_DISPLAY="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/${WAYLAND_DISPLAY:-wayland-0}")
fi

# `agentvoice agents ...` writes the agent folders, which hold what every
# agent is told (merged plan, Phase 10). In a preview it always runs this
# checkout's agentfs.py against a scratch data folder, whatever the mode, so
# saving an instructions box in a preview never reaches a real agent. The
# rest goes to the stub above (--state) or to the real command.
mkdir -p "$tmp/data"
real_agentvoice=$(command -v agentvoice || true)
if [ ! -x "$tmp/bin/agentvoice.rest" ]; then
  printf '#!/usr/bin/env bash\nexec %q "$@"\n' "${real_agentvoice:-false}" > "$tmp/bin/agentvoice.rest"
  chmod +x "$tmp/bin/agentvoice.rest"
fi
# Starting, stopping or toggling the real service, typing to a real agent or
# answering its permission question is never what a preview means, and since
# Phase 10 a start also migrates the real agent folders: those are logged and
# do nothing, in every mode.
cat > "$tmp/bin/agentvoice" <<STUB
#!/usr/bin/env bash
case "\${1:-}" in
  agents)
    # PREVIEW_AGENTS_DELAY: seconds each call takes, to draw "Reading…".
    sleep "\${PREVIEW_AGENTS_DELAY:-0}"
    # An export with no folder named would land in the real ~/Downloads.
    if [ "\${2:-}" = export ] && [ \$# -eq 3 ]; then
      mkdir -p '$tmp/exports'; set -- "\$@" '$tmp/exports'
    fi
    XDG_DATA_HOME='$tmp/data' exec '$repo/bin/agentvoice' "\$@" ;;
  chats)
    # Saved chats: from the scratch data folder under --scratch-data, so
    # sharing a chat in a preview touches no real one; else as before.
    if [ '$scratch' = 1 ]; then XDG_DATA_HOME='$tmp/data' exec '$repo/bin/agentvoice' "\$@"; fi ;;
  start|stop|restart|toggle|enable|disable|mic|open-mic|interrupt|lock|unlock|type|talk|talk-end|permit|wake-test|calibrate|pass|tasks)
    printf 'agentvoice %s\n' "\$*" >> '$out.writes'; exit 0 ;;
esac
exec '$tmp/bin/agentvoice.rest' "\$@"
STUB
chmod +x "$tmp/bin/agentvoice"

# --scratch-data: the overlay reads the scratch data folder too (saved
# chats, agent folders), so a screenshot holds no real conversation. A
# target's own synthetic content, targets/TARGET.seed.py, is written there
# first.
data_env=()
if [ "$scratch" -eq 1 ]; then
  data_env=(XDG_DATA_HOME="$tmp/data")
  if [ -f "$here/targets/$target.seed.py" ]; then
    PREVIEW_DATA="$tmp/data/agentvoice" python3 "$here/targets/$target.seed.py" "$repo/daemon"
  fi
fi

env "${runtime_env[@]}" "${config_env[@]}" "${data_env[@]+"${data_env[@]}"}" \
PATH="$tmp/bin:$PATH" PREVIEW_ARG="$arg" PREVIEW_WRITES="$out.writes" \
  PREVIEW_DATA="$tmp/data/agentvoice" PREVIEW_AGENTS_DELAY="${PREVIEW_AGENTS_DELAY:-0}" \
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

[ "$live" -eq 1 ] && cp "$tmp/config/omarchy/shell.json" "$out.shell.json.after"

if [ "$keep" -eq 1 ]; then
  echo "running; Ctrl+C to stop (log: $out.log, writes: $out.writes)" >&2
  wait "$pid"
fi
