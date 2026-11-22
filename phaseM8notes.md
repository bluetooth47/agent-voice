# Phase M8: Crew links and quarantine, enforced, with the table

Written 2026-11-22, unattended (started by the runner script). Branch
`phase-m8`, cut from `phase-m7` at 8756c0b. Result commit: the notes commit
on top of a64219f, pushed to `fork/phase-m8` only; `dev` fast-forwarded to
it and pushed to `fork`. Model: Claude Opus 5.5 (tier A in the plan).

Commits:
- 1e15005: the phase;
- 789761d: Codex pass 1 fixes;
- a973171: Codex pass 2 fixes;
- a64219f: a broken link list refuses agent calls and nothing else (found
  by the live check);
- then these notes.

Deployed: **yes**, twice, through `bin/agentvoice-deploy --install` (its
strict check green both times: 3657, then 3662 tests):
- a973171 replaced M7's 152a109;
- a64219f replaced a973171, after live check D found a bug (below).

The daemon was idle before each (state `listening`, no task running, no
open mic, unlocked). **The way back to before M8 is `bin/agentvoice-deploy
152a1097e592`**; the script's own "way back" line names a973171.

Installed: **yes**, both times: "Build 0.2.0 (a64219f), replacing 0.2.0
(a973171)". The daemon, the crew server and the hook changed.

**Shell restart needed** (the Crew map page, the Send sheet and the
shortcuts are QML). Not run: the next stop point is after M9. **Until the
restart there is no Crew map page in the running shell, and no crew links
are set on this machine, so no agent can reach another** (question 2's
default; open issue 1). A pass the person starts still works.

A copy of `shell.json` was taken before the first deploy
(`~/agentvoice-notes/shell.json.before-M8`, mode 0600). The live checks
changed `crewLinks` through `omarchy bar set` (only that key, checked);
afterwards the file was put back from the copy and is byte-identical to it.

`./bin/agentvoice-check`: green on a64219f.
- **3662 tests** (was 3433; +229), 14 of 14 static checks, "the check
  wrote nothing in the tree: ok".
- The bare-runner variant (`AGENTVOICE_STRICT=1`, a venv with only
  requirements-dev): green on 1e15005 (3621 passed, 9 skipped, the existing
  numpy skips) and on a64219f (3646 passed, 9 skipped).
- Box: not run (`install.sh` did not change).

## What was built

**The rule, in one place** (new `daemon/crew_links.py`, pure, standard
library). Two settings, both by stable agent id (`main` for the main agent):

- `crewLinks`: `[{"from", "to", "allow": [ask|delegate|message|pass],
  "askFirst"}]`. A link has a direction.
- `crewQuarantine`: `[id, ...]`.

What they mean:
- **No link, or a link that does not list the ability, is refused.** An
  empty or missing list is nobody linked (question 2's default).
- **Unreadable is every agent-started call refused**: not a list, `null`, an entry that is
  not exactly a link (an unknown key, no `allow`, an unknown or doubled
  ability, a non-bool `askFirst`), the same pair twice, a self-link, more
  than 128 links; or settings that cannot be read at all
  (`Config.settings_readable`, which includes shell.json giving a key
  twice). An id nobody has is not malformed: an agent was removed, and it
  matches nothing.
- **Quarantine**: nothing out of a quarantined agent; into one, only `ask`
  and `delegate` count.
- `askFirst` makes the effective level `ask` (the M7 card), short of `off`.
- `everyone(ids)` is "Link everyone as before": every ordered pair, every
  ability, none asking first.
- `refusal()` gives the sentence and the audit code: `no-link`,
  `quarantined`, `crew-unreadable` (added to `audit.REASONS`).

`runtime.Config` gains `crew()`, `crew_links()` and `quarantined()`, built
from that Config's values; collaboration reads a fresh Config for every
check (`Runtime._crew`), never the copy the daemon last loaded.

**Enforced in the daemon** (`daemon/collab.py`):
- **Request**: `_guard` (unreadable and a quarantined caller first, then the
  link, then everything that was there before).
- **Approval**: after the card or the spoken line, the guard again with a
  fresh read, plus the target's quarantine and the effective level
  compared with what it was admitted under.
- **Dispatch**: `start()` before and after the catch-up and the chat
  lookup, and `_prepare` before and after the chat share (taking the share
  back); a question, before its side turn starts and again once its
  adapter is registered. One gate, `_task_refusal`: link, quarantine, and
  the level (off, or stricter: `askFirst` gained while it waited).
- **Delivery**: an answer before it is handed back; messages and delegated
  results at the start of the caller's next turn (`deliveries`). A result
  whose agent's quarantine changed since it was given is withheld, a
  quarantine-and-release in between included (a per-agent epoch).
- **The sweep** (`Runtime.sweep`, every poll, before the lock check):
  queued work whose gate now refuses is refused, running work cancelled
  with its turn and anything it started. It watches the settings files
  itself (`Daemon.watched_config`, two stat calls a poll), because the
  daemon's own copy is not refreshed while the mic is off.
- An unreadable list flashes "Crew links can't be read: agents can't reach
  each other" in the HUD (at most once per 6 s) and says so in the journal.

**Quarantine, carried out**:
- the caller's collaboration tools are hidden (`crew_mcp.offers_collab`,
  shared with the daemon's warm-process check, so a change lets the idle
  process go) and every call refused, the read-only ones included;
- a delegation or question into it carries at most 1000 characters of
  task and summary together (`quarantine_cap`, cut with a marker, before
  the card so the card shows what goes); a delegation runs in a new
  session, with no share, no replay, its own conversation put back after,
  and its turn saved into a chat of its own;
- its answers, results and the aside in the caller's saved chat are marked
  "from a quarantined agent";
- no communal-note writes (checked again inside the store's lock); a
  quarantine list that cannot be read refuses them too; its own notes and
  reading are unaffected;
- the moment it is seen quarantined it is owed a detach, carried out when
  it is idle even if released first: its conversation and warm process let
  go, then every chat stops being shared with it and forgets its sessions
  (`ChatStore.detach`), retried if the chat store will not take it.
  Release restores nothing;
- `continue_chat` holds it to its own chats; `chats share` into quarantine
  and `chats continue` of another's chat are refused.

**A pass the person starts** needs no link, but never goes into quarantine:
voice ("Sora is quarantined. Release it on the Crew map first.", spoken),
the Send sheet (greyed, with the reason), `agentvoice pass` (stderr), and
again when the daemon takes the request and when the turn starts. Settings
that cannot say whether the target is quarantined refuse it. A pass out of
quarantine is marked in the brief.

**What agents are told**: `list_agents` lists only the agents the caller
may reach, each with `you_may`, `asks_the_person_first` and `quarantined`,
or says nobody is linked. Each agent's prompt roster
(`reconcile_parts`) names only those agents, none for a quarantined one or
while the list is unreadable.

**The orders guard** (pass 1, beyond the plan) asks at every level about
`agentvoice pass`, `collab.py pass`, `agentvoice chats share` and anything
under `$RUNDIR/crew`, whitespace folded: a pass the person files is
governed only by quarantine, so an agent filing one itself would step
round its links.

**The Crew map page** (`pages/CrewMapPage.qml`, the tenth page, after
Communal):
- an unreadable list: a banner saying why, and "Start again with no links"
  (a `DangerButton`);
- no links: "No links yet, so agents cannot reach each other" and **Link
  everyone as before** (a `DangerButton`, question 2);
- the table: From → To, Delete (`DangerButton`), the four abilities as
  `ToggleChips` (disabled with the reason into or out of quarantine), Ask
  me first (labelled "advisory: Theo is Trusted" when the caller is
  Trusted, and a Hint under the table: M7 open issue 1), and the effective
  line, e.g. "Theo → Sora: ask, delegate, message, pass · asks you first
  (link; advisory, Theo is Trusted) · announces (Theo's level)";
- Add link (From, To; a new link allows ask);
- per agent: Quarantine (a `DangerButton` whose question says what it
  loses: its links out, message and pass on links in, its sessions and
  shared chats) or Release; can reach / reached by;
- "Changed outside Settings at HH:MM", tracked by the overlay
  (`crewOutsideAt`), which stays loaded; the sidebar badge shows it and an
  unreadable list;
- an Overview line for an unreadable list, or agents with no links.

All writes go through `writeLinks` and `writeQuarantine`; quarantine is
written before the links it trims. The page's reading of the lists, what
each link allows, and every edit are run in node against the Python
(`test_crew_links.py`). `test_confirms.py` holds link delete, link
everyone, quarantine and crew reset to `onConfirmed`.

**Shortcuts**: Ctrl+1..9 the first nine pages in sidebar order, Ctrl+0 the
tenth, Ctrl+PgUp/PgDn step (`Settings.pageForKey`).

**The Send sheet**: a quarantined target is listed "(quarantined)", Send is
greyed with the reason, and `send()` refuses too.

**Docs**: the stale `collab.py`/`crew_mcp.py` docstrings fixed; CODEBASE
(module, flow, page, settings, preview target, guard, the known-issue line
removed), README (a new "Agents working together, and the Crew map"),
SECURITY (a limitation entry), CLAUDE.md (an eighth fails-open rule: "A
link that was there when the work was asked for is not a link now").

**Settings** (both defaults-only in the manifest, as lists are; `[]` in
`runtime.DEFAULTS`; no TOML alias; written only on the Crew map):

| Key | Default | Unreadable |
|---|---|---|
| `crewLinks` | `[]`, nobody linked | every agent-started call refused, with the reason (and nothing else) |
| `crewQuarantine` | `[]` | every agent-started call refused; every agent's crew tools hidden; communal writes, user passes and shares refused |

**Preview**: target `crew` (`--arg empty|linked|clicks`, `:520` for the
narrow card), config `crew3.json`. `clicks` drives Link everyone (armed →
Cancel, then confirmed), a chip, Ask me first, Delete (Cancel, then
confirmed), Add link, Quarantine and Release through real saves, and checks
each list written: **18 of 18 PASS**, one `bar set` per action, quarantine
written before the links. Shots: 3 agents empty and linked (narrow, dark
and flexoki-light), 8 agents linked (wide and narrow, dark), 8 agents empty
(wide, light). The screenshots were looked at and left in /tmp (not
kept in the repository, as before).

## What was proven, and how

**Tests, against the real call path** (the socket with the kernel's pid,
the daemon's own record of who is calling, the board, the poll, a real
ChatStore), in `tests/test_collab.py` section M8 and
`tests/test_crew_links.py`:
- **The matrix**: both directions × the four abilities × the link missing
  (linked the other way only), unreadable, revoked (listing every other
  ability) or present × nobody, the target or the caller quarantined: 96
  cases, each refusal with its code and nothing dispatched or asked.
- A change read on the next call of a warm client; the link deleted while
  the card was up; `askFirst` raising the card at `allow` (and not lifting
  `off`); `askFirst` gained while queued; a queued job refused by the poll
  after its link was deleted, and by `start()` with the poll held off;
  running work cancelled; a question whose link goes while it is answered
  not handed on; a question waiting for a busy agent checked before any
  side turn is built; a message and a result judged again at delivery;
  `list_agents` filtered; settings that will not load refusing everything;
  `task_status` and `cancel_task` still working when the list is unreadable.
- Quarantine: the capped brief with nothing of the chat and a new session;
  marked answers; detach and revoke, once, and release giving nothing back;
  a busy agent detached when its turn ends; queued work refused; the crew
  server hiding and refusing the tools; the daemon refusing every tool;
  communal writes refused (own notes fine); `continue_chat` refused even
  with a share put back by hand; the warm process let go on a quarantine.
- User passes: no link needed; refused into quarantine out loud, when
  queued, with an unreadable list, from the CLI; a pass out of quarantine
  marked; `chats share` into quarantine refused.
- The page's JavaScript in node against the Python: 21 inputs read the
  same, the effective abilities agree for every pair, each edit writes the
  exact list; each key written in one function; quarantine before links.
- Codex's 13 findings, each with a test (classes `TestCodexPass1`,
  `TestCodexPass2`, and the orders-guard cases in `test_cards.py`).

**Mutations: 70, all red at the end.**
- 48 on the phase: 43 red on the first run. The 5 that survived were real
  gaps in the tests, each closed: quarantine changing while the card was
  up, the `continue_chat` block on its own (the revocation hid it), the
  warm-process restart on a quarantine, the HUD line said by an acting call
  (list_agents said it too), and a question checked before its side turn
  (the delivery check caught it later).
- 12 on pass 1's fixes, one surviving until a test for `askFirst` gained
  during the catch-up; 5 on pass 2's fixes; 5 on the live-found fix
  (`quarantined()` and the four reads that now use the quarantine alone).
- They covered each guard (request, approval, dispatch, delivery, sweep),
  `_effective`, the gate, the capped brief, the marks, the user-pass
  refusals, `list_agents`, the detach (persona, chats, busy, owed, retry,
  epoch), `crew_links` (quarantine out and in, unknown keys, duplicate
  pairs, `ok`, the unreadable refusal), `crew_mcp` (listing, communal,
  `quarantined()` failing closed, `offers_collab`), `Config.crew`'s
  readability, `chats.detach` and `quarantine_refusal`, the
  `continue_chat` block, the roster filter, the warm-process flag, the
  page's parsing, quarantine filter, trim and write order, a Delete moved
  to `onClicked`, and the Send sheet's denied state.
- The runner script lived in /tmp; every file was restored (checked by
  md5 after each run).

## Shared files touched, and where

- `daemon/collab.py` (big shared, +620/−68 over the phase): the docstring; `Task.into_quarantine`
  and `q_epoch`; the quarantine sentences; `quarantine_cap`; the crew
  methods (`_crew`, `_crew_seen`, `_effective`, `_link_refusal`,
  `_task_refusal`, `_gate`, `_said_refusal`, `_crew_said`,
  `_user_pass_refusal`, `is_quarantined`, `sweep`, `_withdraw`,
  `_apply_quarantine`, `_detach`); hooks in `pass_conversation`, `tick`,
  `start`, `_prepare`, `_roll_back`, `_guard`, `_permit`, `_card`, `_act`,
  `_hand`, `_ask`, `_report`, `deliveries`, `_run_call`, `_list_agents`,
  `cli_pass`.
- `daemon/wake_listen.py` (big, +~40): `continue_chat` (quarantine block),
  `apply_extras` (`offers_collab`), `reconcile_parts` (the roster filter),
  new `watched_config`.
- `Settings.qml` (big, +~75): the page entry, loader and component,
  `pageForKey` and the key handler, the sidebar hint, `crewUnreadable`,
  `crewProblem`, the Overview line, the outside-change tracker.
- `daemon/permission_hook.py` (security-critical, +~25): `_crew_dirs`,
  `CREW_WORDS`, the whitespace-folded match. Nothing else in the hook
  changed; its decision paths for silence, failure and malformed input are
  untouched.
- Also: `daemon/crew_mcp.py`, `daemon/chats.py`, `daemon/runtime.py`,
  `daemon/audit.py`, `ui/SendSheet.qml`, `manifest.json`, `pages/qmldir`.
- Untouched: `AgentsPage.qml`, `AgentDetailsPage.qml`, `Panel.qml`,
  `agentfs.py`.

## Measured

On this machine (i7-1185G7, 8 threads), the daemon's venv Python:
- **The link check** (`crew_links.refusal` on a nine-agent, 72-link list):
  **0.89 µs** (n=20,000).
- **Parsing a 72-link list**: median **366 µs** (n=500).
- **What every crew call pays for reading the settings fresh**
  (`Config()` + `crew()` on the real 4,105-byte shell.json): median
  **577 µs**, max 1,118 µs (n=200). A call reads them several times (the
  guard, the level, twice more after a wait), so a few milliseconds a call,
  against seconds for a turn. The sweep re-reads only when the files'
  stamps move.
- **Live**: Theo's turn that delegated took 17.6 s (first token 2.0 s);
  Sora's task turn 5.2 s (first token 1.3 s). The refused calls came back
  inside Theo's turn (20.4 s and 23.2 s turns, mostly the model).
- Tests 3433 → 3662. The check's test run is about 3 min 10 s (was 2:50).
- No speed or size claim is made, so nothing went to FINDINGS.

## Different from the plan, and why

- **"`agentfs.py` (roster label)"**: the roster each agent is told is
  filtered in `wake_listen.reconcile_parts`, and `list_agents` in
  `collab._list_agents`, where the per-agent view is; `agentfs.py` was not
  touched.
- **The tools stay listed for an agent with no links**; only off and
  quarantine hide them. A call then comes back "the Crew map has no link
  from you to Sora", which the agent can say; a missing tool says nothing.
  `list_agents` and the prompt roster are filtered, as the plan says.
  Open issue 4.
- **Quarantine revokes rather than blocks.** "Old native sessions detached"
  and "replay grants blocked" are done by taking the agent out of every
  chat's `shared_with` and `sessions` (and the live block in
  `continue_chat` besides), so "leaving quarantine grants nothing" holds
  literally. Quarantining from the page also drops the agent's links out
  and message/pass on links in, which the confirm says (M9's "a confirm
  that shows what it loses", taken for the table too). The daemon enforces
  quarantine whatever the links say, so a hand-written quarantine works
  the same. Open issue 5.
- **Beyond the plan**: the orders guard's crew words (pass 1); `chats share`
  and `chats continue` refusing quarantine; a pass out of quarantine marked;
  "Start again with no links" for an unreadable list; the Overview line;
  the HUD flash; the quarantine epoch and owed detaches (pass 1 and 2).
- **"Unreadable = refuse every agent-started call"** also refuses a pass the
  person starts and a communal write when the *quarantine* list cannot be
  read, since then nobody can tell who is quarantined.
- **Both settings are defaults-only** in the manifest (lists; Omarchy cannot
  draw one), like `voiceAgents`, and have no TOML alias.
- **The table for eight agents is 56 rows.** Not grouped; M9's map is the
  compact view. Open issue 8.
- **Chat search for a quarantined agent (M20)** is not built: CLAUDE.md's new
  rule says it must call `crew_links.refusal`.
- **Codex pass 1 was sent the daemon diff plus `Settings.qml` and
  `ui/SendSheet.qml`** (1,686 lines), not the Crew map page (its logic is
  checked in node against the Python), to save credits. Pass 2 got pass 1's
  daemon fix diff (407 lines). **Pass 2's fixes and a64219f (the live-found
  fix) were not reviewed by Codex.**
- **Codex ran on the read-only copy both times**; `codex sandbox linux --
  true` still panics ("Failed to execvp linux"). The clone's HEAD and status
  were unchanged after both passes. After pass 1 the copy was left in place
  (still read-only) until pass 2's setup found it; it was then deleted, and
  the pass 2 copy was deleted straight after.

## Codex review

**Pass 1** (8 findings, all fixed in 789761d):
1. An agent could run `agentvoice pass` (or write a request file) and pass
   as the person, stepping round its links. The orders guard now asks
   about it at every level.
2. A quarantine during the catch-up or the chat store's lock was decided on
   the first read. Checked again after both, and after the share.
3. The sweep read the daemon's copy of the settings, stale while the mic is
   off. It watches the files itself.
4. A busy agent quarantined and released before its turn ended was never
   detached. Owed from the moment it is seen.
5. A chat store that would not take the revocation counted as done. Retried.
6. A queued question skipped the level (`askFirst` gained, or off). One
   gate holds the level everywhere.
7. A result was delivered after its agent was quarantined. Withheld.
8. A quarantined agent's answer lost its mark in the saved chat. Kept.

**Pass 2** (5 findings, all fixed in a973171):
1. Extra whitespace hid `agentvoice  pass` from the guard. Folded.
2. Something was shared before the gate refused it, and a failed unshare
   was swallowed. A gate before the share too; the failure is logged.
3. A question cancelled before its adapter was registered was still sent.
   Checked once the adapter is registered.
4. A quarantine and a release before delivery left both readings equal. An
   epoch per agent.
5. The last gate did not hold `acceptsWork`. It does.

## Found along the way

- **Found live, fixed in a64219f: a broken `crewLinks` reached too far.**
  `Config.quarantined()` went through `crew()`, so a malformed link list
  made the quarantine "unreadable" as well. In live check D every agent's
  crew tools were withdrawn ("tools for “Theo”: desktop · omarchy" in the
  journal), so Theo could not even make the call that would have told him
  why, and said "the ask agent tool has been taken away from me". It also
  refused every agent's communal notes, and would have refused a pass the
  person started, continuing a shared chat and carrying out a quarantine.
  Still fail-closed, but wider than the rule. `quarantined()`, the user
  pass check, `is_quarantined`, the CLI and the sweep's quarantine now read
  the quarantine list alone. Five tests, four mutations, all red.

- **On this machine, after the install, no agent can reach another** until
  someone links them: there is no `crewLinks` in shell.json, and the Crew
  map page that offers "Link everyone as before" is QML, which the running
  shell reads only after `omarchy-restart-shell` (stop 2). That is question
  2's default; the gap until the restart is open issue 1.
- **Quarantine changes saved chats for good**, by design (release grants
  nothing). On this machine Sora is in 7 saved chats and Hazel in 3, so the
  live quarantine check was not run unattended (below).
- My mutation runner's first `-k` selections did not always include the
  test that catches a mutation, and on the re-run I mapped two survivors to
  the wrong entries. Each survivor was re-run by hand against named tests
  before being counted either way.

## Not verified

- **The Crew map page in the real shell.** It needs `omarchy-restart-shell`,
  held for stop 2. Seen only in `preview.sh` (screenshots and the clicks
  run). Until then the running shell has M7's QML: no Crew map page, and
  the Send sheet without the quarantine state (the daemon and the CLI
  refuse such a pass anyway).
- **Link everyone as before, quarantine and release clicked in the real
  shell.** Synthetic clicks only (QtTest's TestEvent, in the preview).
- **The keyboard**: Ctrl+0 and Ctrl+PgUp/PgDn, and a keyboard-only walk of
  the page. Tested by reading `pageForKey`, not by pressing keys.
- **"Changed outside Settings at HH:MM"** in the real shell (the overlay
  that tracks it is QML).
- **The live quarantine checks** ("quarantine Sora; Theo's ask runs while
  his pass is refused"). Not run: quarantining any agent on this machine
  revokes its sessions and shares in the user's saved chats (Sora is in 7,
  Hazel in 3), and release gives none of it back, by design. Proven by
  tests against a real ChatStore. For stop 2, with the user's say-so: back
  up `~/.local/share/agentvoice/chats`, or accept the revocation.
- **A user pass into quarantine by voice**, live. Tests only.
- **The Codex path** (`crew_mcp --guard`) with links or quarantine, live.
  Tests only.
- **The Send sheet's denied state** was not screenshotted (a static test
  holds it).
- **Pass 2's fixes and a64219f were not reviewed by Codex** (credits).
- **The installer box** (`install.sh` did not change).

## Going back

`bin/agentvoice-deploy 152a109` from the clone (M7's last deploy, printed
by the deploy as the one replaced), then `./install.sh --yes` from the
plugin folder once the daemon is idle, then `omarchy-restart-shell`.
- An older build **ignores `crewLinks` and `crewQuarantine`**: collaboration
  goes back to all-to-all, quarantine lifts, and nothing is filtered from
  `list_agents` or the rosters. That is **fail-open on downgrade**: master
  plan 7.7 first. On this machine no link and no quarantine has been set,
  so today there is nothing to turn into denials beforehand.
- Shares and sessions revoked by a quarantine stay revoked (nothing was
  quarantined here).
- The orders guard's crew words go with the build.

## Open issues, for the next phase

1. **Question 2 taken by default: nobody linked, with "Link everyone as
   before".** On this machine that means no agent can reach another from
   now until stop 2: the page with the button is QML the running shell
   has not loaded. Meanwhile `omarchy bar set duaneoca.agentvoice
   crewLinks '<json>' --json` is the only way to link agents. Acceptable
   for the one phase until stop 2, or should the runner link everyone
   until the user has seen the page?
2. **Question 11 taken by default**: quarantine blocks communal-note
   writes (built) and chat search (M20 must honour it; CLAUDE.md says how).
3. **M7's open issue 1 carried**: "Ask me first" is labelled advisory for
   Trusted agents, on the table and in the effective line.
4. **The tools stay listed for an agent with no links** (so a refused call
   can say why). Hide them instead, as for off and quarantine?
5. **Quarantining from the page drops the agent's links out and
   message/pass on links in, and revokes its shares and sessions.** Release
   gives none back. Keep, or keep the links (inert while quarantined)?
6. **The orders guard now asks about `agentvoice chats share` too**, at
   every level. The overlay's own "Share chat with" is unaffected (it runs
   from the shell, not through the hook); a Trusted agent asked to share a
   chat gets a card.
7. **A message or result judged at delivery and refused is dropped**, not
   kept for later (the inbox is taken as it is read). Keep instead?
8. **Eight agents make a 56-row table.** Group by agent, or leave it to the
   map (M9)?
9. **"Changed outside Settings" lives in the overlay's memory**: a change
   made while the shell was not running is not flagged.
10. **Pass requests are still files** the daemon cannot attribute. The
    orders guard catches the plain forms (pass 1); a socket with an
    ancestry check, as M7 did for cards, would be stronger.
11. **The live quarantine check** waits for the user (it changes saved
    chats for good). See Not verified.
12. **Codex credits**: 34.41 this phase; **55.49 left for M9–M29**, about
    2.6 a phase: less than one low-effort pass each. The plan wants two
    passes on Tier A phases (M10, M17, M20, M22, M27 remain). The runner
    needs a decision: one pass per phase, and only the Tier A ones?
13. **Carried, still open**: M7's 2–7; M6's 1, 3, 4; M5's 1, 4–6; M4's
    4–13; the Voice library trash icon (M25); M0's small test and bench
    fixes; agy's `carries_session_across`; the runner's sandbox test
    command (`codex sandbox linux -- true` still panics).

## Codex credits used

**34.41**. The balance went from 89.91 at the end of M7 to 55.49, read from
the session logs' `rate_limits.credits.balance`. It was still 89.91 at
this phase's first call. The live checks used no Codex agent.
- **Pass 1: 24.75** (89.91 → 65.15). `gpt-6.2-astra`, medium effort,
  sub-agents disabled, the read-only copy, the daemon diff plus
  `Settings.qml` and `ui/SendSheet.qml` (1,686 lines), at most 8 findings.
  93,524 tokens.
- **Pass 2: 9.66** (65.15 → 55.49). Low effort, otherwise the same, on pass
  1's daemon fix diff (407 lines), at most 5 findings. 36,694 tokens.

**55.49 left** for M9–M29.

## Live checklist: what was said, what happened

All typed (`agentvoice type main` on stdin), synthetic text. Nothing was
said into the microphone. Theo (Claude Code, Trusted, collaboration
`announce` by default) and Sora (Claude Code, Ask). Each check was read
from `journalctl --user -u agentvoice -o json`.
- Before the first deploy: state `listening`, no task, no open mic,
  unlocked; `shell.json` copied.
- After each install: the service active, `agentvoice locked` "no",
  `shell.json` byte-identical to the copy.
- **A. A link that allows it runs.** `crewLinks` = Theo → Sora,
  `["delegate"]`. Theo was asked to delegate "say exactly the words crew
  check alpha seven". Journal: `prompt for “Theo”: … roster 1` (the roster
  filtered to the one agent he is linked to),
  `[mcp__agentvoice-crew__delegate]`, `delegate a7a1cbff9d2cd439: Theo →
  Sora (agent)`, `delegate a7a1cbff9d2cd439: Sora has the floor
  (replayed)`, `agent 5.2s`. `agentvoice tasks`: completed. History: "Sora:
  crew check alpha seven".
- **B. The link deleted: refused, and the reason said.** `crewLinks` = [].
  Journal: `roster 0`, then `delegate 20684d46d03600ec refused (no-link)`.
  Theo said: "The tool refused because the Crew map no longer has a link
  from me to Sora that allows giving Sora a task, so nothing was sent."
- **D. The list broken by hand: everything refused.** `crewLinks` =
  `"broken by hand"`.
  - On a973171: nothing was sent, but every agent's crew tools were
    withdrawn ("tools for “Theo”: desktop · omarchy · plugins …" for all
    three), and Theo said "the ask agent tool has been taken away from me
    … there's no refusal message to pass on". A bug (Found along the way),
    fixed in a64219f and deployed.
  - On a64219f: `[mcp__agentvoice-crew__ask_agent]`, `crew links: unreadable
    (crewLinks is not a list); every agent call is refused`, `ask
    09fd7e6c5f8a5577 refused (crew-unreadable)`; the state file's HUD line
    read "Crew links can't be read: agents can't reach each other". Theo
    said: "The tool refused because the crew links setting is broken, so no
    agent can contact another until the links are fixed on the Crew map."
- **C. Quarantine (Theo's ask runs, his pass is refused): not run**, see
  Not verified.
- `shell.json` put back from the copy: byte-identical. The journal since
  the first live turn: **0** lines holding any of the typed words.
- No shell restart. No other setting changed.
