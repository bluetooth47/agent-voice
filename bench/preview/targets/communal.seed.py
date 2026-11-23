"""Synthetic Communal content for the `communal` preview target (phase M15):
rules saved twice (so History has a version to restore), defaults, one
communal skill, Sora's own instructions, and a folder laid out as Export
writes it, for the Import to check and bring in. Written through agentfs,
so every file has its saved versions; every word is made up."""
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

agentfs.write("communal", "rules.md", "Ask before deleting anything.")
time.sleep(0.01)
agentfs.write("communal", "rules.md", "Ask before deleting anything.\nNever buy anything.")
agentfs.write("communal", "defaults.md", "Use metric units.")
d = base / "communal" / "skills" / "house-style"
d.mkdir(parents=True, exist_ok=True)
(d / "SKILL.md").write_text("---\nname: house-style\ndescription: How replies are worded here. "
                            "Use for every written reply.\n---\n\nShort sentences.\n")
agentfs.write("sora", "instructions.md", "Keep answers to two sentences.")

src = base.parent / "import-me"
(src / "skills" / "packing-list").mkdir(parents=True, exist_ok=True)
(src / "rules.md").write_text("Ask before deleting anything.\nNever buy anything.\n"
                              "Say when you are unsure.\n")
(src / "skills" / "packing-list" / "SKILL.md").write_text(
    "---\nname: packing-list\ndescription: Make a packing list for a trip. Use when asked to "
    "pack.\n---\n\nList by category.\n")
(src / "README.txt").write_text("An export from another machine.\n")
