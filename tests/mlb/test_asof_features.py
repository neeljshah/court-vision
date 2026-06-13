"""tests/mlb/test_asof_features.py — offline tests for domains/mlb/asof_features.py.

Network hard-blocked. Every test builds TINY synthetic ``pitchers`` + ``games``
DataFrames in-memory and writes the parquet to tmp_path — it never loads the real
corpus and never touches the network.

Run: python -m pytest tests/mlb/test_asof_features.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Network hard-block — before any import
# ---------------------------------------------------------------------------

def _block_network(*args, **kwargs):
    raise RuntimeError("Network access is forbidden in tests")

import urllib.request  # noqa: E402
urllib.request.urlopen = _block_network  # type: ignore[assignment]

from domains.mlb.asof_features import (  # noqa: E402
    OUT_COLS, build_asof_features,
)


# ---------------------------------------------------------------------------
# Synthetic-fixture helpers
# ---------------------------------------------------------------------------

def _game(eid, date, home, away, h_sp, a_sp, home_runs, away_runs,
          h_present: Optional[bool] = None, a_present: Optional[bool] = None):
    """Return (pitchers_row, games_row) dicts for one synthetic game."""
    pr = {
        "event_id": eid, "date": pd.Timestamp(date),
        "home_team": home, "away_team": away,
        "home_sp_name": h_sp, "away_sp_name": a_sp,
        "home_sp_present": (h_sp is not None) if h_present is None else h_present,
        "away_sp_present": (a_sp is not None) if a_present is None else a_present,
    }
    gr = {"event_id": eid, "home_runs": home_runs, "away_runs": away_runs}
    return pr, gr


def _frames(games: List[tuple]):
    """Split a list of (pitchers_row, games_row) tuples into two DataFrames."""
    return pd.DataFrame([p for p, _ in games]), pd.DataFrame([g for _, g in games])


def _build(games: List[tuple], tmp_path: Path) -> pd.DataFrame:
    pf, gf = _frames(games)
    out = build_asof_features(pitchers=pf, games=gf, out_path=str(tmp_path / "f.parquet"))
    assert Path(out).exists()
    return pd.read_parquet(str(out)).set_index("event_id")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_prior_only_trailing_mean(tmp_path):
    """A pitcher's 3rd start asof == mean runs-allowed of his prior 2 starts."""
    # SP 'Ace' starts at HOME 3 times. Runs allowed (home SP) == away_runs.
    games = [
        _game("g1", "2012-04-01", "AAA", "BBB", "Ace", "Z1", 5, 2),  # Ace allows 2
        _game("g2", "2012-04-08", "AAA", "CCC", "Ace", "Z2", 5, 4),  # Ace allows 4
        _game("g3", "2012-04-15", "AAA", "DDD", "Ace", "Z3", 5, 9),  # Ace allows 9
    ]
    df = _build(games, tmp_path)
    assert np.isnan(df.loc["g1", "home_sp_ra_asof"])           # no prior
    assert df.loc["g1", "home_sp_starts_prior"] == 0
    assert df.loc["g2", "home_sp_ra_asof"] == pytest.approx(2.0)  # mean of [2]
    assert df.loc["g2", "home_sp_starts_prior"] == 1
    assert df.loc["g3", "home_sp_ra_asof"] == pytest.approx(3.0)  # mean of [2,4]
    assert df.loc["g3", "home_sp_starts_prior"] == 2


def test_flip_future_no_change(tmp_path):
    """Changing a FUTURE game's outcome must not change an earlier game's asof."""
    base = [
        _game("g1", "2012-04-01", "AAA", "BBB", "Ace", "Z1", 5, 2),
        _game("g2", "2012-04-08", "AAA", "CCC", "Ace", "Z2", 5, 4),
        _game("g3", "2012-04-15", "AAA", "DDD", "Ace", "Z3", 5, 9),
    ]
    flipped = [
        base[0], base[1],
        _game("g3", "2012-04-15", "AAA", "DDD", "Ace", "Z3", 5, 99),  # future RA changed
    ]
    a = _build(base, tmp_path)
    b = _build(flipped, tmp_path)
    # g1 and g2 asof features are unchanged — leak-free (no future leakage).
    for eid in ("g1", "g2"):
        assert a.loc[eid, "home_sp_ra_asof"] is b.loc[eid, "home_sp_ra_asof"] or \
            (np.isnan(a.loc[eid, "home_sp_ra_asof"]) and np.isnan(b.loc[eid, "home_sp_ra_asof"])) or \
            a.loc[eid, "home_sp_ra_asof"] == pytest.approx(b.loc[eid, "home_sp_ra_asof"])
        assert a.loc[eid, "home_sp_starts_prior"] == b.loc[eid, "home_sp_starts_prior"]


def test_name_indexed_across_home_away(tmp_path):
    """A pitcher starting HOME then AWAY combines into one trailing history by NAME."""
    games = [
        # Ace starts HOME: allows away_runs == 2.
        _game("g1", "2012-04-01", "AAA", "BBB", "Ace", "Z1", 5, 2),
        # Ace now starts AWAY (away SP): allows home_runs == 6.
        _game("g2", "2012-04-08", "CCC", "AAA", "Z2", "Ace", 6, 1),
        # Ace starts HOME again: asof == mean of [2, 6] == 4.0 ; 2 prior starts.
        _game("g3", "2012-04-15", "AAA", "DDD", "Ace", "Z3", 5, 3),
    ]
    df = _build(games, tmp_path)
    assert df.loc["g2", "away_sp_ra_asof"] == pytest.approx(2.0)   # only g1 prior
    assert df.loc["g2", "away_sp_starts_prior"] == 1
    assert df.loc["g3", "home_sp_ra_asof"] == pytest.approx(4.0)   # mean of [2,6]
    assert df.loc["g3", "home_sp_starts_prior"] == 2


def test_runs_allowed_proxy_mapping(tmp_path):
    """home SP runs-allowed proxy == away_runs; away SP == home_runs."""
    games = [
        # First start each: establishes history from THIS game's proxy.
        _game("g1", "2012-04-01", "AAA", "BBB", "H1", "A1", 7, 3),
        # H1 starts home again -> asof should reflect g1 away_runs (3).
        _game("g2", "2012-04-08", "AAA", "CCC", "H1", "A2", 1, 1),
        # A1 starts away again -> asof should reflect g1 home_runs (7).
        _game("g3", "2012-04-09", "DDD", "BBB", "Z9", "A1", 2, 8),
    ]
    df = _build(games, tmp_path)
    assert df.loc["g2", "home_sp_ra_asof"] == pytest.approx(3.0)  # away_runs of g1
    assert df.loc["g3", "away_sp_ra_asof"] == pytest.approx(7.0)  # home_runs of g1


def test_nan_when_absent_or_zero_prior(tmp_path):
    """SP absent (present==False) or zero prior starts -> NaN asof, 0 count."""
    games = [
        _game("g1", "2012-04-01", "AAA", "BBB", None, "A1", 5, 2,
              h_present=False, a_present=True),
        _game("g2", "2012-04-08", "AAA", "BBB", "H1", "A1", 4, 1),
    ]
    df = _build(games, tmp_path)
    # g1 home SP absent -> NaN, 0.
    assert np.isnan(df.loc["g1", "home_sp_ra_asof"])
    assert df.loc["g1", "home_sp_starts_prior"] == 0
    # g1 away SP present but zero prior -> NaN, 0.
    assert np.isnan(df.loc["g1", "away_sp_ra_asof"])
    assert df.loc["g1", "away_sp_starts_prior"] == 0
    # g2 home SP first appearance -> NaN, 0 (no prior).
    assert np.isnan(df.loc["g2", "home_sp_ra_asof"])
    # diff is NaN when either side NaN.
    assert np.isnan(df.loc["g1", "sp_ra_diff_asof"])


def test_starts_prior_counts(tmp_path):
    """starts_prior increments by exactly one per prior start of that name."""
    games = [
        _game("g1", "2012-04-01", "AAA", "BBB", "Ace", "Z1", 5, 2),
        _game("g2", "2012-04-08", "AAA", "CCC", "Ace", "Z2", 5, 3),
        _game("g3", "2012-04-15", "AAA", "DDD", "Ace", "Z3", 5, 4),
        _game("g4", "2012-04-22", "AAA", "EEE", "Ace", "Z4", 5, 5),
    ]
    df = _build(games, tmp_path)
    assert list(df.loc[["g1", "g2", "g3", "g4"], "home_sp_starts_prior"]) == [0, 1, 2, 3]


def test_schema_sign_and_row_count(tmp_path):
    """Output schema, 1:1 row count, and away_minus_home diff sign."""
    games = [
        # Build histories: HomeAce trailing RA low (good), AwayBad trailing RA high (bad).
        _game("g1", "2012-04-01", "AAA", "BBB", "HomeAce", "X1", 5, 1),  # HomeAce allows 1
        _game("g2", "2012-04-02", "CCC", "DDD", "X2", "AwayBad", 9, 0),  # AwayBad allows 9
        # The decision game: both have exactly one prior start.
        _game("g3", "2012-04-10", "AAA", "DDD", "HomeAce", "AwayBad", 3, 2),
    ]
    pf, gf = _frames(games)
    out = build_asof_features(pitchers=pf, games=gf, out_path=str(tmp_path / "f.parquet"))
    df = pd.read_parquet(str(out))
    # schema exact + order.
    assert list(df.columns) == list(OUT_COLS)
    # 1:1 row count with pitchers input.
    assert len(df) == len(pf)
    di = df.set_index("event_id")
    # home_sp_ra_asof == 1 (HomeAce), away_sp_ra_asof == 9 (AwayBad).
    assert di.loc["g3", "home_sp_ra_asof"] == pytest.approx(1.0)
    assert di.loc["g3", "away_sp_ra_asof"] == pytest.approx(9.0)
    # diff = away - home = 9 - 1 = 8 > 0  => higher means HOME edge.
    assert di.loc["g3", "sp_ra_diff_asof"] == pytest.approx(8.0)
    assert di.loc["g3", "sp_ra_diff_asof"] > 0


def test_default_paths_callable(monkeypatch, tmp_path):
    """build_asof_features with no frames reads default parquet paths (smoke)."""
    import domains.mlb.asof_features as mod
    pf, gf = _frames([
        _game("g1", "2012-04-01", "AAA", "BBB", "Ace", "Z1", 5, 2),
        _game("g2", "2012-04-08", "AAA", "CCC", "Ace", "Z2", 5, 4),
    ])
    pp = tmp_path / "pitchers.parquet"
    gp = tmp_path / "games.parquet"
    pf.to_parquet(str(pp))
    gf.to_parquet(str(gp))
    monkeypatch.setattr(mod, "_default_pitchers_path", lambda: pp)
    monkeypatch.setattr(mod, "_default_games_path", lambda: gp)
    out = mod.build_asof_features(out_path=str(tmp_path / "out.parquet"))
    df = pd.read_parquet(str(out))
    assert len(df) == 2
    assert list(df.columns) == list(OUT_COLS)
