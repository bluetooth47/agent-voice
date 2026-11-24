import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// "Send to another agent" (merged plan, Phase 15): pass a conversation on.
//
// Sending is the confirmation, so everything that will happen is on the
// sheet before the button is pressed: who receives it, the exact brief
// (editable), that the whole chat goes with it, and for an endpoint the
// host it is sent to. Nothing is shared or dispatched until Send, and then
// through `agentvoice pass`, the same path the CLI and the voice command
// take; the daemon checks the target again when the turn starts.
//
// `s` is the overlay (Settings.qml). Opened with open(fromId, chatId):
// fromId is the source agent's external id ("main" for the main agent),
// chatId a saved chat's id or "" for this session's conversation.
Rectangle {
  id: sheet

  property var s
  property bool shown: false
  property string fromId: "main"
  property string chatId: ""
  property string toId: ""
  property string note: ""
  property bool sending: false
  property bool sent: false
  // One press is one task: the id goes with the request, and the daemon
  // files a second arrival under the first.
  property string taskId: ""
  property var chat: ({})
  // The requested chat has been read into the brief: until then Send would
  // send whatever the box held before.
  property bool loaded: true

  visible: shown
  // Opaque: the theme's menu colour may be translucent, and the page
  // beneath must not show through the brief.
  color: Qt.rgba(sheet.s.background.r, sheet.s.background.g, sheet.s.background.b, 1)
  radius: Style.cornerRadius
  // Swallow clicks so they do not reach the page beneath.
  MouseArea { anchors.fill: parent }
  Keys.onEscapePressed: sheet.close()

  function hex(n) {
    var out = ""
    for (var i = 0; i < n; i++) out += "0123456789abcdef"[Math.floor(Math.random() * 16)]
    return out
  }

  function open(fromId, chatId) {
    sheet.fromId = /^[a-z0-9][a-z0-9-]{0,47}$/.test(String(fromId || "")) ? String(fromId) : "main"
    sheet.chatId = /^[0-9a-f]{16}$/.test(String(chatId || "")) ? String(chatId) : ""
    sheet.note = ""
    sheet.sending = false
    sheet.sent = false
    sheet.answeredFor = false
    closeLater.stop()
    ackTimeout.stop()
    sheet.taskId = sheet.hex(16)
    sheet.chat = ({})
    var c = sheet.candidates
    sheet.toId = c.length > 0 ? c[0].value : ""
    sheet.shown = true
    briefBox.reset("")
    if (sheet.chatId !== "") { sheet.loaded = false; chatFile.reload() }
    else { briefBox.reset(sheet.sessionBrief()); sheet.loaded = true }
    sheet.forceActiveFocus()
  }
  function close() { sheet.shown = false }

  // --- who --------------------------------------------------------------------
  function nameOf(id) {
    if (id === "main") return sheet.s.mainLabel
    for (var i = 0; i < sheet.s.voiceAgents.length; i++)
      if (sheet.s.agentId(sheet.s.voiceAgents[i]) === id) return sheet.s.agentLabel(sheet.s.voiceAgents[i])
    return id
  }
  function entryOf(id) {
    for (var i = 0; i < sheet.s.voiceAgents.length; i++)
      if (sheet.s.agentId(sheet.s.voiceAgents[i]) === id) return sheet.s.voiceAgents[i]
    return null
  }
  // Whether the daemon has it built and answering: the live map is keyed
  // by internal id, "" for the main agent.
  function reachable(id) {
    var live = sheet.s.vLive || {}
    var key = id === "main" ? "" : id
    if (live[key] === undefined) return false
    if (id === "main") return true
    var e = sheet.entryOf(id)
    return e !== null && e.enabled !== false && String(sheet.s.crewInfo(id).problem || "") === ""
  }
  readonly property var candidates: {
    var out = []
    var ids = ["main"]
    for (var i = 0; i < sheet.s.voiceAgents.length; i++) ids.push(sheet.s.agentId(sheet.s.voiceAgents[i]))
    for (var j = 0; j < ids.length; j++) {
      if (ids[j] === sheet.fromId || !sheet.reachable(ids[j])) continue
      out.push({ label: sheet.nameOf(ids[j]) + (sheet.quarantined(ids[j]) ? " (quarantined)" : ""),
                 value: ids[j] })
    }
    return out
  }
  // Phase M8: a pass the person starts needs no crew link -- they are its
  // approver -- but nothing goes into quarantine, and the daemon refuses it
  // too. A quarantine list that cannot be read refuses every pass (the
  // daemon cannot tell either), so it is said here before Send.
  function quarantined(id) {
    var q = sheet.s.cfg["crewQuarantine"]
    if (q === undefined) return false
    return !Array.isArray(q) || q.indexOf(id) >= 0
  }
  readonly property string denied: {
    if (sheet.toId === "" || !sheet.quarantined(sheet.toId)) return ""
    if (!Array.isArray(sheet.s.cfg["crewQuarantine"]))
      return "The crew settings can't be read, so nothing can be passed until they are fixed on the Crew map."
    return sheet.nameOf(sheet.toId) + " is quarantined. Release it on the Crew map first."
  }
  function hostOf(url) {
    // The scheme is optional: the settings may hold `localhost:11434`.
    var m = String(url || "").match(/^(?:[a-z][a-z0-9+.-]*:\/\/)?(?:[^@\/]*@)?(\[[^\]]*\]|[^:\/?#]+)/i)
    return m ? m[1] : String(url || "")
  }
  // The host an endpoint target sends to; "" for any other program.
  readonly property string host: {
    if (sheet.toId === "main")
      return sheet.s.usingEndpoint ? sheet.hostOf(sheet.s.setting("endpointUrl", "")) : ""
    var e = sheet.entryOf(sheet.toId)
    return (e && e.agent === "endpoint") ? sheet.hostOf(e.endpointUrl) : ""
  }

  // --- the brief ----------------------------------------------------------------
  function briefOf(transcript, reply, who) {
    var t = ""
    if (transcript) t += "User: " + transcript + "\n"
    if (reply) t += (who || "Agent") + ": " + reply
    return Array.from(t.trim()).slice(0, 2000).join("")
  }
  // The last exchange with the source in this session's memory.
  function sessionBrief() {
    var rows = sheet.s.historyRows
    for (var i = rows.count - 1; i >= 0; i--) {
      var r = rows.get(i)
      if (String(r.agentId || "main") !== sheet.fromId) continue
      return sheet.briefOf(r.transcript, r.reply, r.agent || sheet.nameOf(sheet.fromId))
    }
    return ""
  }
  FileView {
    id: chatFile
    path: sheet.chatId !== "" ? sheet.s.dataHome + "/agentvoice/chats/" + sheet.chatId + ".json" : ""
    printErrors: false
    onLoaded: {
      var d = {}
      try { d = JSON.parse(chatFile.text()) } catch (e) { d = {} }
      sheet.chat = (d && d.id === sheet.chatId) ? d : ({})
      var ex = Array.isArray(sheet.chat.exchanges) ? sheet.chat.exchanges : []
      var last = ex.length > 0 ? ex[ex.length - 1] : {}
      briefBox.reset(sheet.briefOf(String(last.transcript || ""), String(last.reply || ""),
                                   String(last.agent_label || sheet.chat.agent_label || "")))
      sheet.loaded = sheet.chat.id === sheet.chatId
      if (!sheet.loaded) sheet.note = "That chat could not be read, so it cannot be sent."
    }
    onLoadFailed: {
      sheet.chat = ({})
      briefBox.reset("")
      sheet.loaded = false
      sheet.note = "That chat could not be read, so it cannot be sent."
    }
  }

  // --- sending --------------------------------------------------------------------
  Process {
    id: sender
    property string pending: ""
    property bool failed: false
    // -1 until it exits: a spawn that never started emits no exit at all.
    property int code: -1
    stdinEnabled: true
    onExited: function(exitCode, exitStatus) { sender.code = exitCode }
    onStarted: { write(sender.pending + "\n"); sender.pending = "" }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        // The CLI says what it is doing on stderr before it sends, and why
        // when it refuses; only a refusal starts with its name.
        if (t.indexOf("agentvoice") === 0 || t.indexOf("usage:") === 0) {
          sender.failed = true
          sheet.note = t.replace(/^agentvoice( pass)?: /, "")
        }
      }
    }
    // `running` going false, not onExited: a spawn that never started emits
    // no exit, and a send that did nothing must say so.
    onRunningChanged: if (!running) sentCheck.restart()
  }
  Timer {
    id: sentCheck
    interval: 150
    onTriggered: {
      sheet.sending = false
      if (sender.failed) return
      if (sender.code !== 0) {
        if (sheet.note === "") sheet.note = "Not sent: agentvoice did not run."
        return
      }
      // Handed over; what the daemon made of it is read back from its
      // task list by id below, so a pass it refused is not shown as sent.
      sheet.sent = true
      sheet.note = "Handed to the service…"
      ackTimeout.restart()
      // The daemon may have answered before the CLI exited: read it now,
      // since the change that announced it has already gone by.
      sheet.readAck()
    }
  }
  // The daemon's answer, from the state file: the task filed under this
  // press's id.
  readonly property var ack: {
    var tasks = sheet.s.vTasks || []
    for (var i = 0; i < tasks.length; i++)
      if (tasks[i] && tasks[i].id === sheet.taskId) return tasks[i]
    return null
  }
  onAckChanged: sheet.readAck()
  // Set once the daemon has answered this press, so a state file re-read
  // with the same task does not restart the close timer over and over.
  property bool answeredFor: false
  function readAck() {
    if (!sheet.sent || sheet.answeredFor || sheet.ack === null) return
    // Read before anything below changes taskId, which changes `ack`.
    var st = String(sheet.ack.state || "")
    var reason = String(sheet.ack.reason || st)
    var queued = st === "pending" && Number(sheet.ack.position || 0) > 0
    ackTimeout.stop()
    sheet.answeredFor = true
    if (st === "refused" || st === "failed" || st === "cancelled") {
      closeLater.stop()
      sheet.sent = false
      sheet.answeredFor = false
      sheet.taskId = sheet.hex(16)        // a fresh press is a fresh task
      sheet.note = "Not passed: " + reason
      return
    }
    sheet.note = queued
                 ? "Sent. " + sheet.nameOf(sheet.toId) + " is busy; it goes to them when they've finished."
                 : "Sent. " + sheet.nameOf(sheet.toId) + " has it; the reply shows in the conversation."
    closeLater.restart()
  }
  Timer {
    id: ackTimeout
    interval: 6000
    // Send comes back, with the same id: pressing it again cannot make a
    // second task if the first does arrive.
    onTriggered: if (sheet.sent && sheet.ack === null) {
                   sheet.sent = false
                   sheet.note = "The service has not picked it up yet. Is it running? Send tries again."
                 }
  }
  Timer { id: closeLater; interval: 2500; onTriggered: sheet.close() }
  function send() {
    if (sheet.sending || sheet.toId === "" || sheet.denied !== "") return
    sheet.note = ""
    sheet.sending = true
    sender.failed = false
    sender.code = -1
    // Cut to what the daemon takes, so what is sent is what was shown.
    sender.pending = JSON.stringify(Array.from(briefBox.text.trim()).slice(0, 2000).join(""))
    // The host this sheet showed goes with it: the daemon refuses the pass
    // if the chat would go anywhere else.
    sender.command = ["agentvoice", "pass", sheet.toId, "--from", sheet.fromId,
                      "--entry", "sheet", "--id", sheet.taskId, "--host", sheet.host, "--line"]
                     .concat(sheet.chatId !== "" ? ["--chat", sheet.chatId] : [])
    sender.running = true
  }

  // --- the sheet ------------------------------------------------------------------
  Column {
    anchors.fill: parent
    anchors.margins: Style.spacing.panelPadding
    spacing: Style.space(10)

    Text {
      width: parent.width
      text: "Send to another agent"
      color: sheet.s.foreground
      font.family: sheet.s.fontFamily
      font.pixelSize: Style.font.subtitle
      font.bold: true
    }
    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: "From " + sheet.nameOf(sheet.fromId) +
            (sheet.chatId !== "" && sheet.chat.title ? ", the chat “" + sheet.chat.title + "”"
                                                     : ", this session's conversation") + "."
      color: sheet.s.dim
      font.family: sheet.s.fontFamily
      font.pixelSize: Style.font.caption
    }

    Text {
      visible: sheet.candidates.length === 0
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: sheet.s.serviceActive
            ? "No other agent can take it right now: each one is switched off, cannot be heard by the wake engine, or is not set up."
            : "The service is not running, so nothing can be passed."
      color: sheet.s.urgent
      font.family: sheet.s.fontFamily
      font.pixelSize: Style.font.body
    }
    Dropdown {
      visible: sheet.candidates.length > 0
      width: parent.width
      label: "To"
      fontFamily: sheet.s.fontFamily
      foreground: sheet.s.foreground
      options: sheet.candidates
      value: sheet.toId
      onChanged: function(v) { sheet.toId = v }
    }

    Text {
      width: parent.width
      text: "Brief"
      color: sheet.s.foreground
      font.family: sheet.s.fontFamily
      font.pixelSize: Style.font.body
    }
    InstructionsBox {
      id: briefBox
      width: parent.width
      maxLength: 2000
      minHeight: Style.space(110)
      placeholder: "What they should know. The last exchange is filled in; change it as you like."
      editingHint: "sent as it is"
      foreground: sheet.s.foreground
      accent: sheet.s.accent
      fontFamily: sheet.s.fontFamily
    }

    // What travels, said before it does (open question 3: the target
    // joins the chat). The words match collab.sees_line.
    Text {
      visible: sheet.toId !== ""
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: sheet.nameOf(sheet.toId) + " will see this whole chat (up to 8000 characters) and the brief, " +
            "and answers in it from now on. " + sheet.nameOf(sheet.fromId) +
            "'s session, tool results and approvals do not go with it."
      color: sheet.s.foreground
      font.family: sheet.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Text {
      visible: sheet.host !== ""
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: sheet.nameOf(sheet.toId) + " is an endpoint: the chat and the brief are sent to " +
            sheet.host + ", off this machine."
      color: sheet.s.urgent
      font.family: sheet.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Text {
      visible: sheet.denied !== ""
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: sheet.denied
      color: sheet.s.urgent
      font.family: sheet.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Text {
      visible: sheet.note !== ""
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: sheet.note
      color: sheet.sent ? sheet.s.accent : sheet.s.urgent
      font.family: sheet.s.fontFamily
      font.pixelSize: Style.font.caption
    }

    Row {
      spacing: Style.space(8)
      ActionButton {
        text: sheet.sending ? "Sending…" : "Send"
        bordered: true
        focusable: true
        enabled: sheet.toId !== "" && sheet.denied === "" && sheet.loaded && !sheet.sending && !sheet.sent
                 && sheet.s.serviceActive
        fontFamily: sheet.s.fontFamily
        foreground: sheet.s.foreground
        onClicked: sheet.send()
      }
      ActionButton {
        text: "Cancel"
        bordered: true
        focusable: true
        fontFamily: sheet.s.fontFamily
        foreground: sheet.s.foreground
        onClicked: sheet.close()
      }
    }
  }
}
