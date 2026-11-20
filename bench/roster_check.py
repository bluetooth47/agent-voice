#!/usr/bin/env python3
"""Does the roster earn its place in the preamble? (merged plan, A11-5)

Asks an agent the same "who else here can help with X?" questions with the
roster of the other agents in its prompt and without it, through the real
adapter at the agent's own level, in an empty scratch folder, and prints
the answers side by side as JSON. Costs one model call per question per
arm.

    python bench/roster_check.py --agent main            # 5 with, 5 without
    python bench/roster_check.py --agent main --role sora="Quick answers"

`--role ID=TEXT` stands in for that agent's role.md in this run only (no
file is written), for a machine whose role lines are still empty. Without
it the real role lines are used. Prints model answers: run it on synthetic
questions, as below, and nothing personal is asked or shown.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "daemon"))
sys.path.insert(0, str(REPO / "bench"))

import agentfs  # noqa: E402
import runtime  # noqa: E402
import start_bench  # noqa: E402

QUESTIONS = [
    "Who else here could help me fix a bug in a Python script?",
    "Is there anyone here who is better for a really quick one-line answer?",
    "Which of the other agents should I ask to refactor some code in my project?",
    "If I want a fast answer about the weather, who should I wake?",
    "Who else can I talk to here, and what are they for?",
]


def answer(ad, question: str) -> str:
    """The whole reply to one fresh turn, or the error it ended with."""
    text = []
    for chunk in ad.send(question):
        if chunk.error:
            return f"(error: {chunk.error})"
        if chunk.text:
            text.append(chunk.text)
    return "".join(text).strip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--agent", default="main")
    ap.add_argument("--role", action="append", default=[],
                    help="ID=TEXT: that agent's role line for this run only")
    a = ap.parse_args(argv)
    cfg = runtime.Config()
    spec = start_bench.agent_spec(cfg, a.agent)
    roles = dict(r.split("=", 1) for r in a.role)
    out = {"agent": a.agent, "roles_given": sorted(roles), "answers": []}
    with tempfile.TemporaryDirectory(prefix="av-roster-") as cwd:
        for q in QUESTIONS:
            row = {"question": q}
            for arm in ("with", "without"):
                ad = start_bench.build(spec, cfg, cwd, "folders")
                parts = dict(ad.parts)
                if arm == "without":
                    parts["roster"] = []
                elif roles:
                    texts = agentfs.snapshot()[1]
                    for target, role in roles.items():
                        texts.setdefault(target, {})["role.md"] = role
                    live = agentfs._configured(cfg)
                    me = agentfs.folder_id(spec["named"])
                    parts = agentfs.parts_from(texts, me, parts["name"], live)
                ad.parts = parts
                try:
                    row[arm] = answer(ad, q)
                finally:
                    ad.cancel()
            out["answers"].append(row)
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
