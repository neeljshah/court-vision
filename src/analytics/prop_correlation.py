"""
prop_correlation.py — Historical correlations between player prop stats.

Reads all gamelog_full_{player_id}_{season}.json files to compute:
  - Per-player stat correlations (pts-reb, pts-ast, reb-ast)
  - Same-team player pair correlations (lineup correlation)

Outputs:
  data/nba/prop_correlations.json    — {player_id: {pts_reb_r, pts_ast_r, reb_ast_r, n_games}}
  data/nba/lineup_correlations.json  — {team: {pid1_pid2: pts_r}}

CLI: python src/analytics/prop_correlation.py --build
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)
_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")


def _pearsonr(x: list, y: list) -> float:
    """Pearson r, returns 0.0 on insufficient data or error."""
    if len(x) < 10:
        return 0.0
    xa = np.array(x, dtype=float)
    ya = np.array(y, dtype=float)
    try:
        from scipy.stats import pearsonr
        r, _ = pearsonr(xa, ya)
        return round(float(r), 4) if not np.isnan(r) else 0.0
    except Exception:
        # Fallback: manual pearson
        try:
            xm, ym = xa - xa.mean(), ya - ya.mean()
            denom = np.sqrt((xm ** 2).sum() * (ym ** 2).sum())
            if denom == 0:
                return 0.0
            return round(float((xm * ym).sum() / denom), 4)
        except Exception:
            return 0.0


def _load_player_data() -> dict:
    """
    Load all per-player game stats from gamelog_full files.

    Returns {player_id_str: {team, dates: [], pts: [], reb: [], ast: []}}
    File naming: gamelog_full_{player_id}_{season}.json
    """
    pattern = re.compile(r"gamelog_full_(\d+)_([\d-]+)\.json$")
    files = glob.glob(os.path.join(_NBA_CACHE, "gamelog_full_*.json"))
    print(f"[corr] {len(files)} gamelog files")

    # Accumulate across all seasons per player
    player_data: dict = defaultdict(lambda: {
        "team": "", "dates": [], "pts": [], "reb": [], "ast": []
    })

    for fpath in files:
        fname = os.path.basename(fpath)
        m = pattern.match(fname)
        if not m:
            continue
        pid = m.group(1)

        try:
            data = json.load(open(fpath, encoding="utf-8"))
            rows = data if isinstance(data, list) else list(data.values())
        except Exception:
            continue

        for row in rows:
            if not isinstance(row, dict):
                continue

            # Lowercase keys in gamelog_full files
            min_val = str(row.get("min", row.get("MIN", "1"))).strip()
            if min_val in ("0", "0:00", "", "None", "null"):
                continue  # skip DNP rows

            def _get(*keys, default=0.0):
                for k in keys:
                    v = row.get(k)
                    if v is not None:
                        try:
                            return float(v)
                        except (ValueError, TypeError):
                            pass
                return default

            pts = _get("pts", "PTS")
            reb = _get("reb", "REB")
            ast = _get("ast", "AST")
            date = str(row.get("game_date", row.get("GAME_DATE", "")))

            # Infer team from matchup (e.g. "SAS vs. TOR" or "SAS @ TOR")
            matchup = str(row.get("matchup", row.get("MATCHUP", "")))
            if matchup and not player_data[pid]["team"]:
                team = matchup.split()[0]  # first word is always player's team
                player_data[pid]["team"] = team

            if date:
                player_data[pid]["dates"].append(date)
                player_data[pid]["pts"].append(pts)
                player_data[pid]["reb"].append(reb)
                player_data[pid]["ast"].append(ast)

    return dict(player_data)


def build() -> None:
    """Build and save prop correlation caches."""
    player_data = _load_player_data()

    # Per-player correlations
    prop_corrs: dict = {}
    for pid, d in player_data.items():
        if len(d["pts"]) < 10:
            continue
        prop_corrs[pid] = {
            "pts_reb_r": _pearsonr(d["pts"], d["reb"]),
            "pts_ast_r": _pearsonr(d["pts"], d["ast"]),
            "reb_ast_r": _pearsonr(d["reb"], d["ast"]),
            "n_games":   len(d["pts"]),
        }

    out1 = os.path.join(_NBA_CACHE, "prop_correlations.json")
    json.dump(prop_corrs, open(out1, "w"), indent=2)
    print(f"[corr] {len(prop_corrs)} player correlations -> {out1}")

    # Lineup correlations: same-team player pairs by date alignment
    team_players: dict = defaultdict(set)
    for pid, d in player_data.items():
        if d["team"]:
            team_players[d["team"]].add(pid)

    lineup_corrs: dict = {}
    total_pairs = 0
    for team, pids in team_players.items():
        pids = list(pids)
        lineup_corrs[team] = {}
        # Build date-indexed lookup for fast access
        dates_by_pid: dict = {}
        for pid in pids:
            d = player_data[pid]
            dates_by_pid[pid] = {
                date: (pts, reb, ast)
                for date, pts, reb, ast in zip(
                    d["dates"], d["pts"], d["reb"], d["ast"]
                )
            }

        for i in range(len(pids)):
            for j in range(i + 1, len(pids)):
                p1, p2 = pids[i], pids[j]
                common = sorted(set(dates_by_pid[p1]) & set(dates_by_pid[p2]))
                if len(common) < 10:
                    continue
                v1 = [dates_by_pid[p1][d][0] for d in common]  # pts
                v2 = [dates_by_pid[p2][d][0] for d in common]
                r = _pearsonr(v1, v2)
                key = f"{p1}_{p2}"
                lineup_corrs[team][key] = r
                total_pairs += 1

    out2 = os.path.join(_NBA_CACHE, "lineup_correlations.json")
    json.dump(lineup_corrs, open(out2, "w"), indent=2)
    print(f"[corr] {total_pairs} lineup pairs -> {out2}")


def get_correlation_penalty(player1_id: int | str, player2_id: int | str) -> float:
    """
    Return Pearson r of pts correlation for same-team players.

    Args:
        player1_id: NBA player ID (int or str).
        player2_id: NBA player ID (int or str).

    Returns:
        Pearson r in [-1, 1]. 0.0 if not found or cache missing.
    """
    path = os.path.join(_NBA_CACHE, "lineup_correlations.json")
    try:
        d = json.load(open(path))
        p1, p2 = str(player1_id), str(player2_id)
        for team_data in d.values():
            for key, r in team_data.items():
                ids = key.split("_")
                if p1 in ids and p2 in ids:
                    return float(r)
        return 0.0
    except Exception:
        return 0.0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build prop correlation matrices")
    parser.add_argument("--build", action="store_true", help="Build correlation caches")
    args = parser.parse_args()
    build()
