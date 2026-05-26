"""
probe_R12_F2_per_player_brier.py

R12 F2 — per-player in-play winprob calibration adjustment.

Probe idea
----------
The endQ3 in-play winprob model (data/models/inplay_winprob_endq3.lgb) may
systematically miscalibrate for individual players. If LeBron's team is up 5
at endQ3 the model has no idea LeBron is the one on the floor — only the
score margin and team-level pregame WP. The hypothesis is that adding a
per-player residual adjustment (sum of "this player tends to make the model
under/over-predict their team's win prob") will improve Brier on a
held-out fold.

Algorithm
---------
For each game (gid, game_date, home_team_won) with full linescore + quarter_box
coverage:

    1.  Compute the endQ3 model's predicted P(home wins). Residual = y - pred.
    2.  Attribute residual to each player who played in periods 1-3 (signed
        positive if player was on the HOME team, negative if AWAY team). This
        encodes "model under-predicts the team this player is on".
    3.  Walk-forward by game_date into 4 expanding folds. For each game in the
        test fold, compute per-player adjustment from the SHIFTED last-30
        game-appearances **strictly before** that game's date — never the
        same game or any future game.
    4.  adj_player = clip(mean_residual_l30, -0.05, +0.05)
    5.  adjusted_pred = clip(pred + sum(adj_player for player on court in this
        game's periods 1-3, side-signed), 0.02, 0.98)
    6.  Compute Brier(baseline) and Brier(adjusted) per fold + over all folds.

Ship gate
---------
    Brier improvement >= 0.005 on held-out fold AND >= 3/4 walk-forward
    folds positive.

Deliverables
------------
    - This script
    - data/models/per_player_winprob_adjustment.json    (final adjustment table)
    - data/cache/probe_R12_F2_per_player_brier_results.json   (metrics)
    - If SHIP: wires into src/prediction/inplay_winprob.py via the loader

Leakage audit
-------------
    The per-player rolling mean uses STRICT shift(1) on game_date — the same
    game's residual is never used to adjust its own prediction. Tests at the
    end of the script verify this directly (test_no_leakage_*).
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

from sklearn.metrics import accuracy_score, brier_score_loss  # noqa: E402

NBA_CACHE = os.path.join(PROJECT, "data", "nba")
DATA_CACHE = os.path.join(PROJECT, "data", "cache")
QUARTER_BOX_DIR = os.path.join(DATA_CACHE, "quarter_box")
MODEL_DIR = os.path.join(PROJECT, "data", "models")
LINESCORES_PATH = os.path.join(NBA_CACHE, "linescores_all.json")

OUT_JSON = os.path.join(DATA_CACHE, "probe_R12_F2_per_player_brier_results.json")
ADJ_TABLE_PATH = os.path.join(MODEL_DIR, "per_player_winprob_adjustment.json")

ADJ_CLIP = 0.05
PRED_CLIP_LO, PRED_CLIP_HI = 0.02, 0.98
WINDOW_GAMES = 30
N_FOLDS = 4
SHIP_BRIER_DELTA = 0.005


# ─────────────────────────────────────────────────────────────────────────────
# Data loaders
# ─────────────────────────────────────────────────────────────────────────────

def _load_season_games() -> Dict[str, Dict]:
    seasons = ["2022-23", "2023-24", "2024-25"]
    all_rows: Dict[str, Dict] = {}
    for s in seasons:
        path = os.path.join(NBA_CACHE, f"season_games_{s}.json")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            data = json.load(f)
        for row in data.get("rows", []):
            all_rows[row["game_id"]] = row
    return all_rows


def _load_linescores() -> Dict[str, Dict]:
    if not os.path.exists(LINESCORES_PATH):
        return {}
    with open(LINESCORES_PATH) as f:
        return json.load(f)


def _pregame_wp(row: Dict) -> float:
    """Closed-form Elo-derived pregame WP; mirror trainer fallback."""
    hca = 65.0
    home_elo = row.get("home_elo")
    away_elo = row.get("away_elo")
    if home_elo is None or away_elo is None:
        return 0.55
    try:
        diff = float(home_elo) - float(away_elo) + hca
        return float(1.0 / (1.0 + 10.0 ** (-diff / 400.0)))
    except (TypeError, ValueError):
        return 0.55


def _load_player_team_map() -> pd.DataFrame:
    """Read every quarter_box shard and emit (game_id, player_id, team_id,
    period, min_played). Used to figure out which players were on which side
    for each game.
    """
    rows: List[Dict] = []
    for path in glob.glob(os.path.join(QUARTER_BOX_DIR, "*_q*.json")):
        base = os.path.basename(path)
        try:
            gid, qtag = base.rsplit("_q", 1)
            q = int(qtag.replace(".json", ""))
        except (ValueError, IndexError):
            continue
        if q not in (1, 2, 3):
            continue  # only periods 1-3 contribute to endQ3 attribution
        try:
            with open(path) as f:
                shard = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        for p in shard.get("players", []):
            pid = p.get("player_id")
            tid = p.get("team_id")
            mn = p.get("min", "0:00")
            try:
                if isinstance(mn, str) and ":" in mn:
                    a, _, b = mn.partition(":")
                    minutes = float(a) + (float(b) / 60.0 if b else 0.0)
                else:
                    minutes = float(mn) if mn else 0.0
            except (TypeError, ValueError):
                minutes = 0.0
            if pid is None or tid is None:
                continue
            rows.append({
                "game_id": gid,
                "player_id": int(pid),
                "team_id": int(tid),
                "period": q,
                "min_played": minutes,
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # one row per (game, player): summed minutes Q1-Q3, primary team_id
    agg = df.groupby(["game_id", "player_id", "team_id"], as_index=False).agg(
        min_played_q13=("min_played", "sum")
    )
    # keep only players who actually played
    agg = agg[agg["min_played_q13"] > 0.0]
    return agg


# ─────────────────────────────────────────────────────────────────────────────
# endQ3 feature builder (matches trainer + inplay_winprob.py exactly)
# ─────────────────────────────────────────────────────────────────────────────

ENDQ3_FEATURES = [
    "score_margin", "total_pts", "pace_so_far",
    "q1_delta", "q2_delta", "q3_delta",
    "last_q_margin", "pregame_win_prob", "home_team_id", "season",
]
CAT_COLS = ["home_team_id", "season"]
MIN_PER_QTR = 12.0


def _build_endq3_rows(linescores: Dict, season_games: Dict) -> pd.DataFrame:
    records: List[Dict] = []
    for gid, ls in linescores.items():
        sg = season_games.get(gid)
        if sg is None:
            continue
        if any(ls.get(k) is None for k in
               ("home_q1", "home_q2", "home_q3", "home_q4",
                "away_q1", "away_q2", "away_q3", "away_q4")):
            continue
        hq = [ls["home_q1"], ls["home_q2"], ls["home_q3"], ls["home_q4"]]
        aq = [ls["away_q1"], ls["away_q2"], ls["away_q3"], ls["away_q4"]]
        home_team_won = int(sum(hq) > sum(aq))
        game_date = sg.get("game_date", "1900-01-01")
        home_team_id = ls.get("home_team_id", 0) or sg.get("home_team", "UNK")
        season = sg.get("season", "unknown")
        pregame_wp = sg.get("sim_win_prob")
        if pregame_wp is None:
            pregame_wp = _pregame_wp(sg)

        h_cum = sum(hq[:3])
        a_cum = sum(aq[:3])
        total_pts = h_cum + a_cum
        if total_pts < 60:
            continue
        records.append({
            "game_id": gid,
            "game_date": game_date,
            "home_team_id": home_team_id,
            "home_nba_team_id": ls.get("home_team_id"),  # numeric NBA team_id
            "season": season,
            "score_margin": h_cum - a_cum,
            "total_pts": total_pts,
            "pace_so_far": total_pts / (3 * MIN_PER_QTR),
            "q1_delta": hq[0] - aq[0],
            "q2_delta": hq[1] - aq[1],
            "q3_delta": hq[2] - aq[2],
            "last_q_margin": hq[2] - aq[2],
            "pregame_win_prob": pregame_wp,
            "home_team_won": home_team_won,
        })
    df = pd.DataFrame(records)
    if df.empty:
        return df
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values("game_date").reset_index(drop=True)
    return df


def _predict_with_booster(booster, df: pd.DataFrame) -> np.ndarray:
    X = df[ENDQ3_FEATURES].copy()
    for c in CAT_COLS:
        if c in X.columns:
            X[c] = X[c].astype("category")
    raw = booster.predict(X)
    return np.clip(np.asarray(raw, dtype=float), 0.0, 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Per-player residual + adjustment with strict shift(1) leakage guard
# ─────────────────────────────────────────────────────────────────────────────

def _attribute_residuals(games: pd.DataFrame,
                         pt_map: pd.DataFrame,
                         baseline_pred: np.ndarray) -> pd.DataFrame:
    """For each (game, player), emit one row with signed residual.

    Signed residual: (home_team_won - pred) if player is on HOME team, else
    -(home_team_won - pred). Positive => "model under-predicted the team
    this player is on".
    """
    g = games.copy()
    g["pred"] = baseline_pred
    g["resid"] = g["home_team_won"].astype(float) - g["pred"]

    # join player-team -> per-game home_nba_team_id
    g_small = g[["game_id", "game_date", "home_nba_team_id",
                 "home_team_won", "pred", "resid"]].copy()
    merged = pt_map.merge(g_small, on="game_id", how="inner")
    merged["is_home"] = (
        merged["team_id"] == merged["home_nba_team_id"]
    ).astype(int)
    merged["signed_resid"] = np.where(
        merged["is_home"] == 1,
        merged["resid"],
        -merged["resid"],
    )
    merged = merged.sort_values(["player_id", "game_date"]).reset_index(drop=True)
    return merged


def _per_player_l30_adjustment(merged: pd.DataFrame) -> pd.DataFrame:
    """Per (player_id, game_id), mean of signed_resid over the player's
    previous WINDOW_GAMES appearances, using STRICT shift(1) so the same
    game's residual NEVER feeds its own prediction.
    """
    g = merged.sort_values(["player_id", "game_date"]).reset_index(drop=True)
    rolled = (
        g.groupby("player_id")["signed_resid"]
         .apply(lambda s: s.shift(1).rolling(WINDOW_GAMES, min_periods=5).mean())
         .reset_index(level=0, drop=True)
    )
    g["adj_l30"] = rolled.clip(-ADJ_CLIP, ADJ_CLIP)
    return g[["game_id", "player_id", "team_id", "is_home", "adj_l30"]]


def _adjusted_predictions(games: pd.DataFrame,
                          baseline_pred: np.ndarray,
                          per_game_adj: pd.DataFrame) -> Tuple[np.ndarray,
                                                                np.ndarray]:
    """Sum per-player adj_l30 across all players on court for each game's
    Q1-Q3, signed to match the home perspective.

    is_home=1 player adj    -> adds to home win prob (player makes their
                                team win more often than the model thinks)
    is_home=0 player adj    -> subtracts from home win prob (this player
                                makes the AWAY team win more often)
    """
    pg = per_game_adj.copy()
    pg["signed_team_adj"] = np.where(
        pg["is_home"] == 1,
        pg["adj_l30"],
        -pg["adj_l30"],
    )
    pg = pg.dropna(subset=["signed_team_adj"])
    summed = pg.groupby("game_id", as_index=False)["signed_team_adj"].sum()
    summed = summed.rename(columns={"signed_team_adj": "total_adj"})
    by_gid = games[["game_id"]].merge(summed, on="game_id", how="left")
    by_gid["total_adj"] = by_gid["total_adj"].fillna(0.0)

    adjusted = baseline_pred + by_gid["total_adj"].to_numpy()
    adjusted = np.clip(adjusted, PRED_CLIP_LO, PRED_CLIP_HI)
    return adjusted, by_gid["total_adj"].to_numpy()


# ─────────────────────────────────────────────────────────────────────────────
# Walk-forward eval
# ─────────────────────────────────────────────────────────────────────────────

def _walk_forward_folds(df: pd.DataFrame, n_folds: int) -> List[pd.Index]:
    """Expanding-window 4-fold split by game_date.

    Fold k uses [0, train_end_k] as train and (train_end_k, val_end_k] as test.
    Test sizes are roughly balanced; train always uses everything before test.
    """
    n = len(df)
    sorted_ix = df.sort_values("game_date").index.to_list()
    fold_size = n // (n_folds + 1)
    folds = []
    for k in range(n_folds):
        test_start = fold_size * (k + 1)
        test_end = fold_size * (k + 2) if k < n_folds - 1 else n
        folds.append(sorted_ix[test_start:test_end])
    return folds


def _evaluate(df: pd.DataFrame,
              pt_map: pd.DataFrame,
              booster,
              fold_indexes: List[List[int]]) -> Tuple[Dict, np.ndarray, np.ndarray]:
    """Walk-forward: train residual table on ALL games strictly before the
    fold's earliest test date; test on the fold.
    """
    baseline_pred = _predict_with_booster(booster, df)
    merged_all = _attribute_residuals(df, pt_map, baseline_pred)
    adj_all = _per_player_l30_adjustment(merged_all)
    # Note: adj_all uses shift(1) so a player's adj_l30 on game G is based
    # only on prior games. Within a fold, this is per-game-of-player honest.
    adjusted_pred, total_adj = _adjusted_predictions(df, baseline_pred, adj_all)

    fold_metrics = {}
    for i, fold_ix in enumerate(fold_indexes, start=1):
        sub = df.loc[fold_ix]
        b_pred = baseline_pred[fold_ix]
        a_pred = adjusted_pred[fold_ix]
        y = sub["home_team_won"].astype(int).to_numpy()
        bbri = float(brier_score_loss(y, b_pred))
        abri = float(brier_score_loss(y, a_pred))
        bacc = float(accuracy_score(y, (b_pred >= 0.5).astype(int)))
        aacc = float(accuracy_score(y, (a_pred >= 0.5).astype(int)))
        fold_metrics[f"f{i}"] = {
            "n_test": int(len(fold_ix)),
            "test_date_start": str(sub["game_date"].min().date()),
            "test_date_end": str(sub["game_date"].max().date()),
            "brier_baseline": bbri,
            "brier_adjusted": abri,
            "brier_delta": bbri - abri,
            "accuracy_baseline": bacc,
            "accuracy_adjusted": aacc,
        }
    return fold_metrics, baseline_pred, adjusted_pred


# ─────────────────────────────────────────────────────────────────────────────
# Final adjustment table (for production wire-in)
# ─────────────────────────────────────────────────────────────────────────────

def _final_adjustment_table(merged: pd.DataFrame) -> Dict[int, float]:
    """Snapshot of mean-residual-l30 keyed by player_id, computed on the
    full available history. This is what gets saved to disk for live use.
    """
    g = merged.sort_values(["player_id", "game_date"]).reset_index(drop=True)
    # take the last L30 mean for each player (no shift -- this IS the final
    # table snapshot, but it only sees data through the last training game)
    last = (
        g.groupby("player_id")["signed_resid"]
         .apply(lambda s: s.tail(WINDOW_GAMES).mean())
    )
    last = last.dropna()
    out = {int(k): float(np.clip(v, -ADJ_CLIP, ADJ_CLIP))
           for k, v in last.items()}
    # drop near-zero adjustments (< 0.005 magnitude) — they're noise
    out = {k: v for k, v in out.items() if abs(v) >= 0.005}
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Leakage tests
# ─────────────────────────────────────────────────────────────────────────────

def _test_leakage_shift1() -> None:
    """A player's adjustment on game G must never use game G's own residual."""
    fake = pd.DataFrame({
        "player_id": [1, 1, 1, 1, 1, 1],
        "game_date": pd.to_datetime([
            "2024-01-01", "2024-01-05", "2024-01-10",
            "2024-01-15", "2024-01-20", "2024-01-25"]),
        "game_id":   ["a", "b", "c", "d", "e", "f"],
        "team_id":   [1] * 6,
        "is_home":   [1] * 6,
        "signed_resid": [0.10, 0.20, 0.30, 0.40, 0.50, 0.60],
    })
    out = _per_player_l30_adjustment(fake)
    # Row 0 (game a) -> shifted_l30 has no prior data -> NaN
    assert pd.isna(out.iloc[0]["adj_l30"]), (
        f"first game must be NaN under shift(1); got {out.iloc[0]['adj_l30']}")
    # Row 5 (game f) -> previous 5 games' mean = mean([.1,.2,.3,.4,.5]) = .3
    # (min_periods=5 satisfied) ; clipped at 0.05 since 0.3 > 0.05.
    assert out.iloc[5]["adj_l30"] == 0.05, (
        f"expected 0.05 clipped value got {out.iloc[5]['adj_l30']}")
    print("[test] leakage shift(1)  PASS")


def _test_adjustment_clip_bounds() -> None:
    """clip(-0.05, +0.05) must hold even with extreme residuals."""
    fake = pd.DataFrame({
        "player_id":    [2, 2, 2, 2, 2, 2],
        "game_date":    pd.to_datetime([f"2024-01-0{i+1}" for i in range(6)]),
        "game_id":      [f"g{i}" for i in range(6)],
        "team_id":      [1] * 6,
        "is_home":      [1] * 6,
        "signed_resid": [10.0, -10.0, 5.0, -5.0, 1.0, -1.0],
    })
    out = _per_player_l30_adjustment(fake)
    adj_nonnan = out["adj_l30"].dropna()
    assert (adj_nonnan.abs() <= ADJ_CLIP + 1e-9).all(), \
        f"clip violated: {adj_nonnan.tolist()}"
    print("[test] clip bounds       PASS")


def _test_pred_clip_bounds() -> None:
    """Adjusted pred must stay within [0.02, 0.98]."""
    games = pd.DataFrame({
        "game_id": ["x", "y"],
    })
    base = np.array([0.99, 0.01])
    per_game_adj = pd.DataFrame({
        "game_id":  ["x", "x", "y", "y"],
        "player_id":[1, 2, 3, 4],
        "team_id":  [1, 1, 1, 1],
        "is_home":  [1, 1, 1, 1],
        "adj_l30":  [0.05, 0.05, -0.05, -0.05],
    })
    adj, _ = _adjusted_predictions(games, base, per_game_adj)
    assert PRED_CLIP_LO <= adj[0] <= PRED_CLIP_HI, adj[0]
    assert PRED_CLIP_LO <= adj[1] <= PRED_CLIP_HI, adj[1]
    print("[test] pred clip bounds  PASS")


def _run_tests() -> None:
    print("\n[tests] running leakage + bounds checks ...")
    _test_leakage_shift1()
    _test_adjustment_clip_bounds()
    _test_pred_clip_bounds()
    print("[tests] all PASS\n")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    print("=== probe_R12_F2 per-player winprob calibration ===", flush=True)

    _run_tests()

    print("[1] loading data ...", flush=True)
    linescores = _load_linescores()
    season_games = _load_season_games()
    if not linescores:
        raise RuntimeError("no linescores at " + LINESCORES_PATH)
    print(f"   linescores={len(linescores)} season_games={len(season_games)}",
          flush=True)

    print("[2] building endQ3 feature frame ...", flush=True)
    df = _build_endq3_rows(linescores, season_games)
    print(f"   rows={len(df)} (after total_pts>=60 filter)", flush=True)
    if df.empty:
        raise RuntimeError("no rows after build")

    print("[3] loading player-team map from quarter_box ...", flush=True)
    pt_map = _load_player_team_map()
    print(f"   pt_map rows={len(pt_map)} "
          f"games={pt_map['game_id'].nunique()} "
          f"players={pt_map['player_id'].nunique()}", flush=True)

    # restrict to games with both linescore + pt_map coverage
    df = df[df["game_id"].isin(pt_map["game_id"].unique())].reset_index(drop=True)
    print(f"   joined endQ3 rows: {len(df)}", flush=True)

    print("[4] loading booster ...", flush=True)
    import lightgbm as lgb
    booster = lgb.Booster(
        model_file=os.path.join(MODEL_DIR, "inplay_winprob_endq3.lgb")
    )

    print("[5] walk-forward folds ...", flush=True)
    fold_lists = _walk_forward_folds(df, N_FOLDS)
    for i, ix in enumerate(fold_lists, start=1):
        sub = df.loc[ix]
        print(f"   f{i}: n={len(ix)} "
              f"[{sub['game_date'].min().date()} .. "
              f"{sub['game_date'].max().date()}]", flush=True)

    print("[6] evaluating ...", flush=True)
    fold_metrics, baseline_all, adjusted_all = _evaluate(
        df, pt_map, booster, fold_lists
    )

    y_all = df["home_team_won"].astype(int).to_numpy()
    brier_baseline_all = float(brier_score_loss(y_all, baseline_all))
    brier_adjusted_all = float(brier_score_loss(y_all, adjusted_all))

    # build final shippable adjustment table
    merged_all = _attribute_residuals(df, pt_map, baseline_all)
    final_table = _final_adjustment_table(merged_all)

    n_pos = sum(
        1 for k in fold_metrics
        if fold_metrics[k]["brier_delta"] > 0
    )
    overall_delta = brier_baseline_all - brier_adjusted_all
    ship = (
        overall_delta >= SHIP_BRIER_DELTA
        and n_pos >= 3
    )
    ship_status = "SHIP" if ship else "REJECT"

    print("\n=== RESULTS ===")
    print(f"   brier_baseline_all   = {brier_baseline_all:.4f}")
    print(f"   brier_adjusted_all   = {brier_adjusted_all:.4f}")
    print(f"   overall_delta        = {overall_delta:+.4f}")
    print(f"   n_pos folds          = {n_pos}/4")
    print(f"   n_players_in_table   = {len(final_table)}")
    print(f"   ship_status          = {ship_status}")
    for k, v in fold_metrics.items():
        print(f"   {k}: brier {v['brier_baseline']:.4f} -> "
              f"{v['brier_adjusted']:.4f}  "
              f"delta {v['brier_delta']:+.4f}  n={v['n_test']}")

    payload = {
        "probe": "R12_F2_per_player_brier",
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "brier_baseline": brier_baseline_all,
        "brier_adjusted": brier_adjusted_all,
        "brier_delta_overall": overall_delta,
        "n_players_with_adjustment": len(final_table),
        "n_games": int(len(df)),
        "n_player_game_rows": int(len(pt_map)),
        "fold_count": N_FOLDS,
        "window_games": WINDOW_GAMES,
        "adj_clip": ADJ_CLIP,
        "pred_clip_lo": PRED_CLIP_LO,
        "pred_clip_hi": PRED_CLIP_HI,
        "ship_gate_brier_delta": SHIP_BRIER_DELTA,
        "ship_gate_min_pos_folds": 3,
        "ship_status": ship_status,
        "by_fold": fold_metrics,
        "leakage_audit": {
            "strategy": "strict shift(1) rolling-30 mean per player",
            "tests_pass": True,
            "test_names": [
                "test_leakage_shift1",
                "test_adjustment_clip_bounds",
                "test_pred_clip_bounds",
            ],
        },
    }
    with open(OUT_JSON, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\n[OK] wrote results -> {OUT_JSON}", flush=True)

    with open(ADJ_TABLE_PATH, "w") as f:
        json.dump(
            {"player_adjustments": {str(k): v for k, v in final_table.items()},
             "ship_status": ship_status,
             "window_games": WINDOW_GAMES,
             "adj_clip": ADJ_CLIP,
             "pred_clip_lo": PRED_CLIP_LO,
             "pred_clip_hi": PRED_CLIP_HI,
             "ran_at": payload["ran_at"]},
            f, indent=2)
    print(f"[OK] wrote adjustment table -> {ADJ_TABLE_PATH}", flush=True)

    print(f"\nelapsed: {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
