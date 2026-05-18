"""
query_cv_features.py — Query CV-derived features from the database.

Usage
-----
    conda activate basketball_ai

    # Last 5 games of CV features for a player
    python scripts/query_cv_features.py --player "LeBron James" --last 5

    # All CV features for a specific game
    python scripts/query_cv_features.py --game-id 0022400625

    # List all games that have CV features
    python scripts/query_cv_features.py --list-games

    # All players in the CV feature store
    python scripts/query_cv_features.py --list-players
"""

import argparse
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)


def _get_conn():
    from src.data.db import get_connection
    return get_connection()


def list_games():
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT game_id, COUNT(*) as n_records "
            "FROM cv_features GROUP BY game_id ORDER BY game_id"
        )
        rows = cur.fetchall()
    conn.close()
    if not rows:
        print("No CV feature data found in DB.")
        return
    print(f"\n{'game_id':15s}  {'records':>8}")
    print("-" * 26)
    for r in rows:
        print(f"{r[0]:15s}  {r[1]:>8,}")
    print(f"\nTotal: {len(rows)} games with CV features.")


def list_players():
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT player_id, COUNT(DISTINCT game_id) as n_games "
            "FROM cv_features GROUP BY player_id ORDER BY n_games DESC"
        )
        rows = cur.fetchall()
    conn.close()
    if not rows:
        print("No player CV data found in DB.")
        return
    print(f"\n{'player_id':12s}  {'games':>6}")
    print("-" * 21)
    for r in rows:
        print(f"{r[0]:<12}  {r[1]:>6,}")
    print(f"\nTotal: {len(rows)} players with CV features.")


def query_player(player_name: str, last_n: int):
    """Query CV features for a player by name (fuzzy match via NBA data cache)."""
    # First try to find player_id from cached data
    player_id = _resolve_player_name(player_name)
    if player_id is None:
        print(f"Could not resolve player_id for '{player_name}'")
        print("Try using --player-id directly if you know the NBA player_id.")
        return

    print(f"\nCV features for {player_name!r} (player_id={player_id}) — last {last_n} games\n")
    _print_player_cv(player_id, last_n)


def query_player_id(player_id: int, last_n: int):
    print(f"\nCV features for player_id={player_id} — last {last_n} games\n")
    _print_player_cv(player_id, last_n)


def _print_player_cv(player_id: int, last_n: int):
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT game_id FROM cv_features "
            "WHERE player_id = ? "
            "GROUP BY game_id ORDER BY MAX(created_at) DESC LIMIT ?",
            (player_id, last_n),
        )
        game_ids = [r[0] for r in cur.fetchall()]

    if not game_ids:
        print(f"  No CV data found for player_id={player_id}.")
        conn.close()
        return

    for gid in game_ids:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT feature_name, feature_value FROM cv_features "
                "WHERE player_id = ? AND game_id = ? ORDER BY feature_name",
                (player_id, gid),
            )
            feats = cur.fetchall()
        print(f"  Game {gid}")
        for f in feats:
            print(f"    {f[0]:35s}  {f[1]:.4f}")
        print()

    conn.close()


def query_game(game_id: str):
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT player_id, feature_name, feature_value "
            "FROM cv_features WHERE game_id = ? "
            "ORDER BY player_id, feature_name",
            (game_id,),
        )
        rows = cur.fetchall()
    conn.close()

    if not rows:
        print(f"No CV data found for game_id={game_id}.")
        return

    print(f"\nCV features for game {game_id}\n")
    cur_pid = None
    for r in rows:
        if r[0] != cur_pid:
            cur_pid = r[0]
            print(f"  player_id={cur_pid}")
        print(f"    {r[1]:35s}  {r[2]:.4f}")
    print()


def _resolve_player_name(name: str):
    """Try to find a player_id from name via cached NBA data or DB."""
    import json, os, unicodedata, re
    cache_dir = os.path.join(PROJECT_DIR, "data", "nba")
    norm = lambda s: unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    target = norm(name)

    # 1. Try player_avgs cache
    for fname in sorted(os.listdir(cache_dir)) if os.path.isdir(cache_dir) else []:
        if fname.startswith("player_avgs_") and fname.endswith(".json"):
            try:
                with open(os.path.join(cache_dir, fname)) as f:
                    data = json.load(f)
                for pname, stats in data.items():
                    if norm(pname) == target:
                        pid = stats.get("PLAYER_ID") or stats.get("player_id")
                        if pid:
                            return int(pid)
            except Exception:
                pass

    # 2. Try gamelog cache files
    for fname in sorted(os.listdir(cache_dir)) if os.path.isdir(cache_dir) else []:
        if fname.startswith("gamelog_full_") and fname.endswith(".json"):
            try:
                m = re.search(r"gamelog_full_(\d+)", fname)
                if not m:
                    continue
                pid = int(m.group(1))
                with open(os.path.join(cache_dir, fname)) as f:
                    data = json.load(f)
                if data and isinstance(data, list):
                    pname_found = (data[0].get("player_name") or
                                   data[0].get("PLAYER_NAME") or "")
                    if norm(str(pname_found)) == target:
                        return pid
            except Exception:
                pass

    return None


def main():
    ap = argparse.ArgumentParser(
        description="Query CV-derived player features from the basketball_ai DB."
    )
    ap.add_argument("--player",    default="", help="Player name (e.g. 'LeBron James')")
    ap.add_argument("--player-id", type=int,   help="NBA player_id integer")
    ap.add_argument("--game-id",   default="", help="NBA game_id to query")
    ap.add_argument("--last",      type=int, default=5, help="Last N games (default 5)")
    ap.add_argument("--list-games",   action="store_true", help="List all games with CV data")
    ap.add_argument("--list-players", action="store_true", help="List all players with CV data")
    args = ap.parse_args()

    if args.list_games:
        list_games()
    elif args.list_players:
        list_players()
    elif args.game_id:
        query_game(args.game_id)
    elif args.player_id:
        query_player_id(args.player_id, args.last)
    elif args.player:
        query_player(args.player, args.last)
    else:
        ap.print_help()
        print("\nExample: python scripts/query_cv_features.py --player 'LeBron James' --last 5")


if __name__ == "__main__":
    main()
