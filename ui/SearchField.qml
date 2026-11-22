import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// A search box with filter chips under it: the Chats page's search
// (feedback item 6), and later Settings search.
//
// `searched(text)` fires a moment after typing stops (`debounceMs`) and at
// once on Enter, so a page does not search on every keystroke. Escape
// clears a box that has text in it; an empty box lets Escape through, so it
// still closes the overlay.
//
// `filters`: [{ id, label, tooltip }]; `active`: the ids switched on. A chip
// emits filterToggled(id, on) and the page decides what `active` becomes.
//
//   SearchField {
//     width: parent.width; placeholder: "Search chats"
//     filters: [{ id: "mine", label: "Theo" }, { id: "week", label: "This week" }]
//     active: page.filters
//     onSearched: function(t) { page.query = t }
//     onFilterToggled: function(id, on) { page.setFilter(id, on) }
//   }
Column {
  id: search

  property alias text: field.text
  property string placeholder: "Search"
  property var filters: []
  property var active: []
  property int debounceMs: 250

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  readonly property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  signal searched(string text)
  signal filterToggled(string id, bool on)

  function isActive(id) { return active && active.indexOf(id) >= 0 }
  function clear() { search.text = ""; debounce.stop(); searched("") }
  function focusField() { field.forceActiveFocus() }

  spacing: Style.space(6)

  Timer { id: debounce; interval: search.debounceMs; onTriggered: search.searched(field.text) }

  Item {
    width: parent.width
    height: field.implicitHeight

    TextField {
      id: field
      anchors.fill: parent
      placeholderText: search.placeholder
      foreground: search.foreground
      accent: search.accent
      font.family: search.fontFamily
      leftPadding: horizontalPadding + Style.space(18)
      rightPadding: horizontalPadding + (text !== "" ? Style.space(22) : 0)
      onTextEdited: debounce.restart()
      onAccepted: { debounce.stop(); search.searched(text) }
      Keys.onEscapePressed: function(e) {
        if (text === "") { e.accepted = false; return }
        search.clear()
        e.accepted = true
      }
    }
    Text {
      anchors.left: parent.left
      anchors.leftMargin: Style.space(8)
      anchors.verticalCenter: parent.verticalCenter
      text: "\u{f0349}"
      color: search.dim
      font.family: search.fontFamily
      font.pixelSize: Style.font.body
    }
    Text {
      visible: field.text !== ""
      anchors.right: parent.right
      anchors.rightMargin: Style.space(8)
      anchors.verticalCenter: parent.verticalCenter
      text: "×"
      color: clearArea.containsMouse ? search.foreground : search.dim
      font.family: search.fontFamily
      font.pixelSize: Style.font.body
      MouseArea {
        id: clearArea
        anchors.fill: parent
        anchors.margins: -Style.space(5)
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: { search.clear(); field.forceActiveFocus() }
      }
    }
  }

  Flow {
    width: parent.width
    visible: search.filters.length > 0
    spacing: Style.space(6)
    Repeater {
      model: search.filters
      Button {
        required property var modelData
        readonly property bool on: search.isActive(String(modelData.id))
        text: String(modelData.label || modelData.id)
        tooltipText: String(modelData.tooltip || "")
        selected: on
        bordered: true
        focusable: true
        fontSize: Style.font.caption
        foreground: search.foreground
        accent: search.accent
        fontFamily: search.fontFamily
        onClicked: search.filterToggled(String(modelData.id), !on)
      }
    }
  }
}
