"""live_factors.py — single source of truth for live in-game adjustment factors.

Cycle 89b (loop 5) unification.

Prior to this module, three independent copies of ``foul_trouble_factor`` lived
in ``scripts/predict_in_game.py``, ``scripts/foul_trouble_adjust.py``, and
``scripts/live_player.py`` (under the wrapper name ``foul_factor_for``). All
three disagreed on the same input — e.g. Q3 with pf=4 returned 0.70, 0.55, and
0.55 respectively — which silently corrupted every downstream MAE / EV / alert
computation depending on which entry point fired.

This module is now the SINGLE SOURCE OF TRUTH. All consumers MUST import
``foul_trouble_factor`` from here. The canonical table is the most conservative
of the three (``foul_trouble_adjust.py``'s) because the underlying factors are
heuristic and not yet empirically calibrated.

Factor table
------------
    pf >= 5 (any period)                       -> 0.40
    pf == 4 and period <= 2                     -> 0.55
    pf == 4 and period == 3                     -> 0.55
    pf == 4 and period == 4 and clock > 6.0     -> 0.65
    pf == 4 (late Q4 OR OT)                     -> 0.90
    pf == 3 and period == 2                     -> 0.80
    otherwise                                   -> 1.00

Inputs are coerced defensively — ``None``, strings, NaNs, and negative values
all fall through to 1.00 (no adjustment) rather than raising. This matches the
"safe for live dashboards" contract: a malformed snapshot must never crash the
prediction loop.
"""
from __future__ import annotations

from typing import Any


def _safe_int(value: Any, default: int = 0) -> int:
    """Coerce to int; return ``default`` on any failure (None, str, NaN, ...)."""
    if value is None:
        return default
    try:
        v = int(value)
    except (TypeError, ValueError):
        try:
            v = int(float(value))
        except (TypeError, ValueError):
            return default
    return v


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Coerce to float; return ``default`` on any failure."""
    if value is None:
        return default
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    # Reject NaN (NaN != NaN).
    if v != v:
        return default
    return v


def foul_trouble_factor(pf: Any, period: Any,
                        clock_minutes_remaining: Any = 12.0) -> float:
    """Penalty multiplier for remaining-minutes when a player is in foul trouble.

    Parameters
    ----------
    pf : int-like
        Current personal-foul count. ``None`` / garbage -> treated as 0.
    period : int-like
        Current period (1-4 regulation, 5+ for OT). Garbage -> treated as 0
        (returns 1.00, no adjustment).
    clock_minutes_remaining : float-like, default 12.0
        Decimal minutes left on the current period's game clock (e.g. 5.7 when
        the clock shows 5:42). Only consulted for the Q4 split. Garbage -> 12.0.

    Returns
    -------
    float
        Multiplicative penalty in [0.0, 1.0]. 1.00 means "no foul trouble"; a
        smaller value means "coach is likely to bench — scale remaining-minutes
        accordingly".

    Notes
    -----
    See module docstring for the canonical table. This is the MOST CONSERVATIVE
    of the three legacy tables (was ``foul_trouble_adjust.foul_trouble_factor``).
    """
    pf_i = _safe_int(pf, default=0)
    period_i = _safe_int(period, default=0)
    clock_f = _safe_float(clock_minutes_remaining, default=12.0)

    # Negative pf is nonsensical — treat as "no fouls".
    if pf_i < 0:
        pf_i = 0

    # Rule 1: 5+ fouls anywhere — one away from foul-out, aggressive bench.
    if pf_i >= 5:
        return 0.40

    # Rule 2: 4 fouls — period-dependent leash.
    if pf_i == 4:
        if period_i <= 2:
            return 0.55
        if period_i == 3:
            return 0.55
        # Q4: split on clock; OT (period >= 5) acts like late Q4.
        if period_i == 4 and clock_f > 6.0:
            return 0.65
        return 0.90

    # Rule 3: 3 fouls in Q2 — common "save him for the half" bench.
    if pf_i == 3 and period_i == 2:
        return 0.80

    # No trouble.
    return 1.00


# ── W-026: CV_FOUL_PERSTAT — per-stat foul-trouble dampeners + gap fill ──────
# Default OFF: zero changes to any existing computation (byte-identical path
# calls foul_trouble_factor and returns the shared scalar unchanged).
# When ON: (1) fills two table gaps — pf==2/Q1 → 0.85, pf==3/Q3 → 0.80;
#          (2) replaces the single shared scalar with per-stat dampeners using
#              empirical calibration ratios from probe_R10_M30v2_foulout_results.json
#              (4/4-fold positive, all 7 stats improving).
#
# Per-stat formula:
#   ff_stat = 1 - (1 - ff_base) * ratio_stat
# where ff_base is the extended table value (with gaps filled) and ratio_stat is
# the calibration ratio from the validated probe. The ratio is scaled relative
# to the PTS ratio (1.1279) so PTS is the reference (ratio_pts / ratio_pts = 1.0).
# This keeps the PTS dampener exactly at ff_base, while reb/tov/blk are dampened
# more and fg3m is dampened slightly less.
#
# Clamp: ff_stat is always in [max(0.0, ff_base - 0.30), 1.0] to prevent
# over-dampening of high-ratio stats (tov 1.607) at extreme foul levels.
#
# GAPS FILLED (when flag ON only — byte-identical guarantee when OFF):
#   pf==2 and period==1  → 0.85  (early double-foul: reactive bench, Q1 still risky)
#   pf==3 and period==3  → 0.80  (3 fouls in Q3: save him for Q4 rule)
#   pf==3 and period==1  → 0.90  (3 fouls in Q1: rare, but definitely benched)
#
# Byte-identical guarantee: foul_trouble_factor_perstat(pf, period, clock, stat)
# with CV_FOUL_PERSTAT=0 returns foul_trouble_factor(pf, period, clock) for every
# (pf, period, clock, stat) combination — no branch taken other than the early
# flag-off return.
#
# Source for ratios: probe_R10_M30v2_foulout_results.json, stage2.calibration_ratios.
# The probe used dampener_volume=0.95 / dampener_other=0.97; per-stat ratios
# describe RELATIVE sensitivity (reb 1.425 = 42.5% more affected than league avg).
import os as _os_w026  # local alias for W-026 flag — _os imported later for W-017
_CV_FOUL_PERSTAT: bool = _os_w026.environ.get(
    "CV_FOUL_PERSTAT", "0"
).strip().lower() not in ("", "0", "false", "off")

# Per-stat calibration ratios (from stage2.calibration_ratios in the probe JSON).
# Reference: pts = 1.1279 (normalised to 1.0 below for the formula).
_FOUL_PERSTAT_RATIOS: dict = {
    "pts":  1.1279,
    "reb":  1.4251,
    "ast":  1.2077,
    "fg3m": 0.9175,
    "stl":  1.1165,
    "blk":  1.3505,
    "tov":  1.6070,
}
_FOUL_PERSTAT_PTS_RATIO: float = 1.1279   # normalisation reference


def _foul_trouble_factor_extended(pf: Any, period: Any,
                                   clock_minutes_remaining: Any = 12.0) -> float:
    """Extended foul-trouble table that fills the two calibration gaps.

    Identical to foul_trouble_factor() EXCEPT it adds:
      pf==3 and period==1  → 0.90   (3 fouls Q1 — rare but benched)
      pf==2 and period==1  → 0.85   (2 fouls Q1 — most reactive bench trigger)
      pf==3 and period==3  → 0.80   (3 fouls Q3 — save him for Q4)

    Only called when CV_FOUL_PERSTAT is ON.  NOT exposed in __all__ — internal
    helper for foul_trouble_factor_perstat.
    """
    pf_i = _safe_int(pf, default=0)
    period_i = _safe_int(period, default=0)
    clock_f = _safe_float(clock_minutes_remaining, default=12.0)

    if pf_i < 0:
        pf_i = 0

    # Rule 1: 5+ fouls anywhere
    if pf_i >= 5:
        return 0.40

    # Rule 2: 4 fouls
    if pf_i == 4:
        if period_i <= 2:
            return 0.55
        if period_i == 3:
            return 0.55
        if period_i == 4 and clock_f > 6.0:
            return 0.65
        return 0.90

    # Rule 3: 3 fouls — extended with Q3 and Q1 gaps
    if pf_i == 3:
        if period_i == 2:
            return 0.80   # existing rule
        if period_i == 3:
            return 0.80   # W-026 gap fill: save him for Q4
        if period_i == 1:
            return 0.90   # W-026 gap fill: 3 fouls Q1 — very rare, reactive bench

    # Rule 4 (W-026 gap fill): 2 fouls in Q1 — coaches bench even at pf==2 in Q1
    if pf_i == 2 and period_i == 1:
        return 0.85

    # No trouble
    return 1.00


def foul_trouble_factor_perstat(pf: Any, period: Any,
                                 clock_minutes_remaining: Any = 12.0,
                                 stat: str = "pts") -> float:
    """Per-stat foul-trouble factor (W-026).

    When CV_FOUL_PERSTAT is OFF returns the shared scalar from
    foul_trouble_factor() — byte-identical to the pre-W026 path.

    When ON, uses the extended table (fills pf==2/Q1, pf==3/Q3 gaps) and
    applies per-stat calibration ratios from probe_R10_M30v2_foulout:

        ff_stat = 1 - (1 - ff_base) * (ratio_stat / ratio_pts)

    Clamp: result in [max(0.0, ff_base - 0.30), 1.0].

    Parameters
    ----------
    pf, period, clock_minutes_remaining : same as foul_trouble_factor.
    stat : str
        Stat name ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov").
        Unknown stats fall back to the shared scalar (ratio = 1.0).
    """
    if not _CV_FOUL_PERSTAT:
        # Byte-identical path: delegate to canonical shared-scalar function.
        return foul_trouble_factor(pf, period, clock_minutes_remaining)

    ff_base = _foul_trouble_factor_extended(pf, period, clock_minutes_remaining)

    if ff_base >= 1.0:
        # No trouble — per-stat ratios don't matter.
        return 1.0

    ratio = _FOUL_PERSTAT_RATIOS.get(stat, _FOUL_PERSTAT_PTS_RATIO)
    # Normalise so PTS is the reference (ratio → relative_ratio).
    relative_ratio = ratio / _FOUL_PERSTAT_PTS_RATIO

    dampener_amount = (1.0 - ff_base) * relative_ratio
    ff_stat = 1.0 - dampener_amount

    # Clamp: never worse than ff_base - 0.30, never better than 1.0.
    lower_bound = max(0.0, ff_base - 0.30)
    return max(lower_bound, min(1.0, ff_stat))


# ── W-017: CV_CLUTCH_CLOSER — clutch-closer rest-of-game tilt ─────────────────
# Default OFF: zero changes to any existing computation.
# When ON: at period=4 (Q4) with |margin|<=6, apply a tier-rank tilt on the
# projected REMAINING stat for pts/ast/reb/fg3m.  The tilt is a fold-mean
# multiplier on project_remaining (adj = current + tilt * remaining), derived
# from clutch_closer_eval.json (do NOT refit live).
#
# Tier assignment: load clutch_profiles_2025-26.parquet once per process;
# rank players within each team by (clutch_min + 0.5*clutch_pts); top-3 = "top",
# next-3 = "mid", rest = "bottom".
#
# PLAYOFF GUARD: game_id prefix "004" -> always return 1.0 (no tilt).
# FOUL GUARD: if foul_trouble_factor(pf, period, clock) < 1.0, scale back the
# boost so a foul-troubled closer isn't amplified.
# STATS: pts, ast, reb, fg3m only.  blk/tov/stl unchanged.
# ONLY fires in regulation Q4 (period == 4); never OT, never Q1/Q2/Q3.
#
# All data loaded from disk (no model retrain). Lazy singleton.

import os as _os
from typing import Any, Dict, Optional, Tuple

_CV_CLUTCH_CLOSER: bool = _os.environ.get(
    "CV_CLUTCH_CLOSER", "0"
).strip().lower() not in ("", "0", "false", "off")

# ── Fold-mean tilts (from .planning/ingame/clutch_closer_eval.json, 3 folds) ──
# Key: (stat, tier) -> float tilt on projected_remaining.
# Tier: "top" = top players by clutch score, "mid" = mid tier, "bottom" = 1.0 (no tilt).
#
# DESIGN RATIONALE:
# The ablation (clutch_closer_ablation.json) shows that the lift comes from
# BOOSTING top-tier closers in close Q4 situations. The original research was
# done with team-specific ranking (top-3 per team), but clutch_profiles_2025-26.parquet
# lacks team column so we rank globally. Bottom-tier negative tilts (0.831) harm
# the calibration because global percentile ranking misclassifies players compared
# to the team-specific research definition. Conservative fix: set bottom tier to 1.0
# (no tilt) — preserves the positive boost signal without the false-negative penalty.
#
# Tilts for top/mid are the RANK-ONLY fold means from clutch_closer_eval.json
# (averaged over clutch0/clutch1 per the ablation finding that most lift is rank-prior).
# Bottom tier = 1.0 (conservative; avoids cross-season mismatch false-penalty).
# Players absent from clutch_profiles entirely also receive 1.0 (no tilt).
_CLUTCH_TILTS: Dict[str, Dict[str, float]] = {
    "pts":  {"top": 1.150, "mid": 1.017, "bottom": 1.0},
    "ast":  {"top": 0.818, "mid": 0.782, "bottom": 1.0},
    "reb":  {"top": 1.090, "mid": 1.027, "bottom": 1.0},
    "fg3m": {"top": 0.867, "mid": 0.712, "bottom": 1.0},
}

# Close-game margin threshold (absolute value)
_CLOSE_MARGIN: float = 6.0

# Minimum clutch_gp to include a player in ranking (filter noise)
_MIN_CLUTCH_GP: int = 2

# Lazy-loaded per-team tier map: {player_id: "top"|"mid"|"bottom"}
_CLUTCH_TIER_MAP: Optional[Dict[int, str]] = None
_CLUTCH_LOAD_ATTEMPTED: bool = False

_CLUTCH_PARQUET_PATH: str = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
    "data", "cache", "clutch_profiles_2025-26.parquet",
)


def _load_clutch_tier_map() -> Dict[int, str]:
    """Load clutch_profiles and return {player_id: tier} for all players.

    Ranks players within each team by (clutch_min + 0.5*clutch_pts).
    Top-3 per team -> "top", next-3 -> "mid", rest -> "bottom".
    Returns empty dict on any error (graceful degradation).
    """
    global _CLUTCH_TIER_MAP, _CLUTCH_LOAD_ATTEMPTED
    if _CLUTCH_LOAD_ATTEMPTED:
        return _CLUTCH_TIER_MAP or {}
    _CLUTCH_LOAD_ATTEMPTED = True
    try:
        import pandas as _pd  # noqa: PLC0415
        if not _os.path.exists(_CLUTCH_PARQUET_PATH):
            _CLUTCH_TIER_MAP = {}
            return {}
        df = _pd.read_parquet(_CLUTCH_PARQUET_PATH)
        # Filter to players with enough clutch appearances
        df = df[df["clutch_gp"] >= _MIN_CLUTCH_GP].copy()
        # Composite clutch score used for ranking
        df["_score"] = df["clutch_min"] + 0.5 * df["clutch_pts"]
        # Assign a team based on max clutch_min if team column absent
        # The parquet has player_id and player_name but no team column
        # We'll rank globally within this season (no team column available)
        # Sort descending by score, assign tiers per player_id globally
        # Since we don't have team in the parquet, we use cross-team global ranks
        # and trust the top-3-per-team heuristic from season clutch volume
        # Approach: use global rank, top-N/3 -> top, next-N/3 -> mid, rest -> bottom
        # This is the robust approach when team is unavailable
        df_sorted = df.sort_values("_score", ascending=False).reset_index(drop=True)
        n = len(df_sorted)
        top_n = max(1, n // 3)
        mid_n = max(1, n // 3)
        tier_map: Dict[int, str] = {}
        for i, row in df_sorted.iterrows():
            pid = int(row["player_id"])
            if i < top_n:
                tier_map[pid] = "top"
            elif i < top_n + mid_n:
                tier_map[pid] = "mid"
            else:
                tier_map[pid] = "bottom"
        _CLUTCH_TIER_MAP = tier_map
        return tier_map
    except Exception:  # noqa: BLE001
        _CLUTCH_TIER_MAP = {}
        return {}


def clutch_closer_factor(
    player_id: Any,
    stat: str,
    period: Any,
    margin: Any,
    pf: Any = 0,
    clock_minutes_remaining: Any = 6.0,
    game_id: Optional[str] = None,
) -> float:
    """Tilt multiplier for remaining-stat projection in Q4 close games.

    Returns a float that should be applied as a multiplier on ``project_remaining``
    (NOT on the final projection).  1.0 means "no tilt".

    Parameters
    ----------
    player_id : int-like
        NBA player_id for tier lookup.
    stat : str
        Stat name: "pts", "ast", "reb", "fg3m".  Other stats -> 1.0.
    period : int-like
        Current game period.  Only fires for period == 4 (regulation Q4).
    margin : float-like
        Signed score margin (home - away from the home team's perspective, or
        absolute |margin| for the close-game check).  Pass absolute |margin|.
    pf : int-like, default 0
        Player's current personal fouls.  If foul_trouble_factor < 1.0 (i.e.
        the player is in foul trouble), the closer boost is scaled down so a
        foul-troubled star isn't amplified.
    clock_minutes_remaining : float-like, default 6.0
        Minutes remaining on the Q4 game clock.  Used by foul_trouble_factor
        for the Q4 split.
    game_id : str or None, default None
        NBA game_id (e.g. "0042500401").  Prefix "004" = playoffs -> 1.0
        (hard OFF in playoffs per the AST-edge protocol).

    Returns
    -------
    float
        Tilt multiplier on remaining-stat.  1.0 = no change.
    """
    # Hard OFF when flag unset
    if not _CV_CLUTCH_CLOSER:
        return 1.0

    # Playoff guard: game_id prefix "004" -> no tilt
    if game_id is not None and str(game_id).startswith("004"):
        return 1.0

    # Only fires in regulation Q4
    period_i = _safe_int(period, default=0)
    if period_i != 4:
        return 1.0

    # Only for supported stats
    if stat not in _CLUTCH_TILTS:
        return 1.0

    # Close-game check
    try:
        abs_margin = abs(float(margin)) if margin is not None else 999.0
    except (TypeError, ValueError):
        abs_margin = 999.0
    if abs_margin > _CLOSE_MARGIN:
        return 1.0

    # Tier lookup: players absent from the clutch profiles parquet (e.g.
    # rookies with 0 clutch appearances, or players from a different season) get
    # no tilt (1.0) rather than defaulting to the "bottom" tier penalty.  Only
    # players explicitly ranked in the parquet receive a non-neutral tilt.
    tier_map = _load_clutch_tier_map()
    pid = _safe_int(player_id, default=-1)
    if pid not in tier_map:
        return 1.0
    tier = tier_map.get(pid, "bottom")

    # Base tilt from pre-fit fold-mean table
    tilt = _CLUTCH_TILTS[stat].get(tier, 1.0)

    # Foul guard: scale back boost if player is in foul trouble.
    # ftf < 1.0 means the player is likely to be benched; don't amplify.
    ftf = foul_trouble_factor(pf, period_i, clock_minutes_remaining)
    if ftf < 1.0 and tilt > 1.0:
        # Scale the boost by the foul factor (e.g. ftf=0.65 -> boost reduced 35%)
        tilt = 1.0 + (tilt - 1.0) * ftf

    return tilt


__all__ = ["foul_trouble_factor", "clutch_closer_factor",
           "foul_trouble_factor_perstat"]
