"""Each voice agent as a section in Omarchy's Agents panel.

That panel draws whatever JSON record lands in its usage directory, whoever
wrote it (see the README beside /usr/share/omarchy/shell/plugins/agents), so
nothing of Omarchy's is changed: the daemon writes one record per agent,
`agentvoice-<name>.json`, and the panel's own file watch picks up changes.
A record that is new only appears the next time that panel is opened,
because that is when it lists the directory again.

What a section can show is fixed by that panel: a name, the plan text on the
right, which is the one line always in view, and a note under an info mark
on hover. So the plan text says what the agent is doing now and the note says
what it runs on.

The token and prompt counts stay at zero. A voice turn runs the agent's own
CLI, whose collector already counts the prompt and its tokens; counting them
here as well would show them twice in the panel's totals. Voice turns are
said in the note instead.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path

PREFIX = "agentvoice-"

#: At most one write per agent per this many seconds. The state file is
#: rewritten for every change of microphone level; a record only changes with
#: what an agent is doing, and even that can flicker inside one turn.
MIN_INTERVAL = 1.0

PROGRAMS = {
    "claude": "Claude Code",
    "codex": "Codex",
    "gemini": "Gemini",
    "agy": "Antigravity",
    "opencode": "OpenCode",
    "grok": "Grok",
    "copilot": "Copilot",
    "endpoint": "Endpoint",
}

LEVELS = {
    "ask": "asks before every change",
    "edits": "may edit files",
    "trusted": "trusted with everything",
}

_BUSY = ("thinking", "speaking")


def usage_dir() -> Path:
    state = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local/state")
    return Path(state) / "omarchy/agents/usage"


def slug(name: str) -> str:
    """The file name for an agent: its wake name, which Config.agents() has
    already limited to lower-case words, joined with hyphens."""
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "main"


def program_label(program: str) -> str:
    return PROGRAMS.get(program, program.capitalize() if program else "No agent")


def status(agent: dict, mic: str, running: bool = True) -> str:
    """The one line always in view: what this agent is doing now."""
    if not running:
        return "Off"
    activity = agent.get("activity", "idle")
    # Doing a task another agent passed it (Phase 15): who it is for says
    # more than whether it is thinking or speaking.
    if activity in ("thinking", "speaking") and agent.get("for"):
        return f"Working for {agent['for']}"
    if activity == "thinking":
        return "Thinking…"
    if activity == "speaking":
        return "Speaking"
    if agent.get("hearing"):
        return "Transcribing" if mic == "transcribing" else "Listening to you"
    if not agent.get("program"):
        return "Not set up"
    if mic == "locked":
        return "Paused while locked"
    if mic == "off":
        return "Microphone off"
    if mic == "yielded":
        return "Paused for a recording"
    if mic in ("listening", "capture", "followup", "transcribing"):
        phrase = agent.get("phrase") or ""
        return f"Listening for “{phrase}”" if phrase else "Listening"
    return "Starting"


def note(agent: dict, turns: int, running: bool = True) -> str:
    """The note on hover: what it runs on, what it may do, how much it was used."""
    program = agent.get("program") or ""
    if not program:
        problem = agent.get("problem") or "No agent is set up for it."
        return f"{problem} Set it up in Agent Voice's settings, on the Agents page."
    parts = [program_label(program)]
    if agent.get("model"):
        parts.append(str(agent["model"]))
    if agent.get("effort"):
        parts.append(f"{agent['effort']} effort")
    level = LEVELS.get(agent.get("level") or "")
    if level:
        parts.append(level)
    said = " · ".join(parts) + "."
    said += f" {turns} voice turn{'s' if turns != 1 else ''} today."
    if agent.get("problem"):
        said += f" {agent['problem']}"
    if not running:
        said += " The voice service is stopped; middle-click its bar icon to start it."
    return said


def record(agent: dict, mic: str, turns: int, running: bool = True,
           today: str | None = None) -> dict:
    """One agent as the Agents panel reads it."""
    key = agent["key"]
    name = agent.get("label") or key.capitalize()
    return {
        "schemaVersion": 1,
        "id": PREFIX + key,
        "name": f"{name} (voice)",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        # The panel only gives a section to a ready record with a plan, so the
        # status takes the plan's place.
        "ready": True,
        "tierLabel": status(agent, mic, running),
        "usageStatusText": note(agent, turns, running),
        "authHelpText": "",
        "limits": [],
        "limitsStale": False,
        "limitsFetchedAt": 0,
        "hasLocalStats": False,
        "hasPromptStats": False,
        # Zero on purpose: see the module docstring.
        "todayPrompts": 0,
        "todaySessions": 0,
        "todayTotalTokens": 0,
        "todayTokensByModel": {},
        "recentDays": [],
        "totalPrompts": 0,
        "totalSessions": 0,
        "activeDays": 0,
        "activeDates": [],
        "modelUsage": {},
        # Ours, which the panel ignores: who wrote it, and the day's count, so
        # a restart of the service does not reset it to nothing.
        "source": "duaneoca.agentvoice",
        "voiceTurns": {"date": today or date.today().isoformat(), "count": turns},
    }


class AgentsPanel:
    """Keeps one record per voice agent in step with what the daemon publishes.

    `publish(mic, agents)` is called for every state write; it is cheap when
    nothing an agent shows has changed. `enabled` is read each time, so the
    setting takes effect without a restart.
    """

    def __init__(self, directory: Path | None = None, enabled=lambda: True,
                 clock=time.monotonic, today=lambda: date.today().isoformat()):
        self.dir = Path(directory) if directory is not None else usage_dir()
        self.enabled = enabled
        self._clock = clock
        self._today = today
        self._lock = threading.RLock()
        #: key -> the record last written, without its timestamp.
        self._written: dict[str, dict] = {}
        self._written_at: dict[str, float] = {}
        #: key -> the record waiting for its interval to pass.
        self._pending: dict[str, dict] = {}
        self._timer: threading.Timer | None = None
        #: key -> [date, count, busy] for the voice-turn count.
        self._turns: dict[str, list] = {}
        self._last: tuple[str, list] = ("off", [])
        #: The agents last pruned against, and whether the directory is known
        #: clear of ours: both spare a directory listing on every state write.
        self._keys: set[str] | None = None
        self._cleared = False

    # --- the count -------------------------------------------------------

    def _count(self, key: str, busy: bool) -> int:
        today = self._today()
        entry = self._turns.get(key)
        if entry is None:
            entry = [today, self._carried(key, today), False]
            self._turns[key] = entry
        if entry[0] != today:
            entry[0], entry[1] = today, 0
        if busy and not entry[2]:
            entry[1] += 1
        entry[2] = busy
        return entry[1]

    def _carried(self, key: str, today: str) -> int:
        """Today's count from the record a previous run left, if any."""
        try:
            old = json.loads((self.dir / f"{PREFIX}{key}.json").read_text())
            turns = old.get("voiceTurns") or {}
            if turns.get("date") == today:
                return max(0, int(turns.get("count", 0)))
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        return 0

    # --- writing ---------------------------------------------------------

    def publish(self, mic: str, agents: list[dict], running: bool = True) -> None:
        with self._lock:
            self._last = (mic, agents)
            if not self.enabled():
                if not self._cleared:
                    self.remove_all()
                return
            self._cleared = False
            wanted = set()
            for agent in agents:
                key = agent["key"]
                wanted.add(key)
                turns = self._count(key, agent.get("activity") in _BUSY)
                self._offer(key, record(agent, mic, turns, running, self._today()))
            if wanted != self._keys:
                self._prune(wanted)
                self._keys = wanted

    def _offer(self, key: str, rec: dict) -> None:
        bare = {k: v for k, v in rec.items() if k != "updatedAt"}
        if self._written.get(key) == bare:
            self._pending.pop(key, None)
            return
        wait = self._written_at.get(key, -MIN_INTERVAL) + MIN_INTERVAL - self._clock()
        if wait <= 0:
            self._pending.pop(key, None)
            self._write(key, rec)
            return
        self._pending[key] = rec
        if self._timer is None:
            self._timer = threading.Timer(wait, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            self._timer = None
            if not self.enabled():
                self._pending.clear()
                return
            pending, self._pending = self._pending, {}
            for key, rec in pending.items():
                self._offer(key, rec)

    def _write(self, key: str, rec: dict) -> None:
        path = self.dir / f"{PREFIX}{key}.json"
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            # Renamed into place: the panel watches the file, and must never
            # read half of one.
            tmp = self.dir / f".{PREFIX}{key}.tmp"
            tmp.write_text(json.dumps(rec) + "\n")
            tmp.replace(path)
        except OSError:
            return      # the panel missing an update is not worth a turn
        self._written[key] = {k: v for k, v in rec.items() if k != "updatedAt"}
        self._written_at[key] = self._clock()

    def _ours(self) -> list[Path]:
        try:
            return [p for p in self.dir.glob(f"{PREFIX}*.json") if p.is_file()]
        except OSError:
            return []

    def _prune(self, wanted: set[str]) -> None:
        """Remove the records of agents that are gone."""
        for path in self._ours():
            key = path.name[len(PREFIX):-len(".json")]
            if key not in wanted:
                path.unlink(missing_ok=True)
                self._written.pop(key, None)
                self._pending.pop(key, None)
                self._turns.pop(key, None)

    def remove_all(self) -> None:
        with self._lock:
            for path in self._ours():
                path.unlink(missing_ok=True)
            self._written.clear()
            self._pending.clear()
            self._keys = None
            self._cleared = True

    def stopped(self) -> None:
        """On the way out: every agent says Off, now, ignoring the interval.

        Kept rather than deleted, so the panel still lists them and says how
        to start them again. The uninstaller deletes them.
        """
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._pending.clear()
            if not self.enabled():
                self.remove_all()
                return
            mic, agents = self._last
            for agent in agents:
                key = agent["key"]
                turns = self._count(key, False)
                self._write(key, record({**agent, "activity": "idle", "hearing": False},
                                        mic, turns, running=False, today=self._today()))
