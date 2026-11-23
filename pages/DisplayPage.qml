import QtQuick
import Quickshell
import Quickshell.Io
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

  // The Overview's numbers (master plan M21): how many days are kept and how
  // big, read when the page opens and after a clear. Counts only.
  property var statsInfo: null
  property string statsNote: ""
  Process {
    id: statsInfoReader
    command: ["agentvoice", "stats", "--days", "1", "--json"]
    stdout: StdioCollector {
      onStreamFinished: {
        try { page.statsInfo = JSON.parse(text) } catch (e) { page.statsInfo = null }
      }
    }
  }
  function readStatsInfo() { if (!statsInfoReader.running) statsInfoReader.running = true }
  Component.onCompleted: readStatsInfo()
  // `agentvoice stats clear` deletes every day's numbers. Started only by
  // clearStats(), which only the DangerButton's onConfirmed calls
  // (tests/test_confirms.py).
  Process {
    id: statsClearer
    property bool launched: false
    command: ["agentvoice", "stats", "clear"]
    onStarted: launched = true
    stdout: StdioCollector {
      onStreamFinished: {
        var n = parseInt(text, 10)
        if (!isNaN(n)) page.statsNote = n === 0 ? "There was nothing to clear."
                                     : (n === 1 ? "1 day of numbers cleared." : n + " days of numbers cleared.")
      }
    }
    stderr: StdioCollector {
      onStreamFinished: if (text.trim() !== "") page.statsNote = text.trim()
    }
    onRunningChanged: if (!running) {
      if (!launched) page.statsNote = "Nothing was cleared: agentvoice could not be started."
      page.readStatsInfo()
    }
  }
  function clearStats() {
    if (statsClearer.running) return
    page.statsNote = ""
    statsClearer.launched = false
    statsClearer.running = true
  }
  function sizeText(bytes) {
    var b = Number(bytes) || 0
    return b < 1024 ? b + " bytes" : b < 1048576 ? Math.round(b / 1024) + " KB" : (b / 1048576).toFixed(1) + " MB"
  }

  PageHeader {
    width: parent.width
    title: "Display & privacy"
    subtitle: "The readout on screen, privacy, and the keys. Saving chats is on the Chats page."
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

    // phase M3 (feedback items 3 and 20). Position and text size are dimmed
    // with the switch, like the duration: they shape the floating readout
    // alone. Size and keeping the answer shape the popup too, so stay live.
    SettingRow {
      width: parent.width
      label: "Size"
      hint: page.s.setting("hudSize", "locked") === "dynamic"
            ? "Grows and shrinks to fit what it shows."
            : "Always the same size: two fixed lines, the last answer and what is being said now."
      help: "Locked keeps the readout, and the popup's last-heard lines, the same size " +
            "from one turn to the next, so nothing on screen jumps while you talk. Long " +
            "text shows its newest words; click the readout for the whole conversation."
      changed: page.s.changed("hudSize")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onReset: page.s.resetKey("hudSize")
      SegmentedChoice {
        options: [
          { value: "locked", label: "Locked" },
          { value: "dynamic", label: "Dynamic" }
        ]
        // Anything but "dynamic" is locked, as the readout itself reads it.
        value: page.s.setting("hudSize", "locked") === "dynamic" ? "dynamic" : "locked"
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onCommitted: function(v) { page.s.put("hudSize", v) }
      }
    }

    ToggleRow {
      width: parent.width
      // Not dimmed with the switch: like Size, it shapes the popup's
      // last-heard lines too.
      label: "Keep the last answer on screen while I talk"
      hint: "The answer stays above what you are saying, so replying to it does not make it vanish."
      help: "It clears, with what you said, when the screen locks, when you talk to " +
            "another agent or switch chats, and after ten minutes with nothing new."
      checked: page.s.setting("hudKeepReply", true) !== false
      changed: page.s.changed("hudKeepReply")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("hudKeepReply", !checked)
      onReset: page.s.resetKey("hudKeepReply")
    }

    SettingRow {
      width: parent.width
      disabledReason: page.s.setting("hud", true) === true ? "" : "Only while the readout is shown."
      label: "Position"
      hint: "Which edge of the screen, on the right and clear of the bar."
      help: "The popup from the bar icon stays under the icon either way."
      changed: page.s.changed("hudPosition")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onReset: page.s.resetKey("hudPosition")
      SegmentedChoice {
        options: [
          { value: "top", label: "Top" },
          { value: "bottom", label: "Bottom" }
        ]
        value: page.s.setting("hudPosition", "top") === "bottom" ? "bottom" : "top"
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onCommitted: function(v) { page.s.put("hudPosition", v) }
      }
    }

    SettingRow {
      width: parent.width
      disabledReason: page.s.setting("hud", true) === true ? "" : "Only while the readout is shown."
      label: "Text size"
      hint: "Medium is the bar's own text size."
      changed: page.s.changed("hudTextSize")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onReset: page.s.resetKey("hudTextSize")
      SegmentedChoice {
        options: [
          { value: "small", label: "Small" },
          { value: "medium", label: "Medium" },
          { value: "large", label: "Large" }
        ]
        // Strict, as the HUD reads it: a malformed value shows as medium,
        // which is what is drawn.
        value: page.s.setting("hudTextSize", "medium") === "small" ? "small"
               : page.s.setting("hudTextSize", "medium") === "large" ? "large" : "medium"
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onCommitted: function(v) { page.s.put("hudTextSize", v) }
      }
    }

    // Not a setting: shows the readout for four seconds with sample text,
    // through the running daemon, so it is drawn exactly as a turn is.
    Row {
      width: parent.width
      spacing: Style.space(10)
      Button {
        id: previewButton
        text: "Preview"
        iconText: "\u{f0208}"
        bordered: true
        enabled: page.s.hudPreviewBlocked === ""
        opacity: enabled ? 1 : 0.45
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        tooltipText: "Show the readout for four seconds with sample text"
        onClicked: page.s.previewHud()
      }
      // Why it does nothing, when it would do nothing.
      Hint {
        anchors.verticalCenter: previewButton.verticalCenter
        width: parent.width - previewButton.width - parent.spacing
        text: page.s.hudPreviewBlocked !== "" ? page.s.hudPreviewBlocked
              : "Four seconds, with sample text, where the readout appears."
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
      }
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

    // Saving chats, how long they are kept, and this session's conversation
    // moved to the Chats page in phase M18 (same settings, same values).
    SettingRow {
      width: parent.width
      label: "Saved chats"
      hint: "Whether conversations are saved, for how long, and this session's: on the Chats page."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      Button {
        text: "Go to Chats →"
        bordered: true
        focusable: true
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.s.goTo("chats", "")
      }
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

    // Master plan M21: the Overview's numbers, and the one way to remove them.
    ToggleRow {
      width: parent.width
      label: "Keep usage numbers for the Overview"
      hint: "Counts and timings only, never what was said. Kept 90 days."
      help: "Turns per agent, wakes and the ones turned down, and how long the waits " +
            "were: one small file a day in ~/.local/share/agentvoice/stats, readable by " +
            "you alone. Off counts nothing new; what was kept stays until you clear it."
      checked: page.s.setting("keepStats", true) === true
      changed: page.s.changed("keepStats")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("keepStats", !checked)
      onReset: page.s.resetKey("keepStats")
    }
    Item {
      width: parent.width
      height: Math.max(statsText.implicitHeight, clearStatsButton.implicitHeight)

      Column {
        id: statsText
        anchors.left: parent.left
        anchors.right: clearStatsButton.left
        anchors.rightMargin: Style.space(12)
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(2)
        Text {
          width: parent.width
          wrapMode: Text.Wrap
          text: !page.statsInfo ? "Reading what is kept…"
                : Number(page.statsInfo.files) === 0 ? "No usage numbers kept."
                : page.statsInfo.files + (Number(page.statsInfo.files) === 1 ? " day" : " days")
                  + " of usage numbers · " + page.sizeText(page.statsInfo.bytes)
          textFormat: Text.PlainText
          color: page.s.foreground
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
        Text {
          width: parent.width
          visible: page.statsNote !== ""
          wrapMode: Text.Wrap
          text: page.statsNote
          textFormat: Text.PlainText
          color: page.s.dim
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
      }

      DangerButton {
        id: clearStatsButton
        objectName: "clearStats"
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        text: "Clear stats"
        enabled: !!page.statsInfo && Number(page.statsInfo.files) > 0
        busy: statsClearer.running
        tooltipText: enabled ? "" : "There are no usage numbers to clear"
        question: "Clear every day of usage numbers? The Overview starts again from nothing."
        confirmText: "Clear"
        maxWidth: Math.max(Style.space(260), parent.width * 0.6)
        foreground: page.s.foreground
        urgent: page.s.urgent
        fontFamily: page.s.fontFamily
        onConfirmed: page.clearStats()
      }
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
