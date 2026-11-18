"""The Omarchy skill: what this machine's Omarchy can do, as exact commands
(plan 12b).

Built from what is installed rather than written by hand, so it matches the
Omarchy version: `omarchy commands --json` lists every command with its
summary, arguments and examples (the `# omarchy:` headers each script
carries), and `hyprctl binds -j` lists the keybindings that have a
description. "Open a scratchpad terminal" is then one command the agent
already knows, not a search through /usr/share/omarchy/bin.

Two outputs:

- a Claude Code plugin folder holding `skills/omarchy/SKILL.md`, which the
  adapter loads with `--plugin-dir` for its own process only -- nothing is
  written into ~/.claude, so the user's own Claude sessions are untouched;
- a shorter text for backends that run commands here but load no skill
  (Codex, Gemini, Antigravity, Copilot), put in their instructions.

Run as a program: `omarchy_skill.py build` (install.sh does this) and
`omarchy_skill.py show`. The daemon rebuilds it when the Omarchy version
changes underneath it.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

#: Groups worth an agent's attention for getting things done at the desk.
#: Left out on purpose: installing and removing software, updates, packages,
#: hardware setup, boot, kernel, drives, security setup, migrations, dev
#: tooling, and the agent's own accounts -- each either needs a terminal and
#: a person, or is a change no spoken sentence should lead to by way of a
#: skill that made it look routine.
GROUPS = ("launch", "menu", "capture", "theme", "font", "toggle", "hyprland",
          "audio", "brightness", "notification", "clipboard", "system",
          "weather", "webapp", "screensaver", "bluetooth", "network",
          "battery", "powerprofiles", "display", "share", "show", "reminder",
          "osd", "dictation", "transcode", "tui")

#: Routes inside those groups that are still left out: they install,
#: remove, or reach the machine's boot or power configuration.
SKIP_WORDS = ("install", "remove", "reset", "setup", "hybrid gpu",
              "toggle suspend", "toggle enabled", "crash capture")

#: Hyprland actions the commands above do not cover, checked against
#: Omarchy's own bindings (default/hypr/bindings/tiling.lua). Two spellings:
#: Hyprland with a Lua config (Omarchy 4.5 on 0.56) reads `hyprctl
#: dispatch` as Lua and rejects the old form outright.
HYPR_ACTIONS_LUA = (
    ("Show or hide the scratchpad",
     """hyprctl dispatch 'hl.dsp.workspace.toggle_special("scratchpad")'"""),
    ("Move the focused window to the scratchpad",
     """hyprctl dispatch 'hl.dsp.window.move({ workspace = "special:scratchpad", follow = false })'"""),
    ("Go to workspace N", """hyprctl dispatch 'hl.dsp.focus({ workspace = "N" })'"""),
    ("List windows", "hyprctl -j clients"),
)
HYPR_ACTIONS_LEGACY = (
    ("Show or hide the scratchpad", "hyprctl dispatch togglespecialworkspace scratchpad"),
    ("Move the focused window to the scratchpad",
     "hyprctl dispatch movetoworkspacesilent special:scratchpad"),
    ("Go to workspace N", "hyprctl dispatch workspace N"),
    ("List windows", "hyprctl -j clients"),
)


def hypr_actions(config_dir: Path | None = None):
    """The spelling this machine's Hyprland reads."""
    base = config_dir or Path(os.environ.get("XDG_CONFIG_HOME")
                              or Path.home() / ".config") / "hypr"
    return HYPR_ACTIONS_LUA if (base / "hyprland.lua").is_file() else HYPR_ACTIONS_LEGACY


#: hyprctl's modmask bits, in the order Omarchy writes them.
_MODS = ((64, "SUPER"), (4, "CTRL"), (8, "ALT"), (1, "SHIFT"))

MAX_BINDS = 250

#: The short form goes into every turn's instructions, so it is kept short.
INSTRUCTIONS_MAX = 6000
INSTRUCTION_GROUPS = ("launch", "menu", "capture", "theme", "toggle",
                      "hyprland", "audio", "notification")


def skill_root() -> Path:
    from paths import DATA_DIR
    return DATA_DIR / "omarchy-skill"


def plugin_dir() -> str | None:
    """The plugin folder for --plugin-dir, or None when it has not been built."""
    root = skill_root()
    return str(root) if (root / "skills/omarchy/SKILL.md").is_file() else None


def _run_json(argv: list[str], timeout: float = 10.0):
    if not shutil.which(argv[0]):
        return None
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except ValueError:
        return None


def omarchy_version() -> str:
    tool = shutil.which("omarchy-version")
    if not tool:
        return ""
    try:
        return subprocess.run([tool], capture_output=True, text=True,
                              timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def commands(raw=None) -> list[dict]:
    """The commands worth knowing, from `omarchy commands --json`."""
    data = raw if raw is not None else _run_json(["omarchy", "commands", "--json"])
    items = data.get("commands") if isinstance(data, dict) else None
    out = []
    for c in items or []:
        if not isinstance(c, dict) or c.get("hidden") or c.get("requires_sudo"):
            continue
        route = str(c.get("route") or "")
        if c.get("group") not in GROUPS or not route.startswith("omarchy "):
            continue
        if any(w in route for w in SKIP_WORDS):
            continue
        examples = [e for e in (c.get("examples") or []) if isinstance(e, str)]
        out.append({"group": c["group"], "route": route,
                    "summary": " ".join(str(c.get("summary") or "").split()),
                    "args": " ".join(str(c.get("args") or "").split()),
                    "examples": examples[:3]})
    out.sort(key=lambda c: (GROUPS.index(c["group"]), c["route"]))
    return out


def keybindings(raw=None) -> list[tuple[str, str]]:
    """(keys, what it does) for every described binding."""
    data = raw if raw is not None else _run_json(["hyprctl", "binds", "-j"])
    out, seen = [], set()
    for b in data if isinstance(data, list) else []:
        if not isinstance(b, dict) or not b.get("has_description"):
            continue
        desc = " ".join(str(b.get("description") or "").split())
        key = str(b.get("key") or "")
        if not desc or not key or b.get("submap") or key.startswith("XF86"):
            # Media keys say what they do on the key itself.
            continue
        mods = [n for bit, n in _MODS if int(b.get("modmask") or 0) & bit]
        combo = " + ".join(mods + [key.upper() if len(key) == 1 else key])
        if (combo, desc) in seen:
            continue
        seen.add((combo, desc))
        out.append((combo, desc))
    return out[:MAX_BINDS]


GROUP_TITLES = {
    "launch": "Open apps and tools", "menu": "Menus and pickers",
    "capture": "Screenshots, recording, text from the screen",
    "theme": "Themes and backgrounds", "font": "Fonts",
    "toggle": "Toggles", "hyprland": "Windows and workspaces",
    "audio": "Sound", "brightness": "Brightness",
    "notification": "Notifications", "clipboard": "Clipboard",
    "system": "System", "weather": "Weather", "webapp": "Web apps",
}


def skill_markdown(cmds: list[dict], binds: list[tuple[str, str]],
                   version: str, actions=None) -> str:
    actions = actions if actions is not None else hypr_actions()
    lines = [
        "---",
        "name: omarchy",
        "description: Exact commands for this Omarchy desktop: open apps, menus, "
        "scratchpad, screenshots and screen recording, themes and backgrounds, "
        "fonts, toggles, sound, brightness, notifications, and what each "
        "keybinding does. Use when asked to do something on the desktop or how "
        "to do it with the keyboard.",
        "---",
        "",
        f"# Omarchy {version}".rstrip(),
        "",
        "Built from the commands installed on this machine. Run them with Bash. "
        "Prefer one of these to searching for a way: each is the supported route. "
        "The spoken answer should say what happened, not the command.",
        "",
        "## Quick actions",
        "",
    ]
    for what, cmd in actions:
        lines.append(f"- {what}: `{cmd}`")
    group = None
    for c in cmds:
        if c["group"] != group:
            group = c["group"]
            lines += ["", f"## {GROUP_TITLES.get(group, group.capitalize())}", ""]
        usage = c["route"] + (f" {c['args']}" if c["args"] else "")
        line = f"- `{usage}`: {c['summary']}"
        if c["examples"]:
            line += " e.g. " + ", ".join(f"`{e}`" for e in c["examples"][:2])
        lines.append(line)
    if binds:
        lines += ["", "## Keybindings", "",
                  "What each key combination does, for \"how do I…\" questions.", ""]
        lines += [f"- {combo}: {desc}" for combo, desc in binds]
    return "\n".join(lines) + "\n"


def instructions_text(cmds: list[dict], actions=None) -> str:
    """The short form, for a backend's instructions: routes and summaries."""
    head = ("This desktop runs Omarchy. For desktop actions use these commands "
            "(run with your shell tool) rather than searching for a way:")
    lines = [head]
    for what, cmd in (actions if actions is not None else hypr_actions())[:2]:
        lines.append(f"- {cmd} : {what.lower()}")
    size = sum(len(l) + 1 for l in lines)
    for c in cmds:
        if c["group"] not in INSTRUCTION_GROUPS:
            continue
        usage = c["route"] + (f" {c['args']}" if c["args"] else "")
        line = f"- {usage} : {c['summary']}"
        if size + len(line) + 1 > INSTRUCTIONS_MAX:
            break
        lines.append(line)
        size += len(line) + 1
    return "\n".join(lines)


def build(root: Path | None = None, *, cmds=None, binds=None,
          version: str | None = None) -> dict:
    """Write the plugin folder. Returns {"commands", "keybindings", "path"}.
    Leaves an existing skill in place when Omarchy cannot be asked."""
    root = root or skill_root()
    cmds = commands() if cmds is None else cmds
    binds = keybindings() if binds is None else binds
    version = omarchy_version() if version is None else version
    if not cmds:
        return {"commands": 0, "keybindings": 0, "path": str(root), "skipped": True}
    skill = root / "skills/omarchy"
    skill.mkdir(parents=True, exist_ok=True)
    manifest = root / ".claude-plugin/plugin.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    _write(manifest, json.dumps({
        "name": "agentvoice-omarchy",
        "version": "1.0.0",
        "description": "Omarchy desktop commands for Agent Voice's agents, built "
                       "from what is installed.",
    }, indent=2) + "\n")
    _write(skill / "SKILL.md", skill_markdown(cmds, binds, version))
    _write(root / "instructions.txt", instructions_text(cmds) + "\n")
    _write(root / "stamp", stamp(version))
    return {"commands": len(cmds), "keybindings": len(binds), "path": str(root)}


def _write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def stamp(version: str) -> str:
    """What the skill was built against: the Omarchy version and this file."""
    me = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12]
    return f"{version} {me}"


def stale(root: Path | None = None) -> bool:
    """True when the skill is missing or was built for another Omarchy."""
    root = root or skill_root()
    try:
        return (root / "stamp").read_text().strip() != stamp(omarchy_version())
    except OSError:
        return True


def instructions(root: Path | None = None) -> str:
    """The short form, as built, or "" when there is none."""
    try:
        return ((root or skill_root()) / "instructions.txt").read_text().strip()
    except OSError:
        return ""


def main(argv: list[str]) -> int:
    if argv[:1] == ["build"]:
        result = build()
        if result.get("skipped"):
            print("omarchy skill: omarchy commands --json gave nothing; kept as it was")
            return 0
        print(f"omarchy skill: {result['commands']} commands, "
              f"{result['keybindings']} keybindings -> {result['path']}")
        return 0
    if argv[:1] == ["show"]:
        path = skill_root() / "skills/omarchy/SKILL.md"
        try:
            print(path.read_text(), end="")
        except OSError:
            print("not built: run omarchy_skill.py build", file=sys.stderr)
            return 1
        return 0
    print("usage: omarchy_skill.py build|show", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
