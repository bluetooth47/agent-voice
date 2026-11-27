# Phase M30: Release candidate, and hand-off to Phase 17 — PAUSED

Written 2026-11-27, interactively, with the user at the desk for the live
checks. Branch `phase-m30`, cut from `phase-m29` at 963e738. Model: Claude
Opus 5.5. M30 builds nothing, and this run built nothing.

**Result: paused on a release blocker, by the user's decision (2026-11-27).**
The live checks found the skills screens unusable (below, "The release
blocker"). The user chose to build the fix as a new phase, **M31**, and then
rerun this release candidate on top of it. So no hand-off to Phase 17 is
given here, the Phase 17 entry gate is not ticked, and none of steps 6, 9 or
10 is done. What this run did establish, on the installed 963e738, is written
down so the rerun can reuse what M31 does not touch and knows what it must
redo.

Commits: these notes only, on top of 963e738. Nothing fast-forwarded by this
commit; `dev` and `main` stay at 963e738.

**Codex review: owed.** Not run in this run. No code was written, so M30 has
no diff of its own to review. The guard-set review of the owed range
(a15e78a..963e738, low effort, capped, the user's choice) moves to the rerun.
Credits at 2026-11-27, read from `rate_limits` in the newest
`~/.codex/sessions/2026/11/25/*.jsonl`: `credits.balance` "0"
(`has_credits` false), plan `plus`, primary (5 h) 0.0 % used, secondary
(7 d) 0.0 % used. So a review will run on plan quota, not credits. M12 to
M29 remain "review owed".

## A restart, and what the first run left

This was the second M30 run. The first (2026-11-25 19:21 to 19:36) was killed
when its deploy's `install.sh` restarted `agentvoice.service`: the run's
terminal had been opened by an agent, so it was a child of the service
(`KillMode=control-group`), and every service restart kills it. What it had
done, confirmed from git, the deploy log and the installed files:

- Step 3 done: `main` reset to 963e738 at 19:29:25 and pushed to `fork` at
  19:29:28; `dev` at 963e738 (= `phase-m29`) since 2026-11-23. Today
  `main`, `fork/main`, `dev` and `fork/dev` are all 963e738.
- The deploy completed: deploys.log
  `2026-11-25T19:36:46-07:00  137f775… → 963e738…`.
- `install.sh --yes` did all its file work and the service restarted at
  19:36:49 (ActiveEnterTimestamp). What died with the terminal was only the
  closing text and `offer_keybinds` (key bindings were already in place).
- `~/agentvoice-notes/shell.json.before-M30` (19:15) is the first run's
  backup, mode 0644 (finding h).

The user chose to accept that install rather than redeploy (step 5 proves
it). This run started in its own systemd scope
(`app.slice/m30-terminal-*.scope`), so later service restarts could not kill
it.

## Step 1: status, mapping table, bug H

Re-read project-status-2026-11-21.md and the plan. The mapping table with
the delivering commits is "Item ledger" below. Bug H's gate passed in M0
(phaseM0notes.md: 0 reload events, same shell PID, window open) and nothing
since has changed the symlink layout.

## Step 4: deploy, install, and one deliberate shell restart

Deploy and install: the first run's (above), accepted.
`omarchy-restart-shell`, run with the user's approval at 2026-11-25
19:59:16: quickshell PID 1293 → 154084. The service was untouched
(ActiveEnterTimestamp still 19:36:49). No QML had changed since 137f775
(137f775..963e738 is notes and images), and the old shell had started at
boot (18:25), so it was already reading the current QML; the restart makes
that certain and gives the watcher a fresh start.

## Step 5: the install, proven

Rechecked 2026-11-27 against `git archive 963e738` (/tmp/m30-proof.i7QF):

- Plugin path `~/.config/omarchy/plugins/duaneoca.agentvoice` →
  `~/.local/share/agentvoice-plugin`, a detached checkout at
  963e738a8c3d…, `git status --porcelain` empty.
- `diff -r` of the archive against that checkout: identical, apart from
  `__pycache__`/`.pytest_cache` folders, which are git-ignored and older than
  the deploy.
- `diff -r` of the archive's `daemon/` and `bin/` against
  `~/.local/share/agentvoice/app/`: identical (bytecode excluded).
- `manifest.json` sha256 c3950d450f0cf0ba… in both; every `.qml` hashed in
  sorted order: f9d855ebcd5f7c80… in both.
- `~/.local/share/agentvoice/app/VERSION`: `0.2.0 (963e738)`,
  `commit=963e738a8c3dcedd0fd108c9574aa4206fe7c745`, `branch=detached`,
  `installed=2026-11-25T19:36:47-07:00`.
- `agentvoice about` (2026-11-27): "settings 963e738a8c3d (detached)",
  "service 0.2.0 (963e738) (detached), installed 2026-11-25T19:36:47-07:00",
  "The settings and the service are the same build."
- The clone's tree clean on `phase-m30` throughout.

**Step 5: passed.**

## Step 7: the M0 baseline rerun as a pair

M0 build (92c71ff, from `git archive` into /tmp/m30-bench/m0) and the RC
(963e738), alternated M0, RC, M0, RC on 2026-11-25 19:47 to 20:00, load
0.7 to 1.2 throughout (M0's own baseline ran at 5.6 to 6.9, which is why
§40 called it provisional). Protocol: §33 S, Sora (Claude Code, haiku),
20 cold and 20 warm asks per round, 160 turns, 0 failures, 0 fallbacks to
cold.

| | M0 r1 | RC r1 | M0 r2 | RC r2 |
|---|---|---|---|---|
| warm median / p95 (s) | 1.32 / 1.57 | 1.31 / 1.52 | 1.32 / 1.55 | 1.31 / 1.76 |
| cold median / p95 (s) | 2.34 / 2.91 | 2.27 / 2.42 | 2.30 / 2.76 | 2.26 / 3.46 |

RC round 2's p95 is inflated by the deliberate shell restart (19:59:16),
which overlapped it: two cold outliers 3.46/3.66 s and a warm 2.46 s. The
medians say no regression: the RC is 0.01 s faster warm and 0.04 to 0.07 s
faster cold.

Prompt size (`bench/preamble_size.py --json`): Claude agents unchanged
(Theo 1109 chars ≈ 277 tokens, Sora 1210 ≈ 302). Codex (Hazel) 7088 → 7389
chars (≈ 1772 → 1847 tokens): the Omarchy skill text grew 5979 → 6280 and
the Agent Voice skill's list entry adds 299 (M14).

Processes and memory for a warm Sora agent (/tmp/m30-bench/procs.py, 5 runs
each, median): M0 4 processes, 263.1 MB idle, 260.9 MB after a turn; RC 4
processes (3 to 5: extra `claude` children that come and go), 247.0 MB idle,
244.4 MB after a turn.

J, from the journal since the install (`bench/turn_latency.py --since
'2026-11-25 19:36:49'`), only the live checks' own turns: Theo 12 turns,
end of speech to first word median 6.2 s, p95 7.7 s (wake to word 10.2 /
18.9 s, 8 turns); Hazel (Codex) 1 turn, 8.8 s. M0's J was Theo 105 turns,
median 9.7 s. Too few turns, and a different mix, to call that a gain.

Not done: `agentvoice wake-test auto` (CPU-heavy, changes nothing between
builds); FINDINGS §58 and `bench/baselines/m30.json` not written, because
the numbers belong to the RC that ships, which will be after M31.

**The daemon's memory keeps growing (finding d):** RSS 1160 MB at M21; 1637
MB on 2026-11-25 shortly after the install; **1984 MB** on 2026-11-27 (PID
113861, up since 2026-11-25 19:36:49), with a zombie `claude` child seen on
the 25th. Not investigated: owed to M31 or Phase 17.

## Step 8: an installed wake, reply and stop

The live check did it by voice (below: wake, reply, stop by barge-in, full
stop ×2). The synthetic one (`agentvoice wake-test` or a typed turn plus
`agentvoice interrupt`) was **not run**.

## Live checks, with the user (2026-11-25 to 2026-11-27, real shell, 963e738)

Passed, each seen by the user and confirmed in the journal or audit log:

- Real-shell keyboard walk (M29): Ctrl+1–9/0/PgUp/PgDn change page; Tab
  walks with visible focus; Space/Enter press; Ctrl+F "pause" then Enter
  lands on the control; Esc closes the overlay.
- Popup: no permission section (bug D); fixed size, the label cleared
  (bug B).
- DangerButton on Sora's Advanced "Start fresh": arm, Cancel, Esc and the
  timeout each disarm (M1/M16).
- Crew map (V-15, M9 stop 2): a link drawn by hand (jarvis-ajc → sora,
  ask); Hazel's typed crew ask allowed over it; refused, reason no-link in
  audit.log, after the user deleted it.
- Copy diagnostics (M26): no transcript, keys or paths. It does contain
  agent names and the headset's model (finding e).
- Codex live (Hazel): two typed turns and one spoken (codex 5.8 s).
- Cards in the real shell (M7, Phase 16): allow (card 4bfa1d4114f6, journal
  "allowed") and deny (2798fdfde834); the first card timed out at 45 s as
  designed. One mis-click allowed b8f9391d46e0 (the user confirmed it was
  theirs; finding c).
- Recent permission decisions on Sora's Advanced tab (M16).
- Voice (M2/M4): wake and reply; stop by barge-in; open mic by command
  (edges mode, at the end of a sentence); "stop listening to that song" not
  taken as a command; close mic, and "still listening" cleared on the same
  frame (bug K).
- Background work announced 7.98 s after it finished, with a question
  interleaved (M27, item 24).
- Full stop, twice (intended).
- Chat search by voice (M20): 10 hits, its own scope, a real chat described.
- S1, tools (M10, bug G): `gh` switched on for Sora only (Sora: yes; the
  others: no), then off.
- S2, skills (M11): minecraft off for Sora only (Sora: not in the list;
  Theo: has it), then back on.
- shell.json at the end matches the backup taken before the live checks
  (`~/agentvoice-notes/shell.json.m30-before-live-checks`, 0600) except
  `bargeFactor: 120`, which the user set and keeps.

Not done (owed to the rerun, not passed):

- S3, communal opt-out (M15, mango rule): stopped, because M31 rewrites the
  Communal page.
- S4, bug I level flip both ways (Theo keeps a word across trusted → edits
  → trusted).
- Bug C / V-23, the 90 s limit (the user skipped it).
- Bug J, the 20-minute open-mic chime count (only the chimes heard during
  the checks, all normal).
- Bug #10, a muted typed turn shows the HUD.
- Wake mode "both" by voice; Personality "Try it"; skill drag/move and Undo
  (M12, now being redesigned); note moves (M13); launch extras and
  `--debug` /proc (M17); quarantine (left out by the user's choice); light
  theme and HUD bottom/small/large in the real shell; a screen reader;
  Gemini, Antigravity, Copilot and endpoint targets (none configured here:
  fixture-only, plan Q15).

## The release blocker, and M31

Reported by the user during S3: "the entire process of delegating skills and
tools is not user friendly at all"; in scope now:

1. **Agent details → Tools & skills shows every agent and Communal, whatever
   agent is selected.** That is M12's lane design (this agent, Communal, each
   other agent read-only, Unused), working as built.
2. **Communal → Skills has nothing to act on here.** All 37 skills on this
   machine are the programs' own (`~/.claude/skills` for Theo and Sora,
   `~/.codex/skills` for Hazel). The communal folder and every agent's
   Agent Voice folder are empty, and the Communal tab lists only those, so
   it shows empty lanes and "Open the skills folder". There is no way to say
   which skills are communal. Only `omarchy-app` and `workmap-pages` are in
   all three agents.

M31, as the user decided (2026-11-27):

- Agent details → Tools & skills: only the selected agent, in two sections:
  "From communal", each with an Exclude for this agent (its `skillsOff`), and
  its own skills, each on/off. No other agents' lanes, no Unused.
- Communal → Skills: the communal skills at the top, each with Remove behind
  a confirmation; below them every available skill (all agents' native
  skills and Agent Voice's own) with a search field and a toggle each.
- A skill every agent already has is communal automatically.
- Communal is a grouping: an agent whose program lacks the skill does not
  get a copy, and the list names who does not have it.
- Removing an automatically communal skill puts it back under each agent's
  own skills, still on, and keeps it out of the automatic rule until it is
  added back. Nothing is switched off.
- Adding to Communal keeps its confirm (plan 7.3: a widening asks; the
  daemon refuses a widening move without `--confirm`).
- Out of scope, later: the cramped window, and the delegation flow for
  skills and tools as a whole.

The communal set will be a new setting, so it needs all three homes
(manifest, `runtime.DEFAULTS`, one page).

## Item ledger (master plan section 8, with the delivering commits)

Commits are each phase's own (not its notes commit); every one is an
ancestor of the installed 963e738. "Closing check" says what was run live in
this run; anything else is under "Not verified".

| Item | What | Phase | Delivered by |
|---|---|---|---|
| 1 | Commands inside a longer sentence | M4 | 9646c25, 72dc2e5, 72c9589 |
| 2 | Remove the popup's "what Claude Code may do" | M3 | 17af638, f52d9fc, d4c209f |
| 3 | Popup jumps around | M3 | 17af638, f52d9fc, d4c209f |
| 4 | Shell restarts whenever a file is saved | M0 | 832a97c, 48a8c73, 0d4e165 (gate passed in M0) |
| 5 | Chats as their own sidebar page | M18 | 7d8b9b1, c94490e |
| 6 | Easier chats: names, details, search, agents search, bubbles | M18, M19, M20 | 7d8b9b1, c94490e; 9e9f743; fc40f7c |
| 7 | Overview statistics (all five) | M21 | 952883c |
| 8 | Agents tab: cards, compact effort, chips, header strip, no duplicates | M5 | d8f2424, 735c1f6, 314d726 |
| 9 | Agent details: tabs instead of a drop-down | M6 | fa40d42, 98953fd, c4c67f9 |
| 10 | Personality: trait chips, hints, templates, Try it, meters | M6 | fa40d42, 98953fd, c4c67f9 |
| 11 | Tools & skills: detection, real controls, drag, Unused, Agent Voice skill | M10, M11, M12, M14 | 4494823, 92af969, 2a83bb1; 18c91f2, 9d2f825, cc4b7de, c912e54; cfe69f7, b8247f1; 49e527e, 6a3cd2b, ed12962, 2cd2bcd. **Reopened: the M31 blocker** |
| 12 | Notes in categories, movable | M13 | 051ecc3 |
| 13 | Conversation page polish | M24 (+M18, M2, M4) | d4ad068 (+7d8b9b1, 0be9572, 9646c25) |
| 14 | Agent details Advanced, warning + confirm everywhere | M16, M17, M1 | cc1845e, ba46488, 154bcf4, 0322b00; d7c3918; eba9ca0, ec8372b, 1034393 |
| 15 | Communal: shared tools, who gets it, preview, import, history, skills gap | M5, M10–M13, M15, M18 | bf3945d (M15) and the phases' commits above. **Skills part reopened: M31** |
| 16 | Crew map | M7, M8, M9 | 79d8bdc, 90315cd, c7d0983, 2f8af2d, b8f0c88, 152a109; 1e15005, 789761d, a973171, a64219f; 12f21f6, b68fcd1, 961ed64 |
| 17 | One design language | M1, page phases, M29 | eba9ca0 …; 6d453d3, 137f775 |
| 18 | Listening as a pipeline | M22, M23 | f0e2340; 071092e |
| 19 | Voice page | M25 | a2c0900. **Partial, deferred:** Whisper models beyond the three, until pinned (plan 9) |
| 20 | Display & privacy → Other settings | M3, M18, M21, M26 | 6fe6536 and the phases' commits above. **Partial, deferred:** changing key bindings from the page (plan 9) |
| 21 | About page | M26 | 6fe6536 |
| 22 | Diagnostics, updates, changelog, license; search; first run; keyboard + light theme; command caution; fix H early | M26, M28, M29, M4, M0 | 6fe6536; 8efa5e0; 6d453d3; 9646c25; 832a97c |
| 24 | Speak up when background work finishes | M27 | ce50b5f, 3bec4a3, ca3a9a4. **Partial, deferred:** an agent's own background tasks on Codex, Gemini, Antigravity, Copilot and endpoints (plan 9) |

| Bug | What | Phase | Delivered by | Closing check |
|---|---|---|---|---|
| A | Commands only fire when said alone | M4 | 9646c25, 72dc2e5, 72c9589 | live: open mic in a sentence (edges); a near-miss not taken |
| B | Popup bounces | M3 | 17af638, f52d9fc, d4c209f | live: fixed size |
| C | Turns cut at 30 s with no warning | M2, M24 | 0be9572, eb60501, a2deeb6; d4ad068 | **not verified** (skipped) |
| D | Old global permission section on the popup | M3 | 17af638 | live: gone |
| E | Duplicate tool sections at the bottom of Agents | M5 | d8f2424 | static: test_settings_pages |
| F | Voice library rows misalign | M25 | a2c0900 | preview (M25); real shell not verified |
| G | Tools & skills has no controls | M10, M11 | 4494823 …; 18c91f2 … | live: S1 and S2 |
| H | Shell restarts on any write in the plugin folder | M0 | 832a97c, 48a8c73, 0d4e165 | passed (M0 gate) |
| I | Open-mic chats lose earlier turns | M2 | 0be9572 | **not verified** (S4 not run) |
| J | Surprise "be-deep" chime | M2 | 0be9572 | **not verified** (20-minute count not run) |
| K | "Still listening" lingers after open mic off | M2 | 0be9572 | frame loop ≤ 200 ms (M2); live: cleared on the same frame |
| #10 | Muted typed turn shows no HUD | M2 | 0be9572 | **not verified** |
| Phase 16 | A Trusted agent can answer its own card | M7 | 79d8bdc … | tests (Desk.answer); live: allow and deny in the real shell |

## Found along the way

- (a) The feedback's example sentence fires only in `clause` mode, by design
  (Q4). `agentvoice commands` says open mic works "in its own clause" even in
  `edges` mode, which is misleading.
- (b) An utterance at 2026-11-25 21:09:49 (3.2 s, probably "close the mic"
  while open mic was already off) left no log line at all: neither
  `command:` nor `command not taken:`. A silent drop.
- (c) A second card appeared where Allow had just been clicked, which
  invites a habit click: that is how b8f9391d46e0 was allowed by mistake.
  UX, for Phase 17.
- (d) Daemon RSS growth: 1160 MB (M21) → 1637 MB → 1984 MB in two days of
  uptime.
- (e) Copy diagnostics includes agent names and the audio device's model.
  Not secret, but personal; say so beside the button or leave them out.
- (f) Theo acted on "stop listening to that song" by pausing media through
  the desktop tool. Correct as agent behaviour (it wasn't a command); noted
  because it looks like a command firing.
- (g) The user set `bargeFactor` 120 and keeps it.
- (i) **An intermittent test failure.** The pre-commit `./bin/agentvoice-check`
  on 2026-11-27 failed one test,
  `tests/test_history.py::test_a_failed_turn_records_why_and_never_the_message`
  (1 failed, 5336 passed), on code unchanged since M29 (5337 passed). It
  then passed alone three times, with its file (28 passed), and in a full
  run in the same order (5337 passed, 383.67 s). The check keeps only the
  last 20 lines of pytest output, so the traceback was lost. Reading the
  test and `Daemon.answer` found no clock dependency. Suspects: state left
  on the shared `daemon` fixture by an earlier test (`_interrupt` set, or
  a thread still running), which would leave zero rows or an empty
  reply. Owed: find it in M31, and make the check print the failing
  test's traceback, not just the tail.
- (h) The first run's `shell.json.before-M30` backup is mode 0644. It holds
  settings, not keys, but backups should be 0600 like this run's.

## Known limits, for Phase 17

- **A terminal or program an agent opens is a child of agentvoice.service
  and dies on every service restart** (deploy, install, the panel toggle).
  That killed the first M30 run. Workaround: launch it in its own scope
  (`systemd-run --user --scope …`). A fix belongs in how the desktop tool
  launches things.
- The Communal and agent skills screens (the M31 blocker), and the cramped
  window for skills and tools delegation as a whole (later, after M31).
- Daemon memory growth (finding d).

## Not verified

Everything under "Not done" in the live checks above, plus:

- Steps 6 (strict, NO_SKIPS and box runs), 9 (CODEBASE.md, a status note,
  phase-17-plan.md, the entry gate) and 10 (hand-off): not done; for the
  rerun.
- Section 7.7 downgrade rehearsal on copies: not done.
- Step 8's synthetic wake, reply and stop: not run (the live one passed).
- Codex review: owed for M12–M29 and for M30 itself.
- Every "Not verified" in phase12notes.md to phase16notes.md and
  phaseM0notes.md to phaseM29notes.md is still owed, except the items listed
  as passed above. Counts of the bullets in each section: 12: 4, 13: 5,
  14: 6, 15: 7, 16: 8; M0: 3, M1: 6, M2: 6, M3: 6, M4: 4, M5: 5, M6: 6,
  M7: 9, M8: 10, M9: 8, M10: 8, M11: 8, M12: 7, M13: 7, M14: 8, M15: 8,
  M16: 8, M17: 7, M18: 8, M19: 6, M20: 8, M21: 6, M22: 7, M23: 8, M24: 10,
  M25: 9, M26: 9, M27: 10, M28: 7, M29: 6. The rerun copies them into its
  hand-off.

## Going back

Nothing to undo: this run wrote only these notes, a memory file outside the
repo, scratch under /tmp, and `~/agentvoice-notes/shell.json.m30-before-live-checks`.
The installed build is 963e738, deployed by the first run; the way back from
it is `bin/agentvoice-deploy 137f775` (deploys.log).

## Next

1. M31, the skills redesign, on its own branch from `phase-m30`: tests, the
   two Codex passes, a deploy and install, and the user's live check of both
   screens.
2. Then M30 again: step 3 to the M31 result, deploy and install from a
   clean checkout (from a terminal in its own scope), steps 5 to 10, the
   owed guard-set review, the live checks listed as not done here, and the
   checks M31 touched redone (S2, S3, the skills part of G).
