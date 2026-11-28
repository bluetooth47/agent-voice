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
    # ... and it is a FileEditor, once. Since M15 a FileHistory beside it may
    # name the file too: it lists versions and restores one through `agents
    # revert`, never `agents write` (test_only_the_file_editor_runs_agents_write).
    at = [m.start() for m in re.finditer(re.escape(f'file: "{name}"'), page)]
    kinds = [re.findall(r"\b([A-Z]\w*) \{", page[:i])[-1] for i in at]
    assert kinds.count("FileEditor") == 1, (name, kinds)
    assert set(kinds) <= {"FileEditor", "FileHistory"}, (name, kinds)


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
    # Once: since M5 the main agent and the extra ones are one block.
    assert page.count("Edit in Agent details →") == 1
    assert page.count("pg.folderSummary(") == 1


# --- what the pages may write ---------------------------------------------------

def test_agent_details_writes_only_its_launch_settings():
    """Agent details wrote no setting until M17, whose Advanced tab is the
    home of how an agent is launched: the main agent's three twins, put in
    one function (`putLaunch`), and nothing else put anywhere on the page.
    The tool and skill switches go through overlay functions (M10, M11)."""
    from qml_scan import scan
    src = scan(ROOT / "pages" / "AgentDetailsPage.qml").nocomment
    at = src.index("function putLaunch(")
    body = src[at:src.index("\n  }", at)]
    rest = src[:at] + src[at + len(body):]
    assert not re.search(r"\b(put|putMap)\(", rest)
    assert set(re.findall(r'\bput\("(\w+)"', body)) == {"mainResume", "mainIdleTimeoutS",
                                                        "mainExtraArgs"}


def test_communal_writes_only_the_tools_for_every_agent():
    """Communal wrote no setting until M5 moved the three switches for every
    agent there (bug E), M10 added the found tools for every agent
    (`sharedTools`, through one function) and M14 the Agent Voice skill's
    switch, M15 who takes Communal at all (`communalOff`), and M31 which
    skills are communal (`communalSkills`, a grouping). Those, and nothing
    else: the rules, skills and notes are files, written through the CLI."""
    page = text("pages/CommunalPage.qml")
    keys = re.findall(r'\b(?:put|putMap)\("(\w+)"', page)
    assert sorted(keys) == ["agentvoiceSkill", "browserTools", "communalOff", "communalSkills",
                            "desktopTools", "omarchySkill", "sharedTools"]
    assert len(re.findall(r"\b(?:put|putMap)\(", page)) == 7


def test_the_folder_operations_write_only_the_agent_list():
    keys = set(re.findall(r'\bput\("(\w+)"', text("AgentFolders.qml")))
    assert keys == {"voiceAgents"}


def test_text_from_files_is_never_rich():
    for rel in ["ui/PromptPreview.qml", "ui/FileEditor.qml", "ui/FileHistory.qml",
                "ui/CommunalImport.qml"]:
        body = text(rel)
        assert body.count("Text {") == body.count("textFormat: Text.PlainText"), rel


# --- the sidebar ------------------------------------------------------------------

def test_every_page_has_a_key_with_the_new_ones_after_agents():
    """Ctrl+1..9 for the first nine pages in sidebar order, Ctrl+0 for the
    tenth (phase M8: the Crew map made ten), Ctrl+PgUp/PgDn to step. Since
    phase M18 there are eleven: Chats after the Crew map, and About, the
    eleventh, reached by a click and Ctrl+PgDn."""
    s = text("Settings.qml")
    ids = re.findall(r'\{ id: "(\w+)",\s+label:', s[s.index("readonly property var pages:"):])[:11]
    assert ids == ["overview", "agents", "agentdetails", "communal", "crew", "chats", "listening",
                   "conversation", "voice", "other", "about"]
    assert "ctrl+1–9, 0 or pgup/pgdn to switch pages" in s
    assert "n >= 0 && n < root.pages.length" in s
    keys = s[s.index("function pageForKey("):s.index("function goTo(")]
    for want in ("key - Qt.Key_1", "key === Qt.Key_0) return 9", "Qt.Key_PageUp", "Qt.Key_PageDown"):
        assert want in keys, want
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


# --- Codex's review of Phase 12 -------------------------------------------------

BOX = text("ui/FileEditor.qml")
FOLDERS = text("AgentFolders.qml")
DETAILS = text("pages/AgentDetailsPage.qml")


def test_an_edit_made_during_a_save_is_saved_next_not_dropped():
    save = BOX[BOX.index("function save("):BOX.index("function keepMine(")]
    queue = save[:save.index("fe.saveGen++")]
    assert "if (writer.running) {" in queue and "fe.hasQueued = true" in queue
    done = BOX[BOX.index("id: writer"):]
    assert "if (fe.hasQueued) {" in done and "fe.save(next)" in done


def test_an_over_long_text_is_refused_whole_never_cut():
    save = BOX[BOX.index("function save("):BOX.index("function keepMine(")]
    # Counted as the agent would be told it, since M6 (the meters).
    assert save.index("fe.sentChars(t) > fe.limit") < save.index("writer.running = true")
    assert "cutOff: false" in BOX
    ibox = text("ui/InstructionsBox.qml")
    commit = ibox[ibox.index("function commit()"):]
    # Compared before anything is cut, and counted as the daemon counts.
    assert commit.index("if (t === box.value.trim()) return") < commit.index("box.cutOff")
    assert "Array.from(String(t)).length" in ibox


def test_the_editor_shows_the_whole_file_not_the_cut_prompt_text():
    assert "fe.saved = String(f.full !== undefined ? f.full : (f.text || \"\"))" in BOX


def test_typed_text_is_handed_on_when_the_editor_goes_or_moves():
    assert "Component.onDestruction: handOff(fe.boundTarget)" in BOX
    on_target = BOX[BOX.index("onTargetChanged:"):]
    assert on_target.index("handOff(boundTarget)") < on_target.index("boundTarget = target")
    assert "box.reset(\"\")" in on_target[:800]
    keep = FOLDERS[FOLDERS.index("function keep("):]
    assert '"--base", base]' in keep[:400] and "JSON.stringify(text)" in keep[:400]


def test_keep_mine_saves_what_is_in_the_box_now():
    keep = BOX[BOX.index("function keepMine()"):BOX.index("function showTheirs()")]
    assert "save(box.text.trim())" in keep


def test_a_save_before_the_first_read_waits_for_it():
    save = BOX[BOX.index("function save("):BOX.index("function keepMine(")]
    assert "fe.retryAfterRead = true" in save
    reader = BOX[BOX.index("id: reader"):BOX.index("id: writer")]
    assert "if (fe.retryAfterRead) {" in reader and "fe.save(t)" in reader


def test_the_queue_waits_for_the_agent_list_to_be_saved():
    done = FOLDERS[FOLDERS.index("id: finished"):FOLDERS.index("function release()")]
    assert done.index("if (af.awaitingSave)") < done.index("af.busy = false")
    for branch in ('af.rollback = { verb: "trash"', 'af.rollback = { verb: "restore"'):
        tail = FOLDERS[FOLDERS.index(branch):]
        assert tail.index("af.awaitingSave = true") < tail.index("saveAgents(")


def test_a_double_remove_trashes_once():
    remove = FOLDERS[FOLDERS.index("function remove("):FOLDERS.index("function undo(")]
    assert remove.index('if (pending("trash", entry.id)) return') < remove.index('op(["trash"')


def test_a_restore_never_takes_a_wake_phrase_another_agent_has():
    restore = FOLDERS[FOLDERS.index("function restore("):FOLDERS.index("function trashOrphan(")]
    guard = 'if (!orphan && phrase !== "") {'
    assert guard in restore and "now wakes" in restore
    assert restore.index(guard) < restore.index("now wakes") < restore.index('op(["restore"')


def test_a_restored_entry_takes_the_id_its_folder_came_back_under():
    handled = FOLDERS[FOLDERS.index('what.verb === "restore"'):]
    assert handled.index("entry.id = String(what.name)") < handled.index("saveAgents(back)")


def test_the_picker_and_the_tab_stay_bound():
    # Since M6 the picker is AgentTabs: its `current` is bound to the page's
    # agent and a pick only asks the overlay, so it can never stay on a
    # removed agent the way the Dropdown's own assignment once did.
    import re
    assert re.search(r'AgentTabs \{\s*id: agentPicker[^}]*current: page\.target', DETAILS)
    assert not re.search(r"\bcurrent\s*=", DETAILS[DETAILS.index("AgentTabs {"):][:900])
    assert "readonly property string tab: s.detailsTab" in DETAILS
    assert "function pickTab(id) { s.detailsTab = id }" in DETAILS


def test_an_agent_with_the_reserved_id_reaches_no_folder():
    assert 'readonly property string folderTarget: reserved ? "" : target' in DETAILS
    assert DETAILS.count("target: page.folderTarget") == 3


def test_hints_and_labels_are_plain_text():
    row = text("ui/SettingRow.qml")
    assert row.count("textFormat: Text.PlainText") >= 3


def test_read_file_gives_the_whole_text_beside_what_is_told():
    agentfs.write("main", "role.md", "x" * 320)
    got = agentfs.read_file("main", "role.md")
    assert len(got["text"]) == 300 and len(got["full"]) == 320 and got["problem"]


def test_the_published_sizes_carry_each_files_stamp():
    agentfs.write("main", "role.md", "One.")
    first = agentfs.summary()["main"]["files"]["role.md"]["stamp"]
    agentfs.write("main", "role.md", "Two.")       # same length
    assert agentfs.summary()["main"]["files"]["role.md"]["stamp"] != first


@pytest.mark.parametrize("entry,folder_only", [
    ({"id": "a", "name": "alpha"}, False),
    ({"id": "a", "orphan": True}, True),
    ({}, True),
    ({"id": "a", "name": "  "}, True),
    ({"id": "a", "name": 3}, True),
])
def test_one_rule_says_what_is_a_folder_only_trash_entry(entry, folder_only):
    assert agentfs.is_folder_only(entry) is folder_only


def test_export_copies_whole_files_beyond_the_read_cap(tmp_path):
    agentfs.create("big")
    (paths.AGENTS_DIR / "big" / "personality.md").write_bytes(b"a" * (agentfs.READ_CAP + 1))
    out = Path(agentfs.export("big", str(tmp_path)))
    assert (out / "personality.md").stat().st_size == agentfs.READ_CAP + 1


def test_a_failed_export_leaves_nothing_behind(tmp_path):
    agentfs.create("bad")
    target = paths.AGENTS_DIR / "bad" / "instructions.md"
    target.unlink()
    target.symlink_to("/etc/hostname")
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(agentfs.AgentFsError):
        agentfs.export("bad", str(out))
    assert list(out.iterdir()) == []


def test_a_switched_off_endpoint_is_previewed_as_an_endpoint(cfg_factory):
    cfg = cfg_factory(phrase="theo", voiceAgents=[
        {"id": "ep", "name": "echo", "agent": "endpoint", "enabled": False,
         "endpointUrl": "http://127.0.0.1:9/v1", "endpointModel": "m",
         "instructions": "Old words."}])
    got = agentfs.preview("ep", cfg)
    labels = [x["label"] for x in got]
    assert "Omarchy commands and keybindings" not in labels
    assert any(x["text"] == "Old words." for x in got)
