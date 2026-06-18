"""tests.mlb.test_refresh_ratings -- the CURRENT-as-of MLB ratings refresh.

Asserts: the current corpus loads and extends past 2021; the combined corpus runs the
SAME walk_forward MOV-Elo; the refreshed predictor builds and differs from the frozen one
(sanity -- 2022-2026 results moved the ratings). The frozen pipeline is untouched.

Per-file only (full pytest freezes the box):
    python -m pytest tests/mlb/test_refresh_ratings.py -q
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_CURRENT = _REPO / "data" / "domains" / "mlb" / "games_current.parquet"
_FROZEN = _REPO / "data" / "domains" / "mlb" / "games.parquet"

# These tests need the gitignored local corpora; skip cleanly on a fresh clone.
pytestmark = pytest.mark.skipif(
    not (_CURRENT.exists() and _FROZEN.exists()),
    reason="local MLB corpora absent (gitignored); run ingest_current first",
)

_SCHEMA = {"event_id", "date", "season", "home_team", "away_team",
           "home_runs", "away_runs", "target_home_win", "game_seq", "home_league"}


def test_current_corpus_loads_and_extends_past_2021():
    import pandas as pd
    df = pd.read_parquet(_CURRENT)
    assert len(df) > 5000, "current corpus suspiciously small"
    assert _SCHEMA.issubset(set(df.columns)), "schema must match frozen games.parquet"
    dmax = pd.to_datetime(df["date"]).max().date()
    dmin = pd.to_datetime(df["date"]).min().date()
    assert dmin.year >= 2022, "current corpus should start 2022+"
    assert dmax > dt.date(2021, 11, 2), "must extend past the frozen 2021-11-02 cutoff"
    assert dmax <= dt.date(2026, 6, 16), "must not include unsettled future games"


def test_combined_corpus_is_chronological_and_aligned():
    from domains.mlb.refresh_ratings import load_combined_corpus
    import pandas as pd
    combined = load_combined_corpus()
    frozen = pd.read_parquet(_FROZEN)
    assert len(combined) > len(frozen), "combined must add the current rows"
    d = pd.to_datetime(combined["date"]).dt.date
    assert list(d) == sorted(d), "combined corpus must be chronological"
    assert d.iloc[-1] > dt.date(2021, 11, 2)


def test_walk_forward_runs_on_combined():
    from domains.mlb.ratings import walk_forward_elo
    from domains.mlb.refresh_ratings import load_combined_corpus
    wf = walk_forward_elo(load_combined_corpus())
    for c in ("elo_home", "elo_away", "elo_diff_hfa", "p_home_elo"):
        assert c in wf.columns
    assert wf["p_home_elo"].between(0.0, 1.0).all()


def test_refreshed_ratings_differ_from_frozen():
    from domains.mlb.refresh_ratings import refreshed_elo, frozen_elo
    re, fe = refreshed_elo(), frozen_elo()
    common = set(re) & set(fe)
    assert len(common) >= 25, "should share the 30 active franchises"
    max_delta = max(abs(re[k] - fe[k]) for k in common)
    assert max_delta > 5.0, (
        "refreshed Elo must differ from frozen (2022-2026 results should move ratings); "
        f"max delta only {max_delta:.2f}")


def test_refreshed_predictor_builds_and_predicts():
    from domains.mlb.refresh_ratings import refreshed_predictor, frozen_predictor
    rp = refreshed_predictor()
    fp = frozen_predictor()
    assert rp.n_games > fp.n_games, "refreshed predictor must see more games than frozen"
    out = rp.predict("BOS", "TOR")
    assert 0.0 <= out["p_home_win"] <= 1.0
    assert out["expected_total"] > 0.0
    # The refreshed and frozen predictors should generally produce different numbers
    # for at least one of a few matchups (sanity that the corpus actually changed them).
    diffs = [abs(rp.predict(h, a)["p_home_win"] - fp.predict(h, a)["p_home_win"])
             for h, a in [("CUB", "COL"), ("NYY", "CWS"), ("HOU", "DET")]]
    assert max(diffs) > 0.01, "refreshed win-probs should diverge from frozen"


def test_frozen_predictor_unchanged():
    """The no-arg frozen predictor must still build off games.parquet alone (2010-2021)."""
    from domains.mlb.predictor import MLBPredictor
    fp = MLBPredictor()
    assert fp.n_games == 27983, "frozen default-path corpus must be untouched"
