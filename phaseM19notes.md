# Phase M19: Chat names, summaries and search filters

Written 2026-11-23, unattended (started by the runner script). Branch
`phase-m19`, cut from `phase-m18` at 0ed266f. Result commit: the notes commit
on top of 9e9f743, pushed to `fork/phase-m19` only; `dev` fast-forwarded to it
and pushed to `fork`. Model: Claude Opus 5.5 (tier B in the plan).

Commits:
- 9e9f743: the phase;
- then these notes.

**Codex review: bypassed (user decision, 2026-11-22).** Codex was not run, for
review or anything else. In its place I re-read the whole diff before the
commit; what that found is under "Found along the way". Nothing in this phase
has been reviewed by a second model.

Deployed: **yes**, through `bin/agentvoice-deploy --install --wait 120
9e9f743` (its strict check green) with the daemon idle (state `listening`,
every agent idle, no open mic, no journal line in the five minutes before):
"deployed 9e9f7430daef. The way back: bin/agentvoice-deploy c94490ee0fb3".

Installed: **yes**: "Build 0.2.0 (9e9f743), replacing 0.2.0 (c94490e)". The
daemon (`chat_names.py`, `chats.py`, `runtime.py`, a hook in `wake_listen.py`)
and the CLI help changed. `install.sh` did not.

**Shell restart needed** (`Chats.qml`, `pages/ChatsPage.qml`). Not run. Until
it is, the running shell has M18's overlay: the list shows the written names
already (the index's `title` is the shown title, which the old QML reads), but
not the summaries, the duration, "named by", the filter hint, the "Left out"
note, or the **Names and summaries** switch. The switch is a setting
(`chatSummaries`), so `omarchy bar set duaneoca.agentvoice chatSummaries off`
works before the restart; the daemon reads it on every look.

A copy of `shell.json` was taken before the deploy
(`~/agentvoice-notes/shell.json.before-M19`, 0600); after the install and the
live checks it was byte-identical. No live check wrote a setting.

`./bin/agentvoice-check`: green on the final tree (exit 0, every line ok).
- **4759 tests** (was 4670; +89), 14 of 14 static checks, "the check wrote
  nothing in the tree: ok".
- Bare-runner variant (`AGENTVOICE_STRICT=1`, a venv with only
  requirements-dev): **green**, 4743 passed, 9 skipped (the same numpy-only
  skips as M18).
- Box: not run (`install.sh` did not change).
- The phase commit was made on a check read in full with its exit status.

## What was built

**A real name and a one-line summary for each saved chat**
(`daemon/chat_names.py`, the daemon's half in `wake_listen.py`).

- The instant title stays (`title_from`), stored now also as `instant_title`.
  Once a chat has been quiet **2 minutes**, the idle poll starts **one quiet
  side turn on the chat's own agent** -- its owner, on the program the chat
  was held with, so the words go to no provider that did not already have
  them -- which reads the chat and answers two lines, `Title:` and `Summary:`.
  They are cleaned (control and format characters out, one line, markdown and
  wrapping quotes stripped) and capped at **60** and **160** characters at a
  word, then stored in the chat file as `auto_title` and `summary`, beside
  `named_for` (the `updated` they were written for) and `named_at`.
- **A rename by the person always wins.** `renamed` is set by a rename from
  now on, and a title that is not the chat's instant one counts as a rename
  too, so a rename from before M19, or by an older build after it, is never
  hidden behind a written name (`chats.user_renamed`). What is shown
  (`display_title`): the rename, else the written name, else the first
  sentence. That is the index's `title`, so the list, the spoken "Two chats
  match: …", "Continuing …", Export and `chats list` all show the same one.
  A renamed chat still gets its summary.
- **At most one per chat per change** (a chat is looked at again only when
  `updated` moves) **and ten an hour** in all; the hour is seeded from the
  index's `named_at` at start, so a restart does not hand out ten more. A turn
  that comes back with no title still marks the change as tried.
- **Only chats used in the last day**: switching it on does not start on a
  year of old chats.
- **The side turn is Try it's** (M6): level ask, `no_tools` (Claude:
  `--tools ""` and `--strict-mcp-config`), none of Agent Voice's tools, no
  skills, no personality, instructions or roster, not spoken, `ephemeral`
  (`--no-session-persistence`). The request goes through the adapter's
  `send()`: on stdin, never argv. **Only Claude Code and plain endpoints**,
  the two backends where "no tools" is enforced (`try_it.backend_refusal`):
  the transcript is untrusted text, and a backend that could act on it is
  refused rather than trusted. Codex, Gemini, Antigravity and Copilot chats
  keep their first sentence.
- **Refused** while the screen is locked or that cannot be told, while any
  agent is busy or speaking or the microphone is lent, for a quarantined
  owner or unreadable crew settings, for an owner that is gone or now runs a
  different program from the chat's, and with `saveChats` or `chatSummaries`
  off or unreadable. It runs from the idle poll **below the listening gate**,
  so never while locked or muted, and **in a thread**, so a wake word said
  during the 2–5 s turn is heard. One at a time. Switched off while it ran:
  nothing is kept. Deleted while it ran: nothing comes back (`set_name`
  refuses a chat that is gone).
- The journal gets "chat named in 4.1s (39+105 chars)", "(chat not named:
  its program cannot run a turn with no tools)" and the like: seconds,
  lengths and fixed reasons, never the chat or the name.
- Titles and summaries live inside the chat file and its index entry (both
  0600), so a delete, an expiry and Delete all take them too.

**Setting**: `chatSummaries`, `off` / `owner`, default `owner` (question 5),
unreadable or saving off = off. Manifest schema and defaults,
`runtime.DEFAULTS` and `TOML_ALIASES` (`[ui] chat_summaries`),
`Config.chat_summaries()`, and a control on **Chats → Saving and privacy**:
"Names and summaries", Off / By the chat's agent, shown with saving on,
saying "About 2 to 3 seconds of its time per chat, at most ten an hour. A
rename of yours always wins." Its help says which programs, and why.

**More per chat** (`Chats.qml`): each row now shows who spoke, when, turns,
**how long it ran** ("3 min", "2 h", "over 3 days") and its **summary** (the
last line said until it has one); the open chat shows the summary under its
title and "named by Theo" when the shown name is the written one.

**Search filters** (`chats.parse_query`): `agent:NAME` (an id, the agent's
name now from the settings, or a name it answered under in that chat;
`agent:"Two words"`; several mean any), `after:DATE` (used on or after that
day), `before:DATE` (started before it); dates are `2026-11-01`, `2026-11`,
`today`, `yesterday`, `7d`, `2w`. Filters alone list every chat they pass,
newest first. A filter that cannot be read is left out **and said**
(`left out: …` on stderr; the page shows "Left out: before: needs a date
like 2026-11-01, today or 7d" under the box). The box's placeholder hints at
them ("Search chats, or agent:Theo after:7d"). Ranking extends the scorer:
every name the chat has had counts as a title (2), the summary 1.5, the body
1. The settings are read for names only when the query holds `agent:`.

**Faster scoring, no index** (FINDINGS §52): the scorer joins a chat's text
once, skips a chat that does not even contain the word as a substring, and
finds a word with one anchored `re.search` instead of splitting every
exchange into a set. Same results, about half the time over 1000 chats.

**Preview**: the `chats` seed gives the garden chat and the forecast a
written name and summary, and the pinned chat a rename over its written
name; `--arg names` adds two chats that open with the same words and are
about different things, and drives 17 checks. **Docs**: README (saved
conversations: names, summaries, filters), CODEBASE (`chats.py`,
`chat_names.py`, Chats.qml, ChatsPage.qml, settings), `bin/agentvoice` help,
FINDINGS §52.

## What was proven, and how

- **Tests** (`tests/test_chat_names.py`, 89 cases from 60 functions;
  `test_agent_fixtures` adjusted for `instant_title`):
  - **A summary never overwrites a rename**: a written name shows until a
    rename and never after; a name written after a rename never shows; a
    rename to the first sentence's own words still wins; a rename from
    before M19 (no `instant_title`, no `renamed`) wins; a rename by an older
    build after M19 (title changed, no flag) wins; a legacy chat never
    renamed does take a name; `set_name` never touches `title`.
  - **The side turn's text travels on stdin**: through a real `ClaudeCode`
    built by `make_side`, with `subprocess.Popen` replaced: the canary is in
    what was written to the process's stdin and in no argv element; and
    `_argv` of the request holds `--tools ""`, `--strict-mcp-config`,
    `--no-session-persistence` and no canary.
  - **Cleaning and caps**: bidi overrides, zero-width characters, escape
    sequences, markdown and quotes out; 60 / 160 cut at a word with "…"; no
    title is no name; a recorded **real** reply (below) parses.
  - **The rate limit**: ten an hour, the eleventh refused, one back when the
    oldest leaves the hour, seeded across a restart (in the store and driven
    through the daemon).
  - **Nothing written with saving off**: saving off, switch off, a misspelt
    value, locked, cannot tell, speaking, quarantined owner, a different
    program: each builds nothing, sends nothing and leaves the chat file
    byte-identical. Switched off mid-turn: nothing kept.
  - **Derived text gone after a delete**: a canary in the name and summary
    is in no file in the folder after delete, expiry (`prune 30d`) and
    Delete all; a name for a deleted chat recreates nothing; files 0600, the
    folder 0700.
  - **Legacy, renamed, multi-speaker and corrupt fixtures**: a multi-speaker
    chat names every speaker in the request; a chat with non-string
    `auto_title`, a dict `summary`, junk exchanges and no index still lists
    with a title and builds a request; an unreadable file takes no name.
  - The request: fenced, the chat cannot close its fence, the first exchange
    and the newest kept with a "left out" marker, one huge exchange still
    leaves something, asides labelled as agents' words.
  - The daemon: named by its own agent, the title untouched, the journal
    with no words (`capsys`, canary); once per change then again after the
    next; a Codex chat refused once, not every poll; a removed agent's chat
    left alone; a reply with no name tried once; a failing side turn never
    reaches the loop; the turn runs beside the loop (the idle poll returns
    at once, a second look says "running"); the run loop calls it on the
    idle poll below the listening gate (source order); an AST check that no
    print or `say_once` in the namer reads a name holding chat text.
  - Search: `after:`, `before:`, `agent:` by id, name now, saved label, a
    quoted name, two agents; filters alone; an unreadable filter said and
    left out; `reagent:x` is a word; titles outrank summaries; `find` by
    voice uses the written name and the summary; the CLI takes filters on
    stdin and reports what it left out; `show` and `list` show the name.
  - The setting's three parts and its fail-closed reading.
- **Mutations: 33 run, 33 red** (a scratch copy under /tmp, never the
  clone): the legacy rename not detected; a written name over a rename;
  rename not setting `renamed`; `set_name` writing `title`; `set_name`
  recreating a deleted chat; the mode ignoring saving, ignoring unreadable
  settings; `due` ignoring `named_for`, without the freshness window, without
  the idle wait; the budget never running out, not seeded at start; each of
  the nine refusals dropped (lock, undetermined lock, quarantine, unreadable
  crew, different program, tool-capable backend, busy); control characters
  kept; no cap; the fence not escaped; the side turn keeping tools, keeping a
  session, getting a personality; no re-check after the turn; the journal
  printing the name; the namer not called from the poll; a refused chat
  retried every poll; `after:` ignored; `agent:` ignored; a bad filter
  swallowed; the summary not ranked. The last **survived at first**: every
  ranking test searched one word, which takes the prefix branch; a test of a
  summary word by voice (`find`) and as a non-last word was added, and it
  went red.
- **Preview** (`preview.sh`, synthetic mouse and key events, scratch data,
  config and runtime folders, the real pointer never moved):
  **`chats --arg names` 17 of 17 PASS**: nine chats; the two alike openings
  show "Yellowing tomato leaves" and "Laptop battery drain in suspend"; a
  row shows its summary; the renamed pinned chat shows "Release checklist",
  not its written name; no row titled with the shared first words; "named by
  Theo" and the summary on the open chat; the filter hint; `agent:sora
  after:3d` answered by `chats search`, keeping Sora's chats from today and
  dropping her five-day-old one, with the filters in no argv; `garden
  before:someday` shows "Left out: before: …"; the switch on the page with
  its cost; Off writes `chatSummaries "off"`, and back to `"owner"`.
  **`chats --arg drive` 31 of 31 PASS** (M18's, with the placeholder
  matched by its start). **`confirms`**: every DangerButton cancelled writes
  nothing; the chat's Delete 3 → 2, Delete all 2 → 0.
- **Screenshots** (`/tmp/m19`, not committed): 1100×760 dark (names: the
  list, the open chat, the card with the switch, the "Left out" note),
  flexoki-light, and 520×720 (the crop cuts the overlay's right edge, as in
  earlier phases).
- **A real side turn** (FINDINGS §52): Claude Code 2.1.330 through
  `make_side` over `adapters.load`, on synthetic chats: 2.2–3.0 s, every
  reply the two lines asked for, the alike openings named apart. One run is
  `tests/fixtures/chat-names/claude-replies.json`, replayed by a test.
- **Live, on the installed build**: see the checklist at the end.

## Shared files touched, and where

- `daemon/wake_listen.py` (big shared, 7,120 → 7,259): `import chat_names`;
  `name_chats` and `_name_one` after `handle_try` (130 lines, the daemon's
  half: who owns the chat now, its program, busy, the thread); one guarded
  call after `refresh()` in the idle poll; "Continuing …" says the shown
  title. Nothing in the turn loop or the wake path changed.
- `Chats.qml` (1,029 → 1,086): `openMeta` / `openTitle` / `openSummary`,
  `durationOf`, `plainWords`; the row's meta line and summary; the open
  chat's summary and "named by"; rename compares with the shown title; the
  search's stderr note; the placeholder.
- `daemon/chats.py`, `daemon/runtime.py`, `manifest.json`,
  `pages/ChatsPage.qml`, `bin/agentvoice` (help), `README.md`, `CODEBASE.md`,
  `bench/FINDINGS.md`, `bench/preview/targets/chats.{qml,seed.py}`; new
  `daemon/chat_names.py`, `tests/test_chat_names.py`,
  `tests/fixtures/chat-names/claude-replies.json`.

## Measured

FINDINGS §52, on the i7-1185G7:
- **The side turn on Claude Code**: 2.2–3.0 s, median 2.4 s (12 turns on
  synthetic chats, default model, a cold process each time). On the installed
  build, Theo's chats (Opus) took 3.4–5.6 s a turn (twelve turns, from the
  journal). Other backends are refused, so cost nothing; an endpoint was not
  measured (none configured). At the cap, at most about 30–50 s of an agent's
  time an hour.
- **Search over 1000 synthetic chats** (8.4 MB): `chats search --json`, as
  the page runs it, **283 ms median, 305 ms p95** for a query most chats
  match (was 588 / 625 with M18's scorer); 240 / 250 for a word no chat
  holds; 339 / 380 with `agent:` (the settings read for names). In process
  177 / 183 ms (was 374 / 425). **No index file**: under a third of a second
  at 1000 chats, after the box's 250 ms pause; this machine has 41.

## Different from the plan, and why

- **Claude Code and plain endpoints only.** The plan says "the chat's own
  agent"; section 7.5 says summaries run with "no tools". Only those two
  backends can start a turn with none (Try it's rule, recorded in M6), and
  the transcript is untrusted text, so a Codex, Gemini, Antigravity or
  Copilot chat keeps its first sentence and the switch's help says why.
- **"The provider that already has the conversation"** is taken as the
  owner's program *as the chat recorded it*: an agent switched to another
  program since does not get its old chats sent to the new provider.
- **Only chats used in the last day** (`FRESH_S`), so turning it on (or
  upgrading, since it is on by default) does not name a year of chats. Not in
  the plan; the alternative was up to ten side turns an hour on old chats
  until every one had a name.
- **Quarantined owners and unreadable crew settings are refused**: the plan
  does not say; a quarantined agent should not be taking turns nobody asked
  for, and an unreadable quarantine list closes, as everywhere since M8.
- **Not while muted**: the call sits below the listening gate with
  `refresh()`. Muting for an hour means no names for that hour. Deliberate
  (the gate is also what keeps it off while locked).
- **A summary is written for a renamed chat**; only the written *name* is
  never shown over a rename.
- **The scorer was made faster** (same results), which is what made an
  index unnecessary at 1000 chats.
- **More than the plan's filters**: relative dates (`today`, `yesterday`,
  `7d`, `2w`) and month dates (`2026-11`).
- **Codex review bypassed** by the user's decision.

## Found along the way

- **The first summary prompt overran its cap a third of the time** ("at most
  25 words"; 2 of 6 real summaries past 160 characters, cut with "…") and
  wrote "Person asked…". "At most 20 words" and "about the subject itself,
  not about who said what": 0 of 6 cut, and subject-first sentences.
- **Search over 1000 chats took 0.6 s** with M18's scorer, almost all of it
  splitting every exchange into word sets (profiled). Fixed without an index
  (above). My first attempt sliced a lower-cased joined string by the
  original lengths, which `str.lower()` does not preserve for every
  character (İ becomes two); caught on re-reading before it was measured,
  and the parts are lowered separately.
- **The ranking mutation that survived** (above): every search test was one
  word, so the non-prefix branch of the scorer was untested for summaries.
- **My re-read**: the per-chat refusal memory would have grown with every
  deleted chat (now kept only for chats still listed unchanged); the switch
  showed "By the chat's agent" for a misspelt value the daemon treats as off
  (it now shows Off for anything but `owner`); the settings were imported on
  every CLI search for agent names (now only with `agent:`); a stale comment.
- **Preview**: my first `names` check expected `after:7d` to drop a
  five-day-old chat (the check was wrong, not the page; it uses `after:3d`
  now); a drive run with `--wait 3` ended before the drive did (M18's 31
  checks need about 40 s).
- **Upgrading names a burst of chats at once**: right after the install the
  daemon named ten recent real chats in about two and a half minutes, one
  every 15 s look, then stopped at the cap, exactly as written. It means the
  first hour after an upgrade (or after switching it on) spends its ten at
  once; see Open issues 3.

## Not verified

- **The page in the real shell.** It needs `omarchy-restart-shell` (not
  run). Seen only in `preview.sh`: the switch, the summaries, the duration,
  "named by", the filter hint and the "Left out" note against a real pointer
  and the real store were not driven.
- **What the written names and summaries of the user's real chats say.**
  Ten were written on the installed build; deliberately not read (only
  counts and lengths: titles up to 56, summaries up to 121 characters).
  Worth a look at the next stop point: are they good names, and is "on by
  default" right?
- **An endpoint chat named** (none configured here) and **a renamed real
  chat** (none of the 41 is renamed).
- **The narrow layout** (below 560 px), as in M18: never drawn.
- **The installer box** (`install.sh` did not change).
- **The Codex review** (bypassed, not owed).

## Going back

`bin/agentvoice-deploy c94490ee0fb3` from the clone, `./install.sh --yes`
once the daemon is idle, then `omarchy-restart-shell`. An M18 build ignores
`instant_title`, `renamed`, `auto_title`, `summary`, `named_for` and
`named_at` (harmless: they stay in the files) and shows each chat's `title`,
the first sentence or the person's rename, exactly as before; its index
rebuild writes the first sentence back as the listed title. It ignores
`chatSummaries` (the key stays in shell.json). Search filters become plain
words there (`agent:sora` matches nothing). A rename made under M18 after
M19 named a chat still wins when M19 comes back (`user_renamed`).

## Open issues, for the next phase

1. **Codex review bypassed** for M19 (user decision, 2026-11-22). M12 stays
   "review owed".
2. **Question 5 (on by default)**: default taken, **on** (`owner`). The
   installed build has named ten of the user's recent Claude chats. If the
   answer is "off by default", change `DEFAULTS` and the manifest default;
   the names already written stay unless the chats are renamed or deleted.
3. **The first hour spends its ten at once.** Should the cap also space the
   turns out (say one every six minutes), or should the backlog of the last
   day not be named at all on first start (only chats that go quiet while
   the new daemon runs)? Default taken: as written (ten an hour, one per
   15 s look, last day only).
4. **Codex, Gemini, Antigravity and Copilot chats are never named.** If one
   of them can be shown, with a recorded turn, to start with no tools, it can
   join `try_it.backend_refusal`'s list and both Try it and this follow.
   Alternatively a chat could be named by a different, no-tools agent (a
   Claude agent) -- but that sends the chat to a provider that did not have
   it, which the plan's wording rules out. Default: not named.
5. **A rename cannot be undone back to the written name.** Renaming to
   exactly the written name keeps it as a rename (it then never changes
   again). Should there be "Use the written name" on a renamed chat?
   Default: no control.
6. **A lock that lands mid-turn does not cancel the side turn**: it was
   refused at the start, writes only into the chat file, shows and says
   nothing. Should it be cancelled anyway?
7. **Carried, still open**: M18's 2–6; M17's 2–7; M16's 2–9; M15's 2–8;
   M14's 2–7; M13's 2–9; M12's 2–7; M11's 1–7; M10's 1–8; M9's 2–7; M8's
   2–11; M7's 2–7; M6's 1, 3, 4; M5's 1, 4–6; M4's 4–13; the Voice library
   trash icon (M25); M0's small test and bench fixes; agy's
   `carries_session_across`; the runner's sandbox test command.

## Live checklist: what was done, what happened

Nothing was said into the microphone. One typed turn to Theo, spoken aloud by
the daemon as any typed turn is.
- Before the deploy: state `listening`, every agent idle (`''`, `sora`,
  `jarvis-ajc`), no open mic, no journal line in five minutes; `shell.json`
  copied (0600).
- `bin/agentvoice-deploy --install --wait 120 9e9f743`: strict check green;
  "deployed 9e9f7430daef. The way back: bin/agentvoice-deploy c94490ee0fb3";
  "QML changed: run omarchy-restart-shell? (not run)"; "Build 0.2.0
  (9e9f743), replacing 0.2.0 (c94490e)". Service active.
- The journal after the restart (`-o json`, structural lines only): ten
  "chat named in 3.7s–4.9s (NN+NNN chars)" lines in about 2.5 minutes, then
  none (the cap), no error, no traceback.
- The real chats folder, **counts only** (the index read by a script that
  printed numbers): 41 chats, 10 now shown by a written name, 10 with a
  summary, all Claude chats, 0 renamed, 10 `named_at` in the last hour, 5
  used in the last day still waiting for the cap; the longest written title
  56 characters, the longest summary 121; index mode 0600.
- `agentvoice chats new main`, then one typed turn to Theo with synthetic
  text and a canary ("Synthetic check for phase M19, canary WALRUS-5521: …
  which three colours are lighthouses usually painted?"). Found by `echo
  "walrus 5521" | agentvoice chats search --json` (the query on stdin), one
  hit.
- It waited for the cap (the ten real chats above had used the hour) and was
  named in the first free slot, at 02:08:29, an hour after the first of the
  ten: "chat named in 5.6s (33+93 chars)" in the journal, and `agentvoice
  chats show` on that chat alone: **"# Usual colours of lighthouse paint"**
  (instant title "Synthetic check for phase M19, canary WALRUS-5521: in
  one…") with the summary "_Lighthouses are usually painted white, red and
  black, per a brief M19 synthetic check answer._". The written name shows,
  the instant title is kept in the file, the summary sits under the title in
  Export. **Titles and summaries appear after the idle time: verified live**
  (for a typed turn; delayed here by the cap, not by the idle time).
- Cleanup: `agentvoice chats delete` of that synthetic chat (the canary then
  in no file in the chats folder, the search empty) and `agentvoice chats new
  main`, so Theo's next turn starts a fresh chat rather than continuing the
  synthetic one. Theo's previous real chat is saved and can be continued.
- `shell.json` byte-identical to the copy afterwards. No shell restart.
