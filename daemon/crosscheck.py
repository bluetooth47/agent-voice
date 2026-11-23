"""A second look at short bursts of speech the keyword spotter let pass.

sherpa-onnx misses short names a lot: on synthesized clips it caught "theo"
5/10 and "sora" 3/10 at any threshold (FINDINGS §24). Nothing in the log
showed those misses, so it looked like valid attempts were being discarded.

So when a short burst of speech ends and the spotter said nothing, two other
engines are asked about the same audio, and both have to hear the same name:

- Vosk, constrained to a grammar of the names. Hears "theo" 10/10 but also
  wakes on "Video", "Cleo" and "Leo" -- useless alone, a good second vote.
- Whisper, transcribing freely with the names as a prompt. Heard "theo"
  10/10 and "sora" 8/10, and nothing else said "theo"; "Story" came out
  "Sora" 2/10.

Agreement lost no "theo" wakes and woke on no distractor. Vosk's lexicon has
no "sora", so a stand-in it does know votes for it ("zora": Sora 10/10, but
also Story/Sorry -- Whisper rejects those). A name with neither gets Whisper
alone, held to the strictest form: the transcript is only the name.

Everything here is pure, so it is tested without a model; wake_listen.py
owns the engines and calls in.

**Which stages must agree** (master plan M22). With the second check on, a
spotter hit wakes at once and the second check only rescues what the spotter
missed, so either stage alone can wake. `wakeBothAgree` adds the third
choice: a spotter hit is held while the second check listens to the same
burst, and wakes only if it names the same agent. `decision()` names the
three, `both_blocker()` says when the third cannot run (and the daemon then
holds wakes closed rather than fall back to one stage), and `Agreement` is
the hold itself.
"""

from __future__ import annotations

import re

#: Words Vosk's lexicon does know that sound like a name it does not. Picked
#: by measurement (FINDINGS §24), not by spelling: "soar a" caught Sora 3/10.
STAND_INS: dict[str, tuple[str, ...]] = {
    "sora": ("zora",),
}

#: Words a person puts in front of a name. Stripped before matching, so
#: "Hey, Theo." counts as "theo".
GREETINGS = frozenset({"hey", "hi", "hello", "ok", "okay", "yo", "oi"})

#: A burst this short is a click or a breath, not a name.
MIN_BURST_MS = 300
#: Longer than this is a sentence, and a name buried in one is someone
#: talking about the agent rather than to it.
MAX_BURST_MS = 2600
#: Quiet frames that end a burst. Also time for the spotter to finish
#: decoding: it reports a phrase a frame or two after the speech stops, and a
#: second check must not run on audio the first is still deciding about.
QUIET_END_FRAMES = 2
#: Frames kept from before the first loud one, so the name's onset -- quieter
#: than its vowel -- is in the audio the engines see.
PREROLL_FRAMES = 1
#: Words allowed after the name for the two-engine rule ("Theo, you there?").
MAX_TRAILING_WORDS = 3


def words(text: str) -> list[str]:
    """Lower-case words with punctuation dropped. An apostrophe joins rather
    than splits, so "Theo's" is "theos", which is not the name."""
    return re.findall(r"[a-z0-9]+", text.lower().replace("'", "").replace("’", ""))


def leading_name(text: str, names: list[str]) -> tuple[str, int]:
    """(name, words after it) when `text` opens with one of `names` after an
    optional greeting, else ("", 0). Longest name first, so "hey computer"
    beats "computer"."""
    w = words(text)
    ordered = sorted(names, key=lambda n: -len(n.split()))
    while True:
        # Names are tried before each greeting is dropped: "hey computer" is
        # a phrase of its own, not a greeting in front of "computer".
        for name in ordered:
            parts = name.split()
            if w[:len(parts)] == parts:
                return name, len(w) - len(parts)
        if not w or w[0] not in GREETINGS:
            return "", 0
        w = w[1:]


def vosk_grammar(names: list[str], knows) -> tuple[list[str], dict[str, str]]:
    """The grammar Vosk listens with, and what each entry means.

    Each name Vosk knows is itself; one it does not is replaced by its
    stand-ins. A name with neither is left out -- it has no Vosk vote.
    """
    grammar: list[str] = []
    means: dict[str, str] = {}
    for name in names:
        if all(knows(w) for w in name.split()):
            options = [name]
        else:
            options = [s for s in STAND_INS.get(name, ())
                       if all(knows(w) for w in s.split())]
        for o in options:
            if o not in means:
                grammar.append(o)
                means[o] = name
    return grammar, means


def vosk_heard(text: str, means: dict[str, str]) -> str:
    """The name a Vosk grammar result stands for, or ""."""
    padded = f" {text} "
    found = [o for o in means if f" {o} " in padded]
    return means[max(found, key=len)] if found else ""


#: crossCheckEngines: which engines vote on a burst.
#:   both    -- Vosk and Whisper must name the same agent (FINDINGS §24);
#:   whisper -- Whisper alone, held to `trailing` words after the name. It
#:              runs on every burst, about a second of CPU each;
#:   vosk    -- Vosk alone. Cheap, and wakes on sound-alikes ("Video",
#:              "Cleo" for Theo): only for a quiet room.
MODES = ("both", "whisper", "vosk")


def decide(names: list[str], has_vote: set[str], vosk: str,
           whisper: str, mode: str = "both",
           trailing: int = MAX_TRAILING_WORDS) -> tuple[str, str]:
    """(name to wake, why) or ("", why not).

    `has_vote` holds the names Vosk can hear at all; `vosk` is the name it
    heard ("" for none); `whisper` is the raw transcript ("" when Whisper
    was not asked). `trailing` is how many words may follow the name.
    """
    if mode == "vosk":
        return (vosk, "vosk alone") if vosk else ("", "")
    said, after = leading_name(whisper, names)
    if mode == "whisper":
        if not said:
            return "", ""
        if after <= trailing:
            return said, "whisper alone"
        return "", "whisper alone — too many words after the name"
    if said and said in has_vote:
        if vosk == said and after <= trailing:
            return said, "vosk + whisper"
        if vosk == said:
            return "", "too many words after the name"
        return "", "whisper only — vosk disagreed"
    if said:
        # Nobody to cross-check with: only the bare name will do.
        if after == 0:
            return said, "whisper (vosk can't hear this name)"
        return "", "whisper only — not the bare name"
    if vosk:
        return "", "vosk only — whisper disagreed"
    return "", ""


class Bursts:
    """Cuts the frame stream into bursts of speech by level.

    feed() returns the burst's audio once QUIET_END_FRAMES quiet frames have
    followed it, if it was the right length; otherwise None. The audio holds
    the preroll and the quiet tail, which Vosk needs to finish a word.
    """

    def __init__(self, frame_ms: int, min_ms: int = MIN_BURST_MS,
                 max_ms: int = MAX_BURST_MS) -> None:
        self.frame_ms = frame_ms
        #: The window, from crossCheckMinMs / crossCheckMaxMs. Plain
        #: attributes, so a new setting applies to the next burst.
        self.min_ms = min_ms
        self.max_ms = max_ms
        self._pre: list[bytes] = []
        self._buf: list[bytes] = []
        self._loud = 0
        self._quiet = 0

    def clear(self) -> None:
        self._pre, self._buf, self._loud, self._quiet = [], [], 0, 0

    def feed(self, pcm: bytes, loud: bool) -> bytes | None:
        if not self._buf:
            if not loud:
                self._pre = (self._pre + [pcm])[-PREROLL_FRAMES:] if PREROLL_FRAMES else []
                return None
            self._buf = list(self._pre)
            self._pre = []
        self._buf.append(pcm)
        if loud:
            self._loud += 1
            self._quiet = 0
            # A burst that has run past the limit is a sentence; drop it now
            # rather than buffer a monologue.
            if self._loud * self.frame_ms > self.max_ms:
                self._buf = self._buf[-1:]
                self._loud = self.max_ms // self.frame_ms + 1
            return None
        self._quiet += 1
        if self._quiet < QUIET_END_FRAMES:
            return None
        speech_ms = self._loud * self.frame_ms
        audio = b"".join(self._buf)
        self.clear()
        if self.min_ms <= speech_ms <= self.max_ms:
            return audio
        return None

    def take(self) -> bytes | None:
        """The burst so far, cut here rather than at its end, and start again.

        For "both must agree" (master plan M22): a spotter hit is confirmed
        on the speech up to it, so a request said in one breath ("Theo,
        what's the time") is not lost to the trailing-word rule at its end. The same window applies: less speech than
        `min_ms` is not enough to judge, and a burst already past `max_ms`
        is a sentence with a name inside it. None for either, or when no
        burst has started (a name said below the gate).
        """
        speech_ms = self._loud * self.frame_ms
        audio = b"".join(self._buf) if self._buf else None
        self.clear()
        if audio is not None and self.min_ms <= speech_ms <= self.max_ms:
            return audio
        return None


# --- which stages must agree (master plan M22) ---------------------------------

#: The three wake decisions the Listening page offers, in its order.
#:   first  -- the first listener alone (second check off);
#:   either -- a spotter hit wakes at once, and the second check rescues a
#:             short burst the spotter missed (second check on: the default);
#:   both   -- a spotter hit is held until the second check names the same
#:             agent (wakeBothAgree).
DECISIONS = ("first", "either", "both")

#: Frames a spotter hit waits, at most, before the second check is asked
#: about the speech up to it (the burst ends sooner if the person pauses).
#: 0: on the hit's own frame. Measured in FINDINGS §55 against 1 and 2,
#: which were meant to let a word that only starts like a name ("Theodore",
#: "Hazelnut") be heard to its end: they stopped no more of those, lost five
#: more real wakes (one-breath requests ran past the trailing-word rule) and
#: added 0.2-0.4s. The frames a longer tail waits are carried to the capture.
CONFIRM_TAIL_FRAMES = 0

#: How long, in ms, a second-check vote waits for a late spotter hit on the
#: same name. The spotter reports a frame or two after the speech stops,
#: which is usually before the burst ends; this covers the rest.
AGREE_WINDOW_MS = 600


def decision(cross_check: bool, both_agree: bool) -> str:
    """Which of DECISIONS the two settings make.

    `both_agree` wins whatever `cross_check` says: someone who asked for
    both stages has not asked for one, and if the second check is off the
    daemon holds wakes closed and says so (`both_blocker`) rather than wake
    on the spotter alone.
    """
    if both_agree:
        return "both"
    return "either" if cross_check else "first"


#: Why "both must agree" cannot run, by code. The state file carries both:
#: the page decides on the code and shows the sentence.
BLOCKERS = {
    "oww": "openWakeWord has no second check",
    "vosk": "Vosk has no second check",
    "fallback": "sherpa-onnx is not running, and Vosk has no second check",
    "off": "the second check is switched off",
    "no-vosk": "the second check votes with Vosk, which is not installed",
}


def both_blocker(engine: str, cross_check: bool, engines: str = "both",
                 vosk_installed: bool = True, sherpa_chosen: bool = True) -> str:
    """Why "both must agree" cannot run with the engines as they are: a key
    of BLOCKERS, or "" when it can.

    `engine` is the engine actually listening (a sherpa-onnx that fell back
    is "vosk"), `sherpa_chosen` whether sherpa-onnx is the one chosen.
    """
    if engine == "openwakeword":
        return "oww"
    if engine != "sherpa":
        return "fallback" if sherpa_chosen else "vosk"
    if not cross_check:
        return "off"
    if engines == "vosk" and not vosk_installed:
        return "no-vosk"
    return ""


class Agreement:
    """The hold behind "both must agree": one stage has named an agent and
    the other has not answered yet.

    Two orders, because the stages report at different moments:

    - the spotter first (the usual one): its hit is held for up to
      `tail` frames, or until the burst ends, and the second check is then
      asked about that burst;
    - the second check first: the burst ended, the second check named
      somebody, and the spotter -- which reports a frame or two after the
      speech stops -- has not yet. Its vote waits `window` frames.

    Frames that arrive while a hit is held are kept: they belong to the
    capture the wake opens, as they would have with the spotter alone.
    Pure: the caller asks the engines and feeds the answers in.
    """

    def __init__(self, tail: int = CONFIRM_TAIL_FRAMES, window: int = 3) -> None:
        self.tail = max(0, int(tail))
        self.window = max(1, int(window))
        #: None, or {"stage": "spotter" | "check", "name", "left", "frames"}.
        self.pending: dict | None = None

    def clear(self) -> None:
        self.pending = None

    def hold(self, stage: str, name: str) -> None:
        """Start holding a vote from `stage` for `name`."""
        self.pending = {"stage": stage, "name": name, "frames": [],
                        "left": self.tail if stage == "spotter" else self.window}

    def waiting_on_check(self) -> bool:
        return self.pending is not None and self.pending["stage"] == "spotter"

    def check_vote(self, name: str) -> str:
        """A second-check vote held from the burst that just ended, or ""."""
        p = self.pending
        return p["name"] if p is not None and p["stage"] == "check" and p["name"] == name else ""

    def frame(self, pcm: bytes) -> str:
        """One more frame while something is held. Returns "due" when a held
        spotter hit has waited its tail and the second check must be asked
        now, "expired" when a held second-check vote ran out (the caller
        drops it), else ""."""
        p = self.pending
        if p is None:
            return ""
        p["frames"].append(pcm)
        p["left"] -= 1
        if p["left"] > 0:
            return ""
        return "due" if p["stage"] == "spotter" else "expired"

    def take(self) -> dict | None:
        """The held vote, and stop holding it."""
        p, self.pending = self.pending, None
        return p
