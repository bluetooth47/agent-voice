import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// An agent's standing instructions, kept in its folder's instructions.md
// (merged plan, Phase 10) rather than in shell.json.
//
// Read and written through `agentvoice agents`, the one module that owns the
// folders: it checks the id, keeps a saved version of every write and never
// lets two saves overwrite each other. Looks and saves exactly like the old
// box (on losing focus), so the page is unchanged until Phase 12 replaces it.
//
// - The text goes over stdin as one JSON line, never argv: /proc/<pid>/cmdline
//   is readable by every account, and this is what the agent is told.
// - Each save carries the stamp the text was read at. If the file changed
//   since (a hand edit, another window), nothing is overwritten: the typed
//   text stays in the box and the note says what happened, with a way to
//   keep either.
// - Until the daemon has made the folder (it does on its next start), the
//   file is missing and the agent is still told the old setting, so that is
//   what the box shows: `fallback`. The first save creates the file.
Column {
  id: fib

  // "main", or the agent's id.
  property string target: ""
  // The old setting, shown while the file does not exist yet.
  property string fallback: ""
  property string placeholder: ""
  // Anything that changes when the daemon notices a change to this folder:
  // the published sizes. Reloads, unless an unsaved edit is being kept.
  property string watch: ""
  property color foreground: Commons.Color.foreground
  property string fontFamily: Style.font.family

  // What the agent is told now, as last read or saved.
  property string saved: ""
  property string stamp: ""
  property bool exists: false
  property bool loaded: false
  // Why the last read or save failed, in words; "" when it did not.
  property string note: ""
  // A save refused because the file changed since it was read: the stamp it
  // has now, so "keep mine" can replace exactly that version.
  property string conflictStamp: ""
  // Text the person typed that is not saved yet (a failed or refused save).
  // While it is held, nothing reloads over it.
  property string unsaved: ""
  property bool holding: false

  // Bumped by every save and every change of target. A read started before
  // either and finished after would otherwise put the old text and stamp
  // back over the new ones, or one agent's text on another's card.
  property int saveGen: 0
  // A reload asked for while the box was being edited, done when the edit
  // ends. Never during one: it would move the stamp on under text read at
  // the old one, and the save on blur would then overwrite a newer file
  // with no conflict (Phase 10 review).
  property bool reloadWanted: false

  readonly property string shown: exists ? saved : fallback.trim()
  readonly property bool busy: reader.running || writer.running

  spacing: Style.space(4)
  width: parent ? parent.width : 300

  function reload() {
    if (box.editing) { reloadWanted = true; return }
    if (target === "" || reader.running || holding) return
    reader.gen = fib.saveGen
    reader.forTarget = target
    reader.command = ["agentvoice", "agents", "show", target, "--json"]
    reader.running = true
  }
  function save(t) {
    if (target === "" || writer.running) return
    fib.saveGen++
    fib.unsaved = t
    fib.holding = true
    fib.conflictStamp = ""
    // With no stamp read there is no base to save against, and a save with
    // none overwrites whatever is there. Kept in the box instead.
    if (!fib.loaded) {
      fib.note = "Not saved: the current instructions could not be read first" +
                 (fib.note !== "" ? " (" + fib.note + ")" : "") +
                 ", so saving might overwrite them."
      return
    }
    fib.note = ""
    writer.forTarget = target
    var cmd = ["agentvoice", "agents", "write", target, "instructions.md", "--line"]
    // "missing" is a stamp too: it means create, and only if still absent.
    if (fib.stamp !== "") cmd = cmd.concat(["--base", fib.stamp])
    writer.command = cmd
    writer.pending = JSON.stringify(t) + "\n"
    writer.running = true
  }
  function keepMine() {
    if (conflictStamp === "") return
    fib.stamp = conflictStamp
    save(unsaved)
  }
  function showTheirs() {
    fib.holding = false
    fib.unsaved = ""
    fib.conflictStamp = ""
    fib.note = ""
    reload()
  }

  // A card reused for another agent (the list reordered) starts clean, and
  // any read or save still running for the old one is ignored when it ends.
  onTargetChanged: {
    saveGen++
    holding = false; loaded = false; exists = false; reloadWanted = false
    saved = ""; stamp = ""; unsaved = ""; note = ""; conflictStamp = ""
    reload()
  }
  onWatchChanged: reload()
  Component.onCompleted: reload()

  Process {
    id: reader
    property int gen: 0
    property string forTarget: ""
    stdout: StdioCollector {
      onStreamFinished: {
        if (reader.gen !== fib.saveGen || fib.holding || reader.forTarget !== fib.target) return
        // An edit began while this read ran: read again once it ends.
        if (box.editing) { fib.reloadWanted = true; return }
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        var f = ((d || {}).files || {})["instructions.md"]
        if (!f) return
        fib.exists = f.exists === true && f.stamp !== "missing"
        fib.saved = String(f.text || "")
        fib.stamp = String(f.stamp || "missing")
        fib.loaded = true
        fib.note = f.problem ? String(f.problem) : ""
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        if (t !== "" && reader.forTarget === fib.target)
          fib.note = t.replace(/^agentvoice agents: /, "")
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
        if (!/^[0-9a-f]{16}-[0-9]+$/.test(t) || writer.forTarget !== fib.target) return
        fib.stamp = t
        fib.saved = fib.unsaved.trim()
        fib.exists = true
        fib.holding = false
        fib.unsaved = ""
        fib.note = ""
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        if (t === "" || writer.forTarget !== fib.target) return
        var m = t.match(/current stamp ([0-9a-f]{16}-[0-9]+|missing)/)
        if (t.indexOf("conflict:") === 0 && m) {
          fib.conflictStamp = m[1]
          fib.note = "These instructions were changed somewhere else after you opened them, " +
                     "so yours were not saved."
        } else {
          fib.note = "Not saved: " + t.replace(/^agentvoice agents: /, "")
        }
      }
    }
  }

  // Both output streams have finished by now; if neither said anything,
  // the CLI never ran.
  Timer {
    id: silentCheck
    interval: 300
    onTriggered: if (fib.holding && fib.note === "")
                   fib.note = "Not saved: the agentvoice command could not be run."
  }

  InstructionsBox {
    id: box
    width: parent.width
    value: fib.holding ? fib.unsaved : fib.shown
    placeholder: fib.placeholder
    foreground: fib.foreground
    fontFamily: fib.fontFamily
    onCommitted: function(t) { fib.save(t) }
    // After the commit that losing focus makes, so the save goes first.
    onEditingChanged: if (!editing && fib.reloadWanted) {
      fib.reloadWanted = false
      Qt.callLater(fib.reload)
    }
  }

  Text {
    width: parent.width
    visible: fib.note !== ""
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: fib.note
    color: Commons.Color.urgent
    font.family: fib.fontFamily
    font.pixelSize: Style.font.bodySmall
  }

  Row {
    visible: fib.conflictStamp !== ""
    spacing: Style.space(8)
    Button {
      text: "Replace it with mine"
      bordered: true
      foreground: fib.foreground
      fontFamily: fib.fontFamily
      onClicked: fib.keepMine()
    }
    Button {
      text: "Show the other version"
      bordered: true
      foreground: fib.foreground
      fontFamily: fib.fontFamily
      onClicked: fib.showTheirs()
    }
  }
}
