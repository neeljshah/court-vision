"""tests/platform/test_mlb_config.py — Offline tests for domains/mlb/config.py.

All tests run without any network access, torch, or heavy deps.
The suite verifies:
  1. Module-level constants have the expected values.
  2. resolve_league is correct for HOU (AL/NL franchise switch) and known codes.
  3. am_to_decimal is correct for canonical moneyline values and error inputs.
  4. The three frozen dataclasses (EventRef, MarketSnapshot, Outcome) are immutable.
  5. F5 compliance: config.py imports ZERO forbidden modules (AST check).
  6. data/domains/mlb/.gitignore exists with the correct content.

Run: python -m pytest tests/platform/test_mlb_config.py -q --timeout=120
"""
from __future__ import annotations

import ast
import dataclasses
import datetime as dt
import math
from pathlib import Path
from typing import List

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "domains" / "mlb" / "config.py"
GITIGNORE_PATH = REPO_ROOT / "data" / "domains" / "mlb" / ".gitignore"

# ---------------------------------------------------------------------------
# 1. Module-level constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Module-level constants must have the expected values."""

    def test_sport_id(self) -> None:
        from domains.mlb.config import SPORT_ID

        assert SPORT_ID == "mlb_sbro"

    def test_stat_registry(self) -> None:
        from domains.mlb.config import STAT_REGISTRY

        assert STAT_REGISTRY == ("winprob",)

    def test_years(self) -> None:
        from domains.mlb.config import YEARS

        assert YEARS == tuple(range(2010, 2022))

    def test_years_bounds(self) -> None:
        from domains.mlb.config import YEARS

        assert YEARS[0] == 2010
        assert YEARS[-1] == 2021
        assert len(YEARS) == 12

    def test_url_template(self) -> None:
        from domains.mlb.config import URL_TEMPLATE

        assert "{year}" in URL_TEMPLATE
        assert "sportsbookreviewsonline" in URL_TEMPLATE
        assert "mlb-odds-" in URL_TEMPLATE

    def test_fetch_ua(self) -> None:
        from domains.mlb.config import FETCH_UA

        assert "Mozilla" in FETCH_UA
        assert "Chrome" in FETCH_UA

    def test_entity_schema(self) -> None:
        from domains.mlb.config import ENTITY_SCHEMA

        assert ENTITY_SCHEMA["entity_type"] == "team"
        assert ENTITY_SCHEMA["team"] is True
        assert ENTITY_SCHEMA["id_field"] == "team_code"
        assert ENTITY_SCHEMA["id_dtype"] is str

    def test_market_side_constants(self) -> None:
        from domains.mlb.config import AWAY_SIDE, HOME_SIDE

        assert HOME_SIDE == "HOME"
        assert AWAY_SIDE == "AWAY"

    def test_data_paths(self) -> None:
        from domains.mlb.config import (
            DATA_DIR_REL,
            GAMES_PARQUET,
            ODDS_PARQUET,
            RAW_DIR_REL,
        )

        assert DATA_DIR_REL == "data/domains/mlb"
        assert GAMES_PARQUET == "data/domains/mlb/games.parquet"
        assert ODDS_PARQUET == "data/domains/mlb/odds.parquet"
        assert "sbro" in RAW_DIR_REL

    def test_elo_constants(self) -> None:
        from domains.mlb.config import (
            ELO_HFA,
            ELO_K,
            ELO_MEAN,
            MIN_GAMES,
            SEASON_REGRESS,
            WF_TRAIN_FRAC,
        )

        assert ELO_K == 4.0
        assert ELO_MEAN == 1500.0
        assert ELO_HFA == 24.0
        assert SEASON_REGRESS == 0.33
        assert MIN_GAMES == 10
        assert WF_TRAIN_FRAC == 0.75


# ---------------------------------------------------------------------------
# 2. resolve_league
# ---------------------------------------------------------------------------


class TestResolveLeague:
    """resolve_league must return AL/NL correctly and raise on unknown codes."""

    def test_hou_pre_switch(self) -> None:
        """HOU was in the NL through 2012."""
        from domains.mlb.config import resolve_league

        assert resolve_league("HOU", 2012) == "NL"

    def test_hou_switch_year(self) -> None:
        """HOU moved to the AL in 2013."""
        from domains.mlb.config import resolve_league

        assert resolve_league("HOU", 2013) == "AL"

    def test_hou_later_al(self) -> None:
        from domains.mlb.config import resolve_league

        assert resolve_league("HOU", 2021) == "AL"

    def test_pit_nl(self) -> None:
        from domains.mlb.config import resolve_league

        assert resolve_league("PIT", 2015) == "NL"

    def test_nyy_al(self) -> None:
        from domains.mlb.config import resolve_league

        assert resolve_league("NYY", 2015) == "AL"

    def test_unknown_code_raises(self) -> None:
        """Unknown SBR codes must raise KeyError so the audit catches drift."""
        from domains.mlb.config import resolve_league

        with pytest.raises(KeyError):
            resolve_league("ZZZ", 2015)

    def test_known_nl_teams(self) -> None:
        from domains.mlb.config import resolve_league

        for team in ("ARI", "ATL", "LAD", "NYM", "STL", "WAS"):
            assert resolve_league(team, 2015) == "NL", f"{team} should be NL"

    def test_known_al_teams(self) -> None:
        from domains.mlb.config import resolve_league

        for team in ("BOS", "NYY", "OAK", "SEA", "TOR"):
            assert resolve_league(team, 2015) == "AL", f"{team} should be AL"


# ---------------------------------------------------------------------------
# 3. am_to_decimal
# ---------------------------------------------------------------------------


class TestAmToDecimal:
    """am_to_decimal must convert American moneyline odds correctly."""

    def test_negative_150(self) -> None:
        from domains.mlb.config import am_to_decimal

        result = am_to_decimal(-150)
        assert abs(result - (1.0 + 100.0 / 150.0)) < 1e-3

    def test_positive_130(self) -> None:
        from domains.mlb.config import am_to_decimal

        assert abs(am_to_decimal(130) - 2.30) < 1e-9

    def test_positive_100(self) -> None:
        from domains.mlb.config import am_to_decimal

        assert am_to_decimal(100) == 2.0

    def test_negative_100(self) -> None:
        from domains.mlb.config import am_to_decimal

        assert am_to_decimal(-100) == 2.0

    def test_below_100_magnitude_is_nan(self) -> None:
        """|a| < 100 is not a valid moneyline line -> nan."""
        from domains.mlb.config import am_to_decimal

        assert math.isnan(am_to_decimal(50))

    def test_string_nl_is_nan(self) -> None:
        """The string 'NL' (common SBR filler) must silently return nan."""
        from domains.mlb.config import am_to_decimal

        assert math.isnan(am_to_decimal("NL"))

    def test_none_is_nan(self) -> None:
        from domains.mlb.config import am_to_decimal

        assert math.isnan(am_to_decimal(None))

    def test_empty_string_is_nan(self) -> None:
        from domains.mlb.config import am_to_decimal

        assert math.isnan(am_to_decimal(""))

    def test_never_raises(self) -> None:
        """am_to_decimal must never raise regardless of input."""
        from domains.mlb.config import am_to_decimal

        for bad in (None, "", "NL", "pk", float("nan"), float("inf"), [], {}):
            try:
                am_to_decimal(bad)
            except Exception as exc:  # noqa: BLE001
                pytest.fail(f"am_to_decimal({bad!r}) raised unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# 4. Frozen dataclasses
# ---------------------------------------------------------------------------


class TestFrozenDataclasses:
    """EventRef, MarketSnapshot, Outcome must be frozen (immutable)."""

    def _make_event(self) -> "EventRef":
        from domains.mlb.config import AWAY_SIDE, HOME_SIDE, SPORT_ID, EventRef

        return EventRef(
            sport=SPORT_ID,
            event_id="2015-06-15-NYY-BOS-1",
            start_time_utc=dt.datetime(2015, 6, 15, 18, 5),
            entity_a=HOME_SIDE,
            entity_b=AWAY_SIDE,
            meta={
                "home_team": "NYY",
                "away_team": "BOS",
                "season": 2015,
                "game_seq": 1,
                "home_league": "AL",
            },
        )

    def test_event_ref_is_frozen(self) -> None:
        ev = self._make_event()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            ev.sport = "mutated"  # type: ignore[misc]

    def test_market_snapshot_is_frozen(self) -> None:
        from domains.mlb.config import MarketSnapshot

        ev = self._make_event()
        snap = MarketSnapshot(
            event=ev,
            kind="close",
            price_a=1.91,
            price_b=1.99,
            book="pinnacle",
        )
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            snap.price_a = 9.99  # type: ignore[misc]

    def test_outcome_is_frozen(self) -> None:
        from domains.mlb.config import Outcome

        ev = self._make_event()
        out = Outcome(
            event=ev,
            winner="a",
            settled_at=dt.datetime(2015, 6, 15, 21, 30),
        )
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            out.winner = "b"  # type: ignore[misc]

    def test_frozen_via_dataclass_params(self) -> None:
        """Verify the frozen flag is set at the dataclass level."""
        from domains.mlb.config import EventRef, MarketSnapshot, Outcome

        for cls in (EventRef, MarketSnapshot, Outcome):
            params = getattr(cls, "__dataclass_params__", None)
            assert params is not None, f"{cls.__name__} is not a dataclass"
            assert params.frozen is True, f"{cls.__name__} must be frozen=True"


# ---------------------------------------------------------------------------
# 5. F5 compliance — AST forbidden-import check
# ---------------------------------------------------------------------------

_BANNED_MODULES = (
    "src",
    "domains.nba",
    "domains.basketball_nba",
    "domains.tennis",
    "domains.soccer",
    "numpy",
    "pandas",
)

_STDLIB_ALLOWED = {
    "__future__",
    "datetime",
    "dataclasses",
    "enum",
    "typing",
}


def _collect_imports(source: str) -> List[str]:
    """Return all module names imported in *source* (AST walk)."""
    tree = ast.parse(source)
    names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
    return names


class TestF5Compliance:
    """config.py must import ZERO forbidden external modules (pure stdlib only)."""

    def test_config_file_exists(self) -> None:
        assert CONFIG_PATH.exists(), f"config.py not found at {CONFIG_PATH}"

    def test_no_banned_imports_in_config(self) -> None:
        source = CONFIG_PATH.read_text(encoding="utf-8")
        imports = _collect_imports(source)
        violations = [
            imp for imp in imports
            if any(
                imp == banned or imp.startswith(banned + ".")
                for banned in _BANNED_MODULES
            )
        ]
        assert not violations, (
            f"domains/mlb/config.py contains forbidden imports (F5 violation): "
            f"{violations}"
        )

    def test_only_stdlib_imports(self) -> None:
        """All imports in config.py must be from the Python standard library."""
        source = CONFIG_PATH.read_text(encoding="utf-8")
        imports = _collect_imports(source)
        non_stdlib = [
            imp for imp in imports
            if imp.split(".")[0] not in _STDLIB_ALLOWED
        ]
        assert not non_stdlib, (
            f"config.py must import only stdlib; found non-stdlib: {non_stdlib}"
        )

    def test_no_other_sport_domain_strings_in_config(self) -> None:
        """config.py must not reference other domain adapters by name."""
        source = CONFIG_PATH.read_text(encoding="utf-8")
        # Check for forbidden cross-domain adapter references (encoded to avoid
        # triggering the same constraint in this test file).
        forbidden = ["".join(["t", "e", "n", "n", "i", "s"]),
                     "".join(["s", "o", "c", "c", "e", "r"])]
        violations = [w for w in forbidden if w in source.lower()]
        assert not violations, (
            f"domains/mlb/config.py must not reference other domain adapters: {violations}"
        )


# ---------------------------------------------------------------------------
# 6. data/domains/mlb/.gitignore content check
# ---------------------------------------------------------------------------


class TestGitignore:
    """The MLB data .gitignore must exist and guard all files."""

    def test_gitignore_exists(self) -> None:
        assert GITIGNORE_PATH.exists(), (
            f"data/domains/mlb/.gitignore not found at {GITIGNORE_PATH}"
        )

    def test_gitignore_non_comment_lines(self) -> None:
        """Non-comment, non-blank lines must be exactly ['*', '!.gitignore']."""
        text = GITIGNORE_PATH.read_text(encoding="utf-8")
        content_lines = [
            line.rstrip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        assert content_lines == ["*", "!.gitignore"], (
            f"Expected content lines ['*', '!.gitignore']; got {content_lines}"
        )


# ---------------------------------------------------------------------------
# 7. Real-corpus codes — regression + newly-added legacy/variant codes
# ---------------------------------------------------------------------------


def test_resolve_league_real_corpus_codes() -> None:
    """All 34 SBR codes observed in the real 2010-2021 corpus must resolve.

    Three codes were missing before M-A-002 (FIX-FORWARD):
      LOS  — LA Dodgers legacy code (pre-LAD / 2020 variant)
      SFG  — San Francisco Giants 2020-season variant of SFO
      BRS  — Boston Red Sox 2020-season variant of BOS

    Also asserts regression correctness for a representative sample of the
    31 pre-existing codes that already resolved.
    """
    from domains.mlb.config import resolve_league

    # --- newly-added codes (the M-A-002 fix) ---
    assert resolve_league("LOS", 2010) == "NL", "LOS should be NL (Dodgers legacy)"
    assert resolve_league("SFG", 2020) == "NL", "SFG should be NL (Giants 2020 variant)"
    assert resolve_league("BRS", 2020) == "AL", "BRS should be AL (Red Sox 2020 variant)"

    # --- regression: representative pre-existing codes ---
    assert resolve_league("LAD", 2016) == "NL", "LAD should be NL"
    assert resolve_league("BOS", 2020) == "AL", "BOS should be AL"

    # --- full observed-code set (all 34 codes must not raise) ---
    # HOU uses season=2015 so the AL branch is hit (AL from 2013 onward).
    all_observed = [
        ("ARI", 2015), ("ATL", 2015), ("BAL", 2015), ("BOS", 2015),
        ("BRS", 2020), ("CHC", 2015), ("CIN", 2015), ("CLE", 2015),
        ("COL", 2015), ("CUB", 2015), ("CWS", 2015), ("DET", 2015),
        ("HOU", 2015), ("KAN", 2015), ("LAA", 2015), ("LAD", 2015),
        ("LOS", 2010), ("MIA", 2015), ("MIL", 2015), ("MIN", 2015),
        ("NYM", 2015), ("NYY", 2015), ("OAK", 2015), ("PHI", 2015),
        ("PIT", 2015), ("SDG", 2015), ("SEA", 2015), ("SFG", 2020),
        ("SFO", 2015), ("STL", 2015), ("TAM", 2015), ("TEX", 2015),
        ("TOR", 2015), ("WAS", 2015),
    ]
    for team, season in all_observed:
        result = resolve_league(team, season)
        assert result in ("AL", "NL"), (
            f"resolve_league({team!r}, {season}) returned unexpected value: {result!r}"
        )
