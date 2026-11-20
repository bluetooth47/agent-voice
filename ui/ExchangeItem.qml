import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// One exchange in a conversation: what was said, what was answered, and
// how it ended. The session's view and a saved chat draw it the same way.
//
//   ExchangeItem {
//     width: parent.width
//     when: "3:04 PM"; who: "Theo"; latencyMs: 1800
//     heard: "make the hud wider"; answer: "Done."
//     failure: ""; wasStopped: false; startsNew: false
//     aside: ""      // "Theo asked Sora": a question between agents (Phase 16)
//   }
//
// An aside is drawn folded to its one line; a click opens the question
// (heard) and the answer. Both halves are an agent's words, plain text.
Column {
  id: turn

  property string when: ""
  property string who: ""
  property int latencyMs: 0
  property string heard: ""
  property string answer: ""
  property string failure: ""
  property bool wasStopped: false
  // A reasoning model's thinking: never spoken, shown greyed and folded.
  property string thinking: ""
  property bool thinkingOpen: false
  // Draws the "new conversation" rule above it.
  property bool startsNew: false
  // "Theo asked Sora" for a question one agent asked another; "" otherwise.
  property string aside: ""
  property bool asideOpen: false
  readonly property bool folded: aside !== "" && !asideOpen

  property color foreground: Commons.Color.foreground
  property color background: Commons.Color.background
  property color urgent: Commons.Color.urgent
  property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  spacing: Style.space(4)

  // Where a conversation began: a turn sent with no session to continue.
  // "What did I ask it earlier" is usually this one.
  Item {
    visible: turn.startsNew
    width: parent.width
    height: visible ? newLabel.implicitHeight + Style.space(10) : 0
    PanelSeparator {
      anchors.verticalCenter: newLabel.verticalCenter
      width: parent.width
      foreground: turn.foreground
    }
    Text {
      id: newLabel
      anchors.horizontalCenter: parent.horizontalCenter
      leftPadding: Style.space(8)
      rightPadding: Style.space(8)
      text: "new conversation"
      color: turn.dim
      font.family: turn.fontFamily
      font.pixelSize: Style.font.caption
      Rectangle {
        z: -1
        anchors.fill: parent
        color: turn.background
      }
    }
  }

  Text {
    width: parent.width
    elide: Text.ElideRight
    text: (turn.aside !== "" ? (turn.asideOpen ? "▾ " : "▸ ") : "") + turn.when
          + (turn.aside !== "" ? " · " + turn.aside
             : (turn.who !== "" ? " · " + turn.who : ""))
          + (turn.latencyMs > 0 ? " · answered in " + (turn.latencyMs / 1000).toFixed(1) + "s" : "")
    textFormat: Text.PlainText
    color: turn.dim
    font.family: turn.fontFamily
    font.pixelSize: Style.font.caption
    MouseArea {
      anchors.fill: parent
      enabled: turn.aside !== ""
      cursorShape: turn.aside !== "" ? Qt.PointingHandCursor : Qt.ArrowCursor
      onClicked: turn.asideOpen = !turn.asideOpen
    }
  }

  // TextEdit, read-only, rather than Text: selectable, so a path or a
  // command the agent read out can be copied, not retyped. Plain text for
  // the same reason every other transcript here is -- neither half of this
  // was written by us.
  TextEdit {
    visible: !turn.folded
    width: parent.width
    readOnly: true
    selectByMouse: true
    wrapMode: TextEdit.Wrap
    textFormat: TextEdit.PlainText
    text: turn.heard
    color: turn.foreground
    selectionColor: Qt.rgba(turn.foreground.r, turn.foreground.g, turn.foreground.b, 0.3)
    selectedTextColor: turn.foreground
    font.family: turn.fontFamily
    font.pixelSize: Style.font.body
  }

  // Folded by default: it is often longer than the answer and was never
  // said out loud. Plain text, like the rest -- a model wrote it.
  Text {
    visible: turn.thinking !== ""
    width: parent.width
    wrapMode: Text.Wrap
    maximumLineCount: turn.thinkingOpen ? 400 : 1
    elide: Text.ElideRight
    textFormat: Text.PlainText
    text: (turn.thinkingOpen ? "▾ thought (not spoken): " : "▸ thought (not spoken): ")
          + turn.thinking
    color: Qt.rgba(turn.foreground.r, turn.foreground.g, turn.foreground.b, 0.4)
    font.family: turn.fontFamily
    font.pixelSize: Style.font.caption
    font.italic: true
    MouseArea {
      anchors.fill: parent
      cursorShape: Qt.PointingHandCursor
      onClicked: turn.thinkingOpen = !turn.thinkingOpen
    }
  }

  Item {
    visible: turn.answer !== "" && !turn.folded
    width: parent.width
    height: visible ? replyText.implicitHeight : 0

    // A rule down the left of the answer, rather than an arrow in its text
    // that would come along with every copy.
    Rectangle {
      width: Style.space(2)
      height: parent.height
      color: Qt.rgba(turn.foreground.r, turn.foreground.g, turn.foreground.b, 0.35)
    }
    TextEdit {
      id: replyText
      x: Style.space(10)
      width: parent.width - x
      readOnly: true
      selectByMouse: true
      wrapMode: TextEdit.Wrap
      textFormat: TextEdit.PlainText
      text: turn.answer
      color: Qt.rgba(turn.foreground.r, turn.foreground.g, turn.foreground.b, 0.8)
      selectionColor: Qt.rgba(turn.foreground.r, turn.foreground.g, turn.foreground.b, 0.3)
      selectedTextColor: turn.foreground
      font.family: turn.fontFamily
      font.pixelSize: Style.font.body
    }
  }

  Text {
    visible: turn.failure !== "" || turn.wasStopped
    text: turn.failure !== "" ? "failed" : "stopped part-way"
    color: turn.failure !== "" ? turn.urgent : turn.dim
    font.family: turn.fontFamily
    font.pixelSize: Style.font.caption
  }
}
