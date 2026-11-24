#!/usr/bin/env python3
"""Print every setting as key -> the page that writes it -> the control.

The snapshot the master plan asks for before the redesign moves anything
(M1): each phase that moves a control can rerun this and diff it against the
table in its notes, so a key that lost its home, or gained a second one,
shows up as a changed line rather than as a user asking where it went.

    python3 -I bench/key-inventory.py > /tmp/keys.md

Reads the QML structurally (tests/qml_scan.py), never imports the daemon.
Writes nothing.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "tests"))

from qml_scan import scan  # noqa: E402


def control_at(s, pos) -> str:
    """The innermost element holding a write, and the handler it is in."""
    el = s.element_of(pos) or "?"
    h = s.handler_of(pos)
    return f"{el} ({h})" if h else el


def overlay_homes() -> dict[str, tuple[str, str]]:
    """OVERLAY_HOMES from tests/test_settings_pages.py, read with ast rather
    than imported: a key whose one writer is an overlay function (M10's
    setAgentTool, M11's setAgentSkill, M17's setAgentField) and the page that
    calls it. Without it those keys printed as having no home (M29)."""
    tree = ast.parse((ROOT / "tests" / "test_settings_pages.py").read_text())
    for node in tree.body:
        target = node.target if isinstance(node, ast.AnnAssign) else (
            node.targets[0] if isinstance(node, ast.Assign) else None)
        if isinstance(target, ast.Name) and target.id == "OVERLAY_HOMES":
            return ast.literal_eval(node.value)
    return {}


def main() -> int:
    homes = overlay_homes()
    manifest = json.loads((ROOT / "manifest.json").read_text())["barWidget"]
    schema = [k["key"] for k in manifest["schema"]]
    extra = sorted(set(manifest["defaults"]) - set(schema))
    pages = sorted((ROOT / "pages").glob("*.qml"))
    scanned = [scan(p) for p in pages]

    print("| Key | Kind | Page | Control (handler) |")
    print("|---|---|---|---|")
    for key in schema + extra:
        kind = "schema" if key in schema else "defaults only"
        rows = []
        pat = re.compile(r'\b(?:put|putMap)\("' + re.escape(key) + r'"')
        for s in scanned:
            for m in pat.finditer(s.nocomment):
                if s.clean[m.start()] == s.src[m.start()]:
                    rows.append((s.path.stem, control_at(s, m.start())))
        if not rows and key in homes:
            fn, page = homes[key]
            rows.append((page.removesuffix(".qml"), f"overlay function {fn}"))
        if not rows:
            print(f"| `{key}` | {kind} | **none** | |")
        for page, ctl in sorted(set(rows)):
            print(f"| `{key}` | {kind} | {page} | {ctl} |")

    print()
    print("| voiceAgents[i] field | Page | Control (handler) |")
    print("|---|---|---|")
    agents = scan(ROOT / "pages" / "AgentsPage.qml")
    fields: dict[str, set[str]] = {}
    for m in re.finditer(r'\bupdateAgent\([^"\n]*?"(\w+)"', agents.nocomment):
        if agents.clean[m.start()] == agents.src[m.start()]:
            fields.setdefault(m.group(1), set()).add(("AgentsPage", control_at(agents, m.start())))
    endpoint = scan(ROOT / "ui" / "EndpointEditor.qml")
    for m in re.finditer(r'\bedited\("(\w+)"', endpoint.nocomment):
        fields.setdefault(m.group(1), set()).add(("AgentsPage", "EndpointEditor → " + control_at(endpoint, m.start())))
    for key, (fn, page) in homes.items():
        if key.startswith("field:"):
            fields.setdefault(key[len("field:"):], set()).add((page.removesuffix(".qml"), f"overlay function {fn}"))
    for field in sorted(fields):
        for page, ctl in sorted(fields[field]):
            print(f"| `{field}` | {page} | {ctl} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
