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
      hint: "Each agent's voice and speaking speed live on its card, beside its other settings."
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
