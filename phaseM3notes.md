# Phase M3: Popup and readout (bugs B, D; items 2, 3, 20's readout)

Written 2026-11-21, unattended (started by the runner script). Branch
`phase-m3`, cut from `phase-m2` at a8ef9f4. Result commit: the notes commit
on top of d4c209f, pushed to `fork/phase-m3` only; `dev` fast-forwarded to
it and pushed to `fork`. Model: Claude Opus 5.5, high.

Commits: 17af638 (the phase), f52d9fc (Codex pass 1 fixes), d4c209f (Codex
pass 2 fixes), then these notes.

Deployed: **yes**, d4c209f through `bin/agentvoice-deploy --install` (its
strict check green in a fresh worktree), daemon idle (state `listening`,
every agent idle, open mic off). It replaced a2deeb6 (the way back:
`bin/agentvoice-deploy --install a2deeb6`). Installed: **yes**: build 0.2.0
(d4c209f) replaced 0.2.0 (a2deeb6); the service is active. **Shell restart
needed** for the QML (`Panel.qml`, `Hud.qml`, `Settings.qml`,
`pages/DisplayPage.qml`, `ui/ReadoutLines.qml`): not run, stop point 1.

`./bin/agentvoice-check`: green, **2973 tests** (was 2918; +55), 14 of 14
static checks, "the check wrote nothing in the tree: ok". Box: not run
(`install.sh` did not change).

## What was built

**D / item 2: no global permission section in the popup.** The "What
Claude Code may do" picker, `setMainLevel`, `trustPending` and the
two-click "Trust it" strip are gone from `Panel.qml`. `permissions` has one
home, the Agents page (`setLevel`), held by
`test_the_popup_no_longer_writes_a_permission_level` and by
`OUTSIDE_WRITERS`, which now allows the popup to write `voice` only. What is
in force (folder, posture, "does not remember", "instead of …") moved into
the main agent's chip tooltip, so it is still one hover away. Kept: chips,
mic, STOP, typing, quick toggles, voice, settings, live state. The popup
never drew permission *prompts* (those are the overlay's), so there were
none to keep.

**B / item 3: a readout that does not bounce.** New setting `hudSize`:
- **Locked** (default): the HUD and the popup's LAST HEARD draw
  `ui/ReadoutLines.qml`, two slots of fixed height (two text lines each):
  the agent's answer, dim, with an accent bar, and what is being said now,
  bright, with a bar in the state colour. The heights come from the font
  alone. Long text shows its newest words, cut at a sentence or word
  boundary with "…" in front, elided as a fallback, PlainText. In the popup
  the LAST HEARD section is always there (placeholders "No answer yet" /
  "Nothing heard yet"). The STOP button stays in place, dimmed and inert,
  reading "STOP · nothing running" between turns. The agent chips are as
  wide as their longest state, measured bold. The HUD has one width (from
  the text size) and one height; the collaboration line moves into its
  header, elided.
- **Dynamic**: today's grow and shrink, but LAST HEARD keeps its slot when
  empty.
- "more" still unfolds LAST HEARD in either mode, on request.

**The kept answer (`hudKeepReply`, item 20).** New `daemon/readout.py`,
called from `Daemon._compose` for every unlocked payload:
- the last answer is published as `last_reply` while the turn under way has
  none. A capture never carries an answer: a follow-up's old reply moves to
  `last_reply`. Whether it is drawn is the screen's setting;
- both lines clear **together** on a lock, on a switch to another agent, on
  a chat switch from the conversation view, when a rebuild ends a chat, and
  after `KEEP_S` = 600 s with nothing new (polled above the listening gate).
  They stay cleared: until new words arrive both fields go out as "". Every
  clear bumps a generation, and the run loop then drops the text from its
  own copy of the turn. The agents' cached turns (`Persona.last`) are
  marked and not merged into idle payloads again. They are still kept,
  because collaboration builds a pass's brief from them;
- the popup and the overlay also drop their own copies of both texts when a
  `locked` payload arrives (a field not sent keeps its value).

**Preview.** `agentvoice hud-preview` and a **Preview** button on the
Display page. The button says why when it cannot work: no engine, service
stopped, readout off, screen locked, or a turn under way. It publishes four
seconds of sample text as a real `speaking` payload with `preview: true`.
It shows only over `listening`/`off`, never over a lock, and is never
mirrored to Omarchy's Agents panel. The sample is never kept. The HUD
closes at its end without the linger. Push-to-talk over it listens rather
than interrupts, and STOP is not offered.

**New settings**, three places each (manifest schema + defaults,
`runtime.DEFAULTS`, one control on `pages/DisplayPage.qml`). There are no
TOML aliases: without Omarchy there is no screen to draw them.

| Key | Values (default) | Unreadable | Control |
|---|---|---|---|
| `hudSize` | locked / dynamic (locked) | locked (anything but "dynamic") | Size (live with the readout off: it shapes the popup too) |
| `hudKeepReply` | bool (true) | true (anything but false) | Keep the last answer on screen while I talk (live, same reason) |
| `hudPosition` | top / bottom (top) | top | Position (dimmed with the readout off) |
| `hudTextSize` | small / medium / large (medium) | medium (strict, in the HUD and the page) | Text size (dimmed with the readout off) |

**Tests.** New `tests/test_readout.py` (47: the pure object on a fake
clock, the daemon's real state file, the CLI run with systemd stubbed);
additions to `test_hud.py` (three places per key, unreadable fallbacks,
locked vs dynamic, fixed height, popup slot and STOP, lock clears the
popup's copy); `test_settings_pages.py` (popup no longer writes
`permissions`); `test_history.py` and `test_states.py` adjusted to the
locked mode.

**Mutations** (each reintroduced, each turned a test red, all restored):
12 on the phase, 14 on pass 1's fixes, 8 of 9 on pass 2's. The survivor,
"keep the `gone` set after new words", is equivalent: the set is consulted
only while blanking, which new words end.

**Preview target.** `bench/preview/targets/readout.qml` rewrites the state
file through one turn and logs the popup's and the HUD's size after each
state (FINDINGS §42). `preview.sh`'s stub logs `hud-preview` like the other
commands, so a preview's Preview button never reaches a real daemon.

**Docs.** README "Reading it back", CODEBASE (layout, state fields,
`readout.py`, `ReadoutLines`), FINDINGS §42.

## Shared files touched, and where

- `daemon/wake_listen.py` (big shared): `import readout`; `__init__`
  (`self.readout` on the state file's lock, `_stale_lasts`);
  `carry_session` (forget + clear on a dropped chat); new `readout_for`,
  `forget_readout`, `_readout_cleared`, `expire_readout`,
  `apply_readout_command` after `apply_lock_command`; `_mirror_panel`
  (skips previews); `_recompose` (snapshot under the state lock);
  `_compose` (readout compose before the muted flag, `lock()` and the extra
  locked-payload filter); `_compose_line` (stale cached turns not merged);
  `continue_chat`, `new_chat`, `apply_chat_command` (forget); the run loop
  (generation check at the top, `apply_readout_command`, `expire_readout()`
  in the 2 s lock poll).
- `Panel.qml` (big shared): permission picker removed; `mainPosture`;
  readout properties and parse (`lastKept`, `vPreview`, clear on lock);
  `vTurnRunning` excludes previews; the HUD's new inputs; STOP; chips; LAST
  HEARD rewritten.
- `Settings.qml` (big shared): `hudPreviewBlocked`, `previewHud`, `vPreview`
  in `turnRunning`, both texts cleared on lock.
- `Hud.qml`, `ui/ReadoutLines.qml` (new), `ui/qmldir`,
  `pages/DisplayPage.qml`, `manifest.json`, `daemon/runtime.py`,
  `daemon/readout.py` (new), `bin/agentvoice` (`hud-preview`; `talk` reads
  one snapshot), `bench/preview/preview.sh` (stub).

## Measured

FINDINGS §42: popup content height through idle → capture → partial →
thinking → speaking → follow-up, logical px, the user's three agents:

- **before (M2): 428–557, a 129 px range**;
- **locked: 481 in every state, 0 px**;
- dynamic: 430–493.

HUD: before, 233×34 → 467×96. Locked: 367×98 throughout. Tests 2918 →
2973. The check's test run is ~2 min 31 s, as before.

## Different from the plan, and why

- **The STOP button and the chips also changed.** The plan names the last
  heard line. The measurements showed STOP appearing for thinking and
  speaking was half of the bounce, and a chip going "idle" → "transcribing"
  can rewrap the row. Locked mode fixes both. Dynamic leaves STOP as it was.
- **`hudTextSize` and `hudPosition` act on the HUD only.** The popup stays
  under its bar icon at the bar's own size (the Astra plan said the same).
- **`hudPosition` replaces "follow the bar".** The HUD used to sit at
  whichever edge the bar was on. Now it sits at the edge the setting names,
  still clear of a bar there. See open issue 3.
- **Expiry is a fixed 10 minutes** (`readout.KEEP_S`), not a setting. The
  plan says "on expiry" without a number.
- **The overlay's own cache** of the exchange was cleared on lock too (a
  pre-existing path Codex found). No other overlay code changed.
- **Codex ran on the read-only copy both times.** `codex sandbox linux --
  true` still panics ("Failed to execvp linux"), which is not a bwrap
  error, so neither branch of the runner's test applies cleanly. The copy
  is the safe one. HEAD and status in the clone were unchanged after both
  passes, and both copies were deleted.

## Codex review

- **Pass 1** (10 findings + 6 small; all fixed in f52d9fc):
  - pre-lock words could return after a new turn (the run loop's stale copy
    of the turn);
  - a SIGUSR1 deadlock on the readout's lock;
  - the overlay kept the exchange through a lock (pre-existing);
  - expiry never ran while muted or lent;
  - the preview's `speaking` made push-to-talk interrupt and lit STOP;
  - the preview timer's recompose raced the microphone;
  - the sample survived a muted preview's end, and lingered;
  - a rebuild re-kept the old reply;
  - an owner change left the previous agent's words;
  - `hudKeepReply` off was ignored in a follow-up;
  - small: the close handler reached an id it cannot see, STOP was inert
    without saying why, chip width with bold text, two Display controls
    dimmed although they shape the popup, a loose enum read.
- **Pass 2** (7 findings; all fixed in d4c209f):
  - a cross-thread deadlock (two locks in opposite orders): now one lock;
  - the `gone` filter was bounded and swallowed repeated wording: the
    caches are now invalidated at their source instead;
  - an off-screen agent's rebuild;
  - main agent vs nobody, both "";
  - the CLI read the state twice;
  - the preview restore was sent once;
  - chip width still depended on state.
- **Pass 2's fixes were not re-reviewed** (credits, below).

## Found along the way

- **The overlay kept the last exchange through a lock** (Settings.qml
  merges the state file like the popup). It was never visible, because the
  overlay closes on lock, but a summon over a lock would have shown it.
  Fixed.
- **Before M3, the run loop's copy of a voice turn could be republished over
  a typed exchange** with each level update. That is a pre-existing UX
  quirk, not a leak. M3 drops that copy's text only after a readout clear.
  Otherwise LAST HEARD can still swap a typed exchange back to the previous
  voice one.
- **The old popup's close handler** would also have failed to reach an id
  inside the loaded content. That handler is new in M3 and was fixed in
  pass 1.
- `bench/preview/preview.sh --size` still crops the middle of the screen
  (noted in M2). Screenshots of the popup were cropped with `magick`.

## Not verified

- **The QML in the real shell** (needs `omarchy-restart-shell`; stop point
  1): the popup without the permission section, locked LAST HEARD, the
  inert STOP, chip widths, the HUD's locked look, the Display page controls
  and the **Preview button clicked for real**. All were seen only in
  `preview.sh`: dark at 1920×1080, plus the Display page in flexoki-light.
- **`hudPosition` bottom and `hudTextSize` small/large were never drawn.**
  The readout target ran top and medium only.
- **A real open-mic chat watched for bounce** (stop 1, as the plan says).
- **`agentvoice lock` mid-partial** needs the microphone (somebody
  speaking), so it was not run. Run instead on the live daemon after a typed
  turn: lock → payload `locked` with no text fields; preview refused ("the
  screen is locked"); unlock → `transcript` and `reply` both "" (Sora's "OK"
  did not come back). The real lock screen was not used.
- **The run loop's generation check** is held by a source test and a
  mutation, not driven through `tests/frame_loop.py`.
- Voice: nothing said by voice in this phase.

## Going back

`bin/agentvoice-deploy --install a2deeb6` from the clone, then
`omarchy-restart-shell` for the QML. No stored data changes. The four new
keys sit unused in shell.json: an older build ignores them, shows the
popup's permission section again, the bouncing LAST HEARD, and the HUD
following the bar, and has no `hud-preview`.

## Open issues, for the next phase

1. **No section 11 question applied to M3**; none was taken by default.
2. **Codex credits: this phase overspent badly** (below). The runner must
   pass `-c model_reasoning_effort='"medium"' --disable multi_agent` (and
   `--disable multi_agent_v2`) to every review. `~/.codex/config.toml` sets
   `model_reasoning_effort = "ultra"`, and at that effort pass 1 spawned
   three sub-agents of its own.
3. **`hudPosition` default `top`**: the plan calls top "today's place",
   which holds for a top bar (this machine). With a bottom bar the HUD used
   to sit at the bottom and now moves to the top until the setting is
   changed. Question for the user: keep top, or add a third value, "beside
   the bar", as the default?
4. **Expiry of 10 minutes** is a judgement, not a measurement. Should it be
   a setting, or tied to `openMicIdleMin`?
5. **Locked-mode tail**: the cut is estimated from the font's average glyph
   width (×0.85). Text with many wide glyphs can still elide the very last
   words. Rendered-width fitting was not done.
6. **Right after a clear**, a new turn whose question *and* answer exactly
   match the cleared ones stays blank until different words arrive.
7. **Pass 2's fixes were not reviewed by Codex.**
8. **Carried from M1/M2, still open**: the Voice library's trash icon (→
   M25). M0's small test and bench fixes (`test_tools_skills`' TMPDIR
   length, `test_permission_hook`'s cwd and live-folder cleanup,
   `turn_latency.py --build` with `-dirty`). agy's `carries_session_across`.
9. The runner's sandbox test command still does not exist in codex-cli
   0.171.0 (open issue 5 of M1).

## Codex credits used

**177.02** (398.22 at the end of M2 → 221.20, read from the session logs'
`rate_limits.credits.balance`):
- pass 1: **160.63** (398.22 → 237.59). `gpt-6.2-astra` at the config's
  default **ultra** effort, which this run did not override. Codex spawned
  three sub-agents (four session logs, all in the read-only copy). The main
  session alone logged 2.96 M input tokens (2.84 M cached);
- 7.27 unexplained between the passes (237.59 → 230.32, no Codex session
  logged in between; probably pass 1's sub-agents settling late);
- pass 2: **9.12** (230.32 → 221.20), medium effort, sub-agents disabled,
  41,646 tokens.

**221.20 left** for M4–M29, about 8.5 per phase. That is enough for two
medium passes per phase only if every pass runs with the flags in open
issue 2.

## Live checklist: what was said, what happened

- `agentvoice hud-preview` on the new daemon: the state was `speaking`,
  `preview: true` with the sample reply at 0.3 s and 2.3 s, and `listening`
  at 6.9 s. The journal said "(readout preview for 4s)". The running shell
  still has M2's QML, so the old HUD drew it.
- Typed to Sora ("Reply with the single word OK."): answered in 4.0 s
  (first token 1240 ms). Then `agentvoice lock`: the payload was `locked`
  with none of transcript/reply/last_reply/preview. `agentvoice hud-preview`
  was refused, exit 1. `agentvoice unlock`: `listening`, transcript "",
  reply "", who `sora`. `agentvoice locked`: "no".
- Nothing said by voice; no shell restart; no settings changed.
