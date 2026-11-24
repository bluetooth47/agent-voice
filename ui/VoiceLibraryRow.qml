import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// One voice in the library: the trash first, then its name and kind, then
// what can be done with it. Knows nothing about settings; the page wires the
// signals to the overlay.
//
// Every column but the name has a fixed width and the name takes what is
// left, so the trash cell, the name and the Test / Download cell start at the
// same x on every row (bug F). The trash cell is reserved whether or not the
// row can be removed: a voice that is not on disk or is in use shows a quiet
// dash there, never a gap that moves the name.
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
  readonly property int trashWidth: Style.space(34)
  readonly property int testWidth: Style.space(124)
  readonly property int useWidth: Style.space(120)

  implicitHeight: Math.max(info.implicitHeight, Style.space(30)) + Style.space(12)

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
    objectName: "voiceName"
    anchors.left: trashCell.right
    anchors.leftMargin: Style.space(4)
    anchors.right: testCell.left
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
      text: row.detail
      color: row.foreground
      opacity: 0.6
      font.family: row.fontFamily
      font.pixelSize: Style.font.bodySmall
      elide: Text.ElideRight
      textFormat: Text.PlainText
    }
    // Who speaks in it, on a line of its own so a long list is not cut off
    // by the detail beside it. Names are the agents' own: PlainText.
    Text {
      visible: row.users !== ""
      width: parent.width
      text: "Used for " + row.users
      color: row.accent
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

  // The trash, first and always there.
  Item {
    id: trashCell
    objectName: "trashCell"
    anchors.left: parent.left
    anchors.leftMargin: Style.space(4)
    anchors.verticalCenter: parent.verticalCenter
    width: row.trashWidth
    height: Style.space(30)
    ActionButton {
      anchors.centerIn: parent
      visible: row.onDisk && row.removable
      iconText: "\u{f01b4}"
      tooltipText: "Delete it from this machine"
      bordered: true
      foreground: row.foreground
      fontFamily: row.fontFamily
      onClicked: row.remove()
    }
    // What stands in for it: why this one cannot go, or nothing to remove yet.
    Text {
      anchors.centerIn: parent
      visible: !(row.onDisk && row.removable)
      text: "–"
      color: row.foreground
      opacity: 0.3
      font.family: row.fontFamily
      font.pixelSize: Style.font.body
      textFormat: Text.PlainText
    }
  }

  Item {
    id: testCell
    objectName: "testCell"
    anchors.right: useCell.left
    anchors.rightMargin: Style.space(6)
    anchors.verticalCenter: parent.verticalCenter
    width: row.testWidth
    height: Style.space(30)

    ActionButton {
      width: parent.width
      visible: row.onDisk
      text: row.playing ? "■ Stop" : "▶ Test"
      tooltipText: row.playing ? "Stop the sample" : "Hear about a minute of this voice"
      bordered: true
      selected: row.playing
      foreground: row.foreground
      fontFamily: row.fontFamily
      onClicked: row.test()
    }
    ActionButton {
      width: parent.width
      visible: !row.onDisk
      enabled: !row.downloading && !row.queued
      text: row.downloading ? ("Downloading " + row.percent + "%")
                            : (row.queued ? "Waiting…" : "Download")
      bordered: true
      foreground: row.foreground
      fontFamily: row.fontFamily
      onClicked: row.download()
    }
  }

  Item {
    id: useCell
    objectName: "useCell"
    anchors.right: parent.right
    anchors.rightMargin: Style.space(4)
    anchors.verticalCenter: parent.verticalCenter
    width: row.useWidth
    height: Style.space(30)
    Dropdown {
      width: parent.width
      showLabel: false
      fontFamily: row.fontFamily
      foreground: row.foreground
      options: [{ label: "Use for…", value: "__pick" }].concat(row.agents)
      value: "__pick"
      onChanged: function(v) { if (v !== "__pick") row.use(v) }
    }
  }
}
