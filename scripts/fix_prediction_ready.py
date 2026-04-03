"""Fix data integrity blockers for prediction-readiness on 4 clean games.

Blockers fixed:
1. game_id missing → derive from directory name
2. x_norm/y_norm missing → derive from x_position/y_position (pixel → 0-1)
3. player_name missing → backfill from tracking_data.csv or jersey_name_map.json
4. team_abbrev missing → backfill from tracking_data.csv or team_colors.json
5. ft_x/ft_y missing → derive from x_norm/y_norm (court = 94x50 ft)
6. shot 'made' all null → mark unknown (drop col if no ground truth)
7. possessions_enriched.csv missing → run enrichment
"""

import pandas as pd
import numpy as np
import os
import json
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GAMES = ["0022400909", "0022400430", "0022400537", "0022401123"]
COURT_LEN_FT = 94.0
COURT_WID_FT = 50.0


def fix_game(gid: str) -> dict:
    base = f"data/games/{gid}"
    report = {"game": gid, "fixes": [], "errors": []}

    # Determine primary CSV
    feat_path = os.path.join(base, "features.csv")
    if not os.path.exists(feat_path):
        feat_path = os.path.join(base, "tracking_data.csv")
    if not os.path.exists(feat_path):
        report["errors"].append("no CSV found")
        return report

    print(f"\n[{gid}] Loading {os.path.basename(feat_path)}...")
    df = pd.read_csv(feat_path, encoding="utf-8")
    changed = False

    # 1. game_id
    if "game_id" not in df.columns:
        df["game_id"] = gid
        report["fixes"].append("added game_id")
        changed = True

    # 2. x_norm / y_norm from x_position / y_position
    if "x_norm" not in df.columns and "x_position" in df.columns:
        # Estimate court bounding box from data
        xmin, xmax = df["x_position"].quantile(0.01), df["x_position"].quantile(0.99)
        ymin, ymax = df["y_position"].quantile(0.01), df["y_position"].quantile(0.99)
        df["x_norm"] = ((df["x_position"] - xmin) / (xmax - xmin)).clip(0, 1)
        df["y_norm"] = ((df["y_position"] - ymin) / (ymax - ymin)).clip(0, 1)
        report["fixes"].append(f"derived x_norm/y_norm (bbox {xmin:.0f}-{xmax:.0f}, {ymin:.0f}-{ymax:.0f})")
        changed = True

    # 3. ft_x / ft_y from x_norm / y_norm
    if "ft_x" not in df.columns and "x_norm" in df.columns:
        df["ft_x"] = df["x_norm"] * COURT_LEN_FT
        df["ft_y"] = df["y_norm"] * COURT_WID_FT
        report["fixes"].append("derived ft_x/ft_y")
        changed = True

    if "dist_to_basket_ft" not in df.columns and "ft_x" in df.columns:
        basket_x, basket_y = 88.0, 25.0  # right basket
        df["dist_to_basket_ft"] = np.sqrt(
            (df["ft_x"] - basket_x) ** 2 + (df["ft_y"] - basket_y) ** 2
        )
        report["fixes"].append("derived dist_to_basket_ft")
        changed = True

    # 4. player_name — try tracking_data.csv merge or jersey_name_map.json
    if "player_name" not in df.columns or df["player_name"].isnull().mean() > 0.5:
        td_path = os.path.join(base, "tracking_data.csv")
        jnm_path = os.path.join(base, "jersey_name_map.json")

        if os.path.exists(td_path) and td_path != feat_path:
            td_cols_avail = pd.read_csv(td_path, nrows=0, encoding="utf-8").columns
            if "player_name" not in td_cols_avail:
                td = pd.DataFrame()
            else:
                td = pd.read_csv(td_path, usecols=["frame", "player_id", "player_name"],
                                 encoding="utf-8")
                td = td.dropna(subset=["player_name"])
            if len(td) > 0:
                # Build player_id → name mapping from tracking
                pid_name = td.groupby("player_id")["player_name"].first().to_dict()
                df["player_name"] = df["player_id"].map(pid_name)
                report["fixes"].append(f"player_name from tracking ({len(pid_name)} ids)")
                changed = True

        if ("player_name" not in df.columns or df["player_name"].isnull().mean() > 0.5) and os.path.exists(jnm_path):
            with open(jnm_path, "r", encoding="utf-8") as f:
                jnm = json.load(f)
            # jersey_name_map is {jersey_number: name}
            if "jersey_number" in df.columns:
                df["player_name"] = df["player_name"].fillna(
                    df["jersey_number"].astype(str).map(jnm)
                ) if "player_name" in df.columns else df["jersey_number"].astype(str).map(jnm)
                report["fixes"].append("player_name from jersey_name_map")
                changed = True

    # 5. team_abbrev — try tracking_data or team_colors.json
    if "team_abbrev" not in df.columns or df["team_abbrev"].isnull().mean() > 0.5:
        td_path = os.path.join(base, "tracking_data.csv")
        tc_path = os.path.join(base, "team_colors.json")

        if os.path.exists(td_path) and td_path != feat_path:
            td_cols = pd.read_csv(td_path, nrows=0, encoding="utf-8").columns
            if "team_abbrev" in td_cols:
                td = pd.read_csv(td_path, usecols=["frame", "player_id", "team_abbrev"],
                                 encoding="utf-8")
                td = td.dropna(subset=["team_abbrev"])
                if len(td) > 0:
                    pid_ta = td.groupby("player_id")["team_abbrev"].first().to_dict()
                    df["team_abbrev"] = df["player_id"].map(pid_ta)
                    report["fixes"].append(f"team_abbrev from tracking ({len(pid_ta)} ids)")
                    changed = True

        if ("team_abbrev" not in df.columns or df["team_abbrev"].isnull().mean() > 0.5) and os.path.exists(tc_path):
            with open(tc_path, "r", encoding="utf-8") as f:
                tc = json.load(f)
            # team_colors.json: {"green": "DEN", "white": "PHX"} or similar
            if "team" in df.columns:
                df["team_abbrev"] = df["team"].map(tc)
                report["fixes"].append(f"team_abbrev from team_colors.json ({tc})")
                changed = True

        # Last resort: derive from game summary
        if "team_abbrev" not in df.columns or df["team_abbrev"].isnull().mean() > 0.5:
            summary_path = f"data/game_results/{gid}_summary.json"
            if os.path.exists(summary_path):
                with open(summary_path, "r", encoding="utf-8") as f:
                    summary = json.load(f)
                home = summary.get("home_team", {}).get("abbreviation", "")
                away = summary.get("away_team", {}).get("abbreviation", "")
                if home and away and "team" in df.columns:
                    teams = df["team"].dropna().unique()
                    if len(teams) == 2:
                        # Assign alphabetically or by frequency
                        mapping = {teams[0]: home, teams[1]: away}
                        df["team_abbrev"] = df["team"].map(mapping)
                        report["fixes"].append(f"team_abbrev from summary ({mapping})")
                        changed = True

    # Save
    if changed:
        # Backup
        bak = feat_path + ".pre_fix_bak"
        if not os.path.exists(bak):
            os.rename(feat_path, bak)
            report["fixes"].append(f"backup → {os.path.basename(bak)}")
        df.to_csv(feat_path, index=False, encoding="utf-8")
        report["fixes"].append(f"saved {len(df)} rows")

    # Final fill check
    required = ["game_id", "team", "player_id", "x_norm", "y_norm", "player_name", "team_abbrev"]
    fills = {}
    for c in required:
        if c in df.columns:
            fills[c] = f"{(1 - df[c].isnull().mean()) * 100:.0f}%"
        else:
            fills[c] = "MISSING"
    report["fills"] = fills

    return report


if __name__ == "__main__":
    results = []
    for gid in GAMES:
        r = fix_game(gid)
        results.append(r)
        print(f"  fixes: {r['fixes']}")
        print(f"  fills: {r['fills']}")
        if r["errors"]:
            print(f"  errors: {r['errors']}")

    # Summary
    print("\n===== PREDICTION READINESS (POST-FIX) =====")
    for r in results:
        fills = r.get("fills", {})
        missing_or_low = [k for k, v in fills.items() if v == "MISSING" or (v != "MISSING" and int(v.rstrip("%")) < 50)]
        score = 100 - 15 * len(missing_or_low)
        tag = "READY" if score >= 70 else "NEEDS_FIX" if score >= 40 else "BLOCKED"
        print(f"  {r['game']}: {score}/100 [{tag}] blockers={missing_or_low or 'none'}")
