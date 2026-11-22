"""Approval cards in tests, answered the way the overlay answers them.

Since phase M7 a card is the daemon's (cards.py), not a pair of files, so the
helpers that used to glob `$RUNDIR/permissions/*.request` and write a
`.response` beside it now take the in-process desk conftest installs for
every test (`card_desk`) and answer through its own path: shown with the
nonce a checked caller is given, answered with that nonce and the digest.
The caller check itself is tested with real processes in test_cards.py.
"""
from __future__ import annotations

import threading
import time


def wait_card(desk, within: float = 3.0) -> dict | None:
    """The first card to go up within `within` seconds, as shown, or None."""
    end = time.time() + within
    while time.time() < end:
        up = desk.pending()
        if up:
            return up[0]
        time.sleep(0.01)
    return None


def answer_after(desk, delay: float = 0.0, verdict: str = "allow",
                 seen: dict | None = None, within: float = 5.0) -> threading.Thread:
    """Answer the next card with `verdict`, `delay` seconds after it goes up,
    as the overlay would. `seen`, when given, gets the card as shown. A
    verdict of None leaves it unanswered (only `seen` is filled)."""
    def run():
        card = wait_card(desk, within)
        if card is None:
            return
        if seen is not None:
            seen.update(card)
        if verdict is None:
            return
        time.sleep(delay)
        shown = desk.show(card["id"], verified=True)
        desk.answer(card["id"], verdict, shown.get("nonce", ""),
                    shown.get("digest", ""), verified=True)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def peek(desk, seen: dict, verdict: str | None = "deny") -> threading.Thread:
    """Record the next card as shown, then answer it (`deny` by default, so
    the call returns at once rather than at its timeout)."""
    return answer_after(desk, 0.0, verdict, seen=seen)


import contextlib  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


@contextlib.contextmanager
def live_desk(rundir: Path, verifier=None, is_locked=None):
    """A real desk and listener under `rundir` -- what XDG_RUNTIME_DIR
    names for a subprocess -- so `bin/agentvoice pending|permit` run against
    a real socket. Whatever is still up at the end is denied."""
    import cards
    desk = cards.Desk(summon=lambda cid: None,
                      is_locked=is_locked if is_locked is not None else (lambda: False))
    listener = cards.Listener(desk, verifier if verifier is not None else cards.Verifier(),
                              rundir / "agentvoice" / "cards")
    assert listener.start()
    try:
        yield desk
    finally:
        listener.stop()
        for c in desk.pending():
            desk.answer(c["id"], "deny")


def post_async(desk, fields: dict, timeout: float = 10.0):
    """Post a card from a thread: (thread, out) where out["answer"] is what
    the asker got, once the thread is done. Waits until it is up."""
    out: dict = {}
    before = {c["id"] for c in desk.pending()}
    t = threading.Thread(target=lambda: out.update(answer=desk.post(fields, timeout)),
                         daemon=True)
    t.start()
    end = time.time() + 3
    while time.time() < end:
        new = [c for c in desk.pending() if c["id"] not in before]
        if new:
            out["id"] = new[0]["id"]
            break
        time.sleep(0.01)
    return t, out


def cli(rundir: Path, *args: str, stdin: str | None = None, **kw):
    """bin/agentvoice under `rundir`, with this interpreter as its Python."""
    env = {**os.environ, "XDG_RUNTIME_DIR": str(rundir),
           "AGENTVOICE_PYTHON": sys.executable}
    return subprocess.run([str(ROOT / "bin" / "agentvoice"), *args], env=env,
                          input=stdin, capture_output=True, text=True, timeout=30, **kw)
