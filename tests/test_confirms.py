"""A command that destroys something runs only from a confirmation.

Feedback item 14 asks for "a warning and a confirm everywhere". ui/
DangerButton is the confirm: its first click only arms it, and the action
runs from `onConfirmed`. This holds the other half -- that nothing reaches a
destructive command any other way. A page that called `folders.remove(...)`
from a plain `onClicked` would draw and work perfectly, and lose somebody an
agent on one stray click; no screenshot would show it.

How it is held, per verb:

1. the command is built in exactly the overlay functions named here, and
   nowhere else (so a new path to it has to be added to this table, by
   somebody who then reads why);
2. every call of those functions, in every QML file, is inside an
   `onConfirmed` handler -- or inside one of the named functions
   themselves, which is how a wrapper passes it on.

Later phases add their verbs (reset, delete --all, stats clear, link
delete) to DESTRUCTIVE with the functions that run them.
"""
from __future__ import annotations

import re

import pytest

from qml_scan import ROOT, overlay_qml, scan

def call(dotted: str, arg: str = "") -> re.Pattern:
    """A call of `dotted` (`folders.remove`), any spacing, optionally with a
    first argument that is the string `arg` in any quotes. Exact substrings
    missed `run('delete', ...)` (Codex review, M1)."""
    name = r"\s*\.\s*".join(re.escape(p) for p in dotted.split("."))
    tail = r"\s*\(" + (r"\s*['\"`]" + re.escape(arg) + r"['\"`]" if arg else "")
    return re.compile(r"(?<![\w.])(?:\w+\s*\.\s*)*" + name + tail if "." not in dotted
                      else r"\b" + name + tail)


def start(process: str) -> re.Pattern:
    """Anything that starts Process `process`: `running = ...` or
    startDetached()."""
    return re.compile(r"\b" + re.escape(process) + r"\s*\.\s*(?:running\s*=(?!=)|startDetached\s*\()")


# verb: (where it is built: {file: [the functions, handlers or, for a
# declaration, the element holding it]}, the calls that reach it)
DESTRUCTIVE: dict[str, tuple[dict[str, list[str]], list[re.Pattern]]] = {
    # An agent's folder and settings entry to the trash. AgentFolders also
    # re-trashes after a failed restore (`onFailed`): that is a rollback of
    # the user's own undo, never a first removal.
    "agents trash": ({"AgentFolders.qml": ["remove", "trashOrphan", "onFailed"]},
                     [call("folders.remove"), call("folders.trashOrphan"), call("removeAgent")]),
    "chats delete": ({"Chats.qml": ["run"]}, [call("run", "delete")]),
    "--uninstall": ({"Settings.qml": ["removeEverything"]}, [call("removeEverything"), start("remover")]),
    # The session's conversation, from memory: a Process, started by
    # setting `running`, which only clearSession() does.
    "history clear": ({"Settings.qml": ["Process"]}, [call("clearSession"), start("clearHistory")]),
    # Phase M8, the Crew map. A link deleted; every agent linked to every
    # other (it widens rather than destroys, and is held the same way:
    # question 2 asks for a confirm); an agent quarantined, which loses its
    # links out, its sessions and its shared chats; and unreadable crew
    # settings replaced with none, which loses whatever was written there.
    # Each list is built by a helper only its one wrapper calls.
    "link delete": ({"CrewMapPage.qml": ["removeLink"]},
                    [call("removeLink"), call("withoutLink")]),
    "link everyone": ({"CrewMapPage.qml": ["linkEveryone"]},
                      [call("linkEveryone"), call("everyoneLinks")]),
    "quarantine": ({"CrewMapPage.qml": ["quarantineAgent"]},
                   [call("quarantineAgent"), call("linksQuarantining")]),
    "crew reset": ({"CrewMapPage.qml": ["clearUnreadable"]}, [call("clearUnreadable")]),
}

# How each verb looks where it is built.
SPELLING = {
    "agents trash": '["trash"',
    "chats delete": '"chats", verb',
    "--uninstall": "--uninstall",
    "history clear": '"history", "clear"',
    "link delete": '"link delete "',
    "link everyone": '"link everyone"',
    "quarantine": '"quarantine "',
    "crew reset": '"crew reset"',
}

# Functions a call may sit in without a confirmation of its own, because
# they are the wrappers named above, file by file: their own callers are
# checked, by the patterns above. A function of the same name anywhere else
# earns nothing (Codex review, M1).
WRAPPERS = {("AgentFolders.qml", "function remove"), ("AgentFolders.qml", "function trashOrphan"),
            ("pages/AgentsPage.qml", "function removeAgent"),
            ("Settings.qml", "function removeEverything"), ("Settings.qml", "function clearSession"),
            ("pages/CrewMapPage.qml", "function removeLink"),
            ("pages/CrewMapPage.qml", "function linkEveryone"),
            ("pages/CrewMapPage.qml", "function quarantineAgent")}


def _built_in(scanned, spelling):
    """Where a verb's spelling occurs in code or in a string, not a comment."""
    if spelling.startswith(("[", '"')):
        return [m.start() for m in re.finditer(re.escape(spelling), scanned.nocomment)]
    return scanned.literals(spelling)


@pytest.mark.parametrize("verb", sorted(DESTRUCTIVE))
def test_each_destructive_command_is_built_only_where_the_table_says(verb):
    built, _ = DESTRUCTIVE[verb]
    found = {}
    for path in overlay_qml():
        s = scan(path)
        for pos in _built_in(s, SPELLING[verb]):
            h = s.handler_of(pos).replace("function ", "") or s.element_of(pos)
            found.setdefault(path.name, set()).add(h)
    expected = {f: set(fs) for f, fs in built.items()}
    assert found == expected, (verb, found)


@pytest.mark.parametrize("verb", sorted(DESTRUCTIVE))
def test_each_destructive_command_runs_only_from_a_confirmation(verb):
    _, calls = DESTRUCTIVE[verb]
    seen = 0
    wrong = []
    for path in overlay_qml():
        s = scan(path)
        rel = str(path.relative_to(ROOT))
        for needle in calls:
            for pos in s.calls(needle):
                seen += 1
                h = s.handler_of(pos)
                if h == "onConfirmed" or (rel, h) in WRAPPERS:
                    continue
                wrong.append(f"{rel}:{s.lineno(pos)} {needle.pattern} in {h or 'nothing'}")
    assert wrong == [], wrong
    # A table whose calls match nothing checks nothing.
    assert seen > 0, verb


def test_a_chat_is_deleted_only_through_the_confirmed_run():
    """run(verb, ...) is generic, so the verb could arrive in a variable the
    patterns above never see. In Chats.qml the string `delete` appears only
    as run()'s first argument -- in any quotes."""
    s = scan(ROOT / "Chats.qml")
    literals = [m.start() for m in re.finditer(r"['\"`]delete['\"`]", s.nocomment)]
    as_run = {m.end() - len("delete") - 2 for m in call("run", "delete").finditer(s.nocomment)}
    assert literals and set(literals) <= as_run, [s.lineno(p) for p in literals if p not in as_run]


def test_the_buttons_that_confirm_are_danger_buttons():
    """onConfirmed is DangerButton's signal; a handler of that name on
    anything else would satisfy the test above without a confirmation.
    The one other: ToolConfirm (phase M10), the question before a tool
    found on this machine is switched on, whose handlers may only write a
    tool switch -- or, since M11, give an agent a copy of a skill found on
    this machine (importSkill), or, since M12, move or copy a skill into
    Communal or out of a quarantined agent (transferSkill) -- never one of
    the destructive commands above."""
    wrong = []
    for path in overlay_qml():
        s = scan(path)
        for m in re.finditer(r"\bonConfirmed\s*:", s.clean):
            el = s.element_of(m.start())
            if el == "ToolConfirm":
                body = s.src[m.end():m.end() + 400].split("onCancelled")[0]
                if not re.search(r"\b(setAgentTool|putShared|importSkill|transferSkill)\(", body) or \
                        re.search(r"agents\W+trash|chats\W+delete|--uninstall|remove|reset", body):
                    wrong.append(f"{path.relative_to(ROOT)}:{s.lineno(m.start())} ToolConfirm "
                                 f"doing something other than a tool switch")
            elif el != "DangerButton":
                wrong.append(f"{path.relative_to(ROOT)}:{s.lineno(m.start())} on {el}")
    assert wrong == [], wrong


def test_tool_confirm_says_yes_only_from_its_own_button():
    s = scan(ROOT / "ui" / "ToolConfirm.qml")
    emits = [m.start() for m in re.finditer(r"\bconfirmed\(\)", s.clean)
             if not s.clean[max(0, m.start() - 7):m.start()].endswith("signal ")]
    assert [s.handler_of(p) for p in emits] == ["onClicked"]
    assert "cancelButton.forceActiveFocus()" in s.src and "Keys.onEscapePressed" in s.src


def test_the_danger_button_runs_its_action_only_on_the_second_step():
    s = scan(ROOT / "ui" / "DangerButton.qml")
    # Exactly one place emits confirmed(): confirm(), which refuses unless
    # armed; and the idle button only arms.
    emits = [m.start() for m in re.finditer(r"\bconfirmed\(\)", s.clean)
             if not s.clean[max(0, m.start() - 7):m.start()].endswith("signal ")]
    assert [s.handler_of(p) for p in emits] == ["function confirm"]
    body = s.src[s.src.index("function confirm()"):]
    body = body[:body.index("\n  }")]
    assert "if (!_armed" in body
    idle = s.src[s.src.index("id: idle"):]
    idle = idle[:idle.index("\n  }")]
    assert "onClicked: danger.arm()" in idle
    # It disarms by itself, and on Escape; Cancel takes the focus.
    assert "interval: danger.armMs" in s.src and "property int armMs: 6000" in s.src
    assert "Keys.onEscapePressed" in s.src
    assert "cancelButton.forceActiveFocus()" in s.src


def test_the_scanner_sees_a_confirmation_go_missing():
    """The test above has to be able to fail: an onConfirmed turned into an
    onClicked is caught, on a copy."""
    from qml_scan import Scanned, blank
    src = (ROOT / "pages" / "AboutPage.qml").read_text()
    mutated = src.replace("onConfirmed: page.s.removeEverything()",
                          "onClicked: page.s.removeEverything()")
    assert mutated != src

    def scanned(text):
        clean = blank(text)
        stack, opens, closes = [], [], {}
        for i, c in enumerate(clean):
            if c == "{":
                stack.append(i); opens.append(i)
            elif c == "}":
                closes[stack.pop()] = i
        return Scanned(ROOT / "x.qml", text, clean, blank(text, strings=False), opens, closes)

    good, bad = scanned(src), scanned(mutated)
    remove = call("removeEverything")
    assert [good.handler_of(p) for p in good.calls(remove)] == ["onConfirmed"]
    assert [bad.handler_of(p) for p in bad.calls(remove)] == ["onClicked"]

    # The shapes exact substrings missed: other quotes, other spacing, a
    # template literal's ${...} (Codex review, M1).
    chats = (ROOT / "Chats.qml").read_text()
    extra = ("\n  Button { onClicked: view.run('delete', [view.chat.id]) }"
             "\n  Button { onClicked: view . run ( `delete`, []) }"
             "\n  Text { text: `${view.s.clearSession()}` }\n")
    hacked = scanned(chats[:chats.rindex("}")] + extra + "}\n")
    runs = [hacked.handler_of(p) for p in hacked.calls(call("run", "delete"))]
    assert runs.count("onClicked") == 2, runs
    clears = [hacked.handler_of(p) for p in hacked.calls(call("clearSession"))]
    assert clears.count("onConfirmed") == 1 and len(clears) == 2, clears

    # A brace inside a string in ${...} does not end the expression, and
    # a handler is the last one started before the call on its line
    # (Codex review pass 2, M1).
    more = ("\n  Text { text: `${\"}\" + view.s.clearSession()}` }"
            "\n  DangerButton { id: d; onConfirmed: view.s.clearSession() }"
            "\n  DangerButton { onConfirmed: x() } Button { onClicked: view.s.clearSession() }\n")
    hacked = scanned(chats[:chats.rindex("}")] + more + "}\n")
    clears = [hacked.handler_of(p) for p in hacked.calls(call("clearSession"))]
    assert clears == ["onConfirmed", "", "onConfirmed", "onClicked"], clears


def test_no_building_block_writes_a_setting_by_name():
    """ui/ holds pieces that know no setting: a `put("key"` there would be a
    setting drawn wherever the piece happens to be used, which is the
    scattering the pages were split to end. A piece emits; the page puts."""
    wrong = []
    for path in sorted((ROOT / "ui").glob("*.qml")):
        s = scan(path)
        for m in re.finditer(r"\b(?:put|putMap)\(\s*\"", s.nocomment):
            if s.clean[m.start()] == s.src[m.start()]:
                wrong.append(f"ui/{path.name}:{s.lineno(m.start())}")
    assert wrong == [], wrong
