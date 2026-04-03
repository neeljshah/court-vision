"""
clean_shot_log.py — Retroactively clean over-detected shots in existing shot_log.csv files.

Applies the same guards that are now in the live pipeline (post ISSUE-040 fix):
  1. Global 5-second debounce   — keep only one shot every 5s game-time
  2. Backcourt filter           — remove shots from mid-court band (x_norm 0.40-0.60)
  3. Handler zone filter        — remove shots where shooter is far from either basket
                                  (x_norm < 0.05 or x_norm > 0.95 = behind the baseline)

Run:
    python scripts/clean_shot_log.py                      # all games in data/tracking/
    python scripts/clean_shot_log.py --game-ids 0022400430 0022400537
    python scripts/clean_shot_log.py --dry-run            # print stats, don't write

Backup:
    Original files saved as shot_log.csv.bak before any write.
"""

import argparse
import csv
import os
import shutil
import sys

# ── Config ────────────────────────────────────────────────────────────────────
DATA_DIR      = os.path.join(os.path.dirname(__file__), "..", "data", "tracking")
DEBOUNCE_SEC  = 10.0   # minimum real-time seconds between kept shots
                       # NBA pace ≈ 1 FGA every 14s per team; 10s debounce keeps
                       # ~1 shot every 10s and allows up to 60/10min which is realistic
BACKCOURT_LO  = 0.40   # x_norm — mid-court start  (ISSUE-047 fix mirrors this band)
BACKCOURT_HI  = 0.60   # x_norm — mid-court end
BASELINE_LO   = 0.04   # x_norm — too close behind left baseline
BASELINE_HI   = 0.96   # x_norm — too close behind right baseline


def _load_games(data_dir: str, game_ids: list) -> list:
    games = []
    if game_ids:
        for gid in game_ids:
            path = os.path.join(data_dir, gid, "shot_log.csv")
            if os.path.exists(path):
                games.append((gid, path))
            else:
                print(f"  [WARN] {gid}: shot_log.csv not found, skipping")
    else:
        for entry in sorted(os.listdir(data_dir)):
            path = os.path.join(data_dir, entry, "shot_log.csv")
            if os.path.exists(path):
                games.append((entry, path))
    return games


def _clean(rows: list, debounce_sec: float = DEBOUNCE_SEC) -> tuple:
    """Return (kept_rows, stats_dict)."""
    kept = []
    n_debounce = 0
    n_backcourt = 0
    n_baseline = 0
    last_ts = -999.0

    for row in rows:
        ts = float(row.get("timestamp") or 0)
        xn = row.get("x_norm") or row.get("x_position")  # fallback to raw if norm missing

        # Try to parse x_norm
        try:
            xn_f = float(xn) if xn not in ("", None) else None
        except (ValueError, TypeError):
            xn_f = None

        # 1. Global debounce
        if ts - last_ts < debounce_sec:
            n_debounce += 1
            continue

        # 2. Backcourt band filter (mid-court: 40-60% of court width)
        if xn_f is not None and BACKCOURT_LO < xn_f < BACKCOURT_HI:
            n_backcourt += 1
            continue

        # 3. Behind-baseline filter (< 4% or > 96% of court)
        if xn_f is not None and (xn_f < BASELINE_LO or xn_f > BASELINE_HI):
            n_baseline += 1
            continue

        kept.append(row)
        last_ts = ts

    stats = {
        "original": len(rows),
        "kept":     len(kept),
        "removed_debounce":  n_debounce,
        "removed_backcourt": n_backcourt,
        "removed_baseline":  n_baseline,
    }
    return kept, stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-ids", nargs="*", default=[])
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing")
    parser.add_argument("--debounce", type=float, default=DEBOUNCE_SEC,
                        help=f"Minimum seconds between kept shots (default {DEBOUNCE_SEC})")
    args = parser.parse_args()

    games = _load_games(DATA_DIR, args.game_ids)
    if not games:
        print("No shot_log.csv files found.")
        sys.exit(1)

    total_before = 0
    total_after  = 0

    for gid, path in games:
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            rows   = list(reader)
            fields = reader.fieldnames or []

        if not rows:
            print(f"  {gid}: empty — skip")
            continue

        kept, stats = _clean(rows, debounce_sec=args.debounce)
        total_before += stats["original"]
        total_after  += stats["kept"]

        print(
            f"  {gid}: {stats['original']:>4} → {stats['kept']:>4} shots  "
            f"(-{stats['removed_debounce']} debounce "
            f"-{stats['removed_backcourt']} backcourt "
            f"-{stats['removed_baseline']} baseline)"
        )

        if args.dry_run:
            continue

        # Re-number shot_id column sequentially
        for i, row in enumerate(kept, start=1):
            if "shot_id" in row:
                row["shot_id"] = str(i)

        bak = path + ".bak"
        if not os.path.exists(bak):
            shutil.copy2(path, bak)

        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(kept)

    mode = "(DRY RUN)" if args.dry_run else "(WRITTEN)"
    print(f"\n{'='*60}")
    print(f"TOTAL {mode}: {total_before} → {total_after} shots")
    print(f"Removed {total_before - total_after} over-detected events")
    if not args.dry_run:
        print("Originals backed up as shot_log.csv.bak")


if __name__ == "__main__":
    main()
