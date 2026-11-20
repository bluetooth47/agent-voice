#!/usr/bin/env python3
"""Cold and warm start of a Claude turn and a Codex turn, through the adapters.

The Phase 8 baseline that Phases 15 and 16 are budgeted against (a task turn
or a quiet side turn may have to start a CLI cold). Each turn goes through
the real adapter, at the agent's own permission level (an Ask agent keeps its
hook, a Codex agent below Trusted keeps --guard), with the extras the daemon
would give it here (desktop tools, Chrome, the Omarchy skill), in an empty
scratch folder rather than the agent's project, with a prompt that needs no
tool:

    python bench/start_bench.py               # 5 of each
    python bench/start_bench.py --runs 3 --only claude
    python bench/start_bench.py --agent main --runs 20   # as an agent here

`--agent` builds the adapter as the daemon builds that agent (`main` or an
extra agent's id): its program, model, effort and standing instructions, so
the preamble it is handed is the real one. This is the controlled number the
Phase 11 gate compares against; the journal (`turn_latency.py`) is the
real-use one, and too varied to show 150ms.

Timed from `send()` to the first chunk carrying text. "cold" builds a new
adapter per turn, so the CLI starts for that turn; "warm" (Claude only) lets
`prepare()` start the process first and waits for it, which is what the
daemon does while you are still talking. Codex has no warm process in this
app: every turn is a fresh `codex exec`, so its "resume" row is a fresh
process continuing the session the first turn made.

Known limit: an interrupt in the middle of a Codex turn can leave that
`codex exec` running, because the adapter drops its handle while unwinding;
check `pgrep codex` after a Ctrl-C. Costs one short model call per turn. Prints timings only. An agent with
standing instructions has them written to a private prompt file under
$XDG_RUNTIME_DIR by the Claude adapter, exactly as a daemon turn does.
"""
from __future__ import annotations

import argparse
import json
import signal
import statistics
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "daemon"))

import adapters  # noqa: E402
import agentfs  # noqa: E402
import omarchy_skill  # noqa: E402
import runtime  # noqa: E402
from adapters.claude_code import ClaudeCode  # noqa: E402
from adapters.codex import Codex  # noqa: E402

PROMPT = "Reply with the single word OK and nothing else."


def first_text(adapter, session=None):
    """Seconds to the first text chunk, and the session id the turn reported.

    A turn that ends in an error, or with no text at all, counts as a
    failure (None) even if some text arrived first, and its session id is
    not returned, so nothing resumes a turn that did not finish."""
    t0 = time.monotonic()
    first, sid, failed = None, session, False
    for chunk in adapter.send(PROMPT, session_id=session):
        if chunk.session_id:
            sid = chunk.session_id
        if chunk.error:
            failed = True
        if first is None and chunk.text:
            first = time.monotonic() - t0
    if failed or first is None:
        return None, None
    return first, sid


def extras(ad, cfg):
    """What the daemon's apply_extras gives an adapter, from the same keys."""
    if hasattr(ad, "desktop_tools"):
        ad.desktop_tools = cfg.get_bool("desktopTools")
    if hasattr(ad, "browser_tools"):
        ad.browser_tools = cfg.get_bool("browserTools")
    skill_on = cfg.get_bool("omarchySkill")
    if hasattr(ad, "skill_dir"):
        ad.skill_dir = omarchy_skill.plugin_dir() if skill_on else None
    if ad.takes_skill_text and ad.has_tools:
        ad.skill_text = omarchy_skill.instructions() if skill_on else ""


def build(spec, cfg, cwd):
    """The adapter as the daemon builds this agent (wake_listen.py
    _build_persona / reconcile_agent): its own level, so an Ask agent keeps
    its hook and Codex keeps --guard; its id for the hook; its instructions."""
    level = spec["level"]
    cls = ClaudeCode if spec["program"] == "claude" else Codex
    kw = {"model": spec["model"], "effort": spec["effort"], "cwd": cwd,
          "ask_permission": level != "trusted", "named": spec["named"]}
    ad = cls(**kw)
    if level in getattr(ad, "levels", ()):
        ad.level = level
    ad.instructions = spec["instructions"]
    extras(ad, cfg)
    return ad


def claude_turn(spec, cfg, cwd, warm):
    ad = build(spec, cfg, cwd)
    try:
        if warm:
            ad.prepare()
            # A head start, not a readiness check: system/init arrives in
            # about 1s (FINDINGS 19). A run the adapter still calls "cold"
            # is reported apart from the warm ones.
            time.sleep(6)
        secs, _ = first_text(ad)
        return secs, ad.last_start
    finally:
        ad.cancel()


def codex_turn(spec, cfg, cwd, session=None):
    ad = build(spec, cfg, cwd)
    try:
        return first_text(ad, session)
    finally:
        ad.cancel()


def stats(xs):
    ok = [x for x in xs if x is not None]
    out = {"attempts": len(xs), "failed": len(xs) - len(ok), "n": len(ok)}
    if not ok:
        return out
    s = sorted(ok)
    p95 = s[max(0, -(-95 * len(s) // 100) - 1)]  # nearest rank
    return {**out, "median": round(statistics.median(ok), 2),
            "p95": round(p95, 2), "min": round(min(ok), 2),
            "max": round(max(ok), 2), "runs": [round(x, 3) for x in ok]}


def agent_spec(cfg, agent):
    """program, model, effort, level, instructions and hook id for `agent`."""
    if agent == "main":
        if cfg.main_endpoint():
            raise SystemExit("the main agent is an endpoint; not timed here")
        program = adapters.main_program(cfg.get_str("mainProgram"))
        if not program:
            raise SystemExit("the main agent has no program; nothing to time")
        return {"program": program, "model": cfg.model_for(program),
                "effort": cfg.effort_for(program),
                "level": cfg.level_for(program), "named": "",
                "instructions": agentfs.instructions_for("", cfg["agentInstructions"])}
    entry = next((e for e in cfg.agents() if e["id"] == agent), None)
    if entry is None:
        raise SystemExit(f"no enabled agent with id {agent!r}")
    return {"program": entry["agent"], "model": entry["model"] or None,
            "effort": entry["effort"] or None, "level": entry["level"],
            "named": entry["id"],
            "instructions": agentfs.instructions_for(entry["id"], entry["instructions"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--only", choices=("claude", "codex"))
    ap.add_argument("--claude-model", default="haiku")
    ap.add_argument("--codex-model", default=None)
    ap.add_argument("--codex-effort", default="medium")
    ap.add_argument("--level", default="ask", choices=("ask", "edits", "trusted"),
                    help="without --agent: the level to run at (default ask)")
    ap.add_argument("--agent", help="main, or an extra agent's id")
    a = ap.parse_args(argv)
    cfg = runtime.Config()
    # SIGTERM runs the finally blocks too, so no CLI is left behind.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    if a.agent:
        spec = agent_spec(cfg, a.agent)
        if spec["program"] not in ("claude", "codex"):
            ap.error(f"{spec['program']} is not timed here")
        specs = {spec["program"]: spec}
    else:
        base = {"level": a.level, "named": "", "instructions": ""}
        specs = {"claude": {**base, "program": "claude",
                            "model": a.claude_model, "effort": None},
                 "codex": {**base, "program": "codex",
                           "model": a.codex_model, "effort": a.codex_effort}}
        if a.only:
            specs = {a.only: specs[a.only]}
    out = {}
    with tempfile.TemporaryDirectory(prefix="av-start-") as cwd:
        if "claude" in specs:
            spec = specs["claude"]
            for kind in ("cold", "warm"):
                xs, fallback = [], 0
                for _ in range(a.runs):
                    secs, how = claude_turn(spec, cfg, cwd, kind == "warm")
                    if kind == "warm" and how != "warm":
                        fallback += 1  # reported, never pooled with warm
                        continue
                    xs.append(secs)
                row = stats(xs)
                row["attempts"] += fallback  # every turn sent, fallbacks too
                out[f"claude {spec['model']} {spec['level']} {kind}"] = {
                    **row, "fell_back_to_cold": fallback}
        if "codex" in specs:
            spec = specs["codex"]
            fresh, resumed = [], []
            for _ in range(a.runs):
                secs, sid = codex_turn(spec, cfg, cwd)
                fresh.append(secs)
                if sid:
                    r, _ = codex_turn(spec, cfg, cwd, sid)
                    resumed.append(r)
            label = (f"codex {spec['model'] or 'default'} {spec['effort']} "
                     f"{spec['level']}")
            out[f"{label} fresh"] = stats(fresh)
            out[f"{label} resume"] = stats(resumed)
    if a.agent:
        out = {f"{a.agent}: {k}": v for k, v in out.items()}
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
