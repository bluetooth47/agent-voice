import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// Importing rules, defaults and skills into Communal from a folder (master
// plan, M15), with Undo. It names no setting: it runs `agentvoice agents
// import communal DIR`, which is a dry run, shows everything that says --
// each file it would write, a diff for each text, each skill, the agents it
// reaches and every problem -- and only then asks. The commit carries the
// dry run's token, so it is exactly what was shown or nothing (the command
// refuses when the folder or Communal moved since); `--confirm` is built in
// commitImport() alone, which is called only from the ToolConfirm's
// onConfirmed (tests/test_confirms.py). Undo, for ten seconds, runs
// `agentvoice agents import-undo OP`, refused when anything it wrote has
// changed since.
//
// Every line of a dry run is somebody's file or folder name: plain text.
Column {
  id: imp

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property color urgent: Commons.Color.urgent
  readonly property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family
  // Where an export lands by default, shown as the field's example.
  property string example: "~/Downloads/agentvoice-communal-…"

  property bool open: false
  property var planned: null
  property string checkedDir: ""
  property bool confirming: false
  property string note: ""
  property var last: null
  readonly property bool busy: checker.running || committer.running || undoer.running

  signal changed()

  width: parent ? parent.width : 300
  spacing: Style.space(8)

  function check(dir) {
    var d = String(dir || "").trim()
    if (d === "" || checker.running) return
    note = ""
    planned = null
    confirming = false
    checker.dir = d
    checker.out = ""
    checker.command = ["agentvoice", "agents", "import", "communal", d, "--json"]
    checker.running = true
  }
  function canImport() {
    return planned !== null && planned.problems.length === 0 && planned.changes > 0
  }
  function commitImport() {
    if (!canImport() || committer.running) return
    confirming = false
    committer.out = ""
    committer.err = ""
    committer.command = ["agentvoice", "agents", "import", "communal", checkedDir,
                         "--confirm", String(planned.token), "--json"]
    committer.running = true
  }
  function undoImport() {
    if (last === null || undoer.running) return
    undoer.err = ""
    undoer.command = ["agentvoice", "agents", "import-undo", String(last.op), "--json"]
    undoer.running = true
  }
  // What the confirm lists: the files, who it reaches, what it replaces.
  function confirmLines() {
    if (planned === null) return []
    var out = [{ label: "Writes", value: planned.files.join(", ") }]
    out.push({ label: "Reaches", value: planned.reaches.length ? planned.reaches.join(", ")
                                        : "no agent now (each one has opted out)" })
    var replaced = planned.texts.filter(function(t) { return t.change === "replace" })
                                .map(function(t) { return t.file })
    if (replaced.length) out.push({ label: "Replaces", value: replaced.join(", ") +
                                    " (each one's current text stays in its History)" })
    return out
  }

  Process {
    id: checker
    property string dir: ""
    property string out: ""
    stdout: StdioCollector { onStreamFinished: checker.out = String(text) }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        if (t !== "") imp.note = t.replace(/^agentvoice agents: /, "").split("\n").pop()
      }
    }
    onRunningChanged: if (!running) {
      var d
      try { d = JSON.parse(checker.out) } catch (e) { return }
      if (!d || !Array.isArray(d.problems)) return
      imp.planned = d
      imp.checkedDir = checker.dir
    }
  }
  Process {
    id: committer
    property string out: ""
    property string err: ""
    stdout: StdioCollector { onStreamFinished: committer.out = String(text) }
    stderr: StdioCollector { onStreamFinished: committer.err = String(text).trim() }
    onRunningChanged: if (!running) {
      var d = null
      try { d = JSON.parse(committer.out) } catch (e) { d = null }
      if (d && d.op) {
        imp.last = d
        imp.planned = null
        undo.show("Imported " + [d.texts.length ? d.texts.join(" and ") : "",
                                 d.skills.length ? d.skills.length + (d.skills.length === 1 ? " skill" : " skills") : ""]
                  .filter(function(x) { return x !== "" }).join(" and ") + " into Communal.")
      } else {
        imp.note = "Not imported: " + (committer.err.replace(/^agentvoice agents: /, "").split("\n").pop()
                                       || "the agentvoice command could not be run.")
      }
      imp.changed()
    }
  }
  Process {
    id: undoer
    property string err: ""
    stderr: StdioCollector { onStreamFinished: undoer.err = String(text).trim() }
    onRunningChanged: if (!running) {
      imp.note = undoer.err !== "" ? "Not undone: " + undoer.err.replace(/^agentvoice agents: /, "").split("\n").pop()
                                   : "The import was undone."
      imp.last = null
      imp.changed()
    }
  }

  Flow {
    width: parent.width
    spacing: Style.space(8)
    TextField {
      id: dirField
      width: Math.min(parent.width, Style.space(340))
      placeholderText: "Folder, e.g. " + imp.example
      foreground: imp.foreground
      font.family: imp.fontFamily
      onAccepted: imp.check(text)
    }
    ActionButton {
      text: checker.running ? "Reading…" : "Check"
      tooltipText: "List what importing this folder would change; nothing changes yet"
      bordered: true
      focusable: true
      enabled: !imp.busy && dirField.text.trim() !== ""
      foreground: imp.foreground
      fontFamily: imp.fontFamily
      onClicked: imp.check(dirField.text)
    }
  }
  Text {
    width: parent.width
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: "A folder as Export writes it: rules.md, defaults.md and skills/. Checking changes nothing; " +
          "importing asks first, and can be undone."
    color: imp.dim
    font.family: imp.fontFamily
    font.pixelSize: Style.font.caption
  }

  // The dry run.
  Column {
    width: parent.width
    visible: imp.planned !== null
    spacing: Style.space(4)

    Repeater {
      model: imp.planned ? imp.planned.texts : []
      Column {
        required property var modelData
        width: parent.width
        spacing: Style.space(2)
        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          textFormat: Text.PlainText
          text: modelData.file + ": " + ({ same: "the same as now, left alone", "new": "new",
                                           replace: "replaces the current one" })[modelData.change] +
                " · " + modelData.chars + " of " + modelData.limit + " characters"
          color: imp.foreground
          font.family: imp.fontFamily
          font.pixelSize: Style.font.caption
        }
        Repeater {
          model: (modelData.diff || []).slice(2)
          Text {
            required property var modelData
            width: parent.width
            leftPadding: Style.space(10)
            wrapMode: Text.WrapAtWordBoundaryOrAnywhere
            textFormat: Text.PlainText
            text: String(modelData)
            color: String(modelData).charAt(0) === "+" ? imp.accent
                   : String(modelData).charAt(0) === "-" ? imp.urgent : imp.dim
            font.family: "monospace"
            font.pixelSize: Style.font.caption
          }
        }
      }
    }
    Repeater {
      model: imp.planned ? imp.planned.skills : []
      Text {
        required property var modelData
        width: parent.width
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: "Skill " + modelData.name + ": " +
              ({ "new": "new", same: "Communal has it already, left alone",
                 clash: "Communal has another skill by this name" })[modelData.change] +
              " · " + modelData.files + (modelData.files === 1 ? " file" : " files") +
              (modelData.hidden_for.length ? " · hidden for " + modelData.hidden_for.join(", ") +
               " by its own of that name" : "")
        color: modelData.change === "clash" ? imp.urgent : imp.foreground
        font.family: imp.fontFamily
        font.pixelSize: Style.font.caption
      }
    }
    Text {
      width: parent.width
      visible: imp.planned !== null && imp.planned.ignored.length > 0
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: imp.planned ? "Not imported (not rules, defaults or skills): " + imp.planned.ignored.join(", ") : ""
      color: imp.dim
      font.family: imp.fontFamily
      font.pixelSize: Style.font.caption
    }
    Text {
      width: parent.width
      visible: imp.planned !== null
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: imp.planned ? "Reaches " + (imp.planned.reaches.length ? imp.planned.reaches.join(", ") : "no agent now") +
                          ": every agent that takes Communal." : ""
      color: imp.dim
      font.family: imp.fontFamily
      font.pixelSize: Style.font.caption
    }
    Repeater {
      model: imp.planned ? imp.planned.problems : []
      Text {
        required property var modelData
        width: parent.width
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: "! " + String(modelData)
        color: imp.urgent
        font.family: imp.fontFamily
        font.pixelSize: Style.font.caption
      }
    }
    Text {
      width: parent.width
      visible: imp.planned !== null && imp.planned.problems.length === 0 && imp.planned.changes === 0
      text: "Nothing to import: Communal has all of it already."
      textFormat: Text.PlainText
      color: imp.dim
      font.family: imp.fontFamily
      font.pixelSize: Style.font.caption
    }
    ActionButton {
      text: "Import…"
      bordered: true
      focusable: true
      visible: imp.canImport() && !imp.confirming
      enabled: !imp.busy
      foreground: imp.foreground
      fontFamily: imp.fontFamily
      onClicked: imp.confirming = true
    }
  }

  ToolConfirm {
    width: parent.width
    visible: imp.confirming && imp.canImport()
    title: "Import into Communal?"
    lines: imp.confirmLines()
    warning: "Every agent that takes Communal is told these rules and defaults and given these " +
             "skills from its next request."
    confirmText: "Import"
    foreground: imp.foreground
    fontFamily: imp.fontFamily
    onConfirmed: imp.commitImport()
    onCancelled: imp.confirming = false
  }

  Text {
    width: parent.width
    visible: imp.note !== ""
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: imp.note
    color: imp.note.indexOf("Not ") === 0 ? imp.urgent : imp.foreground
    font.family: imp.fontFamily
    font.pixelSize: Style.font.caption
  }

  UndoToast {
    id: undo
    width: Math.min(parent.width, Style.space(460))
    foreground: imp.foreground
    accent: imp.accent
    fontFamily: imp.fontFamily
    onUndo: imp.undoImport()
  }
}
