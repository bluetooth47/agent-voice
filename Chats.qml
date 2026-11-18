import QtQuick
import QtQuick.Controls as QQC
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "ui"

// Saved conversations (saveChats), beside this session's: a list on the
// left, grouped Pinned / Today / This week / Older, searchable and filtered
// by agent; the open chat on the right with Continue, Rename, Pin, Export
// and Delete.
//
// Read straight from ~/.local/share/agentvoice/chats/, the way the state
// file is: index.json for the list, one <id>.json for the open chat. Every
// change goes through `agentvoice chats`, which takes the same lock the
// daemon does, so a turn ending while a chat is renamed loses neither.
Item {
  id: view

  property var s

  // "session", or the id of a saved chat.
  property string selected: "session"
  property string query: ""
  // "all", "" for the main agent, or an extra agent's id.
  property string agentFilter: "all"
  property var index: ({ chats: [], current: {} })
  property var chat: ({})
  property string note: ""
  property bool renaming: false
  property bool confirmDelete: false

  readonly property string dir: s.dataHome + "/agentvoice/chats"
  readonly property bool sessionOpen: selected === "session"

  function validId(id) { return /^[0-9a-f]{16}$/.test(String(id || "")) }

  // What an agent is called now, rather than when the chat began: chats
  // know their agent by id, so a rename shows up here too.
  function agentName(c) {
    var id = String((c || {}).agent_id || "")
    if (id === "") return s.mainLabel
    for (var i = 0; i < s.voiceAgents.length; i++)
      if (s.agentId(s.voiceAgents[i]) === id) return s.agentLabel(s.voiceAgents[i])
    return String((c || {}).agent_label || "") || "a removed agent"
  }
  function inUse(c) {
    var cur = view.index.current || {}
    return cur[String(c.agent_id || "")] === c.id
  }

  function groupOf(c) {
    if (c.pinned === true) return "Pinned"
    var now = new Date()
    var start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime() / 1000
    var at = Number(c.updated) || 0
    if (at >= start) return "Today"
    if (at >= start - 6 * 86400) return "This week"
    return "Older"
  }

  // Header rows and chat rows in one list, so the groups scroll with it.
  readonly property var rows: {
    var q = view.query.trim().toLowerCase()
    var groups = { "Pinned": [], "Today": [], "This week": [], "Older": [] }
    var all = Array.isArray(view.index.chats) ? view.index.chats : []
    for (var i = 0; i < all.length; i++) {
      var c = all[i] || {}
      if (!view.validId(c.id)) continue
      if (view.agentFilter !== "all" && String(c.agent_id || "") !== view.agentFilter) continue
      if (q !== "") {
        var hay = (String(c.title || "") + " " + String(c.preview || "") + " " +
                   view.agentName(c)).toLowerCase()
        if (hay.indexOf(q) < 0) continue
      }
      groups[view.groupOf(c)].push(c)
    }
    var out = []
    var order = ["Pinned", "Today", "This week", "Older"]
    for (var g = 0; g < order.length; g++) {
      if (groups[order[g]].length === 0) continue
      out.push({ header: order[g] })
      for (var j = 0; j < groups[order[g]].length; j++) out.push({ chat: groups[order[g]][j] })
    }
    return out
  }

  readonly property var agentOptions: {
    var out = [{ label: "All agents", value: "all" }, { label: s.mainLabel, value: "" }]
    for (var i = 0; i < s.voiceAgents.length; i++)
      out.push({ label: s.agentLabel(s.voiceAgents[i]), value: s.agentId(s.voiceAgents[i]) })
    return out
  }

  function whenOf(at) {
    if (!(at > 0)) return ""
    var d = new Date(at * 1000)
    var today = new Date()
    if (d.toDateString() === today.toDateString()) return Qt.formatTime(d, "h:mm AP")
    return Qt.formatDateTime(d, "MMM d, h:mm AP")
  }

  // Asked for by the summon payload: {"mode":"history","chat":ID}.
  Connections {
    target: view.s
    function onOpenChatChanged() { if (view.s.openChat !== "") view.open(view.s.openChat) }
  }
  Component.onCompleted: if (view.s.openChat !== "") view.open(view.s.openChat)

  function open(id) {
    view.selected = id
    view.renaming = false
    view.confirmDelete = false
    view.note = ""
    if (id !== "session") chatFile.reload()
  }

  // --- files ------------------------------------------------------------------
  FileView {
    id: indexFile
    path: view.dir + "/index.json"
    watchChanges: true
    printErrors: false
    onFileChanged: indexFile.reload()
    onLoaded: {
      try {
        var d = JSON.parse(indexFile.text())
        if (d && Array.isArray(d.chats))
          view.index = { chats: d.chats, current: (d.current && typeof d.current === "object") ? d.current : {} }
      } catch (e) {}
    }
    onLoadFailed: view.index = ({ chats: [], current: {} })
  }
  // The index may not exist when the watch is set (nothing saved yet), and
  // a file created later is never watched: read again while shown.
  Timer {
    interval: 2000
    running: view.visible
    repeat: true
    triggeredOnStart: true
    onTriggered: indexFile.reload()
  }

  ListModel { id: chatModel }
  FileView {
    id: chatFile
    path: view.validId(view.selected) ? view.dir + "/" + view.selected + ".json" : ""
    watchChanges: true
    printErrors: false
    onFileChanged: chatFile.reload()
    onLoaded: {
      var d = {}
      try { d = JSON.parse(chatFile.text()) } catch (e) { return }
      if (!d || d.id !== view.selected) return
      view.chat = d
      var ex = Array.isArray(d.exchanges) ? d.exchanges : []
      // Appended rows only, when it has grown: a turn ending while it is
      // open must not throw away where you had scrolled to.
      if (chatModel.count > ex.length || chatList.chatId !== d.id) {
        chatModel.clear()
        chatList.chatId = d.id
      }
      for (var i = chatModel.count; i < ex.length; i++) {
        var e = ex[i] || {}
        chatModel.append({
          at: Number(e.at) || 0,
          transcript: String(e.transcript || ""),
          reply: String(e.reply || ""),
          failed: String(e.error || ""),
          stopped: e.stopped === true
        })
      }
    }
    onLoadFailed: {
      view.chat = ({})
      chatModel.clear()
    }
  }

  // --- actions ----------------------------------------------------------------
  property string pendingVerb: ""
  Process {
    id: action
    stdout: StdioCollector {
      onStreamFinished: {
        if (view.pendingVerb === "export" && text.trim() !== "")
          view.note = "Saved to " + text.trim()
      }
    }
    stderr: StdioCollector {
      onStreamFinished: if (text.trim() !== "") view.note = text.trim()
    }
    onRunningChanged: if (!running) { indexFile.reload(); chatFile.reload() }
  }
  function run(verb, args) {
    if (action.running) return
    view.pendingVerb = verb
    action.command = ["agentvoice", "chats", verb].concat(args)
    action.running = true
  }

  function continueChat() {
    var c = view.chat
    run("continue", [c.id])
    var program = String(c.backend || "")
    view.note = program === "claude"
                ? "Your next request to " + view.agentName(c) + " picks this conversation up where it left off."
                : "Your next request to " + view.agentName(c) + " continues this chat. " +
                  (program !== "" ? s.programLabel(program) : "This program") + " cannot resume a " +
                  "conversation, so the chat's words go with that request, which costs tokens."
  }

  // --- the list ---------------------------------------------------------------
  Column {
    id: side
    width: Math.min(Style.space(300), view.width * 0.36)
    height: parent.height
    spacing: Style.space(8)

    TextField {
      id: search
      width: parent.width
      placeholderText: "Search chats"
      foreground: view.s.foreground
      font.family: view.s.fontFamily
      onTextChanged: view.query = text
    }
    Dropdown {
      width: parent.width
      showLabel: false
      fontFamily: view.s.fontFamily
      foreground: view.s.foreground
      options: view.agentOptions
      value: view.agentFilter
      onChanged: function(v) { view.agentFilter = v }
    }

    Rectangle {
      width: parent.width
      height: sessionRow.implicitHeight + Style.space(12)
      radius: Style.cornerRadius
      color: view.sessionOpen ? Qt.rgba(view.s.foreground.r, view.s.foreground.g, view.s.foreground.b, 0.12)
                              : "transparent"
      Column {
        id: sessionRow
        anchors.verticalCenter: parent.verticalCenter
        x: Style.space(8)
        width: parent.width - Style.space(16)
        Text {
          text: "This session"
          color: view.s.foreground
          font.family: view.s.fontFamily
          font.pixelSize: Style.font.body
          font.bold: true
        }
        Text {
          text: view.s.historyRows.count + (view.s.historyRows.count === 1 ? " exchange" : " exchanges") + " · in memory"
          color: view.s.dim
          font.family: view.s.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
      MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: view.open("session") }
    }

    ListView {
      id: list
      width: parent.width
      height: parent.height - y
      clip: true
      spacing: Style.space(2)
      model: view.rows
      boundsBehavior: Flickable.StopAtBounds
      QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }

      delegate: Item {
        id: row
        required property var modelData
        readonly property bool isHeader: modelData.header !== undefined
        readonly property var c: modelData.chat || ({})
        width: ListView.view ? ListView.view.width - Style.space(8) : 0
        height: isHeader ? headerText.implicitHeight + Style.space(10) : chatRow.implicitHeight + Style.space(12)

        Text {
          id: headerText
          visible: row.isHeader
          anchors.bottom: parent.bottom
          anchors.bottomMargin: Style.space(2)
          x: Style.space(8)
          text: row.isHeader ? String(row.modelData.header).toUpperCase() : ""
          color: view.s.dim
          font.family: view.s.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
        }

        Rectangle {
          visible: !row.isHeader
          anchors.fill: parent
          radius: Style.cornerRadius
          color: view.selected === row.c.id
                 ? Qt.rgba(view.s.foreground.r, view.s.foreground.g, view.s.foreground.b, 0.12)
                 : rowMouse.containsMouse
                   ? Qt.rgba(view.s.foreground.r, view.s.foreground.g, view.s.foreground.b, 0.05)
                   : "transparent"
          Column {
            id: chatRow
            anchors.verticalCenter: parent.verticalCenter
            x: Style.space(8)
            width: parent.width - Style.space(16)
            Text {
              width: parent.width
              elide: Text.ElideRight
              text: (row.c.pinned === true ? "\u{f0403} " : "") + String(row.c.title || "Untitled chat")
              textFormat: Text.PlainText
              color: view.s.foreground
              font.family: view.s.fontFamily
              font.pixelSize: Style.font.body
            }
            Text {
              width: parent.width
              elide: Text.ElideRight
              text: view.agentName(row.c) + " · " + view.whenOf(row.c.updated)
                    + (view.inUse(row.c) ? " · in use" : "")
              textFormat: Text.PlainText
              color: view.inUse(row.c) ? view.s.accent : view.s.dim
              font.family: view.s.fontFamily
              font.pixelSize: Style.font.caption
            }
          }
          MouseArea {
            id: rowMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: view.open(row.c.id)
          }
        }
      }
    }

    Text {
      visible: view.rows.length === 0
      width: parent.width
      wrapMode: Text.WordWrap
      text: view.query !== "" || view.agentFilter !== "all"
            ? "No saved chat matches."
            : "No saved chats yet. Each conversation is saved here as it happens."
      color: view.s.dim
      font.family: view.s.fontFamily
      font.pixelSize: Style.font.caption
    }
  }

  // --- the open chat ----------------------------------------------------------
  Item {
    id: main
    anchors.left: side.right
    anchors.leftMargin: Style.space(16)
    anchors.right: parent.right
    height: parent.height

    // This session: the same rows the plain view shows.
    ListView {
      id: sessionList
      visible: view.sessionOpen
      anchors.top: parent.top
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.bottom: sessionFooter.top
      anchors.bottomMargin: Style.spacing.md
      clip: true
      spacing: Style.spacing.xxxl
      model: view.s.historyRows
      boundsBehavior: Flickable.StopAtBounds
      QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }
      onCountChanged: Qt.callLater(sessionList.positionViewAtEnd)
      delegate: ExchangeItem {
        required property int index
        required property real at
        required property string agent
        required property string transcript
        required property string reply
        required property string failed
        required property bool stopped
        required property bool fresh
        required property int latency
        width: ListView.view ? ListView.view.width - Style.space(10) : 0
        when: view.s.timeOf(at)
        who: agent
        latencyMs: latency
        heard: transcript
        answer: reply
        failure: failed
        wasStopped: stopped
        startsNew: fresh && index > 0
        foreground: view.s.foreground
        background: view.s.background
        urgent: view.s.urgent
        fontFamily: view.s.fontFamily
      }
    }
    Text {
      visible: view.sessionOpen && view.s.historyRows.count === 0
      anchors.centerIn: sessionList
      width: Math.min(parent.width, Style.space(380))
      horizontalAlignment: Text.AlignHCenter
      wrapMode: Text.WordWrap
      text: view.s.keepHistory ? "Nothing yet this session. Saved chats are on the left."
                               : "This session's view is off (Display). Saved chats are on the left."
      color: view.s.dim
      font.family: view.s.fontFamily
      font.pixelSize: Style.font.body
    }
    Item {
      id: sessionFooter
      visible: view.sessionOpen
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.bottom: parent.bottom
      height: clearSession.implicitHeight
      Text {
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width - clearSession.width - Style.space(12)
        elide: Text.ElideRight
        text: "In memory only, gone at logout. Saved chats are kept separately."
        color: view.s.dim
        font.family: view.s.fontFamily
        font.pixelSize: Style.font.caption
      }
      Button {
        id: clearSession
        anchors.right: parent.right
        visible: view.s.historyRows.count > 0
        text: view.s.confirmClear ? "Clear it all?" : "Clear"
        fontFamily: view.s.fontFamily
        bordered: true
        onClicked: {
          if (!view.s.confirmClear) { view.s.confirmClear = true; return }
          view.s.confirmClear = false
          view.s.clearSession()
        }
      }
    }

    // A saved chat.
    Column {
      id: chatHead
      visible: !view.sessionOpen
      width: parent.width
      spacing: Style.space(6)

      Text {
        visible: !view.renaming
        width: parent.width
        wrapMode: Text.WordWrap
        text: String(view.chat.title || "")
        textFormat: Text.PlainText
        color: view.s.foreground
        font.family: view.s.fontFamily
        font.pixelSize: Style.font.subtitle
        font.bold: true
      }
      TextField {
        id: renameField
        visible: view.renaming
        width: parent.width
        foreground: view.s.foreground
        font.family: view.s.fontFamily
        onAccepted: {
          var t = text.trim()
          if (t !== "" && t !== view.chat.title) view.run("rename", [view.chat.id, t])
          view.renaming = false
        }
        Keys.onEscapePressed: view.renaming = false
      }
      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        text: view.agentName(view.chat) + " · " + (view.chat.backend ? view.s.programLabel(view.chat.backend) : "agent")
              + " · started " + view.whenOf(view.chat.started)
              + (view.inUse(view.chat) ? " · in use now" : "")
        textFormat: Text.PlainText
        color: view.s.dim
        font.family: view.s.fontFamily
        font.pixelSize: Style.font.caption
      }
      Flow {
        width: parent.width
        spacing: Style.space(6)
        Button {
          text: "Continue"
          iconText: "\u{f040a}"
          bordered: true
          enabled: view.s.serviceActive && !view.inUse(view.chat)
          tooltipText: view.s.serviceActive ? "Make this " + view.agentName(view.chat) + "'s current chat"
                                            : "The service is not running"
          fontFamily: view.s.fontFamily
          onClicked: view.continueChat()
        }
        Button {
          text: "Rename"
          bordered: true
          fontFamily: view.s.fontFamily
          onClicked: {
            renameField.text = String(view.chat.title || "")
            view.renaming = true
            renameField.forceActiveFocus()
            renameField.selectAll()
          }
        }
        Button {
          text: view.chat.pinned === true ? "Unpin" : "Pin"
          bordered: true
          fontFamily: view.s.fontFamily
          onClicked: view.run(view.chat.pinned === true ? "unpin" : "pin", [view.chat.id])
        }
        Button {
          text: "Export to Markdown"
          bordered: true
          fontFamily: view.s.fontFamily
          onClicked: view.run("export", [view.chat.id])
        }
        Button {
          text: view.confirmDelete ? "Delete it?" : "Delete"
          bordered: true
          foreground: view.confirmDelete ? view.s.urgent : view.s.foreground
          fontFamily: view.s.fontFamily
          onClicked: {
            if (!view.confirmDelete) { view.confirmDelete = true; deleteTimeout.restart(); return }
            view.confirmDelete = false
            view.run("delete", [view.chat.id])
            view.open("session")
          }
        }
      }
      Text {
        visible: view.note !== ""
        width: parent.width
        wrapMode: Text.WordWrap
        text: view.note
        textFormat: Text.PlainText
        color: view.s.dim
        font.family: view.s.fontFamily
        font.pixelSize: Style.font.caption
      }
    }
    Timer { id: deleteTimeout; interval: 4000; onTriggered: view.confirmDelete = false }

    ListView {
      id: chatList
      property string chatId: ""
      visible: !view.sessionOpen
      anchors.top: chatHead.bottom
      anchors.topMargin: Style.spacing.md
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.bottom: parent.bottom
      clip: true
      spacing: Style.spacing.xxxl
      model: chatModel
      boundsBehavior: Flickable.StopAtBounds
      QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }
      delegate: ExchangeItem {
        required property real at
        required property string transcript
        required property string reply
        required property string failed
        required property bool stopped
        width: ListView.view ? ListView.view.width - Style.space(10) : 0
        when: view.whenOf(at)
        heard: transcript
        answer: reply
        failure: failed
        wasStopped: stopped
        foreground: view.s.foreground
        background: view.s.background
        urgent: view.s.urgent
        fontFamily: view.s.fontFamily
      }
    }
  }
}
