"""bin/agentvoice: what the full test run found (testresults.md)."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "bin/agentvoice"


def run(*args, runtime: Path):
    env = {**os.environ, "XDG_RUNTIME_DIR": str(runtime)}
    return subprocess.run(["bash", str(CLI), *args], capture_output=True,
                          text=True, env=env, timeout=20)


def test_an_answer_to_no_question_is_refused_and_leaves_nothing(tmp_path):
    import cardhelp
    with cardhelp.live_desk(tmp_path):
        out = cardhelp.cli(tmp_path, "permit", "deadbeef0000", "deny")
    assert out.returncode == 1 and "no question" in out.stderr
    assert not list(tmp_path.rglob("*.response"))


def test_a_terminal_can_say_no(tmp_path):
    import cardhelp
    with cardhelp.live_desk(tmp_path) as desk:
        t, card = cardhelp.post_async(desk, {"tool": "Bash", "summary": "ls"})
        out = cardhelp.cli(tmp_path, "permit", card["id"], "deny")
        t.join(5)
    assert out.returncode == 0, out.stderr
    assert card["answer"]["allow"] is False
    assert not list(tmp_path.rglob("*.response"))


def test_a_terminal_cannot_say_yes_and_trying_denies(tmp_path):
    """Phase M7: `agentvoice permit ID allow` from anywhere but the overlay
    -- an agent's shell, a terminal -- is refused, and the question it tried
    to answer is denied rather than left for somebody else to allow."""
    import cardhelp
    with cardhelp.live_desk(tmp_path) as desk:
        t, card = cardhelp.post_async(desk, {"tool": "Bash", "summary": "ls"})
        shown = json.loads(cardhelp.cli(tmp_path, "pending", card["id"]).stdout)
        out = cardhelp.cli(tmp_path, "permit", card["id"], "allow",
                           stdin=json.dumps({"digest": shown["digest"]}) + "\n")
        t.join(5)
    assert out.returncode == 1
    assert "not started by the Omarchy shell" in out.stderr
    assert card["answer"]["allow"] is False
    assert "could not be checked" in card["answer"]["reason"]


def test_the_nonce_never_travels_in_argv():
    body = re.search(r"^  permit\)\n(.*?)\n    ;;", CLI.read_text(), re.M | re.S).group(1)
    exec_line = [ln for ln in body.splitlines() if ln.strip().startswith("exec ")]
    assert exec_line and all("nonce" not in ln for ln in exec_line)
    assert 'cards.py" answer "$id" "$verdict"' in body


def test_the_usage_line_names_every_command():
    text = CLI.read_text()
    commands = set(re.findall(r"^  ([a-z][a-z-]*)\)", text, re.M))
    usage = re.search(r'echo "usage: agentvoice \[([^\]]+)\]"', text).group(1).split("|")
    assert commands - set(usage) == set(), commands - set(usage)


def test_a_start_clears_systemds_start_limit_first():
    block = re.search(r"^  start\)\n(.*?)\n    ;;", CLI.read_text(), re.M | re.S).group(1)
    assert block.index("reset-failed") < block.index("systemctl --user start")
