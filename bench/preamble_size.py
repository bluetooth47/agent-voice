#!/usr/bin/env python3
"""How big the preamble each backend is handed is, with today's settings.

The Phase 8 baseline for prompt assembly (merged plan, Phase 11): what
`Adapter.preamble()` produces for every agent configured here, and for every
backend the registry offers with the main agent's instructions, so a later
phase can say how much it added. Sizes only -- the text is never printed,
because it holds the user's own instructions.

    python bench/preamble_size.py            # a table
    python bench/preamble_size.py --json

Tokens are estimated as characters / 4 (marked "~"): no tokenizer for every
provider is installed here, and the number is used only to compare against
itself later. What a CLI adds of its own (Claude Code's system prompt, a
plugin's skill descriptions) is outside this figure: it is not ours to shrink.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "daemon"))

import adapters  # noqa: E402
import agentfs  # noqa: E402
import omarchy_skill  # noqa: E402
import runtime  # noqa: E402
from adapters.base import Adapter, INSTRUCTIONS_HEAD, SPOKEN_STYLE  # noqa: E402
from adapters.claude_code import ClaudeCode  # noqa: E402
from adapters.cli_agent import TEMPLATES as CLI_TEMPLATES, CliAgent  # noqa: E402
from adapters.codex import Codex  # noqa: E402
from adapters.gemini import Gemini  # noqa: E402
from adapters.antigravity import Antigravity  # noqa: E402
from adapters.openai_compat import OpenAICompatible  # noqa: E402


def backends():
    """One instance of each backend, built without starting anything."""
    yield "claude", ClaudeCode()
    yield "codex", Codex()
    yield "gemini", Gemini()
    yield "agy", Antigravity()
    yield "copilot", CliAgent("copilot")
    yield "endpoint (chat)", OpenAICompatible("http://127.0.0.1:9", "m")
    yield "endpoint (agent)", OpenAICompatible("http://127.0.0.1:9", "m",
                                               is_agent=True)


def offline(program: str, endpoint: dict | None) -> Adapter | None:
    """The adapter class the daemon would use for `program`, constructed
    without checking it is installed or starting anything."""
    if program == "endpoint":
        if not endpoint:
            return None
        return OpenAICompatible(endpoint["url"], endpoint["model"],
                                is_agent=bool(endpoint.get("is_agent")))
    cls = adapters.REGISTRY.get(program)
    if cls is not None:
        return cls()
    if program in CLI_TEMPLATES:
        return CliAgent(program)
    return None


def claude_plugin() -> dict:
    """What Claude gets instead of skill text: the plugin's SKILL.md, whose
    front matter is always in context and whose body is read on demand."""
    root = omarchy_skill.plugin_dir()
    files = sorted(Path(root).glob("skills/*/SKILL.md")) if root else []
    out = {}
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            out[f.parent.name] = {"unreadable": type(e).__name__}
            continue
        parts = text.split("---", 2)
        front = parts[1] if len(parts) == 3 else ""
        out[f.parent.name] = {"front_matter_chars": len(front),
                              "file_chars": len(text)}
    return out


def size(adapter: Adapter, instructions: str, skill_text: str) -> dict:
    adapter.instructions = instructions
    adapter.skill_text = skill_text
    text = adapter.preamble()
    return {"chars": len(text), "tokens_est": round(len(text) / 4)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    cfg = runtime.Config()
    skill_on = cfg.get_bool("omarchySkill")
    skill_text = omarchy_skill.instructions() if skill_on else ""
    # Where the daemon reads them from (Phase 10): the folder's file, the old
    # setting only while that is missing.
    main_instr = agentfs.instructions_for("", cfg["agentInstructions"])

    parts = {"spoken_style": len(SPOKEN_STYLE),
             "instructions_head": len(INSTRUCTIONS_HEAD),
             "omarchy_skill_text": len(skill_text),
             "omarchy_skill_on": skill_on}

    per_backend = {name: size(ad, main_instr, skill_text)
                   for name, ad in backends()}

    per_agent = {}
    main_endpoint = cfg.main_endpoint()
    agents = [{"label": "main",
               "program": "endpoint" if main_endpoint else
               (adapters.main_program(cfg.get_str("mainProgram")) or "claude"),
               "endpoint": main_endpoint,
               "instructions": main_instr, "id": "main"}]
    for entry in cfg.agents():
        agents.append({"label": entry["id"], "id": entry["id"], "program": entry["agent"],
                       "endpoint": entry.get("endpoint"),
                       "instructions": agentfs.instructions_for(
                           entry["id"], entry.get("instructions", ""))})
    for ag in agents:
        adapter = offline(ag["program"], ag["endpoint"])
        row = {"program": ag["program"],
               "instructions_chars": len(ag["instructions"])}
        if adapter is None:
            row["unavailable"] = "no adapter for this program"
        else:
            # Without the folder pieces first (the Phase 10 preamble), then
            # with them, assigned as the daemon's reconcile_parts does.
            row["without_parts_chars"] = size(adapter, ag["instructions"], skill_text)["chars"]
            adapter.parts = agentfs.parts(ag["id"], cfg)
            row["roster_lines"] = len(adapter.parts["roster"])
            row.update(size(adapter, ag["instructions"], skill_text))
        per_agent[ag["label"]] = row

    out = {"parts": parts, "backends": per_backend, "agents": per_agent,
           "claude_plugin": claude_plugin() if skill_on else {}}
    if a.json:
        print(json.dumps(out, indent=2))
        return 0
    print("parts:", ", ".join(f"{k} {v}" for k, v in parts.items()))
    print(f"\n{'backend (main agent instructions)':34} {'chars':>6} {'~tokens':>8}")
    for name, v in per_backend.items():
        print(f"{name:34} {v['chars']:>6} {v['tokens_est']:>8}")
    print(f"\n{'agent':14} {'program':8} {'instr':>6} {'chars':>6} {'~tokens':>8} "
          f"{'no parts':>9} {'roster':>7}")
    for name, v in per_agent.items():
        if "unavailable" in v:
            print(f"{name:14} {v['program']:8} {v['instructions_chars']:>6} "
                  f"  {v['unavailable']}")
            continue
        print(f"{name:14} {v['program']:8} {v['instructions_chars']:>6} "
              f"{v['chars']:>6} {v['tokens_est']:>8} {v['without_parts_chars']:>9} "
              f"{v['roster_lines']:>7}")
    for skill, v in out["claude_plugin"].items():
        if "unreadable" in v:
            print(f"\nclaude plugin skill {skill}: unreadable ({v['unreadable']})")
            continue
        print(f"\nclaude plugin skill {skill}: front matter "
              f"{v['front_matter_chars']} chars always, file {v['file_chars']} "
              f"on demand")
    return 0


if __name__ == "__main__":
    sys.exit(main())
