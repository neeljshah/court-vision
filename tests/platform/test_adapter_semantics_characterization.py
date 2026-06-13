"""tests/platform/test_adapter_semantics_characterization.py

PIN-DOWN tests for two adapter semantics flagged by the W19 planning fleet.
These tests document CURRENT behavior; they fix NOTHING.

Semantic 1 — MLB h2h directionality (_add_context in domains/mlb/adapter.py)
  Key is frozenset([home, away]) → POOLED/ROLE-BLIND.  h2h_rate = home-win rate
  across ALL prior meetings regardless of which team was home in those meetings.
  Leak-free (strictly prior games only).  Acceptable tradeoff; not a bug.

Semantic 2 — Season-filter cold-start (MLB, tennis, soccer feature_bundle)
  seasons=[S2] filters the corpus BEFORE walk_forward runs → first S2 event
  starts at the prior (ELO_MEAN, not warm).  Leak-free (data exclusion, not
  future contamination).  Known fidelity tradeoff; documented here.

No future leaks found.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(date, home, away, season, hr, ar, seq=1, league="NL"):
    return {
        "event_id": f"{date}-{home}-{away}-{seq}",
        "date": date, "season": season,
        "home_team": home, "away_team": away,
        "home_runs": hr, "away_runs": ar,
        "target_home_win": 1 if hr > ar else 0,
        "game_seq": seq, "home_league": league,
    }


def _hyp(name="test"):
    from src.loop.signal import Hypothesis
    return Hypothesis(name=name, target="winprob", scope="pregame",
                      statement=f"{name} hypothesis")


# ---------------------------------------------------------------------------
# SEMANTIC 1 — MLB h2h directionality
# ---------------------------------------------------------------------------

class TestMLBH2HDirectionality:
    """h2h key = frozenset([home, away]) is ROLE-BLIND (pooled).

    h2h_rate is the HOME-TEAM win rate in ALL prior meetings between the two teams,
    not the named-team win rate.  When A wins every prior meeting as AWAY, h2h_rate
    in those rows is 0.0 (home team lost) — and that 0.0 carries forward when A is
    later HOME.  This is leak-free but directionally opaque.
    """

    @pytest.fixture
    def corpus(self):
        # NYY wins 3 times as AWAY team (BOS is home, BOS loses each time)
        # Then NYY hosts BOS — h2h looks up frozenset({"NYY","BOS"})
        return pd.DataFrame([
            _row("2015-04-01", "BOS", "NYY", 2015, 2, 5),  # NYY wins as away
            _row("2015-04-08", "BOS", "NYY", 2015, 1, 4),  # NYY wins as away
            _row("2015-04-15", "BOS", "NYY", 2015, 0, 3),  # NYY wins as away
            _row("2015-04-22", "NYY", "BOS", 2015, 6, 2),  # NYY now HOME
        ])

    def test_h2h_pooled_not_directional(self, corpus):
        """PINNED: NYY-home row sees h2h_n=3, h2h_rate=0.0 (BOS-as-home lost all 3).

        NYY's 3 prior away-wins appear as home-losses in the pooled mean.
        This confirms the POOLED / ROLE-BLIND semantic.
        """
        from domains.mlb.adapter import _add_context
        from domains.mlb.ratings import walk_forward_elo
        ctx = _add_context(walk_forward_elo(corpus))
        last = ctx.iloc[-1]
        assert last["home_team"] == "NYY"
        assert int(last["h2h_n"]) == 3, (
            f"Expected 3 pooled prior meetings, got h2h_n={last['h2h_n']}"
        )
        assert abs(float(last["h2h_rate"]) - 0.0) < 1e-9, (
            f"Expected h2h_rate=0.0 (BOS lost all 3 as home), got {last['h2h_rate']:.6f}. "
            "SEMANTIC: rate = home-win rate in prior meetings (role-blind pool)."
        )

    def test_h2h_default_on_first_meeting(self, corpus):
        """PINNED: Row 0 (first BOS-NYY meeting) has h2h_n=0, h2h_rate=0.5 (default)."""
        from domains.mlb.adapter import _add_context
        from domains.mlb.ratings import walk_forward_elo
        ctx = _add_context(walk_forward_elo(corpus))
        r0 = ctx.iloc[0]
        assert int(r0["h2h_n"]) == 0
        assert abs(float(r0["h2h_rate"]) - 0.5) < 1e-9, (
            f"Row 0 h2h_rate should be default 0.5, got {r0['h2h_rate']:.6f}"
        )

    def test_h2h_is_leak_free(self, corpus):
        """PINNED: Flipping row 0 outcome changes row 1 h2h_rate but NOT row 0's.

        Confirms h2h is strictly pre-game (post-game update only).
        """
        from domains.mlb.adapter import _add_context
        from domains.mlb.ratings import walk_forward_elo
        orig = _add_context(walk_forward_elo(corpus))

        mod = corpus.copy()
        mod.at[0, "home_runs"] = 10  # BOS now wins row 0
        mod.at[0, "away_runs"] = 1
        mod.at[0, "target_home_win"] = 1
        pert = _add_context(walk_forward_elo(mod))

        assert abs(float(orig.iloc[0]["h2h_rate"]) -
                   float(pert.iloc[0]["h2h_rate"])) < 1e-9, (
            "Row 0 h2h_rate must not change when row 0 outcome changes (leak guard)"
        )
        assert abs(float(orig.iloc[1]["h2h_rate"]) -
                   float(pert.iloc[1]["h2h_rate"])) > 1e-9, (
            "Row 1 h2h_rate SHOULD change when row 0 outcome changes (expected post-game update)"
        )


# ---------------------------------------------------------------------------
# SEMANTIC 2 — Season-filter cold-start
# ---------------------------------------------------------------------------

def _two_season_corpus():
    """Season 2015: 6 NYM/ATL games building Elo history.
    Season 2016: 4 games — the filtered slice under test."""
    return pd.DataFrame([
        # 2015: NYM dominates → diverged Elo
        _row("2015-04-01", "NYM", "ATL", 2015, 8, 2),
        _row("2015-04-08", "NYM", "ATL", 2015, 7, 1),
        _row("2015-04-15", "NYM", "ATL", 2015, 6, 0),
        _row("2015-04-22", "ATL", "NYM", 2015, 1, 5),
        _row("2015-04-29", "ATL", "NYM", 2015, 0, 4),
        _row("2015-05-06", "NYM", "ATL", 2015, 9, 3),
        # 2016
        _row("2016-04-01", "NYM", "ATL", 2016, 5, 3),
        _row("2016-04-08", "ATL", "NYM", 2016, 3, 4),
        _row("2016-04-15", "NYM", "ATL", 2016, 6, 2),
        _row("2016-04-22", "ATL", "NYM", 2016, 4, 5),
    ])


class TestSeasonFilterColdStart:
    """Cold-start: seasons=[2016] filters BEFORE walk_forward → first 2016 game
    uses ELO_MEAN (no prior history).  Leak-free; only a fidelity tradeoff.
    """

    @pytest.fixture
    def corpus(self):
        return _two_season_corpus()

    def test_cold_start_first_row_at_elo_mean(self, corpus):
        """PINNED: First 2016 game elo_home == elo_away == ELO_MEAN when filtered."""
        from domains.mlb.ratings import walk_forward_elo
        from domains.mlb.config import ELO_MEAN
        wf = walk_forward_elo(corpus[corpus["season"] == 2016].copy())
        first = wf.iloc[0]
        assert abs(float(first["elo_home"]) - ELO_MEAN) < 1e-6, (
            f"Cold-start elo_home={first['elo_home']:.4f} != ELO_MEAN={ELO_MEAN}"
        )
        assert abs(float(first["elo_away"]) - ELO_MEAN) < 1e-6, (
            f"Cold-start elo_away={first['elo_away']:.4f} != ELO_MEAN={ELO_MEAN}"
        )

    def test_warm_start_first_2016_row_differs_from_mean(self, corpus):
        """PINNED: Full-corpus walk warm-starts 2016 with diverged ratings."""
        from domains.mlb.ratings import walk_forward_elo
        from domains.mlb.config import ELO_MEAN
        wf = walk_forward_elo(corpus)
        first_2016 = wf[wf["season"] == 2016].iloc[0]
        deviation = max(
            abs(float(first_2016["elo_home"]) - ELO_MEAN),
            abs(float(first_2016["elo_away"]) - ELO_MEAN),
        )
        assert deviation > 1.0, (
            f"Warm-start: expected Elo divergence > 1.0 from 2015 history, "
            f"got max_deviation={deviation:.4f}"
        )

    def test_cold_vs_warm_differ_for_first_2016_game(self, corpus):
        """PINNED: cold-start elo_home != warm-start elo_home for first 2016 game."""
        from domains.mlb.ratings import walk_forward_elo
        from domains.mlb.config import ELO_MEAN
        cold_elo = float(
            walk_forward_elo(corpus[corpus["season"] == 2016].copy()).iloc[0]["elo_home"]
        )
        warm_elo = float(
            walk_forward_elo(corpus)[corpus["season"] == 2016]["elo_home"].iloc[0]
        )
        assert abs(cold_elo - warm_elo) > 1.0, (
            f"Cold ({cold_elo:.4f}) and warm ({warm_elo:.4f}) should differ for first 2016 game"
        )
        assert abs(cold_elo - ELO_MEAN) < 1e-6, (
            f"Cold-start elo_home should be ELO_MEAN={ELO_MEAN}, got {cold_elo:.4f}"
        )

    def test_cold_start_is_not_a_future_leak(self, corpus):
        """PINNED: Cold-start first p_home_elo = _p_home(MEAN, MEAN); no future data.

        The cold-start is a DATA EXCLUSION (fewer prior games), not contamination.
        """
        from domains.mlb.ratings import walk_forward_elo, _p_home
        from domains.mlb.config import ELO_MEAN
        wf = walk_forward_elo(corpus[corpus["season"] == 2016].copy())
        expected_p = _p_home(ELO_MEAN, ELO_MEAN)
        actual_p = float(wf.iloc[0]["p_home_elo"])
        assert abs(actual_p - expected_p) < 1e-9, (
            f"Cold-start p_home_elo={actual_p:.6f} != expected {expected_p:.6f}. "
            "Cold-start = data exclusion (leak-free), not future contamination."
        )

    def test_feature_bundle_seasons_filter_triggers_cold_start(self, corpus):
        """END-TO-END PINNED: MLBAdapter.feature_bundle(seasons=[2016]) cold-starts."""
        from domains.mlb.adapter import MLBAdapter
        from domains.mlb.config import ELO_MEAN
        adp = MLBAdapter(games_df=corpus)
        cold = adp.feature_bundle(_hyp("cold"), seasons=[2016])
        warm = adp.feature_bundle(_hyp("warm"), seasons=[2015, 2016])

        cold_elo_home = float(cold.base[0, 0])
        assert abs(cold_elo_home - ELO_MEAN) < 1e-6, (
            f"feature_bundle(seasons=[2016]) cold elo_home={cold_elo_home:.4f} != ELO_MEAN"
        )
        # First 2016 row in warm bundle
        warm_2016_idx = next(
            i for i, d in enumerate(warm.dates) if d.startswith("2016")
        )
        warm_elo_home = float(warm.base[warm_2016_idx, 0])
        assert abs(cold_elo_home - warm_elo_home) > 1.0, (
            f"Cold ({cold_elo_home:.4f}) and warm ({warm_elo_home:.4f}) should differ"
        )
