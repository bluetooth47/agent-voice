// The tool switches and skills (merged plan, Phase 13), driven by synthetic
// clicks through the real settings store and the real `agentvoice agents`:
//
//   preview.sh --live-config --wait 80 --out /tmp/t tools
//   grep PREVIEW /tmp/t.log; cat /tmp/t.writes
//
// Opens the main card's "Tools & collaboration", turns its browser off and
// back to "same as every agent" (watching mainTools and the Rule of Two
// warning), opens Sora's group from a deep link and turns her desktop tools
// off, checks a Codex agent's browser row says why instead of offering a
// switch, then reads Sora's Tools & skills tab (her switch, her own skill
// hiding the communal one of the same name) and Communal's Skills tab (a
// malformed skill listed with its problem). Synthetic skills only, in the
// scratch data folder; shell.json is a scratch copy.
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
    function find(item, test) {
      if (!item) return null
      if (item.visible !== false && test(item)) return item
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
    function card(id) {
      return find(content(), function(i) {
        return i.switchedOff !== undefined && (id === "main" ? i.isDefault === true : i.agentId === id)
      })
    }
    function switches(id) {
      return find(card(id), function(i) { return i.globals !== undefined && i.picked !== undefined })
    }
    function header(sw) {
      return find(sw, function(i) { return i.clicked !== undefined && String(i.text).indexOf("Tools & collaboration") >= 0 })
    }
    function row(sw, label) {
      return find(sw, function(i) { return i.label === label && i.reset !== undefined && i.why !== undefined })
    }
    function chip(sw, label, text) {
      return find(row(sw, label), function(i) { return i.clicked !== undefined && i.text === text })
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
          overlay.check(c !== null, "the main card is open")
          overlay.theoWarning = c ? c.warning : ""
          overlay.check(c && (c.warning !== "") === (overlay.setting("browserTools", false) === true),
                        "the Rule of Two warning shows exactly when its browser is on at Trust everything (" +
                        (c ? c.warning.slice(0, 40) : "") + ")")
          sw = overlay.switches("main")
          overlay.check(sw && !sw.expanded && overlay.row(sw, "Browser") === null, "its tool switches start shut")
          overlay.click(overlay.header(sw), "the main card's Tools header")
          break
        case 2:
          sw = overlay.switches("main")
          overlay.check(sw && sw.expanded && overlay.row(sw, "Browser") !== null, "clicking the header opens them")
          overlay.click(overlay.chip(sw, "Browser", "Off"), "main Browser Off")
          break
        case 3:
          var mt = overlay.setting("mainTools", {})
          overlay.check(mt && mt.browser === "off", "Off writes mainTools.browser = off (" + JSON.stringify(mt) + ")")
          c = overlay.card("main")
          overlay.check(c && c.warning === "", "with its browser off the warning goes")
          sw = overlay.switches("main")
          r = overlay.row(sw, "Browser")
          overlay.check(r && r.changed && r.hint.indexOf("Off for this agent") === 0, "the row says it is its own choice (" + (r ? r.hint : "") + ")")
          overlay.click(overlay.chip(sw, "Browser", "Same as every agent"), "main Browser inherit")
          break
        case 4:
          mt = overlay.setting("mainTools", {})
          overlay.check(mt && mt.browser === undefined, "Same as every agent removes the key (" + JSON.stringify(mt) + ")")
          c = overlay.card("main")
          overlay.check(c && c.warning === overlay.theoWarning, "the warning is back as it was")
          overlay.goTo("agents", "sora", "tools")
          break
        case 5:
          sw = overlay.switches("sora")
          overlay.check(sw && sw.expanded, "the deep link opened Sora's card and her tool switches")
          overlay.click(overlay.chip(sw, "Desktop tools", "Off"), "Sora Desktop Off")
          break
        case 6:
          var i = overlay.indexOf("sora")
          var tools = i >= 0 ? (overlay.voiceAgents[i] || {}).tools : undefined
          overlay.check(tools && tools.desktop === "off", "Off writes her entry's tools.desktop (" + JSON.stringify(tools) + ")")
          overlay.goTo("agents", "jarvis-ajc", "tools")
          break
        case 7:
          sw = overlay.switches("jarvis-ajc")
          r = sw ? overlay.row(sw, "Browser") : null
          overlay.check(r && r.why.indexOf("Only Claude Code") === 0 && overlay.chip(sw, "Browser", "On") === null,
                        "a Codex agent's browser row says why instead of offering a switch (" + (r ? r.why : "") + ")")
          overlay.check(overlay.chip(sw, "Desktop tools", "On") !== null, "its desktop tools can be switched")
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
          overlay.check(overlay.page === "agents" && overlay.switches("sora") && overlay.switches("sora").expanded,
                        "the link back opens her card's tool switches")
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
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          Qt.quit()
          break
        }
      }
    }
  }
}
