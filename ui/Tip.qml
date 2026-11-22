import QtQuick
import QtQuick.Controls as QQC
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// The tooltip every piece in ui/ uses, drawn the way Omarchy's Button draws
// its own: the theme's tooltip colours and border, plain text. One place, so
// a Hint's detail, a disabled chip's reason and a bar's number look alike.
//
//   Tip { tipText: "Why this is off"; shown: area.containsMouse }
//
// Plain text always: a tooltip often repeats a name somebody typed or a
// path, and AutoText renders anything that looks like markup.
QQC.ToolTip {
  id: tip

  property string tipText: ""
  property bool shown: false
  property string fontFamily: Style.font.family

  readonly property var _border: Border.localOrSurfaceSpec("tooltip", "border", Commons.Color.tooltip.border,
                                                            Commons.Color.tooltip.border, Math.max(1, Style.normalBorderWidth))

  visible: shown && tipText !== ""
  delay: 400
  padding: 0
  text: tipText

  background: BorderSurface {
    color: Commons.Color.tooltip.background
    borderSpec: tip._border
    radius: 0
  }
  contentItem: Text {
    textFormat: Text.PlainText
    text: tip.tipText
    wrapMode: Text.WordWrap
    width: Math.min(implicitWidth, Style.space(360))
    color: Commons.Color.tooltip.text
    font.family: tip.fontFamily
    font.pixelSize: Style.font.bodySmall
    leftPadding: Border.left(tip._border) + Style.spacing.controlPaddingX
    rightPadding: Border.right(tip._border) + Style.spacing.controlPaddingX
    topPadding: Border.top(tip._border) + Style.spacing.controlPaddingY
    bottomPadding: Border.bottom(tip._border) + Style.spacing.controlPaddingY
  }
}
