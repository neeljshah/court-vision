"""cv_tracking_stats.py -- volume/coverage stats for data/nba_ai.db:cv_features.

HONESTY: volume/coverage ONLY. No accuracy/quality claims -- MOT tracking
metrics are unbenchmarked (docs/JOB_EVIDENCE_PACKET.md s4). This module never
computes or prints anything resembling precision/recall/MOTA/IDF1.

Schema (inspected live): cv_features(id, game_id, player_id, feature_name,
feature_value, created_at). No date/season/name column or table exists on
this row's join path (box_scores.player_id join returns 0 matches) -- so
season/date breakdown and player names are correctly omitted, not guessed.

Usage: python cv_tracking_stats.py [--check]
"""
import argparse
import json
import sqlite3
import statistics
from pathlib import Path

DB = Path(__file__).resolve().parents[3] / "data" / "nba_ai.db"
OUT_DIR = Path(__file__).resolve().parent / "out"
IMG_DIR = Path(__file__).resolve().parents[3] / "docs" / "img"


def compute_stats(con: sqlite3.Connection) -> dict:
    cur = con.cursor()

    # rows per game (distinct game_id, player_id) -- feature rows are long-format
    # so "rows per game" = feature-row count per game_id.
    cur.execute("SELECT game_id, COUNT(*) FROM cv_features GROUP BY game_id")
    rows_per_game = [c for _, c in cur.fetchall()]

    cur.execute(
        "SELECT game_id, COUNT(DISTINCT player_id) FROM cv_features GROUP BY game_id"
    )
    players_per_game = [c for _, c in cur.fetchall()]

    cur.execute("SELECT COUNT(*) FROM cv_features")
    total_rows = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT game_id) FROM cv_features")
    n_games = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT player_id) FROM cv_features")
    n_players = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT feature_name) FROM cv_features")
    n_feature_names = cur.fetchone()[0]

    cur.execute("SELECT MIN(created_at), MAX(created_at) FROM cv_features")
    created_min, created_max = cur.fetchone()

    cur.execute(
        "SELECT player_id, COUNT(*) AS n FROM cv_features "
        "GROUP BY player_id ORDER BY n DESC LIMIT 20"
    )
    top20 = [{"player_id": pid, "row_count": n} for pid, n in cur.fetchall()]

    def dist(vals):
        if not vals:
            return {"min": 0, "max": 0, "mean": 0, "median": 0}
        return {
            "min": min(vals),
            "max": max(vals),
            "mean": round(statistics.mean(vals), 2),
            "median": statistics.median(vals),
        }

    return {
        "note": "volume/coverage stats only -- no accuracy/quality claims (MOT metrics unbenchmarked, see JOB_EVIDENCE_PACKET s4)",
        "total_rows": total_rows,
        "n_games": n_games,
        "n_players": n_players,
        "n_distinct_feature_names": n_feature_names,
        "created_at_range": {"min": created_min, "max": created_max},
        "season_or_date_breakdown": "not available -- cv_features has no date/season column; box_scores join on (game_id, player_id) returns 0 matching rows",
        "rows_per_game": dist(rows_per_game),
        "distinct_players_per_game": dist(players_per_game),
        "top20_most_tracked_player_ids": top20,
    }


def make_chart(stats: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    top = stats["top20_most_tracked_player_ids"]
    ids = [str(r["player_id"]) for r in top]
    counts = [r["row_count"] for r in top]
    axes[0].barh(ids[::-1], counts[::-1], color="#4C72B0")
    axes[0].set_title("Top 20 most-tracked player IDs (cv_features row count)")
    axes[0].set_xlabel("row count")

    rpg = stats["rows_per_game"]
    axes[1].bar(
        ["min", "median", "mean", "max"],
        [rpg["min"], rpg["median"], rpg["mean"], rpg["max"]],
        color="#DD8452",
    )
    axes[1].set_title("cv_features rows per game (distribution)")
    axes[1].set_ylabel("rows")

    fig.suptitle("cv_tracking_stats -- volume/coverage only (no accuracy claims)")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="self-check only, no writes")
    args = ap.parse_args()

    con = sqlite3.connect(str(DB))
    try:
        stats = compute_stats(con)
    finally:
        con.close()

    if args.check:
        assert stats["total_rows"] > 0
        assert stats["n_games"] > 0
        assert len(stats["top20_most_tracked_player_ids"]) > 0
        print("--check OK:", stats["total_rows"], "rows,", stats["n_games"], "games")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    out_json = OUT_DIR / "cv_tracking_stats.json"
    out_json.write_text(json.dumps(stats, indent=2), encoding="utf-8")

    img_path = IMG_DIR / "cv_tracking_stats.png"
    make_chart(stats, img_path)

    print("wrote", out_json)
    print("wrote", img_path)
    print("total_rows:", stats["total_rows"], "n_games:", stats["n_games"], "n_players:", stats["n_players"])


if __name__ == "__main__":
    main()
