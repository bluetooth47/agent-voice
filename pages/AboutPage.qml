import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import ".."
import "../ui"

// What is installed, and the two things done to the installation itself:
// repairing it, and removing it.
Column {
  id: page

  required property var s

  spacing: Style.space(18)

  PageHeader {
    width: parent.width
    title: "About"
    subtitle: "Agent Voice" + (page.s.version !== "" ? " " + page.s.version : "") +
              " — wake word, spoken replies and the knobs that govern them."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
  }

  SettingsGroup {
    width: parent.width
    title: "WHAT IS INSTALLED"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    Repeater {
      model: [
        { label: "Voice engine",
          value: page.s.engineInstalled ? "installed" : "not installed",
          ok: page.s.engineInstalled },
        { label: "Service",
          value: page.s.serviceActive ? "running" : "stopped — it does not start itself after a reboot",
          ok: true },
        { label: "Wake engine",
          value: page.s.owwLive ? "openWakeWord" : page.s.usingOww ? "Vosk (openWakeWord is not installed)"
               : page.s.sherpaLive ? "sherpa-onnx" : page.s.usingSherpa ? "Vosk (sherpa-onnx is not installed)"
               : "Vosk",
          ok: !(page.s.usingOww && !page.s.owwAvailable) && !(page.s.usingSherpa && !page.s.sherpaAvailable) },
        { label: "openWakeWord",
          value: page.s.owwAvailable ? "installed" : "not installed (optional, about 154MB)",
          ok: true },
        { label: "sherpa-onnx",
          value: page.s.sherpaAvailable ? "installed" : "not installed (optional, about 60MB)",
          ok: true },
        { label: "Voices on disk",
          value: page.s.voicesOnDisk.length === 0 ? "none found"
                 : page.s.voicesOnDisk.map(function(v) { return page.s.voiceName(v) }).join(", "),
          ok: page.s.voicesOnDisk.length > 0 },
        { label: "Main agent",
          value: page.s.usingEndpoint ? "an OpenAI-compatible endpoint"
                 : (page.s.mainAgent ? page.s.programLabel(page.s.mainAgent) : "none — set one with `omarchy default agent`"),
          ok: page.s.usingEndpoint || page.s.mainAgent !== "" }
      ]
      Item {
        required property var modelData
        width: parent ? parent.width : 0
        height: Math.max(rowLabel.implicitHeight, rowValue.implicitHeight)
        Text {
          id: rowLabel
          width: Style.space(150)
          text: modelData.label
          color: page.s.foreground
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
        Text {
          id: rowValue
          anchors.left: rowLabel.right
          anchors.right: parent.right
          wrapMode: Text.WordWrap
          text: modelData.value
          textFormat: Text.PlainText
          color: modelData.ok ? page.s.dim : page.s.urgent
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
    }
  }

  SettingsGroup {
    width: parent.width
    title: "MAINTENANCE"
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
      Button {
        text: page.s.engineInstalled ? "Repair…" : "Install…"
        bordered: true
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
      Button {
        text: "Install…"
        bordered: true
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
      Button {
        text: "Install…"
        bordered: true
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.s.fetchNow(["--sherpa"])
      }
    }
  }

  // Last, and the only red control in the overlay.
  SettingsGroup {
    width: parent.width
    title: "REMOVE"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    SettingRow {
      width: parent.width
      label: "Remove Agent Voice"
      hint: "The engine, the service and the widget in one go. Your trained verifiers, " +
            "recordings and API keys are kept, and it says where they are on the way out."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      Button {
        text: "Remove Agent Voice…"
        bordered: true
        foreground: page.s.urgent
        accent: page.s.urgent
        fontFamily: page.s.fontFamily
        onClicked: page.s.removeEverything()
      }
    }
  }
}
