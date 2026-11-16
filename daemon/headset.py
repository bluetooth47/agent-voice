"""Whether our voice is going into somebody's ears or into the room.

Barge-in fails on a laptop for one reason: the speaker sits beside the
microphone, so our own voice reaches it as loudly as the person's does
(bench/FINDINGS.md). On headphones that reason is gone. Measured on a
Bluetooth headset (OpenRun Pro 2, HFP), playing a reply into the ears and
recording its own microphone at the same time: median -180 dBFS, peak
-71 dBFS, against a gate at -38.4. The headset's own echo cancellation took
out everything, so a gate floored where upstream floors it never fired on
our voice at all.

So instead of asking everybody to run `agentvoice calibrate`, the daemon
asks the sound server where the output goes. Wired headphones on the
built-in card count too: the card's form factor says "internal" but the
active port says "Headphones", and either one is enough.

Answers None when it cannot tell: no pactl, a pactl too old for JSON, no
default sink, a timeout. Not a guess either way -- the caller treats it as
"not a headset", because the cost of guessing wrong in that direction is
the behaviour everybody already had, and the cost of guessing wrong in the
other is a reply that keeps interrupting itself.
"""
from __future__ import annotations

import json
import subprocess

#: PipeWire's `device.form_factor` values that put the sound in someone's
#: ears. "handset" is a phone held to the head; "hands-free" is what a
#: Bluetooth headset calls itself in some profiles.
HEADSET_FORMS = frozenset({"headset", "headphone", "hands-free", "handset"})

#: Port types and names that mean the same on a card that is otherwise
#: internal: a 3.5mm jack is a port of the laptop's own card.
HEADSET_PORT_TYPES = frozenset({"headphones", "headset"})


def is_headset(sink: dict) -> bool:
    """True when this sink, as `pactl -f json list sinks` describes it,
    plays into somebody's ears."""
    props = sink.get("properties") or {}
    if not isinstance(props, dict):
        props = {}
    if str(props.get("device.form_factor", "")).lower() in HEADSET_FORMS:
        return True
    active = str(sink.get("active_port") or "")
    if not active:
        return False
    for port in sink.get("ports") or []:
        if isinstance(port, dict) and port.get("name") == active:
            if str(port.get("type", "")).lower() in HEADSET_PORT_TYPES:
                return True
    # Older pactl prints no port type; the name carries it on ALSA cards.
    return "headphone" in active.lower() or "headset" in active.lower()


def default_output() -> tuple[bool, str] | None:
    """(is it a headset, what it is called) for the default sink, or None."""
    try:
        name = subprocess.run(["pactl", "get-default-sink"],
                              capture_output=True, text=True,
                              timeout=2).stdout.strip()
        if not name:
            return None
        out = subprocess.run(["pactl", "-f", "json", "list", "sinks"],
                             capture_output=True, text=True,
                             timeout=2).stdout
        sinks = json.loads(out)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if not isinstance(sinks, list):
        return None
    for sink in sinks:
        if isinstance(sink, dict) and sink.get("name") == name:
            props = sink.get("properties") or {}
            label = (props.get("device.description") if isinstance(props, dict)
                     else None) or sink.get("description") or name
            return is_headset(sink), str(label)
    return None
