"""Approval cards answered by the person at the screen (phase M7).

A card's answer used to be a file any process running as the user could
write, so an agent at Trusted could answer its own card. These tests are
about every way an answer must *not* count: from the wrong process, from an
agent's child, for another card, after it expired, twice, for a changed card,
while locked -- and each of those must end the card as a no, never leave it
for somebody else to allow.

The caller checks run against real processes over the real socket: a fake
shell (tests/fixtures/cards/fake_shell.py, an interpreter started with
`-p DIR`, as quickshell is) runs `bin/agentvoice pending|permit` as its own
children with pipes it holds, the way the overlay's Process objects do.
"""
from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import cardhelp
import cards
import permission_hook as hook

ROOT = Path(__file__).resolve().parent.parent
FAKE_SHELL = ROOT / "tests" / "fixtures" / "cards" / "fake_shell.py"
#: What /proc/PID/exe says for this interpreter, so a fake shell started
#: with it passes the "is it quickshell" check the way the real one does.
EXE = os.path.basename(os.readlink("/proc/self/exe"))


def _desk(**kw):
    return cards.Desk(summon=lambda cid: None, **kw)


def _shown(desk, cid):
    return desk.show(cid, verified=True)


# --- the desk: one card, answered once -------------------------------------------------

class TestDesk:
    def test_a_checked_allow_is_a_yes(self):
        desk = _desk()
        t, card = cardhelp.post_async(desk, {"tool": "Bash", "summary": "ls"})
        s = _shown(desk, card["id"])
        assert desk.answer(card["id"], "allow", s["nonce"], s["digest"],
                           verified=True) == (True, "allowed")
        t.join(5)
        assert card["answer"] == {"allow": True}
        assert desk.pending() == []

    def test_a_deny_is_taken_from_anyone(self):
        desk = _desk()
        t, card = cardhelp.post_async(desk, {"tool": "Bash"})
        assert desk.answer(card["id"], "deny") == (True, "denied")
        t.join(5)
        assert card["answer"]["allow"] is False

    @pytest.mark.parametrize("change", ["unchecked", "nonce", "digest", "no-nonce",
                                        "verdict", "locked", "session"])
    def test_an_allow_that_fails_a_check_denies_the_card(self, change):
        """Not ignored -- denied, so trying to answer somebody else's card
        ends it rather than leaving it to be allowed later."""
        locked = {"now": False}
        desk = _desk(is_locked=lambda: locked["now"])
        t, card = cardhelp.post_async(desk, {"tool": "Bash", "sessionWide": False})
        s = _shown(desk, card["id"])
        nonce, digest, verified, verdict = s["nonce"], s["digest"], True, "allow"
        if change == "unchecked":
            verified = False
        elif change == "nonce":
            nonce = "0" * 32
        elif change == "digest":
            digest = cards.digest_of({**{k: v for k, v in s.items()
                                         if k not in ("digest", "verified", "nonce")},
                                      "summary": "rm -rf ~"})
        elif change == "no-nonce":
            nonce = ""
        elif change == "verdict":
            verdict = "yes"
        elif change == "locked":
            locked["now"] = True
        elif change == "session":
            verdict = "allow-session"
        ok, text = desk.answer(card["id"], verdict, nonce, digest, verified=verified)
        t.join(5)
        assert not ok and "denied" in text
        assert card["answer"]["allow"] is False
        assert "could not be checked" in card["answer"]["reason"] or change == "locked"
        assert desk.pending() == []

    def test_a_second_answer_changes_nothing(self):
        desk = _desk()
        t, card = cardhelp.post_async(desk, {"tool": "Bash"})
        s = _shown(desk, card["id"])
        assert desk.answer(card["id"], "allow", s["nonce"], s["digest"], verified=True)[0]
        again = desk.answer(card["id"], "deny")
        t.join(5)
        assert again == (False, f"no question {card['id']} is waiting")
        assert card["answer"] == {"allow": True}

    def test_a_deny_first_cannot_become_an_allow(self):
        desk = _desk()
        t, card = cardhelp.post_async(desk, {"tool": "Bash"})
        s = _shown(desk, card["id"])
        desk.answer(card["id"], "deny")
        assert desk.answer(card["id"], "allow", s["nonce"], s["digest"],
                           verified=True)[0] is False
        t.join(5)
        assert card["answer"]["allow"] is False

    def test_silence_is_none_and_an_answer_after_it_is_too_late(self):
        desk = _desk()
        t, card = cardhelp.post_async(desk, {"tool": "Bash"}, timeout=0.3)
        s = _shown(desk, card["id"])
        t.join(5)
        assert card["answer"] is None
        assert desk.answer(card["id"], "allow", s["nonce"], s["digest"],
                           verified=True) == (False, f"no question {card['id']} is waiting")

    def test_a_stop_takes_the_card_down(self):
        desk = _desk()
        t0 = time.monotonic()
        assert desk.post({"tool": "Bash"}, 10, stop=lambda: True) is None
        assert time.monotonic() - t0 < 1 and desk.pending() == []

    def test_a_stop_that_raises_is_a_stop(self):
        desk = _desk()
        assert desk.post({"tool": "Bash"}, 10, stop=lambda: 1 / 0) is None

    def test_locked_when_asked_is_a_no_at_once_and_nothing_is_shown(self):
        shown = []
        desk = cards.Desk(summon=shown.append, is_locked=lambda: True)
        t0 = time.monotonic()
        got = desk.post({"tool": "Bash", "summary": "ls"}, 10)
        assert got == {"allow": False, "reason": cards.LOCKED}
        assert shown == [] and time.monotonic() - t0 < 0.5

    def test_a_lock_while_it_waits_denies_it(self):
        locked = {"now": False}
        desk = _desk(is_locked=lambda: locked["now"])
        t, card = cardhelp.post_async(desk, {"tool": "Bash"})
        locked["now"] = True
        t.join(5)
        assert card["answer"] == {"allow": False, "reason": cards.LOCKED_SINCE}

    @pytest.mark.parametrize("answer", [None, "yes", 0, RuntimeError])
    def test_a_lock_that_cannot_be_told_is_locked(self, answer):
        def is_locked():
            if answer is RuntimeError:
                raise RuntimeError("no compositor")
            return answer
        desk = _desk(is_locked=is_locked)
        assert desk.post({"tool": "Bash"}, 5)["allow"] is False

    def test_no_socket_means_no_card(self):
        desk = _desk()
        desk.ready = False
        assert desk.post({"tool": "Bash"}, 5) == {"allow": False, "reason": cards.NO_SOCKET}

    def test_too_many_waiting_is_a_no(self, monkeypatch):
        monkeypatch.setattr(cards, "MAX_PENDING", 2)
        desk = _desk()
        held = [cardhelp.post_async(desk, {"tool": "Bash"}) for _ in range(2)]
        assert desk.post({"tool": "Bash"}, 5) == {"allow": False, "reason": cards.TOO_MANY}
        for _t, c in held:
            desk.answer(c["id"], "deny")

    def test_an_answer_and_the_timeout_settle_it_once(self):
        desk = _desk()
        card = cards._Card({**cards.clean_fields({}), "id": "a" * 12, "asked_at": 0,
                            "timeout": 1}, 0)
        desk._cards[card.id] = card
        assert desk._finish(card, {"allow": True}) is True
        assert desk._finish(card, None) is False
        assert card.answer == {"allow": True}

    def test_show_without_a_check_has_no_nonce(self):
        desk = _desk()
        t, card = cardhelp.post_async(desk, {"tool": "Bash", "summary": "ls"})
        shown = desk.show(card["id"], verified=False, why="not the panel")
        assert "nonce" not in shown and shown["verified"] is False
        assert shown["why"] == "not the panel" and shown["summary"] == "ls"
        assert desk.show("f" * 12, verified=True) == {}
        desk.answer(card["id"], "deny")
        t.join(5)


class TestTheCard:
    def test_only_known_fields_of_their_kind_get_through(self):
        got = cards.clean_fields({"tool": "Bash", "summary": "x" * 100000,
                                  "sessionWide": "true", "announce": 1,
                                  "truncated": -3, "length": True, "input": [1],
                                  "nonce": "f" * 32, "verified": True, "id": "x"})
        assert got["sessionWide"] is False and got["announce"] is False
        assert got["truncated"] == 0 and got["length"] == 0 and got["input"] == {}
        assert len(got["summary"]) == 64 * 1024
        assert not {"nonce", "verified", "id"} & set(got)

    def test_garbage_is_a_card_about_nothing(self):
        assert cards.clean_fields(None)["tool"] == "unknown"
        assert cards.clean_fields([1, 2])["sessionWide"] is False

    def test_the_digest_binds_every_shown_field(self):
        base = {**cards.clean_fields({"tool": "Bash", "summary": "ls"}),
                "id": "a" * 12, "asked_at": 1.0, "timeout": 45.0}
        d = cards.digest_of(base)
        for k, v in (("summary", "ls; rm -rf ~"), ("id", "b" * 12), ("tool", "Write"),
                     ("sessionWide", True), ("note", "x")):
            assert cards.digest_of({**base, k: v}) != d, k
        assert cards.digest_of(dict(reversed(list(base.items())))) == d


# --- who may answer: real processes over the real socket --------------------------------

@pytest.fixture
def decoy():
    """A process that is nobody's ancestor here, to stand as the daemon
    when the fake shell must not descend from it."""
    p = subprocess.Popen(["sleep", "60"])
    yield p.pid
    p.kill()
    p.wait()


def _verifier(tmp_path, daemon_pid):
    shell_dir = tmp_path / "omarchy-shell"
    shell_dir.mkdir(exist_ok=True)
    return cards.Verifier(daemon_pid=daemon_pid, shell_dir=shell_dir, shell_exes=(EXE,))


def _fake_shell(tmp_path, steps: dict, config: Path | None = None) -> dict:
    env = {**os.environ, "XDG_RUNTIME_DIR": str(tmp_path),
           "AGENTVOICE_PYTHON": sys.executable}
    steps = {"agentvoice": str(ROOT / "bin" / "agentvoice"), **steps}
    r = subprocess.run([sys.executable, str(FAKE_SHELL), "-p",
                        str(config or tmp_path / "omarchy-shell"), json.dumps(steps)],
                       env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


class TestWhoMayAnswer:
    def test_the_panel_is_given_the_nonce_and_its_allow_counts(self, tmp_path, decoy):
        with cardhelp.live_desk(tmp_path, _verifier(tmp_path, decoy)) as desk:
            t, card = cardhelp.post_async(desk, {"tool": "Bash", "summary": "ls"})
            got = _fake_shell(tmp_path, {"id": card["id"], "verdict": "allow"})
            t.join(5)
        assert got["shown"]["verified"] is True, got["shown"].get("why")
        assert cards.NONCE.fullmatch(got["shown"]["nonce"])
        assert json.loads(got["permit"]["out"]) == {"ok": True, "text": "allowed"}
        assert card["answer"] == {"allow": True}

    def test_allow_all_in_this_chat_from_the_panel(self, tmp_path, decoy):
        with cardhelp.live_desk(tmp_path, _verifier(tmp_path, decoy)) as desk:
            t, card = cardhelp.post_async(desk, {"tool": "Bash", "sessionWide": True})
            _fake_shell(tmp_path, {"id": card["id"], "verdict": "allow-session"})
            t.join(5)
        assert card["answer"] == {"allow": True, "session": True}

    def test_the_wrong_caller_is_refused_and_the_card_denied(self, tmp_path, decoy):
        """`agentvoice permit ID allow` from anywhere else -- here this test,
        a plain process -- even holding the right nonce."""
        with cardhelp.live_desk(tmp_path, _verifier(tmp_path, decoy)) as desk:
            t, card = cardhelp.post_async(desk, {"tool": "Bash"})
            s = _shown(desk, card["id"])
            r = cardhelp.cli(tmp_path, "permit", card["id"], "allow",
                             stdin=json.dumps({"nonce": s["nonce"], "digest": s["digest"]}) + "\n")
            t.join(5)
        # This interpreter passes as the shell's executable here, so it is
        # caught one check later: it was not started with the shell's folder.
        assert r.returncode == 1 and "not running" in r.stderr
        assert card["answer"]["allow"] is False

    def test_an_agents_child_is_refused_even_with_the_nonce(self, tmp_path):
        """The fake shell is this test's child, and this test stands as the
        daemon: a shell an agent started. It is handed the real nonce, so
        the only thing between it and a yes is the ancestry check."""
        with cardhelp.live_desk(tmp_path, _verifier(tmp_path, os.getpid())) as desk:
            t, card = cardhelp.post_async(desk, {"tool": "Bash"})
            s = _shown(desk, card["id"])
            got = _fake_shell(tmp_path, {"id": card["id"], "verdict": "allow",
                                         "nonce": s["nonce"], "digest": s["digest"]})
            t.join(5)
        assert got["shown"]["verified"] is False
        assert "inside an agent" in got["shown"]["why"]
        assert got["permit"]["rc"] == 1 and "inside an agent" in got["permit"]["err"]
        assert card["answer"]["allow"] is False

    def test_a_shell_running_another_config_is_refused(self, tmp_path, decoy):
        """`qs -p ~/evil` runs whatever QML it likes; only the Omarchy
        shell's own folder counts."""
        other = tmp_path / "evil-shell"
        other.mkdir()
        with cardhelp.live_desk(tmp_path, _verifier(tmp_path, decoy)) as desk:
            t, card = cardhelp.post_async(desk, {"tool": "Bash"})
            s = _shown(desk, card["id"])
            got = _fake_shell(tmp_path, {"id": card["id"], "verdict": "allow",
                                         "nonce": s["nonce"], "digest": s["digest"]},
                              config=other)
            t.join(5)
        assert got["shown"]["verified"] is False and "not running" in got["shown"]["why"]
        assert card["answer"]["allow"] is False

    def test_a_link_to_the_shell_folder_is_the_shell_folder(self, tmp_path, decoy):
        link = tmp_path / "link-to-shell"
        (tmp_path / "omarchy-shell").mkdir()
        link.symlink_to(tmp_path / "omarchy-shell")
        with cardhelp.live_desk(tmp_path, _verifier(tmp_path, decoy)) as desk:
            t, card = cardhelp.post_async(desk, {"tool": "Bash"})
            got = _fake_shell(tmp_path, {"id": card["id"], "verdict": "allow"}, config=link)
            t.join(5)
        assert card["answer"] == {"allow": True}, got

    def test_a_pending_whose_output_goes_to_a_file_gets_no_nonce(self, tmp_path, decoy):
        """`exec agentvoice pending ID > /tmp/x`, smuggled into a command the
        shell runs (a custom bar widget's exec), would hand the nonce to
        whoever reads the file."""
        with cardhelp.live_desk(tmp_path, _verifier(tmp_path, decoy)) as desk:
            t, card = cardhelp.post_async(desk, {"tool": "Bash"})
            got = _fake_shell(tmp_path, {"id": card["id"],
                                         "pending_to_file": str(tmp_path / "x.json")})
            desk.answer(card["id"], "deny")
            t.join(5)
        assert got["shown"]["verified"] is False and "nonce" not in got["shown"]
        assert "output is not the shell's own pipe" in got["shown"]["why"]

    def test_a_pending_writing_into_somebody_elses_pipe_gets_no_nonce(self, tmp_path, decoy):
        """A pipe, but not one the shell holds: what `exec agentvoice
        pending ID | tee /tmp/x` would give, if it could keep the shell as
        its parent."""
        with cardhelp.live_desk(tmp_path, _verifier(tmp_path, decoy)) as desk:
            t, card = cardhelp.post_async(desk, {"tool": "Bash"})
            got = _fake_shell(tmp_path, {"id": card["id"], "pending_to_other": True})
            desk.answer(card["id"], "deny")
            t.join(5)
        assert got["shown"]["verified"] is False and "nonce" not in got["shown"]
        assert "output is not the shell's own pipe" in got["shown"]["why"]

    def test_a_caller_that_changes_while_it_is_checked_is_refused(self, tmp_path, decoy,
                                                                   monkeypatch):
        """The caller's pid read twice, first and last: a process that died
        and whose pid went to another in between is not the one checked.
        Made to happen by reporting a later start time the second time."""
        real, asked = cards._stat, []

        def changing(pid):
            ppid, started = real(pid)
            asked.append(pid)
            return (ppid, started + 1) if asked.count(asked[0]) > 1 and pid == asked[0] \
                else (ppid, started)
        with cardhelp.live_desk(tmp_path, _verifier(tmp_path, decoy)) as desk:
            t, card = cardhelp.post_async(desk, {"tool": "Bash"})
            monkeypatch.setattr(cards, "_stat", changing)
            got = _fake_shell(tmp_path, {"id": card["id"]})
            monkeypatch.setattr(cards, "_stat", real)
            desk.answer(card["id"], "deny")
            t.join(5)
        assert got["shown"]["verified"] is False
        assert "changed while it was checked" in got["shown"]["why"]

    def test_a_permit_reading_a_file_is_refused(self, tmp_path, decoy):
        with cardhelp.live_desk(tmp_path, _verifier(tmp_path, decoy)) as desk:
            t, card = cardhelp.post_async(desk, {"tool": "Bash"})
            s = _shown(desk, card["id"])
            got = _fake_shell(tmp_path, {"id": card["id"], "verdict": "allow",
                                         "nonce": s["nonce"], "digest": s["digest"],
                                         "permit_from_file": str(tmp_path / "in.json")})
            t.join(5)
        assert got["permit"]["rc"] == 1 and "input is not the shell's own pipe" in got["permit"]["err"]
        assert card["answer"]["allow"] is False

    def test_an_expired_card_cannot_be_answered(self, tmp_path, decoy):
        with cardhelp.live_desk(tmp_path, _verifier(tmp_path, decoy)) as desk:
            t, card = cardhelp.post_async(desk, {"tool": "Bash"}, timeout=0.5)
            s = _shown(desk, card["id"])
            t.join(5)
            got = _fake_shell(tmp_path, {"id": card["id"], "verdict": "allow",
                                         "nonce": s["nonce"], "digest": s["digest"]})
        assert card["answer"] is None
        assert got["permit"]["rc"] == 1 and "no question" in got["permit"]["err"]

    def test_a_changed_card_is_denied(self, tmp_path, decoy):
        with cardhelp.live_desk(tmp_path, _verifier(tmp_path, decoy)) as desk:
            t, card = cardhelp.post_async(desk, {"tool": "Bash", "summary": "ls"})
            got = _fake_shell(tmp_path, {"id": card["id"], "verdict": "allow",
                                         "digest": "ab" * 32})
            t.join(5)
        assert got["shown"]["verified"] is True
        assert got["permit"]["rc"] == 1 and "not the question asked" in got["permit"]["err"]
        assert card["answer"]["allow"] is False

    def test_a_double_submit_changes_nothing(self, tmp_path, decoy):
        with cardhelp.live_desk(tmp_path, _verifier(tmp_path, decoy)) as desk:
            t, card = cardhelp.post_async(desk, {"tool": "Bash"})
            s = _shown(desk, card["id"])
            first = _fake_shell(tmp_path, {"id": card["id"], "verdict": "allow"})
            again = _fake_shell(tmp_path, {"id": card["id"], "verdict": "deny",
                                           "nonce": s["nonce"], "digest": s["digest"]})
            t.join(5)
        assert first["permit"]["rc"] == 0
        assert again["permit"]["rc"] == 1 and "no question" in again["permit"]["err"]
        assert card["answer"] == {"allow": True}

    def test_an_allow_while_locked_is_refused(self, tmp_path, decoy):
        locked = {"now": False}
        with cardhelp.live_desk(tmp_path, _verifier(tmp_path, decoy),
                                is_locked=lambda: locked["now"]) as desk:
            t, card = cardhelp.post_async(desk, {"tool": "Bash"})
            s = _shown(desk, card["id"])
            locked["now"] = True
            ok, text = desk.answer(card["id"], "allow", s["nonce"], s["digest"], verified=True)
            t.join(5)
        assert not ok and card["answer"]["allow"] is False


class TestWhoMayAsk:
    def test_only_a_process_the_daemon_started_can_post(self, tmp_path, decoy):
        code = ("import sys, json; sys.path.insert(0, sys.argv[1]); import cards; "
                "print(json.dumps(cards.ask({'tool': 'Bash'}, 0.5)))")
        env = {**os.environ, "XDG_RUNTIME_DIR": str(tmp_path)}
        with cardhelp.live_desk(tmp_path, _verifier(tmp_path, decoy)):
            r = subprocess.run([sys.executable, "-c", code, str(ROOT / "daemon")],
                               env=env, capture_output=True, text=True, timeout=20)
        got = json.loads(r.stdout)
        assert got["allow"] is False and "only an agent" in got["reason"]

    def test_a_child_of_the_daemon_can_post_and_hears_the_answer(self, tmp_path):
        code = ("import sys, json; sys.path.insert(0, sys.argv[1]); import cards; "
                "print(json.dumps(cards.ask({'tool': 'Bash', 'summary': 'ls'}, 10)))")
        env = {**os.environ, "XDG_RUNTIME_DIR": str(tmp_path)}
        with cardhelp.live_desk(tmp_path, _verifier(tmp_path, os.getpid())) as desk:
            cardhelp.answer_after(desk, 0.0, "allow")
            r = subprocess.run([sys.executable, "-c", code, str(ROOT / "daemon")],
                               env=env, capture_output=True, text=True, timeout=20)
        assert json.loads(r.stdout) == {"allow": True}, r.stderr

    def test_the_real_hook_end_to_end(self, tmp_path, monkeypatch):
        """permission_hook.py as Claude Code runs it, over the socket: a yes
        from the panel is an allow, silence a deny."""
        env = {**os.environ, "XDG_RUNTIME_DIR": str(tmp_path),
               "AGENTVOICE_PERMISSION_TIMEOUT": "1.5", "XDG_CONFIG_HOME": str(tmp_path / "cfg")}

        def run_hook():
            r = subprocess.run([sys.executable, str(ROOT / "daemon" / "permission_hook.py"),
                                "claude"],
                               input=json.dumps({"tool_name": "Bash",
                                                 "tool_input": {"command": "make"}}),
                               env=env, capture_output=True, text=True, timeout=30)
            return json.loads(r.stdout)["hookSpecificOutput"]

        with cardhelp.live_desk(tmp_path, _verifier(tmp_path, os.getpid())) as desk:
            seen = {}
            cardhelp.answer_after(desk, 0.0, "allow", seen=seen)
            assert run_hook()["permissionDecision"] == "allow"
            assert seen["summary"] == "make" and seen["tool"] == "Bash"
            out = run_hook()
            assert out["permissionDecision"] == "deny"
            assert "Nobody answered" in out["permissionDecisionReason"]
            assert desk.pending() == []

    def test_a_hook_that_is_killed_takes_its_card_down(self, tmp_path):
        env = {**os.environ, "XDG_RUNTIME_DIR": str(tmp_path),
               "AGENTVOICE_PERMISSION_TIMEOUT": "30", "XDG_CONFIG_HOME": str(tmp_path / "cfg")}
        with cardhelp.live_desk(tmp_path, _verifier(tmp_path, os.getpid())) as desk:
            p = subprocess.Popen([sys.executable, str(ROOT / "daemon" / "permission_hook.py"),
                                  "claude"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 env=env, text=True)
            p.stdin.write(json.dumps({"tool_name": "Bash", "tool_input": {"command": "x"}}))
            p.stdin.close()
            assert cardhelp.wait_card(desk) is not None
            p.kill()
            p.wait()
            end = time.time() + 3
            while desk.pending() and time.time() < end:
                time.sleep(0.05)
            assert desk.pending() == []

    def test_the_hook_checks_the_listener_is_its_ancestor(self, tmp_path, monkeypatch):
        """Anything running as the user can bind a socket at that path; only
        the daemon is the hook's ancestor. Here the listener is a child."""
        monkeypatch.setattr(cards, "LOCAL_DESK", None)
        root = tmp_path / "agentvoice" / "cards"
        root.mkdir(parents=True)
        monkeypatch.setattr(cards, "SOCKET_DIR", root)
        code = ("import socket, sys; s = socket.socket(socket.AF_UNIX); s.bind(sys.argv[1]); "
                "s.listen(1); print('up', flush=True); c, _ = s.accept(); c.recv(65536); "
                "c.sendall(b'{\"answer\": {\"allow\": true}}\\n')")
        p = subprocess.Popen([sys.executable, "-c", code, str(root / cards.SOCKET_NAME)],
                             stdout=subprocess.PIPE, text=True)
        try:
            assert p.stdout.readline().strip() == "up"
            got = cards.ask({"tool": "Bash"}, 2)
        finally:
            p.kill()
            p.wait()
        assert got == {"allow": False, "reason": cards.NOT_OURS}

    def test_no_daemon_is_a_denial_that_says_so(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cards, "LOCAL_DESK", None)
        monkeypatch.setattr(cards, "SOCKET_DIR", tmp_path / "none")
        decision, reason = hook._ask("Bash", {"command": "ls"})
        assert decision == "deny" and "not running" in reason

    def test_an_exception_on_the_way_is_a_denial(self, monkeypatch, capsys):
        """Every path out of the hook is a decision (CLAUDE.md)."""
        import io
        monkeypatch.setattr(cards, "LOCAL_DESK", None)

        def boom(*a, **k):
            raise RuntimeError("socket on fire")
        monkeypatch.setattr(cards, "ask", boom)
        monkeypatch.setattr(hook, "_settings", lambda: ("ask", None))
        monkeypatch.setattr("sys.stdin", io.StringIO(
            '{"tool_name": "Bash", "tool_input": {"command": "ls"}}'))
        assert hook.main() == 0
        out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
        assert out["permissionDecision"] == "deny" and "failed" in out["permissionDecisionReason"]


class TestTheSocket:
    def test_it_is_private(self, tmp_path):
        with cardhelp.live_desk(tmp_path):
            sock = tmp_path / "agentvoice" / "cards" / cards.SOCKET_NAME
            assert stat.S_IMODE(sock.stat().st_mode) == 0o600
            assert stat.S_IMODE(sock.parent.stat().st_mode) == 0o700

    @pytest.mark.parametrize("raw", [b"not json\n", b"[1]\n", b'{"op": "bogus"}\n',
                                     b'{"op": "show", "id": "../x"}\n',
                                     b'{"op": "answer", "id": 5, "verdict": "allow"}\n',
                                     b'{"op": "show", "op": "answer"}\n'])
    def test_garbage_gets_no_card_and_changes_nothing(self, tmp_path, raw):
        with cardhelp.live_desk(tmp_path) as desk:
            t, card = cardhelp.post_async(desk, {"tool": "Bash"})
            with socket.socket(socket.AF_UNIX) as c:
                c.connect(str(tmp_path / "agentvoice" / "cards" / cards.SOCKET_NAME))
                c.sendall(raw)
                reply = c.recv(65536)
            assert b"nonce" not in reply
            assert [x["id"] for x in desk.pending()] == [card["id"]]
            desk.answer(card["id"], "deny")
            t.join(5)

    def test_the_listener_without_a_socket_refuses_every_card(self, tmp_path):
        desk = _desk()
        blocker = tmp_path / "file"
        blocker.write_text("")
        assert cards.Listener(desk, cards.Verifier(), blocker / "cards").start() is False
        assert desk.ready is False
        assert desk.post({"tool": "Bash"}, 5)["reason"] == cards.NO_SOCKET


class TestProc:
    def test_config_path_reads_every_spelling(self):
        for argv in (["qs", "-n", "-p", "/x"], ["qs", "--path", "/x"],
                     ["qs", "--path=/x"], ["qs", "-p/x"]):
            assert cards.config_path(argv) == "/x", argv
        assert cards.config_path(["qs", "-n"]) is None
        assert cards.config_path(["qs", "-p"]) is None

    def test_descends_and_clear_of(self):
        me, parent = os.getpid(), os.getppid()
        assert cards.descends(me, parent) and not cards.descends(parent, me)
        assert not cards.descends(me, me)
        assert cards._clear_of(parent, me) and not cards._clear_of(me, parent)
        assert not cards._clear_of(10 ** 7, 1234)    # unreadable is not clear

    def test_a_peer_pidfd_names_its_process(self):
        a, b = socket.socketpair()
        with a, b:
            fd = cards.peer_pidfd(a)
            if fd is None:
                # Not a skip: the caller check stands without a pidfd (the
                # start-time comparison), so this only has to be honest
                # about why there is none -- an architecture whose number
                # is not known, or a kernel older than 6.5.
                release = tuple(int(x) for x in os.uname().release.split(".")[:2]
                                if x.isdigit())
                assert cards.SO_PEERPIDFD is None or release < (6, 5), \
                    "SO_PEERPIDFD should exist here and returned nothing"
                return
            try:
                assert cards.pidfd_pid(fd) == os.getpid()
            finally:
                os.close(fd)

    def test_the_default_shell_folder_follows_omarchy_path(self, monkeypatch):
        monkeypatch.setenv("OMARCHY_PATH", "/opt/om")
        assert cards.omarchy_shell_dir() == Path("/opt/om/shell")
        monkeypatch.delenv("OMARCHY_PATH")
        assert cards.omarchy_shell_dir() == Path("/usr/share/omarchy/shell")


# --- the second layer: the orders guard ---------------------------------------------------

class TestOrdersGuard:
    @pytest.mark.parametrize("cmd", [
        "agentvoice permit abcdef012345 allow",
        "echo '{}' > $XDG_RUNTIME_DIR/agentvoice/permissions/abcdef012345.response",
        "socat - UNIX-CONNECT:$XDG_RUNTIME_DIR/agentvoice/cards/cards.sock",
        "cp evil.qml ~/.config/omarchy/plugins/x/Main.qml",
        "sed -i s/a/b/ {data}/app/daemon/cards.py",
        "{data}/venv/bin/pip install evil",
    ])
    def test_a_command_that_could_answer_a_card_is_asked_at_trusted(self, cmd, monkeypatch):
        cmd = cmd.replace("{data}", str(hook.DATA_DIR))
        monkeypatch.setattr(hook, "_settings", lambda: ("trusted", None))
        monkeypatch.setattr(hook, "granted", lambda s: True)
        asked = []
        monkeypatch.setattr(hook, "_ask", lambda *a, **k: asked.append((a, k)) or ("deny", "asked"))
        assert hook.decide("Bash", {"command": cmd}, "x")[0] == "deny"
        assert asked and asked[0][1].get("session") == ""      # no chat grant

    @pytest.mark.parametrize("where", [
        lambda: hook.PENDING / "abcdef012345.response",
        lambda: hook.RUNTIME_DIR / "cards" / "cards.sock",
        lambda: Path.home() / ".config" / "omarchy" / "plugins" / "evil" / "Main.qml",
        lambda: hook.DATA_DIR / "app" / "daemon" / "cards.py",
        lambda: hook.DATA_DIR / "venv" / "lib" / "site.py",
    ])
    def test_a_write_to_what_answers_cards_is_asked_at_trusted(self, where, monkeypatch):
        monkeypatch.setattr(hook, "_settings", lambda: ("trusted", None))
        asked = []
        monkeypatch.setattr(hook, "_ask", lambda *a, **k: asked.append(k) or ("deny", "asked"))
        assert hook.decide("Write", {"file_path": str(where()), "content": "x"})[0] == "deny"
        assert asked and "approval cards" in asked[0]["note"]

    def test_an_ordinary_command_is_not(self, monkeypatch):
        monkeypatch.setattr(hook, "_settings", lambda: ("trusted", None))
        monkeypatch.setattr(hook, "_ask", lambda *a, **k: pytest.fail("asked"))
        assert hook.decide("Bash", {"command": "agentvoice status"})[0] == "allow"
        assert hook.decide("Bash", {"command": "ls ~/Projects/agent-voice/daemon"})[0] == "allow"


# --- Codex review of M7, pass 1 -----------------------------------------------------------

class TestReviewPass1:
    @staticmethod
    def _held(desk_kw=None):
        """A desk whose summon blocks until released, so post() is not yet
        looking at its deadline or its stop: the window the review found."""
        gate = threading.Event()
        desk = cards.Desk(summon=lambda cid: gate.wait(10), **(desk_kw or {}))
        return desk, gate

    def test_an_allow_after_the_deadline_is_refused_while_post_is_busy(self):
        now = {"t": 1000.0}
        desk, gate = self._held({"clock": lambda: now["t"]})
        t, card = cardhelp.post_async(desk, {"tool": "Bash"}, timeout=1)
        s = _shown(desk, card["id"])
        now["t"] += 5                      # past the deadline; post() is in summon
        ok, text = desk.answer(card["id"], "allow", s["nonce"], s["digest"], verified=True)
        gate.set()
        t.join(5)
        assert not ok and "expired" in text
        assert card["answer"]["allow"] is False

    def test_an_allow_for_a_stopped_turn_is_withdrawn_not_acknowledged(self):
        stopped = {"now": False}
        desk, gate = self._held()
        out = {}
        th = threading.Thread(target=lambda: out.update(
            a=desk.post({"tool": "Bash"}, 10, stop=lambda: stopped["now"])))
        th.start()
        card = cardhelp.wait_card(desk)
        s = _shown(desk, card["id"])
        stopped["now"] = True
        ok, text = desk.answer(card["id"], "allow", s["nonce"], s["digest"], verified=True)
        gate.set()
        th.join(5)
        assert not ok and "withdrawn" in text
        assert out["a"] is None

    @pytest.mark.parametrize("fresh, allowed", [(True, False), (None, True), (False, True),
                                                (RuntimeError, False)])
    def test_an_allow_asks_the_lock_afresh(self, fresh, allowed):
        """The daemon's flag can be two seconds behind a lock."""
        def locked_now():
            if fresh is RuntimeError:
                raise RuntimeError("no compositor")
            return fresh
        desk = _desk(locked_now=locked_now)
        t, card = cardhelp.post_async(desk, {"tool": "Bash"})
        s = _shown(desk, card["id"])
        ok, _text = desk.answer(card["id"], "allow", s["nonce"], s["digest"], verified=True)
        t.join(5)
        assert ok is allowed
        assert card["answer"]["allow"] is allowed

    def test_the_asker_never_waits_past_its_budget(self, tmp_path, monkeypatch):
        """A timeout of 90 s handed to the asker must not outlive Claude's
        60: the whole wait is capped."""
        monkeypatch.setattr(cards, "LOCAL_DESK", None)
        monkeypatch.setattr(cards, "ASK_BUDGET_S", 0.6)
        root = tmp_path / "cards"
        root.mkdir()
        monkeypatch.setattr(cards, "SOCKET_DIR", root)
        srv = socket.socket(socket.AF_UNIX)
        srv.bind(str(root / cards.SOCKET_NAME))
        srv.listen(1)
        held = []
        threading.Thread(target=lambda: held.append(srv.accept()), daemon=True).start()
        t0 = time.monotonic()
        try:
            got = cards.ask({"tool": "Bash"}, 90)
        finally:
            srv.close()
        assert got is None and time.monotonic() - t0 < 3

    @pytest.mark.parametrize("raw, want", [("90", 50.0), ("50", 50.0), ("12", 12.0),
                                           ("nan", 45.0), ("-1", 45.0), ("x", 45.0)])
    def test_the_hook_timeout_is_held_under_claudes_limit(self, raw, want, monkeypatch):
        monkeypatch.setenv("AGENTVOICE_PERMISSION_TIMEOUT", raw)
        assert hook._timeout() == want

    def test_the_overlay_is_handed_the_card_without_the_tool_call(self):
        desk = _desk()
        t, card = cardhelp.post_async(desk, {"tool": "Write", "summary": "/tmp/x",
                                             "input": {"content": "x" * 100000}})
        s = desk.show(card["id"], verified=True)
        assert "input" not in s and s["summary"] == "/tmp/x"
        assert s["digest"] == cards.digest_of({k: v for k, v in s.items()
                                               if k not in ("digest", "verified", "nonce")})
        # The daemon keeps it, for the browser question said out loud.
        assert desk.pending()[0]["input"]["content"] == "x" * 100000
        desk.answer(card["id"], "deny")
        t.join(5)
