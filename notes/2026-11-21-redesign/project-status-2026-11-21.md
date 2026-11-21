# Agent Voice: project status, 2026-11-21

Repo: `~/.config/omarchy/plugins/duaneoca.agentvoice`. Report written about 01:05 MST.
Research only. Nothing in the repo was changed, and no service or shell was
restarted. Git was read with `GIT_OPTIONAL_LOCKS=0` so not even the index was
touched. The test run used a copy in `/tmp`.

---

## 1. Git

### Where things stand

- **Current branch:** `orders-guard`
- **HEAD:** `92c71ff` (2026-11-21 00:11:17), "Orders guard: ask before any write to the agents' orders, even at Trusted"
- **Remotes:**
  - `origin` = `github.com/duaneoca/agent-voice` (upstream). It has only `main` at `7dd52b2` (2026-10-21), plus `refs/pull/1/head` (eafbcf7), a third-party PR that was closed on 2026-10-21. **None of this work is on origin.**
  - `fork` = `github.com/bluetooth47/agent-voice` (the user's fork). `git ls-remote fork` was checked live. **Every local branch is on fork at exactly the same commit.** No branch exists only locally, and no local branch is ahead of or behind its fork copy.
- No stashes, and one worktree.

### Local branches (newest first)

| Branch | Commit | Date | Last commit | Upstream config |
|---|---|---|---|---|
| **orders-guard** (HEAD) | 92c71ff | 11-21 00:11 | Orders guard: ask before any write to the agents' orders | none (pushed) |
| phase-16 | 5d29e33 | 11-20 20:13 | Phase 16: notes | none (pushed) |
| phase-15 | 687680a | 11-20 14:39 | Phase 15: notes | none (pushed) |
| phase-14 | f1b8c13 | 11-20 05:39 | Phase 14: notes (Codex's second pass, Hazel's live turn) | none (pushed) |
| phase-13 | 2e2fa7b | 11-20 00:39 | Phase 13: notes | none (pushed) |
| phase-12 | 0a8944e | 11-19 21:41 | Phase 12: fix Codex review findings, notes | none (pushed) |
| phase-11 | e467d99 | 11-19 20:04 | Phases 10-11: fix Codex review findings | none (pushed) |
| phase-10 | da49bed | 11-19 17:16 | Phase 10: migrate instructions into agent folders | none (pushed) |
| phase-9 | f76c9e1 | 11-19 16:28 | Phase 9: agent folders storage, hook rules, Codex session fix | fork/phase-9 |
| phase-8 | ecbaffe | 11-19 15:25 | Phase 8: record the user's answers | fork/phase-8 |
| dev | 2eeb919 | 11-18 17:40 | Mute closes the microphone, not the chat | fork/dev |
| latency-2 | ece1c3b | 11-18 16:49 | Main agent picks its program; Codex models without the daemon | fork/latency-2 |
| main | e331d31 | 11-18 15:05 | Fixes from the full test run | **origin/main** (35 commits ahead of it) |
| test-fixes | e331d31 | 11-18 15:05 | (same as main) | none (pushed) |
| phase-g | 9e1918f | 11-18 14:12 | Editor and browser tools, Hyprland Lua dispatch (Phase G) | none (pushed) |
| phase-f | b571a5a | 11-18 13:50 | Endpoints, desktop tools, Omarchy skill (Phase F) | none (pushed) |
| phase-e | 1c75562 | 11-18 00:47 | Open mic and terminal handoff | none (pushed) |
| phase-d | 0a05908 | 11-18 00:33 | Progress talk while it works | none (pushed) |
| phase-c | cde8eb3 | 11-17 22:45 | Saved conversations | none (pushed) |
| phase-b | 39de35f | 11-17 22:03 | Hold a stop during PortAudio's start | none (pushed) |
| voice-latency-and-conversation | 919c4c4 | 11-17 14:32 | Spoken "goodbye" / "full stop" | fork/voice-latency-and-conversation |

`fork/HEAD` (the fork's default branch) points at `main` = `e331d31`.

### How the branches chain

The history is **one straight line with no merges**. Each branch is an
ancestor of the next one, and none is behind its predecessor:

```
origin/main 7dd52b2
 +21  voice-latency-and-conversation 919c4c4
 +7   phase-b 39de35f          (Phase A commits 5d6392a..af2fee1 sit here, no phase-a branch)
 +2   phase-c cde8eb3
 +1   phase-d 0a05908
 +1   phase-e 1c75562
 +1   phase-f b571a5a
 +1   phase-g 9e1918f
 +1   main = test-fixes e331d31  (= fork/main)
 +3   latency-2 ece1c3b
 +4   dev 2eeb919
 +2   phase-8 ecbaffe
 +1   phase-9 f76c9e1
 +1   phase-10 da49bed
 +2   phase-11 e467d99
 +2   phase-12 0a8944e
 +7   phase-13 2e2fa7b
 +6   phase-14 f1b8c13
 +5   phase-15 687680a
 +5   phase-16 5d29e33
 +1   orders-guard 92c71ff       (HEAD)
```

There are 74 commits between origin/main and HEAD. `orders-guard` is 1 commit
ahead of `phase-16`, 32 ahead of `dev` (104 files, +28.3k/-0.3k lines) and
39 ahead of `main`/`fork/main`. **Nothing from Phases 8 to 16 or orders-guard
has been merged back into `dev` or `main`.** The newest work exists only as
the tip of the stack.

---

## 2. Working tree

`git status` shows one modified file and four untracked ones. **There are no
uncommitted code changes.**

### Modified (tracked)

- `testresults.md`: one new row, bug **#10** (user, live 2026-11-19, medium, open). With the microphone muted, replies to turns typed in the Claude terminal are still spoken, but the HUD popup never appears and the panel's "last heard" and "speaking" chip go stale. This one row is why the install stamp reads `-dirty`.

### Untracked planning notes

| File | Written | What it is | Copy elsewhere? |
|---|---|---|---|
| `agents-plan.md` | 11-18 22:36 | Plan A for agent folders (Phases 8-16). Superseded by `merged-plan.md` | Yes, identical in `~/Documents/agent-reconfiguration-plan/` |
| `CODEBASE.md` | 11-18 22:43 | Codebase summary for agents (written against dev 2eeb919) | Yes, identical in the same folder |
| `bugs-notes.md` | 11-19 00:30 | 4 bugs (open-mic chat losing turns, the surprise "be-deep" chime, the shell restarting on any file save in the plugin folder, the open-mic display lingering) | No file copy, but all 4 are carried into `~/agentvoice-notes/feedback-notes-2026-11-21.md` §23 H-K |
| `voice-commands-notes.md` | 11-19 00:16 | Notes for a voice-commands skill and a trigger-word list. Not built | **No copy anywhere** |

### Ignored (not part of git status)

These are local test caches from the user's own run at about 00:04-00:07:
`.pytest_cache/`, `tests/.pytest_cache/`, and `__pycache__/` in `daemon/`,
`daemon/adapters/`, `tests/`, `bench/` and `bench/narration/`.

### Tracked planning docs (all committed)

`plan.md`, `latencyplan.md`, `merged-plan.md`, `merge-decisions.md`,
`testplan.md`, `testresults.md`, and `phase1notes.md` to `phase16notes.md`.
`merged-plan.md` and `merge-decisions.md` are byte-identical to the copies in
`~/Documents/agent-reconfiguration-plan/plans/`.

---

## 3. What is installed and running

- **Installed copy:** `~/.local/share/agentvoice/app`, written at **2026-11-21 00:12:20**.
- **Stamp:** `app/VERSION` = `0.2.0 (92c71ff-dirty)`. The service banner at startup says the same: `build 0.2.0 (92c71ff-dirty)`.
- **File comparison:** I extracted `92c71ff` with `git archive` and ran `diff -r` against the installed `daemon/ bin/ desktop/ install.sh requirements*.txt models.lock`, ignoring `__pycache__` and `VERSION`. They are **identical**.
  - Compared with `5d29e33` (phase-16) and `c47aae1` (the build the runner installed), only `daemon/adapters/claude_code.py` and `daemon/permission_hook.py` differ. Those are exactly the two code files the orders-guard commit changed.
  - The `-dirty` flag comes only from the `testresults.md` row. No installed file is affected.
- **Service:** `agentvoice.service` has been active since **00:12:23**, 3 s after the install (PID 1922399). So the running daemon is the orders-guard build.
  - The live `claude -p` child carries the new PreToolUse hook (`Bash|Write|Edit|MultiEdit|NotebookEdit` → `permission_hook.py claude`, `onFailure: block`) even though the project is Trusted. That hook is the orders guard at work.
  - The unit shows as "disabled" (not started at login by systemd). That is how install.sh sets it up.
- **Shell (QML):** quickshell started 2026-11-20 20:03:09. That is after the last QML commit (`c47aae1`, 20:02:54) and after the newest QML file (`pages/AgentsPage.qml`, 19:59). orders-guard changed no QML, so **the shell is showing current QML.**
- **Verdict:** **orders-guard (92c71ff) IS installed and running.** The memory note "pushed to fork, NOT installed" is out of date. The user's install at about 00:12 was this commit, made one minute after it was committed at 00:11:17.
- **Settings seen live:** Theo has `mainTools.browser = off`, and Sora has `notesWrite = deny`.
  - `maxUtteranceMs = "90000"` is stored as a string. `get_int` converts it, so it works.
  - The journal shows "hit max_utterance_ms" at 30 s intervals until 00:36. Settings were updated at 00:39, and there have been 0 hits since, so the 90 s workaround is in effect.
  - Hazel's agent folder is `agents/jarvis-ajc` (her stable id from before the rename). That is expected under plan 7c, just confusing to read.

---

## 4. Plans and phases

### plan.md (Phases A-G, 2026-11-17): done

All items were built:

| Phase | Items | Where |
|---|---|---|
| A | bar click, wake Advanced tab, agent on/off | commits on the chain before phase-b |
| B | adaptive gate, accurate transcript | `phase-b` |
| C | display names / ids, saved chats | `phase-c`, 100e0c0 + cde8eb3 |
| D | progress talk | `phase-d` |
| E | open mic, terminal handoff | `phase-e` |
| F | endpoints, desktop tools, Omarchy skill | `phase-f` |
| G | editor and browser tools, second-mouse spike | `phase-g` |

Two items were dropped on purpose (timed pause, "think hard" routing).
`latencyplan.md` work landed in `latency-2`. `testplan.md` was run against
9e1918f; its fixes are in e331d31. Of the 10 rows in `testresults.md`, only
#10 is still open.

### merged-plan.md (agent folders, communal folder, collaboration)

| Phase | Status | Record | What is still open |
|---|---|---|---|
| 8 Spec / baseline | Done 11-19 | phase8notes, FINDINGS §33 | none |
| 9 agentfs storage | Done 11-19 | phase9notes | none |
| 10 Migration | Done 11-19 | phase10notes | Codex review later done in e467d99 |
| 11 Prompt assembly | Done 11-19 | phase11notes, §35 | none |
| 12 Agent details + Communal pages | Built 11-19 | phase12notes | keyboard walk in the real shell; the spoken personality check (the user's) |
| 13 Tools + skills | Built 11-19 | phase13notes, §36 | Codex S run and a Codex turn through the skills index (quota); keyboard walk |
| 14 Notes | Built 11-20 (runner) | phase14notes, §37 | answering a card; keyboard walk; `--guard` live |
| 15 Collaboration runtime | Built 11-20 (runner) | phase15notes, §38 | spoken passes and spoken stop; Send clicked in the real shell; endpoint target; passing back to the owner's session |
| 16 Agent-started collaboration | Built 11-20 (runner) | phase16notes, §39 | voice yes/no on the card (design question); bare "stop" during an announcement; Gemini target live |
| (extra) orders-guard | committed + installed 11-21 | commit message only | not in merged-plan; no notes file |
| **17 Verification sweep + release decision** | **Not started** | no `phase17notes.md`, no branch | everything (below) |

Every live check in 14-16 used typed turns, not voice. Nothing new was
clicked in the real shell, only in the preview.

### Open questions phase16notes leaves for the user

- Should voice yes/no be allowed in the follow-up window, or require the wake word, or stay on screen only?
- Should card answers go over a socket before release? Today a Trusted agent with a shell can answer its own card.
- Should the announcement open a stop-only window?
- Codex side questions take 5.5-7.2 s, over the 5 s budget. Say so on screen, or accept it?
- Smaller items:
  - messages are lost when the daemon restarts (a new signing key);
  - "timeout" never appears in the audit log for a collaboration card;
  - some review items were deferred.

### What remains (Phase 17 and after)

- **Phase 17, by the user.** It builds nothing new. It runs V-01 to V-12 against an installed release candidate:
  - V-01 code: check, strict, no-skips, mutation, fuzz, 10-min soak, /code-review
  - V-02 install, migration and going back (box run)
  - V-03 every backend
  - V-04 desktop and browser tools
  - V-05 folders and notes edge cases
  - V-06 collaboration matrix
  - V-07 injection red-team
  - V-08 voice and hardware
  - V-09 settings overlay
  - V-10 UX walkthrough of 11 tasks
  - V-11 performance against the Phase 8 baseline
  - V-12 privacy and recovery
  - Output: `phase17notes.md` (findings by severity, coverage matrix, README update) and a release decision.
- **A release revision must be chosen first.** Phase 17 says it runs "against the build installed from the revision meant for release". Today that would be `orders-guard` 92c71ff, which sits outside both `dev` and `main`.
- **Backlog, not built:**
  - `testresults.md` #10;
  - `bugs-notes.md` 1-4;
  - `voice-commands-notes.md`;
  - `~/agentvoice-notes/feedback-notes-2026-11-21.md`: 22 items plus known bugs A-K, including the shell restarting on any file save in the plugin folder;
  - merged-plan's "Deferred, on purpose" list (browser settings UI, per-note audiences, sandbox for Trusted backends, and so on).

---

## 5. Test and check health

- `./bin/agentvoice-check` **does** write inside the folder: its pytest step creates `.pytest_cache` and `__pycache__`. So I did not run it in place.
- Instead I copied the whole repo, including `.git`, to `/tmp/avstatus-check` without caches, at 92c71ff plus the working-tree notes. I ran the full script there with `PYTHONDONTWRITEBYTECODE=1`.
- **Result: all green.**
  - 14 of 14 static checks ok. This covers: schema keys drawn and defaulted, Python and shell syntax, symlinks, manifest, heavy imports, nested bash -c, qmldir, orphaned comments, pinned models, numeric min/max/step, daemon states drawn, and qmllint property references.
  - The installer-in-a-box was not run (opt-in with `AGENTVOICE_BOX=1`).
  - **Tests: 2790 passed in 133 s.** The runner's Phase 16 count was 2790, so orders-guard only adjusted existing tests.
- Afterwards I confirmed that nothing in the plugin folder had changed in the 20 minutes before.
- Not run: the bare-runner job (`AGENTVOICE_STRICT=1`), the `full` job (`AGENTVOICE_NO_SKIPS=1`) and the box. All three are part of Phase 17's V-01 and V-02.

---

## 6. Anything odd

1. **Stale memory.** The roadmap memory says orders-guard is "NOT installed". It is installed (00:12:20) and running (00:12:23).
2. **No integration branch has the new work.** `dev` (2eeb919) and `main`/`fork/main` (e331d31) are 32 and 39 commits behind HEAD. The fork's default branch shows the state of 11-18 afternoon. orders-guard is a one-off branch on top of phase-16 with no plan entry or notes file.
3. **Local `main` tracks `origin/main`.** A bare `git push` while on `main` would target upstream origin, which goes against the "never push origin" rule. `push.default` and `remote.pushDefault` are unset. Other branches track fork or have no upstream.
4. **Uncommitted notes at risk.**
   - `voice-commands-notes.md` exists only in the plugin folder.
   - The `testresults.md` bug #10 row is uncommitted.
   - Both would be lost to `git clean`, `git checkout -f` or `omarchy plugin remove` (an rm -rf).
   - `agents-plan.md` and `CODEBASE.md` have identical backups in `~/Documents/agent-reconfiguration-plan/`.
5. **Leftover runner.** `agentvoice-phase-runner.service` finished cleanly (exit 0, 2026-11-20 20:13:20, state.json `"finished"`). However, it is still **enabled** (`WantedBy=default.target`), so it starts at every login.
   - It should skip all three phases, because phase-14/15/16 carry their notes. It would then send another "all done, Phase 17 is yours" notification.
   - It would only redo work if those branches or notes went away.
   - Logs and state: `~/Documents/agent-reconfiguration-plan/phase-runner/` (logs about 15 MB).
6. **Install stamp says `-dirty`.** This is cosmetic: it comes only from the `testresults.md` row. The installed code equals 92c71ff.
7. **Many old branches.** `phase-b` … `phase-g`, `test-fixes` (= main), `latency-2` and `voice-latency-and-conversation` are all strict ancestors of HEAD. They are harmless but stale, and could be pruned once something is merged.
8. **The folder changed at 00:26 with no file left behind.** The plugin folder's own mtime is 00:26:08, but no file in it is that new. Something created and removed a temp entry. That fits the "shell restarts on any write in the plugin folder" bug.
9. **Minor.** Hazel's id is the old `jarvis-ajc`. The Phase 10 "Codex review still owed" note in merged-plan was later resolved by e467d99, but the text was not updated.

---

## What this means

Everything is safely on the fork. All 21 local branches match the fork
exactly, nothing is local-only, and nothing went to upstream. The work is one
straight stack of commits, and its tip, `orders-guard` (92c71ff), is what is
checked out, installed and running right now. The install at 00:12 was that
commit, so the memory note saying it was not installed is out of date. The
code is healthy: every check passes and all 2790 tests pass.

The agent-folders plan is built through Phase 16. What is left is Phase 17,
the user's full verification sweep and release decision. Before starting it,
pick the release revision (most likely orders-guard) and consider bringing it
into `dev`/`main`, which still sit two days back.

Small housekeeping items:
- commit or back up `voice-commands-notes.md` and the new bug row;
- disable the finished phase-runner service;
- be careful that `main` still pushes to upstream origin by default.
