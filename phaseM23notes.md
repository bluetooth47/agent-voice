# Phase M23: Listening as a pipeline, and gate speed

Written 2026-11-23, unattended (started by the runner script). Branch
`phase-m23`, cut from `phase-m22` at 47f52a4. Result commit: the notes commit
on top of 071092e, pushed to `fork/phase-m23` only; `dev` fast-forwarded to it
and pushed to `fork`. Model: Claude Opus 5.5 (tier B in the plan, high).

Commits:
- 071092e: the phase;
- then these notes.

**Codex review: bypassed (user decision, 2026-11-22).** Codex was not run, for
review or anything else. In its place I re-read the whole diff before the
commit and ran 13 mutations of the new daemon code, its reader and the page's
presets; what that found is under "Found along the way". Nothing in this phase
has been reviewed by a second model.

Deployed: **yes**, through `bin/agentvoice-deploy --install --wait 120
071092e` (its strict check green) with the daemon idle (state `listening`,
every agent idle (`''`, `sora`, `jarvis-ajc`), no open mic, no journal line in
the five minutes before): "deployed 071092e021d0. The way back:
bin/agentvoice-deploy f0e2340f38ab".

Installed: **yes**: "Build 0.2.0 (071092e), replacing 0.2.0 (f0e2340)". The
daemon (`noise_floor.py`, `runtime.py`, `wake_listen.py`) changed;
`install.sh` did not.

**Nothing about listening changed on this machine.** Neither new key was
written; the shipped rates are the ones the gate always had, and the journal
now says them: "gate follows the room (+10 dB, rises 0.5 dB/s, falls 3.0
dB/s)".

**Shell restart needed** (`pages/ListeningPage.qml`, `KnobRow.qml`). Not run.
Until it is, the running shell shows M22's Listening page: the old boxes, no
stages and no "Adapts" control. The settings work before the restart:
`omarchy bar set duaneoca.agentvoice gateRiseTenths 15` and `gateFallTenths
80` (fast), `2` / `15` (slow), `5` / `30` (normal, as shipped).

A copy of `shell.json` was taken before the deploy
(`~/agentvoice-notes/shell.json.before-M23`, 0600); after the install and the
live checks it was byte-identical. No live check wrote a setting.

`./bin/agentvoice-check`: green on the final tree (exit 0, every line ok).
- **5043 tests** (was 4997; +46), 14 of 14 static checks, "the check wrote
  nothing in the tree: ok". 5 min 49 s.
- **Bare-runner variant: run on the new and changed test files** (`/tmp/ci`
  venv from `requirements-dev.txt`, no numpy, `AGENTVOICE_STRICT=1`):
  `test_gate_speed.py`, `test_noise_floor.py`, `test_no_openwakeword.py`,
  `test_sherpa_wake.py`: 120 passed, 1 skipped. The skip is
  `test_sherpa_wake.py:121`'s `importorskip("numpy")`, the same on the base
  commit. The whole bare suite was not run.
- Box: not run (`install.sh` did not change).

## What was built

**The Listening page as a pipeline** (`pages/ListeningPage.qml`): four
numbered stages drawn with `ui/StageBlock` (built in M1 for exactly this and
used here for the first time), joined by its connector line, each with a
one-line summary beside its title and its own fine-tuning folded under a
`ui/AdvancedSection` (also its first use on a page):

1. **Microphone**: the level meter with the gate drawn on it; **Gate** Fixed /
   Follows the room (`adaptiveGate`, now a two-chip choice instead of a
   switch); the room's live numbers; **Adapts** slow / normal / fast (new, a
   preset over the two rates, shown only while the gate follows the room, with
   what each means in a room, from the bench); the fixed level
   (`micThresholdDb`); **Advanced (3)**: the margin (`gateMarginDb`) and the
   exact rates, read and typed in dB/s; the lock note.
2. **First listener**: Engine (`engine`), the not-installed banners, the
   chosen engine's threshold (`owwThresholdPct` or `sherpaThresholdPct`), the
   wake phrase with its link to the Agents card. **Engine-specific blocks
   appear only for the chosen engine, and only while it is really running**
   (`owwLive`, `sherpaLive`): openWakeWord's block holds the old "Only your
   voice" as **YOUR VOICE** (the verifier card, Train, `useVerifier`) and **A
   PHRASE OF YOUR OWN**; sherpa-onnx's holds `shortNameBoostPct` and **Also
   sounds like (N)** (`wakeAlsoSounds`), folded.
3. **Second check**: **Who votes** (`crossCheckEngines`); **Advanced (4)**:
   the window (`crossCheckMinMs`, `crossCheckMaxMs`), words after the name
   (`crossCheckTrailingWords`), the Whisper hint (`crossCheckWhisperHint`).
   **Greyed with the reason** (`SettingRow.disabledReason`, not hidden) where
   there is none: openWakeWord, Vosk, an engine not installed (Vosk standing
   in), or First only chosen below ("Off: …"); its Advanced is folded away
   then.
4. **Decision**: M22's **When a wake counts** selector, its refused and
   held-closed lines (unchanged, moved here as the plan said); Vosk's
   **Grammar confidence** (`wakeConfidencePct`, Vosk only: on the other
   engines it does nothing); and **"Today: 7 wakes (2 confirmed by the second
   check) · 3 rejected by the second check · 1 held, then dropped"**, from
   `agentvoice stats --days 1 --json`, read when the page is built, each time
   the overlay opens and when a turn ends (the second check's count only where
   there is one, held and confidence only when not zero; "numbers are off
   (Display)" with `keepStats` off).

**Test my wake word** sits underneath in its own box: it is not a stage, it
runs the whole pipeline. Every Listening key keeps its single home on this
page (`test_settings_pages.py`); `phrase` and `owwModel` stay on the Agents
card, shown with a link.

**Gate speed, the daemon** (`daemon/noise_floor.py`): `NoiseFloor` gains
`rise_db_per_s` and `fall_db_per_s`, plain attributes that `feed()` reads in
place of the module constants, set by `set_rates()` inside `RISE_BOUNDS`
(0.1–3.0 dB/s) and `FALL_BOUNDS` (0.5–10.0); anything that is not a finite
number is the shipped rate. `SPEEDS` holds the page's presets in the settings'
units: slow (2, 15), normal (5, 30, the shipped pair), fast (15, 80).
`Pipeline.apply()` hands the rates to the running floor after the spec check,
like the margin (`_gate_rates(cfg)`, which never raises: a stand-in config or
a reader that fails gives the shipped rates). A new rate changes the next step
and keeps everything the floor has learned; no model is rebuilt. The journal's
start-up line says the rates.

**Settings `gateRiseTenths` (1–30, default 5) and `gateFallTenths` (5–100,
default 30)**: manifest schema and defaults, `runtime.DEFAULTS`,
`TOML_ALIASES` (`[audio] gate_rise_tenths`, `gate_fall_tenths`),
`Config.gate_rates()`: a whole number of tenths (an integer, a float with no
fraction, or ASCII digits from a hand edit), clamped to its bounds; a bool, a
list, a fraction, "abc" and settings that cannot be read give 0.5 and 3.0
dB/s, as Appendix A fixes it. One page writes them: Listening (Adapts writes
both together; the two Advanced knobs write one each).

**`KnobRow.qml`** (shared): `displayDivisor` and `decimals`, so a setting
stored in tenths reads "0.5 dB/s" and is typed as 0.5 (a decimal validator;
the whole-number path, and every existing caller, unchanged).

**Preview**: a new `listening` target (`sherpa`, `oww`, `vosk`, `missing`,
and `-shot` variants that open every Advanced and walk the page), seeded with
fixed stats by `listening.seed.py` into the scratch data folder.

**Measure**: `bench/gate_speed.py` (FINDINGS §56).

**Docs**: README (the page as four stages; Adapts and what each speed
means), CODEBASE (`noise_floor.py`, the page, the key list), FINDINGS §56.

## What was proven, and how

- **Tests** (`tests/test_gate_speed.py`, 46 cases):
  - the floor: the shipped rates by default; each rise and fall rate is
    exactly the most it moves per second; a new rate keeps the window and the
    floor; bounds and nonsense (0, negative, huge, NaN, inf, a string, None, a
    list);
  - **warm-up and the hard limits unchanged at every speed** (the fixed gate
    until three seconds, -55 and -25 dBFS, the wake word's slack);
  - talk for 45% of the window at the fastest rates allowed leaves the floor
    on the room;
  - the presets inside the bounds, ordered, falling faster than rising, and
    normal equal to `DEFAULTS` and to the module constants;
  - **`runtime.Config.gate_rates()`**: 15 raw pairs (whole numbers, clamped
    both ways, hand-edited strings, 15.0, bools, fractions, "abc", None, a
    list, a dict, "²", "1e3", "0x10"); **unreadable settings give today's
    rates**; a stand-in config, a reader that raises and one that returns
    nonsense all keep the shipped rates;
  - **a changed rate reaches the running floor through the real `apply()`
    and a real `runtime.Config`, with no rebuild** (`FakeSherpa.built` stays
    1), the same floor object, and what it learned kept; then a nonsense
    value puts the shipped rates back;
  - slow against fast through the whole pipeline: the same start, a different
    gate 25 s after the room gets louder;
  - **frames are still dropped on lock before the meter**: the real frame loop
    over a scripted microphone, loud frames said behind a lock reach neither
    `learn_room` nor a published `level_db`;
  - the page: both keys in all three places with matching bounds and one
    page; **the page's presets are `noise_floor.SPEEDS`** (parsed from the
    QML); a speed writes both rates and nothing else.
  - Changed: `test_sherpa_wake.py` asserted a group titled "ADVANCED" (now
    each stage's own Advanced), and `test_no_openwakeword.py` asserted the
    verifier card's "Install openWakeWord to enable this" (the card now lives
    in openWakeWord's block, drawn only while it runs; the test now holds
    that, and that no engine switch is offered).
- **Mutations: 13 run, 13 red** (a scratch copy under /tmp, never the clone):
  `feed()` ignoring the rates; `set_rates()` not clamping; `apply()` never
  setting them; `apply()` building a new floor each time; the reader ignoring
  unreadable settings; accepting a bool; not clamping; accepting a fraction;
  `_gate_rates` letting a reader's exception through; the room learned before
  the lock check; the page's fast preset drifting from the daemon's; a speed
  writing one key; the default rise changed.
- **Preview** (`preview.sh`, synthetic mouse events through `TestEvent`, a
  scratch config, state and data folder, the real pointer never moved):
  **`listening` 46 of 46 PASS**:
  - `sherpa` 26: four stages; sherpa-onnx's block and not openWakeWord's;
    the second check live with its Advanced; stage 2's summary; a fixed gate
    shows no speed and no Advanced; Follows the room writes `adaptiveGate`;
    Normal shown and explained; Fast writes 15 and 80; the Advanced rates read
    "1.5 dB/s" and "8.0 dB/s"; Slow writes 2 and 15; a pair that is no preset
    reads "Custom: rises 0.7 dB/s and falls 1.5 dB/s"; Normal writes 5 and
    30; **clicking the rise rate's number opens a box that takes a decimal,
    and typing 1.2 writes 12 tenths**; First only greys the second check with
    "Off: …" and folds its Advanced; Either stage brings it back; the Today
    line from the seeded numbers;
  - `oww` 9: your voice inside openWakeWord's block; no sherpa-onnx block;
    the second check greyed with "openWakeWord has no second check"; no
    Vosk bar; **switching to sherpa-onnx writes the engine and swaps the
    blocks**;
  - `vosk` 5: no engine block, the confidence bar in the Decision stage, the
    second check greyed, no other engine's threshold;
  - `missing` 6: sherpa-onnx chosen and not installed: the banner, "Vosk,
    standing in", stage 2 marked, no sherpa-onnx block, the second check
    greyed with why, Vosk's bar offered.
  The write logs agree with every check.
  **M22's `decision` target 25 of 25** against the moved selector (sherpa 9,
  refused 9, novosk 2, closed 5). The `knob` target ran with no QML error
  after the KnobRow change.
- **Screenshots** (`/tmp/m23`, not committed): 1100×760 dark (`sherpa-shot`,
  six shots down the page), flexoki-light (`oww-shot`, three), 520×720
  (`vosk-shot`; the crop cuts the overlay's right edge, as in M18 to M22), and
  one per clicks run.

## Shared files touched, and where

- `daemon/wake_listen.py` (big shared, 7,794 → 7,815): the `noise_floor`
  import; `_gate_rates()`; `Pipeline.apply()` one line after the margin
  (`self._floor.set_rates(...)`); the journal's gate line. Assignment only, as
  the plan said.
- `KnobRow.qml` (shared root component): `displayDivisor`, `decimals`,
  `display()`, the typed entry.
- `pages/ListeningPage.qml` (957 → 1,267), `daemon/noise_floor.py`,
  `daemon/runtime.py`, `manifest.json`, `tests/test_no_openwakeword.py`,
  `tests/test_sherpa_wake.py`, `README.md`, `CODEBASE.md`,
  `bench/FINDINGS.md`; new `tests/test_gate_speed.py`, `bench/gate_speed.py`,
  `bench/preview/targets/listening.qml`, `listening.seed.py`.
- Not touched: `Settings.qml`, `install.sh`.

## Measured

FINDINGS §56, on the i7-1185G7, `bench/gate_speed.py`: the daemon's own
`NoiseFloor` over synthetic noise, time to settle within 1 dB after a 10 dB
step at -50 dBFS:

| | slow (0.2 / 1.5 dB/s) | normal (0.5 / 3.0) | fast (1.5 / 8.0) |
|---|---|---|---|
| fan, louder | 56.8 s | 31.2 s | 20.2 s |
| fan, quieter | 20.4 s | 17.6 s | 16.0 s |
| music, louder | 48.0 s | 24.0 s | 15.8 s |
| music, quieter | 24.8 s | 24.8 s | 24.8 s |
| 14 s of talk at -26 in a -50 room: gate before → highest | -40.0 → -39.3 | -40.0 → -39.3 | -40.0 → -39.3 |

**The 30 s median sets the first ~15 s whatever the rate**, so the speeds
spread out going louder and barely going quieter, and talk never moves it at
any speed. A second seed gave the same within 0.8 s.

## Different from the plan, and why

- **The fixed level stays beside the meter, not under the stage's
  Advanced.** With the gate fixed (the default, and what most installs run)
  it is the Microphone stage's only control, and the meter is there to set it
  by eye; folded away, a new user would have nothing to set. Its label still
  says "Fixed gate (until it has heard the room)" when the gate follows the
  room. Open issue 3.
- **Vosk's confidence (`wakeConfidencePct`) shows only on Vosk**, in the
  Decision stage as the plan places it: it is read only by the Vosk grammar
  path, so on the other engines it would be a control that does nothing.
- **The second check's who-votes row is greyed, its Advanced hidden**, where
  there is none: the plan's "greyed with the reason", without four greyed
  sliders under it.
- **The verifier card no longer shows on other engines.** It used to say
  "Needs openWakeWord" with a button that switched or installed the engine;
  the plan puts it inside openWakeWord's block. The engine's hint still says
  openWakeWord "can learn your voice". Open issue 4.
- **"Adapts" is three presets plus a custom reading**, not a fourth chip: a
  pair set apart under Advanced shows no chip lit and says the pair.
- **Gate is a two-chip choice**, Fixed / Follows the room, rather than the
  switch it was: the plan writes "gate fixed / dynamic"; same key, same value.
- **Test my wake word moved out of the old Advanced** into its own box under
  the stages.
- **The window was not made a setting**, though it, not the rates, decides
  most of how fast the gate follows (measured). Open issue 2.
- **Codex review bypassed** by the user's decision.

## Found along the way

- **The window dominates speed** (above, and FINDINGS §56). My first guess was
  that "fast" would follow a step in a few seconds; it takes 16–20 s.
- **My first bench gave every speed the same "quieter" time and normal equal
  to fast**: unfiltered pink noise drifts by several dB below 20 Hz, so the
  room's own median wandered past the tolerance. The fan is now pink above
  20 Hz, as a fan's level is.
- **`{ slow: [...] }` as a property value is a binding block in QML**, not an
  object; the preview refused to load until it was `({ ... })`. qmllint did
  not catch it (it only gates missing properties).
- **My re-read**: the page read the rates with a bare `Number()`, so a
  hand-edited `"abc"` would have shown 0.0 dB/s and "custom" while the daemon
  used 0.5; it now reads them the way `Config.gate_rates()` does. And the
  typed-number path in `KnobRow` had no exercise anywhere; the `sherpa`
  preview now types 1.2 and checks 12 tenths were written.
- **The Today line first said "0 rejected by the second check" on Vosk and
  openWakeWord**, which have none; it now shows that count only where there
  is a second check (or where it said no earlier today).
- **Observation, not changed: the live microphone reads -180 dBFS**, which is
  exactly what all-zero frames give (`frame_db`'s floor), before and after the
  deploy, so the adaptive gate sits clamped at -55 and the floor at -99.
  PipeWire's default source (`alsa_input.pci-0000_00_1f.3.analog-stereo`) is
  not muted and is at 100%. Not investigated further (a capture switch below
  PipeWire, a hardware mute, or another device opened by the daemon). If
  nothing wakes at the next stop point, start there: `agentvoice monitor`.

## Not verified

- **The page in the real shell.** It needs `omarchy-restart-shell` (not run).
  Seen only in `preview.sh`. Until the restart the running shell has M22's
  Listening page.
- **Live: switch engines and only that engine's block shows** (the plan's
  check), in the real shell. Driven in the preview only (`oww` → sherpa-onnx).
- **The gate's speed in a real room**: the numbers are synthetic noise through
  the daemon's own floor; no microphone was used, and the live microphone is
  delivering silence (above). Choosing slow or fast on the live daemon was
  not tried (no setting was written).
- **The manual wake test by voice.** Needs the user. The automatic one ran
  twice (below), and is not repeatable (open issue 7).
- **The narrow layout** (below 560 px): the crop cuts the overlay's edge.
- **Typing a rate by keyboard**: the preview sets the box's text and accepts
  it (the preview never takes the keyboard), so the validator's keystroke
  filtering was not driven.
- **The installer box** (`install.sh` did not change).
- **The Codex review** (bypassed, not owed).

## Going back

`bin/agentvoice-deploy f0e2340f38ab` from the clone, `./install.sh --yes`
once the daemon is idle, then `omarchy-restart-shell`. **An M22 build ignores
`gateRiseTenths` and `gateFallTenths` and uses the fixed rates (0.5 and 3.0
dB/s)**, which are also the shipped defaults, so nothing changes unless a
speed was chosen. The keys stay in shell.json if they were written, and M22's
Listening page does not draw them. Nothing else changed shape.

## Open issues, for the next phase

1. **Codex review bypassed** for M23 (user decision, 2026-11-22). M12 stays
   "review owed".
2. **The 30 s window, not the rates, sets most of how fast the gate
   follows** (16–20 s to go quieter at any speed). Make "fast" also shorten
   the window, or add a window setting? A shorter window lets more of a TV or
   a conversation into the floor. Default: not changed (the plan names the
   two rates only), and the page says plainly what each speed does.
3. **The fixed level beside the meter rather than under Advanced** (above).
   Default: beside the meter.
4. **The verifier is now invisible unless openWakeWord is running.** Is the
   lost "switch to openWakeWord to train your voice" offer missed? Default:
   the plan's rule, engine blocks only for the chosen engine.
5. **The presets**: slow 0.2 / 1.5, normal 0.5 / 3.0, fast 1.5 / 8.0 dB/s,
   chosen inside the bounds and measured. Default: as shipped.
6. **The live microphone reads all-zero frames** (above). Default: noted for
   the stop point; nothing changed.
7. **The automatic wake test is not repeatable**: identical seeded clips on
   the same build gave Theo 15 then 18, Sora 17 then 21, with the spotter's
   share moving too. Most likely the sherpa-onnx stream keeping state across
   `reset()` (M22 found this in its bench and gave each clip a fresh stream
   there; `wake_auto.py` still resets) and the second check's 10 s timeout
   under load. A test whose result moves by three wakes in 24 cannot judge
   a change of a few. Default: noted; fix in the phase that next touches the
   wake test (pre-existing).
8. **Carried, still open**: M22's 2–7; M21's 2–7; M20's 2–8; M19's 3–6; M18's
   2–6; M17's 2–7; M16's 2–9; M15's 2–8; M14's 2–7; M13's 2–9; M12's 2–7;
   M11's 1–7; M10's 1–8; M9's 2–7; M8's 2–11; M7's 2–7; M6's 1, 3, 4; M5's 1,
   4–6; M4's 4–13; the Voice library trash icon (M25); M0's small test and
   bench fixes; agy's `carries_session_across`; the runner's sandbox test
   command.

## Live checklist: what was done, what happened

Nothing was said into the microphone and nothing was spoken: no turn was run.
- Before the deploy: state `listening`, every agent idle, no open mic, no
  journal line in five minutes; `shell.json` copied (0600). The real settings
  have the gate following the room (`adaptiveGate: true`, margin 10) and
  neither new key.
- `bin/agentvoice-deploy --install --wait 120 071092e`: strict check green;
  "deployed 071092e021d0. The way back: bin/agentvoice-deploy f0e2340f38ab";
  "QML changed: run omarchy-restart-shell? (not run)"; "Build 0.2.0
  (071092e), replacing 0.2.0 (f0e2340)". Service active.
- The journal after the restart (`-o json`, decoded): "wake: sherpa-onnx @
  0.20 (theo, sora, hazel, full stop) + second check", "wake decision: either
  stage can wake", and **"gate follows the room (+10 dB, rises 0.5 dB/s,
  falls 3.0 dB/s)"**. No error or traceback.
- The installed reader against the real settings (`runtime.Config()` from
  `~/.local/share/agentvoice/app`, the microphone not opened): settings
  readable, **`gate_rates()` = (0.5, 3.0)**, `SPEEDS` as on the page.
- `agentvoice stats --days 1 --json` (what the Decision stage reads):
  `keeping: true`, 0 wakes, the rejection and wake keys the page reads.
- `agentvoice status`: `wake_decision: {mode: either, closed: false}`,
  `level_db -180.0`, `gate_db -55.0`, `floor_db -99.0` (the all-zero input,
  above).
- **A slip: my first `agentvoice wake-test` had no argument**, which is
  `start`, the *manual* test: for 90 s a wake on the live daemon would have
  been counted instead of answered. It timed out by itself with 0 attempts
  (`wake-test.json`: `timeout`, peak -99 dBFS); nothing was answered or
  missed because of it, as nothing could be heard.
- **The automatic wake test** (`agentvoice wake-test auto`: every installed
  voice through the installed engines in its own process, no microphone, no
  speakers), run twice on the same build, settings "threshold 20% · boost
  150% · second check on, both":
  - first run, 114 s: Theo 15/24 (spotter 5, second check 10), Sora 17/24
    (13, 4), Hazel 21/24 (3, 18), full stop 12/12; no false wake in 78;
  - second run, 120 s: **Theo 18/24 (3, 15), Sora 21/24 (9, 12), Hazel 22/24
    (4, 18), full stop 12/12; no false wake in 78**. M22's run was 18, 21 and
    20.
  The clips' noise is seeded and the input identical, so **the test is not
  repeatable run to run**: the spotter's own counts moved (Sora 13 → 9). Not
  this phase's code: the automatic test never calls `learn_room`, so the
  floor never warms and the gate is the fixed one, whatever the rates. Open
  issue 7.
- `shell.json` byte-identical to the copy afterwards. No shell restart.
