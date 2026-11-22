import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// The model and its effort as one control: "opus ▾ │ high ▾". Effort means
// nothing without the model it belongs to, and on the old card they were
// two full-width rows apart.
//
// `efforts` empty hides the effort half. `effortReason` keeps it shown but
// says why it cannot be changed ("This model has no effort setting"), the
// way every control here that does nothing says why.
//
//   ModelPicker {
//     models: ["opus", "sonnet"]; model: card.modelData.model
//     efforts: ["low", "medium", "high"]; effort: card.modelData.effort
//     onModelCommitted: function(v) { page.updateAgent(i, "model", v) }
//     onEffortCommitted: function(v) { page.updateAgent(i, "effort", v) }
//   }
Rectangle {
  id: picker

  property var models: []
  property string model: ""
  property var efforts: []
  property string effort: ""
  property string effortReason: ""
  property string modelReason: ""
  property string modelPlaceholder: "default model"
  property string effortPlaceholder: "default"

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property string fontFamily: Style.font.family

  signal modelCommitted(string value)
  signal effortCommitted(string value)

  // From the selectors' natural widths, not the row's: the row holds the
  // widths they were given, so a picker narrowed once would ask for that
  // narrower width ever after (Codex review, M5).
  implicitWidth: modelSel.implicitWidth + (effortSel.visible ? effortSel.implicitWidth + 1 : 0) + 2
  implicitHeight: row.implicitHeight + 2
  radius: Style.cornerRadius
  color: "transparent"
  border.width: 1
  border.color: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.18)

  Row {
    id: row
    x: 1
    y: 1
    CompactSelector {
      id: modelSel
      // The room left once effort has its natural width: a long model name
      // elides here rather than pushing effort out of the picker.
      width: Math.max(0, Math.min(implicitWidth, picker.width - 2 -
                                  (effortSel.visible ? effortSel.width + 1 : 0)))
      framed: false
      label: "Model"
      options: picker.models
      value: picker.model
      placeholder: picker.modelPlaceholder
      disabledReason: picker.modelReason
      foreground: picker.foreground
      accent: picker.accent
      fontFamily: picker.fontFamily
      KeyNavigation.right: effortSel.visible ? effortSel : null
      onCommitted: function(v) { picker.modelCommitted(v) }
    }
    Rectangle {
      visible: effortSel.visible
      width: 1
      height: modelSel.height
      color: Qt.rgba(picker.foreground.r, picker.foreground.g, picker.foreground.b, 0.18)
    }
    CompactSelector {
      id: effortSel
      visible: picker.efforts.length > 0 || picker.effortReason !== ""
      // Effort elides too, past what leaves the model a usable target (an
      // unknown saved effort is shown as saved, however long).
      width: Math.max(0, Math.min(implicitWidth, picker.width - 3 - Math.min(modelSel.implicitWidth, Style.space(90))))
      framed: false
      label: "Effort"
      options: picker.efforts
      value: picker.effort
      placeholder: picker.effortPlaceholder
      disabledReason: picker.effortReason
      foreground: picker.foreground
      accent: picker.accent
      fontFamily: picker.fontFamily
      KeyNavigation.left: modelSel
      onCommitted: function(v) { picker.effortCommitted(v) }
    }
  }
}
