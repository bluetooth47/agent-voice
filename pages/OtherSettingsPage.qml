import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import ".."
import "../ui"

// Other settings (master plan M26; "Display & privacy" until then): an honest
// grab-bag of what belongs to no one page -- the readout on screen, privacy,
// the keys, and the installation itself (repair and removal, moved here from
// About, which now only says what is installed). The old page id "display"
// still opens this one (Settings.qml goTo).
Column {
  id: page

  required property var s

  spacing: Style.space(18)

  // --- the keys -------------------------------------------------------------------
  // Read live (`agentvoice keys --json`: bindings.lua for what each key runs,
  // `hyprctl binds -j` for what Hyprland has loaded) when the page opens.
  // Read only: the bindings are the user's, in a file Omarchy owns, and
  // changing one here is deferred (plan section 9). The page opens the file.
  property var keysInfo: null
  property string keysError: ""
  Process {
    id: keysReader
    command: ["agentvoice", "keys", "--json"]
    stdout: StdioCollector {
      onStreamFinished: {
        try { page.keysInfo = JSON.parse(text); page.keysError = "" }
        catch (e) {
          page.keysInfo = null
          page.keysError = "Could not read them: this needs the service installed from this build " +
                           "(Maintenance → Repair)."
        }
      }
    }
  }
  function readKeys() { if (!keysReader.running) keysReader.running = true }
  // The file to open, checked against the one shape it may have before it
  // reaches argv.
  function bindingsPath() {
    var f = page.keysInfo ? String(page.keysInfo.file || "") : ""
    return /^\/[^\0]*\/hypr\/bindings\.lua$/.test(f) && f.indexOf("/../") < 0 ? f : ""
  }
  Process { id: bindingsOpener }
  function openBindings() {
    var f = page.bindingsPath()
    if (f === "") return
    bindingsOpener.command = ["omarchy-launch-editor", f]
    bindingsOpener.running = true
  }

  // --- writing what is said to the journal ----------------------------------------
  // Off is one click. On is asked first, because the journal keeps it for
  // weeks: the switch only opens the question, and `logSpeech` true is
  // written by turnOnSpeechLog(), which only the question's onConfirmed
  // calls (tests/test_confirms.py).
  property bool confirmingLog: false
  function turnOnSpeechLog() {
    page.s.put("logSpeech", true)
    page.confirmingLog = false
  }

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
  Component.onCompleted: { readStatsInfo(); readKeys() }
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
    title: "Other settings"
    subtitle: "What belongs to no one page: the readout on screen, privacy, the keys, and the " +
              "installation itself. Saving chats is on the Chats page."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
  }

  // The switch and its duration together, because the two are one setting
  // described twice: how long it stays governs nothing when it is not shown.
  Card {
    width: parent.width
    title: "On-screen readout"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    ToggleRow {
      objectName: "set-hud"
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

    SliderRow {
      objectName: "set-hudLingerMs"
      width: parent.width
      // Dimmed, not hidden: hiding made the page jump, and left nothing to
      // say where the setting had gone.
      disabledReason: page.s.setting("hud", true) === true ? "" : "Only while the readout is shown."
      foreground: page.s.foreground; fontFamily: page.s.fontFamily
      label: "How long it stays afterwards"
      unit: "ms"
      hint: "From the end of the exchange, including the follow-up window. 0 closes it at once."
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
      objectName: "set-hudSize"
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
      objectName: "set-hudKeepReply"
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
      objectName: "set-hudPosition"
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
      objectName: "set-hudTextSize"
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
      ActionButton {
        objectName: "hudPreview"
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

    // Omarchy's Agents panel: also something on screen, so it sits with the
    // readout (its own group until M26).
    ToggleRow {
      objectName: "set-agentsPanel"
      width: parent.width
      label: "Show each voice agent in Omarchy's Agents panel"
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

  Card {
    width: parent.width
    title: "Privacy"
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
      ActionButton {
        text: "Go to Chats →"
        bordered: true
        focusable: true
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.s.goTo("chats", "")
      }
    }

    ToggleRow {
      objectName: "set-yieldToRecorders"
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
      objectName: "set-logSpeech"
      width: parent.width
      label: "\u26a0 Write what is said to the system log"
      hint: page.s.setting("logSpeech", false) === true
            ? "On: what you say and every reply go to the journal, which keeps them for weeks. Turn it off when you are done."
            : "Off. The journal keeps it for weeks, so turn it on only to diagnose something, then off again."
      help: "The journal keeps entries for weeks, so logging replies leaves a " +
            "transcript of everything the agent read out — file contents, key names " +
            "— sitting there until it rotates. Timings, wake events and errors are " +
            "always logged; this is only the words. Copy diagnostics (About) leaves " +
            "them out either way."
      checked: page.s.setting("logSpeech", false) === true
      changed: page.s.changed("logSpeech")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      // Off at once; on only through the question below.
      onToggled: {
        if (checked) { page.confirmingLog = false; page.s.put("logSpeech", false) }
        else page.confirmingLog = true
      }
      onReset: { page.confirmingLog = false; page.s.resetKey("logSpeech") }
    }
    ToolConfirm {
      objectName: "logSpeechConfirm"
      width: parent.width
      visible: page.confirmingLog && page.s.setting("logSpeech", false) !== true
      title: "Write what is said to the system log?"
      lines: [
        { label: "What goes there", value: "Everything you say to an agent, and everything it says back." },
        { label: "How long", value: "The journal keeps entries for weeks, until it rotates. " +
                                    "Turning this off later does not remove what was written." },
        { label: "Who can read it", value: "You, and any account allowed to read the whole system journal (administrators)." }
      ]
      warning: "Replies can carry file contents and key names. Turn it on to diagnose something, then off again."
      confirmText: "Turn logging on"
      foreground: page.s.foreground
      accent: page.s.accent
      urgent: page.s.urgent
      fontFamily: page.s.fontFamily
      onConfirmed: page.turnOnSpeechLog()
      onCancelled: page.confirmingLog = false
    }

    // Master plan M21: the Overview's numbers, and the one way to remove them.
    ToggleRow {
      objectName: "set-keepStats"
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
      textFormat: Text.PlainText
      text: "\u{f033e}  The mic always closes while the screen is locked. That is not a " +
            "setting: a locked machine that still answers would let anyone at the desk talk to it."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
  }

  Card {
    objectName: "keysGroup"
    width: parent.width
    title: "Keys"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: page.keysError !== "" ? page.keysError
            : !page.keysInfo ? "Reading the keys…"
            : page.keysInfo.rows.length === 0
              ? "No key runs an Agent Voice command. Repair the installation to be offered the usual ones, or add them to the file yourself."
              : "Read from your bindings file" + (page.keysInfo.hyprland ? " and what Hyprland has loaded." : "; Hyprland could not be asked whether they are loaded.")
      color: page.keysError !== "" ? page.s.urgent : page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }

    // A key's row: what it is, what it does, and a mark when Hyprland has not
    // loaded it (a line it rejected, or one not reloaded yet).
    Repeater {
      model: page.keysInfo ? page.keysInfo.rows : []
      Item {
        required property var modelData
        width: parent ? parent.width : 0
        height: Math.max(keyText.implicitHeight, whatText.implicitHeight)
        Text {
          id: keyText
          width: Style.space(190)
          wrapMode: Text.Wrap
          text: modelData.keys
          textFormat: Text.PlainText
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
          text: modelData.what + (modelData.loaded === false ? "  (in the file, but Hyprland has not loaded it)" : "")
          textFormat: Text.PlainText
          color: modelData.loaded === false ? page.s.urgent : page.s.dim
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
    }

    // The bar icon's own clicks: the widget's, not Hyprland's, so fixed.
    Repeater {
      model: [
        { keys: "Click the bar icon", what: "Open the panel. Its STOP button stops a turn." },
        { keys: "Right-click the bar icon", what: "Mute or unmute the microphone." },
        { keys: "Middle-click the bar icon", what: "Start or stop the service." }
      ]
      Item {
        required property var modelData
        width: parent ? parent.width : 0
        height: Math.max(mouseKey.implicitHeight, mouseWhat.implicitHeight)
        Text {
          id: mouseKey
          width: Style.space(190)
          text: modelData.keys
          color: page.s.foreground
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
        }
        Text {
          id: mouseWhat
          anchors.left: mouseKey.right
          anchors.right: parent.right
          wrapMode: Text.WordWrap
          text: modelData.what
          color: page.s.dim
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
    }

    SettingRow {
      width: parent.width
      label: "Change a key"
      hint: page.bindingsPath() !== ""
            ? "In " + page.keysInfo.file_shown + ". It is your file: Hyprland reloads it when it is saved."
            : "In Hyprland's bindings file, once it has been found."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      ActionButton {
        objectName: "openBindings"
        text: "Open bindings file"
        bordered: true
        focusable: true
        enabled: page.bindingsPath() !== ""
        opacity: enabled ? 1 : 0.45
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.openBindings()
      }
    }
  }

  Card {
    width: parent.width
    title: "Maintenance"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    SettingRow {
      width: parent.width
      label: page.s.engineInstalled ? "Repair the installation" : "Install the voice engine"
      hint: page.s.engineInstalled
            ? "Runs the installer again: fetches anything missing, keeps your settings, and restarts the service if it is running."
            : "About 700MB — speech recognition, a voice and the wake word — run as a service you can stop."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      ActionButton {
        objectName: "repair"
        text: page.s.engineInstalled ? "Repair…" : "Install…"
        bordered: true
        focusable: true
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.s.fetchNow([])
      }
    }

    SettingRow {
      width: parent.width
      visible: !page.s.owwAvailable
      label: "Add openWakeWord"
      hint: "Better rejection of sound-alikes, and a verifier trained on your voice. About 154MB."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      ActionButton {
        text: "Install…"
        bordered: true
        focusable: true
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.s.fetchNow(["--oww"])
      }
    }

    SettingRow {
      width: parent.width
      visible: !page.s.sherpaAvailable
      label: "Add sherpa-onnx"
      hint: "Takes any phrase and your agents' names, with far fewer false wakes than Vosk. About 60MB."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      ActionButton {
        text: "Install…"
        bordered: true
        focusable: true
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.s.fetchNow(["--sherpa"])
      }
    }

    // Last, and the only control drawn red before it is clicked.
    SettingRow {
      width: parent.width
      label: "Remove Agent Voice"
      hint: "The engine, the service, the keys it added and the widget in one go. Your trained " +
            "verifiers, recordings and API keys are kept, and it says where they are on the way out."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      DangerButton {
        objectName: "removeEverything"
        text: "Remove Agent Voice…"
        question: "Really remove Agent Voice?"
        confirmText: "Remove"
        foreground: page.s.urgent
        urgent: page.s.urgent
        fontFamily: page.s.fontFamily
        onConfirmed: page.s.removeEverything()
      }
    }
  }
}
