"""scripts.platformkit.answers.coverage_stress -- runs coverage_bank.jsonl (the
question-diversity stress bank, distinct from qa_bank.py's graded regression
bank) through resolver_registry.resolve() in ONE process and writes the
coverage scoreboard every consumer reads:

    data/cache/analytics_verify/coverage_stress_report.json

Fail-closed like qa_runner: one row's crash is recorded as an "error" status
row, never a raised exception -- it must never kill the run. The headline
number is coverage over expects_answer=true rows ONLY (a correct no_data /
not_supported / ambiguous / refused on an expects_answer=false row is a PASS
for that row's design, not a gap -- see docs/JOB_EVIDENCE_PACKET.md framing:
an honest refusal/no_data is a success, not a failure).

CLI:
  cd /c/Users/neelj/nba-ai-system && python -m scripts.platformkit.answers.coverage_stress
  cd /c/Users/neelj/nba-ai-system && python -m scripts.platformkit.answers.coverage_stress --bank path/to/bank.jsonl

ponytail: NOT run on this laptop (RAM discipline) -- the pod runs the full
176-row bank; this file is proof-read + a small monkeypatched test only.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_REPO = Path(__file__).resolve().parents[3]
BANK_PATH = _REPO / "scripts" / "platformkit" / "answers" / "coverage_bank.jsonl"
OUT_PATH = _REPO / "data" / "cache" / "analytics_verify" / "coverage_stress_report.json"

_STATUSES = ("ok", "no_data", "not_supported", "ambiguous", "refused", "error")


def load_bank(path: Path = BANK_PATH) -> List[Dict[str, Any]]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _blank_rollup() -> Dict[str, int]:
    return {"n": 0, **{s: 0 for s in _STATUSES}}


def _run_row(row: Dict[str, Any], resolve_fn) -> Dict[str, Any]:
    """Runs one bank row for real. Never raises -- any exception becomes an
    'error' status row (a crash IS a recorded status, never a killed run)."""
    t0 = time.perf_counter()
    try:
        result = resolve_fn(row["q"], row["sport"])
        status = result.get("status", "error")
        category = result.get("category")
        note = result.get("note") or ""
    except Exception as exc:  # noqa: BLE001 -- one crash must never kill the run
        status = "error"
        category = None
        note = f"resolve() raised: {exc!r}"
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    if status not in _STATUSES:
        status = "error"
    out = {
        "q": row["q"], "sport": row["sport"], "kind": row["kind"],
        "expects_answer": row["expects_answer"], "category": category,
        "status": status, "latency_ms": latency_ms,
    }
    if status != "ok" and note:
        out["note_head"] = note[:120]
    return out


def run(bank: List[Dict[str, Any]], resolve_fn=None) -> Dict[str, Any]:
    """Runs every row in ONE process. `resolve_fn` defaults to the real
    resolver_registry.resolve (imported lazily so tests can monkeypatch it
    without importing the heavy resolver stack)."""
    if resolve_fn is None:
        from scripts.platformkit.answers import resolver_registry as R
        resolve_fn = R.resolve

    rows = [_run_row(r, resolve_fn) for r in bank]

    per_sport: Dict[str, Dict[str, int]] = defaultdict(_blank_rollup)
    per_category: Dict[str, Dict[str, int]] = defaultdict(_blank_rollup)
    for r in rows:
        per_sport[r["sport"]]["n"] += 1
        per_sport[r["sport"]][r["status"]] += 1
        cat = r["category"] or "(uncategorized)"
        per_category[cat]["n"] += 1
        per_category[cat][r["status"]] += 1

    answerable = [r for r in rows if r["expects_answer"]]
    n_answerable = len(answerable)
    n_answerable_ok = sum(1 for r in answerable if r["status"] == "ok")
    coverage_rate = round(n_answerable_ok / n_answerable, 4) if n_answerable else None

    gaps = sorted(
        ({"q": r["q"], "sport": r["sport"], "kind": r["kind"], "category": r["category"],
          "status": r["status"], "note_head": r.get("note_head", "")}
         for r in answerable if r["status"] != "ok"),
        key=lambda g: (g["sport"], g["kind"]),
    )

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "n_rows": len(rows),
        "n_expects_answer_true": n_answerable,
        "n_expects_answer_true_ok": n_answerable_ok,
        "coverage_rate": coverage_rate,
        "coverage_rate_note": "honest headline: n_expects_answer_true_ok / n_expects_answer_true "
                               "ONLY -- expects_answer=false rows are excluded (a correct "
                               "no_data/not_supported/ambiguous/refused there is a design PASS, "
                               "not counted toward or against coverage)",
        "per_sport": dict(per_sport),
        "per_category": dict(per_category),
        "gaps": gaps,
        "rows": rows,
        "edge_claimed": False,
    }


def write_report(report: Dict[str, Any], out_path: Path = OUT_PATH) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    tmp.replace(out_path)


def _print_summary(report: Dict[str, Any]) -> None:
    print(f"coverage_stress: {report['n_rows']} rows run")
    cov = report["coverage_rate"]
    print(f"headline coverage (expects_answer=true only): "
          f"{report['n_expects_answer_true_ok']}/{report['n_expects_answer_true']} "
          f"({cov * 100:.1f}%)" if cov is not None else "headline coverage: n/a (0 answerable rows)")
    print()
    header = f"{'sport':<10}" + "".join(f"{s:<15}" for s in _STATUSES)
    print(header)
    print("-" * len(header))
    for sport in sorted(report["per_sport"]):
        r = report["per_sport"][sport]
        print(f"{sport:<10}" + "".join(f"{r[s]:<15}" for s in _STATUSES) + f"  n={r['n']}")
    print()
    print(f"{'category':<28}" + "".join(f"{s:<15}" for s in _STATUSES))
    for cat in sorted(report["per_category"]):
        r = report["per_category"][cat]
        print(f"{cat:<28}" + "".join(f"{r[s]:<15}" for s in _STATUSES) + f"  n={r['n']}")
    print()
    print(f"gaps (expects_answer=true, not ok): {len(report['gaps'])}")
    for g in report["gaps"][:20]:
        print(f"  [{g['sport']}/{g['kind']}] {g['status']:<14} {g['q'][:70]}")
    if len(report["gaps"]) > 20:
        print(f"  ... and {len(report['gaps']) - 20} more (see report file)")


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--bank", default=str(BANK_PATH))
    args = p.parse_args(argv)
    bank = load_bank(Path(args.bank))
    report = run(bank)
    write_report(report)
    _print_summary(report)
    print(f"\nreport written -> {OUT_PATH}")
    return 0  # exit 0 always -- the report is the product, never a raised failure


if __name__ == "__main__":
    raise SystemExit(main())
