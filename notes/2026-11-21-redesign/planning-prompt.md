# Prompt: build the next Agent Voice plan

Copy everything below the line into the planning model. It is written to be
given to more than one model; compare their plans afterwards.

---

You are planning the next round of work on **Agent Voice**, a hands-free
voice front end for AI coding agents on an Omarchy (Arch + Hyprland +
Quickshell) desktop. A Python daemon (systemd user service) handles wake
word, transcription and speech; a QML Quickshell plugin is the settings
window, bar widget and popup. Your job is to produce a **build plan only**.
Do not write or change code.

## Read these first, in this order

All notes are in `~/agentvoice-notes/`. The repository is
`~/.config/omarchy/plugins/duaneoca.agentvoice`.

1. `CODEBASE.md` (in ~/agentvoice-notes): how the code works today, at
   branch `orders-guard`, commit `92c71ff`.
2. The repo's `CLAUDE.md`: binding rules for working on this project
   (checks before every commit, what earns a test, "settings are three
   things", fail-open rules, the mic closes when the screen locks, and so
   on). Your plan must respect every one of them.
3. `project-status-2026-11-21.md`: branches, what's installed, test
   health, risks.
4. `feedback-notes-2026-11-21.md`: the user's requested changes, page by
   page, items 1 to 22 and 24, plus all known bugs in section 23 (A to K). Every
   item is approved unless it says otherwise.
5. `mockups/index.html`: clickable sketches of the redesigned pages. Treat
   them as the intended layout and behaviour, not pixel-exact designs.
6. The repo's `merged-plan.md` (Phases 8 to 16 done; read it for the
   house style of a phase, the notes template, and the risk table) and
   `voice-commands-notes.md` (the planned Agent Voice skill and command
   list).
7. `phase-17-plan.md`: the verification sweep that runs **after** this
   plan is finished. Your plan must leave the project ready for its entry
   gate.

## Current state, in short

- Phases 8 to 16 plus the orders guard are built, pushed to the user's
  fork, installed and running. 2790 tests pass, all static checks green.
- `dev` and `main` are 32 and 39 commits behind `orders-guard`. Nothing
  newer is merged into them.
- Local `main` tracks upstream `origin`. **Never push to origin**; push
  only to the `fork` remote.
- Writing any file inside the plugin folder restarts the desktop shell
  (bug H). Plans, notes and scratch files belong in `~/agentvoice-notes/`.

## What the plan must contain

1. **Phase 0, housekeeping**, before any feature work:
   - Fix bug H (shell restarts on any write to the plugin folder) first,
     since every later phase writes there.
   - Bring `dev` and `main` up to date with `orders-guard` (fast-forward;
     it's one straight line), and make local `main` stop tracking origin.
   - Disable the finished phase-runner service so it stops notifying at
     every login.
2. **Phases**, each small enough for one focused session, in an order that
   respects dependencies. Suggested grouping (change it if you have a
   better reason):
   - Shared UI building blocks in `ui/` (cards, compact selector, chips,
     hint, warning + confirm, draggable card) so every page uses the same
     ones (item 17).
   - Remaining bugs A to K.
   - Page by page: Agents, Agent details, Communal, Chats, Crew map,
     Listening, Conversation, Voice, Other settings, About, Overview, bar
     popup and readout.
   - Backend work the pages need: chat names, summaries and search (also
     as an agent tool), tool and skill auto-detection, skill and note
     moves, note categories, crew links list enforced by the crew MCP,
     quarantine, stats collection, voice commands inside sentences (with
     the misfire safeguards), the Agent Voice skill.
3. **For every phase:** goal; the feedback items and bug letters it
   covers; files likely touched (call out the big shared files
   `wake_listen.py`, `Settings.qml`, `AgentsPage.qml`); new settings with
   all three parts (manifest, `runtime.py` DEFAULTS, a page control);
   tests to add per CLAUDE.md; how it's verified (agentvoice-check,
   `bench/preview/preview.sh` screenshots, a live voice check where
   needed); risks; and what an older build sees after it (going back).
4. **Security review points.** Several features widen what agents can do:
   auto-detected tools, agents searching chats, skills and notes moving
   between agents, the crew map. For each, say how it stays fail-closed
   (unlinked = denied, quarantine enforced in the daemon and not only in
   the UI, new tools off by default, nothing spoken put in argv).
5. **A mapping table**: every feedback item (1 to 22, and 24) and bug (A to K) to
   the phase that delivers it, or "deferred" with a reason. Nothing may be
   silently dropped.
6. **Open questions** for the user, kept short.

## Constraints

- No setting is removed; settings are regrouped. Fine-tuning goes under
  collapsed "Advanced" sections.
- Each phase ends with `./bin/agentvoice-check` green and its notes file
  (`phaseNnotes.md`, template in merged-plan.md).
- Branch per phase off the previous one; push to `fork` only.
- QML changes need a shell restart to show up; say so in each verification
  step. Use the preview tool for screenshots instead of the live shell.
- Measure, don't assume: anything claimed faster or smaller needs a number.
- Keep the plan readable: plain language, short sections, tables where
  they help.

## Output

One markdown file, `next-plan.md`, written to `~/agentvoice-notes/` (not
the plugin folder). Start with a one-paragraph summary, then Phase 0, the
phases, the security points, the mapping table, and open questions.
