import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import ".."
import "../ui"

// What is happening right now, and anything that needs fixing.
//
// The page the overlay opens on. Everything here is a reading, or a link to
// the page where the thing it reads is changed -- the only controls are the
// two that change what the microphone is doing, because those are what
// somebody opening this in a hurry is looking for.
Column {
  id: page

  required property var s

  spacing: Style.space(18)

  PageHeader {
    width: parent.width
    title: "Overview"
    subtitle: "What Agent Voice is doing, and anything that needs fixing."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
  }

  // The service, and the microphone: two controls, not one. The switch
  // stops the service, which unloads ~600MB and takes seconds to come back;
  // the microphone button releases the mic and keeps everything warm.
  StatusCard {
    width: parent.width
    icon: !page.s.serviceActive || page.s.vState === "off" ? "\u{f036d}" : "\u{f036c}"
    title: "Voice service"
    subtitle: page.s.stateLabel
    tone: page.s.stateTone
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    Row {
      spacing: Style.space(10)

      Button {
        anchors.verticalCenter: parent.verticalCenter
        visible: page.s.serviceActive
        text: page.s.vState === "off" ? "Unmute mic" : "Mute mic"
        iconText: page.s.vState === "off" ? "\u{f036c}" : "\u{f036d}"
        bordered: true
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.s.toggleMic()
      }
      ToggleSwitch {
        anchors.verticalCenter: parent.verticalCenter
        visible: page.s.engineInstalled
        checked: page.s.serviceActive
        busy: page.s.serviceBusy
        foreground: page.s.foreground
        onToggled: page.s.toggleService()
      }
    }
  }

  // The most important control in the interface when a turn is running:
  // it kills the agent's whole process group, not just the talking.
  Button {
    visible: page.s.turnRunning
    text: "Stop " + (page.s.lastWho || page.s.mainAgent || "the agent")
    iconText: "\u{f06d7}"
    bordered: true
    foreground: page.s.urgent
    accent: page.s.urgent
    fontFamily: page.s.fontFamily
    onClicked: page.s.stopTurn()
  }

  Column {
    width: parent.width
    spacing: Style.space(6)

    Item {
      width: parent.width
      height: micLabel.implicitHeight
      Text {
        id: micLabel
        text: "Microphone"
        color: page.s.foreground
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.body
      }
      Text {
        anchors.right: parent.right
        text: "gate " + page.s.setting("micThresholdDb", -38) + " dBFS · adjust ›"
        color: gateLink.containsMouse ? page.s.foreground : page.s.dim
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
        MouseArea {
          id: gateLink
          anchors.fill: parent
          anchors.margins: -Style.space(4)
          hoverEnabled: true
          cursorShape: Qt.PointingHandCursor
          onClicked: page.s.goTo("listening", "")
        }
      }
    }
    LevelMeter {
      width: parent.width
      levelDb: page.s.serviceActive ? page.s.levelDb : -99
      gateDb: page.s.setting("micThresholdDb", -38)
      idleText: page.s.serviceActive ? "no reading — the microphone is off"
                                     : "no reading — the service is off"
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
    }
  }

  SettingsGroup {
    width: parent.width
    visible: page.s.problems.length > 0
    title: "NEEDS ATTENTION"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    Repeater {
      model: page.s.problems
      StatusCard {
        required property var modelData
        width: parent ? parent.width : 0
        icon: "\u{f0026}"
        title: modelData.text
        tone: "alert"
        status: modelData.page ? "fix ›" : ""
        clickable: !!modelData.page
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.s.goTo(modelData.page, modelData.agent || "")
      }
    }
  }

  SettingsGroup {
    width: parent.width
    title: "AGENTS"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    StatusCard {
      width: parent.width
      readonly property string st: page.s.agentStatus("")
      icon: "\u{f06a9}"
      title: page.s.usingEndpoint ? "Endpoint · " + page.s.setting("endpointModel", "")
                                  : (page.s.mainAgent ? page.s.programLabel(page.s.mainAgent) : "No default agent")
      subtitle: "“" + page.s.activePhrase + "” · default"
      status: st
      tone: page.s.statusTone(st)
      clickable: true
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onClicked: page.s.goTo("agents", "main")
    }

    Repeater {
      model: page.s.voiceAgents
      StatusCard {
        required property var modelData
        readonly property string name: String(modelData.name || "")
        readonly property string st: page.s.agentStatus(name)
        width: parent ? parent.width : 0
        icon: "\u{f06a9}"
        title: name || "unnamed agent"
        subtitle: "“" + name + "” · " + page.s.programLabel(String(modelData.agent || "claude"))
                  + (modelData.model ? " · " + modelData.model : "")
        status: st
        tone: String((page.s.crewInfo(name) || {}).problem || "") !== "" ? "alert" : page.s.statusTone(st)
        clickable: true
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.s.goTo("agents", name)
      }
    }

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      text: page.s.voiceAgents.length === 0
            ? "One agent. Add more on the Agents page, each woken by its own name."
            : "Start a sentence with a name to talk to that agent."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
  }

  SettingsGroup {
    width: parent.width
    visible: page.s.lastTranscript !== ""
    title: "LAST EXCHANGE"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    Text {
      width: parent.width
      visible: page.s.lastWho !== ""
      text: page.s.lastWho
      textFormat: Text.PlainText
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      maximumLineCount: 3
      elide: Text.ElideRight
      // A transcript of speech: attacker-shaped input as far as the UI is
      // concerned, so never markup.
      text: page.s.lastTranscript
      textFormat: Text.PlainText
      color: page.s.foreground
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.body
    }
    Item {
      width: parent.width
      visible: page.s.lastReply !== ""
      height: replyText.implicitHeight
      Rectangle {
        width: Style.space(2)
        height: parent.height
        color: Qt.rgba(page.s.foreground.r, page.s.foreground.g, page.s.foreground.b, 0.35)
      }
      Text {
        id: replyText
        x: Style.space(10)
        width: parent.width - x
        wrapMode: Text.WordWrap
        maximumLineCount: 4
        elide: Text.ElideRight
        text: page.s.lastReply
        textFormat: Text.PlainText
        color: page.s.dim
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.body
      }
    }
    Button {
      text: "Open the whole conversation"
      iconText: "\u{f0b79}"
      bordered: true
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onClicked: page.s.showPage("history")
    }
  }
}
