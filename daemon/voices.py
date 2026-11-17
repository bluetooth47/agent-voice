"""The voice library behind the Voice page: fetch, hear and remove Piper voices.

    agentvoice voice fetch <voice>          download it, checked against models.lock
    agentvoice voice sample <voice> [speed] read about a minute of text in it
    agentvoice voice remove <voice>         delete it from disk

Run by the settings screen, which reads stdout line by line: `progress <pct>`
while downloading, then `done`, or `error <why>` and a non-zero exit.

A download here is held to the same rules as install.sh's: the revision and
the sha256 come from models.lock, a voice with no recorded hash is refused,
nothing but https is followed, and the file is written under a temporary name
and renamed only once its hash matches -- so an interrupted download never
leaves a file that looks installed.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
import urllib.request
from pathlib import Path

from paths import ROOT, VOICE_ID, piper_voices, voice_stem

REPO = "rhasspy/piper-voices"

#: The voice every install has. Removing it would leave nothing to fall back
#: on when another voice is missing, so it stays.
DEFAULT_VOICE = "lessac-medium"

#: About a minute at normal speed: 219 words, which lessac-medium read in 68
#: seconds on this machine (Piper runs near 195 words a minute). Varied on purpose -- a question, numbers, a list said as
#: a sentence, a long clause -- because that is where voices differ.
SAMPLE = (
    "Hello. This is a preview of how I sound, so take a minute and listen. "
    "I will be the one reading your answers out loud, so it matters that I am "
    "easy to follow. Here is the kind of thing I might say. The build finished "
    "in forty two seconds, and all one hundred and twelve tests passed. Two "
    "files changed: the settings page and the installer. Would you like me to "
    "commit them now, or look over the changes first? "
    "Some voices are warmer, some are crisper, and some are simply faster. "
    "A low quality voice is lighter on your machine and a little thinner to "
    "the ear. A high quality voice is fuller, and about twice the size to "
    "download. "
    "If I am talking too quickly or too slowly, you can change my speed on the "
    "agent's card, and it applies from the very next reply, with nothing to "
    "reload. "
    "One more sentence, to hear how I handle a longer thought: when you wake "
    "me with your phrase, I listen until you pause, write down what you said, "
    "hand it to your agent, and read its answer back to you, a sentence at a "
    "time, so you hear the start while the rest is still being written. "
    "That is the end of the preview. Thanks for listening."
)


def say(line: str) -> None:
    print(line, flush=True)


def fail(why: str) -> int:
    say(f"error {why}")
    return 1


def check_name(voice: str) -> str | None:
    return voice if VOICE_ID.fullmatch(voice or "") else None


def lock(path: Path | None = None) -> tuple[str, dict[str, str]]:
    """The pinned revision and every recorded hash, from models.lock."""
    text = (path or ROOT / "models.lock").read_text()
    rev = re.search(r"^revision piper ([0-9a-f]{40})$", text, re.M)
    hashes = dict(re.findall(r"^sha256 (\S+)\s+([0-9a-f]{64})$", text, re.M))
    return (rev.group(1) if rev else ""), hashes


def url_for(voice: str, rev: str, suffix: str = "") -> str:
    stem = voice_stem(voice)
    locale, rest = stem.split("-", 1)
    name, quality = rest.rsplit("-", 1)
    return (f"https://huggingface.co/{REPO}/resolve/{rev}/"
            f"{locale[:2]}/{locale}/{name}/{quality}/{stem}.onnx{suffix}")


class HttpsOnly(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only to another https URL."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith("https://"):
            raise urllib.error.URLError(f"refused a redirect to {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener():
    return urllib.request.build_opener(HttpsOnly)


def download(url: str, dest: Path, want: str, progress=None,
             opener=None) -> None:
    """Fetch `url` to `dest`, refusing anything whose sha256 is not `want`."""
    if not url.startswith("https://"):
        raise ValueError("only https")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / f".download.{dest.name}.{os.getpid()}"
    digest = hashlib.sha256()
    try:
        with (opener or _opener()).open(url, timeout=60) as resp, open(tmp, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            got = 0
            while True:
                block = resp.read(1 << 16)
                if not block:
                    break
                out.write(block)
                digest.update(block)
                got += len(block)
                if progress and total:
                    progress(got, total)
        if digest.hexdigest() != want:
            raise ValueError(f"{dest.name} does not match the hash in models.lock")
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)


def fetch(voice: str, folder: Path | None = None, lock_path: Path | None = None,
          opener=None) -> int:
    if not check_name(voice):
        return fail("that is not the name of a Piper voice")
    folder = folder or piper_voices()
    stem = voice_stem(voice)
    if (folder / f"{stem}.onnx").exists() and (folder / f"{stem}.onnx.json").exists():
        say("progress 100")
        say("done")
        return 0
    rev, hashes = lock(lock_path)
    model, config = f"{stem}.onnx", f"{stem}.onnx.json"
    if not rev or model not in hashes or config not in hashes:
        return fail(f"{voice} is not in models.lock, so it cannot be installed")
    last = [-1]

    def progress(got, total):
        pct = min(99, got * 100 // total)
        if pct != last[0]:
            last[0] = pct
            say(f"progress {pct}")

    try:
        # The small config first: a model with no config cannot be loaded,
        # and the model is what makes the file "present".
        download(url_for(voice, rev, ".json"), folder / config, hashes[config],
                 opener=opener)
        download(url_for(voice, rev), folder / model, hashes[model], progress,
                 opener=opener)
    except Exception as e:  # noqa: BLE001 -- reported, not raised
        return fail(str(e) or type(e).__name__)
    say("progress 100")
    say("done")
    return 0


def remove(voice: str, folder: Path | None = None) -> int:
    if not check_name(voice):
        return fail("that is not the name of a Piper voice")
    if voice == DEFAULT_VOICE:
        return fail("the default voice stays, so there is always one to fall back on")
    folder = folder or piper_voices()
    stem = voice_stem(voice)
    for name in (f"{stem}.onnx", f"{stem}.onnx.json"):
        (folder / name).unlink(missing_ok=True)
    say("done")
    return 0


def sample(voice: str, speed: int = 100) -> int:
    """Read SAMPLE in `voice`. Never a substitute: hearing a different voice
    than the one asked about would be a preview that lies."""
    if not check_name(voice):
        return fail("that is not the name of a Piper voice")
    if not (piper_voices() / f"{voice_stem(voice)}.onnx").exists():
        return fail(f"{voice} is not downloaded")
    from runtime import Speaker, speed_pct
    sp = Speaker(voice)
    sp.speed = speed_pct(speed)
    say("playing")
    sp.say(SAMPLE)
    say("done")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in ("fetch", "sample", "remove"):
        print("usage: agentvoice voice fetch|sample|remove <voice> [speed]",
              file=sys.stderr)
        return 2
    cmd, voice = argv[0], argv[1]
    if cmd == "fetch":
        return fetch(voice)
    if cmd == "remove":
        return remove(voice)
    speed = int(argv[2]) if len(argv) > 2 and argv[2].isdigit() else 100
    return sample(voice, speed)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
