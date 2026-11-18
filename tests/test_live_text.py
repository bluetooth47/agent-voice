"""The accurate live transcript (plan item 6).

Vosk's rough text appears as you talk; at each pause, the part Whisper has
read is replaced by Whisper's text. What has to hold:

- Whisper's text replaces exactly the rough part it covers, no more;
- text never falls back from Whisper to Vosk for audio Whisper has already
  read (the flicker the plan warned about), even when a short piece is
  thrown away to be heard again as part of a longer one;
- "on" and "auto" show what they always showed;
- "accurate" loads Vosk like "on", and is offered on the Voice page.

The daemon's own `hear()` is driven, with a Vosk-shaped fake and the real
Utterance, on an executor that runs only when told to.
"""
from __future__ import annotations

import json

import pytest

from eager import PAUSE_FRAMES, LiveText, Utterance
from test_eager import FRAME, LOUD, QUIET, Manual

BPS = 32000


class Vosk:
    """Hears one word per loud frame: v1, v2, ... FinalResult flushes."""

    def __init__(self):
        self.n = 0
        self.words: list[str] = []

    def AcceptWaveform(self, pcm):
        if pcm == LOUD:
            self.n += 1
            self.words.append(f"v{self.n}")
        return False

    def PartialResult(self):
        return json.dumps({"partial": " ".join(self.words)})

    def Result(self):
        raise AssertionError("never final in these tests")

    def FinalResult(self):
        out, self.words = " ".join(self.words), []
        return json.dumps({"text": out})


class Whisper:
    """Names each piece by how many frames it was: W<frames>."""

    def __call__(self, pcm, context):
        return f"W{len(pcm) // FRAME}"


class Pipe:
    accurate_partials = True


@pytest.fixture
def live(daemon):
    daemon.pipe = Pipe()
    ex = Manual()
    utt = Utterance(Whisper(), ex.submit, bytes_per_s=BPS, frame_bytes=FRAME)
    cap = Vosk()

    def say(*frames):
        shown = []
        for f in frames:
            shown.append(daemon.hear(cap, utt, f, f == LOUD))
        return shown
    return say, ex, utt


def test_rough_first_then_whisper_at_the_pause(live):
    say, ex, _ = live
    shown = say(LOUD, LOUD, LOUD)
    assert shown == ["v1", "v1 v2", "v1 v2 v3"]
    shown = say(*[QUIET] * PAUSE_FRAMES)
    assert shown[-1] == "v1 v2 v3", "Whisper has not run yet"
    ex.run()
    assert say(QUIET)[-1] == "W5", "the rough part it covers is replaced"


def test_whisper_replaces_only_what_it_read(live):
    say, ex, _ = live
    say(*[LOUD] * 16, *[QUIET] * PAUSE_FRAMES)       # 3.2s: a piece to keep
    say(LOUD, LOUD)                                   # talking again
    assert say(LOUD)[-1] == "v1 v2 v3 v4 v5 v6 v7 v8 v9 v10 v11 v12 v13 v14 v15 v16 v17 v18 v19"
    ex.run()
    assert say(LOUD)[-1] == "W18 v17 v18 v19 v20"


def test_a_thrown_away_piece_never_falls_back_to_vosk(live):
    """1s, pause, Whisper reads it; then more speech. The short piece is
    thrown away to be heard again as part of the longer one, but its text
    stays on screen until the longer one is ready."""
    say, ex, utt = live
    say(*[LOUD] * 5, *[QUIET] * PAUSE_FRAMES)
    ex.run()
    assert say(QUIET)[-1] == "W7"
    shown = say(*[LOUD] * 5, *[QUIET] * PAUSE_FRAMES)
    assert all(s.startswith("W7") for s in shown), shown
    ex.run()
    assert say(QUIET)[-1] == "W15", "the longer piece replaces the shorter"
    # And the final transcript is the longer piece alone.
    assert utt.finish()[0] == "W15"


def test_words_vosk_makes_of_the_silence_after_a_cut_are_not_shown(live):
    """Measured: "Tell me which one. the" -- the last piece was Whisper's,
    and Vosk heard "the" in the silence after it."""
    say, ex, _ = live
    say(*[LOUD] * 3, *[QUIET] * PAUSE_FRAMES)
    ex.run()
    assert say(QUIET)[-1] == "W5"
    _, _, utt = live
    utt.live.partial = "the"            # Vosk, hearing the room
    assert say(QUIET)[-1] == "W5"


def test_without_accurate_it_shows_vosk_as_before(live, daemon):
    say, ex, _ = live
    daemon.pipe.accurate_partials = False
    say(*[LOUD] * 3, *[QUIET] * PAUSE_FRAMES)
    ex.run()
    assert say(LOUD)[-1] == "v1 v2 v3 v4", "the rough text is not cut at pauses"


def test_no_vosk_and_a_fake_utterance_are_both_fine(daemon):
    """cap is None when partials are off; the run-loop tests' utterances
    have no live text."""
    daemon.pipe = Pipe()

    class Bare:
        def add(self, pcm, loud):
            pass
    assert daemon.hear(None, Bare(), LOUD, True) == ""
    utt = Utterance(Whisper(), Manual().submit, bytes_per_s=BPS, frame_bytes=FRAME)
    assert daemon.hear(None, utt, LOUD, True) == ""


def test_vosk_finals_stay_in_their_segment():
    lt = LiveText()
    lt.final("open the")
    lt.partial = "file"
    assert lt.render("", 0) == "open the file"
    lt.cut(100, "file please")
    lt.partial = "and"
    assert lt.render("", 0) == "open the file please", "nobody spoke since the cut"
    lt.heard(True)
    assert lt.render("", 0) == "open the file please and"
    assert lt.render("Open the file, please.", 100) == "Open the file, please. and"


def test_accurate_loads_vosk_and_is_offered():
    import wake_listen
    from conftest import ROOT
    from qml_sources import page
    pipe = object.__new__(wake_listen.Pipeline)
    pipe.engine = "sherpa"
    for mode, needs in (("auto", False), ("on", True), ("accurate", True), ("off", False)):
        pipe._partials = mode
        assert pipe._partials_need_vosk() is needs
        assert pipe.want_partials is needs
    man = json.loads((ROOT / "manifest.json").read_text())["barWidget"]
    opts = next(e for e in man["schema"] if e["key"] == "livePartials")["options"]
    assert "accurate" in opts
    assert '{ value: "accurate"' in page("Voice")


def test_the_run_loop_shows_what_hear_returns():
    """Both places a capture is fed go through hear(), so the barge path's
    early frames cut the rough text at the same pauses."""
    from conftest import ROOT
    src = (ROOT / "daemon" / "wake_listen.py").read_text()
    assert "partial = self.hear(cap, utt, pcm, voiced)" in src
    assert src.count("self.hear(cap, utt, early, self.voiced(frame_db(early)))") == 2
    assert "utt.add(" not in src.replace("cut = utt.add(pcm, voiced)", "")
