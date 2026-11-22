// Screenshots of the Agents page (M5), one scene per shot, and a keyboard
// walk. PREVIEW_ARG is JSON:
//
//   {"width": 560}      draw the overlay that many pixels wide, as on a small screen (the
//                       overlay is min(880, screen) wide, so a cropped
//                       screenshot of a big screen is never the narrow layout)
//   {"keys": true}      no scenes: walk the page with Tab, Enter and Space only
//                       and log where the focus goes and what was written
//
//   preview.sh --config bench/preview/configs/agents8.json \
//     --state bench/preview/states/agents.json --size 1000x1000 \
//     --wait 6 --shots 9 --gap 2.5 --out /tmp/shot agentshots
//
// Scenes, one per shot: every agent shut; the main agent open, top and
// below; sora (an extra agent) open; the endpoint agent; the switched off
// one; the long name; Communal → Tools; and the 1-agent config's main agent
// when there is only the one.
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

    readonly property var arg: { try { return JSON.parse(Quickshell.env("PREVIEW_ARG") || "{}") } catch (e) { return {} } }
    readonly property real waitS: Number(Quickshell.env("PREVIEW_WAIT") || 3)
    readonly property real gapS: Number(Quickshell.env("PREVIEW_GAP") || 1.5)

    function log(m) { console.warn("PREVIEW " + m) }
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
    function findAll(item, test, out) {
      if (!item || item.visible === false) return out
      if (test(item)) out.push(item)
      var kids = item.children || []
      for (var i = 0; i < kids.length; i++) findAll(kids[i], test, out)
      return out
    }
    function content() { return overlay.pageScroll ? overlay.pageScroll.contentItem : null }
    function strip(id) { return find(content(), function(i) { return i.agentId === id && i.pg !== undefined }) }
    function cardOf() {
      var w = overlay.pageScroll ? overlay.pageScroll.Window.window : null
      return w ? find(w.contentItem, function(i) { return i.objectName === "settingsCard" }) : null
    }
    function only(id) {
      var page = find(content(), function(i) { return i.openCards !== undefined && i.setOpen !== undefined })
      if (!page) return
      var all = {}
      if (id !== "") all[id] = true
      page.openCards = all
    }
    function scrollTo(item, below) {
      var f = overlay.pageScroll
      if (!f) return
      var y = item ? item.mapToItem(f.contentItem, 0, 0).y : 0
      f.contentY = Math.max(0, Math.min(y + (below ? f.height * 0.8 : -8), f.contentHeight - f.height))
    }

    property int scene: -1
    readonly property var scenes: [
      function() { overlay.only(""); overlay.scrollTo(null, false); overlay.log("scene: every agent shut") },
      function() { overlay.only("main"); overlay.scrollTo(overlay.strip("main"), false); overlay.log("scene: main open") },
      function() { overlay.scrollTo(overlay.strip("main"), true); overlay.log("scene: main open, below") },
      function() { overlay.only("sora"); overlay.scrollTo(overlay.strip("sora"), false); overlay.log("scene: sora open") },
      function() { overlay.scrollTo(overlay.strip("sora"), true); overlay.log("scene: sora open, below") },
      function() { overlay.only("echo-local"); overlay.scrollTo(overlay.strip("echo-local"), false); overlay.log("scene: endpoint open") },
      function() { overlay.only("nova"); overlay.scrollTo(overlay.strip("nova"), false); overlay.log("scene: switched off, open") },
      function() { overlay.only("sage"); overlay.scrollTo(overlay.strip("sage"), false); overlay.log("scene: long name, open") },
      function() { overlay.goTo("communal", "", "tools"); overlay.log("scene: Communal → Tools") }
    ]

    // --- the keyboard walk ---------------------------------------------------
    function focused() { var w = overlay.pageScroll ? overlay.pageScroll.Window.window : null; return w ? w.activeFocusItem : null }
    function describe(i) {
      if (!i) return "none"
      var s = String(i).split("(")[0]
      if (i.label !== undefined && i.label !== "") s += " '" + i.label + "'"
      else if (i.text !== undefined && i.text !== "") s += " '" + String(i.text).slice(0, 30) + "'"
      else if (i.name !== undefined && i.name !== "") s += " '" + i.name + "'"
      for (var p = i.parent; p; p = p.parent) if (p.agentId !== undefined && p.pg !== undefined) { s += " in " + p.agentId; break }
      return s
    }
    property int keyStep: -1
    // TestEvent sends keys to the focus window, else to its parent item's
    // window. The preview's window is never the focus window, and the overlay
    // is not an item, so the one that sends keys lives inside the page.
    property var keyInput: null
    function keyEvents() {
      if (!keyInput) keyInput = Qt.createQmlObject("import QtTest; TestEvent {}", overlay.pageScroll.contentItem)
      return keyInput
    }
    function key(k, what) {
      keyEvents().keyClick(k, Qt.NoModifier, -1)
      Qt.callLater(function() { overlay.log("key " + what + " -> " + overlay.describe(overlay.focused())) })
    }
    readonly property var keySteps: {
      var out = []
      // The preview's window never takes the keyboard from the compositor,
      // so the walk starts by putting the focus on the main strip, as the
      // gallery's does; from there it is keys only.
      out.push(function() { overlay.only(""); overlay.strip("main").forceActiveFocus(); overlay.log("start on " + overlay.describe(overlay.focused())) })
      out.push(function() { overlay.key(Qt.Key_Return, "Enter (opens the main agent)") })
      for (var b = 0; b < 26; b++) out.push(function() { overlay.key(Qt.Key_Tab, "Tab") })
      // Onto the next strip, open it with Space, and flip its first tool chip.
      out.push(function() { overlay.tabTo(function(i) { return i.agentId === "sora" }, "sora's strip") })
      out.push(function() { overlay.key(Qt.Key_Space, "Space (opens sora)") })
      out.push(function() { overlay.tabTo(function(i) { return i.chipStates !== undefined }, "sora's tool chips") })
      out.push(function() { overlay.key(Qt.Key_Space, "Space (flips Desktop tools)") })
      out.push(function() { overlay.log("open: " + JSON.stringify(overlay.find(overlay.content(), function(i) { return i.openCards !== undefined }).openCards)) })
      out.push(function() { overlay.log("reached: " + overlay.reached.join(", ")) })
      return out
    }
    // Tab until the focus is inside something `test` accepts (at most 60).
    function tabTo(test, label) {
      function inside() {
        for (var i = overlay.focused(); i; i = i.parent) if (test(i)) return true
        return false
      }
      var n = 0
      for (; n < 60 && !inside(); n++) keyEvents().keyClick(Qt.Key_Tab, Qt.NoModifier, -1)
      overlay.log("tab to " + label + ": " + (inside() ? "reached in " + n : "NOT reached") + " -> " + overlay.describe(overlay.focused()))
    }
    property var reached: []
    function note() {
      var d = describe(focused())
      var short = d.split(" in ")[0]
      if (reached.indexOf(short) < 0) reached = reached.concat([short])
    }

    Timer {
      id: first
      interval: overlay.arg.keys ? 4000 : Math.max(1500, overlay.waitS * 1000 - 3500)
      running: true
      onTriggered: {
        if (overlay.arg.width) {
          var c = overlay.cardOf()
          if (c) { c.width = overlay.arg.width; overlay.log("overlay width " + c.width) }
        }
        if (overlay.arg.keys) { keys.start(); return }
        overlay.scene = 0
        overlay.scenes[0]()
        every.start()
      }
    }
    // Right after each of preview.sh's shots, as Scroller does: a change made
    // just before a shot did not always reach it.
    Timer {
      id: every
      interval: overlay.gapS * 1000
      repeat: true
      onTriggered: {
        if (++overlay.scene < overlay.scenes.length) overlay.scenes[overlay.scene]()
      }
    }
    Timer {
      id: keys
      interval: 400
      repeat: true
      onTriggered: {
        if (++overlay.keyStep >= overlay.keySteps.length) { stop(); overlay.log("DONE keys"); return }
        overlay.keySteps[overlay.keyStep]()
        Qt.callLater(overlay.note)
      }
    }
  }
}
