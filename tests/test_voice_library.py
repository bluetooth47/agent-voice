"""The Voice page's library: fetch, sample and remove a Piper voice.

A download from the settings screen is held to the installer's rules: the
revision and hash come from models.lock, an unlisted voice is refused, a
mismatch leaves nothing behind, and only https is followed.
"""
from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path

import pytest

import voices

ROOT = Path(__file__).resolve().parent.parent
REV = "c" * 40


def _lock(tmp_path, files: dict[str, bytes]) -> Path:
    lines = [f"revision piper {REV}"]
    for name, body in files.items():
        lines.append(f"sha256 {name} {hashlib.sha256(body).hexdigest()}")
    p = tmp_path / "models.lock"
    p.write_text("\n".join(lines) + "\n")
    return p


class Served:
    """An opener that answers each URL with a fixed body."""

    def __init__(self, bodies: dict[str, bytes]):
        self.bodies, self.asked = bodies, []

    def open(self, url, timeout=None):
        self.asked.append(url)
        body = self.bodies[url.rsplit("/", 1)[1]]
        resp = io.BytesIO(body)
        resp.headers = {"Content-Length": str(len(body))}
        resp.__enter__ = lambda: resp
        return _Ctx(resp)


class _Ctx:
    def __init__(self, r): self.r = r
    def __enter__(self): return self.r
    def __exit__(self, *a): return False


# --- names and URLs ------------------------------------------------------------

@pytest.mark.parametrize("voice, path", [
    ("ryan-medium", "en/en_US/ryan/medium/en_US-ryan-medium.onnx"),
    ("hfc_male-medium", "en/en_US/hfc_male/medium/en_US-hfc_male-medium.onnx"),
    ("en_GB-alan-low", "en/en_GB/alan/low/en_GB-alan-low.onnx"),
    ("en_GB-northern_english_male-medium",
     "en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx"),
])
def test_the_url_follows_the_repository_layout(voice, path):
    assert voices.url_for(voice, REV) == (
        f"https://huggingface.co/rhasspy/piper-voices/resolve/{REV}/{path}")


@pytest.mark.parametrize("bad", ["../../x-medium", "a b-low", "x;rm -rf ~-medium",
                                 "EN_GB-alan-medium", "alan", ""])
def test_anything_not_a_voice_name_is_refused(bad, capsys):
    assert voices.fetch(bad) == 1
    assert voices.remove(bad) == 1
    assert "not the name of a Piper voice" in capsys.readouterr().out


# --- fetch ---------------------------------------------------------------------

def test_a_voice_arrives_verified(tmp_path, capsys):
    model, config = b"model" * 1000, b'{"audio": {}}'
    names = {"en_GB-alan-medium.onnx": model, "en_GB-alan-medium.onnx.json": config}
    served = Served(names)
    assert voices.fetch("en_GB-alan-medium", folder=tmp_path / "piper",
                        lock_path=_lock(tmp_path, names), opener=served) == 0
    assert (tmp_path / "piper" / "en_GB-alan-medium.onnx").read_bytes() == model
    assert all(u.startswith(f"https://huggingface.co/rhasspy/piper-voices/resolve/{REV}/")
               for u in served.asked)
    out = capsys.readouterr().out.split()
    assert out[-1] == "done" and "100" in out


def test_a_mismatched_file_leaves_nothing(tmp_path, capsys):
    names = {"ryan-x": b""}
    lock = _lock(tmp_path, {"en_US-ryan-medium.onnx": b"the real one",
                            "en_US-ryan-medium.onnx.json": b"{}"})
    served = Served({"en_US-ryan-medium.onnx": b"something else",
                     "en_US-ryan-medium.onnx.json": b"{}"})
    assert voices.fetch("ryan-medium", folder=tmp_path / "piper",
                        lock_path=lock, opener=served) == 1
    left = sorted(p.name for p in (tmp_path / "piper").iterdir())
    assert "en_US-ryan-medium.onnx" not in left
    assert not [n for n in left if n.startswith(".download")]
    assert "does not match" in capsys.readouterr().out
    del names


def test_a_voice_not_in_the_lock_is_not_fetched(tmp_path, capsys):
    served = Served({})
    assert voices.fetch("ryan-medium", folder=tmp_path, opener=served,
                        lock_path=_lock(tmp_path, {})) == 1
    assert served.asked == []
    assert "not in models.lock" in capsys.readouterr().out


def test_a_voice_already_here_is_not_fetched_again(tmp_path):
    (tmp_path / "en_US-joe-medium.onnx").write_bytes(b"x")
    (tmp_path / "en_US-joe-medium.onnx.json").write_bytes(b"{}")
    served = Served({})
    assert voices.fetch("joe-medium", folder=tmp_path, opener=served,
                        lock_path=_lock(tmp_path, {})) == 0
    assert served.asked == []


def test_a_redirect_to_plain_http_is_refused():
    import urllib.error
    import urllib.request
    h = voices.HttpsOnly()
    req = urllib.request.Request("https://huggingface.co/x")
    with pytest.raises(urllib.error.URLError):
        h.redirect_request(req, None, 302, "Found", {}, "http://evil.example/x")


def test_every_offered_voice_can_be_fetched():
    """Each voice the screen offers resolves to a URL and two hashes."""
    rev, hashes = voices.lock()
    assert re.fullmatch(r"[0-9a-f]{40}", rev)
    offered = re.findall(r'value: "((?:[a-z]{2}_[A-Z]{2}-)?[a-z_]+-(?:x_low|low|medium|high))"',
                         (ROOT / "Settings.qml").read_text())
    assert len(offered) >= 30
    for v in offered:
        stem = voices.voice_stem(v)
        assert f"{stem}.onnx" in hashes and f"{stem}.onnx.json" in hashes, v


# --- remove and sample -----------------------------------------------------------

def test_removing_deletes_both_files(tmp_path):
    for n in ("en_GB-alba-medium.onnx", "en_GB-alba-medium.onnx.json"):
        (tmp_path / n).write_bytes(b"x")
    assert voices.remove("en_GB-alba-medium", folder=tmp_path) == 0
    assert list(tmp_path.iterdir()) == []


def test_the_default_voice_cannot_be_removed(tmp_path, capsys):
    (tmp_path / "en_US-lessac-medium.onnx").write_bytes(b"x")
    assert voices.remove("lessac-medium", folder=tmp_path) == 1
    assert (tmp_path / "en_US-lessac-medium.onnx").exists()
    assert "fall back" in capsys.readouterr().out


def test_a_sample_never_plays_a_substitute(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(voices, "piper_voices", lambda: tmp_path)
    (tmp_path / "en_US-lessac-medium.onnx").write_bytes(b"x")
    assert voices.sample("ryan-medium") == 1
    assert "not downloaded" in capsys.readouterr().out


def test_the_sample_is_about_a_minute():
    words = len(voices.SAMPLE.split())
    # 219 words measured at 68s in lessac-medium: Piper reads ~195 a minute.
    assert 180 <= words <= 240, words


def test_british_voices_are_found_on_disk_and_used(tmp_path, monkeypatch):
    import runtime
    monkeypatch.setattr(runtime, "piper_voices", lambda: tmp_path)
    (tmp_path / "en_GB-alan-medium.onnx").write_bytes(b"x")
    assert runtime.Speaker._resolve("en_GB-alan-medium") == ("en_GB-alan-medium", "")
    assert runtime.Speaker._resolve("ryan-medium") == ("en_GB-alan-medium", "ryan-medium")


def test_a_british_voice_is_a_valid_agent_voice(cfg_factory):
    cfg = cfg_factory(voiceAgents=[{"name": "friday", "voice": "en_GB-cori-high"}])
    assert cfg.agents()[0]["voice"] == "en_GB-cori-high"
