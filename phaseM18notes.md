# Phase M18: Chats page

Written 2026-11-22, unattended (started by the runner script). Branch
`phase-m18`, cut from `phase-m17` at 1d61a51. Result commit: the notes commit
on top of the fix commit after 7d8b9b1, pushed to `fork/phase-m18` only; `dev` fast-forwarded to it
and pushed to `fork`. Model: Claude Opus 5.5 (tier B in the plan).

Commits:
- 7d8b9b1: the phase;
- c94490e: a deletion time stored exactly, not rounded (found by a flaky
  check run after the phase commit; see "Found along the way");
- then these notes.

**Codex review: bypassed (user decision, 2026-11-22).** Codex was not run, for
review or anything else. In its place I re-read the whole diff before the
commit; what that found is under "Found along the way". Nothing in this phase
has been reviewed by a second model.

Deployed: **yes**, twice, each through `bin/agentvoice-deploy --install --wait
120` (its strict check green) with the daemon idle (state `listening`, every
agent idle, no open mic, no task, no journal line in the five minutes
before): 7d8b9b1 ("deployed 7d8b9b118b6a. The way back: bin/agentvoice-deploy
d7c3918c2528"), then the fix c94490e ("deployed c94490ee0fb3. The way back:
bin/agentvoice-deploy 7d8b9b118b6a"). **The way back to before M18 is
`bin/agentvoice-deploy d7c3918c2528`** (see "Going back").

Installed: **yes**, twice: "Build 0.2.0 (7d8b9b1), replacing 0.2.0
(d7c3918)", then "Build 0.2.0 (c94490e), replacing 0.2.0 (7d8b9b1)". The
installed build is c94490e. The
daemon (`chats.py`, a small hook in `wake_listen.py`), the skill's page
labels and the CLI help changed. `install.sh` did not.

**Shell restart needed** (`Settings.qml`, `Chats.qml`, `Panel.qml`, the new
`pages/ChatsPage.qml`, `pages/{AgentDetails,Communal,Display,Overview}Page.qml`,
`ui/ChatBubble.qml`, `ui/ExchangeItem.qml`). Not run. Until it is, the running
shell has M17's overlay: the Conversation button, the history mode and the
privacy settings on Display all still work against the new daemon, because no
setting changed name and the old QML never runs a new verb. The one new
daemon behaviour (a save in flight after a delete is refused) applies to the
old overlay's single Delete too.

A copy of `shell.json` was taken before the deploy
(`~/agentvoice-notes/shell.json.before-M18`, 0600); after the install and the
live checks it was byte-identical. No live check wrote a setting or touched a
real chat.

`./bin/agentvoice-check`: green on the final tree (exit 0, every line ok).
- **4670 tests** (was 4629; +41), 14 of 14 static checks, "the check wrote
  nothing in the tree: ok".
- Bare-runner variant (`AGENTVOICE_STRICT=1`, a venv with only
  requirements-dev): **green**, 4653 passed, 9 skipped (the same numpy-only
  skips as M17).
- Box: not run (`install.sh` did not change).
- The phase commit was made on a check read in full with its exit status (the
  first full run found two failures, both tests pinned to the old layout,
  below).

## What was built

**A Chats page in the sidebar** (`pages/ChatsPage.qml`), sixth, after the
Crew map, where the mockup puts it. The overlay's second mode ("history") and
the lone **Conversation** button on its top row are gone: the button's name
collided with the Conversation settings page, which keeps its name (feedback
items 5 and 13's rename). The bar popup's button now says **Chats** and opens
the page; the readout's click and Overview's "Open the whole conversation"
open it too. An older bar or HUD's summon (`{"mode":"history"}`, with or
without a `chat`) still lands on the page. The card is a little wider on this
page (980 instead of 880) so a list and a chat fit side by side.

- **Saving and privacy** (a foldable `Card` at the top): `saveChats`,
  `chatRetention` and `keepHistory`, moved from Display with the same names,
  values and controls (feedback item 20); where the chats are and how much
  room they take (`agentvoice chats stats --json`, read when the page opens,
  when the number of saved chats changes and after a delete -- not on a
  timer); and **Delete all saved chats**, a `DangerButton` whose question
  states the count and the scope ("Delete all 7 saved chats, every agent's,
  pinned too?") with a line beside it saying what it does not touch. Folded
  by default once chats are saved (its subtitle then summarises: "Saving on ·
  kept forever · 7 chats, 9.0 KB"); open while nothing is saved, so the switch
  that saves is in plain sight. Once opened or folded it stays so for the
  session.
- **Display** keeps a "Saved chats → Go to Chats" row where the three
  settings were; the "Go to Display →" buttons on Agent details and Communal
  now go to Chats.
- **Eleven pages.** Ctrl+1..9 the first nine, Ctrl+0 the tenth (Display),
  Ctrl+PgUp/PgDn to step; About, the eleventh, by a click and Ctrl+PgDn (M28
  adds search).

**One browser, three places** (`Chats.qml`): the Chats page (this session
first, then every chat), Agent details → Chats (`scope: "agent"`: the chats
that agent owns, has spoken in or may carry on, with "passed to it" or
"shared" for those it does not own, as before) and Communal → Chats
(`scope: "multi"`: chats more than one agent spoke in). Only the page's
instance follows `s.openChat`, so a chat opened in an embedded one does not
move the page's.
- **The list**: grouped Pinned / Today / This week / Older; each row the
  title, who spoke ("Theo + Sora"), when, how many turns, "in use", and the
  last thing said (the summary until M19 writes one), with the owner's
  colour down its left edge. Filter chips (Agent conversations, then one per
  agent: chats that agent owns or spoke in), on the page only.
- **Search** (`ui/SearchField`): a moment after typing stops, or on Enter,
  `agentvoice chats search --json` with **the words on stdin**; the list
  becomes one "Best matches" group in score order. Until it answers (or if it
  cannot run) the list filters on what it already holds, and says why when
  the search could not run.
- **The open chat** as a messaging app draws one: you on the right in the
  theme's accent tint; each agent on the left, always named, in **its own
  colour** (`Settings.agentTint`: the main agent has the accent, every other
  agent the accent turned round the colour wheel by a step its id picks, so
  colours follow the theme and survive adding or removing an agent); a
  question one agent asked another folded to one line that opens to both
  agents' bubbles; thinking folded; "failed" / "stopped part-way" under the
  answer. All of it plain, selectable text.
- **Actions kept**, in three rows: Continue / Continue with X / **New chat**
  (`chats new OWNER`); Send to another agent / Share with…; Rename / Pin /
  Export / Delete. A rename now sends the title **on stdin** (`chats rename
  ID`, one line).
- **Narrow**: below 560 px the list and the chat take turns, with "← All
  chats" (not seen at that width in the preview: see "Not verified").

**`daemon/chats.py`**:
- `delete_all()` → how many chat files went. Only `<16 hex>.json` files and
  the temporary files they are written through, directly in the chats
  folder; a link there is removed as a link (never followed, not counted);
  any other name, a folder, or anything below is left; a missing folder is
  not created, and a chats folder that is itself a link is not followed. The
  index is rewritten `{"chats": [], "current": {}, "purged": NOW}`.
- **An in-flight save never brings deleted history back.** `record()` takes
  `began` (when the turn was sent; `wake_listen` passes `clock["sent"]`) and
  refuses -- returns None, writes nothing -- a turn that began before the last
  `delete_all` or before its own chat was deleted (a single `delete` now
  remembers the id an hour, in the index's `deleted`). The daemon then says
  "chat not saved: deleted while the turn ran", drops that turn's asides too,
  and its next turn starts a fresh chat. Without `began` (old callers) it
  saves as before.
- `stats()`: dir, exists, chats, pinned, bytes; regular files only, by lstat;
  creates nothing.
- `search(query, agent=None)`: every chat (the person sees every chat) or one
  agent's, scored by the scorer "continue the chat about" uses (now the
  shared `score()`), with the last word also a prefix so a box being typed
  into finds "wake" from "wak". The spoken `find` is unchanged.
- CLI: `delete --all`, `stats [--json]`, `search [--agent ID] [--json]`
  (words on stdin; words in argv are a usage error), `rename ID` (title on
  stdin; `rename ID TITLE` still works for a terminal).

**Preview**: a `chats` target and seed (synthetic: a chat passed from Theo to
Sora with an aside to Hazel and some thinking, a pinned long title, a renamed
agent, a removed agent, unicode, text that looks like HTML, a failed and a
stopped turn, dates from today to a year ago, and -- with `--state` -- a
200-exchange session written into the scratch runtime folder). Views: list,
empty, html, session, details, communal, and **drive** (31 checks). The stub
now logs every `chats` call's argv to `OUT.chats` (argv only), logs `continue`
as well as `new` instead of sending it to the real daemon, and without
`--scratch-data` logs every writing verb (rename, pin, share, export, delete)
instead of writing a real chat. `confirms` covers Delete all and matches the
chat's Delete exactly.

**Docs**: CODEBASE (layout, `chats.py`, pages, `ui/`, settings, CLI), README
(the conversation, saved conversations, Delete all, the layout list),
`bin/agentvoice` help lines.

## What was proven, and how

- **Tests** (`tests/test_chats_page.py`, 39 functions; six adjusted
  elsewhere):
  - **`delete --all` removes only files in the chats folder, never a link
    target, and reports the count**: three chats (one pinned) gone and "3"; a
    link to a file outside and a dangling one removed as links, the outside
    file byte-identical, neither counted; `notes.txt`, `README.json`,
    `0123.json`, an upper-case id, a subfolder's chat file and `.lock` kept;
    a half-written temporary removed; no folder created; a chats folder that
    is a link not followed; nothing of a deleted title left in the index.
  - **An in-flight save does not recreate deleted history**: in the store
    (began before the purge: None, nothing written, for an existing chat and
    a new one; began after: saved into a new chat; one deleted chat holds off
    only its own late turn; ids forgotten after an hour; a damaged marker
    never stops a save) and **driven through the real `answer()`** (a backend
    whose turn runs `delete_all`, then `delete`, mid-turn: no chat afterwards,
    the structural line printed, the next turn a fresh one-turn chat).
  - **The query arrives on stdin**: the CLI through `bin/agentvoice` finds by
    stdin and refuses words in argv (exit 2); the page's search Process has
    the words nowhere but `write(pending)`; rename the same.
  - Search ranking, the typed-prefix rule (only the last word), filler, one
    agent's scope (shares included), a long query, nothing saved (no folder
    made), a damaged date; stats (nothing created, a link not counted, pinned).
  - **The one-page test** (`test_settings_pages`) with the three keys on
    ChatsPage; `test_chats_page` asserts none is left on Display.
  - **The confirm test covers `delete --all`**: a new row in
    `test_confirms.DESTRUCTIVE` ("chats delete --all": built only in
    ChatsPage's `purger` Process, started only by `deleteAllChats()`, which
    only a DangerButton's `onConfirmed` calls).
  - The page structure: the sidebar entry, no top-row button, no history
    mode, the old summon mapped, every way in, one browser in three places,
    the confirm's count and scope, the skill naming the page "Chats".
  - Adjusted: `test_history` (the summon, plain text now held in ChatBubble
    and ExchangeItem, Clear on "This session"), `test_agent_pages` (eleven
    pages in order), `test_chats` (the keys' page), `test_communal` (the
    stub's `new|continue`), `test_confirms` (the new row).
- **Mutations: 21 run, 20 red, 1 survived as an equivalent and was replaced
  by one that goes red** (a scratch copy under /tmp, never the clone): delete_all following a link, deleting any name, counting
  links, creating the folder; no in-flight guard; no purge time; a single
  delete not remembered; the daemon not passing `began`; the daemon going on
  after a refused save; stats creating the folder; stats counting what a link
  points at (the first version of that mutation, "stats follows links",
  survived because links are skipped before any size is read -- equivalent,
  so the docstring was corrected and the real guard mutated); search taking
  argv; no typed prefix; search ignoring the agent; the title in argv; the
  search words in argv; Delete all from a plain handler; the purger started
  elsewhere; a bubble rendering markup; a key left on Display.
- **Preview** (`preview.sh`, synthetic mouse and key events, scratch data,
  config and runtime folders, the real pointer never moved):
  **`chats --arg drive` 31 of 31 PASS** -- eleven pages, Ctrl+6 Chats, Ctrl+0
  Display, Ctrl+PgDn to About, no Conversation button; seven chats listed; an
  HTML-looking title drawn as plain text; a renamed agent under its current
  name, a removed one under its saved name; **keyboard: focus the search
  box, type, Enter** → answered by `chats search` with the words in no argv
  (`OUT.chats`) → Tab to the best match, **Enter opens it** → bubbles on both
  sides, Sora and Theo in different colours, the aside folded → **Space on
  Continue** runs `chats continue ID` (logged, not sent); Rename on stdin
  landed and not in argv; the Hazel chip keeps the one chat she spoke in, a
  second click shows all; the card folded with chats saved, opened from the
  keyboard; **Delete all armed → Enter on Cancel deletes nothing and runs
  nothing**; armed → confirmed leaves no chat and says how many went.
  **`confirms`**: every DangerButton cancelled writes nothing and confirmed
  runs once, the chat's Delete (3 → 2) and Delete all (2 → 0) included.
  **`shared --arg send`**: the send sheet opens over the Chats page and
  `agentvoice pass …` is logged.
- **Screenshots** (`/tmp/m18`, not committed): 1100×760 dark (list, html,
  session with 200 exchanges, details, communal, empty), flexoki-light, and
  520×720 (the crop cuts the overlay's right edge, as in earlier phases).
- **Live, on the installed build**: the journal after the restart, 30 lines
  read with `-o json`, none with an error; the installed CLI on a scratch
  data folder: search by stdin (a canary found), words in argv refused,
  stats, rename by stdin, `delete --all` printing 2 and leaving `index.json`
  and `.lock`; the real chats folder's stats read (counts only: 40 chats,
  179,741 bytes); `shell.json` byte-identical afterwards.

## Shared files touched, and where

- `Settings.qml` (big shared, 2,281 → 2,172): the page entry, the
  loader line and Component; the header comment; `mode` is "settings" or
  "permission" (the old summon's "history" maps to the page in `open()`);
  `showChat` goes to the page; `openSendSheet` opens over the current page and
  the sheet closes on a page change; `chatsSettingsOpen`, `chatsShown`,
  `agentTint`; the history timer runs while the page is shown; the card's
  width; the top-row button and the old history body (about 130 lines)
  removed.
- `pages/AgentDetailsPage.qml` (big shared, 3,544 → 3,443): its own
  chat index, list and helpers replaced by `Chats { scope: "agent" }`;
  "Go to Chats".
- `daemon/wake_listen.py` (big shared, +15 −5): `remember`/`save_chat` take
  `began`; `answer()` passes `clock["sent"]`; a refused save prints one
  structural line and returns. Nothing else in the turn loop changed.
- `Chats.qml` (rewritten around the same files and verbs), `Panel.qml` (the
  button's label and icon, the summon payload), `pages/CommunalPage.qml`,
  `pages/DisplayPage.qml`, `pages/OverviewPage.qml`, `pages/qmldir`,
  `ui/ChatBubble.qml`, `ui/ExchangeItem.qml`, `daemon/chats.py`,
  `daemon/agentvoice_skill.py` (page label), `bin/agentvoice` (help),
  `bench/preview/preview.sh`; new `pages/ChatsPage.qml`, the `chats` target
  and seed; tests as above.

## Measured

On the i7-1185G7, 200 synthetic chats of 10 exchanges, 15 runs each: the
page's `chats stats --json` is a 101 ms process (p90 105); `chats search
--json` 174 ms (p90 196), of which 6.5 ms is the search itself in process.
Neither polls: stats runs on open, when the saved count moves and after a
delete; search a quarter second after typing stops. Not put in FINDINGS: no
claim rests on them, and M19 measures search over 1000 chats as the plan
asks.

## Different from the plan, and why

- **The search box searches every saved chat**, not one agent's: the person
  sees all of them on this page. The scorer is today's, with one addition the
  box needed: the last word also matches as a prefix, so results appear while
  a word is still being typed. The spoken "continue the chat about" is
  untouched.
- **"Tool lines dim"**: saved chats hold no tool lines today (an exchange is
  what was said and answered), so there is nothing to dim; `ChatBubble`'s
  quieter `kind: "note"` is ready for M19 or later if they are kept.
- **A save in flight is refused by the turn's start time**, and a single
  Delete got the same protection (the plan asks it of the bulk delete). The
  exchange in flight is lost with the rest, which is what deleting it meant.
- **"New chat"** joins the chat's actions (the plan lists "new" among the
  existing actions; there was no button for it in the browser).
- **Rename moved to stdin** (a title is often the first sentence somebody
  said; 7.6 says typed and chat text never goes in argv).
- **The card is wider on the Chats page** (980 rather than 880), so the chat
  is not squeezed beside the list.
- **The settings card folds** once chats are saved, to leave the browser the
  page's height; open while nothing is saved.
- **Preview stub**: `continue` is logged like `new` (it reached the real
  daemon's socket from a preview), and writing verbs are logged without
  `--scratch-data`.
- **Codex review bypassed** by the user's decision.

## Found along the way

- **A flaky check after the phase commit: a deletion time was stored rounded
  to the millisecond.** `test_one_chat_deleted_during_a_turn_stays_deleted`
  failed once in the check run for these notes and passed alone: when the
  delete came within a millisecond of the turn being sent, `round(now, 3)`
  could fall *below* the turn's start, and the in-flight guard let the save
  through. In real use that needs a click within a millisecond of a turn
  starting, but it is a hole in a guard, so the times (`purged`, `deleted`)
  are now stored exactly, in a separate commit, with a test that is red
  against the rounded version; the driven test then passed 30 runs of 30.

- **The overlay froze on a long session.** ChatBubble measured its text with
  a hidden `Text`; with 200 exchanges in "This session" the ListView never
  settled and Quickshell stopped responding (no further log line, timers
  stopped). My synthetic runs had no session, so it showed only when the
  `confirms` target ran without `--state` and read the real session's 200
  exchanges. Bisected in a scratch copy (fixed width: no freeze; FontMetrics:
  no freeze); it now uses `FontMetrics`, and the `chats` seed writes a
  200-exchange session so the drive run covers it.
- **A preview without `--state` reads the real session history** (the
  runtime folder): the `confirms` target always has. Only the count showed
  in its screenshot, which was deleted (a full-screen grab that also held the
  real desktop). This phase's runs of `confirms` pass `--state`.
- **A hand-edited non-numeric `updated` in the chat index crashed every
  save** (`_save_index`'s sort raised TypeError, which `save_chat` does not
  catch, so it reached the turn), and the CLI's `list` and `find`. One
  robust sort key (`_when`) now serves all four. Found by my own new search
  test.
- **My re-read**: `search` would have created the chats folder (through the
  locked listing) when nothing was ever saved; it now returns nothing
  without looking. The storage line showed the full path (the overlay has no
  `homeDir`); it reads `HOME`. Agent details' list had said "shared" or
  "passed to it" for chats an agent does not own; the shared browser says so
  again. A stale comment on the card's sizes.
- **The first full check** found two tests pinned to the old layout (the
  sidebar order, the stub's `new` case); updated with the reason.
- `SettingRow.qml:160` logs one height binding loop when "Keep saved chats"
  is drawn: pre-existing (HEAD's Display page logs the same with saving on),
  harmless, left.
- A `--arg details` screenshot taken before the target's timer had moved
  looked like a failure; it was timing.

## Not verified

- **The page in the real shell.** It needs `omarchy-restart-shell` (not run).
  Seen only in `preview.sh` with synthetic events: a real pointer, real
  keyboard focus moving through the page (Tab order across the card, chips,
  rows and actions), scrolling a long chat by hand, and the real store
  writing `shell.json` for the three moved keys were not driven.
- **The narrow layout** (list and chat taking turns below 560 px) was never
  drawn: the overlay is never that narrow on this screen, and the 520×720
  crop only cuts it.
- **Delete all on the real chats** (40 saved): deliberately not done. At the
  next stop point, if wanted: open the page, Delete all, check the folder.
- **A save in flight refused on the real daemon**: needs a real turn with a
  delete during it (driven in tests only).
- **Continue, New chat and Send from the page against the real daemon**
  (logged in previews, not sent).
- **The bar popup's Chats button and the readout's click** opening the page
  (they need the restarted shell).
- **The installer box** (`install.sh` did not change).
- **The Codex review** (bypassed, not owed).

## Going back

`bin/agentvoice-deploy d7c3918c2528` from the clone, `./install.sh --yes`
once the daemon is idle, then `omarchy-restart-shell`. An M17 build shows the
chat privacy settings on Display again (the same keys and values) and the
conversation view behind the top-row button; it ignores the index's `purged`
and `deleted` (harmless: an M17 daemon simply saves an in-flight turn as
before). **A confirmed deletion stays deleted**: nothing in a downgrade
brings chats back.

## Open issues, for the next phase

1. **Codex review bypassed** for M18 (user decision, 2026-11-22). M12 stays
   "review owed".
2. **Should an agent running `agentvoice chats delete --all` be asked at
   every level** (the orders guard), as for the other person-only verbs? Not
   added: the plan does not ask it, the hook is security-critical code, and
   a Trusted agent with a shell can remove the folder directly anyway.
   Default taken: not guarded (below Trusted, Bash is asked as before).
3. **Delete all leaves each agent's live conversation running**: the next
   turn starts a new saved chat, but the agent's own program still remembers
   the conversation (its session), and Claude Code keeps its own transcript
   files. Should Delete all also start every agent fresh (`chats new` for
   each)? Default taken: no; the page says each program's own records are
   not touched.
4. **The search box searches every chat**; should the chips' agent filter be
   sent to the search (`--agent`) rather than applied to its results? Same
   result today; matters only if M19's index makes per-agent search cheaper.
5. **Agent colours** are derived from the theme accent by id. Should an
   agent's colour be a setting (a per-agent field) instead? Default: derived,
   no new setting.
6. **The settings card folds itself** once chats exist. Keep, or always open?
7. **Carried, still open**: M17's 2–7; M16's 2–9; M15's 2–8; M14's 2–7; M13's
   2–9; M12's 2–7; M11's 1–7; M10's 1–8; M9's 2–7; M8's 2–11; M7's 2–7; M6's
   1, 3, 4; M5's 1, 4–6; M4's 4–13; the Voice library trash icon (M25); M0's
   small test and bench fixes; agy's `carries_session_across`; the runner's
   sandbox test command.

## Live checklist: what was done, what happened

Nothing was said into the microphone and no turn was typed.
- Before the deploy: state `listening`, every agent idle (`''`, `sora`,
  `jarvis-ajc`), no open mic, no task, no journal line in five minutes;
  `shell.json` copied (0600).
- `bin/agentvoice-deploy --install --wait 120 7d8b9b1`: strict check green;
  "deployed 7d8b9b118b6a. The way back: bin/agentvoice-deploy d7c3918c2528";
  "QML changed: run omarchy-restart-shell? (not run)"; "Build 0.2.0
  (7d8b9b1), replacing 0.2.0 (d7c3918)". Service active.
- After: 30 journal lines since the restart, none with an error (`-o json`).
- The fix, the same way, the daemon idle again: `bin/agentvoice-deploy
  --install --wait 120 c94490e` ("Build 0.2.0 (c94490e), replacing 0.2.0
  (7d8b9b1)"); service active; 8 journal lines, none with an error. The
  untracked notes file was moved to /tmp for the deploy (it refuses a dirty
  clone) and back.
- The installed CLI with `XDG_DATA_HOME` a scratch folder holding two
  synthetic chats: `echo "canary wak" | agentvoice chats search --json` found
  the canary chat (score 1.0); `agentvoice chats search canary` refused
  (usage, words on stdin); `stats --json` 2 chats, 1,864 bytes; `rename ID`
  from stdin renamed it; `delete --all` printed 2 and left `index.json` and
  `.lock`. Scratch folder removed.
- The real chats folder: `chats stats --json` read, counts only (exists, 40
  chats, 0 pinned, 179,741 bytes). Nothing listed, opened or written.
- `shell.json` byte-identical to the copy afterwards. No shell restart.
