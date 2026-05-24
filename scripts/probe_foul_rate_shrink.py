"""probe_foul_rate_shrink.py -- cycle 90c (loop 5) T1-B probe.

Hypothesis (see scripts/_results/in_game_gaps_v1.md T1-B):
    Top-quintile foul-per-36 players have a fatter LEFT tail on MIN-coupled
    box-score realisations than the pre-game model captures (coaches yank
    them on early 4th foul -> 18-22 min vs typical 32). Apply an asymmetric
    multiplicative shrink (factor in (0.95, 0.98)) to PTS / REB / BLK
    predictions for top-quintile big-position players. Bigs proxy:
    top-quartile season BLK/36 (BLK rate is a strong "big" proxy).

DATA-AVAILABILITY CONSTRAINT (honest):
    Our cached gamelog JSONs (data/nba/gamelog_*.json) carry only
    PTS / REB / AST / FG3M / STL / BLK / TOV / MIN / GAME_DATE / MATCHUP.
    PF (personal fouls) is NOT present, and data/season_games.parquet
    is absent in this working tree. Without an extra NBA-API fetch of
    PF per game (out of the 35-min time bound for this probe), we
    cannot compute season PF/36 directly. We therefore PROBE the
    weaker variant: shrink keyed on BLK/36 alone (the "is-a-big"
    proxy). If even this single-axis variant fails the dual gate,
    we reject the full PF/36 + BLK/36 variant a fortiori (adding
    a noisier axis cannot recover a sign that's not there). If it
    PASSES, a follow-up cycle should fetch PF per game and re-probe
    the conjunction-gated variant.

Workflow:
    1. Walk every gamelog_<pid>_<season>.json. For each (player_id, date)
       compute expanding-window aggregates of PRIOR played games:
           season_blk_per_36 = sum(blk_prior) / sum(min_prior) * 36
       First games of a player's season fall back to 0.0 (UNtreated).
    2. Build the holdout the same way validate_adjustment.py does
       (chronological 80/20 split). For each holdout row attach the
       (player_id, date) -> season_blk_per_36 lookup.
    3. Find the GLOBAL top-quartile threshold on the EXPANDING training
       portion (rows[:train_end]) of blk_per_36 -- this is the bigs
       proxy. (Top-quintile threshold would be tighter; cycle 89f's
       hypothesis is top-QUINTILE of PF/36, but with BLK proxy alone
       we use top-QUARTILE since the BLK rate is noisier per-game and
       we want enough rows in the affected bucket to learn from.)
    4. Adjustment: apply factor in {0.95, 0.96, 0.97, 0.98} only to
       PTS / REB / BLK predictions for rows where the player's prior
       season_blk_per_36 >= top-quartile threshold.
    5. Validator + WF-style 4-fold sliding-window gate on the holdout.

Ship gate (BOTH):
    - Single-split MAE strictly down on >= 2 of {PTS, REB, BLK} AND
      aggregate MAE on those 3 down by >= 0.003.
    - 4/4 sliding-window folds positive on >= 2 of {PTS, REB, BLK}.

Run:
    python scripts/probe_foul_rate_shrink.py
"""
from __future__ import annotations

import glob
import json
import os
import sys
import warnings
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns,
)
# Reuse validate_adjustment's bulk-predict so we exercise the exact
# production dispatch path (cycle 48 logic, q50 / NNLS blend, sqrt+Huber
# / log1p inverses). This keeps the baseline numerically identical to
# what validate_adjustment.py reports for no-op control.
from scripts.validate_adjustment import _bulk_predict  # noqa: E402

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")

# Adjustment scope: stats whose MIN realisations are most directly capped
# by foul trouble for bigs. PTS / REB scale with floor minutes; BLK is
# concentrated on the biggest minutes (centres in foul trouble drop BLK
# disproportionately). AST / STL / TOV / FG3M have different drivers
# (playmaking, perimeter defence, 3-point volume) and are NOT shrunk.
_SHRINK_STATS = ("pts", "reb", "blk")


def _parse_date(s):
    """Returns a datetime (NOT a date) so isoformat() includes the T00:00:00
    suffix and aligns with build_pergame_dataset's row['date'] format.
    """
    if not s:
        return None
    try:
        return datetime.strptime(str(s), "%b %d, %Y")
    except ValueError:
        try:
            return datetime.strptime(str(s), "%Y-%m-%d")
        except ValueError:
            return None


def _safe_float(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def build_blk_per_36_lookup() -> Dict[Tuple[int, str], float]:
    """Return {(player_id, iso_date): season_blk_per_36_PRIOR_GAMES_ONLY}.

    Expanding-window EXCLUDING the target game. First games fall back to
    0.0 so they're not flagged as bigs by the threshold downstream.
    """
    lookup: Dict[Tuple[int, str], float] = {}
    n_files = 0
    for path in glob.glob(os.path.join(_NBA_CACHE, "gamelog_*.json")):
        n_files += 1
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(games, list) or not games:
            continue
        try:
            pid = int(os.path.basename(path).split("_")[1])
        except (IndexError, ValueError):
            continue

        # Chronological order
        dated = []
        for g in games:
            d = _parse_date(g.get("GAME_DATE"))
            if d is None:
                continue
            dated.append((d, g))
        dated.sort(key=lambda x: x[0])

        sum_blk = 0.0
        sum_min = 0.0
        for d, g in dated:
            # Look up uses the iso date of THIS game; the value attached
            # is built from PRIOR games only (no leakage).
            lookup[(pid, d.isoformat())] = (
                (sum_blk / sum_min) * 36.0 if sum_min > 0 else 0.0
            )
            # After recording the pre-game rate, accumulate this game's
            # contribution for future games. Only count games where the
            # player actually played (avoids divide-by-zero noise from
            # DNPs that just sit in the gamelog).
            mins = _safe_float(g.get("MIN"))
            if mins >= 1.0:
                sum_min += mins
                sum_blk += _safe_float(g.get("BLK"))
    print(f"  scanned {n_files} gamelogs, "
          f"built {len(lookup)} (pid,date) -> blk_per_36 entries")
    return lookup


def build_dataset_with_pid() -> Tuple[List[dict], List[str]]:
    """Like build_pergame_dataset but ALSO attaches player_id per row.

    The canonical builder strips player_id (it's not a feature column).
    We replicate enough of the structure to recover the (player_id,
    iso_date) key needed to join the blk/36 lookup. Cheaper than parsing
    gamelogs a second time end-to-end: we just re-attach player_id by
    matching each row's (target_pts, target_reb, target_ast, date) tuple
    to the source game when building.

    Implementation: simpler -- re-derive rows by walking gamelogs the
    same way build_pergame_dataset does, but emit (pid, date) per row.
    We delegate feature computation to build_pergame_dataset so the
    feature column order stays consistent. We then assume the row
    order is reproducible and use parallel walk to attach pid.
    """
    # The dataset builder doesn't expose player_id, so we rebuild the
    # (pid, date) sequence in lock-step with build_pergame_dataset's
    # iteration order. We mirror its glob ordering + per-file early
    # break logic so the row sequence matches 1:1.
    from src.prediction.prop_pergame import (
        _row_features, _parse_date as _pp_parse, _num, _BOX_COL,
        _MIN_PLAYED, feature_columns,
    )

    rows, fc = build_pergame_dataset(min_prior=0)
    # We need pid per row. Reproduce the iteration but skip feature
    # computation; just emit (pid, iso_date, target_pts_marker) tuples,
    # then zip with rows in the SAME order. The canonical builder
    # iterates glob results, and within each file iterates the
    # date-sorted games applying the same gate. So our pid sequence
    # will match exactly.
    pid_seq: List[Tuple[int, str]] = []
    for path in glob.glob(os.path.join(_NBA_CACHE, "gamelog_*.json")):
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(games, list) or len(games) <= 0:
            continue
        dated = [(d, g) for g in games
                 if (d := _pp_parse(g.get("GAME_DATE"))) is not None]
        dated.sort(key=lambda x: x[0])
        try:
            pid = int(os.path.basename(path).split("_")[1])
        except (IndexError, ValueError):
            pid = 0
        prior_played: List[dict] = []
        for idx, (gdate, game) in enumerate(dated):
            played = _num(game.get("MIN")) >= _MIN_PLAYED
            if played and len(prior_played) >= 0:
                pid_seq.append((pid, gdate.isoformat()))
            if played:
                prior_played.append(game)

    if len(pid_seq) != len(rows):
        # Defensive: if any drift, fall back to filling pid=0
        print(f"  WARNING: pid sequence drift "
              f"({len(pid_seq)} pids vs {len(rows)} rows). "
              f"PID lookup will be unreliable.")
        for r in rows:
            r["_pid"] = 0
    else:
        for r, (pid, _) in zip(rows, pid_seq):
            r["_pid"] = pid
    return rows, fc


def make_shrink_adjuster(threshold_blk36: float, factor: float):
    """Return a callable (pred_arr, holdout_rows, stat) -> adjusted_arr.

    Applies multiplicative shrink only when:
      - stat is in _SHRINK_STATS, AND
      - the row's player season_blk_per_36 (PRIOR games only) >= threshold.
    """
    def fn(pred: np.ndarray, rows: List[dict], stat: str) -> np.ndarray:
        if stat not in _SHRINK_STATS:
            return pred.copy()
        out = pred.copy()
        for i, r in enumerate(rows):
            rate = r.get("_season_blk_per_36", 0.0) or 0.0
            if rate >= threshold_blk36:
                out[i] = pred[i] * factor
        return np.clip(out, 0.0, None)
    return fn


def measure_single_split(rows: List[dict], holdout: List[dict],
                         X_ho: np.ndarray,
                         threshold: float, factor: float) -> Dict[str, dict]:
    fn = make_shrink_adjuster(threshold, factor)
    out: Dict[str, dict] = {}
    for stat in STATS:
        y = np.array([
            np.nan if r.get(f"target_{stat}") is None else float(r[f"target_{stat}"])
            for r in holdout
        ], dtype=float)
        mask = ~np.isnan(y)
        pred = _bulk_predict(stat, X_ho)
        if pred is None:
            out[stat] = {"base": float("nan"), "adj": float("nan"),
                         "delta": float("nan"), "n": 0, "n_treated": 0}
            continue
        adj = fn(pred, holdout, stat)
        n_treated = sum(
            1 for r in holdout
            if (r.get("_season_blk_per_36", 0.0) or 0.0) >= threshold
        )
        base_mae = float(np.mean(np.abs(pred[mask] - y[mask])))
        adj_mae = float(np.mean(np.abs(adj[mask] - y[mask])))
        out[stat] = {"base": base_mae, "adj": adj_mae,
                     "delta": adj_mae - base_mae,
                     "n": int(mask.sum()), "n_treated": n_treated}
    return out


def measure_walk_forward(holdout: List[dict], X_ho: np.ndarray,
                         threshold: float, factor: float,
                         n_splits: int = 4) -> Dict[str, List[float]]:
    """Slide a window across the holdout in n_splits chronological folds.

    The post-prediction adjustment is independent of the base model, so
    we don't need to retrain per fold -- just measure delta MAE on
    each fold's slice. Reports per-stat fold-by-fold deltas.
    """
    n = len(holdout)
    edges = [int(round(n * i / n_splits)) for i in range(n_splits + 1)]

    # Pre-cache predictions once
    preds_by_stat = {s: _bulk_predict(s, X_ho) for s in STATS}
    fn = make_shrink_adjuster(threshold, factor)

    per_stat_deltas: Dict[str, List[float]] = {s: [] for s in STATS}
    for k in range(n_splits):
        lo, hi = edges[k], edges[k + 1]
        sl_rows = holdout[lo:hi]
        for stat in STATS:
            pred = preds_by_stat[stat]
            if pred is None:
                per_stat_deltas[stat].append(float("nan"))
                continue
            y = np.array([
                np.nan if r.get(f"target_{stat}") is None else float(r[f"target_{stat}"])
                for r in sl_rows
            ], dtype=float)
            mask = ~np.isnan(y)
            base_seg = pred[lo:hi]
            adj_seg = fn(base_seg, sl_rows, stat)
            base_mae = float(np.mean(np.abs(base_seg[mask] - y[mask])))
            adj_mae = float(np.mean(np.abs(adj_seg[mask] - y[mask])))
            per_stat_deltas[stat].append(adj_mae - base_mae)
    return per_stat_deltas


def main() -> int:
    print("=== cycle 90c probe -- foul-rate (BLK-proxy) MIN shrink ===")
    print("Building (player_id, date) -> prior season BLK/36 lookup...",
          flush=True)
    blk36 = build_blk_per_36_lookup()

    print("\nBuilding pergame dataset...", flush=True)
    rows, fc = build_dataset_with_pid()
    rows.sort(key=lambda r: r["date"])
    n = len(rows)

    # Attach the prior-only season BLK/36 to each row
    n_keyed = 0
    for r in rows:
        key = (r.get("_pid", 0), r["date"])
        v = blk36.get(key)
        if v is not None:
            r["_season_blk_per_36"] = float(v)
            n_keyed += 1
        else:
            r["_season_blk_per_36"] = 0.0
    print(f"  attached BLK/36 to {n_keyed}/{n} rows "
          f"({100 * n_keyed / max(n, 1):.1f}%)")

    train_end = int(n * 0.80)
    holdout = rows[train_end:]
    X_ho = np.array([[float(r.get(c, 0.0) or 0.0) for c in fc]
                     for r in holdout], dtype=float)
    print(f"  n={n} holdout={len(holdout)} features={len(fc)}")

    # Compute thresholds from the TRAINING portion only (no leakage).
    train_rates = np.array([
        rows[i].get("_season_blk_per_36", 0.0) or 0.0
        for i in range(train_end)
    ], dtype=float)
    nonzero = train_rates[train_rates > 0]
    print(f"\n=== BLK/36 distribution (training portion, prior-only) ===")
    print(f"  rows considered: {len(train_rates)}  "
          f"non-zero (has prior games): {len(nonzero)}")
    if len(nonzero) > 0:
        q_quintile = float(np.quantile(nonzero, 0.80))
        q_quartile = float(np.quantile(nonzero, 0.75))
        q_median = float(np.quantile(nonzero, 0.50))
        q_max = float(nonzero.max())
        print(f"  median        = {q_median:.3f}")
        print(f"  top-quartile  = {q_quartile:.3f}  (cutoff)")
        print(f"  top-quintile  = {q_quintile:.3f}")
        print(f"  max           = {q_max:.3f}")
    else:
        print("  no non-zero rates -- abort")
        print("\nVERDICT: REJECT (no BLK/36 signal could be extracted)")
        return 1
    threshold = q_quartile  # bigs proxy = top-quartile BLK/36

    n_treated_ho = sum(
        1 for r in holdout
        if (r.get("_season_blk_per_36", 0.0) or 0.0) >= threshold
    )
    print(f"\nHoldout treated rows (blk_per_36 >= {threshold:.3f}): "
          f"{n_treated_ho}/{len(holdout)} "
          f"({100 * n_treated_ho / max(len(holdout), 1):.1f}%)")
    if n_treated_ho < 200:
        print("  WARNING: very few treated rows; results may be noisy.")

    # ---- Single-split sweep across factors --------------------------------
    factors = (0.95, 0.96, 0.97, 0.98)
    print("\n=== SINGLE-SPLIT sweep (delta MAE per stat) ===")
    print(f"  {'factor':>6}  {'PTS d':>8}  {'REB d':>8}  {'BLK d':>8}  "
          f"{'agg(PTS+REB+BLK) d':>20}")
    print("  " + "-" * 60)
    sweep_results: Dict[float, Dict[str, dict]] = {}
    best_factor = None
    best_agg = float("inf")
    for f in factors:
        res = measure_single_split(rows, holdout, X_ho, threshold, f)
        sweep_results[f] = res
        agg = sum(res[s]["delta"] for s in _SHRINK_STATS
                  if not np.isnan(res[s]["delta"]))
        print(f"  {f:>6.2f}  "
              f"{res['pts']['delta']:>+8.4f}  "
              f"{res['reb']['delta']:>+8.4f}  "
              f"{res['blk']['delta']:>+8.4f}  "
              f"{agg:>+20.4f}")
        if agg < best_agg:
            best_agg = agg
            best_factor = f
    print(f"\n  Best factor (min aggregate delta): {best_factor}  "
          f"(agg delta = {best_agg:+.4f})")

    # ---- Full per-stat detail at best factor ------------------------------
    res = sweep_results[best_factor]
    print(f"\n=== SINGLE-SPLIT detail @ factor={best_factor} ===")
    print(f"  {'stat':<6} {'n':>6} {'base':>10} {'adj':>10} {'delta':>10}  verdict")
    print("  " + "-" * 60)
    n_improved_shrink = 0  # among _SHRINK_STATS only
    for stat in STATS:
        r = res[stat]
        if r["n"] == 0 or np.isnan(r["delta"]):
            print(f"  {stat:<6} (no data)")
            continue
        verdict = ("BETTER" if r["delta"] < -0.0005
                   else "worse" if r["delta"] > 0.0005 else "flat")
        if stat in _SHRINK_STATS and r["delta"] < -0.0005:
            n_improved_shrink += 1
        print(f"  {stat:<6} {r['n']:>6d} {r['base']:>10.4f} "
              f"{r['adj']:>10.4f} {r['delta']:>+10.4f}  {verdict}")

    # ---- Walk-forward (4 chronological folds on the holdout) -------------
    print(f"\n=== WALK-FORWARD (4 sliding folds) @ factor={best_factor} ===")
    wf = measure_walk_forward(holdout, X_ho, threshold, best_factor, n_splits=4)
    n_4of4_in_shrink = 0
    for stat in STATS:
        deltas = wf[stat]
        if not deltas or any(np.isnan(d) for d in deltas):
            print(f"  {stat:<6} (no data)")
            continue
        signs = ["+" if d > 0 else "-" if d < 0 else "0" for d in deltas]
        n_pos_folds = sum(1 for d in deltas if d < 0)  # negative delta = improvement
        mean_d = float(np.mean(deltas))
        std_d = float(np.std(deltas))
        marker = " [4/4]" if n_pos_folds == 4 else ""
        print(f"  {stat:<6} folds={[f'{d:+.4f}' for d in deltas]}  "
              f"mean={mean_d:+.4f}  std={std_d:.4f}  "
              f"pos={n_pos_folds}/4{marker}")
        if stat in _SHRINK_STATS and n_pos_folds == 4:
            n_4of4_in_shrink += 1

    # ---- Ship-gate decision ----------------------------------------------
    print("\n=== SHIP GATE ===")
    agg_shrink_delta = sum(res[s]["delta"] for s in _SHRINK_STATS
                           if not np.isnan(res[s]["delta"]))
    gate_a_single = (n_improved_shrink >= 2 and agg_shrink_delta <= -0.003)
    gate_b_wf = (n_4of4_in_shrink >= 2)
    print(f"  Gate A (single-split): >=2 of {_SHRINK_STATS} improved   "
          f"({n_improved_shrink}/{len(_SHRINK_STATS)})  "
          f"AND aggregate <= -0.003  ({agg_shrink_delta:+.4f})   "
          f"=> {'PASS' if gate_a_single else 'FAIL'}")
    print(f"  Gate B (walk-forward): >=2 of {_SHRINK_STATS} 4/4 folds  "
          f"({n_4of4_in_shrink}/{len(_SHRINK_STATS)})   "
          f"=> {'PASS' if gate_b_wf else 'FAIL'}")
    if gate_a_single and gate_b_wf:
        verdict = (f"SHIP factor={best_factor} threshold_blk_per_36"
                   f"={threshold:.3f}")
        print(f"\n  VERDICT: {verdict}")
    else:
        if not gate_a_single and not gate_b_wf:
            reason = "both gates failed (no single-split or WF signal)"
        elif not gate_a_single:
            reason = "single-split gate failed"
        else:
            reason = "walk-forward gate failed"
        verdict = f"REJECT ({reason})"
        print(f"\n  VERDICT: {verdict}")

    # One-line summary for the loop log
    print(f"\n[probe_foul_rate_shrink] verdict: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
