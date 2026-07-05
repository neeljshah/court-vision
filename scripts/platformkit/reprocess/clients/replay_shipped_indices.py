"""Reprocess-harness client registry for shipped gate exports (wave-30 lane 8,
extended wave-45 lane: reprocess-register; wave-47: harness-rmse-mode gap
closure).

The reprocess harness (reprocess_harness.py) is proven to 1e-6. This module
enumerates gate-exported row parquets and, for each one, either:
  (a) registers a runnable client (name, rows_source callable, metric,
      committed verdict path, tolerance, optional custom comparator) that the
      harness can replay, or
  (b) records an honest UNAVAILABLE with a reason, when rows are schema-
      incompatible with the harness, no committed verdict exists to replay
      against, or the per-row scores were never persisted.

POLICY (Fable-ratified, wave-45): REJECT/NOT_TESTABLE verdicts get clients
too, not just ADOPT/SHIP -- replaying a REJECT verifies the honest negative
stays reproducible as the harness/code evolves. A schema/verdict-shape
mismatch is NEVER coerced -- it is recorded as UNAVAILABLE with a reason.

WAVE-30 SEARCH (original, ADOPT/SHIP only): grepped ADOPT/SHIP verdict
strings across .planning/*.md and data/**/*.json -> one hit, WNBA anchored
blend (registered below, UNAVAILABLE -- per-row scores never persisted).

WAVE-45 SEARCH (newest gate exports named in that task):
  - data/domains/mlb/umpire_totals_gate_rows.parquet       -> was UNAVAILABLE
    (harness had no RMSE metric path). SEE WAVE-47 -- now REGISTERED.
  - data/domains/basketball_nba/positional_weight_rows.parquet -> REGISTERED
    (metric=rho, per-fold comparator; verdict=NOT_TESTABLE).
  - data/domains/wnba/elo_refresh_harness_rows.parquet     -> REGISTERED
    (metric=brier, per-candidate-corpus comparator; verdict=REJECT).
  - data/domains/basketball_nba/ingame_hypothesis_{hot_night,scheme_fit}_
    {2024-25,2025-26}_rows.parquet (4 files) -> UNAVAILABLE, schema mismatch
    (in-game-state columns, no corpus_id/fold_id/p_variant/p_base; deeper
    reason confirmed wave-47: the gated/train-fit predictions in the
    committed verdict were never persisted per-row, only the plain p_live/
    cond_prior columns were -- reproducing brier_base/brier_prior would
    require RE-FITTING the fold's TRAIN-only prior surface, not a rename).
  - data/domains/tennis/h3_playstyle_rows.parquet          -> UNAVAILABLE;
    wave-47 found the committed verdict DOES exist (data/frontend/ingame/
    playstyle_gate_verdict.json, not under data/domains/tennis/ as first
    searched) but the exported rows' p_base column is the gate's plain
    sigmoid base model, NOT the H0 arm's own detail-model prediction the
    committed brier_h0 scores -- H0's per-row predictions were never
    exported (only H1's), so replay still cannot reach brier_h0 without
    re-running the gate. Reason text corrected wave-47 to name this exact
    field gap instead of "no committed verdict exists".

WAVE-47 (harness-rmse-mode lane): added --metric rmse to reprocess_harness
(reprocess_harness_rmse.py); mlb_umpire_totals_gate now REGISTERED (was
UNAVAILABLE) via umpire_totals_rows()/compare_umpire_totals in
replay_shipped_indices_io.py -- a column RENAME + fold_id derived with the
gate's OWN BURN_IN=300/N_FOLDS=3 constants (verified byte-exact fold sizes
1521/1520/1520), no re-scoring, replay matches committed per-fold RMSE
within 1e-6 (actual max_abs_diff=0.0). The two nba_ingame_hypothesis clients
and tennis_h3_playstyle were re-checked for a field-paths mapping fix per
the task; both genuinely require re-running gate machinery (train-refit /
missing H0 export respectively), so they stay honest UNAVAILABLE with a
corrected, more precise reason (see above) rather than a coerced RAN.

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
from scripts.platformkit.reprocess.clients.replay_shipped_indices_io import (
    compare_elo_refresh,
    compare_positional_weight,
    compare_umpire_totals,
    elo_refresh_rows,
    h3_playstyle_unavailable_reason,
    ingame_hypothesis_unavailable_reason,
    positional_weight_rows,
    umpire_totals_rows,
)

_REPO = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class ReprocessClient:
    """One registered gate-exported layer wired to the reprocess harness."""
    name: str
    metric: str  # "brier" | "rho"
    committed_verdict_path: Path
    tolerance: float
    rows_source: Optional[Callable[[], pd.DataFrame]]  # None => UNAVAILABLE
    unavailable_reason: Optional[str] = None
    # Optional custom comparator for committed verdicts that don't carry a
    # pooled_diagnostic.vs_base.delta shape (fn(client, committed_dict) -> result dict).
    # Default (None) uses the pooled-diagnostic scalar comparison below.
    compare_fn: Optional[Callable[["ReprocessClient", dict], dict]] = None


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


# Declarative registry: one entry per gate-exported layer found in the search.
REGISTRY: list[ReprocessClient] = [
    ReprocessClient(
        name="wnba_anchored_linescore_blend",
        metric="brier",
        committed_verdict_path=_REPO / "data" / "domains" / "wnba" / "hist_blend_crosscorpus_check.json",
        tolerance=1e-6,
        rows_source=None,
        unavailable_reason=_wnba_anchored_unavailable_reason(),
    ),
    ReprocessClient(
        name="nba_positional_weight",
        metric="rho",
        committed_verdict_path=_REPO / "data" / "domains" / "basketball_nba" / "positional_weight_verdict.json",
        tolerance=1e-6,
        rows_source=positional_weight_rows,
        compare_fn=compare_positional_weight,
    ),
    ReprocessClient(
        name="wnba_elo_refresh",
        metric="brier",
        committed_verdict_path=_REPO / "data" / "domains" / "wnba" / "elo_refresh_verdict.json",
        tolerance=1e-6,
        rows_source=elo_refresh_rows,
        compare_fn=compare_elo_refresh,
    ),
    ReprocessClient(
        name="mlb_umpire_totals_gate",
        metric="rmse",
        committed_verdict_path=_REPO / "data" / "domains" / "mlb" / "umpire_totals_gate_verdict.json",
        tolerance=1e-6,
        rows_source=umpire_totals_rows,
        compare_fn=compare_umpire_totals,
    ),
    ReprocessClient(
        name="nba_ingame_hypothesis_hot_night",
        metric="brier",
        committed_verdict_path=_REPO / "data" / "domains" / "basketball_nba" / "ingame_hypothesis_hot_night.json",
        tolerance=1e-6,
        rows_source=None,
        unavailable_reason=ingame_hypothesis_unavailable_reason("hot_night"),
    ),
    ReprocessClient(
        name="nba_ingame_hypothesis_scheme_fit",
        metric="brier",
        committed_verdict_path=_REPO / "data" / "domains" / "basketball_nba" / "ingame_hypothesis_scheme_fit.json",
        tolerance=1e-6,
        rows_source=None,
        unavailable_reason=ingame_hypothesis_unavailable_reason("scheme_fit"),
    ),
    ReprocessClient(
        name="tennis_h3_playstyle",
        metric="brier",
        # Found wave-47 (was reported as not existing anywhere under
        # data/domains/tennis/**): the actual committed verdict lives at
        # data/frontend/ingame/playstyle_gate_verdict.json. Still UNAVAILABLE
        # -- see h3_playstyle_unavailable_reason() for the field-gap reason.
        committed_verdict_path=_REPO / "data" / "frontend" / "ingame" / "playstyle_gate_verdict.json",
        tolerance=1e-6,
        rows_source=None,
        unavailable_reason=h3_playstyle_unavailable_reason(),
    ),
]


def run_client(client: ReprocessClient) -> dict:
    """Run one registered client through the harness, or record UNAVAILABLE.

    Two comparison paths:
      - client.compare_fn set: committed verdict has a bespoke shape (per-fold,
        per-candidate-corpus, etc); the comparator owns rows_source + harness
        invocation + the scalar(s) it diffs against. Used by clients whose
        committed JSON does not carry a pooled_diagnostic.vs_base.delta.
      - client.compare_fn None: default path, diffs the harness's
        pooled_diagnostic.vs_base.delta against the same path in committed.
    """
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
    committed = json.loads(client.committed_verdict_path.read_text(encoding="ascii"))

    if client.compare_fn is not None:
        result = client.compare_fn(client, committed)
        return {"client": client.name, **result}

    df = client.rows_source()
    try:
        verdict = run_harness(df, metric=client.metric)
    except SchemaError as e:
        return {"client": client.name, "status": "UNAVAILABLE", "reason": f"SchemaError: {e}"}

    replayed = verdict_to_dict(verdict)

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
