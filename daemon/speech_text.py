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


#: Where a sentence may be cut for synthesis without cutting a phrase: after
#: a comma, semicolon or colon, or around a spaced dash.
_CLAUSE = re.compile(r"[,;:](?=\s)|\s[-\u2013\u2014](?=\s)")

#: A head shorter than this is a word or two ("Sure,") and renders in a
#: tenth of a second anyway; cutting there only adds a join.
HEAD_MIN_CHARS = 12
#: What has to be left after a cut, so the second piece is a phrase too.
TAIL_MIN_CHARS = 20
#: Sentences shorter than this are not worth splitting: even the slowest
#: voice measured (ryan-high, about 2x realtime) renders them in well under
#: a second.
SPLIT_FROM_CHARS = 50
#: A head is looked for this far in, no further. Past it the "head" is most
#: of the sentence and saves nothing.
HEAD_MAX_CHARS = 80
#: Later sentences longer than this are cut so rendering stays ahead.
LONG_CHARS = 160


def _clause_cuts(sentence: str) -> list[int]:
    """Offsets just past each clause break, outside code."""
    if _FENCE in sentence or "`" in sentence:
        return []
    return [m.end() for m in _CLAUSE.finditer(sentence)]


def split_head(sentence: str) -> list[str]:
    """Cut a short opening off a long sentence, for a faster first sound.

    Piper renders an entire utterance before it gives back any audio, so the
    first sound of a reply waits for the whole first sentence: 3.6 seconds
    for 158 characters on ryan-high, measured on this machine. Rendered on
    its own, a clause of twenty characters takes 0.3 to 0.5, and the rest is
    rendered while it plays. Cut only at a clause break, where a speaker
    would pause anyway.
    """
    sentence = sentence.strip()
    if len(sentence) < SPLIT_FROM_CHARS:
        return [sentence] if sentence else []
    for at in _clause_cuts(sentence):
        if at > HEAD_MAX_CHARS:
            break
        head, rest = sentence[:at].strip(), sentence[at:].strip()
        if len(head) >= HEAD_MIN_CHARS and len(rest) >= TAIL_MIN_CHARS:
            return [head, rest]
    return [sentence]


def split_long(sentence: str, limit: int = LONG_CHARS) -> list[str]:
    """Cut a very long sentence at clause breaks into pieces under `limit`,
    where it can be: a piece with no break in it stays whole."""
    sentence = sentence.strip()
    pieces: list[str] = []
    while len(sentence) > limit:
        cuts = [at for at in _clause_cuts(sentence)
                if at >= HEAD_MIN_CHARS and len(sentence) - at >= TAIL_MIN_CHARS]
        under = [at for at in cuts if at <= limit]
        if not cuts:
            break
        at = under[-1] if under else cuts[0]
        pieces.append(sentence[:at].strip())
        sentence = sentence[at:].strip()
    if sentence:
        pieces.append(sentence)
    return pieces


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


#: "new chat" and the ways it is said. Whole transcript only, like a stop.
_NEW_CHATS = frozenset({
    "new chat", "a new chat", "start a new chat", "new conversation",
    "start a new conversation", "fresh chat", "start a fresh chat",
    "start a fresh conversation", "lets start a new chat",
    "lets start a new conversation",
})
_CONTINUE = re.compile(
    r"^(?:please |can you |could you |lets )?"
    r"(?:continue|resume|go back to|pick up|reopen)"
    r"(?: the| our| my| that)? (?:chat|conversation)"
    r"(?:(?: about| on| from| where| with| we had about) (?P<about>.+))?$")


def chat_command(text: str) -> tuple[str, str]:
    """("new", "") for "new chat", ("continue", what) for "continue the chat
    about the HUD" -> "the hud"... or ("", "") for anything else.

    Matched on the whole transcript, so "can you continue the work" or a
    sentence that merely mentions a chat is an ordinary request."""
    norm = _normalize(text)
    if norm in _NEW_CHATS:
        return "new", ""
    m = _CONTINUE.match(norm)
    if m:
        return "continue", (m.group("about") or "").strip()
    return "", ""


#: Keep the microphone open: no wake word until it is closed or goes quiet.
_OPEN_MIC = frozenset({
    "keep listening", "keep on listening", "stay listening", "lets keep talking",
    "keep talking with me", "lets talk", "open mic", "open the mic",
    "keep the mic open", "leave the mic open", "listen to me",
    "start listening", "dont stop listening", "lets have a conversation",
})
#: Close it again. A goodbye and a full stop close it too; a plain "stop"
#: stops the reply and leaves it open.
_CLOSE_MIC = frozenset({
    "stop listening", "close the mic", "close mic", "mic off",
    "turn the mic off", "stop the open mic", "end the open mic",
    "wait for your name", "wait for the wake word", "go back to sleep",
    "go to sleep",
})


def open_mic_command(text: str) -> str:
    """"open" for "keep listening", "close" for "stop listening", else ""."""
    norm = _normalize(text)
    for lead in ("please ", "okay ", "ok "):
        if norm.startswith(lead):
            norm = norm[len(lead):]
    if norm in _OPEN_MIC:
        return "open"
    if norm in _CLOSE_MIC:
        return "close"
    return ""


#: Move the conversation into a terminal, where typing continues it.
_HANDOFF = re.compile(
    r"^(?:please |can you |could you |lets )?"
    r"(?:move|take|hand|send|open|continue|carry on|put|switch)"
    r"(?: this| it| that| the chat| this chat| the conversation| this conversation)?"
    r"(?: over)? (?:to|in|into|on) (?:a |the |my )?terminal$")


def is_handoff(text: str) -> bool:
    """True for "move this to a terminal" and the ways it is said, whole."""
    return bool(_HANDOFF.match(_normalize(text)))


#: "pass this to Sora" (merged plan, Phase 15): the conversation goes to
#: another agent. "pass" or "send", never "hand", which is the terminal's
#: word. What follows the name is the user's request riding with it.
_PASS = re.compile(
    r"^\W*(?:please\s+|can you\s+|could you\s+|now\s+)?(?:pass|send)\s+"
    r"(?:(?:this|it|that|the chat|this chat|the conversation|this conversation)\s+)?"
    r"(?:over\s+)?to\s+(?P<rest>.+)$", re.IGNORECASE | re.DOTALL)
#: "Sora, take over", said to the agent that is to take it.
_TAKE_OVER = frozenset({
    "take over", "take it over", "take this over", "you take over",
    "take over from here", "you take it from here", "take it from here",
    "please take over", "can you take over", "take over please",
})


def pass_command(text: str, names) -> tuple[str, str]:
    """(name, request) for "pass this to Sora, and ask her about the
    weather" -> ("sora", "ask her about the weather"); ("", "") for anything
    else, including a name that is no agent's ("pass this to the left").

    `names` are the names an agent may be called by -- display names and
    wake phrases, lower case. Matched at the start of what follows "to",
    longest first, on whole words."""
    m = _PASS.match(str(text or "").strip())
    if not m:
        return "", ""
    rest = m.group("rest").strip()
    words = rest.split()
    plain = [re.sub(r"^[^\w']+|[^\w']+$", "", w).lower() for w in words]
    for name in sorted({n for n in names if n}, key=len, reverse=True):
        parts = name.lower().split()
        if plain[:len(parts)] == parts:
            request = " ".join(words[len(parts):])
            request = re.sub(r"^[\s,.:;!?—–-]*(?:and\s+(?:then\s+)?)?", "", request,
                             flags=re.IGNORECASE)
            return name.lower(), request.strip()
    return "", ""


def is_take_over(text: str) -> bool:
    """True for "take over" and the ways it is said, whole."""
    return _normalize(text) in _TAKE_OVER
