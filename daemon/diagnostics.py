"""About: this install, what it copies, updates, and who it talks to
(master plan M26).

Four things the About page asks, each answered from the place that knows:

- **This install** (`about`). The settings window runs from the plugin
  folder, the service from the copy `install.sh` put in `DATA_DIR/app`, and
  they can be different builds -- a deploy without an install leaves them
  so on purpose when no daemon file changed. Each side says its own commit;
  when they differ, git is asked whether the daemon's files differ between
  the two, so "different builds, same daemon code" is not reported as a
  fault. The stamp is read tolerantly: a VERSION from before M26 has one
  line, and says nothing about its branch.
- **Diagnostics** (`report`, `copy`). Built from allowlists, never from a
  blocklist, because the thing being protected is whatever somebody said:
  a setting is shown only by its kind (a number, a switch, a word from a
  short list; a URL as its host; any other text only as "set"), and a
  journal line only when it matches one of the shapes the daemon's
  structural prints have. A line nothing matches is left out and counted,
  even with `logSpeech` on -- a transcript line has no fixed shape, so the
  only safe test is "is this one of ours". Home paths collapse to `~` and
  anything key-shaped is masked last, over the whole text. `copy` hands it
  to `wl-copy` on stdin.
- **Updates** (`updates`). Only when clicked: one `git ls-remote` of the
  remote the plugin folder tracks, which the answer names. A folder that
  tracks none (a deploy checkout has no `origin`, on purpose) says so and
  asks nobody.
- **Who it talks to** (`backends`). What runs here (wake word,
  transcription, voices) and each backend as cloud or local with what is
  known about it: not found, installed, or has answered a turn here -- the
  last from stats (`record_answer`), never from finding the program, which
  says nothing about whether it is signed in.

    diagnostics.py about [--plugin DIR] [--json]
    diagnostics.py report [--plugin DIR]      the text Copy diagnostics copies
    diagnostics.py copy [--plugin DIR]        ... into the clipboard; prints a JSON line
    diagnostics.py updates [--plugin DIR] [--json]
    diagnostics.py backends [--json]
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import paths  # noqa: E402

PLUGIN_ID = "duaneoca.agentvoice"
#: The files whose difference makes two builds run different daemon code:
#: what install.sh copies into DATA_DIR/app.
DAEMON_FILES = ("daemon", "bin", "desktop", "install.sh", "requirements.txt",
                "requirements-openwakeword.txt", "requirements-sherpa.txt", "models.lock")
#: How many structural journal lines a report carries, and how far back it
#: looks for them.
JOURNAL_LINES = 50
JOURNAL_SCAN = 3000


def _git(folder: Path, *args: str, timeout: float = 5.0) -> subprocess.CompletedProcess | None:
    """git in `folder`, never prompting, never writing.

    `core.fsmonitor` is emptied because a repository's own config can set it
    to a command that git then runs (paths.build_id has the longer note);
    `--no-optional-locks` keeps a status-like command from refreshing the
    index; `protocol.ext.allow=never` keeps a remote URL from being a
    command line."""
    # GIT_DIR and friends from a caller (a git hook, a terminal inside one)
    # would point every question at some other repository.
    env = {k: v for k, v in os.environ.items()
           if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")}
    env.update({"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "/bin/false",
                "SSH_ASKPASS": "/bin/false", "LC_ALL": "C"})
    try:
        return subprocess.run(["git", "-c", "core.fsmonitor=", "-c", "protocol.ext.allow=never",
                               "--no-optional-locks", "-C", str(folder), *args],
                              capture_output=True, text=True, timeout=timeout, env=env,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None


def _out(p: subprocess.CompletedProcess | None) -> str:
    return p.stdout.strip() if p is not None and p.returncode == 0 else ""


# --- this install ---------------------------------------------------------------------

_COMMIT = re.compile(r"[0-9a-f]{7,40}")
_BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,99}")
_WHEN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[+-]\d{2}:?\d{2}|Z)?")
#: install.sh's first line: `0.2.0 (d4ad068)`, `0.2.0 (v0.2-3-gd4ad068-dirty)`,
#: `unversioned`.
_FIRST = re.compile(r"^(\S{1,40})(?:\s+\((?:.*?-g)?([0-9a-f]{4,40})(-dirty)?\))?")


def default_app() -> Path:
    return paths.DATA_DIR / "app"


def default_plugin() -> Path:
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return config / "omarchy" / "plugins" / PLUGIN_ID


def _iso(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def read_stamp(app: Path) -> dict:
    """What `install.sh` wrote in `app/VERSION`, read so that anything it
    does not recognise is left out rather than shown.

    Line one is the build (`0.2.0 (d4ad068)`), as every install has written
    it; from M26 `commit=`, `branch=` and `installed=` lines follow. An older
    stamp gives its short commit from line one, no branch (the page says
    "unknown branch") and, for the install time, the file's own time."""
    out = {"found": False, "build": "", "version": "", "commit": "", "dirty": False,
           "branch": "", "installed": "", "installed_from": ""}
    stamp = app / "VERSION"
    try:
        text = stamp.read_text(errors="replace")[:4096]
        mtime = stamp.stat().st_mtime
    except OSError:
        return out
    lines = text.splitlines()
    first = lines[0].strip() if lines else ""
    out["found"] = True
    out["build"] = first[:80]
    m = _FIRST.match(first)
    if m:
        out["version"] = m.group(1)
        out["commit"] = m.group(2) or ""
        out["dirty"] = bool(m.group(3))
    for line in lines[1:20]:
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key == "commit" and _COMMIT.fullmatch(value):
            out["commit"] = value
        elif key == "branch" and (value == "detached" or _BRANCH.fullmatch(value)):
            out["branch"] = value
        elif key == "installed" and _WHEN.fullmatch(value):
            out["installed"], out["installed_from"] = value, "stamp"
    if not out["installed"]:
        out["installed"], out["installed_from"] = _iso(mtime), "file"
    return out


def _manifest_version(folder: Path) -> str:
    try:
        m = json.loads((folder / "manifest.json").read_text())
        v = str(m.get("version") or "") if isinstance(m, dict) else ""
        return v if re.fullmatch(r"[0-9A-Za-z.+-]{1,40}", v) else ""
    except (OSError, ValueError):
        return ""


def plugin_info(plugin: Path) -> dict:
    """The settings' own build: the plugin folder's manifest and, when it is
    a git checkout of its own, its commit and branch ("detached" for a
    deploy checkout)."""
    folder = plugin.resolve()
    out = {"version": _manifest_version(folder), "commit": "", "branch": "", "git": False}
    top = _out(_git(folder, "rev-parse", "--show-toplevel"))
    if not top or Path(top).resolve() != folder:
        return out
    out["git"] = True
    commit = _out(_git(folder, "rev-parse", "HEAD"))
    out["commit"] = commit if _COMMIT.fullmatch(commit) else ""
    branch = _out(_git(folder, "symbolic-ref", "--short", "-q", "HEAD"))
    out["branch"] = branch if _BRANCH.fullmatch(branch) else "detached"
    return out


def compare(plugin: Path, daemon_commit: str, plugin_commit: str) -> str:
    """"same", "same-code" (two builds, no daemon file differs), "differs",
    or "unknown"."""
    if not daemon_commit or not plugin_commit:
        return "unknown"
    if plugin_commit.startswith(daemon_commit) or daemon_commit.startswith(plugin_commit):
        return "same"
    p = _git(plugin.resolve(), "diff", "--quiet", daemon_commit, plugin_commit, "--", *DAEMON_FILES)
    if p is None:
        return "unknown"
    return {0: "same-code", 1: "differs"}.get(p.returncode, "unknown")


def about(plugin: Path | None = None, app: Path | None = None) -> dict:
    plugin = default_plugin() if plugin is None else plugin
    app = default_app() if app is None else app
    daemon = read_stamp(app)
    mine = plugin_info(plugin)
    match = compare(plugin, daemon["commit"], mine["commit"]) if daemon["found"] else "unknown"
    if not daemon["found"]:
        note = "The service is not installed, or was installed before builds were stamped."
    elif match == "same":
        note = "The settings and the service are the same build."
    elif match == "same-code":
        note = ("The settings and the service are different builds, but no daemon file "
                "differs between them, so the service is current.")
    elif match == "differs":
        note = ("The service was installed from a different build than these settings. "
                "Repair the installation (Other settings → Maintenance) to bring it level.")
    else:
        note = "Could not tell whether the service and the settings are the same build."
    if daemon["dirty"] and match in ("same", "same-code"):
        # A commit says nothing about uncommitted edits installed with it.
        note += " The service was installed from a tree with uncommitted changes, which no commit records."
    return {"version": mine["version"] or daemon["version"], "plugin": mine, "daemon": daemon,
            "match": match, "note": note}


# --- diagnostics: settings ----------------------------------------------------------

#: Text settings shown as their value, because every value they take is a
#: word from a short list (or a model or voice name). Checked against
#: _WORD as well: a hand-edited value that is not a plain word is "(other)".
ENUM_KEYS = frozenset({
    "engine", "model", "owwModel", "narration", "commandsInSentences", "hudSize",
    "hudPosition", "hudTextSize", "mainProgram", "voice", "mainNotesWrite",
    "mainCollaboration", "mainChatSearch", "chatSummaries", "chatRetention",
    "endpointModel", "crossCheckEngines", "livePartials",
})
URL_KEYS = frozenset({"endpointUrl"})
#: Maps of program -> word (the main agent's level, model and effort by
#: program): shown when every key and value is a plain word.
WORD_MAPS = frozenset({"permissions", "agentModels", "agentEfforts"})
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:+-]{0,47}")
#: Per-agent fields shown in the summary, each a word from a short list.
AGENT_FIELDS = ("agent", "model", "effort", "level", "voice", "narration", "collaboration",
                "chatSearch", "notesWrite")


def host_only(url) -> str:
    try:
        parts = urllib.parse.urlsplit(str(url or "").strip())
        host = parts.hostname or ""
        port = parts.port
    except ValueError:
        return "(not a URL)"
    if not host:
        return "(not a URL)" if str(url or "").strip() else ""
    return f"{parts.scheme}://{host}" + (f":{port}" if port else "")


def _shown(key: str, value, default):
    """A setting as the summary may show it, or None to leave it out."""
    if key in URL_KEYS:
        return host_only(value)
    if isinstance(default, bool):
        return value if isinstance(value, bool) else "(unreadable)"
    if isinstance(default, (int, float)):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
        # The daemon reads "90000" as 90000 (M24), so it is shown as written.
        if isinstance(value, str) and re.fullmatch(r"\s*-?\d{1,9}(?:\.\d{1,6})?\s*", value):
            return value.strip()
        return "(unreadable)"
    if key in ENUM_KEYS:
        if value in ("", None):
            return ""
        return value if isinstance(value, str) and _WORD.fullmatch(value) else "(other)"
    if key in WORD_MAPS:
        if not isinstance(value, dict):
            return "(unreadable)"
        return {k: v for k, v in value.items()
                if isinstance(k, str) and _WORD.fullmatch(k)
                and isinstance(v, str) and _WORD.fullmatch(v)}
    if key == "voiceAgents":
        if not isinstance(value, list):
            return "(unreadable)"
        agents = []
        for entry in value[:32]:
            if not isinstance(entry, dict):
                agents.append("(unreadable)")
                continue
            a = {f: entry[f] for f in AGENT_FIELDS
                 if isinstance(entry.get(f), str) and _WORD.fullmatch(entry[f])}
            if isinstance(entry.get("enabled"), bool):
                a["enabled"] = entry["enabled"]
            if entry.get("endpointUrl"):
                a["endpoint"] = host_only(entry.get("endpointUrl"))
            agents.append(a)
        return agents
    if isinstance(value, list):
        return f"{len(value)} item" + ("" if len(value) == 1 else "s")
    if isinstance(value, dict):
        return f"{len(value)} entr" + ("y" if len(value) == 1 else "ies")
    if isinstance(value, str):
        return "set" if value.strip() else "not set"
    return "(unreadable)"


def settings_summary(values: dict, defaults: dict) -> list[str]:
    """`key = value` for every setting that is not its default, each shown
    only by its kind (see _shown). Only keys the daemon knows are looked at,
    so a stray key somebody added to shell.json is not read at all."""
    out = []
    for key in sorted(defaults):
        if key not in values or values[key] == defaults[key]:
            continue
        shown = _shown(key, values[key], defaults[key])
        if shown is None:
            continue
        out.append(f"{key} = {json.dumps(shown, ensure_ascii=False)}")
    return out


# --- diagnostics: the journal --------------------------------------------------------

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
#: A display name in the daemon's quotes, with no quote of any kind inside.
_N = r"[^\"“”\n]{1,40}"
_NUM = r"\d+(?:\.\d+)?"
#: Each structural line the daemon prints, as a whole line. A transcript, a
#: reply, a typed message, a progress line or an error's text has no fixed
#: shape, so none of them can match one of these -- which is the point: a
#: line is kept because it is known to be ours, never because it was not
#: recognised as speech. Nothing below admits a quoted string except a name.
STRUCTURAL = [re.compile(p) for p in (
    r"\[[A-Za-z0-9_:.\-]{1,80}\]",                                     # a tool marker
    rf"agent {_NUM}s(?:, first token \d+ms)?",
    rf"\(dropped \d+ms of echo\)",
    rf"{_NUM}s audio, whisper \d+ms(?: in \d+ pieces)?, \d+ms waited",
    rf"heard → spoke in {_NUM}s(?:\s+\([a-z][a-z ]{{0,30}} {_NUM}s(?: · [a-z][a-z ]{{0,30}} {_NUM}s)*\))?",
    r"● [^\"“”]{1,120}",                                                # wake, open mic, still listening
    r"⌨ typed",
    r"chime: [a-z]+ \([a-z0-9 ]{1,60}\)",
    r"Missing phoneme from id map: \S{0,4}",
    r"sound is going to [^\"“”]{1,80} — (?:not a headset, so it cannot be interrupted by voice"
    r"|talk over it to interrupt)",
    rf"prompt for “{_N}”: rules \d+ · defaults \d+ · personality \d+ · instructions \d+"
    rf" · roster \d+ = \d+ chars",
    r"\((?:nothing heard|hit max_utterance_ms)\)",
    r"interrupted|knobs updated|mic released|mic engaged|full stop — everything stopped"
    r"|heard you over us — stopping",
    r"screen (?:locked|unlocked)(?: \(told, not polled\)| — microphone (?:open|closed))?",
    r"loading whisper [\w.]{1,30}\.\.\.\s+whisper [\w.]{1,30} ready, \d+ vocab terms",
    r"listening for \"[a-z ]{1,40}\"\s+lead-in \d+ms · trailing \d+ms",
    r"conversation: (?:on|off)(?:, \d+s follow-up window)?",
    r"permission: [A-Za-z0-9 ,.'’—()-]{1,160}",
    r"agent: [\w.-]{1,30} · [^\"“”]{1,200}",
    # Collaboration and cards: an id first, then names, tools and reasons
    # from fixed lists (no brief or answer is printed by collab.py).
    r"(?:pass|delegate|ask|message) [0-9a-f]{8,16}[: ][^\"“”]{1,200}",
    r"card [0-9a-f]{8,32}:? [^\"“”]{1,160}",
    rf"{_N}: \d+ message\(s\), \d+ result\(s\) delivered",
    r"\((?:goodbye — waiting for the wake word|open mic: not meant for it|readout preview for \d+s"
    r"|try for [\w-]{1,48} refused)\)",
    r"agent files: [a-z0-9 :|_-]{1,1000}",
    rf"agent “{_N}”: [\w.-]{{1,30}} · [\w.:/-]{{1,60}} · [a-z]{{1,10}} effort · [a-z]{{1,10}}",
    rf"agent “{_N}” speaks as [\w-]{{1,60}}",
    rf"agent “{_N}”: (?:new chat|continuing a saved chat \((?:replayed|resumed)\)|moved to a terminal"
    r"|the terminal is closed — the chat is back)",
    r"voice speed: \d+%|vocabulary: \d+ terms",
    r"wake: [\w.\- @(),+]{1,200}",
    r"wake decision: [a-z ]{1,60}",
    r"command: [a-z_]{1,30} \([a-z ,]{1,80}\)",
    r"gate [\w .,+()/·\[\]-]{1,200}",
    r"\(second check: [^\"“”]{1,120}, \d+ms\)",
    r"\(rejected — confidence [\d.]+ < [\d.]+\)",
    r"project: [^\"“”]{1,200} · [a-z ]{1,20} — [a-z ]{1,30}",
    rf"tools for “{_N}”: [\w ·:-]{{1,300}}",
    rf"chat named in {_NUM}s \(\d+\+\d+ chars\)",
    r"agentvoice skill rebuilt: \d+ characters",
    rf"try: [\w-]{{1,48}} answered in {_NUM}s \(\d+ chars\)",
    r"knobs: [\w.\[\]-]{1,80} · build [\w.() -]{1,60}",
    r"agent error: [a-z-]{1,40}\s+\(details withheld — logSpeech is off\)",
    r"Traceback \(most recent call last\):",
    r"File \"[^\"\n]{1,300}\", line \d+, in [\w<>.]{1,80}",
)]
#: systemd's own lines about the unit: starting, stopping, how it exited,
#: what it used. Nothing said reaches them.
_SYSTEMD = re.compile(r"(?:Starting|Started|Stopping|Stopped|Failed to start) Agent Voice[^\n]{0,120}"
                      r"|agentvoice\.service: [A-Za-z][^\n]{0,250}")
#: An exception's type; its message is not kept (it can quote a prompt).
_EXC = re.compile(r"((?:[A-Za-z_][\w]*\.)*[A-Z][\w]*(?:Error|Exception|Interrupt|Exit|Warning))(?::.*)?")


def structural(line: str) -> str | None:
    """The line as the report may carry it, or None to leave it out."""
    line = _ANSI.sub("", line).strip()
    if not line:
        return None
    if any(p.fullmatch(line) for p in STRUCTURAL):
        return line
    m = _EXC.fullmatch(line)
    if m:
        return m.group(1) + (": (message left out)" if ":" in line else "")
    return None


def _message(entry: dict) -> str:
    m = entry.get("MESSAGE")
    if isinstance(m, list):
        try:
            return bytes(int(b) & 0xFF for b in m).decode("utf-8", "replace")
        except (TypeError, ValueError):
            return ""
    return m if isinstance(m, str) else ""


def _journal_json(n: int = JOURNAL_SCAN) -> list[str]:
    """The service's last `n` journal entries as JSON lines (-o json: the
    default renderer shows a line with a carriage return as a blob, which
    hides exactly the lines most likely to carry speech -- CLAUDE.md)."""
    try:
        p = subprocess.run(["journalctl", "--user", "-u", "agentvoice.service", "-o", "json",
                            "-n", str(n), "--no-pager", "-q"],
                           capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return []
    return p.stdout.splitlines() if p.returncode == 0 else []


def journal_tail(raw_lines: list[str], keep: int = JOURNAL_LINES) -> tuple[list[str], int]:
    """The last `keep` structural lines, and how many were left out.

    Each entry is split at carriage returns and newlines and every piece is
    judged alone, so a progress line that rewrote itself cannot carry text
    past the check on its first piece. systemd's own lines about the unit
    (start, stop, exit status) are matched against their own shapes."""
    kept, left_out = [], 0
    for raw in raw_lines:
        try:
            entry = json.loads(raw)
        except ValueError:
            left_out += 1
            continue
        if not isinstance(entry, dict):
            left_out += 1
            continue
        when = ""
        try:
            when = time.strftime("%H:%M:%S", time.localtime(int(entry.get("__REALTIME_TIMESTAMP")) / 1e6))
        except (TypeError, ValueError):
            pass
        text = _message(entry)
        pieces = [p for p in re.split(r"[\r\n]", text) if p.strip()]
        if entry.get("SYSLOG_IDENTIFIER") == "systemd":
            good = [_ANSI.sub("", p).strip()[:300] for p in pieces if _SYSTEMD.fullmatch(p.strip())]
        else:
            good = [s for s in (structural(p) for p in pieces) if s]
        left_out += len(pieces) - len(good)
        kept.extend(f"{when} {g}".strip() for g in good)
    return kept[-keep:], left_out


def collapse_home(text: str) -> str:
    home = str(Path.home()).rstrip("/")
    if len(home) > 1:
        text = text.replace(home + "/", "~/")
        text = re.sub(re.escape(home) + r"(?![\w.-])", "~", text)
    return text


def mask_keys(text: str) -> str:
    """Anything key-shaped, wherever it ended up: the masks the Advanced
    tab's command line uses (runinfo), over the whole text."""
    import runinfo
    text = runinfo._KEYISH.sub(runinfo.MASK, text)
    text = runinfo._BEARER.sub(lambda m: m.group(1) + runinfo.MASK, text)
    text = runinfo._USERINFO.sub(lambda m: m.group(1) + runinfo.MASK + "@", text)
    return runinfo._QUERY.sub(lambda m: m.group(1) + "?" + runinfo.MASK, text)


def _omarchy_version() -> str:
    try:
        p = subprocess.run(["omarchy-version"], capture_output=True, text=True, timeout=3,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    v = p.stdout.strip().splitlines()[0] if p.returncode == 0 and p.stdout.strip() else ""
    return v if re.fullmatch(r"[0-9A-Za-z.+_-]{1,40}", v) else "unknown"


def _service_state() -> str:
    try:
        p = subprocess.run(["systemctl", "--user", "is-active", "agentvoice.service"],
                           capture_output=True, text=True, timeout=3, stdin=subprocess.DEVNULL)
        active = p.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if active != "active":
        return re.sub(r"[^a-z-]", "", active)[:20] or "unknown"
    try:
        state = json.loads((paths.RUNTIME_DIR / "state").read_text()).get("state")
    except (OSError, ValueError, AttributeError):
        state = ""
    return "running" + (f", {state}" if isinstance(state, str) and re.fullmatch(r"[a-z-]{1,20}", state)
                        else "")


def report(plugin: Path | None = None, app: Path | None = None, *, values: dict | None = None,
           journal: list[str] | None = None, now: float | None = None) -> str:
    """The text Copy diagnostics puts on the clipboard."""
    import runtime
    a = about(plugin, app)
    if values is None:
        cfg = runtime.Config()
        # As stored (shell.json over the TOML over the defaults), not as
        # each getter reads it: an unreadable value is shown as unreadable.
        values = {k: cfg._values.get(k, v) for k, v in runtime.DEFAULTS.items()}
    lines_out = [
        "Agent Voice diagnostics, " + time.strftime("%Y-%m-%d %H:%M", time.localtime(now)),
        "(made from allowlists: no transcript, reply, key, URL path or folder text is in it)",
        "",
        f"version: {a['version'] or 'unknown'}",
        "settings build: " + (
            (a["plugin"]["commit"][:12] + " (" + (a["plugin"]["branch"] or "unknown branch") + ")")
            if a["plugin"]["commit"] else "not a git checkout"),
        "service build: " + (
            (a["daemon"]["build"] + ", " + (a["daemon"]["branch"] or "unknown branch")
             + ", installed " + a["daemon"]["installed"]) if a["daemon"]["found"] else "not installed"),
        f"builds: {a['match']}",
        f"Omarchy: {_omarchy_version()}",
        f"service: {_service_state()}",
    ]
    changed = settings_summary(values, runtime.DEFAULTS)
    lines_out += ["", f"settings changed from the defaults ({len(changed)}):"]
    lines_out += ["  " + c for c in changed] or ["  none"]
    raw = _journal_json() if journal is None else journal
    kept, left_out = journal_tail(raw)
    lines_out += ["", f"journal: the last {len(kept)} structural lines"
                  + (f" ({left_out} other lines left out)" if left_out else "")]
    lines_out += ["  " + k for k in kept] or ["  (nothing)"]
    return mask_keys(collapse_home("\n".join(lines_out))) + "\n"


def copy(text: str) -> bool:
    """Into the clipboard through `wl-copy`, on stdin (argv is readable by
    every account). stdout and stderr go nowhere: wl-copy forks a child
    that serves the clipboard until it is replaced, and a pipe held by it
    would keep this waiting until then."""
    try:
        p = subprocess.run(["wl-copy"], input=text, text=True, timeout=10,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return False
    return p.returncode == 0


# --- updates --------------------------------------------------------------------------

def shown_url(url: str) -> str:
    """A remote's URL with any user or password taken out."""
    url = str(url or "").strip()
    m = re.match(r"^([a-z][a-z0-9+.-]*://)(?:[^@/]*@)?(.*)$", url, re.I)
    if m:
        return m.group(1) + m.group(2)
    m = re.match(r"^[^@/]+@([^:/]+):(.*)$", url)       # scp-like: git@host:path
    if m:
        return f"{m.group(1)}:{m.group(2)}"
    return url[:200]


def update_check(plugin: Path | None = None, timeout: float = 20.0) -> dict:
    """Ask the remote the plugin folder tracks for its newest commit. Run
    only when somebody clicks Check for updates."""
    folder = (default_plugin() if plugin is None else plugin).resolve()
    out = {"status": "", "remote": "", "url": "", "ref": "", "local": "", "remote_commit": "",
           "message": ""}
    info = plugin_info(folder)
    if not info["git"]:
        out.update(status="no-git", message="This copy is not a git checkout, so there is "
                   "nothing to compare it with. Update it the way it was installed.")
        return out
    out["local"] = info["commit"]
    remote, ref = "", ""
    upstream = _out(_git(folder, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"))
    remotes = _out(_git(folder, "remote")).split()
    if upstream and "/" in upstream:
        r, b = upstream.split("/", 1)
        if r in remotes:
            remote, ref = r, "refs/heads/" + b
    if not remote and "origin" in remotes:
        remote, ref = "origin", "HEAD"
    if not remote:
        out.update(status="no-remote", message="This copy tracks no remote, so there is "
                   "nobody to ask. (A copy put here by agentvoice-deploy has none on purpose: "
                   "it is updated from the clone it came from.)")
        return out
    out["remote"], out["ref"] = remote, ref
    out["url"] = shown_url(_out(_git(folder, "remote", "get-url", remote)))
    p = _git(folder, "ls-remote", "--exit-code", remote, ref, timeout=timeout)
    first = _out(p).splitlines()[0].split() if _out(p) else []
    sha = first[0] if first and _COMMIT.fullmatch(first[0]) else ""
    if not sha:
        out.update(status="failed", message=f"Could not ask {remote}: no answer, or it does "
                   "not have that branch.")
        return out
    out["remote_commit"] = sha
    if sha == info["commit"]:
        out.update(status="current", message=f"Up to date with {remote}.")
    elif getattr(_git(folder, "merge-base", "--is-ancestor", sha, "HEAD"), "returncode", 1) == 0:
        out.update(status="ahead", message=f"This copy already has {remote}'s newest commit, "
                   "and more.")
    else:
        out.update(status="newer", message=f"{remote} has a commit this copy does not "
                   f"({sha[:12]}). `omarchy plugin update` fetches it; then repair the "
                   "installation.")
    return out


# --- who it talks to ----------------------------------------------------------------

#: Every backend offered (CLAUDE.md: one earns its place with a real turn),
#: with the program it needs on PATH. All of them send the conversation to
#: their provider: a CLI agent is a cloud service with a local front end.
BACKENDS = (
    ("claude", "Claude Code", "claude"),
    ("codex", "Codex", "codex"),
    ("gemini", "Gemini CLI", "gemini"),
    ("agy", "Antigravity", "agy"),
    ("copilot", "GitHub Copilot CLI", "copilot"),
)


def _private(host: str) -> bool:
    import endpoints
    return bool(host) and endpoints._private_host(host)


def backends(cfg=None, answered: dict | None = None, which=shutil.which) -> dict:
    """What runs here and what goes out, with what is known of each."""
    import runtime
    import stats
    cfg = runtime.Config() if cfg is None else cfg
    if answered is None:
        answered = stats.summary(stats.KEEP_DAYS)["range"].get("answered", {}) \
            if cfg.keep_stats() else None
    users: dict[str, list[str]] = {}
    try:
        import adapters
        main_program = adapters.main_program(cfg.get_str("mainProgram")) or ""
    except Exception:                   # noqa: BLE001 -- a label is not worth a crash
        main_program = cfg.get_str("mainProgram")
    main_label = cfg.main_label(cfg.get_str("phrase")) if hasattr(cfg, "main_label") else "main"
    if cfg.main_endpoint():
        main_program = "endpoint"
    users.setdefault(main_program, []).append(main_label)
    endpoints_seen = []
    if cfg.main_endpoint():
        endpoints_seen.append((cfg.main_endpoint().get("url", ""), main_label))
    for spec in cfg.all_agents():
        users.setdefault(spec.get("agent") or "", []).append(spec.get("label") or spec.get("name"))
        if spec.get("endpoint"):
            endpoints_seen.append((spec["endpoint"].get("url", ""), spec.get("label") or ""))
    rows = []
    for program, label, binary in BACKENDS:
        found = bool(which(binary))
        n = None if answered is None else int(answered.get(program, 0) or 0)
        status = "answered" if n else ("installed" if found else "not found")
        rows.append({"id": program, "label": label, "where": "cloud", "found": found,
                     "answered": n, "status": status, "used_by": users.get(program, [])})
    for url, who in endpoints_seen:
        host = host_only(url)
        hostname = urllib.parse.urlsplit(url).hostname or ""
        n = None if answered is None else int(answered.get("endpoint", 0) or 0)
        rows.append({"id": "endpoint", "label": "Endpoint " + host, "where":
                     "local" if _private(hostname) else "cloud", "found": True, "answered": n,
                     "status": "answered" if n else "configured", "used_by": [who]})
    engine = cfg.get_str("engine") or "vosk"
    local = [
        {"what": "Wake word", "how": {"oww": "openWakeWord", "openwakeword": "openWakeWord",
                                      "sherpa": "sherpa-onnx"}.get(engine, "Vosk")},
        {"what": "Transcription", "how": "Whisper " + (cfg.get_str("model") or "base.en")},
        {"what": "Voices", "how": "Piper"},
    ]
    return {"local": local, "backends": rows, "stats": answered is not None}


# --- the command line ------------------------------------------------------------------

def _plugin_arg(argv: list[str]) -> Path | None:
    if "--plugin" in argv:
        i = argv.index("--plugin")
        if i + 1 < len(argv):
            return Path(argv[i + 1])
    return None


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    as_json = "--json" in rest
    plugin = _plugin_arg(rest)
    if cmd == "about":
        a = about(plugin)
        if as_json:
            print(json.dumps(a))
        else:
            d, p = a["daemon"], a["plugin"]
            print(f"version   {a['version'] or 'unknown'}")
            print(f"settings  {p['commit'][:12] or 'not a git checkout'} "
                  f"({p['branch'] or 'unknown branch'})")
            print(f"service   {d['build'] or 'not installed'} "
                  f"({d['branch'] or 'unknown branch'}), installed {d['installed'] or 'unknown'}")
            print(a["note"])
        return 0
    if cmd == "report":
        sys.stdout.write(report(plugin))
        return 0
    if cmd == "copy":
        text = report(plugin)
        ok = copy(text)
        print(json.dumps({"copied": ok, "lines": text.count("\n"), "chars": len(text)}))
        return 0 if ok else 1
    if cmd == "updates":
        u = update_check(plugin)
        print(json.dumps(u) if as_json else u["message"])
        return 0
    if cmd == "backends":
        b = backends()
        if as_json:
            print(json.dumps(b))
        else:
            for row in b["local"]:
                print(f"{row['what']:<14} {row['how']} (on this machine)")
            for row in b["backends"]:
                print(f"{row['label']:<20} {row['where']:<6} {row['status']}")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
