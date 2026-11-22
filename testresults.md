# Test results

Run started 2026-11-18 against build 9e1918f (`phase-g`). Plan: testplan.md.

## Bugs found

| # | found by | bug | severity | status |
|---|---|---|---|---|
| 1 | B-CLI-14 | `agentvoice permit <id>` writes a `.response` even when no `<id>.request` exists; stale responses pile up (one left from 13:42) | low | fixed e331d31 |
| 2 | B-CLI-24 | the usage line leaves out `endpoint` | trivial | fixed e331d31 (a test holds it to every command) |
| 3 | B-CLI-20 | `agentvoice voice fetch` of an unpinned voice prints the refusal but exits 0 | — | not a bug: it exits 1; my check read `tail`'s status |
| 4 | B-MCP-08 | `clipboard_write` copies, then reports "wl-copy did not finish in 10s": wl-copy forks a holder that keeps the output pipes open. The stub tests could not see it | medium | fixed e331d31, checked on the real desktop (0.06s) |
| 5 | A-05 M7 | no test catches `endpoints.py` sending a saved key over plain http to a public host (the adapter's own check is tested; the helper's is not) | low (test gap) | fixed e331d31; M7 now goes red |
| 6 | B-UI-12 | the permission card says "The agent" for the main agent, not its name, and shows the raw tool name (`mcp__claude-in-chrome__computer`) | polish | fixed e331d31 (seen after the next shell restart) |
| 7 | B-UI-14 | the `clicks` preview target clicked controls below the fold, where a synthetic click lands on nothing, and reported nothing for the model chip | harness | fixed in the working tree (scrolls into view first) |
| 8 | Codex run | phase3notes.md says Codex chats are replayed, not resumed. Codex claims `remembers` and resumed across two real turns | doc | fixed in phase3notes.md |

| 9 | D-01 | after 5 quick restarts systemd refuses starts, and `agentvoice start` / the panel switch fail until `systemctl --user reset-failed` | low | fixed e331d31 |
| 10 | user, live 2026-11-19 | with the microphone muted, replies to turns typed in the Claude terminal are still spoken, but the HUD popup never appears; the panel's "last heard" stays on the last turn from before (`random`) and Theo's chip still reads "speaking". Expected: the popup shows whatever is being spoken, muted or not. Cause (M2): with several agents the readout put the microphone's "off" over the agent's own state; with one, nothing published "off" after a typed turn while muted | medium | fixed in M2 (driven in test_typed.py; not yet seen live) |

## Results

| ID | result | evidence | note |
|---|---|---|---|
| B-CLI-01 | pass | listening, claude, trusted, crew [sora] | |
| B-CLI-02 | pass | yes, exit 0 | |
| B-CLI-03 | pass | no; pid file removed | |
| B-CLI-04 | pass | listening in 4.3s; banner build 0.2.0 (9e1918f) | |
| B-CLI-05 | pass | no → yes | |
| B-CLI-06 | pass | state `off` (widget: MICROPHONE OFF) → listening, same pid | plan said `muted`; `off` is the design |
| B-CLI-07 | pass | yes/0, state locked → no/1, listening | |
| B-CLI-08 | pass | exit 0, no change | |
| B-CLI-09 | pass | capture → listening, "(nothing heard)" | |
| B-CLI-10 | pass | open_mic {who Theo, id main, until} → {} | |
| B-CLI-11 | pass | running → stopped, file 600 | |
| B-CLI-13 | pass | `{}` | |
| B-CLI-14 | fail | bad id shape refused (exit 2), but a well-formed unknown id writes a response | bug 1 |
| B-CLI-15 | pass | "nothing yet this session" after restart | |
| B-CLI-17 | pass | usage, exit 2 | |
| B-CLI-24 | pass (bug 2) | usage, exit 2 | |
| B-CLI-25 | pass | help box | |
| B-CLI-16 | pass | test chat: list/show/rename/pin/unpin/export (no overwrite: `-2.md`)/delete; dir 700, index 600 | export keeps `<b>` from a reply as text in the Markdown |
| B-CLI-12 | pass | auto test 77s: Theo 13/20, Sora 16/20, full stop 10/10, 0 false of 65 | §26 had Theo 15/20 |
| B-CLI-18 | pass | voice played (cut at 6s by me) | |
| B-CLI-19 | pass | lessac-low fetched in 3s, hash-checked, removed | |
| B-CLI-20 | pass (bug 3) | refused: "not in models.lock" | exit 0 |
| B-CLI-21 | pass | verdict: barge-in will not work on speakers here; use a headset | |
| B-CLI-22 | pass | monitor prints scores; daemon still active | |
| B-RT-01 | pass | dir 700; state, wake-test, wake-auto 600 | pid and wake-auto.log 644 inside the 700 dir |
| B-RT-02 | pass | 0 bad reads of 400 | |
| B-RT-03 | pass | pid matches the daemon; removed on stop | |
| B-RT-04 | pass | no grants dir after restart | |
| B-EP-01 | pass | 7 forms as expected; `user:key@` and junk refused, exit 1 | |
| B-EP-02 | pass | "Ollama isn't running (nothing on port 11434)" | |
| B-EP-03 | pass | "nothing is listening on 127.0.0.1 port 47211: wrong port?" | |
| B-EP-04 | pass | "it wants an API key" | |
| B-EP-05 | pass | masked gsk…9999, file 600, not in shell.json, cleared to {} | |
| B-EP-06 | pass | endpoints.py argv has no key | |
| B-EP-07 | blocked | no key or local server | |
| B-EP-08 | blocked | no reasoning-model endpoint | |
| B-MCP-01 | pass | 19 tools, 82 ms median | |
| B-MCP-02 | pass | real window list | |
| B-MCP-03 | pass | focus "done" (Lua) | |
| B-MCP-04 | pass | "done" | |
| B-MCP-05 | pass | Files opened, closed | |
| B-MCP-06 | pass | moved to 9 (focus stayed on foot), back | |
| B-MCP-07 | pass | shown | |
| B-MCP-08 | fail (bug 4) | text copied and read back, but the write reported a timeout | |
| B-MCP-09 | pass | volume 40% (unchanged) | |
| B-MCP-10 | pass | "nothing is playing" | |
| B-MCP-11 | pass | README at line 100 in VS Code | |
| B-MCP-12 | pass | diff window "…HEAD-calc.py ↔ calc.py" | |
| B-MCP-13 | pass | terminal and editor in the folder | |
| B-MCP-14 | pass | refused | |
| B-MCP-15 | pass | refused | |
| B-MCP-16 | pass | card, refused after 6s, no file left | |
| B-HOOK-01 | pass | read allowed, no card | |
| B-HOOK-02 | pass | Write asked ×2, denied | |
| B-HOOK-03 | pass | asked, "this reads …/sub/.env" | |
| B-HOOK-04 | pass | asked (Claude Code 2.1.327 has no Grep tool; it used Bash, which is asked) | the Grep pre-search path is now unreachable from Claude |
| B-HOOK-05 | pass | written, no card (project at ~/.cache) | first run under ~/.claude was asked: `/.claude/` is NEVER_SILENT, so is `/.config/omarchy/` — this plugin's own repo |
| B-HOOK-06 | pass | asked | |
| B-HOOK-07 | pass | asked; file not made | |
| B-HOOK-08 | pass | Bash ran, no hook | |
| B-HOOK-09 | pass | WebSearch asked | |
| B-HOOK-10..12 | pass | §31 real turns today (list free, notify asked, ToolSearch free) | |
| B-HOOK-13 | pass | allow-session: second write not asked; new chat asked again | |
| B-HOOK-14 | pass | `agentvoice permit … deny` denied | |
| B-HOOK-15 | pass | killed mid-card: no .request left | |
| B-HOOK-16 | pass | corrupt response → denied | |
| B-SK-01 | pass | 145 commands; Lua scratchpad line; no install/update commands | |
| B-SK-02 | pass | stamp 4.5.0-3 3c0aa25425d2 = now | |
| B-SK-03 | pass | 3/3 exact, 5.3s | |
| B-UI-01..07 | pass | 7 pages × 3 screens × 2 themes (current, flexoki-light), checked by eye | |
| B-UI-08 | pass | popup with the showcase state | |
| B-UI-10/11 | pass | conversation view: session plus saved chats list | |
| B-UI-12 | pass (bug 6) | browser card with note; Bash card with 520-char truncation note and "allow all" | `<b>` shown as text |
| B-UI-13 | pass | records for main and Sora | |
| B-UI-14 | pass after harness fix | hud, model, Snappy (4 keys), permissions written to the stub; real shell.json unchanged | bug 7 |
| B-UI-15 | pass | 2 commits, on release only; external set followed | |
| A-01 | pass | 15 checks ok, 1716 tests | |
| A-02 | pass | box 9/9 | |
| A-03 | pass | 1700 passed, 9 honest skips (numpy/openWakeWord) | |
| A-04 | pass | 1716, no skips | |
| A-05 | 6 of 7 caught | M1 hook crash, M2 --settings, M3 thinking, M4 desktop prefix, M5 dispatch, M6 browser at trusted: red. M7 key over http: survived | bug 5 |
| A-06 | pass | in A-01 | |
| Codex | pass | real turns: "noted." in 6.5s (first text 3.9s); remembered "teal" next turn; `codex resume <id>` exists for the handoff | bug 8 |
| A-07 | pass with known exceptions | dev 1279, phase-b 1304, phase-d 1489, phase-e 1557 green; phase-c and phase-f fail qmllint only (fixed in the next branch each time: Chats.qml in phase-d, EndpointEditor in phase-g) | merging in order ends green |
| D-01 | pass (bug 9) | 10 restarts, 4 within 1.5s of start: no core dumps; systemd start limit tripped | |
| D-02 | pass | kill -9: systemd restarted it (Restart=on-failure), new pid, listening | |
| D-11 | in progress | RSS 946 MB at 6.5 min idle, 3.6% CPU; 702 MB after reinstall | older notes said ~594 MB: sherpa + Vosk + Whisper base.en + two Piper voices now |
| Fixes re-run | pass | check 1722; M7 red; clipboard 0.06s on the real desktop; permit unknown id → exit 1; build e331d31 installed | |

## Not run yet

- **Tier C (live voice)**: all of it. Needs you at the desk (testplan.md section 11, sessions 1–7).
- **B-UI-09** (the HUD readout): no preview target; covered in C-HEAR-01.
- **B-EP-07/08, C-EP**: need an endpoint (a key, Ollama, or the llama.cpp server).
- **Browser (C-BROW)**: needs Chrome with Claude in Chrome running.
- **E-PRIV-01**: needs a spoken turn with logSpeech off; it closes session 7.
- **D-03..D-14, E-SEC, F, G**: mostly alongside the live sessions; G-06/07 (uninstall/reinstall) last.
- **Gemini**: not installed. Antigravity, Copilot: one turn each if wanted.
