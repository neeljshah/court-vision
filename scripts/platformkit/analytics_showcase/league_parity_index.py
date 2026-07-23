"""league_parity_index.py -- season competitiveness / parity indices from NBA outcomes.

DESCRIPTIVE_ONLY (see docs/JOB_EVIDENCE_PACKET.md). NO edge/ROI/$/forecast: every
number describes seasons ALREADY PLAYED; a completed season's parity is not a
prediction of the next one.

Scope -- from the player box-score parquet (same team-game derivation as
nba_matchup_grid.py): team-game points = sum of a team's players' `pts` per
game_id; only game_ids with EXACTLY 2 distinct teams are used (all-star/malformed
dropped, count reported); the higher score wins (ties -- NBA OT rules them out --
are counted and excluded from margins). Per season, over every team that played
(0-win teams INCLUDED), it reports win-share concentration (Gini, HHI + 1/N floor
+ normalized), the games-normalized win_pct_stdev companion, and absolute-margin
dispersion. Each metric's exact definition is in the JSON `methodology` block.

DECLARED FLOORS (declared once, never tuned to output): MIN_GAMES_PER_SEASON --
a season below it is a small-sample artifact, still reported but flagged
meets_games_floor=false and EXCLUDED from the chart; CLOSE_GAME_PTS=5 defines a
"close" game. Games are pooled AS PRESENT in the parquet (reg season + any
playoff games, which inflate win concentration; no game-type flag to split);
opponent-raw (no strength-of-schedule adjustment). The full caveat list is in the
JSON `methodology.not_this` block.

Input:  data/domains/basketball_nba/player_boxscores.parquet
        (columns-only read: game_id, team, season, date, pts)
Output: out/league_parity_index.json     (per-season indices + methodology)
        docs/img/league_parity_index.png  (ONE win-share Lorenz-curve chart)

Usage:
    python -m scripts.platformkit.analytics_showcase.league_parity_index
    python -m scripts.platformkit.analytics_showcase.league_parity_index --check
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
OUT_JSON = OUT_DIR / "league_parity_index.json"
OUT_PNG = REPO_ROOT / "docs" / "img" / "league_parity_index.png"

COLS = ["game_id", "team", "season", "date", "pts"]
MIN_GAMES_PER_SEASON = 200   # below this a season's parity index is a small-sample artifact -> flagged + off the chart
CLOSE_GAME_PTS = 5           # a game decided by <= this many points is "close" (descriptive)
FULL_SEASON_GAMES = 1230     # 30 teams x 82 / 2 = a complete NBA regular season; a reference for the partiality flag, NOT a filter


def gini(counts) -> float:
    """Gini coefficient of nonnegative counts (scale-invariant; 0 = equal)."""
    x = np.sort(np.asarray(counts, dtype=float))
    n = x.size
    total = x.sum()
    if n == 0 or total == 0:
        return 0.0
    idx = np.arange(1, n + 1)
    return float(np.sum((2 * idx - n - 1) * x) / (n * total))


def hhi(counts) -> float:
    """Herfindahl index of shares derived from counts (1/N .. 1)."""
    s = np.asarray(counts, dtype=float)
    total = s.sum()
    if total == 0:
        return 0.0
    p = s / total
    return float(np.sum(p ** 2))


def hhi_normalized(counts, n_teams: int) -> float:
    """(HHI - 1/N) / (1 - 1/N), clamped at 0: 0 = perfectly balanced, 1 = monopoly."""
    if n_teams <= 1:
        return 0.0
    floor = 1.0 / n_teams
    return max(0.0, (hhi(counts) - floor) / (1.0 - floor))


def lorenz(counts):
    """Lorenz-curve points: cumulative team share (x) vs cumulative win share (y)."""
    x = np.sort(np.asarray(counts, dtype=float))
    n = x.size
    cum = np.concatenate([[0.0], np.cumsum(x)])
    y = cum / cum[-1] if cum[-1] > 0 else cum
    return np.arange(0, n + 1) / n, y


def build_team_games(df: pd.DataFrame):
    """Player box rows -> (kept team-games, decided-game winners, coverage).

    kept: one row per (game_id, team, pts, season) for exactly-2-team games.
    wins: one row per DECIDED game -- team_w beat team_l by abs_margin.
    """
    tg = df.groupby(["game_id", "team"], as_index=False).agg(pts=("pts", "sum"))
    n_teams_in_game = tg.groupby("game_id")["team"].transform("nunique")
    kept = tg[n_teams_in_game == 2][["game_id", "team", "pts"]]
    gs = df.drop_duplicates("game_id")[["game_id", "season"]]
    kept = kept.merge(gs, on="game_id")
    m = kept.merge(kept, on=["game_id", "season"], suffixes=("_w", "_l"))
    m = m[m["team_w"] != m["team_l"]]
    wins = m[m["pts_w"] > m["pts_l"]].copy()   # one row per decided game; ties drop out
    wins["abs_margin"] = wins["pts_w"] - wins["pts_l"]
    games_total = int(tg["game_id"].nunique())
    games_two = int(kept["game_id"].nunique())
    coverage = {
        "rows": int(len(df)),
        "games_total": games_total,
        "games_two_team": games_two,
        "games_dropped_not_two_team": games_total - games_two,
        "seasons": sorted(df["season"].unique().tolist()),
        "date_max": str(df["date"].max().date()) if len(df) else None,
    }
    return kept, wins, coverage


def _win_counts(wins_season, teams):
    """Per-team win counts aligned to the full team list (0-win teams -> 0)."""
    wc = wins_season["team_w"].value_counts()
    return np.array([int(wc.get(t, 0)) for t in teams], dtype=float)


def per_season(kept: pd.DataFrame, wins: pd.DataFrame) -> list:
    out = []
    for season in sorted(kept["season"].unique().tolist()):
        ks = kept[kept["season"] == season]
        ws = wins[wins["season"] == season]
        teams = sorted(ks["team"].unique().tolist())
        n_teams = len(teams)
        n_games = int(ks["game_id"].nunique())
        win_counts = _win_counts(ws, teams)
        gp = ks["team"].value_counts()
        games_played = np.array([int(gp.get(t, 0)) for t in teams], dtype=float)
        win_pct = np.divide(win_counts, games_played, out=np.zeros_like(win_counts), where=games_played > 0)
        margins = ws["abs_margin"].to_numpy(dtype=float)
        out.append({
            "season": season,
            "n_games": n_games,
            "n_decided_games": int(len(ws)),
            "n_ties_or_undecided": n_games - int(len(ws)),
            "n_teams": n_teams,
            "meets_games_floor": bool(n_games >= MIN_GAMES_PER_SEASON),
            "looks_partial_vs_full_season": bool(n_games < FULL_SEASON_GAMES),
            "win_share_gini": round(gini(win_counts), 4),
            "win_share_hhi": round(hhi(win_counts), 4),
            "hhi_balanced_floor_1_over_n": round(1.0 / n_teams, 4) if n_teams else None,
            "win_share_hhi_normalized": round(hhi_normalized(win_counts, n_teams), 4),
            "win_pct_stdev": round(float(np.std(win_pct, ddof=1)) if n_teams > 1 else 0.0, 4),
            "margin_mean_abs": round(float(margins.mean()) if margins.size else 0.0, 2),
            "margin_stdev_abs": round(float(np.std(margins, ddof=1)) if margins.size > 1 else 0.0, 2),
            "pct_close_games_le5": round(float((margins <= CLOSE_GAME_PTS).mean() * 100) if margins.size else 0.0, 1),
            "max_wins": int(win_counts.max()) if win_counts.size else 0,
            "min_wins": int(win_counts.min()) if win_counts.size else 0,
        })
    return out


def build_output(seasons: list, coverage: dict) -> dict:
    floor_ok = [s for s in seasons if s["meets_games_floor"]]
    most = min(floor_ok, key=lambda s: s["win_share_gini"]) if floor_ok else None
    least = max(floor_ok, key=lambda s: s["win_share_gini"]) if floor_ok else None
    return {
        "label": "DESCRIPTIVE_ONLY",
        "source": f"{SOURCE_ARTIFACT} + docs/JOB_EVIDENCE_PACKET.md",
        "methodology": {
            "unit": "team-game points = sum of a team's players' pts within one game_id",
            "game_filter": "only game_ids with exactly 2 distinct teams; higher score wins (ties excluded from margins)",
            "win_share_gini": "Gini of per-team win counts (wins/total-wins sum to 1); 0 = balanced, (N-1)/N = one team hoards all",
            "win_share_hhi": "Herfindahl of win shares; balanced floor = 1/N; normalized = (HHI-1/N)/(1-1/N)",
            "win_pct_stdev": "std of team win percentage -- games-normalized companion (robust to unequal game counts)",
            "margin_dispersion": f"mean/std of absolute final margin + pct of games decided by <= {CLOSE_GAME_PTS} points",
            "not_a_forecast": True,
            "not_this": [
                "NOT a prediction of any future season's parity (describes seasons already played)",
                "NOT reg-season-only (pooled with any playoff games in the parquet, which inflate win concentration)",
                "NOT strength-of-schedule adjusted (opponent-raw win counts)",
            ],
        },
        "declared_floors": {
            "min_games_per_season": MIN_GAMES_PER_SEASON,
            "rule": "season below the floor is flagged meets_games_floor=false and excluded from the Lorenz chart",
            "close_game_pts": CLOSE_GAME_PTS,
            "full_regular_season_games_reference": FULL_SEASON_GAMES,
        },
        "input_coverage": coverage,
        "extremes_descriptive": {
            "most_balanced_season": {"season": most["season"], "win_share_gini": most["win_share_gini"]} if most else None,
            "least_balanced_season": {"season": least["season"], "win_share_gini": least["win_share_gini"]} if least else None,
        },
        "seasons": seasons,
    }


def render_chart(seasons: list, kept: pd.DataFrame, wins: pd.DataFrame, path) -> None:
    """ONE win-share Lorenz curve per floor-meeting season + the equality diagonal.

    The gap between a season's curve and the diagonal IS its Gini -- flatter/lower
    curve = more concentrated wins = less competitive balance.
    """
    floor_ok = [s for s in seasons if s["meets_games_floor"]]
    fig, ax = plt.subplots(figsize=(7.5, 7))
    ax.plot([0, 1], [0, 1], ls="--", color="#888888", label="perfect balance (Gini=0)")
    colors = plt.cm.viridis(np.linspace(0.15, 0.85, max(len(floor_ok), 1)))
    for c, s in zip(colors, floor_ok):
        ks = kept[kept["season"] == s["season"]]
        ws = wins[wins["season"] == s["season"]]
        teams = sorted(ks["team"].unique().tolist())
        x, y = lorenz(_win_counts(ws, teams))
        ax.plot(x, y, marker="o", ms=3, color=c,
                label=f"{s['season']} (Gini={s['win_share_gini']:.3f})")
    ax.set_xlabel("cumulative share of teams (fewest wins -> most)")
    ax.set_ylabel("cumulative share of league wins")
    ax.set_title("NBA win-share Lorenz curves by season\n"
                 "DESCRIPTIVE_ONLY -- completed-season parity, not a forecast")
    ax.set(xlim=(0, 1), ylim=(0, 1))
    ax.set_aspect("equal")
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main() -> dict:
    df = pd.read_parquet(PARQUET, columns=COLS)
    kept, wins, coverage = build_team_games(df)
    seasons = per_season(kept, wins)
    output = build_output(seasons, coverage)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(output, indent=2), encoding="ascii")
    render_chart(seasons, kept, wins, OUT_PNG)
    return output


def _check() -> None:
    # (1) index-math self-checks -- floor-independent, no parquet read.
    assert abs(gini([1, 1, 1, 1])) < 1e-9, "equal counts -> Gini 0"
    assert abs(gini([0, 2]) - 0.5) < 1e-9, "one-team-hoards -> Gini (N-1)/N"
    assert gini([1, 1]) < gini([2, 0]), "concentrated wins raise the Gini"
    assert abs(hhi([1, 1]) - 0.5) < 1e-9 and abs(hhi([2, 0]) - 1.0) < 1e-9
    assert abs(hhi_normalized([2, 0], 2) - 1.0) < 1e-9  # monopoly normalizes to 1
    lx, ly = lorenz([1, 1, 1])
    assert lx[0] == 0.0 and abs(lx[-1] - 1.0) < 1e-9 and abs(ly[-1] - 1.0) < 1e-9
    # (2) end-to-end on a synthetic frame; game 5 is a 3-team row that MUST drop.
    # S1: A beats B, then B beats A -> 1-1, perfectly balanced (Gini 0).
    # S2: A beats B twice -> 2-0, concentrated. C appears ONLY in the dropped game.
    fake = pd.DataFrame({
        "game_id": [1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 5],
        "team":    ["A", "B", "A", "B", "A", "B", "A", "B", "A", "B", "C"],
        "season":  ["S1"] * 4 + ["S2"] * 7,
        "date":    pd.to_datetime(["2023-11-01"] * 11),
        "pts":     [100, 90, 90, 100, 100, 80, 100, 70, 55, 55, 55],
    })
    kept, wins, cov = build_team_games(fake)
    assert cov["games_two_team"] == 4 and cov["games_dropped_not_two_team"] == 1
    seasons = per_season(kept, wins)
    by = {s["season"]: s for s in seasons}
    assert abs(by["S1"]["win_share_gini"]) < 1e-9, "S1 is 1-1 balanced"
    assert by["S2"]["win_share_gini"] > by["S1"]["win_share_gini"], "S2 is 2-0 concentrated"
    assert by["S2"]["win_share_hhi"] > by["S1"]["win_share_hhi"]
    assert by["S1"]["n_teams"] == 2 and by["S2"]["n_teams"] == 2, "C only in the dropped 3-team game"
    out = build_output(seasons, cov)
    assert out["label"] == "DESCRIPTIVE_ONLY"
    print("logic check ok")
    # (3) built artifacts must exist and be nonzero (like nba_matchup_grid).
    assert OUT_JSON.exists(), (
        f"{OUT_JSON} missing -- run "
        f"`python -m scripts.platformkit.analytics_showcase.league_parity_index` first"
    )
    obj = json.loads(OUT_JSON.read_text(encoding="ascii"))
    assert obj["seasons"], "no seasons in output"
    assert any(s["meets_games_floor"] for s in obj["seasons"]), "no season met the games floor"
    for s in obj["seasons"]:
        if s["meets_games_floor"]:
            assert 0.0 <= s["win_share_gini"] <= 1.0, "Gini out of [0,1]"
            assert s["win_share_hhi"] > 0.0, "HHI must be positive with nonzero wins"
    assert OUT_PNG.exists() and OUT_PNG.stat().st_size > 0, f"chart missing/empty: {OUT_PNG}"
    n_floor = sum(s["meets_games_floor"] for s in obj["seasons"])
    print(f"check ok: {len(obj['seasons'])} seasons, {n_floor} met floor, png {OUT_PNG.stat().st_size}B")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        result = main()
        print(json.dumps({
            "seasons": [s["season"] for s in result["seasons"]],
            "gini_by_season": {s["season"]: s["win_share_gini"] for s in result["seasons"]},
            "games_two_team": result["input_coverage"]["games_two_team"],
            "games_dropped_not_two_team": result["input_coverage"]["games_dropped_not_two_team"],
        }, indent=2))
        print(f"wrote {OUT_JSON}\nwrote {OUT_PNG}")
