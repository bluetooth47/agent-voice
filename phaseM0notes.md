# Phase M0: housekeeping, and bug H first

Written 2026-11-21, with the user at the desk. Branch `phase-m0`, cut from
`dev` at fa319ba (orders-guard plus a notes commit). Pushed to
`fork/phase-m0` only. Model: Claude Opus 5.5, high, interactive.

Deployed: yes, through the new `bin/agentvoice-deploy` into the new
symlinked layout (below). Installed: **no**. The daemon code is unchanged
since 92c71ff (`git diff 92c71ff fa319ba -- daemon` is empty, and the
installed `app/daemon` matches), so the running daemon is 92c71ff's.

`./bin/agentvoice-check`: green, **2824 tests** (was 2790; +34 in
`tests/test_deploy.py`), and the new last line "the check wrote nothing in
the tree: ok". Box: not run (`install.sh` did not change).

## Answers taken at the start (section 11)

- **Q1:** yes, both. The dev clone is at `~/Projects/agent-voice`, and Theo's
  project folder points there (`projectDir`, set with the user's OK; shell.json
  backup in `~/agentvoice-notes/m0/shell.json.before-projectDir`).
- **Q14:** yes. The runner may deploy and run `install.sh` at the end of each
  phase once the daemon is idle. Shell restarts wait for the stop points.
- Step 2's session log: background only (the logger ran for all of M0).
- Symlink trial: plugin reloads were OK; each `omarchy-restart-shell` was
  asked for separately (two were run, both approved).

Questions 1 and 14 are marked answered in `notes/master-plan.md` and in
`~/agentvoice-notes/master-plan.md`.

## What was built

1. **Safety net.** `~/agentvoice-notes/backup-2026-11-21.bundle`, all 46
   refs, verified.
2. **Before picture** (counts below). Tools: `~/agentvoice-notes/m0/watch.py`
   runs Omarchy's exact `inotifywait` command with its exact
   `localPluginIdForPath` filter and logs each event as TRIGGER or ignored;
   `count.py` counts triggers and estimates reloads (bursts split by the
   shell's 150 ms debounce). Logs are in `~/agentvoice-notes/m0/`.
3. **`main`.** Fast-forwarded e331d31 → fa319ba, pushed to `fork` (not
   forced), now tracking `fork/main`. In the plugin repo `origin`'s push URL
   is `DISABLED-never-push-origin` and `remote.pushDefault` is `fork`; after
   the cutover that remote is renamed `upstream` (below).
4. **Dev clone** at `~/Projects/agent-voice`, cloned from the fork with the
   remote named `fork`, plus `upstream` (duaneoca) with its push URL disabled
   and `remote.pushDefault=fork`. The plan is at `notes/master-plan.md`.
   `master_runner.py --dry-run` finds it there
   (`plan /home/null/Projects/agent-voice/notes/master-plan.md`) and lists
   M1–M29 with their models.
5. **The check writes nothing in the tree.** `bin/agentvoice-check` exports
   `PYTHONDONTWRITEBYTECODE=1` before its interpreter probe, runs pytest with
   `-p no:cacheprovider`, and ends with check 14 (the plan's "static check
   15": the fifteenth line of output), which compares NUL-separated relative
   path lists taken before and after, kept outside the tree, plus a marker
   file. It reports new, deleted and rewritten files, and files created and
   removed during the run (through their folder's changed time). Mutations:
   removing the two settings turns it red, naming `.pytest_cache` and the
   `__pycache__` files; an injected overwrite, deletion and transient file
   are all reported.
6. **`bin/agentvoice-deploy`.** Refuses: running from inside the plugins
   folder (script or working directory); a dirty clone (untracked files
   count, whatever `status.showUntrackedFiles` says); a target that is not
   its own checkout of `duaneoca.agentvoice` (a subfolder of another repo,
   the clone, another plugin); local edits in the target; untracked files
   where `install.sh` copies whole folders; a red check. The check is strict
   and runs on exactly the commit, in a fresh worktree under `~/.cache`.
   Then it locks, rechecks, fetches, checks out detached with
   `--no-overwrite-ignore`, logs to `~/.local/state/agentvoice/deploys.log`,
   prints the way back and the QML notice, and installs only on request once
   the daemon is clearly idle. Status goes on stdin, never argv. Anything
   unreadable counts as busy, and a stopped service counts as idle. 34 tests
   with recording stubs; three mutations (own-checkout guard, idle predicate,
   worktree) each turn tests red.
7. **Symlink trial, then adopted.** Throwaway plugin `local.m0-symtest`
   (outside the tree, symlinked in): discovered and listed; 20 writes through
   either path gave 0 events; `omarchy plugin update` refused (no `origin`:
   "fetch failed", nothing changed); `omarchy plugin remove` unlinked it and
   kept the checkout. Took about 15 minutes. Then, with the user's OK:
   `mv -T ~/.config/omarchy/plugins/duaneoca.agentvoice
   ~/.local/share/agentvoice-plugin && ln -s …` (same Btrfs subvolume, so an
   atomic rename; 2 events, 1 reload), and in the checkout `git remote rename
   origin upstream`. The popup and Settings load through the link, and
   `install.sh` resolves its `ROOT` with `readlink -f`, so it installs from
   the checkout (read, not run: see Not verified). The checkout sits beside
   `~/.local/share/agentvoice`, not inside it, so an uninstall's `rm -rf` of
   that tree's named parts never reaches it.
8. **Orders-guard recorded** (below). merged-plan's stale Phase 10 line is
   corrected: Codex did review Phases 10 and 11 together, with fixes in
   e467d99.
9. **Docs.** CLAUDE.md has a new "Where to work" section (the watcher's file
   and lines, the symlink, deploy, pushes, the stale-watch note); CODEBASE.md
   (disk table, workflow, state, known issues; also copied to
   `~/agentvoice-notes/CODEBASE.md`); CONTRIBUTING.md; phase-17-plan's bug H
   box (`~/agentvoice-notes`); the assistant memory notes.
10. **Baseline**: FINDINGS §40 and `bench/baselines/m0.json` (S, J, the
    automatic wake test). S is provisional (Open issues).

## Orders-guard (92c71ff), which had no notes file

What it guards: a write to the agents' orders is asked about at **every**
level, Trusted included, with no "allow all in this chat" option. The orders
are the agent folders (`AGENTS_DIR`), communal rules and skills
(`COMMUNAL_DIR`), the generated agent plugins (`agent-plugins/`), the
Omarchy skill (`omarchy-skill/`), the config folder (`~/.config/agentvoice`)
and `~/.config/omarchy/shell.json` (`permission_hook._orders_dirs`). To make
that possible a trusted Claude agent now gets the hook on Bash and the edit
tools (plus the browser when it is on).

**The Bash caveat.** Bash is judged on the command's text only
(`_orders_spellings`): the absolute path, the resolved path, the part from
the home folder on (so `~`, `$HOME` and `${HOME}` forms match), and
`bar set duaneoca.agentvoice`. It catches the plain case. A command that
builds the path (a variable, `cd` and then a relative path, a script, a
`python -c`) is not seen.

**Trusted Codex has no hook.** A Codex agent at Trusted runs with
`--approve-for-me` and no guard (FINDINGS §33's matrix), so the orders-guard
does not apply to it at all. Hazel is a Codex agent at Trusted.

## Shared files touched, and where

None of the big shared files. Changed: `bin/agentvoice-check` (top: bytecode
setting and snapshot; pytest flag; check 14 at the end), new
`bin/agentvoice-deploy`, new `tests/test_deploy.py`, `CLAUDE.md`,
`CODEBASE.md`, `CONTRIBUTING.md`, `merged-plan.md` (one paragraph),
`bench/FINDINGS.md` (§40), new `bench/baselines/m0.json`, new
`notes/master-plan.md`. No product code, no settings keys.

## Measured: the bug H gate

**Before.**
- One full check run on a scratch copy, under Omarchy's filter: **478
  events, 14 triggers** (`.pytest_cache`, pytest's `pytest-cache-files-*`),
  **about 1 reload**.
- The previous shell's log (2026-11-20 20:03 to 2026-11-21 18:05) has **507
  "Local plugin changed, reloading"** lines, 445 of them in the 01:00 hour
  of 2026-11-21, when agents worked in the plugin folder.
- Who writes in the real folder during an ordinary session: the logger ran
  through all of M0 (16:09–18:22, with Theo in use). Every trigger was one of
  my own steps, and every other event was under `.git/` from my own git
  commands. **The daemon and the UI write nothing there**, so nothing joined
  this phase for that reason.

**After** (quickshell PID before → after each):

| Check | Events (triggers) | quickshell | Result |
|---|---|---|---|
| In the clone: full check run, 19 edits (Markdown, Python, QML, 3 atomic saves, swap file, two caches made and removed, `sed -i`, bytecode) and a commit, then a 20th edit | **0 (0)** | 207740 → 207740 | pass |
| Same again, 20 edits and a commit, with Settings open (opened by `omarchy-shell shell summon`) | **0 (0)** | 251402 → 251402 | pass; Settings still open in the screenshots before and after |
| Deploy back to the older 0d4e165 (the way back) through the symlink | **0 (0)** | 207740 → 207740 | pass: no reload at all |
| First deploy (53ea2b0, a harmless QML edit), before the first restart | 9 triggers, ~1 reload | 1370488 → 1370488 | expected: the old watcher still watched the moved folder (Found along the way) |
| After restart 1: the QML edit visible | — | → 207740 | user saw "Agent Voice · M0 test" |
| After restart 2: restored | — | → 251402 | screenshot: "Agent Voice" (opened over IPC; the user had stepped away) |
| `local.vpn-hub`, `io.voxtype.settings` | — | — | load after both restarts; the user checked both after restart 1 |
| Synthetic reply | — | — | `agentvoice type sora` with "Reply with the single word OK": "OK", first token 1473 ms |
| Synthetic wake | — | — | `agentvoice wake-test auto`: 162 clips, Theo 14/24, Sora 21/24, Hazel 19/24, full stop 8/12, 1 false wake in 78 distractors |
| `git rev-parse dev main fork/dev fork/main` | — | — | see the end of this file |
| `git push --dry-run origin main` (plugin repo, before the rename) | — | — | fails, exit 128 ("DISABLED-never-push-origin"); after the rename there is no `origin`, and `upstream` fails the same way |

The first "Settings stays open" try failed: Settings closed. The shell
logged **no reload** (0 "Local plugin changed" lines, against 507 in the
previous shell). The overlay closes on a click outside it by design
(`Settings.qml`, "Click-away closes"), and answering my question in the
terminal needed a click away. The retest above, with nobody touching
anything, passed.

**Baseline**: FINDINGS §40. In short: S Sora warm 1.62s median (provisional,
under load), J Theo 9.7s median over 105 real turns, wake test as above.

## Different from the plan, and why

- **Symlink adopted**, so a deploy gives 0 reloads, not 1. The plan expected
  "none if the symlink was adopted".
- **The deploy checkout has no `origin`** (renamed `upstream`), so `omarchy
  plugin update` refuses at the fetch, not later.
- **Codex: one review pass, not two.** The single pass cost 56.27 credits
  out of the round's shared 500, so the second pass (of the fix commits) was
  not run. **Second review: owed.**
- The plan copy in `notes/` was left out of `REVIEW.diff` (2,495 lines of
  prose) to save credits.
- The deploy's strict check keeps the inherited `TMPDIR`. Codex suggested a
  scratch one, which turned four tests red (Found along the way); it now
  switches only when `TMPDIR` is inside the plugins folder.

## Found along the way

- **Moving a watched folder leaves the old watcher on it.** After the
  cutover, the running shell's `inotifywait` still watched the moved
  folder's inodes and reported writes in the deploy checkout under the old
  path (9 triggers on the first deploy). A shell restart ends it; the new
  watcher does not follow the symlink (0 events since). Written in
  CLAUDE.md.
- **Omarchy's watcher reaper kills any `inotifywait` on the plugins folder**
  at a shell restart, mine included. The logger had to be restarted twice.
- **Four `test_tools_skills` tests depend on `TMPDIR`'s length**: their
  fixtures' paths land in budgeted skill-index text, so a long `TMPDIR`
  pushes a skill out ("and 1 more, not listed here").
- **`test_permission_hook` failed once** (`test_read_only_tools_are_never_
  asked_about`: Read of `/etc/hostname` got "deny") when pytest ran with
  `/tmp` as its working directory and rootdir; it passed alone and in every
  run from the repo root. Its `clean_pending` fixture also deletes every file
  in the **live** `$XDG_RUNTIME_DIR/agentvoice/permissions`, so a test run can
  delete a real pending permission request.
- **One check run went red** with bytecode under `daemon/` in the clone,
  shortly after Theo answered a turn with the clone as his project folder.
  The suite alone writes nothing (three clean runs). Check 14 did its job,
  but a runner phase and Theo share the clone.
- **`turn_latency.py --build`** cannot match a `-dirty` build line, so it
  found no turns for `92c71ff-dirty`.
- `omarchy-shell shell summon duaneoca.agentvoice '{}'` and `qs -p
  /usr/share/omarchy/shell ipc call shell hide duaneoca.agentvoice` open and
  close Settings, and `ipc call duaneoca.agentvoice open|close` the popup,
  with no pointer. `ydotool` key presses failed here (exit 2).

## Not verified

- **`install.sh` run through the symlink** (its `ROOT` resolves with
  `readlink -f`, read from the code; no install was needed in M0). The
  runner's first `agentvoice-deploy --install` exercises it.
- After restart 2, the restored title was checked by my screenshot, not by
  the user.
- A spoken wake by the user after the cutover: only the synthetic test was
  run.

## Going back

- **To the old real folder:** `rm ~/.config/omarchy/plugins/duaneoca.agentvoice
  && mv ~/.local/share/agentvoice-plugin
  ~/.config/omarchy/plugins/duaneoca.agentvoice` (one reload), optionally
  `git -C … remote rename upstream origin`.
- **To an older commit:** `bin/agentvoice-deploy <sha>` from the clone (tried:
  53ea2b0 → 0d4e165).
- **Git state before M0:** every ref is in
  `~/agentvoice-notes/backup-2026-11-21.bundle`; `main` was e331d31.
- **Theo's project folder:** `omarchy bar set duaneoca.agentvoice projectDir
  '""' --json`, or restore the shell.json backup.
- No data changed.

## Open issues, for the next phase

1. **Sora's S baseline is provisional**: warm 1.62s against 0.64–0.76s in §33
   to §39, measured at load average ~6. Before a phase gates on it, rerun it
   on a quiet machine, interleaved with a §39 build if the gap stays.
2. **Codex credits: 443.73 left of the 500** for M1–M29 (M0 used 56.27 from
   the same pool), about 15.3 per phase. The weekly Codex window was at
   100%, so every call spends credits.
3. **Theo and the runner share the clone.** A voice turn that writes there
   (bytecode, an edit) can turn a phase's check red or mix into its commit.
   Options: don't give Theo code work during runner phases, or give the
   runner its own worktree.
4. Codex findings left open: checkout is not atomic (with the symlink a
   half-done checkout reloads nothing, and the shell reads it only at its
   next start); a voice turn can still start while `install.sh` runs (that
   needs the daemon to stop taking turns first); `AGENTVOICE_BOX=1` would
   mount an empty `/tmp` over a worktree there (the deploy never sets BOX).
5. `test_tools_skills`' `TMPDIR`-length dependence, `test_permission_hook`'s
   cwd sensitivity and its live `permissions` cleanup, and
   `turn_latency.py --build` with `-dirty`: small test and bench fixes,
   M1 or M2.
6. The second Codex review of M0 is owed.

## Codex credits used

**56.27** (balance 500.00 → 443.73, read from the session log's
`rate_limits.credits.balance`): one review pass of `agentvoice-deploy`, the
check change and the tests, 99,034 tokens, `gpt-6.2-astra`, run on a
read-only copy (the sandbox still fails: "bwrap: Can't open source /").
The clone's and the plugin folder's HEAD and status were the same before
and after. Second pass: not run (owed).

## Live checklist: what was said, what happened

- Restart 1 (user OK): new quickshell; user saw the test title, Settings
  opened, VPN Hub and Voxtype worked.
- Settings stayed open during edits? First try no (click-away, no reload);
  retest yes.
- Restart 2 (user OK): title restored (screenshot).
- Typed to Sora "Reply with the single word OK": she said "OK".
