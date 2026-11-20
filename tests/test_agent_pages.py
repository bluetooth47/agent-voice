"""The Agent details and Communal pages (merged plan, Phase 12).

The QML is not run here (CLAUDE.md: its behaviour is exercised by hand and
by bench/preview's `details` target); what is held is what can be read off
it, and the CLI it stands on:

- A12-2: one editor per file. Each folder file is edited by exactly one
  FileEditor on one page, and FileEditor is the only QML that runs
  `agents write`.
- The new pages write no setting; the shared AgentFolders writes only the
  agent list, as the second half of a folder move.
- Nine pages fit Ctrl+1..9, with Agent details and Communal after Agents.
- `agents export` copies a folder's files and nothing else, privately; the
  trash list says which entries were folders with no agent.
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import agentfs
import paths

ROOT = Path(__file__).resolve().parent.parent
QML = [p for p in [*ROOT.glob("*.qml"), *ROOT.glob("ui/*.qml"), *ROOT.glob("pages/*.qml")]]


def text(rel: str) -> str:
    return (ROOT / rel).read_text()


@pytest.fixture(autouse=True)
def data(tmp_path, monkeypatch):
    d = tmp_path / "data"
    monkeypatch.setattr(paths, "DATA_DIR", d)
    monkeypatch.setattr(paths, "AGENTS_DIR", d / "agents")
    monkeypatch.setattr(paths, "COMMUNAL_DIR", d / "communal")
    agentfs._LAST_GOOD.clear()
    return d


# --- A12-2: one editor per file ----------------------------------------------

@pytest.mark.parametrize("name", [*agentfs.AGENT_FILES, *agentfs.COMMUNAL_FILES])
def test_each_folder_file_has_exactly_one_editor(name):
    where = [p.relative_to(ROOT).as_posix() for p in QML
             if re.search(r'\bfile:\s*"' + re.escape(name) + '"', p.read_text())]
    assert len(where) == 1, (name, where)
    page = (ROOT / where[0]).read_text()
    # ... and it is a FileEditor, once.
    assert page.count(f'file: "{name}"') == 1
    opened = re.findall(r"\b([A-Z]\w*) \{", page[:page.index(f'file: "{name}"')])
    assert opened[-1] == "FileEditor", (name, opened[-1])


def test_a_change_noticed_mid_read_is_read_again():
    """Found by the details preview: a new agent's editor read its folder a
    moment before `agents create` made it, and the reload asked for when it
    appeared was dropped because the first read was still running."""
    box = text("ui/FileEditor.qml")
    reload = box[box.index("function reload()"):box.index("function save(")]
    assert "if (reader.running) { readAgain = true; return }" in reload
    reader = box[box.index("id: reader"):]
    assert "onRunningChanged: if (!running && fe.readAgain)" in reader[:400]


def test_only_the_file_editor_runs_agents_write():
    writers = [p.relative_to(ROOT).as_posix() for p in QML
               if re.search(r'"agents",\s*"write"', p.read_text())]
    assert writers == ["ui/FileEditor.qml"]


def test_the_agents_card_shows_a_summary_and_links_to_the_editor():
    page = text("pages/AgentsPage.qml")
    assert "FileEditor {" not in page and "InstructionsBox {" not in page
    assert page.count("Edit in Agent details →") == 2
    assert page.count("page.folderSummary(") == 2


# --- what the pages may write ---------------------------------------------------

@pytest.mark.parametrize("rel", ["pages/AgentDetailsPage.qml", "pages/CommunalPage.qml"])
def test_the_new_pages_write_no_setting(rel):
    assert not re.search(r"\b(put|putMap)\(", text(rel)), rel


def test_the_folder_operations_write_only_the_agent_list():
    keys = set(re.findall(r'\bput\("(\w+)"', text("AgentFolders.qml")))
    assert keys == {"voiceAgents"}


def test_text_from_files_is_never_rich():
    for rel in ["ui/PromptPreview.qml", "ui/FileEditor.qml"]:
        body = text(rel)
        assert body.count("Text {") == body.count("textFormat: Text.PlainText"), rel


# --- the sidebar ------------------------------------------------------------------

def test_nine_pages_fit_the_keys_with_the_new_two_after_agents():
    s = text("Settings.qml")
    ids = re.findall(r'\{ id: "(\w+)",\s+label:', s[s.index("readonly property var pages:"):])[:9]
    assert ids == ["overview", "agents", "agentdetails", "communal", "listening",
                   "conversation", "voice", "display", "about"]
    assert "ctrl+1–9 to switch pages" in s
    assert "n >= 0 && n < root.pages.length" in s
    # A deep link picks the agent Agent details opens on.
    go = s[s.index("function goTo("):s.index("function showPage(")]
    assert 'if (page === "agentdetails")' in go and "detailsAgent = agent" in go


# --- export -----------------------------------------------------------------------

def test_export_copies_the_files_privately_and_leaves_the_history(tmp_path):
    agentfs.write("sora", "personality.md", "Dry.")
    agentfs.write("sora", "personality.md", "Drier.")
    (paths.AGENTS_DIR / "sora" / "skills" / "tea").mkdir(parents=True)
    (paths.AGENTS_DIR / "sora" / "skills" / "tea" / "SKILL.md").write_text("Brew.")
    out = Path(agentfs.export("sora", str(tmp_path)))
    assert out.parent == tmp_path and out.name.startswith("agentvoice-sora-")
    assert (out / "personality.md").read_text() == "Drier."
    assert (out / "skills" / "tea" / "SKILL.md").read_text() == "Brew."
    assert not (out / ".history").exists()
    assert stat.S_IMODE(out.stat().st_mode) == 0o700
    assert stat.S_IMODE((out / "personality.md").stat().st_mode) == 0o600


@pytest.mark.parametrize("bad", ["../x", "/etc", "Sora", ""])
def test_export_refuses_what_is_not_an_id(bad, tmp_path):
    with pytest.raises(agentfs.AgentFsError):
        agentfs.export(bad, str(tmp_path))


def test_export_refuses_a_missing_folder_or_destination(tmp_path):
    with pytest.raises(agentfs.AgentFsError):
        agentfs.export("nobody", str(tmp_path))
    agentfs.write("main", "role.md", "x")
    with pytest.raises(agentfs.AgentFsError):
        agentfs.export("main", str(tmp_path / "missing"))


def test_export_from_the_cli_prints_where(tmp_path):
    env = {**os.environ, "XDG_DATA_HOME": str(tmp_path / "xdg")}
    cli = [sys.executable, str(ROOT / "daemon" / "agentfs.py")]
    w = subprocess.run(cli + ["write", "communal", "rules.md"], input="Be kind.", env=env,
                       capture_output=True, text=True, timeout=60)
    assert w.returncode == 0, w.stderr
    (tmp_path / "out").mkdir()
    r = subprocess.run(cli + ["export", "communal", str(tmp_path / "out")], env=env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert (Path(r.stdout.strip()) / "rules.md").read_text() == "Be kind."


# --- the trash list -----------------------------------------------------------------

def test_the_trash_list_says_which_entries_were_folders_with_no_agent():
    agentfs.create("stray")
    agentfs.create("wren")
    agentfs.trash("stray", '{"id": "stray", "orphan": true}')
    agentfs.trash("wren", '{"id": "wren", "name": "wren"}')
    got = {t["id"]: t["orphan"] for t in agentfs.trash_list()}
    assert got == {"stray": True, "wren": False}
