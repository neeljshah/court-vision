"""probe_officials_wf.py — iter-5 autonomous-loop probe (officials re-test).

Re-tests whether the 3 cols in data/officials_features.parquet
    ref_crew_fouls, ref_crew_fta, ref_crew_home_win_pct
improve walk-forward MAE on the XGB-q50 prop heads. Cycle 15 rejected
this feature set on the smaller corpus + log1p loss surface. Now we have
~2x the training rows and q50 loss surfaces — robust to outlier tails
which is exactly where refs should affect counts (foul-heavy nights drive
FTA / fouls / and indirectly BLK/STL via possessions). Worth one more shot.

The probe mirrors scripts/probe_player_adv_stats_wf.py:
  1. Build the standard prop dataset.
  2. Reconstruct (player_id, date_iso) -> team_abbrev from gamelog cache
     (rows don't carry team_abbrev directly).
  3. Look up officials_features by (team_abbrev, date_iso); defaults on miss.
  4. Append 3 cols to the feature set, train baseline XGB-q50 vs probe
     XGB-q50 on the same folds, report per-fold + aggregate MAE delta.
  5. Smoke-test on FG3M first. Expand to BLK/STL/TOV only if FG3M passes
     a "promising" bar (>= 2/4 folds positive). Reject otherwise.

Gate: 4/4 WF folds positive AND mean delta < 0 -> SHIP. Otherwise REJECT.

Run:
    python scripts/probe_officials_wf.py                  # FG3M smoke + expand if promising
    python scripts/probe_officials_wf.py --stats fg3m,blk # explicit set
"""
from __future__ import annotations

import argparse
import glob
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
    build_pergame_dataset, _LOG_TRANSFORM_STATS,
)
from src.prediction.prop_quantiles import _per_stat_xgb_params  # noqa: E402


_OFFICIALS_PARQUET = os.path.join(PROJECT_DIR, "data", "officials_features.parquet")
_GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
_OFF_COLS = ("ref_crew_fouls", "ref_crew_fta", "ref_crew_home_win_pct")
_OFF_DEFAULTS = {
    "ref_crew_fouls":        42.0,
    "ref_crew_fta":          43.5,
    "ref_crew_home_win_pct": 0.55,
}


# ── lookups ────────────────────────────────────────────────────────────────

def _load_officials_lookup() -> Dict[Tuple[str, str], Dict[str, float]]:
    """(team_abbrev, date_iso) -> {ref_crew_*}. date_iso is YYYY-MM-DD."""
    import pandas as pd  # noqa: PLC0415
    df = pd.read_parquet(_OFFICIALS_PARQUET)
    out: Dict[Tuple[str, str], Dict[str, float]] = {}
    for _, r in df.iterrows():
        # game_date in parquet is stored as 'YYYY-MM-DD' string.
        key = (str(r["team_abbreviation"]), str(r["game_date"]))
        out[key] = {c: float(r[c]) for c in _OFF_COLS}
    return out


def _parse_gamelog_date(raw: str):
    try:
        return datetime.strptime(str(raw).strip(), "%b %d, %Y")
    except Exception:
        return None


def _load_player_team_lookup() -> Dict[Tuple[int, str], str]:
    """(player_id, date_iso) -> team_abbrev. From gamelog_*.json MATCHUP col."""
    out: Dict[Tuple[int, str], str] = {}
    n_files = 0
    n_rows = 0
    for path in glob.glob(os.path.join(_GAMELOG_DIR, "gamelog_*.json")):
        # filename pattern: gamelog_<pid>_<season>.json
        base = os.path.basename(path)
        try:
            pid = int(base.split("_")[1])
        except Exception:
            continue
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(games, list):
            continue
        n_files += 1
        for g in games:
            d = _parse_gamelog_date(g.get("GAME_DATE"))
            if d is None:
                continue
            matchup = str(g.get("MATCHUP", "")).strip()
            if not matchup:
                continue
            tokens = matchup.split()
            if not tokens:
                continue
            team = tokens[0].upper()
            out[(pid, d.date().isoformat())] = team
            n_rows += 1
    print(f"  gamelog cache: {n_files} files, {n_rows} (pid,date) keys", flush=True)
    return out


# ── learner ────────────────────────────────────────────────────────────────

def _transform(stat: str, y: np.ndarray) -> np.ndarray:
    return np.log1p(y) if stat in _LOG_TRANSFORM_STATS else y


def _inverse(stat: str, v: np.ndarray) -> np.ndarray:
    if stat in _LOG_TRANSFORM_STATS:
        return np.clip(np.expm1(v), 0.0, None)
    return np.clip(v, 0.0, None)


def _train_xgb_q50(stat, X_tr, y_tr, X_val, y_val, X_ho, y_ho, sw):
    import xgboost as xgb
    from sklearn.metrics import mean_absolute_error

    params = _per_stat_xgb_params(stat)
    yt_tr = _transform(stat, y_tr)
    yt_val = _transform(stat, y_val)
    m = xgb.XGBRegressor(
        **{k: v for k, v in params.items() if k != "random_state"},
        random_state=42,
        objective="reg:quantileerror",
        quantile_alpha=0.5,
        early_stopping_rounds=40,
        eval_metric="mae",
    )
    m.fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)],
          sample_weight=sw, verbose=False)
    preds_ho = _inverse(stat, m.predict(X_ho))
    return float(mean_absolute_error(y_ho, preds_ho))


# ── per-stat walk-forward ─────────────────────────────────────────────────

def _run_stat_wf(stat: str, rows, fc_base, n_splits=4) -> Tuple[List[dict], dict]:
    print(f"\n--- {stat.upper()} XGB-q50 walk-forward (n_splits={n_splits}) ---", flush=True)
    n = len(rows)
    X_base = np.array([[r[c] for c in fc_base] for r in rows], dtype=float)
    X_aug = np.array(
        [[r[c] for c in fc_base] + [r[k] for k in _OFF_COLS] for r in rows],
        dtype=float,
    )
    y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)

    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    results: List[dict] = []
    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        te_end = n if fold_idx == n_splits - 1 else int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        if tr_end < 5000 or (te_end - va_end) < 2000:
            print(f"  fold {fold_idx+1}: too small — skip", flush=True)
            continue
        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        slc = lambda M: (M[:tr_end], M[tr_end:va_end], M[va_end:te_end])  # noqa: E731
        Xb_tr, Xb_val, Xb_ho = slc(X_base)
        Xa_tr, Xa_val, Xa_ho = slc(X_aug)
        y_tr, y_val, y_ho = y[:tr_end], y[tr_end:va_end], y[va_end:te_end]

        t0 = time.time()
        mae_base = _train_xgb_q50(stat, Xb_tr, y_tr, Xb_val, y_val, Xb_ho, y_ho, sw)
        mae_aug = _train_xgb_q50(stat, Xa_tr, y_tr, Xa_val, y_val, Xa_ho, y_ho, sw)
        delta = mae_aug - mae_base
        print(f"  [fold {fold_idx+1}] base={mae_base:.4f} probe={mae_aug:.4f} "
              f"delta={delta:+.4f} ({'WIN' if delta < 0 else 'loss'})  "
              f"({time.time()-t0:.0f}s)", flush=True)
        results.append({"fold": fold_idx + 1, "stat": stat,
                        "mae_base": mae_base, "mae_aug": mae_aug, "delta": delta})

    n_wins = sum(1 for r in results if r["delta"] < 0)
    mean_delta = float(np.mean([r["delta"] for r in results])) if results else 0.0
    summary = {"stat": stat, "n_wins": n_wins, "n_folds": len(results),
               "mean_delta": mean_delta}
    return results, summary


# ── main ──────────────────────────────────────────────────────────────────

def main(stats: List[str], smoke_only: bool, n_splits: int):
    t0 = time.time()
    print("Probe iter-5: officials_features re-test (XGB-q50 WF)")
    print(f"  parquet={_OFFICIALS_PARQUET}")
    print(f"  smoke_stats=fg3m; expand_stats={stats}", flush=True)

    print("Building pergame dataset...", flush=True)
    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    print(f"  rows={n}, base_features={len(fc)}", flush=True)

    print("Loading (player_id,date) -> team lookup from gamelog cache...", flush=True)
    pid_team = _load_player_team_lookup()

    print("Loading officials lookup...", flush=True)
    off_lookup = _load_officials_lookup()
    print(f"  (team,date) keys: {len(off_lookup)}", flush=True)

    # Attach officials cols to every row.
    n_team_hit = 0
    n_off_hit = 0
    for r in rows:
        pid = int(r.get("player_id") or 0)
        d_iso = r["date"][:10]  # YYYY-MM-DD slice
        team = pid_team.get((pid, d_iso))
        if team:
            n_team_hit += 1
            feats = off_lookup.get((team, d_iso))
            if feats:
                n_off_hit += 1
                for k in _OFF_COLS:
                    r[k] = feats[k]
            else:
                for k in _OFF_COLS:
                    r[k] = _OFF_DEFAULTS[k]
        else:
            for k in _OFF_COLS:
                r[k] = _OFF_DEFAULTS[k]
    print(f"  team lookup hit rate:      {n_team_hit}/{n} ({100*n_team_hit/max(1,n):.1f}%)")
    print(f"  officials lookup hit rate: {n_off_hit}/{n} ({100*n_off_hit/max(1,n):.1f}%)")

    # Verify the new cols actually have variance — if everything's defaults
    # the probe is pointless.
    samp_fouls = np.array([r["ref_crew_fouls"] for r in rows[:5000]])
    print(f"  ref_crew_fouls sample (first 5k rows): "
          f"mean={samp_fouls.mean():.3f} std={samp_fouls.std():.4f} "
          f"non-default={int((samp_fouls != _OFF_DEFAULTS['ref_crew_fouls']).sum())}/5000",
          flush=True)

    all_results: List[dict] = []
    summaries: List[dict] = []

    # Smoke-test FG3M
    smoke_results, smoke_summary = _run_stat_wf("fg3m", rows, fc, n_splits=n_splits)
    all_results.extend(smoke_results)
    summaries.append(smoke_summary)

    proceed = smoke_summary["n_wins"] >= 2  # at least 2/4 folds positive
    if smoke_only:
        proceed = False
    if not proceed:
        print(f"\n[FG3M smoke] {smoke_summary['n_wins']}/{smoke_summary['n_folds']} "
              f"folds positive, mean_delta={smoke_summary['mean_delta']:+.4f}.")
        print("  -> NOT promising enough to expand. Skipping BLK/STL/TOV.")
    else:
        print(f"\n[FG3M smoke] {smoke_summary['n_wins']}/{smoke_summary['n_folds']} "
              f"folds positive — proceeding to expand stats.")
        for s in stats:
            if s == "fg3m":
                continue
            res, summ = _run_stat_wf(s, rows, fc, n_splits=n_splits)
            all_results.extend(res)
            summaries.append(summ)

    # Final table.
    print("\n" + "=" * 86)
    print("OFFICIALS RE-TEST WALK-FORWARD SUMMARY")
    print("-" * 86)
    print(" Fold | Stat | Baseline MAE | Probe MAE | Delta    | Result")
    print(" -----+------+--------------+-----------+----------+-------")
    for r in all_results:
        print(f"   {r['fold']}  | {r['stat']:<4} |   {r['mae_base']:.4f}     "
              f"|  {r['mae_aug']:.4f}   |  {r['delta']:+.4f} | "
              f"{'win' if r['delta'] < 0 else 'loss'}")
    print("-" * 86)
    print(" PER-STAT VERDICT (gate: 4/4 folds positive AND mean_delta < 0)")
    print("-" * 86)
    for s in summaries:
        all_win = s["n_wins"] == s["n_folds"] and s["n_folds"] >= 4
        mean_win = s["mean_delta"] < 0
        if all_win and mean_win:
            verdict = "SHIP"
        elif not all_win and not mean_win:
            verdict = "REJECT"
        else:
            verdict = "INCONCLUSIVE"
        print(f"  {s['stat']:<5} {s['n_wins']}/{s['n_folds']} folds  "
              f"mean_delta={s['mean_delta']:+.4f}  -> {verdict}")
    print("=" * 86)
    print(f"total runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", type=str, default="fg3m,blk,stl,tov",
                    help="Stats to probe (comma-sep). FG3M runs first as smoke test.")
    ap.add_argument("--smoke-only", action="store_true",
                    help="Run FG3M only, do not auto-expand.")
    ap.add_argument("--splits", type=int, default=4)
    args = ap.parse_args()
    stats = [s.strip().lower() for s in args.stats.split(",") if s.strip()]
    if "fg3m" not in stats:
        stats = ["fg3m"] + stats
    main(stats, args.smoke_only, args.splits)
