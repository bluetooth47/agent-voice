"""Migration, and the agents told what their folders say (merged plan, Phase 10).

The checks A10-1 to A10-3: every Phase 8 fixture migrates to exactly the
folders its `expect` block names, with the instructions it says; a second
run, a run after a kill, and a run over files the person already has change
nothing that exists; shell.json is never written; and an instructions file
emptied on purpose stays empty rather than falling back to the old setting.
Then the daemon side: the main agent and the extra agents are told the file,
a hand edit reaches them on the next poll, and the Agents page writes the
file and no longer the retired setting.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

import agentfs
import paths

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "agents"
ALL = sorted(FIXTURES.glob("*.json"))


@pytest.fixture(autouse=True)
def data(tmp_path, monkeypatch):
    d = tmp_path / "data"
    monkeypatch.setattr(paths, "DATA_DIR", d)
    monkeypatch.setattr(paths, "AGENTS_DIR", d / "agents")
    monkeypatch.setattr(paths, "COMMUNAL_DIR", d / "communal")
    agentfs._LAST_GOOD.clear()
    return d


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def folders() -> set[str]:
    return {p.name for p in paths.AGENTS_DIR.iterdir()
            if p.is_dir() and not p.name.startswith(".")}


def tree(root: Path) -> dict[str, bytes]:
    """Every file under `root`, by relative path, with its bytes."""
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


# --- A10-1: every fixture -----------------------------------------------------

@pytest.mark.parametrize("path", ALL, ids=lambda p: p.stem)
def test_every_fixture_migrates_to_exactly_its_folders(path, cfg_factory):
    fx = load(path)
    cfg = cfg_factory(**fx["settings"])
    report = agentfs.migrate(cfg)
    want = fx["expect"]["folders"]
    assert folders() == set(want), report
    assert report["problems"] == [] and report["recorded"]
    for folder, exp in want.items():
        got = agentfs.read_file(folder, "instructions.md")
        assert got["exists"]
        if "instructions_chars" in exp:
            assert got["chars"] == exp["instructions_chars"], folder
        if "instructions" in exp:
            assert got["text"] == exp["instructions"], folder
        # A migrated file is a saved version, not a change from outside.
        assert not got["changed_outside"], folder
        for name in agentfs.AGENT_FILES:
            assert agentfs.read_file(folder, name)["exists"], (folder, name)
    for name in agentfs.COMMUNAL_FILES:
        assert agentfs.read_file("communal", name)["exists"]


def test_a_second_claim_on_an_id_makes_one_folder_with_the_first_ones_text(cfg_factory):
    fx = load(FIXTURES / "duplicate-id.json")
    agentfs.migrate(cfg_factory(**fx["settings"]))
    assert folders() == {"main", "twin"}
    assert agentfs.read_file("twin", "instructions.md")["text"] == "First."


def test_a_switched_off_agent_gets_its_folder_and_its_instructions(cfg_factory):
    fx = load(FIXTURES / "disabled-agent.json")
    cfg = cfg_factory(**fx["settings"])
    assert "kestrel-x7q" not in {a["id"] for a in cfg.agents()}
    agentfs.migrate(cfg)
    assert agentfs.read_file("kestrel-x7q", "instructions.md")["text"] == "Only on Fridays."


def test_all_agents_is_agents_plus_the_switched_off_ones(cfg_factory):
    fx = load(FIXTURES / "disabled-agent.json")
    cfg = cfg_factory(**fx["settings"])
    every = cfg.all_agents()
    assert [a["id"] for a in every] == ["nova", "kestrel-x7q"]
    assert [a["enabled"] for a in every] == [True, False]
    live = {k: v for k, v in every[0].items() if k != "enabled"}
    assert live == cfg.agents()[0]
    assert every[1]["instructions"] == "Only on Fridays."


def test_an_agent_whose_id_is_communal_is_reported_and_gets_no_folder(cfg_factory):
    cfg = cfg_factory(voiceAgents=[{"id": "communal", "name": "nova", "instructions": "Hi."}])
    report = agentfs.migrate(cfg)
    assert folders() == {"main"}
    assert [s["id"] for s in report["skipped"]] == ["communal"]
    assert "communal" in agentfs.migration_lines(report)[-1]
    # Skipped is not a failure: the rest is done and recorded.
    assert report["recorded"]


def test_entries_the_settings_drop_are_counted_in_the_report(cfg_factory):
    cfg = cfg_factory(voiceAgents=[{"name": "nova"}, {"name": "Not A Name!"},
                                   {"name": "nova"}, "junk"])
    report = agentfs.migrate(cfg)
    assert folders() == {"main", "nova"}
    assert any("2 entries" in s["reason"] for s in report["skipped"])


# --- A10-2: idempotent, resumable, never overwrites, never writes shell.json --

def test_a_second_run_changes_nothing(cfg_factory):
    cfg = cfg_factory(**load(FIXTURES / "three-agents.json")["settings"])
    agentfs.migrate(cfg)
    before = tree(paths.DATA_DIR)
    again = agentfs.migrate(cfg)
    after = tree(paths.DATA_DIR)
    # Only the state file's time may move; every folder file and version is
    # byte-for-byte what it was.
    before.pop("agents/.state.json"), after.pop("agents/.state.json")
    assert after == before
    assert all(f["made"] == [] for f in again["folders"]) and again["communal"] == []
    assert agentfs.migration_lines(again, changes_only=True) == []


def test_an_existing_file_is_never_overwritten(cfg_factory):
    fx = load(FIXTURES / "three-agents.json")
    agentfs.write("nova", "instructions.md", "Mine, written by hand.")
    os.makedirs(paths.AGENTS_DIR / "kestrel-x7q")
    (paths.AGENTS_DIR / "kestrel-x7q" / "role.md").write_text("A role I wrote.")
    report = agentfs.migrate(cfg_factory(**fx["settings"]))
    assert agentfs.read_file("nova", "instructions.md")["text"] == "Mine, written by hand."
    assert (paths.AGENTS_DIR / "kestrel-x7q" / "role.md").read_text() == "A role I wrote."
    nova = next(f for f in report["folders"] if f["id"] == "nova")
    assert nova["instructions"] == "kept the existing file"
    assert "instructions.md" not in nova["made"]
    assert set(nova["made"]) == {"role.md", "personality.md"}


def test_shell_json_is_never_written(sandbox, tmp_path):
    """Through the CLI, as the daemon's start and `agents migrate` both read
    the real file: its bytes and its mtime are what they were."""
    shell = tmp_path / "config" / "omarchy" / "shell.json"
    shell.parent.mkdir(parents=True)
    fx = load(FIXTURES / "three-agents.json")
    shell.write_text(json.dumps({"bar": {"layout": {"right": [
        {"id": "duaneoca.agentvoice", **fx["settings"]}]}}}))
    before = (hashlib.sha256(shell.read_bytes()).hexdigest(), shell.stat().st_mtime_ns)
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "config"),
           "XDG_DATA_HOME": str(tmp_path / "xdgdata")}
    for _ in range(2):
        r = subprocess.run([sys.executable, str(ROOT / "daemon" / "agentfs.py"), "migrate"],
                           env=env, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr
    after = (hashlib.sha256(shell.read_bytes()).hexdigest(), shell.stat().st_mtime_ns)
    assert after == before
    made = tmp_path / "xdgdata" / "agentvoice" / "agents"
    assert {p.name for p in made.iterdir() if not p.name.startswith(".")} == {
        "main", "nova", "kestrel-x7q"}
    assert (made / "nova" / "instructions.md").read_text().startswith("Keep answers")


_KILLED = """
import json, os, signal, sys
sys.path.insert(0, {daemon!r})
import paths
from pathlib import Path
d = Path({data!r})
paths.DATA_DIR, paths.AGENTS_DIR, paths.COMMUNAL_DIR = d, d / "agents", d / "communal"
import agentfs, runtime
cfg = runtime.Config.__new__(runtime.Config)
cfg._values = dict(runtime.DEFAULTS); cfg._values.update(json.loads(sys.argv[1]))
cfg._stamps = (); cfg.source = "test"
real = agentfs._write_locked
n = [0]
def dying(target, *a, **k):
    # Killed outright -- no cleanup, no finally -- as the agent folder after
    # main is half made.
    if target not in ("communal", "main"):
        n[0] += 1
        if n[0] == 2:
            os.kill(os.getpid(), signal.SIGKILL)
    return real(target, *a, **k)
agentfs._write_locked = dying
agentfs.migrate(cfg)
"""


def test_a_kill_part_way_is_finished_on_the_next_run(data, cfg_factory):
    fx = load(FIXTURES / "three-agents.json")
    script = _KILLED.format(daemon=str(ROOT / "daemon"), data=str(data))
    r = subprocess.run([sys.executable, "-c", script, json.dumps(fx["settings"])],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == -signal.SIGKILL, r.stderr
    # Cut short: the state was not recorded, and one folder is half made.
    assert agentfs.migration_state() == {}
    assert sorted(os.listdir(paths.AGENTS_DIR / "nova")) != sorted(
        [*agentfs.AGENT_FILES, ".history"])
    report = agentfs.migrate(cfg_factory(**fx["settings"]))
    assert report["recorded"] and report["problems"] == []
    assert agentfs.migration_state()["migrated"] == agentfs.MIGRATION_VERSION
    assert folders() == {"main", "nova", "kestrel-x7q"}
    assert agentfs.read_file("nova", "instructions.md")["chars"] == 54
    for folder in folders():
        for name in agentfs.AGENT_FILES:
            assert agentfs.read_file(folder, name)["exists"], (folder, name)
    # No temporary file was left where an agent's files are.
    assert not [p for p in paths.DATA_DIR.rglob("*.tmp")]


def test_a_folder_that_cannot_be_made_is_reported_and_the_rest_go_on(cfg_factory, tmp_path):
    fx = load(FIXTURES / "three-agents.json")
    paths.AGENTS_DIR.mkdir(parents=True)
    (tmp_path / "elsewhere").mkdir()
    os.symlink(tmp_path / "elsewhere", paths.AGENTS_DIR / "nova")
    report = agentfs.migrate(cfg_factory(**fx["settings"]))
    assert any(p.startswith("nova:") for p in report["problems"])
    assert not report["recorded"] and agentfs.migration_state() == {}
    assert list((tmp_path / "elsewhere").iterdir()) == []
    assert agentfs.read_file("kestrel-x7q", "role.md")["exists"]


def test_a_dry_run_changes_nothing_and_says_what_it_would_do(data, cfg_factory):
    fx = load(FIXTURES / "three-agents.json")
    report = agentfs.migrate(cfg_factory(**fx["settings"]), dry_run=True)
    assert not data.exists()
    assert not report["recorded"]
    lines = agentfs.migration_lines(report)
    assert any(line.startswith("nova (Nova): would make") for line in lines)
    assert any("copied 54 characters" in line for line in lines)


def test_the_report_never_holds_instruction_text(cfg_factory):
    cfg = cfg_factory(agentInstructions="Zanzibar is the secret word.",
                      voiceAgents=[{"name": "nova", "instructions": "Quokka facts only."}])
    report = agentfs.migrate(cfg)
    blob = json.dumps(report) + "\n".join(agentfs.migration_lines(report))
    assert "Zanzibar" not in blob and "Quokka" not in blob


def test_settings_that_could_not_be_read_make_no_agent_folder(cfg_factory):
    """shell.json mid-write or broken at start: Config falls back to the
    defaults, whose instructions are empty. Copying those would make an empty
    instructions.md that hides the real setting for good."""
    cfg = cfg_factory(**load(FIXTURES / "main-with-instructions.json")["settings"])
    report = agentfs.migrate(cfg, settings_read=False)
    assert not paths.AGENTS_DIR.exists() or folders() == set()
    assert report["problems"] and not report["recorded"]
    assert report["communal"]                      # the shared folder is safe to make
    assert agentfs.instructions_for("", cfg["agentInstructions"]).startswith("Call me captain")
    # Read properly on the next start: migrated as usual.
    assert agentfs.migrate(cfg)["recorded"]
    assert agentfs.instructions_for("", "").startswith("Call me captain")


@pytest.mark.parametrize("source,want", [
    ("shell.json[duaneoca.agentvoice]", True), ("defaults", False),
    ("agentvoice.toml", False), ("test", False), ("", False)])
def test_only_settings_read_from_shell_json_count_as_read(cfg_factory, source, want):
    cfg = cfg_factory()
    cfg.source = source
    assert agentfs.settings_were_read(cfg) is want


def test_the_cli_migration_checks_the_settings_were_read(tmp_path):
    """No shell.json at all: the CLI makes the communal folder only, says why
    and exits 1, and records nothing."""
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "c"),
           "XDG_DATA_HOME": str(tmp_path / "d")}
    r = subprocess.run([sys.executable, str(ROOT / "daemon" / "agentfs.py"), "migrate"],
                       env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 1 and "could not be read" in r.stdout
    data = tmp_path / "d" / "agentvoice"
    assert (data / "communal" / "rules.md").is_file()
    assert not (data / "agents" / "main").exists()


# --- A10-3 and the fallback: which source wins --------------------------------

def test_the_old_setting_is_read_only_while_the_file_is_missing():
    assert agentfs.instructions_for("", "Be brief.") == "Be brief."
    assert agentfs.instructions_for("nova", " Be kind.\t") == "Be kind."
    agentfs.write("main", "instructions.md", "From the file.")
    assert agentfs.instructions_for("", "Be brief.") == "From the file."


def test_an_emptied_file_stays_empty():
    """A10-3: cleared on purpose stays cleared; the setting does not return."""
    agentfs.write("main", "instructions.md", "Something.")
    agentfs.write("main", "instructions.md", "")
    assert agentfs.instructions_for("", "The old setting.") == ""
    # And one that holds only the starter comment reads as empty too.
    agentfs.write("nova", "instructions.md", "<!-- starter -->\n")
    assert agentfs.instructions_for("nova", "The old setting.") == ""


def test_an_unreadable_file_does_not_fall_back_either():
    agentfs.write("main", "instructions.md", "Good text.")
    agentfs.instructions_for("", "")
    (paths.AGENTS_DIR / "main" / "instructions.md").write_bytes(b"\xff\xfe bad")
    assert agentfs.instructions_for("", "The old setting.") == "Good text."


def test_an_agent_with_no_folder_of_its_own_is_told_the_setting():
    assert agentfs.instructions_for("communal", "Kept.") == "Kept."


# --- the daemon tells its agents the file -------------------------------------

class Agent:
    instructions = ""

    def __init__(self):
        self.cancelled = 0

    def posture(self, level): return level
    def cancel(self): self.cancelled += 1
    def prepare(self, *a, **k): pass


def test_the_main_agent_is_told_its_file_and_a_hand_edit_on_the_next_poll(daemon):
    daemon.agent = None
    daemon.cfg._values["agentInstructions"] = "The old setting."
    assert daemon.instructions_for("", daemon.cfg["agentInstructions"]) == "The old setting."
    agentfs.write("main", "instructions.md", "Say yes.")
    daemon.reconcile_agent_files()
    assert daemon.instructions_for("", daemon.cfg["agentInstructions"]) == "Say yes."
    # The same size: no size in the summary moves, the words still do.
    (paths.AGENTS_DIR / "main" / "instructions.md").write_text("Say no!.")
    daemon.reconcile_agent_files()
    assert daemon.instructions_for("", "x") == "Say no!."
    daemon.agent = Agent()
    daemon.apply_instructions(daemon.instructions_for("", "x"))
    assert daemon.agent.instructions == "Say no!."


def test_reconcile_agent_hands_the_main_agent_its_file(daemon, monkeypatch):
    import wake_listen
    agentfs.write("main", "instructions.md", "From the folder.")
    daemon.cfg._values["agentInstructions"] = "From the setting."
    daemon.agent = None
    monkeypatch.setattr(wake_listen, "load_adapter", lambda **kw: type(
        "A", (Agent,), {"instructions": kw["instructions"], "name": kw.get("name"),
                        "cwd": kw.get("cwd"), "ask_permission": kw.get("ask_permission")})())
    monkeypatch.setattr(daemon, "main_program", lambda: "claude")
    monkeypatch.setattr(daemon, "publish_agent", lambda: None)
    daemon.reconcile_agent()
    assert daemon.agent.instructions == "From the folder."


def test_refresh_reads_the_folders_before_it_builds_any_agent(daemon, monkeypatch):
    order = []
    for name in ("reconcile_agent_files", "reconcile_agent", "reconcile_crew"):
        monkeypatch.setattr(daemon, name, lambda n=name: order.append(n))
    monkeypatch.setattr(daemon.cfg, "reload", lambda: False, raising=False)
    for name in ("reconcile_extras", "reconcile_voice", "reconcile_output"):
        monkeypatch.setattr(daemon, name, lambda: None)
    monkeypatch.setattr(daemon, "pipe", type("P", (), {"reconcile_vocab": lambda s: None})())
    daemon.refresh()
    assert order == ["reconcile_agent_files", "reconcile_agent", "reconcile_crew"]


def test_an_extra_agent_is_told_its_file_and_keeps_its_conversation(daemon, monkeypatch):
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
    daemon.agent = None
    daemon.cfg._values["speakReplies"] = False
    daemon.cfg._values["voiceAgents"] = [{"id": "fri", "name": "friday",
                                          "instructions": "The old setting."}]
    daemon.reconcile_crew()
    p = daemon.crew["fri"]
    assert p.agent.instructions == "The old setting."
    p.session_id = "keep"
    agentfs.write("fri", "instructions.md", "From the folder.")
    daemon.reconcile_agent_files()
    daemon.reconcile_crew()
    assert len(built) == 1 and p.agent.instructions == "From the folder."
    assert p.session_id == "keep" and p.agent.cancelled == 1
    # Emptied on purpose: told nothing, not the old setting.
    agentfs.write("fri", "instructions.md", "")
    daemon.reconcile_agent_files()
    daemon.reconcile_crew()
    assert p.agent.instructions == ""


def test_a_folder_missing_its_instructions_file_falls_back_in_the_daemon_too(daemon):
    """The daemon's cached copy agrees with agentfs.instructions_for: a folder
    whose instructions.md is missing (deleted by hand, not yet migrated) is
    told the old setting, not nothing."""
    daemon.agent = None
    agentfs.write("main", "role.md", "A role.")
    daemon.reconcile_agent_files()
    assert "main" in daemon._agent_files
    assert daemon.instructions_for("", "The old setting.") == "The old setting."
    assert agentfs.instructions_for("", "The old setting.") == "The old setting."


def test_a_failed_read_keeps_the_instructions_it_had(daemon, monkeypatch):
    daemon.agent = None
    agentfs.write("main", "instructions.md", "Kept.")
    daemon.reconcile_agent_files()
    (paths.AGENTS_DIR / "main" / "instructions.md").write_text("New.")
    monkeypatch.setattr(agentfs, "snapshot", lambda: (_ for _ in ()).throw(OSError("x")))
    daemon.reconcile_agent_files()
    assert daemon.instructions_for("", "The old setting.") == "Kept."


@pytest.mark.parametrize("enabled", [False, True])
def test_a_typed_turn_catches_up_first(daemon, monkeypatch, enabled):
    """Found live, twice: the idle poll sits below the listening gate, so
    with the microphone muted nothing re-read the folders and a typed turn
    to Sora was told her instructions from before an edit; and with it
    listening, a turn typed straight after the save beat the 2s poll."""
    calls = []
    monkeypatch.setattr(daemon, "refresh", lambda: calls.append(1))
    monkeypatch.setattr(daemon, "pipe", object())
    monkeypatch.setattr(daemon, "answer", lambda text, last: None)
    monkeypatch.setattr(daemon, "voice_command", lambda p, text: False)
    daemon.enabled = enabled
    daemon.handle_typed("", "hello", False)
    assert len(calls) == 1


def test_the_daemon_migrates_before_it_builds_the_main_agent():
    src = (ROOT / "daemon" / "wake_listen.py").read_text()
    body = src[src.index("def main("):]
    assert body.index("agentfs.migrate(cfg, settings_read=agentfs.settings_were_read(cfg))") \
        < body.index("agent = load_adapter(")
    assert 'agentfs.instructions_for(\n                                 "", cfg["agentInstructions"])' in body


# --- the CLI the page uses -----------------------------------------------------

def cli(*args, stdin=""):
    return subprocess.run([sys.executable, str(ROOT / "daemon" / "agentfs.py"), *args],
                          input=stdin, capture_output=True, text=True, timeout=60,
                          env={**os.environ, "XDG_DATA_HOME": str(paths.DATA_DIR.parent / "xdg")})


def test_write_line_takes_one_json_line_and_a_base():
    r = cli("write", "main", "instructions.md", "--line", "--base", "missing",
            stdin=json.dumps("Two lines,\nhere.") + "\n" + "ignored after the line")
    assert r.returncode == 0, r.stderr
    stamp = r.stdout.strip()
    got = json.loads(cli("show", "main", "--json").stdout)["files"]["instructions.md"]
    assert got["text"] == "Two lines,\nhere." and got["stamp"] == stamp
    stale = cli("write", "main", "instructions.md", "--line", "--base", "missing",
                stdin=json.dumps("Over it.") + "\n")
    assert stale.returncode == 3 and f"current stamp {stamp}" in stale.stderr
    bad = cli("write", "main", "instructions.md", "--line", stdin="not json\n")
    assert bad.returncode == 1 and "JSON" in bad.stderr
    notstr = cli("write", "main", "instructions.md", "--line", stdin="[1]\n")
    assert notstr.returncode == 1


def test_trash_line_takes_the_entry_as_one_line_and_restore_gives_it_back():
    entry = {"id": "nova", "name": "nova", "level": "ask"}
    assert cli("create", "nova").returncode == 0
    r = cli("trash", "nova", "--line", stdin=json.dumps(entry) + "\n")
    assert r.returncode == 0, r.stderr
    back = cli("restore", r.stdout.strip())
    assert back.returncode == 0 and json.loads(back.stdout) == entry


def test_migrate_dry_run_on_the_cli_changes_nothing(tmp_path):
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "c"),
           "XDG_DATA_HOME": str(tmp_path / "d")}
    r = subprocess.run([sys.executable, str(ROOT / "daemon" / "agentfs.py"),
                        "migrate", "--dry-run"], env=env, capture_output=True,
                       text=True, timeout=60)
    # With no shell.json it would make the communal folder only, and says so.
    assert r.returncode == 1 and "communal: would make" in r.stdout
    assert "could not be read" in r.stdout
    assert not (tmp_path / "d").exists()


# --- the page and the retired setting -----------------------------------------

PAGE = (ROOT / "pages" / "AgentsPage.qml").read_text()


def test_the_retired_setting_left_the_manifest_but_not_the_daemons_defaults():
    from runtime import DEFAULTS
    manifest = load(ROOT / "manifest.json")["barWidget"]
    assert "agentInstructions" not in {k["key"] for k in manifest["schema"]}
    assert "agentInstructions" not in manifest["defaults"]
    assert "agentInstructions" in DEFAULTS


def test_no_page_writes_instructions_into_the_settings_any_more():
    for page in (ROOT / "pages").glob("*.qml"):
        text = page.read_text()
        assert 'put("agentInstructions"' not in text, page.name
        assert '"instructions", ' not in text, page.name
    assert "instructions:" not in PAGE[PAGE.index("function addAgent("):
                                      PAGE.index("function folderOp(")]


def test_the_page_edits_the_folder_files_through_the_cli():
    box = (ROOT / "ui" / "FolderInstructionsBox.qml").read_text()
    assert '["agentvoice", "agents", "write", target, "instructions.md", "--line"]' in box
    assert '"--base", fib.stamp' in box
    # The text goes over stdin, as JSON, never into the command.
    assert "JSON.stringify(t)" in box and "writer.pending" in box
    assert 'target: "main"' in PAGE and "target: page.s.agentId(card.modelData)" in PAGE
    assert PAGE.count("FolderInstructionsBox {") == 2
    assert "InstructionsBox {" not in PAGE.replace("FolderInstructionsBox {", "")


def test_adding_and_removing_an_agent_go_through_its_folder():
    add = PAGE[PAGE.index("function addAgent("):PAGE.index("// --- agent folders")]
    assert 'folderOp(["create", id]' in add
    remove = PAGE[PAGE.index("function removeAgent("):PAGE.index("function undoRemove(")]
    assert '["trash", entry.id, "--line"]' in remove
    assert "JSON.stringify(entry)" in remove
    # The agent leaves the list only once its folder is in the trash.
    assert "saveAgents" not in remove
    undo = PAGE[PAGE.index("function undoRemove("):]
    assert '["restore", page.trashed.name]' in undo[:600]
