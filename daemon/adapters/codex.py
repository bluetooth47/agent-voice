"""Codex CLI, headless, via `codex exec --json`.

Verified against a signed-in CLI (codex-cli 0.154.0, gpt-5.6-terra) on
2026-09-22. A whole turn is four lines of newline-delimited JSON:

    {"type": "thread.started", "thread_id": "01a0cc69-..."}
    {"type": "turn.started"}
    {"type": "item.completed", "item": {"id": ..., "type": "agent_message",
                                        "text": "A wake word is ..."}}
    {"type": "turn.completed", "usage": {...}}

Assistant text arrives whole, on `item.completed` with `item.type` of
`agent_message` -- not as deltas, so there is no partial-token stream to
regroup here the way the Claude adapter does. `thread_id` is the handle
`codex exec resume` takes, and it really does carry context: a second turn
recalled a number from the first.

Text extraction stays structural rather than keyed to that one event name.
The guess turned out right, but it was a guess when written, and the cost of
being wrong -- an adapter that looks correct and silently yields nothing -- is
worse than the cost of walking a few extra keys.

One trap worth recording: `codex exec` reads additional input from stdin and
will block forever waiting for it. A turn left to inherit a terminal hangs
with no output at all, which is why send() passes stdin=DEVNULL.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
from pathlib import Path
from typing import Any, Iterator

from .base import (
    Adapter, Chunk, Drain, Watchdog, feed, installed,
    stop_tree,
)

# Keys that have carried assistant text in this family of protocols. Checked
# in order; the first non-empty string wins.
_TEXT_KEYS = ("text", "delta", "content", "message")

#: Item types that are not the answer. Where the text lives stays structural
#: -- see the module docstring -- but not every item is something to say out
#: loud: `reasoning` is the model thinking, and a plan or a todo list is
#: scaffolding. Spoken, they came out as the assistant talking to itself.
_NOT_SPEECH = frozenset({
    "error", "reasoning", "reasoning_summary", "todo_list", "plan",
    "web_search", "file_change", "patch_apply", "mcp_tool_call",
})


#: Item types that are something the agent did, for progress talk.
_ACTIVITY = frozenset({"command_execution", "file_change", "web_search",
                       "mcp_tool_call", "patch_apply"})


def activity_chunks(kind: str, item: dict, started: set[str]) -> list[Chunk]:
    """Progress-talk chunks for one `item.*` event.

    The activity is announced once per item, on whichever event arrives
    first (a file change has only `item.completed`), and its end on
    `item.completed`. `started` holds the ids already announced, for the
    turn. Separate from send() so the narration replay goes through it.
    """
    itype = str(item.get("type", ""))
    if itype not in _ACTIVITY:
        return []
    item_id = str(item.get("id") or "")
    out = []
    if item_id:
        new = item_id not in started
        started.add(item_id)
    else:
        # No id to match on: announced where it begins.
        new = kind == "item.started" or itype in ("file_change", "patch_apply")
    if new:
        name = "file_change" if itype == "patch_apply" else itype
        out.append(Chunk(activity={"name": name, "input": item,
                                   "id": item_id, "helper": False}))
    if kind == "item.completed" and item_id:
        out.append(Chunk(tool_done=item_id))
    return out


def _harvest_text(node: Any, depth: int = 0) -> str:
    """Pull assistant text out of an item of unknown shape."""
    if depth > 4:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(_harvest_text(x, depth + 1) for x in node)
    if isinstance(node, dict):
        for key in _TEXT_KEYS:
            if key in node:
                found = _harvest_text(node[key], depth + 1)
                if found:
                    return found
    return ""


def _codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


_CACHE: dict = {}


def codex_models() -> list[dict]:
    """The models Codex itself offers, from the list it caches.

    Codex fetches its model list from the server and keeps it in
    models_cache.json, which is the only place the names that work for this
    account are written down -- they change every few months, and a list
    typed in here would be stale by the next release. The ones Codex hides
    from its own picker (review models, retired ones) are left out.
    """
    path = _codex_home() / "models_cache.json"
    try:
        stamp = path.stat().st_mtime_ns
        if _CACHE.get("stamp") == (str(path), stamp):
            return _CACHE["models"]
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    out = []
    for m in data.get("models") or []:
        if not isinstance(m, dict) or not m.get("slug"):
            continue
        if m.get("visibility", "list") != "list":
            continue
        out.append(m)
    out.sort(key=lambda m: m.get("priority", 999))
    # Read once per change: it is 600KB, and the settings ask often.
    _CACHE.update(stamp=(str(path), stamp), models=out)
    return out


class ConfigUnaccounted(Exception):
    """Codex's config.toml exists but cannot be read whole (phase M10)."""


#: How much of config.toml is read, and how many servers it may name.
#: Past either, the file is not accounted for and no turn starts.
CONFIG_MAX = 4 * 1024 * 1024
CONFIG_SERVERS_MAX = 1000


def config_servers() -> dict | None:
    """The MCP servers in Codex's own config.toml, name -> definition, read
    now, every one of them (_argv decides what to do with a name `-c` cannot
    carry). No file is no servers. A file
    that is there but cannot be read whole -- too large, too many servers,
    not TOML, unreadable -- is None: some of its servers could not be named,
    so the caller does not start Codex (Codex review of M10)."""
    import re
    import tomllib
    try:
        with open(_codex_home() / "config.toml", "rb") as f:
            data = f.read(CONFIG_MAX + 1)
    except FileNotFoundError:
        return {}
    except OSError:
        return None
    if len(data) > CONFIG_MAX:
        return None
    try:
        table = tomllib.loads(data.decode("utf-8")).get("mcp_servers", {})
    except (ValueError, UnicodeDecodeError, RecursionError):
        return None
    if not isinstance(table, dict) or len(table) > CONFIG_SERVERS_MAX:
        return None
    return {n: spec for n, spec in sorted(table.items()) if isinstance(n, str) and isinstance(spec, dict)}


def codex_default_model() -> str:
    """The model in Codex's own config.toml, which it uses when given none."""
    try:
        import tomllib
        with open(_codex_home() / "config.toml", "rb") as f:
            return str(tomllib.load(f).get("model") or "")
    except (OSError, ValueError):
        return ""


class Codex(Adapter):
    name = "codex"
    remembers = True          # resume <thread_id>, verified across two turns
    # `resume <id>` with and without --approve-for-me and another -m, both
    # ways, recalled a marker from the first turn: recorded against 0.171.0
    # in tests/fixtures/resume/codex-level-and-model.json (M2). A model
    # change makes Codex emit an `error` item (a warning that the session was
    # recorded with another model) and then answer normally.
    carries_session_across = frozenset({"level", "model"})

    # Codex's own spelling of "do not stop to ask", as used by omarchy-agent.
    def __init__(self, model: str | None = None, spoken: bool = True,
                 cwd: str | None = None, full_auto: bool | None = None,
                 ask_permission: bool = True, effort: str | None = None,
                 named: str = ""):
        self.model = model
        #: Which extra agent this is, so a question the desktop tools put on
        #: screen is filed as that agent's. Empty for the main agent.
        self.named = named
        #: Agent Voice's desktop tools (plan 12a), set by the daemon from
        #: desktopTools exactly as for Claude.
        self.desktop_tools = False
        #: The notes tools (crew_mcp.py, Phase 14): always, since Codex can
        #: take an MCP server; guarded on this agent's own level.
        self.crew_tools = True
        #: The servers in Codex's own config.toml this agent is switched on
        #: for (phase M10): name -> the digest of the definition approved
        #: (tooldetect.spec_digest), set by the daemon. Every other server
        #: there, and one whose definition no longer matches, is started
        #: with enabled=false: see _argv.
        self.mcp_on: dict = {}
        self.effort = effort
        self.spoken = spoken
        self.cwd = cwd
        # --approve-for-me is Codex's unattended mode. Without it Codex uses
        # its own default, which asks -- and with no terminal to ask in, a
        # turn that needs approval stalls until the adapter is cancelled.
        # That fails closed, which is the right direction. The flag itself is
        # read off `--help` rather than observed, which is a hypothesis and
        # not a contract -- unlike the event envelope below, which was
        # recorded from a real turn.
        self.full_auto = (not ask_permission) if full_auto is None else full_auto
        #: What it was asked for, kept as given: the daemon's reconcile_agent
        #: compares this to decide whether a refresh may keep the adapter.
        #: Without it every idle refresh rebuilt a Codex main agent and threw
        #: away its conversation (found in Phase 8, fixed in Phase 9).
        self.ask_permission = ask_permission
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def available(self) -> bool:
        """Installed AND signed in.

        An unauthenticated Codex reaches `thread.started` and then 401s five
        times per transport before failing the turn, so it would narrate an
        auth error rather than answer. Absent is the more useful verdict:
        the loop falls back to echoing instead.
        """
        if not installed("codex"):
            return False
        home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        return (home / "auth.json").exists()

    def _argv(self, text: str, session_id: str | None) -> list[str]:
        argv = ["codex", "exec", "--json", "--skip-git-repo-check"]
        if getattr(self, "ephemeral", False):
            # A quiet side turn (Phase 16, ask_agent): no session file kept.
            argv.append("--ephemeral")
        if self.model:
            argv += ["-m", self.model]
        if self.effort and self.effort in self.efforts():
            argv += ["-c", f'model_reasoning_effort="{self.effort}"']
        if self.full_auto:
            argv.append("--approve-for-me")
        if self.desktop_tools:
            # Codex has no hook to ask through, so below "trusted" the server
            # asks itself (--guard); Codex's own approval is turned off for it
            # because in `exec` it cannot ask and refuses every change.
            from desktop_mcp import codex_config
            argv += codex_config(self.name, self.named, guard=not self.full_auto)
        servers = config_servers()
        if servers is None:
            # Its servers cannot all be named, so some would start with
            # their switch off: no turn rather than that (Codex review).
            raise ConfigUnaccounted(
                "Codex's config.toml cannot be read whole, so Agent Voice cannot switch its MCP "
                "servers off; Codex was not started. Make the file smaller, or fix it.")
        import re
        from tooldetect import spec_digest
        for name, spec in servers.items():
            if (self.mcp_on or {}).get(name) == spec_digest(spec):
                continue                    # switched on, as approved
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
                # `-c` cannot name it (a dotted path; quoting is refused
                # too, tried against 0.171.0), so Codex would start it with
                # its switch off: no turn until it is switched on or renamed
                # (Codex review of M10, pass 2).
                shown = name if re.fullmatch(r"[\w .:@+-]{1,64}", name) else "one of its servers"
                raise ConfigUnaccounted(
                    f"Codex's config.toml has a server Agent Voice cannot switch off ({shown}), "
                    f"so Codex was not started. Turn it on for this agent, or rename it.")
            # Found in the user's own config.toml and not switched on
            # for this agent, or changed since it was (phase M10):
            # Codex would start it otherwise. Read now, not from the
            # last scan, so a server added or rewritten since is off
            # from its first turn -- and only names that are there,
            # because naming one that is not stops Codex from starting
            # at all ("invalid transport"). Recorded in
            # tests/fixtures/tools/codex-mcp-enabled.json.
            argv += ["-c", f"mcp_servers.{name}.enabled=false"]
        if self.crew_tools:
            # Below Trusted the notes server asks for itself (--guard), on
            # Codex's own level, not on the desktop server's condition: with
            # desktopTools off a Codex agent below Trusted still gets it
            # (merged plan, Phase 8 corrections; A14-3).
            import crew_mcp
            argv += crew_mcp.codex_config(self.name, self.named, guard=not self.full_auto)
        # Every option goes BEFORE `resume`: the resume subcommand rejects
        # --approve-for-me ("unexpected argument"), which failed every turn
        # after the first for a trusted Codex agent. Checked against
        # codex-cli 0.170.0 on 2026-11-18, with -m and -c alike.
        if session_id:
            argv += ["resume", session_id]
        # The prompt is NOT appended: it goes to stdin, because argv is world
        # readable through /proc/<pid>/cmdline. `codex exec` with no trailing
        # prompt reads one from stdin -- verified against the real CLI.
        return argv

    @classmethod
    def models(cls) -> list[dict]:
        """Model choices for the settings: Codex's own list, best first."""
        out = []
        for m in codex_models():
            name = str(m.get("display_name") or m["slug"])
            about = str(m.get("description") or "").rstrip(".")
            out.append({"value": m["slug"],
                        "label": f"{name} — {about}" if about else name})
        return out

    def efforts(self) -> tuple[str, ...]:
        """The reasoning levels the model in force takes, from Codex's list.

        Its own default when none is chosen. A model the list does not know
        gets none: a level Codex would reject is worse than no slider.
        """
        want = (self.model or "").strip() or codex_default_model()
        for m in codex_models():
            if m["slug"] == want:
                return tuple(str(level["effort"]) for level in
                             m.get("supported_reasoning_levels") or []
                             if isinstance(level, dict) and level.get("effort"))
        return ()

    def why_unavailable(self) -> str:
        if not installed("codex"):
            return "codex is not installed"
        return "codex is not signed in — run: codex login"

    def send(self, text: str, session_id: str | None = None) -> Iterator[Chunk]:
        try:
            argv = self._argv(text, session_id)
        except ConfigUnaccounted as e:
            yield Chunk(error=str(e))
            return
        prompt = self.with_preamble(text)
        try:
            # stdin carries the prompt and is then closed. Closing was always
            # required -- `codex exec` otherwise waits on it ("Reading
            # additional input from stdin...") and never returns -- and the
            # prompt now rides the same channel rather than argv, which any
            # local account can read out of /proc.
            proc = subprocess.Popen(argv, cwd=self.cwd, stdin=subprocess.PIPE,
                                    start_new_session=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, bufsize=1)
        except OSError as e:
            yield Chunk(error=f"could not start codex: {e}")
            return
        feed(proc, prompt)

        # Drained in the background from here on: stderr is a 64KB pipe
        # and it is not read until stdout ends, so a chatty CLI fills it,
        # blocks on its next write, and stops producing stdout -- which the
        # watchdog then reports as "stopped responding".
        errors = Drain(proc.stderr)

        with self._lock:
            self._proc = proc
        dog = Watchdog(proc, self.idle_timeout_s)
        #: For the daemon to poke while a tool call of this turn waits on it
        #: (a collaboration question, Phase 16).
        self.watchdog = dog

        spoken_any = False
        incomplete = ""
        tools_seen: set[str] = set()
        started: set[str] = set()
        try:
            for line in proc.stdout:
                dog.poke()
                line = line.strip()
                if not line or not line.startswith("{"):
                    continue          # codex interleaves plain log lines
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                kind = msg.get("type", "")

                if kind == "thread.started":
                    yield Chunk(session_id=msg.get("thread_id"))

                elif kind == "error":
                    # Retry chatter is noisy but not terminal; only turn.failed
                    # ends the turn.
                    continue

                elif kind == "turn.failed":
                    err = (msg.get("error") or {}).get("message") or "codex turn failed"
                    yield Chunk(error=str(err))

                elif kind.startswith("item."):
                    item = msg.get("item") or msg
                    itype = str(item.get("type", ""))
                    yield from activity_chunks(kind, item, started)
                    if "tool" in itype or "command" in itype:
                        # Announced once, on whichever event arrives first.
                        if itype not in tools_seen:
                            tools_seen.add(itype)
                            yield Chunk(tool=item.get("name") or itype)
                        continue
                    if itype in _NOT_SPEECH:
                        continue
                    found = _harvest_text(item)
                    if not found.strip():
                        continue
                    # Only `item.completed`. `item.started` and `item.updated`
                    # carry the same item again as it grows, so harvesting all
                    # three said the answer two or three times over.
                    if kind == "item.completed":
                        spoken_any = True
                        yield Chunk(text=found)
                    else:
                        # Kept in case nothing ever completes. A silent turn is
                        # the one failure a voice interface cannot report.
                        incomplete = found

                elif kind == "turn.completed":
                    pass

            if not spoken_any and incomplete.strip():
                yield Chunk(text=incomplete)
                spoken_any = True

            code = proc.wait()
            if dog.fired:
                # Killed for going quiet. Indistinguishable from a cancel by
                # exit code alone, and silence is the one thing a voice
                # interface must never answer with.
                yield Chunk(error=f"codex stopped responding after "
                                  f"{dog.idle_s:.0f}s")
                return
            if code != 0 and not spoken_any and code not in (-15, 143, -9, 137):
                err = errors.text().splitlines()
                yield Chunk(error=(err[-1] if err else f"codex exited {code}"))
        finally:
            dog.stop()
            with self._lock:
                self._proc = None
            for stream in (proc.stdout, proc.stderr):
                try:
                    stream.close()
                except Exception:
                    pass

        yield Chunk(done=True)

    def cancel(self) -> None:
        with self._lock:
            proc = self._proc
        if proc and proc.poll() is None:
            stop_tree(proc, signal.SIGTERM)
