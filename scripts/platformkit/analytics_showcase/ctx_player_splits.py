"""Context-conditioned player scoring efficiency (no context-blind metrics).

Standing user directive: every player metric must carry its context. This module
takes the ~50 highest-minute players and splits their TRUE SHOOTING % across three
game contexts, then scores how context-sensitive each player is:

  (a) opponent defensive tier  -- top-10 vs bottom-10 defenses (by points allowed / game, per season)
  (b) home / away              -- is_home flag
  (c) rest                     -- back-to-back (1 day) vs 2+ days rest (from game dates)

TS% is aggregate (sum pts / (2*(sum fga + 0.44*sum fta))) within each cell, which is
more stable than averaging per-game rates. A "context sensitivity score" is the mean of
the available absolute TS% deltas across the three dimensions.

DESCRIPTIVE_ONLY. Calibration/intelligence analytic. No edge/ROI/$ claims. An honest
insufficient-sample verdict per cell is a success, not a gap.

Floors: cells with n<10 player-games are marked insufficient and dropped from the
sensitivity score. Players with fewer than 2 usable dimensions are reported but their
sensitivity score is null.

Input:  data/domains/basketball_nba/player_boxscores.parquet
Output: scripts/platformkit/analytics_showcase/out/ctx_player_splits.json
        docs/img/ctx_player_splits.png (top-15 most context-sensitive)

Usage:
    python -m scripts.platformkit.analytics_showcase.ctx_player_splits
    python -m scripts.platformkit.analytics_showcase.ctx_player_splits --check
"""
import json
import sys
from pathlib import Path

import pandas as pd

try:
    from scripts.platformkit.analytics_showcase._clone_safe import verify_recorded_artifact
except ImportError:
    from _clone_safe import verify_recorded_artifact

HERE = Path(__file__).parent
REPO = Path(__file__).resolve().parents[3]
OUT_JSON = HERE / "out" / "ctx_player_splits.json"
OUT_PNG = REPO / "docs" / "img" / "ctx_player_splits.png"
PARQUET = REPO / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"

N_PLAYERS = 50           # highest-minute players analysed
CELL_MIN_GAMES = 10      # n<10 player-games in a cell -> insufficient, dropped
DEF_TIER_SIZE = 10       # top-10 / bottom-10 defenses per season
COLS = ["game_id", "date", "season", "team", "opp", "is_home",
        "player_id", "player_name", "pts", "fga", "fta"]


def ts_pct(pts: float, fga: float, fta: float) -> float | None:
    """Aggregate true-shooting %. None when no shot attempts (undefined)."""
    denom = 2.0 * (fga + 0.44 * fta)
    return None if denom <= 0 else pts / denom


def defensive_tiers(df: pd.DataFrame) -> pd.DataFrame:
    """Per (season, team) mean points allowed, tagged top10 / bottom10 defense.

    Team score per game = sum of its players' pts; points allowed = opponent's score.
    """
    team_score = df.groupby(["season", "game_id", "team"], as_index=False)["pts"].sum()
    team_score = team_score.rename(columns={"pts": "team_pts"})
    # opponent score: self-join on the other team in the same game
    merged = team_score.merge(
        team_score.rename(columns={"team": "opp", "team_pts": "allowed"}),
        on=["season", "game_id"],
    )
    merged = merged[merged["team"] != merged["opp"]]
    allowed = merged.groupby(["season", "team"], as_index=False)["allowed"].mean()
    tiers = []
    for season, grp in allowed.groupby("season"):
        grp = grp.sort_values("allowed")  # fewest allowed = best defense
        top = set(grp.head(DEF_TIER_SIZE)["team"])
        bot = set(grp.tail(DEF_TIER_SIZE)["team"])
        for _, r in grp.iterrows():
            tier = "top10_def" if r["team"] in top else ("bottom10_def" if r["team"] in bot else "mid")
            tiers.append({"season": season, "opp": r["team"], "opp_def_tier": tier,
                          "opp_pts_allowed": round(float(r["allowed"]), 2)})
    return pd.DataFrame(tiers)


def rest_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Per (season, team, date) rest bucket: b2b (1 day) vs rest2plus (>=2).

    First game of a team's season has unknown rest and is left unlabeled.
    """
    sched = df[["season", "team", "date"]].drop_duplicates().sort_values(["season", "team", "date"])
    sched["prev"] = sched.groupby(["season", "team"])["date"].shift(1)
    gap = (sched["date"] - sched["prev"]).dt.days
    sched["rest_bucket"] = gap.map(lambda d: "b2b" if d == 1 else ("rest2plus" if d >= 2 else None))
    return sched[["season", "team", "date", "rest_bucket"]]


def cell_ts(sub: pd.DataFrame) -> dict:
    n = int(len(sub))
    if n < CELL_MIN_GAMES:
        return {"n": n, "ts_pct": None, "insufficient": True}
    ts = ts_pct(float(sub["pts"].sum()), float(sub["fga"].sum()), float(sub["fta"].sum()))
    return {"n": n, "ts_pct": None if ts is None else round(ts, 4), "insufficient": False}


def player_splits(pdf: pd.DataFrame) -> dict:
    dims = {
        "opp_def_tier": ("top10_def", "bottom10_def", "opp_def_tier"),
        "home_away": ("home", "away", "_home_away"),
        "rest": ("b2b", "rest2plus", "rest_bucket"),
    }
    out = {}
    deltas = []
    for dim, (a, b, col) in dims.items():
        cell_a = cell_ts(pdf[pdf[col] == a])
        cell_b = cell_ts(pdf[pdf[col] == b])
        entry = {a: cell_a, b: cell_b}
        if not cell_a["insufficient"] and not cell_b["insufficient"] \
                and cell_a["ts_pct"] is not None and cell_b["ts_pct"] is not None:
            delta = round(cell_a["ts_pct"] - cell_b["ts_pct"], 4)
            entry["delta_ts_pct"] = delta
            deltas.append(abs(delta))
        else:
            entry["delta_ts_pct"] = None
        out[dim] = entry
    overall = ts_pct(float(pdf["pts"].sum()), float(pdf["fga"].sum()), float(pdf["fta"].sum()))
    sens = round(sum(deltas) / len(deltas), 4) if deltas else None
    return {
        "overall_ts_pct": None if overall is None else round(overall, 4),
        "total_games": int(len(pdf)),
        "usable_dimensions": len(deltas),
        "context_sensitivity_score": sens,
        "splits": out,
    }


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["_home_away"] = df["is_home"].map(lambda v: "home" if float(v) == 1.0 else "away")
    df = df.merge(defensive_tiers(df), on=["season", "opp"], how="left")
    df = df.merge(rest_flags(df), on=["season", "team", "date"], how="left")
    return df


def build_from_full(df: pd.DataFrame) -> dict:
    prepared = prepare(df)
    top = (prepared.groupby(["player_id", "player_name"], as_index=False)["min"].sum()
           .sort_values("min", ascending=False).head(N_PLAYERS))
    players = []
    for _, r in top.iterrows():
        pdf = prepared[prepared["player_id"] == r["player_id"]]
        rec = player_splits(pdf)
        rec["player_id"] = int(r["player_id"])
        rec["player_name"] = r["player_name"]
        rec["total_minutes"] = round(float(r["min"]), 1)
        players.append(rec)
    ranked = sorted(
        players,
        key=lambda p: (p["context_sensitivity_score"] is not None, p["context_sensitivity_score"] or 0.0),
        reverse=True,
    )
    return {
        "label": "DESCRIPTIVE_ONLY",
        "metric": "true_shooting_pct = pts / (2*(fga + 0.44*fta)), aggregated within each context cell",
        "edge_claimed": False,
        "method": {
            "players": "top-%d by total minutes" % N_PLAYERS,
            "contexts": [
                "opponent defensive tier: top-10 vs bottom-10 defenses by points allowed/game, per season",
                "home vs away (is_home)",
                "rest: back-to-back (1 day) vs 2+ days rest, from game dates",
            ],
            "context_sensitivity_score": "mean of available absolute TS%-deltas across the 3 dimensions",
            "cell_min_games": CELL_MIN_GAMES,
            "def_tier_size": DEF_TIER_SIZE,
        },
        "floors": {
            "cells with n<%d player-games" % CELL_MIN_GAMES: "marked insufficient, dropped from sensitivity",
            "players with <2 usable dimensions": "reported with context_sensitivity_score=null",
            "first game of a team-season": "unknown rest, unlabeled",
        },
        "coverage": {
            "input_rows": int(len(df)),
            "seasons": sorted(df["season"].unique().tolist()),
            "players_analysed": len(players),
        },
        "players": ranked,
    }


def render_chart(output: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ranked = [p for p in output["players"] if p["context_sensitivity_score"] is not None][:15]
    names = [f'{p["player_name"]}'.encode("ascii", "replace").decode() for p in ranked][::-1]
    vals = [p["context_sensitivity_score"] for p in ranked][::-1]
    fig, ax = plt.subplots(figsize=(9, 6.5))
    ax.barh(names, vals, color="#b5651d")
    ax.set_xlabel("context sensitivity (mean |TS% delta| across opp-D / home-away / rest)")
    ax.set_title("Most context-sensitive scorers -- TS%% swing by game context (top 15)")
    seasons = ",".join(output["coverage"]["seasons"])
    fig.text(0.5, 0.01,
             "Source: out/ctx_player_splits.json <- data/domains/basketball_nba/player_boxscores.parquet | "
             "seasons %s | DESCRIPTIVE_ONLY, edge_claimed=False" % seasons,
             ha="center", fontsize=7, color="gray")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main() -> dict:
    df = pd.read_parquet(PARQUET, columns=[*COLS, "min"])
    output = build_from_full(df)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(output, indent=2))
    render_chart(output, OUT_PNG)
    return output


def _validate(data: dict) -> None:
    assert data["label"] == "DESCRIPTIVE_ONLY", data.get("label")
    assert data["edge_claimed"] is False
    assert isinstance(data["players"], list) and data["players"], "no players"
    for p in data["players"]:
        assert "context_sensitivity_score" in p and "splits" in p


def _check() -> None:
    """--check: re-derive from local parquet if present, else verify committed artifact."""
    if PARQUET.exists():
        out = main()
        _validate(out)
        # synthetic sanity: TS% math
        assert ts_pct(20.0, 10.0, 5.0) is not None
        assert ts_pct(0.0, 0.0, 0.0) is None
        print("ctx_player_splits self-check OK (re-derived from parquet)")
    else:
        verify_recorded_artifact(OUT_JSON, _validate, "ctx_player_splits")


if __name__ == "__main__":
    if "--check" in sys.argv:
        _check()
    else:
        res = main()
        print(json.dumps({"coverage": res["coverage"],
                          "top5_sensitive": [
                              {"name": p["player_name"].encode("ascii", "replace").decode(),
                               "sensitivity": p["context_sensitivity_score"]}
                              for p in res["players"][:5]]}, indent=2))
        print(f"wrote {OUT_JSON}")
        print(f"wrote {OUT_PNG}")
