"""NBA schedule-density analytics: b2b / 3-in-4 / 4-in-6 frequencies per
team-season + the descriptive per-36 production gap under each class vs rested.

DESCRIPTIVE_ONLY (see docs/JOB_EVIDENCE_PACKET.md) -- no edge/ROI/$ claims.
DESCRIPTIVE COMPANION to the confirmed b2b mechanism receipt, NOT a
re-measurement of it: the receipt -- CONFIRMED_LOCAL claim `b2b_rest_penalty`
(effect=-1.73 pts/100 team ORtg, n=4732, p=0.0056) in
domains/basketball_nba/knowledge/validation_ledger.jsonl, computed by
scripts/team_system/effects_rest_b2b.py (team ORtg/eFG/pace vs 2+-day rest) --
OWNS the significance-tested effect. This module independently derives the
schedule classes from the boxscore `date` column and reports RAW pooled per-36
means per class; it runs no test and no CI/p-value, and does NOT restate the
receipt's -1.73 as its own result (that number is cited FROM the receipt).

Density classes, assigned to the TRAILING game of each calendar-day window,
within a season (one game per team per date). b2b: previous game exactly 1
calendar day earlier (2nd leg). 3-in-4: >=3 games in the 4 calendar days
ending on this game. 4-in-6: >=4 games in the 6 calendar days ending on it.
The three OVERLAP (a b2b that closes a cluster is also 3-in-4) -- lenses, NOT
a partition; counts are not additive. Baseline ("rested") = games in NONE of
the three (>= 2 days rest, no compression), matching the receipt's baseline.
The per-36 number reuses the frozen Win-Score-style box composite
(WEIGHTS_PER36, imported VERBATIM from box_value_index.py; Berri 2006), at
player-game grain; it is NOT BPM/EPM/RAPM.

Declared floors (declared once, never tuned to any result):
  - per-game minutes: a player-game enters the per-36 pool only at min >= MIN_PER_GAME_MINUTES
  - team-season:      reported in the frequency table only at >= MIN_TEAM_GAMES team-games
  - class delta:      a class reports a per-36 delta only at >= MIN_CLASS_PLAYER_GAMES player-games

Input:  data/domains/basketball_nba/player_boxscores.parquet (columns-only read)
Output: out/schedule_density.json  (per-team-season frequencies + per-36 deltas + methodology)
        docs/img/schedule_density.png  (ONE chart: per-36 composite delta vs rested per class)

Usage:
    python -m scripts.platformkit.analytics_showcase.schedule_density
    python -m scripts.platformkit.analytics_showcase.schedule_density --check
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
OUT_JSON = OUT_DIR / "schedule_density.json"
OUT_PNG = REPO_ROOT / "docs" / "img" / "schedule_density.png"

MIN_PER_GAME_MINUTES = 8.0       # a player-game enters the per-36 pool only at/above this
MIN_TEAM_GAMES = 20              # a team-season is reported only at/above this many team-games
MIN_CLASS_PLAYER_GAMES = 200     # a class reports a per-36 delta only at/above this many player-games

BOX_STATS = list(WEIGHTS_PER36)  # frozen composite ingredients, reused verbatim
COLS = ["team", "season", "game_id", "date", "min", *BOX_STATS]
METRICS = ["composite_per36", "pts_per36", "reb_per36", "ast_per36"]
CLASSES = [("b2b", "is_b2b"), ("3in4", "is_3in4"), ("4in6", "is_4in6")]
FLOOR_LABEL = (f"min>={MIN_PER_GAME_MINUTES:g}/game for per-36 pool; team-season>={MIN_TEAM_GAMES} "
               f"team-games to report a frequency; class>={MIN_CLASS_PLAYER_GAMES} player-games to report a delta")

MECHANISM_RECEIPT = {
    "claim": "b2b_rest_penalty",
    "verdict": "CONFIRMED_LOCAL",
    "effect_cited_from_receipt": "-1.73 pts/100 team ORtg (rested minus b2b), n=4732, p=0.0056",
    "ledger": "domains/basketball_nba/knowledge/validation_ledger.jsonl",
    "computing_script": "scripts/team_system/effects_rest_b2b.py",
    "relation": "DESCRIPTIVE COMPANION -- this module independently derives b2b/3-in-4/4-in-6 "
                "classes from the boxscore date column and reports raw pooled per-36 means per "
                "class. It does NOT re-run or re-test the mechanism; the significance-tested "
                "team-ORtg effect (and the -1.73/n/p above) belong to the receipt, not to this module.",
}


def team_schedule(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (team, season, game_id) with b2b / 3-in-4 / 4-in-6 flags on
    the trailing game of each calendar-day window. Density is a team-schedule
    property, so it is derived from distinct team-game dates, keyed by
    (team, season, game_id) so both sides of a shared game_id flag separately."""
    sched = df.drop_duplicates(["team", "season", "game_id"])[["team", "season", "game_id", "date"]].copy()
    sched["day"] = sched["date"].to_numpy().astype("datetime64[D]").astype("int64")  # days since epoch, floored
    parts = []
    for _, g in sched.groupby(["team", "season"], sort=False):
        g = g.sort_values("day")
        day = g["day"].to_numpy()
        idx = np.arange(len(day))
        prev = np.concatenate(([day[0] - 999], day[:-1]))  # sentinel makes the first game a non-b2b
        g = g.assign(
            is_b2b=(day - prev) == 1,
            is_3in4=(idx - np.searchsorted(day, day - 3, "left") + 1) >= 3,  # 4 calendar days incl. today
            is_4in6=(idx - np.searchsorted(day, day - 5, "left") + 1) >= 4,  # 6 calendar days incl. today
        )
        parts.append(g)
    return pd.concat(parts, ignore_index=True)


def build_freq_table(sched: pd.DataFrame) -> pd.DataFrame:
    """Per-team-season class frequencies over team-games clearing the floor."""
    tbl = sched.groupby(["team", "season"]).agg(
        games=("game_id", "size"),
        b2b=("is_b2b", "sum"),
        n3in4=("is_3in4", "sum"),
        n4in6=("is_4in6", "sum"),
    ).reset_index()
    tbl = tbl[tbl["games"] >= MIN_TEAM_GAMES].copy()
    tbl["b2b_freq"] = tbl["b2b"] / tbl["games"]
    tbl["freq_3in4"] = tbl["n3in4"] / tbl["games"]
    tbl["freq_4in6"] = tbl["n4in6"] / tbl["games"]
    return tbl


def player_game_density(df: pd.DataFrame, sched: pd.DataFrame) -> pd.DataFrame:
    """Qualifying player-games with per-36 composite/pts/reb/ast + class flags."""
    q = df[df["min"] >= MIN_PER_GAME_MINUTES].copy()
    for c in BOX_STATS:
        q[c] = q[c].fillna(0.0)  # a played game shouldn't carry NaN counts; guard the per-36 divide anyway
    flags = sched[["team", "season", "game_id", "is_b2b", "is_3in4", "is_4in6"]]
    q = q.merge(flags, on=["team", "season", "game_id"], how="inner")
    q["composite_per36"] = sum(w * q[s] for s, w in WEIGHTS_PER36.items()) * 36.0 / q["min"]
    for s in ("pts", "reb", "ast"):
        q[f"{s}_per36"] = q[s] * 36.0 / q["min"]
    q["is_rested"] = ~(q["is_b2b"] | q["is_3in4"] | q["is_4in6"])
    return q


def build_deltas(pg: pd.DataFrame) -> tuple[dict, dict, int]:
    """Per-class pooled per-36 means and their delta vs the rested baseline."""
    base = pg[pg["is_rested"]]
    base_means = {m: float(base[m].mean()) for m in METRICS}
    out = {}
    for cls, col in CLASSES:
        sub = pg[pg[col]]
        n = int(len(sub))
        entry = {"n_player_games": n, "reported": bool(n >= MIN_CLASS_PLAYER_GAMES)}
        for m in METRICS:
            cm = float(sub[m].mean()) if n else None
            entry[m] = round(cm, 3) if n else None
            entry[f"{m}_delta_vs_rested"] = round(cm - base_means[m], 3) if n else None
        out[cls] = entry
    return out, {m: round(v, 3) for m, v in base_means.items()}, int(len(base))


def build_output(sched: pd.DataFrame, freq: pd.DataFrame, pg: pd.DataFrame, df: pd.DataFrame) -> dict:
    deltas, base_means, n_rested = build_deltas(pg)
    seasons = sorted(df["season"].unique().tolist())
    freq_rows = [
        {"team": r["team"], "season": r["season"], "games": int(r["games"]),
         "b2b_games": int(r["b2b"]), "b2b_freq": round(float(r["b2b_freq"]), 3),
         "games_3in4": int(r["n3in4"]), "freq_3in4": round(float(r["freq_3in4"]), 3),
         "games_4in6": int(r["n4in6"]), "freq_4in6": round(float(r["freq_4in6"]), 3)}
        for _, r in freq.sort_values(["season", "team"]).iterrows()
    ]
    return {
        "label": "DESCRIPTIVE_ONLY",
        "edge_claimed": False,
        "source": SOURCE_ARTIFACT + " + docs/JOB_EVIDENCE_PACKET.md",
        "methodology": {
            "density_classes": "b2b=prev game exactly 1 calendar day earlier (2nd leg); "
                               "3in4=>=3 games in the 4 calendar days ending on this game; "
                               "4in6=>=4 games in the 6 calendar days ending on it. Assigned to the "
                               "TRAILING game of the window, within a season. OVERLAPPING lenses, NOT "
                               "a partition (a b2b closing a cluster is also 3in4) -- counts not additive.",
            "baseline": "rested = games in NONE of the three classes (>= 2 days rest, no compression)",
            "production_metric": "per-36; composite = frozen Win-Score box composite (WEIGHTS_PER36, verbatim from box_value_index.py; Berri 2006)",
            "weights_per36": WEIGHTS_PER36,
            "weights_frozen": True,
            "weights_tuned_to_output": False,
            "delta_definition": "class pooled per-36 mean minus rested pooled per-36 mean (raw, unadjusted)",
            "floors": FLOOR_LABEL,
            "seasons_pooled": seasons,
        },
        "not_this": [
            "NOT the tested mechanism -- the significance-tested b2b effect lives in the receipt (see mechanism_receipt)",
            "NOT roster/opponent/minutes/home-away adjusted (raw pooled per-36 means); NOT BPM/EPM/RAPM",
            "NOT significance-tested here (no CI/p-value on these descriptive deltas; single pooled read)",
            "classes OVERLAP -- b2b/3-in-4/4-in-6 are not mutually exclusive; do not sum their counts",
        ],
        "input_coverage": {
            "rows": int(len(df)),
            "seasons": seasons,
            "teams": int(sched["team"].nunique()),
            "team_games_total": int(len(sched)),
            "team_seasons_reported": int(len(freq)),
            "player_games_pooled": int(len(pg)),
            "rested_player_games": n_rested,
        },
        "mechanism_receipt": MECHANISM_RECEIPT,
        "rested_baseline_per36": base_means,
        "per36_deltas": deltas,
        "per_team_season_frequencies": freq_rows,
    }


def render_chart(output: dict, path: Path) -> None:
    labels = {"b2b": "b2b (2nd leg)", "3in4": "3-in-4", "4in6": "4-in-6"}
    d = output["per36_deltas"]
    order = ["b2b", "3in4", "4in6"]
    names = [labels[c] for c in order]
    vals = [d[c]["composite_per36_delta_vs_rested"] or 0.0 for c in order]
    ns = [d[c]["n_player_games"] for c in order]
    colors = ["#c0392b" if v < 0 else "#27ae60" for v in vals]
    n_seasons = len(output["methodology"]["seasons_pooled"])

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(names, vals, color=colors)
    ax.axhline(0, color="#333333", lw=0.8)
    ax.set_ylabel("per-36 box composite: class mean minus rested mean\n"
                  "(DESCRIPTIVE_ONLY -- raw, unadjusted, not significance-tested)")
    ax.set_title(f"NBA production under schedule density vs rested ({n_seasons} seasons pooled)\n"
                 f"companion to the b2b_rest_penalty mechanism receipt (which owns the tested effect)")
    for bar, v, n in zip(bars, vals, ns):
        ax.annotate(f"{v:+.2f}\nn={n:,}", (bar.get_x() + bar.get_width() / 2, v),
                    ha="center", va="bottom" if v >= 0 else "top",
                    xytext=(0, 2 if v >= 0 else -2), textcoords="offset points", fontsize=8)
    ax.margins(y=0.18)
    fig.text(0.01, 0.01, f"source: {SOURCE_ARTIFACT}  |  floor: {FLOOR_LABEL}",
             fontsize=5.5, ha="left", va="bottom", color="#555555")
    fig.text(0.99, 0.01, "DESCRIPTIVE_ONLY", fontsize=7, ha="right", va="bottom",
             color="#b33333", fontweight="bold")
    fig.tight_layout(rect=(0.0, 0.04, 1.0, 1.0))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main() -> dict:
    df = pd.read_parquet(PARQUET, columns=COLS)
    sched = team_schedule(df)
    freq = build_freq_table(sched)
    pg = player_game_density(df, sched)
    assert len(freq), "no team-season cleared the team-games floor -- check the input parquet"
    assert len(pg), "no player-game cleared the minutes floor -- check the input parquet"
    output = build_output(sched, freq, pg, df)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(output, indent=2), encoding="ascii")
    render_chart(output, OUT_PNG)
    return output


def _synthetic_smoke() -> None:
    """Known b2b + a 3-in-4 (that also closes a b2b) must flag correctly, and a
    lower-production b2b class must show a negative composite delta vs rested."""
    const = dict(reb=5, stl=1, blk=1, ast=3, fga=10, fta=4, tov=2, pf=2)
    # rested: 11-01, 11-08, 11-15 ; b2b-only: 11-02 ; 3-in-4 cluster closing a b2b: 12-01,12-03,12-04
    dates = ["2023-11-01", "2023-11-02", "2023-11-08", "2023-11-15",
             "2023-12-01", "2023-12-03", "2023-12-04"]
    compressed = {"2023-11-02", "2023-12-03", "2023-12-04"}  # lower production on compressed legs
    rows = []
    for i, ds in enumerate(dates):
        pts = 10 if ds in compressed else 30
        rows.append({"team": "AAA", "season": "2023-24", "game_id": 1000 + i,
                     "date": pd.Timestamp(ds), "min": 30.0, "pts": pts, **const})
    fake = pd.DataFrame(rows)
    sched = team_schedule(fake)
    by_gid = sched.set_index("game_id")
    assert bool(by_gid.loc[1001, "is_b2b"]) and not bool(by_gid.loc[1001, "is_3in4"])  # 11-02 pure b2b
    assert bool(by_gid.loc[1006, "is_3in4"]) and bool(by_gid.loc[1006, "is_b2b"])       # 12-04 overlap
    assert not bool(by_gid.loc[1000, "is_b2b"])                                          # first game
    pg = player_game_density(fake, sched)
    deltas, base_means, n_rested = build_deltas(pg)
    assert n_rested > 0 and np.isfinite(base_means["composite_per36"])
    assert deltas["b2b"]["n_player_games"] > 0
    assert deltas["b2b"]["composite_per36_delta_vs_rested"] < 0  # lower-production b2b legs by construction


def _check() -> None:
    _synthetic_smoke()  # logic first, no disk needed
    assert OUT_JSON.exists() and OUT_JSON.stat().st_size > 0, f"missing/empty {OUT_JSON} -- run main() first"
    data = json.loads(OUT_JSON.read_text(encoding="ascii"))
    assert data["label"] == "DESCRIPTIVE_ONLY" and data["edge_claimed"] is False
    assert data["input_coverage"]["team_seasons_reported"] > 0, "no team-seasons reported"
    assert data["input_coverage"]["player_games_pooled"] > 0, "no pooled player-games"
    assert data["per_team_season_frequencies"], "empty frequency table"
    assert all(c in data["per36_deltas"] for c in ("b2b", "3in4", "4in6")), "missing a density class"
    assert data["mechanism_receipt"]["claim"] == "b2b_rest_penalty", "mechanism receipt not cited"
    assert OUT_PNG.exists() and OUT_PNG.stat().st_size > 0, f"missing/empty {OUT_PNG}"
    print(f"check ok: {data['input_coverage']['team_seasons_reported']} team-seasons, "
          f"{data['input_coverage']['player_games_pooled']} pooled player-games")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        result = main()
        print(json.dumps(result["input_coverage"], indent=2))
        print(f"wrote {OUT_JSON}")
        print(f"wrote {OUT_PNG}")
