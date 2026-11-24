import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import ".."
import "../ui"

// What is happening right now, how it has been going, and anything that
// needs fixing.
//
// The page the overlay opens on. Everything here is a reading, or a link to
// the page where the thing it reads is changed -- the only controls are the
// two that change what the microphone is doing, because those are what
// somebody opening this in a hurry is looking for, and the Today / 7 days
// choice, which changes only what is shown.
//
// The numbers (master plan M21, feedback item 7) come from
// `agentvoice stats --json` (daemon/stats.py): counts and timings, never
// anything said. Every timing is shown with how many turns it is from, and
// "no data" when there are none -- an average of nothing drawn as "0 s"
// would look like a fast machine. Uptime and memory come from the state
// file's `service`.
Column {
  id: page

  required property var s

  spacing: Style.space(18)

  // --- the numbers --------------------------------------------------------
  // null until the first read; `statsProblem` says why there are none.
  property var stats: null
  property string statsProblem: ""
  property bool week: false
  readonly property var part: page.stats ? (page.week ? page.stats.range : page.stats.day) : null
  // Each agent's newest saved chat, by id ("main" for the main agent), for
  // "last chat ›": only a chat whose file is there (chats.last_by_owner).
  property var lastChats: ({})
  // Seconds since the epoch, for the uptime; moved on by the clock below.
  property real now: Date.now() / 1000

  Process {
    id: statsReader
    property bool launched: false
    command: ["agentvoice", "stats", "--days", "7", "--json"]
    onStarted: launched = true
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var d = JSON.parse(text)
          if (!d || typeof d !== "object" || !d.day || !d.range) throw "shape"
          page.stats = d
          page.statsProblem = ""
        } catch (e) {
          page.statsProblem = "The numbers could not be read."
        }
      }
    }
    onRunningChanged: if (!running && !launched)
      page.statsProblem = "No numbers: agentvoice could not be started."
  }
  Process {
    id: lastReader
    command: ["agentvoice", "chats", "last", "--json"]
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var d = JSON.parse(text)
          page.lastChats = (d && typeof d === "object" && !Array.isArray(d)) ? d : ({})
        } catch (e) { page.lastChats = ({}) }
      }
    }
  }
  function readStats() {
    if (!statsReader.running) { statsReader.launched = false; statsReader.running = true }
    if (!lastReader.running) lastReader.running = true
  }
  Component.onCompleted: readStats()
  // Rejections and the memory move without a turn ending, so a slow clock
  // as well as the reading after each turn.
  Timer {
    interval: 30000
    running: page.visible && page.s.opened
    repeat: true
    onTriggered: { page.now = Date.now() / 1000; page.readStats() }
  }
  Connections {
    target: page.s
    // A turn has ended when the daemon goes back to listening.
    function onVStateChanged() { if (page.s.opened && page.s.vState === "listening") page.readStats() }
    // The page may stay loaded while the overlay is closed: fresh numbers
    // each time it is opened again.
    function onOpenedChanged() { if (page.s.opened) { page.now = Date.now() / 1000; page.readStats() } }
  }

  function seconds(ms) {
    if (ms === null || ms === undefined || isNaN(Number(ms))) return "—"
    var x = Number(ms) / 1000
    return (x < 10 ? x.toFixed(1) : String(Math.round(x))) + " s"
  }
  function turnsWord(n) { return n === 1 ? "1 turn" : n + " turns" }
  function timingCaption(t) {
    if (!t || !t.n) return "no data yet"
    return "p95 " + page.seconds(t.p95_ms) + " · " + page.turnsWord(t.n)
  }
  function megabytes(mb) {
    if (mb === null || mb === undefined || isNaN(Number(mb))) return "—"
    return Number(mb) >= 1024 ? (Number(mb) / 1024).toFixed(1) + " GB" : Math.round(Number(mb)) + " MB"
  }
  function uptime(started) {
    var s = Number(started)
    if (!page.s.serviceActive || !s || isNaN(s)) return "—"
    var up = Math.max(0, page.now - s)
    var d = Math.floor(up / 86400), h = Math.floor(up % 86400 / 3600), m = Math.floor(up % 3600 / 60)
    if (d > 0) return d + " d " + h + " h"
    if (h > 0) return h + " h " + m + " m"
    return m > 0 ? m + " m" : "< 1 m"
  }
  // An agent's name for a count, by the id stats.py keeps.
  function labelFor(id) {
    if (id === "main") return page.s.mainLabel
    for (var i = 0; i < page.s.voiceAgents.length; i++) {
      var a = page.s.voiceAgents[i]
      if (page.s.agentId(a) === id) return page.s.agentLabel(a) || id
    }
    return id + " (removed)"
  }
  function perAgent(turns) {
    var ids = Object.keys(turns || {}).sort(function(a, b) { return turns[b] - turns[a] })
    return ids.map(function(id) { return page.labelFor(id) + " " + turns[id] }).join(" · ")
  }
  function kindsLine(k) {
    if (!k) return ""
    var parts = []
    if (k.wake) parts.push(k.wake + " by the wake word")
    if (k.followup) parts.push(k.followup + " follow-up or open mic")
    if (k.talk) parts.push(k.talk + " push-to-talk")
    if (k.typed) parts.push(k.typed + " typed")
    if (k.task) parts.push(k.task + " for another agent")
    return parts.join(", ")
  }
  function hourLabels() {
    var out = []
    var rej = page.part ? page.part.reject_hours : []
    for (var i = 0; i < 24; i++) {
      var n = rej && rej[i] ? rej[i] : 0
      out.push((i < 10 ? "0" : "") + i + ":00" + (n ? " (" + n + " turned down)" : ""))
    }
    return out
  }

  PageHeader {
    width: parent.width
    title: "Overview"
    subtitle: "What Agent Voice is doing, how it has been going, and anything that needs fixing."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
  }

  // The service: the switch stops it, which unloads ~600MB and takes
  // seconds to come back. The microphone card below has the other control,
  // the mute, which releases the mic and keeps everything warm.
  StatusCard {
    objectName: "serviceSwitch"
    width: parent.width
    icon: !page.s.serviceActive || page.s.vState === "off" ? "\u{f036d}" : "\u{f036c}"
    title: "Voice service"
    subtitle: page.s.stateLabel
    tone: page.s.stateTone
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    FocusSwitch {
      anchors.verticalCenter: parent.verticalCenter
      accessibleName: "Voice service"
      visible: page.s.engineInstalled
      checked: page.s.serviceActive
      busy: page.s.serviceBusy
      foreground: page.s.foreground
      onToggled: page.s.toggleService()
    }
  }

  // The most important control in the interface when a turn is running:
  // it kills the agent's whole process group, not just the talking.
  ActionButton {
    visible: page.s.turnRunning
    text: "Stop " + (page.s.lastWho || page.s.mainAgent || "the agent")
    iconText: "\u{f06d7}"
    bordered: true
    foreground: page.s.urgent
    accent: page.s.urgent
    fontFamily: page.s.fontFamily
    onClicked: page.s.stopTurn()
  }

  // Master plan M28: first-run setup that was skipped or closed part way.
  // A line here, never setup itself again: it is offered by itself once.
  // "Not now" stops the reminding; About → Run setup again still runs it.
  Row {
    objectName: "setupReminder"
    width: parent.width
    visible: page.s.setupUnfinished
    spacing: Style.space(10)
    StatusCard {
      width: parent.width - notNow.width - parent.spacing
      icon: "\u{f0493}"
      title: "Setup is not finished"
      subtitle: "Left at step " + (Math.max(0, page.s.setupSteps.indexOf(String(page.s.setupMarker.step || "mic"))) + 1) +
                " of 4."
      status: "finish ›"
      clickable: true
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onClicked: page.s.runSetup(String(page.s.setupMarker.step || "mic"))
    }
    ActionButton {
      id: notNow
      objectName: "setupNotNow"
      anchors.verticalCenter: parent.verticalCenter
      text: "Not now"
      bordered: true
      focusable: true
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onClicked: page.s.dismissSetup()
    }
  }

  Card {
    width: parent.width
    visible: page.s.problems.length > 0
    title: "Needs attention"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    Repeater {
      model: page.s.problems
      StatusCard {
        required property var modelData
        width: parent ? parent.width : 0
        icon: "\u{f0026}"
        title: modelData.text
        tone: "alert"
        status: modelData.page ? "fix ›" : ""
        clickable: !!modelData.page
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.s.goTo(modelData.page, modelData.agent || "")
      }
    }
  }

  // --- the numbers ----------------------------------------------------------
  Column {
    id: numbers
    objectName: "overviewNumbers"
    width: parent.width
    spacing: Style.space(10)

    Item {
      width: parent.width
      height: Math.max(numbersTitle.implicitHeight, range.implicitHeight)
      Text {
        id: numbersTitle
        anchors.verticalCenter: parent.verticalCenter
        // A Card's title, in words and weight (master plan M29: the last
        // capitalised heading left on a page).
        text: page.week ? "The last 7 days" : "Today"
        textFormat: Text.PlainText
        color: page.s.foreground
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.body
        font.bold: true
      }
      SegmentedChoice {
        id: range
        objectName: "overviewRange"
        accessibleName: "Numbers for"
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        holdMs: 0
        options: [{ value: "day", label: "Today" }, { value: "week", label: "7 days" }]
        value: page.week ? "week" : "day"
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onCommitted: function(v) { page.week = v === "week" }
      }
    }

    Hint {
      width: parent.width
      visible: text !== ""
      text: page.statsProblem !== "" ? page.statsProblem
            : (page.stats && page.stats.keeping === false
               ? "Usage numbers are off, so nothing new is counted. Turn them on in Other settings."
               : "")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
    }

    Flow {
      id: tiles
      width: parent.width
      spacing: Style.space(10)
      readonly property int columns: width >= Style.space(600) ? 3 : 2
      readonly property real tileWidth: (width - spacing * (columns - 1)) / columns

      StatTile {
        objectName: "tileTurns"
        width: tiles.tileWidth
        value: page.part ? String(page.part.turn_count) : "—"
        label: page.week ? "turns in 7 days" : "turns today"
        caption: !page.part ? "" : (page.part.turn_count > 0 ? page.perAgent(page.part.turns) : "none yet")
        tooltip: page.part && page.part.turn_count > 0 ? page.kindsLine(page.part.kinds) + "." : ""
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
      }
      StatTile {
        objectName: "tileWake"
        width: tiles.tileWidth
        value: page.part ? page.seconds(page.part.timings.wake_to_reply.median_ms) : "—"
        label: "wake to first word"
        caption: page.part ? page.timingCaption(page.part.timings.wake_to_reply) : ""
        tooltip: "The middle of the turns a wake word opened: from the wake word being " +
                 "heard to the first sound of the reply, your own sentence included. " +
                 "Follow-ups, the open microphone, push-to-talk and typed messages are left out."
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
      }
      StatTile {
        objectName: "tileReply"
        width: tiles.tileWidth
        value: page.part ? page.seconds(page.part.timings.reply.median_ms) : "—"
        label: "reply after you stop"
        caption: page.part ? page.timingCaption(page.part.timings.reply) : ""
        tooltip: "From the end of what you said (or the key coming up) to the first " +
                 "sound of the reply: the wait you sit through."
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
      }
      StatTile {
        objectName: "tileTranscribe"
        width: tiles.tileWidth
        value: page.part ? page.seconds(page.part.timings.transcribe.median_ms) : "—"
        label: "transcription"
        caption: page.part ? page.timingCaption(page.part.timings.transcribe) : ""
        tooltip: "Whisper's own time on what was said, from its start to the final text. " +
                 "Much of it runs while you are still talking."
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
      }
      StatTile {
        objectName: "tileWakes"
        width: tiles.tileWidth
        value: page.part ? page.part.wakes + " / " + page.part.rejected : "—"
        label: "wakes / turned down"
        caption: !page.part ? "" : (page.part.rejected_by["second-check"]
                                    + (page.part.rejected_by["second-check"] === 1 ? " false wake" : " false wakes")
                                    + " (second check)"
                                    + (page.part.rejected_by.confidence ? " · " + page.part.rejected_by.confidence
                                                                          + " unsure" : "")
                                    // Master plan M22: with both stages made to agree.
                                    + (page.part.rejected_by.held ? " · " + page.part.rejected_by.held
                                                                    + " held" : ""))
        tooltip: "A false wake here is a burst in which a name was heard and the second check " +
                 "turned it down -- exactly that, not every wake that did not happen. \"Unsure\" " +
                 "is the grammar engine hearing the phrase below the confidence bar. \"Held\" " +
                 "is a name one stage heard and the other did not confirm, with both stages made " +
                 "to agree (Listening)." +
                 (page.part && page.part.wakes_by && page.part.wakes_by.confirmed
                  ? " " + page.part.wakes_by.confirmed + " confirmed by the second check." : "") +
                 (page.part && page.part.limit_hits ? " " + page.part.limit_hits +
                  (page.part.limit_hits === 1 ? " turn was" : " turns were") + " cut at the longest-turn limit." : "")
        tone: page.part && page.part.rejected > 0 ? "busy" : "active"
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
      }
      StatTile {
        objectName: "tileUptime"
        width: tiles.tileWidth
        readonly property var svc: page.s.vService || ({})
        value: page.uptime(svc.started_at)
        label: "up"
        caption: page.s.serviceActive && svc.rss_mb !== undefined
                 ? "service " + page.megabytes(svc.rss_mb) + " · agents " + page.megabytes(svc.agents_mb)
                 : (page.s.serviceActive ? "" : "the service is off")
        tooltip: "Resident memory, read every 30 seconds: the voice service itself, and apart from " +
                 "it every process it started -- the agents' programs and their tool servers. " +
                 "A library shared by several is counted in each, so the agents' figure leans high."
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
      }
    }

    Text {
      width: parent.width
      text: page.week ? "Wakes by hour, over 7 days" : "Wakes by hour, today"
      color: page.s.foreground
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    MiniBars {
      objectName: "wakeBars"
      accessibleName: "Wakes by hour"
      width: parent.width
      values: page.part ? page.part.wake_hours : []
      labels: page.hourLabels()
      unit: "wakes"
      highlight: page.week ? -1 : new Date(page.now * 1000).getHours()
      emptyText: page.week ? "No wakes in the last 7 days." : "No wakes yet today."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
    }
  }

  // --- the microphone: its level, the gate, and the mute ---------------------
  Card {
    width: parent.width
    title: "Microphone"
    subtitle: page.s.setting("adaptiveGate", false) === true ? "The gate follows the room."
              : "Gate at " + page.s.setting("micThresholdDb", -38) + " dBFS."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    LevelMeter {
      width: parent.width
      levelDb: page.s.serviceActive ? page.s.levelDb : -99
      gateDb: page.s.gateInForce
      idleText: page.s.serviceActive ? "no reading — the microphone is off"
                                     : "no reading — the service is off"
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
    }
    Item {
      width: parent.width
      height: Math.max(muteButton.implicitHeight, gateLink.implicitHeight)
      ActionButton {
        id: muteButton
        objectName: "muteButton"
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        visible: page.s.serviceActive
        text: page.s.vState === "off" ? "Unmute mic" : "Mute mic"
        iconText: page.s.vState === "off" ? "\u{f036c}" : "\u{f036d}"
        bordered: true
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.s.toggleMic()
      }
      TextLink {
        id: gateLink
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        text: "Listening settings ›"
        foreground: page.s.foreground
        accent: page.s.accent
        dim: page.s.dim
        font.family: page.s.fontFamily
        onActivated: page.s.goTo("listening", "")
      }
    }
  }

  Card {
    width: parent.width
    title: "Agents"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    StatusCard {
      width: parent.width
      readonly property string st: page.s.agentStatus("")
      icon: "\u{f06a9}"
      title: page.s.mainLabel
      subtitle: "“" + page.s.activePhrase + "” · " +
                (page.s.usingEndpoint ? "endpoint · " + page.s.setting("endpointModel", "")
                                      : (page.s.mainAgent ? page.s.programLabel(page.s.mainAgent) : "no default agent")) +
                " · default"
      status: st
      tone: page.s.statusTone(st)
      clickable: true
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onClicked: page.s.goTo("agents", "main")

      LastChatLink {
        chatId: String(page.lastChats["main"] || "")
      }
    }

    Repeater {
      model: page.s.voiceAgents
      StatusCard {
        required property var modelData
        readonly property string name: String(modelData.name || "")
        readonly property string agentId: page.s.agentId(modelData)
        readonly property string st: modelData.enabled === false ? "switched off" : page.s.agentStatus(agentId)
        width: parent ? parent.width : 0
        icon: "\u{f06a9}"
        title: page.s.agentLabel(modelData) || "unnamed agent"
        subtitle: "“" + name + "” · " + page.s.programLabel(String(modelData.agent || "claude"))
                  + (modelData.model ? " · " + modelData.model : "")
        status: st
        tone: String((page.s.crewInfo(agentId) || {}).problem || "") !== "" ? "alert" : page.s.statusTone(st)
        clickable: true
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.s.goTo("agents", agentId)

        LastChatLink {
          chatId: String(page.lastChats[agentId] || "")
        }
      }
    }

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      text: page.s.voiceAgents.length === 0
            ? "One agent. Add more on the Agents page, each woken by its own name."
            : "Start a sentence with a name to talk to that agent."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
  }

  // "last chat ›" on an agent's card: opens its newest saved chat on the
  // Chats page. Drawn only for a chat that is really there.
  component LastChatLink: TextLink {
    id: chatLink
    property string chatId: ""
    property string who: ""
    visible: chatId !== ""
    anchors.verticalCenter: parent ? parent.verticalCenter : undefined
    text: "last chat ›"
    accessibleName: "Open " + (who !== "" ? who + "'s" : "its") + " last chat"
    foreground: page.s.foreground
    accent: page.s.accent
    dim: page.s.dim
    font.family: page.s.fontFamily
    onActivated: page.s.showChat(chatLink.chatId)
  }

  Card {
    width: parent.width
    visible: page.s.lastTranscript !== ""
    title: "Last exchange"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    Text {
      width: parent.width
      visible: page.s.lastWho !== ""
      text: page.s.lastWho
      textFormat: Text.PlainText
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      maximumLineCount: 3
      elide: Text.ElideRight
      // A transcript of speech: attacker-shaped input as far as the UI is
      // concerned, so never markup.
      text: page.s.lastTranscript
      textFormat: Text.PlainText
      color: page.s.foreground
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.body
    }
    Item {
      width: parent.width
      visible: page.s.lastReply !== ""
      height: replyText.implicitHeight
      Rectangle {
        width: Style.space(2)
        height: parent.height
        color: Qt.rgba(page.s.foreground.r, page.s.foreground.g, page.s.foreground.b, 0.35)
      }
      Text {
        id: replyText
        x: Style.space(10)
        width: parent.width - x
        wrapMode: Text.WordWrap
        maximumLineCount: 4
        elide: Text.ElideRight
        text: page.s.lastReply
        textFormat: Text.PlainText
        color: page.s.dim
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.body
      }
    }
    ActionButton {
      text: "Open the whole conversation"
      iconText: "\u{f0b79}"
      bordered: true
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onClicked: page.s.showChat("")
    }
  }
}
