// "When a wake counts" on the Listening page (master plan M22): the three
// choices, the refused one, and wakes held closed.
//
//   preview.sh --config bench/preview/configs/agents1.json \
//     --state bench/preview/states/showcase.json --size 1100x760 \
//     --wait 24 --arg sherpa --out /tmp/dec decision
//   grep PREVIEW /tmp/dec.log; cat /tmp/dec.writes
//
// --arg:
//   sherpa    sherpa-onnx listening: Either stage is shown (the default);
//             Both must agree writes wakeCrossCheck and wakeBothAgree, First
//             only writes both off, Either stage puts it back
//   refused   openWakeWord listening: Both must agree is refused with the
//             reason and writes nothing; a second click is not swallowed;
//             switching to sherpa-onnx clears the reason, and Both is taken
//   novosk    sherpa-onnx with the second check voting with Vosk alone and
//             the daemon saying the Vosk model is missing: refused, with the
//             daemon's reason
//   closed    the daemon says both is chosen and cannot run: the page says
//             wakes are held closed, the Overview lists it under what needs
//             attention, and Either stage is a way out
//   MODE-shot the page at the selector, nothing clicked (for screenshots)
//
// The engine and the daemon's word are set by the target (the store, through
// --config's scratch shell.json; `vWakeDecision` as the state file would set
// it), so nothing depends on what this machine has installed.
import QtQuick
import QtTest
import Quickshell
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    Component.onCompleted: overlay.open('{"page":"listening"}')

    TestEvent { id: input }

    readonly property string arg: Quickshell.env("PREVIEW_ARG") || "sherpa"
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
    function chip(text) {
      return find(named("decisionChoice"), function(i) { return i.clicked !== undefined && i.text === text })
    }
    function lp() { return named("listeningPage") }
    function shown() { var c = named("decisionChoice"); return c ? c.shown : "missing" }
    function refusedText() { var t = named("decisionRefused"); return t ? String(t.text) : "" }
    function said(text) {
      return find(content(), function(i) { return i.text !== undefined && String(i.text).indexOf(text) >= 0 }) !== null
    }
    // A property of the overlay itself, set the way the state file or a scan
    // would set it. By name: qmllint cannot see the plugin's types from here.
    function poke(name, value) { overlay[name] = value }
    function done() { console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed") }

    property int step: 0
    property int warm: 0

    Timer {
      interval: 2000
      repeat: true
      running: true
      onTriggered: {
        if (!overlay.store.loaded || ++overlay.warm < 3) return
        overlay.step++
        if (overlay.step === 1) {
          // What the page is drawn against: the engine and its install, and
          // what the daemon would say about it.
          overlay.poke("sherpaAvailable", true)
          overlay.poke("owwAvailable", true)
          var engine = overlay.mode === "refused" || overlay.mode === "closed" ? "openwakeword" : "sherpa"
          overlay.put("engine", engine)
          if (overlay.mode === "novosk") {
            overlay.put("crossCheckEngines", "vosk")
            overlay.poke("vWakeDecision", { mode: "either", closed: false, blocked: "no-vosk",
                                      why: "the second check votes with Vosk, which is not installed" })
          } else if (overlay.mode === "closed") {
            overlay.put("wakeBothAgree", true)
            overlay.poke("vWakeDecision", { mode: "both", closed: true, blocked: "oww",
                                      why: "openWakeWord has no second check" })
          } else {
            overlay.poke("vWakeDecision", { mode: "either", closed: false,
                                      blocked: engine === "sherpa" ? "" : "oww",
                                      why: engine === "sherpa" ? "" : "openWakeWord has no second check" })
          }
          return
        }
        if (overlay.shot) {
          if (overlay.step === 2) {
            var c = overlay.named("decisionChoice")
            if (c && overlay.pageScroll)
              overlay.pageScroll.contentY = Math.max(0, c.mapToItem(overlay.content(), 0, 0).y - 260)
          }
          return
        }
        switch (overlay.mode + ":" + overlay.step) {
        case "sherpa:2":
          overlay.check(overlay.shown() === "either", "Either stage is the default (" + overlay.shown() + ")")
          overlay.check(overlay.said("rescues a short name"), "the hint says what Either stage does")
          overlay.click(overlay.chip("Both must agree"), "Both must agree")
          break
        case "sherpa:3":
          overlay.check(overlay.setting("wakeBothAgree", false) === true
                        && overlay.setting("wakeCrossCheck", false) === true,
                        "Both must agree writes both keys on")
          overlay.check(overlay.shown() === "both" && overlay.refusedText() === "", "and is shown, not refused")
          overlay.check(overlay.said("about 0.8 s later"), "the hint says what it costs")
          overlay.click(overlay.chip("First only"), "First only")
          break
        case "sherpa:4":
          overlay.check(overlay.setting("wakeBothAgree", true) === false
                        && overlay.setting("wakeCrossCheck", true) === false,
                        "First only writes both keys off")
          overlay.check(overlay.shown() === "first", "and is shown (" + overlay.shown() + ")")
          overlay.click(overlay.chip("Either stage"), "Either stage")
          break
        case "sherpa:5":
          overlay.check(overlay.setting("wakeBothAgree", true) === false
                        && overlay.setting("wakeCrossCheck", false) === true,
                        "Either stage: the second check on, both off")
          overlay.check(overlay.shown() === "either", "and is shown (" + overlay.shown() + ")")
          overlay.done()
          break
        case "refused:2":
          overlay.check(overlay.shown() === "either", "Either stage, as set")
          overlay.check(overlay.said("openWakeWord has no second check, so it decides alone"),
                        "the hint says the engine decides alone")
          overlay.click(overlay.chip("Both must agree"), "Both must agree")
          break
        case "refused:3":
          overlay.check(overlay.refusedText().indexOf("Not chosen: openWakeWord has no second check") === 0,
                        "refused, with the reason (" + overlay.refusedText() + ")")
          overlay.check(overlay.setting("wakeBothAgree", false) !== true, "and nothing written")
          overlay.check(overlay.shown() === "either", "the chip goes back to what is set (" + overlay.shown() + ")")
          // Cleared by hand, so the next click has to say it again.
          overlay.lp().decisionRefused = ""
          overlay.click(overlay.chip("Both must agree"), "Both must agree, again")
          break
        case "refused:4":
          overlay.check(overlay.refusedText() !== "", "a second click is not swallowed")
          overlay.check(overlay.setting("wakeBothAgree", false) !== true, "still nothing written")
          overlay.put("engine", "sherpa")
          overlay.poke("vWakeDecision", { mode: "either", closed: false, blocked: "", why: "" })
          break
        case "refused:5":
          overlay.check(overlay.refusedText() === "", "the reason goes with its cause")
          overlay.click(overlay.chip("Both must agree"), "Both must agree on sherpa-onnx")
          break
        case "refused:6":
          overlay.check(overlay.setting("wakeBothAgree", false) === true && overlay.shown() === "both",
                        "on sherpa-onnx it is taken")
          overlay.done()
          break
        case "novosk:2":
          overlay.click(overlay.chip("Both must agree"), "Both must agree")
          break
        case "novosk:3":
          overlay.check(overlay.refusedText().indexOf("Vosk, which is not installed") > 0,
                        "refused with the daemon's reason (" + overlay.refusedText() + ")")
          overlay.check(overlay.setting("wakeBothAgree", false) !== true, "and nothing written")
          overlay.done()
          break
        case "closed:2":
          var line = overlay.named("decisionClosed")
          overlay.check(line !== null && String(line.text).indexOf(
                          "Wakes are held closed: both stages must agree, and openWakeWord has no second check") === 0,
                        "the page says wakes are held closed, and why")
          overlay.check(overlay.shown() === "both", "Both must agree is what is set")
          var listed = false
          for (var i = 0; i < overlay.problems.length; i++)
            if (String(overlay.problems[i].text).indexOf("Wakes are held closed") === 0
                && overlay.problems[i].page === "listening") listed = true
          overlay.check(listed, "and it is listed under what needs attention, linking here")
          overlay.goTo("overview", "")
          break
        case "closed:3":
          overlay.check(overlay.said("Wakes are held closed: both stages must agree"),
                        "the Overview shows it")
          overlay.goTo("listening", "")
          break
        case "closed:4":
          overlay.click(overlay.chip("Either stage"), "Either stage")
          break
        case "closed:5":
          overlay.check(overlay.setting("wakeBothAgree", true) === false
                        && overlay.setting("wakeCrossCheck", false) === true,
                        "Either stage is a way out")
          overlay.done()
          break
        }
      }
    }
  }
}
