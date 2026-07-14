"""scripts.platformkit.claims.claims_report -- P6 status report for the claims engine.

Assembles card_registry (latest row per card) + card_grader's card_ledger.jsonl
(latest graded verdict per card) + card_consumer's consumed-log into one table and
writes .planning/claims/CLAIMS_STATUS.md. Read-only against every other claims
module; this file only ever appends its own report artifact.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/claims/test_claims_report.py -q
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.claims import card_registry as _reg
from scripts.platformkit.claims.card_grader import LEDGER_PATH as _DEFAULT_LEDGER_PATH
from scripts.platformkit.claims.card_consumer import CONSUMED_PATH as _DEFAULT_CONSUMED_PATH

_REPO_ROOT = Path(__file__).resolve().parents[3]
STATUS_PATH = _REPO_ROOT / ".planning" / "claims" / "CLAIMS_STATUS.md"

# Every test file that makes up the conditional-claims engine (P1-P6). Run individually
# per the repo's per-file-test-only rule -- never as one combined `pytest tests/`.
TEST_FILES = [
    "tests/platformkit/claims/test_card_registry.py",
    "tests/platformkit/claims/test_card_miner.py",
    "tests/platformkit/claims/test_condition_tagger.py",
    "tests/platformkit/claims/test_card_grader.py",
    "tests/platformkit/claims/test_card_consumer.py",
    "tests/platformkit/claims/test_claims_report.py",
    "tests/platformkit/test_clv_ledger_claim_tags.py",
]


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="ascii", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _latest_by_card_id(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    latest: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        cid = r.get("card_id")
        if cid:
            latest[cid] = r
    return latest


def build_rows(*, registry_module=_reg, ledger_path: Optional[Path] = None,
               consumed_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """One row per card: id, claim, condition, fired-rate, n, halves-agree, verdict."""
    cards = registry_module.get_all_latest()
    ledger = _latest_by_card_id(_read_jsonl(ledger_path or _DEFAULT_LEDGER_PATH))
    consumed_ids = {r["card_id"] for r in _read_jsonl(consumed_path or _DEFAULT_CONSUMED_PATH)
                    if r.get("card_id")}
    rows: List[Dict[str, Any]] = []
    for card_id, card in sorted(cards.items()):
        grade = ledger.get(card_id)
        cond = card.get("condition") or {}
        n_fired = grade.get("n_fired", 0) if grade else 0
        n_total = grade.get("n_total") if grade else None
        fired_rate = "%.4f%%" % (100.0 * n_fired / n_total) if n_total else "n/a (0 rows)"
        detail = (grade or {}).get("detail") or {}
        halves_agree = "Y" if detail.get("cond_sign_match") else ("N" if detail else "n/a")
        rows.append({
            "card_id": card_id,
            "claim": (card.get("claim") or "")[:90],
            "scope": cond.get("scope"),
            "condition": (cond.get("trigger") or "")[:60],
            "fired_rate": fired_rate,
            "n_fired": n_fired,
            "halves_agree": halves_agree,
            "verdict": card.get("status", "?"),
            "consumed": card_id in consumed_ids,
        })
    return rows


def run_tests(test_files: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Run each known test file via subprocess and capture pass/fail counts. Never raises."""
    results = []
    for rel in (test_files or TEST_FILES):
        cmd = [sys.executable, "-m", "pytest", rel, "-q"]
        try:
            proc = subprocess.run(cmd, cwd=str(_REPO_ROOT), capture_output=True,
                                  text=True, timeout=300)
            tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
            results.append({"cmd": " ".join(cmd), "file": rel, "returncode": proc.returncode,
                            "summary": tail})
        except Exception as exc:  # noqa: BLE001
            results.append({"cmd": " ".join(cmd), "file": rel, "returncode": -1,
                            "summary": "ERROR: %s" % type(exc).__name__})
    return results


def build_report(*, registry_module=_reg, ledger_path: Optional[Path] = None,
                 consumed_path: Optional[Path] = None,
                 test_results: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    rows = build_rows(registry_module=registry_module, ledger_path=ledger_path,
                      consumed_path=consumed_path)
    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rows": rows, "counts": counts, "n_cards": len(rows),
        "n_validated": counts.get("VALIDATED", 0),
        "test_results": test_results or [],
        "highest_value_next_card": (
            "An INGAME style-mismatch card (mirroring card_1's midQ1-endQ1 window) is "
            "highest-value: it is the only scope with a real on-disk accrual path today "
            "(inplay_daytrader already merges claim_tags into the ingame grade files). "
            "Pregame cards now have a persistence path too (this lane's clv_ledger fix), "
            "but only accrue on NEW paper bets placed after the fix lands -- historical "
            "rows have no claim_tags. Next card: cross the transition-defense-mismatch "
            "pregame prior (card_06a04b0f42's condition) with its REALIZED early-game "
            "deviation, the same cross-term pattern as card_1, since 8 of the 9 pregame "
            "cards are single-factor priors with no in-game confirmation leg yet."
        ),
        "edge_claimed": False,
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# CLAIMS_STATUS -- conditional claims engine",
        "",
        "Generated: %s. Paper-only. edge_claimed: False." % report["generated_at"],
        "",
        "## Cards (%d total, %s)" % (report["n_cards"], report["counts"]),
        "",
        "| card_id | scope | claim | condition | fired-rate | n | halves-agree | verdict | consumed |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in report["rows"]:
        lines.append("| %s | %s | %s | %s | %s | %d | %s | %s | %s |" % (
            r["card_id"], r["scope"], r["claim"], r["condition"], r["fired_rate"],
            r["n_fired"], r["halves_agree"], r["verdict"], "Y" if r["consumed"] else "N"))
    lines += ["", "## What got wired where", "",
              "- P1 card_registry.py: pre-registration lock, 10 cards seeded (MAX_OPEN=10, 0 QUEUED).",
              "- P2 condition_tagger.py: wired into inplay_daytrader.on_tick (ingame) and "
              "run_paper_today._record_priced (pregame).",
              "- P3 card_grader.py: pooled game-clustered grading, 4-condition VALIDATED gate.",
              "- P4/P5 gap fix (this lane): clv_ledger.record_bet now persists claim_tags "
              "(additive, optional kwarg) -- pregame cards had ZERO on-disk source before this; "
              "they still need NEW paper bets placed post-fix to start accruing (no backfill "
              "of historical rows).",
              "- P5 card_consumer.py (this lane): consumption mechanism for VALIDATED cards -- "
              "ingame_routes.jsonl (shadow-only, default-OFF per-card env flag), "
              "pregame_trust_segments.jsonl (TRUSTED/ADVERSE sizing gate), proven_lines.jsonl "
              "(n + effect size). Built and tested against a SYNTHETIC validated card; 0 real "
              "cards qualify yet, so nothing has actually routed or been trusted in production.",
              "", "## Test commands + pass counts", ""]
    for t in report["test_results"]:
        lines.append("- `%s` -> rc=%d: %s" % (t["cmd"], t["returncode"], t["summary"]))
    lines += ["", "## Highest-value next card to register", "",
              report["highest_value_next_card"], "",
              "## Honest engine status", "",
              "10 cards accruing, 0 VALIDATED, 0 REJECTED, 0 STARVED. The 1 ingame card "
              "(card_1, pre-registered midQ1-endQ1 cross-term) has a live on-disk accrual "
              "path already wired; the 9 pregame style-mismatch cards were structurally "
              "inert until this lane's persistence fix, and even now only accrue from bets "
              "placed after the fix -- MIN_FIRED_PER_HALF=60 means real verdicts are weeks "
              "away at normal game volume, not days."]
    return "\n".join(lines)


def write_status(*, path: Optional[Path] = None, run_test_files: bool = True,
                 registry_module=_reg) -> Dict[str, Any]:
    """Build the report (optionally running tests) and write STATUS_PATH. Returns the report."""
    test_results = run_tests() if run_test_files else []
    report = build_report(registry_module=registry_module, test_results=test_results)
    out = Path(path) if path is not None else STATUS_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(report), encoding="ascii", errors="replace")
    return report


def main() -> int:
    report = write_status()
    print("wrote %s (%d cards, %d validated)" % (STATUS_PATH, report["n_cards"], report["n_validated"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["STATUS_PATH", "TEST_FILES", "build_rows", "run_tests", "build_report",
           "render_markdown", "write_status"]
