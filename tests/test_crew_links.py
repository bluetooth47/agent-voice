"""Crew links and quarantine (master plan M8): the rules, the settings that
hold them, and the Crew map page's copy of them.

What has to hold:

- no link, an empty or missing list, is nothing allowed; a link allows only
  what it lists, in its own direction;
- a list that cannot be read -- not a list, an entry that is not exactly a
  link, an unknown ability, a pair twice, a self-link, too long, `null`,
  settings that cannot be read at all -- allows nothing, and says why;
- a quarantined agent starts nothing, and a link into one carries only ask
  and delegate;
- "Link everyone as before" is every ordered pair, everything allowed;
- the page reads the lists exactly as the daemon does, and each of its
  edits writes exactly the list it says (run in node, as test_agents_page
  runs the Agents page).

The daemon's use of all this -- the four checks, the sweep, quarantine
carried out -- is driven end to end in test_collab.py, section M8.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import crew_links
from crew_links import ABILITIES, Crew, everyone, parse_links, parse_quarantine

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "pages" / "CrewMapPage.qml"


def link(frm, to, allow=("ask",), **kw):
    return {"from": frm, "to": to, "allow": list(allow), **kw}


# --- reading the list --------------------------------------------------------------

def test_a_good_list_is_normalised():
    links, why = parse_links([link("main", "sora", ["pass", "ask"]),
                              link("sora", "main", [], askFirst=True)])
    assert why == ""
    assert links == [{"from": "main", "to": "sora", "allow": ["ask", "pass"], "askFirst": False},
                     {"from": "sora", "to": "main", "allow": [], "askFirst": True}]


UNREADABLE = [
    None, "everyone", {"from": "main"}, 3,
    ["not a link"],
    [link("main", "sora") | {"note": "hi"}],              # a key no link has
    [{"to": "sora", "allow": ["ask"]}],                    # no from
    [link("Main", "sora")],                                # not an id
    [link("main", "main")],                                # itself
    [{"from": "main", "to": "sora"}],                      # no allow
    [{"from": "main", "to": "sora", "allow": "ask"}],      # allow not a list
    [link("main", "sora", ["ask", "shout"])],              # unknown ability
    [link("main", "sora", ["ask", "ask"])],                # twice
    [link("main", "sora", ["ask"], askFirst="yes")],       # askFirst not a bool
    [link("main", "sora"), link("main", "sora", ["pass"])],   # the pair twice
    [link("a", f"b{i}") for i in range(crew_links.LINKS_MAX + 1)],
]


@pytest.mark.parametrize("raw", UNREADABLE, ids=range(len(UNREADABLE)))
def test_anything_but_a_list_of_links_is_unreadable_and_says_why(raw):
    links, why = parse_links(raw)
    assert links is None and why


def test_an_unknown_id_is_not_malformed_it_matches_nothing():
    links, why = parse_links([link("main", "gone")])
    assert why == "" and Crew(links, frozenset()).abilities("main", "sora") == []


@pytest.mark.parametrize("raw", [None, "sora", ["Sora"], [1], ["x"] * (crew_links.QUARANTINE_MAX + 1)])
def test_a_quarantine_list_that_is_not_ids_is_unreadable(raw):
    ids, why = parse_quarantine(raw)
    assert ids is None and why


def test_a_quarantine_id_twice_is_one_id():
    assert parse_quarantine(["sora", "sora"]) == (frozenset({"sora"}), "")


# --- what a link allows --------------------------------------------------------------

def test_direction_and_ability_both_matter():
    crew = Crew.from_raw([link("main", "sora", ["delegate"])], [])
    assert crew.allows("main", "sora", "delegate")
    assert not crew.allows("main", "sora", "ask")
    assert not crew.allows("sora", "main", "delegate")
    assert crew.reach("main") == {"sora": ["delegate"]} and crew.reach("sora") == {}
    assert crew.reached_by("sora") == {"main": ["delegate"]}


def test_nobody_linked_allows_nothing():
    for raw in ([], ):
        crew = Crew.from_raw(raw, [])
        assert crew.ok and not any(crew.allows(a, b, x) for a in ("main", "sora")
                                   for b in ("main", "sora") for x in ABILITIES)


def test_quarantine_out_is_nothing_and_in_is_ask_or_delegate():
    crew = Crew.from_raw(everyone(["main", "sora"]), ["sora"])
    assert crew.abilities("sora", "main") == []
    assert crew.abilities("main", "sora") == ["ask", "delegate"]
    assert not crew.starts_anything("sora") and crew.starts_anything("main")


def test_unreadable_allows_nothing_and_holds_everyone_apart():
    for crew in (Crew.from_raw("x", []), Crew.from_raw([], "x"),
                 Crew.from_raw(everyone(["main", "sora"]), [], readable=False)):
        assert not crew.ok and crew.why
        assert crew.abilities("main", "sora") == [] and crew.is_quarantined("main")
        why, code = crew_links.refusal(crew, "main", "sora", "ask", "Sora")
        assert code == "crew-unreadable" and "can't be read" in why


def test_ask_first_is_per_link():
    crew = Crew.from_raw([link("main", "sora", askFirst=True), link("sora", "main")], [])
    assert crew.asks_first("main", "sora") and not crew.asks_first("sora", "main")


def test_link_everyone_is_every_ordered_pair_with_everything():
    got = everyone(["main", "sora", "hazel", "sora", "Bad"])
    assert len(got) == 6
    assert {(e["from"], e["to"]) for e in got} == {
        (a, b) for a in ("main", "sora", "hazel") for b in ("main", "sora", "hazel") if a != b}
    assert all(e["allow"] == list(ABILITIES) and e["askFirst"] is False for e in got)
    assert parse_links(got) == (got, "")


@pytest.mark.parametrize("case,code", [
    (dict(links=[], q=[], frm="main"), "no-link"),
    (dict(links=[link("main", "sora", ["pass"])], q=[], frm="main"), "no-link"),
    (dict(links=[link("main", "sora")], q=["main"], frm="main"), "quarantined"),
    (dict(links=[link("main", "sora", ["message"])], q=["sora"], frm="main", ab="message"),
     "quarantined"),
    (dict(links=[link("main", "sora")], q=[], frm="main"), ""),
])
def test_each_refusal_has_its_code_and_a_sentence(case, code):
    crew = Crew.from_raw(case["links"], case["q"])
    why, got = crew_links.refusal(crew, case["frm"], "sora", case.get("ab", "ask"), "Sora")
    assert got == code and bool(why) == bool(code)
    if code == "no-link":
        assert "no link from you to Sora" in why


def test_the_audit_log_takes_every_code():
    import audit
    assert set(crew_links.CODES) <= audit.REASONS


# --- the settings ---------------------------------------------------------------------

def test_missing_keys_are_nobody_linked_and_nobody_held(cfg_factory):
    cfg = cfg_factory()
    crew = cfg.crew()
    assert crew.ok and crew.links == [] and crew.quarantined == frozenset()
    assert cfg.crew_links() == [] and cfg.quarantined() == frozenset()


def test_null_in_place_of_a_list_is_unreadable(cfg_factory):
    assert cfg_factory(crewLinks=None).crew_links() is None
    assert cfg_factory(crewQuarantine=None).quarantined() is None


def test_a_broken_or_doubled_shell_json_is_unreadable(tmp_path, monkeypatch):
    import runtime
    shell = tmp_path / "shell.json"
    monkeypatch.setattr(runtime, "SHELL_JSON", shell)
    entry = ('{"id": "duaneoca.agentvoice", "crewLinks": [{"from": "main", "to": "sora", '
             '"allow": ["ask"]}]%s}')
    shell.write_text('{"bar": {"layout": {"right": [' + entry % "" + ']}}}')
    cfg = runtime.Config()
    assert cfg.crew().allows("main", "sora", "ask")
    shell.write_text('{"bar": {"layout": {"right": [' + entry % ', "crewLinks": []' + ']}}}')
    cfg = runtime.Config()
    assert not cfg.crew().ok, "a key given twice says two things"
    shell.write_text('{"bar": ')
    assert not runtime.Config().crew().ok
    assert runtime.Config().quarantined() is None


# --- the page's copy, run in node -------------------------------------------------------

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed, so the page's JavaScript cannot be run")

PAGE_FUNCTIONS = ["validId", "parseLinks", "parseQuarantine", "isQuarantined", "linkOf",
                  "effectiveOf", "reachOf", "reachedBy", "everyoneLinks", "copyLinks", "withLink",
                  "withAbility", "withAskFirst", "withoutLink", "quarantineLoses",
                  "linksQuarantining"]


def page_js(calls: str, links_raw, quarantine_raw) -> object:
    from test_agents_page import function_source, run_js
    fns = "\n".join(function_source(PAGE, n) for n in PAGE_FUNCTIONS)
    script = f"""
var page = {{ abilities: ["ask", "delegate", "message", "pass"], intoQuarantine: ["ask", "delegate"] }};
{fns}
page.validId = validId; page.isQuarantined = isQuarantined; page.linkOf = linkOf;
page.effectiveOf = effectiveOf;
var rl = parseLinks({json.dumps(links_raw)}), rq = parseQuarantine({json.dumps(quarantine_raw)});
page.readable = rl.links !== null && rq.ids !== null;
page.links = rl.links || []; page.quarantine = rq.ids || [];
process.stdout.write(JSON.stringify((function() {{ {calls} }})()));
"""
    return run_js(script)


CASES = [
    ([], []),
    (everyone(["main", "sora", "hazel"]), []),
    (everyone(["main", "sora", "hazel"]), ["sora"]),
    ([link("main", "sora", ["delegate", "message"], askFirst=True), link("sora", "hazel", ["pass"])],
     ["hazel"]),
] + [(raw, []) for raw in UNREADABLE if raw is not None] + [([], "x"), ([], ["Bad"])]


@needs_node
@pytest.mark.parametrize("links_raw,q_raw", CASES, ids=range(len(CASES)))
def test_the_page_reads_the_lists_as_the_daemon_does(links_raw, q_raw):
    ids = ["main", "sora", "hazel"]
    got = page_js(f"""
      var out = {{ links: rl.links, linksWhy: rl.why !== "", q: rq.ids, qWhy: rq.why !== "", eff: {{}} }};
      var ids = {json.dumps(ids)};
      for (var i = 0; i < ids.length; i++) for (var j = 0; j < ids.length; j++)
        out.eff[ids[i] + ">" + ids[j]] = effectiveOf(ids[i], ids[j]);
      return out;""", links_raw, q_raw)
    links, why_l = parse_links(links_raw)
    q, why_q = parse_quarantine(q_raw)
    assert got["links"] == links and got["linksWhy"] == bool(why_l)
    assert (got["q"] is None) == (q is None) and set(got["q"] or []) == set(q or [])
    assert got["qWhy"] == bool(why_q)
    crew = Crew.from_raw(links_raw, q_raw)
    for a in ids:
        for b in ids:
            assert got["eff"][f"{a}>{b}"] == crew.abilities(a, b), (a, b)


@needs_node
def test_each_edit_writes_exactly_the_list_it_says():
    """What the clicks write: the whole list, every other link untouched,
    and each result a list the daemon reads."""
    start = [link("main", "sora", ["ask", "pass"]), link("sora", "main", ["message"], askFirst=True)]
    got = page_js("""return {
        add: withLink("main", "hazel"), addAgain: withLink("main", "sora"),
        addSelf: withLink("sora", "sora"),
        on: withAbility("main", "sora", "delegate", true),
        off: withAbility("main", "sora", "pass", false),
        first: withAskFirst("main", "sora", true),
        del: withoutLink("sora", "main"),
        everyone: everyoneLinks(["main", "sora"]),
        quarantine: linksQuarantining("sora"), loses: quarantineLoses("sora") };""",
                  start, [])
    norm = parse_links(start)[0]
    assert got["add"] == norm + [{"from": "main", "to": "hazel", "allow": ["ask"], "askFirst": False}]
    assert got["addAgain"] == norm and got["addSelf"] == norm
    assert got["on"][0]["allow"] == ["ask", "delegate", "pass"] and got["on"][1] == norm[1]
    assert got["off"][0]["allow"] == ["ask"] and got["off"][1] == norm[1]
    assert got["first"][0]["askFirst"] is True and got["first"][1] == norm[1]
    assert got["del"] == [norm[0]]
    assert got["everyone"] == everyone(["main", "sora"])
    # Quarantining Sora: its link out goes, its link in keeps only ask.
    assert got["quarantine"] == [{"from": "main", "to": "sora", "allow": ["ask"], "askFirst": False}]
    assert got["loses"] == {"out": 1, "trimmed": 1}
    for k, v in got.items():
        if isinstance(v, list):
            assert parse_links(v)[1] == "", k


def test_the_page_writes_each_key_in_one_function_only():
    """writeLinks and writeQuarantine are the only writes, so the map (M9)
    and the table cannot drift apart."""
    from qml_scan import scan
    s = scan(PAGE)
    for key, fn in (("crewLinks", "function writeLinks"), ("crewQuarantine", "function writeQuarantine")):
        found = [s.handler_of(m.start()) for m in re.finditer(r'\bput\("' + key + '"', s.nocomment)]
        assert found == [fn], (key, found)


def test_quarantine_is_written_before_the_links_it_trims():
    src = PAGE.read_text()
    body = src[src.index("function quarantineAgent("):]
    body = body[:body.index("\n  }")]
    assert body.index("writeQuarantine(") < body.index("writeLinks(")


def test_the_send_sheet_will_not_send_into_quarantine():
    """The sheet says why and keeps Send greyed; send() refuses too, for an
    Enter that reaches it some other way. The daemon refuses it anyway."""
    from qml_scan import scan
    s = scan(ROOT / "ui" / "SendSheet.qml")
    send = s.src[s.src.index("function send()"):]
    send = send[:send.index("\n  }")]
    assert 'sheet.denied !== ""' in send.split("\n")[1]
    button = s.src[s.src.index('text: sheet.sending ? "Sending…" : "Send"'):]
    assert 'sheet.denied === ""' in button[:button.index("onClicked")]
    q = s.src[s.src.index("function quarantined("):]
    q = q[:q.index("\n  }")]
    assert "!Array.isArray(q) ||" in q, "an unreadable list denies"
