"""P0.2 — Tests for src/brain/coverage.py.

Coverage taxonomy (ARCHITECTURE §4 L0, CORRECTIONS C1):
  - mc_teams()       : derived from team_rates.json keys (30 teams in live data)
  - shotzone_teams() : derived from pbp_attributes.parquet 'team' column (13 teams)
  - coverage_class() : maps (home, away) to "mc_full" | "shotzone" | "league_min"
                       with precedence mc_full > shotzone > league_min

Tests are robust: they read the real live sets and assert membership / count lower
bounds rather than brittle exact lists, so they stay green if the data grows.
"""
from __future__ import annotations

import json
import os
import sys
from typing import FrozenSet

# ---------------------------------------------------------------------------
# Path setup — ensure src/ is importable regardless of cwd.
# ---------------------------------------------------------------------------
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

import brain.coverage as cov  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clear() -> None:
    """Clear module-level lru_caches so each test starts with a fresh read."""
    cov._reset_caches()


# ---------------------------------------------------------------------------
# mc_teams() — team_rates.json
# ---------------------------------------------------------------------------


class TestMcTeams:
    """mc_teams() must reflect the real team_rates.json keys."""

    def setup_method(self) -> None:
        _clear()

    def test_returns_frozenset(self) -> None:
        result = cov.mc_teams()
        assert isinstance(result, frozenset)

    def test_count_at_least_30(self) -> None:
        """C1 correction: team_rates.json has 30 teams — never fewer than 30."""
        result = cov.mc_teams()
        assert len(result) >= 30, f"Expected >= 30 mc teams, got {len(result)}: {sorted(result)}"

    def test_matches_json_keys(self) -> None:
        """mc_teams() must exactly match team_rates.json keys."""
        json_path = os.path.join(_ROOT, "data", "cache", "team_system", "team_rates.json")
        with open(json_path, encoding="utf-8") as fh:
            expected: FrozenSet[str] = frozenset(json.load(fh).keys())
        assert cov.mc_teams() == expected

    def test_finals_2026_teams_present(self) -> None:
        """Build-check: the 2026 Finals pair (NYK, SAS) must both be in mc_teams()."""
        mc = cov.mc_teams()
        assert "NYK" in mc, "NYK (2026 Finals home) must be in mc_teams()"
        assert "SAS" in mc, "SAS (2026 Finals away) must be in mc_teams()"

    def test_all_30_canonical_teams_present(self) -> None:
        """All 30 canonical NBA abbreviations must be in mc_teams()."""
        mc = cov.mc_teams()
        for abbr in cov._CANONICAL_30:
            assert abbr in mc, f"{abbr} missing from mc_teams()"

    def test_result_is_cached(self) -> None:
        """lru_cache: two calls return the exact same object."""
        assert cov.mc_teams() is cov.mc_teams()


# ---------------------------------------------------------------------------
# shotzone_teams() — pbp_attributes.parquet
# ---------------------------------------------------------------------------


class TestShotzoneTeams:
    """shotzone_teams() must reflect the real pbp_attributes.parquet 'team' column."""

    # Discovery 02 G4 / CORRECTIONS C1: the known 13-team set.
    _KNOWN_13 = frozenset([
        "ATL", "CLE", "GSW", "LAL", "MIN", "NOP",
        "NYK", "OKC", "ORL", "PHI", "POR", "SAS", "WAS",
    ])

    def setup_method(self) -> None:
        _clear()

    def test_returns_frozenset(self) -> None:
        result = cov.shotzone_teams()
        assert isinstance(result, frozenset)

    def test_count_at_least_13(self) -> None:
        """pbp_attributes.parquet currently has 13 teams; count must not shrink."""
        result = cov.shotzone_teams()
        assert len(result) >= 13, (
            f"Expected >= 13 shotzone teams, got {len(result)}: {sorted(result)}"
        )

    def test_known_13_teams_are_members(self) -> None:
        """All 13 known pbp-attributes teams must be present."""
        sz = cov.shotzone_teams()
        for abbr in self._KNOWN_13:
            assert abbr in sz, f"{abbr} missing from shotzone_teams()"

    def test_finals_2026_teams_present(self) -> None:
        """NYK and SAS are in the 13-team pbp_attributes set."""
        sz = cov.shotzone_teams()
        assert "NYK" in sz, "NYK must be in shotzone_teams()"
        assert "SAS" in sz, "SAS must be in shotzone_teams()"

    def test_gsw_present(self) -> None:
        """GSW is one of the known 13 shotzone teams."""
        assert "GSW" in cov.shotzone_teams()

    def test_dal_absent(self) -> None:
        """DAL is NOT in the 13-team pbp_attributes parquet (known non-shotzone team)."""
        sz = cov.shotzone_teams()
        assert "DAL" not in sz, (
            f"DAL should NOT be in shotzone_teams(); current set: {sorted(sz)}"
        )

    def test_result_is_cached(self) -> None:
        """lru_cache: two calls return the exact same object."""
        assert cov.shotzone_teams() is cov.shotzone_teams()


# ---------------------------------------------------------------------------
# coverage_class() — precedence and correctness
# ---------------------------------------------------------------------------


class TestCoverageClass:
    """coverage_class(home, away) must map matchups to the correct fidelity tier."""

    def setup_method(self) -> None:
        _clear()

    # --- return-value contract ---

    def test_returns_string(self) -> None:
        result = cov.coverage_class("NYK", "SAS")
        assert isinstance(result, str)

    def test_return_value_in_coverage_classes(self) -> None:
        result = cov.coverage_class("NYK", "SAS")
        assert result in cov.COVERAGE_CLASSES

    # --- Finals 2026 matchup ---

    def test_finals_2026_nyk_sas_is_mc_full(self) -> None:
        """NYK vs SAS are both in mc_teams() → coverage_class must be 'mc_full'."""
        assert cov.coverage_class("NYK", "SAS") == "mc_full"

    def test_finals_2026_reversed_is_mc_full(self) -> None:
        """Order of arguments must not change the tier for the Finals pair."""
        assert cov.coverage_class("SAS", "NYK") == "mc_full"

    # --- mc_full precedence ---

    def test_both_in_mc_yields_mc_full(self) -> None:
        """Any pair of teams both in mc_teams() returns 'mc_full'."""
        mc = cov.mc_teams()
        assert len(mc) >= 2
        teams = sorted(mc)
        # Pick a non-Finals pair to also cover a different slice
        t1, t2 = teams[0], teams[1]
        assert cov.coverage_class(t1, t2) == "mc_full", (
            f"Expected mc_full for ({t1},{t2}), both in mc_teams()"
        )

    def test_mc_full_precedence_over_shotzone(self) -> None:
        """When both teams are in mc AND shotzone, mc_full must win (precedence rule)."""
        mc = cov.mc_teams()
        sz = cov.shotzone_teams()
        # NYK + SAS are in both sets; confirm mc_full wins.
        assert "NYK" in mc and "NYK" in sz
        assert "SAS" in mc and "SAS" in sz
        assert cov.coverage_class("NYK", "SAS") == "mc_full"

    # --- league_min for unknown teams ---

    def test_nonexistent_pair_yields_league_min(self) -> None:
        """A clearly fake/non-existent team pair must degrade gracefully to league_min."""
        result = cov.coverage_class("FAKE", "TEAM")
        assert result == "league_min", (
            f"Expected league_min for ('FAKE','TEAM'), got {result!r}"
        )

    def test_one_known_one_unknown_yields_league_min(self) -> None:
        """If one team is out of both sets, the result must be league_min."""
        result = cov.coverage_class("NYK", "FAKE")
        assert result == "league_min"

    # --- shotzone class: reachable when mc is artificially restricted ---

    def test_shotzone_class_reachable_when_mc_restricted(self, monkeypatch) -> None:
        """When mc_teams() excludes both teams but they are in shotzone, class == 'shotzone'.

        This tests the precedence logic directly by patching mc_teams() to return an
        empty frozenset.  shotzone_teams() still returns the live 13-team set.
        """
        _clear()
        monkeypatch.setattr(cov, "mc_teams", lambda: frozenset())
        # NYK and SAS ARE in shotzone_teams per the live parquet.
        result = cov.coverage_class("NYK", "SAS")
        assert result == "shotzone", (
            f"Expected 'shotzone' when mc is empty and both teams in shotzone, got {result!r}"
        )

    def test_shotzone_single_member_yields_league_min(self, monkeypatch) -> None:
        """If only one team is in shotzone (mc empty), still falls back to league_min."""
        _clear()
        monkeypatch.setattr(cov, "mc_teams", lambda: frozenset())
        # NYK is in shotzone, FAKE is not.
        result = cov.coverage_class("NYK", "FAKE")
        assert result == "league_min"

    def test_league_min_when_both_sets_empty(self, monkeypatch) -> None:
        """If both mc and shotzone return empty (file-not-found scenario), return league_min."""
        _clear()
        monkeypatch.setattr(cov, "mc_teams", lambda: frozenset())
        monkeypatch.setattr(cov, "shotzone_teams", lambda: frozenset())
        result = cov.coverage_class("NYK", "SAS")
        assert result == "league_min"


# ---------------------------------------------------------------------------
# COVERAGE_CLASSES sentinel
# ---------------------------------------------------------------------------


class TestCoverageClassesSentinel:
    """COVERAGE_CLASSES must contain exactly the three valid tokens."""

    def test_three_elements(self) -> None:
        assert len(cov.COVERAGE_CLASSES) == 3

    def test_contains_mc_full(self) -> None:
        assert "mc_full" in cov.COVERAGE_CLASSES

    def test_contains_shotzone(self) -> None:
        assert "shotzone" in cov.COVERAGE_CLASSES

    def test_contains_league_min(self) -> None:
        assert "league_min" in cov.COVERAGE_CLASSES


# ---------------------------------------------------------------------------
# league_teams() — superset guarantee
# ---------------------------------------------------------------------------


class TestLeagueTeams:
    """league_teams() must cover all 30 canonical teams and be a superset of mc/shotzone."""

    def setup_method(self) -> None:
        _clear()

    def test_count_equals_30(self) -> None:
        """Union with _CANONICAL_30 always yields exactly 30 (no franchise changes expected)."""
        lt = cov.league_teams()
        assert len(lt) == 30, f"Expected 30 league teams, got {len(lt)}"

    def test_superset_of_mc_teams(self) -> None:
        assert cov.mc_teams().issubset(cov.league_teams())

    def test_superset_of_shotzone_teams(self) -> None:
        assert cov.shotzone_teams().issubset(cov.league_teams())

    def test_canonical_30_subset(self) -> None:
        assert cov._CANONICAL_30.issubset(cov.league_teams())
