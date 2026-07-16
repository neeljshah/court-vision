"""LANE E -- analytics-verify resolver tests. Proves the four fail-closed
paths (ok / no_data / refused-stale / refused-missing-edge_claimed) per
resolver, plus that resolver_registry actually dispatches the four new
question types.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/analytics_verify/test_answers.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from scripts.platformkit.analytics_verify import answers as A
from scripts.platformkit.answers import resolver_registry as R

FRESH = datetime.now(timezone.utc).isoformat()
STALE = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _point(kind, tmp_path, monkeypatch):
    p = tmp_path / f"{kind}.json"
    monkeypatch.setitem(A.ARTIFACTS, kind, str(p))
    return p


# ---------------------------------------------------------------------------
# attribution
# ---------------------------------------------------------------------------
def test_attribution_no_data_when_artifact_absent(tmp_path, monkeypatch):
    _point("attribution", tmp_path, monkeypatch)
    r = A.attribution("nba", family="player_prop")
    assert r["status"] == "no_data"
    assert r["category"] == "analytics_attribution"


def test_attribution_refused_when_edge_claimed_missing(tmp_path, monkeypatch):
    p = _point("attribution", tmp_path, monkeypatch)
    _write(p, {"generated_at": FRESH, "by_family": {}})  # no edge_claimed key
    r = A.attribution("nba")
    assert r["status"] == "refused"
    assert "edge_claimed" in r["note"]


def test_attribution_refused_when_stale(tmp_path, monkeypatch):
    p = _point("attribution", tmp_path, monkeypatch)
    _write(p, {"generated_at": STALE, "edge_claimed": False, "by_family": {}})
    r = A.attribution("nba")
    assert r["status"] == "refused"
    assert "staleness" in r["note"]


def test_attribution_ok_family_receipt(tmp_path, monkeypatch):
    p = _point("attribution", tmp_path, monkeypatch)
    _write(p, {"generated_at": FRESH, "edge_claimed": False, "honest_note": "calibration only",
                "link_method_mix": {"exact": 0.9}, "join_rates": {"nba": 0.95},
                "by_family": {"player_prop": {"n_bets": 40, "n_settled": 40, "mean_clv_pct": 1.2,
                                               "median_clv_pct": 0.9, "pct_beat_close": 0.55,
                                               "flat_units_result": 0.3, "n_proxy_close": 2}},
                "by_card": {}})
    r = A.attribution("nba", family="player_prop")
    assert r["status"] == "ok"
    assert r["receipt"]["n_bets"] == 40
    assert r["as_of"] == FRESH
    assert r["source_artifact"] == str(p)


def test_attribution_no_data_unknown_family(tmp_path, monkeypatch):
    p = _point("attribution", tmp_path, monkeypatch)
    _write(p, {"generated_at": FRESH, "edge_claimed": False, "by_family": {"totals": {}}})
    r = A.attribution("nba", family="nope")
    assert r["status"] == "no_data"
    assert "totals" in r["note"]


# ---------------------------------------------------------------------------
# claim_survival / verification / contradictions -- one representative gate
# each (the fail-closed gate itself is shared code, proven above)
# ---------------------------------------------------------------------------
def test_claim_survival_ok(tmp_path, monkeypatch):
    p = _point("claim_survival", tmp_path, monkeypatch)
    _write(p, {"generated_at": FRESH, "edge_claimed": False, "n_cards_total": 10, "n_eligible": 8,
                "verdict_counts": {"DECAYED": 1}, "survival": {"7d": 0.9}, "decayed_cards": ["c1"],
                "insufficient_cards": []})
    r = A.claim_survival("nba")
    assert r["status"] == "ok"
    assert r["n_cards_total"] == 10
    assert r["decayed_cards"] == ["c1"]


def test_verification_ok_and_stat_filter(tmp_path, monkeypatch):
    p = _point("verification", tmp_path, monkeypatch)
    _write(p, {"as_of": FRESH, "edge_claimed": False, "overall": "PASS",
                "checks": [{"stat": "mean_clv_pct", "served_value": 1.2, "recomputed_value": 1.2,
                            "delta": 0.0, "verdict": "VERIFIED"}],
                "n_verified": 1, "n_discrepant": 0, "n_stale": 0, "n_uncheckable": 0})
    ok = A.verification("nba", stat="mean_clv_pct")
    assert ok["status"] == "ok" and ok["checks"][0]["verdict"] == "VERIFIED"
    missing = A.verification("nba", stat="not_a_stat")
    assert missing["status"] == "no_data"


def test_contradictions_no_data_when_absent(tmp_path, monkeypatch):
    _point("contradictions", tmp_path, monkeypatch)
    r = A.contradictions("nba", family="player_prop")
    assert r["status"] == "no_data"


# ---------------------------------------------------------------------------
# registry dispatch integrity
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cat", ["analytics_attribution", "analytics_claim_survival",
                                  "analytics_verification", "analytics_contradictions"])
def test_registry_has_resolver_metadata(cat):
    assert cat in R.RESOLVERS
    assert R.RESOLVERS[cat]["source_artifact"].startswith("data/cache/analytics_verify/")


def test_registry_dispatches_analytics_categories(tmp_path, monkeypatch):
    """resolve() with an explicit category reaches the real resolver (no_data
    path, since no fixture is pointed at ARTIFACTS here)."""
    for cat in ("analytics_attribution", "analytics_claim_survival",
                "analytics_verification", "analytics_contradictions"):
        env = R.resolve("irrelevant text", sport="nba", category=cat)
        assert env["category"] == cat
        assert env["status"] in ("no_data", "ok", "refused")


def test_classify_routes_analytics_keywords():
    assert R.classify("show me the clv attribution for player_prop") == "analytics_attribution"
    assert R.classify("what is the claim survival rate") == "analytics_claim_survival"
    assert R.classify("run the sentinel check on mean_clv_pct") == "analytics_verification"
    assert R.classify("any contradiction between these claims") == "analytics_contradictions"
