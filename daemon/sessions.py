"""Whether a conversation survives rebuilding an agent (bug I, phase M2).

An agent's adapter is rebuilt between turns when a setting it was started
with changes: its program, its project folder, its endpoint, its permission
level or its model. The rebuild itself stays: a new level means new flags,
and a warm process started under the old ones -- a trusted one that no
longer should be, or a guarded one that should no longer ask -- must not
take the next turn. What used to go with it was the conversation, so
flipping Ask to Trusted mid-chat left the agent unable to recall what it had
said a minute before (seen live on 2026-11-19 at 00:20:51; FINDINGS §41).

The rule, decided here so both rebuild paths (the main agent's and an extra
agent's) apply the same one:

- a different program, endpoint or project folder starts a new conversation.
  A CLI's session belongs to its program, and Claude Code scopes `--resume`
  to a folder; an endpoint keeps its history client-side, in the adapter
  being replaced;
- a different level or model keeps it, but only on a backend that has been
  shown to resume under the new flags: `carries_session_across` on the
  adapter, which a backend earns with a recorded real turn in
  `tests/fixtures/resume/` (the same rule as being offered at all);
- anything else starts a new one, and says why.

Pure, so the decision is tested apart from the daemon that acts on it.
"""
from __future__ import annotations

#: What can differ between the adapter being replaced and its replacement.
PROGRAM, ENDPOINT, FOLDER, LEVEL, MODEL, OTHER = (
    "program", "endpoint", "folder", "level", "model", "other")
#: Not a change: the reason a session that could have been kept was not --
#: an "allow all in this chat" made under the old level could not be
#: withdrawn (permission_hook.revoke), so the chat itself goes instead.
GRANTS = "grants"

#: A change that always ends the conversation, in the order they are named.
_ENDS = (PROGRAM, ENDPOINT, FOLDER, OTHER)


def carry(changed: set[str], carries: frozenset[str] | set[str]) -> tuple[bool, str]:
    """(keep the session, why not) for a rebuild that changed `changed`.

    `carries` is the new adapter's `carries_session_across`. The reason is
    one of the change names above, or "" when the session is kept."""
    for end in _ENDS:
        if end in changed:
            return False, end
    unproven = set(changed) - set(carries)
    if unproven:
        return False, LEVEL if LEVEL in unproven else MODEL
    return True, ""


def spec_changes(before: dict, after: dict) -> set[str]:
    """What differs between two extra-agent specs, as change names.

    Only the fields that force a rebuild reach here (the daemon keeps the
    rest on the running adapter); anything it does not know is OTHER, which
    ends the conversation -- the direction a new field should fail in."""
    names = {"agent": PROGRAM, "endpoint": ENDPOINT, "projectDir": FOLDER,
             "level": LEVEL, "model": MODEL}
    out = set()
    for key in set(before) | set(after):
        if before.get(key) != after.get(key):
            out.add(names.get(key, OTHER))
    return out


def why(reason: str, program: str = "") -> str:
    """The reason in words, for the journal and the readout. Never any text
    from the conversation itself."""
    program = program or "this program"
    return {
        PROGRAM: "it runs on a different program now",
        ENDPOINT: "its endpoint changed",
        FOLDER: "its project folder changed",
        LEVEL: f"{program} cannot carry a chat across a permission change",
        MODEL: f"{program} cannot carry a chat across a model change",
        OTHER: "its settings changed",
        GRANTS: "its old permissions could not be withdrawn",
    }.get(reason, "its settings changed")
