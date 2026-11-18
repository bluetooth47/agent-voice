"""sherpa-onnx as the third wake engine (FINDINGS §23).

What has to hold:

- it takes the phrase and the extra agents' names as text, through a phone
  lexicon, and refuses a name whose word it lacks the way Vosk does;
- the names and the threshold go on the stream, so changing either never
  reloads the model, while the phrase (which can force a fallback) does;
- it is fed every frame, gate or no gate, like openWakeWord;
- when it cannot run -- no package, no model, a phrase word it lacks -- the
  daemon falls back to Vosk, and from then on the names are back in the
  spec, because Vosk's grammar holds them;
- the settings page, the installer and the lock all know it exists.

Nothing here needs the sherpa-onnx wheel or a model on disk. The one test of
the real SherpaWake class needs numpy, because the class converts audio with
it, and says so by skipping.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "daemon"))

from qml_sources import overlay, page  # noqa: E402

LEXICON = """\
COMPUTER K AH0 M P Y UW1 T ER0
HEY HH EY1
SARAH S EH1 R AH0
SARAH S AA1 R AH0
JARVIS JH AA1 R V IH0 S
THEO TH IY1 OW0
"""


@pytest.fixture
def model(tmp_path):
    (tmp_path / "en.phone").write_text(LEXICON)
    return tmp_path


# --- the keyword text --------------------------------------------------------

def test_the_lexicon_keeps_only_the_words_asked_for_and_their_first_reading(model):
    import wake_listen
    got = wake_listen.sherpa_lexicon(model, ["sarah", "Computer", "ziggy"])
    assert got == {"sarah": ["S", "EH1", "R", "AH0"],
                   "computer": ["K", "AH0", "M", "P", "Y", "UW1", "T", "ER0"]}


def test_a_keyword_line_is_phones_boost_threshold_and_a_tag(model):
    import wake_listen
    lex = wake_listen.sherpa_lexicon(model, ["hey", "sarah", "computer"])
    text = wake_listen.sherpa_keywords(["computer", "hey sarah"], lex, 0.3)
    assert text.splitlines() == [
        f"K AH0 M P Y UW1 T ER0 :{wake_listen.SHERPA_BOOST} #0.30 @computer",
        f"HH EY1 S EH1 R AH0 :{wake_listen.SHERPA_BOOST} #0.30 @hey_sarah",
    ]



def test_a_short_name_gets_both_readings_and_the_stronger_pull(model):
    import wake_listen
    lex = wake_listen.sherpa_lexicon(model, ["hey", "theo"])
    text = wake_listen.sherpa_keywords(["theo", "hey theo"], lex, 0.25)
    short, long = wake_listen.SHORT_BOOST, wake_listen.SHERPA_BOOST
    assert text.splitlines() == [
        f"TH IY1 OW0 :{short} #0.25 @theo",
        f"TH IY1 AH0 :{short} #0.25 @theo",
        f"HH EY1 TH IY1 OW0 :{long} #0.25 @hey_theo",
        f"HH EY1 TH IY1 AH0 :{long} #0.25 @hey_theo",
    ]

# --- the real class, against a stand-in library ------------------------------

class _FakeSpotter:
    """Records how it was built and what each stream was asked to spot, and
    reports `script[n]` on the n-th decode."""
    last = None

    def __init__(self, **kw):
        self.kw = kw
        self.file_text = Path(kw["keywords_file"]).read_text()
        self.streams: list[str] = []
        self.script: list[str] = []
        self._decodes = 0
        _FakeSpotter.last = self

    def create_stream(self, keywords=None):
        self.streams.append(keywords)
        return types.SimpleNamespace(pending=0,
                                     accept_waveform=self._accept)

    def _accept(self, rate, samples):
        assert rate == 16_000 and samples.dtype.name == "float32"
        self._pending = True

    def is_ready(self, stream):
        ready, self._pending = getattr(self, "_pending", False), False
        return ready

    def decode_stream(self, stream):
        self._decodes += 1

    def get_result(self, stream):
        n = self._decodes - 1
        return self.script[n] if n < len(self.script) else ""

    def reset_stream(self, stream):
        pass


def test_sherpa_wake_puts_every_real_keyword_on_the_stream(model, monkeypatch):
    np = pytest.importorskip("numpy")
    import wake_listen
    monkeypatch.setitem(sys.modules, "sherpa_onnx",
                        types.SimpleNamespace(KeywordSpotter=_FakeSpotter))

    spot = wake_listen.SherpaWake(model, 0.25)
    fake = _FakeSpotter.last

    # The constructor's file holds only the never-firing placeholder, and is
    # gone afterwards.
    assert fake.file_text.strip() == wake_listen._SHERPA_NEVER
    assert not Path(fake.kw["keywords_file"]).exists()
    assert fake.kw["keywords_threshold"] == 0.25
    assert fake.kw["num_threads"] == 1

    assert spot.knows("sarah") and spot.knows("HEY") and not spot.knows("ziggy")
    spot.listen_for(["computer", "hey sarah"], 0.4)
    assert "@computer" in fake.streams[-1] and "@hey_sarah" in fake.streams[-1]
    assert "#0.40" in fake.streams[-1]

    silence = np.zeros(3200, dtype=np.int16).tobytes()
    fake.script = ["", "_never", "hey_sarah"]
    assert spot.feed(silence) == ""
    assert spot.feed(silence) == "", "the placeholder must never wake it"
    assert spot.feed(silence) == "hey sarah", "the tag turns back into the phrase"


# --- the Pipeline ------------------------------------------------------------

class FakeSherpa:
    """Stands in for SherpaWake. `heard` is what the next feed() returns."""
    built = 0

    def __init__(self, model_dir, threshold):
        FakeSherpa.built += 1
        self.threshold = threshold
        self.phrases: list[str] = []
        self.streams: list[tuple] = []
        self.fed = 0
        self.heard = ""

    def knows(self, word):
        return word.lower() in {"hey", "computer", "sarah", "jarvis"}

    def listen_for(self, phrases, threshold, also=None, short_boost=None):
        self.phrases, self.threshold = list(phrases), threshold
        self.streams.append((tuple(phrases), threshold))
        self.tuning = (also, short_boost)

    def feed(self, pcm):
        self.fed += 1
        hit, self.heard = self.heard, ""
        return hit


class Cfg(dict):
    """Real defaults for anything not named, and the agents() Config has."""
    def _v(self, k):
        from runtime import DEFAULTS
        return self[k] if k in self else DEFAULTS[k]

    def get_str(self, k): return str(self._v(k))
    def get_int(self, k): return int(self._v(k))
    def get_bool(self, k): return bool(self._v(k))
    def __getitem__(self, k): return self._v(k) if k not in self.keys() else dict.__getitem__(self, k)

    def agents(self):
        return [{"name": n} for n in self.get("names", [])]

    def wake_tuning(self):
        from runtime import Config
        return Config.wake_tuning(self)


def _pipe(monkeypatch, tmp_path, **cfg):
    import wake_listen
    FakeSherpa.built = 0
    monkeypatch.setattr(wake_listen, "SherpaWake", FakeSherpa)
    monkeypatch.setattr(wake_listen, "sherpa_model", lambda: tmp_path)
    pipe = object.__new__(wake_listen.Pipeline)
    pipe._oww = pipe._sherpa = pipe._model = pipe._wake = None
    pipe._whisper_size, pipe._whisper_override = "tiny.en", None
    pipe._partials = "auto"
    pipe.names, pipe.unheard = [], {}
    # Vosk is only reached on a fallback; these tests record that instead.
    pipe._vosk_built = []
    pipe._reset_wake = lambda: pipe._vosk_built.append(
        (pipe.phrase, tuple(pipe.names)))
    pipe._knows_vosk = True
    # The "full stop" keyword is off unless a test asks for it, so the
    # phrase lists below stay the wake names.
    c = Cfg({"engine": "sherpa", "phrase": "computer", "model": "tiny.en",
             "names": ["sarah"], "fullStopAnytime": False, **cfg})
    return pipe, c


def test_it_listens_for_the_phrase_and_the_names(monkeypatch, tmp_path):
    pipe, cfg = _pipe(monkeypatch, tmp_path)
    pipe.apply(cfg)
    assert pipe.engine == "sherpa"
    assert pipe._sherpa.phrases == ["computer", "sarah"]
    assert pipe._sherpa.threshold == pytest.approx(0.15)
    assert pipe.detection_threshold == pytest.approx(0.15)
    assert pipe._vosk_built == []


def test_a_name_its_lexicon_lacks_is_refused_and_said(monkeypatch, tmp_path, capsys):
    pipe, cfg = _pipe(monkeypatch, tmp_path, names=["sarah", "ziggy"])
    pipe.apply(cfg)
    assert pipe._sherpa.phrases == ["computer", "sarah"]
    assert "ziggy" in pipe.unheard
    assert "ziggy" in capsys.readouterr().out


def test_threshold_and_names_change_the_stream_not_the_model(monkeypatch, tmp_path):
    pipe, cfg = _pipe(monkeypatch, tmp_path)
    pipe.apply(cfg)
    assert FakeSherpa.built == 1

    cfg["sherpaThresholdPct"] = 40
    pipe.apply(cfg)
    assert pipe._sherpa.streams[-1] == (("computer", "sarah"), 0.40)

    cfg["names"] = ["sarah", "jarvis"]
    pipe.apply(cfg)
    assert pipe._sherpa.streams[-1] == (("computer", "sarah", "jarvis"), 0.40)

    assert FakeSherpa.built == 1, "a slider move or a new agent reloaded the model"


def test_nothing_changed_means_no_new_stream(monkeypatch, tmp_path):
    pipe, cfg = _pipe(monkeypatch, tmp_path)
    pipe.apply(cfg)
    pipe.apply(cfg)
    pipe.apply(cfg)
    assert len(pipe._sherpa.streams) == 1, \
        "apply runs on every poll; a new stream each time drops what it heard"


def test_a_new_phrase_does_rebuild(monkeypatch, tmp_path):
    pipe, cfg = _pipe(monkeypatch, tmp_path)
    pipe.apply(cfg)
    cfg["phrase"] = "hey jarvis"
    pipe.apply(cfg)
    assert FakeSherpa.built == 2
    assert pipe._sherpa.phrases[0] == "hey jarvis"


def test_it_is_fed_below_the_gate_and_says_which_phrase(monkeypatch, tmp_path):
    pipe, cfg = _pipe(monkeypatch, tmp_path)
    pipe.apply(cfg)
    pipe._refractory_until = 0.0

    assert pipe.feed_wake(b"\0" * 6400, -70.0) is False
    assert pipe._sherpa.fed == 1, "a gated frame never reached the spotter"

    pipe._sherpa.heard = "sarah"
    assert pipe.feed_wake(b"\0" * 6400, -70.0) is True
    assert pipe.heard_phrase == "sarah"

    pipe._sherpa.heard = "sarah"
    assert pipe.feed_wake(b"\0" * 6400, -20.0) is False, "refractory window"


def test_no_model_falls_back_to_vosk(monkeypatch, tmp_path, capsys):
    import wake_listen
    pipe, cfg = _pipe(monkeypatch, tmp_path)
    monkeypatch.setattr(wake_listen, "sherpa_model", lambda: None)
    pipe._choose_names = lambda names: setattr(pipe, "names", list(names))

    pipe.apply(cfg)

    assert pipe.engine == "vosk" and pipe._sherpa is None
    assert pipe._vosk_built == [("computer", ("sarah",))]
    assert "falling back to Vosk" in capsys.readouterr().out


def test_after_a_fallback_a_new_name_reaches_the_vosk_grammar(monkeypatch, tmp_path):
    """The sherpa spec leaves the names out because they go on the stream. Once
    Vosk is listening instead, its grammar holds them, so leaving them out
    would mean a new agent is never heard."""
    import wake_listen
    pipe, cfg = _pipe(monkeypatch, tmp_path)
    monkeypatch.setattr(wake_listen, "sherpa_model", lambda: None)
    pipe._choose_names = lambda names: setattr(pipe, "names", list(names))
    pipe.apply(cfg)
    pipe.apply(cfg)
    assert len(pipe._vosk_built) == 1, "a settled fallback must not rebuild every poll"

    cfg["names"] = ["sarah", "jarvis"]
    pipe.apply(cfg)
    assert pipe._vosk_built[-1] == ("computer", ("sarah", "jarvis"))


def test_a_phrase_word_it_lacks_falls_back_with_the_reason(monkeypatch, tmp_path, capsys):
    pipe, cfg = _pipe(monkeypatch, tmp_path, phrase="hey omarchy")
    pipe._choose_names = lambda names: setattr(pipe, "names", list(names))
    pipe.apply(cfg)
    out = capsys.readouterr().out
    assert pipe.engine == "vosk"
    assert "omarchy" in out and "falling back to Vosk" in out


def test_leaving_sherpa_drops_it(monkeypatch, tmp_path):
    pipe, cfg = _pipe(monkeypatch, tmp_path)
    pipe.apply(cfg)
    pipe._choose_names = lambda names: setattr(pipe, "names", list(names))
    cfg["engine"] = "vosk"
    pipe.apply(cfg)
    assert pipe._sherpa is None and pipe.engine == "vosk"
    assert pipe.detection_threshold is None


def test_live_partials_on_auto_do_not_load_vosk_for_it(monkeypatch, tmp_path):
    pipe, cfg = _pipe(monkeypatch, tmp_path)
    pipe.apply(cfg)
    assert pipe.want_partials is False


# --- settings, installer, lock -----------------------------------------------

def test_the_setting_exists_in_all_three_places():
    from runtime import DEFAULTS, TOML_ALIASES
    manifest = json.loads((ROOT / "manifest.json").read_text())["barWidget"]
    assert DEFAULTS["sherpaThresholdPct"] == manifest["defaults"]["sherpaThresholdPct"]
    assert "sherpaThresholdPct" in TOML_ALIASES
    engine = next(e for e in manifest["schema"] if e["key"] == "engine")
    assert "sherpa" in engine["options"]
    assert 's.put("sherpaThresholdPct"' in page("Listening")


def test_settings_knows_whether_sherpa_is_installed():
    src = overlay()
    assert "site-packages/sherpa_onnx" in src
    assert "sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20/tokens.txt" in src, \
        "the package alone runs nothing; the model has to be there too"
    assert "scanSherpa.running = true" in src
    assert "readonly property bool sherpaLive: usingSherpa && sherpaAvailable" in src


def test_engine_specific_controls_follow_what_is_running():
    listening = page("Listening")
    assert "visible: page.s.sherpaLive" in listening
    assert "visible: !page.s.owwLive && !page.s.sherpaLive" in listening, \
        "Vosk's confidence bar does nothing on sherpa-onnx"
    assert "visible: page.s.usingSherpa && !page.s.sherpaAvailable" in listening
    assert 'page.s.fetchNow(["--sherpa"])' in listening


def test_the_model_path_agrees_everywhere():
    from paths import SHERPA_KWS_MODEL
    install = (ROOT / "install.sh").read_text()
    lock = (ROOT / "models.lock").read_text()
    assert f"SHERPA_MODEL={SHERPA_KWS_MODEL}" in install
    assert f"sha256 {SHERPA_KWS_MODEL}.tar.bz2 " in lock
    assert SHERPA_KWS_MODEL in overlay()


def test_the_installer_takes_the_flag_and_ships_the_requirements():
    install = (ROOT / "install.sh").read_text()
    assert "--sherpa) WANT_SHERPA=1" in install
    assert '"$ROOT/requirements-sherpa.txt"' in install
    copy = install[install.index('cp "$ROOT/install.sh"'):]
    assert "requirements-sherpa.txt" in copy[:copy.index('"$APP/"') + 8], \
        "a repair run from the installed copy would not find it"
    # The model goes through download(), which refuses an unhashed file.
    fetch = install[install.index("fetch_sherpa() {"):]
    assert 'download "https://github.com/k2-fsa/' in fetch[:fetch.index("\n}\n")]


def test_the_model_finder_wants_every_file(tmp_path, monkeypatch):
    import paths
    monkeypatch.setattr(paths, "models_dir", lambda: tmp_path)
    d = tmp_path / paths.SHERPA_KWS_MODEL
    d.mkdir()
    (d / "tokens.txt").write_text("")
    assert paths.sherpa_model() is None, "a half-extracted folder is not a model"
    for n in ("en.phone", "encoder-epoch-13-avg-2-chunk-16-left-64.onnx",
              "decoder-epoch-13-avg-2-chunk-16-left-64.onnx",
              "joiner-epoch-13-avg-2-chunk-16-left-64.onnx"):
        (d / n).write_text("")
    assert paths.sherpa_model() == d


# --- the Advanced wake settings (plan item 9) -------------------------------

def test_boost_and_also_sounds_change_the_stream_not_the_model(monkeypatch, tmp_path):
    pipe, cfg = _pipe(monkeypatch, tmp_path)
    pipe.apply(cfg)
    assert pipe._sherpa.tuning == ({"theo": ["TH IY1 AH0"]}, 1.5), \
        "the shipped default is what ALT_PHONES and SHORT_BOOST were"
    cfg["shortNameBoostPct"] = 200
    pipe.apply(cfg)
    assert pipe._sherpa.tuning[1] == 2.0
    cfg["wakeAlsoSounds"] = {"sarah": ["sara", "S AA1 R AH0"]}
    pipe.apply(cfg)
    assert pipe._sherpa.tuning[0] == {"sarah": ["sara", "S AA1 R AH0"]}
    assert len(pipe._sherpa.streams) == 3
    assert FakeSherpa.built == 1, "a tuning change reloaded the model"
    pipe.apply(cfg)
    assert len(pipe._sherpa.streams) == 3, "no change, but a new stream"


def test_the_burst_window_reaches_the_cutter(monkeypatch, tmp_path):
    pipe, cfg = _pipe(monkeypatch, tmp_path, crossCheckMinMs=500,
                      crossCheckMaxMs=1800)
    pipe.apply(cfg)
    cutter = pipe._burst_cutter()
    assert (cutter.min_ms, cutter.max_ms) == (500, 1800)


def test_also_sounds_lines_carry_the_names_tag_and_the_boost(model):
    import wake_listen
    lex = wake_listen.sherpa_lexicon(model, ["sarah", "hey"])
    text = wake_listen.sherpa_keywords(
        ["sarah"], lex, 0.2, alts={"sarah": [["S", "AA1", "R", "AH0"],
                                             ["S", "EH1", "R", "AH0"]]},
        short_boost=2.0)
    # The duplicate of the dictionary reading is dropped; the new one wakes
    # the same agent.
    assert text.splitlines() == [
        f"S EH1 R AH0 :{wake_listen.SHERPA_BOOST} #0.20 @sarah",
        f"S AA1 R AH0 :{wake_listen.SHERPA_BOOST} #0.20 @sarah",
    ]
    short = wake_listen.sherpa_keywords(["hey"], lex, 0.2, alts={}, short_boost=2.0)
    assert short == "HH EY1 :2.0 #0.20 @hey", "a short phrase takes the boost given"


def test_alternatives_are_resolved_and_bad_ones_skipped(model):
    import wake_listen
    (model / "tokens.txt").write_text(
        "\n".join(f"{t} {i}" for i, t in enumerate(
            ["TH", "IY1", "AH0", "OW0", "S", "EH1", "R", "HH", "EY1"])) + "\n")
    spot = object.__new__(wake_listen.SherpaWake)
    spot.model_dir, spot._lexicon, spot._tokens, spot.unusable = model, {}, None, {}
    got = spot.alternatives(["theo", "sarah"], {
        "theo": ["TH IY1 AH0", "TH IY1 XX9"],
        "sarah": ["hey sarah", "ziggy"],
        "nobody": ["TH"]})
    assert got == {"theo": [["TH", "IY1", "AH0"]],
                   "sarah": [["HH", "EY1", "S", "EH1", "R", "AH0"]]}
    assert set(spot.unusable) == {"theo: TH IY1 XX9", "sarah: ziggy"}


@pytest.mark.parametrize("raw, want", [
    ({"theo": ["thea", "TH IY1 AH0"]}, {"theo": ["thea", "TH IY1 AH0"]}),
    ({"Theo": ["  thea  "]}, {"theo": ["thea"]}),
    ({"theo": ["Thea", "rm -rf", "TH;", "a b c d", 7, "thea", "thea"]}, {"theo": ["thea"]}),
    ({"theo": []}, {}),
    ({"two words": ["x"]}, {}),
    ("theo", {}),
    (None, {}),
    ({"theo": "thea"}, {}),
])
def test_also_sounds_is_cleaned(raw, want):
    from runtime import Config
    cfg = Config.__new__(Config)
    cfg._values = {"wakeAlsoSounds": raw}
    assert cfg.wake_tuning()["also_sounds"] == want


@pytest.mark.parametrize("values, want", [
    ({}, (1.5, 300, 2600)),
    ({"shortNameBoostPct": 9999, "crossCheckMinMs": 1, "crossCheckMaxMs": 99999}, (3.0, 100, 5000)),
    ({"shortNameBoostPct": "abc"}, (1.5, 300, 2600)),
    # A window that would close keeps the minimum under the maximum.
    ({"crossCheckMinMs": 1000, "crossCheckMaxMs": 1000}, (1.5, 300, 1000)),
])
def test_the_numbers_are_clamped(values, want):
    from runtime import Config
    cfg = Config.__new__(Config)
    cfg._values = dict(values)
    t = cfg.wake_tuning()
    assert (t["short_boost"], t["burst_min_ms"], t["burst_max_ms"]) == want


def test_the_advanced_settings_are_drawn_on_the_listening_page():
    text = page("Listening")
    for key in ("shortNameBoostPct", "crossCheckMinMs", "crossCheckMaxMs",
                "wakeAlsoSounds", "sherpaThresholdPct", "wakeCrossCheck"):
        assert f'"{key}"' in text, key
    assert 'title: "ADVANCED"' in text


# --- "full stop" as a keyword ----------------------------------------------

def test_full_stop_is_spotted_beside_the_names(monkeypatch, tmp_path):
    import wake_listen
    pipe, cfg = _pipe(monkeypatch, tmp_path, fullStopAnytime=True)
    pipe.apply(cfg)
    assert pipe._sherpa.phrases == ["computer", "sarah", wake_listen.STOP_PHRASE]
    assert FakeSherpa.built == 1
    cfg["fullStopAnytime"] = False
    pipe.apply(cfg)
    assert pipe._sherpa.phrases == ["computer", "sarah"]
    assert FakeSherpa.built == 1, "the switch reloaded the model"


def test_a_spotted_full_stop_is_reported_as_itself(monkeypatch, tmp_path):
    import wake_listen
    pipe, cfg = _pipe(monkeypatch, tmp_path, fullStopAnytime=True)
    pipe.apply(cfg)
    pipe._refractory_until = 0.0
    pipe._sherpa.heard = "full stop"
    assert pipe.feed_wake(b"\0" * 6400, -60.0)
    assert pipe.heard_phrase == wake_listen.STOP_PHRASE


def test_the_daemon_stops_everything_on_it_and_opens_no_capture():
    """Read from the source: the run loop and the thinking-time watcher both
    need a microphone to drive."""
    from conftest import ROOT
    src = (ROOT / "daemon" / "wake_listen.py").read_text()
    loop = src[src.index("fired = self.pipe.feed_wake(pcm, level)"):]
    loop = loop[:loop.index("capture_for = self._woken()")]
    assert "self.heard_full_stop()" in loop and "self.full_stop()" in loop
    assert "continue" in loop, "falls through into opening a capture"
    watch = src[src.index("def _wake_watch_until"):]
    watch = watch[:watch.index("def chime")]
    assert "self.heard_full_stop()" in watch and "self.full_stop()" in watch
    assert watch.index("heard_full_stop") < watch.index("self._woke = True")
    # The wake test does not count it as a wake.
    test = src[src.index("def wake_testing"):]
    test = test[:test.index("def _write_wake_test")]
    assert "not self.heard_full_stop()" in test


# --- the second check's modes -------------------------------------------------

class _Mode:
    """A Pipeline with the votes stubbed, to see which engines are asked."""

    def __init__(self, monkeypatch, mode, vosk="theo", text="Theo."):
        import wake_listen
        pipe = object.__new__(wake_listen.Pipeline)
        pipe.phrase, pipe.names = "theo", ["sora"]
        pipe.cc_engines, pipe.cc_trailing, pipe.cc_hint = mode, 3, True
        pipe.threshold_db = pipe.wake_gate_db = -40.0
        pipe.refractory_ms = 2000
        pipe._log_speech = False
        self.asked = []
        pipe._burst_cutter = lambda: type("C", (), {"feed": lambda s, p, l: b"x"})()
        pipe._vosk_vote = lambda a, n: (self.asked.append("vosk"), (vosk, {"theo", "sora"}))[1]
        pipe._whisper_names = lambda a, n: (self.asked.append("whisper"), text)[1]
        pipe._sherpa = type("S", (), {"reset": lambda s: None})()
        self.pipe = pipe


@pytest.mark.parametrize("mode, vosk, text, woke, asked", [
    ("both", "theo", "Theo.", True, ["vosk", "whisper"]),
    ("both", "", "Theo.", False, ["vosk"]),
    ("whisper", "", "Theo.", True, ["whisper"]),
    ("whisper", "", "Video.", False, ["whisper"]),
    ("vosk", "theo", "", True, ["vosk"]),
    ("vosk", "", "", False, ["vosk"]),
])
def test_each_mode_asks_only_its_engines(monkeypatch, mode, vosk, text, woke, asked):
    m = _Mode(monkeypatch, mode, vosk, text)
    assert m.pipe._second_check(b"\0" * 6400, -20.0) is woke
    assert m.asked == asked
    if woke:
        assert m.pipe.heard_phrase == "theo" and m.pipe.wake_how == "second check"


def test_whisper_only_mode_lets_vosk_go(monkeypatch, tmp_path):
    pipe, cfg = _pipe(monkeypatch, tmp_path, crossCheckEngines="whisper")
    pipe.apply(cfg)
    assert pipe.cc_engines == "whisper" and not pipe._needs_vosk()
    cfg["crossCheckEngines"] = "both"
    pipe.apply(cfg)
    assert pipe._needs_vosk()


def test_the_whisper_hint_can_be_turned_off(monkeypatch):
    import wake_listen
    pipe = object.__new__(wake_listen.Pipeline)
    seen = []

    class Pool:
        def submit(self, fn, audio, prompt):
            seen.append(prompt)
            return type("F", (), {"result": lambda s, timeout=None: ""})()
    pipe._pool = Pool()
    pipe.cc_hint = True
    pipe._whisper_names(b"", ["theo", "sora"])
    pipe.cc_hint = False
    pipe._whisper_names(b"", ["theo", "sora"])
    assert seen == ["Theo, Sora.", None]


def test_the_new_controls_are_drawn():
    text = page("Listening")
    for key in ("crossCheckEngines", "crossCheckTrailingWords", "crossCheckWhisperHint"):
        assert f'"{key}"' in text, key
    assert '"fullStopAnytime"' in page("Conversation")
