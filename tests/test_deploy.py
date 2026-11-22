"""bin/agentvoice-deploy: the only way the plugin folder changes (bug H).

Each test builds a throwaway "clone" and a "plugin folder" cloned from it
under a temporary HOME, with stub check, installer and `agentvoice` commands,
and runs the real deploy script against them. Nothing here touches the real
plugin folder or needs anything beyond git and bash.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DEPLOY = REPO / "bin" / "agentvoice-deploy"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

CHECK_STUB = '#!/usr/bin/env bash\nexit "${STUB_CHECK_EXIT:-0}"\n'
INSTALL_STUB = '#!/usr/bin/env bash\ntouch "$HOME/installed"\n'


def _git(cwd, *args, env):
    return subprocess.run(["git", "-C", str(cwd), *args], env=env, check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def world(tmp_path):
    home = tmp_path / "home"
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "agentvoice").write_text(
        '#!/usr/bin/env bash\n[[ $1 == status ]] && cat "$HOME/state.json"\n')
    (stubs / "agentvoice").chmod(0o755)
    env = {
        "HOME": str(home), "PATH": f"{stubs}:{os.environ['PATH']}",
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
        "GIT_CONFIG_NOSYSTEM": "1", "XDG_STATE_HOME": str(home / "state"),
    }
    home.mkdir()
    (home / "state.json").write_text('{"state": "listening", "live": {"": "idle"}}')
    clone = tmp_path / "dev"
    (clone / "bin").mkdir(parents=True)
    shutil.copy(DEPLOY, clone / "bin" / "agentvoice-deploy")
    (clone / "bin" / "agentvoice-check").write_text(CHECK_STUB)
    (clone / "install.sh").write_text(INSTALL_STUB)
    for f in ("bin/agentvoice-check", "install.sh"):
        (clone / f).chmod(0o755)
    (clone / "Panel.qml").write_text("Item {}\n")
    (clone / "notes.md").write_text("one\n")
    _git(tmp_path, "init", "-q", "-b", "dev", str(clone), env=env)
    _git(clone, "add", "-A", env=env)
    _git(clone, "commit", "-qm", "first", env=env)
    plugin = home / ".config/omarchy/plugins/duaneoca.agentvoice"
    plugin.parent.mkdir(parents=True)
    _git(tmp_path, "clone", "-q", str(clone), str(plugin), env=env)

    class W:
        pass
    w = W()
    w.env, w.clone, w.plugin, w.home = env, clone, plugin, home

    def commit(path, text, msg):
        (clone / path).write_text(text)
        _git(clone, "commit", "-qam", msg, env=env)
        return _git(clone, "rev-parse", "HEAD", env=env)

    def deploy(*args, script=None, **extra):
        return subprocess.run(
            [str(script or clone / "bin" / "agentvoice-deploy"), *args],
            env={**env, **extra}, capture_output=True, text=True,
            stdin=subprocess.DEVNULL)

    def head():
        return _git(plugin, "rev-parse", "HEAD", env=env)

    w.commit, w.deploy, w.head = commit, deploy, head
    w.first = _git(clone, "rev-parse", "HEAD", env=env)
    return w


def test_a_commit_is_checked_out_detached_and_the_way_back_is_printed(world):
    sha = world.commit("notes.md", "two\n", "second")
    r = world.deploy("--no-install")
    assert r.returncode == 0, r.stderr
    assert world.head() == sha
    assert _git(world.plugin, "rev-parse", "--abbrev-ref", "HEAD", env=world.env) == "HEAD"
    assert f"bin/agentvoice-deploy {world.first[:12]}" in r.stdout
    assert "QML changed" not in r.stdout
    log = (world.home / "state/agentvoice/deploys.log").read_text().split("\t")
    assert log[1:3] == [world.first, sha]
    assert not (world.home / "installed").exists()


def test_a_qml_change_asks_for_a_shell_restart_and_never_runs_it(world):
    world.commit("Panel.qml", "Item { id: x }\n", "qml")
    r = world.deploy("--no-install")
    assert r.returncode == 0, r.stderr
    assert "QML changed: run omarchy-restart-shell?" in r.stdout


def test_going_back_deploys_an_older_commit(world):
    world.commit("notes.md", "two\n", "second")
    assert world.deploy("--no-install").returncode == 0
    r = world.deploy("--no-install", world.first[:7])
    assert r.returncode == 0, r.stderr
    assert world.head() == world.first
    # the older commit was checked in a worktree that is gone again
    assert _git(world.clone, "worktree", "list", env=world.env).count("\n") == 0


@pytest.mark.parametrize("dirt", ["modified", "untracked"])
def test_a_dirty_clone_is_refused(world, dirt):
    world.commit("notes.md", "two\n", "second")
    if dirt == "modified":
        (world.clone / "notes.md").write_text("edited\n")
    else:
        (world.clone / "scratch.txt").write_text("x\n")
    r = world.deploy("--no-install")
    assert r.returncode == 1
    assert "uncommitted or untracked" in r.stderr
    assert world.head() == world.first


def test_a_red_check_is_refused(world):
    world.commit("notes.md", "two\n", "second")
    r = world.deploy("--no-install", STUB_CHECK_EXIT="1")
    assert r.returncode == 1
    assert "the check is red" in r.stderr
    assert world.head() == world.first


def test_a_red_check_on_an_older_commit_is_refused(world):
    world.commit("notes.md", "two\n", "second")
    assert world.deploy("--no-install").returncode == 0
    r = world.deploy("--no-install", world.first, STUB_CHECK_EXIT="1")
    assert r.returncode == 1 and "red on" in r.stderr
    assert world.head() != world.first


def test_it_refuses_to_run_from_inside_the_plugins_folder(world):
    world.commit("notes.md", "two\n", "second")
    r = world.deploy("--no-install", script=world.plugin / "bin" / "agentvoice-deploy",
                     AGENTVOICE_PLUGIN_DIR=str(world.clone))
    assert r.returncode == 1
    assert "this is the plugin folder" in r.stderr


def test_local_edits_in_the_plugin_folder_are_not_trampled(world):
    world.commit("notes.md", "two\n", "second")
    (world.plugin / "notes.md").write_text("edited in place\n")
    r = world.deploy("--no-install")
    assert r.returncode == 1 and "local edits" in r.stderr
    assert (world.plugin / "notes.md").read_text() == "edited in place\n"
    assert world.head() == world.first


def test_install_runs_from_the_plugin_folder_once_idle(world):
    world.commit("notes.md", "two\n", "second")
    r = world.deploy("--install")
    assert r.returncode == 0, r.stderr
    assert (world.home / "installed").exists()


@pytest.mark.parametrize("state", [
    '{"state": "speaking", "live": {"": "busy"}}',
    '{"state": "listening", "live": {"": "idle", "sora": "working"}}',
])
def test_install_waits_for_a_busy_daemon_and_gives_up(world, state):
    (world.home / "state.json").write_text(state)
    sha = world.commit("notes.md", "two\n", "second")
    r = world.deploy("--install", "--wait", "0")
    assert r.returncode == 1 and "stayed busy" in r.stderr
    assert world.head() == sha                  # deployed, just not installed
    assert not (world.home / "installed").exists()


def test_dry_run_changes_nothing(world):
    world.commit("notes.md", "two\n", "second")
    r = world.deploy("--dry-run")
    assert r.returncode == 0 and "dry run" in r.stdout
    assert world.head() == world.first
