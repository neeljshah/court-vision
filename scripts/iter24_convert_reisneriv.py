"""iter-24: convert reisneriv 2024 playoffs xlsx into canonical CSV format.

Schema target: date, player, opp, venue, stat, closing_line, over_odds, under_odds, actual_value

Notes:
- reisneriv files name is "NBA_PLAYER_PROPS_AprilXX_*.xlsx" — date inferred from filename.
- LINE USED <STAT> is book consensus; we default odds to -110/-110 (typical prop juice).
- Stat columns present: PTS, REB, AST, 3PM, STL, BLK. (No TOV.)
- Actuals are in plain column name (PTS, REB, AST, 3PM, STL, BLK).
"""
import glob
import os
import re
from datetime import datetime

import pandas as pd

SRC_DIR = "data/external/historical_lines/reisneriv_2024_playoffs"
OUT_PATH = "data/external/historical_lines/reisneriv_2024_canonical.csv"

# (line_col, actual_col, canonical_stat)
STAT_MAP = [
    ("LINE USED PTS", "PTS", "pts"),
    ("LINE USED REB", "REB", "reb"),
    ("LINE USED AST", "AST", "ast"),
    ("LINE USED 3PT", "3PM", "fg3m"),
    ("LINE USED STL", "STL", "stl"),
    ("LINE USED BLK", "BLK", "blk"),
]


def parse_date_from_filename(fn: str) -> str:
    # NBA_PLAYER_PROPS_April21_newRating_colored.xlsx -> 2024-04-21
    m = re.search(r"NBA_PLAYER_PROPS_(April|May)(\d{1,2})", os.path.basename(fn))
    if not m:
        return None
    month_name, day = m.group(1), int(m.group(2))
    month = {"April": 4, "May": 5}[month_name]
    return f"2024-{month:02d}-{day:02d}"


def main():
    rows = []
    files = sorted(glob.glob(os.path.join(SRC_DIR, "NBA_PLAYER_PROPS_*_colored.xlsx")))
    print(f"reisneriv files: {len(files)}")
    for fp in files:
        date = parse_date_from_filename(fp)
        if not date:
            continue
        try:
            df = pd.read_excel(fp)
        except Exception as e:
            print(f"  skip {os.path.basename(fp)}: {e}")
            continue
        for _, r in df.iterrows():
            fn = str(r.get("First_Name", "")).strip()
            ln = str(r.get("Last_Name", "")).strip()
            if not fn or fn == "nan" or not ln or ln == "nan":
                continue
            player = f"{fn} {ln}"
            opp = str(r.get("OPPONENT", "")).strip()
            home_away = str(r.get("Home/Away", "")).strip()
            venue = "home" if home_away.lower() == "home" else "away"
            for line_col, actual_col, stat in STAT_MAP:
                if line_col not in df.columns or actual_col not in df.columns:
                    continue
                line_v = r.get(line_col)
                actual_v = r.get(actual_col)
                # Drop rows where line is missing/zero or actual is missing
                try:
                    line_f = float(line_v)
                    actual_f = float(actual_v)
                except (TypeError, ValueError):
                    continue
                if line_f <= 0:
                    continue
                rows.append(
                    {
                        "date": date,
                        "player": player,
                        "opp": opp,
                        "venue": venue,
                        "stat": stat,
                        "closing_line": line_f,
                        "over_odds": -110,
                        "under_odds": -110,
                        "actual_value": actual_f,
                    }
                )
    out = pd.DataFrame(rows)
    print(f"converted rows: {len(out)}")
    if len(out):
        print(f"date range: {out['date'].min()} -> {out['date'].max()}")
        print(f"unique (date,player): {out[['date','player']].drop_duplicates().shape[0]}")
        print(f"stat counts: {out['stat'].value_counts().to_dict()}")
        os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
        out.to_csv(OUT_PATH, index=False)
        print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
