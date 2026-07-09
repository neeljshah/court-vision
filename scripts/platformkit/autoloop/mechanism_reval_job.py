"""scripts.platformkit.autoloop.mechanism_reval_job -- watermark-gated re-run of
the per-domain UNTESTED mechanism validators as new season data lands (autoloop
job #7). Wraps the EXISTING domains/<sport>/knowledge/validate_*.py modules --
never reimplements their math. Each module's own run() already appends its
verdict (CONFIRMED_LOCAL/NULL_LOCAL/NOT_TESTABLE) to that domain's
validation_ledger.jsonl -- exactly what a human running
`python -m domains.X.knowledge.validate_Y` produces by hand. This job only
decides WHEN to call that run(), off the domain's primary corpus file mtime.
It NEVER edits mechanisms.md -- a human/Fable reads the fresh ledger rows and
updates the prose status.

WATERMARK = newest mtime across the representative corpus file(s) each
domain's validate_*.py scripts actually read (see _REGISTRY). No watermark
yet -> due iff the file exists (first tick establishes the baseline, mirrors
ingame_benchmark_job's "no prior watermark" convention). A module raising is
isolated -- one bad mechanism test never blocks its siblings or the next
domain; the domain's watermark still advances once every registered module
has been attempted (an already-logged failure should not retry every cycle).

INVARIANTS: ledger-append only (identical shape to a human running the
module's CLI); no promotion; no flag flip; no mechanisms.md edit; no gate.

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autoloop/test_mechanism_reval_job.py -q
"""
from __future__ import annotations

import importlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_REPO = Path(__file__).resolve().parents[3]

# domain -> representative corpus file(s) + the validate_*.py modules that
# read them (each exposes a uniform run() -> List[Dict]).
_REGISTRY: Dict[str, Dict[str, Any]] = {
    "basketball_nba": {
        "corpus": [_REPO / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"],
        "modules": [
            "domains.basketball_nba.knowledge.validate_schedule_fatigue",
            "domains.basketball_nba.knowledge.validate_usage_garbage",
            "domains.basketball_nba.knowledge.validate_rotation_pace",
        ],
    },
    "mlb": {
        "corpus": [_REPO / "data" / "cache" / "statcast" / "savant_full__2025.parquet"],
        "modules": [
            "domains.mlb.knowledge.validate_contact_park",
            "domains.mlb.knowledge.validate_count_zone",
            "domains.mlb.knowledge.validate_data_gaps",
        ],
    },
    "soccer": {
        "corpus": [_REPO / "data" / "cache" / "statsbomb" / "match_meta.parquet"],
        "modules": [
            "domains.soccer.knowledge.validate_data_gaps",
            "domains.soccer.knowledge.validate_ingame_state",
            "domains.soccer.knowledge.validate_season_structure",
        ],
    },
    "tennis": {
        "corpus": [_REPO / "data" / "domains" / "tennis" / "matches.parquet",
                  _REPO / "data" / "domains" / "tennis" / "wta_matches.parquet"],
        "modules": [
            "domains.tennis.knowledge.validate_match_outcomes",
            "domains.tennis.knowledge.validate_point_dynamics",
        ],
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _corpus_mtime(paths: List[Path]) -> Optional[float]:
    mtimes = [p.stat().st_mtime for p in paths if p.is_file()]
    return max(mtimes) if mtimes else None


def run_mechanism_reval(watermarks: Dict[str, Any], *,
                        registry: Optional[Dict[str, Dict[str, Any]]] = None,
                        import_fn: Optional[Callable[[str], Any]] = None) -> Dict[str, Any]:
    """Per domain: iff its corpus grew (mtime newer than the stored watermark),
    call every registered validate module's run(). Each module isolated -- one
    raising never blocks the domain's other modules or the next domain."""
    reg = registry if registry is not None else _REGISTRY
    importer = import_fn or importlib.import_module
    out: Dict[str, Any] = {}
    for domain, spec in reg.items():
        key = "M07_mechanism_reval__%s" % domain
        mtime = _corpus_mtime(spec["corpus"])
        prior = float((watermarks.get(key) or {}).get("corpus_mtime", -1.0))
        if mtime is None or mtime <= prior:
            out[domain] = {"status": "skipped", "corpus_mtime": mtime, "watermark": prior}
            continue
        ran: List[str] = []
        failed: List[Dict[str, str]] = []
        rows_appended = 0
        for mod_name in spec["modules"]:
            try:
                mod = importer(mod_name)
                result = mod.run()
                rows_appended += len(result)
                ran.append(mod_name)
            except Exception as exc:  # noqa: BLE001 -- one module failing must not block siblings
                failed.append({"module": mod_name, "error": str(exc)[:200]})
        watermarks[key] = {"corpus_mtime": mtime, "last_run_ts": _now_iso()}
        out[domain] = {"status": "ran", "modules_ran": ran, "modules_failed": failed,
                       "rows_appended": rows_appended}
    return out


__all__ = ["run_mechanism_reval", "_REGISTRY"]
