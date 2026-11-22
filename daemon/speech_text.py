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
from dataclasses import dataclass, field

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


# --- the command table, and commands inside sentences (phase M4) -------------
#
# Every spoken command in one place: what it is called, how it is said, what
# it does, where in a sentence it may sit, and the one fixed sentence said
# out loud when it fires from inside a longer one. The phrase sets above are
# the table's phrases, unchanged -- `alone` mode is exactly the behaviour
# before M4, and the functions above are still what decides it.
#
# What is new is a command found *inside* something longer: "take notes, and
# keep listening" opens the microphone and sends "take notes". That is a
# command firing on words nobody meant as one, if it is wrong, so it is
# narrow on purpose: a short list of phrases per command (the subset of its
# phrases that do not turn up in ordinary talk), only at the positions the
# policy table allows, and never
#
#   - with anything after the verb ("stop listening to that song"),
#   - after a negation ("don't keep listening"), which is the same rule:
#     the phrase must sit at a boundary, and "don't" is not one,
#   - in reported or quoted speech ("he said, keep listening"),
#   - when anything else in what was said is a command too.
#
# The contexts it must also never fire in -- dictation, partial text, the
# agent's own voice heard back, a locked screen -- are the daemon's to know,
# and are checked where it calls this (`Daemon.sentence_command`).

#: Where a command may be found in what was said.
POSITIONS = ("alone", "start", "end", "clause")

#: `commandsInSentences`. "alone" is the behaviour before M4.
COMMAND_MODES = ("alone", "edges", "clause")

_MODE_POSITIONS = {
    "alone": frozenset({"alone"}),
    "edges": frozenset({"alone", "start", "end"}),
    "clause": frozenset({"alone", "start", "end", "clause"}),
}


def command_mode(value) -> str:
    """A `commandsInSentences` value as one of COMMAND_MODES. Anything else
    -- unset, misspelt, the wrong type -- is "alone": commands only when
    said on their own, the behaviour nobody has to opt out of."""
    return value if isinstance(value, str) and value in COMMAND_MODES else "alone"


@dataclass(frozen=True)
class Command:
    """One spoken command. `phrases` are the whole-transcript forms (for a
    command matched by a pattern, examples of it, and `pattern` its source);
    `in_sentence` the forms that count inside something longer."""
    id: str
    label: str
    effect: str
    where: frozenset
    phrases: frozenset = frozenset()
    pattern: str = ""
    in_sentence: tuple = ()
    #: False only where the command is heard without a wake word: "full
    #: stop" with the sherpa-onnx engine (fullStopAnytime). Every command
    #: works in a follow-up window and on the open microphone.
    needs_wake: bool = True
    #: What does the same from a terminal, or "" when nothing does.
    cli: str = ""
    #: Said once, and shown, when it fires from inside a sentence. Fixed
    #: text: never a model's, never built from what was said.
    said: str = ""
    #: No follow-up window after the turn it fires in: back to the wake word.
    ends: bool = False

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "effect": self.effect,
            "where": [p for p in POSITIONS if p in self.where],
            "phrases": sorted(self.phrases),
            "pattern": self.pattern,
            "in_sentence": list(self.in_sentence),
            "needs_wake": self.needs_wake,
            "cli": self.cli,
            "said": self.said,
            "ends": self.ends,
        }


_ALL = frozenset(POSITIONS)

#: Checked in this order, which is the order the run loop checks them in:
#: a full stop before a goodbye before a stop, then the open microphone,
#: the terminal, passing, and last the chats (`Daemon.answer`).
COMMANDS = (
    Command(
        id="full_stop", label="Full stop",
        effect="Stops every agent at once: every reply, task and follow-up "
               "window, and the open mic.",
        where=frozenset({"alone"}), phrases=_FULL_STOPS, needs_wake=False,
        cli="agentvoice interrupt"),
    Command(
        id="goodbye", label="Goodbye",
        effect="Ends the conversation: the open mic closes and it waits for "
               "the wake word again.",
        where=frozenset({"alone", "end"}), phrases=_GOODBYES,
        in_sentence=("goodbye", "good bye", "bye", "bye bye", "bye for now",
                     "see you later", "talk to you later", "good night",
                     "goodnight"),
        said="Goodbye.", ends=True),
    Command(
        id="stop", label="Stop",
        effect="Stops the reply, or cancels a turn not yet sent: nothing "
               "goes to the agent.",
        where=frozenset({"alone"}), phrases=_STOP_PHRASES,
        cli="agentvoice interrupt"),
    Command(
        id="open_mic", label="Open mic",
        effect="Listens without the wake word until it is closed or nothing "
               "is said for a while.",
        where=_ALL, phrases=_OPEN_MIC,
        in_sentence=("keep listening", "keep on listening", "stay listening",
                     "open mic", "open the mic", "keep the mic open",
                     "leave the mic open"),
        cli="agentvoice open-mic on [AGENT_ID]", said="Open mic on."),
    Command(
        id="close_mic", label="Close the open mic",
        effect="Closes the open mic: back to the wake word.",
        where=frozenset({"alone", "start", "end"}), phrases=_CLOSE_MIC,
        in_sentence=("stop listening", "close the mic", "close mic", "mic off",
                     "turn the mic off", "stop the open mic", "end the open mic"),
        cli="agentvoice open-mic off", said="Open mic off.", ends=True),
    Command(
        id="handoff", label="Move to a terminal",
        effect="Carries the chat on in a terminal, and stays out of it until "
               "the terminal closes.",
        where=frozenset({"alone"}), pattern=_HANDOFF.pattern,
        phrases=frozenset({"move this to the terminal", "continue in a terminal",
                           "hand it over to my terminal"})),
    Command(
        id="pass", label="Pass to another agent",
        effect="Passes the conversation to the agent named; anything said "
               "after the name is its request.",
        where=frozenset({"alone", "start"}), pattern=_PASS.pattern,
        phrases=frozenset({"pass this to NAME",
                           "pass this to NAME and ask about the weather"}),
        cli="agentvoice pass TO [--from ID] < brief"),
    Command(
        id="take_over", label="Take over",
        effect="Said to an agent: it takes the conversation over from the "
               "one spoken to last.",
        where=frozenset({"alone"}), phrases=_TAKE_OVER,
        cli="agentvoice pass TO --from ID < brief"),
    Command(
        id="new_chat", label="New chat",
        effect="Starts a new chat with that agent.",
        where=frozenset({"alone", "start"}), phrases=_NEW_CHATS,
        in_sentence=("new chat", "start a new chat", "new conversation",
                     "start a new conversation", "fresh chat",
                     "start a fresh chat", "start a fresh conversation",
                     "lets start a new chat", "lets start a new conversation"),
        cli="agentvoice chats new [AGENT_ID]", said="New chat."),
    Command(
        id="continue_chat", label="Continue a chat",
        effect="Picks up one of that agent's saved chats, found by what it "
               "was about.",
        where=frozenset({"alone", "start"}), pattern=_CONTINUE.pattern,
        phrases=frozenset({"continue the chat about the HUD",
                           "resume our conversation",
                           "go back to the chat about the trip"}),
        cli="agentvoice chats continue ID [AGENT_ID]",
        said="Continuing that chat."),
)

_BY_ID = {c.id: c for c in COMMANDS}


def command(command_id: str) -> Command:
    """The table's entry for `command_id`."""
    return _BY_ID[command_id]


@dataclass(frozen=True)
class Found:
    """A command found in what was said.

    `where` is one of POSITIONS. `rest` is what is left for the agent, ""
    when nothing is. `arg` is a chat's topic ("continue") or an agent's
    name ("pass"). `phrase` is the command's words as matched, normalized.
    `exact` says it was matched by the rules from before M4, which the run
    loop already acts on: everything else here is new, and is what
    `Daemon.sentence_command` acts on.
    """
    command: Command
    where: str
    rest: str = ""
    arg: str = ""
    phrase: str = ""
    exact: bool = False
    extra: dict = field(default_factory=dict, compare=False)


def _exact(text: str, names) -> Found | None:
    """The command `text` is by the rules from before M4, or None."""
    norm = _normalize(text)
    if is_full_stop(text):
        return Found(command("full_stop"), "alone", phrase=norm, exact=True)
    if is_goodbye(text):
        return Found(command("goodbye"), "alone", phrase=norm, exact=True)
    if is_stop_command(text):
        return Found(command("stop"), "alone", phrase=norm, exact=True)
    mic = open_mic_command(text)
    if mic:
        return Found(command("open_mic" if mic == "open" else "close_mic"),
                     "alone", phrase=norm, exact=True)
    if is_handoff(text):
        return Found(command("handoff"), "alone", phrase=norm, exact=True)
    name, request = pass_command(text, names)
    if name:
        # The request riding after the name was already "start".
        return Found(command("pass"), "start" if request else "alone",
                     rest=request, arg=name, phrase=norm, exact=True)
    if is_take_over(text):
        return Found(command("take_over"), "alone", phrase=norm, exact=True)
    kind, about = chat_command(text)
    if kind:
        return Found(command("new_chat" if kind == "new" else "continue_chat"),
                     "alone", arg=about, phrase=norm, exact=True)
    return None


# A word, with an apostrophe inside it ("don't", "that's") kept as part of
# it. Anything between two words is a gap, and the gaps are where the
# punctuation lives.
_WORD = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)*")
#: A gap holding one of these ends a clause: Whisper's punctuation.
_BREAK = re.compile(r"[.!?;:,…]|\s[-‐‑‒–—]+\s|[–—]")
#: The end of a sentence rather than of a clause.
_SENTENCE_BREAK = re.compile(r"[.!?;…]")
#: Quotation marks. An apostrophe inside a word belongs to the word, so one
#: left in a gap is a quote.
_QUOTES = "\"“”„«»'‘’"

#: May stand between a clause's start and the command: "…, and please keep
#: listening". Never a negation or a verb of saying, which is what keeps
#: "don't keep listening" and "he said keep listening" out.
_JOINERS = frozenset({
    "and", "then", "so", "now", "please", "okay", "ok", "alright", "also",
    "just", "actually", "oh", "um", "uh", "well", "hey",
})
#: "can you keep listening": a joiner only as the pair. "You" on its own is
#: the start of a sentence about the agent -- "You keep listening, but you
#: never act" -- and not a request to it.
_POLITE = frozenset({"can", "could", "would", "will"})
#: Without any punctuation in the transcript, these mark where a clause
#: starts or ends: "take notes and keep listening because I might pause".
_CUES_BEFORE = frozenset({"and", "then", "so", "but", "also"})
_CUES_AFTER = frozenset({"and", "then", "so", "but", "because", "cause", "cos",
                         "since", "while", "till", "until"})
#: May follow the command at the very end: "…, keep listening please".
_TRAILING = frozenset({"please", "thanks", "thank", "you", "now", "okay", "ok",
                       "then"})
#: Words that say nothing to an agent. A rest made only of these (and of
#: the agents' names) is no rest: "Alright then, keep listening" sends
#: nothing. Not "yes" or "no", which answer something.
_FILLER = _JOINERS | _TRAILING | _POLITE | frozenset({
    "all", "right", "hi", "hello", "great", "cool", "perfect", "good", "fine",
    "sure", "thats", "it",
})
#: The clause before ends in one of these: what follows is quoted, not said
#: to us. "He said, keep listening." "The button says: open mic."
_REPORTING = frozenset({
    "say", "says", "said", "saying", "tell", "tells", "told", "telling",
    "ask", "asks", "asked", "asking", "hear", "hears", "heard", "call",
    "calls", "called", "mean", "means", "meant", "word", "words", "phrase",
    "command", "like", "write", "wrote", "type", "typed", "read", "reads",
    "shout", "shouted", "yell", "yelled", "whisper", "whispered", "go",
    "goes", "went", "reply", "replied", "answer", "answered", "quote",
    "sing", "sings", "sang", "song", "titled", "named", "lyrics", "sign",
})

#: "continue the chat about X." inside a sentence: the topic runs to the
#: end of its sentence, and something has to follow it.
_CONTINUE_HEAD = re.compile(
    r"^\W*(?:(?:okay|ok|alright|so|now|and|please)\W+)*"
    r"(?:(?:please|can you|could you|let['’]?s)\s+)?"
    r"(?P<verb>continue|resume|go back to|pick up|reopen)"
    r"(?:\s+(?:the|our|my|that))?\s+(?:chat|conversation)\b",
    re.IGNORECASE)
_CONTINUE_TOPIC = re.compile(r"^\s+(?:about|on|from|where|with|we had about)\s+",
                             re.IGNORECASE)
_CONTINUE_BARE = re.compile(r"^\s*[.!?;:,](?=\s)(?P<rest>.*)$", re.DOTALL)
#: A full stop after one of these, or after a single letter, is not the end
#: of a sentence: "the chat about Dr. Smith" keeps its topic whole.
_ABBREVIATIONS = frozenset({"dr", "mr", "mrs", "ms", "st", "vs", "etc", "eg",
                            "ie", "jr", "sr", "prof", "no", "approx"})


def _phrase_table():
    """(words, command) for every in-sentence phrase, longest first."""
    out = []
    for c in COMMANDS:
        for p in c.in_sentence:
            out.append((tuple(p.split()), c))
    out.sort(key=lambda wc: len(wc[0]), reverse=True)
    return tuple(out)


_PHRASES = _phrase_table()


def _hits(words: list[str]) -> list[tuple[int, int, Command]]:
    """Every in-sentence phrase in `words` as (start, end, command). Where
    two overlap the longer wins: "stop the open mic" is not "open mic"."""
    taken = [False] * len(words)
    hits = []
    for phrase, cmd in _PHRASES:
        n = len(phrase)
        for i in range(len(words) - n + 1):
            if tuple(words[i:i + n]) == phrase and not any(taken[i:i + n]):
                hits.append((i, i + n, cmd))
                for k in range(i, i + n):
                    taken[k] = True
    hits.sort()
    return hits


def _clean_rest(rest: str, names) -> str:
    """`rest` tidied at the cut, or "" when nothing in it says anything."""
    rest = rest.strip().strip(",;:-‐‑‒–— ").strip()
    words = [w.lower().replace("'", "").replace("’", "")
             for w in _WORD.findall(rest)]
    named = {w for n in names for w in str(n).lower().split()}
    if not words or all(w in _FILLER or w in named for w in words):
        return ""
    return rest[0].upper() + rest[1:]


def _continue_in_sentence(text: str) -> tuple[str, str, str] | None:
    """(topic, phrase, rest) for "continue the chat about X. <rest>", or None."""
    head = _CONTINUE_HEAD.match(text)
    if not head:
        return None
    after = text[head.end():]
    m = _CONTINUE_TOPIC.match(after)
    if m:
        body = after[m.end():]
        for stop in re.finditer(r"[.!?;:](?=\s)", body):
            word = re.search(r"(\w+)\W*$", body[:stop.start()])
            word = word.group(1).lower() if word else ""
            if stop.group() == "." and (len(word) == 1 or word in _ABBREVIATIONS):
                continue
            about = _normalize(body[:stop.start()])
            if not about:
                return None
            return (about,
                    _normalize(text[head.start("verb"):head.end() + m.end() + stop.start()]),
                    body[stop.end():])
        return None
    m = _CONTINUE_BARE.match(after)
    if m:
        return "", _normalize(text[head.start("verb"):head.end()]), m.group("rest")
    return None


def _in_sentence(text: str, allowed: frozenset, names) -> Found | None:
    """A command inside something longer, at a position `allowed` lets it
    fire from -- or None, which is also the answer whenever it is unclear."""
    spans = [(m.start(), m.end()) for m in _WORD.finditer(text)]
    words = [text[a:b].lower().replace("'", "").replace("’", "") for a, b in spans]
    n = len(words)
    if not n:
        return None
    named = {w for nm in names for w in str(nm).lower().split()}

    def gap(k: int) -> str:
        """What lies before word k (k == n: after the last word)."""
        left = spans[k - 1][1] if k > 0 else 0
        right = spans[k][0] if k < n else len(text)
        return text[left:right]

    punctuated = any(_BREAK.search(gap(k)) for k in range(1, n))

    found = []          # (where, start_char, end_char, phrase, command, arg)
    hits = _hits(words)
    cont = _continue_in_sentence(text) if "start" in allowed else None
    if cont is not None:
        about, phrase, rest = cont
        found.append(("start", None, None, phrase, command("continue_chat"),
                      about, rest))
    # Quotation marks open and close across the gaps; a phrase that begins
    # inside a quote is somebody else's words.
    quoted = []
    inside = False
    for k in range(n):
        for ch in gap(k):
            if ch in "\"'‘’":
                inside = not inside
            elif ch in "“„«":
                inside = True
            elif ch in "”»":
                inside = False
        quoted.append(inside)

    def joiner(x: int) -> bool:
        w = words[x]
        if w in _JOINERS or w in named:
            return True
        if w == "you":
            return x > 0 and words[x - 1] in _POLITE
        return w in _POLITE and x + 1 < n and words[x + 1] == "you"

    for i, j, cmd in hits:
        if quoted[i] or any(ch in _QUOTES for ch in gap(i) + gap(j)):
            found.append((None, i, j, " ".join(words[i:j]), cmd, "", ""))
            continue
        # Before: back over joiners to where the clause starts.
        k = i
        while k > 0 and joiner(k - 1) \
                and not (punctuated and _BREAK.search(gap(k))):
            k -= 1
        at_start = all(joiner(x) for x in range(i))
        joined = words[k:i]
        if at_start:
            before = True
        elif punctuated:
            before = bool(_BREAK.search(gap(k)))
        else:
            before = any(w in _CUES_BEFORE for w in joined)
        # Said, told, called...: the clause before introduces a quotation.
        # Across a comma or a colon -- "she told me: stop listening" -- and
        # not across the end of a sentence: "I heard you. Keep listening."
        if not at_start and k > 0 and not _SENTENCE_BREAK.search(gap(k)):
            x = k - 1
            while x >= max(0, k - 3):
                if words[x] in _REPORTING:
                    before = False
                    break
                if x > 0 and _BREAK.search(gap(x)):
                    break
                x -= 1
        # After: over "please" and the like to where the clause ends.
        m = j
        while m < n and words[m] in _TRAILING \
                and not (punctuated and _BREAK.search(gap(m))):
            m += 1
        at_end = m == n
        if at_end:
            after = True
        elif punctuated:
            after = bool(_BREAK.search(gap(m)))
        else:
            # Right after the phrase, before "then" was walked over.
            after = j < n and words[j] in _CUES_AFTER
        # "Keep listening? Why would I?" is a question about it, not a
        # request -- unless asked as one: "can you keep listening?"
        asked = "?" in gap(m) and not any(
            words[x] == "you" and x > 0 and words[x - 1] in _POLITE
            for x in range(k, i))
        if asked:
            where = None
        elif at_start and at_end:
            where = "start" if "start" in cmd.where else "end"
        elif at_start and after:
            where = "start"
        elif at_end and before:
            where = "end"
        elif before and after:
            where = "clause"
        else:
            where = None
        found.append((where, i, j, " ".join(words[i:j]), cmd, "",
                      (k, m)))

    # One command, at one place, or nothing: two of them -- or one said
    # twice, or the same words where they cannot fire -- is not something
    # to guess between.
    if len(found) != 1:
        return None
    where, i, j, phrase, cmd, arg, extra = found[0]
    if where is None or where not in allowed or where not in cmd.where:
        return None
    if cmd.id == "continue_chat":
        rest = extra
    else:
        k, m = extra
        if where == "start":
            rest = text[spans[m][0]:] if m < n else ""
        elif where == "end":
            rest = text[:spans[k - 1][1]] if k > 0 else ""
        else:
            rest = (text[:spans[k - 1][1]] + gap(m).rstrip() + " "
                    + text[spans[m][0]:])
    rest = _clean_rest(rest, names)
    # Whatever is left must not be a command of its own either: "keep
    # listening. Stop." is two things, and neither wins.
    if rest and (_exact(rest, names) is not None
                 or _hits([w.lower().replace("'", "").replace("’", "")
                           for w in _WORD.findall(rest)])):
        return None
    if cmd.id == "continue_chat" and not rest:
        return None         # all of it was the topic: the rule before M4's
    return Found(cmd, where, rest=rest, arg=arg, phrase=phrase)


def find_command(text: str, mode: str = "alone", names=()) -> Found | None:
    """The command in `text`, or None for an ordinary request.

    Matched on the transcript as Whisper wrote it, before its punctuation is
    thrown away, because the punctuation is what says where a clause ends.
    A command said on its own -- the rules before M4, which hold in every
    mode -- is found first. Then, if `mode` allows it, one at the start or
    end of what was said ("edges"), or in a clause of its own ("clause"),
    as the policy in each command's `where` permits. `names` are what the
    agents answer to: for "pass this to …", and so that "Hey Jarvis, keep
    listening" leaves nothing to send.
    """
    text = str(text or "")
    names = tuple(n for n in (names or ()) if n)
    found = _exact(text, names)
    allowed = _MODE_POSITIONS[command_mode(mode)]
    if found is not None:
        # The rule before M4 takes everything after "about" as the topic,
        # to the end, punctuation and all. Where a sentence plainly ends
        # first -- "continue the chat about the HUD. What did we pick?" --
        # a mode that reads sentences gives the question to the agent.
        if found.command.id == "continue_chat" and "start" in allowed:
            split = _in_sentence(text, allowed, names)
            if split is not None and split.command.id == "continue_chat":
                return split
        return found
    if allowed == _MODE_POSITIONS["alone"]:
        return None
    return _in_sentence(text, allowed, names)


#: Said within this many seconds after an in-sentence open-mic command
#: finished being answered, these undo it.
UNDO_S = 3.0
_UNDO = frozenset({"no", "no no", "nope", "cancel that", "no cancel that",
                   "undo", "undo that", "not that"})


def is_undo(text: str) -> bool:
    """True for "no" and "cancel that", said on their own."""
    return _normalize(text) in _UNDO


def heard_back(phrase: str, said: str) -> bool:
    """True when the words of `phrase` occur, in order, in `said` -- which
    is how the agent's own voice, picked up by the microphone, would bring
    a command into a transcript."""
    p, s = _normalize(phrase).split(), _normalize(said).split()
    return bool(p) and any(s[i:i + len(p)] == p for i in range(len(s) - len(p) + 1))


def table(names_by_agent=None, mode: str = "alone") -> dict:
    """The table as data, for `agentvoice commands --json` and the pages
    that list it. `names_by_agent` is [{"id", "label", "phrase"}]."""
    return {
        "mode": command_mode(mode),
        "modes": list(COMMAND_MODES),
        "positions": list(POSITIONS),
        "undo": {"seconds": UNDO_S, "phrases": sorted(_UNDO)},
        "commands": [c.as_dict() for c in COMMANDS],
        "wake_phrases": list(names_by_agent or []),
    }
