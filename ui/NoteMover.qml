import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// Moving, copying and combining notes, and Undo (master plan, M13), for the
// Notes tabs: a drop on a note lane and a card's "Move to…" both end in
// request(); the Combine button ends in askCombine(). It knows no setting:
// the panel hands it the lane names and who is quarantined, both from
// `agentvoice notes lanes`.
//
// Widening asks first (section 7.3): into Communal (every agent can read
// it), out of a quarantined agent (or any agent when the list cannot be
// read), and a note that may hold text from web pages. The confirm says
// that past versions go with it. The command then carries --confirm, which
// is built in transferNote() alone, called only from the ToolConfirm's
// onConfirmed (tests/test_notemoves_ui.py). Anything else runs at once. The
// daemon checks again (`agentvoice notes move` refuses a widening move
// without --confirm), so this is the question, not the guard.
//
// Combine removes notes from the list, so it is always asked: which note
// is kept, which are added under it, and that each one's past versions
// stay (Earlier notes puts one back). combineNotes() is called only from
// that confirm's onConfirmed.
//
// After a move or copy an UndoToast offers Undo for ten seconds; Undo runs
// `agentvoice notes undo OP`, which the daemon refuses if either side has
// changed since. A failure is said, never silent.
//
//   NoteMover {
//     labels: ({ theo: "Theo", communal: "Communal" })
//     quarantined: ["hazel"]            // anything but a list: unreadable
//     onChanged: panel.refresh()
//   }
Column {
  id: mover

  property var labels: ({})
  property var quarantined: []
  property color foreground: Commons.Color.foreground
  property color urgent: Commons.Color.urgent
  property string fontFamily: Style.font.family

  // What the move confirm asks about: { name, label, from, to, copy, tainted, versions }.
  property var pending: null
  // What the Combine confirm asks about: { target, into, names, labels, tainted, locked }.
  property var pendingCombine: null
  property var last: null
  property string note: ""
  readonly property bool busy: runner.running || undoer.running || combiner.running

  signal changed()
  // A Combine finished: the note kept, so the panel can open it.
  signal combined(string target, string into)

  width: parent ? parent.width : implicitWidth
  spacing: Style.space(6)

  function label(id) {
    if (id === "communal") return "Communal"
    return labels && labels[id] !== undefined ? String(labels[id]) : String(id)
  }
  function quarantineReadable() { return Array.isArray(quarantined) }
  function isQuarantined(id) { return id !== "communal" && (!quarantineReadable() || quarantined.indexOf(id) >= 0) }
  function widening(from, to, tainted) {
    return to === "communal" || isQuarantined(from) || tainted === true
  }

  // Asked by a drop or a menu.
  function request(name, from, to, copy, tainted, topic, versions) {
    if (busy || from === to || !name) return
    note = ""
    pendingCombine = null
    if (widening(from, to, tainted)) {
      pending = { name: name, label: topic || name, from: from, to: to, copy: copy === true,
                  tainted: tainted === true, versions: versions || 0 }
      return
    }
    pending = null
    runner.command = ["agentvoice", "notes", copy === true ? "copy" : "move", from, name, to]
    runner.running = true
  }
  // The confirmed one: only ever from the move ToolConfirm below.
  function transferNote(p) {
    pending = null
    if (busy || p === null) return
    runner.command = ["agentvoice", "notes", p.copy ? "copy" : "move", p.from, p.name, p.to, "--confirm"]
    runner.running = true
  }
  // Combine: always asked. `parts`: [{ name, label, tainted, locked }], the
  // first is the note kept.
  function askCombine(target, parts) {
    if (busy || !parts || parts.length < 2) return
    note = ""
    pending = null
    pendingCombine = { target: target, into: parts[0].name, intoLabel: parts[0].label,
                       names: parts.map(function(x) { return x.name }),
                       others: parts.slice(1).map(function(x) { return x.label }),
                       tainted: parts.some(function(x) { return x.tainted === true }),
                       locked: parts.some(function(x) { return x.locked === true }) }
  }
  // The confirmed one: only ever from the Combine ToolConfirm below.
  function combineNotes(c) {
    pendingCombine = null
    if (busy || c === null) return
    combiner.target = c.target
    combiner.into = c.into
    combiner.command = ["agentvoice", "notes", "combine", c.target, c.into].concat(c.names)
    combiner.running = true
  }
  function undoLast() {
    if (last === null || undoer.running) return
    note = ""
    undoer.command = ["agentvoice", "notes", "undo", String(last.op)]
    last = null
    undoer.running = true
  }
  function said(text, prefix) {
    var t = String(text).trim()
    return t === "" ? "" : prefix + t.replace(/^agentvoice notes: /, "").split("\n").pop()
  }

  ToolConfirm {
    visible: mover.pending !== null
    title: mover.pending === null ? ""
           : (mover.pending.copy ? "Copy " : "Move ") + mover.pending.label + " to " +
             mover.label(mover.pending.to) + "?"
    lines: mover.pending === null ? [] : [
             { label: "From", value: mover.label(mover.pending.from) +
                                     (mover.isQuarantined(mover.pending.from)
                                      ? (mover.quarantineReadable() ? " (quarantined)"
                                         : " (the quarantine list cannot be read)") : "") },
             { label: "Who can read it", value: mover.pending.to === "communal"
               ? "Every agent here, through the notes tools"
               : mover.label(mover.pending.to) + (mover.pending.copy ? ", and whoever could read the original" : " only") },
             { label: "Past versions", value: (mover.pending.versions > 0
               ? mover.pending.versions + (mover.pending.versions === 1 ? " saved version" : " saved versions")
               : "Any saved versions") + (mover.pending.copy ? " are copied too" : " go with it") }]
    warning: mover.pending === null ? ""
             : (mover.pending.tainted ? "It may contain text from web pages: an agent that reads it is reading that text. " : "") +
               (mover.isQuarantined(mover.pending.from)
                ? "This agent is quarantined: it may have written this note for others to read. Read it before you share it. " : "") +
               "Its past versions " + (mover.pending.copy ? "are copied" : "move") +
               " too, so whoever can read it there can read what it said before."
    confirmText: mover.pending !== null && mover.pending.copy ? "Copy" : "Move"
    foreground: mover.foreground
    fontFamily: mover.fontFamily
    onConfirmed: mover.transferNote(mover.pending)
    onCancelled: mover.pending = null
  }

  ToolConfirm {
    visible: mover.pendingCombine !== null
    title: mover.pendingCombine === null ? ""
           : "Combine " + mover.pendingCombine.names.length + " notes into " + mover.pendingCombine.intoLabel + "?"
    lines: mover.pendingCombine === null ? [] : [
             { label: "Kept", value: mover.pendingCombine.intoLabel },
             { label: "Added under it", value: mover.pendingCombine.others.join(", ") +
                                               ", each under its topic as a heading" },
             { label: "Afterwards", value: "Only " + mover.pendingCombine.intoLabel + " is listed. Each other " +
                                           "note's past versions stay, and Earlier notes can put it back." }]
    warning: mover.pendingCombine === null ? ""
             : (mover.pendingCombine.tainted ? "Part of it may contain text from web pages, so the combined note is marked so too. " : "") +
               (mover.pendingCombine.locked ? "Part of it is locked, so the combined note is locked too. " : "") +
               "This cannot be undone in one step."
    confirmText: "Combine"
    foreground: mover.foreground
    fontFamily: mover.fontFamily
    onConfirmed: mover.combineNotes(mover.pendingCombine)
    onCancelled: mover.pendingCombine = null
  }

  UndoToast {
    id: toast
    width: Math.min(implicitWidth, parent.width)
    foreground: mover.foreground
    fontFamily: mover.fontFamily
    onUndo: mover.undoLast()
    onExpired: mover.last = null
  }

  Text {
    width: parent.width
    visible: mover.note !== ""
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: mover.note
    color: mover.urgent
    font.family: mover.fontFamily
    font.pixelSize: Style.font.caption
  }

  Process {
    id: runner
    stdout: StdioCollector {
      onStreamFinished: {
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        if (!d || !d.op) return
        mover.last = d
        toast.show((d.action === "copy" ? "Copied " : "Moved ") + d.name + " to " + mover.label(d.to) + ".")
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = mover.said(text, "Not moved: ")
        if (t !== "") mover.note = t
      }
    }
    onRunningChanged: if (!running) mover.changed()
  }
  Process {
    id: undoer
    stdout: StdioCollector {
      onStreamFinished: {
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        if (d && d.name) mover.note = ""
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = mover.said(text, "Not undone: ")
        if (t !== "") mover.note = t
      }
    }
    onRunningChanged: if (!running) mover.changed()
  }
  Process {
    id: combiner
    property string target: ""
    property string into: ""
    property bool done: false
    onStarted: done = false
    stdout: StdioCollector {
      onStreamFinished: {
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        if (d && d.action === "combine") { combiner.done = true; mover.note = "" }
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = mover.said(text, "Not combined: ")
        if (t !== "") mover.note = t
      }
    }
    onRunningChanged: if (!running) {
      mover.changed()
      if (combiner.done) mover.combined(combiner.target, combiner.into)
    }
  }
}
