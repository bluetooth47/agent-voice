"""What the on-screen readout may show: the kept reply, and when the two
lines clear (phase M3, bug B and feedback item 20).

The readout -- the HUD and the popup's LAST HEARD -- has two lines: the
agent's last answer and what is being said now. Before M3 the wake word
cleared both (`_empty_turn`), so the answer vanished the moment somebody
began to reply to it, and the popup's section appeared and disappeared with
every turn, which is the bounce. Two things are decided here, apart from the
daemon so they can be tested on their own:

- **The kept reply.** The last non-empty `reply` the readout carried is kept
  and published as `last_reply` while the turn under way has no reply of its
  own. Always the same agent's as the turn's (`who_label` names it): it is
  dropped the moment another agent's turn is shown. Whether it is *drawn* is
  the screen's setting (`hudKeepReply`); the daemon only says what it is.
- **When both texts clear, at once.** On a lock (and they stay cleared after
  the unlock: nothing is saved and restored around a lock, CLAUDE.md), on a
  switch to another agent, on a chat switch from the conversation view, and
  on expiry: ten minutes with nothing new on the readout. The words cleared
  are remembered as `gone` -- every text the readout carried since the last
  clear, not only what was on it at that instant: a lock during a capture
  finds the screen blank, and the exchange before it would otherwise come
  straight back, because crew mode re-merges `Persona.last` into every idle
  payload, and the run loop republishes its own copy of the last turn with
  every level update. Until new words arrive both fields are sent as "".
  And the caches themselves are emptied (Codex review of M3): `on_clear`
  tells the daemon, which stops merging the agents' cached turns, and
  `generation` tells the run loop to drop the text from its own copy.
- **A capture never carries an answer.** The follow-up window opens on the
  turn just finished, and its partials replace only the transcript, so the
  old answer rode along as `reply` -- drawn whatever `hudKeepReply` said.
  While somebody is speaking (`capture`, `transcribing`) a reply is moved to
  `last_reply`.

The preview (the Display page's button) is here too: four seconds of sample
text published as a real `speaking` payload, so the HUD draws it exactly as
it would draw a turn. Only over an idle readout, never over a lock, and the
synthetic text never becomes the kept reply.

Thread-safety: compose() runs under the state file's lock from any thread;
the rest come from the run loop and turn threads, so one lock guards it all.
"""
from __future__ import annotations

import threading
import time

#: Nothing new on the readout for this long, and both lines clear. Long
#: enough to outlast a pause in an open-mic conversation (openMicIdleMin
#: runs to ten minutes), short enough that a reply is not still on screen
#: hours later for whoever opens the popup.
KEEP_S = 600.0

#: How many recent texts a clear covers. A turn carries a growing reply and
#: a growing partial, so this spans the last few turns.
SEEN_MAX = 64
#: And how many cleared texts are remembered, newest kept.
GONE_MAX = 256

#: How long the preview shows, as the plan specifies.
PREVIEW_S = 4.0

#: States in which nothing is being said or answered, so the readout can
#: expire without cutting off words somebody is reading. `followup` counts:
#: the window is open and waiting, and the text in it is the last exchange.
IDLE = ("listening", "off", "yielded", "followup")

#: Somebody is speaking: whatever reply a payload carries is the last one.
CAPTURING = ("capture", "transcribing")

#: The preview sits only on these: a real turn, a capture, a lent
#: microphone and a lock all win over it.
PREVIEWABLE = ("listening", "off")

#: Sample text for the preview. Plain and harmless, long enough to show how
#: a locked readout elides and a dynamic one wraps.
SAMPLE_TRANSCRIPT = "What's left on my calendar this afternoon?"
SAMPLE_REPLY = ("Two things: the design review at three, and a call with Sam at "
                "half past four. Nothing after that, so the evening is yours.")


class Readout:
    def __init__(self, clock=time.monotonic, lock=None, on_clear=None) -> None:
        self._clock = clock
        #: Called (under the lock) whenever both lines are cleared, so the
        #: daemon can stop its caches of the old turn from bringing it back.
        self._on_clear = on_clear
        #: Bumped on every clear; the run loop compares it with the one it
        #: last saw and drops the text from its own copy of the turn.
        self.generation = 0
        # The state file's own lock when the daemon gives it, else a new
        # one; re-entrant either way. One lock, not two: compose() runs
        # under the state file's lock, so a separate one here could be held
        # by the main thread (expire) while a worker held the state file's
        # and waited for it -- and SIGUSR1's handler, which publishes from
        # the main thread, then deadlocked both (Codex review of M3).
        self._lock = lock if lock is not None else threading.RLock()
        #: {"who", "text"}: the last reply the readout carried.
        self._kept: dict | None = None
        #: Texts cleared and not to be shown again, oldest first.
        self._gone: list[str] = []
        #: True from a clear until new words arrive: both fields go out as "".
        self._blank = False
        #: The preview was on the screen and its end has not been drawn yet.
        self._previewed = False
        #: Every text the readout has carried since the last clear: what a
        #: clear has to cover. Bounded, oldest first.
        self._seen: list[str] = []
        #: What the readout last showed: who, transcript, reply, state.
        self._who = ""
        self._shown = ("", "")
        self._state = "off"
        #: When the readout last changed: new words in either line.
        self._at = clock()
        self._preview_until = 0.0

    # --- every payload ----------------------------------------------------

    def compose(self, state: str, extra: dict) -> tuple[str, dict]:
        """`extra` as it should be published, for a payload that is not
        locked. Returns new objects; never changes the ones it is given."""
        with self._lock:
            now = self._clock()
            extra = dict(extra)
            # Whose words these are. The main agent's id is "" in crew mode,
            # as is nobody's, so its label tells the two apart (Codex review:
            # a lent microphone after the main agent answered kept its words).
            who = str(extra.get("who", "") or "")
            if not who and extra.get("who_label"):
                who = "\x00main"
            t, r = extra.get("transcript"), extra.get("reply")

            if self._blank:
                gone = set(self._gone)
                if any(isinstance(v, str) and v != "" and v not in gone for v in (t, r)):
                    # New words: the screen is the new turn's now. The
                    # daemon's caches of the old one were emptied at the
                    # clear (on_clear, generation), so nothing stale is
                    # left to filter, and a new turn worded like an old
                    # one ("Yes.") is shown like any other.
                    self._blank = False
                    self._gone = []
                else:
                    # Said outright, not left out: the screen updates only a
                    # field it is sent, so an absent key keeps the old words.
                    extra["transcript"] = extra["reply"] = ""
                    t = r = ""

            if who != self._who:
                # Another agent's turn, or none: its answer is not this
                # one's, and words the payload does not replace were the
                # other agent's (a lent microphone after Theo answered
                # said nothing about Theo's words, and they stayed).
                self._kept = None
                if t is None:
                    extra["transcript"] = t = ""
                if r is None:
                    extra["reply"] = r = ""

            if state in CAPTURING and r:
                # The answer before this capture, not an answer to it.
                self._kept = {"who": who, "text": str(r)}
                extra["reply"] = r = ""

            shown_t = self._shown[0] if t is None else str(t)
            shown_r = self._shown[1] if r is None else str(r)
            if (shown_t, shown_r) != self._shown or who != self._who:
                self._at = now
            self._who, self._shown, self._state = who, (shown_t, shown_r), state
            for v in (shown_t, shown_r):
                if v and v not in self._seen:
                    self._seen = (self._seen + [v])[-SEEN_MAX:]

            if r:
                self._kept = {"who": who, "text": str(r)}
            elif self._kept is not None and r is not None:
                # The turn under way has no answer yet (the wake word cleared
                # it): the last one, for the screen to keep if it is set to.
                extra["last_reply"] = self._kept["text"]

            if now < self._preview_until and state in PREVIEWABLE:
                # Laid over the real payload, after everything above, so the
                # sample is never kept and never marks anything gone.
                extra.update(transcript=SAMPLE_TRANSCRIPT, reply=SAMPLE_REPLY,
                             preview=True)
                extra.pop("last_reply", None)
                self._previewed = True
                state = "speaking"
            elif self._previewed:
                # After it: the real words, said outright, or a merging screen
                # keeps the sample (a muted `off` payload carries no text at
                # all). Until a payload carries both itself, not just once:
                # the watcher can miss a write that is replaced at once.
                if t is not None and r is not None:
                    self._previewed = False
                extra.setdefault("transcript", self._shown[0])
                extra.setdefault("reply", self._shown[1])
            return state, extra

    # --- clearing ---------------------------------------------------------

    def _clear_shown(self) -> None:
        texts = set(self._seen) | {v for v in self._shown if v}
        if self._kept is not None:
            texts.add(self._kept["text"])
        if texts:
            self._gone = ([g for g in self._gone if g not in texts] + sorted(texts))[-GONE_MAX:]
            self._blank = True
        self._seen = []
        self._kept = None
        self.generation += 1
        if self._on_clear is not None:
            self._on_clear()

    def lock(self) -> None:
        """The screen locked: both lines go, and stay gone after the unlock.
        Called for every locked payload; idempotent."""
        with self._lock:
            self._clear_shown()
            self._preview_until = 0.0

    def forget(self, who: str, clear: bool = False) -> None:
        """`who`'s conversation changed (a new chat, a continued one, a
        rebuild that dropped the session): its reply is not kept for the
        next turn. With `clear`, what is on screen for it goes too -- for a
        switch made from the conversation view, where no turn follows to
        replace it. Not for "new chat" said aloud: that turn's own words are
        the ones on screen, and clearing them would blink."""
        # The main agent is "" to the daemon and "\x00main" here in crew
        # mode (compose, above): either names it.
        mine = {who, "\x00main"} if who == "" else {who}
        with self._lock:
            if self._kept is not None and self._kept["who"] in mine:
                self._kept = None
            if clear and self._who in mine:
                self._clear_shown()

    def expire(self) -> bool:
        """Clear both lines after KEEP_S with nothing new, while idle. True
        when it did, so the caller republishes."""
        with self._lock:
            if self._state not in IDLE:
                return False
            if self._clock() - self._at < KEEP_S:
                return False
            if not any(self._shown) and self._kept is None:
                return False
            self._clear_shown()
            return True

    # --- the preview ------------------------------------------------------

    def preview(self) -> float:
        """Start the preview; returns how long it lasts."""
        with self._lock:
            self._preview_until = self._clock() + PREVIEW_S
            return PREVIEW_S

    @property
    def previewing(self) -> bool:
        with self._lock:
            return self._clock() < self._preview_until
