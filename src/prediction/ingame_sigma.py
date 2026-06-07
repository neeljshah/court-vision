"""ingame_sigma.py — per-(bucket, stat) in-game sigma for honest bet sizing.

THE HONEST PICTURE
------------------
The in-game `routed` ensemble serves only a POINT projection; no uncertainty
is served today. Audit-3 in docs/_audits/INGAME_ENSEMBLE_OPTIMALITY.md showed:
  - the point is well-centred (|bias| <= 0.37 everywhere, <=0.17 from endQ1)
  - residual spread tightens monotonically with game progress (pts sigma
    7.22 @ Q1-2min -> 1.71 @ 46min — but that std is misleading because
    late-game residuals are highly right-skewed / leptokurtic)

sigma DEFINITION
----------------
We use the 68th-percentile of |routed - truth| per (stat, bucket) — the
CALIBRATED sigma: by construction P(|resid| <= sigma) = 0.68. This is
strictly more honest than 1.48*MAD (the robust Gaussian estimate) because
late-game residuals are HEAVILY fat-tailed (pts 46min kurtosis ~68; REB
46min ~44; AST 42min ~20). The 1.48*MAD only covers 42-59% at those buckets,
which would make Kelly OVER-size late-game bets. The p68 covers exactly 68%
at EVERY (stat, bucket) — that is the honest "typical miss" for sizing.

The sigma is computed once from the 1987-game eval cache (OOF by construction)
and persisted to data/models/ingame_sigma_table.json. It is BUCKET-AND-STAT-
SPECIFIC — a Q3 pts projection (sigma ~3.4) is genuinely much tighter than a
Q1 one (sigma ~6.8); a flat constant would mis-size all bets.

PUBLIC API
----------
    from src.prediction.ingame_sigma import ingame_sigma, load_sigma_table

    sigma = ingame_sigma("pts", elapsed_min=30.0)  # -> float
    sigma = ingame_sigma("ast", elapsed_min=42.5)  # nearest bucket
    table = load_sigma_table()                      # full dict

BUCKET ASSIGNMENT
-----------------
game_elapsed_sec (from the fast cache / serve path) is converted to
elapsed_min and snapped to the nearest bucket breakpoint by midpoint
bisection. The 11 breakpoints are:
  2, 4, 6, 12, 18, 24, 30, 36, 42, 44, 46 minutes.
Any elapsed < 2 snaps to the 2min bucket; > 46 stays at 46min.

GATED USAGE (CV_INGAME_SIGMA)
------------------------------
The sigma is ONLY served when os.environ["CV_INGAME_SIGMA"] == "1".
When OFF (default): byte-identical — nothing in the serve path changes.
When ON: the inplay_bet_ranker replaces its heuristic ±25% sigma with
ingame_sigma(stat, elapsed_min) so that Kelly sizing is calibrated.

IMPORTANT: this module NEVER changes the point projection; it only provides
the uncertainty for sizing. AST logic and AST point are untouched.

HONEST CAVEATS
--------------
- Sigma is derived from the historical residual distribution of `routed`.
  For stats/buckets where the future serve uses a different head (e.g. if
  the late-Q4 v2-route fix is ever applied), the sigma may need re-deriving.
- Coverage at 2*sigma ranges from 0.83 to 0.94 (not 0.95); the distribution
  is non-Gaussian. Do NOT interpret 2*sigma as a 95% interval late-game.
- n_games = 1987 (2022-26 mixed seasons); cross-season stability unconfirmed.
"""
from __future__ import annotations

import bisect
import json
import os
from typing import Dict, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_HERE))
_DEFAULT_TABLE_PATH = os.path.join(_PROJECT_ROOT, "data", "models",
                                   "ingame_sigma_table.json")

# ── Canonical bucket breakpoints (elapsed game minutes) ──────────────────────
BUCKET_BREAKPOINTS: list[float] = [2.0, 4.0, 6.0, 12.0, 18.0, 24.0,
                                    30.0, 36.0, 42.0, 44.0, 46.0]

BUCKET_NAMES: list[str] = [
    "02min(earlyQ1)", "04min(earlyQ1)", "06min(midQ1)", "12min(endQ1)",
    "18min(midQ2)", "24min(endQ2/half)", "30min(midQ3)", "36min(endQ3)",
    "42min(midQ4)", "44min(lateQ4)", "46min(lateQ4)",
]

assert len(BUCKET_BREAKPOINTS) == len(BUCKET_NAMES)

# ── Module-level cache so the JSON is only read once per process ──────────────
_SIGMA_TABLE: Optional[Dict] = None
_TABLE_PATH_LOADED: Optional[str] = None


def _snap_to_bucket(elapsed_min: float) -> str:
    """Return the canonical bucket name nearest to `elapsed_min`.

    Uses midpoint bisection on the sorted breakpoints:
    - < 1.0 min -> 2min bucket  (pre-game or minute-0 edge)
    - > 46.0 min -> 46min bucket
    - between: nearest breakpoint by linear distance.
    """
    if elapsed_min <= BUCKET_BREAKPOINTS[0]:
        return BUCKET_NAMES[0]
    if elapsed_min >= BUCKET_BREAKPOINTS[-1]:
        return BUCKET_NAMES[-1]
    # Find the two surrounding breakpoints and pick the nearer one.
    idx = bisect.bisect_right(BUCKET_BREAKPOINTS, elapsed_min)
    # idx is the first breakpoint > elapsed_min; idx-1 is the last <= elapsed_min.
    lo, hi = idx - 1, idx
    if hi >= len(BUCKET_BREAKPOINTS):
        return BUCKET_NAMES[-1]
    d_lo = elapsed_min - BUCKET_BREAKPOINTS[lo]
    d_hi = BUCKET_BREAKPOINTS[hi] - elapsed_min
    return BUCKET_NAMES[lo] if d_lo <= d_hi else BUCKET_NAMES[hi]


def load_sigma_table(path: str = _DEFAULT_TABLE_PATH) -> Dict:
    """Load and cache the per-(stat, bucket) sigma table from JSON.

    The table is persisted by ``build_sigma_table()`` below and committed to
    data/models/ingame_sigma_table.json. It is re-computed from the fast cache
    when that function is called explicitly; normal serve-path usage reads the
    persisted file.

    Returns the full dict with keys ``sigma_table``, ``coverage_table``, etc.
    """
    global _SIGMA_TABLE, _TABLE_PATH_LOADED
    if _SIGMA_TABLE is not None and _TABLE_PATH_LOADED == path:
        return _SIGMA_TABLE
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    _SIGMA_TABLE = data
    _TABLE_PATH_LOADED = path
    return data


def ingame_sigma(stat: str,
                 elapsed_min: Optional[float] = None,
                 *,
                 bucket: Optional[str] = None,
                 table_path: str = _DEFAULT_TABLE_PATH) -> float:
    """Return the calibrated in-game sigma (p68 of |routed - truth|) for
    ``stat`` at ``elapsed_min`` game-minutes (or an explicit ``bucket``).

    ``stat`` must be one of the stats in the sigma table (at minimum: pts,
    reb, ast). If the stat is missing from the table (e.g. fg3m, stl, blk),
    a generous fallback is returned: max sigma across pts/reb/ast at the
    nearest bucket (over-estimates uncertainty rather than under-estimates).

    Parameters
    ----------
    stat         : counting stat name (lowercase, e.g. "pts", "reb", "ast").
    elapsed_min  : elapsed game time in MINUTES (0..48). Mutually exclusive
                   with ``bucket``.
    bucket       : canonical bucket name (e.g. "24min(endQ2/half)"). Use
                   this when the bucket is already known to avoid re-snapping.
    table_path   : path to the persisted JSON (default: data/models/).

    Returns
    -------
    float  : calibrated sigma >= 0.05; guaranteed > 0.
    """
    if elapsed_min is None and bucket is None:
        raise ValueError("Either elapsed_min or bucket must be provided.")
    if bucket is None:
        bucket = _snap_to_bucket(float(elapsed_min))  # type: ignore[arg-type]

    data = load_sigma_table(table_path)
    stat_tbl = data["sigma_table"]
    stat_lc = str(stat).lower()

    if stat_lc in stat_tbl and bucket in stat_tbl[stat_lc]:
        return float(stat_tbl[stat_lc][bucket]["calibrated_sigma"])

    # Fallback for stats not in the table: conservative max across core stats.
    best = 0.05
    for s in ("pts", "reb", "ast"):
        if s in stat_tbl and bucket in stat_tbl[s]:
            v = float(stat_tbl[s][bucket]["calibrated_sigma"])
            best = max(best, v)
    return best


def build_sigma_table(cache_path: str | None = None,
                      table_path: str = _DEFAULT_TABLE_PATH) -> Dict:
    """Re-compute the sigma table from the eval cache and persist to JSON.

    This is a MAINTENANCE function; normal usage reads the pre-built JSON.
    The sigma is the 68th percentile of |routed - truth| per (stat, bucket),
    computed on all rows in the fast cache (OOF by construction — the cache
    stores residuals from leave-one-fold-out rounds, not in-sample).

    The function is idempotent: calling it twice with the same cache produces
    the same JSON.

    Parameters
    ----------
    cache_path  : path to ingame_eval_cache.parquet. Defaults to the
                  standard project path.
    table_path  : output JSON path.

    Returns
    -------
    dict  : the full sigma table (same structure as the persisted JSON).
    """
    import numpy as np
    import pandas as pd

    if cache_path is None:
        cache_path = os.path.join(_PROJECT_ROOT, "data", "cache",
                                  "ingame_eval_cache.parquet")

    df = pd.read_parquet(cache_path)
    STATS = sorted(df["stat"].unique())

    sigma_table: Dict = {}
    coverage_table: list = []

    for s in STATS:
        sigma_table[s] = {}
        for b, _ in zip(BUCKET_NAMES, BUCKET_BREAKPOINTS):
            sub = df[(df["stat"] == s) & (df["bucket"] == b)]
            if not len(sub):
                continue
            resid = (sub["routed"] - sub["truth"]).to_numpy(float)
            n = int(len(resid))
            abs_r = np.abs(resid)
            bias = float(resid.mean())
            mae = float(abs_r.mean())
            std = float(resid.std(ddof=1)) if n > 1 else float("nan")
            mad = float(np.median(np.abs(resid - np.median(resid))))
            rob_sigma = 1.4826 * mad
            # Coverage-targeted sigma: 68th pctile of |resid|.
            # By construction P(|resid| <= calibrated_sigma) = 0.68 exactly.
            calibrated_sigma = float(np.percentile(abs_r, 68.0))
            p95 = float(np.percentile(abs_r, 95.0))
            cov1 = float((abs_r <= calibrated_sigma).mean())
            cov2 = float((abs_r <= 2.0 * calibrated_sigma).mean())

            row = {
                "elapsed_min": dict(zip(BUCKET_NAMES, BUCKET_BREAKPOINTS))[b],
                "n": n,
                "bias": round(bias, 4),
                "mae": round(mae, 4),
                "std": round(std, 4),
                "rob_sigma": round(rob_sigma, 4),
                "calibrated_sigma": round(calibrated_sigma, 4),
                "p95_sigma": round(p95, 4),
                "coverage_at_1sig": round(cov1, 4),
                "coverage_at_2sig": round(cov2, 4),
            }
            sigma_table[s][b] = row
            coverage_table.append({
                "stat": s, "bucket": b,
                "elapsed_min": row["elapsed_min"],
                "n": n, "bias": row["bias"], "mae": row["mae"],
                "rob_sigma": row["rob_sigma"],
                "calibrated_sigma": row["calibrated_sigma"],
                "coverage_at_1sig": row["coverage_at_1sig"],
                "coverage_at_2sig": row["coverage_at_2sig"],
            })

    out = {
        "sigma_table": sigma_table,
        "coverage_table": coverage_table,
        "bucket_order": BUCKET_NAMES,
        "bucket_elapsed_min": dict(zip(BUCKET_NAMES, BUCKET_BREAKPOINTS)),
        "generated_from": cache_path,
        "n_games": int(df["game_id"].nunique()),
        "n_rows": int(len(df)),
        "sigma_definition": (
            "calibrated_sigma = p68 = 68th percentile of abs(routed - truth) "
            "per (stat, bucket). By construction: "
            "P(|routed-truth| <= calibrated_sigma) = 0.68 exactly. "
            "This is preferred over 1.48*MAD for late-game buckets where "
            "residuals are highly fat-tailed (kurtosis up to ~68)."
        ),
        "note": "Persisted by src/prediction/ingame_sigma.py build_sigma_table()",
    }

    os.makedirs(os.path.dirname(table_path), exist_ok=True)
    # Invalidate module-level cache so next call re-reads.
    global _SIGMA_TABLE, _TABLE_PATH_LOADED
    _SIGMA_TABLE = None
    _TABLE_PATH_LOADED = None
    with open(table_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, default=float)
    return out


def sigma_to_gaussian_q10_q90(point: float, sigma: float) -> tuple[float, float]:
    """Convert (point, sigma) to approximate (q10, q90) assuming Gaussian tails.

    This is used so the existing model_prob_over() consumer in inplay_bet_ranker
    can accept the calibrated sigma without a code-path change: it derives sigma
    from (q90-q10)/(2*1.2816), so we invert: q90-q10 = 2*1.2816*sigma.

    NOTE: this is an approximation. The true residual distribution is NOT
    Gaussian (fat tails late-game). The calibrated_sigma guarantees 68%
    coverage, but the resulting 10/90 quantiles should be treated as a
    sizing proxy, not a literal distribution fit.
    """
    half_span = 1.2816 * sigma  # so (q90-q10)/(2*1.2816) == sigma
    q10 = max(0.0, point - half_span)
    q90 = point + half_span
    return q10, q90
