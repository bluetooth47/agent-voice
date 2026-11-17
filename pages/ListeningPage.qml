import QtQuick
import Quickshell
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import ".."
import "../ui"

// How it hears you: the wake word, the engine behind it, the microphone
// gate, and the verifier that knows your voice.
//
// These were four separate boxes -- "wake word", "train wake word to your
// voice", "training your own wake word" and "microphone" -- although they
// are one subject: the gate decides what reaches the wake grammar, and the
// verifier refines what the engine already heard.
Column {
  id: page

  required property var s

  spacing: Style.space(18)

  PageHeader {
    width: parent.width
    title: "Listening"
    subtitle: "The wake word, the engine that hears it, and where your voice ends and the room begins."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
  }

  SettingsGroup {
    width: parent.width
    title: "WAKE WORD"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    SettingRow {
      width: parent.width
      stacked: true
      label: "Engine"
      hint: page.s.usingOww
            ? "Better at rejecting sound-alikes, and can learn your voice. Hears only its own phrase."
            : page.s.usingSherpa
            ? "Any phrase, and your other agents' names, with far fewer false wakes than Vosk."
            : "Any phrase, and your other agents' names. Weaker at rejecting sound-alikes."
      changed: page.s.changed("engine")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onReset: page.s.resetKey("engine")
      SegmentedChoice {
        options: page.s.engineOptions
        value: page.s.engine
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onCommitted: function(v) {
          page.s.put("engine", v)
          if (v === "openwakeword" && !page.s.owwAvailable) page.s.fetchNow(["--oww"])
          if (v === "sherpa" && !page.s.sherpaAvailable) page.s.fetchNow(["--sherpa"])
        }
      }
    }

    // The state that had no representation at all. Choosing openWakeWord
    // without the package installed left the daemon falling back to Vosk
    // while the page went on showing an openWakeWord model, threshold and
    // verifier. The controls below follow what is actually listening; this
    // says why.
    Column {
      width: parent.width
      spacing: Style.space(6)
      visible: page.s.usingOww && !page.s.owwAvailable

      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        text: "openWakeWord is not installed, so Vosk is listening instead. It can be " +
              "added now — about 154MB, and it brings real rejection plus verifiers " +
              "trained from your own voice."
        color: page.s.urgent
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }
      Button {
        text: "Try installing openWakeWord again…"
        bordered: true
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.s.fetchNow(["--oww"])
      }
    }

    Column {
      width: parent.width
      spacing: Style.space(6)
      visible: page.s.usingSherpa && !page.s.sherpaAvailable

      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        text: "sherpa-onnx is not installed, so Vosk is listening instead. It can be " +
              "added now: about 60MB, for the same phrases and names with far fewer " +
              "false wakes."
        color: page.s.urgent
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }
      Button {
        text: "Try installing sherpa-onnx again…"
        bordered: true
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.s.fetchNow(["--sherpa"])
      }
    }

    SettingRow {
      width: parent.width
      label: "Wake phrase"
      hint: "“" + page.s.activePhrase + "” wakes the main agent. It is set on its card, beside each other agent's name."
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

    KnobRow {
      width: parent.width
      visible: page.s.owwLive
      foreground: page.s.foreground; fontFamily: page.s.fontFamily
      label: "Detection threshold"
      unit: "%"
      description: "Higher rejects more near misses; lower wakes more easily."
      help: "Measured on a 2014 MacBook Pro: the real phrase peaks near 99 and a " +
            "phonetically similar phrase near 90, so 90 rejects the near miss and " +
            "still fires reliably."
      value: page.s.setting("owwThresholdPct", 90)
      defaultValue: page.s.defaults.owwThresholdPct !== undefined ? page.s.defaults.owwThresholdPct : NaN
      changed: page.s.changed("owwThresholdPct")
      minimum: 10; maximum: 99; stepSize: 1
      onCommitted: function(v) { page.s.put("owwThresholdPct", v) }
      onReset: page.s.resetKey("owwThresholdPct")
    }

    // sherpa-onnx shares Vosk's phrase above -- both take it as text -- but
    // not its confidence bar: it has a keyword threshold of its own.
    KnobRow {
      width: parent.width
      visible: page.s.sherpaLive
      foreground: page.s.foreground; fontFamily: page.s.fontFamily
      label: "Detection threshold"
      unit: "%"
      description: "Higher rejects more sound-alikes; lower wakes more easily."
      help: "Measured on synthesized speech: anywhere from 15 to 35 caught the same " +
            "wakes, and higher mostly cut sound-alikes such as \"Sarong\" for \"Sarah\". " +
            "At 50 it missed about half the real ones."
      value: page.s.setting("sherpaThresholdPct", 25)
      defaultValue: page.s.defaults.sherpaThresholdPct !== undefined ? page.s.defaults.sherpaThresholdPct : NaN
      changed: page.s.changed("sherpaThresholdPct")
      minimum: 10; maximum: 60; stepSize: 5
      onCommitted: function(v) { page.s.put("sherpaThresholdPct", v) }
      onReset: page.s.resetKey("sherpaThresholdPct")
    }

    KnobRow {
      width: parent.width
      visible: !page.s.owwLive && !page.s.sherpaLive
      foreground: page.s.foreground; fontFamily: page.s.fontFamily
      label: "Grammar confidence"
      unit: "%"
      description: "How sure it must be that it heard the phrase."
      help: "Weak against phonetic neighbours by nature: a grammar must pick between " +
            "the phrase and anything-else, so \"hey cloud\" scores as high as \"hey " +
            "claude\". Switch engines if a phone keeps waking it."
      value: page.s.setting("wakeConfidencePct", 70)
      defaultValue: page.s.defaults.wakeConfidencePct !== undefined ? page.s.defaults.wakeConfidencePct : NaN
      changed: page.s.changed("wakeConfidencePct")
      minimum: 0; maximum: 100; stepSize: 5
      onCommitted: function(v) { page.s.put("wakeConfidencePct", v) }
      onReset: page.s.resetKey("wakeConfidencePct")
    }
  }

  SettingsGroup {
    width: parent.width
    title: "MICROPHONE"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    // The gate is drawn on the live meter: the only way to set it well is to
    // talk and see where your voice falls against the line.
    LevelMeter {
      width: parent.width
      levelDb: page.s.serviceActive ? page.s.levelDb : -99
      gateDb: page.s.setting("micThresholdDb", -38)
      minDb: -60
      idleText: page.s.serviceActive ? "no reading — the microphone is off"
                                     : "no reading — start the service to see your level"
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
    }

    KnobRow {
      width: parent.width
      foreground: page.s.foreground; fontFamily: page.s.fontFamily
      label: "Microphone gate"
      unit: " dBFS"
      description: "The red line above. Talk normally and put it under your voice."
      // It has one job on both engines -- deciding which frames count as you
      // talking, which is what ends your turn -- and one extra on Vosk.
      help: "Where your voice stops and the room starts. Anything above the line " +
            "counts as you talking, so this is what ends your turn: once you have " +
            "been under the line for the pause set on the Conversation page, it " +
            "stops listening. Set it too low and room noise holds the turn open; too " +
            "high and a quiet word cuts you off." +
            (page.s.owwLive || page.s.sherpaLive ? "" :
              "\n\nOn Vosk it also gates the wake word: quieter frames never reach " +
              "the grammar, so the phrase cannot be matched against room noise.")
      value: page.s.setting("micThresholdDb", -38)
      defaultValue: page.s.defaults.micThresholdDb !== undefined ? page.s.defaults.micThresholdDb : NaN
      changed: page.s.changed("micThresholdDb")
      minimum: -60; maximum: -20; stepSize: 1
      onCommitted: function(v) { page.s.put("micThresholdDb", v) }
      onReset: page.s.resetKey("micThresholdDb")
    }

    // Not a setting, deliberately: it is a security property, and a setting
    // is a thing that gets switched off once and forgotten.
    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      text: "\u{f033e}  The microphone closes while the screen is locked and opens again " +
            "when you unlock. A microphone you had muted stays muted."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
  }

  SettingsGroup {
    width: parent.width
    title: "ONLY YOUR VOICE"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    // Three states, not two. A trained verifier that is switched off read
    // as "no verifier yet" -- the one message that would send someone back
    // to redo work they had already done.
    StatusCard {
      width: parent.width
      icon: page.s.vVerifier ? "\u{f0483}" : "\u{f0484}"
      title: !page.s.owwLive ? "Needs openWakeWord"
             : page.s.vVerifier ? "In use for “" + page.s.activePhrase + "”"
             : page.s.setting("useVerifier", true) !== true ? "Trained, and switched off"
             : "Not trained for “" + page.s.activePhrase + "” yet"
      subtitle: !page.s.owwLive
                ? "Verifiers attach to an openWakeWord model; Vosk has none to attach one to."
                : page.s.vVerifier ? "Only your voice saying the phrase gets through."
                : page.s.setting("useVerifier", true) !== true ? "Anyone can wake it. The training is kept."
                : "Anyone saying the phrase can wake it. Verifiers are per phrase."
      tone: page.s.vVerifier ? "active" : "idle"
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily

      // A disabled button that does nothing when clicked reads as a bug, not
      // as a precondition -- so on Vosk the button becomes the fix instead:
      // it switches the engine, which is the thing that was missing.
      Button {
        text: page.s.owwLive ? "Train a verifier from your voice…"
              : !page.s.owwAvailable ? "Install openWakeWord to enable this"
              : "Switch to openWakeWord to enable this"
        bordered: true
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.s.trainVerifier()
      }
    }

    // The switch that had no switch. `use_verifier` existed in OwwWake since
    // it was written and nothing passed it, so the only way to stop verifying
    // was to delete the .joblib -- which also threw the training away.
    ToggleRow {
      width: parent.width
      label: "Only wake for my voice"
      hint: "Off lets anyone wake it. Your training stays on disk."
      help: "The stock wake models are speaker independent, so a podcast or phone " +
            "saying the phrase gets through. A verifier trained on your voice is the " +
            "only layer that knows who is talking — which also means it ignores " +
            "anyone else at this computer, with nothing to say why."
      disabledReason: page.s.owwLive ? "" : "Only with openWakeWord."
      checked: page.s.setting("useVerifier", true) === true
      changed: page.s.changed("useVerifier")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("useVerifier", !checked)
      onReset: page.s.resetKey("useVerifier")
    }
  }

  // Advanced, and folded: a few hours in a notebook is not a setting.
  SettingsGroup {
    id: ownPhrase
    width: parent.width
    visible: page.s.owwLive
    title: "A PHRASE OF YOUR OWN"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
    property bool open: false

    SettingRow {
      width: parent.width
      label: "Train a new wake phrase"
      hint: "About 2.5 hours in a free Colab notebook. You edit two lines: the phrase and the output name."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      Button {
        text: ownPhrase.open ? "Hide" : "How…"
        bordered: true
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: ownPhrase.open = !ownPhrase.open
      }
    }

    Column {
      width: parent.width
      visible: ownPhrase.open
      spacing: Style.space(8)

      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        text: "A verifier refines an existing model; it cannot create a new phrase. " +
              "For one openWakeWord was not shipped with, train one in a Colab notebook " +
              "— about 2.5 hours on the free tier, 90 minutes on Colab Pro.\n\n" +
              "Only the small classifier head is trained; the feature models it sits on " +
              "ship with openWakeWord and do not change. That is why it is quick, and " +
              "why training is network-bound rather than GPU-bound."
        color: page.s.dim
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }
      Button {
        text: "Open the training notebook…"
        bordered: true
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: Quickshell.execDetached(["omarchy-launch-browser",
          "https://github.com/alfiedennen/openwakeword-colab-2026"])
      }
      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        text: "Upstream's own notebook has not been maintained since 2023; this one is " +
              "patched for current Python and torchaudio.\n\nSave the .onnx it gives you " +
              "into ~/.local/share/agentvoice/wakewords/ and it appears in the phrase " +
              "list above, ready for its own verifier. Check it with 'agentvoice monitor' " +
              "before trusting it: this ships openwakeword 0.4.0, and a model built " +
              "against a newer one should load but has not been proven to."
        color: page.s.dim
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }
    }
  }
}
