import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// The question before a tool found on this machine is switched on (master
// plan, M10): what will run, where it is defined, and who gets it. Inline,
// never a modal, and never on a timer -- unlike DangerButton's strip, this
// one asks to be read. Cancel has the focus, Escape cancels, and the switch
// is written only in `onConfirmed`: the pages call it from there and from
// nowhere else (tests/test_tool_controls.py).
//
//   ToolConfirm {
//     visible: page.confirming === modelData.id
//     title: "Turn on github for Theo?"
//     lines: [{ label: "Runs", value: "npx -y @modelcontextprotocol/server-github" },
//             { label: "Defined in", value: "~/.claude.json" },
//             { label: "Who gets it", value: "Theo only" }]
//     confirmText: "Turn on"
//     onConfirmed: s.setAgentTool(page.target, modelData.id, "on:" + modelData.fp)
//     onCancelled: page.confirming = ""
//   }
FocusScope {
  id: box

  property string title: ""
  // [{label, value}]: each shown as plain text -- a command line or a path
  // read from somebody's config file is never rendered as markup.
  property var lines: []
  property string warning: ""
  property string confirmText: "Turn on"
  property string cancelText: "Cancel"

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property color urgent: Commons.Color.urgent
  property string fontFamily: Style.font.family

  signal confirmed()
  signal cancelled()
  // When it appears, for a page that wants it scrolled into view (its
  // Turn on may be pressed somewhere else on the page, as in a notice).
  signal shown()

  width: parent ? parent.width : implicitWidth
  implicitHeight: frame.implicitHeight
  height: visible ? implicitHeight : 0
  onVisibleChanged: if (visible) { cancelButton.forceActiveFocus(); box.shown() }
  Keys.onEscapePressed: box.cancelled()

  Rectangle {
    id: frame
    width: parent.width
    implicitHeight: body.implicitHeight + Style.space(16)
    radius: Style.cornerRadius
    color: Qt.rgba(box.accent.r, box.accent.g, box.accent.b, 0.08)
    border.width: 1
    border.color: Qt.rgba(box.accent.r, box.accent.g, box.accent.b, 0.45)

    Column {
      id: body
      x: Style.space(8)
      y: Style.space(8)
      width: parent.width - Style.space(16)
      spacing: Style.space(6)

      Text {
        width: parent.width
        text: box.title
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: box.foreground
        font.family: box.fontFamily
        font.pixelSize: Style.font.body
        font.bold: true
      }
      Repeater {
        model: box.lines
        Column {
          required property var modelData
          width: body.width
          spacing: Style.space(1)
          Text {
            width: parent.width
            text: String(modelData.label || "")
            textFormat: Text.PlainText
            color: Qt.rgba(box.foreground.r, box.foreground.g, box.foreground.b, 0.6)
            font.family: box.fontFamily
            font.pixelSize: Style.font.caption
          }
          Text {
            width: parent.width
            text: String(modelData.value || "")
            textFormat: Text.PlainText
            // At a space where there is one, so a sentence keeps its words
            // (M20's "How much" split "charac-ters"); anywhere inside a
            // command line or a path too long for the line.
            wrapMode: Text.WrapAtWordBoundaryOrAnywhere
            maximumLineCount: 6
            elide: Text.ElideRight
            color: box.foreground
            font.family: box.fontFamily
            font.pixelSize: Style.font.caption
          }
        }
      }
      Text {
        width: parent.width
        visible: box.warning !== ""
        text: box.warning
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: box.urgent
        font.family: box.fontFamily
        font.pixelSize: Style.font.caption
      }
      Flow {
        width: parent.width
        spacing: Style.space(8)
        Button {
          id: cancelButton
          text: box.cancelText
          bordered: true
          focusable: true
          foreground: box.foreground
          fontFamily: box.fontFamily
          onClicked: box.cancelled()
        }
        Button {
          text: box.confirmText
          bordered: true
          focusable: true
          foreground: box.accent
          fontFamily: box.fontFamily
          onClicked: box.confirmed()
        }
      }
    }
  }
}
