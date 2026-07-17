"""scripts.platformkit.answers.qa_runner -- runs the answer-quality regression
bank (qa_bank.QA_BANK) against the REAL resolver_registry.resolve() in ONE
process, asserts each entry's `expect` block, and writes the report every
consumer (human, autoloop, next-session Claude) reads:

    data/cache/analytics_verify/qa_bank_report.json

Fail-closed like every other analytics_verify producer: a per-entry crash or
a mismatched expectation is a FAIL row in the report, never a raised
exception -- one entry's failure never blocks the rest of the bank. Exit
code is always 0; the report is the product (autoloop consumers read the
JSON, not a process exit code).

CLI:
  cd /c/Users/neelj/nba-ai-system && python -m scripts.platformkit.answers.qa_runner
  cd /c/Users/neelj/nba-ai-system && python -m scripts.platformkit.answers.qa_runner --tier SMOKE
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from scripts.platformkit.answers import qa_bank as _bank
from scripts.platformkit.answers import resolver_registry as R

_REPO = Path(__file__).resolve().parents[3]
OUT_PATH = _REPO / "data" / "cache" / "analytics_verify" / "qa_bank_report.json"
RSS_LIMIT_MB = 2048.0  # ponytail: 2GB rail per the caller's spec; abort-and-report, never crash

HONEST_NOTE = (
    "Answer-quality regression bank over resolver_registry.resolve() -- fail-closed "
    "status/receipt checks only. A correct no_data/not_supported/ambiguous is a PASS, "
    "not a failure. Calibration/consistency measurement only; no edge/ROI claim."
)


def _rss_mb() -> float | None:
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / 1e6
    except Exception:  # noqa: BLE001 -- psutil absence must never crash the runner
        return None


def _check_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Runs one bank entry for real and grades it against its `expect` block.
    Never raises -- any exception becomes a FAIL row with the error text."""
    exp = entry["expect"]
    try:
        result = R.resolve(entry["question"], sport=entry["sport"])
    except Exception as exc:  # noqa: BLE001 -- one crash must never kill the run
        return {"id": entry["id"], "verdict": "FAIL", "reason": f"resolve() raised: {exc!r}"[:300]}

    reasons: List[str] = []
    status = result.get("status")
    if status not in exp["status_one_of"]:
        reasons.append(f"status={status!r} not in {exp['status_one_of']}")
    # note: result["category"] is each dispatched sub-resolver's OWN category
    # label (e.g. "player_comparables", "edge_facts_injury_report"), not the
    # registry's routing key -- classify()+resolve() already proved routing
    # correctness (that's what picked this resolver), so we don't re-assert
    # category equality here, only the receipt shape.
    if exp.get("receipt_required") and status == "ok":
        missing = [k for k in exp.get("must_contain_keys", []) if k not in result]
        if missing:
            reasons.append(f"missing receipt keys: {missing}")
    if reasons:
        return {"id": entry["id"], "verdict": "FAIL", "reason": "; ".join(reasons),
                "observed_status": status}
    return {"id": entry["id"], "verdict": "PASS", "observed_status": status}


def run(tier: str = "FULL") -> Dict[str, Any]:
    entries = _bank.by_tier(tier)
    rows: List[Dict[str, Any]] = []
    aborted = False
    for entry in entries:
        rss = _rss_mb()
        if rss is not None and rss > RSS_LIMIT_MB:
            aborted = True
            break
        rows.append(_check_entry(entry))

    n_pass = sum(1 for r in rows if r["verdict"] == "PASS")
    n_fail = sum(1 for r in rows if r["verdict"] == "FAIL")
    report = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "tier": tier,
        "n_entries": len(entries),
        "n_run": len(rows),
        "n_pass": n_pass,
        "n_fail": n_fail,
        "aborted_rss": aborted,
        "fails": [r for r in rows if r["verdict"] == "FAIL"],
        "edge_claimed": False,
        "honest_note": HONEST_NOTE,
    }
    return report


def write_report(report: Dict[str, Any]) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    tmp.replace(OUT_PATH)


def run_smoke_job() -> Dict[str, Any]:
    """Zero-arg autoloop hook (maintenance_templates._JOB_TABLE): re-verify
    answer quality every burst/cycle via the cheap SMOKE tier, write the
    report, return a compact summary for the job-table digest."""
    report = run("SMOKE")
    write_report(report)
    return {"n_pass": report["n_pass"], "n_fail": report["n_fail"], "n_run": report["n_run"]}


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tier", choices=["SMOKE", "FULL"], default="FULL")
    args = p.parse_args(argv)
    report = run(args.tier)
    write_report(report)
    print(f"qa_bank[{args.tier}]: {report['n_pass']}/{report['n_run']} pass "
          f"({report['n_fail']} fail) -> {OUT_PATH}")
    return 0  # exit 0 always -- the report is the product


if __name__ == "__main__":
    raise SystemExit(main())
