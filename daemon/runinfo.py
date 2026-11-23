"""What is running: Agent details → Advanced (phase M16). Read only.

Four things the page shows about one agent, each from the place that
actually knows it rather than from a second copy of the logic:

- **The command line.** The daemon holds the live adapters, so it asks each
  one for `launch_argv()` -- the very `_argv` its `send()` runs -- and
  publishes the answer here (`$RUNDIR/runinfo.json`, 0600), with the argv
  of the last process it really started beside it. No prompt is ever in
  either: since the marketplace review every adapter hands the prompt over
  on stdin, and prompt files travel by path. What could still be in a line
  is a value somebody put in a config (a key in a detected server's `-c`,
  a header) -- so every element goes through `redact_argv`, which leans
  wide: a masked word costs a word, a missed one costs a key on screen.
- **The servers it is given, and the ones it said it started.** Given is
  the adapter's `handed_servers()`, by the same tests `_argv` makes; seen
  is the init event Claude Code prints (`tooldetect.live_servers`, M10).
  Kept apart on purpose: what a backend *can* load and what it *did* are
  different facts, and only one of them is a recording.
- **Recent log lines.** A small ring per agent in the daemon, written only
  through `Ring.add`, whose every field is typed: a kind from a fixed list,
  seconds, a tool's name by pattern, a failure kind from `failure.KINDS`, a
  change from `sessions`. There is no field a sentence fits in, so nothing
  anybody said can land there -- with `logSpeech` on or off.
- **Recent permission decisions.** `audit.log` lines of kind `permission`,
  written by the hook (time, agent, tool name, decision, how, level; never
  an argument or a path).

`agentvoice agents runinfo ID [--json]` puts them together for the page.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import stat
import sys
import threading
import time
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

MASK = "•••"

# --- redaction ----------------------------------------------------------------------

#: A word in a flag or a config key that says its value is a secret. Not
#: "session": a session id is shown on purpose, and `--no-session-persistence`
#: would otherwise hide the flag after it.
_WORD = r"(?:key|token|secret|passw(?:or)?d|auth|credential|bearer|cookie|signature)"
#: Flags whose value is masked whatever it is called: a header, an
#: environment variable.
_CARRY = r"(?:header|headers|env|environment)"
_FLAG_EQ = re.compile(r"(?is)^(--?[a-z0-9_.-]*(?:" + _WORD + "|" + _CARRY + r")[a-z0-9_.-]*=)(.+)$")
_FLAG = re.compile(r"(?i)^(?:--?[a-z0-9_.-]*(?:" + _WORD + "|" + _CARRY + r")[a-z0-9_.-]*|-H|-e)$")
#: A generated key on its own, anywhere in a word: the well-known prefixes,
#: with a digit somewhere after (so a skill named "sk-reading-list" stays).
_KEYISH = re.compile(r"(?:gh[pousr]_|github_pat_|sk-|xox[abprs]-|AKIA|glpat-|AIza)"
                     r"(?=[A-Za-z0-9_\-]*\d)[A-Za-z0-9_\-]{8,}")
_BEARER = re.compile(r"(?i)\b(bearer\s+)[^\s\"',}]+")
#: A word that looks generated: long, letters and digits mixed, no path.
_TOKENISH = re.compile(r"^(?=.*[0-9])(?=.*[A-Za-z])[A-Za-z0-9_+=-]{20,}$")
#: Which the session id is, and is shown as.
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
#: `key=value`, as Codex's `-c` takes it.
_ASSIGN = re.compile(r"(?s)^([A-Za-z0-9_.\"-]{1,200})=(.*)$")
#: A config key whose value is masked: its last part names a secret or
#: carries one. `env_vars` is a list of names, not values, and stays.
_SECRET_KEY = re.compile(r"(?i)(?:" + _WORD + r"|^env$|^headers$|^http_headers$|^environment$)")
_USERINFO = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^/\s:@\"']+):([^@\s/\"']+)@")
_QUERY = re.compile(r"(://[^\s?\"']*)\?[^\s\"']*")


def _mask_inside(word: str) -> str:
    """Keys, bearer tokens and a URL's password or query, wherever they sit."""
    word = _KEYISH.sub(MASK, word)
    word = _BEARER.sub(lambda m: m.group(1) + MASK, word)
    word = _USERINFO.sub(lambda m: f"{m.group(1)}{m.group(2)}:{MASK}@", word)
    word = _QUERY.sub(lambda m: m.group(1) + "?" + MASK, word)
    return word


def redact_argv(argv) -> list[str]:
    """`argv` as the page shows it: every element a string, and anything
    that looks like a secret masked -- the value after a secret-named,
    header or environment flag, a `--flag=value` of one, a `-c key=value`
    whose key names one, a generated-looking word, a key with a known
    prefix anywhere in a word, a bearer token, a URL's password and query.
    The session id after `--resume` is not a secret and stays."""
    out: list[str] = []
    hide_next = False
    after_c = False
    for raw in list(argv or [])[:400]:
        a = str(raw)
        if hide_next:
            hide_next = False
            # A flag right after a flag is not its value: never swallow one.
            if not a.startswith("-"):
                out.append(MASK)
                continue
        if after_c:
            after_c = False
            m = _ASSIGN.match(a)
            if m:
                last = m.group(1).replace('"', "").split(".")[-1]
                if _SECRET_KEY.search(last):
                    out.append(m.group(1) + "=" + MASK)
                    continue
            out.append(_mask_inside(a))
            continue
        if a == "-c" or a == "--config":
            after_c = True
            out.append(a)
            continue
        m = _FLAG_EQ.match(a)
        if m:
            out.append(m.group(1) + MASK)
            continue
        if _FLAG.match(a):
            hide_next = True
            out.append(a)
            continue
        if _TOKENISH.match(a) and not _UUID.match(a):
            out.append(MASK)
            continue
        out.append(_mask_inside(a))
    return out


def shown_line(argv) -> str:
    """One line a person could paste, quoted as a shell would need it."""
    return " ".join(w if w == MASK else shlex.quote(w) for w in argv or [])


# --- the log ring --------------------------------------------------------------------

#: What a line may say happened.
LOG_KINDS = ("turn", "rebuilt", "dropped", "fresh")
#: A tool's name as the CLIs report it ("Bash", "mcp__agentvoice-crew__notes_read",
#: Codex's item types). Anything else is "?".
_TOOL = re.compile(r"[A-Za-z0-9_.:@/-]{1,96}")
#: How a process was found for a turn (ClaudeCode.last_start).
_STARTS = ("warm", "cold")
#: What the ring keeps per agent.
RING_SIZE = 40


def _changes() -> frozenset:
    import sessions
    return frozenset({sessions.PROGRAM, sessions.ENDPOINT, sessions.FOLDER, sessions.LEVEL,
                      sessions.MODEL, sessions.OTHER, sessions.GRANTS})


def _failure_kinds() -> tuple:
    import failure
    return failure.KINDS


def _agent_key(value) -> str:
    return value if isinstance(value, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", value) else "?"


class Ring:
    """The last RING_SIZE structural lines for each agent, in the daemon.

    Written only through `add`, whose every field is typed, so nothing
    anybody said can be put here even by mistake (the module docstring).
    Thread-safe: turns end on their own threads."""

    def __init__(self, size: int = RING_SIZE) -> None:
        self._lines: dict[str, deque] = {}
        self._size = size
        self._lock = threading.Lock()
        #: {agent: (session id, turns in it)}, for "turns kept".
        self._turns: dict[str, tuple] = {}
        self.version = 0

    def add(self, agent: str, kind: str, *, secs=None, first_ms=None, start: str = "",
            tools=(), error: str = "", stopped: bool = False, changed=(),
            kept: bool | None = None, task: bool = False) -> dict:
        line: dict = {"at": round(time.time(), 3),
                      "kind": kind if kind in LOG_KINDS else "?"}
        if isinstance(secs, (int, float)) and not isinstance(secs, bool) and 0 <= secs < 1e6:
            line["secs"] = round(float(secs), 1)
        if isinstance(first_ms, (int, float)) and not isinstance(first_ms, bool) \
                and 0 <= first_ms < 1e8:
            line["first_ms"] = int(first_ms)
        if start:
            line["start"] = start if start in _STARTS else "?"
        counts: dict[str, int] = {}
        for t in list(tools or ())[:200]:
            name = t if isinstance(t, str) and _TOOL.fullmatch(t) else "?"
            counts[name] = counts.get(name, 0) + 1
        if counts:
            line["tools"] = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
        if error:
            line["error"] = error if error in _failure_kinds() else "unknown"
        if stopped is True:
            line["stopped"] = True
        if task is True:
            line["task"] = True
        known = _changes()
        moved = sorted({c if c in known else "?" for c in (changed or ()) if isinstance(c, str)})
        if moved:
            line["changed"] = moved
        if kept is not None:
            line["kept"] = bool(kept)
        line["text"] = render(line)
        key = _agent_key(agent)
        with self._lock:
            self._lines.setdefault(key, deque(maxlen=self._size)).append(line)
            self.version += 1
        return line

    def count_turn(self, agent: str, session_id) -> int:
        """One more turn in `session_id`; returns how many it has had here.
        A new session starts the count again."""
        key = _agent_key(agent)
        sid = session_id if isinstance(session_id, str) else None
        with self._lock:
            was, n = self._turns.get(key, (None, 0))
            n = n + 1 if (sid is not None and sid == was) else 1
            self._turns[key] = (sid, n)
            self.version += 1
            return n

    def turns(self, agent: str, session_id) -> int:
        """Turns this daemon has seen in `session_id`, 0 when it is another."""
        with self._lock:
            was, n = self._turns.get(_agent_key(agent), (None, 0))
        return n if session_id and session_id == was else 0

    def lines(self, agent: str) -> list[dict]:
        with self._lock:
            return list(self._lines.get(_agent_key(agent), ()))


def render(line: dict) -> str:
    """A ring line as words, from its typed fields alone."""
    kind = line.get("kind")
    if kind == "turn":
        parts = [f"turn {line['secs']:.1f}s" if "secs" in line else "turn"]
        if line.get("task"):
            parts.append("for another agent")
        if line.get("start") in _STARTS:
            parts.append(f"{line['start']} start")
        if "first_ms" in line:
            parts.append(f"first token {line['first_ms']} ms")
        if line.get("tools"):
            parts.append("tools: " + ", ".join(
                name + (f" ×{n}" if n > 1 else "") for name, n in line["tools"]))
        if line.get("stopped"):
            parts.append("stopped")
        if line.get("error"):
            parts.append(f"failed ({line['error']})")
        return " · ".join(parts)
    if kind == "rebuilt":
        what = " and ".join(line.get("changed") or [])
        tail = ("" if "kept" not in line else
                " · conversation kept" if line["kept"] else " · new conversation")
        return (f"started again for a new {what}" if what else "started again") + tail
    if kind == "dropped":
        return f"conversation dropped after a failure ({line.get('error') or 'unknown'})"
    if kind == "fresh":
        # Phase M17: Start fresh, or New chat, from Settings or the CLI.
        return "started fresh: new conversation"
    return "?"


# --- the record the daemon publishes ---------------------------------------------------

def path() -> Path:
    from paths import RUNTIME_DIR
    return RUNTIME_DIR / "runinfo.json"


def _host_only(url) -> str:
    from urllib.parse import urlsplit
    try:
        u = urlsplit(str(url or "").strip())
        host = u.hostname or ""
        return f"{host}:{u.port}" if u.port else host
    except ValueError:
        return ""


def record_for(agent, *, session_id=None, turns: int = 0, busy: bool = False,
               state: str = "", previous: dict | None = None) -> dict:
    """What the page shows about one adapter, built from the adapter itself.

    The next launch line is the adapter's own `launch_argv()`; while a turn
    is running the line is not rebuilt (the turn's thread owns the adapter)
    and the previous one is kept. Never raises."""
    rec: dict = {"program": str(getattr(agent, "name", "") or ""), "state": str(state or ""),
                 "busy": bool(busy)}
    if agent is None:
        rec["program"] = ""
        return rec
    cwd = getattr(agent, "cwd", None)
    rec["cwd"] = str(cwd) if cwd and getattr(agent, "has_tools", True) else ""
    rec["prompt_channel"] = str(getattr(agent, "prompt_channel", "") or "")
    remembers = bool(getattr(agent, "remembers", False))
    sid = session_id if isinstance(session_id, str) and session_id else None
    resume = getattr(agent, "resume", True) is not False
    rec["session"] = {"id": sid, "remembers": remembers,
                      "resumes": bool(remembers and sid and resume),
                      "turns": int(turns or 0),
                      # Phase M17: off, every turn starts fresh.
                      "resume": bool(resume)}
    timeouts = {"idle_s": float(getattr(agent, "idle_timeout_s", 0) or 0)}
    warm = getattr(agent, "keep_warm_s", None)
    if isinstance(warm, (int, float)) and not isinstance(warm, bool):
        timeouts["keep_warm_s"] = float(warm)
    rec["timeouts"] = timeouts
    base = getattr(agent, "base_url", None)
    if isinstance(base, str):
        rec["endpoint"] = {"host": _host_only(base), "model": str(getattr(agent, "model", "") or ""),
                           "history_turns": int(getattr(agent, "history_turns", 0) or 0)}
    if busy and previous and "argv" in previous:
        rec["argv"], rec["error"] = previous.get("argv"), previous.get("error", "")
    else:
        try:
            argv = agent.launch_argv(sid) if hasattr(agent, "launch_argv") else None
            rec["argv"] = redact_argv(argv) if argv is not None else None
            rec["error"] = ""
        except Exception as e:          # noqa: BLE001 -- Codex refusing to start, said
            rec["argv"] = None
            rec["error"] = _own_error(e)
    try:
        rec["handed"] = [{"name": str(s.get("name", ""))[:96], "source": str(s.get("source", "")),
                          "on": s.get("on") is True}
                         for s in (agent.handed_servers() if hasattr(agent, "handed_servers")
                                   else [])[:64]]
    except Exception:                   # noqa: BLE001
        rec["handed"] = []
    last = getattr(agent, "last_launch", None)
    if isinstance(last, dict) and isinstance(last.get("argv"), list):
        try:
            running = bool(agent.launch_running())
        except Exception:               # noqa: BLE001
            running = False
        rec["last"] = {"argv": redact_argv(last["argv"]),
                       "pid": last.get("pid") if isinstance(last.get("pid"), int) else None,
                       "at": last.get("at") if isinstance(last.get("at"), (int, float)) else None,
                       "running": running}
    else:
        rec["last"] = None
    return rec


def _own_error(e: Exception) -> str:
    """An adapter's refusal to build a line, when the words are its own (a
    ConfigUnaccounted, or since M17 a LaunchRefused, which names a flag and
    never its value); otherwise only the class."""
    try:
        from adapters.codex import ConfigUnaccounted
        from launch_extras import LaunchRefused
        if isinstance(e, (ConfigUnaccounted, LaunchRefused)):
            from speech_text import safe_for_terminal
            return safe_for_terminal(str(e))[:400]
    except Exception:                   # noqa: BLE001
        pass
    return f"the command line could not be built ({type(e).__name__})"


def write(records: dict) -> None:
    """{agent id: record} plus who wrote it, 0600, replaced atomically."""
    target = path()
    body = {"daemon_pid": os.getpid(), "at": round(time.time(), 3), "agents": records}
    try:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = target.with_name(f".runinfo.{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0),
                     0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(body, f)
        os.replace(tmp, target)
    except OSError:
        pass


def read() -> dict:
    """The published file, or {} when it is missing, odd, or not from the
    daemon running now (a file left by a daemon that died says nothing true)."""
    try:
        fd = os.open(path(), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return {}
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > 2 * 1024 * 1024:
            return {}
        data = json.loads(os.read(fd, st.st_size + 1))
    except (OSError, ValueError, RecursionError):
        return {}
    finally:
        os.close(fd)
    if not isinstance(data, dict) or not isinstance(data.get("agents"), dict):
        return {}
    return data if _daemon_alive(data.get("daemon_pid")) else {}


def _service_pid() -> int | None:
    """The daemon's pid, from its pidfile, when that process is alive."""
    from paths import RUNTIME_DIR
    try:
        pid = int((RUNTIME_DIR / "pid").read_text().strip())
        if pid <= 0:
            return None
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def _daemon_alive(pid) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    return _service_pid() == pid


# --- the page's view -------------------------------------------------------------------

#: How a decision was reached, as the page says it (audit.HOWS).
HOW_WORDS = {"asked": "you were asked", "unanswered": "nobody answered",
             "refused": "without asking", "level": "by its level",
             "chat": "by “allow all in this chat”", "failed": "the hook failed"}

#: How much of the end of each audit file a read looks at: the page wants
#: the newest few, and parsing two full megabytes every five seconds cost
#: 87 ms a read (FINDINGS §50).
TAIL_BYTES = 256 * 1024


def _tail(path: Path, max_bytes: int = TAIL_BYTES) -> list[str]:
    """The whole lines in the last `max_bytes` of a regular file, oldest first."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK)
    except OSError:
        return []
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return []
        start = max(0, st.st_size - max_bytes)
        os.lseek(fd, start, os.SEEK_SET)
        data = os.read(fd, st.st_size - start)
    except OSError:
        return []
    finally:
        os.close(fd)
    lines = data.decode("utf-8", errors="replace").splitlines()
    return lines[1:] if start > 0 and lines else lines


def decisions(agent_id: str, limit: int = 20) -> list[dict]:
    """The newest permission decisions for this agent, newest first, from
    the end of the audit log and then of its one archive."""
    import audit
    out = []
    for p in (audit.log_path(), audit.log_path().with_name("audit.log.1")):
        for raw in reversed(_tail(p)):
            if '"permission"' not in raw:
                continue
            try:
                line = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(line, dict) or line.get("kind") != "permission" \
                    or line.get("from") != agent_id:
                continue
            out.append({"at": line.get("at"), "tool": str(line.get("tool") or "?"),
                        "decision": str(line.get("decision") or "?"),
                        "how": str(line.get("how") or ""),
                        "how_words": HOW_WORDS.get(str(line.get("how") or ""), ""),
                        "level": str(line.get("level") or "")})
            if len(out) >= limit:
                return out
    return out


def view(agent_id: str, cfg) -> dict:
    """Everything Advanced shows for `agent_id` ("main" or an agent's id)."""
    import tooldetect
    me = agent_id if agent_id == "main" else _agent_key(agent_id)
    if me == "?":
        raise ValueError(f"no agent {agent_id!r}")
    if me != "main" and cfg.agent_by_id(me) is None:
        raise ValueError(f"no agent {agent_id!r} in the settings")
    published = read()
    rec = (published.get("agents") or {}).get(me) if published else None
    out: dict = {"agent": me, "daemon": bool(published), "service": _service_pid() is not None,
                 "published_at": published.get("at") if published else None}
    if isinstance(rec, dict):
        out.update({k: rec.get(k) for k in ("program", "state", "busy", "cwd", "prompt_channel",
                                            "session", "timeouts", "endpoint", "error",
                                            "last", "log")})
        argv = rec.get("argv")
        out["argv"] = argv if isinstance(argv, list) else None
        out["line"] = shown_line(argv) if isinstance(argv, list) else ""
        last = rec.get("last")
        if isinstance(last, dict) and isinstance(last.get("argv"), list):
            out["last"] = {**last, "line": shown_line(last["argv"])}
            out["last_same"] = last["argv"] == argv
        handed = rec.get("handed") if isinstance(rec.get("handed"), list) else []
    else:
        out.update({"argv": None, "line": "", "last": None, "log": [], "session": None,
                    "timeouts": None, "error": ""})
        handed = []
    if not out.get("program"):
        out["program"] = _program(me, cfg)
    seen_raw = tooldetect.read_live().get(me) or {}
    seen = {s["name"]: s.get("status", "") for s in (seen_raw.get("servers") or [])
            if isinstance(s, dict) and isinstance(s.get("name"), str)}
    servers = []
    for s in handed:
        name = s.get("name", "")
        servers.append({"name": name, "source": s.get("source", ""),
                        "given": "on" if s.get("on") else "off",
                        "seen": seen.pop(name, "")})
    for name, status in sorted(seen.items()):
        # Said it started, and not among what this agent is given now: a
        # switch turned off since the process started, or a server of the
        # CLI's own (Claude Code's built-ins). Shown, never hidden.
        servers.append({"name": name, "source": "seen",
                        "given": "not now" if isinstance(rec, dict) else "", "seen": status})
    out["servers"] = servers
    out["reports_seen"] = out.get("program") == "claude"
    out["decisions"] = decisions(me)
    return out


def _program(me: str, cfg) -> str:
    try:
        from agentfs import program_of
        return program_of(me, cfg)
    except Exception:                   # noqa: BLE001
        return ""


NOT_RUNNING = "Agent Voice is not running, so nothing is launched."
NOT_PUBLISHED = ("The running service has not said what it launches: it is starting, or it is "
                 "an older build than this page.")


def text(v: dict) -> str:
    """The view as lines for a terminal."""
    from speech_text import safe_for_terminal as safe
    lines = [f"{v['agent']} · {v.get('program') or 'no program'}"]
    if not v.get("daemon"):
        lines.append(NOT_PUBLISHED if v.get("service") else NOT_RUNNING)
    if v.get("error"):
        lines.append(f"next turn: {v['error']}")
    elif v.get("line"):
        lines.append("next launch: " + v["line"])
    elif v.get("endpoint"):
        e = v["endpoint"]
        lines.append(f"no process: each turn is an HTTPS request to {e.get('host')} ({e.get('model')})")
    last = v.get("last")
    if last:
        lines.append(f"last launch (pid {last.get('pid')}, "
                     f"{'running' if last.get('running') else 'ended'}): {last.get('line', '')}")
    if v.get("cwd"):
        lines.append(f"working directory: {v['cwd']}")
    sess = v.get("session") or {}
    if sess:
        lines.append(f"session: {sess.get('id') or 'none yet'}"
                     f" · {'resumes' if sess.get('resumes') else 'starts fresh'}"
                     f" · {sess.get('turns', 0)} turns here")
    for s in v.get("servers") or []:
        lines.append(f"  server {s['name']} [{s['source']}] given {s['given'] or 'unknown'}"
                     + (f", started: {s['seen']}" if s.get("seen") else ""))
    for line in v.get("log") or []:
        lines.append(f"  log {time.strftime('%H:%M:%S', time.localtime(line.get('at') or 0))} "
                     f"{line.get('text', '')}")
    for d in v.get("decisions") or []:
        lines.append(f"  decision {time.strftime('%H:%M:%S', time.localtime(d.get('at') or 0))} "
                     f"{d['tool']} {d['decision']} ({d['how_words'] or d['how']}, {d['level']})")
    return safe("\n".join(lines))


def cli(agent_id: str, as_json: bool) -> int:
    from runtime import Config
    try:
        v = view(agent_id, Config())
    except ValueError as e:
        print(f"agentvoice agents: {e}", file=sys.stderr)
        return 1
    print(json.dumps(v) if as_json else text(v))
    return 0
