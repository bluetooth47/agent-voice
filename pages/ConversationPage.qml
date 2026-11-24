import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import ".."
import "../ui"

// When a turn starts and ends, whether it keeps listening afterwards, and
// what happens when you talk over it (master plan M24).
//
// The same settings as before, compact: four cards for what happens around a
// turn, the turn itself drawn start to end from the live values, the timings
// folded under it, and the spoken commands listed from the daemon's own table.
//
// A page is one subject: the rhythm of an exchange. Nothing here is stored
// that is not already a setting; "Pace" is only a shorthand for four of them,
// worked out from their values.
Column {
  id: page
  objectName: "conversationPage"

  required property var s

  spacing: Style.space(18)

  // --- reading a setting the way the daemon does --------------------------------
  // shell.json is hand-edited and synced, so a timing can be stored as the
  // string "90000". The daemon reads it with int() (Config.get_int): a whole
  // number, a float cut to one, or digits in a string. Anything else is the
  // shipped value there, and here. A bare Number() would call "" zero and
  // "abc" NaN, and hand a slider a string it cannot take.
  function num(key, fallback) {
    var v = s.setting(key, fallback)
    if (typeof v === "number") return isFinite(v) ? Math.trunc(v) : fallback
    if (typeof v === "boolean") return v ? 1 : 0
    if (typeof v === "string" && /^\s*[+-]?[0-9]+\s*$/.test(v)) return parseInt(v, 10)
    return fallback
  }
  function dflt(key) {
    return s.defaults[key] !== undefined ? s.defaults[key] : NaN
  }

  // --- pace ----------------------------------------------------------------------
  // Four timings move together. A preset is only a shorthand for them --
  // nothing stores which one was picked; the page works it out from the
  // values, so a slider moved by hand reads as "custom".
  readonly property var presets: ({
    "patient":  { leadInMs: 8000, trailingSilenceMs: 2000, quickEndMs: 1200, followUpMs: 12000 },
    "balanced": { leadInMs: 5000, trailingSilenceMs: 1200, quickEndMs: 800,  followUpMs: 7000 },
    "snappy":   { leadInMs: 3500, trailingSilenceMs: 800,  quickEndMs: 500,  followUpMs: 5000 }
  })
  // A timing never written is its shipped value, as it is for the daemon, so
  // a fresh install reads Balanced rather than Custom.
  function paceValue(key) { return num(key, isNaN(dflt(key)) ? -1 : dflt(key)) }
  readonly property string preset: {
    for (var name in presets) {
      var p = presets[name]
      var all = true
      for (var k in p) if (paceValue(k) !== p[k]) all = false
      if (all) return name
    }
    return "custom"
  }
  function applyPreset(name) {
    var p = presets[name]
    if (!p) return
    for (var k in p) if (paceValue(k) !== p[k]) s.put(k, p[k])
  }

  // --- the limit note ------------------------------------------------------------
  // Moved on once a minute while the page is shown, so the line below is
  // worked out again after midnight even if nothing else changes.
  property real minuteTick: 0
  Timer {
    interval: 60000
    repeat: true
    running: page.visible
    onTriggered: page.minuteTick = Date.now()
  }
  // Turns cut at the longest-turn limit today, by the date they were counted
  // on, not by whether the daemon has rolled it over: it does that on its idle
  // poll, which a mute overnight stops (Codex review of M2).
  readonly property int limitToday: {
    var tick = minuteTick
    var h = s.vLimitHits || {}
    if (String(h.date || "") !== Qt.formatDate(new Date(), "yyyy-MM-dd")) return 0
    var n = Number(h.today)
    return isFinite(n) && n > 0 ? Math.floor(n) : 0
  }
  readonly property string limitLine: {
    var tick = minuteTick
    if (limitToday <= 0) return ""
    var h = s.vLimitHits || {}
    var when = Number(h.last) > 0
        ? ", the last at " + Qt.formatTime(new Date(Number(h.last) * 1000), "HH:mm") : ""
    return limitToday + (limitToday === 1 ? " turn" : " turns") + " today hit the limit" + when + "."
  }

  // --- bringing a control into view ---------------------------------------------
  // "Raise it →" on the limit note, or a deep link carrying "focus": the
  // folded timings open, the control is scrolled to and outlined for a moment.
  // Only the six timings are here to be asked for.
  readonly property var timingKeys: ["leadInMs", "trailingSilenceMs", "quickEndMs",
                                     "minUtteranceMs", "maxUtteranceMs", "echoTailMs"]
  property string flash: ""
  Timer { id: flashTimer; interval: 2500; onTriggered: page.flash = "" }
  function knobFor(key) {
    return key === "leadInMs" ? leadInKnob : key === "trailingSilenceMs" ? pauseKnob
         : key === "quickEndMs" ? quickKnob : key === "minUtteranceMs" ? minKnob
         : key === "maxUtteranceMs" ? maxKnob : key === "echoTailMs" ? echoKnob : null
  }
  Timer {
    id: scrollTimer
    interval: 80
    onTriggered: {
      var f = page.s.pageScroll
      var k = page.knobFor(page.flash)
      if (!f || !k) return
      var y = k.mapToItem(f.contentItem, 0, 0).y
      f.contentY = Math.max(0, Math.min(y - Style.space(120), f.contentHeight - f.height))
    }
  }
  function showFocus() {
    var key = s.focusKey
    if (key === "" || timingKeys.indexOf(key) < 0) return
    timings.expanded = true
    flash = key
    flashTimer.restart()
    // Once the fold has laid out: the scroller's height is only the new one
    // a frame later, and the last control would stop short of the bottom.
    scrollTimer.restart()
    // Taken: asking for the same control again must be a change again.
    s.focusKey = ""
  }
  Connections {
    target: page.s
    function onFocusKeyChanged() { page.showFocus() }
  }

  // --- the open mic ---------------------------------------------------------------
  // From the state file: {who, until}. Read the way the popup reads it.
  readonly property bool openMicOn: s.serviceActive && s.vOpenMic.until !== undefined
  property real nowMs: Date.now()
  // A fresh clock when it opens, and what the last press complained about is
  // not true of a state it has since left.
  onOpenMicOnChanged: { nowMs = Date.now(); openMicNote = "" }
  Timer {
    interval: 1000
    repeat: true
    running: page.visible && page.openMicOn
    onTriggered: page.nowMs = Date.now()
  }
  readonly property int openMicLeftS: openMicOn
      ? Math.max(0, Math.round(Number(s.vOpenMic.until) - nowMs / 1000)) : 0
  readonly property string openMicLine: {
    if (!s.serviceActive) return "The service is not running."
    if (!openMicOn) return "Off. It needs the wake word."
    var who = String(s.vOpenMic.who || "")
    var left = openMicLeftS >= 60 ? Math.ceil(openMicLeftS / 60) + " min left"
             : openMicLeftS > 0 ? "under a minute left" : "closing"
    return "On" + (who !== "" ? " with " + who : "") + " · " + left
  }
  // What the last press said, if it could not do it. Cleared by the next press
  // and by the thing it complained about stopping being true.
  property string openMicNote: ""
  readonly property string openMicWhy: s.serviceActive ? openMicNote
      : "Start the service first: the open mic is the running service listening."
  // The only way in. The service is checked here, in the function every press
  // passes through, so a second entry point added later cannot skip it.
  function toggleOpenMic() {
    if (!s.serviceActive) { openMicNote = "Start the service first."; return }
    if (openMicProc.running) return
    openMicNote = ""
    openMicProc.began = false
    openMicProc.command = ["agentvoice", "open-mic", page.openMicOn ? "off" : "on"]
    openMicProc.running = true
  }
  Process {
    id: openMicProc
    property bool began: false
    onStarted: began = true
    onExited: function(code, status) {
      if (code !== 0) page.openMicNote = "The service did not take that (exit " + code + ")."
    }
    // `running` going false is emitted whether or not the process started;
    // onExited is not (CLAUDE.md), so a spawn that never happened is caught here.
    onRunningChanged: if (!running && !began) page.openMicNote = "agentvoice could not be started."
  }

  // --- the command table ------------------------------------------------------------
  // `agentvoice commands --json` (daemon/voice_commands.py): the phrases the
  // daemon matches, so this page holds none of its own and cannot drift from
  // what is heard. Read when the page is built and each time the overlay opens.
  property var cmd: null
  property string cmdProblem: ""
  Process {
    id: cmdReader
    command: ["agentvoice", "commands", "--json"]
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var d = JSON.parse(text)
          if (!d || typeof d !== "object" || !Array.isArray(d.commands)) throw "shape"
          page.cmd = d
          page.cmdProblem = ""
        } catch (e) {
          page.cmdProblem = "The command list could not be read."
        }
      }
    }
  }
  function readCommands() { if (!cmdReader.running) cmdReader.running = true }
  Component.onCompleted: { readCommands(); showFocus() }
  Connections {
    target: page.s
    function onOpenedChanged() { if (page.s.opened) page.readCommands() }
  }
  function command(id) {
    var list = cmd ? cmd.commands : []
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i]
    return null
  }
  // A phrase to quote for a command: one that works inside a sentence if there
  // is one (the daemon's own list, not a guess), else the first it matches.
  // "" while the table has not been read.
  function phraseOf(id) {
    var c = command(id)
    if (!c) return ""
    if (c.in_sentence && c.in_sentence.length > 0) return String(c.in_sentence[0])
    return c.phrases && c.phrases.length > 0 ? String(c.phrases[0]) : ""
  }
  // A command's name as the table gives it, or `fallback` before it is read.
  function labelOf(id, fallback) {
    var c = command(id)
    return c ? String(c.label).toLowerCase() : fallback
  }
  function said(p) { return "“" + p + "”" }
  readonly property string openPhrase: phraseOf("open_mic")
  readonly property string closePhrase: phraseOf("close_mic")
  readonly property string undoPhrase: (cmd && cmd.undo && cmd.undo.phrases && cmd.undo.phrases.length > 0)
                                       ? String(cmd.undo.phrases[cmd.undo.phrases.length - 1]) : ""
  readonly property var whereWords: ({
    "alone": "on its own", "start": "at the start", "end": "at the end", "clause": "in its own clause"
  })
  // Where a command fires in the mode chosen now: what it can do, and the
  // mode lets it do.
  function liveWhere(c) {
    var allowed = (cmd && cmd.mode_positions && cmd.mode_positions[commandsRow.mode]) || ["alone"]
    var out = []
    var all = cmd && cmd.positions ? cmd.positions : ["alone", "start", "end", "clause"]
    for (var i = 0; i < all.length; i++)
      if (c.where.indexOf(all[i]) >= 0 && allowed.indexOf(all[i]) >= 0) out.push(String(whereWords[all[i]] || all[i]))
    return out
  }
  function phraseList(c) {
    var list = c.phrases || []
    var shown = []
    for (var i = 0; i < Math.min(3, list.length); i++) shown.push(said(list[i]))
    var more = list.length - shown.length
    return "Say: " + shown.join(", ") + (more > 0 ? ", and " + more + " more" : "")
  }
  function allPhrases(c) {
    var out = []
    var list = c.phrases || []
    for (var i = 0; i < list.length; i++) out.push(said(list[i]))
    return out.join("  ")
  }

  // An outline round the control a link asked for. Plain properties, because
  // an inline component cannot see the page's ids.
  component Marked: Item {
    id: mark
    property bool flashed: false
    property color outline: "transparent"
    default property alias inner: slot.data
    width: parent ? parent.width : 0
    height: slot.childrenRect.height
    Rectangle {
      anchors.fill: parent
      anchors.margins: -Style.space(3)
      visible: mark.flashed
      color: "transparent"
      radius: Style.cornerRadius
      border.width: 2
      border.color: mark.outline
    }
    Item {
      id: slot
      width: parent.width
      height: childrenRect.height
    }
  }

  PageHeader {
    width: parent.width
    title: "Conversation"
    subtitle: "When it starts and stops listening, and how you interrupt it."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
  }

  SettingRow {
    objectName: "set-pace"
    width: parent.width
    label: "Pace"
    hint: page.preset === "patient" ? "Waits longer for you to start, pause and carry on. Good for thinking aloud."
          : page.preset === "snappy" ? "Ends turns quickly. Good for short commands; cuts in on long pauses."
          : page.preset === "balanced" ? "The defaults."
          : "Your own timings, set below."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
    CompactSelector {
      objectName: "paceChoice"
      options: [
        { value: "patient", label: "Patient" },
        { value: "balanced", label: "Balanced" },
        { value: "snappy", label: "Snappy" }
      ].concat(page.preset === "custom" ? [{ value: "custom", label: "Custom", enabled: false }] : [])
      value: page.preset
      foreground: page.s.foreground
      accent: page.s.accent
      fontFamily: page.s.fontFamily
      onCommitted: function(v) { page.applyPreset(v) }
    }
  }

  // Two columns only where each card can hold a setting's label whole: at the
  // overlay's usual width a half-width card cut "Keep listening after a reply"
  // to "Keep listening after a rep…".
  CardGrid {
    width: parent.width
    wideAt: Style.space(720)

    // --- follow-ups -------------------------------------------------------------
    Card {
      objectName: "followCard"
      title: "Follow-ups"
      subtitle: "Carrying on after a reply"
      foreground: page.s.foreground
      accent: page.s.accent
      fontFamily: page.s.fontFamily

      ToggleRow {
        objectName: "set-conversationMode"
        width: parent.width
        label: "Keep listening after a reply"
        hint: "Carry on without the wake word. Say the stop command, or stay quiet, to end it."
        checked: page.s.setting("conversationMode", true) === true
        changed: page.s.changed("conversationMode")
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onToggled: page.s.put("conversationMode", !checked)
        onReset: page.s.resetKey("conversationMode")
      }

      // Left on rather than switched off for a backend that forgets: it still
      // saves the wake word, which is half of what it is for. What it cannot
      // do is follow on, and that failure is silent.
      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        visible: page.s.setting("conversationMode", true) === true && !page.s.vRemembers
        text: "⚠  " + (page.s.mainAgent === "" ? "This agent" : page.s.mainAgent) +
              " starts fresh on every turn, so this saves you the wake word and nothing " +
              "more. Asking what it meant by that gets an answer to a question it " +
              "has never seen."
        textFormat: Text.PlainText
        color: page.s.urgent
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }

      KnobRow {
        objectName: "set-followUpMs"
        width: parent.width
        enabled: page.s.setting("conversationMode", true) === true
        opacity: enabled ? 1 : 0.45
        foreground: page.s.foreground; fontFamily: page.s.fontFamily
        label: "Follow-up window"
        description: enabled ? "How long it keeps listening after speaking before it needs the wake word again."
                             : "Only while it keeps listening after a reply."
        value: page.num("followUpMs", 7000)
        defaultValue: page.dflt("followUpMs")
        changed: page.s.changed("followUpMs")
        minimum: 2000; maximum: 20000; stepSize: 500
        onCommitted: function(v) { page.s.put("followUpMs", v) }
        onReset: page.s.resetKey("followUpMs")
      }
    }

    // --- open mic ---------------------------------------------------------------
    // An open conversation: no wake word until it is closed or goes quiet.
    Card {
      objectName: "openMicCard"
      title: "Open mic"
      subtitle: "Talk without the wake word"
      foreground: page.s.foreground
      accent: page.s.accent
      fontFamily: page.s.fontFamily

      Item {
        width: parent.width
        height: Math.max(micStatus.implicitHeight, micButton.implicitHeight)

        Row {
          id: micStatus
          anchors.left: parent.left
          anchors.right: micButton.left
          anchors.rightMargin: Style.space(8)
          anchors.verticalCenter: parent.verticalCenter
          spacing: Style.space(6)
          Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: Style.space(9)
            height: width
            radius: width / 2
            color: page.openMicOn ? page.s.accent : "transparent"
            border.width: 1
            border.color: page.openMicOn ? page.s.accent : page.s.dim
          }
          Text {
            objectName: "openMicLine"
            width: parent.width - Style.space(15)
            text: page.openMicLine
            textFormat: Text.PlainText
            elide: Text.ElideRight
            color: page.openMicOn ? page.s.foreground : page.s.dim
            font.family: page.s.fontFamily
            font.pixelSize: Style.font.body
          }
        }
        Button {
          id: micButton
          objectName: "openMicButton"
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          text: page.openMicOn ? "Turn off" : "Turn on"
          bordered: true
          enabled: page.s.serviceActive && !openMicProc.running
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onClicked: page.toggleOpenMic()
        }
      }

      // A control that does nothing must say why.
      Text {
        objectName: "openMicWhy"
        width: parent.width
        wrapMode: Text.WordWrap
        visible: text !== ""
        text: page.openMicWhy
        textFormat: Text.PlainText
        color: page.s.serviceActive ? page.s.urgent : page.s.dim
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }

      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        text: (page.openPhrase !== "" ? "Say " + page.said(page.openPhrase) + " to start it"
                                        + (page.closePhrase !== "" ? " and " + page.said(page.closePhrase) + " to end it. " : ". ")
                                      : "Its voice commands are listed under Voice commands below. ")
              + "It stays with the agent you started it with; say another agent's name to hand "
              + "it over. The bar icon and the HUD show while it is open."
        textFormat: Text.PlainText
        color: page.s.dim
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }

      KnobRow {
        objectName: "set-openMicIdleMin"
        width: parent.width
        foreground: page.s.foreground; fontFamily: page.s.fontFamily
        label: "Closes after"
        description: "Minutes with nothing said before it needs the wake word again."
        value: page.num("openMicIdleMin", 10)
        defaultValue: page.dflt("openMicIdleMin")
        changed: page.s.changed("openMicIdleMin")
        minimum: 1; maximum: 60; stepSize: 1
        unit: " min"
        onCommitted: function(v) { page.s.put("openMicIdleMin", Math.round(v)) }
        onReset: page.s.resetKey("openMicIdleMin")
      }

      ToggleRow {
        objectName: "set-openMicAddressedOnly"
        width: parent.width
        label: "Only answer if it's meant for you"
        hint: "It stays silent when what it heard was said to someone else, or came from a television."
        help: "Each thing heard on the open mic goes to the agent with a note asking it to " +
              "reply SKIP if it was not said to it, and a SKIP is never spoken or kept. It " +
              "costs a turn of the agent's time for everything heard."
        checked: page.s.setting("openMicAddressedOnly", true) === true
        changed: page.s.changed("openMicAddressedOnly")
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onToggled: page.s.put("openMicAddressedOnly", !checked)
        onReset: page.s.resetKey("openMicAddressedOnly")
      }

      ToggleRow {
        objectName: "set-openMicAuto"
        width: parent.width
        label: "Open the mic after every wake"
        hint: "Every wake word starts an open conversation, as if you had asked for it by voice."
        checked: page.s.setting("openMicAuto", false) === true
        changed: page.s.changed("openMicAuto")
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onToggled: page.s.put("openMicAuto", !checked)
        onReset: page.s.resetKey("openMicAuto")
      }
    }

    // --- while it works ---------------------------------------------------------
    // Progress talk. Off by default: what it says was written from recorded
    // turns (bench/narration), and is yours to switch on.
    Card {
      objectName: "workCard"
      title: "While it works"
      subtitle: "Talk between your request and the answer"
      foreground: page.s.foreground
      accent: page.s.accent
      fontFamily: page.s.fontFamily

      SettingRow {
        objectName: "set-narration"
        width: parent.width
        stacked: true
        label: "Talk while it works"
        hint: page.s.setting("narration", "off") === "detailed"
              ? "Names files, searches and pages: \"I'm reading Panel.qml.\""
              : page.s.setting("narration", "off") === "brief"
              ? "Names the stage only: \"I'm running the tests.\""
              : "Silent between its first sentence and its answer."
        help: "Every sentence comes from a tool the agent really ran, never a guess. " +
              "It waits for a quiet stretch, spaces its sentences further apart as a " +
              "turn goes on, never repeats itself, and stops the moment the agent " +
              "starts talking. Secret files are \"a config file\" and a command line is " +
              "never read out. Claude Code and Codex report their tools; Gemini, " +
              "Antigravity, Copilot and endpoints do not, so they stay quiet. Each " +
              "agent's card can choose for itself."
        changed: page.s.changed("narration")
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onReset: page.s.resetKey("narration")
        SegmentedChoice {
          options: [
            { value: "off", label: "Off" },
            { value: "brief", label: "Brief" },
            { value: "detailed", label: "Detailed" }
          ]
          value: page.s.setting("narration", "off")
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onCommitted: function(v) { page.s.put("narration", v) }
        }
      }

      KnobRow {
        objectName: "set-narrationSilenceS"
        width: parent.width
        enabled: page.s.setting("narration", "off") !== "off"
        opacity: enabled ? 1 : 0.45
        foreground: page.s.foreground; fontFamily: page.s.fontFamily
        label: "Quiet before it says anything"
        description: "How long a turn has been silent before the first sentence. Later ones come at least 10, then 15, then 25 seconds apart."
        value: page.num("narrationSilenceS", 7)
        defaultValue: page.dflt("narrationSilenceS")
        changed: page.s.changed("narrationSilenceS")
        minimum: 3; maximum: 30; stepSize: 1
        unit: "s"
        onCommitted: function(v) { page.s.put("narrationSilenceS", Math.round(v)) }
        onReset: page.s.resetKey("narrationSilenceS")
      }
    }

    // --- talking over it --------------------------------------------------------
    Card {
      objectName: "overCard"
      title: "Talking over it"
      subtitle: "Interrupting a reply"
      foreground: page.s.foreground
      accent: page.s.accent
      fontFamily: page.s.fontFamily

      ToggleRow {
        objectName: "set-fullStopAnytime"
        width: parent.width
        label: "Stop everything by voice, without the wake word"
        hint: "Stops every agent at once, even mid-thought. Not while it is speaking on speakers: the microphone is the reply's then."
        help: "sherpa-onnx listens for the full-stop command in every frame, so nothing waits for a " +
              "wake word, a pause or Whisper. On synthesized clips it caught 8 of 10 and " +
              "woke on none of 50 sound-alikes. Only with the sherpa-onnx engine; on the " +
              "others say the wake word first."
        disabledReason: page.s.usingSherpa ? "" : "Only with the sherpa-onnx engine."
        checked: page.s.setting("fullStopAnytime", true) === true
        changed: page.s.changed("fullStopAnytime")
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onToggled: page.s.put("fullStopAnytime", !checked)
        onReset: page.s.resetKey("fullStopAnytime")
      }

      ToggleRow {
        objectName: "set-bargeOnHeadset"
        width: parent.width
        label: "Interrupt by talking, on a headset"
        hint: "On headphones it stops as soon as you talk over it, and what you say is your next request."
        checked: page.s.setting("bargeOnHeadset", true) === true
        changed: page.s.changed("bargeOnHeadset")
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onToggled: page.s.put("bargeOnHeadset", !checked)
        onReset: page.s.resetKey("bargeOnHeadset")
      }

      ToggleRow {
        objectName: "set-bargeIn"
        width: parent.width
        label: "On speakers too"
        hint: "Laptop speakers usually drown you out. Measure first with: agentvoice calibrate"
        help: "Through speakers, talking cannot interrupt a reply: at a normal volume its " +
              "own voice reaches the mic as loudly as yours, so the microphone is ignored " +
              "while it talks. On a headset that problem is gone."
        checked: page.s.setting("bargeIn", false) === true
        changed: page.s.changed("bargeIn")
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onToggled: page.s.put("bargeIn", !checked)
        onReset: page.s.resetKey("bargeIn")
      }

      AdvancedSection {
        objectName: "overAdvanced"
        width: parent.width
        count: 1
        summary: "how much louder you must be"
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily

        KnobRow {
          objectName: "set-bargeFactor"
          width: parent.width
          enabled: page.s.setting("bargeIn", false) === true
                   || page.s.setting("bargeOnHeadset", true) === true
          opacity: enabled ? 1 : 0.45
          foreground: page.s.foreground; fontFamily: page.s.fontFamily
          label: "How much louder you must be"
          unit: "%"
          description: enabled ? "Than its own voice, before it stops. Higher is harder to trigger, by accident and on purpose."
                               : "Only when talking can interrupt it."
          value: page.num("bargeFactor", 150)
          defaultValue: page.dflt("bargeFactor")
          changed: page.s.changed("bargeFactor")
          minimum: 110; maximum: 400; stepSize: 10
          onCommitted: function(v) { page.s.put("bargeFactor", v) }
          onReset: page.s.resetKey("bargeFactor")
        }
      }
    }
  }

  // --- three stops, kept apart ------------------------------------------------------
  // They sound alike and are not: one ends the always-listening window, one
  // ends a reply, one unloads the models. Each says what it leaves running.
  Card {
    objectName: "stopsCard"
    width: parent.width
    title: "Three different stops"
    subtitle: "What each one ends, and what it leaves"
    foreground: page.s.foreground
    accent: page.s.accent
    fontFamily: page.s.fontFamily

    Repeater {
      model: [
        { key: "mic", name: "Turn off open mic",
          what: "It needs the wake word again. Nothing that is running is stopped, and everything stays loaded.",
          how: page.openMicOn ? "The Turn off button above." : "The Turn on button above, once it is on." },
        { key: "reply", name: "Stop a reply",
          what: (page.command("stop") ? String(page.command("stop").effect)
                 : "Stops the reply, or cancels a turn not yet sent.") + " The service keeps running.",
          how: "By voice: the " + page.labelOf("stop", "stop") + " command, listed below. The "
               + page.labelOf("full_stop", "wider one") + " command is the wider one: it ends every agent's work and the open mic too." },
        { key: "service", name: "Stop the service",
          what: "Unloads the models (about 600 MB) and nothing hears anything until it is started: three to four seconds to come back.",
          how: "The switch in the bar popup. Mute, there too, only lets go of the microphone and keeps everything warm." }
      ]
      delegate: Column {
        required property var modelData
        objectName: "stop-" + modelData.key
        width: parent.width
        spacing: Style.space(1)
        Text {
          width: parent.width
          text: modelData.name
          textFormat: Text.PlainText
          color: page.s.foreground
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.body
          font.bold: true
        }
        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          text: modelData.what + " " + modelData.how
          textFormat: Text.PlainText
          color: page.s.dim
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
    }
  }

  // --- a turn, start to end ---------------------------------------------------------
  Card {
    objectName: "turnCard"
    width: parent.width
    title: "A turn, start to end"
    subtitle: "Drawn from the timings below"
    foreground: page.s.foreground
    accent: page.s.accent
    fontFamily: page.s.fontFamily

    TurnTimeline {
      width: parent.width
      leadInMs: page.num("leadInMs", 5000)
      talkMs: page.num("maxUtteranceMs", 30000)
      pauseMs: page.num("trailingSilenceMs", 1200)
      quickMs: page.num("quickEndMs", 800)
      followMs: page.s.setting("conversationMode", true) === true ? page.num("followUpMs", 7000) : 0
      limitHits: page.limitToday
      foreground: page.s.foreground
      accent: page.s.accent
      urgent: page.s.urgent
      fontFamily: page.s.fontFamily
    }

    // Turns were cut at this limit with nothing on screen to say so (phase M2,
    // bug C). Only while it is true: the count is today's.
    Row {
      objectName: "limitNote"
      width: parent.width
      visible: page.limitLine !== ""
      spacing: Style.space(8)
      Hint {
        width: parent.width - raise.width - parent.spacing
        tone: "warn"
        text: page.limitLine
        detail: "Each of these turns stopped recording at the limit, mid-sentence " +
                "if you were still talking. Raise it if you talk for longer."
        foreground: page.s.foreground
        urgent: page.s.urgent
        fontFamily: page.s.fontFamily
      }
      Text {
        id: raise
        objectName: "raiseIt"
        text: "Raise it →"
        textFormat: Text.PlainText
        color: page.s.accent
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
        font.underline: raiseArea.containsMouse || activeFocus
        activeFocusOnTab: true
        Keys.onReturnPressed: page.s.focusKey = "maxUtteranceMs"
        Keys.onEnterPressed: page.s.focusKey = "maxUtteranceMs"
        Keys.onSpacePressed: page.s.focusKey = "maxUtteranceMs"
        MouseArea {
          id: raiseArea
          anchors.fill: parent
          hoverEnabled: true
          cursorShape: Qt.PointingHandCursor
          onClicked: page.s.focusKey = "maxUtteranceMs"
        }
      }
    }

    AdvancedSection {
      id: timings
      objectName: "timingsAdvanced"
      width: parent.width
      title: "Advanced timings"
      count: 6
      summary: "when a turn starts, ends and is cut"
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily

      Marked {
        flashed: page.flash === "leadInMs"
        outline: page.s.accent
        KnobRow {
          id: leadInKnob
          objectName: "leadInKnob"
          width: parent.width
          foreground: page.s.foreground; fontFamily: page.s.fontFamily
          label: "Time to start speaking"
          description: "After the wake word, how long it waits for you to make a sound."
          help: "If you do not, it gives up quietly and goes back to listening for the " +
                "wake word. Once you start talking this no longer applies — the pause " +
                "below ends the turn instead. Err generous: being cut off before you have " +
                "started is the most irritating way this can fail."
          value: page.num("leadInMs", 5000)
          defaultValue: page.dflt("leadInMs")
          changed: page.s.changed("leadInMs")
          minimum: 1000; maximum: 15000; stepSize: 500
          onCommitted: function(v) { page.s.put("leadInMs", v) }
          onReset: page.s.resetKey("leadInMs")
        }
      }

      Marked {
        flashed: page.flash === "trailingSilenceMs"
        outline: page.s.accent
        KnobRow {
          id: pauseKnob
          objectName: "pauseKnob"
          width: parent.width
          foreground: page.s.foreground; fontFamily: page.s.fontFamily
          label: "Pause that ends a turn"
          description: "This much quiet, under the microphone gate, and it stops listening."
          value: page.num("trailingSilenceMs", 1200)
          defaultValue: page.dflt("trailingSilenceMs")
          changed: page.s.changed("trailingSilenceMs")
          minimum: 400; maximum: 4000; stepSize: 100
          onCommitted: function(v) { page.s.put("trailingSilenceMs", v) }
          onReset: page.s.resetKey("trailingSilenceMs")
        }
      }

      Marked {
        flashed: page.flash === "quickEndMs"
        outline: page.s.accent
        KnobRow {
          id: quickKnob
          objectName: "quickKnob"
          width: parent.width
          foreground: page.s.foreground; fontFamily: page.s.fontFamily
          label: "Shorter pause when you sound finished"
          description: "Used instead when what you said reads as a finished sentence. 0 turns it off."
          help: "Whisper works through what you said at each pause, so by the time you " +
                "stop it usually has the words already. When they read as a finished " +
                "sentence, this much quiet ends the turn instead of the full pause. " +
                "Trailing off, or stopping on a word like \"and\" or \"the\", still waits " +
                "the full pause."
          value: page.num("quickEndMs", 800)
          defaultValue: page.dflt("quickEndMs")
          changed: page.s.changed("quickEndMs")
          minimum: 0; maximum: 2000; stepSize: 100
          onCommitted: function(v) { page.s.put("quickEndMs", v) }
          onReset: page.s.resetKey("quickEndMs")
        }
      }

      Marked {
        flashed: page.flash === "minUtteranceMs"
        outline: page.s.accent
        KnobRow {
          id: minKnob
          objectName: "minKnob"
          width: parent.width
          foreground: page.s.foreground; fontFamily: page.s.fontFamily
          label: "Ignore a turn shorter than"
          description: "Throws away a turn too short to hold anything — usually a wake word fired by a noise."
          help: "Measured on the whole recording — the wake word to the end of the pause " +
                "— not on the speech inside it. With the pause at its default this rarely " +
                "triggers, since any finished turn already contains that much silence; it " +
                "starts to matter once you shorten the pause."
          value: page.num("minUtteranceMs", 400)
          defaultValue: page.dflt("minUtteranceMs")
          changed: page.s.changed("minUtteranceMs")
          minimum: 0; maximum: 2000; stepSize: 100
          onCommitted: function(v) { page.s.put("minUtteranceMs", v) }
          onReset: page.s.resetKey("minUtteranceMs")
        }
      }

      Marked {
        flashed: page.flash === "maxUtteranceMs"
        outline: page.s.accent
        KnobRow {
          id: maxKnob
          objectName: "maxKnob"
          width: parent.width
          foreground: page.s.foreground; fontFamily: page.s.fontFamily
          label: "Longest a turn can be"
          description: "Counted from your first word. A microphone stuck open stops here rather than recording forever."
          value: page.num("maxUtteranceMs", 30000)
          defaultValue: page.dflt("maxUtteranceMs")
          changed: page.s.changed("maxUtteranceMs")
          minimum: 5000; maximum: 120000; stepSize: 5000
          onCommitted: function(v) { page.s.put("maxUtteranceMs", v) }
          onReset: page.s.resetKey("maxUtteranceMs")
        }
      }

      Marked {
        flashed: page.flash === "echoTailMs"
        outline: page.s.accent
        KnobRow {
          id: echoKnob
          objectName: "echoKnob"
          width: parent.width
          foreground: page.s.foreground; fontFamily: page.s.fontFamily
          label: "Deaf period after speaking"
          description: "The microphone is ignored while it talks, and for this long after."
          help: "One microphone beside the speakers cannot win against its own output, " +
                "so the mic goes deaf while the voice talks and for this long after. Too " +
                "short and it hears the end of its own sentence as you."
          value: page.num("echoTailMs", 350)
          defaultValue: page.dflt("echoTailMs")
          changed: page.s.changed("echoTailMs")
          minimum: 0; maximum: 1500; stepSize: 50
          onCommitted: function(v) { page.s.put("echoTailMs", v) }
          onReset: page.s.resetKey("echoTailMs")
        }
      }
    }
  }

  // --- voice commands -----------------------------------------------------------------
  // Phase M4's control, and the table it governs: read from the daemon, so a
  // phrase is never written on this page.
  Card {
    objectName: "commandsCard"
    width: parent.width
    title: "Voice commands"
    subtitle: page.cmd ? page.cmd.commands.length + " commands, read from the running build" : "What you can say"
    foreground: page.s.foreground
    accent: page.s.accent
    fontFamily: page.s.fontFamily

    // Where a spoken command counts besides on its own. Read with the
    // daemon's fallback: anything that is not one of the three is "alone",
    // the behaviour before it.
    SettingRow {
      id: commandsRow
      objectName: "commandsRow"
      width: parent.width
      stacked: true
      readonly property string mode: {
        var v = page.s.setting("commandsInSentences", "edges")
        return (v === "alone" || v === "edges" || v === "clause") ? v : "alone"
      }
      // An example built from the daemon's own phrase, or none while it has
      // not been read.
      readonly property string example: page.openPhrase !== ""
          ? "Take notes, and " + page.openPhrase + (mode === "clause" ? ", because I might pause." : ".") : ""
      label: "Commands inside a sentence"
      hint: mode === "clause"
            ? "Also in a clause of its own" + (example !== "" ? ": " + example : ".")
            : mode === "edges"
            ? "Also at the start or end of what you say" + (example !== "" ? ": " + example : ".")
            : "Only when the command is all you say."
      help: "A command that fires inside a sentence is said out loud once, and the rest of " +
            "the sentence goes to the agent as your request. " +
            (page.undoPhrase !== "" ? "Saying " + page.said(page.undoPhrase) + " straight after undoes an open-mic switch. " : "") +
            "It never fires with something after it, after a negative, when quoting " +
            "somebody, when two commands are in one sentence, while you dictate, or " +
            "on the agent's own voice. A command marked \"on its own\" in the list below " +
            "never fires inside a sentence."
      changed: page.s.changed("commandsInSentences")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onReset: page.s.resetKey("commandsInSentences")
      SegmentedChoice {
        options: [
          { value: "alone", label: "Alone" },
          { value: "edges", label: "Start or end" },
          { value: "clause", label: "Own clause" }
        ]
        value: commandsRow.mode
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onCommitted: function(v) { page.s.put("commandsInSentences", v) }
      }
    }

    Hint {
      width: parent.width
      tone: "warn"
      text: page.cmdProblem
      foreground: page.s.foreground
      urgent: page.s.urgent
      fontFamily: page.s.fontFamily
    }

    AdvancedSection {
      objectName: "commandList"
      width: parent.width
      title: "All commands"
      count: page.cmd ? page.cmd.commands.length : 0
      summary: "what each does, and what to say"
      visible: page.cmd !== null
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily

      Repeater {
        model: page.cmd ? page.cmd.commands : []
        delegate: Column {
          required property var modelData
          objectName: "command-" + modelData.id
          width: parent.width
          spacing: Style.space(2)

          Row {
            spacing: Style.space(8)
            Text {
              text: modelData.label
              textFormat: Text.PlainText
              color: page.s.foreground
              font.family: page.s.fontFamily
              font.pixelSize: Style.font.body
              font.bold: true
              anchors.verticalCenter: parent.verticalCenter
            }
            Pill {
              text: {
                var w = page.liveWhere(modelData)
                return w.length > 0 ? w.join(", ") : "on its own"
              }
              tone: "idle"
              foreground: page.s.foreground
              fontFamily: page.s.fontFamily
              anchors.verticalCenter: parent.verticalCenter
            }
            Pill {
              text: "no wake word needed"
              visible: modelData.needs_wake === false
              tone: "busy"
              foreground: page.s.foreground
              accent: page.s.accent
              fontFamily: page.s.fontFamily
              anchors.verticalCenter: parent.verticalCenter
            }
          }
          Text {
            width: parent.width
            wrapMode: Text.WordWrap
            text: modelData.effect
            textFormat: Text.PlainText
            color: page.s.dim
            font.family: page.s.fontFamily
            font.pixelSize: Style.font.caption
          }
          Hint {
            width: parent.width
            text: page.phraseList(modelData)
            detail: page.allPhrases(modelData)
            foreground: page.s.foreground
            fontFamily: page.s.fontFamily
          }
        }
      }
    }
  }

  Text {
    width: parent.width
    wrapMode: Text.WordWrap
    text: "Saying the stop command cancels a turn it has not taken yet — useful " +
          "when the wake word fires by mistake, so nothing is sent to the agent."
    textFormat: Text.PlainText
    color: page.s.dim
    font.family: page.s.fontFamily
    font.pixelSize: Style.font.caption
  }
}
