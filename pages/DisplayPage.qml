import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import ".."
import "../ui"

// What it shows, what it keeps, and the keys.
Column {
  id: page

  required property var s

  spacing: Style.space(18)

  PageHeader {
    width: parent.width
    title: "Display & privacy"
    subtitle: "The readout on screen, what is kept and where, and the keys."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
  }

  // The switch and its duration together, because the two are one setting
  // described twice: how long it stays governs nothing when it is not shown.
  SettingsGroup {
    width: parent.width
    title: "ON-SCREEN READOUT"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    ToggleRow {
      width: parent.width
      label: "Show what it heard and what it answered"
      hint: "A panel by the bar from the wake word until shortly after the answer. Click it for the whole conversation."
      help: "It cannot take the keyboard from what you are typing, and it hides at " +
            "once when the screen locks."
      checked: page.s.setting("hud", true) === true
      changed: page.s.changed("hud")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("hud", !checked)
      onReset: page.s.resetKey("hud")
    }

    KnobRow {
      width: parent.width
      // Dimmed, not hidden: hiding made the page jump, and left nothing to
      // say where the setting had gone.
      enabled: page.s.setting("hud", true) === true
      opacity: enabled ? 1 : 0.45
      foreground: page.s.foreground; fontFamily: page.s.fontFamily
      label: "How long it stays afterwards"
      unit: "ms"
      description: enabled ? "From the end of the exchange, including the follow-up window. 0 closes it at once."
                           : "Only while the readout is shown."
      value: page.s.setting("hudLingerMs", 2000)
      defaultValue: page.s.defaults.hudLingerMs !== undefined ? page.s.defaults.hudLingerMs : NaN
      changed: page.s.changed("hudLingerMs")
      minimum: 0; maximum: 10000; stepSize: 500
      onCommitted: function(v) { page.s.put("hudLingerMs", v) }
      onReset: page.s.resetKey("hudLingerMs")
    }
  }

  SettingsGroup {
    width: parent.width
    title: "OMARCHY'S AGENTS PANEL"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    ToggleRow {
      width: parent.width
      label: "Show each voice agent there"
      hint: "A section per agent, saying what it is doing. Hover its info mark for what it runs on."
      help: "A new agent appears the next time that panel is opened. Their prompts and " +
            "tokens are already counted under the agent's own program, so they add " +
            "nothing to the panel's totals. Off removes the sections; Omarchy's own " +
            "per-agent switch hides them too."
      checked: page.s.setting("agentsPanel", true) === true
      changed: page.s.changed("agentsPanel")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("agentsPanel", !checked)
      onReset: page.s.resetKey("agentsPanel")
    }
  }

  SettingsGroup {
    width: parent.width
    title: "PRIVACY"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    ToggleRow {
      width: parent.width
      label: "Keep this session's conversation"
      hint: "For the conversation view. In memory only, readable by you alone, gone at logout."
      help: "Off deletes what is already kept."
      checked: page.s.setting("keepHistory", true) === true
      changed: page.s.changed("keepHistory")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("keepHistory", !checked)
      onReset: page.s.resetKey("keepHistory")
    }

    ToggleRow {
      width: parent.width
      label: "Step aside when another app records"
      hint: "Stops listening during dictation, a call or a recording, and starts again after."
      help: "Without this, saying the wake phrase while dictating elsewhere makes the " +
            "agent answer out loud into what you are dictating. Your own mute is " +
            "untouched either way."
      checked: page.s.setting("yieldToRecorders", true) === true
      changed: page.s.changed("yieldToRecorders")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("yieldToRecorders", !checked)
      onReset: page.s.resetKey("yieldToRecorders")
    }

    ToggleRow {
      width: parent.width
      label: "Write what is said to the system log"
      hint: "Off by default. Turn it on to diagnose something, then off again."
      help: "The journal keeps entries for weeks, so logging replies leaves a " +
            "transcript of everything the agent read out — file contents, key names " +
            "— sitting there until it rotates. Timings, wake events and errors are " +
            "always logged; this is only the words."
      checked: page.s.setting("logSpeech", false) === true
      changed: page.s.changed("logSpeech")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("logSpeech", !checked)
      onReset: page.s.resetKey("logSpeech")
    }

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      text: "\u{f033e}  The microphone closes while the screen is locked. That is not a " +
            "setting: a locked machine that still answers would let anyone at the desk talk to it."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
  }

  SettingsGroup {
    width: parent.width
    title: "KEYS"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    Repeater {
      model: [
        { keys: "Hold F8", what: "Talk without the wake word; release when done." },
        { keys: "F8", what: "While it replies: stop it." },
        { keys: "Super+Ctrl+Space", what: "Stop the reply and everything the agent started." },
        { keys: "Super+Alt+Space", what: "Release the microphone entirely, or take it back." },
        { keys: "Click the bar icon", what: "Open the panel. Its STOP button stops a turn." },
        { keys: "Right-click the bar icon", what: "Mute or unmute the microphone." },
        { keys: "Middle-click the bar icon", what: "Start or stop the service." }
      ]
      Item {
        required property var modelData
        width: parent ? parent.width : 0
        height: Math.max(keyText.implicitHeight, whatText.implicitHeight)
        Text {
          id: keyText
          width: Style.space(190)
          text: modelData.keys
          color: page.s.foreground
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
        }
        Text {
          id: whatText
          anchors.left: keyText.right
          anchors.right: parent.right
          wrapMode: Text.WordWrap
          text: modelData.what
          color: page.s.dim
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
    }
  }
}
