"""
Coverage-set helpers for the control-brain layer.

ROADMAP phase : L0 DATA & FRESHNESS substrate (ARCHITECTURE §4 L0)
GATE required : MUST_RESOLVE #2 in RED_C — "fix the fidelity-scope taxonomy:
                mc_teams, shotzone_teams, league_teams derived from the actual
                parquets at build time, NOT hardcoded."
FLAG           : No runtime CV_* flag; this module is read-only / import-safe.
                 Nothing in the live prediction path imports this until the
                 caller (coverage_class consumers in L3/L4) flips its own flag.

Design refs:
  ARCHITECTURE.md §4 L0 — three non-nested coverage tiers
  design/RED_C_data_scope_migration.md §1 ATTACK 1 — the taxonomy mistake
  .planning/brain/ARCHITECTURE.md §4 L0 coverage-sets note

The three sets are NEVER hardcoded.  They are materialised at first call from
the real artifacts under data/cache/team_system/ and then frozen via
functools.lru_cache so subsequent lookups are O(1) dict operations.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import FrozenSet

# ---------------------------------------------------------------------------
# Canonical paths — relative to the project root so this module works from
# any working directory (the repo root is inferred from this file's location).
# ---------------------------------------------------------------------------

_REPO_ROOT: Path = Path(__file__).resolve().parents[2]  # src/brain -> src -> repo
_TEAM_RATES_PATH: Path = _REPO_ROOT / "data" / "cache" / "team_system" / "team_rates.json"
_PBP_ATTR_PATH: Path = _REPO_ROOT / "data" / "cache" / "team_system" / "pbp_attributes.parquet"

# ---------------------------------------------------------------------------
# All-30-team canonical list (NBA, 2025-26).
# This is the ONLY place a hardcoded list lives; it is used only when the
# parquet/json sources are unavailable (graceful empty-set fallback) and as
# the "league_teams" canonical source of truth.
# ---------------------------------------------------------------------------
_CANONICAL_30: FrozenSet[str] = frozenset([
    "ATL", "BKN", "BOS", "CHA", "CHI", "CLE", "DAL", "DEN",
    "DET", "GSW", "HOU", "IND", "LAC", "LAL", "MEM", "MIA",
    "MIL", "MIN", "NOP", "NYK", "OKC", "ORL", "PHI", "PHX",
    "POR", "SAC", "SAS", "TOR", "UTA", "WAS",
])


# ---------------------------------------------------------------------------
# Public coverage-set accessors (lru_cache = materialised once per process)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def mc_teams() -> FrozenSet[str]:
    """Return the set of teams covered by the Monte-Carlo TeamModel.

    Derived from the keys of data/cache/team_system/team_rates.json.
    Falls back to an empty frozenset if the file is absent or unreadable
    (so callers degrade gracefully to league_min instead of raising).

    ARCHITECTURE §4 L0: "mc_teams(5: NYK CLE DAL SAS BOS) … derived from
    parquets, not hardcoded."  The actual count may exceed 5 as more teams
    accumulate PBP data; the membership check is always against the live file.

    # TODO(P0.1): add a build-check assertion that the two Finals teams are
    #             always members of this set before a serve table is claimed valid.
    """
    try:
        with open(_TEAM_RATES_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return frozenset(data.keys())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return frozenset()


@lru_cache(maxsize=1)
def shotzone_teams() -> FrozenSet[str]:
    """Return the set of teams covered by the shot-zone / pbp_attributes model.

    Derived from the distinct values of the 'team' column in
    data/cache/team_system/pbp_attributes.parquet.
    Falls back to an empty frozenset on any read error.

    Discovery 02 G4 shows 13 teams (ATL CLE GSW LAL MIN NOP NYK OKC ORL
    PHI POR SAS WAS) — a different, non-nested set from mc_teams.
    The membership check is always derived at runtime, never hardcoded.

    # TODO(P0.2): extend to handle a 'team_abbrev' alias column if the
    #             parquet schema changes post-V2 richer-PBP substrate.
    """
    try:
        import pandas as pd  # lazy — avoids heavy import at module load

        df = pd.read_parquet(_PBP_ATTR_PATH, columns=["team"])
        return frozenset(df["team"].dropna().unique().tolist())
    except (FileNotFoundError, ImportError, KeyError, OSError, Exception):
        return frozenset()


@lru_cache(maxsize=1)
def league_teams() -> FrozenSet[str]:
    """Return all 30 NBA teams.

    Strategy: union of mc_teams() ∪ shotzone_teams() ∪ _CANONICAL_30.
    The canonical fallback is the only hardcoded list in this module and
    exists only to guarantee this function always returns a non-empty set
    even when both parquet sources are unavailable.

    # TODO(P0.3): replace _CANONICAL_30 with a live season roster fetch
    #             (e.g. from nba_api.stats.endpoints.teams) once the data
    #             freshness layer (D07) is wired.
    """
    return _CANONICAL_30 | mc_teams() | shotzone_teams()


# ---------------------------------------------------------------------------
# coverage_class — the primary public interface for the control brain / regime
# router.  Maps a (home, away) matchup onto one of three string tokens.
# ---------------------------------------------------------------------------

_MC_FULL: str = "mc_full"
_SHOTZONE: str = "shotzone"
_LEAGUE_MIN: str = "league_min"

COVERAGE_CLASSES: tuple[str, ...] = (_MC_FULL, _SHOTZONE, _LEAGUE_MIN)
"""All valid return values of coverage_class(), for downstream isinstance checks."""


def coverage_class(home: str, away: str) -> str:
    """Classify a matchup by data-fidelity tier.

    Returns one of:
        "mc_full"    — both teams have Monte-Carlo TeamModel coverage.
        "shotzone"   — both teams have shot-zone/pbp_attributes coverage
                       (but at least one lacks MC coverage).
        "league_min" — fallback; at least one team is absent from both
                       higher-fidelity sets (or either set is empty due to
                       a read error — graceful degradation).

    The classification uses strict "both in set" membership so that a
    matchup is never promoted to a tier it cannot fully serve.

    Precedence: mc_full > shotzone > league_min
    This matches ARCHITECTURE §4 L0 and RED_C §1 recommended fix.

    Args:
        home: Three-letter NBA team abbreviation, e.g. "NYK".
        away: Three-letter NBA team abbreviation, e.g. "SAS".

    Returns:
        str — one of the three COVERAGE_CLASSES tokens.

    # TODO(P0.4): emit a structured warning (not a log.error) when either
    #             team is absent from league_teams() — signals a data-staleness
    #             issue or a bad abbreviation upstream.
    """
    mc = mc_teams()
    if mc and home in mc and away in mc:
        return _MC_FULL

    sz = shotzone_teams()
    if sz and home in sz and away in sz:
        return _SHOTZONE

    return _LEAGUE_MIN


# ---------------------------------------------------------------------------
# Convenience: invalidate the caches (used by tests that swap out the parquet
# paths via monkeypatching or need a fresh read after fixture setup).
# ---------------------------------------------------------------------------


def _reset_caches() -> None:
    """Clear all lru_caches so the next call re-reads from disk.

    NOT part of the public API — prefixed with underscore.
    Called only by the test suite (tests/brain/test_coverage.py) when it
    swaps parquet fixtures.
    """
    mc_teams.cache_clear()
    shotzone_teams.cache_clear()
    league_teams.cache_clear()
