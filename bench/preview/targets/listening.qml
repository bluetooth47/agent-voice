// The Listening page as a pipeline (master plan M23): four stages, each
// engine's own block shown only for that engine, the second check greyed
// with the reason where there is none, and the gate's speed.
//
//   preview.sh --config bench/preview/configs/agents1.json \
//     --state bench/preview/states/showcase.json --scratch-data \
//     --size 1100x760 --wait 30 --arg sherpa --out /tmp/lis listening
//   grep PREVIEW /tmp/lis.log; cat /tmp/lis.writes
//
// --arg:
//   sherpa    sherpa-onnx listening: its block shows and openWakeWord's does
//             not; the gate goes from Fixed to Follows the room, Fast, Slow
//             and Normal write both rates, the Advanced rates read in dB/s, a
//             custom pair is said, First only greys the second check with
//             the reason; the Decision stage says today's numbers
//   oww       openWakeWord listening: "your voice" is inside its block, the
//             second check is greyed (openWakeWord has none); switching to
//             sherpa-onnx swaps the blocks
//   vosk      Vosk: no engine block, its confidence bar in the Decision stage,
//             the second check greyed
//   missing   sherpa-onnx chosen and not installed: the banner, Vosk standing
//             in, no sherpa-onnx block, the second check greyed with why
//   MODE-shot the page with that engine and the gate following the room,
//             every Advanced open, nothing clicked (for --shots)
//
// The engine and its install are set by the target (the store, through
// --config's scratch shell.json, and the overlay's own probes), so nothing
// depends on what this machine has installed.
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
    function chip(choice, text) {
      return within(choice, function(i) { return i.clicked !== undefined && i.text === text })
    }
    function shown(choice) { var c = named(choice); return c ? c.shown : "missing" }
    function said(text) {
      return find(content(), function(i) { return i.text !== undefined && String(i.text).indexOf(text) >= 0 }) !== null
    }
    function saidIn(name, text) {
      return within(name, function(i) { return i.text !== undefined && String(i.text).indexOf(text) >= 0 }) !== null
    }
    function reason() { var r = named("secondCheckVotes"); return r ? String(r.disabledReason) : "missing" }
    function summary(name) { var b = named(name); return b ? String(b.summary) : "missing" }
    // An AdvancedSection's header is its first child.
    function openAdvanced(name) {
      var a = named(name)
      if (!a) { check(false, "found " + name); return }
      if (!a.expanded) click(a.children[0], name + " header")
    }
    // A property of the overlay itself, set the way a probe would set it. By
    // name: qmllint cannot see the plugin's types from here.
    function poke(name, value) { overlay[name] = value }
    function done() { console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed") }

    property int step: 0
    property int warm: 0
    // The sherpa walk has three steps between 8 and 9 (typing a rate), named
    // 8.5 and 8.75 so the cases after them keep their numbers.
    function key() {
      if (mode !== "sherpa" || step <= 8) return String(step)
      if (step === 9) return "8.5"
      if (step === 10) return "8.75"
      return String(step - 2)
    }

    Timer {
      interval: 2000
      repeat: true
      running: true
      onTriggered: {
        if (!overlay.store.loaded || ++overlay.warm < 3) return
        overlay.step++
        if (overlay.step === 1) {
          overlay.poke("owwAvailable", overlay.mode !== "missing")
          overlay.poke("sherpaAvailable", overlay.mode !== "missing")
          overlay.poke("vWakeDecision", { mode: "either", closed: false, blocked: "", why: "" })
          var engine = overlay.mode === "oww" ? "openwakeword" : overlay.mode === "vosk" ? "vosk" : "sherpa"
          overlay.put("engine", engine)
          if (overlay.shot) overlay.put("adaptiveGate", true)
          return
        }
        if (overlay.shot) {
          if (overlay.step === 2) {
            overlay.openAdvanced("micAdvanced")
            overlay.openAdvanced("checkAdvanced")
            overlay.openAdvanced("alsoSoundsSection")
            if (overlay.pageScroll) overlay.pageScroll.contentY = 0
          } else if (overlay.step > 3 && overlay.pageScroll) {
            // Half a screenful per tick, so --shots N --gap 2 walks the page.
            var f = overlay.pageScroll
            f.contentY = Math.min(f.contentY + f.height * 0.5, Math.max(0, f.contentHeight - f.height))
          }
          return
        }
        switch (overlay.mode + ":" + overlay.key()) {
        // --- sherpa-onnx, and the gate ---
        case "sherpa:2":
          var stages = ["stageMicrophone", "stageListener", "stageCheck", "stageDecision"]
          var all = true
          for (var i = 0; i < stages.length; i++) if (!overlay.named(stages[i])) all = false
          overlay.check(all, "four stages, top to bottom")
          overlay.check(overlay.named("sherpaBlock") !== null, "sherpa-onnx's block shows")
          overlay.check(overlay.named("owwBlock") === null && !overlay.said("Only wake for my voice"),
                        "openWakeWord's block, and your voice, do not")
          overlay.check(overlay.saidIn("sherpaBlock", "Short-name boost"), "the short-name boost is in sherpa-onnx's block")
          overlay.check(overlay.reason() === "" && overlay.named("checkAdvanced") !== null,
                        "the second check is live, with its Advanced")
          overlay.check(overlay.summary("stageListener").indexOf("sherpa-onnx · threshold") === 0,
                        "stage 2 says the engine and its threshold (" + overlay.summary("stageListener") + ")")
          overlay.check(overlay.named("gateSpeedChoice") === null && overlay.named("micAdvanced") === null,
                        "a fixed gate shows no speed and no Advanced")
          overlay.click(overlay.chip("gateChoice", "Follows the room"), "Follows the room")
          break
        case "sherpa:3":
          overlay.check(overlay.setting("adaptiveGate", false) === true, "Follows the room writes adaptiveGate")
          overlay.check(overlay.shown("gateSpeedChoice") === "normal", "the speed shows Normal (" + overlay.shown("gateSpeedChoice") + ")")
          overlay.check(overlay.said("About 30 s to follow a room that gets 10 dB louder"), "and says what Normal means")
          overlay.click(overlay.chip("gateSpeedChoice", "Fast"), "Fast")
          break
        case "sherpa:4":
          overlay.check(overlay.setting("gateRiseTenths", 0) === 15 && overlay.setting("gateFallTenths", 0) === 80,
                        "Fast writes both rates (" + overlay.setting("gateRiseTenths", 0) + ", " + overlay.setting("gateFallTenths", 0) + ")")
          overlay.check(overlay.shown("gateSpeedChoice") === "fast", "and is shown")
          overlay.openAdvanced("micAdvanced")
          break
        case "sherpa:5":
          overlay.check(overlay.saidIn("gateRiseKnob", "1.5 dB/s") && overlay.saidIn("gateFallKnob", "8.0 dB/s"),
                        "the Advanced rates read in dB/s")
          overlay.check(overlay.named("micAdvanced").expanded === true, "the Advanced opened")
          overlay.click(overlay.chip("gateSpeedChoice", "Slow"), "Slow")
          break
        case "sherpa:6":
          overlay.check(overlay.setting("gateRiseTenths", 0) === 2 && overlay.setting("gateFallTenths", 0) === 15,
                        "Slow writes both rates")
          overlay.check(overlay.saidIn("gateRiseKnob", "0.2 dB/s"), "and the knob follows")
          // Set apart by hand, as the Advanced knobs or a hand edit would.
          overlay.put("gateRiseTenths", 7)
          break
        case "sherpa:7":
          overlay.check(overlay.shown("gateSpeedChoice") === "custom", "a pair that is no preset reads as custom")
          overlay.check(overlay.said("Custom: rises 0.7 dB/s and falls 1.5 dB/s"), "and says the pair")
          overlay.click(overlay.chip("gateSpeedChoice", "Normal"), "Normal")
          break
        case "sherpa:8":
          overlay.check(overlay.setting("gateRiseTenths", 0) === 5 && overlay.setting("gateFallTenths", 0) === 30,
                        "Normal puts back the rates it always had")
          // The number beside the knob can be typed into, in dB/s.
          overlay.click(overlay.within("gateRiseKnob", function(i) { return i.text === "0.5 dB/s" }), "the rise rate's number")
          break
        case "sherpa:8.5":
          var entry = overlay.within("gateRiseKnob", function(i) { return i.cursorPosition !== undefined && i.validator })
          overlay.check(entry !== null && entry.validator.regularExpression !== undefined,
                        "clicking the number opens a box that takes a decimal")
          if (entry) { entry.text = "1.2"; entry.accepted() }
          break
        case "sherpa:8.75":
          overlay.check(overlay.setting("gateRiseTenths", 0) === 12, "typing 1.2 writes 12 tenths ("
                        + overlay.setting("gateRiseTenths", 0) + ")")
          overlay.check(overlay.saidIn("gateRiseKnob", "1.2 dB/s"), "and the knob reads 1.2 dB/s")
          overlay.put("gateRiseTenths", 5)
          overlay.click(overlay.chip("decisionChoice", "First only"), "First only")
          break
        case "sherpa:9":
          overlay.check(overlay.reason().indexOf("Off:") === 0, "First only greys the second check, with why (" + overlay.reason() + ")")
          overlay.check(overlay.named("checkAdvanced") === null, "and folds its Advanced away")
          overlay.click(overlay.chip("decisionChoice", "Either stage"), "Either stage")
          break
        case "sherpa:10":
          overlay.check(overlay.reason() === "", "Either stage brings it back")
          var today = overlay.named("todayLine")
          var t = today ? String(today.text) : ""
          overlay.check(t.indexOf("Today: 7 wakes (2 confirmed by the second check)") === 0
                        && t.indexOf("3 rejected by the second check") > 0
                        && t.indexOf("1 held, then dropped") > 0,
                        "the Decision stage says today's numbers (" + t + ")")
          overlay.done()
          break
        // --- openWakeWord ---
        case "oww:2":
          overlay.check(overlay.named("owwBlock") !== null && overlay.saidIn("owwBlock", "Only wake for my voice"),
                        "your voice is inside openWakeWord's block")
          overlay.check(overlay.named("sherpaBlock") === null && !overlay.said("Short-name boost"),
                        "sherpa-onnx's block does not show")
          overlay.check(overlay.reason().indexOf("openWakeWord has no second check") === 0,
                        "the second check is greyed with the reason (" + overlay.reason() + ")")
          overlay.check(overlay.named("checkAdvanced") === null, "with no Advanced")
          overlay.check(!overlay.said("Grammar confidence"), "Vosk's bar is not offered")
          overlay.check(overlay.summary("stageDecision") === "the spotter alone", "stage 4 says the spotter decides alone")
          overlay.click(overlay.chip("engineChoice", "sherpa-onnx"), "sherpa-onnx")
          break
        case "oww:3":
          overlay.check(overlay.setting("engine", "") === "sherpa", "the engine choice writes the engine")
          overlay.check(overlay.named("owwBlock") === null && overlay.named("sherpaBlock") !== null,
                        "switching engines swaps the blocks")
          overlay.check(overlay.reason() === "", "and the second check comes back")
          overlay.done()
          break
        // --- Vosk ---
        case "vosk:2":
          overlay.check(overlay.named("owwBlock") === null && overlay.named("sherpaBlock") === null,
                        "no engine block on Vosk")
          overlay.check(overlay.said("Grammar confidence"), "its confidence bar is drawn")
          overlay.check(overlay.reason().indexOf("Vosk has no second check") === 0,
                        "the second check is greyed with the reason")
          overlay.check(overlay.summary("stageDecision") === "confidence 70%",
                        "stage 4 says the bar (" + overlay.summary("stageDecision") + ")")
          overlay.check(!overlay.said("Detection threshold"), "no other engine's threshold")
          overlay.done()
          break
        // --- an engine that is not installed ---
        case "missing:2":
          overlay.check(overlay.said("sherpa-onnx is not installed, so Vosk is listening instead"), "the banner says so")
          overlay.check(overlay.summary("stageListener").indexOf("Vosk, standing in") === 0,
                        "stage 2 says Vosk is standing in (" + overlay.summary("stageListener") + ")")
          overlay.check(overlay.named("stageListener").tone === "alert", "and is marked")
          overlay.check(overlay.named("sherpaBlock") === null, "no sherpa-onnx block for an engine not running")
          overlay.check(overlay.reason().indexOf("sherpa-onnx is not installed") === 0,
                        "the second check is greyed with why (" + overlay.reason() + ")")
          overlay.check(overlay.said("Grammar confidence"), "Vosk's bar is offered, since Vosk is what listens")
          overlay.done()
          break
        }
      }
    }
  }
}
