"""bin/agentvoice-deploy: the only way the plugin folder changes (bug H).

Each test builds a throwaway "clone" and a "plugin folder" cloned from it
under a temporary HOME, with stub check, installer, `agentvoice`,
`systemctl` and `omarchy-restart-shell` commands that record how they were
called, and runs the real deploy script against them. Nothing here touches
the real plugin folder or needs anything beyond git, bash and flock.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DEPLOY = REPO / "bin" / "agentvoice-deploy"

pytestmark = pytest.mark.skipif(
    not (shutil.which("git") and shutil.which("flock")), reason="needs git and flock")

MANIFEST = '{"id": "duaneoca.agentvoice"}\n'
# Records which commit was checked, and from where.
CHECK_STUB = ('#!/usr/bin/env bash\necho "$(git rev-parse HEAD) $PWD" >> "$HOME/checked"\n'
              'exit "${STUB_CHECK_EXIT:-0}"\n')
INSTALL_STUB = '#!/usr/bin/env bash\necho "$PWD $(git rev-parse HEAD) $*" >> "$HOME/installed"\n'
# `agentvoice status`: prints $HOME/state.json, or, while $HOME/busy-polls
# counts down, a busy state; exits 1 if $HOME/status-fails exists.
AGENTVOICE_STUB = '''#!/usr/bin/env bash
[[ $1 == status ]] || exit 0
[[ -e $HOME/status-fails ]] && exit 1
n=$(cat "$HOME/busy-polls" 2>/dev/null || echo 0)
if (( n > 0 )); then
  echo $((n - 1)) > "$HOME/busy-polls"
  echo '{"state": "speaking", "live": {"": "busy"}}'
else
  cat "$HOME/state.json"
fi
'''
SYSTEMCTL_STUB = '#!/usr/bin/env bash\n[[ -e $HOME/service-active ]]\n'
RESTART_STUB = '#!/usr/bin/env bash\ntouch "$HOME/restarted"\n'


def _git(cwd, *args, env):
    return subprocess.run(["git", "-C", str(cwd), *args], env=env, check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def world(tmp_path):
    home = tmp_path / "home"
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name, body in (("agentvoice", AGENTVOICE_STUB), ("systemctl", SYSTEMCTL_STUB),
                       ("omarchy-restart-shell", RESTART_STUB)):
        (stubs / name).write_text(body)
        (stubs / name).chmod(0o755)
    env = {
        "HOME": str(home), "PATH": f"{stubs}:{os.environ['PATH']}",
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
        "GIT_CONFIG_NOSYSTEM": "1", "XDG_STATE_HOME": str(home / "state"),
        "AGENTVOICE_PYTHON": "/bin/true",
    }
    home.mkdir()
    (home / "state.json").write_text('{"state": "listening", "live": {"": "idle"}}')
    (home / "service-active").touch()
    clone = tmp_path / "dev"
    (clone / "bin").mkdir(parents=True)
    shutil.copy(DEPLOY, clone / "bin" / "agentvoice-deploy")
    (clone / "bin" / "agentvoice-check").write_text(CHECK_STUB)
    (clone / "install.sh").write_text(INSTALL_STUB)
    for f in ("bin/agentvoice-check", "install.sh"):
        (clone / f).chmod(0o755)
    (clone / "manifest.json").write_text(MANIFEST)
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
    w.env, w.clone, w.plugin, w.home, w.tmp = env, clone, plugin, home, tmp_path

    def commit(path, text, msg, repo=clone):
        (repo / path).write_text(text)
        _git(repo, "commit", "-qam", msg, env=env)
        return _git(repo, "rev-parse", "HEAD", env=env)

    def deploy(*args, script=None, **extra):
        return subprocess.run(
            [str(script or clone / "bin" / "agentvoice-deploy"), *args],
            env={**env, **extra}, capture_output=True, text=True,
            stdin=subprocess.DEVNULL, timeout=60)

    def head():
        return _git(plugin, "rev-parse", "HEAD", env=env)

    def lines(name):
        p = home / name
        return p.read_text().splitlines() if p.exists() else []

    w.commit, w.deploy, w.head, w.lines = commit, deploy, head, lines
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
    assert not world.lines("installed")


def test_the_check_runs_on_that_commit_outside_the_clone_and_the_plugins(world):
    sha = world.commit("notes.md", "two\n", "second")
    assert world.deploy("--no-install").returncode == 0
    [(checked, where)] = [ln.split(" ", 1) for ln in world.lines("checked")]
    assert checked == sha
    assert not where.startswith(str(world.clone) + "/") and where != str(world.clone)
    assert "/.config/omarchy/plugins" not in where
    assert not Path(where).exists()                       # the worktree is gone
    assert _git(world.clone, "worktree", "list", env=world.env).count("\n") == 0


def test_a_qml_change_asks_for_a_shell_restart_and_never_runs_it(world):
    world.commit("Panel.qml", "Item { id: x }\n", "qml")
    r = world.deploy("--no-install")
    assert r.returncode == 0, r.stderr
    assert "QML changed: run omarchy-restart-shell?" in r.stdout
    assert not (world.home / "restarted").exists()


def test_going_back_checks_and_deploys_the_older_commit(world):
    world.commit("notes.md", "two\n", "second")
    assert world.deploy("--no-install").returncode == 0
    r = world.deploy("--no-install", world.first[:7])
    assert r.returncode == 0, r.stderr
    assert world.head() == world.first
    assert world.lines("checked")[-1].split()[0] == world.first


def test_the_way_back_works_for_a_commit_only_the_plugin_folder_has(world):
    local = world.commit("notes.md", "made in place\n", "local only", repo=world.plugin)
    world.commit("Panel.qml", "Item { id: y }\n", "new")
    r = world.deploy("--no-install")
    assert r.returncode == 0, r.stderr
    assert f"bin/agentvoice-deploy {local[:12]}" in r.stdout
    r = world.deploy("--no-install", local[:12])
    assert r.returncode == 0, r.stderr
    assert world.head() == local


@pytest.mark.parametrize("dirt", ["modified", "untracked", "untracked, hidden by config"])
def test_a_dirty_clone_is_refused(world, dirt):
    world.commit("notes.md", "two\n", "second")
    if dirt == "modified":
        (world.clone / "notes.md").write_text("edited\n")
    else:
        (world.clone / "scratch.txt").write_text("x\n")
    if "config" in dirt:
        _git(world.clone, "config", "status.showUntrackedFiles", "no", env=world.env)
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


def test_it_refuses_to_deploy_into_the_clone_itself(world):
    world.commit("notes.md", "two\n", "second")
    r = world.deploy("--no-install", AGENTVOICE_PLUGIN_DIR=str(world.clone))
    assert r.returncode == 1 and "overlap" in r.stderr


def test_a_folder_inside_another_repository_is_refused(world):
    outer = world.tmp / "dotfiles"
    (outer / "agentvoice").mkdir(parents=True)
    (outer / "agentvoice" / "manifest.json").write_text(MANIFEST)
    _git(world.tmp, "init", "-q", str(outer), env=world.env)
    _git(outer, "add", "-A", env=world.env)
    _git(outer, "commit", "-qm", "dotfiles", env=world.env)
    before = _git(outer, "rev-parse", "HEAD", env=world.env)
    world.commit("notes.md", "two\n", "second")
    r = world.deploy("--no-install", AGENTVOICE_PLUGIN_DIR=str(outer / "agentvoice"))
    assert r.returncode == 1 and "not a checkout of its own" in r.stderr
    assert _git(outer, "rev-parse", "HEAD", env=world.env) == before


def test_a_checkout_of_some_other_plugin_is_refused(world):
    world.commit("manifest.json", '{"id": "someone.else"}\n', "other", repo=world.plugin)
    world.commit("notes.md", "two\n", "second")
    r = world.deploy("--no-install")
    assert r.returncode == 1 and "does not hold" in r.stderr


def test_local_edits_in_the_plugin_folder_are_not_trampled(world):
    world.commit("notes.md", "two\n", "second")
    (world.plugin / "notes.md").write_text("edited in place\n")
    r = world.deploy("--no-install")
    assert r.returncode == 1 and "local edits" in r.stderr
    assert (world.plugin / "notes.md").read_text() == "edited in place\n"
    assert world.head() == world.first


def test_a_stray_module_the_installer_would_copy_is_refused(world):
    world.commit("notes.md", "two\n", "second")
    (world.plugin / "daemon").mkdir()
    (world.plugin / "daemon" / "extra.py").write_text("x = 1\n")
    r = world.deploy("--no-install")
    assert r.returncode == 1 and "install.sh would install" in r.stderr
    assert world.head() == world.first


def test_install_waits_for_idle_then_runs_once_from_the_plugin_folder(world):
    (world.home / "busy-polls").write_text("2")
    sha = world.commit("notes.md", "two\n", "second")
    r = world.deploy("--install", "--wait", "30")
    assert r.returncode == 0, r.stderr
    assert "waiting for the daemon" in r.stdout
    assert world.lines("installed") == [f"{world.plugin} {sha} --yes"]


def test_install_runs_when_the_service_is_not_running(world):
    (world.home / "service-active").unlink()
    (world.home / "status-fails").touch()
    world.commit("notes.md", "two\n", "second")
    assert world.deploy("--install").returncode == 0
    assert len(world.lines("installed")) == 1


@pytest.mark.parametrize("state", [
    '{"state": "speaking", "live": {"": "busy"}}',
    '{"state": "listening", "live": {"": "idle", "sora": "working"}}',
    '{"state": "off"}',                          # the CLI's answer when it cannot read the state
    '{"state": "listening", "live": {"": "idle"}, "tasks": [{"state": "pending"}]}',
    '{"state": "dreaming", "live": {"": "idle"}}',
    'not json',
    None,                                        # the status command fails
])
def test_install_refuses_anything_not_clearly_idle(world, state):
    if state is None:
        (world.home / "status-fails").touch()
    else:
        (world.home / "state.json").write_text(state)
    sha = world.commit("notes.md", "two\n", "second")
    r = world.deploy("--install", "--wait", "0")
    assert r.returncode == 1 and "stayed busy" in r.stderr
    assert world.head() == sha                  # deployed, just not installed
    assert not world.lines("installed")


def test_finished_tasks_do_not_block_the_install(world):
    (world.home / "state.json").write_text(
        '{"state": "listening", "live": {"": "idle"}, "tasks": [{"state": "completed"}]}')
    world.commit("notes.md", "two\n", "second")
    assert world.deploy("--install", "--wait", "0").returncode == 0
    assert len(world.lines("installed")) == 1


def test_retrying_an_install_after_a_timeout_installs_and_detaches(world):
    (world.home / "state.json").write_text('{"state": "thinking", "live": {"": "busy"}}')
    sha = world.commit("notes.md", "two\n", "second")
    assert world.deploy("--install", "--wait", "0").returncode == 1
    (world.home / "state.json").write_text('{"state": "listening", "live": {"": "idle"}}')
    r = world.deploy("--install", "--wait", "0")
    assert r.returncode == 0, r.stderr
    assert world.lines("installed") == [f"{world.plugin} {sha} --yes"]


def test_a_plugin_folder_on_a_branch_at_the_same_commit_is_detached(world):
    r = world.deploy("--no-install")
    assert r.returncode == 0, r.stderr
    assert _git(world.plugin, "rev-parse", "--abbrev-ref", "HEAD", env=world.env) == "HEAD"


@pytest.mark.parametrize("value, ok", [("08", True), ("abc", False), ("", False)])
def test_wait_takes_decimal_seconds(world, value, ok):
    r = world.deploy("--dry-run", "--wait", value)
    assert (r.returncode == 0) == ok, r.stderr


def test_dry_run_changes_nothing(world):
    world.commit("notes.md", "two\n", "second")
    r = world.deploy("--dry-run")
    assert r.returncode == 0 and "dry run" in r.stdout
    assert world.head() == world.first
    assert not world.lines("checked")
