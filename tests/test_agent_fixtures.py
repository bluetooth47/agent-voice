"""The Phase 8 agent fixtures describe what today's code really does.

`tests/fixtures/agents/*.json` are synthetic settings and chats shaped like
the real machine and its edge cases (merged plan, Phase 8). Phases 9 and 10
build the agent folders and the migration against them, and each file's
`expect` block says which folders a migration must make and what each must
hold. This suite checks those expectations against the *current* reader,
`runtime.Config`, so a fixture cannot quietly describe an id resolution or an
instruction clean-up the code does not perform. Since Phase 10 the
same expectations are the migration's acceptance checks, in
test_agentfs_migrate.py.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from chats import ChatStore
from runtime import (_AGENT_ID, _AGENT_NAME, INSTRUCTIONS_MAX, agent_id_for,
                     instructions_text)

FIXTURES = Path(__file__).parent / "fixtures" / "agents"
ALL = sorted(FIXTURES.glob("*.json"))


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def raw_entry(settings: dict, agent_id: str) -> dict:
    """The saved entry `Config` accepted for an id, disabled ones included.

    Walks the list the way `Config._agents` does -- a bad or repeated name is
    skipped, and so is a second claim on an id -- so a row `Config` rejected
    is never the one checked."""
    seen_names, seen_ids = set(), set()
    for entry in settings.get("voiceAgents", []):
        if not isinstance(entry, dict):
            continue
        name = " ".join(str(entry.get("name") or "").lower().split())
        if (len(name) > 32 or not _AGENT_NAME.fullmatch(name)
                or name in seen_names):
            continue
        seen_names.add(name)
        raw = entry.get("id") if isinstance(entry.get("id"), str) else ""
        rid = raw.strip()
        if not _AGENT_ID.fullmatch(rid) or rid == "main":
            rid = agent_id_for(name)
        if rid in seen_ids:
            continue
        seen_ids.add(rid)
        if rid == agent_id:
            return entry
    raise AssertionError(f"no accepted entry resolves to {agent_id!r}")


def test_there_are_fixtures_for_every_case_the_plan_names():
    names = {p.stem for p in ALL}
    assert {"main-with-instructions", "main-without-instructions",
            "three-agents", "disabled-agent", "no-stored-id", "mangled-id",
            "empty-instructions", "instructions-at-limit", "unicode",
            "saved-chats"} <= names


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.stem)
def test_live_and_disabled_ids(path, cfg_factory):
    fx = load(path)
    cfg = cfg_factory(**fx["settings"])
    assert [a["id"] for a in cfg.agents()] == fx["expect"]["live"]
    assert cfg.disabled_agents() == set(fx["expect"]["disabled"])


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.stem)
def test_one_folder_per_agent_and_every_folder_name_is_an_id(path, cfg_factory):
    fx = load(path)
    cfg = cfg_factory(**fx["settings"])
    folders = set(fx["expect"]["folders"])
    want = {"main"} | {a["id"] for a in cfg.agents()} | cfg.disabled_agents()
    assert folders == want
    for name in folders:
        assert _AGENT_ID.fullmatch(name), name
        assert "/" not in name and ".." not in name


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.stem)
def test_instruction_lengths_and_details(path, cfg_factory):
    fx = load(path)
    settings = fx["settings"]
    cfg = cfg_factory(**settings)
    live = {a["id"]: a for a in cfg.agents()}
    for folder, want in fx["expect"]["folders"].items():
        if folder == "main":
            got = instructions_text(cfg["agentInstructions"])
        elif folder in live:
            got = live[folder]["instructions"]
        else:
            got = instructions_text(raw_entry(settings, folder)
                                    .get("instructions"))
        if "instructions_chars" in want:
            assert len(got) == want["instructions_chars"], folder
        if "instructions" in want:
            # The exact cleaned text: a length alone would pass a tab kept
            # and a character dropped.
            assert got == want["instructions"], folder
        if "raw_chars" in want:
            raw = (settings["agentInstructions"] if folder == "main"
                   else raw_entry(settings, folder)["instructions"])
            assert len(raw) == want["raw_chars"] == len(got)
        if want.get("oversize"):
            raw = raw_entry(settings, folder)["instructions"]
            assert len(raw) > INSTRUCTIONS_MAX == len(got)
        if folder in live:
            for key in ("level", "label", "name"):
                if key in want:
                    assert live[folder][key] == want[key], (folder, key)
            if "program" in want:
                assert live[folder]["agent"] == want["program"]
        if want.get("enabled") is False:
            assert folder in cfg.disabled_agents()


def test_saved_chats_use_the_empty_id_for_the_main_agent():
    fx = load(FIXTURES / "saved-chats.json")
    ids = [c["id"] for c in fx["chats"]]
    assert len(ids) == len(set(ids))
    # Every chat is mapped to a folder, so the mapping cannot pass by being
    # empty, and the one translation the plan allows is "" -> main.
    assert set(fx["expect"]["chat_folders"]) == set(ids)
    for chat in fx["chats"]:
        assert re.fullmatch(r"[0-9a-f]{16}", chat["id"])
        assert (chat["agent_id"] or "main") == fx["expect"]["chat_folders"][chat["id"]]
    assert any(c["agent_id"] == "" for c in fx["chats"])
    assert not any(c["agent_id"] == "main" for c in fx["chats"])


def test_saved_chats_are_shaped_as_the_real_writer_writes_them(tmp_path):
    """Each fixture chat, written again through ChatStore.record with the
    same values, comes back equal apart from its random id and title -- and,
    from Phase 15, the shared-chat fields the writer adds beside the old
    ones (owner, participants, sessions, each exchange's speaker), which an
    older reader ignores; from M19, `instant_title`, the same text as the
    title it was made with. Every old field keeps its old value."""
    fx = load(FIXTURES / "saved-chats.json")
    store = ChatStore(tmp_path / "chats")
    for chat in fx["chats"]:
        ex = chat["exchanges"][0]
        new_id = store.record(chat_id=None, agent_id=chat["agent_id"],
                              agent_label=chat["agent_label"],
                              backend=chat["backend"],
                              session_id=chat["session_id"],
                              project_dir=chat["project_dir"],
                              exchange={k: ex[k] for k in
                                        ("transcript", "reply", "error",
                                         "stopped")},
                              now=chat["started"])
        written = store.load(new_id)
        assert written.pop("instant_title") == written["title"]
        for key in ("id", "title"):
            written.pop(key)
        owner = chat["agent_id"] or "main"
        assert written.pop("owner") == owner
        assert written.pop("participants") == [owner]
        assert written.pop("sessions") == {owner: {
            "backend": chat["backend"], "session_id": chat["session_id"],
            "project_dir": chat["project_dir"]}}
        for e in written["exchanges"]:
            assert e.pop("agent_id") == owner
            assert e.pop("agent_label") == chat["agent_label"]
        want = {k: v for k, v in chat.items() if k not in ("id", "title")}
        assert written == want


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.stem)
def test_fixtures_hold_nothing_from_the_real_machine(path):
    text = path.read_text(encoding="utf-8").lower()
    # The real agents' wake names and the real Codex id stay out of the repo.
    for real in ("theo", "sora", "hazel", "jarvis", "/home/"):
        assert real not in text, real
