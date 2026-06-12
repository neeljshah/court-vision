"""tests.platform.test_soccer_ratings — leak-free walk-forward goals ratings tests.

Covers:
  - Truncation-invariance (EXACT float equality, the key test)
  - First match uses priors for unseen teams
  - p_over monotone-increasing and bounded (0, 1)
  - Hand-computed 3-match EW sequence matches to 1e-12
  - Determinism: two walk_forward_goals runs produce identical output
  - walk_forward_goals columns are strictly pre-match (first appearance uses priors)
  - AST / forbidden-import check
"""
from __future__ import annotations

import ast
import datetime as dt
import math
import pathlib

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from domains.soccer.config import ALPHA, PRIOR_GF, PRIOR_GA, RATE_CLIP
from domains.soccer.ratings import (
    GoalsState,
    _lambdas,
    _p_over,
    _sorted,
    goals_state_asof,
    replay,
    walk_forward_goals,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_D = dt.date  # shorthand


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Build a matches DataFrame from a list of dicts."""
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


# 12-match synthetic corpus: 4 teams (Arsenal, Chelsea, Liverpool, Everton),
# 3 divisions to exercise the (date, div, home_team, away_team) sort key.
MATCHES_12 = _make_df(
    [
        # week 1
        {"date": "2024-08-10", "div": "E0", "home_team": "Arsenal",   "away_team": "Chelsea",    "fthg": 2, "ftag": 1},
        {"date": "2024-08-10", "div": "E0", "home_team": "Liverpool",  "away_team": "Everton",    "fthg": 3, "ftag": 0},
        # week 2
        {"date": "2024-08-17", "div": "E0", "home_team": "Chelsea",    "away_team": "Liverpool",  "fthg": 1, "ftag": 2},
        {"date": "2024-08-17", "div": "E0", "home_team": "Everton",    "away_team": "Arsenal",    "fthg": 0, "ftag": 3},
        # week 3
        {"date": "2024-08-24", "div": "E0", "home_team": "Arsenal",    "away_team": "Liverpool",  "fthg": 1, "ftag": 1},
        {"date": "2024-08-24", "div": "E0", "home_team": "Chelsea",    "away_team": "Everton",    "fthg": 2, "ftag": 2},
        # week 4
        {"date": "2024-08-31", "div": "E0", "home_team": "Liverpool",  "away_team": "Arsenal",    "fthg": 2, "ftag": 1},
        {"date": "2024-08-31", "div": "E0", "home_team": "Everton",    "away_team": "Chelsea",    "fthg": 1, "ftag": 0},
        # week 5
        {"date": "2024-09-07", "div": "E0", "home_team": "Arsenal",    "away_team": "Everton",    "fthg": 4, "ftag": 1},
        {"date": "2024-09-07", "div": "E0", "home_team": "Chelsea",    "away_team": "Liverpool",  "fthg": 0, "ftag": 2},
        # week 6
        {"date": "2024-09-14", "div": "E0", "home_team": "Everton",    "away_team": "Liverpool",  "fthg": 2, "ftag": 3},
        {"date": "2024-09-14", "div": "E0", "home_team": "Arsenal",    "away_team": "Chelsea",    "fthg": 1, "ftag": 1},
    ]
)

# Cut date: in the middle of the corpus (after week 3, before week 4)
CUT_DATE = _D(2024, 8, 31)

# 3-match toy sequence for hand-computation
TOY_3 = _make_df(
    [
        {"date": "2025-01-01", "div": "D1", "home_team": "TeamA", "away_team": "TeamB", "fthg": 2, "ftag": 1},
        {"date": "2025-01-08", "div": "D1", "home_team": "TeamB", "away_team": "TeamA", "fthg": 0, "ftag": 3},
        {"date": "2025-01-15", "div": "D1", "home_team": "TeamA", "away_team": "TeamB", "fthg": 1, "ftag": 0},
    ]
)


# ---------------------------------------------------------------------------
# 1. Truncation-invariance — exact float equality (the key test)
# ---------------------------------------------------------------------------


class TestTruncationInvariance:
    """goals_state_asof(full_df, D) == replay(full_df[full_df.date < D]) bitwise."""

    def _states_equal(self, s1: GoalsState, s2: GoalsState) -> None:
        """Assert every field of two GoalsState objects is exactly equal."""
        assert set(s1.gf_ew.keys()) == set(s2.gf_ew.keys()), "gf_ew keys differ"
        for k in s1.gf_ew:
            assert s1.gf_ew[k] == s2.gf_ew[k], f"gf_ew[{k!r}] not bitwise equal"

        assert set(s1.ga_ew.keys()) == set(s2.ga_ew.keys()), "ga_ew keys differ"
        for k in s1.ga_ew:
            assert s1.ga_ew[k] == s2.ga_ew[k], f"ga_ew[{k!r}] not bitwise equal"

        assert set(s1.counts.keys()) == set(s2.counts.keys()), "counts keys differ"
        for k in s1.counts:
            assert s1.counts[k] == s2.counts[k], f"counts[{k!r}] differ"

        assert s1.league_mu_home == s2.league_mu_home, "league_mu_home not bitwise equal"
        assert s1.league_mu_away == s2.league_mu_away, "league_mu_away not bitwise equal"
        assert s1.n_processed == s2.n_processed, "n_processed differs"

    def test_asof_equals_filtered_replay(self):
        """The main truncation-invariance assertion."""
        full_df = MATCHES_12.copy()

        # Path A: asof on full df
        state_a = goals_state_asof(full_df, CUT_DATE)

        # Path B: replay on pre-filtered subset
        subset = full_df[pd.to_datetime(full_df["date"]).dt.date < CUT_DATE].copy()
        state_b = replay(subset)

        self._states_equal(state_a, state_b)

    def test_asof_early_cutoff(self):
        """Truncation-invariance holds for a cutoff that falls after only a few matches."""
        full_df = MATCHES_12.copy()
        cut = _D(2024, 8, 17)  # after week 1 only

        state_a = goals_state_asof(full_df, cut)
        subset = full_df[pd.to_datetime(full_df["date"]).dt.date < cut].copy()
        state_b = replay(subset)

        self._states_equal(state_a, state_b)

    def test_asof_end_cutoff(self):
        """Truncation-invariance holds for a cutoff past the last match."""
        full_df = MATCHES_12.copy()
        cut = _D(2099, 1, 1)

        state_a = goals_state_asof(full_df, cut)
        state_b = replay(full_df)

        self._states_equal(state_a, state_b)


# ---------------------------------------------------------------------------
# 2. First match of history uses priors
# ---------------------------------------------------------------------------


class TestPriorInitialisation:
    def test_first_match_lambda_uses_priors(self):
        """Before any match is processed, unseen teams yield PRIOR_GF/PRIOR_GA lambdas."""
        # Single match; the pre-match state is fresh (all priors)
        single = _make_df(
            [{"date": "2024-01-01", "div": "E0", "home_team": "Home", "away_team": "Away",
              "fthg": 2, "ftag": 1}]
        )
        out = walk_forward_goals(single)
        # Both teams unseen before the first match → rates equal PRIOR_GF/PRIOR_GA
        # lam_home = clip(PRIOR_GF) * clip(PRIOR_GA) / mu_all
        lo, hi = RATE_CLIP
        mu_all = max((PRIOR_GF + PRIOR_GA) / 2.0, 0.25)
        expected_lh = min(max(PRIOR_GF, lo), hi) * min(max(PRIOR_GA, lo), hi) / mu_all
        expected_la = expected_lh  # symmetric
        assert abs(out["lam_home"].iloc[0] - expected_lh) < 1e-15
        assert abs(out["lam_away"].iloc[0] - expected_la) < 1e-15

    def test_replay_empty_until_cutoff(self):
        """replay() with until before all data returns an empty-state GoalsState."""
        state = replay(MATCHES_12, until=_D(2020, 1, 1))
        assert state.n_processed == 0
        assert len(state.gf_ew) == 0
        assert state.league_mu_home == PRIOR_GF
        assert state.league_mu_away == PRIOR_GA


# ---------------------------------------------------------------------------
# 3. p_over monotone-increasing, bounded (0, 1)
# ---------------------------------------------------------------------------


class TestPOver:
    def test_monotone(self):
        values = [0.5, 1.0, 2.0, 2.7, 3.5, 5.0, 8.0]
        probs = [_p_over(v) for v in values]
        for i in range(len(probs) - 1):
            assert probs[i] < probs[i + 1], (
                f"p_over not monotone at lam={values[i]:.1f}: {probs[i]:.6f} >= {probs[i+1]:.6f}"
            )

    def test_bounded(self):
        for lam in [0.01, 0.5, 1.0, 2.0, 3.5, 10.0]:
            p = _p_over(lam)
            assert 0.0 < p < 1.0, f"p_over({lam}) = {p} out of (0,1)"

    def test_specific_values(self):
        # At lam=3.0: P(Pois(3)>=3) = 1 - e^{-3}(1 + 3 + 4.5) = 1 - 8.5*e^{-3}
        lam = 3.0
        expected = 1.0 - math.exp(-3.0) * (1.0 + 3.0 + 4.5)
        assert abs(_p_over(lam) - expected) < 1e-15
        assert _p_over(2.0) < _p_over(3.5)


# ---------------------------------------------------------------------------
# 4. Hand-computed 3-match EW sequence
# ---------------------------------------------------------------------------


class TestHandComputed:
    """Manually compute EW updates for TOY_3 and compare."""

    def test_three_match_ew_sequence(self):
        """Exact EW values after 3 matches verified by hand."""
        a = ALPHA

        # Match 1: TeamA(home)=2, TeamB(away)=1 — both unseen, init to PRIOR
        gf_A = PRIOR_GF
        ga_A = PRIOR_GA
        gf_B = PRIOR_GF
        ga_B = PRIOR_GA
        # update after match 1
        gf_A = gf_A + a * (2.0 - gf_A)   # home scored 2
        ga_A = ga_A + a * (1.0 - ga_A)   # home conceded 1
        gf_B = gf_B + a * (1.0 - gf_B)   # away scored 1
        ga_B = ga_B + a * (2.0 - ga_B)   # away conceded 2

        # Match 2: TeamB(home)=0, TeamA(away)=3
        # update after match 2
        gf_B = gf_B + a * (0.0 - gf_B)
        ga_B = ga_B + a * (3.0 - ga_B)
        gf_A = gf_A + a * (3.0 - gf_A)
        ga_A = ga_A + a * (0.0 - ga_A)

        # Match 3: TeamA(home)=1, TeamB(away)=0
        # update after match 3
        gf_A2 = gf_A + a * (1.0 - gf_A)
        ga_A2 = ga_A + a * (0.0 - ga_A)
        gf_B2 = gf_B + a * (0.0 - gf_B)
        ga_B2 = ga_B + a * (1.0 - ga_B)

        state = replay(TOY_3)

        assert abs(state.gf_ew["TeamA"] - gf_A2) < 1e-12, f"gf_A: {state.gf_ew['TeamA']} vs {gf_A2}"
        assert abs(state.ga_ew["TeamA"] - ga_A2) < 1e-12, f"ga_A: {state.ga_ew['TeamA']} vs {ga_A2}"
        assert abs(state.gf_ew["TeamB"] - gf_B2) < 1e-12, f"gf_B: {state.gf_ew['TeamB']} vs {gf_B2}"
        assert abs(state.ga_ew["TeamB"] - ga_B2) < 1e-12, f"ga_B: {state.ga_ew['TeamB']} vs {ga_B2}"
        assert state.counts["TeamA"] == 3
        assert state.counts["TeamB"] == 3
        assert state.n_processed == 3

    def test_league_mu_three_matches(self):
        """League mu EW update matches hand computation."""
        a = ALPHA
        mu_h = PRIOR_GF
        mu_a = PRIOR_GA
        goals = [(2, 1), (0, 3), (1, 0)]
        for fthg, ftag in goals:
            mu_h = mu_h + a * (fthg - mu_h)
            mu_a = mu_a + a * (ftag - mu_a)

        state = replay(TOY_3)
        assert abs(state.league_mu_home - mu_h) < 1e-12
        assert abs(state.league_mu_away - mu_a) < 1e-12


# ---------------------------------------------------------------------------
# 5. Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_walk_forward_identical_runs(self):
        """Two calls to walk_forward_goals on the same df produce identical output."""
        out1 = walk_forward_goals(MATCHES_12.copy())
        out2 = walk_forward_goals(MATCHES_12.copy())
        assert_frame_equal(out1, out2, check_exact=True)

    def test_walk_forward_column_count(self):
        """Output has exactly 4 extra columns added."""
        original_cols = set(MATCHES_12.columns)
        out = walk_forward_goals(MATCHES_12.copy())
        extra = set(out.columns) - original_cols
        assert extra == {"lam_home", "lam_away", "lam_total", "p_over25"}


# ---------------------------------------------------------------------------
# 6. walk_forward_goals columns are strictly pre-match
# ---------------------------------------------------------------------------


class TestPreMatchSnapshot:
    def test_first_team_appearance_uses_priors(self):
        """The very first time each team appears its pre-match lambda derives from PRIOR."""
        single = _make_df(
            [{"date": "2024-01-01", "div": "E0", "home_team": "NewHome",
              "away_team": "NewAway", "fthg": 5, "ftag": 0}]
        )
        out = walk_forward_goals(single)

        lo, hi = RATE_CLIP
        mu_all = max((PRIOR_GF + PRIOR_GA) / 2.0, 0.25)
        prior_clipped = min(max(PRIOR_GF, lo), hi)  # = PRIOR_GF (within clip range)
        expected_lam = prior_clipped * prior_clipped / mu_all

        assert abs(out["lam_home"].iloc[0] - expected_lam) < 1e-15
        assert abs(out["lam_away"].iloc[0] - expected_lam) < 1e-15

    def test_lam_total_equals_sum(self):
        """lam_total == lam_home + lam_away for every row."""
        out = walk_forward_goals(MATCHES_12.copy())
        for _, row in out.iterrows():
            assert abs(row["lam_total"] - (row["lam_home"] + row["lam_away"])) < 1e-15

    def test_p_over25_derived_from_lam_total(self):
        """p_over25 == _p_over(lam_total) for every row."""
        out = walk_forward_goals(MATCHES_12.copy())
        for _, row in out.iterrows():
            expected = _p_over(row["lam_total"])
            assert abs(row["p_over25"] - expected) < 1e-15

    def test_second_appearance_differs_from_prior(self):
        """After the first match, a team's pre-match lambda should differ from the naive prior."""
        # Two sequential matches involving TeamX — on its second appearance its
        # rates should have been updated by the first result.
        two = _make_df(
            [
                {"date": "2024-01-01", "div": "E0", "home_team": "TeamX",
                 "away_team": "TeamY", "fthg": 4, "ftag": 0},
                {"date": "2024-01-08", "div": "E0", "home_team": "TeamX",
                 "away_team": "TeamZ", "fthg": 1, "ftag": 1},
            ]
        )
        out = walk_forward_goals(two)
        lam_first = out["lam_home"].iloc[0]
        lam_second = out["lam_home"].iloc[1]
        # After scoring 4, TeamX's gf_ew should be higher than PRIOR → second lam_home > first
        assert lam_second != lam_first, "Second appearance should use updated rate, not same as first"

    def test_all_lambdas_positive(self):
        """All lambda values must be strictly positive."""
        out = walk_forward_goals(MATCHES_12.copy())
        assert (out["lam_home"] > 0).all()
        assert (out["lam_away"] > 0).all()
        assert (out["lam_total"] > 0).all()

    def test_p_over25_in_unit_interval(self):
        """All p_over25 values must be in (0, 1)."""
        out = walk_forward_goals(MATCHES_12.copy())
        assert (out["p_over25"] > 0).all()
        assert (out["p_over25"] < 1).all()


# ---------------------------------------------------------------------------
# 7. AST forbidden-import test
# ---------------------------------------------------------------------------


class TestForbiddenImports:
    """F5 compliance: ratings.py must not import src.*, domains.nba, domains.basketball_nba,
    domains.tennis, or use random / datetime.now."""

    RATINGS_PATH = (
        pathlib.Path(__file__).parent.parent.parent
        / "domains" / "soccer" / "ratings.py"
    )
    FORBIDDEN_MODULES = {
        "src",
        "domains.nba",
        "domains.basketball_nba",
        "domains.tennis",
        "random",
    }

    def _get_imports(self) -> list[str]:
        source = self.RATINGS_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.append(node.module)
        return imported

    def test_no_forbidden_modules(self):
        imports = self._get_imports()
        for mod in imports:
            for forbidden in self.FORBIDDEN_MODULES:
                assert not mod.startswith(forbidden), (
                    f"ratings.py imports forbidden module: {mod!r} (matches {forbidden!r})"
                )

    def test_tennis_string_absent(self):
        """The string 'tennis' must not appear anywhere in ratings.py."""
        source = self.RATINGS_PATH.read_text(encoding="utf-8")
        assert "tennis" not in source, "ratings.py must not reference 'tennis'"

    def test_allowed_imports_only(self):
        """Only stdlib, numpy, pandas, and domains.soccer.config are allowed."""
        ALLOWED_PREFIXES = {"__future__", "math", "datetime", "dataclasses", "typing",
                            "numpy", "pandas", "domains.soccer"}
        imports = self._get_imports()
        for mod in imports:
            ok = any(mod == p or mod.startswith(p + ".") for p in ALLOWED_PREFIXES)
            assert ok, f"ratings.py has unexpected import: {mod!r}"
