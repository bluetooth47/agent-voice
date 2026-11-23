"""Agents speak up when background work finishes (master plan, M27).

When work an agent started in the background finishes, that agent says one
short line, without waiting for the wake word, and a desktop notification
appears. This module is the part of that which can be judged without a
microphone: what counts as an event, what is said and shown, and the queue
that decides when.

**What starts an announcement.** Only something this daemon tracked itself:

- ``crew`` (tier 1, every backend that can delegate): a task an agent gave
  another with ``report_back`` finished (collab.Runtime.turn_ended). The
  daemon started that job and knows it ended; the line is the caller's,
  from a fixed table, because the target has already said its result out
  loud in its own voice (Phase 16) and the result itself still waits for
  the caller's next turn.
- ``background`` (tier 2, Claude Code only): the CLI's own stream said a
  background task this process started had finished (`task_notification`),
  and the turn it then took by itself is what the agent says
  (adapters/claude_code.py, recorded in tests/fixtures/background/).

A model writing "done" is text, not an event: nothing here is reachable from
anything an agent writes, no CLI verb files an announcement, and the adapter
announces an unprompted turn only when the CLI's own job tracking preceded
it.

**Delivery.** Spoken only when nobody is capturing or speaking, behind the
person and other agents; at most one line per agent per RATE_S; the spoken
part at most SPOKEN_MAX characters (the whole text goes to the chat, marked
unprompted); duplicates dropped; anything older than STALE_S expires. A
notification is shown when the event is accepted. While the screen is
locked, the microphone is muted or lent out, or Omarchy's notifications are
silenced, the notification is all there is, and the line is not kept to be
said on the way back. It opens no microphone capture by itself: the daemon
opens the usual follow-up window after a line it said, never while locked.

**The notification's text is fixed** ("Theo finished a background task"):
`notify-send` takes it in argv, which every local account can read, so a
model's words never go there -- only the agents' names, which are settings.

Pure apart from `notify()` and `silenced()`, each of which takes its runner
so a test can watch exactly what would have been run.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

#: The spoken part of an announcement, at most (the rest goes to the chat).
SPOKEN_MAX = 300
#: At most one line per agent in this many seconds; a later one waits.
RATE_S = 120.0
#: An announcement that could not be said for this long is not said at all.
STALE_S = 300.0
#: How long an event's key is remembered, so the same finish is never said
#: twice in this run.
SEEN_KEEP_S = 3600.0
#: Events waiting at once, every agent together; past it a new one is refused.
QUEUE_MAX = 16
#: The longest unprompted text kept for the chat.
TEXT_MAX = 8000
#: How long a silencing answer is reused before asking again.
SILENCED_TTL_S = 5.0

SOURCES = ("crew", "background")
STATUSES = ("completed", "failed")
#: How an announcement left the queue, for the journal and the chat record.
OUTCOMES = ("said", "locked", "lent", "muted", "silenced", "off", "stale",
            "stopped", "gone", "refused")

_AGENT = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_,.-]{0,199}")
_LABEL_MAX = 60


def clean_label(value, fallback: str = "An agent") -> str:
    """An agent's name as it may appear in a notification: one line, printable,
    bounded. It is a setting the person chose, never a model's text."""
    text = " ".join(str(value or "").split())
    text = "".join(c for c in text if c.isprintable())[:_LABEL_MAX].strip()
    return text or fallback


@dataclass
class Event:
    """One finished piece of background work, as the daemon saw it.

    `agent` is the external id ("main" for the main agent) of whoever speaks
    up. `key` names the finish (a crew task id, or the CLI's task ids), so a
    second report of the same finish is dropped. `text` is what the agent
    said by itself (tier 2 only; model text, untrusted). `label` and `other`
    are the daemon's own names for the agent and, for a crew task, the agent
    that did the work. `finished` is when the daemon learned of it."""
    agent: str
    source: str
    key: str
    status: str = "completed"
    text: str = ""
    label: str = ""
    other: str = ""
    finished: float = 0.0
    session: str | None = None
    #: Set on acceptance: whether the agent's setting said to speak up, read
    #: then (and read again before speaking).
    loud: bool = True
    notified: float | None = None
    extra: dict = field(default_factory=dict)

    def problem(self) -> str:
        """Why this is not an event at all, or "": a forged or malformed one
        is refused before it reaches the queue."""
        if self.source not in SOURCES:
            return "not a source the daemon tracks"
        if not isinstance(self.agent, str) or not _AGENT.fullmatch(self.agent):
            return "no such agent"
        if not isinstance(self.key, str) or not _KEY.fullmatch(self.key):
            return "no key"
        if self.status not in STATUSES:
            return "not a finish"
        if self.source == "crew" and self.text:
            # Tier 1 says a fixed line; the other agent's words are its own.
            return "a crew event carries no text"
        return ""


# --- what is said and shown --------------------------------------------------

def fixed_line(event: Event) -> str:
    """The line said in the agent's own voice when it has no words of its own
    (every crew event; a background task whose turn wrote nothing). From a
    table, never a model; another agent is named, never a pronoun."""
    other = clean_label(event.other, "the other agent")
    if event.source == "crew":
        if event.status == "completed":
            return f"The task I gave {other} is done, and I have the result."
        return f"The task I gave {other} didn't finish."
    if event.status == "completed":
        return "My background task has finished."
    return "My background task didn't finish."


def notification_text(event: Event) -> str:
    """The notification's one line. Fixed words around the agents' names --
    which are settings, never anything a model wrote -- because notify-send
    takes it in argv (world readable while it runs)."""
    me = clean_label(event.label)
    if event.source == "crew":
        other = clean_label(event.other, "Another agent")
        if event.status == "completed":
            return f"{other} finished a task for {me}"
        return f"{other}'s task for {me} didn't finish"
    if event.status == "completed":
        return f"{me} finished a background task"
    return f"{me}'s background task failed"


def hud_note(event: Event) -> str:
    """The readout's extra line while the announcement is on screen."""
    me = clean_label(event.label)
    if event.source == "crew":
        return f"{me}: a task for {clean_label(event.other, 'another agent')} finished"
    return f"{me}: background work finished"


_END = re.compile(r"[.!?…](?=\s|$)")


def spoken_part(text: str, limit: int = SPOKEN_MAX) -> str:
    """What is said of `text`: flattened to speech, at most `limit`
    characters, cut after the last whole sentence that fits, else at a word
    with an ellipsis. Never empty for a non-empty text."""
    import speech_text
    flat = speech_text.make_speakable(str(text or ""))
    if len(flat) <= limit:
        return flat
    head = flat[:limit]
    ends = [m.end() for m in _END.finditer(head)]
    if ends and ends[-1] >= limit // 3:
        return head[:ends[-1]].strip()
    cut = head[:limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return (cut or head[:limit - 1]) + "…"


def what_is_said(event: Event) -> tuple[str, str]:
    """(spoken, kept): the line to say and the text the chat keeps. A
    background event's own words when it has any, else the fixed line."""
    text = str(event.text or "").strip()[:TEXT_MAX]
    if event.source == "background" and text:
        spoken = spoken_part(text)
        if spoken:
            return spoken, text
    line = fixed_line(event)
    return line, line


# --- the queue ------------------------------------------------------------------

class Announcer:
    """Events waiting to be said, in the order they finished. Thread-safe:
    collab and the adapters' readers offer from their own threads; the run
    loop takes. Nothing here speaks or records."""

    def __init__(self, *, rate_s: float = RATE_S, stale_s: float = STALE_S,
                 queue_max: int = QUEUE_MAX) -> None:
        self.rate_s, self.stale_s, self.queue_max = rate_s, stale_s, queue_max
        self._lock = threading.Lock()
        self._queue: deque[Event] = deque()
        #: (agent, source, key) -> when first seen.
        self._seen: dict[tuple, float] = {}
        #: agent -> when its last line was said.
        self._said: dict[str, float] = {}
        #: agent -> when its last notification was shown.
        self._shown: dict[str, float] = {}

    def offer(self, event: Event, now: float | None = None) -> str:
        """Queue `event`. "" when accepted, else why not."""
        now = time.time() if now is None else now
        why = event.problem()
        if why:
            return why
        mark = (event.agent, event.source, event.key)
        with self._lock:
            for k, at in list(self._seen.items()):
                if now - at > SEEN_KEEP_S:
                    del self._seen[k]
            if mark in self._seen:
                return "already announced"
            if len(self._queue) >= self.queue_max:
                return "too many waiting"
            self._seen[mark] = now
            if not event.finished:
                event.finished = now
            self._queue.append(event)
        return ""

    def pending(self) -> int:
        with self._lock:
            return len(self._queue)

    def may_notify(self, agent: str, now: float | None = None) -> bool:
        """Whether `agent` may show a notification now, and if so counts it:
        the same limit as its lines, so a burst of finishes is one popup."""
        now = time.time() if now is None else now
        with self._lock:
            last = self._shown.get(agent)
            if last is not None and now - last < self.rate_s:
                return False
            self._shown[agent] = now
            return True

    def expired(self, now: float | None = None) -> list[Event]:
        """Take every event that waited longer than `stale_s`."""
        now = time.time() if now is None else now
        with self._lock:
            old = [e for e in self._queue if now - e.finished > self.stale_s]
            for e in old:
                self._queue.remove(e)
        return old

    def take_all(self) -> list[Event]:
        """Everything waiting (a lock, a mute, silencing: none is kept)."""
        with self._lock:
            out = list(self._queue)
            self._queue.clear()
        return out

    def drop(self, agent: str) -> list[Event]:
        """Everything waiting for `agent` ("Sora, stop")."""
        with self._lock:
            out = [e for e in self._queue if e.agent == agent]
            for e in out:
                self._queue.remove(e)
        return out

    def next_due(self, ready, now: float | None = None) -> Event | None:
        """The oldest event whose agent may speak now, taken off the queue.

        `ready(event)` is the daemon's word on that agent: "go", "wait" (busy,
        say it later) or "drop" (gone, or switched off; taken off with
        `outcome` set in event.extra). An agent that spoke less than `rate_s`
        ago waits, and so do the events behind it for the same agent: its
        lines keep their order."""
        now = time.time() if now is None else now
        with self._lock:
            waiting = list(self._queue)
        held: set[str] = set()
        for e in waiting:
            if e.agent in held:
                continue
            last = self._said.get(e.agent)
            if last is not None and now - last < self.rate_s:
                held.add(e.agent)
                continue
            verdict = ready(e)
            if verdict == "wait":
                held.add(e.agent)
                continue
            with self._lock:
                if e not in self._queue:
                    continue            # taken meanwhile (a stop)
                self._queue.remove(e)
            if verdict == "go":
                return e
            e.extra.setdefault("outcome", verdict if verdict in OUTCOMES else "gone")
            return e
        return None

    def spoke(self, agent: str, now: float | None = None) -> None:
        with self._lock:
            self._said[agent] = time.time() if now is None else now

    def clear(self) -> list[Event]:
        return self.take_all()


# --- the desktop's side ----------------------------------------------------------

def notify(event: Event, run=subprocess.run) -> str:
    """Show the fixed notification for `event`. "" when it was shown, else
    why not ("missing", "failed"). Never raises; never waits more than a few
    seconds. argv holds the fixed text and nothing else."""
    argv = ["notify-send", "--app-name=Agent Voice", "--", notification_text(event)]
    try:
        done = run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=5, check=False)
    except FileNotFoundError:
        return "missing"
    except (OSError, subprocess.SubprocessError, ValueError):
        return "failed"
    return "" if getattr(done, "returncode", 1) == 0 else "failed"


def quiet_file() -> Path:
    """Where Omarchy's notification service keeps do-not-disturb
    (plugins/notifications/Service.qml: `{"dnd": bool}`, written on change)."""
    state = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state) / "omarchy" / "notifications" / "quiet.json"


def silenced(run=subprocess.run, path: Path | None = None) -> tuple[bool, str]:
    """Whether Omarchy's notification silencing is on, and how that was
    known. The running shell is asked first (`omarchy-shell notifications
    isDnd`: "on" or "off"); then the file it saves the switch in. No file is
    off (the shell's own default); a file that cannot be read is on: when in
    doubt, quiet, and the notification is still shown."""
    try:
        done = run(["omarchy-shell", "notifications", "isDnd"], stdin=subprocess.DEVNULL,
                   capture_output=True, text=True, timeout=3, check=False)
        answer = (getattr(done, "stdout", "") or "").strip().lower()
        if getattr(done, "returncode", 1) == 0 and answer in ("on", "off"):
            return answer == "on", "shell"
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    path = path or quiet_file()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False, "no file"
    except (OSError, UnicodeDecodeError):
        return True, "unreadable"
    try:
        data = json.loads(raw)
    except ValueError:
        return True, "unreadable"
    if not isinstance(data, dict) or not isinstance(data.get("dnd", False), bool):
        return True, "unreadable"
    return data.get("dnd", False) is True, "file"
