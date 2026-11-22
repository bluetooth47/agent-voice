import QtQuick
import qs.Commons
import qs.Commons as Commons

// The locked readout (phase M3, bug B): two lines that are always there.
//
// The agent's last answer on top, dim, behind an accent bar; what is being
// said now below it, bright. Each slot is a fixed number of text lines tall
// whether it holds a sentence, a paragraph or nothing at all, so nothing
// appears, disappears or changes height from one turn to the next -- which
// is what made the popup bounce: its last-heard section came and went with
// every wake word.
//
// Long text shows its *end*, the way the dynamic readout scrolls to follow
// the newest sentence: the words being spoken or heard right now are the
// ones worth reading at a glance. Cut at a sentence boundary when one falls
// in range, with an ellipsis in front, and elided on the right as a last
// resort. Both texts are a transcript of speech and a model's reply, so
// both are PlainText.
//
// A building block with no setting in it: the HUD and the popup pass the
// words, the size and the colours in. Whose answer it is, they say in their
// own header.
//
//   ReadoutLines { width: parent.width; reply: r; transcript: t }
Column {
  id: root

  property string reply: ""
  property string transcript: ""
  // Shown dim in an empty slot, so an empty readout still says what goes
  // where. Empty strings leave the slot blank (still the same height).
  property string replyPlaceholder: ""
  property string transcriptPlaceholder: ""
  property int linesEach: 2
  property real pixelSize: Style.font.body
  property string fontFamily: Style.font.family
  property color foreground: Commons.Color.foreground
  property color replyAccent: Commons.Color.accent
  property color nowAccent: Commons.Color.foreground

  spacing: Style.space(6)

  readonly property int barWidth: Style.space(3)
  readonly property int barGap: Style.space(8)

  FontMetrics {
    id: fm
    font.family: root.fontFamily
    font.pixelSize: root.pixelSize
  }
  // Fixed from the font, never from the text: this is the whole point.
  readonly property int slotHeight: Math.ceil(Math.max(fm.lineSpacing, fm.height) * root.linesEach) + 1
  // Roughly what fits in a slot, with a margin for glyphs wider than the
  // average and for word wrap; the elide below catches what this misses,
  // at the cost of the very last words (Codex review: noted, not solved).
  readonly property int tailChars: Math.max(24, Math.floor(
      Math.floor(Math.max(0, root.width - root.barWidth - root.barGap)
                 / Math.max(1, fm.averageCharacterWidth)) * root.linesEach * 0.85))

  // The end of `s` that fits, from a sentence (or failing that a word)
  // boundary, with an ellipsis where it was cut.
  function tail(s) {
    var text = String(s || "").replace(/\s+/g, " ").trim()
    if (text.length <= root.tailChars) return text
    var from = text.length - root.tailChars
    var rest = text.slice(from)
    var sentence = rest.search(/[.!?…]\s+\S/)
    // A sentence start only when it keeps at least half the room: cutting
    // to the last short sentence left a slot half empty.
    if (sentence >= 0 && rest.length - sentence >= root.tailChars / 2)
      return "…" + rest.slice(sentence + 1).replace(/^\s+/, "")
    var space = rest.indexOf(" ")
    return "…" + (space >= 0 && space < 20 ? rest.slice(space + 1) : rest)
  }

  component Slot: Item {
    id: slot
    property string text: ""
    property string placeholder: ""
    property color accent: root.foreground
    property real strength: 1.0

    width: root.width
    height: root.slotHeight

    Rectangle {
      width: root.barWidth
      height: parent.height
      radius: width / 2
      color: slot.accent
      opacity: slot.text !== "" ? 1.0 : 0.35
    }
    Text {
      x: root.barWidth + root.barGap
      width: parent.width - x
      // No height: an explicit one makes Qt elide by height, and a line
      // that is a pixel taller than lineSpacing then cuts the slot to one
      // line. maximumLineCount bounds it; the slot's own height is fixed.
      wrapMode: Text.WordWrap
      maximumLineCount: root.linesEach
      elide: Text.ElideRight
      verticalAlignment: Text.AlignTop
      text: slot.text !== "" ? slot.text : slot.placeholder
      textFormat: Text.PlainText
      color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b,
                     slot.text !== "" ? slot.strength : 0.4)
      font.family: root.fontFamily
      font.pixelSize: root.pixelSize
      font.italic: slot.text === ""
    }
  }

  Slot {
    text: root.tail(root.reply)
    placeholder: root.replyPlaceholder
    accent: root.replyAccent
    strength: 0.7
  }
  Slot {
    text: root.tail(root.transcript)
    placeholder: root.transcriptPlaceholder
    accent: root.nowAccent
    strength: 1.0
  }
}
