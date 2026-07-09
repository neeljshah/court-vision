"""scripts.platformkit.autoloop.maintenance_templates -- the 3 zero-LLM
pipeline-maintenance jobs that keep the intel layer visible to ask/weighting,
wired as a single extra phase inside autoloop_runner.run_cycle().

These are NOT prereg statistical templates (no universe/K-ledger/blocklist --
standing_prereg.Template is for hypothesis-testing families only). Each job
here is a plain, watermark-gated function; run_all() is the ONE hook point
run_cycle() calls once per tick, isolated so one job's failure never blocks
the other two or the SP-template cycle around it.

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
"""
from __future__ import annotations

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
def run_all(watermarks: Dict[str, Any], *, queue_fn: Optional[Callable[[Dict[str, Any]], Any]] = None
           ) -> Dict[str, Any]:
    """run_cycle()'s one call site for all 3 maintenance jobs. Each isolated:
    a raise in one is caught here and never blocks the others."""
    out: Dict[str, Any] = {}
    try:
        out["validate_new_stores"] = run_validate_new_stores()
    except Exception as exc:  # noqa: BLE001
        out["validate_new_stores"] = {"status": "error", "error": str(exc)[:200]}
    try:
        out["weighting_refresh"] = run_weighting_refresh(watermarks)
    except Exception as exc:  # noqa: BLE001
        out["weighting_refresh"] = {"status": "error", "error": str(exc)[:200]}
    try:
        out["replication_watch"] = run_replication_watch(watermarks, queue_fn=queue_fn)
    except Exception as exc:  # noqa: BLE001
        out["replication_watch"] = {"status": "error", "error": str(exc)[:200]}
    try:
        # report-only census freshness (census_drift.json); rot surfaced, never fixed here
        from scripts.platformkit.census_drift import run_check
        out["census_drift"] = run_check()
    except Exception as exc:  # noqa: BLE001
        out["census_drift"] = {"status": "error", "error": str(exc)[:200]}
    try:
        # longitudinal calibration log (idempotent append; calibration only, no $)
        from scripts.platformkit.scoreboard_history import append_rows
        out["scoreboard_history"] = append_rows()
    except Exception as exc:  # noqa: BLE001
        out["scoreboard_history"] = {"status": "error", "error": str(exc)[:200]}
    return out


__all__ = ["run_validate_new_stores", "run_weighting_refresh", "run_replication_watch",
          "run_all", "PREREG_LEDGER_PATH"]
