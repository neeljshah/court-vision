"""Per-file test: 2026-07-19 merge alias additions in ask_index.py for 3 new
claim families (shooter_composite_v2_asof_approx, nba_context_shooting_defadj,
nba_lineup_context) whose obvious phrasings previously resolved to no metric
at all (extract_metric_synonym returned None -> honest UNANSWERABLE even
though the metric is VERIFIED and on disk).

Run: python -m pytest scripts/platformkit/intel_query/test_ask_index_new_family_aliases.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.platformkit.intel_query import ask_index
from scripts.platformkit.intel_query.claims_index import build_index
from scripts.platformkit.intel_query.families import ParsedQuestion

REPO_ROOT = Path(__file__).resolve().parents[3]

# ---------------------------------------------------------------------------
# Alias -> metric string, one assertion per requested phrasing.
# ---------------------------------------------------------------------------
_ALIAS_CASES = [
    ("best shooter ranking", "shooter_composite_v2"),
    ("top shooters", "shooter_composite_v2"),
    ("shooter composite", "shooter_composite_v2"),
    ("who are the best shooters this season", "shooter_composite_v2_asof_approx"),
    ("who are the best shooters in the nba in 2025-26", "shooter_composite_v2_asof_approx"),
    ("defense adjusted true shooting", "def_adj_ts_pct"),
    ("defense-adjusted ts", "def_adj_ts_pct"),
    ("shoot better against weak defenses", "ts_pct_weak_minus_tough"),
    ("weak vs tough defense split", "ts_pct_weak_minus_tough"),
    ("scheme sensitive scorers", "scheme_ts_pct_best_minus_worst"),
    ("ts swing by scheme", "scheme_ts_pct_best_minus_worst"),
    ("usage when trailing vs leading", "trailing_fga_pg_minus_leading_fga_pg"),
    ("shot volume collapse when leading", "trailing_fga_pg_minus_leading_fga_pg"),
    ("on off net rating", "net_rating_delta"),
    ("on-off net rating", "net_rating_delta"),
    ("on/off impact", "net_rating_delta"),
    ("teammates shoot better with him on", "teammate_efg_lift"),
    ("gravity proxy", "gravity_proxy"),
    ("rim protection on off", "rim_protection_delta"),
    ("best spacing lineup", "spacing_mean_dist"),
]


@pytest.mark.parametrize("phrase,expected_metric", _ALIAS_CASES, ids=[c[0] for c in _ALIAS_CASES])
def test_alias_resolves_to_expected_metric(phrase, expected_metric):
    assert ask_index.extract_metric_synonym(phrase) == expected_metric


def test_no_season_token_keeps_pre_existing_shooter_metric_no_regression():
    """Pre-existing 'best shooter'/'best shooters' behavior (no season
    token) is UNCHANGED by the season-aware branch."""
    assert ask_index.extract_metric_synonym("best shooter") == "shooter_composite_v2"
    assert ask_index.extract_metric_synonym("best shooters") == "shooter_composite_v2"


def test_unrelated_phrase_still_returns_none_no_regression():
    assert ask_index.extract_metric_synonym("what is the capital of France") is None


# ---------------------------------------------------------------------------
# One end-to-end index_top_n_lookup proof (shooter_composite_v2_asof_approx)
# -- same fixture shape as test_ask_index.py's own established pattern.
# ---------------------------------------------------------------------------
def _ranking_row(claim_id, metric, window, computed_at, ranking):
    return {
        "claim_id": claim_id, "kind": "ranking",
        "question": f"{metric} leaderboard ({window})?",
        "criteria": {"metric": metric, "window": window, "entity_key": "player_id"},
        "ranking": ranking, "source_files": ["data/fake/source.parquet"],
        "computed_at": computed_at, "n_considered": 100, "n_excluded_below_floor": 5,
        "caveats": [],
    }


def _write_family(claims_dir, family, rows, verdicts):
    claims_path = claims_dir / f"{family}.jsonl"
    with open(claims_path, "w", encoding="ascii") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    payload = {
        "component": "test", "generated_at": "2026-07-19T00:00:00+00:00",
        "n_claims": len(rows), "n_verified": sum(1 for v in verdicts.values() if v == "VERIFIED"),
        "n_mismatch": 0, "n_unverifiable": 0, "edge_claimed": False,
        "details": [{"claim_id": cid, "verdict": v, "reason": "test"} for cid, v in verdicts.items()],
    }
    (claims_dir / f"{family}_validation.json").write_text(json.dumps(payload), encoding="ascii")


def test_shooter_asof_approx_end_to_end_index_lookup(tmp_path):
    rows = [_ranking_row("s1", "shooter_composite_v2_asof_approx", "season_2025_26",
                          "2026-07-19T00:00:00+00:00",
                          [{"rank": 1, "player_id": 1, "player_name": "Alpha", "value": 0.9}])]
    _write_family(tmp_path, "shooter_composite_v2_claims", rows, {"s1": "VERIFIED"})
    build_index("shooter_composite_v2_claims", tmp_path)

    parsed = ParsedQuestion(family="top_n", top_n=5,
                            raw="who are the best shooters in the nba this season?")
    row = ask_index.index_top_n_lookup(parsed, tmp_path, REPO_ROOT)
    assert row is not None
    assert row["claim_id"] == "s1"
