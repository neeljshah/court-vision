"""Signal builder: per-player SITUATIONAL SPLITS profile.

Reads five atlas parquets (pre-aggregated, multi-season) plus the raw
player_quarter_stats.parquet to emit one wide row per player_id with
flat scalar signals covering every situational dimension requested:

  Quarter scoring shape  : q1-q4 pts/reb/ast/min per game, q4_fade_abs,
                           q4_vs_early_ratio.  Derived fresh from raw
                           player_quarter_stats (shift-free — these are
                           season aggregates, not per-game predictors).
  B2B fade               : b2b_pts_delta, b2b_reb_delta, b2b_ast_delta,
                           b2b_min_delta, b2b_efg_delta (B2B 2nd leg vs
                           rested/1-day-rest baseline).
  Rest-day response      : efg and minutes for three rest buckets (b2b,
                           one_day, two_plus) plus fatigue proxy diffs.
  Home / road split      : pts/reb/ast/fg3m delta (home minus road) plus
                           absolute road averages.
  Leading/trailing split : pts, reb, ast, efg% while team leading vs
                           trailing vs tied (measured per quarter).
  Foul-trouble proxy     : mean_pf_pg, foul_trouble_rate (games ≥4 PF),
                           foul_out_rate, early_foul_trouble_rate,
                           q1_pf_pg (picking up early fouls = predictive
                           of reduced minutes and usage).
  Blowout behavior       : pct_games_in_garbage_time,
                           min_pct_in_garbage_time, gt_pts_pg (scoring
                           in garbage-time — often inflated vs real
                           competition).

Leak rule: SEASON-AGGREGATE / SCOUTING — all signals computed over a
full past season (or set of seasons) without future leakage.  They are
safe as scouting context (Consumer A) and can be screened as pregame
point-model candidates (Consumer D) subject to the standard walk-forward
+ OOS-ROI gate.  Do NOT use raw per-game values without shift(1) if
feeding inline into the point model.

Sources:
  data/cache/atlas_player_quarter_shape_fatigue.parquet  (497 players)
  data/cache/atlas_player_rest_b2b_splits.parquet        (722 players)
  data/cache/atlas_player_situational_splits.parquet     (690 players)
  data/cache/atlas_player_score_margin_splits.parquet    (540 players)
  data/cache/atlas_player_foul_tendency.parquet          (465 players)
  data/player_quarter_stats.parquet                      (raw, 609 players)

Output: data/cache/signals/situational_splits.parquet — one row per
player_id with ~40 flat scalar columns.

  python scripts/signals/build_situational_splits.py
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(ROOT, "data", "cache", "signals")
OUT = os.path.join(OUT_DIR, "situational_splits.parquet")

# Source paths
_ATLAS = os.path.join(ROOT, "data", "cache")
_PQS = os.path.join(ROOT, "data", "player_quarter_stats.parquet")
_Q_SHAPE = os.path.join(_ATLAS, "atlas_player_quarter_shape_fatigue.parquet")
_REST_B2B = os.path.join(_ATLAS, "atlas_player_rest_b2b_splits.parquet")
_SITUATIONAL = os.path.join(_ATLAS, "atlas_player_situational_splits.parquet")
_SCORE_MGN = os.path.join(_ATLAS, "atlas_player_score_margin_splits.parquet")
_FOUL = os.path.join(_ATLAS, "atlas_player_foul_tendency.parquet")

MIN_GAMES_QUARTER = 10   # minimum season games to emit quarter signal
MIN_GAMES_SPLIT = 5      # minimum games in a situational split to emit


def _safe_json(val) -> dict:
    """Parse a JSON string or return {} if null/non-string."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return {}
    if isinstance(val, dict):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return {}


# ---------------------------------------------------------------------------
# 1. Quarter shape — derived FRESH from raw player_quarter_stats
# ---------------------------------------------------------------------------

def _quarter_shape_from_raw() -> pd.DataFrame:
    """Aggregate per-quarter stats for each player over all 2024-25+ games.

    Returns one row per player_id with q1-q4 pts/reb/ast/min per game,
    q4_fade_abs (q4_pts - q1_pts), q4_vs_early_ratio (q4_pts / q1_pts),
    and n_games.  Season-aggregate: no shift needed.
    """
    pqs = pd.read_parquet(_PQS)
    # Keep only standard quarters (OT handled by NBA data as period>4 — not present here)
    pqs = pqs[pqs["period"].between(1, 4)].copy()

    # Per-game totals (needed to count n_games per player)
    game_totals = (
        pqs.groupby(["player_id", "game_id"])["min"].sum().reset_index()
    )
    n_games = game_totals.groupby("player_id")["game_id"].count().rename("n_games_pqs")

    # Per-quarter averages
    qpivot = (
        pqs.groupby(["player_id", "period"])
        .agg(pts=("pts", "mean"), reb=("reb", "mean"),
             ast=("ast", "mean"), min=("min", "mean"))
        .unstack(level="period")
    )
    qpivot.columns = [f"q{p}_{stat}" for stat, p in qpivot.columns]
    qpivot = qpivot.reset_index()

    # Q4 fade signals
    for stat in ("pts", "reb", "ast"):
        q1 = qpivot.get(f"q1_{stat}")
        q4 = qpivot.get(f"q4_{stat}")
        if q1 is not None and q4 is not None:
            qpivot[f"q4_fade_{stat}_abs"] = q4 - q1
            qpivot[f"q4_vs_q1_{stat}_ratio"] = (
                q4 / q1.replace(0, np.nan)
            ).round(3)

    qpivot = qpivot.join(n_games, on="player_id")
    # Filter: only players with enough games
    qpivot = qpivot[qpivot["n_games_pqs"].fillna(0) >= MIN_GAMES_QUARTER]
    return qpivot.round(3)


# ---------------------------------------------------------------------------
# 2. Atlas: quarter shape + B2B fade
# ---------------------------------------------------------------------------

def _atlas_quarter_shape() -> pd.DataFrame:
    df = pd.read_parquet(_Q_SHAPE)
    keep = ["player_id", "b2b_pts_delta", "b2b_reb_delta", "b2b_ast_delta",
            "b2b_decay_ratio", "b2b_n_games", "n_games", "confidence", "as_of"]
    # b2b_reb_delta / b2b_ast_delta may not exist — check
    avail = [c for c in keep if c in df.columns]
    out = df[avail].copy().rename(columns={"n_games": "n_games_qshape",
                                            "confidence": "qshape_confidence"})
    return out


# ---------------------------------------------------------------------------
# 3. Atlas: rest / B2B splits
# ---------------------------------------------------------------------------

def _atlas_rest_b2b() -> pd.DataFrame:
    df = pd.read_parquet(_REST_B2B)
    rows = []
    for _, r in df.iterrows():
        pid = int(r["player_id"])
        b2b = _safe_json(r.get("b2b"))
        one_day = _safe_json(r.get("one_day"))
        two_plus = _safe_json(r.get("two_plus"))
        fat = _safe_json(r.get("fatigue_proxy"))
        rows.append({
            "player_id": pid,
            "b2b_efg": b2b.get("efg_pct"),
            "b2b_min_pg": b2b.get("min_pg"),
            "b2b_n_games_rest": b2b.get("n_games"),
            "one_day_efg": one_day.get("efg_pct"),
            "one_day_min_pg": one_day.get("min_pg"),
            "two_plus_efg": two_plus.get("efg_pct"),
            "two_plus_min_pg": two_plus.get("min_pg"),
            "efg_b2b_minus_2plus": fat.get("efg_b2b_minus_2plus"),
            "min_b2b_minus_2plus": fat.get("min_b2b_minus_2plus"),
            "rest_confidence": r.get("confidence"),
            "rest_as_of": str(r.get("as_of", "")),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 4. Atlas: situational splits (home/road, blowout, back-to-back per-stat)
# ---------------------------------------------------------------------------

def _atlas_situational() -> pd.DataFrame:
    df = pd.read_parquet(_SITUATIONAL)
    rows = []
    for _, r in df.iterrows():
        pid = int(r["player_id"])
        hr = _safe_json(r.get("home_road"))
        home = hr.get("home", {})
        road = hr.get("road", {})
        blowout = _safe_json(r.get("blowout"))
        gt_perf = blowout.get("gt_performance", {})
        b2b_sit = _safe_json(r.get("back_to_back"))
        b2b_2nd = b2b_sit.get("b2b_second_night", {})
        rows.append({
            "player_id": pid,
            # Home / road
            "home_n_games": home.get("n_games"),
            "home_pts_pg": home.get("pts_pg"),
            "road_pts_pg": road.get("pts_pg"),
            "pts_delta_home_minus_road": home.get("pts_delta_home_minus_road"),
            "reb_delta_home_minus_road": home.get("reb_delta_home_minus_road"),
            "ast_delta_home_minus_road": home.get("ast_delta_home_minus_road"),
            "fg3m_delta_home_minus_road": home.get("fg3m_delta_home_minus_road"),
            # Blowout / garbage time
            "pct_games_in_garbage_time": blowout.get("pct_games_in_garbage_time"),
            "mean_pct_min_in_gt": blowout.get("mean_pct_min_in_gt"),
            "gt_pts_pg": gt_perf.get("pts_in_gt_pg"),
            "gt_reb_pg": gt_perf.get("reb_in_gt_pg"),
            "gt_ast_pg": gt_perf.get("ast_in_gt_pg"),
            "gt_fg_pct": gt_perf.get("gt_fg_pct"),
            "n_games_blowout_total": blowout.get("n_games_total"),
            # B2B per-stat delta from situational (may be richer than qshape)
            "b2b_pts_pg_2ndleg": b2b_2nd.get("pts_pg"),
            "b2b_pts_delta_vs_rested": b2b_2nd.get("pts_delta_b2b_minus_rested"),
            "b2b_reb_delta_vs_rested": b2b_2nd.get("reb_delta_b2b_minus_rested"),
            "b2b_ast_delta_vs_rested": b2b_2nd.get("ast_delta_b2b_minus_rested"),
            "b2b_min_delta_vs_rested": b2b_2nd.get("min_delta_b2b_minus_rested"),
            "sit_n_games": int(r.get("n") or 0),
            "sit_confidence": r.get("confidence"),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 5. Atlas: score-margin splits (leading / trailing / tied)
# ---------------------------------------------------------------------------

def _atlas_score_margin() -> pd.DataFrame:
    df = pd.read_parquet(_SCORE_MGN)
    rows = []
    for _, r in df.iterrows():
        pid = int(r["player_id"])
        leading = _safe_json(r.get("leading"))
        trailing = _safe_json(r.get("trailing"))
        tied = _safe_json(r.get("tied"))

        n_lead = leading.get("n_games", 0) or 0
        n_trail = trailing.get("n_games", 0) or 0
        n_tied = tied.get("n_games", 0) or 0

        # Compute trailing minus leading efg delta (directional: does player
        # elevate or deflate when trailing?)
        efg_lead = leading.get("efg_pct")
        efg_trail = trailing.get("efg_pct")
        efg_delta_trail_minus_lead = (
            (efg_trail - efg_lead)
            if efg_lead is not None and efg_trail is not None
            else None
        )
        rows.append({
            "player_id": pid,
            # Leading
            "lead_pts_pg": leading.get("pts_pg") if n_lead >= MIN_GAMES_SPLIT else None,
            "lead_reb_pg": leading.get("reb_pg") if n_lead >= MIN_GAMES_SPLIT else None,
            "lead_ast_pg": leading.get("ast_pg") if n_lead >= MIN_GAMES_SPLIT else None,
            "lead_efg": leading.get("efg_pct") if n_lead >= MIN_GAMES_SPLIT else None,
            "lead_n_games": n_lead,
            # Trailing
            "trail_pts_pg": trailing.get("pts_pg") if n_trail >= MIN_GAMES_SPLIT else None,
            "trail_reb_pg": trailing.get("reb_pg") if n_trail >= MIN_GAMES_SPLIT else None,
            "trail_ast_pg": trailing.get("ast_pg") if n_trail >= MIN_GAMES_SPLIT else None,
            "trail_efg": trailing.get("efg_pct") if n_trail >= MIN_GAMES_SPLIT else None,
            "trail_n_games": n_trail,
            # Tied
            "tied_pts_pg": tied.get("pts_pg") if n_tied >= MIN_GAMES_SPLIT else None,
            "tied_efg": tied.get("efg_pct") if n_tied >= MIN_GAMES_SPLIT else None,
            "tied_n_games": n_tied,
            # Derived
            "efg_trail_minus_lead": efg_delta_trail_minus_lead,
            "margin_n_games": r.get("n"),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 6. Atlas: foul tendency
# ---------------------------------------------------------------------------

def _atlas_foul_tendency() -> pd.DataFrame:
    df = pd.read_parquet(_FOUL)
    rows = []
    for _, r in df.iterrows():
        pid = int(r["player_id"])
        committed = _safe_json(r.get("committed"))
        early = _safe_json(r.get("early_trouble"))
        foul_out = _safe_json(r.get("foul_out_risk"))
        by_q = _safe_json(r.get("by_quarter"))
        rows.append({
            "player_id": pid,
            "mean_pf_pg": foul_out.get("mean_pf_pg"),
            "foul_out_rate": foul_out.get("foul_out_rate"),
            "foul_trouble_rate_l10": committed.get("foul_trouble_rate_l10"),
            "season_pf_per_36": committed.get("season_pf_per_36"),
            "early_foul_trouble_rate": early.get("early_foul_trouble_rate"),
            "half_foul_trouble_rate": early.get("half_trouble_rate"),
            "q1_pf_pg": by_q.get("q1_pf_pg"),
            "q2_pf_pg": by_q.get("q2_pf_pg"),
            "q3_pf_pg": by_q.get("q3_pf_pg"),
            "q4_pf_pg": by_q.get("q4_pf_pg"),
            "foul_n_games": foul_out.get("n_games"),
            "foul_confidence": r.get("confidence"),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 7. Combine all frames on player_id (outer join — not every source covers every player)
# ---------------------------------------------------------------------------

def build() -> pd.DataFrame:
    pqs_q = _quarter_shape_from_raw()
    atlas_q = _atlas_quarter_shape()
    rest = _atlas_rest_b2b()
    sit = _atlas_situational()
    margin = _atlas_score_margin()
    foul = _atlas_foul_tendency()

    # Merge chain: outer on player_id so we keep all players from any source
    df = (
        pqs_q
        .merge(atlas_q, on="player_id", how="outer")
        .merge(rest,    on="player_id", how="outer")
        .merge(sit,     on="player_id", how="outer")
        .merge(margin,  on="player_id", how="outer")
        .merge(foul,    on="player_id", how="outer")
    )

    # Sanity guard: row count should equal distinct players, not a cartesian blowup
    n_players = df["player_id"].nunique()
    assert len(df) == n_players, (
        f"Row count {len(df)} != player count {n_players} — join produced duplicates"
    )

    df["player_id"] = df["player_id"].astype(int)
    df = df.sort_values("player_id").reset_index(drop=True)
    return df


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    out = build()
    out.to_parquet(OUT, index=False)

    n_rows = len(out)
    n_players = out["player_id"].nunique()
    print(f"DONE: situational_splits -> {OUT}")
    print(f"  rows={n_rows}  distinct players={n_players}  columns={len(out.columns)}")
    print()

    # 3 sample rows
    print("--- Sample rows (3) ---")
    for r in out.head(3).itertuples(index=False):
        print(f"  player_id={r.player_id}  "
              f"q4_fade_pts_abs={getattr(r,'q4_fade_pts_abs',None)}  "
              f"b2b_pts_delta={getattr(r,'b2b_pts_delta',None)}  "
              f"pts_delta_home_minus_road={getattr(r,'pts_delta_home_minus_road',None)}  "
              f"trail_pts_pg={getattr(r,'trail_pts_pg',None)}  "
              f"mean_pf_pg={getattr(r,'mean_pf_pg',None)}")
    print()

    # Sanity ranking: top Q4 faders (most negative q4_fade_pts_abs)
    fade_col = "q4_fade_pts_abs"
    if fade_col in out.columns and out[fade_col].notna().any():
        worst = out.dropna(subset=[fade_col]).nsmallest(8, fade_col)[
            ["player_id", fade_col, "q4_vs_q1_pts_ratio", "b2b_pts_delta"]
        ]
        print("--- Top Q4 faders (lowest q4_fade_pts_abs) ---")
        for r in worst.itertuples(index=False):
            print(f"  pid={r.player_id}  q4_fade={r.q4_fade_pts_abs:.2f}  "
                  f"q4/q1={getattr(r,'q4_vs_q1_pts_ratio','N/A')}  "
                  f"b2b_delta={r.b2b_pts_delta}")

    # Sanity ranking: biggest home advantage (pts_delta_home_minus_road)
    home_col = "pts_delta_home_minus_road"
    if home_col in out.columns and out[home_col].notna().any():
        best_home = out.dropna(subset=[home_col]).nlargest(5, home_col)[
            ["player_id", home_col, "home_pts_pg", "road_pts_pg"]
        ]
        print()
        print("--- Biggest home pts advantage ---")
        for r in best_home.itertuples(index=False):
            print(f"  pid={r.player_id}  home_adv={r.pts_delta_home_minus_road:.2f}  "
                  f"home={r.home_pts_pg}  road={r.road_pts_pg}")


if __name__ == "__main__":
    main()
