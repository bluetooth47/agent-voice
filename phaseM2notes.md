# Phase M2: Daemon bug sweep (I, J, K, C, testresults #10)

Written 2026-11-21, unattended (started by the runner script). Branch
`phase-m2`, cut from `phase-m1` at 2adb15f. Result commit: the notes commit
on top of a2deeb6, pushed to `fork/phase-m2` only. Model: Claude Opus 5.5,
xhigh.

Commits: 0be9572 (the sweep), eb60501 (Codex pass 1 fixes), a2deeb6 (Codex
pass 2 fixes), then these notes.

Deployed: **yes**, a2deeb6 through `bin/agentvoice-deploy --install` (its
strict check green in a fresh worktree, 2918 tests), daemon idle (state
`listening`, every agent idle, open mic off). It replaced 103439366e47 (the
way back: `bin/agentvoice-deploy --install 103439366e47`). Installed: **yes**:
build 0.2.0 (a2deeb6) replaced 0.2.0 (92c71ff-dirty), the service is active
and the state file carries `limit_hits`. This was the first `install.sh`
run through M0's symlinked plugin path, which M0 left not verified: it
installed from the checkout. **Shell restart needed** for the QML
(`Panel.qml`, `Settings.qml`, `pages/ConversationPage.qml`): not run, stop
point 1.

`./bin/agentvoice-check`: green, **2918 tests** (was 2843; +75), 14 of 14
static checks, "the check wrote nothing in the tree: ok". Box: not run
(`install.sh` did not change).

## What was built

Each bug was reproduced before it was changed: I and J from the journal and
three recorded real turns per backend, K and C in the real frame loop (a new
driver, below), #10 by reading `_compose_line` and driving a typed turn.

**I. A permission or model change keeps the conversation.** The journal
shows it plainly: 2026-11-19 00:20:51, Trusted → Ask in open mic, the main
agent rebuilt, and the next two turns judged "not meant for it" by a session
with no history (FINDINGS §41).
- `reconcile_agent` (main) and `_rebuild_persona` (extra agents) still build
  a **new adapter** for any change of program, folder, endpoint, level or
  model, and cancel the old one: no process started under the old flags
  takes another turn.
- The new `daemon/sessions.py` decides whether the conversation survives:
  a new program, endpoint or folder ends it; a new level or model keeps it
  if the adapter's new `carries_session_across` covers it. **Claude Code and
  Codex** carry `{"level", "model"}`, each earned with three recorded real
  turns (ask → trusted with another model → ask, each on a new adapter
  object, a marker recalled both ways): `tests/fixtures/resume/`, replayed
  in `test_adapters.py`, which also checks today's argv equals the recorded
  one. **agy** could not be recorded (not signed in here) and keeps the old
  behaviour.
- A dropped conversation **says why**: the journal line `agent “X”: new
  conversation — <reason>`, and a `notice` in every non-locked state
  payload until that agent's next turn, shown on the HUD's extra line
  (`Panel.qml`).
- A kept conversation **loses its "allow all in this chat" grants on any
  level change** (new `permission_hook.revoke`), Ask ↔ Edits included. If a
  grant cannot be withdrawn (folder unlistable, a grant unreadable or
  undeletable) the conversation is dropped instead: fail closed.
- `catch_up_flags()`: a level or folder that moved while an agent was busy
  is applied **before its next turn starts** (in `dispatch()`, and in the
  single-agent path before `answer()`); a turn for an agent deleted or
  switched off meanwhile is refused. `adapter_stale()`, which collaboration
  calls check, now counts Ask ↔ Edits too. (Codex findings; pre-existing,
  fail-open.)

**J. The surprise "be-deep" chime.** The two-note `wake` chime. In the
journal both wakes inside open mic (11-21 00:38:49 and 16:34:18) were the
agent's own name heard while it worked: the turn was stopped and the chime
played over a microphone that was listening already.
- Every chime that plays logs `chime: NAME (why)` (wake word / the wake word
  stopped the reply / end of what was said / a Ns turn ended).
- A wake for the agent the open microphone is already listening for re-arms
  **silently** (`listening_for`), logging `chime: wake not played (open mic
  was already listening)`. The wake still stops the agent's turn, as before.
- Dropped open-mic turns (not meant for it, nothing heard, too short) are
  shown to keep the session id and the saved chat.

**K. "Still listening" after open mic off.** Nothing ended an empty open-mic
window: it ran out its lead-in, which for the open microphone is the rest of
`openMicIdleMin` (up to 600 s). Now it closes on the frame `open_mic` goes to
None (≤ 200 ms after `agentvoice open-mic off`, frame loop); a capture
somebody is speaking into finishes and is sent. Follow-up payloads carry
`window`: `open` or `followup`, and the popup labels "OPEN MIC" only for the
open one.

**C. Turns cut at the limit.** Found while reproducing: the limit was
measured from when the window opened, so the open mic's wait cut any turn
begun more than `maxUtteranceMs` into it **at its first frame** — 18 of the
journal's 21 cuts were in open mic. It now counts from the first voiced frame
(from key-down with push-to-talk; a key held in silence also stops there).
Real cuts are counted in `limit_hits` `{date, today, last}` (sticky state
field, carried over a daemon restart through the old state file), with a
structural journal line, and the Conversation page shows one line under the
slider: "Cut 3 turns off at this limit today, the last at 20:47." (today's
date only; re-read each minute). The slider's description now says
"Counted from your first word."

**#10. Muted typed turns.** With several agents `_compose_line` put the
microphone's `off` over the agent's own state, so a muted typed turn never
showed (no HUD, stale "last heard", an agent shown speaking afterwards). Now
`off` shows the agent like `listening` does; payloads that name another
state while muted carry `muted: true`, and the popup's Mute button and hint
read `micOff` (state `off` or `muted`) so a muted user is never offered
"Mute" (a click that would unmute). With one agent, a muted typed turn no
longer leaves the state on `speaking`. A lock still wins over everything.

**Tests.** `tests/frame_loop.py` drives the real `Daemon.run()` over a
scripted microphone on a fake clock (200 ms of audio time per frame, actions
such as a command file between frames, every state payload recorded with its
time). New `tests/test_sessions.py`; additions to `test_adapters.py`,
`test_chimes.py`, `test_open_mic.py`, `test_states.py`, `test_typed.py`;
fixtures adjusted in `test_crew.py`, `test_collab.py`, `conftest.py` (the test
daemon's `fresh_config` is its own config).

**Mutations** (each reintroduced, each turned a test red, all restored): 11
on the sweep (a level change ends the session; the folder change unnoticed,
main and extra agents; revoke deleting nothing; the open-mic re-arm
chiming; the window not closed; the limit counted from the window; a cut not
counted; muted winning again; no `muted` flag; one agent left on
"speaking"), 9 on pass 1's fixes and 5 on pass 2's.

**Docs.** CLAUDE.md (the `carries_session_across` rule beside "a backend
earns its place with one real turn"; the frame-loop driver), CODEBASE.md
(states and fields, rebuilds, chimes, limit, open mic, `sessions.py`, the
adapters' resume notes, the test driver), FINDINGS §41, testresults #10
marked fixed (not yet seen live).

## Shared files touched, and where

- `daemon/wake_listen.py` (big shared): `Daemon.__init__` (`_notices`,
  `_main_level`, `limit_hits`); `reconcile_agent` (change set, level as a
  level, `carry_session`); new `carry_session`, `flags_moved`,
  `catch_up_flags`, `expire_notices` after it; `refresh` (notice expiry, day
  roll-over); `handle_typed` (publish after a single-agent typed turn);
  `limit_field` / `limit_hits_rolled` / `count_limit_hit` and
  `listening_for` beside `chime()`, which gained `why`; `answer` (the `done`
  reason); `adapter_stale` (level string); `_rebuild_persona` (rebuild then
  carry, actual cwd); `crew_fields` (`limit_hits`); `_compose` (`muted`,
  `notice`); `_compose_line` (`off` like `listening`); `dispatch`
  (`catch_up_flags`); the run loop: `spoke_at`, the open-mic window close
  after the command handlers, the two wake-chime sites, the `heard` reason,
  the limit check, the silent push-to-talk stop, `window=` on the three
  `followup` publishes, `catch_up_flags` before the single-agent `answer`.
  Module helpers `_today`, `_limit_hits_from`.
- `Panel.qml` (big shared): `micMuted`/`micOff`/`vWindow` properties, the
  state-file parse (notice, muted, window), the OPEN MIC label, the mic
  button and its hint.
- `Settings.qml` (big shared): `vLimitHits` and its parse.
- `pages/ConversationPage.qml`: the limit line (a `Hint`), its minute tick,
  the slider's description.
- `daemon/permission_hook.py`: new `revoke()` only; `decide()` untouched.
- `daemon/adapters/base.py`, `claude_code.py`, `codex.py`:
  `carries_session_across` only.

## Measured

FINDINGS §41, in short:
- Journal 2026-11-18 → 21 (3,530 entries, structural lines only): 45 wake
  chimes (2 inside open mic, both stopping a busy agent), 21 limit cuts (18
  in open mic), 3 "not meant for it" (all in open mic, 2 right after the
  level-flip rebuild).
- Recorded resumes: Claude Code 2.1.330 and codex-cli 0.171.0 both resumed
  the same session/thread under the other level and another model, both
  ways, and recalled the marker; agy 1.5.14: "authentication failed or timed
  out".
- K: `listening` ≤ 200 ms after `open-mic off` (frame loop); before, up to
  600 s.
- C: a turn begun 40 s into an open-mic window was cut at 40.2 s (its first
  frame) before; it now runs to its pause (42.6 s).
- Tests 2843 → 2918; the check's test run ~2 min 28 s, as before.

## Different from the plan, and why

- **C grew a fix.** The plan asked for a counter. Reproducing the cut showed
  most "cuts" were the limit measured from the window's opening, so counting
  them would have reported phantoms; the limit now counts from the first
  word. Same setting, same name, same default.
- **I covers extra agents too** (`_rebuild_persona`), not only
  `reconcile_agent`: the same bug, and one rule for both.
- **Model changes keep the session only on recorded backends**, and the
  plan's "effort" was already kept before M2.
- **Grant revocation** is new: keeping a session that used to be dropped
  would otherwise have kept an "allow all in this chat" past a lowered level
  (a fail-open the old drop prevented by accident).
- **More than the four named sites changed**: `catch_up_flags` in
  `dispatch()` and before the single-agent `answer()`, `adapter_stale`, and
  the silent push-to-talk stop came from Codex findings (pre-existing
  fail-opens and a pre-existing hang in the same code). The `muted` flag and
  Panel's `micOff` were needed so #10's fix could not make the Mute button
  lie.
- **The HUD notice** rides the existing extra line (`collab`'s), one Panel
  line, rather than a new HUD element.
- **Codex pass 1 ran in the clone** (`-s read-only`, as M1: `codex sandbox
  linux -- true` still panics "Failed to execvp linux", which is not a bwrap
  error, and `codex sandbox -- touch ~/x` fails read-only). It explored the
  repository despite the instruction and cost 21.11 credits. **Pass 2 ran on
  an empty read-only folder** (`/tmp/codex-review-M2`, the runner's copy
  procedure with nothing copied but the prompt) with the fix diff inline:
  3.55 credits. HEAD and status in the clone were unchanged after both; the
  folder was deleted.
- Not sent to Codex (to save credits): tests other than `frame_loop.py`,
  `test_sessions.py`, `test_open_mic.py`, `test_typed.py` in pass 1; docs;
  fixtures. Pass 2 saw only pass 1's fix diff; pass 2's fixes were not
  re-reviewed.

## Codex review

- **Pass 1** (10 findings; 8 fixed in eb60501, 2 not changed): grants
  survived Edits → Ask (no rebuild) and Edits → Ask with a model change; a
  failed revoke kept the session; the extra agent's folder was judged by the
  settings resolved now; a level lowered while busy missed the next turn
  (pre-existing); the notice sat in the sticky fields and reached a locked
  payload; a push-to-talk key held in silence never stopped (pre-existing);
  the limit line could show yesterday's count; an empty `collab` hid the
  notice. Not changed: the notice expiring after the next attempted turn or
  an hour (by design: it is on the HUD during that turn), and barge pre-roll
  excluded from the limit (pre-existing, bounded by the pre-roll).
- **Pass 2** (6 findings, all fixed in a2deeb6): an unreadable grant counted
  as cleared; a turn could go to an agent deleted while it was spoken to;
  collaboration calls missed Ask ↔ Edits in `adapter_stale`; a
  `RecursionError` could escape `revoke`; `_notices` mutated while turn
  threads read it; the limit line did not re-evaluate at midnight.

## Found along the way

- **The limit-from-the-window bug** (C, above) — the likely cause of every
  "cut off at 30 seconds" report, since the open mic is where people pause.
- **"The 00:23:19 flip to Trusted did not lose the chat"** (bugs-notes): the
  log shows it did rebuild and drop the session; the saved chat continued,
  which is what looked continuous.
- **Codex resumes across a model change but warns** with an `error`-typed
  item ("recorded with model X but is resuming with Y"); the adapter already
  neither speaks it nor fails the turn, and a replay test now holds that.
- **Test daemons built with `Daemon.__new__`** (test_tools_skills) lack
  attributes `__init__` sets; new code reads `pipe` and `_main_level`
  defensively.
- **A muted single-agent typed turn left the state file on `speaking`**
  until the microphone came back (nothing else publishes while muted) — the
  "chip still reads speaking" half of #10.
- `bench/preview/preview.sh --size` crops the middle of the screen rather
  than sizing the window.

## Not verified

- **All voice checks** (stop point 1): a 20-minute open-mic session with
  `chime:` lines counted before/after; Theo recalling his previous reply
  after a level flip both ways **by voice**; whether the "be-deep" the user
  hears is gone; turns started late in an open-mic window no longer cut.
- **`agentvoice open-mic off` on the live daemon**, with milliseconds: needs
  the open microphone on (the room listened to without a wake word), so not
  run unattended. Measured in the frame loop instead (≤ 200 ms).
- **A level flip on the live daemon**: needs a change to the user's
  settings (and a turn in a real chat), so not done unattended. Proven by
  the recorded CLI turns and the daemon tests.
- **The QML in the real shell** (needs `omarchy-restart-shell`; stop point
  1): the Conversation page line (seen only in `preview.sh`, dark wide and
  light), the popup's OPEN MIC / STILL LISTENING labels with `window`, the
  Mute button while a muted typed turn speaks, the HUD showing a muted typed
  turn and a `notice`. The HUD was not previewed.
- **agy across a level change**: it starts a new chat and says why, by
  design; whether it could have resumed is unknown (not signed in).
- Copilot, Gemini, endpoints: not affected (no session to carry, or the
  endpoint's identity changed), not run.

## Going back

`bin/agentvoice-deploy --install <older sha>` from the clone (the deploy
printed the commit it replaced); then `omarchy-restart-shell` for the QML.
No stored data changes: `limit_hits` lives in the runtime state file, grants
in the runtime folder. An older build drops the session on any level or
model change again, chimes over the open mic, leaves "still listening" up
after open mic off, cuts late open-mic turns at their first frame, and hides
muted typed turns; it ignores the new state fields.

## Open issues, for the next phase

1. **No section 11 question applied to M2**; none was taken by default.
2. **In open mic, saying the agent's name while it works still stops its
   turn** (now silently). That is the documented wake-word stop, and the
   person's next sentence becomes the new request — but in open mic, where
   people talk freely, it may not be what they meant. A design question for
   M4 (commands in sentences) or the stop point.
3. **Codex credits**: this phase used 33.38 (below), well over the ~15 per
   phase. 398.22 are left for M3–M29, about 14.7 per phase. Recommendation
   for the runner: run **both** passes the way pass 2 ran (empty folder,
   diff inline): 3.55 against 21.11.
4. **agy's `carries_session_across`** stays empty until someone signs agy in
   and records the three turns (the recorder is `record.py` in these notes'
   scratch folder; its logic is in the fixture's "how").
5. M1's open issues 1 (Voice library trash icon → M25) and 3 (M0's small
   test and bench fixes: `test_tools_skills`' TMPDIR-length dependence,
   `test_permission_hook`'s cwd sensitivity and live-folder cleanup,
   `turn_latency.py --build` with `-dirty`) are **still open**: not done
   here, to keep M2 to the daemon bugs. Carried.
6. Codex review coverage: pass 2's fixes were not re-reviewed; the tests
   and docs were never sent.

## Codex credits used

**33.38** (431.60 at the end of M1 → 398.22, read from the session logs'
`rate_limits.credits.balance`):
- 8.55 unexplained: the balance already read 423.05 at this phase's first
  Codex call, with no Codex session logged since M1's 431.60. Possibly a
  late charge for M1's pass 2, possibly use outside these logs.
- ~0.17: the three recorded Codex turns for bug I (gpt-6-luna and
  gpt-5.6-luna, low effort, 87,612 input tokens; balance 423.05 → 422.88).
- 21.11: pass 1, `gpt-6.2-astra` medium, in the clone: 837,212 input tokens
  (771,328 cached) because it read the repository.
- 3.55: pass 2, `gpt-6.2-astra` medium, empty folder: 29,251 input tokens.

**398.22 left** for M3–M29.

## Live checklist: what was said, what happened

- Typed to Sora (`agentvoice type sora`), "Reply with the single word OK."
  after the install: answered, `agent 5.9s, first token 1330ms`; the journal
  held only `⌨ typed` and the timing line (logSpeech off).
- Nothing said by voice; no shell restart; no settings changed.
