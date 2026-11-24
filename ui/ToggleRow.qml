import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// A SettingRow with a switch in it: the shape of most settings here.
//
//   ToggleRow {
//     width: parent.width
//     label: "Speak replies aloud"
//     checked: s.setting("speakReplies", true) === true
//     changed: s.changed("speakReplies")
//     onToggled: s.put("speakReplies", !checked)
//     onReset: s.resetKey("speakReplies")
//   }
//
// The switch shows the new position the moment it is clicked: `checked`
// comes from the settings store, which shows a change before shell.json
// has it (ui/SettingsStore).
//
// The switch takes the keyboard (ui/FocusSwitch, master plan M29): Tab
// reaches it, Space flips it, and a screen reader hears the row's label.
SettingRow {
  id: row

  property bool checked: false
  property bool busy: false

  signal toggled()

  FocusSwitch {
    checked: row.checked
    busy: row.busy
    foreground: row.foreground
    accent: row.accent
    accessibleName: row.label
    Accessible.description: row.applies ? row.hint : row.disabledReason
    onToggled: row.toggled()
  }
}
