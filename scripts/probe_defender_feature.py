"""probe_defender_feature.py — cycle 84b PROBE.

Tests adding ONE defender-matchup feature to the prop_pergame PTS model:
    opp_top_def_pts_per_min = the opp team's BEST defender's points allowed
    per matchup minute over the prior 30 days. Lower = stronger primary
    defender on the opposing team.

Heuristic rationale (since we lack position data):
- For each player-game, look up the opponent team
- Find that team's "top defender" = the defender (across team's prior-30-day
  games) with the largest matchup_minutes_total AND lowest points_per_min
- The feature is that defender's points_allowed / matchup_minutes_total
- Defaults to a neutral league mean (~0.65 pts/min) when no data is available

This is leakage-free: the lookup window strictly precedes the game date.

Runs:
    1. Walk-forward 4-fold for PTS (2-way XGB+LGB blend baseline vs +1 feature)
    2. Production single-split (chronological 70/15/15) for PTS

Ship gate: BOTH WF 4/4 folds MAE down AND single-split MAE strictly down.
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time
import warnings
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, _opponent_from_matchup, _parse_date,
)

_MATCHUP_DIR = os.path.join(PROJECT_DIR, "data", "defender_matchups")
_SCHEDULE_DIR = os.path.join(PROJECT_DIR, "data", "nba", "schedule")
_LOOKBACK_DAYS = 30
_NEUTRAL_PTS_PER_MIN = 0.65  # league mean ~ 25pts allowed / 38 min per starter
_MIN_MATCHUP_MIN = 5.0  # need at least 5 cumulative min to call someone "primary"


# ── lookup builders ──────────────────────────────────────────────────────────


def build_schedule_lookup() -> Dict[Tuple[str, str], str]:
    """Map (team_abbrev, date_iso) -> game_id from cached team schedule files."""
    lookup: Dict[Tuple[str, str], str] = {}
    if not os.path.isdir(_SCHEDULE_DIR):
        return lookup
    for fname in os.listdir(_SCHEDULE_DIR):
        if not fname.startswith("schedule_") or not fname.endswith(".json"):
            continue
        try:
            parts = fname.removeprefix("schedule_").removesuffix(".json").split("_")
            team = parts[0]
        except (ValueError, IndexError):
            continue
        try:
            rows = json.load(open(os.path.join(_SCHEDULE_DIR, fname),
                                  encoding="utf-8"))
        except Exception:
            continue
        for r in rows:
            gid = str(r.get("game_id", ""))
            date = str(r.get("date", ""))
            if gid and date:
                lookup[(team, date)] = gid
    return lookup


def build_team_games_index() -> Dict[str, List[Tuple[str, str]]]:
    """Per-team chronological list of (date_iso, game_id) — for prior-N lookups."""
    out: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    if not os.path.isdir(_SCHEDULE_DIR):
        return out
    for fname in os.listdir(_SCHEDULE_DIR):
        if not fname.startswith("schedule_") or not fname.endswith(".json"):
            continue
        parts = fname.removeprefix("schedule_").removesuffix(".json").split("_")
        team = parts[0]
        try:
            rows = json.load(open(os.path.join(_SCHEDULE_DIR, fname),
                                  encoding="utf-8"))
        except Exception:
            continue
        for r in rows:
            gid = str(r.get("game_id", ""))
            date = str(r.get("date", ""))
            if gid and date:
                out[team].append((date, gid))
    for team in out:
        out[team].sort()
    return out


def load_game_defender_summary(game_id: str
                               ) -> Dict[str, Dict[str, float]]:
    """For one game, return {team_tricode: {def_player_id: {min, pts}}}.

    Aggregates the raw matchups by defender, keeping totals only.
    Returns {} if cache file missing.
    """
    path = os.path.join(_MATCHUP_DIR, f"raw_{game_id}.json")
    if not os.path.exists(path):
        return {}
    try:
        records = json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}
    by_team: Dict[str, Dict[int, Dict[str, float]]] = defaultdict(dict)
    for rec in records:
        team = str(rec.get("def_team_tricode", ""))
        try:
            pid = int(rec.get("def_player_id"))
        except (TypeError, ValueError):
            continue
        d = by_team[team].setdefault(pid, {"min": 0.0, "pts": 0.0})
        d["min"] += float(rec.get("matchup_minutes_float", 0.0) or 0.0)
        d["pts"] += float(rec.get("player_points", 0) or 0)
    return by_team


def _date_iso(s: str) -> str:
    """Normalise a date string to YYYY-MM-DD. Accepts ISO or 'MMM DD, YYYY'."""
    dt = _parse_date(s)
    if dt:
        return dt.date().isoformat()
    try:
        return datetime.fromisoformat(s).date().isoformat()
    except (TypeError, ValueError):
        return s


def build_team_defender_lookup(
    team_games: Dict[str, List[Tuple[str, str]]],
) -> Dict[str, List[Tuple[str, Dict[int, Dict[str, float]]]]]:
    """Per-team list of (game_date_iso, defender_summary) sorted chronologically.

    defender_summary = {def_player_id: {min: float, pts: float}}.
    Only games with a cached raw_<gid>.json file are included.
    """
    out: Dict[str, List[Tuple[str, Dict[int, Dict[str, float]]]]] = {}
    for team, schedule in team_games.items():
        chronicle: List[Tuple[str, Dict[int, Dict[str, float]]]] = []
        for (date_iso, gid) in schedule:
            per_team = load_game_defender_summary(gid)
            if team in per_team:
                chronicle.append((date_iso, per_team[team]))
        chronicle.sort()  # already sorted but be safe
        if chronicle:
            out[team] = chronicle
    return out


def compute_opp_top_def_pts_per_min(
    opp_team: str,
    game_date_iso: str,
    team_def_lookup: Dict[str, List[Tuple[str, Dict[int, Dict[str, float]]]]],
    lookback_days: int = _LOOKBACK_DAYS,
) -> Tuple[float, int]:
    """Return (opp_top_def_pts_per_min, n_games_used).

    Aggregates the opp team's defender matchups over [game_date - lookback, game_date).
    Finds the defender with the most cumulative matchup minutes; returns
    that defender's pts_allowed / matchup_minutes. Strictly leakage-free.
    """
    chronicle = team_def_lookup.get(opp_team)
    if not chronicle:
        return _NEUTRAL_PTS_PER_MIN, 0
    try:
        target = datetime.fromisoformat(game_date_iso).date()
    except (TypeError, ValueError):
        return _NEUTRAL_PTS_PER_MIN, 0
    window_start = target - timedelta(days=lookback_days)

    agg: Dict[int, Dict[str, float]] = defaultdict(
        lambda: {"min": 0.0, "pts": 0.0}
    )
    n_games = 0
    for (d_iso, summary) in chronicle:
        try:
            d = datetime.fromisoformat(d_iso).date()
        except (TypeError, ValueError):
            continue
        if d >= target:
            break  # leakage guard
        if d < window_start:
            continue
        n_games += 1
        for pid, vals in summary.items():
            agg[pid]["min"] += vals["min"]
            agg[pid]["pts"] += vals["pts"]
    if not agg:
        return _NEUTRAL_PTS_PER_MIN, 0

    # Find primary defender = most matchup minutes, with a floor
    top_pid, top_vals = max(agg.items(), key=lambda kv: kv[1]["min"])
    if top_vals["min"] < _MIN_MATCHUP_MIN:
        return _NEUTRAL_PTS_PER_MIN, n_games
    return float(top_vals["pts"] / top_vals["min"]), n_games


# ── walk-forward probe ───────────────────────────────────────────────────────


def _train_pts(X_tr, y_tr, X_val, y_val, X_ho, y_ho, sw):
    """Train a 2-way XGB+LGB blend for PTS (matches prop_pergame's PTS recipe).

    Returns (mae, r2) on the holdout. Uses sqrt label transform + Huber loss
    (PTS production recipe from cycle 18).
    """
    import lightgbm as lgb
    import xgboost as xgb
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error, r2_score

    y_tr_t = np.sqrt(y_tr)
    y_val_t = np.sqrt(y_val)

    # PTS-specific HP from prop_pergame _STAT_PARAMS["pts"]
    xgb_m = xgb.XGBRegressor(
        n_estimators=800, max_depth=6,
        learning_rate=0.025, subsample=0.8, colsample_bytree=0.9,
        min_child_weight=20, reg_lambda=4.0, reg_alpha=2.0, gamma=0.2,
        random_state=42, objective="reg:pseudohubererror",
        early_stopping_rounds=40, eval_metric="mae",
    )
    xgb_m.fit(X_tr, y_tr_t, eval_set=[(X_val, y_val_t)],
              sample_weight=sw, verbose=False)
    lgb_m = lgb.LGBMRegressor(
        n_estimators=800, max_depth=6,
        learning_rate=0.025, subsample=0.8, subsample_freq=1,
        colsample_bytree=0.9, min_child_samples=40,
        reg_lambda=4.0, reg_alpha=2.0, random_state=42,
        objective="huber", n_jobs=-1, verbosity=-1,
    )
    lgb_m.fit(X_tr, y_tr_t, eval_set=[(X_val, y_val_t)],
              sample_weight=sw,
              callbacks=[lgb.early_stopping(40, verbose=False)])

    def _inv(v):
        return np.clip(v, 0.0, None) ** 2

    xv, lv = _inv(xgb_m.predict(X_val)), _inv(lgb_m.predict(X_val))
    xh, lh = _inv(xgb_m.predict(X_ho)), _inv(lgb_m.predict(X_ho))

    st = LinearRegression(positive=True, fit_intercept=False)
    st.fit(np.column_stack([xv, lv]), y_val)
    w = st.coef_
    if not (0.5 <= w.sum() <= 1.5):
        w = np.array([0.5, 0.5])
    pred = w[0] * xh + w[1] * lh

    return (float(mean_absolute_error(y_ho, pred)),
            float(r2_score(y_ho, pred)))


def main():
    print("=" * 70)
    print("PROBE: opp_top_def_pts_per_min as new PTS feature")
    print("=" * 70)

    # 1. Build cache lookups
    print("\n[1/4] Building schedule + team-defender lookups ...")
    t0 = time.time()
    team_games = build_team_games_index()
    print(f"  team schedules loaded: {len(team_games)} teams")
    team_def_lookup = build_team_defender_lookup(team_games)
    n_team_games_with_data = sum(len(v) for v in team_def_lookup.values())
    print(f"  team-games with cached matchup data: {n_team_games_with_data} "
          f"(across {len(team_def_lookup)} teams)")
    n_cached_files = len(glob.glob(os.path.join(_MATCHUP_DIR, "raw_*.json")))
    print(f"  raw matchup cache files: {n_cached_files}")
    print(f"  build wall: {time.time()-t0:.1f}s")

    # 2. Load dataset + compute new feature
    print("\n[2/4] Building pergame dataset ...")
    t0 = time.time()
    rows, fc = build_pergame_dataset(min_prior=0)
    print(f"  rows={len(rows)}, baseline_features={len(fc)}")
    print(f"  dataset wall: {time.time()-t0:.1f}s")

    print("\n[3/4] Joining defender feature ...")
    t0 = time.time()
    feature_vals: List[float] = []
    n_hits = 0
    for r in rows:
        # Find opp_team from the row — we need to recover MATCHUP somehow.
        # The dataset rows don't carry team/opp directly. We need to rebuild
        # by re-scanning the gamelog... OR use the opp_def_* signature in
        # the row to look up the (date, team) tuple. Actually opp team isn't
        # in the row. Need to rebuild from raw gamelog scan.
        pass
    # Re-scan gamelogs to extract (player_id, season, date_iso) -> opp_team
    # and align with rows by date+target_pts as proxy. Cleaner approach:
    # add opp/date as auxiliary alongside the rebuild here.

    # Use an alternative: walk the gamelog dir same way build_pergame_dataset does,
    # but emit (date_iso, opp_team) per emitted row in identical order.
    aux = _rebuild_row_aux(min_prior=0)
    print(f"  aux rows for join: {len(aux)} (vs dataset rows: {len(rows)})")
    if len(aux) != len(rows):
        print("  WARNING: aux row count mismatch — alignment cannot be guaranteed")
        # Bail safely
        return

    for (date_iso, opp_team) in aux:
        val, n_games = compute_opp_top_def_pts_per_min(
            opp_team, date_iso, team_def_lookup,
        )
        if n_games > 0:
            n_hits += 1
        feature_vals.append(val)
    coverage = n_hits / max(1, len(rows))
    print(f"  feature join: {n_hits}/{len(rows)} non-default values "
          f"({coverage:.1%} coverage)")
    print(f"  join wall: {time.time()-t0:.1f}s")

    # If coverage < 5%, the test will be noise. Bail early.
    if coverage < 0.02:
        print("  ABORT: coverage too low — feature can't move the needle")
        return

    # 3. Build X matrices: baseline (fc) and augmented (fc + new feature)
    print("\n[4/4] Walk-forward + single-split probe ...")
    rows.sort(key=lambda r: r["date"])
    # Re-align aux to the sorted order — need stable join
    # Easier: zip + sort together
    rows_with_aux = list(zip(rows, feature_vals))
    rows_with_aux.sort(key=lambda x: x[0]["date"])
    rows = [r for r, _ in rows_with_aux]
    feature_vals = [v for _, v in rows_with_aux]

    n = len(rows)
    X_base = np.array([[r[c] for c in fc] for r in rows], dtype=float)
    X_aug = np.hstack([X_base, np.array(feature_vals).reshape(-1, 1)])
    y = np.array([r["target_pts"] for r in rows], dtype=float)

    print(f"  X_base={X_base.shape} X_aug={X_aug.shape} y={y.shape}")

    # ── Walk-forward 4-fold ─────────────────────────────────────────────────
    n_splits = 4
    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    fold_results = []  # (fold_idx, mae_base, mae_aug, r2_base, r2_aug)

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        te_end = n if fold_idx == n_splits - 1 else int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        if tr_end < 5000 or (te_end - va_end) < 2000:
            print(f"  fold {fold_idx+1}: too small — skip")
            continue
        Xb_tr, Xb_val, Xb_ho = X_base[:tr_end], X_base[tr_end:va_end], X_base[va_end:te_end]
        Xa_tr, Xa_val, Xa_ho = X_aug[:tr_end], X_aug[tr_end:va_end], X_aug[va_end:te_end]
        y_tr, y_val, y_ho = y[:tr_end], y[tr_end:va_end], y[va_end:te_end]

        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        print(f"\n[fold {fold_idx+1}/{n_splits}] tr={tr_end} val={va_end-tr_end} ho={te_end-va_end}",
              flush=True)
        t0 = time.time()
        mae_b, r2_b = _train_pts(Xb_tr, y_tr, Xb_val, y_val, Xb_ho, y_ho, sw)
        mae_a, r2_a = _train_pts(Xa_tr, y_tr, Xa_val, y_val, Xa_ho, y_ho, sw)
        print(f"  PTS base mae={mae_b:.4f} r2={r2_b:.4f}  "
              f"aug mae={mae_a:.4f} r2={r2_a:.4f}  "
              f"d_mae={mae_a-mae_b:+.4f}  ({time.time()-t0:.0f}s)",
              flush=True)
        fold_results.append({
            "fold": fold_idx + 1,
            "mae_base": mae_b, "mae_aug": mae_a,
            "r2_base": r2_b, "r2_aug": r2_a,
            "d_mae": mae_a - mae_b,
        })

    # ── Production single-split (chronological 70/15/15) ────────────────────
    print("\n[single-split] chronological 70/15/15 ...")
    tr_end = int(n * 0.70)
    va_end = int(n * 0.85)
    Xb_tr, Xb_val, Xb_ho = X_base[:tr_end], X_base[tr_end:va_end], X_base[va_end:]
    Xa_tr, Xa_val, Xa_ho = X_aug[:tr_end], X_aug[tr_end:va_end], X_aug[va_end:]
    y_tr, y_val, y_ho = y[:tr_end], y[tr_end:va_end], y[va_end:]
    tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
    max_d = max(tr_dates)
    age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
    sw = np.exp(-0.5 * age)
    t0 = time.time()
    ss_mae_b, ss_r2_b = _train_pts(Xb_tr, y_tr, Xb_val, y_val, Xb_ho, y_ho, sw)
    ss_mae_a, ss_r2_a = _train_pts(Xa_tr, y_tr, Xa_val, y_val, Xa_ho, y_ho, sw)
    print(f"  PTS base mae={ss_mae_b:.4f} r2={ss_r2_b:.4f}")
    print(f"  PTS aug  mae={ss_mae_a:.4f} r2={ss_r2_a:.4f}")
    print(f"  d_mae={ss_mae_a-ss_mae_b:+.4f}   ({time.time()-t0:.0f}s)")

    # ── Verdict ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    wf_wins = sum(1 for r in fold_results if r["d_mae"] < 0)
    wf_total = len(fold_results)
    print(f"WF: {wf_wins}/{wf_total} folds improved MAE")
    print(f"single-split d_mae = {ss_mae_a-ss_mae_b:+.4f}")
    ship = (wf_wins == wf_total and wf_total >= 3
            and ss_mae_a < ss_mae_b)
    print(f"DUAL GATE: {'PASS — SHIP' if ship else 'FAIL — REJECT'}")

    # Persist results
    out = {
        "feature": "opp_top_def_pts_per_min",
        "coverage": coverage,
        "n_cached_games": n_cached_files,
        "n_team_games_with_data": n_team_games_with_data,
        "walk_forward": fold_results,
        "single_split": {
            "mae_base": ss_mae_b, "mae_aug": ss_mae_a,
            "r2_base": ss_r2_b, "r2_aug": ss_r2_a,
            "d_mae": ss_mae_a - ss_mae_b,
        },
        "verdict": "SHIP" if ship else "REJECT",
        "wf_wins": wf_wins,
        "wf_total": wf_total,
    }
    out_path = os.path.join(PROJECT_DIR, "data", "models",
                            "probe_defender_feature.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nWrote {out_path}")


# ── helper: rebuild auxiliary (date_iso, opp_team) in row-emission order ─────


def _rebuild_row_aux(min_prior: int = 0) -> List[Tuple[str, str]]:
    """Re-scan the gamelog dir mirroring build_pergame_dataset's emission order
    to give us per-row (date_iso, opp_team). This MUST stay in lock-step with
    the iteration in build_pergame_dataset.
    """
    from src.prediction.prop_pergame import _NBA_CACHE, _MIN_PLAYED, _num

    aux: List[Tuple[str, str]] = []
    # NB: leave unsorted — matches build_pergame_dataset's iteration order.
    for path in glob.glob(os.path.join(_NBA_CACHE, "gamelog_*.json")):
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(games, list) or len(games) <= min_prior:
            continue
        dated = [(d, g) for g in games
                 if (d := _parse_date(g.get("GAME_DATE"))) is not None]
        dated.sort(key=lambda x: x[0])
        prior_played: List[dict] = []
        for idx, (gdate, game) in enumerate(dated):
            played = _num(game.get("MIN")) >= _MIN_PLAYED
            if played and len(prior_played) >= min_prior:
                opp = _opponent_from_matchup(game.get("MATCHUP", ""))
                aux.append((gdate.date().isoformat(), opp))
            if played:
                prior_played.append(game)
    return aux


if __name__ == "__main__":
    main()
