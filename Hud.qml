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
import "ui"

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
// Two sizes (phase M3, hudSize). Locked, the default: one width and one
// height whatever it shows -- a header and two fixed lines, the agent's last
// answer and what is being said now (ui/ReadoutLines), long text showing its
// newest words -- so nothing on it appears, disappears or moves from one turn
// to the next. Dynamic, the earlier behaviour: it sizes itself to what it is
// showing. That was a fixed 280 wide with the transcript cut at three lines
// and the answer at six, so anything worth reading was an ellipsis --
// reported from use as "if a response or prompt is too long the popup is too
// small" -- and it widens to fit, up to a share of the screen; grows taller,
// up to most of it; and past that it scrolls, following the answer down as
// it is spoken unless you have scrolled back to reread.
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
  // Collaboration between agents (Phase 15), one line: "Theo → Sora:
  // passing", "Sora (for Theo): working", "Sora finished". Empty otherwise.
  property string collab: ""
  property color accent: Commons.Color.foreground
  // phase M3. The agent's previous answer, drawn while this turn has none of
  // its own yet; "" when hudKeepReply is off or there is none to keep.
  property string keptReply: ""
  // Locked (one size, two fixed lines) or dynamic (sized to fit).
  property bool locked: true
  // "top" or "bottom": the edge of the screen it sits at, on the right.
  property string position: "top"
  // 0.85, 1 or 1.25: small, medium (the bar's own size) or large.
  property real textScale: 1.0
  // The payload is the Display page's preview (readout.py). Its end closes
  // the readout at once: the linger is for reading a real answer.
  property bool preview: false
  property bool wasPreview: false
  // A real turn taking over mid-preview lingers as a turn does. The widget
  // sets `preview` after the state, so at the end of a preview `busy` has
  // already gone false and this does not fire while busy.
  onPreviewChanged: if (busy) wasPreview = preview
  readonly property real bodySize: Math.round(Style.font.body * textScale)
  readonly property real captionSize: Math.round(Style.font.caption * textScale)
  // The header names the state and, with several agents, whose turn it is;
  // in locked mode it carries the collaboration line too, so that line does
  // not come and go as a row of its own.
  readonly property string headerText: (who !== "" ? who + " · " + stateLabel : stateLabel)
                                       + (locked && collab !== "" ? " · " + collab : "")

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
        || vState === "followup"
        // A pass waiting out its cancel window is worth seeing; never over
        // the lock screen.
        || (collab !== "" && vState !== "locked" && vState !== "off"))

  property bool showing: false

  onBusyChanged: {
    if (busy) {
      linger.stop()
      showing = true
      wasPreview = preview
    } else if (showing && wasPreview) {
      linger.stop()
      showing = false
      wasPreview = false
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
  // Locked: one width, from the text size, bounded like the dynamic one.
  readonly property int lockedWidth: Math.round(Math.max(minWidth,
                                                         Math.min(maxWidth, Style.space(440) * textScale)))
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
    font.pixelSize: hud.bodySize
    text: hud.transcript === "" ? "" : "“" + hud.transcript + "”"
  }
  TextMetrics {
    id: replyWidth
    font.family: hud.fontFamily
    font.pixelSize: hud.bodySize
    text: hud.reply !== "" ? "→ " + hud.reply : hud.keptReply !== "" ? "→ " + hud.keptReply : ""
  }
  TextMetrics {
    id: headerWidth
    font.family: hud.fontFamily
    font.pixelSize: hud.captionSize
    text: hud.headerText
  }
  readonly property real wanted: Math.max(heardWidth.width, replyWidth.width,
                                          headerIcon.implicitWidth + Style.space(6) + headerWidth.width)
  readonly property int textWidth: locked ? lockedWidth - pad * 2
                                   : Math.round(Math.min(maxWidth - pad * 2,
                                                         Math.max(minWidth - pad * 2,
                                                                  wanted + Style.space(2))))

  visible: showing
  implicitWidth: textWidth + pad * 2
  // Locked: everything in the body is a fixed height, so this is a constant.
  implicitHeight: Math.min(maxHeight, body.implicitHeight + pad * 2)

  color: "transparent"
  exclusionMode: ExclusionMode.Ignore
  WlrLayershell.namespace: "agentvoice-hud"
  WlrLayershell.layer: WlrLayer.Overlay
  WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

  // At the edge hudPosition names (phase M3; it used to follow the bar),
  // on the right: below a top bar, above a bottom one, and clear of a
  // vertical one. Falls back to a plain corner offset when the bar does not
  // say where it is.
  readonly property string barSide: bar && bar.position ? bar.position : "top"
  readonly property string edge: position === "bottom" ? "bottom" : "top"
  anchors {
    top: hud.edge === "top"
    bottom: hud.edge === "bottom"
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
          height: Math.max(headerIcon.implicitHeight, headerLabel.implicitHeight)

          Text {
            id: headerIcon
            anchors.verticalCenter: parent.verticalCenter
            text: hud.icon
            color: hud.accent
            font.family: hud.fontFamily
            font.pixelSize: hud.bodySize
          }
          Text {
            id: headerLabel
            anchors.left: headerIcon.right
            anchors.leftMargin: Style.space(6)
            anchors.right: clickHint.visible ? clickHint.left : parent.right
            anchors.rightMargin: clickHint.visible ? Style.space(6) : 0
            anchors.verticalCenter: parent.verticalCenter
            text: hud.headerText
            // Agents' names and the collaboration line are text somebody
            // typed or a model wrote.
            textFormat: Text.PlainText
            elide: Text.ElideRight
            maximumLineCount: 1
            color: Commons.Color.tooltip.text
            font.family: hud.fontFamily
            font.pixelSize: hud.captionSize
          }

          // Said only while the pointer is here, so it never costs room in a
          // readout that is mostly glanced at.
          Text {
            id: clickHint
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            visible: hover.hovered
            text: "click for the conversation"
            color: Qt.rgba(Commons.Color.tooltip.text.r, Commons.Color.tooltip.text.g,
                           Commons.Color.tooltip.text.b, 0.6)
            font.family: hud.fontFamily
            font.pixelSize: hud.captionSize
          }
        }

        // Locked: the two fixed lines.
        ReadoutLines {
          width: parent.width
          visible: hud.locked
          reply: hud.reply !== "" ? hud.reply : hud.keptReply
          transcript: hud.transcript
          pixelSize: hud.bodySize
          fontFamily: hud.fontFamily
          foreground: Commons.Color.tooltip.text
          replyAccent: Commons.Color.accent
          nowAccent: hud.accent
        }

        // Dynamic from here down: the lines come and go and wrap in full.
        Text {
          width: parent.width
          visible: !hud.locked && hud.collab !== ""
          wrapMode: Text.WordWrap
          text: hud.collab
          // Agents' names are any text somebody typed.
          textFormat: Text.PlainText
          color: hud.accent
          font.family: hud.fontFamily
          font.pixelSize: hud.captionSize
        }

        // The previous answer, while this turn has none yet: it came before
        // what is being said now, so it sits above it.
        Text {
          width: parent.width
          visible: !hud.locked && hud.reply === "" && hud.keptReply !== ""
          wrapMode: Text.WordWrap
          text: "→ " + hud.keptReply
          textFormat: Text.PlainText
          color: Qt.rgba(Commons.Color.tooltip.text.r, Commons.Color.tooltip.text.g,
                         Commons.Color.tooltip.text.b, 0.6)
          font.family: hud.fontFamily
          font.pixelSize: hud.bodySize
        }

        Text {
          width: parent.width
          visible: !hud.locked && hud.transcript !== ""
          wrapMode: Text.WordWrap
          text: "“" + hud.transcript + "”"
          // Whatever was said out loud, and whatever a model answered, are
          // both strings this did not write. AutoText would render anything
          // that looks like HTML as rich text, which hides characters and can
          // make the bar fetch an <img src> of someone else's choosing.
          textFormat: Text.PlainText
          color: Commons.Color.tooltip.text
          font.family: hud.fontFamily
          font.pixelSize: hud.bodySize
        }

        // The answer, growing a sentence at a time as it is said. Dimmed
        // against the transcript so the two are told apart at a glance rather
        // than by reading them.
        Text {
          width: parent.width
          visible: !hud.locked && hud.reply !== ""
          wrapMode: Text.WordWrap
          text: "→ " + hud.reply
          textFormat: Text.PlainText
          color: Qt.rgba(Commons.Color.tooltip.text.r, Commons.Color.tooltip.text.g,
                         Commons.Color.tooltip.text.b, 0.8)
          font.family: hud.fontFamily
          font.pixelSize: hud.bodySize
        }
      }
    }
  }
}
