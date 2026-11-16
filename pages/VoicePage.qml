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

  readonly property string voice: String(s.setting("voice", "lessac-medium"))
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
      label: "Voice"
      hint: page.s.voiceMissing(page.voice) ? "Not on this machine yet — choosing a voice downloads it (about 60MB)."
                                            : "The main agent's. Other agents can have their own, on Agents."
      disabledReason: page.speaks ? "" : "Replies are not spoken."
      changed: page.s.changed("voice")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onReset: { page.s.resetKey("voice"); page.s.chooseVoice(page.s.defaults.voice || "") }
      Dropdown {
        width: Style.space(250)
        showLabel: false
        fontFamily: page.s.fontFamily
        foreground: page.s.foreground
        options: page.s.voiceOptions
        value: page.voice
        onChanged: function(v) {
          if (v === page.voice) return
          page.s.put("voice", v)
          page.s.chooseVoice(v)
        }
      }
    }

    // Choosing the voice already starts the download. This is for
    // afterwards: a download declined, a terminal closed, no network at the
    // time. Without it the only way back would be to pick a different voice
    // and pick this one again.
    Column {
      width: parent.width
      spacing: Style.space(6)
      visible: page.s.voiceMissing(page.voice)

      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        text: "“" + page.s.voiceName(page.voice) + "” is not on this machine, so it is " +
              "speaking in one that is."
        textFormat: Text.PlainText
        color: page.s.urgent
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }
      Button {
        // Names the voice, as the dropdown does. Passing no name left it to
        // install.sh to read the setting, which is a race the flag exists
        // to avoid.
        text: "Try the download again…"
        bordered: true
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.s.fetchVoice(page.voice)
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
            "already loaded, so it is free; on openWakeWord it is an extra 114MB. " +
            "\"Auto\" shows it only when it is free."
      changed: page.s.changed("livePartials")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onReset: page.s.resetKey("livePartials")
      SegmentedChoice {
        options: [
          { value: "auto", label: "Auto", tooltip: "Only when it costs nothing" },
          { value: "on", label: "On", tooltip: "Always; costs 114MB on openWakeWord" },
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
