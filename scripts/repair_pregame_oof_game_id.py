"""repair_pregame_oof_game_id.py - Backfill the missing game_id column in
data/cache/pregame_oof.parquet.

Root cause: scripts/cache_pergame_oof.py reads gamelog_<pid>_<season>.json
files which do NOT carry a Game_ID field; the producer therefore wrote
empty strings into the parquet's game_id column. The probe
probe_R9_C3_synthetic_closing_line.py joins on (game_id, player_id, stat)
so Tier 3 silently degrades to Tier 4 for every bet.

Recovery strategy
-----------------
Build (player_id, game_date_iso) -> game_id from four on-disk sources,
unioned in order of authority:

  1. data/player_adv_stats.parquet  - 77,728 (pid, gid, date) triples
     covering 2022-10-18 .. 2025-04-13 (regular boxscore -> adv stats).

  2. data/nba/boxscore_adv_<gid>.json - 4,273 advanced boxscores; each
     player entry has 'personid' + 'gameid'. We cross-reference 'gameid'
     against season_games_*.json for the game_date.

  3. data/nba/boxscore_<gid>.json - 1,197 standard boxscores with
     'player_id' + 'game_id'; cross-reference season_games for date.

  4. data/nba/season_games_<season>.json - schedule (gid -> date).

Then left-join (player_id, game_date) onto pregame_oof.parquet and
overwrite the file.

Coverage target: >= 80% non-empty game_id; rows that miss remain ''
and fall through to Tier 4 as they would have anyway.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from typing import Dict, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import pandas as pd

NBA_DIR  = os.path.join(PROJECT_DIR, "data", "nba")
OOF_PATH = os.path.join(PROJECT_DIR, "data", "cache", "pregame_oof.parquet")
ADV_PARQUET = os.path.join(PROJECT_DIR, "data", "player_adv_stats.parquet")


def build_gameid_date_map() -> Dict[str, str]:
    """game_id (str) -> ISO game_date (YYYY-MM-DD)."""
    out: Dict[str, str] = {}
    for path in sorted(glob.glob(os.path.join(NBA_DIR, "season_games_*.json"))):
        try:
            blob = json.load(open(path, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows = blob.get("rows") if isinstance(blob, dict) else blob
        if not isinstance(rows, list):
            continue
        for r in rows:
            gid = str(r.get("game_id", "") or "").strip()
            gd  = str(r.get("game_date", "") or "").strip()[:10]
            if gid and gd:
                out[gid] = gd
    return out


def add_from_adv_parquet(out: Dict[Tuple[int, str], str]) -> int:
    """Add pairs from data/player_adv_stats.parquet. Returns n_added."""
    if not os.path.exists(ADV_PARQUET):
        print(f"  WARN: {ADV_PARQUET} missing")
        return 0
    d = pd.read_parquet(ADV_PARQUET, columns=["player_id", "game_id", "game_date"])
    d["game_date"] = d["game_date"].astype(str).str.slice(0, 10)
    d["game_id"] = d["game_id"].astype(str)
    d["player_id"] = pd.to_numeric(d["player_id"], errors="coerce").astype("Int64")
    added = 0
    for pid, gid, gd in zip(d["player_id"], d["game_id"], d["game_date"]):
        if pd.isna(pid) or not gid or not gd:
            continue
        key = (int(pid), gd)
        if key not in out:
            out[key] = gid
            added += 1
    return added


def add_from_adv_boxscores(
    out: Dict[Tuple[int, str], str], gid_to_date: Dict[str, str],
) -> int:
    """Iterate boxscore_adv_<gid>.json files. Returns n_added."""
    added = 0
    n_files = 0
    n_no_date = 0
    for path in sorted(glob.glob(os.path.join(NBA_DIR, "boxscore_adv_*.json"))):
        n_files += 1
        gid = os.path.basename(path).replace("boxscore_adv_", "").replace(".json", "")
        gd = gid_to_date.get(gid)
        if not gd:
            n_no_date += 1
            continue
        try:
            b = json.load(open(path, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        gid_body = str(b.get("game_id", gid) or gid).strip()
        for p in b.get("players", []) or []:
            try:
                pid = int(p.get("personid"))
            except (TypeError, ValueError):
                continue
            key = (pid, gd)
            if key not in out:
                out[key] = gid_body
                added += 1
    print(f"  adv_boxscores: files={n_files} no_date={n_no_date} added={added}")
    return added


def add_from_standard_boxscores(
    out: Dict[Tuple[int, str], str], gid_to_date: Dict[str, str],
) -> int:
    """Iterate boxscore_<gid>.json (not adv) files. Returns n_added."""
    added = 0
    n_files = 0
    n_no_date = 0
    for path in sorted(glob.glob(os.path.join(NBA_DIR, "boxscore_*.json"))):
        if "boxscore_adv_" in os.path.basename(path):
            continue
        n_files += 1
        gid = os.path.basename(path).replace("boxscore_", "").replace(".json", "")
        gd = gid_to_date.get(gid)
        if not gd:
            n_no_date += 1
            continue
        try:
            b = json.load(open(path, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        gid_body = str(b.get("game_id", gid) or gid).strip()
        for p in b.get("players", []) or []:
            try:
                pid = int(p.get("player_id"))
            except (TypeError, ValueError):
                continue
            key = (pid, gd)
            if key not in out:
                out[key] = gid_body
                added += 1
    print(f"  std_boxscores: files={n_files} no_date={n_no_date} added={added}")
    return added


def main() -> int:
    if not os.path.exists(OOF_PATH):
        print(f"ERROR: {OOF_PATH} does not exist")
        return 1

    df = pd.read_parquet(OOF_PATH)
    n_total = len(df)
    n_empty_before = int((df["game_id"] == "").sum())
    print(f"Loaded {OOF_PATH}: rows={n_total}  empty_game_id={n_empty_before}")

    # ---- build maps ----
    print("Building game_id -> game_date map from season_games_*.json ...")
    gid_to_date = build_gameid_date_map()
    print(f"  schedule rows: {len(gid_to_date)}")

    print("Building (player_id, game_date) -> game_id map ...")
    pd_to_gid: Dict[Tuple[int, str], str] = {}

    n_from_parquet = add_from_adv_parquet(pd_to_gid)
    print(f"  player_adv_stats.parquet: added {n_from_parquet}")
    print(f"  cumulative keys: {len(pd_to_gid)}")

    n_from_adv = add_from_adv_boxscores(pd_to_gid, gid_to_date)
    print(f"  cumulative keys: {len(pd_to_gid)}")

    n_from_std = add_from_standard_boxscores(pd_to_gid, gid_to_date)
    print(f"  cumulative keys: {len(pd_to_gid)}")

    # ---- join ----
    df["game_date"] = df["game_date"].astype(str).str.slice(0, 10)
    df["player_id"] = df["player_id"].astype(int)

    keys = list(zip(df["player_id"].tolist(), df["game_date"].tolist()))
    new_gids = [pd_to_gid.get(k, "") for k in keys]

    df["game_id"] = new_gids
    n_filled = int((df["game_id"] != "").sum())
    n_empty_after = n_total - n_filled
    pct_filled = 100.0 * n_filled / max(n_total, 1)
    print(f"Repair result: filled={n_filled}/{n_total} ({pct_filled:.2f}%)  "
          f"still_empty={n_empty_after}")

    # ---- diagnostic: per-stat & per-fold coverage ----
    by_stat = (
        df.assign(filled=(df["game_id"] != "").astype(int))
          .groupby("stat")["filled"].mean() * 100.0
    )
    print("Per-stat fill %:")
    for s, pct in by_stat.items():
        print(f"  {s:5s}: {pct:6.2f}%")

    by_fold = (
        df.assign(filled=(df["game_id"] != "").astype(int))
          .groupby("fold")["filled"].mean() * 100.0
    )
    print("Per-fold fill %:")
    for f, pct in by_fold.items():
        print(f"  fold {f}: {pct:6.2f}%")

    # ---- save ----
    df = df[["game_id", "player_id", "stat", "oof_pred", "actual",
             "game_date", "fold", "season"]]
    df.to_parquet(OOF_PATH, index=False)
    print(f"Wrote {OOF_PATH} ({os.path.getsize(OOF_PATH)//1024} KB)")

    if pct_filled < 80.0:
        print(f"WARNING: coverage {pct_filled:.2f}% below 80% target")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
