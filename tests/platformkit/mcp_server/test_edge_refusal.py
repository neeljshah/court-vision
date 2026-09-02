"""S37 -- money-outcome phrasings must be REFUSED before any category routing.

Regression for S27 probe E04 ("how much money can we make beating the closing
line"), which the ask resolver classified `player_stat` and answered: the
edge-language guard's literal list carried no gerund and no money-OUTCOME
family, so the refusal path in `.claude/rules/no-edge-claims.md` never fired.

Both directions are asserted on purpose. Widening the guard is only correct if
it stays narrow: a calibration question that names the close ("do we match the
closing line", "what is the Brier vs the close") must still be answered, and
over-blocking one is as much a failure here as under-blocking E04.

Probes run through the SAME `tools.handler_for("ask")` the live MCP server
uses, so this covers the whole path, not just the classifier.

Run: python -m pytest tests/platformkit/mcp_server/test_edge_refusal.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.platformkit.answers import resolver_registry as R
from scripts.platformkit.mcp_server import tools as mcp_tools

_ROOT = Path(__file__).resolve().parents[3]
_PROBE_FILE = _ROOT / "docs/evidence/answer_probe_50.json"

# The four S27 refusal probes, read from the pinned probe file rather than
# retyped, so this test cannot drift away from the envelope contract's set.
_E_PROBES = [p for p in json.loads(_PROBE_FILE.read_text(encoding="utf-8"))
             if p["id"].startswith("E")]

# Money-outcome phrasings the guard missed before S37. Every one is edge
# language: it asks what the engine WINS, not how well it is calibrated.
_MONEY_QUERIES = [
    "how much money can we make on tennis tonight",
    "can we make money following these picks",
    "what is the return on investment here",
    "what are the expected winnings",
    "is this a sure bet",
    "are we beating the closing line",
    "do we beat the closing line on ATP",
    "are we beating the market",
]

# Calibration questions that name the close or a score -- these MUST answer.
_CALIBRATION_QUERIES = [
    "do we match the close",
    "what is the Brier vs the close",
    "do we match the closing line",
]


def test_e_probes_are_the_four_s27_refusal_probes():
    assert [p["id"] for p in _E_PROBES] == ["E01", "E02", "E03", "E04"]
    assert all(p["tool"] == "ask" and p["expect"] == "refused" for p in _E_PROBES)


@pytest.mark.parametrize("probe", _E_PROBES, ids=[p["id"] for p in _E_PROBES])
def test_s27_e_probes_all_refused(probe):
    env = mcp_tools.handler_for("ask")(probe["arguments"])
    assert env["status"] == "refused", "%s -> %r" % (probe["id"], env.get("status"))
    assert env["category"] == "edge_language"
    # The refusal cites the no-edge rule, exactly as the existing path does.
    assert env["source_artifact"] == ".claude/rules/no-edge-claims.md"
    assert "no-edge-claims.md" in env["note"]


@pytest.mark.parametrize("query", _MONEY_QUERIES)
def test_money_outcome_phrasings_refused(query):
    assert R.is_edge_language(query) is not None
    assert R.classify(query) == "edge_language"
    env = mcp_tools.handler_for("ask")({"query": query, "sport": "nba"})
    assert env["status"] == "refused"
    assert env["source_artifact"] == ".claude/rules/no-edge-claims.md"


@pytest.mark.parametrize("query", _CALIBRATION_QUERIES)
def test_calibration_questions_not_refused(query):
    assert R.is_edge_language(query) is None, query
    assert R.classify(query) != "edge_language"
    env = mcp_tools.handler_for("ask")({"query": query, "sport": "nba"})
    assert env["status"] != "refused", "%s -> %r" % (query, env.get("note"))
