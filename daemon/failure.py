"""Why an agent turn failed, in words that are safe to say and to log.

Every failure used to be "Sorry, the agent failed." aloud and "agent error
(text withheld)" in the journal. Both were right to withhold the text: a CLI
that rejects its input often quotes it back, so the error message is speech
as surely as the reply is. But it left nothing to act on. Five turns in a
row failed in this machine's journal on 2026-11-15, about ten seconds each,
and there is no way to tell now whether that was a usage limit, an expired
login or the network.

So the text is *classified* rather than repeated. classify() reads it and
returns one of a fixed set of kinds; spoken() turns a kind into a sentence.
Neither ever puts any of the original text into what is said or logged --
with one exception, a usage limit's reset time, which is extracted by a
pattern that can only match a clock time.

Two kinds also mean the conversation itself is unusable -- it is too long,
or the CLI no longer has it -- and every later turn would fail the same way
until something dropped it. forgets_conversation() says which.
"""
from __future__ import annotations

import re
import time

#: Checked in order; the first match wins. Our own wording first, because it
#: is exact, then the specific before the general -- "refusing to send an API
#: key" is not an expired login, and a 429 is not an outage.
_KINDS: tuple[tuple[str, re.Pattern], ...] = tuple(
    (kind, re.compile(pattern, re.IGNORECASE)) for kind, pattern in (
        # Phase M17: an extra flag or variable Agent Voice never passes
        # (launch_extras.LaunchRefused, our own sentence).
        ("refused", r"agent voice did not start it"),
        ("hung", r"stopped responding after"),
        ("start", r"could not start|exited before it could be asked|"
                  r"command not found|is not installed"),
        ("insecure", r"refusing to send an api key"),
        ("lost", r"no conversation found|session not found|"
                 r"could not find (the )?session|no such session"),
        ("too_long", r"prompt is too long|context (length|window|limit)|"
                     r"maximum context|too many tokens|input length"),
        ("credit", r"credit balance|insufficient (credit|funds|balance)|"
                   r"payment required|\b402\b|billing"),
        ("limit", r"usage limit|limit reached|hit your (\w+ )?limit|"
                  r"rate[ _-]?limit|too many requests|\b429\b|quota"),
        ("auth", r"invalid (api|x-api)[ -]?key|authenticat|unauthori[sz]ed|"
                 r"\b401\b|\b403\b|forbidden|/login|log ?in again|"
                 r"not (logged|signed) in|sign in|oauth|token (has )?expired"),
        ("overloaded", r"overloaded|\b5(00|02|03|29)\b|service unavailable|"
                       r"bad gateway|internal server error|api_error"),
        ("network", r"connection (error|refused|reset)|econn|enotfound|"
                    r"eai_again|getaddrinfo|fetch failed|socket hang up|"
                    r"name or service not known|name resolution|"
                    r"no route to host|network is unreachable|urlerror|"
                    r"timed out|etimedout"),
    ))

KINDS = tuple(kind for kind, _ in _KINDS) + ("unknown",)

#: What each kind sounds like. "{name}" is the agent, as people say it.
_SAID = {
    "refused": "{name} was not started: one of its launch settings is never passed. "
               "Agent details, Advanced, says which.",
    "hung": "{name} stopped responding, so I stopped it.",
    "start": "{name} would not start.",
    "insecure": "{name} needs an https address before I will send it your key.",
    "lost": "{name} lost track of our conversation, so the next thing you "
            "say starts a new one.",
    "too_long": "This conversation has grown too long for {name}, so the next "
                "thing you say starts a new one.",
    "credit": "{name} has run out of credit.",
    "limit": "{name} has hit its usage limit.",
    "auth": "{name} needs you to sign in again.",
    "overloaded": "{name} is having trouble on its end. Try again in a moment.",
    "network": "{name} could not reach its service. Check your connection.",
    "unknown": "Sorry, {name} failed.",
}

#: How a few agents are said aloud. Anything else is capitalised.
_NAMES = {"agy": "Antigravity", "endpoint": "the endpoint", "": "the agent"}


def classify(text: str | None) -> str:
    """One of KINDS. Never any of `text` itself."""
    for kind, pattern in _KINDS:
        if text and pattern.search(text):
            return kind
    return "unknown"


def forgets_conversation(kind: str) -> bool:
    """Whether every later turn in this conversation would fail the same way."""
    return kind in ("lost", "too_long")


def _resets_at(text: str) -> str | None:
    """When a usage limit lifts, if the message says -- as a clock time only.

    Two shapes are known: "resets 3pm" / "resets at 3:30 PM" in words, and
    "usage limit reached|1731686400", an epoch. Each pattern matches only
    digits and am/pm, so nothing else the message carries can come through.
    """
    m = re.search(r"\bresets?\s+(?:at\s+)?(\d{1,2}(?::\d{2})?)\s*([ap])\.?m\b",
                  text, re.IGNORECASE)
    if m:
        # "3 PM", spaced, which a voice reads as a time; "3PM" it spells.
        return f"{m.group(1)} {m.group(2).upper()}M"
    m = re.search(r"limit reached\|(\d{10})\b", text, re.IGNORECASE)
    if m:
        return time.strftime("%-I:%M %p", time.localtime(int(m.group(1))))
    return None


def spoken(kind: str, agent: str | None, text: str | None = None) -> str:
    """The sentence to say for `kind`, naming `agent` the way people do."""
    name = _NAMES.get(agent or "") or (agent or "").capitalize()
    said = _SAID.get(kind, _SAID["unknown"]).format(name=name)
    said = said[0].upper() + said[1:]       # "the endpoint" opening a sentence
    if kind == "limit" and text:
        when = _resets_at(text)
        if when:
            said += f" It resets at {when}."
    return said
