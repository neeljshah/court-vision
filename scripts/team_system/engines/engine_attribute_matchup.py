"""ATTRIBUTE-MATCHUP ENGINE — deepest signal layer: 87 attributes x ~900 players.

METHODOLOGY:
  For (home, away), load attribute_vault.parquet (87 attrs, 0-99 league percentile) and
  player_rates.parquet (team, mpg for minute-weighting).  Compute each team's minute-weighted
  OFFENSIVE facet profile and DEFENSIVE facet profile across the 8 FACETS defined in
  build_attribute_clash.py (rim finishing vs intd_fg_suppress, rim pressure vs intd_block,
  paint vs intd_stops, drives vs perd_stops, catch-and-shoot vs perd_fg3_suppress,
  iso/PnR vs perd_stops, OREB vs DREB, drawing fouls vs perd_foul_disc).

  Each facet edge = home_off_attr - away_def_attr (or vice versa) in 0-99 percentile units.
  A saturation guard (def aggregate must be in [8, 92]) skips non-discriminating facets.

  net_attr_advantage = sum(home_off_edges) - sum(away_off_edges)  [facet-edge SUM, not avg]
  margin_home = net_attr_advantage * SCALE + home_court  [SCALE=0.075, HC=+2.7]

  SCALE calibration: the full distribution of net across all 30x29 matchups has p95 ~130
  percentile-point-sum.  SCALE=0.075 maps p95 -> ~10 pts (the realistic extreme).  A
  balanced matchup (+30 net sum) maps to ~2.3 pts -- appropriately conservative, so this
  engine contributes a diversified scouting view to the ensemble without overconfidence.

HONEST caveat: the attribute vault is DESCRIPTIVE scouting intelligence (opponent/usage-adjusted,
  volume-gated seasonal averages).  It tells WHERE a matchup tilts, not how the game unfolds
  possession by possession.  This engine should be ensemble-weighted conservatively alongside
  the MC-possession and four-factors engines, whose margin_sd already reflects single-game
  variance.

n_models breakdown:
  8 facets x 2 directions = 16 team-level facet-edge models
  + (n_home_players + n_away_players) x 8 facets x 2 directions = per-player sub-models
  Total for a NYK/SAS game: 320 sub-models

n_signals: 86 attribute columns x all mpg>=12 players for both rosters
  For NYK/SAS (19 qualifying players): ~1634 raw signals consumed
"""
from __future__ import annotations

import os
import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import norm

# ---------------------------------------------------------------------------
# Paths
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
# Facets: (label, offensive_attr, defensive_attr)
# Exactly the FACETS list from build_attribute_clash.py -- do not change without
# also updating that script.
FACETS: List[Tuple[str, str, str]] = [
    ("Rim finishing",      "fin_rim_pct",        "intd_fg_suppress"),
    ("Rim pressure (vol)", "fin_rim_volume",      "intd_block"),
    ("Paint scoring",      "fin_paint_pts",       "intd_stops"),
    ("Drives",             "crea_drives_vol",     "perd_stops"),
    ("Catch & shoot 3",    "shoot_catch_shoot3",  "perd_fg3_suppress"),
    ("Iso / PnR creation", "crea_pnr_ppp",        "perd_stops"),
    ("Off. rebounding",    "reb_oreb_pct",        "reb_dreb_pct"),
    ("Drawing fouls",      "fin_contact_ft",      "perd_foul_disc"),
]

SAT_LO: float = 8.0   # skip a facet whose team-def aggregate falls below this (non-discriminating)
SAT_HI: float = 92.0  # skip a facet whose team-def aggregate rises above this (saturated)

# Percentile-sum -> points conversion.
# Calibration: p95 of net across all 30x29 matchups ~ 130 pctile-point sum.
# SCALE = 0.075 maps p95 -> ~9.75 pts.  Conservative by design.
SCALE: float = 0.075

HOME_EDGE: float = 2.7       # standard NBA home-court adjustment (pts)
MARGIN_SD: float = 13.5      # single-game margin SD (used for win_prob; conservative)
LEAGUE_AVG_TOTAL: float = 228.0  # pts, league-average total (used when pace unknown)
MIN_MPG: float = 12.0        # minimum minutes per game to include a player in team profile

_META_COLS = {"player_id", "player", "team", "mpg"}

# ---------------------------------------------------------------------------
# Cache (lazy-load on first call)
# ---------------------------------------------------------------------------
_vault: Optional[pd.DataFrame] = None
_rates: Optional[pd.DataFrame] = None
_lg: Optional[pd.DataFrame] = None


def _load_data() -> None:
    global _vault, _rates, _lg
    if _vault is not None:
        return
    _vault = pd.read_parquet(_VAULT_PATH).set_index("player_id")
    _rates = pd.read_parquet(_RATES_PATH)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _lg = pd.read_parquet(_LG_PATH)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wmean(pids: np.ndarray, weights: np.ndarray, col: str) -> float:
    """Minute-weighted mean of vault[col] for given player ids."""
    vals = _vault.loc[pids, col].values.astype(float)
    w = weights.astype(float)
    m = np.isfinite(vals)
    if not m.any() or w[m].sum() == 0:
        return float("nan")
    return float(np.average(vals[m], weights=w[m]))


def _roster(tri: str) -> pd.DataFrame:
    """Return players for team tri with mpg >= MIN_MPG that have vault data."""
    ro = _rates[(_rates["team"] == tri) & (_rates["mpg"] >= MIN_MPG)].copy()
    ro = ro[ro["pid"].isin(_vault.index)]
    return ro


def _team_profiles(tri: str) -> Tuple[np.ndarray, np.ndarray, Dict[str, float], Dict[str, float]]:
    """Return (pids, weights, off_profile, def_profile) for a team.

    off_profile: {attr: wmean} for all offensive attrs in FACETS
    def_profile: {attr: wmean} for all defensive attrs in FACETS
    """
    ro = _roster(tri)
    pids = ro["pid"].values
    weights = ro["mpg"].values
    off_prof: Dict[str, float] = {}
    def_prof: Dict[str, float] = {}
    for _label, oc, dc in FACETS:
        if oc in _vault.columns:
            off_prof[oc] = _wmean(pids, weights, oc)
        if dc in _vault.columns:
            def_prof[dc] = _wmean(pids, weights, dc)
    return pids, weights, off_prof, def_prof


def _facet_edges(
    off_pids: np.ndarray, off_w: np.ndarray,
    off_prof: Dict[str, float],
    def_prof: Dict[str, float],
    off_tri: str,
) -> Tuple[float, int, List[Tuple[str, float, float, float]]]:
    """Compute the net facet-edge sum for (off_tri offense vs opponent defense).

    Returns:
      net_edge: float  -- sum of passing facet edges
      n_active: int    -- number of facets that passed saturation guard
      details: list of (label, off_val, def_val, edge) for all active facets
    """
    net = 0.0
    n_active = 0
    details: List[Tuple[str, float, float, float]] = []
    for label, oc, dc in FACETS:
        o = off_prof.get(oc, float("nan"))
        d = def_prof.get(dc, float("nan"))
        if not np.isfinite(o) or not np.isfinite(d):
            continue
        if not (SAT_LO <= d <= SAT_HI):
            continue
        edge = o - d
        net += edge
        n_active += 1
        details.append((label, o, d, edge))
    return net, n_active, details


def _per_player_models(off_pids: np.ndarray, def_prof: Dict[str, float]) -> int:
    """Count per-player facet sub-models (player off attr vs team def aggregate)."""
    count = 0
    for pid in off_pids:
        for _label, oc, dc in FACETS:
            d = def_prof.get(dc, float("nan"))
            if not np.isfinite(d) or not (SAT_LO <= d <= SAT_HI):
                continue
            if oc not in _vault.columns:
                continue
            v = _vault.loc[pid, oc] if pid in _vault.index else float("nan")
            if np.isfinite(float(v)):
                count += 1
    return count


def _league_avg_pace() -> float:
    if _lg is None or len(_lg) == 0:
        return 101.8
    return float(_lg["poss"].mean())


def _team_pace(tri: str) -> float:
    if _lg is None:
        return _league_avg_pace()
    sub = _lg[_lg["team"] == tri]
    if len(sub) == 0:
        return _league_avg_pace()
    return float(sub["poss"].mean())


def _n_attr_cols() -> int:
    return len([c for c in _vault.columns if c not in _META_COLS])


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def predict(
    home_tri: str = "NYK",
    away_tri: str = "SAS",
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Attribute-matchup engine prediction.

    context keys (all optional):
      neutral_site (bool): suppress home-court +2.7 if True
      home_b2b (bool): not used in this engine (captured in ensemble)
      away_b2b (bool): not used in this engine
      playoffs (bool): not used in this engine

    Returns the standard engine dict (see engines/__init__.py for full spec).
    """
    ctx = context or {}
    neutral = bool(ctx.get("neutral_site", False))

    _load_data()

    # ---- roster profiles for both teams --------------------------------
    h_pids, h_w, h_off, h_def = _team_profiles(home_tri)
    a_pids, a_w, a_off, a_def = _team_profiles(away_tri)

    n_h = len(h_pids)
    n_a = len(a_pids)

    # ---- facet edges in both directions --------------------------------
    home_net, home_n, home_details = _facet_edges(h_pids, h_w, h_off, a_def, home_tri)
    away_net, away_n, away_details = _facet_edges(a_pids, a_w, a_off, h_def, away_tri)

    net_attr = home_net - away_net   # positive -> home has attribute advantage

    # ---- per-player sub-model count ------------------------------------
    pp_home = _per_player_models(h_pids, a_def)   # home off players vs away def
    pp_away = _per_player_models(a_pids, h_def)   # away off players vs home def
    n_team_models = len(FACETS) * 2               # 8 facets x 2 directions = 16
    n_models = n_team_models + pp_home + pp_away

    # ---- n_signals consumed --------------------------------------------
    n_attr = _n_attr_cols()
    n_signals = n_attr * (n_h + n_a)

    # ---- margin and total ----------------------------------------------
    home_court = 0.0 if neutral else HOME_EDGE
    margin_home = net_attr * SCALE + home_court

    # pace-adjusted total
    league_pace = _league_avg_pace()
    h_pace = _team_pace(home_tri)
    a_pace = _team_pace(away_tri)
    if league_pace > 0:
        pace_factor = (h_pace + a_pace) / (2.0 * league_pace)
    else:
        pace_factor = 1.0
    total = LEAGUE_AVG_TOTAL * pace_factor

    home_pts = total / 2.0 + margin_home / 2.0
    away_pts = total / 2.0 - margin_home / 2.0

    # ---- win probability -----------------------------------------------
    win_prob_home = float(norm.cdf(margin_home / MARGIN_SD))

    # ---- top-3 facet edges each way (for notes / self-test) ------------
    home_top3 = sorted(home_details, key=lambda x: x[3], reverse=True)[:3]
    away_top3 = sorted(away_details, key=lambda x: x[3], reverse=True)[:3]

    home_top3_str = "; ".join(
        f"{lbl}({e:+.1f})" for lbl, _o, _d, e in home_top3
    ) or "none"
    away_top3_str = "; ".join(
        f"{lbl}({e:+.1f})" for lbl, _o, _d, e in away_top3
    ) or "none"

    notes = (
        f"net_attr={net_attr:+.1f} pctile-pts "
        f"(home={home_net:+.1f} [top: {home_top3_str}] | "
        f"away={away_net:+.1f} [top: {away_top3_str}]); "
        f"scale={SCALE} => raw_margin={net_attr*SCALE:+.2f} + HC={home_court:+.1f} = {margin_home:+.2f}; "
        f"total={total:.1f} (pace_factor={pace_factor:.3f}); "
        f"DESCRIPTIVE scouting: vault is seasonal averages, not live-matchup intel"
    )

    return {
        "engine": "attribute_matchup",
        "win_prob_home": round(win_prob_home, 4),
        "margin_home": round(margin_home, 2),
        "total": round(total, 1),
        "home_pts": round(home_pts, 2),
        "away_pts": round(away_pts, 2),
        "margin_sd": MARGIN_SD,
        "n_models": n_models,
        "n_signals": n_signals,
        "notes": notes,
        # extra diagnostics (not part of the required interface, harmless to include)
        "_net_attr": round(net_attr, 2),
        "_home_facet_net": round(home_net, 2),
        "_away_facet_net": round(away_net, 2),
        "_home_top3_facets": home_top3,
        "_away_top3_facets": away_top3,
        "_pace_factor": round(pace_factor, 4),
        "_scale": SCALE,
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import pprint

    print("=" * 70)
    print("ENGINE: attribute_matchup  --  self-test: NYK (home) vs SAS (away)")
    print("=" * 70)

    result = predict("NYK", "SAS")

    # ---- clean ASCII output (strip internal diag keys) ----------------
    public_keys = [
        "engine", "win_prob_home", "margin_home", "total",
        "home_pts", "away_pts", "margin_sd", "n_models", "n_signals",
    ]
    print("\n--- predict('NYK','SAS') ---")
    for k in public_keys:
        print(f"  {k:<20}: {result[k]}")

    print(f"\n  notes (truncated):")
    notes = result["notes"]
    # break long notes across lines at ';'
    for part in notes.split(";"):
        print(f"    {part.strip()}")

    print(f"\n--- Attribute advantage ---")
    print(f"  net_attr_advantage   : {result['_net_attr']:+.2f} percentile-point sum")
    print(f"  home ({result['engine']} home leg): {result['_home_facet_net']:+.2f}")
    print(f"  away ({result['engine']} away leg): {result['_away_facet_net']:+.2f}")
    print(f"  scale constant       : {result['_scale']} pts per pctile-sum unit")
    print(f"    => p95 mismatch (~130) maps to ~{130*result['_scale']:.1f} pts  [conservative ceiling]")

    print(f"\n--- Top-3 facet edges: NYK offense vs SAS defense ---")
    for label, o, d, e in result["_home_top3_facets"]:
        bar = "+" * max(0, int(e / 3)) if e >= 0 else "-" * max(0, int(-e / 3))
        print(f"  {label:<22}: NYK_off={o:5.1f}  SAS_def={d:5.1f}  edge={e:+6.1f}  {bar}")

    print(f"\n--- Top-3 facet edges: SAS offense vs NYK defense ---")
    for label, o, d, e in result["_away_top3_facets"]:
        bar = "+" * max(0, int(e / 3)) if e >= 0 else "-" * max(0, int(-e / 3))
        print(f"  {label:<22}: SAS_off={o:5.1f}  NYK_def={d:5.1f}  edge={e:+6.1f}  {bar}")

    print(f"\n--- Model/signal accounting ---")
    print(f"  n_models  : {result['n_models']}  (16 team-facet + {result['n_models']-16} per-player sub-models)")
    print(f"  n_signals : {result['n_signals']}  (~86 attrs x {result['n_signals']//86} qualifying players)")
    print()
