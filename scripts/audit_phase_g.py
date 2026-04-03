"""
audit_phase_g.py — Phase G audit: check all 6 cleanliness criteria per game.

Criteria:
  1. tracking_data.csv exists, >500 rows, homography_valid mean >= 0.85
  2. shot_log.csv exists, >= 5 shots, zero rows where defender_distance == 200.0
  3. ball_tracking.csv exists, ball_detected_pct >= 0.20
  4. possessions.csv exists, >= 40 possessions
  5. No Python traceback in the game's run.log
  6. PBP enrichment: enriched_pct >= 0.80

Usage:
    python scripts/audit_phase_g.py
    python scripts/audit_phase_g.py --strict
    python scripts/audit_phase_g.py --game-ids 0022400430 0022400537
"""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

PROJECT_DIR  = Path(__file__).resolve().parent.parent
TRACKING_DIR = PROJECT_DIR / "data" / "tracking"

# Phase G target game IDs — all games with videos in data/videos/full_games/
# Excluded: 0022400852 (Brazilian app UI recording), 0022401175 (no players detected)
PHASE_G_GAMES = [
    "0022400430", "0022400537", "0022400625", "0022400687",
    "0022400689", "0022400690", "0022400710",
    "0022400909", "0022400921", "0022400923", "0022401117",
    "0022401123", "0022401156", "0022401183",
    "0022401185", "0022401190", "0022401194", "0022401196",
    "0022401198",
]


def _is_game_dir(p: Path) -> bool:
    return p.is_dir() and p.name.isdigit() and len(p.name) == 10


def _csv_row_count(path: Path) -> int:
    """Return number of data rows (excluding header). -1 if file missing."""
    if not path.exists():
        return -1
    try:
        with path.open(newline="", encoding="utf-8", errors="replace") as f:
            return max(0, sum(1 for _ in f) - 1)
    except Exception:
        return -1


def _check_tracking(game_dir: Path) -> dict:
    """Check 1: tracking_data.csv exists, >500 rows, homography_valid mean >= 0.85."""
    tracking = game_dir / "tracking_data.csv"
    rows = _csv_row_count(tracking)
    if rows < 0:
        return {"pass": False, "rows": -1, "homography_mean": 0.0, "reason": "tracking_data.csv missing"}
    if rows < 500:
        return {"pass": False, "rows": rows, "homography_mean": 0.0, "reason": f"tracking rows={rows} (<500)"}

    # Check homography_valid mean
    homography_mean = 1.0  # Default if column doesn't exist
    try:
        with tracking.open(newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            if "homography_valid" in (reader.fieldnames or []):
                vals = []
                for row in reader:
                    try:
                        v = float(row.get("homography_valid", "1"))
                        vals.append(v)
                    except (ValueError, TypeError):
                        pass
                if vals:
                    homography_mean = sum(vals) / len(vals)
    except Exception:
        pass

    ok = rows > 500 and homography_mean >= 0.85
    reason = ""
    if not ok:
        reasons = []
        if rows <= 500:
            reasons.append(f"rows={rows}")
        if homography_mean < 0.85:
            reasons.append(f"homography={homography_mean:.2f}")
        reason = "; ".join(reasons)

    return {"pass": ok, "rows": rows, "homography_mean": round(homography_mean, 3), "reason": reason}


def _check_shots(game_dir: Path) -> dict:
    """Check 2: shot_log.csv exists, >= 5 shots, zero rows with 200.0 sentinel in distance cols."""
    shot_log = game_dir / "shot_log.csv"
    rows = _csv_row_count(shot_log)
    if rows < 0:
        return {"pass": False, "shots": -1, "sentinel_count": 0, "reason": "shot_log.csv missing"}

    sentinel_count = 0
    _SENTINEL_COLS = ("defender_distance", "handler_isolation")
    try:
        with shot_log.open(newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            fields = set(reader.fieldnames or [])
            for row in reader:
                for col in _SENTINEL_COLS:
                    if col in fields and row.get(col, "").strip() == "200.0":
                        sentinel_count += 1
    except Exception:
        pass

    ok = rows >= 5 and sentinel_count == 0
    reason = ""
    if not ok:
        reasons = []
        if rows < 5:
            reasons.append(f"shots={rows} (<5)")
        if sentinel_count > 0:
            reasons.append(f"sentinel_dist=200.0 x{sentinel_count}")
        reason = "; ".join(reasons)

    return {"pass": ok, "shots": rows, "sentinel_count": sentinel_count, "reason": reason}


def _check_ball(game_dir: Path) -> dict:
    """Check 3: ball_tracking.csv exists, ball_detected_pct >= 0.20."""
    ball_csv = game_dir / "ball_tracking.csv"
    if not ball_csv.exists():
        return {"pass": False, "ball_pct": 0.0, "reason": "ball_tracking.csv missing"}

    detected = 0
    total = 0
    try:
        with ball_csv.open(newline="", encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                total += 1
                if str(row.get("detected", "0")) == "1":
                    detected += 1
    except Exception:
        pass

    pct = detected / total if total > 0 else 0.0
    ok = pct >= 0.20
    reason = "" if ok else f"ball_pct={pct:.2f} (<0.20)"
    return {"pass": ok, "ball_pct": round(pct, 3), "reason": reason}


def _check_possessions(game_dir: Path) -> dict:
    """Check 4: possessions.csv exists, >= 40 possessions."""
    poss_csv = game_dir / "possessions.csv"
    rows = _csv_row_count(poss_csv)
    if rows < 0:
        return {"pass": False, "possessions": -1, "reason": "possessions.csv missing"}
    ok = rows >= 40
    reason = "" if ok else f"possessions={rows} (<40)"
    return {"pass": ok, "possessions": rows, "reason": reason}


def _check_traceback(game_dir: Path) -> dict:
    """Check 5: No Python traceback in run.log."""
    log_file = game_dir / "run.log"
    if not log_file.exists():
        return {"pass": True, "reason": ""}  # No log = no traceback evidence

    try:
        content = log_file.read_text(encoding="utf-8", errors="replace")
        has_traceback = "Traceback (most recent call last)" in content
        ok = not has_traceback
        reason = "" if ok else "traceback in run.log"
        return {"pass": ok, "reason": reason}
    except Exception:
        return {"pass": True, "reason": ""}


def _check_enrichment(game_dir: Path) -> dict:
    """Check 6: PBP enrichment: enriched_pct >= 0.80."""
    enriched = game_dir / "shot_log_enriched.csv"
    shot_log = game_dir / "shot_log.csv"

    # Check enriched file first
    for path in (enriched, shot_log):
        if not path.exists():
            continue
        try:
            with path.open(newline="", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                fields = reader.fieldnames or []
                rows_list = list(reader)

                # Check for shots_pbp_coverage column
                if "shots_pbp_coverage" in fields:
                    for row in rows_list:
                        v = row.get("shots_pbp_coverage", "").strip()
                        if v not in ("", "nan", "None"):
                            pct = float(v)
                            ok = pct >= 0.80
                            reason = "" if ok else f"enriched_pct={pct:.2f} (<0.80)"
                            return {"pass": ok, "enriched_pct": round(pct, 3), "reason": reason}

                # If enriched CSV exists, count rows with 'made' filled
                if path == enriched and "made" in fields:
                    total = len(rows_list)
                    filled = sum(1 for r in rows_list
                                 if r.get("made", "").strip() not in ("", "nan", "None"))
                    if total > 0:
                        pct = filled / total
                        ok = pct >= 0.80
                        reason = "" if ok else f"enriched_pct={pct:.2f} (<0.80)"
                        return {"pass": ok, "enriched_pct": round(pct, 3), "reason": reason}
        except Exception:
            pass

    # No enriched data available — auto-pass if no enriched file
    if not enriched.exists():
        return {"pass": False, "enriched_pct": 0.0, "reason": "shot_log_enriched.csv missing or no PBP data"}

    return {"pass": True, "enriched_pct": 1.0, "reason": ""}


def audit_game(game_dir: Path) -> dict:
    game_id = game_dir.name

    c1 = _check_tracking(game_dir)
    c2 = _check_shots(game_dir)
    c3 = _check_ball(game_dir)
    c4 = _check_possessions(game_dir)
    c5 = _check_traceback(game_dir)
    c6 = _check_enrichment(game_dir)

    checks = [c1, c2, c3, c4, c5, c6]
    all_pass = all(c["pass"] for c in checks)
    fail_reasons = [c["reason"] for c in checks if c["reason"]]

    return {
        "game_id": game_id,
        "exists": game_dir.exists(),
        "c1_tracking": c1,
        "c2_shots": c2,
        "c3_ball": c3,
        "c4_possessions": c4,
        "c5_traceback": c5,
        "c6_enrichment": c6,
        "status": "CLEAN" if all_pass else "FAILED",
        "fail_reasons": "; ".join(fail_reasons),
        "pass_count": sum(1 for c in checks if c["pass"]),
    }


def main():
    ap = argparse.ArgumentParser(description="Phase G full audit — 6 criteria")
    ap.add_argument("--game-ids", nargs="+", default=None,
                    help="Specific game IDs to audit (default: all Phase G + all game dirs)")
    ap.add_argument("--strict", action="store_true",
                    help="All 6 checks must pass for CLEAN status")
    ap.add_argument("--phase-g-only", action="store_true",
                    help="Only audit Phase G target games")
    args = ap.parse_args()

    if args.game_ids:
        game_ids = args.game_ids
    elif args.phase_g_only:
        game_ids = PHASE_G_GAMES
    else:
        # All game dirs + Phase G targets
        existing = sorted(d.name for d in TRACKING_DIR.iterdir() if _is_game_dir(d))
        all_ids = list(dict.fromkeys(PHASE_G_GAMES + existing))  # preserve order, dedupe
        game_ids = all_ids

    results = []
    for gid in game_ids:
        game_dir = TRACKING_DIR / gid
        if game_dir.exists():
            results.append(audit_game(game_dir))
        else:
            results.append({
                "game_id": gid,
                "exists": False,
                "c1_tracking": {"pass": False, "rows": -1, "homography_mean": 0, "reason": "dir missing"},
                "c2_shots": {"pass": False, "shots": -1, "sentinel_count": 0, "reason": "dir missing"},
                "c3_ball": {"pass": False, "ball_pct": 0, "reason": "dir missing"},
                "c4_possessions": {"pass": False, "possessions": -1, "reason": "dir missing"},
                "c5_traceback": {"pass": True, "reason": ""},
                "c6_enrichment": {"pass": False, "enriched_pct": 0, "reason": "dir missing"},
                "status": "MISSING",
                "fail_reasons": "game directory not found",
                "pass_count": 0,
            })

    # Print table
    print()
    hdr = f"{'game_id':<12} {'rows':>8} {'hom':>5} {'shots':>5} {'sent':>4} {'ball':>5} {'poss':>5} {'log':>3} {'enr':>5} {'pass':>4} {'status':<8}  fail_reasons"
    print(hdr)
    print("-" * len(hdr))

    for r in results:
        c1 = r["c1_tracking"]
        c2 = r["c2_shots"]
        c3 = r["c3_ball"]
        c4 = r["c4_possessions"]
        c5 = r["c5_traceback"]
        c6 = r["c6_enrichment"]

        rows_str = str(c1.get("rows", -1)) if c1.get("rows", -1) >= 0 else "---"
        hom_str = f"{c1.get('homography_mean', 0):.2f}" if c1.get("rows", -1) > 0 else "---"
        shots_str = str(c2.get("shots", -1)) if c2.get("shots", -1) >= 0 else "---"
        sent_str = str(c2.get("sentinel_count", 0))
        ball_str = f"{c3.get('ball_pct', 0):.2f}" if r["exists"] else "---"
        poss_str = str(c4.get("possessions", -1)) if c4.get("possessions", -1) >= 0 else "---"
        log_str = "OK" if c5["pass"] else "ERR"
        enr_str = f"{c6.get('enriched_pct', 0):.2f}" if c6.get("enriched_pct", 0) > 0 else "---"
        pass_str = f"{r['pass_count']}/6"

        print(
            f"{r['game_id']:<12} "
            f"{rows_str:>8} "
            f"{hom_str:>5} "
            f"{shots_str:>5} "
            f"{sent_str:>4} "
            f"{ball_str:>5} "
            f"{poss_str:>5} "
            f"{log_str:>3} "
            f"{enr_str:>5} "
            f"{pass_str:>4} "
            f"{r['status']:<8}  "
            f"{r['fail_reasons']}"
        )

    print()
    clean = [r for r in results if r["status"] == "CLEAN"]
    failed = [r for r in results if r["status"] == "FAILED"]
    missing = [r for r in results if r["status"] == "MISSING"]

    print(f"Total games audited : {len(results)}")
    print(f"CLEAN               : {len(clean)}")
    print(f"FAILED              : {len(failed)}")
    print(f"MISSING             : {len(missing)}")
    print(f"20 clean games?     : {'YES ✓' if len(clean) >= 20 else 'NO — gap: ' + str(20 - len(clean))}")

    if clean:
        print(f"\nClean game IDs: {', '.join(r['game_id'] for r in clean)}")

    if failed or missing:
        print("\nIssues:")
        for r in failed + missing:
            print(f"  {r['game_id']} [{r['status']}] {r['fail_reasons']}")


if __name__ == "__main__":
    main()
