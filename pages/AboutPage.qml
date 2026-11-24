import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import ".."
import "../ui"

// About (master plan M26): what is installed and which build, a report to
// copy when asking for help, an update check, what runs on this machine and
// what goes out, and every voice command. It changes nothing: repairing and
// removing the installation moved to Other settings → Maintenance.
//
// Everything here is read through the `agentvoice` CLI (daemon/
// diagnostics.py), when the page opens -- except the update check and the
// local-server probe, which reach out and so run only when clicked.
Column {
  id: page

  required property var s

  spacing: Style.space(18)

  // The plugin folder this file runs from: its own build is the settings'
  // build. A path, never anything said; it travels as one argv element.
  readonly property string pluginDir: decodeURIComponent(String(Qt.resolvedUrl(".."))
                                                         .replace(/^file:\/\//, "")).replace(/\/$/, "")
  function docPath(name) { return page.pluginDir + "/" + name }
  // What a CLI verb this build added says when the installed service is
  // older and does not have it yet.
  readonly property string needsRepair: "This needs the service installed from this build: " +
                                        "Other settings → Maintenance → Repair."

  // --- this install ---------------------------------------------------------------
  property var info: null
  property string infoError: ""
  Process {
    id: infoReader
    command: ["agentvoice", "about", "--json", "--plugin", page.pluginDir]
    stdout: StdioCollector {
      onStreamFinished: {
        try { page.info = JSON.parse(text); page.infoError = "" }
        catch (e) { page.info = null; page.infoError = page.needsRepair }
      }
    }
  }
  function shortCommit(c) { return String(c || "").substring(0, 12) }
  function buildLine(side) {
    if (!page.info) return page.infoError !== "" ? page.infoError : "Reading…"
    var b = page.info[side]
    if (side === "daemon" && !b.found) return "not installed"
    if (side === "plugin" && !b.git) return "version " + (b.version || "unknown") + ", not a git checkout"
    var commit = page.shortCommit(b.commit) || "unknown commit"
    var branch = b.branch === "detached" ? "detached" : b.branch !== "" ? "branch " + b.branch : "unknown branch"
    var when = side === "daemon" && b.installed ? " · installed " + String(b.installed).replace("T", " ").substring(0, 16) : ""
    return commit + " (" + branch + ")" + (b.dirty ? ", with uncommitted changes" : "") + when
  }

  // --- copy diagnostics -----------------------------------------------------------
  // `agentvoice diagnostics copy` builds the report and hands it to wl-copy
  // on stdin; this only says how it went. "Show what it copies" prints the
  // same report here, so nobody has to paste it to read it.
  property string copyNote: ""
  property bool copyFailed: false
  Process {
    id: copier
    property bool launched: false
    command: ["agentvoice", "diagnostics", "copy", "--plugin", page.pluginDir]
    onStarted: launched = true
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var r = JSON.parse(text)
          page.copyFailed = !r.copied
          page.copyNote = r.copied ? "Copied: " + r.lines + " lines. Read it before you send it anywhere."
                                   : "Could not reach the clipboard (wl-copy)."
        } catch (e) { page.copyFailed = true; page.copyNote = page.needsRepair }
      }
    }
    onRunningChanged: if (!running && !launched) { page.copyFailed = true; page.copyNote = "agentvoice could not be started." }
  }
  function copyDiagnostics() {
    if (copier.running) return
    page.copyNote = ""
    copier.launched = false
    copier.running = true
  }
  property string reportText: ""
  property bool reportShown: false
  Process {
    id: reporter
    command: ["agentvoice", "diagnostics", "--plugin", page.pluginDir]
    stdout: StdioCollector {
      onStreamFinished: page.reportText = text.indexOf("Agent Voice diagnostics") === 0 ? text : page.needsRepair
    }
  }
  function showReport() {
    page.reportShown = !page.reportShown
    if (page.reportShown && !reporter.running) reporter.running = true
  }

  // --- updates: only when clicked ---------------------------------------------------
  property var update: null
  Process {
    id: updater
    command: ["agentvoice", "about", "updates", "--json", "--plugin", page.pluginDir]
    stdout: StdioCollector {
      onStreamFinished: {
        try { page.update = JSON.parse(text) }
        catch (e) { page.update = { status: "failed", message: page.needsRepair, remote: "", url: "" } }
      }
    }
  }
  function checkUpdates() {
    if (updater.running) return
    page.update = null
    updater.running = true
  }

  // --- what runs here, and what goes out ------------------------------------------
  property var reach: null
  Process {
    id: reachReader
    command: ["agentvoice", "about", "backends", "--json"]
    stdout: StdioCollector {
      onStreamFinished: { try { page.reach = JSON.parse(text) } catch (e) { page.reach = null } }
    }
  }
  function statusText(b) {
    if (b.status === "answered") return "has answered " + (b.answered === 1 ? "a turn" : b.answered + " turns") + " here (90 days)"
    if (b.status === "configured") return "configured; no turn recorded" + (page.reach && !page.reach.stats ? " (usage numbers are off)" : "")
    if (b.status === "installed")
      return "installed; " + (page.reach && !page.reach.stats ? "usage numbers are off, so whether it has answered is not recorded"
                                                              : "no turn answered here yet")
    return "not found"
  }
  // Ollama and llama.cpp's server, on loopback, when clicked.
  property var probe: null
  Process {
    id: prober
    command: ["agentvoice", "endpoint", "probe-local"]
    stdout: StdioCollector {
      onStreamFinished: { try { page.probe = JSON.parse(text) } catch (e) { page.probe = [] } }
    }
  }
  function probeLocal() {
    if (prober.running) return
    page.probe = null
    prober.running = true
  }

  // --- voice commands ---------------------------------------------------------------
  property var commandTable: null
  Process {
    id: commandsReader
    command: ["agentvoice", "commands", "--json"]
    stdout: StdioCollector {
      onStreamFinished: { try { page.commandTable = JSON.parse(text) } catch (e) { page.commandTable = null } }
    }
  }
  function whereText(c) {
    var w = c.where || []
    var allowed = page.commandTable && page.commandTable.mode_positions
                  ? (page.commandTable.mode_positions[page.commandTable.mode] || ["alone"]) : ["alone"]
    var names = { alone: "on its own", start: "at the start", end: "at the end", clause: "inside a sentence" }
    var out = []
    for (var i = 0; i < w.length; i++) if (allowed.indexOf(w[i]) >= 0) out.push(names[w[i]] || w[i])
    return out.length ? out.join(", ") : "on its own"
  }

  // --- the changelog's newest entry ---------------------------------------------------
  property string changelogTop: ""
  FileView {
    path: page.docPath("CHANGELOG.md")
    printErrors: false
    onLoaded: {
      var t = text()
      var start = t.indexOf("\n## ")
      if (start < 0) { page.changelogTop = ""; return }
      var next = t.indexOf("\n## ", start + 4)
      // Shown as plain text, so the Markdown's marks come off: the heading's
      // hashes, bold and code ticks.
      page.changelogTop = t.substring(start + 1, next > 0 ? next : Math.min(t.length, start + 2000)).trim()
                           .replace(/^## /, "").replace(/\*\*/g, "").replace(/`/g, "")
                           .replace(/\n {2,}/g, " ")
    }
  }
  // A document opens in a terminal pager, read only (LESSSECURE: no editor,
  // no shell from inside it): an edit saved into the plugin folder would
  // leave it a checkout with local changes, which agentvoice-deploy refuses.
  Process { id: docOpener }
  function openDoc(name) {
    if (!/^(CHANGELOG\.md|LICENSE|README\.md)$/.test(name)) return
    docOpener.command = ["omarchy-launch-tui", "--app-id=org.omarchy.agentvoice-docs",
                         "env", "LESSSECURE=1", "less", "--", page.docPath(name)]
    docOpener.running = true
  }

  Component.onCompleted: {
    infoReader.running = true
    reachReader.running = true
    commandsReader.running = true
  }

  PageHeader {
    width: parent.width
    title: "About"
    subtitle: "Agent Voice" + (page.s.version !== "" ? " " + page.s.version : "") +
              " — wake word, spoken replies and the knobs that govern them."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
  }

  Card {
    width: parent.width
    title: "This install"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    InfoRow {
      foreground: page.s.foreground; urgent: page.s.urgent; dim: page.s.dim; fontFamily: page.s.fontFamily
      objectName: "rowVersion"
      label: "Version"
      value: page.info && page.info.version ? page.info.version : (page.s.version || "unknown")
    }
    InfoRow {
      foreground: page.s.foreground; urgent: page.s.urgent; dim: page.s.dim; fontFamily: page.s.fontFamily
      objectName: "rowSettings"
      label: "These settings"
      value: page.buildLine("plugin")
    }
    InfoRow {
      foreground: page.s.foreground; urgent: page.s.urgent; dim: page.s.dim; fontFamily: page.s.fontFamily
      objectName: "rowService"
      label: "The service"
      value: page.buildLine("daemon")
      ok: !page.info || page.info.daemon.found
    }
    Text {
      objectName: "buildNote"
      width: parent.width
      visible: !!page.info
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: page.info ? page.info.note : ""
      color: page.info && page.info.match === "differs" ? page.s.urgent : page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }

    Repeater {
      model: [
        { label: "Voice engine",
          value: page.s.engineInstalled ? "installed" : "not installed (Other settings → Maintenance)",
          ok: page.s.engineInstalled },
        { label: "Service",
          value: page.s.serviceActive ? "running" : "stopped — it does not start itself after a reboot",
          ok: true },
        { label: "Wake engine",
          value: page.s.owwLive ? "openWakeWord" : page.s.usingOww ? "Vosk (openWakeWord is not installed)"
               : page.s.sherpaLive ? "sherpa-onnx" : page.s.usingSherpa ? "Vosk (sherpa-onnx is not installed)"
               : "Vosk",
          ok: !(page.s.usingOww && !page.s.owwAvailable) && !(page.s.usingSherpa && !page.s.sherpaAvailable) },
        { label: "openWakeWord",
          value: page.s.owwAvailable ? "installed" : "not installed (optional, about 154MB)",
          ok: true },
        { label: "sherpa-onnx",
          value: page.s.sherpaAvailable ? "installed" : "not installed (optional, about 60MB)",
          ok: true },
        { label: "Voices on disk",
          value: page.s.voicesOnDisk.length === 0 ? "none found"
                 : page.s.voicesOnDisk.map(function(v) { return page.s.voiceName(v) }).join(", "),
          ok: page.s.voicesOnDisk.length > 0 },
        { label: "Main agent",
          value: page.s.usingEndpoint ? "an OpenAI-compatible endpoint"
                 : (page.s.mainAgent ? page.s.programLabel(page.s.mainAgent) : "none — set one with `omarchy default agent`"),
          ok: page.s.usingEndpoint || page.s.mainAgent !== "" }
      ]
      InfoRow {
      foreground: page.s.foreground; urgent: page.s.urgent; dim: page.s.dim; fontFamily: page.s.fontFamily
        required property var modelData
        label: modelData.label
        value: modelData.value
        ok: modelData.ok
      }
    }

    // Copy diagnostics, and what it copies.
    SettingRow {
      width: parent.width
      label: "Copy diagnostics"
      hint: page.copyNote !== "" ? page.copyNote
            : "For asking for help: the builds, Omarchy's version, the settings you changed, and the " +
              "service's last 50 log lines. Never what was said or answered, a key, a folder's contents " +
              "or a URL's path; your home folder is written ~."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      Row {
        spacing: Style.space(8)
        ActionButton {
          objectName: "showReport"
          text: page.reportShown ? "Hide" : "Show"
          bordered: true
          focusable: true
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          tooltipText: "Show here exactly what Copy puts on the clipboard"
          onClicked: page.showReport()
        }
        ActionButton {
          objectName: "copyDiagnostics"
          text: copier.running ? "Copying…" : "Copy"
          iconText: "\u{f018f}"
          bordered: true
          focusable: true
          enabled: !copier.running
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onClicked: page.copyDiagnostics()
        }
      }
    }
    Rectangle {
      width: parent.width
      visible: page.reportShown
      height: visible ? reportView.implicitHeight + Style.space(16) : 0
      radius: Style.space(6)
      color: page.s.faint
      Text {
        id: reportView
        x: Style.space(8)
        y: Style.space(8)
        width: parent.width - Style.space(16)
        wrapMode: Text.WrapAnywhere
        textFormat: Text.PlainText
        text: page.reportText !== "" ? page.reportText : "Reading…"
        color: page.s.foreground
        font.family: "monospace"
        font.pixelSize: Style.font.caption
      }
    }

    // Updates: one question to one remote, named, only on a click.
    SettingRow {
      width: parent.width
      label: "Check for updates"
      hint: updater.running ? "Asking…"
            : page.update ? page.update.message + (page.update.remote !== ""
                                                   ? " (asked " + page.update.remote + (page.update.url !== "" ? ", " + page.update.url : "") + ")" : "")
            : "Asks the remote this copy was installed from for its newest commit. Nothing is sent but that question, and only when you click."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      ActionButton {
        objectName: "checkUpdates"
        text: updater.running ? "Checking…" : "Check"
        bordered: true
        focusable: true
        enabled: !updater.running
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.checkUpdates()
      }
    }

    // Master plan M28: the first-run walk-through, on demand. It starts
    // from what is set now and writes only what is changed in it, so running
    // it on a working install changes nothing unless you change something.
    SettingRow {
      width: parent.width
      label: "Run setup again"
      hint: "The four steps a fresh install opens with: microphone, wake word, your agent, done. " +
            "Each starts from what is set now; skipping changes nothing."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      ActionButton {
        objectName: "runSetup"
        text: "Run setup"
        bordered: true
        focusable: true
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.s.runSetup("mic")
      }
    }
  }

  Card {
    width: parent.width
    title: "Runs here, and what goes out"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: "Hearing the wake word, turning speech into text and speaking the replies all happen on " +
            "this machine. What you say to an agent goes to wherever that agent runs."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Repeater {
      model: page.reach ? page.reach.local : []
      InfoRow {
      foreground: page.s.foreground; urgent: page.s.urgent; dim: page.s.dim; fontFamily: page.s.fontFamily
        required property var modelData
        label: modelData.what
        value: modelData.how + " · on this machine"
      }
    }
    Repeater {
      model: page.reach ? page.reach.backends : []
      InfoRow {
      foreground: page.s.foreground; urgent: page.s.urgent; dim: page.s.dim; fontFamily: page.s.fontFamily
        required property var modelData
        label: modelData.label
        value: (modelData.where === "local" ? "local" : "cloud") + " · " + page.statusText(modelData)
               + (modelData.used_by.length ? " · used by " + modelData.used_by.join(", ") : "")
        ok: modelData.status !== "not found" || modelData.used_by.length === 0
      }
    }
    Text {
      width: parent.width
      visible: !page.reach
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: page.needsRepair
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: "Installed means its program was found; it does not mean it is signed in. A turn " +
            "answered here is the only thing counted as working."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }

    SettingRow {
      width: parent.width
      label: "Models on this machine"
      hint: prober.running ? "Looking…"
            : page.probe === null ? "Asks 127.0.0.1 whether Ollama (port 11434) or llama.cpp's server (port 8080) is answering. Only when you click."
            : page.probe.length === 0 ? page.needsRepair
            : page.probe.map(function(p) {
                return p.label + ": " + (p.status === "answering" ? "answering, " + p.models + (p.models === 1 ? " model" : " models")
                                         : p.status === "other" ? "something answers on port " + p.port + ", not in the shape expected"
                                         : "nothing on port " + p.port)
              }).join(" · ") + ". Answering is not the same as an agent using it."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      ActionButton {
        objectName: "probeLocal"
        text: prober.running ? "Looking…" : "Look"
        bordered: true
        focusable: true
        enabled: !prober.running
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.probeLocal()
      }
    }
  }

  Card {
    width: parent.width
    title: "Voice commands"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: !page.commandTable ? "Reading the commands…"
            : "Wake phrases: " + page.commandTable.wake_phrases.map(function(w) {
                return "“" + w.phrase + "” for " + w.label }).join(", ") +
              ". Where a command counts in a sentence follows Conversation → Voice commands."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Repeater {
      model: page.commandTable ? page.commandTable.commands : []
      Column {
        required property var modelData
        width: parent ? parent.width : 0
        spacing: Style.space(2)
        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          textFormat: Text.PlainText
          text: modelData.label + "  ·  " + page.whereText(modelData) + (modelData.needs_wake ? "" : " · no wake word needed")
          color: page.s.foreground
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
        }
        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          textFormat: Text.PlainText
          text: modelData.effect
          color: page.s.dim
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          textFormat: Text.PlainText
          text: modelData.phrases.map(function(p) { return "“" + p + "”" }).join("  ")
          color: page.s.dim
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
          font.italic: true
        }
      }
    }
  }

  Card {
    width: parent.width
    title: "Changes, license, README"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    Text {
      objectName: "changelogTop"
      width: parent.width
      visible: page.changelogTop !== ""
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      maximumLineCount: 14
      elide: Text.ElideRight
      text: page.changelogTop
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Flow {
      width: parent.width
      spacing: Style.space(8)
      Repeater {
        model: [
          { name: "CHANGELOG.md", label: "Changelog" },
          { name: "LICENSE", label: "License (MIT)" },
          { name: "README.md", label: "README" }
        ]
        ActionButton {
          required property var modelData
          text: modelData.label
          bordered: true
          focusable: true
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          tooltipText: "Open it, read only, in a terminal"
          onClicked: page.openDoc(modelData.name)
        }
      }
    }
  }
}
