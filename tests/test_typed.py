"""Typing to an agent: for no microphone, a wake word that will not fire, or a
room where talking is not an option.

`agentvoice type` takes the text on stdin -- argv is readable by every
account through /proc -- and leaves it in a private folder the run loop
reads between captures. A typed turn is answered with the microphone
switched off, and never with the screen locked.
"""
from __future__ import annotations

import os
import stat
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "bin/agentvoice"


def _cli(tmp_path, *args, stdin=""):
    """The CLI, with systemd answering that the service is running."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "systemctl"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    env = {**os.environ, "XDG_RUNTIME_DIR": str(tmp_path),
           "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    return subprocess.run(["bash", str(CLI), "type", *args], input=stdin,
                          capture_output=True, text=True, env=env, timeout=20)


def _take(daemon, monkeypatch, tmp_path):
    import wake_listen
    monkeypatch.setattr(wake_listen, "RUNTIME_DIR", tmp_path / "agentvoice")
    daemon._typed_polled = 0.0
    return daemon.take_typed()


def test_a_message_goes_from_stdin_to_the_daemon(daemon, monkeypatch, tmp_path):
    out = _cli(tmp_path, "sora", stdin="what is on my calendar\ntomorrow")
    assert out.returncode == 0, out.stderr
    folder = tmp_path / "agentvoice/typed"
    (msg,) = folder.iterdir()
    # Private: it holds what somebody typed to their agent.
    assert stat.S_IMODE(msg.stat().st_mode) == 0o600
    assert _take(daemon, monkeypatch, tmp_path) == ("sora", "what is on my calendar tomorrow")
    assert list(folder.iterdir()) == [], "a message read is a message gone"


def test_the_panel_sends_one_line(daemon, monkeypatch, tmp_path):
    out = _cli(tmp_path, "main", "--line", stdin="hello there\nnot this\n")
    assert out.returncode == 0, out.stderr
    assert _take(daemon, monkeypatch, tmp_path) == ("main", "hello there")


def test_nothing_and_a_bad_agent_are_refused(tmp_path):
    assert _cli(tmp_path, stdin="   \n").returncode == 2
    assert _cli(tmp_path, "../x", stdin="hi").returncode == 2
    assert not (tmp_path / "agentvoice/typed").exists() or \
        list((tmp_path / "agentvoice/typed").iterdir()) == []


def test_a_file_naming_an_odd_agent_is_skipped(daemon, monkeypatch, tmp_path):
    folder = tmp_path / "agentvoice/typed"
    folder.mkdir(parents=True)
    (folder / "1.msg").write_text("../../etc\nhello")
    (folder / "2.msg").write_text("main\nhello")
    assert _take(daemon, monkeypatch, tmp_path) == ("main", "hello")


def test_a_typed_turn_is_answered_with_the_microphone_off(daemon):
    daemon.enabled = False
    assert not daemon.listening
    daemon._here.typed = True
    try:
        assert daemon.listening
        daemon.locked = True
        assert not daemon.listening, "never to a locked screen"
    finally:
        daemon._here.typed = False
        daemon.locked = False


def test_a_typed_message_reaches_the_agent_and_is_answered(daemon):
    from adapters.base import Chunk

    sent = []

    class Agent:
        name = "stub"

        def send(self, text, session_id=None):
            sent.append(text)
            yield Chunk(text="Here you go. ")

        def cancel(self):
            pass

    daemon.agent = Agent()
    daemon.enabled = False                  # the microphone switched off
    daemon.handle_typed("", "what time is it", crew=False)
    assert sent and sent[0].endswith("what time is it")
    assert daemon.speaker.said == ["Here you go."], "the answer was not spoken"


def test_a_typed_message_is_dropped_when_locked(daemon):
    sent = []
    daemon.agent.send = lambda text, session_id=None: sent.append(text) or iter(())
    daemon.locked = True
    try:
        daemon.handle_typed("", "anything", crew=False)
    finally:
        daemon.locked = False
    assert sent == []


def test_no_microphone_runs_on_silence(daemon):
    """No input device used to end the daemon, taking typed messages and
    spoken replies with it."""
    import types

    def broken(**kw):
        raise OSError("no default input device")

    sd = types.SimpleNamespace(RawInputStream=broken)
    frames = []
    with daemon._microphone(sd, None, lambda data, *a: frames.append(data)):
        end = time.time() + 1.0
        while not frames and time.time() < end:
            time.sleep(0.01)
    assert frames and set(frames[0]) == {0}, "no silent frames came"
