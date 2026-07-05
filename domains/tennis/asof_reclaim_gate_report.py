"""domains.tennis.asof_reclaim_gate_report -- CLI + verdict-JSON writer for the ATP
as-of reclaim gate (domains.tennis.asof_reclaim_gate).

Split out for LOC-discipline (<=300 LOC/file rule): the sibling module holds pure
gate math; this module holds presentation (print) and persistence (verdict JSON
under data/domains/tennis/, catalog/notes registration only -- no live wiring, no
flag). ACCURACY ONLY -- NO MARKET EDGE CLAIMED.

CLI:  python -m domains.tennis.asof_reclaim_gate_report
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from domains.tennis.asof_reclaim_gate import CANDIDATES, _honest_verdict, run_all

_REPO = Path(__file__).resolve().parents[2]
_OUT_DEFAULT = _REPO / "data/domains/tennis/asof_reclaim_gate_verdict.json"


def _print_report(results: List[Dict]) -> None:
    print("=" * 88)
    print("ATP as-of RECLAIM gate -- hold% / return / serve-form vs Elo AND devigged close")
    print("=" * 88)
    for res in results:
        ve = res["vs_elo"]["real"]
        verdict = _honest_verdict(res)
        print(f"\n{res['feature']:<28} n={res['n_rows']}  covered={res['cov_total']} "
              f"({res['cov_pct']}%)  close_cov={res['close_cov_total']}")
        if ve["verdict"] == "NOT_TESTABLE":
            print("  vs Elo:   NOT_TESTABLE (insufficient covered test rows)")
        else:
            print(f"  vs Elo:   verdict={ve['verdict']:<7} brier_delta={ve['brier_delta']:+.6f} "
                  f"dm_p={ve['dm_p']:.4f} null={res['vs_elo']['planted_null']['verdict']} "
                  f"trunc={res['vs_elo']['truncation']['verdict']}")
        if res["vs_close"] is not None:
            vc = res["vs_close"]["real"]
            if vc["verdict"] == "NOT_TESTABLE":
                print("  vs Close: NOT_TESTABLE (insufficient covered+priced test rows)")
            else:
                print(f"  vs Close: verdict={vc['verdict']:<7} brier_delta={vc['brier_delta']:+.6f} "
                      f"dm_p={vc['dm_p']:.4f} null={res['vs_close']['planted_null']['verdict']} "
                      f"trunc={res['vs_close']['truncation']['verdict']}")
        else:
            print("  vs Close: SKIPPED (< 50 covered+priced rows)")
        print(f"  HONEST VERDICT: {verdict}")
    print("\n(REJECT = honest success; calibration only; no edge ever claimed.)")


def build_verdict_report(seed: int = 0) -> Dict:
    """Run every candidate and assemble the CATALOG/NOTES verdict report dict.

    CANDIDATE-ONLY / DEFAULT-OFF: this function only reads + gates the on-disk
    parquets; it never imports TennisAdapter.feature_bundle or signal_catalog.py
    and never flips a flag.  Verdict is CALIBRATION (held-out Brier), never $.
    """
    results = run_all(seed=seed)
    rows = []
    for res in results:
        rows.append({
            "feature": res["feature"],
            "n_rows": res["n_rows"],
            "cov_total": res["cov_total"],
            "cov_pct": res["cov_pct"],
            "close_cov_total": res["close_cov_total"],
            "vs_elo": res["vs_elo"],
            "vs_close": res["vs_close"],
            "honest_verdict": _honest_verdict(res),
        })
    n_ship = sum(1 for r in rows if r["honest_verdict"] == "SHIP")
    n_reject = sum(1 for r in rows if r["honest_verdict"] == "REJECT")
    n_untestable = sum(1 for r in rows if r["honest_verdict"] == "NOT_TESTABLE")
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sport": "tennis", "tour": "atp",
        "gate": "domains.tennis.asof_reclaim_gate (single-corpus walk-forward DM, "
                "planted-null + truncation-invariance controls)",
        "sources": sorted({spec[1].relative_to(_REPO).as_posix() for spec in CANDIDATES}),
        "n_candidates": len(rows), "n_ship": n_ship, "n_reject": n_reject,
        "n_not_testable": n_untestable,
        "summary": (
            f"{n_reject}/{len(rows)} REJECT, {n_ship}/{len(rows)} SHIP, "
            f"{n_untestable}/{len(rows)} NOT_TESTABLE. "
            "REJECT/NULL is an honest success; no edge is claimed anywhere. "
            "Candidate-only / default-off: no adapter, catalog, or predictor wiring; "
            "no flag flipped."
        ),
        "candidates": rows,
    }


def write_verdict_json(out_path: Path = _OUT_DEFAULT, seed: int = 0) -> Path:
    """Write the verdict report to data/domains/tennis/ as JSON; return the path."""
    report = build_verdict_report(seed=seed)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return out_path


def main() -> int:
    results = run_all()
    _print_report(results)
    dest = write_verdict_json()
    print(f"\nverdict JSON written -> {dest.relative_to(_REPO).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_verdict_report", "write_verdict_json", "main"]
