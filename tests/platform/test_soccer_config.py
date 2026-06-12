"""tests/platform/test_soccer_config.py — Offline tests for domains/soccer/config.py.

All tests run without any network access, torch, or heavy deps.
The suite verifies:
  1. Season code helpers are correct + round-trip clean.
  2. The three frozen dataclasses (EventRef, MarketSnapshot, Outcome) are immutable.
  3. Module-level constants have the expected values.
  4. F5 compliance: config.py imports ZERO forbidden modules (AST check).
  5. data/domains/soccer/.gitignore exists with the correct content.

Run: python -m pytest tests/platform/test_soccer_config.py -q --timeout=120
"""
from __future__ import annotations

import ast
import dataclasses
import datetime as dt
from pathlib import Path
from typing import List

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "domains" / "soccer" / "config.py"
GITIGNORE_PATH = REPO_ROOT / "data" / "domains" / "soccer" / ".gitignore"

# ---------------------------------------------------------------------------
# 1. Season code helpers
# ---------------------------------------------------------------------------


class TestSeasonHelpers:
    """season_code and season_start_year must be correct and invertible."""

    def test_season_code_2025(self) -> None:
        from domains.soccer.config import season_code

        assert season_code(2025) == "2526"

    def test_season_code_2015(self) -> None:
        from domains.soccer.config import season_code

        assert season_code(2015) == "1516"

    def test_season_start_year_round_trip(self) -> None:
        """season_start_year(season_code(y)) == y for all y in 2015..2025."""
        from domains.soccer.config import season_code, season_start_year

        for y in range(2015, 2026):
            assert season_start_year(season_code(y)) == y, (
                f"Round-trip failed for year {y}: "
                f"season_code={season_code(y)!r} -> {season_start_year(season_code(y))}"
            )

    def test_season_code_zero_padding(self) -> None:
        """season_code must zero-pad both components."""
        from domains.soccer.config import season_code

        # 2000 -> "0001"; 2009 -> "0910"
        assert season_code(2000) == "0001"
        assert season_code(2009) == "0910"

    def test_season_start_year_legacy_nineties(self) -> None:
        """season_start_year("9900") must return 1999 (pre-2000 boundary)."""
        from domains.soccer.config import season_start_year

        assert season_start_year("9900") == 1999


# ---------------------------------------------------------------------------
# 2. Frozen dataclasses
# ---------------------------------------------------------------------------


class TestFrozenDataclasses:
    """EventRef, MarketSnapshot, Outcome must be frozen (immutable)."""

    def _make_event(self) -> "EventRef":
        from domains.soccer.config import OVER_SIDE, SPORT_ID, UNDER_SIDE, EventRef

        return EventRef(
            sport=SPORT_ID,
            event_id="2025-01-01-E0-Arsenal-Chelsea",
            start_time_utc=dt.datetime(2025, 1, 1, 15, 0),
            entity_a=OVER_SIDE,
            entity_b=UNDER_SIDE,
            meta={"home_team": "Arsenal", "away_team": "Chelsea", "div": "E0", "season": "2526"},
        )

    def test_event_ref_is_frozen(self) -> None:
        ev = self._make_event()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            ev.sport = "mutated"  # type: ignore[misc]

    def test_market_snapshot_is_frozen(self) -> None:
        from domains.soccer.config import MarketSnapshot

        ev = self._make_event()
        snap = MarketSnapshot(
            event=ev,
            kind="close",
            price_a=1.95,
            price_b=1.95,
            book="pinnacle",
        )
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            snap.price_a = 9.99  # type: ignore[misc]

    def test_outcome_is_frozen(self) -> None:
        from domains.soccer.config import Outcome

        ev = self._make_event()
        out = Outcome(
            event=ev,
            winner="a",
            settled_at=dt.datetime(2025, 1, 1, 17, 0),
        )
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            out.winner = "b"  # type: ignore[misc]

    def test_frozen_via_dataclass_params(self) -> None:
        """Verify the frozen flag is set at the dataclass level (not just incidental)."""
        from domains.soccer.config import EventRef, MarketSnapshot, Outcome

        for cls in (EventRef, MarketSnapshot, Outcome):
            params = getattr(cls, "__dataclass_params__", None)
            assert params is not None, f"{cls.__name__} is not a dataclass"
            assert params.frozen is True, f"{cls.__name__} must be frozen=True"


# ---------------------------------------------------------------------------
# 3. Module-level constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Module-level constants must have the expected values."""

    def test_sport_id(self) -> None:
        from domains.soccer.config import SPORT_ID

        assert SPORT_ID == "soccer_fd"

    def test_stat_registry(self) -> None:
        from domains.soccer.config import STAT_REGISTRY

        assert STAT_REGISTRY == ("winprob",)

    def test_ou_line(self) -> None:
        from domains.soccer.config import OU_LINE

        assert OU_LINE == 2.5

    def test_all_six_leagues_present(self) -> None:
        from domains.soccer.config import LEAGUES

        expected = {"E0", "E1", "D1", "SP1", "I1", "F1"}
        assert expected == set(LEAGUES.keys()), (
            f"LEAGUES keys mismatch; expected {expected}, got {set(LEAGUES.keys())}"
        )

    def test_league_display_names(self) -> None:
        from domains.soccer.config import LEAGUES

        assert LEAGUES["E0"] == "Premier League"
        assert LEAGUES["D1"] == "Bundesliga"
        assert LEAGUES["SP1"] == "La Liga"

    def test_over_under_side_constants(self) -> None:
        from domains.soccer.config import OVER_SIDE, UNDER_SIDE

        assert OVER_SIDE == "O2.5"
        assert UNDER_SIDE == "U2.5"

    def test_entity_schema(self) -> None:
        from domains.soccer.config import ENTITY_SCHEMA

        assert ENTITY_SCHEMA["entity_type"] == "team"
        assert ENTITY_SCHEMA["team"] is True
        assert ENTITY_SCHEMA["id_field"] == "team_name"
        assert ENTITY_SCHEMA["id_dtype"] is str

    def test_walk_forward_constants(self) -> None:
        from domains.soccer.config import (
            ALPHA,
            MIN_MATCHES,
            PRIOR_GA,
            PRIOR_GF,
            RATE_CLIP,
            WF_TRAIN_FRAC,
        )

        assert ALPHA == 0.10
        assert PRIOR_GF == 1.35
        assert PRIOR_GA == 1.35
        assert RATE_CLIP == (0.2, 4.0)
        assert MIN_MATCHES == 6
        assert WF_TRAIN_FRAC == 0.75

    def test_data_paths(self) -> None:
        from domains.soccer.config import (
            DATA_DIR_REL,
            MATCHES_PARQUET,
            ODDS_PARQUET,
            RAW_DIR_REL,
        )

        assert DATA_DIR_REL == "data/domains/soccer"
        assert MATCHES_PARQUET == "data/domains/soccer/matches.parquet"
        assert ODDS_PARQUET == "data/domains/soccer/odds.parquet"
        assert "footballdata" in RAW_DIR_REL

    def test_url_template(self) -> None:
        from domains.soccer.config import URL_TEMPLATE

        assert "{season}" in URL_TEMPLATE
        assert "{div}" in URL_TEMPLATE
        assert "football-data.co.uk" in URL_TEMPLATE


# ---------------------------------------------------------------------------
# 4. F5 compliance — AST forbidden-import check
# ---------------------------------------------------------------------------

_BANNED_MODULES = (
    "src",
    "domains.nba",
    "domains.basketball_nba",
    "domains.tennis",
    "numpy",
    "pandas",
)


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
            f"domains/soccer/config.py contains forbidden imports (F5 violation): "
            f"{violations}"
        )

    def test_only_stdlib_imports(self) -> None:
        """All imports in config.py must be from the Python standard library."""
        _STDLIB_ALLOWED = {
            "__future__",
            "datetime",
            "dataclasses",
            "enum",
            "typing",
        }
        source = CONFIG_PATH.read_text(encoding="utf-8")
        imports = _collect_imports(source)
        non_stdlib = [
            imp for imp in imports
            if imp.split(".")[0] not in _STDLIB_ALLOWED
        ]
        assert not non_stdlib, (
            f"config.py must import only stdlib; found non-stdlib: {non_stdlib}"
        )

    def test_config_file_exists(self) -> None:
        assert CONFIG_PATH.exists(), f"config.py not found at {CONFIG_PATH}"


# ---------------------------------------------------------------------------
# 5. data/domains/soccer/.gitignore content check
# ---------------------------------------------------------------------------


class TestGitignore:
    """The soccer data .gitignore must exist and guard all files."""

    def test_gitignore_exists(self) -> None:
        assert GITIGNORE_PATH.exists(), (
            f"data/domains/soccer/.gitignore not found at {GITIGNORE_PATH}"
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
