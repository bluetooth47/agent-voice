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

  // What the agent is told now, as last read or saved.
  property string saved: ""
  property string stamp: ""
  property bool exists: false
  property bool loaded: false
  // What the last read said was wrong with the file (too long, cannot be
  // read); the box then shows what the agent is told instead.
  property string readProblem: ""
  property bool changedOutside: false
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
  // A reload asked for while the box was being edited, done when the edit
  // ends. Never during one: it would move the stamp on under text read at
  // the old one, and the save on blur would then overwrite a newer file
  // with no conflict (Phase 10 review).
  property bool reloadWanted: false
  property bool readAgain: false

  readonly property string shown: exists ? saved : fallback.trim()
  readonly property bool busy: reader.running || writer.running || fixer.running
  readonly property alias editing: box.editing

  // One line under the box saying where it stands.
  readonly property string status: {
    if (!fe.loaded && reader.running) return "Reading…"
    if (writer.running) return "Saving…"
    if (fixer.running) return "Working…"
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

  function reload() {
    if (box.editing) { reloadWanted = true; return }
    if (target === "" || file === "" || holding) return
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
    if (target === "" || file === "" || writer.running) return
    fe.saveGen++
    fe.unsaved = t
    fe.holding = true
    fe.justSaved = false
    fe.conflictStamp = ""
    // With no stamp read there is no base to save against, and a save with
    // none overwrites whatever is there. Kept in the box instead.
    if (!fe.loaded) {
      fe.note = "Not saved: the file could not be read first" +
                (fe.readProblem !== "" ? " (" + fe.readProblem + ")" : "") +
                ", so saving might overwrite it."
      return
    }
    fe.note = ""
    writer.forTarget = target
    var cmd = ["agentvoice", "agents", "write", target, fe.file, "--line"]
    // "missing" is a stamp too: it means create, and only if still absent.
    if (fe.stamp !== "") cmd = cmd.concat(["--base", fe.stamp])
    writer.command = cmd
    writer.pending = JSON.stringify(t) + "\n"
    writer.running = true
  }
  function keepMine() {
    if (conflictStamp === "") return
    fe.stamp = conflictStamp
    save(unsaved)
  }
  function showTheirs() {
    fe.holding = false
    fe.unsaved = ""
    fe.conflictStamp = ""
    fe.note = ""
    reload()
  }
  // The outside-change notice: keep what is there now, or put back the
  // newest saved version. Both only if the file is still what was read.
  function fix(verb) {
    if (fixer.running || fe.stamp === "" || !fe.loaded) return
    fe.note = ""
    fixer.forTarget = target
    fixer.verb = verb
    fixer.command = ["agentvoice", "agents", verb, target, fe.file, "--base", fe.stamp]
    fixer.running = true
  }

  // A different agent starts clean, and any read or save still running for
  // the previous one is ignored when it ends.
  onTargetChanged: {
    saveGen++
    holding = false; loaded = false; exists = false; reloadWanted = false
    saved = ""; stamp = ""; unsaved = ""; note = ""; conflictStamp = ""
    readProblem = ""; changedOutside = false; justSaved = false
    reload()
  }
  onWatchChanged: reload()
  Component.onCompleted: reload()

  Process {
    id: reader
    property int gen: 0
    property string forTarget: ""
    onRunningChanged: if (!running && fe.readAgain) {
      fe.readAgain = false
      Qt.callLater(fe.reload)
    }
    stdout: StdioCollector {
      onStreamFinished: {
        if (reader.gen !== fe.saveGen || fe.holding || reader.forTarget !== fe.target) return
        // An edit began while this read ran: read again once it ends.
        if (box.editing) { fe.reloadWanted = true; return }
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        var f = ((d || {}).files || {})[fe.file]
        if (!f) return
        fe.exists = f.exists === true && f.stamp !== "missing"
        fe.saved = String(f.text || "")
        fe.stamp = String(f.stamp || "missing")
        fe.loaded = true
        fe.readProblem = f.problem ? String(f.problem) : ""
        fe.changedOutside = f.changed_outside === true
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        if (t !== "" && reader.forTarget === fe.target)
          fe.readProblem = t.replace(/^agentvoice agents: /, "")
      }
    }
  }

  Process {
    id: writer
    property string pending: ""
    property string forTarget: ""
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
        if (!/^[0-9a-f]{16}-[0-9]+$/.test(t) || writer.forTarget !== fe.target) return
        fe.stamp = t
        fe.saved = fe.unsaved.trim()
        fe.exists = true
        fe.holding = false
        fe.unsaved = ""
        fe.note = ""
        fe.readProblem = ""
        fe.changedOutside = false
        fe.justSaved = true
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        if (t === "" || writer.forTarget !== fe.target) return
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
    onTriggered: if (fe.holding && fe.note === "")
                   fe.note = "Not saved: the agentvoice command could not be run."
  }

  Process {
    id: fixer
    property string forTarget: ""
    property string verb: ""
    property string err: ""
    onStarted: fixer.err = ""
    stderr: StdioCollector { onStreamFinished: fixer.err = String(text).trim() }
    onRunningChanged: if (!running) fixDone.restart()
  }
  Timer {
    id: fixDone
    interval: 300
    onTriggered: {
      if (fixer.forTarget !== fe.target) return
      var t = fixer.err
      if (t.indexOf("conflict:") === 0)
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
          foreground: fe.foreground
          fontFamily: fe.fontFamily
          onClicked: fe.fix("ack")
        }
        Button {
          text: "Revert"
          bordered: true
          enabled: !fe.busy
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
      foreground: fe.foreground
      fontFamily: fe.fontFamily
      onClicked: fe.keepMine()
    }
    Button {
      text: "Reload"
      bordered: true
      foreground: fe.foreground
      fontFamily: fe.fontFamily
      onClicked: fe.showTheirs()
    }
  }
}
