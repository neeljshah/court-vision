"""
iter76_inplay_mid_quarter_snapshot.py
─────────────────────────────────────
Iter 76: MID-quarter snapshot probe at Q4 6:00 remaining (= 6 min elapsed in Q4).

Hypothesis (per Iter 64/72 saturation lesson): microstructure features
saturate at end-of-quarter boundaries because the summary stats already
encode the prior-quarter trajectory by construction. But at MID-quarter
snapshots, the existing summary stats (`score_margin`, `total_pts`,
`last_q_margin`) do NOT yet reflect the in-progress quarter. So PBP
microstructure for the in-progress quarter (runs, points, TOs, lead
changes) should carry signal the model can't extract from the
incomplete-quarter snapshot.

PROBE SCOPE (tight): just `q4_6min` (start of Q4 + 6 min played = 6:00
remaining). Closest snapshot to the endQ3 model we already know works,
and in-game betting volume peaks here.

PBP cache structure: `data/nba/pbp_<game_id>_p4.json` events in
chronological order, `game_clock_sec` counts UP from 0 (period start)
to 720 (period end). Q4 6:00 remaining ⇒ first event where
`game_clock_sec >= 360`.

Features (11):
  Base (5):
    score_margin           (home - away cum at snapshot)
    total_pts              (home + away cum at snapshot)
    pace_so_far            (total_pts per minute of game time elapsed)
    pregame_win_prob       (corrected: 1 - sim_win_prob per Iter 74)
    last_q_margin          (Q3 margin = home_q3 - away_q3)
  New mid-quarter microstructure (6):
    q4_run_so_far          (max scoring run since Q4 started; signed +home / -away)
    q4_pts_so_far_home     (home Q4 pts thru 6:00 mark)
    q4_pts_so_far_away     (away Q4 pts thru 6:00 mark)
    q4_lead_changes_so_far (sign-flips of cum margin since Q4 started)
    q4_to_so_far_home      (home turnovers in Q4 thru snapshot)
    q4_to_so_far_away      (away turnovers in Q4 thru snapshot)

Baselines (must beat both):
  pregame:  pregame_win_prob alone (Pinnacle-class)
  sigmoid:  sigmoid(score_margin / 4) — more aggressive than endQ3's /6
            because we're 30 of 48 min in (well past the endQ3 mark).

Ship gate:
  WF Brier <= MIN(pregame, sigmoid) − 0.005 on ≥3/4 folds
  AND mean Brier < 0.10.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ── paths ─────────────────────────────────────────────────────────────────────
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

NBA_CACHE = os.path.join(PROJECT, "data", "nba")
DATA_CACHE = os.path.join(PROJECT, "data", "cache")
MODELS_DIR = os.path.join(PROJECT, "data", "models")
FEATURES_PARQUET = os.path.join(DATA_CACHE, "inplay_midquarter_features.parquet")
OUT_JSON = os.path.join(DATA_CACHE, "iter76_inplay_midquarter_results.json")

os.makedirs(DATA_CACHE, exist_ok=True)

SNAPSHOT_NAME = "q4_6min"
SNAPSHOT_PERIOD = 4
SNAPSHOT_ELAPSED_SEC = 360   # 6 min played ⇒ 6:00 remaining
QUARTER_LEN_SEC = 720
MINUTES_PER_QUARTER = 12.0

N_FOLDS = 4
RANDOM_SEED = 42

# Iter 68 tight HPs (closest analogue is endQ3 since q4_6min is mid-Q4):
#   lr=0.03, num_leaves=15, min_child_samples=20 (per task spec)
HP = {
    "n_estimators": 300,
    "learning_rate": 0.03,
    "num_leaves": 15,
    "min_child_samples": 20,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "random_state": RANDOM_SEED,
}

FEATURE_COLS = [
    "score_margin",
    "total_pts",
    "pace_so_far",
    "pregame_win_prob",
    "last_q_margin",
    "q4_run_so_far",
    "q4_pts_so_far_home",
    "q4_pts_so_far_away",
    "q4_lead_changes_so_far",
    "q4_to_so_far_home",
    "q4_to_so_far_away",
]
CAT_COLS: List[str] = []

SHIP_MIN_FOLDS_IMPROVED = 3
SHIP_DELTA = -0.005
SHIP_MEAN_BRIER_MAX = 0.10

# Cap to last 2 seasons if PBP parsing is too slow.
SEASONS = ["2022-23", "2023-24", "2024-25"]


# ── PBP parsing ───────────────────────────────────────────────────────────────

def _parse_score(score_str: str) -> Optional[Tuple[int, int]]:
    if not score_str or "-" not in score_str:
        return None
    try:
        h_str, a_str = score_str.split("-", 1)
        return int(h_str), int(a_str)
    except (ValueError, AttributeError):
        return None


def extract_q4_state_at_6min(
    pbp_p4: List[Dict],
    home_pts_through_q3: int,
    away_pts_through_q3: int,
) -> Optional[Dict[str, float]]:
    """Compute the snapshot state at Q4 6:00 remaining (game_clock_sec >= 360).

    Returns dict with:
      home_pts_at_snap, away_pts_at_snap     (cumulative game pts at snap)
      q4_pts_so_far_home, q4_pts_so_far_away (Q4-only pts up to snap)
      q4_run_so_far                          (signed max consecutive run in Q4)
      q4_lead_changes_so_far                 (since cumulative margin sign flips)
      q4_to_so_far_home, q4_to_so_far_away
    Returns None if Q4 PBP is missing/empty or snapshot not reachable.
    """
    if not pbp_p4:
        return None

    # Identify home/away team_abbrev from votes on positive score deltas.
    prev_score = (home_pts_through_q3, away_pts_through_q3)
    team_home_votes: Dict[str, int] = {}
    team_away_votes: Dict[str, int] = {}

    for ev in pbp_p4:
        s = _parse_score(ev.get("score", ""))
        if s is None:
            continue
        h_now, a_now = s
        ta = ev.get("team_abbrev") or ""
        if ta:
            if h_now > prev_score[0]:
                team_home_votes[ta] = team_home_votes.get(ta, 0) + (h_now - prev_score[0])
            if a_now > prev_score[1]:
                team_away_votes[ta] = team_away_votes.get(ta, 0) + (a_now - prev_score[1])
        prev_score = s

    home_team = max(team_home_votes.items(), key=lambda kv: kv[1])[0] if team_home_votes else None
    away_team = max(team_away_votes.items(), key=lambda kv: kv[1])[0] if team_away_votes else None

    # Walk events forward, tracking state up to first event with clock >= 360.
    home_run = 0
    away_run = 0
    # Track max ABS run since Q4 start; sign + if home, − if away.
    max_home_run = 0
    max_away_run = 0
    q4_home_pts = 0
    q4_away_pts = 0
    lead_changes = 0
    prev_margin_sign: Optional[int] = None
    # Initialize prev_margin_sign with the margin at start of Q4 (the score at
    # period-start). Lead-changes count flips that happen WITHIN Q4.
    init_margin = home_pts_through_q3 - away_pts_through_q3
    if init_margin > 0:
        prev_margin_sign = 1
    elif init_margin < 0:
        prev_margin_sign = -1

    home_tos = 0
    away_tos = 0
    h_running = home_pts_through_q3
    a_running = away_pts_through_q3
    found_snapshot = False
    h_at_snap = home_pts_through_q3
    a_at_snap = away_pts_through_q3

    for ev in pbp_p4:
        clock = int(ev.get("game_clock_sec", 0) or 0)
        # The snapshot is the state JUST BEFORE the first event at clock >= 360.
        # All events with clock < 360 have already happened.
        if clock >= SNAPSHOT_ELAPSED_SEC:
            found_snapshot = True
            break

        et = ev.get("event_type", -1)
        ta = ev.get("team_abbrev") or ""
        s = _parse_score(ev.get("score", ""))
        if s is None:
            # turnovers (et==5) may have no score progression
            if et == 5 and ta:
                if home_team and ta == home_team:
                    home_tos += 1
                elif away_team and ta == away_team:
                    away_tos += 1
            continue

        h_now, a_now = s
        h_delta = h_now - h_running
        a_delta = a_now - a_running

        if h_delta > 0:
            home_run += h_delta
            away_run = 0
            q4_home_pts += h_delta
        if a_delta > 0:
            away_run += a_delta
            home_run = 0
            q4_away_pts += a_delta

        if home_run > max_home_run:
            max_home_run = home_run
        if away_run > max_away_run:
            max_away_run = away_run

        # Lead change in cumulative margin
        margin = h_now - a_now
        if margin > 0:
            sign = 1
        elif margin < 0:
            sign = -1
        else:
            sign = 0
        if prev_margin_sign is not None and sign != 0 and prev_margin_sign != 0 and sign != prev_margin_sign:
            lead_changes += 1
        if sign != 0:
            prev_margin_sign = sign

        # Turnovers
        if et == 5 and ta:
            if home_team and ta == home_team:
                home_tos += 1
            elif away_team and ta == away_team:
                away_tos += 1

        h_running = h_now
        a_running = a_now
        h_at_snap = h_now
        a_at_snap = a_now

    if not found_snapshot:
        # Snapshot not reached (e.g., game ended before 6:00 elapsed in Q4 — shouldn't happen)
        return None

    # Signed run feature: + if last big run was home, - if away.
    if max_home_run >= max_away_run:
        q4_run_signed = float(max_home_run)
    else:
        q4_run_signed = float(-max_away_run)

    return {
        "home_pts_at_snap": float(h_at_snap),
        "away_pts_at_snap": float(a_at_snap),
        "q4_pts_so_far_home": float(q4_home_pts),
        "q4_pts_so_far_away": float(q4_away_pts),
        "q4_run_so_far": q4_run_signed,
        "q4_lead_changes_so_far": float(lead_changes),
        "q4_to_so_far_home": float(home_tos),
        "q4_to_so_far_away": float(away_tos),
    }


# ── data loaders ──────────────────────────────────────────────────────────────

def load_linescores() -> Dict[str, Dict]:
    with open(os.path.join(NBA_CACHE, "linescores_all.json")) as f:
        return json.load(f)


def load_season_games() -> Dict[str, Dict]:
    all_rows: Dict[str, Dict] = {}
    for s in SEASONS:
        path = os.path.join(NBA_CACHE, f"season_games_{s}.json")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            data = json.load(f)
        for row in data.get("rows", []):
            all_rows[row["game_id"]] = row
    return all_rows


def _pregame_wp_from_sg(sg: Dict) -> float:
    """Return pregame home-win prob, polarity-CORRECTED per Iter 74.

    sim_win_prob in season_games is stored from the visitor perspective
    (Iter 74 finding). So the home-win prob = 1 - sim_win_prob.
    """
    wp = sg.get("sim_win_prob")
    if wp is not None:
        return 1.0 - float(wp)
    # Fallback: ELO with home court advantage
    hca = 65.0
    home_elo = sg.get("home_elo")
    away_elo = sg.get("away_elo")
    if home_elo is None or away_elo is None:
        return 0.55
    try:
        diff = float(home_elo) - float(away_elo) + hca
        return float(1.0 / (1.0 + 10.0 ** (-diff / 400.0)))
    except (TypeError, ValueError):
        return 0.55


def build_features() -> pd.DataFrame:
    """Build the per-game snapshot row table for q4_6min."""
    linescores = load_linescores()
    season_games = load_season_games()
    print(f"  linescores={len(linescores)}  season_games={len(season_games)}", flush=True)

    rows: List[Dict] = []
    n_processed = 0
    n_missing_pbp = 0
    n_no_snapshot = 0
    n_incomplete_linescore = 0
    t0 = time.time()

    for gid, sg in season_games.items():
        ls = linescores.get(gid)
        if ls is None:
            n_incomplete_linescore += 1
            continue
        required_qs = ["home_q1", "home_q2", "home_q3", "home_q4",
                       "away_q1", "away_q2", "away_q3", "away_q4"]
        if any(ls.get(k) is None for k in required_qs):
            n_incomplete_linescore += 1
            continue

        hq = [ls["home_q1"], ls["home_q2"], ls["home_q3"], ls["home_q4"]]
        aq = [ls["away_q1"], ls["away_q2"], ls["away_q3"], ls["away_q4"]]
        home_total = sum(hq)
        away_total = sum(aq)
        home_won = int(home_total > away_total)

        home_pts_q3 = sum(hq[:3])
        away_pts_q3 = sum(aq[:3])
        last_q_margin = hq[2] - aq[2]  # Q3 margin

        # Load Q4 PBP
        pbp_path = os.path.join(NBA_CACHE, f"pbp_{gid}_p4.json")
        if not os.path.exists(pbp_path):
            n_missing_pbp += 1
            continue
        try:
            with open(pbp_path) as f:
                pbp_p4 = json.load(f)
        except (json.JSONDecodeError, OSError):
            n_missing_pbp += 1
            continue

        snap = extract_q4_state_at_6min(pbp_p4, home_pts_q3, away_pts_q3)
        if snap is None:
            n_no_snapshot += 1
            continue

        score_margin = snap["home_pts_at_snap"] - snap["away_pts_at_snap"]
        total_pts = snap["home_pts_at_snap"] + snap["away_pts_at_snap"]
        # 30 minutes elapsed at snapshot (3 quarters + 6 min)
        minutes_played = 3 * MINUTES_PER_QUARTER + 6.0
        pace_so_far = total_pts / minutes_played

        pregame_wp = _pregame_wp_from_sg(sg)
        game_date = sg.get("game_date", "1900-01-01")
        season = sg.get("season", "unknown")
        home_team_id = ls.get("home_team_id", 0) or sg.get("home_team", "UNK")

        rec = {
            "game_id": gid,
            "game_date": game_date,
            "season": season,
            "home_team_id": str(home_team_id),
            "score_margin": float(score_margin),
            "total_pts": float(total_pts),
            "pace_so_far": float(pace_so_far),
            "pregame_win_prob": float(pregame_wp),
            "last_q_margin": float(last_q_margin),
            "q4_run_so_far": snap["q4_run_so_far"],
            "q4_pts_so_far_home": snap["q4_pts_so_far_home"],
            "q4_pts_so_far_away": snap["q4_pts_so_far_away"],
            "q4_lead_changes_so_far": snap["q4_lead_changes_so_far"],
            "q4_to_so_far_home": snap["q4_to_so_far_home"],
            "q4_to_so_far_away": snap["q4_to_so_far_away"],
            "home_team_won": home_won,
        }
        rows.append(rec)
        n_processed += 1
        if n_processed % 500 == 0:
            print(f"    processed {n_processed} games  elapsed={time.time()-t0:.1f}s", flush=True)

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values(["game_date", "game_id"]).reset_index(drop=True)
    print(f"  coverage: {n_processed} games  "
          f"missing_pbp={n_missing_pbp}  no_snapshot={n_no_snapshot}  "
          f"incomplete_linescore={n_incomplete_linescore}", flush=True)
    return df


# ── walk-forward ──────────────────────────────────────────────────────────────

def walk_forward(df: pd.DataFrame, feature_cols: List[str]) -> Tuple[List[Dict], List[Dict]]:
    """4-fold expanding split. Returns (model_fold_results, baseline_fold_results).

    baseline_fold_results entries hold per-fold {pregame_brier, sigmoid_brier}
    on the same test slice as the model.
    """
    import lightgbm as lgb
    from sklearn.metrics import (accuracy_score, brier_score_loss,
                                 log_loss, roc_auc_score)
    n = len(df)
    min_train = int(n * 0.60)
    test_size = (n - min_train) // N_FOLDS
    model_out: List[Dict] = []
    base_out: List[Dict] = []

    for fold in range(N_FOLDS):
        train_end = min_train + fold * test_size
        test_start = train_end
        test_end = test_start + test_size if fold < N_FOLDS - 1 else n
        if train_end < 30 or test_start >= n:
            continue
        X_tr = df[feature_cols].iloc[:train_end].copy()
        y_tr = df["home_team_won"].iloc[:train_end]
        X_te = df[feature_cols].iloc[test_start:test_end].copy()
        y_te = df["home_team_won"].iloc[test_start:test_end]
        if len(X_te) < 10:
            continue

        model = lgb.LGBMClassifier(
            n_estimators=int(HP["n_estimators"]),
            learning_rate=float(HP["learning_rate"]),
            num_leaves=int(HP["num_leaves"]),
            min_child_samples=int(HP["min_child_samples"]),
            subsample=float(HP["subsample"]),
            colsample_bytree=float(HP["colsample_bytree"]),
            reg_alpha=float(HP["reg_alpha"]),
            reg_lambda=float(HP["reg_lambda"]),
            random_state=int(HP["random_state"]),
            n_jobs=4,
            verbose=-1,
        )
        model.fit(X_tr, y_tr)
        probs = model.predict_proba(X_te)[:, 1]
        preds = (probs >= 0.5).astype(int)
        probs_safe = np.clip(probs, 1e-6, 1 - 1e-6)
        y_arr = y_te.values
        try:
            auc = float(roc_auc_score(y_arr, probs))
        except ValueError:
            auc = float("nan")
        model_out.append({
            "fold": fold,
            "train_n": int(len(X_tr)),
            "test_n": int(len(X_te)),
            "brier": float(brier_score_loss(y_arr, probs)),
            "log_loss": float(log_loss(y_arr, probs_safe)),
            "auc": auc,
            "accuracy": float(accuracy_score(y_arr, preds)),
        })

        # Baselines on the SAME test slice.
        pregame_probs = df["pregame_win_prob"].iloc[test_start:test_end].clip(1e-6, 1 - 1e-6).values
        sigmoid_probs = 1.0 / (1.0 + np.exp(-(df["score_margin"].iloc[test_start:test_end].values / 4.0)))
        sigmoid_probs = np.clip(sigmoid_probs, 1e-6, 1 - 1e-6)
        base_out.append({
            "fold": fold,
            "test_n": int(len(X_te)),
            "pregame_brier": float(brier_score_loss(y_arr, pregame_probs)),
            "sigmoid_brier": float(brier_score_loss(y_arr, sigmoid_probs)),
        })
    return model_out, base_out


# ── full-data fit + integrity check ──────────────────────────────────────────

def train_full_and_save(df: pd.DataFrame, wf_stats: Dict[str, Any]) -> Dict[str, Any]:
    import lightgbm as lgb
    from sklearn.metrics import (accuracy_score, brier_score_loss,
                                 log_loss, roc_auc_score)

    X = df[FEATURE_COLS].copy()
    y = df["home_team_won"]

    model = lgb.LGBMClassifier(
        n_estimators=int(HP["n_estimators"]),
        learning_rate=float(HP["learning_rate"]),
        num_leaves=int(HP["num_leaves"]),
        min_child_samples=int(HP["min_child_samples"]),
        subsample=float(HP["subsample"]),
        colsample_bytree=float(HP["colsample_bytree"]),
        reg_alpha=float(HP["reg_alpha"]),
        reg_lambda=float(HP["reg_lambda"]),
        random_state=int(HP["random_state"]),
        n_jobs=4,
        verbose=-1,
    )
    model.fit(X, y)
    probs = model.predict_proba(X)[:, 1]
    preds = (probs >= 0.5).astype(int)
    probs_safe = np.clip(probs, 1e-6, 1 - 1e-6)
    in_sample = {
        "auc": float(roc_auc_score(y, probs)) if len(np.unique(y)) > 1 else float("nan"),
        "brier": float(brier_score_loss(y, probs)),
        "log_loss": float(log_loss(y, probs_safe)),
        "accuracy": float(accuracy_score(y, preds)),
    }

    out_lgb = os.path.join(MODELS_DIR, f"inplay_winprob_{SNAPSHOT_NAME}_v1.lgb")
    out_meta = os.path.join(MODELS_DIR, f"inplay_winprob_{SNAPSHOT_NAME}_v1_meta.json")
    booster = model.booster_
    booster.save_model(out_lgb)

    # pkl integrity check
    reloaded = lgb.Booster(model_file=out_lgb)
    probs_reload = reloaded.predict(X)
    max_diff = float(np.abs(probs - probs_reload).max())
    booster_n_features = int(reloaded.num_feature())
    n_features_in = int(model.n_features_in_)
    integrity_ok = (
        max_diff < 1e-6
        and n_features_in == len(FEATURE_COLS)
        and booster_n_features == len(FEATURE_COLS)
    )
    if not integrity_ok:
        try:
            os.remove(out_lgb)
        except OSError:
            pass
        raise RuntimeError(
            f"[INTEGRITY FAIL] {SNAPSHOT_NAME}: max_diff={max_diff:.6f} "
            f"n_features_in={n_features_in} booster_nfeat={booster_n_features} "
            f"vs feature_cols_len={len(FEATURE_COLS)}"
        )

    meta = {
        "snapshot": SNAPSHOT_NAME,
        "snapshot_period": SNAPSHOT_PERIOD,
        "snapshot_elapsed_sec": SNAPSHOT_ELAPSED_SEC,
        "variant": "v1_midquarter",
        "iter": "iter76",
        "feature_cols": FEATURE_COLS,
        "categorical_cols": CAT_COLS,
        "n_train_rows": int(len(X)),
        "n_features_in_": int(len(FEATURE_COLS)),
        "home_win_rate": float(y.mean()),
        "in_sample": in_sample,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "probe": "iter76_inplay_mid_quarter_snapshot",
        "hyperparams": HP,
        "wf_eval": wf_stats,
        "integrity": {
            "max_prob_diff_pkl_vs_inmemory": max_diff,
            "n_features_in": n_features_in,
            "booster_n_features": booster_n_features,
            "ok": integrity_ok,
        },
    }
    with open(out_meta, "w") as f:
        json.dump(meta, f, indent=2, default=str)
    print(f"    saved {out_lgb}", flush=True)
    print(f"    saved {out_meta}", flush=True)
    print(f"    PKL integrity: max_diff={max_diff:.2e}  "
          f"n_features_in={n_features_in}  booster_nfeat={booster_n_features}",
          flush=True)
    return meta


# ── orchestrator ─────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    print("=" * 70, flush=True)
    print(f"ITER 76: mid-quarter snapshot probe at {SNAPSHOT_NAME} "
          f"(period {SNAPSHOT_PERIOD}, elapsed {SNAPSHOT_ELAPSED_SEC}s)",
          flush=True)
    print(f"  features: {len(FEATURE_COLS)}", flush=True)
    print(f"  HPs: lr={HP['learning_rate']} nl={HP['num_leaves']} mcs={HP['min_child_samples']}", flush=True)
    print(f"  ship gate: WF Brier <= MIN(pregame, sigmoid) - {abs(SHIP_DELTA)} on "
          f">={SHIP_MIN_FOLDS_IMPROVED}/{N_FOLDS} folds AND mean<{SHIP_MEAN_BRIER_MAX}",
          flush=True)
    print("=" * 70, flush=True)

    print("\n[1] Building features ...", flush=True)
    if os.path.exists(FEATURES_PARQUET):
        print(f"    cache hit: {FEATURES_PARQUET}", flush=True)
        df = pd.read_parquet(FEATURES_PARQUET)
        df["game_date"] = pd.to_datetime(df["game_date"])
        df = df.sort_values(["game_date", "game_id"]).reset_index(drop=True)
    else:
        df = build_features()
        if df.empty:
            print("ERROR: no rows extracted — exiting with REVERT", flush=True)
            results = {
                "iter": "iter76_inplay_mid_quarter_snapshot",
                "snapshot": SNAPSHOT_NAME,
                "verdict": "REVERT",
                "reason": "no rows extracted — PBP parse blocker",
                "elapsed_s": float(time.time() - t0),
            }
            with open(OUT_JSON, "w") as f:
                json.dump(results, f, indent=2, default=str)
            return
        df.to_parquet(FEATURES_PARQUET, index=False)
        print(f"    wrote {FEATURES_PARQUET} ({len(df)} rows)", flush=True)

    n_games = len(df)
    home_wr = float(df["home_team_won"].mean())
    print(f"    rows: {n_games}  home_win_rate: {home_wr:.4f}", flush=True)

    print("\n[2] Walk-forward (4 expanding folds) ...", flush=True)
    model_folds, base_folds = walk_forward(df, FEATURE_COLS)
    model_briers = [f["brier"] for f in model_folds]
    pregame_briers = [b["pregame_brier"] for b in base_folds]
    sigmoid_briers = [b["sigmoid_brier"] for b in base_folds]
    model_mean = float(np.mean(model_briers)) if model_briers else float("nan")
    pregame_mean = float(np.mean(pregame_briers)) if pregame_briers else float("nan")
    sigmoid_mean = float(np.mean(sigmoid_briers)) if sigmoid_briers else float("nan")

    print(f"\n    model per-fold:   {[f'{b:.4f}' for b in model_briers]}", flush=True)
    print(f"    pregame per-fold: {[f'{b:.4f}' for b in pregame_briers]}", flush=True)
    print(f"    sigmoid per-fold: {[f'{b:.4f}' for b in sigmoid_briers]}", flush=True)
    print(f"\n    model mean:   {model_mean:.4f}", flush=True)
    print(f"    pregame mean: {pregame_mean:.4f}", flush=True)
    print(f"    sigmoid mean: {sigmoid_mean:.4f}", flush=True)

    # Per-fold ship check: model_brier <= min(pregame, sigmoid) + SHIP_DELTA
    folds_improved = 0
    fold_deltas = []
    for m, b in zip(model_briers, [min(p, s) for p, s in zip(pregame_briers, sigmoid_briers)]):
        delta = m - b
        fold_deltas.append(delta)
        if delta <= SHIP_DELTA:
            folds_improved += 1
    mean_min_baseline = float(np.mean([min(p, s) for p, s in zip(pregame_briers, sigmoid_briers)]))
    mean_delta = model_mean - mean_min_baseline

    print(f"\n    per-fold delta vs MIN(pregame, sigmoid): "
          f"{[f'{d:+.4f}' for d in fold_deltas]}", flush=True)
    print(f"    mean delta vs MIN baseline: {mean_delta:+.4f}", flush=True)
    print(f"    folds improved (delta <= {SHIP_DELTA}): "
          f"{folds_improved}/{len(fold_deltas)}", flush=True)

    ship = (
        folds_improved >= SHIP_MIN_FOLDS_IMPROVED
        and model_mean < SHIP_MEAN_BRIER_MAX
    )
    print(f"\n    SHIP? {ship}", flush=True)

    results: Dict[str, Any] = {
        "iter": "iter76_inplay_mid_quarter_snapshot",
        "snapshot": SNAPSHOT_NAME,
        "snapshot_period": SNAPSHOT_PERIOD,
        "snapshot_elapsed_sec": SNAPSHOT_ELAPSED_SEC,
        "run_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "random_seed": RANDOM_SEED,
        "n_folds": N_FOLDS,
        "feature_cols": FEATURE_COLS,
        "hyperparams": HP,
        "ship_gate": {
            "min_folds_improved": SHIP_MIN_FOLDS_IMPROVED,
            "delta_threshold": SHIP_DELTA,
            "max_mean_brier": SHIP_MEAN_BRIER_MAX,
            "baseline": "min(pregame, sigmoid) per fold",
        },
        "coverage": {
            "n_games_total": int(n_games),
            "home_win_rate": home_wr,
        },
        "model_fold_briers": model_briers,
        "pregame_fold_briers": pregame_briers,
        "sigmoid_fold_briers": sigmoid_briers,
        "model_mean_brier": model_mean,
        "pregame_mean_brier": pregame_mean,
        "sigmoid_mean_brier": sigmoid_mean,
        "fold_deltas_vs_min_baseline": fold_deltas,
        "mean_delta_vs_min_baseline": mean_delta,
        "folds_improved": folds_improved,
        "model_fold_detail": model_folds,
        "baseline_fold_detail": base_folds,
        "ships": ship,
    }

    if ship:
        print(f"\n[3] Training on FULL data + integrity check ...", flush=True)
        wf_stats = {
            "model_fold_briers": model_briers,
            "model_mean_brier": model_mean,
            "pregame_fold_briers": pregame_briers,
            "pregame_mean_brier": pregame_mean,
            "sigmoid_fold_briers": sigmoid_briers,
            "sigmoid_mean_brier": sigmoid_mean,
            "fold_deltas_vs_min_baseline": fold_deltas,
            "mean_delta_vs_min_baseline": mean_delta,
            "folds_improved": folds_improved,
        }
        train_meta = train_full_and_save(df, wf_stats)
        results["saved_meta"] = {
            "in_sample": train_meta.get("in_sample"),
            "integrity": train_meta.get("integrity"),
        }
        results["verdict"] = "SHIP"
        results["reason"] = (
            f"WF folds improved {folds_improved}/{N_FOLDS} (delta<={SHIP_DELTA}) "
            f"AND mean Brier {model_mean:.4f} < {SHIP_MEAN_BRIER_MAX}"
        )
    else:
        results["verdict"] = "REVERT"
        if folds_improved < SHIP_MIN_FOLDS_IMPROVED:
            results["reason"] = (
                f"only {folds_improved}/{N_FOLDS} folds improved vs MIN(pregame, sigmoid) "
                f"by >= {abs(SHIP_DELTA)}"
            )
        else:
            results["reason"] = (
                f"mean Brier {model_mean:.4f} >= {SHIP_MEAN_BRIER_MAX} ceiling"
            )

    results["elapsed_s"] = float(time.time() - t0)
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print("\n" + "=" * 70, flush=True)
    print(f"ITER 76 VERDICT: {results['verdict']}", flush=True)
    print(f"Reason: {results['reason']}", flush=True)
    print("=" * 70, flush=True)
    print(f"  Coverage: {n_games} games", flush=True)
    print(f"  Model:    {model_mean:.4f}", flush=True)
    print(f"  Pregame:  {pregame_mean:.4f}  (delta {model_mean - pregame_mean:+.4f})", flush=True)
    print(f"  Sigmoid:  {sigmoid_mean:.4f}  (delta {model_mean - sigmoid_mean:+.4f})", flush=True)
    print(f"  Min-base: {mean_min_baseline:.4f}  (delta {mean_delta:+.4f})", flush=True)
    print(f"  Folds improved: {folds_improved}/{N_FOLDS}", flush=True)
    print(f"  Elapsed: {results['elapsed_s']:.1f}s", flush=True)
    print(f"  Results: {OUT_JSON}", flush=True)


if __name__ == "__main__":
    main()
