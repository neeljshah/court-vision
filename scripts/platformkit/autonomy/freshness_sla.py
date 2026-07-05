"""scripts.platformkit.autonomy.freshness_sla -- per-daemon freshness SLA table.

THE GAP THIS CLOSES
--------------------
output_freshness.py (M29) covers ONLY the 9 readiness=NONE daemons (m19-m27).
Every other daemon in supervisor.stack_specs (m1, m2, m4, m7, m10-m18, m29-m32,
the capture loops...) has NO declarative "what output artifact proves this
daemon is actually DOING WORK, and how stale can it get before that is a lie"
table anywhere -- a HEARTBEAT-fresh process can still be looping with a wedged
inner step (e.g. writing its heartbeat but silently failing to touch its real
output). This module is that missing table, generalized across the fleet
(not just the readiness=NONE subset).

DECLARATIVE TABLE
-----------------
``TABLE: Dict[str, SlaEntry]`` maps daemon name -> its declared output artifact
path + max_staleness_seconds. Populated ONLY for daemons whose real cadence was
verified by reading their ProcSpec/runner code (the docstring on each row cites
the source: the ProcSpec argv --interval in supervisor.stack_specs, or the
runner module's own DEFAULT_INTERVAL_SEC). A daemon NOT in the table probes as
NA (unknown) -- NEVER GREEN. A missing table entry is an honest gap, not a
silent pass.

HONESTY: read-only, no restart authority (mirrors output_freshness.py); no $
field; no flag flip; no data/registry/ write; never raises.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autonomy/test_freshness_sla.py -q
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional

_REPO = Path(__file__).resolve().parents[3]
_OPS = _REPO / "data" / "frontend" / "ops"
_HB = _REPO / "data" / "cache" / "daemon_heartbeats"
_FRONTEND = _REPO / "data" / "frontend"

GREEN = "GREEN"
RED = "RED"
NA = "NA"   # no table entry -- unknown, NEVER treated as GREEN.

STATUS_PATH = _OPS / "freshness_sla.json"
COMPONENT = "m_freshness_sla"


class SlaEntry(NamedTuple):
    path: Path
    max_staleness_sec: float


# daemon name -> (declared output artifact, max staleness before RED).
# max_staleness_sec = ~2.2x the daemon's OWN verified cadence (same house margin
# output_freshness.py uses), read from supervisor.stack_specs ProcSpec argv
# --interval or the runner module's DEFAULT_INTERVAL_SEC. Each row cites its
# source so a future edit can re-verify instead of guessing.
TABLE: Dict[str, SlaEntry] = {
    # m1_producer: predict_service.scheduler --interval 600 (stack_specs.py L116).
    "m1_producer": SlaEntry(
        _FRONTEND / "predict_service" / "_heartbeat.json", 1500.0),
    # m1_paper: auto_loop --forever, ~20min (1200s) default cycle (stack_specs.py L163-166).
    "m1_paper": SlaEntry(_HB / "m1_paper.txt", 2700.0),
    # m2_inplay: capture runner heartbeat-gated (stack_specs.py, HEARTBEAT readiness).
    "m2_inplay": SlaEntry(_HB / "m2_inplay.txt", 1800.0),
    # m2_inplay_capture: phase-aware live/idle poll (stack_specs.py HEARTBEAT readiness).
    "m2_inplay_capture": SlaEntry(_HB / "m2_inplay_capture.txt", 1800.0),
    # m4_selfimprove: measurement-only cadence loop (HEARTBEAT readiness in stack_specs.py).
    "m4_selfimprove": SlaEntry(_HB / "m4_selfimprove.txt", 1800.0),
    # m7_ingame_refresh: continuous refresh loop (HEARTBEAT readiness, stack_specs.py).
    "m7_ingame_refresh": SlaEntry(_HB / "m7_ingame_refresh.txt", 7800.0),
    # m8_ci_cadence: HOURLY-light interval per module docstring (stack_specs.py L54-57).
    "m8_ci_cadence": SlaEntry(_HB / "m8_ci_cadence.txt", 7800.0),
    # m10_best_bets_compute: 240s cadence, fresh_sec=300 in its own ReadinessSpec
    # (stack_specs.py L303-309) -- reused verbatim as the output SLA too.
    "m10_best_bets_compute": SlaEntry(
        _FRONTEND / "best_bets.json", 300.0),
    # m11_ingame_pred_tick: 20s live / 120s idle; fresh_sec=300 (stack_specs.py L315-322).
    "m11_ingame_pred_tick": SlaEntry(_HB / "m11_ingame_pred_tick.txt", 300.0),
    # m12_pm_paper_tick: 60s cadence; fresh_sec=150 (stack_specs.py L328-335).
    "m12_pm_paper_tick": SlaEntry(_HB / "m12_pm_paper_tick.txt", 150.0),
    # m13_props_pred_tick: 300s cadence; fresh_sec=660 (stack_specs.py L337-348).
    "m13_props_pred_tick": SlaEntry(_FRONTEND / "props_snapshot.json", 660.0),
    # m14_brain_rebuild: 6h cadence; fresh_sec=46800 (stack_specs.py L350-373).
    "m14_brain_rebuild": SlaEntry(_HB / "m14_brain_rebuild.txt", 46800.0),
    # m15_prop_settle: 900s cadence; fresh_sec=1980 (stack_specs.py L375-389).
    "m15_prop_settle": SlaEntry(_HB / "m15_prop_settle.txt", 1980.0),
    # m16_prop_close_capture: 60s cadence; fresh_sec=150 (stack_specs.py L391-407).
    "m16_prop_close_capture": SlaEntry(_HB / "m16_prop_close_capture.txt", 150.0),
    # m17_kalshi_scan: 1800s cadence; fresh_sec=3900 (stack_specs.py L409-421).
    "m17_kalshi_scan": SlaEntry(_HB / "m17_kalshi_scan.txt", 3900.0),
    # m18_pm_close_capture: 900s cadence; fresh_sec=1980 (stack_specs.py L423-436).
    "m18_pm_close_capture": SlaEntry(_HB / "m18_pm_close_capture.txt", 1980.0),
    # m29_output_freshness: 300s cadence; fresh_sec=660 (stack_specs.py L596-613);
    # its own output is output_freshness.json.
    "m29_output_freshness": SlaEntry(_OPS / "output_freshness.json", 660.0),
    # m30_feed_health: 600s cadence; fresh_sec=1320 (stack_specs.py L614-621).
    "m30_feed_health": SlaEntry(_OPS / "feed_health.json", 1320.0),
    # m31_mlb_context: 21600s (6h) cadence; fresh_sec=45000 (stack_specs.py L622-635).
    "m31_mlb_context": SlaEntry(_HB / "m31_mlb_context.txt", 45000.0),
    # m32_mlb_context_autogate: 86400s (24h) cadence; fresh_sec=190000
    # (stack_specs.py L636-654).
    "m32_mlb_context_autogate": SlaEntry(
        _OPS / "mlb_context_autogate.json", 190000.0),

    # --- LANE 3 (2026-07-03): outcome-LABEL artifact freshness -----------------
    # These are NOT daemon heartbeats -- they are the realized-score parquets the
    # in-game outcome resolvers (soccer_outcome/ingame_outcome_label/
    # wnba_outcome_resolver/npb_outcome_resolver/kbo_outcome_resolver) read.
    # 26/32 unresolved soccer_intl in-game bets traced to espn_finals.parquet
    # going stale silently for 6 days (2026-06-22..28 never ingested) with no
    # SLA row to catch it. max_staleness_sec below is deliberately generous
    # (each sport plays at most ~1x/day, so a same-day miss is normal) but
    # bounded so a MULTI-day silent gap goes RED, not NA-forever.
    #
    # soccer_intl finals: now self-healed every ~900s by BOTH m27's own 3-day
    # lookback (ingame_paper_settle._refresh_soccer_finals) AND the new bounded
    # multi-day refresh wired into m36 (label_finals_refresh.refresh_all, capped
    # 10 dates/tick) -- 36h is a daily-tournament-slate cadence with margin.
    "soccer_intl_finals": SlaEntry(
        _REPO / "data" / "domains" / "soccer_intl" / "espn_finals.parquet", 129600.0),
    # mlb espn_boxscores: MLB plays every day of the season; observed stale
    # 2.5 days (2026-07-01) at lane start with NO periodic caller anywhere in
    # the repo before this lane wired one into m36. 36h (129600s) margin over a
    # daily cadence.
    "mlb_espn_boxscores": SlaEntry(
        _REPO / "data" / "domains" / "mlb" / "espn_boxscores.parquet", 129600.0),
    # wnba espn_scoreboard: daily-ish WNBA slate; same "nobody calls this
    # periodically" gap as MLB before this lane. 36h margin.
    "wnba_espn_scoreboard": SlaEntry(
        _REPO / "data" / "domains" / "wnba" / "espn_scoreboard.parquet", 129600.0),
    # npb_results / kbo_results: SLA-monitored but NOT auto-refreshed by this
    # lane (see label_finals_refresh.py module docstring -- monthly HTML scrape
    # with its own polite-pacing/bot-wall discipline, different shape from the
    # bounded per-date ESPN JSON refresh). Both sports play near-daily in
    # season; 48h (172800s) margin gives a bit more slack than the ESPN-sourced
    # rows since refresh here is still a manual/CLI re-run.
    "npb_results": SlaEntry(
        _REPO / "data" / "domains" / "npb" / "npb_results.parquet", 172800.0),
    "kbo_results": SlaEntry(
        _REPO / "data" / "domains" / "kbo" / "kbo_results.parquet", 172800.0),

    # --- LANE 1 (2026-07-05): manual/CLI ops-report freshness -------------------
    # edge_greenlight / clv_scoreboard / clv_reconcile (moneyline + paper_pm) /
    # after_cost / beat_the_line write scoreboards used to gate real decisions but
    # have NO ProcSpec/daemon at all (scripts/platformkit/clv/ + econ/, hand/CLI-
    # run only) -- found 73-75h stale with nothing flagging it. Same 48h manual-
    # refresh margin as npb_results/kbo_results above (a hand-run report going a
    # day-plus silent is normal; multi-day is the honest-gap signal to catch).
    "edge_greenlight": SlaEntry(
        _OPS / "edge_greenlight.json", 172800.0),
    "clv_scoreboard": SlaEntry(
        _OPS / "clv_scoreboard.json", 172800.0),
    "clv_reconcile_moneyline": SlaEntry(
        _OPS / "clv_reconcile_moneyline.json", 172800.0),
    "clv_reconcile_paper_pm": SlaEntry(
        _OPS / "clv_reconcile_paper_pm.json", 172800.0),
    "after_cost_scoreboard": SlaEntry(
        _OPS / "after_cost_scoreboard.json", 172800.0),
    "beat_the_line": SlaEntry(
        _OPS / "beat_the_line.json", 172800.0),
}


def check_one(name: str, *, now: Optional[float] = None,
              table: Optional[Dict[str, SlaEntry]] = None) -> Dict[str, Any]:
    """GREEN/RED/NA verdict for one daemon. A name absent from *table* is NA --
    NEVER GREEN. Never raises."""
    ts = float(now) if now is not None else time.time()
    tbl = table if table is not None else TABLE
    entry = tbl.get(name)
    if entry is None:
        return {"name": name, "status": NA, "path": None,
                "max_staleness_sec": None, "age_sec": None,
                "reason": "no_sla_entry"}
    row: Dict[str, Any] = {
        "name": name, "path": str(entry.path),
        "max_staleness_sec": entry.max_staleness_sec,
    }
    try:
        p = Path(entry.path)
        if not p.exists():
            row.update(status=RED, age_sec=None, reason="missing")
            return row
        age = ts - p.stat().st_mtime
        if age < 0:
            age = 0.0  # clock skew must never manufacture a negative age
        row["age_sec"] = round(age, 1)
        if age > entry.max_staleness_sec:
            row.update(status=RED, reason="stale")
        else:
            row.update(status=GREEN, reason=None)
    except Exception as exc:  # noqa: BLE001 -- an unreadable path is RED, not a crash
        row.update(status=RED, age_sec=None, reason="error:%s" % str(exc)[:80])
    return row


def check_all(names: List[str], *, now: Optional[float] = None,
              table: Optional[Dict[str, SlaEntry]] = None) -> List[Dict[str, Any]]:
    """GREEN/RED/NA rows for every name in *names* (typically every ProcSpec
    name the caller supervises). Order-preserving. Never raises."""
    ts = float(now) if now is not None else time.time()
    return [check_one(n, now=ts, table=table) for n in (names or [])]


def write_status(rows: List[Dict[str, Any]], *, out_path: Optional[Path] = None,
                 now: Optional[float] = None) -> bool:
    """Atomically write the SLA rows (tmp + os.replace). Never raises.

    ``overall`` is RED iff any row is RED; NA rows do not themselves flip
    overall to RED (an unmonitored daemon is a visible gap, counted separately
    in ``n_na``, not conflated with an active failure)."""
    try:
        path = Path(out_path) if out_path is not None else STATUS_PATH
        ts = float(now) if now is not None else time.time()
        n_red = sum(1 for r in rows if r.get("status") == RED)
        n_na = sum(1 for r in rows if r.get("status") == NA)
        doc = {
            "generated_at": ts, "component": COMPONENT, "rows": list(rows or []),
            "n_daemons": len(rows or []), "n_red": n_red, "n_na": n_na,
            "overall": RED if n_red else GREEN,
            "honest_note": (
                "per-daemon output-freshness SLA; a name with NO table entry "
                "reads NA (unknown), NEVER GREEN; read-only, NO restart "
                "authority; no $ field."
            ),
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
    """Best-effort read of the rows[] list. Missing/bad file -> [] (unknown,
    never treated as all-green). Never raises."""
    try:
        p = Path(path) if path is not None else STATUS_PATH
        if not p.exists():
            return []
        doc = json.loads(p.read_text(encoding="ascii"))
        rows = doc.get("rows")
        return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    except Exception:  # noqa: BLE001
        return []


def probe(name: str, *, now: Optional[float] = None) -> str:
    """Convenience helper for wake probes: returns just the status string
    (GREEN/RED/NA) for *name* against the real TABLE. Never raises."""
    try:
        return check_one(name, now=now).get("status", NA)
    except Exception:  # noqa: BLE001
        return NA


__all__ = [
    "SlaEntry", "TABLE", "GREEN", "RED", "NA", "STATUS_PATH", "COMPONENT",
    "check_one", "check_all", "write_status", "load_status", "probe",
]
