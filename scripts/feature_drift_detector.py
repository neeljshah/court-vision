"""feature_drift_detector.py — R27_T3 per-feature distribution drift detector.

Compares the distribution of every production prediction feature in the
"current" window (default: last 14 days of available 2025-26 games) against
the "reference" training-era distribution (2022-23 + 2023-24 + 2024-25
combined) and reports per-feature KS statistic, p-value, and mean z-score.

Why
---
The 60-feature m2_family model and the 100+ feature prop_pergame model were
trained on a fixed historical era. As 2025-26 data accumulates, the
distribution of input features can shift (rule changes, pace, 3-pt
volume, etc.). Silent shift degrades predictions BEFORE the residuals
catch it. This detector surfaces shifts at the input layer.

Classification per feature
--------------------------
    stable        p > 0.05 AND |mean_z| < 0.5
    drift_minor   p > 0.01 AND |mean_z| < 1.0   (and not stable)
    drift_major   p < 0.01 OR  |mean_z| > 1.0

CLI
---
    python scripts/feature_drift_detector.py
    python scripts/feature_drift_detector.py --features m2
    python scripts/feature_drift_detector.py --features prop_pergame
    python scripts/feature_drift_detector.py --features all --current-days 14
    python scripts/feature_drift_detector.py --out data/cache/drift_today.json
    python scripts/feature_drift_detector.py --major-threshold 1.5

Output
------
    JSON report (always written to --out) + human-readable table on stdout.
    Report shape:
      {
        "ts": ISO8601,
        "feature_set": "m2"|"prop_pergame"|"all",
        "status": "OK"|"BLOCKED",
        "blocked_reason": "" | "...",
        "n_reference": int,
        "n_current": int,
        "current_window_days": int,
        "n_features_analyzed": int,
        "n_stable": int, "n_drift_minor": int, "n_drift_major": int,
        "features": [{name, ks_stat, p_value, mean_z, std_ratio, class}, ...]
      }
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from scipy.stats import ks_2samp  # type: ignore
    _SCIPY_OK = True
except Exception:  # noqa: BLE001
    _SCIPY_OK = False


PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

# Data root may be overridden so a worktree can read from the main repo.
_DEFAULT_DATA_ROOT = Path(os.environ.get("NBA_AI_ROOT") or PROJECT_DIR) / "data"
if not (_DEFAULT_DATA_ROOT / "nba" / "season_games_2024-25.json").exists():
    _alt = Path(r"C:\Users\neelj\nba-ai-system") / "data"
    if (_alt / "nba" / "season_games_2024-25.json").exists():
        _DEFAULT_DATA_ROOT = _alt

DEFAULT_OUT_PATH = PROJECT_DIR / "data" / "cache" / "feature_drift_latest.json"

# Training-era seasons; current = 2025-26 by default.
_REFERENCE_SEASONS = ("2022-23", "2023-24", "2024-25")
_CURRENT_SEASON = "2025-26"

# Default classification thresholds. CLI may override.
DEFAULT_STABLE_P = 0.05
DEFAULT_MINOR_P = 0.01
DEFAULT_STABLE_Z = 0.5
DEFAULT_MAJOR_Z = 1.0

# Per-feature minimum non-null sample count to bother testing.
_MIN_SAMPLES_PER_SIDE = 30

# Columns from season_games rows that are NOT features (identifiers / labels).
_M2_NON_FEATURE = {
    "game_id", "season", "game_date",
    "home_team", "away_team", "home_team_id", "away_team_id",
}

# Stat columns from per-player gamelogs that are usable for prop_pergame
# distribution drift (raw per-game stats — the inputs that ultimately become
# l5/l10/ewma form features inside prop_pergame).
_PROP_RAW_STATS = ("PTS", "REB", "AST", "MIN", "FG3M", "STL", "BLK", "TOV")


# --------------------------------------------------------------------------- #
# Loaders                                                                       #
# --------------------------------------------------------------------------- #
def _season_path(season: str, data_root: Path) -> Path:
    return data_root / "nba" / f"season_games_{season}.json"


def _load_season_rows(season: str, data_root: Path) -> List[Dict[str, Any]]:
    p = _season_path(season, data_root)
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(payload, dict) and "rows" in payload:
        return list(payload.get("rows") or [])
    if isinstance(payload, list):
        return list(payload)
    return []


def load_m2_dataframe(
    seasons: Iterable[str], data_root: Path = _DEFAULT_DATA_ROOT
) -> pd.DataFrame:
    """Load season_games rows for the given seasons into one DataFrame."""
    all_rows: List[Dict[str, Any]] = []
    for s in seasons:
        all_rows.extend(_load_season_rows(s, data_root))
    if not all_rows:
        return pd.DataFrame()
    df = pd.DataFrame(all_rows)
    if "game_date" in df.columns:
        df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce")
    return df


def load_prop_dataframe(
    seasons: Iterable[str],
    data_root: Path = _DEFAULT_DATA_ROOT,
    max_files_per_season: int = 400,
) -> pd.DataFrame:
    """Load per-player gamelog rows. This is the raw input distribution for
    prop_pergame (the per-stat counts that prop_pergame rolls into l5/l10/ewma
    form features). Capped at max_files_per_season to keep the probe cheap."""
    gl_dir = data_root / "nba"
    if not gl_dir.exists():
        return pd.DataFrame()
    frames: List[pd.DataFrame] = []
    for s in seasons:
        files = sorted(gl_dir.glob(f"gamelog_*_{s}.json"))
        if max_files_per_season and len(files) > max_files_per_season:
            files = files[:max_files_per_season]
        rows: List[Dict[str, Any]] = []
        for fp in files:
            try:
                with open(fp, "r", encoding="utf-8") as fh:
                    payload = json.load(fh)
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(payload, list):
                rows.extend(payload)
            elif isinstance(payload, dict):
                rows.extend(payload.get("rows") or [])
        if rows:
            df = pd.DataFrame(rows)
            df["_season"] = s
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True, sort=False)
    # Normalize a parsed date column if present.
    if "GAME_DATE" in out.columns:
        out["game_date"] = pd.to_datetime(out["GAME_DATE"], errors="coerce",
                                          format="%b %d, %Y")
    return out


# --------------------------------------------------------------------------- #
# Window selection                                                             #
# --------------------------------------------------------------------------- #
def select_current_window(
    df: pd.DataFrame,
    *,
    current_days: int,
    date_col: str = "game_date",
) -> pd.DataFrame:
    """Return the last `current_days` of games available in df.

    "Last N days" means: anchor is max(date) in df, return rows whose
    date >= anchor - (N-1) days. If no date column or no dates parse, returns
    the whole df (caller decides whether to treat that as a block).
    """
    if df.empty or date_col not in df.columns:
        return df
    dates = pd.to_datetime(df[date_col], errors="coerce")
    if dates.notna().sum() == 0:
        return df
    anchor = dates.max()
    cutoff = anchor - pd.Timedelta(days=int(max(current_days, 0)) - 1
                                    if current_days > 0 else 0)
    if current_days <= 0:
        # current_days=0 means "all of current season"
        return df
    mask = dates >= cutoff
    return df.loc[mask].copy()


# --------------------------------------------------------------------------- #
# Feature-set selection                                                        #
# --------------------------------------------------------------------------- #
def m2_feature_columns(df: pd.DataFrame) -> List[str]:
    """All numeric columns from season_games that aren't identifiers."""
    if df.empty:
        return []
    cols: List[str] = []
    for c in df.columns:
        if c in _M2_NON_FEATURE:
            continue
        s = df[c]
        if pd.api.types.is_numeric_dtype(s):
            cols.append(c)
    return cols


def prop_feature_columns(df: pd.DataFrame) -> List[str]:
    """The raw per-game stat columns prop_pergame consumes upstream."""
    if df.empty:
        return []
    return [c for c in _PROP_RAW_STATS if c in df.columns]


# --------------------------------------------------------------------------- #
# Per-feature test                                                             #
# --------------------------------------------------------------------------- #
def _ks_2samp_fallback(a: np.ndarray, b: np.ndarray) -> Tuple[float, float]:
    """Pure-numpy KS two-sample fallback if scipy isn't available."""
    a = np.sort(a)
    b = np.sort(b)
    n1, n2 = len(a), len(b)
    if n1 == 0 or n2 == 0:
        return float("nan"), float("nan")
    data_all = np.concatenate([a, b])
    cdf_a = np.searchsorted(a, data_all, side="right") / n1
    cdf_b = np.searchsorted(b, data_all, side="right") / n2
    d = float(np.max(np.abs(cdf_a - cdf_b)))
    # Asymptotic two-sided p-value (Kolmogorov distribution).
    en = math.sqrt(n1 * n2 / (n1 + n2))
    lam = (en + 0.12 + 0.11 / en) * d
    j = np.arange(1, 101)
    p = 2.0 * float(np.sum((-1) ** (j - 1) * np.exp(-2.0 * lam * lam * j * j)))
    p = max(0.0, min(1.0, p))
    return d, p


def _ks_test(a: np.ndarray, b: np.ndarray) -> Tuple[float, float]:
    if _SCIPY_OK:
        try:
            res = ks_2samp(a, b)
            return float(res.statistic), float(res.pvalue)
        except Exception:  # noqa: BLE001
            pass
    return _ks_2samp_fallback(a, b)


def classify(
    p_value: float,
    mean_z: float,
    *,
    stable_p: float = DEFAULT_STABLE_P,
    minor_p: float = DEFAULT_MINOR_P,
    stable_z: float = DEFAULT_STABLE_Z,
    major_z: float = DEFAULT_MAJOR_Z,
) -> str:
    """Classify a single feature's drift state."""
    abs_z = abs(mean_z) if mean_z is not None and not math.isnan(mean_z) else 0.0
    # major first (most severe)
    if (p_value is not None and not math.isnan(p_value) and p_value < minor_p) \
            or abs_z > major_z:
        return "drift_major"
    if (p_value is not None and not math.isnan(p_value) and p_value > stable_p) \
            and abs_z < stable_z:
        return "stable"
    return "drift_minor"


def compute_feature_drift(
    reference: pd.Series,
    current: pd.Series,
    *,
    stable_p: float = DEFAULT_STABLE_P,
    minor_p: float = DEFAULT_MINOR_P,
    stable_z: float = DEFAULT_STABLE_Z,
    major_z: float = DEFAULT_MAJOR_Z,
    min_samples: int = _MIN_SAMPLES_PER_SIDE,
) -> Optional[Dict[str, Any]]:
    """Return a per-feature drift record, or None if there isn't enough data."""
    ref = pd.to_numeric(reference, errors="coerce").dropna().to_numpy(dtype=float)
    cur = pd.to_numeric(current, errors="coerce").dropna().to_numpy(dtype=float)
    if len(ref) < min_samples or len(cur) < min_samples:
        return None
    ref_mean = float(np.mean(ref))
    ref_std = float(np.std(ref, ddof=1)) if len(ref) > 1 else 0.0
    cur_mean = float(np.mean(cur))
    cur_std = float(np.std(cur, ddof=1)) if len(cur) > 1 else 0.0
    mean_z = (cur_mean - ref_mean) / ref_std if ref_std > 0 else float("nan")
    std_ratio = (cur_std / ref_std) if ref_std > 0 else float("nan")
    ks_stat, p_val = _ks_test(ref, cur)
    klass = classify(
        p_val, mean_z,
        stable_p=stable_p, minor_p=minor_p,
        stable_z=stable_z, major_z=major_z,
    )
    return {
        "ks_stat":  ks_stat,
        "p_value":  p_val,
        "ref_mean": ref_mean,
        "cur_mean": cur_mean,
        "ref_std":  ref_std,
        "cur_std":  cur_std,
        "mean_z":   mean_z,
        "std_ratio": std_ratio,
        "n_ref":    int(len(ref)),
        "n_cur":    int(len(cur)),
        "class":    klass,
    }


# --------------------------------------------------------------------------- #
# Orchestration                                                                #
# --------------------------------------------------------------------------- #
def detect_drift(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    feature_cols: List[str],
    *,
    stable_p: float = DEFAULT_STABLE_P,
    minor_p: float = DEFAULT_MINOR_P,
    stable_z: float = DEFAULT_STABLE_Z,
    major_z: float = DEFAULT_MAJOR_Z,
    min_samples: int = _MIN_SAMPLES_PER_SIDE,
) -> Dict[str, Any]:
    """Compute drift per column. Returns the per-feature list + counts."""
    features: List[Dict[str, Any]] = []
    n_stable = n_minor = n_major = 0
    for col in feature_cols:
        if col not in reference.columns or col not in current.columns:
            continue
        rec = compute_feature_drift(
            reference[col], current[col],
            stable_p=stable_p, minor_p=minor_p,
            stable_z=stable_z, major_z=major_z,
            min_samples=min_samples,
        )
        if rec is None:
            continue
        rec["feature"] = col
        features.append(rec)
        klass = rec["class"]
        if klass == "stable":
            n_stable += 1
        elif klass == "drift_minor":
            n_minor += 1
        elif klass == "drift_major":
            n_major += 1
    # Sort with majors first, then by |mean_z| desc.
    _class_rank = {"drift_major": 0, "drift_minor": 1, "stable": 2}
    features.sort(key=lambda r: (
        _class_rank.get(r.get("class"), 99),
        -abs(r.get("mean_z") or 0.0),
    ))
    return {
        "n_features_analyzed": len(features),
        "n_stable":            n_stable,
        "n_drift_minor":       n_minor,
        "n_drift_major":       n_major,
        "features":            features,
    }


def run(
    *,
    feature_set: str = "m2",
    current_days: int = 14,
    data_root: Path = _DEFAULT_DATA_ROOT,
    stable_p: float = DEFAULT_STABLE_P,
    minor_p: float = DEFAULT_MINOR_P,
    stable_z: float = DEFAULT_STABLE_Z,
    major_z: float = DEFAULT_MAJOR_Z,
    min_samples: int = _MIN_SAMPLES_PER_SIDE,
    reference_df: Optional[pd.DataFrame] = None,
    current_df: Optional[pd.DataFrame] = None,
    feature_cols: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Single end-to-end drift analysis. Returns the report dict.

    Callers may inject reference_df/current_df/feature_cols for tests; when
    omitted, loads them from the on-disk season files / gamelogs.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report: Dict[str, Any] = {
        "ts":                  ts,
        "feature_set":         feature_set,
        "status":              "OK",
        "blocked_reason":      "",
        "current_window_days": int(current_days),
        "n_reference":         0,
        "n_current":           0,
        "n_features_analyzed": 0,
        "n_stable":            0,
        "n_drift_minor":       0,
        "n_drift_major":       0,
        "features":            [],
        "scipy_available":     _SCIPY_OK,
    }

    # Load if not injected.
    if reference_df is None or current_df is None or feature_cols is None:
        if feature_set == "m2":
            ref = load_m2_dataframe(_REFERENCE_SEASONS, data_root)
            cur_all = load_m2_dataframe((_CURRENT_SEASON,), data_root)
            cur = select_current_window(cur_all, current_days=current_days)
            cols = m2_feature_columns(ref)
        elif feature_set == "prop_pergame":
            ref = load_prop_dataframe(_REFERENCE_SEASONS, data_root)
            cur_all = load_prop_dataframe((_CURRENT_SEASON,), data_root)
            cur = select_current_window(cur_all, current_days=current_days)
            cols = prop_feature_columns(ref)
        elif feature_set == "all":
            ref_m2 = load_m2_dataframe(_REFERENCE_SEASONS, data_root)
            cur_m2 = select_current_window(
                load_m2_dataframe((_CURRENT_SEASON,), data_root),
                current_days=current_days,
            )
            ref_pp = load_prop_dataframe(_REFERENCE_SEASONS, data_root)
            cur_pp = select_current_window(
                load_prop_dataframe((_CURRENT_SEASON,), data_root),
                current_days=current_days,
            )
            # Stitch into a single record with side-tagged columns to avoid
            # column-name collisions (PTS vs home_off_rtg etc are disjoint).
            ref = pd.concat([ref_m2, ref_pp], axis=0, ignore_index=True,
                            sort=False)
            cur = pd.concat([cur_m2, cur_pp], axis=0, ignore_index=True,
                            sort=False)
            cols = list(dict.fromkeys(
                m2_feature_columns(ref_m2) + prop_feature_columns(ref_pp)
            ))
        else:
            report["status"] = "BLOCKED"
            report["blocked_reason"] = f"unknown feature_set: {feature_set}"
            return report
        reference_df, current_df, feature_cols = ref, cur, cols

    report["n_reference"] = int(len(reference_df))
    report["n_current"] = int(len(current_df))

    if reference_df.empty or len(reference_df) < min_samples:
        report["status"] = "BLOCKED"
        report["blocked_reason"] = (
            f"insufficient reference data (rows={len(reference_df)})"
        )
        return report
    if current_df.empty or len(current_df) < min_samples:
        report["status"] = "BLOCKED"
        report["blocked_reason"] = (
            f"insufficient current window data (rows={len(current_df)})"
        )
        return report
    if not feature_cols:
        report["status"] = "BLOCKED"
        report["blocked_reason"] = "no feature columns resolved"
        return report

    res = detect_drift(
        reference_df, current_df, feature_cols,
        stable_p=stable_p, minor_p=minor_p,
        stable_z=stable_z, major_z=major_z,
        min_samples=min_samples,
    )
    report.update({
        "n_features_analyzed": res["n_features_analyzed"],
        "n_stable":            res["n_stable"],
        "n_drift_minor":       res["n_drift_minor"],
        "n_drift_major":       res["n_drift_major"],
        "features":            res["features"],
    })
    if res["n_features_analyzed"] == 0:
        report["status"] = "BLOCKED"
        report["blocked_reason"] = "no per-feature sample sizes met threshold"
    return report


# --------------------------------------------------------------------------- #
# Pretty-printer                                                               #
# --------------------------------------------------------------------------- #
def format_report_table(report: Dict[str, Any], *, top: int = 20) -> str:
    """Compact human-readable summary."""
    lines: List[str] = []
    lines.append(f"Feature Drift — {report.get('feature_set','?')} "
                 f"({report.get('ts','')})")
    if report.get("status") != "OK":
        lines.append(f"  STATUS: {report.get('status')}  "
                     f"reason: {report.get('blocked_reason','')}")
    lines.append(
        f"  n_ref={report.get('n_reference',0)} "
        f"n_cur={report.get('n_current',0)} "
        f"window={report.get('current_window_days',0)}d  "
        f"analyzed={report.get('n_features_analyzed',0)}"
    )
    lines.append(
        f"  stable={report.get('n_stable',0)}  "
        f"minor={report.get('n_drift_minor',0)}  "
        f"MAJOR={report.get('n_drift_major',0)}"
    )
    feats = report.get("features") or []
    if feats:
        lines.append("")
        lines.append(f"  {'feature':<32} {'class':<12} "
                     f"{'ks':>6} {'p':>9} {'mean_z':>8}")
        for r in feats[: max(0, int(top))]:
            lines.append(
                f"  {str(r.get('feature',''))[:32]:<32} "
                f"{str(r.get('class','')):<12} "
                f"{float(r.get('ks_stat') or 0.0):>6.3f} "
                f"{float(r.get('p_value') or 0.0):>9.3e} "
                f"{float(r.get('mean_z') or 0.0):>+8.2f}"
            )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="R27_T3 feature drift detector — reference vs current "
                    "distribution per production feature."
    )
    ap.add_argument("--features", choices=("m2", "prop_pergame", "all"),
                    default="m2",
                    help="Which feature set to analyze (default: m2).")
    ap.add_argument("--current-days", type=int, default=14,
                    help="Window size in days for current data "
                         "(0 = all of current season).")
    ap.add_argument("--out", type=str, default=str(DEFAULT_OUT_PATH),
                    help="Output JSON path.")
    ap.add_argument("--data-root", type=str,
                    default=str(_DEFAULT_DATA_ROOT),
                    help="Override the data root (handy for worktrees).")
    ap.add_argument("--major-threshold", type=float, default=DEFAULT_MAJOR_Z,
                    help="|mean_z| above this is drift_major "
                         "(default: 1.0).")
    ap.add_argument("--stable-z", type=float, default=DEFAULT_STABLE_Z,
                    help="|mean_z| below this is stable when p>stable_p "
                         "(default: 0.5).")
    ap.add_argument("--stable-p", type=float, default=DEFAULT_STABLE_P,
                    help="p-value above this is stable (default: 0.05).")
    ap.add_argument("--minor-p", type=float, default=DEFAULT_MINOR_P,
                    help="p-value below this is drift_major (default: 0.01).")
    ap.add_argument("--min-samples", type=int, default=_MIN_SAMPLES_PER_SIDE,
                    help="Per-feature non-null sample minimum (default: 30).")
    ap.add_argument("--top", type=int, default=20,
                    help="Top-N features to print in the table.")
    ap.add_argument("--quiet", action="store_true",
                    help="Suppress the human-readable table.")
    return ap.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    report = run(
        feature_set=args.features,
        current_days=args.current_days,
        data_root=Path(args.data_root),
        stable_p=args.stable_p,
        minor_p=args.minor_p,
        stable_z=args.stable_z,
        major_z=args.major_threshold,
        min_samples=args.min_samples,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    if not args.quiet:
        print(format_report_table(report, top=args.top))
        print(f"\nReport written to {out_path}")
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
