"""More than one agent, each woken by its own name, working at the same time.

The main agent is the one configured everywhere else in the settings: the
wake phrase, Omarchy's default agent, the model, effort, voice, permission
level and folder chosen for it. Each extra agent in `voiceAgents` brings its
own of all of those, and its own conversation.

With only the main agent, nothing here is used and a turn runs exactly as it
always has: in the run loop, which listens again once the reply is over. With
any extra agent, every turn runs on a thread of its own instead, so the
microphone keeps listening while agents work, and somebody can give a second
agent something to do while the first is still busy.

Two things are still one at a time, because there is one room:

- speaking. One microphone beside one speaker cannot hear its own voice
  apart from yours, so nothing is listened to while any agent talks (the
  headset barge-in excepted, as before), and agents take turns: whichever
  started a reply keeps the floor until it goes quiet for a moment, so two
  replies are never interleaved sentence by sentence.
- listening. Nobody is talked over: once someone is speaking to an agent, or
  has just said a name, every reply waits until they have finished.
"""
from __future__ import annotations

import re
import threading

#: How long an agent keeps the floor after a sentence, waiting for its next
#: one, before another agent may start. Long enough to cover the gap between
#: two sentences of one reply, short enough that a reply that has gone off to
#: run tools does not keep everyone else waiting.
FLOOR_LEASE_S = 1.5

#: How long after a reply its follow-up window may still open. A window is
#: only opened from the idle loop, and if somebody was talking to another
#: agent by then, this one's moment has passed.
FOLLOW_UP_STALE_S = 2.0

#: Said before a name and not part of it: "hey jarvis, ..." is for jarvis.
_GREETINGS = ("hey", "okay", "ok", "hi")

_EDGE = re.compile(r"^[^\w']+|[^\w']+$")


class Persona:
    """One agent the person can talk to, and everything that is its own.

    The main agent is a Persona too, with `spec` None, so the code that runs
    a turn never needs to know which kind it is serving.
    """

    def __init__(self, name: str = "", spec: dict | None = None) -> None:
        #: The word that wakes it. The main agent's is the wake phrase.
        self.name = name
        #: Its settings as Config.agents() cleaned them, or None for the main
        #: agent, whose settings are the ordinary ones.
        self.spec = spec
        #: What grants, the permission hook, saved chats and the Agents panel
        #: know it by. Stays put when its name or wake phrase changes. ""
        #: for the main agent, which the hook knows by having no id.
        self.id = (spec or {}).get("id", "")
        #: What it is called on screen and out loud. Any text.
        self.label = (spec or {}).get("label", "") or name
        self.agent = None
        #: Its own conversation: agents never share one.
        self.session_id: str | None = None
        self.speaker = None
        #: Set to stop this agent's turn, and only this one's.
        self.interrupt = threading.Event()
        self.thread: threading.Thread | None = None
        #: "idle", "thinking" or "speaking", for the readout.
        self.state = "idle"
        #: Its turn as the readout shows it: transcript, reply, timings.
        self.last: dict = {}
        #: Whether its last turn ended in a way that opens a follow-up window.
        self.follow_up = False
        self.finished_at = 0.0
        #: Why this agent cannot answer, when it cannot, for the settings.
        self.problem = ""
        #: The saved chat its turns go into (chats.py), when chats are saved.
        self.chat_id: str | None = None
        #: Set by Continue: the next turn belongs to `chat_id` even though it
        #: starts a new session, because the chat is being replayed.
        self.chat_continued = False
        #: The chat as text, put ahead of the next request once, for a
        #: backend that cannot resume a session natively.
        self.replay = ""
        #: The next turn was heard on the open microphone, without a name.
        self.open_turn = False
        #: The session handed to a terminal, while that terminal may still
        #: hold it: voice does not touch it until it is closed.
        self.terminal: str | None = None

    @property
    def main(self) -> bool:
        return self.spec is None

    @property
    def busy(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def stop(self) -> None:
        """Stop whatever this agent is doing: thinking, running, speaking."""
        self.interrupt.set()
        for part in (self.speaker, self.agent):
            if part is not None:
                try:
                    part.cancel()
                except Exception:
                    pass

    def __repr__(self) -> str:      # pragma: no cover - debugging aid
        return f"Persona({self.name!r}, {'main' if self.main else 'extra'})"


class View:
    """What a turn running for one agent publishes to, instead of the state
    file itself. It records the agent's own state; the daemon then decides
    what the shared readout shows, so two agents and the microphone do not
    overwrite one another's line on screen."""

    def __init__(self, persona: Persona, recompose) -> None:
        self.persona = persona
        self._recompose = recompose

    def publish(self, state: str, **extra) -> None:
        self.persona.state = state
        self.persona.last = dict(extra)
        self._recompose()

    @property
    def current(self) -> str:
        return self.persona.state


def route(text: str, names) -> tuple[str, str]:
    """Who `text` is addressed to, and what is left of it once the name is off.

    ("", text) when it does not open with one of `names`. A name counts only
    at the very start -- "ask jarvis about it" is not for jarvis -- and may
    follow a greeting: "Hey Jarvis, what time is it?" is ("jarvis", "what
    time is it?"). Matched on whole words, longest name first, ignoring case
    and the punctuation Whisper puts around them.
    """
    words = text.split()
    plain = [_EDGE.sub("", w).lower() for w in words]
    # A greeting may be part of the name itself: "hey computer".
    starts = (0, 1) if plain and plain[0] in _GREETINGS else (0,)
    for name in sorted({n for n in names if n}, key=len, reverse=True):
        parts = name.split()
        for start in starts:
            end = start + len(parts)
            if plain[start:end] == parts:
                return name, " ".join(words[end:]).lstrip(",.:;!?-—– ")
    return "", text
