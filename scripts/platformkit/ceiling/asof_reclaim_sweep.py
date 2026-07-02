"""scripts.platformkit.ceiling.asof_reclaim_sweep -- gate EVERY on-disk leak-free
asof ``*_diff_asof`` candidate through the REAL single-corpus walk-forward DM gate
and log the SHIP/REJECT verdict, autonomously (no Claude in the loop).

WHY: the ceiling lever "reclaim already-on-disk data through the leak-free gate" is
a cheap, repeatable experiment.  The daemons keep refreshing the asof parquets; this
sweep re-gates them on a schedule, records each verdict to the reject_ledger, and
appends a one-line scoreboard row -> the "getting better" search runs on the flywheel.

CONTRACT (honest):
  * Each registered candidate is gated by a VERIFIED, consistent gate.  We register
    only candidates we can normalize against that contract (NBA generic Elo gate +
    MLB sp_ra_diff_asof, which shares the same run() shape).  Other sports' evals
    have heterogeneous return shapes; they are added here ONLY once they expose the
    same {real:{verdict,brier_base,brier_cand,...}} contract -- never faked.
  * REJECT is the EXPECTED, honest verdict (pregame markets are efficient).  A SHIP
    is flagged as a probable artifact for human review; no $ / edge is ever claimed.
  * CANDIDATE-ONLY: reads parquets additively, flips NO flag, touches NO predictor.

F5 / invariants: no src.*/kernel.*/api.* imports; ASCII only; local-only ledger.

CLI:  python -m scripts.platformkit.ceiling.asof_reclaim_sweep
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List

_REPO = Path(__file__).resolve().parents[3]
_NBA = _REPO / "data" / "domains" / "basketball_nba"
SCOREBOARD = _REPO / "data" / "frontend" / "ceiling_reclaim_scoreboard.jsonl"


@dataclass(frozen=True)
class GateSpec:
    sport: str
    signal: str
    fn: Callable[[], Dict]   # returns the eval module's {real, ...} dict


# --------------------------------------------------------------------------- #
# Per-sport candidate adapters -> the shared {real:{verdict,brier_*,...}} shape
# --------------------------------------------------------------------------- #

def _nba(feat_col: str, parquet: str) -> Callable[[], Dict]:
    from domains.basketball_nba import asof_ast_rate_eval as nba

    def _fn() -> Dict:
        return nba.gate_feature(feat_col, asof_path=str(_NBA / parquet))
    return _fn


def _mlb_ra_diff() -> Dict:
    from domains.mlb import asof_ra_diff_eval as mlb
    return mlb.run()


def registry() -> List[GateSpec]:
    """The frozen candidate list.  Extend ONLY with same-contract evals."""
    specs = [
        GateSpec("nba", "nba_ast_rate_diff_asof",
                 _nba("ast_rate_diff_asof", "asof_features.parquet")),
        GateSpec("nba", "nba_dreb_diff_asof",
                 _nba("dreb_diff_asof", "asof_box_extra.parquet")),
        GateSpec("nba", "nba_fg3m_diff_asof",
                 _nba("fg3m_diff_asof", "asof_box_extra.parquet")),
        GateSpec("nba", "nba_stl_diff_asof",
                 _nba("stl_diff_asof", "asof_box_extra.parquet")),
        GateSpec("nba", "nba_blk_diff_asof",
                 _nba("blk_diff_asof", "asof_box_extra.parquet")),
        GateSpec("mlb", "mlb_sp_ra_diff_asof", _mlb_ra_diff),
    ]
    return specs


# --------------------------------------------------------------------------- #
# Normalize + control checks
# --------------------------------------------------------------------------- #

def _normalize(spec: GateSpec, res: Dict) -> Dict:
    """Flatten the eval result + apply the control gates (null must collapse,
    truncation must match) so a SHIP that fails a control is downgraded to REVIEW.
    """
    real = res.get("real", {})
    null = res.get("planted_null", {})
    trunc = res.get("truncation", {})
    verdict = real.get("verdict", "ERROR")
    null_ok = null.get("verdict") == "REJECT"
    trunc_ok = trunc.get("verdict") == verdict
    # a SHIP only survives if BOTH controls hold; else it is a probable artifact
    if verdict == "SHIP" and not (null_ok and trunc_ok):
        verdict = "SHIP_REVIEW"
    return {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sport": spec.sport, "signal": spec.signal, "verdict": verdict,
        "n_cov_test": real.get("n_cov_test"),
        "brier_base": real.get("brier_base"), "brier_cand": real.get("brier_cand"),
        "brier_delta": real.get("brier_delta"), "dm_p": real.get("dm_p"),
        "feat_weight": real.get("feat_weight"), "cov_pct": res.get("cov_pct"),
        "null_collapses": null_ok, "truncation_invariant": trunc_ok,
    }


def _log_reject_ledger(row: Dict) -> None:
    """Mirror the verdict into the signal graveyard (best-effort, never fatal)."""
    try:
        from scripts.platformkit import reject_ledger as RL
        RL.record(
            sport=row["sport"], signal=row["signal"], verdict=row["verdict"],
            reason=("asof reclaim sweep: Brier base %s -> cand %s (delta %s); "
                    "DM p=%s; null_collapses=%s trunc_inv=%s"
                    % (row["brier_base"], row["brier_cand"], row["brier_delta"],
                       row["dm_p"], row["null_collapses"], row["truncation_invariant"])),
            corpus="asof_reclaim_sweep",
            metrics={k: row[k] for k in ("n_cov_test", "brier_base", "brier_cand",
                                         "brier_delta", "dm_p", "feat_weight")},
            source="manual",
        )
    except Exception:  # pragma: no cover - ledger is best-effort
        pass


# --------------------------------------------------------------------------- #
# Sweep
# --------------------------------------------------------------------------- #

def sweep(log_ledger: bool = True, write_scoreboard: bool = True) -> List[Dict]:
    """Gate every registered candidate; return normalized rows.  Each candidate is
    isolated in try/except so one failure never kills the autonomous sweep."""
    rows: List[Dict] = []
    for spec in registry():
        try:
            res = spec.fn()
            row = _normalize(spec, res)
        except Exception as exc:  # robust: record ERROR, keep going
            row = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "sport": spec.sport, "signal": spec.signal,
                   "verdict": "ERROR", "error": str(exc)[:200]}
        rows.append(row)
        if log_ledger and row.get("verdict") not in ("ERROR",):
            _log_reject_ledger(row)
    if write_scoreboard and rows:
        SCOREBOARD.parent.mkdir(parents=True, exist_ok=True)
        with SCOREBOARD.open("a", encoding="ascii") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
    return rows


def main() -> int:
    rows = sweep()
    print("=" * 78)
    print("ASOF RECLAIM SWEEP -- leak-free single-corpus WF DM gate (calibration only)")
    print("=" * 78)
    print(f"{'sport':<5} {'signal':<26} {'verdict':<12} {'brier_delta':>12} {'dm_p':>7}")
    print("-" * 78)
    for r in rows:
        print(f"{r.get('sport',''):<5} {r.get('signal',''):<26} "
              f"{r.get('verdict',''):<12} {str(r.get('brier_delta','')):>12} "
              f"{str(r.get('dm_p','')):>7}")
    n_rej = sum(1 for r in rows if r.get("verdict") == "REJECT")
    print("-" * 78)
    print(f"{len(rows)} candidates  |  {n_rej} REJECT (honest success)  |  "
          f"scoreboard -> {SCOREBOARD.name}")
    print("(REJECT = market efficient; no edge ever claimed.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
