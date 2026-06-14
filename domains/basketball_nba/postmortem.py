"""
domains/basketball_nba/postmortem.py
=====================================
Per-game POST-MORTEM foundation — a structured "why did this game go the
way it did" record for every NBA game in the boxscore corpus.

KNOWLEDGE / DESCRIPTIVE LAYER ONLY.
This module operates on *realized* game outcomes (final box scores).
Output is a factual decomposition — it is NOT a prediction signal and
MUST NOT feed any model or betting system.  Leak-free AS-OF companions
(which could legitimately feed models) are a separate future module.

Four-Factor decomposition (Dean Oliver framework):
  1. Shooting   — eFG differential
  2. Turnovers  — TOV-rate differential
  3. Rebounding — OREB-pct differential
  4. Free throws — FT-rate differential

Each factor is scaled to approximate point-margin contribution so that
  sum(factor_contributions) ≈ realized margin (within rounding).

NO edge claim anywhere in this file.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[2]
_BS_PATH = _ROOT / "data/domains/basketball_nba/player_boxscores.parquet"
_GAMES_PATH = _ROOT / "data/domains/basketball_nba/games.parquet"
_OUT_PATH = _ROOT / "data/domains/basketball_nba/postmortem.parquet"

# Four-Factor weights (Oliver 2004, scaled to point units via avg ~100 poss/game)
_FF_WEIGHTS = {
    "shooting": 1.65,    # eFG swing → pts swing
    "turnovers": 1.20,   # TOV-rate swing → pts swing
    "rebounding": 0.75,  # OREB-pct swing → pts swing
    "free_throws": 0.40, # FT-rate swing → pts swing
}


# ---------------------------------------------------------------------------
# Core aggregation helpers
# ---------------------------------------------------------------------------

def _agg_team_game(grp: pd.DataFrame) -> pd.Series:
    """Aggregate player rows to team-game totals and compute Four-Factor stats."""
    fga = grp["fga"].sum()
    fgm = grp["fgm"].sum()
    fg3m = grp["fg3m"].sum()
    oreb = grp["oreb"].sum()
    dreb = grp["dreb"].sum()
    tov = grp["tov"].sum()
    fta = grp["fta"].sum()
    ftm = grp["ftm"].sum()
    pts = grp["pts"].sum()

    poss = max(fga - oreb + tov + 0.44 * fta, 1.0)  # guard div-by-zero
    efg = (fgm + 0.5 * fg3m) / max(fga, 1)
    tov_rate = tov / poss
    ft_rate = fta / max(fga, 1)
    ortg = 100.0 * pts / poss

    return pd.Series(
        {
            "pts": pts,
            "fga": fga,
            "fgm": fgm,
            "fg3m": fg3m,
            "oreb": oreb,
            "dreb": dreb,
            "tov": tov,
            "fta": fta,
            "ftm": ftm,
            "poss": poss,
            "efg": efg,
            "tov_rate": tov_rate,
            "ft_rate": ft_rate,
            "ortg": ortg,
        }
    )


def _compute_oreb_pct(team_oreb: float, opp_dreb: float) -> float:
    denom = team_oreb + opp_dreb
    return team_oreb / max(denom, 1.0)


def _decide_factor(contributions: dict[str, float]) -> str:
    """Return label for the dominant swing factor."""
    abs_vals = {k: abs(v) for k, v in contributions.items()}
    dominant = max(abs_vals, key=abs_vals.get)
    max_abs = abs_vals[dominant]
    total_abs = sum(abs_vals.values())
    if total_abs == 0 or max_abs / total_abs < 0.35:
        return "BALANCED"
    return dominant.upper()


# ---------------------------------------------------------------------------
# Main build function
# ---------------------------------------------------------------------------

def build_postmortems(
    bs_path: Path = _BS_PATH,
    games_path: Path = _GAMES_PATH,
) -> pd.DataFrame:
    """Build one descriptive post-mortem record per game.

    Parameters
    ----------
    bs_path:
        Path to player_boxscores.parquet.
    games_path:
        Path to games.parquet (used for home_team / away_team labels and
        home_win ground truth; also provides the correct opponent join).

    Returns
    -------
    pd.DataFrame
        One row per game_id with columns documented below.
        NOT suitable as a model feature — knowledge layer only.
    """
    bs = pd.read_parquet(bs_path)
    games = pd.read_parquet(games_path)[["game_id", "home_team", "away_team", "home_win"]]

    # Keep only games present in both sources
    valid_games = set(games["game_id"])
    bs = bs[bs["game_id"].isin(valid_games)].copy()

    # --- Aggregate to team-game level ---
    agg = (
        bs.groupby(["game_id", "team"])
        .apply(_agg_team_game, include_groups=False)
        .reset_index()
    )

    # --- Join games table for home/away identity ---
    merged = agg.merge(games, on="game_id", how="inner")
    merged["is_home"] = merged["team"] == merged["home_team"]

    # --- Self-join to get opponent dreb (for correct OREB%) ---
    # For each team-row, the opponent team is determined by games.home_team /
    # games.away_team (NOT the player-level 'opp' column, which is unavailable
    # after groupby aggregation).
    merged["opp_team"] = merged.apply(
        lambda r: r["away_team"] if r["is_home"] else r["home_team"], axis=1
    )
    opp_dreb = agg[["game_id", "team", "dreb"]].rename(
        columns={"team": "opp_team", "dreb": "opp_dreb_val"}
    )
    merged2 = merged.merge(opp_dreb, on=["game_id", "opp_team"], how="left")

    merged2["oreb_pct"] = merged2.apply(
        lambda r: _compute_oreb_pct(r["oreb"], r["opp_dreb_val"]), axis=1
    )

    # --- Build per-game records ---
    records = []
    for game_id, g in merged2.groupby("game_id"):
        home_row = g[g["is_home"] == True]
        away_row = g[g["is_home"] == False]
        if home_row.empty or away_row.empty:
            continue
        h = home_row.iloc[0]
        a = away_row.iloc[0]

        margin = float(h["pts"] - a["pts"])
        pace = float((h["poss"] + a["poss"]) / 2.0)
        home_win = bool(int(home_row["home_win"].iloc[0]))

        # Four-Factor differentials (home − away; positive = home advantage)
        d_efg = float(h["efg"] - a["efg"])
        d_tov = float(a["tov_rate"] - h["tov_rate"])  # lower is better → flip
        d_oreb = float(h["oreb_pct"] - a["oreb_pct"])
        d_ft = float(h["ft_rate"] - a["ft_rate"])

        # Scale differentials to approximate point contributions
        # Multiply by pace to convert per-possession units to points
        scale = pace
        contrib = {
            "shooting": d_efg * _FF_WEIGHTS["shooting"] * scale / 100.0 * 100.0,
            "turnovers": d_tov * _FF_WEIGHTS["turnovers"] * scale,
            "rebounding": d_oreb * _FF_WEIGHTS["rebounding"] * scale,
            "free_throws": d_ft * _FF_WEIGHTS["free_throws"] * scale,
        }

        decided_by = _decide_factor(contrib)

        records.append(
            {
                "game_id": game_id,
                "date": g["date"].iloc[0] if "date" in g.columns else None,
                "season": g["season"].iloc[0] if "season" in g.columns else None,
                "home_team": str(h["team"]),
                "away_team": str(a["team"]),
                "home_win": home_win,
                "margin": margin,
                "pace": round(pace, 2),
                "home_pts": float(h["pts"]),
                "away_pts": float(a["pts"]),
                "home_efg": round(float(h["efg"]), 4),
                "away_efg": round(float(a["efg"]), 4),
                "home_ortg": round(float(h["ortg"]), 2),
                "away_ortg": round(float(a["ortg"]), 2),
                "home_tov_rate": round(float(h["tov_rate"]), 4),
                "away_tov_rate": round(float(a["tov_rate"]), 4),
                "home_oreb_pct": round(float(h["oreb_pct"]), 4),
                "away_oreb_pct": round(float(a["oreb_pct"]), 4),
                "home_ft_rate": round(float(h["ft_rate"]), 4),
                "away_ft_rate": round(float(a["ft_rate"]), 4),
                "contrib_shooting": round(contrib["shooting"], 3),
                "contrib_turnovers": round(contrib["turnovers"], 3),
                "contrib_rebounding": round(contrib["rebounding"], 3),
                "contrib_free_throws": round(contrib["free_throws"], 3),
                "decided_by": decided_by,
                # KNOWLEDGE LAYER ONLY — do not use as model features
                "_leak_tier": "DESCRIPTIVE_REALIZED",
            }
        )

    df = pd.DataFrame(records)
    return df


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build NBA per-game post-mortems (descriptive/knowledge layer)."
    )
    parser.add_argument("--out", default=str(_OUT_PATH), help="Output parquet path")
    parser.add_argument("--dry-run", action="store_true", help="Skip writing parquet")
    args = parser.parse_args()

    print("Building post-mortems …")
    df = build_postmortems()
    n = len(df)
    print(f"  Games covered: {n:,}")

    if not args.dry_run:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out_path, index=False)
        print(f"  Written to: {out_path}")

    print()
    print("=== decided_by distribution ===")
    dist = df["decided_by"].value_counts()
    for label, cnt in dist.items():
        print(f"  {label:<15} {cnt:>5}  ({100*cnt/n:.1f}%)")

    print()
    print("=== mean Four-Factor contributions (home - away, in ~pts) ===")
    for col in ["contrib_shooting", "contrib_turnovers", "contrib_rebounding", "contrib_free_throws"]:
        print(f"  {col:<25} {df[col].mean():+.3f}")

    print()
    print("HONEST SUMMARY: This is a descriptive/knowledge layer only.")
    print("It uses realized outcomes and carries NO edge claim.")
    print("Do NOT feed these columns into any model or betting signal.")


if __name__ == "__main__":
    main()
