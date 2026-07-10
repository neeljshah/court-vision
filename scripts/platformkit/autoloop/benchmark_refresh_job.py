"""scripts.platformkit.autoloop.benchmark_refresh_job -- M15: watermark-gated
RERUN of the two wired-shadow benchmarks that M09 (shadow_settle_wired.py)
only WATCHES. Per the autonomy charter, watching readiness is not enough --
nothing accrues a moat checkpoint (inn6/7/8 provisionals) without a human
running the CLI by hand. This job pulls the trigger once a corpus is powered.

REFRESH ONLY -- zero promotion logic. Calling each existing entrypoint with
its existing (default) args IS the whole job; the promotion bar (CI excludes
zero on an independent-corpus rerun) stays human, same as M09's
PROMOTE_CANDIDATE note already says. shadow_settle_wired.py is READ-ONLY
here -- its baseline readers are reused, never edited.

READINESS reuses shadow_settle_wired's OWN baseline + counting (its
_mlb_crps_baseline / _soccer_chain_baseline, and the same eligible-match
filter the soccer wired-shadow already calls) so "due" means exactly what
M09's PROMOTE_CANDIDATE tick already means -- one definition of "powered",
not two that can drift apart.

  1. mlb_crps -- scripts.platformkit.benchmarks.crps_market.ingame_mlb.run()
     (existing --max-games default=300, already >= the 178 real game files,
     so no override needed). Self-resetting watermark: a successful rerun
     overwrites last_run_ingame_mlb.json's own n_game_files, so the very next
     readiness check needs a fresh min_n-sized batch of NEW games before it
     fires again -- no separate watermark to drift from the artifact.
  2. soccer_chain -- domains.soccer.chain_engine.validate_full_power.run()
     called with the SAME min_matches the baseline artifact was built at
     (an explicit passthrough, not the module's own default, so the rerun is
     an apples-to-apples comparison against that baseline) + its own
     append_ledger_row (same as the CLI's default path -- not new promotion
     logic, just the honest recomputed verdict landing in the same ledger a
     human run would write to). Measured wall-clock on this box: ~6s for a
     51-match competition, ~36s for a 380-match one -- summed over ~20
     eligible competitions, a full run is ~5-6min, under the ~10min bound
     this job holds itself to.

HONESTY: refresh only. No new verdict math invented here, no $/ROI. Every
artifact this job writes already carries edge_claimed:false (unchanged from
the wrapped entrypoint's own output).

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; never writes
data/registry/; never flips a flag; one sport failing never blocks the other.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autoloop/test_benchmark_refresh_job.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from scripts.platformkit.autoloop.shadow_settle_wired import (
    _mlb_crps_baseline as _default_mlb_baseline,  # noqa: SLF001 -- reused read-only, mirrors M09's own convention
    _soccer_chain_baseline as _default_soccer_baseline,  # noqa: SLF001
)

_MLB_KEY = "M15_benchmark_refresh__mlb_crps"
_SOCCER_KEY = "M15_benchmark_refresh__soccer_chain"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mlb_n_avail() -> int:
    from scripts.platformkit.benchmarks.crps_market import ingame_mlb as IM
    return len(list(IM._GAME_DIR.glob("*.jsonl"))) if IM._GAME_DIR.is_dir() else 0  # noqa: SLF001


def _soccer_n_eligible(min_matches: int) -> int:
    import pandas as pd
    from domains.soccer.chain_engine import validate_full_power as VFP
    meta = pd.read_parquet(VFP.MATCH_META_FULL, columns=["competition"])
    comps = VFP._eligible_competitions(meta, min_matches)  # noqa: SLF001 -- gate's own filter, reused not reimplemented
    return int(meta["competition"].isin(comps).sum())


def _default_mlb_rerun() -> Dict[str, Any]:
    from scripts.platformkit.benchmarks.crps_market import ingame_mlb as IM
    return IM.run()


def _default_soccer_rerun(min_matches: int) -> Dict[str, Any]:
    from domains.soccer.chain_engine import validate_full_power as VFP
    doc = VFP.run(min_matches=min_matches)
    VFP.append_ledger_row(doc)  # same default path _main() takes -- honest verdict, not a promotion
    return doc


def run_benchmark_refresh(watermarks: Dict[str, Any], *,
                          mlb_baseline_fn: Optional[Callable[[], Optional[Dict[str, Any]]]] = None,
                          mlb_n_avail_fn: Optional[Callable[[], int]] = None,
                          mlb_rerun_fn: Optional[Callable[[], Any]] = None,
                          soccer_baseline_fn: Optional[Callable[[], Optional[Dict[str, Any]]]] = None,
                          soccer_n_eligible_fn: Optional[Callable[[int], int]] = None,
                          soccer_rerun_fn: Optional[Callable[[int], Any]] = None) -> Dict[str, Any]:
    """Rerun each wired shadow's source benchmark iff its own readiness bar
    (baseline's min_n / min_matches -- the SAME number M09's PROMOTE_CANDIDATE
    tick uses) is met by NEW rows since that baseline. REFRESH ONLY. Each
    sport isolated: one raising never blocks the other."""
    out: Dict[str, Any] = {}

    mlb_baseline = (mlb_baseline_fn or _default_mlb_baseline)()
    if mlb_baseline is None:
        out["mlb_crps"] = {"status": "no_baseline"}
    else:
        n_avail = (mlb_n_avail_fn or _mlb_n_avail)()
        n_new = n_avail - mlb_baseline["n_game_files"]
        min_n = mlb_baseline["min_n"]
        if n_new < min_n:
            out["mlb_crps"] = {"status": "skipped", "reason": "not powered",
                               "n_new": n_new, "min_n": min_n}
        else:
            try:
                (mlb_rerun_fn or _default_mlb_rerun)()
                watermarks[_MLB_KEY] = {"n_game_files_at_run": n_avail, "last_run_ts": _now_iso()}
                out["mlb_crps"] = {"status": "ran", "n_new": n_new, "n_game_files": n_avail}
            except Exception as exc:  # noqa: BLE001 -- one sport failing must not block the other
                out["mlb_crps"] = {"status": "error", "error": str(exc)[:200]}

    soccer_baseline = (soccer_baseline_fn or _default_soccer_baseline)()
    if soccer_baseline is None:
        out["soccer_chain"] = {"status": "no_baseline"}
    else:
        min_matches = soccer_baseline["min_matches"]
        n_eligible = (soccer_n_eligible_fn or _soccer_n_eligible)(min_matches)
        n_new = n_eligible - soccer_baseline["n_matches_total"]
        if n_new < min_matches:
            out["soccer_chain"] = {"status": "skipped", "reason": "not powered",
                                   "n_new": n_new, "min_matches": min_matches}
        else:
            try:
                (soccer_rerun_fn or _default_soccer_rerun)(min_matches)
                watermarks[_SOCCER_KEY] = {"n_matches_at_run": n_eligible, "last_run_ts": _now_iso()}
                out["soccer_chain"] = {"status": "ran", "n_new": n_new, "n_matches": n_eligible}
            except Exception as exc:  # noqa: BLE001
                out["soccer_chain"] = {"status": "error", "error": str(exc)[:200]}

    return out


__all__ = ["run_benchmark_refresh", "_MLB_KEY", "_SOCCER_KEY"]
