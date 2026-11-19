# Merge decisions

Written 2026-11-18, alongside `merged-plan.md`. **Plan A** is
`agents-plan.md`. **Plan B** is `agent-voice-implementation-plan.md`. Code
claims were checked on `dev` at `2eeb919`.

The "Goal" section of the merge request was still the unfilled template
line, so the goal in `merged-plan.md` section 1 is taken from the two plans.
Correct it there if it is wrong.

---

## 1. Where the plans differed

| Area | Plan A | Plan B | Chosen | Why |
|---|---|---|---|---|
| Phase numbers | 8 to 16, continuing the repo's notes | 0 to 7, to be mapped later | 8 to 17 | The repo already has `phase1notes.md` to `phase7notes.md`. One extra phase comes from splitting collaboration. |
| First-release scope | Full collaboration and shared chats, recorded as user decisions | User-directed handoff only; agent-started work and group chats later | A's scope, in B's order | The user's recorded decisions stand. B's order is safer, so Phase 15 is user-started and Phase 16 is agent-started on the same path. Phase 16 is a clean cut line if the scope shrinks. |
| Agent identity | Assumes the main agent's id is `main` | One normalized record used by runtime, QML, permissions, chats and the panel | Keep the existing plumbing; one helper maps `""` to `main`; a read-only roster view for new code | The id plumbing already works and is security-relevant (hook, grants). Rewriting it is a large change to shared files for no user-visible gain. |
| Where knobs are stored | shell.json only, never in the folder | Existing structured settings | Same in both; kept | A value lives in one place. |
| Where the new knobs are edited | On the Agents card | Agent overrides on the Details page | Agents card, in a collapsed group | `test_settings_pages.py` allows one writing page per key, and `voiceAgents` is written by the Agents page. It also matches user decision 4. See open question 4. |
| Folder names | `communal/` with `rules.md` and `defaults.md` | `shared/` with `instructions.md` and `defaults.md` | A | "Communal" is the page name and the user's word, and rules against defaults is clearer than instructions against defaults. |
| The agent's short description | `card.md`, authored, plus a generated half | `role.md` authored; the card is a generated view | `role.md`; the generated half is computed and never written | "Card" already means the box on the Agents page (`ui/AgentCard.qml`). Two meanings of one word is the confusion A's own audit list looks for. |
| How agents learn about each other | A roster with tool lists in every preamble | Fetch cards on demand | A short roster (name, wake phrase, role) in the preamble; tools and busy state on demand through `list_agents` | Backends without the MCP server have no on-demand path, and an agent that does not know others exist never delegates. Keeping tools out of the preamble means a tool switch does not invalidate every agent's cached prompt. Phase 11 measures whether the roster earns its place. |
| Template location | `<repo>/templates/`, copied by `install.sh` | Shipped with the app; update the copy list if needed | `daemon/templates/` | `install.sh` copies only `daemon/`, `bin/` and `desktop/`. Under `daemon/` the installer does not change. |
| User override of the template | `~/.config/agentvoice/templates/agent/` | One shipped template | Dropped for now | Nobody asked for it, and it adds a path and tests. Listed as deferred. |
| Protecting the folders | Add them to `NEVER_SILENT` | Protect at each provider boundary and say what each runtime really enforces | Absolute-path checks in `_sensitive()`, a new read rule for other agents' folders, an enforcement table (plan section 3.5), and saved versions with an outside-change notice | A's rule covers only Claude below Trusted. Theo and Hazel run with no hook, so visibility has to stand in for enforcement there. |
| Unreadable or oversize files | Truncate, read missing as empty, publish the problem | Keep the last good text, show an actionable error | Truncate oversize; keep the last good text in memory when a file becomes unreadable; publish both | Silently dropping the communal rules for a turn because of a bad save is worse than using the last good copy. |
| Migration safety | Idempotent, never writes shell.json, one-release fallback | Backup first, validate, rehearse rollback | A, plus B's rules that an emptied file stays empty and that going back is tested | Nothing is deleted or rewritten, so the old settings are the backup. V-02 installs the older build over the new data. |
| Fixtures | An anonymized snapshot of the real shell.json | Synthetic only; production data stays out | Synthetic, shaped like the real machine | Anonymizing real instructions is easy to get wrong, and the shapes are what the tests need. |
| Latency gate | Median may not rise more than 150 ms | p95 may not rise more than 10% | Both: 150 ms on the median, and 10% or 300 ms on p95 | They catch different regressions. |
| Notes access | Private or communal; all agents write unless denied; per-note lock | Audiences and explicit writers per note | A | User decision 2, and A rules out per-note audiences. |
| Notes concurrency | Lock, history, last write wins | Compare the base revision under the lock; keep both on conflict | A's history plus B's base-revision check | Two agents writing one note should not lose an update. `notes_append` stays the easy path. |
| Notes metadata | `.locks.json` plus history file names | Author, audience, revision, timestamps | One `.meta.json` per notes folder | One sidecar instead of two, and it fails closed (corrupt means locked). |
| Where notes and collaboration tools live | `notes_mcp.py` or `desktop_mcp.py`, plus `collab_mcp.py` | An app-owned collaboration interface | One server, `crew_mcp.py` | One extra process per agent instead of two, and it must not depend on `desktopTools`. |
| Name of the feature | `hand_off` | "Send to another agent", distinct from "Continue in terminal" | "Pass": `pass_conversation`, "Send to another agent" | `Daemon.hand_off` already means the terminal handoff. |
| What a pass or delegation does to the chat | Adds the target to the source chat's participants | Keeps chats separate with a link; membership is a separate user choice | One transcript with every reply labelled; a pass or delegation adds the target to `shared_with` (user's answer to open question 3); otherwise being in it grants nothing | The user chose A's behaviour. B's concern is met by saying before the send that the whole chat goes with it. |
| Which session a task runs in | `ask_agent` in its own session; unstated for delegation | The target's own session, grants and project | A fresh session for a question; the chat's own session for the target on a pass or delegation | It keeps the target's private conversation clean and carries no session-wide approvals into the task. |
| Inbox location | `agents/<id>/inbox.jsonl` in the data folder | Briefs and transfer state are ephemeral when saving is off | `$RUNDIR/crew/inbox/` (tmpfs) | Messages then never outlive the session, whatever `saveChats` says. |
| The brief | Request plus a short summary | A bounded brief the user can review; no generated summary unless checked | By voice: the last exchange, capped. From the UI: a sheet showing the exact text | The user sees what leaves before it leaves. |
| Who speaks the announcement | "The caller says one sentence" | Announce or display the new active agent | A fixed sentence from a table, in the caller's voice | The same rule as progress talk: never model-written. |
| Editor saving | On blur and Ctrl+S | Explicit save with a pending state and kept drafts | On blur and Ctrl+S, with B's visible state and failed-save behaviour | `InstructionsBox` already saves on blur. Two saving styles in one overlay would confuse. |
| Instructions editor on the Agents card | Stays, writing the file | Detail pages hold long-form editing | Stays until Phase 12, then becomes a summary with a link | One editor per file. |
| Communal Chats tab | None; a filter in the Chats view | A Chats section on Communal | Both, as the same filtered list | It costs one preset filter. |
| Browser-hosted settings UI | "Web UI" means the settings overlay | A conditional workstream | Out of scope | The app has no browser UI and nothing asked for one. See open question 5. |
| Final sweep | Mutation, fuzz, soak, an injection list, a UX audit list | A matrix V-01 to V-12 with required evidence and a release gate | B's matrix structure filled with A's cases | B's "evidence required" column stops a confident reply standing in for an observed result. |
| Phase notes | A fixed template | A longer list of contents | A's template plus "Shared files touched", "Not verified" and "Going back" | Those three are what later phases and the sweep need. |

Covered by only one plan, and kept:

- From A: character budgets; the "What this agent is told" preview; the Rule
  of Two warning; trash and restore; depth, cycle and rate limits; the audit
  log; the injection list.
- From B: the per-backend compatibility matrix; the task state machine with
  dedupe and a recheck at dispatch; fixed chat ownership; knobs read fresh
  on every call; naming an endpoint as a remote recipient; reachable against
  merely enabled; marking skipped checks as not verified.

Covered by only one plan, and dropped: A's merge map for the A–G branches
(they are already merged); B's normalized agent record; B's per-note
audiences; B's browser UI workstream.

---

## 2. Assumptions that are wrong for this codebase

**In Plan A**

1. **"The A–G branches are not merged."** Every one of `phase-b` to
   `phase-g`, `latency-2` and `test-fixes` is an ancestor of `dev` (zero
   commits ahead). There is no later merge to plan for. Terminal handoff,
   open mic and progress talk are live and had to be designed against
   directly.
2. **"The main agent's id is `main`."** Its `Persona.id` is the empty
   string, saved chats store `""`, and `agent_id_for()` only maps old names
   to ids. `main` exists at the CLI and panel edges.
3. **"Adding the folders to `NEVER_SILENT` stops an agent rewriting its own
   instructions."** `NEVER_SILENT` holds path fragments, not locations. More
   importantly, the hook is installed only for Claude below Trusted. Theo
   (Claude, Trusted) and Hazel (Codex, Trusted) have no hook, so the rule
   does nothing for two of the three real agents.
4. **"The agents are Theo and Sora."** There is a third, Hazel, on Codex at
   Trusted, with an id that differs from her name.
5. **"Check migration by asking Theo something his instructions decide."**
   Theo has no instructions set. Only Sora does.
6. **"`install.sh` copies `templates/`."** It copies `daemon/`, `bin/` and
   `desktop/` only.
7. **"A notes write is silent at Edits."** At Edits the hook silently allows
   only the four file-edit tools inside the project. Any other tool is asked
   about, so the notes tools need an explicit rule.
8. **"Every backend can receive collaboration", with the roster listing
   enabled agents.** An enabled agent whose wake word the engine cannot hear
   is never built, so it cannot receive anything.
9. **"Chats gain `participants`."** `chats.record()` overwrites `agent_id`,
   `backend` and `session_id` on every exchange, so a second speaker would
   take the chat over. Ownership has to be fixed first.
10. **"Remove the instruction keys from manifest, DEFAULTS and the page in
    one commit, after a release of fallback."** The page stops writing
    `agentInstructions` in Phase 10, and the one-writer test then fails
    unless the manifest key goes at the same time. The manifest and page
    change together in Phase 10; only the `DEFAULTS` read lingers.
11. **`hand_off` as the tool name.** `Daemon.hand_off` already exists and
    means something else.

**In Plan B**

1. **Agent-started collaboration and group chats as optional follow-ons.**
   Plan A records both as decided by the user.
2. **One normalized agent record as a prerequisite.** Stable ids already
   reach chats, grants, the hook and the panel. The rewrite is not needed
   for anything in scope.
3. **A possible browser-hosted settings UI.** The UI is QML in Quickshell.

**In `CODEBASE.md`**

- "The main agent's id is `"main"`" is true only at the edges (see A2).
- "Feature branches `phase-b` … `phase-g` exist too" is true, but they hold
  nothing that `dev` lacks.

**Not checked:** Plan B's baseline of 1,763 passing tests; its statement
that Antigravity has no Edits mode; whether Codex loads skills natively
(Phase 13 tests it with a real turn); whether the Agents page already saves
an id for an entry that lacks one (Phase 10 confirms it).

---

## 3. Open questions

**Answered by the user on 2026-11-19 (Phase 8).** Every proposal was
accepted except question 3: a pass or delegation **adds the target to the
chat**, so it is replayed the transcript, not only the brief. Question 1 was
answered "announce by default, with ask and silent as options", which is the
four-level setting already in the plan. The answers and what each changed
are in `merged-plan.md` section 1; the original questions are kept below.

Each has a proposal, and the merged plan is written as if the proposal
holds. Questions 1 and 2 should be answered before Phase 8 closes.

1. **What is the default for `collaboration`?** Plan A proposes `announce`.
   That means that after the upgrade Theo may start delegating on his own,
   with one spoken sentence and a 3-second stop window. `ask` is the
   cautious alternative. *Proposal: `announce`, as Plan A has it.*
2. **Is the full scope still what you want for the first release?** Plan A
   records your decisions as full agent-to-agent communication and shared
   chats. Plan B recommended shipping user-started passing first and adding
   the rest later. *Proposal: keep the full scope; Phases 15 and 16 are
   ordered so you can stop after 15.*
3. **When Theo passes or delegates to Sora, should Sora get the whole chat
   or only the brief?** Plan A added her to the chat. Plan B kept access
   separate. *Proposal: she appears in the transcript but receives only the
   brief, and "Share chat with…" is the explicit step that gives her the
   rest.*
4. **Where should the per-agent tool switches be edited?** The repo's
   one-page rule puts them on the Agents card, which already has about
   twelve controls. The alternative is the Details page's Tools tab, which
   needs either a different storage shape or an exception in the test.
   *Proposal: the Agents card, in a collapsed group, and let UX task 4
   decide whether that is findable.*
5. **Does "WebUI" mean the settings overlay?** *Proposal: yes, and no
   browser-hosted UI is planned.*
6. **Can a note be locked read-only by you?** (Carried over from Plan A.)
   *Proposal: yes.*
7. **Is "visible, with Revert" enough for a Trusted agent changing its own
   instructions?** Nothing in the app can stop a Trusted agent doing it. The
   options are to accept visibility, to lower Theo's level, or to add
   sandboxing later. *Proposal: accept visibility for now and list
   containment as deferred.*
8. **May undelivered agent-to-agent messages be lost at logout?** The inbox
   is on tmpfs so that nothing outlives the session. *Proposal: yes.*
