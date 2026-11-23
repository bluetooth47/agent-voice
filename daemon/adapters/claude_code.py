"""Claude Code, headless, streaming, with session resume.

One process carries the conversation from turn to turn, instead of one per
turn. Measured on the 2014 dev machine against `claude` 2.1.325 with Haiku:
a process started for the turn took ~1.0s to come up (MCP servers connected,
session loaded) and 2.3-2.5s to its first word; the same turn written to a
process that was already running reached its first word in 1.3-1.4s. That
second is dead air after every single thing anyone says, so it is worth the
~230MB a waiting process holds -- but only while it is likely to be used,
which is why it is started when the wake word fires and let go after a few
idle minutes rather than kept forever.
"""
from __future__ import annotations

import atexit
import json
import os
import queue
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
import weakref
from pathlib import Path
from typing import Iterator

from launch_extras import LaunchRefused

from .base import (
    Adapter, Chunk, Drain, SPOKEN_STYLE, Unprompted, Watchdog, installed,
    private_config_file, prompt_file, stop_tree,
)

#: Every tool. The hook's `matcher` is also the limit of what the permission
#: system can see, so naming the dangerous ones here put the rest outside it
#: entirely. Which tools are free is decided in permission_hook.py, where it
#: can be read, tested and said out loud -- see NO_EFFECT and READ_ONLY.
GUARDED_TOOLS = ".*"

#: Seconds a running claude waits for the next turn before it is let go.
#: Long enough to cover a conversation with pauses in it, short enough that
#: ~230MB is not held all afternoon on a machine that has 4GB.
KEEP_WARM_S = 300.0

#: Master plan M27: while the process still runs background work it
#: started (a command, a helper), the idle let-go above waits, up to this
#: long after its last turn ended. Letting it go kills that work.
BACKGROUND_KEEP_S = 1800.0

#: After a turn during which a background task finished, how long to wait
#: for the turn the CLI then takes by itself before deciding the reply
#: already covered it. Recorded: that turn starts within 0.1 s.
UNPROMPTED_GRACE_S = 5.0

#: The most of an unprompted turn's own words kept (base.Unprompted).
UNPROMPTED_TEXT_MAX = 8000

#: Exit statuses that mean we stopped it, not that it failed.
_STOPPED = (-15, 143, -9, 137)

#: Every level `claude --effort` accepts, lowest first (2.1.325's --help).
EFFORTS = ("low", "medium", "high", "xhigh", "max")

#: Names Claude Code resolves to a current model itself, every one of which
#: takes all five levels.
_CURRENT = {"default", "fable", "opus", "sonnet", "haiku", "opusplan"}

#: A full model id, wherever it sits: "claude-opus-4-6", the Bedrock
#: "us.anthropic.claude-haiku-5-5", the dated "claude-opus-4-5-20251101" and
#: Vertex's "claude-opus-4-5@20251101". The minor version is one or two
#: digits so a date is never read as one.
_MODEL_ID = re.compile(r"claude-(fable|mythos|opus|sonnet|haiku)-(\d+)(?:-(\d{1,2}))?(?!\d)")


def _default_model() -> str:
    """What `claude` runs with no --model: the environment, then settings."""
    value = os.environ.get("ANTHROPIC_MODEL", "").strip()
    if value:
        return value
    home = os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude"
    try:
        value = json.loads((Path(home) / "settings.json").read_text()).get("model")
    except (OSError, ValueError, AttributeError):
        return ""
    return value.strip() if isinstance(value, str) else ""


def effort_levels(model: str | None) -> tuple[str, ...]:
    """The effort levels `model` takes, or none.

    The CLI does not check: `--effort max` with a model that has no effort
    parameter is accepted and the turn runs, so whether the slider means
    anything has to be worked out here. From Anthropic's model table: every
    current model takes all five; xhigh arrived with Opus 4.7, so Opus and
    Sonnet 4.6 stop at four; Opus 4.5 has three; Sonnet 4.5, Haiku 4.5 and
    everything older have none. A name nothing here recognises gets no
    slider -- a level silently dropped is worse than no level offered.
    """
    name = (model or "").strip().lower() or _default_model().lower() or "default"
    if name.split("[", 1)[0] in _CURRENT:
        return EFFORTS
    found = _MODEL_ID.search(name)
    if not found:
        return ()
    family = found.group(1)
    version = (int(found.group(2)), int(found.group(3) or 0))
    if family in ("fable", "mythos"):
        return EFFORTS
    if family == "opus":
        if version >= (4, 7):
            return EFFORTS
        if version == (4, 6):
            return ("low", "medium", "high", "max")
        if version == (4, 5):
            return ("low", "medium", "high")
        return ()
    if family == "sonnet":
        if version >= (5, 0):
            return EFFORTS
        if version == (4, 6):
            return ("low", "medium", "high", "max")
        return ()
    return EFFORTS if version >= (5, 0) else ()     # haiku

#: Every adapter that may own a process, so one left waiting is not orphaned
#: when the daemon is run in a terminal and stopped with ctrl-c. Under systemd
#: the unit's cgroup is killed whole and this is belt and braces.
_LIVE: "weakref.WeakSet[ClaudeCode]" = weakref.WeakSet()


@atexit.register
def _stop_all() -> None:
    for adapter in list(_LIVE):
        try:
            adapter.cancel()
        except Exception:
            pass


def _write_turn(proc, text: str) -> bool:
    """Hand one turn to a running claude on stdin. False if it has gone.

    stdin, never argv: `/proc/<pid>/cmdline` is world readable on an ordinary
    Linux box, so a prompt passed as an argument is readable by every local
    account for as long as the process lives -- and this process now lives
    for minutes, not for one turn. The stream-json input protocol is one JSON
    object per line, and stdin stays open between turns, which is what keeps
    the process alive to take the next one.
    """
    line = json.dumps({"type": "user",
                       "message": {"role": "user", "content": text},
                       "parent_tool_use_id": None, "session_id": ""})
    try:
        proc.stdin.write(line + "\n")
        proc.stdin.flush()
        return True
    except (OSError, ValueError, AttributeError):
        return False


def parse_line(msg: dict) -> list[Chunk]:
    """The chunks one stream-json line carries, apart from `result`.

    Separate from send() so the narration replay reads a recorded turn
    through exactly the code a live one goes through.
    """
    kind = msg.get("type")
    if kind == "system" and msg.get("subtype") == "init":
        return [Chunk(session_id=msg.get("session_id"))]
    if kind == "stream_event":
        event = msg.get("event") or {}
        etype = event.get("type")
        if etype == "message_start":
            if msg.get("ttft_ms") is not None:
                return [Chunk(ttft_ms=msg["ttft_ms"])]
        elif etype == "content_block_delta":
            delta = event.get("delta") or {}
            if delta.get("type") == "text_delta":
                return [Chunk(text=delta.get("text", ""))]
        elif etype == "content_block_start":
            block = event.get("content_block") or {}
            if block.get("type") == "tool_use":
                return [Chunk(tool=block.get("name"))]
        return []
    # The whole message, once a block is complete: the only place a tool's
    # arguments arrive in one piece (the stream sends them as JSON
    # fragments). A subagent's messages carry the id of the Task that
    # started it, and stream no deltas of their own.
    if kind == "assistant":
        helper = bool(msg.get("parent_tool_use_id"))
        out = []
        for block in (msg.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                out.append(Chunk(activity={
                    "name": str(block.get("name") or ""),
                    "input": block.get("input") if isinstance(block.get("input"), dict) else {},
                    "id": str(block.get("id") or ""),
                    "helper": helper}))
        return out
    if kind == "user":
        content = (msg.get("message") or {}).get("content")
        if isinstance(content, list):
            return [Chunk(tool_done=str(b.get("tool_use_id") or ""))
                    for b in content
                    if isinstance(b, dict) and b.get("type") == "tool_result"]
    return []


# --- what a warm claude says between turns (master plan M27) -----------------

_TASK_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _top(msg: dict) -> bool:
    """A line of the conversation itself, not of a helper (a subagent's
    messages carry the id of the tool call that started it)."""
    return not msg.get("parent_tool_use_id")


def is_echo(msg: dict) -> bool:
    """Our own turn coming back (--replay-user-messages): the user message
    written on stdin, echoed when the CLI starts the turn for it -- recorded
    after that turn's init and before its first words. Only what was written
    to stdin is echoed, so a turn the CLI takes by itself has none."""
    return msg.get("type") == "user" and msg.get("isReplay") is True and _top(msg)


class Between:
    """The background work one claude process started, and the turns it
    takes by itself when that work finishes (tests/fixtures/background/).

    `track` sees every line the process writes, in a turn of ours or not:
    `task_started` with `is_backgrounded` (not a helper's own) starts a task;
    `background_tasks_changed` says which still run; `task_notification`
    for one of ours, completed or failed, is a finish. Only those finishes,
    the CLI's own job tracking, start an announcement: a turn the CLI takes
    with none before it is read off the stream and dropped -- a model writing
    "done" is text, not an event.

    `feed` reads a turn that is not ours (`foreign`), collecting its own
    top-level words; at its `result` it hands back the Unprompted to say.
    Not thread-safe by itself: one reader at a time (the pump's lock)."""

    def __init__(self) -> None:
        #: Task id -> True: backgrounded by a turn of this process, not ended.
        self.started: dict[str, bool] = {}
        #: What `background_tasks_changed` last said still runs.
        self.running: set[str] = set()
        #: [task id, status, when read, whether a turn of ours began since].
        self.finished: list[list] = []
        #: A turn that is not ours is under way.
        self.auto = False
        self.text: list[str] = []
        self._size = 0

    @property
    def outstanding(self) -> bool:
        return bool(self.started or self.running)

    @property
    def foreign(self) -> bool:
        """A turn that is not ours is due (a finish read) or under way."""
        return bool(self.finished) or self.auto

    def track(self, msg: dict) -> None:
        if msg.get("type") != "system":
            return
        sub, tid = msg.get("subtype"), msg.get("task_id")
        ours = isinstance(tid, str) and bool(_TASK_ID.fullmatch(tid))
        if sub == "task_started":
            if ours and msg.get("is_backgrounded") is True and not msg.get("owned_by_subagent"):
                self.started[tid] = True
        elif sub == "task_updated":
            patch = msg.get("patch") if isinstance(msg.get("patch"), dict) else {}
            # A command moved to the background after it started.
            if ours and patch.get("is_backgrounded") is True and not msg.get("owned_by_subagent"):
                self.started[tid] = True
        elif sub == "background_tasks_changed":
            tasks = msg.get("tasks")
            if isinstance(tasks, list):
                self.running = {t["task_id"] for t in tasks
                                if isinstance(t, dict) and isinstance(t.get("task_id"), str)}
        elif sub == "task_notification" and ours and tid in self.started:
            # Taken off as it is read: the same finish reported twice -- or
            # replayed -- is one finish.
            del self.started[tid]
            self.running.discard(tid)
            status = msg.get("status")
            if status in ("completed", "failed"):
                self.finished.append([tid, status, time.time(), False])
            # "killed", "stopped": ended on purpose, by the agent or by us.

    def turn_began(self) -> None:
        """Our echo arrived: a turn of ours is under way, and may answer for
        the finishes read so far (the CLI may fold one into it). Each now
        waits for a turn of its own after ours, or for UNPROMPTED_GRACE_S."""
        for f in self.finished:
            f[3] = True
        self.auto, self.text, self._size = False, [], 0

    def forget_covered(self) -> None:
        """Before a new turn of ours: a finish a turn of ours already began
        on, whose own turn never came, was answered there."""
        self.finished = [f for f in self.finished if not f[3]]

    def feed(self, msg: dict) -> Unprompted | None:
        """One line of a turn that is not ours. At its end, what to say if a
        finish came before it, else None."""
        kind = msg.get("type")
        if kind == "result":
            out = None
            if self.finished:
                out = Unprompted(
                    tasks=tuple((f[0], f[1]) for f in self.finished),
                    text=" ".join(self.text).strip()[:UNPROMPTED_TEXT_MAX],
                    session=msg.get("session_id") if isinstance(msg.get("session_id"), str) else None,
                    finished=min(f[2] for f in self.finished),
                    failed=any(f[1] == "failed" for f in self.finished) or bool(msg.get("is_error")))
            self.finished, self.auto, self.text, self._size = [], False, [], 0
            return out
        if kind == "system" and msg.get("subtype") == "init":
            self.auto = True
        elif kind in ("stream_event", "assistant") and _top(msg):
            self.auto = True
            if kind == "assistant":
                for block in (msg.get("message") or {}).get("content") or []:
                    if (isinstance(block, dict) and block.get("type") == "text"
                            and isinstance(block.get("text"), str)
                            and self._size < UNPROMPTED_TEXT_MAX):
                        self.text.append(block["text"])
                        self._size += len(block["text"])
        return None

    def settle(self, now: float) -> Unprompted | None:
        """With no turn under way, finishes whose own turn never started
        within the grace: one a turn of ours began on was answered there and
        is dropped; one read between turns is said with no words of its own."""
        if self.auto:
            return None
        due = [f for f in self.finished if now - f[2] >= UNPROMPTED_GRACE_S]
        if not due:
            return None
        self.finished = [f for f in self.finished if f not in due]
        said = [f for f in due if not f[3]]
        if not said:
            return None
        return Unprompted(tasks=tuple((f[0], f[1]) for f in said), text="",
                          finished=min(f[2] for f in said),
                          failed=any(f[1] == "failed" for f in said))


def _parse(raw: str) -> dict | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return msg if isinstance(msg, dict) else None


class Pump:
    """Every line one running claude writes, read on one thread for as long
    as it lives (master plan M27).

    A warm process is not quiet between turns: when a background task it
    started finishes, the CLI says so and takes a turn by itself, `result`
    and all (recorded). Before M27 nothing read stdout between turns, so that
    turn waited in the pipe and the next turn's reading took its `result`
    for its own: the person heard the background report as the answer to
    their new question, and the real answer a turn late. Now one thread
    reads everything. While a turn is registered (`begin`) its lines go to
    that turn's queue, in order; otherwise they are Between's to read. Started
    by the first turn, so nothing a turn is owed is read before it asks."""

    def __init__(self, proc, bg: Between, hand) -> None:
        self.proc, self.bg, self.hand = proc, bg, hand
        self.lock = threading.Lock()
        self.turn: queue.Queue | None = None
        self.ended = False
        self.thread: threading.Thread | None = None

    def begin(self) -> "queue.Queue":
        q: queue.Queue = queue.Queue()
        with self.lock:
            self.turn = q
            if self.ended:
                q.put(None)
            self.bg.forget_covered()
            if self.thread is None:
                self.thread = threading.Thread(target=self._run, name="claude-stdout",
                                               daemon=True)
                self.thread.start()
        return q

    def end(self, q) -> None:
        """The turn read its `result`: what is already queued behind it is a
        turn the CLI took by itself, read now, in order, under the lock."""
        with self.lock:
            if self.turn is q:
                self.turn = None
            while True:
                try:
                    raw = q.get_nowait()
                except queue.Empty:
                    break
                if raw is None:
                    break
                self._between(raw)
            waiting = bool(self.bg.finished)
        if waiting:
            self._settle_later()

    def _run(self) -> None:
        try:
            out = self.proc.stdout
            while True:
                raw = out.readline()
                if not raw:
                    break
                with self.lock:
                    if self.turn is not None:
                        self.turn.put(raw)
                        continue
                    self._between(raw)
                    waiting = bool(self.bg.finished) and not self.bg.auto
                if waiting:
                    self._settle_later()
        except (OSError, ValueError, AttributeError):
            pass
        finally:
            with self.lock:
                self.ended = True
                if self.turn is not None:
                    self.turn.put(None)

    def _between(self, raw: str) -> None:
        """Locked."""
        msg = _parse(raw)
        if msg is None:
            return
        self.bg.track(msg)
        out = self.bg.feed(msg)
        if out is not None:
            self.hand(out)

    def _settle_later(self) -> None:
        t = threading.Timer(UNPROMPTED_GRACE_S + 0.1, self.settle)
        t.daemon = True
        t.start()

    def settle(self, now: float | None = None) -> None:
        with self.lock:
            if self.turn is not None:
                return
            out = self.bg.settle(time.time() if now is None else now)
        if out is not None:
            self.hand(out)


class ClaudeCode(Adapter):
    #: It loads the Omarchy skill itself, from --plugin-dir.
    takes_skill_text = False
    name = "claude"
    guards_permissions = True
    remembers = True          # one process per conversation, --resume after
    # --resume under the other level's hook settings and another --model,
    # both ways, recalled a marker from the first turn: recorded against
    # 2.1.330 in tests/fixtures/resume/claude-level-and-model.json (M2).
    carries_session_across = frozenset({"level", "model"})
    # The only backend with somewhere to put the question: a PreToolUse hook
    # receives the pending call and blocks on the verdict, so "edits" can be
    # decided per call against the project path.
    levels = ("ask", "edits", "trusted")

    # `auto` is the mode Omarchy's own `omarchy agent` uses for unattended
    # launches, and the one this runs in: the question is answered by the
    # PreToolUse hook and the overlay, not by Claude's own prompt, which has
    # no terminal to appear in. A mode that can block would simply hang.
    def __init__(self, model: str | None = None,
                 effort: str | None = None,
                 permission_mode: str = "auto",
                 cwd: str | None = None,
                 spoken: bool = True,
                 ask_permission: bool = True,
                 keep_warm_s: float = KEEP_WARM_S,
                 named: str = ""):
        self.model = model
        #: The extra agent this is, by the name that wakes it, or "" for the
        #: main one. Handed to the permission hook, which reads that agent's
        #: own level and folder rather than the main agent's.
        self.named = named
        #: Plan 12a and 12b, set by the daemon from desktopTools and
        #: omarchySkill. Both are read when the process starts.
        self.desktop_tools = False
        #: Agent Voice's own tools for agents (crew_mcp.py: notes, from
        #: Phase 14), attached whenever this program can take them, whatever
        #: desktopTools says (merged plan, section 3.7).
        self.crew_tools = True
        self.skill_dir: str | None = None
        #: Claude in Chrome (plan 12d), from browserTools.
        self.browser_tools = False
        #: The MCP servers found on this machine that this agent is switched
        #: on for (phase M10): {name in the config: definition}, set by the
        #: daemon from tooldetect.delivery. Read when the process starts.
        self.detected_servers: dict = {}
        #: The CLIs found here and switched off for it: refused by a deny
        #: rule in the plain forms (`gh`, `gh pr list`, a path, a && chain),
        #: which `sh -c` gets past -- the reason the row says "told, not
        #: enforced" (tests/fixtures/tools/claude-deny-rules.json).
        self.clis_denied: tuple = ()
        #: The skills switched off for this agent where Claude Code looks
        #: (phase M11, skillscan.native_off): each named `off` in
        #: skillOverrides, so its Skill tool refuses it ("disabled for model
        #: invocation"). Never touches the agent's own `agentvoice:` copies:
        #: tests/fixtures/skills/spike-m11.json. Read when the process starts.
        self.skills_off: tuple = ()
        #: Why those could not be named, or "": then it is given no skill at
        #: all (--disable-slash-commands drops every one, recorded in
        #: FINDINGS §44), rather than ones nobody could switch off.
        self.skills_unknown: str = ""
        #: What the last process said it started, from its init event:
        #: [{"name", "status"}] (tooldetect.live_servers). For the Tools &
        #: skills tab and M16.
        self.live_servers: list | None = None
        #: Applied only when the model takes it: see efforts().
        self.effort = effort
        self.spoken = spoken
        self.ask_permission = ask_permission
        self.permission_mode = permission_mode
        self.cwd = cwd or os.getcwd()
        self.keep_warm_s = keep_warm_s
        #: The running claude, between turns as well as during one.
        self._proc: subprocess.Popen | None = None
        #: Its stderr, drained from the moment it starts. See Drain.
        self._errors: Drain | None = None
        #: The conversation that process is carrying: what it was resumed
        #: from, then whatever its last turn reported. A turn for any other
        #: conversation must not be written to it.
        self._holds: str | None = None
        #: True while a turn is being read from it, so the idle timer and
        #: prepare() cannot take it away mid-turn.
        self._busy = False
        self._expiry: threading.Timer | None = None
        # Reentrant, because cancel() is reached from a signal handler -- the
        # interrupt keybind -- which runs on the main thread, and the main
        # thread may be holding this when the signal lands.
        self._lock = threading.RLock()
        #: "warm" when the last turn found claude already running, "cold"
        #: when it had to be started for it. Said in the timing line, because
        #: it is the difference between the two numbers at the top of this file.
        self.last_start = ""
        #: Master plan M27: the running process's background work and the
        #: thread that reads its stdout, both made anew with each process.
        self._bg = Between()
        self._pump: Pump | None = None
        #: When its last turn ended: how long background work may hold it.
        self._idle_since = time.time()
        _LIVE.add(self)

    @classmethod
    def _hook_settings(cls, named: str = "", matcher: str = "", deny=(), skills_off=()) -> str:
        """A PreToolUse hook, passed inline as JSON.

        `--settings` takes a JSON string and loads it *in addition to* the
        user's own settings, so this adds the hook without disturbing anything
        they have configured.

        A hook rather than `--permission-prompt-tool`: that flag is accepted
        by the CLI and loads the MCP server, but is never consulted -- tested
        against 2.1.278 across every permission mode. Hooks fire in all of
        them, including `auto`, and with `--input-format stream-json` --
        tested against 2.1.325 with a hook that blocked a Bash call.
        """
        hook = Path(__file__).resolve().parent.parent / "permission_hook.py"
        # Quoted, because this string is run by a shell. A space anywhere in
        # the interpreter path or the plugin path -- and the plugin lives
        # under $HOME -- would split the command, give exit 127, and a hook
        # that cannot start is read by Claude Code as a non-blocking error:
        # the tool proceeds. Failing to quote here disables the guard.
        parts = [sys.executable, str(hook), cls.name]
        if named:
            parts.append(named)
        command = " ".join(shlex.quote(part) for part in parts)
        extra = {}
        if deny:
            # A CLI switched off (phase M10): its plain forms refused by
            # Claude Code itself, even when the hook answers allow. The
            # exact name and the name with arguments, never a ":*" prefix,
            # which could catch a longer name ("gh" and "ghc").
            extra["permissions"] = {"deny": [rule for name in deny
                                             for rule in (f"Bash({name})", f"Bash({name} *)")]}
        if skills_off:
            # The skills switched off for this agent (phase M11), merged by
            # Claude Code with the person's own skillOverrides; an unknown
            # name is ignored (recorded).
            extra["skillOverrides"] = {name: "off" for name in sorted(skills_off)}
        return json.dumps({**extra, "hooks": {"PreToolUse": [{
            "matcher": matcher or GUARDED_TOOLS,
            # ".*" -- every tool, with permission_hook.py deciding which ones
            # are free. A matcher that named the dangerous tools left every
            # other one outside the permission system altogether: `mcp__*`
            # from the user's own servers (send mail, post to Slack, write a
            # calendar), WebSearch, whose query *is* the exfiltration, Read
            # of any path at all, and Task. Meanwhile the settings screen
            # said "asks before every change".
            #
            # The cost is a process per tool call. The free tools return
            # before importing anything but json and os, which is where that
            # cost is paid back.
            # The agent's own name travels with the hook: permission levels
            # are per agent now, and the hook is a separate process that
            # cannot otherwise know which one spawned it.
            #
            # onFailure "block": a hook that cannot start, crashes or runs out
            # of time was otherwise read by Claude Code as a non-blocking
            # error, and the tool went ahead under Claude's own permission
            # flow (the Phase 13 open issue, raised again by Codex's review
            # of Phase 14 for the notes tools). Checked against 2.1.329 with
            # a real turn: a missing hook script let Bash run without it and
            # blocked it with it, and a hook answering allow still allowed.
            "hooks": [{"type": "command", "command": command, "onFailure": "block"}],
        }]}})

    def available(self) -> bool:
        return installed("claude")

    def _argv(self, text: str, session_id: str | None) -> list[str]:
        # No prompt here at all: turns arrive on stdin as stream-json, because
        # argv is world readable through /proc. `text` stays in the signature
        # so the test that hunts for a prompt in argv keeps asking the question.
        argv = [
            "claude", "-p",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--include-partial-messages",
            "--verbose",                      # stream-json requires it
            # Master plan M27: each turn written on stdin is echoed back as
            # the CLI starts it, which is how a turn of ours is told apart
            # from one the CLI takes by itself when background work ends
            # (recorded: tests/fixtures/background/claude-race.json).
            "--replay-user-messages",
            "--permission-mode", self.permission_mode,
            # Print mode leaves Claude in Chrome off even when it is the
            # default in the user's own settings, so it is asked for or
            # refused outright, from browserTools (plan 12d).
            "--chrome" if self.browser_tools and not self.no_tools else "--no-chrome",
        ]
        if self.no_tools:
            # Try it (phase M6): a sentence and nothing else. No built-in
            # tool, and no MCP server -- not even the user's own, which
            # `claude -p` otherwise loads from their settings.
            argv += ["--tools", ""]
        # Only the servers Agent Voice names, always (phase M10). Without
        # this `claude -p` also loads every server in the user's own
        # settings, every project's .mcp.json -- unapproved -- and every
        # plugin's, which made a switch saying "off" untrue. Recorded both
        # ways in tests/fixtures/tools/claude-strict-mcp.json.
        argv.append("--strict-mcp-config")
        if getattr(self, "ephemeral", False):
            # A quiet side turn (Phase 16, ask_agent): nothing kept on disk.
            argv.append("--no-session-persistence")
        head = self.preamble()
        if head == SPOKEN_STYLE:
            # A constant this file ships, so argv is no leak.
            argv += ["--append-system-prompt", SPOKEN_STYLE]
        elif head:
            # The user's own words: off argv, into a private file.
            argv += ["--append-system-prompt-file", prompt_file(head)]
        detected = {} if self.no_tools else dict(self.detected_servers or {})
        deny = () if self.no_tools else tuple(self.clis_denied or ())
        skills_off = () if self.no_tools else tuple(self.skills_off or ())
        if self.ask_permission:
            argv += ["--settings", self._hook_settings(self.named, deny=deny, skills_off=skills_off)]
        else:
            # Trusted, but a click in a signed-in browser can still buy or
            # post, and a write to the agents' orders (the communal rules,
            # skills, instructions, settings) is still asked: a hook on the
            # browser and the writing tools, not on reads.
            from permission_hook import BROWSER_MATCHER, TRUSTED_MATCHER
            matcher = TRUSTED_MATCHER if self.browser_tools else \
                TRUSTED_MATCHER[len(BROWSER_MATCHER) + 1:]
            if detected:
                # And the servers found on this machine (phase M10): not to
                # ask -- the hook allows them at Trusted -- but so a switch
                # turned off reaches this process at its next call, before
                # the idle process is let go.
                import re as _re
                matcher += "|" + "|".join(f"mcp__{_re.escape(k)}__.*" for k in sorted(detected))
            argv += ["--settings", self._hook_settings(self.named, matcher, deny=deny,
                                                       skills_off=skills_off)]
        servers: dict = {}
        if self.desktop_tools and not self.no_tools:
            # Agent Voice's desktop tools (plan 12a), as this agent: the
            # server files a screenshot question under the same id the hook
            # uses. Added to the user's own MCP servers, not instead of them.
            import desktop_mcp
            servers.update(desktop_mcp.servers(self.name, self.named))
        if self.crew_tools and not self.no_tools:
            # The notes tools (Phase 14), as this agent, on its own
            # condition: never the desktop tools'. One config for both.
            import crew_mcp
            servers.update(crew_mcp.servers(self.name, self.named, browser=self.browser_tools))
        for key, spec in sorted(detected.items()):
            # Found on this machine and switched on for this agent (M10),
            # as its own settings define it. Never one of ours by name.
            servers.setdefault(key, spec)
        if servers:
            # In a 0600 file, never inline: a detected server's definition
            # can carry an API key, and argv is world readable.
            argv += ["--mcp-config", private_config_file({"mcpServers": servers})]
        if self.skills_unknown and not self.no_tools:
            argv.append("--disable-slash-commands")
        if self.skill_dir and not self.no_tools:
            # The Omarchy skill (plan 12b), loaded as a plugin for this
            # process only: nothing is written into ~/.claude.
            argv += ["--plugin-dir", self.skill_dir]
        if session_id:
            argv += ["--resume", session_id]
        if self.model:
            argv += ["--model", self.model]
        if self.effort and self.effort in self.efforts():
            argv += ["--effort", self.effort]
        # Phase M17: the person's extra flags, checked here, at launch,
        # against what is never passed (launch_extras), so a setting written
        # past the page is refused when it would run. Last, so a flag that
        # wants a value can take none of ours: it gets nothing, and claude
        # says so instead of starting.
        argv += self._extras_argv()
        return argv

    def efforts(self) -> tuple[str, ...]:
        return effort_levels(self.model)

    #: Turns arrive as stream-json lines on stdin, which stays open between them.
    prompt_channel = "as stream-json lines on stdin, kept open between turns"

    def handed_servers(self) -> list[dict]:
        """What _argv hands this process (phase M16): the same conditions."""
        if self.no_tools:
            return []
        out = []
        if self.desktop_tools:
            out.append({"name": "agentvoice-desktop", "source": "agentvoice", "on": True})
        if self.crew_tools:
            out.append({"name": "agentvoice-crew", "source": "agentvoice", "on": True})
        for key in sorted(self.detected_servers or {}):
            out.append({"name": key, "source": "found", "on": True})
        if self.browser_tools:
            out.append({"name": "claude-in-chrome", "source": "browser", "on": True})
        return out

    # --- the process, kept between turns -----------------------------------

    def _ready_for(self, session_id: str | None) -> bool:
        """Whether the running process can take a turn in `session_id`."""
        return (self._proc is not None and self._proc.poll() is None
                and self._holds == session_id)

    def _spawn(self, session_id: str | None) -> subprocess.Popen:
        """Start claude, continuing `session_id` if there is one. Locked."""
        # The environment is inherited whole, including AGENTVOICE_ENDPOINT_KEY
        # and OPENAI_API_KEY, which any Bash command the agent runs can read.
        # Deliberately: Codex authenticates with OPENAI_API_KEY, so scrubbing
        # it here would break a backend to protect a key from an agent the
        # user is already trusting to run commands on their behalf. The key
        # that matters is not in the environment on this machine anyway --
        # endpoint_key() prefers the login keyring.
        argv = self._argv("", session_id)
        # Phase M17: its own environment variables on top of the daemon's,
        # checked like its flags; None when it has none, as before.
        env = self._popen_env()
        proc = subprocess.Popen(argv, cwd=self.cwd, env=env,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, bufsize=1,
                                start_new_session=True)
        # Drained in the background from here on: stderr is a 64KB pipe and
        # a process that lives for minutes has plenty of time to fill it,
        # block on its next write, and stop producing stdout -- which the
        # watchdog then reports as "stopped responding".
        self._errors = Drain(proc.stderr)
        self._proc, self._holds = proc, session_id
        # Master plan M27: this process's own background work, and the one
        # thread that will read everything it writes.
        self._bg = Between()
        self._pump = Pump(proc, self._bg, self._hand_unprompted)
        self._launched(argv, proc)          # phase M16: Agent details → Advanced
        return proc

    def _hand_unprompted(self, said: Unprompted) -> None:
        """Pass what the CLI said by itself to the daemon, on a thread of its
        own: the pump never waits on a listener."""
        listener = self.on_unprompted
        if listener is None:
            return
        threading.Thread(target=listener, args=(said,), name="claude-unprompted",
                         daemon=True).start()

    def background_running(self) -> bool:
        with self._lock:
            proc = self._proc
            return (proc is not None and proc.poll() is None and not self._busy
                    and self._bg.outstanding)

    def _forget(self) -> subprocess.Popen | None:
        """Let go of the running process and return it, to be stopped. Locked."""
        proc, self._proc, self._holds = self._proc, None, None
        if self._expiry is not None:
            self._expiry.cancel()
            self._expiry = None
        return proc

    def _arm_expiry(self) -> None:
        """Let go of an idle process after `keep_warm_s`. Locked."""
        if self._expiry is not None:
            self._expiry.cancel()
        proc = self._proc
        if proc is None or self.keep_warm_s <= 0:
            self._expiry = None
            return
        timer = threading.Timer(self.keep_warm_s, self._expire, args=(proc,))
        timer.daemon = True
        timer.start()
        self._expiry = timer

    def _expire(self, proc) -> None:
        with self._lock:
            if self._proc is not proc or self._busy:
                return
            if (self._bg.outstanding and proc.poll() is None
                    and time.time() - self._idle_since < BACKGROUND_KEEP_S):
                # Master plan M27: letting it go would kill the background
                # work it is still doing; asked again a while later.
                self._arm_expiry()
                return
            self._forget()
        stop_tree(proc, signal.SIGTERM)

    def prepare(self, session_id: str | None = None) -> None:
        """Start claude now, so the turn about to be spoken finds it running.

        Called when the wake word fires. The person then talks for a few
        seconds and Whisper takes another, which is far longer than the ~1s
        claude needs to start -- so by the time there is a prompt, there is a
        process waiting for it. Never raises: a process that cannot start
        here is started again by send(), which can say why out loud.
        """
        stale = None
        with self._lock:
            if self._busy:
                return
            if not self._ready_for(session_id):
                stale = self._forget()
                try:
                    self._spawn(session_id)
                except (OSError, LaunchRefused):
                    # Said by the turn's own send(), which reaches the same
                    # check. The process let go above is still stopped below:
                    # this returned past it before M17, and left it running.
                    pass
            self._arm_expiry()
        if stale is not None and stale.poll() is None:
            stop_tree(stale, signal.SIGTERM)

    def _take(self, session_id: str | None, *, fresh: bool = False):
        """The process this turn will use, started if need be, marked busy.

        Returns (proc, its Drain, a process to stop) or raises OSError. Never
        yields while holding the lock -- a generator suspended inside it would
        leave every other thread that reaches cancel() waiting on the turn.
        """
        with self._lock:
            if self._expiry is not None:
                self._expiry.cancel()
                self._expiry = None
            stale = None
            self.last_start = "warm"
            if fresh or not self._ready_for(session_id):
                stale = self._forget()
                self.last_start = "cold"
                try:
                    self._spawn(session_id)
                except BaseException:
                    # The one let go is not this turn's to keep, and nobody
                    # else holds it now (phase M17: a refused launch raises
                    # here as a failed start always could).
                    if stale is not None and stale.poll() is None:
                        stop_tree(stale, signal.SIGTERM)
                    raise
            self._busy = True
            return self._proc, self._errors, stale

    def _own(self, msg: dict) -> list[Chunk]:
        """The chunks of one line of our own turn."""
        if msg.get("type") == "system" and msg.get("subtype") == "init":
            # Which servers this process started (phase M10): names and
            # status only.
            from tooldetect import live_servers
            self.live_servers = live_servers(msg.get("mcp_servers"))
        return parse_line(msg)

    def _pump_for(self, proc) -> Pump:
        """The pump reading `proc` (master plan M27): the one made with it,
        or -- for a process this adapter did not spawn itself -- a new one."""
        with self._lock:
            pump = self._pump
            if pump is None or pump.proc is not proc:
                pump = Pump(proc, Between(), self._hand_unprompted)
                if self._proc is proc:
                    self._pump, self._bg = pump, pump.bg
            return pump

    def send(self, text: str, session_id: str | None = None) -> Iterator[Chunk]:
        try:
            proc, errors, stale = self._take(session_id)
        except LaunchRefused as e:
            # Phase M17: our own words, naming the flag and never its value.
            yield Chunk(error=str(e))
            return
        except OSError as e:
            yield Chunk(error=f"could not start claude: {e}")
            return
        if stale is not None and stale.poll() is None:
            stop_tree(stale, signal.SIGTERM)

        finished = False
        dog = None
        turn = None
        pump = self._pump_for(proc)
        try:
            # Registered before the write, so not one line of this turn is
            # read as between-turn talk (master plan M27).
            turn = pump.begin()
            if not _write_turn(proc, text):
                # Died between the check and the write -- the idle timer, or
                # the CLI itself. Once more from cold, then give up honestly.
                pump.end(turn)
                turn = None
                try:
                    proc, errors, _ = self._take(session_id, fresh=True)
                except LaunchRefused as e:
                    yield Chunk(error=str(e))
                    return
                except OSError as e:
                    yield Chunk(error=f"could not start claude: {e}")
                    return
                pump = self._pump_for(proc)
                turn = pump.begin()
                if not _write_turn(proc, text):
                    yield Chunk(error="claude exited before it could be asked")
                    return

            dog = Watchdog(proc, self.idle_timeout_s)
            #: For the daemon to poke while a tool call of this turn waits
            #: on it (a collaboration question, Phase 16).
            self.watchdog = dog
            bg = pump.bg
            # Master plan M27. Until this turn's own echo arrives, a turn the
            # CLI takes by itself may still come first: a background task
            # finished just before this was written, and the CLI answers
            # that before it answers us (recorded:
            # tests/fixtures/background/claude-race.json). While one is due
            # or under way its lines are held and read as its own, and its
            # `result` ends it, not this turn. The echo settles it: from
            # there on every line is ours, and anything held was ours too
            # (the CLI folded the finish into this turn).
            ours = False
            held: list[dict] = []
            # The stream does not end at the end of a turn any more -- the
            # process waits for the next one -- so the turn ends at its
            # `result`, and the pump keeps what comes after.
            while True:
                raw = turn.get()
                if raw is None:
                    break                     # the process ended
                dog.poke()
                msg = _parse(raw)
                if msg is None:
                    continue
                bg.track(msg)
                kind = msg.get("type")
                if not ours and is_echo(msg):
                    ours = True
                    bg.turn_began()
                    for early in held:
                        yield from self._own(early)
                    held = []
                    continue
                if not ours and bg.foreign:
                    held.append(msg)
                    said = bg.feed(msg)
                    if kind == "result":
                        held = []
                        if said is not None:
                            self._hand_unprompted(said)
                    continue
                if kind != "result":
                    yield from self._own(msg)
                else:
                    # Marked finished before anything else is yielded: a
                    # consumer that stops reading at the error chunk still
                    # leaves a process that has completed its turn, and that
                    # one is safe to keep.
                    finished = True
                    with self._lock:
                        if self._proc is proc:
                            self._holds = msg.get("session_id") or self._holds
                    if msg.get("subtype") != "success" and msg.get("is_error"):
                        yield Chunk(error=str(msg.get("result") or "agent error"))
                    yield Chunk(done=True,
                                session_id=msg.get("session_id"),
                                cost_usd=msg.get("total_cost_usd"),
                                duration_ms=msg.get("duration_ms"))
                    return

            # The stream ended without a result: the process is gone.
            code = proc.wait()
            if dog.fired:
                # Killed for going quiet. Indistinguishable from a cancel by
                # exit code alone, and silence is the one thing a voice
                # interface must never answer with.
                yield Chunk(error=f"claude stopped responding after "
                                  f"{dog.idle_s:.0f}s")
                return
            if code not in _STOPPED:
                # A cancel closes the pipe under us; that is not a failure.
                err = errors.text() if errors is not None else ""
                yield Chunk(error=err or f"claude exited {code}")
        finally:
            if dog is not None:
                dog.stop()
            if turn is not None:
                # What came after the result is the pump's from here.
                pump.end(turn)
            with self._lock:
                self._busy = False
                self._idle_since = time.time()
                if self._proc is proc:
                    if finished and proc.poll() is None:
                        self._arm_expiry()
                    else:
                        # Abandoned mid-turn -- the consumer stopped reading,
                        # or raised -- or already dead. Either way it is not a
                        # process anyone should write the next turn to: one
                        # still working would answer the old question first.
                        stale = self._forget()
                        if stale is not None and stale.poll() is None:
                            stop_tree(stale, signal.SIGTERM)

    def cancel(self) -> None:
        """Stop the turn in progress, and the process carrying it.

        A process that was interrupted mid-turn may still be working on the
        old question, so it is not kept: the next prepare() starts a fresh
        one with --resume, which is exactly what every turn used to cost.
        """
        with self._lock:
            proc = self._forget()
        if proc is not None and proc.poll() is None:
            stop_tree(proc, signal.SIGTERM)
