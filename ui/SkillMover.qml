import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// Moving and copying a skill between agents and Communal, and Undo (master
// plan, M12), for every page that shows skill lanes: a drop on a lane and a
// card's "Move to…" both end in request(). It knows no setting; the page
// hands it the lane names and the quarantine list.
//
// Widening asks first (section 7.3): into Communal ("every agent will get
// this skill"), and out of a quarantined agent, or out of any agent when the
// quarantine list cannot be read. The command then carries --confirm, which
// is built in transferSkill() alone, and that is called only from the
// ToolConfirm's onConfirmed (tests/test_transfer_ui.py). Anything else runs
// at once. The daemon checks again (`agentvoice skills` refuses a widening
// move without --confirm), so this is the question, not the guard.
//
// After a move or copy, an UndoToast offers Undo for ten seconds; Undo runs
// `agentvoice skills undo OP`, which the daemon refuses if either side has
// changed since. A failure is said under the lanes, never silent.
//
//   SkillMover {
//     labels: ({ theo: "Theo", communal: "Communal" })
//     quarantined: page.s.setting("crewQuarantine", [])
//     onChanged: page.reload()
//   }
//   ... onReceived: function(p, copy, from) { mover.request(p.name, from, laneId, copy) }
Column {
  id: mover

  property var labels: ({})
  // Agent ids in quarantine; anything but a list reads as "cannot be read".
  property var quarantined: []
  property color foreground: Commons.Color.foreground
  property color urgent: Commons.Color.urgent
  property string fontFamily: Style.font.family

  // What the confirm is asking about: { name, from, to, copy, shadows }.
  property var pending: null
  // The last move or copy, for Undo: the command's own answer.
  property var last: null
  property string note: ""
  readonly property bool busy: runner.running || undoer.running

  signal changed()

  width: parent ? parent.width : implicitWidth
  spacing: Style.space(6)

  function label(id) {
    if (id === "communal") return "Communal"
    return labels && labels[id] !== undefined ? String(labels[id]) : String(id)
  }
  function quarantineReadable() { return Array.isArray(quarantined) }
  function isQuarantined(id) { return !quarantineReadable() || quarantined.indexOf(id) >= 0 }
  function widening(from, to) { return to === "communal" || (from !== "communal" && isQuarantined(from)) }

  // Asked by a drop or a menu. `shadows`: the lanes that keep their own
  // skill of this name, for the confirm to say.
  function request(name, from, to, copy, shadows) {
    if (busy || from === to || !name) return
    note = ""
    if (widening(from, to)) {
      pending = { name: name, from: from, to: to, copy: copy === true, shadows: shadows || [] }
      return
    }
    pending = null
    runner.command = ["agentvoice", "skills", copy === true ? "copy" : "move", from, name, to]
    runner.running = true
  }
  // The confirmed one: only ever from the ToolConfirm below.
  function transferSkill(p) {
    pending = null
    if (busy || p === null) return
    runner.command = ["agentvoice", "skills", p.copy ? "copy" : "move", p.from, p.name, p.to, "--confirm"]
    runner.running = true
  }
  function undoLast() {
    if (last === null || undoer.running) return
    note = ""
    undoer.command = ["agentvoice", "skills", "undo", String(last.op)]
    last = null
    undoer.running = true
  }
  // A transfer made elsewhere (a Give a copy import), offered for Undo here.
  function offer(result, message) {
    if (!result || !result.op) return
    last = result
    toast.show(message)
  }
  function said(text, prefix) {
    var t = String(text).trim()
    return t === "" ? "" : prefix + t.replace(/^agentvoice skills: /, "").split("\n").pop()
  }

  ToolConfirm {
    visible: mover.pending !== null
    title: mover.pending === null ? ""
           : (mover.pending.copy ? "Copy " : "Move ") + mover.pending.name + " to " +
             mover.label(mover.pending.to) + "?"
    lines: mover.pending === null ? [] : [
             { label: "From", value: mover.label(mover.pending.from) +
                                     (mover.isQuarantined(mover.pending.from) && mover.pending.from !== "communal"
                                      ? (mover.quarantineReadable() ? " (quarantined)"
                                         : " (the quarantine list cannot be read)") : "") },
             { label: "Who gets it", value: mover.pending.to === "communal"
               ? "Every agent will get this skill, unless it switches it off or has its own of that name"
               : mover.label(mover.pending.to) + " only" },
             { label: "Keeps its own", value: mover.pending.shadows.length > 0
               ? mover.pending.shadows.map(function(x) { return mover.label(x) }).join(", ")
               : "nobody" }]
    warning: mover.pending === null ? ""
             : (mover.pending.from !== "communal" && mover.isQuarantined(mover.pending.from)
                ? "This agent is quarantined: it may have written this skill itself. Read it before " +
                  "you share it. " : "") +
               "A skill tells an agent what to do, and its scripts run at that agent's own permission " +
               "level. Its past versions go with it."
    confirmText: mover.pending !== null && mover.pending.copy ? "Copy" : "Move"
    foreground: mover.foreground
    fontFamily: mover.fontFamily
    onConfirmed: mover.transferSkill(mover.pending)
    onCancelled: mover.pending = null
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
}
