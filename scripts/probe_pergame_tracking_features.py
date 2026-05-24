"""probe_pergame_tracking_features.py — cycle 84a (loop 5).

Standalone probe: does adding per-game playertrackv3 features
(prev-game touches, passes, contestedFGA, reboundChances) measurably
improve walk-forward + single-split MAE on the prop_pergame model
WITHOUT modifying production code?

DUAL GATE (cycle 45 lesson):
  - 4/4 walk-forward folds must show STRICT MAE improvement
  - production single-split MAE must STRICTLY decrease
Only then is this worth a real cycle. Otherwise: REJECT.

Scoped down per cycle-84a brief:
  - SINGLE season backfill (2024-25 only) for the new features
  - SINGLE stat probed first (AST — passes is mechanically upstream)
  - prev-game value only (cycle-6 lesson: rolling means caused covariate shift)

NO production code is touched. All wiring is in this script. Results
go to scripts/_results/probe_pergame_tracking_features.json.
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from datetime import datetime
from typing import Dict, List, Tuple

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns, _parse_date,
)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_OUT_PATH = os.path.join(PROJECT_DIR, "scripts", "_results",
                         "probe_pergame_tracking_features.json")

# The four features the research probe (cycle 78b) flagged as game-to-game
# variable (CoV 13-50%) and mechanically upstream of box stats.
_TRACK_RAW_COLS = (
    "touches",
    "passes",
    "contestedFieldGoalsAttempted",
    "reboundChancesTotal",
)
_TRACK_FEAT_NAMES = tuple(f"prev_track_{c}" for c in _TRACK_RAW_COLS)
_TRACK_DEFAULTS: Dict[str, float] = {n: 0.0 for n in _TRACK_FEAT_NAMES}

# Stats to probe in order — AST first (passes is upstream), then PTS as a
# control (large dollar impact). Each runs its own 4-fold WF.
_PROBE_STATS = ("ast", "pts")


# ── Build game_id ↔ (date_iso, sorted-team-pair) lookup ──────────────────────

def build_game_lookup() -> Dict[Tuple[str, Tuple[str, str]], str]:
    """Return {(date_iso, (team_a, team_b)): game_id} from season_games_*.json."""
    import glob
    mapping: Dict[Tuple[str, Tuple[str, str]], str] = {}
    for path in glob.glob(os.path.join(_NBA_CACHE, "season_games_*.json")):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        rows = d["rows"] if isinstance(d, dict) else d
        for r in rows:
            gid = str(r["game_id"]).zfill(10)
            date = str(r["game_date"])  # already ISO
            home, away = str(r["home_team"]), str(r["away_team"])
            mapping[(date, tuple(sorted([home, away])))] = gid
    return mapping


# ── Build per-(player_id, game_id) tracking lookup from cached v3 jsons ──────

def build_tracking_lookup() -> Dict[Tuple[int, str], Dict[str, float]]:
    """Return {(player_id, game_id): {touches, passes, contFGA, rebChances}}."""
    import glob
    lookup: Dict[Tuple[int, str], Dict[str, float]] = {}
    for path in glob.glob(os.path.join(_NBA_CACHE, "playertrackv3_*.json")):
        gid_from_path = (
            os.path.basename(path)
            .replace("playertrackv3_", "")
            .replace(".json", "")
            .zfill(10)
        )
        try:
            with open(path, encoding="utf-8") as f:
                rows = json.load(f)
        except Exception:
            continue
        if not isinstance(rows, list):
            continue
        for r in rows:
            try:
                pid = int(r.get("personId") or 0)
            except (TypeError, ValueError):
                continue
            if pid <= 0:
                continue
            # DNP rows have minutes='0:00' — skip so they don't poison prev
            minutes = str(r.get("minutes") or "")
            if minutes in ("", "0:00"):
                continue
            gid = str(r.get("gameId") or gid_from_path).zfill(10)
            lookup[(pid, gid)] = {
                f"prev_track_{c}": float(r.get(c) or 0.0)
                for c in _TRACK_RAW_COLS
            }
    return lookup


# ── Match a player's game (date, MATCHUP) to a game_id ───────────────────────

def parse_matchup(matchup: str) -> Tuple[str, str]:
    """('LAL vs. HOU', 'LAL @ HOU') -> ('LAL', 'HOU')."""
    raw = str(matchup).replace("@", "vs.")
    parts = raw.split("vs.")
    if len(parts) != 2:
        return ("", "")
    return (parts[0].strip(), parts[1].strip())


# ── Build the augmented dataset ──────────────────────────────────────────────

def build_augmented_dataset() -> Tuple[List[dict], List[str], List[str]]:
    """Build the standard pergame dataset, then attach prev-game tracking.

    Returns (rows, feature_cols_base, feature_cols_with_track).
    rows[i] has BOTH base feature cols AND _TRACK_FEAT_NAMES.

    For each (player, game) row, the "prev_track_*" value is the player's
    most-recent PRIOR game where tracking data was available. Rows whose
    player has no prior tracking row get neutral defaults (0.0).
    """
    import glob

    print("[load] building base pergame dataset ...", flush=True)
    t0 = time.time()
    rows_base, fc_base = build_pergame_dataset(min_prior=0)
    print(f"  base rows={len(rows_base)} cols={len(fc_base)} "
          f"({time.time()-t0:.0f}s)", flush=True)

    print("[load] building game_id and tracking lookups ...", flush=True)
    game_lookup = build_game_lookup()
    track_lookup = build_tracking_lookup()
    print(f"  game_ids={len(game_lookup)} track rows={len(track_lookup)}",
          flush=True)

    # For each player, build chronological list of (date, game_id, track_row)
    # by re-walking gamelogs (matches build_pergame_dataset's iteration order).
    # We use this to compute prev_track_* as the player's most-recent PRIOR
    # tracking row.
    print("[load] joining tracking to gamelog rows ...", flush=True)
    t0 = time.time()
    player_history: Dict[int, List[Tuple[datetime, Dict[str, float]]]] = {}
    for path in glob.glob(os.path.join(_NBA_CACHE, "gamelog_*.json")):
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        try:
            basename = os.path.basename(path)
            parts = basename.split("_")
            pid = int(parts[1])
        except Exception:
            continue
        if not isinstance(games, list):
            continue
        for g in games:
            gdate = _parse_date(g.get("GAME_DATE"))
            if gdate is None:
                continue
            min_played = float(g.get("MIN") or 0.0)
            if min_played < 1.0:
                continue
            t_a, t_b = parse_matchup(g.get("MATCHUP", ""))
            if not t_a or not t_b:
                continue
            key = (gdate.date().isoformat(), tuple(sorted([t_a, t_b])))
            gid = game_lookup.get(key)
            if gid is None:
                continue
            trk = track_lookup.get((pid, gid))
            if trk is None:
                # No tracking data for this (player, game) — skip but DON'T
                # break the history; next prior is whatever last had data.
                continue
            player_history.setdefault(pid, []).append((gdate, trk))

    # Sort each player's history ascending by date.
    for pid in player_history:
        player_history[pid].sort(key=lambda x: x[0])
    print(f"  player_history players={len(player_history)} "
          f"({time.time()-t0:.0f}s)", flush=True)

    # Now attach prev_track_* to each base row by binary-searching the player's
    # history for the most-recent date STRICTLY BEFORE the row date.
    # gamelog file basename has player_id in parts[1] — we cannot re-derive
    # from the row alone (row dicts don't carry player_id). Re-walk gamelogs
    # to attach the player_id alongside row date, then merge.
    # But build_pergame_dataset returns a row PER (player, game) without pid.
    # Workaround: re-build the same emission walk here and attach features
    # to a new dataset list directly.

    print("[walk] re-emitting per-game rows with prev_track_* attached ...",
          flush=True)
    t0 = time.time()

    # We need to RE-DO the dataset walk to know which player each row belongs
    # to. Easiest path: monkey-patch nothing, just iterate gamelogs in the
    # SAME order build_pergame_dataset uses (glob sort order is deterministic
    # on the same filesystem) and emit the prev_track_* values, then zip with
    # rows_base in date order.
    #
    # Safer approach: build a parallel list of prev_track dicts in the SAME
    # iteration order as build_pergame_dataset, then verify dates match.

    from src.prediction.prop_pergame import _MIN_PLAYED

    aux_rows: List[Tuple[str, Dict[str, float]]] = []  # (date_iso, prev_track_dict)
    for path in sorted(glob.glob(os.path.join(_NBA_CACHE, "gamelog_*.json"))):
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(games, list) or len(games) == 0:
            continue
        try:
            basename = os.path.basename(path)
            parts = basename.split("_")
            pid = int(parts[1])
        except Exception:
            pid = 0

        dated = [(d, g) for g in games
                 if (d := _parse_date(g.get("GAME_DATE"))) is not None]
        dated.sort(key=lambda x: x[0])

        prior_played: List[dict] = []
        for idx, (gdate, game) in enumerate(dated):
            played = float(game.get("MIN") or 0.0) >= _MIN_PLAYED

            if played:
                # Compute prev_track from player_history strictly before gdate
                hist = player_history.get(pid, [])
                # Binary-search the rightmost entry with date < gdate
                lo, hi = 0, len(hist)
                while lo < hi:
                    mid = (lo + hi) // 2
                    if hist[mid][0] < gdate:
                        lo = mid + 1
                    else:
                        hi = mid
                if lo == 0:
                    prev_track = dict(_TRACK_DEFAULTS)
                else:
                    prev_track = dict(hist[lo - 1][1])
                aux_rows.append((gdate.isoformat(), prev_track))
                prior_played.append(game)

    if len(aux_rows) != len(rows_base):
        raise RuntimeError(
            f"row count mismatch: base={len(rows_base)} aux={len(aux_rows)} — "
            "iteration order between probe and build_pergame_dataset diverged"
        )

    # Verify dates match row-for-row (cheap sanity check).
    mismatch = sum(1 for (d_aux, _), r in zip(aux_rows, rows_base)
                   if d_aux != r["date"])
    if mismatch:
        raise RuntimeError(f"date mismatch in {mismatch}/{len(rows_base)} rows")

    # Attach to base rows in-place.
    coverage = 0
    for (_, trk), r in zip(aux_rows, rows_base):
        for k in _TRACK_FEAT_NAMES:
            r[k] = trk.get(k, 0.0)
        if any(trk.get(k, 0.0) != 0.0 for k in _TRACK_FEAT_NAMES):
            coverage += 1
    print(f"  augmented {len(rows_base)} rows; non-zero coverage = "
          f"{coverage} ({coverage / len(rows_base):.1%}) "
          f"({time.time()-t0:.0f}s)", flush=True)

    fc_with_track = list(fc_base) + list(_TRACK_FEAT_NAMES)
    return rows_base, fc_base, fc_with_track


# ── Train one stat with a given feature set and return (single-split MAE, ──
#     walk-forward fold MAEs).

def _train_blend(stat: str, rows: List[dict], fc: List[str],
                 train_end: int, val_end: int, te_end: int) -> Tuple[float, float]:
    """Train XGB+LGB+MLP NNLS blend on one slice and return (mae, r2).

    Same recipe as prop_pergame_walk_forward.py:_train_one_stat — but
    accepts arbitrary slice indices so we can re-use across single-split
    and walk-forward folds.
    """
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.neural_network import MLPRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error, r2_score

    X_all = np.array([[r[c] for c in fc] for r in rows], dtype=float)
    y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
    X_tr, X_val, X_ho = X_all[:train_end], X_all[train_end:val_end], X_all[val_end:te_end]
    y_tr, y_val, y_ho = y[:train_end], y[train_end:val_end], y[val_end:te_end]

    tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(train_end)]
    max_d = max(tr_dates)
    age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
    sw = np.exp(-0.5 * age)

    is_count = stat in ("stl", "blk")
    xgb_m = xgb.XGBRegressor(
        n_estimators=600, max_depth=3 if is_count else 4,
        learning_rate=0.04, subsample=0.8, colsample_bytree=0.8,
        min_child_weight=10, reg_lambda=2.0, reg_alpha=0.5, gamma=0.2,
        random_state=42,
        objective="count:poisson" if is_count else "reg:squarederror",
        early_stopping_rounds=40, eval_metric="mae",
    )
    xgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
              sample_weight=sw, verbose=False)
    lgb_m = lgb.LGBMRegressor(
        n_estimators=600, max_depth=3 if is_count else 4,
        learning_rate=0.04, subsample=0.8, subsample_freq=1,
        colsample_bytree=0.8, min_child_samples=20,
        reg_lambda=2.0, reg_alpha=0.5, random_state=42,
        objective="poisson" if is_count else "regression",
        n_jobs=-1, verbosity=-1,
    )
    lgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], sample_weight=sw,
              callbacks=[lgb.early_stopping(40, verbose=False)])

    sc = StandardScaler()
    X_tr_s = sc.fit_transform(X_tr)
    X_val_s = sc.transform(X_val)
    X_ho_s = sc.transform(X_ho)
    from src.prediction.prop_pergame import _MLPSeedEnsemble  # noqa: PLC0415
    mlp_m = _MLPSeedEnsemble().fit(X_tr_s, y_tr)

    xv, lv, mv = xgb_m.predict(X_val), lgb_m.predict(X_val), mlp_m.predict(X_val_s)
    xh, lh, mh = xgb_m.predict(X_ho), lgb_m.predict(X_ho), mlp_m.predict(X_ho_s)
    st = LinearRegression(positive=True, fit_intercept=False)
    st.fit(np.column_stack([xv, lv, mv]), y_val)
    w = st.coef_
    if not (0.5 <= w.sum() <= 1.5):
        w = np.array([1.0 / 3, 1.0 / 3, 1.0 / 3])
    blend = w[0] * xh + w[1] * lh + w[2] * mh
    return float(mean_absolute_error(y_ho, blend)), float(r2_score(y_ho, blend))


def run_probe() -> dict:
    rows, fc_base, fc_with = build_augmented_dataset()
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    print(f"\n[probe] rows={n} base_cols={len(fc_base)} "
          f"with_track_cols={len(fc_with)}", flush=True)

    summary: dict = {
        "n_rows": n,
        "base_cols": len(fc_base),
        "track_cols_added": len(fc_with) - len(fc_base),
        "track_col_names": list(_TRACK_FEAT_NAMES),
        "stats": {},
    }

    # Single-split: same proportions as train_pergame_models defaults
    # (val_frac=0.15, holdout_frac=0.20)
    train_end_ss = int(n * (1.0 - 0.20 - 0.15))
    val_end_ss = int(n * (1.0 - 0.20))
    te_end_ss = n

    # Walk-forward: 4 folds, same as prop_pergame_walk_forward.py
    n_splits = 4
    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]

    for stat in _PROBE_STATS:
        print(f"\n=== STAT: {stat.upper()} ===", flush=True)
        stat_out = {"single_split": {}, "wf_folds": []}

        # Single-split — base vs with_track
        t0 = time.time()
        ss_base = _train_blend(stat, rows, fc_base, train_end_ss, val_end_ss, te_end_ss)
        ss_with = _train_blend(stat, rows, fc_with, train_end_ss, val_end_ss, te_end_ss)
        ss_d_mae = ss_with[0] - ss_base[0]
        ss_d_r2 = ss_with[1] - ss_base[1]
        stat_out["single_split"] = {
            "base_mae": ss_base[0], "base_r2": ss_base[1],
            "with_mae": ss_with[0], "with_r2": ss_with[1],
            "delta_mae": ss_d_mae, "delta_r2": ss_d_r2,
        }
        print(f"  single-split base mae={ss_base[0]:.4f} r2={ss_base[1]:.4f}  "
              f"with mae={ss_with[0]:.4f} r2={ss_with[1]:.4f}  "
              f"d_mae={ss_d_mae:+.4f} d_r2={ss_d_r2:+.4f}  "
              f"({time.time()-t0:.0f}s)", flush=True)

        # Walk-forward
        for fold_idx, train_end_frac in enumerate(fold_ends):
            tr_end = int(n * train_end_frac)
            if fold_idx == n_splits - 1:
                te_end = n
            else:
                te_end = int(n * fold_ends[fold_idx + 1])
            va_end = int(tr_end + (te_end - tr_end) * 0.4)
            if tr_end < 5000 or (te_end - va_end) < 2000:
                continue
            t0 = time.time()
            wf_base = _train_blend(stat, rows, fc_base, tr_end, va_end, te_end)
            wf_with = _train_blend(stat, rows, fc_with, tr_end, va_end, te_end)
            d_mae = wf_with[0] - wf_base[0]
            d_r2 = wf_with[1] - wf_base[1]
            stat_out["wf_folds"].append({
                "fold": fold_idx + 1,
                "tr_end": tr_end, "va_end": va_end, "te_end": te_end,
                "base_mae": wf_base[0], "base_r2": wf_base[1],
                "with_mae": wf_with[0], "with_r2": wf_with[1],
                "delta_mae": d_mae, "delta_r2": d_r2,
            })
            print(f"  fold {fold_idx+1}/4 base mae={wf_base[0]:.4f}  "
                  f"with mae={wf_with[0]:.4f}  d_mae={d_mae:+.4f}  d_r2={d_r2:+.4f}  "
                  f"({time.time()-t0:.0f}s)", flush=True)

        # Dual-gate verdict
        wf_d_maes = [f["delta_mae"] for f in stat_out["wf_folds"]]
        wf_pass = bool(wf_d_maes) and all(d < 0 for d in wf_d_maes)
        ss_pass = ss_d_mae < 0
        stat_out["wf_mean_delta_mae"] = float(np.mean(wf_d_maes)) if wf_d_maes else None
        stat_out["wf_all_folds_pass"] = wf_pass
        stat_out["ss_pass"] = ss_pass
        stat_out["ship_verdict"] = "SHIP" if (wf_pass and ss_pass) else "REJECT"
        summary["stats"][stat] = stat_out
        print(f"\n  {stat.upper()} VERDICT: WF 4/4={wf_pass} (mean d_mae="
              f"{stat_out['wf_mean_delta_mae']:+.4f})  "
              f"SS pass={ss_pass} (d_mae={ss_d_mae:+.4f})  "
              f"=> {stat_out['ship_verdict']}", flush=True)

    os.makedirs(os.path.dirname(_OUT_PATH), exist_ok=True)
    with open(_OUT_PATH, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nWrote {_OUT_PATH}", flush=True)
    return summary


if __name__ == "__main__":
    run_probe()
