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
  // Cut a longer text to maxLength when committing (the old instructions
  // box did). Off for a caller that refuses an over-long save itself and
  // keeps the text, as FileEditor does.
  property bool cutOff: true
  // The smallest the box is drawn: a one-line role needs less than a page
  // of instructions.
  property real minHeight: Style.space(84)
  // What the counter says while the box is being typed in.
  property string editingHint: "saved when you click away"
  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property string fontFamily: Style.font.family

  signal committed(string text)

  readonly property alias editing: area.activeFocus
  readonly property alias text: area.text
  // Typed in and not committed yet.
  readonly property bool dirty: area.activeFocus && area.text.trim() !== value.trim()

  // Characters as the daemon counts them: code points, so an emoji is one.
  function chars(t) { return Array.from(String(t)).length }
  // Show `v` even while the box has focus: a caller moving the box to other
  // content (another agent) must not leave the old text in it.
  function reset(v) { area.text = v }

  width: parent ? parent.width : 300
  // No room kept for the counter while it has nothing to say.
  implicitHeight: frame.height + (counter.text !== "" ? counter.height + Style.space(4) : 0)

  onValueChanged: if (!area.activeFocus) area.text = value
  Component.onCompleted: area.text = value

  // Compared before anything is cut, so focusing and leaving an unchanged
  // box never saves.
  function commit() {
    var t = area.text.trim()
    if (t === box.value.trim()) return
    if (box.cutOff && box.chars(t) > box.maxLength)
      t = Array.from(t).slice(0, box.maxLength).join("")
    box.committed(t)
  }

  readonly property var _spec: Border.controlSpec(area.activeFocus ? "focus"
                                                  : (hover.hovered ? "hover-cursor" : "normal"),
                                                  box.foreground, box.accent)

  BorderSurface {
    id: frame
    width: parent.width
    height: Math.max(box.minHeight, Math.min(Style.space(200), area.implicitHeight + Style.space(4)))
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
        // Ctrl+S saves without leaving the box (merged plan, Phase 12).
        Keys.onPressed: function(e) {
          if (e.key === Qt.Key_S && (e.modifiers & Qt.ControlModifier)) {
            box.commit()
            e.accepted = true
          } else if (e.key === Qt.Key_Tab || e.key === Qt.Key_Backtab) {
            // Tab moves on rather than typing a tab, so the page can be
            // walked by keyboard alone; nothing here needs a tab character.
            var to = area.nextItemInFocusChain(e.key === Qt.Key_Tab)
            if (to) to.forceActiveFocus(Qt.TabFocusReason)
            e.accepted = true
          }
        }
      }
    }
  }

  Text {
    id: counter
    anchors.top: frame.bottom
    anchors.topMargin: Style.space(4)
    anchors.right: parent.right
    text: box.chars(area.text) > box.maxLength
          ? (box.chars(area.text) + " / " + box.maxLength + (box.cutOff ? " — the rest is cut off" : " — too long to save"))
          : (area.activeFocus ? (box.chars(area.text) + " / " + box.maxLength + "  ·  " + box.editingHint)
                              : (area.text.trim() === "" ? "" : box.chars(area.text.trim()) + " characters"))
    color: box.chars(area.text) > box.maxLength ? Commons.Color.urgent : box.foreground
    opacity: box.chars(area.text) > box.maxLength ? 1 : 0.55
    font.family: box.fontFamily
    font.pixelSize: Style.font.bodySmall
    textFormat: Text.PlainText
  }
}
