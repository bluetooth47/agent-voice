# Agent Voice redesign and feedback notes (2026-11-21)

Dictated by voice during a walk through every settings page, then cleaned
up. Planning only: nothing here is built yet, and no code was changed.

## Files that go with this

All in ~/agentvoice-notes/ (kept outside the plugin folder, because writing
there restarts the shell, see bug H):

- feedback-notes-2026-11-21.md: this file. What to change and why.
- mockups/index.html: clickable HTML sketches of every page in the
  redesign (open in a browser). Sketch quality; small CSS glitches are
  known and don't matter. The real build is QML.
- project-status-2026-11-21.md: branch, install and test status.
- phase-17-plan.md: the reworked verification sweep, run after all this.
- CODEBASE.md: agent-facing summary of the code, updated to orders-guard.
- planning-prompt.md: the prompt to hand to models to turn all of this
  into a build plan.

## Summary

- Design: one shared visual language on every page (item 17): cards,
  compact selectors, toggle chips, one-line hints with tooltips, warning +
  confirm on anything risky, draggable cards. Pages are laid out in the
  order things happen, one block per stage. Fine-tuning goes in collapsed
  "Advanced" sections. No setting is removed, only regrouped.
- New pages or big changes: Chats (5, 6), Crew map (16), Listening as a
  pipeline (18), Overview stats (7), Agent details tabs, tools, skills and
  notes (9 to 12, 14), Other settings (20), About (21).
- Bugs: section 23 (A to K). Fix H (shell restart on save) first.
- Approval: every suggestion in this file was approved by the user unless
  marked otherwise.

## Mockup coverage

The sketch has every page: Overview, Agents, Agent details, Communal, Crew
map, Chats, Listening, Conversation, Voice, Other settings, About, and the
bar popup. Every setting key on today's pages was checked against it and
placed somewhere (most fine-tuning under "Advanced"). The crew map sketch is
interactive: drag agents, drag from an agent's dot to link, click a line to
pick abilities (ask, delegate, message, pass chat) and "ask me first", drag
into the red zone or flip a switch to quarantine, and a table view of the
same links.

## 1. Commands inside a longer sentence should still run

- Today a voice command (stop, open mic / "keep listening", and the other
  built-in commands) only fires when it is said on its own.
- Wanted: if a command phrase shows up inside a longer sentence in a chat,
  it should still be carried out, not just passed to the agent as text.
- Example: "...take notes, and keep listening, because I might pause" should
  turn open mic on.
- Caution (agreed): this can misfire, e.g. "stop listening to that song".
  Consider only accepting commands at the start or end of what was said,
  and always saying out loud when one fires (see item 22).

## 2. Popup: "what Claude Code may do" section

- On the popup (not the Settings page) there is a section showing what
  Claude Code may do, with the trust / edits levels.
- Permission levels are now set per agent, so this global section is
  redundant. Remove it from the popup.

## 3. Popup jumps around during a chat

- While a chat is running, the "last heard" line keeps appearing and
  disappearing, so the whole popup window bounces up and down.
- Wanted: a steady layout. Reserve the space (or keep the line always
  present) so the window size doesn't change turn to turn.

## 4. Shell restarts whenever a file is saved

- Still happening: every time the agent writes a file, the shell resets.
- Already recorded as item 3 in bugs-notes.md (first seen 2026-11-19).
  Seen again today.
- Workaround for now: these notes moved out of the plugin folder to
  ~/agentvoice-notes/ so saving them doesn't reset the shell.

## 5. Settings window: Conversations button and section are confusing

- The "Conversations" button sits alone on the top row, next to only the
  window title and "Esc to close". Odd spot for it.
- There is also a "Conversations" section in the sidebar with conversation
  settings, so the name appears twice and it's unclear which is which.
- Idea: make chats their own sidebar section (e.g. "Chats") and keep the
  conversation settings separate, then drop the top-row button.
- Past chats can also be reached from Agent details. Keep that as it is.

## 6. Make past chats easier to browse

- Clean up the chat list so it's easier to read through.
- Give each chat a proper name (not just an id or the first words).
- Show more information per chat (e.g. agent, date, length, a short
  summary).
- Add a search feature over past chats.
- Agents should be able to use the same search too (e.g. as a tool), so
  they can find old chats quickly.
- Opened chat view: messaging-app layout. The user's lines on the right,
  the agent's on the left, with different background shading/colour per
  side (from the Omarchy theme).

## 7. Overview page: add some statistics

- Likes: the agents list and the mic gain control.
- Feels thin on information. Add some stats.
- Add all of these (user approved all of them):
  - Turns today / this week, per agent.
  - Average wake-to-reply time and transcription time.
  - Wake word hits vs. false wakes (rejected by the second check).
  - Time since the service started, and memory used.
  - Last chat per agent, with a link to open it.

## 8. Agents tab: tidy up each agent's settings

- One of the best tabs. Likes the per-agent drop-down and how much can be
  configured there.
- Problem: there are a lot of settings and they're not well organized.
- Name, wake phrase, and "runs on" / model take up most of the first
  section. Compress them (e.g. put them side by side on one or two rows).
- Not about removing settings. Keep every setting (more will be added
  later); just make them neater and easier to get to.
- Effort: shrink it into a small control right next to the model picker,
  like a compact selector bar or mini slider, similar to how VS Code does
  it.
- Permissions, project folders and the rest of each agent's section look
  great. Keep as is.
- At the bottom of the Agents tab there are extra sections for desktop
  tools, browser, Omarchy commands and notes. These already live inside
  each agent, so they're duplicates. Remove them from the bottom of the tab.
- Layout feels like "row, row, row, row": one long stack of identical
  rows. Wants something more dynamic.
- Approved by the user:
  - Group settings into small cards (Identity, Voice, Model, Permissions,
    Tools), laid out two per row where the window is wide enough.
  - On/off options as a row of toggle chips instead of one row each.
  - A header strip per agent showing name, model, effort and voice at a
    glance, with the details folded underneath.

## 9. Agent details page: tabs instead of a drop-down

- At the top there is a drop-down to pick which agent to look at.
- Replace it with tabs, one per agent, so switching between agents is
  quicker and it looks nicer.

## 10. Agent details: Personality & instructions section

- Looks a little off and doesn't give the user what they want from it.
- Today it's three plain text boxes (Role, Personality, Standing
  instructions), each with a long paragraph of explanation above it.
- Approved by the user (all of these):
  - Quick-pick trait chips on top (tone: warm / dry / playful; length:
    brief / detailed; formality), which write into personality.md. Free
    text stays below for anything else.
  - Short one-line hints instead of long paragraphs; details in a tooltip.
  - Starter templates to pick from when a box is empty.
  - A "Try it" button that has the agent speak a sample line in its voice
    with the current personality.
  - Character limits shown as a small meter instead of plain text.

## 11. Agent details: Tools & skills (big one)

- The built-in tools (desktop, browser, Omarchy commands, collaboration)
  are great base tools. Keep them.
- Wanted: support for other tools already on the machine. Agent Voice
  should detect what's installed (e.g. other MCP servers, CLIs, plugins)
  and offer a toggle switch for each one it finds, per agent.
- Problem: nothing in this section can be changed. It only shows
  information, which doesn't fit a settings page. Every tool and skill
  listed here should have a real control (at least an on/off toggle per
  agent).
- Idea: skills as draggable cards. Drag a skill onto another agent or into
  Communal to move it.
  - My take: good fit for skills, since each one is a folder. Plain drag
    moves it, holding Ctrl copies it, and there's an undo. For tools,
    toggles fit better than dragging, since a tool is a permission rather
    than a file, but the same card look can be shared so both feel alike.
- Make an Agent Voice skill (a reference of how Agent Voice works: its
  commands, settings, files) so the agents can look things up themselves.
  Ties in with voice-commands-notes.md in the plugin folder, which already
  plans a skill for the command list.
- Agreed: tools are toggles, skills are draggable cards.
- Skills should populate themselves: scan for every skill on the system
  (agent folders, Communal, and skills installed elsewhere, e.g. Claude
  Code's) and show each one as a card with a drop-down for details.
- Add an "Unused" area for skills that no agent uses and that aren't in
  Communal, so they can be dragged onto an agent from there.

## 12. Agent details: Notes, sorted into categories

- Wanted: notes grouped into categories, one file per topic (e.g. "this
  system", "a project", and so on) instead of one flat list.
- Each category file can be moved between agents and Communal the same way
  as skills: draggable cards.

## 13. Conversation settings page: general polish

- Pretty good already, just needs general improvement.
- Rename the non-settings "Conversations" area to "Chats" (see item 5) so
  the two can't be confused.
- Pace presets (Patient / Balanced / Snappy) are good but take too much
  space; make them a compact selector in the shared style (item 17).
- The long run of timing sliders is useful but doesn't belong on the main
  view: put them in a collapsed "Advanced" drop-down.
- "Talking over it" section is good; keep it, just restyled.
- Approved by the user (all of these):
  - Live open mic status at the top of the Open Mic group: on/off, time
    left, and a button to turn it on or off.
  - A list of the voice commands (keep listening, stop listening, full
    stop, new chat, hand off...) right on this page, so they're
    discoverable.
  - Turn "When a turn starts and ends" into a small timeline picture
    showing lead-in, pause that ends a turn, and longest turn, instead of
    five sliders in a row.
  - Fold the fine-tuning timings (deaf period, louder by, shortest turn)
    into a collapsed "Advanced" group; Pace presets stay on top.
  - A note when turns are being cut off by the length limit (like earlier
    today at 30s), with a shortcut to raise it.

## 14. Agent details: Advanced tab is nearly empty

- Today it has almost nothing beyond opening a folder. It should show in
  depth how the agent is run, what it's connected to, and what's going on.
- Ideas:
  - Full assembled prompt preview (what the agent is actually sent), with
    each part labelled by where it came from.
  - The exact command line the CLI is started with, plus a box for extra
    flags and environment variables.
  - Connected MCP servers and tools, each with a live status (running,
    failed, off).
  - Session info: current session id, resume on/off, how many past turns
    are kept, and a "start fresh" button.
  - Timeouts: how long a turn may run before it's stopped.
  - Working directory the agent starts in.
  - Recent log lines for this agent only, with a button to open the full
    log.
  - Recent permission decisions (what was allowed, asked, denied).
  - Export, duplicate, and reset-to-defaults for the agent.
- Approved by the user, with one addition: anything risky or permanent
  (reset, start fresh, delete, extra flags) gets a warning icon and a
  confirmation step before it runs. This should apply across the whole
  settings window, not just this tab.

## 15. Communal tab

- Has Rules & defaults, Skills, Notes, Chats. Most of the Agent details
  changes above (draggable skills, note categories, chat layout and
  search, warning on risky buttons) apply here too.
- Gaps found on review (approved by the user, all of these):
  - No shared tools. Skills can be shared but tools can't; add a Tools
    tab with toggles that turn a tool on for every agent at once.
  - No way to choose which agents get the communal content. Add a per-agent
    on/off ("this agent ignores communal rules").
  - No preview of what an agent ends up with once communal and its own
    files are combined.
  - No import, only export. Add importing rules/skills from a folder.
  - No history or undo for rules and defaults edits.
  - Skills tab doesn't show which agents can't use skills (some programs
    can't take them).

## 16. Crew map: a picture of how agents connect

- Agents can ask, delegate to, message and pass conversations to each
  other. Wanted: a visual page showing this as a diagram.
- Each agent is a box; a line between two agents is labelled with what one
  may do to the other (ask, delegate, message, pass the conversation).
- A quarantined agent sits in its own fenced-off box and can only be
  reached through the specific links drawn to it.
- Approach (approved by the user):
  - Lines have a direction, since "Theo may delegate to Sora" is not the
    same as the reverse. Arrows show which way.
  - Drag from one agent to another to make a link; click a line to toggle
    its abilities as chips; a warning-styled delete.
  - The links are saved as a plain list in settings, and the crew tools
    enforce that list, so the picture is only an editor and never the only
    place the rules live. Anything not linked is denied.
  - A table view of the same links as a fallback, for screen readers and
    for when the picture gets crowded.
  - Build order: links list + enforcement first, then the table, then the
    drawn map.
- Quarantine rules (as sketched): a quarantined agent can't start any
  link; lines into it may carry only ask or delegate, with a short brief
  and no chat history. Quarantine by dragging into the red zone or with a
  switch on the agent.
- Inspector: clicking an agent lists who it can reach and who can reach
  it; clicking a line shows ability chips, "ask me first", a button for
  the reverse direction, and delete (with confirm).

## 17. One design language across every settings page

- The new style worked out for the Agents tab (cards, compact selectors
  like the VS Code effort bar, toggle chips, short hints with tooltips,
  warning icon + confirm on risky actions, draggable cards) should be used
  on every settings page, not just Agents.
- Goal: everything looks consistent, and a user can tell at a glance what
  each control is and what clicking it will do.
- Build these as shared pieces in ui/ so every page uses the same ones.
- Design principle: pages are laid out in the order things actually
  happen. Each stage is its own clearly separated block ("first check",
  "second check", ...) holding only that stage's settings, so the eye
  flows top to bottom from one stage to the next without a wall of text
  and colours.

## 18. Listening page: wake engines as one layered pipeline

- Same general cleanup as everywhere (compact, pretty, enough info, new
  selectors).
- Today: the wake engine and phrase are picked in the first section, and
  using more than one engine is tucked away under Advanced, even though
  multiple engines is what's normally in use.
- Wanted: one unified pipeline view.
  - Stage 1: which engine listens first, and its sensitivity level.
  - Stage 2: which engine checks second, and its level.
  - Which stages have to agree before a wake counts.
  - Each stage is its own block with its own settings, in order, so it's
    obvious at a glance how a wake word passes through.
- Microphone settings: good as they are; just restyle them to match.
  - The dynamic gate works well. Add a slider or two for how quickly it
    adapts to the room's noise level.
- "Your voice" section feels vestigial and out of place. Fold it into the
  engine stages: settings that only apply to one engine (e.g. openWakeWord's
  voice training / verifier) appear inside that engine's block only when
  that engine is chosen.

## 19. Voice page

- One of the best pages. Likes the quick settings across the top ("speak
  replies aloud" etc.).
- The "voice and speed" item links straight to the Agents tab. The idea of
  a link is good, but how it's done isn't great yet; rework it (e.g. show
  each agent's current voice and speed inline, with the link to change it).
  Approved by the user.
- Voice library:
  - Default the list to "Downloaded" instead of showing every voice.
  - Replace the row of filter buttons (All, Downloaded, Male, Female,
    British...) with a search box plus one compact filter control.
  - Move the trash-can icon to the front of each row, before the name.
    Right now it shifts the spacing, so the Test buttons don't line up.
  - Keep the "Used for" label, but name the agent(s): "Used for Theo", or
    "Used for Theo, Sora" when several agents share a voice.
  - Names must line up in a column whether or not a row has a trash can
    (reserve the icon's space on every row).
- "Hearing you" section (transcription model: base English, small English,
  etc., plus live transcription): move into a collapsed "Advanced"
  drop-down. Add more there: a short explanation of what transcription
  does, and any other transcription models available to pick from.

## 20. Display & privacy page

- Today it mixes three unrelated things: the on-screen readout (plus
  Omarchy's Agents panel toggle), privacy (keep/save chats, how long, step
  aside for other recorders, log speech), and a read-only list of keys.
- User's direction:
  - The page is a grab-bag of disconnected things. Rename/reframe it as
    "Other settings" (or "More").
  - Chat-related privacy settings (keep/save chats, how long) already
    belong with the Chats section; move them there.
  - New setting: readout window size "Locked" vs "Dynamic". Locked keeps
    the readout/popup a fixed size and position; Dynamic keeps today's
    grow/shrink behaviour. (Related to item 3, the bouncing popup.)
  - New setting: keep the last reply on screen while transcribing. The
    readout always shows two things at once: the agent's last answer and
    what the user is saying now, so the previous reply doesn't vanish.
- Earlier suggestions (agreed in spirit; overlap with the above):
  - Move the key list to its own "Keys" block or the About page.
  - Readout: a "Show preview" button, plus position and size options for
    the on-screen text.
  - Keys: make them changeable from here, or at least link to where they're
    set, instead of plain text.
  - Privacy: show where chats are stored and how much space they use, and a
    "Delete all saved chats" button with the warning + confirm style.
  - Give "Write what is said to the system log" the warning icon, since it
    keeps a transcript in the journal for weeks.
  - A one-line note that the mic always closes while the screen is locked,
    so people know it's covered.

## 21. About page

- Move "Repair installation" and "Remove Agent Voice" off About and into
  "Other settings" (the old Display & privacy page, item 20), with the
  warning + confirm style.
- Add a full list of voice commands (full stop, keep listening, stop
  listening, new chat, continue a chat, hand off to the terminal, the
  agents' wake phrases...), each with a one-line description of what it
  does. Generate it from the phrase lists in speech_text.py so it can't
  drift from the code (see voice-commands-notes.md).
- It's still an About page, not only commands. Keep and expand the
  "What's installed" section with normal About info:
  - Agent Voice version (and git commit/branch it's running from).
  - What runs locally (wake engines, transcription, voices) vs. what
    connects out to AI services.
  - Which backends are connected: Claude Code, Codex, other CLIs, and
    local model servers such as llama.cpp or Ollama, each with status.

## 22. Things not yet covered (suggested by Theo, approved by the user)

- About page:
  - "Copy diagnostics" button: version, settings summary, recent errors,
    with spoken text left out, for bug reports.
  - Check for updates, a short changelog, license, and a link to the README.
- General:
  - A search box across all settings pages ("where is the pause setting?").
  - First-run setup: a short guided walk-through (mic, wake word, first
    agent) for a fresh install.
  - Keyboard navigation and a light-theme check for the redesigned pages.
  - Item 1 (commands inside longer sentences) needs care: a command buried
    in normal speech could fire by accident, e.g. saying "stop listening
    to that song". Maybe only accept commands at the start or end of what
    was said, and say out loud when one fires.
  - Fix the shell-restarts-on-save bug (item 4) early, since all of this
    work will touch the plugin folder constantly.

## 23. Known bugs (all of them, for the plan)

From today:

- A. Voice commands only fire when said on their own; inside a longer
  sentence they go to the agent as plain text (item 1).
- B. The popup bounces: the "last heard" line appears and disappears
  during a chat, resizing the whole window (item 3).
- C. Turns were cut off at 30 seconds by the longest-turn limit with no
  warning. Raised to 90 s today as a workaround (maxUtteranceMs = 90000);
  the page should warn when it happens (item 13).
- D. The old global "what Claude Code may do" permission section is still
  on the popup though permissions are per agent now (item 2).
- E. Desktop tools, browser, Omarchy commands and notes sections are
  duplicated at the bottom of the Agents tab (item 8).
- F. Voice library rows misalign: the trash-can icon shifts the spacing so
  names and Test buttons don't line up (item 19).
- G. Tools & skills section shows only information, with no controls
  (item 11).

Carried over from bugs-notes.md in the plugin folder (2026-11-19):

- H. Shell restarts whenever an agent saves a file in the plugin folder,
  even a .md note. Seen again today. Guess: something watches the folder
  and reloads the shell on any change.
- I. Open-mic chats seem to lose earlier turns. Likely cause: changing the
  permission level rebuilds the agent and drops the session (seen at
  00:20:51 on 11-19), though a later flip to trusted didn't lose it. Check
  both paths, and whether the drop should be softer.
- J. Feels like new chats keep starting, with a random "be-deep" chime.
  Every reply ends with a "still listening" chime, and some turns are
  dropped as "not meant for it" or "nothing heard". Find which plays the
  surprise chime and whether any of them resets the chat.
- K. After turning open mic off, the "still listening" display may stay up
  too long (low confidence). Check whether it clears at once or waits out
  the follow-up window.

## 24. Agents should speak up when background work finishes

- Today, when an agent starts something in the background (a sub-agent, a
  long command), the result only reaches the user after they speak again.
  The agent has no way to say "that's done" on its own.
- Wanted: when background work finishes, the agent can start a turn by
  itself: a short spoken line ("the codebase doc is updated") plus a
  desktop notification, without waiting for the wake word.
- Respect: don't talk over the user or another agent (queue it); stay
  silent while the screen is locked, muted, or in a "do not disturb" mode
  (show only the notification); a setting per agent to turn it off.

## Next step after these notes

- Once the notes are done and laid out, start a separate session to sketch
  the new layouts (Agents tab cards, Overview stats, Chats section, popup)
  with drawing tools, before building anything.
