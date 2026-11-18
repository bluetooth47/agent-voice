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


def decide(names: list[str], has_vote: set[str], vosk: str,
           whisper: str) -> tuple[str, str]:
    """(name to wake, why) or ("", why not).

    `has_vote` holds the names Vosk can hear at all; `vosk` is the name it
    heard ("" for none); `whisper` is the raw transcript.
    """
    said, after = leading_name(whisper, names)
    if said and said in has_vote:
        if vosk == said and after <= MAX_TRAILING_WORDS:
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
