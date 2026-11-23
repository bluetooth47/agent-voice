# Phase M25: Voice page

Written 2026-11-23, unattended (started by the runner script). Branch
`phase-m25`, cut from `phase-m24` at f73de9d. Result commit: the notes commit
on top of a2c0900, pushed to `fork/phase-m25` only; `dev` fast-forwarded to it
and pushed to `fork`. Model: Claude Sonnet 5.5 (high).

Commits:
- a2c0900: the phase;
- then these notes.

**Codex review: bypassed (user decision, 2026-11-22).** Codex was not run, for
review or anything else. In its place I re-read the whole diff before the
commit and ran 15 mutations of the page's tests; what that found is under
"Found along the way". Nothing in this phase has been reviewed by a second
model.

Deployed: **yes**, through `bin/agentvoice-deploy --no-install a2c0900` (its strict
check green) with the daemon idle (state `listening`, every agent idle,
`open_mic` empty): "deployed a2c090030cbc. The way back: bin/agentvoice-deploy
d4ad068d3bff".

Installed: **no, on purpose**: this phase changed no daemon file (QML, tests,
preview and docs only), so the running daemon is the build it should be.
`install.sh` did not change; the box was not run.

**Shell restart needed** (`pages/VoicePage.qml`, `ui/VoiceLibraryRow.qml`,
`ui/VoiceAgentRow.qml`, `Settings.qml`). Not run. Until it is, the running
shell shows M24's Voice page. Every setting works before the restart.
`shell.json` is byte-identical to the copy taken before the deploy
(`~/agentvoice-notes/shell.json.before-M25`, 0600); no setting was written and
no turn was run.

`./bin/agentvoice-check`: CHECKa2c0900

## What was built

**The Voice page** (`pages/VoicePage.qml`), the same four settings
(`speakReplies`, `chimes`, `model`, `livePartials`), tidier:

- **Quick settings**: `speakReplies`, `chimes`. The old "Voice and speed →
  Agents ›" row is gone: the next card does its job.
- **Each agent** (new `ui/VoiceAgentRow.qml`): the main agent and every extra
  agent, each with its name, voice, speed (and "follows the main agent" where
  it does), a **▶ Test** and **Change on Agents →**, which opens that agent's
  card (`goTo("agents", id)`). The row reads and writes nothing: voice and
  speed keep their home on the Agents card. ▶ Test plays what the agent
  really speaks in, at its real pace (the same rule as the Agents card's
  `voiceHeard`/`testPace`); it is off, with the reason, while replies are not
  spoken or the voice is not on this machine.
- **Library**: opens on **Downloaded**. One search box and one compact filter
  (Downloaded / All voices / Female / Male / American / British) replace the
  row of five buttons. A search matches every word against name, quality,
  gender and accent ("british female" finds the five British women). A voice
  being fetched stays in Downloaded so its progress is seen. An empty list
  says why. The row (`ui/VoiceLibraryRow.qml`): **the trash cell is first and
  is reserved on every row** (a quiet dash stands in for it when the voice is
  not on disk, is in use or is the default), the name takes what is left, and
  the Test/Download cell and the "Use for…" cell are fixed-width and anchored
  to the right edge: bug F. "Used for Theo, Sora" is its own line (the main
  agent by its display name, no longer "main"), `PlainText`. Use-for, fetch,
  retry, sample, remove and the in-use protection are kept, through the same
  overlay functions.
- **Advanced: hearing you** (folded, count 2): `model` and `livePartials`, with
  one line saying transcription turns speech into text on this machine before
  anything is sent to an agent.
- **More transcription models: deferred** (below).

`Settings.qml::voiceUsers` now returns the main agent's display name instead of
the word "main" (one line).

`bench/preview`: a `voice` case in the stub (Test, fetch and remove only log
to `<out>.writes`; `PREVIEW_REAL_VOICE=1` passes them through); target
`voicepage` (31 checks, measures the x of every column); config `voice.json`
(synthetic: Theo, Sora, Jarvis, Friday); `voices.qml` updated for the
selector.

**Docs**: CODEBASE (page, two rows, the targets). No README change (it does not
describe this page's layout). No FINDINGS entry: no speed or size claim.

## What was proven, and how

- **Preview `voicepage`, 31 of 31 PASS** (synthetic mouse events, scratch
  config, state and data, the pointer never moved), `.log` read for FAIL,
  ReferenceError, TypeError: none.
  - opens on Downloaded with 3 rows; one row per agent;
  - **bug F, measured** (`mapToItem` of each row's cells): on the Downloaded
    list (installed, in use, default) and on **All, 31 rows** (installed,
    missing, in use), the x of the trash cell is **11**, of the name **42**,
    of the Test column **302** and of Use for **410** on every row; one x for
    the agent rows' Test and Change cells too; the extra "Used for" line moves
    no column;
  - Amy reads "Used for Sora" and cannot be removed, Lessac "Used for Theo",
    the default has no trash button; a missing voice shows Download in the same
    column as Test;
  - "british female" finds 5; "zzz" says "No voice matches"; clearing it and
    choosing Downloaded is back to 3; Male filters;
  - Test (library and agent) wrote `agentvoice voice sample lessac-medium 100`
    and `... amy-medium 130` (Sora's own pace) to the write log; Change on
    Agents opened `agents` with `focusAgent` `jarvis`; the model chip wrote
    `model "base.en"`; replies off disables the agents' Test and the page
    says why; freeing Alba from Friday (through `assignVoice`) makes the trash
    appear and it wrote `voice remove en_GB-alba-medium`.
  The write log was read as well as the PASS lines (M24's lesson).
- **Tests** (`tests/test_voice_page.py`, 21): the four keys, once each; no new
  setting; the rows contain no `put`, `setAgentField` or `resetKey`, and the
  page does not write `voice`, `voiceAgents` or `voiceSpeed`; ▶ Test uses the
  Agents card's rule; the trash cell is first, anchored left, has no `visible`
  of its own and has a stand-in; each column but the name has a fixed width
  and the cells hang off the right edge; Test and Download share one cell; the
  library opens on Downloaded with one search and one filter; the search rule
  runs over the real voice list in `Settings.qml`; "Used for" uses display
  names; every `Text` is `PlainText`; Advanced holds exactly `model` and
  `livePartials`; **the models offered are exactly the manifest's three**; the
  preview stub cannot run the real `voice` command by default; the qmldir
  entry. `test_the_voice_librarys_shortcut_goes_through_one_function` and the
  key-inventory tests pass unchanged.
- **Mutations: 15 run, 15 red** (scratch copy in /tmp, never the clone):
  library opening on All; a row writing `voice`; Test ignoring the pace;
  Test ignoring why it cannot play; `AutoText`; the trash button shown for
  every voice on disk; the name ignoring the trash cell; a content-width Test
  cell; no stand-in; "used by"; "main" back in `voiceUsers`; an extra write on
  the model chip; an unpinned model offered; the preview stub running the real
  command (the first version of the test let this one pass; strengthened); the
  qmldir entry removed.
- **Screenshots** (`/tmp/m25`, not committed): 1100×760 dark (`dark-*`),
  flexoki-light (`light-*`), 520×720 (`narrow-*`; the crop cuts the overlay's
  right edge, as in M18 to M24).

## Shared files touched, and where

- `Settings.qml` (big shared): one line in `voiceUsers` and its comment.
- `pages/VoicePage.qml`, `ui/VoiceLibraryRow.qml`, `ui/VoiceAgentRow.qml` (new),
  `ui/qmldir`, `CODEBASE.md`, `bench/preview/preview.sh`,
  `bench/preview/targets/voices.qml`, new `voicepage.qml`, new
  `configs/voice.json`, new `tests/test_voice_page.py`.
- Not touched: `wake_listen.py`, `runtime.py`, `manifest.json`, `install.sh`,
  `models.lock`, `bench/pin-models.sh`.

## Measured

Nothing. No speed or size claim is made. (No models were added, so the
per-model memory and time measure the plan asks for does not apply.)

## Different from the plan, and why

- **Whisper pinning deferred (question 10).** The plan says to use Opus if
  pinning is included, and this phase runs on Sonnet; the default is "yes if
  it fits the session, else deferred". It touches `install.sh` (the box run),
  `models.lock`, `bench/pin-models.sh` and `wake_listen.py`'s loader, which is
  a different size of job from a page, and no hash is better than a wrong
  one. The page offers `tiny.en`, `base.en`, `small.en`, as before, and a test
  holds that list equal to the manifest's. The gap stays for V-02. Open issue 2.
- **One filter, single choice**: Downloaded / All / Female / Male / American /
  British are alternatives, not combinable (the search box combines with it).
  The plan says "one compact filter (downloaded / all, accent, gender)".
- **The "Every voice comes from the pinned revision..." paragraph** that was a
  `?` help on the library row is now a small paragraph under the search box,
  because the new header has no row to hang a help on.
- **The "Voice and speed → Agents ›" row removed**: each agent's own link
  does what it did.
- **Codex review bypassed** by the user's decision.

## Found along the way

- **A preview heredoc ran my comment.** I wrote a backtick-quoted target name
  in a comment inside the stub's unquoted heredoc; bash ran it ("voices:
  command not found"). Reworded. (Pre-existing hazard of that heredoc.)
- **The first test of the stub passed a mutation** that made it always run
  the real command; the test now asserts the guard line itself.
- **`qmllint` and the preview target**: assigning an overlay member
  (`overlay.voicesOnDisk = ...`, or `overlay["name"] = ...` directly) in a target
  fails the check; it goes through a `poke()` helper (memory note already
  there). Two runs of the check were lost to it.
- **The new QML is unlinted until staged** (memory note): I staged before every
  check run.
- **A test sliced the page's source on a comment**, which the comment-blanked
  source no longer has; it fails, not passes, when that happens. Sliced on a
  property instead.
- **The `voices` target now needs `PREVIEW_REAL_VOICE=1`**, because the stub
  intercepts `agentvoice voice` otherwise. Stated at its top. It was not run
  (below).
- **My re-read**: a voice being downloaded would have vanished from the
  Downloaded list the page now opens on (the row, and its progress bar, are
  not on disk yet); it stays while it is `fetching` or queued, and a test holds
  it.

## Not verified

- **The page in the real shell.** Needs `omarchy-restart-shell` (not run).
  Seen only in `preview.sh`. Until it, the running shell has M24's Voice page.
- **Live: Test and Use for.** The plan's live check. The stub only logs: no
  sample was played and no voice fetched or removed on this machine. The old
  `voices` target (the real fetch of `en_GB-alba-medium`, 63MB, and a sample
  through the speakers) was updated for the new selector but **not run**:
  it writes to the real voice library and plays audio.
- **Remove with the trash against the real library**: logged by the stub.
- **A real downloading row**: its progress bar in the Downloaded list was
  read from the code (the filter keeps it) and not seen drawn.
- **The narrow layout** (below 560 px): the crop cuts the overlay's edge.
- **Keyboard**: Tab through the search, the selector and the rows was not
  driven (the preview never takes the keyboard).
- **Whisper models beyond the three**: deferred, not built.
- **The installer box** (`install.sh` did not change).
- **The Codex review** (bypassed, not owed).

## Going back

`bin/agentvoice-deploy d4ad068d3bff` from the clone, `./install.sh --yes` once
the daemon is idle (nothing in the daemon changed, so it is not needed for
this), then `omarchy-restart-shell`. Nothing stored changes: no setting was
added, moved or rewritten, and the page's own filter and search are not
saved.

## Open issues, for the next phase

1. **Codex review bypassed** for M25 (user decision, 2026-11-22). M12 stays
   "review owed".
2. **Whisper models are not pinned** (plan question 10). Default taken:
   deferred. Pinning `tiny.en`, `base.en`, `small.en` and `medium.en` in
   `models.lock`, a verified fetch and a local-path loader is its own phase,
   best on Opus, with the box run and a memory/time measure per model.
3. **The filter is one choice, not combinable.** Default: as built; the
   search box does the combining ("british female").
4. **The agent rows are read-only.** Default: as the plan says (voice and
   speed keep their home on the Agents card); inline editing would be a
   second home for a key `FIELD_HOMES` forbids.
5. **The pinned-revision paragraph sits under the search box** at a small
   size. Default: as built; it could go into a `?` on the "VOICES" title.
6. **Carried, still open**: M24's 2–6; M23's 2–7; M22's 2–7; M21's 2–7; M20's
   2–8; M19's 3–6; M18's 2–6; M17's 2–7; M16's 2–9; M15's 2–8; M14's 2–7; M13's
   2–9; M12's 2–7; M11's 1–7; M10's 1–8; M9's 2–7; M8's 2–11; M7's 2–7; M6's
   1, 3, 4; M5's 1, 4–6; M4's 4–13; M0's small test and bench fixes; agy's
   `carries_session_across`; the runner's sandbox test command.
