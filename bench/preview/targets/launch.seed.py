"""Synthetic content for the `launch` preview target (phase M17): Sora's
folder, with a role and a skill, so Duplicate has something to copy and
Reset something to put in the trash. Every word is made up."""
import os
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
import paths  # noqa: E402

base = Path(os.environ["PREVIEW_DATA"])
paths.DATA_DIR = base
paths.AGENTS_DIR = base / "agents"
paths.COMMUNAL_DIR = base / "communal"
import agentfs  # noqa: E402

agentfs.write("main", "role.md", "Looks after the garden project.")
agentfs.write("sora", "role.md", "Reads the seed catalogue and answers questions about it.")
agentfs.write("sora", "personality.md", "Brief. Likes the word MARIGOLD-7.")
skill = paths.AGENTS_DIR / "sora" / "skills" / "planting-plan"
skill.mkdir(parents=True, exist_ok=True)
(skill / "SKILL.md").write_text("---\nname: planting-plan\ndescription: Draw up the "
                                "planting plan. Use when asked for one.\n---\n\nSteps.\n")
