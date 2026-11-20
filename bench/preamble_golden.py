"""Record Adapter.preamble() from a checkout, for every backend and every
combination that changes it (spoken or quiet, instructions, Omarchy text).
Synthetic text only. Wrote tests/fixtures/preamble/2eeb919.json, which
tests/test_preamble.py holds the new preamble to (merged plan, A11-1):

    git worktree add /tmp/old 2eeb919
    python bench/preamble_golden.py /tmp/old 2eeb919 > tests/fixtures/preamble/2eeb919.json
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "daemon"))
from adapters.claude_code import ClaudeCode
from adapters.codex import Codex
from adapters.gemini import Gemini
from adapters.antigravity import Antigravity
from adapters.cli_agent import CliAgent
from adapters.openai_compat import OpenAICompatible

def backends():
    yield "claude", ClaudeCode
    yield "codex", Codex
    yield "gemini", Gemini
    yield "agy", Antigravity
    yield "copilot", lambda: CliAgent("copilot")
    yield "endpoint-chat", lambda: OpenAICompatible("http://127.0.0.1:9", "m")
    yield "endpoint-agent", lambda: OpenAICompatible("http://127.0.0.1:9", "m", is_agent=True)

INSTR = ["", "Call me captain.\nKeep it to one sentence.", "   padded  "]
SKILL = ["", "OMARCHY SKILL TEXT (synthetic)"]
out = {}
for name, make in backends():
    for spoken in (True, False):
        for i, instr in enumerate(INSTR):
            for k, skill in enumerate(SKILL):
                ad = make()
                ad.spoken = spoken
                ad.instructions = instr
                ad.skill_text = skill
                out[f"{name}|spoken={int(spoken)}|instr={i}|skill={k}"] = ad.preamble()
json.dump({"build": sys.argv[2], "instructions": INSTR, "skill_text": SKILL,
           "preambles": out}, sys.stdout, indent=1, ensure_ascii=False)
