# Phase M27: Agents speak up when background work finishes

Written 2026-11-23, unattended (started by the runner script). Branch
`phase-m27`, cut from `phase-m26` at 89b7c59. Result commit: the notes commit
on top of ca3a9a4, pushed to `fork/phase-m27` only; `dev` fast-forwarded to it
and pushed to `fork`. Model: Claude Opus 5.5 (xhigh, tier A).

Commits:
- ce50b5f: the phase;
- 3bec4a3: the test suite showed real desktop notifications (found by the
  first live check, below);
- ca3a9a4: a lock in the seconds before a finish is said lost it (found by
  the live lock check, below);
- then these notes.

**Codex review: bypassed (user decision, 2026-11-22).** Codex was not run, for
review or anything else. In its place I re-read the whole diff before each
commit and ran 40 mutations of the new code against the new tests; what that
found is under "Found along the way". Nothing in this phase has been reviewed
by a second model.

Deployed: **yes**, three times, through `bin/agentvoice-deploy --install
--wait 120` with the daemon idle (state `listening`, no open mic, every agent
idle), each time after its strict check (5302, 5303, then 5306 passed):
- ce50b5f replaced M26's 6fe6536;
- 3bec4a3 replaced ce50b5f;
- ca3a9a4 replaced 3bec4a3 ("deployed ca3a9a4adbf9. The way back:
  bin/agentvoice-deploy 3bec4a3cfbf4"). **The way back to before M27 is
  `bin/agentvoice-deploy 6fe65361e6cb`.**

Installed: **yes**, each time; last "Build 0.2.0 (ca3a9a4), replacing 0.2.0
(3bec4a3)". `agentvoice about` on the final install: settings ca3a9a4adbf9
(detached), service 0.2.0 (ca3a9a4), installed 2026-11-23T17:20:44-07:00,
"The settings and the service are the same build". Service `active`, state
`listening`, every agent idle afterwards.

**No setting was written.** `shell.json` is byte-identical to the copy taken
before the first deploy (`~/agentvoice-notes/shell.json.before-M27`, 0600),
checked after each deploy and after the live checks. The live checks used the
crew link Theo → Sora that was already there (set at stop 2).

**Shell restart needed** (`pages/AgentsPage.qml`, `Chats.qml`, `Settings.qml`).
Not run. Until it is, the running shell has no "Speak up when work finishes"
switch on the Agents page and does not mark unprompted lines in Chats; the
daemon speaks up already (the setting defaults to on) and the readout's extra
line comes from the daemon, so it shows now.

`./bin/agentvoice-check`: green on the final tree (exit 0, no FAIL line).
- **5306 tests** (M26: 5177; +86 test_announce, +34 test_background, +9
  test_collab), 14 of 14 static checks, "the check wrote nothing in the tree:
  ok". 7 min 3 s.
- **Bare runner** (`/tmp/ci`, requirements-dev only, no numpy,
  `AGENTVOICE_STRICT=1`): test_announce, test_background, test_collab,
  test_crew, test_settings_pages, test_adapters on the final tree: 776
  passed, none skipped.
  The whole bare suite was not run.
- The 39 warnings are fork() in a multi-threaded process in three test files;
  the base tree (89b7c59, run in a temporary worktree) has the same 39.
- Box: not run (`install.sh` did not change).

## The spike

Plan: "in a warm `claude -p` stream-json process start a background command
(`sleep 20; echo done`) and a background sub-agent, let the turn end, and see
whether new assistant output arrives when they finish." Three real turns'
worth, Claude Code 2.1.330 with Haiku, in scratch folders under /tmp, only
`Bash(sleep *)`, `Bash(echo *)` and the Agent tool pre-approved
(`--permission-mode dontAsk`), no hook, no MCP server. Recorded, reduced to the
fields the adapter reads, in `tests/fixtures/background/`:

- **claude-bash.json**: the turn started `sleep 20; echo done-alpha` with
  `run_in_background` and ended (`result` at 3.1 s). With nothing written to
  stdin, at 22.3 s the process wrote `task_updated`, `task_notification`
  (status completed), `background_tasks_changed` (empty), then **a whole turn
  of its own**: `init` at 22.4 s, words from 23.2 s ("The background command
  finished with exit code 0. It was `sleep 20; echo done-alpha`, so it printed
  `done-alpha`."), `result` at 23.4 s. A second turn written at 53 s answered
  normally.
- **claude-agent.json**: the same with a background sub-agent. Its own lines
  (marked `parent_tool_use_id`) streamed between turns, its inner Bash had a
  notification of its own (`owned_by_subagent` on its start), then the
  Agent's `task_notification` and an unprompted turn ("The background
  sub-agent finished. Its result was `sub-done-bravo`, as you asked.").
- **claude-race.json**: with `--replay-user-messages`, and the second message
  written the instant the notification was read: the CLI answered the
  notification first (its own `init` … `result`) and then our turn (`init`,
  **our echo**, NEXT, `result`). The echo of each written message comes after
  that turn's `init`, before its first words; a turn the CLI takes by itself
  has none.

So **tier 2 is built**, not deferred. And the spike found a **pre-existing
bug**: nothing read a warm process's stdout between turns, so that unprompted
turn waited in the pipe, and the next turn's reading -- which stops at the
first `result` -- took it for its own. Any Claude agent that started background
work and was spoken to again within five minutes answered the new question
with the background report, and the real answer arrived one turn late.

## What was built

**`daemon/announce.py`** (new, pure apart from two commands with injectable
runners): `Event` and what refuses a forged or malformed one (a source the
daemon does not track, no such agent, no key, not a finish, a crew event
carrying text); the fixed lines and the fixed notification text; `spoken_part`
(markdown flattened by `speech_text.make_speakable`, at most 300 characters,
cut after the last whole sentence that fits, else at a word with "…");
`Announcer`, the queue (dedupe by agent+source+key for an hour, 16 at most,
oldest first, one line per agent per 120 s with an agent's lines kept in
order, 300 s to be said or it expires, `may_notify` on the same limit);
`notify()` (`notify-send --app-name=Agent Voice -- TEXT`, stdin closed, 5 s,
never raises); `silenced()` (Omarchy's `omarchy-shell notifications isDnd`,
then the `quiet.json` the shell saves the switch in; no file is off, the
shell's own default; a file that cannot be read is on).

**Tier 1, crew work the daemon tracks** (`collab.Runtime._announce_finish`,
from `turn_ended`): a `delegate` an agent started with `report_back` that
completed or failed is one event for the caller. A stop is the person's own
doing (no event), a delegation without `report_back` already has its news said
by the target, and one whose result the Crew map would now withhold (link
deleted, quarantine moved) is not announced. **The line is fixed, in the
caller's voice**: "The task I gave Sora is done, and I have the result." /
"The task I gave Sora didn't finish." The result itself still reaches the
caller at the start of its next turn, as before, and the follow-up window
after the line makes that one sentence away. Notification: "Sora finished a
task for Theo".

**Tier 2, Claude Code's own background work** (`adapters/claude_code.py`):
- **`Pump`**: one thread per process reads every stdout line from its first
  turn on. A turn registers (`begin`) before it writes and gets its lines in
  order from a queue; lines with no turn registered go to `Between`; lines
  already queued behind a turn's `result` are handed back when it ends.
- **`Between`**: tracks `task_started` with `is_backgrounded` (not a
  helper's), `task_updated` moving one to the background, `background_tasks_
  changed`, and `task_notification` for one of its own tasks, completed or
  failed (taken off as read, so a second report is not a second finish;
  killed/stopped say nothing). It reads an unprompted turn's top-level words
  (no thinking, no helper's text) and at its `result` hands an `Unprompted`
  (task ids and statuses from the CLI, the words, the session, when the
  finish was read) to `on_unprompted` on a thread of its own. **An unprompted
  turn with no finish of ours before it is read and dropped.**
- **`--replay-user-messages` on every Claude turn**: until a turn's own echo,
  lines that belong to an unprompted turn (a finish read, or one under way)
  are held and read as that turn's, and its `result` does not end ours; at the
  echo everything is ours, held lines included (the CLI folded the finish into
  our turn). A finish a turn of ours began on that got no turn of its own
  within 5 s was answered there.
- **The idle let-go waits** while background work runs -- or a finish of it
  is still to be said (`Between.pending`, ca3a9a4) -- up to 30 minutes after
  the last turn (`BACKGROUND_KEEP_S`); `background_running()` answers the
  same.
- `_take` keeps its three-value return; `send()` finds the pump with
  `_pump_for`, which also gives a process the adapter did not spawn (a test's)
  one of its own.

**Delivery** (`wake_listen.py`, one commented block after `_say_for` plus
hooks):
- `background_finished` takes an `Unprompted` only from the agent's current
  adapter and current conversation; `announce_event` (any thread) reads
  `speakWhenDone` fresh, queues the event and shows the notification at once.
- `announce_poll`, every pass of the run loop above the listening gate: a stop
  noted by the signal handler, stale events, and -- **locked, mic lent out,
  muted, notifications silenced** -- everything waiting taken as shown and
  recorded unsaid, never kept to be said on the way back.
- `deliver_announcements`, below the gate: only between captures or in an
  open-mic window nobody has started speaking into, never in a reply's
  follow-up window; not while anyone is speaking, `_hold_speech` is set, a
  floor lease is held, or a turn somebody asked for is in flight (a task turn
  working quietly for another agent does not hold it; the agent's own turn
  holds its own line). With extra agents the line is said on a thread of its
  own through the floor; with one agent on the run loop, which then opens the
  usual follow-up window itself.
- **An announcing thread never stops its agent** (whose process may still be
  doing other background work): `speak()` returns on a lock instead of calling
  `silence()` there, and the interrupt keybind cuts the line only.
- The readout shows the agent speaking (`_announcing` counts as busy in
  `_compose_line`), `unprompted: true` and a `notice` line ("Theo: background
  work finished"); a lock strips both.
- `_record_unprompted`: one structural journal line per event that leaves the
  queue (the words only with `logSpeech`), and the history and the agent's open
  chat (never a new one) get the whole text marked unprompted (`kind:
  "unprompted"` in a chat; `unprompted`, `said` in the history). A crew line is
  recorded only if it was said.
- `collab.stop_from` / `stop_all` drop what waits to be said (from the signal
  handler only noted).
- **A lock no longer stops an idle agent's background work** (`silence()`):
  an agent with no turn under way whose adapter reports `background_running()`
  keeps its process, as a delegated task always did; its finish is a
  notification only. A turn under way still stops, and so does an idle
  process with nothing running.

**The setting**: `mainSpeakWhenDone` / `voiceAgents[i].speakWhenDone`, bool,
default on (question 8); only a bool counts, so anything else, an unknown agent
or unreadable settings is off. Manifest schema and defaults, `runtime.DEFAULTS`
with a TOML alias, `Config.speak_when_done_for`, and **Speak up when work
finishes** on each agent's Voice card (a `ToggleRow`; an extra agent's on
writes nothing, off writes `false`), with a hint per program: Claude Code
(both kinds), Codex (only tasks it gave out: its own work ends with each turn),
anything else "Nothing to announce". `FIELD_HOMES` has the field.

**Chats and history**: "NAME (unprompted)" in a saved chat and in the session
view.

**Preview**: target `speakup` (Theo, Sora and Hazel from `crew3.json`).

**Docs**: README ("Speaking up when background work finishes"), SECURITY (a
limitation: background work keeps going behind a lock), CLAUDE.md (the lock
paragraph, and "A warm process talks between turns"), CODEBASE, CHANGELOG,
FINDINGS §57.

## What was proven, and how

- **The recordings through the real adapter** (`tests/test_background.py`, its
  pump thread, turn queue and echo): every turn gets its own reply and each
  finish is handed on exactly once with the CLI's words, for the command, the
  sub-agent and both orders of the race; **the next turn is its own even when
  the whole unprompted turn waited in the pipe** (the pre-M27 bug); an
  unprompted turn with no finish before it is dropped; a finish the CLI folds
  into our turn is ours (only the echo tells); a turn the CLI takes right
  behind ours is handed on; the helper's own command is not a finish; a
  notification for a task never started is not one; the same finish reported
  twice is one; killed/stopped say nothing; only top-level words, never
  thinking; the grace rule both ways; the let-go waits for background work and
  not for ever; a finish still to be said keeps the process (ca3a9a4); and a real subprocess stand-in for `claude` (real pipes, a
  background job finishing 0.4 s later), written to before and during the
  unprompted turn.
- **The queue and the daemon** (`tests/test_announce.py`): fixed lines and
  notification text with a canary in the model's words absent from them and
  from `notify-send`'s argv; a label cannot carry a newline or control
  character into it; a missing or failing notification service reported, not
  raised, and the line still said; the 300-character cap; forged and malformed
  events refused; dedupe, bounds, rate limit (per agent, order kept), expiry,
  drops; silencing from the shell, then the file, every unreadable form quiet;
  the setting's defaults, bool-only, unreadable off, unknown agent off; in the
  daemon: shown at once and said at a quiet moment; the chat gets all of it
  marked unprompted while the voice says at most 300 characters; no chat
  started; **locked, muted, lent and silenced are the notification only, with
  nothing on screen, and nothing is said after**; switched off before or while
  waiting; never over somebody speaking, talking or waiting for a reply; a
  quiet task turn does not hold it, the agent's own turn does; two agents one
  after the other; the rate limit with one popup for a burst; stale recorded
  unsaid; stops drop lines (from a signal only noted); an earlier
  conversation's or a replaced adapter's finish refused; a failure said as
  one; the follow-up window after a line said and not after one cut short or
  unsaid; the readout's speaking payload and the lock stripping it; the lock
  sparing an idle agent's background work but not a turn under way; repeated
  locks sparing it until its finish is said; the
  interrupt and a lock arriving at the last moment cutting the line without
  stopping the agent; only collab and the adapter's stream reach
  `announce_event`.
- **The frame loop** (`tests/frame_loop.py`, the real `Daemon.run`): queued
  behind a lock it is never said, not after the unlock either; queued during a
  capture it is said only after the capture, the turn and the reply's whole
  follow-up window; after it the usual window opens.
- **Tier 1 through the real call path** (`tests/test_collab.py`,
  `TestM27CrewWork`: the call socket, the board, real turns): one event for the
  caller with the fixed fields; the fixed line in the caller's voice holding
  none of the task or the target's words; the result still delivered at the
  caller's next turn; no event without `report_back`, for a stopped task or
  after the link was deleted; a failure says so; switched off, nothing shown or
  said; one event per task.
- **Mutations: 40, all red at the end** (scratch copies in /tmp, never the
  clone). 33 of the first 38 were red on the first run; the 5 that survived
  were gaps in the tests, each closed (below); 2 more on ca3a9a4's fix
  (`pending` back to `outstanding`, in `background_running` and in the
  let-go), both red. They covered: the notification text and argv
  holding model text; lock, mute and silencing each ignored; silenced lines
  kept for later; the room never busy; no rate limit, dedupe or expiry; a
  non-bool or unreadable setting speaking; the setting not read again before
  speaking; an unprompted turn with no finish announced; any notification a
  finish; no echo boundary; foreign lines read as ours; lines behind a result
  dropped; the grace announcing covered finishes; the let-go ignoring
  background work; a lock killing background work, or sparing a busy agent;
  the speak() guard removed; the interrupt stopping the agent; an earlier
  conversation's or another adapter's finish said; tier 1 without
  `report_back`, for a stop, past a deleted link; stop_from keeping lines; the
  follow-up window missing, or opened after an unsaid line; delivery inside a
  follow-up window; the spoken part uncapped; a crew event with text; the lock
  leaving `unprompted` on screen; an unreadable quiet file read as off.
- **The resume fixture re-recorded** with the new flag
  (`tests/fixtures/resume/claude-level-and-model.json`): three real turns
  through `ClaudeCode` as the test builds it, Ask/Haiku → Trusted/Sonnet
  resuming → Ask/Haiku resuming; the marker (PELICAN-6914) recalled both ways,
  and each turn carried its echo.
- **Preview `speakup`, 10 of 10 checks, dark and flexoki-light** (synthetic
  clicks, scratch config with the write round trip, the real pointer never
  moved): the switch on Theo's Voice card, on by default, Claude's hint; off
  writes `mainSpeakWhenDone false`, on writes `true`; Sora off writes her entry
  with `speakWhenDone: false` and every other field kept (including an unknown
  one), on again leaves the field out; Hazel's hint says Codex announces only
  tasks. The write log is exactly those four lines. Screenshots in /tmp/m27
  (not committed).
- **Live, typed, on the installed build**: see the checklist at the end.

## Shared files touched, and where

- `daemon/wake_listen.py` (big shared, +396/−5): `import announce`, `ANNOUNCE_NOTE_S`; four attributes in
  `__init__`; `silence()` (an idle agent's background work kept); `_on_interrupt`
  (an announcement cut first); `apply_extras` (the adapter's `on_unprompted`);
  `speak()` (an announcing thread returns on a lock); the new block after
  `_say_for` (`background_finished` … `_record_unprompted`); `_compose`
  (`unprompted` stripped on lock, the notice line); `_compose_line` (an
  announcing agent shown speaking); `run()`: `announce_poll` above the gate,
  the note's expiry in the 2 s poll, and the delivery hook with the
  one-agent follow-up window before the wake test.
- `daemon/collab.py` (big shared, +43): `turn_ended` (one call),
  `_announce_finish`, `stop_from`, `stop_all`.
- `daemon/adapters/claude_code.py` (+383/−22): `Between`, `Pump`, `is_echo`,
  `_parse`, the flag, `_spawn`, `_hand_unprompted`, `background_running`,
  `_expire`, `_own`, `_pump_for`, `send()` (reads its queue; the foreign and
  echo handling; `pump.end` and `_idle_since` in its `finally`).
- `pages/AgentsPage.qml` (big shared, +32): `putAgentSpeakWhenDone`, two
  `writeField` cases, two properties on the agent block, the `ToggleRow` at
  the end of the Voice card.
- Also: `daemon/adapters/base.py` (`Unprompted`, `on_unprompted`,
  `background_running`), `daemon/runtime.py`, `daemon/chats.py` (one kind),
  `manifest.json`, `Settings.qml` (one history role), `Chats.qml` (two marks),
  `tests/conftest.py` (the notification stand-in, in 3bec4a3).
- New: `daemon/announce.py`, `tests/test_announce.py`,
  `tests/test_background.py`, `tests/fixtures/background/` (three recordings),
  `bench/preview/targets/speakup.qml`.
- Not touched: `Hud.qml`, `daemon/crew.py`, `Panel.qml`, `permission_hook.py`,
  `install.sh`, `models.lock`.

## Measured

FINDINGS §57, in short:
- **Finish to notification: median 3.37 s; finish to first sound: median
  4.33 s** (five typed runs on 3bec4a3: 3.37/4.33, 2.39/3.27, 3.44/4.39,
  2.63/3.36, 5.87/6.85). "Finish" is when the daemon read the CLI's
  `task_notification`. Nearly all of it is the CLI's own turn about the
  finish (its words are what is said); notify-send itself takes tens of
  milliseconds, and the first sound follows the notification by 0.7–1.0 s.
- A delegated task: notification **0.06 s** after it ended; the caller's line
  8.92 s after, having waited out the target's own follow-up window.
- The spike: the CLI's own turn began 0.02–0.11 s after each finish and ended
  1.1 s after it.
- Tests 5177 → 5306; the check's test run 6 min 9 s (M26: 6 min 0 s).
- Nothing else is claimed faster or smaller.

## Different from the plan, and why

- **Tier 1's line is fixed, not a model turn.** The plan says a finished task
  "is queued as an unprompted turn for the caller". But the target of a
  delegation already says its result out loud in its own voice (Phase 16), so
  a line the caller's model wrote from the result would say it twice; a real
  turn in the caller's warm process could act, which the security table's
  "speech only, no actions" forbids; and a quiet side turn would carry another
  agent's text into speech through a model. A fixed line says the news,
  carries no model text, costs nothing, and the follow-up window makes the
  caller's real turn (which gets the result) one sentence away. Open issue 2.
- **Only delegations with `report_back` count for tier 1.** Without it the
  target's own spoken result is the news, and the caller asked for nothing back.
- **The lock changed** (`silence()`): an idle agent's background work survives
  it. The plan's "notification only while the screen is locked" means nothing
  if a lock kills the work first, which it did. Open issue 3.
- **Every Claude turn carries `--replay-user-messages`**, which the plan did
  not list: the race recording shows it is the only exact boundary between a
  turn of ours and one the CLI takes by itself. It meant re-recording the resume
  fixture (three real turns).
- **The warm process is kept for background work** up to 30 minutes past the
  idle let-go: letting it go after 5 minutes killed any longer job silently.
  Open issue 4.
- **The notification is shown when the event is accepted, the line when the
  room is quiet** (the plan measures the two apart, so they are apart). Both
  are limited to one per agent per two minutes.
- **The HUD needed no QML change**: the daemon's `notice` line (the M22
  mechanism) says why the agent is talking, and the reply line shows the
  words. `Hud.qml` and `daemon/crew.py`, in the plan's file list, were not
  touched; `chats.py`, `Chats.qml` and `Settings.qml` were, for the
  "unprompted" mark.
- **"Nothing is capturing" read as**: no capture somebody is speaking into or a
  wake word or key opened (`_hold_speech`), and not a reply's follow-up window;
  an open-mic window nobody is speaking into does not hold it (otherwise an
  open microphone would hold every announcement for up to ten minutes).

## Found along the way

- **Pre-existing (the spike): the next question got the background report as
  its answer.** Described under "The spike"; fixed by the pump and the echo,
  and held by `test_the_next_turn_is_its_own_even_when_the_report_waited_in_the_pipe`
  and the race tests.
- **Pre-existing: a lock killed every idle agent's background work**, through
  `silence()` cancelling every adapter. Changed on purpose (above).
- **Mine, found live: a lock in the two seconds before a finish is said lost
  it.** The first lock check held `agentvoice lock` (each call renews its
  10 s hold, and each runs `silence()`) across the job's end: the journal
  showed the Bash call, twelve locks, and **no announcement and no
  notification**. Once the finish was read, `Between.outstanding` was false
  while the CLI was still taking the turn in which it says so, so the next
  lock's `silence()` found no background work, cancelled Theo's process
  mid-turn, and the finish was gone. A real lock or the idle let-go landing in
  those seconds does the same. Fixed in ca3a9a4 (`Between.pending`: running
  work, a finish read, or an unprompted turn under way); two adapter tests
  replay the recording to that moment, a daemon test locks three times, two
  mutations go red; the same live check then gave "locked" and the
  notification.
- **Mine, found live: the test suite showed real desktop notifications.**
  Collaboration tests (older ones, not M27's) that finish a delegation with
  `report_back` went through the real `announce_event` to the real
  `notify-send`: Omarchy's notification history held **24 "Sora finished a task
  for Theo"** from six suite runs (four each, at 15:46, 15:50, 16:05, 16:12,
  16:15 and 16:22), beside the one real "Theo finished a background task" the
  live check sent. `silenced()` also asked the real shell. Fixed in 3bec4a3:
  `announce._run` is looked up at call time and a conftest autouse fixture makes
  it run nothing; a test holds it, and a run of test_collab afterwards added no
  entry. **The 24 entries are still in the person's notification history**; I
  did not remove them (it is their desktop's history, and every one carries the
  fixed text).
- **Five mutations survived the first run**, each a weak test: muted was
  checked only by "not said", which the speaker's own `listening` check
  already gives, so a readout showing the line while muted went unseen (now:
  nothing on screen, and the journal names the reason); the lock in the
  speak() guard test landed after the guard (now it lands in `poll_session`,
  just before); "no window after an unsaid line" was tested only while locked,
  where nothing opens anyway (now with the interrupt, the room still
  listening); "not inside a follow-up window" asserted nothing a window-time
  delivery broke (now: at least the window's length after it opened); the
  quiet file's unreadable branch had no case (now a directory at its path).
- **My first `send()` returned the pump from `_take`**: a test that fakes
  `_take` with three values broke, so `_take` kept its return and `_pump_for`
  finds the pump. Partial daemons built without `_main` (test_tool_controls)
  broke the wiring in `apply_extras`, now guarded; `FakeAgent` has no
  `background_running`, so `silence()` asks for it with `getattr`.
- **My re-read of the diff** found: an unsaid crew line was going into the
  chat as if the agent had said it (now journal only); and the race case in
  which our own turn errors before its echo while a finish read a moment
  earlier is still waiting -- the error `result` would be taken for the
  unprompted turn's. The recording shows the CLI answers the finish first, so
  this needs it to answer ours first *and* fail before the echo; left as is and
  written in open issue 7.

## Not verified

- **By voice, at stop 5** (the plan's live list): "Theo, run a 30-second
  background job and tell me when it's done"; again with `agentvoice lock`;
  again with notifications silenced; again while talking. Typed equivalents of
  the first two ran (below); the voice ones need the person.
- **Silencing live**: not run. Turning Omarchy's do-not-disturb on and off
  unattended would change the person's desktop, and a failed restore would
  leave it silenced. Proven by tests (the shell's answer and the file).
- **"While the user is talking"** live: the frame-loop test drives it; no live
  capture was possible unattended.
- **The switch and the "(unprompted)" marks in the real shell**: need
  `omarchy-restart-shell` (not run). Seen in `preview.sh` only.
- **Hearing it**: the journal says each line was said and when the first
  sound went out; whether the voice, its volume and its timing are right needs
  ears.
- **A background sub-agent finishing, live through Agent Voice**: the spike
  recorded one through a bare `claude -p`; the live checks used a background
  command.
- **The readout's extra line** ("Theo: background work finished") in the real
  shell: in the state file and the tests, not looked at on screen.
- **Codex as the caller of a tier 1 task**, live: tests only.
- **The narrow layout** of the new row: dark and light at 1100×760 only.
- **The Codex review** (bypassed, not owed).

## Going back

`bin/agentvoice-deploy 6fe65361e6cb` from the clone (M26), then
`./install.sh --yes` once the daemon is idle, then `omarchy-restart-shell`.
Master plan 7.7 step 1 first: drain announcements, which an older build would
never say -- there is nothing stored to drain (the queue is in memory and goes
with the daemon). An older build:
- never speaks unprompted and returns to next-turn reports;
- ignores `mainSpeakWhenDone` / `speakWhenDone` (none is written on this
  machine; everything is at the default);
- reads no stdout between turns again, so the pre-M27 bug comes back: after a
  Claude agent's background work finishes, its next turn answers with the
  background report;
- kills an idle agent's background work on a lock and after five idle minutes;
- shows saved chats' `kind: "unprompted"` exchanges as plain replies with no
  transcript, and the history's extra fields are unread.

## Open issues, for the next phase

1. **Codex review bypassed** for M27 (user decision, 2026-11-22). M12 stays
   "review owed".
2. **Tier 1 says a fixed line** ("The task I gave Sora is done, and I have the
   result.") rather than a line the caller's model writes from the result
   (above, "Different from the plan"). Default taken: fixed. Should the caller
   write its own line (a quiet side turn, no tools), at the cost of repeating
   what the target said?
3. **A lock no longer stops an idle agent's background work.** It keeps
   running behind the lock, as a delegated task always did, and when it
   finishes Claude Code takes a short turn by itself: anything it asks about is
   refused while locked, but an agent at **Trusted can act in that turn without
   asking**, as in any of its turns (SECURITY.md says so). Default taken from
   item 24 ("stay silent while the screen is locked … show only the
   notification"), which needs the work alive. Keep, or stop background work on
   a lock as before?
4. **Background work is still lost, unannounced**, when the agent's process is
   let go: a new or switched chat for that agent, a setting that lets the idle
   process go (a tool switch, flags, a level or model rebuild), "Theo, stop"
   while a turn runs, `install.sh`/a daemon restart, or 30 minutes idle with
   work still running (`BACKGROUND_KEEP_S`). Should Agent Voice say "my
   background task was stopped" then, or hold the process longer?
5. **Full stop drops waiting lines but leaves idle background work running**
   (as before M27); its later finish is announced. Should "full stop" also stop
   background work?
6. **The numbers** (question 8's default on; 300 characters, 2 minutes, 5
   minutes, from the plan; 16 waiting at most, 30 minutes kept, 5 s grace,
   one popup per agent per 2 minutes): defaults taken, none measured against
   use.
7. **A race left open**: our turn written within milliseconds of a finish,
   the CLI answering ours first and our turn failing before its echo -- that
   error would be taken for the unprompted turn's and our turn would wait for
   the watchdog. Not seen; the recording shows the opposite order.
8. **Unprompted text in a saved chat does not say whether it was heard**
   (the session history does: `said`). Add it to the chat record?
9. **The 24 test notifications** in the person's Omarchy notification history
   (Found along the way) were left there.
10. **Carried, still open**: M26's 2–6; M25's 2–5; M24's 2–6; M23's 2–7; M22's
    2–7; M21's 2–7; M20's 2–8; M19's 3–6; M18's 2–6; M17's 2–7; M16's 2–9;
    M15's 2–8; M14's 2–7; M13's 2–9; M12's 2–7; M11's 1–7; M10's 1–8; M9's 2–7;
    M8's 2–11; M7's 2–7; M6's 1, 3, 4; M5's 1, 4–6; M4's 4–13; M0's small test
    and bench fixes; agy's `carries_session_across`; the runner's sandbox test
    command.

## Live checklist: what was typed, what happened

All typed (`agentvoice type main`, synthetic text on stdin) through Theo
(Claude Code, Opus, Trusted), with `agentvoice chats new main` before and after
each, so nothing went into the person's current chat. Read from `journalctl
--user -u agentvoice -o json`, structural lines only (`logSpeech` is off, so no
words reach the journal). The machine spoke the replies and the lines aloud.
Before the first deploy: state `listening`, no open mic, every agent idle,
silencing off, `shell.json` copied.

- **A. A background command finishing announces itself** (ce50b5f, then five
  times on 3bec4a3). "Use your Bash tool with run_in_background set to true to
  run exactly this command: sleep 20; echo m27-live-N. Do not wait for it …
  Then reply with only the word started." Each time: `[Bash]`, the turn
  (7–9 s), then about 20 s later "announce Theo: background completed,
  notification shown 2.39–5.87s after it finished", "announce Theo: said
  (78–140 chars) …", "background completed, said". Omarchy's notification
  history gained one "Theo finished a background task" per run, from app
  "Agent Voice", with an empty body.
- **B. A delegated task finishing announces itself** (3bec4a3). "Use your
  delegate tool to give Sora this task, with report_back set to true: say
  exactly the words crew check m27 and nothing else. Then reply with only the
  word delegated." Journal: `[mcp__agentvoice-crew__delegate]`, "delegate
  19dcea7bebb32c3e: Theo → Sora (agent)", Theo's turn 12.9 s, "Sora has the
  floor (replayed)", Sora's turn 6.2 s, "result kept for Theo (completed, 15
  chars)", "announce Theo: crew completed, notification shown 0.06s after it
  finished", "announce Theo: said (52 chars) 8.92s after it finished" (52 is
  "The task I gave Sora is done, and I have the result."). History: "Sora
  finished a task for Theo". Theo's next typed turn: "Theo: 0 message(s), 1
  result(s) delivered" -- the result still came with it.
- **C. One `agentvoice lock` after the turn** (3bec4a3). The lock lapsed after
  its 10 s hold (the poll found the session unlocked, as designed for a lock
  the compositor does not confirm), so the finish came unlocked and was said
  (2.51/3.33 s). What it did show: **the job survived the lock**. Before M27
  `silence()` cancelled Theo's idle process on a lock, and the `sleep` with
  it.
- **D. The lock held across the finish.** On 3bec4a3: the Bash call, twelve
  locks, then **nothing at all** -- the bug fixed in ca3a9a4 (Found along the
  way). On ca3a9a4: "announce Theo: background completed, locked (102
  chars)", "notification shown 2.30s after it finished", then "screen unlocked
  (told, not polled)" and 15 s with **nothing said** on the way back. History:
  one more "Theo finished a background task".
- Not run live: silencing (it would change the person's desktop), anything by
  voice, "while the user is talking" (Not verified).
- Afterwards: service `active`, state `listening`; `shell.json` byte-identical
  to the copy. Omarchy's notification history holds 33 entries from "Agent
  Voice": the 24 the suite leaked before 3bec4a3, and exactly one per live
  check that should notify (A ×6, B, C, D on ca3a9a4); none from the three
  suite runs since the fix.
