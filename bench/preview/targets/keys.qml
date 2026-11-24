// The keyboard-only pass (master plan M29): every page and tab walked with
// Tab alone, in the real overlay, the pointer never touched.
//
//   preview.sh --config bench/preview/configs/agents8.json --state \
//     bench/preview/states/showcase.json --scratch-data --size 1100x760 \
//     --wait 150 --out /tmp/keys keys
//   grep PREVIEW /tmp/keys.log; cat /tmp/keys.writes
//
// For each page it presses Tab until the focus comes round to where it
// started (or 400 presses) and checks, of everything the page draws that
// says it takes Tab focus (shown, enabled):
//   - each one was reached (an action nobody can Tab to is pointer-only);
//   - each thing reached has a name a screen reader can say;
//   - the page scrolled so the focused thing is in view (Settings.qml's
//     followFocus), every time;
//   - and how often the order went back up the page, which is logged
//     (a row's controls read left to right, so "up" means a jump back of
//     more than a line).
// Tabbing presses nothing, so the write log must stay empty.
//
// --arg: a page id (or "page/tab") to walk only that one; "shot" stops on
// the third focus stop of the Conversation page for a screenshot of what
// focus looks like.
import QtQuick
import QtTest
import Quickshell
import Quickshell.Io
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    Component.onCompleted: overlay.open('{"page":"overview"}')

    readonly property string want: Quickshell.env("PREVIEW_ARG") || ""
    readonly property var plan: {
      var all = [["overview"], ["agents"], ["agentdetails", "main", "prompt"], ["agentdetails", "main", "tools"],
                 ["agentdetails", "main", "notes"], ["agentdetails", "main", "chats"], ["agentdetails", "main", "advanced"],
                 ["communal", "", "rules"], ["communal", "", "who"], ["communal", "", "preview"], ["communal", "", "tools"],
                 ["communal", "", "skills"], ["communal", "", "notes"], ["communal", "", "chats"],
                 ["crew"], ["chats"], ["listening"], ["conversation"], ["voice"], ["other"], ["about"]]
      if (want === "" || want === "shot") return want === "shot" ? [["conversation"]] : all
      var out = []
      for (var i = 0; i < all.length; i++) {
        var id = all[i][0] + (all[i][2] ? "/" + all[i][2] : "")
        if (id === want || all[i][0] === want) out.push(all[i])
      }
      return out
    }

    property var keys: null
    function keyEvents() {
      if (!overlay.keys) overlay.keys = Qt.createQmlObject("import QtTest; TestEvent {}", overlay.pageScroll.contentItem)
      return overlay.keys
    }
    function key(k, mods) { keyEvents().keyClick(k, mods === undefined ? Qt.NoModifier : mods, -1) }

    property int passed: 0
    property int failed: 0
    function check(ok, what) {
      if (ok) passed++; else failed++
      console.warn("PREVIEW " + (ok ? "PASS " : "FAIL ") + what)
    }
    function windowRoot() {
      var i = overlay.pageScroll
      while (i && i.parent) i = i.parent
      return i
    }
    function findIn(item, test) {
      if (!item) return null
      if (test(item)) return item
      var kids = item.children || []
      for (var i = 0; i < kids.length; i++) {
        var hit = findIn(kids[i], test)
        if (hit) return hit
      }
      return null
    }
    function byName(name) { return findIn(windowRoot(), function(i) { return i.objectName === name }) }
    function focused() { return overlay.pageScroll ? overlay.pageScroll.Window.activeFocusItem : null }
    function shown(item) {
      for (var a = item; a; a = a.parent) if (a.visible === false || a.opacity === 0) return false
      return true
    }
    function inside(item, box) {
      for (var a = item; a; a = a.parent) if (a === box) return true
      return false
    }
    // Everything on the page that says it takes Tab, shown and enabled.
    function candidates(item, out) {
      if (!item || item.visible === false || item.enabled === false) return out
      if (item.activeFocusOnTab === true) out.push(item)
      var kids = item.children || []
      for (var i = 0; i < kids.length; i++) candidates(kids[i], out)
      return out
    }
    function nameOf(item) {
      var n = ""
      try { n = String(item.Accessible.name || "") } catch (e) { n = "" }
      if (n === "" && item.placeholderText !== undefined) n = String(item.placeholderText || "")
      return n
    }
    function describe(item) {
      var t = String(item).split("(")[0]
      var n = nameOf(item)
      if (n === "" && item.text !== undefined) n = "text=" + String(item.text).slice(0, 30)
      return t + (item.objectName ? "#" + item.objectName : "") + " " + n
    }

    property string writes: ""
    Process {
      id: writesReader
      command: ["sh", "-c", "cat \"$PREVIEW_WRITES\" 2>/dev/null"]
      stdout: StdioCollector { onStreamFinished: overlay.writes = text }
    }

    property int idx: -1
    property int warm: 0
    property var seen: []
    property var first: null
    property int presses: 0
    property int offScreen: 0
    property int upJumps: 0
    property real lastY: -1
    property var unnamed: []
    property bool walking: false
    property bool done: false
    property string label: ""
    // The second walk of a page, with every fold opened.
    property bool unfolded: false

    // Every folded section, card and agent strip on the page.
    function folds(item, out) {
      if (!item || item.visible === false) return out
      if (item.expanded === false && typeof item.flip === "function" && item.foldable !== false) out.push(item)
      var kids = item.children || []
      for (var i = 0; i < kids.length; i++) folds(kids[i], out)
      return out
    }

    function startPage() {
      var p = overlay.plan[overlay.idx]
      overlay.label = p[0] + (p[2] ? "/" + p[2] : "")
      overlay.unfolded = false
      overlay.goTo(p[0], p[1] || "", p[2] || "")
      overlay.warm = 0
    }
    function finishPage() {
      overlay.walking = false
      var page = overlay.byName("pageLoader") || overlay.pageScroll.contentItem
      var cand = overlay.candidates(overlay.pageScroll.contentItem, [])
      var missing = []
      for (var i = 0; i < cand.length; i++)
        if (overlay.seen.indexOf(cand[i]) < 0) missing.push(overlay.describe(cand[i]))
      var onPage = 0
      for (var j = 0; j < overlay.seen.length; j++) if (overlay.inside(overlay.seen[j], overlay.pageScroll.contentItem)) onPage++
      console.warn("PREVIEW " + overlay.label + ": " + overlay.seen.length + " stops (" + onPage + " on the page), "
                   + overlay.presses + " presses, " + overlay.upJumps + " jumps back up")
      overlay.check(overlay.presses < 400, overlay.label + ": Tab comes back round to where it started")
      overlay.check(missing.length === 0, overlay.label + ": every focusable control is reached by Tab"
                    + (missing.length ? " (missed " + missing.length + ": " + missing.slice(0, 6).join("; ") + ")" : ""))
      overlay.check(overlay.unnamed.length === 0, overlay.label + ": everything reached has a name"
                    + (overlay.unnamed.length ? " (" + overlay.unnamed.length + ": " + overlay.unnamed.slice(0, 6).join("; ") + ")" : ""))
      overlay.check(overlay.offScreen === 0, overlay.label + ": the page scrolls to keep the focus in view ("
                    + overlay.offScreen + " stops out of view)")
      overlay.check(overlay.inside(overlay.seen[0], overlay.byName("settingsSearchField")) || overlay.seen.some(function(s) {
        return overlay.inside(s, overlay.byName("settingsSearchField")) }), overlay.label + ": the search box is in the Tab order")
    }

    Timer {
      id: tick
      interval: 30
      repeat: true
      running: true
      onTriggered: {
        if (overlay.done || !overlay.store.loaded) return
        if (overlay.idx < 0) { overlay.idx = 0; overlay.startPage(); return }
        if (!overlay.walking) {
          // Let the page build (folders, chats and stats arrive by Process).
          if (++overlay.warm < 60) return
          overlay.seen = []; overlay.first = null; overlay.presses = 0
          overlay.offScreen = 0; overlay.upJumps = 0; overlay.lastY = -1; overlay.unnamed = []
          overlay.byName("settingsCard").forceActiveFocus()
          overlay.walking = true
          overlay.key(Qt.Key_Tab)
          return
        }
        // The previous press has been handled and the page has had its
        // turn to follow; judge where the focus is.
        var f = overlay.focused()
        if (f && overlay.first === null) overlay.first = f
        else if (f && f === overlay.first) { overlay.finishPage(); next(); return }
        if (f) {
          // Every stop is logged, so a trap or a wrong order can be read back.
          if (overlay.want !== "shot")
            console.warn("PREVIEW   stop " + overlay.presses + ": " + overlay.describe(f))
          if (overlay.seen.indexOf(f) < 0) {
            overlay.seen.push(f)
            if (overlay.nameOf(f) === "") overlay.unnamed.push(overlay.describe(f))
          }
          var sc = overlay.pageScroll
          if (overlay.inside(f, sc.contentItem)) {
            var y = f.mapToItem(sc.contentItem, 0, 0).y
            var mid = y + f.height / 2
            if (sc.interactive && (mid < sc.contentY - 1 || mid > sc.contentY + sc.height + 1)) {
              overlay.offScreen++
              console.warn("PREVIEW   out of view: " + overlay.describe(f))
            }
            if (overlay.lastY >= 0 && y < overlay.lastY - 40) overlay.upJumps++
            overlay.lastY = y
          }
          if (overlay.want === "shot" && overlay.seen.length === 9) { overlay.done = true; return }
        }
        if (++overlay.presses >= 400) { overlay.finishPage(); next(); return }
        overlay.key(Qt.Key_Tab)
      }
      function next() {
        // Once more with everything opened: a control under a fold is as
        // much the page's as one above it.
        if (!overlay.unfolded) {
          var f = overlay.folds(overlay.pageScroll.contentItem, [])
          if (f.length > 0) {
            for (var i = 0; i < f.length; i++) f[i].flip()
            overlay.unfolded = true
            overlay.label = overlay.label + " (" + f.length + " folds opened)"
            overlay.warm = 40
            return
          }
        }
        overlay.idx++
        if (overlay.idx < overlay.plan.length) { overlay.startPage(); return }
        overlay.done = true
        writesReader.running = true
        final.start()
      }
    }
    Timer {
      id: final
      interval: 600
      onTriggered: {
        overlay.check(overlay.writes.trim() === "", "tabbing wrote nothing (" + overlay.writes.trim() + ")")
        console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
      }
    }
  }
}
