"""Rendering the next sentence while this one plays.

Piper renders a whole sentence before it gives back any audio, and the speaker
used to render and play by turns: sentence two was not started until sentence
one had finished playing. With ryan-high, about twice realtime on this
machine, that was one to three and a half seconds of silence between every
sentence, and the text of each sentence sat on screen for as long as its
render took before a word was heard.

Driven with a fake PortAudio, numpy and Piper, like test_speaker_stop, so it
runs on the bare CI runner.
"""
from __future__ import annotations

import sys
import threading
import time
import types

from adapters.base import Chunk


class FakeStream:
    def __init__(self, log, **kw):
        self.log = log
        self.writes = 0
        log.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def start(self):
        pass

    def stop(self):
        pass

    def close(self):
        pass

    #: Seconds a write blocks, as PortAudio's does while audio plays.
    pace = 0.0

    def write(self, pcm):
        time.sleep(self.pace)
        self.writes += 1

    def abort(self):
        pass


class FakeVoice:
    def __init__(self, seconds=0.2, rate=22050, delay=0.0):
        self.config = types.SimpleNamespace(sample_rate=rate)
        self._bytes = b"\x00\x01" * int(seconds * rate)
        self.rendered: list[str] = []
        self.delay = delay

    def synthesize(self, sentence):
        time.sleep(self.delay)
        self.rendered.append(sentence)
        yield types.SimpleNamespace(audio_int16_bytes=self._bytes)


def _speaker(monkeypatch, **voice):
    import runtime

    streams: list[FakeStream] = []
    fake_sd = types.ModuleType("sounddevice")
    fake_sd.OutputStream = lambda **kw: FakeStream(streams, **kw)
    fake_np = types.ModuleType("numpy")
    fake_np.int16 = "int16"
    fake_np.frombuffer = lambda b, dtype=None: memoryview(b).cast("h")
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)
    monkeypatch.setitem(sys.modules, "numpy", fake_np)

    sp = runtime.Speaker.__new__(runtime.Speaker)
    sp._voice = FakeVoice(**voice)
    sp._rate = 22050
    sp._stop = threading.Event()
    return sp, streams


def _wait_for(cond, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.005)
    return False


# --- the splits -------------------------------------------------------------

def test_a_long_first_sentence_has_its_opening_clause_rendered_alone():
    from speech_text import split_head
    head, rest = split_head("Sure, I looked at the logs, and the daemon restarted "
                            "twice this morning because of the voice swap.")
    assert head == "Sure, I looked at the logs,"
    assert rest.startswith("and the daemon")


def test_short_sentences_and_tiny_heads_are_not_cut():
    from speech_text import split_head
    assert split_head("Done.") == ["Done."]
    # "Sure," is a word: it renders in no time and a cut only adds a join.
    assert split_head("Sure, that is fine.") == ["Sure, that is fine."]
    # No clause break: never cut mid-phrase.
    one = "The weather today is sunny with a high of twelve degrees and light wind."
    assert split_head(one) == [one]


def test_code_is_never_cut():
    from speech_text import split_head
    s = "Run `git log --oneline, --graph` to see it, and then check the output twice."
    assert split_head(s) == [s]


def test_a_very_long_sentence_is_cut_at_clauses_under_the_limit():
    from speech_text import LONG_CHARS, split_long
    s = ", ".join(["this clause has several words in it"] * 12) + "."
    pieces = split_long(s)
    assert len(pieces) > 1
    assert all(len(p) <= LONG_CHARS for p in pieces)
    assert " ".join(pieces) == s


# --- the speaker ------------------------------------------------------------

def test_a_prefetched_sentence_is_rendered_before_it_is_asked_for(monkeypatch):
    sp, _ = _speaker(monkeypatch)
    sp.prefetch("The second sentence is here.")
    assert _wait_for(lambda: sp._voice.rendered), "nothing rendered ahead"
    sp.say("The second sentence is here.")
    assert sp._voice.rendered == ["The second sentence is here."], \
        "say() rendered it again instead of playing what was ready"


def test_say_renders_the_next_sentence_while_this_one_plays(monkeypatch):
    """Two sentences in one say(): the second is rendering while the first is
    written, not after."""
    sp, streams = _speaker(monkeypatch, seconds=0.5, delay=0.05)
    monkeypatch.setattr(FakeStream, "pace", 0.01)   # 10 slices: 100ms
    seen_while_playing = []

    def watch():
        seen_while_playing.append(len(sp._voice.rendered))
        return False

    sp.say("First sentence goes here. Second sentence goes here too.", watch=watch)
    assert len(sp._voice.rendered) == 2
    # Done before the first sentence's ten slices were: rendered during it.
    assert max(seen_while_playing[:10]) == 2


def test_a_reply_writes_to_one_stream(monkeypatch):
    sp, streams = _speaker(monkeypatch)
    with sp.holding():
        sp.say("One sentence for the reply.")
        sp.say("Another sentence for the reply.")
    assert len(streams) == 1, f"{len(streams)} streams for one reply"


def test_another_thread_never_shares_the_held_stream(monkeypatch):
    """One thread drives PortAudio. A say() from a different thread while a
    reply holds its stream gets a stream of its own."""
    sp, streams = _speaker(monkeypatch)
    with sp.holding():
        sp.say("The reply's own sentence.")
        t = threading.Thread(target=sp.say, args=("Somebody else's line.",))
        t.start()
        t.join()
        sp.say("The reply's next sentence.")
    assert len(streams) == 2


def test_cancel_drops_what_was_rendered_ahead(monkeypatch):
    sp, _ = _speaker(monkeypatch, delay=0.05)
    for i in range(6):
        sp.prefetch(f"Sentence number {i} of a reply that is stopped.")
    sp.cancel()
    sp.say("The next thing said after the stop.")
    assert len(sp._voice.rendered) <= 2, \
        f"it went on rendering a stopped reply: {sp._voice.rendered}"


def test_a_render_that_fails_is_raised_by_say(monkeypatch):
    sp, _ = _speaker(monkeypatch)

    def broken(sentence):
        raise RuntimeError("onnx")
        yield

    sp._voice.synthesize = broken
    try:
        sp.say("Anything at all.")
    except RuntimeError as e:
        assert "onnx" in str(e)
    else:
        raise AssertionError("a failed render was swallowed")


# --- the reply loop ---------------------------------------------------------

def test_the_stream_reader_sees_the_same_sentences_as_the_reply(monkeypatch):
    from adapters.base import sentences
    from wake_listen import Ticker

    parts = ["Hello there, how ", "are you today? I am ", "fine. Thanks."]
    got = []
    t = Ticker(iter([Chunk(text=p) for p in parts]),
               on_sentence=lambda s, first: got.append((s, first)))
    list(t)
    expected = list(sentences(iter([Chunk(text=p) for p in parts])))
    assert [s for s, _ in got] == expected
    assert [f for _, f in got] == [True] + [False] * (len(expected) - 1)


class Agent:
    name = "stub"
    last_start = "warm"

    def __init__(self, *parts):
        self.parts = parts

    def send(self, text, session_id=None):
        for p in self.parts:
            yield Chunk(text=p)

    def cancel(self):
        pass


def test_the_text_goes_up_when_its_sound_does(daemon, monkeypatch):
    """Not before: put up first, the text sat on screen for as long as the
    voice took to render it."""
    playing = []
    published = []

    def say(text, watch=None):
        daemon.speaker.first_audio_at = None
        watch and watch()                       # rendering: nothing out yet
        playing.append(text)
        daemon.speaker.first_audio_at = time.time()
        watch and watch()

    daemon.speaker.say = say
    real = daemon.state.publish

    def publish(state, **kw):
        if state == "speaking":
            published.append((kw.get("reply"), len(playing)))
        return real(state, **kw)

    monkeypatch.setattr(daemon.state, "publish", publish)
    daemon.agent = Agent("The first sentence of it. ", "And the second one here.")
    daemon.answer("hello", {"transcript": "hello"})

    assert published, "the reply never went on screen"
    for reply, sounds in published:
        sentence_count = reply.count(".")
        assert sounds >= sentence_count, \
            f"{reply!r} was on screen before its sound ({sounds} played)"
