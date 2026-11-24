import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// A titled box, the unit the redesigned pages are built from (feedback item
// 17). SettingsGroup puts its title above the box; a Card puts it inside,
// with an optional line under it and an optional caret that folds the body,
// so cards sit side by side in a CardGrid and read as one thing each.
//
//   Card {
//     title: "Voice"; subtitle: "What Theo sounds like"
//     SettingRow { width: parent.width; ... }
//   }
//
// Children size themselves to `parent.width`, as inside SettingsGroup.
Rectangle {
  id: card

  property string title: ""
  property string subtitle: ""
  property bool foldable: false
  property bool expanded: true
  property bool highlighted: false

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  readonly property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family
  readonly property int pad: Style.space(12)

  default property alias body: inner.data

  signal toggled(bool expanded)

  implicitHeight: column.implicitHeight + pad * 2
  height: implicitHeight
  radius: Style.cornerRadius
  color: "transparent"
  border.width: 1
  border.color: highlighted ? Qt.rgba(accent.r, accent.g, accent.b, 0.7)
                            : Qt.rgba(foreground.r, foreground.g, foreground.b, 0.18)

  Column {
    id: column
    x: card.pad
    y: card.pad
    width: parent.width - card.pad * 2
    spacing: Style.space(8)

    Item {
      id: head
      width: parent.width
      visible: card.title !== "" || card.subtitle !== ""
      height: titles.implicitHeight
      activeFocusOnTab: card.foldable
      Accessible.role: Accessible.Button
      Accessible.name: card.title + (card.expanded ? ", open" : ", folded")
      Accessible.description: card.subtitle
      Accessible.focusable: card.foldable
      Accessible.ignored: !card.foldable
      Accessible.onPressAction: card.flip()
      Keys.onReturnPressed: card.flip()
      Keys.onEnterPressed: card.flip()
      Keys.onSpacePressed: card.flip()

      Column {
        id: titles
        anchors.left: parent.left
        anchors.right: caret.visible ? caret.left : parent.right
        anchors.rightMargin: caret.visible ? Style.space(8) : 0
        spacing: Style.space(2)
        Text {
          width: parent.width
          visible: text !== ""
          text: card.title
          textFormat: Text.PlainText
          elide: Text.ElideRight
          color: card.foreground
          font.family: card.fontFamily
          font.pixelSize: Style.font.body
          font.bold: true
          font.underline: head.activeFocus
        }
        Hint {
          width: parent.width
          text: card.subtitle
          foreground: card.foreground
          fontFamily: card.fontFamily
        }
      }
      Text {
        id: caret
        visible: card.foldable
        anchors.right: parent.right
        anchors.verticalCenter: titles.verticalCenter
        text: card.expanded ? "▾" : "▸"
        color: card.dim
        font.family: card.fontFamily
        font.pixelSize: Style.font.body
      }
      MouseArea {
        anchors.fill: parent
        enabled: card.foldable
        cursorShape: Qt.PointingHandCursor
        onClicked: card.flip()
      }
    }

    Column {
      id: inner
      width: parent.width
      visible: !card.foldable || card.expanded
      spacing: Style.space(6)
    }
  }

  function flip() {
    if (!foldable) return
    expanded = !expanded
    toggled(expanded)
  }
  // As HeaderStrip: folding never leaves the focus on a hidden control.
  onExpandedChanged: {
    if (expanded) return
    for (var i = card.Window.activeFocusItem; i; i = i.parent)
      if (i === inner) { head.forceActiveFocus(); return }
  }
}
