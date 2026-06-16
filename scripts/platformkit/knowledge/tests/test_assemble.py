"""Per-file test: assemble.py -- cited bundle, honest-reject, scrubbing, graph follow.

Uses stub retrievers so it runs without a built index. Standalone + pytest. ASCII.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.knowledge import assemble as A  # noqa: E402
from scripts.platformkit.knowledge.retrieve import Hit, RetrievalResult  # noqa: E402

_HITS = [
    Hit(note_id="NBA/Tactics/drop_coverage", sport="NBA", category="Tactics",
        title="Drop Coverage", snippet="the big drops below the screen",
        citation="[[NBA/Tactics/drop_coverage]]", score=0.9),
    Hit(note_id="NBA/Pace/transition", sport="NBA", category="Pace",
        title="Transition Tempo", snippet="pushing tempo after a rebound",
        citation="[[NBA/Pace/transition]]", score=0.8),
]


def _stub(query, sport=None, top_k=6):
    return RetrievalResult(list(_HITS), query, sport, reject=False)


def _empty(query, sport=None, top_k=6):
    return RetrievalResult([], query, sport, reject=True)


def test_successful_bundle_structure():
    b = A.assemble("NBA", question="drop coverage and tempo",
                   follow_graph=False, retriever=_stub)
    assert not b.reject
    assert b.markdown.startswith("# Scouting Context -- NBA")
    assert A.NO_EDGE_DISCLAIMER in b.markdown
    assert len(b.citations) == 2
    assert b.markdown.isascii()
    assert A.check_bundle(b) == []


def test_honest_reject_first_class():
    b = A.assemble("NBA", question="nothing relevant at all", retriever=_empty)
    assert b.reject
    assert A.HONEST_REJECT in b.markdown
    assert A.NO_EDGE_DISCLAIMER in b.markdown
    assert b.citations == []


def test_scrub_removes_numeric_tokens():
    # a snippet containing percentages / edge language must be scrubbed in output
    hits = [Hit(note_id="NBA/X/y", sport="NBA", category="X", title="Edge Note 55%",
                snippet="this gives a 55% edge and +200 odds and ROI",
                citation="[[NBA/X/y]]", score=0.7)]

    def _r(query, sport=None, top_k=6):
        return RetrievalResult(list(hits), query, sport, reject=False)

    b = A.assemble("NBA", question="anything", follow_graph=False, retriever=_r)
    assert A.check_bundle(b) == []
    assert "55%" not in b.markdown and "ROI" not in b.markdown


def test_every_claim_line_cited():
    b = A.assemble("NBA", question="concepts", follow_graph=False, retriever=_stub)
    import re
    cite = re.compile(r"\[\[[^\]]+\]\]\s*$")
    for ln in b.markdown.splitlines():
        s = ln.strip()
        if s.startswith("- "):
            assert cite.search(s), s


def _run() -> int:
    fails = 0
    for fn in (test_successful_bundle_structure, test_honest_reject_first_class,
               test_scrub_removes_numeric_tokens, test_every_claim_line_cited):
        try:
            fn()
            print("PASS", fn.__name__)
        except AssertionError as exc:
            fails += 1
            print("FAIL", fn.__name__, exc)
    return fails


if __name__ == "__main__":
    raise SystemExit(_run())
