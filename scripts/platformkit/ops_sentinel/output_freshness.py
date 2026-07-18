"""scripts.platformkit.ops_sentinel.output_freshness -- SELF-HEALING VISIBILITY for
the readiness=NONE daemons (m19-m27).

THE GAP THIS CLOSES
--------------------
m19-m27 all use readiness=NONE in supervisor.stack_specs (ready as soon as the
process is alive -- a daily/slow-batch loop has no useful HEARTBEAT freshness
window). That means a WEDGED tick -- process still running, but its scoreboard /
verdict / status file silently stopped advancing -- is INVISIBLE: the supervisor's
own health view still reads OK. This sentinel closes that gap by checking each
daemon's OWN declared output artifact's mtime against its expected cadence and
writing an honest GREEN/RED verdict per daemon to ops/output_freshness.json.

NO RESTART AUTHORITY: this module is read-only. It never kills or restarts a
process (that stays the supervisor's + heartbeat_reaper's job) -- it only makes a
wedged tick VISIBLE so a human or the autonomy monitor can act on it.

TABLE-DRIFT GUARD: the per-file test asserts TABLE's keys match EXACTLY the set of
readiness=NONE ProcSpec names in supervisor.stack_specs.base_specs(), so a newly
added readiness=NONE daemon WITHOUT a sentinel row fails the test instead of
silently going unmonitored forever.

FOLLOW-UP (not done here): wire merge_freshness_into_services into the m5 autonomy
monitor's compose path (mirrors the existing, also-not-yet-wired
autonomy.reaper_status_bridge.merge_reaper_into_services pattern). Deferred because
both status_composer.py and autonomy_monitor_runner.py already sit at the 300-LOC
cap -- wiring needs its own trim-and-wire pass, not bundled into this build.

HONESTY: read-only; no $ field; no flag flip; no data/registry/ write; never raises.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ops_sentinel/test_output_freshness.py -q
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional

_REPO = Path(__file__).resolve().parents[3]
_OPS = _REPO / "data" / "frontend" / "ops"

GREEN = "GREEN"
RED = "RED"

STATUS_PATH = _OPS / "output_freshness.json"
COMPONENT = "m_output_freshness"


class _Entry(NamedTuple):
    path: Path
    max_age_sec: float


# daemon name -> (its declared output artifact, expected max staleness before RED).
# max_age_sec ~= 2.2x each daemon's own --interval (supervisor.stack_specs) plus the
# same house margin already used for HEARTBEAT ReadinessSpecs elsewhere in that file
# (e.g. a 900s cadence -> fresh_sec=1980 for m18/m25/m27; a 1800s cadence -> 3900 for
# m17; a 3600s cadence -> 7800 for m7/m8) -- reused verbatim where the cadence matches.
TABLE: Dict[str, _Entry] = {
    "m19_asof_reclaim": _Entry(
        _REPO / "data" / "frontend" / "ceiling_reclaim_scoreboard.jsonl", 194400.0),
    "m20_ingame_clv_verdict": _Entry(_OPS / "ingame_clv_verdict.json", 1320.0),
    "m21_ingame_baseout_gate": _Entry(_OPS / "ingame_baseout_gate.json", 7800.0),
    "m22_best_price_scan": _Entry(_OPS / "best_price_scan.json", 540.0),
    "m23_scraped_line_gaps": _Entry(_OPS / "scraped_line_gaps.json", 540.0),
    "m24_ingame_placement_funnel": _Entry(_OPS / "ingame_placement_funnel.json", 660.0),
    "m25_ingame_outcome_verdict": _Entry(_OPS / "ingame_outcome_verdict.json", 1980.0),
    "m26_ingame_segment_trust": _Entry(_OPS / "ingame_segment_trust.json", 3900.0),
    "m27_ingame_paper_settle": _Entry(_OPS / "ingame_paper_settle_status.json", 1980.0),
}


def check_one(name: str, entry: _Entry, *, now: Optional[float] = None) -> Dict[str, Any]:
    """GREEN/RED verdict for one daemon's declared output artifact. Never raises."""
    ts = float(now) if now is not None else time.time()
    row: Dict[str, Any] = {"name": name, "path": str(entry.path),
                           "max_age_sec": entry.max_age_sec}
    try:
        p = Path(entry.path)
        if not p.exists():
            row.update(status=RED, age_sec=None, reason="missing")
            return row
        age = ts - p.stat().st_mtime
        if age < 0:
            age = 0.0  # clock skew must never manufacture a negative age
        row["age_sec"] = round(age, 1)
        if age > entry.max_age_sec:
            row.update(status=RED, reason="stale")
        else:
            row.update(status=GREEN, reason=None)
    except Exception as exc:  # noqa: BLE001 -- an unreadable path is RED, not a crash
        row.update(status=RED, age_sec=None, reason="error:%s" % str(exc)[:80])
    return row


def check_all(table: Optional[Dict[str, _Entry]] = None,
              *, now: Optional[float] = None) -> List[Dict[str, Any]]:
    """GREEN/RED rows for every daemon in *table* (default: the real TABLE)."""
    tbl = table if table is not None else TABLE
    ts = float(now) if now is not None else time.time()
    return [check_one(name, entry, now=ts) for name, entry in sorted(tbl.items())]


def write_status(rows: List[Dict[str, Any]], *, out_path: Optional[Path] = None,
                 now: Optional[float] = None) -> bool:
    """Atomically write the freshness rows (tmp + os.replace). Never raises.

    STALE-INPUT VISIBILITY (go-live hardening finding #4, 2026-07-17): this
    artifact was previously recomputed+written every tick regardless of whether
    any of the CHECKED inputs (the m19-m27 output files rows[] reports on) had
    actually advanced since the LAST time this artifact itself was written --
    silently masking a scenario where the sentinel keeps re-deriving the same
    verdict from unchanged source data. newest_input_mtime (derived from each
    row's own age_sec) is now stamped into the artifact, and stale_inputs is
    True when that newest input is OLDER than this artifact's own previous
    generated_at -- i.e. nothing checked this cycle has changed since the prior
    write. A missing/unreadable previous artifact never sets stale_inputs.
    """
    try:
        path = Path(out_path) if out_path is not None else STATUS_PATH
        ts = float(now) if now is not None else time.time()
        n_red = sum(1 for r in rows if r.get("status") == RED)
        input_mtimes = [ts - r["age_sec"] for r in (rows or [])
                        if isinstance(r, dict) and isinstance(r.get("age_sec"), (int, float))]
        newest_input_mtime = max(input_mtimes) if input_mtimes else None
        prev_generated_at = None
        try:
            if path.exists():
                prev_generated_at = json.loads(
                    path.read_text(encoding="ascii")).get("generated_at")
        except Exception:  # noqa: BLE001 -- an unreadable prior write is not stale_inputs
            prev_generated_at = None
        stale_inputs = bool(
            newest_input_mtime is not None
            and isinstance(prev_generated_at, (int, float))
            and newest_input_mtime < prev_generated_at)
        doc = {
            "generated_at": ts, "component": COMPONENT, "rows": list(rows or []),
            "n_daemons": len(rows or []), "n_red": n_red,
            "overall": RED if n_red else GREEN,
            "newest_input_mtime": newest_input_mtime,
            "stale_inputs": stale_inputs,
            "honest_note": ("output-freshness only; NO restart authority; read-only; "
                            "no $ field; a wedged (alive-but-silent) daemon shows RED "
                            "here even though the supervisor still sees it as running. "
                            "stale_inputs=true means none of this cycle's checked inputs "
                            "have advanced since this artifact's own previous write."),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=True, indent=2, sort_keys=True),
                       encoding="ascii")
        os.replace(str(tmp), str(path))
        return True
    except Exception:  # noqa: BLE001 -- write must never crash the caller's tick
        return False


def load_status(*, path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Best-effort read of the rows[] list. Missing/bad file -> [] (unknown, never
    treated as all-green). Never raises."""
    try:
        p = Path(path) if path is not None else STATUS_PATH
        if not p.exists():
            return []
        doc = json.loads(p.read_text(encoding="ascii"))
        rows = doc.get("rows")
        return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    except Exception:  # noqa: BLE001
        return []


def merge_freshness_into_services(services: List[Dict[str, Any]],
                                  freshness_rows: List[Dict[str, Any]],
                                  ) -> List[Dict[str, Any]]:
    """Degrade-only merge (mirrors autonomy.reaper_status_bridge.
    merge_reaper_into_services): a RED freshness row degrades the matching
    services[] entry (matched by name); GREEN/unknown never upgrades an existing
    "down"/"degraded" severity. Not yet called from the live compose path -- see
    module docstring FOLLOW-UP. Never raises."""
    try:
        red_names = {r.get("name") for r in (freshness_rows or [])
                    if isinstance(r, dict) and r.get("status") == RED}
        result: List[Dict[str, Any]] = []
        for svc in (services or []):
            if not isinstance(svc, dict):
                result.append(svc)
                continue
            if svc.get("name") in red_names:
                item = dict(svc)
                cur = svc.get("severity")
                item["severity"] = "degraded" if cur in (None, "ok") else cur
                item["output_freshness"] = RED
                result.append(item)
            else:
                result.append(dict(svc))
        return result
    except Exception:  # noqa: BLE001 -- merge must never crash the caller
        try:
            return [dict(s) if isinstance(s, dict) else s for s in (services or [])]
        except Exception:  # noqa: BLE001
            return []


__all__ = [
    "TABLE", "GREEN", "RED", "STATUS_PATH", "COMPONENT",
    "check_one", "check_all", "write_status", "load_status",
    "merge_freshness_into_services",
]
