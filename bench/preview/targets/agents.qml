// End to end on the Agents page, through real saves: run with a scratch
// config so every write lands in a scratch shell.json and comes back through
// the store's reload, exactly as on the real shell.
//
//   preview.sh --config bench/preview/configs/agents8.json \
//     --state bench/preview/states/agents.json --wait 60 --out /tmp/a agents
//   grep PREVIEW /tmp/a.log
//
// Each check logs "PREVIEW PASS ..." or "PREVIEW FAIL ...", and the last line
// is "PREVIEW DONE n passed, m failed". It expects the agents8 config (sora,
// hazel, echo-local, nova, atlas, max, sage); --live-config with the real
// shell.json works too if it has a "sora".
//
// What it is for: an agent that shut itself after every save (the Repeater
// was handed a new array on any settings reload and rebuilt every block), a
// dropdown that closed under you for the same reason, and -- since M5 --
// that a save of one agent leaves every other agent's entry exactly as it
// was. Those only show on the round trip, so a stubbed write could never
// catch them.
import QtQuick
import QtTest
import Quickshell
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    Component.onCompleted: overlay.open('{"page":"agents","agent":"sora"}')

    TestEvent { id: input }

    property int passed: 0
    property int failed: 0
    function check(ok, what) {
      if (ok) passed++; else failed++
      console.warn("PREVIEW " + (ok ? "PASS " : "FAIL ") + what)
    }

    // Skips what cannot be seen or clicked: hidden items, and anything fully
    // transparent (SegmentedChoice's measuring copy of its chips).
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
    // Hidden ones too: for asking whether something is there but not shown.
    function findAny(item, test) {
      if (!item) return null
      if (test(item)) return item
      var kids = item.children || []
      for (var i = 0; i < kids.length; i++) {
        var hit = findAny(kids[i], test)
        if (hit) return hit
      }
      return null
    }
    function content() { return overlay.pageScroll ? overlay.pageScroll.contentItem : null }
    // An agent's strip, by id ("main" for the main agent).
    function strip(id) {
      return find(content(), function(i) { return i.agentId === id && i.pills !== undefined && i.pg !== undefined })
    }
    function cardIn(root, title) {
      return find(root, function(i) { return i.title === title && i.highlighted !== undefined })
    }
    // A synthetic click lands wherever the item is on screen, so anything
    // below the fold is scrolled to first or the click hits nothing.
    function reveal(item) {
      var f = overlay.pageScroll
      if (!f || !item) return
      var y = item.mapToItem(f.contentItem, 0, 0).y
      f.contentY = Math.max(0, Math.min(y - 40, f.contentHeight - f.height))
    }
    function header(st, label) {
      reveal(st)
      console.warn("PREVIEW click " + label)
      input.mouseClick(st, st.width / 2, 12, Qt.LeftButton, Qt.NoModifier, -1)
    }
    function clickItem(b, label) {
      if (!b) { check(false, "found " + label); return false }
      reveal(b)
      console.warn("PREVIEW click " + label)
      input.mouseClick(b, b.width / 2, b.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
      return true
    }
    function clickIn(root, text, label) {
      return clickItem(find(root, function(i) { return i.text === text && i.clicked !== undefined }), label)
    }
    function rowIn(root, label) {
      return find(root, function(i) { return i.label === label && i.stacked !== undefined })
    }
    function dropdownIn(root) {
      return find(root, function(i) { return i.popupOpen !== undefined && i.options !== undefined })
    }
    function selectorIn(root, label) {
      return find(root, function(i) { return i.label === label && i.placeholder !== undefined && i.committed !== undefined })
    }
    // The MenuList a CompactSelector opens: a Popup, so in `data`, not
    // `children`.
    function menuOf(sel) {
      var d = sel ? sel.data : []
      for (var i = 0; i < d.length; i++) if (d[i] && d[i].entries !== undefined && d[i].choose !== undefined) return d[i]
      return null
    }
    // Opens the selector with a real click, then chooses through the menu's
    // own choose(), which is what a click on an entry calls.
    property var pending: null
    function openSelector(root, label) {
      var sel = selectorIn(root, label)
      if (!clickItem(sel, label + " selector")) return
      pending = sel
    }
    function choose(value, label) {
      var m = menuOf(pending)
      check(m !== null && m.opened, label + ": the menu opened")
      if (!m) return
      for (var i = 0; i < m.entries.length; i++) {
        var e = m.entries[i]
        if (String((e !== null && typeof e === "object") ? e.value : e) === value) { m.choose(i); return }
      }
      check(false, label + ": " + value + " is offered")
    }
    function agent(id) {
      for (var i = 0; i < overlay.voiceAgents.length; i++)
        if (overlay.agentId(overlay.voiceAgents[i]) === id) return overlay.voiceAgents[i]
      return null
    }

    property var before: ({})
    property var held: null
    property var heldDrop: null
    property int step: 0
    // Ticks after the settings first loaded: a click sent while the overlay
    // is still coming up lands on nothing.
    property int warm: 0

    Timer {
      interval: 1500
      repeat: true
      running: true
      onTriggered: {
        if (!overlay.store.loaded || ++overlay.warm < 3) return
        overlay.step++
        var c = overlay.content()
        switch (overlay.step) {
        case 1:
          // Every entry as it was, to compare at the end.
          var b = {}
          for (var i = 0; i < overlay.voiceAgents.length; i++)
            b[overlay.agentId(overlay.voiceAgents[i])] = JSON.stringify(overlay.voiceAgents[i])
          overlay.before = b
          var k = overlay.strip("sora")
          overlay.check(k !== null, "sora's strip is drawn")
          overlay.check(k && k.expanded, "the deep link opened sora")
          overlay.check(overlay.strip("main") && !overlay.strip("main").expanded, "the main agent starts shut")
          overlay.check(k && k.pills.length >= 3, "sora's strip has its pills (" + (k ? k.pills.map(function(p) { return p.text }).join(" | ") : "") + ")")
          for (var t of ["Identity", "Permissions", "Voice", "Tools", "Collaboration & notes", "Agent"])
            overlay.check(overlay.cardIn(k, t) !== null, "sora has its " + t + " card")
          overlay.check(overlay.cardIn(k, "Endpoint") === null, "and no Endpoint card")
          overlay.held = k
          overlay.openSelector(overlay.cardIn(k, "Identity"), "Effort")
          break
        case 2:
          var target = (overlay.agent("sora") || {}).effort === "high" ? "low" : "high"
          overlay.choose(target, "sora effort " + target)
          break
        case 4:
          var k4 = overlay.strip("sora")
          var saved = overlay.agent("sora") || {}
          overlay.check(saved.effort === "high" || saved.effort === "low",
                        "the effort was saved and read back (" + saved.effort + ")")
          overlay.check(k4 && k4.expanded, "sora is still open after the save")
          overlay.check(k4 === overlay.held, "sora's strip was not rebuilt")
          overlay.clickIn(overlay.cardIn(k4, "Voice"), "Its own", "sora speed: its own")
          break
        case 7:
          var k7 = overlay.strip("sora")
          var s7 = overlay.agent("sora") || {}
          overlay.check(Number(s7.speed) >= 50, "its own speed was saved (" + s7.speed + ")")
          overlay.check(k7 && k7.expanded, "sora still open after the speed save")
          var knob = overlay.find(k7, function(i) { return i.label === "Speed" && i.unit === "%" })
          overlay.check(knob !== null, "its speed slider is shown")
          // Open its voice dropdown, then save something unrelated.
          var d = overlay.dropdownIn(overlay.rowIn(overlay.cardIn(k7, "Voice"), "Voice"))
          overlay.check(d !== null, "its voice dropdown is drawn")
          if (d) { d.open(); overlay.heldDrop = d }
          break
        case 8:
          overlay.check(overlay.heldDrop && overlay.heldDrop.popupOpen, "the voice dropdown opened")
          overlay.put("chimes", overlay.setting("chimes", true) !== true)
          break
        case 11:
          overlay.check(overlay.heldDrop && overlay.heldDrop.popupOpen,
                        "the dropdown stayed open through an unrelated save")
          if (overlay.heldDrop) overlay.heldDrop.close()
          overlay.clickIn(overlay.cardIn(overlay.strip("sora"), "Voice"), "Same as the main agent", "speed back to main")
          break
        case 14:
          overlay.check(Number((overlay.agent("sora") || {}).speed || 0) === 0, "speed back to following the main agent")
          // A tool chip: sora's desktop tools are "on"; one click is "off".
          overlay.clickIn(overlay.cardIn(overlay.strip("sora"), "Tools"), "Desktop tools", "sora desktop tools chip")
          break
        case 17:
          var t17 = (overlay.agent("sora") || {}).tools || {}
          overlay.check(t17.desktop === "off", "the chip saved desktop: off (" + JSON.stringify(t17) + ")")
          overlay.check(overlay.strip("sora") === overlay.held, "and sora's strip was not rebuilt")
          var m = overlay.strip("main")
          overlay.check(m !== null, "the main strip is drawn")
          if (m && !m.expanded) overlay.header(m, "main header")
          break
        case 18:
          var m18 = overlay.strip("main")
          overlay.check(m18 && m18.expanded, "the main agent opens from its header")
          var phrase = overlay.rowIn(overlay.cardIn(m18, "Identity"), "Wake phrase")
          overlay.check(phrase !== null, "the main agent has its wake phrase")
          overlay.check(overlay.rowIn(overlay.cardIn(m18, "Voice"), "Voice") !== null, "the main agent has its voice")
          overlay.check(overlay.find(m18, function(i) { return i.label === "Speaking speed" && i.unit === "%" }) !== null,
                        "the main agent has its speaking speed")
          overlay.check(overlay.strip("sora") && overlay.strip("sora").expanded, "opening main left sora open")
          overlay.held = m18
          overlay.openSelector(overlay.cardIn(m18, "Identity"), "Effort")
          break
        case 19:
          overlay.choose("low", "main effort low")
          break
        case 21:
          var m21 = overlay.strip("main")
          var eff = overlay.setting("agentEfforts", {})
          overlay.check(eff && eff.claude === "low", "the main effort was saved per program (" + JSON.stringify(eff) + ")")
          overlay.check(m21 && m21.expanded && m21 === overlay.held, "the main agent is still open, not rebuilt")
          overlay.check(overlay.strip("sora") && overlay.strip("sora").expanded, "sora is still open after a main save")
          // Shutting one stays shut through a save.
          overlay.header(overlay.strip("sora"), "sora header (close)")
          break
        case 22:
          overlay.put("voiceSpeed", Number(overlay.setting("voiceSpeed", 100)) === 130 ? 125 : 130)
          break
        case 25:
          overlay.check(overlay.strip("sora") && !overlay.strip("sora").expanded, "sora stays shut through a save")
          overlay.check(Number(overlay.setting("voiceSpeed", 0)) >= 125, "main speed saved and read back")
          // The endpoint agent: its own card, no permissions.
          var e = overlay.strip("echo-local")
          if (e && !e.expanded) overlay.header(e, "echo header")
          break
        case 26:
          var e26 = overlay.strip("echo-local")
          overlay.check(e26 && e26.expanded, "the endpoint agent opens")
          overlay.check(overlay.cardIn(e26, "Endpoint") !== null, "it has the Endpoint card")
          overlay.check(overlay.cardIn(e26, "Permissions") === null, "and no Permissions card")
          var chip = overlay.find(overlay.cardIn(e26, "Tools"), function(i) { return i.text !== undefined && String(i.text).indexOf("Desktop tools") === 0 })
          overlay.check(chip !== null && chip.opacity < 1, "its tool chips are drawn disabled, not hidden")
          // The deep link for tools marks that agent's Tools card.
          overlay.goTo("agents", "hazel", "tools")
          break
        case 27:
          var h = overlay.strip("hazel")
          overlay.check(h && h.expanded, "the tools deep link opened hazel")
          overlay.check(h && overlay.cardIn(h, "Tools").highlighted, "and marked its Tools card")
          overlay.clickIn(overlay.content(), "For every agent: Communal → Tools ›", "hazel's Tools card link")
          break
        case 28:
          overlay.check(overlay.page === "communal" && overlay.communalTab === "tools", "the link opens Communal → Tools")
          var row = overlay.find(overlay.content(), function(i) { return i.label === "Desktop tools" && i.checked !== undefined })
          overlay.check(row !== null, "Communal → Tools has the desktop tools switch")
          overlay.held = overlay.setting("desktopTools", false)
          var sw = row ? overlay.find(row, function(i) { return i.trackWidth !== undefined && i.toggled !== undefined }) : null
          overlay.clickItem(sw, "desktop tools for every agent")
          break
        case 31:
          overlay.check(overlay.setting("desktopTools", false) === !overlay.held, "desktopTools was written from Communal")
          overlay.goTo("agents", "")
          break
        case 32:
          overlay.check(overlay.findAny(overlay.content(), function(i) { return i.title === "ON THE DESKTOP" }) === null,
                        "the Agents page has no \"On the desktop\" group")
          // Nobody but sora was touched; sora lost nothing it did not change.
          var after = {}
          for (var j = 0; j < overlay.voiceAgents.length; j++)
            after[overlay.agentId(overlay.voiceAgents[j])] = overlay.voiceAgents[j]
          for (var id in overlay.before) {
            if (id === "sora") continue
            overlay.check(JSON.stringify(after[id]) === overlay.before[id], id + "'s entry is byte for byte as it was")
          }
          var was = JSON.parse(overlay.before["sora"] || "{}")
          var now = after["sora"] || {}
          var lost = Object.keys(was).filter(function(key) { return !(key in now) })
          overlay.check(lost.length === 0, "sora kept every field (" + (lost.join(", ") || "none lost") + ")")
          overlay.check(JSON.stringify(now.futureField) === JSON.stringify(was.futureField),
                        "including a field this build does not know")
          overlay.goTo("listening", "")
          break
        case 33:
          overlay.check(overlay.find(overlay.content(), function(i) { return i.label === "Wake phrase" && i.stacked !== undefined }) !== null,
                        "the Listening page points to Agents for the phrase")
          overlay.clickIn(overlay.content(), "Agents ›", "Listening → Agents")
          break
        case 34:
          overlay.check(overlay.page === "agents", "the link goes to the Agents page")
          var m34 = overlay.strip("main")
          overlay.check(m34 && m34.expanded, "and opens the main agent")
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          break
        }
      }
    }
  }
}
