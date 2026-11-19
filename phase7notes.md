# Phase 7 (plan.md Phase G): editor, browser, second-mouse spike

Written 2026-11-18. Branch `phase-g`, cut from `phase-f` at b571a5a, so it
carries Phases A to F too. Commit 9e1918f, pushed to `fork/phase-g` only.
Not installed, not merged. This is the last phase in plan.md.

`./bin/agentvoice-check`: green, 1716 tests (was 1678). install.sh did
not change, so the box was not rerun.

## Fixed from Phase 6: Hyprland's Lua dispatch

Hyprland 0.56 with Omarchy 4.5's Lua config reads `hyprctl dispatch X` as
Lua. `closewindow address:0x…` is therefore a syntax error there, which
broke focus, move, close and switch-workspace in the desktop tools, and the
skill's scratchpad lines. The Phase 6 tests missed it because the stub
`hyprctl` answered "ok" to anything.

- The tools now send the Lua form first (`hl.dsp.focus`,
  `hl.dsp.window.close`, `hl.dsp.window.move`, `hl.dsp.focus({workspace})`)
  and fall back to the old form, as Omarchy's own scripts do.
- The skill writes the Lua spelling when `~/.config/hypr/hyprland.lua`
  exists. Installing rebuilds the skill: the stamp includes the
  generator's hash, so the daemon rebuilds it too.
- Checked against the real compositor: focus, close, and the scratchpad
  toggled and back.

## 12d. VS Code

- New desktop tools:
  - **`open_in_editor`** opens a file, at a line and column, in Omarchy's
    default editor. VS Code-style editors get `--goto file:line:col`,
    terminal editors `+line`, Zed `file:line`, anything else
    `omarchy-launch-editor`.
  - **`show_changes`** opens VS Code diffs of what changed in a git folder
    since the last commit: one file, or up to 5. The HEAD copies go into
    `$XDG_RUNTIME_DIR/agentvoice/diffs` (0700, files 0600, tmpfs). With
    another editor it returns the `git diff --stat` instead.
- Both are asked about below Trusted, like the other changes.
- Both ran on the real desktop with your default editor `code`.
- **`--ide` is not offered.** VS Code was opened three times on a scratch
  folder, and the Claude Code extension (auto-updated to 2.1.327 on the
  first start) never activated: no lock file in `~/.claude/ide`, so there
  was nothing for `claude --ide` to connect to. To retry, restart VS Code
  yourself, open a project, and check for a `~/.claude/ide/*.lock`. If one
  appears, `claude -p --ide` in that folder is the turn to try.

## 12d. Browser

- **`browserTools` setting, off by default**, on Agents → On the desktop.
  It replaces the uncommitted `--chrome` line, which is now committed as
  `--chrome` when on and `--no-chrome` when off. **Your installed build had
  it always on. After installing this one, turn on Browser to keep it.**
- **Asked at every level**, past Trusted and past "allow all in this chat"
  (`permission_hook.browser_consequence`):
  - a click, key, typed text or form fill whose own `action_summary` says
    it sends, buys, posts, orders, pays, books, deletes, confirms, signs up,
    uploads, saves and similar (the word list leans wide: a false match
    costs a question);
  - any such action that gives no summary;
  - `javascript_tool` and `file_upload`, always;
  - a `browser_batch` holding any of these.
- Reading pages, find, screenshots, scrolling and navigating follow the
  level as before.
- **Said out loud:** the request is marked `announce`. While the turn's
  stream is quiet (the hook is waiting), the daemon says "Nova is asking
  first: places the order. Answer on screen." once, on that agent's own
  thread and floor. Only the summary is spoken, never what is being typed.
- A trusted agent with the browser on gets a hook on the browser's tools
  only (`mcp__claude-in-chrome__.*`), so nothing else pays for a hook
  process.
- **Not tried live:** Claude in Chrome wasn't connected (Chrome wasn't
  running). The decisions are tested: 13 consequential, 10 ordinary, at
  Trusted and with a grant.

## 12c. Second mouse (spike, decision made)

- **(c) Hyprland has one pointer.** Its virtual-pointer protocol, and
  ydotool through uinput, both move your cursor. Nothing supports a second
  seat.
- **(a) Acting without the pointer works.** Window commands, the editor
  and Claude in Chrome all act without moving it: `hyprctl cursorpos` read
  the same before and after.
- **Ghost cursor prototype:** `bench/spike/ghost/shell.qml`, an
  overlay-layer surface with an empty input region and no keyboard focus.
  It drew a labelled ring over the real desktop, and the cursor did not
  move. Click-through was not measured; it needs a pointer event.
- **Decision: (a).** The agent acts through commands, a ghost cursor shows
  where it acts, and ydotool is never used for the agent. The overlay is
  the next thing to build. The browser's click coordinates already reach
  the hook, and a window's centre gives a position for desktop tools.

## Live checklist

1. Install (`install.sh --yes`) and restart the shell (QML changed).
2. Agents → On the desktop → turn **Browser** on (and Desktop tools, if
   off). Start Chrome with the Claude in Chrome extension.
3. "Theo, open the README in the editor at line 100." VS Code opens there
   (Theo is trusted, so no card).
4. Edit a file in a git folder, then "Theo, show me what changed in
   <folder>". A VS Code diff opens.
5. "Theo, go to example.com and tell me the heading." No card.
6. "Theo, put a kettle in the cart on <a shop> and check out." Adding to the
   cart isn't on the list and goes through. The checkout or place-order
   click should be asked about, out loud and on screen, even though Theo is
   trusted. Deny it.
7. "Theo, close the Chrome window" (desktop tools, Lua dispatch).
