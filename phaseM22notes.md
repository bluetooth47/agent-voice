# Phase M22: Wake decisions that match the controls

Written 2026-11-23, unattended (started by the runner script). Branch
`phase-m22`, cut from `phase-m21` at d9d56fb. Result commit: the notes commit
on top of f0e2340, pushed to `fork/phase-m22` only; `dev` fast-forwarded to it
and pushed to `fork`. Model: Claude Opus 5.5 (tier A in the plan, xhigh).

Commits:
- f0e2340: the phase;
- then these notes.

**Codex review: bypassed (user decision, 2026-11-22).** Codex was not run, for
review or anything else. In its place I re-read the whole diff twice before
the commit and ran 29 mutations of the decision and its guards; what that
found is under "Found along the way". Nothing in this phase has been reviewed
by a second model, and this is a Tier A phase, where the plan wanted both
passes.

Deployed: **yes**, through `bin/agentvoice-deploy --install --wait 120
f0e2340` (its strict check green) with the daemon idle (state `listening`,
every agent idle (`''`, `sora`, `jarvis-ajc`), no open mic, no task, no
journal line in the five minutes before): "deployed f0e2340f38ab. The way
back: bin/agentvoice-deploy 952883cb66f1".

Installed: **yes**: "Build 0.2.0 (f0e2340), replacing 0.2.0 (952883c)". The
daemon (`crosscheck.py`, `wake_listen.py`, `runtime.py`, `stats.py`,
`monitor.py`, `wake_auto.py`) changed. `install.sh` did not.

**Nothing about waking changed on this machine.** `wakeBothAgree` is off by
default and was not written; the daemon says "wake decision: either stage can
wake", exactly the behaviour before.

**Shell restart needed** (`pages/ListeningPage.qml`, `pages/OverviewPage.qml`,
`Settings.qml`). Not run. Until it is, the running shell shows M21's Listening
page: the old "Second check for short names" switch (it still works: it writes
`wakeCrossCheck`, which the daemon reads as before) and no "When a wake
counts" selector. The setting works before the restart: `omarchy bar set
duaneoca.agentvoice wakeBothAgree true` (and `false` to go back).

A copy of `shell.json` was taken before the deploy
(`~/agentvoice-notes/shell.json.before-M22`, 0600); after the install and the
live checks it was byte-identical. No live check wrote a setting.

`./bin/agentvoice-check`: green on the final tree (exit 0, every line ok).
- **4997 tests** (was 4920; +77), 14 of 14 static checks, "the check wrote
  nothing in the tree: ok". 5 min 50 s.
- **Bare-runner variant: run** (`/tmp/ci` venv from `requirements-dev.txt`,
  `AGENTVOICE_STRICT=1`). It failed one new test, which measured frames with
  `frame_db` and so needed numpy; every other test passed. Fixed (the test now
  uses the standard-library RMS `tests/frame_loop.py` already has); the new
  test file was then rerun on the bare venv (77 passed). The whole bare suite
  was not rerun after that one-line test change.
- Box: not run (`install.sh` did not change).

## What was built

**Three wake decisions** (`daemon/crosscheck.py`): `decision(cross_check,
both_agree)` names them --
- **first** -- the spotter alone (`wakeCrossCheck` off);
- **either** -- a spotter hit wakes at once and the second check rescues a
  short burst the spotter missed (`wakeCrossCheck` on: the default, and the
  path every existing wake test holds; unchanged);
- **both** -- `wakeBothAgree` on: a spotter hit is held while the second check
  hears the speech up to it, and wakes only if it names the same agent.
  `wakeBothAgree` wins over `wakeCrossCheck`: both asked for with the check off
  is "both", which cannot run, so wakes are held closed (below), never the
  spotter alone.

**The hold** (`crosscheck.Agreement`, driven by `Pipeline._both` in
`wake_listen.py`), two orders because the stages report at different moments:
- **spotter first**: the hit is held for `CONFIRM_TAIL_FRAMES` frames (0, so
  it is judged on its own frame; measured, below) or until the burst ends.
  The second check (`Pipeline._ask`, the same Vosk/Whisper vote and rule as
  before, factored out of `_second_check`) hears the burst so far
  (`Bursts.take()`: the preroll and the speech up to the hit; under 300 ms or
  past the burst maximum is "too short, or inside a sentence"). The same name
  wakes, with `wake_how = "confirmed"`; anything else is **held, then
  dropped**;
- **second check first**: a burst the spotter stayed silent on still goes to
  the second check, and a name it hears waits `AGREE_WINDOW_MS` (600 ms, three
  frames) for a late spotter hit on the same name.
- **Frames said while a hit is held are carried into the capture it opens**
  (`take_carried` → `Daemon.carry_into`, in the run loop's wake branch and the
  wake-while-working branch), judged against the gate rather than `voiced()`,
  which would discount them for the wake chime that came after them. With the
  shipped tail of 0 only the late-spotter order carries anything.
- A hold older than 3 s by the clock is dropped, not decided (its frames went
  elsewhere: a deaf window, a capture). A change of decision clears it.

**Held closed, never one stage.** `crosscheck.both_blocker` names why "both"
cannot run, as a code with a fixed sentence (`BLOCKERS`): `oww` (openWakeWord
has no second check), `vosk` (nor Vosk), `fallback` (sherpa-onnx chosen and not
running), `off` (the second check switched off), `no-vosk` (a Vosk-only check
with no Vosk model; asked again on the idle poll, outside the config guard,
because a model arriving on disk is not a setting change). With "both" chosen
and a blocker, every name an engine hears is "held, then dropped" with that
reason (a refractory stops one phrase counting five times on openWakeWord and
Vosk). The journal says "wakes held closed: both stages must agree, and …".

**"Full stop" keeps its own immediate path in every mode**, held closed
included, and drops anything held.

**A lock or a mute drops a held wake and the burst under way**
(`Pipeline.forget_wake`, called for every frame the run loop discards while
not listening), so a name said before a lock is never joined to speech after
it.

**What is said about it:**
- the state file's sticky `wake_decision`: `{mode, closed, blocked, why}`,
  published when it changes (`Daemon.reconcile_decision`, on the idle poll and
  after a settings change);
- **the HUD**: "Theo: heard, not confirmed" for four seconds through the
  existing `notice` line (agent label, never what was said; composed after the
  lock check, so never over a lock screen; its expiry polled above the
  listening gate, with the readout's);
- **stats**: wakes `confirmed` ("confirmed by the second check") and
  rejections `held` ("held, then dropped"), in `agentvoice stats` and on the
  Overview's wakes tile (" · N held", and the tooltip);
- **`agentvoice monitor`** prints the decision in force first ("wake
  decision: …", or "… -- wakes are held closed"), and in "both" labels a
  spotter hit "SPOTTED: theo (held for the second check)" instead of "WOULD
  FIRE";
- the automatic wake test tallies `confirmed` as its own column, and its
  settings line says "both must agree".

**Setting `wakeBothAgree`** (bool, default off): manifest schema and defaults,
`runtime.DEFAULTS`, `TOML_ALIASES` (`[wake] both_agree`), `Config.
wake_both_agree()` (only a plain true, or "true"/"yes"/"on"/"1" from a hand
edit; anything else and unreadable settings are off, as Appendix A fixes it).
A plain attribute on the pipeline, assigned after the spec check: a rule is a
number, not a model (no rebuild, tested).

**One control: Listening → Wake word → "When a wake counts"**
(`pages/ListeningPage.qml`): First only / Either stage / Both must agree,
writing `wakeCrossCheck` and `wakeBothAgree` in an order that keeps every
state in between one of the three. It replaces the Advanced "Second check for
short names" switch (same key, same value; the Advanced second-check rows
still show while the check is on). The hint says what each costs, "Both" with
its measured delay. **Both is refused with the reason** when the page can see
the second stage cannot run (openWakeWord, Vosk, sherpa-onnx not installed) or
the daemon says so (fell back, no Vosk model): nothing is written, the chip's
hold is dropped, and the reason clears itself when its cause goes. When the
daemon says wakes are held closed, a red line says why and what to do (by
cause), and the Overview lists it under what needs attention.

**Preview**: a new `decision` target (`sherpa`, `refused`, `novosk`, `closed`,
and `-shot` variants).

**Measure**: `bench/wake_modes.py` (FINDINGS §55).

**Docs**: README ("When a wake counts"; the Overview's confirmed and held),
CODEBASE (the decision, the state file fields, the page, the key list),
FINDINGS §55.

## What was proven, and how

- **Tests** (`tests/test_wake_decision.py`, 77 cases):
  - the three decisions from two settings; every blocker by engine and case,
    each a fixed sentence; the agreement's tail, window, expiry; `take()`
    keeping the window (too short, too long, no burst);
  - through the Pipeline with the engines stood in for: **first hit and second
    miss** (held, counted, the reason, no speech in the journal); **first
    miss rescued** (a wake with either stage, held and expired with both);
    **the two stages naming different agents**; **a vote inside the window**
    (late spotter agrees) and **outside** it; a name inside a sentence; a
    name below the gate; a second check that fails; a stale hold; forgetting;
    the shipped tail judging the hit on its own frame; carried frames;
  - **an unavailable second stage**: the check switched off, a Vosk-only check
    with no model (and the model arriving), openWakeWord, the Vosk grammar --
    all held closed, never a wake;
  - **"full stop" in every mode** (first, either, both, both held closed), and
    a full stop dropping a held name;
  - **with `wakeBothAgree` off the existing wake tests pass unchanged**:
    `test_crosscheck.py`, `test_sherpa_wake.py` and `test_wake_reconcile.py`
    are untouched and green; plus explicit "a spotter hit still wakes at once"
    cases;
  - the setting: three places, eleven raw values, default off, unreadable off,
    a stand-in config without the method, `apply()` taking it with no rebuild
    and clearing a hold;
  - **the real frame loop** over a scripted microphone with the real
    `Pipeline._both`: the capture opens with the held frames first; with
    either stage nothing is carried; **a lock in the middle of a hold drops
    it** (nothing wakes after the unlock);
  - the HUD note (said, expires, not over a lock), the state file field, one
    publish per change and none for a pipeline that says nothing, the wake test
    draining held names, stats counting confirmed and held, the selector's
    source (both keys, the refusal before any write, the hold dropped), the
    plain-text reasons, the overlay's parse and problem, `monitor`'s line
    (including a sherpa-onnx with no model).
- **Mutations: 29 run, 29 red** (a scratch copy under /tmp, never the clone):
  the sherpa "both" branch removed; full stop routed into the hold; a blocked
  stage not held closed; a different agent accepted; no verdict taken as
  agreement; openWakeWord and the Vosk grammar waking on one stage; forget
  doing nothing; the run loop not forgetting on lock; frames not carried
  (twice); a vote never expiring; a stale hold decided; `take()` ignoring
  either bound; both-with-check-off read as first; three blockers removed;
  `wake_both_agree` truthy for any value and read with settings unreadable;
  `closed` never reported; a hold surviving a change of rule; held names never
  reaching the HUD or the stats; the note shown over a lock; the refused pick
  keeping its hold or writing anyway; monitor ignoring a missing model.
- **Preview** (`preview.sh`, synthetic mouse events through `TestEvent`, a
  scratch config and runtime folder, the real pointer never moved):
  **`decision` 25 of 25 PASS** -- `sherpa` 9 (Either stage shown by default;
  Both writes both keys on; First only both off; Either back), `refused` 9
  (refused with "openWakeWord has no second check", nothing written, the chip
  back on what is set, a second click not swallowed, the reason gone with its
  cause, Both taken on sherpa-onnx), `novosk` 2 (refused with the daemon's
  reason), `closed` 5 (the red line and why, listed under what needs
  attention, shown on the Overview, Either stage a way out). The write logs
  agree. **`overview` `several` 11 of 11** after the wakes tile change.
- **Screenshots** (`/tmp/m22`, not committed): 1100×760 dark (default, the
  refused state, closed), flexoki-light (closed), 520×720 (the crop cuts the
  overlay's right edge, as in M18 to M21).

## Shared files touched, and where

- `daemon/wake_listen.py` (big shared, 7,407 → 7,794): `_both_agree`,
  `WAKE_NOTE_S`, `HOLD_STALE_S`; `Pipeline.apply` (the decision, clearing a
  hold, `reconcile_decision`); `feed_wake` (the "both" branch before the
  spotter's own, the held-closed paths for openWakeWord and Vosk, `carried`
  reset); `_second_check` now calls `_ask` (same vote, same prints); new
  `_ask`, `_agreement`, `_both`, `_confirm`, `_agreed`, `_held`, `take_held`,
  `take_carried`, `forget_wake`, `decision_why`, `decision_field`,
  `reconcile_decision`; `Daemon.wake_testing` drains held names; `refresh`
  and `reconcile_decision`; the wake watch keeps carried frames; `note_wake`
  → `note_held`, `wake_note_line`, `expire_wake_note`, `take_carried`,
  `carry_into`; `crew_fields` → `wake_decision`; `_compose`'s `notice`; the
  run loop: `forget_wake` while not listening, the note's expiry above the
  gate, `carry_into` in the wake and woke branches.
- `Settings.qml` (big shared, 2,177 → 2,190): `vWakeDecision`, its parse, one
  `problems` entry.
- `daemon/crosscheck.py` (198 → 352), `daemon/runtime.py`, `daemon/stats.py`,
  `daemon/monitor.py`, `daemon/wake_auto.py`, `manifest.json`,
  `pages/ListeningPage.qml` (838 → 957), `pages/OverviewPage.qml`,
  `tests/test_stats.py`, `tests/test_wake_test.py`, `README.md`, `CODEBASE.md`,
  `bench/FINDINGS.md`; new `tests/test_wake_decision.py`,
  `bench/wake_modes.py`, `bench/preview/targets/decision.qml`.

## Measured

FINDINGS §55, on the i7-1185G7, `bench/wake_modes.py`: the daemon's own
Pipeline over 300 synthesized clips per decision (six Piper voices, two
levels; phrase "theo", agents "sora" and "hazel"; Whisper base.en):

| | first only | either stage | both must agree |
|---|---|---|---|
| true accepts | 60/96 | 77/96 | 48/96 |
| one-breath requests | 20/24 | 20/24 | 18/24 |
| distractor accepts | 34/204 | 40/204 | 8/204 |
| a name inside a sentence | 19/36 | 19/36 | 0/36 |
| added over a spotter wake | — | — | +0.79 s median, +1.14 s p95 |
| CPU for 300 clips | 34 s | 426 s | 710 s |

The tail: 1 and 2 frames stopped the same 8 distractors as 0, caught 5 fewer
real wakes and added more delay; shipped at 0. Three second checks across the
three "both" runs took 4.6 s or hit the 10 s timeout (below).

## Different from the plan, and why

- **The confirmation hears the speech up to the spotter hit, not the whole
  burst.** Held to the burst's end, a request said in one breath ("Theo, what
  time is it?") runs past the trailing-word rule or the burst maximum and
  never wakes. Measured: tail 0 caught 18 of 24 one-breath requests, against
  13 with a two-frame tail.
- **The second check still runs on bursts the spotter missed, and a name it
  hears waits 600 ms for a late spotter.** The spotter sometimes reports after
  the burst has ended; without this, "both" would lose those wakes too. The
  plan's "a vote outside the window" is this window.
- **"Held, then dropped" counts both orders**, and every name heard while
  wakes are held closed. A spotter hold whose confirmation says no counts once
  (as held), not also as a second-check rejection.
- **`wakeBothAgree` on with `wakeCrossCheck` off reads as "both", held
  closed**, not "first": that pair arises only from a hand edit, and the plan's
  rule is never to fall back to one stage silently. Open issue 3.
- **The selector replaced the Advanced "Second check for short names" switch**
  and sits in the Wake word group (M23 moves it into the Decision stage). The
  key keeps its name and value.
- **The HUD's "heard, not confirmed" uses the existing `notice` line**, so the
  HUD needed no change.
- **The tests are a new file**, `tests/test_wake_decision.py`. The three files
  the plan names are untouched, which is the plan's "existing wake tests pass
  unchanged" taken literally. Two existing assertions elsewhere changed:
  `test_stats.py`'s exact-shape dict and `test_wake_test.py`'s tally gained the
  new `held` and `confirmed` keys, and the count of `_rejected("second-check")`
  call sites is now two (either stage, and both).
- **CPU is measured over the clip set**, not at idle: "both" adds nothing
  while nobody speaks; its cost is one Whisper transcription per spotter hit.
- **Codex review bypassed** by the user's decision.

## Found along the way

- **The second check's burst survived a lock** (pre-existing, in either
  mode): frames stop during a lock, but the cutter kept a burst in progress,
  so a name said as the lock landed plus two quiet frames after the unlock
  could make the rescue path wake straight after unlocking. `forget_wake` now
  clears it for every frame discarded while locked or muted.
- **A second check can hold the frame loop for up to 10 s** (pre-existing; the
  rescue path does it too): in the bench one Whisper reading of a short burst
  took 4.6 s and two hit the 10 s timeout. Frames queue, so nothing is lost,
  but the wake waits. Open issue 6.
- **My guess about the tail was wrong.** I set it at two frames so that
  "Theodore" or "Hazelnut" would be heard to the end; the bench showed no
  distractor stopped by it and five real wakes lost. Shipped at 0.
- **The bench first gave different spotter results for identical audio in
  different modes**: a reset sherpa stream still carries state from the clip
  before, and the clip before differed (one mode stops at a wake, another
  holds). Each clip now gets a fresh stream.
- **Two of my tests used a one-frame name** (200 ms, under the 300 ms
  minimum), so one passed for the wrong reason and two failed; they use a
  two-frame name now and assert the reason.
- **My first `refresh()` hook published on its first call** whatever the
  pipeline said, which broke seven tests whose fake agents cannot describe
  themselves, and **the note's expiry was below the listening gate** (a muted
  microphone would never have expired it; a readout test caught it). It now
  publishes only a field that says something and differs from the one last
  published, and the expiry is polled above the gate.
- **The bare runner caught a test that needed numpy** (above).
- **My re-read**: `monitor` would have called "both" ready with sherpa-onnx's
  model missing (the daemon falls back to Vosk and holds wakes closed); the
  held-closed line advised "switch to sherpa-onnx" whatever the cause (it now
  follows the cause: install it, switch the check back on, or let Whisper
  vote).

## Not verified

- **The page in the real shell.** It needs `omarchy-restart-shell` (not run).
  Seen only in `preview.sh`. Until the restart the running shell has M21's
  Listening page and Overview.
- **By voice (the plan's stop 5 check): names and distractors in each mode.**
  Nothing was said into the microphone. The live daemon was left in "either
  stage" (no setting written), so "both" has run only in the tests, the
  preview and the bench, never on the live daemon with a microphone.
- **The HUD's "heard, not confirmed" in the real shell** (needs "both" on and
  a name the second check turns down).
- **The wake-while-working carry** (a held wake heard during a reply, in the
  single-agent watch): checked in the source, not driven.
- **The narrow layout** (below 560 px): the crop cuts the overlay's edge.
- **The installer box** (`install.sh` did not change).
- **The Codex review** (bypassed, not owed).

## Going back

`bin/agentvoice-deploy 952883cb66f1` from the clone, `./install.sh --yes`
once the daemon is idle, then `omarchy-restart-shell`. **An M21 build ignores
`wakeBothAgree` and wakes on one stage again** (either stage, if
`wakeCrossCheck` is on): if it was switched on, say so before handing the mic
back, or set `wakeCrossCheck` off for the spotter alone. The key stays in
shell.json if it was written. M21's `stats.py` drops the unknown `confirmed`
and `held` counts from a day file the next time it writes that day; nothing
else it reads changed shape (the state file's `wake_decision` is ignored by
older QML).

## Open issues, for the next phase

1. **Codex review bypassed** for M22 (user decision, 2026-11-22), a Tier A
   phase. M12 stays "review owed".
2. **"Both" is strict: the spotter and Vosk and Whisper**, with "who votes"
   on both. In the bench it kept 48 of 77 wakes; 17 of the 29 lost were names
   the spotter never heard (the mode's definition), 7 were Vosk disagreeing.
   Should "both" default to Whisper alone as the second stage? Default: no --
   the second stage is whatever "who votes" says, and the page links to it.
3. **`wakeBothAgree` on with `wakeCrossCheck` off** (a hand edit) holds wakes
   closed rather than reading as "first only". Default: closed, with the page
   saying how to switch the check back on.
4. **Unreadable reads as off** (either stage), as Appendix A fixes it. For a
   wake rule, is "both" (fewer wakes) the safer reading? Default: off, as the
   plan says.
5. **The HUD appears for four seconds on "heard, not confirmed"** while idle.
   Welcome, or noise? Default: shown.
6. **A slow second check holds the frame loop** (4.6 s, and two 10 s timeouts
   in 900 bench clips; the rescue path too). Run it off the loop, or cap
   Whisper's output length? Default: noted, not changed (pre-existing).
7. **The trailing-word rule also applies to the confirmation** (2 of the 29
   lost wakes). Default: kept.
8. **Carried, still open**: M21's 2–7; M20's 2–8; M19's 3–6; M18's 2–6; M17's
   2–7; M16's 2–9; M15's 2–8; M14's 2–7; M13's 2–9; M12's 2–7; M11's 1–7;
   M10's 1–8; M9's 2–7; M8's 2–11; M7's 2–7; M6's 1, 3, 4; M5's 1, 4–6; M4's
   4–13; the Voice library trash icon (M25); M0's small test and bench fixes;
   agy's `carries_session_across`; the runner's sandbox test command.

## Live checklist: what was done, what happened

Nothing was said into the microphone and nothing was spoken: no turn was run.
- Before the deploy: state `listening`, every agent idle, no open mic, no
  task, no journal line in five minutes; `shell.json` copied (0600).
- `bin/agentvoice-deploy --install --wait 120 f0e2340`: strict check green;
  "deployed f0e2340f38ab. The way back: bin/agentvoice-deploy 952883cb66f1";
  "QML changed: run omarchy-restart-shell? (not run)"; "Build 0.2.0
  (f0e2340), replacing 0.2.0 (952883c)". Service active.
- The journal after the restart: "wake: sherpa-onnx @ 0.20 (theo, sora,
  hazel, full stop) + second check", then **"wake decision: either stage can
  wake"**. 31 lines over twelve minutes (`-o json`), none an error or a
  traceback.
- `agentvoice status`: **`wake_decision: {mode: either, closed: false,
  blocked: "", why: ""}`**; no `notice`.
- `agentvoice stats`: the wakes line now reads "wakes 0 (confirmed by the
  second check 0), turned down 0 (second check 0, confidence 0, held, then
  dropped 0)".
- `monitor.decision_line` from the installed code with the real settings (the
  microphone not opened): "wake decision: either stage can wake (a spotter
  hit at once, or the second check)".
- **The automatic wake test** (`agentvoice wake-test auto`: every installed
  voice through the installed engines in its own process, no microphone, no
  speakers): done, 162 of 162 clips in 121 s; settings "threshold 20% · boost
  150% · second check on, both"; Theo 18/24, Sora 21/24, Hazel 20/24, full
  stop 12/12, each with the new `confirmed` column at 0; no false wake.
- `shell.json` byte-identical to the copy afterwards. No shell restart.
