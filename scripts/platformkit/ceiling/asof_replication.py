"""scripts.platformkit.ceiling.asof_replication -- CROSS-CORPUS replication gate
for the 3 asof-reclaim wave-1 survivors (wta_hold_pct_diff_asof,
soccer_diff_sot_for_asof, soccer_diff_shots_for_asof).

WHY: the m19 sweep (asof_reclaim_sweep.py) runs each candidate through ONE
single-corpus 70/30 walk-forward DM gate.  The binding bar for any SHIP-class
verdict is >=2 INDEPENDENT corpora (no-edge-claims discipline).  This module
(with asof_replication_core.py) builds that bar honestly: for each candidate
we carve the SAME on-disk corpus into two INDEPENDENT split schemes, each
producing two disjoint sub-corpora, and re-run the identical walk-forward DM
gate inside each sub-corpus alone (never training across a sub-corpus
boundary).  Split-scheme + gate mechanics live in asof_replication_core.py
(300-LOC cap); this module is the registry-driven runner + writers + CLI.

SPLIT SCHEMES (mirrors ingame_segment_trust.py's md5 discipline + sp_adjust's
both-eras-same-sign discipline -- see module docstrings for both):
  (a) SEASON-ERA split: sort by date, first half of seasons = era A, second
      half = era B.  A genuine early-vs-late regime check.
  (b) md5 DATE-PARITY split: md5(event_id) even/odd -> two interleaved,
      pseudo-random sub-corpora.  Deterministic (unlike builtin hash(), which
      is per-process randomized -- see ingame_segment_trust.py comment).
Each half is walk-forward evaluated STRICTLY WITHIN itself: rows are re-sorted
by date inside the half and the candidate's own single-corpus _gate_once
(70/30 time-ordered train/test) runs on that half alone.  No row from outside
the half is ever used to fit or score inside it -- zero cross-boundary leak.

VERDICT RULE (pinned, per the lane brief):
  REPLICATES only if, in ALL 4 sub-corpora (era-A, era-B, parity-even,
  parity-odd), the Brier delta improves (brier_delta > 0, i.e. cand beats
  base) AND the feature weight has the SAME SIGN as the wave-1 single-corpus
  result, AND dm_p < 0.10 holds in >= 3 of those 4 sub-corpora.
  Anything less -> honest REJECT, all numbers recorded.
  A REPLICATED verdict is surfaced as SHIP_REVIEW for the human queue --
  NEVER wired into any adapter/predictor (CANDIDATE-ONLY, read-only gates).

CANDIDATE-ONLY / DEFAULT-OFF: imports the existing gate contracts read-only
(domains.tennis.asof_hold_wta_gate, domains.soccer.asof_features_gate). No
flag flipped, no adapter touched, no src.*/kernel.*/api.* import.

Writes: extends the existing ceiling_reclaim_scoreboard.jsonl (does not fork
a new ledger) + a standalone summary at
data/frontend/ops/asof_replication.json.

CLI:  python -m scripts.platformkit.ceiling.asof_replication
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from scripts.platformkit.ceiling.asof_replication_core import (
    DM_P_THRESHOLD,
    MIN_SIGNIFICANT,
    ReplicationSpec,
    registry,
    replicate_one,
)

_REPO = Path(__file__).resolve().parents[3]
SCOREBOARD = _REPO / "data" / "frontend" / "ceiling_reclaim_scoreboard.jsonl"
SUMMARY_JSON = _REPO / "data" / "frontend" / "ops" / "asof_replication.json"

__all__ = ["registry", "replicate_one", "run_all", "main", "ReplicationSpec"]


# --------------------------------------------------------------------------- #
# Ledger + scoreboard writers (extend, do not fork)
# --------------------------------------------------------------------------- #

def _log_reject_ledger(res: Dict) -> None:
    try:
        from scripts.platformkit import reject_ledger as RL
        RL.record(
            sport=res["sport"], signal=res["signal"], verdict=res["verdict"],
            reason="asof cross-corpus replication: " + res["verdict_reason"],
            corpus="asof_replication_4way",
            metrics={"n_rows_total": res["n_rows_total"],
                     "n_significant_sub_corpora": res["n_significant_sub_corpora"],
                     "wave1_dm_p": res["wave1_dm_p"]},
            source="manual",
        )
    except Exception:  # pragma: no cover - ledger is best-effort
        pass


def _append_scoreboard_row(res: Dict, generated_at: str) -> None:
    row = {
        "ts": generated_at, "sport": res["sport"], "signal": res["signal"],
        "verdict": res["verdict"], "stage": "cross_corpus_replication",
        "n_significant_sub_corpora": res["n_significant_sub_corpora"],
        "n_rows_total": res["n_rows_total"],
    }
    SCOREBOARD.parent.mkdir(parents=True, exist_ok=True)
    with SCOREBOARD.open("a", encoding="ascii") as fh:
        fh.write(json.dumps(row) + "\n")


def run_all(log_ledger: bool = True, write_outputs: bool = True) -> List[Dict]:
    results = [replicate_one(spec) for spec in registry()]
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for res in results:
        res["generated_at"] = generated_at
    if write_outputs:
        for res in results:
            _append_scoreboard_row(res, generated_at)
            if log_ledger:
                _log_reject_ledger(res)
        SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
        with SUMMARY_JSON.open("w", encoding="ascii") as fh:
            json.dump({
                "generated_at": generated_at,
                "dm_p_threshold": DM_P_THRESHOLD, "min_significant_required": MIN_SIGNIFICANT,
                "results": results,
            }, fh, indent=2, default=str)
    return results


def main() -> int:
    results = run_all()
    print("=" * 88)
    print("ASOF CROSS-CORPUS REPLICATION -- 3 wave-1 survivors, 4 independent sub-corpora each")
    print("=" * 88)
    for res in results:
        print(f"\n{res['sport']:<8} {res['signal']}")
        print(f"  wave1 single-corpus dm_p={res['wave1_dm_p']}")
        for scheme_name, key in (("season-era", "season_era_scheme"), ("md5-parity", "md5_parity_scheme")):
            sc = res[key]
            print(f"  [{scheme_name}] all_improve={sc['all_improve']} same_sign={sc['same_sign']} "
                  f"n_usable={sc['n_usable']}")
            for half_name, half in sc["halves"].items():
                print(f"      {half_name:<14} verdict={half.get('verdict'):<16} "
                      f"n_cov_test={half.get('n_cov_test')} "
                      f"brier_delta={half.get('brier_delta')} dm_p={half.get('dm_p')} "
                      f"feat_w={half.get('feat_weight')}")
        print(f"  n_significant_sub_corpora={res['n_significant_sub_corpora']}/4 "
              f"(need >={MIN_SIGNIFICANT})")
        print(f"  VERDICT: {res['verdict']} -- {res['verdict_reason']}")
    print("\n" + "=" * 88)
    n_ship_review = sum(1 for r in results if r["verdict"] == "SHIP_REVIEW")
    n_reject = sum(1 for r in results if r["verdict"] == "REJECT")
    print(f"{len(results)} candidates adjudicated | {n_ship_review} SHIP_REVIEW (human queue) | "
          f"{n_reject} REJECT (honest success)")
    print(f"summary -> {SUMMARY_JSON}")
    print("(No candidate is wired into any adapter/predictor. No edge is ever claimed.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
