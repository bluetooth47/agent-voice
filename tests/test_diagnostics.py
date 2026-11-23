"""About and Other settings (master plan M26): daemon/diagnostics.py,
daemon/keybinds.py, the local-server probe in endpoints.py, the install
stamp, and the CLI verbs that reach them.

What these hold:

- **diagnostics carry nothing personal**: a journal seeded with a transcript
  line, a reply line, a typed message, an error's text and an endpoint key
  -- with `logSpeech` on, so each is printed the way the daemon prints it
  then -- gives a report with none of them in it; home paths collapse to
  `~`; a setting is shown only by its kind;
- **the clipboard is fed on stdin**, never argv, and wl-copy's pipes cannot
  hold the call open;
- **the stamp is read tolerantly**: an older one-line VERSION gives "unknown
  branch" and the file's time; junk in it is left out, never shown;
- **the update check asks only the tracked remote**, names it, strips a
  password from its URL, and says so when there is none to ask;
- **a backend is "answered" only from a record**, never from being found;
- **keys** are read from bindings.lua and checked against what Hyprland
  loaded, read only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

import diagnostics
import endpoints
import keybinds
import paths
import stats

ROOT = Path(__file__).resolve().parent.parent
CANARY = "WALRUS-4471"
KEY = "sk-proj-a1b2c3d4e5f6a7b8c9d0"
HOME = str(Path.home())


def _entry(text, ident="python", t=1_700_000_000):
    return json.dumps({"MESSAGE": text, "SYSLOG_IDENTIFIER": ident,
                       "__REALTIME_TIMESTAMP": str(t * 1_000_000)})


#: What the daemon prints with logSpeech on, each carrying the canary or the
#: key, in the shapes wake_listen.py prints them (the speech_is_logged
#: branches), plus lines no rule knows.
SPEECH = [
    f"  \x1b[36mThe launch code is {CANARY}.\x1b[0m",                       # a reply sentence
    f"  \x1b[32m⌨ typed\x1b[0m  \x1b[1mtell Sora {CANARY}\x1b[0m",           # a typed message
    f"  \x1b[2m(progress) reading {CANARY}.txt\x1b[0m",                      # a progress line
    f"  \x1b[33magent error (auth): bad key {KEY}\x1b[0m",                   # an error's text
    f"  \x1b[2m(rejected \"{CANARY}\" — confidence 0.40 < 0.80)\x1b[0m",     # a rejected wake
    f"  \x1b[2m(second check: no wake — vosk only — whisper heard \"{CANARY}\", 700ms)\x1b[0m",
    "\r" + " " * 120 + f"\rheard: {CANARY}",                                 # a rewritten progress line
    f"ValueError: prompt was {CANARY}",                                      # an exception's message
    f"agent “Theo”: new chat\r{CANARY}",                                     # a good line, then text
    f"Theo: {CANARY}",
    f"interrupted {CANARY}",
]
STRUCTURAL = [
    "  \x1b[2magent 14.2s, first token 345ms\x1b[0m",
    "  6.0s audio, whisper 783ms, 0ms waited",
    "  [Bash]",
    "  ● wake Theo  go ahead (6.5s to start)",
    "  chime: heard (end of what was said)",
    "  prompt for “Theo”: rules 0 · defaults 0 · personality 0 · instructions 0 · roster 2 = 1109 chars",
    f"  project: {HOME}/Projects/x · trusted — never asks",
    "  agent error: auth  (details withheld — logSpeech is off)",
    "  (second check: theo by vosk + whisper, 696ms)",
    "  delegate 7b3f373dac139e6d: Theo → Sora (agent)",
    f'  File "{HOME}/.local/share/agentvoice/app/daemon/wake_listen.py", line 12, in answer',
    # A structural line that happens to carry something key-shaped: kept,
    # and masked by the last pass over the whole text.
    f"  project: {HOME}/{KEY} · trusted — never asks",
]


def test_the_report_carries_no_transcript_reply_or_key():
    journal = [_entry(t) for t in STRUCTURAL + SPEECH]
    journal.append(_entry("Started Agent Voice — wake word, transcription, spoken replies.", "systemd"))
    journal.append(_entry(f"agentvoice.service: Main process exited, code=exited, status=1/FAILURE", "systemd"))
    values = {"logSpeech": True, "endpointUrl": f"https://user:{KEY}@api.example.com/v1?key={KEY}",
              "projectDir": f"{HOME}/Projects/{CANARY}", "phrase": CANARY.lower(),
              "voiceAgents": [{"name": CANARY.lower(), "label": CANARY, "agent": "claude",
                               "instructions": CANARY, "projectDir": f"{HOME}/{CANARY}",
                               "endpointUrl": f"http://10.0.0.5:8080/{CANARY}"}],
              "agentModels": {"claude": "opus", "codex": f"x {CANARY}"},
              "model": f"../{CANARY}", "leadInMs": "abc", "maxUtteranceMs": "90000"}
    text = diagnostics.report(ROOT, ROOT / "nowhere", values=values, journal=journal)
    assert CANARY not in text and CANARY.lower() not in text
    assert KEY not in text and "sk-proj" not in text
    assert HOME + "/" not in text and "~/Projects/x" in text
    assert "~/.local/share/agentvoice/app/daemon/wake_listen.py" in text
    # Every structural line came through, and the speech was counted, not shown.
    for line in ("agent 14.2s, first token 345ms", "[Bash]", "● wake Theo  go ahead",
                 "chime: heard (end of what was said)", "(second check: theo by vosk + whisper, 696ms)",
                 "delegate 7b3f373dac139e6d: Theo → Sora (agent)", "Started Agent Voice",
                 "Main process exited", "agent “Theo”: new chat", "ValueError: (message left out)"):
        assert line in text, line
    assert "lines left out" in text
    # Settings by their kind: a URL as its host, other text as "set".
    assert 'endpointUrl = "https://api.example.com"' in text
    assert 'projectDir = "set"' in text and 'phrase = "set"' in text
    assert '"endpoint": "http://10.0.0.5:8080"' in text and '"agent": "claude"' in text
    assert 'agentModels = {"claude": "opus"}' in text
    assert 'model = "(other)"' in text and 'leadInMs = "(unreadable)"' in text
    assert 'maxUtteranceMs = "90000"' in text


def test_a_setting_the_daemon_does_not_know_is_not_read():
    lines = diagnostics.settings_summary({"logSpeech": True, "mySecret": CANARY},
                                         {"logSpeech": False})
    assert lines == ["logSpeech = true"]


@pytest.mark.parametrize("line", SPEECH)
def test_no_speech_line_passes_the_structural_filter(line):
    import re
    pieces = [p for p in re.split(r"[\r\n]", line) if p.strip()]
    kept = [diagnostics.structural(p) for p in pieces]
    assert not any(k and (CANARY in k or KEY in k) for k in kept), kept


def test_the_journal_is_read_as_json_and_a_blob_message_is_decoded():
    blob = list("agent 3.0s\r".encode()) + list(f"{CANARY}".encode())
    kept, left = diagnostics.journal_tail([json.dumps({"MESSAGE": blob, "SYSLOG_IDENTIFIER": "python"}),
                                           "not json", json.dumps([1, 2])])
    assert [k.split(" ", 1)[1] if k[0].isdigit() else k for k in kept] == ["agent 3.0s"]
    assert left == 3
    src = Path(diagnostics.__file__).read_text()
    assert '"-o", "json"' in src, "the default renderer hides a line with a carriage return"


def test_only_the_last_fifty_are_kept():
    kept, _ = diagnostics.journal_tail([_entry(f"agent {i}.0s") for i in range(80)])
    assert len(kept) == 50 and kept[-1].endswith("agent 79.0s")


def test_a_key_anywhere_is_masked_last():
    text = diagnostics.mask_keys(f"x {KEY} y https://a:b@h.example/p?token=zz Bearer abcdefghijklmnop")
    assert KEY not in text and "a:b@" not in text and "token=zz" not in text and "abcdefghijklmnop" not in text


def test_the_clipboard_is_fed_on_stdin(tmp_path, monkeypatch):
    """A fake wl-copy that records its argv and stdin, and forks a child
    holding stdout open (as the real one does): copy() must return anyway."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    out = tmp_path / "got"
    (bin_ / "wl-copy").write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" > {out}.argv\n"
        f"cat > {out}\n"
        "( sleep 30 ) &\n")
    (bin_ / "wl-copy").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}:{os.environ['PATH']}")
    t0 = time.monotonic()
    assert diagnostics.copy(f"hello {CANARY}\n")
    assert time.monotonic() - t0 < 10
    assert out.read_text() == f"hello {CANARY}\n"
    assert out.with_suffix(".argv").read_text().strip() == ""


def test_copy_reports_a_missing_clipboard(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert diagnostics.copy("x") is False


# --- the stamp ------------------------------------------------------------------------

def _stamp(tmp_path, text):
    app = tmp_path / "app"
    app.mkdir(exist_ok=True)
    (app / "VERSION").write_text(text)
    return app


def test_a_new_stamp_is_read_whole(tmp_path):
    app = _stamp(tmp_path, "0.2.0 (d4ad068)\ncommit=d4ad068d3bff0000000000000000000000000000\n"
                           "branch=detached\ninstalled=2026-11-23T13:09:18-07:00\n")
    s = diagnostics.read_stamp(app)
    assert s["version"] == "0.2.0" and s["commit"].startswith("d4ad068d3bff")
    assert s["branch"] == "detached" and s["installed"] == "2026-11-23T13:09:18-07:00"
    assert s["installed_from"] == "stamp"


def test_an_older_stamp_says_unknown_branch(tmp_path):
    app = _stamp(tmp_path, "0.2.0 (v0.2-3-gd4ad068-dirty)\n")
    s = diagnostics.read_stamp(app)
    assert s["commit"] == "d4ad068" and s["dirty"] and s["branch"] == ""
    assert s["installed_from"] == "file" and s["installed"][:4].isdigit()
    a = diagnostics.about(ROOT, app)
    assert "unknown branch" not in json.dumps(a)       # the page writes it, from ""
    page = (ROOT / "pages" / "AboutPage.qml").read_text()
    assert '"unknown branch"' in page


@pytest.mark.parametrize("junk", ["", "\n\n", "unversioned\n", f"0.2 (zz)\nbranch=$(rm -rf ~)\n"
                                  f"commit={CANARY}\ninstalled=yesterday\n", "\x00\xff" * 50])
def test_junk_in_a_stamp_is_left_out(tmp_path, junk):
    s = diagnostics.read_stamp(_stamp(tmp_path, junk))
    assert s["found"]
    assert s["branch"] in ("",) and CANARY not in json.dumps(s) and "rm -rf" not in json.dumps(s)


def test_no_stamp_is_not_installed(tmp_path):
    assert diagnostics.read_stamp(tmp_path)["found"] is False
    a = diagnostics.about(ROOT, tmp_path)
    assert a["match"] == "unknown" and "not installed" in a["note"]


def _run_stamp_block(tmp_path, root):
    """install.sh's stamp block, run by bash against `root`."""
    sh = (ROOT / "install.sh").read_text()
    start = sh.index("  {\n    printf '%s\\n' \"$NEW_BUILD\"")
    end = sh.index('  } > "$APP/VERSION"', start) + len('  } > "$APP/VERSION"')
    app = tmp_path / "app"
    app.mkdir()
    script = (f'set -euo pipefail\nROOT="{root}"\nAPP="{app}"\nNEW_BUILD="0.2.0 (abc1234)"\n'
              f'ROOT_IS_GIT=0\n[[ "$(git -C "$ROOT" rev-parse --show-toplevel 2>/dev/null || true)" == "$ROOT" ]] '
              f'&& ROOT_IS_GIT=1\n' + sh[start:end])
    subprocess.run(["bash", "-c", script], check=True)
    return app


def test_the_installer_writes_a_stamp_the_reader_reads(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git = ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(git[:3] + ["init", "-q", "-b", "phase-x"], check=True)
    (repo / "f").write_text("x")
    subprocess.run(git + ["add", "f"], check=True)
    subprocess.run(git + ["commit", "-qm", "x"], check=True)
    head = subprocess.run(git[:3] + ["rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    s = diagnostics.read_stamp(_run_stamp_block(tmp_path, repo))
    assert s["build"] == "0.2.0 (abc1234)" and s["commit"] == head
    assert s["branch"] == "phase-x" and s["installed_from"] == "stamp"
    # Line one is unchanged, which is all build_id and PREV_BUILD read.
    assert paths.build_id(tmp_path / "app") == "0.2.0 (abc1234)"


def test_a_stamp_from_a_detached_checkout_says_detached(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git = ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(git[:3] + ["init", "-q"], check=True)
    (repo / "f").write_text("x")
    subprocess.run(git + ["add", "f"], check=True)
    subprocess.run(git + ["commit", "-qm", "x"], check=True)
    subprocess.run(git[:3] + ["checkout", "-q", "--detach"], check=True)
    assert diagnostics.read_stamp(_run_stamp_block(tmp_path, repo))["branch"] == "detached"


def test_a_folder_that_is_not_git_writes_only_the_first_line_and_the_time(tmp_path, monkeypatch):
    folder = tmp_path / "plain"
    folder.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    lines = (_run_stamp_block(tmp_path, folder) / "VERSION").read_text().splitlines()
    assert len(lines) == 2
    assert lines[0] == "0.2.0 (abc1234)" and lines[1].startswith("installed=")


# --- two builds --------------------------------------------------------------------------

def _repo(tmp_path):
    repo = tmp_path / "plugin"
    repo.mkdir()
    git = ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(git[:3] + ["init", "-q", "-b", "main"], check=True)
    (repo / "daemon").mkdir()
    (repo / "daemon" / "x.py").write_text("1")
    (repo / "manifest.json").write_text('{"version": "0.2.0"}')
    (repo / "Panel.qml").write_text("1")
    subprocess.run(git + ["add", "."], check=True)
    subprocess.run(git + ["commit", "-qm", "a"], check=True)

    def commit(path, text):
        (repo / path).write_text(text)
        subprocess.run(git + ["commit", "-qam", path], check=True)
        return subprocess.run(git[:3] + ["rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    first = subprocess.run(git[:3] + ["rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    return repo, git, first, commit


def test_two_builds_with_the_same_daemon_code_are_not_a_fault(tmp_path):
    repo, git, first, commit = _repo(tmp_path)
    commit("Panel.qml", "2")
    app = _stamp(tmp_path, f"0.2.0 ({first[:7]})\ncommit={first}\nbranch=main\n")
    a = diagnostics.about(repo, app)
    assert a["match"] == "same-code" and a["plugin"]["branch"] == "main"
    commit("daemon/x.py", "2")
    assert diagnostics.about(repo, app)["match"] == "differs"
    # A commit the plugin's repository does not have: cannot tell.
    (tmp_path / "b").mkdir()
    app2 = _stamp(tmp_path / "b", "0.2.0 (0000000)\n")
    assert diagnostics.about(repo, app2)["match"] == "unknown"


def test_a_plugin_folder_inside_someone_elses_repo_is_not_its_checkout(tmp_path):
    repo, git, first, commit = _repo(tmp_path)
    inner = repo / "sub"
    inner.mkdir()
    (inner / "manifest.json").write_text('{"version": "9.9"}')
    info = diagnostics.plugin_info(inner)
    assert info == {"version": "9.9", "commit": "", "branch": "", "git": False}


# --- updates -------------------------------------------------------------------------------

def test_no_remote_asks_nobody_and_says_so(tmp_path):
    repo, *_ = _repo(tmp_path)
    u = diagnostics.update_check(repo)
    assert u["status"] == "no-remote" and u["remote"] == "" and "nobody to ask" in u["message"]


def test_the_tracked_remote_is_asked_and_named(tmp_path):
    repo, git, first, commit = _repo(tmp_path)
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(repo), str(bare)], check=True)
    subprocess.run(git[:3] + ["remote", "add", "fork", str(bare)], check=True)
    subprocess.run(git[:3] + ["fetch", "-q", "fork"], check=True)
    subprocess.run(git[:3] + ["branch", "-q", "-u", "fork/main"], check=True)
    u = diagnostics.update_check(repo)
    assert u["status"] == "current" and u["remote"] == "fork" and u["url"] == str(bare)
    # The remote moves on: newer.
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(bare), str(other)], check=True)
    (other / "Panel.qml").write_text("3")
    og = ["git", "-C", str(other), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(og + ["commit", "-qam", "3"], check=True)
    subprocess.run(og + ["push", "-q", "origin", "main"], check=True)
    u = diagnostics.update_check(repo)
    assert u["status"] == "newer" and u["remote_commit"] != first
    # This copy moves past it: ahead.
    subprocess.run(git[:3] + ["pull", "-q", "--ff-only", "fork", "main"], check=True)
    commit("Panel.qml", "4")
    assert diagnostics.update_check(repo)["status"] == "ahead"


def test_a_remote_that_does_not_answer_fails_and_says_which(tmp_path):
    repo, git, *_ = _repo(tmp_path)
    subprocess.run(git[:3] + ["remote", "add", "origin", str(tmp_path / "gone.git")], check=True)
    u = diagnostics.update_check(repo)
    assert u["status"] == "failed" and u["remote"] == "origin" and "origin" in u["message"]


@pytest.mark.parametrize("url, shown", [
    ("https://user:pw@github.com/a/b.git", "https://github.com/a/b.git"),
    ("https://github.com/a/b", "https://github.com/a/b"),
    ("git@github.com:a/b.git", "github.com:a/b.git"),
    ("ssh://git@host/x", "ssh://host/x"),
])
def test_a_remote_url_is_shown_without_a_password(url, shown):
    assert diagnostics.shown_url(url) == shown


def test_git_is_run_so_that_it_cannot_prompt_or_run_a_repos_command():
    src = Path(diagnostics.__file__).read_text()
    for need in ('"core.fsmonitor="', '"protocol.ext.allow=never"', '"--no-optional-locks"',
                 '"GIT_TERMINAL_PROMPT": "0"', "stdin=subprocess.DEVNULL"):
        assert need in src, need


# --- who it talks to ----------------------------------------------------------------------

class _Cfg:
    def __init__(self, values, keep=True):
        self.v = values
        self.keep = keep

    def keep_stats(self):
        return self.keep

    def get_str(self, key):
        return str(self.v.get(key, ""))

    def main_endpoint(self):
        return self.v.get("_endpoint")

    def main_label(self, phrase=""):
        return "Theo"

    def all_agents(self):
        return self.v.get("_agents", [])


def test_found_is_installed_and_only_a_record_is_answered():
    cfg = _Cfg({"mainProgram": "claude", "engine": "sherpa", "model": "base.en",
                "_agents": [{"agent": "codex", "label": "Hazel"}]})
    found = {"claude", "codex", "agy"}
    b = diagnostics.backends(cfg, {"claude": 3}, which=lambda x: x in found and "/usr/bin/" + x)
    by = {r["id"]: r for r in b["backends"]}
    assert by["claude"]["status"] == "answered" and by["claude"]["answered"] == 3
    assert by["codex"]["status"] == "installed" and by["codex"]["used_by"] == ["Hazel"]
    assert by["gemini"]["status"] == "not found"
    assert all(r["where"] == "cloud" for r in b["backends"])
    assert [x["how"] for x in b["local"]] == ["sherpa-onnx", "Whisper base.en", "Piper"]
    # Stats off: nothing is claimed either way.
    b = diagnostics.backends(_Cfg({}, keep=False), which=lambda x: "/usr/bin/" + x)
    assert b["stats"] is False and all(r["answered"] is None for r in b["backends"])
    assert {r["status"] for r in b["backends"]} == {"installed"}


def test_an_endpoint_is_local_or_cloud_by_its_host():
    cfg = _Cfg({"_endpoint": {"url": "http://127.0.0.1:11434/v1"},
                "_agents": [{"agent": "endpoint", "label": "Remote",
                             "endpoint": {"url": "https://api.example.com/v1/x"}}]})
    rows = [r for r in diagnostics.backends(cfg, {}, which=lambda x: None)["backends"]
            if r["id"] == "endpoint"]
    assert [(r["label"], r["where"]) for r in rows] == [
        ("Endpoint http://127.0.0.1:11434", "local"), ("Endpoint https://api.example.com", "cloud")]
    assert all("/v1" not in r["label"] for r in rows)


def test_the_page_never_calls_a_found_program_connected():
    page = (ROOT / "pages" / "AboutPage.qml").read_text()
    assert "connected" not in page.lower().replace("not the same as an agent using it", "")
    assert "does not mean it is signed in" in page


# --- the local servers ----------------------------------------------------------------------

class _Models(BaseHTTPRequestHandler):
    seen: list = []

    def do_GET(self):
        _Models.seen.append((self.path, dict(self.headers)))
        body = json.dumps({"data": [{"id": "a"}, {"id": "b"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def test_the_probe_reads_a_local_server_and_sends_no_key(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), _Models)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        # A proxy in the environment must not be used for loopback.
        monkeypatch.setenv("http_proxy", "http://127.0.0.1:9/")
        free = HTTPServer(("127.0.0.1", 0), _Models)
        free_port = free.server_address[1]
        free.server_close()
        got = endpoints.probe_local(servers=(
            {"id": "ollama", "label": "Ollama", "port": srv.server_address[1]},
            {"id": "llamacpp", "label": "llama.cpp server", "port": free_port}))
    finally:
        srv.shutdown()
    assert got[0]["status"] == "answering" and got[0]["models"] == 2
    assert got[1]["status"] == "nothing"
    path, headers = _Models.seen[-1]
    assert path == "/v1/models" and "Authorization" not in headers


def test_the_probe_asks_loopback_only():
    assert [(s["id"], s["port"]) for s in endpoints.PROBED_SERVERS] == [("ollama", 11434), ("llamacpp", 8080)]
    import inspect
    assert 'host: str = "127.0.0.1"' in inspect.getsource(endpoints.probe_local)


# --- the keys ---------------------------------------------------------------------------------

LUA = '''
o.bind("SUPER + RETURN", "Terminal", "uwsm-app -- xdg-terminal-exec")
-- >>> agentvoice keybinds (added by install.sh, removed by --uninstall)
o.bind("F8", "Talk to the agent (push-to-talk)", "agentvoice talk")
o.bind("F8", "End the turn (push-to-talk)", "agentvoice talk-end", { release = true })
o.bind("SUPER + CTRL + SPACE", "Stop the agent talking", "agentvoice interrupt")
o.bind("SUPER + ALT + SPACE", "Release or re-engage the mic", "agentvoice mic")
-- <<< agentvoice keybinds
o.bind("SUPER + SHIFT + M", "Mute it", "agentvoice mic --quiet")
'''


def _h(mods, key, desc, release=False):
    return {"modmask": mods, "key": key, "description": desc, "has_description": True,
            "dispatcher": "__lua", "arg": "12", "release": release}


def test_the_keys_are_read_from_the_file_and_checked_against_hyprland():
    loaded = [_h(0, "F8", "Talk to the agent (push-to-talk)"),
              _h(0, "F8", "End the turn (push-to-talk)", True),
              _h(68, "SPACE", "Stop the agent talking"),
              {"modmask": 64, "key": "X", "dispatcher": "exec", "arg": "agentvoice toggle",
               "has_description": False, "release": False}]
    rows = keybinds.merge(keybinds.from_file(LUA), loaded, True)
    by = {r["keys"]: r for r in rows}
    assert set(by) == {"Hold F8", "Super+Ctrl+Space", "Super+Alt+Space", "Super+Shift+M", "Super+X"}
    assert by["Hold F8"]["loaded"] is True and "release when done" in by["Hold F8"]["what"]
    assert by["Super+Ctrl+Space"]["loaded"] is True
    assert by["Super+Alt+Space"]["loaded"] is False          # in the file, not loaded
    assert by["Super+Shift+M"]["what"] == keybinds.VERBS["mic"]
    assert by["Super+X"]["source"] == "hyprland" and by["Super+X"]["what"] == keybinds.VERBS["toggle"]
    # Hyprland not asked: nothing claimed either way.
    assert {r["loaded"] for r in keybinds.merge(keybinds.from_file(LUA), None, False)} == {None}


def test_a_key_view_survives_no_file_and_no_hyprland(tmp_path):
    v = keybinds.view(tmp_path / "nope.lua", hypr=lambda: None)
    assert v == {**v, "file_found": False, "hyprland": False, "rows": []}


def test_a_line_that_is_not_a_plain_binding_is_left_out():
    rows = keybinds.from_file('o.bind(key, "x", "agentvoice talk")\n'
                              'o.bind("F9", "x", "notagentvoice talk")\n'
                              'o.bind("F10", "x", "agentvoice")\n')
    assert [r["key"] for r in rows] == ["F10"]


@pytest.mark.parametrize("mask, key, shown", [(0, "F8", "F8"), (68, "SPACE", "Super+Ctrl+Space"),
                                             (9, "x", "Alt+Shift+X"), (64, "RETURN", "Super+Return")])
def test_keys_are_written_the_way_a_person_writes_them(mask, key, shown):
    assert keybinds.pretty(mask, key) == shown


# --- the CLI ----------------------------------------------------------------------------------

def test_bin_agentvoice_has_the_verbs():
    src = (ROOT / "bin/agentvoice").read_text()
    block = src[src.index("  about|diagnostics)"):]
    assert 'exec "$PY" "$REPO/daemon/diagnostics.py" "$sub" "$@"' in block[:2000]
    keys = src[src.index("  keys)"):]
    assert 'exec "$PY" "$REPO/daemon/keybinds.py" "$@"' in keys[:800]
    assert "about|diagnostics|keys" in src


def test_the_cli_runs_and_nothing_it_prints_is_personal(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(diagnostics, "_journal_json", lambda n=0: [_entry(SPEECH[0])])
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "data")
    assert diagnostics.main(["report", "--plugin", str(ROOT)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Agent Voice diagnostics") and CANARY not in out
    assert diagnostics.main(["about", "--json", "--plugin", str(ROOT)]) == 0
    a = json.loads(capsys.readouterr().out)
    assert a["version"] and a["daemon"]["found"] is False
    assert diagnostics.main([]) == 2 and diagnostics.main(["nope"]) == 2


def test_the_installer_asks_git_only_about_its_own_checkout():
    """A copy unpacked inside another repository is not stamped with that
    repository's commit, on line one or after it."""
    sh = (ROOT / "install.sh").read_text()
    assert '[[ "$(git -C "$ROOT" rev-parse --show-toplevel 2>/dev/null || true)" == "$ROOT" ]] && ROOT_IS_GIT=1' in sh
    assert 'if [[ $ROOT_IS_GIT == 1 ]] && GIT_DESC=' in sh
    assert 'if [[ $ROOT_IS_GIT == 1 ]] && STAMP_COMMIT=' in sh


def test_a_folder_inside_another_repo_is_stamped_with_no_commit(tmp_path):
    repo, *_ = _repo(tmp_path)
    inner = repo / "unpacked"
    inner.mkdir()
    lines = (_run_stamp_block(tmp_path, inner) / "VERSION").read_text().splitlines()
    assert len(lines) == 2 and lines[1].startswith("installed=")


def test_an_install_from_a_dirty_tree_says_so(tmp_path):
    repo, git, first, commit = _repo(tmp_path)
    app = _stamp(tmp_path, f"0.2.0 ({first[:7]}-dirty)\ncommit={first}\n")
    a = diagnostics.about(repo, app)
    assert a["match"] == "same" and "uncommitted changes" in a["note"]


def test_a_callers_git_dir_is_not_followed(tmp_path, monkeypatch):
    repo, *_ = _repo(tmp_path)
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "elsewhere.git"))
    assert diagnostics.plugin_info(repo)["git"] is True
