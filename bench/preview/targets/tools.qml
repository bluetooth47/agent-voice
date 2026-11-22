// Tool switches and the tools found on this machine (master plan, M10),
// driven by synthetic clicks through the real settings store, the real
// `agentvoice agents catalog` and the real `agentvoice tools scan`, on the
// synthetic machine preview.sh makes (three Claude Code servers, one Codex
// server, two fake CLIs; never the person's own):
//
//   preview.sh --config bench/preview/configs/crew3.json --wait 120 --out /tmp/t tools
//   grep PREVIEW /tmp/t.log; cat /tmp/t.writes
//
// On Sora's Tools & skills tab (her own switches live there since M10):
// the "off since this version" notice; her desktop tools switched off by
// the built-in chip; github picked On -- the confirm shows what it runs and
// never the key in its environment -- cancelled, then turned on (her entry
// gets "mcp:github": "on:<fingerprint>"); gh on the same way; github off at
// once; the notice dismissed. Her Agents card then only summarises and
// links back. Hazel (Codex) cannot use a Claude Code server and says why.
// Communal → Tools turns linear on for every agent through its confirm,
// and adds a CLI by name.
import QtQuick
import QtTest
import Quickshell
import Quickshell.Io
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    Component.onCompleted: {
      seed.running = true
      overlay.open('{"page":"agentdetails","agent":"sora","tab":"tools"}')
    }

    TestEvent { id: input }

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
    function details() { return find(content(), function(i) { return i.previewParts !== undefined && i.askTool !== undefined }) }
    function row(label) {
      return find(content(), function(i) { return i.label !== undefined && i.hint !== undefined && String(i.label) === label })
    }
    function chip(within, text) {
      return find(within, function(i) { return i.clicked !== undefined && i.text !== undefined && String(i.text).indexOf(text) === 0 })
    }
    function confirmBox() { return find(content(), function(i) { return i.confirmText !== undefined && i.lines !== undefined }) }
    function button(within, text) {
      return find(within, function(i) { return i.clicked !== undefined && String(i.text) === text })
    }
    function soraTools() {
      for (var i = 0; i < overlay.voiceAgents.length; i++)
        if (overlay.agentId(overlay.voiceAgents[i]) === "sora") return overlay.voiceAgents[i].tools || {}
      return {}
    }
    function detected(id) {
      var d = details()
      var rows = d && d.catalog ? d.catalog.detected || [] : []
      return rows.filter(function(r) { return r.id === id })[0] || null
    }
    function communal() { return find(content(), function(i) { return i.toolList !== undefined && i.putShared !== undefined }) }

    Process {
      id: seed
      command: ["bash", "-c", 'agentvoice agents migrate >/dev/null']
      onRunningChanged: if (!running) overlay.folders.refresh()
    }

    property int step: 0
    property int warm: 0

    Timer {
      interval: 2000
      repeat: true
      running: true
      onTriggered: {
        if (!overlay.store.loaded || seed.running || ++overlay.warm < 3) return
        overlay.step++
        var d, r, box, c, t
        switch (overlay.step) {
        case 1:
          d = overlay.details()
          var cat = d ? d.catalog : null
          overlay.check(cat && cat.agent === "sora", "Sora's Tools & skills tab read her catalog")
          var ids = cat ? (cat.detected || []).map(function(x) { return x.id }).sort() : []
          overlay.check(JSON.stringify(ids) === JSON.stringify(["cli:gh", "cli:stripe", "mcp:desktop-control",
                                                                 "mcp:filesystem", "mcp:github", "mcp:linear"]),
                        "it lists what the synthetic machine has, nothing real (" + ids.join(", ") + ")")
          overlay.check(cat && !(cat.detected || []).some(function(x) { return x.on }), "every one is off")
          var notice = cat ? (cat.notice || []).map(function(x) { return x.id }).sort() : []
          overlay.check(notice.length === 5 && notice.indexOf("mcp:filesystem") < 0,
                        "the notice lists the five Sora could use, not Codex's (" + notice.join(", ") + ")")
          var fs = overlay.detected("mcp:filesystem")
          overlay.check(fs && !fs.can && fs.why_not.indexOf("Codex") >= 0, "Codex's server says why Sora cannot use it")
          overlay.click(overlay.chip(overlay.row("Desktop tools"), "Off"), "Desktop tools → Off")
          break
        case 2:
          t = overlay.soraTools()
          overlay.check(t.desktop === "off", "the built-in chip wrote her tools.desktop = off (" + JSON.stringify(t) + ")")
          overlay.click(overlay.chip(overlay.row("github · MCP server"), "On"), "github → On")
          break
        case 3:
          box = overlay.confirmBox()
          overlay.check(box !== null, "picking On asks first")
          var text = box ? JSON.stringify(box.lines) + box.title + box.warning : ""
          overlay.check(String(text).indexOf("server-github") >= 0 && String(text).indexOf("GITHUB_PERSONAL_ACCESS_TOKEN") >= 0,
                        "the confirm shows what it runs and the name of what it is given")
          overlay.check(String(text).indexOf("PREVIEWFAKE") < 0, "and never the key itself")
          overlay.check(String(text).indexOf("Sora only") >= 0, "and who gets it")
          overlay.check(overlay.soraTools()["mcp:github"] === undefined, "nothing is written before the answer")
          overlay.click(overlay.button(box, "Cancel"), "Cancel")
          break
        case 4:
          overlay.check(overlay.confirmBox() === null && overlay.soraTools()["mcp:github"] === undefined,
                        "Cancel writes nothing and closes it")
          overlay.click(overlay.chip(overlay.row("github · MCP server"), "On"), "github → On, again")
          break
        case 5:
          overlay.click(overlay.button(overlay.confirmBox(), "Turn on"), "Turn on")
          break
        case 6:
          break                           // the store, then the catalog on its delay
        case 7:
          t = overlay.soraTools()
          r = overlay.detected("mcp:github")
          overlay.check(r && t["mcp:github"] === "on:" + r.fp, "Turn on wrote her approval of this definition (" +
                        String(t["mcp:github"]).slice(0, 12) + "…)")
          overlay.check(r && r.on && r.choice === "on", "and the tab says it is on, her own")
          overlay.click(overlay.chip(overlay.row("gh · command-line tool"), "On"), "gh → On")
          break
        case 8:
          box = overlay.confirmBox()
          overlay.check(box && String(box.title).indexOf("gh") >= 0, "a CLI asks the same way")
          overlay.click(overlay.button(box, "Turn on"), "Turn on gh")
          break
        case 9:
          break
        case 10:
          t = overlay.soraTools()
          overlay.check(String(t["cli:gh"]).indexOf("on:") === 0, "gh is on for Sora (" + String(t["cli:gh"]).slice(0, 12) + "…)")
          r = overlay.detected("cli:gh")
          overlay.check(r && r.asks.indexOf("Asks before each command") === 0, "at Ask it says it asks first")
          overlay.click(overlay.chip(overlay.row("github · MCP server"), "Off"), "github → Off")
          break
        case 11:
          overlay.check(overlay.soraTools()["mcp:github"] === "off" && overlay.confirmBox() === null,
                        "Off is written at once, with no question")
          overlay.click(overlay.button(overlay.content(), "Dismiss"), "Dismiss the notice")
          break
        case 12:
          break
        case 13:
          d = overlay.details()
          overlay.check(d && d.catalog && (d.catalog.notice || []).length === 0, "the notice is gone after Dismiss")
          overlay.goTo("agentdetails", "hazel", "tools")
          break
        case 14:
          break
        case 15:
          r = overlay.detected("mcp:github")
          var fs2 = overlay.detected("mcp:filesystem")
          overlay.check(r && !r.can && r.why_not.indexOf("Claude Code") >= 0, "Hazel (Codex) cannot use a Claude Code server, and says why")
          overlay.check(fs2 && fs2.can && fs2.asks.indexOf("⚠") === 0, "her own Codex server can be switched, with the Trusted warning")
          overlay.goTo("agents", "sora", "tools")
          break
        case 16:
          var sw = overlay.find(overlay.content(), function(i) { return i.part === "tools" && i.detailsAsked !== undefined && i.foundOn !== undefined && i.program === "claude" && i.choices && i.choices["cli:gh"] !== undefined })
          overlay.check(sw && sw.foundOn === 1, "Sora's Agents card counts one found tool switched on (gh)")
          overlay.check(sw && overlay.find(sw, function(i) { return i.chipStates !== undefined }) === null, "and has no chips that write")
          overlay.click(sw ? overlay.button(sw, "Change on Agent details › Tools & skills") : null, "Change on Agent details")
          break
        case 17:
          overlay.check(overlay.page === "agentdetails" && overlay.detailsAgent === "sora" && overlay.detailsTab === "tools",
                        "the link opens her Tools & skills tab")
          overlay.goTo("communal", "", "tools")
          break
        case 18:
          break
        case 19:
          c = overlay.communal()
          overlay.check(c && c.toolList && c.toolList.tools.length === 6, "Communal → Tools lists the six found")
          var lin = overlay.find(overlay.content(), function(i) { return i.label === "linear · MCP server" && i.checked !== undefined })
          // The switch itself, as a click lands on it (ToggleSwitch).
          overlay.click(lin ? overlay.find(lin, function(i) { return i.trackWidth !== undefined && i.toggled !== undefined }) : null,
                        "linear → on for every agent")
          break
        case 20:
          box = overlay.confirmBox()
          text = box ? JSON.stringify(box.lines) : ""
          overlay.check(box && String(text).indexOf("mcp.linear.app") >= 0 && String(text).indexOf("PREVIEWFAKE") < 0,
                        "it asks, showing the URL and not the header's value")
          overlay.click(overlay.button(box, "Turn on for every agent"), "Turn on for every agent")
          break
        case 21:
          var st = overlay.setting("sharedTools", {})
          overlay.check(String(st["mcp:linear"]).indexOf("on:") === 0, "sharedTools has linear's approval (" + JSON.stringify(st).slice(0, 60) + ")")
          var field = overlay.find(overlay.content(), function(i) { return i.placeholderText === "e.g. rclone" })
          if (field) { field.text = "mytool"; field.accepted() }
          break
        case 22:
          break
        case 23:
          st = overlay.setting("sharedTools", {})
          overlay.check(st["cli:mytool"] === "off", "a CLI added by name is written off (" + JSON.stringify(st["cli:mytool"]) + ")")
          c = overlay.communal()
          var mine = c && c.toolList ? c.toolList.tools.filter(function(x) { return x.id === "cli:mytool" })[0] : null
          overlay.check(mine && mine.found === false, "and listed, not found on PATH")
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          Qt.quit()
          break
        }
      }
    }
  }
}
