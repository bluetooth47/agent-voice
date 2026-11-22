import QtQuick
import qs.Commons
import qs.Commons as Commons

// Small bars, one per hour (or per anything): when the agents were busy
// today. The tallest bar is the full height; the exact number is on the
// line underneath for the bar under the pointer (or the cursor, from the
// keyboard), never only in a tooltip.
//
//   MiniBars { width: parent.width; values: stats.byHour; unit: "turns" }
//
// `labels` names each bar; without it bars are hours, "00:00" to "23:00".
// `highlight` marks one bar (the current hour). All zeros draws an honest
// "Nothing yet" rather than a flat line that looks like a broken chart.
//
// Keyboard: one Tab stop; Left/Right walk the bars.
FocusScope {
  id: bars

  property var values: []
  property var labels: []
  property string unit: ""
  property int highlight: -1
  property string emptyText: "Nothing yet."
  property real barsHeight: Style.space(48)

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  readonly property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  property int cursor: -1
  readonly property real peak: {
    var m = 0
    for (var i = 0; i < values.length; i++) m = Math.max(m, Number(values[i]) || 0)
    return m
  }

  function labelAt(i) {
    if (labels && i < labels.length) return String(labels[i])
    return (i < 10 ? "0" : "") + i + ":00"
  }
  function readout(i) {
    if (i < 0 || i >= values.length) return ""
    return labelAt(i) + " · " + (Number(values[i]) || 0) + (unit !== "" ? " " + unit : "")
  }

  activeFocusOnTab: values.length > 0
  implicitHeight: column.implicitHeight
  width: parent ? parent.width : 300

  Keys.onLeftPressed: cursor = Math.max(0, (cursor < 0 ? values.length : cursor) - 1)
  Keys.onRightPressed: cursor = Math.min(values.length - 1, cursor + 1)
  onActiveFocusChanged: if (!activeFocus) cursor = -1

  Column {
    id: column
    width: parent.width
    spacing: Style.space(4)

    Item {
      width: parent.width
      height: bars.barsHeight
      Row {
        id: barRow
        anchors.fill: parent
        spacing: Math.max(1, Style.space(2))
        visible: bars.peak > 0
        Repeater {
          model: bars.values.length
          Item {
            id: slot
            required property int index
            width: Math.max(1, (barRow.width - barRow.spacing * (bars.values.length - 1)) / Math.max(1, bars.values.length))
            height: barRow.height
            readonly property real v: Number(bars.values[index]) || 0
            Rectangle {
              anchors.bottom: parent.bottom
              width: parent.width
              // A non-zero value always shows at least a sliver.
              height: slot.v <= 0 ? 1 : Math.max(Style.space(2), parent.height * slot.v / bars.peak)
              radius: Math.min(width / 2, Style.space(2))
              color: slot.index === bars.cursor || hover.containsMouse ? bars.accent
                     : slot.index === bars.highlight ? Qt.rgba(bars.accent.r, bars.accent.g, bars.accent.b, 0.7)
                     : slot.v <= 0 ? Qt.rgba(bars.foreground.r, bars.foreground.g, bars.foreground.b, 0.12)
                     : Qt.rgba(bars.foreground.r, bars.foreground.g, bars.foreground.b, 0.45)
            }
            MouseArea {
              id: hover
              anchors.fill: parent
              hoverEnabled: true
              onContainsMouseChanged: if (containsMouse) bars.cursor = slot.index
                                      else if (bars.cursor === slot.index && !bars.activeFocus) bars.cursor = -1
            }
          }
        }
      }
      Text {
        anchors.centerIn: parent
        visible: bars.peak <= 0
        text: bars.emptyText
        textFormat: Text.PlainText
        color: bars.dim
        font.family: bars.fontFamily
        font.pixelSize: Style.font.caption
      }
    }
    Text {
      width: parent.width
      // Always takes its line, so pointing at a bar never moves the page.
      text: bars.cursor >= 0 ? bars.readout(bars.cursor) : " "
      textFormat: Text.PlainText
      color: bars.dim
      font.family: bars.fontFamily
      font.pixelSize: Style.font.caption
    }
  }
}
