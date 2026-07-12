"""scripts.platformkit.autoloop.pregame_benchmark_job -- M19: cadence-gated
REFRESH of the PREGAME crps_market MLB benchmark (data/frontend/ops/
pregame_crps_scoreboard_latest.json). run_mlb.py (docstring: "CRPS-vs-market
DISTRIBUTIONAL benchmark for MLB totals") has no daemon caller and writes its
artifact only next to its own source (last_run_mlb.json, hand-run-only) -- a
human running it by hand is the only prior path (measured: run_mlb.py takes
1m16s wall on this box, n_scored=300, verdict UNDERPOWERED, 2026-07-12). This
is the daemon side of that gap, mirroring M18 (eval_gate_job.py) exactly.

REFRESH ONLY: calls run_mlb.run() DIRECTLY with run_mlb.py's own CLI default
args (start/end/max_games below, copied verbatim from run_mlb.py:182-184) --
no verdict math of its own. This job wraps that call and writes the one
ops-json artifact under data/frontend/ops/ run_mlb.py itself never produces
(its own last_run_mlb.json write is untouched, still hand-run-only).

argv=[] discipline (the cac9f26f class): run_mlb.py's _main(argv=None) calls
argparse.parse_args(argv), which falls back to sys.argv when argv is None --
calling _main() from inside a daemon would leak the daemon's own argv (e.g.
"--interval 86400") into this benchmark's argparse. This job NEVER calls
_main(); it calls run_mlb.run(start, end, max_games, seed) directly, the same
choice M15's benchmark_refresh_job made for ingame_mlb.run() (see that
module's _default_mlb_rerun). sys.argv is untouched by this job (regression-
tested below).

STATIC WINDOW (documented, not invented): run_mlb.run() takes required
start/end args (no built-in defaults, unlike ingame_mlb.run()'s max_games).
This job passes the same literal 2026-06-18..2026-07-08 window run_mlb.py's
own argparse defaults to, matching the already-hand-run evidence artifact.
# ponytail: static window, not a rolling one -- add a rolling end-date (e.g.
# "yesterday") when the corpus needs to extend past 2026-07-08; out of scope
# for this refresh-only wrapper, which only mirrors the CLI's own defaults.

Cadence = pregame_crps_scoreboard_latest.json's own mtime. Self-resetting:
a successful run overwrites that file, so the next check needs a fresh 7d
before it fires again -- same convention as M15/M16/M17/M18. The
`watermarks` dict param is accepted for call-shape uniformity with every
other maintenance job; unused here.

HONESTY: pregame sharpness (CRPS/interval-coverage) only, never a market
edge -- run_mlb.py's own doc already carries edge_claimed:false and an
honest_note; this job passes that doc through verbatim under
pregame_crps_scoreboard, adding only a generated_at stamp + wrapper
honesty_note (see .claude/rules/no-edge-claims.md). A job-level exception
(e.g. missing corpus) propagates uncaught here and is isolated one level up
by maintenance_templates.run_all's own try/except, same as every other job
in the table -- no ops-json is written on that path, so the artifact stays
stale and the next cycle retries (the "loud red row" is run_all's own
{"status": "error", ...}). A benchmark VERDICT (MODEL_SHARPER /
MARKET_SHARPER / UNDERPOWERED / NOT_TESTABLE) is never an exception -- those
are honest results and are written to the ops-json exactly as run_mlb.py
computed them.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; never writes
data/registry/; never flips a flag.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autoloop/test_pregame_benchmark_job.py -q
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

_REPO = Path(__file__).resolve().parents[3]
_LATEST_PATH = _REPO / "data" / "frontend" / "ops" / "pregame_crps_scoreboard_latest.json"
_STALE_AFTER_H = 168.0  # 7d -- refresh-only benchmark, not a live-drifting metric

# run_mlb.py's own argparse defaults (run_mlb.py:182-184), copied verbatim so
# this job's rerun is the same window the hand-run evidence artifact used.
_DEFAULT_START = "2026-06-18"
_DEFAULT_END = "2026-07-08"
_DEFAULT_MAX_GAMES = 300


def _artifact_age_h(path: Path) -> Optional[float]:
    """Age in hours of the ops-json artifact; None if it does not exist yet
    (treated as due -- there is nothing to be fresh)."""
    p = Path(path)
    if not p.exists():
        return None
    return (time.time() - p.stat().st_mtime) / 3600.0


def _default_run() -> Dict[str, Any]:
    """Call run_mlb.run() directly (never _main()/argparse) with its own CLI
    default window, so no daemon argv can leak into this benchmark's args."""
    from scripts.platformkit.benchmarks.crps_market import run_mlb as RM
    return RM.run(start=_DEFAULT_START, end=_DEFAULT_END, max_games=_DEFAULT_MAX_GAMES)


def _write_ops_json(result: Dict[str, Any], out_path: Path) -> None:
    doc = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "honesty_note": "PREGAME CRPS/COVERAGE SHARPNESS ONLY. Not a market or betting edge.",
        "pregame_crps_scoreboard": {
            "source_tool": "scripts/platformkit/benchmarks/crps_market/run_mlb.py",
            **result,
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="ascii")


def run_pregame_benchmark(watermarks: Optional[Dict[str, Any]] = None, *,
                          artifact_path: Optional[Path] = None,
                          age_fn: Optional[Callable[[Path], Optional[float]]] = None,
                          run_fn: Optional[Callable[[], Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Refresh iff pregame_crps_scoreboard_latest.json is >7d stale (or
    missing). Refresh only: reruns the pregame MLB CRPS-vs-market benchmark
    and writes the ops-json artifact run_mlb.py itself never produces."""
    p = Path(artifact_path) if artifact_path is not None else _LATEST_PATH
    age_h = (age_fn or _artifact_age_h)(p)
    if age_h is not None and age_h < _STALE_AFTER_H:
        return {"status": "skipped", "age_h": round(age_h, 1)}
    result = (run_fn or _default_run)()
    _write_ops_json(result, p)
    return {"status": "ran", "age_h": age_h, "verdict": result.get("verdict"),
           "n_scored": result.get("n_scored")}


__all__ = ["run_pregame_benchmark"]
