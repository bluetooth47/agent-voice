# Phase 12: The Agent details and Communal pages

Written 2026-11-19. Branch `phase-12`, cut from `phase-11` at e467d99,
pushed to `fork/phase-12` only (the hash is in `git log`). Installed: yes.
Tested on: i7-1185G7, Quickshell under Omarchy's shell, `claude` 2.1.328.

`./bin/agentvoice-check`: green, 2245 tests (was 2200), qmllint clean. Box:
not run (`install.sh` did not change). Preview: the new `details` target
39/39, `folders` 11/11, `voices` 22/22, all against a scratch data folder
and a scratch shell.json.

**The first commit (61982a1) went in with the check red**: qmllint flagged
three property writes in the new preview targets, and I read only the last
lines of the check's output, where the tests passed. The review commit
fixes it (the targets go through `goTo()`, which now takes a tab) and the
check is green on it. **Codex reviewed the phase** after the first commit:
6 high, 7 medium and 3 low findings, each checked against the code; 14 are
fixed in a second commit and the rest are under "Found along the way".

## What was built

- **Two sidebar pages after Agents**, so nine in all and Ctrl+1..9 (the
  sidebar hint says so). `{"page": "agentdetails", "agent": ID}` opens one
  agent's details.
- **Agent details** (`pages/AgentDetailsPage.qml`): a selector of every
  agent by display name, the main one first and switched off ones marked,
  remembered for the session (`detailsAgent`, `detailsTab` on the
  overlay). Under it, the agent's settings in one line ("Claude Code · haiku
  · ask first · Amy voice") with **Change on Agents page →**, then why it
  would not answer now (switched off, or the daemon's reason it cannot be
  reached), and for an endpoint agent which host its prompt goes to (Phase
  11's open issue). Tabs:
  - **Personality & instructions**: editors for the role (300),
    personality (1500) and standing instructions (2000), and **What <name>
    is told**: every piece of the prompt in order, each labelled by where it
    comes from ("From Communal · rules", "From Sora's personality"), built
    by `agents preview` (the daemon's own code) after every save and every
    change on disk.
  - **Tools & skills**: what the agent can use, worked out from its program
    and the three switches on the Agents page (desktop tools, browser,
    Omarchy commands, each with the reason when it cannot), and the skills
    found in its folder, with the plain statement that they are not given
    to agents yet.
  - **Chats**: its saved chats from the chats index; a row opens it in the
    conversation view. With saving off, an empty state that says so and
    links to Display.
  - **Advanced**: the id, the folder path, **Open folder** (`xdg-open`,
    argv), **Export**, **Remove** (two clicks) with Undo, the **trash**
    with Restore, and **folders no agent uses**, each with Open and Move to
    trash.
- **Communal** (`pages/CommunalPage.qml`): the rules and defaults editors,
  how many agents are told them, the folder with Open and Export. Worded
  from section 3.5: rules are "instructions, not locks: the app does not
  enforce them", and the help says an agent at Trust everything can change
  the file itself, and that such a change shows with Keep and Revert.
- **One editor per file**: the Agents card's instructions box is now a
  summary line ("Role: none · personality: none · instructions: 24
  characters", plus "changed outside Settings" or a problem) with **Edit in
  Agent details →**, which is also the card's Details link.
- **`ui/FileEditor.qml`** replaces `FolderInstructionsBox`: any of the five
  files, saved on blur and on **Ctrl+S**, one status line ("Reading…",
  "Saving…", "Unsaved · Ctrl+S or click away to save", "Saved · applies on
  the next turn", "No role.md yet. Saving creates it."), the CLI's reason
  when a save is refused with the typed text kept, **Keep mine / Reload**
  on a conflict, and the **outside-change notice with Keep and Revert**
  (`agents ack` / `agents revert`, each with `--base`). Tab leaves the box
  rather than typing a tab, so a page can be walked by keyboard.
- **`AgentFolders.qml`** (overlay level): add, remove, Undo, restore from
  the trash, trash an orphan folder, export, and the `agents list` /
  `trash-list` reads, moved out of the Agents page so both pages share one
  queue and one rollback, and so an operation and its Undo survive leaving
  the page (the page Loader drops a page when another is shown).
- New blocks: `ui/TabStrip.qml` (wraps at a narrow width; Left/Right and
  h/l), `ui/PromptPreview.qml` (plain text throughout).
- **agentfs**: `export TARGET [DIR]` (the folder's files and skills, no
  history, into a new 0700 folder of 0600 files under ~/Downloads or home);
  `trash-list` says which entries were orphan folders, and restoring one
  brings the folder back without adding an agent; `preview` gives the
  spoken style in full and names "Omarchy commands and keybindings" where
  the agent is told them (not an endpoint, not with the skill off).
- While the service is off nobody publishes folder sizes, so the overlay
  reads `agents list` every 3s while Agents, Agent details or Communal is
  on screen; a hand edit then shows within seconds.
- `bench/preview`: the `details` target drives every control above through
  the real CLI and logs PASS/FAIL; `detailshots` seeds every drawn state
  for screenshots, and can draw the card narrow (`"width": 520`);
  `preview.sh` gives targets `PREVIEW_DATA`, `PREVIEW_AGENTS_DELAY` (to
  draw "Reading…"), and sends an export with no folder named to the scratch
  directory instead of ~/Downloads.

## Shared files touched, and where

- `Settings.qml`: the two page entries and their badges, the Loader and
  Components, `detailsAgent` / `detailsTab`, `goTo` for the deep link,
  Ctrl+1..9 and the hint, the `AgentFolders` instance, `changedOutside()`,
  the 3s folder read, `objectName` on the card (for the narrow preview).
- `pages/AgentsPage.qml`: the folder machinery removed (now
  `AgentFolders`), the two instructions boxes replaced by summary rows, the
  Undo row now a Flow.
- `daemon/agentfs.py`: `preview`, `export`, `trash_list`, the CLI.
- `ui/InstructionsBox.qml`: `minHeight`, `editingHint`, `dirty`, Ctrl+S,
  Tab, no gap for an empty counter.
- `bench/preview/preview.sh`, targets `folders`, `voices` (updated),
  `details`, `detailshots` (new). Tests: `test_agent_pages.py` (new),
  `test_preamble.py`, `test_agentfs_migrate.py` (pointed at the moved code).

## Measured (numbers, against the baseline)

- No prompt or turn path changed: the daemon logged the same sizes after
  install (Theo 1109, Sora 1210, Hazel 7088 characters). No latency run.
- `agents preview` takes 0.24s and `agents show` 0.13s on this machine;
  each editor runs one `show` on open and on each change.

## Different from the plan, and why

- **No Notes tab yet, and Communal has no tabs.** Notes are Phase 14 and
  shared skills and shared chats Phases 13 and 15; a tab that only says
  "later" reads as broken (V-10's audit list). They are added with the
  features.
- **Tools & skills is a read-out**, not empty: the per-agent switches are
  Phase 13, but what the agent can use today is worth seeing now.
- **One link per card**, "Edit in Agent details →", serves as both the
  plan's "Details →" link and the instructions summary's link.
- **"Folders no agent uses" can be trashed**, marked as orphans, and
  restored as folders only. The plan listed them without saying what could
  be done with them.
- **Export goes to ~/Downloads** (or home) with no folder picker:
  Quickshell has no file dialog, and the result line names the path.
- **"Changed outside: reload / keep mine"** is worded "Keep mine / Reload",
  and appears when the save on blur is refused. An editor never reloads
  while it is being typed in, so nothing is overwritten either way.

## Found along the way (bugs, surprises)

- **An editor could miss a folder appearing** (found by the `details`
  preview): a new agent's editor read its folder a moment before `agents
  create` made it, and the re-read asked for when the folder appeared was
  dropped because the first read was still running. The editor then showed
  the file as missing and its first save was refused. A change noticed
  mid-read is now read again when the read ends.
- **The Undo button could sit off the page** (found by the same target, and
  latent on the Agents page since Phase 10): the "Moved … to the trash"
  row was a Row, so a long sentence pushed Undo past the clipped edge, where
  a click does not reach it. Both pages now wrap it.
- **A personality edit does not show in a conversation already under way.**
  Live, Theo's personality was set (through the same `agents write --line
  --base` the page runs) to begin every reply with "Aye, aye". The journal
  logged the new prompt (1202 characters) two seconds before the next typed
  turn, and his running process's prompt file held the text, but in the
  continuing conversation he answered exactly as before, twice. After
  `agentvoice chats new main`, the same question gave "Aye, aye, two plus
  two is four." An instruction or personality change keeps the
  conversation by design (Phase 10), and the model follows its own earlier
  answers. The Personality help now says so; whether a personality save
  should offer to start a new conversation is left for the UX walkthrough.
- The preview window never takes keyboard focus (by design), so synthetic
  key presses there go nowhere: Ctrl+S and the keyboard walk cannot be
  driven in a preview.
- **Mutations** (first commit): each of 14 new guards was removed in turn; 13 turned a
  test red (export permissions ×2, the orphan flag, no commands for an
  endpoint, the spoken style in full, a second editor for a file, a page
  running `agents write` itself, a page writing a setting, the folder code
  writing another key, the dropped re-read, saving with nothing read, the
  card editing a file, the deep link's agent). The 14th, export's own id
  check, survived because `_base()` already refuses a bad id; the duplicate
  was removed.

### Codex's review, and what was done

Fixed (each with a test, each new guard mutated and caught but one, whose
test was then tightened; the two worst also driven in the `details`
preview):

- **An edit made while a save was running was dropped** (high), so the box
  said "Saved" over newer text. It is now queued and saved on the stamp the
  first save returns. **Typed text was lost when the page was left or the
  overlay closed** before the box lost focus: an editor now hands unsaved
  text to `AgentFolders.keep()` as it is destroyed, which saves it on the
  stamp it was read at (or says why it could not).
- **The agent picker, the text and a save could name different agents**
  (high). Omarchy's Dropdown assigns its own value on a pick, cutting the
  page's binding, so after a removal it kept naming the removed agent; the
  binding is now restored after each pick. Text typed for one agent and
  still in the box when another was picked is now saved under the first,
  never shown under the second; a write's answer counts only in the session
  it began in.
- **Saving could cut a file** (high): the editor showed the budget-cut text
  the agent is told, so editing an over-long hand-written file dropped its
  end; and the box counted UTF-16 units, so focusing and leaving 1000 emoji
  "saved" 750. The editor now shows the whole file (`full` from `agents
  show`), counts as the daemon does, compares before anything is cut, and
  refuses an over-long save with the text kept and the count shown.
- **A late settings failure could roll back the wrong move** (high): the
  folder queue was released before the agent list was confirmed saved. It
  now waits for the store's answer; a double Remove trashes once.
- **Undo could change who answers a wake phrase** (high), when an agent had
  been added under the removed one's phrase meanwhile. Restore now refuses
  and says who has it; `trash-list` gives each entry's phrase.
- A save made before the first read finished stuck the editor; it now reads
  first, then saves. **Keep mine** saves what is in the box now, not the
  text first refused. Keep, Revert, Keep mine and Reload are keyboard
  reachable and say so when the command never ran.
- A second same-length hand edit went unnoticed: the published sizes now
  carry each file's stamp. The prompt preview now also refreshes when
  another agent's role, name or reachability changes, and the overlay keeps
  reading folders and the trash while those pages are open even with the
  service running.
- One rule (`agentfs.is_folder_only`) says which trash entries are folders
  only; a restored entry takes the id its folder came back under.
- An agent whose id is `communal` (a hand edit) no longer edits or exports
  the communal folder from its own page.
- **Export** copies whole files (it stopped at 256 KB), without following
  links, refuses what it cannot copy instead of skipping it, and builds in a
  hidden staging folder renamed into place, so a failure leaves nothing.
- A switched off endpoint's preview listed the Omarchy commands and missed
  its old instructions; the preview now looks at every agent.
- "At the start of every conversation" was wrong (the prompt goes with
  every request); both pages say so now. A second deep link reset the
  overlay's tab but not the page's; the tab is bound. Setting hints and
  labels are plain text (a display name in markup rendered as markup).

Deferred, with the reason:

- **A stamp covers the first 256 KB and the size** (high, inherited from
  Phase 9), and an editor that takes no lock can still write between the
  check and the replace. Files that size are already far over every budget,
  and a strict compare-and-swap against writers that take no lock is not
  possible from here; noted for Phase 17's V-05.
- **The agent list in argv** through `omarchy bar set` (medium, the
  Phase 10 and 11 deferral): now also reached from restore. It ends when
  `instructions` is stripped from saved entries.
- The Tools tab says the Omarchy skill is on from the setting, not from
  whether its generated file exists (low).
- A save still running when its page is destroyed is not handed on (the
  write is atomic, so it either landed or did not, but a cut-off one is not
  reported); a symlinked skills folder is skipped by export, as the reader
  skips it.

## Not verified (what was skipped, and why)

- **The keyboard-only walk and Ctrl+S in the real shell.** The real
  overlay opened on Agent details and drew correctly (screenshot), but
  this session cannot send input to the desktop: `ydotoold` is not
  running, so the desktop tools' keys and clicks fail. The preview cannot
  do it either (above). Left for you: Ctrl+3 and Ctrl+4, Tab through a
  page, Left/Right on the tabs, Ctrl+S in an editor.
- **A12-4 as written**: "the user has edited Theo's personality from the
  page and heard the difference" is yours to do. What was checked instead:
  the edit through the page's own command, typed turns, and the difference
  in a new conversation (above). The test personality was put back to
  empty and the three test chats deleted; Theo's personality history keeps
  the test version (74 characters) and the empty one.
- **Screenshots of a chats list with real chats** were not taken (they
  would show your conversations); the saving-off state and the list's code
  path were.
- The box (`install.sh` unchanged).

## Going back (what an older build sees after this phase)

Nothing on disk changes shape. An older build ignores `role.md` and
`personality.md` (Phase 11 is the first to read them) and an exported or
orphan-trashed folder; a trash entry marked as an orphan has a settings
sidecar of `{"id", "orphan": true}`, which an older build's restore would
put into the agent list as an entry with no name, which the settings then
drop.

## Open issues, for the next phase

- Phase 13 fills Tools & skills with the per-agent switches; Phase 14 adds
  the Notes tabs; Phase 15 the Communal chats tab.
- Whether saving a personality should offer a new conversation (UX
  walkthrough, task 1).
- Keyboard walk and the spoken A12-4 check (above).

## Live checklist: what was said, what happened

No voice from me. On the installed build:

- Install → the journal printed the same three `prompt for` lines as
  Phase 11. Shell restarted; `omarchy-shell shell summon
  duaneoca.agentvoice '{"page":"agentdetails","agent":"main"}'` opened the
  new page in the real shell with the sidebar of nine; closed again with
  `shell hide`.
- Theo's personality set, three typed turns, a new conversation and one
  more turn: see "Found along the way". Put back afterwards.
