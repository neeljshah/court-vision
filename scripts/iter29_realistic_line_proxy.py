"""iter29_realistic_line_proxy.py — iter 29 (autonomous data-completion loop).

WHY: iter-26 measured in-game ROI at +80% endQ3 on an L5-rolling-mean line proxy.
iter-28 found zero overlap between extended_oos_canonical.csv (real book lines)
and player_quarter_stats.parquet (game state), so the REAL in-game ROI against
sharp books is unmeasured. Until that data gap closes the L5 proxy is an upper
bound — sharp books are sharper than L5.

This script builds a more REALISTIC line proxy that approximates how sharp
sportsbooks actually price props:

  1. Weighted blend of L5 + season-to-date (books use longer windows than 5).
  2. Pace adjustment: line scales with opponent pace.
  3. Opponent def_rtg adjustment: tighter defense lowers PTS/AST lines.
  4. Round to half-points (books always do).
  5. Juice at -115 / -120 (books rarely sit at -110 for props).

Backtests at threshold=1.0 endQ3 across blends + juice levels:
  - L5 alone (baseline, -110)
  - 0.7×L5 + 0.3×season, no opp adj (-110, -115, -120)
  - Realistic full: 0.6×L5 + 0.3×season + pace_adj + def_adj (-115, -120)
  - Aggressive: 0.5×L5 + 0.5×season + pace + def (-120) — closest to a true
    sharp closing line

Outputs per-stat + pooled ROI; flags the threshold at which in-game edge
matches pregame Strategy D's +23.29% extended.

Strictly READ-ONLY: no forbidden-file edits, no model writes.

Run:
    python scripts/iter29_realistic_line_proxy.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import pandas as pd  # noqa: E402

import retro_inplay_mae as v1  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
# Same calibrated sigma as cycle 95d backtest.
_CAL_SPREAD = {
    "pts": 14.0, "reb": 5.5, "ast": 4.0, "fg3m": 2.4,
    "stl": 2.0, "blk": 1.6, "tov": 2.4,
}
# League average baselines for pace + def_rtg normalisation.
_LEAGUE_PACE = 99.5
_LEAGUE_DEF_RTG = 114.0
# How much each unit of pace / def_rtg shifts a counting stat. These are
# intentionally conservative — published sportsbook research suggests prop
# lines shift ~0.2-0.4 PTS per pace point and ~0.1-0.2 PTS per def_rtg unit.
# Counting-stat sensitivities scaled to PTS for relative shifts.
_PACE_SENS = 0.012   # +1 pace = +1.2% on each counting stat
_DEF_SENS = -0.008   # -1 def_rtg (better D) = -0.8% on each counting stat


# ── betting math (mirrors cycle 95d backtest_inplay_edge.py) ─────────────────

def american_payout(odds: int, stake: float = 1.0) -> float:
    odds = int(odds)
    if odds > 0:
        return stake * (odds / 100.0)
    return stake * (100.0 / -odds)


def model_hit_prob(point_pred: float, line: float, sigma: float,
                   side: str) -> float:
    from math import erf, sqrt
    if sigma <= 0:
        return 1.0 if (
            (side == "OVER" and point_pred > line)
            or (side == "UNDER" and point_pred < line)
        ) else 0.0
    z = (line - point_pred) / sigma
    cdf_at_line = 0.5 * (1.0 + erf(z / sqrt(2.0)))
    p_over = 1.0 - cdf_at_line
    return p_over if side == "OVER" else 1.0 - p_over


def kelly_fraction(prob: float, odds: int) -> float:
    if prob is None:
        return 0.0
    b = american_payout(odds, 1.0)
    if b <= 0:
        return 0.0
    p = float(prob)
    q = 1.0 - p
    f = (b * p - q) / b
    return max(0.0, f)


def settle_bet(stake: float, side: str, line: float, actual: float,
               odds: int) -> float:
    if actual == line:
        return 0.0
    if side == "OVER":
        win = actual > line
    else:
        win = actual < line
    if win:
        return stake * american_payout(odds, 1.0)
    return -stake


def round_half(x: float) -> float:
    return round(x * 2) / 2.0


# ── data loaders ──────────────────────────────────────────────────────────────

def load_season_avgs(qstats_df, game_dates: Dict[str, str]) -> Dict[Tuple[str, int, str], float]:
    """For each (game_id, player_id, stat), compute the player's season-to-date
    average BEFORE the target game date. Aggregates all played quarters into
    per-game totals, then takes the mean over all games strictly before target.
    """
    # Per-game totals from quarter parquet.
    pg = qstats_df.groupby(["game_id", "player_id"])[list(STATS) + ["min"]].sum().reset_index()
    # Map game_id -> date for ordering.
    pg["game_date"] = pg["game_id"].map(game_dates)
    pg = pg.dropna(subset=["game_date"])
    pg = pg[pg["min"] >= 1.0]  # exclude DNP
    pg = pg.sort_values(["player_id", "game_date"]).reset_index(drop=True)

    out: Dict[Tuple[str, int, str], float] = {}
    # For each (pid, stat) compute the expanding mean shifted by 1 (no leak).
    for stat in STATS:
        pg[f"{stat}_std_mean"] = (
            pg.groupby("player_id")[stat]
              .apply(lambda s: s.shift(1).expanding().mean())
              .reset_index(level=0, drop=True)
        )
    for _, row in pg.iterrows():
        gid = row["game_id"]
        pid = int(row["player_id"])
        for stat in STATS:
            v = row.get(f"{stat}_std_mean")
            if pd.notna(v):
                out[(gid, pid, stat)] = float(v)
    return out


def load_team_advanced(qstats_df, game_dates: Dict[str, str]):
    """Returns:
      game_team: {(game_id, team_abbrev): {'pace': ..., 'def_rtg': ...}}
      pid_team:  {(game_id, player_id): team_abbrev}
      team_other: {(game_id, team_abbrev): other_team_abbrev}
    """
    ta = pd.read_parquet(os.path.join(PROJECT_DIR, "data", "team_advanced_stats.parquet"))
    game_team: Dict[Tuple[str, str], Dict[str, float]] = {}
    for _, row in ta.iterrows():
        gid = str(row["game_id"]).zfill(10)
        team = row["team_tricode"]
        game_team[(gid, team)] = {
            "pace": float(row["pace"]) if pd.notna(row["pace"]) else _LEAGUE_PACE,
            "def_rtg": float(row["def_rtg"]) if pd.notna(row["def_rtg"]) else _LEAGUE_DEF_RTG,
        }
    # Build pid → team using quarter_box cache for each game.
    pid_team: Dict[Tuple[str, int], str] = {}
    team_other: Dict[Tuple[str, str], str] = {}
    games = sorted(set(qstats_df["game_id"].unique()))
    for gid in games:
        try:
            pidmap, home_abbr, away_abbr = v1.load_team_map(gid)
        except Exception:
            continue
        if not pidmap:
            continue
        for pid, team in pidmap.items():
            pid_team[(gid, int(pid))] = team
        if home_abbr and away_abbr:
            team_other[(gid, home_abbr)] = away_abbr
            team_other[(gid, away_abbr)] = home_abbr
    return game_team, pid_team, team_other


# ── line construction ────────────────────────────────────────────────────────

def build_realistic_lines(
    l5_lines: Dict[Tuple[str, int, str], float],
    season_avgs: Dict[Tuple[str, int, str], float],
    pid_team: Dict[Tuple[str, int], str],
    team_other: Dict[Tuple[str, str], str],
    game_team: Dict[Tuple[str, str], Dict[str, float]],
    w_l5: float,
    w_season: float,
    use_pace: bool,
    use_def: bool,
    round_half_flag: bool = True,
) -> Dict[Tuple[str, int, str], float]:
    """Build realistic line = w_l5*L5 + w_season*season_avg, then apply
    pace + def_rtg multipliers, then round to half-points.
    """
    out: Dict[Tuple[str, int, str], float] = {}
    for key, l5 in l5_lines.items():
        gid, pid, stat = key
        season = season_avgs.get(key)
        if season is None:
            # Fall back to L5 alone if season missing.
            base = l5
        else:
            base = w_l5 * l5 + w_season * season
        if use_pace or use_def:
            team = pid_team.get((gid, pid))
            opp = team_other.get((gid, team)) if team else None
            if opp:
                opp_meta = game_team.get((gid, opp))
                if opp_meta:
                    mult = 1.0
                    if use_pace:
                        mult *= 1.0 + _PACE_SENS * (opp_meta["pace"] - _LEAGUE_PACE)
                    if use_def:
                        # Higher def_rtg = WORSE defense = HIGHER line.
                        mult *= 1.0 - _DEF_SENS * (opp_meta["def_rtg"] - _LEAGUE_DEF_RTG)
                    base = base * mult
        if round_half_flag:
            base = round_half(base)
        out[key] = base
    return out


# ── simulator ────────────────────────────────────────────────────────────────

def simulate_bets(
    triples: Dict[Tuple[str, int, str], float],
    lines: Dict[Tuple[str, int, str], float],
    actuals: Dict[Tuple[str, int, str], float],
    threshold: float,
    odds: int,
) -> Dict[str, dict]:
    out: Dict[str, dict] = {s: {
        "n_bets": 0, "wins": 0,
        "stake_flat": 0.0, "pnl_flat": 0.0,
    } for s in STATS}
    for key, pred in triples.items():
        gid, pid, stat = key
        line = lines.get(key)
        actual = actuals.get(key)
        if line is None or actual is None:
            continue
        edge = pred - line
        if abs(edge) < threshold:
            continue
        side = "OVER" if edge > 0 else "UNDER"
        sigma = _CAL_SPREAD.get(stat, 1.0) / (2.0 * 1.2816)
        prob = model_hit_prob(pred, line, sigma, side)
        kf = kelly_fraction(prob, odds)
        if kf <= 0:
            continue
        pnl = settle_bet(1.0, side, line, actual, odds)
        b = out[stat]
        b["n_bets"] += 1
        if pnl > 0:
            b["wins"] += 1
        b["stake_flat"] += 1.0
        b["pnl_flat"] += pnl
    for s, b in out.items():
        b["roi_flat"] = b["pnl_flat"] / b["stake_flat"] if b["stake_flat"] > 0 else None
        b["win_rate"] = b["wins"] / b["n_bets"] if b["n_bets"] > 0 else None
    return out


def pooled_roi(per_stat: Dict[str, dict]) -> Tuple[int, float]:
    n = sum(b["n_bets"] for b in per_stat.values())
    pnl = sum(b["pnl_flat"] for b in per_stat.values())
    stake = sum(b["stake_flat"] for b in per_stat.values())
    return n, (pnl / stake) if stake > 0 else None


# ── main ─────────────────────────────────────────────────────────────────────

def run(max_games: Optional[int] = None):
    print(f"  iter29 realistic_line_proxy starting...")
    qstats_df = v1.load_quarter_stats()
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]
    print(f"  games: {len(games)}")

    # 1) game_id → date map
    game_dates: Dict[str, str] = {}
    for gid in games:
        d = v1.find_game_date(gid, qstats_df)
        if d:
            game_dates[gid] = d
    print(f"  dated games: {len(game_dates)} / {len(games)}")

    # 2) endQ3 projections + actuals
    inplay: Dict[Tuple[str, int, str], float] = {}
    actuals: Dict[Tuple[str, int, str], float] = {}
    for i, gid in enumerate(games):
        if i % 100 == 0:
            print(f"    [{i}/{len(games)}] projecting...")
        snap = v1.build_snapshot(gid, "endQ3", qstats_df)
        if snap is not None:
            for (pid, stat), proj in v1.project_snapshot_to_finals(snap).items():
                inplay[(gid, pid, stat)] = float(proj)
        for (pid, stat), act in v1.actuals_for_game(gid, qstats_df).items():
            actuals[(gid, pid, stat)] = float(act)
    print(f"  endQ3 projections: {len(inplay)}; actuals: {len(actuals)}")

    # 3) L5 baseline + season-to-date averages
    l5 = v1.pregame_predictions_via_gamelog(game_dates, qstats_df)
    print(f"  L5 proxies: {len(l5)}")
    season = load_season_avgs(qstats_df, game_dates)
    print(f"  season averages: {len(season)}")

    # 4) Team-level pace + def_rtg + pid→team mapping
    game_team, pid_team, team_other = load_team_advanced(qstats_df, game_dates)
    print(f"  game-team pace/def entries: {len(game_team)}; pid→team: {len(pid_team)}")

    # 5) Construct line variants
    configs = [
        # (label, w_l5, w_season, use_pace, use_def, juice)
        ("L5 raw (-110)",      1.0, 0.0, False, False, -110),
        ("L5 raw (-115)",      1.0, 0.0, False, False, -115),
        ("L5 raw (-120)",      1.0, 0.0, False, False, -120),
        ("0.8L5+0.2S (-110)",  0.8, 0.2, False, False, -110),
        ("0.8L5+0.2S (-115)",  0.8, 0.2, False, False, -115),
        ("0.7L5+0.3S (-110)",  0.7, 0.3, False, False, -110),
        ("0.7L5+0.3S (-115)",  0.7, 0.3, False, False, -115),
        ("0.7L5+0.3S+P+D (-115)", 0.7, 0.3, True, True, -115),
        ("0.7L5+0.3S+P+D (-120)", 0.7, 0.3, True, True, -120),
        ("0.6L5+0.4S+P+D (-115)", 0.6, 0.4, True, True, -115),
        ("0.6L5+0.4S+P+D (-120)", 0.6, 0.4, True, True, -120),
        ("0.5L5+0.5S+P+D (-120)", 0.5, 0.5, True, True, -120),
    ]

    results: Dict[str, Dict] = {}
    threshold = 1.0
    for (label, w_l5, w_s, up, ud, juice) in configs:
        lines = build_realistic_lines(
            l5, season, pid_team, team_other, game_team,
            w_l5, w_s, up, ud, round_half_flag=True,
        )
        per_stat = simulate_bets(inplay, lines, actuals, threshold, juice)
        n_pooled, roi_pooled = pooled_roi(per_stat)
        results[label] = {"per_stat": per_stat, "n_pool": n_pooled, "roi_pool": roi_pooled}
        roi_s = f"{roi_pooled:+.4f}" if roi_pooled is not None else "—"
        print(f"  {label:32s}  n={n_pooled:5d}  ROI={roi_s}")

    # ── per-stat table for headline configs ────────────────────────────────
    print("\n  ── Per-stat ROI: L5 raw (-110) vs 0.7L5+0.3S+P+D (-115) vs 0.6L5+0.4S+P+D (-120)")
    print(f"  {'stat':6s} {'n_L5':>6s} {'ROI_L5':>10s} {'n_R1':>6s} {'ROI_R1':>10s} {'n_R2':>6s} {'ROI_R2':>10s}")
    for stat in STATS:
        a = results["L5 raw (-110)"]["per_stat"][stat]
        b = results["0.7L5+0.3S+P+D (-115)"]["per_stat"][stat]
        c = results["0.6L5+0.4S+P+D (-120)"]["per_stat"][stat]
        def _f(x):
            return f"{x['roi_flat']:+.4f}" if x['roi_flat'] is not None else "    —   "
        print(f"  {stat:6s} {a['n_bets']:>6d} {_f(a):>10s} "
              f"{b['n_bets']:>6d} {_f(b):>10s} "
              f"{c['n_bets']:>6d} {_f(c):>10s}")

    # Save JSON for record
    out_json = os.path.join(PROJECT_DIR, "data", "cache", "iter29_realistic_line_proxy.json")
    summary = {
        "n_games": len(games),
        "threshold": threshold,
        "configs": [
            {
                "label": label,
                "n_pool": results[label]["n_pool"],
                "roi_pool": results[label]["roi_pool"],
                "per_stat": {
                    s: {
                        "n_bets": results[label]["per_stat"][s]["n_bets"],
                        "wins": results[label]["per_stat"][s]["wins"],
                        "win_rate": results[label]["per_stat"][s]["win_rate"],
                        "roi_flat": results[label]["per_stat"][s]["roi_flat"],
                    }
                    for s in STATS
                },
            }
            for (label, *_rest) in configs
        ],
    }
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=lambda v: None if v != v else v)
    print(f"\n  wrote {out_json}")
    return summary


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()
    run(max_games=args.max_games)
