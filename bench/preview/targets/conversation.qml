// The Conversation page (master plan M24): pace presets as a compact selector,
// four cards, the turn drawn from the live values, the timings folded under
// it, the open mic's live state with a button that says why when it cannot,
// the limit note and its link, and the commands read from the daemon.
//
//   preview.sh --config bench/preview/configs/conversation.json \
//     --state bench/preview/states/showcase.json --scratch-data \
//     --size 1100x760 --wait 30 --out /tmp/conv conversation
//   grep PREVIEW /tmp/conv.log; cat /tmp/conv.writes
//
// The config stores maxUtteranceMs as the string "90000", which the daemon
// reads as 90000 (int()), so the page must too.
//
// --arg:
//   walk        (default) the whole page, clicked and checked
//   shot        the page with every fold open and the open mic on, nothing
//               clicked, scrolled half a screenful per tick (for --shots)
import QtQuick
import QtTest
import Quickshell
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    Component.onCompleted: overlay.open('{"page":"conversation"}')

    TestEvent { id: input }

    readonly property string arg: Quickshell.env("PREVIEW_ARG") || "walk"
    readonly property bool shot: arg === "shot"
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
    // Not `visible`-filtered: a folded section's children are the point of
    // some checks.
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
    function named(name) { return find(content(), function(i) { return i.objectName === name }) }
    function anyNamed(name) { return findAny(content(), function(i) { return i.objectName === name }) }
    function within(name, test) { return find(named(name), test) }
    function click(item, label) {
      if (!item) { check(false, "found " + label); return }
      var flick = overlay.pageScroll
      if (flick && content()) {
        var y = item.mapToItem(content(), 0, 0).y
        flick.contentY = Math.max(0, Math.min(y - 160, flick.contentHeight - flick.height))
      }
      input.mouseClick(item, item.width / 2, item.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
    }
    function said(text) {
      return find(content(), function(i) { return i.text !== undefined && String(i.text).indexOf(text) >= 0 }) !== null
    }
    function saidIn(name, text) {
      return within(name, function(i) { return i.text !== undefined && String(i.text).indexOf(text) >= 0 }) !== null
    }
    function textOf(name) { var n = named(name); return n ? String(n.text) : "missing" }
    function poke(name, value) { overlay[name] = value }
    function done() { console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed") }
    // Open (or close) a fold: its header is its first child.
    function fold(name, open) {
      var a = anyNamed(name)
      if (!a) { check(false, "found " + name); return }
      if (a.expanded !== open) click(a.children[0], name + " header")
    }
    // The page's own members, by name, so qmllint need not know them.
    function pageItem() { return named("conversationPage") }
    // A CompactSelector's MenuList is a Popup: in `data`, not `children`.
    function menuOf(sel) {
      var d = sel ? sel.data : []
      for (var i = 0; i < d.length; i++) if (d[i] && d[i].entries !== undefined && d[i].choose !== undefined) return d[i]
      return null
    }
    function openPace() { click(named("paceChoice"), "the pace selector") }
    function choosePace(value) {
      var m = menuOf(named("paceChoice"))
      check(m !== null && m.opened, "the pace menu opened")
      if (!m) return
      for (var i = 0; i < m.entries.length; i++) {
        var e = m.entries[i]
        if (String((e !== null && typeof e === "object") ? e.value : e) === value) { m.choose(i); return }
      }
      check(false, value + " is offered")
    }
    function offered() {
      var m = menuOf(named("paceChoice")), out = []
      if (m) for (var i = 0; i < m.entries.length; i++) out.push(String(m.entries[i].value))
      return out.join(",")
    }
    function segment(key) {
      var t = named("turnTimeline")
      if (!t) return null
      for (var i = 0; i < t.segments.length; i++) if (t.segments[i].key === key) return t.segments[i]
      return null
    }
    function inView(item) {
      var f = overlay.pageScroll
      if (!f || !item) return false
      var y = item.mapToItem(f.contentItem, 0, 0).y
      return y >= f.contentY - 1 && y + item.height <= f.contentY + f.height + 1
    }

    property int step: 0
    property int warm: 0

    Timer {
      interval: 2000
      repeat: true
      running: true
      onTriggered: {
        if (!overlay.store.loaded || ++overlay.warm < 3) return
        overlay.step++
        var now = Date.now() / 1000
        var d = new Date()
        var today = d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2)
        if (overlay.step === 1) {
          // The service running, the open mic on with eight and a half
          // minutes left, three turns cut today.
          overlay.poke("vOpenMic", { who: "Theo", until: now + 8 * 60 + 30 })
          overlay.poke("vLimitHits", { date: today, today: 3, last: now - 3600 })
          return
        }
        if (overlay.shot) {
          if (overlay.step === 2) {
            overlay.fold("timingsAdvanced", true)
            overlay.fold("overAdvanced", true)
            overlay.fold("commandList", true)
            if (overlay.pageScroll) overlay.pageScroll.contentY = 0
          } else if (overlay.step > 3 && overlay.pageScroll) {
            var f = overlay.pageScroll
            f.contentY = Math.min(f.contentY + f.height * 0.5, Math.max(0, f.contentHeight - f.height))
          }
          return
        }
        switch (overlay.step) {
        case 2:
          var cards = ["followCard", "openMicCard", "workCard", "overCard", "stopsCard", "turnCard", "commandsCard"]
          var all = true
          for (var i = 0; i < cards.length; i++) if (!overlay.named(cards[i])) all = false
          overlay.check(all, "the seven cards are there")
          overlay.check(overlay.named("paceChoice") !== null && overlay.named("paceChoice").shown === "balanced",
                        "Pace is a compact selector and reads Balanced from the stored values (" + (overlay.named("paceChoice") ? overlay.named("paceChoice").shown : "missing") + ")")
          // maxUtteranceMs is the string "90000" in this config.
          var talk = overlay.segment("talk")
          overlay.check(talk !== null && talk.note === "up to 90 s from your first word",
                        "a timing stored as the string \"90000\" is read as 90 s (" + (talk ? talk.note : "missing") + ")")
          var lead = overlay.segment("leadin"), pause = overlay.segment("pause"), follow = overlay.segment("follow")
          overlay.check(lead !== null && lead.note === "up to 5 s for you to start"
                        && pause !== null && pause.note === "1.2 s of quiet ends it, 800 ms after a finished sentence"
                        && follow !== null && follow.note === "listens 7 s without the wake word",
                        "the turn is drawn from the live values")
          overlay.check(overlay.named("seg-follow") !== null && overlay.named("seg-talk") !== null,
                        "and the blocks are on screen")
          overlay.check(overlay.within("seg-talk", function(i) { return i.objectName === "limitMark" && i.visible === true }) !== null
                        && overlay.within("seg-leadin", function(i) { return i.objectName === "limitMark" }) === null,
                        "where turns were cut today is marked on the turn")
          overlay.check(overlay.textOf("openMicLine") === "On with Theo · 9 min left"
                        || overlay.textOf("openMicLine") === "On with Theo · 8 min left",
                        "the open mic says it is on, with the time left (" + overlay.textOf("openMicLine") + ")")
          overlay.check(overlay.named("openMicButton") !== null && overlay.named("openMicButton").text === "Turn off"
                        && overlay.named("openMicButton").enabled === true, "its button says Turn off")
          overlay.check(overlay.said("3 turns today hit the limit, the last at "), "the limit note counts today's turns")
          overlay.check(overlay.named("timingsAdvanced") !== null && overlay.named("timingsAdvanced").expanded === false
                        && overlay.named("timingsAdvanced").count === 6, "the six timings are folded away")
          overlay.check(overlay.named("overAdvanced") !== null && overlay.named("overAdvanced").expanded === false,
                        "so is how much louder you must be")
          overlay.check(overlay.said("Three different stops"), "the three stops are kept apart")
          overlay.check(overlay.said("Turn off open mic") && overlay.said("Stop a reply") && overlay.said("Stop the service"),
                        "and each is named")
          overlay.fold("commandList", true)
          break
        case 3:
          var list = overlay.named("commandList")
          overlay.check(list !== null && list.count === 10, "the command table is read from the daemon (" + (list ? list.count : "missing") + ")")
          overlay.check(overlay.named("command-open_mic") !== null && overlay.named("command-stop") !== null,
                        "each command is listed")
          overlay.check(overlay.said("Open mic on.") === false && overlay.said("Listens without the wake word"),
                        "with what it does, from the table")
          overlay.check(overlay.saidIn("commandsRow", "Take notes, and keep listening."),
                        "the example is built from the table's own phrase")
          overlay.check(overlay.said("Say “keep listening” to start it and “stop listening” to end it."),
                        "and so is the open mic's note")
          // Edges: the open mic fires at the start or end of a sentence, Stop only alone.
          var stopPill = overlay.within("command-stop", function(i) { return i.tone !== undefined && i.text === "on its own" })
          var openPill = overlay.within("command-open_mic", function(i) { return i.tone !== undefined && i.text.indexOf("at the start") >= 0 })
          overlay.check(stopPill !== null, "Stop is marked on its own")
          overlay.check(openPill !== null && openPill.text === "on its own, at the start, at the end",
                        "the open mic works at the edges in this mode (" + (openPill ? openPill.text : "missing") + ")")
          overlay.fold("commandList", false)
          // The link on the limit note.
          overlay.click(overlay.named("raiseIt"), "Raise it")
          break
        case 4:
          var adv = overlay.named("timingsAdvanced")
          overlay.check(adv !== null && adv.expanded === true, "Raise it opens the timings")
          overlay.check(overlay.setting("maxUtteranceMs", 0) === "90000" || Number(overlay.setting("maxUtteranceMs", 0)) === 90000,
                        "and writes nothing")
          var knob = overlay.named("maxKnob")
          overlay.check(knob !== null && overlay.inView(knob), "the longest-turn control is scrolled into view")
          overlay.check(knob !== null && knob.value === 90000, "and reads the stored string as 90000 (" + (knob ? knob.value : "missing") + ")")
          overlay.check(overlay.focusKey === "", "the request is taken, so asking again is a change again")
          overlay.check(overlay.named("timingsAdvanced").expanded === true, "still open")
          // Shut, and asked for from outside: a deep link with a focus.
          overlay.fold("timingsAdvanced", false)
          break
        case 5:
          overlay.check(overlay.named("timingsAdvanced").expanded === false, "shut again")
          overlay.open('{"page":"conversation","focus":"echoTailMs"}')
          break
        case 6:
          overlay.check(overlay.named("timingsAdvanced") !== null && overlay.named("timingsAdvanced").expanded === true,
                        "a deep link with a focus opens the timings")
          overlay.check(overlay.inView(overlay.named("echoKnob")), "and scrolls to that control")
          overlay.fold("timingsAdvanced", false)
          break
        case 7:
          overlay.open('{"page":"conversation","focus":"not a key; rm -rf"}')
          break
        case 8:
          overlay.check(overlay.focusKey === "", "a focus that is not a setting's key is dropped")
          overlay.check(overlay.named("timingsAdvanced") !== null && overlay.named("timingsAdvanced").expanded === false,
                        "and opens nothing")
          overlay.open('{"page":"conversation","focus":"bargeFactor"}')
          break
        case 9:
          overlay.check(overlay.named("timingsAdvanced").expanded === false, "a key that is not one of the timings opens nothing")
          // The open mic. A deep link reloads the state file, which says it
          // is closed (the preview's state has no open mic), so it is put
          // back, the way the daemon would say it.
          overlay.poke("vOpenMic", { who: "Theo", until: now + 5 * 60 })
          overlay.check(overlay.named("openMicButton").text === "Turn off", "open again, the button says Turn off")
          overlay.click(overlay.named("openMicButton"), "Turn off")
          break
        case 10:
          overlay.poke("vOpenMic", ({}))
          break
        case 11:
          overlay.check(overlay.textOf("openMicLine") === "Off. It needs the wake word.", "closed, the line says so (" + overlay.textOf("openMicLine") + ")")
          overlay.check(overlay.named("openMicButton").text === "Turn on", "and the button says Turn on")
          overlay.click(overlay.named("openMicButton"), "Turn on")
          break
        case 12:
          // The service stops: the button cannot work, and says why.
          overlay.poke("serviceActive", false)
          overlay.check(overlay.named("openMicButton").enabled === false, "with the service stopped the button is off")
          overlay.check(overlay.textOf("openMicWhy").indexOf("Start the service first") === 0,
                        "and says why (" + overlay.textOf("openMicWhy") + ")")
          overlay.check(overlay.textOf("openMicLine") === "The service is not running.", "the line says the service is not running")
          overlay.poke("serviceActive", true)
          break
        case 13:
          overlay.check(overlay.textOf("openMicWhy") === "missing" || overlay.textOf("openMicWhy") === "", "the reason goes when the service is back")
          // Pace, by the real menu.
          overlay.openPace()
          break
        case 14:
          overlay.check(overlay.offered() === "patient,balanced,snappy", "the selector offers the three presets (" + overlay.offered() + ")")
          overlay.choosePace("snappy")
          break
        case 15:
          overlay.check(overlay.setting("leadInMs", 0) === 3500 && overlay.setting("trailingSilenceMs", 0) === 800
                        && overlay.setting("quickEndMs", 0) === 500 && overlay.setting("followUpMs", 0) === 5000,
                        "Snappy writes the same four timings as before")
          overlay.check(overlay.named("paceChoice").shown === "snappy", "and the selector shows Snappy")
          overlay.check(overlay.segment("leadin").note === "up to 3500 ms for you to start"
                        || overlay.segment("leadin").note === "up to 3.5 s for you to start",
                        "the turn follows it (" + overlay.segment("leadin").note + ")")
          overlay.put("followUpMs", 9000)
          break
        case 16:
          overlay.check(overlay.named("paceChoice").shown === "custom", "a timing moved by hand reads as Custom")
          overlay.openPace()
          break
        case 17:
          overlay.check(overlay.offered() === "patient,balanced,snappy,custom", "and Custom is listed, to say so (" + overlay.offered() + ")")
          overlay.done()
          break
        }
      }
    }
  }
}
