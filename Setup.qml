import QtQuick
import QtQuick.Controls as QQC
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "ui"

// First-run setup (master plan M28, feedback item 22): a short walk through
// the three things a fresh install needs -- a microphone gate that suits the
// room, a wake word that wakes it, and an agent to answer -- then done.
//
// Drawn by the settings overlay in place of the sidebar and page while its
// mode is "setup" (Settings.qml says when that is). Not a page: it changes
// keys whose home is a page, through the overlay's own put(), and that is
// the documented exception in tests/test_settings_pages.py, which holds it
// to exactly these seven keys:
//
//   adaptiveGate, micThresholdDb     the Listening page's
//   engine, phrase, owwModel         the Listening and Agents pages'
//   mainProgram, mainName            the Agents page's
//
// Every control starts from what is set now and writes only when it is
// changed here, so running it again on a working install (About → Run setup
// again) changes nothing unless you change something. Skipping writes the
// marker and nothing else. It never touches an agent folder, another agent,
// an endpoint or a permission level.
Item {
  id: setup

  required property var s

  readonly property string step: s.setupStep
  readonly property int stepIndex: Math.max(0, s.setupSteps.indexOf(step))
  readonly property var stepNames: ["Microphone", "Wake word", "Your agent", "Done"]

  function next() { setup.s.setupGo(setup.s.setupSteps[Math.min(3, stepIndex + 1)]) }
  function back() { setup.s.setupGo(setup.s.setupSteps[Math.max(0, stepIndex - 1)]) }
  onStepChanged: {
    scroll.contentY = 0
    // Leaving the wake step stops a test still counting.
    if (step !== "wake") stopTest()
    if (step === "agent") backends.look()
    Qt.callLater(function() { primary.forceActiveFocus() })
  }
  Component.onCompleted: {
    if (step === "agent") backends.look()
    Qt.callLater(function() { primary.forceActiveFocus() })
  }

  // --- the wake test, three tries --------------------------------------------------
  // The daemon's own `wake-test` (it counts wakes instead of answering them
  // and writes wake-test.json); setup stops it after three tries.
  readonly property int tries: 3
  property bool testing: false
  // The file still holds the last test anyone ran (the Listening page's,
  // say) until the daemon writes this one, and the overlay re-reads it every
  // second: so a reading counts only once this test has been seen running.
  property bool sawRunning: false
  readonly property var t: s.vWakeTest || ({})
  readonly property int attempts: sawRunning ? Math.min(tries, Number(t.attempts || 0)) : 0
  readonly property int hits: sawRunning ? Math.min(tries, Number(t.hits || 0)) : 0
  readonly property bool testDone: sawRunning && !testing && String(t.status || "") !== ""
                                   && String(t.status) !== "running"
  function startTest() {
    if (!s.serviceActive) return
    sawRunning = false
    testing = true
    s.wakeTest(true)
  }
  function stopTest() {
    if (!testing) return
    testing = false
    s.wakeTest(false)
  }
  Connections {
    target: setup.s
    function onVWakeTestChanged() {
      if (!setup.testing) return
      var st = String(setup.t.status || "")
      if (!setup.sawRunning) {
        if (st === "running") setup.sawRunning = true
        return
      }
      if (Number(setup.t.attempts || 0) >= setup.tries || Number(setup.t.hits || 0) >= setup.tries)
        setup.stopTest()
      else if (st !== "" && st !== "running")
        setup.testing = false
    }
  }
  // Leaving setup stops a test still counting, too.
  Component.onDestruction: stopTest()

  // --- what is installed, for the agent step ---------------------------------------
  // `agentvoice about backends --json` (M26): each program Agent Voice
  // offers, found on PATH or not. Finding one is not being signed in.
  QtObject {
    id: backends
    property var list: []
    property bool read: false
    property string err: ""
    function look() { if (!backendsProc.running) backendsProc.running = true }
  }
  Process {
    id: backendsProc
    command: ["agentvoice", "about", "backends", "--json"]
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var d = JSON.parse(String(text).trim() || "{}")
          backends.list = Array.isArray(d.backends) ? d.backends : []
          backends.err = ""
        } catch (e) { backends.list = []; backends.err = "could not read what is installed" }
        backends.read = true
      }
    }
  }
  readonly property string mainProgram: String(s.setting("mainProgram", ""))
  readonly property var programChoices: {
    var out = []
    if (s.defaultAgent !== "")
      out.push({ value: "omarchy", label: "Omarchy's default (" + s.programLabel(s.defaultAgent) + ")",
                 tooltip: "Follows `omarchy default agent`." })
    for (var i = 0; i < backends.list.length; i++) {
      var b = backends.list[i] || {}
      if (b.found === true && /^[a-z]+$/.test(String(b.id || "")))
        out.push({ value: String(b.id), label: String(b.label || b.id) })
    }
    // What is saved stays choosable, found or not.
    if (mainProgram !== "" && !out.some(function(o) { return o.value === mainProgram }))
      out.push({ value: mainProgram, label: s.programLabel(mainProgram) + " (not found)" })
    return out
  }
  readonly property var missingPrograms: backends.list.filter(function(b) { return b && b.found !== true })
                                                      .map(function(b) { return String(b.label || b.id) })

  // --- the steps --------------------------------------------------------------------
  Column {
    id: frame
    anchors.fill: parent
    spacing: Style.spacing.md

    // Where you are: four steps, the current one marked.
    Row {
      id: steps
      objectName: "setupSteps"
      spacing: Style.space(14)
      Repeater {
        model: setup.stepNames
        Text {
          required property var modelData
          required property int index
          text: (index + 1) + "  " + modelData
          textFormat: Text.PlainText
          color: index === setup.stepIndex ? setup.s.foreground : setup.s.dim
          font.family: setup.s.fontFamily
          font.pixelSize: Style.font.body
          font.bold: index === setup.stepIndex
        }
      }
    }

    PanelSeparator { width: parent.width; foreground: setup.s.foreground }

    Flickable {
      id: scroll
      width: parent.width
      height: frame.height - steps.height - footer.height - frame.spacing * 3 - Style.space(2)
      contentWidth: width
      contentHeight: body.implicitHeight + Style.space(12)
      clip: true
      boundsBehavior: Flickable.StopAtBounds
      flickableDirection: Flickable.VerticalFlick
      interactive: contentHeight > height
      QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }

      Column {
        id: body
        width: Math.min(scroll.width - Style.space(14), Style.space(640))
        spacing: Style.space(12)

        // --- 1. microphone ---------------------------------------------------------
        Column {
          objectName: "setupMic"
          width: parent.width
          spacing: Style.space(10)
          visible: setup.step === "mic"

          Text {
            width: parent.width
            text: "The microphone"
            textFormat: Text.PlainText
            color: setup.s.foreground
            font.family: setup.s.fontFamily
            font.pixelSize: Style.font.title
            font.bold: true
          }
          Text {
            width: parent.width
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
            text: "Agent Voice listens for its wake word all the time, on this machine. The gate is the line " +
                  "on the meter: anything louder counts as you talking, and dropping back under it ends your turn. " +
                  "Talk normally and watch the bar cross the line; stop, and it should fall back under."
            color: setup.s.dim
            font.family: setup.s.fontFamily
            font.pixelSize: Style.font.body
          }

          // Nothing to measure until the service runs; starting it is a
          // choice, made here with a button, never by opening setup.
          Row {
            visible: !setup.s.serviceActive
            spacing: Style.space(10)
            Button {
              objectName: "setupStart"
              text: setup.s.serviceBusy ? "Starting…" : "Start Agent Voice"
              bordered: true
              focusable: true
              enabled: setup.s.engineInstalled && !setup.s.serviceBusy
              foreground: setup.s.foreground
              fontFamily: setup.s.fontFamily
              // Toggle is the overlay's one way to start it, with its
              // guards; only offered while it is known to be off.
              onClicked: if (setup.s.serviceKnown && !setup.s.serviceActive) setup.s.toggleService()
            }
            Text {
              anchors.verticalCenter: parent.verticalCenter
              text: setup.s.engineInstalled ? "It loads its speech models first: a few seconds."
                                            : "The voice engine is not installed yet."
              textFormat: Text.PlainText
              color: setup.s.engineInstalled ? setup.s.dim : setup.s.urgent
              font.family: setup.s.fontFamily
              font.pixelSize: Style.font.caption
            }
          }
          Text {
            width: parent.width
            visible: setup.s.note !== ""
            wrapMode: Text.WordWrap
            text: setup.s.note
            textFormat: Text.PlainText
            color: setup.s.urgent
            font.family: setup.s.fontFamily
            font.pixelSize: Style.font.caption
          }

          LevelMeter {
            objectName: "setupMeter"
            width: parent.width
            levelDb: setup.s.serviceActive ? setup.s.levelDb : -99
            gateDb: setup.s.gateInForce
            minDb: -60
            idleText: setup.s.serviceActive ? "no reading — the microphone is muted"
                                            : "no reading — start Agent Voice to see your level"
            foreground: setup.s.foreground
            fontFamily: setup.s.fontFamily
          }

          SettingRow {
            width: parent.width
            label: "Gate"
            hint: setup.s.setting("adaptiveGate", false) === true
                  ? "The line sits a margin above the room's own noise, and moves with it."
                  : "The line stays where you put it."
            foreground: setup.s.foreground
            fontFamily: setup.s.fontFamily
            SegmentedChoice {
              objectName: "setupGateChoice"
              options: [{ label: "Fixed", value: "fixed" },
                        { label: "Follows the room", value: "dynamic" }]
              value: setup.s.setting("adaptiveGate", false) === true ? "dynamic" : "fixed"
              foreground: setup.s.foreground
              fontFamily: setup.s.fontFamily
              onCommitted: function(v) {
                var on = v === "dynamic"
                if (on !== (setup.s.setting("adaptiveGate", false) === true)) setup.s.put("adaptiveGate", on)
              }
            }
          }
          KnobRow {
            objectName: "setupGateKnob"
            width: parent.width
            foreground: setup.s.foreground; fontFamily: setup.s.fontFamily
            label: setup.s.setting("adaptiveGate", false) === true ? "Fixed gate (until it has heard the room)"
                                                                  : "Microphone gate"
            unit: " dBFS"
            description: "Put the line under your voice: lower if it cuts you off, higher if the room holds it open."
            value: Number(setup.s.setting("micThresholdDb", -38))
            defaultValue: setup.s.defaults.micThresholdDb !== undefined ? setup.s.defaults.micThresholdDb : NaN
            minimum: -60; maximum: -20; stepSize: 1
            onCommitted: function(v) { if (v !== Number(setup.s.setting("micThresholdDb", -38))) setup.s.put("micThresholdDb", v) }
          }
        }

        // --- 2. wake word ----------------------------------------------------------
        Column {
          objectName: "setupWake"
          width: parent.width
          spacing: Style.space(10)
          visible: setup.step === "wake"

          Text {
            width: parent.width
            text: "The wake word"
            textFormat: Text.PlainText
            color: setup.s.foreground
            font.family: setup.s.fontFamily
            font.pixelSize: Style.font.title
            font.bold: true
          }
          Text {
            width: parent.width
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
            text: "What you say to start a turn. The engine is what listens for it; all three run on this machine."
            color: setup.s.dim
            font.family: setup.s.fontFamily
            font.pixelSize: Style.font.body
          }

          SettingRow {
            width: parent.width
            stacked: true
            label: "Engine"
            hint: setup.s.usingOww ? "Four phrases, better rejection, and a verifier trained on your voice."
                  : setup.s.usingSherpa ? "Any phrase, with far fewer false wakes than Vosk."
                  : "Any phrase. Weaker at rejecting sound-alikes."
            foreground: setup.s.foreground
            fontFamily: setup.s.fontFamily
            SegmentedChoice {
              objectName: "setupEngineChoice"
              options: setup.s.engineOptions
              value: setup.s.engine
              foreground: setup.s.foreground
              fontFamily: setup.s.fontFamily
              // An engine that is not installed is not chosen from here: the
              // daemon would quietly fall back to Vosk. Its installer is
              // offered instead, below.
              onCommitted: function(v) {
                setup.wantEngine = v
                var ok = v === "vosk" || (v === "openwakeword" && setup.s.owwAvailable)
                         || (v === "sherpa" && setup.s.sherpaAvailable)
                if (ok && v !== setup.s.engine) setup.s.put("engine", v)
              }
            }
          }
          Row {
            visible: setup.missingEngine !== ""
            spacing: Style.space(10)
            Text {
              anchors.verticalCenter: parent.verticalCenter
              text: setup.missingEngine + " is not installed."
              textFormat: Text.PlainText
              color: setup.s.urgent
              font.family: setup.s.fontFamily
              font.pixelSize: Style.font.caption
            }
            Button {
              text: "Install it…"
              tooltipText: "Opens the installer in a terminal and closes setup; finish setting up from the Overview afterwards."
              bordered: true
              focusable: true
              foreground: setup.s.foreground
              fontFamily: setup.s.fontFamily
              onClicked: setup.s.fetchNow([setup.wantEngine === "sherpa" ? "--sherpa" : "--oww"])
            }
          }

          // The phrase: any words on Vosk and sherpa-onnx, one of the
          // models on openWakeWord.
          SettingRow {
            width: parent.width
            visible: !setup.s.owwLive
            stacked: true
            label: "Wake phrase"
            hint: "One to three plain words; Enter saves. A short name like “computer” wakes more by mistake."
            foreground: setup.s.foreground
            fontFamily: setup.s.fontFamily
            Column {
              width: parent.width
              spacing: Style.space(6)
              TextField {
                objectName: "setupPhrase"
                width: parent.width
                // Read again whenever phraseEpoch moves, which puts back
                // the saved phrase after something that was not saved.
                text: { setup.phraseEpoch; return String(setup.s.setting("phrase", "hey computer")) }
                placeholderText: "the words that wake it"
                foreground: setup.s.foreground
                font.family: setup.s.fontFamily
                onEditingFinished: setup.setPhrase(text)
              }
              Flow {
                width: parent.width
                spacing: Style.space(6)
                Repeater {
                  model: setup.s.phraseOptions
                  Button {
                    required property var modelData
                    text: modelData
                    selected: String(setup.s.setting("phrase", "hey computer")) === modelData
                    bordered: true
                    focusable: true
                    fontSize: Style.font.caption
                    foreground: setup.s.foreground
                    fontFamily: setup.s.fontFamily
                    onClicked: setup.setPhrase(modelData)
                  }
                }
              }
            }
          }
          SettingRow {
            width: parent.width
            visible: setup.s.owwLive
            stacked: true
            label: "Wake phrase"
            hint: "openWakeWord hears only the phrase its model was trained on."
            foreground: setup.s.foreground
            fontFamily: setup.s.fontFamily
            Dropdown {
              objectName: "setupOwwModel"
              width: parent.width
              showLabel: false
              options: setup.s.owwOptions
              value: String(setup.s.setting("owwModel", "hey_jarvis"))
              foreground: setup.s.foreground
              fontFamily: setup.s.fontFamily
              onChanged: function(v) { if (v !== String(setup.s.setting("owwModel", "hey_jarvis"))) setup.s.put("owwModel", v) }
            }
          }

          // Three tries through the daemon's wake test.
          Card {
            objectName: "setupTest"
            width: parent.width
            title: "Try it"
            subtitle: "Say “" + setup.s.activePhrase + "” three times, on its own, with a pause after each. " +
                      "Nothing is answered while it counts."
            foreground: setup.s.foreground
            fontFamily: setup.s.fontFamily

            Row {
              spacing: Style.space(10)
              Button {
                objectName: "setupTestButton"
                text: setup.testing ? "Stop" : setup.testDone ? "Try again" : "Start"
                bordered: true
                focusable: true
                enabled: setup.s.serviceActive
                foreground: setup.s.foreground
                fontFamily: setup.s.fontFamily
                onClicked: setup.testing ? setup.stopTest() : setup.startTest()
              }
              Text {
                anchors.verticalCenter: parent.verticalCenter
                text: !setup.s.serviceActive ? "Start Agent Voice first (step 1)."
                      : setup.testing ? "Listening… " + setup.attempts + " of " + setup.tries + " tries so far."
                      : ""
                textFormat: Text.PlainText
                color: setup.testing ? setup.s.accent : setup.s.dim
                font.family: setup.s.fontFamily
                font.pixelSize: Style.font.caption
              }
            }
            Text {
              objectName: "setupTestResult"
              width: parent.width
              visible: setup.s.serviceActive && (setup.testing || setup.testDone)
              wrapMode: Text.WordWrap
              textFormat: Text.PlainText
              readonly property real peak: Number(setup.t.peak_db !== undefined ? setup.t.peak_db : -99)
              readonly property real gate: Number(setup.t.gate_db || 0)
              text: setup.hits + " of " + Math.max(setup.attempts, setup.hits) + " tries woke it." +
                    (setup.testDone && setup.hits >= setup.tries ? " It hears you." : "") +
                    (setup.testDone && setup.hits < setup.tries && peak > -99 && peak < gate
                     ? " You never reached the gate: lower it on step 1, or speak up."
                     : setup.testDone && setup.hits < setup.tries
                       ? " Try again, try a longer phrase, or tune it later on the Listening page." : "")
              color: setup.s.foreground
              font.family: setup.s.fontFamily
              font.pixelSize: Style.font.body
            }
          }
        }

        // --- 3. your agent ---------------------------------------------------------
        Column {
          objectName: "setupAgent"
          width: parent.width
          spacing: Style.space(10)
          visible: setup.step === "agent"

          Text {
            width: parent.width
            text: "Your agent"
            textFormat: Text.PlainText
            color: setup.s.foreground
            font.family: setup.s.fontFamily
            font.pixelSize: Style.font.title
            font.bold: true
          }
          Text {
            width: parent.width
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
            text: "The coding agent that answers. It runs as the program you already use, signed in the way you " +
                  "signed it in; what it may do without asking is set per agent on the Agents page, and starts at " +
                  "“ask first”."
            color: setup.s.dim
            font.family: setup.s.fontFamily
            font.pixelSize: Style.font.body
          }

          SettingRow {
            width: parent.width
            visible: !setup.s.usingEndpoint
            stacked: true
            label: "Runs on"
            hint: !backends.read ? "Looking for what is installed…"
                  : backends.err !== "" ? "Could not tell what is installed: " + backends.err + "."
                  : setup.programChoices.length === 0
                    ? "None of the programs Agent Voice works with was found. Install Claude Code or Codex, then come back."
                  : setup.missingPrograms.length > 0 ? "Not found here: " + setup.missingPrograms.join(", ") + "."
                  : "Found on this machine. Installed is not the same as signed in."
            foreground: setup.s.foreground
            fontFamily: setup.s.fontFamily
            SegmentedChoice {
              objectName: "setupProgram"
              visible: setup.programChoices.length > 0
              wrap: true
              options: setup.programChoices
              value: setup.mainProgram === "" ? "omarchy" : setup.mainProgram
              foreground: setup.s.foreground
              fontFamily: setup.s.fontFamily
              onCommitted: function(v) {
                var program = v === "omarchy" ? "" : v
                if (program !== setup.mainProgram) setup.s.put("mainProgram", program)
              }
            }
          }
          Text {
            width: parent.width
            visible: setup.s.usingEndpoint
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
            text: "It runs on an endpoint (" + String(setup.s.setting("endpointModel", "")) + "). Change that on the Agents page."
            color: setup.s.dim
            font.family: setup.s.fontFamily
            font.pixelSize: Style.font.body
          }

          SettingRow {
            width: parent.width
            stacked: true
            label: "Name"
            hint: "What it is called on screen and in saved chats. Empty uses the wake phrase."
            foreground: setup.s.foreground
            fontFamily: setup.s.fontFamily
            TextField {
              objectName: "setupName"
              width: parent.width
              text: String(setup.s.setting("mainName", ""))
              placeholderText: setup.s.capitalised(setup.s.activePhrase) || "a name to show"
              foreground: setup.s.foreground
              font.family: setup.s.fontFamily
              onEditingFinished: {
                var v = setup.s.cleanLabel(text)
                if (v !== String(setup.s.setting("mainName", ""))) setup.s.put("mainName", v)
              }
            }
          }

          Row {
            spacing: Style.space(10)
            Text {
              anchors.verticalCenter: parent.verticalCenter
              text: "It wakes to “" + setup.s.activePhrase + "”."
              textFormat: Text.PlainText
              color: setup.s.foreground
              font.family: setup.s.fontFamily
              font.pixelSize: Style.font.body
            }
            Button {
              text: "Change"
              bordered: true
              focusable: true
              fontSize: Style.font.caption
              foreground: setup.s.foreground
              fontFamily: setup.s.fontFamily
              onClicked: setup.s.setupGo("wake")
            }
          }
        }

        // --- 4. done -----------------------------------------------------------------
        Column {
          objectName: "setupDone"
          width: parent.width
          spacing: Style.space(8)
          visible: setup.step === "done"

          Text {
            width: parent.width
            text: "Ready"
            textFormat: Text.PlainText
            color: setup.s.foreground
            font.family: setup.s.fontFamily
            font.pixelSize: Style.font.title
            font.bold: true
          }
          InfoRow {
            width: parent.width
            label: "Microphone"
            value: setup.s.setting("adaptiveGate", false) === true ? "the gate follows the room"
                   : "gate at " + setup.s.setting("micThresholdDb", -38) + " dBFS"
            foreground: setup.s.foreground
            fontFamily: setup.s.fontFamily
          }
          InfoRow {
            width: parent.width
            label: "Wake word"
            value: "“" + setup.s.activePhrase + "”, heard by " +
                   (setup.s.owwLive ? "openWakeWord" : setup.s.sherpaLive ? "sherpa-onnx" : "Vosk")
            foreground: setup.s.foreground
            fontFamily: setup.s.fontFamily
          }
          InfoRow {
            width: parent.width
            label: "Agent"
            // What was chosen, not what the daemon runs this second: it
            // picks a change up on its next turn.
            value: setup.s.mainLabel + ", on " +
                   (setup.s.usingEndpoint ? "an endpoint"
                    : setup.mainProgram !== "" ? setup.s.programLabel(setup.mainProgram)
                    : setup.s.defaultAgent !== "" ? "Omarchy's default (" + setup.s.programLabel(setup.s.defaultAgent) + ")"
                    : "no program yet")
            foreground: setup.s.foreground
            fontFamily: setup.s.fontFamily
          }
          InfoRow {
            width: parent.width
            label: "Service"
            value: setup.s.serviceActive ? "running" : "off: start it from the Overview"
            foreground: setup.s.foreground
            fontFamily: setup.s.fontFamily
          }
          Text {
            width: parent.width
            topPadding: Style.space(6)
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
            text: "Say “" + setup.s.activePhrase + "”, then what you want. Everything here can be changed in the " +
                  "settings: Ctrl+F finds any of them. More agents, their voices and what each may do are on " +
                  "the Agents page."
            color: setup.s.dim
            font.family: setup.s.fontFamily
            font.pixelSize: Style.font.body
          }
        }
      }
    }

    // --- the way through, and the way out ----------------------------------------
    Item {
      id: footer
      width: parent.width
      height: Math.max(skip.implicitHeight, primary.implicitHeight)

      Button {
        id: skip
        objectName: "setupSkip"
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        visible: setup.step !== "done"
        text: "Skip setup"
        tooltipText: "Changes nothing. Finish it later from the Overview, or run it again from About."
        bordered: true
        focusable: true
        foreground: setup.s.foreground
        fontFamily: setup.s.fontFamily
        onClicked: setup.s.leaveSetup("skipped")
      }
      Row {
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(10)
        Button {
          objectName: "setupBack"
          visible: setup.stepIndex > 0
          text: "Back"
          bordered: true
          focusable: true
          foreground: setup.s.foreground
          fontFamily: setup.s.fontFamily
          onClicked: setup.back()
        }
        Button {
          id: primary
          objectName: "setupNext"
          text: setup.step === "done" ? "Open the settings" : "Next"
          bordered: true
          focusable: true
          selected: true
          foreground: setup.s.foreground
          fontFamily: setup.s.fontFamily
          onClicked: setup.step === "done" ? setup.s.leaveSetup("done") : setup.next()
        }
      }
    }
  }

  // Which engine was last picked here, and what is missing for it.
  property string wantEngine: ""
  readonly property string missingEngine:
      wantEngine === "openwakeword" && !s.owwAvailable ? "openWakeWord"
      : wantEngine === "sherpa" && !s.sherpaAvailable ? "sherpa-onnx" : ""
  property int phraseEpoch: 0
  function setPhrase(text) {
    var v = String(text).trim().toLowerCase().replace(/\s+/g, " ")
    var was = String(s.setting("phrase", "hey computer"))
    // As the Agents page checks the main phrase: one to three plain words.
    if (/^[a-z']+( [a-z']+){0,2}$/.test(v) && v !== was) s.put("phrase", v)
    phraseEpoch++
  }
}
