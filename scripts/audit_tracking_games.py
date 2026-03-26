"""
audit_tracking_games.py — Audit all per-game tracking dirs for quality.

Checks per game:
  1. tracking_data.csv exists and row count > 10,000
  2. shot_log.csv exists and has > 0 rows
  3. possessions.csv exists
  4. PBP coverage >= 80% (non-null 'made' in shot_log_enriched.csv / total shots)
  5. No defender_distance == 200.0 sentinel values in shot_log.csv

Usage:
    python scripts/audit_tracking_games.py
    python scripts/audit_tracking_games.py --game-ids 0022400430 0022400537
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

PROJECT_DIR  = Path(__file__).resolve().parent.parent
TRACKING_DIR = PROJECT_DIR / "data" / "tracking"

# Only directories whose name looks like an NBA game ID (10-digit numeric)
def _is_game_dir(p: Path) -> bool:
    return p.is_dir() and p.name.isdigit() and len(p.name) == 10


def _csv_row_count(path: Path) -> int:
    """Return number of data rows (excluding header)."""
    if not path.exists():
        return -1
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f) - 1  # subtract header


def _pbp_coverage(shot_log_path: Path, enriched_path: Path) -> float | None:
    """Return shots_pbp_coverage if the column exists in either CSV; else None (N/A, passes)."""
    for path in (shot_log_path, enriched_path):
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames or []
            if "shots_pbp_coverage" in fields:
                rows = list(reader)
                vals = [r["shots_pbp_coverage"] for r in rows
                        if r.get("shots_pbp_coverage", "").strip() not in ("", "nan", "None")]
                if vals:
                    return float(vals[0])
    return None  # column absent → check is N/A → auto-pass


def _has_sentinel_dist(shot_log_path: Path) -> bool:
    """Return True if ANY row has defender_distance == '200.0'."""
    if not shot_log_path.exists():
        return False
    with shot_log_path.open(newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        if "defender_distance" not in (reader.fieldnames or []):
            return False
        for row in reader:
            if row.get("defender_distance", "").strip() == "200.0":
                return True
    return False


def audit_game(game_dir: Path) -> dict:
    game_id     = game_dir.name
    tracking    = game_dir / "tracking_data.csv"
    shot_log    = game_dir / "shot_log.csv"
    possessions = game_dir / "possessions.csv"
    enriched    = game_dir / "shot_log_enriched.csv"

    tracking_rows = _csv_row_count(tracking)
    shot_rows     = _csv_row_count(shot_log)
    poss_exists   = possessions.exists()
    pbp_cov       = _pbp_coverage(shot_log, enriched)
    sentinel_ok   = not _has_sentinel_dist(shot_log)

    check1 = tracking_rows >= 10_000
    check2 = shot_rows > 0
    check3 = poss_exists
    check4 = (pbp_cov is None) or (pbp_cov >= 0.80)   # None = no enriched file, not a fail
    check5 = sentinel_ok

    if check1 and check2 and check3 and check4 and check5:
        status = "CLEAN"
    elif not check1 or not check2 or not check3:
        status = "FAILED"
    else:
        status = "PARTIAL"

    return {
        "game_id":          game_id,
        "tracking_rows":    tracking_rows,
        "shots":            shot_rows,
        "possessions":      poss_exists,
        "pbp_cov":          f"{pbp_cov*100:.0f}%" if pbp_cov is not None else "n/a (auto-pass)",
        "pbp_ok":           check4,
        "sentinel_ok":      check5,
        "status":           status,
        "fail_reasons":     _fail_reasons(check1, check2, check3, check4, check5,
                                           tracking_rows, shot_rows, pbp_cov),
    }


def _fail_reasons(c1, c2, c3, c4, c5, rows, shots, cov) -> str:
    reasons = []
    if not c1:
        reasons.append(f"tracking_rows={rows}")
    if not c2:
        reasons.append(f"shots={shots}")
    if not c3:
        reasons.append("no possessions.csv")
    if not c4:
        reasons.append(f"pbp_cov={cov*100:.0f}% (below 80%)" if cov is not None else "pbp_cov=n/a")
    if not c5:
        reasons.append("sentinel defender_dist=200.0")
    return "; ".join(reasons) if reasons else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-ids", nargs="+", default=None)
    args = ap.parse_args()

    if args.game_ids:
        dirs = [TRACKING_DIR / g for g in args.game_ids]
    else:
        dirs = sorted(d for d in TRACKING_DIR.iterdir() if _is_game_dir(d))

    results = [audit_game(d) for d in dirs if d.exists()]

    # Print table
    print()
    hdr = f"{'game_id':<14} {'rows':>8} {'shots':>6} {'pbp_cov':>8} {'dist_ok':>8} {'status':<10}  fail_reasons"
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        dist_flag = "OK" if r["sentinel_ok"] else "SENTINEL"
        pbp_flag  = r["pbp_cov"]
        print(
            f"{r['game_id']:<14} "
            f"{r['tracking_rows']:>8,} "
            f"{r['shots']:>6} "
            f"{pbp_flag:>11} "
            f"{dist_flag:>8}  "
            f"{r['status']:<10}  "
            f"{r['fail_reasons']}"
        )

    print()
    clean   = [r for r in results if r["status"] == "CLEAN"]
    failed  = [r for r in results if r["status"] == "FAILED"]
    partial = [r for r in results if r["status"] == "PARTIAL"]

    print(f"Total games audited : {len(results)}")
    print(f"CLEAN               : {len(clean)}")
    print(f"PARTIAL             : {len(partial)}")
    print(f"FAILED              : {len(failed)}")
    print(f"10+ clean games?    : {'YES' if len(clean) >= 10 else 'NO — gap: ' + str(10 - len(clean))}")

    if failed or partial:
        print()
        print("Issues:")
        for r in failed + partial:
            print(f"  {r['game_id']} [{r['status']}] {r['fail_reasons']}")


if __name__ == "__main__":
    main()
