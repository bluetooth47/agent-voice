import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "SettingsIndex.js" as SettingsIndex

// Settings search (master plan M28, feedback item 22: "where is the pause
// setting?"): a box at the top of the sidebar, and the results under it,
// drawn over the page because the sidebar is too narrow for a path.
//
// The index is ui/SettingsIndex.js. This piece only asks it and shows what
// comes back; a result is handed to the overlay with chosen(result), and
// the overlay's reveal() opens the page, unfolds what holds the control,
// scrolls to it and gives it the keyboard.
//
// Keyboard: Ctrl+F (the overlay's) puts the cursor here; typing searches;
// Up/Down move through the results; Enter opens the one marked; Escape
// clears the box, and on an empty box closes the overlay as before.
//
//   SettingsSearch {
//     width: sidebar.width
//     pages: root.pages
//     agents: [{ id: "main", label: "Theo" }, { id: "sora-x1", label: "Sora" }]
//     onChosen: function(r) { root.reveal(r) }
//   }
Item {
  id: search

  property var pages: []
  property var agents: []
  // Under the box: why the last result could not be shown as asked.
  property string note: ""
  // How wide the results may draw, over the page beside the sidebar.
  property real resultsWidth: Style.space(420)

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property color urgent: Commons.Color.urgent
  property color background: Commons.Color.menu.background
  readonly property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  property string query: ""
  property var results: []
  property int current: 0
  readonly property bool showing: query !== "" && box.fieldFocused

  signal chosen(var result)

  function focusField() { box.focusField() }
  function clear() { box.clear() }
  // Exposed for bench/preview targets, which type into the box.
  function type(text) { box.text = text; query = text; refresh() }
  function refresh() {
    results = SettingsIndex.search(query, pages, agents, 12)
    current = 0
  }
  function choose(i) {
    if (i < 0 || i >= results.length) return
    var r = results[i]
    box.clear()
    query = ""
    results = []
    chosen(r)
  }
  onAgentsChanged: if (query !== "") refresh()

  implicitHeight: column.implicitHeight
  height: implicitHeight
  z: 30

  Column {
    id: column
    width: parent.width
    spacing: Style.space(4)

    SearchField {
      id: box
      objectName: "settingsSearchField"
      width: parent.width
      placeholder: "Search settings"
      debounceMs: 120
      stepsList: true
      foreground: search.foreground
      accent: search.accent
      fontFamily: search.fontFamily
      Accessible.name: "Search settings"
      onSearched: function(t) { search.query = t; search.note = ""; search.refresh() }
      onSubmitted: function(t) {
        search.query = t
        search.refresh()
        search.choose(search.current)
      }
      onStepped: function(d) {
        if (search.results.length === 0) return
        search.current = Math.max(0, Math.min(search.results.length - 1, search.current + d))
      }
    }

    Text {
      width: parent.width
      visible: search.note !== ""
      wrapMode: Text.WordWrap
      text: search.note
      textFormat: Text.PlainText
      color: search.dim
      font.family: search.fontFamily
      font.pixelSize: Style.font.caption
    }
  }

  // The results, over whatever is beside the sidebar.
  Rectangle {
    id: drop
    objectName: "settingsSearchResults"
    visible: search.showing
    x: 0
    y: column.y + box.height + Style.space(4)
    width: search.resultsWidth
    height: list.implicitHeight + Style.space(12)
    radius: Style.cornerRadius
    color: search.background
    border.width: 1
    border.color: Qt.rgba(search.foreground.r, search.foreground.g, search.foreground.b, 0.25)

    // Clicks on the list's gaps stop here, not on the page underneath.
    MouseArea { anchors.fill: parent }

    Column {
      id: list
      x: Style.space(6)
      y: Style.space(6)
      width: parent.width - Style.space(12)
      spacing: Style.space(2)

      Text {
        width: parent.width
        visible: search.results.length === 0
        topPadding: Style.space(4)
        bottomPadding: Style.space(4)
        leftPadding: Style.space(6)
        wrapMode: Text.WordWrap
        text: "Nothing matches “" + search.query + "”."
        textFormat: Text.PlainText
        color: search.dim
        font.family: search.fontFamily
        font.pixelSize: Style.font.caption
      }

      Repeater {
        model: search.results
        Rectangle {
          id: row
          required property var modelData
          required property int index
          readonly property bool marked: index === search.current
          objectName: "searchResult-" + index
          width: list.width
          height: rowText.implicitHeight + Style.space(8)
          radius: Style.cornerRadius
          color: marked ? Style.selectedFillFor(search.foreground, search.accent)
                 : rowArea.containsMouse ? Qt.rgba(search.foreground.r, search.foreground.g, search.foreground.b, 0.06)
                 : "transparent"
          Accessible.role: Accessible.ListItem
          Accessible.name: modelData.label + ", " + modelData.path

          Column {
            id: rowText
            x: Style.space(8)
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - Style.space(16)
            spacing: Style.space(1)
            Text {
              width: parent.width
              elide: Text.ElideRight
              text: row.modelData.label
              textFormat: Text.PlainText
              color: search.foreground
              font.family: search.fontFamily
              font.pixelSize: Style.font.body
              font.bold: row.marked
            }
            Text {
              width: parent.width
              elide: Text.ElideRight
              text: row.modelData.path + (row.modelData.when !== "" ? " · shown when " + row.modelData.when : "")
              textFormat: Text.PlainText
              color: search.dim
              font.family: search.fontFamily
              font.pixelSize: Style.font.caption
            }
          }
          MouseArea {
            id: rowArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onEntered: search.current = row.index
            onClicked: search.choose(row.index)
          }
        }
      }
    }
  }
}
