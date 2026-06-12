"""domains.soccer.config — SportContext literals for the MARKET_ONLY soccer adapter.

All sport-specific constants for ``soccer_fd`` (football-data.co.uk sourced club soccer).
This module imports NOTHING from ``src.*`` or ``domains.nba`` / ``domains.tennis``
(falsifier F5 compliance — verified by test AST check).

The market target is the two-way Over/Under 2.5 goals market:
  entity_a = OVER_SIDE  ("O2.5") = P(total goals >= 3)
  entity_b = UNDER_SIDE ("U2.5") = P(total goals <= 2)

The EventRef/MarketSnapshot/Outcome dataclasses are the proof-era local versions;
once the kernel's DOMAIN_ADAPTER_SPEC lands they will be imported from there
(reconciliation note from SECOND_DOMAIN_PROOF.md §8.2).

PRIVATE: combined with odds data these artifacts are price-bearing; never tracked
on the public repo.  football-data.co.uk data is free for personal/research use only.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Dict, Literal, Optional

# ---------------------------------------------------------------------------
# Sport identity
# ---------------------------------------------------------------------------

SPORT_ID = "soccer_fd"   # football-data-sourced club soccer

# The one market-only stat target this adapter feeds.
# Semantics: P(side a of the 2-way Over/Under 2.5 goals market) = P(total goals >= 3).
# Stays "winprob" so the kernel gate routes binary Brier scoring — this is a
# config-level reinterpretation, NOT a kernel edit.
STAT_REGISTRY: tuple[str, ...] = ("winprob",)

# ---------------------------------------------------------------------------
# League taxonomy (football-data.co.uk div codes + display names)
# ---------------------------------------------------------------------------

LEAGUES: Dict[str, str] = {
    "E0": "Premier League",
    "E1": "EFL Championship",
    "D1": "Bundesliga",
    "SP1": "La Liga",
    "I1": "Serie A",
    "F1": "Ligue 1",
}

# ---------------------------------------------------------------------------
# Data source URL template
# ---------------------------------------------------------------------------

URL_TEMPLATE = "https://www.football-data.co.uk/mmz4281/{season}/{div}.csv"

# ---------------------------------------------------------------------------
# Season helpers
# ---------------------------------------------------------------------------


def season_code(start_year: int) -> str:
    """Return the two-digit-start + two-digit-end season code for *start_year*.

    Examples:
        season_code(2025) -> "2526"
        season_code(2015) -> "1516"
        season_code(1999) -> "9900"
    """
    yy_start = start_year % 100
    yy_end = (start_year + 1) % 100
    return f"{yy_start:02d}{yy_end:02d}"


def season_start_year(code: str) -> int:
    """Return the four-digit start year from a two-digit-pair season code.

    Assumes codes refer to seasons in 2000–2099 (i.e., ``code[0:2]`` is
    post-millennium).  For codes like "9900" the start year is 1999.

    Examples:
        season_start_year("2526") -> 2025
        season_start_year("1516") -> 2015
        season_start_year("9900") -> 1999
    """
    yy_start = int(code[:2])
    # Heuristic: two-digit years 00–29 map to 2000–2029; 30–99 map to 1930–1999.
    # For the practical range of football-data.co.uk data (1993–present) this is
    # unambiguous: years 93–99 are 1993–1999; 00–29 are 2000–2029.
    if yy_start >= 30:
        return 1900 + yy_start
    return 2000 + yy_start


# ---------------------------------------------------------------------------
# Entity schema
# ---------------------------------------------------------------------------

# Soccer entities are clubs (teams).
# The market is outcome-blind: entity_a = Over side, entity_b = Under side.
# Real team names + div + season live in EventRef.meta.
ENTITY_SCHEMA: Dict[str, object] = {
    "entity_type": "team",
    "team": True,
    "id_field": "team_name",
    "id_dtype": str,
}

# ---------------------------------------------------------------------------
# Market sides for the 2-way O/U 2.5 goals market
# ---------------------------------------------------------------------------

OVER_SIDE = "O2.5"   # entity_a: P(total goals >= 3) = "a wins"
UNDER_SIDE = "U2.5"  # entity_b: P(total goals <= 2) = "b wins"

# ---------------------------------------------------------------------------
# Proof-era local dataclasses (EventRef / MarketSnapshot / Outcome)
# Placement here (not in domains/soccer/adapter.py) so config is the single
# source-of-truth; adapter imports from here.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EventRef:
    """Sport-agnostic event key for a single soccer match.

    For soccer the market sides are outcome-blind:
      entity_a = OVER_SIDE ("O2.5")
      entity_b = UNDER_SIDE ("U2.5")

    The real teams + competition context live in ``meta``:
      meta keys: home_team (str), away_team (str), div (str), season (str)

    ``event_id`` format: ``{date}-{div}-{home_team}-{away_team}``
    (pre-resolution — the Over/Under identity is NOT baked in).
    """

    sport: str                        # SPORT_ID constant
    event_id: str
    start_time_utc: dt.datetime
    entity_a: str                     # OVER_SIDE ("O2.5")
    entity_b: str                     # UNDER_SIDE ("U2.5")
    meta: Dict[str, object] = field(default_factory=dict)  # home_team, away_team, div, season


@dataclass(frozen=True)
class MarketSnapshot:
    """One two-sided price observation (open or close) for a soccer O/U 2.5 market."""

    event: EventRef
    kind: Literal["open", "close", "live"]
    price_a: float                    # decimal odds, side A (Over 2.5)
    price_b: float                    # decimal odds, side B (Under 2.5)
    book: str                         # "pinnacle" | "bet365" | "market_avg" | ...
    observed_at: Optional[dt.datetime] = None


@dataclass(frozen=True)
class Outcome:
    """Settled result of a soccer O/U 2.5 market.

    ``winner``:
      "a" = Over (total goals >= 3, i.e., 3+ goals were scored)
      "b" = Under (total goals <= 2, i.e., 0–2 goals were scored)
    """

    event: EventRef
    winner: Literal["a", "b"]         # "a" = Over, "b" = Under
    settled_at: dt.datetime
    meta: Dict[str, object] = field(default_factory=dict)  # total_goals, home_goals, away_goals

# ---------------------------------------------------------------------------
# Data paths (relative to repo root; joined by the adapter at runtime)
# ---------------------------------------------------------------------------

DATA_DIR_REL = "data/domains/soccer"
MATCHES_PARQUET = f"{DATA_DIR_REL}/matches.parquet"
ODDS_PARQUET = f"{DATA_DIR_REL}/odds.parquet"
RAW_DIR_REL = f"{DATA_DIR_REL}/_raw/footballdata"

# ---------------------------------------------------------------------------
# Ratings + walk-forward constants (module-level; downstream ratings.py reads these)
# ---------------------------------------------------------------------------

ALPHA = 0.10            # EW update rate for goals-for/against per match
PRIOR_GF = 1.35         # prior goals-for rate for an unseen team
PRIOR_GA = 1.35         # prior goals-against rate for an unseen team
RATE_CLIP = (0.2, 4.0)  # clip team rates before forming Poisson lambda
OU_LINE = 2.5           # over/under goal line (the market this adapter prices)
MIN_MATCHES = 6         # min history before a team enters the gate matrix
WF_TRAIN_FRAC = 0.75    # walk-forward train split (matches kernel default)
