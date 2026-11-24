// First-run setup (master plan M28): offered by itself on a fresh install
// and never on a configured one; each step writing only what is changed in
// it; Skip writing nothing; the marker; the Overview's reminder.
//
// A fresh install (no settings, no agent folder, the service never started):
//   preview.sh --config bench/preview/configs/fresh.json --service-off \
//     --size 1100x760 --wait 30 --arg fresh --out /tmp/setup setup
// A configured one, also with the service off:
//   preview.sh --config bench/preview/configs/crew3.json --service-off \
//     --size 1100x760 --wait 20 --arg configured --out /tmp/setup setup
// The four steps with the service running, from About's "Run setup again":
//   preview.sh --config bench/preview/configs/fresh.json --state \
//     bench/preview/states/showcase.json --size 1100x760 --wait 40 \
//     --arg walk --out /tmp/setup setup
// A marker from an earlier skip, and "Not now":
//   preview.sh --config bench/preview/configs/fresh.json --service-off \
//     --size 1100x760 --wait 20 --arg reminder --out /tmp/setup setup
//   grep PREVIEW /tmp/setup.log; cat /tmp/setup.writes /tmp/setup.setup.json
//
// --arg mic|wake|agent|done (with --state) opens that step for a screenshot.
// Nothing real is touched: settings go to the scratch shell.json, the marker
// to the scratch XDG_STATE_HOME, `agentvoice toggle` and `wake-test` to the
// write log, and the programs found are preview.sh's fake claude and codex.
import QtQuick
import QtTest
import Quickshell
import Quickshell.Io
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    readonly property string want: (Quickshell.env("PREVIEW_ARG") || "fresh").split(",")[0]
    // ",narrow" on the argument draws the card itself 500px wide, for a
    // screenshot of the narrow layout (a --size crop only cuts a wide one).
    readonly property bool narrow: (Quickshell.env("PREVIEW_ARG") || "").indexOf(",narrow") >= 0
    Timer {
      interval: 400; running: true
      onTriggered: {
        if (!overlay.narrow) return
        for (var i = overlay.pageScroll; i; i = i.parent)
          if (i.objectName === "settingsCard") { i.width = 500; return }
      }
    }
    readonly property string runDir: (Quickshell.env("XDG_RUNTIME_DIR") || "/nonexistent") + "/agentvoice"
    Component.onCompleted: {
      if (want === "reminder") markerWriter.running = true
      // A fresh machine may have no state folder at all: the marker's first
      // save has to make it.
      else if (want === "fresh") stateRemover.running = true
      else if (["mic", "wake", "agent", "done"].indexOf(want) >= 0) overlay.open('{"mode":"setup","step":"' + want + '"}')
      else if (want === "walk") overlay.open('{"page":"about"}')
      else overlay.open("{}")
    }
    // An earlier skip at step 2, written before the overlay opens.
    Process {
      id: markerWriter
      command: ["sh", "-c", "mkdir -p \"$XDG_STATE_HOME/agentvoice\" && printf '%s\\n' " +
                "'{\"version\": 1, \"status\": \"skipped\", \"step\": \"wake\", \"at\": \"2026-11-23T10:00:00Z\"}' " +
                "> \"$XDG_STATE_HOME/agentvoice/setup.json\""]
      onExited: overlay.open("{}")
    }

    Process {
      id: stateRemover
      command: ["sh", "-c", "rm -rf \"$XDG_STATE_HOME/agentvoice\""]
      onExited: overlay.open("{}")
    }

    TestEvent { id: input }
    property var keys: null
    function keyEvents() {
      if (!overlay.keys) overlay.keys = Qt.createQmlObject("import QtTest; TestEvent {}", overlay.pageScroll.contentItem)
      return overlay.keys
    }
    function typeKeys(t) {
      for (var i = 0; i < t.length; i++) keyEvents().keyClick(t.toUpperCase().charCodeAt(i), Qt.NoModifier, -1)
    }

    property int passed: 0
    property int failed: 0
    function check(ok, what) {
      if (ok) passed++; else failed++
      console.warn("PREVIEW " + (ok ? "PASS " : "FAIL ") + what)
    }
    function findIn(item, test) {
      if (!item || item.visible === false) return null
      if (test(item)) return item
      var kids = item.children || []
      for (var i = 0; i < kids.length; i++) {
        var hit = findIn(kids[i], test)
        if (hit) return hit
      }
      return null
    }
    function windowRoot() {
      var i = overlay.pageScroll
      while (i && i.parent) i = i.parent
      return i
    }
    function byName(name) { return findIn(windowRoot(), function(i) { return i.objectName === name }) }
    function textHas(needle) {
      return findIn(windowRoot(), function(i) { return i.text !== undefined && i.clicked === undefined
                                                       && String(i.text).indexOf(needle) >= 0 })
    }
    function click(item, label) {
      if (!item) { check(false, "found " + label); return }
      console.warn("PREVIEW click " + label)
      input.mouseClick(item, item.width / 2, item.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
    }
    // A chip of a SegmentedChoice, or a Button, by its text.
    function chip(parent, label) {
      return findIn(parent, function(i) { return i.clicked !== undefined && i.text === label })
    }

    property string writes: ""
    property string marker: ""
    Process {
      id: reader
      command: ["sh", "-c", "cat \"$PREVIEW_WRITES\" 2>/dev/null; echo '---MARKER---'; " +
                "cat \"$XDG_STATE_HOME/agentvoice/setup.json\" 2>/dev/null"]
      stdout: StdioCollector {
        onStreamFinished: {
          var parts = String(text).split("---MARKER---")
          overlay.writes = parts[0].trim()
          overlay.marker = (parts[1] || "").trim()
        }
      }
    }
    function readBack() { reader.running = true }
    function setsOf() { return overlay.writes.split("\n").filter(function(l) { return l.indexOf("bar set") >= 0 }) }
    function markerSays(status, step) {
      try { var d = JSON.parse(overlay.marker); return d.status === status && (!step || d.step === step) }
      catch (e) { return false }
    }
    // A fake wake test, as the daemon would write it beside the state.
    Process { id: testWriter }
    function writeTest(json) {
      testWriter.command = ["sh", "-c", "printf '%s' \"$1\" > \"$2/wake-test.json\"", "sh", json, overlay.runDir]
      testWriter.running = true
    }

    property int step: 0
    property int warm: 0
    Timer {
      interval: 1000
      repeat: true
      running: true
      onTriggered: {
        if (!overlay.store.loaded || ++overlay.warm < 4) return
        overlay.step++
        if (["mic", "wake", "agent", "done"].indexOf(overlay.want) >= 0) return
        if (overlay.want === "fresh") overlay.fresh()
        else if (overlay.want === "configured") overlay.configured()
        else if (overlay.want === "reminder") overlay.reminder()
        else if (overlay.want === "walk") overlay.walk()
      }
    }

    function done() { console.warn("PREVIEW DONE " + passed + " passed, " + failed + " failed") }

    function fresh() {
      switch (step) {
      case 1:
        check(mode === "setup", "a fresh install opens setup by itself (" + mode + ")")
        check(setupStep === "mic", "at the microphone")
        check(byName("setupStart") !== null, "with a button to start the service, since nothing has started it")
        check(textHas("no reading — start Agent Voice") !== null, "and a meter that says why it is empty")
        readBack()
        break
      case 2:
        check(setsOf().length === 0, "opening setup wrote no setting (" + setsOf().join(" | ") + ")")
        check(markerSays("open", "mic"), "the marker says it was shown (" + marker + ")")
        click(byName("setupStart"), "Start Agent Voice")
        break
      case 3:
        readBack()
        break
      case 4:
        check(writes.indexOf("agentvoice toggle") >= 0, "Start Agent Voice starts the service, once asked")
        click(byName("setupSkip"), "Skip setup")
        break
      case 5:
        check(mode === "settings" && page === "overview", "Skip goes to the Overview")
        check(byName("setupReminder") !== null, "where a line offers to finish setting up")
        readBack()
        break
      case 6:
        check(setsOf().length === 0, "skipping wrote no setting")
        check(markerSays("skipped", "mic"), "the marker says skipped, at the microphone (" + marker + ")")
        // Summoned again: setup is not put up again by itself.
        close()
        open("{}")
        break
      case 8:
        check(mode === "settings" && page === "overview", "summoned again, setup does not come back by itself")
        done()
        break
      }
    }

    function configured() {
      switch (step) {
      case 2:
        check(!serviceActive && serviceKnown, "the service is known to be off")
        check(folders.foldersRead, "the folders were read")
        check(mode === "settings" && page === "overview", "a configured install is not taken over by setup")
        check(!setupFresh, "and is not called fresh")
        readBack()
        break
      case 3:
        check(marker === "", "no marker was written (" + marker + ")")
        check(byName("setupReminder") === null, "and nothing reminds anyone about setup")
        done()
        break
      }
    }

    function reminder() {
      switch (step) {
      case 1:
        check(mode === "settings" && page === "overview", "a marker from an earlier skip keeps setup from opening by itself")
        check(byName("setupReminder") !== null, "the Overview offers to finish it")
        check(textHas("Left at step 2 of 4") !== null, "from where it was left")
        click(byName("setupNotNow"), "Not now")
        break
      case 2:
        check(byName("setupReminder") === null, "Not now hides it")
        readBack()
        break
      case 3:
        check(markerSays("dismissed", "wake"), "and the marker says dismissed (" + marker + ")")
        check(setsOf().length === 0, "and no setting was written")
        goTo("about", "")
        break
      case 4:
        click(byName("runSetup"), "Run setup again")
        break
      case 5:
        check(mode === "setup" && setupStep === "mic", "About's Run setup again opens it at the start")
        done()
        break
      }
    }

    function walk() {
      switch (step) {
      case 1:
        check(page === "about" && byName("runSetup") !== null, "About has Run setup again")
        click(byName("runSetup"), "Run setup again")
        break
      case 2:
        check(mode === "setup" && setupStep === "mic", "it opens at the microphone")
        check(byName("setupStart") === null, "the service is running, so no start button")
        check(byName("setupMeter") !== null && byName("setupMeter").live, "the meter shows the level")
        click(chip(byName("setupGateChoice"), "Follows the room"), "Follows the room")
        break
      case 3:
        click(byName("setupNext"), "Next")
        break
      case 4:
        check(setupStep === "wake", "Next goes to the wake word")
        click(chip(byName("setupWake"), "Vosk"), "Vosk (already chosen)")
        click(chip(byName("setupWake"), "hey agent"), "the phrase “hey agent”")
        // Another test's result left in the file, as the Listening page's
        // would be: not this test's, so never shown as its result.
        writeTest('{"status": "done", "attempts": 10, "hits": 10, "target": 10, "peak_db": -30, "gate_db": -38}')
        break
      case 5:
        check(textHas("tries woke it") === null, "an earlier test's result is not shown as this one's")
        check(String(setting("phrase", "")) === "hey agent", "the phrase is “hey agent”")
        check(textHas("Say “hey agent” three times") !== null, "the test asks for the new phrase")
        click(byName("setupTestButton"), "Start the test")
        break
      case 6:
        var su = findIn(windowRoot(), function(i) { return i.sawRunning !== undefined && i.tries !== undefined })
        check(su !== null && su.testing && su.attempts === 0, "after Start the old result still counts for nothing")
        writeTest('{"status": "running", "attempts": 1, "hits": 1, "target": 10, "peak_db": -30, "gate_db": -38}')
        break
      case 8:
        check(textHas("1 of 3 tries so far") !== null, "it counts the tries")
        writeTest('{"status": "running", "attempts": 3, "hits": 2, "target": 10, "peak_db": -30, "gate_db": -38}')
        break
      case 10:
        writeTest('{"status": "stopped", "attempts": 3, "hits": 2, "target": 10, "peak_db": -30, "gate_db": -38}')
        break
      case 12:
        check(textHas("2 of 3 tries woke it") !== null, "after three tries it stops and says how it went")
        check(byName("setupTestButton").text === "Try again", "and offers to try again")
        readBack()
        break
      case 13:
        check(writes.indexOf("agentvoice wake-test start") >= 0 && writes.indexOf("agentvoice wake-test stop") >= 0,
              "the daemon's wake test was started, and stopped after three")
        click(byName("setupNext"), "Next")
        break
      case 15:
        check(setupStep === "agent", "Next goes to the agent")
        check(chip(byName("setupAgent"), "Codex") !== null && chip(byName("setupAgent"), "Claude Code") !== null,
              "the programs found are offered (preview.sh's fake claude and codex)")
        check(textHas("Not found here:") !== null, "and the ones not found are named")
        click(chip(byName("setupAgent"), "Codex"), "Codex")
        break
      case 16:
        var f = findIn(byName("setupName"), function(i) { return i.placeholderText !== undefined })
        if (f) f.forceActiveFocus()
        typeKeys("ada")
        keyEvents().keyClick(Qt.Key_Return, Qt.NoModifier, -1)
        break
      case 17:
        click(byName("setupNext"), "Next")
        break
      case 18:
        check(setupStep === "done", "Next goes to done")
        check(textHas("Ada, on Codex") !== null || textHas("ada, on Codex") !== null, "done says who answers and on what")
        check(textHas("the gate follows the room") !== null, "and the gate")
        click(byName("setupNext"), "Open the settings")
        break
      case 19:
        check(mode === "settings" && page === "overview", "Open the settings leaves setup for the Overview")
        check(byName("setupReminder") === null, "with nothing left to finish")
        readBack()
        break
      case 20:
        var sets = setsOf()
        var keys = sets.map(function(l) { return l.split(" ")[3] })
        check(keys.join(",") === "adaptiveGate,phrase,mainProgram,mainName",
              "exactly four settings were written, each one changed here (" + keys.join(",") + ")")
        check(sets.every(function(l) { return l.indexOf("duaneoca.agentvoice") >= 0 }), "all through the widget's own entry")
        check(markerSays("done", "done"), "the marker says done (" + marker + ")")
        done()
        break
      }
    }
  }
}
