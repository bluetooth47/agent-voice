# Phase 17 (reworked): verification sweep and release decision

Living document. Started 2026-11-21. Planning only, nothing run yet.

The original Phase 17 in merged-plan.md (plugin folder) was a full
verification sweep of Phases 8–16. It was paused on purpose so the redesign
in feedback-notes-2026-11-21.md could land first. This version keeps its
core and extends it to cover the redesign. It runs **after** all of those
changes are built and installed.

## Core rules kept from the original

- Nothing new is built during Phase 17. Every finding is written up; fixes
  go in a follow-up phase, never quietly inside the sweep.
- It runs against the build installed from the exact revision meant for
  release. Record that revision at the top of the results.
- Fixtures only: a throwaway project, synthetic prompts, a test browser
  profile, harmless local actions, `logSpeech` off.
- Every case gets evidence (output, counts, screenshots, traces), not a
  "looked fine".
- A case that couldn't be run is written down as "not verified", never
  left out.
- Each backend is marked live, fixture-only, or not verified.

## Before it can start (entry gate)

- [ ] Every item in feedback-notes-2026-11-21.md is built, or explicitly
      deferred with a reason.
- [ ] Bugs A–K from that sheet are fixed or deferred with a reason.
      Bug H (shell restarts on save) must be fixed first, or the sweep
      itself will keep restarting the shell.
- [ ] Branches merged into one release candidate, installed, and the
      install verified (installed copy matches the commit).
- [ ] Project status report reviewed (project-status-2026-11-21.md).
- [ ] Rerun the Phase 8 latency baseline on today's hardware so V-11 has
      a fair comparison.

## The checks

Status: todo / running / pass / fail / not verified.

### Kept from the original (V-01 to V-12)

| ID | Area | What it covers (short) | Status |
|---|---|---|---|
| V-01 | Code | agentvoice-check green; bare-runner and full runs; mutation pass on every guard; fuzz every file the daemon reads; 10-min soak with 8 agents; code review at high effort | todo |
| V-02 | Install, migration, going back | fresh install in the box; upgrade over real state; kill mid-install; reinstall/uninstall keep folders; older build over new data; file modes 0700/0600 | todo |
| V-03 | Each backend | personality, instructions, communal vs agent precedence, roster answers, own skills only, safe edit in a temp git project; no user text in argv | todo |
| V-04 | Desktop and browser tools | per agent: allowed, denied, timeout, unsupported, switched off mid-session, two agents at once | todo |
| V-05 | Folders, notes, context | create/edit/rename/remove/restore, concurrent and stale saves, symlinks, full disk, outside edits, notesWrite deny | todo |
| V-06 | Collaboration | every crew tool both ways, every level, 3-hop chain, 4th hop refused, cycles refused, stop cancels chain, no level escalation | todo |
| V-07 | Injection | red-team list: poisoned web page, note, role line, brief, ask_agent answer, fake user message; 3 runs per victim backend; zero unintended actions | todo |
| V-08 | Voice and hardware | wake word, push to talk, headset vs speakers, mute vs stop, barge-in, lock/unlock mid-chain, sleep/resume, service and shell restarts mid-turn | todo |
| V-09 | Settings overlay | preview shots of every page, narrow/wide, dark/light, empty/full state; keyboard-only walk; clicks mode; error messages; qmllint | todo |
| V-10 | User experience | think-aloud task walkthrough (below) | todo |
| V-11 | Performance | median and p95 vs baseline: first word, stop to silence, pass time, ask time, prompt size, process count, memory | todo |
| V-12 | Privacy and recovery | nothing personal in argv or journal; nothing kept with saving off; audit log content-free; timed rollback | todo |

### New for the redesign (V-13 onward)

| ID | Area | What it covers | Status |
|---|---|---|---|
| V-13 | Design consistency | Every page uses the shared ui/ pieces (cards, compact selectors, chips, hints, warning+confirm). Pages flow in stage order. No leftover old-style rows. Audit by screenshot of every page side by side. | todo |
| V-14 | Voice commands | Commands said alone and inside sentences; false-trigger list ("stop listening to that song", "keep listening to me explain"); each command does exactly what the About list says; list matches speech_text.py. | todo |
| V-15 | Crew map | Links list enforced by crew tools (unlinked = denied, direction respected); quarantined agent reachable only via its links; map, table and saved list always agree; delete link confirms. | todo |
| V-16 | Chats | Chats section, proper names, details, search from the UI and by an agent's tool; bubble layout (user right, agent left); privacy settings now living under Chats. | todo |
| V-17 | Skills and tools | Auto-detected skills and tools appear; toggles actually turn tools on/off per agent; drag moves, Ctrl-drag copies, undo works; Unused area; communal tools apply to all. | todo |
| V-18 | Categorized notes | Note categories as files; drag between agents and Communal; agent tools see the right categories only. | todo |
| V-19 | Wake pipeline | Stage 1 / stage 2 / must-agree settings behave as shown; engine-specific settings appear only for the chosen engine; gate adapt-speed sliders take effect live. | todo |
| V-20 | Readout and popup | Locked vs dynamic size; no bouncing in locked mode; last reply stays visible while transcribing; old global permission section gone. | todo |
| V-21 | Overview stats and About | Stats numbers match the journal (turns, reply time, wake hits vs rejects, uptime, memory); About shows correct version/commit and backend status; copy diagnostics leaves out speech. | todo |
| V-22 | Risky actions | Every reset/delete/remove/start-fresh shows the warning and confirm; cancel leaves state untouched; confirm does exactly one thing. | todo |
| V-23 | Long turns | 90 s turn limit works; the warning appears when a turn hits the limit. | todo |

## UX walkthrough (V-10), updated

The user does each task thinking out loud, without coaching. After each,
ask what they think just happened and what happens next; compare with the
real state.

Kept from the original:

1. Make Sora more cheerful.
2. Give every agent a rule.
3. Why did Theo just say that?
4. Turn off the browser for Sora only; find out if she'd ask first.
5. Have Theo pass this to Sora.
6. Make Theo ask you before giving Sora any work.
7. What did Theo and Sora say to each other just now?
8. Delete an agent, then get it back.
9. Find what Sora wrote in shared notes yesterday, and undo it.
10. Rename an agent, then find its conversation.
11. Mute the microphone, then stop a reply.

New:

12. Let Hazel delegate to Sora but not the other way round (crew map).
13. Quarantine an agent so only Theo can talk to it.
14. Move a skill from Theo to Communal, then give a copy back to Theo.
15. Find last week's chat about the wake word, by searching.
16. Make the on-screen readout stop changing size.
17. Find out what "keep listening" does, without asking an agent.
18. Make the wake word harder to trigger by accident.
19. Find out which version is installed and whether anything talks to the
    internet.

Audit list (each "yes" is a finding): kept from the original, plus:

- Does any page still look like the old style?
- Does any page make you read a wall of text before you know what to do?
- Can a command fire when you didn't mean it?
- Does the crew map ever show a link the crew tools don't enforce, or the
  reverse?

## Output and release gate

Results go to phase17notes.md: every finding with severity (blocker /
should fix / polish), how to reproduce, and which follow-up phase fixes it;
measured numbers beside baselines; the coverage matrix (live /
fixture-only / not verified per backend and device); and a README update
that only claims what was verified.

Blockers: lost data, an unintended action or disclosure, a permission
failure, stuck audio, broken existing behaviour, a command firing by
accident, and any UX problem that stops a core task.

## How to run it (to decide)

- Who runs what: the automated parts (V-01, V-02, V-09, V-11, V-12, the
  fixture parts of V-03 to V-07) could go through the phase runner
  headless; voice, hardware and UX (V-08, V-10, V-14, V-20) need the user.
- Order suggestion: V-01 and V-02 first (if the build or install is broken
  nothing else counts), then automated checks, then hands-on, UX last on a
  stable build.
- Split into sessions, each with its own notes section, so it can pause
  and resume.

## Open questions

- Which backends are in scope for the release: all five, or only Claude
  Code and Codex?
- Is 8 agents still the right size for the soak and full-state screenshots?
- Should the red-team list (V-07) be written by another model, so it isn't
  written by the same agent being tested?
- Run the box install (downloads ~800 MB) or skip it with a note?
