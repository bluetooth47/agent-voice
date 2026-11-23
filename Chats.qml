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
// by agent; the open chat on the right, drawn as a messaging app draws one,
// with continuation, sharing and conversation management controls.
//
// One component, three places (phase M18): the Chats page (every chat, this
// session first), Agent details → Chats (`scope: "agent"`, one agent's) and
// Communal → Chats (`scope: "multi"`, those more than one agent spoke in).
//
// Read straight from ~/.local/share/agentvoice/chats/, the way the state
// file is: index.json for the list, one <id>.json for the open chat. Every
// change goes through `agentvoice chats`, which takes the same lock the
// daemon does, so a turn ending while a chat is renamed loses neither. The
// search box asks `agentvoice chats search` with the words on stdin, never
// argv (/proc/PID/cmdline is readable by every local account), and so does
// a rename.
Item {
  id: view

  property var s

  // "all": every chat; "agent": those `scopeAgent` (external id) owns, has
  // spoken in or may carry on; "multi": those more than one agent spoke in.
  property string scope: "all"
  property string scopeAgent: ""
  // The "This session" entry at the top of the list.
  property bool showSession: true
  // Follows the summon payload's chat ({"page":"chats","chat":ID}) and
  // keeps the open chat in s.openChat, so leaving the page and coming back
  // finds it open. Only the Chats page does: an embedded browser opening a
  // chat must not move the page's.
  property bool followSummon: false

  // "session", "" (nothing open), or the id of a saved chat.
  property string selected: showSession ? "session" : ""
  property string query: ""
  // What `chats search` answered for `query`: {id: score}, or null while it
  // has not (the list then filters on the words it already holds).
  property var results: null
  property string searchNote: ""
  // "all", "multi", or an agent's external id ("main" for the main agent).
  property string agentFilter: "all"
  property var index: ({ chats: [], current: {} })
  property var chat: ({})
  property string note: ""
  property bool renaming: false

  readonly property string dir: s.dataHome + "/agentvoice/chats"
  readonly property bool sessionOpen: showSession && selected === "session"
  readonly property bool savedChatOpen: view.validId(selected) && chat.id === selected
  readonly property bool narrow: width < Style.space(560)
  readonly property string ownerId: view.ownerOf(chat)
  readonly property var sharedAgents: Array.isArray(chat.shared_with) ? chat.shared_with : []
  readonly property var continueAgents: {
    var entry = view.index.chats.find(function(c) { return c && c.id === view.chat.id })
    // The index lists who can continue. The full chat can arrive ahead of it.
    var ids = entry && Array.isArray(entry.agents) ? entry.agents
              : view.sharedAgents.concat(Object.keys(view.chat.sessions || {}))
    return ids.filter(function(id) { return id !== view.ownerId })
  }

  function validId(id) { return /^[0-9a-f]{16}$/.test(String(id || "")) }

  // The open chat's entry in the index: its title as shown (phase M19: a
  // rename, else the name its agent wrote, else the first sentence -- the
  // daemon decides, chats.display_title) and its summary. The chat file
  // can arrive ahead of the index; its own title stands in until then.
  readonly property var openMeta: {
    var all = Array.isArray(view.index.chats) ? view.index.chats : []
    for (var i = 0; i < all.length; i++) if (all[i] && all[i].id === view.chat.id) return all[i]
    return ({})
  }
  readonly property string openTitle: String(view.openMeta.title || view.chat.title || "")
  readonly property string openSummary: String(view.openMeta.summary || view.chat.summary || "")

  // How long a chat ran, first word to last: "12 min", "2 h", "over 3 days".
  function durationOf(c) {
    var a = Number(c.started) || 0, b = Number(c.updated) || 0
    var secs = b - a
    if (!(a > 0) || !(secs >= 60)) return ""
    if (secs < 3600) return Math.round(secs / 60) + " min"
    if (secs < 86400) return Math.round(secs / 3600) + " h"
    var days = Math.round(secs / 86400)
    return "over " + days + (days === 1 ? " day" : " days")
  }

  // The words of a search, filters (agent:, before:, after:) left out, for
  // matching on what the list already holds before the search answers.
  function plainWords(q) {
    return String(q || "").replace(/(^|\s)(agent|before|after):("[^"]*"|\S*)/gi, " ")
                          .replace(/\s+/g, " ").trim()
  }

  function ownerOf(c) { return String(c.owner || c.agent_id || "main") }

  // A Repeater's modelData, or JSON from a FileView, can hand over a list
  // Array.isArray does not recognise; membership is checked by hand.
  function has(list, id) {
    if (!list || list.length === undefined) return false
    for (var i = 0; i < list.length; i++) if (list[i] === id) return true
    return false
  }

  function currentAgentName(id) {
    if (id === "main") return s.mainLabel
    for (var i = 0; i < s.voiceAgents.length; i++) {
      var agent = s.voiceAgents[i]
      if (s.agentId(agent) === id) return s.agentLabel(agent)
    }
    return ""
  }

  // The owner's current name, or the saved label for a removed agent.
  function agentName(c) {
    return view.currentAgentName(view.ownerOf(c)) || String(c.agent_label || "a removed agent")
  }

  // Everyone who spoke, owner first: "Theo + Sora".
  function peopleOf(c) {
    var ids = [view.ownerOf(c)]
    var said = c.participants || []
    for (var i = 0; i < said.length; i++) if (!view.has(ids, said[i])) ids.push(String(said[i]))
    return ids.map(function(id, n) {
      return n === 0 ? view.agentName(c) : (view.currentAgentName(id) || id)
    }).join(" + ")
  }

  // Some agent's current chat: a shared chat can be Sora's while its
  // owner has moved on. For the label; Continue asks about the owner alone.
  function currentOf(agent) {
    var cur = view.index.current || {}
    var id = cur[agent === "main" ? "" : agent]
    return view.validId(id) ? id : ""
  }
  function inUseByAnyone(c) {
    var cur = view.index.current || {}
    for (var k in cur) if (cur[k] === c.id) return true
    return false
  }
  function inUse(c) {
    var cur = view.index.current || {}
    var id = view.ownerOf(c)
    return cur[id === "main" ? "" : id] === c.id
  }

  function lastSpeaker() {
    var exchanges = view.chat.exchanges
    var last = Array.isArray(exchanges) && exchanges.length > 0 ? exchanges[exchanges.length - 1] : null
    return String((last && last.agent_id) || view.ownerId)
  }

  function sessionSpeaker() {
    var rows = view.s.historyRows
    return rows.count > 0 ? String(rows.get(rows.count - 1).agentId || "main") : "main"
  }

  function exchangeSpeaker(id, label, kind, passedFrom) {
    var name = label || view.currentAgentName(id) || view.agentName(view.chat)
    if (kind === "brief") {
      var source = view.currentAgentName(passedFrom) || passedFrom || "another agent"
      return name + " (passed from " + source + ")"
    }
    return name
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

  function inScope(c) {
    if (view.scope === "multi")
      return c.participants !== undefined && c.participants.length > 1
    if (view.scope === "agent")
      return view.ownerOf(c) === view.scopeAgent || view.has(c.agents, view.scopeAgent)
             || view.has(c.participants, view.scopeAgent)
    return true
  }
  function passesFilter(c) {
    if (view.agentFilter === "all") return true
    if (view.agentFilter === "multi") return c.participants !== undefined && c.participants.length > 1
    return view.ownerOf(c) === view.agentFilter || view.has(c.participants, view.agentFilter)
  }
  // Until the search answers (or if it cannot run), the words the list
  // already holds: title, summary (M19), the last thing said, who. Filters
  // are left to the search.
  function localMatch(c, q) {
    var words = view.plainWords(q)
    if (words === "") return true
    var hay = (String(c.title || "") + " " + String(c.summary || "") + " " + String(c.preview || "")
               + " " + view.peopleOf(c)).toLowerCase()
    return hay.indexOf(words) >= 0
  }

  // Header rows and chat rows in one list, so the groups scroll with it.
  // With a search: one group, best match first.
  readonly property var rows: {
    var q = view.query.trim().toLowerCase()
    var groups = { "Pinned": [], "Today": [], "This week": [], "Older": [] }
    var found = []
    var all = Array.isArray(view.index.chats) ? view.index.chats : []
    for (var i = 0; i < all.length; i++) {
      var c = all[i] || {}
      if (!view.validId(c.id) || !view.inScope(c) || !view.passesFilter(c)) continue
      if (q !== "") {
        if (view.results !== null) {
          if (view.results[c.id] === undefined) continue
        } else if (!view.localMatch(c, q)) continue
        found.push(c)
        continue
      }
      groups[view.groupOf(c)].push(c)
    }
    var out = []
    if (q !== "") {
      if (view.results !== null)
        found.sort(function(a, b) {
          return (view.results[b.id] - view.results[a.id]) || ((Number(b.updated) || 0) - (Number(a.updated) || 0))
        })
      if (found.length > 0) out.push({ header: view.results !== null ? "Best matches" : "Matches" })
      for (var f = 0; f < found.length; f++) out.push({ chat: found[f] })
      return out
    }
    var order = ["Pinned", "Today", "This week", "Older"]
    for (var g = 0; g < order.length; g++) {
      if (groups[order[g]].length === 0) continue
      out.push({ header: order[g] })
      for (var j = 0; j < groups[order[g]].length; j++) out.push({ chat: groups[order[g]][j] })
    }
    return out
  }
  // Every saved chat in the index, whatever is filtered: the Chats page
  // reads the folder's size again when it moves.
  readonly property int savedCount: Array.isArray(view.index.chats) ? view.index.chats.length : 0
  readonly property int chatRowCount: {
    var n = 0
    for (var i = 0; i < view.rows.length; i++) if (view.rows[i].chat !== undefined) n++
    return n
  }

  readonly property var agents: {
    var out = [{ label: s.mainLabel, value: "main" }]
    for (var i = 0; i < s.voiceAgents.length; i++)
      out.push({ label: s.agentLabel(s.voiceAgents[i]), value: s.agentId(s.voiceAgents[i]) })
    return out
  }
  // The filter chips: only on the Chats page, where every chat is listed.
  readonly property var filterChips: view.scope !== "all" ? []
    : [{ id: "multi", label: "Agent conversations",
         tooltip: "Chats more than one agent has spoken in" }]
      .concat(view.agents.map(function(agent) {
        return { id: agent.value, label: agent.label, tooltip: "Chats " + agent.label + " has spoken in" }
      }))
  readonly property var shareOptions: view.agents.filter(function(agent) {
    return agent.value !== view.ownerId && view.sharedAgents.indexOf(agent.value) === -1
  })
  readonly property var unshareOptions: view.sharedAgents.map(function(id) {
    return { label: "Stop sharing with " + (view.currentAgentName(id) || id), value: id }
  })

  function whenOf(at) {
    if (!(at > 0)) return ""
    var d = new Date(at * 1000)
    var today = new Date()
    if (d.toDateString() === today.toDateString()) return Qt.formatTime(d, "h:mm AP")
    return Qt.formatDateTime(d, "MMM d, h:mm AP")
  }
  // On one agent's list (Agent details), how a chat it does not own came
  // to be there, as the list said before M18.
  function relationOf(c) {
    if (view.scope !== "agent" || view.ownerOf(c) === view.scopeAgent) return ""
    if (view.has(c.participants, view.scopeAgent)) return " · passed to it"
    if (view.has(c.shared_with, view.scopeAgent)) return " · shared"
    return ""
  }
  function turnsOf(c) {
    var n = Number(c.count) || 0
    return n + (n === 1 ? " turn" : " turns")
  }

  // Asked for by the summon payload: {"page":"chats","chat":ID}.
  Connections {
    target: view.s
    enabled: view.followSummon
    function onOpenChatChanged() {
      if (view.s.openChat !== "" && view.s.openChat !== view.selected) view.open(view.s.openChat)
    }
  }
  Component.onCompleted: if (view.followSummon && view.s.openChat !== "") view.open(view.s.openChat)

  function open(id) {
    view.selected = id
    view.renaming = false
    deleteButton.disarm()
    view.note = ""
    if (view.followSummon && view.validId(id)) view.s.openChat = id
    if (view.validId(id)) chatFile.reload()
  }

  // --- search -----------------------------------------------------------------
  function search(text) {
    view.query = String(text || "")
    view.results = null
    view.searchNote = ""
    if (view.query.trim() === "") return
    if (searcher.running) { searcher.again = true; return }
    searcher.start(view.query)
  }
  Process {
    id: searcher
    property string asked: ""
    property bool again: false
    property bool launched: false
    property string pending: ""
    function start(q) {
      asked = q
      pending = q.replace(/[\r\n]+/g, " ") + "\n"
      launched = false
      command = ["agentvoice", "chats", "search", "--json"]
      running = true
    }
    stdinEnabled: true
    onStarted: { launched = true; write(pending); pending = "" }
    // A filter it could not read (phase M19): said, since leaving it out
    // widens the list.
    stderr: StdioCollector {
      onStreamFinished: if (searcher.asked === view.query && text.trim() !== "")
        view.searchNote = text.trim().replace(/^left out: /, "Left out: ")
    }
    stdout: StdioCollector {
      onStreamFinished: {
        if (searcher.asked !== view.query) return
        try {
          var hits = JSON.parse(text)
          var map = {}
          for (var i = 0; i < hits.length; i++)
            if (hits[i] && view.validId(hits[i].id)) map[hits[i].id] = Number(hits[i].score) || 0
          view.results = map
        } catch (e) {
          view.searchNote = "The search could not be read, so only titles and last lines are matched."
        }
      }
    }
    onRunningChanged: if (!running) {
      if (!launched)
        view.searchNote = "agentvoice could not be started, so only titles and last lines are matched."
      if (again) { again = false; if (view.query.trim() !== "") start(view.query) }
    }
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
      // Append in place to preserve scroll, unless the daemon dropped old turns.
      var firstChanged = chatModel.count > 0 && ex.length > 0 &&
                         chatModel.get(0).at !== (Number((ex[0] || {}).at) || 0)
      if (chatModel.count > ex.length || chatList.chatId !== d.id || firstChanged) {
        chatModel.clear()
        chatList.chatId = d.id
      }
      for (var i = chatModel.count; i < ex.length; i++) {
        var e = ex[i] || {}
        chatModel.append({
          at: Number(e.at) || 0,
          speakerId: String(e.agent_id || ""),
          speakerLabel: String(e.agent_label || ""),
          kind: String(e.kind || ""),
          passedFrom: String(e["for"] || ""),
          asked: String(e.asked || ""),
          askedLabel: String(e.asked_label || ""),
          transcript: String(e.transcript || ""),
          reply: String(e.reply || ""),
          thought: String(e.thinking || ""),
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
    property string input: ""
    stdinEnabled: true
    onStarted: if (input !== "") { write(input); input = "" }
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
  function run(verb, args, input) {
    if (action.running) return false
    view.note = ""
    view.pendingVerb = verb
    action.input = input || ""
    action.command = ["agentvoice", "chats", verb].concat(args)
    action.running = true
    return true
  }
  // The new title on stdin, one line (phase M18): what was typed is not put
  // in a command line every account can read.
  function rename(id, title) {
    return view.run("rename", [id], String(title).replace(/[\r\n]+/g, " ") + "\n")
  }

  function continueChat() {
    var c = view.chat
    if (!run("continue", [c.id])) return
    var program = String(c.backend || "")
    view.note = program === "claude"
                ? "Your next request to " + view.agentName(c) + " picks this conversation up where it left off."
                : "Your next request to " + view.agentName(c) + " continues this chat. " +
                  (program !== "" ? s.programLabel(program) : "This program") + " cannot resume a " +
                  "conversation, so the chat's words go with that request, which costs tokens."
  }

  component SendButton: Button {
    text: "Send to another agent"
    bordered: true
    focusable: true
    enabled: view.s.serviceActive
    tooltipText: view.s.serviceActive ? "" : "The service is not running"
    fontFamily: view.s.fontFamily
    foreground: enabled ? view.s.foreground : view.s.dim
    width: Math.min(implicitWidth, parent.width)
  }

  // --- the list ---------------------------------------------------------------
  Column {
    id: side
    // Narrow: the list alone until a chat is opened, then the chat alone
    // with a way back, rather than two columns too thin to read.
    visible: !view.narrow || !(view.sessionOpen || view.savedChatOpen)
    width: view.narrow ? view.width : Math.min(Style.space(280), view.width * 0.34)
    height: parent.height
    spacing: Style.space(8)

    SearchField {
      id: searchBox
      width: parent.width
      placeholder: view.scope === "agent" ? "Search these chats" : "Search chats, or agent:Theo after:7d"
      filters: view.filterChips
      active: [view.agentFilter]
      foreground: view.s.foreground
      accent: view.s.accent
      fontFamily: view.s.fontFamily
      onSearched: function(t) { view.search(t) }
      onFilterToggled: function(id, on) { view.agentFilter = on ? id : "all" }
    }
    Text {
      visible: view.searchNote !== ""
      width: parent.width
      wrapMode: Text.WordWrap
      text: view.searchNote
      textFormat: Text.PlainText
      color: view.s.dim
      font.family: view.s.fontFamily
      font.pixelSize: Style.font.caption
    }

    Rectangle {
      visible: view.showSession
      width: parent.width
      height: sessionRow.implicitHeight + Style.space(12)
      radius: Style.cornerRadius
      color: view.sessionOpen ? Qt.rgba(view.s.foreground.r, view.s.foreground.g, view.s.foreground.b, 0.12)
                              : "transparent"
      border.width: activeFocus ? 1 : 0
      border.color: view.s.accent
      activeFocusOnTab: true
      Keys.onReturnPressed: view.open("session")
      Keys.onSpacePressed: view.open("session")
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
      visible: view.rows.length > 0
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
          id: chatCell
          visible: !row.isHeader
          anchors.fill: parent
          radius: Style.cornerRadius
          color: view.selected === row.c.id
                 ? Qt.rgba(view.s.foreground.r, view.s.foreground.g, view.s.foreground.b, 0.12)
                 : rowMouse.containsMouse
                   ? Qt.rgba(view.s.foreground.r, view.s.foreground.g, view.s.foreground.b, 0.05)
                   : "transparent"
          border.width: chatCell.activeFocus ? 1 : 0
          border.color: view.s.accent
          activeFocusOnTab: !row.isHeader
          Keys.onReturnPressed: view.open(row.c.id)
          Keys.onSpacePressed: view.open(row.c.id)
          // The owner's colour, down the left edge, as in the chat itself.
          Rectangle {
            x: Style.space(2)
            anchors.verticalCenter: parent.verticalCenter
            width: Style.space(3)
            height: parent.height - Style.space(12)
            radius: width / 2
            color: view.s.agentTint(view.ownerOf(row.c))
          }
          Column {
            id: chatRow
            anchors.verticalCenter: parent.verticalCenter
            x: Style.space(10)
            width: parent.width - Style.space(18)
            spacing: Style.space(1)
            Text {
              width: parent.width
              elide: Text.ElideRight
              text: (row.c.pinned === true ? "\u{f0403} " : "") + String(row.c.title || "Untitled chat")
              textFormat: Text.PlainText
              color: view.s.foreground
              font.family: view.s.fontFamily
              font.pixelSize: Style.font.body
              font.bold: view.selected === row.c.id
            }
            Text {
              width: parent.width
              elide: Text.ElideRight
              text: view.peopleOf(row.c) + view.relationOf(row.c) + " · " + view.whenOf(row.c.updated)
                    + " · " + view.turnsOf(row.c)
                    + (view.durationOf(row.c) !== "" ? " · " + view.durationOf(row.c) : "")
                    + (view.inUseByAnyone(row.c) ? " · in use" : "")
              textFormat: Text.PlainText
              color: view.inUseByAnyone(row.c) ? view.s.accent : view.s.dim
              font.family: view.s.fontFamily
              font.pixelSize: Style.font.caption
            }
            // Its summary (phase M19), written by its own agent once it
            // went quiet; until then, the last thing said.
            Text {
              width: parent.width
              visible: text !== ""
              elide: Text.ElideRight
              text: String(row.c.summary || row.c.preview || "").replace(/\s+/g, " ")
              textFormat: Text.PlainText
              color: Qt.rgba(view.s.foreground.r, view.s.foreground.g, view.s.foreground.b, 0.45)
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
      text: !view.s.saveChats && (view.index.chats || []).length === 0
            ? "Saving chats is off, so nothing is kept once a conversation ends."
            : view.query.trim() !== "" ? "No saved chat matches “" + view.query.trim() + "”."
            : view.agentFilter !== "all" ? "No saved chat matches this filter."
            : view.scope === "multi" || view.agentFilter === "multi"
              ? "No conversations with more than one agent yet. Pass a chat to another agent, or share it."
            : view.scope === "agent" ? "No saved chats with " + (view.currentAgentName(view.scopeAgent) || "this agent") + " yet."
            : "No saved chats yet. Each conversation is saved here as it happens."
      textFormat: Text.PlainText
      color: view.s.dim
      font.family: view.s.fontFamily
      font.pixelSize: Style.font.caption
    }
  }

  // --- the open chat ----------------------------------------------------------
  Item {
    id: main
    visible: !view.narrow || view.sessionOpen || view.savedChatOpen
    anchors.left: view.narrow ? parent.left : side.right
    anchors.leftMargin: view.narrow ? 0 : Style.space(16)
    anchors.right: parent.right
    height: parent.height

    Button {
      id: back
      visible: view.narrow
      text: "← All chats"
      bordered: true
      focusable: true
      fontFamily: view.s.fontFamily
      foreground: view.s.foreground
      onClicked: view.selected = ""
    }

    Text {
      visible: !view.sessionOpen && !view.savedChatOpen
      anchors.centerIn: parent
      width: Math.min(parent.width, Style.space(320))
      horizontalAlignment: Text.AlignHCenter
      wrapMode: Text.WordWrap
      text: view.chatRowCount > 0 ? "Pick a chat on the left to read it." : ""
      color: view.s.dim
      font.family: view.s.fontFamily
      font.pixelSize: Style.font.body
    }

    // This session: the same rows the plain view shows.
    ListView {
      id: sessionList
      visible: view.sessionOpen
      anchors.top: view.narrow ? back.bottom : parent.top
      anchors.topMargin: view.narrow ? Style.spacing.md : 0
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.bottom: sessionFooter.top
      anchors.bottomMargin: Style.spacing.md
      clip: true
      spacing: Style.spacing.xl
      model: view.showSession ? view.s.historyRows : null
      boundsBehavior: Flickable.StopAtBounds
      QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }
      // At the end while you are at the end, so a turn taken with the page
      // open appears without scrolling; left alone once you have scrolled
      // back to read.
      property bool following: true
      onMovementEnded: following = atYEnd
      onCountChanged: if (following) Qt.callLater(sessionList.positionViewAtEnd)
      onVisibleChanged: if (visible) { following = true; Qt.callLater(sessionList.positionViewAtEnd) }
      delegate: ExchangeItem {
        required property int index
        required property real at
        required property string agent
        required property string agentId
        required property string transcript
        required property string reply
        required property string thought
        required property string failed
        required property bool stopped
        required property bool fresh
        required property int latency
        width: ListView.view ? ListView.view.width - Style.space(10) : 0
        when: view.s.timeOf(at)
        who: agent
        tint: view.s.agentTint(agentId)
        latencyMs: latency
        heard: transcript
        answer: reply
        thinking: thought
        failure: failed
        wasStopped: stopped
        startsNew: fresh && index > 0
        foreground: view.s.foreground
        background: view.s.background
        accent: view.s.accent
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
      text: view.s.keepHistory ? "Nothing yet this session. Each exchange appears here as it ends."
                               : "Keeping this session's conversation is off (above, on this page)."
      color: view.s.dim
      font.family: view.s.fontFamily
      font.pixelSize: Style.font.body
    }
    Column {
      id: sessionFooter
      visible: view.sessionOpen
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.bottom: parent.bottom
      spacing: Style.space(6)
      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        text: "In memory only, gone at logout. Saved chats are kept separately. Drag across text to copy it."
        color: view.s.dim
        font.family: view.s.fontFamily
        font.pixelSize: Style.font.caption
      }
      Flow {
        width: parent.width
        layoutDirection: Qt.RightToLeft
        spacing: Style.space(6)
        DangerButton {
          visible: view.s.historyRows.count > 0
          text: "Clear"
          question: "Clear this session's conversation?"
          confirmText: "Clear"
          foreground: view.s.foreground
          urgent: view.s.urgent
          fontFamily: view.s.fontFamily
          onConfirmed: view.s.clearSession()
        }
        SendButton {
          visible: view.s.historyRows.count > 0
          // The chat the daemon would pass (the source's current one), so
          // the sheet previews what goes, not this session's memory.
          onClicked: view.s.openSendSheet(view.sessionSpeaker(), view.currentOf(view.sessionSpeaker()))
        }
      }
    }

    // A saved chat.
    Column {
      id: chatHead
      visible: view.savedChatOpen
      anchors.top: view.narrow ? back.bottom : parent.top
      anchors.topMargin: view.narrow ? Style.spacing.md : 0
      width: parent.width
      spacing: Style.space(6)

      Text {
        visible: !view.renaming
        width: parent.width
        wrapMode: Text.WordWrap
        text: view.openTitle
        textFormat: Text.PlainText
        color: view.s.foreground
        font.family: view.s.fontFamily
        font.pixelSize: Style.font.subtitle
        font.bold: true
      }
      // Phase M19: the one-line summary its agent wrote, and whose words
      // the name is -- written by the agent, not typed by you.
      Text {
        visible: !view.renaming && text !== ""
        width: parent.width
        wrapMode: Text.WordWrap
        text: view.openSummary
        textFormat: Text.PlainText
        color: view.s.foreground
        font.family: view.s.fontFamily
        font.pixelSize: Style.font.caption
      }
      TextField {
        id: renameField
        visible: view.renaming
        width: parent.width
        foreground: view.s.foreground
        font.family: view.s.fontFamily
        onAccepted: {
          var t = text.trim()
          if (t !== "" && t !== view.openTitle) view.rename(view.chat.id, t)
          view.renaming = false
        }
        Keys.onEscapePressed: view.renaming = false
        // Inside the field: qmllint cannot see the base type's `text` from
        // outside it (Omarchy's TextField wraps QtQuick.Controls').
        function begin(title) {
          text = title
          forceActiveFocus()
          selectAll()
        }
      }
      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        text: view.peopleOf(view.chat) + " · " + (view.chat.backend ? view.s.programLabel(view.chat.backend) : "agent")
              + " · started " + view.whenOf(view.chat.started)
              + " · " + view.turnsOf({ count: (view.chat.exchanges || []).length })
              + (view.durationOf(view.chat) !== "" ? " · " + view.durationOf(view.chat) : "")
              + (view.openMeta.auto === true ? " · named by " + view.agentName(view.chat) : "")
              + (view.inUseByAnyone(view.chat) ? " · in use now" : "")
              // What was typed there is in the agent's own session, not here.
              + (Number(view.chat.terminal || 0) > 0
                 ? " · went on in a terminal " + view.whenOf(view.chat.terminal) : "")
        textFormat: Text.PlainText
        color: view.s.dim
        font.family: view.s.fontFamily
        font.pixelSize: Style.font.caption
      }
      // What to do with it, in three rows: carrying it on, passing it on,
      // then the smaller things done to the chat itself.
      Flow {
        width: parent.width
        spacing: Style.space(6)
        Button {
          text: "Continue"
          iconText: "\u{f040a}"
          bordered: true
          focusable: true
          enabled: view.s.serviceActive && !view.inUse(view.chat)
          tooltipText: view.s.serviceActive ? "Make this " + view.agentName(view.chat) + "'s current chat"
                                            : "The service is not running"
          fontFamily: view.s.fontFamily
          onClicked: view.continueChat()
        }
        Repeater {
          model: view.continueAgents
          Button {
            required property string modelData
            readonly property string agentName: view.currentAgentName(modelData) || modelData
            text: "Continue with " + agentName
            width: Math.min(implicitWidth, parent.width)
            bordered: true
            focusable: true
            enabled: view.s.serviceActive
            tooltipText: view.s.serviceActive ? "Make this " + agentName + "'s current chat"
                                              : "The service is not running"
            fontFamily: view.s.fontFamily
            foreground: enabled ? view.s.foreground : view.s.dim
            onClicked: view.run("continue", [view.chat.id, modelData])
          }
        }
        Button {
          text: "New chat"
          bordered: true
          focusable: true
          enabled: view.s.serviceActive
          tooltipText: view.s.serviceActive ? view.agentName(view.chat) + "'s next request begins a new conversation; this one stays here"
                                            : "The service is not running"
          fontFamily: view.s.fontFamily
          foreground: enabled ? view.s.foreground : view.s.dim
          onClicked: view.run("new", [view.ownerId])
        }
      }
      Flow {
        width: parent.width
        spacing: Style.space(6)
        SendButton {
          onClicked: view.s.openSendSheet(view.lastSpeaker(), view.chat.id)
        }
        Dropdown {
          visible: view.shareOptions.length > 0
          width: Math.min(Style.space(150), parent.width)
          showLabel: false
          fontFamily: view.s.fontFamily
          foreground: view.s.foreground
          options: view.shareOptions
          value: "Share with…"
          onChanged: function(agentId) {
            value = "Share with…"
            view.run("share", [view.chat.id, agentId])
          }
        }
      }
      Flow {
        width: parent.width
        spacing: Style.space(6)
        Button {
          text: "Rename"
          bordered: true
          focusable: true
          fontFamily: view.s.fontFamily
          onClicked: {
            view.renaming = true
            renameField.begin(view.openTitle)
          }
        }
        Button {
          text: view.chat.pinned === true ? "Unpin" : "Pin"
          bordered: true
          focusable: true
          fontFamily: view.s.fontFamily
          onClicked: view.run(view.chat.pinned === true ? "unpin" : "pin", [view.chat.id])
        }
        Button {
          text: "Export"
          tooltipText: "Write it as Markdown into Documents"
          bordered: true
          focusable: true
          fontFamily: view.s.fontFamily
          onClicked: view.run("export", [view.chat.id])
        }
        DangerButton {
          id: deleteButton
          text: "Delete"
          question: "Really delete this chat?"
          confirmText: "Delete"
          foreground: view.s.foreground
          urgent: view.s.urgent
          fontFamily: view.s.fontFamily
          onConfirmed: {
            view.run("delete", [view.chat.id])
            view.open(view.showSession ? "session" : "")
          }
        }
      }
      Flow {
        visible: view.sharedAgents.length > 0
        width: parent.width
        spacing: Style.space(6)
        Text {
          width: Math.min(implicitWidth, parent.width)
          wrapMode: Text.Wrap
          text: "Shared with: " + view.sharedAgents.map(function(id) {
            return view.currentAgentName(id) || id
          }).join(", ")
          textFormat: Text.PlainText
          color: view.s.dim
          font.family: view.s.fontFamily
          font.pixelSize: Style.font.caption
        }
        Dropdown {
          width: Math.min(implicitWidth, parent.width)
          showLabel: false
          fontFamily: view.s.fontFamily
          foreground: view.s.foreground
          options: view.unshareOptions
          value: "Stop sharing with…"
          onChanged: function(agentId) {
            value = "Stop sharing with…"
            view.run("unshare", [view.chat.id, agentId])
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

    ListView {
      id: chatList
      property string chatId: ""
      visible: view.savedChatOpen
      anchors.top: chatHead.bottom
      anchors.topMargin: Style.spacing.md
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.bottom: parent.bottom
      clip: true
      spacing: Style.spacing.xl
      model: chatModel
      boundsBehavior: Flickable.StopAtBounds
      QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }
      delegate: ExchangeItem {
        required property real at
        required property string speakerId
        required property string speakerLabel
        required property string kind
        required property string passedFrom
        required property string asked
        required property string askedLabel
        required property string transcript
        required property string reply
        required property string thought
        required property string failed
        required property bool stopped
        readonly property string speaker: speakerId || view.ownerId
        width: ListView.view ? ListView.view.width - Style.space(10) : 0
        when: view.whenOf(at)
        who: view.exchangeSpeaker(speakerId, speakerLabel, kind, passedFrom)
        tint: view.s.agentTint(speaker)
        // A question one agent asked another (Phase 16): folded to one line.
        aside: kind === "aside"
               ? view.exchangeSpeaker(speakerId, speakerLabel, "", "") + " asked "
                 + (askedLabel || view.currentAgentName(asked) || asked || "another agent")
               : ""
        askedName: askedLabel || view.currentAgentName(asked) || asked
        askedTint: view.s.agentTint(asked)
        heard: transcript
        answer: reply
        thinking: thought
        failure: failed
        wasStopped: stopped
        foreground: view.s.foreground
        background: view.s.background
        accent: view.s.accent
        urgent: view.s.urgent
        fontFamily: view.s.fontFamily
      }
    }
  }
}
