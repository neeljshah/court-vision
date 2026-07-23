"""NBA player form curves: per-player 10-game rolling per-36 box-composite,
league percentile context bands, and the biggest net risers/fallers.

DESCRIPTIVE_ONLY (see docs/JOB_EVIDENCE_PACKET.md) -- no edge/ROI/$ claims.
The "form" number is a 10-game, minute-weighted, per-36 rolling value of the
frozen Win-Score-style box composite reused VERBATIM from box_value_index.py
(WEIGHTS_PER36 -- Berri 2006 convention). It is NOT BPM/EPM/RAPM and NOT a
live "hot/cold" or predictive signal. The "mover" delta is simply the net
change between a player's FIRST and LAST retained 10-game window over the
observed span -- a trajectory description, computed once, never tuned, and
the two windows may abut when early low-minute windows are dropped (labeled,
not claimed disjoint). Percentile bands are pooled over EVERY retained
10-game window (player-game weighted), i.e. the league distribution of
observed form states. Accented-name player_id fragmentation is a known
upstream data issue (see box_value_index.py), carried through, not fixed here.

Declared floors (declared once, never tuned to any result):
  - per-game minutes: a game enters a window only if min >= MIN_PER_GAME_MINUTES
  - window minutes:   a full 10-game window is kept only if total min >= MIN_WINDOW_MINUTES
  - mover eligibility: a player needs >= 2*WINDOW qualifying games

Input:  data/domains/basketball_nba/player_boxscores.parquet (columns-only read)
Output: out/nba_form_curves.json  (bands + top/bottom movers + methodology)
        docs/img/nba_form_curves.png  (ONE league-level movers chart)

Usage:
    python -m scripts.platformkit.analytics_showcase.nba_form_curves
    python -m scripts.platformkit.analytics_showcase.nba_form_curves --check
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
    from scripts.platformkit.analytics_showcase.box_value_index import WEIGHTS_PER36
except ImportError:  # bare-script run from the showcase dir
    from atlas_factory import REPO_ROOT, OUT_DIR
    from box_value_index import WEIGHTS_PER36

SOURCE_ARTIFACT = "data/domains/basketball_nba/player_boxscores.parquet"
PARQUET = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
OUT_JSON = OUT_DIR / "nba_form_curves.json"
OUT_PNG = REPO_ROOT / "docs" / "img" / "nba_form_curves.png"

WINDOW = 10                    # games per rolling form window
MIN_PER_GAME_MINUTES = 8.0     # a game enters a window only at/above this
MIN_WINDOW_MINUTES = 120.0     # a full window is kept only at/above this total
TABLE_N = 15                   # risers/fallers reported in JSON per side
CHART_N = 10                   # risers/fallers drawn on the chart per side

BOX_STATS = list(WEIGHTS_PER36)  # frozen composite ingredients, reused verbatim
COLS = ["player_id", "player_name", "season", "date", "min", *BOX_STATS]
FLOOR_LABEL = (f"min>={MIN_PER_GAME_MINUTES:g}/game, window_total_min>={MIN_WINDOW_MINUTES:g}, "
               f">={2 * WINDOW} qualifying games")


def rolling_form(df: pd.DataFrame) -> pd.DataFrame:
    """One row per RETAINED 10-game window with its minute-weighted per-36
    composite ('form'), in (player_id, date) order. Frozen weights, no tuning."""
    q = df[df["min"] >= MIN_PER_GAME_MINUTES].sort_values(["player_id", "date"]).copy()
    for c in BOX_STATS:
        q[c] = q[c].fillna(0.0)  # a played game shouldn't carry NaN counts; guard the per-36 divide anyway
    rolled = (q.groupby("player_id", sort=False)[["min", *BOX_STATS]]
                .rolling(WINDOW, min_periods=WINDOW).sum())
    rolled.index = rolled.index.droplevel(0)  # (player_id, orig_idx) -> orig_idx, realign to q
    roll_min = rolled["min"]
    # leading rows have roll_min = NaN -> form NaN -> dropped by the filter below (no divide error)
    q["roll_min"] = roll_min
    q["form"] = sum(w * rolled[stat] * 36.0 / roll_min for stat, w in WEIGHTS_PER36.items())
    return q[(q["roll_min"] >= MIN_WINDOW_MINUTES) & q["form"].notna()].copy()


def build_movers(valid: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """First-vs-last retained-window net change per eligible player."""
    qual = df[df["min"] >= MIN_PER_GAME_MINUTES]
    n_qual = qual.groupby("player_id").size()
    qual_min = qual.groupby("player_id")["min"].sum()
    name_map = qual.sort_values("date").groupby("player_id")["player_name"].last()

    v = valid.sort_values(["player_id", "date"])
    first = v.groupby("player_id").first()
    last = v.groupby("player_id").last()
    idx = first.index

    m = pd.DataFrame({
        "player_name": name_map.reindex(idx).values,
        "n_qual_games": n_qual.reindex(idx).values,
        "qual_minutes": qual_min.reindex(idx).values,
        "first_form": first["form"].values,
        "last_form": last["form"].values,
        "first_date": first["date"].values,
        "last_date": last["date"].values,
    }, index=idx)
    m = m[m["n_qual_games"] >= 2 * WINDOW].copy()
    m["delta"] = m["last_form"] - m["first_form"]
    return m


def _pctile(pooled_sorted: np.ndarray, x: float) -> float:
    """Percentile of x within an ascending pooled array (share strictly below)."""
    return float(np.searchsorted(pooled_sorted, x) / len(pooled_sorted) * 100.0)


def _row(r: pd.Series, pooled_sorted: np.ndarray) -> dict:
    return {
        "player_name": str(r["player_name"]),
        "delta": round(float(r["delta"]), 3),
        "first_form": round(float(r["first_form"]), 3),
        "last_form": round(float(r["last_form"]), 3),
        "last_form_league_pctile": round(_pctile(pooled_sorted, r["last_form"]), 1),
        "n_qual_games": int(r["n_qual_games"]),
        "qual_minutes": round(float(r["qual_minutes"]), 1),
        "first_date": pd.Timestamp(r["first_date"]).strftime("%Y-%m-%d"),
        "last_date": pd.Timestamp(r["last_date"]).strftime("%Y-%m-%d"),
    }


def build_output(valid: pd.DataFrame, movers: pd.DataFrame, df: pd.DataFrame) -> dict:
    pooled = np.sort(valid["form"].to_numpy())
    bands = np.percentile(pooled, [10, 25, 50, 75, 90])
    seasons = sorted(df["season"].unique().tolist())
    risers = movers.sort_values("delta", ascending=False).head(TABLE_N)
    fallers = movers.sort_values("delta", ascending=True).head(TABLE_N)
    return {
        "label": "DESCRIPTIVE_ONLY",
        "source": SOURCE_ARTIFACT + " + docs/JOB_EVIDENCE_PACKET.md",
        "methodology": {
            "form_metric": "10-game minute-weighted per-36 rolling value of the frozen "
                           "Win-Score-style box composite (WEIGHTS_PER36, reused verbatim "
                           "from box_value_index.py; Berri 2006 convention).",
            "window_games": WINDOW,
            "weights_per36": WEIGHTS_PER36,
            "weights_frozen": True,
            "weights_tuned_to_output": False,
            "normalization": "per-36 minutes, minute-weighted over the window (sum stats / sum min)",
            "mover_delta": "last retained window form minus first retained window form over the "
                           "observed span (trajectory; windows may abut, not claimed disjoint).",
            "bands_basis": "pooled over every retained 10-game window (player-game weighted)",
            "floors": FLOOR_LABEL,
            "seasons_pooled": seasons,
        },
        "not_this": [
            "NOT a live hot/cold streak or predictive signal (net-change over the whole span)",
            "NOT BPM/EPM/RAPM/DARKO (box-composite only, same limits as box_value_index.py)",
            "NOT age/opponent/role adjusted (raw box rates only)",
            "NOT player_id-deduped (accented names split across ids upstream -- carried through)",
        ],
        "input_coverage": {
            "rows": int(len(df)),
            "unique_players": int(df["player_id"].nunique()),
            "seasons": seasons,
            "players_with_retained_window": int(valid["player_id"].nunique()),
            "movers_eligible": int(len(movers)),
            "pooled_windows": int(len(valid)),
        },
        "league_percentile_bands": {
            "metric": "10-game rolling per-36 box composite",
            "p10": round(float(bands[0]), 3),
            "p25": round(float(bands[1]), 3),
            "p50": round(float(bands[2]), 3),
            "p75": round(float(bands[3]), 3),
            "p90": round(float(bands[4]), 3),
        },
        "top_movers_risers": [_row(r, pooled) for _, r in risers.iterrows()],
        "top_movers_fallers": [_row(r, pooled) for _, r in fallers.iterrows()],
    }


def render_chart(output: dict, path: Path) -> None:
    risers = output["top_movers_risers"][:CHART_N]
    fallers = output["top_movers_fallers"][:CHART_N]
    combo = sorted(risers + fallers, key=lambda r: r["delta"])
    names = [r["player_name"] for r in combo]
    vals = [r["delta"] for r in combo]
    colors = ["#c0392b" if v < 0 else "#27ae60" for v in vals]
    n_seasons = len(output["methodology"]["seasons_pooled"])

    fig, ax = plt.subplots(figsize=(9, 8))
    ax.barh(names, vals, color=colors)
    ax.axvline(0, color="#333333", lw=0.8)
    ax.set_xlabel("net change in 10-game rolling per-36 box composite\n"
                  "(DESCRIPTIVE_ONLY -- not BPM/EPM/RAPM, not a hot/cold or predictive claim)")
    ax.set_title(f"NBA form movers: biggest net risers/fallers over {n_seasons} seasons\n"
                 f"(first vs last retained {WINDOW}-game window)")
    fig.text(0.01, 0.01, f"source: {SOURCE_ARTIFACT}  |  floor: {FLOOR_LABEL}",
             fontsize=6, ha="left", va="bottom", color="#555555")
    fig.text(0.99, 0.01, "DESCRIPTIVE_ONLY", fontsize=7, ha="right", va="bottom",
             color="#b33333", fontweight="bold")
    fig.tight_layout(rect=(0.0, 0.03, 1.0, 1.0))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main() -> dict:
    df = pd.read_parquet(PARQUET, columns=COLS)
    valid = rolling_form(df)
    movers = build_movers(valid, df)
    assert len(movers), "no players cleared the mover-eligibility floor -- check the input parquet"
    output = build_output(valid, movers, df)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(output, indent=2), encoding="ascii")
    render_chart(output, OUT_PNG)
    return output


def _synthetic_smoke() -> None:
    """Riser must out-delta a flat player; guards the rolling/delta logic."""
    n = 2 * WINDOW + 5
    dates = pd.date_range("2023-11-01", periods=n, freq="D")
    const = dict(reb=5, ast=3, stl=1, blk=1, tov=2, fga=10, fta=4, pf=2)
    rows = []
    for pid, ramp in [(1, True), (2, False)]:
        for i, d in enumerate(dates):
            pts = (25 if i >= n // 2 else 5) if ramp else 12
            rows.append({"player_id": pid, "player_name": f"P{pid}", "season": "2023-24",
                         "date": d, "min": 30.0, "pts": pts, **const})
    fake = pd.DataFrame(rows)
    valid = rolling_form(fake)
    assert not valid.empty and valid["player_id"].nunique() == 2
    movers = build_movers(valid, fake)
    assert (movers.loc[1, "delta"] > 0) and (movers.loc[1, "delta"] > movers.loc[2, "delta"])


def _check() -> None:
    _synthetic_smoke()  # logic first, no disk needed
    assert OUT_JSON.exists() and OUT_JSON.stat().st_size > 0, f"missing/empty {OUT_JSON} -- run main() first"
    data = json.loads(OUT_JSON.read_text(encoding="ascii"))
    assert data["label"] == "DESCRIPTIVE_ONLY"
    assert data["top_movers_risers"] and data["top_movers_fallers"], "empty mover tables"
    assert len(data["league_percentile_bands"]) >= 5, "missing percentile bands"
    assert data["input_coverage"]["pooled_windows"] > 0, "no retained windows"
    assert OUT_PNG.exists() and OUT_PNG.stat().st_size > 0, f"missing/empty {OUT_PNG}"
    print(f"check ok: {data['input_coverage']['movers_eligible']} eligible movers, "
          f"{data['input_coverage']['pooled_windows']} pooled windows")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        result = main()
        print(json.dumps(result["input_coverage"], indent=2))
        print(f"wrote {OUT_JSON}")
        print(f"wrote {OUT_PNG}")
