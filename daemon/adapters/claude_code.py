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
import re
import shlex
import signal
import subprocess
import sys
import threading
import weakref
from pathlib import Path
from typing import Iterator

from .base import (
    Adapter, Chunk, Drain, SPOKEN_STYLE, Watchdog, installed, prompt_file, stop_tree,
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


class ClaudeCode(Adapter):
    #: It loads the Omarchy skill itself, from --plugin-dir.
    takes_skill_text = False
    name = "claude"
    guards_permissions = True
    remembers = True          # one process per conversation, --resume after
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
        self.skill_dir: str | None = None
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
        _LIVE.add(self)

    @classmethod
    def _hook_settings(cls, named: str = "") -> str:
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
        return json.dumps({"hooks": {"PreToolUse": [{
            "matcher": GUARDED_TOOLS,
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
            "hooks": [{"type": "command", "command": command}],
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
            "--permission-mode", self.permission_mode,
        ]
        head = self.preamble()
        if head == SPOKEN_STYLE:
            # A constant this file ships, so argv is no leak.
            argv += ["--append-system-prompt", SPOKEN_STYLE]
        elif head:
            # The user's own words: off argv, into a private file.
            argv += ["--append-system-prompt-file", prompt_file(head)]
        if self.ask_permission:
            argv += ["--settings", self._hook_settings(self.named)]
        if self.desktop_tools:
            # Agent Voice's desktop tools (plan 12a), as this agent: the
            # server files a screenshot question under the same id the hook
            # uses. Added to the user's own MCP servers, not instead of them.
            from desktop_mcp import mcp_config
            argv += ["--mcp-config", mcp_config(self.name, self.named)]
        if self.skill_dir:
            # The Omarchy skill (plan 12b), loaded as a plugin for this
            # process only: nothing is written into ~/.claude.
            argv += ["--plugin-dir", self.skill_dir]
        if session_id:
            argv += ["--resume", session_id]
        if self.model:
            argv += ["--model", self.model]
        if self.effort and self.effort in self.efforts():
            argv += ["--effort", self.effort]
        return argv

    def efforts(self) -> tuple[str, ...]:
        return effort_levels(self.model)

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
        proc = subprocess.Popen(self._argv("", session_id), cwd=self.cwd,
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
        return proc

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
                except OSError:
                    self._arm_expiry()
                    return
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
                self._spawn(session_id)
            self._busy = True
            return self._proc, self._errors, stale

    def send(self, text: str, session_id: str | None = None) -> Iterator[Chunk]:
        try:
            proc, errors, stale = self._take(session_id)
        except OSError as e:
            yield Chunk(error=f"could not start claude: {e}")
            return
        if stale is not None and stale.poll() is None:
            stop_tree(stale, signal.SIGTERM)

        finished = False
        dog = None
        try:
            if not _write_turn(proc, text):
                # Died between the check and the write -- the idle timer, or
                # the CLI itself. Once more from cold, then give up honestly.
                try:
                    proc, errors, _ = self._take(session_id, fresh=True)
                except OSError as e:
                    yield Chunk(error=f"could not start claude: {e}")
                    return
                if not _write_turn(proc, text):
                    yield Chunk(error="claude exited before it could be asked")
                    return

            dog = Watchdog(proc, self.idle_timeout_s)
            # readline, not iteration: the stream does not end at the end of a
            # turn any more -- the process waits for the next one -- so the
            # turn ends at `result` and nothing past it may be read here.
            while True:
                line = proc.stdout.readline()
                if not line:
                    break                     # the process ended
                dog.poke()
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                kind = msg.get("type")

                if kind != "result":
                    yield from parse_line(msg)

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
            with self._lock:
                self._busy = False
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
