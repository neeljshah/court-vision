"""Per-file test for the S91 games.parquet MLB outcome fallback.

Run: python -m pytest scripts/platformkit/ingame/test_mlb_games_outcome_fallback.py -q
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from scripts.platformkit.ingame.ingame_outcome_label import MlbOutcomeResolver
from scripts.platformkit.ingame.mlb_games_outcome_fallback import (
    CURRENT_ABBRS, load_games_box_frame)

TODAY = dt.date(2026, 9, 2)

# 3 synthetic tickers: one only the ESPN box knows, one only games.parquet
# knows, one both know (the ESPN row must win and it disagrees on purpose).
T_ESPN_ONLY = "KXMLBGAME-26JUL142000ALNL"
T_GAMES_ONLY = "KXMLBGAME-26JUL011420SDCHC"
T_BOTH = "KXMLBGAME-26JUL011335DETNYY"


def _games_frame() -> pd.DataFrame:
    return pd.DataFrame([
        # SDG/CUB are games.parquet codes -> must map to SD/CHC.
        {"event_id": "2026-07-01-CUB-SDG-1", "date": "2026-07-01",
         "home_team": "CUB", "away_team": "SDG", "home_runs": 5, "away_runs": 2},
        {"event_id": "2026-07-01-NYY-DET-1", "date": "2026-07-01",
         "home_team": "NYY", "away_team": "DET", "home_runs": 1, "away_runs": 9},
        # relic code -> must be dropped, never widening the abbr alphabet.
        {"event_id": "2020-08-11-BRS-NYY-1", "date": "2020-08-11",
         "home_team": "BRS", "away_team": "NYY", "home_runs": 3, "away_runs": 1},
    ])


def _espn_frame() -> pd.DataFrame:
    return pd.DataFrame([
        {"event_id": "401817370", "date": "2026-07-14", "status": "STATUS_FINAL",
         "home_abbr": "NL", "away_abbr": "AL", "home_score": 0.0,
         "away_score": 4.0, "start_time": "2026-07-15T00:00Z"},
        # SAME game as the games row, opposite winner: ESPN must win.
        {"event_id": "401800001", "date": "2026-07-01", "status": "STATUS_FINAL",
         "home_abbr": "NYY", "away_abbr": "DET", "home_score": 7.0,
         "away_score": 2.0, "start_time": "2026-07-01T17:35Z"},
    ])


def _resolver(tmp_path, espn: pd.DataFrame, games: pd.DataFrame
              ) -> MlbOutcomeResolver:
    ep = tmp_path / "espn_boxscores.parquet"
    espn.to_parquet(ep, index=False)
    gp = tmp_path / "games.parquet"
    games.to_parquet(gp, index=False)
    r = MlbOutcomeResolver(box_parquet=ep, games_fallback=False)
    fb = load_games_box_frame([gp])
    assert fb is not None
    r._ingest(fb, into=r._fb)
    return r


def test_three_tickers(tmp_path):
    r = _resolver(tmp_path, _espn_frame(), _games_frame())
    assert r.available
    # espn-only ticker still resolves off the espn rows
    assert r.home_win(T_ESPN_ONLY, today=TODAY) == 0
    # games-only ticker now resolves (was None before S91): CHC 5, SD 2
    assert r.home_win(T_GAMES_ONLY, today=TODAY) == 1
    # both known -> the ESPN row wins (7-2 home) not the games row (1-9 home)
    assert r.home_win(T_BOTH, today=TODAY) == 1
    assert r.final_score(T_BOTH, today=TODAY) == (7, 2)


def test_no_espn_rows_still_resolves(tmp_path):
    """The real S91 state: the espn parquet is (near) empty."""
    empty = _espn_frame().iloc[:1]  # only the all-star row
    r = _resolver(tmp_path, empty, _games_frame())
    assert r.home_win(T_GAMES_ONLY, today=TODAY) == 1
    assert r.home_win(T_BOTH, today=TODAY) == 0  # now the games row decides


def test_fallback_is_exact_date_only(tmp_path):
    """A +1/-1 day hop must NOT reach the fallback rows (that mislabelled a
    real 2026-07-07 doubleheader -- see the module docstring)."""
    r = _resolver(tmp_path, _espn_frame().iloc[:1], _games_frame())
    assert r.home_win("KXMLBGAME-26JUN301420SDCHC", today=TODAY) is None
    assert r.home_win("KXMLBGAME-26JUL021420SDCHC", today=TODAY) is None


def test_relic_codes_dropped_and_mapping():
    assert load_games_box_frame([]) is None  # no paths -> honest None
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        gp = Path(td) / "games.parquet"
        _games_frame().to_parquet(gp, index=False)
        out = load_games_box_frame([gp])
    assert len(out) == 2  # the BRS relic row is gone
    assert set(out["home_abbr"]) == {"CHC", "NYY"}
    assert set(out["away_abbr"]) == {"SD", "DET"}
    assert set(out["home_abbr"]) <= CURRENT_ABBRS
    assert (out["status"] == "STATUS_FINAL").all()
    assert (out["start_time"] == "").all()


def test_real_disk_fallback_covers_the_ticker_corpus():
    """Non-synthetic: the on-disk games parquets must load and cover 2026."""
    fb = load_games_box_frame()
    if fb is None:
        pytest.skip("games parquets absent (clean clone)")
    assert len(fb) > 10000
    assert set(fb["home_abbr"]) <= CURRENT_ABBRS
    r = MlbOutcomeResolver()
    assert r.home_win("KXMLBGAME-26JUL011420SDCHC", today=TODAY) is not None
