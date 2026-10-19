"""scripts.platformkit.eval_gate.conformal_coverage_audit -- S687 per-sport conformal coverage audit.

Report-only SCREEN over walk-forward predictions (columns sport, date, y, pred, optional game_id).
Per sport: an out-of-time split (conformal_coverage_core.split_out_of_time), then crepes split
conformal at NOMINAL 0.90 -- binary: ConformalClassifier on 1 - P(label), non-smoothed p-values,
set coverage; regression: ConformalRegressor on |y - pred|, interval coverage. An in-house
order-statistic reference is computed beside crepes and must agree (spec AMENDMENT 1 items 1-2).
Verdict = crepes coverage against the sealed bar; width / set size are diagnostics only.

Under exchangeability split conformal covers >= NOMINAL whatever the model, so a flag here means
calibration-to-test drift over time, not that `pred` is miscalibrated. No prereg seal, no ledger
charge, no K read: a SCREEN is a non-finding. SINGLE-WINDOW. Calibration language only.
crepes (BSD-3-Clause) is a DEV-ONLY dependency pinned in requirements-dev-conformal.txt and is
imported lazily, so importing this module never needs it. ASCII only.
Usage: python -m scripts.platformkit.eval_gate.conformal_coverage_audit --input P --out J
Test: python -m pytest tests/platformkit/eval_gate/test_conformal_coverage_audit.py -q
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate import conformal_coverage_core as core
from scripts.platformkit.ops.atomic_replace import replace_with_retry

DEV_REQUIREMENTS = "requirements-dev-conformal.txt"
def _crepes():
    try:
        import crepes  # noqa: F401  (dev-only, lazy)
        from crepes import ConformalClassifier, ConformalRegressor
    except ImportError as exc:  # pragma: no cover - exercised via sys.modules patch
        raise RuntimeError("S687 needs the dev-only dependency crepes; install it with "
                           "`pip install -r %s`" % DEV_REQUIREMENTS) from exc
    return crepes, ConformalClassifier, ConformalRegressor


def _binary(cal: pd.DataFrame, test: pd.DataFrame) -> Dict[str, Any]:
    _, ConformalClassifier, _ = _crepes()
    cal_scores = core.binary_scores(cal["pred"].to_numpy(float), cal["y"].to_numpy(int))
    p_t, y_t = test["pred"].to_numpy(float), test["y"].to_numpy(int)
    mat = core.binary_score_matrix(p_t)
    cc = ConformalClassifier().fit(cal_scores)
    sets = np.asarray(cc.predict_set(mat, confidence=core.NOMINAL, smoothing=False), dtype=int)
    srt = np.sort(cal_scores)
    ref = np.column_stack([core.ref_keep(srt, mat[:, 0]), core.ref_keep(srt, mat[:, 1])]).astype(int)
    idx = np.arange(len(y_t))
    covered = int(sets[idx, y_t].sum())
    size = sets.sum(axis=1)
    n = max(len(y_t), 1)
    full = float((size == 2).sum() / n)
    return {"covered": covered, "covered_reference": int(ref[idx, y_t].sum()),
            "reference_agrees": bool(np.array_equal(sets, ref)), "crepes_offbyone": 0,
            "share_full_sets": round(full, 9),
            "share_singleton_sets": round(float((size == 1).sum() / n), 9),
            "share_empty_sets": round(float((size == 0).sum() / n), 9),
            "mean_set_size": round(float(size.mean()) if len(size) else 0.0, 9),
            "degenerate_full_sets": bool(full > core.DEGENERATE_FULL_SHARE)}


def _regression(cal: pd.DataFrame, test: pd.DataFrame) -> Dict[str, Any]:
    _, _, ConformalRegressor = _crepes()
    res = cal["y"].to_numpy(float) - cal["pred"].to_numpy(float)
    yh, y_t = test["pred"].to_numpy(float), test["y"].to_numpy(float)
    cr = ConformalRegressor().fit(res)
    iv = np.asarray(cr.predict_int(yh, confidence=core.NOMINAL), dtype=float)
    radius = float(np.asarray(cr.predict_int(np.zeros(1), confidence=core.NOMINAL))[0, 1])
    scores = np.sort(np.abs(res))
    ref = core.ref_radius(scores)
    k = core.ref_rank(len(scores))
    offbyone = 0
    if radius == ref:
        agrees = True
    elif k < len(scores) and radius == float(scores[k]):   # the (k+1)-th smallest score
        agrees, offbyone = True, 1
    else:
        agrees = False
    covered = int(((y_t >= iv[:, 0]) & (y_t <= iv[:, 1])).sum())
    return {"covered": covered, "covered_reference": int((np.abs(y_t - yh) <= ref).sum()),
            "reference_agrees": agrees, "crepes_offbyone": offbyone,
            "radius_crepes": radius, "radius_reference": ref,
            "mean_interval_width": round(2.0 * radius, 9) if np.isfinite(radius) else None}


def audit_sport(df: pd.DataFrame, kind: str = "auto") -> Dict[str, Any]:
    """Audit one sport's rows; returns the per-sport report row."""
    frozen_last_cal_date, frozen_spanning_game_ids = core.freeze_temporal_partition(df)
    common, _ = core.clean_common(df)
    calibration_side, _, _ = core.split_out_of_time(
        common, frozen_last_cal_date, frozen_spanning_game_ids)
    k = core.detect_kind(calibration_side) if kind == "auto" else kind
    if k not in ("binary", "regression"):
        raise ValueError("kind must be auto, binary or regression")
    d, reasons = core.clean(df, k)
    cal, test, info = core.split_out_of_time(d, frozen_last_cal_date, frozen_spanning_game_ids)
    n_cal, n_test = int(len(cal)), int(len(test))
    row: Dict[str, Any] = {"kind": k, "n_input": int(len(df)), "n_kept": int(len(d)),
                           "n_excluded": int(sum(reasons.values())), "excluded_reasons": reasons,
                           "n_cal": n_cal, "n_test": n_test, **info}
    if n_cal == 0 or n_test == 0:
        row.update({"verdict": core.INSUFFICIENT, "coverage": None})
        return row
    detail = _binary(cal, test) if k == "binary" else _regression(cal, test)
    if not detail["reference_agrees"]:
        raise ValueError("refused: crepes and reference disagree")
    row.update(detail)
    row["coverage"] = round(detail["covered"] / n_test, 9)
    row["coverage_reference"] = round(detail["covered_reference"] / n_test, 9)
    row["coverage_wilson95"] = core.wilson95(detail["covered"], n_test)
    row["null_flag_rate_approx"] = core.null_flag_rate_approx(n_cal, n_test)
    row["verdict"] = core.verdict(detail["covered"], n_test, n_cal)
    return row


def audit_frame(df: pd.DataFrame, kind: str = "auto") -> Dict[str, Any]:
    """Audit every sport in a walk-forward prediction table."""
    missing = [c for c in ("sport", "date", "y", "pred") if c not in df.columns]
    if missing:
        raise ValueError("input lacks columns: %s" % ",".join(missing))
    named = df[df["sport"].notna()].copy()
    named["sport"] = named["sport"].astype(str)
    rows = {s: audit_sport(group, kind) for s, group in named.groupby("sport", sort=True)}
    crepes, _, _ = _crepes()
    return {"row": "S687", "screen": True, "single_window": True,
            "nominal": core.NOMINAL, "tol": core.TOL, "min_n": core.MIN_N,
            "calib_frac": core.CALIB_FRAC, "embargo_days": core.EMBARGO_DAYS,
            "assumption": core.ASSUMPTION, "crepes_version": getattr(crepes, "__version__", None),
            "n_rows_without_sport": int(df["sport"].isna().sum()),
            "sports": rows,
            "flagged": sorted(s for s, r in rows.items() if r["verdict"].startswith("FLAGGED"))}


def file_identity(path: Path) -> Dict[str, Any]:
    """A9: path as given, byte size, sha256."""
    data = Path(path).read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def load_table(path: Path) -> pd.DataFrame:
    p = Path(path)
    return pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p)


def write_report(path: Path, report: Dict[str, Any]) -> None:
    """Write a report through a sibling temporary file, then atomically replace it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent) as temporary_dir:
        temporary = Path(temporary_dir) / path.name
        temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
        replace_with_retry(temporary, path)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="S687 per-sport conformal coverage audit (screen)")
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--kind", default="auto", choices=("auto", "binary", "regression"))
    a = ap.parse_args(argv)
    core.refuse_registry_output(a.out)
    report = audit_frame(load_table(a.input), a.kind)
    report["input"] = file_identity(a.input)
    write_report(a.out, report)
    for s, r in report["sports"].items():
        print("%s kind=%s n_cal=%d n_test=%d coverage=%s verdict=%s" % (
            s, r["kind"], r["n_cal"], r["n_test"], r["coverage"], r["verdict"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
