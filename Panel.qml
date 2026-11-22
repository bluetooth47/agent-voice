import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
// Namespaced as well: on Qt 6.12 a bare `Color` resolves to QtQuick's own
// value-type helper, not to the theme, and every colour read through it was
// undefined. Omarchy's own QML writes Commons.Color for the same reason.
import qs.Commons as Commons
import qs.Ui
import "ui"

// Agent Voice bar widget: one icon, one panel, one switch.
//
// The icon's whole job is principle 3 -- you own the mic. Linux gives us no
// OS-level microphone gate, so a wake word means something is listening
// continuously and the only honest answer is to make that impossible to miss.
// Recording is drawn in the urgent colour; released is dimmed.
//
// The id is `voice`, not `root`. A Component assigned to one of PanelHero's
// properties is instantiated in PanelHero's context, where `root` resolves to
// PanelHero -- so anything reaching back into this file has to do it through a
// name PanelHero does not also use.
Panel {
  id: voice
  moduleName: "duaneoca.agentvoice"
  ipcTarget: "duaneoca.agentvoice"

  // The bar sizes each widget from its implicit size. Without these the slot
  // is allocated 0x0, the icon anchors to nothing, and the widget is simply
  // absent -- no warning, no error, nothing in the log.
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  // --- Theme ------------------------------------------------------------------
  readonly property color fg: bar ? bar.foreground : Commons.Color.foreground
  readonly property color urgent: bar ? bar.urgent : Commons.Color.urgent
  // Translucent rather than Qt.darker: darker is dimmer only on a dark
  // theme, and on a light one made every hint as black as the label.
  readonly property color dim: Qt.rgba(fg.r, fg.g, fg.b, 0.6)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

  // --- Daemon state -----------------------------------------------------------
  property bool serviceActive: false
  property bool busy: false
  // The last reason a switch did nothing. Empty when there is nothing to say.
  // It exists because "the switch won't go on and there is no indication as
  // to why" was a real report, and silence is the worst answer a control can
  // give: the user cannot tell a broken install from a broken switch.
  property string note: ""
  property string vState: "off"
  // The open microphone (agentvoice open-mic, or "keep listening"): who it
  // is open for and until when, from the daemon. Empty when it is closed.
  property var openMic: ({})
  readonly property bool openMicOn: serviceActive && openMic.until !== undefined
  property real nowMs: Date.now()
  readonly property int openMicMinutes: openMicOn
    ? Math.max(1, Math.ceil((Number(openMic.until) * 1000 - nowMs) / 60000)) : 0
  Timer {
    interval: 15000
    repeat: true
    running: voice.openMicOn
    triggeredOnStart: true
    onTriggered: voice.nowMs = Date.now()
  }
  property string lastTranscript: ""
  property int lastMs: 0
  property real lastAudioS: 0
  // From the moment you stopped talking to the first word back; 0 until a
  // turn has got that far. The wait people actually notice.
  property int lastLatencyMs: 0
  property string lastReply: ""
  // Whose turn the readout is showing, with more than one agent.
  property string lastWho: ""
  // The collaboration line for the HUD (Phase 15); "" when nothing is passing.
  // Also why an agent had to start a new chat (phase M2), when nothing is.
  property string collabLine: ""
  // The microphone is muted even though the state names something else:
  // an agent answering a typed turn, or a reply that kept playing (M2).
  property bool micMuted: false
  readonly property bool micOff: vState === "off" || micMuted
  // Which listening window "followup" is: "open" for the open microphone,
  // "followup" after a reply (M2), "undo" for the seconds after "…, stop
  // listening" in which "no" puts the open mic back (M4: open mic is off
  // then, so it reads STILL LISTENING). "" from a daemon that does not say.
  property string vWindow: ""

  // --- the readout (phase M3) ---------------------------------------------------
  // The agent's previous answer, while the turn under way has none of its
  // own yet (the wake word clears `reply`). The daemon keeps it and says
  // when it is gone (readout.py); whether it is drawn is hudKeepReply.
  property string lastKept: ""
  // The payload is the readout's preview, not a turn (readout.py).
  property bool vPreview: false
  // LAST HEARD unfolded by its "more". Here, not on the section: the close
  // handler below cannot reach an id inside the panel's loaded content.
  property bool lastExpanded: false
  // Locked: two fixed lines, the same height every turn. Anything but
  // "dynamic" is locked, so an unreadable value gets the steady one.
  readonly property bool readoutLocked: voice.pref("hudSize", "locked") !== "dynamic"
  readonly property bool keepReply: voice.pref("hudKeepReply", true) !== false
  // small / medium / large; medium is the bar's own body size.
  readonly property real readoutScale: {
    var v = voice.pref("hudTextSize", "medium")
    return v === "small" ? 0.85 : v === "large" ? 1.25 : 1.0
  }
  // The top line: this turn's answer, else the kept one.
  readonly property string readoutReply: voice.lastReply !== "" ? voice.lastReply
                                         : voice.keepReply ? voice.lastKept : ""

  readonly property bool live: serviceActive && vState !== "off"

  // Quote one argument for a shell: the floating-terminal launcher takes a
  // command line, not an argv, so everything handed to it is shell source.
  function shq(s) {
    return "'" + String(s).replace(/'/g, "'\\''") + "'"
  }

  readonly property string configHome:
      Quickshell.env("XDG_CONFIG_HOME")
      || ((Quickshell.env("HOME") || "") + "/.config")

  readonly property string icon: {
    if (!serviceActive) return "󰍭"              // mic off
    if (vState === "locked") return "󰍭"         // closed while the screen is locked
    if (vState === "capture" || vState === "followup") return "󰑊"  // recording you
    if (vState === "transcribing") return "󰗊"   // turning speech into text
    if (vState === "thinking") return "󰔟"
    if (vState === "speaking") return "󰕾"
    if (vState === "listening") return "󰍬"
    if (vState === "off") return "󰍭"           // running, microphone released
    if (vState === "yielded") return "󰍭"       // lent to another app
    return "󰍭"
  }

  readonly property color barIconColor: {
    if (vState === "capture" && serviceActive)
      return bar ? bar.urgent : Commons.Color.urgent
    // Its own colour, the whole time it is open: listening without the wake
    // word is the thing you most need to know is happening.
    if (openMicOn) return Commons.Color.accent
    if (vState === "followup" && serviceActive)
      return bar ? bar.urgent : Commons.Color.urgent
    if (live) return barForeground
    return Qt.darker(barForeground, 1.55)
  }

  readonly property string stateLabel: {
    if (!serviceActive) return "OFF"
    // Its own state rather than OFF, because OFF invites you to switch it
    // back on and then wonder why nothing happens.
    if (vState === "locked") return "CLOSED WHILE LOCKED"
    if (vState === "capture") return "LISTENING TO YOU"
    // Still hot after a reply, waiting to see if you carry on.
    if (vState === "followup" && openMicOn && vWindow !== "followup")
      return "OPEN MIC · " + String(openMic.who || "").toUpperCase() + " · "
             + openMicMinutes + " MIN LEFT"
    if (vState === "followup") return "STILL LISTENING"
    // These were one state called "thinking", labelled "TRANSCRIBING" -- which
    // described the shorter half and then sat there through the longer one.
    if (vState === "transcribing") return "TRANSCRIBING"
    if (vState === "thinking") return "THINKING"
    if (vState === "speaking") return "SPEAKING"
    if (vState === "listening") return "WAITING FOR \"" + voice.activePhrase.toUpperCase() + "\""
    // The service is up and the microphone is released: the mic keybind, the
    // panic key, a right click on the bar, or the panel's own icon. Its own
    // label because it fell through to the default and read "STARTING"
    // forever -- a running daemon describing itself as still starting.
    if (vState === "off") return "MICROPHONE OFF"
    // Named rather than folded into MICROPHONE OFF, because this one undoes
    // itself and the other does not: nothing here is waiting for you to click
    // anything.
    if (vState === "yielded") return "ANOTHER APP IS RECORDING"
    return "STARTING"
  }

  // --- Settings ---------------------------------------------------------------
  // Both engines keep their own phrase key, and the inactive one stays in
  // shell.json rather than being cleared -- so switching to openWakeWord left
  // the panel announcing the Vosk phrase it was no longer listening for.
  // Everything user-facing reads activePhrase, never the raw keys.
  readonly property string engine: setting("engine", "vosk")
  readonly property bool usingOww: engine === "openwakeword"
  readonly property string phrase: setting("phrase", "hey computer")
  readonly property string owwModel: setting("owwModel", "hey_jarvis")
  readonly property string activePhrase:
      usingOww ? owwModel.replace(/_/g, " ") : phrase
  // Only what the panel actually shows. Every other knob is edited on the
  // settings page, and the copies that used to live here were worse than
  // unused: the check script read this file too when deciding whether a
  // declared setting was drawn anywhere, so a dead `setting("leadInMs", ...)`
  // here kept the check green after the real control was deleted.
  readonly property string voiceName: setting("voice", "lessac-medium")
  readonly property string model: setting("model", "tiny.en")
  readonly property bool speakReplies: setting("speakReplies", true)

  // The switch runs the service; `mic` only releases the microphone while
  // leaving the daemon up, which is the cheap panic button on right-click.
  // Why this is the guard rather than the switch: there are three ways in.
  // The panel's switch is one; the bar icon's middle click and its right
  // click are the other two, and hiding the switch did nothing about either.
  // A guard on one entry point is not a guard.
  // Release or re-engage the microphone, leaving the service alone. Shared by
  // the bar icon's right click and the panel's icon, so both get the same
  // guard and the same refusal -- the right click used to reach the Process
  // directly, which meant no check that `agentvoice` was even there.
  function toggleMic() {
    if (!voice.engineInstalled) {
      voice.note = "The voice engine is not installed yet."
      if (!voice.opened) voice.open()
      return
    }
    // Nothing to mute when nothing is listening; the switch is that control.
    if (!voice.serviceActive) return
    voice.note = ""
    micToggle.running = true
  }

  //: Whether there is a turn to stop. The three states in which the daemon is
  //: either listening to you, working, or talking -- which is exactly when a
  //: stop means something. `_on_interrupt` in the daemon checks the same list
  //: and does nothing outside it, so a control shown at any other moment
  //: would be a button that silently does nothing.
  //: Not during the readout's preview (phase M3): its `speaking` is four
  //: seconds of sample text, and STOP would interrupt nothing -- or, with
  //: collaboration work queued, cancel it (Codex review).
  readonly property bool vTurnRunning: serviceActive && !vPreview
                                       && (vState === "speaking"
                                           || vState === "thinking"
                                           || vState === "transcribing")

  // Stop whatever is happening: the reply being spoken, the agent's turn, and
  // every process the agent started -- `agentvoice interrupt` reaches the
  // process group, not just the CLI.
  //
  // Two ways in, so one guard: the panel's STOP and a left click on the bar
  // icon. The second exists because that is what somebody actually did -- "it
  // was rambling on, I clicked the icon, and it didn't work" -- since a left
  // click opened the panel and nothing else.
  function stopTurn() {
    if (!voice.engineInstalled) {
      voice.note = "The voice engine is not installed yet."
      if (!voice.opened) voice.open()
      return
    }
    // Nothing to stop. Deliberately silent rather than a note: the daemon
    // treats an interrupt outside a turn as a no-op for the same reason, so
    // a stray click cannot leave things in a state nobody asked for.
    if (!voice.vTurnRunning) return
    voice.note = ""
    interrupt.running = true
  }

  function toggleService() {
    if (!voice.engineInstalled) {
      // Nothing to toggle, and the panel is where that is explained -- it
      // carries the offer, the size, and the button. Opening it beats any
      // message this could invent, and beats the silence it used to give.
      voice.note = "The voice engine is not installed yet."
      if (!voice.opened) voice.open()
      return
    }
    voice.note = ""
    voice.busy = true
    switcher.command = ["agentvoice", "toggle"]
    switcher.running = true
  }

  Process {
    id: switcher
    // Set by onExited, which a spawn that never started does not emit. It is
    // how a failed spawn is told apart from a command that ran and returned
    // something -- the difference between "the engine is gone" and "systemd
    // refused", and the user is owed one of those rather than nothing.
    property bool exited: false
    onExited: exited = true
    // Not onExited. A spawn that never started -- `agentvoice` not on PATH,
    // because the engine is a second install -- does not emit it: measured
    // with a Process against a missing binary, which logs "failed to start",
    // sets running back to false, and never exits. And onExited was the only
    // thing clearing `busy`, which ToggleSwitch uses to swallow further
    // clicks. So one click on the switch before the engine was installed
    // left busy true for the life of the plugin instance, and the switch
    // ignored every click afterwards -- including after a successful
    // install, which is exactly when someone tries it again.
    //
    // `running` goes false in both cases, after onExited on a real exit and
    // on its own when the spawn failed, so it is the signal that cannot be
    // missed.
    onRunningChanged: if (!running) {
      voice.busy = false
      if (!exited)
        voice.note = "Could not run `agentvoice`. The engine may have been removed."
      exited = false
      probe.running = true            // re-read the truth rather than assume
    }
  }

  Process { id: micToggle; command: ["agentvoice", "mic"] }
  Process { id: openMicToggle; command: ["agentvoice", "open-mic", "off"] }
  function toggleOpenMic() {
    if (!voice.serviceActive) return
    openMicToggle.command = voice.openMicOn ? ["agentvoice", "open-mic", "off"]
                                            : ["agentvoice", "open-mic", "on"]
    openMicToggle.running = true
  }
  Process { id: interrupt; command: ["agentvoice", "interrupt"] }

  // Typed messages. The text goes over stdin, never argv: /proc/<pid>/cmdline
  // is readable by every account on the machine. One line, ended by the
  // newline, so the CLI does not wait for an end of file.
  property string typeTarget: ""          // agent id; "" is the main agent
  readonly property string typeTargetLabel: {
    if (voice.typeTarget === "") return voice.mainLabel
    var e = voice.crewEntry(voice.typeTarget)
    return e && e.name ? voice.agentLabel(e) : voice.mainLabel
  }
  function nextTypeTarget() {
    var ids = [""].concat(voice.crew.map(function(a) { return voice.agentId(a) }))
    var i = ids.indexOf(voice.typeTarget)
    voice.typeTarget = ids[(i + 1) % ids.length]
  }
  property var typedQueue: []
  function sendTyped(t) {
    voice.typedQueue = voice.typedQueue.concat([{ to: voice.typeTarget || "main", text: t }])
    if (!typer.running) voice.sendNextTyped()
  }
  function sendNextTyped() {
    if (voice.typedQueue.length === 0) return
    var next = voice.typedQueue[0]
    voice.typedQueue = voice.typedQueue.slice(1)
    typer.pending = next.text.replace(/[\r\n]+/g, " ")
    typer.command = ["agentvoice", "type", next.to, "--line"]
    typer.running = true
  }
  Process {
    id: typer
    property string pending: ""
    stdinEnabled: true
    onStarted: { write(typer.pending + "\n"); typer.pending = "" }
    onExited: voice.sendNextTyped()
  }

  // What the agent is pointed at, and how much it may do there. On the panel
  // rather than behind the gear because it is the thing to check *before*
  // speaking -- what am I about to change, and can it act without asking.
  readonly property string projectDir: voice.setting("projectDir", "")
  // Agent, level and posture come from the daemon's state file rather than
  // from shell.json: what a level *means* depends on what the running agent
  // can honour, and only the daemon knows that. Keeping a second copy here
  // is how a screen ends up promising a guarantee that is not in force.
  property string vAgent: ""
  property string permissionLevel: "ask"
  property string vPosture: ""
  // Shown because conversation mode fails quietly on a backend that does
  // not remember: the window opens, it listens, it answers, and every turn
  // starts from nothing.
  property bool vRemembers: true
  // Non-empty when an endpoint is configured and is answering instead of
  // the agent chosen in Omarchy's settings.
  property string vOverriding: ""
  // False when the project and permission settings do not reach the running
  // backend, because it acts somewhere we do not control.
  property bool vGoverned: true
  readonly property string projectLabel: {
    var d = String(voice.projectDir).trim()
    // Said in words: a bare "~" read as a stray mark.
    if (d === "" || d === "~") return "your home folder"
    var home = Quickshell.env("HOME") || ""
    if (home !== "" && d.indexOf(home) === 0) return "~" + d.slice(home.length)
    return d
  }
  // What the main agent may do, and where, in words: its chip's tooltip
  // (phase M3). The popup's own level picker is gone -- permissions are per
  // agent, set on the Agents page -- but what is in force stays one hover
  // away, because it is the thing to check before speaking.
  readonly property string mainPosture:
    (voice.vGoverned ? "in " + voice.projectLabel + " · " : "")
    + (voice.vPosture !== "" ? voice.vPosture
       : voice.permissionLevel === "trusted" ? "nothing is asked"
       : voice.permissionLevel === "edits" ? "edits without asking, asks for commands"
       : "asks before every change")
    + (voice.vRemembers ? "" : " · does not remember")
    + (voice.vOverriding === "" ? "" : " · instead of " + voice.vOverriding)

  // systemd is the authority on whether the daemon exists; the state file only
  // says what it is doing. Both are needed: a stale state file outlives a
  // crashed daemon, and would otherwise leave the switch stuck on.
  // The daemon is a separate install: the widget arrives with `omarchy
  // plugin add`, the engine behind it is a few hundred megabytes and does
  // not. Rather than show a dead switch, ask.
  property bool engineInstalled: true
  Process {
    id: enginePresent
    command: ["bash", "-c", "command -v agentvoice >/dev/null && echo yes || echo no"]
    stdout: StdioCollector {
      onStreamFinished: {
        var found = String(text).trim() === "yes"
        // An engine that has arrived makes the complaint about it stale, and
        // a message that outlives its cause is its own bug.
        if (found && !voice.engineInstalled) voice.note = ""
        voice.engineInstalled = found
      }
    }
  }
  // The command is set at the call site, which knows the plugin's path.
  Process { id: installer }

  Process {
    id: probe
    command: ["agentvoice", "is-active"]
    stdout: StdioCollector {
      onStreamFinished: voice.serviceActive = String(text).trim() === "yes"
    }
  }

  Timer {
    interval: 2000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: {
      if (!enginePresent.running) enginePresent.running = true
      // Only probe a command that is on PATH. Quickshell logs a warning for
      // every spawn of a missing binary, so a half-removed engine otherwise
      // writes to the journal twice a second for as long as the bar runs --
      // which is how the broken uninstall was found.
      if (voice.engineInstalled) {
        if (!probe.running) probe.running = true
      } else {
        voice.serviceActive = false
      }
      // A watch never attaches to a file that was not there, and on a first
      // install it is not: the widget arrives with `plugin add`, the daemon
      // minutes later. Without this retry the panel reads "off" from a
      // failed load, the service starts, and the label sits on STARTING
      // until the shell is restarted. Only fires while actually stuck.
      if (voice.serviceActive && voice.vState === "off") stateFile.reload()
    }
  }

  FileView {
    id: stateFile
    path: (Quickshell.env("XDG_RUNTIME_DIR") || "/run/user/1000") + "/agentvoice/state"
    watchChanges: true
    printErrors: false
    // text() is stale inside the change signal, so route every path through
    // reload -> onLoaded and always parse fresh content.
    onFileChanged: stateFile.reload()
    onLoadFailed: voice.vState = "off"
    onLoaded: {
      try {
        var d = JSON.parse(text())
        voice.vState = String(d.state || "off")
        if (d.transcript !== undefined) voice.lastTranscript = String(d.transcript)
        if (d.ms !== undefined) voice.lastMs = Math.round(d.ms)
        if (d.audio_s !== undefined) voice.lastAudioS = d.audio_s
        if (d.latency_ms !== undefined) voice.lastLatencyMs = Math.round(d.latency_ms)
        // Drawn on the panel's level meter; absent when nothing is listening.
        voice.levelDb = d.level_db !== undefined ? d.level_db : -99
        if (d.gate_db !== undefined) voice.gateDb = d.gate_db
        voice.agentLive = (d.live && typeof d.live === "object") ? d.live : ({})
        if (d.reply !== undefined) voice.lastReply = String(d.reply)
        // Only with a reply field: a payload that does not speak about the
        // exchange (a level update) must not blank the kept answer.
        if (d.reply !== undefined)
          voice.lastKept = d.last_reply !== undefined ? String(d.last_reply) : ""
        // A lock takes both lines off at once, here as well as in the
        // daemon: a locked payload carries no text, and a field that is not
        // sent keeps its old value on screen.
        if (voice.vState === "locked") {
          voice.lastTranscript = ""
          voice.lastReply = ""
          voice.lastKept = ""
        }
        // Absent with a single agent, and then cleared rather than kept: a
        // name left over from when there were several would be wrong.
        voice.lastWho = d.who_label !== undefined ? String(d.who_label) : ""
        // A task list with no line yet publishes collab as "": the notice
        // shows then too (Codex review of M2).
        voice.collabLine = d.collab ? String(d.collab)
                         : d.notice ? String(d.notice) : ""
        voice.micMuted = d.muted === true
        voice.vWindow = d.window !== undefined ? String(d.window) : ""
        // After vState, on purpose: the HUD reads it when its `busy` turns
        // false, to close a preview without the turn's linger.
        voice.vPreview = d.preview === true
        if (d.agent !== undefined) voice.vAgent = String(d.agent)
        if (d.level !== undefined) voice.permissionLevel = String(d.level)
        if (d.posture !== undefined) voice.vPosture = String(d.posture)
        if (d.remembers !== undefined) voice.vRemembers = (d.remembers === true)
        if (d.overriding !== undefined) voice.vOverriding = String(d.overriding)
        voice.openMic = (d.open_mic && typeof d.open_mic === "object") ? d.open_mic : ({})
        if (d.governed !== undefined) voice.vGoverned = (d.governed === true)
      } catch (e) {
        voice.vState = "off"
      }
    }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: voice.bar
    text: voice.icon
    fontFamily: voice.bar ? voice.bar.fontFamily : Style.font.family
    foreground: voice.barIconColor
    tooltipText: voice.opened ? "" : "Agent Voice — " + voice.stateLabel
    // WidgetButton emits pressed(buttonCode); there is no onClicked.
    // A left click always opens the popup, turn or no turn. It used to stop
    // the turn, which meant a click meant to look at what it was doing ended
    // it. The popup's STOP is one more click, and "full stop" and the wake
    // word still stop everything hands-free.
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.RightButton) {
        if (voice.serviceActive) voice.toggleMic()
        else voice.toggleService()
      } else if (buttonCode === Qt.MiddleButton) {
        voice.toggleService()
      } else {
        voice.toggle()
      }
    }
  }

  // A readout while it works, in its own layer-shell surface. Not the panel
  // below: that one is a KeyboardPanel and takes keyboard focus on every open,
  // which for a hands-free interface would mean roughly 25 seconds of typing
  // going to a status display after every utterance.
  Hud {
    bar: voice.bar
    fontFamily: voice.fontFamily
    enabled: voice.serviceActive && voice.setting("hud", true) === true
    lingerMs: voice.setting("hudLingerMs", 2000)
    vState: voice.vState
    stateLabel: voice.stateLabel
    icon: voice.icon
    accent: voice.barIconColor
    // Straight through. The daemon clears both at the wake word now, so there
    // is nothing here to paper over -- and the version that did only blanked
    // the transcript, which left the previous *answer* on screen while it
    // listened for the next question.
    transcript: voice.lastTranscript
    reply: voice.lastReply
    who: voice.lastWho
    collab: voice.collabLine
    // phase M3: the previous answer while this turn has none (hudKeepReply),
    // the size, the edge it sits at and its text size.
    keptReply: voice.keepReply ? voice.lastKept : ""
    locked: voice.readoutLocked
    position: voice.pref("hudPosition", "top") === "bottom" ? "bottom" : "top"
    textScale: voice.readoutScale
    preview: voice.vPreview
    // A click on the readout opens the whole conversation -- the answer to
    // "the popup is too small" for anything longer than a glance.
    onOpenConversation: conversation.running = true
  }

  // --- what the popup adds -----------------------------------------------------
  // The popup used to show a switch, a state line and the last thing heard,
  // with "settings" and "conversation" as two caption-sized words in the
  // corner: nothing to change, nothing to pick, and no sign of which of your
  // agents was doing what. Now: the microphone level, a stop button big
  // enough to find in a hurry, every agent and what it is doing, the five
  // switches people flip day to day and the voice. Everything else stays in
  // the overlay -- the main agent's permission level included since M3: it
  // is set per agent, on the Agents page, and the popup's copy was a second
  // way to promote an agent to "trusted" (feedback item 2, bug D).

  property real levelDb: -99
  // The gate in use, when it follows the room; see Settings.gateInForce.
  property real gateDb: NaN
  // name -> what that agent is doing, with more than one agent.
  property var agentLive: ({})

  // One copy of the settings for the popup's own controls, so a switch shows
  // its new position the moment it is clicked instead of after shell.json
  // comes back (ui/SettingsStore). Reads fall through to the bar's own
  // `settings` until the store has loaded.
  SettingsStore { id: store }
  function pref(key, fallback) {
    return store.loaded ? store.get(key, fallback) : voice.setting(key, fallback)
  }

  // Omarchy's default agent, from the file `omarchy default agent` writes,
  // so the main agent has a name while the service is stopped.
  property string defaultAgent: ""
  FileView {
    id: defaultAgentFile
    path: voice.configHome + "/omarchy/defaults/agent"
    watchChanges: true
    printErrors: false
    onFileChanged: defaultAgentFile.reload()
    onLoaded: voice.defaultAgent = String(text()).trim()
    onLoadFailed: voice.defaultAgent = ""
  }
  // What the daemon runs, else what it will run: its own choice, else Omarchy's.
  readonly property string mainAgent: vAgent !== "" ? vAgent
                                      : (String(pref("mainProgram", "")) || defaultAgent)
  // As the settings name them; the same list as Settings.programOptions.
  function programLabel(value) {
    var names = { claude: "Claude Code", codex: "Codex", gemini: "Gemini",
                  agy: "Antigravity", copilot: "Copilot",
                  endpoint: "Endpoint" }
    return names[value] || value
  }
  readonly property bool usingEndpoint: String(pref("endpointUrl", "")) !== ""
                                        && String(pref("endpointModel", "")) !== ""
  // Agents switched off on their card have no chip here: they can't be
  // woken, so offering them would be offering nothing.
  readonly property var crew: {
    var v = pref("voiceAgents", [])
    return Array.isArray(v) ? v.filter(function(a) { return (a || {}).enabled !== false }) : []
  }
  // As Settings.agentId / agentLabel: ids for lookups, names for reading.
  function agentId(a) {
    var raw = typeof (a || {}).id === "string" ? a.id.trim() : ""
    if (/^[a-z0-9][a-z0-9-]{0,47}$/.test(raw) && raw !== "main") return raw
    var slug = String((a || {}).name || "").toLowerCase().replace(/[^a-z0-9]+/g, "-")
                 .replace(/^-+|-+$/g, "").slice(0, 48).replace(/-+$/g, "")
    return slug === "main" ? "agent-main" : slug
  }
  function capitalised(phrase) {
    return String(phrase || "").split(" ").map(function(w) {
      return w.charAt(0).toUpperCase() + w.slice(1) }).join(" ")
  }
  function cleanLabel(text) {
    return String(text || "").replace(/\s+/g, " ").replace(/[\u0000-\u001f\u007f]/g, "").trim().slice(0, 40).trim()
  }
  function agentLabel(a) {
    return cleanLabel((a || {}).label) || capitalised(String((a || {}).name || ""))
  }
  function crewEntry(id) {
    for (var i = 0; i < voice.crew.length; i++)
      if (voice.agentId(voice.crew[i]) === id) return voice.crew[i]
    return ({})
  }
  readonly property string mainLabel: cleanLabel(pref("mainName", "")) || capitalised(voice.activePhrase)

  function agentState(name) {
    if (!voice.serviceActive) return "off"
    var live = voice.agentLive || {}
    // By id; "" is the main agent, which has its own entry with several.
    if (live[name] !== undefined) return String(live[name])
    if (name === "" && Object.keys(live).length === 0) {
      if (vState === "thinking" || vState === "speaking" || vState === "transcribing") return vState
    }
    if (vState === "locked" || vState === "off" || vState === "yielded") return "paused"
    return "idle"
  }

  readonly property var voiceOptions: [
    { label: "Lessac — female", value: "lessac-medium" },
    { label: "Lessac — female, low", value: "lessac-low" },
    { label: "Amy — female", value: "amy-medium" },
    { label: "Ryan — male", value: "ryan-medium" },
    { label: "Joe — male", value: "joe-medium" },
    { label: "HFC — male", value: "hfc_male-medium" }
  ]

  // The five switches flipped day to day. Each is also on its page in the
  // overlay; these write the same keys through the same store.
  readonly property var quickToggles: [
    { key: "speakReplies",     label: "Speak replies",  icon: "\u{f057e}", fallback: true },
    { key: "conversationMode", label: "Keep listening", icon: "\u{f0b79}", fallback: true },
    { key: "hud",              label: "Readout",        icon: "\u{f0379}", fallback: true },
    { key: "chimes",           label: "Chimes",         icon: "\u{f009a}", fallback: true },
    { key: "bargeOnHeadset",   label: "Headset interrupt", icon: "\u{f02cb}", fallback: true }
  ]

  // --- keyboard ---------------------------------------------------------------
  // One cursor over the actionable things, in reading order, the way
  // Omarchy's own panels move: j/k or the arrows, Enter to act, Esc to close.
  property bool cursorActive: false
  property int cursor: 0
  readonly property var targets: {
    var out = []
    if (voice.engineInstalled) out.push("service")
    if (voice.serviceActive) out.push("mic")
    if (voice.vTurnRunning) out.push("stop")
    out.push("agent:")
    for (var c = 0; c < voice.crew.length; c++) out.push("agent:" + voice.agentId(voice.crew[c]))
    for (var i = 0; i < voice.quickToggles.length; i++) out.push("toggle:" + voice.quickToggles[i].key)
    if (voice.serviceActive) out.push("openmic")
    out.push("conversation")
    out.push("settings")
    return out
  }
  function cursorOn(name) { return voice.cursorActive && voice.targets[voice.cursor] === name }
  function moveCursor(d) {
    if (!voice.cursorActive) { voice.cursorActive = true; return }
    voice.cursor = Math.max(0, Math.min(voice.targets.length - 1, voice.cursor + d))
  }
  function activate(name) {
    if (name === "service") voice.toggleService()
    else if (name === "mic") voice.toggleMic()
    else if (name === "stop") voice.stopTurn()
    else if (name === "openmic") voice.toggleOpenMic()
    else if (name === "conversation") { conversation.running = true; voice.close() }
    else if (name === "settings") voice.summon({})
    else if (name.indexOf("agent:") === 0)
      voice.summon({ page: "agents", agent: name.slice(6) === "" ? "main" : name.slice(6) })
    else if (name.indexOf("toggle:") === 0) {
      var key = name.slice(7)
      store.set(key, !(voice.pref(key, true) === true))
    }
  }
  onTargetsChanged: if (cursor >= targets.length) cursor = Math.max(0, targets.length - 1)
  onOpenedChanged: if (!opened) { cursorActive = false; lastExpanded = false }

  // Open the overlay, on a page: {"page": "agents", "agent": "sarah"}.
  function summon(payload) {
    summoner.command = ["omarchy-shell", "shell", "summon", "duaneoca.agentvoice",
                        JSON.stringify(payload || {})]
    summoner.running = true
    voice.close()
  }

  // A switch tile: icon and label, filled when on.
  component QuickToggle: Button {
    property string key: ""
    property bool on: false
    selected: on
    bordered: true
    leftAlign: true
    focusable: false
    foreground: voice.fg
    fontFamily: voice.fontFamily
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: voice
    bar: voice.bar
    open: voice.opened
    focusTarget: panel.loadedContent
    contentWidth: Style.space(400)
    contentHeight: panel.fittedContentHeight(panel.loadedContentHeight, Style.space(680))

    content: PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      implicitHeight: content.implicitHeight
      onMoveRequested: function(dx, dy) { voice.moveCursor(dy !== 0 ? dy : dx) }
      onActivateRequested: if (voice.cursorActive) voice.activate(voice.targets[voice.cursor])
      onCloseRequested: voice.close()
      onTabRequested: function(direction) { voice.switchPanel(direction) }
      onTextKey: function(t) {
        // m: the microphone, s: stop, the two things wanted in a hurry.
        if (t === "m" || t === "M") voice.toggleMic()
        else if (t === "s" || t === "S") voice.stopTurn()
      }

    Column {
      id: content
      width: parent.width
      spacing: Style.spacing.md

      // The switch lives in the hero because turning the thing on is the first
      // question anyone has when they open this panel.
      PanelHero {
        id: hero
        width: parent.width
        title: "Agent Voice"
        meta: voice.stateLabel
        foreground: voice.fg
        fontFamily: voice.fontFamily
        iconOpacity: voice.serviceActive ? 1.0 : 0.5

        iconComponent: Component {
          // Clickable, because the only ways to release the microphone were a
          // right click on the bar icon and a keybind, and neither announces
          // itself: the person this was built for had been stopping the whole
          // service and starting it again instead, not knowing either existed.
          Item {
            implicitWidth: glyph.implicitWidth
            implicitHeight: glyph.implicitHeight

            Text {
              id: glyph
              text: voice.icon
              color: voice.barIconColor
              font.family: voice.fontFamily
              font.pixelSize: Style.font.display
            }

            MouseArea {
              anchors.fill: parent
              // Only while something is listening. With the service down the
              // switch beside it is the control, and a second one that looks
              // identical and does nothing is worse than none.
              enabled: voice.serviceActive
              cursorShape: Qt.PointingHandCursor
              onClicked: voice.toggleMic()
            }
          }
        }

        trailingControl: Component {
          ToggleSwitch {
            // The offer below says the engine is a separate install and that
            // a switch which cannot turn anything on should not be shown.
            visible: voice.engineInstalled
            checked: voice.serviceActive
            busy: voice.busy
            hasCursor: voice.cursorOn("service")
            foreground: voice.fg
            onToggled: voice.toggleService()
          }
        }
      }

      // Why a switch did nothing, when it did nothing. Takes no space at all
      // the rest of the time, which is almost always: `note` is set only by
      // toggleService refusing, or by a spawn that never started.
      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        visible: voice.note !== "" || store.error !== ""
        text: voice.note !== "" ? voice.note : store.error
        // Untrusted only in the sense that everything shown here is, but the
        // rule in this file has no exceptions.
        textFormat: Text.PlainText
        color: voice.urgent
        font.family: voice.fontFamily
        font.pixelSize: Style.font.caption
      }

      // The engine is a separate, larger install. Offer it rather than
      // showing a switch that cannot turn anything on -- and say the size,
      // because consent to "install" and consent to "download 700MB and run
      // a background service" are not the same consent.
      Column {
        width: parent.width
        spacing: Style.space(6)
        visible: !voice.engineInstalled

        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          text: "The voice engine is not installed yet. It is about 700MB — " +
                "speech recognition, a voice, and the wake word — and runs as " +
                "a background service you can stop at any time. It does not " +
                "start itself after a reboot; that is one click each session, " +
                "on purpose."
          color: voice.dim
          font.family: voice.fontFamily
          font.pixelSize: Style.font.caption
        }

        Button {
          text: "Install the voice engine…"
          bordered: true
          fontFamily: voice.fontFamily
          onClicked: {
            // Quoted, and XDG_CONFIG_HOME rather than ~/.config: the launcher
            // runs this through `bash -c`, so a space in the path would split
            // it into two commands, and the plugin is not under ~/.config at
            // all on a machine that sets the variable.
            installer.command = ["omarchy-launch-floating-terminal-with-presentation",
                                 voice.shq(voice.configHome +
                                   "/omarchy/plugins/duaneoca.agentvoice/install.sh")]
            installer.running = true
            voice.close()
          }
        }
      }

      // --- the live strip ---
      // The microphone as a level, a mute that says what it does, and while
      // a turn runs, the stop button.
      Column {
        width: parent.width
        spacing: Style.space(8)
        visible: voice.serviceActive

        Row {
          width: parent.width
          spacing: Style.space(10)

          LevelMeter {
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - micButton.width - parent.spacing
            levelDb: voice.levelDb
            gateDb: voice.pref("adaptiveGate", false) === true && !isNaN(voice.gateDb)
                    ? voice.gateDb : voice.pref("micThresholdDb", -38)
            idleText: voice.vState === "yielded" ? "lent to another app — back when it stops"
                      : voice.vState === "locked" ? "closed while the screen is locked"
                      : voice.vState === "off" ? "microphone off" : ""
            foreground: voice.fg
            fontFamily: voice.fontFamily
          }
          Button {
            id: micButton
            anchors.verticalCenter: parent.verticalCenter
            text: voice.micOff ? "Unmute" : "Mute"
            iconText: voice.micOff ? "\u{f036d}" : "\u{f036c}"
            bordered: true
            hasCursor: voice.cursorOn("mic")
            foreground: voice.fg
            fontFamily: voice.fontFamily
            tooltipText: "Release the microphone and keep the service warm (m)"
            onClicked: voice.toggleMic()
          }
        }

        // Said where somebody who has just muted it will be looking. Only
        // then: a hint that is always on screen stops being read. Lent to
        // another app is different: nothing here is waiting for a click.
        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          visible: voice.micOff || voice.vState === "yielded"
          text: voice.vState === "yielded"
                ? "Listening again as soon as it stops."
                : "Unmute, or click the microphone above, to start listening again."
          textFormat: Text.PlainText
          color: voice.dim
          font.family: voice.fontFamily
          font.pixelSize: Style.font.caption
        }

        // Barge-in cannot work acoustically through speakers -- the
        // microphone sits beside them -- so stopping is an explicit act
        // there, and this is where somebody looks for it. It was once the
        // word "stop" in a caption colour; reported from use: "if I asked the
        // agent to do something very destructive by accident I might panic,
        // and I don't feel like I have a stop button." Full width, the
        // theme's alarm colour, and an octagon from the same icon set as the
        // bar icon. It kills the agent's whole process group, not just the
        // talking.
        //
        // Locked readout (phase M3): always in its place, dimmed and inert
        // between turns, because a button that comes and goes with every
        // turn bounces the popup as much as the last-heard lines did -- and
        // a stop button is better found where it always is.
        Button {
          width: parent.width
          visible: voice.vTurnRunning || voice.readoutLocked
          enabled: voice.vTurnRunning
          opacity: enabled ? 1.0 : 0.35
          // Says why it is inert, in its own fixed slot.
          text: !voice.vTurnRunning ? "STOP · nothing running"
                : "STOP" + (voice.lastWho !== "" ? "  " + voice.lastWho : "")
          iconText: "\u{f06d7}"
          bordered: true
          hasCursor: voice.cursorOn("stop")
          foreground: voice.urgent
          accent: voice.urgent
          fontFamily: voice.fontFamily
          fontSize: Math.round(Style.font.body * 1.15)
          onClicked: voice.stopTurn()
        }
      }

      // --- agents ---
      // One chip per agent: who, and what it is doing. A click opens that
      // agent's card in the overlay.
      Flow {
        id: chips
        width: parent.width
        spacing: Style.space(6)
        visible: voice.engineInstalled

        Repeater {
          // Ids; "" is the main agent.
          model: [""].concat(voice.crew.map(function(a) { return voice.agentId(a) }))
          Button {
            id: chip
            required property string modelData
            readonly property var entry: voice.crewEntry(modelData)
            readonly property string st: voice.agentState(modelData)
            readonly property bool busyNow: st === "thinking" || st === "speaking" || st === "transcribing"
            readonly property string name: modelData === "" ? voice.mainLabel : voice.agentLabel(entry)
            text: name + "  ·  " + st
            // Locked readout (phase M3): as wide as its longest state, so
            // "idle" turning into "transcribing" never rewraps the row of
            // chips onto another line. Elided past the popup's width; the
            // full name is in the tooltip.
            // Measured bold, as a busy chip draws, with a fixed allowance
            // for the icon, the same in every state (Codex review: a
            // proportional font near the wrap could still add a row).
            TextMetrics {
              id: chipNow
              font.family: voice.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: chip.selected
              text: chip.text
            }
            TextMetrics {
              id: chipWidest
              font.family: voice.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: true
              text: chip.name + "  ·  transcribing"
            }
            width: voice.readoutLocked
                   ? Math.min(chips.width, implicitWidth - chipNow.width + chipWidest.width
                                           + Style.space(4))
                   : Math.min(chips.width, implicitWidth)
            iconText: busyNow ? "\u{f0e4e}" : "\u{f06a9}"
            bordered: true
            selected: busyNow
            hasCursor: voice.cursorOn("agent:" + modelData)
            foreground: voice.fg
            fontFamily: voice.fontFamily
            fontSize: Style.font.caption
            tooltipText: modelData === ""
                         ? voice.mainLabel + " answers to “" + voice.activePhrase + "” · " + (voice.usingEndpoint ? "endpoint" : (voice.programLabel(voice.mainAgent) || "no agent"))
                           + (voice.serviceActive && voice.mainAgent !== "" ? " · " + voice.mainPosture : "")
                         : name + " answers to “" + String(entry.name || "") + "” · " + voice.programLabel(String(entry.agent || "claude"))
            onClicked: voice.summon({ page: "agents", agent: modelData === "" ? "main" : modelData })
          }
        }
      }

      // --- typing ---
      // For when talking is not an option: no microphone, a wake word that
      // will not fire, a room where you would rather not. Sent the way a
      // transcript is, so "Sora, ..." still picks Sora.
      Row {
        width: parent.width
        spacing: Style.space(6)
        visible: voice.serviceActive

        TextField {
          id: typeField
          width: parent.width - (typeTo.visible ? typeTo.width + parent.spacing : 0)
          foreground: voice.fg
          font.family: voice.fontFamily
          placeholderText: "Type to " + voice.typeTargetLabel + "…  Enter sends"
          onAccepted: {
            var t = text.trim()
            if (t === "") return
            voice.sendTyped(t)
            text = ""
          }
          Keys.onEscapePressed: { if (text !== "") text = ""; else voice.close() }
        }
        // Who it goes to, when there is more than one agent. A click moves
        // to the next.
        Button {
          id: typeTo
          visible: voice.crew.length > 0
          text: voice.typeTargetLabel
          bordered: true
          focusable: false
          foreground: voice.fg
          fontFamily: voice.fontFamily
          fontSize: Style.font.caption
          tooltipText: "Who the message goes to. Starting it with a name works too."
          onClicked: voice.nextTypeTarget()
        }
      }

      PanelSeparator { width: parent.width; foreground: voice.fg }

      // --- quick toggles ---
      Grid {
        id: toggles
        width: parent.width
        columns: 2
        columnSpacing: Style.space(6)
        rowSpacing: Style.space(6)

        Repeater {
          model: voice.quickToggles
          QuickToggle {
            required property var modelData
            width: (toggles.width - toggles.columnSpacing) / 2
            key: modelData.key
            on: voice.pref(modelData.key, modelData.fallback) === true
            text: modelData.label
            iconText: modelData.icon
            hasCursor: voice.cursorOn("toggle:" + modelData.key)
            onClicked: store.set(key, !on)
          }
        }

        // Not a setting: the daemon's state. On is "listening without the
        // wake word right now", for the agent spoken to last.
        QuickToggle {
          visible: voice.serviceActive
          width: (toggles.width - toggles.columnSpacing) / 2
          on: voice.openMicOn
          text: voice.openMicOn ? "Open mic · " + voice.openMicMinutes + " min" : "Open mic"
          iconText: "\u{f036c}"
          tooltipText: voice.openMicOn ? "Listening without the wake word. Click to close it."
                                       : "Talk without the wake word until you stop or go quiet."
          hasCursor: voice.cursorOn("openmic")
          onClicked: voice.toggleOpenMic()
        }
      }

      // --- quick pickers ---
      Column {
        width: parent.width
        spacing: Style.space(8)

        Item {
          width: parent.width
          height: voicePicker.height
          Text {
            anchors.verticalCenter: parent.verticalCenter
            text: "Voice"
            color: voice.pref("speakReplies", true) === true ? voice.fg : voice.dim
            font.family: voice.fontFamily
            font.pixelSize: Style.font.body
          }
          Dropdown {
            id: voicePicker
            anchors.right: parent.right
            width: Style.space(220)
            showLabel: false
            enabled: voice.pref("speakReplies", true) === true
            fontFamily: voice.fontFamily
            foreground: voice.fg
            options: voice.voiceOptions
            value: voice.pref("voice", "lessac-medium")
            // A voice not on disk is fetched by the overlay, which knows
            // what is there and can say so; the popup only picks.
            onChanged: function(v) { if (v !== voice.pref("voice", "lessac-medium")) store.set("voice", v) }
          }
        }
      }

      // --- last exchange ---
      // What it last heard, and what it answered. On screen, because the
      // whole problem with an interface you cannot see is being unsure
      // whether it understood you.
      //
      // Always there (phase M3, bug B). It used to appear only once
      // something had been heard and vanish at every wake word, and the
      // whole popup bounced up and down with it through a conversation.
      // Locked (hudSize, the default): two fixed lines, the answer above
      // what is being said now, the same height whatever they hold.
      // Dynamic: the old folded text, which grows with what it shows but
      // keeps its slot when empty. "more" unfolds either, on request.
      Column {
        id: lastExchange
        width: parent.width
        spacing: Style.space(4)
        visible: voice.engineInstalled
        readonly property bool expanded: voice.lastExpanded
        readonly property bool folded: voice.readoutLocked && !expanded

        Item {
          width: parent.width
          height: lastHeader.implicitHeight
          PanelSectionHeader {
            id: lastHeader
            text: "LAST HEARD" + (voice.lastWho !== "" ? " · " + voice.lastWho.toUpperCase() : "")
            foreground: voice.dim
            fontFamily: voice.fontFamily
          }
          Text {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            // In a row of fixed height, so coming and going moves nothing.
            visible: voice.lastTranscript !== "" || voice.readoutReply !== ""
            text: lastExchange.expanded ? "less" : "more"
            color: moreHover.containsMouse ? voice.fg : voice.dim
            font.family: voice.fontFamily
            font.pixelSize: Style.font.caption
            MouseArea {
              id: moreHover
              anchors.fill: parent
              anchors.margins: -Style.space(6)
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: voice.lastExpanded = !voice.lastExpanded
            }
          }
        }

        ReadoutLines {
          width: parent.width
          visible: lastExchange.folded
          reply: voice.readoutReply
          transcript: voice.lastTranscript
          replyPlaceholder: "No answer yet"
          transcriptPlaceholder: voice.serviceActive ? "Nothing heard yet" : "Not listening"
          pixelSize: Style.font.body
          fontFamily: voice.fontFamily
          foreground: voice.fg
          replyAccent: Commons.Color.accent
          nowAccent: voice.barIconColor
        }

        // Dynamic, or unfolded. The kept answer first: it came before what
        // is being said now. Only while this turn has no answer of its own.
        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          visible: !lastExchange.folded && voice.lastReply === "" && voice.readoutReply !== ""
          maximumLineCount: lastExchange.expanded ? 1000 : 2
          elide: Text.ElideRight
          text: "→ " + voice.readoutReply
          textFormat: Text.PlainText
          color: voice.dim
          font.family: voice.fontFamily
          font.pixelSize: Style.font.body
        }
        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          visible: !lastExchange.folded
          maximumLineCount: lastExchange.expanded ? 1000 : 2
          elide: Text.ElideRight
          // A placeholder rather than nothing: the slot stays, so the popup
          // does not jump when the first words arrive.
          text: voice.lastTranscript !== "" ? voice.lastTranscript
                : voice.serviceActive ? "Nothing heard yet" : "Not listening"
          // Not AutoText: this is a transcript of speech and of a model's
          // reply, so it is attacker-shaped input as far as the bar is
          // concerned. Rich text would hide characters behind markup.
          textFormat: Text.PlainText
          color: voice.lastTranscript !== "" ? voice.fg : voice.dim
          font.italic: voice.lastTranscript === ""
          font.family: voice.fontFamily
          font.pixelSize: Style.font.body
        }
        // The agent's answer, so the panel is a transcript of the exchange
        // rather than only of your half of it.
        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          visible: !lastExchange.folded && voice.lastReply !== ""
          maximumLineCount: lastExchange.expanded ? 1000 : 3
          elide: Text.ElideRight
          text: "→ " + voice.lastReply
          textFormat: Text.PlainText
          color: voice.dim
          font.family: voice.fontFamily
          font.pixelSize: Style.font.body
        }
        Text {
          visible: lastExchange.expanded
          text: voice.lastAudioS.toFixed(1) + "s audio · whisper " + voice.lastMs + "ms" +
                (voice.lastLatencyMs > 0
                 ? " · answered in " + (voice.lastLatencyMs / 1000).toFixed(1) + "s" : "")
          color: voice.dim
          font.family: voice.fontFamily
          font.pixelSize: Style.font.caption
        }
      }

      PanelSeparator { width: parent.width; foreground: voice.fg }

      // Real buttons, where there used to be two words in the caption
      // colour that few people noticed were links.
      Row {
        width: parent.width
        spacing: Style.space(8)

        Button {
          width: (parent.width - parent.spacing) / 2
          text: "Conversation"
          iconText: "\u{f0b79}"
          bordered: true
          hasCursor: voice.cursorOn("conversation")
          foreground: voice.fg
          fontFamily: voice.fontFamily
          onClicked: {
            conversation.running = true
            voice.close()
          }
        }
        Button {
          width: (parent.width - parent.spacing) / 2
          text: "All settings"
          iconText: "\u{f0493}"
          bordered: true
          hasCursor: voice.cursorOn("settings")
          foreground: voice.fg
          fontFamily: voice.fontFamily
          onClicked: voice.summon({})
        }
      }
    }
    }
  }

  // The overlay is the same plugin, summoned by id, with a page to open.
  Process { id: summoner }

  // The same overlay, on its conversation page.
  Process {
    id: conversation
    command: ["omarchy-shell", "shell", "summon", "duaneoca.agentvoice",
              "{\"mode\":\"history\"}"]
  }

}
