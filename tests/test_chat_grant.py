""""Allow all in this chat": one answer that covers the rest of a conversation.

This lives in the permission hook, where a bug fails open, so most of these
are about the grant *not* applying: another conversation, another agent, a
file someone else could have written, a missing or malformed session id.
Each of those must fall back to asking, never to allowing.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import cardhelp
import permission_hook as hook

ROOT = Path(__file__).resolve().parent.parent
SID = "97c52faa-f737-43a3-83db-1ef0a1d86245"
OTHER = "11111111-2222-3333-4444-555555555555"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(hook, "PENDING", tmp_path / "permissions")
    monkeypatch.setattr(hook, "GRANTS", tmp_path / "grants")
    monkeypatch.setattr(hook, "_settings", lambda: ("ask", None))
    monkeypatch.setattr(sys, "argv", ["permission_hook.py", "claude"])
    monkeypatch.setattr(hook, "TIMEOUT", 0.4)
    return tmp_path


def answer(body: dict):
    """Answer the next card the way the overlay would (phase M7: through the
    desk, with the card's nonce)."""
    import cards
    verdict = ("allow-session" if body.get("session") is True else "allow") \
        if body.get("allow") is True else "deny"
    cardhelp.answer_after(cards.LOCAL_DESK, 0.0, verdict)


def asks(tool="Bash", cmd="rm -rf build", session=SID) -> bool:
    """True when this call was put to the user (and, unanswered, denied)."""
    decision, reason = hook.decide(tool, {"command": cmd}, session)
    return decision == "deny" and "answered" in reason


# --- the grant does its job ------------------------------------------------------

def test_allow_all_covers_the_rest_of_the_conversation():
    answer({"allow": True, "session": True})
    assert hook.decide("Bash", {"command": "make"}, SID)[0] == "allow"
    # Nobody answers these: they are allowed without a question.
    assert hook.decide("Bash", {"command": "rm -rf build"}, SID) == ("allow", "")
    assert hook.decide("Write", {"file_path": "/tmp/x"}, SID) == ("allow", "")
    assert hook.decide("Read", {"file_path": str(Path.home() / ".ssh/id_rsa")}, SID) == ("allow", "")
    import cards
    assert len(cards.LOCAL_DESK.summoned) == 1      # only the first was asked


def test_allow_once_grants_nothing_more():
    answer({"allow": True})
    assert hook.decide("Bash", {"command": "make"}, SID)[0] == "allow"
    assert asks()


def test_the_prompt_offers_it_only_with_a_conversation_to_scope_it_to(card_desk):
    seen = {}
    for session, want in ((SID, True), ("", False), ("not-a-uuid", False)):
        seen.clear()
        t = cardhelp.peek(card_desk, seen)
        hook.decide("Bash", {"command": "ls"}, session)
        t.join()
        assert seen.get("sessionWide") is want, session


def test_allow_all_is_refused_for_a_card_that_did_not_offer_it(card_desk):
    """Phase M7: the daemon refuses "allow all in this chat" for a card that
    had no conversation to scope it to -- the answer does not match the
    question -- and the question is denied, not allowed once."""
    seen = {}
    t = cardhelp.answer_after(card_desk, 0.0, "allow-session", seen=seen)
    decision, reason = hook.decide("Bash", {"command": "ls"}, "")
    t.join()
    assert seen.get("sessionWide") is False
    assert decision == "deny" and "whole chat" in reason
    assert not hook.granted("")


# --- and applies nowhere else ------------------------------------------------------

def test_another_conversation_is_asked_as_usual():
    assert hook.grant(SID)
    assert asks(session=OTHER)


def test_another_agent_in_the_same_conversation_is_asked(monkeypatch):
    assert hook.grant(SID)
    monkeypatch.setattr(sys, "argv", ["permission_hook.py", "claude", "sarah"])
    assert asks()
    monkeypatch.setattr(sys, "argv", ["permission_hook.py", "codex"])
    assert asks()


@pytest.mark.parametrize("session", ["", "../../etc/passwd", SID.upper(), SID + "x", None, 42])
def test_no_valid_session_no_grant(session):
    assert hook.grant(session) is False if isinstance(session, str) else True
    assert hook.granted(session) is False


def test_a_grant_anyone_else_could_write_is_ignored():
    assert hook.grant(SID)
    f = hook._grant_file(SID)
    f.chmod(0o666)
    assert asks()


def test_a_symlinked_grant_is_ignored(tmp_path):
    real = tmp_path / "elsewhere.json"
    real.write_text(json.dumps({"session": SID, "who": "", "agent": "claude"}))
    real.chmod(0o600)
    hook.GRANTS.mkdir(mode=0o700)
    hook._grant_file(SID).symlink_to(real)
    assert asks()


@pytest.mark.parametrize("body", [
    "{ not json", "[]", '"yes"', "{}",
    json.dumps({"session": OTHER, "who": "", "agent": "claude"}),
    json.dumps({"session": SID, "who": "sarah", "agent": "claude"}),
    json.dumps({"session": SID, "who": "", "agent": "codex"}),
])
def test_a_grant_that_is_not_exactly_the_record_is_ignored(body):
    hook.GRANTS.mkdir(mode=0o700)
    f = hook._grant_file(SID)
    f.write_text(body)
    f.chmod(0o600)
    assert asks()


@pytest.mark.parametrize("body", [
    {"allow": "true", "session": True}, {"allow": True, "session": "yes"},
    {"allow": False, "session": True}, {"session": True},
])
def test_only_the_literal_answer_grants(body):
    answer(body)
    hook.decide("Bash", {"command": "make"}, SID)
    assert not hook.granted(SID)


def test_a_grant_that_cannot_be_written_still_allows_the_one_asked_about(monkeypatch):
    monkeypatch.setattr(hook, "grant", lambda s: False)
    answer({"allow": True, "session": True})
    assert hook.decide("Bash", {"command": "make"}, SID)[0] == "allow"
    assert asks()


def test_the_grant_file_is_private():
    assert hook.grant(SID)
    import stat
    assert stat.S_IMODE(hook.GRANTS.stat().st_mode) == 0o700
    assert stat.S_IMODE(hook._grant_file(SID).stat().st_mode) == 0o600


# --- end to end: the real hook process, reading Claude Code's payload ---------------

def test_the_hook_reads_the_session_from_claudes_payload(isolated, monkeypatch):
    """Run as Claude Code runs it: a separate process, JSON on stdin."""
    env = dict(os.environ, XDG_RUNTIME_DIR=str(isolated), AGENTVOICE_PERMISSION_TIMEOUT="0.5")
    run_dir = isolated / "agentvoice"
    # Grant it in the place the real process will look, as the real process would.
    script = ("import sys; sys.argv=['h','claude']; import permission_hook as h; "
              f"print(h.grant({SID!r}))")
    out = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True,
                         text=True, cwd=ROOT / "daemon")
    assert out.stdout.strip() == "True", out.stderr
    assert (run_dir / "grants").is_dir()

    def call(session):
        payload = {"tool_name": "Bash", "tool_input": {"command": "touch x"},
                   "session_id": session}
        r = subprocess.run([sys.executable, str(ROOT / "daemon" / "permission_hook.py"), "claude"],
                           input=json.dumps(payload), env=env, capture_output=True, text=True,
                           timeout=30)
        return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"]

    assert call(SID) == "allow"
    assert call(OTHER) == "deny"            # asked, nobody answered


def test_the_daemon_forgets_every_grant_when_it_starts(tmp_path, monkeypatch):
    import wake_listen
    monkeypatch.setattr(wake_listen, "RUNTIME_DIR", tmp_path)
    (tmp_path / "grants").mkdir()
    (tmp_path / "grants" / "a.grant").write_text("{}")
    assert wake_listen.forget_chat_grants() == 1
    assert list((tmp_path / "grants").iterdir()) == []
    assert wake_listen.forget_chat_grants() == 0


def test_the_cli_sends_the_session_answer():
    """The verdict the overlay passes is handed to the daemon as it is, and
    the daemon turns a checked one into the grant (cards.py, phase M7)."""
    body = (ROOT / "bin" / "agentvoice").read_text()
    assert "allow|allow-session|deny" in body
    import cards
    desk = cards.Desk(summon=lambda cid: None)
    out = {}
    t = __import__("threading").Thread(
        target=lambda: out.update(a=desk.post({"tool": "Bash", "sessionWide": True}, 5)))
    t.start()
    import cardhelp
    card = cardhelp.wait_card(desk)
    shown = desk.show(card["id"], verified=True)
    assert desk.answer(card["id"], "allow-session", shown["nonce"], shown["digest"],
                       verified=True) == (True, "allowed")
    t.join(5)
    assert out["a"] == {"allow": True, "session": True}


def test_the_prompt_button_sends_it():
    qml = (ROOT / "Settings.qml").read_text()
    i = qml.index('text: "Allow all in this chat"')
    block = qml[i - 400:i + 600]
    assert 'root.answer("allow-session")' in block
    assert "root.request.sessionWide === true" in block
