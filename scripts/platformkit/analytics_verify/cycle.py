"""scripts.platformkit.analytics_verify.cycle -- one autoloop tick wiring the
four analytics_verify producers (sentinel, regrader, contradiction,
attribution) into a single cheap step + a digest the meta improvement_finder
reads to emit DECAYED_CLAIM / DISCREPANT_STAT / CLAIM_CONTRADICTION candidates.

Read-only over source ledgers; each producer already writes its own report
file (this module does not duplicate that). Every producer is isolated in its
own try/except so one failure never blocks the others or the autoloop tick.
edge_claimed is always False -- calibration/CLV/units language only.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    tests/platformkit/analytics_verify/test_cycle.py -q
CLI:
  cd /c/Users/neelj/nba-ai-system && python -m scripts.platformkit.analytics_verify.cycle
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
OUT_PATH = _ROOT / "data" / "cache" / "analytics_verify" / "analytics_verify_digest.json"

# contradiction.py streams whole family files; cap it for a per-cycle tick
# (the standalone CLI keeps its own larger default).
CYCLE_MAX_LINES_PER_FAMILY = 5000

HONEST_NOTE = (
    "MEASUREMENT-ONLY autoloop tick over analytics_verify's own producers. "
    "No dollars, no ROI, no edge. Contradiction conflicts are DESCRIPTIVE "
    "consistency signals, not a market edge."
)


def _run_producer(name: str, fn) -> Dict[str, Any]:
    try:
        result = fn()
        return {"status": "ok", "summary": result}
    except Exception as exc:  # noqa: BLE001 -- one producer's failure must never block the rest
        return {"status": "error", "error": str(exc)[:200]}


def _run_sentinel() -> Dict[str, Any]:
    from scripts.platformkit.analytics_verify import sentinel
    report = sentinel.build_report()
    sentinel.write_report(report)
    return {"overall": report["overall"], "n_verified": report["n_verified"],
            "n_discrepant": report["n_discrepant"], "n_stale": report["n_stale"],
            "n_uncheckable": report["n_uncheckable"]}


def _run_regrader() -> Dict[str, Any]:
    from scripts.platformkit.analytics_verify import regrader
    snap = regrader.run()
    return {"n_eligible": snap["n_eligible"], "n_decayed": len(snap["decayed_cards"]),
            "insufficient_cards": snap["insufficient_cards"], "survival": snap["survival"]}


def _run_contradiction() -> Dict[str, Any]:
    from scripts.platformkit.analytics_verify import contradiction
    report = contradiction.run(max_lines=CYCLE_MAX_LINES_PER_FAMILY)
    worst_family, worst_score = None, None
    for fam, rec in report.get("by_family_consistency", {}).items():
        score = rec.get("consistency")
        if score is not None and (worst_score is None or score < worst_score):
            worst_family, worst_score = fam, score
    return {"n_claims": report["n_claims"], "n_conflicts": sum(report["n_conflicts_by_kind"].values()),
            "worst_family": worst_family, "worst_family_consistency": worst_score}


def _run_attribution() -> Dict[str, Any]:
    from scripts.platformkit.analytics_verify import attribution
    res = attribution.run()
    return {"settled_bets": res["settled_bets"], "rows_appended": res["rows_appended"]}


def _atomic_write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, default=str)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def run_cycle() -> Dict[str, Any]:
    """Run the four analytics_verify producers in-process; write the digest."""
    producers = {
        "sentinel": _run_producer("sentinel", _run_sentinel),
        "regrader": _run_producer("regrader", _run_regrader),
        "contradiction": _run_producer("contradiction", _run_contradiction),
        "attribution": _run_producer("attribution", _run_attribution),
    }

    sent = producers["sentinel"].get("summary") or {}
    regr = producers["regrader"].get("summary") or {}
    contr = producers["contradiction"].get("summary") or {}

    digest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "edge_claimed": False,
        "honest_note": HONEST_NOTE,
        "producers": producers,
        "signals": {
            "n_decayed_cards": regr.get("n_decayed", 0),
            "n_discrepant_stats": sent.get("n_discrepant", 0),
            "n_contradiction_conflicts": contr.get("n_conflicts", 0),
            "worst_family": contr.get("worst_family"),
        },
    }
    _atomic_write_json(OUT_PATH, digest)
    return digest


# --- improvement_finder glue -------------------------------------------------
# Reads the underlying artifacts directly (not just the digest) so candidates
# survive even if a given cycle tick errored on one producer. Absent files ->
# empty list, never a crash. Returns plain dicts (finder builds its own
# Candidate dataclass) to avoid a circular import.
FINDER_CATEGORIES = ("DECAYED_CLAIM", "DISCREPANT_STAT", "CLAIM_CONTRADICTION")


def _load(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- missing/corrupt artifact -> no candidates, never a crash
        return {}


def scan_finder_candidates() -> List[Dict[str, Any]]:
    from scripts.platformkit.analytics_verify import regrader as _regr
    from scripts.platformkit.analytics_verify import sentinel as _sent

    out: List[Dict[str, Any]] = []

    survival = _load(_regr.SURVIVAL_JSON)
    for card in survival.get("decayed_cards", [])[:25]:
        cid = card.get("card_id", "unknown")
        out.append({
            "id": "DECAYED_" + str(cid)[:40], "category": "DECAYED_CLAIM",
            "sport": "platform", "what": f"card {cid} decayed: {card.get('reason', '')}",
            "where": "data/cache/analytics_verify/claim_survival.json",
            "expected_outcome": "post-validation CLV decayed below margin; review demotion proposal",
            "gate_action": "inspect regrade_ledger.jsonl row; demotion is a proposal, not auto-applied",
            "priority": 78.0,
        })

    sent = _load(_sent.OUT_PATH)
    for chk in sent.get("checks", []):
        if chk.get("verdict") != "DISCREPANT":
            continue
        name = chk.get("name", "unknown")
        out.append({
            "id": "DISCREPANT_" + str(name)[:40], "category": "DISCREPANT_STAT",
            "sport": "platform", "what": f"served stat diverges from raw-ledger recompute: {name}",
            "where": "data/cache/analytics_verify/sentinel_report.json",
            "expected_outcome": "reconcile served JSON with independently recomputed value",
            "gate_action": "diff served vs recomputed field; fix the writer, not the sentinel",
            "priority": 82.0,
        })

    contr = _load(_ROOT / "data" / "cache" / "analytics_verify" / "contradiction_report.json")
    for conflict in contr.get("conflicts", [])[:25]:
        fam_a, fam_b = conflict.get("family_a", "?"), conflict.get("family_b", "?")
        kind = conflict.get("kind", "CONFLICT")
        out.append({
            "id": "CONTRA_" + f"{fam_a}_{fam_b}_{kind}"[:40], "category": "CLAIM_CONTRADICTION",
            "sport": "platform", "what": f"{kind} between {fam_a} and {fam_b}: {conflict.get('detail', '')}",
            "where": "data/cache/analytics_verify/contradiction_report.json",
            "expected_outcome": "descriptive consistency gap; no market or edge implied",
            "gate_action": "reconcile the two claim families or document the divergence reason",
            "priority": 65.0,
        })

    return out


def main() -> int:
    digest = run_cycle()
    sig = digest["signals"]
    statuses = {k: v["status"] for k, v in digest["producers"].items()}
    print(
        "analytics_verify_cycle: producers=%s decayed=%d discrepant=%d "
        "conflicts=%d worst_family=%s -> %s"
        % (statuses, sig["n_decayed_cards"], sig["n_discrepant_stats"],
           sig["n_contradiction_conflicts"], sig["worst_family"], OUT_PATH)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
