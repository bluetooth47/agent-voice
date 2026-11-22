"""Crew links and quarantine (master plan, M8): who may do what to whom.

Two settings, both read fresh by whoever decides (runtime.Config.crew_links
and .quarantined), and both lists in shell.json, by stable agent id ("main"
for the main agent):

- `crewLinks`: `[{"from": ID, "to": ID, "allow": [ABILITY, ...],
  "askFirst": BOOL}, ...]`. A link has a direction: Theo → Sora lets Theo
  reach Sora and nothing else. ABILITY is one of ABILITIES, each the right
  to one crew tool (TOOL_ABILITY).
- `crewQuarantine`: `[ID, ...]`, the agents held apart from the others.

What they mean, and this module is the one place it is decided:

- **No link, or a link that does not list the ability, is refused.** A
  missing or empty list is nobody linked: an agent can reach no other until
  the person links them (question 2's default).
- **A list that cannot be read is every agent-started call refused.** Not a
  list, an entry that is not exactly a link, an ability nobody knows, the
  same pair twice, a self-link, too many entries: `parse_links` returns
  None and says why. So does settings that cannot be read at all
  (Config.settings_readable). An unknown id is not malformed -- it is an
  agent that was removed -- and matches nothing.
- **Quarantine.** A quarantined agent starts nothing (its links out count
  for nothing), and a link into it carries only `ask` or `delegate`
  (INTO_QUARANTINE); anything else on it counts for nothing too. What a
  delegation into quarantine may carry, and what comes back, is collab.py's
  business (QUARANTINE_BRIEF_MAX, the "from a quarantined agent" mark).
- **askFirst** puts the approval card up for every call over that link,
  whatever the caller's own collaboration level says, except `off`, which
  still refuses.

Links are the rule for calls agents start. They combine with what existed
before them -- the target switched on and taking work, the caller's
collaboration level, depth, cycles, the rate, lock and stop -- and the
stricter always wins. A pass the *person* starts is not governed by links
(they are its approver), but a pass into quarantine is refused.

Pure, standard library only: the daemon, the crew server, the CLI and the
tests read the same rules, and the Crew map page's own copy is checked
against this one in node (tests/test_crew_links.py).
"""
from __future__ import annotations

import re

#: What a link may allow, in the order the page shows them.
ABILITIES = ("ask", "delegate", "message", "pass")
#: Which crew tool each ability is the right to use.
TOOL_ABILITY = {"ask_agent": "ask", "delegate": "delegate",
                "message_agent": "message", "pass_conversation": "pass"}
#: Which ability each collab.Task kind needs.
KIND_ABILITY = {"ask": "ask", "delegate": "delegate", "message": "message", "pass": "pass"}
#: What a link into a quarantined agent may carry: a question, answered in a
#: side conversation of its own, and a task, given the brief only.
INTO_QUARANTINE = ("ask", "delegate")
#: The most of a brief (the task and its summary, or the question and its
#: context, together) that goes into a quarantined agent.
QUARANTINE_BRIEF_MAX = 1000
#: Nine agents make 72 directed pairs; past this the list is not one anyone
#: wrote by hand or on the page.
LINKS_MAX = 128
QUARANTINE_MAX = 64
#: The keys a link has. Anything else makes the list unreadable: a guard
#: that cannot tell what an entry says closes rather than guesses.
LINK_KEYS = frozenset({"from", "to", "allow", "askFirst"})
_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")

#: The audit codes the refusals below carry (audit.REASONS has them).
CODES = ("no-link", "quarantined", "crew-unreadable")


def valid_id(value) -> bool:
    return isinstance(value, str) and bool(_ID.fullmatch(value))


def parse_links(raw) -> tuple[list[dict] | None, str]:
    """`crewLinks` as written, checked: (links, "") with each link
    normalised -- `allow` in ABILITIES order, `askFirst` a bool -- or (None,
    why) when the list cannot be read. A missing key is the default, [], by
    the time it gets here (runtime.DEFAULTS); a `null` written in its place
    is not a list, and so not readable."""
    if not isinstance(raw, list):
        return None, "crewLinks is not a list"
    if len(raw) > LINKS_MAX:
        return None, f"crewLinks has more than {LINKS_MAX} links"
    out, pairs = [], set()
    for i, e in enumerate(raw, 1):
        if not isinstance(e, dict):
            return None, f"link {i} is not an object"
        extra = set(e) - LINK_KEYS
        if extra:
            return None, f"link {i} has a key no link has ({sorted(extra)[0][:24]})"
        frm, to = e.get("from"), e.get("to")
        if not valid_id(frm) or not valid_id(to):
            return None, f"link {i} does not name two agents by id"
        if frm == to:
            return None, f"link {i} links an agent to itself"
        allow = e.get("allow")
        if not isinstance(allow, list) or not all(isinstance(a, str) for a in allow):
            return None, f"link {i} has no list of what it allows"
        unknown = [a for a in allow if a not in ABILITIES]
        if unknown:
            return None, f"link {i} allows something no link can ({unknown[0][:24]})"
        if len(set(allow)) != len(allow):
            return None, f"link {i} lists an ability twice"
        ask_first = e.get("askFirst", False)
        if not isinstance(ask_first, bool):
            return None, f"link {i}'s askFirst is not true or false"
        if (frm, to) in pairs:
            return None, f"link {i} repeats a link from {frm} to {to}"
        pairs.add((frm, to))
        out.append({"from": frm, "to": to,
                    "allow": [a for a in ABILITIES if a in allow],
                    "askFirst": ask_first})
    return out, ""


def parse_quarantine(raw) -> tuple[frozenset | None, str]:
    """`crewQuarantine` as written: (ids, "") or (None, why). Missing is
    the default, [], nobody quarantined; an id given twice is the same id."""
    if not isinstance(raw, list):
        return None, "crewQuarantine is not a list"
    if len(raw) > QUARANTINE_MAX:
        return None, f"crewQuarantine has more than {QUARANTINE_MAX} entries"
    for i, a in enumerate(raw, 1):
        if not valid_id(a):
            return None, f"quarantine entry {i} is not an agent id"
    return frozenset(raw), ""


class Crew:
    """One reading of the two settings. `ok` False (with `why`) when either
    could not be read: then nothing is allowed and everything says so."""

    def __init__(self, links: list[dict] | None, quarantined: frozenset | None,
                 why: str = "") -> None:
        self.ok = links is not None and quarantined is not None
        self.why = "" if self.ok else (why or "the crew settings could not be read")
        self.links = list(links or []) if self.ok else []
        self.quarantined = frozenset(quarantined or ()) if self.ok else frozenset()
        self._by_pair = {(e["from"], e["to"]): e for e in self.links}

    @classmethod
    def from_raw(cls, links_raw, quarantine_raw, readable: bool = True) -> "Crew":
        if not readable:
            return cls(None, None, "the settings could not be read")
        links, why_l = parse_links(links_raw)
        quarantined, why_q = parse_quarantine(quarantine_raw)
        return cls(links, quarantined, why_l or why_q)

    def is_quarantined(self, agent: str) -> bool:
        """Whether `agent` is held apart. Unreadable settings hold everyone:
        a guard asking this closes."""
        return (not self.ok) or agent in self.quarantined

    def link(self, frm: str, to: str) -> dict | None:
        return self._by_pair.get((frm, to)) if self.ok else None

    def abilities(self, frm: str, to: str) -> list[str]:
        """What `frm` may do to `to` as things stand: its link's abilities,
        none from a quarantined agent, only INTO_QUARANTINE into one."""
        e = self.link(frm, to)
        if e is None or frm == to or frm in self.quarantined:
            return []
        if to in self.quarantined:
            return [a for a in e["allow"] if a in INTO_QUARANTINE]
        return list(e["allow"])

    def allows(self, frm: str, to: str, ability: str) -> bool:
        return ability in self.abilities(frm, to)

    def asks_first(self, frm: str, to: str) -> bool:
        e = self.link(frm, to)
        return bool(e and e["askFirst"])

    def reach(self, frm: str) -> dict[str, list[str]]:
        """Every agent `frm` may do something to, with what."""
        out = {}
        for e in self.links:
            if e["from"] == frm:
                got = self.abilities(frm, e["to"])
                if got:
                    out[e["to"]] = got
        return out

    def reached_by(self, to: str) -> dict[str, list[str]]:
        out = {}
        for e in self.links:
            if e["to"] == to:
                got = self.abilities(e["from"], to)
                if got:
                    out[e["from"]] = got
        return out

    def starts_anything(self, frm: str) -> bool:
        """Whether `frm` has any way to reach anyone: what decides whether
        its crew server lists the collaboration tools at all."""
        return bool(self.reach(frm))


def everyone(ids) -> list[dict]:
    """"Link everyone as before": every ordered pair of `ids`, each allowing
    every ability, none asking first -- what collaboration was before M8."""
    ids = [a for a in dict.fromkeys(ids) if valid_id(a)]
    return [{"from": a, "to": b, "allow": list(ABILITIES), "askFirst": False}
            for a in ids for b in ids if a != b]


# --- what is said ------------------------------------------------------------

VERBS = {"ask": "ask", "delegate": "give a task to", "message": "leave a message for",
         "pass": "pass this conversation to"}


def refusal(crew: Crew, frm: str, to: str, ability: str, to_label: str) -> tuple[str, str]:
    """Why the crew settings refuse `frm` doing `ability` to `to`, as
    (sentence for the calling agent, audit code); ("", "") when they allow
    it. Run at request, at approval, when queued work starts and when its
    result is delivered (collab.py)."""
    if not crew.ok:
        return (f"The crew links can't be read ({crew.why}), so no agent may start anything "
                f"with another until they are fixed on the Crew map."), "crew-unreadable"
    if frm in crew.quarantined:
        return ("You are quarantined, so you can't start anything with other agents. The "
                "person can release you on the Crew map."), "quarantined"
    if crew.allows(frm, to, ability):
        return "", ""
    if to in crew.quarantined and crew.link(frm, to) and ability not in INTO_QUARANTINE:
        return (f"{to_label} is quarantined, so it can only be asked a question or given a "
                f"task, with the brief alone."), "quarantined"
    return (f"The Crew map has no link from you to {to_label} that lets you "
            f"{VERBS.get(ability, ability)} {to_label}, so nothing was sent."), "no-link"


def quarantined_line(label: str) -> str:
    """What is said when the person passes a conversation into quarantine."""
    return f"{label} is quarantined. Release it on the Crew map first."
