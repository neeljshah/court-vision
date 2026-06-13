"""domains.mlb.config — SportContext literals for the MARKET_ONLY MLB moneyline adapter.

All sport-specific constants for ``mlb_sbro`` (sportsbookreviewsonline.com sourced MLB
moneyline data, archive 2010–2021).
This module imports NOTHING from ``src.*`` or any other domain adapter
(falsifier F5 compliance — verified by test AST check).

The market target is the two-way moneyline market:
  entity_a = HOME_SIDE ("HOME") = P(home team wins)
  entity_b = AWAY_SIDE ("AWAY") = P(away team wins)

The EventRef/MarketSnapshot/Outcome dataclasses are the proof-era local versions;
once the kernel's DOMAIN_ADAPTER_SPEC lands they will be imported from there
(reconciliation note from SECOND_DOMAIN_PROOF.md §8.2).

PRIVATE: combined with odds data these artifacts are price-bearing; never tracked
on the public repo.  sportsbookreviewsonline.com data is for personal/research use only.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Dict, Literal, Optional, Tuple

# ---------------------------------------------------------------------------
# Sport identity
# ---------------------------------------------------------------------------

SPORT_ID = "mlb_sbro"   # sportsbookreviewsonline-sourced MLB moneyline

# The one market-only stat target this adapter feeds.
# Semantics: winprob = P(home team wins) = P(side a of the 2-way moneyline market).
# Stays "winprob" so the kernel gate routes binary Brier scoring — this is a
# config-level reinterpretation (config-level semantics, NOT a kernel edit).
STAT_REGISTRY: tuple[str, ...] = ("winprob",)

# ---------------------------------------------------------------------------
# Archive years (frozen at 2021 — source corpus)
# ---------------------------------------------------------------------------

YEARS: tuple = tuple(range(2010, 2022))  # 2010..2021 inclusive (archive frozen at 2021)

# ---------------------------------------------------------------------------
# Data source URL template
# ---------------------------------------------------------------------------

URL_TEMPLATE = (
    "https://www.sportsbookreviewsonline.com/wp-content/uploads/"
    "sportsbookreviewsonline_com_737/mlb-odds-{year}.xlsx"
)

# The server 404-redirects non-browser UAs; this header is REQUIRED.
FETCH_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36 "
    "(private research archive fetch; contact in repo)"
)

# ---------------------------------------------------------------------------
# Entity schema
# ---------------------------------------------------------------------------

# MLB entities are franchises (teams).
# id_field uses SBR 3-letter team codes (e.g. "NYY", "BOS").
ENTITY_SCHEMA: Dict[str, object] = {
    "entity_type": "team",
    "team": True,
    "id_field": "team_code",
    "id_dtype": str,  # SBR 3-letter codes
}

# ---------------------------------------------------------------------------
# Market sides for the 2-way moneyline market
# ---------------------------------------------------------------------------

HOME_SIDE = "HOME"   # entity_a: P(home team wins) = "a wins"
AWAY_SIDE = "AWAY"   # entity_b: P(away team wins) = "b wins"

# ---------------------------------------------------------------------------
# League map + resolver (AL/NL corpus split)
# Static SBR codes — PROVISIONAL until the real-data audit.
# resolve_league RAISES on unknown codes so the audit catches drift loudly.
# ---------------------------------------------------------------------------

LEAGUE_MAP: Dict[str, str] = {
    # NL
    "ARI": "NL", "ATL": "NL", "CUB": "NL", "CHC": "NL", "CIN": "NL",
    "COL": "NL", "LAD": "NL", "MIA": "NL", "FLA": "NL", "MIL": "NL",
    "NYM": "NL", "PHI": "NL", "PIT": "NL", "SDG": "NL", "SFO": "NL",
    "SF":  "NL", "STL": "NL", "WAS": "NL",
    "LOS": "NL",  # LA Dodgers legacy code (pre-LAD / 2020 variant)
    "SFG": "NL",  # San Francisco Giants 2020-season variant of SFO
    # AL
    "BAL": "AL", "BOS": "AL", "CWS": "AL", "CHW": "AL", "CLE": "AL",
    "DET": "AL", "KAN": "AL", "LAA": "AL", "ANA": "AL", "MIN": "AL",
    "NYY": "AL", "OAK": "AL", "SEA": "AL", "TAM": "AL", "TEX": "AL",
    "TOR": "AL",
    "BRS": "AL",  # Boston Red Sox 2020-season variant of BOS
    # HOU handled by override (moved NL->AL in 2013)
}

# (team, season) -> league overrides:
# HOU was NL through 2012, AL from 2013 onward.
LEAGUE_OVERRIDES: Dict[Tuple[str, int], str] = {}
for _year in YEARS:
    LEAGUE_OVERRIDES[("HOU", _year)] = "NL" if _year <= 2012 else "AL"


def resolve_league(team: str, season: int) -> str:
    """Return 'AL' or 'NL' for an SBR team code in a given season.

    Raises KeyError on unknown code so the real-data audit catches drift loudly.
    """
    if (team, season) in LEAGUE_OVERRIDES:
        return LEAGUE_OVERRIDES[(team, season)]
    if team in LEAGUE_MAP:
        return LEAGUE_MAP[team]
    raise KeyError(
        f"unknown SBR team code {team!r} (season {season}) "
        "— add to LEAGUE_MAP before proceeding"
    )


# ---------------------------------------------------------------------------
# American -> decimal odds helper (pure, stdlib-only)
# Shared by ingest + adapter.
# ---------------------------------------------------------------------------


def am_to_decimal(american) -> float:
    """American moneyline -> decimal odds.

    |a|>=100 required; else / non-numeric / 'NL' -> nan (never raises).

    Examples:
        +130 -> 2.30
        -150 -> 1.6667
        +100 -> 2.0
        -100 -> 2.0
    """
    try:
        a = float(american)
    except (TypeError, ValueError):
        return float("nan")
    if abs(a) < 100:
        return float("nan")
    return 1.0 + (a / 100.0 if a > 0 else 100.0 / abs(a))


# ---------------------------------------------------------------------------
# Proof-era local dataclasses (EventRef / MarketSnapshot / Outcome)
# Placement here (not in domains/mlb/adapter.py) so config is the single
# source-of-truth; adapter imports from here.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EventRef:
    """Sport-agnostic event key for a single MLB game.

    For MLB the market sides map to game outcome:
      entity_a = HOME_SIDE ("HOME") = home team
      entity_b = AWAY_SIDE ("AWAY") = away team

    The real teams + competition context live in ``meta``:
      meta keys: home_team (str), away_team (str), season (int),
                 game_seq (int), home_league (str)

    ``event_id`` format: ``{date}-{home_team}-{away_team}-{game_seq}``
    """

    sport: str                         # SPORT_ID constant
    event_id: str
    start_time_utc: dt.datetime
    entity_a: str                      # HOME_SIDE ("HOME")
    entity_b: str                      # AWAY_SIDE ("AWAY")
    meta: Dict[str, object] = field(default_factory=dict)
    # meta keys: home_team, away_team, season, game_seq, home_league


@dataclass(frozen=True)
class MarketSnapshot:
    """One two-sided price observation (open or close) for an MLB moneyline market."""

    event: EventRef
    kind: Literal["open", "close", "live"]
    price_a: float                     # decimal odds, side A (home team)
    price_b: float                     # decimal odds, side B (away team)
    book: str                          # "pinnacle" | "market_avg" | ...
    observed_at: Optional[dt.datetime] = None


@dataclass(frozen=True)
class Outcome:
    """Settled result of an MLB moneyline market.

    ``winner``:
      "a" = home win  (home_runs > away_runs)
      "b" = away win  (away_runs > home_runs)
    """

    event: EventRef
    winner: Literal["a", "b"]          # "a" = home win, "b" = away win
    settled_at: dt.datetime
    meta: Dict[str, object] = field(default_factory=dict)
    # meta keys: home_runs, away_runs

# ---------------------------------------------------------------------------
# Data paths (relative to repo root; joined by the adapter at runtime)
# ---------------------------------------------------------------------------

DATA_DIR_REL = "data/domains/mlb"
GAMES_PARQUET = f"{DATA_DIR_REL}/games.parquet"
ODDS_PARQUET = f"{DATA_DIR_REL}/odds.parquet"
RAW_DIR_REL = f"{DATA_DIR_REL}/_raw/sbro"

# ---------------------------------------------------------------------------
# Elo + walk-forward constants (module-level; downstream ratings.py reads these)
# ---------------------------------------------------------------------------

ELO_K = 4.0            # K-factor for Elo update (baseball: lower than basketball)
ELO_MEAN = 1500.0      # prior mean Elo for an unseen franchise
ELO_HFA = 24.0         # home-field Elo advantage (in Elo points)
SEASON_REGRESS = 0.33  # fraction to regress toward mean between seasons
MIN_GAMES = 10         # min history before a team enters the gate matrix
WF_TRAIN_FRAC = 0.75   # walk-forward train split (matches kernel default)
