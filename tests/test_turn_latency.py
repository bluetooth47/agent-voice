"""bench/turn_latency.py reads the journal, so it must never repeat speech.

The Phase 8 latency baseline is read out of the daemon's structural journal
lines. With `logSpeech` on, transcripts reach the journal too, and a first
version of the parser took any `for <word>` it found as an agent name and
printed it. These replay synthetic journal lines (no journal is read) to pin
down that only announced names come out, which turn belongs to whom, and
which lines are not a spoken-latency sample at all.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))

import turn_latency as tl  # noqa: E402

START = [
    "  knobs: shell.json[duaneoca.agentvoice] · build 0.2.0 (abc1234)",
    '  listening for "theo"   lead-in 6500ms · trailing 1600ms',
    "  agent: claude · voice: ryan-high   (ctrl-c to stop)",
    "  agent “Nova”: claude · haiku · low effort · ask",
    "  agent “Wren”: codex · gpt-test · medium effort · trusted",
]


def heard(total=4.0, adapter="claude warm"):
    return (f"  heard → spoke in {total}s  (pause 1.0s · whisper 0.1s · "
            f"{adapter} 2.0s · first sentence 0.2s · voice 0.7s)")


def run(lines, step=1.0):
    return list(tl.turns([(i * step, line) for i, line in enumerate(lines)]))


def test_a_transcript_in_the_journal_is_never_taken_for_a_name():
    rows = run(START + [
        "  ● wake theo  go ahead (6.5s to start)",
        "  you: remind me what I said for PrivateMarker anything",
        "  ● still listening  (3s for PrivateMarker anything — or say a name)",
        "  3.0s audio, whisper 800ms, 0ms waited",
        heard(),
        "  ● still listening  (7s for PrivateMarker — or say a name)",
    ])
    assert len(rows) == 1
    assert "privatemarker" not in repr(rows).lower()
    assert rows[0]["agent"] == "?"


def test_the_follow_up_line_after_a_reply_names_who_answered():
    rows = run(START + [
        "  ● wake theo  go ahead (6.5s to start)",
        "  3.0s audio, whisper 800ms, 0ms waited",
        heard(),
        "  ● still listening  (7s for Nova — or say a name)",
    ])
    assert [r["agent"] for r in rows] == ["Nova"]


def test_an_adapter_that_disagrees_with_the_agent_is_unattributed():
    rows = run(START + [
        "  ● wake wren  go ahead (6.5s to start)",
        "  3.0s audio, whisper 800ms, 0ms waited",
        heard(adapter="claude warm"),   # Wren is Codex
    ])
    assert rows[0]["agent"] == "?"


def test_a_reply_shown_but_not_spoken_is_not_a_sample():
    rows = run(START + [
        "  ● wake theo  go ahead (6.5s to start)",
        "  heard → showed in 3.0s  (pause 1.0s · whisper 0.1s · claude warm 1.9s)",
    ])
    assert rows == []


def test_a_discarded_wake_does_not_time_a_later_turn():
    rows = run(START + [
        "  ● wake theo  go ahead (6.5s to start)",
        "  (nothing heard)",
        "  ● open mic  (Theo; 10 min after the last thing said)",
        "  3.0s audio, whisper 800ms, 0ms waited",
        heard(),
    ])
    assert rows[0]["wake_to_word"] is None


def test_wake_to_word_is_derived_from_the_transcription_line():
    rows = run(START + [
        "  ● wake theo  go ahead (6.5s to start)",       # t = 5
        "  3.0s audio, whisper 800ms, 0ms waited",      # t = 6
        heard(total=4.0),                                # first word at 6+4-1-0.1
    ])
    assert rows[0]["agent"] == "Theo"
    assert rows[0]["wake_to_word"] == round(6 + 4.0 - 1.0 - 0.1 - 5, 2)


def test_a_nameless_wake_is_the_main_agent_only_when_it_is_alone():
    alone = START[:3] + ["  ● wake  go ahead (5.0s to start)",
                         "  2.0s audio, whisper 500ms, 0ms waited", heard()]
    crowd = START + ["  ● wake  go ahead (5.0s to start)",
                     "  2.0s audio, whisper 500ms, 0ms waited", heard()]
    assert run(alone)[0]["agent"] == "Theo"
    assert run(crowd)[0]["agent"] == "?"


def test_a_reply_shaped_like_an_announcement_adds_no_name():
    rows = run(START + [f"  filler {i}" for i in range(40)] + [
        "  agent “PrivateMarker”: claude · haiku · low effort · ask",
        "  ● wake theo  go ahead (6.5s to start)",
        "  3.0s audio, whisper 800ms, 0ms waited",
        heard(),
        "  ● still listening  (7s for PrivateMarker — or say a name)",
    ])
    assert "privatemarker" not in repr(rows).lower()
    assert rows[0]["agent"] == "?"


def test_a_malformed_number_is_not_a_sample_and_does_not_crash():
    rows = run(START + [
        "  heard → spoke in 1.2.3s  (pause 1.0s · claude warm 2.0s)",
    ])
    assert rows == []


def test_the_wake_figure_the_daemon_prints_is_taken_as_said():
    """Master plan M21: a turn a wake word opened ends its latency line with
    "wake → spoke in Ns", from the daemon's own timestamps. The line still
    parses, and that figure wins over the estimate from journal times."""
    rows = run(START + [
        "  ● wake theo  go ahead (6.5s to start)",
        "  3.0s audio, whisper 800ms, 0ms waited",
        heard() + "  wake → spoke in 7.3s",
    ])
    assert len(rows) == 1 and rows[0]["end_to_word"] == 4.0
    assert rows[0]["wake_to_word"] == 7.3
