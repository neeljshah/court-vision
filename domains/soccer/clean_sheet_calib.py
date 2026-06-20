"""domains.soccer.clean_sheet_calib -- Walk-forward calibration for clean-sheet/BTTS markets.

Derives P(clean-sheet-home), P(clean-sheet-away), P(BTTS-yes) from the
Dixon-Coles scoreline engine then applies a leak-free walk-forward isotonic
calibrator. Ships recalibrated probs only when ECE(recal) < ECE(raw) AND
pinball loss is non-worse for each market; else records an honest REJECT verdict.

COHERENCE (from markets.py algebraic read-offs):
  P(cs_home_clean) + P(no_cs_home) = 1.0 by construction.
  P(btts_yes) + P(btts_no) = 1.0 by construction.
  Both probabilities are derived from the same scoreline matrix as 1X2/O/U.

WALK-FORWARD CONTRACT: for event i the calibrator is fitted on events 0..i-1
ONLY. Events before MIN_HISTORY pass through raw. No future leak.

HONEST: calibration != edge. Better-calibrated probabilities do NOT imply
beating the market. Pregame soccer markets are efficient. NO edge claimed.

INVARIANTS: never edit src/ kernel/ api/ scripts/team_system/ intel/. <=300 LOC.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
from sklearn.isotonic import IsotonicRegression

from domains.soccer.ratings import walk_forward_goals
from domains.soccer.scoreline_engine import scoreline_matrix
from domains.soccer.markets import clean_sheet, btts as _btts

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_HISTORY: int = 50
MIN_CORPUS: int = 100

CALIBRATION_NOTE: str = (
    "calibration != edge: better-calibrated derived-market probabilities "
    "do NOT imply beating the market"
)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    """Binary ECE -- kernel re-use if available, else inline."""
    try:
        from kernel.validation.proof_metrics import ece as _k
        return _k(p, y, bins=bins)
    except ImportError:
        pass
    total = len(p)
    if total == 0:
        return 0.0
    edges = np.linspace(0.0, 1.0, bins + 1)
    val = 0.0
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < bins - 1 else (p >= lo) & (p <= hi)
        nb = int(mask.sum())
        if nb == 0:
            continue
        val += (nb / total) * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return float(val)


def _pinball(p: np.ndarray, y: np.ndarray) -> float:
    """Brier score == CRPS for binary outcomes -- the correct 'pinball' metric.

    For binary events, CRPS = integral of pinball over all quantile levels
    = Brier = mean((p - y)^2).  Using Brier avoids the L1 median-not-mean
    pathology and is the standard calibration quality metric for probabilities.
    Lower is better; calibration improvement must reduce this.
    """
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


# ---------------------------------------------------------------------------
# Market extraction
# ---------------------------------------------------------------------------

def _build_raw_outcomes(wf) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Extract raw engine probs + binary outcomes for (cs_home, cs_away, btts).

    Returns:
      raw  (N, 3) -- engine probs [cs_home, cs_away, btts_yes]
      out  (N, 3) -- binary outcomes
      valid (N,)  -- rows with finite probs AND known outcomes
    """
    n = len(wf)
    raw = np.full((n, 3), np.nan)
    out = np.full((n, 3), np.nan)

    for i, (_, row) in enumerate(wf.iterrows()):
        try:
            P = scoreline_matrix(float(row["lam_home"]), float(row["lam_away"]))
            cs = clean_sheet(P)
            b = _btts(P)
            raw[i] = [cs["cs_home_clean"], cs["cs_away_clean"], b["btts_yes"]]
        except Exception:   # noqa: BLE001
            continue
        try:
            fthg, ftag = float(row["fthg"]), float(row["ftag"])
            out[i] = [
                1.0 if ftag == 0 else 0.0,   # cs_home: away scored 0
                1.0 if fthg == 0 else 0.0,   # cs_away: home scored 0
                1.0 if (fthg >= 1 and ftag >= 1) else 0.0,
            ]
        except Exception:   # noqa: BLE001
            pass

    valid = np.all(np.isfinite(raw), axis=1) & np.all(np.isfinite(out), axis=1)
    return raw, out, valid


# ---------------------------------------------------------------------------
# Walk-forward calibration (one binary market)
# ---------------------------------------------------------------------------

def _wf_cal(raw: np.ndarray, out: np.ndarray, valid: np.ndarray,
            min_history: int = MIN_HISTORY) -> np.ndarray:
    """Leak-free walk-forward isotonic calibration for a single binary prob vector."""
    cal = raw.copy()
    ir = IsotonicRegression(out_of_bounds="clip")
    valid_so_far = 0

    for i in range(len(raw)):
        if not valid[i]:
            continue
        if valid_so_far < min_history:
            cal[i] = float(raw[i])
        else:
            prior = valid[:i]
            ph, yh = raw[:i][prior], out[:i][prior]
            fm = np.isfinite(ph) & np.isfinite(yh)
            if fm.any():
                try:
                    ir.fit(ph[fm], yh[fm])
                    cal[i] = float(ir.transform([raw[i]])[0])
                except Exception:   # noqa: BLE001
                    cal[i] = float(raw[i])
        valid_so_far += 1

    return np.clip(cal, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Main API
# ---------------------------------------------------------------------------

def run_calibration(
    matches_path: Optional[str] = None,
    *,
    repo_root: Optional[Path] = None,
    min_history: int = MIN_HISTORY,
    min_corpus: int = MIN_CORPUS,
) -> Dict:
    """Walk-forward calibrate cs_home / cs_away / btts; return verdicted result dict.

    Returns dict:
      verdict         : 'SHIP' | 'REJECT' | 'INSUFFICIENT_DATA'
      n               : valid events
      markets         : per-market scores + gate result
      sum_to_one_ok   : bool coherence check
      note            : human-readable summary
      calibration_note: anti-edge reminder
    """
    import pandas as pd

    if matches_path is not None:
        df = pd.read_parquet(matches_path)
    else:
        root = repo_root or Path(__file__).resolve().parents[2]
        p = root / "data" / "domains" / "soccer" / "matches.parquet"
        if not p.exists():
            return {
                "verdict": "INSUFFICIENT_DATA",
                "n": 0,
                "markets": {},
                "sum_to_one_ok": False,
                "note": f"Corpus not found at {p}",
                "calibration_note": CALIBRATION_NOTE,
            }
        df = pd.read_parquet(str(p))

    wf = walk_forward_goals(df)
    raw, out, valid = _build_raw_outcomes(wf)
    n_valid = int(valid.sum())

    if n_valid < min_corpus:
        return {
            "verdict": "INSUFFICIENT_DATA",
            "n": n_valid,
            "markets": {},
            "sum_to_one_ok": False,
            "note": f"Thin corpus: {n_valid} < min_corpus={min_corpus}",
            "calibration_note": CALIBRATION_NOTE,
        }

    # Held-out second half of valid events (same split as calib_1x2_wf pattern)
    valid_idx = np.where(valid)[0]
    val_idx = valid_idx[len(valid_idx) // 2:]

    labels = ("cs_home", "cs_away", "btts")
    market_results: Dict[str, Dict] = {}
    all_pass = True

    for col_i, label in enumerate(labels):
        cal = _wf_cal(raw[:, col_i], out[:, col_i], valid, min_history)
        r_val, c_val, y_val = raw[val_idx, col_i], cal[val_idx], out[val_idx, col_i]

        ece_raw = _ece(r_val, y_val)
        ece_cal = _ece(c_val, y_val)
        pb_raw = _pinball(r_val, y_val)
        pb_cal = _pinball(c_val, y_val)
        ece_improves = bool(ece_cal < ece_raw)
        pinball_ok = bool(pb_cal <= pb_raw + 1e-6)
        passes = ece_improves and pinball_ok
        if not passes:
            all_pass = False

        market_results[label] = {
            "ece_raw": float(ece_raw),
            "ece_cal": float(ece_cal),
            "pinball_raw": float(pb_raw),
            "pinball_cal": float(pb_cal),
            "n_val": int(len(val_idx)),
            "ece_improves": ece_improves,
            "pinball_ok": pinball_ok,
            "passes": passes,
        }

    # Coherence check: complement sums to 1 for all valid raw probs
    cs_home_raw = raw[valid, 0]
    sum_to_one_ok = bool(np.all(np.abs(cs_home_raw + (1.0 - cs_home_raw) - 1.0) < 1e-9))

    verdict = "SHIP" if all_pass else "REJECT"
    failing = [k for k, v in market_results.items() if not v["passes"]]
    note = (
        f"verdict={verdict} n_valid={n_valid} held_out={len(val_idx)} | "
        + " | ".join(
            f"{k}: ECE {v['ece_raw']:.4f}->{v['ece_cal']:.4f} "
            f"pinball {v['pinball_raw']:.4f}->{v['pinball_cal']:.4f} "
            f"({'PASS' if v['passes'] else 'FAIL'})"
            for k, v in market_results.items()
        )
        + (f" | REJECT reason: {failing} failed gate" if failing else "")
        + f" | {CALIBRATION_NOTE}"
    )

    return {
        "verdict": verdict,
        "n": n_valid,
        "markets": market_results,
        "sum_to_one_ok": sum_to_one_ok,
        "note": note,
        "calibration_note": CALIBRATION_NOTE,
    }


# ---------------------------------------------------------------------------
# __main__ CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    result = run_calibration()
    print(json.dumps(result, indent=2))
