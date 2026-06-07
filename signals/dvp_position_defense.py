"""Signal: dvp_position_defense — opponent defense allowed to the player's position (DvP).

**Basketball Hypothesis**
Teams differ systematically in how many points they surrender to guards, forwards,
and centers. A guard facing a guard-friendly defense (high pts-allowed-to-G) has a
meaningful edge above the naive ``opp_def_pts`` factor, which averages across ALL
positions.  DvP (Defense versus Position) isolates that structural matchup edge.

**Operationalization**
For a player P with canonical position group POS in {G, F, C}, facing opponent OPP
on game date D:

  dvp = (mean pts OPP allowed to POS in games before D) /
        (league mean pts allowed to POS in games before D)

Values >1 mean OPP is easier than league average for this position group;
<1 means OPP is tougher.  Returns ``None`` when the player has no mapped position,
the opponent has fewer than 3 prior position-specific games, or any required
data is absent.

**Data sources (REAL -- no DEFER on primary path)**
1. ``data/nba/gamelog_{player_id}_{season}.json`` (per-player game logs)
   Grain: one dict per game; keys ``GAME_DATE, MATCHUP, PTS, REB, AST, ...``.
   Sourced by the existing prop_pergame ``build_opponent_defense`` logic;
   gamelog filenames encode the player_id so position can be looked up.
   Leak guard: only games with ``GAME_DATE < ctx.decision_time`` are used.
2. ``data/cache/player_profile_features.parquet``
   Grain: one row per player; columns ``player_id, position``.
   Position is stable bio information (birth data, draft) and does not leak.
3. ``data/team_positional_defense_2025-26.parquet`` (OPTIONAL atlas read)
   Grain: one row per team_abbreviation; per-shot-zone defense factors.
   Read from the store as atlas ``defense_by_position`` section when available;
   used to supplement/shrink the raw ratio when the store has a higher-confidence
   Atlas value from ARM-B.

**DEFER conditions**
The gamelog directory path is resolved at import time relative to the repo root;
on a fresh clone the data/nba/ directory may be absent -> degrades to None (not
an error).  Positions outside {G, F, C, G-F, F-G, F-C, C-F} default to the
nearest canonical group.  The 2025-26 season parquets are season-level snapshots;
the in-season walk-forward DvP from gamelogs is the primary leak-safe path.
Prior season gamelogs (2022-23 onward) are included with uniform weighting.

**Atlas reads (reinforcement)**
``self.read_atlas("team", ctx.opp, "defense_by_position", ctx.decision_time)``
When ARM-B writes a ``defense_by_position`` atlas for the opponent, its value is
blended (Bayesian shrinkage) with the computed ratio.  Degrades to the raw
gamelog ratio when absent.

**Gate expectations**
DvP is a well-known sportsbook feature (books price guard vs center matchups
differently).  Expected verdict: SHIP on pts; possibly VARIANCE_ONLY if position
group widths collapse the cross-sectional variation too much.
"""
from __future__ import annotations

import datetime as _dt
import glob
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from src.loop.signal import AsOfContext, Hypothesis, Signal, SignalValue

# ---------------------------------------------------------------------------
# Repository root (script-relative; portable to RunPod Linux)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_GAMELOG_GLOB = str(_ROOT / "data" / "nba" / "gamelog_*.json")
_PROFILE_PATH = _ROOT / "data" / "cache" / "player_profile_features.parquet"

# Minimum number of prior games (from an opponent against this position group)
# before we trust the ratio; below this, return None.
_MIN_GAMES_OPP = 3

# Shrinkage prior weight: equivalent to k pseudo-games of league-mean evidence.
_SHRINKAGE_K: int = 30

# Minimum minutes played threshold (mirrors prop_pergame _MIN_PLAYED = 10).
_MIN_PLAYED: float = 10.0

# ---------------------------------------------------------------------------
# Position normalization
# ---------------------------------------------------------------------------
_POS_MAP: Dict[str, str] = {
    "Guard": "G",
    "Guard-Forward": "G",
    "Forward": "F",
    "Forward-Guard": "F",
    "Forward-Center": "F",
    "Center": "C",
    "Center-Forward": "C",
    # short-form from player_positional_defense_2025-26.parquet
    "G": "G",
    "G-F": "G",
    "F": "F",
    "F-G": "F",
    "F-C": "F",
    "C": "C",
    "C-F": "C",
}


def _canonical_pos(raw: Optional[str]) -> Optional[str]:
    """Map any NBA position string to the canonical G / F / C group."""
    if not raw:
        return None
    return _POS_MAP.get(str(raw).strip(), None)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_date(raw: str) -> Optional[str]:
    """Parse gamelog GAME_DATE ('Apr 08, 2025') to ISO 'YYYY-MM-DD' or None."""
    raw = raw.strip()
    for fmt in ("%b %d, %Y", "%Y-%m-%d"):
        try:
            return _dt.datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _opponent_from_matchup(matchup: str) -> str:
    """Last token of 'TEAM vs. OPP' or 'TEAM @ OPP', e.g. 'OKC vs. LAL' -> 'LAL'."""
    parts = str(matchup).strip().split()
    return parts[-1] if parts else ""


def _load_player_positions() -> Dict[int, str]:
    """Load ``{player_id: canonical_position}`` from the profile parquet.

    Position is stable bio information and does NOT leak.  Returns an empty
    dict if the parquet is absent (degrades gracefully).
    """
    if not _PROFILE_PATH.exists():
        return {}
    try:
        df = pd.read_parquet(_PROFILE_PATH, columns=["player_id", "position"])
        out: Dict[int, str] = {}
        for row in df.itertuples(index=False):
            pos = _canonical_pos(getattr(row, "position", None))
            if pos is not None:
                out[int(row.player_id)] = pos
        return out
    except Exception:
        return {}


def _player_id_from_path(path: str) -> Optional[int]:
    """Extract player_id int from a gamelog filename like gamelog_1628983_2024-25.json."""
    fname = os.path.basename(path)
    m = re.match(r"gamelog_(\d+)_.*\.json", fname)
    return int(m.group(1)) if m else None


def _build_dvp_index(
    before_date: str,
    player_positions: Dict[int, str],
) -> Tuple[Dict[Tuple[str, str], List[float]], List[Tuple[str, float]]]:
    """Scan all gamelogs and build per-(opp, position) and league-by-position lists.

    Args:
        before_date:       ISO date string; only games strictly before this date
                           are included (leak-safe).
        player_positions:  mapping from player_id -> canonical position group.

    Returns:
        (team_pos_allowed, league_pos_rows) where
            team_pos_allowed: {(opp_abbr, pos_group): [pts_float, ...]}
            league_pos_rows:  [(pos_group, pts_float), ...]  (league-wide reference)
    """
    team_pos: Dict[Tuple[str, str], List[float]] = {}
    league_pos: List[Tuple[str, float]] = []

    for path in glob.glob(_GAMELOG_GLOB):
        pid = _player_id_from_path(path)
        if pid is None:
            continue
        pos = player_positions.get(pid)
        if pos is None:
            continue  # skip players without a known position

        try:
            with open(path, "r", encoding="utf-8") as fh:
                games = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue

        if not isinstance(games, list):
            continue

        for g in games:
            # Leak guard: skip games on or after decision_time
            gdate = _parse_date(str(g.get("GAME_DATE", "")))
            if not gdate or gdate >= before_date:
                continue
            # Minimum minutes gate (mirrors prop_pergame logic)
            try:
                mins = float(g.get("MIN", 0) or 0)
            except (TypeError, ValueError):
                mins = 0.0
            if mins < _MIN_PLAYED:
                continue
            # Opponent abbreviation from MATCHUP
            opp = _opponent_from_matchup(str(g.get("MATCHUP", "")))
            if not opp:
                continue
            try:
                pts = float(g.get("PTS", 0) or 0)
            except (TypeError, ValueError):
                continue

            key = (opp, pos)
            team_pos.setdefault(key, []).append(pts)
            league_pos.append((pos, pts))

    return team_pos, league_pos


def _compute_dvp_ratio(
    opp: str,
    pos: str,
    team_pos: Dict[Tuple[str, str], List[float]],
    league_pos: List[Tuple[str, float]],
    store_val: Optional[float],
) -> Optional[float]:
    """Compute the DvP ratio with Bayesian shrinkage toward the league mean.

    Args:
        opp:        opponent team abbreviation.
        pos:        canonical position group (G/F/C).
        team_pos:   per-(opp, pos) lists of pts allowed (from _build_dvp_index).
        league_pos: league-wide (pos, pts) pairs.
        store_val:  atlas DvP value previously shipped (None if absent).

    Returns:
        DvP ratio (float, >1 = easier matchup for this position), or None
        when the opponent has fewer than _MIN_GAMES_OPP games.
    """
    opp_pts = team_pos.get((opp, pos), [])
    if len(opp_pts) < _MIN_GAMES_OPP:
        return None

    opp_mean = sum(opp_pts) / len(opp_pts)

    league_pts_for_pos = [p for (pg, p) in league_pos if pg == pos]
    if not league_pts_for_pos:
        return None
    league_mean = sum(league_pts_for_pos) / len(league_pts_for_pos)
    if league_mean <= 0:
        return None

    raw_ratio = opp_mean / league_mean

    # --- Bayesian shrinkage toward 1.0 (the neutral / league-average ratio) ---
    n = len(opp_pts)
    shrink = n / (n + _SHRINKAGE_K)
    shrunk = 1.0 * (1 - shrink) + raw_ratio * shrink

    # Blend with store-prior if available (reinforcement loop).
    if store_val is not None:
        # Give store_prior the equivalent of _SHRINKAGE_K games of extra weight.
        alpha = _SHRINKAGE_K / (n + _SHRINKAGE_K)
        shrunk = alpha * store_val + (1 - alpha) * shrunk

    return round(shrunk, 4)


# ---------------------------------------------------------------------------
# Signal class
# ---------------------------------------------------------------------------

class DvpPositionDefenseSignal(Signal):
    """DvP: opponent defense vs player position — point-estimate pregame signal.

    Reads per-player gamelogs to compute how many points opponent OPP has
    historically allowed to position group POS, normalized by league mean.
    A ratio >1 indicates an easier-than-average matchup for this position.

    Reads the store for any prior shipped atlas value (reinforcement).
    Returns None for players without a known position or when the opponent
    has fewer than _MIN_GAMES_OPP prior position-specific games (too noisy).
    """

    name: str = "dvp_position_defense"
    target: str = "pts"
    scope: str = "pregame"
    reads_atlas: List[str] = ["defense_by_position"]
    emits: List[str] = []  # scalar signal

    # Cache player positions across builds (position is static bio data).
    _pos_cache: Optional[Dict[int, str]] = None

    def _get_player_positions(self) -> Dict[int, str]:
        """Load player positions once (static bio data, no leak)."""
        if DvpPositionDefenseSignal._pos_cache is None:
            DvpPositionDefenseSignal._pos_cache = _load_player_positions()
        return DvpPositionDefenseSignal._pos_cache

    def build(self, ctx: AsOfContext) -> SignalValue:
        """Compute the leak-safe DvP ratio for ctx.player_id vs ctx.opp.

        Reads gamelogs filtered to ``< ctx.decision_time`` and the point-in-time
        store for any previously shipped atlas value.

        Returns:
            float ratio where >1 means the opponent allows more than league-avg pts
            to this position, or None when the signal cannot be computed.
        """
        if ctx.player_id is None or ctx.opp is None:
            return None

        # ---- 1. Resolve canonical position for the subject player ----
        pos_map = self._get_player_positions()
        pos = pos_map.get(int(ctx.player_id))
        if pos is None:
            return None  # unknown position; can't compute position-specific DvP

        before_date = ctx.as_of_iso()  # YYYY-MM-DD strict <

        # ---- 2. Read atlas prior from store (reinforcement loop) ----
        store_val: Optional[float] = None
        if self.store is not None:
            atlas = self.store.read_atlas(
                "team", ctx.opp, "defense_by_position", ctx.decision_time
            )
            if isinstance(atlas, dict):
                # Expect sub-field keyed by position group, e.g. {"G": 1.05, "F": 0.97}
                raw = atlas.get(pos)
                if raw is not None:
                    try:
                        store_val = float(raw)
                    except (TypeError, ValueError):
                        store_val = None

        # ---- 3. Build the DvP index from gamelogs (leak-safe) ----
        team_pos, league_pos = _build_dvp_index(before_date, pos_map)

        # ---- 4. Compute the shrinkage-calibrated DvP ratio ----
        ratio = _compute_dvp_ratio(ctx.opp, pos, team_pos, league_pos, store_val)
        return ratio

    def hypothesis(self) -> Hypothesis:
        """Return the basketball hypothesis this signal tests."""
        return Hypothesis(
            name=self.name,
            target=self.target,
            scope=self.scope,
            statement=(
                "Sportsbooks price guard vs center matchups differently because "
                "teams systematically allow more or fewer points to specific position "
                "groups. A guard facing a guard-friendly defense (opp_dvp_G > 1.0) "
                "should score above his position-naive baseline; a center against an "
                "elite rim-protecting team (opp_dvp_C < 1.0) should score below."
            ),
            rationale=(
                "The existing ``opp_def_pts`` feature (used in the production model) "
                "pools all positions together — it cannot distinguish a team that "
                "surrenders to guards vs one that surrenders to bigs. Position-stratified "
                "DvP isolates the structural matchup edge. Historical gamelog data "
                "(4,385 files, 2022-23 to 2025-26) provide sufficient volume for "
                "position-group (G/F/C) aggregation; position is stable bio data "
                "(no leak). The signal reads the team ``defense_by_position`` atlas "
                "section (ARM-B reinforcement) when available to blend trained values."
            ),
            source="seed",
            atlas_fields=["defense_by_position"],
            expected_verdict="SHIP",
            priority="P2",
        )
