"""Phase M17: Duplicate and Reset to defaults (agent_manage.py, agentfs).

A copy is a new agent: it carries what the original is told and how it
sounds, every restriction the original has, and no grant, secret, session
or replay right. A reset keeps who the agent is, puts everything else back,
and goes through the trash so Restore undoes it.
"""
from __future__ import annotations

import json
import os

import pytest

import agentfs
import agent_manage
import launch_extras
import paths
import permission_hook as hook


@pytest.fixture(autouse=True)
def data(tmp_path, monkeypatch):
    d = tmp_path / "data"
    monkeypatch.setattr(paths, "DATA_DIR", d)
    monkeypatch.setattr(paths, "AGENTS_DIR", d / "agents")
    monkeypatch.setattr(paths, "COMMUNAL_DIR", d / "communal")
    monkeypatch.setattr(hook, "AGENTS_DIR", d / "agents")
    monkeypatch.setattr(hook, "COMMUNAL_DIR", d / "communal")
    agentfs._LAST_GOOD.clear()
    launch_extras.env_path().unlink(missing_ok=True)
    launch_extras._CACHE.clear()
    yield d
    launch_extras.env_path().unlink(missing_ok=True)
    launch_extras._CACHE.clear()


SORA = {"id": "sora-1", "name": "sora", "label": "Sora", "agent": "codex", "model": "gpt-5.6",
        "effort": "high", "voice": "amy-medium", "speed": 110, "narration": "brief",
        "level": "trusted", "projectDir": "/srv/work",
        "tools": {"desktop": "on", "browser": "off", "mcp:github": "on:" + "a" * 32, "cli:gh": "off"},
        "skillsOff": ["weekly"], "notesWrite": "deny", "collaboration": "allow",
        "acceptsWork": False, "extraArgs": ["--oss"], "resume": False, "idleTimeoutS": 300,
        "instructions": "old field"}


def _make_sora():
    agentfs.create("sora-1")
    agentfs.write("sora-1", "role.md", "Reads carefully.")
    agentfs.write("sora-1", "personality.md", "Dry.")
    agentfs.write("sora-1", "instructions.md", "Answer briefly.")
    skill = paths.AGENTS_DIR / "sora-1" / "skills" / "weekly"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: weekly\ndescription: The weekly report.\n---\nSteps.\n")
    (skill / "make.sh").write_text("#!/bin/sh\necho report\n")
    notes = paths.AGENTS_DIR / "sora-1" / "notes"
    notes.mkdir()
    (notes / "secret-plan.md").write_text("a note")


# --- what a copy holds --------------------------------------------------------------------

def test_a_copy_has_no_grant_and_keeps_every_restriction():
    out = agent_manage.duplicate_entry(SORA, "sora-copy-1", "sora copy", "Sora copy")
    assert out["id"] == "sora-copy-1" and out["name"] == "sora copy" and out["enabled"] is False
    # What it runs and how it sounds come along.
    for key in ("agent", "model", "effort", "voice", "speed", "narration", "projectDir",
                "resume", "idleTimeoutS"):
        assert out[key] == SORA[key], key
    # No grant: Ask, nothing switched on.
    assert out["level"] == "ask"
    assert out["tools"] == {"browser": "off", "cli:gh": "off"}
    # Restrictions stay.
    assert out["skillsOff"] == ["weekly"] and out["notesWrite"] == "deny"
    assert out["acceptsWork"] is False
    # Not copied at all.
    for key in ("extraArgs", "instructions"):
        assert key not in out
    # "allow" is wider than a new agent's "announce": not copied.
    assert "collaboration" not in out
    for strict in ("off", "ask"):
        assert agent_manage.duplicate_entry({**SORA, "collaboration": strict}, "x", "y", "Y")[
            "collaboration"] == strict


def test_a_copy_of_an_unrestricted_agent_is_a_new_agents_entry():
    plain = {"id": "kit-1", "name": "kit", "agent": "claude"}
    out = agent_manage.duplicate_entry(plain, "kit-copy-1", "kit copy", "Kit copy")
    assert out == {"id": "kit-copy-1", "name": "kit copy", "label": "Kit copy", "enabled": False,
                   **agent_manage.NEW_AGENT}


def test_a_reset_keeps_who_it_is_and_nothing_else():
    out = agent_manage.reset_entry({**SORA, "enabled": False})
    assert out == {"id": "sora-1", "name": "sora", "label": "Sora", "enabled": False,
                   **agent_manage.NEW_AGENT}
    assert "enabled" not in agent_manage.reset_entry(SORA)


def test_a_copys_name_is_its_own():
    assert agent_manage.copy_name("sora", set()) == "sora copy"
    assert agent_manage.copy_name("hey jarvis", {"jarvis copy"}) == "jarvis second copy"
    assert agent_manage.copy_name("", set()) == "agent copy"
    taken = {f"sora {w}" for w in agent_manage._COPY_WORDS}
    with pytest.raises(agent_manage.Refused):
        agent_manage.copy_name("sora", taken)
    import runtime
    for name in ("sora copy", "jarvis second copy", "agent copy"):
        assert runtime._AGENT_NAME.fullmatch(name)


# --- duplicate, end to end --------------------------------------------------------------------

def test_duplicate_copies_the_folder_and_nothing_private(cfg_factory):
    _make_sora()
    launch_extras.set_env("sora-1", "OPENAI_API_KEY", "sk-secret-value")
    cfg = cfg_factory(voiceAgents=[SORA], mainProgram="claude")
    got = agent_manage.duplicate("sora-1", cfg)
    entry = got["entry"]
    new = entry["id"]
    assert new.startswith("sora-copy-") and new != "sora-1"
    assert entry["name"] == "sora copy" and entry["label"] == "Sora copy"
    assert entry["level"] == "ask" and "extraArgs" not in entry and entry["enabled"] is False
    # The folder: role, personality, instructions and skills; no notes.
    for f, text in (("role.md", "Reads carefully."), ("personality.md", "Dry."),
                    ("instructions.md", "Answer briefly.")):
        assert agentfs.read_file(new, f)["text"] == text
    assert got["skills"] == ["weekly"] and got["left"] == []
    assert (paths.AGENTS_DIR / new / "skills" / "weekly" / "make.sh").read_text() == "#!/bin/sh\necho report\n"
    assert not (paths.AGENTS_DIR / new / "notes").exists()
    # No secret: the environment stays with the original.
    assert launch_extras.env_for(new) == ({}, "")
    assert launch_extras.env_for("sora-1")[0] == {"OPENAI_API_KEY": "sk-secret-value"}
    # Read by the daemon as an agent that is switched off, at Ask.
    cfg2 = cfg_factory(voiceAgents=[SORA, entry], mainProgram="claude")
    assert new in cfg2.disabled_agents()
    spec = next(a for a in cfg2.all_agents() if a["id"] == new)
    assert spec["level"] == "ask" and spec["tools"]["desktop"] == "inherit"
    assert spec["detected"] == {"cli:gh": "off"} and spec["extraArgs"] == []


def test_a_copy_has_no_chat_session_or_replay_right(cfg_factory, tmp_path):
    """Chats, sessions and replay rights are keyed by id; a fresh id holds none."""
    import chats as chat_schema
    _make_sora()
    entry = agent_manage.duplicate("sora-1", cfg_factory(voiceAgents=[SORA],
                                                         mainProgram="claude"))["entry"]
    chat = {"id": "c1", "owner": "sora-1", "shared_with": ["sora-1"],
            "sessions": {"sora-1": {"session_id": "abc", "backend": "codex"}}}
    assert chat_schema.may_replay(chat, "sora-1")
    assert not chat_schema.may_replay(chat, entry["id"])
    assert entry["id"] not in chat_schema.sessions_of(chat)


def test_the_main_agent_can_be_copied(cfg_factory):
    agentfs.create("main")
    agentfs.write("main", "role.md", "The main one.")
    cfg = cfg_factory(mainProgram="claude", phrase="hey theo", mainName="Theo",
                      agentModels={"claude": "opus"}, permissions={"claude": "trusted"},
                      mainTools={"browser": "on", "desktop": "off"}, mainNotesWrite="deny",
                      mainExtraArgs=["--debug"])
    entry = agent_manage.duplicate("main", cfg)["entry"]
    assert entry["name"] == "theo copy" and entry["label"] == "Theo copy"
    assert entry["agent"] == "claude" and entry["model"] == "opus"
    assert entry["level"] == "ask" and entry["tools"] == {"desktop": "off"}
    assert entry["notesWrite"] == "deny" and "extraArgs" not in entry
    assert agentfs.read_file(entry["id"], "role.md")["text"] == "The main one."


def test_a_quarantined_agent_is_not_copied(cfg_factory):
    _make_sora()
    with pytest.raises(agent_manage.Refused, match="quarantined"):
        agent_manage.duplicate("sora-1", cfg_factory(voiceAgents=[SORA], crewQuarantine=["sora-1"]))
    with pytest.raises(agent_manage.Refused, match="quarantine list cannot be read"):
        agent_manage.duplicate("sora-1", cfg_factory(voiceAgents=[SORA], crewQuarantine="sora-1"))
    assert [p.name for p in paths.AGENTS_DIR.iterdir()] == ["sora-1"]


def test_no_copy_past_the_most_agents_or_from_unreadable_settings(cfg_factory):
    _make_sora()
    many = [SORA] + [{"id": f"a{i}", "name": f"agent {w}"} for i, w in
                     enumerate(["one", "two", "three", "four", "five", "six", "seven"])]
    with pytest.raises(agent_manage.Refused, match="already 8"):
        agent_manage.duplicate("sora-1", cfg_factory(voiceAgents=many))
    cfg = cfg_factory(voiceAgents=[SORA])
    cfg.source, cfg._toml_broken = "real", True
    with pytest.raises(agent_manage.Refused, match="settings cannot be read"):
        agent_manage.duplicate("sora-1", cfg)
    with pytest.raises(agent_manage.Refused, match="no agent"):
        agent_manage.duplicate("nobody", cfg_factory(voiceAgents=[SORA]))


def test_a_skill_that_breaks_a_rule_is_left_out_and_named(cfg_factory):
    _make_sora()
    bad = paths.AGENTS_DIR / "sora-1" / "skills" / "broken"
    bad.mkdir()
    (bad / "SKILL.md").write_text("no front matter at all")
    got = agent_manage.duplicate("sora-1", cfg_factory(voiceAgents=[SORA]))
    assert got["skills"] == ["weekly"] and [x["name"] for x in got["left"]] == ["broken"]


def test_a_link_in_the_source_folder_is_refused(cfg_factory, tmp_path):
    _make_sora()
    (paths.AGENTS_DIR / "sora-1" / "role.md").unlink()
    target = tmp_path / "elsewhere.md"
    target.write_text("not this")
    (paths.AGENTS_DIR / "sora-1" / "role.md").symlink_to(target)
    with pytest.raises(agentfs.AgentFsError, match="symlink"):
        agent_manage.duplicate("sora-1", cfg_factory(voiceAgents=[SORA]))


# --- reset, and putting it back -----------------------------------------------------------------

def test_reset_round_trips_with_restore(cfg_factory):
    _make_sora()
    got = agent_manage.reset("sora-1", json.dumps(SORA))
    assert got["entry"] == agent_manage.reset_entry(SORA)
    name = got["trash"]
    # The fresh folder holds the starting templates; the old one is in the trash.
    assert agentfs.read_file("sora-1", "role.md")["text"] == ""
    assert not (paths.AGENTS_DIR / "sora-1" / "notes").exists()
    trash = {t["name"]: t for t in agentfs.trash_list()}
    assert trash[name]["label"] == "Sora" and not trash[name]["orphan"]
    # Put back: the old folder, notes and skills; its whole settings entry.
    entry = agentfs.undo_reset(name)
    assert entry == SORA
    assert agentfs.read_file("sora-1", "role.md")["text"] == "Reads carefully."
    assert (paths.AGENTS_DIR / "sora-1" / "notes" / "secret-plan.md").read_text() == "a note"
    assert (paths.AGENTS_DIR / "sora-1" / "skills" / "weekly" / "make.sh").exists()
    # And the fresh folder went to the trash as a folder no agent uses.
    left = agentfs.trash_list()
    assert len(left) == 1 and left[0]["orphan"] is True and left[0]["id"] == "sora-1"


def test_reset_refuses_the_main_agent_and_a_wrong_entry():
    _make_sora()
    with pytest.raises(agent_manage.Refused, match="main agent"):
        agent_manage.reset("main", json.dumps({"name": "theo"}))
    with pytest.raises(agent_manage.Refused, match="another agent"):
        agent_manage.reset("sora-1", json.dumps({**SORA, "id": "kit-2"}))
    with pytest.raises(agent_manage.Refused, match="did not arrive"):
        agent_manage.reset("sora-1", "")
    assert agentfs.trash_list() == []
    assert agentfs.read_file("sora-1", "role.md")["text"] == "Reads carefully."


def test_a_reset_that_cannot_make_the_new_folder_puts_the_old_one_back(monkeypatch):
    _make_sora()

    def boom(agent_id):
        raise agentfs.AgentFsError("disk full")
    monkeypatch.setattr(agentfs, "create", boom)
    with pytest.raises(agentfs.AgentFsError):
        agentfs.reset_folder("sora-1", json.dumps(SORA))
    assert agentfs.read_file("sora-1", "role.md")["text"] == "Reads carefully."
    assert agentfs.trash_list() == []


def test_undo_reset_leaves_an_unreadable_entry_where_it_is():
    _make_sora()
    name = agent_manage.reset("sora-1", json.dumps(SORA))["trash"]
    agentfs._sidecar(agentfs._trash_dir(), name).write_text("{broken")
    with pytest.raises(agentfs.AgentFsError, match="cannot be read"):
        agentfs.undo_reset(name)
    assert agentfs.read_file("sora-1", "role.md")["text"] == ""      # the reset one, untouched


def test_the_cli_round_trip(tmp_path):
    """Through bin/agentvoice, as the page runs it."""
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    env = {**os.environ, "XDG_DATA_HOME": str(tmp_path / "xdg"), "XDG_CONFIG_HOME": str(tmp_path / "cfg"),
           "XDG_RUNTIME_DIR": str(tmp_path / "run"), "PYTHONDONTWRITEBYTECODE": "1",
           "AGENTVOICE_PYTHON": sys.executable}

    def run(*args, inp=""):
        return subprocess.run([str(root / "bin/agentvoice"), "agents", *args], input=inp,
                              capture_output=True, text=True, env=env, timeout=60)
    assert run("create", "sora-1").returncode == 0
    out = run("reset", "sora-1", "--line", inp=json.dumps(SORA) + "\n")
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert got["entry"]["level"] == "ask"
    back = run("unreset", got["trash"])
    assert back.returncode == 0 and json.loads(back.stdout) == SORA
    refused = run("reset", "main", "--line", inp="{}\n")
    assert refused.returncode == 1 and "main agent" in refused.stderr


# --- only the person does these -------------------------------------------------------------

@pytest.mark.parametrize("cmd", [
    "agentvoice agents duplicate sora-1",
    "agentvoice agents reset sora-1 --line",
    "agentvoice  agents  unreset sora-1-1795406639716567043",
    "agentvoice agents env main set ANTHROPIC_API_KEY --line",
    "agentvoice agents env sora-1 unset OPENAI_API_KEY",
    "agentvoice agents env sora-1 clear",
    "python3 daemon/agentfs.py env main set X",
])
@pytest.mark.parametrize("level", ["ask", "trusted"])
def test_an_agent_copying_resetting_or_setting_a_key_is_asked_at_every_level(cmd, level, monkeypatch):
    assert hook.orders_write("Bash", {"command": cmd}), cmd
    monkeypatch.setattr(hook, "_settings", lambda: (level, None))
    monkeypatch.setattr(hook, "_ask", lambda *a, **k: ("asked", k.get("note", "")))
    assert hook.decide("Bash", {"command": cmd})[0] == "asked"


@pytest.mark.parametrize("cmd", ["agentvoice agents env main list --json",
                                 "agentvoice agents flags check claude",
                                 "agentvoice agents runinfo sora-1 --json"])
def test_reading_names_and_checking_flags_is_not_asked(cmd):
    assert hook.orders_write("Bash", {"command": cmd}) == "", cmd


def test_the_env_file_itself_is_under_the_orders_guard():
    path = str(launch_extras.env_path())
    assert hook.orders_write("Write", {"file_path": path, "content": "{}"})
    assert hook.orders_write("Bash", {"command": f"cat > {path}"})
