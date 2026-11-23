"""Synthetic content for the `advanced` preview target (phase M16): the
main agent's personality and instructions, holding a made-up word the page
must not draw until a piece is shown, and permission decisions in the
scratch audit log, written through audit.record exactly as the hook writes
them. Every word is made up."""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, sys.argv[1])
import paths  # noqa: E402

base = Path(os.environ["PREVIEW_DATA"])
paths.DATA_DIR = base
paths.AGENTS_DIR = base / "agents"
paths.COMMUNAL_DIR = base / "communal"
import agentfs  # noqa: E402
import audit  # noqa: E402

agentfs.write("main", "personality.md", "Calm and plain. Keeps a lighthouse called MARIGOLD-7.")
agentfs.write("main", "instructions.md", "Say which file you changed.")
agentfs.write("communal", "rules.md", "Ask before deleting anything.")

for who, tool, decision, how, level in (
        ("main", "Bash", "allow", "asked", "ask"),
        ("main", "Write", "deny", "unanswered", "ask"),
        ("main", "mcp__github__create_issue", "deny", "refused", "ask"),
        ("main", "Edit", "allow", "chat", "ask"),
        ("hazel", "Bash", "allow", "level", "trusted")):
    audit.record("permission", frm=who, to=who, tool=tool, decision=decision, how=how,
                 level=level)
    time.sleep(0.01)
