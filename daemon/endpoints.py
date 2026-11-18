"""OpenAI-compatible endpoints: tidying a URL, keys, a connection test, the
model list, and the thinking text a reasoning model streams (plan item 7b).

Everything an endpoint needs that is not the streaming turn itself, which is
`adapters/openai_compat.py`. Kept apart so the settings page can call it
through `agentvoice endpoint ...` without loading the daemon.

Run as a program it is that CLI:

    endpoints.py clean URL                 the URL that will actually be used
    endpoints.py models URL                JSON list of model names
    endpoints.py test URL MODEL            JSON: reachable, key, first word, error
    endpoints.py key set URL               the key on stdin, never in argv
    endpoints.py key show URL              masked: "sk-…a1b2", or nothing
    endpoints.py key clear URL
    endpoints.py presets                   JSON list of the shipped presets
"""
from __future__ import annotations

import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

#: Presets. The repo's rule for a backend holds here too: one ships only
#: after a real turn has gone through it. These four answered the latency
#: run in FINDINGS §14. LM Studio, llama.cpp's server, vLLM and OpenRouter
#: speak the same dialect and are reachable by typing their URL, but are not
#: offered as presets until one has answered here.
PRESETS = (
    {"id": "ollama", "label": "Ollama", "url": "http://localhost:11434/v1",
     "key": False, "local": True},
    {"id": "openai", "label": "OpenAI", "url": "https://api.openai.com/v1",
     "key": True, "local": False},
    {"id": "groq", "label": "Groq", "url": "https://api.groq.com/openai/v1",
     "key": True, "local": False},
    {"id": "xai", "label": "xAI", "url": "https://api.x.ai/v1",
     "key": True, "local": False},
)

#: Default ports of the local servers people run, for explaining a refused
#: connection in their terms rather than errno's.
LOCAL_SERVERS = {11434: "Ollama", 1234: "LM Studio", 8080: "llama.cpp's server",
                 8000: "vLLM"}

#: The tails people paste with a URL copied from documentation.
_TAILS = ("/chat/completions", "/completions", "/models", "/responses")

#: Bounds on what a test or a model list will read. The same reasoning as
#: openai_compat's caps: the far end decides how much it sends.
MAX_BODY = 2 * 1024 * 1024
TEST_TIMEOUT_S = 20.0

USER_AGENT = "agentvoice/0.2 (+https://github.com/duaneoca/agent-voice)"


# --- the URL ---------------------------------------------------------------

def clean_url(raw: str) -> str:
    """The URL that will actually be used, from what somebody typed.

    - a missing scheme becomes http:// for a local or private host and
      https:// for anything else, because a public host over plain http
      would carry the key in the clear and the adapter refuses that anyway;
    - a pasted /chat/completions (or /models, /completions) is cut back;
    - a missing /v1 is added when the path is empty; a path that already
      says something (/openai/v1, /api/v1, /v2) is left alone;
    - a trailing slash and whitespace go.

    Returns "" for anything that is not plainly a URL.
    """
    text = (raw or "").strip()
    if not text or any(c.isspace() for c in text):
        return ""
    if "://" not in text:
        host = re.split(r"[/:]", text, maxsplit=1)[0]
        text = ("http://" if _private_host(host) else "https://") + text
    try:
        parts = urllib.parse.urlsplit(text)
    except ValueError:
        return ""
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return ""
    if parts.username or parts.password:
        # A key typed into the URL would be shown on screen and kept in the
        # synced settings. Refused rather than quietly stripped.
        return ""
    path = parts.path.rstrip("/")
    lowered = path.lower()
    for tail in _TAILS:
        if lowered.endswith(tail):
            path = path[: -len(tail)].rstrip("/")
            break
    if not path:
        path = "/v1"
    try:
        port = parts.port
    except ValueError:
        return ""
    netloc = parts.hostname if ":" not in parts.hostname else f"[{parts.hostname}]"
    if port:
        netloc += f":{port}"
    return urllib.parse.urlunsplit((parts.scheme, netloc, path, "", ""))


def _private_host(host: str) -> bool:
    import ipaddress
    host = host.strip("[]").lower()
    if host in ("localhost", "::1") or host.endswith(".local") or "." not in host:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private


def host_of(url: str) -> str:
    """host[:port], what keys are filed under."""
    try:
        return urllib.parse.urlsplit(url).netloc.lower()
    except ValueError:
        return ""


# --- keys ------------------------------------------------------------------

def _keys_file() -> Path:
    from paths import CONFIG_DIR
    return CONFIG_DIR / "endpoint-keys.json"


def _read_keys() -> dict[str, str]:
    """{host: key} from the owner-only file, or {} when it is absent or
    anybody else could read it."""
    path = _keys_file()
    try:
        st = path.stat()
    except OSError:
        return {}
    if st.st_mode & 0o077 or st.st_uid != os.getuid():
        print(f"agentvoice: ignoring {path}: others can read it. chmod 600 it.",
              file=sys.stderr)
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, str) and v}


def stored_key(host: str) -> str:
    """The key saved from the settings page for this host, or ""."""
    return _read_keys().get((host or "").lower(), "")


def save_key(host: str, key: str) -> None:
    """File `key` under `host`, or remove it when `key` is empty."""
    host = (host or "").lower()
    if not host:
        raise ValueError("no host")
    key = key.strip()
    if any(c.isspace() for c in key) or len(key) > 4096:
        raise ValueError("that does not look like an API key")
    keys = _read_keys()
    if key:
        keys[host] = key
    else:
        keys.pop(host, None)
    path = _keys_file()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staged = path.with_suffix(f".{os.getpid()}.tmp")
    fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
                 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(keys, f, indent=1)
    os.replace(staged, path)


def masked(key: str) -> str:
    """Enough of a key to recognise it, never enough to use it."""
    if not key:
        return ""
    if len(key) <= 8:
        return "•" * len(key)
    head = key[:3] if key[:3].isalpha() or key.startswith("sk-") else ""
    return f"{head}…{key[-4:]}"


def key_for(url: str) -> str:
    """The key to send to this endpoint: paths.endpoint_key's order, with
    the settings page's own file after the keyring for that host."""
    from paths import endpoint_key
    return endpoint_key(host_of(url))


# --- talking to it ---------------------------------------------------------

class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code,
                                     f"it redirects to {newurl}", headers, fp)


_OPENER = urllib.request.build_opener(_NoRedirects)


def _request(url: str, key: str, body: dict | None = None):
    headers = {"User-Agent": USER_AGENT}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if key and safe_to_send_key(url):
        headers["Authorization"] = f"Bearer {key}"
    data = json.dumps(body).encode() if body is not None else None
    return urllib.request.Request(url, data=data, headers=headers)


def safe_to_send_key(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    return parts.scheme == "https" or _private_host(parts.hostname or "")


def plain_error(url: str, error: BaseException, model: str = "") -> str:
    """What went wrong, in words somebody can act on."""
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or url
    port = parts.port or (443 if parts.scheme == "https" else 80)
    server = LOCAL_SERVERS.get(port, "")
    reason = getattr(error, "reason", error)
    if isinstance(error, urllib.error.HTTPError):
        code = error.code
        try:
            detail = error.read(8192).decode("utf-8", "replace")
        except Exception:
            detail = ""
        low = detail.lower()
        if code in (401, 403) and "1010" in detail:
            return "blocked by Cloudflare"
        if code == 401:
            return "it wants an API key" if not key_for(url) else \
                "it refused the API key"
        if code == 403:
            return "it refused the API key"
        if code == 404 and model and ("model" in low or "not found" in low):
            if server == "Ollama":
                return f"model not pulled: run ollama pull {model}"
            return f"it has no model called {model}"
        if code == 404:
            return "nothing answers at that path: check the /v1 part"
        if 300 <= code < 400:
            return str(error.reason)
        return f"HTTP {code}: {detail.strip()[:120] or error.reason}"
    if isinstance(reason, ConnectionRefusedError) or "refused" in str(reason).lower():
        if _private_host(host) and server:
            return f"{server} isn't running (nothing on port {port})"
        return f"nothing is listening on {host} port {port}: wrong port?"
    if isinstance(reason, socket.gaierror) or "name or service" in str(reason).lower():
        return f"no such host: {host}"
    if isinstance(error, (TimeoutError, socket.timeout)) or "timed out" in str(reason).lower():
        return f"{host} did not answer in time"
    if "ssl" in str(reason).lower() or "certificate" in str(reason).lower():
        return f"https failed: {reason}"
    return f"{type(error).__name__}: {reason}"


def list_models(url: str, key: str | None = None,
                timeout: float = 8.0) -> list[str]:
    """Model names the endpoint offers: /v1/models, else Ollama's /api/tags.

    Raises with a plain message when neither answers.
    """
    url = clean_url(url)
    if not url:
        raise ValueError("that is not a URL")
    key = key_for(url) if key is None else key
    first: BaseException | None = None
    try:
        with _OPENER.open(_request(f"{url}/models", key), timeout=timeout) as r:
            data = json.loads(r.read(MAX_BODY).decode("utf-8", "replace"))
        names = [m.get("id") for m in (data.get("data") or [])
                 if isinstance(m, dict)]
        names = sorted({n for n in names if isinstance(n, str) and n})
        if names:
            return names
    except Exception as e:                      # noqa: BLE001
        first = e
    # Ollama answers /v1/models too, but older versions did not; its own
    # list is beside /v1, not under it.
    base = url[:-3] if url.endswith("/v1") else url
    try:
        with _OPENER.open(_request(f"{base}/api/tags", key), timeout=timeout) as r:
            data = json.loads(r.read(MAX_BODY).decode("utf-8", "replace"))
        names = sorted({m.get("name") for m in (data.get("models") or [])
                        if isinstance(m, dict) and isinstance(m.get("name"), str)})
        if names:
            return names
    except Exception:                           # noqa: BLE001
        pass
    if first is not None:
        raise RuntimeError(plain_error(url, first))
    return []


def test_connection(url: str, model: str, key: str | None = None,
                    timeout: float = TEST_TIMEOUT_S) -> dict:
    """One tiny streamed request, timed.

    Returns {"ok", "url", "reachable", "key" ("none"|"sent"|"withheld"),
    "first_word_s", "total_s", "reply", "error"}. Never raises.
    """
    out = {"ok": False, "url": "", "reachable": False, "key": "none",
           "first_word_s": None, "total_s": None, "reply": "", "error": ""}
    cleaned = clean_url(url)
    out["url"] = cleaned
    if not cleaned:
        out["error"] = "that is not a URL"
        return out
    if not model.strip():
        out["error"] = "no model chosen"
        return out
    key = key_for(cleaned) if key is None else key
    if key:
        out["key"] = "sent" if safe_to_send_key(cleaned) else "withheld"
    body = {"model": model.strip(), "stream": True, "max_tokens": 16,
            "messages": [{"role": "user", "content": "Say hello in one word."}]}
    start = time.monotonic()
    think = ThinkFilter()
    try:
        with _OPENER.open(_request(f"{cleaned}/chat/completions", key, body),
                          timeout=timeout) as r:
            out["reachable"] = True
            read = 0
            while True:
                raw = r.readline(65537)
                if not raw:
                    break
                read += len(raw)
                if read > MAX_BODY or time.monotonic() - start > timeout:
                    break
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    event = json.loads(payload)
                except ValueError:
                    continue
                said, _ = split_delta(event, think)
                if said and out["first_word_s"] is None:
                    out["first_word_s"] = round(time.monotonic() - start, 2)
                out["reply"] += said
                if len(out["reply"]) > 200:
                    break
        out["total_s"] = round(time.monotonic() - start, 2)
        out["reply"] = out["reply"].strip()[:200]
        out["ok"] = True
        if out["first_word_s"] is None:
            out["error"] = "it answered, but said nothing"
            out["ok"] = False
    except urllib.error.HTTPError as e:
        out["reachable"] = True
        out["error"] = plain_error(cleaned, e, model)
    except Exception as e:                      # noqa: BLE001
        out["error"] = plain_error(cleaned, e, model)
    if out["key"] == "withheld" and not out["ok"]:
        out["error"] += (" (a key is saved, but it is not sent over plain "
                         "http to a public host)")
    return out


# --- thinking text ---------------------------------------------------------

#: Other spellings reasoning models use for the same block.
_TAGS = (("<think>", "</think>"), ("<thinking>", "</thinking>"),
         ("<reasoning>", "</reasoning>"))


class ThinkFilter:
    """Takes a reasoning model's `<think>…</think>` out of a streamed reply.

    Streamed, so a tag can arrive split across two pieces ("<thi", "nk>");
    anything that could still be the start of a tag is held back until the
    next piece settles it. `feed()` returns (to say, thinking). `flush()`
    returns whatever was held at the end: held text that never became a tag
    is ordinary text, and thinking that was never closed stays thinking --
    an unfinished block is not an answer.
    """

    def __init__(self) -> None:
        self._held = ""
        self._inside: str | None = None      # the closing tag being waited for

    def feed(self, piece: str) -> tuple[str, str]:
        text = self._held + (piece or "")
        self._held = ""
        said, thought = [], []
        while text:
            if self._inside:
                end = text.find(self._inside)
                if end >= 0:
                    thought.append(text[:end])
                    text = text[end + len(self._inside):]
                    self._inside = None
                    continue
                keep = _partial_suffix(text, (self._inside,))
                thought.append(text[: len(text) - keep])
                self._held = text[len(text) - keep:]
                break
            starts = [(text.find(o), o, c) for o, c in _TAGS if text.find(o) >= 0]
            if starts:
                at, opened, closing = min(starts)
                said.append(text[:at])
                text = text[at + len(opened):]
                self._inside = closing
                continue
            keep = _partial_suffix(text, tuple(o for o, _ in _TAGS))
            said.append(text[: len(text) - keep])
            self._held = text[len(text) - keep:]
            break
        return "".join(said), "".join(thought)

    def flush(self) -> tuple[str, str]:
        held, self._held = self._held, ""
        if self._inside:
            return "", held
        return held, ""


def _partial_suffix(text: str, tags: tuple[str, ...]) -> int:
    """How many trailing characters of `text` could begin one of `tags`."""
    best = 0
    for tag in tags:
        for n in range(min(len(tag) - 1, len(text)), 0, -1):
            if tag.startswith(text[-n:]):
                best = max(best, n)
                break
    return best


def split_delta(event: dict, think: ThinkFilter) -> tuple[str, str]:
    """(said, thinking) from one streamed chat-completions event.

    Thinking comes either inline as tags, or in a field of its own: llama.cpp
    and vLLM send `reasoning_content`, OpenRouter and Ollama `reasoning`.
    """
    choices = event.get("choices") if isinstance(event, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return "", ""
    delta = choices[0].get("delta") or {}
    if not isinstance(delta, dict):
        return "", ""
    thought = ""
    for field in ("reasoning_content", "reasoning"):
        value = delta.get(field)
        if isinstance(value, str):
            thought += value
    content = delta.get("content")
    said = ""
    if isinstance(content, str) and content:
        said, inline = think.feed(content)
        thought += inline
    return said, thought


def strip_thinking(text: str) -> str:
    """A whole reply with every thinking block taken out."""
    f = ThinkFilter()
    said, _ = f.feed(text)
    rest, _ = f.flush()
    return said + rest


# --- the CLI the settings page runs ----------------------------------------

def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == "presets":
        print(json.dumps(list(PRESETS)))
        return 0
    if cmd == "clean" and len(args) == 1:
        print(clean_url(args[0]))
        return 0 if clean_url(args[0]) else 1
    if cmd == "models" and len(args) == 1:
        try:
            print(json.dumps({"models": list_models(args[0]), "error": ""}))
        except Exception as e:                  # noqa: BLE001
            print(json.dumps({"models": [], "error": str(e)}))
        return 0
    if cmd == "test" and len(args) == 2:
        print(json.dumps(test_connection(args[0], args[1])))
        return 0
    if cmd == "key" and len(args) == 2 and args[0] in ("set", "show", "clear"):
        url = clean_url(args[1])
        host = host_of(url)
        if not host:
            print("that is not a URL", file=sys.stderr)
            return 2
        if args[0] == "show":
            print(masked(key_for(url)))
            return 0
        try:
            # From stdin only: argv is readable by every account on the box.
            save_key(host, sys.stdin.readline() if args[0] == "set" else "")
        except (OSError, ValueError) as e:
            print(f"could not save it: {e}", file=sys.stderr)
            return 1
        print(masked(stored_key(host)))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
