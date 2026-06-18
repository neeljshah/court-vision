"""Leak-free, empirical-Bayes-shrunk per-exposure rate priors for MLB props.

Mirrors domains/soccer/player_rates.py but the exposure unit differs by role:
  - BATTERS: rate is per plate-appearance (PA). PA proxy = atBats + baseOnBalls
    + hitByPitch. lam later = per_pa * E[PA].
  - PITCHERS: rate is per batter-faced (BF). BF = battersFaced. lam = per_bf*E[BF].
    EXCEPT "Outs", which is exposure-natural and modelled per START (mean outs).

Every output is keyed by a CANONICAL MLB stat name (MLB_CANON) so it joins
downstream to scraped MLB prop lines.

LEAK-FREENESS (load-bearing): every rate uses ONLY rows whose ``date`` is STRICTLY
BEFORE ``as_of`` -- a player's own row dated on/after the game is never an input.

MLB is mid-season so regulars have plenty of PA; empirical-Bayes shrink (K~30
PA-worth toward the LEAGUE per-exposure baseline) is light for regulars, heavy for
call-ups / thin pitchers. No $-edge claims; calibration is the yardstick.

Public functions NEVER raise -- they degrade to {"status": "unknown"}.

Run the per-file test (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_player_rates_mlb.py -q
"""
from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

# Shrinkage strength in "PA-worth" (batters) or "BF-worth" (pitchers). ~30 PA is
# light for a regular (hundreds of PA by mid-season) but heavy for a call-up.
SHRINK_K = 30.0
# For per-START stats (Outs) shrink in "starts-worth"; a few starts settle it.
SHRINK_K_START = 3.0
_EPS = 1e-9

# Canonical BATTER stat -> raw columns to SUM per game (exposure = PA).
BATTER_CANON: Dict[str, List[str]] = {
    "Hits": ["hits"],
    "Total Bases": ["totalBases"],
    "RBIs": ["rbi"],
    "Runs": ["runs"],
    "Home Runs": ["homeRuns"],
    "Walks": ["baseOnBalls"],
    "Batter Strikeouts": ["strikeOuts"],
    "Stolen Bases": ["stolenBases"],
    "Hits+Runs+RBIs": ["hits", "runs", "rbi"],
}

# Canonical PITCHER stat -> raw columns to SUM per game (exposure = BF, except
# "Outs" which is per-start).
PITCHER_CANON: Dict[str, List[str]] = {
    "Pitcher Strikeouts": ["pitch_strikeOuts"],
    "Earned Runs": ["earnedRuns"],
    "Hits Allowed": ["hits_allowed"],
    "Walks Allowed": ["baseOnBalls_allowed"],
    "Outs": ["outs"],
}

# Combined canonical map: stat -> {"cols", "role", "exposure"}.
MLB_CANON: Dict[str, Dict[str, object]] = {}
for _s, _c in BATTER_CANON.items():
    MLB_CANON[_s] = {"cols": _c, "role": "batter", "exposure": "pa"}
for _s, _c in PITCHER_CANON.items():
    _exp = "start" if _s == "Outs" else "bf"
    MLB_CANON[_s] = {"cols": _c, "role": "pitcher", "exposure": _exp}

# Per-start stats are exposure-natural (modelled directly per game start).
PER_START_STATS = {"Outs"}


def canonical_stats() -> List[str]:
    """All canonical MLB stat names this engine can produce."""
    return list(MLB_CANON.keys())


def is_pitcher_stat(stat_canonical: str) -> bool:
    """True if the canonical stat is a pitcher stat (per-BF / per-start path)."""
    spec = MLB_CANON.get(stat_canonical)
    return bool(spec) and spec.get("role") == "pitcher"


def _as_ts(value) -> Optional[pd.Timestamp]:
    try:
        ts = pd.Timestamp(value)
        return None if pd.isna(ts) else ts
    except Exception:
        return None


def _prior_rows(df: pd.DataFrame, as_of) -> Optional[pd.DataFrame]:
    """Rows STRICTLY BEFORE as_of (leak guard). None on bad input."""
    if df is None or len(df) == 0 or "date" not in df.columns:
        return None
    ts = _as_ts(as_of)
    if ts is None:
        return None
    dates = pd.to_datetime(df["date"], errors="coerce")
    mask = dates.notna() & (dates < ts)
    return df.loc[mask]


def _col_sum(rows: pd.DataFrame, cols: List[str]) -> float:
    total = 0.0
    for col in cols:
        if col in rows.columns:
            total += pd.to_numeric(rows[col], errors="coerce").fillna(0.0).sum()
    return float(total)


def _stat_total(rows: pd.DataFrame, stat_canonical: str) -> Optional[float]:
    spec = MLB_CANON.get(stat_canonical)
    if spec is None:
        return None
    return _col_sum(rows, spec["cols"])  # type: ignore[arg-type]


def _pa_total(rows: pd.DataFrame) -> float:
    """Plate-appearance proxy = atBats + baseOnBalls + hitByPitch."""
    return _col_sum(rows, ["atBats", "baseOnBalls", "hitByPitch"])


def _bf_total(rows: pd.DataFrame) -> float:
    return _col_sum(rows, ["battersFaced"])


def _own_rows(prior: pd.DataFrame, player_id) -> pd.DataFrame:
    if "player_id" not in prior.columns:
        return prior
    return prior.loc[prior["player_id"].astype(str) == str(player_id)]


def _league_per_exposure(
    df: pd.DataFrame, stat_canonical: str, as_of, exposure: str
) -> Optional[float]:
    """Pooled league per-PA / per-BF / per-start baseline using rows before as_of.

    For batter stats pools rows where PA>0; for pitcher per-BF pools rows BF>0;
    for per-start pools pitcher rows that recorded outs (a start). None if no
    signal."""
    prior = _prior_rows(df, as_of)
    if prior is None or len(prior) == 0:
        return None
    spec = MLB_CANON.get(stat_canonical)
    if spec is None:
        return None
    role = spec["role"]
    if "is_pitcher" in prior.columns:
        want = (role == "pitcher")
        flag = prior["is_pitcher"].fillna(False).astype(bool)
        prior = prior.loc[flag == want]
    if len(prior) == 0:
        return None
    total_stat = _stat_total(prior, stat_canonical)
    if total_stat is None:
        return None
    if exposure == "pa":
        denom = _pa_total(prior)
    elif exposure == "bf":
        denom = _bf_total(prior)
    else:  # per-start: count games (starts)
        denom = float(len(prior))
    if denom <= _EPS:
        return None
    return total_stat / denom


def _result(per_key, per_val, n_key, n_val, shrunk, status):
    return {per_key: per_val, n_key: int(n_val), "shrunk": shrunk, "status": status}


def batter_rate(
    df: pd.DataFrame, player_id, stat_canonical: str, as_of
) -> Dict[str, object]:
    """Leak-free, shrunk per-PA rate for one batter + canonical stat.

    Returns {"per_pa": float|None, "n_pa": int, "shrunk": bool, "status"}.
    rate = sum(stat)/sum(PA) over rows before as_of, empirical-Bayes shrunk toward
    the league per-PA baseline with strength SHRINK_K (~30 PA-worth). status
    "unknown" when neither the player nor the league has any signal. Never raises.
    """
    unknown = _result("per_pa", None, "n_pa", 0, False, "unknown")
    spec = MLB_CANON.get(stat_canonical)
    if spec is None or spec["role"] != "batter":
        return dict(unknown)
    prior = _prior_rows(df, as_of)
    if prior is None:
        return dict(unknown)

    own = _own_rows(prior, player_id)
    n_pa = _pa_total(own)
    baseline = _league_per_exposure(df, stat_canonical, as_of, "pa")

    if n_pa <= _EPS:
        if baseline is None:
            return dict(unknown)
        return _result("per_pa", float(baseline), "n_pa", 0, True, "ok")

    raw = (_stat_total(own, stat_canonical) or 0.0) / n_pa
    if baseline is None:
        return _result("per_pa", float(raw), "n_pa", round(n_pa), False, "ok")
    shrunk = (n_pa * raw + SHRINK_K * baseline) / (n_pa + SHRINK_K)
    return _result("per_pa", float(shrunk), "n_pa", round(n_pa), True, "ok")


def pitcher_rate(
    df: pd.DataFrame, player_id, stat_canonical: str, as_of
) -> Dict[str, object]:
    """Leak-free, shrunk per-BF rate for one pitcher + canonical stat.

    Returns {"per_bf": float|None, "n_bf": int, "shrunk", "status"} -- EXCEPT for
    "Outs", which is per-start: {"per_start": float|None, "n_start": int, ...}.
    rate uses only rows before as_of, shrunk toward the league baseline (SHRINK_K
    BF-worth, or SHRINK_K_START starts for Outs). status "unknown" when no signal.
    Never raises.
    """
    spec = MLB_CANON.get(stat_canonical)
    per_start = stat_canonical in PER_START_STATS
    per_key = "per_start" if per_start else "per_bf"
    n_key = "n_start" if per_start else "n_bf"
    unknown = _result(per_key, None, n_key, 0, False, "unknown")
    if spec is None or spec["role"] != "pitcher":
        return dict(unknown)
    prior = _prior_rows(df, as_of)
    if prior is None:
        return dict(unknown)

    own = _own_rows(prior, player_id)
    if per_start:
        n = float(len(own))
        baseline = _league_per_exposure(df, stat_canonical, as_of, "start")
        k = SHRINK_K_START
    else:
        n = _bf_total(own)
        baseline = _league_per_exposure(df, stat_canonical, as_of, "bf")
        k = SHRINK_K

    if n <= _EPS:
        if baseline is None:
            return dict(unknown)
        return _result(per_key, float(baseline), n_key, 0, True, "ok")

    raw = (_stat_total(own, stat_canonical) or 0.0) / n
    if baseline is None:
        return _result(per_key, float(raw), n_key, round(n), False, "ok")
    shrunk = (n * raw + k * baseline) / (n + k)
    return _result(per_key, float(shrunk), n_key, round(n), True, "ok")
