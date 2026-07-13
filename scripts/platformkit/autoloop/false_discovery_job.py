"""scripts.platformkit.autoloop.false_discovery_job -- M22: nightly false-
discovery accounting per PREREG R1/R2 (docs/research/PREREG_ALPHA_BUDGETS.md,
registered 2026-07-13, binding). Read-only over the interaction-factory
verdict ledger; writes its OWN ledger only -- never touches
interaction_factory_ledger.jsonl.

R1: every calendar date (UTC, by computed_at) that gates >=1 discovery row
gets exactly one accounting row in data/cache/intel_claims/
false_discovery_ledger.jsonl:
    {date, n_tested, families_touched, expected_false_survivors, alpha_used,
     observed_survivors, survivor_ids, within_noise_floor}
expected_false_survivors = sum of alpha_fwer over that date's discovery rows
(the per-test bar each REAL test was held to -- expectation under the global
null); NOT_TESTABLE rows have alpha_fwer None and count toward n_tested but
contribute 0 expectation, matching the ledger's own semantics (runner.py:
"NOT_TESTABLE spends no budget"). R2: within_noise_floor is True iff
observed_survivors <= ceil(expected_false_survivors) -- the label the caller
attaches to that night's survivors in any human-facing summary; it never
gates the pipeline (M21 replication still runs on them regardless).

DISCOVERY ROWS ONLY: rows with `replication_of` set are excluded -- a
replication is not a discovery test (it doesn't spend fresh alpha; see
replication_job.py's own docstring: SURVIVES_PREREG_PROVISIONAL is always an
original discovery-time row, no replicate_* worker ever writes it, so this
filter is belt-and-suspenders against any future replication verdict getting
counted as a fresh test).

COMPLETED DATES ONLY: a date strictly before `today` (UTC) is backfilled;
today-so-far is never accounted (R1 wants one settled row per night, not a
moving partial count) -- simply retried once it is no longer "today".

Own file, own writer: false_discovery_ledger.jsonl has exactly one writer
(this job), so clv_ledger_io.append_row's internal ledger_lock (the same
shared advisory-lock primitive every other ledger writer in this repo uses)
is sufficient -- no separate `with ledger_lock():` wrap needed on top of it.

WATERMARK (M20/d1e8eccb convention, own-success only): stamped in
watermarks[STATE_KEY] ONLY when every date processed this tick appended
without raising -- one date's append failure withholds the stamp so the
SAME unaccounted date is retried next tick, never silently dropped. Already-
accounted dates are never reprocessed (idempotent scan of the FDR ledger's
own `date` column), so a partial tick's successes are not redone either.

CLI (list/backfill, prints the appended rows' date/n_tested/expected/observed):
    python -m scripts.platformkit.autoloop.false_discovery_job

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autoloop/test_false_discovery_job.py -q
"""
from __future__ import annotations

import json
import math
from datetime import date as _date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.clv_ledger_io import append_row
from scripts.platformkit.combo.fwer_budget import DEFAULT_EPS
from scripts.platformkit.interaction_factory import runner as IFR

_REPO = Path(__file__).resolve().parents[3]
FDR_LEDGER_PATH = _REPO / "data" / "cache" / "intel_claims" / "false_discovery_ledger.jsonl"
STATE_KEY = "M22_false_discovery_accounting"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iter_jsonl(path: Path):
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _accounted_dates(fdr_path: Path) -> set:
    return {row.get("date") for row in _iter_jsonl(fdr_path) if row.get("date")}


def _discovery_rows_by_date(source_rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """date (YYYY-MM-DD, from computed_at) -> that date's discovery rows,
    excluding replication rows (replication_of set -- see module docstring)."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    for row in source_rows:
        if row.get("replication_of"):
            continue
        d = str(row.get("computed_at", ""))[:10]
        if len(d) != 10:
            continue
        out.setdefault(d, []).append(row)
    return out


def accounting_row(date_str: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build one R1 row for `date_str` from its discovery rows (see module
    docstring for the exact expectation/noise-floor semantics)."""
    families = sorted({str(r["template_id"]) for r in rows if r.get("template_id")})
    expected = sum(float(r["alpha_fwer"]) for r in rows if r.get("alpha_fwer") is not None)
    survivor_ids = sorted(r.get("candidate_id") for r in rows if r.get("verdict") == IFR.SURVIVES)
    observed = len(survivor_ids)
    return {
        "date": date_str,
        "n_tested": len(rows),
        "families_touched": families,
        "expected_false_survivors": round(expected, 6),
        "alpha_used": DEFAULT_EPS,
        "observed_survivors": observed,
        "survivor_ids": survivor_ids,
        "within_noise_floor": observed <= math.ceil(expected),
        "computed_at": _now_iso(),
    }


def run_false_discovery_accounting(watermarks: Dict[str, Any], *,
                                   source_ledger_path: Optional[Path] = None,
                                   fdr_ledger_path: Optional[Path] = None,
                                   load_source_fn: Optional[Callable[[Path], List[Dict[str, Any]]]] = None,
                                   append_fn: Optional[Callable[[Dict[str, Any], Path], None]] = None,
                                   today: Optional[_date] = None) -> Dict[str, Any]:
    """One M22 tick: append one R1 row per completed, unaccounted date with
    >=1 discovery row. Idempotent (skips dates already in the FDR ledger),
    never raises out (a per-date append failure isolates and simply withholds
    that date + the watermark stamp)."""
    src = Path(source_ledger_path) if source_ledger_path is not None else IFR.LEDGER_PATH
    fdr = Path(fdr_ledger_path) if fdr_ledger_path is not None else FDR_LEDGER_PATH
    do_append = append_fn or (lambda row, path: append_row(row, path=path))
    cutoff = today if today is not None else datetime.now(timezone.utc).date()

    rows = (load_source_fn or IFR._load_ledger)(src)  # noqa: SLF001 -- same loader replication_job reuses
    by_date = _discovery_rows_by_date(rows)
    already = _accounted_dates(fdr)

    dates_appended: List[str] = []
    errors: Dict[str, str] = {}
    for d in sorted(by_date):
        if d in already or not by_date[d]:
            continue
        try:
            y, m, dd = (int(x) for x in d.split("-"))
            if _date(y, m, dd) >= cutoff:
                continue  # today-so-far / future rows never accounted (R1: completed dates only)
        except ValueError:
            errors[d] = "unparseable date"
            continue
        row = accounting_row(d, by_date[d])
        try:
            do_append(row, fdr)
            dates_appended.append(d)
        except Exception as exc:  # noqa: BLE001 -- one date's append failure must not block siblings
            errors[d] = str(exc)[:200]

    success = not errors
    if success:
        watermarks[STATE_KEY] = {"last_run_ts": _now_iso(), "dates_appended": dates_appended}
    return {"status": "ran", "dates_appended": dates_appended, "errors": errors,
           "watermark_stamped": success, "fdr_ledger": str(fdr)}


def main() -> int:  # pragma: no cover
    out = run_false_discovery_accounting({})
    for d in out["dates_appended"]:
        print("appended %s" % d)
    print(json.dumps({k: out[k] for k in ("status", "dates_appended", "errors", "watermark_stamped")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_false_discovery_accounting", "accounting_row", "main",
          "FDR_LEDGER_PATH", "STATE_KEY"]
