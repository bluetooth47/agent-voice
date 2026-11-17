import QtQuick
import QtQuick.Controls
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// A few lines of free text: an agent's standing instructions.
//
// Saved when it loses focus, the way the folder field is, rather than on
// every keystroke: each save is a write to shell.json and a reload, and a
// reload per letter would also restart the agent's waiting process per
// letter. `committed(text)` carries the trimmed text, and only when it
// differs from what was there.
//
// The text it shows follows `value` only while it is not being edited, so a
// settings reload landing mid-sentence never throws away what is being typed.
Item {
  id: box

  property string value: ""
  property string placeholder: ""
  property int maxLength: 2000
  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property string fontFamily: Style.font.family

  signal committed(string text)

  readonly property alias editing: area.activeFocus
  readonly property alias text: area.text

  width: parent ? parent.width : 300
  implicitHeight: frame.height + counter.height + Style.space(4)

  onValueChanged: if (!area.activeFocus) area.text = value
  Component.onCompleted: area.text = value

  function commit() {
    var t = area.text.trim()
    if (t.length > box.maxLength) t = t.substring(0, box.maxLength)
    if (t !== box.value.trim()) box.committed(t)
  }

  readonly property var _spec: Border.controlSpec(area.activeFocus ? "focus"
                                                  : (hover.hovered ? "hover-cursor" : "normal"),
                                                  box.foreground, box.accent)

  BorderSurface {
    id: frame
    width: parent.width
    height: Math.max(Style.space(84), Math.min(Style.space(200), area.implicitHeight + Style.space(4)))
    color: Style.controlFill(area.activeFocus, hover.hovered, box.foreground, box.accent)
    borderSpec: box._spec
    radius: Style.cornerRadius

    HoverHandler { id: hover; cursorShape: Qt.IBeamCursor }

    Flickable {
      id: flick
      anchors.fill: parent
      anchors.margins: Style.space(2)
      clip: true
      contentWidth: width
      contentHeight: area.implicitHeight
      boundsBehavior: Flickable.StopAtBounds

      TextArea.flickable: TextArea {
        id: area
        wrapMode: TextEdit.Wrap
        textFormat: TextEdit.PlainText
        placeholderText: box.placeholder
        placeholderTextColor: Qt.darker(box.foreground, 1.6)
        color: box.foreground
        selectionColor: Style.selectionFillFor(box.foreground, box.accent)
        selectedTextColor: box.foreground
        font.family: box.fontFamily
        font.pixelSize: Style.font.body
        leftPadding: Style.spacing.controlPaddingX
        rightPadding: Style.spacing.controlPaddingX
        topPadding: Style.spacing.inputPaddingY
        bottomPadding: Style.spacing.inputPaddingY
        background: null
        onEditingFinished: box.commit()
        onActiveFocusChanged: if (!activeFocus) box.commit()
      }
    }
  }

  Text {
    id: counter
    anchors.top: frame.bottom
    anchors.topMargin: Style.space(4)
    anchors.right: parent.right
    text: area.text.length > box.maxLength
          ? (area.text.length + " / " + box.maxLength + " — the rest is cut off")
          : (area.activeFocus ? (area.text.length + " / " + box.maxLength + "  ·  saved when you click away")
                              : (area.text.trim() === "" ? "" : area.text.trim().length + " characters"))
    color: area.text.length > box.maxLength ? Commons.Color.urgent : box.foreground
    opacity: area.text.length > box.maxLength ? 1 : 0.55
    font.family: box.fontFamily
    font.pixelSize: Style.font.bodySmall
    textFormat: Text.PlainText
  }
}
