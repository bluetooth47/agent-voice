import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import ".."
import "../ui"

// When a turn starts and ends, whether it keeps listening afterwards, and
// what happens when you talk over it.
//
// The timings and the talking-over settings were split between "timing" and
// "key bindings and interruptions", with the deaf period after speaking on
// one side and the barge-in switches it governs on the other. They are one
// subject: the rhythm of an exchange.
Column {
  id: page

  required property var s

  spacing: Style.space(18)

  // Four timings move together. A preset is only a shorthand for them --
  // nothing stores which one was picked; the page works it out from the
  // values, so a slider moved by hand reads as "custom".
  readonly property var presets: ({
    "patient":  { leadInMs: 8000, trailingSilenceMs: 2000, quickEndMs: 1200, followUpMs: 12000 },
    "balanced": { leadInMs: 5000, trailingSilenceMs: 1200, quickEndMs: 800,  followUpMs: 7000 },
    "snappy":   { leadInMs: 3500, trailingSilenceMs: 800,  quickEndMs: 500,  followUpMs: 5000 }
  })
  readonly property string preset: {
    for (var name in presets) {
      var p = presets[name]
      var all = true
      for (var k in p) if (Number(s.setting(k, -1)) !== p[k]) all = false
      if (all) return name
    }
    return "custom"
  }
  function applyPreset(name) {
    var p = presets[name]
    if (!p) return
    for (var k in p) if (Number(s.setting(k, -1)) !== p[k]) s.put(k, p[k])
  }
  function dflt(key) {
    return s.defaults[key] !== undefined ? s.defaults[key] : NaN
  }

  PageHeader {
    width: parent.width
    title: "Conversation"
    subtitle: "When it starts and stops listening, and how you interrupt it."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
  }

  SettingRow {
    width: parent.width
    stacked: true
    label: "Pace"
    hint: page.preset === "patient" ? "Waits longer for you to start, pause and carry on. Good for thinking aloud."
          : page.preset === "snappy" ? "Ends turns quickly. Good for short commands; cuts in on long pauses."
          : page.preset === "balanced" ? "The defaults."
          : "Your own timings, set below."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
    SegmentedChoice {
      options: [
        { value: "patient", label: "Patient" },
        { value: "balanced", label: "Balanced" },
        { value: "snappy", label: "Snappy" }
      ].concat(page.preset === "custom" ? [{ value: "custom", label: "Custom" }] : [])
      value: page.preset
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onCommitted: function(v) { page.applyPreset(v) }
    }
  }

  SettingsGroup {
    width: parent.width
    title: "FOLLOW-UPS"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    ToggleRow {
      width: parent.width
      label: "Keep listening after a reply"
      hint: "Carry on without the wake word. Say \"stop\" or \"never mind\" to end it, or stay quiet."
      checked: page.s.setting("conversationMode", true) === true
      changed: page.s.changed("conversationMode")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("conversationMode", !checked)
      onReset: page.s.resetKey("conversationMode")
    }

    // Left on rather than switched off for a backend that forgets: it still
    // saves the wake word, which is half of what it is for. What it cannot
    // do is follow on, and that failure is silent.
    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      visible: page.s.setting("conversationMode", true) === true && !page.s.vRemembers
      text: "⚠  " + (page.s.mainAgent === "" ? "This agent" : page.s.mainAgent) +
            " starts fresh on every turn, so this saves you the wake word and nothing " +
            "more. Asking \"what did you mean by that?\" gets an answer to a question it " +
            "has never seen."
      textFormat: Text.PlainText
      color: page.s.urgent
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }

    KnobRow {
      width: parent.width
      enabled: page.s.setting("conversationMode", true) === true
      opacity: enabled ? 1 : 0.45
      foreground: page.s.foreground; fontFamily: page.s.fontFamily
      label: "Follow-up window"
      description: enabled ? "How long it keeps listening after speaking before it needs the wake word again."
                           : "Only while it keeps listening after a reply."
      value: page.s.setting("followUpMs", 7000)
      defaultValue: page.dflt("followUpMs")
      changed: page.s.changed("followUpMs")
      minimum: 2000; maximum: 20000; stepSize: 500
      onCommitted: function(v) { page.s.put("followUpMs", v) }
      onReset: page.s.resetKey("followUpMs")
    }
  }

  // An open conversation: no wake word until it is closed or goes quiet.
  // Started by voice ("keep listening") or the popup's toggle.
  SettingsGroup {
    width: parent.width
    title: "OPEN MIC"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      text: "Say \"keep listening\" to talk without the wake word, and \"stop listening\", " +
            "\"goodbye\" or \"full stop\" to end it. It stays with the agent you started it " +
            "with; say another agent's name to hand it over. The bar icon and the HUD show " +
            "while it is open."
      textFormat: Text.PlainText
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }

    KnobRow {
      width: parent.width
      foreground: page.s.foreground; fontFamily: page.s.fontFamily
      label: "Closes after"
      description: "Minutes with nothing said before it needs the wake word again."
      value: page.s.setting("openMicIdleMin", 10)
      defaultValue: page.dflt("openMicIdleMin")
      changed: page.s.changed("openMicIdleMin")
      minimum: 1; maximum: 60; stepSize: 1
      unit: " min"
      onCommitted: function(v) { page.s.put("openMicIdleMin", Math.round(v)) }
      onReset: page.s.resetKey("openMicIdleMin")
    }

    ToggleRow {
      width: parent.width
      label: "Only answer if it's meant for you"
      hint: "It stays silent when what it heard was said to someone else, or came from a television."
      help: "Each thing heard on the open mic goes to the agent with a note asking it to " +
            "reply SKIP if it was not said to it, and a SKIP is never spoken or kept. It " +
            "costs a turn of the agent's time for everything heard."
      checked: page.s.setting("openMicAddressedOnly", true) === true
      changed: page.s.changed("openMicAddressedOnly")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("openMicAddressedOnly", !checked)
      onReset: page.s.resetKey("openMicAddressedOnly")
    }

    ToggleRow {
      width: parent.width
      label: "Open the mic after every wake"
      hint: "Every wake word starts an open conversation, as if you had said \"keep listening\"."
      checked: page.s.setting("openMicAuto", false) === true
      changed: page.s.changed("openMicAuto")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("openMicAuto", !checked)
      onReset: page.s.resetKey("openMicAuto")
    }
  }

  // Progress talk. Off by default: what it says was written from recorded
  // turns (bench/narration), and is yours to switch on.
  SettingsGroup {
    width: parent.width
    title: "WHILE IT WORKS"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    SettingRow {
      width: parent.width
      stacked: true
      label: "Talk while it works"
      hint: page.s.setting("narration", "off") === "detailed"
            ? "Names files, searches and pages: \"I'm reading Panel.qml.\""
            : page.s.setting("narration", "off") === "brief"
            ? "Names the stage only: \"I'm running the tests.\""
            : "Silent between its first sentence and its answer."
      help: "Every sentence comes from a tool the agent really ran, never a guess. " +
            "It waits for a quiet stretch, spaces its sentences further apart as a " +
            "turn goes on, never repeats itself, and stops the moment the agent " +
            "starts talking. Secret files are \"a config file\" and a command line is " +
            "never read out. Claude Code and Codex report their tools; Gemini, " +
            "Antigravity, Copilot and endpoints do not, so they stay quiet. Each " +
            "agent's card can choose for itself."
      changed: page.s.changed("narration")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onReset: page.s.resetKey("narration")
      SegmentedChoice {
        options: [
          { value: "off", label: "Off" },
          { value: "brief", label: "Brief" },
          { value: "detailed", label: "Detailed" }
        ]
        value: page.s.setting("narration", "off")
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onCommitted: function(v) { page.s.put("narration", v) }
      }
    }

    KnobRow {
      width: parent.width
      enabled: page.s.setting("narration", "off") !== "off"
      opacity: enabled ? 1 : 0.45
      foreground: page.s.foreground; fontFamily: page.s.fontFamily
      label: "Quiet before it says anything"
      description: "How long a turn has been silent before the first sentence. Later ones come at least 10, then 15, then 25 seconds apart."
      value: page.s.setting("narrationSilenceS", 7)
      defaultValue: page.dflt("narrationSilenceS")
      changed: page.s.changed("narrationSilenceS")
      minimum: 3; maximum: 30; stepSize: 1
      unit: "s"
      onCommitted: function(v) { page.s.put("narrationSilenceS", Math.round(v)) }
      onReset: page.s.resetKey("narrationSilenceS")
    }
  }

  SettingsGroup {
    width: parent.width
    title: "WHEN A TURN STARTS AND ENDS"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    KnobRow {
      width: parent.width
      foreground: page.s.foreground; fontFamily: page.s.fontFamily
      label: "Time to start speaking"
      description: "After the wake word, how long it waits for you to make a sound."
      help: "If you do not, it gives up quietly and goes back to listening for the " +
            "wake word. Once you start talking this no longer applies — the pause " +
            "below ends the turn instead. Err generous: being cut off before you have " +
            "started is the most irritating way this can fail."
      value: page.s.setting("leadInMs", 5000)
      defaultValue: page.dflt("leadInMs")
      changed: page.s.changed("leadInMs")
      minimum: 1000; maximum: 15000; stepSize: 500
      onCommitted: function(v) { page.s.put("leadInMs", v) }
      onReset: page.s.resetKey("leadInMs")
    }

    KnobRow {
      width: parent.width
      foreground: page.s.foreground; fontFamily: page.s.fontFamily
      label: "Pause that ends a turn"
      description: "This much quiet, under the microphone gate, and it stops listening."
      value: page.s.setting("trailingSilenceMs", 1200)
      defaultValue: page.dflt("trailingSilenceMs")
      changed: page.s.changed("trailingSilenceMs")
      minimum: 400; maximum: 4000; stepSize: 100
      onCommitted: function(v) { page.s.put("trailingSilenceMs", v) }
      onReset: page.s.resetKey("trailingSilenceMs")
    }

    KnobRow {
      width: parent.width
      foreground: page.s.foreground; fontFamily: page.s.fontFamily
      label: "Shorter pause when you sound finished"
      description: "Used instead when what you said reads as a finished sentence. 0 turns it off."
      help: "Whisper works through what you said at each pause, so by the time you " +
            "stop it usually has the words already. When they read as a finished " +
            "sentence, this much quiet ends the turn instead of the full pause. " +
            "Trailing off, or stopping on a word like \"and\" or \"the\", still waits " +
            "the full pause."
      value: page.s.setting("quickEndMs", 800)
      defaultValue: page.dflt("quickEndMs")
      changed: page.s.changed("quickEndMs")
      minimum: 0; maximum: 2000; stepSize: 100
      onCommitted: function(v) { page.s.put("quickEndMs", v) }
      onReset: page.s.resetKey("quickEndMs")
    }

    KnobRow {
      width: parent.width
      foreground: page.s.foreground; fontFamily: page.s.fontFamily
      label: "Ignore a turn shorter than"
      description: "Throws away a turn too short to hold anything — usually a wake word fired by a noise."
      help: "Measured on the whole recording — the wake word to the end of the pause " +
            "— not on the speech inside it. With the pause at its default this rarely " +
            "triggers, since any finished turn already contains that much silence; it " +
            "starts to matter once you shorten the pause."
      value: page.s.setting("minUtteranceMs", 400)
      defaultValue: page.dflt("minUtteranceMs")
      changed: page.s.changed("minUtteranceMs")
      minimum: 0; maximum: 2000; stepSize: 100
      onCommitted: function(v) { page.s.put("minUtteranceMs", v) }
      onReset: page.s.resetKey("minUtteranceMs")
    }

    KnobRow {
      width: parent.width
      foreground: page.s.foreground; fontFamily: page.s.fontFamily
      label: "Longest a turn can be"
      description: "A microphone stuck open stops here rather than recording forever."
      value: page.s.setting("maxUtteranceMs", 30000)
      defaultValue: page.dflt("maxUtteranceMs")
      changed: page.s.changed("maxUtteranceMs")
      minimum: 5000; maximum: 120000; stepSize: 5000
      onCommitted: function(v) { page.s.put("maxUtteranceMs", v) }
      onReset: page.s.resetKey("maxUtteranceMs")
    }
  }

  SettingsGroup {
    width: parent.width
    title: "TALKING OVER IT"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    ToggleRow {
      width: parent.width
      label: "“Full stop” works without the wake word"
      hint: "Stops every agent at once, even mid-thought. Not while it is speaking on speakers: the microphone is the reply's then."
      help: "sherpa-onnx listens for \"full stop\" in every frame, so nothing waits for a " +
            "wake word, a pause or Whisper. On synthesized clips it caught 8 of 10 and " +
            "woke on none of 50 sound-alikes. Only with the sherpa-onnx engine; on the " +
            "others say the wake word first."
      disabledReason: page.s.usingSherpa ? "" : "Only with the sherpa-onnx engine."
      checked: page.s.setting("fullStopAnytime", true) === true
      changed: page.s.changed("fullStopAnytime")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("fullStopAnytime", !checked)
      onReset: page.s.resetKey("fullStopAnytime")
    }

    ToggleRow {
      width: parent.width
      label: "Interrupt by talking, on a headset"
      hint: "On headphones it stops as soon as you talk over it, and what you say is your next request."
      checked: page.s.setting("bargeOnHeadset", true) === true
      changed: page.s.changed("bargeOnHeadset")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("bargeOnHeadset", !checked)
      onReset: page.s.resetKey("bargeOnHeadset")
    }

    ToggleRow {
      width: parent.width
      label: "On speakers too"
      hint: "Laptop speakers usually drown you out. Measure first with: agentvoice calibrate"
      help: "Through speakers, talking cannot interrupt a reply: at a normal volume its " +
            "own voice reaches the mic as loudly as yours, so the microphone is ignored " +
            "while it talks. On a headset that problem is gone."
      checked: page.s.setting("bargeIn", false) === true
      changed: page.s.changed("bargeIn")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("bargeIn", !checked)
      onReset: page.s.resetKey("bargeIn")
    }

    KnobRow {
      width: parent.width
      enabled: page.s.setting("bargeIn", false) === true
               || page.s.setting("bargeOnHeadset", true) === true
      opacity: enabled ? 1 : 0.45
      foreground: page.s.foreground; fontFamily: page.s.fontFamily
      label: "How much louder you must be"
      unit: "%"
      description: enabled ? "Than its own voice, before it stops. Higher is harder to trigger, by accident and on purpose."
                           : "Only when talking can interrupt it."
      value: page.s.setting("bargeFactor", 150)
      defaultValue: page.dflt("bargeFactor")
      changed: page.s.changed("bargeFactor")
      minimum: 110; maximum: 400; stepSize: 10
      onCommitted: function(v) { page.s.put("bargeFactor", v) }
      onReset: page.s.resetKey("bargeFactor")
    }

    KnobRow {
      width: parent.width
      foreground: page.s.foreground; fontFamily: page.s.fontFamily
      label: "Deaf period after speaking"
      description: "The microphone is ignored while it talks, and for this long after."
      help: "One microphone beside the speakers cannot win against its own output, " +
            "so the mic goes deaf while the voice talks and for this long after. Too " +
            "short and it hears the end of its own sentence as you."
      value: page.s.setting("echoTailMs", 350)
      defaultValue: page.dflt("echoTailMs")
      changed: page.s.changed("echoTailMs")
      minimum: 0; maximum: 1500; stepSize: 50
      onCommitted: function(v) { page.s.put("echoTailMs", v) }
      onReset: page.s.resetKey("echoTailMs")
    }

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      text: "Saying \"stop\" or \"never mind\" cancels a turn it has not taken yet — useful " +
            "when the wake word fires by mistake, so nothing is sent to the agent."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
  }
}
