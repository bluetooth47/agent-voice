"""Each voice agent as a section in Omarchy's Agents panel.

The panel draws any record in its usage directory, so what matters is the
record: that the panel will give it a section at all (ready, with a plan
line), that it never adds to the panel's token totals, that the status says
what the agent is doing, that a gone agent's record goes, and that the
setting removes them all. Nothing of Omarchy's is read or changed.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from agents_panel import PREFIX, AgentsPanel, note, record, slug, status

ROOT = Path(__file__).resolve().parent.parent


def _agent(**kw):
    base = {"key": "main", "label": "Agent Voice", "program": "claude",
            "model": "opus", "effort": "high", "level": "edits",
            "phrase": "hey computer", "activity": "idle", "hearing": False,
            "problem": ""}
    base.update(kw)
    return base


def _files(d: Path) -> dict:
    return {p.name: json.loads(p.read_text()) for p in sorted(d.glob(f"{PREFIX}*.json"))}


@pytest.fixture
def panel(tmp_path):
    clock = [100.0]
    on = [True]
    p = AgentsPanel(tmp_path, enabled=lambda: on[0], clock=lambda: clock[0],
                    today=lambda: "2026-11-16")
    p.clock, p.on = clock, on
    return p


# --- the record -------------------------------------------------------------

class TestRecord:
    def test_the_panel_gives_it_a_section(self):
        """Main.qml: providerHasData wants ready with a plan, and
        providerHasSubscription wants a plan (tierLabel) to draw a section."""
        r = record(_agent(), "listening", 0)
        assert r["ready"] is True and r["tierLabel"] != ""
        assert r["id"] == "agentvoice-main" and r["name"] == "Agent Voice (voice)"
        assert r["schemaVersion"] == 1

    def test_it_adds_nothing_to_the_totals(self):
        """The agent's own CLI is already counted by its own collector."""
        r = record(_agent(), "listening", 7)
        for k in ("todayPrompts", "todaySessions", "todayTotalTokens",
                  "totalPrompts", "totalSessions", "activeDays"):
            assert r[k] == 0, k
        assert r["modelUsage"] == {} and r["todayTokensByModel"] == {}
        assert r["limits"] == []

    def test_its_status_never_reads_as_a_sign_in_the_panel_would_offer(self):
        """Panel.qml offers to sign in again on these two strings."""
        for mic in ("listening", "off", "locked", "yielded", "capture", "", "thinking"):
            for act in ("idle", "thinking", "speaking"):
                s = status(_agent(activity=act), mic)
                assert s not in ("Sign-in expired", "Waiting for auth")

    @pytest.mark.parametrize("mic,agent,want", [
        ("listening", {}, "Listening for “hey computer”"),
        ("listening", {"activity": "thinking"}, "Thinking…"),
        ("listening", {"activity": "speaking"}, "Speaking"),
        ("capture", {"hearing": True}, "Listening to you"),
        ("transcribing", {"hearing": True}, "Transcribing"),
        ("capture", {"hearing": False}, "Listening for “hey computer”"),
        ("locked", {}, "Paused while locked"),
        ("off", {}, "Microphone off"),
        ("yielded", {}, "Paused for a recording"),
        ("listening", {"program": ""}, "Not set up"),
    ])
    def test_status_says_what_it_is_doing(self, mic, agent, want):
        assert status(_agent(**agent), mic) == want

    def test_stopped_says_off_and_how_to_start(self):
        assert status(_agent(activity="thinking"), "listening", running=False) == "Off"
        assert "middle-click" in note(_agent(), 0, running=False)

    def test_the_note_says_what_it_runs_on(self):
        n = note(_agent(), 3)
        assert n.startswith("Claude Code · opus · high effort · may edit files.")
        assert "3 voice turns today" in n
        assert "1 voice turn today" in note(_agent(), 1)

    def test_an_agent_with_no_program_says_why(self):
        n = note(_agent(program="", problem="“omarchy” is not a word it knows."), 0)
        assert "is not a word it knows" in n and "Agents page" in n

    def test_a_name_makes_a_file_name(self):
        assert slug("jarvis") == "jarvis"
        assert slug("mister smith") == "mister-smith"
        assert slug("") == "main"


# --- keeping the files in step ----------------------------------------------

class TestFiles:
    def test_one_file_per_agent(self, panel, tmp_path):
        panel.publish("listening", [_agent(), _agent(key="sarah", label="Sarah", phrase="sarah")])
        files = _files(tmp_path)
        assert set(files) == {"agentvoice-main.json", "agentvoice-sarah.json"}
        assert files["agentvoice-sarah.json"]["tierLabel"] == "Listening for “sarah”"

    def test_written_by_rename_and_nothing_left_behind(self, panel, tmp_path):
        panel.publish("listening", [_agent()])
        assert [p.name for p in tmp_path.iterdir()] == ["agentvoice-main.json"]

    def test_leaves_every_other_record_alone(self, panel, tmp_path):
        (tmp_path / "claude.json").write_text("{}")
        panel.publish("listening", [_agent()])
        panel.publish("listening", [])
        assert (tmp_path / "claude.json").read_text() == "{}"

    def test_a_removed_agent_is_removed(self, panel, tmp_path):
        panel.publish("listening", [_agent(), _agent(key="sarah")])
        panel.publish("listening", [_agent()])
        assert set(_files(tmp_path)) == {"agentvoice-main.json"}

    def test_unchanged_is_not_rewritten(self, panel, tmp_path):
        """Every microphone-level change rewrites the state file."""
        panel.publish("listening", [_agent()])
        path = tmp_path / "agentvoice-main.json"
        before = path.stat().st_mtime_ns
        panel.clock[0] += 5
        time.sleep(0.01)
        for _ in range(20):
            panel.publish("listening", [_agent()])
        assert path.stat().st_mtime_ns == before

    def test_at_most_once_a_second_and_the_last_state_lands(self, panel, tmp_path):
        panel.publish("listening", [_agent()])
        panel.publish("listening", [_agent(activity="thinking")])
        assert _files(tmp_path)["agentvoice-main.json"]["tierLabel"] == "Listening for “hey computer”"
        assert panel._timer is not None
        panel.clock[0] += 1.5
        panel._timer.cancel()
        panel._flush()
        assert _files(tmp_path)["agentvoice-main.json"]["tierLabel"] == "Thinking…"

    def test_switched_off_removes_them_and_writes_no_more(self, panel, tmp_path):
        panel.publish("listening", [_agent()])
        panel.on[0] = False
        panel.publish("listening", [_agent(activity="thinking")])
        assert _files(tmp_path) == {}
        panel.stopped()
        assert _files(tmp_path) == {}

    def test_stopping_the_service_leaves_them_saying_off(self, panel, tmp_path):
        panel.publish("listening", [_agent(activity="thinking")])
        panel.stopped()
        r = _files(tmp_path)["agentvoice-main.json"]
        assert r["tierLabel"] == "Off"


class TestTurns:
    def test_a_turn_counts_once_however_it_flickers(self, panel, tmp_path):
        for act in ("idle", "thinking", "speaking", "thinking", "speaking", "idle",
                    "thinking", "idle"):
            panel.clock[0] += 2
            panel.publish("listening", [_agent(activity=act)])
        r = _files(tmp_path)["agentvoice-main.json"]
        assert r["voiceTurns"] == {"date": "2026-11-16", "count": 2}

    def test_a_restart_keeps_the_days_count(self, panel, tmp_path):
        panel.publish("listening", [_agent(activity="thinking")])
        again = AgentsPanel(tmp_path, today=lambda: "2026-11-16")
        again.publish("listening", [_agent()])
        assert _files(tmp_path)["agentvoice-main.json"]["voiceTurns"]["count"] == 1

    def test_a_new_day_starts_at_nothing(self, panel, tmp_path):
        panel.publish("listening", [_agent(activity="thinking")])
        again = AgentsPanel(tmp_path, today=lambda: "2026-11-17")
        again.publish("listening", [_agent()])
        assert _files(tmp_path)["agentvoice-main.json"]["voiceTurns"]["count"] == 0


# --- the daemon --------------------------------------------------------------

class TestDaemon:
    def test_every_state_write_reaches_the_panel(self, daemon, tmp_path):
        daemon.panel = AgentsPanel(tmp_path)
        daemon.state.publish("listening")
        assert "agentvoice-main.json" in _files(tmp_path)

    def test_a_broken_panel_never_stops_the_readout(self, daemon):
        class Broken:
            def publish(self, *a):
                raise RuntimeError("no")
        daemon.panel = Broken()
        daemon.state.publish("thinking")
        assert daemon.state.current == "thinking"

    def test_one_agent(self, daemon):
        daemon.pipe = type("P", (), {"phrase": "hey computer", "_oww": None})()
        daemon.agent.name, daemon.agent.model = "claude", "opus"
        [main] = daemon.panel_agents({"state": "thinking"})
        assert main["program"] == "claude" and main["model"] == "opus"
        assert main["activity"] == "thinking" and main["phrase"] == "hey computer"
        assert main["label"] == "Claude Code"

    def test_side_by_side_each_says_its_own(self, daemon):
        from crew import Persona
        daemon.pipe = type("P", (), {"phrase": "computer", "_oww": None,
                                     "unheard": {"friday": "not a word it knows"}})()
        daemon.cfg._values["voiceAgents"] = [
            {"name": "jarvis", "agent": "codex", "level": "ask"},
            {"name": "friday"}]
        jarvis = daemon.crew["jarvis"] = Persona("jarvis", {"name": "jarvis", "id": "jarvis"})
        jarvis.agent = type("A", (), {"name": "codex", "model": "", "effort": None})()
        jarvis.state = "speaking"
        jarvis.thread = type("T", (), {"is_alive": lambda self: True})()
        daemon.crew["friday"] = Persona("friday", {"name": "friday", "id": "friday"})
        daemon._mic_shown = ("listening", {})
        agents = {a["key"]: a for a in daemon.panel_agents({"state": "speaking", "who": "jarvis"})}
        assert agents["main"]["activity"] == "idle"
        assert agents["jarvis"]["activity"] == "speaking" and agents["jarvis"]["program"] == "codex"
        assert agents["friday"]["program"] == "" and "not a word" in agents["friday"]["problem"]


# --- the setting and the uninstall ------------------------------------------

def test_the_setting_is_in_all_three_places():
    import runtime
    manifest = json.loads((ROOT / "manifest.json").read_text())
    assert manifest["barWidget"]["defaults"]["agentsPanel"] is True
    assert any(e["key"] == "agentsPanel" for e in manifest["barWidget"]["schema"])
    assert runtime.DEFAULTS["agentsPanel"] is True
    assert 'put("agentsPanel"' in (ROOT / "pages/OtherSettingsPage.qml").read_text()


def test_uninstall_removes_the_records_after_the_service_stops():
    text = (ROOT / "install.sh").read_text()
    stop = text.index("disable --now agentvoice.service")
    where = text.index('usage_dir="${XDG_STATE_HOME:-$HOME/.local/state}/omarchy/agents/usage"')
    rm = text.index('rm -f "$usage_dir"/agentvoice-*.json', where)
    assert stop < where < rm


def test_a_record_that_cannot_be_removed_does_not_end_the_uninstall():
    """install.sh runs under `set -e`, and a bare `rm -f` that failed (a
    read-only state directory) exited 1 there: the voice directories after it
    were never checked and the data directory was left behind. Found by the
    installer-in-a-box round trip."""
    text = (ROOT / "install.sh").read_text()
    line = text[text.rindex("\n", 0, text.index('rm -f "$usage_dir"/agentvoice-*.json')) + 1:]
    line = line[:line.index("\n")]
    assert line.strip().startswith("if ! rm -f"), line


def test_simulate_never_appears_in_the_panel():
    src = (ROOT / "daemon/wake_listen.py").read_text()
    sim = src.index("return run_simulated(pipe, speaker, args.simulate, daemon)")
    made = src.index("daemon.panel = AgentsPanel(")
    assert sim < made


def test_a_systemd_stop_runs_the_cleanup():
    """systemd stops with SIGTERM, whose default skips `finally`: the panel
    was left saying "Listening to you" after a stop, and the pidfile stayed.
    Checked live: start, wake, `agentvoice stop`, and the record reads Off."""
    src = (ROOT / "daemon/wake_listen.py").read_text()
    handler = src.index("signal.signal(signal.SIGTERM, _stopped)")
    assert "raise SystemExit(0)" in src[src.index("def _stopped"):handler]
    assert handler < src.index("    state = StateFile()\n    panel = None")
    assert src.index("panel.stopped()") > src.index("    finally:\n        state.clear()")
