"""The readout's two lines (phase M3, bug B and feedback item 20).

What these hold, from the plan: the agent's last answer stays on screen
while somebody replies to it (`last_reply`), and both lines clear *at once*
on a lock, on a switch to another agent or chat, and on expiry -- and stay
cleared, because crew mode re-merges an agent's last turn into every idle
payload and the words would otherwise come straight back. The preview is
four seconds of sample text through the state file, only over an idle
readout, and never over a lock.

Most of it is readout.Readout, a pure object on a fake clock; the rest is
the daemon's state file, written for real and read back.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import readout
from readout import KEEP_S, PREVIEW_S, SAMPLE_REPLY, SAMPLE_TRANSCRIPT, Readout

ROOT = Path(__file__).resolve().parent.parent


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def r(clock):
    return Readout(clock=clock)


def empty(**extra):
    """A turn starting: the wake word's cleared fields (_empty_turn)."""
    return {"transcript": "", "reply": "", "ms": 0, "audio_s": 0.0, "latency_ms": 0, **extra}


def answered(r, who=""):
    r.compose("speaking", {"transcript": "What time is it?", "reply": "Nine.", "who": who})
    return r.compose("listening", {"transcript": "What time is it?", "reply": "Nine.", "who": who})


# --- the kept reply -----------------------------------------------------------

def test_the_last_answer_is_kept_while_the_next_turn_has_none(r):
    answered(r)
    state, extra = r.compose("capture", empty())
    assert state == "capture"
    assert extra["last_reply"] == "Nine."
    assert extra["transcript"] == "" and extra["reply"] == ""


def test_it_is_not_sent_beside_a_reply_of_the_turns_own(r):
    answered(r)
    r.compose("capture", empty())
    _, extra = r.compose("speaking", {"transcript": "And tomorrow?", "reply": "Rain."})
    assert "last_reply" not in extra
    # And the new answer is the one kept from now on.
    _, extra = r.compose("capture", empty())
    assert extra["last_reply"] == "Rain."


def test_a_payload_that_says_nothing_about_the_exchange_is_left_alone(r):
    """A level update carries no reply field; the screen keeps what it had
    (it updates only fields it is sent), so nothing is added either."""
    answered(r)
    _, extra = r.compose("capture", {"level_db": -40})
    assert extra == {"level_db": -40}


def test_another_agents_turn_drops_it(r):
    answered(r, who="theo")
    _, extra = r.compose("capture", empty(who="sora", who_label="Sora"))
    assert "last_reply" not in extra
    # And it does not come back when Theo is shown again with nothing new.
    _, extra = r.compose("capture", empty(who="theo"))
    assert "last_reply" not in extra


def test_compose_never_changes_what_it_was_given(r):
    answered(r)
    given = empty()
    r.compose("capture", given)
    assert given == empty()


# --- clearing, and staying cleared -------------------------------------------

def test_a_lock_clears_both_and_they_stay_cleared_after_the_unlock(r):
    answered(r, who="theo")
    r.lock()
    # Crew mode re-merges the agent's last turn into the idle payload.
    _, extra = r.compose("listening", {"transcript": "What time is it?", "reply": "Nine.",
                                       "who": "theo"})
    assert extra["transcript"] == "" and extra["reply"] == ""
    _, extra = r.compose("capture", empty(who="theo"))
    assert "last_reply" not in extra, "the kept answer outlived the lock"


def test_a_cleared_payload_says_so_even_when_it_omits_the_fields(r):
    """The screen keeps a field it is not sent, so clearing means sending ""."""
    answered(r)
    r.lock()
    _, extra = r.compose("listening", {"level_db": -50})
    assert extra["transcript"] == "" and extra["reply"] == ""


def test_new_words_end_the_clearing(r):
    answered(r)
    r.lock()
    r.compose("listening", {"transcript": "What time is it?", "reply": "Nine."})
    _, extra = r.compose("capture", {"transcript": "Hello", "reply": ""})
    assert extra["transcript"] == "Hello"
    # And from then on an omitted field is left alone again.
    _, extra = r.compose("capture", {"level_db": -40})
    assert "transcript" not in extra


def test_expiry_clears_both_after_ten_quiet_minutes(r, clock):
    answered(r)
    clock.t += KEEP_S - 1
    assert r.expire() is False
    clock.t += 2
    assert r.expire() is True
    _, extra = r.compose("listening", {"transcript": "What time is it?", "reply": "Nine."})
    assert extra["transcript"] == "" and extra["reply"] == ""
    _, extra = r.compose("capture", empty())
    assert "last_reply" not in extra
    # Once is enough: nothing left to clear.
    clock.t += KEEP_S + 1
    assert r.expire() is False


def test_expiry_never_cuts_off_words_being_said(r, clock):
    answered(r)
    r.compose("capture", {"transcript": "Let me think about", "reply": ""})
    clock.t += KEEP_S + 1
    assert r.expire() is False


def test_new_words_restart_the_ten_minutes(r, clock):
    answered(r)
    clock.t += KEEP_S - 10
    r.compose("followup", {"transcript": "Thanks", "reply": "Nine."})
    clock.t += 20
    assert r.expire() is False


def test_a_chat_switch_drops_the_kept_answer(r):
    answered(r, who="theo")
    r.forget("theo")
    _, extra = r.compose("capture", empty(who="theo"))
    assert "last_reply" not in extra


def test_a_switch_from_the_conversation_view_clears_the_screen_too(r):
    answered(r, who="theo")
    r.forget("theo", clear=True)
    _, extra = r.compose("listening", {"transcript": "What time is it?", "reply": "Nine.",
                                       "who": "theo"})
    assert extra["transcript"] == "" and extra["reply"] == ""


def test_forgetting_one_agent_leaves_another_alone(r):
    answered(r, who="theo")
    r.forget("sora", clear=True)
    _, extra = r.compose("capture", empty(who="theo"))
    assert extra["last_reply"] == "Nine."


# --- the preview --------------------------------------------------------------

def test_the_preview_is_a_real_speaking_payload_for_four_seconds(r, clock):
    assert PREVIEW_S == 4.0
    assert r.preview() == PREVIEW_S
    state, extra = r.compose("listening", {"level_db": -50})
    assert state == "speaking"
    assert extra["transcript"] == SAMPLE_TRANSCRIPT and extra["reply"] == SAMPLE_REPLY
    assert extra["preview"] is True and extra["level_db"] == -50
    clock.t += PREVIEW_S + 0.01
    state, extra = r.compose("listening", {"level_db": -50})
    assert state == "listening" and "preview" not in extra


def test_a_real_turn_wins_over_the_preview(r):
    r.preview()
    for state in ("capture", "transcribing", "thinking", "speaking", "followup",
                  "yielded"):
        got, extra = r.compose(state, empty())
        assert got == state and "preview" not in extra, state


def test_the_sample_is_never_kept(r, clock):
    r.preview()
    r.compose("listening", {})
    clock.t += PREVIEW_S + 1
    _, extra = r.compose("capture", empty())
    assert "last_reply" not in extra
    assert SAMPLE_REPLY not in json.dumps(extra)


def test_a_lock_ends_the_preview(r, clock):
    r.preview()
    r.lock()
    clock.t += 1
    state, _ = r.compose("listening", {})
    assert state == "listening"


# --- the daemon ---------------------------------------------------------------

def written(d) -> dict:
    return json.loads(d.state.path.read_text())


def test_the_daemon_publishes_the_kept_answer(daemon):
    daemon.state.publish("speaking", transcript="What time is it?", reply="Nine.")
    daemon.state.publish("capture", **empty())
    assert written(daemon)["last_reply"] == "Nine."


def test_a_locked_payload_carries_neither_line_nor_the_kept_one(daemon):
    daemon.state.publish("speaking", transcript="What time is it?", reply="Nine.")
    daemon.state.publish("capture", **empty())
    daemon.locked = True
    daemon.state.publish("capture", **empty())
    payload = written(daemon)
    assert payload["state"] == "locked"
    for field in ("transcript", "reply", "last_reply", "preview"):
        assert field not in payload, field
    daemon.locked = False
    daemon.state.publish("listening", transcript="What time is it?", reply="Nine.")
    payload = written(daemon)
    assert payload["transcript"] == "" and payload["reply"] == ""


def test_the_preview_command_goes_through_the_state_file(daemon, monkeypatch):
    import threading
    started = []
    monkeypatch.setattr(threading.Timer, "start", lambda self: started.append(self.interval))
    daemon._publish()
    assert daemon.apply_readout_command("hud-preview") is True
    payload = written(daemon)
    assert payload["state"] == "speaking" and payload["preview"] is True
    assert payload["reply"] == SAMPLE_REPLY
    # A redraw is booked for when it ends.
    assert started and started[0] >= PREVIEW_S
    assert daemon.apply_readout_command("open-mic off") is False


def test_the_preview_is_refused_while_locked(daemon, capsys):
    daemon.locked = True
    daemon._publish()
    assert daemon.apply_readout_command("hud-preview") is True
    assert written(daemon)["state"] == "locked"
    assert not daemon.readout_for().previewing
    assert "locked" in capsys.readouterr().out


def test_the_preview_never_reaches_omarchys_agents_panel(daemon):
    seen = []

    class Panel:
        def publish(self, mic, agents):
            seen.append(mic)

    daemon.panel = Panel()
    daemon._mirror_panel({"state": "speaking", "preview": True})
    daemon._mirror_panel({"state": "listening"})
    assert seen == ["listening"]


def test_a_new_chat_drops_the_kept_answer(daemon):
    daemon.state.publish("speaking", transcript="What time is it?", reply="Nine.")
    daemon.new_chat(daemon._main)
    daemon.state.publish("capture", **empty())
    assert "last_reply" not in written(daemon)


def test_the_run_loop_and_the_idle_poll_reach_it():
    """Read off the source, because the run loop needs a microphone: the
    command is applied beside the others (expiry: further down)."""
    src = (ROOT / "daemon" / "wake_listen.py").read_text()
    loop = src[src.index("cmd = self.take_command()\n                # One implementation"):]
    loop = loop[:loop.index("if mic_cmd:")]
    assert "self.apply_readout_command(cmd)" in loop
    assert "readout_for().lock()" in src[src.index("    def _compose(self"):
                                         src.index("    def _compose_line(self")]


def test_the_cli_only_asks_for_a_preview_over_an_idle_readout():
    cli = (ROOT / "bin" / "agentvoice").read_text()
    block = cli[cli.index("  hud-preview)"):]
    block = block[:block.index("    ;;\n")]
    assert "listening|off) send_command hud-preview" in block
    assert "locked)" in block
    preview = (ROOT / "bench" / "preview" / "preview.sh").read_text()
    stubbed = re.search(r"\n  (start\|stop\|[^)]*)\)\n", preview).group(1).split("|")
    assert "hud-preview" in stubbed, "a preview's Preview button must not reach a real daemon"


def test_the_idle_and_previewable_states_are_daemon_states():
    import wake_listen
    assert set(readout.IDLE) <= set(wake_listen.STATES)
    assert set(readout.PREVIEWABLE) <= set(readout.IDLE)
    assert not set(readout.IDLE) & {"capture", "transcribing", "thinking", "speaking"}


def test_a_locked_payload_drops_the_readout_fields_whoever_sent_them(daemon):
    """Defence in depth: nothing publishes last_reply or preview itself
    today, but a lock must drop them from any payload, as it drops the
    transcript and the reply."""
    daemon.locked = True
    daemon.state.publish("capture", transcript="x", reply="y", last_reply="z", preview=True)
    payload = written(daemon)
    assert payload["state"] == "locked"
    assert not {"transcript", "reply", "last_reply", "preview"} & set(payload)


# --- Codex review of M3, pass 1 -------------------------------------------------

def test_a_signal_publishing_inside_compose_does_not_deadlock(r):
    """SIGUSR1's handler publishes from the main thread, which may already
    be inside compose() when it lands: the lock must be re-entrant."""
    import threading
    done = threading.Event()

    def nested():
        with r._lock:                     # the main thread, mid-compose
            r.compose("listening", {"transcript": "a", "reply": "b"})
        done.set()

    t = threading.Thread(target=nested, daemon=True)
    t.start()
    t.join(2)
    assert done.is_set(), "compose() deadlocked on its own lock"


def test_a_stale_copy_of_cleared_words_never_replaces_newer_ones(r):
    """Single agent: answer, lock, unlock, type a new question -- then the
    run loop's level update republishes its own copy of the old turn."""
    answered(r)
    r.lock()
    r.compose("listening", {"level_db": -50})
    _, extra = r.compose("thinking", {"transcript": "Typed question", "reply": ""})
    assert extra["transcript"] == "Typed question"
    _, extra = r.compose("listening", {"transcript": "What time is it?", "reply": "Nine.",
                                       "level_db": -45})
    assert "transcript" not in extra and "reply" not in extra, \
        "the old exchange came back over the new one"
    assert extra["level_db"] == -45


def test_a_change_of_owner_clears_words_the_payload_does_not_replace(r):
    """A lent microphone after Theo answered: `yielded`, no `who`, no text.
    The label went and Theo's words stayed."""
    answered(r, who="theo")
    _, extra = r.compose("yielded", {"who": ""})
    assert extra["transcript"] == "" and extra["reply"] == ""
    # The same owner again with nothing to say leaves the screen alone.
    _, extra = r.compose("yielded", {"who": ""})
    assert "transcript" not in extra


def test_a_capture_never_carries_an_answer(r):
    """The follow-up window opens on the finished turn and partials replace
    only the transcript: the old answer rode along as `reply` and was drawn
    whatever hudKeepReply said."""
    answered(r)
    _, extra = r.compose("capture", {"transcript": "And tomor", "reply": "Nine."})
    assert extra["reply"] == "" and extra["last_reply"] == "Nine."
    _, extra = r.compose("transcribing", {"transcript": "And tomorrow?", "reply": "Nine."})
    assert extra["reply"] == "" and extra["last_reply"] == "Nine."
    # The follow-up window itself still shows the exchange it follows.
    _, extra = r.compose("followup", {"transcript": "What time is it?", "reply": "Nine."})
    assert extra["reply"] == "Nine."


def test_the_end_of_a_preview_says_the_real_words_outright(r, clock):
    """Muted, the underlying payload is a bare `off`: without this the
    merging screen kept the sample question and answer after the preview."""
    answered(r)
    r.preview()
    _, extra = r.compose("off", {})
    assert extra["reply"] == SAMPLE_REPLY
    clock.t += PREVIEW_S + 0.1
    state, extra = r.compose("off", {})
    assert state == "off"
    assert extra["transcript"] == "What time is it?" and extra["reply"] == "Nine."
    _, extra = r.compose("off", {})
    assert extra == {}, "once is enough"


def test_expiry_is_polled_above_the_listening_gate():
    """It was in refresh(), below the gate a muted or lent microphone stops
    at, so the last exchange stayed on screen for hours."""
    src = (ROOT / "daemon" / "wake_listen.py").read_text()
    poll = src[src.index("if time.time() - last_lock_poll > 2.0:"):]
    poll = poll[:poll.index("if crew:")]
    assert "self.reconcile_lock()" in poll and "self.expire_readout()" in poll
    refresh = src[src.index("    def refresh(self):"):src.index("    def catch_up(self)")]
    assert "expire" not in refresh.replace("expire_notices", "")


def test_expire_readout_republishes_when_it_clears(daemon, clock):
    daemon.readout = Readout(clock=clock)
    daemon.state.publish("listening", transcript="What time is it?", reply="Nine.")
    clock.t += KEEP_S + 1
    daemon.expire_readout()
    payload = written(daemon)
    assert payload["transcript"] == "" and payload["reply"] == ""


def test_a_rebuild_that_ends_the_chat_clears_the_screen_too():
    src = (ROOT / "daemon" / "wake_listen.py").read_text()
    body = src[src.index("    def carry_session("):src.index("    def flags_moved(")]
    assert 'self.readout_for().forget(p.id or "", clear=True)' in body


def test_recompose_reads_its_snapshot_under_the_state_files_lock(daemon):
    seen = []
    real = daemon.state.publish

    def publish(state, **extra):
        seen.append(daemon.state._lock._is_owned())
        real(state, **extra)

    daemon.state.publish = publish
    daemon._recompose()
    assert seen == [True]


def test_push_to_talk_during_a_preview_listens_rather_than_interrupts(tmp_path):
    """Run the CLI itself, with systemd stubbed to say the service is up:
    over a preview it sends `talk`; over a real reply it interrupts (and
    here, with no daemon to signal, says so) and sends nothing."""
    import os
    import subprocess
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "systemctl").write_text("#!/bin/sh\nexit 0\n")
    (bin_dir / "systemctl").chmod(0o755)
    run = tmp_path / "run"
    (run / "agentvoice").mkdir(parents=True)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
           "XDG_RUNTIME_DIR": str(run)}
    state = run / "agentvoice" / "state"
    command = run / "agentvoice" / "command"

    state.write_text(json.dumps({"state": "speaking", "transcript": SAMPLE_TRANSCRIPT,
                                 "preview": True}))
    subprocess.run([str(ROOT / "bin" / "agentvoice"), "talk"], env=env, check=True,
                   capture_output=True)
    assert command.read_text() == "talk"

    command.unlink()
    state.write_text(json.dumps({"state": "speaking", "reply": "Nine."}))
    subprocess.run([str(ROOT / "bin" / "agentvoice"), "talk"], env=env,
                   capture_output=True)
    assert not command.exists(), "a real reply is interrupted, not talked over"


def test_neither_surface_offers_stop_during_a_preview():
    def code(name):
        return "\n".join(l.split("//")[0] for l in (ROOT / name).read_text().splitlines())
    panel, settings, hud = code("Panel.qml"), code("Settings.qml"), code("Hud.qml")
    assert "readonly property bool vTurnRunning: serviceActive && !vPreview" in panel
    assert "readonly property bool turnRunning: serviceActive && !vPreview" in settings
    # Set after the state, which the HUD's quick close depends on.
    parse = panel[panel.index("onLoaded: {"):]
    assert parse.index("voice.vState = ") < parse.index("voice.vPreview = d.preview === true")
    assert "preview: voice.vPreview" in panel
    assert re.search(r"showing && wasPreview\) \{\s*linger\.stop\(\)\s*showing = false", hud)


def test_the_overlay_forgets_the_exchange_on_lock():
    settings = (ROOT / "Settings.qml").read_text()
    assert 'if (root.vState === "locked") { root.lastTranscript = ""; root.lastReply = "" }' in settings
