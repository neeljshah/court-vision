"""season_progress_shrinkage.py — R32_Y2 season-progress shrinkage.

Window-artifact features (e.g. ``home_top_lineup_net_rtg`` =27.4 in current
season vs ref_mean 4.2) drift because the R27_T3 detector compares an
end-of-season-stabilized REFERENCE distribution against a mid-season
CURRENT distribution that is still dominated by early-season noise.

Top-N lineup net rating is the classic case: through 5 games the best
five-man unit's net_rtg is inflated (top-of-distribution noise); by game
70 the values regress to true talent (~4 pts/100). Same pattern for L10
ratings, ELO, etc.

Fix (this module): shrink the current value toward the historical league
mean by a weight that decays as the season elapses:

    elapsed_frac  = min(1.0, n_games_played / total_games)
    shrink_weight = (1 - elapsed_frac) ** alpha
    shrunk        = shrink_weight * league_mean + (1 - shrink_weight) * value

At ``elapsed_frac=0`` (no games played) the shrunk value equals the
league mean (maximum shrinkage). At ``elapsed_frac=1.0`` (end of season)
the shrunk value equals the raw value (no shrinkage). ``alpha`` controls
how sharply shrinkage decays — larger alpha = faster decay = less
shrinkage in the middle of the season.

This is a POST-process over already-computed leak-free expanding-window
values. We never touch the leak-free computation itself.

Public surface
--------------
    shrink(value, league_mean, n_games_played, total_games=82, alpha=0.5)
        -> float

    shrink_series(values, league_means, n_games_played, total_games=82,
                  alpha=0.5) -> np.ndarray
        # vectorized version; accepts scalars, lists, np.arrays, pd.Series

    DEFAULT_WINDOW_ARTIFACT_FEATURES  (frozenset of 22 feature names)
        # the features R29_V3 classifies as window_artifact

    SHRINKAGE_CONFIG  (dict)
        # per-feature {league_mean: float, alpha: float} defaults
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional, Union

import numpy as np

# --------------------------------------------------------------------------- #
# Feature catalog                                                             #
# --------------------------------------------------------------------------- #
# Mirrors the "window_artifact" verdict in
# scripts/improve_loop/probe_R29_V3_residual_drift.py::_CATEGORIZATION
# (22 features) plus the two lineup features from R31_X6 (data gap closed
# but distribution remains window-shape — early-season games still have
# only 2-3 games' worth of lineup data per team). The 22 R29_V3 features
# are the canonical set referenced in the R32_Y2 ship gate; the 2 lineup
# features are an additive group reclassified by R31_X6.
R29_V3_WINDOW_ARTIFACT_FEATURES = frozenset({
    "home_off_rtg",
    "away_off_rtg",
    "home_def_rtg",
    "away_def_rtg",
    "home_pace",
    "away_pace",
    "home_ts_pct",
    "away_ts_pct",
    "away_tov_pct",
    "home_off_rtg_L10",
    "home_def_rtg_L10",
    "away_off_rtg_L10",
    "away_def_rtg_L10",
    "home_net_rtg_L10",
    "away_net_rtg_L10",
    "home_efg_L10",
    "away_efg_L10",
    "home_off_rtg_home_L10",
    "away_off_rtg_away_L10",
    "home_elo",
    "away_elo",
    "elo_differential",
})

R31_X6_LINEUP_WINDOW_ARTIFACT_FEATURES = frozenset({
    "home_top_lineup_net_rtg",
    "away_top_lineup_net_rtg",
})

# Union: every feature whose mid-season distribution drifts purely due to
# season-progress noise vs. an end-of-season reference. Shrinkage applies
# to all of them.
DEFAULT_WINDOW_ARTIFACT_FEATURES = frozenset({
    # 4-factor expanding-window ratings
    "home_off_rtg",
    "away_off_rtg",
    "home_def_rtg",
    "away_def_rtg",
    "home_pace",
    "away_pace",
    "home_ts_pct",
    "away_ts_pct",
    "away_tov_pct",
    # L10 rolling ratings (reference mixes early-season defaults)
    "home_off_rtg_L10",
    "home_def_rtg_L10",
    "away_off_rtg_L10",
    "away_def_rtg_L10",
    "home_net_rtg_L10",
    "away_net_rtg_L10",
    "home_efg_L10",
    "away_efg_L10",
    "home_off_rtg_home_L10",
    "away_off_rtg_away_L10",
    # ELO accumulators (1500 starts in reference; mid-season values inflated)
    "home_elo",
    "away_elo",
    "elo_differential",
    # Top-lineup net rating (R31_X6 reclassified -> window_artifact)
    "home_top_lineup_net_rtg",
    "away_top_lineup_net_rtg",
})

# Per-feature shrinkage config: league_mean defaults are taken from the
# REFERENCE-SEASON means in data/cache/drift_post_R31_X6.json (2022-23 +
# 2023-24 + 2024-25 combined). These are prior-season truth — no current-
# season leakage. ``alpha`` defaults to 0.5 (sqrt-shape decay); calibrate
# per-feature later if a slower/faster decay tightens any specific drift.
SHRINKAGE_CONFIG: Dict[str, Dict[str, float]] = {
    "home_off_rtg":            {"league_mean": 114.10, "alpha": 0.5},
    "away_off_rtg":            {"league_mean": 114.10, "alpha": 0.5},
    "home_def_rtg":            {"league_mean": 114.09, "alpha": 0.5},
    "away_def_rtg":            {"league_mean": 114.09, "alpha": 0.5},
    "home_pace":               {"league_mean": 99.51,  "alpha": 0.5},
    "away_pace":               {"league_mean": 99.51,  "alpha": 0.5},
    "home_ts_pct":             {"league_mean": 0.579,  "alpha": 0.5},
    "away_ts_pct":             {"league_mean": 0.579,  "alpha": 0.5},
    "away_tov_pct":            {"league_mean": 0.140,  "alpha": 0.5},
    "home_off_rtg_L10":        {"league_mean": 112.04, "alpha": 0.5},
    "home_def_rtg_L10":        {"league_mean": 112.11, "alpha": 0.5},
    "away_off_rtg_L10":        {"league_mean": 112.13, "alpha": 0.5},
    "away_def_rtg_L10":        {"league_mean": 112.05, "alpha": 0.5},
    "home_net_rtg_L10":        {"league_mean": -0.074, "alpha": 0.5},
    "away_net_rtg_L10":        {"league_mean": 0.079,  "alpha": 0.5},
    "home_efg_L10":            {"league_mean": 0.544,  "alpha": 0.5},
    "away_efg_L10":            {"league_mean": 0.544,  "alpha": 0.5},
    "home_off_rtg_home_L10":   {"league_mean": 112.85, "alpha": 0.5},
    "away_off_rtg_away_L10":   {"league_mean": 110.79, "alpha": 0.5},
    "home_elo":                {"league_mean": 1500.23, "alpha": 0.5},
    "away_elo":                {"league_mean": 1499.91, "alpha": 0.5},
    "elo_differential":        {"league_mean": 0.315,  "alpha": 0.5},
    "home_top_lineup_net_rtg": {"league_mean": 4.22,   "alpha": 0.5},
    "away_top_lineup_net_rtg": {"league_mean": 4.20,   "alpha": 0.5},
}

DEFAULT_TOTAL_GAMES = 82


# --------------------------------------------------------------------------- #
# Core math                                                                   #
# --------------------------------------------------------------------------- #
def shrink(
    value: float,
    league_mean: float,
    n_games_played: float,
    total_games: int = DEFAULT_TOTAL_GAMES,
    alpha: float = 0.5,
) -> float:
    """Shrink a single value toward ``league_mean`` by season-progress weight.

    Parameters
    ----------
    value : float
        Raw computed feature value.
    league_mean : float
        Prior-season truth for this feature (no current-season leakage).
    n_games_played : float
        Number of games played by the team UP TO BUT NOT INCLUDING the
        current row (so the feature already reflects season-to-date math).
    total_games : int, default 82
        Total games in a regular season.
    alpha : float, default 0.5
        Decay exponent. weight = (1 - elapsed_frac) ** alpha.
        alpha < 1.0 -> sub-linear decay (more aggressive early-season shrink).
        alpha = 1.0 -> linear decay.
        alpha > 1.0 -> super-linear decay (shrinkage drops faster).

    Returns
    -------
    float
        ``weight * league_mean + (1 - weight) * value``.

    Boundary semantics
    ------------------
    * n_games_played <= 0           -> weight = 1.0  -> returns league_mean
    * n_games_played >= total_games -> weight = 0.0  -> returns value
    * NaN value                     -> returns NaN  (passthrough)
    * NaN league_mean               -> returns value (no shrink possible)
    """
    # NaN passthrough rules: value-NaN propagates; league-mean-NaN means we
    # can't shrink so return the raw value (better than NaN).
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return float("nan")
    if league_mean is None or (
        isinstance(league_mean, float) and np.isnan(league_mean)
    ):
        return float(value)

    n = float(n_games_played) if n_games_played is not None else 0.0
    t = max(int(total_games), 1)
    elapsed = max(0.0, min(1.0, n / t))
    a = max(0.0, float(alpha))
    weight = (1.0 - elapsed) ** a
    return float(weight) * float(league_mean) + (1.0 - float(weight)) * float(value)


def shrink_series(
    values: Union[Iterable[float], np.ndarray],
    league_means: Union[float, Iterable[float], np.ndarray],
    n_games_played: Union[Iterable[float], np.ndarray, float],
    total_games: int = DEFAULT_TOTAL_GAMES,
    alpha: float = 0.5,
) -> np.ndarray:
    """Vectorized shrink. Accepts pd.Series / list / np.ndarray / scalars.

    Broadcasts ``league_means`` and ``n_games_played`` to the shape of
    ``values``. NaN handling matches the scalar ``shrink``:
      * NaN in values stays NaN.
      * NaN in league_mean returns the raw value (no shrink possible).

    Returns a numpy array of the same length as ``values``.
    """
    vals = np.asarray(values, dtype=float)
    means = np.broadcast_to(
        np.asarray(league_means, dtype=float), vals.shape
    ).astype(float)
    n_played = np.broadcast_to(
        np.asarray(n_games_played, dtype=float), vals.shape
    ).astype(float)

    t = max(int(total_games), 1)
    elapsed = np.clip(n_played / float(t), 0.0, 1.0)
    a = max(0.0, float(alpha))
    weight = np.power(1.0 - elapsed, a)

    out = weight * means + (1.0 - weight) * vals

    # NaN handling
    val_nan = np.isnan(vals)
    mean_nan = np.isnan(means)
    # value-NaN -> NaN
    out = np.where(val_nan, np.nan, out)
    # league-mean-NaN (and value is not NaN) -> raw value
    out = np.where((~val_nan) & mean_nan, vals, out)
    return out


# --------------------------------------------------------------------------- #
# Convenience: shrink a season_games rows list in-place                       #
# --------------------------------------------------------------------------- #
def compute_games_played_lookup(
    rows: Iterable[Mapping[str, Any]],
) -> Dict[str, Dict[str, int]]:
    """Walk rows chronologically and build a {game_id: {team: n_played_prior}}.

    ``n_played_prior`` is the number of games each team has completed
    STRICTLY BEFORE this game_id — matches the semantic the leak-free
    expanding-window stats already use (they're shifted by 1 game).
    """
    # Sort by date then game_id for chronological order.
    sorted_rows = sorted(
        list(rows),
        key=lambda r: (str(r.get("game_date", "")), str(r.get("game_id", ""))),
    )
    counts: Dict[str, int] = {}
    out: Dict[str, Dict[str, int]] = {}
    for r in sorted_rows:
        gid = str(r.get("game_id", ""))
        h = r.get("home_team")
        a = r.get("away_team")
        if not gid or not isinstance(h, str) or not isinstance(a, str):
            continue
        out[gid] = {"home": counts.get(h, 0), "away": counts.get(a, 0)}
        counts[h] = counts.get(h, 0) + 1
        counts[a] = counts.get(a, 0) + 1
    return out


def apply_shrinkage_to_rows(
    rows: list,
    *,
    features: Optional[Iterable[str]] = None,
    config: Optional[Mapping[str, Mapping[str, float]]] = None,
    total_games: int = DEFAULT_TOTAL_GAMES,
) -> Dict[str, Any]:
    """Apply season-progress shrinkage to every window-artifact feature in
    each row. Mutates ``rows`` in place. Returns a per-feature summary.

    Side parsing: a feature prefixed ``home_`` uses the home_team's
    n_games_played; ``away_`` uses the away_team's. Symmetric features
    (e.g. ``elo_differential``) use the MEAN of both sides' counts so the
    shrinkage weight scales with how much data BOTH teams have.
    """
    feats = list(features) if features is not None else list(
        DEFAULT_WINDOW_ARTIFACT_FEATURES
    )
    cfg: Mapping[str, Mapping[str, float]] = config or SHRINKAGE_CONFIG
    gp_lookup = compute_games_played_lookup(rows)

    summary: Dict[str, Any] = {
        "n_rows": len(rows),
        "n_features": 0,
        "per_feature": {},
    }
    n_features = 0
    for feat in feats:
        meta = cfg.get(feat)
        if not meta:
            continue
        league_mean = float(meta.get("league_mean", 0.0))
        alpha = float(meta.get("alpha", 0.5))
        before_mean = 0.0
        after_mean = 0.0
        n_touched = 0
        for r in rows:
            v = r.get(feat)
            if v is None or not isinstance(v, (int, float)):
                continue
            gid = str(r.get("game_id", ""))
            sides = gp_lookup.get(gid, {"home": 0, "away": 0})
            if feat.startswith("home_"):
                n_played = sides.get("home", 0)
            elif feat.startswith("away_"):
                n_played = sides.get("away", 0)
            else:
                # Symmetric feature: use mean of both sides.
                n_played = (sides.get("home", 0) + sides.get("away", 0)) / 2.0
            shrunk = shrink(float(v), league_mean, n_played,
                            total_games=total_games, alpha=alpha)
            before_mean += float(v)
            after_mean += shrunk
            r[feat] = shrunk
            n_touched += 1
        if n_touched > 0:
            summary["per_feature"][feat] = {
                "n_touched":   n_touched,
                "mean_before": before_mean / n_touched,
                "mean_after":  after_mean / n_touched,
                "league_mean": league_mean,
                "alpha":       alpha,
            }
            n_features += 1
    summary["n_features"] = n_features
    return summary


__all__ = [
    "DEFAULT_WINDOW_ARTIFACT_FEATURES",
    "R29_V3_WINDOW_ARTIFACT_FEATURES",
    "R31_X6_LINEUP_WINDOW_ARTIFACT_FEATURES",
    "SHRINKAGE_CONFIG",
    "DEFAULT_TOTAL_GAMES",
    "shrink",
    "shrink_series",
    "compute_games_played_lookup",
    "apply_shrinkage_to_rows",
]
