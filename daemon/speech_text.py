"""Make agent replies speakable, and chunk them for streaming TTS.

Adapted from duaneoca/hermes-satellite (src/hermes_satellite/core/speech_text.py),
which had already solved this properly. Kept nearly verbatim because the edge
cases here are all ones that only show up when you listen to the output:

  - a sentence boundary must not split "2.47 PM" or "J. Smith"
  - fragments under ~20 characters make TTS sound choppy, so they merge forward
  - a fenced code block becomes "Code omitted", not silence
  - list items need terminal punctuation or they run together when joined

The system prompt asking for plain prose is the first line of defence; this is
the second, for whatever slips through anyway.
"""
from __future__ import annotations

import re

_CODE_BLOCK = re.compile(r"```.*?(```|\Z)", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]*)`")
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__")
_ITALIC = re.compile(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])|(?<![\w_])_([^_\n]+)_(?![\w_])")
_HEADER = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+", re.MULTILINE)
_BLOCKQUOTE = re.compile(r"^[ \t]*>[ \t]?", re.MULTILINE)
_BULLET = re.compile(r"^[ \t]*(?:[-*•+]|\d+[.)])[ \t]+")
_EMOJI = re.compile(
    "["
    "\U0001f000-\U0001faff"
    "←-⇿"
    "⌀-➿"
    "⬀-⯿"
    "️"
    "]+"
)
_WHITESPACE = re.compile(r"[ \t]+")

#: C0 and C1 control characters, less tab and newline. Transcripts and model
#: replies are printed, and a terminal does not merely display these: OSC 52
#: writes the system clipboard in foot, and a CSI sequence can rewrite lines
#: that have already scrolled past. The daemon normally runs under systemd,
#: where they land in the journal instead -- but `agentvoice listen` in a
#: terminal is how it is developed and debugged, which is exactly when the
#: text being printed is the text nobody trusts.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def safe_for_terminal(text: str) -> str:
    """`text` with control characters taken out, for printing or logging."""
    return _CONTROL.sub("", str(text))


#: A leading dash that is a minus sign rather than a stray mark: one of the
#: dash characters Whisper emits, immediately followed by a digit.
_SIGNED = re.compile(r"^[-‐‑‒–—]\d")


def as_prompt(text: str) -> str:
    """A transcript, tidied, without losing anything that was said.

    Whisper puts a leading dash on a pause, a dictated dash or a false start
    -- "- something" -- and dropping it makes the readout cleaner. That used
    to matter for more than tidiness: every backend passed the transcript in
    argv, where a leading hyphen reads as a flag, and this was what stopped a
    turn being lost to an unknown-flag error.

    It no longer carries that weight. No backend puts the transcript in argv
    any more -- they feed stdin or an HTTPS body, which
    `TestNoSpokenPromptInArgv` asserts -- so the strip is now cosmetic, and a
    cosmetic rule must not change what a person said.

    It was doing exactly that. This docstring used to end "nothing a person
    says starts with a hyphen", which a user falsified in the obvious way:
    "-5 degrees" arrived as "5 degrees", so the agent answered about the
    wrong temperature and nothing in the readout showed the sign had gone.
    Reported from use.

    So a dash that is a minus sign stays. Ambiguity resolves towards keeping
    it -- a spurious minus is visible and harmless, a missing one is neither.
    """
    cleaned = _CONTROL.sub("", str(text)).strip()
    if _SIGNED.match(cleaned):
        return cleaned
    return cleaned.lstrip("-‐‑‒–— \t").strip()
_SENTENCE_END = (".", "!", "?", ":", ";", ",")


def make_speakable(text: str) -> str:
    """Flatten markdown-ish agent output into plain prose for TTS."""
    if not text:
        return ""

    text = _CODE_BLOCK.sub(" Code omitted. ", text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _IMAGE.sub(r"\1", text)
    text = _LINK.sub(r"\1", text)
    text = _BOLD.sub(lambda m: m.group(1) or m.group(2), text)
    text = _ITALIC.sub(lambda m: m.group(1) or m.group(2), text)
    text = _HEADER.sub("", text)
    text = _BLOCKQUOTE.sub("", text)

    lines = []
    for line in text.splitlines():
        stripped = _BULLET.sub("", line)
        if stripped != line:
            stripped = stripped.rstrip()
            if stripped and not stripped.endswith(_SENTENCE_END):
                stripped += "."
        lines.append(stripped)
    text = " ".join(line.strip() for line in lines if line.strip())

    text = text.replace("|", " ").replace("*", " ").replace("#", " ")
    text = _EMOJI.sub("", text)
    return _WHITESPACE.sub(" ", text).strip()


# A boundary is .!? followed by whitespace -- but not after a single capital
# initial ("J. Smith"), which is what `\b[A-Z]` describes: a capital that is
# a word on its own.
#
# It used to be `(?<!\d)(?<![A-Z])`, which was too broad on both counts and
# refused to end a sentence after *any* digit or *any* capital: "shipped in
# 2024." and "fix the GPU." were never boundaries, so the rest of the reply
# merged into one long utterance. The decimal case it was guarding does not
# need a guard at all -- the "2.47" period is followed by a digit, and a
# boundary already has to be followed by whitespace.
_BOUNDARY = re.compile(r"(?<!\b[A-Z])[.!?]+(?=\s)")

#: Sentences shorter than this merge forward so TTS does not sound choppy.
MIN_CHUNK_CHARS = 20

#: A code fence. Matters here and not only in make_speakable, because the
#: splitting happens first: `make_speakable` turns a *whole* fenced block
#: into "Code omitted", but it is handed one sentence at a time, so a block
#: containing ". " used to be cut up -- the opening piece became "Code
#: omitted" and every piece after it was read out as code.
_FENCE = "```"


def _next_boundary(buffer: str):
    """The first sentence boundary outside a code fence, or None.

    Inside a fence nothing is a sentence, however much it looks like one: the
    whole block is going to become "Code omitted", and splitting it first
    means the opening piece becomes those two words and every piece after it
    is read out as code, one line at a time.

    A *closed* fence is skipped over, so a boundary after it is still found
    and the emitted chunk carries the complete block for make_speakable to
    flatten. An unclosed one ends the scan: the rest of it may still be on
    its way.
    """
    pos = 0
    while True:
        opens_at = buffer.find(_FENCE, pos)
        end = len(buffer) if opens_at < 0 else opens_at
        match = _BOUNDARY.search(buffer, pos, end)
        if match:
            return match
        if opens_at < 0:
            return None
        closes_at = buffer.find(_FENCE, opens_at + len(_FENCE))
        if closes_at < 0:
            return None
        pos = closes_at + len(_FENCE)


#: Put in the delta stream to mean "nothing more is coming for a while": the
#: agent has gone off to run a tool. Whatever is waiting is spoken now.
#:
#: Without it, "Let me check the logs." sat unspoken until the tool finished,
#: which is exactly the moment it stops being worth saying. A boundary needs
#: the whitespace that follows it, and a text block that ends in a tool call
#: has none until the next block -- after the tool. And anything under
#: MIN_CHUNK_CHARS ("On it.") waits to merge with what comes next, which is
#: the same wait again.
FLUSH = object()


def iter_sentences(deltas):
    """Group a stream of text deltas into speakable sentence chunks."""
    buffer = ""
    pending = ""
    for delta in deltas:
        if delta is FLUSH:
            waiting = (pending + " " + buffer).strip() if pending else buffer.strip()
            pending = buffer = ""
            if waiting:
                yield waiting
            continue
        buffer += delta
        while True:
            match = _next_boundary(buffer)
            if not match:
                break
            sentence = buffer[:match.end()]
            buffer = buffer[match.end():].lstrip()
            candidate = (pending + " " + sentence).strip() if pending else sentence.strip()
            if len(candidate) < MIN_CHUNK_CHARS:
                pending = candidate
                continue
            pending = ""
            yield candidate
    tail = (pending + " " + buffer).strip() if pending else buffer.strip()
    if tail:
        yield tail


# Spoken commands that mean "stop": exact-match against the normalized
# transcript, so an ordinary sentence merely containing "stop" cannot misfire.
_STOP_PHRASES = frozenset({
    "stop", "stop talking", "stop it", "cancel", "cancel that", "never mind",
    "nevermind", "be quiet", "shut up", "thats all", "forget it", "abort",
})


# Ways of saying the conversation is over. They end it the way a stop does
# -- nothing is sent, no follow-up window opens -- so the microphone goes
# back to waiting for the wake word instead of taking the next thing said in
# the room as a turn. Whisper writes "bye bye" as "Bye-bye", which the
# normalizer turns back into two words.
_GOODBYES = frozenset({
    "goodbye", "good bye", "bye", "bye bye", "bye for now", "see you",
    "see you later", "see ya", "talk to you later", "talk later",
    "thats all", "thats it", "im done", "were done", "good night",
    "goodnight",
})

# Said in front of a goodbye without changing what it means: "okay, thanks,
# goodbye". Only ever stripped from the front, so "goodbye okay" is not one.
_GOODBYE_LEAD = frozenset({
    "ok", "okay", "alright", "all", "right", "thanks", "thank", "you",
    "great", "cool", "perfect", "and", "so", "well", "thats",
})

# Stop every agent at once, not only the one the turn was for. Measured with
# Whisper base.en on four Piper voices: "Full stop" came back as the words in
# 8 of 8 clips, never as a bare ".".
_FULL_STOPS = frozenset({
    "full stop", "stop everything", "everybody stop", "everyone stop",
    "stop all", "stop all of it", "emergency stop", "all stop",
})


def _normalize(text: str) -> str:
    norm = re.sub(r"[^a-z ]+", " ", text.lower().replace("'", ""))
    return " ".join(norm.split())


def is_goodbye(text: str) -> bool:
    """True when the transcript says the conversation is over, and no more."""
    words = _normalize(text).split()
    while words and " ".join(words) not in _GOODBYES and words[0] in _GOODBYE_LEAD:
        words = words[1:]
    return bool(words) and " ".join(words) in _GOODBYES


def is_full_stop(text: str) -> bool:
    """True when the transcript asks for everything to stop."""
    return _normalize(text) in _FULL_STOPS


def is_stop_command(text: str) -> bool:
    """True when the transcript is a stop command and nothing else.

    A goodbye and a full stop count: each ends the exchange, so every place
    that already discards a stop discards those too. Callers that must do
    more for a full stop check is_full_stop() first.
    """
    norm = _normalize(text)
    return norm in _STOP_PHRASES or is_full_stop(norm) or is_goodbye(norm)
