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

And for the drawn map (M9): nothing the page saves skips the daemon's own
validator (`agentvoice crew check`, crew_links.check_write), which refuses
duplicates, self-links, ids nobody has (removed or renamed) unless that link
was already saved, abilities that cannot go into quarantine, links out of
it, and an oversize list; the page trims what quarantine lets a link carry
before asking, so the map and the table never trip it by themselves; and
the layout file the map keeps is never read by the daemon.
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


def test_a_broken_link_list_leaves_the_quarantine_readable(cfg_factory):
    """Found live in M8: a malformed crewLinks made quarantined() None,
    which hid every agent's crew tools -- no call could then say it was
    refused -- and refused every agent's communal notes."""
    cfg = cfg_factory(crewLinks="broken by hand", crewQuarantine=["sora"])
    assert not cfg.crew().ok
    assert cfg.quarantined() == frozenset({"sora"})
    import crew_mcp
    assert crew_mcp.offers_collab(cfg, "") and not crew_mcp.offers_collab(cfg, "sora")


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
                  "linksQuarantining", "trimmed", "withReverse", "parseLayout"]


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


def _body(src: str, name: str) -> str:
    body = src[src.index(f"function {name}("):]
    return body[:body.index("\n  }")]


def test_quarantine_is_written_before_the_links_it_trims():
    """applyChecked is where both are written; the quarantine goes first, so
    the daemon holds the agent apart before its links change."""
    body = _body(PAGE.read_text(), "applyChecked")
    assert body.index("writeQuarantine(") < body.index("writeLinks(")
    assert "quarantine.concat([id])" in _body(PAGE.read_text(), "quarantineAgent")


# --- M9: nothing is saved that the daemon's validator did not take ----------------------

def test_the_two_writes_are_reached_only_from_what_the_validator_took():
    """writeLinks and writeQuarantine are called from applyChecked alone;
    applyChecked from checked() alone, which reads `agentvoice crew check`'s
    answer; and the only process the page starts with that command is the
    checker. So the map, the table and anything added later save only a
    list the daemon's own validator accepted."""
    from qml_scan import scan
    s = scan(PAGE)
    for fn, caller in (("writeLinks", "function applyChecked"), ("writeQuarantine", "function applyChecked"),
                       ("applyChecked", "function checked"), ("checked", None)):
        calls = [m.start() for m in re.finditer(r"\b(?:page\.)?" + fn + r"\(", s.nocomment)
                 if not s.nocomment[max(0, m.start() - 9):m.start()].endswith("function ")]
        where = [s.handler_of(i) for i in calls]
        if caller:
            assert where == [caller] * len(where) and where, (fn, where)
        else:
            assert len(calls) == 1, (fn, where)
    checker = s.nocomment[s.nocomment.index("id: checker"):]
    checker = checker[:checker.index("\n  }")]
    assert 'command: ["agentvoice", "crew", "check"]' in checker
    assert "page.checked(h, checker.out, checker.code)" in checker
    assert s.nocomment.count('"crew", "check"') == 1


def test_every_edit_goes_through_commit():
    """Each edit the map or the table makes builds both lists and hands
    them to commit(); none writes, or queues, by itself."""
    src = PAGE.read_text()
    for name in ("quarantineAgent", "releaseAgent", "linkEveryone", "removeLink", "addLink",
                 "setAbility", "setAskFirst", "addReverse", "clearUnreadable"):
        body = _body(src, name)
        assert "commit(" in body, name
        assert "put(" not in body and "page.queue" not in body, name
    # And the controls reach the edits, never the writes.
    from qml_scan import scan
    ui = scan(PAGE).nocomment
    ui = ui[ui.index("PageHeader {"):]
    assert "writeLinks(" not in ui and "writeQuarantine(" not in ui and "put(" not in ui


def test_a_refused_check_drops_every_edit_built_on_it():
    body = _body(PAGE.read_text(), "refused")
    assert "page.queue = []" in body and "Not saved" in body
    checked = _body(PAGE.read_text(), "checked")
    # Anything but {"ok": true, both lists} is a refusal: an empty answer, a
    # crash, a non-JSON line.
    assert "d.ok !== true" in checked and "refused(" in checked
    # A checker that never started says so, and saves nothing.
    src = PAGE.read_text()
    proc = src[src.index("id: checker"):]
    assert "!launched" in proc[:proc.index("stdout:")] and "page.refused(" in proc[:proc.index("stdout:")]


KNOWN = ["main", "sora", "hazel"]


def test_the_validator_takes_a_good_pair_and_normalises_it():
    got, why = crew_links.check_write([link("main", "sora", ["pass", "ask"])], ["hazel"], KNOWN)
    assert why == ""
    assert got == {"crewLinks": [{"from": "main", "to": "sora", "allow": ["ask", "pass"], "askFirst": False}],
                   "crewQuarantine": ["hazel"]}
    assert crew_links.check_write([], [], KNOWN) == ({"crewLinks": [], "crewQuarantine": []}, "")


@pytest.mark.parametrize("links,q,needle", [
    ([link("main", "sora"), link("main", "sora", ["delegate"])], [], "repeats a link"),
    ([link("sora", "sora")], [], "itself"),
    ([link("main", "nobody")], [], "nobody, which is no agent here now"),
    ([link("ghost", "main")], [], "ghost, which is no agent here now"),
    ([link("main", "hazel", ["ask", "message"])], ["hazel"], "only ask and delegate go in"),
    ([link("main", "hazel", ["pass"])], ["hazel"], "only ask and delegate go in"),
    ([link("hazel", "main", ["ask"])], ["hazel"], "quarantined and so starts nothing"),
    ([link("hazel", "main", [])], ["hazel"], "quarantined and so starts nothing"),
    ([link("main", "sora")] * 0 + [link(f"a{i}", f"b{i}") for i in range(129)], [], "more than 128"),
    ("all", [], "not a list"),
    ([link("main", "sora", ["fly"])], [], "no link can"),
    ([], ["nobody"], "the quarantine names nobody"),
    ([], "hazel", "not a list"),
    ([], ["Hazel"], "not an agent id"),
    ([], ["hazel", "hazel"], "names an agent twice"),
], ids=["duplicate", "self", "unknown-to", "unknown-from", "message-into-q", "pass-into-q",
        "out-of-q", "empty-out-of-q", "oversize", "not-a-list", "unknown-ability",
        "unknown-quarantine", "quarantine-not-a-list", "quarantine-bad-id", "quarantine-twice"])
def test_the_validator_refuses_and_says_why(links, q, needle):
    got, why = crew_links.check_write(links, q, KNOWN)
    assert got is None and needle in why, why


def test_an_id_left_by_a_rename_is_refused_unless_it_was_already_saved():
    """An agent saved without an id takes its id from its wake phrase, so a
    rename changes it: a link written to the old id is refused, while one
    already saved naming it (which matches nothing) does not block every
    other edit until it is deleted."""
    stale = link("main", "sora")
    known = ["main", "sky", "hazel"]          # Sora renamed Sky
    assert crew_links.check_write([stale], [], known)[0] is None
    got, why = crew_links.check_write([stale, link("main", "hazel")], [], known, saved_links=[stale])
    assert why == "" and len(got["crewLinks"]) == 2
    # It may narrow as saved, never widen: the id could come back, and a
    # link to it would then carry what was added (Codex review of M9).
    wide = link("main", "sora", ["ask", "pass"], askFirst=True)
    assert crew_links.check_write([link("main", "sora", ["pass"], askFirst=True)], [], known, saved_links=[wide])[1] == ""
    assert crew_links.check_write([link("main", "sora", [])], [], known, saved_links=[stale])[1] == ""
    assert crew_links.check_write([link("main", "sora", ["delegate"])], [], known, saved_links=[stale])[0] is None
    assert crew_links.check_write([link("main", "sora", ["ask"])], [], known, saved_links=[wide])[0] is None, \
        "dropping ask-first widens it"
    # A new link to the same old id is not carried over.
    assert crew_links.check_write([link("hazel", "sora")], [], known, saved_links=[stale])[0] is None
    # The quarantine the same way.
    assert crew_links.check_write([], ["sora"], known)[0] is None
    assert crew_links.check_write([], ["sora"], known, saved_quarantine=["sora"])[1] == ""
    # Saved lists that cannot be read carry nothing over.
    assert crew_links.check_write([stale], [], known, saved_links="junk")[0] is None


def test_what_the_validator_takes_the_daemon_reads_the_same():
    raw = [link("main", "sora", ["delegate", "ask"], askFirst=True), link("sora", "hazel", ["ask"])]
    got, _ = crew_links.check_write(raw, ["hazel"], KNOWN)
    crew = Crew.from_raw(got["crewLinks"], got["crewQuarantine"])
    want = Crew.from_raw(raw, ["hazel"])
    for a in KNOWN:
        for b in KNOWN:
            assert crew.abilities(a, b) == want.abilities(a, b)
            assert crew.asks_first(a, b) == want.asks_first(a, b)


class _Cfg:
    def __init__(self, agents=("sora", "hazel"), links=None, quarantine=None, readable=True):
        self._agents = [{"id": a} for a in agents]
        self._vals = {"crewLinks": links if links is not None else [],
                      "crewQuarantine": quarantine if quarantine is not None else []}
        self._readable = readable

    def settings_readable(self):
        return self._readable

    def all_agents(self):
        return self._agents

    def __getitem__(self, key):
        return self._vals[key]


def _crew_cli(line, cfg=None, args=("check",)):
    import io

    import collab
    out, err = io.StringIO(), io.StringIO()
    code = collab.cli_crew(list(args), io.StringIO(line), out, err, cfg=cfg or _Cfg())
    return code, out.getvalue(), err.getvalue()


def test_crew_check_says_yes_with_the_normalised_lists():
    code, out, _ = _crew_cli(json.dumps({"crewLinks": [link("sora", "main", ["pass", "ask"])],
                                         "crewQuarantine": []}) + "\n")
    assert code == 0
    assert json.loads(out) == {"ok": True, "crewLinks": [{"from": "sora", "to": "main", "allow": ["ask", "pass"],
                                                          "askFirst": False}], "crewQuarantine": []}


@pytest.mark.parametrize("line,cfg,needle", [
    ("", None, "not JSON"),
    ("not json\n", None, "not JSON"),
    ('["crewLinks"]\n', None, "not the two crew lists"),
    ('{"crewLinks": []}\n', None, "not the two crew lists"),
    ('{"crewLinks": [], "crewQuarantine": [], "more": 1}\n', None, "not the two crew lists"),
    ('{"crewLinks": [], "crewQuarantine": []}\n', _Cfg(readable=False), "can't be read"),
    (json.dumps({"crewLinks": [link("main", "zed")], "crewQuarantine": []}) + "\n", None, "zed"),
    ('{"crewLinks": [' + ",".join(['{"from": "main", "to": "sora", "allow": []}'] * 4000) + '], "crewQuarantine": []}\n',
     None, "too long"),
    # Nested past the parser's recursion limit, under the size limit: a
    # refusal either way, never a traceback (Codex review of M9).
    ("[" * 30000 + "]" * 30000 + "\n", None, "not"),
], ids=["empty", "not-json", "a-list", "one-key", "extra-key", "unreadable", "unknown-id", "too-long",
        "nested-deep"])
def test_crew_check_refuses_on_stdout_and_exits_1(line, cfg, needle):
    code, out, _ = _crew_cli(line, cfg)
    d = json.loads(out)
    assert code == 1 and d["ok"] is False and needle in d["why"], d


def test_crew_check_checks_against_what_is_saved():
    stale = link("main", "gone")
    line = json.dumps({"crewLinks": [stale], "crewQuarantine": []}) + "\n"
    assert _crew_cli(line)[0] == 1
    assert _crew_cli(line, _Cfg(links=[stale]))[0] == 0


def test_crew_check_takes_only_check():
    for args in ((), ("set",), ("check", "extra")):
        code, out, err = _crew_cli("{}\n", args=args)
        assert code == 2 and out == "" and "usage" in err


def test_agentvoice_crew_check_runs_the_daemons_validator(tmp_path):
    """Through bin/agentvoice, as the page runs it: stdin in, JSON out, no
    daemon needed and nothing written."""
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path / "cfg"),
           "XDG_RUNTIME_DIR": str(tmp_path / "run"), "PYTHONDONTWRITEBYTECODE": "1",
           "AGENTVOICE_PYTHON": __import__("sys").executable}
    ok = subprocess.run([str(ROOT / "bin" / "agentvoice"), "crew", "check"], env=env, text=True,
                        input='{"crewLinks": [], "crewQuarantine": []}\n', capture_output=True, timeout=30)
    assert ok.returncode == 0 and json.loads(ok.stdout)["ok"] is True, ok.stderr
    no = subprocess.run([str(ROOT / "bin" / "agentvoice"), "crew", "check"], env=env, text=True,
                        input=json.dumps({"crewLinks": [link("main", "sora")], "crewQuarantine": []}) + "\n",
                        capture_output=True, timeout=30)
    assert no.returncode == 1 and "sora" in json.loads(no.stdout)["why"]
    assert sorted(p.name for p in tmp_path.iterdir()) == [], "it wrote nothing"


@needs_node
def test_the_page_trims_for_quarantine_and_the_validator_takes_every_edit():
    """Every edit the page can make, from every starting list, trimmed as
    commit() trims it, is a pair the validator accepts -- so neither the
    map nor the table is refused for something the person did not do."""
    for links_raw, q_raw in CASES[:4]:
        q = parse_quarantine(q_raw)[0]
        q = sorted(q) if q is not None else None
        if q is None or parse_links(links_raw)[0] is None:
            continue
        got = page_js(f"""
          var q = {json.dumps(q)}, ids = ["main", "sora", "hazel"], out = [];
          page.quarantine = q;
          var edits = [copyLinks(), everyoneLinks(ids)];
          for (var i = 0; i < ids.length; i++) for (var j = 0; j < ids.length; j++) {{
            edits.push(withLink(ids[i], ids[j])); edits.push(withoutLink(ids[i], ids[j]));
            edits.push(withReverse(ids[i], ids[j])); edits.push(withAskFirst(ids[i], ids[j], true));
            for (var k = 0; k < page.abilities.length; k++) edits.push(withAbility(ids[i], ids[j], page.abilities[k], true));
          }}
          for (var e = 0; e < edits.length; e++) out.push(trimmed(edits[e], q));
          // quarantineAgent never quarantines an agent twice.
          for (var h = 0; h < ids.length; h++) out.push(trimmed(linksQuarantining(ids[h]), q.indexOf(ids[h]) < 0 ? q.concat([ids[h]]) : q));
          return out;""", links_raw, q_raw)
        for i, edit in enumerate(got):
            extra = [] if i < len(got) - 3 else [KNOWN[i - (len(got) - 3)]]
            held = q + [a for a in extra if a not in q]
            assert crew_links.check_write(edit, held, KNOWN)[1] == "", (links_raw, q, edit)


@needs_node
def test_the_reverse_copies_the_link_the_other_way_and_only_once():
    start = [link("main", "sora", ["ask", "pass"], askFirst=True), link("sora", "hazel", ["ask"]),
             link("hazel", "sora", ["message"])]
    got = page_js("""return { rev: withReverse("main", "sora"), again: withReverse("sora", "hazel"),
                             none: withReverse("main", "hazel"),
                             trim: trimmed([{from: "main", to: "sora", allow: ["ask", "message"], askFirst: false},
                                            {from: "sora", to: "main", allow: ["ask"], askFirst: true}], ["sora"]) };""",
                  start, [])
    norm = parse_links(start)[0]
    assert got["rev"] == norm + [{"from": "sora", "to": "main", "allow": ["ask", "pass"], "askFirst": True}]
    assert got["again"] == norm and got["none"] == norm
    assert got["trim"] == [{"from": "main", "to": "sora", "allow": ["ask"], "askFirst": False}]


@needs_node
@pytest.mark.parametrize("text,want", [
    ('{"version": 1, "spots": {"main": {"x": 0.5, "y": 0.25}}}', {"main": {"x": 0.5, "y": 0.25}}),
    ('{"spots": {"main": {"x": 1.5, "y": 0.2}, "Bad": {"x": 0.1, "y": 0.1}, "ok": {"x": 0, "y": 1}}}',
     {"ok": {"x": 0, "y": 1}}),
    ('{"spots": {"main": {"x": "0.5", "y": 0.2}, "sora": [0.1, 0.2]}}', {}),
    ('{"spots": [1, 2]}', {}),
    ("not json", {}),
    ("", {}),
    ('{"spots": {"main": {"x": 0.1, "y": 0.1}}}' + " " * 70000, {}),
])
def test_the_layout_file_is_read_as_positions_or_not_at_all(text, want):
    assert page_js(f"return parseLayout({json.dumps(text)});", [], []) == want


def test_the_daemon_never_reads_the_map_layout():
    """Where the boxes sit is the page's alone: no daemon module, script or
    installer names the file, so dragging a box can never change a
    decision."""
    hits = []
    for path in list((ROOT / "daemon").rglob("*.py")) + list((ROOT / "bin").iterdir()) + [ROOT / "install.sh"]:
        if path.is_file() and "crew-layout" in path.read_text(errors="replace"):
            hits.append(str(path.relative_to(ROOT)))
    assert hits == []
    src = PAGE.read_text()
    assert '"/agentvoice/crew-layout.json"' in src and "XDG_STATE_HOME" in src
    assert "crew-layout" not in (ROOT / "manifest.json").read_text()


def test_the_map_draws_with_the_crew_edge_and_hands_drops_to_the_page():
    from qml_scan import scan
    s = scan(PAGE).nocomment
    assert "CrewEdge {" in s and "drag.target: node" in s and "preventStealing: true" in s
    # A drop into the zone only asks: quarantine itself comes from the
    # confirm (test_confirms holds quarantineAgent to onConfirmed).
    dropped = _body(PAGE.read_text(), "dropped")
    assert "quarantineAgent(" not in dropped and "pendingQuarantine = id" in dropped
    assert "releaseAgent(id)" in dropped


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


# --- the page's save queue, run in node (M9, and Codex review pass 1) -------------------

QUEUE_FUNCTIONS = ["trimmed", "savedPair", "rawOf", "crewSettling", "commit", "nextCheck", "checked", "refused",
                   "applyChecked", "writeLinks", "writeQuarantine"]


def queue_js(calls: str, cfg: dict) -> object:
    """The page's commit -> check -> apply path against a fake overlay whose
    put() records each write and applies it, and a fake checker that only
    records what it was asked to run. `calls` drives it and returns a value."""
    from test_agents_page import function_source, run_js
    fns = "\n".join(function_source(PAGE, n) for n in QUEUE_FUNCTIONS)
    canon = function_source(ROOT / "Settings.qml", "crewCanon")
    script = f"""
{canon}
var writes = [], runs = [];
var page = {{ intoQuarantine: ["ask", "delegate"], queue: [], saveNote: "", expectSaved: "",
              pendingQuarantine: "", lastAction: "",
              s: {{ cfg: {json.dumps(cfg)}, crewCanon: crewCanon, crewOwnWrite: function() {{}}, store: {{ pending: {{}} }},
                    put: function(k, v) {{ writes.push([k, v]); page.s.cfg[k] = v }} }} }};
var checker = {{ running: false, head: null, launched: false, pending: "", out: "", gotOut: false,
                gotExit: false, code: -1 }};
Object.defineProperty(checker, "running", {{ get: function() {{ return this._r || false }},
  set: function(v) {{ this._r = v; if (v) runs.push(JSON.parse(this.pending)) }} }});
{fns}
page.trimmed = trimmed; page.nextCheck = nextCheck; page.refused = refused; page.crewSettling = crewSettling;
// The checker finishing: what the process printed and its exit status.
function finish(out, code) {{
  var h = checker.head; checker.running = false; checker.head = null;
  checked(h, out, code); nextCheck();
}}
function yes() {{ var r = runs[runs.length - 1]; return JSON.stringify({{ ok: true, crewLinks: r.crewLinks, crewQuarantine: r.crewQuarantine }}) }}
process.stdout.write(JSON.stringify((function() {{ {calls} }})()));
"""
    return run_js(script)


L1 = [link("main", "sora", ["ask"])]


@needs_node
def test_two_quick_edits_are_checked_and_saved_in_order():
    got = queue_js("""
      commit([{from: "main", to: "sora", allow: ["ask"], askFirst: false}], [], "one");
      commit([{from: "main", to: "sora", allow: ["ask", "pass"], askFirst: false}], [], "two");
      var before = runs.length;
      finish(yes(), 0);              // the first answer starts the second check
      var between = runs.length;
      finish(yes(), 0);
      return { before: before, between: between, runs: runs.length, writes: writes, queue: page.queue.length, note: page.saveNote };""",
                   {})
    assert got["before"] == 1 and got["between"] == 2 and got["runs"] == 2
    assert [w[1][0]["allow"] for w in got["writes"]] == [["ask"], ["ask", "pass"]]
    assert got["queue"] == 0 and got["note"] == ""


@needs_node
def test_a_check_that_prints_yes_and_fails_saves_nothing():
    got = queue_js("""
      commit([{from: "main", to: "sora", allow: ["ask"], askFirst: false}], [], "one");
      commit([], [], "two");
      finish(yes(), 1);
      return { writes: writes, queue: page.queue.length, note: page.saveNote, runs: runs.length };""", {})
    assert got["writes"] == [] and got["queue"] == 0 and got["runs"] == 1
    assert got["note"].startswith("Not saved: the crew links could not be checked")


@needs_node
def test_a_refusal_says_why_and_drops_what_was_built_on_it():
    got = queue_js("""
      commit([{from: "main", to: "nobody", allow: ["ask"], askFirst: false}], [], "one");
      commit([], [], "two");
      finish(JSON.stringify({ ok: false, why: "link 1 names nobody" }), 1);
      return { writes: writes, queue: page.queue.length, note: page.saveNote, runs: runs.length };""", {})
    assert got == {"writes": [], "queue": 0, "note": "Not saved: link 1 names nobody.", "runs": 1}


@needs_node
def test_a_change_made_outside_while_saving_is_not_overwritten():
    """Codex review of M9: Hazel released in another window while an edit
    to another link is being checked; the edit, built on the old pair, must
    not put the quarantine back."""
    got = queue_js("""
      commit([{from: "main", to: "sora", allow: ["ask", "delegate"], askFirst: false}], ["hazel"], "chip");
      page.s.cfg.crewQuarantine = [];           // released elsewhere meanwhile
      finish(yes(), 0);
      return { writes: writes, note: page.saveNote, q: page.s.cfg.crewQuarantine };""",
                   {"crewLinks": L1, "crewQuarantine": ["hazel"]})
    assert got["writes"] == [] and got["q"] == []
    assert "changed outside Settings while this was being saved" in got["note"]


@needs_node
def test_quarantine_is_saved_before_the_links_and_unchanged_lists_not_at_all():
    got = queue_js("""
      commit([{from: "sora", to: "main", allow: ["ask", "message"], askFirst: false}], ["main"], "q");
      finish(yes(), 0);
      commit([], ["main"], "unchanged quarantine");
      finish(yes(), 0);
      return writes;""", {"crewLinks": [link("sora", "main", ["ask", "message"])], "crewQuarantine": []})
    assert [w[0] for w in got] == ["crewQuarantine", "crewLinks", "crewLinks"]
    assert got[1][1] == [{"from": "sora", "to": "main", "allow": ["ask"], "askFirst": False}], "trimmed"
    assert got[2][1] == []


def test_the_queue_moves_on_when_the_checker_exits():
    """The next queued edit starts when the checker process has gone: its
    output ends while it is still running, so starting the next one there
    found it busy and the queue stalled (found from the 8-agent preview)."""
    src = PAGE.read_text()
    proc = src[src.index("id: checker"):]
    on = proc[proc.index("onRunningChanged:"):]
    on = on[:on.index("\n    }\n")]
    assert "Qt.callLater(page.nextCheck)" in on
    assert "checker.head !== null" in _body(src, "nextCheck")


def test_crew_check_refuses_when_the_file_is_not_what_the_page_saw():
    """Codex review of M9, pass 2: the page's copy of the settings can lag
    the file; the check compares the pair the page saw with the file."""
    saved = [link("main", "sora", ["ask"], askFirst=False)]
    cfg = _Cfg(links=saved, quarantine=["hazel"])
    ask = {"crewLinks": [], "crewQuarantine": ["hazel"]}
    same = _crew_cli(json.dumps({**ask, "saved": {"crewLinks": saved, "crewQuarantine": ["hazel"]}}) + "\n", cfg)
    assert same[0] == 0
    for seen in ({"crewLinks": [], "crewQuarantine": ["hazel"]},
                 {"crewLinks": saved, "crewQuarantine": []},
                 {"crewLinks": saved},
                 "everything"):
        code, out, _ = _crew_cli(json.dumps({**ask, "saved": seen}) + "\n", cfg)
        assert code == 1 and "changed outside Settings" in json.loads(out)["why"], seen
    # Key order and JavaScript's 1 for 1.0 are the same list.
    odd = _Cfg(links=[{"to": "sora", "from": "main", "allow": ["ask"], "n": 1.0}])
    seen = {"crewLinks": [{"from": "main", "to": "sora", "allow": ["ask"], "n": 1}], "crewQuarantine": []}
    assert _crew_cli(json.dumps({"crewLinks": [], "crewQuarantine": [], "saved": seen}) + "\n", odd)[0] == 0


@needs_node
def test_the_page_sends_what_it_saw_and_waits_for_its_own_write():
    got = queue_js("""
      page.s.store.pending = { crewQuarantine: ["x"], voice: "y" };
      commit([], [], "one");
      var whileBusy = runs.length;
      page.s.store.pending = { voice: "y" }; nextCheck();
      return { whileBusy: whileBusy, runs: runs };""",
                   {"crewLinks": L1, "crewQuarantine": []})
    assert got["whileBusy"] == 0
    assert got["runs"] == [{"crewLinks": [], "crewQuarantine": [], "saved": {"crewLinks": L1, "crewQuarantine": []}}]
    src = PAGE.read_text()
    conn = src[src.index("target: page.s.store"):]
    assert "onPendingChanged" in conn[:conn.index("\n  }")] and "page.nextCheck()" in conn[:conn.index("\n  }")]
