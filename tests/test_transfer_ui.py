"""Phase M12: the pages that move skills ask before widening, and nothing
else reaches the confirmed command.

The daemon refuses a move into Communal, or out of a quarantined agent,
without `--confirm` (test_transfer.py). This holds the other half: that the
pages add `--confirm` only after the person said yes -- in
SkillMover.transferSkill, called only from a ToolConfirm's onConfirmed, and
in the import's own function, likewise -- and that every way a card can be
moved (a drop on a lane, its Move to… menu) ends in the one function that
decides whether to ask. A refused drop is said, not silent.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import json

import pytest

from qml_scan import ROOT, overlay_qml, scan
from test_tool_controls import function_source

MOVER = ROOT / "ui" / "SkillMover.qml"
DETAILS = ROOT / "pages" / "AgentDetailsPage.qml"
COMMUNAL = ROOT / "pages" / "CommunalPage.qml"
NODE = shutil.which("node")


def calls_of(path, name):
    s = scan(path)
    out = []
    for m in re.finditer(r"\b" + re.escape(name) + r"\(", s.nocomment):
        if s.nocomment[max(0, m.start() - 9):m.start()].endswith("function "):
            continue
        out.append((s.handler_of(m.start()), s.element_of(m.start())))
    return out


def test_confirm_is_added_only_in_the_two_confirmed_functions():
    found = []
    for path in overlay_qml():
        s = scan(path)
        for m in re.finditer(r'"--confirm"', s.nocomment):
            found.append((path.name, s.handler_of(m.start())))
    # Since M13 the note mover's own confirmed function too
    # (tests/test_notemoves_ui.py).
    assert sorted(found) == [("AgentDetailsPage.qml", "function importSkill"),
                             ("NoteMover.qml", "function transferNote"),
                             ("SkillMover.qml", "function transferSkill")]


def test_the_confirmed_move_is_reached_only_from_a_confirm():
    for path in overlay_qml():
        got = calls_of(path, "transferSkill")
        if path == MOVER:
            assert got == [("onConfirmed", "ToolConfirm")], got
        else:
            assert got == [], (path.name, got)


def test_move_and_copy_commands_are_built_only_in_the_mover():
    for path in overlay_qml():
        src = scan(path).nocomment
        hits = len(re.findall(r'"skills",\s*(?:p\.copy|copy === true)', src)) + src.count('"skills", "undo"')
        if path == MOVER:
            assert hits == 3, hits
        else:
            assert hits == 0, path.name
            assert '"skills", "move"' not in src and '"skills", "copy"' not in src, path.name


@pytest.mark.parametrize("page", [DETAILS, COMMUNAL])
def test_every_way_a_card_moves_goes_through_skill_dropped(page):
    """A drop on a lane and a card's menu both end in skillDropped, which
    refuses (and says so) or hands the move to the mover's request()."""
    s = scan(page)
    dropped = calls_of(page, "skillDropped")
    handlers = {h for h, _ in dropped}
    assert handlers == {"onReceived", "onMoveRequested"}, handlers
    assert calls_of(page, "request") and all(h == "function skillDropped" for h, _ in calls_of(page, "request"))
    fn = function_source(page, "skillDropped")
    assert "skillRefusal(p, to)" in fn and "page.skillNote = why" in fn
    # Every lane judges a hovering card by the same refusal.
    assert len(re.findall(r"refuse: function\(p, copy, from\) \{ return page\.skillRefusal\(p, ", s.nocomment)) >= 2
    assert "not built yet" not in s.src


def test_a_skill_found_outside_is_only_ever_copied_and_only_through_the_import_confirm():
    fn = function_source(DETAILS, "skillDropped")
    assert "if (p.outside) { page.askImport(p.entry, to); return }" in fn
    src = scan(DETAILS).nocomment
    # Outside cards offer copying alone.
    assert src.count("canMove: modelData.native !== true") == 2
    assert "canMove: false" in src
    assert calls_of(DETAILS, "importSkill") == [("onConfirmed", "ToolConfirm")]


def test_the_mover_asks_for_communal_and_quarantine_and_an_unreadable_list():
    fn = function_source(MOVER, "widening")
    assert 'to === "communal"' in fn and "isQuarantined(from)" in fn
    q = function_source(MOVER, "isQuarantined")
    assert "!quarantineReadable()" in q
    for page in (DETAILS, COMMUNAL):
        assert 'quarantined: page.s.setting("crewQuarantine", [])' in page.read_text()


def test_skill_text_on_the_cards_and_the_confirm_is_plain():
    for path in (MOVER, ROOT / "ui" / "SkillCard.qml"):
        src = path.read_text()
        for m in re.finditer(r"\bText \{", src):
            body = src[m.start():m.start() + 600]
            assert "textFormat: Text.PlainText" in body or "text: \"" in body.split("\n")[1] \
                or "⠿" in body or "card.expanded" in body or "×" in body, (path.name, body[:120])


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.parametrize("quarantined, frm, to, asks", [
    ([], "theo", "communal", True), ([], "theo", "sora", False), (["theo"], "theo", "sora", True),
    (["hazel"], "theo", "sora", False), (None, "theo", "sora", True), ("x", "theo", "sora", True),
    ([], "communal", "sora", False), (None, "communal", "sora", False)])
def test_when_the_mover_asks(quarantined, frm, to, asks):
    script = "\n".join(function_source(MOVER, n) for n in
                       ("quarantineReadable", "isQuarantined", "widening"))
    script = script.replace("function ", "function ") + f"""
var quarantined = {json.dumps(quarantined)};
console.log(JSON.stringify(widening({json.dumps(frm)}, {json.dumps(to)})));
"""
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) is asks
