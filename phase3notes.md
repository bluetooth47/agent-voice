# Phase 3 (plan.md Phase C): what changed

Written 2026-11-17. Branch `phase-c`, cut from `phase-b` at 39de35f, so it
carries Phases A and B too. Pushed to `fork/phase-c` only. Not installed,
not merged.

Decisions taken from plan.md where it left them open:

- **One shared chat list with an agent filter**, as the plan recommended.
- **Retention defaults to "forever".** Saving is opt-in and off by default,
  so someone who turns it on has asked to keep chats. The options are
  forever, 90 days, 30 days and the last 100. Pinned chats are always kept.

## 7c. A name apart from the wake phrase, and a stable id (100e0c0)

- Every `voiceAgents` entry now has a `label` (any text, one line, up to 40
  characters) and an `id`. `name` still holds the wake phrase, so a saved
  list keeps its meaning and no field was renamed.
- **Upgrade:** an entry without an id gets its wake phrase slugged
  (`hey jarvis` → `hey-jarvis`). That is exactly what the Agents panel,
  grants and the permission hook already called it, so nothing moves. The
  Agents page writes the id into each entry before its first edit, so
  changing the wake phrase can never change the id. New agents get the
  phrase plus a random suffix (`nova-k3f`), so an agent deleted and
  recreated under the same name doesn't inherit the old one's chats.
- **Moved to the id:** the crew dict, the permission hook's argv (and so
  grants and the pending card's `who`), the Agents panel key, the readout's
  `who` and `live` (keyed by id, `""` for the main agent, with a new
  `who_label` field for display), history's new `agent_id`, the settings'
  crew info, card open/focus state, and the Voice library's "Use for".
- **Unchanged:** routing and waking still use the wake phrase. A new wake
  phrase or display name keeps the conversation, the adapter process and
  "allow all in this chat".
- **New setting `mainName`:** the main agent's name, set on the main card
  (manifest, `runtime` + TOML `[agent] main_name`, Agents page). Empty means
  the wake phrase, capitalised. The Agents panel shows it only once chosen;
  until then it still shows the program name, as before.
- **Shown by name:** the HUD, popup chips (the tooltip gives the wake
  phrase and program), the permission card, Overview, the Voice library,
  the Agents panel, spoken lines ("Research cannot answer: …") and the
  journal.
- Two agents may share a name, but never a wake phrase or an id.
- Tests: `tests/test_agent_names.py` (38). The rename-keeps-session and
  hook-gets-the-id tests were mutation-checked.

## 2. Saved conversations (cde8eb3)

- **Settings:** `saveChats` (off by default) and `chatRetention`, both on
  Display → Privacy, in all three places.
- **Store:** `daemon/chats.py`, writing to `~/.local/share/agentvoice/chats/`
  (dir 0700, files 0600). Each chat is one file holding id, agent id,
  agent label, backend, session id, project folder, title, start and last
  time, pinned flag and the exchanges. `index.json` lists every chat without
  its exchanges, plus which chat each agent is in right now. Every
  read-modify-write holds a `flock`, so the daemon appending while the CLI
  renames loses nothing (tested with two threads). Writes go through a
  temporary file and a rename. A damaged index is rebuilt from the chat
  files.
- **Recording:** `Daemon.save_chat`, called from `remember()` on every turn
  whether or not `keepHistory` is on. A new session starts a new chat unless
  Continue put the turn in one. A write failure costs the record, not the
  turn. Retention is applied whenever a new chat starts.
- **Continue** (`continue_chat`): native `--resume` only when the program is
  the same, it remembers (only Claude Code's adapter claims to), and the
  project folder matches. Anything else gets the chat's words once, ahead
  of the next request (up to 8000 characters, newest first), and the view
  says that costs tokens.
- **Voice** (`speech_text.chat_command`, handled in `Daemon.chat_turn`
  before anything reaches the agent):
  - "new chat" / "start a new conversation";
  - "continue / resume / go back to / pick up the chat about X".
  Both must be the whole sentence. A search covers only that agent's chats;
  title words count double, and filler counts for nothing. When two match
  about equally, it names both and asks for more words.
- **CLI:** `agentvoice chats [list|show|rename|pin|unpin|delete|export|continue|new]`.
  `continue` and `new` go to the daemon through the command file; the rest
  edit the files directly under the lock. `list` and `show` print through
  `safe_for_terminal`.
- **Conversation view:** with saving on, the card widens to 980 and
  `Chats.qml` replaces it:
  - left: search, agent filter, "This session", then Pinned / Today / This
    week / Older, with "in use" on each agent's current chat;
  - right: the open chat, with Continue, Rename (inline), Pin/Unpin, Export
    to Markdown (into `~/Documents`, never overwriting; the note gives the
    path) and Delete (two clicks).
  `{"mode":"history","chat":ID}` opens a chat directly. One exchange is now
  drawn by `ui/ExchangeItem.qml` for both views. With saving off, the view
  is exactly as before.
- **Uninstall** keeps a chats folder that holds chats and names it, and
  removes one that holds only the index and the lock.
- Tests: `tests/test_chats.py` (48), plus two in `test_uninstall.py` and a
  plain-text check over `Chats.qml` in `test_history.py`. Mutations caught:
  replay sent every turn, a continued chat split into a new one, resuming
  across folders, the lock removed, and the listing printing raw escapes.

Not done from the plan's spec for item 2:

- Tool summaries and narration lines in the saved transcript. Narration is
  Phase D. Tool markers aren't kept per turn today; adding them is a small
  follow-up.
- ~~Codex resuming natively.~~ Corrected 2026-11-18 by the full test run:
  the Codex adapter does claim `remembers` (`resume <thread_id>`), and two
  real turns showed it remembering, so its saved chats resume natively like
  Claude's.

## Still to do

1. Done: check green (1393 tests), installer box 9/9.
2. Install (`install.sh --yes` ends any voice turn) and restart the shell
   (QML changed).
3. Live checklist:
   - Agents → Sora: set Name to "Research", leave the wake phrase. "Sora,
     what time is it?" works, and the HUD, popup chip and permission card
     say "Research".
   - Change Sora's wake phrase to another word while a conversation is
     going. The new word wakes it, and it remembers the conversation.
   - Main card: set Name to "Theo". The popup chip and Overview say Theo.
   - Display → Save conversations on. Have two short conversations, with
     "Theo, new chat" between them. Both show in the conversation view.
   - "Theo, continue the chat about <first topic>". It says "Continuing …",
     and the next request carries on that chat.
   - In the view: rename, pin, export (check the file in ~/Documents),
     delete, and search.
4. Merge dev → phase-b → phase-c → main when
   the checklists pass.

`daemon/adapters/claude_code.py` (`--chrome`) is still uncommitted.
