import QtQuick
import qs.Commons
import qs.Commons as Commons

// How much of a file's budget its text uses (phase M6, feedback item 10): a
// thin bar and "312 / 1500", counted the way the daemon counts what it sends
// (FileEditor.sentChars), so the number is the one that decides whether the
// end is cut off. Toned as it fills: plain, the accent from 85%, urgent past
// the budget, where it also says by how much.
//
// `note` sits on the left: what a save would do, while the box is typed in.
Item {
  id: meter

  property int used: 0
  property int limit: 1
  property string note: ""
  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property color urgent: Commons.Color.urgent
  property string fontFamily: Style.font.family

  readonly property real ratio: limit > 0 ? used / limit : 0
  readonly property bool over: used > limit
  readonly property color tint: over ? urgent
                                : ratio >= 0.85 ? accent
                                : Qt.rgba(foreground.r, foreground.g, foreground.b, 0.45)

  width: parent ? parent.width : 300
  implicitHeight: track.height + Style.space(3) + Math.max(count.implicitHeight, noteText.implicitHeight)

  Rectangle {
    id: track
    width: parent.width
    height: Style.space(3)
    radius: height / 2
    color: Qt.rgba(meter.foreground.r, meter.foreground.g, meter.foreground.b, 0.12)
    Rectangle {
      width: parent.width * Math.min(1, meter.ratio)
      height: parent.height
      radius: parent.radius
      color: meter.tint
    }
  }
  Text {
    id: noteText
    anchors.top: track.bottom
    anchors.topMargin: Style.space(3)
    anchors.left: parent.left
    anchors.right: count.left
    anchors.rightMargin: Style.space(8)
    elide: Text.ElideRight
    text: meter.note
    textFormat: Text.PlainText
    color: meter.foreground
    opacity: 0.55
    font.family: meter.fontFamily
    font.pixelSize: Style.font.bodySmall
  }
  Text {
    id: count
    anchors.top: track.bottom
    anchors.topMargin: Style.space(3)
    anchors.right: parent.right
    text: meter.used + " / " + meter.limit +
          (meter.over ? " — " + (meter.used - meter.limit) + " over; not saved until shorter" : "")
    textFormat: Text.PlainText
    color: meter.over ? meter.urgent : meter.foreground
    opacity: meter.over ? 1 : 0.55
    font.family: meter.fontFamily
    font.pixelSize: Style.font.bodySmall
  }
}
