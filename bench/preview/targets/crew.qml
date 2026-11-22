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
      return find(overlay.pageScroll, function(i) { return i.writeLinks !== undefined && i.linksQuarantining !== undefined })
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
      mode === "clicks" ? clickSteps : mode === "linked" ? linkedSteps : [function() { overlay.log("empty") }])

    property var linkedSteps: [
      function() {
        var p = overlay.crewPage()
        var all = p.everyoneLinks(p.ids)
        all[0].askFirst = true
        p.writeLinks(all)
      },
      function() {
        var p = overlay.crewPage()
        var last = p.ids[p.ids.length - 1]
        p.writeQuarantine([last])
        p.writeLinks(p.linksQuarantining(last))
      },
      function() { overlay.log("linked"); overlay.pageScroll.contentY = 0 }
    ]

    property var clickSteps: [
      function() {
        var p = overlay.crewPage()
        overlay.ids = p ? p.ids : []
        overlay.check(p !== null, "the Crew map page is shown")
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
