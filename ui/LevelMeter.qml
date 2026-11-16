import QtQuick
import qs.Commons
import qs.Commons as Commons

// How loud the microphone is right now, with the gate drawn on it.
//
// The gate decides when a turn has ended and what the wake grammar hears, and
// the only way to set it well is to see where your own voice and the room
// fall against it: talk, watch the bar go past the line; stop, watch it fall
// back under. So the line is on the meter, not on a separate slider.
//
// Above the gate the bar is the foreground colour, below it dim. With no
// reading (`levelDb` at or below `minDb`, as when the service is off) the bar
// is empty and `idleText` is shown instead.
Item {
  id: meter

  property real levelDb: -99
  property real gateDb: NaN
  property real minDb: -70
  property real maxDb: 0
  property string idleText: ""

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property color urgent: Commons.Color.urgent
  // Translucent rather than Qt.darker: darker is dimmer only on a dark
  // theme, and on a light one made every hint as black as the label.
  property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  readonly property bool live: levelDb > minDb
  readonly property bool open: live && !isNaN(gateDb) && levelDb >= gateDb

  function frac(db) {
    return Math.max(0, Math.min(1, (db - minDb) / (maxDb - minDb)))
  }

  implicitWidth: Style.space(200)
  implicitHeight: Math.max(Style.space(12), Math.round(Style.spacing.controlHeight * 0.3))

  Rectangle {
    id: track
    anchors.fill: parent
    radius: Math.min(height / 2, Style.cornerRadius)
    color: Style.selectedFillFor(meter.foreground, meter.accent)
    clip: true

    Rectangle {
      height: parent.height
      width: parent.width * meter.frac(meter.levelDb)
      radius: track.radius
      color: meter.open ? meter.foreground : meter.dim
      Behavior on width { NumberAnimation { duration: 80 } }
    }
  }

  // The gate.
  Rectangle {
    visible: !isNaN(meter.gateDb)
    x: track.width * meter.frac(meter.gateDb) - width / 2
    width: Math.max(2, Style.space(2))
    height: parent.height + Style.space(6)
    anchors.verticalCenter: parent.verticalCenter
    color: meter.urgent
  }

  Text {
    anchors.left: parent.left
    anchors.leftMargin: Style.space(8)
    anchors.verticalCenter: parent.verticalCenter
    visible: !meter.live && meter.idleText !== ""
    text: meter.idleText
    color: meter.dim
    font.family: meter.fontFamily
    font.pixelSize: Style.font.caption
  }
}
