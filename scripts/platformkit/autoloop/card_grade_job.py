"""scripts.platformkit.autoloop.card_grade_job -- autonomous card mine+grade.

USER DIRECTIVE 2026-07-15: 10,000s of cards, validated as autonomously as
possible. Each autoloop cycle this job (a) tops up the mechanical grid via
card_miner_bulk.mine() (idempotent -- registered cells are skipped), then
(b) re-runs card_grade_bulk.grade_bulk() whenever the grade corpus GREW since
the stored watermark (total ingame_grade byte size), so every new settled
game immediately pushes more cards toward a verdict.

Watermark-gated like every job in maintenance_templates._JOB_TABLE; failures
degrade to a status dict, never raise. PAPER; probability units; no $/edge
claims -- REJECTED is the expected majority verdict and that is the gate
working.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autoloop/test_card_grade_job.py -q
"""
from __future__ import annotations

import glob
import os
from pathlib import Path
from typing import Any, Dict

_REPO = Path(__file__).resolve().parents[3]
GRADE_GLOB = str(_REPO / "data" / "cache" / "ingame_grade" / "*" / "*.jsonl")
_WM_KEY = "card_grade_corpus_bytes"


def _corpus_bytes(pattern: str = GRADE_GLOB) -> int:
    total = 0
    for p in glob.glob(pattern):
        try:
            total += os.path.getsize(p)
        except OSError:
            continue
    return total


def run_card_grade(watermarks: Dict[str, Any]) -> Dict[str, Any]:
    """Mine missing grid cells, then bulk-grade when the corpus grew."""
    out: Dict[str, Any] = {"edge_claimed": False}
    try:
        from scripts.platformkit.claims.card_miner_bulk import mine
        res = mine()
        out["mine"] = {k: res.get(k) for k in ("n_open", "n_queued", "n_rejected")}
    except Exception as exc:  # noqa: BLE001
        out["mine"] = {"status": "error", "error": str(exc)[:200]}
    now_bytes = _corpus_bytes()
    seen = int(watermarks.get(_WM_KEY, 0) or 0)
    if now_bytes <= seen:
        out["grade"] = {"status": "skipped", "reason": "corpus unchanged",
                        "corpus_bytes": now_bytes}
        return out
    try:
        from scripts.platformkit.claims.card_grade_bulk import grade_bulk
        res = grade_bulk()
        out["grade"] = {"counts": res.get("counts"), "n_cards": res.get("n_cards"),
                        "n_rows": res.get("n_rows"),
                        "n_validated": len(res.get("validated_card_ids", []))}
        watermarks[_WM_KEY] = now_bytes  # only advance on a successful pass
    except Exception as exc:  # noqa: BLE001
        out["grade"] = {"status": "error", "error": str(exc)[:200]}
    return out


__all__ = ["run_card_grade", "GRADE_GLOB"]
