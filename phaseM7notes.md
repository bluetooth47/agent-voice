# Phase M7: Authenticated answers for approval cards

Written 2026-11-22, unattended (started by the runner script). Branch
`phase-m7`, cut from `phase-m6` at 95531d3. Result commit: the notes commit
on top of 152a109, pushed to `fork/phase-m7` only; `dev` fast-forwarded to
it and pushed to `fork`. Model: Claude Opus 5.5 (tier A in the plan).

Commits:
- 79d8bdc: the phase;
- 90315cd: Codex pass 1 fixes;
- c7d0983: Codex pass 2 fixes;
- 2f8af2d: the card client writes no bytecode (found by the deploy);
- b8f0c88 and 152a109: two journal lines, added for the live checks;
- then these notes.

Deployed: **yes**, 152a109 through `bin/agentvoice-deploy --install`. It took
three deploys:
- the first attempt, c7d0983, was **refused** by the deploy's own strict
  check (below, "Found along the way");
- 2f8af2d replaced c4c67f9;
- b8f0c88 and 152a109 followed for the journal lines.

The daemon was idle before each (state `listening`, every agent idle, no
open mic). **The way back to before M7 is `bin/agentvoice-deploy
c4c67f9bdcc2`.** The script's own "way back" line names the previous M7
build, b8f0c88.

Installed: **yes**. The installer reported "Build 0.2.0 (152a109), replacing
0.2.0 (b8f0c88)". The daemon, `bin/agentvoice` and the hook changed, so it
had to be.

**Shell restart needed** (the card is QML). Not run: the next stop point is
after M9. **Until the restart, Allow on every card is refused and the card
denied.** The old overlay QML is still loaded and sends no nonce. Deny and
silence work as before. That is the fail-closed direction, and on this
machine it matters only for an agent below Trusted, today Sora.

A copy of `shell.json` was taken before the first deploy
(`~/agentvoice-notes/shell.json.before-M7`, mode 0600). It was
byte-identical to the live file afterwards.

`./bin/agentvoice-check`: green on 152a109.
- **3433 tests** (was 3312; +121), 14 of 14 static checks, "the check
  wrote nothing in the tree: ok".
- The deploy's strict run in a fresh worktree: 3433 passed.
- The bare-runner variant (`AGENTVOICE_STRICT=1`, a venv with only
  requirements-dev): green on c7d0983 (3414 passed, 9 skipped, the
  existing numpy skips) and again on the final tree, 152a109
  (3417 passed, 9 skipped).
- Box: not run (`install.sh` did not change).

## What was built

**The daemon holds every card** (new `daemon/cards.py`, 941 lines).
Before M7, the hook wrote `$RUNDIR/permissions/<id>.request` and took
whatever appeared as `<id>.response`. Any process running as the user could
write that file, so an agent at Trusted could answer its own card with
`agentvoice permit ID allow`. Now:

- **Asking.** The hook, and the desktop and crew servers under `--guard`
  (Codex), connect to `$RUNDIR/cards/cards.sock` (0600, in a 0700 folder).
  They post the card and wait on the same connection. Before trusting the
  listener, they check by `SO_PEERCRED` that it is their own ancestor.
  Anything running as the user can bind a socket at that path; nothing can
  make itself the hook's ancestor. On the daemon's side, only a process
  descended from the daemon may post. The daemon's own collaboration
  questions post in-process (`cards.LOCAL_DESK`).
- **Showing.** `agentvoice pending ID` (the overlay's lookup) gets the card
  from the daemon. It is given the card's one-use **nonce** and digest only
  if the caller passes the check below. Anyone else sees the question
  without the nonce, as a terminal always could. The overlay is handed the
  card without `input`, the whole tool call, which the card never drew. The
  digest covers exactly the fields shown.
- **Answering.** `agentvoice permit ID VERDICT`. The verdict goes on argv;
  the nonce and digest go on stdin, never argv. The daemon accepts an
  **allow** only when all of these hold:
  - the caller's **parent is the live Omarchy shell**: its executable is
    `quickshell`, it was started with `-p $OMARCHY_PATH/shell` (a link to
    that folder counts), and it is owned by this user;
  - that shell **does not descend from the daemon**, so nothing an agent
    started can stand in for it, a second shell included;
  - the caller's stdin (for `permit`) or stdout (for `pending`) is **a pipe
    the shell itself holds**;
  - the nonce and the digest match, and the card is still waiting and
    inside its deadline;
  - the asker has not stopped;
  - the screen is **unlocked**, asked afresh (`session_locked()`), because
    the daemon's own flag can be 2 s behind a lock. "Cannot tell" refuses.

  A pidfd (`SO_PEERPIDFD`, where the kernel and architecture have one) and
  a second read of the caller's start time and parent close the pid-reuse
  race.
- **A deny is taken from anyone.** An allow that fails any check is not
  ignored: **the card is denied**, and the journal says why. Silence, the
  deadline, a stopped turn, the asker hanging up (a killed hook) and a lock
  all deny. One lock settles each card, so an answer and the timeout cannot
  both win. At most 16 cards wait at once.
- **The hook never waits into Claude Code's 60 s cutoff.**
  - `AGENTVOICE_PERMISSION_TIMEOUT` is held to 50 s.
  - `main()` starts a 55 s budget that covers time spent before asking (a
    content search's checks).
  - The card's own timeout is cut to fit, and with under a second left the
    hook says no at once.
  - The long-lived servers get no such budget.
- **The journal** gets structural lines only, never a word of the card:
  - `card ID up: TOOL for AGENT`;
  - `card ID shown to the panel`, or `shown, unchecked: WHY`;
  - `card ID: allowed`, `denied`, or `an allow was refused (WHY); denied`;
  - `card ID: the screen locked; denied`;
  - `card ID down: nobody answered`, or `the asker stopped waiting`.
- **Request files are gone.** Nothing reads `$RUNDIR/permissions/` any
  more; `PENDING` stays as a name for the secret-read rule and the orders
  guard. `announce_permission` (the browser question said aloud) reads the
  desk.

**The orders guard's second layer** (`permission_hook.py`). These are asked
about at every level, Trusted and "allow all in this chat" included:
- Bash text containing `agentvoice permit`, `agentvoice/permissions` or
  `agentvoice/cards`;
- any spelling of the card dirs (`_card_dirs`) below;
- writes (and Bash that names them) under:
  - `$RUNDIR/permissions` and `$RUNDIR/cards`;
  - `~/.config/omarchy`: the shell's config, plugins and hooks;
  - this plugin's checkout behind its link;
  - the daemon's installed `app/` and `venv/`.

The reason is in the card: "this changes what answers approval cards", or
"this command could answer an approval card, or change what does".

**The overlay** (`Settings.qml`, the card handler):
- Allow is enabled only for a card handed over with a nonce (`mayAllow`).
  Otherwise it is greyed out, with the daemon's reason in plain text: "Allow
  cannot be accepted from here: …. Deny still works, and doing nothing is a
  no."
- One Process per answer and one per lookup. A shared one silently did
  nothing when started while still running, so a second card's answer or
  lookup was lost.
- After Allow the card stays up ("sending…") until the daemon replies:
  - on success it closes;
  - on a refusal it says "Not allowed: …. The agent was told no.", and the
    header reads "denied · esc to close";
  - a reply that never came says it is **not known** whether the answer was
    taken. It never says "told no" there.
- After an answer, the next card still waiting comes up, never over a newer
  summons and never while locked. A card that waited counts down the time
  it has left, not its whole timeout.
- The countdown starts when the card arrives, not when the overlay opens. A
  lookup that finds nothing hides the overlay.
- **The card closes as a no when the screen locks.** Before, it stayed open
  over the lock screen with the command on it.

**`bin/agentvoice`**: `permit` and `pending` `exec` the cards client
(`python -I -B`), so the process the daemon checks is the one the overlay
started. A person at a terminal can still say no; nobody can say yes from
there.

**Preview**: new target `card`. The stubbed `agentvoice pending` serves a
synthetic card the target writes; the stubbed `permit` logs the verdict and
what came on stdin, and answers "allowed", or refuses under
`PREVIEW_PERMIT=refuse`. Scenarios:
- `verified`: pending, then refused;
- `unverified`: Allow greyed, with the reason;
- `allow`: the card closes and does not reopen;
- `next`: a second card comes up after the first is answered.

Each run checks the nonce arrived on stdin and not on argv:
"nonce-on-stdin=true nonce-on-argv=false digest-on-stdin=true".

**Docs**:
- CODEBASE: runtime files, `cards.py`, the CLI, the security section, known
  limits, the preview target;
- README: the hook paragraph says what M7 stops and what it does not;
- SECURITY: the permission request is no longer a file, and a new "checked,
  not proven" limitation;
- CLAUDE.md: "Seven ways this fails open", the new one being "An answer is
  only as good as whoever sent it".

**Settings.** None.

## What was proven, and what was not

The plan asks for exactly this. "Sound" below means: no way found to get an
allow accepted without the person at the screen, short of a same-user
process deliberately built to defeat it.

**Proven by tests with real processes and real IPC** (`tests/test_cards.py`).
A fake shell (an interpreter started with `-p DIR`) runs the real
`bin/agentvoice` as its own children, holding their pipes:
- the overlay's path is accepted, including "allow all in this chat";
- refused, with the card denied, even when holding the real nonce:
  - this test process as caller (a terminal, an agent's shell);
  - a shell descended from the stand-in daemon (an agent's child);
  - a shell running another folder (`qs -p ~/evil`);
  - a `permit` reading a file;
- no nonce for a `pending` whose output goes to a file, or into a pipe the
  shell does not hold;
- no nonce for a caller whose start time changes mid-check (pid reuse);
- an expired card, a changed card (digest), a double submit and a lock all
  refused;
- an allow arriving after the deadline while `post()` is busy, an allow
  whose lock probe runs past the deadline, and an allow for a stopped turn
  are all refused;
- the hook: a listener that is not its ancestor is refused; no daemon,
  silence, an unreadable answer, a key given twice and an exception all
  deny;
- the real `permission_hook.py` end to end over the socket; a killed hook
  takes its card down; nothing of the card is left on disk.

**Mutations: 47, all red.** 30 on the phase, 9 on pass 1's fixes, 7 on pass
2's, 1 more on the journal line test. One survived at first (cutting the
card's timeout to the hook's budget) until the test checked the timeout the
daemon is handed. They covered:
- each caller check: exe, config folder, not from the daemon, pipe kind,
  pipe held, re-stat;
- the listener: `show` handing the nonce to anyone, and `permit` checking
  stdout instead of stdin;
- the desk: nonce, digest, verified, lock (cached, fresh, cannot-tell,
  raising), session, settle-once, deadline, withdrawn, no socket, the
  asker check;
- the client: listener ancestry, answer kind, no daemon, the budget, the
  lost reply;
- the hook: literal yes, silence, exception, timeout clamp, its clock;
- the orders guard: words and dirs;
- the QML: `mayAllow`, nonce in argv, the lock handler, the probe sequence,
  the countdown, the next card.

**Proven live**, on the real daemon with real Claude turns (Sora, at "ask"),
synthetic text. Details in the checklist at the end.
- The real Omarchy shell's own child passes the check. The still-old
  overlay's lookup was logged `shown to the panel` four times. Separately,
  `Verifier()` accepted a real direct child of the live quickshell
  (inotifywait) and refused a plain process.
- A forged `agentvoice permit ID allow` from a terminal was refused, the
  card denied, and Sora replied "denied". Bash never ran.
- `agentvoice lock` while a card was up: "the screen locked; denied".
- Silence: "down: nobody answered" at 45 s, and Sora was told it timed out.

**Not stopped: a same-user process that sets out to defeat it.**
1. **A plugin dropped into `~/.config/omarchy/plugins`.** The shell loads it
   within 150 ms (the bug H watcher). Its QML can run `agentvoice
   pending|permit` as the shell's own child, pipes and all.
2. **This plugin's QML edited** in the deploy checkout, then a shell
   restart.
3. **Shell config that runs a command attached to the shell.** A custom bar
   widget runs `bash -lc <exec>` from `shell.json`
   (`plugins/bar/Bar.qml:3207`), and there are menu provider scripts and
   idle commands. `exec agentvoice pending ID` there passes the pipe check,
   and the bar *displays* its output: a screenshot of the bar gives the
   nonce. A second widget's `exec agentvoice permit ID allow` can then be
   fed the nonce through `/proc/PID/fd/0`.
4. **Injected input.** Hyprland offers the virtual-keyboard and
   virtual-pointer protocols to any client (`wtype`, `wlrctl`), which can
   click Allow on a real card.
5. **Pipe races through `/proc/PID/fd`.** Opening another process's pipe
   needs PTRACE_MODE_READ, which Yama's `ptrace_scope=1` does not restrict.
   A same-user process can race the overlay for `pending`'s output (the
   nonce). It cannot flip a Deny into an Allow: the verdict is on argv,
   which only the shell sets.
6. **Replacing the daemon's code** (`app/`, `venv/`), or killing the daemon
   and running another.
7. **ptrace** is blocked here (`kernel.yama.ptrace_scope = 1`). On a machine
   at 0, a same-user process could inject into quickshell.

The orders guard asks about the plain forms of 1, 2, 3 and 6 at every
level. Below Trusted every command and every write outside the project is
a card the user sees, and `/.config/omarchy/` is in `NEVER_SILENT`. So an
agent there cannot set any of this up without approving its own setup on
screen. **At Trusted it can**: the Bash match is on text, and Trusted Codex
has no hook at all.

**Result for M8: the check is sound below Trusted and not at Trusted.**
Following the plan's own fallback, M8 ships and **"Ask me first" carries
the label "advisory for Trusted agents"**. Open issue 1.

## Shared files touched, and where

- `daemon/permission_hook.py` (security-critical, +93/−100):
  - `ask_card` now goes through the desk, and the file protocol and its
    `_strict` are gone;
  - `_timeout` held to 50 s; `_HOOK_STARTED` and `HOOK_BUDGET_S`;
  - `_card_dirs`, `CARD_WORDS` and `_spellings` in the orders guard;
  - docstrings.
- `daemon/wake_listen.py` (big, +15/−13):
  - 5 lines in `main()` start the desk (`start_desk(is_locked=…,
    locked_now=session_locked)`);
  - `announce_permission` reads the desk instead of request files.
- `daemon/collab.py` (big shared): the `_card` docstring only. The call is
  unchanged: it goes through `permission_hook.ask_card`, which uses the
  desk.
- `Settings.qml` (big, +207/−28): the card handler (`answer`, `permitReplied`,
  `permitNeverRan`, `nextCard`, `probeReplied`, `hideCard`, `mayAllow`, the
  probe and permit Components), the lock handler, the countdown, the
  buttons, the note and the header hint. Nothing outside the card.
- `bin/agentvoice`: `permit` and `pending`.
- `bench/preview/preview.sh`: the `pending` and `permit` stubs.
- `AgentsPage.qml`, `AgentDetailsPage.qml`, `Panel.qml`, `agentfs.py`:
  untouched.

## Measured

- **The caller check** against the real shell: **0.73 ms** per check
  (n=200). It reads about 150 of the shell's fd links.
- **`agentvoice pending`**: **98 ms** median, 103 max (n=10). That is the
  venv Python's start, the connect and the check. The old `cat` of a file
  was a few ms. The overlay now starts its countdown when the card arrives.
- **The live forged allow**: refused, and the card denied, at once.
- **A lock while a card was up**: denied within the desk's 0.1 s poll.
- **An unanswered live card**: down at 45 s; the turn took 49 s.
- Tests 3312 → 3433. The check's test run is about 2 min 50 s (was 2:45).
- No speed or size claim is made, so nothing went to FINDINGS.

## Different from the plan, and why

- **"Ancestry includes the live shell" became "the parent *is* the live
  shell", plus the pipe check.** Measured with a scratch `qs`: an attached
  `Process` is the shell's direct child, while `Quickshell.execDetached`
  (what Omarchy's menu, dock and bar use to launch things) double-forks to
  `systemd --user`. So "direct child" excludes every detached spawn.
  Omarchy also runs attached shell strings taken from config (the custom
  bar widget), which is why the caller must also read or write the shell's
  own pipe.
- **"Must not include any agent process the daemon started" is checked as
  "the shell does not descend from the daemon at all".** Every agent process
  descends from the daemon, so this needs no pid tracking. A process that
  escaped by double-forking is in nobody's ancestry any more.
- **"Unauthenticated = denied" applies to allows.** A deny is accepted from
  anyone, because it can only make things safer. An unauthenticated
  `pending` still shows the question, without the nonce.
- **A terminal can no longer allow**, only deny. The old usage line said
  "The overlay calls this; so can you." Open issue 3.
- **The request files are gone too**, not only the responses. The old folder
  stays guarded.
- **The orders guard's second layer is wider than the plan's two items.**
  The plan names `agentvoice permit` and writes under `$RUNDIR/permissions/`.
  This also covers the card socket, `~/.config/omarchy` as a whole, the
  plugin's checkout, and the daemon's `app/` and `venv/`: each is a way to
  change what answers a card. Open issue 2.
- **A lock now denies the card**, in the daemon (cached flag, and a fresh
  probe for allows) and in the overlay. The plan does not mention the lock.
  The old card stayed on top of the lock screen.
- **Beyond the plan, from the review**: the overlay waits for the daemon's
  verdict and shows a refusal; the next waiting card comes up; the
  countdown shows the time left; the hook's 50 s cap and 55 s budget;
  `show` omits `input`.
- **Two journal lines were added after the first deploy** (b8f0c88,
  152a109), so the live check could see the real shell pass and tell a
  lock's denial from a stopped turn. Each cost a deploy cycle.
- **Preview**: the card has a fixed width (560), so there is no separate
  narrow shot. Shots: dark (pending, refused, unverified, next) and
  `flexoki-light` (refused, unverified).
- **Codex ran on the read-only copy both times.** `codex sandbox linux --
  true` still panics ("Failed to execvp linux"). The clone's HEAD and
  status were unchanged after both passes, and both copies were deleted.
  - Pass 1 was sent the product-code diff only (`-- '*.qml' daemon bin`,
    1,532 lines), not the tests or docs, capped at 8 findings.
  - Pass 2 was sent pass 1's fix diff only (281 lines), at low effort,
    capped at 5.
  - **Pass 2's fixes and the three later commits were not reviewed by
    Codex** (credits). The later commits are small: `-B`, and two journal
    lines.

## Codex review

**Pass 1** (8 findings, all fixed in 90315cd):
1. The hook could outlive Claude's 60 s with a long timeout setting. Now
   held to 50 s, with a 55 s cap on any asker's wait.
2. An allow could land after a lock the 2 s poll had not seen. The lock is
   now asked afresh for an allow.
3. An allow after the deadline was taken while `post()` was busy. `answer()`
   now checks the deadline.
4. An allow for a stopped turn was acknowledged as taken. It is now
   withdrawn.
5. Overlapping summons lost the newer card (one shared probe). Now one probe
   per summons; only the latest counts.
6. A lookup slower than a second dismissed the empty overlay. The countdown
   now starts when the card arrives.
7. A lost acknowledgement said "told no". That is now said only when the
   daemon said no.
8. A card near the ask limit could not be shown. `show` omits `input`.

**Pass 2** (5 findings, all fixed in c7d0983):
1. The hook budget counted from the ask, not the hook's start, so a slow
   content search could still run into 60 s. Now `main()` starts the clock.
2. "Cannot tell" from the fresh probe let an allow through. It now refuses.
3. An allow whose lock probe ran past the deadline could land. The deadline
   is now checked where the allow is settled, under the lock.
4. A reply lost after sending was printed `ok: false`. It is now `ok: null`,
   "not known".
5. A displaced card was left to time out unseen. The next waiting card now
   comes up.

## Found along the way

- **`python -I` drops `PYTHONDONTWRITEBYTECODE`** (it implies `-E`). During
  the check the card client wrote `daemon/__pycache__` for `paths` and
  `speech_text`. The clone already had those `.pyc` files (gitignored), so
  its check passed. `agentvoice-deploy`'s fresh worktree had none and
  refused the deploy, as designed. Fixed with `-B` and a test. The wider
  point is open issue 7.
- **Omarchy runs attached shell commands from its own config.** The custom
  bar widget's `exec` in `shell.json` is one. This matters for M8 to M10
  (section 7.4): `shell.json` is already under the orders guard, and so is
  the rest of `~/.config/omarchy` now.
- **Quickshell's Process holds all three pipes** of its child, even with
  `stdinEnabled: false`. Measured with a scratch `qs`.
- **The permission card stayed open over the lock screen** before M7. The
  lock handler skipped it on purpose. It now closes as a no.
- **Two old overlay bugs, made likelier by a slower lookup**: the shared
  probe lost a second summons, and the countdown started before the card
  arrived. Both fixed (pass 1).

## Not verified

- **The new card in the real shell.** It needs `omarchy-restart-shell`,
  which is held for stop point 2. Seen only in `preview.sh`.
- **A real Allow click.** The plan's stop-2 check stays: accept one harmless
  ask, deny another. Until the restart, Allow is refused, because the old
  QML sends no nonce.
- **A real pointer and keyboard on the card.** Every click was synthetic
  (QtTest's TestEvent). Esc is unchanged (a no); there was no keyboard walk.
- **The next-card behaviour, the "sending…" state and a refusal shown** in
  the real shell. Preview only.
- **The real lock screen.** `agentvoice lock` was used, not a real lock.
- **The Codex path** (`desktop_mcp`/`crew_mcp --guard` asking over the
  socket) live. Tests only.
- **A collaboration "ask" card** (in-process) live. Tests only.
- **Pass 2's fixes and the later commits were not reviewed by Codex.**
- **The installer box** (`install.sh` did not change).

## Going back

`bin/agentvoice-deploy c4c67f9bdcc2` from the clone, then `./install.sh
--yes` from the plugin folder once the daemon is idle, then
`omarchy-restart-shell`.
- An older build's hook writes request files and its overlay writes
  response files again, so **any same-user process can answer a card
  again**.
- No setting changed, and no crew links exist yet (M8), so there is nothing
  to turn into denials first (section 7.7).
- The old build ignores `$RUNDIR/cards/`.

## Open issues, for the next phase

1. **M8's "Ask me first" carries "advisory for Trusted agents"**, the
   plan's fallback for a check that is not sound at Trusted (above). Taken
   as the default. The alternative is a sandbox for Trusted backends,
   already on the deferred list.
2. **How wide the orders guard's second layer is.** It covers
   `~/.config/omarchy` as a whole (themes, Omarchy hooks, `shell.json`,
   plugins), the plugin checkout, `app/` and `venv/`, at every level
   including Trusted. Keep, or narrow to `plugins/`, `hooks/` and
   `shell.json`?
3. **Allowing from a terminal.** Is a terminal path for allowing wanted, for
   example when the overlay is broken? Default: no; the terminal can deny.
4. **Until the shell restarts, every Allow is refused** (the old QML). This
   lasts until stop 2. Acceptable?
5. **Injected input.** Mitigations such as an arming delay on Allow, or
   ignoring a click without pointer motion, were not built. They would only
   slow down a virtual pointer.
6. **`agentvoice try` under the orders guard** (M6 open issue 2). Still
   open; M7 did not add it.
7. **The check's "wrote nothing in the tree"** cannot see new bytecode for a
   module whose `.pyc` already exists in the clone. Run the suite with a
   temporary `PYTHONPYCACHEPREFIX`, or start from a clean `__pycache__`?
8. **Codex credits**: 27.25 this phase. **89.91 left for M8–M29**, about 4.1
   per phase: one low-effort pass per phase is about what is left.
9. **Carried, still open**:
   - M6's open issues 1, 3 and 4 (Try it on other backends, the leading
     comment, the logind fallback);
   - M5's 1 and 4–6;
   - M4's 4–13;
   - the Voice library trash icon (M25);
   - M0's small test and bench fixes;
   - agy's `carries_session_across`;
   - the runner's sandbox test command (still panics).

## Codex credits used

**27.25**. The balance went from 117.16 at the end of M6 to 89.91, read from
the session logs' `rate_limits.credits.balance`. It was still 117.16 at this
phase's first call.
- **Pass 1: 17.50** (117.16 → 99.65): `gpt-6.2-astra`, medium effort,
  sub-agents disabled, the read-only copy, the product-code diff (1,532
  lines), at most 8 findings. 57,711 tokens.
- **Pass 2: 9.75** (99.65 → 89.91): low effort, otherwise the same, on pass
  1's fix diff only (281 lines), at most 5 findings. 33,701 tokens.

**89.91 left** for M8–M29.

## Live checklist: what was said, what happened

All with synthetic text, typed. Nothing was said into the microphone. The
typed turns went into Sora's conversation, as any typed turn does. Each
check put a synthetic card on the real screen for at most 45 s.
- Before each deploy: `agentvoice status` showed state `listening`, every
  agent idle, no open mic.
- After the install:
  - the service was active;
  - `$RUNDIR/cards/cards.sock` exists (`srw-------`, folder `drwx------`);
  - `agentvoice pending` printed `{}`;
  - `agentvoice permit abcdef012345 allow` printed "no question … is
    waiting" (exit 1);
  - `permit ../x allow` printed the usage (exit 2).
- **The forged allow.** Typed to Sora: "…Use the Bash tool to run exactly
  this command and nothing else: echo m7-card-check-7c1…".
  - The journal: `card 3e0f670a756c up: Bash for sora`, then `card
    3e0f670a756c shown to the panel`. That was the old overlay's own
    lookup, checked against the real shell.
  - From a terminal, `agentvoice pending 3e0f670a756c` showed
    `verified=False`, no nonce, "it was not started by the Omarchy shell".
  - `agentvoice permit 3e0f670a756c allow` printed "refused, and the
    question was denied: it was not started by the Omarchy shell" (exit 1).
    The journal: `an allow was refused (…); denied`.
  - Sora replied "denied". The command did not run.
- **The lock, first try** (b8f0c88). Card f61a230079bf, then `agentvoice
  lock`. The card went down and the turn was stopped ("Sora: [stopped]" in
  history), but the journal could not say which did it. That led to
  152a109.
- **The lock, second try** (152a109). Card c3c6aaa03948, `shown to the
  panel`, then `agentvoice lock`. The journal: `card c3c6aaa03948: the
  screen locked; denied`. Then `agentvoice unlock`; `locked` said no.
- **Silence.** Card c6358d379d2c, `shown to the panel`, then `down: nobody
  answered` (49 s after the typed turn started). Sora replied that "the
  permission prompt timed out after 45 seconds with no answer".
- The journal since the first live turn, read with `-o json`: **0** lines
  holding any of the canary words or the typed text.
- `$RUNDIR/permissions/` stayed empty. `agentvoice pending` printed `{}`
  after each check.
- No shell restart. No setting changed. `shell.json` was byte-identical
  before and after.
