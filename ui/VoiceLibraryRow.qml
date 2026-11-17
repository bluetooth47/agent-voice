import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// One voice in the library: its name and kind on the left, what can be done
// with it on the right. Knows nothing about settings; the page wires the
// signals to the overlay.
//
//   test()      play or stop its minute-long sample (only when on disk)
//   download()  fetch it
//   remove()    delete it from disk
//   use(who)    make it the voice of "" (the main agent) or a named agent
Item {
  id: row

  property string label: ""
  property string detail: ""
  property string users: ""          // "main, friday", or empty
  property bool onDisk: false
  property bool playing: false
  property bool downloading: false
  property bool queued: false
  property int percent: 0
  property bool removable: true
  property var agents: []            // [{label, value}] for "Use for"
  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property string fontFamily: Style.font.family

  signal test()
  signal download()
  signal remove()
  signal use(string who)

  width: parent ? parent.width : 400
  implicitHeight: Math.max(info.implicitHeight, actions.implicitHeight) + Style.space(12)

  Rectangle {
    anchors.fill: parent
    radius: Style.cornerRadius
    color: row.playing ? Qt.rgba(row.accent.r, row.accent.g, row.accent.b, 0.12)
                       : (hover.hovered ? Qt.rgba(row.foreground.r, row.foreground.g, row.foreground.b, 0.05)
                                        : "transparent")
  }
  HoverHandler { id: hover }

  Column {
    id: info
    anchors.left: parent.left
    anchors.leftMargin: Style.space(8)
    anchors.right: actions.left
    anchors.rightMargin: Style.space(8)
    anchors.verticalCenter: parent.verticalCenter
    spacing: Style.space(2)

    Text {
      width: parent.width
      text: row.label
      color: row.foreground
      font.family: row.fontFamily
      font.pixelSize: Style.font.body
      font.bold: row.users !== ""
      elide: Text.ElideRight
      textFormat: Text.PlainText
    }
    Text {
      width: parent.width
      text: row.detail + (row.users !== "" ? "  ·  used by " + row.users : "")
      color: row.foreground
      opacity: 0.6
      font.family: row.fontFamily
      font.pixelSize: Style.font.bodySmall
      elide: Text.ElideRight
      textFormat: Text.PlainText
    }
    // The download's progress, under the name rather than in a dialog.
    Rectangle {
      visible: row.downloading
      width: parent.width
      height: Style.space(3)
      radius: height / 2
      color: Qt.rgba(row.foreground.r, row.foreground.g, row.foreground.b, 0.15)
      Rectangle {
        width: parent.width * Math.max(0.02, row.percent / 100)
        height: parent.height
        radius: parent.radius
        color: row.accent
      }
    }
  }

  Row {
    id: actions
    anchors.right: parent.right
    anchors.rightMargin: Style.space(4)
    anchors.verticalCenter: parent.verticalCenter
    spacing: Style.space(6)

    Button {
      visible: row.onDisk
      text: row.playing ? "■ Stop" : "▶ Test"
      tooltipText: row.playing ? "Stop the sample" : "Hear about a minute of this voice"
      bordered: true
      selected: row.playing
      foreground: row.foreground
      fontFamily: row.fontFamily
      onClicked: row.test()
    }
    Button {
      visible: !row.onDisk
      enabled: !row.downloading && !row.queued
      text: row.downloading ? ("Downloading " + row.percent + "%")
                            : (row.queued ? "Waiting…" : "Download")
      bordered: true
      foreground: row.foreground
      fontFamily: row.fontFamily
      onClicked: row.download()
    }
    Dropdown {
      width: Style.space(120)
      showLabel: false
      fontFamily: row.fontFamily
      foreground: row.foreground
      options: [{ label: "Use for…", value: "__pick" }].concat(row.agents)
      value: "__pick"
      onChanged: function(v) { if (v !== "__pick") row.use(v) }
    }
    Button {
      visible: row.onDisk && row.removable
      iconText: "\u{f01b4}"
      tooltipText: "Delete it from this machine"
      bordered: true
      foreground: row.foreground
      fontFamily: row.fontFamily
      onClicked: row.remove()
    }
  }
}
