import QtQuick
import qs.Commons
import qs.Commons as Commons

// One turn of a conversation as a bubble (feedback item 6): what you said
// on the right, what the agent said on the left, so a long chat reads as a
// conversation rather than a log.
//
// The text is whatever was said or answered, so it is untrusted: plain text
// always (CLAUDE.md: a transcript and a model reply are untrusted input to
// the UI), selectable so it can be copied, never rendered as markup.
//
//   ChatBubble { width: parent.width; mine: true; who: "You"; when: "14:02"; text: "…" }
//   ChatBubble { width: parent.width; who: "Sora"; stripe: "#c678dd"; text: "…" }
//
// `stripe` (phase M18): the speaking agent's own colour, drawn down the
// bubble's left edge, so in a chat several agents spoke in each reply says
// whose it is at a glance -- the name above it says it in words.
Item {
  id: bubble

  property string text: ""
  property string who: ""
  property string when: ""
  property bool mine: false
  // "", or "note" for a quieter line (a tool marker, a handover).
  property string kind: ""
  property real maxRatio: 0.8
  property color stripe: "transparent"

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  readonly property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  readonly property real maxWidth: width * maxRatio
  readonly property int pad: Style.space(10)
  readonly property int stripeWidth: stripe.a > 0 ? Style.space(3) : 0

  implicitHeight: column.implicitHeight
  height: implicitHeight

  // The text's natural width, its widest line, from the font's metrics:
  // worked out once per text, by no item in the layout. (A hidden Text
  // measuring it froze the overlay on a long session: the ListView laying
  // out 200 of them never settled.)
  FontMetrics {
    id: metrics
    font.family: bubble.fontFamily
    font.pixelSize: bubble.kind === "note" ? Style.font.caption : Style.font.body
  }
  readonly property real naturalWidth: {
    var widest = 0
    var lines = String(bubble.text).split("\n")
    for (var i = 0; i < lines.length; i++) {
      widest = Math.max(widest, metrics.advanceWidth(lines[i]))
      if (widest >= bubble.maxWidth) break
    }
    return Math.ceil(widest)
  }

  Column {
    id: column
    width: parent.width
    spacing: Style.space(2)

    Text {
      visible: bubble.who !== "" || bubble.when !== ""
      anchors.right: bubble.mine ? parent.right : undefined
      anchors.left: bubble.mine ? undefined : parent.left
      anchors.rightMargin: bubble.mine ? Style.space(4) : 0
      anchors.leftMargin: bubble.mine ? 0 : Style.space(4)
      width: Math.min(implicitWidth, parent.width)
      elide: Text.ElideRight
      text: bubble.who + (bubble.who !== "" && bubble.when !== "" ? " · " : "") + bubble.when
      textFormat: Text.PlainText
      color: bubble.dim
      font.family: bubble.fontFamily
      font.pixelSize: Style.font.caption
    }

    Rectangle {
      id: box
      anchors.right: bubble.mine ? parent.right : undefined
      anchors.left: bubble.mine ? undefined : parent.left
      width: Math.min(bubble.maxWidth, bubble.naturalWidth + 2 + bubble.pad * 2 + bubble.stripeWidth)
      height: body.implicitHeight + bubble.pad * 1.4
      radius: Style.cornerRadius * 2
      clip: bubble.stripeWidth > 0
      color: bubble.kind === "note" ? "transparent"
             : bubble.mine ? Qt.rgba(bubble.accent.r, bubble.accent.g, bubble.accent.b, 0.16)
             : Qt.rgba(bubble.foreground.r, bubble.foreground.g, bubble.foreground.b, 0.07)
      border.width: bubble.kind === "note" ? 1 : 0
      border.color: Qt.rgba(bubble.foreground.r, bubble.foreground.g, bubble.foreground.b, 0.18)

      Rectangle {
        visible: bubble.stripeWidth > 0
        width: bubble.stripeWidth
        height: parent.height
        color: bubble.stripe
      }

      TextEdit {
        id: body
        x: bubble.pad + bubble.stripeWidth
        anchors.verticalCenter: parent.verticalCenter
        width: box.width - bubble.pad * 2 - bubble.stripeWidth
        readOnly: true
        selectByMouse: true
        textFormat: TextEdit.PlainText
        wrapMode: TextEdit.Wrap
        text: bubble.text
        color: bubble.kind === "note" ? bubble.dim : bubble.foreground
        selectionColor: Qt.rgba(bubble.accent.r, bubble.accent.g, bubble.accent.b, 0.35)
        font.family: bubble.fontFamily
        font.pixelSize: bubble.kind === "note" ? Style.font.caption : Style.font.body
      }
    }
  }
}
