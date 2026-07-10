"""scripts.platformkit.autonomy.post_restart_verify -- LANE 4, the ONE
post-`boot.ps1` verifier: turns "did the restart activate everything the
sprint promised?" into a PASS/FAIL/PENDING table, not a guess.

WHAT IT CHECKS (each row independent, one bad row never crashes the rest --
see post_restart_checks.py for the check implementations + data tables):
  (a) supervisor_status: all_ready=True + the expected proc-name set includes
      m33/m34/m35/m36 (the 4 NEW ProcSpecs this restart activates).
  (b) HTTP 200 on ports 3000/8098/8099 (10s timeout each, read-only probe,
      NEVER kills anything -- reuses http_wedge_probe.http_probe).
  (c) each NEW ProcSpec's declared heartbeat is FRESHER than the restart time
      (restart_ts = supervisor_status.json's own "started_at", falling back to
      its file mtime). Within the first tick interval -> PENDING (never a
      false-early FAIL); heartbeat exists but is OLDER than restart_ts and past
      one tick interval -> FAIL; missing well past one interval -> FAIL.
  (d) capture dirs exist + have a FRESH tick for each capture sport, but ONLY
      when that sport has a live game right now (LiveGameFn injectable); no
      live game -> PENDING with cause, never FAIL.
  (e) a fresh mlb/wnba in-game capture row carries the sport's shadow field
      when the shadow module applies (currently wnba's model_prob_wnba_shadow).
  (f) freshness_sla.json's own "overall" field reads GREEN.
  (g) kalshi pregame n_events per sport (mlb/wnba/npb/kbo) via a LIVE call
      (KalshiProvider.fetch, injectable) -- degrades to PENDING (never FAIL)
      on a network/unavailable error, since that is a feed hiccup, not a
      restart-activation failure.
  (h) LANE 5 (waves 11-13) addition: m37_ingame_enrichment's own data-flow
      surface (fotmob_live/, gumbo_live/, book_depth/ artifact-mtime checks,
      PENDING-when-no-live-game semantics) -- see post_restart_enrichment_checks.py.
  (i) LANE 5 addition: a fresh in-play tick for a live game carries the
      enrichment tick fields (xg_*/spread_bp/book_thinness/stale_quote/espn_wp;
      None values fine) -- PENDING without a live game.
  (j) LANE 5 addition: espn_event_id present (non-null) in a fresh mlb capture tick.
  (k)-(p) RESTART-READINESS LANE 3 addition (see post_restart_readiness_checks.py):
      the 6 activations waves 15/17/18/20 shipped that need this pending m2/
      supervisor bounce to run under the NEW code -- grade-writer frac-clamp (k),
      Kalshi 429 pacing counters (l), enrichment persisted into grade rows (m),
      sidecar retention dry-run plan (n), supervisor beat-thread + boot_initiator
      stamp (o), npb/kbo live-state bridge wiring (p).
  (q) E3 addition: autoloop_report.json[maintenance] carries the 6 M07-M12
      job keys + an execution key, none status=error (see
      post_restart_readiness_checks.check_autoloop_maintenance_jobs).

Every external effect (HTTP probe, kalshi fetch, live-game lookup, wall clock)
is INJECTABLE so tests never hit a real socket, kill a PID, or restart
anything. Read-only: no flag flip, no data/registry/ write, no PID touched.

Prints an ASCII PASS/FAIL/PENDING table and writes
data/frontend/ops/post_restart_verify.json. Exit code 0 iff no row is FAIL
(PENDING is allowed and expected on a fresh/quiet restart).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autonomy/test_post_restart_verify.py -q
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.autonomy.post_restart_capture_checks import (
    check_capture_dirs,
    check_shadow_field,
)
from scripts.platformkit.autonomy.post_restart_enrichment_checks import (
    check_enrichment_tick_fields,
    check_espn_event_id_mlb,
    check_m37_artifact_dirs,
)
from scripts.platformkit.autonomy.post_restart_readiness_checks import (
    check_autoloop_maintenance_jobs,
    check_enrichment_persistence,
    check_grade_writer_clamp,
    check_kalshi_pacing_counters,
    check_npb_kbo_live_state_bridge,
    check_sidecar_retention,
    check_supervisor_beat_thread,
)
from scripts.platformkit.autonomy.post_restart_checks import (
    FAIL,
    PASS,
    PENDING,
    check_freshness_sla,
    check_kalshi_pregame,
    check_new_procs,
    check_ports,
    check_supervisor_status,
    restart_ts as _compute_restart_ts,
)

_REPO = Path(__file__).resolve().parents[3]
_OPS = _REPO / "data" / "frontend" / "ops"

STATUS_PATH = _OPS / "post_restart_verify.json"
COMPONENT = "post_restart_verify"


def _default_http_probe() -> Callable[..., Dict[str, Any]]:
    from scripts.platformkit.autonomy.http_wedge_probe import http_probe
    return http_probe


def _default_kalshi_fetch() -> Callable[[str], Any]:
    from scripts.platformkit.odds_provider.kalshi import KalshiProvider
    provider = KalshiProvider()
    return provider.fetch


def _default_live_game_fn() -> Callable[[str], bool]:
    """No wiring for a live-game oracle exists in this lane's injectable scope
    -- default conservatively reports "unknown -> not live" so (d)/(e) degrade
    to an honest PENDING rather than fabricate a live-game claim. A caller with
    a real live-state source should inject its own fn."""
    def _unknown(_sport: str) -> bool:
        return False
    return _unknown


def run_all(*, now: Optional[float] = None,
           http_probe_fn: Optional[Callable[..., Dict[str, Any]]] = None,
           kalshi_fetch_fn: Optional[Callable[[str], Any]] = None,
           live_game_fn: Optional[Callable[[str], bool]] = None) -> Dict[str, Any]:
    """Run every check -> one report dict. Never raises."""
    ts = float(now) if now is not None else time.time()
    http_probe_fn = http_probe_fn if http_probe_fn is not None else _default_http_probe()
    kalshi_fetch_fn = kalshi_fetch_fn if kalshi_fetch_fn is not None else _default_kalshi_fetch()
    live_game_fn = live_game_fn if live_game_fn is not None else _default_live_game_fn()

    at_restart = _compute_restart_ts(ts)
    rows: List[Dict[str, Any]] = []
    rows.append(check_supervisor_status(ts))
    rows.extend(check_ports(http_probe_fn=http_probe_fn))
    rows.extend(check_new_procs(ts, at_restart))
    rows.extend(check_capture_dirs(ts, live_game_fn=live_game_fn))
    rows.extend(check_shadow_field(ts, live_game_fn=live_game_fn))
    rows.append(check_freshness_sla())
    rows.extend(check_kalshi_pregame(fetch_fn=kalshi_fetch_fn))
    # LANE 5 (waves 11-13) addition: m37_ingame_enrichment data-flow surface.
    rows.extend(check_m37_artifact_dirs(ts, live_game_fn=live_game_fn))
    rows.append(check_enrichment_tick_fields(ts, live_game_fn=live_game_fn, sport="mlb"))
    rows.append(check_espn_event_id_mlb(ts, live_game_fn=live_game_fn))
    # RESTART-READINESS LANE 3 addition: the 6 activations waves 15/17/18/20 shipped
    # that need the pending m2/supervisor bounce to run under the NEW code.
    rows.append(check_grade_writer_clamp(ts, live_game_fn=live_game_fn))
    rows.append(check_kalshi_pacing_counters(at_restart))
    rows.append(check_enrichment_persistence(ts, live_game_fn=live_game_fn))
    rows.append(check_sidecar_retention())
    rows.append(check_supervisor_beat_thread(ts, at_restart))
    rows.append(check_npb_kbo_live_state_bridge())
    rows.append(check_autoloop_maintenance_jobs(at_restart))

    n_pass = sum(1 for r in rows if r["status"] == PASS)
    n_fail = sum(1 for r in rows if r["status"] == FAIL)
    n_pending = sum(1 for r in rows if r["status"] == PENDING)
    return {
        "generated_at": ts, "component": COMPONENT, "restart_ts": at_restart,
        "rows": rows, "n_pass": n_pass, "n_fail": n_fail, "n_pending": n_pending,
        "overall": FAIL if n_fail else PASS,
        "honest_note": (
            "post-boot.ps1 activation verifier; PENDING is expected + honest on "
            "a fresh restart or a quiet slate; only a real FAIL should block."
        ),
    }


def write_status(report: Dict[str, Any], *, out_path: Optional[Path] = None) -> bool:
    """Atomically write the report (tmp + os.replace). Never raises."""
    try:
        path = Path(out_path) if out_path is not None else STATUS_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True),
                       encoding="ascii")
        os.replace(str(tmp), str(path))
        return True
    except Exception:  # noqa: BLE001
        return False


def render_table(report: Dict[str, Any]) -> str:
    """ASCII PASS/FAIL/PENDING table. No unicode box-drawing."""
    lines: List[str] = []
    lines.append("=" * 78)
    lines.append("POST-RESTART VERIFY  (generated_at=%.0f restart_ts=%.0f)"
                 % (report.get("generated_at", 0.0), report.get("restart_ts", 0.0)))
    lines.append("=" * 78)
    lines.append("%-32s %-9s %s" % ("CHECK", "STATUS", "EVIDENCE"))
    lines.append("-" * 78)
    for row in report.get("rows", []):
        name = str(row.get("name", "?"))[:32]
        status = str(row.get("status", "?"))
        evidence = str(row.get("evidence", ""))[:100]
        lines.append("%-32s %-9s %s" % (name, status, evidence))
    lines.append("-" * 78)
    lines.append("TOTAL: pass=%d fail=%d pending=%d  overall=%s"
                 % (report.get("n_pass", 0), report.get("n_fail", 0),
                    report.get("n_pending", 0), report.get("overall", "?")))
    lines.append("=" * 78)
    return "\n".join(lines)


def _main() -> int:  # pragma: no cover
    report = run_all()
    print(render_table(report))
    write_status(report)
    return 1 if report.get("overall") == FAIL else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = [
    "STATUS_PATH", "COMPONENT", "run_all", "write_status", "render_table",
]
