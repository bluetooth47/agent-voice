"""Synthetic saved chats for the `shared` preview target (Phase 15): one
passed from the main agent to Sora, one shared with Hazel, one Theo's
alone. Written through the real ChatStore into PREVIEW_DATA."""
import os
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from chats import ChatStore  # noqa: E402

store = ChatStore(Path(os.environ["PREVIEW_DATA"]) / "chats")
now = 1763600000.0
a = store.record(chat_id=None, agent_id="", agent_label="Theo", backend="claude",
                 session_id="s-theo", project_dir="/tmp",
                 exchange={"transcript": "Draft a packing list for the synthetic trip.",
                           "reply": "Passport, charger, rain jacket, two notebooks."}, now=now)
store.share(a, "sora")
store.record(chat_id=a, agent_id="sora", agent_label="Sora", backend="claude",
             session_id="s-sora", project_dir="/tmp",
             exchange={"transcript": "(passed from Theo)", "kind": "brief", "for": "main",
                       "reply": "Picking this up. Add an umbrella and snacks."}, now=now + 60)
b = store.record(chat_id=None, agent_id="", agent_label="Theo", backend="claude",
                 session_id="s-theo-2", project_dir="/tmp",
                 exchange={"transcript": "What is the synthetic weather today?",
                           "reply": "Mild and grey, as synthetic weather tends to be."},
                 now=now - 3600)
store.share(b, "jarvis-ajc")
store.record(chat_id=None, agent_id="", agent_label="Theo", backend="claude",
             session_id="s-theo-3", project_dir="/tmp",
             exchange={"transcript": "Name three synthetic colours.",
                       "reply": "Teal, ochre and slate."}, now=now - 7200)
print(a)
