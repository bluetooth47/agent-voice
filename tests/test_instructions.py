"""Custom instructions: one set for the main agent, one per extra agent.

They are the user's own words added to the system prompt, so three things
matter: they reach every backend, they never travel in argv (readable by any
local account through /proc), and changing them is a plain attribute -- the
conversation carries on, the way it does for an effort.
"""
from __future__ import annotations

import os
import stat

import pytest

import adapters
from adapters.base import INSTRUCTIONS_HEAD, SPOKEN_STYLE
from adapters.claude_code import ClaudeCode
from adapters.openai_compat import OpenAICompatible

SECRET = "Call me Sam. My server is called hal-9000."


# --- the value ---------------------------------------------------------------

@pytest.mark.parametrize("raw, want", [
    ("  be brief  ", "be brief"),
    ("line one\r\nline two", "line one\nline two"),
    ("bell\x07 and esc\x1b[31m", "bell and esc[31m"),
    (None, ""), (42, ""), (["x"], ""), ({}, ""),
])
def test_instructions_are_plain_bounded_text(raw, want):
    from runtime import instructions_text
    assert instructions_text(raw) == want


def test_a_pasted_essay_is_cut_to_the_limit():
    from runtime import INSTRUCTIONS_MAX, instructions_text
    assert len(instructions_text("a" * 10_000)) == INSTRUCTIONS_MAX


def test_the_main_agent_ships_with_none(cfg_factory):
    assert cfg_factory()["agentInstructions"] == ""


def test_an_extra_agent_keeps_its_own(cfg_factory):
    cfg = cfg_factory(voiceAgents=[{"name": "friday", "instructions": " be terse "},
                                   {"name": "jarvis"}])
    got = {a["name"]: a["instructions"] for a in cfg.agents()}
    assert got == {"friday": "be terse", "jarvis": ""}


# --- the preamble ------------------------------------------------------------

def test_no_instructions_is_the_spoken_style_alone():
    a = ClaudeCode()
    assert a.preamble() == SPOKEN_STYLE


def test_instructions_follow_the_spoken_style():
    a = ClaudeCode()
    a.instructions = SECRET
    head = a.preamble()
    assert head.startswith(SPOKEN_STYLE)
    assert head.endswith(INSTRUCTIONS_HEAD + SECRET)


def test_a_typed_turn_still_gets_the_instructions():
    a = ClaudeCode(spoken=False)
    a.instructions = SECRET
    assert a.preamble() == INSTRUCTIONS_HEAD + SECRET
    a.instructions = ""
    assert a.preamble() == "" and a.with_preamble("hi") == "hi"


# --- they reach the backend, and never argv ----------------------------------

@pytest.fixture
def rundir(tmp_path, monkeypatch):
    import paths
    monkeypatch.setattr(paths, "RUNTIME_DIR", tmp_path)
    return tmp_path


def test_claude_reads_them_from_a_private_file(rundir):
    a = ClaudeCode()
    a.instructions = SECRET
    argv = a._argv("", None)
    assert not any(SECRET in part for part in argv)
    path = argv[argv.index("--append-system-prompt-file") + 1]
    assert "--append-system-prompt" not in argv
    assert open(path).read() == a.preamble()
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_claude_without_instructions_is_unchanged(rundir):
    argv = ClaudeCode()._argv("", None)
    assert argv[argv.index("--append-system-prompt") + 1] == SPOKEN_STYLE
    assert "--append-system-prompt-file" not in argv
    assert not (rundir / "prompts").exists()


def test_two_agents_with_different_instructions_get_different_files(rundir):
    a, b = ClaudeCode(), ClaudeCode()
    a.instructions, b.instructions = "be terse", "be chatty"
    fa = a._argv("", None)
    fb = b._argv("", None)
    pa = fa[fa.index("--append-system-prompt-file") + 1]
    pb = fb[fb.index("--append-system-prompt-file") + 1]
    assert pa != pb and "terse" in open(pa).read() and "chatty" in open(pb).read()


@pytest.mark.parametrize("module, cls", [
    ("codex", "Codex"), ("gemini", "Gemini"), ("cli_agent", None),
])
def test_stdin_backends_put_them_in_the_prompt(module, cls):
    import importlib
    mod = importlib.import_module(f"adapters.{module}")
    a = getattr(mod, cls)() if cls else mod.CliAgent("copilot")
    a.instructions = SECRET
    assert a.with_preamble("what time is it").endswith("\n\nwhat time is it")
    assert SECRET in a.with_preamble("what time is it")


def test_antigravity_carries_them_on_stdin():
    from adapters.antigravity import Antigravity
    a = Antigravity()
    a.instructions = SECRET
    assert SECRET in a.prompt_line("hello")
    assert not any(SECRET in part for part in a._argv("hello", None))


def test_an_endpoint_takes_them_as_its_system_message_and_follows_a_change():
    e = OpenAICompatible(base_url="http://localhost:1", model="m")
    e.instructions = "be terse"
    sid, msgs = e._messages("hi", None)
    assert msgs[0]["role"] == "system" and msgs[0]["content"].endswith("be terse")
    e._sessions[sid] = msgs + [{"role": "assistant", "content": "hello"}]
    e.instructions = "be chatty"
    _, again = e._messages("and now?", sid)
    systems = [m for m in again if m["role"] == "system"]
    assert len(systems) == 1 and systems[0]["content"].endswith("be chatty")
    assert [m["content"] for m in again[1:]] == ["hi", "hello", "and now?"]


def test_load_hands_them_over(monkeypatch):
    monkeypatch.setattr(ClaudeCode, "available", lambda self: True)
    assert adapters.load("claude", instructions="be terse").instructions == "be terse"
    assert adapters.load("claude").instructions == ""


# --- the daemon: a change keeps the conversation -----------------------------

class Agent:
    name = "claude"
    effort = None
    remembers = True
    levels = ("ask", "edits", "trusted")
    instructions = ""

    def __init__(self):
        self.cancelled = 0

    def posture(self, level): return level
    def cancel(self): self.cancelled += 1
    def prepare(self, *a, **k): pass


def test_changing_the_main_instructions_keeps_the_session(daemon):
    daemon.agent = Agent()
    daemon.session_id = "keep"
    daemon.apply_instructions("be terse")
    assert daemon.agent.instructions == "be terse"
    assert daemon.agent.cancelled == 1          # the idle process had the old ones
    assert daemon.session_id == "keep"
    daemon.apply_instructions("be terse")
    assert daemon.agent.cancelled == 1          # no change, no restart


def test_changing_an_extra_agents_instructions_keeps_its_conversation(daemon, monkeypatch):
    import wake_listen
    built = []

    def load(program, **kw):
        a = Agent()
        a.instructions = kw.get("instructions", "")
        built.append(a)
        return a

    monkeypatch.setattr(wake_listen, "load_adapter", load)
    monkeypatch.setattr(wake_listen, "takes_effort", lambda a: False)
    daemon.pipe = type("P", (), {"phrase": "computer", "names": ["friday"], "unheard": {}})()
    daemon.agent = Agent()
    daemon.cfg._values["speakReplies"] = False
    daemon.cfg._values["voiceAgents"] = [{"name": "friday", "instructions": "be terse"}]
    daemon.reconcile_crew()
    p = daemon.crew["friday"]
    assert p.agent.instructions == "be terse"
    p.session_id = "keep"
    daemon.cfg._values["voiceAgents"] = [{"name": "friday", "instructions": "be chatty"}]
    daemon.reconcile_crew()
    assert len(built) == 1 and p.agent.instructions == "be chatty"
    assert p.session_id == "keep" and p.agent.cancelled == 1
