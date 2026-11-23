import QtQuick
import qs.Commons
import qs.Commons as Commons

// One turn, start to end, drawn from the settings that shape it (master plan
// M24): the wait for you to start, you talking up to the longest a turn can
// be, the pause that ends it, the reply, and the follow-up window after it.
//
//   TurnTimeline { width: parent.width; leadInMs: 5000; talkMs: 30000
//                  pauseMs: 1200; quickMs: 800; followMs: 7000; limitHits: 0 }
//
// The widths are for reading, not to scale: a 1.2 s pause beside a 30 s limit
// would be a hairline. Each block grows with the square root of its time, and
// the legend under the bar says so and gives the real numbers, so the picture
// is never the only place a value is written.
//
// `followMs` of 0 leaves the follow-up out (it is switched off), `quickMs` of
// 0 leaves out the shorter pause. `limitHits` above 0 marks the end of "you
// talk" in the urgent colour: that is where turns were cut today.
Column {
  id: tl
  objectName: "turnTimeline"

  property real leadInMs: 5000
  property real talkMs: 30000
  property real pauseMs: 1200
  property real quickMs: 800
  property real followMs: 7000
  property int limitHits: 0

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property color urgent: Commons.Color.urgent
  readonly property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  spacing: Style.space(6)

  // "5 s", "1.2 s", "800 ms". A value that is not a number reads "?" rather
  // than "NaN s": the page hands in what it could parse, and this is the
  // last place a bad one could be shown.
  function fmt(ms) {
    var v = Number(ms)
    if (!isFinite(v)) return "?"
    if (v < 1000) return Math.round(v) + " ms"
    var s = v / 1000
    return (Math.abs(s - Math.round(s)) < 0.05 ? String(Math.round(s)) : s.toFixed(1)) + " s"
  }
  function grow(ms) {
    var v = Number(ms)
    return Math.sqrt(Math.max(0.3, isFinite(v) ? v / 1000 : 1))
  }

  // What is drawn, in order. `w` is the block's share of the bar.
  readonly property var segments: {
    var out = [
      { key: "leadin", label: "Lead-in", short: "wait", tone: "dim", w: grow(leadInMs),
        note: "up to " + fmt(leadInMs) + " for you to start" },
      { key: "talk", label: "You talk", short: "you talk", tone: "accent", w: grow(talkMs) * 1.2,
        note: "up to " + fmt(talkMs) + " from your first word" },
      { key: "pause", label: "Pause", short: "pause", tone: "fore", w: Math.max(grow(pauseMs), 0.9),
        note: fmt(pauseMs) + " of quiet ends it" + (Number(quickMs) > 0
              ? ", " + fmt(quickMs) + " after a finished sentence" : "") },
      { key: "reply", label: "Reply", short: "reply", tone: "dim", w: 1.6,
        note: "spoken, then it waits" }
    ]
    if (Number(followMs) > 0)
      out.push({ key: "follow", label: "Follow-up", short: "follow-up", tone: "accent", w: grow(followMs),
                 note: "listens " + fmt(followMs) + " without the wake word" })
    return out
  }
  readonly property real total: {
    var t = 0
    for (var i = 0; i < segments.length; i++) t += segments[i].w
    return t
  }
  readonly property int gap: Math.max(2, Style.space(3))

  function fillFor(tone, strong) {
    var c = tone === "accent" ? accent : foreground
    return Qt.rgba(c.r, c.g, c.b, tone === "dim" ? 0.08 : (strong ? 0.32 : 0.2))
  }
  function lineFor(tone) {
    var c = tone === "accent" ? accent : foreground
    return Qt.rgba(c.r, c.g, c.b, tone === "dim" ? 0.3 : 0.7)
  }

  Row {
    id: bar
    width: parent.width
    height: Style.space(26)
    spacing: tl.gap

    Repeater {
      model: tl.segments
      delegate: Rectangle {
        required property var modelData
        objectName: "seg-" + modelData.key
        width: (bar.width - tl.gap * (tl.segments.length - 1)) * modelData.w / tl.total
        height: bar.height
        radius: Style.cornerRadius / 2
        color: tl.fillFor(modelData.tone, modelData.key === "talk")
        border.width: 1
        border.color: tl.lineFor(modelData.tone)

        Text {
          anchors.fill: parent
          anchors.leftMargin: Style.space(4)
          anchors.rightMargin: Style.space(4)
          verticalAlignment: Text.AlignVCenter
          horizontalAlignment: Text.AlignHCenter
          text: modelData.short
          textFormat: Text.PlainText
          elide: Text.ElideRight
          color: tl.foreground
          font.family: tl.fontFamily
          font.pixelSize: Style.font.caption
        }
        // Where turns were cut today: the end of "you talk".
        Rectangle {
          objectName: "limitMark"
          visible: modelData.key === "talk" && tl.limitHits > 0
          anchors.right: parent.right
          anchors.top: parent.top
          anchors.bottom: parent.bottom
          width: Math.max(3, Style.space(3))
          radius: width / 2
          color: tl.urgent
        }
      }
    }
  }

  Flow {
    width: parent.width
    spacing: Style.space(14)

    Repeater {
      model: tl.segments
      delegate: Row {
        required property var modelData
        objectName: "legend-" + modelData.key
        spacing: Style.space(5)
        Rectangle {
          anchors.verticalCenter: parent.verticalCenter
          width: Style.space(8)
          height: width
          radius: 2
          color: tl.fillFor(modelData.tone, modelData.key === "talk")
          border.width: 1
          border.color: tl.lineFor(modelData.tone)
        }
        Text {
          text: modelData.label + ": " + modelData.note
          textFormat: Text.PlainText
          color: tl.dim
          font.family: tl.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
    }
  }

  Text {
    width: parent.width
    text: "Widths are for reading, not to scale."
    textFormat: Text.PlainText
    color: tl.dim
    opacity: 0.8
    font.family: tl.fontFamily
    font.pixelSize: Style.font.caption
  }
}
