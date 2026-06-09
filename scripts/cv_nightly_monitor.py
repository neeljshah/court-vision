#!/usr/bin/env python3
"""
cv_nightly_monitor.py - fast (<10s) CV-pipeline data-layer health check.
Prints a single formatted report to stdout.
Exit 0 if all clean, 1 if any P0 issue found.
"""
import os
import sys
import sqlite3
import json
import glob
from datetime import datetime

# Force UTF-8 output on Windows so Unicode box-drawing chars work
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------
_USE_COLOR = sys.stdout.isatty() or os.environ.get("FORCE_COLOR")


def green(s):
    return f"\033[32m{s}\033[0m" if _USE_COLOR else s


def red(s):
    return f"\033[31m{s}\033[0m" if _USE_COLOR else s


def yellow(s):
    return f"\033[33m{s}\033[0m" if _USE_COLOR else s


def bold(s):
    return f"\033[1m{s}\033[0m" if _USE_COLOR else s


def ok(msg):
    return green(f"OK  {msg}")


def warn(msg):
    return yellow(f"WRN {msg}")


def err(msg):
    return red(f"ERR {msg}")


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")

DB_CANDIDATES = [
    os.path.join(DATA, "local.db"),
    os.path.join(DATA, "nba.db"),
    os.path.join(DATA, "nba_ai.db"),
]

NBA_DIR = os.path.join(DATA, "nba")
INTEL_DIR = os.path.join(DATA, "intelligence")
PHASE_G_LOG = os.path.join(DATA, "phase_g_processed.txt")
TRACKER_LOG = os.path.join(BASE, "tracker.log")

STAR_PIDS = {
    201939: "Curry",
    203999: "Jokic",
    2544: "LeBron",
    201942: "DeRozan",
    1641705: "Wemby",
    1628369: "Tatum",
}

P0_ISSUES = []

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_db():
    for p in DB_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def has_table(conn, name):
    r = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return r[0] > 0


def season_from_game_id(gid):
    """002YYXXXX — positions 3-4 are the first year of the season."""
    try:
        yr = int(gid[3:5])
        return f"20{yr}-{(yr + 1):02d}"
    except Exception:
        return "unknown"


def build_player_name_map(sample_pids, limit=200):
    """Scan boxscore JSONs to build {pid: name} for the given pids."""
    name_map = {}
    if not os.path.isdir(NBA_DIR):
        return name_map
    pids_needed = set(sample_pids)
    files = sorted(glob.glob(os.path.join(NBA_DIR, "boxscore_*.json")))[:limit]
    for fpath in files:
        if not pids_needed:
            break
        try:
            with open(fpath, encoding="utf-8") as f:
                d = json.load(f)
            for p in d.get("players", []):
                pid = p.get("player_id")
                name = p.get("player_name")
                if pid and name and pid in pids_needed:
                    name_map[pid] = name
                    pids_needed.discard(pid)
        except Exception:
            continue
    return name_map


def print_section(title):
    print()
    print(bold(f"{'─'*60}"))
    print(bold(f"  {title}"))
    print(bold(f"{'─'*60}"))


# ---------------------------------------------------------------------------
# Main report
# ---------------------------------------------------------------------------

def run():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(bold(f"\n{'='*60}"))
    print(bold(f"  CV NIGHTLY MONITOR  —  {now}"))
    print(bold(f"{'='*60}"))

    db_path = find_db()
    if not db_path:
        print(err("No database found (local.db / nba.db / nba_ai.db)"))
        P0_ISSUES.append("no-db")
        return
    print(f"\n  DB: {db_path}")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

    # ------------------------------------------------------------------ #
    # 1. cv_features stats
    # ------------------------------------------------------------------ #
    print_section("1 · cv_features — database stats")

    if not has_table(conn, "cv_features"):
        print(warn("cv_features table missing"))
    else:
        total = conn.execute("SELECT COUNT(*) FROM cv_features").fetchone()[0]
        n_games = conn.execute("SELECT COUNT(DISTINCT game_id) FROM cv_features").fetchone()[0]
        n_players = conn.execute("SELECT COUNT(DISTINCT player_id) FROM cv_features").fetchone()[0]
        print(f"  rows={total:,}  games={n_games:,}  players={n_players:,}")

        # Per-season breakdown
        game_ids = [r[0] for r in conn.execute("SELECT DISTINCT game_id FROM cv_features").fetchall()]
        season_counts = {}
        for gid in game_ids:
            s = season_from_game_id(gid)
            season_counts[s] = season_counts.get(s, 0) + 1
        print("  Season game distribution:")
        for s, cnt in sorted(season_counts.items()):
            print(f"    {s}: {cnt} games")

        # Row counts per season (via game_id prefix)
        for s, _ in sorted(season_counts.items()):
            yr_pfx = s[2:4]  # "24" from "2024-25"
            row_cnt = conn.execute(
                "SELECT COUNT(*) FROM cv_features WHERE SUBSTR(game_id,4,2)=?", (yr_pfx,)
            ).fetchone()[0]
            print(f"    {s}: {row_cnt:,} rows")

    # ------------------------------------------------------------------ #
    # 2. Bug 33 — ghost rows
    # ------------------------------------------------------------------ #
    print_section("2 · Bug 33 — ghost rows (zero-heavy players)")

    if not has_table(conn, "cv_features"):
        print(warn("cv_features table missing — skip"))
    else:
        q_ghost = """
            SELECT player_id,
                   COUNT(DISTINCT game_id) AS n_games,
                   COUNT(*) AS total_rows,
                   SUM(CASE WHEN feature_value = 0.0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS zero_frac
            FROM cv_features
            GROUP BY player_id
            HAVING n_games >= ? AND zero_frac >= ?
        """
        strict = conn.execute(q_ghost, (3, 0.80)).fetchall()
        broader = conn.execute(q_ghost, (2, 0.75)).fetchall()

        n_strict = len(strict)
        n_broad = len(broader)

        label_strict = ok(f"strict: {n_strict}") if n_strict == 0 else err(f"strict: {n_strict}")
        label_broad = ok(f"broader: {n_broad}") if n_broad == 0 else warn(f"broader: {n_broad}")
        print(f"  Affected players  {label_strict}  |  {label_broad}")

        if n_strict > 0:
            P0_ISSUES.append(f"ghost-rows-strict:{n_strict}")

        # Top 5 worst offenders with names (n_games >= 2 to match broader threshold)
        top5_q = """
            SELECT player_id,
                   COUNT(DISTINCT game_id) AS n_games,
                   SUM(CASE WHEN feature_value = 0.0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS zero_frac
            FROM cv_features
            GROUP BY player_id
            HAVING n_games >= 2
            ORDER BY zero_frac DESC
            LIMIT 5
        """
        top5 = conn.execute(top5_q).fetchall()
        top5_pids = [r[0] for r in top5]
        name_map = build_player_name_map(top5_pids, limit=300)

        print("  Top 5 worst offenders:")
        for pid, ng, zf in top5:
            name = name_map.get(pid, f"pid={pid}")
            flag = red(f"zero={zf:.1%}") if zf >= 0.80 else yellow(f"zero={zf:.1%}")
            print(f"    {name:<30}  games={ng}  {flag}")

    # ------------------------------------------------------------------ #
    # 3. Bug 6 — roster collisions
    # ------------------------------------------------------------------ #
    print_section("3 · Bug 6 — roster collisions (out-of-roster pairs)")

    boxscore_files = glob.glob(os.path.join(NBA_DIR, "boxscore_*.json")) if os.path.isdir(NBA_DIR) else []
    if not boxscore_files:
        print(warn("No boxscore_*.json files found — skip Bug 6"))
    elif not has_table(conn, "cv_features"):
        print(warn("cv_features missing — skip Bug 6"))
    else:
        # Build valid (game_id, player_id) roster set from boxscores
        # Limit scan to a reasonable number of files to stay under 10s
        MAX_BS = 500
        roster_pairs = set()
        sampled = sorted(boxscore_files)[:MAX_BS]
        for fpath in sampled:
            try:
                with open(fpath, encoding="utf-8") as f:
                    d = json.load(f)
                gid = d.get("game_id", "")
                for p in d.get("players", []):
                    pid = p.get("player_id")
                    if gid and pid:
                        roster_pairs.add((str(gid), int(pid)))
            except Exception:
                continue

        # Pull all (game_id, player_id) from cv_features for those games
        sampled_gids = tuple({p[0] for p in roster_pairs})
        if sampled_gids:
            placeholders = ",".join("?" * len(sampled_gids))
            cv_pairs = conn.execute(
                f"SELECT DISTINCT game_id, player_id FROM cv_features WHERE game_id IN ({placeholders})",
                sampled_gids,
            ).fetchall()
            stale_pairs = [(g, p) for g, p in cv_pairs if (g, p) not in roster_pairs]
        else:
            stale_pairs = []

        n_stale = len(stale_pairs)
        if n_stale == 0:
            print(f"  {ok('Bug 6 clean')}  (checked {len(sampled)} boxscores)")
        else:
            print(err(f"  {n_stale} out-of-roster (game, player) pairs found"))
            P0_ISSUES.append(f"roster-collision:{n_stale}")
            # Count rows per stale pair
            row_counts = []
            for (gid, pid) in stale_pairs[:50]:  # cap work
                rc = conn.execute(
                    "SELECT COUNT(*) FROM cv_features WHERE game_id=? AND player_id=?", (gid, pid)
                ).fetchone()[0]
                row_counts.append((rc, gid, pid))
            row_counts.sort(reverse=True)
            name_map2 = build_player_name_map([p for _, _, p in row_counts[:5]])
            print("  Top 5 worst by row count:")
            for rc, gid, pid in row_counts[:5]:
                name = name_map2.get(pid, f"pid={pid}")
                print(f"    game={gid}  {name:<28}  rows={rc}")

    # ------------------------------------------------------------------ #
    # 4. Bug 18 — shot_clock NaN guard
    # ------------------------------------------------------------------ #
    print_section("4 · Bug 18 — shot_clock zero when shots tracked")

    if not has_table(conn, "cv_features"):
        print(warn("cv_features missing — skip"))
    else:
        # Pivot per-player/game: find rows where avg_shot_clock=0 AND n_shots_tracked>0
        # The data is long-format; pull both features per player/game and compare
        q_sc = """
            SELECT a.game_id, a.player_id,
                   a.feature_value AS avg_shot_clock,
                   b.feature_value AS n_shots
            FROM cv_features a
            JOIN cv_features b
              ON a.game_id = b.game_id AND a.player_id = b.player_id
             AND b.feature_name = 'n_shots_tracked'
            WHERE a.feature_name = 'avg_shot_clock_at_shot'
              AND a.feature_value = 0.0
              AND b.feature_value > 0
        """
        bad_sc = conn.execute(q_sc).fetchall()
        n_bad = len(bad_sc)
        if n_bad == 0:
            print(f"  {ok('shot_clock guard clean')}  (0 stale rows)")
        else:
            print(err(f"  {n_bad} rows: avg_shot_clock=0.0 but n_shots>0 (Bug 18 stale)"))
            P0_ISSUES.append(f"shot-clock-zero:{n_bad}")

    # ------------------------------------------------------------------ #
    # 5. Stars sanity check
    # ------------------------------------------------------------------ #
    print_section("5 · Stars sanity check — feature density")

    if not has_table(conn, "cv_features"):
        print(warn("cv_features missing — skip"))
    else:
        print(f"  {'Name':<12} {'pid':>8} {'n_games':>8} {'nonzero_total':>14} {'mean_nz/game':>14}")
        print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*14} {'-'*14}")
        for pid, name in sorted(STAR_PIDS.items(), key=lambda x: x[1]):
            ng = conn.execute(
                "SELECT COUNT(DISTINCT game_id) FROM cv_features WHERE player_id=?", (pid,)
            ).fetchone()[0]
            nz = conn.execute(
                "SELECT COUNT(*) FROM cv_features WHERE player_id=? AND feature_value != 0.0", (pid,)
            ).fetchone()[0]
            mean_nz = (nz / ng) if ng > 0 else 0.0
            flag = ok(f"{mean_nz:>6.1f}") if mean_nz >= 5 else warn(f"{mean_nz:>6.1f}")
            print(f"  {name:<12} {pid:>8} {ng:>8} {nz:>14} {flag}")

    # ------------------------------------------------------------------ #
    # 6. Intelligence atlases freshness
    # ------------------------------------------------------------------ #
    print_section("6 · Intelligence atlases freshness")

    if not os.path.isdir(INTEL_DIR):
        print(warn(f"intelligence dir missing: {INTEL_DIR}"))
    else:
        parquet_files = sorted(glob.glob(os.path.join(INTEL_DIR, "*.parquet")))
        if not parquet_files:
            print(warn("No .parquet files found in intelligence/"))
        else:
            # Try pyarrow then pandas for row counts
            def count_parquet(fpath):
                try:
                    import pyarrow.parquet as pq
                    return pq.read_metadata(fpath).num_rows
                except Exception:
                    pass
                try:
                    import pandas as pd
                    return len(pd.read_parquet(fpath, columns=[]))
                except Exception:
                    return -1

            print(f"  {'File':<45} {'mtime':<20} {'rows':>8}")
            print(f"  {'-'*45} {'-'*20} {'-'*8}")
            now_ts = datetime.now().timestamp()
            for fpath in parquet_files:
                fname = os.path.basename(fpath)
                mtime_ts = os.path.getmtime(fpath)
                mtime_str = datetime.fromtimestamp(mtime_ts).strftime("%Y-%m-%d %H:%M")
                age_h = (now_ts - mtime_ts) / 3600
                rows = count_parquet(fpath)
                row_str = str(rows) if rows >= 0 else "n/a"
                age_flag = warn(f">{age_h:.0f}h ago") if age_h > 48 else ok(f"{age_h:.1f}h ago")
                print(f"  {fname:<45} {mtime_str}  {row_str:>8}  {age_flag}")

    # ------------------------------------------------------------------ #
    # 7. Processing log + tracker log
    # ------------------------------------------------------------------ #
    print_section("7 · Processing logs")

    if os.path.exists(PHASE_G_LOG):
        with open(PHASE_G_LOG, encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        mtime = datetime.fromtimestamp(os.path.getmtime(PHASE_G_LOG)).strftime("%Y-%m-%d %H:%M")
        print(ok(f"phase_g_processed.txt: {len(lines)} entries  (last modified {mtime})"))
    else:
        print(warn("phase_g_processed.txt not found"))

    if os.path.exists(TRACKER_LOG):
        with open(TRACKER_LOG, encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        tail = all_lines[-5:] if len(all_lines) >= 5 else all_lines
        mtime = datetime.fromtimestamp(os.path.getmtime(TRACKER_LOG)).strftime("%Y-%m-%d %H:%M")
        print(f"  tracker.log  (last modified {mtime})  last 5 lines:")
        for ln in tail:
            print(f"    {ln.rstrip()}")
    else:
        print(warn("tracker.log not found (expected on RunPod only)"))

    conn.close()

    # ------------------------------------------------------------------ #
    # Summary
    # ------------------------------------------------------------------ #
    print()
    print(bold(f"{'='*60}"))
    if P0_ISSUES:
        print(red(f"  P0 ISSUES ({len(P0_ISSUES)}): {', '.join(P0_ISSUES)}"))
    else:
        print(green("  ALL CHECKS CLEAN — no P0 issues"))
    print(bold(f"{'='*60}\n"))

    return 1 if P0_ISSUES else 0


if __name__ == "__main__":
    sys.exit(run())
