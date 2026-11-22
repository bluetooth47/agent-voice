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
    python bench/start_bench.py --agent sora --runs 20 --variants none,folders,full

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


def extras(ad, cfg, named=""):
    """What the daemon's apply_extras gives an adapter: since Phase 13 this
    agent's own tool switches (else the settings for every agent) and its
    plugin folder, built from the folders exactly as the daemon builds it."""
    tools = cfg.tools_for(named)
    if hasattr(ad, "desktop_tools"):
        ad.desktop_tools = tools["desktop"]
    if hasattr(ad, "browser_tools"):
        ad.browser_tools = tools["browser"]
    skill_on = tools["omarchySkill"]
    if hasattr(ad, "skill_dir"):
        ad.skill_dir = agentfs.plugin_dir(named or "main",
                                          omarchy_skill.plugin_dir() if skill_on else None)
    if ad.takes_skill_text and ad.has_tools:
        ad.skill_text = omarchy_skill.instructions() if skill_on else ""


#: The preamble variants --variants can interleave (Phase 11 gate):
#: "none" is the Phase 10 preamble (no folder pieces), "folders" is what
#: the daemon's reconcile_parts assigns from the agent folders now, and
#: "full" fills every budget with synthetic text -- rules, defaults,
#: personality and instructions to their limits, and eight roster lines of
#: 380 characters -- the most the folders can ever add.
VARIANTS = ("none", "folders", "full", "skills", "nocrew", "loose", "strict", "strict3")
#: Phase M10: "loose" is "folders" without --strict-mcp-config, the argv
#: before M10, under which Claude Code also starts every server in the
#: user's own settings and the project's .mcp.json; "strict" is "folders"
#: as the daemon starts it now with nothing found switched on; "strict3"
#: adds three found servers switched on (bench/stub_mcp.py, which answers
#: and does nothing), so what a switch costs is measured on any machine.
STUB_MCP = Path(__file__).resolve().with_name("stub_mcp.py")
#: "nocrew" (Phase 14) is "folders" without the notes server, which since
#: Phase 14 every Claude and Codex agent is started with: the Phase 13
#: argv, to interleave against "folders" for the cost of one more server.
#: "skills" (Phase 13 gate, A13-4) is "folders" plus three synthetic
#: communal skills of a realistic size, beside whatever skills the agent
#: already has: Claude is handed a plugin folder holding them all with the
#: Omarchy skill, any other backend their index. They are made in a scratch
#: data folder (the real skills copied in), so no real agent sees them.
SKILL_BODY = ("Synthetic skill for timing only. " * 90).strip()


def synthetic_skills(omarchy_root, me="main"):
    """(plugin folder, index) for agent `me`: its own and the communal
    skills as they are, plus three synthetic communal ones, made once in a
    scratch data folder that agentfs is pointed at only while it builds."""
    import shutil
    import paths
    scratch = Path(tempfile.mkdtemp(prefix="av-skills-"))
    real = {me: paths.AGENTS_DIR / me / "skills", "communal": paths.COMMUNAL_DIR / "skills"}
    saved = paths.DATA_DIR, paths.AGENTS_DIR, paths.COMMUNAL_DIR
    paths.DATA_DIR, paths.AGENTS_DIR, paths.COMMUNAL_DIR = (
        scratch, scratch / "agents", scratch / "communal")
    try:
        for target, src in real.items():
            dest = (paths.COMMUNAL_DIR if target == "communal" else paths.AGENTS_DIR / me) / "skills"
            if src.is_dir() and not src.is_symlink():
                shutil.copytree(src, dest, symlinks=True)   # a link stays one, and is refused
        for n in ("timing-one", "timing-two", "timing-three"):
            d = paths.COMMUNAL_DIR / "skills" / n
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(
                f"---\nname: {n}\ndescription: A synthetic skill used only to time a turn; "
                f"it is never the right one to use for any request.\n---\n\n{SKILL_BODY}\n")
        folder = agentfs.plugin_dir(me, omarchy_root)
        index = agentfs.skills_index(agentfs.skill_set(agentfs.skills(me), agentfs.skills("communal")))
    finally:
        paths.DATA_DIR, paths.AGENTS_DIR, paths.COMMUNAL_DIR = saved
    return folder, index


_SYNTHETIC = {}


def _filler(n: int, word: str) -> str:
    """Exactly `n` characters of `word` repeated, ending in a full stop."""
    return (f"{word} " * (n // (len(word) + 1) + 1))[:n - 1] + "."


def full_parts(name: str) -> dict:
    return {"rules": _filler(1500, "rule"), "defaults": _filler(1500, "default"),
            "personality": _filler(1500, "calm"), "name": name,
            "roster": [_filler(380, f"agent{i}") for i in range(agentfs.ROSTER_MAX)]}


def assign_parts(ad, spec, cfg, variant):
    """Give the adapter the folder pieces as the daemon would, or the
    synthetic full set, or none."""
    if variant in ("folders", "skills"):
        ad.parts = agentfs.parts(spec["named"] or "main", cfg)
        if variant == "skills":
            root = (omarchy_skill.plugin_dir()
                    if cfg.tools_for(spec["named"])["omarchySkill"] else None)
            me = spec["named"] or "main"
            if (root, me) not in _SYNTHETIC:
                _SYNTHETIC[(root, me)] = synthetic_skills(root, me)
            folder, index = _SYNTHETIC[(root, me)]
            if hasattr(ad, "skill_dir"):
                ad.skill_dir = folder
            ad.parts = {**ad.parts, "skills": index}
    elif variant == "full":
        ad.parts = full_parts(spec.get("label") or spec["named"] or "main")
        ad.instructions = _filler(runtime.INSTRUCTIONS_MAX, "brief")
    else:
        ad.parts = None


def build(spec, cfg, cwd, variant="folders"):
    """The adapter as the daemon builds this agent (wake_listen.py
    _build_persona / reconcile_agent): its own level, so an Ask agent keeps
    its hook and Codex keeps --guard; its id for the hook; its instructions;
    and, since Phase 11, its folder pieces (`variant`)."""
    level = spec["level"]
    cls = ClaudeCode if spec["program"] == "claude" else Codex
    kw = {"model": spec["model"], "effort": spec["effort"], "cwd": cwd,
          "ask_permission": level != "trusted", "named": spec["named"]}
    ad = cls(**kw)
    if level in getattr(ad, "levels", ()):
        ad.level = level
    ad.instructions = spec["instructions"]
    extras(ad, cfg, spec["named"])
    assign_parts(ad, spec, cfg, "folders" if variant in ("nocrew", "loose", "strict", "strict3")
                 else variant)
    if variant == "nocrew":
        ad.crew_tools = False
    if variant == "loose" and hasattr(ad, "detected_servers"):
        real = ad._argv
        ad._argv = lambda text, sid: [w for w in real(text, sid) if w != "--strict-mcp-config"]
    if variant == "strict3" and hasattr(ad, "detected_servers"):
        ad.detected_servers = {f"timing-{i}": {"command": sys.executable,
                                               "args": ["-I", str(STUB_MCP), f"timing-{i}"]}
                               for i in range(3)}
    return ad


def claude_turn(spec, cfg, cwd, warm, variant="folders"):
    ad = build(spec, cfg, cwd, variant)
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


def codex_turn(spec, cfg, cwd, session=None, variant="folders"):
    ad = build(spec, cfg, cwd, variant)
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
                "label": cfg.main_label(cfg.get_str("phrase").lower()),
                "instructions": agentfs.instructions_for("", cfg["agentInstructions"])}
    entry = next((e for e in cfg.agents() if e["id"] == agent), None)
    if entry is None:
        raise SystemExit(f"no enabled agent with id {agent!r}")
    return {"program": entry["agent"], "model": entry["model"] or None,
            "effort": entry["effort"] or None, "level": entry["level"],
            "named": entry["id"], "label": entry["label"],
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
    ap.add_argument("--variants", default="folders",
                    help="comma-separated preamble variants, interleaved run "
                         "by run so drift cancels: " + ", ".join(VARIANTS))
    ap.add_argument("--kinds", default="cold,warm",
                    help="Claude only: cold, warm or both (default both)")
    a = ap.parse_args(argv)
    variants = [v.strip() for v in a.variants.split(",") if v.strip()]
    if not variants or any(v not in VARIANTS for v in variants):
        ap.error(f"--variants takes {', '.join(VARIANTS)}")
    kinds = [k.strip() for k in a.kinds.split(",") if k.strip()]
    if not kinds or any(k not in ("cold", "warm") for k in kinds):
        ap.error("--kinds takes cold, warm")
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
            for kind in kinds:
                xs = {v: [] for v in variants}
                fallback = {v: 0 for v in variants}
                for _ in range(a.runs):
                    for v in variants:      # interleaved: drift hits each alike
                        secs, how = claude_turn(spec, cfg, cwd, kind == "warm", v)
                        if kind == "warm" and how != "warm":
                            fallback[v] += 1  # reported, never pooled with warm
                            continue
                        xs[v].append(secs)
                for v in variants:
                    row = stats(xs[v])
                    row["attempts"] += fallback[v]  # every turn sent, fallbacks too
                    tag = "" if variants == ["folders"] else f" [{v}]"
                    out[f"claude {spec['model']} {spec['level']} {kind}{tag}"] = {
                        **row, "fell_back_to_cold": fallback[v]}
        if "codex" in specs:
            spec = specs["codex"]
            fresh = {v: [] for v in variants}
            resumed = {v: [] for v in variants}
            for _ in range(a.runs):
                for v in variants:
                    secs, sid = codex_turn(spec, cfg, cwd, variant=v)
                    fresh[v].append(secs)
                    if sid:
                        r, _ = codex_turn(spec, cfg, cwd, sid, variant=v)
                        resumed[v].append(r)
            label = (f"codex {spec['model'] or 'default'} {spec['effort']} "
                     f"{spec['level']}")
            for v in variants:
                tag = "" if variants == ["folders"] else f" [{v}]"
                out[f"{label} fresh{tag}"] = stats(fresh[v])
                out[f"{label} resume{tag}"] = stats(resumed[v])
    if a.agent:
        out = {f"{a.agent}: {k}": v for k, v in out.items()}
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
