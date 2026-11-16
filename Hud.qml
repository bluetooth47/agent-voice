import QtQuick
import QtQuick.Controls as QQC
import Quickshell
import Quickshell.Wayland
import qs.Commons
// Namespaced as well: on Qt 6.12 a bare `Color` resolves to QtQuick's own
// value-type helper, not to the theme, and every colour read through it was
// undefined. Omarchy's own QML writes Commons.Color for the same reason.
import qs.Commons as Commons
import qs.Ui

// What it is doing, while it is doing it, without taking the keyboard.
//
// The obvious implementation was to call open() on the widget's own panel when
// the wake word fires. That panel is a KeyboardPanel, and its onOpenChanged
// sets focusPrimed = false and primes WlrKeyboardFocus.Exclusive -- so it takes
// keyboard focus on every open, and the flag cannot be pre-set because opening
// clears it. A reply plus its follow-up window is roughly 25 seconds of
// somebody's typing going to a status readout, which is the opposite of what a
// hands-free interface is for.
//
// So this is a layer-shell surface with keyboardFocus None and the exclusion
// zone ignored, the same shape Omarchy's own notifications use. It can never
// steal focus and never moves anything else on screen.
//
// It sizes itself to what it is showing. It was a fixed 280 wide with the
// transcript cut at three lines and the answer at six, so anything worth
// reading was an ellipsis -- reported from use as "if a response or prompt is
// too long the popup is too small". Now it widens to fit, up to a share of the
// screen; grows taller, up to most of it; and past that it scrolls, following
// the answer down as it is spoken unless you have scrolled back to reread.
PanelWindow {
  id: hud

  // Live state, passed in rather than re-read: the widget already watches the
  // state file, and two watchers on one file would disagree during a write.
  property string vState: "off"
  property string stateLabel: ""
  property string icon: ""
  property string transcript: ""
  property string reply: ""
  // Which agent this is, when there is more than one: the name that wakes
  // it. Empty with a single agent, which then reads exactly as it did.
  property string who: ""
  property color accent: Commons.Color.foreground

  // `var`, not QtObject: the bar is reached for position and thickness, and
  // a QtObject-typed handle makes those unresolvable to qmllint -- which
  // the check script rejects, for the good reason that it cannot tell a
  // real typo from a duck-typed one.
  property var bar: null
  property string fontFamily: Style.font.family
  property int lingerMs: 2000
  property bool enabled: true

  // A click asks for the whole conversation. A signal, not a Process here:
  // the widget already owns the summon, and this surface stays a readout.
  signal openConversation()

  // The states that mean an exchange is under way. `followup` is included:
  // the window is still open, another sentence may follow, and closing on it
  // would flicker between turns.
  readonly property bool busy: enabled
    && (vState === "capture" || vState === "transcribing"
        || vState === "thinking" || vState === "speaking"
        || vState === "followup")

  property bool showing: false

  onBusyChanged: {
    if (busy) {
      linger.stop()
      showing = true
    } else if (showing) {
      // Restart, not start: a rapid followup -> capture -> followup bounce
      // would otherwise leave an earlier timer to close it mid-sentence.
      linger.interval = Math.max(0, hud.lingerMs)
      linger.restart()
    }
  }

  onEnabledChanged: if (!enabled) { linger.stop(); showing = false }

  // A lock hides it at once, with no linger. This is a layer-shell surface,
  // so it draws over the lock screen: lingering would leave the last thing
  // you said and the last thing the agent answered on screen above a locked
  // machine, for up to the linger setting. Which is the one place a readout
  // of the exchange must not be. Hovering does not hold it either.
  onVStateChanged: if (vState === "locked") { linger.stop(); showing = false }

  // A new question starts at the top, following whatever is said next.
  onTranscriptChanged: scroller.following = true

  Timer {
    id: linger
    repeat: false
    // Not while the pointer is on it: somebody reading a long answer should
    // not have it taken away mid-line. Leaving restarts the countdown.
    onTriggered: if (!hover.hovered) hud.showing = false
  }

  // --- size ---------------------------------------------------------------

  readonly property int pad: Style.space(12)
  readonly property real screenWidth: hud.screen ? hud.screen.width : 1920
  readonly property real screenHeight: hud.screen ? hud.screen.height : 1080
  readonly property int minWidth: Style.space(280)
  // A share of the screen rather than a number: wide enough that a long
  // answer reads in lines, not a column, and still a corner readout.
  readonly property int maxWidth: Math.max(minWidth,
                                           Math.min(Style.space(560), screenWidth * 0.4))
  readonly property int maxHeight: Math.max(Style.space(120),
                                            (screenHeight - barThickness) * 0.6)

  // The width each line would take unwrapped. Measured, not read from the
  // Texts' implicitWidth, because their width depends on this window's --
  // a binding loop the other way round.
  TextMetrics {
    id: heardWidth
    font.family: hud.fontFamily
    font.pixelSize: Style.font.body
    text: hud.transcript === "" ? "" : "“" + hud.transcript + "”"
  }
  TextMetrics {
    id: replyWidth
    font.family: hud.fontFamily
    font.pixelSize: Style.font.body
    text: hud.reply === "" ? "" : "→ " + hud.reply
  }
  readonly property real wanted: Math.max(heardWidth.width, replyWidth.width,
                                          header.implicitWidth)
  readonly property int textWidth: Math.round(Math.min(maxWidth - pad * 2,
                                                       Math.max(minWidth - pad * 2,
                                                                wanted + Style.space(2))))

  visible: showing
  implicitWidth: textWidth + pad * 2
  implicitHeight: Math.min(maxHeight, body.implicitHeight + pad * 2)

  color: "transparent"
  exclusionMode: ExclusionMode.Ignore
  WlrLayershell.namespace: "agentvoice-hud"
  WlrLayershell.layer: WlrLayer.Overlay
  WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

  // Below a top bar, above a bottom one, and clear of a vertical one. Falls
  // back to a plain corner offset when the bar does not say where it is.
  readonly property string barSide: bar && bar.position ? bar.position : "top"
  anchors {
    top: hud.barSide !== "bottom"
    bottom: hud.barSide === "bottom"
    right: true
  }
  margins {
    top: hud.barSide === "top" ? hud.barThickness + Style.space(6) : Style.space(6)
    bottom: hud.barSide === "bottom" ? hud.barThickness + Style.space(6) : Style.space(6)
    right: hud.barSide === "right" ? hud.barThickness + Style.space(6) : Style.space(6)
  }
  readonly property int barThickness: bar && bar.height > 0 ? bar.height : Style.space(10)

  Rectangle {
    anchors.fill: parent
    radius: Style.cornerRadius
    color: Commons.Color.tooltip.background
    border.width: 1
    // Qt.rgba on the components, not Qt.alpha: the latter appears nowhere in
    // Omarchy's own QML, and an unverifiable helper in a surface nothing can
    // screenshot is a poor bet.
    border.color: Qt.rgba(hud.accent.r, hud.accent.g, hud.accent.b, 0.35)

    // Pointer handlers, not a MouseArea: those take the wheel events the
    // scroller below needs, and these leave them alone.
    HoverHandler {
      id: hover
      onHoveredChanged: {
        if (hovered) linger.stop()
        else if (hud.showing && !hud.busy) {
          linger.interval = Math.max(0, hud.lingerMs)
          linger.restart()
        }
      }
    }
    TapHandler {
      onTapped: hud.openConversation()
    }

    Flickable {
      id: scroller
      anchors.fill: parent
      anchors.margins: hud.pad
      contentWidth: width
      contentHeight: body.implicitHeight
      clip: true
      boundsBehavior: Flickable.StopAtBounds
      flickableDirection: Flickable.VerticalFlick
      interactive: contentHeight > height
      QQC.ScrollBar.vertical: QQC.ScrollBar {
        policy: QQC.ScrollBar.AsNeeded
      }

      // Pinned to the end while the answer grows, the way a terminal is --
      // until you scroll up to reread, which unpins it until the next turn.
      property bool following: true
      onMovementEnded: following = atYEnd
      onContentHeightChanged: {
        if (following && contentHeight > height)
          contentY = contentHeight - height
      }

      Column {
        id: body
        width: scroller.width
        spacing: Style.space(4)

        Item {
          width: parent.width
          height: header.implicitHeight

          Row {
            id: header
            spacing: Style.space(6)
            Text {
              text: hud.icon
              color: hud.accent
              font.family: hud.fontFamily
              font.pixelSize: Style.font.body
            }
            Text {
              text: hud.who !== "" ? hud.who + " · " + hud.stateLabel : hud.stateLabel
              textFormat: Text.PlainText
              color: Commons.Color.tooltip.text
              font.family: hud.fontFamily
              font.pixelSize: Style.font.caption
            }
          }

          // Said only while the pointer is here, so it never costs room in a
          // readout that is mostly glanced at.
          Text {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            visible: hover.hovered
            text: "click for the conversation"
            color: Qt.rgba(Commons.Color.tooltip.text.r, Commons.Color.tooltip.text.g,
                           Commons.Color.tooltip.text.b, 0.6)
            font.family: hud.fontFamily
            font.pixelSize: Style.font.caption
          }
        }

        Text {
          width: parent.width
          visible: hud.transcript !== ""
          wrapMode: Text.WordWrap
          text: "“" + hud.transcript + "”"
          // Whatever was said out loud, and whatever a model answered, are
          // both strings this did not write. AutoText would render anything
          // that looks like HTML as rich text, which hides characters and can
          // make the bar fetch an <img src> of someone else's choosing.
          textFormat: Text.PlainText
          color: Commons.Color.tooltip.text
          font.family: hud.fontFamily
          font.pixelSize: Style.font.body
        }

        // The answer, growing a sentence at a time as it is said. Dimmed
        // against the transcript so the two are told apart at a glance rather
        // than by reading them.
        Text {
          width: parent.width
          visible: hud.reply !== ""
          wrapMode: Text.WordWrap
          text: "→ " + hud.reply
          textFormat: Text.PlainText
          color: Qt.rgba(Commons.Color.tooltip.text.r, Commons.Color.tooltip.text.g,
                         Commons.Color.tooltip.text.b, 0.8)
          font.family: hud.fontFamily
          font.pixelSize: Style.font.body
        }
      }
    }
  }
}
