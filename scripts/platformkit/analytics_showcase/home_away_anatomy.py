"""home_away_anatomy.py -- NBA home/away split anatomy from the player box scores.

DESCRIPTIVE_ONLY (truth source docs/JOB_EVIDENCE_PACKET.md). NO edge/ROI/$/
forecast claim: every number describes games ALREADY PLAYED -- a home-minus-away
mean is a split of past box scores, not a prediction and not a home-court edge.

Two lenses off the SAME player-game grain (each parquet row = one player in one
game; venue = the VERIFIED `is_home` flag, 0/1 -- the same column
domains/basketball_nba/profiles/player_box_splits.py groups on):
  1. LEAGUE-LEVEL per-stat delta (by season + pooled): home_mean(stat) -
     away_mean(stat) over qualifying player-game rows, plus rel_delta_pct =
     100*(home-away)/away for cross-stat comparison, for the counting box stats;
     PLUS pooled shooting % (fg/fg3/ft = sum(makes)/sum(attempts)) home vs away
     in percentage points. Unit = the average PLAYER-GAME (unweighted over
     appearances; NOT minutes-weighted, NOT team-aggregated -- so the pts delta
     is the per-player home bump, well below the ~2-3 pt TEAM home-court margin).
  2. DISTRIBUTION across players (headline stat = pts): each qualifying player's
     home_ppg - away_ppg, summarised (mean/std/quantiles/share positive) and the
     biggest deviators BOTH ways (home boosters / road boosters).

Floors (declared once, never tuned to output):
  - PLAYER_GAMES_FLOOR = 15 home AND 15 away games to enter the per-player
    distribution / deviators (matches player_box_splits.py VENUE_FLOOR=15).
  - LEAGUE_MIN_SIDE_ROWS = 500 player-game rows EACH side for a season's league
    deltas to report (thin/absent is_home coverage is flagged + suppressed).
Negative placeholder player_ids (unresolved-lineup landmine) are dropped, same
as the domain profiles. Diacritic-split player_ids (upstream name-join bug, same
as box_value_index.py) can fragment one star across two ids -- noted, not fixed.

Input:  data/domains/basketball_nba/player_boxscores.parquet (column-selective)
Output: out/home_away_anatomy.json + docs/img/home_away_anatomy.png (ONE grouped
        diverging bar: per-stat relative home-away delta, one group per season)
Usage:  python -m scripts.platformkit.analytics_showcase.home_away_anatomy [--check]
"""
import json

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:  # package-run (-m) vs bare-script both resolve
    from scripts.platformkit.analytics_showcase.atlas_factory import REPO_ROOT, OUT_DIR
except ImportError:
    from atlas_factory import REPO_ROOT, OUT_DIR

SOURCE_ARTIFACT = "data/domains/basketball_nba/player_boxscores.parquet"
PARQUET = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
OUT_JSON = OUT_DIR / "home_away_anatomy.json"
OUT_PNG = REPO_ROOT / "docs" / "img" / "home_away_anatomy.png"

COUNTING = ["pts", "reb", "oreb", "dreb", "ast", "stl", "blk", "tov", "pf",
            "fga", "fg3a", "fta", "fgm", "fg3m", "ftm", "min"]
SHOOTING = {"fg_pct": ("fgm", "fga"), "fg3_pct": ("fg3m", "fg3a"), "ft_pct": ("ftm", "fta")}
CHART_STATS = ["pts", "reb", "ast", "fga", "fg3a", "fta", "stl", "blk", "tov", "pf", "min"]
READ_COLS = ["player_id", "player_name", "season", "is_home"] + COUNTING

PLAYER_GAMES_FLOOR = 15
LEAGUE_MIN_SIDE_ROWS = 500
N_DEVIATORS = 12
HEADLINE = "pts"


def _valid(df: pd.DataFrame) -> pd.DataFrame:
    """Real player_id (>=0, drops unresolved-lineup placeholders); venue flag
    cast to int 0/1 (kills bool/float pivot-label ambiguity)."""
    df = df[(df["player_id"] >= 0) & df["is_home"].isin([0, 1])]
    return df.assign(is_home=df["is_home"].astype(int))


def league_deltas(df: pd.DataFrame):
    """Per-stat home vs away means over one frame (one season, or pooled).
    Returns (counting dict, shooting dict, n_home, n_away)."""
    home, away = df[df["is_home"] == 1], df[df["is_home"] == 0]
    counting = {}
    for k in COUNTING:
        h, a = float(home[k].mean()), float(away[k].mean())
        counting[k] = {
            "home_mean": round(h, 4), "away_mean": round(a, 4),
            "delta": round(h - a, 4),
            "rel_delta_pct": round(100.0 * (h - a) / a, 3) if a else None,
        }
    shooting = {}
    for name, (mk, att) in SHOOTING.items():
        hd, ad = home[att].sum(), away[att].sum()
        hp = home[mk].sum() / hd if hd else np.nan
        ap = away[mk].sum() / ad if ad else np.nan
        shooting[name] = {
            "home_pct": round(float(hp) * 100, 3) if np.isfinite(hp) else None,
            "away_pct": round(float(ap) * 100, 3) if np.isfinite(ap) else None,
            "delta_pp": round(float(hp - ap) * 100, 3) if np.isfinite(hp) and np.isfinite(ap) else None,
        }
    return counting, shooting, len(home), len(away)


def player_distribution(df: pd.DataFrame):
    """Per-player home_ppg - away_ppg (headline stat), floor-gated on BOTH sides.
    Returns (summary dict, DataFrame sorted by delta desc)."""
    g = df.groupby(["player_id", "is_home"]).agg(
        pts=(HEADLINE, "sum"), n=(HEADLINE, "size"), name=("player_name", "first"),
    ).reset_index()
    piv_pts = g.pivot(index="player_id", columns="is_home", values="pts")
    piv_n = g.pivot(index="player_id", columns="is_home", values="n")
    name = g.groupby("player_id")["name"].first()
    n_home = piv_n.get(1, pd.Series(dtype=float)).reindex(piv_n.index).fillna(0)
    n_away = piv_n.get(0, pd.Series(dtype=float)).reindex(piv_n.index).fillna(0)
    ok = piv_n.index[(n_home >= PLAYER_GAMES_FLOOR) & (n_away >= PLAYER_GAMES_FLOOR)]
    rows = pd.DataFrame({
        "player_id": ok,
        "player_name": name.reindex(ok).values,
        "home_ppg": (piv_pts.loc[ok, 1] / piv_n.loc[ok, 1]).values if len(ok) else [],
        "away_ppg": (piv_pts.loc[ok, 0] / piv_n.loc[ok, 0]).values if len(ok) else [],
        "n_home": piv_n.loc[ok, 1].astype(int).values if len(ok) else [],
        "n_away": piv_n.loc[ok, 0].astype(int).values if len(ok) else [],
    })
    rows["delta"] = rows["home_ppg"] - rows["away_ppg"]
    rows = rows.sort_values("delta", ascending=False).reset_index(drop=True)
    d = rows["delta"]
    q = (lambda p: round(float(d.quantile(p)), 4)) if len(rows) else (lambda p: None)
    summary = {
        "stat": HEADLINE, "n_players": int(len(rows)),
        "mean_delta": round(float(d.mean()), 4) if len(rows) else None,
        "std_delta": round(float(d.std()), 4) if len(rows) else None,
        "min_delta": q(0.0), "p10_delta": q(0.10), "median_delta": q(0.50),
        "p90_delta": q(0.90), "max_delta": q(1.0),
        "share_positive": round(float((d > 0).mean()), 4) if len(rows) else None,
    }
    return summary, rows


def _deviators(rows: pd.DataFrame, n: int):
    def rec(r):
        return {"player_name": r["player_name"],
                "home_minus_away_ppg": round(float(r["delta"]), 3),
                "home_ppg": round(float(r["home_ppg"]), 2),
                "away_ppg": round(float(r["away_ppg"]), 2),
                "n_home": int(r["n_home"]), "n_away": int(r["n_away"])}
    top = [rec(r) for _, r in rows.head(n).iterrows()]                 # biggest home bump
    bottom = [rec(r) for _, r in rows.tail(n).iloc[::-1].iterrows()]   # biggest road bump
    return top, bottom


def build_output(df: pd.DataFrame) -> dict:
    seasons = sorted(df["season"].unique().tolist())
    by_season = {}
    for s in seasons:
        sub = df[df["season"] == s]
        counting, shooting, nh, na = league_deltas(sub)
        reported = nh >= LEAGUE_MIN_SIDE_ROWS and na >= LEAGUE_MIN_SIDE_ROWS
        summ, _ = player_distribution(sub)
        by_season[s] = {
            "coverage": {"n_rows": int(len(sub)), "n_home": int(nh), "n_away": int(na),
                         "meets_league_floor": bool(reported)},
            "league_deltas": counting if reported else None,
            "league_shooting_pct": shooting if reported else None,
            "player_distribution": summ,
        }
    counting_p, shooting_p, nh_p, na_p = league_deltas(df)
    summ_p, rows_p = player_distribution(df)
    top, bottom = _deviators(rows_p, N_DEVIATORS)
    return {
        "label": "DESCRIPTIVE_ONLY",
        "edge_claimed": False,
        "source": f"{SOURCE_ARTIFACT} + docs/JOB_EVIDENCE_PACKET.md",
        "methodology": {
            "grain": "player-game (each parquet row = one player in one game); venue = "
                     "verified is_home flag (0/1), the column player_box_splits.py groups on.",
            "league_delta": "home_mean(stat) - away_mean(stat), unweighted over player-game "
                            "appearances; rel_delta_pct = 100*(home-away)/away.",
            "player_delta": f"per-player home_ppg - away_ppg on '{HEADLINE}', floor "
                            f"{PLAYER_GAMES_FLOOR} games EACH side.",
            "shooting_pct": "pooled sum(makes)/sum(attempts) per side; delta in percentage points.",
            "floors": {"player_games_each_side": PLAYER_GAMES_FLOOR,
                       "league_min_side_rows": LEAGUE_MIN_SIDE_ROWS},
            "floors_tuned_to_output": False,
            "not_this": [
                "NOT a forecast / home-court betting edge -- games already played",
                "NOT the team home-court margin (this is the smaller per-player-game bump)",
                "NOT minutes-weighted / pace / rest / opponent / role adjusted (raw means)",
            ],
            "known_data_issue": "Diacritic-split player_ids (upstream name-join bug, same as "
                                "box_value_index.py) can fragment one player across two ids; "
                                "unfixed here (data-layer scope).",
        },
        "input_coverage": {
            "rows_valid": int(len(df)),
            "seasons_with_venue_flag": seasons,
            "unique_players": int(df["player_id"].nunique()),
            "n_home_rows": int(nh_p), "n_away_rows": int(na_p),
        },
        "by_season": by_season,
        "pooled": {
            "league_deltas": counting_p,
            "league_shooting_pct": shooting_p,
            "player_distribution": summ_p,
            "top_home_boosters": top,
            "top_road_boosters": bottom,
        },
    }


def render_chart(output: dict, path) -> None:
    """ONE grouped diverging barh: per-stat relative home-away delta, one bar
    group per season that met the league floor (fallback: pooled)."""
    season_src = {s: v["league_deltas"] for s, v in output["by_season"].items() if v["league_deltas"]}
    if not season_src:
        season_src = {"pooled": output["pooled"]["league_deltas"]}
    seasons = list(season_src)
    stats = [k for k in CHART_STATS if k in output["pooled"]["league_deltas"]]
    y = np.arange(len(stats))
    n = len(seasons); bar_h = 0.8 / n
    colors = plt.cm.viridis(np.linspace(0.15, 0.85, n))
    fig, ax = plt.subplots(figsize=(9, 7))
    for i, s in enumerate(seasons):
        vals = [season_src[s][k]["rel_delta_pct"] or 0.0 for k in stats]
        ax.barh(y + (i - (n - 1) / 2) * bar_h, vals, height=bar_h, color=colors[i], label=s)
    ax.axvline(0, color="#333", lw=0.8)
    ax.set_yticks(y); ax.set_yticklabels(stats); ax.invert_yaxis()
    ax.set_xlabel("home minus away, relative to away baseline (%)   [DESCRIPTIVE_ONLY]")
    ax.set_title("NBA home/away split anatomy: per-stat relative delta by season\n"
                 "positive = higher at home; player-game grain, games already played")
    ax.legend(fontsize=8, title="season")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main() -> dict:
    raw = pd.read_parquet(PARQUET, columns=READ_COLS)
    df = _valid(raw)
    output = build_output(df)
    output["input_coverage"]["rows_raw"] = int(len(raw))
    output["input_coverage"]["rows_dropped_invalid_venue_or_id"] = int(len(raw) - len(df))
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(output, indent=2), encoding="ascii")
    render_chart(output, OUT_PNG)
    return output


def _check() -> None:
    # (1) logic self-check on a synthetic frame -- no parquet read.
    # A: home 20 / away 10 (delta +10); B: home 8 / away 12 (delta -4); 16 games each side.
    n = 16
    parts = []
    for pid, nm, hp, ap in [(1, "A", 20, 10), (2, "B", 8, 12)]:
        for is_home, pv in ((1, hp), (0, ap)):
            d = {c: [1.0] * n for c in COUNTING}
            d["pts"] = [float(pv)] * n
            d["fga"] = [10.0] * n
            d["fgm"] = [4.0] * n
            d.update(player_id=[pid] * n, player_name=[nm] * n,
                     season=["2023-24"] * n, is_home=[is_home] * n)
            parts.append(pd.DataFrame(d))
    fake = pd.concat(parts, ignore_index=True)

    counting, shooting, nh, na = league_deltas(fake)
    assert nh == 32 and na == 32
    assert abs(counting["pts"]["home_mean"] - 14.0) < 1e-9   # (20*16 + 8*16)/32
    assert abs(counting["pts"]["away_mean"] - 11.0) < 1e-9   # (10*16 + 12*16)/32
    assert abs(counting["pts"]["delta"] - 3.0) < 1e-9
    assert abs(shooting["fg_pct"]["delta_pp"]) < 1e-9        # 4/10 both sides -> 0 pp
    summ, rows = player_distribution(fake)
    assert summ["n_players"] == 2 and abs(summ["share_positive"] - 0.5) < 1e-9
    assert rows.iloc[0]["player_name"] == "A" and abs(rows.iloc[0]["delta"] - 10.0) < 1e-9
    top, bottom = _deviators(rows, 5)
    assert top[0]["player_name"] == "A" and bottom[0]["player_name"] == "B"
    out = build_output(fake)
    assert out["label"] == "DESCRIPTIVE_ONLY" and out["edge_claimed"] is False
    assert abs(out["pooled"]["league_deltas"]["pts"]["delta"] - 3.0) < 1e-9
    # 32 rows/side is below the 500 floor -> season league deltas suppressed (exercises the gate)
    assert out["by_season"]["2023-24"]["coverage"]["meets_league_floor"] is False
    assert out["by_season"]["2023-24"]["league_deltas"] is None
    print("logic check ok")

    # (2) built outputs must exist and be nonzero (hard-assert, like nba_matchup_grid).
    assert OUT_JSON.exists(), (
        f"{OUT_JSON} missing -- run "
        f"`python -m scripts.platformkit.analytics_showcase.home_away_anatomy` first")
    obj = json.loads(OUT_JSON.read_text(encoding="ascii"))
    assert obj["pooled"]["league_deltas"], "no pooled league deltas"
    assert obj["pooled"]["player_distribution"]["n_players"] > 0, "no qualifying players"
    assert len(obj["pooled"]["top_home_boosters"]) > 0, "no deviators"
    assert OUT_PNG.exists() and OUT_PNG.stat().st_size > 0, f"chart missing/empty: {OUT_PNG}"
    print(f"check ok: {obj['pooled']['player_distribution']['n_players']} players over floor, "
          f"png {OUT_PNG.stat().st_size}B")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        result = main()
        cov = dict(result["input_coverage"])
        cov["pooled_pts_delta"] = result["pooled"]["league_deltas"]["pts"]["delta"]
        cov["pooled_players_over_floor"] = result["pooled"]["player_distribution"]["n_players"]
        print(json.dumps(cov, indent=2))
        print(f"wrote {OUT_JSON}\nwrote {OUT_PNG}")
