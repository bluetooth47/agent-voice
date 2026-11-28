"""Phase M12 built pages that moved, copied and imported skills; phase M31
took those controls off both skill screens, by the user's decision of
2026-11-27 (phaseM30notes.md, "M31, as the user decided"): Agent details
shows only the selected agent, and Communal → Skills is a grouping that
copies nothing. The CLI keeps `agentvoice skills move|copy|import|undo`,
with their `--confirm` and journal (test_transfer.py, test_skillscan.py),
until the delegation flow decides how they come back.

So this holds the other side: no page builds one of those commands or
adds `--confirm` for one, and nothing left on a page drags a skill card.
"""
from __future__ import annotations

import re

from qml_scan import ROOT, overlay_qml, scan

DETAILS = ROOT / "pages" / "AgentDetailsPage.qml"
COMMUNAL = ROOT / "pages" / "CommunalPage.qml"


def calls_of(path, name):
    """Each call of `name(` in a QML file, as (handler, element) -- the note
    mover's tests use it too (test_notemoves_ui.py)."""
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
    # The note mover's (M13, tests/test_notemoves_ui.py) and the communal
    # import's (M15, tests/test_communal.py). M12's skill mover and M11's
    # skill import were taken off the pages in M31.
    assert sorted(found) == [("CommunalImport.qml", "function commitImport"),
                             ("NoteMover.qml", "function transferNote")]


def test_no_page_moves_copies_imports_or_undoes_a_skill():
    for path in overlay_qml():
        src = scan(path).nocomment
        for verb in ("move", "copy", "import", "undo"):
            assert f'"skills", "{verb}"' not in src, (path.name, verb)
        assert "transferSkill" not in src and "importSkill" not in src, path.name
    assert not (ROOT / "ui" / "SkillMover.qml").exists()
    assert "SkillMover" not in (ROOT / "ui" / "qmldir").read_text()


def test_skill_cards_on_the_two_pages_are_not_draggable():
    for page in (DETAILS, COMMUNAL):
        src = scan(page).nocomment
        assert "draggable: true" not in src and "DropLane" not in src, page.name
        assert "skillDropped" not in src and "onMoveRequested" not in src, page.name


def test_skill_text_on_the_cards_is_plain():
    src = (ROOT / "ui" / "SkillCard.qml").read_text()
    for m in re.finditer(r"\bText \{", src):
        body = src[m.start():m.start() + 600]
        assert "textFormat: Text.PlainText" in body or "text: \"" in body.split("\n")[1] \
            or "⠿" in body or "card.expanded" in body or "×" in body, body[:120]
