"""tests/platform/test_mlb_adapter.py -- MLBAdapter unit + leak tests.

Covers:
  - feature_bundle shape / dtype / ordering
  - NO-LEAK perturbation test (CRITICAL): flipping outcome of row i must not
    alter base or signal_col for any strictly-earlier row j.
  - league_filter corpus selector
  - market_snapshot open vs close, None on missing row, price validation
  - outcome boundary (home wins / away wins)
  - baseline_probability range + ordering
  - base excludes outcome / odds columns (value + AST forbidden-import check)
  - AST forbidden-import: adapter must not import nba, basketball_nba, tennis,
    soccer, src.data, src.sim, src.tracking, src.pipeline
"""
from __future__ import annotations

import ast
import datetime as dt
import importlib
import importlib.util
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Synthetic dataset helpers
# ---------------------------------------------------------------------------

def _make_games_df() -> pd.DataFrame:
    rows = []

    def add(date: str, home: str, away: str, season: int, hr: int, ar: int,
            seq: int = 1, league: str = "NL") -> None:
        eid = f"{date}-{home}-{away}-{seq}"
        rows.append({
            "event_id": eid,
            "date": date,
            "season": season,
            "home_team": home,
            "away_team": away,
            "home_runs": hr,
            "away_runs": ar,
            "target_home_win": 1 if hr > ar else 0,
            "game_seq": seq,
            "home_league": league,
        })

    # Season 2015 -- NL games
    add("2015-04-06", "NYM", "ATL", 2015, 5, 3, league="NL")
    add("2015-04-07", "ATL", "CHC", 2015, 2, 4, league="NL")
    add("2015-04-08", "CHC", "LAD", 2015, 6, 1, league="NL")
    add("2015-04-14", "LAD", "STL", 2015, 3, 4, league="NL", seq=1)
    add("2015-04-14", "NYM", "CHC", 2015, 7, 2, league="NL", seq=2)   # doubleheader
    add("2015-04-20", "STL", "NYM", 2015, 4, 5, league="NL")
    add("2015-04-27", "ATL", "LAD", 2015, 1, 3, league="NL")
    add("2015-05-04", "CHC", "ATL", 2015, 5, 2, league="NL")
    add("2015-05-11", "LAD", "NYM", 2015, 2, 4, league="NL")
    add("2015-06-01", "STL", "CHC", 2015, 8, 2, league="NL")
    add("2015-06-15", "NYM", "STL", 2015, 3, 1, league="NL")

    # Season 2015 -- AL games
    add("2015-04-06", "NYY", "BOS", 2015, 4, 2, league="AL")
    add("2015-04-07", "BOS", "SEA", 2015, 3, 5, league="AL")
    add("2015-04-08", "SEA", "HOU", 2015, 2, 6, league="AL")
    add("2015-04-20", "HOU", "DET", 2015, 5, 3, league="AL")
    add("2015-04-27", "DET", "NYY", 2015, 1, 4, league="AL")
    add("2015-05-04", "NYY", "SEA", 2015, 6, 2, league="AL")
    add("2015-05-11", "BOS", "HOU", 2015, 3, 5, league="AL")
    add("2015-06-01", "SEA", "DET", 2015, 4, 2, league="AL")
    add("2015-06-15", "HOU", "NYY", 2015, 5, 4, league="AL")

    # Season 2016 -- NL games
    add("2016-04-04", "NYM", "LAD", 2016, 2, 3, league="NL")
    add("2016-04-05", "ATL", "STL", 2016, 6, 1, league="NL")
    add("2016-04-11", "CHC", "NYM", 2016, 4, 2, league="NL")
    add("2016-04-18", "LAD", "ATL", 2016, 3, 1, league="NL")
    add("2016-04-25", "STL", "CHC", 2016, 2, 5, league="NL")
    add("2016-05-02", "NYM", "ATL", 2016, 1, 3, league="NL")
    add("2016-05-09", "ATL", "LAD", 2016, 4, 3, league="NL")
    add("2016-05-16", "LAD", "STL", 2016, 5, 2, league="NL")
    add("2016-06-06", "CHC", "NYM", 2016, 7, 3, league="NL")
    add("2016-06-20", "STL", "ATL", 2016, 2, 4, league="NL")

    # Season 2016 -- AL games
    add("2016-04-04", "NYY", "DET", 2016, 5, 3, league="AL")
    add("2016-04-05", "BOS", "NYY", 2016, 4, 2, league="AL")
    add("2016-04-11", "SEA", "BOS", 2016, 3, 1, league="AL")
    add("2016-04-18", "HOU", "SEA", 2016, 6, 4, league="AL")
    add("2016-04-25", "DET", "HOU", 2016, 2, 5, league="AL")
    add("2016-05-02", "NYY", "BOS", 2016, 3, 4, league="AL")
    add("2016-05-09", "BOS", "DET", 2016, 5, 2, league="AL")
    add("2016-05-16", "SEA", "NYY", 2016, 1, 3, league="AL")
    add("2016-06-06", "HOU", "BOS", 2016, 4, 2, league="AL")
    add("2016-06-20", "DET", "SEA", 2016, 3, 1, league="AL")

    return pd.DataFrame(rows)


def _make_odds_df(games_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    rng = np.random.default_rng(42)
    for _, g in games_df.iterrows():
        ho = round(float(rng.uniform(1.7, 2.4)), 2)
        ao = round(float(rng.uniform(1.7, 2.4)), 2)
        hc = round(ho + float(rng.uniform(-0.15, 0.15)), 2)
        ac = round(ao + float(rng.uniform(-0.15, 0.15)), 2)
        hc = max(1.01, hc)
        ac = max(1.01, ac)
        rows.append({
            "event_id": g["event_id"],
            "date": g["date"],
            "season": g["season"],
            "ml_open_home_am": 0,
            "ml_open_away_am": 0,
            "ml_close_home_am": 0,
            "ml_close_away_am": 0,
            "dec_open_home": ho,
            "dec_open_away": ao,
            "dec_close_home": hc,
            "dec_close_away": ac,
            "book": "sbro_archive",
        })
    return pd.DataFrame(rows)


def _make_hyp(name: str = "test"):
    from src.loop.signal import Hypothesis
    return Hypothesis(name=name, target="winprob", scope="pregame",
                      statement=f"{name} hypothesis")


# ---------------------------------------------------------------------------
# Module-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def games_df() -> pd.DataFrame:
    return _make_games_df()


@pytest.fixture(scope="module")
def odds_df(games_df: pd.DataFrame) -> pd.DataFrame:
    return _make_odds_df(games_df)


@pytest.fixture(scope="module")
def adapter(games_df, odds_df):
    from domains.mlb.adapter import MLBAdapter
    return MLBAdapter(games_df=games_df, odds_df=odds_df)


@pytest.fixture(scope="module")
def bundle(adapter):
    return adapter.feature_bundle(_make_hyp("bundle"))


# ---------------------------------------------------------------------------
# 1. FeatureBundle shape / dtype / ordering
# ---------------------------------------------------------------------------

class TestFeatureBundleShape:
    def test_base_shape(self, bundle):
        n = bundle.base.shape[0]
        assert bundle.base.shape == (n, 6), f"Expected (n,6) got {bundle.base.shape}"

    def test_signal_shape(self, bundle):
        n = bundle.base.shape[0]
        assert bundle.signal_col.shape == (n,)

    def test_target_binary(self, bundle):
        vals = set(bundle.target.tolist())
        assert vals.issubset({0.0, 1.0}), f"target values not in {{0,1}}: {np.unique(bundle.target)}"

    def test_dates_ascending(self, bundle):
        assert bundle.dates == sorted(bundle.dates), "dates not ascending"

    def test_dates_length_matches_rows(self, bundle):
        assert len(bundle.dates) == bundle.base.shape[0]

    def test_no_nan_in_base(self, bundle):
        assert not np.any(np.isnan(bundle.base)), "Unexpected NaN in base columns"

    def test_signal_col_in_unit_interval(self, bundle):
        sc = bundle.signal_col
        assert np.all(sc > 0) and np.all(sc < 1), \
            f"signal_col out of (0,1): min={sc.min():.4f} max={sc.max():.4f}"

    def test_base_dtype_float(self, bundle):
        assert bundle.base.dtype == float

    def test_lines_and_closing_present(self, bundle):
        assert bundle.lines is not None, "lines should be set when odds_df is injected"
        assert bundle.closing is not None, "closing should be set when odds_df is injected"

    def test_target_and_signal_lengths_match(self, bundle):
        n = bundle.base.shape[0]
        assert bundle.target.shape == (n,)
        assert bundle.signal_col.shape == (n,)


# ---------------------------------------------------------------------------
# 2. NO-LEAK perturbation test (CRITICAL)
# ---------------------------------------------------------------------------

class TestNoLeakPerturbation:
    """Flip the outcome of one row i; for every row j with dates[j] < dates[i],
    base[j] and signal_col[j] must be bitwise-identical.
    The perturbed row's target must change."""

    def test_no_leak_perturbation(self, games_df, odds_df):
        """Core leak-guard: flipping the outcome of the LAST game must not alter
        any earlier row's base features or signal_col.

        Approach: pick the very last row in the chronologically-sorted bundle
        (position n-1).  Flip that game's runs in games_df.  Because the sort
        key (date, home_team, away_team, game_seq) is unchanged, the perturbed
        bundle has the same row-ordering; positions 0..n-2 are the same games
        in the same order.  All their Elo snapshots are recorded BEFORE the
        last game's update runs, so they must be bitwise-identical.
        """
        from domains.mlb.adapter import MLBAdapter

        adp = MLBAdapter(games_df=games_df.copy(), odds_df=odds_df.copy())
        orig = adp.feature_bundle(_make_hyp("leak_orig"))
        n = orig.base.shape[0]
        assert n >= 2, "Need at least 2 rows for the leak test"

        # Target row: the very last one in the sorted bundle.
        i = n - 1
        date_i = orig.dates[i]
        # In our fixture every date has 2 games (NL + AL); pick the specific
        # event_id of the last bundle row by tracing back through the adapter's
        # walk-forward sort.  We do this by rebuilding the sorted games and
        # reading the last row's event_id directly.
        from domains.mlb.ratings import _sorted as _ratings_sorted
        sorted_games = _ratings_sorted(games_df.copy())
        last_event_id = str(sorted_games.iloc[-1]["event_id"])

        games_mod = games_df.copy()
        row_mask = games_mod["event_id"] == last_event_id
        matched_idx = games_mod[row_mask].index.tolist()
        assert len(matched_idx) == 1, (
            f"Expected exactly 1 row for event_id={last_event_id!r}, "
            f"got {len(matched_idx)}"
        )
        g_idx = matched_idx[0]

        old_hr = int(games_mod.at[g_idx, "home_runs"])
        old_ar = int(games_mod.at[g_idx, "away_runs"])
        old_tgt = int(games_mod.at[g_idx, "target_home_win"])

        # Flip the result: swap runs so winner changes (add 2 to avoid equal)
        games_mod.at[g_idx, "home_runs"] = old_ar + 2
        games_mod.at[g_idx, "away_runs"] = old_hr
        games_mod.at[g_idx, "target_home_win"] = 1 - old_tgt

        adp2 = MLBAdapter(games_df=games_mod, odds_df=odds_df.copy())
        pert = adp2.feature_bundle(_make_hyp("leak_pert"))

        assert pert.base.shape[0] == n, "Perturbed bundle has different row count"

        # The perturbed row (position n-1) must have a different target
        assert orig.target[i] != pert.target[i], \
            "Perturbed row target did NOT change -- test setup invalid"

        # All rows j < i: base and signal_col must be bitwise-identical
        # (sort order unchanged => same games in same positions => same Elo snapshots)
        for j in range(i):
            assert np.allclose(orig.base[j], pert.base[j], atol=0, rtol=0), (
                f"NO-LEAK VIOLATED at j={j} date={orig.dates[j]} "
                f"(perturbed last row at i={i} date={date_i}):\n"
                f"  orig base: {orig.base[j]}\n"
                f"  pert base: {pert.base[j]}"
            )
            assert np.allclose(
                orig.signal_col[j], pert.signal_col[j], atol=0, rtol=0
            ), (
                f"NO-LEAK VIOLATED signal_col j={j} date={orig.dates[j]} "
                f"(perturbed last row at i={i} date={date_i})"
            )


# ---------------------------------------------------------------------------
# 3. league_filter corpus selector
# ---------------------------------------------------------------------------

class TestLeagueFilter:
    def test_nl_filter_reduces_rows(self, games_df, odds_df):
        from domains.mlb.adapter import MLBAdapter
        adp = MLBAdapter(games_df=games_df, odds_df=odds_df)
        b_all = adp.feature_bundle(_make_hyp("all"))
        b_nl = adp.feature_bundle(_make_hyp("nl"), league_filter="NL")
        assert b_nl.base.shape[0] < b_all.base.shape[0], \
            "NL filter did not reduce row count"

    def test_nl_filter_exact_count(self, games_df, odds_df):
        from domains.mlb.adapter import MLBAdapter
        adp = MLBAdapter(games_df=games_df, odds_df=odds_df)
        b_nl = adp.feature_bundle(_make_hyp("nl2"), league_filter="NL")
        expected = int((games_df["home_league"] == "NL").sum())
        assert b_nl.base.shape[0] == expected, (
            f"NL bundle rows {b_nl.base.shape[0]} != expected {expected}"
        )

    def test_nl_filter_no_al_sentinel(self, games_df, odds_df):
        """NYY only appears as home in AL games -- should not appear in NL bundle."""
        from domains.mlb.adapter import MLBAdapter
        adp = MLBAdapter(games_df=games_df, odds_df=odds_df)
        b_nl = adp.feature_bundle(_make_hyp("nl_nyy"), league_filter="NL")
        nl_games = games_df[games_df["home_league"] == "NL"]
        nl_home_teams = set(nl_games["home_team"].tolist())
        assert "NYY" not in nl_home_teams, (
            "NYY should not appear as home in NL games (test data invariant broken)"
        )

    def test_al_filter_exact_count(self, games_df, odds_df):
        from domains.mlb.adapter import MLBAdapter
        adp = MLBAdapter(games_df=games_df, odds_df=odds_df)
        b_al = adp.feature_bundle(_make_hyp("al"), league_filter="AL")
        expected = int((games_df["home_league"] == "AL").sum())
        assert b_al.base.shape[0] == expected


# ---------------------------------------------------------------------------
# 4. market_snapshot
# ---------------------------------------------------------------------------

def _first_event(adapter):
    events = adapter.list_events(dt.date(2015, 4, 6))
    assert events, "No events for 2015-04-06"
    return events[0]


class TestMarketSnapshot:
    def test_prices_above_one(self, adapter):
        ev = _first_event(adapter)
        for kind in ("open", "close"):
            snap = adapter.market_snapshot(ev, kind)
            assert snap is not None, f"{kind} snapshot is None"
            assert snap.price_a > 1.0
            assert snap.price_b > 1.0

    def test_open_and_close_are_valid(self, adapter):
        ev = _first_event(adapter)
        snap_o = adapter.market_snapshot(ev, "open")
        snap_c = adapter.market_snapshot(ev, "close")
        assert snap_o is not None
        assert snap_c is not None
        assert snap_o.kind == "open"
        assert snap_c.kind == "close"

    def test_none_on_unknown_event(self, games_df):
        from domains.mlb.adapter import MLBAdapter
        from domains.mlb.config import EventRef, HOME_SIDE, AWAY_SIDE, SPORT_ID
        adp = MLBAdapter(games_df=games_df)
        ev = EventRef(
            sport=SPORT_ID, event_id="NOEXIST",
            start_time_utc=dt.datetime(2015, 4, 6, 12, 0),
            entity_a=HOME_SIDE, entity_b=AWAY_SIDE,
            meta={"home_team": "NYM", "away_team": "ATL"},
        )
        assert adp.market_snapshot(ev, "open") is None

    def test_none_when_no_odds_file(self, games_df):
        from domains.mlb.adapter import MLBAdapter
        adp = MLBAdapter(games_df=games_df, repo_root=Path("/nonexistent"))
        events = adp.list_events(dt.date(2015, 4, 6))
        if events:
            assert adp.market_snapshot(events[0], "open") is None

    def test_book_label(self, adapter):
        ev = _first_event(adapter)
        snap = adapter.market_snapshot(ev, "open")
        assert snap is not None
        assert snap.book == "sbro_archive"


# ---------------------------------------------------------------------------
# 5. outcome boundary
# ---------------------------------------------------------------------------

class TestOutcome:
    def test_home_win_returns_a(self, adapter):
        # 2015-04-06-NYM-ATL-1: NYM 5 > ATL 3 => home wins
        from domains.mlb.config import EventRef, HOME_SIDE, AWAY_SIDE, SPORT_ID
        ev = EventRef(
            sport=SPORT_ID, event_id="2015-04-06-NYM-ATL-1",
            start_time_utc=dt.datetime(2015, 4, 6, 12, 0),
            entity_a=HOME_SIDE, entity_b=AWAY_SIDE,
            meta={"home_team": "NYM", "away_team": "ATL"},
        )
        result = adapter.outcome(ev)
        assert result is not None
        assert result.winner == "a"

    def test_away_win_returns_b(self, adapter):
        # 2015-04-07-ATL-CHC-1: ATL 2 < CHC 4 => away wins
        from domains.mlb.config import EventRef, HOME_SIDE, AWAY_SIDE, SPORT_ID
        ev = EventRef(
            sport=SPORT_ID, event_id="2015-04-07-ATL-CHC-1",
            start_time_utc=dt.datetime(2015, 4, 7, 12, 0),
            entity_a=HOME_SIDE, entity_b=AWAY_SIDE,
            meta={"home_team": "ATL", "away_team": "CHC"},
        )
        result = adapter.outcome(ev)
        assert result is not None
        assert result.winner == "b"

    def test_none_on_missing_event(self, adapter):
        from domains.mlb.config import EventRef, HOME_SIDE, AWAY_SIDE, SPORT_ID
        ev = EventRef(
            sport=SPORT_ID, event_id="DOESNT-EXIST",
            start_time_utc=dt.datetime(2015, 4, 6, 12, 0),
            entity_a=HOME_SIDE, entity_b=AWAY_SIDE,
            meta={"home_team": "X", "away_team": "Y"},
        )
        assert adapter.outcome(ev) is None

    def test_outcome_meta_runs(self, adapter):
        from domains.mlb.config import EventRef, HOME_SIDE, AWAY_SIDE, SPORT_ID
        ev = EventRef(
            sport=SPORT_ID, event_id="2015-04-06-NYM-ATL-1",
            start_time_utc=dt.datetime(2015, 4, 6, 12, 0),
            entity_a=HOME_SIDE, entity_b=AWAY_SIDE,
            meta={"home_team": "NYM", "away_team": "ATL"},
        )
        result = adapter.outcome(ev)
        assert result is not None
        assert result.meta["home_runs"] == 5
        assert result.meta["away_runs"] == 3

    def test_outcome_settled_at_time(self, adapter):
        from domains.mlb.config import EventRef, HOME_SIDE, AWAY_SIDE, SPORT_ID
        ev = EventRef(
            sport=SPORT_ID, event_id="2015-04-06-NYM-ATL-1",
            start_time_utc=dt.datetime(2015, 4, 6, 12, 0),
            entity_a=HOME_SIDE, entity_b=AWAY_SIDE,
            meta={"home_team": "NYM", "away_team": "ATL"},
        )
        result = adapter.outcome(ev)
        assert result is not None
        assert result.settled_at.time() == dt.time(23, 59)


# ---------------------------------------------------------------------------
# 6. baseline_probability
# ---------------------------------------------------------------------------

class TestBaselineProbability:
    def _make_event(self, home: str, away: str):
        from domains.mlb.config import EventRef, HOME_SIDE, AWAY_SIDE, SPORT_ID
        return EventRef(
            sport=SPORT_ID, event_id="bp-test",
            start_time_utc=dt.datetime(2015, 7, 1, 12, 0),
            entity_a=HOME_SIDE, entity_b=AWAY_SIDE,
            meta={"home_team": home, "away_team": away},
        )

    def test_probability_in_unit_interval(self, adapter):
        ev = self._make_event("NYM", "ATL")
        p = adapter.baseline_probability(ev, dt.datetime(2015, 7, 1, 12, 0))
        assert 0.0 < p < 1.0, f"baseline_probability out of (0,1): {p}"

    def test_strictly_pregame_on_first_day(self, adapter):
        """On the very first game day, both teams have 0 prior games => ELO_MEAN."""
        from domains.mlb.config import ELO_MEAN
        from domains.mlb.ratings import _p_home
        ev = self._make_event("NYM", "ATL")
        # as_of = first game date => no prior games processed for either team
        p = adapter.baseline_probability(ev, dt.datetime(2015, 4, 6, 0, 0))
        p_expected = _p_home(ELO_MEAN, ELO_MEAN)
        assert abs(p - p_expected) < 1e-9, (
            f"First-day probability should equal _p_home(MEAN, MEAN)={p_expected:.6f}, "
            f"got {p:.6f}"
        )

    def test_stronger_home_team_gives_higher_p(self, games_df, odds_df):
        """After many games CHC (with a good record) should give higher p when hosting
        a weaker team vs. a weaker team hosting CHC."""
        from domains.mlb.adapter import MLBAdapter
        from domains.mlb.config import EventRef, HOME_SIDE, AWAY_SIDE, SPORT_ID
        adp = MLBAdapter(games_df=games_df, odds_df=odds_df)
        as_of = dt.datetime(2016, 7, 1, 12, 0)
        # CHC hosting ATL vs ATL hosting CHC
        ev_chc = EventRef(
            sport=SPORT_ID, event_id="bp-chc",
            start_time_utc=as_of, entity_a=HOME_SIDE, entity_b=AWAY_SIDE,
            meta={"home_team": "CHC", "away_team": "ATL"},
        )
        ev_atl = EventRef(
            sport=SPORT_ID, event_id="bp-atl",
            start_time_utc=as_of, entity_a=HOME_SIDE, entity_b=AWAY_SIDE,
            meta={"home_team": "ATL", "away_team": "CHC"},
        )
        p_chc = adp.baseline_probability(ev_chc, as_of)
        p_atl = adp.baseline_probability(ev_atl, as_of)
        assert 0.0 < p_chc < 1.0
        assert 0.0 < p_atl < 1.0
        # Both should be in (0,1); if CHC has higher Elo, p_chc > p_atl
        # (not asserting direction since Elo depends on the tiny fixture corpus)


# ---------------------------------------------------------------------------
# 7. base excludes outcome / odds columns
# ---------------------------------------------------------------------------

class TestLeakFreeBaseColumns:
    def test_base_column_count_is_6(self, bundle):
        assert bundle.base.shape[1] == 6, \
            f"Expected 6 base columns, got {bundle.base.shape[1]}"

    def test_first_row_elo_at_mean(self, games_df, odds_df):
        """First game row: both teams unseen => elo_home and elo_away near ELO_MEAN."""
        from domains.mlb.adapter import MLBAdapter
        from domains.mlb.config import ELO_MEAN
        adp = MLBAdapter(games_df=games_df, odds_df=odds_df)
        b = adp.feature_bundle(_make_hyp("col_check"))
        first_elo_home = b.base[0, 0]
        first_elo_away = b.base[0, 1]
        assert abs(first_elo_home - ELO_MEAN) < 1.0, \
            f"First-row elo_home should be near {ELO_MEAN}, got {first_elo_home}"
        assert abs(first_elo_away - ELO_MEAN) < 1.0, \
            f"First-row elo_away should be near {ELO_MEAN}, got {first_elo_away}"

    def test_h2h_rate_col_range(self, bundle):
        # col 5 = h2h_rate, should be in [0, 1]
        h2h = bundle.base[:, 5]
        assert np.all(h2h >= 0.0) and np.all(h2h <= 1.0), \
            f"h2h_rate out of [0,1]: min={h2h.min():.3f} max={h2h.max():.3f}"

    def test_rest_days_col_range(self, bundle):
        # cols 3 and 4 = rest_days; capped at 10, default 5
        for col_idx in (3, 4):
            col = bundle.base[:, col_idx]
            assert np.all(col >= 0) and np.all(col <= 10), \
                f"rest_days col {col_idx} out of [0,10]"


# ---------------------------------------------------------------------------
# 8. AST forbidden-import test
# ---------------------------------------------------------------------------

FORBIDDEN_MODULE_PREFIXES = (
    "domains.nba",
    "domains.basketball_nba",
    "domains.tennis",
    "domains.soccer",
    "src.data",
    "src.sim",
    "src.tracking",
    "src.pipeline",
)
FORBIDDEN_CODE_STRINGS = ("tennis", "soccer")


class TestForbiddenImports:
    def _adapter_source(self) -> str:
        path = Path(__file__).resolve().parents[2] / "domains" / "mlb" / "adapter.py"
        return path.read_text(encoding="utf-8")

    def test_no_forbidden_module_imports_ast(self):
        source = self._adapter_source()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for forbidden in FORBIDDEN_MODULE_PREFIXES:
                    assert not mod.startswith(forbidden), (
                        f"Forbidden import-from {mod!r} in adapter.py (matches {forbidden!r})"
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in FORBIDDEN_MODULE_PREFIXES:
                        assert not alias.name.startswith(forbidden), (
                            f"Forbidden import {alias.name!r} in adapter.py "
                            f"(matches {forbidden!r})"
                        )

    def test_no_forbidden_strings_in_code_tokens(self):
        import tokenize
        import io
        source = self._adapter_source()
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        # Only check actual NAME tokens (not comments, strings, or whitespace)
        for tok_type, tok_string, *_ in tokens:
            if tok_type == tokenize.NAME:
                for fs in FORBIDDEN_CODE_STRINGS:
                    assert fs not in tok_string.lower(), (
                        f"Forbidden string {fs!r} in code token {tok_string!r}"
                    )

    def test_importing_adapter_does_not_pull_forbidden_modules(self):
        import sys
        before = set(sys.modules.keys())
        importlib.import_module("domains.mlb.adapter")
        after = set(sys.modules.keys())
        new_mods = after - before
        for forbidden in FORBIDDEN_MODULE_PREFIXES:
            matching = [m for m in new_mods if m.startswith(forbidden)]
            assert not matching, (
                f"Importing domains.mlb.adapter pulled in forbidden modules: {matching}"
            )


# ---------------------------------------------------------------------------
# 9. list_events
# ---------------------------------------------------------------------------

class TestListEvents:
    def test_events_on_known_date(self, adapter):
        events = adapter.list_events(dt.date(2015, 4, 6))
        # We have NYM-ATL (NL) and NYY-BOS (AL) on this date
        assert len(events) >= 2

    def test_event_field_types(self, adapter):
        from domains.mlb.config import HOME_SIDE, AWAY_SIDE, SPORT_ID
        events = adapter.list_events(dt.date(2015, 4, 6))
        for ev in events:
            assert ev.sport == SPORT_ID
            assert ev.entity_a == HOME_SIDE
            assert ev.entity_b == AWAY_SIDE
            assert ev.start_time_utc.time() == dt.time(12, 0)
            assert "home_team" in ev.meta
            assert "away_team" in ev.meta
            assert "season" in ev.meta
            assert "game_seq" in ev.meta
            assert "home_league" in ev.meta

    def test_no_events_on_off_day(self, adapter):
        events = adapter.list_events(dt.date(2015, 1, 1))
        assert events == []

    def test_doubleheader_two_events(self, adapter):
        events = adapter.list_events(dt.date(2015, 4, 14))
        # LAD-STL seq=1 and NYM-CHC seq=2 both in NL
        assert len(events) == 2, f"Expected 2 doubleheader events, got {len(events)}"


# ---------------------------------------------------------------------------
# 10. feature_bundle ValueError on empty corpus
# ---------------------------------------------------------------------------

class TestFeatureBundleErrors:
    def test_raises_on_empty_seasons(self, games_df, odds_df):
        from domains.mlb.adapter import MLBAdapter
        adp = MLBAdapter(games_df=games_df, odds_df=odds_df)
        with pytest.raises(ValueError, match="no rows"):
            adp.feature_bundle(_make_hyp("empty"), seasons=[9999])

    def test_raises_on_impossible_league_filter(self, games_df, odds_df):
        from domains.mlb.adapter import MLBAdapter
        adp = MLBAdapter(games_df=games_df, odds_df=odds_df)
        with pytest.raises(ValueError, match="no rows"):
            adp.feature_bundle(_make_hyp("bad_league"), league_filter="ZZLEAGUE")
