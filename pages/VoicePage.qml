import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import ".."
import "../ui"

// What it sounds like, and how it turns your speech into text.
Column {
  id: page

  required property var s

  spacing: Style.space(18)

  readonly property bool speaks: s.setting("speakReplies", true) === true

  // The library's filter: this page's own view, not a setting.
  property string filter: "all"
  readonly property var shown: {
    var out = []
    var all = s.rawVoiceOptions
    for (var i = 0; i < all.length; i++) {
      var v = all[i]
      if (page.filter === "here" && s.voicesOnDisk.indexOf(v.value) < 0) continue
      if ((page.filter === "female" || page.filter === "male") && v.gender !== page.filter) continue
      if (page.filter === "GB" && v.accent !== "GB") continue
      out.push(v)
    }
    return out
  }
  readonly property var agentChoices: {
    var out = [{ label: "Main agent", value: "" }]
    for (var i = 0; i < s.voiceAgents.length; i++) {
      var n = String((s.voiceAgents[i] || {}).name || "")
      if (n !== "") out.push({ label: n.charAt(0).toUpperCase() + n.slice(1), value: n })
    }
    return out
  }

  PageHeader {
    width: parent.width
    title: "Voice"
    subtitle: "How replies sound, and how what you say becomes text."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
  }

  SettingsGroup {
    width: parent.width
    title: "SPEAKING"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    ToggleRow {
      width: parent.width
      label: "Speak replies aloud"
      hint: "Off leaves the reply as text, in the readout and the conversation."
      checked: page.speaks
      changed: page.s.changed("speakReplies")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("speakReplies", !checked)
      onReset: page.s.resetKey("speakReplies")
    }

    SettingRow {
      width: parent.width
      label: "Voice and speed"
      hint: "Pick from the library below, or on each agent's card beside its speed and instructions."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      Button {
        text: "Agents ›"
        bordered: true
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.s.goTo("agents", "main")
      }
    }

    ToggleRow {
      width: parent.width
      label: "Sounds for listening, heard and done"
      hint: "A tone when the wake word lands, one when it has heard you, a chime when a long task ends."
      help: "So you know where it is without looking. Push-to-talk gets no opening " +
            "tone; the key is the signal."
      checked: page.s.setting("chimes", true) === true
      changed: page.s.changed("chimes")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("chimes", !checked)
      onReset: page.s.resetKey("chimes")
    }
  }

  SettingsGroup {
    width: parent.width
    title: "VOICES"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    SettingRow {
      width: parent.width
      stacked: true
      label: "Library"
      hint: page.s.voicesOnDisk.length + " of " + page.s.rawVoiceOptions.length +
            " on this machine. Test plays about a minute at the main agent's speed."
      help: "Every voice comes from the same pinned piper-voices revision as the installer and " +
            "is checked against its hash in models.lock before it is kept. low and medium are " +
            "about 63MB, high about 118MB. The default voice cannot be removed: it is what " +
            "speaks when another voice is missing."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      SegmentedChoice {
        options: [
          { value: "all", label: "All" },
          { value: "here", label: "Downloaded" },
          { value: "female", label: "Female" },
          { value: "male", label: "Male" },
          { value: "GB", label: "British" }
        ]
        value: page.filter
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onCommitted: function(v) { page.filter = v }
      }
    }

    Text {
      visible: page.s.fetchError !== ""
      width: parent.width
      wrapMode: Text.Wrap
      text: "Download failed — " + page.s.fetchError
      color: Commons.Color.urgent
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.bodySmall
      textFormat: Text.PlainText
    }

    Column {
      width: parent.width
      spacing: Style.space(2)
      Repeater {
        model: page.shown
        VoiceLibraryRow {
          required property var modelData
          width: parent.width
          label: modelData.label.split(" — ")[0]
          detail: modelData.label.split(" — ")[1] + "  ·  " + modelData.mb + "MB"
          users: page.s.voiceUsers(modelData.value).join(", ")
          onDisk: page.s.voicesOnDisk.indexOf(modelData.value) >= 0
          playing: page.s.samplePlaying === modelData.value
          downloading: page.s.fetching === modelData.value
          queued: page.s.fetchQueue.indexOf(modelData.value) >= 0
          percent: page.s.fetchPct
          removable: modelData.value !== "lessac-medium" && users === ""
          agents: page.agentChoices
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onTest: page.s.playSample(modelData.value)
          onDownload: page.s.fetchVoice(modelData.value)
          onRemove: page.s.removeVoice(modelData.value)
          onUse: function(who) { page.s.assignVoice(who, modelData.value) }
        }
      }
    }
  }

  SettingsGroup {
    width: parent.width
    title: "HEARING YOU"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    SettingRow {
      width: parent.width
      stacked: true
      label: "Transcription model"
      hint: "Larger is more accurate and slower to answer. tiny.en is right for most voices."
      changed: page.s.changed("model")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onReset: page.s.resetKey("model")
      SegmentedChoice {
        options: [
          { value: "tiny.en", label: "tiny.en", tooltip: "Fastest. The default." },
          { value: "base.en", label: "base.en", tooltip: "More accurate, a little slower." },
          { value: "small.en", label: "small.en", tooltip: "Most accurate, noticeably slower on a laptop." }
        ]
        value: page.s.setting("model", "tiny.en")
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onCommitted: function(v) { page.s.put("model", v) }
      }
    }

    SettingRow {
      width: parent.width
      stacked: true
      label: "Live transcript while you speak"
      hint: "Rough text shown as you talk, before Whisper returns."
      help: "It needs the Vosk model resident. On the Vosk wake engine that model is " +
            "already loaded, so it is free; on openWakeWord or sherpa-onnx it is an extra 114MB. " +
            "\"Auto\" shows it only when it is free."
      changed: page.s.changed("livePartials")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onReset: page.s.resetKey("livePartials")
      SegmentedChoice {
        options: [
          { value: "auto", label: "Auto", tooltip: "Only when it costs nothing" },
          { value: "on", label: "On", tooltip: "Always; costs 114MB on the other engines" },
          { value: "off", label: "Off" }
        ]
        value: page.s.setting("livePartials", "auto")
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onCommitted: function(v) { page.s.put("livePartials", v) }
      }
    }
  }
}
