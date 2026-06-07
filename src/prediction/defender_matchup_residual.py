"""defender_matchup_residual.py — runtime per-stat adjustment for known
(offense, defender) matchups using NBA Stats matchup data (e.g. the WCF
playoff matchup tape ``data/cache/intel_<date>/wcf_defensive_matchups.csv``).

Motivation
----------
The cycle-88 → cycle-110 in-play stack projects every player against an
opponent-team-average defensive profile. In a 7-game series this is
*structurally blind* to the specific defender assignment that actually
drives the night: Hartenstein-on-Wemby (90 partial poss, 37 PTS, 5/9 from 3)
versus Holmgren-on-Wemby (52 partial poss, 8 PTS, 3/8 FG). Same opponent,
opposite outcomes.

This module gives the live engine ONE runtime multiplier per (player, stat)
when the snapshot (or caller) supplies the on-court defender. It is a
PURE LOOKUP — no model weights, no training. The signal is the per-poss
rate vs that specific defender divided by the player's series-average
per-poss rate, regressed toward 1.0 by a Bayesian prior so a 30-poss
sample doesn't lurch the projection by 2x.

Public API
----------
    apply_matchup_adjustment(player_id, stat, projection, snapshot=None,
                              defender_id=None, matchup_df=None,
                              series_df=None)
        -> (adjusted_projection: float, reason: str)

    load_matchup_table(path=None) -> pandas.DataFrame
    load_series_avg_table(path=None) -> pandas.DataFrame

Design rule
-----------
The hot path NEVER raises. Every failure (missing CSV, missing pair, low
sample, missing stat column, snapshot without defender field) returns
``(projection, "<reason>")`` unchanged — the caller can log the reason
but the projection is preserved. The live engine wires this BEHIND a
feature flag ``_USE_DEFENDER_MATCHUP_RESIDUAL`` so it can be killed
without redeploy.

Sample size guard
-----------------
We require ``partial_poss >= _MIN_POSS`` (default 30) to apply the
multiplier. Below that, the empirical rate is too noisy to trust. The
hard cap on the multiplier is ``[_MULT_FLOOR, _MULT_CEIL]`` (default
[0.55, 1.55]) — even with 90 possessions a 2.5x rate ratio is more
likely noise/coaching scheme than a stable per-night effect.

Bayesian shrinkage
------------------
``adjusted = projection * (lambda * rate_ratio + (1 - lambda) * 1.0)``
where ``lambda = partial_poss / (partial_poss + _SHRINK_K)`` (default
``_SHRINK_K = 60``). At 30 poss lambda=0.33, at 90 poss lambda=0.60,
at 180 poss lambda=0.75. Pure empirical at 600+ poss.
"""
from __future__ import annotations

import os
from typing import Optional, Tuple

# Lazy pandas — keep module import cheap.
try:
    import pandas as _pd
except Exception:    # pragma: no cover - env without pandas
    _pd = None


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── tunable thresholds ────────────────────────────────────────────────────────

# Minimum partial_poss vs that defender to even apply the multiplier.
_MIN_POSS = 30.0

# Bayesian shrinkage constant — larger = trust the prior longer.
_SHRINK_K = 60.0

# Hard caps on the final multiplier (defence against outlier samples).
_MULT_FLOOR = 0.55
_MULT_CEIL = 1.55

# Map from live_engine stat keys → (numerator column, denominator column)
# in the WCF matchup CSV. "pts" uses pts_allowed / partial_poss. "fg3m"
# uses fg3m_allowed / partial_poss. Defender-side stats (BLK, STL) are
# from the defender's perspective in the matchup tape — they're forced
# events on the offensive player so we treat them as multiplier ON the
# offensive player's projection (more blocks vs this defender ⇒ FG
# down, but we apply directly to blk allowed/forced for the off player).
_STAT_TO_COLS = {
    "pts":  ("pts_allowed", "partial_poss"),
    "fg3m": ("fg3m_allowed", "partial_poss"),
    "reb":  None,    # matchup tape doesn't carry rebounds; no-op stat
    "ast":  ("ast_allowed", "partial_poss"),
    "stl":  ("tov_forced", "partial_poss"),    # turnovers forced by this defender ⇒ scales OFF player TOV
    "blk":  ("blocks", "partial_poss"),         # blocks by defender on off player
    "tov":  ("tov_forced", "partial_poss"),
}

# For each stat, the series-average column in wcf_player_series_avg.csv.
# The matchup tape gives the offensive player's stat-allowed-per-partial-poss
# vs this defender; we divide by the player's own series per-minute baseline,
# scaled to per-poss via an approximate 2.0 poss/min (NBA pace ~100 poss/48 min
# = 2.083 poss/min). The exact scalar washes out because the ratio uses BOTH.
_STAT_TO_SERIES_PG = {
    "pts":  "pts_pg",
    "fg3m": "fg3m_pg",
    "ast":  "ast_pg",
    "stl":  "tov_pg",
    "blk":  "blk_pg",
    "tov":  "tov_pg",
}

# Approximate possessions per minute for the offensive player's TEAM.
# Used to convert the player's per-game stat to per-(team-partial-poss).
# Series average min_pg is the divisor that links pg → per-min → per-poss.
_POSS_PER_MIN = 2.08


# ── csv loaders ──────────────────────────────────────────────────────────────

def _default_matchup_path() -> Optional[str]:
    """Return the most-recent ``wcf_defensive_matchups.csv`` we can find."""
    cache_root = os.path.join(PROJECT_DIR, "data", "cache")
    if not os.path.isdir(cache_root):
        return None
    candidates = []
    for name in os.listdir(cache_root):
        if not name.startswith("intel_"):
            continue
        p = os.path.join(cache_root, name, "wcf_defensive_matchups.csv")
        if os.path.isfile(p):
            candidates.append(p)
    if not candidates:
        return None
    candidates.sort()
    return candidates[-1]


def _default_series_path() -> Optional[str]:
    cache_root = os.path.join(PROJECT_DIR, "data", "cache")
    if not os.path.isdir(cache_root):
        return None
    candidates = []
    for name in os.listdir(cache_root):
        if not name.startswith("intel_"):
            continue
        p = os.path.join(cache_root, name, "wcf_player_series_avg.csv")
        if os.path.isfile(p):
            candidates.append(p)
    if not candidates:
        return None
    candidates.sort()
    return candidates[-1]


_MATCHUP_DF_CACHE = None
_SERIES_DF_CACHE = None


def load_matchup_table(path: Optional[str] = None):
    """Load + cache the matchup CSV. Returns None if pandas absent / file
    missing — caller must tolerate None.
    """
    global _MATCHUP_DF_CACHE
    if _MATCHUP_DF_CACHE is not None and path is None:
        return _MATCHUP_DF_CACHE
    if _pd is None:
        return None
    if path is None:
        path = _default_matchup_path()
    if path is None or not os.path.isfile(path):
        return None
    try:
        df = _pd.read_csv(path)
    except Exception:
        return None
    if path is None or path == _default_matchup_path():
        _MATCHUP_DF_CACHE = df
    return df


def load_series_avg_table(path: Optional[str] = None):
    """Load + cache the series-average CSV."""
    global _SERIES_DF_CACHE
    if _SERIES_DF_CACHE is not None and path is None:
        return _SERIES_DF_CACHE
    if _pd is None:
        return None
    if path is None:
        path = _default_series_path()
    if path is None or not os.path.isfile(path):
        return None
    try:
        df = _pd.read_csv(path)
    except Exception:
        return None
    if path is None or path == _default_series_path():
        _SERIES_DF_CACHE = df
    return df


def _reset_caches_for_test():
    """Test hook only — clear the module-scope DataFrame caches."""
    global _MATCHUP_DF_CACHE, _SERIES_DF_CACHE
    _MATCHUP_DF_CACHE = None
    _SERIES_DF_CACHE = None


# ── core math ────────────────────────────────────────────────────────────────

def _defender_id_from_snapshot(snapshot: Optional[dict], player_id) -> Optional[int]:
    """Best-effort: pull a defender_id for ``player_id`` from the snapshot.

    The canonical ``src/data/live.py`` schema does NOT currently carry a
    per-player "current defender" field. This helper looks for two
    optional extensions:

      1. ``snapshot["matchups"]`` : dict ``{offense_pid: defender_pid}``
      2. The offensive player's own dict carries ``"current_defender_id"``

    If neither is present return None — callers degrade to no-op.
    """
    if snapshot is None:
        return None
    try:
        pid_i = int(player_id)
    except (TypeError, ValueError):
        return None
    m = snapshot.get("matchups")
    if isinstance(m, dict):
        for k, v in m.items():
            try:
                if int(k) == pid_i:
                    return int(v)
            except (TypeError, ValueError):
                continue
    for p in snapshot.get("players") or []:
        try:
            if int(p.get("player_id")) == pid_i:
                d = p.get("current_defender_id")
                if d is not None:
                    return int(d)
        except (TypeError, ValueError):
            continue
    return None


def _compute_rate_ratio(matchup_row, series_row, stat: str) -> Optional[float]:
    """Compute (per-poss vs this defender) / (per-poss series average)."""
    cols = _STAT_TO_COLS.get(stat)
    if cols is None:
        return None
    num_col, den_col = cols
    try:
        num = float(matchup_row[num_col])
        partial_poss = float(matchup_row[den_col])
    except (KeyError, TypeError, ValueError):
        return None
    if partial_poss <= 0:
        return None
    rate_vs_def = num / partial_poss    # stat per partial possession

    series_col = _STAT_TO_SERIES_PG.get(stat)
    if series_col is None:
        return None
    try:
        stat_pg = float(series_row[series_col])
        min_pg = float(series_row["min_pg"])
    except (KeyError, TypeError, ValueError):
        return None
    if min_pg <= 0 or stat_pg < 0:
        return None
    # Convert pg → per-poss: pg / (min_pg * poss_per_min)
    series_rate = stat_pg / (min_pg * _POSS_PER_MIN)
    if series_rate <= 1e-6:
        return None
    return rate_vs_def / series_rate


def _shrink_multiplier(rate_ratio: float, partial_poss: float) -> float:
    """Bayesian shrinkage toward 1.0; clamp to [_MULT_FLOOR, _MULT_CEIL]."""
    lam = partial_poss / (partial_poss + _SHRINK_K)
    raw = lam * rate_ratio + (1.0 - lam) * 1.0
    return max(_MULT_FLOOR, min(_MULT_CEIL, raw))


# ── public API ───────────────────────────────────────────────────────────────

def apply_matchup_adjustment(
    player_id,
    stat: str,
    projection: float,
    snapshot: Optional[dict] = None,
    defender_id: Optional[int] = None,
    matchup_df=None,
    series_df=None,
) -> Tuple[float, str]:
    """Return (adjusted_projection, reason). ``reason`` is always populated
    so the caller can log WHY we kept / changed the number.

    Resolution order for the defender id:
      1. explicit ``defender_id`` kwarg
      2. ``snapshot["matchups"][player_id]``
      3. ``snapshot["players"][i]["current_defender_id"]``
    """
    try:
        proj = float(projection)
    except (TypeError, ValueError):
        return projection, "matchup_skip:projection_not_numeric"

    stat_l = (stat or "").lower()
    if stat_l not in _STAT_TO_COLS or _STAT_TO_COLS[stat_l] is None:
        return proj, f"matchup_skip:stat_not_supported:{stat_l}"

    # Resolve defender id.
    if defender_id is None:
        defender_id = _defender_id_from_snapshot(snapshot, player_id)
    if defender_id is None:
        return proj, "matchup_skip:defender_not_in_snapshot"

    if matchup_df is None:
        matchup_df = load_matchup_table()
    if matchup_df is None:
        return proj, "matchup_skip:matchup_csv_missing"
    if series_df is None:
        series_df = load_series_avg_table()
    if series_df is None:
        return proj, "matchup_skip:series_csv_missing"

    try:
        pid_i = int(player_id)
        did_i = int(defender_id)
    except (TypeError, ValueError):
        return proj, "matchup_skip:non_int_ids"

    # Locate the (offense, defender) row.
    pair = matchup_df[
        (matchup_df["off_player_id"] == pid_i)
        & (matchup_df["def_player_id"] == did_i)
    ]
    if pair.empty:
        return proj, f"matchup_skip:pair_not_in_table:{pid_i}->{did_i}"
    row = pair.iloc[0]

    try:
        partial_poss = float(row["partial_poss"])
    except (KeyError, TypeError, ValueError):
        return proj, "matchup_skip:partial_poss_unparseable"
    if partial_poss < _MIN_POSS:
        return proj, (f"matchup_skip:low_sample:{partial_poss:.1f}poss"
                      f"<{_MIN_POSS:.0f}")

    series_match = series_df[series_df["player_id"] == pid_i]
    if series_match.empty:
        return proj, f"matchup_skip:off_player_missing_series_avg:{pid_i}"
    series_row = series_match.iloc[0]

    ratio = _compute_rate_ratio(row, series_row, stat_l)
    if ratio is None:
        return proj, f"matchup_skip:rate_uncomputable:{stat_l}"

    mult = _shrink_multiplier(ratio, partial_poss)
    adjusted = proj * mult
    return adjusted, (
        f"matchup_applied:def={did_i},stat={stat_l},poss={partial_poss:.1f},"
        f"ratio={ratio:.3f},mult={mult:.3f}"
    )


__all__ = [
    "apply_matchup_adjustment",
    "load_matchup_table",
    "load_series_avg_table",
]
