"""
run_season_queue.py — Sequential pipeline runner for 2025-26 season games.

Processes each unprocessed game one at a time:
  1. run_phase_g.py --frames 18000 (10 min of gameplay, ~3-10 min processing)
  2. Post-fix: team_abbrev from NBA API + nearest_opponent in feet
  3. Quality audit logged per game
  4. Resume-safe: skips games with >10K rows in tracking_data.csv

Usage:
    conda activate basketball_ai
    python scripts/run_season_queue.py
    python scripts/run_season_queue.py --limit 5        # process at most 5
    python scripts/run_season_queue.py --frames 9000    # 5 min per game
    python scripts/run_season_queue.py --dry-run        # show plan only
"""
from __future__ import annotations

import argparse
import csv
import gc
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from collections import defaultdict

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR    = PROJECT_DIR / "data"
GAMES_DIR   = DATA_DIR / "games"
TRACKING_DIR = DATA_DIR / "tracking"
VIDEOS_DIR  = DATA_DIR / "videos" / "full_games"
LOG_PATH    = DATA_DIR / "season_queue_log.csv"
PYTHON      = sys.executable

sys.path.insert(0, str(PROJECT_DIR))

# Games ordered by video size (largest first = best quality)
SEASON_GAMES = [
    "0022501090", "0022501087", "0022501094", "0022501083",
    "0022501086", "0022501095", "0022501082", "0022501079",
    "0022501080", "0022501088", "0022501076", "0022501097",
    "0022501077", "0022501084", "0022501085", "0022501089",
    "0022501078", "0022501096",
]


def _is_done(game_id: str) -> Optional[int]:
    """Return row count if already processed with >10K rows."""
    for parent in (TRACKING_DIR, GAMES_DIR):
        td = parent / game_id / "tracking_data.csv"
        if td.exists():
            try:
                with open(td, encoding="utf-8", errors="replace") as f:
                    rows = sum(1 for _ in f)
                if rows > 10_000:
                    return rows
            except Exception:
                pass
    return None


def _get_game_dir(game_id: str) -> Optional[Path]:
    for d in (TRACKING_DIR, GAMES_DIR):
        p = d / game_id
        if (p / "tracking_data.csv").exists():
            return p
    return None


def _resolve_team_abbrev(game_id: str, game_dir: Path) -> dict:
    """Resolve team abbreviations from cache or NBA API."""
    cache_path = DATA_DIR / "nba" / f"team_map_{game_id}.json"
    if cache_path.exists():
        cached = json.loads(cache_path.read_text())
        if all(not v.startswith("team_") and v not in ("UNK", "") for v in cached.values()):
            return cached

    try:
        time.sleep(0.6)
        from nba_api.stats.static import teams as _teams_static
        id_to_abbr = {t["id"]: t["abbreviation"] for t in _teams_static.get_teams()}
        try:
            from nba_api.stats.endpoints import boxscoresummaryv3 as bssv3
            bs = bssv3.BoxScoreSummaryV3(game_id=game_id)
            df = bs.get_data_frames()[0]
            home = id_to_abbr.get(int(df["homeTeamId"].iloc[0]), "UNK")
            away = id_to_abbr.get(int(df["awayTeamId"].iloc[0]), "UNK")
        except Exception:
            from nba_api.stats.endpoints import boxscoresummaryv2 as bssv2
            bs = bssv2.BoxScoreSummaryV2(game_id=game_id)
            df2 = bs.get_data_frames()[0]
            home = id_to_abbr.get(int(df2["HOME_TEAM_ID"].iloc[0]), "UNK")
            away = id_to_abbr.get(int(df2["VISITOR_TEAM_ID"].iloc[0]), "UNK")

        sample = pd.read_csv(game_dir / "tracking_data.csv", nrows=2000, low_memory=False)
        labels = sorted(l for l in sample["team"].dropna().unique()
                       if l not in ("", "nan", "referee"))
        color_map = {}
        if len(labels) == 2:
            color_map = {labels[0]: home, labels[1]: away}
        elif len(labels) == 1:
            color_map = {labels[0]: home}

        if color_map:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(color_map, indent=2))
        return color_map
    except Exception as e:
        print(f"    [team_api] failed: {e}")
        return {}


def _apply_team_abbrev(game_dir: Path, color_map: dict) -> None:
    """Apply team abbreviations to all CSVs."""
    (game_dir / "team_colors.json").write_text(json.dumps(color_map, indent=2))
    for csv_path in sorted(game_dir.glob("*.csv")):
        try:
            df = pd.read_csv(csv_path, low_memory=False)
            if "team" not in df.columns:
                continue
            if "team_abbrev" not in df.columns:
                df["team_abbrev"] = df["team"].map(color_map).fillna("UNK")
            else:
                df["team_abbrev"] = df["team_abbrev"].astype(str)
                for color, abbr in color_map.items():
                    mask = (df["team"] == color) & df["team_abbrev"].isin(
                        ["team_a", "team_b", "UNK", "", "nan"])
                    if mask.any():
                        df.loc[mask, "team_abbrev"] = abbr
            df.to_csv(csv_path, index=False, encoding="utf-8")
        except Exception:
            pass


def _recompute_spatial_ft(game_dir: Path) -> None:
    """Recompute nearest_opponent and handler_isolation from ft_x/ft_y."""
    for fname in ("tracking_data.csv", "features.csv"):
        path = game_dir / fname
        if not path.exists():
            continue
        df = pd.read_csv(path, low_memory=False)
        if "ft_x" not in df.columns or "ft_y" not in df.columns:
            continue
        # Skip if already in feet
        if "nearest_opponent" in df.columns:
            cur = pd.to_numeric(df["nearest_opponent"], errors="coerce")
            valid = cur[cur.notna() & (cur > 0)]
            if len(valid) > 100 and valid.max() < 100:
                continue

        ft_x = pd.to_numeric(df["ft_x"], errors="coerce").values
        ft_y = pd.to_numeric(df["ft_y"], errors="coerce").values
        teams = df["team"].astype(str).values if "team" in df.columns else np.full(len(df), "")
        frames = df["frame"].values
        n = len(df)

        frame_idx = defaultdict(list)
        for i, fr in enumerate(frames):
            if not (np.isnan(ft_x[i]) or np.isnan(ft_y[i])):
                frame_idx[fr].append((ft_x[i], ft_y[i], teams[i], i))

        new_opp = np.full(n, np.nan)
        for i, fr in enumerate(frames):
            if np.isnan(ft_x[i]) or np.isnan(ft_y[i]):
                continue
            ti = teams[i]
            dists = [float(np.hypot(ft_x[i] - ox, ft_y[i] - oy))
                     for ox, oy, ot, _ in frame_idx[fr]
                     if ot != ti and ot not in ("referee", "nan", "")]
            if dists:
                new_opp[i] = round(min(dists), 2)
        df["nearest_opponent"] = new_opp

        poss_col = next((c for c in ("ball_possession", "has_ball") if c in df.columns), None)
        if poss_col:
            poss_vals = pd.to_numeric(df[poss_col], errors="coerce").fillna(0).values
            new_iso = np.full(n, np.nan)
            for fr, entries in frame_idx.items():
                handlers = [(x, y, t, idx) for x, y, t, idx in entries if poss_vals[idx] == 1]
                if not handlers:
                    continue
                hx, hy, ht, _ = handlers[0]
                opps = [(x, y) for x, y, t, _ in entries if t != ht and t not in ("referee", "nan", "")]
                if len(opps) < 2:
                    continue
                dists_sorted = sorted(float(np.hypot(hx - ox, hy - oy)) for ox, oy in opps)
                iso_val = round(dists_sorted[1] if len(dists_sorted) >= 2 else dists_sorted[0], 2)
                for _, _, _, idx in entries:
                    new_iso[idx] = iso_val
            df["handler_isolation"] = new_iso

        df.to_csv(path, index=False, encoding="utf-8")


def _quality_audit(game_id: str, game_dir: Path) -> dict:
    """Run quality audit and return metrics."""
    metrics = {"game_id": game_id, "rows": 0, "nearest_opponent_pct": 0,
               "handler_isolation_pct": 0, "team_abbrev_pct": 0, "player_name_pct": 0,
               "homography_pct": 0, "ball_detection_pct": 0, "two_team_pct": 0,
               "shots": 0, "possessions": 0}

    td = game_dir / "tracking_data.csv"
    if not td.exists():
        return metrics

    df = pd.read_csv(td, low_memory=False)
    n = len(df)
    metrics["rows"] = n

    def fill_pct(col, max_val=199):
        if col not in df.columns:
            return 0.0
        return (df[col].notna() & (pd.to_numeric(df[col], errors="coerce") < max_val)).mean() * 100

    metrics["nearest_opponent_pct"] = round(fill_pct("nearest_opponent"), 1)
    metrics["handler_isolation_pct"] = round(fill_pct("handler_isolation"), 1)

    if "team_abbrev" in df.columns:
        n_bad = (df["team_abbrev"].isin(["UNK", "", "nan", "team_a", "team_b"]) | df["team_abbrev"].isna()).sum()
        metrics["team_abbrev_pct"] = round((1 - n_bad / n) * 100, 1)

    if "player_name" in df.columns:
        metrics["player_name_pct"] = round(df["player_name"].notna().mean() * 100, 1)

    if "homography_valid" in df.columns:
        metrics["homography_pct"] = round(pd.to_numeric(df["homography_valid"], errors="coerce").mean() * 100, 1)

    bt = game_dir / "ball_tracking.csv"
    if bt.exists():
        bdf = pd.read_csv(bt)
        if "detected" in bdf.columns:
            metrics["ball_detection_pct"] = round((bdf["detected"] == 1).mean() * 100, 1)

    if "team" in df.columns and "frame" in df.columns:
        div = df.groupby("frame")["team"].nunique()
        metrics["two_team_pct"] = round((div >= 2).mean() * 100, 1)

    sl = game_dir / "shot_log.csv"
    if sl.exists():
        metrics["shots"] = max(0, len(open(sl).readlines()) - 1)

    pv = game_dir / "possessions.csv"
    if pv.exists():
        metrics["possessions"] = max(0, len(open(pv).readlines()) - 1)

    return metrics


def _append_log(row: dict) -> None:
    fields = ["timestamp", "game_id", "status", "rows", "shots", "possessions",
              "nearest_opponent_pct", "handler_isolation_pct", "team_abbrev_pct",
              "player_name_pct", "homography_pct", "ball_detection_pct",
              "two_team_pct", "processing_time_s", "error"]
    write_header = not LOG_PATH.exists()
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if write_header:
            w.writeheader()
        w.writerow(row)


def main():
    parser = argparse.ArgumentParser(description="Season queue runner")
    parser.add_argument("--frames", type=int, default=18000, help="Frames per game (default 18000)")
    parser.add_argument("--limit", type=int, default=None, help="Max games to process")
    parser.add_argument("--dry-run", action="store_true", help="Show plan only")
    args = parser.parse_args()

    print(f"=== Season Queue Runner — {len(SEASON_GAMES)} games, {args.frames} frames each ===\n")

    processed = 0
    for i, game_id in enumerate(SEASON_GAMES, 1):
        if args.limit and processed >= args.limit:
            print(f"\nLimit reached ({args.limit}). Stopping.")
            break

        video = VIDEOS_DIR / f"{game_id}.mp4"
        print(f"[{i}/{len(SEASON_GAMES)}] {game_id}", end="")

        existing = _is_done(game_id)
        if existing:
            print(f"  SKIP ({existing:,} rows)")
            continue

        if not video.exists():
            print(f"  NO VIDEO")
            continue

        size_mb = video.stat().st_size // (1024 * 1024)
        print(f"  ({size_mb}MB)")

        if args.dry_run:
            continue

        # ── Run pipeline ──────────────────────────────────────────────────
        t0 = time.time()
        log_row = {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   "game_id": game_id, "status": "started", "error": ""}

        cmd = [PYTHON, str(PROJECT_DIR / "scripts" / "run_phase_g.py"),
               "--game-ids", game_id, "--frames", str(args.frames)]
        print(f"  Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(cmd, timeout=3600, cwd=str(PROJECT_DIR),
                                   capture_output=True, text=True, encoding="utf-8",
                                   errors="replace")
            elapsed = time.time() - t0
            log_row["processing_time_s"] = round(elapsed, 1)

            if result.returncode != 0:
                # Print stderr tail for diagnosis
                stderr_tail = (result.stderr or "")[-500:]
                print(f"  PIPELINE FAILED (exit {result.returncode})")
                if stderr_tail:
                    print(f"  {stderr_tail[:200]}")
                log_row["status"] = "pipeline_failed"
                log_row["error"] = f"exit {result.returncode}"
                _append_log(log_row)
                continue

            print(f"  Pipeline OK ({elapsed:.0f}s)")
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT (1hr)")
            log_row["status"] = "timeout"
            _append_log(log_row)
            continue

        # ── Post-processing fixes ─────────────────────────────────────────
        game_dir = _get_game_dir(game_id)
        if not game_dir:
            log_row["status"] = "no_output"
            _append_log(log_row)
            continue

        print(f"  Post-fix: team_abbrev...", end="")
        color_map = _resolve_team_abbrev(game_id, game_dir)
        if color_map:
            _apply_team_abbrev(game_dir, color_map)
            print(f" {color_map}")
        else:
            print(" (no map)")

        print(f"  Post-fix: spatial ft...", end="")
        _recompute_spatial_ft(game_dir)
        print(" done")

        # ── Quality audit ─────────────────────────────────────────────────
        audit = _quality_audit(game_id, game_dir)
        log_row.update(audit)
        log_row["status"] = "success"
        _append_log(log_row)

        print(f"  AUDIT: {audit['rows']:,} rows | "
              f"nearest_opp={audit['nearest_opponent_pct']:.0f}% | "
              f"team_abbrev={audit['team_abbrev_pct']:.0f}% | "
              f"player_name={audit['player_name_pct']:.0f}% | "
              f"homography={audit['homography_pct']:.0f}% | "
              f"ball={audit['ball_detection_pct']:.0f}% | "
              f"2team={audit['two_team_pct']:.0f}% | "
              f"shots={audit['shots']} poss={audit['possessions']}")
        processed += 1

        # ── Force garbage collection between games ────────────────────────
        gc.collect()

    print(f"\n=== Done. Processed {processed} games. Log: {LOG_PATH} ===")


if __name__ == "__main__":
    main()
