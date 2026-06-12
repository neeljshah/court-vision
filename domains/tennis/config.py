"""domains.tennis.config — SportContext literals for the MARKET_ONLY tennis adapter.

All sport-specific constants for ``tennis_atp``.  This module imports NOTHING from
``src.*`` or ``domains.nba`` (falsifier F5 compliance — verified by test AST check).
The EventRef/MarketSnapshot/Outcome dataclasses are the proof-era local versions;
once the kernel's DOMAIN_ADAPTER_SPEC lands they will be imported from there
(reconciliation note from SECOND_DOMAIN_PROOF.md §8.2).

PRIVATE: combined with odds data these artifacts are price-bearing; never tracked
on the public repo.  Sackmann data is CC BY-NC-SA — private research use only.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Literal, Optional

# ---------------------------------------------------------------------------
# Sport identity
# ---------------------------------------------------------------------------

SPORT_ID = "tennis_atp"

# The one market-only stat target this adapter feeds.
STAT_REGISTRY: tuple[str, ...] = ("winprob",)

# ---------------------------------------------------------------------------
# Surface taxonomy (Sackmann-aligned values)
# ---------------------------------------------------------------------------


class Surface(str, Enum):
    """ATP surface codes as they appear in Sackmann match CSVs."""

    HARD = "Hard"
    CLAY = "Clay"
    GRASS = "Grass"
    CARPET = "Carpet"
    UNKNOWN = "Unknown"


SURFACES: tuple[str, ...] = tuple(s.value for s in Surface)

# ---------------------------------------------------------------------------
# Entity schema
# ---------------------------------------------------------------------------

# Tennis entities are individual players (no team).
# AsOfContext.team = None; AsOfContext.player_id = Sackmann integer player_id.
ENTITY_SCHEMA: Dict[str, object] = {
    "entity_type": "player",
    "team": None,
    "id_field": "player_id",
    "id_dtype": int,
}

# ---------------------------------------------------------------------------
# Proof-era local dataclasses (EventRef / MarketSnapshot / Outcome)
# Placement here (not in domains/tennis/adapter.py) so config is the single
# source-of-truth; adapter imports from here.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EventRef:
    """Sport-agnostic event key for a single tennis match.

    ``event_id`` format: ``{date}-{tourney_id}-{p1_id}-{p2_id}``
    (Sackmann columns, pre-resolution — winner/loser identity is NOT baked in).
    """

    sport: str                        # SPORT_ID constant
    event_id: str
    start_time_utc: dt.datetime
    entity_a: str                     # str(p1_id) from Sackmann
    entity_b: str                     # str(p2_id)
    meta: Dict[str, object] = field(default_factory=dict)  # surface, tourney_level, best_of


@dataclass(frozen=True)
class MarketSnapshot:
    """One two-sided price observation (open or close) for a tennis match."""

    event: EventRef
    kind: Literal["open", "close", "live"]
    price_a: float                    # decimal odds, side A (p1)
    price_b: float                    # decimal odds, side B (p2)
    book: str                         # "pinnacle" | "bet365" | ...
    observed_at: Optional[dt.datetime] = None


@dataclass(frozen=True)
class Outcome:
    """Settled result of a tennis match."""

    event: EventRef
    winner: Literal["a", "b"]         # "a" = p1 won, "b" = p2 won
    settled_at: dt.datetime
    meta: Dict[str, object] = field(default_factory=dict)  # score string, retirement flag

# ---------------------------------------------------------------------------
# Data paths (relative to repo root; joined by the adapter at runtime)
# ---------------------------------------------------------------------------

DATA_DIR_REL = "data/domains/tennis"
MATCHES_PARQUET = f"{DATA_DIR_REL}/matches.parquet"
PLAYERS_PARQUET = f"{DATA_DIR_REL}/players.parquet"
ODDS_PARQUET = f"{DATA_DIR_REL}/odds.parquet"

# ---------------------------------------------------------------------------
# Gate / walk-forward parameters (sport-local overrides; kernel uses defaults)
# ---------------------------------------------------------------------------

# Minimum historical Elo matches for a player to appear in the gate matrix.
ELO_MIN_MATCHES = 10

# Walk-forward train split fraction (match the kernel's default of 0.75).
WF_TRAIN_FRAC = 0.75
