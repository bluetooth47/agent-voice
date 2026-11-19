# Phase 8: Spec, baseline and compatibility

Written 2026-11-19. Branch `phase-8`, cut from `dev` at 2eeb919, one
commit, pushed to `fork/phase-8` only (the hash is in `git log`; a note
cannot name the commit it is part of). Installed: no (no daemon, QML or
installer file changed). Tested on: i7-1185G7, the installed `dev` build
2eeb919, `claude` 2.1.328, `codex-cli` 0.170.0, Whisper `base.en`, Shokz
OpenRun Pro 2 headset.

`./bin/agentvoice-check`: green, 1819 tests (was 1763). The bare-runner run
(`AGENTVOICE_STRICT=1`) is green too; its 9 skips are the existing numeric
tests, none of this phase's. Box: not run (`install.sh` did not change).

The first phase of `merged-plan.md` (agent folders, the communal folder,
collaboration). No product code, as the plan says. Codex drafted the backend
matrix from source and reviewed the phase; what its review changed is below.

## What was built

- **The open questions are settled.** The user's answers are in
  `merged-plan.md` section 1 ("Answers to the open questions") and marked in
  `merge-decisions.md` section 3. All eight proposals stand except
  **question 3: a pass or delegation adds the target to the chat**, so it is
  replayed the transcript (up to `REPLAY_MAX`), not only the brief. The plan
  was changed to match in Phase 15 ("Passing a conversation", "Shared
  chats"), Phase 16 (the `ask`, `announce` and `allow` levels), section
  3.7's `shared_with`, the risk table, UX task 5 and the sources list. Every
  entry point says the chat goes with it before the target is added to
  `shared_with` or anything is sent, and an endpoint target is named by
  host. Question 1 ("announce by default, with ask and silent as options")
  is the four-level setting the plan already had.
- **One plan decision the user has not answered:** at `allow`, a delegation
  or pass to an **endpoint** is still announced naming the host, because it
  sends the transcript off this machine. Marked as such in Phase 16.
- **Section 2 corrected** from a second read of the code (by Codex, each
  item checked against the file): the browser hook and Codex `--guard` are
  both conditional; the main agent's MCP server gets no id argument; the
  hook's order at "edits"; `record()` keeps an old `session_id`; the wake
  build check is for extra agents only; what `install.sh` copies; what the
  one-page test counts.
- **Acceptance checks for Phases 9 to 16** (`merged-plan.md`, after
  Phase 8): 41 checks, each with what it must prove and the evidence that
  counts, and two fixed latency instruments: **S** (controlled, the gate)
  and **J** (journal, real use), with how the gate is judged given the
  measured noise.
- **Baselines** in `bench/FINDINGS.md` §33 and `bench/baselines/phase8.json`.
- **The compatibility matrix**, one row per backend, in §33, with which
  backends can start collaboration and which can only receive it.
- **Three bench scripts**, each printing timings or sizes only:
  - `bench/turn_latency.py` reads the journal's `heard → spoke` lines and
    attributes each to an agent, accepting only names the daemon announced;
  - `bench/preamble_size.py` measures `Adapter.preamble()` per backend and
    per configured agent, and the Claude plugin's skill sizes, never
    printing the text;
  - `bench/start_bench.py` times a turn through the real adapter, cold and
    warm, built as one of the configured agents (`--agent`) at its own
    permission level.
- **Fixtures** in `tests/fixtures/agents/`, eleven files, all synthetic:
  main with and without instructions; the three-agent shape of the real
  machine (an Ask Claude agent with short instructions and a Trusted Codex
  agent whose id differs from its name and has no `enabled` key); a disabled
  agent; an entry with no id; hand-mangled ids (`../../etc`, `Upper Case!`,
  `main`, empty); a duplicate id; empty and whitespace instructions;
  instructions at exactly 2000 characters and one over; unicode with CRLF, a
  tab and a control character; saved chats with `agent_id: ""` and with an
  extra agent's id. Each has an `expect` block: the folders a migration must
  make and what each must hold, with exact text where cleaning matters.
- **`tests/test_agent_fixtures.py`** (47 tests) holds every `expect` block to
  today's `runtime.Config`, re-writes the saved chats through
  `ChatStore.record` and compares, and checks no fixture contains the real
  agents' names or a home path. **`tests/test_turn_latency.py`** (9 tests)
  replays synthetic journal lines through the parser: a transcript, or a
  reply shaped like an agent announcement, is never echoed as a name;
  attribution; `showed` excluded; a discarded wake not carried forward; a
  malformed number neither counted nor a crash.
- The plan and decisions are now in the repo (`merged-plan.md`,
  `merge-decisions.md`) so later phases branch with them; the copies in
  `~/Documents/agent-reconfiguration-plan/plans/` were updated to match.

## Shared files touched, and where

- `bench/FINDINGS.md`: §33 appended. Nothing earlier changed.
- No daemon, QML, manifest or installer file.

## Measured (numbers, against the baseline)

This phase *is* the baseline. Send to first text, 20 runs, each agent at its
own level:

| | median | p95 |
|---|---|---|
| main (Opus, trusted) warm | 2.21s | 3.37s |
| main cold | 3.36s | 4.68s |
| sora (Haiku, ask) warm | 0.73s | 1.08s |
| sora cold | 1.76s | 2.19s |
| jarvis-ajc (Codex, trusted) fresh | 3.33s | 4.22s |
| jarvis-ajc resume | 3.37s | 4.13s |

Noise of a 20-run median against itself: ±60ms Sora, ±480ms Opus, ±355ms
Codex. End of speech to first word, journal: Theo 5.9s / 11.5s (30 turns on
2eeb919), Hazel 11.6s / 31.0s (16 turns), Sora 5.2s / 17.6s (26 turns on
87ce8e7). Preamble: 856 characters for Claude and endpoints, 957 for Sora,
6,837 for every other CLI (5,979 of it the Omarchy skill's short form).

## Different from the plan, and why

- **The latency baseline is two instruments, not 20 voice turns each.** The
  plan asked for 20 voice turns per agent by voice. Those need someone
  talking, and the journal's real turns vary too much (a 30s tool run next
  to a one-liner) to judge 150ms. The gate is judged on `start_bench.py`
  (S), which times the part a preamble can slow with each agent's real
  configuration; the journal (J) is the real-use check.
- **The 150ms median gate is judged on Sora only.** The measured noise
  (above) means no feasible number of runs resolves 150ms on Opus or Codex.
  The plan now runs old and new builds interleaved on Sora for the median,
  holds the main agent and Hazel to their noise range, and applies the p95
  gate to all three.
- **Wake to first word is derived**, not printed by the daemon, and includes
  the time spent asking.
- **Sora's journal baseline is from `87ce8e7`**: no turns on 2eeb919 were
  attributed to her.
- The matrix is mostly "from source, not run": only cells already shown by
  FINDINGS, a phase note or a recorded turn are marked as a turn. No CLI was
  run just to fill a cell.
- Phase 10's "one folder per `voiceAgents` entry" became "one folder per
  stable id `Config` accepts", which is what the `duplicate-id` fixture
  showed it has to mean.

## Found along the way (bugs, surprises)

- **A Codex main agent loses its session on every idle refresh**
  (`wake_listen.py:2070`: `Codex` and `Gemini` never set `ask_permission`,
  so the keep check is always false and `session_id` is reset). Not hit here
  because Theo is Claude and Hazel is an extra agent, whose rebuild compares
  whole spec dicts. Not fixed: Phase 8 writes no product code.
- **The Omarchy skill's short form is 5,979 characters in every non-Claude
  CLI preamble**, larger than any budget the plan sets.
- **Codex below Trusted with desktop tools off has no `--guard`**, because
  the guard comes with the desktop server. Recorded in section 2 and as
  check A14-3.
- **Codex's review of this phase** found, and this phase fixed:
  - `start_bench.py` forced every agent to Trusted (`ask_permission=False`),
    so Sora ran without her hook and a Codex agent below Trusted would have
    run with `--approve-for-me`. It now builds each agent at its own level
    with its id, rejects an endpoint main agent, counts failed and
    errored turns instead of dropping them, never resumes a failed turn,
    keeps a warm run that fell back to cold out of the warm numbers, and
    lets SIGTERM run its cleanup. Sora was rerun; Theo and Hazel are Trusted,
    so their runs stand.
  - `turn_latency.py` would print any word after "for" in a logged
    transcript as an agent name, counted displayed-only replies as spoken,
    carried a discarded wake into a later turn, and attributed by the
    capture only. It now matches whole status lines, accepts only announced
    names, uses the follow-up line after a reply, and fails loudly when
    `journalctl` does.
  - `preamble_size.py` reported a Codex main agent as Claude and crashed on
    an endpoint or `antigravity-cli` extra agent.
  - The fixture test's saved-chat check could pass on an empty mapping and
    its instruction checks only compared lengths; the fixtures' chat
    timestamps did not match what `ChatStore.record` writes.
  - The plan's Phase 16 levels still described a pass without the
    transcript, and Phase 11 gated on a different measurement from A11-4.
- **Codex's second review**, of those fixes, found and this phase fixed:
  user-started and agent-started passes now have separate notice rules
  (user-started always says the chat goes with it, naming an endpoint's
  host; agent-started follows `collaboration`, where `allow` is silent by the
  user's choice); A15-2 covers the CLI; Phase 15's latency limit matches
  A15-6; the p95 gate is judged on Sora too; **S must assemble the new
  preamble the way the daemon does**, with a test, or Phase 11's gate would
  measure the old one; the parser learns names only in the start-up block
  and no longer crashes on a malformed number; `start_bench.py` counts
  fallbacks as attempts and refuses a main agent with no program.
- **Accepted, not fixed** (all in a dev-only bench script, all written down
  where they apply): two agents answering at once on one adapter can be
  confused in the journal, which has no turn id; open mic and push-to-talk
  turns can inherit the last attribution; a nameless solo wake is assumed to
  be Theo (this machine); with `logSpeech` on, a spoken line shaped exactly
  like a latency line would be counted; a Ctrl-C mid Codex turn can leave
  that `codex exec` running; a Codex turn that prints text then exits
  non-zero without an error event is counted.
- `pkill -f bench/start_bench.py` matched the shell running it and killed
  one benchmark run; it was rerun whole.

## Not verified (what was skipped, and why)

- 20 voice turns per agent by voice, under controlled prompts: needs the
  user talking.
- Whether Codex, Gemini, Antigravity or Copilot load `SKILL.md` natively:
  needs a real turn each; Codex's is check A13-3.
- Every "from source, not run" cell of the matrix, and the whole cancel
  column.
- Token counts are characters / 4, not a tokenizer.
- The derived wake-to-first-word figure against a real stopwatch.
- The five-run smoke figures in the JSON keep summaries only.

## Going back (what an older build sees after this phase)

Nothing changes for an older build: no setting, data-folder file or
installed file was written. The bench scripts read the journal and the
settings. `start_bench.py` runs real CLI turns in a temporary folder that is
removed afterwards, and for an agent with standing instructions the Claude
adapter writes its usual private prompt file under `$XDG_RUNTIME_DIR`, as a
daemon turn does.

## Open issues, for the next phase

- Fix the Codex main-agent session reset, with a refresh test, before or in
  Phase 9.
- Phase 11 decides how the Omarchy skill text is budgeted.
- Answer, or accept, the endpoint-at-`allow` exception in Phase 16.
- Phase 9 starts from the fixtures and checks A9-1 to A9-6.

## Live checklist: what was said, what happened

None: Phase 8 has no live checklist and nothing was installed. The
benchmarks ran about 200 short real CLI turns in a scratch folder (prompt
"Reply with the single word OK"), not voice turns.
