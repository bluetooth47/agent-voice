#!/usr/bin/env python3
"""Stands in for the Omarchy shell in test_cards.py.

Started as `python fake_shell.py -p DIR STEPS`, it runs `agentvoice pending`
and `agentvoice permit` the way the overlay's Process objects do: as its own
children, with their stdout (pending) and stdin (permit) pipes that it holds
until they exit. STEPS is JSON:

  agentvoice        the bin/agentvoice to run
  id, verdict       the card and the answer
  nonce, digest     used instead of what `pending` handed back, when given
  pending_to_file   send pending's stdout to this file instead of a pipe
  pending_to_other  send it into a pipe this process does not hold (a
                    `cat` reads the other end), as a pipeline would
  permit_from_file  give permit its stdin from this file instead of a pipe

It prints what came back as one JSON line.
"""
import json
import subprocess
import sys

steps = json.loads(sys.argv[3])
av = steps["agentvoice"]
cid = steps["id"]
out = {}

if steps.get("pending_to_other"):
    import os
    r, w = os.pipe()
    reader = subprocess.Popen(["cat"], stdin=r, stdout=subprocess.PIPE)
    p = subprocess.Popen([av, "pending", cid], stdout=w)
    os.close(r)
    os.close(w)
    p.wait(timeout=20)
    text = reader.stdout.read()
    reader.wait(timeout=20)
    out["shown"] = json.loads(text or b"{}")
elif steps.get("pending_to_file"):
    with open(steps["pending_to_file"], "w") as f:
        subprocess.run([av, "pending", cid], stdout=f, timeout=20)
    with open(steps["pending_to_file"]) as f:
        out["shown"] = json.loads(f.read() or "{}")
else:
    p = subprocess.Popen([av, "pending", cid], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE)
    text = p.stdout.read()
    p.wait(timeout=20)
    p.stdin.close()
    out["shown"] = json.loads(text or b"{}")

if steps.get("verdict"):
    line = json.dumps({"nonce": steps.get("nonce", out["shown"].get("nonce", "")),
                       "digest": steps.get("digest", out["shown"].get("digest", ""))}) + "\n"
    if steps.get("permit_from_file"):
        with open(steps["permit_from_file"], "w") as f:
            f.write(line)
        with open(steps["permit_from_file"]) as f:
            r = subprocess.run([av, "permit", cid, steps["verdict"]], stdin=f,
                               capture_output=True, text=True, timeout=20)
        out["permit"] = {"rc": r.returncode, "out": r.stdout, "err": r.stderr}
    else:
        # As Quickshell does: the line written at start, the pipe left open
        # until the child is done.
        p = subprocess.Popen([av, "permit", cid, steps["verdict"]], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        p.stdin.write(line)
        p.stdin.flush()
        o = p.stdout.read()
        e = p.stderr.read()
        p.wait(timeout=20)
        p.stdin.close()
        out["permit"] = {"rc": p.returncode, "out": o, "err": e}

print(json.dumps(out))
