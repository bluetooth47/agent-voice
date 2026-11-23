// The Overview (master plan M21) on synthetic numbers, checked tile by tile:
//
//   preview.sh --scratch-data --config bench/preview/configs/crew3.json \
//     --state bench/preview/states/showcase.json --size 1100x760 \
//     --wait 20 --arg several --out /tmp/ov overview
//   grep PREVIEW /tmp/ov.log; cat /tmp/ov.writes
//
// --arg (also read by overview.seed.py, which writes the numbers):
//   idle      one agent's quiet day (configs/agents1.json)
//   several   three agents, a busy day: every tile's figure, the hour bars,
//             Theo's "last chat ›" opening that chat on the Chats page
//   week      `several` and six days before: the 7 days choice
//   empty     nothing kept: every timing says "no data yet", the bars
//             "No wakes yet today."
//   off       keepStats switched off (written to the scratch config through
//             the real store): the Overview says nothing new is counted
//   MODE-shot the same numbers with nothing clicked but `week`'s choice, the
//             page stepped down a screenful each 2 s from 4 s after it is
//             ready (--wait 14 --shots 3 --gap 2)
//   clear     Other settings → Privacy's Clear stats (through the old "display" id): the first click only arms
//             it, Cancel writes nothing, Clear runs `agentvoice stats clear`
//             on the scratch copy, and the page then says none are kept
//
// Every number comes from the scratch data folder (the stub's `stats` case);
// the real stats folder and shell.json are never read or written.
import QtQuick
import QtTest
import Quickshell
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    Component.onCompleted: overlay.open('{"page":"overview"}')

    TestEvent { id: input }

    // "several-shot" and the like: the same numbers, nothing clicked, and the
    // page stepped down a screenful between shots (for screenshots).
    readonly property string arg: Quickshell.env("PREVIEW_ARG") || "several"
    readonly property string mode: arg.split("-")[0]
    readonly property bool shot: arg.indexOf("-shot") > 0
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
    function named(name) { return find(content(), function(i) { return i.objectName === name }) }
    function click(item, label) {
      if (!item) { check(false, "found " + label); return }
      var flick = overlay.pageScroll
      if (flick && content()) {
        var y = item.mapToItem(content(), 0, 0).y
        flick.contentY = Math.max(0, Math.min(y - 160, flick.contentHeight - flick.height))
      }
      input.mouseClick(item, item.width / 2, item.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
    }
    function tile(name) { var t = named(name); return t ? [t.value, t.label, t.caption].join(" | ") : "missing" }
    function has(name, text) { return tile(name).indexOf(text) >= 0 }
    function chip(item, text) {
      return find(item, function(i) { return i.clicked !== undefined && i.text === text })
    }
    function ovPage() { return named("overviewNumbers") ? named("overviewNumbers").parent : null }

    property int step: 0
    property int warm: 0

    Timer {
      interval: 2000
      repeat: true
      running: true
      onTriggered: {
        if (!overlay.store.loaded || ++overlay.warm < 3) return
        overlay.step++
        var p = overlay.ovPage()
        if (overlay.shot) {
          if (overlay.step === 1 && overlay.mode === "week")
            overlay.click(overlay.chip(overlay.named("overviewRange"), "7 days"), "7 days")
          if (overlay.step >= 2 && overlay.pageScroll)
            overlay.pageScroll.contentY = Math.min(overlay.pageScroll.contentHeight - overlay.pageScroll.height,
                                                   (overlay.step - 2) * overlay.pageScroll.height * 0.8)
          return
        }
        if (overlay.step === 1) {
          overlay.check(p !== null && p.stats !== null, "the numbers were read (" +
                        (p ? p.statsProblem : "no page") + ")")
          overlay.check(overlay.tile("tileUptime").indexOf("2 h 14 m") === 0,
                        "uptime from the state file (" + overlay.tile("tileUptime") + ")")
          overlay.check(overlay.has("tileUptime", "service 1.1 GB · agents 412 MB"),
                        "memory, the service and its agents apart")
        }
        switch (overlay.mode + ":" + overlay.step) {
        case "several:1":
        case "week:1":
          overlay.check(overlay.tile("tileTurns") === "9 | turns today | Theo 5 · Sora 3 · Hazel 1",
                        "turns today per agent (" + overlay.tile("tileTurns") + ")")
          overlay.check(overlay.tile("tileWake") === "3.2 s | wake to first word | p95 3.2 s · 5 turns",
                        "wake to first word, with its count (" + overlay.tile("tileWake") + ")")
          overlay.check(overlay.tile("tileTranscribe") === "0.3 s | transcription | p95 0.3 s · 7 turns",
                        "transcription, typed and task turns left out (" + overlay.tile("tileTranscribe") + ")")
          overlay.check(overlay.tile("tileReply") === "1.8 s | reply after you stop | p95 1.8 s · 7 turns",
                        "reply after you stop (" + overlay.tile("tileReply") + ")")
          overlay.check(overlay.tile("tileWakes").indexOf("7 / 2 | wakes / turned down | 2 false wakes (second check)") === 0,
                        "wakes against rejections, labelled as the second check's (" + overlay.tile("tileWakes") + ")")
          var bars = overlay.named("wakeBars")
          var sum = 0
          for (var i = 0; bars && i < bars.values.length; i++) sum += bars.values[i]
          overlay.check(bars !== null && bars.values.length === 24 && sum === 7, "24 hour bars holding the 7 wakes")
          break
        case "several:2":
          var link = overlay.find(overlay.content(), function(i) { return i.chatId !== undefined && i.chatId !== "" })
          overlay.check(link !== null && link.text === "last chat ›", "Theo's card offers his last chat")
          overlay.click(link, "last chat")
          break
        case "several:3":
          overlay.check(overlay.page === "chats" && /^[0-9a-f]{16}$/.test(overlay.openChat),
                        "last chat opens it on the Chats page (" + overlay.page + ", " + overlay.openChat + ")")
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          break
        case "week:2":
          overlay.click(overlay.chip(overlay.named("overviewRange"), "7 days"), "7 days")
          break
        case "week:3":
          overlay.check(overlay.tile("tileTurns") === "33 | turns in 7 days | Theo 17 · Sora 9 · Hazel 7",
                        "7 days: every day's turns (" + overlay.tile("tileTurns") + ")")
          overlay.check(overlay.tile("tileWake") === "3.2 s | wake to first word | p95 3.2 s · 23 turns",
                        "and every day's wake turns (" + overlay.tile("tileWake") + ")")
          overlay.check(overlay.has("tileWakes", "19 / 8"), "and every day's wakes (" + overlay.tile("tileWakes") + ")")
          overlay.check(overlay.named("wakeBars").highlight === -1, "no current hour over a week")
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          break
        case "idle:1":
          overlay.check(overlay.tile("tileTurns") === "2 | turns today | Theo 2", "one agent's day (" + overlay.tile("tileTurns") + ")")
          overlay.check(overlay.tile("tileWake") === "3.2 s | wake to first word | p95 3.2 s · 1 turn",
                        "a single sample, said as one turn (" + overlay.tile("tileWake") + ")")
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          break
        case "empty:1":
          overlay.check(overlay.tile("tileTurns") === "0 | turns today | none yet", "no turns (" + overlay.tile("tileTurns") + ")")
          overlay.check(overlay.tile("tileWake") === "— | wake to first word | no data yet", "no data, never 0 s (" + overlay.tile("tileWake") + ")")
          overlay.check(overlay.tile("tileTranscribe") === "— | transcription | no data yet", "no transcription data")
          overlay.check(overlay.find(overlay.named("wakeBars"), function(i) { return i.text === "No wakes yet today." }) !== null,
                        "the bars say there is nothing yet")
          overlay.check(overlay.find(overlay.content(), function(i) { return i.chatId !== undefined && i.chatId !== "" }) === null,
                        "no last chat without a saved chat")
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          break
        case "off:1":
          overlay.check(p !== null && p.stats.keeping === true, "keeping, before")
          overlay.put("keepStats", false)
          break
        case "off:2":
          overlay.goTo("display", "")
          break
        case "off:3":
          overlay.goTo("overview", "")
          break
        case "off:5":
          overlay.check(p !== null && p.stats && p.stats.keeping === false, "the CLI reads keepStats off")
          overlay.check(overlay.find(overlay.named("overviewNumbers"), function(i) {
            return i.text !== undefined && String(i.text).indexOf("Usage numbers are off") === 0 }) !== null,
                        "the Overview says nothing new is counted")
          overlay.check(overlay.has("tileTurns", "9 | turns today"), "what was kept is still shown")
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          break
        case "clear:1":
          overlay.goTo("display", "")
          break
        case "clear:2":
          var btn = overlay.named("clearStats")
          overlay.check(btn !== null && btn.enabled, "Clear stats is there, with days to clear")
          overlay.click(btn, "Clear stats")
          break
        case "clear:3":
          var b = overlay.named("clearStats")
          overlay.check(b !== null && b.armed, "the first click only arms it")
          overlay.click(overlay.chip(b, "Cancel"), "Cancel")
          break
        case "clear:4":
          var b2 = overlay.named("clearStats")
          overlay.check(b2 !== null && !b2.armed, "Cancel disarms it")
          overlay.click(b2, "Clear stats again")
          break
        case "clear:5":
          overlay.click(overlay.chip(overlay.named("clearStats"), "Clear"), "Clear")
          break
        case "clear:7":
          var info = overlay.find(overlay.content(), function(i) { return i.text === "No usage numbers kept." })
          overlay.check(info !== null, "afterwards the page says none are kept")
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          break
        }
      }
    }
  }
}
