"""scripts.platformkit.autoloop.maintenance_templates -- the zero-LLM
pipeline-maintenance jobs (16, see run_all()) that keep the intel layer visible
to ask/weighting, wired as a single extra phase inside autoloop_runner.run_cycle().

These are NOT prereg statistical templates (no universe/K-ledger/blocklist --
standing_prereg.Template is for hypothesis-testing families only). Each job
here is a plain, watermark-gated function; run_all() is the ONE hook point
run_cycle() calls once per tick, isolated so one job's failure never blocks
any other job in the table.

1. validate_new_stores -- pairing-gap trap (memory: an unvalidated store is
   invisible to ask/weighting). Watermark = FILESYSTEM MTIME: a store's own
   jsonl mtime vs its <stem>_validation.json mtime. No separate checkpoint
   needed -- validate_and_write's own output re-stamps the pairing newer, so
   a clean run is naturally skipped next cycle.
2. weighting_refresh -- per-sport re-run of intel_weighting.cli when any
   paired validation is newer than that SPORT's own last-refresh watermark
   (stored in the runner's watermarks dict, NOT the shared ledger file's raw
   mtime -- claim_weights.jsonl is one file across all 4 sports, so a global
   mtime would misfire cross-sport within a single cycle).
3. replication_watch -- REPORT only. A new season corpus file (matching a
   known pattern) queues one human-queue row naming which SURVIVES_PREREG
   ledger rows (for that sport) now have an untested replication corpus.
   Never auto-runs a replication fit -- a fresh prereg needs a deciding mind.

Job #6, ingame_benchmarks (scripts.platformkit.autoloop.ingame_benchmark_job), follows
the same watermark-gated plain-function shape: re-runs the MLB/NBA in-game
MODEL-vs-MARKET benchmarks only once their labeled-game count grew >=25% since the
stored watermark. See that module's docstring for detail.

Job #7, mechanism_reval (scripts.platformkit.autoloop.mechanism_reval_job), re-runs
each domain's UNTESTED knowledge/validate_*.py mechanism checks once that domain's
season corpus grows -- ledger-append only, never touches mechanisms.md prose.

Job #8, utilization_drift (scripts.platformkit.autoloop.utilization_drift_job),
re-runs the cross-sport stat-utilization census once a sport's corpora grow and
reports any newly-dark (UNUSED) column -- report-only, never wires anything.

Job #9, frontier_probe (scripts.platformkit.data_frontier.frontier_probe_job, M11),
re-probes the ranked keyless-source frontier daily (self-gated, 1 req/s, no
evasion) and appends ACQUISITION_DELTA rows to frontier_deltas.jsonl when a
source flips to KEYLESS_CONFIRMED-with-data or grows a new field.

Job #10, shadow_settle (scripts.platformkit.autoloop.shadow_settle_job, M09),
forward self-shadows provisional/wait-for-data ledger verdicts: recomputes each
row's preregistered metric on the ACCRUED forward grade corpus only (strictly
after the row's as-of) and appends SHADOW_TICK / PROMOTE_CANDIDATE / DEMOTED /
SHADOW_UNSPECIFIED rows to its own shadow ledger -- append-only, promotion human.

Job #11, propose_gate (scripts.platformkit.autoloop.propose_gate_job, M10),
the zero-LLM SELF-PROPOSAL cycle: proposes up to K=8 novel interaction-factory
candidates per cycle (round-robin across sports, deduped against every prior
ledger identity AND the closed classes -- reject-ledger REJECTs + NULL_LOCAL
mechanism families) and runs each through the factory runner's REAL leak-free
gate, which appends the honest verdict rows itself. Wall-clock capped per
cycle; 3 consecutive NOT_TESTABLE-only cycles log a pool EXHAUSTED and rotate.

Job #12, milb_refresh (scripts.platformkit.data_frontier.milb_statsapi, M12),
daily MiLB AAA active-roster + transactions/call-up capture via statsapi
(sportId 11 + the MLB-side sportId-1 ledger; 1 req/s, 35s timeout). Watermark =
the as-of-dated output file's existence -- a captured day is a CACHED no-op.

Job #13, benchmark_refresh (scripts.platformkit.autoloop.benchmark_refresh_job,
M15), reruns the MLB in-game CRPS benchmark and the soccer chain full-power
gate ONLY once their own wired-shadow readiness bar (M09's shadow_settle_wired
baseline + min_n/min_matches -- reused, not redefined) is met by new data.
Refresh only -- zero promotion logic, promotion bar stays human. Self-resetting
watermark: a rerun overwrites the source artifact's own baseline count.

Job #14, clv_refresh (scripts.platformkit.autoloop.clv_refresh_job, M16), reruns
the CLV reconcile + scoreboard ops artifacts once the newest clv_reconcile_*.json
is >24h stale (they are hand/CLI-run only per freshness_sla.py, found ~114h stale).
Refresh only -- same reconciler/scoreboard entrypoints a human would run by hand.

Job #21, replication_cadence (scripts.platformkit.autoloop.replication_job, M21),
runs the existing replicate_survivors.py / replicate_batch2b.py workers for any
interaction-factory gate survivor (SURVIVES_PREREG_PROVISIONAL) that carries no
replication row yet, bounded per tick; own-success watermark (no age gate --
rescans the ledger fresh every tick).

Job #22, false_discovery_accounting (scripts.platformkit.autoloop.false_discovery_job,
M22), nightly PREREG R1/R2 accounting (docs/research/PREREG_ALPHA_BUDGETS.md):
backfills one row per completed calendar date in the interaction-factory ledger
(n_tested, families_touched, expected_false_survivors, observed_survivors,
within_noise_floor) into its OWN false_discovery_ledger.jsonl -- read-only over
the verdict ledger, never writes it; own-success watermark (idempotent per date).

Job #23, mlb_results_refresh (scripts.platformkit.autoloop.mlb_results_refresh_job,
M23), cadence-gated refresh of data/domains/mlb/games_current.parquet (2022..present
FINAL MLB results) -- found 27 days stale with zero freshness REDs, no daemon caller
existed. Calls domains.mlb.ingest_current.build_current() directly (>=24h since this
job's own success stamp); row count checked before/after so a shrink is never
mistaken for success (no stamp); a raised ingest exception (e.g. transient curl
network failure) is caught, not re-raised, and also leaves no stamp -- both classes
retry next tick.

Job #24, weekly_scoreboard_cadence (scripts.platformkit.autoloop.scoreboard_job, M24),
renders the current ISO week's one-page scoreboard (scripts.platformkit.reports.
weekly_scoreboard) once per week -- watermark is the last-rendered week LABEL
(watermarks[STATE_KEY]["week"]), not a file mtime; a new ISO week always re-arms it
regardless of same-week reruns, which write_week() itself already renders as an
idempotent overwrite. A raise from write_week() propagates uncaught, isolated by
this module's own run_all try/except, same as every other job.

run_all() dispatches every job through one table (key, module path, callable
name, arg names) instead of a hand-written try/except per job: each entry is
imported and called fresh every cycle (never cached at module import time) so
a test's mock.patch on either this module or the job's own source module is
picked up identically to the original per-job inline imports.
"""
from __future__ import annotations

import importlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.platformkit.intel_validation.validate_store import (
    CLAIMS_DIR as _DEFAULT_CLAIMS_DIR,
    validate_and_write,
)
from scripts.platformkit.intel_weighting import cli as WCLI
from scripts.platformkit.intel_weighting.weight_ledger import append_results

_REPO = Path(__file__).resolve().parents[3]
PREREG_LEDGER_PATH = _REPO / "data" / "cache" / "intel_claims" / "prereg_hypothesis_ledger.jsonl"
_CORPUS_PATTERNS: List[Tuple[Path, "re.Pattern[str]", str]] = [
    (_REPO / "data" / "cache" / "team_system" / "lineups",
     re.compile(r"^stints_\d{4}_\d{2}\.parquet$"), "nba"),
    (_REPO / "data" / "cache" / "statcast",
     re.compile(r"^savant_full__\d{4}\.parquet$"), "mlb"),
]

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# 1. validate_new_stores -----------------------------------------------------
def run_validate_new_stores(claims_dir: Optional[Path] = None,
                            validate_fn: Optional[Callable[[str], Dict[str, Any]]] = None
                            ) -> Dict[str, Any]:
    """Validate every *.jsonl claim store whose mtime > its
    <stem>_validation.json (or has none). Sequential; one bad store is
    isolated and never blocks the rest."""
    d = Path(claims_dir) if claims_dir is not None else _DEFAULT_CLAIMS_DIR
    fn = validate_fn or validate_and_write
    scanned = validated = failed = 0
    failed_stores: List[str] = []
    if not d.is_dir():
        return {"stores_scanned": 0, "stores_validated": 0, "stores_failed": 0,
               "failed_stores": failed_stores}
    for p in sorted(d.glob("*.jsonl")):
        if p.name.endswith(".index.jsonl"):
            continue
        scanned += 1
        vpath = p.with_name("%s_validation.json" % p.stem)
        if vpath.exists() and vpath.stat().st_mtime >= p.stat().st_mtime:
            continue  # already paired+fresh -- mtime IS the watermark
        try:
            fn(str(p))
            validated += 1
        except Exception as exc:  # noqa: BLE001 -- one bad store must not block the next
            failed += 1
            failed_stores.append("%s: %s" % (p.stem, str(exc)[:120]))
    return {"stores_scanned": scanned, "stores_validated": validated,
           "stores_failed": failed, "failed_stores": failed_stores}


# 2. weighting_refresh --------------------------------------------------------
def _validation_files_for_sport(sport: str, claims_dir: Path) -> List[Path]:
    prefix = WCLI._SPORT_PREFIX[sport]  # noqa: SLF001 -- same-package reuse, read-only
    exclude = WCLI._SPORT_EXCLUDE_PREFIX.get(sport)  # noqa: SLF001
    out = []
    for p in claims_dir.glob("*_validation.json"):
        stem = p.name[: -len("_validation.json")]
        if stem.startswith(prefix) and not (exclude and stem.startswith(exclude)):
            out.append(p)
    return out


def run_weighting_refresh(watermarks: Dict[str, Any], *, claims_dir: Optional[Path] = None,
                          cli_run_fn: Optional[Callable[[str], Any]] = None,
                          append_fn: Optional[Callable[[Any], Any]] = None) -> Dict[str, Any]:
    """Per sport: refresh iff any paired validation is newer than that
    sport's own last-refresh watermark. Mutates `watermarks` in place
    (same convention autoloop_runner._process_template uses)."""
    d = Path(claims_dir) if claims_dir is not None else _DEFAULT_CLAIMS_DIR
    run_fn = cli_run_fn or WCLI.run
    upsert_fn = append_fn or append_results
    refreshed: List[str] = []
    failed: List[Dict[str, str]] = []
    for sport in sorted(WCLI._SPORT_PREFIX):  # noqa: SLF001 -- same-package reuse, read-only
        vfiles = _validation_files_for_sport(sport, d)
        if not vfiles:
            continue
        max_mtime = max(p.stat().st_mtime for p in vfiles)
        key = "M02_weighting_refresh__%s" % sport
        prior = float((watermarks.get(key) or {}).get("validation_mtime_max", 0.0))
        if max_mtime <= prior:
            continue
        try:
            upsert_fn(run_fn(sport))
            watermarks[key] = {"validation_mtime_max": max_mtime, "last_run_ts": _now_iso()}
            refreshed.append(sport)
        except Exception as exc:  # noqa: BLE001 -- one sport failing must not block others
            failed.append({"sport": sport, "error": str(exc)[:200]})
    return {"sports_refreshed": refreshed, "sports_failed": failed}


# 3. replication_watch (REPORT only -- never executes a fit) -----------------
def _survives_prereg_hypotheses(sport: str, ledger_path: Path) -> List[str]:
    if not ledger_path.exists():
        return []
    latest: Dict[str, Dict[str, Any]] = {}
    for line in ledger_path.read_text(encoding="ascii", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("sport") != sport:
            continue
        name = str(row.get("hypothesis", ""))
        if not name:
            continue
        if name not in latest or str(row.get("computed_at", "")) > str(latest[name].get("computed_at", "")):
            latest[name] = row
    return sorted(h for h, row in latest.items() if row.get("verdict") == "SURVIVES_PREREG")


def run_replication_watch(watermarks: Dict[str, Any], *,
                          corpus_patterns: Optional[List[Tuple[Path, "re.Pattern[str]", str]]] = None,
                          ledger_path: Optional[Path] = None,
                          queue_fn: Optional[Callable[[Dict[str, Any]], Any]] = None
                          ) -> Dict[str, Any]:
    """REPORT-only: a NEW corpus file matching a known replication pattern
    queues one row naming that sport's SURVIVES_PREREG hypotheses. Never
    runs a replication fit -- surfacing the opportunity is the job."""
    patterns = corpus_patterns if corpus_patterns is not None else _CORPUS_PATTERNS
    ledger = ledger_path or PREREG_LEDGER_PATH
    key = "M03_replication_watch"
    seen = set((watermarks.get(key) or {}).get("seen_files", []))
    reported: List[str] = []
    for directory, pattern, sport in patterns:
        if not directory.is_dir():
            continue
        for p in sorted(directory.iterdir()):
            if p.name in seen or not pattern.match(p.name):
                continue
            seen.add(p.name)
            row = {"kind": "REPLICATION_OPPORTUNITY", "ts": _now_iso(), "sport": sport,
                   "new_corpus": p.name,
                   "survives_prereg_hypotheses": _survives_prereg_hypotheses(sport, ledger),
                   "note": "surfacing only -- replication needs a fresh prereg + a deciding mind"}
            if queue_fn is not None:
                queue_fn(row)
            reported.append(p.name)
    watermarks[key] = {"seen_files": sorted(seen)}
    return {"new_reports": len(reported), "reported_files": reported}


# Single hook point ------------------------------------------------------------
# (key, module path, callable name, arg names). `arg_names` may contain
# "watermarks" (passed positionally, same as every job's own signature) and/or
# "queue_fn" (passed as a kwarg). Local jobs (1-3 above) use this module's own
# __name__ so a test's mock.patch.object(MT, "run_x", ...) is picked up exactly
# as it was when run_all called the bare name directly.
_JOB_TABLE: List[Tuple[str, str, str, Tuple[str, ...]]] = [
    ("validate_new_stores", __name__, "run_validate_new_stores", ()),
    ("weighting_refresh", __name__, "run_weighting_refresh", ("watermarks",)),
    ("replication_watch", __name__, "run_replication_watch", ("watermarks", "queue_fn")),
    # report-only census freshness (census_drift.json); rot surfaced, never fixed here
    ("census_drift", "scripts.platformkit.census_drift", "run_check", ()),
    # longitudinal calibration log (idempotent append; calibration only, no $)
    ("scoreboard_history", "scripts.platformkit.scoreboard_history", "append_rows", ()),
    # watermark-gated in-game benchmark re-runs (grows with the labeled corpora)
    ("ingame_benchmarks", "scripts.platformkit.autoloop.ingame_benchmark_job",
     "run_ingame_benchmarks", ("watermarks",)),
    # watermark-gated mechanism re-validation (ledger-append only, no mechanisms.md edit)
    ("mechanism_reval", "scripts.platformkit.autoloop.mechanism_reval_job",
     "run_mechanism_reval", ("watermarks",)),
    # watermark-gated stat-utilization drift census (report-only, no wiring)
    ("utilization_drift", "scripts.platformkit.autoloop.utilization_drift_job",
     "run_utilization_drift", ("watermarks", "queue_fn")),
    # M11 keyless-frontier auto-probe (self-gated to daily; deltas -> frontier_deltas.jsonl)
    ("frontier_probe", "scripts.platformkit.data_frontier.frontier_probe_job",
     "run_probe_cycle", ()),
    # M09 forward self-shadowing of provisional verdicts (shadow-ledger append only)
    ("shadow_settle", "scripts.platformkit.autoloop.shadow_settle_job",
     "run_shadow_settle", ("watermarks",)),
    # M10 zero-LLM self-proposal: propose -> real leak-free gate -> honest ledger verdicts
    ("propose_gate", "scripts.platformkit.autoloop.propose_gate_job",
     "run_propose_gate", ("watermarks", "queue_fn")),
    # M12 daily MiLB AAA rosters + call-up transactions (file-existence watermark)
    ("milb_refresh", "scripts.platformkit.data_frontier.milb_statsapi", "run_daily", ("watermarks",)),
    # M15 watermark-gated benchmark rerun (refresh only; promotion stays human)
    ("benchmark_refresh", "scripts.platformkit.autoloop.benchmark_refresh_job",
     "run_benchmark_refresh", ("watermarks",)),
    # M16 cadence-gated CLV reconcile+scoreboard refresh (refresh only; file-mtime watermark)
    ("clv_refresh", "scripts.platformkit.autoloop.clv_refresh_job", "run_clv_refresh", ("watermarks",)),
    # M17 cadence-gated calibration-scoreboard ops-json refresh (refresh only; file-mtime watermark)
    ("calibration_refresh", "scripts.platformkit.autoloop.calibration_refresh_job",
     "run_calibration_refresh", ("watermarks",)),
    # U4 log rotation: archive+truncate any logs/*.out|*.err over 50MB cap (size-check only, no watermark)
    ("log_reaper", "scripts.platformkit.autoloop.log_reaper_job", "run_log_reaper", ("watermarks",)),
    # M18 cadence-gated eval-gate reference-core scoreboard refresh (refresh only; file-mtime watermark)
    ("eval_gate", "scripts.platformkit.autoloop.eval_gate_job", "run_eval_gate", ("watermarks",)),
    # M19 cadence-gated pregame crps_market MLB benchmark refresh (refresh only; file-mtime watermark)
    ("pregame_benchmark", "scripts.platformkit.autoloop.pregame_benchmark_job",
     "run_pregame_benchmark", ("watermarks",)),
    # M20 cadence-gated Savant/Statcast season-parquet cache refresh (refresh only; parquet-mtime watermark)
    ("statcast_refresh", "scripts.platformkit.autoloop.statcast_refresh_job",
     "run_statcast_refresh", ("watermarks",)),
    # M21 auto-replication cadence: gate survivor -> 2nd-corpus replication via the existing
    # replicate_survivors/replicate_batch2b workers (own-success watermark; no age gate)
    ("replication_cadence", "scripts.platformkit.autoloop.replication_job",
     "run_replication_cadence", ("watermarks",)),
    # M22 nightly PREREG R1/R2 false-discovery accounting (own ledger; read-only over the verdict ledger)
    ("false_discovery_accounting", "scripts.platformkit.autoloop.false_discovery_job",
     "run_false_discovery_accounting", ("watermarks",)),
    # M23 cadence-gated MLB current-results parquet refresh (refresh only; own-success watermark)
    ("mlb_results_refresh", "scripts.platformkit.autoloop.mlb_results_refresh_job",
     "run_mlb_results_refresh", ("watermarks",)),
    # M24 weekly cadence: render the current ISO week's one-page scoreboard (own-success
    # watermark keyed by week label; a new week always re-arms it)
    ("weekly_scoreboard_cadence", "scripts.platformkit.autoloop.scoreboard_job",
     "run_scoreboard", ("watermarks",)),
    # M25 nightly S15.K2 incremental K refresh (own-heartbeat watermark; honest
    # no-op logged on off-season/no-games nights -- see k_refresh_job docstring)
    ("k_nightly_refresh", "scripts.platformkit.omni.k_refresh_job",
     "run_k_refresh", ()),
    # M26 escalation->funnel Stage-A intake (idempotent via claim lifecycle;
    # re-scans lifecycle=='proposed'+escalate_to_funnel claims every tick)
    ("k_escalation_intake", "scripts.platformkit.omni.escalation_intake",
     "run_escalation_intake", ()),
]


def run_all(watermarks: Dict[str, Any], *, queue_fn: Optional[Callable[[Dict[str, Any]], Any]] = None
           ) -> Dict[str, Any]:
    """run_cycle()'s one call site for every maintenance job in _JOB_TABLE.
    Each entry isolated: a raise in one is caught here and never blocks the
    rest of the table."""
    out: Dict[str, Any] = {}
    for key, import_path, callable_name, arg_names in _JOB_TABLE:
        try:
            fn = getattr(importlib.import_module(import_path), callable_name)
            args = tuple(watermarks for a in arg_names if a == "watermarks")
            kwargs = {"queue_fn": queue_fn} if "queue_fn" in arg_names else {}
            out[key] = fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 -- one job's failure must never block the rest
            out[key] = {"status": "error", "error": str(exc)[:200]}
    return out


__all__ = ["run_validate_new_stores", "run_weighting_refresh", "run_replication_watch",
          "run_all", "PREREG_LEDGER_PATH"]
