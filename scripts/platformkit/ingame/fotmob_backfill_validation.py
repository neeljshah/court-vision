"""scripts.platformkit.ingame.fotmob_backfill_validation -- LANE 2 item 3:
run GATE A's judge on the BACKFILL-VALIDATION rows (enrichment_rows_soccer.
rows_fn_backfill), writing a VALIDATION verdict to a SEPARATE file --
data/domains/soccer_intl/enrichment_gate_validation.json -- NEVER the forward
verdict file (data/domains/soccer_intl/enrichment_gate_verdict.json, owned by
ingame_enrichment_gates.run_gate_a and scored on forward-only ticks per its
pre-registration discipline).

WHY A SEPARATE RUNNER, NOT run_gate_a(rows_fn=rows_fn_backfill): run_gate_a
hard-codes its output path via _verdict_out("soccer_intl") to the FORWARD
verdict filename. Reusing it here would silently overwrite (or risk
overwriting) the pre-registered forward verdict with retrospective/backfilled
numbers -- exactly the pooling this lane's brief forbids. This module reuses
judge_enrichment (the shared Brier-delta core) directly and writes its own
doc + path, so the two verdict files can never collide.

HONESTY CAVEAT (embedded in the written doc, per the LANE 2 brief):
reconstructed as-of xG assumes the finished match's recorded shot minutes are
accurate and ignores any post-hoc xG revisions FotMob may apply after a match
settles; the xG conditioning itself is FIXED-FORM (unfitted, see
enrichment_rows_soccer._xg_conditioned_prob) -- this is the first WORSE/MATCH
datapoint on a real labeled corpus, not a forward-gate result, and
edge_claimed is always False.

INVARIANTS: platformkit-only; <=300 LOC; ASCII only; no network (reads local
jsonl via enrichment_rows_soccer); no data/registry write; no flag flip;
never raises.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_fotmob_backfill_validation.py -q
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.ingame.ingame_enrichment_gates import judge_enrichment

_REPO_ROOT = Path(__file__).resolve().parents[3]

VALIDATION_HYPOTHESIS = (
    "conditioning the soccer in-play model on RECONSTRUCTED as-of xG state "
    "(xg_diff, sot_diff) from FINISHED-match shotmaps improves Brier vs OUTCOME "
    "over the score+minute-only baseline, on the already-captured soccer_intl "
    "corpus (md5-parity halves); this is a VALIDATION read on a labeled "
    "historical corpus, NOT a forward-gate result and never pooled with one"
)

HONESTY_CAVEAT = (
    "Reconstructed as-of xG assumes the finished match's recorded shot minutes "
    "are accurate at capture time and ignores any post-hoc xG model revisions "
    "FotMob may apply after settlement. The xG conditioning is fixed-form "
    "(unfitted, logit-space nudge) -- not a trained model. Brier/probability "
    "space only; no $/roi/pnl field; edge_claimed is always False; this "
    "verdict never auto-wires into any live decision path."
)


def _validation_out(sport: str = "soccer_intl") -> Path:
    return _REPO_ROOT / "data" / "domains" / sport.lower() / "enrichment_gate_validation.json"


def _atomic_write(path: Path, doc: Dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
        os.replace(str(tmp), str(path))
    except Exception:  # noqa: BLE001 -- a write failure must not raise out of a validation pass
        pass


def run_backfill_validation(rows_fn: Optional[Callable[[], List[Dict[str, Any]]]] = None,
                            verdict_out: Optional[Path] = None) -> Dict[str, Any]:
    """Judge the backfill-validation rows and write a VALIDATION verdict doc.
    *rows_fn* defaults to enrichment_rows_soccer.rows_fn_backfill (injectable
    for hermetic tests). Never raises -- a producer failure yields an honest
    INSUFFICIENT_FORWARD-shaped judged doc with n_games=0."""
    if rows_fn is None:
        from scripts.platformkit.ingame.enrichment_rows_soccer import rows_fn_backfill as rows_fn

    try:
        rows = rows_fn()
    except Exception as exc:  # noqa: BLE001
        rows = []
        judged = {"overall_verdict": "INSUFFICIENT_FORWARD", "half0": None, "half1": None,
                  "n_games": 0, "n_ticks": 0, "error": str(exc)}
    else:
        # Every row from rows_fn_backfill carries provenance="backfill_validation";
        # guard against an accidental live-provenance row ever entering this
        # validation judge (would be a pooling bug, not a data issue -- drop it
        # rather than silently mixing corpora).
        clean_rows = [r for r in rows if r.get("provenance") == "backfill_validation"]
        judged = judge_enrichment(clean_rows)

    doc = {
        "component": "fotmob_backfill_validation", "gate": "A_soccer_xg_VALIDATION",
        "sport": "soccer_intl", "provenance": "backfill_validation",
        "hypothesis": VALIDATION_HYPOTHESIS,
        "verdict": judged["overall_verdict"], "half0": judged.get("half0"),
        "half1": judged.get("half1"), "n_games": judged.get("n_games", 0),
        "n_ticks": judged.get("n_ticks", 0),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "honest_note": HONESTY_CAVEAT,
        "edge_claimed": False,
    }
    out_path = Path(verdict_out) if verdict_out is not None else _validation_out()
    _atomic_write(out_path, doc)
    return doc


def main() -> None:
    doc = run_backfill_validation()
    print("fotmob_backfill_validation | verdict=%s n_games=%d n_ticks=%d" % (
        doc["verdict"], doc["n_games"], doc["n_ticks"]))
    print("  validation file: %s" % _validation_out())
    print("NOTE: Brier/probability space only; retrospective reconstruction; no edge claimed.")


if __name__ == "__main__":
    main()


__all__ = [
    "VALIDATION_HYPOTHESIS", "HONESTY_CAVEAT", "run_backfill_validation", "_validation_out",
]
