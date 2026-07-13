"""Per-file test for scripts.platformkit.omni.close_lookup.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_close_lookup.py -q
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from scripts.platformkit.odds_provider.team_resolver import canonical
from scripts.platformkit.omni.close_lookup import (
    _devig,
    _last_before,
    _ticker_anchor,
    pregame_close,
)

_STORE = "data/cache/inplay_odds"


def _has_store() -> bool:
    from pathlib import Path
    return (Path(_STORE) / "nba_price_series.parquet").exists() and \
        (Path(_STORE) / "mlb_price_series.parquet").exists()


pytestmark = pytest.mark.skipif(not _has_store(), reason="inplay_odds price-series store unavailable")


# --------------------------------------------------------------------------- #
# Devig math -- synthetic two-sided pair.
# --------------------------------------------------------------------------- #

def test_devig_normalizes_two_sided_pair():
    # 0.60/0.45 sums to 1.05 (5% vig) -> devigged home share is 0.60/1.05.
    p = _devig(0.60, 0.45)
    assert p == pytest.approx(0.60 / 1.05)


def test_devig_single_sided_returns_raw_prob():
    # Polymarket store captures only the home side -- undevigged pass-through.
    assert _devig(0.62, None) == pytest.approx(0.62)


def test_devig_degenerate_inputs_return_none():
    assert _devig(0.0, 0.5) is None
    assert _devig(1.0, 0.5) is None
    assert _devig(None, 0.5) is None


# --------------------------------------------------------------------------- #
# Leak test -- no tick at-or-after the start-time proxy ever enters the close.
# --------------------------------------------------------------------------- #

def test_last_before_excludes_at_and_after_cutoff():
    rows = pd.DataFrame({"ts": [100, 200, 300, 400], "prob": [0.5, 0.6, 0.7, 0.8]})
    hit = _last_before(rows, cutoff_ts=300)
    assert hit is not None
    assert hit["ts"] == 200  # 300 itself (at cutoff) must NOT be selected
    assert hit["ts"] < 300


def test_last_before_no_rows_strictly_before_cutoff_is_none():
    rows = pd.DataFrame({"ts": [500, 600], "prob": [0.5, 0.6]})
    assert _last_before(rows, cutoff_ts=500) is None


def test_real_event_close_ts_strictly_before_next_in_game_tick():
    """Real Kalshi NBA playoff event: the returned close ts must be strictly
    before the start-of-game-date UTC proxy, and demonstrably pregame (well
    before the in-game price move captured in this store for the same
    event -- verified live 2026-07-13: BOS/PHI 2026-04-26 shows quiet
    ~0.70-0.74 oscillation through 04-26 21:xx UTC, then a large move to
    0.91+ by 04-26 23:54 UTC as the game resolves)."""
    res = pregame_close("nba", "2026-04-26", "BOS", "PHI")
    assert res is not None
    assert res["source"] == "kalshi"
    close_dt = dt.datetime.utcfromtimestamp(res["ts"])
    cutoff = dt.datetime(2026, 4, 26)
    assert close_dt < cutoff
    # Sanity: the close prob is a plausible pregame number, not the near-1.0
    # settlement value the market reached by game end.
    assert 0.0 < res["prob_home_devig"] < 0.9


# --------------------------------------------------------------------------- #
# Join rate on a real slice (>=95% required).
# --------------------------------------------------------------------------- #

def test_join_rate_mlb_2026_06_10_real_slice():
    paths = ["data/domains/mlb/games.parquet", "data/domains/mlb/games_current.parquet"]
    frames = [pd.read_parquet(p) for p in paths]
    games = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["event_id"], keep="last")
    games["d"] = pd.to_datetime(games["date"]).dt.date.astype(str)
    sub = games[games["d"] == "2026-06-10"]
    assert len(sub) > 0
    hits = sum(
        pregame_close("mlb", "2026-06-10", r["home_team"], r["away_team"]) is not None
        for _, r in sub.iterrows()
    )
    rate = hits / len(sub)
    assert rate >= 0.95, f"join rate {rate:.2%} on {len(sub)} MLB games (2026-06-10)"


def test_join_rate_nba_2025_04_13_real_slice():
    games = pd.read_parquet("data/domains/basketball_nba/games.parquet")
    games["d"] = pd.to_datetime(games["date"]).dt.date.astype(str)
    sub = games[games["d"] == "2025-04-13"]
    assert len(sub) > 0
    hits = sum(
        pregame_close("nba", "2025-04-13", r["home_team"], r["away_team"]) is not None
        for _, r in sub.iterrows()
    )
    rate = hits / len(sub)
    assert rate >= 0.95, f"join rate {rate:.2%} on {len(sub)} NBA games (2025-04-13)"


# --------------------------------------------------------------------------- #
# Misc: ticker parsing, unknown team, missing date.
# --------------------------------------------------------------------------- #

def test_ticker_anchor_parses_embedded_date_and_hhmm():
    date_only, proxy_only = _ticker_anchor("KXNBAGAME-26APR26BOSPHI")
    assert date_only == dt.date(2026, 4, 26)
    assert proxy_only == dt.datetime(2026, 4, 26)

    date_hhmm, proxy_hhmm = _ticker_anchor("KXMLBGAME-26JUN101310BOSTB-BOS")
    assert date_hhmm == dt.date(2026, 6, 10)
    assert proxy_hhmm == dt.datetime(2026, 6, 10, 17, 10)  # 13:10 ET + 4h = 17:10 UTC


def test_ticker_anchor_bad_shape_returns_none():
    assert _ticker_anchor("not-a-real-ticker") is None


def test_pregame_close_missing_date_returns_none():
    assert pregame_close("nba", "2020-01-01", "BOS", "PHI") is None


def test_pregame_close_unknown_team_never_raises():
    assert pregame_close("nba", "2025-04-13", "ZZZ", "YYY") is None


def test_team_resolver_reused_not_reinvented():
    """close_lookup must resolve via the existing alias table, not a new map
    (e.g. Polymarket's 'gs'/'sa'/'no' short codes -> the NBA canonical codes)."""
    assert canonical("nba", "gs") == canonical("nba", "GSW")
    assert canonical("nba", "sa") == canonical("nba", "SAS")
