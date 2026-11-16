"""A failed turn says why, without repeating anything it was told.

The journal for 2026-11-15 has five failures in a row, each "agent error
(text withheld)" and "Sorry, the agent failed." out loud. Withholding was
right -- an error message can quote the prompt -- and useless. These pin the
middle path: the reason, from a fixed list, and never the text.
"""
from __future__ import annotations

import pytest

import failure
from adapters.base import Chunk

# Shaped like what each CLI and service actually returns. The Claude Code
# ones are from its result envelopes; the HTTP ones are what openai_compat
# builds from an HTTPError; the rest are this project's own wording.
SAMPLES = {
    "hung": ["claude stopped responding after 90s",
             "http://mini:8642/v1 stopped responding after 60s"],
    "start": ["could not start claude: [Errno 2] No such file or directory",
              "claude exited before it could be asked"],
    "insecure": ["refusing to send an API key to http://10.0.0.5 over plain http"],
    "lost": ["No conversation found with session ID: 0b69de35-c446"],
    "too_long": ["Prompt is too long",
                 "input length and `max_tokens` exceed context limit: "
                 "198000 + 21333 > 200000"],
    "credit": ["Credit balance is too low"],
    "limit": ["Claude AI usage limit reached|1731686400",
              "5-hour limit reached ∙ resets 3pm",
              "You've hit your limit · resets 7:30 PM",
              "HTTP 429: Too Many Requests",
              'API Error: 429 {"type":"error","error":{"type":"rate_limit_error"}}'],
    "auth": ["Invalid API key · Please run /login",
             "OAuth token has expired. Please obtain a new token.",
             "HTTP 401: Unauthorized",
             'API Error: 401 {"error":{"type":"authentication_error"}}'],
    "overloaded": ['API Error: 529 {"error":{"type":"overloaded_error",'
                   '"message":"Overloaded"}}',
                   "HTTP 503: Service Unavailable",
                   'API Error: 500 {"error":{"type":"api_error"}}'],
    "network": ["API Error: Connection error.",
                "URLError: <urlopen error [Errno -3] Temporary failure in "
                "name resolution>",
                "fetch failed", "Request timed out."],
    "unknown": ["codex turn failed", "", None,
                "unrecognized arguments: how much did I spend on rent"],
}


@pytest.mark.parametrize("kind, text", [(k, t) for k, ts in SAMPLES.items()
                                        for t in ts])
def test_each_failure_is_named(kind, text):
    assert failure.classify(text) == kind


def test_every_kind_has_something_to_say():
    for kind in failure.KINDS:
        assert failure.spoken(kind, "claude").startswith(
            ("Claude", "This", "Sorry")), kind


def test_what_is_said_never_carries_the_message():
    """The prompt quoted back inside an error must not be read out."""
    said = failure.spoken("unknown", "claude",
                          "unrecognized arguments: how much did I spend on rent")
    assert said == "Sorry, Claude failed."


def test_a_usage_limit_says_when_it_lifts():
    assert failure.spoken("limit", "claude", "5-hour limit reached ∙ resets 3pm") \
        == "Claude has hit its usage limit. It resets at 3 PM."
    assert "resets at 7:30 PM" in failure.spoken(
        "limit", "claude", "You've hit your limit · resets 7:30 PM")
    epoch = failure.spoken("limit", "claude", "usage limit reached|1731686400")
    assert "It resets at" in epoch and epoch.endswith("M.")


def test_a_usage_limit_without_a_time_says_nothing_about_one():
    assert failure.spoken("limit", "codex", "HTTP 429: Too Many Requests") \
        == "Codex has hit its usage limit."


def test_agents_are_named_the_way_people_say_them():
    assert failure.spoken("start", "agy") == "Antigravity would not start."
    assert failure.spoken("start", "endpoint") == "The endpoint would not start."
    assert "too long for the endpoint" in failure.spoken("too_long", "endpoint")
    assert failure.spoken("unknown", None) == "Sorry, the agent failed."


def test_only_a_broken_conversation_is_dropped():
    assert failure.forgets_conversation("lost")
    assert failure.forgets_conversation("too_long")
    for kind in set(failure.KINDS) - {"lost", "too_long"}:
        assert not failure.forgets_conversation(kind), kind


# --- in a turn ----------------------------------------------------------------

class Failing:
    name = "claude"

    def __init__(self, error):
        self.error = error

    def send(self, text, session_id=None):
        yield Chunk(session_id=session_id)
        yield Chunk(error=self.error)

    def cancel(self):
        pass


def test_the_reason_is_said_and_logged_but_not_the_text(daemon, capsys):
    daemon.agent = Failing("You've hit your limit · resets 7pm "
                           "while answering: my bank pin is 4421")
    last = {"transcript": "x"}
    daemon.answer("what is my bank pin", last)
    out = capsys.readouterr().out
    assert daemon.speaker.said == ["Claude has hit its usage limit. It resets at 7 PM."]
    assert "agent error: limit" in out
    assert "4421" not in out and "bank pin" not in out
    assert last["reply"] == daemon.speaker.said[0], \
        "the panel should show why, where the reply would have been"


def test_a_lost_conversation_is_not_resumed_again(daemon):
    """Otherwise every later turn resumes it and fails identically."""
    daemon.session_id = "0b69de35"
    daemon.agent = Failing("No conversation found with session ID: 0b69de35")
    daemon.answer("hello", {"transcript": "x"})
    assert daemon.session_id is None
    assert "starts a new one" in daemon.speaker.said[0]


def test_an_ordinary_failure_keeps_the_conversation(daemon):
    daemon.session_id = "0b69de35"
    daemon.agent = Failing("API Error: Connection error.")
    daemon.answer("hello", {"transcript": "x"})
    assert daemon.session_id == "0b69de35"
