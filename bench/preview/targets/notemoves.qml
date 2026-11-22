// Notes: topics as cards, moved, copied and combined (master plan, M13),
// driven by synthetic mouse events (QtTest's TestEvent: the real pointer
// never moves) through the real Notes tab, the real `agentvoice notes
// move|copy|undo|combine` and the real `agentvoice agents notes restore`, on
// the scratch folders notemoves.seed.py writes:
//
//   preview.sh --config bench/preview/configs/transfer3.json --scratch-data \
//     --wait 150 --out /tmp/nm notemoves
//   grep PREVIEW /tmp/nm.log
//
// One lane across in this view, so each drag is between neighbouring lanes;
// Move to… is the path to a far one. Key events do not reach this window,
// so the keyboard paths are checked by hand.
//
// On Sora's Notes tab: her notes are cards titled by topic with their first
// line; Garden dragged onto Theo's lane moves (history and entry with it),
// Undo brings it back; Ctrl+drag copies, Undo takes the copy back; Recipes
// (marked as holding web text) through Move to… asks first, with the
// warning, and Cancel changes nothing; Garden towards Communal asks, saying
// who can read it and that past versions go too, then moves, then Undo;
// Hazel's Birds (quarantined) dragged onto Theo asks with the warning, then
// moves; Sora's Packing towards Theo, who has his own, is refused with the
// reason; Combine picks Seeds then Compost, asks, and leaves one note with
// Compost under Earlier notes, whose Put back brings it back; a card in
// another lane opens on that lane's own tab.
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
    Component.onCompleted: overlay.open('{"page":"agentdetails","agent":"sora","tab":"notes"}')
    TestEvent { id: input }
    // With PREVIEW_ARG=shots: the lanes walked a screenful at a time, with
    // the confirm for a move into Communal up, for screenshots. Nothing moves.
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
          mv.request("garden", "sora", "communal", false, false, "Garden", 2)
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
    function panel() { return find(content(), function(i) { return i.noteDropped !== undefined && i.notesList !== undefined }) }
    function lane(id) { return find(content(), function(i) { return i.laneId === id && i.received !== undefined }) }
    function card(within, title) {
      return find(within, function(i) { return i.moveRequested !== undefined && i.details !== undefined && String(i.title) === title })
    }
    function button(within, text) {
      return find(within, function(i) { return i.clicked !== undefined && String(i.text).indexOf(text) === 0 })
    }
    function confirmBox() { return find(content(), function(i) { return i.confirmText !== undefined && i.lines !== undefined }) }
    function confirmText() {
      var b = confirmBox()
      return b ? b.title + " " + JSON.stringify(b.lines) + " " + b.warning : ""
    }
    function menuOf(c) {
      var d = c ? c.data : []
      for (var i = 0; i < d.length; i++) if (d[i] && d[i].entries !== undefined && d[i].choose !== undefined) return d[i]
      return null
    }
    function pick(c, value) {
      var m = menuOf(c)
      if (!m) { check(false, "a menu on the card"); return }
      for (var i = 0; i < m.entries.length; i++) if (m.entries[i].value === value) { m.choose(i); return }
      check(false, "the menu lists " + value)
    }
    function mover() { return find(content(), function(i) { return i.transferNote !== undefined }) }
    function dragTo(c, l, copy, label) {
      if (!c || !l) { check(false, "found both ends of " + label); return }
      var flick = overlay.pageScroll
      var cy = c.mapToItem(content(), 0, 0).y, ly = l.mapToItem(content(), 0, 0).y
      flick.contentY = Math.max(0, Math.min((cy + ly) / 2 - flick.height / 2, flick.contentHeight - flick.height))
      var win = c.Window.contentItem
      var mods = copy ? Qt.ControlModifier : Qt.NoModifier
      var s = c.mapToItem(win, 24, 12)
      var t = l.mapToItem(win, l.width / 2, Math.min(l.height / 2, 24))
      console.warn("PREVIEW drag " + label)
      input.mousePress(c, 24, 12, Qt.LeftButton, mods, -1)
      // A small first step, as a hand makes: MouseArea moves the ghost from
      // where the drag threshold was crossed, so a long first step would
      // leave the ghost that far behind the pointer.
      var dy = t.y > s.y ? 8 : -8
      input.mouseMove(win, s.x, s.y + dy, -1, Qt.LeftButton, mods)
      for (var k = 1; k <= 12; k++)
        input.mouseMove(win, s.x + (t.x - s.x) * k / 12, s.y + dy + (t.y - s.y - dy) * k / 12, -1, Qt.LeftButton, mods)
      input.mouseRelease(win, t.x, t.y, Qt.LeftButton, mods, -1)
    }

    // Where every note is now, and each one's saved versions.
    property string files: ""
    Process {
      id: lister
      command: ["sh", "-c", "cd \"$PREVIEW_DATA\" && find agents communal -path '*/notes/*' -name '*.md' -not -path '*/.t-*' | sort"]
      stdout: StdioCollector { onStreamFinished: overlay.files = String(text) }
    }
    function look() { lister.running = true }
    function has(rel) { return overlay.files.split("\n").indexOf(rel + ".md") >= 0 }
    function versions(owner, name) {
      return overlay.files.split("\n").filter(function(l) {
        return l.indexOf(owner + "/notes/.history/" + name + "/") === 0 }).length
    }

    property int step: 0
    property int warm: 0

    Timer {
      interval: 2000
      repeat: true
      running: !overlay.shotsOnly
      onTriggered: {
        if (!overlay.store.loaded || ++overlay.warm < 4) return
        overlay.step++
        var c, p, t, m
        switch (overlay.step) {
        case 1:
          c = overlay.card(overlay.lane("sora"), "Garden")
          overlay.check(c !== null && c.subtitle === "Garden plans", "a note is a card: its topic, and its first line (" + (c ? c.subtitle : "") + ")")
          p = overlay.panel()
          overlay.check(p && p.otherLanes.map(function(l) { return l.id }).join() === "main,hazel,communal",
                        "every other folder is a lane, Communal last (" + (p ? p.otherLanes.map(function(l) { return l.id }).join() : "") + ")")
          overlay.look()
          break
        case 2:
          overlay.check(overlay.versions("agents/sora", "garden") === 2, "Garden has two saved versions")
          overlay.dragTo(overlay.card(overlay.lane("sora"), "Garden"), overlay.lane("main"), false, "Garden onto Theo's lane")
          break
        case 3: overlay.look(); break
        case 4:
          overlay.check(overlay.has("agents/main/notes/garden") && !overlay.has("agents/sora/notes/garden"),
                        "a drag moves it: Theo has garden, Sora has not")
          overlay.check(overlay.versions("agents/main", "garden") === 2 && overlay.versions("agents/sora", "garden") === 0,
                        "its saved versions went with it")
          overlay.check(overlay.mover() && overlay.mover().last !== null, "and Undo is offered")
          overlay.click(overlay.button(overlay.mover(), "Undo"), "Undo")
          break
        case 5: overlay.look(); break
        case 6:
          overlay.check(overlay.has("agents/sora/notes/garden") && !overlay.has("agents/main/notes/garden") &&
                        overlay.versions("agents/sora", "garden") === 2, "Undo moves it back, history and all")
          overlay.dragTo(overlay.card(overlay.lane("sora"), "Garden"), overlay.lane("main"), true, "Ctrl+drag Garden onto Theo's lane")
          break
        case 7: overlay.look(); break
        case 8:
          overlay.check(overlay.has("agents/sora/notes/garden") && overlay.has("agents/main/notes/garden"), "Ctrl+drag copies: both have it")
          overlay.click(overlay.button(overlay.mover(), "Undo"), "Undo the copy")
          break
        case 9: overlay.look(); break
        case 10:
          overlay.check(overlay.has("agents/sora/notes/garden") && !overlay.has("agents/main/notes/garden"),
                        "Undo takes the copy back and leaves the original")
          overlay.click(overlay.button(overlay.card(overlay.lane("sora"), "Recipes"), "Move to"), "Recipes' Move to…")
          break
        case 11:
          m = overlay.menuOf(overlay.card(overlay.lane("sora"), "Recipes"))
          overlay.check(m !== null && m.opened, "Move to… opens the menu")
          overlay.check(m && JSON.stringify(m.entries.map(function(e) { return e.section || e.value })) ===
                        '["Move to","move:main","move:hazel","move:communal","Copy to","copy:main","copy:hazel","copy:communal"]',
                        "listing every other lane (" + (m ? m.entries.map(function(e) { return e.section || e.value }).join() : "") + ")")
          overlay.pick(overlay.card(overlay.lane("sora"), "Recipes"), "move:main")
          break
        case 12:
          t = overlay.confirmText()
          overlay.check(t.indexOf("Move Recipes to Theo?") >= 0 && t.indexOf("web pages") >= 0,
                        "a note marked as holding web text asks first, saying so")
          overlay.look()
          break
        case 13:
          overlay.check(overlay.has("agents/sora/notes/recipes"), "nothing moves before the answer")
          overlay.click(overlay.button(overlay.confirmBox(), "Cancel"), "Cancel")
          break
        case 14:
          overlay.check(overlay.confirmBox() === null, "Cancel closes it")
          overlay.click(overlay.button(overlay.card(overlay.lane("sora"), "Garden"), "Move to"), "Garden's Move to…")
          break
        case 15:
          overlay.pick(overlay.card(overlay.lane("sora"), "Garden"), "move:communal")
          break
        case 16:
          t = overlay.confirmText()
          overlay.check(t.indexOf("Move Garden to Communal?") >= 0 && t.indexOf("Every agent here") >= 0 &&
                        t.indexOf("2 saved versions go with it") >= 0 && t.indexOf("past versions move too") >= 0,
                        "towards Communal it asks: who can read it, and that past versions go too")
          overlay.click(overlay.button(overlay.confirmBox(), "Move"), "Move (the confirm)")
          break
        case 17: overlay.look(); break
        case 18:
          overlay.check(overlay.has("communal/notes/garden") && overlay.versions("communal", "garden") === 2,
                        "confirmed, it moves into Communal with its versions")
          overlay.click(overlay.button(overlay.mover(), "Undo"), "Undo")
          break
        case 19: overlay.look(); break
        case 20:
          overlay.check(overlay.has("agents/sora/notes/garden") && !overlay.has("communal/notes/garden"), "Undo brings it back")
          overlay.dragTo(overlay.card(overlay.lane("hazel"), "Birds"), overlay.lane("main"), false, "Birds from quarantined Hazel onto Theo")
          break
        case 21:
          t = overlay.confirmText()
          overlay.check(t.indexOf("quarantined") >= 0 && t.indexOf("Theo only") >= 0, "out of a quarantined agent asks first, with the warning")
          overlay.click(overlay.button(overlay.confirmBox(), "Move"), "Move (the confirm)")
          break
        case 22: overlay.look(); break
        case 23:
          overlay.check(overlay.has("agents/main/notes/birds") && !overlay.has("agents/hazel/notes/birds"), "and moves once confirmed")
          overlay.click(overlay.button(overlay.card(overlay.lane("sora"), "Packing"), "Move to"), "Packing's Move to…")
          break
        case 24:
          overlay.pick(overlay.card(overlay.lane("sora"), "Packing"), "move:main")
          p = overlay.panel()
          overlay.check(p && p.moveNote.indexOf("Theo already has a note called packing") >= 0,
                        "a name clash is refused, saying why (" + (p ? p.moveNote : "") + ")")
          overlay.check(overlay.confirmBox() === null, "and asks nothing")
          overlay.click(overlay.button(overlay.panel(), "Combine…"), "Combine…")
          break
        case 25:
          overlay.click(overlay.button(overlay.card(overlay.lane("sora"), "Seeds"), "Pick"), "pick Seeds")
          break
        case 26:
          overlay.click(overlay.button(overlay.card(overlay.lane("sora"), "Compost"), "Pick"), "pick Compost")
          break
        case 27:
          p = overlay.panel()
          overlay.check(p && p.picked.join() === "seeds,compost", "picked in order: the first is kept (" + (p ? p.picked.join() : "") + ")")
          overlay.click(overlay.button(p, "Combine 2 notes"), "Combine 2 notes…")
          break
        case 28:
          t = overlay.confirmText()
          overlay.check(t.indexOf("Combine 2 notes into Seeds?") >= 0 && t.indexOf("Earlier notes can put it back") >= 0,
                        "Combine always asks, and says how to get one back")
          overlay.look()
          break
        case 29:
          overlay.check(overlay.has("agents/sora/notes/compost"), "nothing is combined before the answer")
          overlay.click(overlay.button(overlay.confirmBox(), "Combine"), "Combine (the confirm)")
          break
        case 30: overlay.look(); break
        case 31:
          overlay.check(overlay.has("agents/sora/notes/seeds") && !overlay.has("agents/sora/notes/compost") &&
                        overlay.versions("agents/sora", "compost") === 1, "one note is left, and Compost's last text is kept as a version")
          break
        case 32:
          overlay.click(overlay.button(overlay.panel(), "▸ Earlier notes"), "Earlier notes")
          break
        case 33:
          overlay.click(overlay.button(overlay.panel(), "Put back"), "Put back")
          break
        case 34: overlay.look(); break
        case 35:
          overlay.check(overlay.has("agents/sora/notes/compost"), "Put back makes Compost a note again")
          overlay.click(overlay.button(overlay.card(overlay.lane("communal"), "House rules"), "Open →"), "House rules' Open →")
          break
        case 36:
          overlay.check(overlay.page === "communal", "a card in another lane opens on its own tab (" + overlay.page + ")")
          break
        case 37:
          p = overlay.panel()
          overlay.check(p && p.target === "communal" && p.otherLanes.map(function(l) { return l.id }).join() === "main,hazel,sora",
                        "Communal's Notes tab has every agent's lane (" + (p ? p.otherLanes.map(function(l) { return l.id }).join() : "") + ")")
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          Qt.quit()
          break
        }
      }
    }
  }
}
