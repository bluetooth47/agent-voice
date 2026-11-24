import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// One exchange in a conversation, drawn the way a messaging app draws it
// (phase M18, feedback item 6): what you said in a bubble on the right, the
// agent's answer in one on the left with its name and its own colour, how
// it ended under that. This session's view and a saved chat draw it the
// same way.
//
//   ExchangeItem {
//     width: parent.width
//     when: "3:04 PM"; who: "Theo"; tint: "#7aa2f7"; latencyMs: 1800
//     heard: "make the hud wider"; answer: "Done."
//     failure: ""; wasStopped: false; startsNew: false
//     aside: ""      // "Theo asked Sora": a question between agents (Phase 16)
//     askedName: ""; askedTint: "transparent"
//   }
//
// An aside is drawn folded to its one line; a click opens the question and
// the answer, each as the bubble of the agent that wrote it -- both halves
// are agents' words, neither is yours. Everything shown is plain text.
Column {
  id: turn

  property string when: ""
  property string who: ""
  // The answering agent's colour, from the theme (Settings.agentTint).
  property color tint: "transparent"
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
  property string askedName: ""
  property color askedTint: "transparent"
  property bool asideOpen: false
  readonly property bool folded: aside !== "" && !asideOpen

  property color foreground: Commons.Color.foreground
  property color background: Commons.Color.background
  property color accent: Commons.Color.accent
  property color urgent: Commons.Color.urgent
  property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  spacing: Style.space(6)

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

  // A question between agents: one dim line, centred like a note, that
  // opens to the two bubbles.
  Text {
    visible: turn.aside !== ""
    width: parent.width
    horizontalAlignment: Text.AlignHCenter
    elide: Text.ElideRight
    text: (turn.asideOpen ? "▾ " : "▸ ") + turn.aside + (turn.when !== "" ? " · " + turn.when : "")
    textFormat: Text.PlainText
    color: turn.dim
    font.family: turn.fontFamily
    font.pixelSize: Style.font.caption
    font.underline: activeFocus
    // Opened from the keyboard too (master plan M29).
    activeFocusOnTab: visible
    Keys.onReturnPressed: turn.asideOpen = !turn.asideOpen
    Keys.onEnterPressed: turn.asideOpen = !turn.asideOpen
    Keys.onSpacePressed: turn.asideOpen = !turn.asideOpen
    Accessible.role: Accessible.Button
    Accessible.name: (turn.asideOpen ? "Hide " : "Show ") + "the question between agents"
    Accessible.focusable: true
    Accessible.onPressAction: turn.asideOpen = !turn.asideOpen
    MouseArea {
      anchors.fill: parent
      cursorShape: Qt.PointingHandCursor
      onClicked: turn.asideOpen = !turn.asideOpen
    }
  }

  // What you said; or, opened, the question one agent asked another.
  ChatBubble {
    visible: !turn.folded && turn.heard !== ""
    width: parent.width
    mine: turn.aside === ""
    who: turn.aside === "" ? "You" : turn.who
    when: turn.aside === "" ? turn.when : ""
    stripe: turn.aside === "" ? "transparent" : turn.tint
    text: turn.heard
    foreground: turn.foreground
    accent: turn.accent
    fontFamily: turn.fontFamily
  }

  // Folded by default: it is often longer than the answer and was never
  // said out loud. Plain text, like the rest -- a model wrote it.
  Text {
    visible: turn.thinking !== "" && !turn.folded
    width: parent.width * 0.8
    leftPadding: Style.space(4)
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
    font.underline: activeFocus
    activeFocusOnTab: visible
    Keys.onReturnPressed: turn.thinkingOpen = !turn.thinkingOpen
    Keys.onEnterPressed: turn.thinkingOpen = !turn.thinkingOpen
    Keys.onSpacePressed: turn.thinkingOpen = !turn.thinkingOpen
    Accessible.role: Accessible.Button
    Accessible.name: (turn.thinkingOpen ? "Fold " : "Unfold ") + "what it thought"
    Accessible.focusable: true
    Accessible.onPressAction: turn.thinkingOpen = !turn.thinkingOpen
    MouseArea {
      anchors.fill: parent
      cursorShape: Qt.PointingHandCursor
      onClicked: turn.thinkingOpen = !turn.thinkingOpen
    }
  }

  // The answer, on the left, named: the speaker is always said, because a
  // chat can hold several agents' replies.
  ChatBubble {
    visible: !turn.folded && turn.answer !== ""
    width: parent.width
    who: turn.aside === "" ? turn.who : (turn.askedName || "the other agent")
    when: turn.aside !== "" ? ""
          : (turn.latencyMs > 0 ? "answered in " + (turn.latencyMs / 1000).toFixed(1) + "s" : "")
    stripe: turn.aside === "" ? turn.tint : turn.askedTint
    text: turn.answer
    foreground: turn.foreground
    accent: turn.accent
    fontFamily: turn.fontFamily
  }

  Text {
    visible: (turn.failure !== "" || turn.wasStopped) && !turn.folded
    leftPadding: Style.space(4)
    text: (turn.who !== "" ? turn.who + " · " : "")
          + (turn.failure !== "" ? "failed" : "stopped part-way")
    textFormat: Text.PlainText
    color: turn.failure !== "" ? turn.urgent : turn.dim
    font.family: turn.fontFamily
    font.pixelSize: Style.font.caption
  }
}
