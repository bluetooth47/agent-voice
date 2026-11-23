// Agent details → Advanced: what is running (master plan, M16), driven by
// synthetic mouse events (QtTest's TestEvent: the real pointer never moves)
// through the real page and the real `agentvoice agents runinfo|prompt`,
// over a scratch runtime folder holding advanced.run.json as the daemon's
// published record (main on Claude Code, hazel on Codex, echo-local on an
// endpoint: the native, index-only and endpoint variants) and a scratch data
// folder advanced.seed.py writes:
//
//   preview.sh --config bench/preview/configs/agents8.json --scratch-data \
//     --wait 40 --out /tmp/adv advanced
//   grep PREVIEW /tmp/adv.log; cat /tmp/adv.writes
//
// --arg shots:AGENT walks that agent's tab a screenful at a time instead,
// clicking nothing (with "Show all" pressed under shots:AGENT:shown).
//
// Checks: the command line drawn is the published one; the session, the
// working directory and the timeouts; the servers, given apart from what
// the program said it started (github: given, failed to start); the log
// lines and the permission decisions; the prompt's text is on screen only
// after Show all (a made-up word in the personality); Open full log hands
// the terminal journalctl and nothing else; Codex's line and no "said it
// started"; the endpoint's "no process"; and no setting is written.
import QtQuick
import QtTest
import Quickshell
import Quickshell.Io
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    readonly property string arg: Quickshell.env("PREVIEW_ARG") || ""
    readonly property bool shotsOnly: arg.indexOf("shots") === 0
    readonly property var shotsArg: arg.split(":")
    Component.onCompleted: overlay.open('{"page":"agentdetails","agent":"' +
                                        (overlay.shotsOnly && shotsArg[1] ? shotsArg[1] : "main") +
                                        '","tab":"advanced"}')
    TestEvent { id: input }
    Loader {
      active: overlay.shotsOnly
      sourceComponent: Component { Scroller { target: overlay } }
    }
    Timer {
      interval: 1500
      running: overlay.shotsOnly && overlay.shotsArg[2] === "shown"
      onTriggered: { var p = overlay.page(); if (p) p.revealPrompt = true }
    }

    property int passed: 0
    property int failed: 0
    function check(ok, what) {
      if (ok) passed++; else failed++
      console.warn("PREVIEW " + (ok ? "PASS " : "FAIL ") + what)
    }
    function find(item, test) {
      if (!item || item.visible === false || item.opacity === 0) return null
      if (test(item)) return item
      var kids = item.children || []
      for (var i = 0; i < kids.length; i++) {
        var hit = find(kids[i], test)
        if (hit) return hit
      }
      return null
    }
    function all(item, test, out) {
      out = out || []
      if (!item || item.visible === false || item.opacity === 0) return out
      if (test(item)) out.push(item)
      var kids = item.children || []
      for (var i = 0; i < kids.length; i++) all(kids[i], test, out)
      return out
    }
    function content() { return overlay.pageScroll ? overlay.pageScroll.contentItem : null }
    function click(item, label) {
      if (!item) { check(false, "found " + label); return }
      var flick = overlay.pageScroll
      if (flick && content()) {
        var y = item.mapToItem(content(), 0, 0).y
        flick.contentY = Math.max(0, Math.min(y - 120, flick.contentHeight - flick.height))
      }
      console.warn("PREVIEW click " + label)
      input.mouseClick(item, item.width / 2, item.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
    }
    function page() { return find(content(), function(i) { return i.loadRun !== undefined }) }
    // Every visible Text on the page holding `s`.
    function drawn(s) {
      return all(content(), function(i) {
        return i.textFormat !== undefined && i.text !== undefined && String(i.text).indexOf(s) >= 0
      }).length
    }
    function button(text) {
      return find(content(), function(i) { return i.clicked !== undefined && String(i.text) === text })
    }

    property string writes: ""
    FileView {
      id: writesFile
      path: Quickshell.env("PREVIEW_WRITES") || "/nonexistent"
      printErrors: false
      onLoaded: overlay.writes = text()
    }

    property int step: 0
    property int warm: 0
    Timer {
      interval: 1500
      repeat: true
      running: !overlay.shotsOnly
      onTriggered: {
        if (!overlay.store.loaded || ++overlay.warm < 3) return
        overlay.step++
        var p = overlay.page()
        switch (overlay.step) {
        case 1:
          overlay.check(p !== null && p.tab === "advanced", "Agent details opens on Advanced")
          break
        case 2:
          overlay.check(p && p.run !== null && p.run.daemon === true, "it reads the published record")
          overlay.check(p && p.run && overlay.drawn(p.run.line) === 1,
                        "the command line drawn is the published one")
          overlay.check(overlay.drawn("--resume 7d1f5a2e-0c4b-4e8a-9f61-2b3c4d5e6f70") >= 1,
                        "it resumes the session it names")
          overlay.check(overlay.drawn("still running, with the same line.") === 1,
                        "the last launch: still running, the same line")
          overlay.check(overlay.drawn("Session 7d1f5a2e-0c4b-4e8a-9f61-2b3c4d5e6f70 · its next turn resumes it · 4 turns") === 1,
                        "the conversation: id, resumes, turns")
          overlay.check(overlay.drawn("/home/you/projects/garden") >= 1, "the working directory")
          overlay.check(overlay.drawn("Stopped after 90 seconds") === 1 && overlay.drawn("waits 5 minutes") === 1,
                        "the timeouts")
          overlay.check(overlay.drawn("github  ·  found on this machine  ·  given  ·  said it started: failed") === 1,
                        "github: given, and failed to start, said apart")
          overlay.check(overlay.drawn("agentvoice-crew  ·  Agent Voice's own  ·  given  ·  said it started: connected") === 1,
                        "the notes server: given and connected")
          overlay.check(overlay.drawn("turn 41.0s · warm start · first token 900 ms · tools: Bash ×6, Edit, mcp__github__list_issues") === 1,
                        "a log line, by its numbers and tool names")
          overlay.check(overlay.drawn("started again for a new level · conversation kept") === 1, "a rebuild in the log")
          overlay.check(overlay.drawn("Write   refused · nobody answered · at") === 1, "a decision nobody answered")
          overlay.check(overlay.drawn("mcp__github__create_issue   refused · without asking") === 1, "a refusal")
          overlay.check(overlay.drawn("Bash   allowed · you were asked") === 1, "an allow, asked")
          break
        case 3:
          overlay.check(p && p.told !== null && p.told.pieces.length > 0, "the prompt is read")
          overlay.check(overlay.drawn("MARIGOLD-7") === 0, "its text is not drawn until asked")
          overlay.click(overlay.button("Show all"), "Show all")
          break
        case 4:
          overlay.check(overlay.drawn("MARIGOLD-7") === 1, "Show all draws it")
          overlay.click(overlay.button("Hide all"), "Hide all")
          break
        case 5:
          overlay.check(overlay.drawn("MARIGOLD-7") === 0, "Hide all hides it again")
          // One piece's own Show: the row whose label is "N. About you, …".
          var label = overlay.find(overlay.content(), function(i) {
            return i.textFormat !== undefined && /^\d+\. About you/.test(String(i.text)) })
          overlay.click(label ? overlay.find(label.parent, function(i) {
            return i.clicked !== undefined && String(i.text) === "Show" }) : null, "About you's Show")
          break
        case 6:
          overlay.check(overlay.drawn("MARIGOLD-7") === 1, "one piece's Show draws that piece")
          overlay.check(overlay.drawn("Standing order") === 0 && overlay.drawn("Say which file you changed.") === 0,
                        "and only that piece")
          overlay.click(overlay.button("Open full log"), "Open full log")
          break
        case 7:
          writesFile.reload()
          break
        case 8:
          overlay.check(overlay.writes.indexOf("floating-terminal journalctl --user -u agentvoice -n 300 -f") >= 0,
                        "Open full log hands the terminal journalctl, and nothing else")
          if (p) overlay.s_detailsAgent("hazel")
          break
        case 9:
          break                         // the switch reads its record: give it a step
        case 10:
          overlay.check(p && p.run && p.run.agent === "hazel" && overlay.drawn("codex exec --json") === 1,
                        "hazel's line is Codex's")
          overlay.check(overlay.drawn("filesystem  ·  found on this machine  ·  switched off: started with it off") === 1,
                        "a config.toml server started switched off")
          overlay.check(overlay.drawn("·  said it started") === 0 && overlay.drawn("not in its last start") === 0,
                        "Codex says nothing about what it started, and the row claims nothing")
          overlay.check(overlay.drawn("ended, with the same line.") === 1, "its last process ended")
          overlay.check(overlay.drawn("No conversation yet") === 1, "no conversation yet")
          overlay.check(overlay.drawn("Bash   allowed · by its level · at") === 1, "its own decision, not main's")
          overlay.check(overlay.drawn("Write   refused") === 0, "and not main's")
          overlay.s_detailsAgent("echo-local")
          break
        case 11:
          break
        case 12:
          overlay.check(p && p.run && p.run.agent === "echo-local" &&
                        overlay.drawn("No process: each turn is an HTTPS request to localhost:11434, model llama3.2.") === 1,
                        "the endpoint: no process, and where it goes")
          overlay.check(overlay.drawn("Keeps the last") === 1, "the endpoint keeps turns itself")
          // The header's link, and the timeout's (no working directory row).
          overlay.check(overlay.all(overlay.content(), function(i) {
                          return i.clicked !== undefined && String(i.text) === "Change on Agents page →" }).length === 2 &&
                        overlay.drawn("/home/you/projects/garden") === 0,
                        "its timeout links to the Agents page, and it has no working directory")
          writesFile.reload()
          break
        case 13:
          overlay.check(overlay.writes.indexOf("bar set") < 0, "no setting was written")
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          break
        }
      }
    }
    function s_detailsAgent(id) { overlay.detailsAgent = id }
  }
}
