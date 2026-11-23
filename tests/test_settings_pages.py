"""Every setting has one home.

The settings page was scattered: agent settings in three boxes, the wake word
in four. Splitting it into pages fixes that only while each setting stays on
the page it belongs to, so this holds it: every key the manifest declares is
*changed* on exactly one settings page. A key read elsewhere (the Overview
shows the gate, the Agents card names the voice) is fine; a second control
for it is the scattering coming back.

The popup's five quick toggles and voice are the deliberate exception, and
live in Panel.qml, not in pages/. Its permission level was one too until M3
removed it (bug D): permissions are per agent, with one home on the Agents
page. So is the Voice page's
library, whose "Use for" sets an agent's voice: it goes through the overlay's
`assignVoice`, never a page's own put, so the Agents card stays the voice's
one home and the library is a shortcut to it (held below).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = sorted((ROOT / "pages").glob("*.qml"))


def _declared() -> set[str]:
    manifest = json.loads((ROOT / "manifest.json").read_text())
    return {k["key"] for k in manifest["barWidget"]["schema"]}


def _writers(key: str) -> list[str]:
    # `s.put("key", ...)`, or a page helper that writes one key of a per-agent
    # map, `putMap("key", ...)`.
    pattern = re.compile(r'\b(?:put|putMap)\("' + re.escape(key) + r'"')
    return [p.name for p in PAGES if pattern.search(p.read_text())]


def test_there_are_pages_to_check():
    assert len(PAGES) >= 7, [p.name for p in PAGES]


def test_every_setting_is_changed_on_exactly_one_page():
    wrong = {k: _writers(k) for k in sorted(_declared()) if len(_writers(k)) != 1}
    assert wrong == {}, wrong


def test_a_reset_goes_back_to_the_manifest_default():
    """`reset` links call resetKey, which needs the defaults the manifest
    declares; the overlay reads them from the file rather than relying on the
    shell to pass the manifest in."""
    settings = (ROOT / "Settings.qml").read_text()
    assert 'Qt.resolvedUrl("manifest.json")' in settings
    assert "m.barWidget.defaults" in settings


def test_every_page_is_reachable_from_the_sidebar():
    settings = (ROOT / "Settings.qml").read_text()
    for p in PAGES:
        assert f"{p.stem} {{ s: root }}" in settings, f"{p.name} is never shown"


def test_the_voice_librarys_shortcut_goes_through_one_function():
    voice = (ROOT / "pages" / "VoicePage.qml").read_text()
    assert "s.assignVoice(" in voice
    assert not re.search(r'\bput\("(voice|voiceAgents)"', voice)
    settings = (ROOT / "Settings.qml").read_text()
    body = settings[settings.index("function assignVoice("):]
    body = body[:body.index("\n  }")]
    assert 'root.put("voice", v)' in body and "root.chooseVoice(v)" in body


# --- FIELD_HOMES: the keys the test above cannot see ------------------------
#
# The test above reads manifest *schema* keys, which leaves out two kinds of
# setting: the six the manifest gives a default but no schema entry (maps and
# lists Omarchy cannot draw a control for), and every field inside an entry
# of `voiceAgents`, which is one key holding all the extra agents. Those are
# exactly what the redesign moves around most (master plan, M1), so before
# anything moves this says where each one is written.
#
# For a voiceAgents[i] field: (the page that writes it, its main-agent twin
# or None). A field is written through the page's `updateAgent(i, "field",
# ...)`, or through a ui/ piece whose `edited("field", ...)` the page passes
# to updateAgent. None as the page means no control writes it: `id` is
# filled in by the list functions themselves, and `instructions` is the
# pre-folder field, read as a fallback and migrated into the agent's folder
# (Phase 10), never written again.
FIELD_HOMES: dict[str, tuple[str | None, str | None]] = {
    "enabled": ("AgentsPage.qml", None),          # the main agent cannot be switched off
    "label": ("AgentsPage.qml", "mainName"),
    "name": ("AgentsPage.qml", "phrase"),
    "agent": ("AgentsPage.qml", "mainProgram"),
    "model": ("AgentsPage.qml", "agentModels"),
    "effort": ("AgentsPage.qml", "agentEfforts"),
    "level": ("AgentsPage.qml", "permissions"),
    "voice": ("AgentsPage.qml", "voice"),
    "speed": ("AgentsPage.qml", "voiceSpeed"),
    "narration": ("AgentsPage.qml", "narration"),
    "projectDir": ("AgentsPage.qml", "projectDir"),
    # Since M10 through the overlay's setAgentTool, called from Agent
    # details' Tools & skills only (OVERLAY_HOMES below).
    "tools": ("AgentDetailsPage.qml", "mainTools"),
    # Phase M11: through the overlay's setAgentSkill, the same way.
    "skillsOff": ("AgentDetailsPage.qml", "mainSkillsOff"),
    "notesWrite": ("AgentsPage.qml", "mainNotesWrite"),
    "collaboration": ("AgentsPage.qml", "mainCollaboration"),
    "acceptsWork": ("AgentsPage.qml", "mainAcceptsWork"),
    # Master plan M20: which saved chats its chat tools may search, on the
    # Agents page's Collaboration, notes & chats card.
    "chatSearch": ("AgentsPage.qml", "mainChatSearch"),
    "endpointUrl": ("AgentsPage.qml", "endpointUrl"),
    "endpointModel": ("AgentsPage.qml", "endpointModel"),
    "endpointIsAgent": ("AgentsPage.qml", "endpointIsAgent"),
    "endpointTimeoutS": ("AgentsPage.qml", "endpointTimeoutS"),
    "endpointHistoryTurns": ("AgentsPage.qml", "endpointHistoryTurns"),
    # Phase M17: how it is launched, on Agent details → Advanced; an extra
    # agent's through the overlay's setAgentField (OVERLAY_HOMES below), the
    # main agent's twins put there directly.
    "resume": ("AgentDetailsPage.qml", "mainResume"),
    "idleTimeoutS": ("AgentDetailsPage.qml", "mainIdleTimeoutS"),
    "extraArgs": ("AgentDetailsPage.qml", "mainExtraArgs"),
    "id": (None, None),
    "instructions": (None, None),
}

# Fields a page sets through a ui/ piece's edited(key, value) signal, which
# the page hands to updateAgent with the key it was given.
VIA_PIECE = {"EndpointEditor": ("endpointUrl", "endpointModel", "endpointIsAgent",
                                "endpointTimeoutS", "endpointHistoryTurns")}

# A field or key written outside a page, and the one named overlay function
# that may do it. The Voice library's "Use for" goes through assignVoice (held
# above); removing, restoring and undoing an agent rewrites the whole list
# through AgentFolders' saveAgents. The popup's voice picker is the
# documented exception (module docstring); its level picker went in M3.
OUTSIDE_WRITERS: dict[tuple[str, str], set[str]] = {
    ("Settings.qml", "function assignVoice"): {"voice", "voiceAgents", "field:voice"},
    # Phase M10: an agent's own tool switches, the one overlay function the
    # Tools & skills tab writes them through.
    ("Settings.qml", "function setAgentTool"): {"mainTools", "voiceAgents", "field:tools"},
    # Phase M11: the skills switched off for an agent.
    ("Settings.qml", "function setAgentSkill"): {"mainSkillsOff", "voiceAgents", "field:skillsOff"},
    # Phase M17: an extra agent's launch fields.
    ("Settings.qml", "function setAgentField"): {"voiceAgents", "field:resume",
                                                 "field:idleTimeoutS", "field:extraArgs"},
    ("Settings.qml", "function trainVerifier"): {"engine"},
    ("AgentFolders.qml", "function saveAgents"): {"voiceAgents"},
    ("Panel.qml", "*"): {"voice"},
}

DEFAULTS_ONLY = {"agentEfforts", "agentModels", "mainTools", "permissions",
                 "voiceAgents", "wakeAlsoSounds",
                 # Phase M8: two lists, written on the Crew map page.
                 "crewLinks", "crewQuarantine",
                 # Phase M10: the found tools for every agent, a map written
                 # on Communal → Tools.
                 "sharedTools",
                 # Phase M11: the main agent's skills switched off, a list
                 # written on Agent details → Tools & skills.
                 "mainSkillsOff",
                 # Phase M15: the agents that take nothing from Communal, a
                 # list written on Communal → Who gets it.
                 "communalOff",
                 # Phase M17: the main agent's extra flags, a list written on
                 # Agent details → Advanced.
                 "mainExtraArgs"}

# A key or an agent field whose one writer is an overlay function, and the
# one page that calls it (phase M10). The page is its home: a call from any
# other page is a second home.
OVERLAY_HOMES: dict[str, tuple[str, str]] = {
    "mainTools": ("setAgentTool", "AgentDetailsPage.qml"),
    "field:tools": ("setAgentTool", "AgentDetailsPage.qml"),
    "mainSkillsOff": ("setAgentSkill", "AgentDetailsPage.qml"),
    "field:skillsOff": ("setAgentSkill", "AgentDetailsPage.qml"),
    # Phase M17: an extra agent's launch fields. (The main agent's twins are
    # put by that page directly, so they need no entry here.)
    "field:resume": ("setAgentField", "AgentDetailsPage.qml"),
    "field:idleTimeoutS": ("setAgentField", "AgentDetailsPage.qml"),
    "field:extraArgs": ("setAgentField", "AgentDetailsPage.qml"),
}


def _overlay_callers(fn: str) -> set[str]:
    """The pages (and ui/ pieces) that call `s.<fn>(`."""
    from qml_scan import overlay_qml, scan
    out = set()
    for path in overlay_qml():
        if path.name == "Settings.qml":
            continue
        src = scan(path)
        for m in re.finditer(r"\b" + re.escape(fn) + r"\(", src.nocomment):
            if src.clean[m.start()] == src.src[m.start()]:
                out.add(("ui/" if path.parent.name == "ui" else "") + path.name)
    return out


def _defaults_only() -> set[str]:
    manifest = json.loads((ROOT / "manifest.json").read_text())["barWidget"]
    return set(manifest["defaults"]) - {k["key"] for k in manifest["schema"]}


def _daemon_fields() -> set[str]:
    """Every voiceAgents[i] field runtime.Config._agents() reads, parsed out
    of the function rather than listed by hand, so a field the daemon
    starts reading needs a home here before the suite passes."""
    import ast
    tree = ast.parse((ROOT / "daemon" / "runtime.py").read_text())
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_agents")
    out = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        # entry.get("x")
        if (isinstance(node.func, ast.Attribute) and node.func.attr == "get"
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "entry"
                and node.args and isinstance(node.args[0], ast.Constant)):
            out.add(node.args[0].value)
        # notes_choice(entry, "notesWrite") and its siblings
        if (len(node.args) >= 2 and isinstance(node.args[0], ast.Name) and node.args[0].id == "entry"
                and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str)):
            out.add(node.args[1].value)
    return out


def _field_writers() -> dict[str, set[str]]:
    """field -> the files (and, outside pages/, functions) that write it."""
    from qml_scan import overlay_qml, scan
    found: dict[str, set[str]] = {}
    pieces = {}
    for name, fields in VIA_PIECE.items():
        s = scan(ROOT / "ui" / f"{name}.qml")
        emitted = set(re.findall(r'\bedited\("(\w+)"', s.nocomment))
        assert emitted == set(fields), (name, emitted)
        pieces[name] = fields
    for path in overlay_qml():
        s = scan(path)
        # ui/ pieces are scanned too, as their own writers: one that called
        # updateAgent itself would be a second home the page cannot see
        # (Codex review, M1). Their edited() signals are VIA_PIECE above.
        where = ("ui/" if path.parent.name == "ui" else "") + path.name
        for m in re.finditer(r'\bupdateAgent\([^"\n]*?"(\w+)"', s.nocomment):
            if s.clean[m.start()] == s.src[m.start()]:
                found.setdefault(m.group(1), set()).add(where)
        # Outside the Agents page's updateAgent: a copied entry given a field.
        for m in re.finditer(r'\bcopy\.(\w+)\s*=(?!=)', s.clean):
            if m.group(1) == "id":
                continue
            h = s.handler_of(m.start())
            found.setdefault(m.group(1), set()).add(f"{where} {h}")
        # An overlay function that writes one agent field (phase M10).
        for key, (fn, _) in OVERLAY_HOMES.items():
            if key.startswith("field:") and path.name != "Settings.qml" and \
                    re.search(r"\b" + re.escape(fn) + r"\(", s.nocomment):
                found.setdefault(key[6:], set()).add(where)
        # A piece whose edited(key, value) is handed to updateAgent.
        for name, fields in pieces.items():
            for m in re.finditer(r"\b" + name + r"\s*\{", s.clean):
                body = s.clean[m.end():s.closes[m.end() - 1]]
                if re.search(r"onEdited\s*:\s*function\s*\(\s*key\s*,\s*value\s*\)\s*\{[^}]*updateAgent\([^,]+,\s*key\b", body):
                    for f in fields:
                        found.setdefault(f, set()).add(where)
    return found


def test_the_defaults_only_keys_are_the_ones_this_file_knows():
    assert _defaults_only() == DEFAULTS_ONLY


def test_every_daemon_agent_field_has_a_home():
    assert _daemon_fields() == set(FIELD_HOMES), _daemon_fields() ^ set(FIELD_HOMES)


def test_every_agent_field_is_written_on_exactly_one_page():
    writers = _field_writers()
    unknown = set(writers) - set(FIELD_HOMES)
    assert unknown == set(), f"written but given no home in FIELD_HOMES: {unknown}"
    wrong = {}
    for field, (home, _) in FIELD_HOMES.items():
        got = writers.get(field, set())
        pages = {w for w in got if " " not in w}
        outside = {w for w in got if " " in w}
        allowed_outside = {f"{f} {fn}" for (f, fn), keys in OUTSIDE_WRITERS.items()
                           if f"field:{field}" in keys}
        if pages != ({home} if home else set()) or not outside <= allowed_outside:
            wrong[field] = sorted(got)
    assert wrong == {}, wrong


def _key_writers(key: str) -> list[str]:
    """_writers, plus the pages calling the overlay function that is the
    key's one writer (OVERLAY_HOMES)."""
    out = set(_writers(key))
    if key in OVERLAY_HOMES:
        out |= _overlay_callers(OVERLAY_HOMES[key][0])
    return sorted(out)


def test_every_main_twin_and_defaults_only_key_is_written_on_exactly_one_page():
    keys = {twin for _, twin in FIELD_HOMES.values() if twin} | DEFAULTS_ONLY
    wrong = {k: _key_writers(k) for k in sorted(keys) if len(_key_writers(k)) != 1}
    assert wrong == {}, wrong


def test_an_overlay_home_is_called_from_its_page_alone():
    """setAgentTool has one caller page (phase M10): a second page calling
    it is a second home for every agent's tools, which the twin test above
    would also catch -- this names it."""
    for key, (fn, page) in OVERLAY_HOMES.items():
        assert _overlay_callers(fn) == {page}, (key, _overlay_callers(fn))


def test_settings_written_outside_the_pages_go_through_named_functions():
    """Settings.qml, the popup and the helpers are not pages, so the
    one-page tests never read them. A write there is allowed only in the
    functions OUTSIDE_WRITERS names, for the keys it names."""
    from qml_scan import scan
    declared = _declared() | _defaults_only()
    wrong = []
    for name in ("Settings.qml", "Panel.qml", "AgentFolders.qml", "Chats.qml", "Hud.qml"):
        path = ROOT / name
        if not path.exists():
            continue
        s = scan(path)
        for m in re.finditer(r'\b(?:put|set|putMap)\("(\w+)"', s.nocomment):
            key = m.group(1)
            if key not in declared or s.clean[m.start()] != s.src[m.start()]:
                continue
            h = s.handler_of(m.start())
            ok = any(f == name and (fn == "*" or fn == h) and key in keys
                     for (f, fn), keys in OUTSIDE_WRITERS.items())
            if not ok:
                wrong.append(f"{name}:{s.lineno(m.start())} {key} in {h or 'nothing'}")
    assert wrong == [], wrong


def test_field_homes_catches_a_second_writer():
    """Mutation, on the table rather than a file: a field claimed by a page
    that does not write it is reported, so the test is not vacuous."""
    writers = _field_writers()
    assert writers["voice"] >= {"AgentsPage.qml"}
    assert "ConversationPage.qml" not in writers.get("narration", set())
    assert writers["endpointUrl"] == {"AgentsPage.qml"}


def test_the_popup_no_longer_writes_a_permission_level():
    """Bug D (phase M3): the popup's "what Claude Code may do" picker was a
    second, global way to set -- and promote to trusted -- what is now set
    per agent on the Agents page. Read with the comments stripped, so a
    sentence about the old picker does not count as the picker."""
    from qml_scan import scan
    panel = scan(ROOT / "Panel.qml").nocomment
    assert '"permissions"' not in panel
    for gone in ("setMainLevel", "trustPending", "Trust it"):
        assert gone not in panel, gone
    agents = (ROOT / "pages" / "AgentsPage.qml").read_text()
    assert re.search(r'\b(?:put|putMap)\("permissions"', agents), "its one home"
