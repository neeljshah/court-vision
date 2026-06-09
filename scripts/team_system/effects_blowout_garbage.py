"""
effects_blowout_garbage.py
--------------------------
Measure how blowout (final margin >= 15 pts) affects:
  1. Starter minutes played (vs close games)
  2. Starter field-goal attempts (usage proxy)
  3. Bench minutes / FGA share rise

Sources:
  - data/cache/team_system/box/*.json  (box scores per game, 196 games 2025-26)
  - data/cache/team_system/team_game.parquet  (margin / game-level)

We measure FINAL margin (not Q4 lead) as a proxy because:
- Close games = final margin <= 5 (competitive throughout Q4)
- Blowout   = final margin >= 15 (garbage time expected in Q4)

All analysis is per-team-game side (i.e. each game contributes 2 rows,
one per team, allowing us to measure both winning AND losing team starters).
"""

import json, os, re
import numpy as np
import pandas as pd
from scipy import stats

BOX_DIR  = "C:/Users/neelj/nba-ai-system/data/cache/team_system/box"
TG_PATH  = "C:/Users/neelj/nba-ai-system/data/cache/team_system/team_game.parquet"

BLOWOUT_THRESH = 15   # final margin >= 15 → blowout
CLOSE_THRESH   = 5    # final margin <= 5  → close game


def parse_min(min_str: str) -> float:
    """Parse 'PT37M30.00S' → 37.5 minutes."""
    if not min_str:
        return 0.0
    m = re.match(r"PT(\d+)M([\d.]+)S", str(min_str))
    if m:
        return int(m.group(1)) + float(m.group(2)) / 60.0
    try:
        return float(min_str)
    except Exception:
        return 0.0


def load_box_game(gid: str) -> dict:
    """Return dict with per-team starter/bench minute + FGA splits."""
    path = os.path.join(BOX_DIR, f"{gid}.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        game = json.load(f)["game"]

    result = {}
    for team_key, score_key in [("homeTeam", "scoreHome"), ("awayTeam", "scoreAway")]:
        team = game[team_key]
        tc   = team["teamTricode"]
        rows = []
        for p in team["players"]:
            st      = p["statistics"]
            mins    = parse_min(st.get("minutes", ""))
            fga     = st.get("fieldGoalsAttempted", 0)
            fgm     = st.get("fieldGoalsMade", 0)
            pts     = st.get("points", 0)
            starter = int(p.get("starter", "0") == "1")
            rows.append({"starter": starter, "min": mins, "fga": fga, "fgm": fgm, "pts": pts})
        if rows:
            result[tc] = rows
    return result


def main():
    # Load team-game table for final margins
    tg = pd.read_parquet(TG_PATH)
    # Compute final margin per game-team (positive = won by this margin)
    tg["margin"] = tg["pts"] - tg["opp_pts"]

    # Build per game: game_id → {team → margin}
    game_margins = {}
    for _, row in tg.iterrows():
        gid = str(row["gid"]).zfill(10)
        game_margins.setdefault(gid, {})[row["team"]] = row["margin"]

    records = []
    for fname in sorted(os.listdir(BOX_DIR)):
        if not fname.endswith(".json"):
            continue
        gid = fname.replace(".json", "")
        box_data = load_box_game(gid)
        margins  = game_margins.get(gid, {})

        for tc, players in box_data.items():
            margin = margins.get(tc)
            if margin is None:
                continue  # game not in team_game (skip)

            # Aggregate starters vs bench
            starters = [p for p in players if p["starter"] == 1]
            bench    = [p for p in players if p["starter"] == 0 and p["min"] > 0]

            if not starters:
                continue

            starter_min  = sum(p["min"] for p in starters)
            starter_fga  = sum(p["fga"] for p in starters)
            bench_min    = sum(p["min"] for p in bench)
            bench_fga    = sum(p["fga"] for p in bench)
            total_min    = starter_min + bench_min
            total_fga    = starter_fga + bench_fga

            records.append({
                "gid":          gid,
                "team":         tc,
                "margin":       margin,
                "abs_margin":   abs(margin),
                "starter_min":  starter_min,
                "bench_min":    bench_min,
                "total_min":    total_min,
                "starter_fga":  starter_fga,
                "bench_fga":    bench_fga,
                "total_fga":    total_fga,
                "starter_min_share": starter_min / total_min if total_min > 0 else np.nan,
                "bench_min_share":   bench_min  / total_min if total_min > 0 else np.nan,
                "starter_fga_share": starter_fga / total_fga if total_fga > 0 else np.nan,
                "bench_fga_share":   bench_fga  / total_fga if total_fga > 0 else np.nan,
            })

    df = pd.DataFrame(records)
    print(f"Total team-game observations: {len(df)}")
    print(f"Margin distribution: min={df['margin'].min()}, max={df['margin'].max()}, mean={df['margin'].mean():.1f}")
    print()

    # Split: blowout vs close
    blow  = df[df["abs_margin"] >= BLOWOUT_THRESH]
    close = df[df["abs_margin"] <= CLOSE_THRESH]

    print(f"Blowout games (|margin| >= {BLOWOUT_THRESH}): {len(blow)} team-sides ({len(blow)//2} games)")
    print(f"Close games   (|margin| <= {CLOSE_THRESH}):  {len(close)} team-sides ({len(close)//2} games)")
    print()

    metrics = [
        ("starter_min",       "Starter raw minutes"),
        ("bench_min",         "Bench raw minutes"),
        ("starter_min_share", "Starter % of team minutes"),
        ("bench_min_share",   "Bench % of team minutes"),
        ("starter_fga",       "Starter FGA (raw)"),
        ("bench_fga",         "Bench FGA (raw)"),
        ("starter_fga_share", "Starter FGA share"),
        ("bench_fga_share",   "Bench FGA share"),
    ]

    print(f"{'Metric':<30} {'Blowout':>10} {'Close':>10} {'Delta':>10} {'Mult':>8} {'p-val':>8}")
    print("-" * 82)
    results = {}
    for col, label in metrics:
        b_val = blow[col].mean()
        c_val = close[col].mean()
        delta = b_val - c_val
        mult  = b_val / c_val if c_val != 0 else np.nan
        t_stat, p_val = stats.ttest_ind(blow[col].dropna(), close[col].dropna())
        print(f"{label:<30} {b_val:>10.3f} {c_val:>10.3f} {delta:>+10.3f} {mult:>8.4f} {p_val:>8.4f}")
        results[col] = {"blowout": b_val, "close": c_val, "delta": delta, "mult": mult, "p": p_val}
    print()

    # Starter minutes: breakdown by win/loss in blowout
    blow_win  = blow[blow["margin"] > 0]
    blow_loss = blow[blow["margin"] < 0]
    print(f"Blowout WINNERS starter min:  {blow_win['starter_min'].mean():.2f}")
    print(f"Blowout LOSERS  starter min:  {blow_loss['starter_min'].mean():.2f}")
    print(f"Close   all     starter min:  {close['starter_min'].mean():.2f}")
    print()

    # Per-starter headcount check: how many starters play < 30 min in blowouts vs close?
    # Use per-player level  from box scores
    player_rows = []
    for fname in sorted(os.listdir(BOX_DIR)):
        if not fname.endswith(".json"):
            continue
        gid = fname.replace(".json", "")
        margins = game_margins.get(gid, {})
        path = os.path.join(BOX_DIR, f"{gid}.json")
        with open(path) as f:
            game = json.load(f)["game"]
        for team_key in ["homeTeam", "awayTeam"]:
            team = game[team_key]
            tc   = team["teamTricode"]
            margin = margins.get(tc)
            if margin is None:
                continue
            for p in team["players"]:
                if p.get("starter", "0") != "1":
                    continue
                st = p["statistics"]
                mins = parse_min(st.get("minutes", ""))
                fga  = st.get("fieldGoalsAttempted", 0)
                player_rows.append({
                    "gid": gid, "team": tc, "player": p["nameI"],
                    "margin": margin, "abs_margin": abs(margin), "min": mins, "fga": fga
                })

    pf = pd.DataFrame(player_rows)
    print(f"Starter player-game observations: {len(pf)}")

    pb = pf[pf["abs_margin"] >= BLOWOUT_THRESH]
    pc = pf[pf["abs_margin"] <= CLOSE_THRESH]

    print(f"\nPer-starter (blowout vs close):")
    print(f"  Blowout starter min/game: {pb['min'].mean():.2f}  (n={len(pb)})")
    print(f"  Close   starter min/game: {pc['min'].mean():.2f}  (n={len(pc)})")
    print(f"  Blowout starter FGA/game: {pb['fga'].mean():.2f}")
    print(f"  Close   starter FGA/game: {pc['fga'].mean():.2f}")

    t_min, p_min = stats.ttest_ind(pb["min"], pc["min"])
    t_fga, p_fga = stats.ttest_ind(pb["fga"], pc["fga"])
    print(f"  min delta: {pb['min'].mean() - pc['min'].mean():+.2f} min  p={p_min:.4f}")
    print(f"  FGA delta: {pb['fga'].mean() - pc['fga'].mean():+.2f} FGA  p={p_fga:.4f}")

    # Starter min multiplier in blowouts relative to close
    min_mult = pb["min"].mean() / pc["min"].mean()
    fga_mult = pb["fga"].mean() / pc["fga"].mean()
    print(f"\n  Starter min multiplier (blowout/close): {min_mult:.4f}")
    print(f"  Starter FGA multiplier (blowout/close): {fga_mult:.4f}")
    print()

    # How much bench usage rises: bench share shift
    b_bench_share = blow["bench_min_share"].mean()
    c_bench_share = close["bench_min_share"].mean()
    bench_share_delta = b_bench_share - c_bench_share
    print(f"Bench minute share:  blowout={b_bench_share:.4f}  close={c_bench_share:.4f}  delta={bench_share_delta:+.4f}")
    b_bench_fga_share = blow["bench_fga_share"].mean()
    c_bench_fga_share = close["bench_fga_share"].mean()
    print(f"Bench FGA share:     blowout={b_bench_fga_share:.4f}  close={c_bench_fga_share:.4f}  delta={b_bench_fga_share - c_bench_fga_share:+.4f}")

    # Sanity: average team total minutes should be ~240 (5x48); blowout vs close?
    print(f"\nAvg team total min:  blowout={blow['total_min'].mean():.1f}  close={close['total_min'].mean():.1f}")

    print("\n=== HEADLINE NUMBERS ===")
    print(f"Starter MPG in close games:   {pc['min'].mean():.2f}")
    print(f"Starter MPG in blowouts:      {pb['min'].mean():.2f}")
    print(f"Starter min multiplier:       {min_mult:.4f}  ({(min_mult-1)*100:+.1f}%)")
    print(f"Starter FGA multiplier:       {fga_mult:.4f}  ({(fga_mult-1)*100:+.1f}%)")
    print(f"Bench min share delta:        {bench_share_delta:+.4f}  ({bench_share_delta*100:+.1f} ppts)")
    print(f"N blowout team-sides: {len(blow)}, N close team-sides: {len(close)}")
    print(f"p-value (starter min): {p_min:.4f}")


if __name__ == "__main__":
    main()
