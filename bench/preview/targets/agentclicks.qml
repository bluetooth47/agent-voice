// The same actions on the Agents page, old layout or new, logging what each
// one wrote: the M5 "clicks diff". Run it on two trees from the same config
// and diff the two <out>.writes files; the redesign is the same settings
// organised, so the writes must be the same keys and values in the same
// order.
//
//   preview.sh --config bench/preview/configs/agents8.json \
//     --state bench/preview/states/agents.json --wait 75 --out /tmp/new agentclicks
//   (the same from a checkout of the old tree, with this file copied in)
//   diff /tmp/old.writes /tmp/new.writes
//
// Each action finds its control by what a person reads (a row's label, a
// chip's text) and clicks it with a synthetic mouse event. Two things are
// not clicked: a Dropdown's popup (both layouts use Omarchy's Dropdown, so
// its `changed` signal is emitted directly, the same way on both sides), and
// an entry in a CompactSelector's menu, which is chosen through the menu's
// own choose() -- what a click on the entry calls. A text field gets its text
// and then editingFinished(), as Enter would.
//
// It knows the layout by what it finds: AgentCards (before M5) or header
// strips with cards (M5).
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

    function log(m) { console.warn("PREVIEW " + m) }
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
    function content() { return overlay.pageScroll ? overlay.pageScroll.contentItem : null }
    // Decided once the page is drawn (a binding would be read before it is).
    property bool newLayout: false

    // id: "main" or an agent id; wake: what the old card shows as wakeName.
    function agentRoot(id, wake) {
      if (newLayout) return find(content(), function(i) { return i.agentId === id && i.pg !== undefined })
      if (id === "main") return find(content(), function(i) { return i.isDefault === true && i.expanded !== undefined })
      return find(content(), function(i) { return i.isDefault === false && i.wakeName === wake && i.expanded !== undefined })
    }
    // A card on the new layout; the whole agent on the old one.
    function section(root, title) {
      if (!newLayout || !root) return root
      return find(root, function(i) { return i.title === title && i.highlighted !== undefined })
    }
    function reveal(item) {
      var f = overlay.pageScroll
      if (!f || !item) return
      var y = item.mapToItem(f.contentItem, 0, 0).y
      f.contentY = Math.max(0, Math.min(y - 60, f.contentHeight - f.height))
    }
    function clickItem(b, label) {
      if (!b) { log("MISS " + label); return }
      reveal(b)
      log("click " + label)
      input.mouseClick(b, b.width / 2, b.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
    }
    function unfold(root, label) {
      if (!root) { log("MISS " + label); return }
      if (root.expanded) return
      reveal(root)
      log("open " + label)
      input.mouseClick(root, root.width / 2, 12, Qt.LeftButton, Qt.NoModifier, -1)
    }
    function row(root, label) {
      return find(root, function(i) { return i.label === label && i.stacked !== undefined })
    }
    function chip(root, rowLabel, text, label) {
      var r = rowLabel === "" ? root : row(root, rowLabel)
      clickItem(find(r, function(i) { return i.text === text && i.clicked !== undefined }), label)
    }
    function type(root, rowLabel, text, label) {
      var f = find(row(root, rowLabel), function(i) { return i.placeholderText !== undefined && i.editingFinished !== undefined })
      if (!f) { log("MISS " + label); return }
      reveal(f)
      log("type " + label)
      f.forceActiveFocus()
      f.text = text
      f.editingFinished()
    }
    function pickDropdown(root, rowLabel, value, label) {
      var d = find(row(root, rowLabel), function(i) { return i.popupOpen !== undefined && i.options !== undefined })
      if (!d) { log("MISS " + label); return }
      log("pick " + label)
      d.changed(value)
    }
    property var pendingSel: null
    function selector(root, selLabel, label) {
      var sel = find(root, function(i) { return i.label === selLabel && i.placeholder !== undefined && i.committed !== undefined })
      pendingSel = sel
      clickItem(sel, label)
    }
    function chooseOpen(value, label) {
      var d = pendingSel ? pendingSel.data : []
      for (var i = 0; i < d.length; i++) {
        var m = d[i]
        if (!m || m.entries === undefined || m.choose === undefined) continue
        for (var j = 0; j < m.entries.length; j++) {
          var e = m.entries[j]
          if (String((e !== null && typeof e === "object") ? e.value : e) === value) { log("choose " + label); m.choose(j); return }
        }
      }
      log("MISS " + label)
    }
    // The old layout's tools and collaboration were in a group that starts
    // shut.
    function openToolGroup(root) {
      if (newLayout) return
      var b = find(root, function(i) { return i.text !== undefined && String(i.text).indexOf("▸  Tools & collaboration") === 0 && i.clicked !== undefined })
      if (b) clickItem(b, "open the tools group")
    }
    function effort(root, value, chipText, label, phase) {
      if (newLayout) {
        if (phase === 0) selector(section(root, "Identity"), "Effort", label)
        else chooseOpen(value, label)
      } else if (phase === 0) chip(root, "Effort", chipText, label)
    }
    function model(root, value, label, phase) {
      if (newLayout) {
        if (phase === 0) selector(section(root, "Identity"), "Model", label)
        else chooseOpen(value, label)
      } else if (phase === 0) pickDropdown(root, "Model", value, label)
    }
    function main_() { return agentRoot("main", "") }
    function sora() { return agentRoot("sora", "sora") }

    // One entry per tick; a function gets the layout's answer to "where".
    readonly property var steps: [
      function() { unfold(main_(), "main") },
      function() { type(section(main_(), "Identity"), "Name", "Theodore", "main name") },
      function() { effort(main_(), "medium", "Medium", "main effort medium", 0) },
      function() { effort(main_(), "medium", "Medium", "main effort medium", 1) },
      function() { model(main_(), "sonnet", "main model sonnet", 0) },
      function() { model(main_(), "sonnet", "main model sonnet", 1) },
      function() { chip(section(main_(), "Permissions"), newLayout ? "Level" : "Permission", "Ask first", "main level ask") },
      function() { chip(section(main_(), "Permissions"), newLayout ? "Level" : "Permission", "Trust everything", "main level trusted") },
      function() { chip(section(main_(), "Permissions"), "", "Trust it", "main trust confirmed") },
      function() { pickDropdown(section(main_(), "Voice"), "Voice", "ryan-medium", "main voice ryan") },
      function() { openToolGroup(main_()) },
      function() {
        if (newLayout) clickItem(find(section(main_(), "Tools"), function(i) { return i.text !== undefined && String(i.text).indexOf("Browser") === 0 && i.clicked !== undefined }), "main browser → every agent")
        else chip(main_(), "Browser", "Same as every agent", "main browser → every agent")
      },
      function() { chip(section(main_(), "Collaboration & notes"), "Notes", "Read only", "main notes read only") },
      function() { chip(section(main_(), "Collaboration & notes"), "Collaboration", "Quietly", "main collaboration quietly") },
      function() { chip(section(main_(), "Collaboration & notes"), "Takes work from agents", "Questions only", "main questions only") },
      function() { type(section(main_(), "Permissions"), "Project folder", "~/Projects/other", "main project folder") },
      function() { unfold(sora(), "sora") },
      function() { type(section(sora(), "Identity"), "Name", "Sora Two", "sora name") },
      function() { effort(sora(), "high", "High", "sora effort high", 0) },
      function() { effort(sora(), "high", "High", "sora effort high", 1) },
      function() { chip(section(sora(), "Permissions"), newLayout ? "Level" : "Permission", "Edits are fine", "sora level edits") },
      function() { pickDropdown(section(sora(), "Voice"), "Voice", "joe-medium", "sora voice joe") },
      function() { chip(section(sora(), "Voice"), "Speaking speed", "Its own", "sora speed own") },
      function() { openToolGroup(sora()) },
      function() {
        if (newLayout) clickItem(find(section(sora(), "Tools"), function(i) { return i.text !== undefined && String(i.text).indexOf("Desktop tools") === 0 && i.clicked !== undefined }), "sora desktop off")
        else chip(sora(), "Desktop tools", "Off", "sora desktop off")
      },
      function() { chip(section(sora(), "Collaboration & notes"), "Collaboration", "Announce", "sora collaboration announce") },
      function() { chip(section(sora(), "Collaboration & notes"), "Notes", "May write", "sora notes may write") },
      function() { chip(section(sora(), "Collaboration & notes"), "Takes work from agents", "Yes", "sora takes work") },
      function() { chip(section(sora(), "Voice"), "Talk while it works", "Brief", "sora narration brief") },
      function() { unfold(agentRoot("nova", "nova"), "nova") },
      function() {
        var r = find(section(agentRoot("nova", "nova"), "Agent"), function(i) { return i.label === "On" && i.checked !== undefined })
        clickItem(r ? find(r, function(i) { return i.trackWidth !== undefined && i.toggled !== undefined }) : null, "nova on")
      },
      function() { unfold(agentRoot("hazel", "hazel"), "hazel") },
      function() { pickDropdown(section(agentRoot("hazel", "hazel"), "Identity"), "Runs on", "claude", "hazel runs on claude") },
      function() { if (newLayout) overlay.goTo("communal", "", "tools") },
      function() {
        // The old page's switch for every agent is a ToggleRow; the agents'
        // own rows were SettingRows, which have no `checked`.
        var r = find(content(), function(i) { return i.label === "Desktop tools" && i.checked !== undefined })
        clickItem(r ? find(r, function(i) { return i.trackWidth !== undefined && i.toggled !== undefined }) : null, "desktop tools for every agent")
      },
      function() { log("DONE " + (newLayout ? "new" : "old") + " layout") }
    ]

    property int step: -1
    property int warm: 0
    Timer {
      interval: 1500
      repeat: true
      running: true
      onTriggered: {
        if (!overlay.store.loaded || ++overlay.warm < 3) return
        if (overlay.store.busy) return
        overlay.step++
        if (overlay.step === 0) {
          overlay.newLayout = overlay.find(overlay.content(), function(i) { return i.pills !== undefined && i.pg !== undefined }) !== null
          overlay.log("layout: " + (overlay.newLayout ? "new" : "old"))
        }
        if (overlay.step < overlay.steps.length) overlay.steps[overlay.step]()
      }
    }
  }
}
