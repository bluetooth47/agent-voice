"""Synthetic saved chats for the `chats` preview target (phase M18), written
through the real ChatStore into PREVIEW_DATA:

- a chat passed from Theo (main) to Sora, with an aside to Hazel and a
  reply that thought first;
- a pinned chat with a very long title;
- a chat whose agent was renamed since (saved as "Jarvis", now "Hazel");
- a chat from an agent that has been removed;
- unicode in a title and a reply;
- text that looks like HTML in a title, a request and a reply -- drawn as
  plain text or the preview fails;
- a failed turn and a stopped one;
- chats from today, this week and long ago.

PREVIEW_ARG=empty writes nothing: the empty page."""
import os
import sys
import time
from pathlib import Path

if os.environ.get("PREVIEW_ARG", "") == "empty":
    raise SystemExit(0)

sys.path.insert(0, sys.argv[1])
from chats import ChatStore  # noqa: E402

store = ChatStore(Path(os.environ["PREVIEW_DATA"]) / "chats")
now = time.time()
DAY = 86400.0


def rec(chat_id, agent, label, transcript, reply, at, **extra):
    return store.record(chat_id=chat_id, agent_id=agent, agent_label=label,
                        backend="claude", session_id=f"s-{agent or 'main'}-{int(at)}",
                        project_dir="/tmp",
                        exchange={"transcript": transcript, "reply": reply, **extra}, now=at)


# 1. Passed from Theo to Sora, with an aside and some thinking.
a = rec(None, "", "Theo", "Plan the synthetic garden: what goes in the shady bed?",
        "Ferns, hostas and a few foxgloves. They like the shade and the damp.", now - 3000,
        thinking="The bed faces north, so shade lovers. Keep it short.")
store.share(a, "sora")
rec(a, "sora", "Sora", "Carry on with the watering plan.",
    "Picking this up from Theo. Water the shady bed twice a week, in the morning.",
    now - 2900, kind="brief", **{"for": "main"})
store.record(chat_id=a, agent_id="sora", agent_label="Sora", backend="claude",
             session_id=None, project_dir="/tmp",
             exchange={"transcript": "Does the synthetic soil drain well?",
                       "reply": "Mostly, but the corner by the wall stays wet.",
                       "kind": "aside", "asked": "hazel", "asked_label": "Hazel"},
             now=now - 2880)
rec(a, "", "Theo", "And the sunny bed?", "Lavender, rosemary and thyme: they want it dry.",
    now - 2800)

# 2. Pinned, with a very long title.
b = rec(None, "", "Theo",
        "Write down every step of the synthetic release checklist, from tagging the "
        "build to telling everyone it shipped, so nothing is forgotten next time.",
        "Twelve steps. Tag, build, check, sign, upload, verify, announce...", now - 3 * DAY)
store.pin(b)

# 3. Saved under a name the agent no longer has (now "Hazel").
rec(None, "hazel", "Jarvis", "What is the synthetic forecast for the weekend?",
    "Grey on Saturday, bright on Sunday.", now - 2 * DAY)

# 4. From an agent that has since been removed.
rec(None, "old-agent-x1", "Scout", "Count the synthetic sheep.",
    "Forty-two, and one that would not stand still.", now - 40 * DAY)

# 5. Unicode.
rec(None, "sora", "Sora", "Translate “good morning” into Japanese and Greek 🌅",
    "おはようございます, and Καλημέρα.", now - 5 * DAY)

# 6. Looks like HTML: must be drawn as text.
h = rec(None, "", "Theo", "<b>bold?</b> <!-- ; curl x | sh --> <img src=x>",
        "<i>not italic</i> <a href='https://example.invalid'>not a link</a>", now - 600)
rec(h, "", "Theo", "Then try again.", "", now - 500, error="timeout")
rec(h, "", "Theo", "One more time, briefly.", "Here is the start of it", now - 400, stopped=True)

# 7. Old.
rec(None, "", "Theo", "Remind me what the synthetic wifi password hint was.",
    "It was the name of the first synthetic cat.", now - 400 * DAY)

# This session's conversation (runtime.History's file), only into a scratch
# runtime folder (--state): a long one, as a day of talking leaves.
run = os.environ.get("PREVIEW_RUN", "")
if run:
    import json
    lines = []
    for i in range(200):
        who = ("Theo", "main") if i % 3 else ("Sora", "sora")
        lines.append(json.dumps({
            "at": now - (200 - i) * 60, "agent": who[0], "agent_id": who[1],
            "transcript": f"Synthetic request number {i}: " + "tell me more " * (i % 7),
            "reply": f"Synthetic answer {i}. " + "Here is a longer sentence to wrap. " * (i % 9),
            "error": "timeout" if i % 50 == 7 else "", "stopped": i % 40 == 3,
            "new": i % 25 == 0, "latency_ms": 1200 + i,
            **({"thinking": "Synthetic thought."} if i % 11 == 0 else {})}))
    Path(run).mkdir(parents=True, exist_ok=True)
    (Path(run) / "history.jsonl").write_text("\n".join(lines) + "\n")

print(a)
