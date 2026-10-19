"""scripts.platformkit.eval_gate.conformal_coverage_core -- S687 pure helpers (no crepes).

Constants, the per-sport out-of-time split, the in-house order-statistic reference for split
conformal, and the coverage verdict. The crepes side lives in conformal_coverage_audit.py.

What the audit measures: split conformal coverage is >= NOMINAL under exchangeability whatever
the base model's quality, so a sport that misses the bar on a later out-of-time block shows
calibration-to-test DRIFT (non-exchangeability over time), not a miscalibrated `pred` as such.
Calibration language only. ASCII only.
Test: python -m pytest tests/platformkit/eval_gate/test_conformal_coverage_audit.py -q
"""
from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

# Sealed constants (spec S687_spec_2026-09-30.md; never tuned on any window, never moved).
NOMINAL = 0.90          # nominal coverage of the prediction set / interval
NOMINAL_NUM, NOMINAL_DEN = 9, 10   # NOMINAL as an exact rational for integer rank arithmetic
TOL = 0.03              # the slate's bar: |coverage - NOMINAL| <= 3 points
TOL_PCT = 3             # TOL in integer percentage points
NOMINAL_PCT = 90
MIN_N = 300             # per side; below this the sport is INSUFFICIENT (missing != bad)
CALIB_FRAC = 0.5        # share of unique dates on the calibration side
EMBARGO_DAYS = 1        # gap between the last calibration date and the first test date
DEGENERATE_FULL_SHARE = 0.5   # binary: full {0,1} sets above this share -> diagnostic only

INSUFFICIENT, WITHIN = "INSUFFICIENT", "WITHIN"
FLAGGED_UNDER, FLAGGED_OVER = "FLAGGED_UNDER", "FLAGGED_OVER"
VERDICTS = (INSUFFICIENT, WITHIN, FLAGGED_UNDER, FLAGGED_OVER)

ASSUMPTION = ("input rows are walk-forward out-of-sample predictions on BOTH sides of the cut; "
              "otherwise calibration scores are self-fit (contract B8)")
REPO_ROOT = Path(__file__).resolve().parents[3]


def ref_rank(n: int) -> int:
    """1-based rank k = ceil((n+1)*NOMINAL) of the calibration score used as the radius."""
    return -(-(NOMINAL_NUM * (n + 1)) // NOMINAL_DEN)


def ref_radius(scores: np.ndarray) -> float:
    """In-house split conformal radius: the k-th smallest score (inf when k > n)."""
    s = np.sort(np.asarray(scores, dtype=float))
    k = ref_rank(len(s))
    return float(s[k - 1]) if k <= len(s) else math.inf


def ref_keep(cal_scores_sorted: np.ndarray, test_scores: np.ndarray) -> np.ndarray:
    """Classifier reference: keep a label iff 10*(c+1) >= n+1, c = #{cal >= a} (the >= tie rule)."""
    n = len(cal_scores_sorted)
    below = np.searchsorted(cal_scores_sorted, test_scores, side="left")
    c = n - below
    return NOMINAL_DEN * (c + 1) >= (NOMINAL_DEN - NOMINAL_NUM) * (n + 1)


def verdict(covered: int, n_test: int, n_cal: int) -> str:
    """Coverage verdict in exact integer arithmetic: WITHIN iff |100*cov - 90*n| <= 3*n."""
    if n_cal < MIN_N or n_test < MIN_N:
        return INSUFFICIENT
    diff = 100 * covered - NOMINAL_PCT * n_test
    if abs(diff) <= TOL_PCT * n_test:
        return WITHIN
    return FLAGGED_UNDER if diff < 0 else FLAGGED_OVER


def null_flag_rate_approx(n_cal: int, n_test: int) -> Optional[float]:
    """Approximate chance an exchangeable sport is flagged by sampling alone (normal approx)."""
    if n_cal <= 0 or n_test <= 0:
        return None
    var = NOMINAL * (1 - NOMINAL)
    sd = math.sqrt(var / n_cal + var / n_test)
    return float(math.erfc((TOL / sd) / math.sqrt(2.0)))


def wilson95(covered: int, n: int) -> Optional[Tuple[float, float]]:
    """Wilson 95 pct interval for the test-side coverage (diagnostic)."""
    if n <= 0:
        return None
    z, p = 1.959963984540054, covered / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (round(mid - half, 9), round(mid + half, 9))


def clean_common(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """Drop rows unusable for either task kind, recording every exclusion."""
    reasons: Dict[str, int] = {}
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce", utc=True,
                               format="mixed").dt.tz_localize(None)
    for col in ("y", "pred"):
        d[col] = pd.to_numeric(d[col], errors="coerce")
    bad = d["date"].isna() | d["y"].isna() | d["pred"].isna()
    bad |= ~np.isfinite(d["y"].fillna(0.0)) | ~np.isfinite(d["pred"].fillna(0.0))
    if int(bad.sum()):
        reasons["missing_or_nonfinite"] = int(bad.sum())
    d = d[~bad]
    return d, reasons


def freeze_temporal_partition(df: pd.DataFrame) -> Tuple[Optional[pd.Timestamp], set[str]]:
    """Freeze the date cut and cross-cut game identities before outcome-specific cleaning."""
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce", utc=True,
                               format="mixed").dt.tz_localize(None)
    d = d[d["date"].notna()]
    last_cal = temporal_cut(d)
    if last_cal is None or "game_id" not in d.columns:
        return last_cal, set()
    valid = d["game_id"].notna()
    game = d["game_id"].astype(str)
    cal_mask = d["date"].dt.normalize() <= last_cal
    return last_cal, set(game[cal_mask & valid]) & set(game[~cal_mask & valid])


def clean(df: pd.DataFrame, kind: str) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """Drop unusable rows, returning the kept rows and a per-reason exclusion count (B1)."""
    d, reasons = clean_common(df)
    if kind == "binary":
        bad_y = ~d["y"].isin([0, 1])
        bad_p = (d["pred"] < 0) | (d["pred"] > 1)
        if int(bad_y.sum()):
            reasons["y_not_binary"] = int(bad_y.sum())
        if int((bad_p & ~bad_y).sum()):
            reasons["pred_outside_0_1"] = int((bad_p & ~bad_y).sum())
        d = d[~(bad_y | bad_p)]
    return d, reasons


def detect_kind(df: pd.DataFrame) -> str:
    """auto: binary iff every supplied, already-cleaned y is 0 or 1."""
    y = pd.to_numeric(df["y"], errors="coerce").dropna()
    return "binary" if len(y) and bool(y.isin([0, 1]).all()) else "regression"


def refuse_registry_output(out: Path) -> None:
    """Refuse lexical and resolved destinations under the protected registry."""
    candidate = Path(out)
    lexical = tuple(part.rstrip(" .").lower() for part in candidate.parts)
    if any(lexical[i:i + 2] == ("data", "registry") for i in range(len(lexical) - 1)):
        raise SystemExit("refused: output under data/registry")
    registry = (REPO_ROOT / "data" / "registry").resolve()
    registry_parts = tuple(part.rstrip(" .").casefold() for part in registry.parts)
    for path in (candidate.absolute(), candidate.resolve()):
        collapsed = Path(os.path.normpath(path))
        parts = tuple(part.rstrip(" .").casefold() for part in collapsed.parts)
        if parts[:len(registry_parts)] == registry_parts:
            raise SystemExit("refused: output under data/registry")


def temporal_cut(d: pd.DataFrame) -> Optional[pd.Timestamp]:
    """Return the sealed calibration-end date from common-cleaned rows."""
    dates = np.array(sorted(d["date"].dt.normalize().unique()))
    n_cal_dates = int(math.floor(CALIB_FRAC * len(dates)))
    if n_cal_dates < 1 or len(dates) < 2:
        return None
    return pd.Timestamp(dates[n_cal_dates - 1])


def split_out_of_time(d: pd.DataFrame, frozen_last_cal_date: Optional[pd.Timestamp] = None,
                      frozen_spanning_game_ids: Optional[set[str]] = None
                      ) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """Per-sport out-of-time split with purge and embargo; optionally retain a prior cut."""
    dates = np.array(sorted(d["date"].dt.normalize().unique()))
    info: Dict[str, Any] = {"n_dates": int(len(dates)), "n_embargoed": 0, "n_purged": 0,
                            "last_cal_date": None, "first_test_date": None}
    if frozen_last_cal_date is None:
        last_cal = temporal_cut(d)
        if last_cal is None:
            return d.iloc[0:0], d.iloc[0:0], info
    else:
        last_cal = pd.Timestamp(frozen_last_cal_date).normalize()
    day = d["date"].dt.normalize()
    gap_end = last_cal + pd.Timedelta(days=EMBARGO_DAYS)
    cal_mask, test_mask = day <= last_cal, day > gap_end
    info["n_embargoed"] = int((~cal_mask & ~test_mask).sum())
    if "game_id" in d.columns:
        valid = d["game_id"].notna()
        g = d["game_id"].astype(str)
        span = frozen_spanning_game_ids
        if span is None:
            span = set(g[cal_mask & valid]) & set(g[~cal_mask & valid])
        purge = valid & g.isin(span)
        info["n_purged"] = int(purge.sum())
        cal_mask, test_mask = cal_mask & ~purge, test_mask & ~purge
    cal, test = d[cal_mask], d[test_mask]
    if len(cal) and len(test):
        assert cal["date"].dt.normalize().max() + pd.Timedelta(days=EMBARGO_DAYS) \
            < test["date"].dt.normalize().min(), "embargo violated"
        if "game_id" in d.columns:
            assert not (set(cal.loc[cal["game_id"].notna(), "game_id"].astype(str)) &
                        set(test.loc[test["game_id"].notna(), "game_id"].astype(str))), \
                "purge violated"
        info["last_cal_date"] = str(cal["date"].max().date())
        info["first_test_date"] = str(test["date"].min().date())
    return cal, test, info


def binary_scores(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Hinge nonconformity 1 - P(label) for the realised label."""
    return np.where(y == 1, 1.0 - p, p)


def binary_score_matrix(p: np.ndarray) -> np.ndarray:
    """Test-side score matrix, column k = score of label k (k = 0, 1)."""
    return np.column_stack([p, 1.0 - p])
