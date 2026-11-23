"""Which keys run Agent Voice, read live (master plan M26: Other settings →
Keys). Read only: the bindings are the user's, in a file Omarchy owns, and
changing them from the settings is deferred on purpose (plan section 9).

Two sources, because neither is enough alone:

- **`bindings.lua`** (`$XDG_CONFIG_HOME/hypr/bindings.lua`) says what each
  key *runs*. On Omarchy 4.5 every binding is a Lua callback, and `hyprctl
  binds -j` reports one as dispatcher `__lua` with a callback number for its
  argument: the command line is not in it. So the file is the only place
  that says "F8 runs `agentvoice talk`". Every `o.bind(...)` whose command
  starts with `agentvoice` counts, inside install.sh's markers or not.
- **`hyprctl binds -j`** says what Hyprland has *loaded*. A line in the file
  that Hyprland rejected, or one not reloaded yet, is not a key that works,
  and the page says so rather than listing it as live. A binding written the
  older way (`exec, agentvoice ...`) is found here directly, by its argument.

Nothing here runs a command from either source; hyprctl is asked with a
timeout and a failure is an answer ("could not ask Hyprland"), never a crash.

    keybinds.py [--json]
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

#: Hyprland's modifier bits, in the order a person writes them.
MODS = (("SUPER", 64), ("CTRL", 4), ("ALT", 8), ("SHIFT", 1))
_ALIASES = {"CONTROL": "CTRL", "WIN": "SUPER", "LOGO": "SUPER", "MOD4": "SUPER",
            "META": "SUPER", "MOD1": "ALT"}

#: What each verb does, in the page's words. A verb not here is shown as the
#: command itself ("agentvoice open-mic on"), which is still true.
VERBS = {
    "talk": "Talk without the wake word; while it replies, stop it.",
    "talk-end": "End the turn you are holding the key for.",
    "interrupt": "Stop the reply, and keep listening.",
    "mic": "Release the microphone entirely, or take it back.",
    "toggle": "Start or stop the service.",
    "start": "Start the service.",
    "stop": "Stop the service.",
    "hud-preview": "Show the readout with sample text.",
    "lock": "Tell it the screen is locking.",
    "unlock": "Tell it the screen is unlocked.",
}

#: One `o.bind("KEYS", "description", "command", { opts })` per line, as
#: install.sh writes them and Omarchy's own bindings.lua does. Strings only:
#: a binding built from Lua expressions is not one this can read, and it is
#: left out rather than guessed at.
_BIND = re.compile(r'^\s*o\.bind\(\s*"((?:[^"\\]|\\.)*)"\s*,\s*"((?:[^"\\]|\\.)*)"\s*,'
                   r'\s*"((?:[^"\\]|\\.)*)"\s*(?:,(.*))?\)\s*$')
_COMMAND = re.compile(r"^agentvoice(?:\s+([a-z][a-z-]{0,30}))?(?:\s.*)?$")
MAX_FILE_BYTES = 512 * 1024


def bindings_file() -> Path:
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return config / "hypr" / "bindings.lua"


def _mods_and_key(keys: str) -> tuple[int, str]:
    """`"SUPER + CTRL + SPACE"` -> (68, "SPACE")."""
    parts = [p.strip().upper() for p in keys.replace(",", "+").split("+") if p.strip()]
    if not parts:
        return 0, ""
    mask = 0
    for p in parts[:-1]:
        p = _ALIASES.get(p, p)
        mask |= dict(MODS).get(p, 0)
    return mask, parts[-1]


def pretty(mask: int, key: str) -> str:
    """(68, "SPACE") -> "Super+Ctrl+Space"."""
    names = [n.capitalize() for n, bit in MODS if mask & bit]
    k = str(key or "")
    if len(k) <= 1 or re.fullmatch(r"[Ff]\d{1,2}", k):
        k = k.upper()
    elif k.isalpha():
        k = k.capitalize()
    return "+".join(names + [k])


def from_file(text: str) -> list[dict]:
    """Every binding in a bindings.lua that runs `agentvoice`."""
    out = []
    for line in text.splitlines():
        m = _BIND.match(line)
        if not m:
            continue
        keys, desc, command, opts = m.group(1), m.group(2), m.group(3).strip(), m.group(4) or ""
        c = _COMMAND.match(command)
        if not c:
            continue
        mask, key = _mods_and_key(keys)
        out.append({"mods": mask, "key": key, "description": desc[:120],
                    "command": command[:120], "verb": c.group(1) or "",
                    "release": bool(re.search(r"\brelease\s*=\s*true\b", opts))})
    return out


def _loaded(binds) -> list[dict]:
    """hyprctl's list, as the few fields compared here."""
    out = []
    for b in binds if isinstance(binds, list) else []:
        if not isinstance(b, dict):
            continue
        try:
            mask = int(b.get("modmask") or 0)
        except (TypeError, ValueError):
            mask = 0
        out.append({"mods": mask, "key": str(b.get("key") or "").upper(),
                    "description": str(b.get("description") or "") if b.get("has_description") else "",
                    "dispatcher": str(b.get("dispatcher") or ""), "arg": str(b.get("arg") or ""),
                    "release": bool(b.get("release"))})
    return out


def merge(file_binds: list[dict], loaded, hyprland_ok: bool) -> list[dict]:
    """One row per key, with whether Hyprland has it loaded.

    A file binding counts as loaded when Hyprland has a binding on the same
    keys, press or release alike, with the same description: on Omarchy 4.5
    that is all hyprctl can say about a Lua binding. A press and a release of
    `talk` / `talk-end` on one key are one row, "Hold F8"."""
    live = _loaded(loaded)
    rows = []
    for b in file_binds:
        if hyprland_ok:
            ok = any(x["mods"] == b["mods"] and x["key"] == b["key"].upper()
                     and x["release"] == b["release"]
                     and (x["description"] == b["description"]
                          or (x["dispatcher"] == "exec" and x["arg"].strip() == b["command"]))
                     for x in live)
        else:
            ok = None
        rows.append({**b, "loaded": ok, "source": "file"})
    # Older configs (`bind = SUPER, X, exec, agentvoice mic`) are visible
    # to hyprctl by their argument, and in no Lua line.
    for x in live:
        c = _COMMAND.match(x["arg"].strip()) if x["dispatcher"] == "exec" else None
        if not c:
            continue
        if any(r["mods"] == x["mods"] and r["key"].upper() == x["key"]
               and r["command"] == x["arg"].strip() for r in rows):
            continue
        rows.append({"mods": x["mods"], "key": x["key"], "description": x["description"][:120],
                     "command": x["arg"].strip()[:120], "verb": c.group(1) or "",
                     "release": x["release"], "loaded": True, "source": "hyprland"})
    # Hold-to-talk: the press and the release on one key, as one row.
    out, used = [], set()
    for i, r in enumerate(rows):
        if i in used:
            continue
        if r["verb"] == "talk" and not r["release"]:
            for j, s in enumerate(rows):
                if (j not in used and j != i and s["verb"] == "talk-end" and s["release"]
                        and s["mods"] == r["mods"] and s["key"].upper() == r["key"].upper()):
                    used.add(j)
                    both = None if r["loaded"] is None or s["loaded"] is None \
                        else bool(r["loaded"] and s["loaded"])
                    out.append({**r, "hold": True, "loaded": both})
                    break
            else:
                out.append({**r, "hold": False})
        else:
            out.append({**r, "hold": False})
        used.add(i)
    for r in out:
        keys = pretty(r["mods"], r["key"])
        r["keys"] = ("Hold " + keys) if r["hold"] else (keys + " (release)" if r["release"] else keys)
        r["what"] = ("Talk without the wake word; release when done. While it replies, "
                     "a press stops it." if r["hold"] else VERBS.get(r["verb"], r["command"]))
    return out


def ask_hyprland(timeout: float = 3.0):
    """hyprctl's binds, or None when it cannot be asked."""
    try:
        p = subprocess.run(["hyprctl", "binds", "-j"], capture_output=True, text=True,
                           timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    try:
        data = json.loads(p.stdout)
    except ValueError:
        return None
    return data if isinstance(data, list) else None


def read_file(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(errors="replace")
    except OSError:
        return None


def view(path: Path | None = None, hypr=ask_hyprland) -> dict:
    path = bindings_file() if path is None else path
    text = read_file(path)
    loaded = hypr()
    rows = merge(from_file(text or ""), loaded, loaded is not None)
    home = str(Path.home())
    shown = str(path)
    if shown == home or shown.startswith(home + "/"):
        shown = "~" + shown[len(home):]
    return {"file": str(path), "file_shown": shown, "file_found": text is not None,
            "hyprland": loaded is not None, "rows": rows}


def text_view(v: dict) -> str:
    lines = []
    if not v["rows"]:
        lines.append("No key runs an Agent Voice command.")
    for r in v["rows"]:
        state = "" if r["loaded"] else ("  (not loaded by Hyprland)" if r["loaded"] is False
                                        else "  (Hyprland not asked)")
        lines.append(f"{r['keys']:<24} {r['what']}{state}")
    lines.append(f"from {v['file_shown']}" + ("" if v["file_found"] else " (not found)"))
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    v = view()
    if "--json" in argv:
        print(json.dumps(v))
    else:
        print(text_view(v))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
