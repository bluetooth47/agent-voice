import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// A card that can be moved between DropLanes: a skill between agents, a
// note between categories (feedback items 11 and 12).
//
// Drag moves it; Ctrl held while dragging (or when it is dropped) copies
// it. The pointer is not the only way: "Move to…" (Enter, or the menu key,
// from the keyboard) lists every lane, and copies as well when
// `allowCopy`. That menu is the guaranteed path -- drag and drop under
// Quickshell is the part most likely to misbehave, and a page must never
// depend on it alone.
//
// This piece only *asks*: the drag lands in a DropLane, which emits
// received(), and the menu emits moveRequested() here. Both go to the same
// page function, which does the move and offers an UndoToast. Nothing in
// ui/ moves anything.
//
//   DraggableCard {
//     title: "summarise"; subtitle: "Theo"; laneId: "theo"
//     payload: ({ kind: "skill", name: "summarise", from: "theo" })
//     lanes: [{ id: "sora", label: "Sora" }, { id: "communal", label: "Communal",
//               reason: "Communal reaches every agent" }]
//     onMoveRequested: function(to, copy) { page.moveSkill(payload, to, copy) }
//   }
//
// A lane entry with `disabledReason` is listed but cannot be picked, and
// says why.
Rectangle {
  id: card

  property string title: ""
  property string subtitle: ""
  property string badge: ""
  property var payload: null
  property string laneId: ""
  property var lanes: []
  property bool allowCopy: true
  property string dragKey: "agentvoice-card"
  property bool draggable: true

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  readonly property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  property bool copying: false
  readonly property bool dragging: dragArea.drag.active

  signal moveRequested(string laneId, bool copy)

  function menuEntries() {
    var out = []
    var others = []
    for (var i = 0; i < lanes.length; i++) if (String(lanes[i].id) !== laneId) others.push(lanes[i])
    function add(copy) {
      for (var j = 0; j < others.length; j++) {
        var l = others[j]
        out.push({ value: (copy ? "copy:" : "move:") + l.id, label: String(l.label || l.id),
                   detail: String(l.disabledReason || l.reason || ""),
                   enabled: String(l.disabledReason || "") === "" })
      }
    }
    if (others.length === 0) return [{ value: "", label: "Nowhere else to put it", enabled: false }]
    out.push({ section: "Move to" })
    add(false)
    if (allowCopy) { out.push({ section: "Copy to" }); add(true) }
    return out
  }
  function openMenu() { menu.entries = menuEntries(); menu.open() }

  implicitHeight: row.implicitHeight + Style.space(14)
  height: implicitHeight
  radius: Style.cornerRadius
  color: dragArea.containsMouse || activeFocus ? Style.hoverFillFor(foreground, accent) : "transparent"
  border.width: 1
  border.color: activeFocus ? accent : Qt.rgba(foreground.r, foreground.g, foreground.b, 0.25)
  opacity: dragging && !copying ? 0.4 : 1
  activeFocusOnTab: true

  Keys.onReturnPressed: openMenu()
  Keys.onEnterPressed: openMenu()
  Keys.onMenuPressed: openMenu()

  Row {
    id: row
    x: Style.space(8)
    anchors.verticalCenter: parent.verticalCenter
    width: parent.width - Style.space(16)
    spacing: Style.space(8)
    Text {
      text: "⠿"
      visible: card.draggable
      color: card.dim
      font.family: card.fontFamily
      font.pixelSize: Style.font.body
      anchors.verticalCenter: parent.verticalCenter
    }
    Column {
      width: parent.width - x - moveButton.width - parent.spacing
      anchors.verticalCenter: parent.verticalCenter
      spacing: Style.space(1)
      Row {
        width: parent.width
        spacing: Style.space(6)
        Text {
          width: Math.min(implicitWidth, parent.width - (badgePill.visible ? badgePill.width + parent.spacing : 0))
          text: card.title
          textFormat: Text.PlainText
          elide: Text.ElideRight
          color: card.foreground
          font.family: card.fontFamily
          font.pixelSize: Style.font.body
        }
        Pill {
          id: badgePill
          text: card.badge
          foreground: card.foreground
          fontFamily: card.fontFamily
        }
      }
      Text {
        width: parent.width
        visible: text !== ""
        text: card.subtitle
        textFormat: Text.PlainText
        elide: Text.ElideRight
        color: card.dim
        font.family: card.fontFamily
        font.pixelSize: Style.font.caption
      }
    }
    Button {
      id: moveButton
      text: "Move to…"
      bordered: true
      fontSize: Style.font.caption
      foreground: card.foreground
      fontFamily: card.fontFamily
      anchors.verticalCenter: parent.verticalCenter
      onClicked: card.openMenu()
    }
  }

  MouseArea {
    id: dragArea
    // Leaves the button its own clicks.
    anchors.left: parent.left
    anchors.top: parent.top
    anchors.bottom: parent.bottom
    anchors.right: parent.right
    anchors.rightMargin: moveButton.width + Style.space(12)
    hoverEnabled: true
    enabled: card.draggable
    cursorShape: drag.active ? Qt.ClosedHandCursor : Qt.OpenHandCursor
    drag.target: ghost
    drag.threshold: Style.space(6)
    onPressed: function(mouse) {
      card.copying = (mouse.modifiers & Qt.ControlModifier) !== 0
      // Lifted out of the page, so a Flickable's clip or a lane's
      // bounds cannot cut the ghost off mid-drag.
      var top = card.Window.contentItem
      if (top) {
        var p = card.mapToItem(top, 0, 0)
        ghost.parent = top
        ghost.x = p.x
        ghost.y = p.y
      }
    }
    onPositionChanged: function(mouse) { card.copying = (mouse.modifiers & Qt.ControlModifier) !== 0 }
    onReleased: function(mouse) {
      card.copying = (mouse.modifiers & Qt.ControlModifier) !== 0
      if (ghost.Drag.active) ghost.Drag.drop()
      ghost.parent = card
      ghost.x = 0
      ghost.y = 0
    }
    onCanceled: { ghost.parent = card; ghost.x = 0; ghost.y = 0 }
    onClicked: card.forceActiveFocus()
  }

  // What follows the pointer. A DropLane reads payload, laneId and copying
  // off it (drag.source).
  Rectangle {
    id: ghost
    readonly property var payload: card.payload
    readonly property string laneId: card.laneId
    readonly property bool copying: card.copying
    width: card.width
    height: card.height
    visible: dragArea.drag.active
    radius: card.radius
    color: Commons.Color.popups.background
    border.width: 1
    border.color: card.accent
    z: 1000
    Drag.active: dragArea.drag.active
    Drag.keys: [card.dragKey]
    Drag.hotSpot.x: Style.space(12)
    Drag.hotSpot.y: height / 2
    Text {
      x: Style.space(12)
      anchors.verticalCenter: parent.verticalCenter
      width: parent.width - Style.space(24)
      text: (card.copying ? "Copy: " : "Move: ") + card.title
      textFormat: Text.PlainText
      elide: Text.ElideRight
      color: card.foreground
      font.family: card.fontFamily
      font.pixelSize: Style.font.body
    }
  }

  MenuList {
    id: menu
    y: card.height + Style.space(2)
    x: Math.max(0, card.width - width)
    fontFamily: card.fontFamily
    onPicked: function(v) {
      if (v === "") return
      var copy = v.indexOf("copy:") === 0
      card.moveRequested(v.slice(5), copy)
    }
    onClosed: card.forceActiveFocus()
  }
}
