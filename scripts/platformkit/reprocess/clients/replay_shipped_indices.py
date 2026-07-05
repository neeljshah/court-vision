"""Reprocess-harness client registry for ADOPTED/SHIPPED layers (wave-30 lane 8).

The reprocess harness (reprocess_harness.py) is proven to 1e-6 but has zero
standing clients wired to it. This module enumerates the layers that carry an
ADOPT/SHIP verdict (REJECTs need no client -- nothing to reprocess-compare),
and for each one either:
  (a) registers a runnable client (name, rows_source callable, metric,
      committed verdict path, tolerance) that the harness can replay, or
  (b) records an honest UNAVAILABLE with a reason, when the per-row scores
      backing the committed verdict were never persisted (only aggregate
      per-checkpoint/per-corpus Brier was written) -- re-deriving them would
      mean RE-RUNNING the gate, which this task explicitly says not to force.

SEARCH PERFORMED (this is the full enumeration, not a partial scan):
  - grep for ADOPT/SHIP verdict strings across .planning/*.md          -> none
    found tagged as a shipped *layer* (only proposals/plans).
  - grep for '"verdict": "ADOPT"' / cross_corpus_winner_adopted across
    data/**/*.json                                                     -> ONE
    hit: data/domains/wnba/hist_blend_crosscorpus_check.json (+ sibling
    data/domains/wnba/ingame_blend_check.json, same adopted family).
  - domains/basketball_wnba/hist_blend_crosscorpus.py implements the ADOPT
    rule (adopt_verdict()): a family adopted only if it wins every checkpoint
    in BOTH directions across both corpora. "anchored" family won -> ADOPT.
  - Tennis WTA surface-hold-pct gate (data/domains/tennis/surface_hold_gate_
    verdict.json) was checked as a candidate per the task text, but its
    verdict is REJECT for both ATP and WTA (both_tours_ship: false) -- no
    client needed, it is correctly excluded.
  - No other verdict JSON under data/domains/**/*.json carries an ADOPT/SHIP
    decision (grep across the tree returned only the WNBA hit above).

REGISTERED CLIENTS: see REGISTRY below.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from scripts.platformkit.reprocess.reprocess_harness import (
    SchemaError,
    run_harness,
    verdict_to_dict,
)

_REPO = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class ReprocessClient:
    """One registered ADOPTED/SHIPPED layer wired to the reprocess harness."""
    name: str
    metric: str  # "brier" | "rho"
    committed_verdict_path: Path
    tolerance: float
    rows_source: Optional[Callable[[], pd.DataFrame]]  # None => UNAVAILABLE
    unavailable_reason: Optional[str] = None


def _wnba_anchored_unavailable_reason() -> str:
    return (
        "ADOPTED layer: WNBA anchored in-game linescore blend "
        "(domains/basketball_wnba/hist_blend_crosscorpus.py, adopt_verdict() "
        "-> 'anchored' family, verdict=cross_corpus_winner_adopted; see "
        "data/domains/wnba/hist_blend_crosscorpus_check.json and "
        "data/domains/wnba/ingame_blend_check.json). Per-row p_variant/p_base/"
        "outcome triples backing those committed Brier numbers were never "
        "persisted to disk -- only aggregate per-checkpoint, per-corpus Brier "
        "was written. Regenerating per-row scores would require re-running "
        "build_rows()/score_family_by_checkpoint() against "
        "data/domains/wnba/linescores.parquet, i.e. RE-RUNNING THE GATE, which "
        "this task says not to force. Recorded as an honest UNAVAILABLE rather "
        "than fabricating or re-deriving rows."
    )


# Declarative registry: one entry per ADOPTED/SHIPPED layer found in the search.
REGISTRY: list[ReprocessClient] = [
    ReprocessClient(
        name="wnba_anchored_linescore_blend",
        metric="brier",
        committed_verdict_path=_REPO / "data" / "domains" / "wnba" / "hist_blend_crosscorpus_check.json",
        tolerance=1e-6,
        rows_source=None,
        unavailable_reason=_wnba_anchored_unavailable_reason(),
    ),
]


def run_client(client: ReprocessClient) -> dict:
    """Run one registered client through the harness, or record UNAVAILABLE."""
    if client.rows_source is None:
        return {
            "client": client.name,
            "status": "UNAVAILABLE",
            "reason": client.unavailable_reason,
        }
    if not client.committed_verdict_path.exists():
        return {
            "client": client.name,
            "status": "UNAVAILABLE",
            "reason": f"committed verdict path missing: {client.committed_verdict_path}",
        }
    df = client.rows_source()
    try:
        verdict = run_harness(df, metric=client.metric)
    except SchemaError as e:
        return {"client": client.name, "status": "UNAVAILABLE", "reason": f"SchemaError: {e}"}

    replayed = verdict_to_dict(verdict)
    committed = json.loads(client.committed_verdict_path.read_text(encoding="ascii"))

    # Compare pooled diagnostic delta as the single scalar checkpoint.
    replay_delta = replayed["pooled_diagnostic"]["vs_base"]["delta"]
    committed_delta = committed.get("pooled_diagnostic", {}).get("vs_base", {}).get("delta")
    if committed_delta is None:
        return {
            "client": client.name,
            "status": "UNAVAILABLE",
            "reason": "committed verdict has no pooled_diagnostic.vs_base.delta to compare against",
        }
    max_abs_diff = abs(replay_delta - committed_delta)
    matched = max_abs_diff <= client.tolerance
    return {
        "client": client.name,
        "status": "RAN",
        "matched": matched,
        "max_abs_diff": max_abs_diff,
        "tolerance": client.tolerance,
    }


def run_all_clients(registry: list[ReprocessClient] = REGISTRY) -> list[dict]:
    return [run_client(c) for c in registry]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run all registered reprocess-harness clients")
    parser.add_argument("--out", default=str(_REPO / "data" / "domains" / "reprocess_clients_report.json"))
    args = parser.parse_args(argv)

    results = run_all_clients()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=1), encoding="ascii")

    for r in results:
        print(f"{r['client']}: {r['status']}" + (f" matched={r.get('matched')} max_abs_diff={r.get('max_abs_diff')}" if r["status"] == "RAN" else f" reason={r.get('reason')}"))
    print(f"wrote report to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
