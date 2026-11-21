# Agent Voice: next plan (the redesign round, R0 to R23)

Written 2026-11-21 against `orders-guard` at `92c71ff` (installed and
running, 2790 tests green). Planning only: nothing in the repo was changed
to write it. Inputs: `CODEBASE.md`, the repo's `CLAUDE.md`,
`project-status-2026-11-21.md`, `feedback-notes-2026-11-21.md`,
`mockups/index.html`, `merged-plan.md`, `voice-commands-notes.md` and
`phase-17-plan.md`, plus the code facts checked in section 1.

## Summary

This plan builds every item in the 2026-11-21 feedback (1 to 22, and 24)
and fixes bugs A to K. It does so in 24 phases, R0 to R23, each sized for
one focused session, and finishes with an installed release candidate that
meets Phase 17's entry gate.

- **R0, housekeeping, fixes bug H first.** Its cause is now known: Omarchy's
  own plugin watcher runs `inotifywait -m -r` over
  `~/.config/omarchy/plugins` and reloads every panel, service and widget
  on any write inside a plugin folder. So development moves to a clone
  outside that folder. The plugin folder becomes a deploy target that
  changes only when a build is deployed on purpose. R0 also brings `dev`
  and `main` up to `orders-guard`, makes `main` stop tracking origin, and
  disables the finished runner.
- **R1** builds the shared UI pieces every later page uses: cards, compact
  selectors, chips, hints, warning + confirm, and drag cards.
- **Then, in order:** the daemon bugs; the popup; the agent pages; crew
  links and quarantine (enforced in the daemon before any map is drawn);
  tools, skills and notes; the voice commands and the Agent Voice skill;
  chats; stats; the remaining settings pages; background announcements.
- **R23, a final pass:** settings search, first-run setup, a consistency
  audit, and the release candidate.

Anything that lets an agent do more is off or denied by default. The daemon
or the tool server makes that decision, never the screen alone. Every
feedback item and bug maps to a phase (section 6). Three parts are deferred,
each with a reason:

- changing key bindings from the page;
- extra Whisper models until they are pinned;
- announcements from backends whose process ends with the turn.

Phase numbering: the new phases are **R0 to R23** ("R" for this round).
Their branches are `phase-r0`, `phase-r1`, … and their notes are
`phaseR0notes.md`, `phaseR1notes.md`, … The prefix avoids clashing with the
existing `phase1notes.md` to `phase16notes.md`. **Phase 17** keeps its name
and runs after R23.

---

## 1. Start state, and facts this plan rests on

Checked 2026-11-21 at 01:32 MST, read-only.

| What | State |
|---|---|
| Installed and running | `orders-guard` 92c71ff, since 00:12; 2790 tests, 14/14 static checks (status report) |
| Local `dev` | **Already at 92c71ff.** Fast-forwarded locally at 01:31:09, after the status report was written, and not pushed: `fork/dev` is still 2eeb919. This plan did not do that. |
| Working tree | **Ten files staged on `dev`, not committed:** `CODEBASE.md`, `agents-plan.md`, `bugs-notes.md`, `voice-commands-notes.md`, the `testresults.md` row (#10), and `notes/2026-11-21-redesign/` (copies of the feedback, mockups, phase-17 plan, prompt and status). Confirm with the user who staged them before R0 commits anything. |
| Local `main` | e331d31, tracking `origin/main`; 39 behind `orders-guard` |
| Runner | `agentvoice-phase-runner.service` finished; still **enabled** |

**Bug H, the cause** (Omarchy 4.5.0-3, read in
`/usr/share/omarchy/shell`):

- `services/PluginRegistry.qml:726` runs
  `inotifywait -m -r -q -e close_write,create,delete,move` over the whole
  plugins folder.
- `localPluginIdForPath` (`:791`) exempts only `.git/` (`:799`) and
  `__pycache__/` (`:801`). Every other write, including a `.md` note, an
  editor's swap file or `.pytest_cache/`, emits `localPluginChanged`.
- `shell.qml:1541` then calls `reloadPlugins()` (`:1517`) after a 150 ms
  timer (`:71`). That unloads and reloads **every** panel, service and
  widget.
- This is Omarchy's code. We never edit it (the same rule as Omarchy's
  Agents panel).
- `./bin/agentvoice-check` run in place writes `.pytest_cache/`, so the
  check itself reloads the shell.

**Other facts the phases depend on:**

| Fact | Where | Consequence |
|---|---|---|
| The Claude adapter passes `--mcp-config` as **JSON in argv** and does not use `--strict-mcp-config` | `daemon/adapters/claude_code.py:365` | Each `claude -p` agent also loads the user's own MCP servers (this machine: `desktop-control` in `~/.claude.json`) and, probably, `~/.claude/skills`. Detected tools cannot be "off by default" until a recorded turn shows what strict mode removes. Any server definition with a secret must go in a 0600 file, never in argv. |
| The init event is read only for `session_id` | `claude_code.py:153` | Live MCP status (item 14) needs the adapter to keep the init event's server list. |
| The one-page test checks **schema** keys in `pages/*.qml` only | `tests/test_settings_pages.py` | Six defaults-only keys are unchecked (`voiceAgents`, `mainTools`, `permissions`, `agentModels`, `agentEfforts`, `wakeAlsoSounds`), and so is every per-agent field. R4 extends the test before fields start moving. |
| `Settings.qml` itself writes `engine`, `voice` and `voiceAgents` | `Settings.qml` | The overlay-function pattern (`assignVoice`) is how a second page reaches a per-agent field without becoming a second writer. |
| The popup writes the main agent's permission level | `Panel.qml:566–583` (`setMainLevel`, `store.set("permissions")`) | Removing it (bug D) also removes one way to promote an agent to Trusted. |
| The Agents page's "ON THE DESKTOP" group writes `desktopTools`, `browserTools`, `omarchySkill` | `pages/AgentsPage.qml:1320` | Bug E: these global keys move to Communal → Tools in the same commit. |
| A permission or project change rebuilds the main agent and **drops its session** | `wake_listen.py:2045` (`reconcile_agent`) | The likely cause of bug I. Only a project change needs the drop. |
| Chime call sites: `done` 3739, `wake` 5184 and 5462 (re-arm), `heard` 5296 | `wake_listen.py` | Where bug J's "be-deep" comes from. |
| Closing open mic does not end the follow-up window | `wake_listen.py:4006` (`end_open_mic`) | The likely cause of bug K. |
| Chats already have titles from the first sentence, rename, and a word-scoring search | `daemon/chats.py:169`, `:418`, `:478` | Item 6 extends what exists rather than starting over. |
| The noise floor's look-back is a module constant, 30 s | `daemon/noise_floor.py:34` | The gate-speed setting becomes a plain attribute, set after the spec check. |
| A hung turn is killed after 90 s with no output | `daemon/adapters/base.py:23` (`IDLE_TIMEOUT_S`) | The per-agent timeout in item 14 is this number. |
| Whisper models are fetched by name at first use; none are in `models.lock` | `wake_listen.py:853` | Adding models (item 19) means pinning them first. |
| `shell.json` is mode **0644** in a 0755 folder | `~/.config/omarchy/shell.json` | It is readable by every local account, so no secret may be stored there: extra environment variables go in a 0600 file. |
| Ctrl+1..9 fill exactly nine pages | `Settings.qml:1367` | The redesign has eleven pages; see R6. |
| A `~/Projects` folder exists | home | Suggested place for the dev clone: `~/Projects/agent-voice`. |

---

## 2. How every phase runs

The house rules from `merged-plan.md` section 4 and `CLAUDE.md`, plus what
R0 changes.

1. **Work in the dev clone** (`~/Projects/agent-voice` after R0), never in
   the plugin folder. The plugin folder changes only through
   `bin/agentvoice-deploy`, and only with the user's OK.
2. **Branch** `phase-rN` off `phase-r(N-1)`. Push to `fork` only; origin's
   push URL is disabled in R0. After a phase passes its check and review,
   fast-forward `dev` to it and push `dev` to fork, so the integration
   branch never falls behind again. `main` moves only in R23.
3. **Agree the spec, then measure first.** Claims of "faster" or "smaller"
   need numbers, recorded in `bench/FINDINGS.md` from §40 on.
4. **Build to `CLAUDE.md`:**
   - settings are three things;
   - one page per key, and from R4, one page per per-agent field too;
   - no setting is removed: a moved key keeps its name and value, and
     fine-tuning goes under a collapsed "Advanced";
   - text arrives on stdin, never argv;
   - any transcript, reply, folder text, chat or agent name is shown with
     `textFormat: Text.PlainText`;
   - read colours as `Commons.Color`;
   - an unreadable value falls back to the safe one.
5. **Big shared files** get small, commented hooks; new code goes in new
   modules and `ui/` components. Each phase's notes list every big file it
   touched. The big files:

   | File | Lines |
   |---|---|
   | `wake_listen.py` | 5699 |
   | `collab.py` | 2464 |
   | `agentfs.py` | 2137 |
   | `Settings.qml` | 1851 |
   | `AgentsPage.qml` | 1391 |
   | `AgentDetailsPage.qml` | 1313 |
   | `Panel.qml` | 1236 |
6. **`./bin/agentvoice-check` green** before every commit. The bare-runner
   and `full` jobs run in CI. Run `AGENTVOICE_BOX=1` whenever `install.sh`
   changes.
7. **Codex reviews each phase twice** (first and second pass). Fixes land
   as separate commits.
8. **Screenshots come from `bench/preview/preview.sh`**, never the live
   shell, and the real pointer never moves:
   - narrow (520×720) and wide;
   - dark and `--theme flexoki-light`;
   - `clicks` logs every write.

   Each new page gets a preview target.
9. **Deploy and install last, and warn first.** `install.sh` ends any voice
   turn. **QML changes show in the real shell only after
   `omarchy-restart-shell`**: ask the user, then verify with a screenshot.
10. **Live checks:** run the phase's live checklist, using voice where the
    phase touches listening or speech. Evidence uses synthetic content.
11. **Notes:** write `phaseRNnotes.md` using the template in
    `merged-plan.md`, plus the "Going back" line. A skipped check is
    recorded as not verified, never as passed.

---

## 3. Phase R0: housekeeping, and bug H first

| | |
|---|---|
| Covers | item 4, bug H; the git, runner and notes housekeeping |
| Needs | the user's answers to open questions 1 and 2 |
| Branch | none for the git steps; `phase-r0` in the dev clone for the script and doc changes |

**Goal.** No more shell reloads while working, `dev` and `main` current on
the fork, nothing able to push to origin, the runner quiet, and every
uncommitted note safe.

**Steps, in order.** Steps 1 to 6 write only inside `.git/`, which the
watcher ignores, so none of them reloads the shell.

1. **Safety net.** Run `git bundle create
   ~/agentvoice-notes/backup-2026-11-21.bundle --all`. This writes outside
   the plugin folder.
2. **Notes.** With the user's OK, commit the staged notes on `dev` as one
   "notes" commit. That includes `voice-commands-notes.md`, which has no
   other copy, and the `testresults.md` #10 row.
3. **Refs only, no checkout:**
   - `git branch -f main dev`;
   - `git branch --unset-upstream main`;
   - `git remote set-url --push origin "DISABLED-never-push-origin"`, so a
     push to origin fails with an error instead of relying on memory;
   - `git push --dry-run fork dev main` first, then the real push (both
     are fast-forwards: 2eeb919 and e331d31 are ancestors);
   - `git branch -u fork/main main` and `git branch -u fork/dev dev`.
4. **Runner.** `systemctl --user disable --now
   agentvoice-phase-runner.service`. Keep the unit file and the 15 MB of
   logs until the user says otherwise.
5. **Record orders-guard.** It has no notes file. Add a short record (what
   it guards, the Bash-text caveat, that Trusted Codex has no hook) to
   `phaseR0notes.md`. Correct merged-plan's stale "Codex review still owed"
   line for Phase 10 (resolved in e467d99).
6. **Name the writers.** Run a read-only `inotifywait -m -r` over the
   plugin folder during one ordinary session, logged to
   `~/agentvoice-notes/`. List every process that wrote there. Expected:
   agents whose project is the plugin folder, and the check's
   `.pytest_cache`. If the daemon or the UI ever writes there, fixing that
   joins this phase.
7. **Dev clone.** `git clone https://github.com/bluetooth47/agent-voice
   ~/Projects/agent-voice`. Then add `upstream` (duaneoca) with its push
   URL disabled.
   - With the user, point Theo's `projectDir` at the clone, and any other
     agent that works on Agent Voice. That is a settings change, so the
     user makes it or approves it.
   - From now on the planning notes can live in the clone's `notes/`
     folder (open question 2): writing there no longer reloads anything.
8. **The plugin folder becomes deploy-only.** Disable both push URLs in its
   own `.git`. Add `bin/agentvoice-deploy` (committed in the clone). It:
   - refuses if the clone is dirty or the check is red;
   - runs `git -C <plugin> fetch <clone> <sha>`, then
     `checkout --detach FETCH_HEAD`. That is one reload, on purpose;
   - offers `./install.sh --yes` from the plugin folder, so the installed
     stamp equals the deployed commit;
   - says "QML changed: run `omarchy-restart-shell`?" and waits for a yes.
     The memory notes say a plugin reload alone does not pick up QML.
9. **The check writes nothing in the tree.** Run pytest with
   `-p no:cacheprovider` and `PYTHONDONTWRITEBYTECODE=1`, and add static
   check 15: "the check left no new file in the tree" (a listing before and
   after).
10. **Docs.** Update the following:
    - `CLAUDE.md`: a new "Where to work" section with the watcher's file and
      line, the dev clone, and deploy;
    - `CODEBASE.md` §2, §10 and §12;
    - `CONTRIBUTING.md`;
    - phase-17-plan's bug H box;
    - the assistant memory notes.
11. **Baseline for this round.** Run S for `sora` (20 runs) and J over
    recent real turns on 92c71ff, into FINDINGS §40. This is the gate for
    R8, R11, R14 and R22, using the rules after merged-plan's Phase 8. R23
    reruns it for Phase 17.
12. *Optional, outward-facing, only if the user asks:* a drafted note to
    Omarchy suggesting the watcher reload only on `*.qml`, `qmldir`,
    `*.js` and `manifest.json`, and ignore `.pytest_cache`. Nothing is sent
    without approval.

**Why a separate clone, not a symlink or a hidden folder.**

- A hidden subfolder is still watched: only `.git/` and `__pycache__/` are
  exempt.
- Quickshell does not resolve singletons through a symlink (`CLAUDE.md`).
- `inotifywait`'s behaviour under a symlinked plugin folder is untested.
- A clone keeps the main repo safe from `omarchy plugin remove` (an
  `rm -rf`), which today would delete the only working copy of any
  uncommitted note.

**Files.** `bin/agentvoice-check`, new `bin/agentvoice-deploy`,
`CLAUDE.md`, `CODEBASE.md`, `CONTRIBUTING.md`. No product code.

**Settings.** None.

**Tests.** Static check 15 (no new files). A test that `agentvoice-deploy`
refuses a dirty tree. A shell syntax check covers the new script.

**Verify.**

- `git rev-parse dev main fork/dev fork/main` all print the same sha.
- `git push --dry-run origin main` fails.
- `systemctl --user is-enabled agentvoice-phase-runner` says `disabled`.
- With `inotifywait` watching the plugin folder, a full check run plus 20
  file edits plus a commit in the clone give **0 events**, and the
  quickshell PID is unchanged. Then one deploy gives one burst, as
  intended.
- No QML changed: no shell restart is needed, except the one deploy, which
  is asked first.

**Measure.** Reload triggers from one in-place check run: before, counted on
a scratch copy watched with the same filter; after, 0 (in the clone).

**Risks.** Paths written into memory notes, the runner, `CODEBASE.md` and
Theo's settings go stale; the docs step lists them all. A detached HEAD in
the plugin folder confuses `omarchy plugin update`; that is fine on this
machine, and the step says so in CONTRIBUTING.

**Going back.** Deploying an older commit is one `agentvoice-deploy <sha>`.
Nothing about the data changes.

---

## 4. The phases

| Phase | What | Covers | Needs | Live check |
|---|---|---|---|---|
| R1 | Shared UI pieces | 17, 14 (confirm everywhere) | R0 | shell |
| R2 | Daemon bug sweep | C, I, J, K, testresults #10 | R0 | voice |
| R3 | Popup and readout | 2, 3, 20 (readout), B, D | R1 | voice, shell |
| R4 | Agents page | 8, E, 15 (home for global tools) | R1 | shell |
| R5 | Agent details: tabs, personality | 9, 10 | R1 | voice |
| R6 | Crew links and quarantine, enforced, plus table | 16 (part 1) | R5 | typed |
| R7 | Crew map, drawn | 16 (part 2) | R6 | shell |
| R8 | Tool detection and real tool controls | 11 (tools), G, 15 (shared tools) | R5, R6 | typed |
| R9 | Skills: scan, lanes, drag | 11 (skills), 15 (skills gap) | R8 | typed |
| R10 | Command table, commands inside sentences | 1, A, 22 (caution) | R2 | voice |
| R11 | The Agent Voice skill | 11 (skill), voice-commands-notes | R9, R10 | voice |
| R12 | Note categories and moves | 12, 15 (notes) | R9 | typed |
| R13 | Agent details: Advanced | 14 | R8 | typed |
| R14 | Communal: who gets it, preview, import, history | 15 | R8, R9, R12 | typed |
| R15 | Chats page | 5, 6 (page), 13 (rename), 20 (chat privacy) | R1 | shell |
| R16 | Chats: names, summaries, search tool | 6 (backend) | R15, R6 | typed, voice |
| R17 | Stats and the Overview page | 7, 20 (stats privacy) | R2 | voice |
| R18 | Listening as a pipeline | 18 | R17 | voice |
| R19 | Conversation page | 13, C (page) | R2, R10 | voice |
| R20 | Voice page | 19, F | R1 | shell |
| R21 | Other settings and About | 20, 21, 22 (About parts) | R10, R17 | shell |
| R22 | Background-work announcements | 24 | R2 | voice |
| R23 | Search, first run, audit, release candidate | 22 (general), 17 (audit) | all | full |

Why this order:

- **Daily annoyances first:** H, the surprise chimes, the bouncing popup.
- **The pieces before the pages.**
- **Crew links and quarantine before tools, skills, notes and chat
  search,** so each later phase respects quarantine as it is built instead
  of having it bolted on.
- **The command table before the pages that list commands.**
- **Stats before the pages that show them.**

### R1 · Shared UI pieces

| | |
|---|---|
| Covers | item 17 (the pieces); item 14's addition, warning + confirm across the window, applied to the risky buttons that exist today |
| Needs | R0 |

**Goal.** One set of building blocks in `ui/`, so every page looks and
behaves the same and a user can tell what a control does at a glance.

**Build.** Reuse `SegmentedChoice`, `SettingRow`, `ToggleRow` and
`TabStrip` where they fit. New pieces:

| Piece | What |
|---|---|
| `Card` | Titled box, caption on the right, optional hint |
| `CardGrid` | Two across when wide (≥ about 760 px), one when narrow |
| `HeaderStrip` | The collapsible agent header: state dot, name, pills, caret |
| `Pill` | Small read-only label |
| `CompactSelector` | Mini segmented control, the VS Code effort bar; arrow keys work |
| `ModelPicker` | Model drop-down with a `CompactSelector` joined to it (effort) |
| `ToggleChips` | A row of on/off chips; optional inherit state; a disabled chip says why in its tooltip |
| `Hint` | One plain line; the detail is in a tooltip |
| `DangerButton` | ⚠ icon. The first click arms an inline "Really reset Theo? Cancel / Reset" strip, which disarms after 6 s or on Escape. The action runs only in `onConfirmed`. Never a modal dialog. |
| `AdvancedSection` | Collapsed by default, titled "Advanced (N)", remembers its state for the session |
| `StageBlock` | Numbered stage with a connector line (Listening) |
| `StatTile`, `MiniBars` | Overview numbers and the per-hour bars |
| `DraggableCard`, `DropLane`, `UndoToast` | Drag moves, Ctrl+drag copies; the lane highlights on hover; Undo for 10 s; a "Move to…" menu as the keyboard way to do the same |
| `AgentTabs` | One tab per agent; scrolls when there are 9 |
| `SearchField` | Search box with filter chips |
| `ChatBubble` | User on the right, agent on the left, theme colours, sender and time |

Convert today's risky buttons to `DangerButton`: trash an agent, delete a
chat, and remove Agent Voice.

**Files.** `ui/*` and `ui/qmldir`, `bench/preview/preview.sh` (new `kit`
target), `pages/AgentDetailsPage.qml`, `Chats.qml`,
`pages/AboutPage.qml`.

**Settings.** None.

**Tests** (static; QML behaviour is not tested):

- `ui/qmldir` is in step, and qmllint is clean.
- New `test_ui_pieces_name_no_settings`: no `put(`, `putMap(` or
  `resetKey(` with a literal key anywhere in `ui/`.
- New `test_risky_actions_go_through_confirm`: each destructive verb
  (`agents trash`, `chats delete`, `--uninstall`, and later `reset`,
  `delete --all`, `stats clear`, link delete) appears in `pages/` and
  `Chats.qml` only inside an `onConfirmed` handler.

**Verify.**

- `preview.sh kit`: every piece, narrow and wide, dark and light.
- `clicks`: each `DangerButton` logged armed → cancelled, and
  armed → confirmed.
- **Shell restart** needed to see the converted buttons live; ask first,
  then screenshot.

**Risks.** Drag and drop in Quickshell QML may be fiddly; the keyboard
"Move to…" menu is the guaranteed path. Theme contrast in light themes:
check with flexoki-light.

**Going back.** UI only; nothing stored.

### R2 · Daemon bug sweep

| | |
|---|---|
| Covers | bugs I, J, K, C (detection and a first warning); testresults #10 |
| Needs | R0 |

**Goal.** Chats stop losing turns, the surprise chime is explained and
gone, open mic closes cleanly, and long turns that get cut off are noticed.

**Build.**

- **I.** `reconcile_agent` keeps `session_id` when only the level, model or
  effort changes. Only a project change drops it, as its docstring
  intends. Prove that `--resume` survives the new flags with one recorded
  turn. Check both directions (into and out of Trusted), since the
  2026-11-19 log showed one losing the chat and one not.
- **J.**
  - Add a structural log line per chime (name and reason, no text).
  - Find which call plays the "be-deep": most likely the `wake` chime on
    re-arm at `wake_listen.py:5462` after a turn dropped as "not meant for
    it" or "nothing heard".
  - A silent re-arm inside open mic or follow-up plays no chime.
  - Prove that no dropped turn resets the chat or the session.
- **K.** Closing open mic ends the follow-up window at once (state →
  listening) unless a capture is under way, so the "still listening"
  display clears.
- **#10.** With the mic muted, a typed turn still publishes
  thinking/speaking, so the HUD appears and the panel's chips stay
  current. Never while locked.
- **C.** Count turns cut at `maxUtteranceMs`. The state file gains
  `limit_hits` (today's count and the last time). The existing
  Conversation page gets a one-line note beside the longest-turn slider:
  "3 turns today hit the limit". R19 restyles it.

**Files.** `daemon/wake_listen.py` (**big shared**: `reconcile_agent`, the
chime sites, `end_open_mic`, state publishing), `daemon/runtime.py`
(`StateFile`), `pages/ConversationPage.qml` (one note), `tests/test_states.py`,
and the adapter tests.

**Settings.** None.

**Tests.** The frame loop is driven with the fake `sounddevice`, as
`CLAUDE.md` describes.

- A level change keeps the session; a project change drops it. Each has a
  mutation that goes red.
- A dropped open-mic turn keeps the chat id and plays no `wake` chime.
- `open-mic off` publishes `listening` within one tick.
- A muted typed turn publishes thinking/speaking.
- A forced cut increments `limit_hits`.
- `runtime.Config` and the state file are re-read, per the rule on values
  read once.

**Verify.**

- A 20-minute open-mic session, compared before and after: count of
  unexplained chimes from the new log lines; chat continuity after a level
  flip (Theo recalls his previous reply).
- `agentvoice open-mic off` clears the display at once.
- **Shell restart** needed to see the one-line note.

**Risks.** `wake_listen.py` is the riskiest file in the repo. The changes
are limited to the four sites named, each with a frame-loop test.

**Going back.** No stored data changes. An older build drops the session on
a level change again.

### R3 · Popup and readout

| | |
|---|---|
| Covers | items 2, 3; item 20's readout settings; bugs B, D |
| Needs | R1 |

**Goal.** A popup that does not bounce, without the old global permission
section, and a readout that can stay one size and keep the last reply in
view.

**Build.**

- **D / item 2.** Remove the "what Claude Code may do" section from
  `Panel.qml`: the level row, `setMainLevel` and `trustPending`. The
  `permissions` key keeps its one home on the Agents page. Update
  `test_settings_pages.py`'s docstring, which names this exception.
- **B / item 3.** In **locked** mode the readout area in the popup and the
  HUD has a fixed height and two fixed lines:
  - the last reply, dim, with the accent bar;
  - what is being said now, bright, with the yellow bar.

  Nothing appears or disappears; long text elides, as `PlainText`.
  **Dynamic** mode keeps today's grow and shrink.
- **Item 20, readout part.** A **Preview** button shows the HUD with
  sample text for 4 s, through the state file, so it renders exactly like a
  real turn. The HUD still hides **at once** on lock, whatever
  `hudKeepReply` says.

**Files.** `Panel.qml` (**big shared**), `Hud.qml`,
`pages/DisplayPage.qml`, `manifest.json`, `daemon/runtime.py`,
`daemon/wake_listen.py` (preview flag only), `tests/test_settings_pages.py`.

**New settings** (each in the manifest schema and defaults,
`runtime.DEFAULTS`, and one control on `DisplayPage`, which becomes Other
settings in R21):

| Key | Values (default) | Unreadable |
|---|---|---|
| `hudSize` | `locked` / `dynamic` (`locked`) | `locked` |
| `hudKeepReply` | bool (`true`) | `true` |
| `hudPosition` | `top` / `bottom` (today's place, `top`) | `top` |

**Tests.** Three places for each key. The popup no longer writes
`permissions`: an assertion in `test_settings_pages.py`.

**Verify.**

- `preview.sh popup` with a five-state sequence (idle → capture → thinking
  → speaking → followup) in `--state` files.
- `agentvoice lock`: the HUD hides with no linger, even with
  `hudKeepReply` on; then `agentvoice unlock`.
- A real open-mic chat, watched for bounce.
- **Shell restart** needed (QML); ask first.

**Measure.** Popup height across the five states, from the screenshots:
today's range in px, against 0 px in locked mode.

**Risks.** A fixed height clips long agent names in the chips row; elide,
and keep the full name in the tooltip.

**Going back.** An older build ignores the three keys and shows the
permission section in the popup again.

### R4 · Agents page

| | |
|---|---|
| Covers | item 8; bug E; item 15's "shared tools" gets its home (Communal → Tools) |
| Needs | R1 |

**Goal.** The same settings, organised: a header strip per agent, cards two
across, effort next to the model, and no duplicate sections at the
bottom.

**Build.**

- **Header strip:** name, program · model, effort, voice · speed, level,
  state dot. Click to unfold.
- **Cards:**
  - *Identity:* name and wake phrase side by side; runs on; model with the
    compact effort selector joined to it.
  - *Voice:* voice with ▶ Test; speed.
  - *Permissions:* level; project folder. The user likes these; restyled
    only.
  - *Tools:* today's per-agent switches as `ToggleChips`. Their home moves
    in R8.
  - *Collaboration & notes:* all four collaboration values (off / ask /
    announce / allow; none is dropped), accepts work, notes write.
  - *Agent:* enabled; the wake model for the main agent.
  - *Endpoint:* shown only when "runs on" is an endpoint.
- **Bug E.** Remove the "ON THE DESKTOP" group. Its three global keys
  (`desktopTools`, `browserTools`, `omarchySkill`) move in the **same
  commit** to a new **Communal → Tools** tab: "For every agent. An agent's
  own switch beats this."
- **Per-agent field homes.** Add `FIELD_HOMES` to `test_settings_pages.py`
  (Appendix B): every `voiceAgents[i]` field and its `main*` twin is
  changed on exactly one page, directly or through one named overlay
  function. Also cover the six defaults-only keys.

**Files.** `pages/AgentsPage.qml` (**big shared**; it should shrink as
pieces move to `ui/`), `ui/AgentCard.qml`, `pages/CommunalPage.qml`,
`tests/test_settings_pages.py`.

**Settings.** None new. **Moved:** `desktopTools`, `browserTools`,
`omarchySkill` → Communal.

**Tests.** The extended one-page test. A test that saving one field of one
agent leaves every other field and agent byte-identical, the data-loss
guard for `voiceAgents`.

**Verify.**

- `preview.sh agents`, narrow and wide, dark and light, with 1 and 8
  agents.
- **`clicks` diff:** the same actions on the old and new page write the
  same keys and values.
- Keyboard-only walk.
- **Shell restart** needed (QML).

**Risks.** The most-used page and the most fragile key (`voiceAgents`).
Mitigated by the clicks diff, the field test, and a `shell.json` copy
taken before deploy.

**Going back.** Same keys; an older build shows the global switches on its
Agents page.

### R5 · Agent details: agent tabs, personality and instructions

| | |
|---|---|
| Covers | items 9, 10 |
| Needs | R1 |

**Goal.** Quick switching between agents, and a personality editor that
helps instead of lecturing.

**Build.**

- **Item 9.** `AgentTabs` replace the agent drop-down. The main agent comes
  first, and the deep link `{page, agent, tab}` still works.
- **Item 10:**
  - **Trait chips:** tone (warm / dry / playful), length (brief /
    detailed), formality (casual / formal). They write one managed line at
    the top of `personality.md` (`Traits: warm, brief, casual.`) and read it
    back. Free text below is never touched. Unknown values in a hand-edited
    line are kept.
  - **One-line hints** with tooltips, replacing the paragraphs.
  - **Starter templates** offered when a box is empty, shipped in
    `daemon/templates/{role,personality,instructions}/`.
  - **Meters** against the budgets (role 300, personality 1500,
    instructions 2000), counting what is actually sent: the comment is
    stripped, and the Traits line counts.
  - **Try it:** `agentvoice try AGENT`. The daemon runs a quiet side turn
    ("one short sentence introducing yourself") with the current preamble
    and speaks the answer in the agent's voice.
    - At most one every 10 s.
    - Never saved to a chat.
    - Refused with the reason shown when the service is off, the agent is
      busy, the backend is unavailable, or the screen is locked.
- Trait parsing lives in Python (`agentvoice agents traits ID get|set`,
  JSON on stdin), so it is testable.

**Files.** `pages/AgentDetailsPage.qml` (**big shared**),
`ui/FileEditor.qml`, `daemon/agentfs.py` (**big**; traits helper),
`daemon/templates/`, `daemon/wake_listen.py` (**big**; a small `try` hook
on `side_adapter`), `bin/agentvoice`.

**Settings.** None (content stays in the folders).

**Tests.**

- Traits round-trip; free text untouched; budget including the line.
- A write keeps the `--base` stamp conflict check.
- Templates exist relative to the module.
- `try` is refused while locked or busy.
- The argv check covers the side turn.

**Verify.**

- `preview.sh details` and `detailshots`; clicks.
- **Live, by voice:** change Theo's tone chip, press Try it, hear the
  difference, then ask a real question and hear it there too.
- **Shell restart** needed (QML).

**Risks.** Chips rewriting text the user typed (only the managed line is
rewritten, under the base stamp). Try it costs a short turn; the button
says so.

**Going back.** An older build reads the Traits line as ordinary
personality text, which still works.

### R6 · Crew links and quarantine, enforced, with the table view

| | |
|---|---|
| Covers | item 16, build order part 1: the links list, enforcement, the table |
| Needs | R5 |

**Goal.** A saved list of who may do what to whom, enforced by the daemon,
plus quarantine. The page is only an editor.

**Build.**

- **`crewLinks`:** entries of the form
  `{from, to, allow: [ask|delegate|message|pass], askFirst}`. Direction
  matters.
  - **Missing key = legacy mode,** today's rule: every agent may reach every
    other, subject to its `collaboration` level. The page says so: "Not set
    up: every agent can reach every other. Add a link to switch to
    links-only." (Open question 5.)
  - **Present, even empty = links-only.** An agent-started call A → B with
    ability X runs only if a link A → B lists X.
  - **Unreadable or invalid = every agent-started call refused,** with the
    reason in the HUD.
- **Ability → tool:** ask → `ask_agent`, delegate → `delegate`,
  message → `message_agent`, pass → `pass_conversation`. `list_agents`
  shows only what the caller may reach and do. The daemon computes it from
  the caller's `SO_PEERCRED` identity.
- **`askFirst`** forces the `ask` card for that link even when the caller's
  level is `announce` or `allow`. The stricter of the two always wins.
- **`crewQuarantine`** (a list of ids), enforced in the daemon:
  - no outgoing calls: its collaboration tools are hidden *and* refused;
  - incoming links may carry only ask or delegate;
  - a delegation into quarantine carries the brief only (capped at 1000
    characters): it is not added to `shared_with`, is not replayed the
    transcript, and shares no session;
  - its answers come back wrapped and marked "from a quarantined agent";
  - no communal-note writes and no chat search (R16); see open question 6;
  - a **user-started** pass to it is refused, with the spoken reason
    "Scout is quarantined. Release it on the Crew map first." Talking to it
    by its wake word still works.

  Links do not govern user-started passes: the user is the approver.
- **Hardening the cards depend on.** Add `$RUNDIR/permissions/` and the
  text `agentvoice permit` to the orders guard, so an agent's plain attempt
  to answer its own card is asked about at every level. The determined case
  (Phase 16's open question) still needs an authenticated answer path:
  stated in the notes and left for V-07.
- **Crew map page, table view.** New `pages/CrewMapPage.qml`:
  - the From / To / Allows / Ask first table with add and delete
    (`DangerButton`);
  - a quarantine switch per agent;
  - the legacy banner;
  - per agent, "can reach / reached by".
- **Shortcuts.** This is the tenth page: Ctrl+1..9 for the first nine
  pages in sidebar order, Ctrl+0 for the tenth, Ctrl+PgUp / PgDn to step
  through all of them (open question 10).
- Fix the stale docstrings in `collab.py` and `crew_mcp.py` (call files →
  socket).

**Files.** `daemon/collab.py` (**big shared**; checks at request time),
`daemon/crew_mcp.py`, `daemon/runtime.py` (`crew_links()` and
`quarantined()`, read fresh on every call), `daemon/permission_hook.py`
(security-critical), `daemon/agentfs.py` (roster label), `manifest.json`,
new `pages/CrewMapPage.qml`, `pages/qmldir`, `Settings.qml` (**big**;
page entry, shortcuts), `bench/preview/preview.sh` (`crew` target).

**New settings** (manifest, `runtime.DEFAULTS`, one control on Crew map):

| Key | Values (default) | Unreadable |
|---|---|---|
| `crewLinks` | list (missing = legacy) | refuse every agent-started call |
| `crewQuarantine` | list of agent ids (`[]`) | refuse every agent-started call |

**Tests.** Collab is guard code, so each guard has a mutation that goes red.

- Unlinked, reversed and unlisted abilities are refused.
- **Legacy mode passes every existing Phase 16 test unchanged.**
- Corrupt `crewLinks` refuses everything.
- A quarantined agent can start nothing.
- A pass or message into quarantine is refused.
- A delegation into quarantine leaves `shared_with` unchanged and its brief
  is capped.
- `askFirst` raises the card at `allow`.
- A user pass to a quarantined agent is refused.
- `list_agents` is filtered.
- A change takes effect mid-session.
- The orders guard asks at Trusted for `agentvoice permit` and for writes
  to `permissions/`; silence, corruption and malformed input deny.

**Verify.**

- `preview.sh crew` (3 and 8 agents, legacy and links-only), narrow and
  wide, dark and light; clicks write `crewLinks` exactly.
- **Live, typed:**
  - Theo → Sora delegate with a link: it runs;
  - delete the link: refused, with the reason spoken;
  - quarantine Sora: Theo's ask runs, his pass is refused;
  - break `crewLinks` by hand: everything refused, the HUD says why.
- **Shell restart** needed (QML).

**Measure.** Cost of the link check per crew call, in µs (expected
negligible; measured anyway).

**Risks.** Locking collaboration out on upgrade (legacy mode prevents it).
Confusion between the level and the link (the inspector shows the effective
result, e.g. "Theo → Sora: delegate · asks you first (link) · announces
(Theo's level)").

**Going back.** An older build ignores both keys: collaboration returns to
all-to-all and quarantine lifts. That is **fail-open on downgrade**,
written in the notes and in V-02's going-back case.

### R7 · Crew map, drawn

| | |
|---|---|
| Covers | item 16, part 2: the picture, the drag-to-link, the quarantine zone, the inspector |
| Needs | R6 |

**Goal.** The interactive map from the mockup, editing the same list as
the table.

**Build.**

- Agent boxes are draggable. Their positions are UI state, kept by
  `agentvoice crew layout` in `$XDG_STATE_HOME/agentvoice/crew-layout.json`,
  not in `shell.json`. With no saved layout, agents are placed in a circle.
- Drag from an agent's dot onto another to create a link carrying `ask`.
  Click a line to open the inspector:
  - ability chips (chips not allowed into quarantine are disabled, and say
    why);
  - **Ask me first**;
  - **Also allow the reverse**;
  - **Delete line** (`DangerButton`).
- Arrows show direction, colours match the legend, and two-way pairs curve
  apart.
- Dragging into the red zone quarantines the agent, and dragging out
  releases it. A quarantined agent's dot is disabled.
- A Map / Table toggle. Both call **one** page function that writes
  `crewLinks`, the one-guard rule. The page validates through
  `agentvoice crew check` (stdin) before writing, using the same validator
  the daemon uses.

**Files.** `pages/CrewMapPage.qml`, `ui/DraggableCard` and `DropLane` (R1),
a new `ui/CrewEdge.qml` (QtQuick.Shapes), `daemon/collab.py` (validator
CLI), `bin/agentvoice`.

**Settings.** None new.

**Tests.** Validator cases (duplicates, self-links, unknown ids, abilities
not allowed into quarantine, oversize list). The layout file is never read
by the daemon.

**Verify.**

- `preview.sh crew --shots`: synthetic drags through `TestEvent`, as the
  `knob` target does; then the map, the table and the saved list compared
  from the clicks log.
- Live: one link drawn in the real shell, then a typed delegation proves
  it is enforced.
- **Shell restart** needed (QML).

**Risks.** Drawing curves and dragging in QML is the most time-uncertain UI
work in the plan. **Time box:** if it is not solid within the session, ship
the table only, write it up, and carry the map to a follow-up phase. The
table already enforces and edits everything.

**Going back.** As R6.

### R8 · Tool detection and real tool controls

| | |
|---|---|
| Covers | item 11 (tools found on the machine; a control for every tool); bug G; item 15 (shared tools) |
| Needs | R5, R6 |

**Goal.** Agent Voice finds the MCP servers and CLIs on the machine and
offers a real switch for each one, per agent and for everyone. Anything new
is off until switched on.

**Build.**

- **Spike first, one real turn each, recorded into FINDINGS §41 and a
  synthetic fixture.** Record Claude's init event with and without
  `--strict-mcp-config`:
  - which servers load: `~/.claude.json` user and project entries,
    `.mcp.json`, plugins, claude.ai connectors;
  - which skills from `~/.claude/skills` load, and whether
    `--setting-sources` can leave them out without dropping the user's
    other settings;
  - whether Claude's `permissions.deny` rules hold at every Agent Voice
    level.

  For Codex: whether a `-c` override can switch off a server from
  `~/.codex/config.toml`. **What gets enforced, and what the UI calls
  enforced, follows these recordings.**
- **Detector** (new `daemon/tooldetect.py`). It **reads** config files and
  never starts a server to probe it. It reads MCP definitions from
  `~/.claude.json`, the agent's project `.mcp.json`, Claude plugin
  manifests and `~/.codex/config.toml`, and finds CLIs from a short curated
  list plus "add a CLI by name", checked with `shutil.which`. Output:
  `agentvoice tools scan --json` (name, source, kind, which backends can
  use it). The result is cached in `$RUNDIR`, with a Rescan button.
- **Delivery to Claude:**
  - one generated MCP config in a **0600 file** (`$RUNDIR/prompts/`),
    passed as `--mcp-config <file>` plus `--strict-mcp-config` where the
    spike proves it. The file holds Agent Voice's own servers and the
    enabled detected servers, copied verbatim;
  - today's argv JSON moves into that file too;
  - switching a tool off lets the idle warm process go, as today.
- **Delivery to Codex:** per the spike.
- **CLIs:** "told" (one line in the preamble), with the label **told, not
  enforced**. Where the spike shows deny rules hold, a disabled CLI is also
  denied for Claude, and the label says **enforced** for Claude only.
- **Live status:** the adapter keeps the init event's server list (name and
  status), for this tab and R13.
- **Agent details → Tools & skills** (bug G):
  - *Built-in tools:* desktop, browser, Omarchy commands, crew.
  - *Found on this machine:* one switch per detected tool. Each row shows
    whether it is on, whether this backend can use it, and whether it asks
    first at this agent's level. A row that cannot work says why.
- **The home of the per-agent tool switches moves here,** through one
  overlay function `s.setAgentTool(id, key, value)` in `Settings.qml`. The
  Agents card's Tools chips become a read-only summary that links here
  (open question 3).
- **Communal → Tools:** the R4 global switches, plus "on for every agent"
  for each detected tool (`sharedTools`).
- **Existing behaviour.** Strict mode would switch off servers Claude
  agents load today (on this machine, `desktop-control`). No migration
  writes `shell.json`. Instead, a one-time notice on the Tools tab lists
  "loaded before this version, now off", each with **Turn on for Theo**
  (open question 4).

**Files.** New `daemon/tooldetect.py`; `daemon/adapters/claude_code.py`
and `codex.py`; `daemon/runtime.py` (`tools_for` extended);
`daemon/wake_listen.py` (**big**; `apply_extras` hook only);
`daemon/agentfs.py` (**big**; catalog); `bin/agentvoice`;
`pages/AgentDetailsPage.qml` (**big**); `pages/CommunalPage.qml`;
`pages/AgentsPage.qml` (**big**; summary chips); `Settings.qml` (**big**;
`setAgentTool`); `manifest.json`.

**New settings:**

| Key | Values (default) | Unreadable | Control on |
|---|---|---|---|
| `sharedTools` | map tool → bool (`{}`, so everything detected is off) | `{}` | Communal → Tools |
| per agent: `mcp:<name>` / `cli:<name>` entries in `mainTools` and `voiceAgents[i].tools` | inherit / on / off (inherit → `sharedTools` → off) | `off` | Agent details → Tools & skills (`setAgentTool`) |

`mainTools` and `voiceAgents` already exist in the manifest defaults and in
`runtime.DEFAULTS`; the new entries need no schema change, and
`FIELD_HOMES` records the move.

**Tests.**

- The detector parses synthetic configs (malformed, huge, symlinked, with
  secrets) and runs no subprocess. A test patches `subprocess` to fail.
- New tools are off by default; unreadable values are off; the inherit
  chain resolves.
- **Claude's argv holds no MCP JSON** (a file path only), and the file is
  0600.
- The strict flag is present when tools are configured.
- Switching off reaches a warm process.
- An `mcp__x__y` call asks at Ask level (hook test).
- Mutation: flip the default to on, and a test goes red.

**Verify.**

- `preview.sh tools` and `details`; clicks.
- **Live, typed:** turn `gh` on for Sora only, and only Sora uses it; turn
  a detected MCP server on for Theo, and its tools appear in his init event
  and the status shows "running".
- **Shell restart** needed (QML).

**Measure.** S on `sora`: no detected servers against three enabled, and
strict against not strict (A11-4 gate rules).

**Risks.** Strict mode removing tools the user relies on (the notice and
one-click restore). claude.ai connectors behaving differently (the spike
decides). CLI switches being text only for some backends (honest labels).

**Going back.** An older build has no strict mode: Claude agents load every
user MCP server again, and the per-agent `mcp:` and `cli:` entries are
ignored.

### R9 · Skills: scan, lanes, drag

| | |
|---|---|
| Covers | item 11 (skills as draggable cards, found automatically, an Unused area); item 15 (show which agents can't use skills) |
| Needs | R8 |

**Goal.** Every skill on the machine shown as a card in its owner's lane,
moved by dragging, with undo.

**Build.**

- **Scan:** agent folders, Communal, `~/.claude/skills`, Claude plugin
  skills, and `~/.codex/skills` if present. Each card has a details
  drop-down: description, source path, size, problems, and who gets it.
- **Lanes:** one per agent (main first), **Communal**, and **Unused**
  (skills outside Agent Voice that no agent uses).
- **Moves:**
  - between Agent Voice lanes, a drag moves and Ctrl+drag copies, with
    Undo;
  - **from Unused, a drag always copies (imports).** Agent Voice never
    edits or deletes a skill it did not create;
  - into Communal, confirm first: "Every agent will get this skill";
  - from a quarantined agent, confirm with a warning;
  - a name clash is refused with a reason, and shadowing is shown.
- **CLI:** `agentvoice agents skills move|copy FROM NAME TO`,
  `skills import PATH TO`, `skills undo OP`. Names are checked by the
  existing regex.
- **Communal → Skills:** marks each agent whose backend cannot take skills,
  and why (endpoint: none; Codex: through the index).
- **Honest note from the R8 spike.** If Claude agents also see
  `~/.claude/skills` and that cannot be switched off, the Unused lane says
  "Claude Code agents can still see these".

**Files.** `daemon/agentfs.py` (**big**; skill operations, under its
lock), a new `daemon/skillscan.py`, `pages/AgentDetailsPage.qml` (**big**),
`pages/CommunalPage.qml`, `bin/agentvoice`.

**Settings.** None.

**Tests.**

- Move, copy and undo round-trips, each saved to `.history`.
- **The external source is unchanged:** its hash before and after.
- A symlink inside an imported skill is refused.
- A malformed import is listed with its problem and not delivered.
- A clash is refused.
- The plugin dir is renamed by content and the warm process lets go.
- Audit lines hold names and sizes only.
- Two moves at once are serialised.

**Verify.**

- `preview.sh details` with a synthetic skills set; drags through
  `TestEvent`.
- Live, typed: move a skill from Theo to Communal, and Sora can use it;
  undo, and she cannot.
- **Shell restart** needed (QML).

**Measure.** Plugin-dir rebuild time with 20 skills. S on `sora` with three
skills, if the index grew.

**Going back.** Skills sit where they were moved; an older build reads the
folders as they are. Imports are plain copies.

### R10 · The command table, and commands inside sentences

| | |
|---|---|
| Covers | item 1; bug A; item 22's caution |
| Needs | R2 |

**Goal.** "…take notes, and keep listening, because I might pause" turns
open mic on, while "stop listening to that song" does nothing. Any command
that fires is said out loud.

**Build.**

- **One table** in `speech_text.py`, built from today's phrase sets
  (nothing lost). Per command: id, phrases, a one-line effect, where it may
  appear, whether it needs the wake word, and the fixed sentence spoken
  when it fires. `agentvoice commands --json` adds the agents' wake phrases
  from settings, and feeds R11, R19 and R21.
- **`find_command(text, mode)`** returns the command, the remaining text,
  and where it was found. Starting policy, to be checked against the
  corpus:

| Command | Alone | Start | End | Own clause (`clause` mode) |
|---|---|---|---|---|
| keep listening / open mic | yes | yes | yes | yes |
| stop listening / mic off | yes | yes | yes | no |
| goodbye | yes | no | yes | no |
| new chat | yes | yes | no | no |
| continue the chat about … | yes | yes | no | no |
| pass this to NAME | yes | yes | no | no |
| full stop, stop everything | yes | no | no | no |
| stop, cancel, never mind | yes | no | no | no |
| move this to the terminal | yes | no | no | no |

- **Exclusions:**
  - an object after the verb ("stop listening *to* …", "keep listening
    *to* me");
  - a negation ("don't keep listening");
  - reported speech ("he said keep listening").
- **When one fires from inside a sentence:**
  - its fixed sentence is spoken ("Open mic on.") and shown in the HUD;
  - the remaining text goes to the agent as the request, if any is left;
  - saying "no" or "cancel that" within 3 s undoes an open-mic toggle.
- `alone` mode is exactly today's behaviour.

**Files.** `daemon/speech_text.py` (earns tests), `daemon/wake_listen.py`
(**big**; one hook where commands are checked), `bin/agentvoice`,
`pages/ConversationPage.qml` (the control), `manifest.json`,
`daemon/runtime.py`, `tests/test_speech_text.py`, and new
`tests/fixtures/commands/{fire,nofire}.txt` (synthetic).

**New settings:**

| Key | Values (default) | Unreadable | Control on |
|---|---|---|---|
| `commandsInSentences` | `alone` / `edges` / `clause` (`edges`; open question 7) | `alone` | Conversation |

**Tests.**

- The corpus, per mode; the remaining text; each policy row; each
  exclusion.
- **`alone` gives byte-identical results** on every existing
  `speech_text` test.
- The table's phrases equal the old sets.
- The spoken sentence comes from the table, never from a model.

**Verify.**

- **Live, by voice:** the example sentence in each mode; the false-trigger
  list said aloud; one command at the start and one at the end. The
  journal's structural line names the command and mode, never the words.
- **Shell restart** needed for the new control.

**Measure.** `bench/commands_scan.py` runs the detector over the user's own
saved chats **locally** and prints counts only: would-fire per mode. The
user labels a sample as meant or not meant. That gives a false-trigger rate
per mode in FINDINGS, and the default is chosen from those numbers.

**Risks.** Misfires, kept small by the policy table, the spoken sentence,
undo, and the conservative default.

**Going back.** An older build ignores the setting: commands work only when
said alone.

### R11 · The Agent Voice skill

| | |
|---|---|
| Covers | item 11 ("an Agent Voice skill"); `voice-commands-notes.md` |
| Needs | R9, R10 |

**Goal.** Agents can look up how Agent Voice works instead of reading its
source.

**Build.**

- **New `daemon/agentvoice_skill.py`,** modelled on `omarchy_skill.py`.
  It writes `skills/agentvoice/SKILL.md` containing:
  - what Agent Voice is;
  - the command table (phrases, effect, where each may appear);
  - the agents' wake phrases, read at build time;
  - the CLI commands it is fine to suggest;
  - each settings key with its page and meaning, generated from the
    manifest and the page map;
  - files, from `paths.py`;
  - what an agent cannot do itself. Example: a terminal handoff started
    inside a turn ends that turn, so the agent tells the user the phrase
    instead.
- **It never teaches** `agentvoice permit`, settings writes, or anything
  the orders guard covers. It tells agents to give the user the phrase
  (open question 11).
- **Delivery:** in each Claude agent's plugin dir beside `omarchy`; one
  index line for the other CLIs; nothing for endpoints. `agentvoice`
  becomes a reserved skill name.
- **Rebuilt when stale:** a hash of the generator, `speech_text.py`,
  `manifest.json` and the wake phrases.

**Files.** New `daemon/agentvoice_skill.py`, `daemon/agentfs.py`
(**big**; plugin dir), `pages/CommunalPage.qml`,
`pages/AgentDetailsPage.qml` (**big**), `manifest.json`,
`daemon/runtime.py`.

**New settings:**

| Key | Values (default) | Unreadable | Control on |
|---|---|---|---|
| `agentvoiceSkill` | bool (`true`) | `false` | Communal → Tools |
| per agent `agentvoiceSkill` in `mainTools` / `voiceAgents[i].tools` | inherit / on / off | inherit | Agent details → Tools & skills |

**Tests.**

- The skill's phrases equal the table.
- **No forbidden command appears** (`permit`, `bar set`).
- A phrase change marks it stale.
- The reserved name is refused for a user skill.
- Size within the 20,000-character limit; index line ≤ 160 characters.
- Only agents with it on receive it.

**Verify.**

- Live, by voice: "Theo, how do I keep the mic open?" is answered from the
  skill. The same question to Hazel (Codex) is answered from the index.
- **Shell restart** needed for the two new switches.

**Measure.** S on `sora` (gate). Claude's skill listing grows by one line;
other backends get one index line.

**Going back.** An older build does not generate it; plugin dirs rebuild
without it.

### R12 · Note categories, and moving notes

| | |
|---|---|
| Covers | item 12; item 15 (Communal notes get the same) |
| Needs | R9 |

**Goal.** Notes organised by topic, and moved between agents and Communal
like skills.

**Build.**

- **A category is one note file per topic** (open question 9): "this
  system", "project agent-voice", and so on. That is what a note file
  already is, so storage does not change. What changes:
  - the crew tools steer agents toward it: `notes_list` returns each topic
    with its first line, and the tool descriptions say "one note per topic;
    append rather than start a new note";
  - the Notes tab shows topic cards in owner lanes (agent and Communal),
    with drag to move, Ctrl+drag to copy, and Undo;
  - **Combine** merges several small notes into one topic note. It is a
    user action, and each source's history is kept.
- **Moving a note** carries its file, history and meta entry: the
  revision continues, and the author, taint and lock travel with it.
  - Both scopes are locked, always in the same order, to avoid deadlock.
  - Each move writes an audit line.
  - Into Communal: confirm. From a quarantined agent, or a tainted note:
    confirm, showing the mark.
- **Agents cannot move or combine notes.** There is no tool for it; only
  the user can.

**Files.** `daemon/notes.py`, `daemon/crew_mcp.py` (descriptions only),
`daemon/agentfs.py` (**big**; CLI), `ui/NotesPanel.qml` (841 lines; cards
and lanes), `pages/AgentDetailsPage.qml` (**big**),
`pages/CommunalPage.qml`.

**Settings.** None.

**Tests.**

- A move keeps rev, history, meta, taint and lock.
- 8 writers during a move lose nothing.
- A clash is refused.
- Lock ordering: no deadlock under concurrent cross-moves.
- A corrupt destination meta refuses the move (fail closed).
- Audit lines hold no content.
- Combine keeps every source's history.
- Crew tools stay scoped to `mine` and `communal`.

**Verify.**

- `preview.sh notes` with synthetic notes; drags.
- Live, typed: Theo appends to an existing topic note instead of starting a
  new one; move it to Communal, and Sora reads it.
- **Shell restart** needed (QML).

**Going back.** An older build reads notes wherever they now are; the meta
format is unchanged.

### R13 · Agent details: Advanced

| | |
|---|---|
| Covers | item 14, all ideas, with warning + confirm on everything risky |
| Needs | R8 (live server status) |

**Goal.** One tab that shows in depth how this agent runs, what it is
connected to, and what it did recently.

**Build. Shown:**

- The **full assembled prompt** (the existing `PromptPreview`, extended to
  the skills index and roster).
- The **exact command line**, from `agentvoice agents runinfo ID --json`.
  It is built by the same function the adapter uses, and holds prompt-file
  paths, never text.
- **MCP servers and tools** with live status (running / failed / off),
  from R8's saved init event.
- **Session:** id, resume on/off, and **Start fresh** (`DangerButton`,
  which runs `chat-new` for this agent).
- **Timeouts:** the hung-turn limit, and the endpoint timeout for an
  endpoint.
- **Working directory:** shown, with a link to change it on the Agents
  card.
- **Recent log lines** for this agent: structural only, from a small
  per-agent ring in the daemon. Never speech, even with `logSpeech` on.
  Plus **Open full log**.
- **Recent permission decisions:** a new audit kind `permission` with time,
  agent, tool name, decision and level. No arguments, no paths.
- **Export** (exists); **Duplicate** (folder and settings entry under a new
  id); **Reset to defaults**. Reset trashes the agent first, so Restore
  undoes it. Both are `DangerButton`s.

**Build. Edited:**

- Resume.
- The hung-turn limit.
- **Extra flags:**
  - checked in the adapter at launch, not only on screen, against a
    per-program denylist: anything touching permissions, settings, hooks,
    MCP, plugins, tool allow/deny lists, extra dirs, system prompts,
    session flags or the stream format. Examples: `--permission-mode`,
    `--dangerously-skip-permissions`, `--settings`, `--setting-sources`,
    `--mcp-config`, `--strict-mcp-config`, `--plugin-dir`,
    `--allowedTools`, `--add-dir`, `--append-system-prompt*`, `--resume`,
    `--output-format`, and Codex's `-c`, `--sandbox`, `--full-auto` and
    bypass flags. `--flag=value` and abbreviated forms are covered;
  - a refused flag is shown with its reason;
  - accepted flags show ⚠ and need a confirm.
- **Extra environment variables:**
  - stored in `~/.config/agentvoice/agent-env.json` (**0600**), never in
    `shell.json` (0644);
  - written through `agentvoice agents env ID set` (stdin);
  - names checked against a denylist (`PATH`, `LD_*`, `PYTHON*`, `HOME`,
    `XDG_*`, `*_PROXY`, `*_BASE_URL`, `NODE_OPTIONS`, `CLAUDE_CONFIG_DIR`,
    `CODEX_HOME`);
  - never logged, and never included in diagnostics.
- The page says that flags are visible to other local users through
  `/proc`, so secrets belong in environment variables.

**Files.** `pages/AgentDetailsPage.qml` (**big**),
`daemon/adapters/base.py`, `claude_code.py`, `codex.py` (runinfo, extras,
resume, timeout), `daemon/audit.py` (new kind), **`daemon/permission_hook.py`
(security-critical:** it records each decision; a failed record must never
change the decision), `daemon/wake_listen.py` (**big**; log ring, start
fresh), `daemon/agentfs.py` (**big**; duplicate, reset), `Settings.qml`
(**big**; `setAgentField`), `manifest.json`, `daemon/runtime.py`.

**New settings** (per agent; controls on Agent details → Advanced through
`s.setAgentField`; the `main*` twins go in the manifest and
`runtime.DEFAULTS`):

| Key (main / extra) | Values (default) | Unreadable |
|---|---|---|
| `mainResume` / `voiceAgents[i].resume` | bool (`true`) | `true` (today) |
| `mainIdleTimeoutS` / `.idleTimeoutS` | 30–600 (`90`) | `90` |
| `mainExtraArgs` / `.extraArgs` | list of strings (`[]`) | `[]` (nothing passed) |

**Tests.**

- runinfo equals the adapter's argv; no user text in it.
- **Denied flags are refused at launch** (every form).
- The env denylist works; the env file is 0600 and never printed.
- **The hook decides the same when its audit write raises.** Mutation:
  make the audit raise, and silence still denies.
- Permission audit lines hold no arguments (the AST check).
- Duplicate and reset round-trip with Restore.
- Resume off means no `--resume`; the timeout reaches the Watchdog.
- Three places for each key.

**Verify.**

- `preview.sh details --arg '{"page":"agentdetails","tab":"advanced"}'`;
  clicks.
- **Live, typed:**
  - add a harmless flag;
  - sample `/proc/<pid>/cmdline` during a turn: it equals the shown command
    line and holds no user text;
  - add a denied flag: refused, with the reason on screen;
  - reset a scratch agent, then Restore.
- **Shell restart** needed (QML).

**Risks.** Extra flags breaking turns: the last error is shown, with
one-click clear. Hook changes are security-critical: tests and mutation.

**Going back.** An older build ignores the new keys and the env file:
agents run without extras and always resume.

### R14 · Communal: who gets it, preview, import, history

| | |
|---|---|
| Covers | item 15 (per-agent opt-out, a combined preview, import, history and undo); Tools, Skills and Notes came in R8, R9 and R12 |
| Needs | R8, R9, R12 |

**Goal.** Choose which agents take communal content, see what each one
ends up with, import, and undo.

**Build.**

- **Who gets communal:** one switch per agent. An opted-out agent is not
  told the rules or defaults and gets no communal skills. Communal notes
  stay reachable through the notes tool, because they are data asked for,
  not instructions; the page says so.
- **Preview:** pick an agent, see its whole prompt piece by piece with
  sources (`PromptPreview`) and the total characters.
- **Import:** `agentvoice agents import communal DIR` (rules, defaults,
  skills). A dry-run list comes first, then a confirm. Each file is saved
  to history; symlinks and oversize files are refused.
- **History and Undo** on the Rules and Defaults editors. Versions are
  already saved (Phase 9); this adds the list (view, restore) and Undo.
- Communal → Chats stays as a filtered view of the Chats page.

**Files.** `pages/CommunalPage.qml`, `ui/FileEditor.qml`,
`daemon/agentfs.py` (**big**; `parts_from` and `plugin_dir` honour the
opt-out; import), `daemon/runtime.py`, `manifest.json`.

**New settings:**

| Key | Values (default) | Unreadable | Control on |
|---|---|---|---|
| `communalOff` | list of agent ids (`[]`) | `[]`, so every agent gets communal (rules may carry safety text, so failing towards "told" is the safe side) | Communal |

**Tests.**

- An opted-out agent's preamble has no rules or defaults, and the
  empty-folder byte-identity (A11-1) still holds.
- Its plugin dir has no communal skills.
- Unreadable → everyone gets communal.
- An import dry run changes nothing; import refuses symlinks and oversize
  files.
- History and undo round-trip.

**Verify.**

- `preview.sh shared`; clicks.
- Live, typed: opt Sora out, and she no longer follows a communal rule;
  opt her back in.
- **Shell restart** needed (QML).

**Measure.** S on `sora` (gate). The change can only shrink the prompt; it
is confirmed anyway.

**Going back.** An older build ignores `communalOff`, so opted-out agents
get communal again.

### R15 · Chats page

| | |
|---|---|
| Covers | item 5; item 6 (cleaner list, more per chat, search box, messaging layout); item 13's rename; item 20 (chat privacy moves here) |
| Needs | R1 |

**Goal.** Chats get their own sidebar page with an easy list and a
messaging-app view, and the confusing top-row button goes.

**Build.**

- **New `pages/ChatsPage.qml`** in the sidebar as **Chats**. The list and
  viewer in `Chats.qml` become one shared component, used here, on Agent
  details → Chats, and on Communal → Chats. Item 5 says to keep those.
- **Remove the top-row "Conversations" button** from `Settings.qml`. The
  conversation *settings* page stays "Conversation", so the two names no
  longer collide.
- **Settings card at the top:**
  - `saveChats`, `chatRetention` and `keepHistory`, moved from Display;
  - where chats are stored, and their size (`agentvoice chats stats
    --json`);
  - **Delete all saved chats** (`DangerButton`; the confirm states the
    count).
- **List:** title, agent(s), date, turn count, and summary (the last-line
  preview until R16), with agent filter chips and a search box (a new
  `agentvoice chats search`, query on stdin, using today's scorer).
- **Viewer:**
  - the user on the right and the agent on the left, coloured from the
    theme (`Commons.Color`), with each agent's own accent;
  - questions between agents folded to one line; tool lines centred and
    dim;
  - the existing actions: continue, share, send, rename, pin, export,
    delete.
- **Eleventh page:** About becomes reachable by click, Ctrl+PgDn and (from
  R23) search.

**Files.** New `pages/ChatsPage.qml`, `Chats.qml`, `ui/ChatBubble.qml`
(R1), `Settings.qml` (**big**; button removed, page added),
`pages/DisplayPage.qml` (keys out), `pages/AgentDetailsPage.qml` (**big**),
`pages/CommunalPage.qml`, `daemon/chats.py` (`delete --all`, `stats`,
`search`), `bin/agentvoice`.

**Settings.** None new. **Moved:** `saveChats`, `chatRetention`,
`keepHistory` → Chats.

**Tests.**

- `delete --all` removes only files in the chats folder (never a link
  target) and reports the count.
- The search query arrives on stdin (the argv check).
- The one-page test.
- The confirm test covers `delete --all`.

**Verify.**

- `preview.sh chats` (new target) with a synthetic set: long titles,
  unicode, and text that looks like HTML, to prove `PlainText`. Narrow and
  wide, dark and light; clicks.
- Live: browse, search, continue a chat by click.
- **Shell restart** needed (QML).

**Going back.** An older build shows the chat privacy settings on its
Display page (same keys). Chat files are unchanged.

### R16 · Chats: names, summaries, and search as an agent tool

| | |
|---|---|
| Covers | item 6 (proper names, more information, search for agents) |
| Needs | R15, R6 (quarantine) |

**Goal.** Each chat gets a real name and a one-line summary. Agents can
search old chats, but only the chats they are allowed to see.

**Build.**

- **Names and summaries.**
  - The instant title stays (`title_from`).
  - After a chat has been idle for 2 minutes, a quiet side turn on **the
    chat's own agent** writes a title (≤ 60 characters) and a summary
    (≤ 160). That provider already has the conversation. The prompt goes
    on stdin, and the output is cleaned.
  - Stored as `auto_title` and `summary` in the chat file. **A rename by
    the user always wins** and is never overwritten.
  - At most one per chat per change, and ten an hour. Off when `saveChats`
    is off.
- **More per chat:** participants, duration and turn count in the index.
- **Agent tools:** `chats_search(query, limit)` and
  `chats_read(id, from, to)` in `crew_mcp.py`, **answered by the daemon
  over `calls.sock`**, which identifies the caller by `SO_PEERCRED`.
  - **Scope per agent (`chatSearch`):**
    - `own` (default): chats the agent owns or is in `shared_with`, which
      is the existing replay rule;
    - `all`: every saved chat;
    - `off`.
  - A quarantined agent is always `off`.
  - Results are capped (10 hits; 8000 characters per read) and wrapped as
    information with the date and speakers.
  - **The query is never logged or audited.** The audit records the kind,
    the caller, the hit count and sizes.
  - With `saveChats` off, the tool says there are no saved chats.
- **Search CLI:** filters `agent:`, `before:` and `after:`. Ranking extends
  today's scorer. An index file is added only if the measurement says it
  is needed.

**Files.** `daemon/chats.py`, `daemon/collab.py` (**big**; a new call
kind) or a new handler module, `daemon/crew_mcp.py`,
`daemon/wake_listen.py` (**big**; idle summariser hook on
`side_adapter`), `daemon/permission_hook.py` (`chats_*` count as reads),
`daemon/runtime.py`, `manifest.json`, `pages/ChatsPage.qml`,
`pages/AgentsPage.qml` (**big**).

**New settings:**

| Key | Values (default) | Unreadable | Control on |
|---|---|---|---|
| `chatSummaries` | `off` / `owner` (`owner`; open question 8) | `off` | Chats |
| `mainChatSearch` / `voiceAgents[i].chatSearch` | `off` / `own` / `all` (`own`) | `off` | Agents → Collaboration, notes & chats |

**Tests.**

- **Scope:** own, all, off, quarantined and unreadable each behave as
  above; a forged caller id in the call is refused.
- Caps and wrapping.
- `saveChats` off.
- **The query appears in no log or audit line** (the AST check extended).
- A summary never overwrites a rename.
- The side turn's text travels on stdin.
- Summaries are cleaned of control characters and capped.
- Rate limit.

**Verify.**

- **Live:** by voice, "Theo, find our chat about the wake word last week"
  uses the tool. Typed: Sora with `own` cannot find Theo's chat. Titles
  and summaries appear after the idle time.
- **Shell restart** needed (QML).

**Measure.** Search latency over 1000 synthetic chats (median and p95).
Summary side-turn cost per backend, in seconds, in FINDINGS.

**Going back.** An older build ignores `auto_title` and `summary` (it shows
the title) and has no chat tools.

### R17 · Stats, and the Overview page

| | |
|---|---|
| Covers | item 7 (every listed statistic); item 20 (stats privacy) |
| Needs | R2 |

**Goal.** An Overview with real numbers that match the journal, and no
transcript in them.

**Build.**

- **New `daemon/stats.py`.**
  - Per-day counters in `DATA_DIR/stats/YYYY-MM-DD.json` (0600): turns per
    agent; wakes accepted and rejected by stage (verifier, second check);
    timings as fixed-bucket histograms (wake → first word, end of speech
    → first word, transcription ms), for median and p95; limit hits (R2).
  - Written at the end of a turn, atomically, under a lock. **Never
    text.** Kept 90 days.
  - `agentvoice stats [--days N] --json`.
- **Live in the state file:** service start time, the daemon's memory,
  and its agents' memory shown separately.
- **Overview page:**
  - tiles: turns today, per agent, with a week toggle; median wake to first
    word and transcription time; wakes against rejections, with the share
    the second check caught; uptime and memory;
  - Agents card: state and **last chat →**, which opens it on the Chats
    page;
  - Microphone card: gain, level, mute. The user likes it; restyled only;
  - per-hour wake bars.

**Files.** New `daemon/stats.py`, `daemon/wake_listen.py` (**big**; calls
where the structural timing lines are already printed), `daemon/runtime.py`,
`bin/agentvoice`, `pages/OverviewPage.qml`, `pages/DisplayPage.qml`,
`manifest.json`.

**New settings:**

| Key | Values (default) | Unreadable | Control on |
|---|---|---|---|
| `keepStats` | bool (`true`) | `false` (collect nothing) | Display → Privacy (Other settings in R21), with **Clear stats** (`DangerButton`) |

**Tests.**

- **The stats AST check:** only typed ids and numbers, as for the audit
  log.
- A driven turn in `test_states.py` gives stats **equal to its structural
  log lines** (rehearses V-21).
- `keepStats` off writes nothing.
- A corrupt day file is skipped and replaced, never failing a turn.
- Pruning, and concurrent writers.

**Verify.**

- `preview.sh` overview with a synthetic stats file.
- Live: 10 real voice turns, then compare the Overview with the journal.
- **Shell restart** needed (QML).

**Measure.** Cost of the stats write per turn (µs); file size per day at
200 turns; the memory figure checked against `ps`.

**Going back.** An older build ignores the stats files and the key.

### R18 · Listening as a pipeline

| | |
|---|---|
| Covers | item 18 |
| Needs | R17 (the "today" line) |

**Goal.** One top-to-bottom view of how a wake word passes through, with
each stage's settings inside it.

**Build.** Every Listening key keeps its single home here. `phrase` and
`owwModel` stay on the Agents card and are shown with a link.

1. **Microphone.**
   - Level meter with the gate marked.
   - Gate fixed / dynamic (`adaptiveGate`).
   - **Adapts slow / normal / fast** (new).
   - Advanced: the fixed level (`micThresholdDb`), the dynamic margin
     (`gateMarginDb`), and the exact look-back.
2. **First listener.**
   - Engine (`engine`) and its sensitivity (`owwThresholdPct` or
     `sherpaThresholdPct`).
   - **Engine-specific blocks appear only for the chosen engine.** The
     old "Your voice" (`useVerifier`, record and train) sits inside
     openWakeWord's block; `shortNameBoostPct` and `wakeAlsoSounds` sit
     inside sherpa's.
3. **Second check.**
   - Engines (`crossCheckEngines`).
   - Advanced: window (`crossCheckMinMs`, `crossCheckMaxMs`), trailing
     words, and the Whisper hint.
4. **Decision.**
   - **Wake counts if: first only / both agree** (`wakeCrossCheck`, one
     control, not two).
   - Confidence (`wakeConfidencePct`).
   - "Today: 31 wakes · 4 rejected by the second check", from stats.

The mockup's "either" is not offered. The second check only runs on what
the first one flagged, so "either" would behave like "first only"; the
hint says so.

**Daemon.** The noise floor's look-back becomes a plain attribute, set
after the spec check (`CLAUDE.md`: a number never rebuilds a model).
Resizing keeps the most recent frames.

**Files.** `pages/ListeningPage.qml` (838 lines), `daemon/noise_floor.py`,
`daemon/wake_listen.py` (**big**; assignment only), `manifest.json`,
`daemon/runtime.py`.

**New settings:**

| Key | Values (default) | Unreadable | Control on |
|---|---|---|---|
| `gateAdaptS` | 5–120 s (`30`, today's); shown as slow 60 / normal 30 / fast 10, exact value under Advanced | `30` | Listening |

**Tests.**

- A changed `gateAdaptS` reaches the noise floor without a rebuild, read
  through `runtime.Config` (earns a test).
- A resize keeps the last frames.
- Bounds; unreadable → 30.

**Verify.**

- `preview.sh` listening for each engine (vosk, oww, sherpa); clicks.
- **Live:** switch engines, and only that engine's block shows;
  `agentvoice monitor` confirms the thresholds; the wake test.
- **Shell restart** needed (QML).

**Measure.** Time to settle after a synthetic 10 dB step in room noise at
10, 30 and 60 s, in FINDINGS.

**Going back.** An older build ignores `gateAdaptS` and uses 30 s.

### R19 · Conversation page

| | |
|---|---|
| Covers | item 13 (every approved part); bug C on the page |
| Needs | R2, R10 |

**Goal.** The same settings, compact. Timings become a picture, and open
mic shows its live state.

**Build.**

- **Pace presets** become a compact selector at the top. They write the
  same keys the preset buttons write today.
- **Cards:**
  - *Follow-ups:* `conversationMode`, `followUpMs`.
  - *Open mic:* live state (on/off and time left from the state file) with
    a **Turn on / Turn off** button (`agentvoice open-mic`);
    `openMicIdleMin`, `openMicAddressedOnly`, `openMicAuto`.
  - *While it works:* `narration`, `narrationSilenceS`.
  - *Talking over it:* `fullStopAnytime`, `bargeIn`, `bargeOnHeadset`,
    with `bargeFactor` under Advanced.
- **"A turn, start to end":** a timeline drawn from the live values
  (lead-in, you talk up to `maxUtteranceMs`, the pause that ends a turn,
  the reply).
  - Under it, the limit note from R2 ("3 turns today hit the limit.
    **Raise it →**"), which opens Advanced at the longest-turn control.
- **Advanced timings:** `leadInMs`, `trailingSilenceMs`, `quickEndMs`,
  `minUtteranceMs`, `maxUtteranceMs`, `echoTailMs`.
- **Voice commands card:** generated from `agentvoice commands --json`,
  with the `commandsInSentences` control from R10.

**Files.** `pages/ConversationPage.qml`, a new `ui/TurnTimeline.qml`.

**Settings.** None new.

**Tests.** The one-page test. The commands card reads only the generated
list: a test that the page holds no command phrases written by hand.

**Verify.**

- `preview.sh` conversation with a state that has open mic on and
  `limit_hits` above 0.
- **`clicks` diff** against the old page: the same keys and values.
- Live: the open-mic button toggles it and the time left counts down.
- **Shell restart** needed (QML).

**Going back.** Nothing stored changes.

### R20 · Voice page

| | |
|---|---|
| Covers | item 19; bug F |
| Needs | R1 |

**Goal.** The page the user likes, tidier: per-agent voices inline, and a
library that lines up.

**Build.**

- **Quick settings:** `speakReplies`, `chimes`.
- **Each agent:** name, voice, speed and ▶, with **Change on Agents →**,
  which deep-links to that agent's card. Voice and speed keep their home
  on the Agents card.
- **Library:**
  - the filter defaults to **Downloaded**;
  - **a search box plus one compact filter** (downloaded / all, accent,
    gender) replace the row of buttons;
  - **the trash icon goes first,** in a column reserved on every row, so
    names and Test buttons line up (F);
  - "Used for Theo, Sora", from agent labels, as `PlainText`.
- **Advanced: hearing you:** `model` and `livePartials`, with one short
  paragraph on what transcription does.
- **More models only once pinned.** Whisper models are fetched by name with
  no hash today, which breaks the "every download pinned" rule.
  - In this phase: pin `tiny.en` and `base.en`, plus `small.en` and
    `medium.en` if they are added, in `models.lock`. Fetch them through
    the verified `download()` and load from a local path.
  - If that does not fit the session, extra models are deferred and the gap
    is recorded for V-02.

**Files.** `pages/VoicePage.qml`, `ui/VoiceLibraryRow.qml`; if pinning:
`models.lock`, `bench/pin-models.sh`, `install.sh` (run the box) and
`daemon/wake_listen.py` (**big**; model path).

**Settings.** None new (the `model` choices may grow).

**Tests.**

- `test_the_voice_librarys_shortcut_goes_through_one_function` stays
  green.
- If pinning: a wrong hash is refused, and check 9 covers the Whisper
  entries.

**Verify.**

- `preview.sh voices`, narrow and wide: rows aligned, measured as the x of
  the name and Test columns across rows; clicks.
- Live: Test and Use for.
- **Shell restart** needed (QML).

**Measure** (if models are added): RSS and transcription time per model
over a fixed clip set, in FINDINGS, before they are offered.

**Going back.** An older build fetches Whisper by name as before, which
works.

### R21 · Other settings, and About

| | |
|---|---|
| Covers | item 20 (the rest), item 21, item 22 (About parts) |
| Needs | R10 (command table), R17 (`keepStats`) |

**Goal.** Display & privacy becomes **Other settings**, an honest
grab-bag. About gets real install information and the full command list.

**Build: Other settings** (`pages/DisplayPage.qml` → `OtherSettingsPage.qml`):

- **On-screen readout:** `hud`, `hudLingerMs`, `hudSize`, `hudKeepReply`,
  `hudPosition`, Preview, `agentsPanel`.
- **Privacy:**
  - `yieldToRecorders`;
  - `logSpeech` with ⚠ and "the journal keeps it for weeks";
  - `keepStats` with Clear stats;
  - "The mic always closes while the screen is locked."
- **Keys:** read live from `hyprctl binds -j`, filtered to Agent Voice's
  commands and read-only, with **Open bindings file**. Changing a binding
  from here is deferred (section 7).
- **Maintenance:** Repair installation, and Remove Agent Voice
  (`DangerButton`), both moved from About.

**Build: About.**

- **This install:** version, commit, branch and install time. `install.sh`
  writes the branch into `VERSION` beside the commit, and the page explains
  `-dirty`.
- **Copy diagnostics** (`agentvoice diagnostics`, sent to `wl-copy` on
  stdin):
  - version and Omarchy version;
  - a settings summary: endpoint keys never included, URLs shown as host
    only, home paths as `~`, no folder text;
  - the last 50 **structural** journal lines. Transcript lines are left out
    even when `logSpeech` is on.
- **Check for updates:** runs only when clicked. It is a `git ls-remote` of
  the plugin folder's tracked remote, and the page names which remote it
  asked.
- **Changelog** (a new `CHANGELOG.md`, kept from the phase notes),
  **License**, **README** (local files, opened with `xdg-open`).
- **Runs here vs. goes out:**
  - wake, transcription and voices run locally;
  - each configured backend is shown as cloud or local, with its status
    (installed / has answered a turn / not found);
  - Ollama and llama.cpp are probed on `127.0.0.1:11434` and `:8080` when
    clicked, and shown as "usable as an endpoint".
- **Voice commands:** the full generated list, with the wake phrases.

**Files.** `pages/DisplayPage.qml` → `pages/OtherSettingsPage.qml`,
`pages/AboutPage.qml`, `Settings.qml` (**big**; page list), `install.sh`
(VERSION stamp; **run the box**), `bin/agentvoice`, new
`daemon/diagnostics.py`, `CHANGELOG.md`.

**Settings.** None new (keys move with the renamed page).

**Tests.**

- **Diagnostics:** seed a fake journal with a transcript line and an
  endpoint key; both are absent from the output, and home paths are
  collapsed.
- The clipboard is fed on stdin.
- The VERSION format, read tolerantly by `status`.
- The one-page test.
- The confirm test covers Remove.

**Verify.**

- `preview.sh` other and about; clicks.
- `AGENTVOICE_BOX=1` (install.sh changed).
- Live: Copy diagnostics, paste into a scratch file, and read it for
  anything personal.
- **Shell restart** needed (QML).

**Going back.** An older build has the old pages; the keys are unchanged.

### R22 · Agents speak up when background work finishes

| | |
|---|---|
| Covers | item 24 |
| Needs | R2 |

**Goal.** When background work finishes, the agent says one short line and
a notification appears, without waiting for the wake word. It never talks
over anyone and stays silent when it should.

**Build.**

- **Spike first, one real turn each:**
  - in a warm `claude -p` stream-json process, start a background command
    (`sleep 20; echo done`), let the turn end, and see whether the CLI
    produces new assistant output on its own when the command finishes;
  - the same for a background subagent.

  Codex, Gemini, Antigravity, Copilot and endpoints end their process with
  the turn, so they cannot do this, and the UI says why.
- **If Claude does produce idle output:**
  - the adapter keeps reading stdout between turns, assistant text only;
  - the daemon queues it as an **unprompted turn**;
  - it is spoken only when nothing is capturing or speaking;
  - at most one line per agent per 2 minutes, with the spoken part capped
    at 300 characters (the rest goes to the conversation view);
  - it is recorded in the chat, marked "unprompted";
  - a follow-up window opens afterwards (not while locked).
- **Silent, notification only,** while the screen is locked, while the mic
  is muted, or while Omarchy's notification silencing is on (the mode
  `omarchy-toggle-notification-silencing` sets).
- **The notification text is fixed** ("Theo finished a background task"),
  never the model's words, because `notify-send` takes its text in argv.
- **If the spike shows no idle output:** the item is deferred for Claude
  too, with the recording as the reason.

**Files.** `daemon/adapters/claude_code.py`, `daemon/wake_listen.py`
(**big**; queue and delivery), `daemon/crew.py`, `daemon/runtime.py`,
`manifest.json`, `pages/AgentsPage.qml` (**big**), `Hud.qml`.

**New settings:**

| Key | Values (default) | Unreadable | Control on |
|---|---|---|---|
| `mainSpeakWhenDone` / `voiceAgents[i].speakWhenDone` | bool (`true`) | `false` (quiet) | Agents → Agent card |

**Tests.**

- The queue never speaks while locked, capturing or speaking (frame loop).
- Silencing on → notification only.
- **No model text in the notification's argv.**
- Rate limit; unreadable → off.
- The spike's recorded idle output replays through the adapter.

**Verify.**

- **Live, by voice:** "Theo, run a 30-second background job and tell me
  when it's done" gives a spoken line plus a notification.
- Again with `agentvoice lock`: notification only, no speech.
- Again with silencing on: notification only.
- **Shell restart** needed for the new switch.

**Measure.** Time from the command finishing to the spoken line, median of
5.

**Going back.** An older build never speaks unprompted; the keys are
ignored.

### R23 · Settings search, first-run setup, the consistency audit, the release candidate

| | |
|---|---|
| Covers | item 22 (search, first run, keyboard and light theme); item 17 (audit); the Phase 17 entry gate |
| Needs | everything before it |

**Goal.** Finish the general items and leave a release candidate installed
and verified, ready for Phase 17.

**Build.**

- **Settings search:** a field at the top of the sidebar (Ctrl+F), backed
  by an index (`ui/SettingsIndex.js`) from labels and synonyms to page and
  anchor. A result jumps there and highlights the control.
- **First-run setup:** shown automatically on a fresh install (no agent
  folders yet, and the service has never started), and from About → **Run
  setup again**.
  - Steps: microphone (level, gate); wake word (engine, say it three times
    through `wake-test`); first agent (program detected and available;
    name, wake phrase); done.
  - It lives in a root-level `Setup.qml`, as the popup does, and writes
    through the overlay's existing functions. That makes it a documented
    exception in `test_settings_pages.py`, not a second page.
- **Keyboard and light theme:** a keyboard-only walk of every page in the
  real shell (the user's), and `--theme flexoki-light` shots of every page
  and tab.
- **Consistency audit** (rehearses V-13): every page's screenshots side by
  side. Any old-style row is fixed here. A static test checks that no page
  still uses the old `SettingsGroup`/`KnobRow` once every page has moved
  off them.
- **Release candidate:**
  - fast-forward `dev` to R23 and `main` to `dev`, and push to fork;
  - deploy and install that commit;
  - **check that the installed copy equals the commit** (`git archive`
    plus `diff -r`, as the status report did);
  - rerun the Phase 8 baseline (S and J) for V-11;
  - refresh `CODEBASE.md` and a project status note;
  - update `phase-17-plan.md` wherever a V-row changed;
  - tick the entry gate.

**Files.** `Settings.qml` (**big**), new `ui/SettingsSearch.qml`,
`ui/SettingsIndex.js`, new `Setup.qml`, `pages/AboutPage.qml`, docs.

**Settings.** None.

**Tests.**

- **Every manifest key and every defaults-only key has a search entry,**
  and every entry's page exists, so search cannot drift.
- The Setup exception is held to the keys it may write.

**Verify.**

- The whole `preview.sh` set: every page, narrow and wide, dark and light,
  empty state and 8-agent state.
- `AGENTVOICE_STRICT=1` and `AGENTVOICE_NO_SKIPS=1` runs.
- The installed-equals-commit check.
- **Shell restart** needed (QML).

**Going back.** This is the revision Phase 17's going-back case (V-02)
starts from.

---

## 5. Security review

These features widen what agents can do, or what reaches them. For each:
how it stays fail-closed, and what proves it. The six fail-open rules in
`CLAUDE.md` hold throughout.

### S1. Auto-detected tools (R8)

- **Off by default:** a missing per-agent value inherits `sharedTools`,
  whose default is `{}` (off). An unreadable value is off. A mutation of
  the default must turn a test red.
- **Enforced only where a recorded turn proves it.** Claude gets
  `--strict-mcp-config` with a generated list. Without strict mode,
  "off" would be a lie, because `claude -p` loads the user's own servers
  today. Codex follows its spike. A CLI switch is labelled "told, not
  enforced" except where Claude's deny rules are shown to hold.
- **Detection never runs anything:** it reads config files only. A test
  makes `subprocess` fail during a scan.
- **Secrets never reach argv:** the MCP config moves from argv JSON to a
  0600 file. It is never logged and never in diagnostics.
- **Trusted runs detected tools without asking.** Below Trusted, the hook
  asks for every MCP tool call (tested). At Trusted, Claude's matcher
  covers only Bash, edits and the browser, so each switch shows ⚠ "runs
  without asking at Trusted".
- **Treated as outside content:** an agent with any detected MCP server on
  has its notes and answers marked tainted, and it counts towards the Rule
  of Two warning like the browser does.

### S2. Agents searching chats (R16)

- **Scope is decided by the daemon,** from the caller's `SO_PEERCRED`
  identity, not from anything in the call. The default `own` uses the
  existing replay rule (owner or `shared_with`). An unreadable value is
  off; a quarantined agent is always off.
- **What comes back is data:** results are wrapped as information, with
  date and speakers, and capped.
- **The query is never stored:** no log line, no audit text (the AST check
  is extended). Nothing exists to search when `saveChats` is off.
- **Honest limit:** chat files are the user's files. A Trusted agent with a
  shell can read them directly; the scope holds through the tool. The page
  says so, as section 3.5 of merged-plan does for notes.

### S3. Skills and notes moving between agents (R9, R12, R14)

- **Only the user moves anything,** through the UI and CLI. No agent tool
  moves or combines a skill or note. Raw writes into `agents/` and
  `communal/` stay under the orders guard at every level.
- **Confirm before widening:** moving into Communal confirms, because it
  reaches every agent. Moving out of a quarantined agent, or moving a
  tainted note, confirms and shows the mark.
- **External skills are copied, never moved or edited.** A test hashes the
  source before and after.
- **Validation as for any skill:** front matter, size, symlinks refused. A
  malformed skill is listed and not delivered. Scripts inside a skill run
  under the agent's own level, never the daemon's.
- **Metadata travels:** taint, locks and history move with a note. A
  corrupt destination meta refuses the move.
- **Every move writes an audit line:** ids, names, sizes. Never text.

### S4. The crew map and quarantine (R6, R7)

- **The list in settings is the rule,** checked in `collab.py` on every
  call and read fresh each time. The page and the map only edit it.
  `list_agents` and the tool listing are filtered for clarity, but the
  daemon still refuses.
- **Unlinked, reversed or unlisted = refused.** A corrupt or unreadable
  list refuses every agent-started call. A missing list is legacy mode, and
  the page says so.
- **Quarantine is enforced in the daemon, not the picture:**
  - no outgoing calls;
  - incoming links carry ask or delegate only;
  - a delegation brings a capped brief and no chat history, with no
    `shared_with` change;
  - answers come back tainted;
  - no communal-note writes and no chat search;
  - a user pass into quarantine is refused, with the reason spoken.
- **"Ask me first" depends on the card being honest.** R6 adds the
  permission files and `agentvoice permit` to the orders guard, which
  catches the plain attempt. A determined Trusted agent with a shell can
  still answer its own card; that stays an open item for V-07 (an
  authenticated answer path).
- **Who can change the list:** an agent writing `crewLinks` in
  `shell.json` is asked at every level by the orders guard. Trusted Codex
  has no hook, so the Crew map shows "changed outside Settings at HH:MM"
  when the list changes without the page.
- **Going back to an older build is fail-open** (all-to-all, no
  quarantine). It is stated in the R6 notes and in V-02.

### S5. Other things that widen or reach out

- **Extra flags and environment (R13):** a denylist checked at launch in
  the adapter, not only on screen. Environment variables are kept in a 0600
  file, never in `shell.json` (0644). Confirm, audit, and the full command
  line shown.
- **Try it, summaries (R5, R16):** quiet side turns with the prompt on
  stdin, rate-limited, never saved to a chat. Refused while locked.
- **Background announcements (R22):** speech only, no actions;
  rate-limited; silent while locked, muted or silenced. The notification
  text is fixed, so no model text goes in argv.
- **The Agent Voice skill (R11):** it never teaches `agentvoice permit`, a
  settings write, or anything under the orders guard (tested).
- **Diagnostics and update check (R21):** structural lines only, no keys,
  paths collapsed. The update check runs only on click, and names the
  remote it asked.
- **The popup (R3):** removing the permission row removes one path to
  Trusted.
- **Stats (R17):** typed numbers and ids only (AST check), 0600, kept 90
  days, with an off switch.

### S6. Rules every phase keeps

- Spoken, typed, folder and chat text never goes in argv. Every new CLI
  verb takes text on stdin, and the existing argv test is extended to each
  new adapter path.
- Untrusted text in the UI is shown as `PlainText`. Anything printed goes
  through `safe_for_terminal`.
- Anything one agent hands another is wrapped with its source and taint.
- New settings fail to the safe value when unreadable (Appendix A).
- The audit and stats logs never hold text (AST-checked).
- The mic still closes while locked: no new feature speaks, listens or
  shows text over a lock screen.

---

## 6. Mapping table

Every feedback item and bug, and where it is delivered.

| Item | What | Phase |
|---|---|---|
| 1 | Commands inside a longer sentence | R10 |
| 2 | Remove the popup's "what Claude Code may do" | R3 |
| 3 | Popup jumps around | R3 |
| 4 | Shell restarts whenever a file is saved | R0 |
| 5 | Chats as their own sidebar page; drop the top-row button | R15 |
| 6 | Easier chats: names, details, search, agents can search, bubble layout | R15 (page, list, search box, layout), R16 (names, summaries, agent tool) |
| 7 | Overview statistics (all five) | R17 |
| 8 | Agents tab: cards, compact effort, chips, header strip, no duplicates | R4 |
| 9 | Agent details: tabs instead of a drop-down | R5 |
| 10 | Personality: trait chips, hints, templates, Try it, meters | R5 |
| 11 | Tools & skills: detection, real controls, draggable skills, Unused, Agent Voice skill | R8 (tools), R9 (skills), R11 (skill) |
| 12 | Notes in categories, movable | R12 |
| 13 | Conversation page polish (all approved parts) | R19; the rename in R15; the limit note's counter in R2; the command list from R10 |
| 14 | Agent details Advanced, plus warning + confirm everywhere | R13; confirm across the window from R1 |
| 15 | Communal: shared tools, who gets it, preview, import, history, skills gap | R4 (Tools tab home), R8 (shared tools), R9 (skills gap), R12 (notes), R14 (rest) |
| 16 | Crew map | R6 (list, enforcement, quarantine, table), R7 (drawn map) |
| 17 | One design language | R1 (pieces), each page phase, R23 (audit) |
| 18 | Listening as a pipeline | R18 |
| 19 | Voice page | R20. Partial: extra transcription models only once pinned (section 7) |
| 20 | Display & privacy → Other settings | R3 (readout settings), R15 (chat privacy), R17 (stats privacy), R21 (the rest). Partial: changing key bindings deferred (section 7) |
| 21 | About page | R21 |
| 22 | Diagnostics, updates, changelog, license; search; first run; keyboard and light theme; command caution; fix H early | R21 (About parts), R23 (search, first run, keyboard, light theme), R10 (caution), R0 (H) |
| 24 | Speak up when background work finishes | R22. Partial: Claude only, and only if the spike shows idle output; one-shot backends deferred (section 7) |

| Bug | What | Phase |
|---|---|---|
| A | Commands only fire when said alone | R10 |
| B | Popup bounces | R3 |
| C | Turns cut at 30 s with no warning | R2 (counter and note), R19 (page) |
| D | Old global permission section on the popup | R3 |
| E | Duplicate tool sections at the bottom of Agents | R4 |
| F | Voice library rows misalign | R20 |
| G | Tools & skills has no controls | R8 |
| H | Shell restarts on any write in the plugin folder | R0 |
| I | Open-mic chats lose earlier turns | R2 |
| J | Surprise "be-deep" chime, chats feel restarted | R2 |
| K | "Still listening" lingers after open mic off | R2 |

Also carried, not lettered:

- `testresults.md` #10 → R2.
- Phase 16's "a Trusted agent can answer its own card" → partly R6 (the
  orders guard); the rest stays open for V-07.

---

## 7. Deferred, on purpose

| What | Why |
|---|---|
| Changing key bindings from Other settings (part of item 20) | Bindings live in the user's Hyprland config, which Omarchy owns. The page shows them live and opens the file. |
| Extra Whisper models (part of item 19), unless R20 pins them | Today Whisper is fetched by name with no hash. Offering more unpinned downloads breaks the project's pinning rule. |
| Background announcements from Codex, Gemini, Antigravity, Copilot and endpoints (part of item 24) | Their process ends with the turn, so nothing is left to finish in the background. The UI says why. |
| In the mockups but not in the feedback: a mic device picker, per-agent "talk while working", an "ask" value for writing notes, an "either" wake decision, a per-agent "speak replies" | Not requested in the notes. Built only if the user asks (open question 12). "Either" behaves like "first only" (R18). |
| An authenticated path for answering permission cards | Bigger than this round. R6 closes the plain case; V-07 tests the rest. |
| Phase 16's other open questions (voice yes/no on cards, a stop-only window, Codex side questions over 5 s, messages lost on restart, timeouts in the audit) | Not in this feedback. They stay listed for Phase 17's findings. |
| merged-plan's own deferred list | Unchanged. |

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| 24 sessions is a long round | Daily fixes come first (R0 to R3). Every phase stands alone, ships behind its own check, and fast-forwards `dev`, so the round can stop at any phase. |
| The big shared files take repeated edits (`AgentsPage.qml` in R4, R8, R16 and R22; `wake_listen.py` in R2, R5, R10, R16, R17 and R22) | New modules and `ui/` pieces, small hooks, the `FIELD_HOMES` test, the clicks diff, and the touched-files list in each phase's notes |
| A per-agent field ends up with two homes | `FIELD_HOMES` (R4) and the overlay-function pattern |
| Strict MCP removes tools the user relies on | The R8 spike, a one-time notice, and one-click restore |
| Crew links lock collaboration out on upgrade | Legacy mode until the first link is drawn |
| Commands misfire inside sentences | The policy table, a default chosen from measured numbers, spoken confirmation, undo |
| Secrets leak through MCP configs or environment variables | 0600 files, nothing in argv, nothing in logs or diagnostics |
| Stats feel like tracking | Typed numbers only, local, 0600, kept 90 days, an off switch, Clear |
| The drawn crew map overruns its session | Time box: ship the table, carry the map |
| The R8 or R22 spikes come out against the design | The plan already says what happens in each case (honest labels, or a deferral with the recording) |
| Preview differs from the real shell | A real-shell walk at each install and in R23; the memory rule that QML needs `omarchy-restart-shell` |
| An Omarchy update changes the watcher | The dev-clone approach does not depend on the watcher's filter |
| Codex review quota runs out mid-round | Record the review as owed in the notes, as Phase 10 did. Never mark it done. |

---

## 9. Open questions for the user

1. **Dev clone location:** `~/Projects/agent-voice`? And point Theo's
   project folder there?
2. **The ten staged files on `dev`,** placed at 01:31 by something other
   than this plan: commit them in R0? And move the planning notes into the
   clone's `notes/` once bug H is fixed?
3. **Tool switches:** one home on Agent details → Tools & skills, with the
   Agents card showing a summary that links there?
4. **Strict MCP:** when it starts, begin with every detected server off
   (with a one-click "turn back on" list), or keep what each agent loads
   today?
5. **Crew links on upgrade:** legacy mode (everyone can reach everyone)
   until the first link is drawn, or start links-only with no links?
6. **Quarantine:** should it also block communal-note writes and chat
   search?
7. **Commands in sentences:** default `edges` (start or end only), or
   `clause`, under which your example works mid-sentence? The R10 numbers
   will inform it.
8. **Chat titles and summaries** by the chat's own agent: on by default? It
   costs one short side turn per chat.
9. **Note categories:** one note file per topic (recommended), or folders
   holding several notes?
10. **Shortcuts with eleven pages:** Ctrl+1..9, Ctrl+0 for the tenth,
    Ctrl+PgUp/PgDn to step, and Ctrl+F for search?
11. **Agent Voice skill:** agents tell you the phrase only, or may they run
    read-only `agentvoice` commands (e.g. `status`)?
12. **Mockup extras not in the notes** (mic picker, per-agent talk while
    working, "ask" for notes, the "either" decision): build any?
13. **Whisper pinning:** worth doing in R20 so more models can be offered?

---

## Appendix A: new settings at a glance

All three parts are required in the phase named: manifest schema and
defaults, `runtime.DEFAULTS`, and one control. Per-agent keys live in
`voiceAgents[i]`, with a `main*` top-level twin.

| Key | Phase | Values (default) | Unreadable | Home |
|---|---|---|---|---|
| `hudSize` | R3 | locked / dynamic (locked) | locked | Other settings |
| `hudKeepReply` | R3 | bool (true) | true | Other settings |
| `hudPosition` | R3 | top / bottom (top) | top | Other settings |
| `crewLinks` | R6 | list (missing = legacy) | refuse all agent-started calls | Crew map |
| `crewQuarantine` | R6 | ids ([]) | refuse all agent-started calls | Crew map |
| `sharedTools` | R8 | map ({}) | {} (all off) | Communal → Tools |
| tool entries `mcp:*`, `cli:*` (per agent) | R8 | inherit / on / off (inherit) | off | Agent details → Tools |
| `commandsInSentences` | R10 | alone / edges / clause (edges) | alone | Conversation |
| `agentvoiceSkill` | R11 | bool (true) | false | Communal → Tools |
| tool entry `agentvoiceSkill` (per agent) | R11 | inherit / on / off | inherit | Agent details → Tools |
| `mainResume` / `.resume` | R13 | bool (true) | true | Agent details → Advanced |
| `mainIdleTimeoutS` / `.idleTimeoutS` | R13 | 30–600 (90) | 90 | Agent details → Advanced |
| `mainExtraArgs` / `.extraArgs` | R13 | list ([]) | [] | Agent details → Advanced |
| `communalOff` | R14 | ids ([]) | [] (everyone gets communal) | Communal |
| `chatSummaries` | R16 | off / owner (owner) | off | Chats |
| `mainChatSearch` / `.chatSearch` | R16 | off / own / all (own) | off | Agents |
| `keepStats` | R17 | bool (true) | false | Other settings |
| `gateAdaptS` | R18 | 5–120 (30) | 30 | Listening |
| `mainSpeakWhenDone` / `.speakWhenDone` | R22 | bool (true) | false | Agents |

These are **files, not settings:**

- extra environment variables: `~/.config/agentvoice/agent-env.json`,
  0600;
- the crew map layout: `$XDG_STATE_HOME/agentvoice/crew-layout.json`;
- stats: `DATA_DIR/stats/`;
- the tool scan cache: `$RUNDIR`.

**Moved, same names:**

- `desktopTools`, `browserTools`, `omarchySkill` → Communal (R4);
- `saveChats`, `chatRetention`, `keepHistory` → Chats (R15);
- the rest of Display → Other settings (R21).

## Appendix B: per-agent fields and their one home

This is the table `FIELD_HOMES` encodes (R4); later phases add their rows.

| Field (extra agent / main) | Home | How |
|---|---|---|
| name, wake phrase, program, model, effort, voice, speed, level, project, endpoint, enabled, wake model (main) | Agents | the page's own writes, as today; the voice library goes through `assignVoice` |
| `tools` built-ins, `mcp:*`, `cli:*`, `agentvoiceSkill` | Agent details → Tools & skills (from R8; Agents until then) | `s.setAgentTool` |
| `notesWrite`, `collaboration`, `acceptsWork`, `chatSearch`, `speakWhenDone` | Agents | the page's own writes |
| `resume`, `idleTimeoutS`, `extraArgs` | Agent details → Advanced | `s.setAgentField` |
| communal opt-out | Communal | top-level `communalOff` |
| quarantine | Crew map | top-level `crewQuarantine` |

## Appendix C: the notes template

Use the template at the end of `merged-plan.md` unchanged, with these
names: `phaseRNnotes.md`, branch `phase-rN`, the dev-clone path, and
whether the phase was deployed to the plugin folder and installed.
