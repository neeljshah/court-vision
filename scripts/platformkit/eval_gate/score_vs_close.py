"""Score one pregame row per match against an already devigged close.

--devig asserts the CSV method; it never transforms probabilities. Validation
counts overlap: duplicated_match_id counts repeats after the first occurrence,
and other row reasons count affected rows. A zero-Brier forecaster marks all
rows as leak_signature, as does any row with |p_model - y| <= 1e-3. Nothing is
silently excluded. Scores use the reference 1e-6 clip after validation. Reliability bins sort by probability, then match_id,
and split into ten groups whose counts differ by at most one.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np

from scripts.platformkit.eval_gate.dm_test import diebold_mariano

COLUMNS = ["date_utc", "match_id", "p_model", "p_close_devig", "devig_method", "y"]
METHODS = ("proportional", "shin")
MIN_ROWS = 500
EPS = 1e-6
NOTE = "calibration readout, paper only, not a verdict"
SIGN = "positive = model trails the close; dm_stat has the same sign as gap"
LEAK_TOL = 1e-3  # |p_model - y| at or below this is a near-certain outcome leak


def _number(value: object) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return float("nan")


def _refusal(n: int, reasons: dict[str, int]) -> dict:
    return {"schema": "score_vs_close/v1", "status": "REFUSED", "n": n,
            "verdict": "INSUFFICIENT" if n < MIN_ROWS else None,
            "reasons": reasons, "gap_sign": SIGN, "note": NOTE}


def _bins(p: np.ndarray, y: np.ndarray, ids: list[str]) -> list[dict]:
    order = np.lexsort((np.asarray(ids), p))
    return [{"mean_p": float(p[b].mean()), "observed_rate": float(y[b].mean()),
             "count": int(len(b))} for b in np.array_split(order, 10)]


def _log_loss(p: np.ndarray, y: np.ndarray) -> float:
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log1p(-p)))


def score_rows(rows: list[dict], devig: str | None = None) -> dict:
    """Validate all rows, then return paired calibration metrics or a refusal."""
    n = len(rows)
    reasons: dict[str, int] = {}
    ids = [str(r.get("match_id") or "").strip() for r in rows]
    methods = [r.get("devig_method") for r in rows]
    pm = np.array([_number(r.get("p_model")) for r in rows])
    pc = np.array([_number(r.get("p_close_devig")) for r in rows])
    y = np.array([_number(r.get("y")) for r in rows])
    duplicate_count = sum(c - 1 for c in Counter(ids).values())
    if duplicate_count:
        reasons["duplicated_match_id"] = duplicate_count
    bad_identity = sum(not k or not str(r.get("date_utc") or "").strip()
                       for k, r in zip(ids, rows))
    if bad_identity:
        reasons["missing_identity"] = bad_identity
    valid_p = (np.isfinite(pm) & np.isfinite(pc) & (pm > 0) & (pm < 1)
               & (pc > 0) & (pc < 1))
    if not valid_p.all():
        reasons["p_outside_open_interval"] = int((~valid_p).sum())
    valid_y = np.isin(y, [0.0, 1.0])
    if not valid_y.all():
        reasons["y_not_binary"] = int((~valid_y).sum())
    with np.errstate(invalid="ignore"):
        leak = valid_y & (np.abs(pm - y) <= LEAK_TOL)
    if n and valid_y.all():
        with np.errstate(over="ignore", invalid="ignore"):
            if np.mean((pm - y) ** 2) == 0 or np.mean((pc - y) ** 2) == 0:
                leak[:] = True
    if leak.any():
        reasons["leak_signature"] = int(leak.sum())
    if len(set(methods)) > 1:
        reasons["mixed_devig_method"] = n
    invalid_method = sum(m not in METHODS for m in methods)
    if invalid_method:
        reasons["invalid_devig_method"] = invalid_method
    if devig is not None:
        mismatch = sum(m != devig for m in methods)
        if mismatch:
            reasons["devig_method_mismatch"] = mismatch
    if n < MIN_ROWS:
        reasons["below_floor"] = n  # observed rows, including zero
    if reasons:
        return _refusal(n, reasons)
    pm, pc = np.clip(pm, EPS, 1 - EPS), np.clip(pc, EPS, 1 - EPS)
    lm, lc = (pm - y) ** 2, (pc - y) ** 2
    dm = diebold_mariano(lm - lc, ids)
    lo, hi = dm.ci95
    verdict = "MATCHES_CLOSE" if lo <= 0 <= hi else (
        "TRAILS_CLOSE" if lo > 0 else "BEATS_CLOSE")
    return {
        "schema": "score_vs_close/v1", "status": "OK", "n": n,
        "n_clusters": dm.n_clusters, "devig_method": methods[0],
        "model_brier": float(lm.mean()), "close_brier": float(lc.mean()),
        "gap": dm.mean_diff, "gap_sign": SIGN, "ci95": [float(lo), float(hi)],
        "dm_stat": dm.dm_stat, "dm_p": dm.p_value,
        "mde": 1.429 * (hi - lo) / 2, "mde_power": 0.8,
        "model_log_loss": _log_loss(pm, y), "close_log_loss": _log_loss(pc, y),
        "reliability": {"model": _bins(pm, y, ids), "close": _bins(pc, y, ids)},
        "verdict": verdict, "reasons": {}, "note": NOTE,
    }


def score_csv(path: Path, devig: str | None = None) -> dict:
    """Read the exact six-column CSV; return counted input failures as refusals."""
    try:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream, strict=True)
            if reader.fieldnames != COLUMNS:
                return _refusal(0, {"invalid_columns": 1})
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error):
        return _refusal(0, {"unreadable_csv": 1})
    malformed = sum(None in r or any(v is None for v in r.values()) for r in rows)
    if malformed:
        return _refusal(len(rows), {"malformed_row": malformed})
    return score_rows(rows, devig)


def main(argv: list[str] | None = None) -> int:
    """Print JSON and optionally save the identical JSON; refusals exit 3."""
    parser = argparse.ArgumentParser(description=__doc__, epilog=NOTE)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--devig", choices=METHODS,
                        help="assert the method already used in the CSV")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args(argv)
    result = score_csv(args.csv, args.devig)
    payload = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.json_out:
        try:
            args.json_out.write_text(payload, encoding="ascii")
        except OSError:
            result = _refusal(result["n"], {"json_write_failed": 1})
            payload = json.dumps(result, indent=2) + "\n"
    print(payload, end="")
    return 3 if result["status"] == "REFUSED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
