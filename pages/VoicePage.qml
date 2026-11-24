import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import ".."
import "../ui"

// What it sounds like, and how it turns your speech into text.
Column {
  id: page

  required property var s

  spacing: Style.space(18)

  readonly property bool speaks: s.setting("speakReplies", true) === true

  // The library's view: this page's own state, not a setting. It opens on
  // what is on this machine; "all" is one choice away.
  property string filter: "here"
  property string query: ""
  readonly property var filterOptions: [
    { value: "here", label: "Downloaded" },
    { value: "all", label: "All voices" },
    { value: "female", label: "Female" },
    { value: "male", label: "Male" },
    { value: "US", label: "American" },
    { value: "GB", label: "British" }
  ]

  // A voice matches the search when every word of it is in its name, quality,
  // gender or accent, so "british female" finds Alba, Cori and the others.
  function matches(v, q) {
    var words = String(q || "").toLowerCase().split(/\s+/)
    var hay = (v.label + " " + v.value + " " + v.gender + " " +
               (v.accent === "GB" ? "british" : "american") + " " + v.quality).toLowerCase()
    for (var i = 0; i < words.length; i++)
      if (words[i] !== "" && hay.indexOf(words[i]) < 0) return false
    return true
  }
  readonly property var shown: {
    var out = []
    var all = s.rawVoiceOptions
    for (var i = 0; i < all.length; i++) {
      var v = all[i]
      // A voice being fetched stays in Downloaded, so its progress is seen
      // rather than the row vanishing until it lands.
      if (page.filter === "here" && s.voicesOnDisk.indexOf(v.value) < 0
          && s.fetching !== v.value && s.fetchQueue.indexOf(v.value) < 0) continue
      if ((page.filter === "female" || page.filter === "male") && v.gender !== page.filter) continue
      if ((page.filter === "US" || page.filter === "GB") && v.accent !== page.filter) continue
      if (!page.matches(v, page.query)) continue
      out.push(v)
    }
    return out
  }

  // The main agent's voice and pace, and whom each agent hears: its own, or
  // the main agent's when it has none. The same reading as the Agents card.
  readonly property string mainVoice: String(s.setting("voice", "lessac-medium"))
  readonly property int mainSpeed: Number(s.setting("voiceSpeed", 100)) || 100
  function paceOf(speed) {
    var n = Math.round(Number(speed))
    return n >= 50 && n <= 200 ? n : page.mainSpeed
  }
  // [{ id, label, voice, own, speed, ownSpeed }] for the main agent and then
  // every extra one.
  readonly property var agentRows: {
    var out = [{ id: "main", label: s.mainLabel, voice: page.mainVoice, ownVoice: true,
                 speed: page.mainSpeed, ownSpeed: true }]
    for (var i = 0; i < s.voiceAgents.length; i++) {
      var a = s.voiceAgents[i] || {}
      if (String(a.name || "") === "") continue
      var v = String(a.voice || "")
      var sp = Number(a.speed || 0)
      out.push({ id: s.agentId(a), label: s.agentLabel(a),
                 voice: v !== "" ? v : page.mainVoice, ownVoice: v !== "",
                 speed: page.paceOf(sp > 0 ? sp : page.mainSpeed), ownSpeed: sp > 0 })
    }
    return out
  }
  readonly property var agentChoices: {
    var out = [{ label: "Main agent", value: "" }]
    for (var i = 0; i < s.voiceAgents.length; i++) {
      var a = s.voiceAgents[i] || {}
      if (String(a.name || "") !== "") out.push({ label: s.agentLabel(a), value: s.agentId(a) })
    }
    return out
  }

  PageHeader {
    width: parent.width
    title: "Voice"
    subtitle: "How replies sound, and how what you say becomes text."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
  }

  SettingsGroup {
    width: parent.width
    title: "QUICK SETTINGS"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    ToggleRow {
      objectName: "set-speakReplies"
      width: parent.width
      label: "Speak replies aloud"
      hint: "Off leaves the reply as text, in the readout and the conversation."
      checked: page.speaks
      changed: page.s.changed("speakReplies")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("speakReplies", !checked)
      onReset: page.s.resetKey("speakReplies")
    }

    ToggleRow {
      objectName: "set-chimes"
      width: parent.width
      label: "Sounds for listening, heard and done"
      hint: "A tone when the wake word lands, one when it has heard you, a chime when a long task ends."
      help: "So you know where it is without looking. Push-to-talk gets no opening " +
            "tone; the key is the signal."
      checked: page.s.setting("chimes", true) === true
      changed: page.s.changed("chimes")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("chimes", !checked)
      onReset: page.s.resetKey("chimes")
    }
  }

  SettingsGroup {
    width: parent.width
    title: "EACH AGENT"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      text: page.speaks ? "Who speaks in which voice, and how fast. Each is set on that agent's card."
                        : "Replies are not spoken, so these voices are not heard. Each is set on that agent's card."
      color: page.s.foreground
      opacity: 0.6
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.bodySmall
      textFormat: Text.PlainText
    }

    Column {
      width: parent.width
      spacing: Style.space(2)
      Repeater {
        model: page.agentRows
        VoiceAgentRow {
          required property var modelData
          width: parent.width
          name: modelData.label
          voiceName: page.s.voiceName(modelData.voice)
          pace: modelData.speed + "%"
          note: modelData.id !== "main" && (!modelData.ownVoice || !modelData.ownSpeed)
                ? (!modelData.ownVoice && !modelData.ownSpeed ? "follows the main agent"
                   : (!modelData.ownVoice ? "voice follows the main agent" : "speed follows the main agent"))
                : ""
          playing: page.s.samplePlaying === modelData.voice && page.s.samplePace === modelData.speed
          canTest: page.speaks && !page.s.voiceMissing(modelData.voice)
          testTip: !page.speaks ? "Replies are not spoken."
                   : page.s.voiceMissing(modelData.voice) ? "Not on this machine yet."
                   : playing ? "Stop the sample" : "Hear about a minute of this voice at its speed"
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onTest: page.s.playSample(modelData.voice, modelData.speed)
          onChange: page.s.goTo("agents", modelData.id)
        }
      }
    }
  }

  SettingsGroup {
    objectName: "voiceLibrary"
    width: parent.width
    title: "VOICES"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      text: page.s.voicesOnDisk.length + " of " + page.s.rawVoiceOptions.length +
            " on this machine. Test plays about a minute at the main agent's speed."
      color: page.s.foreground
      opacity: 0.6
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.bodySmall
      textFormat: Text.PlainText
    }

    Row {
      width: parent.width
      spacing: Style.space(8)
      SearchField {
        id: search
        objectName: "voiceSearch"
        width: parent.width - filterSelect.width - parent.spacing
        placeholder: "Search voices"
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onSearched: function(t) { page.query = t }
      }
      CompactSelector {
        id: filterSelect
        objectName: "voiceFilter"
        label: "Show"
        value: page.filter
        options: page.filterOptions
        tooltip: "Which voices the list shows"
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onCommitted: function(v) { page.filter = v }
      }
    }

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      text: "Every voice comes from the same pinned piper-voices revision as the installer and " +
            "is checked against its hash in models.lock before it is kept. low and medium are " +
            "about 63MB, high about 118MB. The default voice cannot be removed: it is what " +
            "speaks when another voice is missing."
      color: page.s.foreground
      opacity: 0.45
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
      textFormat: Text.PlainText
    }

    Text {
      visible: page.s.fetchError !== ""
      width: parent.width
      wrapMode: Text.Wrap
      text: "Download failed — " + page.s.fetchError
      color: Commons.Color.urgent
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.bodySmall
      textFormat: Text.PlainText
    }

    Column {
      width: parent.width
      spacing: Style.space(2)
      Repeater {
        model: page.shown
        VoiceLibraryRow {
          required property var modelData
          width: parent.width
          label: modelData.label.split(" — ")[0]
          detail: modelData.label.split(" — ")[1] + "  ·  " + modelData.mb + "MB"
          users: page.s.voiceUsers(modelData.value).join(", ")
          onDisk: page.s.voicesOnDisk.indexOf(modelData.value) >= 0
          playing: page.s.samplePlaying === modelData.value
          downloading: page.s.fetching === modelData.value
          queued: page.s.fetchQueue.indexOf(modelData.value) >= 0
          percent: page.s.fetchPct
          removable: modelData.value !== "lessac-medium" && users === ""
          agents: page.agentChoices
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onTest: page.s.playSample(modelData.value)
          onDownload: page.s.fetchVoice(modelData.value)
          onRemove: page.s.removeVoice(modelData.value)
          onUse: function(who) { page.s.assignVoice(who, modelData.value) }
        }
      }
    }

    Text {
      visible: page.shown.length === 0
      width: parent.width
      wrapMode: Text.WordWrap
      text: page.query !== "" ? "No voice matches “" + page.query + "”." +
                                (page.filter === "here" ? " Show All voices to search the ones not downloaded yet." : "")
                              : "Nothing here. Show All voices to download one."
      color: page.s.foreground
      opacity: 0.6
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.bodySmall
      textFormat: Text.PlainText
    }
  }

  AdvancedSection {
    objectName: "hearingAdvanced"
    width: parent.width
    title: "Advanced: hearing you"
    count: 2
    summary: "how your speech becomes text"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      text: "Transcription turns what you say into text on this machine, before anything is sent to an agent."
      color: page.s.foreground
      opacity: 0.6
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.bodySmall
      textFormat: Text.PlainText
    }

    SettingRow {
      objectName: "set-model"
      width: parent.width
      stacked: true
      label: "Transcription model"
      hint: "Larger is more accurate and slower to answer. tiny.en is right for most voices."
      changed: page.s.changed("model")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onReset: page.s.resetKey("model")
      SegmentedChoice {
        options: [
          { value: "tiny.en", label: "tiny.en", tooltip: "Fastest. The default." },
          { value: "base.en", label: "base.en", tooltip: "More accurate, a little slower." },
          { value: "small.en", label: "small.en", tooltip: "Most accurate, noticeably slower on a laptop." }
        ]
        value: page.s.setting("model", "tiny.en")
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onCommitted: function(v) { page.s.put("model", v) }
      }
    }

    SettingRow {
      objectName: "set-livePartials"
      width: parent.width
      stacked: true
      label: "Live transcript while you speak"
      hint: "Rough text shown as you talk, before Whisper returns."
      help: "It needs the Vosk model resident. On the Vosk wake engine that model is " +
            "already loaded, so it is free; on openWakeWord or sherpa-onnx it is an extra 114MB. " +
            "\"Auto\" shows it only when it is free.\n\n\"Accurate\" shows Vosk's rough text " +
            "first, then replaces each part with Whisper's at every pause you leave, so what " +
            "you see becomes what will be sent. It costs what \"On\" costs: Whisper is " +
            "already reading those parts as you talk."
      changed: page.s.changed("livePartials")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onReset: page.s.resetKey("livePartials")
      SegmentedChoice {
        options: [
          { value: "auto", label: "Auto", tooltip: "Only when it costs nothing" },
          { value: "on", label: "On", tooltip: "Always; costs 114MB on the other engines" },
          { value: "accurate", label: "Accurate", tooltip: "Vosk's text, replaced by Whisper's at every pause" },
          { value: "off", label: "Off" }
        ]
        value: page.s.setting("livePartials", "auto")
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onCommitted: function(v) { page.s.put("livePartials", v) }
      }
    }
  }
}
