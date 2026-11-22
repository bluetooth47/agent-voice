import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// One file in an agent's folder or the communal folder (role.md,
// personality.md, instructions.md, rules.md, defaults.md), edited in place
// (merged plan, Phase 12). The one editor for each file: nothing else in
// the overlay writes them.
//
// Read and written through `agentvoice agents`, the one module that owns the
// folders: it checks the id, keeps a saved version of every write and never
// lets two saves overwrite each other.
//
// - The text goes over stdin as one JSON line, never argv: /proc/<pid>/cmdline
//   is readable by every account, and this is what an agent is told.
// - Saved when focus leaves the box and on Ctrl+S. Each save carries the
//   stamp the text was read at; if the file changed since (a hand edit,
//   another window), nothing is overwritten: the typed text stays in the box
//   and the note says what happened, with "Keep mine" and "Reload".
// - A file changed outside Settings (its text no longer matches its newest
//   saved version) shows a notice with Keep and Revert, as the daemon's
//   journal does (Phase 9).
// - Until an agent's instructions.md exists, the agent is still told the old
//   setting, so that is what the box shows: `fallback`. The first save
//   creates the file.
Column {
  id: fe

  // "main", an agent's id, or "communal".
  property string target: ""
  property string file: ""
  property int limit: 2000
  // The old setting, shown while the file does not exist yet.
  property string fallback: ""
  property string placeholder: ""
  property real minHeight: Style.space(84)
  // Anything that changes when the folder changes on disk: the published
  // sizes. Reloads, unless an edit is under way or unsaved text is kept.
  property string watch: ""
  property color foreground: Commons.Color.foreground
  property string fontFamily: Style.font.family
  // Something with keep(target, file, text, base): saves typed text this
  // editor can no longer save itself, because it is being destroyed (the
  // page left, the overlay closed) or moved to another agent mid-edit. The
  // overlay's AgentFolders. Without one, such text is lost.
  property var keeper: null

  // The file's own text, as last read or saved: uncut, so saving it never
  // drops the end of a file over its budget (Phase 12 review).
  property string saved: ""
  property string stamp: ""
  property bool exists: false
  property bool loaded: false
  // What the last read said was wrong with the file (too long, cannot be
  // read); the box then shows what the agent is told instead.
  property string readProblem: ""
  property bool changedOutside: false
  // Only the first part of the file could be read (agentfs READ_CAP): a
  // save from here would write that part back over the whole, so none is
  // made (Codex review of M6, pass 2). Typing and the trait chips alike.
  property bool partial: false
  // Why the last save, Keep or Revert failed, in words; "" when it did not.
  property string note: ""
  // A save refused because the file changed since it was read: the stamp it
  // has now, so "Keep mine" can replace exactly that version.
  property string conflictStamp: ""
  // Text the person typed that is not saved yet (a failed or refused save).
  // While it is held, nothing reloads over it.
  property string unsaved: ""
  property bool holding: false
  // Saved since the box was last typed in: says so until the next edit.
  property bool justSaved: false

  // Bumped by every save and every change of target. A read started before
  // either and finished after would otherwise put the old text and stamp
  // back over the new ones, or one agent's text on another's editor.
  property int saveGen: 0
  // Bumped only when the target changes: a write's result is accepted only
  // in the session it was started in, so A → B → A cannot take A's old
  // result as the answer to the newer edit.
  property int session: 0
  // An edit committed while a write was still running, saved next, on the
  // stamp that write returns.
  property string queued: ""
  property bool hasQueued: false
  // A save asked for before the file was read: saved once it has been.
  property bool retryAfterRead: false
  property string boundTarget: ""
  // A reload asked for while the box was being edited, done when the edit
  // ends. Never during one: it would move the stamp on under text read at
  // the old one, and the save on blur would then overwrite a newer file
  // with no conflict (Phase 10 review).
  property bool reloadWanted: false
  property bool readAgain: false

  readonly property string shown: exists ? saved : fallback.trim()
  readonly property bool busy: reader.running || writer.running || fixer.running
  readonly property alias editing: box.editing
  // What is in the box now, saved or not: the draft Try it speaks from, and
  // the text the trait chips rewrite (phase M6).
  readonly property alias current: box.text

  // One line under the box saying where it stands.
  readonly property string status: {
    if (!fe.loaded && reader.running) return "Reading…"
    if (writer.running) return "Saving…"
    if (fixer.running) return "Working…"
    if (fe.retryAfterRead && reader.running) return "Reading, then saving…"
    if (fe.holding) return "Unsaved"
    if (box.dirty) return "Unsaved · Ctrl+S or click away to save"
    if (fe.justSaved) return "Saved · applies on the next turn"
    if (fe.loaded && !fe.exists && !fe.changedOutside)
      return fe.fallback.trim() !== ""
             ? "Showing the old setting, which the agent is still told. Saving moves it into " + fe.file + "."
             : "No " + fe.file + " yet. Saving creates it."
    return ""
  }

  spacing: Style.space(4)
  width: parent ? parent.width : 300

  // Characters as the daemon counts them (code points, not UTF-16 units).
  function chars(t) { return Array.from(String(t)).length }
  // What the agent is actually told of `t`, counted: agentfs.clean() --
  // BOMs, line endings, tabs, control characters, leading comments and the
  // ends trimmed -- then code points (phase M6, the meters). Python's idea
  // of whitespace, not JavaScript's: \u0085 is space there, \ufeff is not.
  // test_personality.py runs this against clean() itself.
  function sentChars(t) {
    var ws = "[\\t\\n\\v\\f\\r \\u0085\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000]"
    var x = String(t).replace(/^\uFEFF+/, "").replace(/\r\n/g, "\n").replace(/\r/g, "\n")
    x = x.replace(/\t/g, " ").replace(/[\u0000-\u0008\u000b-\u001f\u007f]/g, "")
    var lead = new RegExp("^" + ws + "*<!--[\\s\\S]*?-->")
    for (;;) {
      var m = x.match(lead)
      if (!m) break
      x = x.slice(m[0].length)
    }
    x = x.replace(new RegExp("^" + ws + "+"), "").replace(new RegExp(ws + "+$"), "")
    return Array.from(x).length
  }
  // Put `t` in the box and save it, as if it had been typed: a starter, or
  // the text the trait chips rewrote. The same stamp, conflict check and
  // budget as typing, so nothing else in the overlay writes these files.
  function fill(t) {
    box.reset(String(t))
    save(String(t).trim())
  }

  function reload() {
    if (box.editing) { reloadWanted = true; return }
    if (target === "" || file === "" || holding) return
    read()
  }
  function read() {
    // A change noticed during a read may have landed after the read began:
    // read again when it ends, rather than drop it (the folder made just
    // after a new agent's editor first looked, found by the preview).
    if (reader.running) { readAgain = true; return }
    reader.gen = fe.saveGen
    reader.forTarget = target
    reader.command = ["agentvoice", "agents", "show", target, "--json"]
    reader.running = true
  }
  function save(t) {
    if (target === "" || file === "") return
    // One write at a time; a newer edit waits for the stamp this one returns.
    if (writer.running) {
      fe.queued = t; fe.hasQueued = true
      fe.unsaved = t; fe.holding = true
      return
    }
    fe.saveGen++
    fe.unsaved = t
    fe.holding = true
    fe.justSaved = false
    fe.conflictStamp = ""
    if (fe.partial) {
      fe.note = "Not saved: " + fe.file + " is too large to have been read whole, so saving " +
                "would drop the rest of it. Shorten it by hand."
      return
    }
    // Never cut to fit: the text stays in the box and the count says why.
    // Counted as it would be told, which is what the budget is about.
    if (fe.sentChars(t) > fe.limit) {
      fe.note = "Not saved: " + fe.sentChars(t) + " characters, and at most " + fe.limit +
                " are told to the agent. Shorten it, then save again."
      return
    }
    // With no stamp read there is no base to save against, and a save with
    // none overwrites whatever is there: read first, then save.
    if (!fe.loaded) {
      fe.note = ""
      fe.retryAfterRead = true
      read()
      return
    }
    fe.note = ""
    writer.forTarget = target
    writer.session = fe.session
    writer.text = t
    writer.answered = false
    var cmd = ["agentvoice", "agents", "write", target, fe.file, "--line"]
    // "missing" is a stamp too: it means create, and only if still absent.
    if (fe.stamp !== "") cmd = cmd.concat(["--base", fe.stamp])
    writer.command = cmd
    writer.pending = JSON.stringify(t) + "\n"
    writer.running = true
  }
  // What is in the box: the text as typed, which after a refused save may
  // have been changed again since.
  function keepMine() {
    if (conflictStamp === "") return
    fe.stamp = conflictStamp
    save(box.text.trim())
  }
  function showTheirs() {
    fe.holding = false
    fe.unsaved = ""
    fe.conflictStamp = ""
    fe.note = ""
    fe.hasQueued = false
    box.reset(fe.shown)
    reload()
  }
  // Text typed here and not saved: what the keeper is handed when this
  // editor can no longer save it. null when there is none.
  function typed() {
    if (!box) return null
    var t = box.text.trim()
    var showing = (fe.holding ? fe.unsaved : fe.shown).trim()
    if (t !== showing) return t
    return fe.holding ? fe.unsaved : null
  }
  function handOff(forTarget) {
    var t = typed()
    if (t === null || !fe.keeper || !fe.loaded || forTarget === "" || writer.running) return
    fe.keeper.keep(forTarget, fe.file, t, fe.stamp)
  }
  Component.onDestruction: handOff(fe.boundTarget)

  // The outside-change notice: keep what is there now, or put back the
  // newest saved version. Both only if the file is still what was read.
  function fix(verb) {
    if (fixer.running || fe.stamp === "" || !fe.loaded) return
    fe.note = ""
    fixer.forTarget = target
    fixer.started = false
    fixer.verb = verb
    fixer.command = ["agentvoice", "agents", verb, target, fe.file, "--base", fe.stamp]
    fixer.running = true
  }

  // A different agent starts clean, and any read or save still running for
  // the previous one is ignored when it ends.
  // Typed text for the previous agent is saved under that agent, never
  // carried over to this one.
  onTargetChanged: {
    handOff(boundTarget)
    boundTarget = target
    saveGen++; session++
    holding = false; loaded = false; exists = false; reloadWanted = false
    saved = ""; stamp = ""; unsaved = ""; note = ""; conflictStamp = ""
    readProblem = ""; changedOutside = false; justSaved = false; partial = false
    hasQueued = false; queued = ""; retryAfterRead = false
    box.reset("")
    reload()
  }
  onWatchChanged: reload()
  Component.onCompleted: { boundTarget = target; reload() }

  Process {
    id: reader
    property int gen: 0
    property string forTarget: ""
    onRunningChanged: if (!running && fe.readAgain) {
      fe.readAgain = false
      // A save waiting for its base reads past the hold that stops reloads.
      Qt.callLater(function() { if (fe.retryAfterRead) fe.read(); else fe.reload() })
    }
    stdout: StdioCollector {
      onStreamFinished: {
        if (reader.gen !== fe.saveGen || reader.forTarget !== fe.target) return
        if (fe.holding && !fe.retryAfterRead) return
        // An edit began while this read ran: read again once it ends.
        if (box.editing && !fe.retryAfterRead) { fe.reloadWanted = true; return }
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        var f = ((d || {}).files || {})[fe.file]
        if (!f) return
        fe.exists = f.exists === true && f.stamp !== "missing"
        fe.saved = String(f.full !== undefined ? f.full : (f.text || ""))
        fe.stamp = String(f.stamp || "missing")
        fe.loaded = true
        fe.readProblem = f.problem ? String(f.problem) : ""
        fe.changedOutside = f.changed_outside === true
        fe.partial = f.partial === true
        // A save that waited for this read: now it has a base.
        if (fe.retryAfterRead) {
          fe.retryAfterRead = false
          var t = fe.unsaved
          Qt.callLater(function() { fe.save(t) })
        }
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        if (t === "" || reader.forTarget !== fe.target) return
        fe.readProblem = t.replace(/^agentvoice agents: /, "")
        if (fe.retryAfterRead) {
          fe.retryAfterRead = false
          fe.note = "Not saved: the file could not be read first (" + fe.readProblem +
                    "), so saving might overwrite it."
        }
      }
    }
  }

  Process {
    id: writer
    property string pending: ""
    property string forTarget: ""
    property int session: 0
    property string text: ""
    property bool answered: false
    stdinEnabled: true
    // One JSON line, so the CLI needs no end of input to know it is done.
    onStarted: { write(writer.pending); writer.pending = "" }
    // `running` going false, not onExited: a spawn that never started (no
    // `agentvoice` on PATH) emits no exit, and a save that did nothing must
    // say so rather than leave the box looking saved.
    onRunningChanged: if (!running) silentCheck.restart()
    stdout: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        if (!/^[0-9a-f]{16}-[0-9]+$/.test(t)) return
        writer.answered = true
        if (writer.session !== fe.session || writer.forTarget !== fe.target) return
        fe.stamp = t
        fe.saved = writer.text.trim()
        fe.exists = true
        fe.note = ""
        if (fe.hasQueued) {
          // The edit made meanwhile, on the stamp just returned.
          var next = fe.queued
          fe.hasQueued = false
          fe.queued = ""
          Qt.callLater(function() { fe.save(next) })
          return
        }
        fe.holding = false
        fe.unsaved = ""
        fe.readProblem = ""
        fe.changedOutside = false
        fe.justSaved = true
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        if (t === "") return
        writer.answered = true
        if (writer.session !== fe.session || writer.forTarget !== fe.target) return
        // An edit queued behind a refused one is the newest text: it is what
        // "Keep mine" saves.
        if (fe.hasQueued) { fe.unsaved = fe.queued; fe.hasQueued = false; fe.queued = "" }
        var m = t.match(/current stamp ([0-9a-f]{16}-[0-9]+|missing)/)
        if (t.indexOf("conflict:") === 0 && m) {
          fe.conflictStamp = m[1]
          fe.note = "Changed outside Settings after you opened it, so yours was not saved."
        } else {
          fe.note = "Not saved: " + t.replace(/^agentvoice agents: /, "")
        }
      }
    }
  }

  // Both output streams have finished by now; if neither said anything,
  // the CLI never ran.
  Timer {
    id: silentCheck
    interval: 300
    onTriggered: if (!writer.answered && !writer.running && writer.session === fe.session) {
      writer.answered = true
      fe.note = "Not saved: the agentvoice command could not be run."
    }
  }

  Process {
    id: fixer
    property string forTarget: ""
    property string verb: ""
    property string err: ""
    property bool started: false
    onStarted: { fixer.err = ""; fixer.started = true }
    stderr: StdioCollector { onStreamFinished: fixer.err = String(text).trim() }
    onRunningChanged: if (!running) fixDone.restart()
  }
  Timer {
    id: fixDone
    interval: 300
    onTriggered: {
      if (fixer.forTarget !== fe.target) return
      var t = fixer.err
      if (!fixer.started)
        fe.note = "Nothing changed: the agentvoice command could not be run."
      else if (t.indexOf("conflict:") === 0)
        fe.note = "It changed again since it was shown; look at it once more first."
      else if (t !== "")
        fe.note = (fixer.verb === "revert" ? "Not reverted: " : "Not kept: ") +
                  t.replace(/^agentvoice agents: /, "")
      fe.reload()
    }
  }

  // Changed outside Settings, and nothing typed is waiting.
  Rectangle {
    width: parent.width
    visible: fe.changedOutside && !fe.holding && fe.loaded
    height: visible ? outside.implicitHeight + Style.space(12) : 0
    radius: Style.cornerRadius
    color: Qt.rgba(Commons.Color.urgent.r, Commons.Color.urgent.g, Commons.Color.urgent.b, 0.10)

    Column {
      id: outside
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      anchors.margins: Style.space(8)
      spacing: Style.space(6)

      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: fe.exists
              ? "Changed outside Settings: the agent is already told what is below. Keep it, or put " +
                "back the last version saved here."
              : "Deleted outside Settings" +
                (fe.fallback.trim() !== "" ? ", so the agent is told the old setting shown below. " : ". ") +
                "Keep it deleted, or put back the last version saved here."
        color: fe.foreground
        font.family: fe.fontFamily
        font.pixelSize: Style.font.bodySmall
      }
      Row {
        spacing: Style.space(8)
        Button {
          text: "Keep"
          bordered: true
          enabled: !fe.busy
          focusable: true
          foreground: fe.foreground
          fontFamily: fe.fontFamily
          onClicked: fe.fix("ack")
        }
        Button {
          text: "Revert"
          bordered: true
          enabled: !fe.busy
          focusable: true
          foreground: fe.foreground
          fontFamily: fe.fontFamily
          onClicked: fe.fix("revert")
        }
      }
    }
  }

  InstructionsBox {
    id: box
    width: parent.width
    value: fe.holding ? fe.unsaved : fe.shown
    maxLength: fe.limit
    cutOff: false
    // The meter below counts instead, as the agent is told it.
    showCounter: false
    minHeight: fe.minHeight
    editingHint: "Ctrl+S or click away saves"
    placeholder: fe.placeholder
    foreground: fe.foreground
    fontFamily: fe.fontFamily
    onCommitted: function(t) { fe.save(t) }
    onEditingChanged: {
      if (editing) { fe.justSaved = false; return }
      // After the commit that losing focus makes, so the save goes first.
      if (fe.reloadWanted) {
        fe.reloadWanted = false
        Qt.callLater(fe.reload)
      }
    }
  }

  BudgetMeter {
    width: parent.width
    used: fe.sentChars(box.text)
    limit: fe.limit
    foreground: fe.foreground
    fontFamily: fe.fontFamily
  }

  Text {
    width: parent.width
    visible: fe.status !== ""
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: fe.status
    color: fe.foreground
    opacity: 0.6
    font.family: fe.fontFamily
    font.pixelSize: Style.font.bodySmall
  }

  Text {
    width: parent.width
    visible: fe.readProblem !== "" && !fe.holding
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: fe.readProblem
    color: Commons.Color.urgent
    font.family: fe.fontFamily
    font.pixelSize: Style.font.bodySmall
  }

  Text {
    width: parent.width
    visible: fe.note !== ""
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: fe.note
    color: Commons.Color.urgent
    font.family: fe.fontFamily
    font.pixelSize: Style.font.bodySmall
  }

  Row {
    visible: fe.conflictStamp !== ""
    spacing: Style.space(8)
    Button {
      text: "Keep mine"
      bordered: true
      focusable: true
      foreground: fe.foreground
      fontFamily: fe.fontFamily
      onClicked: fe.keepMine()
    }
    Button {
      text: "Reload"
      bordered: true
      focusable: true
      foreground: fe.foreground
      fontFamily: fe.fontFamily
      onClicked: fe.showTheirs()
    }
  }
}
