# Phase 1 (plan.md Phase A): what changed

Written 2026-11-17. Branch `dev`, cut from `voice-latency-and-conversation`
at 919c4c4, pushed to `fork/dev` only (never origin). Installed as build
af2fee1 with the shell restarted. Not merged to `main` yet.

`./bin/agentvoice-check`: green, 1279 tests (was 1214).

## Commits

| commit | what |
|---|---|
| 5d6392a | Left click on the bar icon always opens the popup (item 8) |
| 846d43a | On/off switch for each extra agent (item 7a) |
| 238d51a | Wake word Advanced section on the Listening page (item 9, part 1) |
| 62207a8 | Test my wake word: count wakes instead of answering them (item 9, part 2) |
| af2fee1 | Fixes after the first live try: wake tests that show up, an automatic test, second-check controls, instant "full stop" |

---

## 8. Bar icon click

- A left click always opens the popup, even during a turn. It used to stop
  the turn, so clicking to see what it was doing ended it.
- Tooltip no longer says "click to stop". Right click (mute), middle click
  (service), "full stop" and the wake word are unchanged.
- Display page shortcut list updated.
- Files: `Panel.qml`, `pages/DisplayPage.qml`, `tests/test_states.py`.

## 7a. Turn an agent off without deleting it

- `"enabled": false` on a `voiceAgents` entry. Missing or any other value
  means on, so existing lists don't change.
- When off: its name leaves the wake grammar, nothing routes to it, there's
  no popup chip and no Agents panel record, and its permission hook answers
  "ask". The card stays in Settings, dimmed, with "switched off" and every
  setting kept.
- An off agent's name stays taken (no second agent can claim it), and it
  counts toward the 8-agent ceiling.
- Switched off mid-turn: the turn is stopped at once, and the agent is
  removed when its thread ends. A deleted agent still finishes its turn, as
  before.
- The main card has no switch and says why.
- Code: `Config.agents()` / `Config.disabled_agents()` in `daemon/runtime.py`,
  `reconcile_crew()` in `daemon/wake_listen.py`, `ui/AgentCard.qml`
  (`switchedOff`), `pages/AgentsPage.qml`, `pages/OverviewPage.qml`,
  `Panel.qml` (chips filter), `Settings.qml` (tone).
- Tests in `tests/test_crew.py`. The "stops its turn" test was
  mutation-checked: it goes red when the stop is removed.

## 9. Wake word Advanced section

A folded **ADVANCED** group on the Listening page (Show / Hide). Moved into
it: the engine thresholds, the second-check switch and grammar confidence.
The engine choice, mic gate and verifier stay where they were. The time to
start speaking (`leadInMs`) stays on the Conversation page, because it's
part of the presets there.

New settings (each in manifest, `runtime.DEFAULTS` + TOML alias, and a
control with a reset):

| setting | default | what |
|---|---|---|
| `shortNameBoostPct` | 150 | sherpa boost for names of ≤3 sounds (was `SHORT_BOOST` 1.5), 50–300 |
| `crossCheckMinMs` | 300 | shortest burst the second check looks at, 100–1000 |
| `crossCheckMaxMs` | 2600 | longest burst, 1000–5000; minimum is kept below maximum |
| `wakeAlsoSounds` | `{"theo": ["TH IY1 AH0"]}` | per word, other ways it's said: lexicon words (lower case) or ARPAbet phones (capitals). Was `ALT_PHONES` |
| `crossCheckEngines` | `both` | who votes: `both` (Vosk + Whisper agree), `whisper`, `vosk` |
| `crossCheckTrailingWords` | 3 | words allowed after the name, 0–6 (was fixed at 3) |
| `crossCheckWhisperHint` | true | prompt Whisper with the agents' names |
| `fullStopAnytime` | true | sherpa spots "full stop" in every frame (on the Conversation page) |

- All of these are plain values on the sherpa stream, the burst cutter or
  the Pipeline, so changing one never reloads a model.
- `Config.wake_tuning()` clamps and cleans them. An "also sounds like" entry
  with an unknown word or phone is skipped, with a journal line, never
  raised.
- `whisper` mode skips Vosk and unloads it; `vosk` mode skips Whisper.
- Code: `daemon/runtime.py`, `daemon/wake_listen.py` (`sherpa_keywords`,
  `SherpaWake.alternatives/listen_for`, `_sherpa_listen`, `_second_check`,
  `_needs_vosk`), `daemon/crosscheck.py` (`decide` modes, `Bursts` window),
  `pages/ListeningPage.qml`, `Settings.qml` (`crossCheckOptions`),
  `README.md`.

### Test my wake word

Two modes, chosen with a Manual / Automatic switch:

- **Manual** (`agentvoice wake-test start|stop`): for ten wakes or 90s, a
  wake is counted instead of answered. Shows tries, hits, rate, how each was
  caught (spotter / second check / openWakeWord / Vosk), near misses (reasons
  only, never words), and the loudest frame against the gate. Code:
  `daemon/wake_test.py`, `Daemon.apply_wake_test_command` / `wake_testing`.
  Results go to `$XDG_RUNTIME_DIR/agentvoice/wake-test.json` (0600).
- **Automatic** (`agentvoice wake-test auto|auto-stop`): `daemon/wake_auto.py`
  in its own process. Every installed Piper voice says each name (alone and
  after "hey", two loudnesses), "full stop", and 13 must-not-wake clips,
  straight into the same engines. No mic, no speakers. About 1.5 minutes.
  Results go to `wake-auto.json`.

Bug found on the first live try: the page showed nothing because the daemon
deleted `wake-test.json` at start, and the page's file watcher never fires
for a file created later. Now the file always exists (`{"status": ""}`
when idle), and the overlay re-reads both files every second while open.

### "Full stop" is instant

Before, it only worked after the wake word, a full capture, the trailing
pause and Whisper, and not at all while an agent was thinking. Now sherpa
listens for "full stop" as its own keyword. When it's heard, every agent
stops and no capture opens: in the run loop, in the thinking-time watcher,
and ignored by the wake test. It still can't work while an agent is
speaking on speakers, because the mic is ignored then; on a headset, talking
over it already stops it. sherpa-onnx engine only.

## Measured (bench/FINDINGS.md §26)

Automatic test with the live settings (sherpa 20%, boost 150%, both
engines), 5 Piper voices, 100 clips, 92s on the i7-1185G7:

- Theo 15/20 (spotter 3, second check 12)
- Sora 16/20 (spotter 8, second check 8)
- Full stop 8/10 (all spotter)
- False wakes 0 of 50

Synthetic voices: compare settings with these, not your own rate. The first
live manual test was 0 tries / 0 wakes: the page part is fixed, but the
0 tries is unexplained. The test now reports the loudest level against
the gate, so the next run will show whether that's the cause.

## Housekeeping

- My `git add -A daemon` once swept in the uncommitted `--chrome` change in
  `daemon/adapters/claude_code.py`. I took it out of the commit and
  force-pushed `fork/dev` (with your OK). It's still uncommitted in the
  working tree, and the installed build includes it (hence "-dirty").
- `plan.md` and these notes are untracked.

## Still to do for Phase A

1. Live checklist:
   - click the bar icon mid-reply: the popup opens and it keeps talking;
   - switch Sora off: "Sora" does nothing and its chip is gone; switch it
     back on and it works again;
   - manual wake test with "Theo" ×10;
   - automatic wake test;
   - "full stop" while it's thinking, with no wake word.
2. Add the live manual-test numbers to FINDINGS §26.
3. Merge `dev` → `main` and push `main` to the fork.
