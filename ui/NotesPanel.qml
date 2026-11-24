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
// Since M13 a note is a topic, shown as a card (its topic, its first line)
// in its owner's lane: this folder's lane first, then every other folder's
// from `agentvoice notes lanes`. A card is dragged to another lane to move
// it (Ctrl copies) or sent with its Move to…; NoteMover asks before it
// widens and offers Undo. Combine merges notes of this folder into one
// topic, and Earlier notes puts back one that was combined away or deleted.
// A card in another lane opens on its owner's own tab (openElsewhere).
//
//   NotesPanel {
//     target: "sora"             // "main", an agent's id, or "communal"
//     owner: "Sora"              // whose notes, in words; "" for communal
//     whyNot: ""                 // why its program cannot use them, or ""
//     onOpenElsewhere: function(id) { page.s.goTo("agentdetails", id, "notes") }
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

  // Phase M13: every notes folder as a lane, this one's first.
  property var lanesData: null
  property string moveNote: ""
  property bool combining: false
  // Names picked for Combine, in the order picked: the first is kept.
  property var picked: []
  property bool showGone: false
  // A card being dragged: a poll that rebuilt the cards now would drop the
  // drag out of the person's hand, so a new reading waits (and one that
  // changed nothing is never applied at all, which also keeps a card that
  // was unfolded unfolded).
  property bool dragActive: false
  signal openElsewhere(string laneId)

  readonly property string homeLabel: communal ? "Communal" : owner
  readonly property bool lockedAll: listing !== null && listing.locked_all === true
  readonly property var goneList: listing && Array.isArray(listing.gone) ? listing.gone : []
  readonly property var allLanes: lanesData && Array.isArray(lanesData.lanes) ? lanesData.lanes : []
  readonly property var otherLanes: allLanes.filter(function(l) { return l.id !== np.target })
  // Anything but a list tells the mover the quarantine cannot be read.
  readonly property var quarantinedIds: lanesData && lanesData.quarantine_readable === false ? null
                                        : allLanes.filter(function(l) { return l.quarantined === true })
                                                  .map(function(l) { return l.id })
  readonly property var laneList: {
    var out = [{ id: np.target, label: np.homeLabel }]
    np.otherLanes.forEach(function(l) {
      out.push({ id: l.id, label: l.label,
                 reason: l.id === "communal" ? "Every agent can read it; asks first" : "" })
    })
    return out
  }
  readonly property var laneLabels: {
    var out = {}
    np.laneList.forEach(function(l) { out[l.id] = l.label })
    return out
  }
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
  property int queuedSession: -1
  // The folder the open note belongs to: a save goes there or nowhere, so a
  // target change (an agent removed) can never send it to another folder.
  property string editTarget: ""
  // The name a refused save was for: what Keep mine and Reload act on, not
  // whatever the name field says by the time they are clicked.
  property string conflictName: ""

  width: parent ? parent.width : 400
  spacing: Style.space(10)

  function when(at) {
    return at > 0 ? Qt.formatDateTime(new Date(at * 1000), "MMM d, h:mm AP") : ""
  }
  function cli(args) { return ["agentvoice", "agents", "notes", np.target].concat(args) }
  function refresh() { list(); lanes() }
  function lanes() {
    if (lanesRunner.running) { lanesRunner.again = true; return }
    lanesRunner.command = ["agentvoice", "notes", "lanes", "--json"]
    lanesRunner.running = true
  }

  // --- M13: cards, moves and Combine -----------------------------------------------
  function laneById(id) {
    for (var i = 0; i < allLanes.length; i++) if (allLanes[i].id === id) return allLanes[i]
    return null
  }
  function laneNotes(id) {
    if (id === target) return notesList
    var l = laneById(id)
    return l && Array.isArray(l.notes) ? l.notes : []
  }
  function laneLocked(id) {
    if (id === target) return lockedAll
    var l = laneById(id)
    return l !== null && l.locked_all === true
  }
  function laneLabel(id) { return laneLabels[id] !== undefined ? laneLabels[id] : id }
  function notePayload(x, laneId) {
    return { kind: "note", name: x.name, label: x.label || x.name, from: laneId,
             tainted: x.tainted === true, problem: x.problem || "", versions: x.versions || 0 }
  }
  function noteRefusal(p, to) {
    if (!p || p.kind !== "note" || !p.name) return "Not a note."
    if (p.problem !== "") return "It cannot be moved: " + p.problem
    if (laneLocked(p.from)) return laneLabel(p.from) + "'s notes record cannot be read, so nothing is moved out of it."
    if (laneLocked(to)) return laneLabel(to) + "'s notes record cannot be read, so nothing is moved into it."
    if (laneNotes(to).some(function(x) { return x.name === p.name }))
      return laneLabel(to) + " already has a note called " + p.name + ". Combine or rename one first."
    return ""
  }
  // Every way a card moves -- a drop on a lane, its Move to… -- ends here.
  function noteDropped(p, copy, from, to) {
    var why = noteRefusal(p, to)
    if (why !== "") { moveNote = why; return }
    moveNote = ""
    noteMover.request(p.name, from, to, copy, p.tainted, p.label, p.versions)
  }
  function noteStatus(x) {
    return "rev " + x.rev + " · " + (x.author_label || x.author) +
           (when(x.at) !== "" ? ", " + when(x.at) : "") + " · " + x.chars + " characters" +
           (x.tainted ? " · may contain text from web pages" : "") +
           (x.problem ? " · " + x.problem : "")
  }
  function noteDetails(x) {
    var out = [{ label: "Name", value: x.name },
               { label: "Saved versions", value: String(x.versions || 0) + " (they move with it)" }]
    if (x.locked) out.push({ label: "Locked", value: "read-only for every agent" })
    if (x.tainted) out.push({ label: "Taint", value: "may contain text from web pages", urgent: true })
    return out
  }
  function togglePick(name) {
    var c = picked.slice()
    var i = c.indexOf(name)
    if (i >= 0) c.splice(i, 1); else c.push(name)
    picked = c
  }
  function startCombine() { combining = !combining; picked = []; moveNote = "" }
  function askCombine() {
    var parts = []
    picked.forEach(function(n) {
      var e = notesList.filter(function(x) { return x.name === n })[0]
      if (e) parts.push({ name: e.name, label: e.label || e.name, tainted: e.tainted === true,
                          locked: e.locked === true })
    })
    noteMover.askCombine(target, parts)
  }
  function restoreGone(g) {
    if (goneRestorer.running) return
    actionNote = ""
    goneRestorer.command = cli(["restore", g.name, g.latest, "--json"])
    goneRestorer.running = true
  }
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
    if (holding) { noteNote = writer.running ? "Still saving; try again in a moment."
                                             : "Save or reload this note first; what you typed is not saved."; return }
    clearEditor()
    creating = false
    editTarget = target
    openName = name
    read()
  }
  function startNew() {
    if (box.dirty) { box.commit(); return }
    if (holding) { noteNote = writer.running ? "Still saving; try again in a moment."
                                             : "Save or reload this note first; what you typed is not saved."; return }
    clearEditor()
    openName = ""
    editTarget = target
    creating = false                    // the Loader makes a fresh, empty field
    creating = true
    noteLoaded = true
    Qt.callLater(function() { if (np.nameInput) np.nameInput.forceActiveFocus() })
  }
  function close() {
    if (box.dirty) { box.commit(); return }
    // A save started by the click's own blur: wait for its answer, so a
    // refusal keeps the text on screen rather than closing over it.
    if (writer.running) { noteNote = "Still saving; close again in a moment."; return }
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
    if (editTarget !== target) return    // the folder changed under the editor
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
      held = t; holding = true            // kept, and nothing reloads over it
      return
    }
    if (writer.running) {
      queued = t; hasQueued = true; queuedSession = session
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
    openName = conflictName
    creating = false
    noteRev = conflictRev
    noteLoaded = true
    save(box.text)
  }
  function reloadTheirs() {
    var name = conflictRev >= 0 ? conflictName : (creating ? newName : openName)
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

  // No save on the way: a commit here would go to the new folder. What was
  // typed for the old one is refused by save() (editTarget) and dropped.
  onTargetChanged: {
    listing = null; listError = ""
    clearEditor()
    openName = ""; creating = false; editTarget = ""
    combining = false; picked = []; moveNote = ""; dragActive = false
    refresh()
  }
  onActiveChanged: if (active) refresh()
  Component.onCompleted: refresh()

  Timer {
    interval: 4000
    repeat: true
    running: np.active && np.target !== ""
    onTriggered: np.list()
  }
  // The other lanes change less often, and reading them all costs more.
  Timer {
    interval: 8000
    repeat: true
    running: np.active && np.target !== ""
    onTriggered: np.lanes()
  }

  Process {
    id: lanesRunner
    property bool again: false
    onRunningChanged: if (!running && again) { again = false; Qt.callLater(np.lanes) }
    stdout: StdioCollector {
      onStreamFinished: {
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        if (!d || !Array.isArray(d.lanes) || np.dragActive) return
        if (np.lanesData === null || JSON.stringify(np.lanesData) !== JSON.stringify(d)) np.lanesData = d
      }
    }
  }
  Process {
    id: goneRestorer
    stdout: StdioCollector {
      onStreamFinished: {
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        if (d && typeof d.rev === "number") np.actionNote = "Put back: " + d.name + "."
      }
    }
    stderr: StdioCollector {
      onStreamFinished: { var t = String(text).trim(); if (t !== "") np.actionNote = "Not put back: " + np.err(t) }
    }
    onRunningChanged: if (!running) np.refresh()
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
        if (np.dragActive) return
        if (np.listing !== null && JSON.stringify(np.listing) === JSON.stringify(d)) return
        np.listing = d
        // Picks for Combine that are no longer here are dropped.
        if (np.picked.length > 0)
          np.picked = np.picked.filter(function(n) { return d.notes.some(function(x) { return x.name === n }) })
        // The open note left (moved, combined or deleted): the editor closes
        // rather than offer to save it back into a folder it left.
        if (np.openName !== "" && !np.creating && np.noteLoaded && np.openEntry === null &&
            !box.editing && !np.holding) {
          var left = np.openName
          np.clearEditor()
          np.openName = ""
          np.actionNote = left + " is no longer here: it was moved, combined or deleted."
          return
        }
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
        // An edit queued behind this one is saved when the writer is idle
        // (writeCheck), on the rev just returned.
        if (np.hasQueued) return
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
          np.conflictName = writer.forName
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
    onTriggered: {
      if (!writer.answered && !writer.running) {
        writer.answered = true
        np.noteNote = "Not saved: the agentvoice command could not be run."
      }
      // Both streams are done by now: drain the queue, for this note only.
      if (np.hasQueued && !writer.running) {
        var next = np.queued
        var mine = np.queuedSession === np.session && np.conflictRev < 0
        np.hasQueued = false; np.queued = ""
        if (mine) np.save(next)
      }
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
    text: (np.communal
          ? "Notes every agent here can read, and write unless it is set to read only on its Agents card. " +
            "A note is handed to an agent as information, never as an instruction."
          : np.owner + "'s own notes: what it writes down for itself. Other agents cannot reach them " +
            "through the notes tools. What it writes in the communal notes is on the Communal page.") +
          " One note per topic: agents are told to add to a topic's note rather than start another."
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
    ActionButton {
      text: "New note"
      bordered: true
      focusable: true
      foreground: np.foreground
      fontFamily: np.fontFamily
      onClicked: np.startNew()
    }
    ActionButton {
      text: "Open folder"
      bordered: true
      focusable: true
      foreground: np.foreground
      fontFamily: np.fontFamily
      onClicked: np.openFolder()
    }
    ActionButton {
      visible: np.notesList.length >= 2 && !np.lockedAll
      text: np.combining ? "Stop combining" : "Combine…"
      focusable: true
      foreground: np.foreground
      fontFamily: np.fontFamily
      tooltipText: "Merge several notes here into one topic note"
      onClicked: np.startCombine()
    }
  }
  Text {
    width: parent.width
    visible: np.combining
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: np.picked.length === 0
          ? "Pick the notes to combine. The first you pick is kept; the others are added under it, each with its topic as a heading."
          : "Kept: " + np.picked[0] + (np.picked.length > 1 ? ". Added under it: " + np.picked.slice(1).join(", ") + "." : ". Pick at least one more.")
    color: np.dim
    font.family: np.fontFamily
    font.pixelSize: Style.font.caption
  }
  ActionButton {
    visible: np.combining
    text: "Combine " + np.picked.length + " notes…"
    bordered: true
    focusable: true
    enabled: np.picked.length >= 2 && !noteMover.busy
    foreground: np.foreground
    fontFamily: np.fontFamily
    onClicked: np.askCombine()
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

  // --- the lanes (M13) -------------------------------------------------------------
  // This folder's topics first, each a card: Open puts it in the editor
  // below, Lock binds every agent. Then every other folder's, whose cards
  // open on their own tab. A drag moves a card (Ctrl copies); Move to… does
  // the same from the keyboard.
  Flow {
    id: noteLanes
    width: parent.width
    visible: np.listing !== null
    spacing: Style.space(10)
    readonly property real laneWidth: width >= Style.space(760) ? (width - spacing) / 2 : width

    DropLane {
      width: noteLanes.laneWidth
      laneId: np.target
      title: np.homeLabel
      subtitle: np.communal ? "Every agent can read these." : "Its own notes."
      count: np.notesList.length
      dragKey: "agentvoice-note"
      emptyText: "No notes yet. " + (np.communal ? "Any agent may start one" : np.owner + " starts one") +
                 " when it has something worth keeping, or you can, with New note, or drag one here."
      refuse: function(p, copy, from) { return np.noteRefusal(p, np.target) }
      onReceived: function(p, copy, from) { np.noteDropped(p, copy, from, np.target) }
      foreground: np.foreground
      fontFamily: np.fontFamily
      Repeater {
        model: np.notesList
        SkillCard {
          required property var modelData
          width: parent.width
          draggable: !np.lockedAll && !modelData.problem
          dragKey: "agentvoice-note"
          laneId: np.target
          payload: np.notePayload(modelData, np.target)
          lanes: np.laneList
          onMoveRequested: function(to, copy) { np.noteDropped(payload, copy, np.target, to) }
          onDraggingChanged: np.dragActive = dragging
          Component.onDestruction: if (dragging) np.dragActive = false
          title: modelData.label || modelData.name
          subtitle: modelData.first_line || ""
          badge: modelData.locked ? "locked" : ""
          status: np.noteStatus(modelData)
          statusUrgent: modelData.tainted === true || (modelData.problem || "") !== ""
          details: np.noteDetails(modelData)
          border.color: modelData.name === np.openName ? Commons.Color.accent
                        : Qt.rgba(np.foreground.r, np.foreground.g, np.foreground.b, 0.22)
          foreground: np.foreground
          fontFamily: np.fontFamily
          ActionButton {
            text: modelData.name === np.openName ? "Open ✓" : "Open"
            focusable: true
            fontSize: Style.font.caption
            foreground: np.foreground
            fontFamily: np.fontFamily
            onClicked: np.open(modelData.name)
          }
          ActionButton {
            text: modelData.locked ? "Unlock" : "Lock"
            enabled: !np.lockedAll
            focusable: true
            fontSize: Style.font.caption
            foreground: np.foreground
            fontFamily: np.fontFamily
            tooltipText: "A locked note is read-only for every agent, wherever it is moved"
            onClicked: np.setLock(modelData.name, !modelData.locked)
          }
          ActionButton {
            visible: np.combining
            text: np.picked.indexOf(modelData.name) === 0 ? "Kept ✓"
                  : np.picked.indexOf(modelData.name) > 0 ? "Picked ✓" : "Pick"
            bordered: np.picked.indexOf(modelData.name) >= 0
            focusable: true
            fontSize: Style.font.caption
            foreground: np.foreground
            fontFamily: np.fontFamily
            onClicked: np.togglePick(modelData.name)
          }
        }
      }
    }

    Repeater {
      model: np.otherLanes
      DropLane {
        id: otherLane
        required property var modelData
        width: noteLanes.laneWidth
        laneId: modelData.id
        title: modelData.label + (modelData.quarantined && modelData.id !== "communal" ? " · quarantined" : "")
        subtitle: modelData.problem !== "" ? modelData.problem
                  : modelData.id === "communal" ? "Every agent can read these. Open one to edit it on the Communal page."
                  : "Open one to edit it on " + modelData.label + "'s own Notes tab."
        count: modelData.notes.length
        dragKey: "agentvoice-note"
        emptyText: "No notes."
        refuse: function(p, copy, from) { return np.noteRefusal(p, laneId) }
        onReceived: function(p, copy, from) { np.noteDropped(p, copy, from, laneId) }
        foreground: np.foreground
        fontFamily: np.fontFamily
        Repeater {
          model: otherLane.modelData.notes
          SkillCard {
            required property var modelData
            width: parent.width
            draggable: otherLane.modelData.locked_all !== true && !modelData.problem
            dragKey: "agentvoice-note"
            laneId: otherLane.laneId
            payload: np.notePayload(modelData, otherLane.laneId)
            lanes: np.laneList
            onMoveRequested: function(to, copy) { np.noteDropped(payload, copy, otherLane.laneId, to) }
            onDraggingChanged: np.dragActive = dragging
          Component.onDestruction: if (dragging) np.dragActive = false
            title: modelData.label || modelData.name
            subtitle: modelData.first_line || ""
            badge: modelData.locked ? "locked" : ""
            status: np.noteStatus(modelData)
            statusUrgent: modelData.tainted === true || (modelData.problem || "") !== ""
            details: np.noteDetails(modelData)
            foreground: np.foreground
            fontFamily: np.fontFamily
            ActionButton {
              text: "Open →"
              focusable: true
              fontSize: Style.font.caption
              foreground: np.foreground
              fontFamily: np.fontFamily
              tooltipText: "Open it on " + otherLane.modelData.label + "'s Notes"
              onClicked: np.openElsewhere(otherLane.laneId)
            }
          }
        }
      }
    }
  }
  // The move or copy itself, its confirm when it widens, Combine's confirm,
  // and Undo.
  NoteMover {
    id: noteMover
    width: parent.width
    labels: np.laneLabels
    quarantined: np.quarantinedIds
    foreground: np.foreground
    fontFamily: np.fontFamily
    onChanged: np.refresh()
    onCombined: function(t, into) { if (t === np.target) { np.combining = false; np.picked = [] } }
  }
  Text {
    width: parent.width
    visible: np.moveNote !== ""
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: np.moveNote
    color: Commons.Color.urgent
    font.family: np.fontFamily
    font.pixelSize: Style.font.caption
  }
  Text {
    width: parent.width
    visible: np.listing !== null
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: "Drag a card to another lane to move it (hold Ctrl to copy), or use its Move to…; Undo is offered " +
          "for ten seconds. A note's past versions, who wrote it, its lock and its web-page mark go with it."
    color: np.dim
    font.family: np.fontFamily
    font.pixelSize: Style.font.caption
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
    ActionButton {
      required property var modelData
      text: modelData.name + (modelData.kind !== "file" ? "  (" + modelData.kind + ")" : "")
      focusable: true
      foreground: np.foreground
      fontFamily: np.fontFamily
      onClicked: np.openFile(modelData.name)
    }
  }

  // --- Earlier notes (M13) ---------------------------------------------------------
  // Names with saved versions and no note now: combined away, or deleted by
  // hand. Put back restores the newest version, as the person.
  ActionButton {
    visible: np.goneList.length > 0
    text: (np.showGone ? "▾ " : "▸ ") + "Earlier notes (" + np.goneList.length + ")"
    focusable: true
    foreground: np.foreground
    fontFamily: np.fontFamily
    onClicked: np.showGone = !np.showGone
  }
  Repeater {
    model: np.showGone ? np.goneList : []
    Flow {
      required property var modelData
      width: np.width
      spacing: Style.space(8)
      Text {
        text: (modelData.label || modelData.name) + " · " + modelData.versions +
              (modelData.versions === 1 ? " saved version" : " saved versions") + " · newest " + np.when(modelData.at)
        textFormat: Text.PlainText
        color: np.foreground
        font.family: np.fontFamily
        font.pixelSize: Style.font.bodySmall
      }
      ActionButton {
        text: "Put back"
        focusable: true
        enabled: !goneRestorer.running
        fontSize: Style.font.caption
        foreground: np.foreground
        fontFamily: np.fontFamily
        tooltipText: "Make it a note again from its newest saved version"
        onClicked: np.restoreGone(modelData)
      }
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
      // Not typed in before the note has been read: an edit begun on the
      // empty box would hold off the read, and the save would have no rev.
      enabled: np.creating || np.noteLoaded
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
      ActionButton {
        text: "Save"
        bordered: true
        focusable: true
        enabled: !writer.running
        foreground: np.foreground
        fontFamily: np.fontFamily
        // The click's blur has already started this save when there was
        // anything to save; a second one would be the same text again.
        onClicked: if (!writer.running) np.save(box.text.trim())
      }
      ActionButton {
        visible: np.conflictRev >= 0
        text: "Keep mine"
        bordered: true
        focusable: true
        foreground: np.foreground
        fontFamily: np.fontFamily
        onClicked: np.keepMine()
      }
      ActionButton {
        visible: np.conflictRev >= 0
        text: "Reload"
        bordered: true
        focusable: true
        foreground: np.foreground
        fontFamily: np.fontFamily
        onClicked: np.reloadTheirs()
      }
      ActionButton {
        visible: !np.creating
        text: np.showHistory ? "Hide history" : "History"
        bordered: true
        focusable: true
        foreground: np.foreground
        fontFamily: np.fontFamily
        onClicked: { np.showHistory = !np.showHistory; if (np.showHistory) np.loadHistory() }
      }
      ActionButton {
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
          ActionButton {
            text: np.viewing === modelData.version ? "Viewing" : "View"
            focusable: true
            foreground: np.foreground
            fontFamily: np.fontFamily
            onClicked: np.view(modelData.version)
          }
          ActionButton {
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
