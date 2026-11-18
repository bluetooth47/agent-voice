#!/usr/bin/env python3
"""Desktop tools for a voice agent: an MCP server on stdio (plan 12a).

Claude Code starts this through `--mcp-config` when `desktopTools` is on.
It speaks MCP's JSON-RPC by hand, with the standard library only, because it
starts with every agent process and the daemon's venv is not the place to
grow a dependency for forty lines of protocol.

argv is `desktop_mcp.py <program> [<agent id>]`, the same convention as
permission_hook.py, so a question this asks is filed as that agent's.

What it can do, and who decides:

- **read-only** (`list_windows`, `active_window`, `list_workspaces`): the
  permission hook allows these at every level, like Read.
- **changes** (open an app, focus, move or close a window, switch workspace,
  open a project layout, media, volume, a notification, write the
  clipboard): asked about by the hook below "trusted", like any other tool.
- **the clipboard's contents** (`clipboard_read`): asked below "trusted",
  like a read of a credential, because a clipboard often holds a password.
- **a screenshot**: asked about every time, at every level and whatever
  "allow all in this chat" says, by this server itself -- so it holds even
  for a trusted agent that has no hook at all.
- **lock and suspend**: refused unless the request heard in this turn says
  so ("lock the screen", "suspend", "go to sleep"). A sentence from a video
  cannot become a locked machine by way of a confused agent.

Nothing here takes a command line. `open_app` launches a desktop entry by
name, never an arbitrary program: an agent that wants to run something
already has Bash, and Bash goes through the hook.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

SERVER = "agentvoice-desktop"
VERSION = "0.1"
#: Protocol versions this speaks; the newest is offered when the client asks
#: for one this does not know.
PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")

#: How long a desktop command may take before it is abandoned.
CMD_TIMEOUT_S = 10
#: The most of the clipboard handed back.
CLIPBOARD_MAX = 20_000

#: Words in this turn's request that allow lock and suspend.
_LOCK_WORDS = re.compile(r"\b(lock|locked)\b", re.I)
_SUSPEND_WORDS = re.compile(r"\b(suspend|sleep|hibernate)\b", re.I)


def _tool(name, description, properties=None, required=(), read_only=False):
    return {"name": name, "description": description,
            "inputSchema": {"type": "object", "properties": properties or {},
                            "required": list(required),
                            "additionalProperties": False},
            "annotations": {"readOnlyHint": read_only}}


_WS = {"type": "integer", "minimum": 1, "maximum": 99,
       "description": "Workspace number"}
_ADDR = {"type": "string", "pattern": "^0x[0-9a-fA-F]{1,16}$",
         "description": "Window address from list_windows, like 0x55d0c1a0"}

TOOLS = [
    _tool("list_windows", "List open windows: address, app class, title, "
          "workspace, and whether it is focused.", read_only=True),
    _tool("active_window", "The focused window.", read_only=True),
    _tool("list_workspaces", "Workspaces in use and how many windows each has.",
          read_only=True),
    _tool("open_app", "Open an installed app by its name as the launcher "
          "shows it (Firefox, Files, Spotify). Desktop apps only, not commands.",
          {"name": {"type": "string", "maxLength": 80}}, ["name"]),
    _tool("focus_window", "Focus a window.", {"address": _ADDR}, ["address"]),
    _tool("move_window", "Move a window to a workspace without following it.",
          {"address": _ADDR, "workspace": _WS}, ["address", "workspace"]),
    _tool("close_window", "Close a window, as its close button would.",
          {"address": _ADDR}, ["address"]),
    _tool("switch_workspace", "Show a workspace.", {"workspace": _WS}, ["workspace"]),
    _tool("open_project_layout", "Open a project to work on: a terminal and "
          "the editor in its folder, and optionally the browser at a URL.",
          {"folder": {"type": "string", "maxLength": 1024},
           "terminal": {"type": "boolean", "default": True},
           "editor": {"type": "boolean", "default": True},
           "url": {"type": "string", "maxLength": 2048,
                   "description": "http(s) URL to open in the browser"}},
          ["folder"]),
    _tool("open_in_editor", "Open a file in the person's editor, at a line "
          "and column when given.",
          {"path": {"type": "string", "maxLength": 4096},
           "line": {"type": "integer", "minimum": 1},
           "column": {"type": "integer", "minimum": 1}}, ["path"]),
    _tool("show_changes", "Open a side-by-side diff in the editor of what has "
          "changed in a git folder since the last commit: one file, or up to "
          "five.",
          {"folder": {"type": "string", "maxLength": 4096},
           "path": {"type": "string", "maxLength": 4096,
                    "description": "One file inside the folder; all changed "
                                   "files when left out"}},
          ["folder"]),
    _tool("media", "Control what is playing: play-pause, play, pause, next, "
          "previous, stop.",
          {"action": {"type": "string",
                      "enum": ["play-pause", "play", "pause", "next",
                               "previous", "stop"]}}, ["action"]),
    _tool("volume", "Change the output volume: raise, lower, mute-toggle, "
          "or set a percentage.",
          {"action": {"type": "string", "enum": ["raise", "lower", "mute-toggle", "set"]},
           "percent": {"type": "integer", "minimum": 0, "maximum": 100}},
          ["action"]),
    _tool("notify", "Show a desktop notification.",
          {"title": {"type": "string", "maxLength": 200},
           "body": {"type": "string", "maxLength": 2000}}, ["title"]),
    _tool("clipboard_read", "Read the text on the clipboard.", read_only=True),
    _tool("clipboard_write", "Put text on the clipboard.",
          {"text": {"type": "string", "maxLength": 100_000}}, ["text"]),
    _tool("screenshot", "See the screen. Asked about every time.",
          {"scale": {"type": "number", "minimum": 0.25, "maximum": 1,
                     "default": 0.5}}, read_only=True),
    _tool("lock_screen", "Lock the screen. Only when the person asked for it "
          "in this request."),
    _tool("suspend", "Suspend the machine. Only when the person asked for it "
          "in this request."),
]

#: Read-only tools the permission hook lets through at every level.
READ_ONLY = frozenset({"list_windows", "active_window", "list_workspaces"})
#: Asked below "trusted", like a credential read.
SENSITIVE_READ = frozenset({"clipboard_read"})
#: Asked by this server itself, every time; the hook lets them through.
SELF_ASKED = frozenset({"screenshot"})


class ToolError(Exception):
    """A refusal or failure to report to the agent as a tool error."""


# --- running things --------------------------------------------------------

def _run(argv, *, input_text=None, timeout=CMD_TIMEOUT_S) -> str:
    if not shutil.which(argv[0]):
        raise ToolError(f"{argv[0]} is not installed")
    try:
        out = subprocess.run(argv, input=input_text, capture_output=True,
                             text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ToolError(f"{argv[0]} did not finish in {timeout}s")
    if out.returncode != 0:
        raise ToolError((out.stderr or out.stdout).strip()[:300]
                        or f"{argv[0]} failed")
    return out.stdout


def _copy(text: str) -> None:
    """Put text on the clipboard with wl-copy.

    Not through _run: wl-copy forks a process that holds the selection until
    something else is copied, and that process keeps whatever stdout and
    stderr it was given. Captured, those pipes never close, so the call
    waited out its whole timeout and reported a failure for a copy that had
    worked (found on the real desktop; the stub did not fork).
    """
    if not shutil.which("wl-copy"):
        raise ToolError("wl-copy is not installed")
    try:
        out = subprocess.run(["wl-copy"], input=text, text=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             timeout=CMD_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise ToolError(f"wl-copy did not finish in {CMD_TIMEOUT_S}s")
    if out.returncode != 0:
        raise ToolError("wl-copy failed")


def _spawn(argv) -> None:
    """Start something that outlives this call, detached from the agent."""
    if not shutil.which(argv[0]):
        raise ToolError(f"{argv[0]} is not installed")
    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def _hypr_json(what: str):
    return json.loads(_run(["hyprctl", "-j", what]) or "null")


def _dispatch(lua: str, *legacy: str) -> str:
    """Run a Hyprland dispatcher: the Lua form first, then the old one.

    Hyprland 0.56 with a Lua config (Omarchy's, from 4.5) reads
    `hyprctl dispatch X` as Lua, so `closewindow address:0x1` is a syntax
    error there -- found on the first real run, after the stubbed tests had
    passed. Older Hyprland reads only the old form. Omarchy's own scripts
    try both in this order, and so does this. Every value interpolated into
    `lua` has already been checked against a pattern (an address, a number).
    """
    out = _run(["hyprctl", "dispatch", lua]).strip()
    if out.lower() == "ok":
        return "done"
    if legacy:
        old = _run(["hyprctl", "dispatch", *legacy]).strip()
        if old.lower() == "ok" or not old:
            return "done"
        raise ToolError(old[:300])
    raise ToolError(out[:300])


def _window(c: dict, focused: str = "") -> dict:
    return {"address": c.get("address"), "class": c.get("class"),
            "title": c.get("title"), "workspace": (c.get("workspace") or {}).get("id"),
            "focused": c.get("address") == focused}


# --- desktop entries -------------------------------------------------------

def _app_dirs() -> list[Path]:
    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    dirs = [data_home] + [Path(d) for d in
                          (os.environ.get("XDG_DATA_DIRS") or
                           "/usr/local/share:/usr/share").split(":") if d]
    return [d / "applications" for d in dirs]


def find_app(name: str, dirs: list[Path] | None = None) -> str | None:
    """The desktop-file id whose Name matches `name`, best match first:
    exact, then starts-with, then contains. Hidden and NoDisplay entries are
    skipped. None when nothing matches."""
    want = " ".join(name.lower().split())
    if not want:
        return None
    exact = starts = contains = None
    seen = set()
    for d in dirs if dirs is not None else _app_dirs():
        if not d.is_dir():
            continue
        for f in sorted(d.rglob("*.desktop")):
            app_id = str(f.relative_to(d)).replace("/", "-")
            if app_id in seen:
                continue
            seen.add(app_id)
            fields = _desktop_fields(f)
            if fields.get("NoDisplay") == "true" or fields.get("Hidden") == "true":
                continue
            names = [fields.get("Name", ""), fields.get("GenericName", ""),
                     app_id.removesuffix(".desktop")]
            for n in (x.lower() for x in names if x):
                if n == want:
                    exact = exact or app_id
                elif n.startswith(want):
                    starts = starts or app_id
                elif want in n:
                    contains = contains or app_id
    return exact or starts or contains


def _desktop_fields(path: Path) -> dict:
    out, inside = {}, False
    try:
        for line in path.read_text(errors="replace").splitlines():
            line = line.strip()
            if line.startswith("["):
                inside = line == "[Desktop Entry]"
                continue
            if inside and "=" in line:
                k, v = line.split("=", 1)
                out.setdefault(k.strip(), v.strip())
    except OSError:
        pass
    return out


# --- what was asked this turn ----------------------------------------------

def heard_this_turn() -> str:
    """The request the daemon heard last, from its state file."""
    from paths import RUNTIME_DIR
    try:
        state = json.loads((RUNTIME_DIR / "state").read_text())
    except (OSError, ValueError):
        return ""
    return str(state.get("transcript") or "") if isinstance(state, dict) else ""


def ask_at_the_desktop(tool: str, args: dict) -> bool:
    """Put the question on screen through the permission hook's own protocol,
    as this agent. True only on an explicit yes; never "for the whole chat"."""
    import permission_hook
    decision, _ = permission_hook._ask(f"mcp__{SERVER}__{tool}", args,
                                       note="it would see everything on screen")
    return decision == "allow"


# --- the tools -------------------------------------------------------------

def call(name: str, args: dict):
    """Run one tool. Returns text, or ("image", png bytes). Raises ToolError."""
    if not isinstance(args, dict):
        raise ToolError("arguments must be an object")
    if name == "list_windows":
        focused = (_hypr_json("activewindow") or {}).get("address", "")
        return json.dumps([_window(c, focused) for c in _hypr_json("clients") or []
                           if c.get("mapped", True)], indent=1)
    if name == "active_window":
        c = _hypr_json("activewindow") or {}
        return json.dumps(_window(c, c.get("address", "")) if c else None)
    if name == "list_workspaces":
        return json.dumps([{"id": w.get("id"), "windows": w.get("windows"),
                            "monitor": w.get("monitor")}
                           for w in _hypr_json("workspaces") or []], indent=1)
    if name == "open_app":
        app = find_app(str(args.get("name", "")))
        if not app:
            raise ToolError(f"no installed app called {args.get('name')!r}")
        _spawn(["uwsm-app", "--", app] if shutil.which("uwsm-app")
               else ["gtk-launch", app])
        return f"opened {app.removesuffix('.desktop')}"
    if name in ("focus_window", "close_window", "move_window"):
        address = str(args.get("address", ""))
        if not re.fullmatch(r"0x[0-9a-fA-F]{1,16}", address):
            raise ToolError("that is not a window address")
        win = f'window = "address:{address}"'
        if name == "focus_window":
            return _dispatch(f"hl.dsp.focus({{ {win} }})",
                             "focuswindow", f"address:{address}")
        if name == "close_window":
            return _dispatch(f"hl.dsp.window.close({{ {win} }})",
                             "closewindow", f"address:{address}")
        n = _workspace(args)
        return _dispatch(f'hl.dsp.window.move({{ workspace = "{n}", follow = false, {win} }})',
                         "movetoworkspacesilent", f"{n},address:{address}")
    if name == "switch_workspace":
        n = _workspace(args)
        return _dispatch(f'hl.dsp.focus({{ workspace = "{n}" }})', "workspace", str(n))
    if name == "open_project_layout":
        return _layout(args)
    if name == "open_in_editor":
        return _open_in_editor(args)
    if name == "show_changes":
        return _show_changes(args)
    if name == "media":
        return _media(str(args.get("action", "")))
    if name == "volume":
        return _volume(str(args.get("action", "")), args.get("percent"))
    if name == "notify":
        title = str(args.get("title", ""))[:200]
        _run(["notify-send", "--app-name=Agent Voice", "--", title,
              str(args.get("body", ""))[:2000]])
        return "shown"
    if name == "clipboard_read":
        try:
            text = _run(["wl-paste", "--no-newline", "--type", "text"])
        except ToolError as e:
            if "nothing is copied" in str(e).lower() or "no selection" in str(e).lower():
                return ""
            raise
        return text[:CLIPBOARD_MAX]
    if name == "clipboard_write":
        _copy(str(args.get("text", "")))
        return "copied"
    if name == "screenshot":
        return _screenshot(args)
    if name == "lock_screen":
        if not _LOCK_WORDS.search(heard_this_turn()):
            raise ToolError("refused: the person did not ask to lock the screen "
                            "in this request")
        _spawn(["omarchy-system-lock"] if shutil.which("omarchy-system-lock")
               else ["loginctl", "lock-session"])
        return "locking"
    if name == "suspend":
        if not _SUSPEND_WORDS.search(heard_this_turn()):
            raise ToolError("refused: the person did not ask to suspend in this "
                            "request")
        _spawn(["systemctl", "suspend"])
        return "suspending"
    raise ToolError(f"no tool called {name}")


def _workspace(args: dict) -> int:
    try:
        n = int(args.get("workspace"))
    except (TypeError, ValueError):
        raise ToolError("workspace must be a number")
    if not 1 <= n <= 99:
        raise ToolError("workspace must be 1 to 99")
    return n


def _layout(args: dict) -> str:
    folder = Path(str(args.get("folder", ""))).expanduser()
    try:
        folder = folder.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ToolError(f"no folder {args.get('folder')!r}")
    if not folder.is_dir():
        raise ToolError(f"{folder} is not a folder")
    done = []
    if args.get("terminal", True):
        _spawn(["uwsm-app", "--", "xdg-terminal-exec", f"--dir={folder}"])
        done.append("terminal")
    if args.get("editor", True):
        _spawn(["omarchy-launch-editor", str(folder)])
        done.append("editor")
    url = str(args.get("url") or "")
    if url:
        if not re.fullmatch(r"https?://[^\s]+", url):
            raise ToolError("the URL must start with http:// or https://")
        _spawn(["omarchy-launch-browser", url])
        done.append("browser")
    return f"opened {', '.join(done) or 'nothing'} for {folder}"


#: Editors that take `--goto file:line:col` and `--diff a b`.
VSCODE_LIKE = ("code", "codium", "code-oss", "cursor", "windsurf")
#: Editors that run in a terminal and take `+line`.
TERMINAL_EDITORS = ("nvim", "vim", "vi", "hx", "helix", "nano", "micro")
#: The most files show_changes opens at once.
MAX_DIFFS = 5


def default_editor() -> str:
    """Omarchy's default editor, as `omarchy default editor` stores it."""
    state = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    try:
        name = (state / "omarchy/defaults/editor").read_text().split()[0]
    except (OSError, IndexError):
        name = "nvim"
    name = Path(name).name
    return "subl" if name == "sublime_text" else name


def _real_file(raw, what="file") -> Path:
    path = Path(str(raw or "")).expanduser()
    try:
        path = path.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ToolError(f"no {what} {raw!r}")
    return path


def _open_in_editor(args: dict) -> str:
    path = _real_file(args.get("path"))
    if not path.is_file():
        raise ToolError(f"{path} is not a file")
    line = _positive(args.get("line"))
    col = _positive(args.get("column"))
    editor = default_editor()
    where = f"{path}:{line}" + (f":{col}" if col else "") if line else str(path)
    if editor in VSCODE_LIKE and shutil.which(editor):
        _spawn(["uwsm-app", "--", editor, "--goto", where] if shutil.which("uwsm-app")
               else [editor, "--goto", where])
    elif editor in ("zed", "zeditor") and shutil.which(editor):
        _spawn(["uwsm-app", "--", editor, where])
    elif editor in TERMINAL_EDITORS and shutil.which(editor):
        _spawn(["omarchy-launch-tui", editor] + ([f"+{line}"] if line else [])
               + ["--", str(path)])
    else:
        _spawn(["omarchy-launch-editor", str(path)])
    return f"opened {path.name}" + (f" at line {line}" if line else "") + f" in {editor}"


def _positive(value) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n >= 1 else None


def _git(folder: Path, *args: str) -> str:
    return _run(["git", "-C", str(folder), *args])


def _show_changes(args: dict) -> str:
    folder = _real_file(args.get("folder"), "folder")
    if not folder.is_dir():
        raise ToolError(f"{folder} is not a folder")
    try:
        top = Path(_git(folder, "rev-parse", "--show-toplevel").strip())
    except ToolError:
        raise ToolError(f"{folder} is not in a git repository")
    changed = [l for l in _git(top, "diff", "--name-only", "HEAD", "--").splitlines() if l]
    if args.get("path"):
        want = _real_file(args["path"])
        try:
            rel = str(want.relative_to(top))
        except ValueError:
            raise ToolError(f"{want} is not inside {top}")
        if rel not in changed:
            return f"{rel} has no changes since the last commit"
        changed = [rel]
    if not changed:
        return "nothing has changed since the last commit"
    editor = default_editor()
    if editor not in VSCODE_LIKE or not shutil.which(editor):
        stat = _git(top, "diff", "--stat", "HEAD", "--").strip()
        return (f"diffs open only in a VS Code-style editor (yours is {editor}); "
                f"changed since the last commit:\n{stat}")[:4000]
    from paths import RUNTIME_DIR
    base_dir = RUNTIME_DIR / "diffs"
    base_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(base_dir, 0o700)
    opened = []
    for rel in changed[:MAX_DIFFS]:
        current = top / rel
        try:
            before = subprocess.run(["git", "-C", str(top), "show", f"HEAD:{rel}"],
                                    capture_output=True, timeout=CMD_TIMEOUT_S).stdout
        except (OSError, subprocess.SubprocessError):
            before = b""
        # The last commit's copy, in the private runtime directory: tmpfs,
        # 0700, gone at logout. Named so the editor's tab says what it is.
        tag = hashlib.sha256(f"{top}\0{rel}".encode()).hexdigest()[:10]
        base = base_dir / f"{tag}-HEAD-{Path(rel).name}"
        fd = os.open(base, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(before)
        target = current if current.exists() else Path(os.devnull)
        _spawn(["uwsm-app", "--", editor, "--diff", str(base), str(target)]
               if shutil.which("uwsm-app") else [editor, "--diff", str(base), str(target)])
        opened.append(rel)
    more = len(changed) - len(opened)
    return ("opened diffs of " + ", ".join(opened)
            + (f" ({more} more changed; ask for one by path)" if more > 0 else ""))


_MPRIS = "org.mpris.MediaPlayer2"
_MEDIA_METHODS = {"play-pause": "PlayPause", "play": "Play", "pause": "Pause",
                  "next": "Next", "previous": "Previous", "stop": "Stop"}


def _media(action: str) -> str:
    method = _MEDIA_METHODS.get(action)
    if not method:
        raise ToolError("unknown media action")
    if shutil.which("playerctl"):
        _run(["playerctl", action])
        return "done"
    # No playerctl here: MPRIS over the session bus, which every player
    # speaks and systemd's busctl can reach.
    names = _run(["busctl", "--user", "--json=short", "list"])
    try:
        players = [n["name"] for n in json.loads(names)
                   if str(n.get("name", "")).startswith(_MPRIS + ".")]
    except (ValueError, TypeError, KeyError):
        players = []
    if not players:
        raise ToolError("nothing is playing")
    _run(["busctl", "--user", "call", players[0], "/org/mpris/MediaPlayer2",
          _MPRIS + ".Player", method])
    return f"done ({players[0].removeprefix(_MPRIS + '.')})"


def _volume(action: str, percent) -> str:
    if action == "set":
        try:
            p = max(0, min(100, int(percent)))
        except (TypeError, ValueError):
            raise ToolError("set needs a percent from 0 to 100")
        _run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{p}%"])
        return f"volume {p}%"
    if action not in ("raise", "lower", "mute-toggle"):
        raise ToolError("unknown volume action")
    if shutil.which("omarchy-audio-output-volume"):
        _run(["omarchy-audio-output-volume", action])
    else:
        _run(["wpctl", *{"raise": ("set-volume", "@DEFAULT_AUDIO_SINK@", "5%+"),
                         "lower": ("set-volume", "@DEFAULT_AUDIO_SINK@", "5%-"),
                         "mute-toggle": ("set-mute", "@DEFAULT_AUDIO_SINK@",
                                         "toggle")}[action]])
    return "done"


def _screenshot(args: dict):
    try:
        scale = float(args.get("scale", 0.5))
    except (TypeError, ValueError):
        scale = 0.5
    scale = max(0.25, min(1.0, scale))
    if not ask_at_the_desktop("screenshot", {"scale": scale}):
        raise ToolError("refused at the desktop: no screenshot was taken")
    fd, tmp = tempfile.mkstemp(prefix="agentvoice-shot-", suffix=".png")
    os.close(fd)
    try:
        os.chmod(tmp, 0o600)
        _run(["grim", "-s", f"{scale:g}", tmp], timeout=15)
        return ("image", Path(tmp).read_bytes())
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# --- the protocol ----------------------------------------------------------

def handle(message: dict) -> dict | None:
    """One JSON-RPC message in, one response out (None for a notification)."""
    if not isinstance(message, dict):
        return _error(None, -32600, "invalid request")
    mid = message.get("id")
    method = message.get("method")
    if mid is None:
        return None                     # notifications need no answer
    if method == "initialize":
        params = message.get("params") or {}
        asked = params.get("protocolVersion") if isinstance(params, dict) else None
        return _result(mid, {
            "protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER, "version": VERSION},
            "instructions": "Desktop tools from Agent Voice. Each change goes "
                            "through the agent's permission level; a screenshot "
                            "is asked about every time.",
        })
    if method == "ping":
        return _result(mid, {})
    if method == "tools/list":
        return _result(mid, {"tools": TOOLS})
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name") if isinstance(params, dict) else None
        args = (params.get("arguments") or {}) if isinstance(params, dict) else {}
        try:
            out = call(str(name), args)
        except ToolError as e:
            return _result(mid, {"content": [{"type": "text", "text": str(e)}],
                                 "isError": True})
        except Exception as e:          # noqa: BLE001 -- reported, not raised
            return _result(mid, {"content": [{"type": "text",
                                              "text": f"{type(e).__name__}: {e}"}],
                                 "isError": True})
        if isinstance(out, tuple) and out[0] == "image":
            return _result(mid, {"content": [{
                "type": "image", "mimeType": "image/png",
                "data": base64.b64encode(out[1]).decode()}]})
        return _result(mid, {"content": [{"type": "text", "text": str(out)}]})
    return _error(mid, -32601, f"no method {method}")


def _result(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _error(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def serve(stdin=sys.stdin, stdout=sys.stdout) -> None:
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            reply = _error(None, -32700, "parse error")
        else:
            reply = handle(message)
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()


def mcp_config(program: str, named: str = "") -> str:
    """The `--mcp-config` JSON that starts this server for one agent."""
    args = [str(Path(__file__).resolve()), program] + ([named] if named else [])
    return json.dumps({"mcpServers": {SERVER: {
        "type": "stdio", "command": sys.executable, "args": args}}})


if __name__ == "__main__":
    serve()
