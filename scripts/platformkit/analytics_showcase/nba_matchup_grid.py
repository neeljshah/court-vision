"""nba_matchup_grid.py -- team-vs-team scoring grid from NBA box scores.

DESCRIPTIVE_ONLY (see docs/JOB_EVIDENCE_PACKET.md). NO edge/ROI/$/forecast
claim: every number here describes games ALREADY PLAYED, pooled across the
seasons present in the box-score parquet (currently 3). A historical mean
margin is not a prediction of any future meeting.

What it builds, from the player box-score parquet:
  - team-game points = sum of a team's players' `pts` within one game_id
  - ONLY game_ids with EXACTLY 2 distinct teams are used (drops all-star /
    malformed rows); the dropped count is reported in the JSON
  - for each ordered team pairing (row, col), pooled over all their meetings:
      mean_total  = mean(row_pts + col_pts)   -- symmetric: (A,B) == (B,A)
      mean_margin = mean(row_pts - col_pts)    -- anti-symmetric: (A,B) == -(B,A)
  - MASK (declared, NOT tuned to output): a pairing is reported/plotted only
    where n_meetings >= MIN_MEETINGS (=2). This is a small-sample floor, not a
    selection for predictiveness.

Home/away is absent from this per-player table, so `mean_margin` pools home and
away meetings together -- it is NOT a home-court split, and it is opponent-raw
(no strength-of-schedule adjustment).

Input:  data/domains/basketball_nba/player_boxscores.parquet
        (columns-only read: game_id, team, season, date, pts)
Output: out/nba_matchup_grid.json     (both grids as a pairing list + methodology)
        docs/img/nba_matchup_grid.png  (ONE margin heatmap, diverging, masked)

Usage:
    python -m scripts.platformkit.analytics_showcase.nba_matchup_grid
    python -m scripts.platformkit.analytics_showcase.nba_matchup_grid --check
"""
import json

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:  # package-run (check_all uses -m) vs bare-script both resolve
    from scripts.platformkit.analytics_showcase.atlas_factory import REPO_ROOT, OUT_DIR
except ImportError:
    from atlas_factory import REPO_ROOT, OUT_DIR

SOURCE_ARTIFACT = "data/domains/basketball_nba/player_boxscores.parquet"
PARQUET = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
OUT_JSON = OUT_DIR / "nba_matchup_grid.json"
OUT_PNG = REPO_ROOT / "docs" / "img" / "nba_matchup_grid.png"

COLS = ["game_id", "team", "season", "date", "pts"]
MIN_MEETINGS = 2  # small-sample floor; declared once, never tuned to output


def build_grid(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Player box rows -> ordered team-pairing grid (BEFORE the mask).

    Returns (grid_df, coverage). grid_df has one row per ordered
    (team_r, team_c) pairing with n / mean_total / mean_margin.
    """
    tg = df.groupby(["game_id", "team"], as_index=False).agg(pts=("pts", "sum"))

    # keep only game_ids that resolve to exactly 2 teams (drop all-star/malformed)
    n_teams_in_game = tg.groupby("game_id")["team"].transform("nunique")
    kept = tg[n_teams_in_game == 2][["game_id", "team", "pts"]]

    games_total = int(tg["game_id"].nunique())
    games_two = int(kept["game_id"].nunique())

    # self-join on game_id -> two ordered rows per meeting: (A,B) and (B,A)
    m = kept.merge(kept, on="game_id", suffixes=("_r", "_c"))
    m = m[m["team_r"] != m["team_c"]]
    m["total"] = m["pts_r"] + m["pts_c"]
    m["margin"] = m["pts_r"] - m["pts_c"]

    grid = m.groupby(["team_r", "team_c"], as_index=False).agg(
        n=("game_id", "nunique"),  # nunique guards against any dup game rows
        mean_total=("total", "mean"),
        mean_margin=("margin", "mean"),
    )

    coverage = {
        "rows": int(len(df)),
        "games_total": games_total,
        "games_two_team": games_two,
        "games_dropped_not_two_team": games_total - games_two,
        "teams": sorted(kept["team"].unique().tolist()),
        "seasons": sorted(df["season"].unique().tolist()),
        "date_max": str(df["date"].max().date()) if len(df) else None,
    }
    return grid, coverage


def build_output(grid: pd.DataFrame, coverage: dict) -> dict:
    masked = grid[grid["n"] >= MIN_MEETINGS].copy()
    pairings = [
        {
            "row": r["team_r"],
            "col": r["team_c"],
            "n_meetings": int(r["n"]),
            "mean_total": round(float(r["mean_total"]), 2),
            "mean_margin": round(float(r["mean_margin"]), 2),
        }
        for _, r in masked.sort_values(["team_r", "team_c"]).iterrows()
    ]
    hi_t = max(pairings, key=lambda p: p["mean_total"]) if pairings else None
    lo_t = min(pairings, key=lambda p: p["mean_total"]) if pairings else None

    return {
        "label": "DESCRIPTIVE_ONLY",
        "source": f"{SOURCE_ARTIFACT} + docs/JOB_EVIDENCE_PACKET.md",
        "methodology": {
            "unit": "team-game points = sum of a team's players' pts within one game_id",
            "game_filter": "only game_ids with exactly 2 distinct teams",
            "mean_total": "mean(row_pts + col_pts) over the pairing's meetings (symmetric)",
            "mean_margin": "mean(row_pts - col_pts) over the pairing's meetings "
                           "(anti-symmetric; pools home+away, NOT a home-court split)",
            "seasons_pooled": coverage["seasons"],
            "not_a_forecast": True,
            "not_this": [
                "NOT a prediction of any future matchup (describes games already played)",
                "NOT a home/away split (per-player table carries no venue flag)",
                "NOT opponent-adjusted / strength-of-schedule (raw pooled means only)",
            ],
        },
        "mask": {
            "min_meetings": MIN_MEETINGS,
            "rule": f"pairing reported only where n_meetings >= {MIN_MEETINGS}",
            "pairings_before_mask": int(len(grid)),
            "pairings_kept": int(len(masked)),
            "pairings_masked_out": int(len(grid) - len(masked)),
        },
        "input_coverage": coverage,
        "extremes_descriptive": {
            "highest_scoring_pairing": hi_t,
            "lowest_scoring_pairing": lo_t,
        },
        "pairings": pairings,
    }


def render_heatmap(pairings: list, teams: list, path) -> None:
    """ONE diverging heatmap of mean margin (row minus col). Masked cells and
    the (no-self-matchup) diagonal render neutral gray."""
    idx = {t: i for i, t in enumerate(teams)}
    mat = np.full((len(teams), len(teams)), np.nan)
    for p in pairings:
        mat[idx[p["row"]], idx[p["col"]]] = p["mean_margin"]
    finite = np.isfinite(mat)
    vmax = float(np.nanmax(np.abs(mat))) if finite.any() else 1.0

    cmap = plt.cm.RdBu_r.copy()
    cmap.set_bad("#dddddd")  # NaN = masked / diagonal -> neutral gray

    fig, ax = plt.subplots(figsize=(11, 9.6))
    im = ax.imshow(np.ma.masked_invalid(mat), cmap=cmap, vmin=-vmax, vmax=vmax, aspect="equal")
    ax.set_xticks(range(len(teams)))
    ax.set_xticklabels(teams, rotation=90, fontsize=6)
    ax.set_yticks(range(len(teams)))
    ax.set_yticklabels(teams, fontsize=6)
    ax.set_xlabel("column team (opponent)")
    ax.set_ylabel("row team")
    ax.set_title(
        "NBA team-vs-team mean point margin (row minus column), pooled seasons\n"
        "DESCRIPTIVE_ONLY -- games already played, not a forecast; "
        "red = row outscored column"
    )
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label(f"mean margin: row_pts - col_pts (gray = n_meetings < {MIN_MEETINGS} or self)")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main() -> dict:
    df = pd.read_parquet(PARQUET, columns=COLS)
    grid, coverage = build_grid(df)
    output = build_output(grid, coverage)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(output, indent=2), encoding="ascii")
    render_heatmap(output["pairings"], coverage["teams"], OUT_PNG)
    return output


def _check() -> None:
    # (1) logic self-check on a synthetic frame -- no parquet read.
    # g1: A20 B16 (+4) ; g2: A24 B40 (-16) ; g3 is a 3-team row that MUST drop.
    fake = pd.DataFrame({
        "game_id": [1, 1, 2, 2, 3, 3, 3],
        "team":    ["A", "B", "A", "B", "A", "B", "C"],
        "season":  ["2023-24"] * 7,
        "date":    pd.to_datetime(["2023-11-01", "2023-11-01", "2023-12-01",
                                   "2023-12-01", "2024-01-01", "2024-01-01", "2024-01-01"]),
        "pts":     [20, 16, 24, 40, 99, 99, 99],
    })
    grid, cov = build_grid(fake)
    ab = grid[(grid["team_r"] == "A") & (grid["team_c"] == "B")].iloc[0]
    ba = grid[(grid["team_r"] == "B") & (grid["team_c"] == "A")].iloc[0]
    assert int(ab["n"]) == 2 and int(ba["n"]) == 2, "3-team game 3 should not add A-B meetings"
    assert abs(ab["mean_total"] - 50.0) < 1e-9        # (36 + 64) / 2
    assert abs(ba["mean_total"] - 50.0) < 1e-9        # total is symmetric
    assert abs(ab["mean_margin"] - (-6.0)) < 1e-9     # (+4 - 16) / 2
    assert abs(ba["mean_margin"] - 6.0) < 1e-9        # margin is anti-symmetric
    assert cov["games_two_team"] == 2 and cov["games_dropped_not_two_team"] == 1
    out = build_output(grid, cov)
    assert out["label"] == "DESCRIPTIVE_ONLY" and out["mask"]["pairings_kept"] == 2
    print("logic check ok")

    # (2) built outputs must exist and be nonzero (hard-assert, like nba_team_atlas).
    assert OUT_JSON.exists(), (
        f"{OUT_JSON} missing -- run "
        f"`python -m scripts.platformkit.analytics_showcase.nba_matchup_grid` first"
    )
    obj = json.loads(OUT_JSON.read_text(encoding="ascii"))
    assert obj["mask"]["pairings_kept"] > 0, "no pairings survived the mask"
    assert len(obj["pairings"]) == obj["mask"]["pairings_kept"]
    assert OUT_PNG.exists() and OUT_PNG.stat().st_size > 0, f"heatmap missing/empty: {OUT_PNG}"
    print(f"check ok: {obj['mask']['pairings_kept']} pairings kept, png {OUT_PNG.stat().st_size}B")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        result = main()
        print(json.dumps({
            "pairings_kept": result["mask"]["pairings_kept"],
            "pairings_masked_out": result["mask"]["pairings_masked_out"],
            "games_two_team": result["input_coverage"]["games_two_team"],
            "games_dropped_not_two_team": result["input_coverage"]["games_dropped_not_two_team"],
            "seasons": result["input_coverage"]["seasons"],
        }, indent=2))
        print(f"wrote {OUT_JSON}")
        print(f"wrote {OUT_PNG}")
