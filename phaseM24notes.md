# Phase M24: Conversation page

Written 2026-11-23, unattended (started by the runner script). Branch
`phase-m24`, cut from `phase-m23` at 300f782. Result commit: the notes commit
on top of d4ad068, pushed to `fork/phase-m24` only; `dev` fast-forwarded to it
and pushed to `fork`. Model: Claude Sonnet 5.5 (tier C in the plan, high).

Commits:
- d4ad068: the phase;
- then these notes.

**Codex review: bypassed (user decision, 2026-11-22).** Codex was not run, for
review or anything else. In its place I re-read the whole diff before the
commit and ran 19 mutations of the page's tests; what that found is under
"Found along the way". Nothing in this phase has been reviewed by a second
model.

Deployed: **yes**, through `bin/agentvoice-deploy --install --wait 120 d4ad068`
(its strict check green) with the daemon idle (state `listening`, every agent
idle, `open_mic` empty, no journal error): "deployed d4ad068d3bff. The way
back: bin/agentvoice-deploy 071092e021d0".

Installed: **yes**: "Build 0.2.0 (d4ad068), replacing 0.2.0 (071092e)". One
daemon file changed (`speech_text.py`, a new field in the commands table);
`install.sh` did not. The installed CLI now answers `agentvoice commands
--json` with `mode_positions`.

**Nothing about listening, turns or the open mic changed on this machine.** No
setting was written and no turn was run. `shell.json` is byte-identical to the
copy taken before the deploy (`~/agentvoice-notes/shell.json.before-M24`, 0600).

**Shell restart needed** (`pages/ConversationPage.qml`, `ui/TurnTimeline.qml`,
`Settings.qml`). Not run. Until it is, the running shell shows M23's
Conversation page. Every setting works before the restart.

`./bin/agentvoice-check`: green on the final tree (exit 0, every line ok).
- **5076 tests** (was 5043; +33, all in the new `tests/test_conversation_page.py`;
  two tests in `test_states.py` were rewritten, not added), 14 of 14 static
  checks, "the check wrote nothing in the tree: ok". 5 min 50 s.
- The first full run was **red (2 failed)**: `test_states.py` read the old
  page's layout (the limit line beside the slider; a date check in a property
  that moved). Both rewritten to say what is true now (below), then green.
- **Bare-runner variant** (`/tmp/ci` venv from `requirements-dev.txt`, no numpy,
  `AGENTVOICE_STRICT=1`): the new file with `test_states.py` and
  `test_commands.py`: 297 passed, 1 skipped (the numpy `importorskip`, as on
  the base commit). The whole bare suite was not run.
- Box: not run (`install.sh` did not change).

## What was built

**The Conversation page** (`pages/ConversationPage.qml`, 513 → 1,063 lines),
the same settings, compact:

- **Pace** at the top as a `CompactSelector` (Patient / Balanced / Snappy;
  **Custom** is listed, disabled, only while the four timings are none of
  them). The presets are unchanged: the four keys `leadInMs`,
  `trailingSilenceMs`, `quickEndMs`, `followUpMs`.
- **Four cards** in a `CardGrid` (one column below 720 px; at the overlay's
  usual width a half-width card cut "Keep listening after a reply" to "…rep…"):
  - *Follow-ups*: `conversationMode`, the forgetful-backend warning,
    `followUpMs`;
  - *Open mic*: **live state from the state file** (`open_mic` {who, until}, now
    `s.vOpenMic` in `Settings.qml`): "On with Theo · 9 min left" / "Off. It
    needs the wake word." / "The service is not running."; a **Turn on / Turn
    off** button (`agentvoice open-mic on|off`, as the popup runs it);
    `openMicIdleMin`, `openMicAddressedOnly`, `openMicAuto`;
  - *While it works*: `narration`, `narrationSilenceS`;
  - *Talking over it*: `fullStopAnytime`, `bargeOnHeadset`, `bargeIn`, and
    `bargeFactor` under its own Advanced.
- **Three different stops** (my reading of "the page keeps turn off open mic,
  stop a reply and stop the service visibly apart"): a card that says what each
  one ends and what it leaves. It has no buttons of its own; the open mic's is
  in its card (Open issue 2).
- **A turn, start to end**: `ui/TurnTimeline` (new) drawn from the live values:
  lead-in, you talk (up to `maxUtteranceMs`), the pause (and the shorter one
  after a finished sentence), the reply, the follow-up window (left out while
  following on is off). Widths grow with the square root of the time and the
  bar says it is "not to scale"; a legend gives the real numbers. Under it the
  limit note, **"3 turns today hit the limit, the last at 11:40. Raise it →"**,
  with a red mark on the end of "you talk". **Raise it** opens the folded
  **Advanced timings (6)**, scrolls to *Longest a turn can be* and outlines it
  for 2.5 s. The six timings (`leadInMs`, `trailingSilenceMs`, `quickEndMs`,
  `minUtteranceMs`, `maxUtteranceMs`, `echoTailMs`) live there.
- **Voice commands** card: `commandsInSentences` (moved in from its old group)
  and **All commands (10)**, folded, generated from `agentvoice commands
  --json`: each command's label, where it works *in the mode chosen now*, "no
  wake word needed" where true, what it does, three of its phrases and "and N
  more" (all of them in the tooltip). **The page holds no command phrase of its
  own**: the open mic's note ("Say “keep listening” to start it and “stop
  listening” to end it.") and the example under the sentence control are built
  from the table; the undo phrase too. Before the table is read they say
  something generic.

**The deep link** (`Settings.qml`): `{"page":"conversation","focus":"echoTailMs"}`.
`focusKey` is a setting's key and nothing else (`^[A-Za-z]{1,40}$`), is set
after `goTo()` (which clears it), and a page acts only on the keys it holds;
the Conversation page takes it (resets it to "") so asking twice is two
changes.

**`daemon/speech_text.py`**: `table()` gains `mode_positions` (which positions
each mode lets a command fire in), so the page does not repeat the rule.

**`bench/preview`**: a `commands` case in the stub (this checkout's CLI, read
only); targets `conversation` (46 checks) and `conversationclicks`; config
`conversation.json` (`maxUtteranceMs` stored as the string `"90000"`).

**Docs**: README (the page), CODEBASE (page, `TurnTimeline`, the `focus` key,
`voice_commands`, the two targets). No FINDINGS entry: nothing here is a
"faster" or "smaller" claim.

## What was proven, and how

- **The `clicks` diff the plan asks for**: `conversationclicks` drives every
  control on the page by its label (old and new wording both listed; the
  pace through chips on the old page and through the selector's menu on the
  new one), against a checkout of `phase-m23` in a worktree and then against
  this tree, same synthetic config and state. **Identical: 23 writes** (every
  one of the 18 keys, plus the engine switch that makes the full-stop switch
  live). `diff` of the sorted write logs was empty.
- **Preview `conversation`, 46 of 46 PASS** (synthetic mouse events through
  `TestEvent`, scratch config, state and data folder, the pointer never moved):
  - the seven cards; Pace reads **Balanced from a config that stores none of
    the timings**; the timing stored as **the string "90000" reads as 90 s** in
    the drawn turn and as 90000 on the knob; the turn's notes say the live
    values; the red limit mark is on "you talk" and on no other block;
  - the open mic says "On with Theo · 9 min left" with a Turn off button; Turn
    off wrote `agentvoice open-mic off` and Turn on `open-mic on` (read from
    the write log, below); with the service stopped the button is disabled, the
    line says "The service is not running." and the reason is written under it,
    both gone when the service is back;
  - the table is read from the daemon: 10 commands, each listed, the example
    "Take notes, and keep listening." and the open mic's note built from the
    table's own phrases; in `edges` the open mic reads "on its own, at the
    start, at the end" and Stop "on its own";
  - **Raise it** opens the timings, scrolls the knob into view, writes nothing,
    and the request is taken; a deep link with `focus: "echoTailMs"` opens and
    scrolls to that knob; `"not a key; rm -rf"` is dropped and opens nothing;
    `bargeFactor` (not a timing) opens nothing;
  - Snappy, chosen through the real menu, writes the same four timings; a
    timing moved by hand reads **Custom**, and Custom is then listed.
  The write log agrees (`open-mic off`, `open-mic on`, the four timings, then
  `followUpMs 9000`). The first run had 4 FAILs (below); the last is 46 of 46.
- **Tests** (`tests/test_conversation_page.py`, 33): every key the page had is
  written once and none added or lost; the six timings are folded together and
  each marked row writes its own key; the presets equal the old four; Balanced
  is what ships; **no quoted command phrase on the page** (against every phrase
  in `COMMANDS` and the undo list); the daemon reads `"90000"`, `" 90000 "`,
  `"-1"`, `90000.9` and gives the shipped value for `""`, `"abc"`, `"9e4"`,
  `"90000ms"`, `None`, a list, a dict; **no number on the page is read bare**
  (every one goes through `num()`); the open mic has one entry point that
  checks the service before it starts the one process; a press that cannot work
  says why, and the page never reads `exitCode`; the state field names match
  what the daemon writes; the deep link's regex, `goTo` clearing, order and
  the page taking it; `mode_positions` against `_MODE_POSITIONS`; every field
  the page reads from a command exists in the table; every `Text` on the page
  and the timeline is `PlainText`; the timeline is fed from the settings.
- **Mutations: 19 run, 19 red** (a scratch copy under /tmp, never the clone):
  a quoted phrase written on the page; `num()` as a bare `Number`; a knob
  reading bare; no service guard; a second entry point to the open mic;
  `exitCode` used; the preset fallback `-1`; a preset drifting; a timing knob
  writing another key; a key lost; a key written twice; the focus not taken;
  any focus accepted; `goTo` keeping the focus; the focus regex loosened;
  `mode_positions` gone; a `Text` without `PlainText`; the timeline ignoring
  follow-up off; the limit count dropped.
- **Screenshots** (`/tmp/m24`, not committed): 1100×760 dark (`dark-1…6`, the
  page top to bottom with every fold open), flexoki-light (`light-1…6`), and
  520×720 (`narrow-1…3`; the crop cuts the overlay's right edge, as in M18 to
  M23).

## Shared files touched, and where

- `Settings.qml` (big shared, 2,190 → 2,207): `focusKey`, `vOpenMic` and its
  parse from the state file, `goTo()` clearing the focus, the summon payload's
  `focus`. Four small hooks, no behaviour changed for any other page.
- `pages/ConversationPage.qml`, `ui/TurnTimeline.qml` (new), `ui/qmldir`,
  `daemon/speech_text.py` (one field), `bench/preview/preview.sh`,
  `README.md`, `CODEBASE.md`, `tests/test_states.py` (two tests), new
  `tests/test_conversation_page.py`, `bench/preview/targets/conversation.qml`,
  `conversationclicks.qml`, `bench/preview/configs/conversation.json`.
- Not touched: `wake_listen.py`, `runtime.py`, `manifest.json`, `install.sh`,
  `KnobRow.qml`.

## Measured

Nothing. No speed or size claim is made.

## Different from the plan, and why

- **Three different stops is a card of words, not three buttons.** The plan
  says the page keeps "turn off open mic", "stop a reply" and "stop the
  service" visibly apart. Only the open mic's button is here (in its card). A
  Stop button and a service switch would add callers to `toggleService`, whose
  caller count a test holds (CLAUDE.md), and the popup already has both. Open
  issue 2.
- **Cards go to one column below 720 px**, not at the `CardGrid` default 520:
  at the overlay's usual width the labels were cut.
- **`bargeFactor` is under an Advanced inside its card**, and **`echoTailMs`
  moved to Advanced timings**, as the plan says; neither has a new key.
- **The voice-command list is folded** ("All commands (10) ▸") with the
  `commandsInSentences` control above it, so the page is not a wall of ten
  paragraphs. Open issue 3.
- **Hand-written examples went.** The old text said `Say "stop" or "never
  mind"`, `"keep listening"`, `"stop listening"`, "full stop" and the like.
  They are now built from the table or reworded ("the stop command"); the
  full-stop switch's label is "Stop everything by voice, without the wake
  word" (it had the phrase in its name). Same key.
- **The limit note's words changed** from "Cut 3 turns off at this limit
  today" to "3 turns today hit the limit", as the plan writes it.
- **Codex review bypassed** by the user's decision.

## Found along the way

- **A fresh config read "Custom", not "Balanced".** The old page read an unset
  timing with a fallback of `-1`; `SettingsStore.get` returns the fallback for
  a missing key, so a config that never wrote the four timings never matched a
  preset (pre-existing). On this machine the keys are written, so it never
  showed. The preview's synthetic config found it. The page now falls back to
  the shipped value, as the daemon does (`paceValue()`), and a test holds it.
- **`exitCode` is not a property of a Quickshell `Process`.** I used it in the
  open mic's error path; the preview logged a `ReferenceError`, which
  `qmllint` does not catch. It is `onExited(code, status)` now (memory
  note written).
- **A deep link's `open()` reloads the state file**, which wiped the open mic
  the target had poked in, so the next "Turn off" click correctly wrote
  `open-mic on`. Found only by reading the write log, not by the PASS lines
  (memory note written). The target pokes it again before the click.
- **The scroll to "Raise it"'s control stopped short for the last knob**: the
  scroller's height is the new one only a frame after the fold opens, so the
  clamp was too low. An 80 ms timer does it now. (A `callLater` passed for the
  middle knob and failed for `echoTailMs`, the last.)
- **A `limitMark` per block** was in the first target as "any item called
  limitMark": every block has one (hidden but the talk block), so the check
  found the wrong one. The target now asks the "you talk" block.
- **My re-read**: the open mic's note said "a reply that is playing finishes";
  `end_open_mic` touches no speaker, so that is true, but I had not read it
  when I wrote it. I read `wake_listen.py:5562` and `:5594` and reworded to
  "Nothing that is running is stopped". "The service and the open mic stay as
  they were" for a reply stop was not something I had read (a full stop ends
  the open mic, `:3002`; a plain stop I did not trace), so it says only "The
  service keeps running." Also: a test searched literals in raw source
  including comments by accident (`text is src()` is never true); it now reads
  comment-free source.

## Not verified

- **The page in the real shell.** It needs `omarchy-restart-shell` (not run).
  Seen only in `preview.sh`. Until the restart the running shell has M23's
  page.
- **Live, at stop 5**: a 90 s capped turn and a shorter one, and the count and
  the link (the plan's check). No turn was spoken or run; no turn on this
  machine has hit the limit (`limit_hits.today` is 0), so the real
  note and link were seen only with a poked count.
- **The open mic's Turn on / Turn off against the live daemon.** The preview
  stub logs the command; the real `agentvoice open-mic on|off` was not run
  (it would change what the microphone is doing; and the live microphone
  reads all-zero frames, M23's open issue 6). The popup's own button runs the
  same command.
- **The live state's countdown**: the preview poked `until`; the daemon's real
  `open_mic` field was only read from the code (`open_mic_field`, `{who,
  until}`) and from `agentvoice status` while it was closed (`{}`).
- **"Nothing that is running is stopped"** under Turn off open mic (read in
  the code, not run); and what a plain stop leaves of the open mic (not
  traced).
- **A timing stored as a string in the real settings**: tested through the
  daemon's reader and a synthetic config in the preview, not written to the
  real `shell.json`.
- **The narrow layout** (below 560 px): the crop cuts the overlay's edge.
- **Keyboard**: Tab to "Raise it →" and Enter was not driven (the preview never
  takes the keyboard).
- **The installer box** (`install.sh` did not change).
- **The Codex review** (bypassed, not owed).

## Going back

`bin/agentvoice-deploy 071092e021d0` from the clone, `./install.sh --yes` once
the daemon is idle, then `omarchy-restart-shell`. Nothing stored changes: no
setting was added, moved or rewritten, and a M23 build ignores the one new
field in the commands table. The deep link's `focus` is ignored by an older
overlay.

## Open issues, for the next phase

1. **Codex review bypassed** for M24 (user decision, 2026-11-22). M12 stays
   "review owed".
2. **"Stop a reply" and "Stop the service" are described, not offered, on this
   page.** Default: words only; the popup has the controls. A Stop-reply button
   (`agentvoice interrupt`) would be harmless to add; a service switch adds a
   `toggleService` caller (CLAUDE.md's guard rule).
3. **The command list is folded.** Default: folded, with the sentence control
   above it. Open it by default?
4. **Cards stack in one column** at the overlay's usual width (720 px to
   split). Default: as built.
5. **The pace selector has no "Custom" to choose**, only to show (a pace you
   set by hand cannot be "applied"). Default: as built.
6. **The Overview's limit line has no link to the control** (the plan puts
   "Raise it" on this page only). `{"page":"conversation","focus":"maxUtteranceMs"}`
   is there for it, or for the bar, if wanted.
7. **Carried, still open**: M23's 2–7; M22's 2–7; M21's 2–7; M20's 2–8; M19's
   3–6; M18's 2–6; M17's 2–7; M16's 2–9; M15's 2–8; M14's 2–7; M13's 2–9; M12's
   2–7; M11's 1–7; M10's 1–8; M9's 2–7; M8's 2–11; M7's 2–7; M6's 1, 3, 4; M5's
   1, 4–6; M4's 4–13; the Voice library trash icon (M25); M0's small test and
   bench fixes; agy's `carries_session_across`; the runner's sandbox test
   command.

## Live checklist: what was done, what happened

Nothing was said into the microphone and nothing was spoken: no turn was run.
- Before the deploy: state `listening`, every agent idle (`''`, `sora`,
  `jarvis-ajc`), `open_mic` `{}`, no journal error; `shell.json` copied (0600).
- `bin/agentvoice-deploy --install --wait 120 d4ad068`: strict check green;
  "deployed d4ad068d3bff. The way back: bin/agentvoice-deploy 071092e021d0";
  "QML changed: run omarchy-restart-shell? (not run)"; "Build 0.2.0 (d4ad068),
  replacing 0.2.0 (071092e)". Service active, no error or traceback in the
  journal after the restart.
- The installed CLI: `agentvoice commands --json` gives mode `edges`, ten
  commands and `mode_positions` `{alone: [alone], edges: [alone, start, end],
  clause: [alone, start, end, clause]}`.
- `shell.json` byte-identical to the copy afterwards. No shell restart.
