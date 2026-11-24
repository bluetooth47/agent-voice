import QtQuick
import qs.Commons
import qs.Commons as Commons

// One setting on one line: what it is on the left, the control on the right,
// one short line saying what it does underneath, and the long explanation
// folded away behind "?".
//
// The settings page had a paragraph under nearly every control, which made
// it a wall of text where the controls were the hard part to find. The
// paragraphs were right -- most exist because somebody hit the thing they
// explain -- so they are kept, one click away, instead of deleted.
//
// A setting that does not apply right now is shown dimmed with the reason
// (`disabledReason`) rather than hidden: hiding made the page jump about as
// other settings changed, and left nothing to say why a control had gone.
//
// `changed` puts a "reset" link beside the label; clicking it emits reset().
//
//   SettingRow {
//     width: parent.width
//     label: "Speak replies aloud"
//     hint: "Off leaves the reply as text in the panel."
//     ToggleSwitch { checked: ...; onToggled: ... }
//   }
//
// A control too wide to share the line (a slider, a text field, a group of
// chips) goes underneath instead: set `stacked: true`.
Item {
  id: row

  property string label: ""
  property string hint: ""
  property string help: ""
  property string disabledReason: ""
  property bool changed: false
  property bool stacked: false

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  // Translucent rather than Qt.darker: darker is dimmer only on a dark
  // theme, and on a light one made every hint as black as the label.
  property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  default property alias control: slot.data
  readonly property bool applies: disabledReason === ""
  property bool helpOpen: false

  signal reset()

  implicitHeight: body.implicitHeight
  height: implicitHeight

  Column {
    id: body
    width: parent.width
    spacing: Style.space(3)

    Item {
      width: parent.width
      height: Math.max(head.implicitHeight, row.stacked ? 0 : slot.childrenRect.height)

      Column {
        id: head
        anchors.left: parent.left
        anchors.right: row.stacked ? parent.right : slot.left
        anchors.rightMargin: row.stacked ? 0 : Style.space(12)
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(2)
        opacity: row.applies ? 1 : 0.5

        Row {
          width: parent.width
          spacing: Style.space(8)

          Text {
            id: title
            width: Math.min(implicitWidth, parent.width - extras.width - parent.spacing)
            text: row.label
            // A label or hint may hold a name someone typed (Phase 12
            // review: a display name in markup rendered as markup).
            textFormat: Text.PlainText
            color: row.foreground
            font.family: row.fontFamily
            font.pixelSize: Style.font.body
            // Two lines before it is cut (M29): in the narrow layout a
            // label beside its switch read "Show what it heard and what it …".
            wrapMode: Text.Wrap
            maximumLineCount: 2
            elide: Text.ElideRight
          }

          Row {
            id: extras
            spacing: Style.space(8)
            anchors.verticalCenter: title.verticalCenter

            // Reached by Tab too since M29 (ui/TextLink): they were
            // pointer-only, so a setting could not be reset or explained
            // from the keyboard.
            TextLink {
              visible: row.help !== ""
              text: row.helpOpen ? "×" : "?"
              lit: row.helpOpen
              foreground: row.foreground
              accent: row.accent
              dim: row.dim
              font.family: row.fontFamily
              accessibleName: (row.helpOpen ? "Hide what " : "Explain ") + row.label
              onActivated: row.helpOpen = !row.helpOpen
            }

            TextLink {
              visible: row.changed && row.applies
              text: "reset"
              foreground: row.foreground
              accent: row.accent
              dim: row.dim
              font.family: row.fontFamily
              accessibleName: "Reset " + row.label
              onActivated: row.reset()
            }
          }
        }

        Text {
          width: parent.width
          visible: text !== ""
          text: row.applies ? row.hint : row.disabledReason
          textFormat: Text.PlainText
          wrapMode: Text.WordWrap
          color: row.dim
          font.family: row.fontFamily
          font.pixelSize: Style.font.caption
        }
      }

      // The control, on the right when it fits on the line.
      Item {
        id: slot
        visible: !row.stacked
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: childrenRect.width
        height: childrenRect.height
        enabled: row.applies
        opacity: row.applies ? 1 : 0.4
      }
    }

    // The control, underneath, when it does not.
    Item {
      id: stackedSlot
      width: parent.width
      visible: row.stacked
      height: visible ? childrenRect.height : 0
      enabled: row.applies
      opacity: row.applies ? 1 : 0.4
    }

    Text {
      width: parent.width
      visible: row.helpOpen && row.help !== ""
      text: row.help
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      color: row.dim
      font.family: row.fontFamily
      font.pixelSize: Style.font.caption
      leftPadding: Style.space(8)
      Rectangle {
        width: Math.max(1, Style.space(2))
        height: parent.height
        color: Qt.rgba(row.foreground.r, row.foreground.g, row.foreground.b, 0.25)
      }
    }
  }

  // The children are declared once, into `slot`; when stacked they move
  // underneath. Reparenting rather than two slots, so a caller never has to
  // know which one its control will end up in.
  function place() {
    var from = stacked ? slot : stackedSlot
    var to = stacked ? stackedSlot : slot
    var kids = []
    for (var i = 0; i < from.children.length; i++) kids.push(from.children[i])
    for (var j = 0; j < kids.length; j++) {
      kids[j].parent = to
      if (stacked && kids[j].width !== undefined) kids[j].width = Qt.binding(function() { return stackedSlot.width })
    }
  }
  onStackedChanged: place()
  Component.onCompleted: {
    if (stacked) place()
    lendName()
  }

  // A control with no name of its own (a row of chips, a selector with no
  // label, Omarchy's Dropdown) is called what the row is called, so a
  // screen reader says "Size, chosen: Locked" rather than nothing (master
  // plan M29). Only a control that takes Tab focus, a few levels down, and
  // only while it has no name: a button's own text is never replaced.
  function lendName() {
    walkName(slot, 0)
    walkName(stackedSlot, 0)
  }
  function walkName(item, depth) {
    var kids = item.children || []
    for (var i = 0; i < kids.length; i++) {
      var c = kids[i]
      if (c.accessibleName !== undefined) {
        // One of ours: it says how to name itself.
        if (c.accessibleName === "" && !(c.text !== undefined && String(c.text) !== "")
            && !(c.label !== undefined && String(c.label) !== ""))
          c.accessibleName = Qt.binding(function() { return row.label })
        continue
      }
      if (c.activeFocusOnTab === true) {
        var named = ""
        try { named = String(c.Accessible.name || "") } catch (e) { named = "" }
        if (named === "" && !(c.text !== undefined && String(c.text) !== ""))
          c.Accessible.name = Qt.binding(function() { return row.label })
        continue
      }
      if (depth < 3) walkName(c, depth + 1)
    }
  }
}
