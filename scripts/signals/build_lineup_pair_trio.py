"""Wave 1 builder: 2-man & 3-man combo signals (entity=lineup, edge=lineup+correlation).

Reads data/cache/intel_outcome/lineup_combos_v2.json (prior-season 2024-25 box net-rating
per pair/trio, 30 teams, real NBA Stats 5-man lineup data), the raw per-team
lineup_splits_<TRI>_2024-25.json files (for pace + 5-man on-court details), and
data/cache/pbp_possession_features.parquet (for per-player PnR role split aggregated
to season level).

Key signals produced (one row per pair OR trio, keyed by team + combo):
  net            – on-court net rating (pts/100 poss) while combo is on floor
  poss           – possessions logged together
  floor_min      – floor minutes together
  n_lineups      – number of distinct 5-man lineups the combo co-appears in
  combo_type     – 'pair' or 'trio'
  rank_in_team   – rank within team by net (1=best)
  team_net_pctile– percentile of this combo net vs league-wide combos of same type
  pnr_handler_share – (pairs only, if both players have pbp data) share of pair's
                    combined PnR ball-handler possessions that belongs to player_1
  pnr_screen_share  – same for screener/roller possessions
  avg_player_min – average season minutes_on of the pair/trio members (from on_off)
  stagger_score  – |min1 - min2| / max(min1, min2); low = overlap, high = stagger
                   (pairs only; proxy for rotation pattern from per-player on-court min)

Leak rule: season-aggregate 2024-25. No future information. Scouting / correlation-model
consumer (tiers A/B). NOT suitable for point-model feed without prior-season offset.
Consumer: scouting (C), corr-model (B).

  python scripts/signals/build_lineup_pair_trio.py
"""
from __future__ import annotations

import json
import os
from itertools import combinations

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COMBOS_V2 = os.path.join(ROOT, "data", "cache", "intel_outcome", "lineup_combos_v2.json")
LINEUP_SPLITS_DIR = os.path.join(ROOT, "data", "nba", "lineups")
PBP = os.path.join(ROOT, "data", "cache", "pbp_possession_features.parquet")
ON_OFF = os.path.join(ROOT, "data", "cache", "on_off_features.parquet")
OUT_DIR = os.path.join(ROOT, "data", "cache", "signals")
OUT = os.path.join(OUT_DIR, "lineup_pair_trio.parquet")

SEASON = "2024-25"
MIN_POSS = 150  # same threshold used in combos_v2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_player_ids_from_group_id(gid: str) -> list[str]:
    """'-203991-1629027-...-' → ['203991','1629027',...]  (zero-padded strings)."""
    return [x for x in gid.split("-") if x]


def _load_pbp_pnr_season(season: str = SEASON) -> pd.DataFrame:
    """Season-aggregate PnR ball-handler and screener possessions per player.

    PBP data spans multiple seasons; we filter to the target season by game_id
    prefix (002224xxxx = 2022-23, 002224xxxx for each season). We use game_date
    instead: 2024-25 games run 2024-10 through 2025-06.
    """
    df = pd.read_parquet(PBP)
    # filter to 2024-25 season by date range
    df["game_date"] = pd.to_datetime(df["game_date"])
    mask = (df["game_date"] >= "2024-10-01") & (df["game_date"] <= "2025-07-01")
    df = df[mask].copy()
    if df.empty:
        return pd.DataFrame(columns=["player_id", "pnr_handler_poss", "pnr_screener_poss"])
    agg = (
        df.groupby("player_id")[["pbp_pnr_ball_handler", "pbp_pnr_screener_proxy"]]
        .sum()
        .reset_index()
        .rename(columns={
            "pbp_pnr_ball_handler": "pnr_handler_poss",
            "pbp_pnr_screener_proxy": "pnr_screener_poss",
        })
    )
    return agg


def _load_on_off_minutes() -> pd.DataFrame:
    """Per-player season minutes_on for 2024-25."""
    df = pd.read_parquet(ON_OFF)
    df = df[df["season"] == SEASON][["player_id", "player_name", "minutes_on", "team_abbreviation"]].copy()
    return df


def _compute_stagger_score(min1: float, min2: float) -> float | None:
    """Stagger score for a pair: |min1-min2| / max(min1,min2). 0=full overlap, ~1=stagger."""
    denom = max(min1, min2)
    if denom <= 0:
        return None
    return round(abs(min1 - min2) / denom, 3)


def _pnr_role_split(player_ids: list[str], pnr: pd.DataFrame) -> tuple[float | None, float | None]:
    """For a pair, compute handler share and screen share of their combined PnR poss."""
    ids_int = []
    for pid in player_ids:
        try:
            ids_int.append(int(pid))
        except ValueError:
            pass
    sub = pnr[pnr["player_id"].isin(ids_int)]
    if sub.empty:
        return None, None
    total_handler = float(sub["pnr_handler_poss"].sum())
    total_screen = float(sub["pnr_screener_poss"].sum())
    if total_handler + total_screen < 1:
        return None, None
    # share = player1's handler poss / total pair handler poss
    p1 = sub[sub["player_id"] == ids_int[0]]
    if p1.empty:
        return None, None
    p1_handler = float(p1["pnr_handler_poss"].sum())
    p1_screen = float(p1["pnr_screener_poss"].sum())
    handler_share = round(p1_handler / total_handler, 3) if total_handler > 0 else None
    screen_share = round(p1_screen / total_screen, 3) if total_screen > 0 else None
    return handler_share, screen_share


def _avg_player_min(player_ids: list[str], on_off_min: dict[int, float]) -> float | None:
    vals = []
    for pid in player_ids:
        try:
            v = on_off_min.get(int(pid))
        except ValueError:
            v = None
        if v is not None:
            vals.append(v)
    return round(float(np.mean(vals)), 1) if vals else None


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build() -> pd.DataFrame:
    # Load source data
    with open(COMBOS_V2, encoding="utf-8") as f:
        combos = json.load(f)

    pnr = _load_pbp_pnr_season()
    on_off = _load_on_off_minutes()
    on_off_min: dict[int, float] = dict(zip(on_off["player_id"].astype(int), on_off["minutes_on"]))

    rows = []

    for team, team_data in combos["by_team"].items():
        # ---- PAIRS ----
        for rank_0based, entry in enumerate(team_data["best_pairs"] + team_data["worst_pairs"]):
            player_ids = [str(pid) for pid in entry["players"]]
            names = entry["names"]
            net = float(entry["net"])
            poss = int(entry["poss"])
            floor_min = float(entry["min"])
            n_lineups = int(entry["n_lineups"])

            # PnR role split (only meaningful for pairs)
            handler_share, screen_share = _pnr_role_split(player_ids, pnr)

            # stagger score from on_off minutes
            mins = []
            for pid in player_ids:
                try:
                    m = on_off_min.get(int(pid))
                except ValueError:
                    m = None
                mins.append(m)
            stagger = None
            if all(m is not None for m in mins):
                stagger = _compute_stagger_score(mins[0], mins[1])

            avg_min = _avg_player_min(player_ids, on_off_min)

            rows.append({
                "team": team,
                "season": SEASON,
                "combo_type": "pair",
                "player_ids": ",".join(player_ids),
                "player_names": " / ".join(names),
                "net": round(net, 2),
                "poss": poss,
                "floor_min": round(floor_min, 1),
                "n_lineups": n_lineups,
                "pnr_handler_share": handler_share,
                "pnr_screen_share": screen_share,
                "avg_player_min": avg_min,
                "stagger_score": stagger,
            })

        # ---- TRIOS ----
        for entry in team_data["best_trios"] + team_data["worst_trios"]:
            player_ids = [str(pid) for pid in entry["players"]]
            names = entry["names"]
            net = float(entry["net"])
            poss = int(entry["poss"])
            floor_min = float(entry["min"])
            n_lineups = int(entry["n_lineups"])
            avg_min = _avg_player_min(player_ids, on_off_min)

            rows.append({
                "team": team,
                "season": SEASON,
                "combo_type": "trio",
                "player_ids": ",".join(player_ids),
                "player_names": " / ".join(names),
                "net": round(net, 2),
                "poss": poss,
                "floor_min": round(floor_min, 1),
                "n_lineups": n_lineups,
                "pnr_handler_share": None,
                "pnr_screen_share": None,
                "avg_player_min": avg_min,
                "stagger_score": None,
            })

    out = pd.DataFrame(rows)

    # Deduplicate: best+worst lists may overlap on the same pair (same entity on both lists
    # for different teams is impossible, but duplicate entries within a team can occur if
    # a pair is both a "best" and "worst" due to small-sample overlap).
    out = out.drop_duplicates(subset=["team", "combo_type", "player_ids"])

    # Rank within team by net (1=highest, i.e. best)
    out["rank_in_team"] = (
        out.groupby(["team", "combo_type"])["net"]
        .rank(method="min", ascending=False)
        .astype(int)
    )

    # League-wide net percentile by combo_type (100=best net)
    out["team_net_pctile"] = (
        out.groupby("combo_type")["net"]
        .rank(pct=True, ascending=True)
        .mul(100)
        .round(0)
        .astype(int)
    )

    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    out = build()
    out.to_parquet(OUT, index=False)

    n_pairs = (out.combo_type == "pair").sum()
    n_trios = (out.combo_type == "trio").sum()
    n_teams = out.team.nunique()
    print(f"DONE: lineup_pair_trio signals -> {OUT}")
    print(f"  rows={len(out)}  pairs={n_pairs}  trios={n_trios}  teams={n_teams}  season={SEASON}")
    print()

    # 3 sample rows
    print("SAMPLE ROWS (3):")
    print(out.head(3).to_string(index=False))
    print()

    # Sanity: top 10 pairs by net rating league-wide
    print("TOP 10 LEAGUE PAIRS by net (>=150 poss):")
    top = out[(out.combo_type == "pair") & (out.poss >= MIN_POSS)].nlargest(10, "net")
    for r in top.itertuples(index=False):
        stag = f"  stagger={r.stagger_score}" if r.stagger_score is not None else ""
        handler = f"  handler_share={r.pnr_handler_share}" if r.pnr_handler_share is not None else ""
        print(f"  {r.team:3s}  {r.player_names:<45s}  net={r.net:+.1f}  poss={r.poss}{stag}{handler}")

    print()
    print("TOP 10 LEAGUE TRIOS by net (>=150 poss):")
    top3 = out[(out.combo_type == "trio") & (out.poss >= MIN_POSS)].nlargest(10, "net")
    for r in top3.itertuples(index=False):
        print(f"  {r.team:3s}  {r.player_names:<60s}  net={r.net:+.1f}  poss={r.poss}")


if __name__ == "__main__":
    main()
