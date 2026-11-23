# Phase M26: Other settings, and About

Written 2026-11-23, unattended (started by the runner script). Branch
`phase-m26`, cut from `phase-m25` at 754d57b. Result commit: the notes commit
on top of 6fe6536, pushed to `fork/phase-m26` only; `dev` fast-forwarded to it
and pushed to `fork`. Model: Claude Opus 5.5 (high).

Commits:
- 6fe6536: the phase;
- then these notes.

**Codex review: bypassed (user decision, 2026-11-22).** Codex was not run, for
review or anything else. In its place I re-read the whole diff before the
commit and ran 23 mutations of the new tests (22 real, one a no-op I
discarded); what that found is under "Found along the way". Nothing in this
phase has been reviewed by a second model.

Deployed: **yes**, through `bin/agentvoice-deploy --install --wait 120 6fe6536`
(its strict check green: 5177 passed) with the daemon idle (state `listening`,
`open_mic` empty): "deployed 6fe65361e6cb. The way back: bin/agentvoice-deploy
a2c090030cbc".

Installed: **yes**: "Build 0.2.0 (6fe6536), replacing 0.2.0 (d4ad068)". The
daemon changed (`stats.py`, one line in `wake_listen.py`, two new modules, the
CLI) and so did `install.sh`. The installed stamp now reads `commit=6fe6536…`,
`branch=detached`, `installed=2026-11-23T15:00:54-07:00`, and `agentvoice
about` says "The settings and the service are the same build". Service
`active`, state `listening` afterwards.

**Nothing about listening, turns or the open mic changed on this machine.** No
setting was written and no turn was run. `shell.json` is byte-identical to the
copy taken before the deploy (`~/agentvoice-notes/shell.json.before-M26`, 0600).

**Shell restart needed** (`Settings.qml`, `pages/OtherSettingsPage.qml`,
`pages/AboutPage.qml`, `ui/InfoRow.qml`, `pages/OverviewPage.qml`, `Hud.qml`).
Not run. Until it is, the running shell shows M25's Display and About pages;
the new CLI verbs work now.

`./bin/agentvoice-check`: green on the final tree (exit 0, every line ok).
- **5177 tests** (+72 in the two new files, +4 in test_stats, +3 in
  test_confirms; several rewritten, below), 14 of 14 static checks, "the check
  wrote nothing in the tree: ok". 6 min 0 s.
- The first full run was **red (5 failed)**: four endpoint tests (a name I
  shadowed) and test_uninstall (Remove moved); both fixed, below.
- **Box** (`AGENTVOICE_BOX=1`, `install.sh` changed): "installer in a box 9
  passed, 0 failed". That run was cut off during its own test step by a
  10-minute limit I set on the background job; the tree did not change, and
  the full check was rerun without the box and is the green above.
- **Bare-runner variant** (`/tmp/ci` venv from `requirements-dev.txt`, no
  numpy, `AGENTVOICE_STRICT=1`): test_diagnostics, test_other_about_pages,
  test_stats, test_confirms and test_endpoints: 251 passed. The whole bare
  suite was not run.

## What was built

**Other settings** (`pages/DisplayPage.qml` → `pages/OtherSettingsPage.qml`,
`git mv`; sidebar id `other`, label "Other settings", tenth, Ctrl+0). The old
id `display` is an alias in `Settings.qml::goTo`, before the "known page"
test, so `{"page":"display"}` and `goTo("display")` still land here (the
`clicks` and `overview` preview targets deliberately still use it). Writes
exactly the ten keys Display wrote; no key added, moved or renamed.

- **On-screen readout**: `hud`, `hudLingerMs`, the four M3 keys, Preview, and
  `agentsPanel` (its own group until now; it is something on screen too).
- **Privacy**: the "Saved chats → Go to Chats" pointer, `yieldToRecorders`,
  **⚠ Write what is said to the system log** (`logSpeech`), whose switch
  writes `false` at once and only *opens a question* when off: a `ToolConfirm`
  saying what goes there, that the journal keeps it for weeks and turning it
  off later does not remove what was written, and who can read it; `true` is
  written by `turnOnSpeechLog()`, which only that question's `onConfirmed`
  calls. `keepStats` with Clear stats (unchanged). "The mic always closes
  while the screen is locked."
- **Keys**: read live through the new `agentvoice keys --json`
  (`daemon/keybinds.py`): every `o.bind(...)` in `bindings.lua` whose command
  starts `agentvoice`, checked against `hyprctl binds -j`. On Omarchy 4.5 a
  binding is a Lua callback and hyprctl reports it as `__lua` with a number,
  **so the command line is not in hyprctl's answer at all** (found by looking:
  filtering hyprctl on "agentvoice" finds nothing on this machine). A Lua
  binding counts as loaded when Hyprland has one on the same keys and
  press/release with the same description; an older `exec, agentvoice …` one
  is found by its argument. Talk + talk-end on one key is one "Hold F8" row; a
  line Hyprland has not loaded is marked. The bar icon's three clicks stay as
  fixed rows (they are the widget's). **Open bindings file**:
  `omarchy-launch-editor` with the path from the CLI, checked against the one
  shape it may have. Read only: changing a binding stays deferred.
- **Maintenance**, moved from About: Repair (or Install), Add openWakeWord,
  Add sherpa-onnx, and **Remove Agent Voice** (the same `DangerButton` into
  `removeEverything()`), last. Today's backup and recovery behaviour is the
  installer's and did not change.

**About** (`pages/AboutPage.qml`, rewritten; changes nothing).

- **This install**: version; *these settings* (the plugin folder's commit and
  branch, "detached" for a deploy checkout); *the service* (the stamp in
  `DATA_DIR/app/VERSION`: commit, branch or "unknown branch", install time);
  and a line saying whether they are the same build, different builds with no
  daemon file different (`git diff --quiet A B -- daemon bin desktop
  install.sh requirements*.txt models.lock`), different, or cannot tell; a
  dirty install is said. Then the engine rows that were there.
- **Copy diagnostics** (`agentvoice diagnostics copy`, `daemon/diagnostics.py`)
  and **Show**, which prints the same report on the page. Built from
  allowlists: a setting is shown only by its kind (a number or switch as
  itself, a word from a short list, a URL as scheme+host, a per-program map
  only where every key and value is a plain word, `voiceAgents` as program,
  model, effort, level, voice and a few other words per agent, any other text
  as "set"/"not set"), and only settings the daemon knows and that differ from
  the defaults. Journal lines (read with `-o json`, each `\r`/`\n` piece
  judged alone) are kept only when they fully match one of ~45 shapes of the
  daemon's structural prints; an exception keeps its type, not its message;
  systemd's lines match their own shapes. Everything else is counted as "N
  other lines left out", **with `logSpeech` on or off**. Home collapses to `~`
  and anything key-shaped is masked last over the whole text (runinfo's
  masks). The clipboard gets it on stdin, with wl-copy's pipes to /dev/null
  (its forked child would otherwise hold the call open).
- **Check for updates** (`agentvoice about updates`): only from its button;
  one `git ls-remote` of the branch's upstream remote (or `origin` HEAD), with
  prompts off, `core.fsmonitor=` and `protocol.ext.allow=never`; the answer
  names the remote and its URL without any password. A folder that tracks no
  remote says so and asks nobody. **The deploy checkout here has no remote,
  on purpose (M0), so live it says exactly that.**
- **Runs here, and what goes out** (`agentvoice about backends`): wake word,
  transcription and voices "on this machine"; each offered backend (Claude
  Code, Codex, Gemini CLI, Antigravity, Copilot CLI) as cloud, with **not
  found / installed / has answered N turns here (90 days)** and who uses it;
  a configured endpoint as local or cloud by its host. "Answered" comes only
  from a record: new `stats.record_answer(program)`, called at the end of a
  turn that said something and did not fail (one guarded line in
  `wake_listen.py`, through `keep_stat`, so `keepStats` off records nothing
  and the page then says it is not recorded). Finding a program never counts
  as connected, and the page says installed is not signed in. **Look**
  (`agentvoice endpoint probe-local`): `GET /v1/models` on 127.0.0.1:11434
  and :8080, only from its button, no proxy, no redirects, no key.
- **Voice commands**: the full list from `agentvoice commands --json` with
  the wake phrases and who answers to each; where each counts follows the
  Conversation page's setting.
- **Changes, license, README**: the newest `CHANGELOG.md` entry, and each of
  the three documents opened read only in `less` with `LESSSECURE=1` through
  `omarchy-launch-tui` (an editor saving into the deploy checkout would leave
  it dirty, which `agentvoice-deploy` refuses).

**`CHANGELOG.md`** (new): one entry per phase, M26 back to M0, and a
paragraph for phases 1–16, condensed from the notes files (claims checked
against them; one rewritten, below).

**`install.sh`**: the VERSION stamp keeps line one as it was (all `build_id`
and `PREV_BUILD` read) and adds `commit=`, `branch=` ("detached"), and
`installed=`; git is asked only when `$ROOT` is its own checkout's top level
(a copy unpacked inside another repository was stamped with that one's
commit -- pre-existing for line one, fixed for both).

**CLI**: `agentvoice about [updates|backends] [--json] [--plugin DIR]`,
`agentvoice diagnostics [copy] [--plugin DIR]`, `agentvoice keys [--json]`.

**Also**: `ui/InfoRow.qml` (label + plain-text value); the spoken "Saved chats
are off. Turn on Save conversations in the Display settings" now says the
Chats page (it moved there in M18 and the sentence was not updated); the
Overview's "Turn them on in Display & privacy" likewise; stale "Display" in
comments; `agentvoice_skill.PAGE_LABELS`.

**Preview**: targets `other` (27 checks) and `about` (29 checks); stub cases
for `keys`, `about`, `diagnostics` and `endpoint probe-local`; a synthetic
bindings.lua, fake hyprctl (all but one line loaded), fake journalctl (with a
`PREVIEW-TRANSCRIPT` line the report must drop), fake omarchy-version, fake
claude/codex on a PATH of their own, a made-up install stamp and a day of
usage numbers; the editor and pager launchers log instead of opening; the
documents are copied into the preview's plugin folder. Copy, Check for
updates and Look only log and answer with fixed text.

**Docs**: README (the renamed page in three places, both builds in
"Diagnosing a turn", a new "Asking for help"), CODEBASE (both pages, the two
modules, `record_answer`, `probe_local`, `InfoRow`, the CLI verbs, the
targets).

## What was proven, and how

- **Tests**: new `tests/test_diagnostics.py` (57, with parameters) and
  `tests/test_other_about_pages.py` (15); `test_confirms.py` +3 (the journal
  question, its mutation, Repair/Remove on Other settings); `test_stats.py`
  +4. Rewritten to the new page: test_hud (2), test_agent_pages,
  test_chats_page (2), test_agents_panel, test_stats, test_confirms (the
  table's `stats clear` row and the scanner mutation), test_uninstall (the
  Remove button), test_commands (the spoken sentence).
  - **The seeded journal**: a reply sentence, a typed message, a progress
    line, an error's text with an `sk-proj-…` key, a rejected wake and a
    second check each quoting the canary, a carriage-return-rewritten line, an
    exception message, a good line followed by text after `\r`: the report
    holds none of them and keeps every structural line; settings holding the
    canary and the key in a URL's userinfo and query, a project folder, an
    agent's name, instructions and endpoint path show only as their kinds.
  - The clipboard: a fake wl-copy records argv (empty) and stdin (the text)
    and forks a child holding stdout; `copy()` returns in under 10 s.
  - The stamp: an M26 stamp read whole; an older one-line stamp gives its
    short commit, no branch and the file's time; junk (a `$(rm -rf ~)`
    branch, a canary commit) is left out; **install.sh's own stamp block run
    by bash** against a fresh repo, a detached one, a plain folder and a folder
    inside another repo, and read back by `read_stamp`, with `build_id`
    unchanged.
  - Two builds: same-code, differs, unknown commit, a dirty install, a
    plugin folder inside another repo, a caller's `GIT_DIR` ignored.
  - Updates against a local bare remote: current, newer, ahead; no remote;
    a remote that is gone; URLs shown without passwords.
  - Backends: answered only from the record; stats off claims nothing; an
    endpoint local or cloud by host, shown without its path.
  - The probe against a real local HTTP server: two models, nothing on a free
    port, no Authorization header, an `http_proxy` in the environment not used.
  - Keys: the file read, matched against a fake hyprctl list, the unloaded
    line marked, an `exec` binding found, junk lines left out.
- **Mutations: 22 real, 22 red** (scratch copy in /tmp, never the clone):
  structural filter keeping every line; pieces not split at `\r`; an
  exception's message kept; the clipboard text in argv; wl-copy's pipes held;
  keys not masked*; any text setting shown; a URL shown whole; any branch
  read from a stamp; found counted as answered; no remote asking origin
  anyway; a password kept in a URL; the probe through a proxy*; an answer
  counted on a failed turn; any program counted; an unloaded key shown
  loaded; the update check run when About opens; a document opened in an
  editor; AutoText in InfoRow; the display alias removed; the journal switch
  writing true itself; the bindings path unchecked. *The two starred
  survived the first run (below) and were caught after the tests were fixed.
- **Preview `other`, 27 of 27** (synthetic mouse events, scratch config,
  state and data, the pointer never moved), and the write log read back line
  by line: opening wrote nothing; the journal switch opened the question and
  wrote nothing; Cancel wrote nothing; Turn logging on wrote `logSpeech true`
  once; off wrote `logSpeech false` at once with no question; Open bindings
  file logged `omarchy-launch-editor …/hypr/bindings.lua` once; Repair logged
  the installer once (and dismissed the overlay, as before); Remove armed,
  Cancel removed nothing, the confirm logged `--uninstall --with-widget`
  once. The whole log was exactly those five lines.
- **Preview `about`, 29 of 29**: both builds and "Could not tell" (the
  preview's plugin copy is not a checkout); Claude Code "has answered 12
  turns here", Codex "installed; no turn answered here yet", the rest "not
  found", nothing called connected; the wake phrases and every command; the
  changelog's newest entry with its Markdown marks off; opening the page
  reached out to nothing; Show printed the report **without the
  PREVIEW-TRANSCRIPT line** and said one line was left out; Copy, Check for
  updates and Look each logged once and only on their clicks; License opened
  in `less` with LESSSECURE; no setting written.
- **Existing targets through the rename**: `confirms` (Remove on Other
  settings: armed, cancelled, confirmed → one `--uninstall` line), `chats
  drive` 7/7 (Ctrl+0 is Other settings; `goTo("display")` lands on `other`;
  Ctrl+PgDn reaches About), `overview clear` 7/7 (through the old id),
  `clicks` (opens `{"page":"display"}`; the first switch is still `hud`).
- **Read-only runs on this machine** (nothing written): `about` says
  settings a2c0900 (detached), service d4ad068 (unknown branch: installed
  before the new stamp), "different builds, but no daemon file differs" --
  which is true, M25 changed no daemon file; `keys` found the four bindings in
  bindings.lua and all loaded; `backends` found claude, codex, agy and
  copilot, Gemini not found; `updates` "tracks no remote"; `probe-local`
  nothing on either port; `diagnostics` (printed to my terminal, not copied)
  held the build lines, 23 changed settings by kind and 50 structural lines.
- **Screenshots** (`/tmp/m26`, not committed): 1100×760 dark (`other-dark-*`,
  `other-mid`, `other-privacy`, `about-dark-*`), flexoki-light
  (`about-light`), 520×720 (`about-narrow`, `other-narrow-light`; the crop
  cuts the overlay's right edge, as in M18 to M25).
- **Installer box**: `AGENTVOICE_BOX=1`: "installer in a box 9 passed, 0
  failed" (`install.sh` changed). That run was then killed during its test
  step by a 10-minute limit I had set on the background job; the tree did not
  change after it, and the full check was run again without the box (above).

## Shared files touched, and where

- `Settings.qml` (big shared): the page list entry, the `display` alias in
  `goTo`, the page component, the install problem's link (`about` → `other`),
  comments.
- `daemon/wake_listen.py` (big shared): one guarded `keep_stat(stats.
  record_answer, …)` after `count_turn` in `answer()`; the "Saved chats are
  off" sentence; two comments.
- `daemon/stats.py`, `daemon/endpoints.py`, `install.sh`, `bin/agentvoice`,
  `bench/preview/preview.sh`, `Hud.qml` (a comment), `pages/OverviewPage.qml`
  (one sentence), `daemon/readout.py` and `daemon/agentvoice_skill.py` (one
  line each).
- New: `daemon/diagnostics.py`, `daemon/keybinds.py`, `ui/InfoRow.qml`,
  `CHANGELOG.md`, two preview targets, two test files.
- Not touched: `runtime.py`, `manifest.json`, `Panel.qml`, `models.lock`.

## Measured

Nothing. No speed or size claim is made.

## Different from the plan, and why

- **Keys come from bindings.lua as well as hyprctl.** The plan says "read live
  from `hyprctl binds -j`, filtered to Agent Voice's commands". On Omarchy 4.5
  hyprctl does not report a Lua binding's command, so that filter matches
  nothing; the file says what each key runs and hyprctl says whether it is
  loaded.
- **"Has answered a turn" needed a record**, so stats gained `answered` per
  program and the daemon one line. The plan lists no daemon change for M26;
  without it the only honest statuses were "installed" and "not found".
- **The documents open in a read-only pager** rather than an editor or a
  browser (the deploy checkout must stay clean; the README is 1,600 lines).
  Only the changelog's newest entry is shown on the page.
- **The add-on installs moved with Repair** to Maintenance (the plan names
  Repair and Remove); About now changes nothing.
- **The update check names the remote and URL but cannot see past a deploy
  checkout**, which has no remote by design (M0). Live it says so.
- **`daemon/keybinds.py`** is a module the plan's file list does not name;
  it keeps the parser testable apart from diagnostics.
- **The Agents panel switch joined the readout group** (its own group before).
- **Codex review bypassed** by the user's decision.

## Found along the way

- **Pre-existing: the spoken "Saved chats are off" pointed to the Display
  settings**, where saving has not been since M18. Fixed, with its test.
- **My first local-probe list was named `LOCAL_SERVERS`, which endpoints.py
  already had** (a port → name map for error messages): the full check failed
  four endpoint tests with an AttributeError. Renamed `PROBED_SERVERS`. A
  fifth failure was test_uninstall still looking for Remove on About.
- **Two mutations survived the first run**: the key mask was never reached
  (every key in the seed was already removed by an earlier rule), and the
  proxy test could not see a module-level opener built before the test set
  `http_proxy`. A structural line carrying a key shape was added to the seed,
  and the opener is built per call; both now go red.
- **My re-read of the diff** found: install.sh would stamp a copy unpacked
  inside another repository with that repository's commit (now asked only of
  its own top level; the same was true of line one before this phase); a
  caller's `GIT_DIR` would have pointed every git question elsewhere (now
  stripped); an install from a dirty tree read as "the same build" (now
  said). Each has a test.
- **The preview's fake PATH needed `cat` and `sh`** for the fake hyprctl; the
  first `other` run marked no line as unloaded because hyprctl could not run.
- **Shot mode scrolled to the bottom before the first shot**; the scrolling
  now starts later.
- **Two existing targets FAILed when I first ran them with the wrong config**
  (voice.json); with their own (crew3.json and showcase.json) both pass.
- **The changelog entry rendered raw Markdown** on the page; the marks are
  taken off and hard-wrapped lines joined.

## Not verified

- **Both pages in the real shell.** Needs `omarchy-restart-shell` (not run).
  Seen only in `preview.sh`. Until it, the running shell shows M25's Display
  and About pages.
- **Live: Copy diagnostics, paste into a scratch file and read it for
  anything personal** (the plan's live check). Not done: it needs a click in
  the real shell, and copying from here would replace the person's clipboard.
  The report was printed to my terminal instead and read: build lines,
  settings by kind, structural lines only, home as `~`. The project folder's
  name does appear (`project: ~/Projects/agent-voice · trusted — never asks`),
  as a structural line; see Open issues.
- **Check for updates against a real remote**: tested against local bare
  repositories only; the deploy checkout here has none.
- **Look against a running Ollama or llama.cpp**: tested against a local test
  server; nothing listens on either port here.
- **Open bindings file, and the three documents in the pager**, in the real
  shell: logged by the preview stubs only.
- **The journal question by keyboard** (Tab, Enter on Cancel): not driven.
- **Remove on the live desktop**: never run, as the plan says.
- **The narrow layout** below 560 px: the crop cuts the overlay's edge.
- **The Codex review** (bypassed, not owed).

## Going back

`bin/agentvoice-deploy a2c090030cbc` from the clone, `./install.sh --yes` once
the daemon is idle (the daemon changed in this phase), then
`omarchy-restart-shell`. Nothing stored changes: no setting was added, moved or
renamed; an older daemon ignores the new VERSION lines and the stats day
file's `answered` field (both read tolerantly by M26 and simply unread
before).

## Open issues, for the next phase

1. **Codex review bypassed** for M26 (user decision, 2026-11-22). M12 stays
   "review owed".
2. **The project folder's path is in diagnostics**, home collapsed
   (`~/Projects/agent-voice`), because the daemon's `project:` line is
   structural. Default taken: kept, as "home paths as `~`" reads; the plan's
   "no folder text" read as the contents of agent folders. Dropping folder
   names too is one pattern change.
3. **Agent display names appear in diagnostics** (in "prompt for “Theo”" and
   similar lines). Default: kept; they are names the person chose, not speech.
4. **Keys are read only** (plan section 9). Default: as built.
5. **"Has answered a turn" starts counting now**: every backend reads
   "installed; no turn answered here yet" until its next answered turn, and
   reads "not recorded" while usage numbers are off. Default: as built (no
   back-fill from saved chats or the journal).
6. **Update check from a deploy checkout**: it tracks no remote by design, so
   it cannot say whether `fork` or upstream is ahead. Default: says so. Could
   be taught to ask the clone `agentvoice-deploy` came from.
7. **Carried, still open**: M25's 2–5; M24's 2–6; M23's 2–7; M22's 2–7;
   M21's 2–7; M20's 2–8; M19's 3–6; M18's 2–6; M17's 2–7; M16's 2–9; M15's
   2–8; M14's 2–7; M13's 2–9; M12's 2–7; M11's 1–7; M10's 1–8; M9's 2–7; M8's
   2–11; M7's 2–7; M6's 1, 3, 4; M5's 1, 4–6; M4's 4–13; M0's small test and
   bench fixes; agy's `carries_session_across`; the runner's sandbox test
   command.
