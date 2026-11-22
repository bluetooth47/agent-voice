#!/usr/bin/env python3
"""A do-nothing MCP stdio server for timing (phase M10, FINDINGS §44): one
tool, `ping`, answering "pong". Started as a "found" server by
start_bench.py's strict3 variant, so what three switched-on servers cost a
turn is measured without depending on anyone's real ones. Writes nothing."""
import json
import sys

name = sys.argv[1] if len(sys.argv) > 1 else "stub"
for line in sys.stdin:
    try:
        msg = json.loads(line)
    except ValueError:
        continue
    mid, method = msg.get("id"), msg.get("method")
    if method == "initialize":
        result = {"protocolVersion": (msg.get("params") or {}).get("protocolVersion", "2024-11-05"),
                  "capabilities": {"tools": {}}, "serverInfo": {"name": name, "version": "0"}}
    elif method == "tools/list":
        result = {"tools": [{"name": "ping", "description": "Answers pong; for timing only.",
                             "inputSchema": {"type": "object", "properties": {}}}]}
    elif method == "tools/call":
        result = {"content": [{"type": "text", "text": "pong"}]}
    elif mid is None:
        continue
    else:
        result = {}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}) + "\n")
    sys.stdout.flush()
