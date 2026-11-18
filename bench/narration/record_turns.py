#!/usr/bin/env python3
"""Record real agent turns, with the time each line arrived, for narration.

Progress talk has to be written from what an agent actually emits, and timed
against how fast it actually emits it, so the corpus is real turns rather
than invented ones. Each turn runs in a throwaway clone of this repository,
so an edit the agent makes lands nowhere that matters.

    python bench/narration/record_turns.py                # every missing turn
    python bench/narration/record_turns.py --only c07 x02  # these again
    python bench/narration/record_turns.py --list

Output: bench/narration/turns/<id>.jsonl. The first line is a header
({"id", "backend", "model", "prompt", "recorded"}); every line after it is
{"t": milliseconds since the prompt was sent, "msg": the CLI's JSON line}.

What is kept is cut down to what narration reads, so the corpus can live in
the repository: the init line keeps only its session id and model, rate-limit
lines (account details) and streamed tool-argument fragments are dropped,
tool results are cut to 400 characters,
and every path is rewritten relative to the clone or the home directory.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
TURNS = HERE / "turns"
sys.path.insert(0, str(REPO / "daemon"))

from adapters.base import SPOKEN_STYLE  # noqa: E402

#: id, backend, what was asked. Phrased the way people talk to it, and chosen
#: to cover every kind of activity narration has to describe: reading,
#: searching, commands short and long, edits, the web, a subagent, a secret
#: file, a denied command, and a turn with no tools at all.
PROMPTS = [
    ("c01", "claude", "How many test files are there, and which one is the biggest?"),
    ("c02", "claude", "Where is the wake word threshold set? Just tell me the file and the default."),
    ("c03", "claude", "What changed in the last five commits?"),
    ("c04", "claude", "Run the checks and tell me whether they pass."),
    ("c05", "claude", "Search the web for the latest Piper text to speech release and tell me the version."),
    ("c06", "claude", "Explain what noise_floor.py does, in two sentences."),
    ("c07", "claude", "Find every place the code reads the saveChats setting."),
    ("c08", "claude", "Add a docstring to the slug function in agents_panel.py."),
    ("c09", "claude", "What's in the .env file?"),
    ("c10", "claude", "Look through the tests folder and tell me which parts of the daemon have the fewest tests."),
    ("c11", "claude", "Use a subagent to find out how the permission hook decides on Bash commands, then summarize it for me."),
    ("c12", "claude", "Fetch the README of github.com/rhasspy/piper and tell me which platforms it supports."),
    ("c13", "claude", "Count the lines of Python in the daemon folder."),
    ("c14", "claude", "Is there any TODO or FIXME left in the code?"),
    ("c15", "claude", "Rename tools_seen to seen_tools in the codex adapter and make sure nothing else uses the old name."),
    ("c16", "claude", "Which QML files are the largest, and what does each one do?"),
    ("c17", "claude", "Check git status and tell me if anything is uncommitted."),
    ("c18", "claude", "Read CLAUDE.md and tell me the rules about settings."),
    ("c19", "claude", "Which Python version does the agentvoice venv use?"),
    ("c20", "claude", "Look at bench/FINDINGS.md and tell me the most recent wake word numbers."),
    ("c21", "claude", "Write a small script that counts the settings in manifest.json, run it, and tell me the count."),
    ("c22", "claude", "What's the weather like in Toronto today?"),
    ("c23", "claude", "Review daemon/chats.py for any obvious bugs."),
    ("c24", "claude", "Hi, how are you doing today?"),
    ("c25", "claude", "Install the requests package into the system Python."),
    # Longer jobs. The short questions above mostly finish inside the seven
    # seconds before progress talk would say anything. c26 and c27 were
    # recorded on Claude Code's default model; the 5-hour limit cut the rest
    # short, and they were recorded again on Sonnet. c30 and c32 are not
    # recorded yet.
    ("c26", "claude", "Add a test for a display name with tabs inside it to the agent name tests, run that test file, and tell me if it passes.", "sonnet"),
    ("c27", "claude", "Find out whether the saved chats list could ever show the same chat twice, and fix it if there's a bug.", "sonnet"),
    ("c28", "claude", "Compare Piper, Kokoro and Coqui XTTS for local text to speech on a laptop CPU. Search the web and give me a recommendation.", "sonnet"),
    ("c29", "claude", "Add a new setting called narrationLevel with the choices off, brief and detailed, following the repo rules for settings, and run the checks.", "sonnet"),
    ("c30", "claude", "Go through every adapter and tell me which ones handle a watchdog timeout, and whether any are missing it.", "sonnet"),
    ("c31", "claude", "Run the full test suite, and if anything fails, figure out why.", "sonnet"),
    ("c32", "claude", "Summarize sections 20 to 28 of bench/FINDINGS.md into a new file called findings-summary.md.", "sonnet"),
    ("c33", "claude", "Use two subagents in parallel, one to review chats.py and one to review crew.py, then tell me the most important finding from each.", "sonnet"),
    ("x01", "codex", "How many test files are there, and which one is the biggest?"),
    ("x02", "codex", "What changed in the last five commits?"),
    ("x03", "codex", "Explain what daemon/noise_floor.py does, in two sentences."),
    ("x04", "codex", "Count the lines of Python in the daemon folder."),
    ("x05", "codex", "Add a docstring to the slug function in daemon/agents_panel.py."),
]

#: What Claude may run without asking. Anything else is denied, and the
#: denial is recorded too -- c25 is there to produce one.
CLAUDE_ALLOWED = [
    "Read", "Grep", "Glob", "Edit", "Write", "WebSearch", "WebFetch", "Task",
    "Bash(git *)", "Bash(ls *)", "Bash(wc *)", "Bash(find *)", "Bash(cat *)",
    "Bash(grep *)", "Bash(rg *)", "Bash(head *)", "Bash(tail *)",
    "Bash(python3 *)", "Bash(./bin/agentvoice-check*)",
    "Bash(~/.local/share/agentvoice/venv/bin/python *)",
]

#: A file the agent is asked about in c09. Fake, and shaped like a real one,
#: so the recording shows what a read of a secret looks like on the stream.
FAKE_ENV = "AGENTVOICE_ENDPOINT_KEY=sk-test-0000000000000000\nDEBUG=1\n"

RESULT_MAX = 400
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


def clone(where: Path) -> Path:
    dest = where / "agentvoice"
    subprocess.run(["git", "clone", "-q", str(REPO), str(dest)], check=True)
    (dest / ".env").write_text(FAKE_ENV)
    return dest


def scrub(value, clone_dir: str, home: str):
    """Paths made relative, recursively, so no recording names this machine."""
    if isinstance(value, str):
        value = value.replace(clone_dir, "<repo>")
        value = _EMAIL.sub("<email>", value)    # git log prints authors
        return value.replace(home, "~")
    if isinstance(value, list):
        return [scrub(v, clone_dir, home) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v, clone_dir, home) for k, v in value.items()}
    return value


def trim(msg: dict) -> dict | None:
    """The line as narration needs it, or None to drop it."""
    kind = msg.get("type")
    if kind == "rate_limit_event":
        return None
    if kind == "stream_event":
        # A tool's arguments arrive whole in the `assistant` line; the
        # fragments streamed before it are most of a recording's size.
        delta = (msg.get("event") or {}).get("delta") or {}
        if delta.get("type") in ("input_json_delta", "thinking_delta",
                                 "signature_delta"):
            return None
    if kind == "system" and msg.get("subtype") == "init":
        return {"type": "system", "subtype": "init",
                "session_id": msg.get("session_id"), "model": msg.get("model")}
    if kind == "result":
        return {k: msg.get(k) for k in
                ("type", "subtype", "is_error", "duration_ms", "num_turns",
                 "session_id", "stop_reason")}
    if kind == "user":
        content = (msg.get("message") or {}).get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    body = block.get("content")
                    if not isinstance(body, str):
                        body = json.dumps(body)
                    block["content"] = body[:RESULT_MAX]
        msg.pop("tool_use_result", None)
    return msg


def run(argv, prompt: str, cwd: Path, stdin_json: bool) -> list[dict]:
    proc = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, bufsize=1, start_new_session=True)
    t0 = time.monotonic()
    if stdin_json:
        proc.stdin.write(json.dumps({
            "type": "user", "message": {"role": "user", "content": prompt},
            "parent_tool_use_id": None, "session_id": ""}) + "\n")
    else:
        proc.stdin.write(prompt)
    proc.stdin.close()
    lines = []
    deadline = t0 + 600
    for raw in proc.stdout:
        t = round((time.monotonic() - t0) * 1000)
        raw = raw.strip()
        if not raw.startswith("{"):
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        lines.append({"t": t, "msg": msg})
        if msg.get("type") == "result" or time.monotonic() > deadline:
            break
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
    return lines


def record(pid: str, backend: str, prompt: str, model: str) -> Path:
    with tempfile.TemporaryDirectory(prefix="narration-") as tmp:
        repo = clone(Path(tmp))
        if backend == "claude":
            argv = ["claude", "-p", "--input-format", "stream-json",
                    "--output-format", "stream-json",
                    "--include-partial-messages", "--verbose",
                    "--permission-mode", "acceptEdits",
                    "--setting-sources", "project",
                    "--append-system-prompt", SPOKEN_STYLE,
                    "--model", model,
                    "--allowedTools", *CLAUDE_ALLOWED]
            lines = run(argv, prompt, repo, stdin_json=True)
        else:
            argv = ["codex", "exec", "--json", "--skip-git-repo-check",
                    "-s", "workspace-write"]
            lines = run(argv, SPOKEN_STYLE + "\n\n" + prompt, repo,
                        stdin_json=False)
        home = str(Path.home())
        out = []
        for entry in lines:
            msg = trim(entry["msg"])
            if msg is not None:
                out.append({"t": entry["t"],
                            "msg": scrub(msg, str(repo), home)})
    TURNS.mkdir(parents=True, exist_ok=True)
    path = TURNS / f"{pid}.jsonl"
    header = {"id": pid, "backend": backend,
              "model": model if backend == "claude" else "codex default",
              "prompt": prompt, "recorded": time.strftime("%Y-%m-%d")}
    with open(path, "w") as f:
        f.write(json.dumps(header) + "\n")
        for entry in out:
            f.write(json.dumps(entry) + "\n")
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)
    if args.list:
        for pid, backend, prompt, *_ in PROMPTS:
            done = "done" if (TURNS / f"{pid}.jsonl").exists() else "    "
            print(f"{pid} {backend:6} {done} {prompt}")
        return 0
    for pid, backend, prompt, *model in PROMPTS:
        if args.only is not None and pid not in args.only:
            continue
        if args.only is None and (TURNS / f"{pid}.jsonl").exists():
            continue
        t = time.monotonic()
        path = record(pid, backend, prompt, model[0] if model else args.model)
        n = sum(1 for _ in open(path)) - 1
        print(f"{pid}: {n} lines in {time.monotonic() - t:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
