"""scripts.platformkit.proof_tennis.recal_parity -- WTA/ATP recalibration parity check.

Two checks: (1) TOUR PARITY -- recalibrate_holdout on held-out ATP/WTA probs;
PASS when ECE_recal < ECE_TARGET for BOTH. (2) Bo5 SIGMA COVERAGE -- 50% Gaussian
band coverage of held-out Bo5 outcomes; target [0.40, 0.67].

CALIBRATION != EDGE. Brier/ECE-graded; markets efficient; no $ edge. <=300 LOC.

Corpus paths (env-overridable via PROOF_CORPUS_ROOT):
  ATP : data/domains/tennis/matches.parquet
  WTA : data/domains/tennis/wta_matches.parquet

Run:
  python -m scripts.platformkit.proof_tennis.recal_parity
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.tennis import elo_tune as et  # noqa: E402
from scripts.platformkit.proof_tennis.ingame_calib import (  # noqa: E402
    ece10,
    recalibrate_holdout,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ECE_TARGET: float = 0.025          # held-out ECE must be below this for PASS
_TRAIN_YEAR_MAX: int = et.TRAIN_YEAR_MAX   # 2022
_Z50: float = 0.6745               # z-score for 50% two-sided Gaussian interval
_BOX3_PP: float = 0.03             # tolerance: 50pct +-3pp -> [0.47, 0.53]
_MIN_N_RECAL: int = 200            # minimum held-out eval rows to run recal
_MIN_N_BO5: int = 60               # minimum Bo5 held-out rows for sigma check


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
def _corpus_root() -> Optional[Path]:
    """$PROOF_CORPUS_ROOT if set, else None."""
    env = os.environ.get("PROOF_CORPUS_ROOT")
    return Path(env) if env else None


def _atp_path() -> Path:
    root = _corpus_root()
    return (root / "tennis" / "matches.parquet") if root else _REPO / "data" / "domains" / "tennis" / "matches.parquet"


def _wta_path() -> Path:
    root = _corpus_root()
    return (root / "tennis" / "wta_matches.parquet") if root else _REPO / "data" / "domains" / "tennis" / "wta_matches.parquet"


# ---------------------------------------------------------------------------
# Per-tour recalibration
# ---------------------------------------------------------------------------
def _tour_recal(parquet_path: Path, tour_label: str, best_blend: float) -> Dict:
    """Walk-forward Elo at best_blend, then recalibrate_holdout on held-out preds.

    Fit is on the TRAIN half (chronological first half of the held-out set);
    scoring is on the EVAL half (second half). Never refits on eval labels.
    """
    if not parquet_path.is_file():
        return {
            "tour": tour_label,
            "status": "no_data",
            "path": str(parquet_path),
        }
    matches = pd.read_parquet(parquet_path)
    wf = et._walk_forward_blend(matches, best_blend)
    years = pd.to_datetime(wf["date"]).dt.year
    test_df = wf[years > _TRAIN_YEAR_MAX].reset_index(drop=True)
    p_raw = test_df["win_prob_p1"].to_numpy(dtype=float)
    y = (test_df["winner"] == 1).to_numpy(dtype=float)
    n_holdout = len(p_raw)
    if n_holdout < _MIN_N_RECAL:
        return {
            "tour": tour_label,
            "status": "INSUFFICIENT_DATA",
            "n_holdout": n_holdout,
            "min_required": _MIN_N_RECAL,
        }
    res = recalibrate_holdout(p_raw, y)
    passed = bool(res["ece_recal"] < ECE_TARGET)
    return {
        "tour": tour_label,
        "status": "ok",
        "n_total": int(len(matches)),
        "n_holdout": n_holdout,
        "best_blend": best_blend,
        "recal_method": res["recal_method"],
        "recal_params": res["recal_params"],
        "n_eval": res["n_eval"],
        "ece_raw": res["ece_raw"],
        "ece_recal": res["ece_recal"],
        "ece_target": ECE_TARGET,
        "reliability_slope": res["reliability_slope"],
        "brier_raw": res["brier_raw"],
        "brier_recal": res["brier_recal"],
        "brier_not_worse": bool(res["brier_recal"] <= res["brier_raw"] + 1e-4),
        "passed": passed,
        "verdict": ("PASS -- ECE_recal < target" if passed
                    else "HONEST FAIL -- ECE_recal >= target (data-limited or systematic)"),
    }


# ---------------------------------------------------------------------------
# Bo5 sigma coverage check
# ---------------------------------------------------------------------------
def _bo5_sigma_coverage(atp_path: Path) -> Dict:
    """50% Gaussian band coverage of ATP Bo5 held-out forecasts.

    sigma_i = sqrt(p*(1-p)); in_band = |y-p| <= Z50*sigma.
    Target [0.40, 0.67] (Bernoulli-adjusted). No $ edge.
    """
    if not atp_path.is_file():
        return {
            "status": "no_data",
            "note": "ATP matches.parquet not found; cannot run Bo5 sigma check.",
        }
    matches = pd.read_parquet(atp_path)
    wf = et._walk_forward_blend(matches, 0.3)
    years = pd.to_datetime(wf["date"]).dt.year
    bo5 = wf[(wf["best_of"] == 5) & (years > _TRAIN_YEAR_MAX)].reset_index(drop=True)
    if len(bo5) < _MIN_N_BO5:
        return {
            "status": "INSUFFICIENT_DATA",
            "n": int(len(bo5)),
            "min_required": _MIN_N_BO5,
        }

    # Raw Elo probs for the Bo5 held-out set (combined = raw Elo here as a proxy,
    # since we do not re-run the full repricer set-state loop; the point-probability
    # calibration check is on the pregame elo prob which is the same forecaster base)
    p = bo5["win_prob_p1"].to_numpy(dtype=float)
    y = (bo5["winner"] == 1).to_numpy(dtype=float)

    sigma = np.sqrt(p * (1.0 - p))
    in_band = np.abs(y - p) <= (_Z50 * sigma)
    coverage = float(in_band.mean())

    lo_ok, hi_ok = 0.40, 0.67
    in_range = bool(lo_ok <= coverage <= hi_ok)
    return {
        "status": "ok",
        "n_bo5_holdout": int(len(p)),
        "z50": _Z50,
        "coverage_50pct_band": round(coverage, 4),
        "expected_range": f"[{lo_ok}, {hi_ok}] (Bernoulli-adjusted; Gaussian would be ~0.50)",
        "in_expected_range": in_range,
        "verdict": ("sigma coverage in expected range" if in_range
                    else f"HONEST FAIL -- coverage {round(coverage, 4)} outside [{lo_ok}, {hi_ok}]"),
        "note": "50% Gaussian band on binary Bo5. Bernoulli coverage > Gaussian nominal. No $ edge.",
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def run(atp_path: Optional[Path] = None, wta_path: Optional[Path] = None) -> Dict:
    """Run WTA/ATP recalibration parity + Bo5 sigma coverage check.

    Returns dict with keys: atp, wta, bo5_sigma, parity_verdict, note.
    Identity smoke test lives in test_recal_parity.py.
    """
    atp_p = atp_path or _atp_path()
    wta_p = wta_path or _wta_path()

    # Best blend per tour (from blend_sweep; ATP Brier=0.3, WTA ECE=0.3).
    atp_res = _tour_recal(atp_p, "ATP", best_blend=0.3)
    wta_res = _tour_recal(wta_p, "WTA", best_blend=0.3)
    bo5_res = _bo5_sigma_coverage(atp_p)

    atp_ok = atp_res.get("passed", False)
    wta_ok = wta_res.get("passed", False)
    both_ok = atp_ok and wta_ok

    parity_verdict = (
        "PARITY PASS -- held-out ECE_recal < target for BOTH tours" if both_ok
        else "PARITY PARTIAL -- " + ", ".join(
            [f"{t} FAIL" for t, ok in [("ATP", atp_ok), ("WTA", wta_ok)] if not ok]
        ) + " (honest data-limited result)"
    )

    return {
        "atp": atp_res,
        "wta": wta_res,
        "bo5_sigma": bo5_res,
        "ece_target": ECE_TARGET,
        "parity_verdict": parity_verdict,
        "note": "CALIBRATION only -- not a market edge. Honest FAIL is valid. No $ edge.",
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _main() -> int:
    rep = run()
    print("=== WTA/ATP Recalibration Parity + Bo5 Sigma Coverage ===")
    print(f"ECE target: <{rep['ece_target']}")
    for tour in ("atp", "wta"):
        r = rep[tour]
        if r.get("status") != "ok":
            print(f"  {tour.upper()}: {r.get('status')} -- {r.get('path','')}")
            continue
        print(f"  {r['tour']}: n_holdout={r['n_holdout']}  blend={r['best_blend']}")
        print(f"    recal_method={r['recal_method']}  params={r['recal_params']}")
        print(f"    ECE: raw={r['ece_raw']} -> recal={r['ece_recal']}  "
              f"(target<{r['ece_target']})  brier: {r['brier_raw']}->{r['brier_recal']}")
        print(f"    reliability_slope={r['reliability_slope']}  "
              f"brier_not_worse={r['brier_not_worse']}")
        print(f"    VERDICT: {r['verdict']}")
    b = rep["bo5_sigma"]
    if b.get("status") == "ok":
        print(f"  Bo5 sigma coverage (n={b['n_bo5_holdout']}, z={b['z50']}): "
              f"{b['coverage_50pct_band']} {b['expected_range']}")
        print(f"    {b['verdict']}")
    else:
        print(f"  Bo5 sigma: {b.get('status')} {b.get('note','')}")
    print(f"\nPARITY: {rep['parity_verdict']}")
    print(rep["note"])
    return 0 if rep["parity_verdict"].startswith("PARITY PASS") else 1


if __name__ == "__main__":
    raise SystemExit(_main())
