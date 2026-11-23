# Phase M21: Stats, and the Overview page

Written 2026-11-23, unattended (started by the runner script). Branch
`phase-m21`, cut from `phase-m20` at 094a963. Result commit: the notes commit
on top of 952883c, pushed to `fork/phase-m21` only; `dev` fast-forwarded to it
and pushed to `fork`. Model: Claude Opus 5.5 (tier B in the plan, high).

Commits:
- 952883c: the phase;
- then these notes.

**Codex review: bypassed (user decision, 2026-11-22).** Codex was not run, for
review or anything else. In its place I re-read the whole diff before the
commit, and ran 25 mutations; what that found is under "Found along the way".
Nothing in this phase has been reviewed by a second model.

Deployed: **yes**, through `bin/agentvoice-deploy --install --wait 120
952883c` (its strict check green) with the daemon idle (state `listening`,
every agent idle (`''`, `sora`, `jarvis-ajc`), no open mic, no task, no
journal line in the five minutes before): "deployed 952883cb66f1. The way
back: bin/agentvoice-deploy fc40f7cbb694".

Installed: **yes**: "Build 0.2.0 (952883c), replacing 0.2.0 (fc40f7c)". The
daemon (`stats.py`, `wake_listen.py`, `runtime.py`, `chats.py`, `paths.py`)
and the CLI changed. `install.sh` did not.

**Since the install the daemon counts** (keepStats is on by default and was
not in shell.json): turns, wakes, rejections, waits and limit hits go into
`~/.local/share/agentvoice/stats/`, numbers only. `agentvoice stats` reads
them now, before any restart.

**Shell restart needed** (`pages/OverviewPage.qml`, `pages/DisplayPage.qml`,
`Settings.qml`). Not run. Until it is, the running shell shows M20's Overview
and Display page: no numbers, no Keep usage numbers switch, no Clear stats.
The setting works before the restart: `omarchy bar set duaneoca.agentvoice
keepStats false`; and `agentvoice stats clear` clears.

A copy of `shell.json` was taken before the deploy
(`~/agentvoice-notes/shell.json.before-M21`, 0600); after the install and the
live checks it was byte-identical. No live check wrote a setting.

`./bin/agentvoice-check`: green on the final tree (exit 0, every line ok).
- **4920 tests** (was 4852; +68), 14 of 14 static checks, "the check wrote
  nothing in the tree: ok".
- The suite takes **5 min 46 s** here, not the "two and a half minutes"
  CLAUDE.md said: M20's own tree, timed the same way in a scratch worktree,
  took 342 s against M21's 347 s, so nothing in this phase slowed it.
  CLAUDE.md now says six minutes, with the numbers.
- Bare-runner variant: not run this phase (no new dependency; `stats.py`
  imports only the standard library, and every new test runs without numpy).
- Box: not run (`install.sh` did not change).

## What was built

**`daemon/stats.py`** (new): per-day counters in
`~/.local/share/agentvoice/stats/YYYY-MM-DD.json`, 0600 in a 0700 folder
(added to `paths.PRIVATE_TREES`), kept 90 days.
- **What a day holds**: turns per agent per kind (`wake`, `followup`, `talk`,
  `typed`, `task`); wakes accepted per engine (`spotter`, `openwakeword`,
  `vosk`, `second-check`, `other`); wakes rejected per stage
  (`second-check`, `confidence`); accepted and rejected wakes per hour; three
  waits as fixed-bucket histograms (31 buckets, 50 ms to 120 s, with n, sum,
  min, max); turns cut at the longest-turn limit; and the turn ids seen
  that day (random hex), so each turn is counted once.
- **Written** at the end of a turn (and on each accepted or rejected wake, and
  each limit hit): today's file read, changed and replaced atomically, under
  a lock that holds across threads and processes (`stats/.lock`, flock,
  O_NOFOLLOW, a FIFO there refused rather than waited on). **Never raises**: a
  failure returns False. A damaged, oversized, linked or wrong-day file is
  skipped and replaced; a damaged field is dropped and the rest kept. Pruned
  past 90 days, day-named regular files only.
- **Never text**, two ways, as the audit log: by shape (an agent id by
  pattern, words from fixed lists, a 16-hex turn id, finite numbers clamped
  to an hour; anything else refused or dropped), and an AST walk over every
  call into stats from the daemon.
- **Read**: `summary(days)` gives today and the range, every timing with its
  sample count and `None` (no data) when there is none; the median and p95
  interpolate within a bucket and never leave min..max, so one sample or many
  equal ones give the value exactly.
- **`agentvoice stats [--days N] [--json]`** (default 7, at most 90; says
  when keepStats is off) and **`agentvoice stats clear`** (prints how many
  days went). No daemon needed.

**The definitions** (fixed in `stats.py`'s docstring, and on the tiles'
tooltips):
- **wake to first word** = accepted wake → first sound of the reply, only for
  turns a wake word opened (the run loop's `woke_at`, now in the turn's clock
  as `woke`). Follow-ups, the open microphone, barge-ins, push-to-talk, typed
  and task turns are counted as turns of their kind and left out of it;
- **transcription** = Whisper's own working time on what was said, start to
  final text: the `whisper Nms` of the turn's log line (see "Different from
  the plan");
- **reply after you stop** = end of speech (or the key coming up) → first
  sound: the existing "heard → spoke" line;
- **false wakes** = bursts in which an engine heard a name and the second
  check turned it down (`crosscheck.decide` with a reason) -- labelled
  "false wakes (second check)". A burst nobody heard a name in is talk and is
  not counted. `confidence` (Vosk matched below the bar) is counted apart and
  shown as "unsure";
- each turn once, by a random id made where the capture ends.

**The daemon's side** (`daemon/wake_listen.py`):
- `Pipeline._rejected(stage)` at the two rejection points and
  `take_rejections()`; the wake test drains them uncounted.
- `Daemon.keep_stat(record, ...)` -- every stats call goes through it; it
  reads `Config.keep_stats()` each time and swallows any failure.
  `note_wake(fired)` after each `feed_wake` (the run loop and the reply-time
  wake watch): rejections, and the wake if one was accepted and was not
  "full stop". `count_turn(persona, clock, typed)` at the end of `answer()`,
  beside M16's ring line, from the same clock the latency line prints.
  `count_limit_hit` also counts it.
- The turn's clock gains `kind` (how the capture opened), `turn` (its id),
  `woke` (for a wake) and `whisper_ms`.
- **The latency line ends with `  wake → spoke in Ns`** for a turn a wake word
  opened, from the same two timestamps the stats use. `bench/turn_latency.py`
  parses it (and prefers it to its own estimate from journal times); a test.
- **`service` in the state file**: `started_at`, `rss_mb` (the daemon's VmRSS)
  and, apart, `agents_mb` / `agents_procs` (the sum over every process below
  the daemon: agents' CLIs and their tool servers). Read at most every 30 s,
  on the idle poll (`StateFile.update`, which keeps the other sticky fields).

**Setting `keepStats`** (bool, default on): manifest schema and defaults,
`runtime.DEFAULTS`, `TOML_ALIASES` (`[ui] keep_stats`), `Config.keep_stats()`
(only a plain true -- or "true"/"yes"/"on"/"1" from a hand edit -- is on;
a number, a list, a typo or settings that cannot be read are off: collect
nothing). One control: **Display & privacy → Privacy → Keep usage numbers for
the Overview**, with how many days are kept and their size, and **Clear stats**
(a `DangerButton`; `clearStats()` starts `agentvoice stats clear` from its
`onConfirmed` only; added to `test_confirms.py`'s table as the plan foresaw).

**The Overview** (`pages/OverviewPage.qml`, rewritten around what was there):
- the voice service card (the switch); Stop while a turn runs; Needs
  attention;
- **the numbers**, with a **Today / 7 days** choice (it changes only what is
  shown): six tiles -- turns (per agent underneath, kinds on hover), wake to
  first word, reply after you stop, transcription (each the median, with p95
  and its turn count, "no data yet" with none), wakes / turned down (false
  wakes labelled as the second check's), and up (uptime, then the service's
  and the agents' memory). A line when the numbers are off or unreadable.
  **Wakes by hour** (`MiniBars`, the current hour marked; the readout under a
  bar says how many were turned down that hour). Read from `agentvoice stats
  --days 7 --json` when the page opens, when the overlay is opened again,
  after each turn and every 30 s while open;
- **the microphone card**: level, gate, the Mute button (moved here from the
  service card; still the Overview's only call of `toggleMic`) and a link to
  Listening;
- **the agents' cards** with state, and **last chat ›** when the agent owns a
  saved chat whose file is there (new `agentvoice chats last --json`, ids
  only: `ChatStore.last_by_owner`), opening it on the Chats page;
- the last exchange, as before.

**Preview**: a new `overview` target with a synthetic stats seed
(`overview.seed.py`, through the real `stats.py` into the scratch data
folder, and the service's start and memory into the scratch state file); the
stub's new `stats` case always reads the scratch folder, and logs a clear.

**Docs**: README ("How it has been going: the Overview"), CODEBASE (module,
data file, pages, setting, CLI), CLAUDE.md (the check's real duration),
FINDINGS §54, `bench/stats_cost.py`.

## What was proven, and how

- **Tests** (`tests/test_stats.py`, 66 cases; `test_confirms.py` gains
  `stats clear`; `test_turn_latency.py` the wake figure):
  - **A driven turn's stats equal its structural log lines**: the real frame
    loop over a scripted microphone (`tests/frame_loop.py`): a wake on the
    second frame, five loud frames, the endpoint, Whisper, the reply. The
    `whisper 12ms` line and the transcription median are equal; "heard →
    spoke" and "wake → spoke" equal the reply and wake medians to the line's
    rounding; one wake, by the spotter; one `wake` turn for main.
  - **keepStats off writes nothing**: a full turn through `answer()`, a limit
    hit and a wake with two rejections, and the data folder is never created.
    `keep_stats()` for eleven raw values; default on; unreadable settings off.
  - **Never text**: a canary sentence as the agent, the kind, the turn id, the
    waits, the wake engine and the stage -- refused or dropped, and not in
    the file; every string in a day file is an id, a date or a fixed word; the
    AST walk (every `stats.record_*` and `keep_stat(stats.record_*, ...)` call
    in the daemon, every name it reads, at any depth); the clock it reads
    holds only timestamps, the kind and the id (a test lists its keys).
  - **A corrupt day file is skipped and replaced** (not JSON, not UTF-8, a
    list, another day's, 300 KB), a damaged field dropped and the rest kept,
    a link at the day file neither followed nor written through, a FIFO lock
    refused, a write that raises returning False -- and a stats call that
    raises leaves the turn's reply untouched.
  - **Two agents at once**: two threads, 40 turns and 40 wakes each, nothing
    lost; **three processes** at once, 60 turns each. **A duplicate event**
    counted once; **midnight** (23:59:59.5 and 00:00:00.5 land on their own
    days, the hour bar at 23, the 2-day summary); **a daemon restart** (the
    module reloaded: the day kept, a turn id from before still counted once);
    **pruning** (89 days back kept, 90 and 120 gone, a notes file and a
    `.bak` untouched); Clear deletes only day files and creates nothing.
  - How a capture opened is the turn's kind (wake, talk, follow-up, open,
    barge, none); a task turn; a typed turn has no voice timings; a full stop
    is not a wake; the wake test is not counted; the service field (sampled
    every 30 s) and real memory of this process and a child; `chats last`
    (newest per owner, a missing file skipped, ids only, creates nothing).
- **Mutations: 25 run, 24 red** (a scratch copy under /tmp, never the clone).
  The one green is equivalent: removing the in-process mutex changes nothing,
  because each `_Locked` opens its own file description and `flock` already
  excludes threads. Two first survived and were tightened (below).
- **Preview** (`preview.sh`, synthetic mouse events through `TestEvent`, a
  scratch config, data and runtime folder, the real pointer never moved):
  **`overview` 51 of 51 PASS** over six runs -- `several` 11 (every tile's
  figure, 24 hour bars holding the 7 wakes, last chat › opening that chat
  on the Chats page), `week` 13 (7 days: 33 turns, 23 wake turns, 19 / 8,
  no current hour), `idle` 5 (one sample said as "1 turn"), `empty` 8 (— and
  "no data yet", never 0 s; "No wakes yet today."; no last chat), `off` 7
  (keepStats written false through the real store, the CLI and the page say
  nothing new is counted, what was kept still shown), `clear` 7 (Clear stats
  arms, Cancel disarms, Clear runs `agentvoice stats clear` on the scratch
  copy, the page then says none are kept). `confirms` covered by the test.
- **Screenshots** (`/tmp/m21`, not committed): 1100×760 dark (three
  screenfuls), flexoki-light on 7 days, the empty day, and 520×720 (the crop
  cuts the overlay's right edge, as in M18 to M20).

## Shared files touched, and where

- `daemon/wake_listen.py` (big shared, 7,274 → 7,407): `import stats`;
  `Pipeline._rejected` / `take_rejections` and the two calls; `SERVICE_SAMPLE_S`;
  `Daemon.__init__` (`started_at`, `_service`); `wake_testing` drains
  rejections; `refresh` publishes the memory every 30 s; the reply-time wake
  watch and the run loop call `note_wake`; `count_limit_hit` counts;
  `keep_stat`, `note_wake`, `count_turn`, `service_field` beside it;
  `report_latency`'s wake figure; `answer()` calls `count_turn`;
  `crew_fields` carries `service`; the capture's clock (`kind`, `turn`,
  `woke`, `whisper_ms`). Nothing in the wake decision or the turn's flow
  changed.
- `Settings.qml` (big shared, 2,172 → 2,177): `vService` and its parse.
- `daemon/runtime.py` (`keepStats`, `keep_stats()`, `StateFile.update`),
  `daemon/chats.py` (`last_by_owner`, `last --json`), `daemon/paths.py`
  (`PRIVATE_TREES`), `bin/agentvoice` (`stats`, the usage line, `chats last`
  in the comment), `manifest.json`, `pages/OverviewPage.qml` (261 → 571),
  `pages/DisplayPage.qml` (317 → 437), `bench/turn_latency.py`,
  `bench/preview/preview.sh` (the stub's `stats` case), `tests/test_confirms.py`,
  `tests/test_turn_latency.py`, `README.md`, `CODEBASE.md`, `CLAUDE.md`,
  `bench/FINDINGS.md`; new `daemon/stats.py`, `tests/test_stats.py`,
  `bench/stats_cost.py`, `bench/preview/targets/overview.{qml,seed.py}`.

## Measured

FINDINGS §54, on the i7-1185G7:
- **The stats write at the end of a turn: 0.80–0.91 ms median, 0.98–1.36 ms
  p95** (200 turns, three runs). A wake or rejection write about the same,
  on the frame a wake is accepted.
- **Day file at 200 turns, 60 wakes, 15 rejections: 4,727 bytes**; about 425
  KB kept at that rate over 90 days.
- **The Overview's read** (`summary(7)` over a full week): 2.8–3.1 ms median.
- **Memory against `ps`**: 1160 MB against `ps -o rss=` 1,187,516 kB
  (1159.7 MB). Reading every process (368 visible): 10.1 ms median, every 30
  s on the idle poll.

## Different from the plan, and why

- **Transcription is Whisper's own working time** (the `whisper Nms` of the
  log line, `Utterance.busy_ms`), not the wall time from transcription start.
  Since Phase 8 Whisper transcribes each piece at a pause while you are still
  talking, so the wall time from the first piece's start to the final text
  includes your own speaking; the working time is what transcription costs,
  and equals a structural log line, which the plan's test asks for.
- **A third timing tile, "reply after you stop"** (the existing "heard →
  spoke" line). "Wake to first word" as defined includes the whole sentence
  you said, so on its own it would read slow for long requests; the wait
  after you stop is the one people sit through.
- **"Wake → spoke in Ns" added to the latency line**, so the wake figure is a
  structural log line too; the bench parser updated with it.
- **Rejected stages are the second check and Vosk's confidence bar.**
  openWakeWord's verifier works inside openWakeWord's own score (there is no
  separate rejection event to count), and the spotter scoring below its
  threshold is not a decision. Said in `stats.py`.
- **Agents' memory is one total** (every process below the daemon), not per
  agent: the plan says "shown separately" from the daemon's, which it is.
- **A new CLI verb `chats last --json`** for "last chat ›" (ids only).
- **The Mute button moved into the Microphone card.** The plan's mic card has
  "gain"; there is no gain setting, so it shows level, gate and mute.
- **The tests are `tests/test_stats.py`**, and the "two agents at once" case
  is three processes as well as two threads.
- **Codex review bypassed** by the user's decision.

## Found along the way

- **The check takes six minutes, not two and a half** (above); CLAUDE.md
  corrected in place.
- **Two zombie `claude` processes under the running daemon** (`<defunct>`,
  started 03:33:38 and 03:34:14, a minute after the M20 install's restart, so
  most likely the M20 live turns' CLIs, ended and never reaped). Harmless in
  memory (0 kB, which is what the Overview's agents' figure showed for them),
  but an adapter somewhere drops a finished process without `wait()`. Not
  fixed here: outside this phase, and the install restarts the daemon, which
  clears them. Open issue 3.
- **My preview target's helper `page()` shadowed the overlay's `page`
  property**, so the first "last chat opens the Chats page" check read a
  function; renamed.
- **The test harness's action ran inside the echo drain** (`deafen` drains
  whatever the scripted queue holds, running its actions), which wiped the
  timestamp it was meant to reset; the driven test is one turn, and the
  follow-up kind has its own test.
- **Two mutations survived at first**: removing the flock (the threads were
  still held by the mutex; a three-process test now catches it), and reading
  through a link at the day file (the planted target was not a valid day, so
  it was replaced either way; the target is now a plausible day of counts).
- **My re-read**: `StateFile.update` read the context and wrote it under two
  separate holds of the lock, so a `describe()` from a turn thread in between
  could have been undone (one hold now); the Overview's 30 s timer ran while
  the overlay was closed if the page stayed loaded (now only while open, and
  a fresh read each time it is opened); a caption elided at 1100 px ("2 false
  wakes stopped by the s…", now "2 false wakes (second check)").

## Not verified

- **The page in the real shell.** It needs `omarchy-restart-shell` (not run).
  Seen only in `preview.sh`. Until the restart the running shell has M20's
  Overview and Display page; the daemon already counts (keepStats is on by
  default) and `agentvoice stats` reads it.
- **Ten real voice turns, then the Overview compared with the journal** (the
  plan's stop 5 check). Nothing was said into the microphone; the live check
  below is typed.
- **A real false wake counted** (needs a wake word said near the mic).
- **The narrow layout** (below 560 px): the crop cuts the overlay's edge.
- **The installer box** (`install.sh` did not change).
- **The Codex review** (bypassed, not owed).

## Going back

`bin/agentvoice-deploy 094a963fb2a4` from the clone, `./install.sh --yes`
once the daemon is idle, then `omarchy-restart-shell`. An M20 build ignores
`keepStats` (the key stays in shell.json if it was written) and the stats
folder (it stays on disk until deleted: `rm -r ~/.local/share/agentvoice/stats`
or Clear stats before going back), and its latency line has no wake figure.
Nothing it reads changed shape: the state file's new `service` field is
ignored by older QML.

## Open issues, for the next phase

1. **Codex review bypassed** for M21 (user decision, 2026-11-22). M12 stays
   "review owed".
2. **keepStats on by default** (Appendix A's default, taken). Installed:
   counting began with this install. If the answer is "off until switched
   on", change `DEFAULTS`, the manifest default and the page's fallback.
3. **Zombie `claude` children of the daemon** (found above): which adapter
   path drops a finished process without reaping it? Default: noted, not
   fixed (outside M21).
4. **Should switching keepStats off also delete what was kept**, as
   `keepHistory` off does? Default: no -- off stops counting, Clear stats
   deletes, and the page says so.
5. **Wake to first word includes the sentence somebody said.** Is that the
   figure wanted on the Overview, or should the tile show the reply wait
   first? Default: both tiles, wake first, as the plan's definition.
6. **Per-agent memory** rather than one total for the agents? Default: one
   total (attributing a crew server to its agent needs the adapter's pid).
7. **The memory read (10 ms every 30 s) runs on the run loop's thread**, on
   the idle poll. Move it to a thread? Default: no; it is below a frame.
8. **Carried, still open**: M20's 2–8; M19's 3–6; M18's 2–6; M17's 2–7;
   M16's 2–9; M15's 2–8; M14's 2–7; M13's 2–9; M12's 2–7; M11's 1–7; M10's
   1–8; M9's 2–7; M8's 2–11; M7's 2–7; M6's 1, 3, 4; M5's 1, 4–6; M4's 4–13;
   the Voice library trash icon (M25); M0's small test and bench fixes; agy's
   `carries_session_across`; the runner's sandbox test command.

## Live checklist: what was done, what happened

Nothing was said into the microphone. One typed turn to Theo, spoken aloud by
the daemon as any typed turn is, synthetic.
- Before the deploy: state `listening`, every agent idle, no open mic, no
  task, no journal line in five minutes; `shell.json` copied (0600).
- `bin/agentvoice-deploy --install --wait 120 952883c`: strict check green;
  "deployed 952883cb66f1. The way back: bin/agentvoice-deploy fc40f7cbb694";
  "QML changed: run omarchy-restart-shell? (not run)"; "Build 0.2.0
  (952883c), replacing 0.2.0 (fc40f7c)". Service active; no journal line
  after the restart (`-o json`) was an error or a traceback.
- `agentvoice status`: `service` present. Sampled during start-up it said
  708 MB; 73 s later, after the 30 s resample, **936 MB against `ps -o rss=`
  935 MB**; agents 0 MB, no child process (the restart cleared M20's two
  zombies).
- `agentvoice stats --json` before the turn: no turns, no day file,
  `keeping: true`.
- `agentvoice chats new main`, then a typed turn to Theo: "Synthetic check
  for phase M21, canary HERON-5521: in one short sentence, what is the
  capital of Australia?" Afterwards `agentvoice stats --json`: **`turns:
  {main: 1}`, kind `typed: 1`, no voice timing** (typed turns give none, as
  defined). The day file: 263 bytes, 0600, folder 0700, holding
  `{"turns":{"main":{"typed":1}}, ..., "ids":["cf58e870603b485a"]}` and **no
  word of the turn** (grep for heron, 5521, Australia, Canberra: 0).
- The journal for those six minutes (`-o json`): 35 lines, **none holding the
  canary**; the stats folder and the audit log neither.
- Cleanup: the synthetic chat (666e00c31bf4d5bf) deleted with `agentvoice
  chats delete`, the search for the canary then empty; `agentvoice chats new
  main`, so Theo's next turn does not continue it. His previous real chat is
  saved and can be continued. The one typed turn stays counted in today's
  stats (Clear stats removes it).
- `shell.json` byte-identical to the copy afterwards. No shell restart.
