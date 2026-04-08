"""
validate_games.py -- Audit and clean tracking data dirs + nightly CV/API diff.

Modes:
  (default)       dry-run audit report
  --fix           delete bad tracking dirs and fix metrics
  --nightly       compare CV tracking vs NBA API box score, write
                  data/fusion/game_quality_scores.csv

Usage:
    python scripts/validate_games.py              # dry-run
    python scripts/validate_games.py --fix        # clean up
    python scripts/validate_games.py --nightly    # CV vs API diff
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
TRACKING_DIR = DATA_DIR / "tracking"
METRICS_LOG = DATA_DIR / "phase_g_metrics.csv"
DONE_LOG = DATA_DIR / "phase_g_processed.txt"

MIN_POSSESSIONS = 3
MIN_TRACKING_ROWS = 500


def count_csv_rows(path: Path) -> int:
    if not path.exists() or path.stat().st_size == 0:
        return 0
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return max(0, sum(1 for _ in f) - 1)
    except Exception:
        return 0


def compute_ball_valid_pct(ball_csv: Path) -> float:
    if not ball_csv.exists():
        return 0.0
    try:
        detected = total = live_total = 0
        has_live = False
        with open(ball_csv, encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                total += 1
                if str(row.get("detected", "0")) == "1":
                    detected += 1
                if "live" in row:
                    has_live = True
                    if str(row["live"]) == "1":
                        live_total += 1
        denom = live_total if (has_live and live_total > 0) else total
        return round(detected / denom * 100, 1) if denom > 0 else 0.0
    except Exception:
        return 0.0


def quality_label(pct: float) -> str:
    if pct >= 80.0:
        return "high"
    if pct >= 65.0:
        return "medium"
    return "low"


def audit_tracking_dirs():
    good, bad = [], []
    for d in sorted(TRACKING_DIR.iterdir()):
        if not d.is_dir():
            continue
        gid = d.name
        bt = count_csv_rows(d / "ball_tracking.csv")
        td = count_csv_rows(d / "tracking_data.csv")
        po = count_csv_rows(d / "possessions.csv")
        ball_pct = compute_ball_valid_pct(d / "ball_tracking.csv")
        stats = {"ball_rows": bt, "track_rows": td, "poss_rows": po,
                 "ball_valid_pct": ball_pct, "dir": d}
        if po < MIN_POSSESSIONS or td < MIN_TRACKING_ROWS:
            bad.append((gid, stats))
        else:
            good.append((gid, stats))
    return good, bad


def rebuild_metrics(good_games):
    existing = {}
    if METRICS_LOG.exists():
        with open(METRICS_LOG, newline="") as f:
            for row in csv.DictReader(f):
                key = row.get("game_key", "")
                existing[key] = row

    fieldnames = ["timestamp", "game_key", "game_id", "frames", "stability",
                  "id_switches", "ball_valid_pct", "quality", "duration_s"]
    rows = []
    for gid, stats in good_games:
        prev = existing.get(gid, {})
        ball_pct = stats["ball_valid_pct"]
        rows.append({
            "timestamp": prev.get("timestamp", datetime.now().isoformat(timespec="seconds")),
            "game_key": gid,
            "game_id": prev.get("game_id", gid if gid.startswith("002") else ""),
            "frames": stats["ball_rows"],
            "stability": prev.get("stability", "1.0"),
            "id_switches": prev.get("id_switches", "0"),
            "ball_valid_pct": ball_pct,
            "quality": quality_label(ball_pct),
            "duration_s": prev.get("duration_s", "0"),
        })

    with open(METRICS_LOG, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def dedup_processed_log(good_ids: set):
    clean = sorted(good_ids)
    DONE_LOG.write_text("\n".join(clean) + "\n", encoding="utf-8")
    return len(clean)


QUALITY_SCORES_CSV = DATA_DIR / "fusion" / "game_quality_scores.csv"
_QUALITY_HEADER = [
    "game_id", "cv_grade", "ball_valid_pct", "tracking_rows",
    "api_pts_home", "api_pts_away", "cv_shots_detected",
    "cv_possessions", "pts_delta_home", "pts_delta_away",
    "overall_score", "run_ts",
]


def _load_cv_shots(game_dir: Path) -> int:
    """Count detected shots in CV shot_log.csv."""
    shot_log = game_dir / "shot_log.csv"
    if not shot_log.exists():
        return 0
    return count_csv_rows(shot_log)


def _fetch_api_pts(game_id: str) -> dict:
    """Fetch final score from NBA API for one game. Returns {} on failure."""
    try:
        from nba_api.stats.endpoints import BoxScoreTraditionalV2  # type: ignore
        import time as _time
        resp = BoxScoreTraditionalV2(game_id=game_id)
        d    = resp.get_dict()
        for rs in d.get("resultSets", []):
            if rs["name"] == "TeamStats":
                hdrs = rs["headers"]
                idx  = {h: i for i, h in enumerate(hdrs)}
                rows = rs["rowSet"]
                if len(rows) >= 2:
                    return {
                        "away_pts": float(rows[0][idx["PTS"]] or 0),
                        "home_pts": float(rows[1][idx["PTS"]] or 0),
                    }
    except Exception as exc:
        print(f"  [nightly] API fetch failed for {game_id}: {exc}")
    return {}


def _grade_from_pct(ball_valid_pct: float) -> str:
    if ball_valid_pct >= 80:
        return "A"
    if ball_valid_pct >= 65:
        return "B"
    if ball_valid_pct >= 50:
        return "C"
    return "F"


def _overall_score(ball_pct: float, track_rows: int, poss_rows: int) -> float:
    """0-100 overall data quality score for a game."""
    bq = min(ball_pct, 100) / 100 * 50      # 50 pts max for ball detection
    tq = min(track_rows / 10000, 1.0) * 30  # 30 pts max for tracking density
    pq = min(poss_rows / 80, 1.0) * 20      # 20 pts max for possession count
    return round(bq + tq + pq, 1)


def nightly_diff(good_games: list, sleep_s: float = 0.6):
    """
    Compare CV tracking vs NBA API box scores for each good game.
    Writes data/fusion/game_quality_scores.csv.
    """
    import time as _time

    QUALITY_SCORES_CSV.parent.mkdir(parents=True, exist_ok=True)

    # Load existing scores to skip already-processed games
    processed_ids: set = set()
    existing_rows: list = []
    if QUALITY_SCORES_CSV.exists():
        with open(QUALITY_SCORES_CSV, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                processed_ids.add(r["game_id"])
                existing_rows.append(r)

    new_rows = []
    for game_dir_name, stats in good_games:
        # Extract NBA game_id from the dir stats (may be empty string for anonymous dirs)
        d: Path = stats["dir"]

        # Try to find a 10-digit game ID in the dir name
        import re as _re
        m = _re.search(r"(002\d{7}|001\d{7})", game_dir_name)
        game_id = m.group(1) if m else ""
        if not game_id or game_id in processed_ids:
            continue

        cv_shots = _load_cv_shots(d)
        ball_pct = stats["ball_valid_pct"]
        track_rows = stats["track_rows"]
        poss_rows  = stats["poss_rows"]
        grade      = _grade_from_pct(ball_pct)
        score      = _overall_score(ball_pct, track_rows, poss_rows)

        api_data = _fetch_api_pts(game_id)
        _time.sleep(sleep_s)

        new_rows.append({
            "game_id":         game_id,
            "cv_grade":        grade,
            "ball_valid_pct":  ball_pct,
            "tracking_rows":   track_rows,
            "api_pts_home":    api_data.get("home_pts", ""),
            "api_pts_away":    api_data.get("away_pts", ""),
            "cv_shots_detected": cv_shots,
            "cv_possessions":  poss_rows,
            "pts_delta_home":  "",   # future: compare with CV score tracking
            "pts_delta_away":  "",
            "overall_score":   score,
            "run_ts":          datetime.now().isoformat(timespec="seconds"),
        })
        print(f"  [nightly] {game_id}  grade={grade}  score={score}  "
              f"ball_pct={ball_pct:.1f}%  api={api_data}")

    all_rows = existing_rows + new_rows
    with open(QUALITY_SCORES_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_QUALITY_HEADER, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_rows)

    print(f"  [nightly] Wrote {len(all_rows)} rows to {QUALITY_SCORES_CSV}")
    return len(new_rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix",     action="store_true", help="Delete bad data and fix metrics")
    ap.add_argument("--nightly", action="store_true", help="CV vs API diff, write quality scores")
    args = ap.parse_args()

    good, bad = audit_tracking_dirs()

    print(f"\n=== TRACKING DATA AUDIT ===")
    print(f"Good games: {len(good)}")
    print(f"Bad/empty:  {len(bad)}")

    if bad:
        print(f"\n--- BAD (will {'DELETE' if args.fix else 'be deleted with --fix'}) ---")
        for gid, s in bad:
            print(f"  {gid:55s} ball={s['ball_rows']:>6}  track={s['track_rows']:>6}  poss={s['poss_rows']:>3}")

    if good:
        print(f"\n--- GOOD ---")
        for gid, s in good:
            print(f"  {gid:55s} ball={s['ball_rows']:>6}  track={s['track_rows']:>6}  "
                  f"poss={s['poss_rows']:>3}  ball_valid={s['ball_valid_pct']:.1f}%")

    if args.fix:
        print(f"\n=== FIXING ===")
        for gid, s in bad:
            print(f"  Deleting {s['dir']}")
            shutil.rmtree(s["dir"])
        print(f"  Deleted {len(bad)} bad tracking dir(s)")

        n = rebuild_metrics(good)
        print(f"  Rebuilt {METRICS_LOG.name} with {n} entries")

        good_ids = {gid for gid, _ in good}
        n2 = dedup_processed_log(good_ids)
        print(f"  Cleaned {DONE_LOG.name}: {n2} unique entries")

        print(f"\nDone. {len(good)} clean games retained.")
    else:
        print(f"\nDry run. Use --fix to clean up.")

    if args.nightly:
        print(f"\n=== NIGHTLY CV vs NBA API DIFF ===")
        n = nightly_diff(good)
        print(f"  Processed {n} new games.")


if __name__ == "__main__":
    main()
