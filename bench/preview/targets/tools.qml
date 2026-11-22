// The tool switches and skills (merged plan, Phase 13), driven by synthetic
// clicks through the real settings store and the real `agentvoice agents`:
//
//   preview.sh --live-config --wait 80 --out /tmp/t tools
//   grep PREVIEW /tmp/t.log; cat /tmp/t.writes
//
// On the main agent's Tools card (M5: chips that cycle every agent → on →
// off), turns its browser on, off and back to "every agent" (watching
// mainTools and the Rule of Two warning), opens Sora from a deep link and
// turns her desktop tools off, checks a Codex agent's browser chip says why
// instead of switching, then reads Sora's Tools & skills tab (her switch,
// her own skill hiding the communal one of the same name) and Communal's
// Skills tab (a malformed skill listed with its problem). Synthetic skills
// only, in the scratch data folder; shell.json is a scratch copy.
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
      overlay.open('{"page":"agents","agent":"main"}')
    }

    TestEvent { id: input }

    property int passed: 0
    property int failed: 0
    function check(ok, what) {
      if (ok) passed++; else failed++
      console.warn("PREVIEW " + (ok ? "PASS " : "FAIL ") + what)
    }
    // Skips the hidden and the fully transparent (SegmentedChoice's
    // measuring copy of its chips, M5).
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
      input.mouseClick(item, item.width / 2, item.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
    }
    // An agent's strip on the Agents page (M5), by id; "main" for the main
    // agent.
    function card(id) {
      return find(content(), function(i) { return i.agentId === id && i.pg !== undefined })
    }
    function switches(id) {
      return find(card(id), function(i) { return i.part === "tools" && i.picked !== undefined })
    }
    function chips(sw) { return find(sw, function(i) { return i.chipStates !== undefined }) }
    function chip(sw, label) {
      return find(sw, function(i) { return i.clicked !== undefined && i.text !== undefined && String(i.text).indexOf(label) === 0 })
    }
    function toolsCard(id) { return find(card(id), function(i) { return i.title === "Tools" && i.highlighted !== undefined }) }
    // Clicks a chip until it reads `want` (the cycle is every agent → on →
    // off), one click per write.
    function clickTo(sw, key, label, want) {
      var order = ["inherit", "on", "off"]
      var now = chips(sw) ? chips(sw).stateOf(key) : ""
      var n = (order.indexOf(want) - order.indexOf(now) + 3) % 3
      for (var k = 0; k < n; k++) overlay.click(overlay.chip(sw, label), label + " → " + want)
    }
    function indexOf(id) {
      for (var i = 0; i < overlay.voiceAgents.length; i++)
        if (overlay.agentId(overlay.voiceAgents[i]) === id) return i
      return -1
    }
    function details() { return find(content(), function(i) { return i.previewParts !== undefined && i.pickTab !== undefined }) }
    function communal() { return find(content(), function(i) { return i.skillList !== undefined }) }

    // The folders, as the daemon makes them, then synthetic skills: one in
    // Communal, Sora's own of the same name, and a malformed communal one.
    Process {
      id: seed
      command: ["bash", "-c",
        'agentvoice agents migrate >/dev/null && d="$1" && ' +
        'mkdir -p "$d/communal/skills/greeting" "$d/communal/skills/broken" "$d/agents/sora/skills/greeting" && ' +
        'printf -- "---\\nname: greeting\\ndescription: Shared greeting.\\n---\\nSay hello.\\n" > "$d/communal/skills/greeting/SKILL.md" && ' +
        'printf -- "---\\nname: greeting\\ndescription: Sora greeting.\\n---\\nSay hi.\\n" > "$d/agents/sora/skills/greeting/SKILL.md" && ' +
        'printf "no front matter\\n" > "$d/communal/skills/broken/SKILL.md"',
        "seed", Quickshell.env("PREVIEW_DATA")]
      onRunningChanged: if (!running) overlay.folders.refresh()
    }

    property int step: 0
    property int warm: 0
    property string theoWarning: ""

    Timer {
      interval: 2000
      repeat: true
      running: true
      onTriggered: {
        if (!overlay.store.loaded || seed.running || ++overlay.warm < 3) return
        overlay.step++
        var sw, r, d, c
        switch (overlay.step) {
        case 1:
          c = overlay.card("main")
          overlay.check(c !== null && c.expanded, "the main agent is open")
          overlay.theoWarning = c ? c.warning : ""
          sw = overlay.switches("main")
          // Whatever the config starts with: the warning is there exactly when
          // the browser it has is on, at Trust everything, on Claude Code.
          overlay.check(c && sw && (c.warning !== "") === (sw.effective("browser") && c.level === "trusted" && c.program === "claude"),
                        "the Rule of Two warning shows exactly when its browser is on at Trust everything (" +
                        (c ? c.warning.slice(0, 40) : "") + ")")
          overlay.check(sw !== null && overlay.chips(sw) !== null, "its tool chips are on its Tools card")
          overlay.clickTo(sw, "browser", "Browser", "off")
          break
        case 2:
          var mt = overlay.setting("mainTools", {})
          overlay.check(mt && mt.browser === "off", "the chip writes mainTools.browser = off (" + JSON.stringify(mt) + ")")
          c = overlay.card("main")
          overlay.check(c && c.warning === "", "with its browser off the warning goes")
          sw = overlay.switches("main")
          overlay.check(sw && sw.source("browser") === "off, this agent's own", "the card says it is its own choice (" + (sw ? sw.source("browser") : "") + ")")
          overlay.clickTo(sw, "browser", "Browser", "inherit")
          break
        case 3:
          break
        case 4:
          mt = overlay.setting("mainTools", {})
          overlay.check(mt && mt.browser === undefined, "every agent removes the key (" + JSON.stringify(mt) + ")")
          c = overlay.card("main")
          overlay.check(c && (c.warning !== "") === (overlay.setting("browserTools", false) === true && c.level === "trusted" && c.program === "claude"),
                        "following every agent, the warning follows the browser for every agent")
          overlay.goTo("agents", "sora", "tools")
          break
        case 5:
          sw = overlay.switches("sora")
          overlay.check(sw && overlay.card("sora").expanded && overlay.toolsCard("sora").highlighted,
                        "the deep link opened Sora and marked her Tools card")
          overlay.clickTo(sw, "desktop", "Desktop tools", "off")
          break
        case 6:
          var i = overlay.indexOf("sora")
          var tools = i >= 0 ? (overlay.voiceAgents[i] || {}).tools : undefined
          overlay.check(tools && tools.desktop === "off", "the chip writes her entry's tools.desktop (" + JSON.stringify(tools) + ")")
          overlay.goTo("agents", "jarvis-ajc", "tools")
          break
        case 7:
          sw = overlay.switches("jarvis-ajc")
          var opts = sw && overlay.chips(sw) ? overlay.chips(sw).options : []
          var br = opts.filter(function(o) { return o.value === "browser" })[0]
          var dk = opts.filter(function(o) { return o.value === "desktop" })[0]
          overlay.check(br && String(br.disabledReason).indexOf("Only Claude Code") === 0,
                        "a Codex agent's browser chip says why instead of switching (" + (br ? br.disabledReason : "") + ")")
          overlay.check(dk && dk.disabledReason === "", "its desktop tools can be switched")
          overlay.goTo("agentdetails", "sora", "tools")
          break
        case 8:
          break                           // the catalog is read on a 250ms delay
        case 9:
          d = overlay.details()
          var cat = d ? d.catalog : null
          overlay.check(cat && cat.agent === "sora", "Sora's Tools & skills tab read her catalog")
          var desk = cat ? cat.tools.filter(function(t) { return t.key === "desktop" })[0] : null
          overlay.check(desk && desk.choice === "off" && desk.on === false, "it shows her desktop switch off, her own")
          var own = cat ? cat.skills.filter(function(s) { return s.source === "sora" && s.name === "greeting" })[0] : null
          var shared = cat ? cat.skills.filter(function(s) { return s.source === "communal" && s.name === "greeting" })[0] : null
          overlay.check(own && own.delivered && shared && shared.shadowed && !shared.delivered,
                        "her own skill hides the communal one of the same name")
          var line = overlay.find(overlay.content(), function(i) { return String(i.text).indexOf("Sora has its own of the same name") >= 0 })
          overlay.check(line !== null, "the tab says so")
          overlay.check(own && own.changed_outside === true, "a skill made by hand reads as changed outside Settings")
          overlay.click(overlay.find(overlay.content(), function(i) { return i.clicked !== undefined && i.text === "Keep" }), "Keep")
          break
        case 10:
          d = overlay.details()
          cat = d ? d.catalog : null
          own = cat ? cat.skills.filter(function(s) { return s.source === "sora" && s.name === "greeting" })[0] : null
          overlay.check(own && own.changed_outside === false && own.delivered, "Keep saved it, and the notice went")
          overlay.click(overlay.find(overlay.content(), function(i) { return i.clicked !== undefined && String(i.text).indexOf("Agents card") >= 0 }),
                        "Change on her Agents card")
          break
        case 11:
          overlay.check(overlay.page === "agents" && overlay.card("sora") && overlay.card("sora").expanded &&
                        overlay.toolsCard("sora").highlighted, "the link back opens her and marks her Tools card")
          overlay.goTo("communal", "", "skills")
          break
        case 12:
          break
        case 13:
          c = overlay.communal()
          var list = c ? (c.skillList || []) : []
          var broken = list.filter(function(s) { return s.name === "broken" })[0]
          overlay.check(broken && broken.problem.indexOf("front matter") >= 0, "Communal lists a malformed skill with its problem")
          var hid = overlay.find(overlay.content(), function(i) { return i.label === "greeting" && String(i.hint).indexOf("Not given to Sora") >= 0 })
          var g = overlay.find(overlay.content(), function(i) { return i.label === "greeting" && i.hint !== undefined })
          overlay.check(hid !== null, "and says Sora gets her own greeting instead (" + (g ? g.hint : "no row") + ")")
          overlay.goTo("agents", "sora", "tools")
          break
        case 14:
          c = overlay.card("sora")
          if (c) {
            overlay.pageScroll.contentY = Math.max(0, c.mapToItem(overlay.content(), 0, 0).y - 40)
            console.warn("PREVIEW click Sora's strip, to shut her")
            input.mouseClick(c, c.width / 2, 12, Qt.LeftButton, Qt.NoModifier, -1)
          }
          break
        case 15:
          overlay.check(overlay.card("sora") && !overlay.card("sora").expanded, "a click shuts her")
          overlay.goTo("agents", "sora", "tools")
          break
        case 16:
          overlay.check(overlay.card("sora") && overlay.card("sora").expanded,
                        "and the deep link opens her again")
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          Qt.quit()
          break
        }
      }
    }
  }
}
