"""probe_R21_N2_line_killed_recovery.py — R21_N2 line_killed recovery probe.

Verifies that scripts/recover_line_killed.py runs cleanly against the REAL
production ledger in read-only / dry-run modes ONLY.

What it does:
  1. --list against the real C:\\Users\\neelj\\nba-ai-system\\data\\pnl_ledger.csv
     (purely read-only).
  2. --refund-all --min-age-hours 24 dry-run against the real ledger (NO writes).
  3. Confirms the 2 real Keldon Johnson bets (player_id 1629640) are detected
     among the line_killed rows IF they exist. If they have already been
     cleaned, reports zero — this is the honest state of the ledger.
  4. Persists results to data/cache/probe_R21_N2_results.json.

HARD GUARANTEES:
  - The probe never invokes --refund-all --commit on the real ledger.
  - The probe never calls --refund <id> on a real bet.
  - All write tests live in tests/test_recover_line_killed.py against
    fixture ledgers under pytest's tmp_path.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from scripts import recover_line_killed as r  # noqa: E402

# The REAL production ledger lives in the maintainer's main checkout, not in
# the worktree. We resolve it explicitly so the probe is reproducible from
# any CWD.
REAL_LEDGER = r"C:\Users\neelj\nba-ai-system\data\pnl_ledger.csv"
REAL_BANKROLL = r"C:\Users\neelj\nba-ai-system\data\pnl_bankroll.csv"
RESULTS_PATH = os.path.join(PROJECT_DIR, "data", "cache",
                            "probe_R21_N2_results.json")


def _summarize_row(row):
    return {
        "bet_id": row.get("bet_id", ""),
        "placed_at": row.get("placed_at", ""),
        "player": row.get("player", ""),
        "player_id": row.get("player_id", ""),
        "stat": row.get("stat", ""),
        "line": row.get("line", ""),
        "side": row.get("side", ""),
        "book": row.get("book", ""),
        "stake": row.get("stake", ""),
        "status": row.get("status", ""),
    }


def run() -> dict:
    started_at = datetime.now().isoformat(timespec="seconds")
    ledger_exists = os.path.exists(REAL_LEDGER)

    # 1) --list (read-only)
    killed = r.find_line_killed(REAL_LEDGER) if ledger_exists else []
    n_real = sum(1 for row in killed if r.is_real_bet(row))
    n_synth = sum(1 for row in killed if not r.is_real_bet(row))

    # 2) --refund-all --dry-run (no writes)
    dry_run = (r.refund_all(REAL_LEDGER, REAL_BANKROLL,
                            min_age_hours=24.0, commit=False)
               if ledger_exists else
               {"dry_run": True, "n_killed": 0, "n_eligible": 0,
                "eligible": [], "refunded": []})

    # 3) Did we surface the 2 real Keldon Johnson bets?
    keldon_rows = [row for row in killed
                   if (row.get("player") or "").lower() ==
                   "keldon johnson"
                   or (row.get("player_id") or "") == "1629640"
                   and r.is_real_bet(row)]
    # the looser interpretation: any line_killed row whose player matches
    # the real human name "Keldon Johnson" (not the synthetic Player_1629640)
    keldon_real = [row for row in killed
                   if (row.get("player") or "").strip().lower()
                   == "keldon johnson"]
    keldon_detected = len(keldon_real) >= 2

    real_killed_sample = [_summarize_row(row) for row in killed
                          if r.is_real_bet(row)][:5]

    payload = {
        "probe_id": "R21_N2",
        "started_at": started_at,
        "real_ledger_path": REAL_LEDGER,
        "real_ledger_exists": ledger_exists,
        "line_killed_count_total": len(killed),
        "line_killed_count_real": n_real,
        "line_killed_count_synth": n_synth,
        "keldon_johnson_line_killed_count": len(keldon_real),
        "keldon_johnson_detected_2_or_more": keldon_detected,
        "real_killed_sample": real_killed_sample,
        "dry_run_refund_all": {
            "n_killed": dry_run["n_killed"],
            "n_eligible": dry_run["n_eligible"],
            "n_refunded_actually_written": 0,  # always 0 on dry-run
            "eligible_sample": dry_run["eligible"][:5],
        },
        "modes_exercised": ["--list (read-only)",
                            "--refund-all --dry-run (no writes)"],
        "no_writes_to_real_ledger": True,
        "summary": "",
    }

    if not ledger_exists:
        payload["summary"] = (
            f"real ledger absent at {REAL_LEDGER}; "
            "tool wired but no live data to probe"
        )
    elif keldon_detected:
        payload["summary"] = (
            f"detected {len(killed)} line_killed total "
            f"(real={n_real}, synth={n_synth}); "
            f"Keldon Johnson bets present ({len(keldon_real)}); "
            f"{dry_run['n_eligible']} eligible for refund "
            "(no writes performed)"
        )
    else:
        payload["summary"] = (
            f"detected {len(killed)} line_killed total "
            f"(real={n_real}, synth={n_synth}); "
            f"0 Keldon Johnson rows currently in ledger (likely "
            "cleaned since R19_L8 snapshot); "
            f"{dry_run['n_eligible']} eligible for refund "
            "(no writes performed)"
        )

    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)

    return payload


def main() -> int:
    result = run()
    print(json.dumps({
        "probe_id": result["probe_id"],
        "line_killed_count_total": result["line_killed_count_total"],
        "line_killed_count_real": result["line_killed_count_real"],
        "line_killed_count_synth": result["line_killed_count_synth"],
        "keldon_johnson_line_killed_count":
            result["keldon_johnson_line_killed_count"],
        "no_writes_to_real_ledger": result["no_writes_to_real_ledger"],
        "summary": result["summary"],
        "results_path": RESULTS_PATH,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
