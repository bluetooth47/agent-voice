import QtQuick
import qs.Commons
import qs.Commons as Commons

// The page list down the side of the settings overlay.
//
// `pages` is [{ id, label, icon, badge? }]; `current` is an id. A badge is a
// short string drawn after the label in the urgent colour, for a page with
// something wrong on it ("!" on Agents when one has no folder for "edits").
//
// Keyboard: Up/Down (or k/j) move and pick, so the page follows the cursor
// the way a list of tabs does; Tab leaves.
FocusScope {
  id: nav

  property var pages: []
  property string current: ""

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property color urgent: Commons.Color.urgent
  // Translucent rather than Qt.darker: darker is dimmer only on a dark
  // theme, and on a light one made every hint as black as the label.
  property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  signal picked(string id)

  implicitWidth: Style.space(150)
  implicitHeight: list.implicitHeight
  activeFocusOnTab: true

  function indexOf(id) {
    for (var i = 0; i < pages.length; i++) if (pages[i].id === id) return i
    return -1
  }
  function step(d) {
    if (pages.length === 0) return
    var i = indexOf(current)
    i = Math.max(0, Math.min(pages.length - 1, (i < 0 ? 0 : i) + d))
    picked(pages[i].id)
  }

  Keys.onUpPressed: step(-1)
  Keys.onDownPressed: step(1)
  Keys.onPressed: function(e) {
    if (e.key === Qt.Key_K) { step(-1); e.accepted = true }
    else if (e.key === Qt.Key_J) { step(1); e.accepted = true }
  }

  Column {
    id: list
    width: parent.width
    spacing: Style.space(2)

    Repeater {
      model: nav.pages

      Rectangle {
        id: entry
        required property var modelData
        readonly property bool selected: modelData.id === nav.current
        width: list.width
        height: Math.round(Style.spacing.controlHeight * 0.85)
        radius: Style.cornerRadius
        color: selected ? Style.selectedFillFor(nav.foreground, nav.accent)
               : hover.containsMouse ? Qt.rgba(nav.foreground.r, nav.foreground.g, nav.foreground.b, 0.06)
               : "transparent"
        border.width: selected && nav.activeFocus ? 1 : 0
        border.color: nav.accent

        Row {
          anchors.left: parent.left
          anchors.leftMargin: Style.space(10)
          anchors.right: parent.right
          anchors.rightMargin: Style.space(8)
          anchors.verticalCenter: parent.verticalCenter
          spacing: Style.space(10)

          Text {
            width: Style.space(16)
            horizontalAlignment: Text.AlignHCenter
            text: entry.modelData.icon || ""
            color: entry.selected ? nav.foreground : nav.dim
            font.family: nav.fontFamily
            font.pixelSize: Style.font.body
          }
          Text {
            text: entry.modelData.label
            color: entry.selected ? nav.foreground : nav.dim
            font.family: nav.fontFamily
            font.pixelSize: Style.font.body
            font.bold: entry.selected
          }
          Text {
            visible: !!entry.modelData.badge
            text: entry.modelData.badge || ""
            color: nav.urgent
            font.family: nav.fontFamily
            font.pixelSize: Style.font.caption
            font.bold: true
          }
        }

        MouseArea {
          id: hover
          anchors.fill: parent
          hoverEnabled: true
          cursorShape: Qt.PointingHandCursor
          onClicked: { nav.forceActiveFocus(); nav.picked(entry.modelData.id) }
        }
      }
    }
  }
}
