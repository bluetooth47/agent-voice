import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import ".."

// One OpenAI-compatible endpoint: address, model, key, timeout, turns
// remembered, and a connection test (plan 7b). Used by the main agent's card
// and by every extra agent whose program is "endpoint".
//
// It writes nothing itself. Every change is an `edited(key, value)` with
// one of the setting names below, and the page that owns the setting writes
// it -- the main card with s.put, an extra card into its voiceAgents entry --
// so each key is still changed on exactly one page.
//
//   EndpointEditor {
//     url: ...; model: ...; isAgent: ...; timeoutS: ...; historyTurns: ...
//     onEdited: function(key, value) { ... }   // endpointUrl, endpointModel,
//   }                                          // endpointIsAgent,
//                                              // endpointTimeoutS,
//                                              // endpointHistoryTurns
Column {
  id: ed

  property string url: ""
  property string model: ""
  property bool isAgent: false
  property int timeoutS: 0
  property int historyTurns: 8

  property color foreground: Commons.Color.foreground
  property color urgent: Commons.Color.urgent
  property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  signal edited(string key, var value)

  spacing: Style.space(10)

  // Shipped presets: only those a real turn has gone through (FINDINGS §14).
  // Kept in step with endpoints.PRESETS by test_endpoints.
  readonly property var presets: [
    { id: "ollama", label: "Ollama", url: "http://localhost:11434/v1" },
    { id: "openai", label: "OpenAI", url: "https://api.openai.com/v1" },
    { id: "groq", label: "Groq", url: "https://api.groq.com/openai/v1" },
    { id: "xai", label: "xAI", url: "https://api.x.ai/v1" }
  ]
  function presetFor(u) {
    for (var i = 0; i < presets.length; i++)
      if (presets[i].url === u) return presets[i].id
    return ""
  }

  // What the daemon will actually use, from endpoints.py's own clean_url,
  // so the page and the daemon cannot disagree about a pasted URL.
  property string cleaned: ""
  // Whether `clean` answered (exit 0: an address, 1: not one). Anything else
  // -- an older agentvoice with no `endpoint` command -- says nothing, rather
  // than calling a good address bad.
  property bool cleanKnown: false
  property var models: []
  property string modelsError: ""
  property string keyShown: ""
  property string keyPending: ""
  property var result: null
  property bool customModel: false
  property string keyDraft: ""
  // Flipped to empty the key field once its key has been handed over.
  property int keyCleared: 0

  function saveKey() {
    if (keyDraft.trim() === "" || url.trim() === "") return
    keyPending = keyDraft.trim()
    keyDraft = ""
    keyCleared++
    run(keySetProc, ["key", "set", url])
  }

  function run(proc, args) {
    if (proc.running) return
    proc.command = ["agentvoice", "endpoint"].concat(args)
    proc.running = true
  }
  function refresh() {
    cleanKnown = false
    if (url.trim() === "") { cleaned = ""; keyShown = ""; return }
    run(cleanProc, ["clean", url])
    run(keyShowProc, ["key", "show", url])
  }
  onUrlChanged: { models = []; modelsError = ""; result = null; refresh() }
  Component.onCompleted: refresh()

  Process {
    id: cleanProc
    stdout: StdioCollector { onStreamFinished: ed.cleaned = String(text).trim() }
    onExited: function(exitCode, exitStatus) { ed.cleanKnown = exitCode === 0 || exitCode === 1 }
  }
  Process {
    id: keyShowProc
    stdout: StdioCollector { onStreamFinished: ed.keyShown = String(text).trim() }
  }
  Process {
    id: modelsProc
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var d = JSON.parse(String(text))
          ed.models = d.models || []
          ed.modelsError = d.error || (ed.models.length ? "" : "it lists no models")
        } catch (e) { ed.models = []; ed.modelsError = "could not read the list" }
      }
    }
  }
  Process {
    id: testProc
    stdout: StdioCollector {
      onStreamFinished: {
        try { ed.result = JSON.parse(String(text)) }
        catch (e) { ed.result = { ok: false, error: "the test did not finish" } }
      }
    }
  }
  // The key goes over stdin, never argv: /proc/<pid>/cmdline is readable by
  // every account on the machine.
  Process {
    id: keySetProc
    stdinEnabled: true
    onStarted: { write(ed.keyPending + "\n"); ed.keyPending = "" }
    stdout: StdioCollector { onStreamFinished: ed.keyShown = String(text).trim() }
  }

  SettingRow {
    width: parent.width
    stacked: true
    label: "Preset"
    hint: "Fills in the address. Anything else that speaks the same dialect (LM Studio, llama.cpp, vLLM, OpenRouter, Hermes) works by typing its address."
    foreground: ed.foreground
    fontFamily: ed.fontFamily
    SegmentedChoice {
      options: [{ value: "", label: "Custom" }].concat(ed.presets.map(function(p) {
        return { value: p.id, label: p.label } }))
      value: ed.presetFor(ed.cleaned || ed.url)
      foreground: ed.foreground
      fontFamily: ed.fontFamily
      onCommitted: function(v) {
        for (var i = 0; i < ed.presets.length; i++)
          if (ed.presets[i].id === v) ed.edited("endpointUrl", ed.presets[i].url)
      }
    }
  }

  SettingRow {
    width: parent.width
    stacked: true
    label: "Address"
    foreground: ed.foreground
    fontFamily: ed.fontFamily
    Column {
      spacing: Style.space(4)
      TextField {
        width: parent.width
        text: ed.url
        placeholderText: "localhost:11434, or https://api.example.com/v1"
        foreground: ed.foreground
        font.family: ed.fontFamily
        onEditingFinished: if (text.trim() !== ed.url) ed.edited("endpointUrl", text.trim())
      }
      Text {
        width: parent.width
        visible: ed.url.trim() !== "" && ed.cleanKnown
        wrapMode: Text.WrapAnywhere
        textFormat: Text.PlainText
        text: ed.cleaned !== "" ? "Will use " + ed.cleaned
                                : "That does not look like an address."
        color: ed.cleaned !== "" ? ed.dim : ed.urgent
        font.family: ed.fontFamily
        font.pixelSize: Style.font.caption
      }
    }
  }

  SettingRow {
    width: parent.width
    stacked: true
    label: "Model"
    foreground: ed.foreground
    fontFamily: ed.fontFamily
    Column {
      spacing: Style.space(6)
      Row {
        width: parent.width
        spacing: Style.space(8)
        Dropdown {
          width: parent.width - listButton.width - parent.spacing
          visible: ed.models.length > 0
          showLabel: false
          fontFamily: ed.fontFamily
          foreground: ed.foreground
          options: {
            var out = []
            var known = ed.model === ""
            for (var i = 0; i < ed.models.length; i++) {
              out.push({ label: ed.models[i], value: ed.models[i] })
              if (ed.models[i] === ed.model) known = true
            }
            if (!known) out.push({ label: ed.model + "  (typed)", value: ed.model })
            out.push({ label: "Other…", value: "__other__" })
            return out
          }
          value: ed.customModel ? "__other__" : ed.model
          onChanged: function(v) {
            if (v === "__other__") { ed.customModel = true; return }
            ed.customModel = false
            if (v !== ed.model) ed.edited("endpointModel", v)
          }
        }
        TextField {
          width: parent.width - listButton.width - parent.spacing
          visible: ed.models.length === 0
          text: ed.model
          placeholderText: "model name, e.g. llama3.2"
          foreground: ed.foreground
          font.family: ed.fontFamily
          onEditingFinished: if (text.trim() !== ed.model) ed.edited("endpointModel", text.trim())
        }
        Button {
          id: listButton
          text: modelsProc.running ? "Asking…" : "List models"
          bordered: true
          foreground: ed.foreground
          fontFamily: ed.fontFamily
          onClicked: if (ed.url.trim() !== "") ed.run(modelsProc, ["models", ed.url])
        }
      }
      TextField {
        width: parent.width
        visible: ed.customModel && ed.models.length > 0
        text: ed.model
        placeholderText: "type a model name"
        foreground: ed.foreground
        font.family: ed.fontFamily
        onEditingFinished: if (text.trim() !== ed.model) ed.edited("endpointModel", text.trim())
      }
      Text {
        width: parent.width
        visible: ed.modelsError !== ""
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: ed.modelsError
        color: ed.urgent
        font.family: ed.fontFamily
        font.pixelSize: Style.font.caption
      }
    }
  }

  SettingRow {
    width: parent.width
    stacked: true
    label: "API key"
    hint: ed.keyShown !== "" ? "Saved: " + ed.keyShown + ". Paste another to replace it, or clear it."
                             : "Ollama and LM Studio need none."
    help: "Saved for this host only, in ~/.config/agentvoice/endpoint-keys.json, " +
          "readable by you alone. Never in the settings file, which is the desktop's " +
          "config and gets copied around. A key in the login keyring " +
          "(secret-tool store --label=agentvoice service agentvoice endpoint HOST) " +
          "is used first.\n\nA key is never sent over plain http to a public host."
    foreground: ed.foreground
    fontFamily: ed.fontFamily
    Row {
      width: parent.width
      spacing: Style.space(8)
      TextField {
        width: parent.width - saveKey.width - clearKey.width - parent.spacing * 2
        password: true
        placeholderText: ed.keyShown !== "" ? ed.keyShown : "paste a key"
        foreground: ed.foreground
        font.family: ed.fontFamily
        // The draft lives on ed, and is emptied from there once saved: read
        // and cleared only from inside this field, where `text` is its own.
        onTextChanged: ed.keyDraft = text
        onAccepted: ed.saveKey()
        Connections {
          target: ed
          function onKeyClearedChanged() { parent.text = "" }
        }
      }
      Button {
        id: saveKey
        text: "Save"
        bordered: true
        foreground: ed.foreground
        fontFamily: ed.fontFamily
        onClicked: ed.saveKey()
      }
      Button {
        id: clearKey
        visible: ed.keyShown !== ""
        text: "Clear"
        bordered: true
        foreground: ed.foreground
        fontFamily: ed.fontFamily
        onClicked: ed.run(keySetProc, ["key", "clear", ed.url])
      }
    }
  }

  ToggleRow {
    width: parent.width
    label: "This endpoint is an agent"
    hint: "It can run commands or change files on its own machine, as Hermes can."
    help: "agentvoice cannot tell from the URL, so it claims nothing about the far " +
          "end unless you say — and gives it longer to answer, because an agent " +
          "goes quiet while it runs tools.\n\nagentvoice offers an endpoint no " +
          "tools and gates nothing, so the permission level does not reach it."
    checked: ed.isAgent
    foreground: ed.foreground
    fontFamily: ed.fontFamily
    onToggled: ed.edited("endpointIsAgent", !checked)
  }

  KnobRow {
    width: parent.width
    foreground: ed.foreground; fontFamily: ed.fontFamily
    label: "Gives up after"
    description: ed.timeoutS > 0 ? "Seconds with nothing from it before the turn ends."
                                 : "Default: 120s, or 300s for an agent. A slow local model may need more."
    value: ed.timeoutS
    minimum: 0; maximum: 600; stepSize: 10
    unit: " s"
    onCommitted: function(v) { ed.edited("endpointTimeoutS", Math.round(v)) }
  }

  KnobRow {
    width: parent.width
    foreground: ed.foreground; fontFamily: ed.fontFamily
    label: "Turns remembered"
    description: "Earlier turns sent again with each request. Each one is re-read, and re-billed on a paid service."
    value: ed.historyTurns
    minimum: 0; maximum: 50; stepSize: 1
    onCommitted: function(v) { ed.edited("endpointHistoryTurns", Math.round(v)) }
  }

  Row {
    width: parent.width
    spacing: Style.space(10)
    Button {
      id: testButton
      text: testProc.running ? "Testing…" : "Test connection"
      bordered: true
      foreground: ed.foreground
      fontFamily: ed.fontFamily
      onClicked: {
        ed.result = null
        if (ed.url.trim() !== "" && ed.model.trim() !== "")
          ed.run(testProc, ["test", ed.url, ed.model])
        else ed.result = { ok: false, error: "an address and a model first" }
      }
    }
    Text {
      anchors.verticalCenter: parent.verticalCenter
      width: parent.width - testButton.width - parent.spacing
      visible: ed.result !== null
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: ed.result === null ? ""
            : ed.result.ok
              ? "✓ Answered: first word in " + ed.result.first_word_s + "s" +
                (ed.result.key === "sent" ? " · key sent" : " · no key sent")
              : "✗ " + (ed.result.error || "no answer")
      color: ed.result !== null && ed.result.ok ? ed.foreground : ed.urgent
      font.family: ed.fontFamily
      font.pixelSize: Style.font.caption
    }
  }
}
