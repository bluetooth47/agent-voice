// End to end on the Agents page, through real saves: run with --live-config
// so every write lands in a scratch shell.json and comes back through the
// store's reload, exactly as on the real shell.
//
//   preview.sh --live-config --wait 40 --out /tmp/a agents
//   grep PREVIEW /tmp/a.log
//
// Each check logs "PREVIEW PASS ..." or "PREVIEW FAIL ...", and the last line
// is "PREVIEW DONE n passed, m failed". It needs at least one extra agent in
// shell.json; it adds one if there is none (to the scratch copy only).
//
// What it is for: a card that shut itself after every save (the Repeater was
// handed a new array on any settings reload and rebuilt every card), and a
// dropdown that closed under you for the same reason. Those only show on the
// round trip, so a stubbed write could never catch them.
import QtQuick
import QtTest
import Quickshell
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    Component.onCompleted: overlay.open('{"page":"agents"}')

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
    function card(name) {
      return find(content(), function(i) { return i.isDefault !== undefined && i.expanded !== undefined && i.wakeName === name })
    }
    function mainCard() {
      return find(content(), function(i) { return i.isDefault === true && i.expanded !== undefined })
    }
    // A synthetic click lands wherever the item is on screen, so anything
    // below the fold is scrolled to first or the click hits nothing.
    function reveal(item) {
      var f = overlay.pageScroll
      if (!f || !item) return
      var y = item.mapToItem(f.contentItem, 0, 0).y
      f.contentY = Math.max(0, Math.min(y - 40, f.contentHeight - f.height))
    }
    function header(c, label) {
      reveal(c)
      console.warn("PREVIEW click " + label)
      input.mouseClick(c, c.width / 2, 14, Qt.LeftButton, Qt.NoModifier, -1)
    }
    function clickIn(root, text, label) {
      var b = find(root, function(i) { return i.text === text && i.clicked !== undefined })
      if (!b) { check(false, "found " + label); return false }
      reveal(b)
      console.warn("PREVIEW click " + label)
      input.mouseClick(b, b.width / 2, b.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
      return true
    }
    function rowIn(root, label) {
      return find(root, function(i) { return i.label === label && i.stacked !== undefined })
    }
    function dropdownIn(root) {
      return find(root, function(i) { return i.popupOpen !== undefined && i.options !== undefined })
    }

    property string extra: ""
    property var held: null
    property var heldDrop: null
    property int writesAt: 0
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
        case 2:
          if (overlay.voiceAgents.length === 0) {
            console.warn("PREVIEW adding an extra agent to the scratch config")
            overlay.put("voiceAgents", [{ name: "friday", agent: "claude", model: "", effort: "",
                                          voice: "", speed: 0, level: "ask", projectDir: "" }])
          }
          break
        case 4:
          overlay.extra = String(overlay.voiceAgents[0].name)
          var k = overlay.card(overlay.extra)
          overlay.check(k !== null, "the card for " + overlay.extra + " is drawn")
          if (!k) break
          if (!k.expanded) overlay.header(k, overlay.extra + " header")
          break
        case 5:
          var k5 = overlay.card(overlay.extra)
          overlay.check(k5 && k5.expanded, overlay.extra + " opens from its header")
          overlay.held = k5
          // An effort chip: a real save of voiceAgents.
          var target = k5 && k5.effort === "medium" ? "High" : "Medium"
          overlay.clickIn(k5, target, overlay.extra + " effort " + target)
          break
        case 8:
          var k8 = overlay.card(overlay.extra)
          var saved = overlay.voiceAgents[0] || {}
          overlay.check(saved.effort === "medium" || saved.effort === "high",
                        "the effort was saved and read back (" + saved.effort + ")")
          overlay.check(k8 && k8.expanded, overlay.extra + " is still open after the save")
          overlay.check(k8 === overlay.held, overlay.extra + "'s card was not rebuilt")
          overlay.clickIn(k8, "Its own", overlay.extra + " speed: its own")
          break
        case 11:
          var k11 = overlay.card(overlay.extra)
          var s11 = overlay.voiceAgents[0] || {}
          overlay.check(Number(s11.speed) >= 50, "its own speed was saved (" + s11.speed + ")")
          overlay.check(k11 && k11.expanded, overlay.extra + " still open after the speed save")
          var knob = overlay.find(k11, function(i) { return i.label === "Speed" && i.unit === "%" })
          overlay.check(knob !== null, "its speed slider is shown")
          // Open its voice dropdown, then save something unrelated.
          var vrow = overlay.rowIn(k11, "Voice")
          var d = vrow ? overlay.dropdownIn(vrow) : null
          overlay.check(d !== null, "its voice dropdown is drawn")
          if (d) { d.open(); overlay.heldDrop = d }
          break
        case 12:
          overlay.check(overlay.heldDrop && overlay.heldDrop.popupOpen, "the voice dropdown opened")
          overlay.put("chimes", overlay.setting("chimes", true) !== true)
          break
        case 15:
          overlay.check(overlay.heldDrop && overlay.heldDrop.popupOpen,
                        "the dropdown stayed open through an unrelated save")
          if (overlay.heldDrop) overlay.heldDrop.close()
          overlay.clickIn(overlay.card(overlay.extra), "Same as the main agent", "speed back to main")
          break
        case 18:
          var s18 = overlay.voiceAgents[0] || {}
          overlay.check(Number(s18.speed || 0) === 0, "speed back to following the main agent")
          // The main card: same settings, same order, on its own card.
          var m = overlay.mainCard()
          overlay.check(m !== null, "the main card is drawn")
          if (m && !m.expanded) overlay.header(m, "main header")
          break
        case 19:
          var m19 = overlay.mainCard()
          overlay.check(m19 && m19.expanded, "the main card opens from its header")
          var phrase = overlay.find(m19, function(i) { return i.label === "Wake phrase" && i.stacked !== undefined })
          overlay.check(phrase !== null, "the main card has its wake phrase")
          overlay.check(overlay.rowIn(m19, "Voice") !== null, "the main card has its voice")
          overlay.check(overlay.find(m19, function(i) { return i.label === "Speaking speed" && i.unit === "%" }) !== null,
                        "the main card has its speaking speed")
          var k19 = overlay.card(overlay.extra)
          overlay.check(k19 && k19.expanded, "opening main left " + overlay.extra + " open")
          overlay.held = m19
          var me = overlay.rowIn(m19, "Effort")
          var chips = me ? overlay.find(me, function(i) { return i.text === "Low" && i.clicked !== undefined && i.enabled }) : null
          if (chips) overlay.clickIn(me, "Low", "main effort Low")
          else {
            console.warn("PREVIEW (main effort not offered here; saving the main voice speed instead)")
            overlay.put("voiceSpeed", Number(overlay.setting("voiceSpeed", 100)) === 120 ? 110 : 120)
          }
          break
        case 22:
          var m22 = overlay.mainCard()
          overlay.check(m22 && m22.expanded, "the main card is still open after its save")
          overlay.check(overlay.card(overlay.extra) && overlay.card(overlay.extra).expanded,
                        overlay.extra + " is still open after a main-card save")
          // Shutting a card stays shut through a save.
          overlay.header(overlay.card(overlay.extra), overlay.extra + " header (close)")
          break
        case 23:
          overlay.put("voiceSpeed", Number(overlay.setting("voiceSpeed", 100)) === 130 ? 125 : 130)
          break
        case 26:
          var k26 = overlay.card(overlay.extra)
          overlay.check(k26 && !k26.expanded, overlay.extra + " stays shut through a save")
          overlay.check(Number(overlay.setting("voiceSpeed", 0)) >= 125, "main speed saved and read back")
          // The pages that used to hold these point here now.
          overlay.goTo("voice", "")
          break
        case 27:
          overlay.check(overlay.find(overlay.content(), function(i) { return i.label === "Voice and speed" }) !== null,
                        "the Voice page points to Agents for voice and speed")
          overlay.check(overlay.findAny(overlay.content(), function(i) { return i.label === "Speaking speed" }) === null,
                        "the Voice page has no second speed control")
          overlay.goTo("listening", "")
          break
        case 28:
          overlay.check(overlay.find(overlay.content(), function(i) { return i.label === "Wake phrase" && i.stacked !== undefined }) !== null,
                        "the Listening page points to Agents for the phrase")
          overlay.clickIn(overlay.content(), "Agents ›", "Listening → Agents")
          break
        case 29:
          overlay.check(overlay.page === "agents", "the link goes to the Agents page")
          var m29 = overlay.mainCard()
          overlay.check(m29 && m29.expanded, "and opens the main card")
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          break
        }
      }
    }
  }
}
