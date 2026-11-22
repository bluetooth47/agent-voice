import QtQuick
import qs.Commons
import qs.Commons as Commons

// Fine-tuning, folded away: "Advanced (4) ▸". Shut by default, every time
// the page is built, because a control under it is one most people should
// never need, and the house rule is that fine-tuning goes under a collapsed
// Advanced rather than beside the settings people came for.
//
// `count` is how many settings are inside, shown in the header so a folded
// section still says there is something in it. It defaults to the number
// of children; a caller whose children are wrappers sets it.
//
//   AdvancedSection { width: parent.width; SettingRow { ... } KnobRow { ... } }
//
// Keyboard: one Tab stop on the header; Enter or Space opens it.
Column {
  id: section

  property string title: "Advanced"
  property bool expanded: false
  property int count: inner.children.length
  property string summary: ""

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  readonly property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  default property alias body: inner.data

  signal toggled(bool expanded)

  function flip() { expanded = !expanded; toggled(expanded) }
  // As HeaderStrip: folding never leaves the focus on a hidden control.
  onExpandedChanged: {
    if (expanded) return
    for (var i = section.Window.activeFocusItem; i; i = i.parent)
      if (i === inner) { head.forceActiveFocus(); return }
  }

  spacing: Style.space(8)

  Rectangle {
    id: head
    width: parent.width
    height: headRow.implicitHeight + Style.space(8)
    radius: Style.cornerRadius
    activeFocusOnTab: true
    color: headArea.containsMouse || activeFocus ? Style.hoverFillFor(section.foreground, section.accent) : "transparent"
    border.width: activeFocus ? 1 : 0
    border.color: section.accent
    Keys.onReturnPressed: section.flip()
    Keys.onEnterPressed: section.flip()
    Keys.onSpacePressed: section.flip()

    Row {
      id: headRow
      x: Style.space(4)
      anchors.verticalCenter: parent.verticalCenter
      width: parent.width - Style.space(8)
      spacing: Style.space(6)
      Text {
        text: section.expanded ? "▾" : "▸"
        color: section.dim
        font.family: section.fontFamily
        font.pixelSize: Style.font.body
      }
      Text {
        text: section.title + (section.count > 0 ? " (" + section.count + ")" : "")
        textFormat: Text.PlainText
        color: section.foreground
        font.family: section.fontFamily
        font.pixelSize: Style.font.body
      }
      Text {
        width: parent.width - x
        visible: section.summary !== "" && !section.expanded
        text: section.summary
        textFormat: Text.PlainText
        elide: Text.ElideRight
        color: section.dim
        font.family: section.fontFamily
        font.pixelSize: Style.font.caption
        anchors.verticalCenter: parent.verticalCenter
      }
    }
    MouseArea {
      id: headArea
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onClicked: { head.forceActiveFocus(); section.flip() }
    }
  }

  Column {
    id: inner
    width: parent.width
    visible: section.expanded
    spacing: Style.space(8)
    leftPadding: 0
  }
}
