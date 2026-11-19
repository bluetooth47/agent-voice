# Phase 6 (plan.md Phase F): endpoints, desktop tools, Omarchy skill

Written 2026-11-18. Branch `phase-f`, cut from `phase-e` at 1c75562, so it
carries Phases A to E too. Commit b571a5a, pushed to `fork/phase-f` only.
Not installed, not merged.

`./bin/agentvoice-check`: green, 1678 tests (was 1557). Installer box 9/9.

## 7b. Local models and API URLs

- **Endpoint per agent.** An extra agent's program can be **Endpoint**, with
  its own `endpointUrl`, `endpointModel`, `endpointIsAgent`,
  `endpointTimeoutS` and `endpointHistoryTurns` in its `voiceAgents` entry.
  The model, effort, permission and folder rows hide for it, because Agent
  Voice offers an endpoint no tools.
- **New main settings:** `endpointTimeoutS` (0 = the old default, 120s or
  300s for an agent, otherwise 10–600) and `endpointHistoryTurns` (8, 0–50).
  Both are in all three places. Changing either rebuilds the main endpoint.
- **One editor** (`ui/EndpointEditor.qml`) on the main card and on every
  endpoint card:
  - **Presets:** Ollama, OpenAI, Groq and xAI. These are only the four that
    have answered a real turn (FINDINGS §14). A test fails if a preset is
    added without a FINDINGS row. LM Studio, llama.cpp, vLLM, OpenRouter
    and Hermes work by typing the address.
  - **Forgiving address:** `endpoints.clean_url`, shown as "Will use …".
    It adds the scheme (http for local, https for public) and `/v1`, cuts a
    pasted `/chat/completions`, `/models` or trailing slash, and refuses a
    key typed into the URL. The daemon applies the same function, so a URL
    from `omarchy bar set` gets it too.
  - **List models:** `/v1/models`, falling back to Ollama's `/api/tags`.
  - **Test connection:** one 16-token streamed request. It reports the
    first word's time and whether a key was sent, or a plain error: "Ollama
    isn't running", "wrong port?", "it wants an API key", "model not pulled:
    run ollama pull X", "blocked by Cloudflare".
  - **Keys:** `~/.config/agentvoice/endpoint-keys.json`, 0600, keyed by host.
    The key reaches the CLI on stdin, never argv. It is shown masked
    (`sk-…1234`) and can be cleared. In `paths.endpoint_key` the keyring for
    that host still comes first. Once any key is filed by host, another
    host gets no key rather than the generic one.
- **Thinking is never spoken.** `endpoints.ThinkFilter` takes out
  `<think>`, `<thinking>` and `<reasoning>` blocks, including tags split
  across stream pieces. `split_delta` also takes `reasoning_content` and
  `reasoning` fields. An unclosed block stays thinking.
  - It travels as `Chunk.thinking` into the history and saved chats.
  - `ExchangeItem` shows it greyed and folded: "▸ thought (not spoken)".
  - The replayed transcript holds only the answer.
- **CLI:** `agentvoice endpoint clean|models|test|key set/show/clear|presets`.
- Item 9 ("local models with tool calling get the 12a tools") is not done.
  The plan marked it later/optional.

## 12a. Desktop tools

- **Setting `desktopTools`, off by default**, on Agents → **On the
  desktop**. When on, Claude Code agents start `daemon/desktop_mcp.py`
  through `--mcp-config`, added to your own MCP servers rather than
  replacing them. The server is stdlib JSON-RPC over stdio.
- **Tools:**
  - windows and workspaces: `list_windows`, `active_window`,
    `list_workspaces`, `focus_window`, `move_window`, `close_window`,
    `switch_workspace`;
  - apps: `open_app`, which opens a desktop entry by its launcher name and
    never a command;
  - `open_project_layout`: a terminal and the editor in the folder, plus the
    browser at an optional http(s) URL. It is configured per call, not by a
    setting;
  - `media` (playerctl if present, else MPRIS over busctl; this machine has
    no playerctl), `volume`, `notify`;
  - `clipboard_read`, `clipboard_write`, `screenshot`, `lock_screen`,
    `suspend`.
- **Permissions:**
  - **Free at every level:** the window and workspace lists.
  - **Asked below Trusted:** every change, and `clipboard_read` (it often
    holds a password).
  - **Screenshots:** asked by the server itself, every time, at every
    level. A chat grant does not cover them. This holds even for a trusted
    agent that has no hook.
  - **`lock_screen` and `suspend`:** refused unless the transcript in the
    state file says lock, or suspend/sleep/hibernate.
  - The hook matches the whole `mcp__agentvoice-desktop__` prefix, and a
    test keeps its lists in step with the server's.
- **`ToolSearch` added to `NO_EFFECT`.** Every MCP tool is deferred and
  loaded through ToolSearch first, so at "ask" each desktop tool used to
  get an extra card.
- Codex and Gemini are not wired. Codex's limit lasts until Nov 27, and no
  Gemini CLI is installed. Per the repo rule, a backend needs one real turn
  first.

## 12b. Omarchy skill

- **Setting `omarchySkill`, on by default**, beside Desktop tools.
- `daemon/omarchy_skill.py` builds
  `~/.local/share/agentvoice/omarchy-skill/` from two sources:
  - `omarchy commands --json`: 145 of 425 commands, from everyday groups
    only. Install, remove, update, hardware, sudo and similar are left out;
  - `hyprctl binds -j`: 162 described bindings, without the media keys.
  It also adds the scratchpad dispatches, taken from Omarchy's
  `tiling.lua`.
  - Output: a plugin folder with `.claude-plugin/plugin.json` and
    `skills/omarchy/SKILL.md` (27KB), plus `instructions.txt` (5.9KB).
- **Claude Code:** `--plugin-dir` for the voice process only. Nothing is
  written into `~/.claude`.
- **Codex, Gemini, Antigravity, Copilot:** the short list, added to their
  instructions (`Adapter.skill_text`). Endpoints get nothing.
- `install.sh` builds it, and that step is never fatal. Uninstall removes
  it. The daemon rebuilds it once per start, on a thread, if the Omarchy
  version or the generator changed.
- `Daemon.apply_extras` sets both on every idle agent. A change lets the
  warm process go but keeps the conversation.

## Measured (FINDINGS §31)

- MCP server start, handshake and tool list: 94ms median. A real
  `list_windows`: 116ms.
- A real Claude turn called `list_windows` and answered "1" (5.4s).
- A real turn as Sora at "ask": the list was allowed with no card, and
  `notify` was asked about and denied on silence.
- Skill, same question with and without `--plugin-dir`: 3/3 exact with it,
  1/3 without (it invented `omarchy-cmd-ocr`).
- The QML was previewed (screen unlocked this time), with an endpoint agent
  in a scratch copy of shell.json. It found that the address line said "That
  does not look like an address" when `agentvoice` was an older build with
  no `endpoint` command. Fixed: the line only shows once `clean` has
  answered.

## Not done / caveats

- **No real endpoint turn.** There is no key on this machine and no local
  server. I downloaded llama.cpp's CPU build and Qwen3-0.6B to
  `~/.cache/agentvoice-bench/` (~660MB), but the session's permission rules
  refused to run the server. To test: start it yourself (command below),
  then use Test connection with `localhost:8080` and model `qwen3-0.6b`.
  That also exercises the thinking filter, because Qwen3 thinks. Delete
  the folder when done.

      ~/.cache/agentvoice-bench/llama-b12503/llama-server \
        -m ~/.cache/agentvoice-bench/qwen3-0.6b-q8.gguf --port 8080 --jinja --alias qwen3-0.6b

  If it answers, llama.cpp can become a preset: add a FINDINGS row, then
  the preset.
- `open_project_layout` is configured per call, not saved as a layout
  setting.
- `daemon/adapters/claude_code.py` (`--chrome`) is still uncommitted, and
  was kept out of this commit as before.

## Live checklist

1. Install (`install.sh --yes`, which ends any voice turn) and restart the
   shell (QML changed). The install line should say "Omarchy skill: N
   commands, M keybindings".
2. Agents → add an agent, program **Endpoint**, preset Ollama (or your Mac
   mini's address). "Will use …" shows the cleaned address. List models
   fills the dropdown. Test connection shows the first word's time.
3. Paste a key for a keyed endpoint and save. It shows masked, and
   `~/.config/agentvoice/endpoint-keys.json` is mode 600.
4. Say that agent's name with a question. It answers, and with a reasoning
   model the thinking appears greyed in the conversation view, never aloud.
5. On the desktop → Desktop tools on. Then "Theo, what windows are open?"
   (no card), "Theo, move the browser to workspace 3" (a card at ask; none
   at trusted, which Theo is), "Theo, take a screenshot and tell me what's
   on screen" (a card every time, even for Theo), and "Theo, lock the
   screen" (works). The refusal without the word is covered by tests:
   an agent that decides on its own to lock the screen is refused.
6. Omarchy skill on: "Theo, turn on do not disturb" should run
   `omarchy toggle notification silencing`, not a guess.
