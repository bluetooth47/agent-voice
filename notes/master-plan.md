# Agent Voice: master plan (the redesign round, M0 to M30)

Written 2026-11-21 from two candidate plans: `next-plan-claude.md` (Opus,
phases R0 to R23) and `next-plan-codex.md` (Astra, sessions 0 to 16). Both
were read in full against `feedback-notes-2026-11-21.md`,
`phase-17-plan.md`, `project-status-2026-11-21.md` and the code at
`orders-guard` 92c71ff. Planning only: nothing in the repo was changed.

## Summary

This plan builds every item in the 2026-11-21 feedback (1 to 22, and 24) and
fixes bugs A to K, in 31 small phases, **M0 to M30** ("M" for master, so
branch and notes names clash with neither earlier plan nor the old
`phase1notes.md` to `phase16notes.md`). It keeps the Opus plan's structure:
facts checked in the code first, one compact template per phase, new
settings listed with all three parts, a spike before any design that
depends on how a CLI really behaves, and measured defaults. It takes from
the Astra plan the parts that were stronger: a pass/fail proof that bug H
is closed, an authenticated answer path for approval cards before "ask me
first" is offered, the correct reading of how the wake second check works,
"unlinked = denied" from the first day, per-chat checks before a search
match is even counted, the split of the largest phases into two sessions,
a written downgrade procedure, and a final phase that builds nothing and
only proves the installed release candidate. M0 fixes bug H first; M30
hands an installed, verified build to Phase 17. Section 4 says which model
builds each phase, and Appendix B is the same table in JSON for the runner
script.

---

## 1. Where the two plans differed, and what this plan takes

"Checked" means read in the code or on this machine on 2026-11-21 while
writing this file.

| Topic | Opus plan | Astra plan | Master plan |
|---|---|---|---|
| Bug H fix | Dev clone outside the plugin folder, deploy script, check writes nothing in the tree | Symlink trial first, else patch the host watcher; a strict proof that the original path survives | **Clone + deploy** (does not depend on the watcher), **plus Astra's proof gate**, plus a time-boxed symlink trial. Checked: `io.voxtype.settings` is already a symlinked plugin, and `inotifywait -r` does not follow symlinks. |
| How the wake second check works | "The second check only runs on what the first flagged, so *either* equals *first only*" | A spotter hit wakes at once; the second check only rescues what the spotter missed | **Astra is right.** Checked: `wake_listen.py:929–938`. "Both must agree" does not exist today and is real daemon work (M22). |
| Gate adapt speed | One look-back setting (30 s) | Rise and fall rates (0.5 and 3.0 dB/s) | Both constants exist (`noise_floor.py`). Rise and fall are the direct "how fast" controls, so they become the two sliders (M23). |
| Crew links on upgrade | Legacy mode: everyone reaches everyone until the first link | Denied from the start | **Denied from the start**, as the feedback says, with a one-click, confirmed "link everyone as before" so nobody is locked out (question 2). |
| "Ask me first" | Add the card files to the orders guard; a real fix deferred to Phase 17 | Authenticate the answer before building on it | **Both**: M7 builds the authenticated path, and adds the orders-guard rule as a second layer. |
| Commands in sentences | A mode setting, a policy table, a measured default, spoken confirmation, undo | Grammar only, no setting; wide negative tests | **Opus design, plus Astra's test contexts** (lock, dictation, partial text, the agent's own voice heard back). |
| Detected tools | Spike first; `--strict-mcp-config`; config in a 0600 file; honest "told, not enforced" labels | A daemon broker in the call path; a fingerprint so a changed definition needs approval again | **Opus design + the fingerprint + a confirm that shows source and audience.** The broker is deferred (section 9). |
| Chat titles | A quiet side turn by the chat's own agent | Local word-picking, no model | **Opus** (a local picker cannot give "a proper name"); a setting turns it off. |
| Chat search tool | Scope `own` / `all` / `off`, decided by the daemon | Each chat checked with `may_replay` before matching, counting or quoting | **Both.** |
| Agent details Advanced | One phase, a denylist for extra flags | Two sessions, an allowlist | **Two phases** (M16 read-only, M17 controls); denylist checked at launch plus confirm (question 12). |
| Background announcements | Spike on Claude's idle output; fixed notification text | Start from the daemon's own held crew reports | **Both tiers**: crew work the daemon already tracks (every backend), then Claude's own background tasks if the spike allows. |
| Final phase | Search, first run, audit and release candidate in one | Search + setup, then a release phase with no features | **Three phases**: M28, M29, M30. |
| Notes files | `phaseRNnotes.md` in the repo | `~/agentvoice-notes/redesign/` | **In the repo** (the dev clone). The runner's "done" test is a committed notes file. |
| Going back | One line per phase | A restricted downgrade procedure | **Both** (section 7.7). |
| Phase order | Daily annoyances first | Daemon proven before its page | **Both rules**, applied together. |

---

## 2. Start state

Checked 2026-11-21 about 14:00, read-only.

| What | State |
|---|---|
| Installed and running | `orders-guard` 92c71ff; 2790 tests, 14 of 14 static checks (status report) |
| Local `dev` | fa319ba = `fork/dev`: orders-guard plus one notes commit. Working tree clean. **Already done.** |
| Local `main` | e331d31 = `fork/main`, still **tracking `origin/main`**; 40 behind `dev`. To do in M0. |
| Phase runner | Service **already disabled**; unit moved to `phase-runner/agentvoice-phase-runner.service.disabled`. Script, state and logs kept. |
| Bug H | Open. Cause known (below). |
| Plugins folder | `duaneoca.agentvoice` (a real folder), `io.voxtype.settings` (a symlink into `/usr/share`), `local.vpn-hub` |

**Bug H, the cause** (Omarchy 4.5.0-3, `/usr/share/omarchy/shell`):
`services/PluginRegistry.qml:726` runs `inotifywait -m -r` over the whole
plugins folder and exempts only `.git/` and `__pycache__/`. Any other write
(a `.md` note, an editor swap file, `.pytest_cache/`) makes `shell.qml`
call `reloadPlugins()`, which unloads every panel, service and widget.
`./bin/agentvoice-check` writes `.pytest_cache/`, so the check itself
reloads the shell. This is Omarchy's code and is never edited.

**Facts the phases rest on.** From the Opus plan's section 1; rows marked ✔
were re-checked today.

| Fact | Where | Consequence |
|---|---|---|
| ✔ A sherpa hit wakes at once; the second check runs only when the spotter stayed silent; openWakeWord has no second check | `wake_listen.py:929–946` | M22 |
| ✔ Noise floor: 30 s window, rises 0.5 dB/s, falls 3.0 dB/s, all constants | `noise_floor.py:34–41` | M23 |
| ✔ The orders guard covers `shell.json` and the agents' folders | `permission_hook.py:278–283` | An agent's write to any new setting is asked about at every level (not Trusted Codex: no hook) |
| ✔ Delegated results wait for the caller's next turn | `collab.py:1051` | M27 starts here |
| The Claude adapter passes `--mcp-config` as JSON in argv, without `--strict-mcp-config` | `adapters/claude_code.py:365` | Claude agents load the user's own MCP servers today; M10 |
| The init event is read only for `session_id` | `claude_code.py:153` | Live MCP status needs it kept; M10, M16 |
| A level or project change rebuilds the main agent and drops its session | `wake_listen.py:2045` | Likely cause of bug I; M2 |
| Chime call sites: `done` 3739, `wake` 5184 and 5462 (re-arm), `heard` 5296 | `wake_listen.py` | Bug J; M2 |
| Closing open mic does not end the follow-up window | `wake_listen.py:4006` | Bug K; M2 |
| The popup writes the main agent's level | `Panel.qml:566–583` | Bug D; M3 |
| The Agents page's "ON THE DESKTOP" group writes three global keys | `pages/AgentsPage.qml:1320` | Bug E; M5 |
| Chats already have first-sentence titles, rename and a word-scoring search | `chats.py:169`, `:418`, `:478` | Item 6 extends them |
| The one-page test checks schema keys only; six defaults-only keys and every per-agent field are unchecked | `tests/test_settings_pages.py` | M1 extends it before anything moves |
| A hung turn is killed after 90 s of silence | `adapters/base.py:23` | The per-agent timeout in M17 |
| Whisper models are fetched by name, not pinned | `wake_listen.py:853` | M25 |
| `shell.json` is mode 0644 | `~/.config/omarchy/` | No secret is ever stored there |
| Ctrl+1..9 fill exactly nine pages | `Settings.qml:1367` | Eleven pages after M18; see M8 |

Big shared files (edit with small, commented hooks; put new code in new
modules): `wake_listen.py` 5699 lines, `collab.py` 2464, `agentfs.py` 2137,
`Settings.qml` 1851, `AgentsPage.qml` 1391, `AgentDetailsPage.qml` 1313,
`Panel.qml` 1236.

---

## 3. How every phase runs

House rules from `merged-plan.md` section 4 and `CLAUDE.md`, plus what M0
changes. Each phase's **Verify** assumes all of this.

1. **Work in the dev clone** (`~/Projects/agent-voice` after M0), never in
   the plugin folder. The plugin folder changes only through
   `bin/agentvoice-deploy`.
2. **Branch** `phase-mN` off `phase-m(N-1)`; `phase-m0` starts from `dev`.
   Push to `fork` only: origin's push URL is disabled in M0. After a phase
   passes, fast-forward `dev` to it and push `dev`. `main` moves in M0 and
   M30 only.
3. **Agree the spec, then measure first.** Any "faster" or "smaller" claim
   needs a number in `bench/FINDINGS.md` (§40 onward).
4. **Build to `CLAUDE.md`:**
   - a setting is three things (manifest schema + defaults,
     `runtime.DEFAULTS`, one page control), and has exactly one writing
     page;
   - no setting is removed; a moved key keeps its name and value;
     fine-tuning goes under a collapsed "Advanced";
   - text travels on stdin, never argv;
   - untrusted text is shown with `textFormat: Text.PlainText`;
   - an unreadable value falls back to the safe one;
   - the mic closes when the screen locks, and nothing new speaks, listens
     or shows text over a lock screen.
5. **Tests as `CLAUDE.md` says:** pure decisions and the real paths that use
   them; guard code gets a mutation that turns a test red; hook changes test
   silence, failure, malformed input and exceptions (all deny); adapter
   changes replay a recorded real turn.
6. **`./bin/agentvoice-check` green** before every commit and on the final
   tree. Run `AGENTVOICE_BOX=1` whenever `install.sh` changes.
7. **Codex reviews each phase twice.** Fixes land as separate commits. If
   Codex is out of quota, the notes say "review owed", never "done".
8. **Screenshots come from `bench/preview/preview.sh`**, never the live
   shell, and the real pointer never moves: narrow (520×720) and wide, dark
   and `--theme flexoki-light`, with `clicks` logging every write. Each new
   page gets a preview target.
9. **Deploy and install last.** `install.sh` ends any voice turn, so wait
   for an idle daemon. **QML changes show in the real shell only after
   `omarchy-restart-shell`**: every Verify below says whether one is
   needed. The script never restarts the shell itself (section 4.3).
10. **Live checks** use synthetic content. A check that needs the user
    (voice, the mic, a click in the real shell) is recorded as **not
    verified** and joins the next stop point's list. Never recorded as
    passed.
11. **Notes:** `phaseMNnotes.md` in the repo root, from the template at the
    end of `merged-plan.md`, with: branch, base and result commit, whether
    deployed and installed, every big shared file touched, measured
    numbers, deviations, not-verified items, open issues, and the "Going
    back" line. The phase is done when that file is committed and pushed.

---

## 4. Models and automation

### 4.1 Which model builds which phase

Three tiers, chosen by what a mistake costs, not by size.

| Tier | Model | Used for |
|---|---|---|
| A | `claude-opus-5-5` at `xhigh` | Guard and security code, changes inside the wake and turn loop of `wake_listen.py`, and phases whose design hangs on a spike |
| B | `claude-opus-5-5` at `high` | Ordinary feature phases: a page plus the daemon work behind it |
| C | `claude-sonnet-5-5` at `high` | Restyles and generators that keep the same keys and add no daemon behaviour |
| Review | Codex `gpt-6.2-astra` | Both review passes on every phase, whatever built it |

A different model reviewing than building is deliberate: Phase 8's Codex
review caught two real faults the builder missed.

| Phase | What | Model | Effort | Run |
|---|---|---|---|---|
| M0 | Housekeeping, bug H | `claude-opus-5-5` | high | **with the user** |
| M1 | Shared UI pieces, key inventory | `claude-opus-5-5` | high | script |
| M2 | Daemon bug sweep (I, J, K, C, #10) | `claude-opus-5-5` | xhigh | script |
| M3 | Popup and readout | `claude-opus-5-5` | high | script |
| M4 | Commands inside sentences | `claude-opus-5-5` | xhigh | script · **stop 1** |
| M5 | Agents page | `claude-opus-5-5` | high | script |
| M6 | Agent details: tabs, personality | `claude-opus-5-5` | high | script |
| M7 | Authenticated card answers | `claude-opus-5-5` | xhigh | script |
| M8 | Crew links and quarantine, enforced; table | `claude-opus-5-5` | xhigh | script |
| M9 | Crew map, drawn | `claude-opus-5-5` | high | script · **stop 2** |
| M10 | Tool detection, real tool controls | `claude-opus-5-5` | xhigh | script |
| M11 | Skills: scan, lanes, assign | `claude-opus-5-5` | high | script |
| M12 | Skills: move, copy, undo | `claude-opus-5-5` | high | script |
| M13 | Note categories and moves | `claude-opus-5-5` | high | script |
| M14 | The Agent Voice skill | `claude-sonnet-5-5` | high | script |
| M15 | Communal: who gets it, preview, import, history | `claude-opus-5-5` | high | script · **stop 3** |
| M16 | Agent details Advanced: what is running | `claude-opus-5-5` | high | script |
| M17 | Advanced: controls and agent management | `claude-opus-5-5` | xhigh | script |
| M18 | Chats page | `claude-opus-5-5` | high | script |
| M19 | Chat names, summaries, search filters | `claude-opus-5-5` | high | script |
| M20 | Chat search as an agent tool | `claude-opus-5-5` | xhigh | script · **stop 4** |
| M21 | Stats and the Overview page | `claude-opus-5-5` | high | script |
| M22 | Wake decision modes | `claude-opus-5-5` | xhigh | script |
| M23 | Listening as a pipeline, gate speed | `claude-opus-5-5` | high | script |
| M24 | Conversation page | `claude-sonnet-5-5` | high | script |
| M25 | Voice page | `claude-sonnet-5-5` | high | script |
| M26 | Other settings and About | `claude-opus-5-5` | high | script |
| M27 | Background announcements | `claude-opus-5-5` | xhigh | script · **stop 5** |
| M28 | Settings search, first-run setup | `claude-opus-5-5` | high | script |
| M29 | Consistency audit, keyboard, light theme | `claude-opus-5-5` | high | script |
| M30 | Release candidate, hand-off to Phase 17 | `claude-opus-5-5` | high | **with the user** |

Totals: 9 phases on Opus 5.5 at xhigh, 19 on Opus 5.5 at high, 3 on
Sonnet 5.5.

Two cautions:

- **Opus 5.5 at `xhigh` is the ceiling for this round** (the user's
  decision, 2026-11-21). Tier A differs from Tier B only in effort, so the
  safety net for Tier A is the review: both Codex passes are mandatory
  there, and the next phase does not start until their findings are
  fixed or written down as open.
- These tiers are a judgement from each phase's risk. No model has been
  measured on this repo. If a Tier C phase comes back with more than a
  handful of Codex findings, rerun the next Tier C phase on Opus.

### 4.2 What the script passes

`claude -p --model <id> --effort <level> --output-format stream-json
--verbose --permission-mode auto`, working directory the **dev clone**, one
fresh session per phase, as `phase_runner.py` did. Appendix B has the
table as JSON. The old runner had one `--model` for every phase; the new
one reads the model and effort per phase.

The phase prompt (the old one, updated):

> Read `notes/master-plan.md` and the notes of the earlier phases
> (`phaseM{prev}notes.md` and earlier), then complete phase M{n}. Do phase
> M{n} only. Follow section 3. Branch `phase-m{n}` from `phase-m{prev}`.
> You are unattended: for a decision, take the default written in section 11
> and record the question under "Open issues"; for a check that needs the
> user, record it under "Not verified". Use Codex for both reviews; if it
> fails, say "review owed". Push to `fork` only. Finish by committing
> `phaseM{n}notes.md`.

### 4.3 Stop points

The script stops after the phases marked **stop**. At each one the user is
at the desk: OK one `omarchy-restart-shell`, then work through the "Not
verified" items gathered since the last stop.

| Stop | After | The user checks |
|---|---|---|
| 1 | M4 | Chimes and chat continuity in open mic; the popup no longer bounces; commands in sentences, by voice, with the false-trigger list |
| 2 | M9 | New Agents page and personality by voice; approve and deny a card; draw a link; quarantine |
| 3 | M15 | Tool switches, skill and note drags, communal opt-out |
| 4 | M20 | Advanced tab against a real turn; Chats page; an agent finding an old chat by voice |
| 5 | M27 | Overview numbers; wake modes by voice; the 90 s turn; a background job announced |
| — | M30 | Run with the user from the start |

Unattended rule: the script may deploy and run `install.sh` at the end of a
phase once the daemon is idle, because typed live checks need the new
daemon. It never runs `omarchy-restart-shell` (question 14).

---

## 5. Phase M0: housekeeping, and bug H first

| | |
|---|---|
| Covers | item 4, bug H, item 22's "fix it early"; git and notes housekeeping |
| Needs | answers to questions 1 and 14; the user present |
| Model | `claude-opus-5-5`, run interactively |

**Goal.** No more shell reloads while working, proven with counts; `main`
current on the fork and unable to reach origin; a baseline to compare the
release against.

**Already done, only re-verify:** `dev` at orders-guard and pushed; the
runner disabled. Confirm with `git rev-parse dev fork/dev` and
`systemctl --user is-enabled agentvoice-phase-runner` (expected: not
found).

**Steps, in order.** Steps 1 to 3 write only inside `.git/`, which the
watcher ignores.

1. **Safety net.** `git bundle create
   ~/agentvoice-notes/backup-2026-11-21.bundle --all`.
2. **Before picture.** With `inotifywait -m -r` watching the plugin folder
   (logged to `~/agentvoice-notes/`), record the quickshell PID and count
   reload triggers from one check run on a scratch copy under the same
   filter. List every process that writes in the real folder during one
   ordinary session. If the daemon or the UI writes there, fixing that
   joins this phase.
3. **`main`, refs only, no checkout:**
   - verify `git merge-base --is-ancestor main dev`;
   - `git branch -f main dev`, then `git push --dry-run fork main`, then
     the real push (a fast-forward; never force);
   - `git branch -u fork/main main`;
   - `git remote set-url --push origin DISABLED-never-push-origin` and
     `git config remote.pushDefault fork`, so a push to origin fails by
     itself instead of relying on memory.
4. **Dev clone.** Clone the fork to `~/Projects/agent-voice`; add
   `upstream` with its push URL disabled. Copy this plan to the clone's
   `notes/master-plan.md`. With the user, point Theo's project folder (and
   any agent that works on Agent Voice) at the clone: a settings change,
   so the user makes or approves it.
5. **The check writes nothing in the tree.** Run pytest with
   `-p no:cacheprovider` and `PYTHONDONTWRITEBYTECODE=1`; add static check
   15, "the check left no new file in the tree".
6. **`bin/agentvoice-deploy`** (committed in the clone). It refuses a dirty
   clone or a red check; fetches the commit into the plugin folder and
   checks it out detached (one reload, on purpose); offers
   `./install.sh --yes`; and says "QML changed: run
   `omarchy-restart-shell`?" without running it.
7. **Symlink trial, 30 minutes at most.** With a disposable plugin, test
   whether a plugin folder that is a symlink to a checkout outside the
   watched tree loads normally and reloads nothing on writes. Check
   discovery, the popup, the overlay, the installer's idea of its root,
   and `omarchy plugin update` and `remove`. If everything passes, the
   Agent Voice plugin path becomes a symlink to a deploy checkout, so even
   a deploy or a stray write through the old path reloads nothing. If
   anything fails, keep step 6's plain deploy-only folder. Either way the
   packaged Omarchy files stay untouched.
8. **Record orders-guard.** It has no notes file: write what it guards, the
   Bash-text caveat, and that Trusted Codex has no hook, into
   `phaseM0notes.md`. Correct merged-plan's stale "Codex review still
   owed" line for Phase 10.
9. **Docs.** `CLAUDE.md` gets a "Where to work" section (the watcher's file
   and line, the clone, deploy); update `CODEBASE.md`, `CONTRIBUTING.md`,
   phase-17-plan's bug H box, and the assistant memory notes.
10. **Baseline.** Run S for `sora` (20 runs) and J over recent real turns
    on 92c71ff with the Phase 8 protocol (FINDINGS §33), into FINDINGS §40,
    with hardware, audio device and settings written down. M30 reruns it
    as a pair.

**Files.** `bin/agentvoice-check`, new `bin/agentvoice-deploy`, `CLAUDE.md`,
`CODEBASE.md`, `CONTRIBUTING.md`. No product code. **Settings.** None.

**Tests.** Static check 15. `agentvoice-deploy` refuses a dirty tree. Shell
syntax check covers the new script.

**Verify: the bug H gate.** All of these, with counts in the notes:

- In the clone: a full check run, 20 file edits (Markdown, Python, QML, an
  atomic editor save, a cache created and removed) and a commit give
  **0 watcher events**, the quickshell PID is unchanged, and an open
  Settings window stays open.
- One deploy gives the one expected reload (none if the symlink was
  adopted); after a deliberate `omarchy-restart-shell` a harmless QML edit
  is visible; then it is restored.
- `local.vpn-hub` and `io.voxtype.settings` still load.
- `git rev-parse dev main fork/dev fork/main` print one commit;
  `git push --dry-run origin main` fails.
- One synthetic wake and reply after the cutover.
- The way back is written down and tried: `agentvoice-deploy <older sha>`.

No feature phase starts until this gate passes.

**Risks.** Paths in memory notes, the old runner, `CODEBASE.md` and Theo's
settings go stale (the docs step lists them). A detached HEAD in the plugin
folder confuses `omarchy plugin update` (fine here; said in CONTRIBUTING).

**Going back.** Deploy an older commit. No data changes.

---

## 6. The phases

Order: daily annoyances first (M1 to M4); the shared pieces before any
page; a rule enforced in the daemon before the page that edits it; the
command table before the pages that list commands; stats before the pages
that show them.

### M1 · Shared UI pieces, and the key inventory

| | |
|---|---|
| Covers | item 17 (the pieces); item 14's "warning + confirm everywhere", applied to today's risky buttons |
| Needs | M0 |
| Model | `claude-opus-5-5` |

**Goal.** One set of building blocks in `ui/`, and a test that knows where
every setting lives before anything moves.

**Build.** Reuse `SegmentedChoice`, `SettingRow`, `ToggleRow`, `TabStrip`
and `AgentCard` where they fit. New:

| Piece | What |
|---|---|
| `Card`, `CardGrid` | Titled box; two across when wide (about 760 px), one when narrow |
| `HeaderStrip`, `Pill` | Foldable agent header: state dot, name, pills, caret |
| `CompactSelector`, `ModelPicker` | The VS Code-style mini selector; the model drop-down with effort joined to it |
| `ToggleChips` | A row of on/off chips, optional inherit state; a disabled chip says why |
| `Hint` | One plain line; detail in a tooltip |
| `DangerButton` | ⚠; the first click arms an inline "Really reset Theo? Cancel / Reset" strip that disarms after 6 s or on Escape. Cancel has the focus. The action runs only in `onConfirmed`. Never a modal. |
| `AdvancedSection` | Collapsed by default, "Advanced (N)" |
| `StageBlock` | A numbered stage with a connector line |
| `StatTile`, `MiniBars` | Overview numbers and per-hour bars |
| `DraggableCard`, `DropLane`, `UndoToast` | Drag moves, Ctrl+drag copies, Undo for 10 s, and a "Move to…" menu as the keyboard way |
| `AgentTabs`, `SearchField`, `ChatBubble` | One tab per agent (scrolls at 9); search with filter chips; left and right bubbles |

Convert today's risky buttons to `DangerButton`: trash an agent, delete a
chat, remove Agent Voice.

**Inventory.** Snapshot key → owning page → control for every setting into
the notes, and extend `test_settings_pages.py` with `FIELD_HOMES`: every
`voiceAgents[i]` field, its `main*` twin and the six defaults-only keys is
written on exactly one page, directly or through one named overlay
function.

**Files.** `ui/*`, `ui/qmldir`, `bench/preview/targets/gallery.qml`,
`pages/AgentDetailsPage.qml`, `Chats.qml`, `pages/AboutPage.qml`,
`tests/test_settings_pages.py`. **Settings.** None.

**Tests.** `ui/qmldir` in step, qmllint clean. No `put(` with a literal key
anywhere in `ui/`. Each destructive verb (`agents trash`, `chats delete`,
`--uninstall`, later `reset`, `delete --all`, `stats clear`, link delete)
appears in pages only inside an `onConfirmed` handler. `FIELD_HOMES`.

**Verify.** `preview.sh gallery`: every piece, narrow and wide, dark and
light, with long labels, keyboard only. `clicks`: each `DangerButton`
armed → cancelled and armed → confirmed. **Shell restart needed** to see
the converted buttons.

**Risks.** Drag and drop in Quickshell QML may be fiddly: the "Move to…"
menu is the guaranteed path. Actions hidden on small screens: every action
fits or scrolls into view.

**Going back.** UI only; nothing stored.

### M2 · Daemon bug sweep

| | |
|---|---|
| Covers | bugs I, J, K; bug C (the counter and a first note); `testresults.md` #10 |
| Needs | M0 |
| Model | `claude-opus-5-5`, effort xhigh (the riskiest file in the repo) |

**Goal.** Chats stop losing turns, the surprise chime is explained and
gone, open mic closes cleanly, and cut-off turns are counted.

**Build.** Reproduce each before changing it: a chat with a synthetic
marker, the level flipped Ask → Trusted and back, the same chat followed
through open-mic turns, with session, chat and turn ids traced.

- **I.** `reconcile_agent` keeps `session_id` when only the level, model or
  effort changes; only a project change drops it. **The process is still
  rebuilt**, so no old permission flag or warm privileged process
  survives: a stale privileged process is worse than a cold resume. Prove
  `--resume` works with the new flags in both directions with a recorded
  turn. If a backend must start fresh, the HUD says why.
- **J.** Add a structural log line per chime (name and reason, no text).
  Find which call plays the "be-deep" (most likely the `wake` chime on
  re-arm at 5462 after a turn dropped as "not meant for it"). A silent
  re-arm inside open mic or follow-up plays no chime. Prove no dropped
  turn resets the chat or session.
- **K.** Closing open mic ends the follow-up window at once unless a
  capture is under way, and the state shows open mic and an ordinary
  follow-up as different things.
- **#10.** With the mic muted, a typed turn still publishes
  thinking/speaking, so the HUD and the panel stay current. Never while
  locked.
- **C.** Count turns cut at `maxUtteranceMs`: the state file gains
  `limit_hits` (today's count, last time). The Conversation page gets one
  line beside the longest-turn slider; M24 restyles it.
- If I or J cannot be reproduced, record the matrix tried and leave the
  bug explicitly open for the gate. Do not guess a fix.

**Files.** `daemon/wake_listen.py` (**big shared**: `reconcile_agent`, the
chime sites, `end_open_mic`, state publishing), `daemon/runtime.py`,
`daemon/chimes.py`, `pages/ConversationPage.qml` (one line),
`tests/test_states.py`, `test_open_mic.py`, `test_chimes.py`, adapter
tests. **Settings.** None.

**Tests** (frame loop driven by the fake `sounddevice`): a level change
keeps the session and a project change drops it, each with a mutation; a
dropped open-mic turn keeps the chat id and plays no `wake` chime;
`open-mic off` publishes `listening` within one tick; a muted typed turn
publishes thinking/speaking; a forced cut increments `limit_hits`.

**Verify.** A 20-minute open-mic session before and after: unexplained
chimes counted from the new log lines; Theo recalls his previous reply
after a level flip. `agentvoice open-mic off` clears the display; record
the milliseconds. **Shell restart needed** for the one-line note. The
voice parts join stop 1.

**Risks.** Changes are limited to the four named sites, each with a
frame-loop test.

**Going back.** No stored data changes. An older build drops the session
on a level change again.

### M3 · Popup and readout

| | |
|---|---|
| Covers | items 2, 3; item 20's readout settings; bugs B, D |
| Needs | M1 |
| Model | `claude-opus-5-5` |

**Goal.** A popup that does not bounce and has no global permission
section, and a readout that can stay one size and keep the last reply in
view.

**Build.**

- **D / item 2.** Remove the "what Claude Code may do" section from
  `Panel.qml` (`setMainLevel`, `trustPending`). Keep agent chips, mic,
  stop, settings, live state and real pending permission prompts. The
  `permissions` key keeps its one home on the Agents page.
- **B / item 3.** In **locked** mode the readout area in the popup and the
  HUD has a fixed height and two fixed lines: the last reply (dim, accent
  bar) and what is being said now (bright). Nothing appears or
  disappears; long text elides as `PlainText`. **Dynamic** keeps today's
  grow and shrink, with a stable last-heard slot.
- **Preview** button: shows the HUD with sample text for 4 s through the
  state file, so it renders like a real turn.
- Both texts clear at once on lock, on an agent or chat switch, and on
  expiry. The HUD hides at once on lock whatever `hudKeepReply` says.

**Files.** `Panel.qml` (**big shared**), `Hud.qml`, `pages/DisplayPage.qml`,
`manifest.json`, `daemon/runtime.py`, `daemon/wake_listen.py` (**big**; a
preview flag and a last-reply field only), `tests/test_settings_pages.py`.

**New settings** (each row: manifest schema + defaults, `runtime.DEFAULTS`,
one control on `DisplayPage`, which becomes Other settings in M26):

| Key | Values (default) | Unreadable |
|---|---|---|
| `hudSize` | `locked` / `dynamic` (`locked`) | `locked` |
| `hudKeepReply` | bool (`true`) | `true` |
| `hudPosition` | `top` / `bottom` (`top`, today's place) | `top` |
| `hudTextSize` | `small` / `medium` / `large` (`medium`, today's) | `medium` |

**Tests.** Three places per key. The popup no longer writes `permissions`.
Lock clears both texts (state fixture).

**Verify.** `preview.sh popup` and a HUD fixture through idle → capture →
thinking → speaking → follow-up. `agentvoice lock` mid-partial: the HUD
hides with no linger. **Shell restart needed.** A real open-mic chat
watched for bounce joins stop 1.

**Measure.** Popup height across the five states from the screenshots:
today's range in px against 0 px in locked mode.

**Risks.** A fixed height clips long agent names (elide; full name in the
tooltip). A layer-shell surface must never draw over the lock screen.

**Going back.** An older build ignores the four keys and shows the
permission section again.

### M4 · The command table, and commands inside sentences

| | |
|---|---|
| Covers | item 1; bug A; item 22's caution |
| Needs | M2 |
| Model | `claude-opus-5-5`, effort xhigh (an accidental command is a release blocker) |

**Goal.** "…take notes, and keep listening, because I might pause" turns
open mic on; "stop listening to that song" does nothing; every command
that fires is said out loud once.

**Build.**

- **One table** in `speech_text.py`, built from today's phrase sets
  (nothing lost). Per command: id, phrases, a one-line effect, where it may
  appear, whether it needs the wake word, the CLI equivalent, and the
  fixed sentence spoken when it fires. `agentvoice commands --json` adds
  the agents' wake phrases and feeds M14, M24 and M26.
- **`find_command(text, mode)`** returns the command, the remaining text
  and where it was found. Matching happens before punctuation is thrown
  away; where the transcript has none, use word boundaries and clause
  cues. Starting policy, checked against the corpus:

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

- **Never fires:** with an object after the verb ("stop listening *to*…",
  "keep listening *to* me"); after a negation; in reported or quoted
  speech; when two commands compete; in dictation; on partial transcripts;
  on the agent's own voice heard back; while locked. Permission answers
  keep their own card flow.
- **When one fires inside a sentence:** its fixed sentence is spoken once
  ("Open mic on.") and shown in the HUD; the remaining text goes to the
  agent once, if any is left; "no" or "cancel that" within 3 s undoes an
  open-mic toggle.
- `alone` mode is exactly today's behaviour, and "full stop" keeps its
  immediate path.

**Files.** `daemon/speech_text.py`, `daemon/wake_listen.py` (**big**; one
hook where commands are checked), `bin/agentvoice`,
`pages/ConversationPage.qml` (the control), `manifest.json`,
`daemon/runtime.py`, `tests/test_speech_text.py`, `test_interrupt.py`,
`test_open_mic.py`, new `tests/fixtures/commands/{fire,nofire}.txt`.

**New settings:**

| Key | Values (default) | Unreadable | Control on |
|---|---|---|---|
| `commandsInSentences` | `alone` / `edges` / `clause` (`edges`; question 4) | `alone` | Conversation |

**Tests.** The corpus per mode; the remaining text; each policy row and
each never-fires case; **`alone` gives byte-identical results** on every
existing `speech_text` test; the table's phrases equal the old sets; the
spoken sentence comes from the table, never a model; one acknowledgement
per command.

**Verify.** Typed and fixture runs for every row. **Shell restart needed**
for the new control. By voice at stop 1: the example sentence in each
mode, the false-trigger list said aloud, one command at the start and one
at the end. The journal's structural line names the command and mode,
never the words.

**Measure.** `bench/commands_scan.py` runs the detector over the user's own
saved chats locally and prints counts only. The user labels a sample
"meant" or "not meant"; the false-trigger rate per mode goes in FINDINGS
and picks the default.

**Risks.** Misfires: the policy table, the spoken sentence, undo, a
conservative default. Any unintended action found is a blocker for this
phase.

**Going back.** An older build ignores the setting: commands work only
when said alone.

### M5 · Agents page

| | |
|---|---|
| Covers | item 8; bug E; the home for item 15's shared tools |
| Needs | M1 |
| Model | `claude-opus-5-5` |

**Goal.** The same settings, organised: a header strip per agent, cards two
across, effort beside the model, no duplicate sections at the bottom.

**Build.**

- **Header strip:** name, program · model, effort, voice · speed, level,
  state dot. Click to unfold.
- **Cards:** *Identity* (name and wake phrase side by side; runs on; model
  with the compact effort selector); *Voice* (voice with ▶ Test; speed);
  *Permissions* (level, project folder: liked, restyled only); *Tools*
  (today's switches as `ToggleChips`, each showing its effective value
  **and where it comes from**, so an inherited "off" is not mistaken for a
  missing control); *Collaboration & notes* (all four collaboration
  values, accepts work, notes write); *Agent* (enabled; wake model for the
  main agent); *Endpoint* (only for endpoint agents).
- **Bug E.** Remove the "ON THE DESKTOP" group. Its three global keys
  (`desktopTools`, `browserTools`, `omarchySkill`) move in the **same
  commit** to a new **Communal → Tools** tab: "For every agent. An agent's
  own switch beats this."

**Files.** `pages/AgentsPage.qml` (**big shared**; it should shrink),
`ui/AgentCard.qml`, `ui/ToolSwitches.qml`, `ui/EndpointEditor.qml`,
`pages/CommunalPage.qml`, `tests/test_settings_pages.py`.

**Settings.** None new. **Moved, same names:** `desktopTools`,
`browserTools`, `omarchySkill` → Communal.

**Tests.** `FIELD_HOMES` updated. Saving one field of one agent leaves
every other field and agent byte-identical (the data-loss guard for
`voiceAgents`).

**Verify.** `preview.sh agents` with 1 and 8 agents, main, extra, disabled
and endpoint, narrow and wide, dark and light. **`clicks` diff:** the same
actions on the old and new page write the same keys and values. The M1
inventory compared before and after. Keyboard-only walk. **Shell restart
needed.**

**Risks.** The most-used page and the most fragile key: the clicks diff,
the field test, and a `shell.json` copy taken before deploy.

**Going back.** Same keys; an older build shows the global switches on its
Agents page.

### M6 · Agent details: agent tabs, personality and instructions

| | |
|---|---|
| Covers | items 9, 10 |
| Needs | M1 |
| Model | `claude-opus-5-5` |

**Goal.** Quick switching between agents, and a personality editor that
helps instead of lecturing.

**Build.**

- **Item 9.** `AgentTabs` replace the drop-down, keyed by stable id so a
  rename keeps the selection; main first; the deep link
  `{page, agent, tab}` still works.
- **Item 10:**
  - **Trait chips:** tone (warm / dry / playful), length (brief /
    detailed), formality (casual / formal). They write one managed line at
    the top of `personality.md` (`Traits: warm, brief, casual.`) and read
    it back. Free text below is never touched; unknown hand-typed values
    are kept.
  - **One-line hints** with tooltips replace the paragraphs.
  - **Starter templates** when a box is empty, from
    `daemon/templates/{role,personality,instructions}/`.
  - **Meters** against the budgets (role 300, personality 1500,
    instructions 2000), counting what is actually sent.
  - **Try it:** `agentvoice try AGENT`. A quiet, no-tools side turn with
    the current draft speaks one sentence in the agent's voice. At most
    one per 10 s; never saved to a chat; refused with the reason when the
    service is off, the agent is busy, the backend is missing or the
    screen is locked.
- Trait parsing lives in Python (`agentvoice agents traits ID get|set`,
  JSON on stdin) so it is testable.

**Files.** `pages/AgentDetailsPage.qml` (**big shared**),
`ui/FileEditor.qml`, `daemon/agentfs.py` (**big**; traits helper),
`daemon/templates/`, `daemon/wake_listen.py` (**big**; a small `try` hook),
`bin/agentvoice`. **Settings.** None.

**Tests.** Traits round-trip with free text untouched; the budget counts
the line; a write keeps the `--base` stamp conflict check, including
against an outside writer; templates exist; `try` is refused while locked
or busy; the argv check covers the side turn.

**Verify.** `preview.sh details` and `detailshots`, empty and full tabs;
clicks. **Shell restart needed.** By voice at stop 2: change Theo's tone
chip, press Try it, hear the difference.

**Risks.** Chips rewriting typed text (only the managed line, under the
base stamp). Try it costs a short turn; the button says so.

**Going back.** An older build reads the Traits line as ordinary
personality text.

### M7 · Authenticated answers for approval cards

| | |
|---|---|
| Covers | the footing for item 16's "ask me first"; Phase 16's open question "a Trusted agent can answer its own card" |
| Needs | M2 |
| Model | `claude-opus-5-5`, effort xhigh |

**Goal.** A card answered "yes" was answered by the person at the screen.
Today the answer is a file any process running as the desktop user can
write, so "ask me first" would be a promise the daemon cannot keep.

**Build.**

- The overlay's answer goes to the daemon over its socket, bound to the
  live request id, a hash of the exact payload shown, and a one-use nonce.
- The daemon checks the caller (`SO_PEERCRED`): its process ancestry must
  include the live shell and must not include any agent process the
  daemon started. File answers are no longer accepted for these cards.
- Unanswered, expired, repeated, changed or unauthenticated = **denied**.
  The spoken announcement and the visible Cancel stay.
- **Second layer:** the orders guard asks at every level about the text
  `agentvoice permit` and about writes under `$RUNDIR/permissions/`.
- **Time box and honesty.** Same-user process checks have limits on a
  desktop without a sandbox. The notes state exactly what was proven. If
  the check cannot be made sound in the session, M8 still ships and
  "Ask me first" carries the label "advisory for Trusted agents".

**Files.** `daemon/collab.py` (**big shared**), `daemon/permission_hook.py`
(security-critical), `Settings.qml` (**big**; the card handler),
`bin/agentvoice` (client helper). **Settings.** None.

**Tests.** Real IPC with synthetic clients: an accepted UI answer; a wrong
caller; an agent's child; an expired request; a changed payload; a double
submit; a timeout; stop. The hook: silence, failure, malformed input and
an exception all deny, each with a mutation.

**Verify.** `preview.sh` of the pending and denied card. **Shell restart
needed** (the handler is QML). At stop 2 the user accepts one harmless ask
and denies another.

**Risks.** Breaking the cards that work today: every Phase 16 card test
stays green.

**Going back.** An older build uses the file path again. Before a
downgrade, turn "ask me first" links into plain denials (section 7.7).

### M8 · Crew links and quarantine, enforced, with the table

| | |
|---|---|
| Covers | item 16, build order parts 1 and 2: the list, enforcement, the table |
| Needs | M6, M7 |
| Model | `claude-opus-5-5`, effort xhigh |

**Goal.** A saved list of who may do what to whom, enforced by the daemon,
plus quarantine. The page is only an editor.

**Build.**

- **`crewLinks`:** entries `{from, to, allow: [ask|delegate|message|pass],
  askFirst}`, by stable id. Direction matters.
  - **Missing, empty, or no matching link = denied.** A call from A to B
    with ability X runs only if a link A → B lists X.
  - **Unreadable or invalid = every agent-started call refused**, with the
    reason in the HUD.
  - **Upgrade.** The page opens with "No links yet, so agents cannot reach
    each other" and one `DangerButton`: **Link everyone as before**, which
    writes the all-to-all list after a confirm (question 2).
- **Ability → tool:** ask → `ask_agent`, delegate → `delegate`, message →
  `message_agent`, pass → `pass_conversation`. `list_agents` shows only
  what the caller may reach. The daemon decides from the caller's
  `SO_PEERCRED` identity, never from the call's own text.
- **Checked four times:** at request, at approval, at dispatch from the
  queue, and at delivery. Queued work whose link or quarantine status
  changed is refused; affected running work is cancelled. Links combine
  with what exists: the target is enabled and accepts work, the caller's
  collaboration level, depth 3, cycle and rate limits, lock and stop. The
  stricter rule always wins.
- **`askFirst`** forces the card (through M7) even when the caller's level
  is `announce` or `allow`.
- **`crewQuarantine`** (a list of ids), enforced in the daemon:
  - no outgoing calls: its collaboration tools are hidden *and* refused;
  - incoming links may carry only ask or delegate;
  - a delegation into quarantine carries the brief only (capped at 1000
    characters): not added to `shared_with`, no transcript replay, no
    shared session;
  - its answers come back wrapped and marked "from a quarantined agent";
  - no communal-note writes, and no chat search (M20) (question 11);
  - at the moment an agent is quarantined, its old native sessions are
    detached and replay grants are blocked;
  - leaving quarantine grants nothing.
- **User-started passes** are not governed by links (the user is the
  approver), but a pass into quarantine is refused with the spoken reason
  "Scout is quarantined. Release it on the Crew map first."
- **Crew map page, table view.** New `pages/CrewMapPage.qml`: the From / To
  / Allows / Ask first table with add and delete (`DangerButton`); a
  quarantine switch per agent; per agent "can reach / reached by"; the
  effective result spelled out ("Theo → Sora: delegate · asks you first
  (link) · announces (Theo's level)"); and "changed outside Settings at
  HH:MM" when the list changes without the page.
- **Shortcuts.** This is the tenth page: Ctrl+1..9 for the first nine in
  sidebar order, Ctrl+0 for the tenth, Ctrl+PgUp / PgDn to step.
- Fix the stale docstrings in `collab.py` and `crew_mcp.py`.

**Files.** `daemon/collab.py` (**big shared**), `daemon/crew_mcp.py`,
`daemon/runtime.py` (`crew_links()`, `quarantined()`, read fresh on every
call), `daemon/agentfs.py` (roster label), `ui/SendSheet.qml` (denied
state), `manifest.json`, new `pages/CrewMapPage.qml`, `pages/qmldir`,
`Settings.qml` (**big**; page entry, shortcuts), a `crew` preview target.

**New settings** (controls on Crew map):

| Key | Values (default) | Unreadable |
|---|---|---|
| `crewLinks` | list (`[]` = nobody linked) | refuse every agent-started call |
| `crewQuarantine` | list of agent ids (`[]`) | refuse every agent-started call |

**Tests.** A matrix: both directions × four abilities × missing / invalid /
revoked / present × quarantine, each guard with a mutation. Also: a change
takes effect mid-session; a queued job is refused after its link is
deleted; a warm MCP client; a delegation into quarantine leaves
`shared_with` unchanged and its brief capped; `askFirst` raises the card
at `allow`; a user pass into quarantine is refused; `list_agents` is
filtered. Phase 16's tests pass once the fixture adds an all-to-all list.

**Verify.** `preview.sh crew` with 3 and 8 agents, empty and linked, narrow
and wide, dark and light; clicks write `crewLinks` exactly. Typed, live:
Theo → Sora delegate with a link runs; delete the link and it is refused
with the reason spoken; quarantine Sora and Theo's ask runs while his pass
is refused; break `crewLinks` by hand and everything is refused. **Shell
restart needed.**

**Measure.** Cost of the link check per crew call, in µs.

**Risks.** Collaboration stops on upgrade until the user links agents (the
one-click button and the banner). Level and link confused (the effective
line).

**Going back.** An older build ignores both keys: collaboration returns to
all-to-all and quarantine lifts. That is **fail-open on downgrade**: use
section 7.7 first.

### M9 · Crew map, drawn

| | |
|---|---|
| Covers | item 16, part 3: the picture, drag to link, the quarantine zone, the inspector |
| Needs | M8 |
| Model | `claude-opus-5-5` |

**Goal.** The interactive map from the mockup, editing the same list as the
table.

**Build.**

- Agent boxes are draggable. Positions are UI state in
  `$XDG_STATE_HOME/agentvoice/crew-layout.json`, not in `shell.json`, and
  the daemon never reads them. No saved layout: a circle.
- Drag from an agent's dot onto another to create a link carrying `ask`.
  Click a line for the inspector: ability chips (chips not allowed into
  quarantine are disabled and say why), **Ask me first**, **Also allow the
  reverse**, **Delete line** (`DangerButton`). Click an agent to see who it
  can reach and who can reach it.
- Arrows show direction; two-way pairs curve apart.
- Dragging into the red zone quarantines an agent after a confirm that
  shows what it loses; dragging out releases it and grants nothing.
- A Map / Table toggle. Both call **one** page function that writes
  `crewLinks`, after `agentvoice crew check` (stdin) has validated it with
  the daemon's own validator.

**Files.** `pages/CrewMapPage.qml`, new `ui/CrewEdge.qml`
(QtQuick.Shapes), `daemon/collab.py` (validator CLI), `bin/agentvoice`.
**Settings.** None new.

**Tests.** Validator cases: duplicates, self-links, unknown or renamed ids,
abilities not allowed into quarantine, an oversize list. The layout file
is never read by the daemon.

**Verify.** `preview.sh crew --shots` with synthetic drags, 1 and 8 agents;
the map, the table and the saved list compared from the clicks log, then
compared with a real daemon decision. Keyboard: create, reverse, delete.
**Shell restart needed.** At stop 2 the user draws one link and a typed
delegation proves it is enforced.

**Risks.** Curves and dragging in QML are the most time-uncertain UI work
here. **Time box:** if not solid within the session, ship the table only,
write it up, and carry the map to a follow-up. The table already edits
everything.

**Going back.** As M8.

### M10 · Tool detection, and real tool controls

| | |
|---|---|
| Covers | item 11 (tools found on the machine; a control for every tool); bug G (tools); item 15 (shared tools) |
| Needs | M6, M8 |
| Model | `claude-opus-5-5`, effort xhigh |

**Goal.** Agent Voice finds the MCP servers and CLIs on the machine and
offers a real switch for each, per agent and for everyone. Anything new is
off until switched on.

**Build.**

- **Spike first, one real turn each, recorded into FINDINGS §41 and a
  fixture.** Claude's init event with and without `--strict-mcp-config`:
  which servers load (`~/.claude.json`, `.mcp.json`, plugins, claude.ai
  connectors); which skills from `~/.claude/skills` load, and whether they
  can be left out; whether `permissions.deny` holds at every Agent Voice
  level. Codex: whether a `-c` override can switch off a server from
  `~/.codex/config.toml`. **What is enforced, and what the page calls
  enforced, follows these recordings.**
- **Detector** (new `daemon/tooldetect.py`). It **reads** config files and
  never starts anything: MCP definitions from `~/.claude.json`, the
  agent's project `.mcp.json`, Claude plugin manifests and
  `~/.codex/config.toml`; CLIs from a short curated list plus "add a CLI
  by name" (`shutil.which`). Bounded file count and size.
  `agentvoice tools scan --json` gives name, source, kind, which backends
  can use it, and a **fingerprint** of the definition. Cached in
  `$RUNDIR`; a Rescan button.
- **A changed definition is off again.** A switch stores the fingerprint it
  approved; if the server's command or arguments change, the tool goes
  off for that agent and the row says "changed since you turned it on".
- **Turning one on** asks for a confirm that shows the source file, the
  command it will run, and who gets it.
- **Delivery to Claude:** one generated MCP config in a **0600 file**
  (`$RUNDIR/prompts/`), passed as `--mcp-config <file>` plus
  `--strict-mcp-config` where the spike proves it. Today's argv JSON moves
  into that file too. Switching a tool off lets the warm process go.
  **Codex:** per the spike.
- **CLIs** are "told" (one preamble line), labelled **told, not enforced**,
  except where the spike shows Claude's deny rules hold: there a disabled
  CLI is denied and labelled **enforced** for Claude only.
- **Live status:** the adapter keeps the init event's server list, for
  this tab and M16.
- **Agent details → Tools & skills** (bug G): *Built-in* (desktop, browser,
  Omarchy commands, crew) and *Found on this machine*, one switch per
  tool, each row showing on/off, whether this backend can use it, and
  whether it asks first at this agent's level. A row that cannot work
  says why. An agent with any detected MCP server on has its notes and
  answers marked tainted, like the browser.
- **The home of per-agent tool switches moves here**, through one overlay
  function `s.setAgentTool(id, key, value)`. The Agents card shows a
  read-only summary that links here.
- **Communal → Tools:** the M5 global switches plus "on for every agent"
  per detected tool (`sharedTools`). A personal off always wins.
- **Existing behaviour.** Strict mode switches off servers Claude agents
  load today (here: `desktop-control`). No migration writes `shell.json`;
  a one-time notice lists "loaded before this version, now off", each with
  **Turn on for Theo** (question 3).

**Files.** New `daemon/tooldetect.py`; `daemon/adapters/claude_code.py`,
`codex.py`; `daemon/runtime.py`; `daemon/wake_listen.py` (**big**;
`apply_extras` hook only); `daemon/agentfs.py` (**big**; catalog);
`daemon/permission_hook.py`; `bin/agentvoice`;
`pages/AgentDetailsPage.qml` (**big**); `pages/CommunalPage.qml`;
`pages/AgentsPage.qml` (**big**; summary); `Settings.qml` (**big**;
`setAgentTool`); `manifest.json`.

**New settings:**

| Key | Values (default) | Unreadable | Control on |
|---|---|---|---|
| `sharedTools` | map tool → bool (`{}`: everything detected is off) | `{}` | Communal → Tools |
| per agent: `mcp:<name>` / `cli:<name>` in `mainTools` and `voiceAgents[i].tools` | inherit / on / off (inherit → `sharedTools` → off) | `off` | Agent details → Tools & skills |

`mainTools` and `voiceAgents` already exist in the manifest defaults and in
`runtime.DEFAULTS`; `FIELD_HOMES` records the move.

**Tests.** The detector parses synthetic configs (malformed, huge,
symlinked, with secrets) and runs no subprocess (a test makes `subprocess`
fail). New tools off; unreadable off; the inherit chain. **Claude's argv
holds no MCP JSON**, and the file is 0600. A changed fingerprint turns the
tool off. Switching off reaches a warm process, including mid-turn. An
`mcp__x__y` call asks at Ask level. Mutation: flip the default to on and a
test goes red.

**Verify.** `preview.sh tools` and `details`; clicks. Typed, live: `gh` on
for Sora only, and only Sora uses it; a detected MCP server on for Theo
appears in his init event and shows "running". **Shell restart needed.**

**Measure.** Scan time and files read. S on `sora`: no detected servers
against three enabled, strict against not strict.

**Risks.** Strict mode removing tools the user relies on (the notice and
one-click restore). claude.ai connectors behaving differently (the spike
decides). Switches that are text only on some backends (honest labels).

**Going back.** An older build has no strict mode: Claude agents load every
user MCP server again, and the per-agent entries are ignored. Section 5.7.

### M11 · Skills: scan, lanes, assign

| | |
|---|---|
| Covers | item 11 (skills found automatically, cards, the Unused area, a control per skill); bug G (skills); item 15 (which agents cannot take skills) |
| Needs | M10 |
| Model | `claude-opus-5-5` |

**Goal.** Every skill on the machine shown as a card in its owner's lane,
with a real control.

**Build.**

- **Scan** (new `daemon/skillscan.py`): agent folders, Communal,
  `~/.claude/skills`, Claude plugin skills, `~/.codex/skills` if present.
  Each card has a details drop-down: description, source path, size,
  problems, shadowed names, who gets it.
- **Lanes:** one per agent (main first), **Communal**, and **Unused**
  (skills outside Agent Voice that no agent uses).
- **Assign from Unused = import a verified copy.** Agent Voice never edits
  or deletes a skill it did not create.
- **A per-agent off switch** on every card the agent would otherwise get,
  including a communal one, so every skill has a control.
- **Communal → Skills** marks each agent whose backend cannot take skills
  and why (endpoint: none; Codex: through the index).
- **Honest note from the M10 spike.** If Claude agents also see
  `~/.claude/skills` and that cannot be switched off, the Unused lane says
  "Claude Code agents can still see these".

**Files.** New `daemon/skillscan.py`, `daemon/agentfs.py` (**big**),
`daemon/runtime.py`, `pages/AgentDetailsPage.qml` (**big**),
`pages/CommunalPage.qml`, `AgentFolders.qml`, `bin/agentvoice`,
`manifest.json`.

**New settings:**

| Key (main / extra) | Values (default) | Unreadable | Control on |
|---|---|---|---|
| `mainSkillsOff` / `voiceAgents[i].skillsOff` | list of skill names (`[]`) | every communal skill off for that agent | Agent details → Tools & skills |

**Tests.** Extend `test_tools_skills.py`: duplicates, reserved names, bad
trees, a symlink inside an import refused, a malformed skill listed and
not delivered, **the external source unchanged** (hash before and after),
an off skill absent from the plugin dir and the index, a warm process let
go when the set changes.

**Verify.** `preview.sh details` with a synthetic skill set: disabled,
Unused, native and index-only cards. Typed, live: each available backend
is asked which skills it can see. **Shell restart needed.**

**Measure.** Plugin-dir rebuild time with 20 skills. S on `sora` with three
skills if the index grew.

**Risks.** Claude agents may see `~/.claude/skills` whatever the lane says
(the M10 spike decides; the lane is labelled honestly). A rebuilt plugin
dir bringing back a switched-off skill (tested).

**Going back.** An older build ignores `skillsOff` and delivers every
assigned skill again: section 7.7. Imports are plain copies.

### M12 · Skills: move, copy, undo

| | |
|---|---|
| Covers | item 11 (draggable skill cards); item 15 (the same on Communal) |
| Needs | M11 |
| Model | `claude-opus-5-5` |

**Goal.** Drag a skill between agents and Communal; Ctrl+drag copies; Undo
works; a crash in the middle loses nothing.

**Build.**

- **One transfer helper** in the storage layer, reused for notes in M13:
  re-check source and destination under the lock, stage the whole folder,
  publish once, and on start-up finish or roll back anything interrupted
  before either side is shown to an adapter.
- Drag moves, Ctrl+drag copies, the "Move to…" menu does both from the
  keyboard. Undo is tied to the exact revision and refuses if either side
  changed since.
- Into Communal: confirm, "Every agent will get this skill". From a
  quarantined agent: confirm with a warning. A name clash is refused with
  the reason.
- **CLI:** `agentvoice agents skills move|copy FROM NAME TO`,
  `skills import PATH TO`, `skills undo OP`. A move drops access at the
  source and rebuilds both plugin caches.
- **Only the user moves a skill.** No agent tool does it.

**Files.** `daemon/agentfs.py` (**big**) and a new `daemon/transfer.py`,
`bin/agentvoice`, `AgentFolders.qml`, `pages/AgentDetailsPage.qml`
(**big**), `pages/CommunalPage.qml`. **Settings.** None.

**Tests.** Move, copy and undo round-trips, each in `.history`; a conflict;
same-name shadowing; a link swapped in mid-move; an oversize folder; a
full disk; an interrupted move recovered; two moves at once serialised; a
stale Undo refused; the bounds kept (64 files, 2 MiB, 20,000-character
SKILL.md); audit lines hold names and sizes only.

**Verify.** `preview.sh details` with drags through `TestEvent`. Typed,
live: move a skill from Theo to Communal and Sora can use it; undo and she
cannot. Keyboard move, copy and undo. **Shell restart needed.**

**Risks.** A half-finished move leaving a skill in two places or none
(staged publish, recovery at start-up). Sharing by accident (the Communal
confirm).

**Going back.** Skills sit where they were moved. Finish any pending
transfer before a downgrade.

### M13 · Note categories, and moving notes

| | |
|---|---|
| Covers | item 12; item 15 (Communal notes get the same) |
| Needs | M12 |
| Model | `claude-opus-5-5` |

**Goal.** Notes organised by topic and moved between agents and Communal
like skills.

**Build.**

- **A category is one note file per topic**, which is what a note file
  already is: storage does not change and nothing is rewritten in bulk.
  - The crew tools steer agents toward it: `notes_list` returns each topic
    with its first line, and the descriptions say "one note per topic;
    append rather than start a new note".
  - The Notes tab shows topic cards in owner lanes, with a friendly topic
    label, drag to move, Ctrl+drag to copy, Undo (the M12 helper).
  - **Combine** merges several small notes into one topic note: a user
    action, each source's history kept.
- **A move carries** the file, its history and its meta entry: revision,
  author, taint and lock travel with it. Each move writes an audit line.
- **Confirm before widening:** into Communal; out of a quarantined agent;
  a tainted note. The confirm says that **past versions move too**.
- **Agents cannot move or combine notes.**

**Files.** `daemon/notes.py`, `daemon/crew_mcp.py` (descriptions only),
`daemon/agentfs.py` (**big**; CLI), `ui/NotesPanel.qml` (cards and lanes),
`pages/AgentDetailsPage.qml` (**big**), `pages/CommunalPage.qml`.
**Settings.** None.

**Tests.** A move keeps rev, history, meta, taint and lock; 8 writers
during a move lose nothing; a clash is refused; no deadlock under
concurrent cross-moves (locks always taken in one order); a corrupt
destination meta refuses the move; `notesWrite=deny` and note locks still
hold; Combine keeps every history; crew tools stay scoped to `mine` and
`communal`; audit lines hold no content.

**Verify.** `preview.sh notes` with synthetic notes and drags. Typed, live:
Theo appends to an existing topic note instead of starting a new one; move
it to Communal and Sora reads it; restore an old version. **Shell restart
needed.**

**Risks.** A move showing a note's past versions to a wider audience (the
confirm says so).

**Going back.** An older build reads notes wherever they now are; the meta
format is unchanged.

### M14 · The Agent Voice skill

| | |
|---|---|
| Covers | item 11 ("an Agent Voice skill"); `voice-commands-notes.md` |
| Needs | M4, M11 |
| Model | `claude-sonnet-5-5` (a generator modelled on `omarchy_skill.py`) |

**Goal.** Agents look up how Agent Voice works instead of reading its
source.

**Build.**

- **New `daemon/agentvoice_skill.py`** writes `skills/agentvoice/SKILL.md`,
  generated from the same definitions the matcher uses: what Agent Voice
  is; the command table (phrases, effect, where each may appear); the
  agents' wake phrases; the CLI commands that are fine to suggest; each
  settings key with its page and meaning (from the manifest and the page
  map); files (from `paths.py`); and what an agent cannot do itself (a
  terminal handoff started inside a turn ends that turn, so the agent
  gives the user the phrase).
- **It never teaches** `agentvoice permit`, a settings write, or anything
  the orders guard covers. Looking something up starts no action
  (question 7).
- **Delivery:** in each Claude agent's plugin dir beside `omarchy`,
  independent of the Omarchy switch; one index line for other CLIs;
  nothing for endpoints. `agentvoice` becomes a reserved skill name.
- **Rebuilt when stale:** a hash of the generator, `speech_text.py`,
  `manifest.json` and the wake phrases.

**Files.** New `daemon/agentvoice_skill.py`, `daemon/agentfs.py` (**big**;
plugin dir), `pages/CommunalPage.qml`, `pages/AgentDetailsPage.qml`
(**big**), `manifest.json`, `daemon/runtime.py`, `README.md`.

**New settings:**

| Key | Values (default) | Unreadable | Control on |
|---|---|---|---|
| `agentvoiceSkill` | bool (`true`) | `false` | Communal → Tools |
| per agent `agentvoiceSkill` in `mainTools` / `voiceAgents[i].tools` | inherit / on / off | inherit | Agent details → Tools & skills |

**Tests.** The skill's phrases equal the table; **no forbidden command
appears** (`permit`, `bar set`); a phrase change marks it stale; the
reserved name is refused for a user skill; size within 20,000 characters;
index line ≤ 160; only agents with it on receive it.

**Verify.** Typed: "how do I keep the mic open?" answered from the skill by
Theo and from the index by Hazel (Codex). **Shell restart needed** for the
two switches.

**Measure.** S on `sora`; the preamble size delta.

**Risks.** Advice going stale, or reading like permission (rebuilt from the
table; it says what an agent cannot do itself).

**Going back.** An older build does not generate it; plugin dirs rebuild
without it.

### M15 · Communal: who gets it, preview, import, history

| | |
|---|---|
| Covers | item 15 (per-agent opt-out, a combined preview, import, history and undo) |
| Needs | M10, M11, M13 |
| Model | `claude-opus-5-5` |

**Goal.** Choose which agents take communal content, see what each one ends
up with, import, and undo.

**Build.**

- **Who gets communal:** one switch per agent. An opted-out agent is not
  told the rules or defaults and gets no communal skills. Communal notes
  stay reachable through the notes tool, because they are data asked for,
  not instructions; the page says so.
  - Opting out lets that agent's warm process go. A session that already
    saw the rules still has them, so the page offers **Start fresh**:
    text already delivered cannot be recalled.
- **Preview:** pick an agent; see its whole prompt piece by piece with
  sources and precedence, and the total characters, built by the real
  prompt builder.
- **Import:** `agentvoice agents import communal DIR` (rules, defaults,
  skills). First a dry-run list with the exact files, a diff, the agents
  affected and name clashes; then a confirm. One all-or-nothing commit
  through the M12 helper, with Undo. Symlinks and oversize files refused.
- **History and Undo** beside the Rules and Defaults editors: versions are
  already saved (Phase 9); this adds the list (view, diff, restore).
- Communal → Chats stays, as a filtered view.

**Files.** `pages/CommunalPage.qml`, `ui/FileEditor.qml`,
`ui/PromptPreview.qml`, `daemon/agentfs.py` (**big**; `parts_from` and
`plugin_dir` honour the opt-out; import), `daemon/runtime.py`,
`manifest.json`.

**New settings:**

| Key | Values (default) | Unreadable | Control on |
|---|---|---|---|
| `communalOff` | list of agent ids (`[]`) | `[]`: every agent gets communal (rules may carry safety text, so "told" is the safe side) | Communal |

**Tests.** An opted-out agent's preamble has no rules or defaults and the
empty-folder byte-identity (A11-1) still holds; its plugin dir has no
communal skills; unreadable → everyone gets communal; the preview equals
what each adapter is actually sent; an import dry run changes nothing; an
interrupted import leaves both sides whole; history and undo round-trip.

**Verify.** `preview.sh shared`; clicks. Typed, live: opt Sora out and she
no longer follows a communal rule; opt her back in. Round-trip a synthetic
export. **Shell restart needed.**

**Measure.** S on `sora`: the change can only shrink the prompt; confirmed
anyway.

**Risks.** An import changing every agent's instructions at once (dry run,
diff, one commit, Undo). A warm session keeping old rules (Start fresh).

**Going back.** An older build ignores `communalOff`, so opted-out agents
get communal again: section 7.7.

### M16 · Agent details Advanced: what is running

| | |
|---|---|
| Covers | item 14, the read-only half |
| Needs | M10 (live server status) |
| Model | `claude-opus-5-5` |

**Goal.** One tab that shows in depth how this agent runs, what it is
connected to, and what it did recently. Nothing here changes anything.

**Build. Shown:**

- The **full assembled prompt** in send order, each part labelled with its
  source (`PromptPreview`, extended to the skills index and roster). Full
  content only on a deliberate reveal.
- The **exact command line**, from `agentvoice agents runinfo ID --json`,
  built by the same function the adapter uses: prompt-file paths, never
  text, secrets redacted.
- **MCP servers and tools** with live status (running / failed / off) from
  M10's saved init event. What a backend *can* do is kept apart from what
  was *seen*.
- **Session:** id, whether it resumes, turns kept. **Timeouts** and
  **working directory**, with a link to where each is changed.
- **Recent log lines** for this agent: structural only, from a small
  per-agent ring in the daemon, never speech even with `logSpeech` on.
  Plus **Open full log**.
- **Recent permission decisions:** a new audit kind `permission` with
  time, agent, tool name, decision and level. No arguments, no paths.

**Files.** `pages/AgentDetailsPage.qml` (**big**), `ui/PromptPreview.qml`,
`daemon/adapters/base.py`, `claude_code.py`, `codex.py` (runinfo),
`daemon/audit.py` (new kind), **`daemon/permission_hook.py`
(security-critical:** it records each decision; a failed record must never
change the decision), `daemon/wake_listen.py` (**big**; the log ring),
`bin/agentvoice`. **Settings.** None.

**Tests.** runinfo equals the adapter's argv, with no user text; **the hook
decides the same when its audit write raises** (mutation: make it raise,
and silence still denies); permission audit lines hold no arguments (the
AST check); two agents on one backend are told apart; a synthetic secret
in a launch line is redacted.

**Verify.** `preview.sh details` with `{"tab":"advanced"}`, native,
index-only and endpoint variants. Typed, live: sample
`/proc/<pid>/cmdline` during a turn; it equals the shown line and holds no
user text. **Shell restart needed.**

**Risks.** A launch or error line can carry a token: an allowlist of
fields, `safe_for_terminal`, `PlainText`.

**Going back.** An older build ignores the new audit kind.

### M17 · Advanced: controls and agent management

| | |
|---|---|
| Covers | item 14, the editing half, with warning + confirm on everything risky |
| Needs | M16 |
| Model | `claude-opus-5-5`, effort xhigh (launch flags are a security boundary) |

**Goal.** Edit how an agent is launched, and manage the agent, without
opening a way around its permission level.

**Build.**

- **Resume** on/off and the **hung-turn limit**, per agent.
- **Extra flags:** checked **in the adapter at launch**, not only on
  screen, against a per-program denylist: anything touching permissions,
  settings, hooks, MCP, plugins, tool allow/deny lists, extra dirs, system
  prompts, session flags, the sandbox or the stream format
  (`--permission-mode`, `--dangerously-skip-permissions`, `--settings`,
  `--setting-sources`, `--mcp-config`, `--strict-mcp-config`,
  `--plugin-dir`, `--allowedTools`, `--add-dir`,
  `--append-system-prompt*`, `--resume`, `--output-format`; Codex's `-c`,
  `--sandbox`, `--full-auto` and bypass flags), including `--flag=value`
  and short forms. These are refused **even after a confirm**, with the
  reason shown. Accepted flags show ⚠ and need a confirm (question 12).
- **Extra environment variables:** stored in
  `~/.config/agentvoice/agent-env.json` (**0600**), never in `shell.json`;
  written through `agentvoice agents env ID set` (stdin); names checked
  against a denylist (`PATH`, `LD_*`, `PYTHON*`, `HOME`, `XDG_*`,
  `*_PROXY`, `*_BASE_URL`, `NODE_OPTIONS`, `CLAUDE_CONFIG_DIR`,
  `CODEX_HOME`); never logged, never in diagnostics. The page says flags
  are visible to other local users through `/proc`, so secrets belong in
  environment variables.
- **Start fresh** (`DangerButton`): ends only this agent's session.
- **Export** (exists). **Duplicate:** a new stable id, with tool and crew
  grants at their safe defaults, and **no** secrets, sessions or replay
  rights copied. **Reset to defaults** (`DangerButton`): says exactly what
  is reset and trashes the agent first, so Restore undoes it.

**Files.** `pages/AgentDetailsPage.qml` (**big**), `AgentFolders.qml`,
`daemon/adapters/base.py`, `claude_code.py`, `codex.py`,
`daemon/wake_listen.py` (**big**; start fresh), `daemon/agentfs.py`
(**big**; duplicate, reset), `Settings.qml` (**big**; `setAgentField`),
`manifest.json`, `daemon/runtime.py`.

**New settings** (per agent; controls on Agent details → Advanced):

| Key (main / extra) | Values (default) | Unreadable |
|---|---|---|
| `mainResume` / `voiceAgents[i].resume` | bool (`true`) | `true` (today) |
| `mainIdleTimeoutS` / `.idleTimeoutS` | 30–600 (`90`) | `90` |
| `mainExtraArgs` / `.extraArgs` | list of strings (`[]`) | `[]` (nothing passed) |

**Tests.** **Denied flags are refused at launch** in every form; the env
denylist; the env file is 0600 and never printed; duplicate copies no
grants, sessions or secrets; reset round-trips with Restore; resume off
means no `--resume`; the timeout reaches the Watchdog; a cold and a warm
launch with a safe flag; three places per key.

**Verify.** `preview.sh details`, each warning: cancel, then confirm once.
Typed, live: add a harmless flag and see it in `/proc`; add a denied flag
and see it refused; reset a scratch agent, then Restore. **Shell restart
needed.**

**Risks.** Extra flags breaking turns (the last error shown, one-click
clear).

**Going back.** An older build ignores the new keys and the env file:
agents run without extras and always resume. Invalidate any session that
should have stayed fresh.

### M18 · Chats page

| | |
|---|---|
| Covers | item 5; item 6 (cleaner list, more per chat, search box, messaging layout); item 13's rename; item 20 (chat privacy moves here) |
| Needs | M1 |
| Model | `claude-opus-5-5` |

**Goal.** Chats get their own sidebar page with an easy list and a
messaging-app view, and the confusing top-row button goes.

**Build.**

- **New `pages/ChatsPage.qml`** in the sidebar as **Chats**. The list and
  viewer in `Chats.qml` become one shared component, used here, on Agent
  details → Chats (filtered to that agent) and on Communal → Chats.
- **Remove the top-row "Conversations" button.** The settings page stays
  "Conversation", so the names no longer collide.
- **Settings card at the top:** `saveChats`, `chatRetention` and
  `keepHistory`, moved from Display; where chats are stored and their
  measured size; **Delete all saved chats** (`DangerButton`; the confirm
  states the count and scope). An in-flight save must not recreate
  deleted history.
- **List:** title, agent(s), date, turn count and summary (the last-line
  preview until M19), agent filter chips, a search box (`agentvoice chats
  search`, query on stdin, today's scorer).
- **Viewer:** the user on the right, the agent on the left, coloured from
  the theme, each agent's own accent, the speaker always named; questions
  between agents folded to one line; tool lines dim. Existing actions
  kept: continue, new, share, send, rename, pin, export, delete.
- **Eleventh page:** About is reached by click, Ctrl+PgDn and, from M28,
  search.

**Files.** New `pages/ChatsPage.qml`, `Chats.qml`, `ui/ChatBubble.qml`,
`ui/ExchangeItem.qml`, `Settings.qml` (**big**; button removed, page
added), `pages/DisplayPage.qml` (keys out), `pages/AgentDetailsPage.qml`
(**big**), `pages/CommunalPage.qml`, `daemon/chats.py` (`delete --all`,
`stats`, `search`), `bin/agentvoice`.

**Settings.** None new. **Moved, same names:** `saveChats`,
`chatRetention`, `keepHistory` → Chats.

**Tests.** `delete --all` removes only files in the chats folder (never a
link target) and reports the count; the query arrives on stdin; the
one-page test; the confirm test covers `delete --all`.

**Verify.** A new `preview.sh chats` target with a synthetic set: empty,
long titles, a renamed agent, unicode, and text that looks like HTML (to
prove `PlainText`); narrow and wide, dark and light; clicks. Keyboard:
search → open → continue, and a cancelled delete. **Shell restart
needed.**

**Risks.** A stale route or a second writer for the three moved keys (the
one-page test; every old link checked).

**Going back.** An older build shows the chat privacy settings on Display
again (same keys). A confirmed deletion stays deleted.

### M19 · Chat names, summaries and search filters

| | |
|---|---|
| Covers | item 6 (proper names, more information, search) |
| Needs | M18 |
| Model | `claude-opus-5-5` |

**Goal.** Each chat gets a real name and a one-line summary, and search
takes filters.

**Build.**

- The instant title stays (`title_from`). After a chat has been idle for
  2 minutes, a quiet side turn on **the chat's own agent** (the provider
  that already has the conversation) writes a title (≤ 60 characters) and
  a summary (≤ 160). Prompt on stdin; output cleaned of control
  characters and capped.
- Stored as `auto_title` and `summary` in the chat file. **A rename by the
  user always wins.** At most one per chat per change and ten an hour.
  Off when `saveChats` is off.
- Titles and summaries are private chat content: 0600, and removed with
  the chat on delete, expiry and bulk purge.
- **More per chat:** participants, duration and turn count.
- **Search:** filters `agent:`, `before:`, `after:`; ranking extends
  today's scorer. An index file is added only if the measurement says so;
  if one is added it is rebuildable, and a failed index write never makes
  a chat unreadable.

**Files.** `daemon/chats.py`, `daemon/wake_listen.py` (**big**; the idle
summariser hook on `side_adapter`), `daemon/runtime.py`, `manifest.json`,
`pages/ChatsPage.qml`, `bin/agentvoice`, `tests/test_chats.py`.

**New settings:**

| Key | Values (default) | Unreadable | Control on |
|---|---|---|---|
| `chatSummaries` | `off` / `owner` (`owner`; question 5) | `off` | Chats |

**Tests.** A summary never overwrites a rename; the side turn's text
travels on stdin; cleaning and caps; the rate limit; nothing written with
saving off; derived text gone after a delete; legacy, renamed,
multi-speaker and corrupt chat fixtures.

**Verify.** Synthetic chats with identical openings and different subjects
get different titles. Typed, live: titles and summaries appear after the
idle time. **Shell restart needed** for the control.

**Measure.** Search latency over 1000 synthetic chats (median and p95).
The summary side turn's cost per backend, in seconds.

**Risks.** Summaries costing turns the user did not expect (the rate limit,
the off switch, the measured cost shown beside the control). Private text
outliving its chat (removed together).

**Going back.** An older build ignores `auto_title` and `summary` and
shows the first-sentence title.

### M20 · Chat search as an agent tool

| | |
|---|---|
| Covers | item 6 ("agents should be able to use the same search") |
| Needs | M19, M8 (quarantine) |
| Model | `claude-opus-5-5`, effort xhigh |

**Goal.** Agents can search old chats, and only the chats they are allowed
to see.

**Build.**

- **Tools:** `chats_search(query, limit)` and `chats_read(id, from, to)`
  in `crew_mcp.py`, **answered by the daemon over `calls.sock`**, which
  identifies the caller by `SO_PEERCRED` and ties it to the running turn.
- **Scope per agent (`chatSearch`):** `own` (chats the agent owns or is in
  `shared_with`, the existing replay rule), `all` (every saved chat; a
  confirm to turn on), or `off`. A quarantined agent is always `off`.
- **Each chat is checked with `may_replay` before it is matched, counted,
  ranked or quoted**, and again before a hit is opened. Being a
  participant, having an old session, a crew link or `may_continue` is not
  enough. A chat the caller may not see adds nothing to any count.
- Results are capped (10 hits; 8000 characters per read) and wrapped as
  information with date and speakers.
- **The query is never logged or audited:** the audit records the kind,
  the caller, the hit count and sizes. With `saveChats` off the tool says
  there are no saved chats.

**Files.** `daemon/chats.py`, `daemon/collab.py` (**big**; a new call kind)
or a new handler module, `daemon/crew_mcp.py`, `daemon/permission_hook.py`
(`chats_*` count as reads), `daemon/runtime.py`, `manifest.json`,
`pages/AgentsPage.qml` (**big**), `tests/test_chat_grant.py`.

**New settings:**

| Key (main / extra) | Values (default) | Unreadable | Control on |
|---|---|---|---|
| `mainChatSearch` / `voiceAgents[i].chatSearch` | `off` / `own` / `all` (`own`; question 6) | `off` | Agents → Collaboration, notes & chats |

**Tests.** The same rare word in a permitted, a private, an unshared and
an expired chat: titles, counts, snippets and ids all respect the scope.
`own`, `all`, `off`, quarantined and unreadable each behave as written; a
forged caller id is refused; a grant revoked mid-query; caps and wrapping;
**the query appears in no log or audit line** (the AST check extended);
each guard with a mutation.

**Verify.** Typed, live, as two agents: Theo finds his chat; Sora with
`own` cannot find Theo's, and gets no hint that it exists. Inspect process
arguments and both output streams with a synthetic canary. By voice at
stop 4: "Theo, find our chat about the wake word last week". **Shell
restart needed** for the control.

**Risks.** Chat files are the user's files: a Trusted agent with a shell
can read them directly. The scope holds through the tool, and the page
says so.

**Going back.** An older build has no chat tools. Stop MCP children that
still offer them before a downgrade.

### M21 · Stats, and the Overview page

| | |
|---|---|
| Covers | item 7 (every listed statistic); item 20 (stats privacy) |
| Needs | M2 |
| Model | `claude-opus-5-5` |

**Goal.** An Overview with real numbers that match the journal, and no
transcript in them.

**Build.**

- **New `daemon/stats.py`.** Per-day counters in
  `DATA_DIR/stats/YYYY-MM-DD.json` (0600): turns per agent; wakes accepted
  and rejected by stage; timings as fixed-bucket histograms (for median
  and p95); limit hits (M2). Written at the end of a turn, atomically,
  under a lock. **Never text.** Kept 90 days.
  `agentvoice stats [--days N] --json`.
- **Definitions, fixed here so the numbers mean one thing:**
  - wake-to-reply = accepted wake → first audible reply;
  - transcription time = transcription start → final text;
  - a turn is counted once, by an opaque turn id; typed and follow-up
    turns are counted separately and left out of the wake average;
  - "false wakes" = bursts the second check rejected, labelled as exactly
    that;
  - every average is shown with its sample count, and "no data" when
    there is none.
- **Live in the state file:** service start time, the daemon's memory, and
  its agents' memory shown separately.
- **Overview page:** tiles (turns today per agent with a week toggle;
  median wake to first word and transcription time; wakes against
  rejections; uptime and memory); the Agents card with state and **last
  chat →** (only for a real saved chat); the Microphone card (gain, level,
  mute: liked, restyled only); per-hour wake bars.

**Files.** New `daemon/stats.py`, `daemon/wake_listen.py` (**big**; calls
where the structural timing lines are already printed),
`daemon/runtime.py`, `daemon/paths.py`, `bin/agentvoice`,
`pages/OverviewPage.qml`, `pages/DisplayPage.qml`, `manifest.json`.

**New settings:**

| Key | Values (default) | Unreadable | Control on |
|---|---|---|---|
| `keepStats` | bool (`true`) | `false` (collect nothing) | Display → Privacy (Other settings in M26), with **Clear stats** (`DangerButton`) |

**Tests.** The stats AST check: only typed ids and numbers, as for the
audit log. A driven turn gives stats **equal to its structural log lines**
(rehearses V-21). `keepStats` off writes nothing. A corrupt day file is
skipped and replaced, never failing a turn. Two agents at once, a
duplicate event, midnight, a daemon restart, pruning.

**Verify.** `preview.sh` overview with a synthetic stats file: idle, no
history, several agents, a full week. **Shell restart needed.** At stop 5:
ten real voice turns, then the Overview compared with the journal.

**Measure.** Cost of the stats write per turn (µs); file size per day at
200 turns; the memory figure against `ps`.

**Risks.** Unmatched ids giving plausible but wrong averages (sample counts,
"no data"). Stats feeling like tracking (numbers only, local, an off
switch, Clear).

**Going back.** An older build ignores the stats files and the key.

### M22 · Wake decisions that match the controls

| | |
|---|---|
| Covers | item 18 ("which stages have to agree before a wake counts") |
| Needs | M21 (the counts) |
| Model | `claude-opus-5-5`, effort xhigh (the wake path) |

**Goal.** The three choices the Listening page will offer are all real.

**What happens today** (checked in `feed_wake`): with sherpa, a spotter
hit wakes at once. Only when the spotter stays silent on a short burst does
the second check run, and then Vosk and Whisper must both hear the same
name (`crossCheckEngines` picks who votes). So "second check on" means
**either stage can wake**, and nothing today requires **both** to agree.
openWakeWord and plain Vosk have no second check.

**Build.**

- Three decisions, shown as one selector:

| Choice | `wakeCrossCheck` | `wakeBothAgree` | Behaviour |
|---|---|---|---|
| First only | off | off | Today, second check off |
| Either stage | on | off | Today, second check on (the default path, unchanged) |
| Both must agree | on | on | **New.** A spotter hit is held until the second check hears the same name for the same agent, inside a set window |

- If "both" is chosen and the second stage cannot run (model missing,
  engine has no second check), the page refuses the choice with the
  reason, or the daemon holds wakes closed and says so. It never falls
  back to waking on one stage silently.
- "Full stop" keeps its own immediate path in every mode.
- Stats gain "confirmed by the second check" and "held, then dropped".

**Files.** `daemon/crosscheck.py`, `daemon/wake_listen.py` (**big**;
`feed_wake` and where a wake is applied), `daemon/runtime.py`,
`manifest.json`, `pages/ListeningPage.qml` (the selector; M23 restyles the
page), `tests/test_crosscheck.py`, `test_sherpa_wake.py`,
`test_wake_reconcile.py`.

**New settings:**

| Key | Values (default) | Unreadable | Control on |
|---|---|---|---|
| `wakeBothAgree` | bool (`false`, today's behaviour) | `false` | Listening → Decision |

**Tests.** First hit and second miss; first miss rescued; the two stages
naming different agents; a vote outside the window; an unavailable second
stage; **with `wakeBothAgree` off the existing wake tests pass
unchanged**; "full stop" in every mode.

**Verify.** `preview.sh` of the selector, including the refused state.
`agentvoice monitor` shows the mode. **Shell restart needed.** By voice at
stop 5: names and distractors in each mode.

**Measure.** On one fixed clip set, per mode: true accepts, distractor
accepts, rejects, **added delay before the wake**, CPU. "Both" is offered
with its measured delay written beside it.

**Risks.** A wake that got harder to trigger feels like a broken mic: the
default does not change, and the HUD shows "heard, not confirmed".

**Going back.** An older build ignores `wakeBothAgree` and wakes on one
stage again. Say so before handing the mic back.

### M23 · Listening as a pipeline, and gate speed

| | |
|---|---|
| Covers | item 18 (the layout, the gate sliders, "Your voice" folded in) |
| Needs | M21, M22 |
| Model | `claude-opus-5-5` |

**Goal.** One top-to-bottom view of how a wake word passes through, each
stage holding only its own settings.

**Build.** Every Listening key keeps its single home here. `phrase` and
`owwModel` stay on the Agents card, shown with a link.

1. **Microphone.** Level meter with the gate marked; gate fixed / dynamic
   (`adaptiveGate`); **adapts slow / normal / fast** (new, a preset over
   the two rates). Advanced: the fixed level (`micThresholdDb`), the
   margin (`gateMarginDb`), and the exact rise and fall rates.
2. **First listener.** Engine (`engine`) and its sensitivity
   (`owwThresholdPct` or `sherpaThresholdPct`). **Engine-specific blocks
   appear only for the chosen engine:** the old "Your voice"
   (`useVerifier`, record and train) inside openWakeWord's block;
   `shortNameBoostPct` and `wakeAlsoSounds` inside sherpa's.
3. **Second check.** Engines (`crossCheckEngines`). Advanced: window
   (`crossCheckMinMs`, `crossCheckMaxMs`), trailing words, the Whisper
   hint. Greyed with the reason for an engine that has none.
4. **Decision.** The M22 selector; confidence (`wakeConfidencePct`);
   "Today: 31 wakes · 4 rejected by the second check", from stats.

**Daemon.** The rise and fall rates become plain attributes on the noise
floor, set after the spec check and changed in place (`CLAUDE.md`: a
number never rebuilds a model). The gate still never learns from speech or
from its own chime.

**Files.** `pages/ListeningPage.qml` (838 lines), `daemon/noise_floor.py`,
`daemon/wake_listen.py` (**big**; assignment only), `manifest.json`,
`daemon/runtime.py`.

**New settings** (Listening → Microphone → Advanced):

| Key | Values (default) | Unreadable |
|---|---|---|
| `gateRiseTenths` | 1–30, shown as 0.1–3.0 dB/s (`5`, today's) | `5` |
| `gateFallTenths` | 5–100, shown as 0.5–10.0 dB/s (`30`, today's) | `30` |

**Tests.** A changed rate reaches the noise floor without a rebuild, read
through `runtime.Config`; bounds; unreadable → today's values; warm-up and
clamps unchanged; frames are still dropped on lock before the meter.

**Verify.** `preview.sh` listening for vosk, oww and sherpa, and an
unavailable engine; clicks. **Shell restart needed.** Live: switch
engines and only that engine's block shows; the wake test.

**Measure.** Time to settle after a synthetic 10 dB step in room noise at
slow, normal and fast.

**Risks.** A fast gate learning speech (it is still fed wake-phase frames
only; both rates are bounded).

**Going back.** An older build ignores both keys and uses the fixed rates.

### M24 · Conversation page

| | |
|---|---|
| Covers | item 13 (every approved part); bug C on the page |
| Needs | M2, M4 |
| Model | `claude-sonnet-5-5` (same keys, no daemon change) |

**Goal.** The same settings, compact. Timings become a picture, and open
mic shows its live state.

**Build.**

- **Pace presets** (Patient / Balanced / Snappy / Custom) as a compact
  selector at the top, writing the same keys the buttons write today.
- **Cards:** *Follow-ups* (`conversationMode`, `followUpMs`); *Open mic*
  (live on/off and time left from the state file, a **Turn on / Turn off**
  button, `openMicIdleMin`, `openMicAddressedOnly`, `openMicAuto`);
  *While it works* (`narration`, `narrationSilenceS`); *Talking over it*
  (`fullStopAnytime`, `bargeIn`, `bargeOnHeadset`, with `bargeFactor`
  under Advanced). The page keeps "turn off open mic", "stop a reply" and
  "stop the service" visibly apart.
- **"A turn, start to end":** a timeline drawn from the live values
  (lead-in, you talk up to `maxUtteranceMs`, the pause that ends a turn,
  the reply). Under it the limit note from M2 ("3 turns today hit the
  limit. **Raise it →**"), which opens Advanced at the longest-turn
  control.
- **Advanced timings:** `leadInMs`, `trailingSilenceMs`, `quickEndMs`,
  `minUtteranceMs`, `maxUtteranceMs`, `echoTailMs`.
- **Voice commands card:** generated from `agentvoice commands --json`,
  with the `commandsInSentences` control from M4.

**Files.** `pages/ConversationPage.qml`, new `ui/TurnTimeline.qml`,
`Settings.qml` (**big**; the deep link). **Settings.** None new.

**Tests.** The one-page test. The page holds no command phrase written by
hand. `maxUtteranceMs` stored as the string `"90000"` still works.

**Verify.** `preview.sh` conversation: preset and custom, open mic on with
a countdown, `limit_hits` above 0. **`clicks` diff** against the old page:
the same keys and values. **Shell restart needed.** At stop 5: a 90 s
capped turn and a shorter one; the count and the link.

**Risks.** A page refresh resetting a timing the user set (the clicks
diff).

**Going back.** Nothing stored changes.

### M25 · Voice page

| | |
|---|---|
| Covers | item 19; bug F |
| Needs | M1 |
| Model | `claude-sonnet-5-5`; use `claude-opus-5-5` if Whisper pinning is included (it touches `install.sh` and `models.lock`) |

**Goal.** The page the user likes, tidier: per-agent voices inline, and a
library that lines up.

**Build.**

- **Quick settings:** `speakReplies`, `chimes`.
- **Each agent:** name, voice, speed and ▶, with **Change on Agents →**,
  a deep link to that agent's card. Voice and speed keep their home there.
- **Library:** opens on **Downloaded**; a search box plus one compact
  filter (downloaded / all, accent, gender) replace the row of buttons;
  **the trash icon goes first, in a column reserved on every row**, so
  names and Test buttons line up (F); "Used for Theo, Sora", as
  `PlainText`. Use-for, fetch, retry, sample, remove and in-use protection
  are kept.
- **Advanced: hearing you:** `model` and `livePartials`, with one line on
  what transcription does (speech becomes text on this machine before
  anything is sent to an agent).
- **More models only once pinned** (question 10). Whisper is fetched by
  name with no hash today. If included here: pin `tiny.en`, `base.en`,
  `small.en` and `medium.en` in `models.lock`, fetch through the verified
  `download()`, load from a local path. Otherwise extra models are
  deferred and the gap recorded for V-02.

**Files.** `pages/VoicePage.qml`, `ui/VoiceLibraryRow.qml`,
`Settings.qml::assignVoice`; if pinning: `models.lock`,
`bench/pin-models.sh`, `install.sh` (run the box), `daemon/wake_listen.py`
(**big**; model path). **Settings.** None new.

**Tests.** `test_the_voice_librarys_shortcut_goes_through_one_function`
stays green. If pinning: a wrong hash is refused; the loader accepts every
offered model.

**Verify.** `preview.sh voices`, narrow and wide, installed, missing and
shared rows: the x position of the name and Test columns is equal across
rows, measured. **Shell restart needed.** Live: Test and Use for.

**Measure** (if models are added): memory and transcription time per model
over a fixed clip set, before they are offered.

**Risks.** Offering a model the loader cannot run (only pinned,
loader-tested models are listed).

**Going back.** An older build fetches Whisper by name as before. Reset a
model it does not know to a supported one first.

### M26 · Other settings, and About

| | |
|---|---|
| Covers | item 20 (the rest), item 21, item 22 (About parts) |
| Needs | M3, M4, M18, M21 |
| Model | `claude-opus-5-5` |

**Goal.** Display & privacy becomes **Other settings**, an honest grab-bag.
About gets real install information and the full command list.

**Build: Other settings** (`DisplayPage.qml` → `OtherSettingsPage.qml`,
with the old deep link kept as an alias):

- **On-screen readout:** `hud`, `hudLingerMs`, the four M3 keys, Preview,
  `agentsPanel`.
- **Privacy:** `yieldToRecorders`; `logSpeech` with ⚠, "the journal keeps
  it for weeks", and a confirm to turn on; `keepStats` with Clear stats;
  a pointer to chat storage on Chats; "The mic always closes while the
  screen is locked."
- **Keys:** read live from `hyprctl binds -j`, filtered to Agent Voice's
  commands, read-only, with **Open bindings file**. Changing a binding
  here is deferred (section 9).
- **Maintenance:** Repair installation and Remove Agent Voice
  (`DangerButton`), moved from About, with today's backup and recovery
  behaviour kept.

**Build: About.**

- **This install:** version, commit, branch (or "detached"), install time;
  the daemon's stamp compared with the plugin's, and a mismatch reported.
- **Copy diagnostics** (`agentvoice diagnostics`, to `wl-copy` on stdin):
  version and Omarchy version; a settings summary from an allowlist (no
  endpoint keys, URLs as host only, home paths as `~`, no folder text);
  the last 50 **structural** journal lines, with transcript lines left out
  even when `logSpeech` is on.
- **Check for updates:** only when clicked; a `git ls-remote` of the
  tracked remote, and the page names which remote it asked.
- **Changelog** (new `CHANGELOG.md`, kept from the phase notes),
  **License**, **README**.
- **Runs here vs. goes out:** wake, transcription and voices run locally;
  each backend shown as cloud or local with honest status (installed / has
  answered a turn / not found). Finding a program never counts as
  "connected". Ollama and llama.cpp are probed on `127.0.0.1:11434` and
  `:8080` when clicked.
- **Voice commands:** the full generated list with the wake phrases.

**Files.** `pages/DisplayPage.qml` → `pages/OtherSettingsPage.qml`,
`pages/AboutPage.qml`, `pages/qmldir`, `Settings.qml` (**big**; page
list), `install.sh` (VERSION stamp; **run the box**), `bin/agentvoice`,
new `daemon/diagnostics.py`, `daemon/endpoints.py`, `CHANGELOG.md`.
**Settings.** None new (keys move with the renamed page).

**Tests.** Diagnostics: seed a fake journal with a transcript line and an
endpoint key; both are absent and home paths collapsed. The clipboard is
fed on stdin. The VERSION format is read tolerantly, and an older install
shows "unknown branch". The one-page test. The confirm test covers Remove
and `logSpeech`.

**Verify.** `preview.sh` other and about; `clicks` with repair, remove and
logging stubbed: cancel writes nothing, confirm issues one action.
`AGENTVOICE_BOX=1`. **Shell restart needed.** Live: copy diagnostics,
paste into a scratch file, read it for anything personal. Never run Remove
on the live desktop.

**Risks.** A stale route stranding a setting (every old deep link checked).
Diagnostics carrying something personal (the allowlist, the seeded test).

**Going back.** An older build has the old pages; the keys are unchanged.

### M27 · Agents speak up when background work finishes

| | |
|---|---|
| Covers | item 24 |
| Needs | M2, M8 |
| Model | `claude-opus-5-5`, effort xhigh (a spike, and speech timing in the turn loop) |

**Goal.** When background work finishes, the agent says one short line and
a notification appears, without waiting for the wake word. It never talks
over anyone and stays silent when it should.

**Build, in two tiers.**

- **Tier 1, every backend: work the daemon itself tracks.** Results of
  delegated crew tasks already wait in `collab.Runtime.reports` for the
  caller's next turn. A finished task becomes a **completion event** the
  daemon trusts because it started the job. It is queued as an unprompted
  turn for the caller.
- **Tier 2, Claude only: its own background tasks.** Spike first, one real
  turn each: in a warm `claude -p` stream-json process start a background
  command (`sleep 20; echo done`) and a background sub-agent, let the turn
  end, and see whether new assistant output arrives when they finish. If
  it does, the adapter keeps reading between turns (assistant text only)
  and queues it the same way. If it does not, tier 2 is deferred with the
  recording as the reason.
- **A model writing "done" is text, not an event.** Only the daemon's own
  job tracking or the adapter's stream starts an announcement.
- **Delivery:** spoken only when nothing is capturing or speaking; queued
  behind the user and other agents; at most one line per agent per
  2 minutes; the spoken part capped at 300 characters (the rest goes to
  the chat, marked "unprompted"); duplicates dropped; stale events expire.
  It starts no microphone capture by itself; a normal follow-up window
  opens afterwards, never while locked.
- **Notification only, no speech,** while the screen is locked, the mic is
  muted, or Omarchy's notification silencing is on. A line that was
  silenced is **not replayed** on unlock.
- **The notification text is fixed** ("Theo finished a background task"),
  never the model's words, because `notify-send` takes its text in argv.

**Files.** `daemon/collab.py` (**big**), `daemon/adapters/base.py`,
`claude_code.py`, `daemon/wake_listen.py` (**big**; queue and delivery),
`daemon/crew.py`, `daemon/runtime.py`, `manifest.json`,
`pages/AgentsPage.qml` (**big**), `Hud.qml`.

**New settings:**

| Key (main / extra) | Values (default) | Unreadable | Control on |
|---|---|---|---|
| `mainSpeakWhenDone` / `voiceAgents[i].speakWhenDone` | bool (`true`; question 8) | `false` (quiet) | Agents → Agent card |

**Tests.** The queue never speaks while locked, capturing or speaking
(frame loop); silencing on → notification only; **no model text in the
notification's argv**; duplicate, replayed, cancelled and forged events;
the wrong session; two agents; the setting changed while queued; the
notification service missing; the rate limit; unreadable → off; the
spike's recording replays through the adapter.

**Verify.** Typed: a delegated task finishing announces itself. **Shell
restart needed** for the switch. By voice at stop 5: "Theo, run a
30-second background job and tell me when it's done"; again with
`agentvoice lock`; again with silencing on; again while the user is
talking.

**Measure.** Finish to notification and finish to speech, median of 5.

**Risks.** Repeated or private speech is a blocker for this phase.

**Going back.** An older build never speaks unprompted and returns to
next-turn reports. Drain the queue first, so nothing is said twice.

### M28 · Settings search, and first-run setup

| | |
|---|---|
| Covers | item 22 (search, first run) |
| Needs | every page phase |
| Model | `claude-opus-5-5` |

**Build.**

- **Settings search:** a field at the top of the sidebar (Ctrl+F), backed
  by an index (`ui/SettingsIndex.js`) from labels, keys and synonyms
  ("pause") to page, agent, tab and anchor. A result opens the right
  place, unfolds Advanced, and focuses the control.
- **First-run setup:** shown on a fresh install (no agent folders, the
  service never started) and from About → **Run setup again**. Steps:
  microphone (level, gate); wake word (engine, say it three times through
  `wake-test`); first agent (program detected, name, wake phrase); done.
  Skip and resume work. It lives in a root-level `Setup.qml` and writes
  through the overlay's existing functions: a documented exception in
  `test_settings_pages.py`, not a second page. A "done" marker is kept
  outside the plugin as UI state; skipping changes no setting.

**Files.** `Settings.qml` (**big**), `ui/SidebarNav.qml`, new
`ui/SettingsSearch.qml`, `ui/SettingsIndex.js`, new `Setup.qml`,
`pages/AboutPage.qml`. **Settings.** None.

**Tests.** **Every manifest key and every defaults-only key has a search
entry**, and every entry's page exists, so search cannot drift. Old deep
links still resolve. The Setup exception is held to the keys it may write.

**Verify.** `preview.sh` fresh and configured states, narrow and wide.
**Shell restart needed.** Keyboard: find "pause" and land on the control.

**Risks.** Setup overwriting a working agent, or reappearing at every
login (the marker; never shown on a configured install).

**Going back.** An older build ignores the marker.

### M29 · Consistency audit, keyboard and light theme

| | |
|---|---|
| Covers | item 17 (the audit); item 22 (keyboard and light theme) |
| Needs | M28 |
| Model | `claude-opus-5-5` |

**Goal.** Every page looks and behaves like the others. This rehearses
V-09, V-13 and V-22.

**Build.**

- The whole `preview.sh` set, every page and tab, narrow and wide, dark
  and `flexoki-light`, empty and 8-agent states, laid side by side. Any
  old-style row, wall of text, or page not in stage order is fixed here.
- A keyboard-only pass in the preview for every page: focus order, visible
  focus, accessible names, every action reachable.
- A static test: no page still uses the old `SettingsGroup` / `KnobRow`.
- The M1 inventory compared one last time: every key from the start still
  has exactly one working home, and no setting was removed.

**Files.** Whatever the audit finds, in `pages/` and `ui/`; the tests.
**Settings.** None.

**Verify.** The screenshot sheet saved with the notes. **Shell restart
needed.** The real-shell keyboard walk is the user's, at M30.

**Risks.** The audit growing into a rewrite: fix what breaks consistency,
and list the rest as polish for Phase 17.

**Going back.** UI only.

### M30 · Release candidate, and hand-off to Phase 17

| | |
|---|---|
| Covers | every item and A to K; the Phase 17 entry gate |
| Needs | everything; the user present |
| Model | `claude-opus-5-5`, run interactively |

**Goal.** One installed build, proven to be the commit it claims, with its
evidence in one place. **This phase builds nothing.**

**Steps.**

1. Read `project-status-2026-11-21.md` again. Copy the mapping table
   (section 8) into the notes and add, per row, the delivering commit or a
   reason and an owner for a deferral. Bug H's gate must have passed.
2. Carry forward the live checks still owed from Phases 12 to 16 (spoken
   passes and stop, live cards, the Codex quota items, Gemini and endpoint
   targets, the real-shell keyboard walk, #10) and every "not verified"
   from M1 to M29. Do them with the user or leave them listed.
3. Fast-forward `dev` to `phase-m29` and `main` to `dev`; push to `fork`.
4. Deploy and install that commit from a clean checkout; one deliberate
   `omarchy-restart-shell`.
5. **Prove the install:** `git archive` plus `diff -r` against the
   installed `daemon/`, `bin/`, `desktop/`, `install.sh`,
   `requirements*.txt` and `models.lock`; manifest and QML hashes compared
   separately; the version stamp, the service banner, and a clean (not
   `-dirty`) tree. A matching version label alone is not enough.
6. `AGENTVOICE_STRICT=1` and `AGENTVOICE_NO_SKIPS=1` runs, and the box.
7. **Rerun the M0 baseline as a pair** on the same hardware, audio device,
   agents, settings and sample count: median and p95, prompt size, process
   count, memory. Controlled samples kept apart from journal timings.
8. A synthetic installed wake, reply and stop.
9. Refresh `CODEBASE.md` and write a new project status note. Update
   `phase-17-plan.md` wherever a V-row changed (item 24 gets a case under
   V-08 and V-12; M22's modes under V-19). Tick the entry gate.
10. Hand the user: the installed commit, the baseline pair, the tested
    downgrade steps (section 7.7), the item ledger, known limits, and
    fixtures for V-01 to V-23.

**Going back.** This is the revision Phase 17's going-back case (V-02)
starts from. A mixed daemon and UI makes the sweep worthless: restore both
from one commit.

---

## 7. Security review

These features widen what agents can do or what reaches them. For each:
how it stays fail-closed, where that is enforced, and what proves it. The
fail-open rules in `CLAUDE.md` hold throughout.

### 7.1 Auto-detected tools (M10)

- **Off by default.** A missing per-agent value inherits `sharedTools`,
  whose default is `{}`. Unreadable is off. A mutation of the default
  turns a test red.
- **Enforced only where a recorded turn proves it.** Claude gets
  `--strict-mcp-config` with a generated list; without it "off" would be
  untrue, because `claude -p` loads the user's own servers today. A CLI
  switch says "told, not enforced" except where deny rules are shown to
  hold.
- **Detection runs nothing:** config files only; a test makes `subprocess`
  fail during a scan.
- **A changed definition needs approval again** (the fingerprint).
- **Secrets never reach argv:** the MCP config moves to a 0600 file, never
  logged, never in diagnostics.
- **Trusted runs detected tools without asking.** Below Trusted the hook
  asks for every MCP tool call. At Trusted each switch shows ⚠ "runs
  without asking at Trusted".
- **Outside content:** an agent with a detected MCP server on has its
  notes and answers marked tainted and counts toward the Rule of Two
  warning.

### 7.2 Agents searching chats (M20)

- **The daemon decides the scope** from the caller's `SO_PEERCRED`
  identity, not from the call. Default `own` is the existing replay rule.
  Unreadable is off; quarantined is always off.
- **Checked per chat before anything is read out of it**, including
  counts: a forbidden chat is invisible, not just unquoted.
- **What comes back is data:** wrapped, attributed, capped.
- **The query is never stored.** Nothing to search with saving off.
- **Honest limit:** a Trusted agent with a shell can read the chat files
  directly. The page says so.
- **Proof:** a canary word in a forbidden chat, checked in every response,
  both output streams, and process arguments.

### 7.3 Skills and notes moving between agents (M11 to M13, M15)

- **Only the user moves anything.** No agent tool moves, combines or
  imports. Raw writes into `agents/` and `communal/` stay under the orders
  guard at every level.
- **Confirm before widening:** into Communal; out of a quarantined agent;
  a tainted note; an import. The confirm names the audience, and for
  notes says past versions move too.
- **External skills are copied, never moved or edited** (hashed before and
  after).
- **Validation as for any skill:** stable roots, no path traversal, no
  symlinks (dangling ones included), no special files, the size bounds. A
  malformed skill is listed and not delivered.
- **Metadata travels:** taint, locks, author and history. A corrupt
  destination refuses the move. `notesWrite=deny` and note locks hold.
- **Crash-safe:** staged, published once, recovered before either side is
  shown to an adapter.
- **Every move writes an audit line:** ids, names, sizes. Never text.

### 7.4 The crew map and quarantine (M7 to M9)

- **The saved list is the rule,** checked in `collab.py` at request,
  approval, dispatch and delivery, read fresh each time. The map and the
  table only edit it, through one function.
- **Unlinked, reversed or unlisted = refused.** Empty or missing = nobody
  linked. Unreadable = every agent-started call refused.
- **Quarantine is enforced in the daemon:** no outgoing calls; incoming
  ask or delegate only, with a capped brief, no history and no
  `shared_with` change; answers tainted; no communal-note writes or chat
  search; old sessions detached at the moment of quarantine; release
  grants nothing.
- **"Ask me first" is only as good as the card.** M7 authenticates the
  answer and adds the orders-guard rule. Its limits are written down, and
  V-07 attacks it.
- **Who can change the list:** an agent writing `crewLinks` in
  `shell.json` is asked at every level by the orders guard. Trusted Codex
  has no hook, so the page shows "changed outside Settings at HH:MM".

### 7.5 Other things that widen or reach out

| Feature | How it stays safe |
|---|---|
| Extra flags and environment (M17) | Denylist checked at launch in the adapter, refused even after a confirm; environment in a 0600 file; the full command line shown; audit |
| Try it, summaries (M6, M19) | Quiet side turns, prompt on stdin, no tools, rate-limited, never saved to a chat, refused while locked |
| Commands in sentences (M4) | A policy table, a measured default, spoken once, undo; never on the agent's own voice, in dictation, or while locked |
| Background announcements (M27) | Speech only, no actions; only daemon-tracked events; rate-limited; silent while locked, muted or silenced; fixed notification text |
| The Agent Voice skill (M14) | Never teaches `agentvoice permit`, a settings write, or anything under the orders guard (tested) |
| Diagnostics and update check (M26) | Allowlist of fields, structural lines only, no keys, paths collapsed; the update check runs only on click |
| Stats (M21) | Typed numbers and ids only (AST check), 0600, 90 days, an off switch |
| Wake decisions (M22) | A missing second stage holds wakes closed; it never quietly falls back to one stage |
| Duplicate an agent (M17) | New id; no grants, secrets, sessions or replay rights copied |

### 7.6 Rules every phase keeps

- Spoken, typed, folder and chat text never goes in argv. Every new CLI
  verb takes text on stdin, and the argv test is extended to each new
  adapter path.
- Untrusted text is shown as `PlainText`; anything printed goes through
  `safe_for_terminal`.
- Anything one agent hands another is wrapped with its source and taint.
- A new setting fails to its safe value when unreadable (Appendix A).
- The audit and stats logs never hold text (AST-checked).
- The mic closes while locked: frames are dropped before measurement, a
  capture in flight is abandoned, the HUD hides, and a prior mute survives
  unlock. No new feature speaks, listens or shows text over a lock screen.
- The orders guard stays on at Trusted, with `onFailure: block`.

### 7.7 Going back to an older build

Several protections do not exist in older builds, so a plain downgrade is
**fail-open**: all-to-all collaboration, no quarantine, communal for
everyone, every user MCP server loaded, every skill delivered. Before
starting an older daemon, on copies first:

1. Stop the daemon; cancel chains and children; drain announcements.
2. Back up settings, agent and communal folders, chats, grants and caches
   (private, versioned).
3. Finish or roll back any pending transfer.
4. For each affected agent, set the switches an old build *does* read
   (collaboration, tools) to off. Move skills that were switched off, and
   communal material an agent opted out of, outside every folder the old
   build loads; rebuild its caches.
5. If the old build cannot express a restriction at all (quarantine,
   "ask me first", an opt-out), keep that agent stopped while it runs.
6. Restore the saved settings only with a daemon that enforces them.

M30 tries this once and times it, for V-02 and V-12.

---

## 8. Mapping table

Every feedback item and bug, and where it is delivered.

| Item | What | Phase |
|---|---|---|
| 1 | Commands inside a longer sentence | M4 |
| 2 | Remove the popup's "what Claude Code may do" | M3 |
| 3 | Popup jumps around | M3 |
| 4 | Shell restarts whenever a file is saved | M0 |
| 5 | Chats as their own sidebar page; drop the top-row button | M18 |
| 6 | Easier chats: names, details, search, agents can search, bubbles | M18 (page, list, search box, layout), M19 (names, summaries, filters), M20 (agent tool) |
| 7 | Overview statistics (all five) | M21 |
| 8 | Agents tab: cards, compact effort, chips, header strip, no duplicates | M5 |
| 9 | Agent details: tabs instead of a drop-down | M6 |
| 10 | Personality: trait chips, hints, templates, Try it, meters | M6 |
| 11 | Tools & skills: detection, real controls, draggable skills, Unused, Agent Voice skill | M10 (tools), M11 (skills found, Unused, controls), M12 (drag, copy, undo), M14 (the skill) |
| 12 | Notes in categories, movable | M13 |
| 13 | Conversation page polish (all approved parts) | M24; the rename in M18; the limit counter in M2; the command list from M4 |
| 14 | Agent details Advanced, plus warning + confirm everywhere | M16 (shown), M17 (edited); confirm across the window from M1 |
| 15 | Communal: shared tools, who gets it, preview, import, history, skills gap | M5 (Tools tab), M10 (shared tools), M11 (skills gap), M12 and M13 (cards), M15 (the rest), M18 (chats) |
| 16 | Crew map | M7 (honest approval), M8 (list, enforcement, quarantine, table), M9 (drawn map) |
| 17 | One design language | M1 (pieces), each page phase, M29 (audit) |
| 18 | Listening as a pipeline | M22 (the decision made real), M23 (the page, gate speed) |
| 19 | Voice page | M25. Partial: extra transcription models only once pinned (section 9) |
| 20 | Display & privacy → Other settings | M3 (readout), M18 (chat privacy), M21 (stats privacy), M26 (the rest). Partial: changing key bindings deferred (section 9) |
| 21 | About page | M26 |
| 22 | Diagnostics, updates, changelog, license; search; first run; keyboard and light theme; command caution; fix H early | M26 (About parts), M28 (search, first run), M29 (keyboard, light theme), M4 (caution), M0 (H) |
| 24 | Speak up when background work finishes | M27. Crew work on every backend; an agent's own background tasks on Claude only, if the spike allows (section 9) |

There is no item 23: section 23 of the notes is the bug list.

| Bug | What | Phase | Closed when |
|---|---|---|---|
| A | Commands only fire when said alone | M4 | The example sentence fires; the false-trigger list does not |
| B | Popup bounces | M3 | 0 px height change in locked mode |
| C | Turns cut at 30 s with no warning | M2 (counter, note), M24 (page) | A real cut-off shows the note and its link; the 90 s case run |
| D | Old global permission section on the popup | M3 | Gone; per-agent editing and real cards still work |
| E | Duplicate tool sections at the bottom of Agents | M5 | Gone; the three keys have one working home |
| F | Voice library rows misalign | M25 | Equal column positions with and without a trash icon |
| G | Tools & skills has no controls | M10 (tools), M11 (skills) | Each control changes what the agent really gets |
| H | Shell restarts on any write in the plugin folder | M0 | The gate: 0 events, same PID, window stays open |
| I | Open-mic chats lose earlier turns | M2 | A marker is recalled after a level flip, both ways |
| J | Surprise "be-deep" chime, chats feel restarted | M2 | The chime's cause logged and removed; no reset proven |
| K | "Still listening" lingers after open mic off | M2 | Cleared within one tick, measured |

Also carried, not lettered: `testresults.md` #10 → M2. Phase 16's "a
Trusted agent can answer its own card" → M7.

---

## 9. Deferred, on purpose

| What | Why |
|---|---|
| Changing key bindings from Other settings (part of item 20) | Bindings live in the user's Hyprland config, which Omarchy owns. The page shows them live and opens the file. |
| Extra Whisper models (part of item 19), unless M25 pins them | Whisper is fetched by name with no hash. More unpinned downloads would break the pinning rule. |
| An agent's own background tasks announced on Codex, Gemini, Antigravity, Copilot and endpoints (part of item 24) | Their process ends with the turn. Crew work is still announced for them (M27 tier 1). The page says why. |
| A daemon broker in the path of every detected tool call (Astra plan, 6b) | Much larger than item 11 asks for. M10 uses strict MCP, the hook, the fingerprint and honest labels. Revisit if V-04 or V-07 finds a hole. |
| In the mockups but not the feedback: a mic device picker, per-agent "talk while working", an "ask" value for writing notes, per-agent "speak replies" | Not requested. Built only if the user asks (question 9). |
| Phase 16's other open questions (voice yes/no on cards, a stop-only window, Codex side questions over 5 s, messages lost on restart, timeouts in the audit) | Not in this feedback. They stay listed for Phase 17. |
| A general sandbox for Trusted backends; merged-plan's own deferred list | Unchanged. |

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| 31 phases is a long round | Daily fixes come first (M0 to M4). Every phase stands alone and fast-forwards `dev`, so the round can stop after any phase. |
| The big shared files take repeated edits (`wake_listen.py` in a dozen phases, `AgentsPage.qml` in four) | New modules and `ui/` pieces, small hooks, `FIELD_HOMES`, the clicks diff, the touched-files list in each phase's notes |
| An unattended phase installs something broken while the user is away | The default path of every new setting is today's behaviour; the script never restarts the shell; `agentvoice-deploy <older sha>` is the way back; M2, M4 and M22 keep "existing tests pass unchanged" as a gate |
| A per-agent field ends up with two homes | `FIELD_HOMES` (M1) and the overlay-function pattern |
| Strict MCP removes tools the user relies on | The M10 spike, a one-time notice, one-click restore |
| Collaboration stops on upgrade | The banner and the one-click "link everyone as before" |
| Commands misfire inside sentences | The policy table, a default chosen from measured numbers, spoken confirmation, undo |
| Secrets leak through MCP configs or environment variables | 0600 files, nothing in argv, logs or diagnostics |
| The drawn crew map overruns its session | Time box: ship the table, carry the map |
| A spike (M10, M27) comes out against the design | Each phase already says what happens then: honest labels, or a deferral with the recording |
| The card authentication in M7 cannot be made sound | Ship M8 with "ask me first" labelled advisory for Trusted agents; V-07 tests it |
| Preview differs from the real shell | A real-shell check at each stop point and in M30 |
| Codex review quota runs out mid-round | The notes say "review owed". Never marked done. Tier A phases wait for the review before the next phase starts. |

---

## 11. Open questions for the user

Each has the default the script uses if there is no answer. Questions 1 and
14 are needed before M0; the rest before the phase named.

| # | Before | Question | Default |
|---|---|---|---|
| 1 | M0 | Dev clone at `~/Projects/agent-voice`, and point Theo's project folder there? | **Answered 2026-11-21 (M0):** yes, both |
| 2 | M8 | Crew links on upgrade: nobody linked until you link them, with a one-click "link everyone as before"? Or keep everyone linked until the first link is drawn? | Nobody linked, with the button |
| 3 | M10 | Strict MCP: start with every detected server off, with a one-click "turn back on" list? Or keep what each agent loads today? | Off, with the list |
| 4 | M4 | Commands in sentences: default `edges` (start or end only) or `clause` (your example works mid-sentence)? | `edges`, unless the measured numbers favour `clause` |
| 5 | M19 | Chat titles and summaries written by the chat's own agent (one short side turn per chat): on by default? | On |
| 6 | M20 | Agent chat search: on by default for an agent's own and shared chats, or off until switched on? | Own and shared |
| 7 | M14 | The Agent Voice skill: explain only, or may agents also run read-only commands such as `agentvoice status`? | Explain only |
| 8 | M27 | Announcements on by default per agent, with a fixed-text notification while locked or silenced? | Yes |
| 9 | M5 | Mockup extras not in the notes (mic picker, per-agent talk while working, "ask" for notes, per-agent speak replies): build any? | No |
| 10 | M25 | Pin Whisper models so more can be offered? | Yes if it fits the session, else deferred |
| 11 | M8 | Should quarantine also block communal-note writes and chat search? | Yes |
| 12 | M17 | Extra flags: a denylist plus confirm, or only a short allowlist of known-safe flags? | Denylist plus confirm |
| 13 | — | Top model for the round | **Answered 2026-11-21:** Opus 5.5 at xhigh is the highest model used |
| 14 | M0 | May the script deploy and install at the end of each phase once the daemon is idle, leaving shell restarts for the stop points? | **Answered 2026-11-21 (M0):** yes |
| 15 | M30 | Which backends and audio devices must pass **live** before release? | Claude Code and Codex live; the rest fixture-only and labelled so |

---

## Appendix A: new settings at a glance

Every row needs all three parts in the phase named: manifest schema and
defaults, `runtime.DEFAULTS`, and one control. Per-agent keys live in
`voiceAgents[i]` with a `main*` top-level twin. Names may still change in
the owning phase; the three parts and the one home may not.

| Key | Phase | Values (default) | Unreadable | Home |
|---|---|---|---|---|
| `hudSize` | M3 | locked / dynamic (locked) | locked | Other settings |
| `hudKeepReply` | M3 | bool (true) | true | Other settings |
| `hudPosition` | M3 | top / bottom (top) | top | Other settings |
| `hudTextSize` | M3 | small / medium / large (medium) | medium | Other settings |
| `commandsInSentences` | M4 | alone / edges / clause (edges) | alone | Conversation |
| `crewLinks` | M8 | list ([]) | refuse all agent-started calls | Crew map |
| `crewQuarantine` | M8 | ids ([]) | refuse all agent-started calls | Crew map |
| `sharedTools` | M10 | map ({}) | {} (all off) | Communal → Tools |
| tool entries `mcp:*`, `cli:*` (per agent) | M10 | inherit / on / off (inherit) | off | Agent details → Tools & skills |
| `mainSkillsOff` / `.skillsOff` | M11 | names ([]) | communal skills off for that agent | Agent details → Tools & skills |
| `agentvoiceSkill` | M14 | bool (true) | false | Communal → Tools |
| tool entry `agentvoiceSkill` (per agent) | M14 | inherit / on / off | inherit | Agent details → Tools & skills |
| `communalOff` | M15 | ids ([]) | [] (everyone gets communal) | Communal |
| `mainResume` / `.resume` | M17 | bool (true) | true | Agent details → Advanced |
| `mainIdleTimeoutS` / `.idleTimeoutS` | M17 | 30–600 (90) | 90 | Agent details → Advanced |
| `mainExtraArgs` / `.extraArgs` | M17 | list ([]) | [] | Agent details → Advanced |
| `chatSummaries` | M19 | off / owner (owner) | off | Chats |
| `mainChatSearch` / `.chatSearch` | M20 | off / own / all (own) | off | Agents |
| `keepStats` | M21 | bool (true) | false | Other settings |
| `wakeBothAgree` | M22 | bool (false) | false | Listening |
| `gateRiseTenths` | M23 | 1–30 (5) | 5 | Listening |
| `gateFallTenths` | M23 | 5–100 (30) | 30 | Listening |
| `mainSpeakWhenDone` / `.speakWhenDone` | M27 | bool (true) | false | Agents |

**Files, not settings:** extra environment variables
(`~/.config/agentvoice/agent-env.json`, 0600); the crew map layout
(`$XDG_STATE_HOME/agentvoice/crew-layout.json`); stats (`DATA_DIR/stats/`);
the tool scan cache (`$RUNDIR`); the setup "done" marker.

**Moved, same names:** `desktopTools`, `browserTools`, `omarchySkill` →
Communal (M5); per-agent tool switches → Agent details (M10); `saveChats`,
`chatRetention`, `keepHistory` → Chats (M18); the rest of Display → Other
settings (M26).

## Appendix B: the runner table

One object per phase, for the Python script. `mode` is `interactive` (the
user starts it and stays) or `script`. `stop_after` means: stop, and wait
for the user to do the stop point in section 4.3. `needs` lists phases
whose notes must be committed first. The Codex reviewer for every phase is
`gpt-6.2-astra`.

```json
[
  {"phase": "M0",  "branch": "phase-m0",  "model": "claude-opus-5-5",   "effort": "high",  "mode": "interactive", "stop_after": true,  "needs": []},
  {"phase": "M1",  "branch": "phase-m1",  "model": "claude-opus-5-5",   "effort": "high",  "mode": "script",      "stop_after": false, "needs": ["M0"]},
  {"phase": "M2",  "branch": "phase-m2",  "model": "claude-opus-5-5",   "effort": "xhigh", "mode": "script",      "stop_after": false, "needs": ["M0"]},
  {"phase": "M3",  "branch": "phase-m3",  "model": "claude-opus-5-5",   "effort": "high",  "mode": "script",      "stop_after": false, "needs": ["M1"]},
  {"phase": "M4",  "branch": "phase-m4",  "model": "claude-opus-5-5",   "effort": "xhigh", "mode": "script",      "stop_after": true,  "needs": ["M2"]},
  {"phase": "M5",  "branch": "phase-m5",  "model": "claude-opus-5-5",   "effort": "high",  "mode": "script",      "stop_after": false, "needs": ["M1"]},
  {"phase": "M6",  "branch": "phase-m6",  "model": "claude-opus-5-5",   "effort": "high",  "mode": "script",      "stop_after": false, "needs": ["M1"]},
  {"phase": "M7",  "branch": "phase-m7",  "model": "claude-opus-5-5",   "effort": "xhigh", "mode": "script",      "stop_after": false, "needs": ["M2"]},
  {"phase": "M8",  "branch": "phase-m8",  "model": "claude-opus-5-5",   "effort": "xhigh", "mode": "script",      "stop_after": false, "needs": ["M6", "M7"]},
  {"phase": "M9",  "branch": "phase-m9",  "model": "claude-opus-5-5",   "effort": "high",  "mode": "script",      "stop_after": true,  "needs": ["M8"]},
  {"phase": "M10", "branch": "phase-m10", "model": "claude-opus-5-5",   "effort": "xhigh", "mode": "script",      "stop_after": false, "needs": ["M6", "M8"]},
  {"phase": "M11", "branch": "phase-m11", "model": "claude-opus-5-5",   "effort": "high",  "mode": "script",      "stop_after": false, "needs": ["M10"]},
  {"phase": "M12", "branch": "phase-m12", "model": "claude-opus-5-5",   "effort": "high",  "mode": "script",      "stop_after": false, "needs": ["M11"]},
  {"phase": "M13", "branch": "phase-m13", "model": "claude-opus-5-5",   "effort": "high",  "mode": "script",      "stop_after": false, "needs": ["M12"]},
  {"phase": "M14", "branch": "phase-m14", "model": "claude-sonnet-5-5", "effort": "high",  "mode": "script",      "stop_after": false, "needs": ["M4", "M11"]},
  {"phase": "M15", "branch": "phase-m15", "model": "claude-opus-5-5",   "effort": "high",  "mode": "script",      "stop_after": true,  "needs": ["M10", "M11", "M13"]},
  {"phase": "M16", "branch": "phase-m16", "model": "claude-opus-5-5",   "effort": "high",  "mode": "script",      "stop_after": false, "needs": ["M10"]},
  {"phase": "M17", "branch": "phase-m17", "model": "claude-opus-5-5",   "effort": "xhigh", "mode": "script",      "stop_after": false, "needs": ["M16"]},
  {"phase": "M18", "branch": "phase-m18", "model": "claude-opus-5-5",   "effort": "high",  "mode": "script",      "stop_after": false, "needs": ["M1"]},
  {"phase": "M19", "branch": "phase-m19", "model": "claude-opus-5-5",   "effort": "high",  "mode": "script",      "stop_after": false, "needs": ["M18"]},
  {"phase": "M20", "branch": "phase-m20", "model": "claude-opus-5-5",   "effort": "xhigh", "mode": "script",      "stop_after": true,  "needs": ["M19", "M8"]},
  {"phase": "M21", "branch": "phase-m21", "model": "claude-opus-5-5",   "effort": "high",  "mode": "script",      "stop_after": false, "needs": ["M2"]},
  {"phase": "M22", "branch": "phase-m22", "model": "claude-opus-5-5",   "effort": "xhigh", "mode": "script",      "stop_after": false, "needs": ["M21"]},
  {"phase": "M23", "branch": "phase-m23", "model": "claude-opus-5-5",   "effort": "high",  "mode": "script",      "stop_after": false, "needs": ["M21", "M22"]},
  {"phase": "M24", "branch": "phase-m24", "model": "claude-sonnet-5-5", "effort": "high",  "mode": "script",      "stop_after": false, "needs": ["M2", "M4"]},
  {"phase": "M25", "branch": "phase-m25", "model": "claude-sonnet-5-5", "effort": "high",  "mode": "script",      "stop_after": false, "needs": ["M1"]},
  {"phase": "M26", "branch": "phase-m26", "model": "claude-opus-5-5",   "effort": "high",  "mode": "script",      "stop_after": false, "needs": ["M3", "M4", "M18", "M21"]},
  {"phase": "M27", "branch": "phase-m27", "model": "claude-opus-5-5",   "effort": "xhigh", "mode": "script",      "stop_after": true,  "needs": ["M2", "M8"]},
  {"phase": "M28", "branch": "phase-m28", "model": "claude-opus-5-5",   "effort": "high",  "mode": "script",      "stop_after": false, "needs": ["M26"]},
  {"phase": "M29", "branch": "phase-m29", "model": "claude-opus-5-5",   "effort": "high",  "mode": "script",      "stop_after": false, "needs": ["M28"]},
  {"phase": "M30", "branch": "phase-m30", "model": "claude-opus-5-5",   "effort": "high",  "mode": "interactive", "stop_after": true,  "needs": ["M29"]}
]
```

Phases run in number order, each branching from the one before, so `needs`
is a safety check for the script, not a way to reorder. M25 switches to
`claude-opus-5-5` if question 10 is answered yes.
