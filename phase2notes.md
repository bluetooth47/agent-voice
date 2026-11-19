# Phase 2 (plan.md Phase B): what changed

Written 2026-11-17. Branch `phase-b`, cut from `dev` at af2fee1, so it
carries Phase A too. Commit e5782fe, pushed to `fork/phase-b` only. Not
installed yet, not merged.

`./bin/agentvoice-check`: green, 1302 tests (was 1279).

## 10. Adaptive microphone gate

- **Gate follows the room** (`adaptiveGate`, default **off**) on the
  Listening page, Microphone group. With it on, the gate is the room's
  noise floor plus **Margin above the room** (`gateMarginDb`, 10 dB,
  3–25), and the fixed gate knob becomes "Fixed gate (until it has heard
  the room)". A live line shows "Room −NN dBFS · gate −NN dBFS".
- The floor (`daemon/noise_floor.py`) is the median of the last 30s of
  frames. It's fed in the wake phase only: never in a capture, never while
  an agent speaks or a chime sounds, never in the deaf window. It rises
  0.5 dB/s, falls 3 dB/s, the gate stays between −55 and −25 dBFS, and the
  fixed gate holds for the first 3s. Switching it off forgets the room.
- The wake word's own checks (second-check bursts, Vosk grammar, the wake
  test's tries) use a gate 6 dB lower (`WAKE_SLACK_DB`). Without that,
  wakes beside a TV fell from 11 to 8 of 12.
- The daemon publishes `gate_db` and `floor_db`. The meters on the
  Listening page, the Overview and the bar popup draw the live gate when
  it's on.
- Settings in all three places: manifest, `runtime.DEFAULTS` + TOML
  (`[audio] adaptive_gate`, `gate_margin_db`), and the page.

Measured (FINDINGS §27, `bench/gate_bench.py`, synthetic rooms):

| room | fixed: turns on time / late / held, wakes | adaptive |
|---|---|---|
| quiet | 15/0/0, 12/12 | 15/0/0, 12/12 |
| fan | 15/0/0, 11/12 | 15/0/0, 12/12 |
| loud fan | 0/2/13, 1/12 | 15/0/0, 9/12 |
| music | 5/10/0, 9/12 | 15/0/0, 10/12 |
| TV | 12/3/0, 10/12 | 15/0/0, 10/12 |
| people talking | 4/6/5, 8/12 | 15/0/0, 10/12 |

No turns cut off, no false wakes (0/18 everywhere). Two designs were tried
and dropped on the numbers: a 10th-percentile floor (held every turn open
beside a TV), and one gate for both turns and wakes (lost wakes).

## 6. Accurate live transcript

- A fourth choice for **Live transcript while you speak** (Voice page):
  **Accurate**. Vosk's rough text appears as you talk; at every pause the
  part Whisper has read is replaced by Whisper's text. Loads Vosk like "On".
- How: `eager.Utterance` records every piece it sends and
  `whisper_so_far()` returns Whisper's text and how far it reaches;
  `eager.LiveText` cuts Vosk's text into segments at the same pauses;
  `Daemon.hear()` feeds both and returns what to show. All three places a
  capture is fed go through `hear()`.
- No flicker: a short piece thrown away to be heard again as part of a
  longer one keeps its text on screen until the longer one is done, so it
  never falls back to Vosk's text. Words Vosk makes of the silence after the
  last pause are hidden.

Measured (`bench/live_text_bench.py`, real Vosk + Whisper base.en, real
time): 0 fallbacks in 12 requests, swap 0.78s median (max 0.98s) after a
pause, last text on screen = transcript sent 12/12.

## Not done / to do

1. **Install and restart the shell.** QML changed. `install.sh --yes` ends
   any voice turn.
2. **QML preview not rendered:** the screen was locked the whole time
   (grim hangs then). qmllint passed in the check.
3. **Live checklist:**
   - Listening → switch on "Gate follows the room". After ~3s the line
     shows the room and the gate, and the red line on the meter moves to it.
   - Turn a fan or music on: the gate climbs over a minute or so, and a
     request still ends about a second after you stop.
   - Wake "Theo" with it on, in a quiet room and with music.
   - Voice → Live transcript "Accurate": say a long request with pauses;
     the rough words turn into Whisper's at each pause and the last text
     is what was sent.
4. Then decide whether `adaptiveGate` should default to on, and merge
   `dev` → `phase-b` → `main`.

`daemon/adapters/claude_code.py` (`--chrome`) is still uncommitted.

## Later: the crash on restart (39de35f)

After installing, a restart during startup killed the old daemon with
SIGSEGV and a core dump (the only crash in 52 stops over two weeks). The
backtrace was PipeWire's JACK thread (`libjack` via PortAudio) jumping into
unloaded code while Python exited. Cause: a SIGTERM landing inside the
first `import sounddevice` (~1.4s, PortAudio starting) raised SystemExit
before sounddevice registered the handler that shuts PortAudio down.
Reproduced 12/12 with the stop timed into that import, 0/12 with the fix:
`main()` now does that import first under `sigterm_deferred()`, which holds
the stop until the import is done. On the real service: 9 restarts timed
into startup, 0 core dumps. Check green, 1304 tests.
