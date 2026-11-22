import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// One skill as a card in a lane (master plan, M11): its name, a line of what
// it is for, where it comes from, and -- folded away until the caret is
// clicked -- the details: description, source path, size, problems, the
// names it shadows or is shadowed by, and who gets it.
//
// The switch, when `switchable`, only *asks*: toggled(on) goes to the page,
// which writes the setting through its overlay function. Buttons placed
// inside the card (Give a copy…) sit under the details, always visible.
// Every text is plain: a description is whatever a skill's author wrote.
//
//   SkillCard {
//     title: "weekly-report"; subtitle: "How to write the weekly report"
//     badge: "~/.claude/skills"; status: "Not given: switched off for Theo"
//     details: [{ label: "Source", value: "~/.claude/skills/weekly-report" }]
//     switchable: true; checked: false
//     onToggled: function(on) { page.s.setAgentSkill(page.target, "weekly-report", on) }
//   }
//
// Since M12 a card can be moved between DropLanes, as a DraggableCard can:
// with `draggable`, a drag on its header moves it and Ctrl held copies it,
// and "Move to…" (also Menu, or Ctrl+M, from the keyboard) lists `lanes`,
// the guaranteed path. `canMove` false (a skill found outside Agent Voice,
// which is only ever copied) offers copying alone. Like the switch, it only
// asks: moveRequested() here, received() on the lane, both to the page.
Rectangle {
  id: card

  property string title: ""
  property string subtitle: ""
  property string badge: ""
  property string badgeTone: "idle"
  // One line under the title when it is not given, or why it is off.
  property string status: ""
  property bool statusUrgent: false
  // [{label, value}], shown when unfolded.
  property var details: []
  property bool switchable: false
  property bool checked: false
  property string switchTooltip: ""
  property bool expanded: false
  property bool dimmed: false
  // Phase M12: moving it between lanes.
  property bool draggable: false
  property var payload: null
  property string laneId: ""
  // [{ id, label, reason, disabledReason }], every lane; its own is skipped.
  property var lanes: []
  property bool canMove: true
  property bool allowCopy: true
  property string dragKey: "agentvoice-card"
  property bool copying: false
  readonly property bool dragging: header.drag.active

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property color urgent: Commons.Color.urgent
  readonly property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  default property alias actions: actionRow.data

  signal toggled(bool on)
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
    if (canMove) { out.push({ section: "Move to" }); add(false) }
    if (allowCopy) { out.push({ section: canMove ? "Copy to" : "Give a copy to" }); add(true) }
    return out
  }
  function openMenu() { if (!draggable) return; menu.entries = menuEntries(); menu.open() }

  width: parent ? parent.width : implicitWidth
  implicitHeight: column.implicitHeight + Style.space(12)
  height: implicitHeight
  radius: Style.cornerRadius
  color: header.containsMouse || activeFocus ? Style.hoverFillFor(foreground, accent) : "transparent"
  border.width: 1
  border.color: activeFocus ? accent : Qt.rgba(foreground.r, foreground.g, foreground.b, 0.22)
  activeFocusOnTab: true
  opacity: dragging && !copying ? 0.4 : 1
  Keys.onMenuPressed: card.openMenu()
  Keys.onPressed: function(ev) {
    if (ev.key === Qt.Key_M && (ev.modifiers & Qt.ControlModifier)) { card.openMenu(); ev.accepted = true }
  }
  Keys.onReturnPressed: card.expanded = !card.expanded
  Keys.onEnterPressed: card.expanded = !card.expanded
  Keys.onSpacePressed: if (card.switchable) card.toggled(!card.checked)

  Column {
    id: column
    x: Style.space(8)
    y: Style.space(6)
    width: parent.width - Style.space(16)
    spacing: Style.space(3)

    Item {
      width: parent.width
      height: Math.max(titleColumn.implicitHeight, toggle.visible ? toggle.implicitHeight : 0)

      MouseArea {
        id: header
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: parent.width - (toggle.visible ? toggle.width + Style.space(6) : 0)
        hoverEnabled: true
        cursorShape: drag.active ? Qt.ClosedHandCursor : card.draggable ? Qt.OpenHandCursor
                                                                         : Qt.PointingHandCursor
        // A drag from the header moves the card (M12); a click unfolds it.
        drag.target: card.draggable ? ghost : null
        drag.threshold: Style.space(6)
        onPressed: function(mouse) {
          if (!card.draggable) return
          card.copying = card.allowCopy && (!card.canMove || (mouse.modifiers & Qt.ControlModifier) !== 0)
          // Hot spot where it was grabbed, and lifted out of the page so no
          // Flickable's clip cuts the ghost off (as DraggableCard does).
          var p0 = header.mapToItem(card, mouse.x, mouse.y)
          ghost.Drag.hotSpot.x = p0.x
          ghost.Drag.hotSpot.y = p0.y
          var top = card.Window.contentItem
          if (top) {
            var p = card.mapToItem(top, 0, 0)
            ghost.parent = top
            ghost.x = p.x
            ghost.y = p.y
          }
        }
        onPositionChanged: function(mouse) {
          if (card.draggable)
            card.copying = card.allowCopy && (!card.canMove || (mouse.modifiers & Qt.ControlModifier) !== 0)
        }
        onReleased: function(mouse) {
          if (!card.draggable) return
          card.copying = card.allowCopy && (!card.canMove || (mouse.modifiers & Qt.ControlModifier) !== 0)
          if (ghost.Drag.active) ghost.Drag.drop()
          ghost.parent = card
          ghost.x = 0
          ghost.y = 0
        }
        onCanceled: { ghost.parent = card; ghost.x = 0; ghost.y = 0 }
        onClicked: { card.forceActiveFocus(); card.expanded = !card.expanded }
      }
      Column {
        id: titleColumn
        width: header.width
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(1)
        Row {
          width: parent.width
          spacing: Style.space(6)
          Text {
            id: caret
            text: card.expanded ? "▾" : "▸"
            color: card.dim
            font.family: card.fontFamily
            font.pixelSize: Style.font.caption
            anchors.verticalCenter: parent.verticalCenter
          }
          Text {
            width: Math.min(implicitWidth, parent.width - caret.width - parent.spacing
                            - (badgePill.visible ? badgePill.width + parent.spacing : 0))
            text: card.title
            textFormat: Text.PlainText
            elide: Text.ElideRight
            color: card.dimmed ? card.dim : card.foreground
            font.family: card.fontFamily
            font.pixelSize: Style.font.body
            anchors.verticalCenter: parent.verticalCenter
          }
          Pill {
            id: badgePill
            text: card.badge
            tone: card.badgeTone
            foreground: card.foreground
            accent: card.accent
            urgent: card.urgent
            fontFamily: card.fontFamily
            anchors.verticalCenter: parent.verticalCenter
          }
        }
        Text {
          width: parent.width
          visible: text !== ""
          text: card.subtitle
          textFormat: Text.PlainText
          elide: Text.ElideRight
          maximumLineCount: 1
          color: card.dim
          font.family: card.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
      ToggleSwitch {
        id: toggle
        visible: card.switchable
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        checked: card.checked
        foreground: card.foreground
        accent: card.accent
        onToggled: card.toggled(!card.checked)
      }
    }
    Text {
      width: parent.width
      visible: text !== ""
      text: card.status
      textFormat: Text.PlainText
      wrapMode: Text.WordWrap
      color: card.statusUrgent ? card.urgent : card.dim
      font.family: card.fontFamily
      font.pixelSize: Style.font.caption
    }
    Column {
      width: parent.width
      visible: card.expanded
      spacing: Style.space(2)
      Repeater {
        model: card.details
        Text {
          required property var modelData
          width: column.width
          wrapMode: Text.WrapAnywhere
          textFormat: Text.PlainText
          text: String(modelData.label) + ": " + String(modelData.value)
          color: modelData.urgent === true ? card.urgent : card.dim
          font.family: card.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
    }
    Flow {
      id: actionRow
      width: parent.width
      visible: children.length > 0
      spacing: Style.space(6)
      Button {
        id: moveButton
        visible: card.draggable
        text: card.canMove ? "Move to…" : "Copy to…"
        bordered: true
        focusable: true
        fontSize: Style.font.caption
        foreground: card.foreground
        fontFamily: card.fontFamily
        tooltipText: card.canMove ? "Move or copy it to another agent or Communal (or drag it; Ctrl copies)"
                                  : "Give a copy to an agent or Communal (or drag it)"
        onClicked: card.openMenu()
      }
    }
  }

  // What follows the pointer. A DropLane reads payload, laneId and copying
  // off it (drag.source).
  Rectangle {
    id: ghost
    readonly property var payload: card.payload
    readonly property string laneId: card.laneId
    readonly property bool copying: card.copying
    width: card.width
    height: Math.min(card.height, Style.space(40))
    visible: header.drag.active
    radius: card.radius
    color: Commons.Color.popups.background
    border.width: 1
    border.color: card.accent
    z: 1000
    Drag.active: header.drag.active
    Drag.keys: [card.dragKey]
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
      // Against the lanes as they are now, not as the menu opened.
      var now = card.menuEntries()
      for (var i = 0; i < now.length; i++) {
        if (now[i].value === v && now[i].enabled !== false) {
          card.moveRequested(v.slice(5), v.indexOf("copy:") === 0)
          return
        }
      }
    }
    onClosed: if (menu.heldFocus()) card.forceActiveFocus()
  }
}
