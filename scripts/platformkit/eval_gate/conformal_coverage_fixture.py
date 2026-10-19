"""scripts.platformkit.eval_gate.conformal_coverage_fixture -- S687 seeded synthetic walk-forward fixture.

SYNTHETIC ONLY (the cloud clone has no data/). Five sports, each a stand-in for one sport's
walk-forward prediction table:
  fx_binary_calm   binary, stationary, calibrated               -> expected WITHIN
  fx_binary_drift  binary, the label law flips on the later dates -> expected FLAGGED_UNDER
  fx_binary_thin   binary, 120 rows                             -> expected INSUFFICIENT
  fx_reg_calm      regression, stationary Gaussian residuals     -> expected WITHIN
  fx_reg_drift     regression, residual sd x2 on the later dates -> expected FLAGGED_UNDER
Calm / drift sports carry 10,000 rows over 500 dates (~5,000 per side). Deterministic for a seed.
Usage: python -m scripts.platformkit.eval_gate.conformal_coverage_fixture --out F.csv [--seed 687]
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate import conformal_coverage_core as core
from scripts.platformkit.ops.atomic_replace import replace_with_retry

SEED = 687
START = pd.Timestamp("2026-04-01")


def _frame(sport: str, n_dates: int, per_date: int, rng: np.random.Generator,
           kind: str, drift: bool) -> pd.DataFrame:
    n = n_dates * per_date
    day = np.repeat(np.arange(n_dates), per_date)
    later = day >= n_dates // 2
    if kind == "binary":
        p = rng.uniform(0.02, 0.98, n)
        truth = np.where(later & drift, 1.0 - p, p)
        y = (rng.uniform(size=n) < truth).astype(int)
        pred = p
    else:
        pred = rng.normal(0.0, 5.0, n)
        sd = np.where(later & drift, 2.0, 1.0)
        y = pred + rng.normal(0.0, 1.0, n) * sd
    return pd.DataFrame({
        "sport": sport,
        "date": (START + pd.to_timedelta(day, unit="D")).strftime("%Y-%m-%d"),
        "game_id": ["%s-%06d" % (sport, i) for i in range(n)],
        "y": y, "pred": np.round(pred, 12)})


def make_fixture(seed: int = SEED) -> pd.DataFrame:
    """Build the five-sport synthetic table (deterministic for a seed)."""
    rng = np.random.default_rng(seed)
    parts = [
        _frame("fx_binary_calm", 500, 20, rng, "binary", False),
        _frame("fx_binary_drift", 500, 20, rng, "binary", True),
        _frame("fx_binary_thin", 30, 4, rng, "binary", False),
        _frame("fx_reg_calm", 500, 20, rng, "regression", False),
        _frame("fx_reg_drift", 500, 20, rng, "regression", True),
    ]
    return pd.concat(parts, ignore_index=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="S687 synthetic walk-forward fixture")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args(argv)
    core.refuse_registry_output(a.out)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=a.out.parent) as temporary_dir:
        temporary = Path(temporary_dir) / a.out.name
        make_fixture(a.seed).to_csv(temporary, index=False, lineterminator="\n", float_format="%.12g")
        replace_with_retry(temporary, a.out)
    print("wrote %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
