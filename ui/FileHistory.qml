import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// The saved versions of one folder file, beside its editor (master plan,
// M15: "History and Undo beside the Rules and Defaults editors"). Every save
// has kept a version since Phase 9; this lists them -- when, who, how long --
// and for each one View (its text, and a diff from it to what the file holds
// now) and Restore, with Undo for ten seconds after.
//
// It names no setting and writes only through `agentvoice agents revert
// TARGET FILE VERSION --base STAMP`, the editor's stamp, so a restore never
// lands on a file that changed since the editor read it; Undo restores the
// version that was newest before, on the stamp the restore returned. While
// the file was changed outside Settings, Restore waits: that text is in no
// version yet, and the editor's own Keep / Revert is the way to settle it.
//
// A version and a diff are somebody's file: plain text, always.
//
//   FileHistory {
//     target: "communal"; file: rulesEditor.file
//     stamp: rulesEditor.stamp; outside: rulesEditor.changedOutside
//     watch: page.watch
//     onRestored: rulesEditor.reload()
//   }
Column {
  id: fh

  property string target: ""
  property string file: ""
  // The editor's stamp: the base every restore is made on.
  property string stamp: ""
  property bool outside: false
  property string watch: ""
  property bool expanded: false
  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property color urgent: Commons.Color.urgent
  readonly property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  property var versions: []
  property string viewing: ""
  property var shown: null
  property string note: ""
  // What Undo puts back: the version that was newest before the restore.
  property string undoTo: ""
  property string undoBase: ""
  readonly property bool busy: lister.running || viewer.running || restorer.running

  signal restored()

  width: parent ? parent.width : 300
  spacing: Style.space(6)

  function whoLabel(w) {
    return ({ settings: "saved here", revert: "restored", you: "kept", template: "starter",
              "import": "imported", undo: "import undone", migrate: "moved in" })[w] || w
  }
  function when(at) {
    var d = new Date(at * 1000)
    return Qt.formatDateTime(d, "d MMM yyyy, hh:mm")
  }
  function load() {
    if (target === "" || file === "") return
    if (lister.running) { again.restart(); return }
    lister.command = ["agentvoice", "agents", "history", target, file, "--json"]
    lister.running = true
  }
  function view(v) {
    if (viewing === v) { viewing = ""; shown = null; return }
    viewing = v
    shown = null
    if (viewer.running) return
    viewer.command = ["agentvoice", "agents", "version", target, file, v, "--json"]
    viewer.running = true
  }
  function restore(v, then) {
    if (restorer.running || stamp === "" || outside) return
    note = ""
    restorer.undoing = then === "undo"
    restorer.previous = versions.length > 0 ? String(versions[0].version) : ""
    restorer.command = ["agentvoice", "agents", "revert", target, file, v,
                        "--base", then === "undo" ? undoBase : stamp]
    restorer.out = ""
    restorer.err = ""
    restorer.started = false
    restorer.running = true
  }

  onWatchChanged: if (expanded) again.restart()
  onStampChanged: if (expanded) again.restart()
  onExpandedChanged: if (expanded) load()
  onTargetChanged: { versions = []; viewing = ""; shown = null; note = "" }
  Timer { id: again; interval: 250; onTriggered: fh.load() }

  Process {
    id: lister
    stdout: StdioCollector {
      onStreamFinished: {
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        if (Array.isArray(d)) fh.versions = d
      }
    }
  }
  Process {
    id: viewer
    stdout: StdioCollector {
      onStreamFinished: {
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        if (d && d.version === fh.viewing) fh.shown = d
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        if (t !== "") fh.note = t.replace(/^agentvoice agents: /, "")
      }
    }
    // The person clicked another View meanwhile: read that one now.
    onRunningChanged: if (!running && fh.viewing !== "" && (fh.shown === null || fh.shown.version !== fh.viewing)) {
      viewer.command = ["agentvoice", "agents", "version", fh.target, fh.file, fh.viewing, "--json"]
      viewer.running = true
    }
  }
  Process {
    id: restorer
    property bool undoing: false
    property string previous: ""
    property string out: ""
    property string err: ""
    property bool started: false
    onStarted: started = true
    stdout: StdioCollector { onStreamFinished: restorer.out = String(text).trim() }
    stderr: StdioCollector { onStreamFinished: restorer.err = String(text).trim() }
    // `running` going false: a spawn that never started emits no exit.
    onRunningChanged: if (!running) settle.restart()
  }
  Timer {
    id: settle
    interval: 200
    onTriggered: {
      if (!restorer.started) { fh.note = "Nothing changed: the agentvoice command could not be run."; return }
      if (restorer.err !== "") {
        fh.note = restorer.err.indexOf("conflict:") === 0
                  ? "It changed since it was shown; look at it again first."
                  : "Not restored: " + restorer.err.replace(/^agentvoice agents: /, "")
        fh.load()
        return
      }
      if (!/^[0-9a-f]{16}-[0-9]+$/.test(restorer.out)) { fh.note = "Not restored."; return }
      fh.viewing = ""
      fh.shown = null
      if (restorer.undoing) {
        fh.undoTo = ""
      } else {
        fh.undoTo = restorer.previous
        fh.undoBase = restorer.out
        if (fh.undoTo !== "") undo.show("Restored an earlier " + fh.file + ".")
      }
      fh.restored()
      fh.load()
    }
  }

  Text {
    id: head
    text: (fh.expanded ? "▾ " : "▸ ") + "History" + (fh.versions.length ? " (" + fh.versions.length + ")" : "")
    textFormat: Text.PlainText
    color: headArea.containsMouse || head.activeFocus ? fh.foreground : fh.dim
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: "History" + (fh.expanded ? ", open" : ", folded")
    Accessible.focusable: true
    font.family: fh.fontFamily
    font.pixelSize: Style.font.caption
    Keys.onReturnPressed: fh.expanded = !fh.expanded
    Keys.onSpacePressed: fh.expanded = !fh.expanded
    MouseArea {
      id: headArea
      anchors.fill: parent
      anchors.margins: -Style.space(4)
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onClicked: fh.expanded = !fh.expanded
    }
  }

  Column {
    width: parent.width
    visible: fh.expanded
    spacing: Style.space(6)

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      visible: fh.outside
      text: "Changed outside Settings: keep or revert that change above before restoring a version."
      color: fh.urgent
      font.family: fh.fontFamily
      font.pixelSize: Style.font.caption
    }
    Text {
      width: parent.width
      visible: fh.versions.length === 0 && !lister.running
      text: "No saved versions yet. Each save keeps one; the newest ten are kept."
      textFormat: Text.PlainText
      wrapMode: Text.WordWrap
      color: fh.dim
      font.family: fh.fontFamily
      font.pixelSize: Style.font.caption
    }

    Repeater {
      model: fh.versions
      Column {
        required property var modelData
        required property int index
        width: parent.width
        spacing: Style.space(4)
        Row {
          width: parent.width
          spacing: Style.space(8)
          Text {
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - viewButton.width - restoreButton.width - parent.spacing * 2
            elide: Text.ElideRight
            textFormat: Text.PlainText
            text: fh.when(modelData.at) + " · " + fh.whoLabel(String(modelData.who)) + " · " +
                  (modelData.chars < 0 ? "cannot be read" : modelData.chars + " characters") +
                  (index === 0 ? " · newest" : "")
            color: fh.foreground
            font.family: fh.fontFamily
            font.pixelSize: Style.font.caption
          }
          ActionButton {
            id: viewButton
            text: fh.viewing === modelData.version ? "Hide" : "View"
            bordered: true
            focusable: true
            foreground: fh.foreground
            fontFamily: fh.fontFamily
            onClicked: fh.view(String(modelData.version))
          }
          ActionButton {
            id: restoreButton
            text: "Restore"
            bordered: true
            focusable: true
            enabled: !fh.busy && !fh.outside && fh.stamp !== "" && index > 0 && modelData.chars >= 0
            tooltipText: index === 0 ? "This is what the file holds now" : "Put this version back; Undo for ten seconds after"
            foreground: fh.foreground
            fontFamily: fh.fontFamily
            onClicked: fh.restore(String(modelData.version), "")
          }
        }
        // View: what that version said, and how the file differs from it now.
        Rectangle {
          width: parent.width
          visible: fh.viewing === modelData.version
          height: visible ? shownCol.implicitHeight + Style.space(12) : 0
          radius: Style.cornerRadius
          color: Qt.rgba(fh.foreground.r, fh.foreground.g, fh.foreground.b, 0.05)
          Column {
            id: shownCol
            x: Style.space(8)
            y: Style.space(6)
            width: parent.width - Style.space(16)
            spacing: Style.space(4)
            Text {
              width: parent.width
              text: fh.shown === null ? "Reading…" : fh.shown.same ? "The same as the file now." :
                    "From this version to the file now (− this version, + now):"
              textFormat: Text.PlainText
              wrapMode: Text.WordWrap
              color: fh.dim
              font.family: fh.fontFamily
              font.pixelSize: Style.font.caption
            }
            Repeater {
              model: fh.shown !== null && fh.viewing === modelData.version ? (fh.shown.diff || []).slice(2) : []
              Text {
                required property var modelData
                width: shownCol.width
                wrapMode: Text.WrapAtWordBoundaryOrAnywhere
                textFormat: Text.PlainText
                text: String(modelData)
                color: String(modelData).charAt(0) === "+" ? fh.accent
                       : String(modelData).charAt(0) === "-" ? fh.urgent : fh.dim
                font.family: "monospace"
                font.pixelSize: Style.font.caption
              }
            }
            Text {
              width: parent.width
              visible: fh.shown !== null
              text: "This version in full:"
              textFormat: Text.PlainText
              color: fh.dim
              font.family: fh.fontFamily
              font.pixelSize: Style.font.caption
            }
            Text {
              width: parent.width
              visible: fh.shown !== null
              wrapMode: Text.WrapAtWordBoundaryOrAnywhere
              textFormat: Text.PlainText
              text: fh.shown !== null ? (String(fh.shown.text) || "(empty)") : ""
              color: fh.foreground
              font.family: fh.fontFamily
              font.pixelSize: Style.font.bodySmall
            }
          }
        }
      }
    }

    Text {
      width: parent.width
      visible: fh.note !== ""
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: fh.note
      color: fh.urgent
      font.family: fh.fontFamily
      font.pixelSize: Style.font.caption
    }
  }

  UndoToast {
    id: undo
    width: Math.min(parent.width, Style.space(460))
    foreground: fh.foreground
    accent: fh.accent
    fontFamily: fh.fontFamily
    onUndo: if (fh.undoTo !== "") fh.restore(fh.undoTo, "undo")
  }
}
