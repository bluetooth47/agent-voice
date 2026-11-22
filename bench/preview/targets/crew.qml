// The Crew map page (M8), drawn and driven through real saves.
//
//   preview.sh --config bench/preview/configs/crew3.json --size 520x720 \
//     --wait 6 --shots 3 --arg empty --out /tmp/crew crew    # screenshots
//   preview.sh --config bench/preview/configs/agents8.json --arg linked ... crew
//   preview.sh --config bench/preview/configs/crew3.json --arg clicks \
//     --wait 40 --out /tmp/cc crew
//   grep PREVIEW /tmp/cc.log; cat /tmp/cc.writes
//
// PREVIEW_ARG: MODE or MODE:WIDTH, WIDTH the card's for the narrow layout.
//   empty   the page as it opens on an upgrade: no links, the banner.
//   linked  links written first, through the page's own functions:
//           everyone, the first link asking first, the last agent
//           quarantined (its links trimmed as the page trims them).
//   clicks  synthetic clicks on the real controls, each write logged by
//           the `omarchy bar set` stub and applied to the scratch config:
//           Link everyone (armed → cancelled, then confirmed), a chip, Ask
//           me first, Delete (cancelled, then confirmed), Add link,
//           Quarantine, Release. Each step's result is checked against the
//           list the step should have written ("PREVIEW PASS/FAIL ...").
//
// Nothing real is touched: --config gives a scratch shell.json, and the
// page writes nothing else.
import QtQuick
import QtTest
import Quickshell
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    Component.onCompleted: overlay.open('{"page":"crew"}')

    TestEvent { id: input }

    // "linked" or "linked:520": the mode, and a card width for the narrow
    // layout (cropping a big screen's shot never gives it).
    readonly property string mode: (Quickshell.env("PREVIEW_ARG") || "empty").split(":")[0]
    readonly property int cardWidth: Number((Quickshell.env("PREVIEW_ARG") || "").split(":")[1] || 0)
    // A third field: "table" to draw the table instead of the map, "sparse"
    // for a map with a few lines rather than everyone linked.
    readonly property string extra: (Quickshell.env("PREVIEW_ARG") || "").split(":")[2] || ""
    readonly property string view: extra === "table" ? "table" : ""
    readonly property bool sparse: extra === "sparse"
    function narrow() {
      if (!overlay.cardWidth) return
      var w = overlay.pageScroll ? overlay.pageScroll.Window.window : null
      var c = w ? find(w.contentItem, function(i) { return i.objectName === "settingsCard" }) : null
      if (c) c.width = overlay.cardWidth
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
    function crewPage() {
      return find(overlay.pageScroll, function(i) { return i.commit !== undefined && i.linksQuarantining !== undefined })
    }
    function button(prefix) {
      return find(overlay.pageScroll, function(i) {
        return i.clicked !== undefined && typeof i.text === "string" && i.text.indexOf(prefix) === 0
      })
    }
    function named(name) {
      return find(overlay.pageScroll, function(i) { return i.objectName === name })
    }
    function click(item, label) {
      if (!item) { console.warn("PREVIEW miss " + label); failed++; return }
      var flick = overlay.pageScroll
      if (flick && flick.contentItem) {
        var y = item.mapToItem(flick.contentItem, 0, 0).y
        flick.contentY = Math.max(0, Math.min(y - 120, flick.contentHeight - flick.height))
      }
      console.warn("PREVIEW click " + label)
      input.mouseClick(item, item.width / 2, item.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
    }
    function saved(key) { var v = overlay.cfg[key]; return v === undefined ? [] : v }
    function pairs(list) { return list.map(function(l) { return l.from + ">" + l.to + ":" + l.allow.join("+") + (l.askFirst ? "!" : "") }).join(" ") }
    function log(label) {
      console.warn("PREVIEW " + label + ": links=" + JSON.stringify(saved("crewLinks")) +
                   " quarantine=" + JSON.stringify(saved("crewQuarantine")))
    }

    property var ids: []
    property var before: []
    property var steps: [function() { overlay.narrow() }].concat(
      mode === "clicks" ? clickSteps : mode === "drags" ? dragSteps
      : mode === "linked" ? linkedSteps : [function() { overlay.log("empty") }])

    // --- drags: the map driven with synthetic pointer and key events (M9) -----
    // Each gesture goes through the real MouseAreas; each write goes through
    // `agentvoice crew check` (this checkout's) and the bar-set stub. Run:
    //   preview.sh --config bench/preview/configs/crew3.json --arg drags \
    //     --wait 60 --out /tmp/cd crew; grep PREVIEW /tmp/cd.log
    property var keys: null
    function keyEvents() {
      // Inside an Item of the overlay's window, so key events find it.
      if (!overlay.keys) overlay.keys = Qt.createQmlObject("import QtTest; TestEvent {}", overlay.pageScroll)
      return overlay.keys
    }
    function mapItem() { return overlay.named("crewMap") }
    function centre(id) { var m = overlay.mapItem(); return m.centreAt(id) }
    function scrollTo(item) {
      var flick = overlay.pageScroll
      var y = item.mapToItem(flick.contentItem, 0, 0).y
      flick.contentY = Math.max(0, Math.min(y - 60, flick.contentHeight - flick.height))
    }
    // Press on `item` at its own (x, y), move in ten steps to (tx, ty) on
    // the map, let go there.
    function dragOnMap(item, x, y, tx, ty, label) {
      if (!item) { console.warn("PREVIEW miss " + label); overlay.failed++; return }
      var m = overlay.mapItem()
      var start = item.mapToItem(m, x, y)
      console.warn("PREVIEW drag " + label)
      input.mousePress(item, x, y, Qt.LeftButton, Qt.NoModifier, -1)
      for (var k = 1; k <= 10; k++)
        input.mouseMove(m, start.x + (tx - start.x) * k / 10, start.y + (ty - start.y) * k / 10, -1, Qt.LeftButton, Qt.NoModifier)
      input.mouseRelease(m, tx, ty, Qt.LeftButton, Qt.NoModifier, -1)
    }
    function dragLink(from, to) {
      var dot = overlay.named("dot:" + from), c = overlay.centre(to)
      overlay.dragOnMap(dot, dot ? dot.width / 2 : 0, dot ? dot.height / 2 : 0, c.x, c.y, "a line from " + from + "'s dot onto " + to)
    }
    function dragBox(id, tx, ty) {
      var box = overlay.named("agent:" + id)
      overlay.dragOnMap(box, 16, box ? box.height / 2 : 0, tx, ty, id + "'s box to " + Math.round(tx) + "," + Math.round(ty))
    }
    function inZone(id) { var m = overlay.mapItem(); return overlay.centre(id).y > m.height - m.zoneH }
    function link(f, t) {
      var got = overlay.saved("crewLinks")
      for (var i = 0; i < got.length; i++) if (got[i].from === f && got[i].to === t) return got[i]
      return null
    }
    function within(item, target) { for (var i = item; i; i = i.parent) if (i === target) return true; return false }
    property var spot: null

    property var dragSteps: [
      function() {
        var p = overlay.crewPage()
        overlay.ids = p ? p.ids : []
        overlay.check(p !== null && p.view === "map" && overlay.mapItem() !== null, "the page opens on the map")
        overlay.check(overlay.saved("crewLinks").length === 0, "with no links")
        overlay.scrollTo(overlay.mapItem())
      },
      function() { overlay.dragLink(overlay.ids[0], overlay.ids[1]) },
      function() {
        var l = overlay.link(overlay.ids[0], overlay.ids[1])
        overlay.check(l !== null && l.allow.join() === "ask" && l.askFirst === false && overlay.saved("crewLinks").length === 1,
                      "the drawn line saved one link carrying ask: " + JSON.stringify(overlay.saved("crewLinks")))
        var p = overlay.crewPage()
        overlay.check(p.isSelectedLink(overlay.ids[0], overlay.ids[1]), "and opened it in the inspector")
      },
      function() { overlay.dragLink(overlay.ids[0], overlay.ids[0]) },
      function() { overlay.check(overlay.saved("crewLinks").length === 1, "a line dropped back on its own agent saves nothing") },
      function() { overlay.click(overlay.button("delegate"), "the inspector's delegate chip") },
      function() {
        var l = overlay.link(overlay.ids[0], overlay.ids[1])
        overlay.check(l && l.allow.join() === "ask,delegate", "the chip added delegate: " + (l ? l.allow.join() : "gone"))
      },
      function() { overlay.click(overlay.named("askFirst"), "the inspector's Ask me first") },
      function() {
        var l = overlay.link(overlay.ids[0], overlay.ids[1])
        overlay.check(l && l.askFirst === true, "Ask me first saved on that link")
      },
      function() { overlay.click(overlay.button("Also allow the reverse"), "Also allow the reverse") },
      function() {
        var r = overlay.link(overlay.ids[1], overlay.ids[0])
        overlay.check(r && r.allow.join() === "ask,delegate" && r.askFirst === true && overlay.saved("crewLinks").length === 2,
                      "the reverse saved with the same abilities: " + JSON.stringify(r))
        overlay.check(overlay.crewPage().isSelectedLink(overlay.ids[1], overlay.ids[0]), "and the inspector moved to it")
      },
      function() { overlay.click(overlay.button("⚠ Delete line"), "Delete line: arm") },
      function() { overlay.click(overlay.button("Cancel"), "Delete line: Cancel") },
      function() { overlay.check(overlay.saved("crewLinks").length === 2, "Cancel deleted nothing") },
      function() { overlay.click(overlay.button("⚠ Delete line"), "Delete line: arm") },
      function() { overlay.click(overlay.button("Delete"), "Delete line: confirm") },
      function() {
        overlay.check(overlay.link(overlay.ids[1], overlay.ids[0]) === null && overlay.link(overlay.ids[0], overlay.ids[1]) !== null,
                      "Delete line removed that one link and kept the other")
      },
      // Quarantine by dragging into the zone: armed, then confirmed.
      function() { var m = overlay.mapItem(); overlay.scrollTo(m); overlay.dragBox(overlay.ids[2], m.width * 0.7, m.height - m.zoneH / 2) },
      function() {
        var p = overlay.crewPage()
        overlay.check(p.pendingQuarantine === overlay.ids[2] && overlay.saved("crewQuarantine").length === 0,
                      "the drop asks first and saves nothing yet")
        overlay.check(overlay.button("Quarantine") !== null, "the confirm is up: " + p.quarantineQuestion(overlay.ids[2]))
      },
      function() { overlay.click(overlay.button("Quarantine"), "Quarantine: confirm") },
      function() {
        overlay.check(JSON.stringify(overlay.saved("crewQuarantine")) === JSON.stringify([overlay.ids[2]]), "the confirm saved the quarantine")
        overlay.check(overlay.inZone(overlay.ids[2]), "and the box stays in the zone")
      },
      // Into the zone again with another agent, and cancelled: it goes back.
      function() { var m = overlay.mapItem(); overlay.spot = overlay.centre(overlay.ids[1]); overlay.dragBox(overlay.ids[1], m.width * 0.3, m.height - m.zoneH / 2) },
      function() { overlay.click(overlay.button("Cancel"), "Quarantine: Cancel") },
      function() {
        var c = overlay.centre(overlay.ids[1])
        overlay.check(overlay.saved("crewQuarantine").indexOf(overlay.ids[1]) < 0, "Cancel quarantined nothing")
        overlay.check(Math.abs(c.x - overlay.spot.x) < 2 && Math.abs(c.y - overlay.spot.y) < 2, "and the box went back where it was")
      },
      // Drawing from a quarantined agent: it has no dot.
      function() { overlay.check(overlay.named("dot:" + overlay.ids[2]) === null, "a quarantined agent has no dot to draw from") },
      // Out of the zone: released, nothing given back.
      function() { overlay.before = overlay.saved("crewLinks"); var m = overlay.mapItem(); overlay.dragBox(overlay.ids[2], m.width * 0.8, m.height * 0.2) },
      function() {
        overlay.check(overlay.saved("crewQuarantine").length === 0, "dragged out of the zone, it is released")
        overlay.check(JSON.stringify(overlay.saved("crewLinks")) === JSON.stringify(overlay.before), "and given no link back")
        overlay.check(!overlay.inZone(overlay.ids[2]), "its box stays where it was dropped")
      },
      // A box moved: the layout file, never shell.json.
      function() { var m = overlay.mapItem(); overlay.dragBox(overlay.ids[0], m.width * 0.25, m.height * 0.3) },
      function() {
        // Grabbed 16 px in from the box's left edge, so its centre lands
        // half a box less 16 px to the right of the pointer.
        var p = overlay.crewPage(), l = p.layout[overlay.ids[0]], m = overlay.mapItem()
        var fx = (m.width * 0.25 + m.boxW / 2 - 16) / m.width
        overlay.check(l && Math.abs(l.x - fx) < 0.01 && Math.abs(l.y - 0.3) < 0.01, "the move is kept in the layout: " + JSON.stringify(l))
      },
      // The keyboard: create from the agent inspector, reverse, delete.
      function() { overlay.click(overlay.named("agent:" + overlay.ids[2]), "select " + overlay.ids[2]) },
      function() {
        var p = overlay.crewPage()
        overlay.check(p.selectedAgent() === overlay.ids[2], "a click on a box opens the agent")
        var b = overlay.button("Add link")
        if (b) { b.forceActiveFocus(); console.warn("PREVIEW key Space on Add link"); overlay.keyEvents().keyClick(Qt.Key_Space, Qt.NoModifier, -1) }
        else { console.warn("PREVIEW miss Add link"); overlay.failed++ }
      },
      function() {
        var l = overlay.link(overlay.ids[2], overlay.ids[0])
        overlay.check(l !== null && l.allow.join() === "ask", "Space on Add link created " + overlay.ids[2] + " → " + overlay.ids[0])
        var b = overlay.button("Also allow the reverse")
        if (b) { b.forceActiveFocus(); console.warn("PREVIEW key Space on Also allow the reverse"); overlay.keyEvents().keyClick(Qt.Key_Space, Qt.NoModifier, -1) }
        else { console.warn("PREVIEW miss reverse"); overlay.failed++ }
      },
      function() {
        overlay.check(overlay.link(overlay.ids[0], overlay.ids[2]) !== null, "Space on the reverse created " + overlay.ids[0] + " → " + overlay.ids[2])
        var chip = overlay.named("edge:" + overlay.ids[0] + ">" + overlay.ids[2])
        if (chip) { chip.forceActiveFocus(); console.warn("PREVIEW key Delete on the line's label"); overlay.keyEvents().keyClick(Qt.Key_Delete, Qt.NoModifier, -1) }
        else { console.warn("PREVIEW miss chip"); overlay.failed++ }
      },
      function() {
        overlay.check(overlay.button("Cancel") !== null && overlay.link(overlay.ids[0], overlay.ids[2]) !== null, "Delete on a label arms the confirm and deletes nothing yet")
        var b = overlay.button("Delete")
        // Cancel has the focus; Tab to Delete, then Space, as somebody
        // without a mouse would.
        overlay.keyEvents().keyClick(Qt.Key_Tab, Qt.NoModifier, -1)
        overlay.keyEvents().keyClick(Qt.Key_Space, Qt.NoModifier, -1)
        console.warn("PREVIEW keys Tab, Space")
      },
      function() { overlay.check(overlay.link(overlay.ids[0], overlay.ids[2]) === null, "Tab and Space confirmed the delete") },
      // A refused save says why and writes nothing: a link to an agent no
      // longer here, asked of the page directly.
      function() {
        var p = overlay.crewPage()
        overlay.before = overlay.saved("crewLinks")
        p.commit(p.copyLinks().concat([{ from: overlay.ids[0], to: "nobody-here", allow: ["ask"], askFirst: false }]), p.quarantine, "a stray")
      },
      function() {
        var p = overlay.crewPage()
        overlay.check(JSON.stringify(overlay.saved("crewLinks")) === JSON.stringify(overlay.before) && p.saveNote.indexOf("Not saved") === 0,
                      "the validator's refusal saved nothing and said: " + p.saveNote)
      },
      // The table shows what the map saved.
      function() { overlay.crewPage().view = "table" },
      function() {
        var p = overlay.crewPage(), got = overlay.saved("crewLinks")
        var rows = 0
        for (var i = 0; i < got.length; i++) if (overlay.button("⚠ Delete") !== null) rows++
        overlay.check(JSON.stringify(p.links) === JSON.stringify(got), "the table reads the list the map saved")
        overlay.check(overlay.crewOutsideAt === "", "no write of the page's own counted as from outside")
        overlay.log("final")
        console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
      }
    ]

    property var linkedSteps: [
      function() {
        var p = overlay.crewPage()
        if (overlay.view !== "") p.view = overlay.view
        var all = p.everyoneLinks(p.ids)
        all[0].askFirst = true
        p.commit(all, [], "seed")
      },
      function() {
        var p = overlay.crewPage()
        var last = p.ids[p.ids.length - 1]
        p.commit(p.linksQuarantining(last), [last], "seed quarantine")
      },
      function() {
        // A sparser picture for the map: a two-way pair, a one-way line,
        // a line into quarantine; the first link selected.
        var p = overlay.crewPage()
        if (overlay.sparse) {
          var ids = p.ids, last = ids[ids.length - 1], L = []
          L.push({ from: ids[0], to: ids[1], allow: ["ask", "delegate"], askFirst: true })
          L.push({ from: ids[1], to: ids[0], allow: ["message"], askFirst: false })
          for (var i = 2; i < ids.length - 1; i++) L.push({ from: ids[0], to: ids[i], allow: ["ask", "delegate", "message", "pass"], askFirst: false })
          L.push({ from: ids[1], to: last, allow: ["ask"], askFirst: false })
          p.commit(L, [last], "seed sparse")
        }
      },
      function() {
        var p = overlay.crewPage()
        if (p.view === "map") p.select({ kind: "link", from: p.ids[0], to: p.ids[1] })
        overlay.log("linked"); overlay.pageScroll.contentY = 0
      }
    ]

    property var clickSteps: [
      function() {
        var p = overlay.crewPage()
        overlay.ids = p ? p.ids : []
        overlay.check(p !== null, "the Crew map page is shown")
        overlay.check(p !== null && p.view === "map", "it opens on the map")
        if (p) p.view = "table"
        overlay.check(overlay.saved("crewLinks").length === 0, "it opens with no links")
        overlay.check(overlay.button("⚠ Link everyone as before") !== null, "the banner offers Link everyone")
      },
      function() { overlay.click(overlay.button("⚠ Link everyone as before"), "Link everyone: arm") },
      function() { overlay.click(overlay.button("Cancel"), "Link everyone: Cancel") },
      function() { overlay.check(overlay.saved("crewLinks").length === 0, "Cancel wrote nothing") },
      function() { overlay.click(overlay.button("⚠ Link everyone as before"), "Link everyone: arm") },
      function() { overlay.click(overlay.button("Link everyone"), "Link everyone: confirm") },
      function() {
        var n = overlay.ids.length, got = overlay.saved("crewLinks")
        overlay.check(got.length === n * (n - 1), "Link everyone wrote " + got.length + " links for " + n + " agents")
        overlay.check(got.every(function(l) { return l.allow.join() === "ask,delegate,message,pass" && l.askFirst === false }),
                      "each allows everything and asks nothing first")
        overlay.before = got
      },
      // The first row is main → the first extra agent.
      function() { overlay.click(overlay.button("delegate"), "the first link's delegate chip") },
      function() {
        var got = overlay.saved("crewLinks")
        overlay.check(got[0].allow.join() === "ask,message,pass", "the chip took delegate off the first link only: " + got[0].allow.join())
        overlay.check(JSON.stringify(got.slice(1)) === JSON.stringify(overlay.before.slice(1)), "every other link is untouched")
      },
      function() { overlay.click(overlay.named("askFirst"), "the first link's Ask me first") },
      function() {
        var got = overlay.saved("crewLinks")
        overlay.check(got[0].askFirst === true && got.slice(1).every(function(l) { return !l.askFirst }), "Ask me first set on the first link only")
      },
      function() { overlay.click(overlay.button("⚠ Delete"), "Delete: arm") },
      function() { overlay.click(overlay.button("Cancel"), "Delete: Cancel") },
      function() { overlay.check(overlay.saved("crewLinks").length === overlay.before.length, "Cancel deleted nothing") },
      function() { overlay.click(overlay.button("⚠ Delete"), "Delete: arm") },
      function() { overlay.click(overlay.button("Delete"), "Delete: confirm") },
      function() {
        var got = overlay.saved("crewLinks"), first = overlay.ids[0] + ">" + overlay.ids[1]
        overlay.check(got.length === overlay.before.length - 1 &&
                      !got.some(function(l) { return l.from + ">" + l.to === first }), "Delete removed " + first + " and nothing else")
      },
      function() { overlay.click(overlay.button("Add link"), "Add link (from the first agent to the second)") },
      function() {
        var got = overlay.saved("crewLinks"), l = got[got.length - 1]
        overlay.check(l.from === overlay.ids[0] && l.to === overlay.ids[1] && l.allow.join() === "ask" && l.askFirst === false,
                      "Add link wrote " + JSON.stringify(l))
        overlay.before = got
      },
      function() { overlay.click(overlay.button("⚠ Quarantine"), "Quarantine the first agent: arm") },
      function() { overlay.click(overlay.button("Quarantine"), "Quarantine: confirm") },
      function() {
        var q = overlay.saved("crewQuarantine"), got = overlay.saved("crewLinks"), who = overlay.ids[0]
        overlay.check(q.length === 1 && q[0] === who, "quarantine wrote [" + q.join() + "]")
        overlay.check(!got.some(function(l) { return l.from === who }), "its links out are gone")
        overlay.check(got.filter(function(l) { return l.to === who }).every(function(l) {
          return l.allow.every(function(a) { return a === "ask" || a === "delegate" }) }), "its links in carry only ask and delegate")
        overlay.before = got
      },
      function() { overlay.click(overlay.button("Release"), "Release") },
      function() {
        overlay.check(overlay.saved("crewQuarantine").length === 0, "Release emptied the quarantine")
        overlay.check(JSON.stringify(overlay.saved("crewLinks")) === JSON.stringify(overlay.before), "Release gave no link back")
        overlay.check(overlay.crewOutsideAt === "", "no write of the page's own counted as from outside")
        overlay.log("final")
        console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
      }
    ]
    // Screenshots walk the page a screenful per shot; the clicks run stay
    // where each click scrolls them.
    Loader {
      active: overlay.mode !== "clicks"
      sourceComponent: Component { Scroller { target: overlay } }
    }
    property int step: 0
    Timer {
      interval: 1100
      repeat: true
      running: true
      onTriggered: {
        if (overlay.step >= 2 && overlay.step - 2 < overlay.steps.length) overlay.steps[overlay.step - 2]()
        overlay.step++
      }
    }
  }
}
