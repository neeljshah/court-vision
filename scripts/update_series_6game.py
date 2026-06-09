"""update_series_6game.py — extend WCF series player averages from 4 games to 6.

Adds real Game 5 (5/26, OKC 127-114) + Game 6 (5/28, SAS 118-91) box scores
(pulled from ESPN) on top of the existing 4-game wcf_player_series_avg.csv.
Per-game GP is tracked honestly (ESPN truncated some G5 bench lines -> those
players just keep the games we have). Writes wcf_player_series_avg_6g.csv.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd

I26 = Path(r"C:\Users\neelj\nba-ai-system\data\cache\intel_2026-05-26")
SRC = I26 / "wcf_player_series_avg.csv"
OUT = I26 / "wcf_player_series_avg_6g.csv"

STATS = ["pts", "reb", "ast", "stl", "blk", "tov", "fg3m"]
# order: min, pts, reb, ast, stl, blk, tov, fg3m
G5 = {
    # OKC
    "Isaiah Hartenstein": (31, 12, 15, 4, 0, 1, 3, 0),
    "Chet Holmgren": (30, 16, 11, 1, 1, 1, 3, 0),
    "Shai Gilgeous-Alexander": (37, 32, 2, 9, 2, 1, 6, 2),
    "Luguentz Dort": (18, 7, 4, 0, 0, 0, 0, 1),
    "Jared McCain": (33, 20, 3, 0, 0, 0, 2, 3),
    "Alex Caruso": (28, 22, 2, 6, 3, 0, 2, 4),
    "Kenrich Williams": (31, 7, 4, 5, 2, 2, 0, 1),
    # SAS
    "Julian Champagnie": (30, 22, 8, 1, 3, 0, 2, 4),
    "Victor Wembanyama": (38, 20, 6, 1, 2, 3, 2, 0),
    "De'Aaron Fox": (33, 9, 4, 8, 3, 0, 1, 0),
    "Devin Vassell": (36, 6, 4, 4, 3, 0, 1, 2),
    "Stephon Castle": (33, 24, 5, 6, 3, 0, 3, 3),
    "Keldon Johnson": (20, 15, 4, 2, 0, 0, 2, 1),
    "Jordan McLaughlin": (25, 5, 6, 3, 0, 0, 3, 1),
}
G6 = {
    "Isaiah Hartenstein": (16, 10, 5, 3, 0, 0, 0, 0),
    "Chet Holmgren": (24, 10, 11, 1, 1, 2, 0, 0),
    "Shai Gilgeous-Alexander": (28, 15, 1, 4, 0, 0, 2, 0),
    "Luguentz Dort": (23, 5, 1, 0, 1, 1, 1, 1),
    "Jared McCain": (27, 13, 2, 6, 2, 0, 2, 2),
    "Jaylin Williams": (26, 4, 9, 2, 0, 0, 0, 0),
    "Alex Caruso": (21, 7, 0, 0, 1, 0, 0, 1),
    "Kenrich Williams": (15, 7, 6, 2, 0, 0, 1, 1),
    "Isaiah Joe": (16, 3, 4, 2, 0, 0, 1, 1),
    "Aaron Wiggins": (7, 5, 0, 0, 0, 0, 1, 1),
    "Jalen Williams": (10, 1, 0, 1, 0, 0, 2, 0),
    "Cason Wallace": (6, 0, 0, 0, 1, 0, 0, 0),
    "Nikola Topić": (20, 11, 3, 1, 3, 0, 2, 3),
    "Julian Champagnie": (25, 10, 6, 2, 1, 2, 1, 2),
    "Victor Wembanyama": (28, 28, 10, 2, 2, 3, 3, 4),
    "De'Aaron Fox": (26, 5, 5, 7, 0, 0, 0, 0),
    "Devin Vassell": (26, 12, 1, 2, 1, 2, 1, 4),
    "Stephon Castle": (32, 17, 5, 9, 1, 0, 1, 0),
    "Harrison Barnes": (13, 6, 1, 0, 0, 0, 1, 2),
    "Kelly Olynyk": (5, 6, 1, 0, 0, 0, 0, 0),
    "Lindy Waters III": (6, 2, 0, 1, 1, 0, 0, 0),
    "Keldon Johnson": (18, 9, 3, 0, 1, 0, 1, 1),
    "Carter Bryant": (8, 2, 4, 0, 0, 0, 1, 0),
    "Bismack Biyombo": (5, 0, 0, 0, 0, 0, 0, 0),
    "Mason Plumlee": (5, 0, 1, 0, 0, 0, 0, 0),
    "Luke Kornet": (13, 3, 5, 1, 0, 0, 1, 0),
    "Jordan McLaughlin": (7, 0, 4, 2, 0, 0, 1, 0),
    "Dylan Harper": (22, 18, 6, 4, 0, 0, 1, 2),
}
COLS = ["min"] + STATS  # tuple order


def main():
    df = pd.read_csv(SRC)
    rows = []
    for _, r in df.iterrows():
        name = r["player_name"]
        gp0 = float(r["gp"]) if pd.notna(r["gp"]) else 0
        # rebuild totals for each stat from 4-game avg
        rec = dict(r)
        for stat in STATS + ["min"]:
            col = "min_pg" if stat == "min" else f"{stat}_pg"
            avg = r.get(col)
            tot = (float(avg) * gp0) if pd.notna(avg) else 0.0
            gp = gp0 if pd.notna(avg) else 0.0
            for G in (G5, G6):
                if name in G:
                    tot += G[name][COLS.index(stat)]
                    gp += 1
            rec[col] = round(tot / gp, 3) if gp > 0 else avg
        # gp = max games any stat counted (use min-based)
        gpn = gp0 + (name in G5) + (name in G6)
        rec["gp"] = int(gpn)
        rows.append(rec)
    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)
    show = out[out.player_name.isin([
        "Victor Wembanyama", "Shai Gilgeous-Alexander", "Stephon Castle", "De'Aaron Fox",
        "Devin Vassell", "Dylan Harper", "Jared McCain", "Chet Holmgren", "Alex Caruso",
        "Isaiah Hartenstein", "Julian Champagnie", "Keldon Johnson"])]
    print("6-GAME SERIES AVERAGES (key rotation):")
    print(show[["player_name", "team", "gp", "min_pg", "pts_pg", "reb_pg", "ast_pg", "fg3m_pg"]]
          .sort_values("pts_pg", ascending=False).to_string(index=False))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
