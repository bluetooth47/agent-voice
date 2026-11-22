import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// Where DraggableCards are dropped: one agent's skills, one category of
// notes. It holds its cards (the caller's children) and lights up while a
// card it would take is over it.
//
// `refuse` decides, before anything is emitted, whether a card may land
// here: a function (payload, copy, fromLane) returning "" for yes or the
// reason for no. A refused card is drawn refused with that reason while it
// hovers, and dropping it does nothing -- but says so, under the lane, for
// a few seconds. A drop onto the lane it came from is ignored.
//
//   DropLane {
//     laneId: "sora"; title: "Sora"; count: soraSkills.length
//     refuse: function(p, copy, from) { return p.locked ? "Locked by Theo" : "" }
//     onReceived: function(p, copy, from) { page.moveSkill(p, "sora", copy) }
//     Repeater { model: soraSkills; DraggableCard { ... } }
//   }
Rectangle {
  id: lane

  property string laneId: ""
  property string title: ""
  property string subtitle: ""
  property int count: 0
  property string emptyText: "Nothing here. Drag a card in, or use its Move to… menu."
  property string dragKey: "agentvoice-card"
  property var refuse: null

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property color urgent: Commons.Color.urgent
  readonly property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  readonly property bool hovered: drop.containsDrag
  property string refusal: ""
  property string said: ""

  signal received(var payload, bool copy, string fromLane)

  default property alias cards: inner.data

  // The drag's source is a DraggableCard's ghost, typed only as QObject,
  // so its properties are read by name.
  function fromOf(src) { return src ? String(src["laneId"]) : "" }
  function deliver(src) { received(src["payload"], src["copying"] === true, fromOf(src)) }
  function judge(src) {
    if (!src || src["payload"] === undefined) return "Not something this lane takes."
    if (fromOf(src) === laneId) return ""
    if (typeof refuse === "function") return String(refuse(src["payload"], src["copying"] === true, fromOf(src)) || "")
    return ""
  }

  Timer { id: saidTimer; interval: 5000; onTriggered: lane.said = "" }

  implicitHeight: column.implicitHeight + Style.space(20)
  height: implicitHeight
  radius: Style.cornerRadius
  color: hovered && refusal === "" ? Qt.rgba(accent.r, accent.g, accent.b, 0.08) : "transparent"
  border.width: hovered ? Math.max(1, Style.space(2)) : 1
  border.color: hovered ? (refusal !== "" ? urgent : accent)
                        : Qt.rgba(foreground.r, foreground.g, foreground.b, 0.18)

  DropArea {
    id: drop
    anchors.fill: parent
    keys: [lane.dragKey]
    onEntered: function(drag) { lane.refusal = lane.judge(drag.source) }
    // Again as it moves: Ctrl pressed or let go over the lane changes a
    // move into a copy, which the lane may judge differently.
    onPositionChanged: function(drag) { lane.refusal = lane.judge(drag.source) }
    onExited: lane.refusal = ""
    onDropped: function(ev) {
      var src = ev.source
      var why = lane.judge(src)
      lane.refusal = ""
      if (!src || lane.fromOf(src) === lane.laneId) return
      if (why !== "") { lane.said = why; saidTimer.restart(); return }
      ev.accept()
      lane.deliver(src)
    }
  }

  Column {
    id: column
    x: Style.space(10)
    y: Style.space(10)
    width: parent.width - Style.space(20)
    spacing: Style.space(6)

    Row {
      width: parent.width
      spacing: Style.space(6)
      visible: lane.title !== ""
      Text {
        width: Math.min(implicitWidth, parent.width - countText.width - parent.spacing)
        text: lane.title
        textFormat: Text.PlainText
        elide: Text.ElideRight
        color: lane.foreground
        font.family: lane.fontFamily
        font.pixelSize: Style.font.body
        font.bold: true
      }
      Text {
        id: countText
        text: lane.count > 0 ? String(lane.count) : ""
        color: lane.dim
        font.family: lane.fontFamily
        font.pixelSize: Style.font.caption
        anchors.verticalCenter: parent.verticalCenter
      }
    }
    Hint {
      width: parent.width
      text: lane.subtitle
      foreground: lane.foreground
      fontFamily: lane.fontFamily
    }
    Column {
      id: inner
      width: parent.width
      spacing: Style.space(6)
    }
    Text {
      width: parent.width
      visible: lane.count === 0
      text: lane.emptyText
      textFormat: Text.PlainText
      wrapMode: Text.WordWrap
      color: lane.dim
      font.family: lane.fontFamily
      font.pixelSize: Style.font.caption
    }
    Text {
      width: parent.width
      visible: text !== ""
      text: lane.hovered ? lane.refusal : lane.said
      textFormat: Text.PlainText
      wrapMode: Text.WordWrap
      color: lane.urgent
      font.family: lane.fontFamily
      font.pixelSize: Style.font.caption
    }
  }
}
