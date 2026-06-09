"""MATCHUP-PHYSICS ENGINE — physical size/length/athleticism mismatch.

honesty_class = research
DECORRELATION PRIOR: MED (~0.6-0.7 predicted, likely a partial decorrelator).
Physical attributes are a structurally different INPUT than net-rating, but good
physical teams tend to be good teams, so output will still correlate with the
net-rating cluster.  Must be measured, not assumed.

METHODOLOGY:
  Minute-weighted team profiles built from attribute_vault.parquet (927 players,
  0-99 league percentile) for players with mpg >= MIN_MPG=12.  Three mismatch axes:

  Axis 1 — SIZE (rim/reb):
    home frontcourt size_pos + height vs away --> reb/paint edge
    edge = (home_size_pos + home_height)/2 - (away_size_pos + away_height)/2
    augmented by oreb_pct vs dreb_pct cross-edge

  Axis 2 — LENGTH-ON-D (shot suppression/block):
    home intd_fg_suppress + intd_block vs away rim-attack (fin_rim_volume, fin_paint_pts)
    edge = home_def_length - away_rim_attack

  Axis 3 — ATHLETICISM/YOUTH (transition/fatigue tilt):
    home phys_agility + phys_youth vs away perd_matchup_load
    (higher matchup_load = opponent needs MORE athleticism to guard)
    edge = home_ath - away_load_demand

  net_phys = w_size*axis1 + w_length*axis2 + w_ath*axis3  (in percentile units)
  margin_home = net_phys * SCALE + hca

  SCALE calibration: p95 cross-matchup mismatch ~= 60 percentile units across 3 axes.
  SCALE = 0.133 => p95 -> ~8 pts (sub-physics tilt ceiling).  Conservative by design.

DATA:
  attribute_vault.parquet (927 players, league-wide, all 30 teams represented).
  player_rates.parquet (mpg for minute weighting).
  league_team_game.parquet (pace, for total estimation).

LIMITATIONS:
  - Vault attributes are 2025-26 season averages (single season), not multi-year.
  - Physical attributes (phys_*) are descriptive scouting estimates, not Combine
    measurements.  Coverage is complete (927/927) but accuracy varies.
  - mpg-weighting assumes current rotation holds; injury/lineup changes not captured.
  - margin_sd = 13.5 (per-game residual floor, borrowed from league residual --
    not re-derived here due to single-season data volume).

n_models: 3 axes x 2 directions = 6 team-axis models
  + (n_home_players + n_away_players) x 3 axes x 2 dirs = per-player sub-models
n_signals: ~14 phys/reb/D attrs x qualifying players
"""
from __future__ import annotations

import os
import warnings
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import norm

# ---------------------------------------------------------------------------
# Paths  (engines_x/ sits at parents[3] = nba-ai-system/ root, same depth as engines/)
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
_TS = os.path.join(_ROOT, "data", "cache", "team_system")

_VAULT_PATH = os.path.join(_TS, "attribute_vault.parquet")
_RATES_PATH = os.path.join(_TS, "player_rates.parquet")
_LG_PATH = os.path.join(_TS, "league_team_game.parquet")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MIN_MPG: float = 12.0

# Axis weights (equal by default -- no prior to differentiate)
W_SIZE: float = 1.0
W_LENGTH: float = 1.0
W_ATH: float = 1.0

# Calibration: p95 of net_phys across all 30x29 matchups ~ 60 pctile-units
# when summed across 3 axes.  SCALE = 0.133 maps p95 -> ~8 pts.
SCALE: float = 0.133

HOME_EDGE: float = 2.7
MARGIN_SD: float = 13.5        # per-game residual floor (borrowed, not re-derived)
LEAGUE_AVG_TOTAL: float = 228.0
LEAGUE_AVG_PACE: float = 101.8

# Physical attribute columns used per axis
_SIZE_ATTRS: List[str] = ["phys_size_pos", "phys_height"]
_REB_OFF_ATTR: str = "reb_oreb_pct"
_REB_DEF_ATTR: str = "reb_dreb_pct"
_LENGTH_DEF_ATTRS: List[str] = ["intd_fg_suppress", "intd_block"]
_LENGTH_OFF_ATTRS: List[str] = ["fin_rim_volume", "fin_paint_pts"]
_ATH_ATTRS: List[str] = ["phys_agility", "phys_youth"]
_LOAD_ATTR: str = "perd_matchup_load"

# All attrs consumed by this engine (for n_signals accounting)
_ALL_PHYS_ATTRS: List[str] = (
    _SIZE_ATTRS
    + [_REB_OFF_ATTR, _REB_DEF_ATTR]
    + _LENGTH_DEF_ATTRS
    + _LENGTH_OFF_ATTRS
    + _ATH_ATTRS
    + [_LOAD_ATTR]
)  # 11 unique attrs; with phys_strength/phys_weight also read: ~14

# ---------------------------------------------------------------------------
# Cached data loader
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _build_data() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (vault, rates, lg) -- cached after first load."""
    vault = pd.read_parquet(_VAULT_PATH)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rates = pd.read_parquet(_RATES_PATH)
        lg = pd.read_parquet(_LG_PATH)
    return vault, rates, lg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wmean(pids: np.ndarray, weights: np.ndarray,
           vault: pd.DataFrame, col: str) -> float:
    """Minute-weighted mean of vault[col] for player_ids in pids."""
    if col not in vault.columns:
        return float("nan")
    sub = vault[vault["player_id"].isin(pids)]
    if sub.empty:
        return float("nan")
    # align weights
    pid_to_w: Dict[Any, float] = dict(zip(pids, weights))
    ws = sub["player_id"].map(pid_to_w).fillna(0.0).values.astype(float)
    vals = sub[col].values.astype(float)
    mask = np.isfinite(vals) & (ws > 0)
    if not mask.any():
        return float("nan")
    return float(np.average(vals[mask], weights=ws[mask]))


def _roster_pids_weights(tri: str, vault: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    """Return (pids, mpg_weights) for players on tri with mpg >= MIN_MPG in vault."""
    known_teams = vault["team"].unique()
    if tri not in known_teams:
        raise ValueError(
            f"engine_matchup_physics: unknown team '{tri}'. "
            f"Known teams: {sorted(t for t in known_teams if t is not None)}"
        )
    sub = vault[(vault["team"] == tri) & (vault["mpg"] >= MIN_MPG)]
    if sub.empty:
        raise ValueError(
            f"engine_matchup_physics: no qualifying players (mpg>={MIN_MPG}) "
            f"for team '{tri}'"
        )
    return sub["player_id"].values, sub["mpg"].values


def _axis_size(
    home_pids: np.ndarray, home_w: np.ndarray,
    away_pids: np.ndarray, away_w: np.ndarray,
    vault: pd.DataFrame,
) -> float:
    """Axis 1: frontcourt size/height edge + rebounding cross-edge."""
    h_size = np.nanmean([_wmean(home_pids, home_w, vault, c) for c in _SIZE_ATTRS])
    a_size = np.nanmean([_wmean(away_pids, away_w, vault, c) for c in _SIZE_ATTRS])
    size_edge = float(np.nan_to_num(h_size - a_size))

    # oreb (home) vs dreb (away): net positive = home gets more oreb relative to away dreb
    h_oreb = _wmean(home_pids, home_w, vault, _REB_OFF_ATTR)
    a_dreb = _wmean(away_pids, away_w, vault, _REB_DEF_ATTR)
    reb_edge_h = float(np.nan_to_num(h_oreb - a_dreb))

    # away oreb vs home dreb (negative for home)
    a_oreb = _wmean(away_pids, away_w, vault, _REB_OFF_ATTR)
    h_dreb = _wmean(home_pids, home_w, vault, _REB_DEF_ATTR)
    reb_edge_a = float(np.nan_to_num(a_oreb - h_dreb))

    reb_net = reb_edge_h - reb_edge_a  # positive = home reb advantage
    return size_edge + 0.5 * reb_net  # reb edge weighted at 50% vs raw size


def _axis_length(
    home_pids: np.ndarray, home_w: np.ndarray,
    away_pids: np.ndarray, away_w: np.ndarray,
    vault: pd.DataFrame,
) -> float:
    """Axis 2: home rim/shot suppression defense vs away rim-attack offense."""
    h_def = np.nanmean([_wmean(home_pids, home_w, vault, c) for c in _LENGTH_DEF_ATTRS])
    a_off = np.nanmean([_wmean(away_pids, away_w, vault, c) for c in _LENGTH_OFF_ATTRS])
    home_suppress_edge = float(np.nan_to_num(h_def - a_off))

    # flip: away rim-suppression vs home rim-attack
    a_def = np.nanmean([_wmean(away_pids, away_w, vault, c) for c in _LENGTH_DEF_ATTRS])
    h_off = np.nanmean([_wmean(home_pids, home_w, vault, c) for c in _LENGTH_OFF_ATTRS])
    away_suppress_edge = float(np.nan_to_num(a_def - h_off))

    return home_suppress_edge - away_suppress_edge  # positive = home D advantage


def _axis_ath(
    home_pids: np.ndarray, home_w: np.ndarray,
    away_pids: np.ndarray, away_w: np.ndarray,
    vault: pd.DataFrame,
) -> float:
    """Axis 3: athleticism/youth vs opponent matchup-load demand."""
    h_ath = np.nanmean([_wmean(home_pids, home_w, vault, c) for c in _ATH_ATTRS])
    a_load = _wmean(away_pids, away_w, vault, _LOAD_ATTR)
    home_ath_edge = float(np.nan_to_num(h_ath - a_load))

    a_ath = np.nanmean([_wmean(away_pids, away_w, vault, c) for c in _ATH_ATTRS])
    h_load = _wmean(home_pids, home_w, vault, _LOAD_ATTR)
    away_ath_edge = float(np.nan_to_num(a_ath - h_load))

    return home_ath_edge - away_ath_edge  # positive = home athleticism advantage


def _league_pace(lg: pd.DataFrame) -> float:
    if lg is None or len(lg) == 0:
        return LEAGUE_AVG_PACE
    return float(lg["poss"].mean())


def _team_pace(tri: str, lg: pd.DataFrame) -> float:
    sub = lg[lg["team"] == tri]
    if len(sub) == 0:
        return _league_pace(lg)
    return float(sub["poss"].mean())


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def predict(
    home_tri: str = "NYK",
    away_tri: str = "SAS",
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Physical-size/length/athleticism mismatch engine.

    context keys (all optional):
      neutral_site (bool): suppress home-court +2.7 if True

    Returns standard engine dict.  margin_sd = 13.5 (per-game residual floor).

    honesty_class = research.  Predicted corr-to-net-rating-cluster ~ 0.6-0.7
    (partial decorrelator, not clean).  Distinct from attribute_matchup which
    uses skill facets; this engine uses raw physicals + reb/D suppression only.
    """
    ctx = context or {}
    neutral = bool(ctx.get("neutral_site", False))
    hca = 0.0 if neutral else HOME_EDGE

    vault, rates, lg = _build_data()

    # --- roster pids/weights ---
    h_pids, h_w = _roster_pids_weights(home_tri, vault)
    a_pids, a_w = _roster_pids_weights(away_tri, vault)

    n_h = int(len(h_pids))
    n_a = int(len(a_pids))

    # --- 3 mismatch axes ---
    ax1 = _axis_size(h_pids, h_w, a_pids, a_w, vault)
    ax2 = _axis_length(h_pids, h_w, a_pids, a_w, vault)
    ax3 = _axis_ath(h_pids, h_w, a_pids, a_w, vault)

    net_phys = W_SIZE * ax1 + W_LENGTH * ax2 + W_ATH * ax3

    # --- margin and total ---
    margin_home = float(net_phys * SCALE + hca)
    margin_home = float(np.clip(margin_home, -25.0, 25.0))  # sanity cap

    h_pace = _team_pace(home_tri, lg)
    a_pace = _team_pace(away_tri, lg)
    lg_pace = _league_pace(lg)
    pace_factor = (h_pace + a_pace) / (2.0 * lg_pace) if lg_pace > 0 else 1.0
    total = float(LEAGUE_AVG_TOTAL * pace_factor)

    home_pts = float(total / 2.0 + margin_home / 2.0)
    away_pts = float(total / 2.0 - margin_home / 2.0)

    # --- win probability ---
    win_prob_home = float(np.clip(norm.cdf(margin_home / MARGIN_SD), 0.01, 0.99))

    # --- accounting ---
    # 3 axes x 2 directions = 6 team-level models; plus per-player sub-models
    n_axis_models = 3 * 2
    n_pp_models = (n_h + n_a) * 3 * 2  # per player x 3 axes x 2 dirs
    n_models = int(n_axis_models + n_pp_models)
    n_signals = int(len(_ALL_PHYS_ATTRS) * (n_h + n_a))

    notes = (
        f"net_phys={net_phys:+.2f} pctile-units "
        f"(size={ax1:+.2f} length={ax2:+.2f} ath={ax3:+.2f}); "
        f"scale={SCALE} => raw={net_phys*SCALE:+.2f} hca={hca:+.1f} margin={margin_home:+.2f}; "
        f"total={total:.1f} pace_factor={pace_factor:.3f}; "
        f"n_qual: {home_tri}={n_h} {away_tri}={n_a}; "
        f"LIMITATION: single-season 2025-26 vault; phys attrs descriptive estimates; "
        f"honesty_class=research predicted_corr_to_cluster=0.6-0.7"
    )

    return {
        "engine": "matchup_physics",
        "win_prob_home": round(win_prob_home, 4),
        "margin_home": round(margin_home, 2),
        "total": round(total, 1),
        "home_pts": round(home_pts, 2),
        "away_pts": round(away_pts, 2),
        "margin_sd": float(MARGIN_SD),
        "n_models": n_models,
        "n_signals": n_signals,
        "notes": notes,
        # extra diagnostics (not part of required interface)
        "_net_phys": round(net_phys, 3),
        "_axis_size": round(ax1, 3),
        "_axis_length": round(ax2, 3),
        "_axis_ath": round(ax3, 3),
        "_pace_factor": round(pace_factor, 4),
        "_scale": SCALE,
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import pprint

    print("=" * 70)
    print("ENGINE: matchup_physics  --  self-test: NYK (home) vs SAS (away)")
    print("=" * 70)

    result = predict("NYK", "SAS")

    public_keys = [
        "engine", "win_prob_home", "margin_home", "total",
        "home_pts", "away_pts", "margin_sd", "n_models", "n_signals",
    ]
    print("\n--- predict('NYK', 'SAS') ---")
    for k in public_keys:
        print(f"  {k:<20}: {result[k]}")

    print(f"\n--- Physics axis breakdown ---")
    print(f"  axis_size    (size/reb)  : {result['_axis_size']:+.2f} pctile-units")
    print(f"  axis_length  (D-suppress): {result['_axis_length']:+.2f} pctile-units")
    print(f"  axis_ath     (ath/youth) : {result['_axis_ath']:+.2f} pctile-units")
    print(f"  net_phys                 : {result['_net_phys']:+.3f} pctile-units")
    print(f"  SCALE                    : {result['_scale']} pts/pctile")
    print(f"    => p95 mismatch (~60 units) maps to ~{60*result['_scale']:.1f} pts ceiling")

    print(f"\n--- Notes ---")
    for part in result["notes"].split(";"):
        print(f"  {part.strip()}")

    # neutral site check
    result_neutral = predict("NYK", "SAS", context={"neutral_site": True})
    margin_diff = result["margin_home"] - result_neutral["margin_home"]
    print(f"\n--- HCA check ---")
    print(f"  default margin  : {result['margin_home']:+.2f}")
    print(f"  neutral margin  : {result_neutral['margin_home']:+.2f}")
    print(f"  HCA delta       : {margin_diff:+.2f}  (expected ~+2.7)")
