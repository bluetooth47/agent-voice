# Phase 15: Collaboration runtime, passing a conversation, shared chats

Written 2026-11-20. Branch `phase-15`, cut from `phase-14` at f1b8c13,
pushed to `fork/phase-15` only (the hashes are in `git log`). Installed:
yes, twice: 1cf6825 (the live checklist ran on it), then 565b902 (Codex's
second pass; smoke-checked live, see the end). Tested on: i7-1185G7,
Quickshell under Omarchy's shell, `claude` 2.1.329, `codex-cli` 0.171.0.

`./bin/agentvoice-check`: green, 2623 tests (was 2492), qmllint clean. Box:
not run (`install.sh` did not change). Preview: the new `shared` target
(chat, sheet, send, communal, details) against a scratch data folder.
Mutations: 17 guards added by the two review passes, each removed in turn,
each turned a named test red (listed under Found along the way).

The run was cut off once by my usage limit, after the preview of the Send
button; it resumed from there and nothing was redone.

## What was built

- **`daemon/collab.py`**: the task model -- id, kind (`pass`, `delegate`,
  `ask`, `message`), from, to, chain, brief, chat, state -- with states
  pending → active → completed | cancelled | failed, or refused. A move
  that may not follow the current state is ignored, so a turn reporting in
  after a cancel changes nothing. One action is one task: an id is never
  used twice (remembered past the display's pruning), and the same spoken
  words inside the confirmation window are one pass. Checks when a pass is
  asked for and again when its turn starts: the target exists, is switched
  on, is in the live crew, is not the sender; each refusal is a sentence
  that is said. A busy target queues the task and says so.
- **The one entry point**, `Runtime.pass_conversation`, for every way in:
  - **voice**: "pass this to Sora" (with an optional request after the
    name: "…, and ask her to check it") said to the current agent, and
    "Sora, take over" (from whoever was spoken to last). The source says
    "Passing this chat to Sora." (naming the host for an endpoint), and the
    task waits 3s in which a bare "stop" (its follow-up window is opened
    for that), "Theo, stop", the stop keybind or "full stop" cancels it. If
    the line could not be said to the end -- muted, locked, lent out, a
    failure -- nothing is passed and the reason is shown.
  - **the sheet** (`ui/SendSheet.qml`), "Send to another agent" on a saved
    chat, on "This session" in the Chats view, and on the conversation view
    with saving off: who receives it, the exact brief (the last exchange,
    editable, 2000 characters), "Sora will see this whole chat (up to 8000
    characters) and the brief…", and for an endpoint the host it is sent
    to. Send runs `agentvoice pass … --entry sheet --id ID --host HOST
    --line`; the sheet then reads the daemon's answer from the state file by
    that id and shows a refusal as a refusal.
  - **the CLI**, `agentvoice pass TO [--from ID] [--chat ID] < brief`: says
    on stderr that the chat goes with it (and the host), then files the
    request in `$RUNDIR/crew/requests/`; the brief on stdin, never argv.
- **The order of events (A15-2)**: told first, then the target is added to
  the chat's `shared_with`, then its turn. The endpoint host the person was
  told is bound to the task and checked again at the start.
- **The task turn** runs on the target's own adapter, folder, model and
  level, in its own session *for that chat* (`chat.sessions[target]` when it
  can be resumed, told what the others said since it last spoke there; else
  a new session replayed the chat), never the session of its own
  conversation (A15-3). With saving off the transcript is this session's
  memory, snapshot when the person was told, and nothing is written (A15-5).
  After a pass the target stays in the shared chat; Continue in terminal is
  untouched. A delegation (Phase 16) puts the target back afterwards.
- **`$RUNDIR/crew/origin/<id>.json`** names who the target works for while
  the task runs; the permission card reads "The agent “Sora”, for Theo, for
  you, wants to…". Missing, corrupt, malformed or a link: no chain text, and
  never a different decision.
- **Shared chats** (`chats.py`): `owner` fixed at creation (`agent_id` kept
  in step, "" for the main agent), each exchange labelled with who answered
  (`agent_id`, `agent_label`, `kind: brief`, `for`), `sessions` per speaker,
  `participants`, `shared_with` as the only grant of replay.
  `agentvoice chats share|unshare ID AGENT`; `chats continue ID AGENT`
  refuses, with the reason, an agent the chat is not shared with, and a
  session it once had there lets it resume natively but never be replayed
  the transcript.
- **Stop, lock and state**: "Sora, stop" stops Sora's turn, every task she
  started and anything waiting for her; the global stop clears everything.
  Behind a lock a running task keeps running and says nothing, nothing new
  starts, the state file carries no transcript, reply or task line, and what
  the task did not get to say is said after the unlock (a stop discards it).
  Every task is one `audit.log` line when it ends (no text).
- **Shown**: the HUD line ("Theo → Sora: passing", "Sora (for Theo):
  working", "Sora finished"); "Sora (for Theo)" as the speaker; the Agents
  panel's plan text "Working for Theo"; `agentvoice tasks [cancel ID]`;
  Agent details → Chats: a Collaboration list with Cancel, and the chats the
  agent may continue ("passed to it", "shared"); Chats view: replies
  labelled ("Sora (passed from Theo)"), an Agent conversations filter,
  Share chat with…, Stop sharing with…, Continue with <agent>; Communal → a
  Chats tab listing conversations with more than one agent.

## Shared files touched, and where

- `daemon/wake_listen.py`: imports; `self.collab`; `silence()` skips a
  running task; `_on_interrupt` and `full_stop` clear tasks; `_send`'s stop;
  `voice_command` → `pass_command`; the run loop's bare stop/goodbye and
  `collab.tick()` (between captures and in an empty follow-up window);
  `_turn` → `collab.turn_ended`; `dispatch` resets `turn_error`; `answer()`
  keeps a task turn going behind a lock and holds what it did not say;
  `speak()` behind a lock does not stop a task turn; `remember`/`save_chat`
  (the request as heard, `kind`/`for`); `continue_chat` (per-speaker
  session, no replay without a share); `apply_chat_command`
  (`chat-continue ID AGENT`, `task-cancel`); `_compose` (tasks, the HUD
  line, "(for Theo)", the lock strip) and `panel_agents` (`for`);
  `_say_for` returns whether it was said.
- `daemon/crew.py` (Persona: `task`, `task_heard`, `saved_conversation`,
  `turn_error`), `daemon/chats.py` (schema, share, CLI), `daemon/audit.py`
  (task kinds, `state`), `daemon/permission_hook.py` (`_chain`),
  `daemon/speech_text.py` (`pass_command`, `is_take_over`),
  `daemon/agents_panel.py` ("Working for …").
- `bin/agentvoice`: `pass`, `tasks`, `chats share|unshare`, `chats continue
  ID [AGENT]`; `vstate()` anchored to the top-level state.
- QML: new `ui/SendSheet.qml`; `Settings.qml` (sheet, `vTasks`,
  `showChat`, history rows' `agentId`, chain on the card, a Send button on
  the plain session view), `Hud.qml`, `Panel.qml`, `Chats.qml`,
  `pages/CommunalPage.qml`, `pages/AgentDetailsPage.qml`, `ui/qmldir`.
- Bench: `bench/pass_latency.py`, `bench/preview/preview.sh`
  (`--scratch-data`; `pass`/`tasks` logged), the `shared` target and its
  seed and state; `bench/FINDINGS.md` §38.
- Tests: new `tests/test_collab.py` (131); `test_agent_fixtures.py` (the
  writer adds the new fields beside the old), `test_notes.py` (the audit
  AST walk knows the task call's names).

## Measured (numbers, against the baseline)

FINDINGS §38 (A15-6). From the command to the target's first reply text,
interleaved, past the follow-up window: Sora (Claude Haiku) direct 0.70s,
pass 0.61s (n=5, medians); Hazel (Codex) direct 5.99s, pass 5.72s (n=3). A
pass from the sheet or the CLI costs nothing measurable, so task turns keep
the target's own adapter. A spoken pass adds the line and the 3s window,
about 4.8s in the live check -- inside the 5s, just. Prompts unchanged after
install: 1109, 1210 and 7088 characters, as in Phase 14.

## Different from the plan, and why

- **A voiced pass that could not be said is not passed.** The plan says
  the spoken confirmation comes first; Codex's review pointed out that a
  muted microphone, a lock mid-line or a failing speaker would have let it
  go ahead unheard. Safe default: refuse and say (show) why, and point at
  the sheet.
- **Nothing new starts behind a lock.** The plan says a running task keeps
  running and results wait; a task still waiting to start waits too.
- **The sheet and the CLI bind the host they showed**, and the daemon
  refuses a pass whose endpoint no longer matches (review finding).
- **The target's display transcript** for a sheet or CLI pass is "(passed
  from Theo)", not the brief, so a typed brief does not sit in the state
  file and history; a spoken request is recorded as said.
- **A non-remembering target stays in the shared chat** on its next turn
  (its membership is not its session).
- **Delegation's put-back** is built and tested now, though only Phase 16
  can start a delegation.
- **`agentvoice locked`/`talk`** needed a fix outside the plan: their
  greedy `sed` read the last `"state"` in the state file, which is now a
  task's.

## Found along the way (bugs, surprises)

- **A Repeater's `modelData` hides arrays from `Array.isArray`**, so
  Agent details called every chat its own; membership is now checked by
  hand (seen only in the preview).
- **The sheet first drew over the settings pages** after leaving the
  conversation view, and let the page show through a translucent theme
  colour; both fixed, seen in the preview.
- **A typed "stop" cannot reach a pass's window**: a typed message waits
  for the follow-up window to end, by which time the pass has gone. The
  live check used the stop keybind; a spoken stop is heard in the window.
- **The bench's first two versions measured the wrong thing** (the previous
  reply still in the state file; then the follow-up window); FINDINGS says
  so and uses neither.
- **shell.json was re-saved** by something outside this app ten seconds
  after I restored it from its copy in L5: same content (`jq -S` identical),
  different bytes.
- **Mutations** (each removed or inverted, each turned the named test red):
  the said-to-the-end check; the re-check between going active and sending;
  the lock strip in `_compose`; the shown-host check; unknown fields;
  repeated fields; the cancel audit; `speak()` behind a lock; the follow-up
  window closed on a cancel; old ids; and from the second pass: the
  signal handler only recording the stop, the stop checked while a turn
  starts, the roll-back, the share checked for a resumed session's catch-up,
  a finished turn not stopped, a crash recorded as failed, hosts without a
  port. The first build's guards (the stop in
  the window, the global stop, the refusals) have tests but were not
  mutated.

### Codex

- **Extra task**: Codex wrote the Chats.qml, Communal Chats tab and Agent
  details Collaboration/Chats changes in parallel from a written spec; I
  reviewed them and fixed three things (the membership check, an empty
  session's Send button, the chat title's size).
- **Review of 05adb93**: 10 high, 11 medium, 2 low, each checked against the
  code. Fixed in 1cf6825 and 7b9212c, with tests: the signal handler could
  deadlock (it now publishes nothing); a cancel could land between going
  active and sending, or leave a follow-up window armed; a bare "stop" was
  consumed before it reached the pass, and an empty window held the
  dispatch back; a voiced disclosure that was not heard counted; the
  endpoint host was not bound; CLI values could inject a header line; a
  session in a chat let an unshared agent be replayed it; with saving off
  the transcript was read at dispatch, not at the confirmation; a worker
  could publish turn text over the lock; briefs became the display
  transcript; held replies repeated what was said and outlived a stop;
  cancels were not audited; old ids could start a second turn; distinct
  spoken requests were merged; a non-remembering target left the chat; a
  resumed session missed what others said; the origin folder could end the
  poll; the sheet could send an old brief while a chat loaded, and showed
  "Sent" for a pass the daemon refused; `vstate` read a task's state; "in
  use" only for the owner. **Not changed**, with reasons:
  - passing a chat back to its owner resumes the owner's session in that
    chat, where an "allow all in this chat" it was given still applies. The
    plan says a task runs in the target's session for that chat; the grant
    was the user's, to that agent, for that chat. Open issues.
  - the backends' own history (Claude Code and Codex keep prompts on disk,
    SECURITY.md) holds a passed brief even with saving off. A15-5 is about
    Agent Voice's data folder; Open issues.
  - a sentence cut off mid-audio by a lock is not counted as unsaid (only
    sentences never started are held).
  - Continue and Cancel refusals from the daemon go to the journal (the CLI
    pre-checks Continue; Cancel of a task already finished says nothing),
    and the one-file command channel can drop a command sent in the same
    instant as another (as before this phase).
  - the plain "This session" sheet previews the last exchange of the
    session, while with saving on the daemon passes the source's current
    saved chat; they are the same unless the source was moved to another
    chat in between.
  - the Communal and Agent details lists read `index.json` directly, so a
    damaged index shows empty there until the next write rebuilds it.
- **Second pass on 1cf6825**: the first attempt was stopped by Codex's own
  service ("flagged for possible cybersecurity risk") partway through; a
  retry with a plainer prompt hit Codex's usage limit; after the 10:23 reset
  it ran (reviewing 1cf6825; it had not seen 7b9212c). Of the 23 original
  findings it counted 8 fixed, 12 partly fixed, 3 not fixed, and found 11
  more (3 high, 6 medium, 2 low). Its last note before the limit pointed at
  the sheet ignoring an answer that arrived before the CLI exited, fixed in
  7b9212c. Fixed in 565b902, with tests: the signal handler could deadlock
  on the audit log's flock (it now only records the stop; the run loop
  carries it out, and nothing starts meanwhile); a start stopped after
  preparing left the share, the chat and the replay installed for the next
  turn (rolled back now); a resumed session's catch-up ignored an unshare in
  between; a turn finishing before dispatch() returned was stopped anyway; a
  crashing turn was audited as completed; goodbye cancelled queued passes;
  spoken repeats coalesced after the window; `localhost:11434` failed the
  host check from the sheet; the sheet read a refusal's reason after
  changing the id (a null read), restarted its close timer on every re-read,
  and left Send disabled after a timeout; "This session" now previews the
  chat that would be passed. **Not changed** beyond the six above: the
  explicit spoken request is still the display transcript (it is what was
  said aloud, as any transcript is); a stop arriving between Board.move's
  check and assignment, now only on the run loop's own thread; a busy main
  agent keeping an old adapter until it is idle (a task never starts on a
  busy target, and catch_up runs first); a non-remembering target can still
  fork the chat on its second follow-up; the catch-up marker is "the last
  exchange it spoke", not per-session delivery; ids are remembered for the
  last 2000; the editor shows over-long text with its counter and sends the
  first 2000 characters. It also flagged the bench, which it saw before its
  fix in 7b9212c.

## Not verified (what was skipped, and why)

- **A spoken pass and a spoken "stop"**: every live check used typed turns
  (`agentvoice type`), which go through the same `_send` → voice command
  path; the stop in the window used the stop keybind. The spoken lines were
  played (journal echo drops) but nobody listened.
- **Clicking Send in the real shell**: the sheet was drawn and its Send
  button clicked in the preview (the exact command logged), and that exact
  command was run live against the daemon (L2); nothing clicked in the real
  shell.
- **A15-6 voiced** (voiced passes against voiced direct turns, J-style):
  the typed/CLI form was measured instead (§38).
- **An endpoint target live**: none is configured; the host naming is
  tested only.
- **The permission card's chain live**: Sora is at Ask, but no task turn of
  hers asked for anything; the chain is tested through the hook's
  `_chain()` and the card's text in source only.
- **Agent details → Collaboration and the HUD line in the real shell**:
  seen in the preview with a synthetic state file only.
- The installer box (install.sh unchanged).

## Going back (what an older build sees after this phase)

- Chats keep their old fields with the old meanings; an older build reads
  `owner`, `participants`, `shared_with`, `sessions` and the exchange
  labels as unknown keys and ignores them. It would again overwrite
  `agent_id`/`backend`/`session_id` when a second agent recorded into a
  chat, but no older build can make a second agent record into one.
- `audit.log` gains `task_*` lines an older build never writes.
- `$RUNDIR/crew/` is left on tmpfs, unread; it is gone at logout.

## Open issues, for the next phase

- **Passing back to the owner** resumes the owner's own session in that
  chat, with any "allow all in this chat" it was given. Kept as the plan
  says. Question for the user: should every task turn start a fresh session
  (replaying the chat) so no grant ever spans a pass, at the cost of
  replayed tokens and the native session?
- **Backend history**: with saving off, Claude Code and Codex still keep the
  prompt (brief and replay included) in their own session files. Should the
  pass sheet say so, as SECURITY.md does?
- The refusal for Continue names the agent by id ("jarvis-ajc") where it
  could use the display name ("Hazel").
- A typed "stop" cannot cancel a pass inside its window (typed messages
  wait for the follow-up window).
- Codex's remaining items above (cut sentence at lock, journal-only
  refusals, command channel, the session sheet's chat, index recovery).
- For Phase 16: `ask` and `message` tasks, `acceptsWork` and
  `collaboration` levels are not built; the task model and delegation's
  put-back are.

## Live checklist: what was said, what happened

Typed turns (`agentvoice type`) and the CLI on the installed build
(1cf6825-dirty: `testresults.md` was modified in the checkout before this
phase began and is not part of it), synthetic text throughout. Saved chats
before: 18; the three test chats were deleted afterwards and each agent
given a new chat; 18 after.

- **Install**: the journal printed the same prompt sizes (1109, 1210,
  7088); shell restarted (`omarchy restart shell`).
- **L1, Theo → Sora by voice command**: Theo answered a synthetic question;
  "pass this to Sora" typed to Theo → 10:05:47.45 typed, 49.25 "pass …: Theo
  → Sora (voice)" after the line was said, Theo's follow-up window opened,
  52.26 "Sora has the floor (replayed)". The chat: owner `main`, `agent_id`
  "" unchanged, participants main and sora, `shared_with` [sora], Sora's
  exchange `kind: brief`, `for: main`, transcript "(passed from Theo)"; her
  reply used the earlier answer. Audit: `task_pass … "state":"completed"`,
  no text.
- **L6, stop during the announcement**: "pass this to Hazel" typed, then
  `agentvoice interrupt` inside the window → task `cancelled stopped`, no
  Hazel turn, `shared_with` still [sora].
- **L5, a switched-off target**: Hazel's `enabled` set false in shell.json
  (jq), "pass this to Hazel" → "refused: Hazel is switched off. Turn it on
  on the Agents page first." (spoken: an echo drop followed); shell.json
  restored from its copy, hash identical (59de4b6403c7db60).
- **L4, a busy target**: Sora counting to fifteen, "pass this to Sora" typed
  to Theo → "queued, place 1"; when she finished, "Sora has the floor
  (resumed)" and the task completed.
- **L3, Sora → Hazel across providers**: "pass this to Hazel, and ask her to
  confirm … she can see this chat" typed to Sora → Hazel (Codex) "has the
  floor (replayed)", her exchange `brief` for `sora`, reply "I'm Hazel, and
  I can see this chat."; `shared_with` [sora, jarvis-ajc].
- **L7, locked mid-pass**: `agentvoice pass sora --from main` (stderr said
  the chat goes with it), `agentvoice lock` as Sora's task turn started
  (10:08:22.85) → 29 of 30 state samples over 9s read `locked` with no
  transcript, reply or task line; her turn finished behind the lock with
  nothing spoken; the task `completed`; at the unlock (10:08:34) about 6s of
  speech followed -- the held reply.
- **L2, the sheet's command**: the exact command the sheet runs
  (`--entry sheet --id … --host "" --line --chat …`, a JSON brief) → the
  task appeared under that id (`active`), the same id sent again made no
  second task and no second turn, and the chat recorded "(passed from
  Theo)", not the brief.
- **L9, Share chat with… then continue with the other agent**: a new Theo
  chat; `chats continue ID jarvis-ajc` → refused, "That chat isn't shared
  with jarvis-ajc…", exit 1; `chats share` then `chats continue` → Hazel
  "continuing a saved chat (replayed)", and asked which vegetable Theo had
  named she answered "Theo named carrots.", recorded in that chat.
- **L8, Continue in terminal**: "move this to a terminal" typed to Sora →
  "moved to a terminal", `foot … claude --resume <her session in the shared
  chat>`; the terminal closed by me; the chat marked as gone to a terminal.
- **argv**: 74 samples of every `/proc/*/cmdline` during the Sora bench: the
  prompt text appeared only in my own sampling shell, never in a daemon,
  CLI or agent process.

### After the second pass (565b902)

Installed, the service restarted (same prompt sizes, 1109/1210/7088), the
shell restarted. "pass this to Sora" typed to Theo → said, then "Sora has
the floor (replayed)", completed; "pass this to Hazel" then `agentvoice
interrupt` inside the window → cancelled through the deferred stop, one
`task_pass … "state":"cancelled"` audit line. The smoke chat deleted (18
saved chats); shell.json's content unchanged from the start of the phase.
