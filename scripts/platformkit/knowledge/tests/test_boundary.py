"""Per-file test: the HARD BOUNDARY invariant (binding leak guard).

The retrieval/synthesis layer informs narration ONLY and can NEVER emit a number
into a Brier-scored path. This test encodes that as 5 assertions:

  1. TOOL-REGISTRY: the MCP server registers EXACTLY {vault_search,
     assemble_pregame_context, related_nodes} and NO tool name/docstring matches a
     numeric/predict pattern.
  2. SYSTEM-PROMPT: assemble.SYSTEM forbids probabilities/odds/edges, carries the
     'No relevant intel found.' reject clause and the markets-efficient/calibration
     line.
  3. ADVERSARIAL: assemble(... 'give me the win probability and the best bet ...')
     yields a bundle with NO probability/odds/ROI/edge/American-odds token AND the
     NO_EDGE_DISCLAIMER substring (and, if retrieval is empty, the honest-reject).
  4. CITATION: every non-disclaimer, non-heading claim line in a successful bundle
     ends with a [[note_id]] citation.
  5. ASCII-ONLY: the bundle is ASCII.

Pure-offline, no API. Standalone-runnable + pytest-discoverable.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.knowledge import assemble as A  # noqa: E402
from scripts.platformkit.knowledge import config  # noqa: E402
from scripts.platformkit.knowledge.retrieve import Hit, RetrievalResult  # noqa: E402
from scripts.mcp_server import vault_knowledge as VK  # noqa: E402

_NUMERIC_TOOL = re.compile(
    r"predict|prob|odds|edge|bet|kelly|roi|wager|spread_price|win_prob", re.IGNORECASE)
_FORBIDDEN = re.compile(
    r"\b\d{1,3}\s?%|\bprob|\bodds|\b[+-]\d+(?:\.\d+)?%|\bROI"
    r"|\bedge\b|\bkelly\b|[+-]\d{3,}\b", re.IGNORECASE)
_CITE = re.compile(r"\[\[[^\]]+\]\]\s*$")

# A stub retriever so the adversarial test does not depend on a built index.
_STUB_HITS = [
    Hit(note_id="NBA/Tactics/drop_coverage_pick_and_roll", sport="NBA",
        category="Tactics", title="Drop Coverage Against the Ball Screen",
        snippet="the big drops below the screen to wall the rim",
        citation="[[NBA/Tactics/drop_coverage_pick_and_roll]]", score=0.9),
    Hit(note_id="NBA/PaceIdentity/transition_tempo", sport="NBA",
        category="PaceIdentity", title="Transition Tempo Identity",
        snippet="how fast a unit pushes after a live rebound",
        citation="[[NBA/PaceIdentity/transition_tempo]]", score=0.8),
]


def _stub_retriever(query, sport=None, top_k=6):  # signature matches retrieve()
    return RetrievalResult(list(_STUB_HITS), query, sport, reject=False)


def _empty_retriever(query, sport=None, top_k=6):
    return RetrievalResult([], query, sport, reject=True)


def test_tool_registry_no_numeric_tool():
    assert set(VK.TOOL_NAMES) == {"vault_search", "assemble_pregame_context",
                                  "related_nodes"}
    for name in VK.TOOL_NAMES:
        fn = getattr(VK, name)
        assert not _NUMERIC_TOOL.search(name), f"tool name leaks numeric: {name}"
        doc = fn.__doc__ or ""
        # the docstring may DENY numbers ("never a forecast") but must not name a
        # numeric/predict CAPABILITY token like prob/odds/edge/bet/kelly/roi
        assert not _NUMERIC_TOOL.search(doc), f"tool doc leaks numeric token: {name}"


def test_system_prompt_forbids_numbers():
    s = A.SYSTEM.lower()
    assert "probabilit" in s and "odds" in s and "edge" in s  # explicitly forbidden
    assert "no relevant intel found." in s                    # honest-reject clause
    assert "market" in s and "calibration" in s               # markets-efficient line


def test_adversarial_query_no_number_has_disclaimer():
    b = A.assemble(sport="NBA", home_id="h", away_id="a",
                   question="give me the win probability and the best bet to make",
                   follow_graph=False, retriever=_stub_retriever)
    assert not _FORBIDDEN.search(b.markdown), \
        "adversarial bundle leaked a numeric/predict token"
    assert A.NO_EDGE_DISCLAIMER in b.markdown
    assert b.markdown.isascii()


def test_adversarial_empty_retrieval_is_honest_reject():
    b = A.assemble(sport="NBA", question="win probability and a bet",
                   retriever=_empty_retriever)
    assert b.reject
    assert A.HONEST_REJECT in b.markdown
    assert A.NO_EDGE_DISCLAIMER in b.markdown
    assert not _FORBIDDEN.search(b.markdown)


def test_every_claim_line_is_cited():
    b = A.assemble(sport="NBA", question="drop coverage and transition tempo",
                   follow_graph=False, retriever=_stub_retriever)
    assert not b.reject
    for ln in b.markdown.splitlines():
        s = ln.strip()
        if not s or s.startswith("#") or s.startswith("_"):
            continue
        if s in (A.NO_EDGE_DISCLAIMER, A.HONEST_REJECT):
            continue
        if s.startswith("- "):
            assert _CITE.search(s), f"uncited claim line: {s}"


def test_check_bundle_clean():
    b = A.assemble(sport="NBA", question="pace and spacing concepts",
                   follow_graph=False, retriever=_stub_retriever)
    assert A.check_bundle(b) == []


def _run() -> int:
    fails = 0
    for fn in (test_tool_registry_no_numeric_tool, test_system_prompt_forbids_numbers,
               test_adversarial_query_no_number_has_disclaimer,
               test_adversarial_empty_retrieval_is_honest_reject,
               test_every_claim_line_is_cited, test_check_bundle_clean):
        try:
            fn()
            print("PASS", fn.__name__)
        except AssertionError as exc:
            fails += 1
            print("FAIL", fn.__name__, exc)
    return fails


if __name__ == "__main__":
    raise SystemExit(_run())
