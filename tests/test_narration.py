"""Progress talk: what a tool call becomes in words, and when it is said.

Every sentence comes from a real event through a fixed table, so these
tests pin the table (event -> words), the privacy filter (what is never
said), and the timing rules (silence first, growing gaps, no repeats, never
over the agent). The recorded turns in bench/narration/turns are replayed at
the end through the adapters' own parsers.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "daemon"))
sys.path.insert(0, str(ROOT / "bench" / "narration"))

import narration  # noqa: E402
from narration import Activity, Narrator, compose, describe  # noqa: E402


def said(name, args, detailed=True, helper=False):
    act = describe(name, args, detailed=detailed, helper=helper)
    if act is None:
        return None
    return compose([act], detailed).text


# --- one tool call, in words ------------------------------------------------

class TestDescribe:
    def test_a_read_names_the_file(self):
        assert said("Read", {"file_path": "/x/daemon/noise_floor.py"}) == \
            "I'm reading noise_floor.py."

    def test_the_voice_says_the_file_name_as_words(self):
        act = describe("Read", {"file_path": "/x/Panel.qml"})
        assert compose([act], True).spoken == "I'm reading Panel dot Q M L."
        assert narration.spoken_file("noise_floor.py") == "noise floor dot py"
        assert narration.spoken_file("Makefile") == "Makefile"

    def test_brief_names_the_stage_not_the_file(self):
        assert said("Read", {"file_path": "/x/a.py"}, detailed=False) == \
            "I'm reading through the files."
        assert said("Edit", {"file_path": "/x/a.py"}, detailed=False) == \
            "I'm making changes."

    def test_edits_and_writes(self):
        assert said("Edit", {"file_path": "/x/crew.py"}) == "I'm editing crew.py."
        assert said("Write", {"file_path": "/x/notes.md"}) == "I'm writing notes.md."

    def test_a_word_search_says_the_word_and_a_regex_does_not(self):
        assert said("Grep", {"pattern": "saveChats"}) == \
            "I'm searching the code for saveChats."
        assert said("Grep", {"pattern": r"def (\w+)_id\b"}) == \
            "I'm searching the code."

    def test_glob(self):
        assert said("Glob", {"pattern": "**/noise_floor.py"}) == \
            "I'm looking for noise_floor.py."
        assert said("Glob", {"pattern": "**/*.qml"}) == "I'm looking for files."

    def test_web(self):
        assert said("WebSearch", {"query": "Toronto weather today"}) == \
            "I'm searching the web for Toronto weather today."
        assert said("WebFetch", {"url": "https://www.github.com/rhasspy/piper?tab=readme"}) == \
            "I'm reading a page on github.com."

    def test_a_long_query_is_not_read_out(self):
        assert said("WebSearch", {"query": "piper text to speech latest release version github"}) == \
            "I'm searching the web."

    def test_a_helper(self):
        assert said("Task", {"description": "Explain Bash permission decisions"}) == \
            "I've started a helper to explain Bash permission decisions."
        assert said("Read", {"file_path": "/x/a.py"}, helper=True) == \
            "My helper is reading a.py."

    def test_tools_with_nothing_to_say(self):
        for name in ("TodoWrite", "ToolSearch", "AskUserQuestion"):
            assert describe(name, {}) is None

    def test_browser_and_other_mcp_tools(self):
        assert said("mcp__claude-in-chrome__navigate", {}) == "I'm using the browser."
        assert said("mcp__desktop-control__click", {}) == "I'm using desktop control."

    def test_an_unknown_tool_is_still_true(self):
        assert said("SomethingNew", {}) == "I'm using a tool."

    def test_bad_input_never_raises(self):
        for args in (None, [], "x", {"file_path": None}, {"command": 7}):
            describe("Read", args)
            describe("Bash", args)
            describe("Grep", args)


class TestCommands:
    @pytest.mark.parametrize("command, expected", [
        ("./bin/agentvoice-check 2>&1 | tail -40", "I'm running the checks."),
        ("python -m pytest -q tests", "I'm running the tests."),
        ("cd /x && pytest tests/test_crew.py", "I'm running the tests."),
        ("git status --short", "I'm checking what has changed."),
        ("git log -5 --stat", "I'm looking at the history."),
        ("pip install requests", "I'm installing packages."),
        ("sudo pacman -S python-requests", "I'm installing packages."),
        ("wc -l daemon/*.py", "I'm counting lines."),
        ("cat daemon/crew.py", "I'm reading crew.py."),
        ("sed -n 1,40p daemon/crew.py", "I'm reading crew.py."),
        ("python3 count_settings.py", "I'm running count_settings.py."),
        ("python3 -c 'print(1)'", "I'm running a short script."),
        ("FOO=1 timeout 30 make", "I'm building it."),
    ])
    def test_said_by_what_it_is_for(self, command, expected):
        assert said("Bash", {"command": command}) == expected

    def test_an_unknown_command_uses_its_description_only_in_detail(self):
        args = {"command": "frobnicate --all", "description": "Rebuild the font cache"}
        assert said("Bash", args) == "I'm running a command to rebuild the font cache."
        assert said("Bash", args, detailed=False) == "I'm running a command."

    def test_echo_alone_is_nothing(self):
        assert describe("Bash", {"command": "echo hi; sleep 1"}) is None

    def test_the_command_line_itself_is_never_said(self):
        for command in ("find . -name 'test_*.py' | xargs wc -l | sort -n",
                        "for f in tests/*.py; do grep -c def $f; done",
                        "awk '{print $2}' data.txt"):
            line = said("Bash", {"command": command, "description": ""})
            assert command not in line
            assert "|" not in line and "$" not in line and "*" not in line


# --- what is never said -----------------------------------------------------

class TestPrivacy:
    @pytest.mark.parametrize("path", [
        "/repo/.env", "/repo/.env.local", "~/.ssh/id_ed25519", "/home/u/.ssh/config",
        "/home/u/.gnupg/pubring.kbx", "/x/server.pem", "/x/deploy.key",
        "/x/credentials.json", "/x/secrets.toml", "/x/.netrc",
        "~/.local/share/agentvoice/endpoint.key", "/x/github_token.txt",
        "~/.codex/auth.json", "/x/.aws/credentials",
    ])
    def test_a_secret_file_is_a_config_file(self, path):
        for tool in ("Read", "Edit"):
            line = said(tool, {"file_path": path})
            assert "config file" in line, line
            name = path.rstrip("/").split("/")[-1]
            assert name == "config" or name not in line

    def test_a_secret_file_read_by_a_command(self):
        assert said("Bash", {"command": "cat .env"}) == "I'm reading a config file."
        assert said("Bash", {"command": "ls ~/.ssh"}) == "I'm running a command."

    @pytest.mark.parametrize("command", [
        "export OPENAI_API_KEY=sk-abc123def456 && codex",
        "curl -H 'Authorization: Bearer abc' https://x",
        "GITHUB_TOKEN=ghp_abcdefghijklmnop gh pr list",
        "secret-tool lookup service agentvoice",
    ])
    def test_a_command_that_handles_a_secret_says_nothing_of_it(self, command):
        line = said("Bash", {"command": command,
                             "description": "Set the key sk-abc123def456"})
        assert line == "I'm running a command."

    @pytest.mark.parametrize("text", [
        "sk-ant-api03-abcdefgh", "ghp_abcdefghijklmnop", "AKIAABCDEFGHIJKLMNOP",
        "a" * 40, "deadbeef" * 4, "my password", "the API key",
    ])
    def test_looks_secret(self, text):
        assert narration.looks_secret(text)

    def test_ordinary_words_do_not_look_secret(self):
        for text in ("I'm reading noise_floor.py.", "I've looked through six files.",
                     "I'm running the checks.", "test_verifier_negatives.py"):
            assert not narration.looks_secret(text), text

    def test_a_secret_query_or_pattern_is_not_read_out(self):
        assert said("Grep", {"pattern": "sk-ant-api03"}) == "I'm searching the code."
        assert said("WebSearch", {"query": "is ghp_abcdefghijklmnop valid"}) == \
            "I'm searching the web."

    def test_a_line_that_still_looks_secret_is_dropped(self):
        n = Narrator("detailed")
        act = Activity("run", "checking sk-abcdef123456", "checking sk-abcdef123456",
                       long=True)
        n.activity(act, 0.0, "t1")
        assert n.due(30.0) is None
        assert n.lines == []


# --- several activities, one line ------------------------------------------

def acts(*specs, helper=False):
    out = []
    for kind, item in specs:
        out.append(Activity(kind, item, item, helper=helper))
    return out


class TestCompose:
    def test_a_burst_is_one_line(self):
        reads = acts(*[("read", f"f{i}.py") for i in range(6)])
        for a in reads:
            a.done = True
        assert compose(reads, True).text == "I've looked through six files."

    def test_one_is_singular(self):
        mixed = acts(("run", "counting lines"), ("run", "using git"), ("read", "a.py"))
        for a in mixed:
            a.done = True
        assert compose(mixed, True).text == "I've run two commands and looked through one file."

    def test_at_most_two_kinds_in_the_order_they_happened(self):
        mixed = acts(("search", "x"), ("read", "a"), ("read", "b"), ("read", "c"),
                     ("run", "y"), ("run", "z"), ("find", ""))
        for a in mixed:
            a.done = True
        assert compose(mixed, True).text == \
            "I've looked through three files and run two commands."

    def test_a_long_command_still_running_is_told_as_it_is(self):
        mixed = acts(("read", "a.py"), ("read", "b.py"))
        for a in mixed:
            a.done = True
        mixed.append(Activity("run", "running the tests", "running the tests", long=True))
        assert compose(mixed, True).text == "I'm running the tests."

    def test_a_helpers_work_is_the_helpers(self):
        started = Activity("helper", "review chats", "review chats", long=True)
        work = acts(("read", "a.py"), ("read", "b.py"), ("search", "x"), helper=True)
        for a in work:
            a.done = True
        assert compose([started, *work], True).text == \
            "My helper has looked through two files and searched the code once."


# --- when -------------------------------------------------------------------

def running(n, kind="run", item="running the tests", t=0.0, tool_id="t1", long=True):
    n.activity(Activity(kind, item, item, long=long), t, tool_id)


class TestTiming:
    def test_nothing_before_the_silence(self):
        n = Narrator("brief")
        running(n)
        assert n.due(6.9) is None
        assert n.due(7.0).text == "I'm running the tests."

    def test_the_silence_counts_from_the_last_thing_said(self):
        n = Narrator("brief")
        n.agent_said("Okay.", until=3.0)
        running(n, t=3.1)
        assert n.due(9.9) is None
        assert n.due(10.0) is not None

    def test_nothing_while_the_agent_writes(self):
        n = Narrator("brief")
        running(n)
        n.text()
        assert n.due(30.0) is None

    def test_a_new_tool_after_words_opens_it_again(self):
        n = Narrator("brief")
        n.text()
        running(n, t=1.0)
        assert n.due(8.0) is not None

    def test_nothing_between_tools(self):
        # Every tool has returned: the model is writing, maybe the answer.
        n = Narrator("brief")
        running(n)
        n.finished("t1")
        assert n.due(30.0) is None

    def test_the_gaps_grow(self):
        n = Narrator("detailed", silence_s=1.0)
        kinds = [("read", "a.py"), ("search", "foo"), ("read", "b.py"),
                 ("web_search", "x y"), ("find", "c.py"), ("edit", "d.py")]
        times = []
        t = 0.0
        for i, (kind, item) in enumerate(kinds):
            n.activity(Activity(kind, item, item), t, f"t{i}")
            while n.due(t) is None:
                t += 0.25
                assert t < 300
            times.append(t)
            n.spoke(t + 2.0)
            n.finished(f"t{i}")
        gaps = [b - a for a, b in zip(times, times[1:])]
        assert gaps[0] >= 10.0
        assert gaps[1] >= 15.0
        assert all(g >= 25.0 for g in gaps[2:])

    def test_never_the_same_line_twice(self):
        n = Narrator("brief", silence_s=0.0, gaps_s=(0.0,))
        running(n, tool_id="a")
        assert n.due(0.0) is not None
        n.finished("a")
        running(n, kind="search", item="x", tool_id="b", t=1.0)
        assert n.due(1.0) is not None
        n.finished("b")
        running(n, tool_id="c", t=2.0)
        assert n.due(2.0) is None

    def test_more_of_the_same_kind_is_not_news(self):
        n = Narrator("brief", silence_s=0.0, gaps_s=(0.0,))
        n.activity(Activity("read", "a.py", "a.py"), 0.0, "a")
        assert n.due(0.0) is not None
        n.finished("a")
        n.activity(Activity("read", "b.py", "b.py"), 1.0, "b")
        assert n.due(5.0) is None

    def test_a_burst_is_waited_for(self):
        n = Narrator("detailed", silence_s=0.0)
        n.activity(Activity("read", "a.py", "a.py"), 10.0, "a")
        n.activity(Activity("read", "b.py", "b.py"), 10.5, "b")
        assert n.due(11.0) is None
        n.activity(Activity("read", "c.py", "c.py"), 11.0, "c")
        assert n.due(13.0).text == "I've looked through three files."

    def test_not_what_the_agent_just_said(self):
        n = Narrator("brief")
        n.agent_said("Running the project's check script now.", until=3.0)
        running(n, item="running the checks", t=3.5)
        assert n.due(20.0) is None

    def test_off_says_nothing(self):
        n = Narrator("off")
        running(n)
        assert n.due(60.0) is None

    def test_a_tool_not_worth_a_word_still_ends_the_talking(self):
        n = Narrator("brief")
        n.text()
        n.activity(None, 1.0, "q")
        assert not n.talking


# --- the adapters ------------------------------------------------------------

class TestAdapters:
    def test_claude_gives_the_arguments_and_the_return(self):
        from adapters.claude_code import parse_line
        msg = {"type": "assistant", "parent_tool_use_id": None, "message": {
            "content": [{"type": "tool_use", "id": "toolu_1", "name": "Read",
                         "input": {"file_path": "/x/a.py"}}]}}
        [chunk] = parse_line(msg)
        assert chunk.activity == {"name": "Read", "input": {"file_path": "/x/a.py"},
                                  "id": "toolu_1", "helper": False}
        done = {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "toolu_1", "content": "x"}]}}
        assert [c.tool_done for c in parse_line(done)] == ["toolu_1"]

    def test_claude_marks_a_helpers_tools(self):
        from adapters.claude_code import parse_line
        msg = {"type": "assistant", "parent_tool_use_id": "toolu_task", "message": {
            "content": [{"type": "tool_use", "id": "t2", "name": "Grep",
                         "input": {"pattern": "x"}}]}}
        assert parse_line(msg)[0].activity["helper"] is True

    def test_claude_text_is_not_an_activity(self):
        from adapters.claude_code import parse_line
        msg = {"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}
        assert parse_line(msg) == []
        assert parse_line({"type": "user", "message": {"content": "a prompt"}}) == []

    def test_codex_announces_each_item_once_and_its_end(self):
        from adapters.codex import activity_chunks
        seen: set[str] = set()
        item = {"id": "item_1", "type": "command_execution", "command": "git status"}
        first = activity_chunks("item.started", item, seen)
        again = activity_chunks("item.updated", item, seen)
        end = activity_chunks("item.completed", item, seen)
        assert [c.activity["name"] for c in first] == ["command_execution"]
        assert again == []
        assert [c.tool_done for c in end] == ["item_1"]
        line = said("command_execution", first[0].activity["input"])
        assert line == "I'm checking what has changed."

    def test_codex_file_change_has_only_a_completion(self):
        from adapters.codex import activity_chunks
        item = {"id": "item_2", "type": "file_change",
                "changes": [{"path": "/x/agents_panel.py", "kind": "update"}]}
        chunks = activity_chunks("item.completed", item, set())
        assert chunks[0].activity["name"] == "file_change"
        assert said("file_change", chunks[0].activity["input"]) == \
            "I'm editing agents_panel.py."

    def test_codex_messages_are_not_activities(self):
        from adapters.codex import activity_chunks
        item = {"id": "i", "type": "agent_message", "text": "hello"}
        assert activity_chunks("item.completed", item, set()) == []


# --- the recorded turns ------------------------------------------------------

TURNS = sorted((ROOT / "bench" / "narration" / "turns").glob("*.jsonl"))


@pytest.mark.skipif(not TURNS, reason="no recorded turns in bench/narration/turns")
class TestRecordedTurns:
    """The corpus, through the adapters' parsers and the narrator."""

    def test_every_tool_call_in_a_recording_reaches_the_narrator(self):
        from adapters.claude_code import parse_line
        for path in TURNS:
            lines = path.read_text().splitlines()
            head = json.loads(lines[0])
            if head["backend"] != "claude":
                continue
            blocks = acts_ = 0
            for raw in lines[1:]:
                msg = json.loads(raw)["msg"]
                if msg.get("type") == "assistant":
                    blocks += sum(1 for b in msg["message"]["content"]
                                  if b.get("type") == "tool_use")
                acts_ += sum(1 for c in parse_line(msg) if c.activity)
            assert acts_ == blocks, path.name

    @pytest.mark.parametrize("level", ["brief", "detailed"])
    def test_the_targets(self, level):
        import replay
        totals = {"repeats": 0, "invented": 0, "secrets": 0}
        for path in TURNS:
            probs = replay.Turn(path, level).problems()
            for k in totals:
                totals[k] += probs[k]
        assert totals == {"repeats": 0, "invented": 0, "secrets": 0}

    def test_the_secret_file_is_never_named(self):
        import replay
        path = ROOT / "bench" / "narration" / "turns" / "c09.jsonl"
        if not path.exists():
            pytest.skip("c09 not recorded")
        for level in ("brief", "detailed"):
            for line in replay.Turn(path, level).narrator.lines:
                assert ".env" not in line.text and "sk-" not in line.text


# --- the reply loop ------------------------------------------------------------

class TestTicker:
    def test_quiet_gives_ticks_and_chunks_pass_through(self):
        import time as _time

        from adapters.base import Chunk
        from wake_listen import TICK, Ticker

        def slow():
            yield Chunk(text="a")
            _time.sleep(0.3)
            yield Chunk(text="b")

        got = list(Ticker(slow(), every=0.05))
        texts = [c.text for c in got if c is not TICK]
        assert texts == ["a", "b"]
        assert any(c is TICK for c in got)

    def test_an_error_in_the_stream_reaches_the_reader(self):
        from wake_listen import Ticker

        def broken():
            raise RuntimeError("boom")
            yield  # pragma: no cover

        with pytest.raises(RuntimeError):
            list(Ticker(broken(), every=0.05))

    def test_words_waiting(self):
        import threading

        from adapters.base import Chunk
        from wake_listen import Ticker

        gate = threading.Event()

        def stream():
            yield Chunk(text="the answer")
            gate.wait(2)

        t = Ticker(stream(), every=0.05)
        for _ in range(40):
            if t.words_waiting():
                break
            gate.wait(0.05)
        assert t.words_waiting()
        gate.set()
        list(t)

    def test_left_mid_turn_the_agent_is_cancelled(self):
        import threading

        from adapters.base import Chunk
        from wake_listen import Ticker

        gate = threading.Event()
        cancelled = []

        def stream():
            yield Chunk(text="first")
            gate.wait(5)            # a turn still going

        t = Ticker(stream(), every=0.05, on_abandon=lambda: (cancelled.append(1), gate.set()))
        for c in t:
            if c.text:
                break
        assert cancelled == [1]

    def test_left_at_the_end_nothing_is_cancelled(self):
        from adapters.base import Chunk
        from wake_listen import Ticker

        cancelled = []
        t = Ticker(iter([Chunk(error="x"), Chunk(done=True)]), every=0.05,
                   on_abandon=lambda: cancelled.append(1))
        for c in t:
            if c.error:
                break
        assert cancelled == []


class WorkingAgent:
    """Says a word, runs the tests for a moment, then answers."""

    def __init__(self, pause=0.8):
        self.pause = pause
        self.cancelled = 0

    def send(self, text, session_id=None):
        import time as _time

        from adapters.base import Chunk
        yield Chunk(session_id="s1")
        yield Chunk(text="One moment. ")
        yield Chunk(tool="Bash")
        yield Chunk(activity={"name": "Bash", "input": {"command": "pytest -q"},
                              "id": "t1", "helper": False})
        _time.sleep(self.pause)
        yield Chunk(tool_done="t1")
        yield Chunk(text="All of them passed.")

    def cancel(self):
        self.cancelled += 1


class TestReplyLoop:
    def test_a_progress_line_is_said_while_a_tool_runs(self, daemon):
        daemon.agent = WorkingAgent()
        daemon.cfg._values["narration"] = "brief"
        daemon.cfg.narration_silence_s = lambda: 0.1
        daemon.answer("run the tests", {"transcript": "run the tests"})
        said = daemon.speaker.said
        assert said[0] == "One moment."
        assert "I'm running the tests." in said
        assert said[-1] == "All of them passed."
        assert said.index("I'm running the tests.") < said.index("All of them passed.")

    def test_it_is_not_part_of_the_reply(self, daemon, tmp_path):
        from runtime import History
        daemon.history = History(tmp_path / "h.jsonl")
        daemon.cfg._values["keepHistory"] = True
        daemon.agent = WorkingAgent()
        daemon.cfg._values["narration"] = "brief"
        daemon.cfg.narration_silence_s = lambda: 0.1
        daemon.answer("run the tests", {"transcript": "run the tests"})
        row = json.loads(daemon.history.path.read_text().splitlines()[-1])
        assert "running the tests" not in row["reply"]

    def test_off_says_nothing_extra(self, daemon):
        daemon.agent = WorkingAgent(pause=0.3)
        daemon.cfg._values["narration"] = "off"
        daemon.answer("run the tests", {"transcript": "x"})
        assert daemon.speaker.said == ["One moment.", "All of them passed."]

    def test_an_agents_own_choice_wins(self, cfg_factory):
        cfg = cfg_factory(narration="brief")
        assert cfg.narration(None) == "brief"
        assert cfg.narration({"narration": "off"}) == "off"
        assert cfg.narration({"narration": ""}) == "brief"
        assert cfg.narration({"narration": "loud"}) == "brief"
        assert cfg_factory(narration="nonsense").narration() == "off"

    def test_the_silence_is_clamped(self, cfg_factory):
        assert cfg_factory(narrationSilenceS=0).narration_silence_s() == 3
        assert cfg_factory(narrationSilenceS=99).narration_silence_s() == 30
        assert cfg_factory(narrationSilenceS="x").narration_silence_s() == 7

    def test_a_card_choice_keeps_the_conversation(self):
        import inspect

        from wake_listen import Daemon
        src = inspect.getsource(Daemon._rebuild_persona)
        assert '"narration"' in src
