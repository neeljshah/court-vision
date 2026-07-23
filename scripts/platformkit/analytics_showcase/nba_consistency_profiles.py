"""NBA player consistency profiles: game-to-game dispersion of per-36 box
production (points / rebounds / assists), stabilized for small samples.

DESCRIPTIVE_ONLY (truth source: docs/JOB_EVIDENCE_PACKET.md) -- no edge / ROI /
$ / profit claim. This is a descriptive measure of how much a player's realized
box line bounces from game to game, NOT a skill, value, or predictive metric.

Consistency measure
--------------------
For each qualifying game (>= MIN_GAME_MINUTES played) we take the per-36 rate
stat36 = stat * 36 / minutes. Per player, per stat, the raw dispersion is the
coefficient of variation CV = sample_std(stat36) / mean(stat36) (scale-free, so
comparable across players of different output level). Lower CV = steadier.

Small-sample shrinkage
----------------------
A player's own CV is noisy with few games, so each CV is shrunk toward the
league-mean CV (empirical-Bayes / regression-to-the-mean):

    cv_shrunk = w * cv_raw + (1 - w) * league_mean_cv,   w = n / (n + SHRINK_K)

At n = SHRINK_K games the player's own CV and the league prior are weighted
equally; as n grows w -> 1 (trust the player). SHRINK_K is declared ONCE below
and is not re-tuned to move any name up or down. The league-mean prior is built
only from players above the games floor.

Declared floors (set once, not tuned per result)
-------------------------------------------------
- MIN_GAME_MINUTES = 10.0 : games under this are dropped from the per-36 series
  (a 3-minute, 4-point cameo is 48/36 and would dominate the variance).
- MIN_QUAL_GAMES   = 15    : players under this are excluded from the ranked
  most/least lists, the distribution, and the league-mean prior.
- SHRINK_K         = 20    : shrinkage strength in games.

NOT this
--------
- NOT a skill / value metric (a low-volume role player can be very "consistent"
  at low output; consistency != quality).
- NOT opponent / rest / role / home-away adjusted -- raw realized dispersion.
- NOT predictive -- describes past games, does not forecast future variance.
- CV inflates mechanically for low-mean stats, so reb/ast CVs are not on the
  same scale as pts CV across archetypes; the composite averages the three by
  declared choice, not because they are comparable units.

Input:  data/domains/basketball_nba/player_boxscores.parquet (columns-only read)
Output: out/nba_consistency_profiles.json (most/least consistent + distribution)
        docs/img/nba_consistency_profiles.png (consistency-vs-volume scatter)

Usage:
    python -m scripts.platformkit.analytics_showcase.nba_consistency_profiles
    python -m scripts.platformkit.analytics_showcase.nba_consistency_profiles --check
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    from scripts.platformkit.analytics_showcase.atlas_factory import REPO_ROOT, OUT_DIR
except ImportError:
    from atlas_factory import REPO_ROOT, OUT_DIR

OUT_JSON = OUT_DIR / "nba_consistency_profiles.json"
OUT_PNG = REPO_ROOT / "docs" / "img" / "nba_consistency_profiles.png"
PARQUET = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
SOURCE_ARTIFACT = "data/domains/basketball_nba/player_boxscores.parquet"

STATS = ["pts", "reb", "ast"]
COLS = ["player_id", "player_name", "season", "date", "min", *STATS]

MIN_GAME_MINUTES = 10.0   # declared once; kills garbage-time per-36 spikes
MIN_QUAL_GAMES = 15       # declared once; ranked-list + prior floor
SHRINK_K = 20.0           # declared once; empirical-Bayes shrinkage strength (games)


def compute_consistency(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Per-player shrunk CV of per-36 pts/reb/ast. Pure -- no file/parquet I/O.

    Returns (per_player_frame, league_mean_cv_by_stat). The frame carries every
    player with a qualifying-minutes game; callers apply the games floor for
    ranking. league_mean_cv is the prior, built only from players >= MIN_QUAL_GAMES.
    """
    d = df[df["min"] >= MIN_GAME_MINUTES].copy()
    for s in STATS:
        d[f"{s}36"] = d[s] * 36.0 / d["min"]

    rec = d.groupby("player_id").agg(
        player_name=("player_name", "last"),
        games=("min", "count"),  # min has no NaN post-filter, so count == group size
        **{f"{s}_mean": (f"{s}36", "mean") for s in STATS},
        **{f"{s}_std": (f"{s}36", "std") for s in STATS},   # ddof=1 (sample std)
    ).reset_index()

    for s in STATS:
        rec[f"{s}_cv_raw"] = rec[f"{s}_std"] / rec[f"{s}_mean"].where(rec[f"{s}_mean"] > 0)

    qual = rec[rec["games"] >= MIN_QUAL_GAMES]
    league_mean_cv = {s: float(qual[f"{s}_cv_raw"].mean()) for s in STATS}

    w = rec["games"] / (rec["games"] + SHRINK_K)
    rec["shrink_weight"] = w
    for s in STATS:
        rec[f"{s}_cv_shrunk"] = w * rec[f"{s}_cv_raw"] + (1.0 - w) * league_mean_cv[s]
    rec["composite_cv_shrunk"] = rec[[f"{s}_cv_shrunk" for s in STATS]].mean(axis=1)
    return rec, league_mean_cv


def _player_row(r: pd.Series) -> dict:
    d = {
        "player_name": r["player_name"],
        "player_id": int(r["player_id"]),
        "games": int(r["games"]),
        "shrink_weight": round(float(r["shrink_weight"]), 3),
        "composite_cv_shrunk": round(float(r["composite_cv_shrunk"]), 4),
        "pts_per36_mean": round(float(r["pts_mean"]), 2),
    }
    for s in STATS:
        d[f"{s}_cv_shrunk"] = round(float(r[f"{s}_cv_shrunk"]), 4)
    return d


def build_output(rec: pd.DataFrame, league_mean_cv: dict, df: pd.DataFrame, as_of: str) -> dict:
    ranked = rec[rec["games"] >= MIN_QUAL_GAMES].dropna(subset=["composite_cv_shrunk"])
    ranked = ranked.sort_values("composite_cv_shrunk")
    comp = ranked["composite_cv_shrunk"].to_numpy()
    return {
        "label": "DESCRIPTIVE_ONLY",
        "source": "docs/JOB_EVIDENCE_PACKET.md (truth source); input " + SOURCE_ARTIFACT,
        "as_of": as_of,
        "methodology": {
            "measure": "coefficient of variation (sample std / mean, ddof=1) of per-36 "
                       "pts/reb/ast across a player's qualifying games; lower = steadier",
            "stats": STATS,
            "per36": "stat * 36 / minutes, per game",
            "shrinkage": "cv_shrunk = w*cv_raw + (1-w)*league_mean_cv, w = games/(games+shrink_k)",
            "shrink_k_games": SHRINK_K,
            "shrink_k_tuned_to_output": False,
            "min_game_minutes_floor": MIN_GAME_MINUTES,
            "min_qualifying_games_floor": MIN_QUAL_GAMES,
            "league_mean_cv_raw": {s: round(league_mean_cv[s], 4) for s in STATS},
            "composite": "unweighted mean of the three shrunk per-stat CVs (declared choice)",
            "caveat": "CV inflates mechanically for low-mean stats; reb/ast CVs are not on the "
                      "same scale as pts CV across archetypes. Consistency is not skill/value.",
            "seasons_pooled": sorted(df["season"].unique().tolist()),
        },
        "not_this": [
            "NOT a skill/value metric -- a low-volume role player can be very consistent at low output",
            "NOT opponent/rest/role/home-away adjusted -- raw game-to-game dispersion only",
            "NOT predictive -- describes past games, does not forecast future variance",
        ],
        "input_coverage": {
            "rows": int(len(df)),
            "unique_players": int(df["player_id"].nunique()),
            "seasons": sorted(df["season"].unique().tolist()),
            "players_meeting_floor": int(len(ranked)),
        },
        "composite_cv_distribution": {
            "n": int(comp.size),
            "min": round(float(np.min(comp)), 4),
            "p25": round(float(np.percentile(comp, 25)), 4),
            "median": round(float(np.median(comp)), 4),
            "p75": round(float(np.percentile(comp, 75)), 4),
            "max": round(float(np.max(comp)), 4),
            "mean": round(float(np.mean(comp)), 4),
        },
        "most_consistent_top15": [_player_row(r) for _, r in ranked.head(15).iterrows()],
        "least_consistent_top15": [_player_row(r) for _, r in ranked.tail(15).iloc[::-1].iterrows()],
    }


def render_chart(rec: pd.DataFrame, as_of: str, path: Path) -> None:
    ranked = rec[rec["games"] >= MIN_QUAL_GAMES].dropna(subset=["pts_cv_shrunk", "pts_mean"])
    x = ranked["pts_mean"].to_numpy()
    y = ranked["pts_cv_shrunk"].to_numpy()
    sizes = np.clip(ranked["games"].to_numpy(), 15, 200) * 0.9

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.scatter(x, y, s=sizes, alpha=0.45, color="#2a6fd9", edgecolor="none")
    ax.set_xlabel("mean points per 36 (scoring volume)")
    ax.set_ylabel("shrunk CV of points per 36 (higher = more volatile)")
    ax.set_title("NBA scoring consistency vs volume (DESCRIPTIVE_ONLY)")

    # annotate the 3 steadiest and 3 streakiest scorers by pts CV, for orientation
    by_pts = ranked.sort_values("pts_cv_shrunk")
    for _, r in pd.concat([by_pts.head(3), by_pts.tail(3)]).iterrows():
        ax.annotate(str(r["player_name"]).encode("ascii", "replace").decode(),
                    (r["pts_mean"], r["pts_cv_shrunk"]), fontsize=6,
                    xytext=(3, 3), textcoords="offset points")

    footer = (f"source: {SOURCE_ARTIFACT}  |  floor: games>={MIN_QUAL_GAMES}, "
              f"min>={MIN_GAME_MINUTES}/g, shrink_k={SHRINK_K}  |  as_of: {as_of}")
    fig.text(0.01, 0.01, footer, fontsize=6, ha="left", color="#555555")
    fig.text(0.99, 0.01, "DESCRIPTIVE_ONLY", fontsize=6, ha="right",
             color="#b33333", fontweight="bold")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main() -> dict:
    df = pd.read_parquet(PARQUET, columns=COLS)
    as_of = str(pd.to_datetime(df["date"]).max().date())
    rec, league_mean_cv = compute_consistency(df)
    output = build_output(rec, league_mean_cv, df, as_of)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(output, indent=2), encoding="ascii")
    render_chart(rec, as_of, OUT_PNG)
    return output


def _check():
    # 1) synthetic logic self-check (no parquet/file I/O): a steady player must
    #    rank lower-CV than a volatile one, and shrink_weight must land in (0,1).
    steady = pd.DataFrame({
        "player_id": 1, "player_name": "Steady",
        "min": 32.0, "pts": 20.0, "reb": 8.0, "ast": 5.0,
    }, index=range(40))
    volatile = pd.DataFrame({
        "player_id": 2, "player_name": "Volatile", "min": 32.0,
        "pts": np.r_[np.full(20, 4.0), np.full(20, 36.0)], "reb": 8.0, "ast": 5.0,
    })
    rec, lm = compute_consistency(pd.concat([steady, volatile], ignore_index=True))
    by_id = rec.set_index("player_id")
    assert by_id.loc[1, "pts_cv_shrunk"] < by_id.loc[2, "pts_cv_shrunk"], "steady must be lower-CV"
    assert all(lm[s] >= 0 for s in STATS), "league mean CV must be non-negative"
    assert 0 < float(by_id.loc[1, "shrink_weight"]) < 1, "shrink weight must be in (0,1)"

    # 2) real outputs exist and are nonzero (built by a prior main() run)
    assert OUT_JSON.exists() and OUT_JSON.stat().st_size > 0, f"missing/empty {OUT_JSON} -- run without --check first"
    assert OUT_PNG.exists() and OUT_PNG.stat().st_size > 0, f"missing/empty {OUT_PNG} -- run without --check first"
    data = json.loads(OUT_JSON.read_text(encoding="ascii"))
    assert data["label"] == "DESCRIPTIVE_ONLY"
    assert data["composite_cv_distribution"]["n"] > 0, "no qualifying players in distribution"
    assert data["most_consistent_top15"] and data["least_consistent_top15"], "empty ranked lists"
    print(f"check ok: {data['composite_cv_distribution']['n']} qualifying players, json+png present")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        result = main()
        print(json.dumps(result["composite_cv_distribution"], indent=2))
        def _names(key):
            return [r["player_name"].encode("ascii", "replace").decode() for r in result[key][:3]]
        print("most consistent:", _names("most_consistent_top15"))
        print("least consistent:", _names("least_consistent_top15"))
        print(f"wrote {OUT_JSON}")
        print(f"wrote {OUT_PNG}")
