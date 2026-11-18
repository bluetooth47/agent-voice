"""bin/agentvoice: what the full test run found (testresults.md)."""
from __future__ import annotations

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
    pending = tmp_path / "agentvoice/permissions"
    pending.mkdir(parents=True)
    out = run("permit", "deadbeef0000", "allow", runtime=tmp_path)
    assert out.returncode == 1 and "no question" in out.stderr
    assert list(pending.iterdir()) == []


def test_a_waiting_question_gets_its_answer(tmp_path):
    pending = tmp_path / "agentvoice/permissions"
    pending.mkdir(parents=True)
    (pending / "abcdef012345.request").write_text("{}")
    out = run("permit", "abcdef012345", "deny", runtime=tmp_path)
    assert out.returncode == 0
    assert '"allow":false' in (pending / "abcdef012345.response").read_text()


def test_the_usage_line_names_every_command():
    text = CLI.read_text()
    commands = set(re.findall(r"^  ([a-z][a-z-]*)\)", text, re.M))
    usage = re.search(r'echo "usage: agentvoice \[([^\]]+)\]"', text).group(1).split("|")
    assert commands - set(usage) == set(), commands - set(usage)


def test_a_start_clears_systemds_start_limit_first():
    block = re.search(r"^  start\)\n(.*?)\n    ;;", CLI.read_text(), re.M | re.S).group(1)
    assert block.index("reset-failed") < block.index("systemctl --user start")
