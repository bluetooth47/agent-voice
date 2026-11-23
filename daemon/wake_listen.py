#!/usr/bin/env python3
"""Wake word -> utterance -> transcript -> spoken reply.

The loop. An agent answers the transcript and the reply is spoken a sentence
at a time; with no agent installed it says back what it heard instead, which
is also how the timing and the echo problem are exercised without one.

Two recognisers, because they are good at different things:

  Vosk, grammar-restricted to the wake phrase, listens continuously. It is
  cheap enough to leave running and its grammar pins the trigger far harder
  than a general model would. It also endpoints your speech and its partial
  results put something on screen immediately.

  Whisper transcribes the captured utterance once you stop. Far more accurate,
  especially with the vocabulary prompt, but it cannot start until you finish,
  so it never runs while you are still talking.

Knobs come from shell.json (written by the bar widget), falling back to
daemon/agentvoice.toml. Both are re-read between utterances.

    python daemon/wake_listen.py
    python daemon/wake_listen.py --simulate bench/corpus/wav/11.wav
    agentvoice start|stop      # the service
    agentvoice mic             # release or re-engage the microphone, service up
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapters import (  # noqa: E402
    explain as explain_agent, load as load_adapter, main_program, omarchy_default,
    sentences,
    model_lists, takes_effort, takes_model,
)
from adapters.base import Chunk, speech_safe  # noqa: E402
from crew import (  # noqa: E402
    FLOOR_LEASE_S, FOLLOW_UP_STALE_S, Persona, View, route,
)
from agents_panel import AgentsPanel, program_label, slug  # noqa: E402
import crosscheck  # noqa: E402
import wake_test  # noqa: E402
import failure  # noqa: E402
from chimes import Chimes  # noqa: E402
from eager import Utterance, sounds_finished  # noqa: E402
from noise_floor import MARGIN_MAX, MARGIN_MIN, NoiseFloor  # noqa: E402
import headset  # noqa: E402
from speech_text import (  # noqa: E402
    UNDO_S, Found, as_prompt, chat_command, command, find_command, heard_back,
    is_full_stop, is_goodbye, is_handoff, is_stop_command, is_take_over,
    is_undo, open_mic_command, pass_command, safe_for_terminal,
)
from chats import RETENTIONS, ChatStore, replay_context  # noqa: E402
import chats as chat_schema  # noqa: E402
import collab  # noqa: E402
import narration  # noqa: E402
import omarchy_skill  # noqa: E402
import agentvoice_skill  # noqa: E402
import readout  # noqa: E402
import try_it  # noqa: E402
import chat_names  # noqa: E402
import sessions  # noqa: E402
import runinfo  # noqa: E402
import launch_extras  # noqa: E402
from runtime import (  # noqa: E402
    REPLY_MAX, RUNTIME_DIR, Config, History, Speaker, StateFile, instructions_text, speed_pct,
)

from paths import (  # noqa: E402
    build_id, endpoint_key, harden_private_trees, project_dir, vocab_file,
    sherpa_model, vosk_model,
)

#: `blocksize` is in frames, not bytes: 3200 frames at 16kHz is 200ms, not
#: the 100ms this said for a long time. Every figure derived from it was
#: therefore stated at half its real value -- the echo drop, the loudness
#: run-up, monitor's end-of-speech wait. CHUNK_MS exists so the next one
#: cannot be written down by hand and be wrong.
RATE, CHUNK = 16_000, 3200

#: The longest typed message accepted, in characters.
TYPED_MAX = 8000
CHUNK_MS = 1000 * CHUNK // RATE     # 200

#: How much of a reasoning model's thinking is kept for the conversation view.
THINKING_MAX = 8000


def _host(url: str) -> str:
    """The host of an endpoint URL, for looking its key up by.

    Port included when there is one, because one machine can run more than
    one endpoint and they do not share a key: Ollama on :11434 needs none,
    while Hermes on :8642 takes a bearer token that its own documentation
    describes as equivalent to a root password. Keying on the hostname alone
    would hand the second one's key to the first.

    A URL with no port keeps the bare hostname, so entries filed before this
    -- api.openai.com and the rest -- still resolve.
    """
    import urllib.parse
    parts = urllib.parse.urlparse(url)
    host = (parts.hostname or "").lower()
    try:
        port = parts.port
    except ValueError:
        port = None
    return f"{host}:{port}" if host and port else host

DIM, RED, GRN, YEL, CYA, BLD, OFF = (
    "\033[2m", "\033[31m", "\033[32m", "\033[33m", "\033[36m", "\033[1m", "\033[0m")


def frame_db(pcm: bytes) -> float:
    """RMS of one frame in dBFS. Cheap: this runs on every 100ms of audio."""
    import numpy as np
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    if not len(x):
        return -99.0
    return float(20.0 * np.log10(np.sqrt((x ** 2).mean()) / 32768.0 + 1e-9))


def vocab_stamp() -> tuple[str, float]:
    """Which vocabulary file, and when it last changed.

    Both halves matter. Editing the list rewrites the file, and creating
    ~/.config/agentvoice/vocab.txt for the first time changes *which* file is
    used -- the shipped default until then. Either way nothing about the
    settings changes, so a daemon that read the list once went on prompting
    Whisper with the old terms until it was restarted.
    """
    path = vocab_file()
    try:
        return str(path), path.stat().st_mtime
    except OSError:
        return str(path), 0.0


def load_vocab() -> str | None:
    """The user's term list as one prompt line, or None.

    Comments are tested after stripping: an indented `  # notes` was being
    read as a vocabulary term, and a term is a word Whisper is told to
    expect, so the file's own commentary ended up in the prompt.
    """
    path = vocab_file()
    if not path.exists():
        return None
    terms = [stripped for line in path.read_text().splitlines()
             if (stripped := line.strip()) and not stripped.startswith("#")]
    return ", ".join(terms) + "." if terms else None


class OwwWake:
    """openWakeWord detector.

    Unlike the Vosk grammar, this scores acoustically rather than deciding
    between the phrase and everything-else -- which is why it can separate a
    phonetic neighbour at all. Measured here: the real phrase peaks ~0.996, a
    near miss ~0.898, unrelated speech 0.000.

    openWakeWord wants 1280-sample frames (80ms) and the capture loop hands
    out 1600 (100ms), so audio is rebuffered rather than resized upstream --
    the 100ms cadence is what the Whisper path and the level meter expect.
    """

    FRAME = 1280

    def __init__(self, model: str, threshold: float, verifier: str | None = None,
                 use_verifier: bool = True):
        import numpy as np
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from verifier import installed_verifiers, resolve_model

        from openwakeword.model import Model

        path, self.key = resolve_model(model)
        kwargs = {}
        if not use_verifier:
            verifier = ""
        if verifier is None:
            found = installed_verifiers().get(self.key)
            verifier = str(found) if found else None
        if verifier:
            kwargs = {"custom_verifier_models": {self.key: verifier},
                      "custom_verifier_threshold": 0.1}
        self.verifier = verifier
        self.threshold = threshold
        self._np = np
        self._model = Model(wakeword_model_paths=[str(path)], **kwargs)
        self._tail = np.empty(0, dtype=np.int16)
        self.phrase = model.replace("_", " ")
        #: Highest score seen in the most recent feed(), for the monitor.
        self.last_score = 0.0

    def reset(self) -> None:
        self._tail = self._np.empty(0, dtype=self._np.int16)
        if hasattr(self._model, "reset"):
            self._model.reset()

    def feed(self, pcm: bytes) -> bool:
        x = self._np.frombuffer(pcm, dtype=self._np.int16)
        self._tail = self._np.concatenate((self._tail, x))
        fired = False
        self.last_score = 0.0
        while len(self._tail) >= self.FRAME:
            frame, self._tail = self._tail[:self.FRAME], self._tail[self.FRAME:]
            best = max(self._model.predict(frame).values())
            self.last_score = max(self.last_score, best)
            if best >= self.threshold:
                fired = True
        if fired:
            self.reset()
        return fired


#: How strongly the decoder is pulled towards a keyword path (sherpa-onnx's
#: keywords_score). 0.5 was the best of 0.25/0.5/1/2 in FINDINGS §23 -- tuned
#: on that corpus, so treat it as a starting point; it is fixed rather than a
#: setting because the threshold is the one knob a person can reason about.
SHERPA_BOOST = 0.5

#: The constructor insists on a keywords file, and keywords given to a stream
#: are added to that file's, not substituted for them. So the file holds only
#: this -- a phone string nobody says, behind a threshold nothing reaches --
#: and every real keyword goes on the stream, where changing one costs a new
#: stream (under 1ms) instead of a new model (about a second).
_SHERPA_NEVER = "ZH ZH ZH ZH ZH ZH ZH ZH :0.01 #1.0 @_never"


#: Names the bundled en.phone lacks, spelled from its neighbours (SOR is
#: S AO1 R there). Only consulted for a word the file does not have.
EXTRA_PHONES = {
    "SORA": ["S", "AO1", "R", "AH0"],
}


#: Second pronunciations listened for alongside the dictionary's. A short
#: name gets few chances to land, and the model hears "Theo" as either
#: ending: on synthesized clips TH IY1 OW0 alone woke 8/30, both 9/30.
#: The shipped default only: the live list is the wakeAlsoSounds setting
#: (Config.wake_tuning), which starts out holding exactly this.
ALT_PHONES = {
    "theo": [["TH", "IY1", "AH0"]],
}

#: Phrases this many phones or shorter get SHORT_BOOST instead of
#: SHERPA_BOOST: a three-phone name has too little sound for the decoder to
#: settle on at 0.5. Measured for "theo": 0.5 -> 5/30, 1.5 -> 8/30 with no
#: false wakes, 3.0 -> 4/30 plus "Thank you"/"Rodeo" waking it.
SHORT_PHONES = 3
SHORT_BOOST = 1.5

#: Spotted alongside the names when fullStopAnytime is on, so "full stop"
#: stops everything at once: no wake word, no capture, no Whisper.
STOP_PHRASE = "full stop"


def sherpa_lexicon(model_dir: Path, words) -> dict[str, list[str]]:
    """The CMU-style phones for each of `words` the model's lexicon has.

    Only the words asked for are kept: the file is 3MB and the engine needs
    a handful of entries. A word with several pronunciations keeps the first,
    which is CMU's primary one.
    """
    want = {w.upper() for w in words}
    found: dict[str, list[str]] = {}
    with open(model_dir / "en.phone", encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if parts and parts[0] in want and parts[0] not in found:
                found[parts[0]] = parts[1:]
    for w in want - found.keys():
        if w in EXTRA_PHONES:
            found[w] = EXTRA_PHONES[w]
    return {w.lower(): p for w, p in found.items()}


def sherpa_keywords(phrases, lexicon: dict[str, list[str]],
                    threshold: float, alts: dict[str, list[list[str]]] | None = None,
                    short_boost: float = SHORT_BOOST) -> str:
    """The keyword text for a stream: one line per phrase.

    The tag after @ is what the spotter reports. It cannot hold a space, so
    "hey sarah" travels as hey_sarah and SherpaWake turns it back. `alts`
    holds other phone spellings per word (ALT_PHONES when not given); each
    one is another line with the same tag, so it wakes the same agent.
    """
    if alts is None:
        alts = ALT_PHONES
    lines = []
    for phrase in phrases:
        spellings = [[]]
        for word in phrase.split():
            options = [lexicon[word]]
            for alt in alts.get(word, []):
                if alt not in options:
                    options.append(alt)
            spellings = [s + o for s in spellings for o in options]
        for phones in spellings:
            boost = short_boost if len(phones) <= SHORT_PHONES else SHERPA_BOOST
            lines.append(f"{' '.join(phones)} :{boost} #{threshold:.2f} "
                         f"@{phrase.replace(' ', '_')}")
    return "\n".join(lines)


class SherpaWake:
    """sherpa-onnx keyword spotting: a small streaming recogniser constrained
    to the phrases it is given, so it scores acoustically like openWakeWord
    yet takes any phrase written as text, like Vosk -- names included.

    Fed every frame, never gated, for openWakeWord's reason: it decodes a
    contiguous stream, and frames cut out of the middle of a word are a word
    it cannot finish. FINDINGS §23 measured it ungated.
    """

    def __init__(self, model_dir: Path, threshold: float) -> None:
        import tempfile

        import numpy as np
        import sherpa_onnx

        self._np = np
        self.model_dir = model_dir
        self.threshold = threshold
        self.phrases: list[str] = []
        self._lexicon: dict[str, list[str]] = {}
        self._tokens: set[str] | None = None
        #: "also sounds like" entries the last listen_for() could not use,
        #: each with why, so the settings can say so.
        self.unusable: dict[str, str] = {}
        chunk = "epoch-13-avg-2-chunk-16-left-64.onnx"
        fd, kw = tempfile.mkstemp(suffix=".txt", prefix="agentvoice-kws-")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(_SHERPA_NEVER + "\n")
            self._spotter = sherpa_onnx.KeywordSpotter(
                tokens=str(model_dir / "tokens.txt"),
                encoder=str(model_dir / f"encoder-{chunk}"),
                decoder=str(model_dir / f"decoder-{chunk}"),
                joiner=str(model_dir / f"joiner-{chunk}"),
                keywords_file=kw, num_threads=1,
                keywords_score=SHERPA_BOOST, keywords_threshold=threshold)
        finally:
            os.unlink(kw)
        self._stream = None
        #: The phrase the most recent feed() spotted, or "".
        self.last_hit = ""

    def knows(self, word: str) -> bool:
        """Whether the lexicon has `word`, so it can be listened for."""
        word = word.lower()
        if word not in self._lexicon:
            self._lexicon.update(sherpa_lexicon(self.model_dir, [word]))
        return word in self._lexicon

    def tokens(self) -> set[str]:
        """The phones the model has a token for, from its tokens.txt."""
        if self._tokens is None:
            with open(self.model_dir / "tokens.txt", encoding="utf-8") as f:
                self._tokens = {line.split()[0] for line in f if line.split()}
        return self._tokens

    def alternatives(self, words, also: dict[str, list[str]]) -> dict[str, list[list[str]]]:
        """Phone spellings for each of `words` from wakeAlsoSounds.

        An entry in capitals is phones and every one must be a model token;
        one in lower case is words, and every word must be in the lexicon.
        Anything else is left out and noted in `unusable`, never raised: a
        typo in an advanced setting must not stop the wake word working.
        """
        out: dict[str, list[list[str]]] = {}
        self.unusable = {}
        for word in words:
            for alt in also.get(word, []):
                if alt.upper() == alt:
                    phones = alt.split()
                    bad = [p for p in phones if p not in self.tokens()]
                    if bad:
                        self.unusable[f"{word}: {alt}"] = f"no sound “{bad[0]}”"
                        continue
                else:
                    missing = [w for w in alt.split() if not self.knows(w)]
                    if missing:
                        self.unusable[f"{word}: {alt}"] = f"unknown word “{missing[0]}”"
                        continue
                    phones = [p for w in alt.split() for p in self._lexicon[w]]
                out.setdefault(word, []).append(phones)
        return out

    def listen_for(self, phrases: list[str], threshold: float,
                   also: dict[str, list[str]] | None = None,
                   short_boost: float = SHORT_BOOST) -> None:
        """Start a stream that spots exactly `phrases` at `threshold`.

        Cheap enough to call on any change: the model stays, only the stream
        is new. A word outside the lexicon raises ValueError naming it --
        callers check with knows() first, so this is the backstop. `also` is
        wakeAlsoSounds as Config.wake_tuning cleaned it; None means the
        shipped ALT_PHONES.
        """
        words = {w for p in phrases for w in p.split()}
        for word in words:
            if not self.knows(word):
                raise ValueError(f"its lexicon has no word “{word}”")
        self.phrases, self.threshold = list(phrases), threshold
        alts = None if also is None else self.alternatives(sorted(words), also)
        text = sherpa_keywords(self.phrases, self._lexicon, threshold,
                               alts=alts, short_boost=short_boost)
        self._stream = self._spotter.create_stream(text)

    def reset(self) -> None:
        if self._stream is not None:
            self._spotter.reset_stream(self._stream)

    def feed(self, pcm: bytes) -> str:
        """The phrase spotted in this frame, or ""."""
        self.last_hit = ""
        if self._stream is None:
            return ""
        x = self._np.frombuffer(pcm, dtype=self._np.int16)
        self._stream.accept_waveform(RATE, x.astype(self._np.float32) / 32768.0)
        while self._spotter.is_ready(self._stream):
            self._spotter.decode_stream(self._stream)
            tag = self._spotter.get_result(self._stream)
            if tag and not self.last_hit and tag != "_never":
                self.last_hit = tag.replace("_", " ")
                self._spotter.reset_stream(self._stream)
        return self.last_hit


def wanted_names(cfg) -> list[str]:
    """The extra agents' names, in the order they were added.

    Tolerates a settings object without agents(): the test stand-ins for
    Config are dicts, and a missing method means no extra agents.
    """
    agents = getattr(cfg, "agents", None)
    if not callable(agents):
        return []
    try:
        return [spec["name"] for spec in agents()]
    except Exception:
        return []


class Pipeline:
    def __init__(self, cfg: Config, whisper_override: str | None = None):
        import vosk
        vosk.SetLogLevel(-1)

        self._vosk = vosk
        self._model = None      # loaded on first use; see vosk_model_lazy()
        self._vocab = load_vocab()
        self._vocab_stamp = vocab_stamp()
        self.phrase = ""
        #: The extra agents' names this engine listens for besides `phrase`,
        #: and the ones it cannot: words Vosk's lexicon does not have, a name
        #: the main agent already answers to, or any name at all on
        #: openWakeWord, which knows only the phrase it was trained on.
        self.names: list[str] = []
        self.unheard: dict[str, str] = {}
        #: Which phrase fired last: `phrase` or one of `names`.
        self.heard_phrase = ""
        self.engine = "vosk"
        self._oww = None
        self._sherpa = None
        self._sherpa_spec = None
        self._loud_frames = 0
        self._refractory_until = 0.0
        self._whisper = None
        self._whisper_size = None
        self._whisper_override = whisper_override
        self._pool = None       # Whisper's one worker; see new_utterance()
        self.apply(cfg)

    def apply(self, cfg: Config) -> None:
        """Pick up the current knobs. Called between utterances only, so a
        turn in progress is never disturbed."""
        engine = cfg.get_str("engine")
        # Read first: building the sherpa engine decides from it whether the
        # Vosk model is worth keeping.
        self.cross_check = cfg.get_bool("wakeCrossCheck")
        tuning = cfg.wake_tuning() if hasattr(cfg, "wake_tuning") else {}
        #: Which engines vote in the second check, and how (crosscheck.decide).
        self.cc_engines = tuning.get("engines", "both")
        self.cc_trailing = tuning.get("trailing", crosscheck.MAX_TRAILING_WORDS)
        self.cc_hint = tuning.get("whisper_hint", True)
        #: "full stop" spotted in every frame (sherpa-onnx only).
        self.stop_keyword = (cfg.get_bool("fullStopAnytime")
                             if hasattr(cfg, "wake_tuning") else False)
        # The verifier's mtime belongs in the spec: retraining rewrites that
        # file, and without it the daemon keeps the copy it loaded at startup
        # for ever. A freshly trained verifier then appears to do nothing --
        # or worse, a replaced bad one goes on suppressing every wake.
        want = (engine,
                cfg.get_str("owwModel") if engine == "openwakeword"
                else cfg.get_str("phrase").lower(),
                self._verifier_stamp(cfg) if engine == "openwakeword" else 0.0,
                # In the spec, not assigned after the fact: openWakeWord takes
                # the verifier as a constructor argument, so turning it off
                # means building the engine without it. The threshold is the
                # opposite case -- a number the running engine can be handed.
                cfg.get_bool("useVerifier") if engine == "openwakeword" else False,
                # The extra agents' names are part of the grammar, so a new
                # one means a new recogniser.
                tuple(wanted_names(cfg)))
        if engine == "sherpa":
            want = self._sherpa_wake_spec(cfg)
        if want != getattr(self, "_wake_spec", None):
            self._build_wake(cfg, engine)
            # Recomputed, because building decides it: a fallback to Vosk
            # puts the names back into what needs a rebuild.
            self._wake_spec = (self._sherpa_wake_spec(cfg) if engine == "sherpa"
                               else want)
        if getattr(self, "_sherpa", None) is not None:
            self._sherpa_listen(cfg)
            # Switched off: nothing else on this engine needs Vosk.
            if not self._needs_vosk() and not self._partials_need_vosk():
                self._drop_vosk()

        self.lead_in_ms = cfg.get_int("leadInMs")
        self.trailing_ms = cfg.get_int("trailingSilenceMs")
        # 0 turns it off: every turn then waits out the full pause above.
        self.quick_end_ms = cfg.get_int("quickEndMs")
        self.min_utterance_ms = cfg.get_int("minUtteranceMs")
        self.max_utterance_ms = cfg.get_int("maxUtteranceMs")
        # The gate. Fixed, or the room's noise floor plus a margin: see
        # noise_floor.py. Plain numbers either way, so a change never rebuilds.
        self.fixed_db = float(cfg["micThresholdDb"])
        self.adaptive_gate = cfg.get_bool("adaptiveGate")
        if getattr(self, "_floor", None) is None:
            self._floor = NoiseFloor(CHUNK_MS)
        self._floor.margin_db = float(max(MARGIN_MIN, min(MARGIN_MAX,
                                                          cfg.get_int("gateMarginDb"))))
        if not self.adaptive_gate:
            # Switched off forgets the room, so switching it on again learns
            # the room it is in then, not the one it was in last week.
            self._floor.reset()
        self.threshold_db = (self._floor.gate(self.fixed_db) if self.adaptive_gate
                             else self.fixed_db)
        #: The wake word's own gate (the Vosk grammar, the second check's
        #: bursts): the same with the gate fixed, a little lower following
        #: the room. See noise_floor.WAKE_SLACK_DB.
        self.wake_gate_db = (self._floor.wake_gate(self.fixed_db) if self.adaptive_gate
                             else self.fixed_db)
        # Assigned here rather than added to the spec above, like every other
        # knob on this list: it needs a different number, not a different model,
        # and a rebuild would drop and reload ~100MB for a slider move.
        #
        # It was the one openWakeWord knob that lived on the engine object and
        # was never updated afterwards. Dragging the slider printed "knobs
        # updated" and changed nothing until the service restarted -- so a
        # detection threshold of 90, which a locally trained model cannot reach,
        # survived being set to 63 and then 51, and the wake word never fired.
        # The accidental cure was switching engines and back, because that does
        # change the spec, which rebuilt the engine at whatever the number had
        # become by then.
        if self._oww is not None:
            self._oww.threshold = cfg.get_int("owwThresholdPct") / 100.0
        self.refractory_ms = int(cfg["refractoryMs"])
        self.wake_confidence = float(cfg["wakeConfidence"])
        # Plain numbers on the burst cutter: a new window costs nothing.
        if hasattr(cfg, "wake_tuning"):
            tuning = cfg.wake_tuning()
            cutter = self._burst_cutter()
            cutter.min_ms = tuning["burst_min_ms"]
            cutter.max_ms = tuning["burst_max_ms"]
        # Changing the transcription model used to be a silent no-op: it was
        # built once in __init__ and never consulted again, so the setting
        # appeared to do nothing until the service restarted.
        wanted = self._whisper_override or cfg.get_str("model")
        if wanted != self._whisper_size:
            self._load_whisper(wanted)

        self._partials = cfg.get_str("livePartials")
        self._log_speech = cfg.get_bool("logSpeech")
        self.conversation = cfg.get_bool("conversationMode")
        self.follow_up_ms = cfg.get_int("followUpMs")
        # 600ms of continuous speech-level audio before a partial may wake
        # it. Written as a duration rather than a frame count because the
        # frame is 200ms, and this was described as 300ms for as long as the
        # frame was described as 100ms.
        self.min_loud_frames = max(1, 600 // CHUNK_MS)

    def _sherpa_wake_spec(self, cfg: Config) -> tuple:
        """What needs a new sherpa-onnx model, as opposed to a new stream.

        The phrase is in it because a word the lexicon lacks means falling
        back to Vosk, a rebuild either way. The names and the threshold are
        not: they go on the stream. Once it has fallen back, though, Vosk is
        what is listening and its grammar does hold the names, so they rejoin
        the spec -- otherwise a new agent would never reach the grammar.
        """
        want = ("sherpa", cfg.get_str("phrase").lower(), str(sherpa_model() or ""))
        if getattr(self, "_sherpa_fell_back", False):
            want += (tuple(wanted_names(cfg)),)
        return want

    @property
    def detection_threshold(self) -> float | None:
        """The engine's firing threshold, or None on Vosk, which has a
        confidence bar instead."""
        if self._oww is not None:
            return self._oww.threshold
        if getattr(self, "_sherpa", None) is not None:
            return self._sherpa.threshold
        return None

    @staticmethod
    def _verifier_stamp(cfg: Config) -> float:
        """Modification time of the verifier this engine would load, or 0."""
        try:
            from verifier import installed_verifiers, resolve_model
            _, key = resolve_model(cfg.get_str("owwModel"))
            found = installed_verifiers().get(key)
            return found.stat().st_mtime if found else 0.0
        except Exception:
            return 0.0

    def _build_wake(self, cfg: Config, engine: str) -> None:
        """Swap the wake engine. Vosk takes any phrase and scores phonetic
        neighbours as high as the real one; openWakeWord has four pretrained
        phrases (plus anything trained locally) and real rejection."""
        self.engine = engine
        if getattr(self, "_sherpa", None) is not None and engine != "sherpa":
            self._sherpa = None
            self._release()
        if engine == "sherpa":
            try:
                self._build_sherpa(cfg)
                self._sherpa_fell_back = False
                return
            except Exception as e:
                self._sherpa_fell_back = True
                self._sherpa = None
                self._release()
                print(f"  {YEL}sherpa-onnx unavailable ({type(e).__name__}: {e});"
                      f" falling back to Vosk{OFF}")
                self.engine = "vosk"
        if engine == "openwakeword":
            try:
                self._oww = OwwWake(cfg.get_str("owwModel"),
                                    cfg.get_int("owwThresholdPct") / 100.0,
                                    use_verifier=cfg.get_bool("useVerifier"))
                self.phrase = self._oww.phrase
                self.names = []
                self.unheard = {n: "the openWakeWord engine hears only its "
                                   "own phrase — use Vosk for named agents"
                                for n in wanted_names(cfg)}
                if self._oww.verifier:
                    verifier = "with your verifier"
                elif not cfg.get_bool("useVerifier"):
                    # Said plainly, because "no verifier yet" would describe a
                    # trained one that is switched off as though none existed.
                    verifier = "anyone may wake it -- your verifier is off"
                else:
                    verifier = "no verifier yet"
                print(f"  {DIM}wake: openWakeWord {self._oww.key} "
                      f"@ {self._oww.threshold:.2f} ({verifier}){OFF}")
                # Nothing needs Vosk on this engine unless partials are
                # explicitly on. Give the memory back rather than hold it for
                # an engine the user has just left.
                if not self._partials_need_vosk():
                    self._drop_vosk()
                return
            except Exception as e:
                print(f"  {YEL}openWakeWord unavailable ({type(e).__name__}: {e});"
                      f" falling back to Vosk{OFF}")
                self.engine = "vosk"
        if self._oww is not None:
            self._oww = None
            self._release()
        self.phrase = cfg.get_str("phrase").lower()
        self._choose_names(wanted_names(cfg))
        self._reset_wake()

    def _build_sherpa(self, cfg: Config) -> None:
        """Load the keyword spotter and start listening. Raises when it cannot
        run -- no package, no model, a phrase word outside its lexicon -- and
        the caller falls back to Vosk."""
        model = sherpa_model()
        if model is None:
            raise FileNotFoundError("no sherpa-onnx model installed -- "
                                    "run install.sh --sherpa")
        if self._oww is not None:
            self._oww = None
        self._sherpa = SherpaWake(model, cfg.get_int("sherpaThresholdPct") / 100.0)
        self.phrase = cfg.get_str("phrase").lower()
        missing = [w for w in self.phrase.split() if not self._sherpa.knows(w)]
        if missing:
            raise ValueError(f"its lexicon has no word “{missing[0]}”, "
                             f"so it cannot hear “{self.phrase}”")
        self._sherpa_spec = None
        self._sherpa_listen(cfg)
        second = " + second check" if getattr(self, "cross_check", False) else ""
        print(f"  {DIM}wake: sherpa-onnx @ {self._sherpa.threshold:.2f}"
              f" ({', '.join(self._sherpa.phrases)}){second}{OFF}")
        # As on openWakeWord: nothing needs Vosk here unless partials are
        # explicitly on or the second check votes with it, so give its
        # memory back.
        if not self._partials_need_vosk() and not self._needs_vosk():
            self._drop_vosk()

    def _partials_need_vosk(self) -> bool:
        """"on" and "accurate" load Vosk for the live text; "auto" never does."""
        return getattr(self, "_partials", "auto") in ("on", "accurate")

    def _needs_vosk(self) -> bool:
        """Whether the second check votes with Vosk at all."""
        return (getattr(self, "cross_check", False)
                and getattr(self, "cc_engines", "both") != "whisper")

    def _sherpa_listen(self, cfg: Config) -> None:
        """Point the spotter at the current names and threshold.

        Assigned after the spec check rather than in it: both live on the
        stream, so a slider move or a new agent costs a stream, not the
        second it takes to load the model again.
        """
        names = tuple(wanted_names(cfg))
        threshold = cfg.get_int("sherpaThresholdPct") / 100.0
        tuning = cfg.wake_tuning() if hasattr(cfg, "wake_tuning") else {}
        boost = tuning.get("short_boost", SHORT_BOOST)
        also = tuning.get("also_sounds")
        frozen = (tuple(sorted((k, tuple(v)) for k, v in also.items()))
                  if also is not None else None)
        stop = bool(getattr(self, "stop_keyword", False))
        spec = (names, threshold, boost, frozen, stop)
        if spec == self._sherpa_spec:
            return
        if self._sherpa_spec is None or names != self._sherpa_spec[0]:
            self._choose_names(list(names))
        self._sherpa_spec = spec
        phrases = [self.phrase, *self.names]
        # Its own keyword, so it stops things without a wake word first. Not
        # added when a name already is "full stop" -- that agent wins.
        if stop and STOP_PHRASE not in phrases:
            phrases.append(STOP_PHRASE)
        self._sherpa.listen_for(phrases, threshold, also=also, short_boost=boost)
        for entry, why in getattr(self._sherpa, "unusable", {}).items():
            print(f"  {YEL}also sounds like “{entry}” not used: {why}{OFF}",
                  flush=True)

    def _choose_names(self, wanted: list[str]) -> None:
        """Keep the names Vosk can actually hear, and say why for the rest.

        A grammar silently drops a word its lexicon does not have, so a name
        made of one would be listened for and never heard -- the reason
        "hey omarchy" is not a phrase option. Vosk can be asked, so it is.
        """
        self.names, self.unheard = [], {}
        main = set(self.phrase.split())
        for name in wanted:
            if name == self.phrase:
                self.unheard[name] = "the main agent already answers to it"
                continue
            if set(name.split()) <= main:
                # "computer" inside "hey computer": the main phrase would be
                # matched first and this one could never win.
                self.unheard[name] = "it is part of the main wake phrase"
                continue
            missing = [w for w in name.split() if not self._knows(w)]
            if missing:
                self.unheard[name] = (f"the wake engine does not know the "
                                      f"word “{missing[0]}”")
                continue
            self.names.append(name)
        for name, why in self.unheard.items():
            print(f"  {YEL}agent “{name}” cannot be woken: {why}{OFF}")

    def _knows(self, word: str) -> bool:
        """Whether the wake engine's lexicon has `word`. True when it cannot
        say."""
        if getattr(self, "_sherpa", None) is not None:
            return self._sherpa.knows(word)
        try:
            find = self.vosk_model_lazy().vosk_model_find_word
        except AttributeError:
            return True
        try:
            return find(word) >= 0
        except Exception:
            return True

    def phrase_in(self, text: str) -> str:
        """The phrase `text` holds -- the main one or an agent's name -- or "".

        Whole words, longest first, so "hey computer" is not mistaken for an
        agent called "computer" that happens to be inside it.
        """
        padded = f" {text} "
        found = [p for p in (self.phrase, *getattr(self, "names", ()))
                 if p and f" {p} " in padded]
        return max(found, key=len) if found else ""

    @staticmethod
    def _release() -> None:
        """Hand freed pages back to the OS.

        Dropping the last reference to a model is not enough: glibc keeps the
        freed arenas and RSS barely moves. Measured here -- releasing the Vosk
        model returns 67MB on the drop alone and 117MB after malloc_trim;
        openWakeWord 57MB and 71MB. Without the trim an engine swap looks
        exactly like a leak.
        """
        import ctypes
        import gc
        gc.collect()
        try:
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            pass        # not glibc, or no malloc_trim; the gc still happened

    def _drop_vosk(self) -> None:
        if self._model is None:
            return
        self._wake = None
        self._model = None
        self._release()

    def reconcile_vocab(self) -> None:
        """Re-read the term list if the file behind it has changed.

        Cheap: one stat, and the prompt is passed per transcription rather than
        baked into the model, so nothing is rebuilt. Called on the same poll as
        the voice, not behind the config-changed guard -- editing a file is not
        a setting change.
        """
        stamp = vocab_stamp()
        if stamp == self._vocab_stamp:
            return
        self._vocab_stamp = stamp
        self._vocab = load_vocab()
        n = len(self._vocab.split(",")) if self._vocab else 0
        print(f"  {CYA}vocabulary: {n} terms{OFF}")

    def _load_whisper(self, size: str) -> None:
        """(Re)build the transcription model, releasing the previous one."""
        from faster_whisper import WhisperModel
        if self._whisper is not None:
            self._whisper = None
            self._release()
        print(f"  {DIM}loading whisper {size}...{OFF}", end="", flush=True)
        self._whisper = WhisperModel(size, device="cpu",
                                     compute_type="int8", cpu_threads=4)
        self._whisper_size = size
        n = len(self._vocab.split(",")) if self._vocab else 0
        print(f"{cursor_home()}  {DIM}whisper {size} ready"
              f"{f', {n} vocab terms' if n else ''}{OFF}{' ' * 24}")

    def vosk_model_lazy(self):
        """The Vosk acoustic model, loaded the first time something needs it.

        It costs 114MB resident -- measured, see bench/FINDINGS.md -- and on the
        openWakeWord engine it buys only the live partial text shown while you
        speak. Endpointing is energy-based and does not need it. So it is no
        longer loaded just in case.
        """
        if self._model is None:
            found = vosk_model()
            if found is None:
                raise FileNotFoundError(
                    "no Vosk model installed — run install.sh, or use the "
                    "openWakeWord engine, which needs no separate download")
            self._model = self._vosk.Model(str(found))
        return self._model

    def _reset_wake(self) -> None:
        self._wake = self._vosk.KaldiRecognizer(
            self.vosk_model_lazy(), RATE,
            json.dumps([self.phrase, *self.names, "[unk]"]))
        # Word-level confidence is the second line of defence. A grammar has
        # to choose between the phrase and [unk], so anything phonetically
        # near the trigger scores as a match -- which is how a podcast on a
        # phone across the room wakes it.
        self._wake.SetWords(True)

    def feed_wake(self, pcm: bytes, level_db: float) -> bool:
        """True when the trigger phrase lands loudly and confidently enough.

        Three gates, because any one of them alone is too easy to trip:
        the frame has to be louder than the room, the phrase has to survive a
        sustained run of such frames rather than one blip, and the recogniser
        has to be reasonably sure of the words it matched.
        """
        # A detector's internal buffers still hold the audio that just fired,
        # so the next few frames can fire again on the same utterance.
        # reset() does not fully clear them -- measured: feeding an unrelated
        # clip straight after a positive one still fired. A refractory window
        # is the reliable guard.
        if time.time() < self._refractory_until:
            return False

        # Measured cost of doing this, on the 2014 dev machine: openWakeWord
        # inference is 2.97ms of CPU per 80ms frame -- 3.7% of one core -- and
        # the whole daemon idles at 5.3%. Cheap enough that gating it to save
        # CPU was never worth the detection it cost.
        #
        # openWakeWord's own vad_threshold does NOT help here. It runs Silero
        # VAD *after* the predictions are computed and zeroes them when the VAD
        # disagrees, so it adds about 22% to the inference cost rather than
        # saving any. It is a false-accept tool, and not even the right one for
        # the case we care about: a podcast saying the wake phrase is speech,
        # so a VAD passes it happily.
        #
        # openWakeWord is fed EVERY frame, gate or no gate. It scores
        # acoustically and rejects unrelated speech on its own -- measured at
        # 0.000 -- so it needs no energy gate, and applying one actively
        # breaks it: the model builds embeddings over a sliding window of
        # contiguous audio, and a gate at -36 dBFS discarded 70% of the frames
        # in a recorded "hey jarvis", fragmenting the phrase. Measured on the
        # same twelve clips: 9/12 detected through the gate, 12/12 without it,
        # and every peak rose to 1.00.
        #
        # The gate below still guards the Vosk grammar, which does need it --
        # a grammar will happily match the phrase against room noise.
        # sherpa-onnx is ungated for the same reason: it decodes a contiguous
        # stream, and it was measured that way (FINDINGS §23).
        if getattr(self, "_sherpa", None) is not None:
            hit = self._sherpa.feed(pcm)
            if hit:
                self._refractory_until = time.time() + self.refractory_ms / 1000.0
                self.heard_phrase = hit
                self.wake_how = "spotter"
                # The caller tells "full stop" apart by heard_phrase.
                self._burst_cutter().clear()
                return True
            if getattr(self, "cross_check", False):
                return self._second_check(pcm, level_db)
            return False

        if self._oww is not None:
            if self._oww.feed(pcm):
                self._refractory_until = time.time() + self.refractory_ms / 1000.0
                self.heard_phrase = self.phrase
                self.wake_how = "openwakeword"
                return True
            return False

        if level_db < self.wake_gate_db:
            ended = self._loud_frames > 0
            self._loud_frames = 0
            if not ended:
                return False
            # The speech has just stopped, so ask for the verdict now. Frames
            # under the gate are never fed to the grammar, so it never hears
            # the silence it needs to finish a word on its own: a name said
            # alone with a pause after it reached only the partial path, which
            # wants 600ms of loud audio. "computer" is three syllables and
            # passes; "sarah" is two and never woke -- measured on synthesized
            # clips, see bench/FINDINGS.md. FinalResult() carries word
            # confidence, so the bar below still applies, and it leaves the
            # recogniser ready for the next utterance.
            final = True
            payload = json.loads(self._wake.Result()
                                 if self._wake.AcceptWaveform(pcm)
                                 else self._wake.FinalResult())
            text = payload.get("text", "")
        else:
            self._loud_frames += 1
            final = self._wake.AcceptWaveform(pcm)
            if final:
                payload = json.loads(self._wake.Result())
                text = payload.get("text", "")
            else:
                payload = {}
                text = json.loads(self._wake.PartialResult()).get("partial", "")
        matched = self.phrase_in(text)
        if not matched:
            return False
        if final:
            words = [w for w in payload.get("result", [])
                     if w.get("word") in matched.split()]
            conf = (sum(w.get("conf", 0.0) for w in words) / len(words)) if words else 0.0
        else:
            conf = None            # partials carry no confidence

        # A partial can only wake it after enough consecutive loud frames to
        # be actual speech; a final also has to clear the confidence bar.
        if conf is None:
            if self._loud_frames < self.min_loud_frames:
                return False
        elif conf < self.wake_confidence:
            self._near(f"vosk confidence {conf:.2f} < {self.wake_confidence:.2f}")
            if speech_is_logged(getattr(self, "_log_speech", False)):
                print(f"  {DIM}(rejected \"{safe_for_terminal(text)}\" — confidence "
                      f"{conf:.2f} < {self.wake_confidence:.2f}){OFF}")
            else:
                print(f"  {DIM}(rejected — confidence {conf:.2f} < "
                      f"{self.wake_confidence:.2f}){OFF}")
            self._reset_wake()
            self._loud_frames = 0
            return False

        self._reset_wake()
        self._loud_frames = 0
        self._refractory_until = time.time() + self.refractory_ms / 1000.0
        self.heard_phrase = matched
        self.wake_how = "vosk"
        return True

    def learn_room(self, level_db: float) -> bool:
        """Feed the noise floor one frame of room, and move the gate with it.

        Only frames that cannot be somebody talking to us: the caller feeds
        the wake phase alone, outside the deaf window and never while we are
        speaking. A no-op with the gate fixed. True when the gate moved.
        """
        if not getattr(self, "adaptive_gate", False):
            return False
        self._floor.feed(level_db)
        before = self.threshold_db
        self.threshold_db = self._floor.gate(self.fixed_db)
        self.wake_gate_db = self._floor.wake_gate(self.fixed_db)
        return self.threshold_db != before

    @property
    def floor_db(self) -> float | None:
        floor = getattr(self, "_floor", None)
        return floor.floor_db if floor is not None and self.adaptive_gate else None

    def _near(self, why: str) -> None:
        """A wake the engines came close to and turned down, for the wake
        test. Reasons only: never what was said."""
        near = getattr(self, "near_misses", None)
        if near is None:
            near = self.near_misses = []
        near.append(why)
        del near[:-20]

    def take_near_misses(self) -> list[str]:
        near, self.near_misses = getattr(self, "near_misses", None) or [], []
        return near

    def _burst_cutter(self) -> crosscheck.Bursts:
        if getattr(self, "_bursts", None) is None:
            self._bursts = crosscheck.Bursts(CHUNK_MS)
        return self._bursts

    def _second_check(self, pcm: bytes, level_db: float) -> bool:
        """Ask Vosk and Whisper about a short burst the spotter let pass.

        See crosscheck.py for the rule and its numbers. Runs only when a
        burst of the right length has just ended, and Whisper only when Vosk
        heard a name or cannot vote for one, so background talk costs a
        grammar pass rather than a transcription.
        """
        audio = self._burst_cutter().feed(pcm, level_db >= self.wake_gate_db)
        if audio is None:
            return False
        names = [self.phrase, *self.names]
        mode = getattr(self, "cc_engines", "both")
        t0 = time.perf_counter()
        vosk, has_vote = ("", set()) if mode == "whisper" else self._vosk_vote(audio, names)
        # Whisper costs about a second, so it is skipped when its vote
        # cannot change the answer: Vosk alone decides, or both must agree
        # and Vosk heard nothing it could have heard.
        if mode == "vosk" or (mode == "both" and not vosk and set(names) <= has_vote):
            text = ""
            if mode == "both":
                return False
        else:
            try:
                text = self._whisper_names(audio, names)
            except Exception as e:
                print(f"  {YEL}second check failed: {type(e).__name__}: {e}{OFF}")
                return False
        name, why = crosscheck.decide(names, has_vote, vosk, text, mode=mode,
                                      trailing=getattr(self, "cc_trailing",
                                                       crosscheck.MAX_TRAILING_WORDS))
        ms = (time.perf_counter() - t0) * 1000
        heard = (f" — whisper heard \"{safe_for_terminal(text.strip())}\""
                 if speech_is_logged(getattr(self, "_log_speech", False)) else "")
        if not name:
            print(f"  {DIM}(second check: no wake — {why}{heard}, {ms:.0f}ms){OFF}",
                  flush=True)
            if why:
                self._near(f"second check: {why}")
            return False
        print(f"  {DIM}(second check: {name} by {why}{heard}, {ms:.0f}ms){OFF}",
              flush=True)
        self._refractory_until = time.time() + self.refractory_ms / 1000.0
        self.heard_phrase = name
        self.wake_how = "second check"
        self._sherpa.reset()
        return True

    def _vosk_vote(self, audio: bytes, names: list[str]) -> tuple[str, set[str]]:
        """(name Vosk heard or "", the names it could have heard)."""
        try:
            model = self.vosk_model_lazy()
            find = model.vosk_model_find_word
        except Exception:
            return "", set()
        grammar, means = crosscheck.vosk_grammar(names, lambda w: find(w) >= 0)
        if not grammar:
            return "", set()
        rec = self._vosk.KaldiRecognizer(model, RATE,
                                         json.dumps([*grammar, "[unk]"]))
        rec.AcceptWaveform(audio)
        text = json.loads(rec.FinalResult()).get("text", "")
        return crosscheck.vosk_heard(text, means), set(means.values())

    def _whisper_names(self, audio: bytes, names: list[str]) -> str:
        """Whisper's reading of a burst, prompted with the names -- the
        prompt measured in FINDINGS §24. Through the one Whisper worker, so
        it never runs beside a piece of an abandoned utterance."""
        prompt = (", ".join(n.title() for n in names) + "."
                  if getattr(self, "cc_hint", True) else None)
        if self._pool is None:
            from concurrent.futures import ThreadPoolExecutor
            self._pool = ThreadPoolExecutor(max_workers=1,
                                            thread_name_prefix="whisper")
        return self._pool.submit(self._whisper_text, audio, prompt).result(timeout=10)

    def new_capture(self):
        """A recogniser for the live partial text, or None when it is not worth
        the memory. The caller must cope with None: the turn still works, it
        just shows nothing until Whisper returns."""
        if not self.want_partials:
            return None
        return self._vosk.KaldiRecognizer(self.vosk_model_lazy(), RATE)

    @property
    def want_partials(self) -> bool:
        # "auto" means free-only: show partials when the Vosk model is already
        # resident for the wake word, and do not load it purely for them.
        if self._partials == "off":
            return False
        if self._partials in ("on", "accurate"):
            return True
        return self.engine == "vosk"

    @property
    def accurate_partials(self) -> bool:
        """Vosk's text first, each part replaced by Whisper's at the pauses."""
        return getattr(self, "_partials", "auto") == "accurate"

    def _whisper_text(self, pcm: bytes, prompt: str | None) -> str:
        import numpy as np
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = self._whisper.transcribe(
            audio, language="en", beam_size=1, initial_prompt=prompt)
        return " ".join(s.text for s in segments)

    def transcribe(self, pcm: bytes) -> tuple[str, float]:
        """A whole recording at once. The bench and --simulate path; the live
        loop transcribes as it goes -- see new_utterance()."""
        t0 = time.perf_counter()
        text = self._whisper_text(pcm, self._vocab)
        # Cleaned here, once, rather than in each adapter: this is the only
        # place a transcript is made, and every backend puts it straight into
        # argv where a leading hyphen would be read as a flag.
        return as_prompt(text), (time.perf_counter() - t0) * 1000

    def transcribe_piece(self, pcm: bytes, context: str) -> str:
        """One piece of an utterance, with what was said before it.

        The vocabulary first, because it is the part measured to matter (41%
        fewer domain errors for 41ms), then the tail of the transcript so far,
        so a sentence split at a pause is still heard as one.
        """
        prompt = " ".join(p for p in (self._vocab, context) if p) or None
        return self._whisper_text(pcm, prompt)

    def new_utterance(self) -> Utterance:
        """A capture that transcribes itself at each pause. See eager.py.

        One worker for every utterance, so Whisper is never asked two things
        at once -- a piece still running from a capture that was abandoned
        simply finishes before the next one starts.
        """
        if self._pool is None:
            from concurrent.futures import ThreadPoolExecutor
            self._pool = ThreadPoolExecutor(max_workers=1,
                                            thread_name_prefix="whisper")
        return Utterance(self.transcribe_piece, self._pool.submit,
                         bytes_per_s=RATE * 2, frame_bytes=CHUNK * 2)


#: Every value the state file can carry, in the order a turn moves through
#: them. Declared rather than left implicit because three separate files
#: switch on these -- the bar widget's icon, its label, and the HUD's "busy"
#: test -- and a state nothing draws reads as "STARTING" forever. The tests
#: and the check script read this list rather than grepping for publish()
#: calls, which is what they used to do and what broke the moment one of
#: these moved into a variable.
STATES = ("off", "locked", "yielded", "listening", "capture", "transcribing",
          "thinking", "speaking", "followup")

#: The subset that means a turn is underway, i.e. what the HUD shows for.
BUSY_STATES = ("capture", "transcribing", "thinking", "speaking", "followup")

#: A turn this long ends with the `done` chime. Short answers do not need
#: one -- you are still listening when they end -- and every turn having one
#: would make it noise.
LONG_TURN_S = 15.0

#: How long past its own length a chime is assumed to still be sounding:
#: PipeWire's output latency means it leaves the speaker a little after it was
#: started.
CHIME_TAIL_S = 0.1

#: How long `agentvoice lock` outranks the poll. Long enough for a compositor
#: to raise its lock surface and for `solitaryBlockedBy` to admit it, short
#: enough that a stale announcement cannot hold the microphone shut.
LOCK_HOLD_S = 10.0

#: How often the idle poll asks where the sound is going: headphones go on
#: and come off between turns, and asking spawns pactl twice (23ms).
OUTPUT_TTL_S = 10.0
#: How old that answer may be before a reply asks again itself, in front of
#: a sentence. Only reached after a long chain of follow-ups, which keep the
#: loop out of the idle poll.
OUTPUT_STALE_S = 60.0

#: Frames kept from before barge-in fired, to start the capture with: 600ms.
#: The detector needs about 100ms of speech and drains in 200ms frames, so
#: the person's first word can be two frames back from the one that tripped
#: it. On a headset the extra is silence; through speakers it may hold a
#: word of our own, which Whisper has to read past.
BARGE_PREROLL_FRAMES = 3


def other_recorders(our_pid: int) -> list[str] | None:
    """Names of anything else capturing audio right now.

    `[]` for nobody, a list of names for somebody, and **None when the
    question cannot be answered** -- no pw-dump, no PipeWire, malformed
    output, a timeout. None is not False: the caller keeps whatever it last
    knew, exactly as it does for an undetermined lock, because guessing
    "nobody" would reopen the microphone over somebody else's recording and
    guessing "somebody" would shut it for good on a machine that cannot say.

    Read from `pw-dump` rather than counted from `pactl` because the answer
    needs a join: a capture stream's own node does not carry the pid that
    owns it -- the *client* object does -- and without the pid there is no
    way to tell our own stream from anyone else's except by matching on a
    name, which `agentvoice monitor` shares with the daemon exactly.

    Only streams PipeWire reports as `running` count. A browser with a tab
    open keeps idle capture nodes around, and treating those as "recording"
    would mute the wake word permanently on an ordinary desktop.
    """
    try:
        out = subprocess.run(["pw-dump"], capture_output=True, text=True,
                             timeout=5).stdout
        graph = json.loads(out)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    # A list of anything-but-objects is not pw-dump's output, and answering
    # "nobody is recording" to garbage is the fail-open direction: it would
    # reopen the microphone over somebody else's call.
    if not isinstance(graph, list) or not all(
            isinstance(obj, dict) for obj in graph):
        return None

    # Two passes: a client can appear after the node that points at it.
    pids: dict[str, str] = {}
    streams: list[dict] = []
    for obj in graph:
        if not isinstance(obj, dict):
            continue
        props = ((obj.get("info") or {}).get("props") or {})
        if not isinstance(props, dict):
            continue
        if str(obj.get("type", "")).endswith(":Client"):
            pid = (props.get("application.process.id")
                   or props.get("pipewire.sec.pid"))
            if pid is not None:
                pids[str(obj.get("id"))] = str(pid)
        elif props.get("media.class") == "Stream/Input/Audio":
            if (obj.get("info") or {}).get("state") == "running":
                streams.append(props)

    others = []
    for props in streams:
        owner = pids.get(str(props.get("client.id")))
        if owner is not None and owner == str(our_pid):
            continue
        others.append(str(props.get("application.name")
                          or props.get("node.name") or "something"))
    return others


def cursor_home(clear: int = 0) -> str:
    """The in-place redraw sequence, on a terminal and nowhere else.

    A live partial is drawn over itself as you speak, so the line that
    replaces it returns the cursor and paints across whatever was longer.
    None of that is true of a journal: systemd stores the carriage return
    literally and journalctl renders the whole record as "[149B blob data]".

    Which hid the exact lines that must never be hidden. Found from a real
    turn: with `logSpeech` off the completed transcript is not printed, so
    the lone carriage return that erased the partial merged into the next
    line and took `3.2s audio, whisper 294ms` -- the timings -- into the
    blob with it. Turning the privacy setting on made the diagnostics
    disappear, and `(nothing heard)`, `(too short, discarded)` and
    `whisper ready` were being swallowed the same way whatever it was set
    to. The words are a setting; the structural lines are not, and being
    unreadable in the default renderer is a way of being hidden.

    `clear` is how wide a field to blank first, for a line that may be
    shorter than what it replaces.
    """
    if not sys.stdout.isatty():
        return ""
    return f"\r{' ' * clear}\r" if clear else "\r"


def speech_is_logged(enabled: bool) -> bool:
    """Whether the words themselves may be printed.

    A terminal is ephemeral and somebody is looking at it, so a foreground
    run always shows what it heard and what it answered -- that is the
    interface. The journal is neither: it keeps entries for weeks, which
    makes "log the replies" mean "keep a transcript of everything the agent
    read out, including file contents and key names, until it rotates".

    Off by default for that reason, and the structural lines -- wake events,
    timings, tool markers, errors, lock transitions -- are never gated by
    it. Nearly every bug in this project was found from those rather than
    from the words.
    """
    return enabled or sys.stdout.isatty()


def session_locked() -> bool | None:
    """True while the compositor holds a session lock, None when unknowable.

    Omarchy ships the detector -- `omarchy-hyprland-session-locked` -- and it
    is used rather than reimplemented because the subtleties belong to
    whoever maintains it: Hyprland reports no lock state directly, so it
    infers one from `solitaryBlockedBy` containing LOCK, and that stays set
    once the lock's client has died, which is the case worth catching.

    Its exit codes are 0 locked, 1 unlocked, 2 undetermined. Undetermined
    comes back as None here rather than as either answer, and the caller
    keeps whatever it last knew: `false` would be the fail-open direction,
    and `true` would leave the microphone shut for good on a machine with no
    compositor to ask -- which is every development run in a terminal.

    logind's LockedHint is the fallback for a machine without the helper.
    Omarchy's own lock does not go through `loginctl lock-session`, so the
    hint is not a substitute here; it is better than nothing elsewhere.
    """
    try:
        done = subprocess.run(["omarchy-hyprland-session-locked"],
                              capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return _logind_locked()
    if done.returncode in (0, 1):
        return done.returncode == 0
    return None


def _logind_locked() -> bool | None:
    session = os.environ.get("XDG_SESSION_ID", "")
    if not session:
        return None
    try:
        done = subprocess.run(
            ["loginctl", "show-session", session, "-p", "LockedHint",
             "--value"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    answer = done.stdout.strip().lower()
    return True if answer == "yes" else (False if answer == "no" else None)


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


def _limit_hits_from(state) -> dict:
    """Today's count of turns cut at maxUtteranceMs, as the state file a
    previous run of the daemon left it (phase M2, bug C), else none.

    The state file lives in the runtime folder, which outlives a restart of
    the service but not a reboot, which is about what "today" should mean
    here. Anything unreadable, from another day, or the wrong shape is no
    count at all -- this is a note on a settings page, not a guard."""
    fresh = {"date": _today(), "today": 0, "last": 0}
    path = getattr(state, "path", None)
    try:
        saved = json.loads(Path(path).read_text())["limit_hits"]
        if (isinstance(saved, dict) and saved.get("date") == fresh["date"]
                and isinstance(saved.get("today"), int) and saved["today"] >= 0
                and isinstance(saved.get("last"), (int, float))):
            return {"date": fresh["date"], "today": saved["today"],
                    "last": saved["last"]}
    except (OSError, TypeError, ValueError, KeyError):
        pass
    return fresh


#: Phase M4: commands found inside a sentence that act inside the agent's
#: own turn, where its chat is (`Daemon.chat_in_sentence`). The others
#: switch the open microphone, which is the run loop's.
_IN_TURN_COMMANDS = ("new_chat", "continue_chat")


def _empty_turn() -> dict:
    """Nothing heard yet, nothing answered.

    Published the instant the wake word fires. The capture state used to carry
    whatever the *previous* turn had left in it, so saying the wake word showed
    the last question and the last answer while it listened for the next one.
    A readout of a finished exchange is worse than no readout: it is the right
    shape in the wrong tense.

    All four keys are always present, because publish() merges what it is given
    and the widget only updates a field it is sent -- an absent key leaves the
    old value on screen rather than clearing it.
    """
    return {"transcript": "", "ms": 0, "audio_s": 0.0, "reply": "",
            "latency_ms": 0}


#: What a turn heard on the open microphone is sent with, when "only answer
#: if it's meant for you" is on. The agent is the only thing here that can
#: tell a request from the television, so it is asked to.
OPEN_MIC_PREAMBLE = (
    "[Heard on an open microphone, without your name. If this was not said to "
    "you -- someone talking to another person, a television, music -- reply "
    "with exactly SKIP and nothing else.]\n")
OPEN_MIC_SKIP = "SKIP"

#: A session id that may go into a terminal's argv: what Claude Code and
#: Codex print, and nothing a shell could read as more.
_SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{7,79}")


def terminal_resume_argv(program: str, session_id: str | None) -> list[str] | None:
    """The command that carries `session_id` on in a terminal, or None when
    the program cannot (or the id is not one)."""
    if not session_id or not _SESSION_ID.fullmatch(session_id):
        return None
    if program == "claude":
        return ["claude", "--resume", session_id]
    if program == "codex":
        return ["codex", "resume", session_id]
    return None


def session_held_elsewhere(session_id: str, proc_dir: str = "/proc") -> bool:
    """Whether a process other than ours has `session_id` on its command
    line: the terminal it was handed to, still open. Only this user's
    processes can be read, which are the only ones that could hold it."""
    me = os.getpid()
    needle = session_id.encode()
    try:
        entries = os.listdir(proc_dir)
    except OSError:
        return False
    for entry in entries:
        if not entry.isdigit() or int(entry) == me:
            continue
        try:
            with open(os.path.join(proc_dir, entry, "cmdline"), "rb") as f:
                args = f.read().split(b"\0")
        except OSError:
            continue
        if needle in args:
            return True
    return False


#: A chunk that carries nothing: the stream was quiet for a moment.
TICK = Chunk()


class Ticker:
    """An agent's stream, read on a thread, with TICK while it is quiet.

    Progress talk needs moments to speak in, and the reply loop only runs
    when a chunk arrives -- nothing arrives during a two-minute test run.
    So the adapter's generator is drained by a thread into a queue, and the
    loop gets TICK whenever the queue has been empty for `every` seconds.

    `words_waiting()` says whether the agent has written words that are not
    yet read: a progress line being spoken stops for them.

    Stopped early -- the loop broke out, or raised -- the agent is cancelled,
    as closing the generator used to do: a process still answering the old
    question must not be handed the next one.
    """

    _END = object()

    def __init__(self, stream, every: float = 0.25, on_abandon=None,
                 on_sentence=None) -> None:
        self._queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._every = every
        self._on_abandon = on_abandon
        #: Called on the pump thread with each sentence as soon as it is
        #: complete -- split by the same rules the reply loop uses, so it sees
        #: the same sentences -- which is how the voice renders sentence two
        #: while sentence one plays. Errors in it are ignored: it is a head
        #: start, and the reply loop renders anything it missed.
        self._on_sentence = on_sentence
        self._thread = threading.Thread(target=self._pump, args=(stream,),
                                        daemon=True)
        self._thread.start()

    def _pump(self, stream) -> None:
        source = iter(stream)
        held: list = []

        def forward():
            # Each chunk goes to the splitter *before* the reader: a sentence
            # it completes is handed to on_sentence first, so the reply loop
            # never reaches a sentence that is not yet rendering.
            for chunk in source:
                held.append(chunk)
                yield chunk
                self._queue.put(held.pop())
                if self._stop.is_set():
                    return

        try:
            if self._on_sentence is not None:
                first = True
                for sentence in sentences(forward()):
                    try:
                        self._on_sentence(sentence, first)
                    except Exception:
                        pass
                    first = False
                # The splitter stops at an error chunk without asking for
                # another, which leaves that chunk here.
                while held:
                    self._queue.put(held.pop())
            if not self._stop.is_set():
                # The rest: everything, when nobody wants sentences, or what
                # follows an error, which ends the sentence split.
                for chunk in source:
                    self._queue.put(chunk)
                    if self._stop.is_set():
                        break
        except BaseException as e:      # handed to the reader, raised there
            self._queue.put(e)
        finally:
            close = getattr(stream, "close", None)
            if close is not None:
                try:
                    close()
                except Exception:
                    pass
            self._queue.put(self._END)

    def words_waiting(self) -> bool:
        with self._queue.mutex:
            return any(getattr(c, "text", "") for c in self._queue.queue)

    def __iter__(self):
        ended = False
        try:
            while True:
                try:
                    item = self._queue.get(timeout=self._every)
                except queue.Empty:
                    yield TICK
                    continue
                if item is self._END:
                    ended = True
                    return
                if isinstance(item, BaseException):
                    ended = True
                    raise item
                yield item
        finally:
            self._stop.set()
            # Left at the turn's last chunk (the reader stops at an error),
            # the pump finishes on its own; only a turn still going is
            # cancelled.
            self._thread.join(0.5)
            if not ended and self._thread.is_alive() and self._on_abandon is not None:
                try:
                    self._on_abandon()
                except Exception:
                    pass


class Daemon:
    def __init__(self, cfg: Config, pipe: Pipeline, state: StateFile,
                 speaker: Speaker | None, agent=None):
        #: Which agent the current thread is serving. A turn runs on a thread
        #: of its own once there are extra agents, and everything that says
        #: `self.agent`, `self.speaker`, `self.session_id` or
        #: `self._interrupt` then means that agent's. Anywhere else -- the run
        #: loop, a signal handler, a test -- it is the main agent's, which is
        #: all there ever was before there could be more than one. See crew.py.
        self._here = threading.local()
        self._main = Persona()
        #: The extra agents, by the name that wakes them.
        self.crew: dict[str, Persona] = {}
        #: Builds a voice; replaced in tests, where there is no Piper.
        self.make_speaker = Speaker
        self.cfg, self.pipe, self.state, self.speaker = cfg, pipe, state, speaker
        self.agent = agent
        # Carried between turns so the agent remembers the conversation.
        self.session_id: str | None = None
        self.enabled = True
        #: Set from the compositor's session lock, not from anything the user
        #: asked for. See the `listening` property.
        self.locked = False
        #: Something else is recording, so the microphone is lent out. A third
        #: flag rather than a second use of `enabled`, for the same reason
        #: `locked` is: `enabled` is what the user asked for, and writing to it
        #: here would mean that when the other app stopped recording we turned
        #: the microphone back *on* for somebody who had deliberately muted it.
        self.yielded = False
        self._yielded_to = ""
        self._last_session_poll = 0.0
        #: Whether the Omarchy skill has been checked against the installed
        #: Omarchy since this daemon started (reconcile_extras).
        self._skill_checked = False
        #: Each agent's Claude plugin folder, by what it was built from
        #: (Phase 13): see plugin_dir_for.
        self._plugin_dirs: dict = {}
        # A skill move or copy cut short by a crash (phase M12) is finished
        # or rolled back first, before any agent is built, so neither side
        # is ever shown to an adapter half-done.
        try:
            import transfer
            for r in transfer.recover() or []:
                print(f"  {YEL}skill transfer {r['op']}: {r['done']}{OFF}", flush=True)
        except Exception as e:
            print(f"  {YEL}skill transfers: could not be checked ({type(e).__name__}){OFF}",
                  flush=True)
        # Plugin folders from an earlier run: nothing has them open now.
        try:
            import agentfs
            agentfs.prune_plugins()
        except Exception:
            pass
        #: How long an explicitly announced lock outranks the poll, for the
        #: moment between the lock key being pressed and the compositor
        #: admitting to a lock.
        self._lock_hold_until = 0.0
        # Half duplex. One microphone six inches from the speakers has no
        # chance against its own output, so the microphone is simply deaf
        # while the machine talks -- and for a moment afterwards, because a
        # room has reverb and the audio device has a buffer.
        self._frames = None
        self._deaf_until = 0.0
        #: The short sounds -- see chimes.py. Set by main(); None means silent,
        #: which is what every test and the --simulate path want.
        self.chimes: Chimes | None = None
        #: The session's exchanges, for the conversation view.
        self.history = History()
        #: Saved chats, when `saveChats` is on. See chats.py.
        self.chats = ChatStore()
        #: Tasks between agents: passing a conversation (Phase 15). See
        #: collab.py; the hooks into this file are marked "collab".
        self.collab = collab.Runtime(self)
        #: The agent the microphone is open for, without the wake word, and
        #: until when (plan item 11). None when it is not open.
        self.open_mic: Persona | None = None
        self.open_mic_until = 0.0
        #: Phase M4. What was said aloud lately, as (began, ended, text): a
        #: command heard in it may be the agent's own voice coming back, and
        #: is not taken (`sentence_command`). And the open-mic switch made
        #: from inside a sentence, which "no" puts back for a moment
        #: (`take_undo`).
        self._said_lately: collections.deque = collections.deque(maxlen=24)
        self._undo: dict | None = None
        #: Moved on by every open-mic switch, from any path: an undo puts
        #: back only the switch it was armed for (Codex review of M4).
        self._open_mic_gen = 0
        #: Until when a frame's loudness may be our own chime rather than the
        #: person. Not `_deaf_until`: deafness throws frames away, and the
        #: frame after a wake word may hold the start of the request.
        self._chime_until = 0.0
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        (RUNTIME_DIR / "pid").write_text(str(os.getpid()))
        # A test result from the last run describes a daemon that is gone.
        wake_test.write(RUNTIME_DIR / "wake-test.json", None)
        # Barge-in is not possible acoustically through laptop speakers: at
        # a normal listening volume our own playback reaches the mic at the
        # same level as the user's voice (SNR +1.2 dB), and detection falls
        # to 5/20. PipeWire's echo canceller fixes that but needs ~30s of
        # continuous output to converge, which is longer than a reply. So
        # there an interrupt is an explicit act -- a keybind, or the Stop
        # button. On a headset the problem is gone, and `bargeOnHeadset`
        # listens over the reply by itself; see headset.py for the numbers.
        self._interrupt = threading.Event()
        self._barge = None
        #: What the person said over the reply, once barge-in has stopped it:
        #: the frames that tripped the detector and a little before. Not None
        #: means "they are talking", so the queue behind it is kept rather
        #: than dropped as echo, and the run loop opens a capture with this
        #: at its start instead of waiting for the wake word.
        self._barged: list[bytes] | None = None
        #: The wake word, heard while the agent was working. Talking does not
        #: stop a turn that is thinking or running tools -- somebody may be
        #: talking to the person beside them -- but the wake word does, and
        #: like `_barged` the queue behind it is kept: it is usually followed
        #: by the request that replaces the one being worked on.
        self._woke = False
        #: Held while a frame is taken off the queue during a turn, so the
        #: wake watch never reads the microphone while `speak()` owns it --
        #: then it is our own voice, and on a headset barge-in's to read.
        self._mic_lock = threading.Lock()
        self._speaking = False
        #: Who may speak, once agents work side by side: one at a time, never
        #: over somebody talking to us, and a reply keeps the floor between
        #: its own sentences. Shares the microphone's lock, so taking the
        #: floor and the run loop taking a frame can never interleave.
        self._floor = threading.Condition(self._mic_lock)
        self._floor_owner: Persona | None = None
        self._floor_until = 0.0
        #: Set by the run loop while somebody is talking to an agent, or has
        #: just said a name and is about to.
        self._hold_speech = False
        #: The agent that was talked over, so what was said goes to it.
        self._barged_by: Persona | None = None
        #: The agent last given a turn: push-to-talk goes to it.
        self._last_target: Persona | None = None
        #: The agent whose turn ended last, so the readout keeps showing its
        #: answer once nothing is happening, as it did with one agent.
        self._recent: Persona | None = None
        #: The agent the capture under way is for, for the readout.
        self._capture_for: Persona | None = None
        #: The microphone's own state, as last published by the run loop.
        self._mic_shown: tuple[str, dict] = ("off", {})
        #: The last answer from headset.default_output(), and when it was
        #: asked: a pactl round trip is 23ms and sits in front of a sentence,
        #: so it is not asked per sentence.
        self._output: tuple[bool, str] | None = None
        self._output_at = 0.0
        #: Depth of `_watching_session()`, which is entered for the whole of a
        #: turn and again inside `speak()`.
        self._watchers = 0
        self._watch_stop = None
        self._watch_thread = None
        #: Last line printed under each key, so the reconcilers can report a
        #: state rather than repeat it. They run on the idle poll, every
        #: couple of seconds, and the ones that cannot succeed -- no agent
        #: installed, no voice downloaded -- used to write the same line to
        #: the journal twenty times a minute, forever.
        self._said: dict[str, str] = {}
        #: phase M2, bug I: why an agent's conversation was ended by a
        #: rebuild, by agent id ("" the main agent), as (line, its turn count
        #: then, when). Shown in the readout until its next turn is answered.
        self._notices: dict[str, tuple[str, int, float]] = {}
        #: phase M3: the readout's kept reply, when its lines clear, and the
        #: Display page's preview. See readout.py.
        self.readout = readout.Readout(lock=getattr(state, "_lock", None),
                                       on_clear=self._readout_cleared)
        #: Agents' cached turns (Persona.last) as they were at the last
        #: readout clear: not merged into the screen again (phase M3).
        self._stale_lasts: list[dict] = []
        #: The permission level the main agent's conversation last ran
        #: under. Compared as a level, not as the hook-or-not flag: Ask and
        #: Edits share the flag, and lowering Edits to Ask must still
        #: withdraw "allow all in this chat" (Codex review of M2).
        self._main_level: str | None = None
        #: phase M2, bug C: turns cut at maxUtteranceMs, today. Carried over
        #: from the state file a previous run of the daemon left, so a restart
        #: (an install) does not wipe the count the Conversation page shows.
        self.limit_hits = _limit_hits_from(state)
        #: phase M16: each agent's last structural log lines (Agent details
        #: → Advanced), typed fields only, never anything said; and what was
        #: last published about what each agent runs (runinfo.json).
        self.agent_ring = runinfo.Ring()
        self._runinfo: dict = {}
        self._runinfo_key = None
        self._runinfo_at = 0.0
        signal.signal(signal.SIGUSR1, self._on_toggle)
        signal.signal(signal.SIGUSR2, self._on_interrupt)
        if state is not None and hasattr(state, "overlay"):
            state.overlay = self._compose
        #: Omarchy's Agents panel, kept in step with every write of the state
        #: file. Set by main(); None in tests and --simulate.
        self.panel = None
        if state is not None and hasattr(state, "mirror"):
            state.mirror = self._mirror_panel

    # --- which agent ---------------------------------------------------------

    def _persona(self) -> Persona:
        return getattr(self._here, "persona", None) or self._main

    def _set(field):
        return property(lambda self: getattr(self._persona(), field),
                        lambda self, value: setattr(self._persona(), field, value))

    agent = _set("agent")
    session_id = _set("session_id")
    speaker = _set("speaker")
    _interrupt = _set("interrupt")
    del _set

    @contextlib.contextmanager
    def _as(self, persona: Persona | None):
        """Act for `persona` on this thread for a moment: the run loop priming
        the agent somebody has just woken, or clearing its stop."""
        if persona is None:
            yield
            return
        before = getattr(self._here, "persona", None)
        self._here.persona = persona
        try:
            yield
        finally:
            self._here.persona = before

    def _in_turn(self) -> bool:
        """Whether this thread is running an agent's turn beside the run loop."""
        return bool(getattr(self._here, "turn", False))

    @property
    def crew_mode(self) -> bool:
        """Whether turns run beside the run loop rather than inside it.

        With extra agents, and for as long as a turn started that way is
        still running after the last of them was removed.
        """
        return bool(self.crew) or self._main.busy

    def personas(self) -> list[Persona]:
        return [self._main, *self.crew.values()]

    def _clear_interrupts(self) -> None:
        for p in self.personas():
            p.interrupt.clear()

    def say_once(self, key: str, line: str) -> bool:
        """Print `line` if it is not what was last printed under `key`."""
        if self._said.get(key) == line:
            return False
        self._said[key] = line
        print(line, flush=True)
        return True

    def _on_toggle(self, *_):
        # A mute closes the microphone and nothing else. It used to call
        # silence(), which cancelled every agent's turn and voice: muting so
        # you could cough or take a call ended the chat you were in. What was
        # captured is still dropped -- the run loop abandons a capture the
        # moment `listening` goes false -- and replies keep playing.
        self.enabled = not self.enabled
        if not self.enabled:
            self.deafen(0)
        print(f"\n  {CYA}mic {'engaged' if self.enabled else 'released'}{OFF}")
        self._publish()

    #: Listening needs both: the user has not released the microphone, and the
    #: screen is not locked.
    #:
    #: Two flags rather than one, because a lock must not disturb what the
    #: user chose. `enabled` is their intent -- the panel switch, the panic
    #: keybind -- and `locked` is the session's state. Nothing is saved and
    #: restored around a lock, so there is no stored copy to get out of step:
    #: unlocking reveals the intent that was there all along. Toggling
    #: `enabled` on lock would have turned the microphone *on* for anyone who
    #: had deliberately turned it off.
    @property
    def listening(self) -> bool:
        # A typed turn is answered with the microphone switched off: typing is
        # what you do when you cannot, or would rather not, talk. A lock and a
        # borrowed microphone still stop it -- nothing is said to a locked
        # room or over somebody's call.
        typed = getattr(self._here, "typed", False)
        return (self.enabled or typed) and not self.locked and not self.yielded

    @property
    def may_speak(self) -> bool:
        """Whether a reply may be heard. A lock (nobody at the desk) and a
        lent microphone (somebody is on a call) stop speech; a mute does not:
        it is about what we hear, not what we say."""
        return not self.locked and not self.yielded

    def silence(self) -> None:
        """Stop talking, stop thinking, and forget what is already captured.

        Draining matters as much as the gate. Frames queue while the loop is
        busy, so without this the audio recorded during the first moments of
        a lock would be waiting to be processed on unlock.
        """
        if self._in_turn():
            # From inside one agent's turn -- it was stopped, or a lock was
            # noticed between its sentences -- this is about that agent. The
            # others are the run loop's to stop, and the microphone's queue is
            # not this thread's to drain: somebody may be talking to another
            # agent right now.
            self._persona().stop()
            return
        for p in self.personas():
            if p.speaker:
                p.speaker.cancel()
            if p.task is not None and p.busy:
                # collab: a task keeps running behind a lock, saying nothing;
                # its reply waits for the unlock (Phase 15).
                continue
            if p.agent:
                p.agent.cancel()
            p.interrupt.set()
        self.deafen(0)

    def reconcile_lock(self) -> None:
        """Close the microphone while the screen is locked, open it after.

        The hole this closes: the daemon kept listening behind a lock screen,
        so anyone within earshot of a locked machine could hold a
        conversation with an agent that had been granted "edits" or
        "trusted" -- which is every permission decision in this project
        undone by walking up to the desk.
        """
        locked = session_locked()
        if locked is None:
            # Said, not swallowed. A daemon that cannot tell whether the
            # screen is locked is a daemon that will keep listening behind
            # one, and that is worth hearing about rather than discovering.
            # say_once, because this condition does not change on its own.
            self.say_once("lockable",
                          f"  {YEL}cannot tell whether the screen is locked, "
                          f"so the microphone will not close on lock: no "
                          f"omarchy-hyprland-session-locked on PATH and no "
                          f"logind LockedHint{OFF}")
            return
        if not locked and time.time() < self._lock_hold_until:
            # Told to lock a moment ago, and the compositor has not caught up:
            # `solitaryBlockedBy` does not gain LOCK the instant the keybind
            # fires. Without this grace period, binding `agentvoice lock` to
            # the lock key made things *worse* than not binding it -- the
            # poll would reopen the microphone for the couple of seconds
            # right after locking, which is precisely the window the binding
            # was there to close.
            return
        if locked == self.locked:
            return
        self.locked = locked
        if locked:
            self._undo = None           # phase M4: a lock ends the chance
            # Mid-turn when it happens: the reply is being read aloud to
            # whoever is standing there, so it stops too.
            self.silence()
            print(f"\n  {YEL}screen locked — microphone closed{OFF}", flush=True)
        else:
            self._clear_interrupts()
            print(f"\n  {CYA}screen unlocked — microphone "
                  f"{'open' if self.enabled else 'still released'}{OFF}",
                  flush=True)
        self._publish()

    def reconcile_yield(self) -> None:
        """Lend the microphone to whatever else has started recording.

        Measured first: dictating into the editor and saying the wake phrase
        made the agent answer out loud into the dictation, 17:34:05 against a
        capture that opened at 17:33:57. Both streams run happily side by side
        -- PipeWire does not arbitrate, so this is a courtesy rather than a
        fix for contention -- and the eight seconds between the two is why a
        2s poll is fast enough to have prevented it.
        """
        if not self.cfg.get_bool("yieldToRecorders"):
            if self.yielded:                 # turned off while lent out
                self.yielded = False
                self._publish()
            return
        # Only while there is something to lend. Asking costs a subprocess,
        # and a released or locked microphone is not listening anyway.
        if not self.enabled or self.locked:
            return

        others = other_recorders(os.getpid())
        if others is None:
            self.say_once("recorders",
                          f"  {YEL}cannot tell what else is using the "
                          f"microphone, so it will not step aside for "
                          f"anything: no pw-dump on PATH{OFF}")
            return
        busy = bool(others)
        if busy == self.yielded:
            return
        self.yielded = busy
        if busy:
            self._yielded_to = others[0]
            # Mid-reply when it happens is the whole point: that is the audio
            # that lands in somebody's dictation.
            self.silence()
            print(f"\n  {YEL}microphone lent to {self._yielded_to} "
                  f"— not listening{OFF}", flush=True)
        else:
            self._clear_interrupts()
            print(f"\n  {CYA}{self._yielded_to or 'the other app'} finished "
                  f"— microphone {'back' if self.enabled else 'still released'}"
                  f"{OFF}", flush=True)
            self._yielded_to = ""
        self._publish()

    def apply_lock_command(self, cmd: str | None) -> bool:
        """Apply an explicit `agentvoice lock`/`unlock`. True if it was one."""
        if cmd not in ("lock", "unlock"):
            return False
        self.locked = cmd == "lock"
        if self.locked:
            self._undo = None           # phase M4: a lock ends the chance
            self._lock_hold_until = time.time() + LOCK_HOLD_S
            self.silence()
        else:
            self._lock_hold_until = 0.0
            self._clear_interrupts()
        print(f"\n  {YEL if self.locked else CYA}screen "
              f"{'locked' if self.locked else 'unlocked'} "
              f"(told, not polled){OFF}", flush=True)
        self._publish()
        return True

    def readout_for(self) -> readout.Readout:
        """The readout's state (phase M3). Made here when missing: test
        daemons built with Daemon.__new__ never ran __init__."""
        r = getattr(self, "readout", None)
        if r is None:
            r = self.readout = readout.Readout(lock=getattr(self.state, "_lock", None),
                                               on_clear=self._readout_cleared)
        return r

    def forget_readout(self, p: Persona, clear: bool = False) -> None:
        """`p`'s conversation changed (readout.Readout.forget). With
        `clear`, its cached turn is marked too, even when another agent is
        on screen: idle payloads would otherwise merge its old words back
        the next time it is the one shown (Codex review of M3)."""
        self.readout_for().forget(p.id or "", clear=clear)
        if clear and getattr(p, "last", None):
            self._stale_lasts = [*getattr(self, "_stale_lasts", []), p.last]

    def _readout_cleared(self) -> None:
        """Both readout lines were cleared (a lock, an expiry, a switch): the
        agents' cached turns, which crew mode merges into every idle
        payload, must not bring the words back. Marked rather than emptied,
        because collaboration reads Persona.last for a pass's brief."""
        try:
            self._stale_lasts = [p.last for p in self.personas()
                                 if getattr(p, "last", None)]
        except Exception:              # a readout aid must never stop a publish
            self._stale_lasts = []

    def expire_readout(self) -> None:
        """Ten minutes with nothing new on the readout: both lines clear
        (readout.KEEP_S). From the run loop's unconditional 2 s poll."""
        if self.readout_for().expire():
            self._recompose()

    def apply_readout_command(self, cmd: str | None) -> bool:
        """`agentvoice hud-preview`, the Display page's Preview button: four
        seconds of sample text through the state file. True if it was one.

        Refused, and said so, while the screen is locked; over a turn under
        way it simply does not show (readout.PREVIEWABLE decides, at every
        publish, so a wake word in the middle of it wins at once)."""
        if cmd != "hud-preview":
            return False
        if self.locked:
            print(f"  {DIM}(readout preview: not while the screen is locked){OFF}",
                  flush=True)
            return True
        seconds = self.readout_for().preview()
        print(f"  {DIM}(readout preview for {seconds:.0f}s){OFF}", flush=True)
        self._recompose()
        # A little after the end, so the clock has passed it when it looks.
        t = threading.Timer(seconds + 0.05, self._recompose)
        t.daemon = True
        t.start()
        return True

    #: Where the wake test's readout goes: beside the state file.
    WAKE_TEST_FILE = RUNTIME_DIR / "wake-test.json"

    def apply_wake_test_command(self, cmd: str | None) -> bool:
        """`agentvoice wake-test start|stop`. True if it was one."""
        if cmd not in ("wake-test-start", "wake-test-stop"):
            return False
        if cmd == "wake-test-start":
            self.wake_test = wake_test.WakeTest()
            self._wake_test_cut = crosscheck.Bursts(
                CHUNK_MS, wake_test.MIN_ATTEMPT_MS, wake_test.MAX_ATTEMPT_MS)
            print(f"\n  {CYA}wake test: say the name {self.wake_test.target} "
                  f"times (wakes are counted, not answered){OFF}", flush=True)
        elif getattr(self, "wake_test", None) is not None:
            self.wake_test.stop()
            print(f"  {CYA}wake test stopped{OFF}", flush=True)
        self._write_wake_test()
        return True

    def wake_testing(self, pcm: bytes, level: float) -> bool:
        """Feed one wake-phase frame to the running test. False when no test
        is running, and the frame goes on to the wake word as usual."""
        test = getattr(self, "wake_test", None)
        if test is None or not test.running:
            return False
        gate = getattr(self.pipe, "wake_gate_db", self.pipe.threshold_db)
        test.on_level(level, gate)
        if self._wake_test_cut.feed(pcm, level >= gate) is not None:
            test.on_attempt()
        if self.pipe.feed_wake(pcm, level) and not self.heard_full_stop():
            how = getattr(self.pipe, "wake_how", "") or "?"
            test.on_wake(self.pipe.heard_phrase, how)
            print(f"  {GRN}● wake test: {self.pipe.heard_phrase} by {how} "
                  f"({len(test.hits)}/{test.target}){OFF}", flush=True)
        take = getattr(self.pipe, "take_near_misses", None)
        for why in (take() if callable(take) else []):
            test.on_near(why)
        test.tick()
        if not test.running:
            snap = test.snapshot()
            print(f"  {CYA}wake test {snap['status']}: {snap['hits']} of "
                  f"{snap['attempts']} attempts woke it{OFF}", flush=True)
        self._write_wake_test()
        return True

    def _write_wake_test(self) -> None:
        test = getattr(self, "wake_test", None)
        snap = test.snapshot() if test is not None else None
        if snap != getattr(self, "_wake_test_shown", None):
            self._wake_test_shown = snap
            wake_test.write(self.WAKE_TEST_FILE, snap)

    def arm_follow_up(self) -> bool:
        """Whether to keep listening after the turn without the wake word.

        Not after a stop. Pressing stop and then being listened to for seven
        seconds is the opposite of what the button says: somebody who reaches
        for it wants the thing to stop paying attention, and an open follow-up
        window means the next thing they say -- very likely about what just
        went wrong, possibly to somebody else in the room -- starts another
        turn with no wake word and no speaker verifier. Reported from use:
        "when I hit stop on the panel it stopped the current task, then
        immediately went back to listening for the next turn."

        `_interrupt` is also set by `silence()`, so a lock, a mute and the
        microphone being lent to another application each close the window
        too, which is what all three of them mean.

        A method rather than an expression in the loop so that it can be
        driven directly, and so the next person to add a reason for stopping
        has one place to put it.
        """
        return self.pipe.conversation and not self._interrupt.is_set()

    def poll_session(self) -> None:
        """Notice a lock from wherever the daemon happens to be.

        The loop polled this at its top, which is the one place the daemon is
        *not* when it matters: `answer()` blocks for the whole agent turn and
        the whole of speech playback -- 22 to 45 seconds in this machine's
        journal -- so locking the screen mid-reply left it reading a private
        answer aloud to an empty room until the reply ended. Reported against
        1d59790 by a marketplace reviewer.

        Called from the loop and from inside the reply, rate limited so a
        subprocess is not spawned per sentence.
        """
        if self._in_turn():
            # The run loop is still running and polls this itself. From here
            # it would take the command file -- a push-to-talk press meant
            # for the loop -- and drop it.
            return
        if time.time() - self._last_session_poll < 1.0:
            return
        self._last_session_poll = time.time()
        if not self.apply_lock_command(self.take_command()):
            self.reconcile_lock()

    def main_program(self) -> str | None:
        """What the main agent runs: its own setting, else Omarchy's default."""
        return main_program(self.cfg.get_str("mainProgram"))

    def reconcile_agent(self) -> None:
        """Rebuild the agent when the project or permission level changes.

        The adapter is constructed once at startup, so without this a new
        directory would be set in the UI and simply not happen -- the same
        read-once bug that made two earlier settings look broken.

        The process always goes: it was started under the old flags. The
        conversation goes only with a new program, endpoint or folder --
        `--resume` is scoped to a project in Claude Code, so carrying an id
        across a directory change would resume the wrong conversation, or
        none. A new level or model keeps it where the backend has been shown
        to resume under the new flags (sessions.py; bug I, phase M2): this
        dropped it too, and a permission flip mid-chat left the agent unable
        to recall what it had just said.
        """
        if self._main.busy:
            # Its turn is running on another thread; rebuilding would cancel
            # it. The idle poll comes round again.
            return
        endpoint = self.endpoint_spec()
        want_name = "endpoint" if endpoint else self.main_program()
        want_cwd = str(project_dir(self.cfg.get_str("projectDir")))
        want_level = self.cfg.level_for(want_name)
        want_ask = want_level != "trusted"
        want_model = None if endpoint else self.cfg.model_for(want_name)
        want_effort = None if endpoint else self.cfg.effort_for(want_name)
        # From agents/main/instructions.md, the setting only while that file
        # is missing (merged plan, Phase 10).
        want_instructions = self.instructions_for("", self.cfg["agentInstructions"])
        # The endpoint's identity is its URL and model, not just its name:
        # switching which machine answers must rebuild, and they all report
        # the same name.
        same_endpoint = (endpoint is None
                         or (getattr(self.agent, "base_url", None)
                             == endpoint["url"].rstrip("/")
                             and getattr(self.agent, "model", None)
                             == endpoint["model"]
                             and getattr(self.agent, "is_agent", False)
                             == endpoint["is_agent"]
                             and getattr(self.agent, "history_turns", None)
                             == endpoint["history_turns"]
                             and (getattr(self.agent, "timeout", None)
                                  if getattr(self.agent, "timeout_set", False)
                                  else 0) == endpoint["timeout_s"]))
        if (self.agent is not None
                and getattr(self.agent, "name", None) == want_name
                and same_endpoint
                and (endpoint is not None
                     or getattr(self.agent, "cwd", None) == want_cwd)
                and (endpoint is not None
                     or getattr(self.agent, "ask_permission", None) == want_ask)
                and (endpoint is not None
                     or not takes_model(self.agent)
                     or getattr(self.agent, "model", None) == want_model)):
            self.apply_instructions(want_instructions)
            self.apply_effort(want_effort)
            # A level that moved no flag (Ask and Edits share the hook)
            # needs no new process, but it is still a new decision.
            if getattr(self, "_main_level", None) not in (None, want_level):
                self.carry_session(self._main, {sessions.LEVEL}, want_name or "",
                                   rebuilt=False)
            self._main_level = want_level
            self.publish_agent()
            return
        old = self.agent
        changed: set[str] = set()
        if old is not None:
            if getattr(old, "name", None) != want_name:
                changed.add(sessions.PROGRAM)
            elif endpoint is not None:
                changed.add(sessions.ENDPOINT)
            else:
                if getattr(old, "cwd", None) != want_cwd:
                    changed.add(sessions.FOLDER)
                if (getattr(old, "ask_permission", None) != want_ask
                        or getattr(self, "_main_level", None) not in (None, want_level)):
                    changed.add(sessions.LEVEL)
                if takes_model(old) and getattr(old, "model", None) != want_model:
                    changed.add(sessions.MODEL)
            old.cancel()
        if endpoint:
            endpoint = {**endpoint, "key": endpoint_key(_host(endpoint["url"]))}
        self.agent = load_adapter(name=None if endpoint else want_name,
                                  ask_permission=want_ask, cwd=want_cwd,
                                  level=want_level, endpoint=endpoint,
                                  model=want_model, effort=want_effort,
                                  instructions=want_instructions)
        # phase M2, bug I: was `self.session_id = None` whatever changed.
        had = bool(self._main.session_id)
        kept = self.carry_session(self._main, changed, want_name or "")
        if old is not None:
            # phase M16: the ring, by kind and the sessions vocabulary only.
            self.agent_ring.add("main", "rebuilt", changed=changed, kept=kept if had else None)
        self._main_level = want_level
        self.publish_agent()
        where = f" · {want_cwd}" if getattr(self.agent, "has_tools", True) else ""
        if want_model and takes_model(self.agent):
            where += f" · {want_model}"
        if self.effort_in_force():
            where += f" · {want_effort} effort"
        # say_once, because with no agent installed self.agent stays None and
        # the guard above can never match, so this ran on every idle poll.
        self.say_once("agent", f"  {CYA}agent: {want_name or 'nobody'}{where}{OFF}"
                               f"  {DIM}({self.posture()}){OFF}")
        chosen = self.main_program()
        if want_name == "endpoint" and chosen:
            self.say_once("override",
                          f"  {YEL}the endpoint setting is answering instead of "
                          f"{chosen} — clear it to use the desktop's agent{OFF}")
        # Said here as well as in the banner, because the banner only reprints
        # when our own config changes and switching agents writes Omarchy's
        # file -- so on the one occasion this matters most, it would not run.
        if (self.agent is not None and self.pipe is not None
                and getattr(self.pipe, "conversation", False)
                and not getattr(self.agent, "remembers", False)):
            self.say_once("forgets",
                          f"  {YEL}conversation is on, but {self.agent.name} starts "
                          f"fresh every turn — it saves you the wake word and "
                          f"nothing more{OFF}")

    def carry_session(self, p: Persona, changed: set[str], program: str,
                      rebuilt: bool = True) -> bool:
        """After `p`'s adapter was rebuilt for `changed` (or, `rebuilt`
        False, after its level moved with no new flags): keep its
        conversation or end it, by sessions.carry(), and say which. True if
        kept (phase M2, bug I).

        Kept across a level change, it loses every "allow all in this chat"
        made under the old level: the level is the newer decision. If one
        cannot be withdrawn the conversation ends instead, which makes the
        grant mean nothing (fail closed). Ended with a conversation to end,
        the reason goes in the journal and in the readout until `p`'s next
        turn, so a backend that has to start fresh says why rather than
        seeming to forget."""
        sid = p.session_id
        if not sid:
            return False
        label = p.label or p.name or "main"
        if p.agent is None:
            keep, reason = False, (sorted(changed & {sessions.PROGRAM, sessions.FOLDER})
                                   or [sessions.OTHER])[0]
        elif not rebuilt:
            keep, reason = True, ""         # the same process: nothing to resume
        else:
            keep, reason = sessions.carry(
                changed, getattr(p.agent, "carries_session_across", frozenset()))
        if keep and sessions.LEVEL in changed:
            import permission_hook
            if permission_hook.revoke(sid):
                print(f"  {CYA}agent “{label}”: no “allow all in this chat” "
                      f"carried over — the permission level changed{OFF}",
                      flush=True)
            else:
                keep, reason = False, sessions.GRANTS
        if keep:
            if rebuilt:
                print(f"  {CYA}agent “{label}”: conversation kept "
                      f"({' and '.join(sorted(changed)) or 'nothing'} changed){OFF}",
                      flush=True)
            return True
        p.session_id = None
        if not rebuilt and p.agent is not None:
            p.agent.cancel()                # its warm process holds the old chat
        because = sessions.why(reason, program_label(program) or program)
        print(f"  {YEL}agent “{label}”: new conversation — {because}{OFF}", flush=True)
        # Replaced, never changed in place: turn threads read it in
        # _compose() while this thread writes it (Codex review of M2).
        self._notices = {**self._notices, p.id or "": (
            f"{label}: new chat — {because}.", getattr(p, "turn_id", 0),
            time.time())}
        # phase M3: the reply kept for the readout was the old chat's, and
        # so are the words on screen: cleared, or the recompose below would
        # read the old answer back and keep it again (Codex review).
        self.forget_readout(p, clear=True)
        self._recompose()
        return False

    def flags_moved(self, p: Persona, cfg) -> bool:
        """Whether the settings in `cfg` have moved `p` away from what its
        running adapter was built under: adapter_stale() -- a level, Ask and
        Edits included, or a folder -- or an extra agent the settings no
        longer have (deleted or switched off), which the idle poll removes.
        False for an endpoint, which runs nothing here."""
        have = p.agent
        if have is None or hasattr(have, "base_url"):
            return False
        return bool(self.adapter_stale(p, cfg))

    def catch_up_flags(self, p: Persona) -> bool:
        """Before `p`'s next turn starts: if its level or folder moved since
        its adapter was built, apply that now (Codex review of M2). False if
        doing so found `p` deleted or switched off: it takes no new turn.

        The idle poll rebuilds an agent only while it is idle. One that was
        busy when the level was lowered, then stopped -- by its name, a
        barge-in, or a typed or spoken replacement -- went straight into its
        next turn: no poll runs during a capture, and catch_up_one() leaves
        the level to the poll. That turn ran on the process started under
        the old flags, Trusted after the user had chosen Ask. Read from the
        settings on disk, as collaboration calls are; on the run loop's
        thread only, where a refresh belongs."""
        if threading.current_thread() is not threading.main_thread() \
                or getattr(self, "pipe", None) is None:
            return True
        if not self.flags_moved(p, self.fresh_config()):
            return True
        print(f"  {CYA}agent “{p.label or p.name or 'main'}”: settings "
              f"changed while it worked — applying them first{OFF}", flush=True)
        self.refresh()
        return p.main or self.crew.get(p.id) is p

    def expire_notices(self) -> bool:
        """Drop each notice once its agent has answered a turn since, or is
        gone, or it is an hour old. True if any went. From refresh(), on the
        run loop's thread, like everything else that rewrites the context."""
        gone = []
        notices = self._notices
        for key, (_line, turn, at) in notices.items():
            p = self._persona_by_id(key)
            if (p is None or time.time() - at > 3600
                    or (getattr(p, "turn_id", 0) > turn
                        and not getattr(p, "answering", False))):
                gone.append(key)
        if gone:
            self._notices = {k: v for k, v in notices.items() if k not in gone}
        return bool(gone)

    def instructions_for(self, persona_id: str, legacy) -> str:
        """An agent's standing instructions: its folder's instructions.md
        when that exists (even empty), else the old setting `legacy`.

        From what reconcile_agent_files last read, so an idle poll reads no
        text; it runs first in refresh(), so a hand edit reaches the agent on
        the same poll. Before the first read, straight from the file."""
        texts = getattr(self, "_folder_texts", None)
        if texts is None:
            import agentfs
            return agentfs.instructions_for(persona_id, legacy)
        got = texts.get(persona_id or "main", {}).get("instructions.md")
        if persona_id == "communal":
            got = None              # that name is the shared folder's
        return got if got is not None else instructions_text(legacy)

    def reconcile_parts(self) -> None:
        """Hand every idle agent the folder pieces of its prompt (merged plan,
        Phase 11): the communal rules and defaults, its personality, and the
        roster of the other agents it could pass work to.

        Built from what reconcile_agent_files last read, so an idle poll reads
        no text, and only between turns: a busy agent keeps the prompt its
        turn started with and is caught up on a later poll. A changed
        preamble lets the idle process go and keeps the conversation, as a
        changed instruction does. Logged as sizes per piece, never text.

        The roster is who is reachable now -- the main agent, and each extra
        agent that was built and has a program -- so switching Sora on
        reaches Theo on his next turn, and an agent nobody can wake is never
        offered."""
        texts = getattr(self, "_folder_texts", None)
        if texts is None:
            return                  # nothing read yet: the old preamble
        import agentfs
        main = self._main
        # Who can be woken now: the settings switch it on and the wake
        # engine hears its name. Not the crew as it stands, which still
        # holds an agent deleted or switched off mid-turn until its turn
        # ends (Phase 11 review).
        agents = getattr(self.cfg, "agents", None)
        wanted = {s["id"]: s["name"] for s in agents()} if callable(agents) else {}
        heard = set(getattr(self.pipe, "names", ()) or ())
        live = []
        if main.agent is not None:
            live.append({"id": "main", "label": main.label or main.name,
                         "phrase": main.name})
        for p in self.crew.values():
            if (p.agent is not None and p.id and p.id in wanted
                    and (not heard or wanted[p.id] in heard)):
                live.append({"id": p.id, "label": p.label, "phrase": p.name})
        # Phase M8: each agent's roster names only the agents the crew links
        # let it reach -- none for a quarantined one, none while the links
        # cannot be read -- so its prompt never offers it someone list_agents
        # would not. A link changed reaches it on the next idle poll.
        try:
            crew = self.cfg.crew()
        except Exception:
            crew = None
        for p in [main, *self.crew.values()]:
            agent = p.agent
            if agent is None or p.busy or not hasattr(agent, "preamble"):
                continue
            fid = "main" if p is main else p.id
            reach = crew.reach(fid) if crew is not None else {}
            mine = [a for a in live if a["id"] == fid or a["id"] in reach]
            want = agentfs.parts_from(texts, fid, p.label or p.name, mine,
                                      self.skills_off_for(p), self.takes_communal(p))
            if getattr(agent, "parts", None) == want:
                continue
            try:
                before = agent.preamble()
                agent.parts = want
                after = agent.preamble()
            except Exception as e:      # a prompt is never worth the poll
                print(f"  {YEL}prompt for “{p.label}”: not built "
                      f"({type(e).__name__}){OFF}", flush=True)
                continue
            if after != before:
                agent.cancel()          # read when its process starts
            sizes = " · ".join(f"{k} {len(want[k])}"
                               for k in ("rules", "defaults", "personality"))
            print(f"  {DIM}prompt for “{p.label or p.name or 'main'}”: {sizes} · "
                  f"instructions {len((agent.instructions or '').strip())} · "
                  f"roster {len(want['roster'])} = {len(after)} chars{OFF}",
                  flush=True)

    def apply_instructions(self, want: str) -> None:
        """Change the standing instructions, keeping the conversation.

        Like an effort, they are read when the agent's process starts (Claude
        Code takes them as a system-prompt file), so the idle process goes
        and the next turn resumes the same session under the new ones.
        """
        if self.agent is None or getattr(self.agent, "instructions", "") == want:
            return
        self.agent.instructions = want
        self.agent.cancel()
        print(f"  {CYA}instructions: {'updated' if want else 'none'}{OFF}",
              flush=True)

    def effort_in_force(self) -> str | None:
        """The effort the next turn will run at, or None for the default."""
        effort = getattr(self.agent, "effort", None)
        if effort and effort in self.efforts():
            return effort
        return None

    def efforts(self) -> tuple[str, ...]:
        """The levels the running agent takes with its model."""
        return tuple(getattr(self.agent, "efforts", tuple)())

    def apply_effort(self, want: str | None) -> None:
        """Change the effort without starting a new conversation.

        It is a flag the waiting claude was started with, so that process has
        to go -- but unlike the model or the folder, nothing about the
        conversation depends on it, so the session is kept and the next turn
        resumes it at the new level. Only reached from refresh(), which runs
        between turns, so cancel() here takes an idle process and never a
        turn somebody is waiting on.
        """
        if not takes_effort(self.agent) or getattr(self.agent, "effort", None) == want:
            return
        before = self.effort_in_force()
        self.agent.effort = want
        if self.effort_in_force() != before:
            self.agent.cancel()
        print(f"  {CYA}effort: {self.effort_in_force() or 'default'}{OFF}",
              flush=True)

    def endpoint_spec(self) -> dict | None:
        """The configured OpenAI-compatible endpoint, or None.

        The key never travels with the rest of the settings: it is read from
        its own file at the moment it is needed, so it cannot end up in
        shell.json, in the state file, or in anything published to the panel.
        """
        # No key here: this runs on the idle poll, every couple of seconds,
        # and reading the keyring means spawning secret-tool. The key is
        # fetched once, where the adapter is actually built.
        main = getattr(self.cfg, "main_endpoint", None)
        return main() if callable(main) else None

    def level(self) -> str:
        return self.cfg.level_for(getattr(self.agent, "name", None))

    def posture(self) -> str:
        """What the level means for the agent actually running."""
        if self.agent is None:
            return "no agent"
        return self.agent.posture(self.level())

    def publish_agent(self) -> None:
        """Tell the panel which agent is up and what it can honour.

        The panel could not work this out for itself without keeping its own
        copy of every adapter's capabilities, which would drift the first time
        one changed. It is published instead, so the screen and the daemon
        cannot disagree about a permission guarantee.
        """
        if self.agent is None:
            # Echoing instead of answering looks like a broken assistant. Say
            # which agent is missing and why, where it can actually be read.
            name = self.main_program() or ""
            self.state.describe(agent=name, level="ask", levels=["ask"],
                                posture=explain_agent(name) or "no agent",
                                **self.crew_fields())
            return
        # An endpoint takes precedence over the desktop's agent, which is a
        # reasonable rule and an unreasonable surprise: choosing Claude in
        # Omarchy's settings and having nothing change is indistinguishable
        # from the setting being broken. Name what is being overridden.
        chosen = self.main_program() or ""
        endpoint_wins = getattr(self.agent, "name", "") == "endpoint" and chosen
        self.state.describe(
            agent=getattr(self.agent, "name", "") or "",
            level=self.level(),
            levels=list(getattr(self.agent, "levels", ("ask", "trusted"))),
            posture=self.posture(),
            remembers=bool(getattr(self.agent, "remembers", False)),
            overriding=chosen if endpoint_wins else "",
            # Whether the project directory and permission level reach the
            # running backend at all. They govern a CLI started here, in a
            # directory we choose, under flags we pass. They govern nothing
            # about a machine down the hall.
            governed=bool(getattr(self.agent, "cwd", None)),
            # Whether the model field means anything for the running backend,
            # and what it is set to, so the panel never offers a setting that
            # would be silently dropped.
            takes_model=takes_model(self.agent),
            model=getattr(self.agent, "model", None) or "",
            # The levels this agent takes *with its model*, so the slider is
            # drawn only when there is something it would change, with exactly
            # the notches the model has.
            efforts=list(self.efforts()),
            effort=self.effort_in_force() or "",
            # Model choices per program, for the ones that can list theirs:
            # Codex's change with every release, so they are read from it.
            model_lists=model_lists(),
            # The daemon has always known this and only ever said it in a log
            # line nobody reads. A verifier is the one layer that knows who is
            # talking, so whether it is in force belongs on screen.
            verifier=bool(getattr(getattr(self.pipe, "_oww", None),
                                  "verifier", None)),
            **self.crew_fields(),
        )

    def _on_interrupt(self, *_):
        """Cut the current reply short and go back to listening.

        Only meaningful mid-turn; when the daemon is already idle this is
        deliberately a no-op, so a stray keypress cannot leave it in a state
        the user never asked for.
        """
        # collab: the global stop clears the task queue, busy or not. From a
        # signal handler, so it publishes nothing here (collab.stop_all).
        self.collab.stop_all(from_signal=True)
        if self.crew_mode:
            busy = [p for p in self.personas() if p.busy]
            if not busy:
                return
            # Everyone: the button and the keybind say "stop", not "stop
            # whichever one I am thinking of", and there is no way to say
            # which from a keypress.
            for p in busy:
                p.stop()
            print(f"\n  {YEL}interrupted{OFF}")
            return
        if self.state.current not in ("transcribing", "thinking", "speaking"):
            return
        self._interrupt.set()
        if self.speaker:
            self.speaker.cancel()
        if self.agent:
            self.agent.cancel()
        print(f"\n  {YEL}interrupted{OFF}")

    def heard_full_stop(self) -> bool:
        """Whether the wake engine's last hit was the "full stop" keyword."""
        return getattr(self.pipe, "heard_phrase", "") == STOP_PHRASE

    def full_stop(self) -> None:
        """Stop everything: every agent's turn, every voice, every window.

        What "full stop" does. Unlike the keybind it is not a no-op when
        nothing is busy, because it also closes each agent's follow-up
        window, so nobody is left listening for a next turn. The microphone
        stays on and waits for the wake word: muting it would leave no way
        back by voice.
        """
        for p in self.personas():
            p.follow_up = False
            if p.busy:
                p.stop()
        self.end_open_mic("full stop")
        self.collab.stop_all()          # collab: and the task queue
        # With one agent there is nothing else to stop: its turn runs on this
        # thread, so by the time a transcript is read it is already over, and
        # the wake word that let "full stop" be heard has stopped any reply.
        print(f"  {YEL}full stop — everything stopped{OFF}", flush=True)

    def take_command(self) -> str | None:
        """One-shot commands from the CLI, for what a signal cannot carry.

        Push-to-talk needs press and release as two distinct events, which is
        more signals than they are worth. A file is atomic enough when the
        writer renames it into place and the reader unlinks it. Interrupts
        stay on a signal, because the run loop is blocked inside playback
        exactly when an interrupt matters and would never read this.
        """
        path = RUNTIME_DIR / "command"
        if not path.exists():
            return None
        try:
            cmd = path.read_text().strip()
            path.unlink()
            return cmd
        except OSError:
            return None

    def take_typed(self) -> tuple[str, str] | None:
        """The oldest message from `agentvoice type`, as (agent id, text).

        A folder of files rather than the command file: a message can be any
        length and hold anything, and a command read by the lock poll in the
        middle of a reply would be lost. Each file is the agent id on its
        first line and the text after it, written privately and renamed into
        place by the CLI, which takes the text on stdin -- argv is readable
        by every account through /proc.
        """
        now = time.time()
        if now - getattr(self, "_typed_polled", 0.0) < 0.2:
            return None
        self._typed_polled = now
        folder = RUNTIME_DIR / "typed"
        try:
            names = sorted(e.name for e in os.scandir(folder)
                           if e.is_file() and e.name.endswith(".msg"))
        except OSError:
            return None
        for name in names:
            path = folder / name
            try:
                raw = path.read_bytes()[:TYPED_MAX * 4]
                path.unlink()
            except OSError:
                continue
            head, _, body = raw.decode("utf-8", "replace").partition("\n")
            agent_id = head.strip()
            if agent_id and not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", agent_id):
                continue
            text = " ".join(body.split())[:TYPED_MAX]
            if text:
                return agent_id, text
        return None

    def handle_typed(self, agent_id: str, text: str, crew: bool) -> None:
        """A typed message, sent the way a transcript would be."""
        if self.locked or self.yielded:
            print(f"  {DIM}(typed message dropped: the microphone is "
                  f"{'locked' if self.locked else 'lent out'}){OFF}", flush=True)
            return
        # Caught up first, so a typed turn is told what the settings and the
        # agent folders say now -- an instruction saved on the Agents page a
        # moment ago, a hand edit -- not what the last idle poll read. That
        # poll runs only while the microphone listens, and even then is up to
        # 2s old; a typed message arrives muted or not, often straight after
        # the save. Both were seen live (Phase 10). Typed turns are rare, and
        # a refresh with nothing changed reads no text.
        if self.pipe is not None:
            self.refresh()
        p = self._persona_by_id("" if agent_id in ("", "main") else agent_id)
        if p is None:
            print(f"  {YEL}typed message for an agent that is not here{OFF}",
                  flush=True)
            return
        if speech_is_logged(self.cfg.get_bool("logSpeech")):
            print(f"  {GRN}⌨ typed{OFF}  {BLD}{safe_for_terminal(text)}{OFF}",
                  flush=True)
        else:
            print(f"  {GRN}⌨ typed{OFF}", flush=True)
        last = {**_empty_turn(), "transcript": text, "typed": True}
        if is_full_stop(text):
            self.full_stop()
        elif crew:
            self._send(p, text, last, {}, typed=True)
        elif is_stop_command(text):
            self.silence()
        else:
            with self._as(p):
                self._here.typed = True
                try:
                    if not self.voice_command(self._main, text):
                        self.answer(text, last)
                finally:
                    self._here.typed = False
            # The turn is over: say so, keeping what was typed and answered
            # on screen. The run loop does this after a spoken turn; after a
            # typed one it went straight back to waiting, and while muted
            # nothing else publishes -- so the readout stayed on "speaking"
            # until the microphone came back (phase M2, testresults #10).
            self._publish(**last)

    # --- Try it (phase M6): one sentence on the draft personality -----------
    # The rules and the request format are in try_it.py; this is the part
    # that needs the daemon: who is busy, the agent's program and voice.

    def take_try(self):
        """The oldest `agentvoice try` request, as try_it.take() gives it."""
        now = time.time()
        if now - getattr(self, "_try_polled", 0.0) < 0.2:
            return None
        self._try_polled = now
        return try_it.take(now)

    def try_adapter(self, p: Persona, req: dict):
        """A throwaway adapter for p's program that may only talk: lowest
        level, none of the tools Agent Voice adds, no skills, no session kept,
        and the draft personality and instructions in place of the saved ones
        (absent from the request: the saved ones). None when p has none."""
        have = p.agent
        if have is None:
            return None
        program = getattr(have, "name", "") or None
        endpoint = None
        if hasattr(have, "base_url"):
            endpoint = (self.cfg.main_endpoint() if p is self._main
                        else (p.spec or {}).get("endpoint"))
            if not endpoint:
                return None
            endpoint = {**endpoint, "key": endpoint_key(_host(endpoint["url"]))}
            program = None
        instructions = req.get("instructions")
        side = load_adapter(name=program, endpoint=endpoint, spoken=True,
                            level="ask", ask_permission=True,
                            cwd=getattr(have, "cwd", None),
                            model=getattr(have, "model", None),
                            effort=getattr(have, "effort", None),
                            instructions=(instructions if instructions is not None
                                          else getattr(have, "instructions", "")),
                            named=getattr(have, "named", "") or "")
        if side is None:
            return None
        side.ephemeral = True
        side.no_tools = True
        for attr in ("desktop_tools", "browser_tools", "crew_tools"):
            if hasattr(side, attr):
                setattr(side, attr, False)
        if hasattr(side, "skill_dir"):
            side.skill_dir = None
        side.skill_text = ""
        side.parts = try_it.draft_parts(getattr(have, "parts", None), req.get("personality"))
        return side

    def handle_try(self, rid: str, req: dict | None) -> None:
        """`agentvoice try AGENT`, between turns, from the run loop: refuse
        with the reason, or run the side turn and say its first sentence in
        the agent's voice. Never a chat, never the readout; the journal gets
        the timing and the length, never the words."""
        if req is None:
            try_it.answer(rid, "refused", "the request could not be read")
            return
        if self.pipe is not None:
            self.refresh()
        p = self._persona_by_id("" if req["agent"] == "main" else req["agent"])
        label = (p.label or p.name or req["agent"]) if p is not None else req["agent"]
        # Asked afresh, not the last poll's answer: the poll is 2 s old at
        # worst, and "cannot tell" is a refusal here (Codex review of M6).
        locked = True if self.locked else session_locked()
        why = try_it.refusal(
            locked=locked, yielded=self.yielded, known=p is not None, label=label,
            has_program=p is not None and p.agent is not None,
            problem=(getattr(p, "problem", "") or "") if p is not None else "",
            target_busy=p is not None and p.busy,
            other_busy=any(q.busy for q in self.personas() if q is not p) or self._speaking,
            since_last=time.monotonic() - getattr(self, "_try_at", -1e9),
            stale=bool(req.get("stale")))
        side = None
        if not why:
            try:
                side = self.try_adapter(p, req)
            except Exception as e:          # noqa: BLE001
                print(f"  {YEL}try: could not build the agent ({type(e).__name__}){OFF}",
                      flush=True)
            if side is None:
                why = f"{label}'s program could not be started"
            else:
                why = try_it.backend_refusal(
                    getattr(side, "name", "") or "", hasattr(side, "base_url"),
                    bool(getattr(side, "is_agent", False)))
        if why:
            print(f"  {DIM}(try for {req['agent']} refused){OFF}", flush=True)
            try_it.answer(rid, "refused", why)
            return
        self._try_at = time.monotonic()
        try_it.answer(rid, "accepted")
        t0 = time.monotonic()
        timer = threading.Timer(try_it.TURN_TIMEOUT_S, side.cancel)
        timer.daemon = True
        timer.start()
        sentence, crash = "", ""
        # The stream is held here, not handed straight in: dropped as soon as
        # the first sentence is out, the adapter's generator would run its
        # own cleanup first and could let go of a process cancel() then
        # cannot reach (Codex review of M6). Cancel, then close.
        stream = None
        try:
            stream = side.send(try_it.PROMPT, None)
            sentence = try_it.first_sentence(stream)
        except Exception as e:              # noqa: BLE001
            crash = type(e).__name__
        finally:
            timer.cancel()
            try:
                side.cancel()               # thrown away: no process left behind
            except Exception:
                pass
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass
        took = time.monotonic() - t0
        # The length and the exception's class name: never the words.
        size = len(sentence)
        print(f"  try: {req['agent']} answered in {took:.1f}s ({size} chars"
              f"{', ' + crash if crash else ''})", flush=True)
        if not sentence:
            self.deafen(0)                  # what the microphone queued meanwhile
            try_it.answer(rid, "failed", "it took too long" if took >= try_it.TURN_TIMEOUT_S
                          else f"{label} gave no answer")
            return
        # Said the way a typed reply is: through speak(), which checks the
        # lock and a lent microphone itself before and during the sentence;
        # `typed` lets it speak while muted, as a typed turn does.
        # And the lock asked once more just before: the turn took seconds.
        now = True if self.locked else session_locked()
        if now is not False:
            try_it.answer(rid, "failed", "the screen locked" if now else
                          "cannot tell whether the screen is locked, so it was not said")
            self.deafen(0)
            return
        was = getattr(self._here, "typed", False)
        self._here.typed = True
        try:
            said = self._say_for(p, sentence)
        finally:
            self._here.typed = was
        if said:
            try_it.answer(rid, "said", text=sentence)
        else:
            try_it.answer(rid, "failed", "the screen locked" if self.locked
                          else "the microphone was lent to a call" if self.yielded
                          else "it was stopped before the end")

    # --- chat names and summaries (phase M19) --------------------------------
    # The rules are in chat_names.py; this is the part that needs the daemon:
    # who owns a chat now, what program it runs, whether anyone is busy.

    def name_chats(self, now: float | None = None) -> str:
        """From the idle poll: when a saved chat has gone quiet, start one
        quiet side turn on its own agent to name and summarise it, in a
        thread, so a wake word said meanwhile is heard. At most one running.
        Returns what it did, for tests: "", "started", or the refusal."""
        now = time.time() if now is None else now
        if now - getattr(self, "_named_look", 0.0) < chat_names.LOOK_EVERY_S:
            return ""
        self._named_look = now
        running = getattr(self, "_namer", None)
        if running is not None and running.is_alive():
            return "running"
        if self.cfg.chat_summaries() != "owner":
            return "off"
        if not self.chats.root.is_dir():
            return "nothing saved"
        try:
            index = self.chats.list()
        except (OSError, ValueError):
            return "the index cannot be read"
        budget = getattr(self, "_named_budget", None)
        if budget is None:
            budget = self._named_budget = chat_names.Budget()
            budget.seed(index, now)
        if budget.left(now) <= 0:
            return "ten this hour"
        # Refused for a reason of the chat's own (its agent is gone, runs on
        # another program): not looked at again until the chat changes.
        # Kept only while the chat is still listed unchanged, so it stays as
        # small as the index.
        listed = {m.get("id"): m.get("updated") for m in index if isinstance(m, dict)}
        refused = {cid: at for cid, at in (getattr(self, "_named_refused", None) or {}).items()
                   if listed.get(cid) == at}
        self._named_refused = refused
        meta = chat_names.pick(index, now, set(refused))
        if meta is None:
            return ""
        cid, updated = meta["id"], meta.get("updated")
        chat = self.chats.load(cid)
        if chat is None:
            refused[cid] = updated
            return "gone"
        owner = chat_schema.owner_of(chat)
        p = self._persona_by_id(chat_schema.internal(owner))
        have = None
        if p is not None:
            have = self.agent if p is self._main else p.agent
        endpoint = None
        if have is not None and hasattr(have, "base_url"):
            endpoint = (self.cfg.main_endpoint() if p is self._main
                        else (p.spec or {}).get("endpoint"))
            if endpoint:
                endpoint = {**endpoint, "key": endpoint_key(_host(endpoint["url"]))}
        locked = True if self.locked else session_locked()
        why = chat_names.refusal(
            mode_now="owner", locked=locked, quarantine=self.cfg.quarantined(),
            owner=owner, known=p is not None,
            has_program=have is not None and (endpoint is not None
                                               or not hasattr(have, "base_url")),
            chat_backend=str(chat.get("backend") or ""),
            program=(getattr(have, "name", "") or "") if have is not None else "",
            endpoint=endpoint is not None,
            endpoint_is_agent=bool(getattr(have, "is_agent", False)),
            busy=any(q.busy for q in self.personas()) or self._speaking
                 or self.yielded or getattr(self, "_capture_for", None) is not None)
        side = None
        if not why:
            try:
                side = chat_names.make_side(load_adapter, have, endpoint)
            except Exception as e:          # noqa: BLE001
                print(f"  {YEL}chat name: could not build the agent ({type(e).__name__}){OFF}",
                      flush=True)
            if side is None:
                why = "its program could not be started"
        if why:
            if why not in ("the screen is locked", "cannot tell whether the screen is locked",
                           "an agent is busy", "the crew settings cannot be read"):
                refused[cid] = updated
            self.say_once("chat-name", f"  {DIM}(chat not named: {why}){OFF}")
            return why
        request = chat_names.prompt(chat)
        budget.spend(now)
        self._namer = threading.Thread(target=self._name_one, name="chat-name", daemon=True,
                                       args=(side, cid, updated, request, now))
        self._namer.start()
        return "started"

    def _name_one(self, side, cid: str, updated, request: str, at: float) -> None:
        """The side turn, in its own thread: send, read, cancel, store. The
        journal gets seconds and lengths, never the chat or the name."""
        t0 = time.monotonic()
        timer = threading.Timer(chat_names.TURN_TIMEOUT_S, side.cancel)
        timer.daemon = True
        timer.start()
        got, crash, stream = "", "", None
        try:
            stream = side.send(request, None)
            got = chat_names.read_reply(stream, t0 + chat_names.TURN_TIMEOUT_S)
        except Exception as e:              # noqa: BLE001
            crash = type(e).__name__
        finally:
            timer.cancel()
            try:
                side.cancel()               # thrown away: no process left behind
            except Exception:
                pass
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass
        took = time.monotonic() - t0
        named = chat_names.parse(got)
        # Switched off, or saving stopped, while it ran: nothing is kept.
        if self.cfg.chat_summaries() != "owner":
            print(f"  {DIM}chat name dropped: switched off while it ran{OFF}", flush=True)
            return
        try:
            kept = self.chats.set_name(cid, for_updated=updated, at=at,
                                       title=named[0] if named else "",
                                       summary=named[1] if named else "")
        except (OSError, ValueError) as e:
            print(f"  {YEL}chat name not saved: {type(e).__name__}{OFF}", flush=True)
            return
        sizes = f"{len(named[0])}+{len(named[1])} chars" if named else "no name in it"
        print(f"  chat named in {took:.1f}s ({sizes}{', ' + crash if crash else ''}"
              f"{'' if kept else ', the chat is gone'})", flush=True)

    def _publish(self, **extra):
        # "locked" is its own state rather than "off": the panel should be
        # able to say why the microphone is closed, because "off" invites
        # someone to turn it back on and wonder why nothing happens.
        # Ordered by which truth matters most. A locked screen outranks a
        # borrowed microphone, and both outrank "listening": the panel has to
        # be able to say *why* it is not hearing you, because "off" invites
        # someone to turn it back on and wonder why nothing happens.
        if self.locked:
            state = "locked"
        elif self.enabled and self.yielded:
            state = "yielded"
        else:
            state = "listening" if self.enabled else "off"
        self.state.publish(state, **extra)

    def banner(self):
        p = self.pipe
        print(f"\n  {BLD}listening{OFF} for {CYA}\"{p.phrase}\"{OFF}"
              f"   {DIM}lead-in {p.lead_in_ms}ms · trailing {p.trailing_ms}ms{OFF}")
        # The detection threshold is openWakeWord's and the grammar confidence
        # is Vosk's; printing the second one on the first engine showed a number
        # that did nothing while the number that mattered was invisible after
        # startup -- which is how a stale 0.90 went unnoticed through two
        # attempts to lower it.
        second = (f"detection {p.detection_threshold:.2f}"
                  if p.detection_threshold is not None
                  else f"confidence {p.wake_confidence:.2f}")
        gate = (f"gate follows the room (+{p._floor.margin_db:.0f} dB)"
                if getattr(p, "adaptive_gate", False) else f"gate {p.threshold_db:.0f} dBFS")
        print(f"  {DIM}{gate} · {second} "
              f"· {self.cfg.source}{OFF}")
        forgets = self.agent is not None and not getattr(self.agent, "remembers", False)
        if p.conversation and forgets:
            print(f"  {YEL}conversation: on, {p.follow_up_ms / 1000:.0f}s window — but "
                  f"{self.agent.name} starts fresh every turn, so it saves you the "
                  f"wake word and nothing else{OFF}")
        else:
            print(f"  {DIM}conversation: "
                  f"{f'on, {p.follow_up_ms / 1000:.0f}s follow-up window' if p.conversation else 'off'}"
                  f"{OFF}")
        who = f"{self.agent.name}" if self.agent else "nobody (echo mode)"
        # A setting called "ask before it changes anything" must not quietly
        # mean nothing. Only Claude Code can raise a prompt from here; the
        # others are held in whatever read-only or ask-first mode their CLI
        # has, which is weaker and worth saying out loud.
        if self.agent and not getattr(self.agent, "has_tools", True):
            print(f"  {DIM}permission: agentvoice offers {self.agent.name} no "
                  f"tools, so there is nothing here to permit{OFF}")
        elif self.agent and not getattr(self.agent, "can_be_gated", True):
            print(f"  {YEL}permission: agentvoice cannot restrain this endpoint. "
                  f"It is given no flags, no hook and no sandbox — whatever it "
                  f"is allowed to do on its own host, it will do{OFF}")
        elif self.agent and self.level() != "trusted":
            if getattr(self.agent, "guards_permissions", False):
                print(f"  {DIM}permission: prompts on screen{OFF}")
            else:
                print(f"  {YEL}permission: {self.agent.name} cannot prompt from here."
                      f" Running in its safest mode instead — it may refuse work"
                      f" rather than ask.{OFF}")
        elif self.agent:
            print(f"  {YEL}permission: not asking. {self.agent.name} can change"
                  f" files and run commands unchallenged.{OFF}")
        if self.agent and getattr(self.agent, "cwd", None):
            print(f"  {DIM}project: {self.agent.cwd} · {self.posture()}{OFF}")
        elif self.agent:
            # No cwd to speak of: it never touches the filesystem.
            print(f"  {DIM}{self.posture()}{OFF}")
        print(f"  {DIM}agent: {who} · voice: "
              f"{self.speaker.name if self.speaker else 'off'}"
              f"   (ctrl-c to stop){OFF}\n")

    def refresh(self):
        """Between turns, re-read config and re-announce if it moved."""
        # Outside the reload guard: `omarchy default agent` writes its own
        # file, which cfg.reload() does not watch, so a switch at the desktop
        # would otherwise not reach the daemon until it restarted.
        # Deliberately *not* reconcile_lock() here. refresh() is called from
        # below the gate in the run loop, so a lock check here would stop
        # being called the moment it closed the gate -- see the dedicated
        # poll in run(), which is above it.
        # The settings first, so everything below works from what they say
        # now: a typed turn straight after a change (handle_typed refreshes
        # before it runs) is otherwise told the old values (Phase 10 review).
        # What depends on the wake engine is caught up at the end, after
        # pipe.apply, when it changed.
        changed = self.cfg.reload()
        self.catch_up()
        # Outside the guard for the same reason: a voice arrives on disk when
        # the installer fetches it, and a file appearing changes no setting.
        # Behind the guard, a substitution outlived its own download until
        # something unrelated was touched -- the same shape of stall as the
        # detection threshold that never reached the running engine.
        self.reconcile_voice()
        self.pipe.reconcile_vocab()
        # Outside the guard: headphones going on is not a setting change.
        # Asked here, on the idle poll, so that the answer is already known
        # when a reply starts and the 23ms is never in front of a word.
        self.reconcile_output()
        # Off means gone, not merely paused: someone who turns it off is
        # saying they do not want the session's words kept, including the
        # ones already kept. Outside the guard, so it also holds for a file
        # left from earlier in the session when the daemon starts.
        if not self.cfg.get_bool("keepHistory"):
            self.history.clear()
        # phase M2: a notice outlives the turn it explained only until the
        # agent answers again, and today's limit count rolls over at midnight.
        if self.expire_notices():
            self._recompose()
        if self.limit_hits_rolled():
            self.publish_agent()
        if not changed:
            return
        self.pipe.apply(self.cfg)
        self.reconcile_voice()
        # The names the wake engine can hear may have changed with it.
        self.reconcile_crew()
        self.reconcile_parts()
        print(f"  {CYA}knobs updated{OFF}")

    def catch_up(self) -> None:
        """The part of refresh() that decides what each agent is and is told,
        outside the reload guard."""
        # Outside the guard: the agent folders are files, and a hand edit
        # changes no setting (merged plan, Phase 9). Before the agents,
        # because the instructions the calls after it hand them come from
        # what this read (Phase 10).
        self.reconcile_agent_files()
        self.reconcile_agent()
        self.reconcile_crew()
        self.reconcile_extras()
        # After the crew, so the roster in each agent's prompt is the crew
        # just reconciled, and after the extras, so the size it logs is the
        # whole preamble, Omarchy commands included (Phase 11).
        self.reconcile_parts()
        # Phase M16: last, so each line is built from what this poll handed
        # the adapter. Before the parts, the first line after a start lacked
        # the roster, and a turn starting then kept that line on the page
        # (a busy agent's line is not rebuilt) -- seen on the installed build.
        self.publish_runinfo(self.personas())

    def catch_up_one(self, p: Persona) -> None:
        """What `p` is told, brought up to date: for an agent whose turn
        dispatch() just stopped, which every refresh until then passed by
        because it was busy (Phase 11 review). Its instructions, prompt
        parts and tool switches (Phase 13 review: a turn that replaced a
        running one kept Chrome after it was switched off); a changed
        setting (model, level) still waits for the next idle poll, as it
        always has."""
        self.reconcile_agent_files()
        agent = p.agent
        if agent is not None:
            if p is self._main:
                want = self.instructions_for("", self.cfg["agentInstructions"])
            else:
                spec = p.spec or {}
                want = self.instructions_for(p.id, spec.get("instructions", ""))
                p.spec = {**spec, "instructions": want}
            if getattr(agent, "instructions", "") != want:
                agent.instructions = want
        self.reconcile_parts()
        extras_for = self.agent if getattr(p, "main", False) else agent
        if extras_for is not None:
            self.apply_extras(extras_for, p)

    def reconcile_agent_files(self) -> None:
        """Notice a change to the agent and communal folders (Phase 9).

        Compares file stamps only, so an idle poll with nothing changed reads
        no text. On a change it re-reads every folder through agentfs, which
        keeps each file's last good text in this process, publishes the
        problems and the files changed outside Settings, and logs one
        structural line of sizes -- never the text. It keeps each agent's
        instructions for instructions_for (Phase 10); Phase 11 hands the
        rest of what it read to the agents. A failed read keeps the
        instructions it had, and the prompt parts it had (Phase 11).
        """
        try:
            # Phase M12: a transfer some other process left unfinished (it
            # died holding the lock) is settled here too, without waiting on
            # the lock: one held is a transfer under way, not a crash.
            import transfer
            if transfer.pending():
                for r in transfer.recover(block=False) or []:
                    print(f"  {YEL}skill transfer {r['op']}: {r['done']}{OFF}", flush=True)
        except Exception as e:  # the idle poll must never stop on this
            self.say_once("transfer-recover", f"  {YEL}skill transfers: could not be "
                                              f"checked ({type(e).__name__}){OFF}")
        try:
            import agentfs
            now = agentfs.stamp()
            if now == getattr(self, "_agentfs_stamp", None):
                return
            summary, texts = agentfs.snapshot()
            # Before the comparison below: an edit that keeps every size
            # still changes what the agent is told.
            self._folder_texts = texts
            # Only once it was read: a failed read is tried again next poll.
            self._agentfs_stamp = now
        except Exception as e:  # the idle poll must never stop on this
            summary = {"error": f"{type(e).__name__}"}
            # Forget the last good stamp too, so recovering to it publishes
            # the recovery instead of leaving the error on screen.
            self._agentfs_stamp = None
        # Starts as {} so a machine with no folders yet logs and publishes
        # nothing at all: until Phase 10 creates them, that is every machine.
        if summary == getattr(self, "_agent_files", {}):
            return
        self._agent_files = summary
        parts = []
        for target, v in summary.items():
            if not isinstance(v, dict):
                parts.append(f"{target} {v}")
                continue
            sizes = " ".join(f"{n.removesuffix('.md')} {f['chars']}"
                             for n, f in v["files"].items() if f["exists"])
            flags = ""
            if v["changed_outside"]:
                flags += f" · {len(v['changed_outside'])} changed outside"
            if v["problems"]:
                flags += f" · {len(v['problems'])} problem(s)"
            parts.append(f"{target}: {sizes or 'empty'}{flags}")
        print(f"  {DIM}agent files: {' | '.join(parts) or 'none'}{OFF}",
              flush=True)
        try:
            self.publish_agent()
        except Exception as e:
            # Published again on the next change, or by whatever publishes
            # next; the poll goes on.
            print(f"  {YEL}agent files: could not publish ({type(e).__name__}){OFF}",
                  flush=True)

    def announce_permission(self, p: Persona, tail_ms: int) -> bool:
        """Say a pending question out loud, once, if the hook marked it to be
        and it is this agent's. True if something was said.

        Only ever a fixed sentence and the action's own summary -- never the
        tool's input, which for a typed action is the text being typed.
        The cards are the daemon's own since phase M7 (cards.py)."""
        said = self.__dict__.setdefault("_announced", set())
        desk = getattr(self, "cards", None)
        if desk is None:
            return False
        for req in desk.pending():
            cid = str(req.get("id") or "")
            if not cid or cid in said:
                continue
            if req.get("announce") is not True:
                continue
            if str(req.get("who") or "") != (p.id or ""):
                continue
            said.add(cid)
            summary = ""
            inp = req.get("input")
            if isinstance(inp, dict):
                summary = " ".join(str(inp.get("action_summary") or "").split())[:160]
            who = p.label or req.get("label") or "The agent"
            line = (f"{who} is asking first: {summary.rstrip('.')}. Answer on screen."
                    if summary else
                    f"{who} is asking first before it acts in your browser. "
                    f"Answer on screen.")
            print(f"  {CYA}browser question said out loud{OFF}", flush=True)
            self.speak(line, tail_ms)
            return True
        return False

    def reconcile_extras(self) -> None:
        """Desktop tools and the Omarchy skill, on every idle agent (plan 12a,
        12b). Outside the reload guard: the skill is a file, rebuilt when
        Omarchy updates, and a file changes with no setting change at all."""
        agents = [self._main] + list(getattr(self, "crew", {}).values())
        wanted = any(self.tools_for(p)["omarchySkill"] for p in agents)
        if wanted and not getattr(self, "_skill_checked", True):
            # Once per daemon: built at install, rebuilt here only when the
            # Omarchy version moved underneath it. On a thread, because
            # asking omarchy for its command list takes about a second.
            self._skill_checked = True
            threading.Thread(target=self._rebuild_skill, daemon=True).start()
        # Phase M14: how Agent Voice works, rebuilt when a command, a wake
        # phrase or a setting moved (a stat check, no read, when nothing did).
        if any(self.tools_for(p)["agentvoiceSkill"] for p in agents):
            self._refresh_agentvoice_skill()
        for p in agents:
            agent = self.agent if p.main else p.agent
            if agent is not None and not p.busy:
                self.apply_extras(agent, p)
        self.publish_live_tools(agents)

    def _refresh_agentvoice_skill(self) -> None:
        """Build the Agent Voice skill when it is missing or its inputs
        changed (agentvoice_skill.stale). A build that is refused or fails
        keeps the earlier skill, says so once, and is not tried again until
        the inputs change: it would only fail the same way every poll."""
        try:
            if not agentvoice_skill.stale(self.cfg):
                return
            now = agentvoice_skill.stamp(self.cfg)
            if getattr(self, "_av_skill_failed", None) == now:
                return
            try:
                result = agentvoice_skill.build(cfg=self.cfg)
                self._av_skill_failed = None
                print(f"  {CYA}agentvoice skill rebuilt: {result['chars']} characters{OFF}",
                      flush=True)
            except Exception as e:          # a skill is never worth a turn
                self._av_skill_failed = now
                why = str(e) if isinstance(e, agentvoice_skill.SkillRefused) else type(e).__name__
                print(f"  {YEL}agentvoice skill not rebuilt: {why}{OFF}", flush=True)
        except Exception:
            pass

    def publish_live_tools(self, agents) -> None:
        """Which MCP servers each Claude agent's last process said it
        started (its init event), for the Tools & skills tab's "running"
        (phase M10; M16 reads it too). Written only when it changed."""
        live = {}
        for p in agents:
            agent = self.agent if p.main else p.agent
            servers = getattr(agent, "live_servers", None)
            if servers is not None:
                live["main" if p.main else (p.id or "")] = {"servers": servers}
        if live == getattr(self, "_live_tools", {}):
            return
        self._live_tools = live
        try:
            import tooldetect
            tooldetect.write_live(live)
        except Exception:
            pass

    #: Seconds between rebuilds of every agent's launch line when nothing
    #: visible moved (a config.toml or a scan can change underneath).
    RUNINFO_EVERY_S = 10.0

    def publish_runinfo(self, agents, now: float | None = None) -> bool:
        """What each agent runs, for Agent details → Advanced (phase M16):
        its adapter's own next launch line and its last real one (redacted),
        session, timeouts, the servers it is given, its log ring. Built from
        the live adapters (runinfo.record_for), so it is what runs. Written
        when something moved, else every RUNINFO_EVERY_S. True if written."""
        try:
            return self._publish_runinfo(agents, time.time() if now is None else now)
        except Exception:               # noqa: BLE001 -- a page is never worth a turn
            return False

    def _publish_runinfo(self, agents, now: float) -> bool:
        def is_main(p):
            return getattr(p, "main", getattr(p, "spec", None) is None)
        pairs = [(p, self.agent if is_main(p) else getattr(p, "agent", None)) for p in agents]
        key = tuple((getattr(p, "id", ""), id(agent), getattr(p, "session_id", None),
                     getattr(p, "busy", False), getattr(p, "state", ""),
                     (getattr(agent, "last_launch", None) or {}).get("at"))
                    for p, agent in pairs) + (self.agent_ring.version,)
        if key == self._runinfo_key and now - self._runinfo_at < self.RUNINFO_EVERY_S:
            return False
        records = {}
        for p, agent in pairs:
            aid = "main" if is_main(p) else (getattr(p, "id", "") or "")
            if not aid:
                continue
            sid = getattr(p, "session_id", None)
            try:
                rec = runinfo.record_for(
                    agent, session_id=sid, turns=self.agent_ring.turns(aid, sid),
                    busy=getattr(p, "busy", False), state=getattr(p, "state", ""),
                    previous=self._runinfo.get(aid))
            except Exception:           # noqa: BLE001 -- a page is never worth a turn
                rec = {"program": getattr(agent, "name", "") or ""}
            rec["log"] = self.agent_ring.lines(aid)
            records[aid] = rec
        self._runinfo_key, self._runinfo_at = key, now
        if records == self._runinfo:
            return False
        self._runinfo = records
        runinfo.write(records)
        return True

    def _rebuild_skill(self) -> None:
        try:
            if omarchy_skill.stale():
                result = omarchy_skill.build()
                if not result.get("skipped"):
                    print(f"  {CYA}omarchy skill rebuilt: {result['commands']} "
                          f"commands, {result['keybindings']} keybindings{OFF}",
                          flush=True)
        except Exception as e:              # a skill is never worth a turn
            print(f"  {YEL}omarchy skill not rebuilt: {type(e).__name__}{OFF}",
                  flush=True)

    def tools_for(self, p) -> dict:
        """The tool switches for persona `p` (Phase 13): its own where it
        says on or off, else the setting for every agent. Read fresh."""
        try:
            return self.cfg.tools_for(getattr(p, "id", "") or "")
        except Exception:               # an odd setting is the globals
            return {"desktop": self.cfg.get_bool("desktopTools"),
                    "browser": self.cfg.get_bool("browserTools"),
                    "omarchySkill": self.cfg.get_bool("omarchySkill")}

    def skills_off_for(self, p):
        """The skills switched off for persona `p` (phase M11), by name, or
        None when that cannot be known (agentfs.skill_set: no communal skill
        then). Read fresh; an odd setting is None."""
        try:
            return self.cfg.skills_off_for("" if getattr(p, "main", False) or p is None
                                           else getattr(p, "id", "") or "")
        except Exception:
            return None

    def takes_communal(self, p) -> bool:
        """Whether persona `p` takes the communal rules, defaults and skills
        (phase M15, `communalOff`). Read fresh; anything odd is yes, as an
        unreadable list is (Config.communal_off)."""
        try:
            return self.cfg.takes_communal("" if getattr(p, "main", False) or p is None
                                           else getattr(p, "id", "") or "")
        except Exception:
            return True

    def plugin_dir_for(self, p, omarchy_root: str | None,
                       agentvoice_root: str | None = None) -> str | None:
        """Persona `p`'s Claude plugin folder (Phase 13): the Omarchy skill
        when `omarchy_root` is given, and its own and the communal skills.
        Built again only when the folders changed (their stamp) or the
        Omarchy skill moved, so the idle poll copies nothing. A build that
        fails keeps the Omarchy skill alone and says so once."""
        import agentfs
        fid = agentfs.folder_id(getattr(p, "id", "") or "")
        # The Omarchy skill is rebuilt in place when Omarchy updates, so its
        # file's revision is in the key, not only its folder's path.
        revision = None
        if omarchy_root:
            try:
                st = os.stat(Path(omarchy_root) / "skills" / "omarchy" / "SKILL.md")
                revision = (st.st_mtime_ns, st.st_size)
            except OSError:
                pass
        # And the Agent Voice skill's (phase M14), rebuilt in place whenever
        # its inputs change: a new revision is a new plugin folder.
        av_revision = None
        if agentvoice_root:
            try:
                st = os.stat(Path(agentvoice_root) / "skills" / "agentvoice" / "SKILL.md")
                av_revision = (st.st_mtime_ns, st.st_size)
            except OSError:
                pass
        # The skills switched off for it are in the key too (phase M11): a
        # switch moved is a different folder, and nothing else would notice.
        off = self.skills_off_for(p)
        # And whether it takes Communal at all (phase M15).
        communal_on = self.takes_communal(p)
        key = (omarchy_root, revision, getattr(self, "_agentfs_stamp", None),
               None if off is None else tuple(sorted(off)),
               agentvoice_root, av_revision, communal_on)
        cache = self.__dict__.setdefault("_plugin_dirs", {})
        have = cache.get(fid)
        now = time.monotonic()
        if (have is not None and have[0] == key and key[2] is not None
                and (have[2] is None or now < have[2])):
            return have[1]
        try:
            got, retry = agentfs.plugin_dir(fid, omarchy_root, off, agentvoice_root,
                                            communal_on), None
        except Exception as e:
            self.say_once(f"plugins-{fid}", f"  {YEL}skills for “{fid}”: not given "
                                            f"({type(e).__name__}){OFF}")
            # Tried again in a while even with nothing changed: a full disk
            # or a busy file clears on its own (Phase 13 review).
            got, retry = omarchy_root or agentvoice_root, now + 30.0
        cache[fid] = (key, got, retry)
        return got

    def detected_for(self, agent, p) -> dict:
        """What `agent` (persona `p`'s) is handed from the tools found on
        this machine (phase M10, tooldetect.delivery): servers for Claude
        Code, the config.toml servers Codex may start, and the CLIs it is
        told it may use and told are off. Anything that goes wrong hands it
        nothing, and says so once: a tool is off until it is shown to be on."""
        empty = {"servers": {}, "mcp_on": {}, "clis_on": [], "clis_off": []}
        program = getattr(agent, "name", "") or ""
        if not program:
            return empty
        try:
            import tooldetect
            agent_id = getattr(p, "id", "") or ""
            if getattr(p, "main", False) or p is None:
                agent_id, project = "", self.cfg.get_str("projectDir")
            else:
                project = str((getattr(p, "spec", None) or {}).get("projectDir") or "")
            scanned, defs = tooldetect.scan_cached(self.cfg, with_defs=True)
            got = tooldetect.delivery(self.cfg, agent_id, program, project, scanned, defs)
            return {"servers": got["servers"], "mcp_on": got["codex_on"] if program == "codex" else {},
                    "clis_on": got["clis_on"], "clis_off": got["clis_off"]}
        except Exception as e:      # never worth a turn; never a tool given on a guess
            who = getattr(p, "label", "") or "main"
            self.say_once(f"detected-{who}", f"  {YEL}tools found on this machine: not given to "
                                              f"“{who}” ({type(e).__name__}){OFF}")
            return empty

    def native_skills_off(self, agent, p) -> tuple[tuple, str]:
        """(the names to switch off where `agent`'s CLI looks, why they
        cannot be named or ""): skillscan.native_off over the folder texts
        last read, so an idle poll reads no file. When the switch list
        cannot be read and a skills folder cannot be listed either, no name
        can be given: the reason goes to the adapter, which then starts no
        turn (Codex) or gives no skill at all (Claude), and is said once."""
        program = getattr(agent, "name", "") or ""
        try:
            import agentfs
            import skillscan
            fid = "main" if getattr(p, "main", False) or p is None else (getattr(p, "id", "") or "main")
            texts = getattr(self, "_folder_texts", None) or {}
            # The communal folder's names only when it takes Communal (M15):
            # its CLI's own copy is hidden for a skill Agent Voice gives it.
            names = {s["name"] for t in (fid, agentfs.COMMUNAL)
                     if t != agentfs.COMMUNAL or self.takes_communal(p)
                     for s in agentfs.skills_from(texts, t)}
            agent_id = "" if fid == "main" else fid
            return tuple(skillscan.native_off(self.cfg, agent_id, program, names)), ""
        except Exception as e:      # never a skill offered on a guess
            who = getattr(p, "label", "") or "main"
            why = (str(e) if type(e).__name__ == "SkillsUnknown"
                   else f"the skills it finds by itself could not be worked out ({type(e).__name__})")
            self.say_once(f"skills-{who}", f"  {YEL}skills for “{who}”: {why}{OFF}")
            return (), f"Agent Voice could not tell which skills to switch off ({why})."

    def apply_extras(self, agent, p=None) -> bool:
        """Give `agent` (persona `p`'s) the desktop tools, the browser, the
        Omarchy skill and its skills, as its switches ask (Phase 13; before
        it, the settings for every agent). All are read when its process
        starts, so a change lets the idle process go -- the conversation is
        kept, as for instructions. True when anything changed."""
        changed = False
        tools = self.tools_for(p)
        skill_on = tools["omarchySkill"]
        av_on = tools["agentvoiceSkill"]
        if hasattr(agent, "desktop_tools"):
            want = tools["desktop"]
            if agent.desktop_tools != want:
                agent.desktop_tools, changed = want, True
        if hasattr(agent, "browser_tools"):
            want = tools["browser"]
            if agent.browser_tools != want:
                agent.browser_tools, changed = want, True
        if hasattr(agent, "skill_dir"):
            want = self.plugin_dir_for(p, omarchy_skill.plugin_dir() if skill_on else None,
                                       agentvoice_skill.plugin_dir() if av_on else None)
            if agent.skill_dir != want:
                agent.skill_dir, changed = want, True
        # Phase M11: the skills its CLI finds by itself, switched off where
        # the CLI looks -- each one in its skillsOff, and each Agent Voice
        # skill's name so the CLI's own of that name is not offered beside
        # it. Read when a process starts, so a change lets the idle one go.
        if hasattr(agent, "skills_off"):
            want_off, unknown = self.native_skills_off(agent, p)
            if tuple(getattr(agent, "skills_off", ()) or ()) != want_off:
                agent.skills_off, changed = want_off, True
            if getattr(agent, "skills_unknown", "") != unknown:
                agent.skills_unknown, changed = unknown, True
        if getattr(agent, "takes_skill_text", False) and getattr(agent, "has_tools", False):
            # The Omarchy commands, then (phase M14) one line saying where to
            # read how Agent Voice works.
            want = "\n\n".join(t for t in (omarchy_skill.instructions() if skill_on else "",
                                           agentvoice_skill.instructions() if av_on else "") if t)
            if getattr(agent, "skill_text", "") != want:
                agent.skill_text, changed = want, True
        if getattr(agent, "crew_tools", False):
            # collab: the crew server lists the collaboration tools unless
            # this agent's collaboration is off or it is quarantined (M8),
            # when its process starts; a change lets the idle process go
            # (Phase 16).
            try:
                import crew_mcp
                want = crew_mcp.offers_collab(self.cfg, getattr(p, "id", "") or "")
            except Exception:
                want = False
            if getattr(agent, "collab_listed", None) is None:
                agent.collab_listed = want
            elif agent.collab_listed != want:
                agent.collab_listed, changed = want, True
        # Phase M10: the tools found on this machine, as this agent's own
        # switches, the ones for every agent and each tool's fingerprint now
        # say. All read when a process starts, so a change lets the idle
        # one go, like the rest; a Claude process still running is held by
        # the permission hook, which refuses a server switched off since.
        got = self.detected_for(agent, p)
        for attr, want in (("detected_servers", got["servers"]),
                           ("clis_denied", tuple(got["clis_off"])),
                           ("mcp_on", dict(got["mcp_on"]))):
            if hasattr(agent, attr) and getattr(agent, attr) != want:
                setattr(agent, attr, want)
                changed = True
        if getattr(agent, "has_tools", False):
            for attr, want in (("clis_on", tuple(got["clis_on"])), ("clis_off", tuple(got["clis_off"]))):
                if getattr(agent, attr, ()) != want:
                    setattr(agent, attr, want)
                    changed = True
        launched = self.apply_launch(agent, p)
        if changed or launched:
            try:
                agent.cancel()
            except Exception:
                pass
        if changed:
            # Structural: which tools, and the plugin folder's name (an id
            # and a hash), never a skill's text.
            have = [k for k, a in (("desktop", "desktop_tools"), ("browser", "browser_tools"))
                    if getattr(agent, a, False)]
            if skill_on and (getattr(agent, "skill_dir", None) or getattr(agent, "skill_text", "")):
                have.append("omarchy")
            if av_on and (getattr(agent, "skill_dir", None) or getattr(agent, "skill_text", "")):
                have.append("agentvoice")
            # Counts only: a server's or a CLI's name can say what the
            # person uses, and names are on the page, not in the journal.
            found = len(getattr(agent, "detected_servers", None) or {}) + \
                len(getattr(agent, "mcp_on", None) or ())
            if found:
                have.append(f"{found} found server{'s' if found != 1 else ''}")
            if getattr(agent, "clis_on", ()):
                have.append(f"{len(agent.clis_on)} CLI{'s' if len(agent.clis_on) != 1 else ''}")
            folder = getattr(agent, "skill_dir", None)
            who = getattr(p, "label", "") or getattr(p, "name", "") or "main"
            print(f"  {DIM}tools for “{who}”: {' · '.join(have) or 'none'}"
                  f"{' · plugins ' + Path(folder).name if folder else ''}{OFF}", flush=True)
        return changed or launched

    def launch_for(self, p) -> dict:
        """How persona `p`'s program is launched (phase M17,
        Config.launch_for), read fresh. Anything odd is the defaults: it
        resumes, 90 seconds, nothing extra."""
        try:
            aid = "" if p is None or getattr(p, "main", False) else (getattr(p, "id", "") or "")
            return self.cfg.launch_for(aid)
        except Exception:
            return {"resume": True, "idle_s": 90, "args": ()}

    def apply_launch(self, agent, p=None) -> bool:
        """Hand `agent` how it is launched (phase M17, Agent details →
        Advanced): its extra flags and environment variables, whether its
        conversation is resumed, and its hung-turn limit. True when the
        flags or the environment changed: both are read when its process
        starts -- and checked again there, at launch (launch_extras) -- so
        the caller lets the idle process go, as for the tool switches; the
        conversation is kept. The limit is read by each turn's watchdog and
        resume by answer(), so neither needs a new process.

        The environment is read from its 0600 file outside any settings
        guard, because a file changes with no setting change; only when the
        file did (launch_extras caches by its stat). Logged as counts, never
        a name or a value."""
        launch = self.launch_for(p)
        fid = "main" if p is None or getattr(p, "main", False) else (getattr(p, "id", "") or "")
        who = getattr(p, "label", "") or getattr(p, "name", "") or "main"
        moved = False
        want_args = tuple(launch.get("args") or ())
        if tuple(getattr(agent, "extra_args", ()) or ()) != want_args:
            agent.extra_args, moved = want_args, True
        env, problem = ({}, "")
        if fid:
            try:
                env, problem = launch_extras.env_for(fid)
            except Exception as e:          # never worth a turn; nothing passed
                env, problem = {}, type(e).__name__
        key = f"env-{fid}"
        if problem:
            self.say_once(key, f"  {YEL}environment variables for “{who}”: not used — "
                               f"{launch_extras.env_path()} {problem}{OFF}")
        else:
            getattr(self, "_said", {}).pop(key, None)
        if (getattr(agent, "extra_env", None) or {}) != env:
            agent.extra_env, moved = dict(env), True
        agent.resume = bool(launch.get("resume", True))
        if not hasattr(agent, "base_url"):
            # An endpoint keeps its own timeout (endpointTimeoutS, Agents page).
            agent.idle_timeout_s = float(launch.get("idle_s") or 90)
        if moved:
            n, m = len(want_args), len(env)
            print(f"  {DIM}launch for “{who}”: {n} extra flag{'s' if n != 1 else ''} · "
                  f"{m} environment variable{'s' if m != 1 else ''}{OFF}", flush=True)
        return moved

    def reconcile_voice(self) -> None:
        """Load the voice the settings ask for, if that is not what is loaded.

        Called between turns rather than mid-sentence, because a voice swap
        means loading a different model. Cheap when nothing has changed: every
        branch below is a comparison.
        """
        if self._main.busy:
            return                      # not mid-reply; next poll
        if not self.cfg.get_bool("speakReplies"):
            self.speaker = None
            return
        wanted = self.cfg.get_str("voice")
        speed = speed_pct(self.cfg["voiceSpeed"])
        if (self.speaker is not None
                and self.speaker.requested == wanted
                and not self.speaker.superseded()):
            # After the spec check: a speed is a number, not a new model.
            if getattr(self.speaker, "speed", 100) != speed:
                self.speaker.speed = speed
                self.say_once("speed", f"  {CYA}voice speed: {speed}%{OFF}")
            return
        try:
            self.speaker = Speaker(wanted)
            self.speaker.speed = speed
        except Exception as e:
            # Reported once, not every two seconds: no voice on disk at all
            # is a standing condition, and it used to reprint the whole
            # banner with it on every idle poll.
            self.say_once("voice", f"  {YEL}voice {wanted} unavailable: {e}{OFF}")
            return
        if self.speaker.substituted_for:
            self.say_once("voice",
                          f"  {YEL}the voice {self.speaker.substituted_for} is not "
                          f"downloaded; speaking as {self.speaker.name}{OFF}")
        else:
            self.say_once("voice", f"  {CYA}voice: {self.speaker.name}{OFF}")
        self.banner()

    def deafen(self, tail_ms: int) -> None:
        """Drop everything the microphone captured while we were speaking.

        The run loop is synchronous, so frames pile up in the queue during
        playback. Processing them afterwards would feed our own voice to the
        wake word -- which is exactly how a speaking assistant wakes itself.
        """
        if (self._barged is not None or self._woke) and self.listening:
            # Not echo: the person talked over us and is still talking, or
            # said the wake word while the agent worked. What is in the queue
            # is the rest of what they are saying, and the run loop picks it
            # up from here. A lock or a mute makes `listening` false, and
            # then it is dropped like anything else.
            self._deaf_until = 0.0
            return
        self._deaf_until = time.time() + tail_ms / 1000.0
        if self._frames is None:
            return
        dropped = 0
        while True:
            try:
                self._frames.get_nowait()
                dropped += 1
            except Exception:
                break
        if dropped:
            print(f"  {DIM}(dropped {dropped * CHUNK_MS}ms of echo){OFF}")

    def _narration_event(self, narr: "narration.Narrator", chunk) -> None:
        """Tell the narrator what the agent just did."""
        now = time.time()
        if chunk.activity:
            a = chunk.activity
            act = narration.describe(a.get("name", ""), a.get("input"),
                                     detailed=narr.detailed,
                                     helper=bool(a.get("helper")))
            narr.activity(act, now, str(a.get("id") or ""))
        if chunk.tool_done:
            narr.finished(chunk.tool_done)
        if chunk.text:
            narr.text()

    def _floor_busy(self) -> bool:
        """Someone else is talking or about to: progress talk waits, never
        another agent's reply. Does not wait itself."""
        with self._floor:
            owner = self._floor_owner
            mine = self._persona()
            return bool(self._speaking or self._hold_speech or (
                owner is not None and owner is not mine and owner.busy
                and time.time() < self._floor_until))

    def _narrate(self, narr, last: dict, out, tail_ms: int, ticker) -> None:
        """Say a progress line if one is due. Lowest priority of anything
        said: never over a permission prompt, the answer or another agent,
        and cut short the moment the agent's own words arrive."""
        if (not self.speaker or not self.may_speak or self._interrupt.is_set()
                or self._floor_busy()):
            return
        line = narr.due(time.time())
        if line is None:
            return
        if speech_is_logged(self.cfg.get_bool("logSpeech")):
            print(f"  {DIM}(progress) {safe_for_terminal(line.text)}{OFF}", flush=True)
        else:
            print(f"  {DIM}(progress line){OFF}", flush=True)
        # The same line as text, where the reply will go. A copy: the turn's
        # record keeps only what the agent said.
        out.publish("thinking", **{**last, "reply": line.text[:REPLY_MAX]})
        self.speak(line.spoken, tail_ms,
                   cut=ticker.words_waiting if ticker is not None else None)
        narr.spoke(time.time())

    def speak(self, text: str, tail_ms: int, cut=None, on_start=None) -> None:
        """Say something, then make sure we did not hear ourselves say it.

        The watch is unconditional, which is the whole point of it. Barge-in
        used to be the only reason to look between audio chunks, so with
        `bargeIn` off -- the default, and measured: where the microphone sits
        beside the speaker every gate that hears the user also fires on our
        own output -- `Speaker.say()` was handed None and nothing could stop a
        sentence once it had started. Polling before the call, which is what
        the first version of this fix did, moved the exposure from the whole
        reply down to one sentence rather than closing it: a lock landing two
        words into "Later this week you have the house cleaners Monday
        morning, Band Night Wednesday at eight, ..." still read the rest of it
        out to a locked room. Reported against 98697f5 by a marketplace
        reviewer, who also pointed out that the no-agent echo path reaches
        here without passing the between-sentence poll at all -- which this
        covers, because the guard is now in the one place both paths go
        through.
        """
        if not self.speaker or self._interrupt.is_set():
            return
        # Before the first chunk rather than after it, and here rather than at
        # the call sites, because this function is what every path that makes
        # a noise goes through -- the reply loop, the echo path, and anything
        # added later that nobody remembers to guard. Cheap enough at this
        # point: nothing is playing yet, so a 9ms spawn cannot underrun
        # anything, and poll_session() rate limits itself to once a second.
        self.poll_session()
        if not self.may_speak:
            if self._in_turn() and self._persona().task is not None:
                # collab: a task keeps running behind a lock; this sentence
                # is not said, and waits with the rest of its reply.
                return
            self.silence()
            return
        if self._in_turn():
            # Beside the run loop: wait until nobody is talking to us and no
            # other agent is mid-reply. Taking the floor is what stops the
            # loop reading the microphone, so the watch below is built after.
            if not self._take_floor(self._persona()):
                return
        if not self._in_turn():
            with self._mic_lock:
                self._speaking = True
        began = time.time()
        try:
            barge = self._barge_watch()
            if self.chimes is not None:
                self.chimes.settle()    # never a chime under the first word
            with self._watching_session():
                self.speaker.say(speech_safe(text),
                                 watch=self._watch(barge, cut, on_start))
        finally:
            self.deafen(tail_ms)
            self.note_said(began, text)
            with self._mic_lock:
                self._speaking = False
                if self._in_turn():
                    # Kept for a moment for this reply's next sentence, so
                    # two replies never alternate sentence by sentence.
                    self._floor_until = time.time() + FLOOR_LEASE_S
                    self._floor.notify_all()

    def _take_floor(self, p: Persona) -> bool:
        """Wait for a turn to speak. False if `p` was stopped meanwhile."""
        with self._floor:
            while True:
                if p.interrupt.is_set() or not self.may_speak:
                    return False
                owner = self._floor_owner
                held = (owner is not None and owner is not p and owner.busy
                        and time.time() < self._floor_until)
                if not (held or self._speaking or self._hold_speech):
                    self._floor_owner = p
                    self._speaking = True
                    return True
                self._floor.wait(0.1)

    def _hold(self, hold: bool) -> None:
        """Hold every reply while somebody is talking to an agent."""
        with self._floor:
            if self._hold_speech != hold:
                self._hold_speech = hold
                self._floor.notify_all()

    def _watch(self, barge, cut=None, on_start=None):
        """What `Speaker.say()` checks between audio chunks.

        In-memory only. `reconcile_lock()` spawns
        `omarchy-hyprland-session-locked`, measured at 9.2ms median on this
        machine, and the playback loop writes chunks to PortAudio just in
        time -- so a check that cost that much would be heard as a stutter in
        every reply, which is a poor trade for noticing a lock 250ms sooner.
        The spawning happens on the thread `speak()` starts; this only reads
        the flags it sets.
        """
        started = on_start is None

        def watch() -> bool:
            nonlocal started
            if not started and getattr(self.speaker, "first_audio_at", None):
                # The first sound is out: now its words go on screen, so the
                # text never runs ahead of the voice.
                started = True
                try:
                    on_start()
                except Exception:
                    pass
            if self._interrupt.is_set() or not self.may_speak:
                return True
            # Progress talk gives way to the agent's own words, at the next
            # chunk of audio rather than at the end of the sentence.
            if cut is not None and cut():
                return True
            return bool(barge is not None and barge())

        return watch

    @contextlib.contextmanager
    def _watching_session(self):
        """Keep looking for a lock while the run loop cannot.

        The loop polls the session every two seconds and `answer()` blocks it
        for the whole turn: 31 seconds in this machine's journal, of which the
        first six were before a word was spoken. Speech was safe once the
        check between sentences existed -- nothing was read aloud -- but the
        *agent* went on working behind a locked screen for as long as the
        thinking phase lasted, running whatever tools the permission level
        allowed. `silence()` cancels the agent, so it is enough to notice.

        Reentrant by counting, because `speak()` wants this too: the no-agent
        echo path reaches the speaker without passing through the rest of
        `answer()`, and nesting must not start a second thread.
        """
        if self._in_turn():
            # The run loop is still running, and polls the lock itself.
            yield
            return
        self._watchers += 1
        if self._watchers == 1:
            self._watch_stop = threading.Event()
            self._watch_thread = threading.Thread(
                target=self._poll_session_until, args=(self._watch_stop,),
                daemon=True)
            self._watch_thread.start()
        try:
            yield
        finally:
            self._watchers -= 1
            if self._watchers == 0:
                self._watch_stop.set()
                self._watch_thread.join(timeout=2.0)
                self._watch_stop = self._watch_thread = None

    def _poll_session_until(self, stop: threading.Event) -> None:
        """Keep looking for a lock while the speaker owns the loop.

        `poll_session()` is rate limited to a second of its own accord, so
        this asks more often than that on purpose: the wait is what makes the
        thread stop promptly when the sentence ends, not the poll interval.
        """
        while not stop.wait(0.25):
            try:
                self.poll_session()
                # The microphone being lent out is reconciled here as well as
                # in the run loop, and for the same reason the lock is: the
                # loop is not running. Somebody who starts dictating into
                # another application while a reply is being read out is
                # exactly the case this setting exists for -- it was their
                # reason for asking for it -- and without this the reply
                # talked over them until it finished, then stepped aside.
                self.reconcile_yield()
            except Exception:
                # A reply that keeps playing is better than a daemon that
                # dies mid-sentence; the run loop polls both of these too.
                pass

    def reconcile_output(self, max_age: float = None) -> bool:
        """Whether the sound is going to a headset, asked at most every
        `max_age` seconds (OUTPUT_TTL_S unless told otherwise).

        Only asked when the answer matters: with `bargeIn` on it is not
        needed, and with `bargeOnHeadset` off nothing reads it.
        """
        if self.cfg.get_bool("bargeIn") or not self.cfg.get_bool("bargeOnHeadset"):
            return False
        now = time.time()
        if now - self._output_at > (OUTPUT_TTL_S if max_age is None else max_age):
            self._output_at = now
            self._output = headset.default_output()
            # Said when it changes, not on every poll: the journal then
            # records when the headset went on and came off, which is what
            # explains a reply that did or did not stop for somebody.
            if self._output is None:
                self.say_once("output", f"  {DIM}cannot tell where the sound "
                              f"is going (no pactl?), so it cannot be "
                              f"interrupted by voice{OFF}")
            elif self._output[0]:
                self.say_once("output", f"  {CYA}sound is going to "
                              f"{self._output[1]} — talk over it to "
                              f"interrupt{OFF}")
            else:
                self.say_once("output", f"  {DIM}sound is going to "
                              f"{self._output[1]} — not a headset, so it "
                              f"cannot be interrupted by voice{OFF}")
        return bool(self._output and self._output[0])

    def barge_wanted(self) -> bool:
        """Whether to listen for the person over this reply.

        Always, with `bargeIn`: that is somebody who ran `agentvoice
        calibrate` and was told their room can take it. Otherwise only when
        the sound is going to a headset and `bargeOnHeadset` is on, which it
        is by default -- there our own voice never reaches the microphone,
        so the reason barge-in is off everywhere else does not apply.

        The headset answer comes from the idle poll. This only asks again
        when that answer is old enough to have missed a whole conversation
        of follow-ups, which do not pass through the idle poll.
        """
        if self.cfg.get_bool("bargeIn"):
            return True
        return self.reconcile_output(max_age=OUTPUT_STALE_S)

    def _barge_watch(self):
        """A callable Speaker checks between chunks, or None when off.

        Off by default through speakers and for a measured reason: where the
        microphone sits beside the speaker, every gate that hears the user
        also fires on our own output, because the two arrive at the same
        level. `agentvoice calibrate` says which kind of room this is. On a
        headset it is on unless `bargeOnHeadset` is turned off.
        """
        if self._frames is None or not self.barge_wanted():
            return None
        if self._barge is None:
            try:
                from barge import BargeIn
                self._barge = BargeIn(factor=self.cfg.get_int("bargeFactor") / 100.0)
            except Exception as e:
                # Said once: on by default now, and an install without
                # openWakeWord (which carries the VAD) would otherwise say
                # this before every sentence of every reply.
                self.say_once("barge", f"  {YEL}barge-in unavailable: {e}{OFF}")
                return None
        self._barge.factor = self.cfg.get_int("bargeFactor") / 100.0
        self._barge.reset()
        # The last few frames the detector was fed. When it fires, these hold
        # the start of what the person said: it needs about 100ms of speech
        # to be sure, the frames are 200ms long, and the first word is the
        # one that tells the agent what they meant.
        recent: collections.deque[bytes] = collections.deque(
            maxlen=BARGE_PREROLL_FRAMES)
        who = self._persona()

        def watch() -> bool:
            # Drain whatever the microphone captured while that chunk played.
            while True:
                try:
                    pcm = self._frames.get_nowait()
                except Exception:
                    return False
                recent.append(pcm)
                if self._barge.feed(pcm):
                    print(f"  {YEL}heard you over us — stopping{OFF}")
                    self._barged = list(recent)
                    self._barged_by = who
                    self._interrupt.set()
                    if self.agent:
                        self.agent.cancel()
                    return True

        return watch

    def take_barge(self) -> list[bytes] | None:
        """What the person said over the reply, once; None if they did not.

        Only while listening: a lock or a mute between the barge and the run
        loop getting here means it is discarded, not carried into a capture.
        """
        barged, self._barged = self._barged, None
        return barged if self.listening else None

    def take_wake(self) -> bool:
        """Whether the wake word stopped the turn, once. Only while
        listening, for the same reason as take_barge()."""
        woke, self._woke = self._woke, False
        return woke and self.listening

    @contextlib.contextmanager
    def _hearing_wake(self):
        """Listen for the wake word while the agent works.

        Reported from use: talking during the thinking phase did nothing
        until the reply started, and then stopped it. Nothing read the
        microphone while the agent worked, so what was said waited in the
        queue, and the first thing that did read it was the barge watch
        inside the first sentence. Talking while it works is not taken as an
        interrupt -- asked for that way -- but the wake word is, and it is
        listened for while nothing is being said, on speakers as well as a
        headset: there is no playback for it to hear itself in.
        """
        if self._frames is None or self._in_turn():
            # Beside the run loop, the loop is what hears the wake word: it
            # never stopped listening. A second reader would split the frames.
            yield
            return
        stop = threading.Event()
        thread = threading.Thread(target=self._wake_watch_until, args=(stop,),
                                  daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop.set()
            # Before the run loop reads the queue again: two readers would
            # each get half of what was said next.
            thread.join(timeout=2.0)

    def _wake_watch_until(self, stop: threading.Event) -> None:
        while not stop.is_set():
            pcm = None
            with self._mic_lock:
                # Not while speaking (our own voice, and barge-in's), not
                # after a stop (what follows belongs to the run loop), and
                # not while locked or muted (the run loop discards those).
                if (not self._speaking and not self._interrupt.is_set()
                        and self.listening):
                    try:
                        pcm = self._frames.get_nowait()
                    except queue.Empty:
                        pass
            if pcm is None:
                stop.wait(0.05)
                continue
            # The tail of a sentence just spoken: reverb, and the buffer.
            if time.time() < self._deaf_until:
                continue
            try:
                fired = self.pipe.feed_wake(pcm, frame_db(pcm))
            except Exception as e:
                self.say_once("wake-watch", f"  {YEL}wake word unavailable "
                              f"while working: {type(e).__name__}: {e}{OFF}")
                return
            if fired and self.heard_full_stop():
                # Stop the turn and open nothing after it.
                print(f"  {YEL}● full stop{OFF}  {DIM}(heard as a keyword){OFF}",
                      flush=True)
                self._interrupt.set()
                for part in (self.speaker, self.agent):
                    if part is not None:
                        part.cancel()
                self.full_stop()
                return
            if fired:
                print(f"  {GRN}● wake{OFF}  {DIM}stopping — go ahead{OFF}",
                      flush=True)
                self._woke = True
                self._interrupt.set()
                if self.agent:
                    self.agent.cancel()
                return

    # --- turns cut at the longest-turn limit (phase M2, bug C) ---------------

    def limit_field(self) -> dict:
        """`limit_hits` for the state file: today's count and the last time,
        or a zero count once the day it was counted on is over."""
        hits = getattr(self, "limit_hits", None) or {}
        if hits.get("date") != _today():
            return {"date": _today(), "today": 0, "last": hits.get("last", 0)}
        return dict(hits)

    def limit_hits_rolled(self) -> bool:
        """Start a new day's count at midnight. True if it did."""
        hits = getattr(self, "limit_hits", None)
        if not hits or hits.get("date") == _today():
            return False
        self.limit_hits = self.limit_field()
        return True

    def count_limit_hit(self) -> None:
        """A turn was cut at maxUtteranceMs: count it where the Conversation
        page can see it. Reported from use: turns were cut at 30 seconds with
        nothing on screen to say so, and the only trace was a journal line."""
        self.limit_hits_rolled()
        hits = self.limit_field()
        hits["today"] += 1
        hits["last"] = round(time.time())
        self.limit_hits = hits
        print(f"  {YEL}cut at the longest-turn limit "
              f"({self.pipe.max_utterance_ms / 1000:.0f}s; "
              f"{hits['today']} today){OFF}", flush=True)
        self.publish_agent()

    def chime(self, name: str, why: str = "") -> None:
        """Play one of the short sounds, if they are on and we are listening.

        Never blocks: the sound plays from PortAudio's own thread. For its
        length the microphone keeps recording but nothing it hears counts as
        speech (`_chime_until`), so our own chime is not taken for the person
        starting to talk -- which on `wake` would end the lead-in's wait for
        nobody. It is not made deaf: that dropped the frame after the wake
        word whole, and with it the first word of anyone who did not pause.

        `why` goes in a journal line beside the sound's name whenever one
        plays (phase M2, bug J): "a random be-deep" could not be traced from
        the journal, which said what the loop did and never what it played.
        A reason is a fixed phrase and an agent's name, never anything said.
        """
        if (self.chimes is None or not self.cfg.get_bool("chimes")
                or not self.listening):
            return
        try:
            length = self.chimes.play(name)
        except Exception as e:
            # A missing output device must not cost the turn. Said once: it
            # is a standing condition, and this runs on every wake.
            self.say_once("chimes", f"  {YEL}cannot play sounds: "
                                    f"{type(e).__name__}: {e}{OFF}")
            return
        print(f"  {DIM}chime: {name}{f' ({why})' if why else ''}{OFF}", flush=True)
        self._chime_until = max(self._chime_until,
                                time.time() + length + CHIME_TAIL_S)

    def listening_for(self, p: Persona) -> str:
        """Why the microphone is already listening for `p` without its name,
        or "" when it is not (phase M2, bug J).

        The wake chime means "listening now; go ahead". Said while the open
        microphone is already listening for that agent -- its name heard
        while it works, in the stretch between its turns -- it announces
        nothing and reads as the machine starting over: the "random be-deep"
        of 2026-11-19 and 11-21, whose wakes in open mic all stopped the agent
        mid-turn. So that re-arm is silent; a wake for anyone else, or with
        no open microphone, still chimes."""
        if p is None or not self.listening:
            return ""
        if self.open_mic is p:
            return "open mic"
        return ""

    def voiced(self, level_db: float) -> bool:
        """Whether a frame this loud counts as the person speaking.

        Louder than the gate, and not while one of our own chimes may be what
        the microphone is hearing -- see chime().
        """
        return (level_db >= self.pipe.threshold_db
                and time.time() >= self._chime_until)

    def prime_agent(self) -> None:
        """Let the agent get ready while the person is still talking.

        Called the moment a capture opens. For Claude Code that starts the
        process the turn will be written to, which takes about a second --
        hidden entirely behind a sentence that takes several to say.
        """
        prepare = getattr(self.agent, "prepare", None)
        if prepare is None or self._persona().terminal:
            # Not while a terminal has the chat: a process started now
            # would hold it without what is typed there.
            return
        try:
            prepare(self.session_id)
        except Exception as e:
            # Never fatal and never silent. The turn itself will try again,
            # and can say why out loud if it still cannot.
            self.say_once("prime", f"  {YEL}could not start "
                                   f"{getattr(self.agent, 'name', 'the agent')}"
                                   f" early: {type(e).__name__}{OFF}")

    def hear(self, cap, utt, pcm: bytes, voiced: bool) -> str:
        """One capture frame to Vosk and to the utterance; the text to show.

        Vosk first, then the utterance, as the loop always did. With live text
        "accurate", a pause that sends a piece to Whisper also flushes Vosk,
        so the rough text is cut where Whisper's will start (eager.LiveText),
        and what is shown is Whisper's text so far plus Vosk's after it.
        Otherwise it is Vosk's partial, as before. "" means nothing new.
        """
        live = getattr(utt, "live", None)
        partial = ""
        if live is not None:
            live.heard(voiced)
        if cap is not None:
            if cap.AcceptWaveform(pcm):
                if live is not None:
                    live.final(json.loads(cap.Result()).get("text", ""))
            else:
                partial = json.loads(cap.PartialResult()).get("partial", "")
                if live is not None:
                    live.partial = partial
        cut = utt.add(pcm, voiced)
        if live is None or not getattr(self.pipe, "accurate_partials", False):
            return partial
        if cut and cap is not None:
            live.cut(utt.size, json.loads(cap.FinalResult()).get("text", ""))
        return live.render(*utt.whisper_so_far())

    def turn_ended(self, quiet_ms: float, utt) -> bool:
        """Whether this much quiet means you have finished.

        The full pause always does. A shorter one does when what you said is
        already transcribed and reads as finished -- see eager.sounds_finished,
        which is deliberately narrow, because being cut off is worse than
        waiting. The quiet is still required: a transcript that looks complete
        after 400ms is a person drawing breath as often as one who is done.
        """
        if quiet_ms > self.pipe.trailing_ms:
            return True
        quick = getattr(self.pipe, "quick_end_ms", 0)
        if not quick or quiet_ms < quick or utt is None:
            return False
        so_far = utt.tail()
        return so_far is not None and sounds_finished(so_far)

    def report_latency(self, clock: dict, last: dict) -> None:
        """One line per turn: from the moment you stopped talking to the
        moment it started answering, and where that time went.

        The number that decides how this feels, and the one nothing measured.
        "first token" below it is the model's own figure, counted from when
        the request left -- it leaves out the pause, Whisper, and starting the
        agent, which together were most of the wait. Structural, never gated:
        it holds timings and the agent's name, and nothing anybody said.
        """
        end = clock.get("voice_end")
        reached = clock.get("first_audio") or clock.get("first_sentence")
        if not end or not reached:
            return
        name = getattr(self.agent, "name", "") or "agent"
        start = getattr(self.agent, "last_start", "")
        spans = []
        for label, a, b in (("pause", "voice_end", "endpoint"),
                            ("whisper", "endpoint", "transcribed"),
                            (f"{name}{' ' + start if start else ''}",
                             "sent", "first_text"),
                            ("first sentence", "first_text", "first_sentence"),
                            ("voice", "first_sentence", "first_audio")):
            if a in clock and b in clock:
                spans.append(f"{label} {clock[b] - clock[a]:.1f}s")
        if clock.get("gaps"):
            # Not part of the wait to the first word, so outside the total:
            # silence between sentences after speaking began.
            spans.append(f"between sentences {clock['gaps']:.1f}s")
        verb = "spoke" if "first_audio" in clock else "showed"
        total = reached - end
        print(f"  {DIM}heard → {verb} in {total:.1f}s  "
              f"({' · '.join(spans)}){OFF}")
        last["latency_ms"] = round(total * 1000)

    def answer(self, text: str, last: dict, clock: dict | None = None,
               command=None) -> None:
        """Hand the transcript to the agent and speak the reply as it lands.

        Speech starts on the first complete sentence rather than the whole
        reply, because the agent's own generation is the slowest thing in the
        loop -- time-to-first-token is measured in seconds, and transcription
        is now mostly finished by the time you are.

        `clock` carries the turn's timestamps from the frame loop -- when you
        stopped talking, when the endpoint fired, when Whisper finished -- and
        this adds the agent's and the voice's, for report_latency().

        `command`: a command found inside what was said (phase M4,
        `sentence_command`), and `text` what was left of it. Nothing in
        `text` is then taken as a command: it is the request.
        """
        clock = dict(clock or {})
        tail_ms = self.cfg.get_int("echoTailMs")
        # Where this turn's state goes: the state file, or -- beside the run
        # loop -- this agent's own line, which the daemon combines with the
        # others' and the microphone's.
        out = self._out()
        self._interrupt.clear()
        if not self._in_turn():
            # Beside the loop these belong to it: it may be about to act on a
            # barge that happened during another agent's reply.
            self._barged = None
            self._woke = False
        if not self.agent:
            if self.speaker and text:
                out.publish("speaking", **last)
                self.speak(text, tail_ms)       # echo mode
            return

        if command is not None:
            if command.command.id in _IN_TURN_COMMANDS and \
                    not self.chat_in_sentence(command, last, out, tail_ms):
                return
            if not text:
                return
        elif self.chat_turn(text, last, out, tail_ms):
            return
        persona = self._persona()
        open_turn = persona.open_turn and self.cfg.get_bool("openMicAddressedOnly")
        persona.open_turn = False
        if self.terminal_holds(persona):
            line = ("That chat is open in a terminal. Say new chat to start "
                    "another one, or close the terminal first.")
            last["reply"] = line
            out.publish("speaking", **last)
            self.speak(line, tail_ms)
            return

        out.publish("thinking", **last)
        if not getattr(self.agent, "resume", True) and self.session_id:
            # Phase M17: resume is off for this agent, so every turn starts
            # fresh (one that set a session since -- a skipped open-mic
            # turn, a task -- is not carried either).
            self.session_id = None
        # collab: this turn, by number, and that it is under way: a call an
        # agent makes is accepted only from the turn it was made in (Phase 16).
        persona.turn_id = getattr(persona, "turn_id", 0) + 1
        persona.answering = True
        # Whether this turn's exchange goes into a new chat (save_chat's own
        # rule), so a task asked for now is not bound to an older one.
        persona.turn_new_chat = not self.session_id and not persona.chat_continued
        t0 = time.time()
        clock["sent"] = t0
        # A turn sent without a session starts a conversation. The view draws
        # a line there, because "what did I ask it earlier" is usually about
        # this conversation, not the one before.
        new_conversation = not self.session_id
        # A continued chat its backend cannot resume: the chat goes ahead of
        # this one request, then the session it starts carries it.
        prompt = persona.replay + text if persona.replay else text
        # collab: messages other agents left it, and the results of tasks it
        # delegated, ahead of everything else, as information (Phase 16).
        # A replay or a task block says whose words follow it; with neither,
        # the request is the user's and is headed so.
        try:
            waiting = self.collab.deliveries(persona)
            if waiting:
                prompt = waiting + (prompt if persona.replay
                                    else "The user now says:\n" + prompt)
        except Exception as e:
            print(f"  {YEL}deliveries not read: {type(e).__name__}{OFF}", flush=True)
        if open_turn:
            prompt = OPEN_MIC_PREAMBLE + prompt
        persona.replay = ""
        reply_parts: list[str] = []
        thinking_parts: list[str] = []
        unsaid: list[str] = []
        ttft = None
        error = None
        kind = ""
        skipped = False
        tools_seen: list[str] = []
        # Progress talk, when this agent has it on. The stream is then read
        # on a thread of its own so a quiet stretch -- a long command -- still
        # gives this one moments to speak in; with it off nothing changes.
        level = self.cfg.narration(persona.spec)
        narr = ticker = None
        if level != "off" and self.speaker:
            narr = narration.Narrator(level, start=t0,
                                      silence_s=self.cfg.narration_silence_s())
        # A browser question is said out loud (plan 12d). The agent's stream
        # is silent while the hook waits for an answer, so the same quiet
        # ticks progress talk uses are where it is said, on this turn's own
        # thread and floor.
        announcing = bool(self.speaker and getattr(self.agent, "browser_tools", False))

        def tap(stream):
            nonlocal ttft, error
            for chunk in stream:
                if chunk is TICK and announcing:
                    self.announce_permission(persona, tail_ms)
                if narr is None and chunk is TICK:
                    continue
                if narr is not None:
                    self._narration_event(narr, chunk)
                    if chunk is TICK or chunk.activity or chunk.tool_done:
                        self._narrate(narr, last, out, tail_ms, ticker)
                    if chunk is TICK:
                        continue
                if chunk.text and "first_text" not in clock:
                    clock["first_text"] = time.time()
                if chunk.session_id:
                    self.session_id = chunk.session_id
                if chunk.ttft_ms is not None and ttft is None:
                    ttft = chunk.ttft_ms
                if chunk.tool:
                    print(f"  {DIM}[{chunk.tool}]{OFF}", flush=True)
                    tools_seen.append(chunk.tool)       # phase M16: the ring
                if chunk.error:
                    error = chunk.error
                if chunk.thinking:
                    # Kept for the conversation view, greyed; never spoken,
                    # and never part of the reply the panel or a chat holds.
                    thinking_parts.append(chunk.thinking)
                yield chunk

        # Rendering ahead: each sentence goes to Piper as soon as the agent
        # has finished writing it, while the one before is still playing.
        speaker = self.speaker if self.may_speak else None
        prefetch = getattr(speaker, "prefetch", None)
        if speaker is not None and hasattr(speaker, "forget"):
            speaker.forget()

        def ahead(sentence: str, first: bool) -> None:
            prefetch(speech_safe(sentence), first=first)

        holding = getattr(speaker, "holding", None)
        gaps = 0.0
        said_until = None
        try:
            with self._watching_session(), self._hearing_wake(), \
                    (holding() if holding else contextlib.nullcontext()):
                stream = self.agent.send(prompt, self.session_id)
                if narr is not None or announcing or prefetch is not None:
                    ticker = Ticker(stream, on_abandon=getattr(self.agent, "cancel", None),
                                    on_sentence=ahead if prefetch is not None else None)
                    stream = ticker
                for sentence in sentences(tap(stream)):
                    # Checked before the sentence is recorded, so the transcript
                    # in the panel is what was actually said out loud rather than
                    # what the agent had written by the time it was stopped.
                    # One of three places that look, now. This one decides
                    # whether the *next* sentence is spoken at all; the watch
                    # inside Speaker.say stops the one already playing, and the
                    # thread this block runs under notices a lock during the
                    # agent's own turn, before any sentence exists.
                    self.poll_session()
                    if self._interrupt.is_set() or (not self.may_speak
                                                    and persona.task is None):
                        self.silence()
                        break
                    if open_turn and not reply_parts and \
                            sentence.strip().strip(".!").upper() == OPEN_MIC_SKIP:
                        # Not meant for it: nothing said, nothing kept.
                        skipped = True
                        break
                    clock.setdefault("first_sentence", time.time())
                    if speech_is_logged(self.cfg.get_bool("logSpeech")):
                        print(f"  {CYA}{safe_for_terminal(sentence)}{OFF}", flush=True)
                    reply_parts.append(sentence)
                    # Published per sentence rather than once at the end. The answer
                    # used to reach the state file only after the last word was
                    # spoken, which is the moment the readout starts counting down
                    # to close -- so it was on screen for the linger and nothing
                    # more. And published when the sentence's first sound goes
                    # out, not before: put up first, the text sat on screen for
                    # as long as Piper took to render it, one to three seconds
                    # with a high voice, and read as the voice lagging behind.
                    last["reply"] = " ".join(reply_parts)[:REPLY_MAX]
                    if self.speaker and self.listening:
                        shown = []

                        def show():
                            shown.append(True)
                            out.publish("speaking", **last)

                        self.speak(sentence, tail_ms, on_start=show)
                        if not shown and not self._interrupt.is_set():
                            out.publish("speaking", **last)
                        if narr is not None:
                            narr.agent_said(sentence, time.time())
                        # When the first sound actually went out, which the
                        # speaker records itself. Only one from this turn
                        # counts: a sentence that was never said leaves the
                        # last turn's value behind.
                        heard_at = getattr(self.speaker, "first_audio_at", None)
                        if (heard_at and heard_at >= t0
                                and "first_audio" not in clock):
                            clock["first_audio"] = heard_at
                        # Silence between sentences, once speaking has begun:
                        # rendering that fell behind, or the agent still
                        # writing.
                        if heard_at and said_until and heard_at > said_until:
                            gaps += heard_at - said_until
                        said_until = time.time()
                    else:
                        # No voice: the text is the entire answer, so it matters
                        # more here, not less. Keep whatever state we are in.
                        out.publish(out.current, **last)
                        if persona.task is not None and not self.may_speak:
                            unsaid.append(sentence)     # collab: said after the unlock
        except Exception as e:                  # a broken agent must not end the loop
            error = f"{type(e).__name__}: {e}"
        finally:
            persona.answering = False           # collab: no calls after this

        if skipped:
            # The open microphone heard something not meant for it. Silence
            # and no record: it was never a turn.
            print(f"  {DIM}(open mic: not meant for it){OFF}", flush=True)
            out.publish("listening", **_empty_turn())
            return

        if self._interrupt.is_set():
            # Killing the agent mid-stream usually surfaces as an error. It is
            # not one, and announcing it would talk over the user who just
            # asked for silence. Beside the run loop speak() has already
            # dropped its own echo, and anything queued since is somebody
            # talking to another agent.
            if not self._in_turn():
                self.deafen(tail_ms)
        elif error:
            # The fact of the error is always logged; its text is speech-
            # adjacent, because a CLI that rejects a prompt often quotes it
            # back. Found by the syntax-tree audit after I had decided by
            # hand that this one was fine.
            #
            # Its *kind* is not: failure.classify() returns a name from a
            # fixed list and never any of the text, so it is logged and said
            # whatever logSpeech is. "agent error (text withheld)" five times
            # in a row left nothing to act on.
            kind = failure.classify(error)
            if speech_is_logged(self.cfg.get_bool("logSpeech")):
                print(f"  {YEL}agent error ({kind}): "
                      f"{safe_for_terminal(error)}{OFF}")
            else:
                print(f"  {YEL}agent error: {kind}  {DIM}(details withheld — "
                      f"logSpeech is off){OFF}")
            if failure.forgets_conversation(kind) and self.session_id:
                # Resuming it would fail the same way on every turn after
                # this one. The process holding it goes with it: prepare()
                # sees a different conversation and starts a fresh one.
                self.session_id = None
                print(f"  {YEL}conversation dropped — the next turn starts "
                      f"a new one{OFF}")
                self.agent_ring.add(persona.id or "main", "dropped", error=kind)
            explained = failure.spoken(kind, getattr(self.agent, "name", ""),
                                       error)
            if not reply_parts:
                # On the panel too, where the reply would have been: a turn
                # that failed silently on screen reads as one still running.
                reply_parts.append(explained)
            # Inside a try of its own: this is the apology for a turn that
            # already went wrong, and the speaker is one of the things that
            # can be wrong. A PortAudio failure here was caught above as an
            # agent error and then re-raised out of this line, which is
            # outside the handler -- so a bad audio device ended the daemon.
            try:
                self.speak(explained, tail_ms)
            except Exception as e:
                print(f"  {YEL}and could not say so: "
                      f"{type(e).__name__}: {e}{OFF}")
        elif time.time() - t0 >= LONG_TURN_S:
            # Long enough that you may have stopped listening for it: most
            # long turns are tools running with nothing being said. The
            # spoken summary is the answer; this is the bell that says it
            # is over and the floor is yours.
            self.chime("done", f"a {time.time() - t0:.0f}s turn ended")

        reply = " ".join(reply_parts)
        last["reply"] = reply[:REPLY_MAX]
        if unsaid and not self._interrupt.is_set():
            # collab: a task finished behind a lock; what it did not get to
            # say waits, and only that.
            self.collab.hold(persona, " ".join(unsaid))
        print(f"  {DIM}agent {time.time() - t0:.1f}s"
              f"{f', first token {ttft:.0f}ms' if ttft else ''}{OFF}")
        # phase M16: one structural line in this agent's ring (runinfo.Ring
        # types every field: no text can reach it), and the turn counted in
        # its conversation.
        try:
            stopped = self._interrupt.is_set()
            secs = time.time() - t0
            start = getattr(self.agent, "last_start", "")
            in_task = persona.task is not None
            self.agent_ring.add(persona.id or "main", "turn", secs=secs, first_ms=ttft,
                                start=start, tools=tools_seen, error=kind, stopped=stopped,
                                task=in_task)
            self.agent_ring.count_turn(persona.id or "main", self.session_id)
        except Exception:               # noqa: BLE001 -- a page is never worth a turn
            pass
        # A stopped turn still counts if it got as far as making a sound --
        # that wait was real. One stopped before it spoke has nothing to say.
        if gaps:
            clock["gaps"] = gaps
        if "first_audio" in clock or not self._interrupt.is_set():
            self.report_latency(clock, last)
        self.remember(text, reply, last, kind=kind,
                      stopped=self._interrupt.is_set(), new=new_conversation,
                      thinking="".join(thinking_parts).strip()[:THINKING_MAX],
                      # Phase M18: when it was sent, so a save into chats
                      # deleted while it ran is refused (chats.record).
                      began=clock.get("sent"))
        if not getattr(self.agent, "resume", True) and self.session_id:
            # Phase M17: resume off. Nothing of this turn carries to the next
            # (the warm process holding it is let go by the next prepare(),
            # which asks for no session), and an "allow all in this chat"
            # given during it ends with it.
            sid, self.session_id = self.session_id, None
            try:
                import permission_hook
                permission_hook.revoke(sid)
            except Exception:
                pass

    def remember(self, heard: str, reply: str, last: dict, *, kind: str,
                 stopped: bool, new: bool, thinking: str = "",
                 began: float | None = None) -> None:
        """Add the exchange to the session's conversation -- runtime.History.

        What was said aloud, not everything the agent wrote: a reply stopped
        halfway is kept as far as it got, and marked, so the record matches
        what you heard rather than what you were spared.

        Saved chats are their own switch: keeping this session's view is not
        a promise to keep anything on disk, and the reverse holds too.
        """
        p = self._persona()
        p.turn_error = kind
        # collab: a task turn records the user's request, not the transcript
        # and brief that were put ahead of it.
        heard = p.task_heard or heard
        self.save_chat(heard, reply, kind=kind, stopped=stopped, new=new,
                       thinking=thinking, began=began)
        if not self.cfg.get_bool("keepHistory"):
            return
        who = getattr(self.agent, "name", "") or ""
        agent_id = ""
        if self.crew_mode:
            p = self._persona()
            who, agent_id = p.label or who, p.id
        self.history.append({
            "at": round(time.time(), 1),
            "agent": who,
            "agent_id": agent_id,
            "transcript": heard,
            "reply": reply[:REPLY_MAX],
            "error": kind,
            "stopped": bool(stopped),
            "new": bool(new),
            "latency_ms": int(last.get("latency_ms") or 0),
            **({"thinking": thinking} if thinking else {}),
        })

    # --- saved chats -----------------------------------------------------------

    def save_chat(self, heard: str, reply: str, *, kind: str, stopped: bool,
                  new: bool, thinking: str = "", began: float | None = None) -> None:
        """Add the exchange to the agent's saved chat, when chats are saved.

        A turn that started a new session starts a new chat, unless Continue
        put it in one. Never costs the turn: a disk that will not take the
        write loses the record, not the reply."""
        p = self._persona()
        # collab: taken whether or not chats are saved, so nothing of a
        # question waits in memory past the turn that asked it.
        asides = self.collab.take_asides(p)
        if not self.cfg.get_bool("saveChats") or not heard:
            return
        chat_id = None if (new and not p.chat_continued) else p.chat_id
        try:
            p.chat_id = self.chats.record(
                chat_id=chat_id, agent_id=p.id,
                agent_label=p.label or getattr(self.agent, "name", "") or "Agent",
                backend=getattr(self.agent, "name", "") or "",
                session_id=self.session_id,
                project_dir=str(getattr(self.agent, "cwd", "") or ""),
                exchange={"transcript": heard, "reply": reply, "error": kind,
                          "stopped": stopped,
                          **({"thinking": thinking} if thinking else {}),
                          # collab: the first turn of a passed conversation.
                          **({"kind": "brief", "for": p.task.frm}
                             if p.task is not None else {})},
                began=began)
            p.chat_continued = False
            if p.chat_id is None:
                # Phase M18: deleted while this turn ran. Not saved, and its
                # asides go with it; the next turn starts a new chat.
                print(f"  {DIM}chat not saved: deleted while the turn ran{OFF}", flush=True)
                return
            # collab: a task this turn asked for before its chat existed.
            self.collab.chat_saved(p, p.chat_id)
            # collab: the questions it asked other agents this turn, each a
            # collapsed "Theo asked Sora" entry after its own (Phase 16).
            for aside in asides:
                self.chats.record(
                    chat_id=p.chat_id, agent_id=p.id,
                    agent_label=p.label or getattr(self.agent, "name", "") or "Agent",
                    backend=getattr(self.agent, "name", "") or "",
                    session_id=None,
                    project_dir=str(getattr(self.agent, "cwd", "") or ""),
                    exchange={"transcript": aside["question"], "reply": aside["answer"],
                              "kind": "aside", "asked": aside["asked"],
                              "asked_label": aside["asked_label"]})
            if p.chat_id != chat_id:
                retention = self.cfg.get_str("chatRetention")
                if retention in RETENTIONS:
                    self.chats.prune(retention)
        except (OSError, ValueError) as e:
            print(f"  {YEL}chat not saved: {type(e).__name__}{OFF}", flush=True)

    def continue_chat(self, p: Persona, chat: dict) -> str:
        """Make `chat` the one `p`'s next turn goes into. Returns how:
        "resumed" when its backend takes the session back natively, else
        "replayed", when the chat is put ahead of the next request."""
        agent = p.agent
        here = str(getattr(agent, "cwd", "") or "")
        # Phase M8: a quarantined agent carries on only its own chats. Its
        # shares were revoked and its sessions detached when it was
        # quarantined; this holds it for a share or a session that came back
        # by hand since, and for unreadable settings.
        if (chat_schema.owner_of(chat) != collab.external(p.id)
                and self.collab.is_quarantined(collab.external(p.id))):
            print(f"  {YEL}agent “{p.label or 'main'}” is quarantined: it carries on only "
                  f"its own chats{OFF}", flush=True)
            return "refused"
        # Its own session in the chat (Phase 15: each speaker has one); an
        # older chat's top-level session is its owner's.
        mine = chat_schema.sessions_of(chat).get(collab.external(p.id), {})
        if (agent is not None and getattr(agent, "remembers", False)
                # Phase M17: with resume off a session is never carried, so
                # the chat is replayed instead (where it may be).
                and getattr(agent, "resume", True)
                and mine.get("session_id")
                and mine.get("backend") == getattr(agent, "name", "")
                and mine.get("project_dir", "") == here):
            p.session_id, p.replay, how = mine["session_id"], "", "resumed"
        elif not chat_schema.may_replay(chat, collab.external(p.id)):
            # Phase 15: a session it once had there lets it resume natively;
            # it never lets it be given the whole transcript. Only the owner
            # and a share may be replayed it.
            print(f"  {YEL}{chat_schema.refusal(chat, collab.external(p.id))}{OFF}",
                  flush=True)
            return "refused"
        else:
            # A session is one backend's, in one folder: anything else gets
            # the words, which costs tokens and says so on screen.
            p.session_id, p.replay, how = None, replay_context(chat), "replayed"
        p.chat_id, p.chat_continued = chat["id"], True
        self.readout_for().forget(p.id or "")
        try:
            self.chats.set_current(p.id, chat["id"])
        except (OSError, ValueError):
            pass
        print(f"  {CYA}agent “{p.label or 'main'}”: continuing a saved chat "
              f"({how}){OFF}", flush=True)
        return how

    def new_chat(self, p: Persona) -> None:
        """Start `p` afresh: no session, no chat until its next turn."""
        p.session_id, p.chat_id, p.chat_continued, p.replay = None, None, False, ""
        p.terminal = None
        self.readout_for().forget(p.id or "")
        try:
            self.chats.set_current(p.id, None)
        except (OSError, ValueError):
            pass

    def continue_by_topic(self, p: Persona, about: str) -> tuple[str, bool]:
        """Find `p`'s saved chat about `about` and make it the current one.
        (what to say, whether it was continued)."""
        if not self.cfg.get_bool("saveChats"):
            return ("Saved chats are off. Turn on Save conversations in the "
                    "Display settings."), False
        try:
            found = self.chats.find(about, p.id)
        except (OSError, ValueError):
            found = []
        if not found:
            return ((f"I couldn't find a chat about {about}." if about
                     else "There's no saved chat to continue."), False)
        if len(found) > 1 and found[1]["score"] >= found[0]["score"] * 0.8:
            return (f"Two chats match: {found[0]['title']}, and "
                    f"{found[1]['title']}. Say a few more words about which one."), False
        chat = self.chats.load(found[0]["id"])
        if chat is None:
            return "That chat is gone.", False
        if self.continue_chat(p, chat) == "refused":
            return ("That chat isn't shared with me any more, so I can't "
                    "pick it up."), False
        return f"Continuing {chat_schema.display_title(chat) or 'that chat'}. Go ahead.", True

    def chat_turn(self, text: str, last: dict, out, tail_ms: int) -> bool:
        """ "new chat" and "continue the chat about ..." said to an agent.

        Handled here rather than sent: True when it was one of them, and
        the answer has been said. Continuing only searches this agent's own
        chats, because another backend's session is not one it can take
        up. Two close matches are named rather than guessed between."""
        kind, about = chat_command(text)
        if not kind:
            return False
        p = self._persona()
        if kind == "new":
            self.new_chat(p)
            msg = "Starting a new chat."
        else:
            msg, _ = self.continue_by_topic(p, about)
        print(f"  {DIM}({kind} chat){OFF}", flush=True)
        out.publish("speaking", **{**last, "reply": msg})
        if self.speaker:
            self.speak(msg, tail_ms)
        return True

    def apply_chat_command(self, cmd: str | None) -> bool:
        """`agentvoice chats continue ID` and `chats new [AGENT]`, from the
        conversation view. True if `cmd` was one of them."""
        if not cmd or not cmd.startswith(("chat-", "task-")):
            return False
        verb, _, arg = cmd.partition(" ")
        arg = arg.strip()
        if verb == "chat-continue":
            chat_id, _, who = arg.partition(" ")
            chat = self.chats.load(chat_id) if chat_id else None
            if chat is None:
                print(f"  {YEL}no such chat to continue{OFF}", flush=True)
                return True
            # By its owner, or (Phase 15) another agent it was shared or
            # passed to; anyone else is refused, with the reason.
            who = who.strip() or chat_schema.owner_of(chat)
            if not chat_schema.may_continue(chat, who):
                print(f"  {YEL}{chat_schema.refusal(chat, who)}{OFF}", flush=True)
                return True
            p = self._persona_by_id(collab.internal(who))
            if p is None:
                print(f"  {YEL}that chat's agent is not here any more{OFF}", flush=True)
            elif p.busy:
                print(f"  {YEL}agent “{p.label}” is working; continue it when it "
                      f"has finished{OFF}", flush=True)
            elif self.continue_chat(p, chat) != "refused":
                # phase M3: switched from the conversation view, so no turn
                # follows to replace the old chat's words on screen.
                self.forget_readout(p, clear=True)
                self._recompose()
            return True
        if verb == "task-cancel":
            # collab: Cancel on the Collaboration list, `agentvoice tasks cancel`.
            if not self.collab.cancel(arg):
                print(f"  {YEL}no open task {arg[:32]} to cancel{OFF}", flush=True)
            return True
        if verb == "chat-new":
            p = self._persona_by_id("" if arg in ("", "main") else arg)
            if p is None:
                # Not echoed: the id came from the command file.
                print(f"  {YEL}no such agent to start fresh{OFF}", flush=True)
            elif p.busy:
                # Said rather than dropped (phase M17, Start fresh): its turn
                # owns the session until it ends.
                print(f"  {YEL}agent “{p.label or 'main'}” is working; start it fresh "
                      f"when it has finished{OFF}", flush=True)
            else:
                old_sid = p.session_id
                self.new_chat(p)
                # Phase M17: only this agent's conversation ends. Its idle
                # process holds the old one and goes now rather than at the
                # next turn, and an "allow all in this chat" given in it
                # ends with it.
                if p.agent is not None:
                    try:
                        p.agent.cancel()
                    except Exception:
                        pass
                if old_sid:
                    try:
                        import permission_hook
                        permission_hook.revoke(old_sid)
                    except Exception:
                        pass
                try:
                    self.agent_ring.add(p.id or "main", "fresh")
                except Exception:       # noqa: BLE001 -- a page is never worth a command
                    pass
                self.forget_readout(p, clear=True)
                self._recompose()
                print(f"  {CYA}agent “{p.label or 'main'}”: new chat{OFF}", flush=True)
            return True
        return False

    # --- open microphone (plan item 11) -------------------------------------

    def open_mic_idle_s(self) -> float:
        return 60.0 * min(60, max(1, self.cfg.get_int("openMicIdleMin")))

    def open_mic_left_ms(self) -> int:
        return max(0, int((self.open_mic_until - time.time()) * 1000))

    def open_mic_field(self) -> dict:
        p = self.open_mic
        if p is None:
            return {}
        return {"who": p.label or "", "id": p.id or "main",
                "until": round(self.open_mic_until)}

    def start_open_mic(self, p: Persona, say: bool = True) -> None:
        """Listen without the wake word, for `p`, until told to stop or
        `openMicIdleMin` passes with nothing said."""
        fresh = self.open_mic is None
        if self.open_mic is not p:
            self._open_mic_gen = getattr(self, "_open_mic_gen", 0) + 1
        self.open_mic, self.open_mic_until = p, time.time() + self.open_mic_idle_s()
        if fresh:
            mins = round(self.open_mic_idle_s() / 60)
            print(f"  {CYA}● open mic{OFF}  {DIM}({p.label or 'main'}; "
                  f"{mins} min after the last thing said){OFF}", flush=True)
            self.publish_agent()
            if say:
                self._say_for(p, "I'm listening. Say stop listening when you're done.")

    def touch_open_mic(self) -> None:
        if self.open_mic is not None:
            self.open_mic_until = time.time() + self.open_mic_idle_s()

    def end_open_mic(self, why: str, say: bool = False) -> None:
        p = self.open_mic
        if p is None:
            return
        self._open_mic_gen = getattr(self, "_open_mic_gen", 0) + 1
        self.open_mic = None
        self.open_mic_until = 0.0
        print(f"  {CYA}● open mic closed{OFF}  {DIM}({why}){OFF}", flush=True)
        self.publish_agent()
        if say:
            self._say_for(p, "Okay. Say my name when you need me.")

    def pass_open_mic(self, p: Persona) -> None:
        """Somebody else was named on the open microphone: it is theirs now."""
        if self.open_mic is not None and self.open_mic is not p:
            self._open_mic_gen = getattr(self, "_open_mic_gen", 0) + 1
            self.open_mic = p
            self.touch_open_mic()
            print(f"  {CYA}● open mic{OFF}  {DIM}(now {p.label or 'main'}){OFF}",
                  flush=True)
            self.publish_agent()

    def apply_open_mic_command(self, cmd: str | None) -> bool:
        """`agentvoice open-mic on|off [AGENT]`, from the popup's toggle."""
        if not cmd or not cmd.startswith("open-mic"):
            return False
        # Phase M4: an explicit switch supersedes an undo still pending, even
        # one that changes nothing (Codex review of M4).
        self._undo = None
        parts = cmd.split()
        want = parts[1] if len(parts) > 1 else ""
        if want == "off":
            self.end_open_mic("turned off")
        elif want == "on" and self.listening:
            p = self._persona_by_id("" if len(parts) < 3 or parts[2] == "main"
                                    else parts[2])
            self.start_open_mic(p or self._last_target or self._main, say=False)
        return True

    def _say_for(self, p: Persona, line: str, beside: bool = False) -> bool:
        """Something short said in `p`'s voice, from the run loop. True when
        it was said to the end: not muted, locked, lent out, stopped or
        failing (collab needs to know a disclosure was heard).

        `beside`: from a thread beside the run loop -- a collaboration call
        p made mid-turn (Phase 16) -- so it takes the speaking floor as p's
        own turn would, and never talks over another agent's reply."""
        said = False
        was = getattr(self._here, "turn", False)
        with self._as(p):
            if beside:
                self._here.turn = True
            try:
                if self.speaker and self.listening:
                    try:
                        self.speak(line, self.cfg.get_int("echoTailMs"))
                        said = (self.may_speak and self.listening
                                and not self._interrupt.is_set())
                    except Exception as e:
                        print(f"  {YEL}could not say it: {type(e).__name__}{OFF}")
            finally:
                if beside:
                    self._here.turn = was
        return said

    def fresh_config(self) -> Config:
        """collab: the settings as on disk now, for a collaboration call's
        knobs, read fresh on every call (merged plan 3.4)."""
        return Config()

    def watched_config(self) -> Config:
        """collab: a Config of its own for the crew sweep on every poll (phase
        M8), re-read only when its files' stamps move -- two stat calls a
        poll. Not self.cfg: refresh() is skipped while the microphone is off,
        so that copy can go stale for as long as listening is (Codex review),
        and reloading self.cfg here would hide a change from refresh()."""
        c = getattr(self, "_watched_cfg", None)
        if c is None:
            c = self._watched_cfg = Config()
        else:
            c.reload()
        return c

    def adapter_stale(self, p: Persona, cfg) -> bool:
        """collab: whether `p`'s running adapter no longer matches what the
        settings now say about how it may act -- its permission level (hook
        or none) and its folder. A task or a question must not start on an
        adapter the idle poll has not yet rebuilt (Codex review: one lowered
        from Trusted to Ask while busy kept its unhooked process). True when
        the settings cannot be read."""
        if cfg is None:
            return True
        have = self.agent if p is self._main else p.agent
        if have is None or hasattr(have, "base_url"):
            return False                    # an endpoint runs nothing here
        if p is self._main:
            level = cfg.level_for(getattr(have, "name", "") or "")
            folder = cfg.get_str("projectDir")
            seen = getattr(self, "_main_level", None)
        else:
            spec = cfg.agent_by_id(p.id)
            if spec is None:
                return True
            level, folder = spec["level"], spec["projectDir"]
            seen = (p.spec or {}).get("level")
        # A level that moved without moving the hook (Ask and Edits) is still
        # a change the idle poll has not applied: its grants are withdrawn
        # there, so nothing may start on the old ones first (Codex review of
        # M2, which found collaboration calls starting turns in that gap).
        if seen is not None and level != seen:
            return True
        want_ask = level != "trusted"
        if getattr(have, "ask_permission", want_ask) != want_ask:
            return True
        cwd = getattr(have, "cwd", None)
        return bool(cwd) and str(cwd) != str(project_dir(folder))

    def side_adapter(self, p: Persona):
        """collab: a fresh adapter for `p`'s program, for a quiet side turn
        (Phase 16, `ask_agent`): text only, no spoken style, a new session,
        thrown away afterwards -- never p's own warm process or session. Its
        own level, folder, model, instructions, prompt parts and tools, so
        nothing about the answer is escalated. None when p has no agent."""
        have = self.agent if p is self._main else p.agent
        if have is None:
            return None
        program = getattr(have, "name", "") or None
        endpoint = None
        if hasattr(have, "base_url"):
            endpoint = (self.cfg.main_endpoint() if p is self._main
                        else (p.spec or {}).get("endpoint"))
            if not endpoint:
                return None
            endpoint = {**endpoint, "key": endpoint_key(_host(endpoint["url"]))}
            program = None
        side = load_adapter(name=program, endpoint=endpoint, spoken=False,
                            level=getattr(have, "level", None),
                            ask_permission=getattr(have, "ask_permission", True),
                            cwd=getattr(have, "cwd", None),
                            model=getattr(have, "model", None),
                            effort=getattr(have, "effort", None),
                            instructions=getattr(have, "instructions", ""),
                            named=getattr(have, "named", "") or "")
        if side is None:
            return None
        side.spoken = False
        # No session written to disk by the CLI: the question is not kept in
        # its own history (Claude --no-session-persistence, Codex --ephemeral).
        side.ephemeral = True
        side.parts = getattr(have, "parts", None)
        for attr in ("skill_text",):
            if hasattr(have, attr):
                setattr(side, attr, getattr(have, attr))
        try:
            self.apply_extras(side, p)
        except Exception:
            pass
        return side

    # --- spoken commands that are not requests -------------------------------

    def voice_command(self, p: Persona, text: str) -> bool:
        """"keep listening", "stop listening" and "move this to a terminal",
        said to `p`. True when `text` was one of them and has been dealt
        with; nothing then goes to the agent."""
        mic = open_mic_command(text)
        if mic == "open":
            self.start_open_mic(p)
            return True
        if mic == "close":
            if self.open_mic is not None:
                self.end_open_mic("asked to", say=True)
            return True
        if is_handoff(text):
            self.hand_off(p)
            return True
        # collab: "pass this to Sora", "Sora, take over" (Phase 15).
        if self.pass_command(p, text):
            return True
        return False

    def command_names(self) -> dict[str, str]:
        """Every name an agent may be called by, lower case, and the agent:
        display names and wake phrases, for "pass this to Sora"."""
        names = {}
        for agent, label in self.collab._known().items():
            names[" ".join(str(label).lower().split())] = agent
        for q in self.personas():
            for n in (q.label, q.name):
                if n:
                    names[" ".join(n.lower().split())] = collab.external(q.id)
        return names

    def pass_command(self, p: Persona, text: str) -> bool:
        """"pass this to Sora" said to `p`, or "take over" said to the agent
        that is to take it from whoever was spoken to last. True when it was
        one and has been dealt with."""
        names = self.command_names()
        name, request = pass_command(text, names)
        if name:
            self.collab.pass_conversation(p, names[name], entry="voice",
                                          request=request)
            return True
        if is_take_over(text):
            source = self._last_target if self._last_target is not None else self._main
            self.collab.pass_conversation(source, collab.external(p.id),
                                          entry="voice")
            return True
        return False

    # --- commands inside sentences (phase M4) ---------------------------------

    #: How long after something was said aloud a command in it may still be
    #: the agent's own voice coming back to the microphone: the room, and
    #: the deaf tail after each sentence.
    OWN_VOICE_S = 2.0

    def note_said(self, began: float, text: str) -> None:
        """Remember what was just said aloud, and when (`speak()`)."""
        said = getattr(self, "_said_lately", None)
        if said is not None:
            said.append((began, time.time(), str(text or "")))

    def recording_elsewhere(self) -> bool:
        """Whether another program is recording right now: somebody
        dictating, whose words are not commands. Asked at the moment a
        command would fire, not only at the 2s poll that lends the
        microphone out, because a sentence can finish inside that gap.
        Asked whatever `yieldToRecorders` says: that setting is about
        stepping aside, not about obeying what was dictated. "Cannot tell"
        (no pw-dump) is no, as it is for lending the microphone."""
        try:
            return bool(other_recorders(os.getpid()))
        except Exception:
            return False

    def locked_now(self) -> bool:
        """Whether the screen is locked, asked now: the 2s poll can be behind
        a lock that landed while Whisper ran (Codex review of M4). Not
        poll_session(), which would also take the CLI's command file -- a
        push-to-talk press meant for the loop -- and drop it. An answer
        nobody can give keeps the last one known, as the poll does."""
        try:
            self.reconcile_lock()
        except Exception:
            pass
        return self.locked

    def _command_refused(self, found, heard_at: float | None) -> str:
        """Why a command found inside a sentence must not fire, or "".
        Also asked of an undo, which switches the microphone too."""
        if self.locked_now():
            return "the screen is locked"
        if self.yielded:
            return "the microphone is lent out"
        if self.recording_elsewhere():
            return "something else is recording"
        if heard_at is not None:
            for began, ended, said in list(getattr(self, "_said_lately", ())):
                if ended >= heard_at - self.OWN_VOICE_S and heard_back(found.phrase, said):
                    return "its own voice"
        return ""

    def sentence_command(self, p: Persona, text: str, last: dict,
                         heard_at: float | None = None):
        """The one place a command said inside a longer sentence is acted on.

        Called with a finished transcript -- never a partial, never a typed
        message -- after the checks for a command said on its own, which
        handle those exactly as before M4. None when there is nothing for
        it to do: an ordinary request, a command said on its own, the mode
        "alone", or a context it must never fire in (locked, lent out,
        dictation, its own voice heard back).

        Otherwise the `speech_text.Found`. The open microphone has already
        been switched and the command's fixed sentence said once and shown;
        a chat command is left to the agent's turn (`answer`), where its
        chat is. Either way `found.rest`, if anything, is what goes to the
        agent, once, as an ordinary request. `heard_at` is when the person
        started speaking, for the own-voice check.
        """
        mode = self.cfg.commands_in_sentences()
        if mode == "alone" or not text:
            return None
        try:
            names = tuple(self.command_names())
        except Exception:
            names = ()
        found = find_command(text, mode, names)
        if found is None or found.exact:
            return None
        if (self.agent if p is self._main else p.agent) is None:
            # Nobody to send the rest to: the echo mode, or an agent that is
            # not set up. Everything goes on as before M4.
            return None
        cmd = found.command
        why = self._command_refused(found, heard_at)
        if why:
            print(f"  {DIM}command not taken: {cmd.id} ({mode}, "
                  f"{found.where}; {why}){OFF}", flush=True)
            return None
        # The structural line: which command and where, never the words.
        print(f"  {CYA}command: {cmd.id}{OFF}  {DIM}({mode}, {found.where}"
              f"{', with a request' if found.rest else ''}){OFF}", flush=True)
        if cmd.id in _IN_TURN_COMMANDS:
            return found
        before = self.open_mic
        if cmd.id == "open_mic":
            self.start_open_mic(p, say=False)
        else:
            if self.open_mic is not None:
                self.end_open_mic("asked to" if cmd.id == "close_mic" else "goodbye")
            if not found.rest:
                # The conversation was just ended: no window after it, not
                # one already armed nor one a turn still working would arm
                # when it ends (Codex review of M4).
                p.follow_up = False
                if p.busy:
                    p.ends_pending = True
        self.state.publish("speaking", **{**last, "reply": cmd.said})
        self._say_for(p, cmd.said)
        if cmd.id in ("open_mic", "close_mic") and self.open_mic is not before:
            # Open from the moment it was said; the clock starts when the
            # turn carrying the rest has finished, if one does (undo_clock).
            self._undo = {"command": cmd.id, "found": found, "before": before,
                          "after": self.open_mic, "persona": p, "at": time.time(),
                          "gen": self._open_mic_gen,
                          "until": None if found.rest else time.time() + UNDO_S}
        return found

    def undo_clock(self, found) -> None:
        """The turn that carried `found`'s request is over: the few seconds
        in which "no" undoes its open-mic switch start now."""
        undo = getattr(self, "_undo", None)
        if undo is not None and undo["found"] is found and undo["until"] is None:
            undo["until"] = time.time() + UNDO_S

    def undo_due(self) -> float:
        """Milliseconds left in which "no" can still put back an open mic
        closed from inside a sentence, else 0. Once it is closed nothing is
        listening without the wake word, so the run loop listens for these
        few seconds -- and takes nothing but an undo from them (Codex review
        of M4: "stop listening" could otherwise never be undone)."""
        undo = getattr(self, "_undo", None)
        if undo is None or undo["command"] != "close_mic" or not self.listening:
            return 0.0
        if self.cfg.commands_in_sentences() == "alone":
            return 0.0
        if self.open_mic is not None or self._speaking or undo["until"] is None:
            return 0.0
        if undo.get("gen") != getattr(self, "_open_mic_gen", 0):
            return 0.0
        return max(0.0, (undo["until"] - time.time()) * 1000)

    def take_undo(self, text: str, heard_at: float | None,
                  capture_for: Persona | None = None) -> bool:
        """"no" or "cancel that", said straight after an open-mic switch made
        from inside a sentence, puts it back and says so. Any finished
        transcript uses the chance up, undo or not.

        True when that was all there was to it. "cancel that" is also a
        stop, so it is undone and then goes on to stop what was asked."""
        undo, self._undo = getattr(self, "_undo", None), None
        if undo is None or not text or not self.listening or not is_undo(text):
            return False
        if capture_for is not None and capture_for is not undo["persona"]:
            return False                # said to another agent: theirs
        if self.cfg.commands_in_sentences() == "alone":
            return False                # switched to alone since: as before M4
        if undo.get("gen") != getattr(self, "_open_mic_gen", 0):
            return False                # switched again since, some other way
        until = undo["until"]
        if until is None and not undo["persona"].busy:
            # The turn that was to carry the rest never ran, or ended
            # without saying so: the window is the one after the command.
            until = undo["at"] + UNDO_S
        if heard_at is None or (until is not None and heard_at > until):
            return False
        # The same contexts as the command: not dictated, and not the
        # agent's own "no" coming back.
        why = self._command_refused(Found(command(undo["command"]), "alone",
                                          phrase=text), heard_at)
        if why:
            print(f"  {DIM}undo not taken: {undo['command']} ({why}){OFF}", flush=True)
            return False
        if undo["command"] == "open_mic":
            if self.open_mic is None or self.open_mic is not undo["after"]:
                return False
            self.end_open_mic("undone")
            line = command("close_mic").said
        else:
            back = undo["before"]
            if self.open_mic is not None or back is None or (
                    back is not self._main and self.crew.get(back.id) is not back):
                return False
            self.start_open_mic(back, say=False)
            line = command("open_mic").said
        print(f"  {CYA}command undone: {undo['command']}{OFF}", flush=True)
        self.state.publish("speaking", **{**_empty_turn(), "transcript": text,
                                          "reply": line})
        self._say_for(undo["persona"], line)
        return not is_stop_command(text)

    def chat_in_sentence(self, found, last: dict, out, tail_ms: int) -> bool:
        """A chat command found inside a sentence, in the agent's turn: start
        or continue the chat, say so once, and True if the rest of what was
        said should go on into it. A chat that cannot be continued says why
        and keeps the rest back: asked of the wrong chat, it would be
        answered from the wrong conversation."""
        p = self._persona()
        cmd = found.command
        if self.locked:
            return False                # locked since the hook passed it
        if cmd.id == "new_chat":
            self.new_chat(p)
            line, go_on = cmd.said, True
        else:
            line, go_on = self.continue_by_topic(p, found.arg)
            if go_on:
                line = cmd.said
        print(f"  {DIM}({cmd.id}){OFF}", flush=True)
        out.publish("speaking", **{**last, "reply": line})
        if self.speaker:
            self.speak(line, tail_ms)
        return go_on

    # --- moving a chat into a terminal (plan item 3) ---------------------------

    def hand_off(self, p: Persona) -> bool:
        """Carry `p`'s conversation on in a terminal, and stay out of it
        until that terminal is closed. True if a terminal was opened."""
        program = getattr(p.agent, "name", "") or ""
        label = p.label or "it"
        if p.agent is None:
            self._say_for(p, f"{label} isn't set up, so there is nothing to move.")
            return False
        if not p.session_id:
            self._say_for(p, "There's nothing to move yet. Ask me something first.")
            return False
        argv = terminal_resume_argv(program, p.session_id)
        if argv is None:
            self._say_for(p, f"{program_label(program) or program} can't carry a "
                             "chat into a terminal, so it stays here.")
            return False
        if p.busy:
            p.stop()
            if p.thread is not None:
                p.thread.join(timeout=5.0)
        # The process kept warm for the next turn holds the old context:
        # anything typed in the terminal would be missing from it.
        cancel = getattr(p.agent, "cancel", None)
        if cancel is not None:
            try:
                cancel()
            except Exception:
                pass
        folder = getattr(p.agent, "cwd", None) or str(Path.home())
        launcher = ["xdg-terminal-exec", f"--dir={folder}", *argv]
        if shutil.which("uwsm-app"):
            launcher = ["setsid", "uwsm-app", "--", *launcher]
        try:
            subprocess.Popen(launcher, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError as e:
            print(f"  {YEL}could not open a terminal: {type(e).__name__}{OFF}",
                  flush=True)
            self._say_for(p, "I couldn't open a terminal.")
            return False
        p.terminal = p.session_id
        if self.open_mic is p:
            self.end_open_mic("moved to a terminal")
        if p.chat_id:
            try:
                self.chats.mark_terminal(p.chat_id)
            except (OSError, ValueError):
                pass
        print(f"  {CYA}agent “{p.label or 'main'}”: moved to a terminal{OFF}",
              flush=True)
        self._say_for(p, "Moved to a terminal.")
        return True

    def terminal_holds(self, p: Persona) -> bool:
        """Whether `p`'s chat is still open in the terminal it was handed to.
        Once it is closed the chat is voice's again, with whatever was typed
        there: the next turn resumes it."""
        if not p.terminal:
            return False
        if p.terminal != p.session_id:
            p.terminal = None           # a new chat since: nothing to wait for
            return False
        if session_held_elsewhere(p.terminal):
            return True
        p.terminal = None
        print(f"  {CYA}agent “{p.label or 'main'}”: the terminal is closed — "
              f"the chat is back{OFF}", flush=True)
        return False

    def _persona_by_id(self, agent_id: str) -> Persona | None:
        return self._main if not agent_id else self.crew.get(agent_id)

    # --- extra agents --------------------------------------------------------

    def reconcile_crew(self) -> None:
        """Build, rebuild or drop the extra agents to match the settings.

        Only between turns: an agent whose turn is running is left exactly as
        it is, and caught up on a later poll. An agent the wake engine cannot
        hear -- a word Vosk does not know, the openWakeWord engine -- is not
        built at all, because nothing could ever reach it.
        """
        if self.pipe is None:
            return
        agents = getattr(self.cfg, "agents", None)
        # By id, so a new wake phrase or display name is a change to the same
        # agent -- same conversation, same grants -- not a new one.
        # Each with the instructions its folder holds (Phase 10), so a change
        # to the file is a change to the spec, caught up like one.
        specs = ({spec["id"]: {**spec, "instructions": self.instructions_for(
                      spec["id"], spec.get("instructions", ""))}
                  for spec in agents()} if callable(agents) else {})
        disabled = getattr(self.cfg, "disabled_agents", None)
        off = disabled() if callable(disabled) else set()
        heard = set(getattr(self.pipe, "names", ()) or ())
        self._main.name = getattr(self.pipe, "phrase", "") or ""
        label = getattr(self.cfg, "main_label", None)
        self._main.label = label(self._main.name) if callable(label) else self._main.name
        changed = False
        for key in list(self.crew):
            p = self.crew[key]
            if p.busy and key in off:
                # Switched off mid-turn: stopped now, not left to finish.
                # A deleted agent still finishes its turn, as before; "off"
                # is a switch somebody reached for, and it should act like one.
                if not p.interrupt.is_set():
                    print(f"  {CYA}agent “{p.label}” switched off: stopping its "
                          f"turn{OFF}", flush=True)
                    p.stop()
                continue
            if (key in specs and specs[key]["name"] in heard) or p.busy:
                continue
            if p.agent is not None:
                p.agent.cancel()
            del self.crew[key]
            changed = True
            print(f"  {CYA}agent “{p.label}” removed{OFF}", flush=True)
        for key, spec in specs.items():
            if spec["name"] not in heard:
                continue
            p = self.crew.get(key)
            if p is not None and p.busy:
                continue
            if p is None:
                p = self.crew[key] = Persona(spec["name"], spec)
                self._build_persona(p, spec)
                changed = True
            elif p.spec != spec:
                self._rebuild_persona(p, spec)
                changed = True
            if self._reconcile_persona_voice(p):
                changed = True
        if changed:
            self.publish_agent()

    def _build_persona(self, p: Persona, spec: dict) -> None:
        """The adapter for an extra agent, from its own settings."""
        p.spec = spec
        p.id, p.name, p.label = spec["id"], spec["name"], spec["label"]
        program = spec["agent"]
        if not program:
            p.agent, p.problem = None, "no agent program is chosen for it"
        elif program == "endpoint":
            # Its own URL, model and key (plan 7b). The key is read here,
            # once, as for the main agent's endpoint, never from settings.
            endpoint = spec.get("endpoint")
            if not endpoint:
                p.agent, p.problem = None, "its endpoint needs an address and a model"
            else:
                p.agent = load_adapter(
                    None,
                    endpoint={**endpoint, "key": endpoint_key(_host(endpoint["url"]))},
                    instructions=spec.get("instructions", ""))
                p.problem = "" if p.agent is not None else "its endpoint is not usable"
        else:
            level = spec["level"]
            p.agent = load_adapter(
                program, level=level, ask_permission=level != "trusted",
                cwd=str(project_dir(spec["projectDir"])),
                model=spec["model"] or None, effort=spec["effort"] or None,
                instructions=spec.get("instructions", ""), named=p.id)
            p.problem = "" if p.agent is not None else (
                explain_agent(program) or f"{program} is not available")
        p.session_id = None
        if program == "endpoint" and spec.get("endpoint"):
            spec = {**spec, "model": spec["endpoint"]["model"]}
        where = (f"{program}{' · ' + spec['model'] if spec['model'] else ''}"
                 f"{' · ' + spec['effort'] + ' effort' if spec['effort'] else ''}"
                 f" · {spec['level']}")
        if p.problem:
            print(f"  {YEL}agent “{p.label}”: {p.problem}{OFF}", flush=True)
        else:
            print(f"  {CYA}agent “{p.label}”: {where}{OFF}", flush=True)

    def _rebuild_persona(self, p: Persona, spec: dict) -> None:
        """Catch an idle extra agent up with changed settings.

        An effort, voice, speed or instructions keep the conversation, as
        they do for the main agent, and so do its display name and wake
        phrase: the permission hook knows it by id. So do its tool switches
        (Phase 13), which apply_extras hands to the adapter between turns,
        and its notes write (Phase 14), which the notes server reads fresh.
        Anything else -- program, model, folder, level -- rebuilds the
        adapter, so no process started under the old flags takes another
        turn. The conversation survives a new level or model where the
        backend can resume under them, as the main agent's does
        (carry_session; phase M2, bug I); a new program, folder or endpoint
        starts a new one, because a session is scoped to those.
        """
        old = p.spec or {}
        kept = ("effort", "voice", "speed", "instructions", "name", "label",
                "narration", "tools", "notesWrite", "collaboration", "acceptsWork",
                # Phase M17: handed to the running adapter by apply_launch.
                "resume", "idleTimeoutS", "extraArgs")
        same = {k: v for k, v in spec.items() if k not in kept}
        was = {k: v for k, v in old.items() if k not in kept}
        if same == was and p.agent is not None:
            p.spec = spec
            if (p.name, p.label) != (spec["name"], spec["label"]):
                print(f"  {CYA}agent “{p.label}” is now “{spec['label']}”, woken by "
                      f"“{spec['name']}”{OFF}", flush=True)
            p.name, p.label = spec["name"], spec["label"]
            want = spec.get("instructions", "")
            if getattr(p.agent, "instructions", "") != want:
                p.agent.instructions = want
                p.agent.cancel()            # read when its process starts
                print(f"  {CYA}agent “{p.label}”: instructions "
                      f"{'updated' if want else 'cleared'}{OFF}", flush=True)
            if takes_effort(p.agent):
                before = getattr(p.agent, "effort", None)
                p.agent.effort = spec["effort"] or None
                if before != p.agent.effort:
                    p.agent.cancel()        # the waiting process had the old flag
                    print(f"  {CYA}agent “{p.label}”: effort "
                          f"{spec['effort'] or 'default'}{OFF}", flush=True)
            return
        changed = sessions.spec_changes(was, same) if p.agent is not None \
            else {sessions.PROGRAM}
        sid = p.session_id
        old_cwd = getattr(p.agent, "cwd", None)
        if p.agent is not None:
            p.agent.cancel()
        self._build_persona(p, spec)        # always: the old flags go
        # The folder each adapter really runs in, not the settings resolved
        # now: a project that was unmounted resolves to home on both sides
        # and would have read as no move at all (Codex review of M2).
        new_cwd = getattr(p.agent, "cwd", None)
        if old_cwd and new_cwd:
            if str(old_cwd) != str(new_cwd):
                changed.add(sessions.FOLDER)
            else:
                changed.discard(sessions.FOLDER)
        # phase M2, bug I: _build_persona drops the session; put it back
        # when this change is one the new adapter can carry it across.
        p.session_id = sid
        kept = self.carry_session(p, changed, spec.get("agent") or "")
        # phase M16: the ring, by kind and the sessions vocabulary only.
        self.agent_ring.add(p.id, "rebuilt", changed=changed, kept=kept if sid else None)

    def persona_speed(self, p: Persona) -> int:
        """An extra agent's own speed, else the main agent's."""
        own = (p.spec or {}).get("speed") or 0
        return speed_pct(own) if own else speed_pct(self.cfg["voiceSpeed"])

    def _reconcile_persona_voice(self, p: Persona) -> bool:
        """Give an extra agent its own voice. True if that changed anything."""
        if not self.cfg.get_bool("speakReplies"):
            if p.speaker is None:
                return False
            p.speaker = None
            return True
        wanted = (p.spec or {}).get("voice") or self.cfg.get_str("voice")
        speed = self.persona_speed(p)
        if (p.speaker is not None and getattr(p.speaker, "requested", None) == wanted
                and not p.speaker.superseded()):
            if getattr(p.speaker, "speed", 100) == speed:
                return False
            p.speaker.speed = speed
            self.say_once(f"speed:{p.id}", f"  {CYA}agent “{p.label}” speaks at "
                                             f"{speed}%{OFF}")
            return True
        try:
            p.speaker = self.make_speaker(wanted)
            p.speaker.speed = speed
        except Exception as e:
            self.say_once(f"voice:{p.id}", f"  {YEL}agent “{p.label}”: voice "
                                             f"{wanted} unavailable: {e}{OFF}")
            return False
        self.say_once(f"voice:{p.id}", f"  {CYA}agent “{p.label}” speaks as "
                                         f"{p.speaker.name}{OFF}")
        return True

    def crew_fields(self) -> dict:
        """What the settings need to draw each extra agent truthfully: the
        effort levels its model takes, the permission levels its program can
        honour, and why it cannot be reached, if it cannot."""
        agents = getattr(self.cfg, "agents", None)
        specs = agents() if callable(agents) else []
        unheard = dict(getattr(self.pipe, "unheard", {}) or {})
        out = []
        for spec in specs:
            p = self.crew.get(spec["id"])
            a = p.agent if p is not None else None
            out.append({
                "id": spec["id"],
                "name": spec["name"],
                "label": spec["label"],
                "efforts": list(getattr(a, "efforts", tuple)()) if a else [],
                "levels": list(getattr(a, "levels", ("ask", "trusted")))
                          if a else ["ask", "edits", "trusted"],
                "takes_model": bool(takes_model(a)) if a else spec["agent"] in (
                    "claude", "codex", "gemini", "agy"),
                "posture": a.posture(spec["level"]) if a else "",
                "problem": unheard.get(spec["name"], "")
                           or (p.problem if p is not None else ""),
                "voice": getattr(p.speaker, "name", "") if p and p.speaker else "",
            })
        return {"crew": out, "open_mic": self.open_mic_field(),
                # Per folder: sizes, problems, files changed outside Settings
                # (Phase 9). The pages draw it from Phase 12.
                "agent_files": getattr(self, "_agent_files", None) or {},
                # phase M2, bug C: {"date", "today", "last"}; the
                # Conversation page says so beside the longest-turn slider.
                "limit_hits": self.limit_field()}

    def panel_agents(self, payload: dict) -> list[dict]:
        """Every agent as agents_panel.py draws it, from the payload just
        written and the agents' own state.

        The payload's state is the one line on screen, which with several
        agents may be another agent's; the microphone's own state is kept
        apart in `_mic_shown`, and each agent's activity is its own.
        """
        mic = self._mic_shown[0] if self.crew_mode else str(payload.get("state", "off"))
        hearing = mic in ("capture", "transcribing", "followup")
        who = str(payload.get("who", "") or "")
        main = self._main
        if self.crew_mode:
            main_activity = main.state if main.busy else "idle"
        else:
            main_activity = mic if mic in ("thinking", "speaking") else "idle"
        program = getattr(main.agent, "name", "") or ""
        main_effort = getattr(main.agent, "effort", None) or ""
        if main_effort not in tuple(getattr(main.agent, "efforts", tuple)()):
            main_effort = ""
        oww = getattr(self.pipe, "_oww", None) is not None
        phrase = (self.cfg.get_str("owwModel").replace("_", " ") if oww
                  else getattr(self.pipe, "phrase", "") or self.cfg.get_str("phrase"))
        out = [{
            "key": "main",
            # Named for what answers it: "Claude Code (voice)". The wake
            # phrase is already in its status line.
            # A display name somebody chose wins; with none it keeps
            # naming what answers, as before.
            "label": (self._main.label if self.cfg.get_str("mainName").strip()
                      else program_label(program) if program else "Agent Voice"),
            "program": program,
            "model": getattr(main.agent, "model", None) or "",
            # Read off the main agent itself, not effort_in_force(): this can
            # run on another agent's turn thread, where self.agent is theirs.
            "effort": main_effort,
            "level": self.cfg.level_for(program) if program else "",
            "phrase": phrase,
            "activity": main_activity,
            "for": self.collab.working_for(main) if main.busy else "",
            "hearing": hearing and who in ("", main.id),
            "problem": "" if program else (payload.get("posture") or ""),
        }]
        unheard = dict(getattr(self.pipe, "unheard", {}) or {})
        agents = getattr(self.cfg, "agents", None)
        for spec in (agents() if callable(agents) else []):
            name = spec["name"]
            p = self.crew.get(spec["id"])
            a = p.agent if p is not None else None
            out.append({
                # The id, not the wake phrase: a renamed agent keeps its record.
                "key": slug(spec["id"]),
                "label": spec["label"],
                "program": spec.get("agent", "") if a is not None else "",
                "model": getattr(a, "model", None) or spec.get("model") or "",
                "effort": getattr(a, "effort", None) or spec.get("effort") or "",
                "level": spec.get("level", ""),
                "phrase": name,
                "activity": (p.state if p is not None and p.busy else "idle"),
                # collab: whom it is working for, while it runs a task.
                "for": self.collab.working_for(p) if p is not None and p.busy else "",
                "hearing": hearing and who == spec["id"],
                "problem": unheard.get(name, "") or (p.problem if p is not None else ""),
            })
        return out

    def _mirror_panel(self, payload: dict) -> None:
        # The preview's sample turn is the readout's alone: Omarchy's Agents
        # panel would show the main agent "speaking" for four seconds.
        if self.panel is not None and not payload.get("preview"):
            self.panel.publish(str(payload.get("state", "off")),
                               self.panel_agents(payload))

    def _out(self):
        """Where the current turn publishes its state. See crew.View."""
        if not self._in_turn():
            return self.state
        p = self._persona()
        view = getattr(p, "view", None)
        if view is None:
            view = p.view = View(p, self._recompose)
        return view

    def _recompose(self) -> None:
        """Redraw the shared readout after an agent's own state moved.

        The snapshot is read under the state file's own lock: read outside
        it, a timer (the readout preview's end) could take `listening`, lose
        the race to the microphone publishing `capture`, and write the stale
        snapshot back over it (Codex review of M3)."""
        if self.state is not None:
            with getattr(self.state, "_lock", None) or contextlib.nullcontext():
                state, extra = self._mic_shown
                self.state.publish(state, **extra)

    def _compose(self, state: str, extra: dict) -> tuple[str, dict]:
        """_compose_line, with the collaboration tasks beside it (Phase 15):
        `tasks` for the Collaboration list and `collab`, one line for the
        HUD. Neither holds a brief or a request. Absent when there are none,
        so the state file reads as before."""
        state, extra = self._compose_line(state, extra)
        if not self.locked:
            # phase M3: the kept reply, texts cleared and staying cleared,
            # and the preview. Before the muted flag below, so a preview
            # laid over a muted microphone still says it is muted.
            state, extra = self.readout_for().compose(state, extra)
        # Said outright now that a muted readout can show an agent
        # speaking (phase M2, testresults #10): the popup's Mute button
        # read "muted" off the state being "off", and would have offered
        # "Mute" -- a click that unmutes -- to somebody already muted.
        if not self.enabled and state != "off":
            extra = {**extra, "muted": True}
        if self.locked:
            # Decided here, under the state file's own lock, because a turn
            # thread may compose from a microphone state read before the lock
            # landed: nothing anybody said or any agent answered goes out
            # while the screen is locked. And what was on screen before it
            # stays gone after the unlock (phase M3).
            self.readout_for().lock()
            return "locked", {k: v for k, v in extra.items()
                              if k not in ("transcript", "reply", "partial", "thinking",
                                           "who", "who_label", "collab", "tasks",
                                           "last_reply", "preview")}
        # phase M2, bug I: why a rebuild ended an agent's conversation, for
        # the HUD's extra line. Here rather than in the sticky fields so that
        # a lock, above, takes it off the screen with everything else.
        notices = getattr(self, "_notices", None)
        if notices:
            extra = {**extra, "notice": " · ".join(n[0] for n in notices.values())}
        fields = self.collab.fields()
        if fields["tasks"] or fields["collab"]:
            extra = {**extra, **fields}
            # Whose turn it is, and for whom: "Sora (for Theo)".
            shown = self._persona_by_id(str(extra.get("who", "") or ""))
            for_whom = self.collab.working_for(shown) if shown is not None else ""
            if for_whom and extra.get("who_label"):
                extra["who_label"] = f"{extra['who_label']} (for {for_whom})"
        return state, extra

    def _compose_line(self, state: str, extra: dict) -> tuple[str, dict]:
        """What the one line on screen shows, given the microphone's state.

        Installed as the state file's overlay, so every publish passes here.
        With one agent it changes nothing. With several, the microphone wins
        whenever it is doing something -- capturing, transcribing, locked,
        lent out -- and otherwise the readout shows the agent that is
        speaking, else the one that started thinking last, else the one that
        answered last. `who` names whose turn it is and `live` says what each
        agent is doing.

        Muted is not "doing something" (phase M2, testresults #10). A mute
        closes the microphone and nothing else: a typed turn is answered
        aloud, and a reply under way keeps playing. With the microphone
        winning, the readout said "off" over all of it -- no HUD, the last
        thing heard stuck on the turn before, an agent shown speaking after
        it had finished. A lock still wins, in _compose(), over everything.
        """
        self._mic_shown = (state, dict(extra))
        if not self.crew_mode:
            return state, extra
        everyone = self.personas()
        # By id, "" being the main agent: a display name is any text and
        # need not be unique, and the screen looks agents up by id.
        live = {p.id: (p.state if p.busy else "idle") for p in everyone}
        if state in ("listening", "off"):
            speaking = [p for p in everyone if p.busy and p.state == "speaking"]
            thinking = sorted((p for p in everyone
                               if p.busy and p.state == "thinking"),
                              key=lambda p: getattr(p, "started_at", 0.0),
                              reverse=True)
            shown = (speaking or thinking or [None])[0]
            if shown is not None:
                merged = {**shown.last, "who": shown.id, "who_label": shown.label,
                          "live": live}
                if "level_db" in extra:
                    merged["level_db"] = extra["level_db"]
                return shown.state, merged
            recent = self._recent
            if recent is not None:
                cached = recent.last or {}
                if any(cached is d for d in getattr(self, "_stale_lasts", ())):
                    # Cleared from the readout since (phase M3).
                    cached = {k: v for k, v in cached.items()
                              if k not in ("transcript", "reply")}
                return state, {**extra, **cached, "who": recent.id,
                               "who_label": recent.label, "live": live}
        capturing = self._capture_for is not None and state in (
            "capture", "transcribing", "followup")
        who = self._capture_for if capturing else None
        return state, {**extra, "who": who.id if who else "",
                       "who_label": who.label if who else "", "live": live}

    def _woken(self) -> Persona:
        """The agent whose name the wake engine just heard.

        If it is working, it stops, exactly as the wake word stops the one
        agent there used to be -- the others carry on.
        """
        heard = getattr(self.pipe, "heard_phrase", "") or ""
        p = next((q for q in self.crew.values() if q.name == heard), self._main)
        if p.busy:
            p.stop()
            print(f"  {GRN}● {p.label or 'wake'}{OFF}  {DIM}stopping it — go "
                  f"ahead{OFF}", flush=True)
        return p

    def _talk_target(self) -> Persona:
        """Who push-to-talk speaks to: whoever was spoken to last, unless the
        sentence starts with somebody else's name."""
        p = self._last_target
        if p is None or (p is not self._main and self.crew.get(p.id) is not p):
            return self._main
        return p

    def _send(self, p: Persona, text: str, last: dict, clock: dict,
              open_turn: bool = False, typed: bool = False,
              heard_at: float | None = None) -> None:
        """Route what was said and hand it to an agent.

        A sentence that opens with an agent's name is for that agent, from
        anywhere -- a follow-up window, push-to-talk, a barge-in -- and the
        name is taken off it. A stop is a stop for that agent.
        """
        names = {q.name: q for q in self.personas() if q.name}
        name, rest = route(text, names)
        if name:
            p = names[name]
            text = rest
            last = {**last, "transcript": text}
            if not text:
                print(f"  {DIM}(only a name — nothing to send){OFF}")
                return
        if is_full_stop(text):
            self.full_stop()
            return
        if is_stop_command(text):
            p.follow_up = False
            # collab: and every task it started, or still waiting for it.
            self.collab.stop_from(p)
            if p.busy:
                p.stop()
                print(f"  {DIM}(stopping {p.label}){OFF}")
            return
        if name:
            # Named on the open microphone: it is that agent's now.
            self.pass_open_mic(p)
        if self.voice_command(p, text):
            return
        # Phase M4: a command inside the sentence. Never in a typed one.
        said = None if typed else self.sentence_command(p, text, last, heard_at)
        if said is not None:
            if not said.rest and said.command.id not in _IN_TURN_COMMANDS:
                return                  # said, and nothing left to send
            text = said.rest
            last = {**last, "transcript": text}
        p.open_turn = open_turn and not name and self.open_mic is p
        if p.agent is None and not p.main:
            # Said out loud through the echo path, rather than the transcript
            # read back, which is what a missing main agent gets.
            text = f"{p.label} cannot answer: {p.problem or 'it is not set up'}."
        if typed:
            self.dispatch(p, text, last, clock, typed=True)
        elif said is not None:
            if not self.dispatch(p, text, last, clock, command=said):
                self.undo_clock(said)   # no turn will carry it
        else:
            self.dispatch(p, text, last, clock)

    def dispatch(self, p: Persona, text: str, last: dict,
                 clock: dict | None = None, typed: bool = False,
                 command=None) -> bool:
        """Start a turn for `p` on its own thread. False if it could not.

        An agent already working is stopped first: one conversation cannot
        take two turns at once, and somebody who asks again has changed
        their mind.
        """
        if p.busy:
            p.stop()
            p.thread.join(timeout=5.0)
            if p.busy:
                print(f"  {YEL}{p.label or 'the agent'} did not stop; not "
                      f"sending{OFF}", flush=True)
                return False
        # Caught up before every turn, not only one that replaced a busy
        # turn (Phase 11 review): a turn stopped by a wake word may end while
        # the next request is still being spoken, and the polls that would
        # have caught it up do not run during a capture (Phase 13 review: it
        # kept Chrome after Chrome was switched off). Cheap when nothing
        # changed: stamps and comparisons. Only on the run loop's thread,
        # where a refresh belongs.
        if threading.current_thread() is threading.main_thread():
            self.catch_up_one(p)
            if not self.catch_up_flags(p):
                # Deleted or switched off while the request was being said:
                # its old adapter, perhaps a trusted one, takes no new turn
                # (Codex review of M2).
                print(f"  {YEL}agent “{p.label}” is no longer set up; "
                      f"not sending{OFF}", flush=True)
                return False
        p.interrupt.clear()
        p.follow_up = False
        p.ends_pending = False      # phase M4: about the turn before this one
        p.turn_error = ""           # collab: this turn's own, not the last one's
        turn = dict(last)
        p.last, p.state, p.started_at = turn, "thinking", time.time()
        self._last_target = p
        self._recent = None
        p.thread = threading.Thread(target=self._turn,
                                    args=(p, text, turn, clock, typed, command),
                                    name=f"turn-{p.name or 'main'}",
                                    daemon=True)
        p.thread.start()
        return True

    def _turn(self, p: Persona, text: str, last: dict,
              clock: dict | None, typed: bool = False, command=None) -> None:
        self._here.persona = p
        self._here.turn = True
        self._here.typed = typed
        try:
            if command is None:
                self.answer(text, last, clock=clock)
            else:
                self.answer(text, last, clock=clock, command=command)
            # Not after a typed turn: whoever typed may not be in a position
            # to talk, and a window would take the room's next sentence. Not
            # after "…, stop listening" either (phase M4).
            p.follow_up = (self.arm_follow_up() and not typed
                           and not (command is not None and command.command.ends)
                           and not getattr(p, "ends_pending", False))
        except Exception as e:      # a broken turn must not take a thread down silently
            print(f"  {YEL}{p.label or 'agent'}: turn failed: "
                  f"{type(e).__name__}: {e}{OFF}", flush=True)
            p.follow_up = False
            p.turn_error = p.turn_error or type(e).__name__    # collab: not "completed"
        finally:
            p.state = "idle"
            p.finished_at = time.time()
            with self._floor:
                if self._floor_owner is p:
                    self._floor_owner, self._floor_until = None, 0.0
                self._floor.notify_all()
            self._recent = p
            if getattr(p, "ends_pending", False):
                p.follow_up = False     # said while this was finishing
            p.ends_pending = False
            if command is not None:
                self.undo_clock(command)        # phase M4
            # collab: a task turn's end is its task's end.
            self.collab.turn_ended(p, stopped=p.interrupt.is_set(),
                                   failed=p.turn_error)
            self._recompose()

    def open_mic_due(self, crew: bool) -> bool:
        """Whether the run loop, waiting for the wake word, should listen
        for the open microphone's agent instead. Closes it when it should
        close: the microphone off (a mute, a lock, a lent microphone), too
        long with nothing said, or its agent gone."""
        om = self.open_mic
        if om is None:
            return False
        if not self.listening:
            if self.enabled or self.locked or self.yielded:
                self.end_open_mic("the microphone is off")
            # Muted: held, not ended. It picks up again on unmute, and the
            # idle timeout below still closes it if the mute lasts.
            elif self.open_mic_until <= time.time():
                self.end_open_mic(f"nothing said for {self.open_mic_idle_s() / 60:.0f} min")
            return False
        if self.open_mic_until <= time.time():
            self.end_open_mic(f"nothing said for {self.open_mic_idle_s() / 60:.0f} min")
            return False
        if not crew:
            return True
        if om is not self._main and self.crew.get(om.id) is not om:
            self.end_open_mic("its agent is gone")
            return False
        return not (om.busy or om.follow_up or self._speaking or self._hold_speech
                    or self._due_follow_up_blocked())

    def _due_follow_up_blocked(self) -> bool:
        """Another agent is mid-reply: the open microphone waits for it."""
        owner = self._floor_owner
        return owner is not None and owner is not self.open_mic and owner.busy

    def _due_follow_up(self) -> Persona | None:
        """The agent whose follow-up window should open now, if any.

        The one that answered last, while its answer is fresh and nobody else
        is mid-reply. Only one window at a time: the rest lapse.
        """
        if not (getattr(self.pipe, "conversation", False) or self.open_mic) \
                or not self.listening:
            return None
        now = time.time()
        best = None
        for p in self.personas():
            if not p.follow_up or p.busy:
                continue
            if now - p.finished_at > FOLLOW_UP_STALE_S:
                p.follow_up = False
                continue
            if best is None or p.finished_at > best.finished_at:
                best = p
        if best is None:
            return None
        owner = self._floor_owner
        if (owner is not None and owner is not best and owner.busy) or self._speaking:
            return None
        for p in self.personas():
            p.follow_up = False
        return best

    def _next_frame(self, frames: "queue.Queue[bytes]") -> bytes | None:
        """A frame for the run loop, or None while an agent is speaking.

        While one speaks the microphone is the reply's -- our own voice, and
        barge-in's to read on a headset -- exactly as it was when the loop
        was blocked inside the reply.
        """
        with self._mic_lock:
            if not self._speaking:
                try:
                    return frames.get_nowait()
                except queue.Empty:
                    pass
        time.sleep(0.02)
        return None

    @contextlib.contextmanager
    def _microphone(self, sd, device, cb):
        """The input stream, or silence in its place when there is none.

        With no microphone at all the stream would not open and the daemon
        would exit, taking typed messages and spoken replies with it. Silence
        at the same pace keeps every part of the loop running: nothing is
        ever heard, and `agentvoice type` still reaches the agents.
        """
        stream = None
        try:
            stream = sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16",
                                       blocksize=CHUNK, device=device, callback=cb)
            stream.__enter__()
        except Exception as e:
            print(f"  {YEL}no microphone ({type(e).__name__}: {e}) — running "
                  f"without one; typed messages still work{OFF}", flush=True)
            stream = None
        if stream is not None:
            try:
                yield
            finally:
                stream.__exit__(None, None, None)
            return
        stop = threading.Event()

        def feed():
            silence = bytes(CHUNK * 2)
            due = time.time()
            while not stop.is_set():
                cb(silence, CHUNK, None, None)
                due += CHUNK / RATE
                stop.wait(max(0.0, due - time.time()))

        threading.Thread(target=feed, name="no-microphone", daemon=True).start()
        try:
            yield
        finally:
            stop.set()

    def run(self, device: int | None) -> int:
        import sounddevice as sd

        frames: queue.Queue[bytes] = queue.Queue()

        def cb(indata, _f, _t, status):
            if status:
                print(f"\n  {YEL}[audio: {status}]{OFF}")
            frames.put(bytes(indata))

        self._frames = frames
        self.banner()
        self._publish()
        last = _empty_turn()
        shown_partial = ""

        with self._microphone(sd, device, cb):
            phase = "wake"
            buf = b""
            cap = None
            # Transcribes as you talk; None outside a capture. See eager.py.
            utt = None
            woke_at = last_voice = released_at = 0.0
            # When the first word of this capture was heard: where the
            # longest-turn limit counts from (phase M2, bug C).
            spoke_at = 0.0
            heard = False
            # A follow-up gets its own, shorter window: after a reply the
            # machine keeps listening for a moment so the next thing you say
            # does not need the wake word again.
            active_lead_in = self.pipe.lead_in_ms

            level_shown = gate_shown = 0.0
            # One idle poll before the first frame, so every agent -- the
            # extra agents are built here -- has its prompt before the first
            # word can be heard: the first poll would otherwise be 2s away,
            # and a wake inside that started Claude on the old preamble
            # (Phase 11 review).
            self.refresh()
            last_poll = last_lock_poll = time.time()
            # Push-to-talk: the key decides both ends of the turn, so the
            # wake word is bypassed and silence no longer endpoints.
            ptt = ptt_done = False
            # With extra agents: who the capture under way is for, and how it
            # opened -- "wake", "talk", "barge" or "followup". See crew.py.
            capture_for: Persona | None = None
            capture_kind = ""
            readout_seen = self.readout_for().generation
            while True:
                crew = self.crew_mode
                # phase M3: the readout was cleared (a lock, an expiry, a
                # switch) since this loop last looked: its copy of the last
                # turn loses the words, or the next level update would put
                # them back on screen. A turn under way starts its own.
                if self.readout_for().generation != readout_seen:
                    readout_seen = self.readout_for().generation
                    last = {k: v for k, v in last.items()
                            if k not in ("transcript", "reply")}
                # Beside running turns the loop never blocks on the queue:
                # it has to keep polling the lock and the commands while an
                # agent speaks, when the microphone is the reply's.
                pcm = self._next_frame(frames) if crew else frames.get()

                cmd = self.take_command()
                # One implementation, shared with the reply loop, so a lock
                # means the same thing wherever the daemon happens to be.
                if self.apply_lock_command(cmd):
                    continue
                if self.apply_wake_test_command(cmd):
                    continue
                if self.apply_readout_command(cmd):
                    continue
                mic_cmd = self.apply_open_mic_command(cmd)
                # phase M2, bug K: the open microphone ended -- the popup's
                # switch, `agentvoice open-mic off`, a full stop -- while
                # its window was open and nobody had started talking. The
                # window was left to run out its lead-in, which for the
                # open microphone is the rest of its idle time, so "still
                # listening" stayed up for up to ten minutes after "off".
                # It closes now; a capture somebody is speaking into is
                # left to finish, and goes to the agent as usual.
                if (phase == "capture" and capture_kind == "undo"
                        and not heard and self.undo_due() <= 0):
                    # Phase M4: the popup, the CLI or a mode change took the
                    # undo's chance away while nobody was speaking.
                    if utt is not None:
                        utt.abandon()
                        utt = None
                    phase, ptt, ptt_done = "wake", False, False
                    self._capture_for = None
                    self._publish(**last)
                    continue
                if (phase == "capture" and capture_kind == "open"
                        and not heard and self.open_mic is None):
                    if utt is not None:
                        utt.abandon()
                        utt = None
                    phase, ptt, ptt_done = "wake", False, False
                    self._capture_for = None
                    print(f"  {DIM}(open mic window closed){OFF}", flush=True)
                    self._publish(**last)
                    continue
                if mic_cmd:
                    continue
                if self.apply_chat_command(cmd):
                    continue
                if phase == "wake":
                    # Only between captures: a message typed while somebody
                    # is talking waits for them to finish.
                    typed = self.take_typed()
                    if typed is not None:
                        self.handle_typed(*typed, crew)
                        continue
                    # phase M6: Agent details' Try it, between captures too.
                    trial = self.take_try()
                    if trial is not None:
                        self.handle_try(*trial)
                        continue
                    # collab: pass requests from the CLI and the sheet, and
                    # tasks whose cancel window or queue has cleared.
                    self.collab.tick()
                elif (phase == "capture" and capture_kind == "followup"
                        and not heard):
                    # collab: an empty follow-up window (the one opened for
                    # "stop" after a pass is announced) does not hold the
                    # pass back once its own window has passed.
                    self.collab.tick()
                if cmd == "talk" and self.listening:
                    if utt is not None:
                        utt.abandon()
                    capture_for = self._talk_target() if crew else None
                    capture_kind = "talk"
                    phase, buf, cap = "capture", b"", self.pipe.new_capture()
                    utt = self.pipe.new_utterance()
                    with self._as(capture_for):
                        self._interrupt.clear()     # see the wake branch
                        self.prime_agent()
                    if crew:
                        self._capture_for, self._recent = capture_for, None
                        self._hold(True)
                    woke_at = last_voice = spoke_at = time.time()
                    heard = False
                    ptt, ptt_done = True, False
                    active_lead_in = self.pipe.lead_in_ms
                    self._deaf_until = 0.0
                    print(f"  {GRN}● talk{OFF}  {DIM}(listening while held){OFF}",
                          flush=True)
                    last = _empty_turn()
                    shown_partial = ""
                    self.state.publish("capture", **last)
                elif cmd == "talk-end" and ptt:
                    ptt_done = True
                    # The key coming up is when you stopped talking, which is
                    # where the turn's latency is counted from.
                    released_at = time.time()

                # Before the gate below, and on its own clock, because
                # everything past the gate is skipped while the screen is
                # locked. The lock check used to live in refresh(), which is
                # below it: the microphone closed on lock and then nothing
                # ever looked again, so it stayed closed after unlocking
                # until the service was restarted. Which is the exact failure
                # this feature exists to avoid.
                if time.time() - last_lock_poll > 2.0:
                    last_lock_poll = time.time()
                    self.reconcile_lock()
                    # Above the `listening` gate for the same reason the lock
                    # poll is: once the microphone is lent out the loop stops
                    # at the gate below, so a check placed after it would
                    # never run again and the microphone would stay lent
                    # forever. That exact bug shipped once already.
                    self.reconcile_yield()
                    # phase M3: ten idle minutes and the readout clears --
                    # here, above the gate, so a muted or lent microphone
                    # does not keep the last exchange on screen for hours
                    # (Codex review of M3; it was in refresh(), below).
                    self.expire_readout()

                if crew:
                    # Every way out of a capture lands in "wake"; releasing
                    # the hold here covers all of them at once.
                    if phase == "wake" and self._hold_speech:
                        self._hold(False)
                    # A follow-up window nobody has spoken into yet closes
                    # when another agent starts its reply: the moment for
                    # a follow-up has passed, and our own voice is not one.
                    if (phase == "capture" and capture_kind in ("followup", "undo")
                            and not heard and self._speaking):
                        if utt is not None:
                            utt.abandon()
                            utt = None
                        phase, ptt, ptt_done = "wake", False, False
                        self._capture_for = None
                        self._publish(**last)
                    if pcm is None:
                        continue

                # Deaf window after our own speech: discard without even
                # measuring, so a tail of reverb cannot register as input.
                if time.time() < self._deaf_until:
                    continue

                level = frame_db(pcm)

                # Every frame recorded while the screen is locked is
                # discarded here, before it is measured, fed to the wake
                # word, or buffered.
                if not self.listening:
                    # And a capture already underway is abandoned rather than
                    # suspended. Leaving the phase alone looked harmless --
                    # frames stop arriving -- but `buf` keeps whatever was
                    # recorded up to the moment of the lock, so the utterance
                    # would resume and be transcribed on unlock, joined to
                    # whatever was said next.
                    if phase != "wake":
                        phase, buf, cap, ptt, ptt_done = "wake", b"", None, False, False
                        self._capture_for = None
                        # Its pieces too: a piece still queued would otherwise
                        # be transcribed after the lock, from audio recorded
                        # before it, for a turn that no longer exists.
                        if utt is not None:
                            utt.abandon()
                            utt = None
                        shown_partial = ""
                        last = _empty_turn()
                        self._publish(**last)
                    continue

                # The meter in the panel is how the threshold becomes settable
                # by eye instead of by guesswork, so the level is published even
                # while nothing is happening -- throttled, since this is every
                # 100ms and the file is watched.
                #
                # The same frames teach the adaptive gate the room: the wake
                # phase only, never while we speak or a chime may be sounding.
                if phase == "wake" and not self._speaking \
                        and time.time() >= self._chime_until:
                    self.pipe.learn_room(level)
                gate = self.pipe.threshold_db
                if phase == "wake" and (abs(level - level_shown) > 1.5
                                        or abs(gate - gate_shown) >= 0.5):
                    level_shown, gate_shown = level, gate
                    floor = self.pipe.floor_db
                    self._publish(level_db=round(level, 1), gate_db=round(gate, 1),
                                  **({"floor_db": round(floor, 1)}
                                     if floor is not None else {}), **last)

                # Settings used to land only after the next turn, because the
                # only refresh() was at a turn boundary -- so changing the
                # engine or the model while idle appeared to do nothing until
                # you spoke. Poll while waiting instead; rebuilding a model
                # blocks for a second or two, which is harmless here and
                # unacceptable mid-utterance.
                if phase == "wake" and time.time() - last_poll > 2.0:
                    last_poll = time.time()
                    self.refresh()
                    # Phase M19: a quiet chat named by its own agent, in a
                    # thread; below the gate, so never while locked or muted.
                    try:
                        self.name_chats()
                    except Exception as e:      # noqa: BLE001 -- never the loop
                        print(f"  {YEL}chat names: {type(e).__name__}{OFF}", flush=True)

                if phase == "wake" and self.open_mic is not None:
                    # The open microphone: back to listening without the
                    # wake word as soon as nothing else is going on. Closed
                    # by a mute, a lock or a lent microphone, which is what
                    # each of those means, and by going quiet for too long.
                    om = self.open_mic
                    if self.open_mic_due(crew):
                        capture_for = om if crew else None
                        capture_kind = "open"
                        if crew:
                            self._capture_for, self._recent = om, None
                        phase, buf, cap = "capture", b"", self.pipe.new_capture()
                        utt = self.pipe.new_utterance()
                        with self._as(capture_for):
                            self._interrupt.clear()     # see the wake branch
                            self.prime_agent()
                        woke_at = last_voice = spoke_at = time.time()
                        heard = False
                        active_lead_in = self.open_mic_left_ms()
                        last = _empty_turn()
                        shown_partial = ""
                        self.state.publish("followup", window=capture_kind, **last)
                        # No `continue`: this frame is the capture's first.

                if phase == "wake" and self.open_mic is None and self.undo_due() > 0:
                    # Phase M4: the seconds after "…, stop listening" in
                    # which "no" puts the open mic back. Anything else heard
                    # here is dropped, unsent.
                    undo_for = self._undo["persona"]
                    capture_for = undo_for if crew else None
                    capture_kind = "undo"
                    if crew:
                        # Not `_recent`: three seconds of listening for "no"
                        # must not take the last reply off the idle readout.
                        self._capture_for = undo_for
                    phase, buf, cap = "capture", b"", self.pipe.new_capture()
                    utt = self.pipe.new_utterance()
                    woke_at = last_voice = spoke_at = time.time()
                    heard = False
                    active_lead_in = self.undo_due()
                    last = _empty_turn()
                    shown_partial = ""
                    self.state.publish("followup", window=capture_kind, **last)
                    # No `continue`: this frame is the capture's first.

                if phase == "wake" and crew:
                    # What the run loop used to do straight after a reply,
                    # done here because replies now end on their own threads:
                    # carry on a sentence that talked over one, or open the
                    # follow-up window of the agent that answered last.
                    barged = self.take_barge()
                    reopen, kind = None, ""
                    if barged is not None:
                        reopen = self._barged_by or self._last_target or self._main
                        kind = "barge"
                    else:
                        due = self._due_follow_up()
                        if due is not None:
                            reopen, kind = due, "followup"
                    if reopen is not None:
                        capture_for, capture_kind = reopen, kind
                        self._capture_for, self._recent = reopen, None
                        phase, buf, cap = "capture", b"", self.pipe.new_capture()
                        utt = self.pipe.new_utterance()
                        with self._as(reopen):
                            self._interrupt.clear()
                            self.prime_agent()
                        woke_at = last_voice = spoke_at = time.time()
                        heard = kind == "barge"
                        active_lead_in = (self.pipe.follow_up_ms if kind == "followup"
                                          else self.pipe.lead_in_ms)
                        if kind == "followup" and reopen is self.open_mic:
                            capture_kind = "open"
                            active_lead_in = max(active_lead_in, self.open_mic_left_ms())
                        if kind == "barge":
                            self._deaf_until = 0.0
                            self._hold(True)
                            for early in barged:
                                buf += early
                                self.hear(cap, utt, early, self.voiced(frame_db(early)))
                            print(f"  {GRN}● go on{OFF}  {DIM}(talked over "
                                  f"{reopen.label or 'the reply'} — listening){OFF}",
                                  flush=True)
                            last = _empty_turn()
                            shown_partial = ""
                            self.state.publish("capture", **last)
                        else:
                            print(f"  {CYA}● still listening{OFF}  {DIM}"
                                  f"({active_lead_in / 1000:.0f}s for "
                                  f"{reopen.label or 'it'} — or say a name){OFF}",
                                  flush=True)
                            last = _empty_turn()
                            shown_partial = ""
                            self.state.publish("followup", window=capture_kind, **last)
                        # No `continue`: this frame is the capture's first.

                # While the wake test runs, a wake is counted, not answered.
                if phase == "wake" and self.wake_testing(pcm, level):
                    continue

                if phase == "wake":
                    fired = self.pipe.feed_wake(pcm, level)
                    if fired and self.heard_full_stop():
                        # Spotted as a keyword: stop everything now, and
                        # open no capture -- there is nothing to say next.
                        print(f"  {YEL}● full stop{OFF}  {DIM}(heard as a keyword){OFF}",
                              flush=True)
                        self.full_stop()
                        continue
                    if fired:
                        capture_for = self._woken() if crew else None
                        capture_kind = "wake"
                        who = (f" {capture_for.label}"
                               if capture_for is not None and capture_for.label else "")
                        print(f"  {GRN}● wake{who}{OFF}  {DIM}go ahead"
                              f" ({self.pipe.lead_in_ms / 1000:.1f}s to start){OFF}",
                              flush=True)
                        if crew:
                            self._capture_for, self._recent = capture_for, None
                            self._hold(True)
                        phase, buf, cap = "capture", b"", self.pipe.new_capture()
                        utt = self.pipe.new_utterance()
                        # A stop belongs to the turn it stopped. The flag
                        # outlived it: answer() clears it on entry, but the
                        # check for a stop pressed during transcription comes
                        # before answer(), so the first request after any
                        # stop was discarded as "interrupted before sending"
                        # and had to be said twice. Cleared wherever a capture
                        # opens, which is after anything it could belong to.
                        with self._as(capture_for):
                            self._interrupt.clear()
                            # Now, while you are still talking, rather than
                            # when there is finally a prompt: a slow agent
                            # start is then hidden behind your own sentence.
                            self.prime_agent()
                        # The wake word only: push-to-talk has the key for
                        # feedback, and you are already talking when it goes
                        # down -- a chime there would be deafness over your
                        # first word.
                        # Not when the open microphone was already
                        # listening for this agent (phase M2, bug J).
                        quiet = self.listening_for(capture_for or self._main)
                        if quiet:
                            print(f"  {DIM}chime: wake not played ({quiet} "
                                  f"was already listening){OFF}", flush=True)
                        else:
                            self.chime("wake", "wake word")
                        woke_at = last_voice = spoke_at = time.time()
                        heard = False
                        active_lead_in = self.pipe.lead_in_ms
                        last = _empty_turn()
                        shown_partial = ""
                        self.state.publish("capture", **last)
                    continue

                buf += pcm
                # cap is None when live partials are off -- the turn runs
                # exactly the same, it just shows nothing until Whisper
                # returns. Endpointing below is energy-based either way.
                #
                # Energy decides when you stopped talking; Vosk's partials only
                # say what it thinks you said. A pause between words produces no
                # new partial but is not the end of a turn.
                #
                # Not while one of our own chimes is sounding: the frame is
                # kept -- you may already be talking over it, and dropping it
                # lost the first word of "computer, what time is it" -- but
                # the chime cannot count as you. Counted, it would end the
                # lead-in's wait for nobody, and a turn of nothing but a
                # chime would go to Whisper.
                voiced = self.voiced(level)
                if voiced:
                    if not heard:
                        spoke_at = time.time()  # see the limit below
                    heard = True
                    last_voice = time.time()
                    if crew and not self._hold_speech:
                        self._hold(True)        # somebody is talking now
                # The same measurement that endpoints the turn decides where
                # its pauses are, so a piece is never cut where the endpoint
                # would have heard speech.
                partial = self.hear(cap, utt, pcm, voiced)
                if capture_kind == "undo":
                    # Phase M4: what is said here is dropped unless it is
                    # "no"; it is not shown while it is said either.
                    partial = ""
                if partial and partial != shown_partial:
                    shown_partial = partial
                    if speech_is_logged(self.cfg.get_bool("logSpeech")):
                        print(f"{cursor_home()}  "
                              f"{DIM}{safe_for_terminal(partial)[:100]}{OFF}"
                              f"{' ' * 20}", end="", flush=True)
                    # Published, not merely printed. "Live transcript while
                    # you speak" costs 114MB and went to stdout alone, which
                    # under systemd means the journal -- so the one setting
                    # whose whole purpose is to be watched was invisible to
                    # anyone not tailing it. Sent as the transcript, so the
                    # readout fills in as you talk and Whisper's version
                    # replaces it in the same place.
                    self.state.publish("capture",
                                       **{**last, "transcript": partial})

                now = time.time()
                elapsed_ms = (now - woke_at) * 1000
                quiet_ms = (now - last_voice) * 1000
                # The longest-turn limit counts from the first word, not
                # from when the window opened (phase M2, bug C). From the
                # window, the open microphone -- which waits up to its idle
                # time for somebody to start -- cut anyone who began more
                # than maxUtteranceMs into it at their first frame: the
                # "cut off at 30 seconds with no warning" of 2026-11-19,
                # every one of them in open mic. A capture still ends at
                # most the lead-in plus the limit after it opens.
                spoken_ms = (now - spoke_at) * 1000

                # Waiting for you to begin. Deliberately generous: being cut
                # off before you have started is the most irritating failure
                # this thing can have.
                if not heard:
                    # Holding the key says "I am about to speak", so the
                    # lead-in timer does not run until it comes back up --
                    # but a key held in silence still stops at the limit, or
                    # a lost key-up buffered forever (Codex review of M2).
                    if (ptt_done if ptt else elapsed_ms > active_lead_in) or (
                            ptt and elapsed_ms >= self.pipe.max_utterance_ms):
                        if capture_kind in ("open", "undo"):
                            # The open microphone's wait is the time it has
                            # left: running out is the idle timeout. The
                            # undo's few seconds run out the same way.
                            print(cursor_home(120), end="")
                        else:
                            print(f"{cursor_home()}  {DIM}(nothing heard){OFF}"
                                  f"{' ' * 40}")
                        utt.abandon()
                        utt = None
                        phase = "wake"
                        ptt = ptt_done = False
                        self._publish(**last)
                        self.refresh()
                    continue

                if ptt and not ptt_done:
                    # A key that never comes back up must not buffer forever.
                    # From the key going down: everything since is recorded.
                    if elapsed_ms < self.pipe.max_utterance_ms:
                        continue
                elif not ptt and spoken_ms < self.pipe.max_utterance_ms \
                        and not self.turn_ended(quiet_ms, utt):
                    continue
                if (elapsed_ms if ptt else spoken_ms) >= self.pipe.max_utterance_ms:
                    print(f"{cursor_home()}  {YEL}(hit max_utterance_ms){OFF}"
                          f"{' ' * 30}")
                    self.count_limit_hit()      # phase M2, bug C
                # Where the latency of this turn is counted from: the last
                # sound you made, or the key coming up. Not the endpoint --
                # the pause it waits out is part of what you sit through.
                # A key still held at max_utterance_ms never came up, so it
                # has no release time of its own this turn.
                clock = {"voice_end": released_at if ptt and ptt_done
                         else last_voice,
                         "endpoint": time.time()}
                ptt = ptt_done = False
                if crew:
                    # They have finished talking; a waiting reply may start
                    # while the last of this is transcribed.
                    self._hold(False)

                audio_ms = len(buf) / 32.0
                follow_up = False
                barged = None
                woke = False
                if audio_ms < self.pipe.min_utterance_ms:
                    print(f"{cursor_home()}  {DIM}(too short, discarded){OFF}"
                          f"{' ' * 40}")
                    utt.abandon()
                else:
                    # Got it. Before the wait for Whisper, not after, so it
                    # marks the moment the turn ended -- the thing you could
                    # not tell before without looking at the bar.
                    self.chime("heard", "end of what was said")
                    # Its own state. This phase and the agent's turn both
                    # published "thinking", and the panel labelled that
                    # "TRANSCRIBING" -- so the label was right here and wrong
                    # for the whole of the agent's turn, which is the part
                    # people actually wait through.
                    self.state.publish("transcribing", **last)
                    # Mostly done already: each pause sent what came before it
                    # to Whisper while the endpoint was still waiting. What is
                    # left is whatever of the last piece has not finished.
                    raw, waited_ms = utt.finish()
                    text = as_prompt(raw)
                    ms = utt.busy_ms
                    clock["transcribed"] = time.time()
                    # Gated like every other line carrying speech. It was not,
                    # and the audit that was supposed to find them all used a
                    # grep that matched only the first physical line of a
                    # wrapped print -- which here holds a carriage return and
                    # 120 spaces, and nothing else. journalctl then rendered
                    # the result as "[214B blob data]", so checking the
                    # journal for leaked speech found none. Both the finding
                    # and the verification were wrong in the same direction.
                    if speech_is_logged(self.cfg.get_bool("logSpeech")):
                        print(f"{cursor_home(120)}  "
                              f"{BLD}{safe_for_terminal(text) or '(nothing)'}{OFF}")
                    else:
                        # Nothing at all in a journal. A lone carriage return
                        # there is not an erase, it is a prefix on the next
                        # line -- which is how the timings below ended up
                        # inside "[149B blob data]".
                        print(cursor_home(120), end="")
                    # Whisper's whole cost, then how much of it you actually
                    # waited for -- the second is the one that used to equal
                    # the first.
                    pieces = (f" in {utt.parts} pieces" if utt.parts > 1
                              else "")
                    print(f"  {DIM}{audio_ms / 1000:.1f}s audio, "
                          f"whisper {ms:.0f}ms{pieces}, "
                          f"{waited_ms:.0f}ms waited{OFF}")
                    last = {**_empty_turn(), "transcript": text,
                            "ms": round(ms),
                            "audio_s": round(audio_ms / 1000, 2)}
                    if text:
                        # Something said: the open microphone's idle time
                        # starts again, whoever it was for.
                        self.touch_open_mic()
                        if capture_kind == "wake" and self.open_mic is None \
                                and self.cfg.get_bool("openMicAuto"):
                            self.start_open_mic(capture_for or self._main, say=False)

                    # "stop", "cancel that", "never mind" and friends discard
                    # the turn instead of sending it. This is not an interrupt
                    # and cannot be one -- by the time anything is being said
                    # aloud the microphone is already deaf. Its real job is
                    # cancelling a wake that fired by mistake. Matched against
                    # the whole transcript, so an ordinary sentence that merely
                    # contains "stop" cannot trigger it.
                    stopped = (capture_for.interrupt
                               if crew and capture_for is not None
                               else self._interrupt)
                    if stopped.is_set():
                        # Stop pressed while Whisper was running. answer()
                        # clears this flag on entry, so the interrupt was
                        # accepted here and then thrown away: the reply arrived
                        # regardless. Discard the turn instead.
                        stopped.clear()
                        print(f"  {DIM}(interrupted before sending){OFF}")
                        follow_up = False
                    elif capture_kind == "undo" and not (
                            text and is_stop_command(text)):
                        # Phase M4: only an undo is taken from these few
                        # seconds -- and a stop, below. Whatever else was
                        # said is not sent, and not kept on screen.
                        if not (text and self.take_undo(text, spoke_at,
                                                        capture_for)) \
                                and self.open_mic is None:
                            print(f"  {DIM}(only \"no\" is taken here — "
                                  f"dropped){OFF}", flush=True)
                            last = _empty_turn()
                            shown_partial = ""
                        follow_up = False
                    elif text and self.take_undo(text, spoke_at, capture_for):
                        # "no", straight after an open-mic switch made
                        # inside a sentence: put back (phase M4).
                        follow_up = False
                    elif text and is_full_stop(text):
                        # Before routing: "Sarah, full stop" still means all
                        # of them, and route() would otherwise hand it to
                        # Sarah alone.
                        self.full_stop()
                        follow_up = False
                    elif text and is_goodbye(text):
                        print(f"  {DIM}(goodbye — waiting for the wake word){OFF}")
                        self.end_open_mic("goodbye")
                        follow_up = False
                    elif text and is_stop_command(text):
                        print(f"  {DIM}(stopping){OFF}")
                        # collab: a bare "stop" in the window after "Passing
                        # this chat to Sora" cancels the pass.
                        self.collab.stop_from(capture_for or self._main)
                        follow_up = False
                    elif text and crew:
                        # On its own thread: the loop goes straight back to
                        # listening, so another agent can be given something
                        # while this one works.
                        self._send(capture_for or self._main, text, last, clock,
                                   open_turn=capture_kind == "open",
                                   heard_at=spoke_at)
                        follow_up = False
                    elif text and self.voice_command(self._main, text):
                        follow_up = False
                    elif text and (said := self.sentence_command(
                            self._main, text, last, spoke_at)) is not None \
                            and not said.rest \
                            and said.command.id not in _IN_TURN_COMMANDS:
                        # Phase M4: a command inside the sentence, said and
                        # done, and nothing else in it to send.
                        follow_up = False
                    elif text:
                        if said is not None:
                            # Phase M4: what was left once the command was
                            # taken out goes to the agent as the request.
                            text = said.rest
                            last = {**last, "transcript": text}
                        self._main.open_turn = capture_kind == "open"
                        # A level lowered during the last turn applies
                        # before this one (Codex review of M2).
                        self.catch_up_flags(self._main)
                        if said is None:
                            self.answer(text, last, clock=clock)
                        else:
                            self.answer(text, last, clock=clock, command=said)
                            self.undo_clock(said)
                        # Uncapped on purpose, and worth stating because it
                        # reads like an oversight: a follow-up window opens
                        # after every answered turn, it uses neither the wake
                        # word nor the speaker verifier, and it re-arms each
                        # time. So a television that keeps producing speech
                        # inside the window can chain turns indefinitely after
                        # one legitimate wake.
                        #
                        # Decided, not missed. A cap would end a real
                        # conversation mid-sentence at an arbitrary number,
                        # which is the failure people notice; the chaining
                        # case needs a room with a television in it and a
                        # permission level that can act. The window length,
                        # conversation mode itself, and the permission level
                        # are all settings, which is where that trade-off
                        # belongs.
                        follow_up = self.arm_follow_up() and not (
                            said is not None and said.command.ends)
                        # Talked over: stopped like any interrupt, so no
                        # follow-up window -- but the person is mid-sentence,
                        # and what they are saying is the next turn.
                        barged = self.take_barge()
                        woke = self.take_wake()
                    else:
                        follow_up = False
                    print()

                utt = None
                if barged is not None:
                    # Straight into a capture, seeded with the start of what
                    # was said over the reply; the rest is still in the queue,
                    # because deafen() kept it. No wake word: barge-in already
                    # decided this was the person talking, and making them say
                    # it again to finish their sentence is what "interrupt"
                    # does not mean. Not the verifier either, for the same
                    # reason a follow-up skips it -- the reply that was talked
                    # over came from a turn that passed it.
                    phase, buf, cap = "capture", b"", self.pipe.new_capture()
                    utt = self.pipe.new_utterance()
                    self._interrupt.clear()     # see the wake branch
                    self.prime_agent()
                    self._deaf_until = 0.0
                    for early in barged:
                        buf += early
                        self.hear(cap, utt, early, self.voiced(frame_db(early)))
                    woke_at = last_voice = spoke_at = time.time()
                    # Already heard: the lead-in timer is for somebody who
                    # has not started, and this person has. Silence from here
                    # endpoints the turn as usual -- so a bare "stop" is a
                    # short turn that is_stop_command() then discards.
                    heard = True
                    active_lead_in = self.pipe.lead_in_ms
                    capture_kind = "barge"
                    last = _empty_turn()
                    shown_partial = ""
                    print(f"  {GRN}● go on{OFF}  {DIM}(talked over the reply"
                          f" — listening){OFF}", flush=True)
                    self.state.publish("capture", **last)
                    continue
                if woke:
                    # The wake word stopped the turn, so it opens the next
                    # one, exactly as it would from idle: a chime, and the
                    # lead-in to start talking. What followed it is still in
                    # the queue, because deafen() kept it -- "computer,
                    # actually make it Tuesday" -- and a bare wake word is a
                    # stop: the lead-in runs out on silence.
                    phase, buf, cap = "capture", b"", self.pipe.new_capture()
                    utt = self.pipe.new_utterance()
                    self._interrupt.clear()     # see the wake branch
                    self.prime_agent()
                    self._deaf_until = 0.0
                    # Silent inside the open microphone, which was
                    # listening for it anyway (phase M2, bug J).
                    quiet = self.listening_for(self._main)
                    if quiet:
                        print(f"  {DIM}chime: wake not played ({quiet} "
                              f"was already listening){OFF}", flush=True)
                    else:
                        self.chime("wake", "the wake word stopped the reply")
                    woke_at = last_voice = spoke_at = time.time()
                    heard = False
                    active_lead_in = self.pipe.lead_in_ms
                    capture_kind = "wake"
                    last = _empty_turn()
                    shown_partial = ""
                    self.state.publish("capture", **last)
                    continue
                if follow_up and self.listening:
                    phase, buf, cap = "capture", b"", self.pipe.new_capture()
                    utt = self.pipe.new_utterance()
                    self._interrupt.clear()     # see the wake branch
                    # Usually a no-op: the agent that just answered is still
                    # running. It matters after a stop or a failed turn, which
                    # leave nothing running.
                    self.prime_agent()
                    woke_at = last_voice = spoke_at = time.time()
                    heard = False
                    active_lead_in = self.pipe.follow_up_ms
                    capture_kind = "followup"
                    if self.open_mic is self._main:
                        capture_kind = "open"
                        active_lead_in = max(active_lead_in, self.open_mic_left_ms())
                    print(f"  {CYA}● still listening{OFF}  {DIM}"
                          f"({active_lead_in / 1000:.0f}s — or say the wake word again)"
                          f"{OFF}", flush=True)
                    self.state.publish("followup", window=capture_kind, **last)
                    self.refresh()
                    continue

                phase = "wake"
                self._publish(**last)
                self.refresh()
        return 0


def run_simulated(pipe: Pipeline, speaker: Speaker | None, wav: Path,
                  daemon: "Daemon | None" = None) -> int:
    with wave.open(str(wav)) as w:
        pcm = w.readframes(w.getnframes())
    print(f"\n  {DIM}simulating: {wav.name} ({len(pcm) / 32000:.1f}s)"
          f" — no wake phrase, capturing the whole clip{OFF}\n")
    cap = pipe.new_capture()
    # In bytes here, because `pcm` is bytes: CHUNK is a frame count, and
    # int16 mono is two bytes a frame. Slicing by CHUNK fed 100ms blocks to
    # a recogniser that sees 200ms blocks live, so a simulation was not
    # reproducing what the daemon does.
    step = CHUNK * 2
    for off in range(0, len(pcm), step):
        if cap is not None and not cap.AcceptWaveform(pcm[off:off + step]):
            p = json.loads(cap.PartialResult()).get("partial", "")
            if p:
                print(f"{cursor_home()}  {DIM}{p[:100]}{OFF}",
                      end="", flush=True)
    text, ms = pipe.transcribe(pcm)
    print(f"{cursor_home(120)}  {BLD}{safe_for_terminal(text)}{OFF}")
    print(f"  {DIM}whisper {ms:.0f}ms{OFF}")
    if text and daemon is not None:
        daemon.answer(text, {"transcript": text, "ms": round(ms), "audio_s": 0.0})
    elif text and speaker:
        print(f"  {DIM}spoke {speaker.say(text):.1f}s{OFF}")
    return 0


@contextlib.contextmanager
def sigterm_deferred():
    """Hold a SIGTERM until the block ends, then stop as it would have.

    Python raises a signal handler's exception at whatever line the main
    thread is on. Inside a native library's import, that can leave the
    library half set up with its threads running; see main(). Masking the
    signal does not help, because Python takes it on another thread and
    still raises in the main one, so the handler itself is swapped for one
    that only remembers.
    """
    held: list[int] = []
    old = signal.signal(signal.SIGTERM, lambda signum, _frame: held.append(signum))
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, old)
        if held:
            raise SystemExit(0)


def forget_chat_grants() -> int:
    """Drop every "allow everything in this chat" left from a previous run.

    A grant is scoped to one conversation already, but a restarted service is
    a natural line to draw under them: whoever allowed a conversation
    wholesale did it for the session in front of them, not for one resumed
    after a restart. Returns how many went."""
    gone = 0
    for f in (RUNTIME_DIR / "grants").glob("*"):
        try:
            f.unlink()
            gone += 1
        except OSError:
            pass
    return gone


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--whisper", default=None, help="override the configured model")
    ap.add_argument("--device", type=int, default=None)
    ap.add_argument("--no-speak", action="store_true")
    ap.add_argument("--no-agent", action="store_true",
                    help="echo the transcript instead of asking an agent")
    ap.add_argument("--simulate", type=Path)
    args = ap.parse_args()

    cfg = Config()
    print(f"  {DIM}knobs: {cfg.source} · build {build_id()}{OFF}")
    forget_chat_grants()
    # No agent has a session after a restart, so none is in a saved chat.
    try:
        ChatStore().forget_current()
    except OSError:
        pass

    # Writing new files with the right mode does nothing for the ones already
    # there. Somebody who trained a verifier while these directories were
    # 0755 still has those recordings and that model readable by every local
    # account, and an upgrade that quietly fixed only new files would leave
    # the old ones exposed and say nothing. Said out loud, because a silent
    # repair cannot be told from no repair.
    repaired = harden_private_trees()
    if repaired:
        print(f"  {YEL}tightened {len(repaired)} voice recording(s) or "
              f"model(s) that other local accounts could read{OFF}")
    pipe = Pipeline(cfg, args.whisper)

    speaker = None
    if cfg.get_bool("speakReplies") and not args.no_speak:
        try:
            speaker = Speaker(cfg.get_str("voice"))
            if speaker.substituted_for:
                print(f"  {YEL}the voice {speaker.substituted_for} is not "
                      f"downloaded; speaking as {speaker.name}{OFF}")
        except Exception as e:
            print(f"  {YEL}tts unavailable: {e}{OFF}")

    # The agent folders, made and filled from the old instructions settings
    # before any agent is built (merged plan, Phase 10). Idempotent, never
    # writes shell.json, and never stops the daemon: an agent with no folder
    # is told the old setting, as before.
    import agentfs
    try:
        report = agentfs.migrate(cfg, settings_read=agentfs.settings_were_read(cfg))
        # Only what changed or went wrong: on every start after the first,
        # nothing.
        for line in agentfs.migration_lines(report, changes_only=True):
            print(f"  {DIM}agent folders: {line}{OFF}")
    except Exception as e:
        print(f"  {YEL}agent folders: not migrated ({type(e).__name__}: {e}); "
              f"agents are told the old instructions settings{OFF}")

    agent = None
    if not args.no_agent:
        # Deliberately the same resolution the run loop uses, which is why
        # the name comes from endpoint_spec rather than being assumed:
        # `cfg.level_for(omarchy_default())` here against
        # `cfg.level_for("endpoint")` there meant the first turn after startup
        # could run at a different permission level from every turn after it.
        url = cfg.get_str("endpointUrl").strip()
        model = cfg.get_str("endpointModel").strip()
        spec = ({"url": url, "model": model, "key": endpoint_key(_host(url)),
                 "is_agent": cfg.get_bool("endpointIsAgent")}
                if url and model else None)
        which = main_program(cfg.get_str("mainProgram"))
        level = cfg.level_for("endpoint" if spec else which)
        agent = load_adapter(ask_permission=level != "trusted", level=level,
                             cwd=str(project_dir(cfg.get_str("projectDir"))),
                             endpoint=spec,
                             name=None if spec else which,
                             model=None if spec else cfg.model_for(which),
                             effort=None if spec else cfg.effort_for(which),
                             instructions=agentfs.instructions_for(
                                 "", cfg["agentInstructions"]))
        if agent is None:
            print(f"  {YEL}no agent: {explain_agent(which)}"
                  f"; echoing instead{OFF}")

    # systemd stops the service with SIGTERM, whose default disposition
    # skips `finally`: the pidfile below was never removed, and the Agents
    # panel was left saying whatever the agents were doing at the moment of
    # the stop ("Listening to you") instead of Off. A stop is a normal
    # unwind, the same as the Ctrl-C a terminal run already gets.
    def _stopped(signum, _frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _stopped)
    # PortAudio starts when sounddevice is first imported (about 1.4s here),
    # and opens a JACK client through PipeWire as it does. A stop landing in
    # that import raised SystemExit inside it, after PortAudio was up and
    # before sounddevice registered the exit handler that shuts it down; the
    # JACK thread then ran into code unloaded at exit, and the daemon died
    # with SIGSEGV and a core dump (seen once, live, on a restart during
    # startup; reproduced 12 of 12 timed into the import, 0 of 12 with this).
    # So the first import happens here, with a stop held until it is done.
    with sigterm_deferred():
        try:
            import sounddevice  # noqa: F401
        except Exception:
            pass        # no audio stack: run() says so where it is needed

    state = StateFile()
    panel = None
    try:
        daemon = Daemon(cfg, pipe, state, speaker, agent)
        if args.simulate:
            return run_simulated(pipe, speaker, args.simulate, daemon)
        # Not under --simulate: a simulated run is not an agent anybody can
        # talk to, and must not appear in the panel as one.
        panel = daemon.panel = AgentsPanel(enabled=lambda: cfg.get_bool("agentsPanel"))
        # Phase M7: the approval cards and the socket their answers come back
        # on. Before any agent can ask; a lock is read from the daemon's own
        # flag, so a card cannot be answered over the lock screen.
        import cards
        daemon.cards = cards.start_desk(is_locked=lambda: daemon.locked,
                                        locked_now=session_locked)
        # Only for the live loop: a simulated turn has no room to chime into.
        # Built whether or not the setting is on, because it can be switched
        # on while running; rendering the three sounds costs a few ms.
        daemon.chimes = Chimes()
        return daemon.run(args.device)
    except KeyboardInterrupt:
        print(f"\n  {DIM}stopped{OFF}")
        return 0
    finally:
        state.clear()
        if panel is not None:
            panel.stopped()
        # The unit keeps its runtime directory across restarts, so a pidfile
        # left behind here is a pid some unrelated process will eventually be
        # given -- and `agentvoice mic` sends SIGUSR1 to whatever it names,
        # whose default action is to terminate.
        (RUNTIME_DIR / "pid").unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
