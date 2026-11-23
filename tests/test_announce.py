"""Agents speak up when background work finishes (master plan M27).

announce.py decides what an event is, what is said and shown, and when; the
daemon (wake_listen.Daemon: announce_event, announce_poll,
deliver_announcements) carries it out. What these hold, in the plan's words:

- only the daemon's own job tracking or the adapter's stream starts one;
- never while locked, capturing or speaking; behind the person and other
  agents; at most one line per agent per two minutes; the spoken part at
  most 300 characters, the rest in the chat marked unprompted; duplicates
  dropped; stale events expire;
- notification only, no speech, while locked, muted or silenced, and a
  silenced line is not said on the way back;
- the notification's text is fixed, never the model's words (argv);
- the per-agent setting, read fresh, unreadable off.

The run loop itself is driven in the frame-loop tests at the end.
"""
from __future__ import annotations

import json
import queue
import subprocess
import threading
import time

import pytest

import announce
import collab
from announce import Announcer, Event
from chats import ChatStore
from crew import Persona

CANARY = "CANARY-model-words-7731"


def _until(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def bg(agent="main", key="b1", text="", label="Theo", status="completed", **kw):
    return Event(agent=agent, source="background", key=key, status=status, text=text,
                 label=label, **kw)


def crew_ev(agent="main", key="a" * 16, label="Theo", other="Sora", status="completed"):
    return Event(agent=agent, source="crew", key=key, status=status, label=label, other=other)


# --- what is said and shown ----------------------------------------------------------

def test_a_crew_line_names_the_other_agent_and_carries_no_result():
    line = announce.fixed_line(crew_ev())
    assert line == "The task I gave Sora is done, and I have the result."
    assert announce.fixed_line(crew_ev(status="failed")) == "The task I gave Sora didn't finish."
    for word in (" her ", " him ", " it ", " she ", " he "):
        assert word not in f" {line} "


def test_a_background_finish_without_words_has_a_fixed_line():
    assert announce.what_is_said(bg()) == ("My background task has finished.",) * 2
    assert announce.what_is_said(bg(status="failed"))[0] == "My background task didn't finish."


def test_the_notification_never_holds_the_models_words():
    for ev in (bg(text=f"{CANARY} the tests passed"), crew_ev(), bg(status="failed", text=CANARY)):
        assert CANARY not in announce.notification_text(ev)
    assert announce.notification_text(bg()) == "Theo finished a background task"
    assert announce.notification_text(crew_ev()) == "Sora finished a task for Theo"


def test_notify_puts_only_the_fixed_text_in_argv():
    seen = []

    def run(argv, **kw):
        seen.append((argv, kw))
        return subprocess.CompletedProcess(argv, 0)
    assert announce.notify(bg(text=f"{CANARY} secret result"), run=run) == ""
    argv, kw = seen[0]
    assert argv == ["notify-send", "--app-name=Agent Voice", "--", "Theo finished a background task"]
    assert CANARY not in json.dumps(seen, default=str)
    assert kw["stdin"] == subprocess.DEVNULL and kw["timeout"] <= 5


def test_a_label_cannot_smuggle_lines_or_controls_into_the_notification():
    ev = bg(label="Theo\n\x1b[31mrm -rf\x07")
    text = announce.notification_text(ev)
    assert "\n" not in text and "\x1b" not in text and "\x07" not in text


@pytest.mark.parametrize("raises, want", [(FileNotFoundError, "missing"),
                                          (subprocess.TimeoutExpired, "failed"),
                                          (OSError, "failed")])
def test_a_missing_or_broken_notification_service_is_reported_not_raised(raises, want):
    def run(argv, **kw):
        raise raises(*(("notify-send", 5) if raises is subprocess.TimeoutExpired else ()))
    assert announce.notify(bg(), run=run) == want


def test_the_suite_never_reaches_the_desktop(tmp_path):
    """conftest's stand-in: nothing runs, as on a machine without either
    command, so no test pops a real notification or asks the real shell."""
    assert announce._run is not subprocess.run
    assert announce.notify(bg()) == "missing"
    assert announce.silenced(path=tmp_path / "none") == (False, "no file")


def test_a_failing_notify_send_is_reported():
    assert announce.notify(bg(), run=lambda a, **k: subprocess.CompletedProcess(a, 1)) == "failed"


def test_the_spoken_part_is_at_most_300_characters_cut_after_a_sentence():
    text = " ".join(f"Sentence number {i} says something fairly long." for i in range(20))
    spoken = announce.spoken_part(text)
    assert len(spoken) <= announce.SPOKEN_MAX
    assert spoken.endswith(".") and spoken in text


def test_a_spoken_part_with_no_sentence_end_is_cut_at_a_word():
    text = "word " * 200
    spoken = announce.spoken_part(text)
    assert len(spoken) <= announce.SPOKEN_MAX and spoken.endswith("…")
    assert not spoken[:-1].endswith(" ")


def test_the_spoken_part_is_flattened_markdown():
    spoken = announce.spoken_part("The build **passed**: `make test` printed `ok`.")
    assert "`" not in spoken and "*" not in spoken and "make test" in spoken


def test_the_chat_keeps_the_whole_text_where_speech_keeps_300():
    text = "First part. " * 60
    spoken, kept = announce.what_is_said(bg(text=text))
    assert len(spoken) <= 300 and kept == text.strip()


# --- what counts as an event -------------------------------------------------------------

@pytest.mark.parametrize("ev, why", [
    (Event(agent="main", source="model", key="k"), "not a source"),
    (Event(agent="Main Agent!", source="background", key="k"), "no such agent"),
    (Event(agent="main", source="background", key=""), "no key"),
    (Event(agent="main", source="background", key="k", status="running"), "not a finish"),
    (Event(agent="main", source="crew", key="k", text="I did it"), "carries no text"),
])
def test_a_forged_or_malformed_event_is_refused(ev, why):
    assert why in Announcer().offer(ev)


def test_the_same_finish_is_said_once():
    a = Announcer()
    assert a.offer(bg(key="t1"), now=100) == ""
    assert a.offer(bg(key="t1", text="again"), now=101) == "already announced"
    assert a.offer(bg(key="t1"), now=100 + announce.SEEN_KEEP_S + 1) == ""
    assert a.pending() == 2


def test_two_agents_may_finish_the_same_key():
    a = Announcer()
    assert a.offer(bg(agent="main", key="t1")) == ""
    assert a.offer(bg(agent="sora", key="t1")) == ""


def test_the_queue_is_bounded():
    a = Announcer(queue_max=2)
    assert a.offer(bg(key="1")) == "" and a.offer(bg(key="2")) == ""
    assert a.offer(bg(key="3")) == "too many waiting"


def test_one_line_per_agent_per_two_minutes_and_the_rest_wait():
    a = Announcer()
    for key, agent in (("1", "main"), ("2", "main"), ("3", "sora")):
        a.offer(bg(agent=agent, key=key), now=0)
    go = lambda e: "go"
    first = a.next_due(go, now=10)
    a.spoke(first.agent, now=10)
    second = a.next_due(go, now=11)
    assert (first.key, second.key) == ("1", "3"), "Sora is not held by Theo's limit"
    a.spoke(second.agent, now=11)
    assert a.next_due(go, now=10 + announce.RATE_S - 1) is None
    assert a.next_due(go, now=10 + announce.RATE_S).key == "2"


def test_a_busy_agent_holds_its_own_lines_in_order():
    a = Announcer()
    a.offer(bg(agent="main", key="1"))
    a.offer(bg(agent="main", key="2"))
    a.offer(bg(agent="sora", key="3"))
    got = a.next_due(lambda e: "wait" if e.agent == "main" else "go")
    assert got.key == "3" and a.pending() == 2
    assert a.next_due(lambda e: "go").key == "1"


def test_a_dropped_agent_comes_back_with_why():
    a = Announcer()
    a.offer(bg(key="1"))
    got = a.next_due(lambda e: "off")
    assert got.extra["outcome"] == "off" and a.pending() == 0


def test_stale_events_expire():
    a = Announcer()
    a.offer(bg(key="old"), now=0)
    a.offer(bg(key="new"), now=announce.STALE_S)
    old = a.expired(now=announce.STALE_S + 1)
    assert [e.key for e in old] == ["old"] and a.pending() == 1


def test_a_stop_drops_only_that_agents_lines():
    a = Announcer()
    a.offer(bg(agent="main", key="1"))
    a.offer(bg(agent="sora", key="2"))
    assert [e.key for e in a.drop("sora")] == ["2"]
    assert [e.key for e in a.clear()] == ["1"] and a.pending() == 0


def test_notifications_have_the_same_limit():
    a = Announcer()
    assert a.may_notify("main", now=0)
    assert not a.may_notify("main", now=1)
    assert a.may_notify("sora", now=1)
    assert a.may_notify("main", now=announce.RATE_S)


# --- Omarchy's notification silencing -----------------------------------------------------

def _shell(answer, code=0):
    def run(argv, **kw):
        assert argv == ["omarchy-shell", "notifications", "isDnd"]
        return subprocess.CompletedProcess(argv, code, stdout=answer, stderr="")
    return run


def _no_shell(argv, **kw):
    raise FileNotFoundError


def test_the_running_shell_is_asked_first(tmp_path):
    assert announce.silenced(run=_shell("on\n"), path=tmp_path / "x") == (True, "shell")
    assert announce.silenced(run=_shell("off"), path=tmp_path / "x") == (False, "shell")


@pytest.mark.parametrize("content, want", [
    (None, (False, "no file")),                 # the shell's own default
    ('{"dnd":true}', (True, "file")),
    ('{"dnd":false}\n', (False, "file")),
    ('{"dnd":"yes"}', (True, "unreadable")),
    ("not json", (True, "unreadable")),
    ("[]", (True, "unreadable")),
])
def test_then_the_file_it_keeps_the_switch_in(tmp_path, content, want):
    path = tmp_path / "quiet.json"
    if content is not None:
        path.write_text(content)
    assert announce.silenced(run=_no_shell, path=path) == want
    assert announce.silenced(run=_shell("", code=1), path=path) == want


def test_a_quiet_file_that_cannot_be_read_is_quiet(tmp_path):
    path = tmp_path / "quiet.json"
    path.mkdir()                            # reading it raises IsADirectoryError
    assert announce.silenced(run=_no_shell, path=path) == (True, "unreadable")


def test_the_quiet_file_is_omarchys(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert announce.quiet_file() == tmp_path / "omarchy" / "notifications" / "quiet.json"


# --- the setting ----------------------------------------------------------------------------

def test_on_by_default_for_the_main_agent_and_an_extra_one(cfg_factory):
    cfg = cfg_factory(voiceAgents=[{"name": "sora"}])
    assert cfg.speak_when_done_for("main") is True
    assert cfg.speak_when_done_for("") is True
    assert cfg.speak_when_done_for("sora") is True


@pytest.mark.parametrize("value, want", [(False, False), (True, True), ("false", False),
                                         ("true", False), (0, False), (1, False), (None, False)])
def test_only_a_bool_counts(cfg_factory, value, want):
    cfg = cfg_factory(mainSpeakWhenDone=value,
                      voiceAgents=[{"name": "sora", "speakWhenDone": value}])
    assert cfg.speak_when_done_for("main") is want
    assert cfg.speak_when_done_for("sora") is want


def test_unreadable_settings_are_quiet(cfg_factory):
    cfg = cfg_factory(voiceAgents=[{"name": "sora"}])
    cfg.source = "file"
    cfg._toml_broken = True
    assert cfg.speak_when_done_for("main") is False
    assert cfg.speak_when_done_for("sora") is False


def test_an_agent_the_settings_do_not_have_is_quiet(cfg_factory):
    assert cfg_factory().speak_when_done_for("nobody") is False


def test_the_setting_is_three_things():
    import runtime
    manifest = json.loads((announce.Path(__file__).resolve().parent.parent
                           / "manifest.json").read_text())
    bar = manifest["barWidget"]
    keys = {e["key"]: e for e in bar["schema"]}
    assert keys["mainSpeakWhenDone"]["type"] == "bool"
    assert keys["mainSpeakWhenDone"]["defaultValue"] is True
    assert bar["defaults"]["mainSpeakWhenDone"] is True
    assert runtime.DEFAULTS["mainSpeakWhenDone"] is True
    page = (announce.Path(__file__).resolve().parent.parent / "pages" / "AgentsPage.qml").read_text()
    assert 's.put("mainSpeakWhenDone", value)' in page
    assert 'updateAgent(index, "speakWhenDone"' in page


# --- the daemon -------------------------------------------------------------------------------

class Voice:
    """A speaker that logs what it said, honouring the watch between chunks."""

    def __init__(self, name, log):
        self.name, self.log = name, log
        self.cancelled = 0
        self.first_audio_at = None

    def say(self, text, watch=None):
        for _ in range(3):
            if watch is not None and watch():
                self.log.append((self.name, "cut", text))
                return
        self.first_audio_at = time.time()
        self.log.append((self.name, "said", text))

    def cancel(self):
        self.cancelled += 1


class Agent:
    name = "claude"
    cwd = "/p"

    def __init__(self, background=False):
        self.cancelled = 0
        self.background = background

    def send(self, text, session_id=None):
        return iter(())

    def cancel(self):
        self.cancelled += 1

    def background_running(self):
        return self.background


@pytest.fixture
def room(daemon, tmp_path, monkeypatch):
    """Theo (main) and Sora, each with a voice; notifications recorded, not
    shown; silencing off."""
    d = daemon
    log: list = []
    spec = {"id": "sora", "name": "sora", "label": "Sora", "agent": "claude"}
    d.cfg._values.update(voiceAgents=[spec], mainName="Theo", keepHistory=True,
                         saveChats=True)
    d.enabled, d.locked, d.yielded = True, False, False
    d._frames = queue.Queue()
    d.pipe = type("P", (), {"conversation": True, "phrase": "theo", "names": ["sora"]})()
    d._main.name, d._main.label = "theo", "Theo"
    d._main.agent = Agent()
    d._main.speaker = Voice("main", log)
    sora = d.crew["sora"] = Persona("sora", spec)
    sora.agent, sora.speaker = Agent(), Voice("sora", log)
    d.chats = ChatStore(tmp_path / "chats")
    d.history.path = tmp_path / "history.jsonl"
    shown: list = []
    monkeypatch.setattr(announce, "notify",
                        lambda ev, run=None: shown.append(announce.notification_text(ev)) or "")
    monkeypatch.setattr(announce, "silenced", lambda *a, **k: (False, "test"))
    d.shown, d.log = shown, log
    return d


def said(d):
    return [(who, text) for who, how, text in d.log if how == "said"]


def deliver(d):
    """The run loop's quiet moment, and the announcing thread let finish."""
    d.announce_poll()
    d.deliver_announcements()
    assert _until(lambda: d._announcing is None)


def history(d):
    if not d.history.path.exists():
        return []
    return [json.loads(line) for line in d.history.path.read_text().splitlines()]


def test_an_event_is_shown_at_once_and_said_at_a_quiet_moment(room):
    d = room
    assert d.announce_event(bg(agent="sora", label="Sora", text="The tests passed."))
    assert d.shown == ["Sora finished a background task"]
    assert said(d) == []
    deliver(d)
    assert said(d) == [("sora", "The tests passed.")]
    assert d.announcer.pending() == 0
    rows = history(d)
    assert rows[-1]["unprompted"] is True and rows[-1]["said"] is True
    assert rows[-1]["reply"] == "The tests passed." and rows[-1]["transcript"] == ""


def test_the_line_goes_into_the_agents_chat_marked_unprompted(room):
    d = room
    sora = d.crew["sora"]
    sora.chat_id = d.chats.record(chat_id=None, agent_id="sora", agent_label="Sora",
                                  backend="claude", session_id="s1", project_dir="/p",
                                  exchange={"transcript": "run the tests", "reply": "On it."})
    text = "Everything passed. " * 40
    d.announce_event(bg(agent="sora", label="Sora", text=text))
    deliver(d)
    chat = d.chats.load(sora.chat_id)
    last = chat["exchanges"][-1]
    assert last["kind"] == "unprompted" and last["transcript"] == ""
    assert last["reply"] == text.strip(), "the chat keeps all of it"
    assert len(said(d)[0][1]) <= 300, "the voice says at most 300 characters"


def test_no_chat_is_started_for_a_line(room):
    d = room
    d.announce_event(bg(agent="sora", label="Sora", text="Done."))
    deliver(d)
    assert not (d.chats.root.exists() and any(d.chats.root.glob("*.json")) and
                d.chats.list()), "an announcement never starts a chat"


@pytest.mark.parametrize("why", ["locked", "muted", "lent", "silenced"])
def test_locked_muted_lent_or_silenced_is_the_notification_only(room, monkeypatch, capsys, why):
    d = room
    seen = []
    real = d.state.publish

    def publish(state, **extra):
        real(state, **extra)
        seen.append(dict(d.state._last))
    d.state.publish = publish
    if why == "locked":
        d.locked = True
    elif why == "muted":
        d.enabled = False
    elif why == "lent":
        d.yielded = True
    else:
        monkeypatch.setattr(announce, "silenced", lambda *a, **k: (True, "shell"))
    d.announce_event(bg(agent="sora", label="Sora", text=f"{CANARY} done."))
    assert d.shown == ["Sora finished a background task"]
    deliver(d)
    assert said(d) == [] and d.announcer.pending() == 0
    assert history(d)[-1]["said"] is False
    assert not [x for x in seen if x.get("unprompted")], "nothing of it on screen either"
    assert f"background completed, {why}" in capsys.readouterr().out
    # And not on the way back: nothing kept to be said.
    d.locked, d.enabled, d.yielded = False, True, False
    monkeypatch.setattr(announce, "silenced", lambda *a, **k: (False, "test"))
    d._silenced_seen = (0.0, False, "")
    deliver(d)
    assert said(d) == []


def test_switched_off_nothing_is_shown_or_said_but_the_words_are_kept(room):
    d = room
    d.cfg._values["voiceAgents"] = [{**d.crew["sora"].spec, "speakWhenDone": False}]
    d.announce_event(bg(agent="sora", label="Sora", text="Done quietly."))
    deliver(d)
    assert d.shown == [] and said(d) == []
    assert history(d)[-1]["reply"] == "Done quietly." and history(d)[-1]["said"] is False


def test_switched_off_while_it_waited_it_is_not_said(room):
    d = room
    d.announce_event(bg(agent="sora", label="Sora", text="Done."))
    d.cfg._values["voiceAgents"] = [{**d.crew["sora"].spec, "speakWhenDone": False}]
    deliver(d)
    assert said(d) == []


def test_unreadable_settings_are_quiet_from_the_start(room):
    d = room
    d.cfg.source = "file"
    d.cfg._toml_broken = True
    d.announce_event(bg(agent="sora", label="Sora", text="Done."))
    deliver(d)
    assert d.shown == [] and said(d) == []


@pytest.mark.parametrize("busy", ["speaking", "hold", "turn"])
def test_never_over_anybody_and_then_said(room, busy):
    d = room
    d.announce_event(bg(agent="sora", label="Sora", text="Done."))
    gate = threading.Event()
    if busy == "speaking":
        d._speaking = True
    elif busy == "hold":
        d._hold(True)
    else:
        d._main.thread = threading.Thread(target=gate.wait, daemon=True)
        d._main.thread.start()
    deliver(d)
    assert said(d) == [] and d.announcer.pending() == 1
    d._speaking = False
    d._hold(False)
    gate.set()
    if d._main.thread is not None:
        d._main.thread.join(2)
    deliver(d)
    assert said(d) == [("sora", "Done.")]


def test_a_task_turn_working_quietly_does_not_hold_it(room):
    d = room
    gate = threading.Event()
    d._main.task = object()
    d._main.thread = threading.Thread(target=gate.wait, daemon=True)
    d._main.thread.start()
    d.announce_event(bg(agent="sora", label="Sora", text="Done."))
    deliver(d)
    gate.set()
    assert said(d) == [("sora", "Done.")]


def test_its_own_turn_holds_its_line(room):
    d = room
    gate = threading.Event()
    sora = d.crew["sora"]
    sora.task = object()             # a task turn: holds only Sora's own line
    sora.thread = threading.Thread(target=gate.wait, daemon=True)
    sora.thread.start()
    d.announce_event(bg(agent="sora", label="Sora", text="Done."))
    deliver(d)
    assert said(d) == []
    gate.set()
    sora.thread.join(2)
    deliver(d)
    assert said(d) == [("sora", "Done.")]


def test_two_agents_one_after_the_other(room):
    d = room
    d.announce_event(bg(agent="sora", key="s", label="Sora", text="Sora's done."))
    d.announce_event(bg(agent="main", key="t", label="Theo", text="Theo's done."))
    deliver(d)
    deliver(d)
    assert said(d) == [("sora", "Sora's done."), ("main", "Theo's done.")]
    assert d.shown == ["Sora finished a background task", "Theo finished a background task"]


def test_the_rate_limit_holds_a_second_line(room):
    d = room
    d.announce_event(bg(agent="sora", key="1", label="Sora", text="One."))
    d.announce_event(bg(agent="sora", key="2", label="Sora", text="Two."))
    deliver(d)
    deliver(d)
    assert said(d) == [("sora", "One.")] and d.announcer.pending() == 1
    assert d.shown == ["Sora finished a background task"], "one popup for the burst"
    d.announcer._said["sora"] -= announce.RATE_S
    deliver(d)
    assert said(d)[-1] == ("sora", "Two.")


def test_a_stale_line_is_recorded_unsaid(room):
    d = room
    d.announce_event(bg(agent="sora", label="Sora", text="Old news.",
                        finished=time.time() - announce.STALE_S - 1))
    deliver(d)
    assert said(d) == [] and history(d)[-1]["said"] is False


def test_the_notification_service_missing_does_not_stop_the_line(room, monkeypatch, capsys):
    d = room
    monkeypatch.setattr(announce, "notify", lambda ev, run=None: "missing")
    d.announce_event(bg(agent="sora", label="Sora", text="Done."))
    deliver(d)
    assert said(d) == [("sora", "Done.")]
    assert "notify-send missing" in capsys.readouterr().out


def test_a_stop_for_that_agent_drops_its_lines(room):
    d = room
    d.announce_event(bg(agent="sora", key="1", label="Sora", text="Done."))
    d.announce_event(bg(agent="main", key="2", label="Theo", text="Mine."))
    d.collab.stop_from(d.crew["sora"])
    deliver(d)
    assert said(d) == [("main", "Mine.")]


def test_the_global_stop_clears_them_and_from_a_signal_only_asks(room):
    d = room
    d.announce_event(bg(agent="sora", label="Sora", text="Done."))
    d.collab.stop_all(from_signal=True)
    assert d.announcer.pending() == 1, "nothing taken inside a signal handler"
    deliver(d)
    assert said(d) == [] and d.announcer.pending() == 0
    d.announce_event(bg(agent="sora", key="2", label="Sora", text="Again."))
    d.collab.stop_all()
    deliver(d)
    assert said(d) == []


def test_a_line_from_an_earlier_conversation_is_not_said(room):
    from adapters.base import Unprompted
    d = room
    sora = d.crew["sora"]
    sora.session_id = "now"
    d.background_finished("sora", sora.agent, Unprompted(tasks=(("b1", "completed"),),
                                                         text="Done.", session="before"))
    assert d.announcer.pending() == 0 and d.shown == []
    d.background_finished("sora", sora.agent, Unprompted(tasks=(("b2", "completed"),),
                                                         text="Done.", session="now"))
    assert d.announcer.pending() == 1


def test_a_line_from_an_adapter_the_agent_no_longer_has_is_not_said(room):
    from adapters.base import Unprompted
    d = room
    old = d.crew["sora"].agent
    d.crew["sora"].agent = Agent()
    d.background_finished("sora", old, Unprompted(tasks=(("b1", "completed"),), text="x"))
    d.background_finished("gone", old, Unprompted(tasks=(("b2", "completed"),), text="x"))
    assert d.announcer.pending() == 0


def test_a_failed_background_turn_is_a_failure(room):
    from adapters.base import Unprompted
    d = room
    d.background_finished("sora", d.crew["sora"].agent,
                          Unprompted(tasks=(("b1", "failed"),), text="", failed=True))
    assert d.shown == ["Sora's background task failed"]
    deliver(d)
    assert said(d) == [("sora", "My background task didn't finish.")]


def test_a_follow_up_window_opens_after_a_line_said(room):
    d = room
    d.announce_event(bg(agent="sora", label="Sora", text="Done."))
    deliver(d)
    sora = d.crew["sora"]
    assert sora.follow_up is True
    assert d._due_follow_up() is sora


def test_no_window_after_a_line_that_was_not_said(room):
    d = room
    d.locked = True
    d.announce_event(bg(agent="sora", label="Sora", text="Done."))
    deliver(d)
    assert d.crew["sora"].follow_up is False


def test_the_readout_shows_it_speaking_unprompted_and_a_lock_strips_it(room):
    d = room
    seen = []
    real = d.state.publish

    def publish(state, **extra):
        real(state, **extra)
        seen.append(json.loads(json.dumps(d.state._last, default=str)))
    d.state.publish = publish
    d.announce_event(bg(agent="sora", label="Sora", text="Done."))
    deliver(d)
    speaking = [p for p in seen if p.get("state") == "speaking"]
    assert speaking and speaking[0]["who_label"] == "Sora"
    assert speaking[0].get("unprompted") is True
    assert "Sora: background work finished" in speaking[0].get("notice", "")
    d.locked = True
    d._recompose()
    last = seen[-1]
    assert last["state"] == "locked"
    assert "unprompted" not in last and "notice" not in last and "reply" not in last


def test_a_lock_spares_an_idle_agents_background_work(room):
    """It keeps running behind the lock, as a task does; a turn under way
    still stops, and so does an idle agent with nothing running."""
    d = room
    d._main.agent = Agent(background=True)
    d.crew["sora"].agent = Agent(background=False)
    d.silence()
    assert d._main.agent.cancelled == 0
    assert d.crew["sora"].agent.cancelled == 1


def test_a_lock_stops_a_turn_under_way_even_with_background_work(room):
    d = room
    gate = threading.Event()
    d._main.agent = Agent(background=True)
    d._main.thread = threading.Thread(target=gate.wait, daemon=True)
    d._main.thread.start()
    d.silence()
    gate.set()
    assert d._main.agent.cancelled == 1


def test_the_interrupt_cuts_a_line_and_stops_no_agent(room):
    d = room
    sora = d.crew["sora"]
    d._announcing = sora
    d._on_interrupt()
    assert sora.speaker.cancelled == 1 and sora.interrupt.is_set()
    assert sora.agent.cancelled == 0
    d._announcing = None


def test_an_announcement_cut_by_a_lock_does_not_stop_its_agent(room):
    d = room
    sora = d.crew["sora"]

    class Locks(Voice):
        def say(self, text, watch=None):
            d.locked = True
            super().say(text, watch)
    sora.speaker = Locks("sora", d.log)
    d.announce_event(bg(agent="sora", label="Sora", text="Done."))
    deliver(d)
    assert sora.agent.cancelled == 0
    assert said(d) == []
    assert history(d)[-1]["said"] is False


def test_a_lock_landing_just_before_the_sentence_stops_no_agent(room):
    """The lock arrives after the line was decided and the floor taken, as
    speak() looks one last time: the line is simply not said. Stopping the
    agent there, as a reply's turn would be, would kill the background work
    its process may still be doing."""
    d = room
    sora = d.crew["sora"]
    d.poll_session = lambda: setattr(d, "locked", True)
    d.announce_event(bg(agent="sora", label="Sora", text="Done."))
    deliver(d)
    assert said(d) == [] and sora.agent.cancelled == 0
    assert history(d)[-1]["said"] is False


def test_no_window_after_a_line_cut_short_while_the_room_still_listens(room):
    d = room
    sora = d.crew["sora"]

    class Cut(Voice):
        def say(self, text, watch=None):
            sora.interrupt.set()            # the interrupt keybind, mid-line
            super().say(text, watch)
    sora.speaker = Cut("sora", d.log)
    d.announce_event(bg(agent="sora", label="Sora", text="Done."))
    deliver(d)
    assert d.listening and said(d) == []
    assert sora.follow_up is False


def test_nothing_an_agent_can_reach_files_an_announcement():
    """Only collab (a task it tracked) and the adapter's stream call into it:
    no CLI verb, no crew tool, no command file."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    callers = []
    for path in list((root / "daemon").rglob("*.py")) + [root / "bin" / "agentvoice"]:
        text = path.read_text(errors="replace")
        if "announce_event" in text or "background_finished" in text:
            callers.append(path.relative_to(root).as_posix())
    assert sorted(callers) == ["daemon/collab.py", "daemon/wake_listen.py"]
    crew_tools = (root / "daemon" / "crew_mcp.py").read_text()
    assert "announce" not in crew_tools


# --- the frame loop ------------------------------------------------------------------------

@pytest.fixture
def one(daemon, monkeypatch, tmp_path):
    """The main agent alone, as the run loop drives it."""
    d = daemon
    d.cfg._values.update(keepHistory=True)
    d.history.path = tmp_path / "history.jsonl"
    shown: list = []
    monkeypatch.setattr(announce, "notify",
                        lambda ev, run=None: shown.append(announce.notification_text(ev)) or "")
    monkeypatch.setattr(announce, "silenced", lambda *a, **k: (False, "test"))
    d.shown = shown
    return d


def _timed(d, clock):
    """The speaker's lines with the fake time each was said at."""
    out = []
    real = d.speaker.say

    def say(text, watch=None):
        out.append((clock.now, text))
        return real(text, watch)
    d.speaker.say = say
    return out


def test_the_frame_loop_never_speaks_while_locked_and_not_after(one, monkeypatch):
    import frame_loop
    d = one
    clock = frame_loop.Clock()
    lines = _timed(d, clock)

    def lock():
        d.locked = True

    def unlock():
        d.locked = False

    def queue_it():
        d.announce_event(bg(text=f"{CANARY} finished."))
    items = [lock, queue_it] + [frame_loop.QUIET] * 5 + [unlock] + [frame_loop.QUIET] * 10
    frame_loop.drive(d, monkeypatch, items, clock=clock)
    assert lines == [], "said over a lock screen, or on the way back"
    assert d.shown == ["Theo finished a background task"]
    assert d.announcer.pending() == 0


def test_the_frame_loop_waits_for_a_capture_and_its_reply(one, monkeypatch):
    """Queued while somebody is talking to the agent: said only once the
    capture, the turn and the reply's follow-up window are over."""
    import frame_loop
    d = one
    clock = frame_loop.Clock()
    lines = _timed(d, clock)
    marks = {}

    def queue_it():
        marks["queued"] = clock.now
        d.announce_event(bg(text="The job finished."))
    pipe = frame_loop.Pipe(feed_wake=frame_loop.wake_on(1))
    items = ([frame_loop.LOUD] * 3 + [queue_it] + [frame_loop.LOUD] * 3
             + [frame_loop.QUIET] * 25)
    payloads, _ = frame_loop.drive(d, monkeypatch, items, pipe=pipe, clock=clock)
    assert [t for _, t in lines] == ["The job finished."]
    at = lines[0][0]
    assert at > marks["queued"]
    # Nothing was said while the capture or the reply's window was open.
    open_until = max(t for t, p in payloads if p.get("state") in ("capture", "transcribing",
                                                                  "thinking", "followup")
                     and t <= at)
    assert at >= open_until
    window = [t for t, p in payloads if p.get("state") == "followup" and t < at]
    assert window, "the reply's follow-up window came first"
    # And it ran its course: not said inside the reply's window.
    assert at - window[0] >= pipe.follow_up_ms / 1000 - frame_loop.FRAME_S
    speaking = [p for t, p in payloads if p.get("state") == "speaking" and p.get("unprompted")]
    assert speaking and speaking[0]["reply"] == "The job finished."


def test_the_frame_loop_opens_the_usual_window_after_a_line(one, monkeypatch):
    import frame_loop
    d = one
    clock = frame_loop.Clock()
    _timed(d, clock)

    def queue_it():
        d.announce_event(bg(text="The job finished."))
    items = [queue_it] + [frame_loop.QUIET] * 3
    payloads, _ = frame_loop.drive(d, monkeypatch, items, clock=clock)
    states = [p.get("state") for _, p in payloads]
    assert "speaking" in states
    after = states[states.index("speaking"):]
    assert "followup" in after, "the usual window, without the wake word"
