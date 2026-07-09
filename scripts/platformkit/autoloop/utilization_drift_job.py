"""scripts.platformkit.autoloop.utilization_drift_job -- watermark-gated
re-run of the cross-sport stat-utilization census (autoloop job #8),
surfacing NEWLY dark (UNUSED) columns as they appear. A report-only
companion to scripts.platformkit.data_frontier.utilization_audit, which was
otherwise only ever run by hand. Never reimplements the census; wraps
build_inventory() verbatim and only decides WHEN to call it, then diffs the
fresh rows against the prior saved snapshot.

WATERMARK = newest mtime across that sport's SPORT_CORPORA files
(utilization_audit.SPORT_CORPORA). No watermark yet -> writes a baseline
snapshot and reports nothing (nothing is "new" against an absent prior,
mirrors replication_watch's first-sight convention). A column newly UNUSED
(absent or USED in the prior snapshot) queues one human_queue row per sport;
a column flipping UNUSED->USED needs no eyes and is not reported.

INVARIANTS: report-only (no promotion, no flag, no gate); writes only the
existing data/frontend/ops/<sport>_stat_utilization.json output path.

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autoloop/test_utilization_drift_job.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.data_frontier.utilization_audit import SPORT_CORPORA, build_inventory

_REPO = Path(__file__).resolve().parents[3]
_OUT_DIR = _REPO / "data" / "frontend" / "ops"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _newest_corpus_mtime(sport: str, corpora: Optional[Dict[str, Any]]) -> Optional[float]:
    reg = corpora if corpora is not None else SPORT_CORPORA
    mtimes = [(_REPO / rel).stat().st_mtime for rel, _kind in reg.get(sport, []) if (_REPO / rel).is_file()]
    return max(mtimes) if mtimes else None


def _load_prior_status(out_path: Path) -> Dict[str, str]:
    if not out_path.is_file():
        return {}
    try:
        rows = json.loads(out_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- unreadable prior treated as absent, never a crash
        return {}
    return {r["column"]: r.get("status") for r in rows if "column" in r}


def run_utilization_drift(watermarks: Dict[str, Any], *,
                          sports: Optional[List[str]] = None,
                          out_dir: Optional[Path] = None,
                          corpora: Optional[Dict[str, Any]] = None,
                          build_fn: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
                          queue_fn: Optional[Callable[[Dict[str, Any]], Any]] = None
                          ) -> Dict[str, Any]:
    """Per sport: iff any corpus file is newer than the stored watermark,
    rebuild the utilization inventory, diff newly-UNUSED columns against the
    prior saved snapshot, queue one report row, then overwrite the snapshot.
    Isolated per sport -- one raising never blocks the others."""
    reg_sports = sports if sports is not None else sorted(SPORT_CORPORA)
    out_root = Path(out_dir) if out_dir is not None else _OUT_DIR
    builder = build_fn or build_inventory
    out: Dict[str, Any] = {}
    for sport in reg_sports:
        key = "M08_utilization_drift__%s" % sport
        mtime = _newest_corpus_mtime(sport, corpora)
        prior_wm = float((watermarks.get(key) or {}).get("corpus_mtime", -1.0))
        if mtime is None or mtime <= prior_wm:
            out[sport] = {"status": "skipped", "corpus_mtime": mtime, "watermark": prior_wm}
            continue
        out_path = out_root / ("%s_stat_utilization.json" % sport)
        try:
            prior_status = _load_prior_status(out_path)
            rows = builder(sport)
            new_unused = sorted(r["column"] for r in rows
                                if r.get("status") == "UNUSED" and prior_status.get(r["column"]) != "UNUSED")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
            if prior_status and new_unused and queue_fn is not None:
                queue_fn({"kind": "NEW_DARK_COLUMNS", "ts": _now_iso(), "sport": sport,
                         "columns": new_unused,
                         "note": "surfacing only -- wiring a dark column is a human/Fable call"})
            watermarks[key] = {"corpus_mtime": mtime, "last_run_ts": _now_iso()}
            out[sport] = {"status": "ran", "total_columns": len(rows),
                         "new_unused": new_unused if prior_status else []}
        except Exception as exc:  # noqa: BLE001 -- one sport failing must not block the others
            out[sport] = {"status": "error", "error": str(exc)[:200]}
    return out


__all__ = ["run_utilization_drift"]
