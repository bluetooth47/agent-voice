# Agent Voice: next round plan

Written 2026-11-17, after comparing Agent Voice with Atzingen's Jarvis
(github.com/Atzingen/hey-jarvis, the `atzingen.jarvis` marketplace plugin).
No code has been written for any of this yet.

---

## How every feature gets built

1. **Agree the spec.** Open questions are answered before building.
2. **Measure first.** A baseline (bench clips, replayed event logs, timings)
   so "better" is a number, not a feeling.
3. **Dev branch.** One branch per feature, merged to main when done.
4. **Build to the repo rules.** Each new setting goes in all three places
   (manifest, `runtime.Config`, the UI page). Tests as `CLAUDE.md` asks.
   QML is checked in `bench/preview/preview.sh` first.
5. **`./bin/agentvoice-check` green.** Installer changes also run the box
   (`AGENTVOICE_BOX=1`).
6. **Install last.** `install.sh --yes` ends any voice turn. QML changes need
   a shell reload, which gets a warning first.
7. **Live test** against a short checklist written for that feature: what to
   say, what should happen.
8. **Record.** A FINDINGS entry with the numbers, commit, push to `fork` only
   (never origin).

**Done means:** check green, the live checklist passes, and every number in
the FINDINGS entry was measured.

---

## Order

| Phase | What |
|---|---|
| A | 8 bar click, 9 wake Advanced tab, 7a agent on/off switch |
| B | 10 adaptive mic gate, 6 accurate live transcript |
| C | 7c display names, 2 chat management |
| D | 1 progress talk: sample run, then audio |
| E | 3 terminal handoff, 11 open conversation |
| F | 7b local models and URLs, 12a desktop tools, 12b Omarchy skill |
| G | 12d VS Code and browser, 12c second-mouse spike |

7c comes before saved chats on purpose: once chats are stored on disk under
agent names, renaming an agent would mean migrating every saved chat.

Dropped: timed pause (`yieldToRecorders` and mute already cover it) and
"think hard" routing (several agents, each on its own model and woken by its
own name, already cover it).

---

## 1. Progress talk while it works

**Now:** one plan sentence before tools, chimes, the speech flushed when a
tool starts. Then silence until the answer.

**Goal:** during a long turn it says short, specific, true sentences about
what it is actually doing, and never gets in the way of the answer.

**Where sentences come from.** Real events only, never guesses:
- Claude stream-json: tool name and input (Bash command, file path, search
  pattern, URL, web search query), subagent starts, thinking blocks.
- Codex `exec --json`: command events.
- Gemini and plain endpoints stream no tool events. They keep chimes only,
  and the UI says so.

**How sentences are written.** From the actual event, with no extra model:
- `Read Panel.qml` → "I'm reading Panel.qml."
- `Bash ./bin/agentvoice-check` → "Running the checks."
- `WebSearch "omarchy jarvis"` → "Searching the web for Omarchy Jarvis."
- Bursts are grouped: 6 reads in 3 seconds → "I've looked through six files."
- Long commands get a short spoken name ("running the tests", "installing
  packages"), never the raw command line.
- A rephrase by a small model can come later as an option, only if the
  templates sound robotic.

**Timing rules:**
- Speaks only after N seconds with nothing said (default 7s, adjustable).
- At least 10s between sentences, and the gap grows (10 → 15 → 25s) so a
  5-minute task doesn't chatter.
- Never repeats a sentence. Speaks only when there is a new kind of activity.
- Never starts once answer text has started. If the answer arrives
  mid-sentence, the sentence is cut at the next word break.
- Priority: permission prompt, then the answer, then narration. Barge-in and
  the wake word stop it like anything else.
- With several agents, narration is lowest priority on the floor: agent B
  never narrates while agent A is talking. Each narrates in its own voice.

**Privacy filter:** no secrets, tokens, `.env` contents, or paths under
`~/.ssh` / `~/.gnupg` are spoken. Those become "reading a config file".

**Settings:** narration off / brief / detailed (brief names the stage,
detailed names files and searches); silence before speaking; per-agent
override on the agent card. The HUD shows the same line as text.

**Execution:**
1. Record the stream-json of 20+ real turns into `bench/narration/`.
2. A replay tool prints exactly what would be said and when, next to what the
   agent was really doing. The user approves the wording before any audio is
   wired.
3. Targets: zero repeats, zero overlaps with the answer, zero sentences about
   events that didn't happen, zero secrets spoken.
4. Tests: event-to-sentence rules, grouping, timing, redaction.

---

## 2. Chat management: save, browse, continue

**Now:** `runtime.History` is a 200-line file in tmpfs, gone at logout. The
conversation view shows the current session. Claude sessions resume with
`--resume`.

**Storage:**
- Opt-in setting "Save conversations", off by default. Memory-only was a
  deliberate privacy choice, so changing it is the user's explicit choice.
- `~/.local/share/agentvoice/chats/`, owner-only, one file per chat.
- Each chat: id, agent id (from 7c), backend, backend session id, project
  folder, title, start and last time, full transcript (with tool summaries
  and narration lines).
- Title from the first request, shortened; renameable.
- Retention: forever, 30 days, or the last N chats.

**Revamped conversation view** (sidebar, like Settings):
- Left: chat list grouped Today / This week / Older, search, filter by agent,
  pins.
- Right: transcript with **Continue**, **Rename**, **Pin**,
  **Export to Markdown**, **Delete**.

**Continuing:**
- **Click:** Continue makes that chat the agent's current session. Claude and
  Codex resume natively. Gemini and endpoints get the transcript replayed as
  context, and the UI says that costs tokens.
- **Voice:** "Theo, continue the chat about the HUD" matches by title and
  recent text and reads back "Continuing *HUD sizing*. Go ahead." Two matches
  → it asks which.
- "Theo, new chat" starts fresh.
- "Allow all in this chat" grants still never survive a daemon restart.

**Open decisions:** retention default; one shared list with an agent filter
(recommended) or a list per agent.

---

## 3. Terminal handoff, by request only

**Trigger:** only when asked: "Theo, move this to a terminal". Works during
a turn (wake word first) or right after one.

1. The voice turn stops cleanly.
2. A terminal opens with `claude --resume <session>` in the agent's project
   folder, so the full context is there and typing continues it.
3. The agent says "Moved to a terminal", and the voice loop is free.
4. While that terminal is open, voice never touches that session (no two
   processes on one chat). Talking to that agent asks "Start a new chat, or
   wait for the terminal one?"
5. When the terminal closes, the chat is marked as continued in a terminal
   and can be continued by voice later.

Codex does the same with its resume. Backends that can't resume refuse with
a spoken reason.

---

## 6. Accurate live transcript (a setting)

**Now:** `livePartials` shows rough Vosk text in the HUD while you talk.
Jarvis's version uses OpenAI Realtime (cloud, paid, more accurate).

**Add:** a third choice, **"accurate"**. Vosk's rough text appears first,
then each part is replaced by Whisper's text from `eager.py` as it comes in.
All local, no extra memory beyond Vosk. Needs testing so the swaps don't
flicker.

---

## 7. Agent settings: three additions

### 7a. Turn an agent off without deleting it

- An **On / Off** switch on each agent card, saved as `enabled` in each
  `voiceAgents` entry. Missing means on, so existing setups don't change.
- **When off:** its name leaves the wake grammar (can't be woken by mistake),
  it disappears from the popup chips and the Agents panel, and its card stays
  in Settings, dimmed, with every setting kept.
- **The main agent** has no switch; the card explains why (something has to
  answer the main wake word).
- **Switched off mid-turn:** its turn is stopped first.
- **Tests:** an off agent can't wake, isn't routed to, keeps every field
  across save and reload.

### 7b. Better support for local models and API URLs

**Now:** endpoints are main-agent only (`endpointUrl`, `endpointModel`),
keys only from environment variables (`paths.endpoint_key`), history fixed at
8 turns, and no filtering of reasoning models' thinking text.

1. **Endpoint per agent.** Backend choice per agent: a CLI program (Claude,
   Codex, Gemini, Antigravity, Copilot) or **Endpoint** with its own URL, model, key.
2. **Presets:** Ollama (`localhost:11434/v1`), LM Studio (`:1234/v1`),
   llama.cpp server (`:8080/v1`), vLLM (`:8000/v1`), OpenRouter, Groq,
   OpenAI, xAI. Per the repo rule, a preset ships only after one real turn
   through it; the rest stay out until tested.
3. **Forgiving URLs.** Add a missing `http://` and `/v1`, cut a pasted
   `/chat/completions` back, drop a trailing slash. The field shows what will
   actually be used.
4. **Test connection:** reachable or not, key needed or not, time to first
   word, plain errors ("Ollama isn't running", "wrong port", "model not
   pulled").
5. **Model dropdown** filled from `/v1/models` (and Ollama's own list).
6. **Keys per endpoint** in an owner-only file, never in the synced settings,
   shown masked.
7. **Thinking text is never spoken.** `<think>…</think>` and separate
   reasoning fields are removed before speech and shown greyed in the
   conversation view.
8. **Timeout and history turns per endpoint.**
9. **Later, optional:** local models with tool calling get the 12a tools.

**Tests:** URL clean-up cases; the thinking filter, including a tag split
across two streamed pieces; keys never written to settings; the existing
hostile-server caps still hold.

### 7c. Display name separate from the wake phrase, for every agent

- **Now:** an extra agent's name is its wake word; the main agent has only a
  wake phrase.
- **New:** every agent, main included, has a **Name** (shown in the HUD,
  popup, chats, Agents panel and spoken lines; any text) and a
  **Wake phrase** (1 to 3 hearable words, as today).
- **Upgrade:** a missing name falls back to the wake phrase, capitalised.
- **Stable ids:** the permission hook, chat grants, Agents panel files and
  voice commands all point at agents by name today. Each is checked first
  and moved to a stable internal id, so a rename never breaks grants, chats
  or panel entries.
- **Tests:** a renamed agent keeps its session, grants and chats; two agents
  can't share a wake phrase even with different names.

---

## 8. Clicking the bar icon shouldn't stop it

**Now:** left-click during a turn calls `stopTurn()` (`Panel.qml`, the
WidgetButton `onPressed` handler).

**Change:** left-click always opens the popup, which already has STOP. The
tooltip drops "click to stop". Right-click (mute) and middle-click (service)
stay. "Full stop" and the wake word still stop everything hands-free.

---

## 9. Wake word: Advanced tab

A collapsed **Advanced** section on the Listening page. Everything done to
get Theo working becomes a setting:
- engine choice and each engine's threshold (sherpa, openWakeWord, Vosk
  confidence);
- second check (`wakeCrossCheck`), with its cost explained (~1s on a backup
  wake, 114MB for Vosk);
- short-name boost (hard-coded `SHORT_BOOST` 1.5 now) as a slider;
- "also sounds like": the alternate pronunciations (hard-coded `ALT_PHONES`
  now) as an editable list per agent;
- burst window for the second check (0.3–2.6s now);
- verifier toggle and lead-in time;
- **Test my wake word:** say the name 10 times, see the hit rate and the near
  misses from the log.

Each value gets range checks and a reset-to-default button.

---

## 10. Adaptive microphone gate (toggle)

**Now:** a fixed gate (`micThresholdDb`) plus the sensitivity slider.

**How it works:**
- Tracks the room's noise floor: a slow low percentile of frame loudness,
  from frames with no speech only.
- Never learns while the user talks or while it speaks.
- Gate = noise floor + margin; with adaptive on, the sensitivity slider is
  the margin.
- Hard minimum and maximum. Rises slowly, falls back faster, never jumps
  mid-phrase.

**UI:** the toggle, plus a live line on the Listening page showing the noise
floor and the current gate.

**Execution:** bench recordings with a fan, music, TV, other people talking.
Compare missed and false wakes, fixed vs adaptive. Ships only if it's at
least as good on every recording.

---

## 11. Open conversation (no wake word, silence allowed)

**Now:** a follow-up window after each reply (`followUpMs`, default 7s,
max 20s), then the wake word again.

- **Start:** "Theo, keep listening" / "let's keep talking", or the popup
  toggle.
- **Stop:** "stop listening", "goodbye", "full stop", the toggle, or the
  idle timeout.
- Stays with the agent that started it; saying another agent's name passes
  the open mic to that agent.
- Always visible: a different bar icon color and a HUD line ("Open mic:
  Theo, 8 min left").
- **Settings:** idle timeout (default 10 min); "only answer if it's meant for
  you" (the agent stays silent when speech clearly isn't addressed to it);
  start automatically after every wake (off by default).
- **Risk:** it hears the TV or another person. Mitigations: minimum utterance
  length, the "meant for you" option, automatic pause during calls
  (`yieldToRecorders`).
- Start and stop phrases go through `speech_text.py` like "goodbye" and
  "full stop", and get checked against Whisper the same way (FINDINGS §25).

---

## 12. Desktop actions and built-in tools

### 12a. Built-in desktop tools (an MCP server shipped with Agent Voice)

Passed via `--mcp-config` (Claude, Codex, Gemini):
- open an app; focus, move, close a window; switch workspace;
- open a project layout (terminals, editor, browser for a folder),
  configurable;
- media and volume, notifications, clipboard read and write;
- screenshot so the agent can see the screen (permission each time);
- suspend or lock, only if the user said it in that turn.

Every tool goes through the permission hook at each agent's level. Read-only
tools are allowed at lower levels; anything that changes things asks.

### 12b. Omarchy productivity skill

- Generated at install from the `omarchy-*` commands actually installed, so
  it matches the Omarchy version: scratchpads, launchers, menus, screenshot
  and recording, themes, keybinding lookup.
- Gives the agent exact commands ("open a scratchpad terminal" is one
  command, not a search).
- Agents that don't load skills get the same list as instructions.

### 12c. A second mouse for the agent (research spike first)

As far as known, Hyprland has no second independent cursor; a virtual
pointer (ydotool, wlr virtual-pointer) moves the user's cursor.
- **(a) Recommended:** act through window and app commands (hyprctl,
  accessibility, browser control) with a "ghost cursor" overlay showing where
  the agent works. The real pointer never moves.
- **(b)** A headless virtual monitor for the agent. Clicks there still borrow
  the cursor briefly.
- **(c)** Check whether recent Hyprland has any multi-pointer support.

A 1-day spike tests (a) and (c), then a decision. Nothing built before that.

### 12d. VS Code and browser

- **VS Code:** open a file at a line; open a diff of what the agent changed;
  check whether Claude Code's IDE connection (`--ide`) can be passed to voice
  sessions so the agent sees the open file and selection.
- **Browser:** build on the uncommitted `--chrome` flag in
  `daemon/adapters/claude_code.py`. Anything that submits, buys or posts asks
  first, out loud and on screen.
