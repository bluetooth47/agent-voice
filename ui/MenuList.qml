import QtQuick
import QtQuick.Controls as QQC
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// A short pick-one list that opens under whatever owns it: the compact
// selector's choices and a card's "Move to…" menu. Not a page control on
// its own, so it knows no setting.
//
// `entries` are strings or objects:
//   { value, label, detail, enabled }   a choice; `detail` is a dim second
//                                       line, and on a disabled entry it is
//                                       the reason it cannot be picked
//   { section: "Copy to" }              a heading, never picked
//
// Keyboard, the way Omarchy's Dropdown does it: Up/Down or j/k walk the
// choices (skipping headings and disabled ones), Enter picks, Escape closes.
QQC.Popup {
  id: menu

  property var entries: []
  property string current: ""
  property real minWidth: Style.space(160)

  property color foreground: Commons.Color.popups.text
  property color fillColor: Commons.Color.popups.background
  property color accent: Commons.Color.accent
  // Not `dim` or `background`: Popup already has both, as final members.
  readonly property color faded: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  property int cursor: -1

  signal picked(string value)

  function isSection(e) { return e !== null && typeof e === "object" && e.section !== undefined }
  function valueOf(e) { return (e !== null && typeof e === "object") ? String(e.value) : String(e) }
  function labelOf(e) {
    if (isSection(e)) return String(e.section)
    if (e !== null && typeof e === "object") return String(e.label !== undefined ? e.label : e.value)
    return String(e)
  }
  function detailOf(e) { return (e !== null && typeof e === "object" && e.detail) ? String(e.detail) : "" }
  function usable(e) { return !isSection(e) && !(e !== null && typeof e === "object" && e.enabled === false) }

  function move(d) {
    var n = entries.length
    for (var step = 1; step <= n; step++) {
      var i = cursor + d * step
      if (i < 0 || i >= n) return
      if (usable(entries[i])) { cursor = i; list.positionViewAtIndex(i, ListView.Contain); return }
    }
  }
  // Whether the window's focus is inside this menu, or nowhere: the cases
  // where closing should hand focus back to the opener.
  function heldFocus() {
    var item = list.Window.activeFocusItem
    if (!item) return true
    for (var i = item; i; i = i.parent) if (i === list) return true
    return false
  }
  function choose(i) {
    if (i < 0 || i >= entries.length || !usable(entries[i])) return
    var v = valueOf(entries[i])
    close()
    picked(v)
  }

  TextMetrics { id: measure; font.family: menu.fontFamily; font.pixelSize: Style.font.body }

  onAboutToShow: {
    var w = 0
    cursor = -1
    for (var i = 0; i < entries.length; i++) {
      measure.text = labelOf(entries[i])
      w = Math.max(w, measure.advanceWidth)
      if (cursor < 0 && usable(entries[i]) && valueOf(entries[i]) === current) cursor = i
    }
    if (cursor < 0) for (var j = 0; j < entries.length; j++) if (usable(entries[j])) { cursor = j; break }
    width = Math.max(minWidth, w + Style.space(40))
  }
  onOpened: list.forceActiveFocus()

  modal: false
  focus: true
  closePolicy: QQC.Popup.CloseOnEscape | QQC.Popup.CloseOnPressOutside
  padding: Style.space(4)

  background: BorderSurface {
    color: menu.fillColor
    borderSpec: Border.localOrSurfaceSpec("popups", "border", Commons.Color.popups.border,
                                         Commons.Color.popups.border, Style.normalBorderWidth)
    radius: Style.cornerRadius
  }

  contentItem: ListView {
    id: list
    implicitHeight: Math.min(contentHeight, Style.space(320))
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    model: menu.entries
    currentIndex: menu.cursor
    keyNavigationEnabled: false

    Keys.onUpPressed: menu.move(-1)
    Keys.onDownPressed: menu.move(1)
    Keys.onReturnPressed: menu.choose(menu.cursor)
    Keys.onEnterPressed: menu.choose(menu.cursor)
    Keys.onSpacePressed: menu.choose(menu.cursor)
    Keys.onPressed: function(e) {
      if (e.key === Qt.Key_J) { menu.move(1); e.accepted = true }
      else if (e.key === Qt.Key_K) { menu.move(-1); e.accepted = true }
    }

    delegate: Rectangle {
      id: entry
      required property var modelData
      required property int index
      readonly property bool heading: menu.isSection(modelData)
      readonly property bool ok: menu.usable(modelData)
      width: ListView.view.width
      height: col.implicitHeight + Style.space(heading ? 6 : 10)
      radius: Style.cornerRadius
      color: !ok ? "transparent"
             : index === menu.cursor ? Style.hoverFillFor(menu.foreground, menu.accent)
             : "transparent"

      Column {
        id: col
        anchors.verticalCenter: parent.verticalCenter
        x: Style.space(8)
        width: parent.width - Style.space(16)
        spacing: Style.space(1)
        Text {
          width: parent.width
          text: menu.labelOf(entry.modelData)
          textFormat: Text.PlainText
          elide: Text.ElideRight
          color: entry.heading || !entry.ok ? menu.faded : menu.foreground
          font.family: menu.fontFamily
          font.pixelSize: entry.heading ? Style.font.caption : Style.font.body
          font.bold: !entry.heading && menu.valueOf(entry.modelData) === menu.current
        }
        Text {
          width: parent.width
          visible: text !== ""
          text: menu.detailOf(entry.modelData)
          textFormat: Text.PlainText
          wrapMode: Text.WordWrap
          color: menu.faded
          font.family: menu.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
      MouseArea {
        anchors.fill: parent
        enabled: entry.ok
        hoverEnabled: true
        cursorShape: entry.ok ? Qt.PointingHandCursor : Qt.ArrowCursor
        onEntered: menu.cursor = entry.index
        onClicked: menu.choose(entry.index)
      }
    }
  }
}
