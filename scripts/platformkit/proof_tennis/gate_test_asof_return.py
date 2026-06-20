"""scripts.platformkit.proof_tennis.gate_test_asof_return -- HONEST as-of RETURN gate test.

Threads the leak-free as-of RETURN diffs (domains.tennis.asof_return) -- the distinct
return-game dimension that serve-side asof_hold / asof_features do NOT cover -- through
the REAL honest gate (src.loop.gate.evaluate) on top of the Elo base.

REUSES the proven base-bundle construction from gate_test_asof (_build_base_bundle_with_ids,
_align_asof, _ArraySignal) so the Elo/surface/best_of/rest base stays byte-identical to
TennisAdapter; only the candidate columns + parquet differ.

DISCIPLINE (binding): expected verdict REJECT or DEFER. Prior-only trailing return form
is very likely REDUNDANT with Elo (player quality already priced). A SHIP verdict is a
PROBABLE ARTIFACT; NO edge is ever claimed. Deeper data => a calibration ceiling, not $.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src.loop.gate import evaluate
from scripts.platformkit.catalog_common import derive_bundle
from scripts.platformkit.proof_tennis.gate_test_asof import (
    _ASOF_SEASONS,
    _ArraySignal,
    _align_asof,
    _build_base_bundle_with_ids,
)

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ASOF_PARQUET = _REPO_ROOT / "data" / "domains" / "tennis" / "asof_return.parquet"

# Overall return diffs (highest coverage); both are pure transforms of leak-free
# prior-only player rates, selected dynamically from the parquet schema.
_PREFERRED_CANDIDATES: Tuple[str, ...] = (
    "diff_return_won_asof",
    "diff_break_pct_asof",
)


def _candidate_columns(asof_df: pd.DataFrame) -> List[str]:
    cols = set(asof_df.columns)
    return [c for c in _PREFERRED_CANDIDATES if c in cols]


def run_gate_test(
    seasons: Optional[Sequence[int]] = None,
    asof_path: Optional[Path] = None,
) -> List[dict]:
    """Run each candidate return-diff column through the REAL gate; return verdict rows."""
    _seasons = list(seasons) if seasons is not None else list(_ASOF_SEASONS)
    apath = Path(asof_path) if asof_path is not None else _ASOF_PARQUET
    if not apath.exists():
        raise FileNotFoundError(
            f"asof_return.parquet not found at {apath}. Run "
            "domains.tennis.asof_return first.")
    asof_df = pd.read_parquet(apath)

    bb, event_ids = _build_base_bundle_with_ids(seasons=_seasons)
    n = bb.base.shape[0]
    candidates = _candidate_columns(asof_df)

    rows: List[dict] = []
    for col in candidates:
        sc = _align_asof(asof_df, event_ids, col)
        coverage = float(np.sum(~np.isnan(sc))) / max(n, 1)
        sig = _ArraySignal(name=f"tennis_{col}")
        sig._gate_matrix = derive_bundle(bb, sc)  # type: ignore[attr-defined]
        r = evaluate(sig, device="cpu", n_splits=3)
        verdict = r.verdict.value
        if verdict == "SHIP":
            logger.warning(
                "TENNIS RETURN AS-OF SHIP FLAG '%s': PROBABLE ARTIFACT. NO edge claimed.", col)
        rows.append({
            "name": sig.name, "column": col, "verdict": verdict,
            "coverage": round(coverage, 4), "n": n,
            "wf_all_improve": r.wf_all_improve, "ablation_pass": r.ablation_pass,
            "null_pass": r.null_pass, "calibration_ok": r.calibration_ok,
            "clv": r.clv, "p_value": r.p_value, "reason": r.reason,
        })
    return rows


def _summary_line(rows: List[dict]) -> str:
    if not rows:
        return "Tennis as-of return: NO candidate columns evaluable -> DEFER; no edge."
    ships = [r["name"] for r in rows if r["verdict"] == "SHIP"]
    verds = sorted({r["verdict"] for r in rows})
    if ships:
        return ("Tennis as-of return: SHIP flagged for " + ", ".join(ships) +
                " -> PROBABLE ARTIFACT, NO edge claimed (artifact-hunt required).")
    return ("Tennis as-of return: " + "/".join(verds) +
            " -> NO edge; markets efficient / redundant with Elo; calibration ceiling deepened only.")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    rows = run_gate_test()
    hdr = f"{'Candidate':<30} {'Verdict':<8} {'Cover':>6} {'wf_all':>7} {'abl':>5} {'null':>5} {'calib':>6} {'p':>8}"
    print("\nTennis as-of RETURN gate test (REAL gate; seasons="
          + ",".join(str(s) for s in _ASOF_SEASONS) + ")")
    print("=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        p = r["p_value"]
        print(f"{r['name']:<30} {r['verdict']:<8} {r['coverage']:>6.3f} "
              f"{str(r['wf_all_improve']):>7} {str(r['ablation_pass']):>5} "
              f"{str(r['null_pass']):>5} {str(r['calibration_ok']):>6} "
              f"{('%.4f' % p) if p is not None else '   -':>8}")
    print("-" * len(hdr))
    print(_summary_line(rows))
    print("(REJECT/DEFER = honest success; no edge is ever claimed here.)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_gate_test", "_summary_line", "_candidate_columns", "main"]
