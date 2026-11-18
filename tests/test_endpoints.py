"""Plan 7b: endpoints per agent, forgiving URLs, keys, the connection test,
the model list, and thinking text that is never spoken.

The servers here are real HTTP servers on localhost, as in test_endpoint.py:
the wire format is public, so it is tested on the wire.
"""
from __future__ import annotations

import importlib
import json
import os
import re
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

import endpoints
from endpoints import ThinkFilter, clean_url, masked, split_delta, strip_thinking

ROOT = Path(__file__).resolve().parent.parent


# --- forgiving URLs -----------------------------------------------------------

@pytest.mark.parametrize("typed, used", [
    ("localhost:11434", "http://localhost:11434/v1"),
    ("http://localhost:11434", "http://localhost:11434/v1"),
    ("http://localhost:11434/", "http://localhost:11434/v1"),
    ("http://localhost:11434/v1/", "http://localhost:11434/v1"),
    ("http://localhost:1234/v1/chat/completions", "http://localhost:1234/v1"),
    ("192.168.1.20:8080", "http://192.168.1.20:8080/v1"),
    ("mac-mini:11434", "http://mac-mini:11434/v1"),
    ("mac-mini.local:11434/v1", "http://mac-mini.local:11434/v1"),
    ("api.openai.com", "https://api.openai.com/v1"),
    ("api.openai.com/v1/chat/completions", "https://api.openai.com/v1"),
    ("https://api.groq.com/openai/v1/", "https://api.groq.com/openai/v1"),
    ("https://openrouter.ai/api/v1/models", "https://openrouter.ai/api/v1"),
    ("  https://api.x.ai/v1  ", "https://api.x.ai/v1"),
    ("HTTPS://API.X.AI/v1", "https://api.x.ai/v1"),
    ("http://[::1]:8000", "http://[::1]:8000/v1"),
])
def test_a_typed_url_is_tidied(typed, used):
    assert clean_url(typed) == used


@pytest.mark.parametrize("typed", [
    "", "   ", "not a url", "ftp://host/v1", "http://", "http://user:sk-1@host/v1",
    "http://host:notaport/v1", "file:///etc/passwd",
])
def test_what_is_not_a_url_is_refused(typed):
    assert clean_url(typed) == ""


def test_a_public_host_without_a_scheme_gets_https():
    # Plain http to a public host would carry the key in the clear.
    assert clean_url("api.example.com").startswith("https://")


# --- thinking is never spoken -------------------------------------------------

def test_a_whole_think_block_is_taken_out():
    f = ThinkFilter()
    said, thought = f.feed("<think>plan the answer</think>Hello there.")
    assert said == "Hello there."
    assert thought == "plan the answer"


def test_a_tag_split_across_two_pieces_is_still_caught():
    f = ThinkFilter()
    out = [f.feed(p) for p in ("<thi", "nk>secret plan</th", "ink>Hi.")]
    said = "".join(s for s, _ in out) + f.flush()[0]
    thought = "".join(t for _, t in out)
    assert said == "Hi."
    assert thought == "secret plan"


@pytest.mark.parametrize("pieces", [
    list("<think>abc</think>Answer."),           # one character at a time
    ["<", "think", ">", "abc", "<", "/", "think", ">", "Answer."],
    ["<think>a", "bc</think", ">Answer."],
])
def test_any_split_gives_the_same_answer(pieces):
    f = ThinkFilter()
    said = "".join(f.feed(p)[0] for p in pieces) + f.flush()[0]
    assert said == "Answer."


def test_unclosed_thinking_is_not_an_answer():
    f = ThinkFilter()
    said, thought = f.feed("<think>still going and going")
    tail, more = f.flush()
    assert said == tail == ""
    assert (thought + more) == "still going and going"


def test_a_lone_angle_bracket_is_kept():
    f = ThinkFilter()
    said = f.feed("3 < 4 and 5 >")[0] + f.flush()[0]
    assert said == "3 < 4 and 5 >"


def test_held_text_that_never_becomes_a_tag_comes_out_at_the_end():
    f = ThinkFilter()
    assert f.feed("Hello <thi")[0] == "Hello "
    assert f.flush() == ("<thi", "")


@pytest.mark.parametrize("open_, close", [("<thinking>", "</thinking>"),
                                          ("<reasoning>", "</reasoning>")])
def test_other_spellings_of_the_block(open_, close):
    assert strip_thinking(f"{open_}x{close}Done.") == "Done."


@pytest.mark.parametrize("field", ["reasoning_content", "reasoning"])
def test_a_separate_reasoning_field_is_thinking(field):
    f = ThinkFilter()
    event = {"choices": [{"delta": {field: "hmm", "content": "Yes."}}]}
    assert split_delta(event, f) == ("Yes.", "hmm")


def test_malformed_events_give_nothing():
    f = ThinkFilter()
    for event in ({}, {"choices": []}, {"choices": ["x"]},
                  {"choices": [{"delta": "x"}]}, None):
        assert split_delta(event, f) == ("", "")


# --- keys ---------------------------------------------------------------------

@pytest.fixture
def keys(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    for var in ("AGENTVOICE_ENDPOINT_KEY", "OPENAI_API_KEY", "XAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    import paths
    importlib.reload(paths)
    monkeypatch.setattr(paths, "_keyring", lambda **kw: "")
    monkeypatch.setattr(paths, "_keyring_has_hosts", lambda: False)
    yield paths
    importlib.reload(paths)


def test_a_saved_key_is_owner_only_and_found_by_host(keys):
    endpoints.save_key("api.groq.com", "gsk_abcdefgh1234")
    path = keys.CONFIG_DIR / "endpoint-keys.json"
    assert path.stat().st_mode & 0o777 == 0o600
    assert keys.endpoint_key("api.groq.com") == "gsk_abcdefgh1234"


def test_another_hosts_key_is_never_handed_over(keys):
    endpoints.save_key("api.groq.com", "gsk_abcdefgh1234")
    # A key filed for one host means a miss on another is no key, not the
    # generic fallback.
    (keys.CONFIG_DIR / "endpoint.key").write_text("sk-generic")
    (keys.CONFIG_DIR / "endpoint.key").chmod(0o600)
    assert keys.endpoint_key("api.x.ai") == ""


def test_a_key_file_others_can_read_is_ignored(keys):
    endpoints.save_key("api.groq.com", "gsk_abcdefgh1234")
    (keys.CONFIG_DIR / "endpoint-keys.json").chmod(0o644)
    assert keys.endpoint_key("api.groq.com") == ""


def test_clearing_a_key_removes_it(keys):
    endpoints.save_key("api.groq.com", "gsk_abcdefgh1234")
    endpoints.save_key("api.groq.com", "")
    assert keys.endpoint_key("api.groq.com") == ""


def test_a_key_with_spaces_is_refused(keys):
    with pytest.raises(ValueError):
        endpoints.save_key("api.groq.com", "not a key")


@pytest.mark.parametrize("key, shown", [
    ("", ""), ("abc", "•••"), ("sk-abcdefghijkl1234", "sk-…1234"),
    ("gsk_abcdefghijkl9876", "gsk…9876"), ("0123456789abcdef", "…cdef"),
])
def test_a_key_is_shown_masked(key, shown):
    assert masked(key) == shown
    if len(key) > 8:
        assert key[4:-4] not in masked(key)


def test_the_cli_takes_the_key_on_stdin_not_argv(tmp_path):
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path)}
    out = subprocess.run([sys.executable, str(ROOT / "daemon/endpoints.py"),
                          "key", "set", "https://api.groq.com/openai/v1"],
                         input="gsk_secretsecret5678\n", text=True,
                         capture_output=True, env=env, timeout=20)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "gsk…5678"
    saved = json.loads((tmp_path / "agentvoice/endpoint-keys.json").read_text())
    assert saved == {"api.groq.com": "gsk_secretsecret5678"}


def test_a_key_never_reaches_the_settings(cfg_factory, keys):
    endpoints.save_key("localhost:9", "sk-secretsecret")
    cfg = cfg_factory(voiceAgents=[{
        "name": "nova", "agent": "endpoint", "endpointUrl": "localhost:9",
        "endpointModel": "m"}])
    assert "sk-secretsecret" not in json.dumps(cfg.agents())
    assert "sk-secretsecret" not in json.dumps(cfg.main_endpoint())


# --- the connection test and the model list -----------------------------------

class Fake(BaseHTTPRequestHandler):
    mode = {"chat": "ok", "models": "ok"}

    def log_message(self, *a):
        pass

    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        m = self.mode["models"]
        if self.path == "/v1/models" and m == "ok":
            return self._json(200, {"data": [{"id": "qwen3:4b"}, {"id": "llama3.2"}]})
        if self.path == "/api/tags" and m == "ollama-old":
            return self._json(200, {"models": [{"name": "phi4"}]})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        m = self.mode["chat"]
        if m == "401":
            return self._json(401, {"error": "missing key"})
        if m == "no-model":
            return self._json(404, {"error": "model 'nope' not found"})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        pieces = ["<think>", "let me", "</think>", "Hello", "!"] if m == "think" \
            else ["Hello", "!"]
        for p in pieces:
            frame = {"choices": [{"delta": {"content": p}}]}
            self.wfile.write(f"data: {json.dumps(frame)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")


@pytest.fixture
def fake():
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    Fake.mode = {"chat": "ok", "models": "ok"}
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_a_working_endpoint_reports_its_first_word(fake):
    r = endpoints.test_connection(fake, "llama3.2", key="")
    assert r["ok"] and r["reachable"]
    assert r["reply"] == "Hello!"
    assert r["first_word_s"] is not None and r["first_word_s"] < 5
    assert r["url"] == fake + "/v1"


def test_the_test_does_not_count_thinking_as_the_first_word(fake):
    Fake.mode["chat"] = "think"
    r = endpoints.test_connection(fake, "qwen3", key="")
    assert r["ok"] and r["reply"] == "Hello!"


def test_a_missing_key_is_said_plainly(fake, keys):
    Fake.mode["chat"] = "401"
    r = endpoints.test_connection(fake, "m", key="")
    assert not r["ok"] and r["error"] == "it wants an API key"


def test_a_missing_model_is_said_plainly(fake):
    Fake.mode["chat"] = "no-model"
    r = endpoints.test_connection(fake, "nope", key="")
    assert "no model called nope" in r["error"]


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_nothing_listening_is_wrong_port():
    r = endpoints.test_connection(f"http://127.0.0.1:{_free_port()}", "m", key="")
    assert not r["ok"] and not r["reachable"]
    assert "wrong port" in r["error"] or "isn't running" in r["error"]


def test_ollama_not_running_is_named(monkeypatch):
    err = ConnectionRefusedError(111, "refused")
    import urllib.error
    msg = endpoints.plain_error("http://localhost:11434/v1",
                                urllib.error.URLError(err))
    assert msg == "Ollama isn't running (nothing on port 11434)"


def test_models_come_from_v1_models(fake):
    assert endpoints.list_models(fake, key="") == ["llama3.2", "qwen3:4b"]


def test_models_fall_back_to_ollamas_own_list(fake):
    Fake.mode["models"] = "ollama-old"
    assert endpoints.list_models(fake + "/v1", key="") == ["phi4"]


def test_a_test_never_raises_on_garbage():
    r = endpoints.test_connection("not a url", "m", key="")
    assert r == {**r, "ok": False, "error": "that is not a URL"}


# --- the adapter: thinking out of the reply, history and timeout --------------

def test_the_adapter_never_streams_thinking_as_text(fake):
    from adapters.openai_compat import OpenAICompatible
    Fake.mode["chat"] = "think"
    a = OpenAICompatible(fake + "/v1", "qwen3")
    chunks = list(a.send("hi"))
    text = "".join(c.text for c in chunks)
    thinking = "".join(c.thinking for c in chunks)
    assert text == "Hello!"
    assert thinking == "let me"
    sid = chunks[0].session_id
    # The transcript replayed next turn holds the answer, not the thinking.
    assert a._sessions[sid][-1] == {"role": "assistant", "content": "Hello!"}


def test_no_history_sends_the_request_alone(fake):
    from adapters.openai_compat import OpenAICompatible
    a = OpenAICompatible(fake + "/v1", "m", spoken=False, history_turns=0)
    sid = list(a.send("one"))[0].session_id
    list(a.send("two", sid))
    _, messages = a._messages("three", sid)
    assert [m["content"] for m in messages] == ["three"]


def test_history_turns_are_bounded():
    from adapters.openai_compat import MAX_HISTORY_TURNS, OpenAICompatible
    assert OpenAICompatible("http://x/v1", "m", history_turns=10_000).history_turns \
        == MAX_HISTORY_TURNS


def test_a_chosen_timeout_is_the_one_used():
    from adapters.openai_compat import OpenAICompatible
    a = OpenAICompatible("http://x/v1", "m", timeout=45)
    assert a.timeout_set and a.timeout == 45
    assert not OpenAICompatible("http://x/v1", "m").timeout_set


def test_load_tidies_the_url_and_passes_the_numbers():
    from adapters import load
    a = load(endpoint={"url": "localhost:11434", "model": "llama3.2",
                       "history_turns": 3, "timeout_s": 60})
    assert a.base_url == "http://localhost:11434/v1"
    assert a.history_turns == 3 and a.timeout == 60


# --- settings: an endpoint for each agent -------------------------------------

def test_an_extra_agent_can_run_on_its_own_endpoint(cfg_factory):
    cfg = cfg_factory(voiceAgents=[{
        "name": "nova", "agent": "endpoint", "endpointUrl": "localhost:11434/",
        "endpointModel": "qwen3:4b", "endpointTimeoutS": 5,
        "endpointHistoryTurns": 99, "endpointIsAgent": "yes"}])
    (spec,) = cfg.agents()
    assert spec["agent"] == "endpoint"
    assert spec["endpoint"] == {"url": "http://localhost:11434/v1",
                                "model": "qwen3:4b", "is_agent": False,
                                "timeout_s": 10, "history_turns": 50}


def test_a_half_filled_endpoint_is_none(cfg_factory):
    cfg = cfg_factory(voiceAgents=[{"name": "nova", "agent": "endpoint",
                                    "endpointUrl": "localhost:11434"}])
    assert cfg.agents()[0]["endpoint"] is None
    assert cfg_factory(endpointUrl="x").main_endpoint() is None


def test_a_flag_shaped_model_is_not_a_model(cfg_factory):
    assert cfg_factory(endpointUrl="localhost:1", endpointModel="--x").main_endpoint() is None


def test_the_main_endpoint_carries_its_numbers(cfg_factory):
    e = cfg_factory(endpointUrl="api.openai.com", endpointModel="gpt-4o-mini",
                    endpointTimeoutS=0, endpointHistoryTurns=4).main_endpoint()
    assert e == {"url": "https://api.openai.com/v1", "model": "gpt-4o-mini",
                 "is_agent": False, "timeout_s": 0, "history_turns": 4}


def test_the_page_offers_exactly_the_shipped_presets():
    qml = (ROOT / "ui/EndpointEditor.qml").read_text()
    shown = re.findall(r'\{ id: "(\w+)", label: "[^"]+", url: "([^"]+)" \}', qml)
    assert shown == [(p["id"], p["url"]) for p in endpoints.PRESETS]


def test_every_preset_is_one_a_real_turn_went_through():
    # FINDINGS §14 is where the turn is recorded. A preset added without
    # one fails here, which is the repo's rule for a backend.
    findings = (ROOT / "bench/FINDINGS.md").read_text()
    for p in endpoints.PRESETS:
        assert f"| {p['label']}" in findings, p["label"]



def test_the_helpers_never_send_a_key_over_plain_http_to_a_public_host():
    """A-05 mutation M7 survived without this: the adapter's own check is
    tested, the connection test's and model list's were not."""
    req = endpoints._request("http://api.example.com/v1/models", "sk-secret")
    assert "Authorization" not in req.headers
    req = endpoints._request("https://api.example.com/v1/models", "sk-secret")
    assert req.headers["Authorization"] == "Bearer sk-secret"
    req = endpoints._request("http://192.168.1.5:11434/v1/models", "sk-secret")
    assert req.headers["Authorization"] == "Bearer sk-secret"
