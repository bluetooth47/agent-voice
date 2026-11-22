import QtQuick
import qs.Commons
import qs.Commons as Commons

// One numbered stage of a pipeline, with the line that joins it to the
// next: how listening is drawn (feedback item 18) -- sound in, gate, wake
// word, second check, transcription -- so the order things happen in is
// on the page rather than in a paragraph.
//
//   StageBlock { number: 2; title: "Gate"; summary: "-38 dB"; tone: "active"
//                SettingRow { ... } }
//   StageBlock { number: 3; title: "Wake word"; last: true; ... }
//
// `tone` colours the number's ring as StatusCard does; `last` drops the
// connector under the final stage.
Item {
  id: stage

  property int number: 1
  property string title: ""
  property string summary: ""
  property string tone: "idle"
  property bool last: false

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property color urgent: Commons.Color.urgent
  readonly property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  readonly property color toneColor: tone === "alert" ? urgent
                                     : tone === "busy" ? accent
                                     : tone === "active" ? foreground : dim
  readonly property int disc: Style.space(24)

  default property alias body: inner.data

  implicitHeight: column.implicitHeight + (last ? 0 : Style.space(14))
  height: implicitHeight

  Rectangle {
    id: ring
    width: stage.disc
    height: width
    radius: width / 2
    color: "transparent"
    border.width: Math.max(1, Style.space(2))
    border.color: stage.toneColor
    Text {
      anchors.centerIn: parent
      text: String(stage.number)
      color: stage.toneColor
      font.family: stage.fontFamily
      font.pixelSize: Style.font.caption
      font.bold: true
    }
  }
  // The connector runs from under the ring to the bottom of this block,
  // where the next stage's ring begins.
  Rectangle {
    visible: !stage.last
    x: ring.width / 2 - width / 2
    y: ring.height + Style.space(2)
    width: Math.max(1, Style.space(2))
    height: stage.height - y
    color: Qt.rgba(stage.foreground.r, stage.foreground.g, stage.foreground.b, 0.25)
  }

  Column {
    id: column
    x: stage.disc + Style.space(12)
    width: stage.width - x
    spacing: Style.space(6)
    Row {
      width: parent.width
      spacing: Style.space(8)
      height: Math.max(stage.disc, titleText.implicitHeight)
      Text {
        id: titleText
        anchors.verticalCenter: parent.verticalCenter
        width: Math.min(implicitWidth, parent.width * 0.6)
        text: stage.title
        textFormat: Text.PlainText
        elide: Text.ElideRight
        color: stage.foreground
        font.family: stage.fontFamily
        font.pixelSize: Style.font.body
        font.bold: true
      }
      Text {
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width - titleText.width - parent.spacing
        text: stage.summary
        textFormat: Text.PlainText
        elide: Text.ElideRight
        color: stage.dim
        font.family: stage.fontFamily
        font.pixelSize: Style.font.caption
      }
    }
    Column {
      id: inner
      width: parent.width
      spacing: Style.space(6)
    }
  }
}
