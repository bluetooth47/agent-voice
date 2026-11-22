"""Phase M13: the Notes tabs move, copy and combine notes only through one
mover, which asks before widening and before Combine.

The daemon refuses a widening move without `--confirm` (test_notemoves.py).
This holds the other half: the panel adds `--confirm` only in
NoteMover.transferNote, called only from its ToolConfirm's onConfirmed;
Combine runs only from its own confirm; every way a note card moves (a drop
on a lane, its Move to… menu) ends in noteDropped, which refuses and says
why, or hands the move to the mover's request(); and the panel names no
setting (it is a ui/ building block).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from qml_scan import ROOT, overlay_qml, scan
from test_tool_controls import function_source
from test_transfer_ui import calls_of

MOVER = ROOT / "ui" / "NoteMover.qml"
PANEL = ROOT / "ui" / "NotesPanel.qml"
NODE = shutil.which("node")


def test_the_confirmed_move_and_combine_are_reached_only_from_their_confirms():
    for path in overlay_qml():
        for name in ("transferNote", "combineNotes"):
            got = calls_of(path, name)
            if path == MOVER:
                assert got == [("onConfirmed", "ToolConfirm")], (name, got)
            else:
                assert got == [], (path.name, name, got)


def test_note_commands_are_built_only_in_the_mover():
    for path in overlay_qml():
        src = scan(path).nocomment
        hits = (len(re.findall(r'"notes",\s*(?:p\.copy|copy === true)', src))
                + src.count('"notes", "undo"') + src.count('"notes", "combine"'))
        if path == MOVER:
            assert hits == 4, hits
        else:
            assert hits == 0, path.name
            assert '"notes", "move"' not in src and '"notes", "copy"' not in src, path.name


def test_every_way_a_note_card_moves_goes_through_note_dropped():
    s = scan(PANEL)
    handlers = {h for h, _ in calls_of(PANEL, "noteDropped")}
    assert handlers == {"onReceived", "onMoveRequested"}, handlers
    assert all(h == "function noteDropped" for h, _ in calls_of(PANEL, "request"))
    fn = function_source(PANEL, "noteDropped")
    assert "noteRefusal(p, to)" in fn and "moveNote = why" in fn
    # Every lane judges a hovering card by the same refusal, and takes notes
    # only (a skill card, on another tab, carries another key).
    assert len(re.findall(r"refuse: function\(p, copy, from\) \{ return np\.noteRefusal\(p, ",
                          s.nocomment)) == 2
    assert s.nocomment.count('dragKey: "agentvoice-note"') == 4


def test_combine_is_asked_through_the_mover_only():
    assert calls_of(PANEL, "askCombine") and \
        [h for h, _ in calls_of(PANEL, "askCombine")] == ["function askCombine", "onClicked"]
    fn = function_source(MOVER, "askCombine")
    assert "pendingCombine = {" in fn and "combiner" not in fn


@pytest.mark.parametrize("path", [MOVER, PANEL])
def test_note_text_is_plain(path):
    src = path.read_text()
    for m in re.finditer(r"\bText \{", src):
        body = src[m.start():m.start() + 700]
        assert "textFormat: Text.PlainText" in body, (path.name, body[:160])


def test_the_panel_names_no_setting_and_reads_quarantine_from_the_lanes():
    src = scan(PANEL).nocomment
    assert "s.setting(" not in src and "crewQuarantine" not in src
    assert '["agentvoice", "notes", "lanes", "--json"]' in src
    assert "quarantine_readable === false ? null" in src


def test_the_pages_open_another_lane_on_its_own_tab():
    for page in ("AgentDetailsPage.qml", "CommunalPage.qml"):
        src = (ROOT / "pages" / page).read_text()
        assert 'onOpenElsewhere: function(id)' in src and 'goTo("agentdetails", id, "notes")' in src


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.parametrize("quarantined, frm, to, tainted, asks", [
    ([], "theo", "communal", False, True), ([], "theo", "sora", False, False),
    (["theo"], "theo", "sora", False, True), (["hazel"], "theo", "sora", False, False),
    (None, "theo", "sora", False, True), ("x", "theo", "sora", False, True),
    ([], "communal", "sora", False, False), (None, "communal", "sora", False, False),
    ([], "theo", "sora", True, True), ([], "communal", "theo", True, True)])
def test_when_the_note_mover_asks(quarantined, frm, to, tainted, asks):
    script = "\n".join(function_source(MOVER, n) for n in
                       ("quarantineReadable", "isQuarantined", "widening")) + f"""
var quarantined = {json.dumps(quarantined)};
console.log(JSON.stringify(widening({json.dumps(frm)}, {json.dumps(to)}, {json.dumps(tainted)})));
"""
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) is asks


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.parametrize("p, to, why", [
    ({"kind": "skill", "name": "x"}, "sora", "Not a note."),
    ({"kind": "note", "name": "x", "from": "theo", "problem": "it is not UTF-8 text"}, "sora",
     "It cannot be moved: it is not UTF-8 text"),
    ({"kind": "note", "name": "garden", "from": "theo", "problem": ""}, "sora",
     "Sora already has a note called garden. Combine or rename one first."),
    ({"kind": "note", "name": "x", "from": "theo", "problem": ""}, "broken",
     "Broken's notes record cannot be read, so nothing is moved into it."),
    ({"kind": "note", "name": "x", "from": "broken", "problem": ""}, "sora",
     "Broken's notes record cannot be read, so nothing is moved out of it."),
    ({"kind": "note", "name": "x", "from": "theo", "problem": ""}, "sora", "")])
def test_what_a_lane_refuses(p, to, why):
    lanes = [{"id": "sora", "label": "Sora", "notes": [{"name": "garden"}], "locked_all": False},
             {"id": "broken", "label": "Broken", "notes": [], "locked_all": True}]
    script = "\n".join(function_source(PANEL, n) for n in
                       ("laneById", "laneNotes", "laneLocked", "laneLabel", "noteRefusal")) + f"""
var allLanes = {json.dumps(lanes)};
var target = "theo", notesList = [], lockedAll = false;
var laneLabels = {{ sora: "Sora", broken: "Broken", theo: "Theo" }};
console.log(JSON.stringify(noteRefusal({json.dumps(p)}, {json.dumps(to)})));
"""
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == why
