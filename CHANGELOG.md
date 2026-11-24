# Changelog

Kept from the phase notes (`phaseMNnotes.md`, `phaseNnotes.md` in this
folder), which hold the detail, what was measured and what was not verified.
Newest first. The version in `manifest.json` has been 0.2.0 throughout the
redesign round; builds are told apart by commit (About shows both the
settings' and the service's).

## M28 · Settings search, and first-run setup (2026-11-23)

- **Settings search**: a box at the top of the settings sidebar (Ctrl+F).
  "pause" finds the pause that ends a turn; Enter opens its page, unfolds the
  Advanced section it is folded in, scrolls to it, outlines it and puts the
  keyboard on it. Every setting is in the index, one agent's settings once
  per agent, with the words people look for them by; a setting not shown for
  the current choice (an engine's threshold) still opens its page and says
  why it is not there. A test fails when a setting has no entry, or its
  entry names a page other than the one that changes it.
- **First-run setup**: on a fresh install (no settings, no agent folder, the
  service never started) the settings open on four steps: microphone (level
  and gate), wake word (engine, phrase, and three tries through the wake
  test), your agent (the programs found, a name), done. Each step starts
  from what is set and writes only what is changed in it; Skip changes
  nothing. Never on a configured install, and only once by itself: the
  Overview offers to finish it, and About has **Run setup again**. A marker
  in `~/.local/state/agentvoice/setup.json` remembers it, outside the
  settings; an older build ignores it.
- Fixed: a deep link to Communal's "Who gets it" or "Preview" tab opened
  Rules instead (the summons did not know the two tabs M15 added).

## M27 · Agents speak up when background work finishes (2026-11-23)

- **When background work finishes, the agent that started it says one short
  line and a notification appears**, without waiting for its name: a Claude
  Code agent's own background command or helper (what Claude Code then says
  by itself, at most 300 characters aloud, all of it in the chat marked
  unprompted), and a task any agent gave another to report back on ("The task
  I gave Sora is done, and I have the result.").
- Never over anybody, at most one line per agent every two minutes, five
  minutes to be said or it is not; while locked, muted, lent out or with
  notifications silenced, only the notification, and nothing is said later.
  The notification's words are fixed, never the model's. A stop drops what
  waits. **Speak up when work finishes** on each agent's Voice card, on by
  default.
- **A lock no longer stops an agent's background work**; a turn under way
  still stops.
- Fixed: a warm Claude Code process that finished background work took a
  turn by itself, nothing read it, and the *next* question was answered with
  that turn's text and the real answer came a turn late. Every Claude turn now
  carries `--replay-user-messages` and one thread reads the process's output
  between turns.

## M26 · Other settings, and About (2026-11-23)

- **Display & privacy is now Other settings**: the readout (with the Agents
  panel switch), privacy, the keys and, moved from About, **Maintenance**
  (Repair, add openWakeWord or sherpa-onnx, Remove Agent Voice). Links to the
  old page still open it.
- **Writing what is said to the journal asks first**, saying the journal keeps
  it for weeks. Turning it off is one click.
- **Keys are read live** from `bindings.lua` and checked against what Hyprland
  has loaded, with **Open bindings file**. Read only.
- **About**: both builds (the settings' and the service's) with commit, branch
  and install time, and whether their daemon code differs; **Copy
  diagnostics** (built from allowlists: no transcript, reply, key, URL path or
  folder text, even with logging on); **Check for updates** (only on a click,
  naming the remote it asked); what runs on this machine and what goes out,
  each backend not found / installed / has answered a turn here; a probe for
  Ollama and llama.cpp on loopback; every voice command with the wake
  phrases; this changelog, the license and the README.
- `install.sh` stamps the commit, branch and install time; new CLI verbs
  `agentvoice about`, `agentvoice diagnostics [copy]`, `agentvoice keys`.
- Fixed: "Saved chats are off" pointed to the Display settings; saving chats
  has been on the Chats page since M18.

## M25 · Voice page (2026-11-23)

Each agent's voice and speed with a test button and a link to its card; the
library opens on Downloaded with one search box and one filter, and its
columns line up (bug F). Transcription moved under Advanced.

## M24 · Conversation page (2026-11-23)

Pace presets; follow-ups, open mic (live, with Turn on / off), progress talk
and talking over it as cards; a drawing of one turn from the live timings,
with "N turns today hit the limit. Raise it"; the full command list.

## M23 · Listening as a pipeline, and gate speed (2026-11-23)

The Listening page laid out as the four stages a sound passes through. How
fast the microphone gate follows the room is now two settings (rise and fall).

## M22 · Wake decisions that match the controls (2026-11-23)

Three wake decisions, the third new: the spotter alone, either stage, or both
must agree. A missing second stage holds wakes closed rather than falling back.

## M21 · Stats, and the Overview page (2026-11-23)

Turns, wakes and false wakes, waits and memory on the Overview, from per-day
counts kept 90 days (never text), with a switch and Clear stats.

## M20 · Chat search as an agent tool (2026-11-23)

Agents can search and read saved chats they are allowed to (their own and the
ones shared with them by default), each chat judged before it is even counted.

## M19 · Chat names, summaries and search filters (2026-11-23)

Saved chats get a proper name and a one-line summary from their own agent (a
quiet side turn; a rename by you always wins), and the search gets filters.

## M18 · Chats page (2026-11-22)

Chats in the sidebar: saving and privacy, a grouped list, search, bubbles.

## M17 · Advanced: controls and agent management (2026-11-22)

Extra flags and environment variables per agent, judged at launch (a flag that
would switch the guard off is refused); resume on or off; the hung-turn limit;
duplicate and reset an agent.

## M16 · Agent details Advanced: what is running (2026-11-22)

The exact command line (secrets masked), session, servers given and started,
recent log lines and permission decisions, read only.

## M15 · Communal: who gets it, preview, import, history (2026-11-22)

Opt an agent out of Communal; preview the whole prompt as sent; import rules
and skills; history of every text.

## M14 · The Agent Voice skill (2026-11-22)

A generated skill that explains Agent Voice to its own agents (commands, wake
phrases, settings and where they live). It explains; it changes nothing.

## M13 · Note categories, and moving notes (2026-11-22)

Notes as topics in categories; move, copy and combine them between agents and
Communal, with their history and undo.

## M12 · Skills: move, copy, undo (2026-11-22)

Drag a skill between agents and Communal; crash-safe, with undo and an audit
line.

## M11 · Skills: scan, lanes, assign (2026-11-22)

Every skill on the machine, who gets it, and a switch for each, enforced where
the CLI looks too.

## M10 · Tool detection, and real tool controls (2026-11-22)

MCP servers and command-line tools found on the machine, off until switched
on; Claude Code turns carry `--strict-mcp-config`, so off is off.

## M9 · Crew map, drawn (2026-11-22)

Agents as boxes and links as lines: drag to link, a red zone to quarantine.

## M8 · Crew links and quarantine, enforced, with the table (2026-11-22)

An agent reaches another only along a link you made, judged four times; nobody
is linked on upgrade, with a one-click "link everyone as before".

## M7 · Authenticated answers for approval cards (2026-11-22)

The daemon holds every approval card and takes an allow only from the live
shell's own overlay; anything else denies the card.

## M6 · Agent details: agent tabs, personality and instructions (2026-11-22)

Agent tabs instead of a drop-down; trait chips, hints, starter templates, Try
it, and meters on each box.

## M5 · The Agents page (2026-11-22)

One card per agent, the main one included, with a header strip; the
duplicate tool sections at the bottom are gone (bug E).

## M4 · Commands inside sentences (2026-11-21)

One command table; a command said at the start or end of a sentence counts
(bug A); it says what it did, and "no" right after undoes an open-mic switch.

## M3 · Popup and readout (2026-11-21)

The popup no longer bounces (bug B) and lost its old global permission section
(bug D); the readout gets size, position, text size and a Preview.

## M2 · Daemon bug sweep (2026-11-21)

Open-mic chats keep their earlier turns across a level change (I); the
surprise chime is gone (J); "still listening" clears when open mic ends (K);
a turn cut at the limit says so (C).

## M1 · Shared UI pieces, and the key inventory (2026-11-21)

Building blocks every page shares, and a confirm on every button that destroys
something.

## M0 · Housekeeping, and bug H (2026-11-21)

Working on Agent Voice no longer reloads the whole desktop shell (bug H): a
development clone, a deploy script, and a check that writes nothing.

## Before the redesign: phases 1 to 16, and orders-guard

The wake word, transcription and spoken replies (phases 1 to 3); progress talk
(4); open mic and handing a chat to a terminal (5); OpenAI-compatible
endpoints, desktop tools and the Omarchy skill (6); the editor and browser
tools (7); agents as folders with their own instructions, notes, tools and
skills (8 to 14); collaboration between agents and shared chats (15, 16); and
the orders guard, which asks before an agent writes its own settings.
