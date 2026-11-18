"""Transcribe an utterance while it is still being spoken.

Whisper cannot start before it has audio, and the loop used to give it none
until the turn had ended -- so every turn paid the whole transcription after
the person had stopped talking. Measured in this machine's journal over 82
real turns: median 7.6s of audio, median 1105ms of Whisper, p90 1511ms, all
of it dead air. The README's ~320ms was a benchmark of short clips.

The fix is to use the pauses. Nobody talks for seven seconds without one,
and a pause is a place where no word can be cut in half. So:

  * At every pause (PAUSE_FRAMES of quiet) everything since the last cut is
    sent to Whisper in the background. The turn may be over -- the endpoint
    is still waiting for its full silence -- and if it is, the transcript is
    already done or nearly done when the wait ends.
  * If the person starts talking again, the pause was mid-thought. The piece
    is kept as a finished part of the transcript when it is long enough to
    stand on its own (MIN_PIECE_S), and thrown away otherwise, to be heard
    again as part of a longer piece. Very short clips are where Whisper is
    least reliable, so short pieces are never kept. The threshold is a
    choice, not a measurement -- bench/ is where to settle it.
  * The tail of what has already been said goes to Whisper as context for
    the next piece, so a sentence split across two pieces is still read as
    one sentence's worth of vocabulary.

Every piece goes through one worker thread, in order, so Whisper is never
asked two things at once and each piece's context is finished before it runs.

Nothing here knows about audio formats beyond a byte count per second, or
about Whisper beyond a function -- so it is tested on the bare CI runner with
a fake of both.
"""
from __future__ import annotations

import re
import threading
import time
from concurrent.futures import Future
from typing import Callable

#: 400ms of quiet at 200ms frames. One frame is too eager: a 200ms window
#: below the gate happens between words that are said slowly.
PAUSE_FRAMES = 2

#: A piece shorter than this is not kept on its own; see the module docstring.
MIN_PIECE_S = 3.0

#: Quiet kept in front of the first word. Whisper does better with a little
#: room before speech, and nothing at all is gained by handing it the seconds
#: of silence a lead-in can hold before anybody started talking.
LEAD_FRAMES = 2

#: How much of what has been said so far travels with the next piece.
CONTEXT_WORDS = 40

#: Words a statement does not end on. A transcript that ends with one is the
#: person drawing breath, not finishing -- so a quick end must not take it.
#: Kept to words that almost never close a sentence: "Turn it on.", "Delete
#: it.", "Do this.", "Tell me what it is." all end where they should, so
#: on, it, this and is are not here.
DANGLING = frozenset("""
    a an the
    and or but so because if than which whose while
    to of for with from into onto by at as like about
    my your his her our their
    um uh er erm hmm
    i
""".split())

#: Words that open more than they finish. Alone, they are somebody about to
#: say something; "Yes." and "Stop." are not on the list.
OPENERS = frozenset("okay ok so well alright right now hey also actually "
                    "and um uh hmm".split())


def sounds_finished(text: str) -> bool:
    """Whether a transcript reads like the end of something said.

    Deliberately narrow, because getting it wrong cuts somebody off -- the
    most irritating failure this program can have -- while getting it right
    only saves a few hundred milliseconds. Whisper ends most pieces with a
    full stop whether or not the speaker was done, so a full stop alone says
    little. What it does do is trail off with "..." or a comma when the voice
    did, and a question mark when the voice rose -- and a dangling word is
    left where a thought was cut. A question may end on a preposition ("What
    is this for?"), so the dangling list applies to statements only.
    """
    text = text.strip()
    if not text or text[-1] not in ".?!":
        return False
    if text.endswith("...") or text.endswith("…"):
        return False
    words = re.findall(r"[a-z']+", text.lower())
    if not words:
        return False
    if len(words) == 1 and words[0] in OPENERS:
        return False
    if text[-1] == "?":
        return True
    return words[-1] not in DANGLING


class Utterance:
    """One capture, transcribed a piece at a time.

    Driven from the frame loop: `add()` every frame, `tail()` when deciding
    whether the turn is over, `finish()` once it is. `abandon()` when the
    capture is thrown away -- a lock, nothing heard -- so queued work stops.
    """

    def __init__(self, transcribe: Callable[[bytes, str], str],
                 submit: Callable[..., Future], *,
                 bytes_per_s: int = 32_000, frame_bytes: int = 6_400) -> None:
        """`transcribe(pcm, context) -> text`; `submit(fn, *args) -> Future`,
        which must run jobs one at a time, in order."""
        self._transcribe = transcribe
        self._submit = submit
        self._bps = bytes_per_s
        self._frame = frame_bytes
        self._pcm = bytearray()
        #: Where the next piece starts, in bytes. None until speech is heard.
        self._start: int | None = None
        #: Pieces that are part of the transcript, in order.
        self._kept: list[Future] = []
        #: The piece sent at the current pause: (where it ends, its result).
        #: Cleared the moment speech resumes, so its presence means "nothing
        #: has been said since this was sent".
        self._pending: tuple[int, Future] | None = None
        self._quiet = 0
        self._abandoned = False
        #: Whisper time across every piece, including ones thrown away.
        self.busy_ms = 0.0
        #: How many pieces the finished transcript was made of.
        self.parts = 0
        #: Every piece ever sent, kept or not: (start, end, result). What the
        #: accurate live text is drawn from; see whisper_so_far().
        self._sent: list[tuple[int, int, Future]] = []
        #: The rough text to show where Whisper has not been yet.
        self.live = LiveText()

    # --- driven by the frame loop -------------------------------------------

    @property
    def size(self) -> int:
        """Bytes captured so far."""
        return len(self._pcm)

    def add(self, pcm: bytes, loud: bool) -> bool:
        """One frame. True when it ended a pause and a piece went to Whisper:
        the place the live text's rough part is cut too."""
        self._pcm += pcm
        if loud:
            self._quiet = 0
            if self._start is None:
                self._start = max(0, len(self._pcm) - len(pcm)
                                  - LEAD_FRAMES * self._frame)
            if self._pending is not None:
                end, fut = self._pending
                self._pending = None
                if (end - self._start) / self._bps >= MIN_PIECE_S:
                    self._kept.append(fut)
                    self._start = end
                else:
                    fut.cancel()      # heard again, as part of a longer piece
            return False
        self._quiet += 1
        if (self._quiet == PAUSE_FRAMES and self._start is not None
                and self._pending is None):
            end = len(self._pcm)
            self._pending = (end, self._submit(
                self._job, bytes(self._pcm[self._start:end])))
            self._sent.append((self._start, end, self._pending[1]))
            return True
        return False

    def whisper_so_far(self) -> tuple[str, int]:
        """Whisper's text for the audio it has finished, and where it ends.

        Walks from the first piece: at each start, the longest finished piece
        from there. A short piece later thrown away to be heard again as part
        of a longer one still counts until the longer one is done, so the
        text never falls back to Vosk's for audio Whisper has already read --
        the flicker this mode was warned about. (0 when there is none.)"""
        if not self._sent:
            return "", 0
        cursor, words, covered = self._sent[0][0], [], 0
        while True:
            done = [(end, fut) for start, end, fut in self._sent
                    if start == cursor and end > cursor and _usable(fut)]
            if not done:
                return " ".join(w for w in words if w), covered
            end, fut = max(done, key=lambda d: d[0])
            words.append(fut.result())
            cursor = covered = end

    def tail(self) -> str | None:
        """Everything said, if it is all transcribed and nothing has been
        said since; otherwise None. What a quick end decides on."""
        if self._pending is None:
            return None
        fut = self._pending[1]
        if not fut.done() or fut.cancelled() or fut.exception() is not None:
            # A piece that failed is finish()'s to report, at the end of the
            # turn, not this check's to raise in the middle of the frame loop.
            return None
        return self._join(self._kept + [fut])

    def finish(self, timeout: float = 60.0) -> tuple[str, float]:
        """The whole transcript, and how long it had to be waited for (ms)."""
        t0 = time.perf_counter()
        if self._start is None:
            # Never louder than the gate. The loop does not end a turn like
            # that, but the whole buffer is still the honest thing to hear.
            self._start = 0
        pieces = list(self._kept)
        if self._pending is not None:
            pieces.append(self._pending[1])
        elif self._start < len(self._pcm):
            pieces.append(self._submit(self._job,
                                       bytes(self._pcm[self._start:])))
        self.parts = len(pieces)
        text = self._join(pieces, timeout)
        return text, (time.perf_counter() - t0) * 1000

    def abandon(self) -> None:
        self._abandoned = True
        for fut in self._kept + ([self._pending[1]] if self._pending else []):
            fut.cancel()

    # --- on the worker thread -----------------------------------------------

    def _context(self) -> str:
        """The last few words already transcribed. Every kept piece ran
        before this one -- one worker, in order -- so each is finished."""
        done = [f.result() for f in list(self._kept)
                if f.done() and not f.cancelled()]
        words = " ".join(done).split()
        return " ".join(words[-CONTEXT_WORDS:])

    def _job(self, pcm: bytes) -> str:
        if self._abandoned:
            return ""
        t0 = time.perf_counter()
        text = self._transcribe(pcm, self._context())
        self.busy_ms += (time.perf_counter() - t0) * 1000
        return text.strip()

    @staticmethod
    def _join(pieces: list[Future], timeout: float | None = None) -> str:
        return " ".join(t for f in pieces if (t := f.result(timeout)))


def _usable(fut: Future) -> bool:
    return fut.done() and not fut.cancelled() and fut.exception() is None


class LiveText:
    """What the "accurate" live transcript shows while somebody talks.

    Vosk's rough text first, cut into segments at the same pauses where
    Utterance sends a piece to Whisper; each segment is replaced by Whisper's
    text once Whisper has read past it. Because both cut at the same frame,
    Whisper's coverage always ends on a segment boundary, and the rough part
    is simply every segment after it plus what Vosk is hearing now.
    """

    def __init__(self) -> None:
        #: Closed segments: (end in bytes, Vosk's text for it).
        self._segments: list[tuple[int, str]] = []
        #: Vosk finals inside the open segment (it ends utterances itself).
        self._finals: list[str] = []
        #: Vosk's partial for the open segment.
        self.partial = ""
        #: Whether anybody has spoken since the last cut. Vosk makes words
        #: out of the silence after one ("the"), and those were left on
        #: screen behind Whisper's finished text; until speech resumes, the
        #: open segment is not shown.
        self.voiced = False

    def heard(self, voiced: bool) -> None:
        self.voiced = self.voiced or voiced

    def final(self, text: str) -> None:
        if text:
            self._finals.append(text)
        self.partial = ""

    def cut(self, end: int, rest: str) -> None:
        """Close the open segment at `end` bytes; `rest` is Vosk's flushed text."""
        self.final(rest)
        self._segments.append((end, " ".join(self._finals)))
        self._finals = []
        self.voiced = False

    def render(self, whisper: str, covered: int) -> str:
        rough = [t for end, t in self._segments if end > covered]
        if self.voiced or not self._segments:
            rough += [*self._finals, self.partial]
        return " ".join(t for t in [whisper, *rough] if t)
