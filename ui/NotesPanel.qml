import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// One notes folder (merged plan, Phase 14): an agent's own, or the communal
// one. A list of the notes (name, who wrote it last and when, the lock),
// a plain-text editor, each note's history with View and Restore, the
// person's lock, and Open folder. Other files dropped into the folder show
// as entries that open with xdg-open. That is the whole of the "file
// manager".
//
// Everything goes through `agentvoice agents notes TARGET …`, which owns
// the folder: it keeps every replaced version, refuses a save based on a
// rev that has moved on, and writes one audit line with no text in it.
// The text goes over stdin as one JSON line, never argv.
//
// What the person writes here is theirs: a lock and an agent's "read only"
// bind the agents, not the person.
//
//   NotesPanel {
//     target: "sora"             // "main", an agent's id, or "communal"
//     owner: "Sora"              // whose notes, in words; "" for communal
//     whyNot: ""                 // why its program cannot use them, or ""
//   }
Column {
  id: np

  property string target: ""
  property string owner: ""
  property string whyNot: ""
  // Polls only while drawn: a hand edit or an agent's write shows within
  // seconds, as the folder editors do.
  property bool active: visible
  property color foreground: Commons.Color.foreground
  property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  readonly property bool communal: target === "communal"
  property var listing: null
  property string listError: ""

  // The note open in the editor.
  property string openName: ""
  property bool creating: false
  property string noteText: ""
  property int noteRev: -1
  property bool noteLoaded: false
  property string noteNote: ""
  property bool justSaved: false
  // A save refused because the note moved on: the rev it is at now, so
  // "Keep mine" can replace exactly that version. -1 when there is none.
  property int conflictRev: -1
  // Text typed and not saved (refused or failed); nothing reloads over it.
  property string held: ""
  property bool holding: false
  // History of the open note, and the version being looked at.
  property bool showHistory: false
  property var versions: []
  property string viewing: ""
  property string viewingText: ""
  property string actionNote: ""

  readonly property var notesList: listing ? listing.notes : []
  readonly property var otherFiles: listing ? listing.files : []
  readonly property var openEntry: {
    for (var i = 0; i < notesList.length; i++)
      if (notesList[i].name === openName) return notesList[i]
    return null
  }
  // The new note's name, from the field (made afresh for every New note).
  // `var`, so it is read as whatever the Loader made (Omarchy's TextField).
  readonly property var nameInput: nameLoader.item
  readonly property string newName: nameInput ? String(nameInput.text).trim() : ""
  readonly property bool validName: /^[a-z0-9][a-z0-9-]{0,47}$/.test(newName)
  // Bumped whenever the editor is given another note (or none), so a read
  // or a save started for the previous one is ignored when it ends.
  property int session: 0
  // An edit committed while a save was still running: saved next, on the
  // rev that save returns, rather than dropped.
  property string queued: ""
  property bool hasQueued: false

  width: parent ? parent.width : 400
  spacing: Style.space(10)

  function when(at) {
    return at > 0 ? Qt.formatDateTime(new Date(at * 1000), "MMM d, h:mm AP") : ""
  }
  function cli(args) { return ["agentvoice", "agents", "notes", np.target].concat(args) }
  function err(t) { return String(t).trim().replace(/^agentvoice agents: /, "").split("\n").pop() }

  function list() {
    if (target === "") return
    if (lister.running) { lister.again = true; return }
    lister.forTarget = target
    lister.command = cli(["list", "--json"])
    lister.running = true
  }
  // The editor, emptied for another note: nothing of the previous note's
  // text or rev can be saved over this one (Phase 14 review).
  function clearEditor() {
    session++
    np.forceActiveFocus()               // out of the box, so a read can land
    noteText = ""; noteRev = -1; noteLoaded = false
    holding = false; held = ""; conflictRev = -1; noteNote = ""; justSaved = false
    hasQueued = false; queued = ""
    showHistory = false; versions = []; viewing = ""; viewingText = ""
    box.reset("")
  }
  function open(name) {
    // Unsaved text goes first; the click that would have moved away is
    // then repeated by the person once it has saved.
    if (box.dirty) { box.commit(); return }
    if (holding) { noteNote = "Save or reload this note first; what you typed is not saved."; return }
    clearEditor()
    creating = false
    openName = name
    read()
  }
  function startNew() {
    if (box.dirty) { box.commit(); return }
    if (holding) { noteNote = "Save or reload this note first; what you typed is not saved."; return }
    clearEditor()
    openName = ""
    creating = true
    noteLoaded = true
    Qt.callLater(function() { if (np.nameInput) np.nameInput.forceActiveFocus() })
  }
  function close() {
    if (box.dirty) { box.commit(); return }
    clearEditor()
    openName = ""; creating = false
  }
  function read() {
    if (openName === "") return
    if (reader.running) { reader.again = true; return }
    reader.forTarget = target
    reader.forName = openName
    reader.session = session
    reader.command = cli(["show", openName, "--json"])
    reader.running = true
  }
  function save(t) {
    var name = creating ? newName : openName
    // Refusals before anything is sent leave the box's baseline alone, so
    // the same text is saved by the next Ctrl+S or Save once fixed.
    if (name === "") { noteNote = "Give the note a name first, then Save."; return }
    if (!/^[a-z0-9][a-z0-9-]{0,47}$/.test(name)) {
      noteNote = "A note's name is 1 to 48 characters of a–z, 0–9 and -, starting with a letter or digit."
      return
    }
    if (!creating && !noteLoaded) { noteNote = "Still reading the note; save again in a moment."; return }
    if (Array.from(t).length > 20000) {
      noteNote = "Not saved: " + Array.from(t).length + " characters, and a note holds at most 20000."
      return
    }
    if (writer.running) {
      queued = t; hasQueued = true
      held = t; holding = true
      return
    }
    held = t; holding = true; noteNote = ""; justSaved = false
    var args = ["write", name, "--line", "--json"]
    // A new note has no rev: the CLI then refuses if one of that name exists.
    if (!creating && noteRev >= 0) args = args.concat(["--base", String(noteRev)])
    writer.forTarget = target
    writer.forName = name
    writer.session = session
    writer.creating = creating
    writer.text = t
    writer.answered = false
    writer.pending = JSON.stringify(t) + "\n"
    writer.command = cli(args)
    writer.running = true
  }
  function keepMine() {
    if (conflictRev < 0) return
    if (creating) { openName = newName; creating = false }
    noteRev = conflictRev
    noteLoaded = true
    save(box.text)
  }
  function reloadTheirs() {
    var name = creating ? newName : openName
    clearEditor()
    creating = false
    openName = name
    read()
  }
  function setLock(name, on) {
    if (locker.running) return
    actionNote = ""
    locker.command = cli([on ? "lock" : "unlock", name])
    locker.running = true
  }
  function loadHistory() {
    if (openName === "" || historian.running) return
    historian.forName = openName
    historian.session = session
    historian.command = cli(["history", openName, "--json"])
    historian.running = true
  }
  function view(version) {
    if (versioner.running) return
    viewing = version
    viewingText = ""
    versioner.session = session
    versioner.version = version
    versioner.command = cli(["version", openName, version, "--json"])
    versioner.running = true
  }
  function restore(version) {
    if (restorer.running || noteRev < 0) return
    actionNote = ""
    restorer.session = session
    restorer.command = cli(["restore", openName, version, "--base", String(noteRev), "--json"])
    restorer.running = true
  }
  function openFolder() {
    folderer.command = cli(["folder"])
    folderer.running = true
  }
  function openFile(name) {
    if (!listing) return
    opener.command = ["xdg-open", listing.folder + "/" + name]
    opener.running = true
  }

  onTargetChanged: { listing = null; listError = ""; close(); list() }
  onActiveChanged: if (active) list()
  Component.onCompleted: list()

  Timer {
    interval: 4000
    repeat: true
    running: np.active && np.target !== ""
    onTriggered: np.list()
  }

  Process {
    id: lister
    property string forTarget: ""
    property bool again: false
    onRunningChanged: if (!running && again) { again = false; Qt.callLater(np.list) }
    stdout: StdioCollector {
      onStreamFinished: {
        if (lister.forTarget !== np.target) return
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        if (!d || !Array.isArray(d.notes)) return
        np.listError = ""
        np.listing = d
        // The open note changed on disk (an agent wrote it, or a hand
        // edit): read it again, unless something typed would be lost.
        var e = np.openEntry
        if (e && np.noteLoaded && e.rev !== np.noteRev && !box.editing && !np.holding)
          np.read()
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        if (t !== "" && lister.forTarget === np.target) np.listError = np.err(t)
      }
    }
  }

  Process {
    id: reader
    property string forTarget: ""
    property string forName: ""
    property bool again: false
    onRunningChanged: if (!running && again) { again = false; Qt.callLater(np.read) }
    property int session: 0
    stdout: StdioCollector {
      onStreamFinished: {
        if (reader.session !== np.session || reader.forTarget !== np.target ||
            reader.forName !== np.openName) return
        if (box.editing || np.holding) return
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        if (!d || typeof d.text !== "string") return
        np.noteText = d.text
        np.noteRev = d.rev
        np.noteLoaded = true
        box.reset(d.text)
        if (np.showHistory) np.loadHistory()
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        if (t !== "" && reader.forTarget === np.target) np.noteNote = np.err(t)
      }
    }
  }

  Process {
    id: writer
    property string pending: ""
    property string forTarget: ""
    property string forName: ""
    property string text: ""
    property bool answered: false
    property int session: 0
    property bool creating: false
    stdinEnabled: true
    onStarted: { write(writer.pending); writer.pending = "" }
    // `running` going false, not onExited: a spawn that never started emits
    // no exit, and a save that did nothing must say so.
    onRunningChanged: if (!running) writeCheck.restart()
    stdout: StdioCollector {
      onStreamFinished: {
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        if (!d || typeof d.rev !== "number") return
        writer.answered = true
        if (writer.session !== np.session || writer.forTarget !== np.target) return
        np.noteRev = d.rev
        np.noteText = writer.text
        np.noteLoaded = true
        if (writer.creating) { np.openName = writer.forName; np.creating = false }
        np.conflictRev = -1; np.noteNote = ""
        np.list()
        if (np.hasQueued) {
          // Typed and committed while this save ran: saved now, on its rev.
          var next = np.queued
          np.hasQueued = false; np.queued = ""
          Qt.callLater(function() { np.save(next) })
          return
        }
        np.holding = false; np.held = ""
        np.justSaved = true
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        if (t === "") return
        writer.answered = true
        if (writer.session !== np.session || writer.forTarget !== np.target) return
        // A queued edit is the newest text: it is what "Keep mine" saves.
        if (np.hasQueued) { np.held = np.queued; np.hasQueued = false; np.queued = "" }
        var m = t.match(/current rev (\d+)/)
        if (t.indexOf("conflict:") === 0 && m) {
          np.conflictRev = parseInt(m[1])
          np.noteNote = writer.creating
                        ? "A note called " + writer.forName + " already exists, so yours was not saved."
                        : "Changed since you opened it (by an agent, or by hand), so yours was not saved."
        } else {
          np.noteNote = "Not saved: " + np.err(t)
        }
      }
    }
  }
  Timer {
    id: writeCheck
    interval: 300
    onTriggered: if (!writer.answered && !writer.running) {
      writer.answered = true
      np.noteNote = "Not saved: the agentvoice command could not be run."
    }
  }

  Process {
    id: locker
    stderr: StdioCollector {
      onStreamFinished: { var t = String(text).trim(); if (t !== "") np.actionNote = "Not changed: " + np.err(t) }
    }
    onRunningChanged: if (!running) np.list()
  }
  Process {
    id: historian
    property string forName: ""
    property int session: 0
    stdout: StdioCollector {
      onStreamFinished: {
        if (historian.session !== np.session || historian.forName !== np.openName) return
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        if (Array.isArray(d)) np.versions = d
      }
    }
  }
  Process {
    id: versioner
    property int session: 0
    property string version: ""
    stdout: StdioCollector {
      onStreamFinished: {
        if (versioner.session !== np.session || versioner.version !== np.viewing) return
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        if (d && typeof d.text === "string") np.viewingText = d.text
      }
    }
  }
  Process {
    id: restorer
    property int session: 0
    property bool done: false
    onStarted: done = false
    stdout: StdioCollector {
      onStreamFinished: {
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        if (d && typeof d.rev === "number") { restorer.done = true; np.viewing = ""; np.actionNote = "Restored." }
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        if (t === "") return
        np.actionNote = t.indexOf("conflict:") === 0
                        ? "It changed since it was shown; look at it again first."
                        : "Not restored: " + np.err(t)
      }
    }
    // Only a restore that landed replaces the editor's text; a refused one
    // leaves whatever was typed where it is.
    onRunningChanged: if (!running) {
      np.list()
      if (restorer.done && restorer.session === np.session) { np.holding = false; np.held = ""; np.read() }
    }
  }
  Process {
    id: folderer
    stdout: StdioCollector {
      onStreamFinished: {
        var path = String(text).trim()
        if (path === "") return
        opener.command = ["xdg-open", path]
        opener.running = true
      }
    }
  }
  Process { id: opener }

  // --- what it says ---------------------------------------------------------------

  Text {
    width: parent.width
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: np.communal
          ? "Notes every agent here can read, and write unless it is set to read only on its Agents card. " +
            "A note is handed to an agent as information, never as an instruction."
          : np.owner + "'s own notes: what it writes down for itself. Other agents cannot reach them " +
            "through the notes tools. What it writes in the communal notes is on the Communal page."
    color: np.foreground
    font.family: np.fontFamily
    font.pixelSize: Style.font.bodySmall
  }
  Text {
    width: parent.width
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: "A lock, and “read only” on an agent's card, hold through the notes tools at every level. " +
          "An agent at “trust everything” also has a shell, and can change these files directly; " +
          "nothing stops that, but such a change shows here as last written by you."
    color: np.dim
    font.family: np.fontFamily
    font.pixelSize: Style.font.caption
  }
  Text {
    width: parent.width
    visible: np.whyNot !== ""
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: np.whyNot + " " + np.owner + " cannot read or write these; you still can, here."
    color: Commons.Color.urgent
    font.family: np.fontFamily
    font.pixelSize: Style.font.bodySmall
  }
  Text {
    width: parent.width
    visible: np.listError !== "" || (np.listing !== null && np.listing.problem !== "")
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: np.listError !== "" ? "Could not read the notes: " + np.listError : (np.listing ? np.listing.problem : "")
    color: Commons.Color.urgent
    font.family: np.fontFamily
    font.pixelSize: Style.font.bodySmall
  }

  Flow {
    width: parent.width
    spacing: Style.space(8)
    Button {
      text: "New note"
      bordered: true
      focusable: true
      foreground: np.foreground
      fontFamily: np.fontFamily
      onClicked: np.startNew()
    }
    Button {
      text: "Open folder"
      bordered: true
      focusable: true
      foreground: np.foreground
      fontFamily: np.fontFamily
      onClicked: np.openFolder()
    }
  }

  Text {
    width: parent.width
    visible: np.listing === null && np.listError === ""
    text: "Reading…"
    textFormat: Text.PlainText
    color: np.dim
    font.family: np.fontFamily
    font.pixelSize: Style.font.bodySmall
  }
  Text {
    width: parent.width
    visible: np.listing !== null && np.notesList.length === 0 && np.otherFiles.length === 0
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: "No notes yet. " + (np.communal ? "Any agent may start one" : np.owner + " starts one") +
          " when it has something worth keeping, or you can, with New note."
    color: np.dim
    font.family: np.fontFamily
    font.pixelSize: Style.font.bodySmall
  }

  // --- the list -------------------------------------------------------------------
  Repeater {
    model: np.notesList
    Item {
      id: row
      required property var modelData
      width: np.width
      height: rowText.implicitHeight + Style.space(10)
      Rectangle {
        anchors.fill: parent
        radius: Style.cornerRadius
        color: np.foreground
        opacity: row.modelData.name === np.openName ? 0.10 : (rowHover.hovered ? 0.05 : 0)
      }
      HoverHandler { id: rowHover; cursorShape: Qt.PointingHandCursor }
      TapHandler { onTapped: np.open(row.modelData.name) }
      Text {
        id: rowText
        anchors.left: parent.left
        anchors.right: lockButton.left
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: Style.space(6)
        anchors.rightMargin: Style.space(8)
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: (row.modelData.locked ? "🔒 " : "") + row.modelData.name + "  ·  " +
              (row.modelData.author_label || row.modelData.author) +
              (np.when(row.modelData.at) !== "" ? ", " + np.when(row.modelData.at) : "") +
              "  ·  " + row.modelData.chars + " characters" +
              (row.modelData.tainted ? "  ·  may contain text from web pages" : "") +
              (row.modelData.problem ? "  ·  " + row.modelData.problem : "")
        color: row.modelData.tainted || row.modelData.problem ? Commons.Color.urgent : np.foreground
        font.family: np.fontFamily
        font.pixelSize: Style.font.bodySmall
      }
      Button {
        id: lockButton
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        text: row.modelData.locked ? "Unlock" : "Lock"
        enabled: !(np.listing && np.listing.locked_all)
        focusable: true
        foreground: np.foreground
        fontFamily: np.fontFamily
        onClicked: np.setLock(row.modelData.name, !row.modelData.locked)
      }
    }
  }
  Text {
    width: parent.width
    visible: np.actionNote !== ""
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: np.actionNote
    color: Commons.Color.urgent
    font.family: np.fontFamily
    font.pixelSize: Style.font.bodySmall
  }

  Text {
    width: parent.width
    visible: np.otherFiles.length > 0
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: "Other files in this folder. Agents do not see them; click one to open it."
    color: np.dim
    font.family: np.fontFamily
    font.pixelSize: Style.font.caption
  }
  Repeater {
    model: np.otherFiles
    Button {
      required property var modelData
      text: modelData.name + (modelData.kind !== "file" ? "  (" + modelData.kind + ")" : "")
      focusable: true
      foreground: np.foreground
      fontFamily: np.fontFamily
      onClicked: np.openFile(modelData.name)
    }
  }

  // --- the open note --------------------------------------------------------------
  Column {
    width: parent.width
    spacing: Style.space(6)
    visible: np.openName !== "" || np.creating

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      visible: !np.creating
      text: np.openEntry
            ? np.openName + " · rev " + np.openEntry.rev + " · last written by " +
              (np.openEntry.author_label || np.openEntry.author) +
              (np.openEntry.locked ? " · locked: read-only for every agent" : "")
            : np.openName
      color: np.foreground
      font.family: np.fontFamily
      font.pixelSize: Style.font.body
    }
    // Made afresh for every New note, so it always starts empty.
    Loader {
      id: nameLoader
      active: np.creating
      visible: active
      width: Math.min(parent.width, Style.space(320))
      sourceComponent: TextField {
        placeholderText: "name, like shopping-list"
        foreground: np.foreground
        font.family: np.fontFamily
      }
    }
    Text {
      width: parent.width
      visible: np.creating && np.newName !== "" && !np.validName
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: "Lowercase letters, digits and -, up to 48, starting with a letter or digit."
      color: Commons.Color.urgent
      font.family: np.fontFamily
      font.pixelSize: Style.font.caption
    }
    InstructionsBox {
      id: box
      width: parent.width
      value: np.holding ? np.held : np.noteText
      maxLength: 20000
      cutOff: false
      minHeight: Style.space(140)
      editingHint: "Ctrl+S or click away saves"
      placeholder: np.creating ? "What the note says" : ""
      foreground: np.foreground
      fontFamily: np.fontFamily
      onCommitted: function(t) { np.save(t) }
      onEditingChanged: if (editing) np.justSaved = false
    }
    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      visible: text !== ""
      text: writer.running ? "Saving…"
            : reader.running && !np.noteLoaded ? "Reading…"
            : np.holding && np.noteNote === "" ? "Unsaved"
            : np.justSaved ? "Saved · agents read it from their next look"
            : ""
      color: np.dim
      font.family: np.fontFamily
      font.pixelSize: Style.font.bodySmall
    }
    Text {
      width: parent.width
      visible: np.noteNote !== ""
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: np.noteNote
      color: Commons.Color.urgent
      font.family: np.fontFamily
      font.pixelSize: Style.font.bodySmall
    }
    Flow {
      width: parent.width
      spacing: Style.space(8)
      Button {
        text: "Save"
        bordered: true
        focusable: true
        enabled: !writer.running
        foreground: np.foreground
        fontFamily: np.fontFamily
        onClicked: np.save(box.text.trim())
      }
      Button {
        visible: np.conflictRev >= 0
        text: "Keep mine"
        bordered: true
        focusable: true
        foreground: np.foreground
        fontFamily: np.fontFamily
        onClicked: np.keepMine()
      }
      Button {
        visible: np.conflictRev >= 0
        text: "Reload"
        bordered: true
        focusable: true
        foreground: np.foreground
        fontFamily: np.fontFamily
        onClicked: np.reloadTheirs()
      }
      Button {
        visible: !np.creating
        text: np.showHistory ? "Hide history" : "History"
        bordered: true
        focusable: true
        foreground: np.foreground
        fontFamily: np.fontFamily
        onClicked: { np.showHistory = !np.showHistory; if (np.showHistory) np.loadHistory() }
      }
      Button {
        // What it does to unsaved text, said on the button.
        text: np.holding ? "Discard and close" : "Close"
        bordered: true
        focusable: true
        foreground: np.foreground
        fontFamily: np.fontFamily
        onClicked: np.close()
      }
    }

    Column {
      width: parent.width
      spacing: Style.space(4)
      visible: np.showHistory && !np.creating
      Text {
        width: parent.width
        visible: np.versions.length === 0
        text: "No earlier versions."
        textFormat: Text.PlainText
        color: np.dim
        font.family: np.fontFamily
        font.pixelSize: Style.font.bodySmall
      }
      Repeater {
        model: np.versions
        Flow {
          required property var modelData
          width: np.width
          spacing: Style.space(8)
          Text {
            text: np.when(modelData.at) + " · " + modelData.who + " · " + modelData.chars + " characters"
            textFormat: Text.PlainText
            color: np.foreground
            font.family: np.fontFamily
            font.pixelSize: Style.font.bodySmall
          }
          Button {
            text: np.viewing === modelData.version ? "Viewing" : "View"
            focusable: true
            foreground: np.foreground
            fontFamily: np.fontFamily
            onClicked: np.view(modelData.version)
          }
          Button {
            text: "Restore"
            focusable: true
            enabled: !restorer.running
            foreground: np.foreground
            fontFamily: np.fontFamily
            onClicked: np.restore(modelData.version)
          }
        }
      }
      Text {
        width: parent.width
        visible: np.viewing !== ""
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: np.viewingText
        color: np.dim
        font.family: np.fontFamily
        font.pixelSize: Style.font.bodySmall
      }
      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: "Restoring saves the text it replaces as a version too, so it can be undone the same way."
        color: np.dim
        font.family: np.fontFamily
        font.pixelSize: Style.font.caption
      }
    }
  }
}
