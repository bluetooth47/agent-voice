// Skills: move, copy, undo (master plan, M12), driven by synthetic mouse
// events (QtTest's TestEvent: the real pointer never moves) through the real
// pages, the real `agentvoice skills move|copy|undo` and the real import, on
// the scratch folders transfer.seed.py writes:
//
//   preview.sh --config bench/preview/configs/transfer3.json --scratch-data \
//     --wait 150 --out /tmp/t transfer
//   grep PREVIEW /tmp/t.log
//
// The overlay's view here is about 530x510, one lane across, so each drag is
// between neighbouring lanes (both ends on screen, as a hand needs); "Move
// to…" is the path for lanes further apart. Key events do not reach this
// window (the preview never takes the keyboard), so the keyboard paths are
// checked in tests/test_transfer_ui.py and by hand, not here.
//
// On Sora's Tools & skills tab: Theo's packing-list dragged onto Hazel's
// lane moves there, and Undo brings it back; Ctrl+drag copies, and Undo takes
// the copy back; Sora's tea-timer through "Move to…" towards Communal asks
// first, Cancel changes nothing, the confirm moves it and Undo brings it
// back; Hazel's bird-notes (Hazel is quarantined) asks, with the warning,
// before it moves to Theo; the communal house-style dropped on Sora, who has
// her own, is refused with the reason; an Unused card dropped on Hazel asks
// the import's question. On Communal → Skills: bird-notes dragged into
// Communal asks and moves; house-style dragged out to Theo moves at once.
import QtQuick
import QtTest
import Quickshell
import Quickshell.Io
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    readonly property bool shotsOnly: Quickshell.env("PREVIEW_ARG") === "shots"
    Component.onCompleted: overlay.open('{"page":"agentdetails","agent":"sora","tab":"tools"}')
    TestEvent { id: input }
    // With PREVIEW_ARG=shots (`--arg shots --shots 8`): the lanes walked a
    // screenful at a time, with the confirm for a move into Communal up
    // under them, for screenshots. Nothing is moved.
    Loader {
      active: overlay.shotsOnly
      sourceComponent: Component { Scroller { target: overlay } }
    }
    Timer {
      interval: 2500
      running: overlay.shotsOnly
      repeat: true
      onTriggered: {
        var mv = overlay.mover()
        if (mv && mv.pending === null && overlay.store.loaded)
          mv.request("tea-timer", "sora", "communal", false, [])
      }
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
    function content() { return overlay.pageScroll ? overlay.pageScroll.contentItem : null }
    function scrollTo(item, above) {
      var flick = overlay.pageScroll
      if (!item || !flick || !content()) return
      var y = item.mapToItem(content(), 0, 0).y
      flick.contentY = Math.max(0, Math.min(y - (above || 40), flick.contentHeight - flick.height))
    }
    function click(item, label) {
      if (!item) { check(false, "found " + label); return }
      scrollTo(item, 120)
      console.warn("PREVIEW click " + label)
      input.mouseClick(item, item.width / 2, item.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
    }
    function lane(id) { return find(content(), function(i) { return i.laneId === id && i.received !== undefined }) }
    function card(within, name) {
      return find(within, function(i) { return i.moveRequested !== undefined && i.details !== undefined && String(i.title) === name })
    }
    function button(within, text) {
      return find(within, function(i) { return i.clicked !== undefined && String(i.text).indexOf(text) === 0 })
    }
    function confirmBox() { return find(content(), function(i) { return i.confirmText !== undefined && i.lines !== undefined }) }
    function confirmText() {
      var b = confirmBox()
      return b ? b.title + " " + JSON.stringify(b.lines) + " " + b.warning : ""
    }
    // A card's Move to… menu (a Popup: in `data`, not `children`).
    function menuOf(c) {
      var d = c ? c.data : []
      for (var i = 0; i < d.length; i++) if (d[i] && d[i].entries !== undefined && d[i].choose !== undefined) return d[i]
      return null
    }
    function mover() { return find(content(), function(i) { return i.transferSkill !== undefined }) }
    // A drag from a card's header onto a lane, in twelve moves, as a hand
    // would; with Ctrl held throughout when `copy`.
    function dragTo(c, l, copy, label) {
      if (!c || !l) { check(false, "found both ends of " + label); return }
      // Both ends on screen: the middle of the two in the middle of the view.
      var flick = overlay.pageScroll
      var cy = c.mapToItem(content(), 0, 0).y, ly = l.mapToItem(content(), 0, 0).y
      flick.contentY = Math.max(0, Math.min((cy + ly) / 2 - flick.height / 2, flick.contentHeight - flick.height))
      var win = c.Window.contentItem
      var mods = copy ? Qt.ControlModifier : Qt.NoModifier
      var s = c.mapToItem(win, 24, 12)
      var t = l.mapToItem(win, l.width / 2, Math.min(l.height / 2, 24))
      var fr = flick.mapToItem(win, 0, 0)
      console.warn("PREVIEW view " + Math.round(fr.x) + "," + Math.round(fr.y) + " " + Math.round(flick.width) + "x" +
                   Math.round(flick.height) + " contentY " + Math.round(flick.contentY) + " cy " + Math.round(cy) + " ly " + Math.round(ly))
      console.warn("PREVIEW drag " + label + " from " + Math.round(s.x) + "," + Math.round(s.y) +
                   " to " + Math.round(t.x) + "," + Math.round(t.y) + " in " + Math.round(win.width) + "x" + Math.round(win.height))
      input.mousePress(c, 24, 12, Qt.LeftButton, mods, -1)
      for (var k = 1; k <= 12; k++)
        input.mouseMove(win, s.x + (t.x - s.x) * k / 12, s.y + (t.y - s.y) * k / 12, -1, Qt.LeftButton, mods)
      input.mouseRelease(win, t.x, t.y, Qt.LeftButton, mods, -1)
    }

    // Where every SKILL.md is now, from the scratch data folder.
    property string files: ""
    Process {
      id: lister
      command: ["sh", "-c", "cd \"$PREVIEW_DATA\" && find agents communal -name SKILL.md -not -path '*/.*' | sort"]
      stdout: StdioCollector { onStreamFinished: overlay.files = String(text) }
    }
    function look() { lister.running = true }
    function has(rel) { return overlay.files.split("\n").indexOf(rel + "/SKILL.md") >= 0 }

    property int step: 0
    property int warm: 0

    Timer {
      interval: 2000
      repeat: true
      running: !overlay.shotsOnly
      onTriggered: {
        if (!overlay.store.loaded || ++overlay.warm < 4) return
        overlay.step++
        var c, l, m, t
        switch (overlay.step) {
        case 1:
          overlay.dragTo(overlay.card(overlay.lane("main"), "packing-list"), overlay.lane("hazel"), false,
                         "packing-list from Theo's lane onto Hazel's")
          break
        case 2: overlay.look(); break
        case 3:
          overlay.check(overlay.has("agents/hazel/skills/packing-list") && !overlay.has("agents/main/skills/packing-list"),
                        "a drag moves it: Hazel has packing-list, Theo has not")
          overlay.check(overlay.mover() && overlay.mover().last !== null, "and Undo is offered")
          overlay.click(overlay.button(overlay.mover(), "Undo"), "Undo")
          break
        case 4: overlay.look(); break
        case 5:
          overlay.check(overlay.has("agents/main/skills/packing-list") && !overlay.has("agents/hazel/skills/packing-list"),
                        "Undo moves it back")
          overlay.dragTo(overlay.card(overlay.lane("main"), "packing-list"), overlay.lane("hazel"), true,
                         "Ctrl+drag packing-list onto Hazel's lane")
          break
        case 6: overlay.look(); break
        case 7:
          overlay.check(overlay.has("agents/hazel/skills/packing-list") && overlay.has("agents/main/skills/packing-list"),
                        "Ctrl+drag copies: both have it")
          overlay.click(overlay.button(overlay.mover(), "Undo"), "Undo the copy")
          break
        case 8: overlay.look(); break
        case 9:
          overlay.check(!overlay.has("agents/hazel/skills/packing-list") && overlay.has("agents/main/skills/packing-list"),
                        "Undo takes the copy back and leaves the original")
          overlay.click(overlay.button(overlay.card(overlay.lane("sora"), "tea-timer"), "Move to"), "tea-timer's Move to…")
          break
        case 10:
          m = overlay.menuOf(overlay.card(overlay.lane("sora"), "tea-timer"))
          overlay.check(m !== null && m.opened, "the Move to… button opens the menu")
          overlay.check(m && JSON.stringify(m.entries.map(function(e) { return e.section || e.value })) ===
                        '["Move to","move:communal","move:main","move:hazel","Copy to","copy:communal","copy:main","copy:hazel"]',
                        "listing every other lane, to move or to copy (" + (m ? m.entries.map(function(e) { return e.section || e.value }).join() : "") + ")")
          // The cursor starts on the first entry; this is what Enter or a
          // click on it calls (the agents target does the same).
          if (m) m.choose(m.cursor)
          break
        case 11:
          t = overlay.confirmText()
          overlay.check(t.indexOf("Move tea-timer to Communal?") >= 0 && t.indexOf("Every agent will get this skill") >= 0,
                        "towards Communal it asks first, naming who gets it")
          overlay.look()
          break
        case 12:
          overlay.check(overlay.has("agents/sora/skills/tea-timer") && !overlay.has("communal/skills/tea-timer"),
                        "nothing moves before the answer")
          overlay.click(overlay.button(overlay.confirmBox(), "Cancel"), "Cancel")
          break
        case 13:
          overlay.check(overlay.confirmBox() === null, "Cancel closes it")
          overlay.click(overlay.button(overlay.card(overlay.lane("sora"), "tea-timer"), "Move to"), "tea-timer's Move to…, again")
          break
        case 14:
          m = overlay.menuOf(overlay.card(overlay.lane("sora"), "tea-timer"))
          if (m) m.choose(m.cursor)
          break
        case 15:
          overlay.click(overlay.button(overlay.confirmBox(), "Move"), "Move (the confirm)")
          break
        case 16: overlay.look(); break
        case 17:
          overlay.check(overlay.has("communal/skills/tea-timer") && !overlay.has("agents/sora/skills/tea-timer"),
                        "confirmed, it moves into Communal")
          overlay.click(overlay.button(overlay.mover(), "Undo"), "Undo")
          break
        case 18: overlay.look(); break
        case 19:
          overlay.check(overlay.has("agents/sora/skills/tea-timer") && !overlay.has("communal/skills/tea-timer"),
                        "Undo brings it back")
          overlay.dragTo(overlay.card(overlay.lane("hazel"), "bird-notes"), overlay.lane("main"), false,
                         "bird-notes from quarantined Hazel onto Theo")
          break
        case 20:
          t = overlay.confirmText()
          overlay.check(t.indexOf("quarantined") >= 0 && t.indexOf("Theo only") >= 0,
                        "out of a quarantined agent asks first, with the warning")
          overlay.look()
          break
        case 21:
          overlay.check(overlay.has("agents/hazel/skills/bird-notes"), "nothing moves before the answer")
          overlay.click(overlay.button(overlay.confirmBox(), "Move"), "Move (the confirm)")
          break
        case 22: overlay.look(); break
        case 23:
          overlay.check(overlay.has("agents/main/skills/bird-notes") && !overlay.has("agents/hazel/skills/bird-notes"),
                        "and moves once confirmed")
          // Too far apart to drag in this view: through the menu.
          overlay.click(overlay.button(overlay.card(overlay.lane("communal"), "house-style"), "Move to"),
                        "communal house-style's Move to…")
          break
        case 24:
          m = overlay.menuOf(overlay.card(overlay.lane("communal"), "house-style"))
          if (m) for (var i = 0; i < m.entries.length; i++) if (m.entries[i].value === "move:sora") m.choose(i)
          l = overlay.find(overlay.content(), function(x) { return x.skillDropped !== undefined && x.skillNote !== undefined })
          overlay.check(l && String(l.skillNote).indexOf("Sora already has a skill named house-style") >= 0,
                        "a name clash (Sora has her own) is refused, saying why (" + (l ? l.skillNote : "") + ")")
          overlay.check(overlay.confirmBox() === null, "and asks nothing")
          overlay.look()
          break
        case 25:
          overlay.check(overlay.has("communal/skills/house-style") && overlay.has("agents/sora/skills/house-style"),
                        "and changes nothing")
          overlay.dragTo(overlay.card(overlay.lane("unused"), "crash-notes"), overlay.lane("hazel"), false,
                         "an Unused card onto Hazel")
          break
        case 26:
          t = overlay.confirmText()
          overlay.check(t.indexOf("Give Hazel a copy of crash-notes?") >= 0 && t.indexOf(".agents/skills/crash-notes") >= 0,
                        "a skill from outside is only ever copied, through the import's question")
          overlay.click(overlay.button(overlay.confirmBox(), "Cancel"), "Cancel")
          break
        case 27:
          overlay.goTo("communal", "", "skills")
          break
        case 28: break
        case 29:
          overlay.dragTo(overlay.card(overlay.lane("main"), "bird-notes"), overlay.lane("communal"), false,
                         "Communal page: bird-notes from Theo into Communal")
          break
        case 30:
          t = overlay.confirmText()
          overlay.check(t.indexOf("Move bird-notes to Communal?") >= 0, "the Communal page asks the same")
          overlay.click(overlay.button(overlay.confirmBox(), "Move"), "Move (the confirm)")
          break
        case 31: overlay.look(); break
        case 32:
          overlay.check(overlay.has("communal/skills/bird-notes") && !overlay.has("agents/main/skills/bird-notes"),
                        "and moves it")
          overlay.dragTo(overlay.card(overlay.lane("communal"), "house-style"), overlay.lane("main"), false,
                         "Communal page: house-style out to Theo")
          break
        case 33: overlay.look(); break
        case 34:
          overlay.check(overlay.has("agents/main/skills/house-style") && !overlay.has("communal/skills/house-style"),
                        "out of Communal to one agent moves at once, asking nothing")
          overlay.check(overlay.mover() && overlay.mover().last !== null, "with Undo offered")
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          Qt.quit()
          break
        }
      }
    }
  }
}
