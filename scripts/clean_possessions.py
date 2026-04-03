"""
clean_possessions.py — Retroactively fix fragmented possessions in existing possessions.csv.

Applies the same merge/filter logic now in the live pipeline (post ISSUE-039 fix):
  1. Filter sub-2s possessions    — remove 0.35s flickers that are noise, not real plays
  2. Merge same-team chains       — consecutive same-team possessions with gap < MERGE_GAP
                                    frames are collapsed into one (e.g. loose ball, same
                                    team rebound, brief OOB all count as one possession)
  3. Report median duration        — should reach 8-20s for broadcast 10-min clips

Run:
    python scripts/clean_possessions.py                      # all games in data/tracking/
    python scripts/clean_possessions.py --game-ids 0022400430 0022400537
    python scripts/clean_possessions.py --dry-run            # print stats, don't write

Backup:
    Original files saved as possessions.csv.bak before any write.
"""

import argparse
import csv
import os
import shutil
import statistics
import sys

# ── Config ────────────────────────────────────────────────────────────────────
DATA_DIR       = os.path.join(os.path.dirname(__file__), "..", "data", "tracking")
MIN_DUR_SEC    = 2.0   # drop possessions shorter than this (noise / clip-edge)
MERGE_GAP_FRAMES = 300 # merge same-team possessions with ≤ this frame gap
                       # ≈ 10s at 30fps/stride-3 (300 abs frames / 30fps = 10s)


def _load_games(data_dir: str, game_ids: list) -> list:
    games = []
    if game_ids:
        for gid in game_ids:
            path = os.path.join(data_dir, gid, "possessions.csv")
            if os.path.exists(path):
                games.append((gid, path))
            else:
                print(f"  [WARN] {gid}: possessions.csv not found, skipping")
    else:
        for entry in sorted(os.listdir(data_dir)):
            path = os.path.join(data_dir, entry, "possessions.csv")
            if os.path.exists(path):
                games.append((entry, path))
    return games


def _fps_est(rows: list) -> float:
    """Estimate frames-per-second from duration_frames / duration_sec pairs."""
    for r in rows:
        df = float(r.get("duration_frames") or 0)
        ds = float(r.get("duration_sec") or 0)
        if df > 0 and ds > 0:
            return df / ds
    return 30.0


def _clean(rows: list) -> tuple:
    """Return (merged_rows, stats_dict)."""
    fps = _fps_est(rows)

    # Step 1: filter sub-2s
    before_filter = len(rows)
    kept = [r for r in rows if float(r.get("duration_sec") or 0) >= MIN_DUR_SEC]
    n_filtered = before_filter - len(kept)

    # Step 2: merge same-team chains
    merged = []
    for row in kept:
        if (merged
                and row.get("team") == merged[-1].get("team")
                and int(row.get("start_frame") or 0) - int(merged[-1].get("end_frame") or 0) <= MERGE_GAP_FRAMES
                and not merged[-1].get("shot_attempted", "0") in ("1", "True", "true")):
            prev = merged[-1]
            prev["end_frame"]       = row["end_frame"]
            prev["duration_frames"] = str(int(prev["end_frame"]) - int(prev["start_frame"]))
            prev["duration_sec"]    = str(round(int(prev["duration_frames"]) / fps, 2))
            # Propagate shot info if the merged row had a shot
            if row.get("shot_attempted") in ("1", "True", "true"):
                prev["shot_attempted"] = row["shot_attempted"]
                prev["shot_frame"]     = row.get("shot_frame", "")
            # Sum event counts
            for col in ("pass_count", "screen_count", "drive_count", "cut_count", "drive_attempts"):
                try:
                    prev[col] = str(int(prev.get(col) or 0) + int(row.get(col) or 0))
                except (ValueError, TypeError):
                    pass
        else:
            merged.append(dict(row))

    n_merged = len(kept) - len(merged)

    # Re-number possession_id sequentially
    for i, row in enumerate(merged, start=1):
        row["possession_id"] = str(i)

    # Stats
    durs = [float(r["duration_sec"]) for r in merged if r.get("duration_sec")]
    stats = {
        "original":       before_filter,
        "after_filter":   len(kept),
        "after_merge":    len(merged),
        "n_filtered":     n_filtered,
        "n_merged":       n_merged,
        "median_dur_sec": round(statistics.median(durs), 2) if durs else 0.0,
        "mean_dur_sec":   round(statistics.mean(durs), 2) if durs else 0.0,
    }
    return merged, stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-ids", nargs="*", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    games = _load_games(DATA_DIR, args.game_ids)
    if not games:
        print("No possessions.csv files found.")
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

        merged, stats = _clean(rows)
        total_before += stats["original"]
        total_after  += stats["after_merge"]

        print(
            f"  {gid}: {stats['original']:>5} → {stats['after_merge']:>4} possessions  "
            f"(-{stats['n_filtered']} sub-2s -({stats['n_merged']} merged))  "
            f"median={stats['median_dur_sec']}s  mean={stats['mean_dur_sec']}s"
        )

        if args.dry_run:
            continue

        bak = path + ".bak"
        if not os.path.exists(bak):
            shutil.copy2(path, bak)

        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(merged)

    mode = "(DRY RUN)" if args.dry_run else "(WRITTEN)"
    print(f"\n{'='*60}")
    print(f"TOTAL {mode}: {total_before} → {total_after} possessions")


if __name__ == "__main__":
    main()
