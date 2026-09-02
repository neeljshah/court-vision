"""Gap S53 -- the soccer gate spine's additive as-of enrichment.

Guards three things: the rebuild stays additive on every pre-S53 column, the
seventeen new columns arrive at their printed join rates against the 25,834-row
denominator, and a same-match (leaky) column is refused BY NAME before it can
reach the spine.

Per-file test only:
`python -m pytest scripts/platformkit/combo/test_corpus_cache_soccer_enrich.py -q`
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.combo import corpus_cache as cc

N_ROWS = 25834

# The soccer spine's columns BEFORE S53, in their exact order. A rebuild must
# reproduce these values and this ordering; new columns append after them.
PRE_S53_COLUMNS = ("event_id", "corpus_unit", cc.DATE_COL, "y", "p_base", "p_over25",
                   "home_sot_for_l10", "away_sot_for_l10", "diff_sot_for_asof",
                   "diff_sot_against_asof", "diff_shots_for_asof", "diff_shots_against_asof",
                   "home_sot_ratio_for_asof", "away_sot_ratio_for_asof",
                   "home_n_prior", "away_n_prior")

# column -> non-null rows out of N_ROWS, measured 2026-09-03.
EXPECTED_JOINED = {
    "home_sot_for_asof": 25752, "home_sot_against_asof": 25752,
    "home_shots_for_asof": 25752, "home_shots_against_asof": 25752,
    "away_sot_for_asof": 25729, "away_sot_against_asof": 25729,
    "away_shots_for_asof": 25729, "away_shots_against_asof": 25729,
    "home_xg_for_asof": 25752, "home_xg_against_asof": 25752,
    "home_xg_supremacy_asof": 25752,
    "away_xg_for_asof": 25729, "away_xg_against_asof": 25729,
    "away_xg_supremacy_asof": 25729,
    "diff_xg_for_asof": 25708, "diff_xg_against_asof": 25708,
    "diff_xg_supremacy_asof": 25708,
}


def _rebuilt(tmp_path, monkeypatch) -> pd.DataFrame:
    """Rebuild the soccer spine into a tmp cache dir (real sources, no mocks)."""
    if not (cc._REPO / "data/domains/soccer/matches.parquet").exists():
        pytest.skip("no soccer domain data (a git worktree has no data tree)")
    monkeypatch.setattr(cc, "_CACHE_DIR", tmp_path)
    return cc.build_gate_corpus("soccer")


def test_rebuild_is_additive_on_every_pre_s53_column(tmp_path, monkeypatch):
    """Pre-existing columns keep their order AND their values (DataFrame.equals)."""
    cached_path = cc._corpus_path("soccer")
    if not cached_path.exists():
        pytest.skip("no cached soccer corpus")
    cached = pd.read_parquet(cached_path)
    after = _rebuilt(tmp_path, monkeypatch)
    assert len(after) == len(cached) == N_ROWS
    assert list(after.columns)[:len(PRE_S53_COLUMNS)] == list(PRE_S53_COLUMNS)
    old = list(PRE_S53_COLUMNS)
    assert after[old].equals(cached[old])


def test_new_columns_arrive_at_their_printed_join_rates(tmp_path, monkeypatch):
    after = _rebuilt(tmp_path, monkeypatch)
    added = [c for c in after.columns if c not in PRE_S53_COLUMNS]
    assert sorted(added) == sorted(EXPECTED_JOINED)
    for col, expected in EXPECTED_JOINED.items():
        assert int(after[col].notna().sum()) == expected, col


def test_sidecar_provenance_names_source_key_and_rate(tmp_path, monkeypatch):
    _rebuilt(tmp_path, monkeypatch)
    prov = cc.freshness_report("soccer")["provenance"]
    assert sorted(prov) == sorted(EXPECTED_JOINED)
    for col, expected in EXPECTED_JOINED.items():
        rec = prov[col]
        assert rec["join_key"] == "event_id"
        assert rec["source"].endswith(".parquet") and rec["source"].startswith("data/domains/soccer/")
        assert rec["n_rows"] == N_ROWS
        assert rec["n_joined"] == expected
        assert rec["join_rate"] == round(expected / N_ROWS, 6)


def test_a_same_match_column_is_refused_by_name():
    """Missing != bad, but a final-score fact is a leak, not a missing ingredient."""
    for leaky in ("home_shots", "fthg", "total_cards", "shot_share"):
        with pytest.raises(ValueError) as err:
            cc._asof_only(["diff_xg_supremacy_asof", leaky])
        assert leaky in str(err.value)
    assert cc._asof_only(["diff_xg_supremacy_asof"]) == ["diff_xg_supremacy_asof"]


def test_no_leaky_column_reached_the_spine(tmp_path, monkeypatch):
    after = _rebuilt(tmp_path, monkeypatch)
    assert not (set(after.columns) & cc.SOCCER_LEAKY_COLUMNS)
