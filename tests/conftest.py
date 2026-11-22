"""Shared fixtures.

daemon/paths.py resolves its locations from the environment at import time,
so the XDG variables are redirected here -- before conftest imports anything
from the package -- and every test then runs against a scratch directory
instead of the developer's real one. A test that writes to
~/.local/share/agentvoice would be a bug in the test, not a feature.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SANDBOX = Path(tempfile.mkdtemp(prefix="agentvoice-tests-"))

for var in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_RUNTIME_DIR", "XDG_STATE_HOME"):
    d = _SANDBOX / var.lower()
    d.mkdir(parents=True, exist_ok=True)
    os.environ[var] = str(d)

sys.path.insert(0, str(ROOT / "daemon"))

# paths.SHELL_JSON is computed at import time, so redirecting the XDG
# variables above only works for modules imported after it -- runtime has
# already captured the value. Rebound here, because without it the suite
# reads the developer's own settings: the permission tests then pass or fail
# according to whatever level happens to be set on the machine, which is how
# a `decide()` that answered "allow" to `rm -rf /` got a green run.
import runtime  # noqa: E402

runtime.SHELL_JSON = _SANDBOX / "shell.json"

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_sound_server(monkeypatch):
    """Where the sound is going is a fact about the machine running the
    suite, so no test asks it. Barge-in on a headset is on by default, and
    without this every refresh() a test drives would spawn the developer's
    own pactl -- passing or failing by whether their headphones were on.
    test_headset keeps a reference to the real function for its own cases."""
    import headset
    monkeypatch.setattr(headset, "default_output", lambda: None)


@pytest.fixture(autouse=True)
def _no_recorder_probe(monkeypatch):
    """Whether another program is recording is a fact about the machine
    running the suite too. A command found inside a sentence asks before it
    fires (phase M4, `Daemon.recording_elsewhere`), and without this every
    such test would run the developer's pw-dump -- passing or failing by
    whether they were dictating. test_commands keeps the real methods."""
    import wake_listen
    monkeypatch.setattr(wake_listen.Daemon, "recording_elsewhere",
                        lambda self: False)
    # And whether the screen is locked: asked afresh before a command fires,
    # it would otherwise ask the compositor of whoever runs the suite.
    monkeypatch.setattr(wake_listen.Daemon, "locked_now",
                        lambda self: self.locked)


@pytest.fixture(autouse=True)
def _no_real_cli_settings(monkeypatch, tmp_path_factory):
    """Which MCP servers and CLIs are on a machine is a fact about the
    machine too (phase M10, tooldetect.py). Without this a catalog, a Codex
    argv or a delivery would read the developer's own ~/.claude.json,
    ~/.codex/config.toml and PATH, and pass or fail by what they have
    installed -- on a runner, nothing. A test that wants something there
    sets these itself (a test's own setenv wins), or passes roots and a
    PATH to tooldetect directly."""
    base = tmp_path_factory.mktemp("cli-settings")
    (base / "claude").mkdir()
    (base / "codex").mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(base / "claude"))
    monkeypatch.setenv("CODEX_HOME", str(base / "codex"))
    import tooldetect
    monkeypatch.setattr(tooldetect, "default_path", lambda: "")
    tooldetect._MEMO.clear()
    # Phase M11: the skills the CLIs find by themselves come from the same
    # two homes, and from ~/.agents/skills, which is pointed here as well.
    (base / "agents-skills").mkdir()
    import skillscan
    monkeypatch.setattr(skillscan, "agents_dir", lambda r: base / "agents-skills")


@pytest.fixture(autouse=True)
def card_desk(monkeypatch):
    """A fresh in-process desk for approval cards (phase M7), as the daemon
    installs one: `permission_hook.ask_card` posts to it instead of a socket.
    Nothing is summoned -- the ids it would have summoned are kept in
    `summoned` -- and the screen is unlocked. tests/cardhelp.py answers its
    cards the way the overlay does."""
    import cards
    desk = cards.Desk(summon=None, is_locked=lambda: False)
    desk.summoned = []
    desk.summon = desk.summoned.append
    monkeypatch.setattr(cards, "LOCAL_DESK", desk)
    return desk


@pytest.fixture
def sandbox() -> Path:
    """The scratch root the XDG variables point into."""
    return _SANDBOX


@pytest.fixture
def cfg_factory():
    """Build a Config without touching shell.json or any file on disk.

    Config reads two files and merges them over the defaults. Tests care
    about the merged result, not the reading, so this bypasses the IO and
    hands back an object with the same interface.
    """
    from runtime import DEFAULTS, Config

    def make(**overrides):
        c = Config.__new__(Config)
        c._values = dict(DEFAULTS)
        c._values.update(overrides)
        c._stamps = ()
        c.source = "test"
        return c

    return make


# --- a Daemon with its moving parts replaced --------------------------------
# Lived in test_lock.py until a second suite needed the same thing. Kept here
# rather than imported across test modules, which pytest tolerates and nobody
# can follow.

class FakeSpeaker:
    """Stands in for Piper, including the part that matters for a lock.

    `say()` consults `watch` between audio chunks, the way the real one does
    between the buffers it writes to PortAudio -- so a test can lock the
    session partway through a sentence and see where the audio stopped. The
    first version of this recorded the text and ignored `watch` entirely,
    which is why a reviewer found the gap rather than the suite: with the
    watch never called, a watch that was never passed looked the same.

    `chunks` is how many pieces a sentence is delivered in, and `played`
    counts the ones that actually went out.
    """

    chunks = 10

    def __init__(self):
        self.said = []
        self.cancelled = 0
        self.played = 0
        self.stopped_early = False

    def say(self, text, watch=None):
        self.said.append(text)
        for _ in range(self.chunks):
            if watch is not None and watch():
                self.stopped_early = True
                return
            self.played += 1

    def cancel(self):
        self.cancelled += 1


class FakeAgent:
    def __init__(self):
        self.cancelled = 0

    def send(self, text, session_id=None):
        return iter(())

    def cancel(self):
        self.cancelled += 1


@pytest.fixture
def daemon(cfg_factory):
    """Signals are process-global, and Daemon installs two in its constructor,
    so they are put back afterwards or a later test inherits them."""
    import signal

    from runtime import StateFile
    from wake_listen import Daemon

    saved = (signal.getsignal(signal.SIGUSR1), signal.getsignal(signal.SIGUSR2))
    d = Daemon(cfg_factory(echoTailMs=0), pipe=None, state=StateFile(),
               speaker=FakeSpeaker(), agent=FakeAgent())
    # "The settings on disk", for code that reads them fresh rather than
    # through d.cfg (collaboration calls; the flag catch-up before a turn,
    # M2): in a test they are the test's own settings, not the sandbox's.
    d.fresh_config = lambda: d.cfg
    # And the copy the crew sweep watches on every poll (phase M8).
    d.watched_config = lambda: d.cfg
    yield d
    signal.signal(signal.SIGUSR1, saved[0])
    signal.signal(signal.SIGUSR2, saved[1])
