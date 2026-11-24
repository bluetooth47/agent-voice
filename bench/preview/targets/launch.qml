// Agent details → Advanced: how an agent is launched (master plan, M17),
// driven by synthetic mouse events (QtTest's TestEvent: the real pointer
// never moves) through the real page, the real `agentvoice agents flags |
// env | duplicate | reset | unreset` over a scratch data and config folder,
// and a scratch shell.json the stub applies each `bar set` to:
//
//   preview.sh --config bench/preview/configs/agents8.json --scratch-data \
//     --wait 40 --out /tmp/launch launch
//   grep PREVIEW /tmp/launch.log; cat /tmp/launch.writes
//
// --arg shots:AGENT walks that agent's tab a screenful at a time instead.
//
// Checks, each warning cancelled once and then confirmed once: a refused
// flag is refused with its reason and cannot be added; a harmless one asks
// first, and Cancel writes nothing; confirmed, it is the one write of
// mainExtraArgs; Remove takes it out. An environment variable on the list
// is refused with the reason; a key is set, shown by its name only, never
// written to the settings or the log, and removed only from its confirm.
// Resume and the hung-turn limit write the main agent's twins; Start fresh
// asks, then runs `chats new main` only. On Sora (an extra agent) the same
// controls write her entry through setAgentField; Duplicate adds a copy,
// switched off, at Ask, with no extra flag; Reset asks, then writes her
// entry back to a new agent's and starts her fresh; Undo puts her back.
// Nova (Gemini) is passed no flag and says why.
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
    function drawn(s) {
      return all(content(), function(i) {
        return i.textFormat !== undefined && i.text !== undefined && String(i.text).indexOf(s) >= 0
      }).length
    }
    // A row by its label (SettingRow, ToggleRow, SliderRow), and a button in it.
    function row(label) {
      return find(content(), function(i) {
        return i.label !== undefined && String(i.label) === label &&
               (i.stacked !== undefined || i.committed !== undefined)
      })
    }
    function buttonIn(item, text) {
      return find(item, function(i) { return i.clicked !== undefined && String(i.text) === text })
    }
    function field(placeholder) {
      return find(content(), function(i) { return String(i.placeholderText || "") === placeholder })
    }
    function knob(label) {
      return find(content(), function(i) { return i.committed !== undefined && String(i.label) === label })
    }
    function switchIn(item) {
      return find(item, function(i) { return i !== item && i.toggled !== undefined && i.checked !== undefined })
    }

    property string writes: ""
    FileView {
      id: writesFile
      path: Quickshell.env("PREVIEW_WRITES") || "/nonexistent"
      printErrors: false
      onLoaded: overlay.writes = text()
    }
    function count(s) { return overlay.writes.split(s).length - 1 }
    function lastWrite(key) {
      var lines = overlay.writes.split("\n").filter(function(l) {
        return l.indexOf("bar set duaneoca.agentvoice " + key + " ") === 0 })
      return lines.length ? lines[lines.length - 1] : ""
    }
    function sora() {
      var list = overlay.voiceAgents
      for (var i = 0; i < list.length; i++) if (overlay.agentId(list[i]) === "sora") return list[i]
      return null
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
          overlay.check(p !== null && p.tab === "advanced" && p.target === "main", "Advanced, on the main agent")
          overlay.check(overlay.row("Extra flags") !== null && overlay.row("Environment variables") !== null,
                        "the flags and environment rows are drawn")
          overlay.check(overlay.knob("Stop a turn after") !== null, "the hung-turn limit is drawn")
          overlay.check(overlay.buttonIn(overlay.content(), "⚠ Start fresh") !== null, "Start fresh is drawn")
          overlay.check(overlay.drawn("How Theo runs") === 1 && overlay.drawn("the risky ones ask first") === 1,
                        "the tab says it changes things now")
          overlay.field("--flag or --flag=value").text = "--dangerously-skip-permissions"
          break
        case 2:
          overlay.check(overlay.drawn("Refused, and not saved: it changes what the agent may do without asking") === 1,
                        "a refused flag says why")
          var add = overlay.buttonIn(overlay.row("Extra flags"), "⚠ Add")
          overlay.check(add !== null && add.enabled === false, "and Add cannot be pressed")
          overlay.field("--flag or --flag=value").text = "--bare"
          break
        case 3:
          overlay.check(overlay.drawn("Refused, and not saved: it changes or skips hooks") === 1,
                        "--bare is refused: it skips the hook")
          overlay.field("--flag or --flag=value").text = "--debug"
          break
        case 4:
          overlay.check(overlay.drawn("⚠ Not one Agent Voice knows to be a way round its settings") === 1,
                        "a harmless flag is marked and asks first")
          overlay.click(overlay.buttonIn(overlay.row("Extra flags"), "⚠ Add"), "Add")
          break
        case 5:
          overlay.check(overlay.drawn("Pass --debug to Theo's program on every turn?") === 1, "the confirm names the flag")
          overlay.click(overlay.buttonIn(overlay.row("Extra flags"), "Cancel"), "Cancel")
          writesFile.reload()
          break
        case 6:
          overlay.check(overlay.count("mainExtraArgs") === 0, "Cancel wrote nothing")
          overlay.click(overlay.buttonIn(overlay.row("Extra flags"), "⚠ Add"), "Add again")
          break
        case 7:
          overlay.click(overlay.buttonIn(overlay.row("Extra flags"), "Add"), "confirm Add")
          writesFile.reload()
          break
        case 8:
          writesFile.reload()
          break
        case 9:
          overlay.check(overlay.count("mainExtraArgs") === 1 && overlay.lastWrite("mainExtraArgs").indexOf('["--debug"]') > 0,
                        "confirmed, it is one write of mainExtraArgs")
          overlay.check(overlay.drawn("--debug   ⚠ passed") === 1, "and is listed as passed")
          overlay.check(overlay.field("--flag or --flag=value").text === "", "the field is emptied")
          overlay.click(overlay.buttonIn(overlay.row("Extra flags"), "Remove"), "Remove the flag")
          break
        case 10:
          writesFile.reload()
          break
        case 11:
          overlay.check(overlay.lastWrite("mainExtraArgs").indexOf("[]") > 0, "Remove writes the list without it")
          overlay.field("NAME").text = "LD_PRELOAD"
          overlay.field("value").text = "/tmp/x.so"
          overlay.click(overlay.buttonIn(overlay.row("Environment variables"), "Set"), "Set LD_PRELOAD")
          break
        case 12:
          overlay.check(overlay.drawn("Not changed: LD_PRELOAD is never set for an agent: it changes which code") === 1,
                        "a denied name is refused with the reason")
          overlay.check(overlay.field("value").text === "", "and the value left the field")
          overlay.field("NAME").text = "ANTHROPIC_API_KEY"
          overlay.field("value").text = "PREVIEW-SECRET-0042"
          overlay.click(overlay.buttonIn(overlay.row("Environment variables"), "Set"), "Set a key")
          break
        case 13:
          break
        case 14:
          overlay.check(overlay.drawn("ANTHROPIC_API_KEY   · set") === 1, "the key is listed by its name")
          overlay.check(overlay.drawn("PREVIEW-SECRET-0042") === 0 && overlay.field("value").text === "",
                        "its value is drawn nowhere and kept in no field")
          writesFile.reload()
          break
        case 15:
          overlay.check(overlay.writes.indexOf("PREVIEW-SECRET") < 0 && overlay.count("ANTHROPIC_API_KEY") === 0,
                        "nor written to the settings")
          overlay.click(overlay.buttonIn(overlay.row("Environment variables"), "⚠ Remove"), "Remove the key")
          break
        case 16:
          overlay.check(overlay.drawn("Remove ANTHROPIC_API_KEY? Its value is kept nowhere else.") === 1,
                        "removing a key asks first")
          overlay.click(overlay.buttonIn(overlay.row("Environment variables"), "Cancel"), "Cancel")
          break
        case 17:
          overlay.check(overlay.drawn("ANTHROPIC_API_KEY   · set") === 1, "Cancel kept it")
          overlay.click(overlay.buttonIn(overlay.row("Environment variables"), "⚠ Remove"), "Remove again")
          break
        case 18:
          overlay.click(overlay.buttonIn(overlay.row("Environment variables"), "Remove"), "confirm Remove")
          break
        case 19:
          break
        case 20:
          overlay.check(overlay.drawn("ANTHROPIC_API_KEY   · set") === 0 && overlay.drawn("ANTHROPIC_API_KEY is removed.") === 1,
                        "confirmed, it is gone")
          overlay.click(overlay.switchIn(overlay.row("Resume its conversation")), "Resume off")
          overlay.knob("Stop a turn after").committed(240)
          break
        case 21:
          writesFile.reload()
          break
        case 22:
          overlay.check(overlay.lastWrite("mainResume").indexOf("false") > 0, "Resume off writes mainResume false")
          overlay.check(overlay.lastWrite("mainIdleTimeoutS").indexOf("240") > 0, "the limit writes mainIdleTimeoutS")
          overlay.click(overlay.buttonIn(overlay.content(), "⚠ Start fresh"), "Start fresh")
          break
        case 23:
          overlay.check(overlay.drawn("End Theo's conversation? This one stays in Chats.") === 1, "Start fresh asks")
          overlay.click(overlay.buttonIn(overlay.content(), "Cancel"), "Cancel")
          writesFile.reload()
          break
        case 24:
          overlay.check(overlay.count("chats new") === 0, "Cancel ran nothing")
          overlay.click(overlay.buttonIn(overlay.content(), "⚠ Start fresh"), "Start fresh again")
          break
        case 25:
          var strip = overlay.find(overlay.content(), function(i) {
            return i.armed === true && String(i.text) === "Start fresh" })
          overlay.click(strip ? overlay.buttonIn(strip, "Start fresh") : null, "confirm Start fresh")
          break
        case 26:
          writesFile.reload()
          break
        case 27:
          overlay.check(overlay.count("agentvoice chats new main") === 1 && overlay.count("chats new") === 1,
                        "confirmed, it ends the main agent's conversation and no other")
          overlay.goTo("agentdetails", "sora", "advanced")
          break
        case 28:
          break
        case 29:
          overlay.check(p && p.target === "sora", "Sora's Advanced")
          overlay.click(overlay.switchIn(overlay.row("Resume its conversation")), "Sora's resume off")
          overlay.field("--flag or --flag=value").text = "--max-budget-usd=1"
          break
        case 30:
          overlay.click(overlay.buttonIn(overlay.row("Extra flags"), "⚠ Add"), "Add Sora's flag")
          break
        case 31:
          overlay.click(overlay.buttonIn(overlay.row("Extra flags"), "Add"), "confirm Sora's flag")
          break
        case 32:
          writesFile.reload()
          break
        case 33:
          var s1 = overlay.sora()
          overlay.check(s1 && s1.resume === false && JSON.stringify(s1.extraArgs) === '["--max-budget-usd=1"]',
                        "Sora's entry holds her resume and her flag (setAgentField)")
          overlay.check(s1 && s1.model === "sonnet" && s1.futureField !== undefined,
                        "and every other field she had")
          overlay.check(overlay.count("mainResume") === 1 && overlay.count("mainExtraArgs") === 2,
                        "the main agent's twins were not touched")
          overlay.click(overlay.buttonIn(overlay.content(), "Duplicate"), "Duplicate Sora")
          break
        case 34:
          break
        case 35:
          writesFile.reload()
          break
        case 36:
          var copy = null
          for (var i = 0; i < overlay.voiceAgents.length; i++)
            if (String(overlay.voiceAgents[i].name) === "sora copy") copy = overlay.voiceAgents[i]
          overlay.check(copy !== null && copy.enabled === false && copy.level === "ask" &&
                        copy.extraArgs === undefined && copy.label === "Sora copy" &&
                        String(copy.id).indexOf("sora-copy-") === 0,
                        "Duplicate adds Sora copy: switched off, at Ask, with no extra flag")
          overlay.check(copy !== null && copy.model === "sonnet" && copy.resume === false &&
                        copy.notesWrite === "deny" && copy.acceptsWork === false,
                        "with her model and resume, and her restrictions")
          overlay.check(overlay.drawn("Made Sora copy, switched off.") === 1, "and says what it made")
          overlay.click(overlay.buttonIn(overlay.content(), "⚠ Reset to defaults"), "Reset")
          break
        case 37:
          overlay.check(overlay.drawn("Reset Sora to a new agent's settings and folder? Restore undoes it.") === 1,
                        "Reset asks, and says Restore undoes it")
          overlay.click(overlay.buttonIn(overlay.content(), "Cancel"), "Cancel")
          break
        case 38:
          var s2 = overlay.sora()
          overlay.check(s2 && s2.model === "sonnet", "Cancel reset nothing")
          overlay.click(overlay.buttonIn(overlay.content(), "⚠ Reset to defaults"), "Reset again")
          break
        case 39:
          overlay.click(overlay.buttonIn(overlay.content(), "Reset"), "confirm Reset")
          break
        case 40:
          break
        case 41:
          writesFile.reload()
          break
        case 42:
          var s3 = overlay.sora()
          overlay.check(s3 && s3.model === "" && s3.level === "ask" && s3.agent === "claude" &&
                        s3.extraArgs === undefined && s3.resume === undefined && s3.label === "Sora" &&
                        s3.name === "sora" && s3.tools === undefined && s3.notesWrite === undefined,
                        "reset: a new agent's settings, her name and wake phrase kept")
          overlay.check(overlay.count("agentvoice chats new sora") === 1, "and her conversation ends")
          overlay.check(overlay.drawn("Reset Sora to its defaults; the old folder and settings are in the trash.") === 1,
                        "with the way back")
          overlay.click(overlay.find(overlay.content(), function(i) {
            return i.clicked !== undefined && String(i.text) === "Undo" &&
                   String(i.parent && i.parent.children[0] && i.parent.children[0].text || "").indexOf("Reset Sora") === 0 }),
                        "Undo the reset")
          break
        case 43:
          break
        case 44:
          writesFile.reload()
          break
        case 45:
          var s4 = overlay.sora()
          overlay.check(s4 && s4.model === "sonnet" && JSON.stringify(s4.extraArgs) === '["--max-budget-usd=1"]' &&
                        s4.notesWrite === "deny" && s4.futureField !== undefined,
                        "Undo puts her back as she was")
          overlay.goTo("agentdetails", "nova", "advanced")
          break
        case 46:
          break
        case 47:
          overlay.check(p && p.target === "nova" &&
                        overlay.drawn("Passed to Claude Code and Codex only: no list of what must be refused has been written for Gemini") === 1,
                        "Gemini is passed no flag, and says why")
          overlay.check(overlay.field("--flag or --flag=value") === null, "and has no field to type one")
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          break
        }
      }
    }
  }
}
