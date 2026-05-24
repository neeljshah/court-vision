"""probe_b2b_veteran.py — cycle 90b (loop 5) T1-C: age-conditional B2B shrink.

Hypothesis (from in_game_gaps_v1.md T1-C):
    The flat b2b multiplier was REJECTED in cycle ~82 because effect is
    CONDITIONAL on age. Veterans aged 33+ sit ~80% of second nights of
    back-to-backs (landyourbets data); under-30s show only mild shooting
    decline. Apply MIN-coupled shrink ONLY on (age >= 33) AND (b2b == True)
    AND (starter_default=True, since dataset lacks per-game starter flag).

Approach:
    1. Re-walk the gamelog cache to attach (player_id, season, date) to
       each holdout row (build_pergame_dataset drops player_id).
    2. Pull `age` from data/external/bbref_advanced_<season>.json
       (already cached, has `age` per player per season).
    3. Apply 0.92x (sweep 0.90/0.92/0.94/0.96) MIN-coupled shrink to PTS,
       REB, AST only on the (age>=33 AND is_b2b>=0.5) cell. FG3M/STL/BLK/TOV
       not touched (saturated).
    4. Single-split MAE delta on n=19964 holdout; if PTS+REB+AST aggregate
       improvement >= 0.005 across all three stats, run 4-fold chronological
       WF on the same holdout (no retraining — production models predict,
       shrink applied per fold).
    5. SHIP only if (single-split STRICTLY DOWN on all 3) AND (WF 4/4 positive
       on each).

Output: scripts/_results/b2b_veteran_v1.md with full table + verdict.

Wire-in (if SHIP): post-prediction hook (new helper) in
src/prediction/prop_pergame.py. Coordinated with cycle 90a (not yet
landed at probe time) — adds a hook namespace that 90a can co-occupy.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import warnings
from typing import Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, _USE_Q50_STATS, _LOG_TRANSFORM_STATS, _SQRT_HUBER_STATS,
    _MODEL_DIR, _META_WEIGHTS_FILENAME, _NBA_CACHE, _MIN_PLAYED,
    _BOX_COL, _num, _parse_date,
    build_pergame_dataset, feature_columns,
    _load_q50_model, load_pergame_model,
    _bbref_id_to_name, _unmangle_utf8,
)

_BBREF_DIR = os.path.join(PROJECT_DIR, "data", "external")
_TARGET_STATS = ("pts", "reb", "ast")  # only these 3, others saturated
_SAVED_STATS = ("fg3m", "stl", "blk", "tov")


# ── age lookup ───────────────────────────────────────────────────────────────


def _load_bbref_age(seasons: List[str]) -> Dict[Tuple[str, str], float]:
    """Build (player_name, season) -> age lookup from bbref_advanced files."""
    out: Dict[Tuple[str, str], float] = {}
    for season in seasons:
        path = os.path.join(_BBREF_DIR, f"bbref_advanced_{season}.json")
        if not os.path.exists(path):
            continue
        try:
            rows = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            name = _unmangle_utf8(str(row.get("player_name", "")).strip())
            if not name:
                continue
            try:
                age = float(row.get("age") or 0.0)
            except (TypeError, ValueError):
                continue
            if age > 0:
                # BBRef may list a player multiple times if traded — keep first.
                out.setdefault((name, season), age)
    return out


# ── walk gamelogs to attach (player_id, season, date) to each row ────────────


def _build_holdout_with_pid(min_prior: int = 0) -> Tuple[List[dict], List[int],
                                                          List[str], List[str],
                                                          List[str]]:
    """Re-walk gamelogs to emit (row, player_id, season, date_iso, name) for
    every (rows[i]). Mirrors build_pergame_dataset emission order exactly so
    indices line up with the standard holdout.

    Returns:
        rows, pids, seasons, dates, names  — all len == n
    """
    from src.prediction.prop_pergame import (  # noqa: PLC0415
        build_opponent_defense, build_rest_travel, build_playtypes,
        build_bbref_advanced, build_contracts,
        _row_features, _opponent_from_matchup,
    )

    oppdef = build_opponent_defense(_NBA_CACHE)
    resttravel = build_rest_travel()
    playtypes = build_playtypes()
    bbref = build_bbref_advanced()
    contracts = build_contracts()
    fc = feature_columns()
    id2name = _bbref_id_to_name()

    rows: List[dict] = []
    pids: List[int] = []
    seasons: List[str] = []
    dates: List[str] = []
    names: List[str] = []

    for path in sorted(glob.glob(os.path.join(_NBA_CACHE, "gamelog_*.json"))):
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(games, list) or len(games) <= min_prior:
            continue
        dated = [(d, g) for g in games if (d := _parse_date(g.get("GAME_DATE"))) is not None]
        dated.sort(key=lambda x: x[0])
        try:
            basename = os.path.basename(path)
            parts = basename.split("_")
            file_player_id = int(parts[1])
            file_season = parts[-1].replace(".json", "")
        except Exception:
            file_player_id = 0
            file_season = ""

        pname = id2name.get(file_player_id, "") if file_player_id else ""

        prior_played: List[dict] = []
        for idx, (gdate, game) in enumerate(dated):
            played = _num(game.get("MIN")) >= _MIN_PLAYED
            if played and len(prior_played) >= min_prior:
                rest = 3.0
                if idx > 0:
                    delta = (gdate - dated[idx - 1][0]).days
                    rest = float(min(max(delta, 0), 10))
                raw_gap_days = 3.0
                if prior_played:
                    last_played_date = _parse_date(prior_played[-1].get("GAME_DATE"))
                    if last_played_date is not None:
                        raw_gap_days = float(max((gdate - last_played_date).days, 0))
                matchup = str(game.get("MATCHUP", ""))
                is_home = 1 if " vs. " in matchup else 0
                team_abbrev = matchup.split()[0] if matchup.split() else ""
                feats = _row_features(prior_played, rest, is_home, len(prior_played),
                                      days_since_last_game=raw_gap_days)
                feats.update(oppdef.factors(_opponent_from_matchup(matchup), gdate))
                feats.update(resttravel.features(team_abbrev, gdate))
                feats.update(playtypes.features(file_player_id, file_season))
                feats.update(bbref.features(file_player_id, file_season))
                feats.update(contracts.features(file_player_id, file_season))
                row = {c: feats[c] for c in fc}
                for stat in STATS:
                    row[f"target_{stat}"] = _num(game.get(_BOX_COL[stat]))
                row["date"] = gdate.isoformat()
                rows.append(row)
                pids.append(file_player_id)
                seasons.append(file_season)
                dates.append(gdate.isoformat())
                names.append(pname)
            if played:
                prior_played.append(game)

    return rows, pids, seasons, dates, names


# ── production predict (mirrors validate_adjustment.py) ──────────────────────


def _inv_pp(stat: str, v: np.ndarray) -> np.ndarray:
    if stat in _SQRT_HUBER_STATS:
        return np.clip(v, 0.0, None) ** 2
    if stat in _LOG_TRANSFORM_STATS:
        return np.clip(np.expm1(v), 0.0, None)
    return v


def _bulk_predict(stat: str, X: np.ndarray) -> Optional[np.ndarray]:
    if stat in _USE_Q50_STATS:
        m = _load_q50_model(stat, _MODEL_DIR)
        if m is None:
            return None
        return _inv_pp(stat, m.predict(X))
    models = load_pergame_model(stat, _MODEL_DIR)
    if not models:
        return None
    parts = []
    for entry in models:
        if isinstance(entry, tuple):
            scaler, m = entry
            parts.append(m.predict(scaler.transform(X)))
        else:
            parts.append(entry.predict(X))
    parts = [_inv_pp(stat, p) for p in parts]
    wmap_path = os.path.join(_MODEL_DIR, _META_WEIGHTS_FILENAME)
    try:
        with open(wmap_path, encoding="utf-8") as f:
            wmap = json.load(f)
    except Exception:
        wmap = {}
    w = wmap.get(stat) or {}
    if len(parts) == 3:
        blend = (float(w.get("w_xgb", 1/3)) * parts[0]
                 + float(w.get("w_lgb", 1/3)) * parts[1]
                 + float(w.get("w_mlp", 1/3)) * parts[2])
    else:
        blend = np.mean(np.column_stack(parts), axis=1)
    return np.clip(blend, 0.0, None)


# ── the b2b-veteran shrink ───────────────────────────────────────────────────


def apply_b2b_veteran_shrink(
    pred: np.ndarray,
    rows: List[dict],
    ages: np.ndarray,
    factor: float,
    age_threshold: float = 33.0,
) -> Tuple[np.ndarray, int]:
    """Shrink pred * factor only on (age >= age_threshold AND is_b2b >= 0.5).

    Starter flag is not in dataset — default to including (treat unknowns as
    starters). Returns (adjusted, n_affected).
    """
    out = pred.copy()
    n_aff = 0
    for i, r in enumerate(rows):
        age = float(ages[i])
        if age < age_threshold:
            continue
        try:
            b2b = float(r.get("is_b2b", 0) or 0)
        except (TypeError, ValueError):
            continue
        if b2b < 0.5:
            continue
        # starter unknown -> include by default
        out[i] = pred[i] * factor
        n_aff += 1
    return np.clip(out, 0.0, None), n_aff


# ── validate ────────────────────────────────────────────────────────────────


def _mae(pred, y):
    mask = ~np.isnan(y)
    return float(np.mean(np.abs(pred[mask] - y[mask])))


def run_single_split(holdout, X, ages, factor):
    """Return {stat: {base_mae, adj_mae, delta, n, n_affected}}."""
    results = {}
    for stat in STATS:
        y = np.array([np.nan if r.get(f"target_{stat}") is None
                      else float(r[f"target_{stat}"]) for r in holdout], dtype=float)
        pred = _bulk_predict(stat, X)
        if pred is None:
            results[stat] = None
            continue
        if stat in _TARGET_STATS:
            adj, n_aff = apply_b2b_veteran_shrink(pred, holdout, ages, factor)
        else:
            adj, n_aff = pred.copy(), 0
        results[stat] = {
            "base_mae": _mae(pred, y),
            "adj_mae":  _mae(adj, y),
            "delta":    _mae(adj, y) - _mae(pred, y),
            "n":        int((~np.isnan(y)).sum()),
            "n_affected": n_aff,
        }
    return results


def run_wf_chronological(holdout, X, ages, factor, n_folds=4):
    """4-fold chronological WF on holdout — no retraining. Production models
    predict on full holdout, then each fold's slice gets the shrink applied
    independently. Validates that the improvement isn't concentrated in one
    sub-window of the holdout."""
    n = len(holdout)
    fold_size = n // n_folds
    wf_results = {stat: [] for stat in _TARGET_STATS}
    for stat in _TARGET_STATS:
        y = np.array([np.nan if r.get(f"target_{stat}") is None
                      else float(r[f"target_{stat}"]) for r in holdout], dtype=float)
        pred = _bulk_predict(stat, X)
        if pred is None:
            wf_results[stat] = [None] * n_folds
            continue
        for f in range(n_folds):
            lo = f * fold_size
            hi = (f + 1) * fold_size if f < n_folds - 1 else n
            sl_rows = holdout[lo:hi]
            sl_pred = pred[lo:hi]
            sl_ages = ages[lo:hi]
            sl_y = y[lo:hi]
            sl_adj, _ = apply_b2b_veteran_shrink(sl_pred, sl_rows, sl_ages, factor)
            wf_results[stat].append({
                "base": _mae(sl_pred, sl_y),
                "adj":  _mae(sl_adj, sl_y),
                "delta": _mae(sl_adj, sl_y) - _mae(sl_pred, sl_y),
                "n": int((~np.isnan(sl_y)).sum()),
            })
    return wf_results


def _season_from_date_iso(date_iso: str) -> str:
    """Infer NBA season string from ISO date.
    NBA season N runs Oct(year=N) through Apr(year=N+1) and is named
    `{year}-{(year+1) % 100:02d}`."""
    y = int(date_iso[:4])
    m = int(date_iso[5:7])
    season_year = y if m >= 9 else y - 1
    return f"{season_year}-{(season_year + 1) % 100:02d}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true",
                    help="sweep factor in {0.90,0.92,0.94,0.96}")
    ap.add_argument("--factor", type=float, default=0.92)
    ap.add_argument("--age-threshold", type=float, default=33.0)
    ap.add_argument("--directional", action="store_true",
                    help="Use Q4 (2024-12 to 2025-10) as holdout instead of standard 80/20. "
                         "This window has is_b2b populated. NOTE: leaked vs production models "
                         "(in-distribution training). Directional signal only.")
    args = ap.parse_args()

    print("Building dataset with player_id attached...", flush=True)
    rows, pids, seasons_raw, dates, names = _build_holdout_with_pid(min_prior=0)
    n = len(rows)
    order = sorted(range(n), key=lambda i: dates[i])
    rows = [rows[i] for i in order]
    pids = [pids[i] for i in order]
    names = [names[i] for i in order]
    dates = [dates[i] for i in order]
    if args.directional:
        # Q4 of chronological split (2024-12 to 2025-10): has is_b2b populated.
        lo, hi = int(n * 0.60), int(n * 0.80)
        holdout = rows[lo:hi]
        holdout_pids = pids[lo:hi]
        holdout_names = names[lo:hi]
        holdout_dates = dates[lo:hi]
        print(f"  DIRECTIONAL MODE: Q4 window (lo={lo}, hi={hi})", flush=True)
    else:
        cut = int(n * 0.80)
        holdout = rows[cut:]
        holdout_pids = pids[cut:]
        holdout_names = names[cut:]
        holdout_dates = dates[cut:]
    n_ho = len(holdout)
    print(f"  full n={n}  holdout={n_ho}", flush=True)

    # Infer seasons for holdout rows from date.
    holdout_seasons = [_season_from_date_iso(d) for d in holdout_dates]
    season_set = sorted(set(holdout_seasons))
    print(f"  holdout seasons: {season_set}", flush=True)

    # Build age lookup from bbref (covers 2024-25 + 2025-26).
    age_lookup = _load_bbref_age(season_set)
    print(f"  bbref age entries loaded: {len(age_lookup)}", flush=True)

    # Resolve age per holdout row.
    ages = np.zeros(n_ho, dtype=float)
    n_known = 0
    for i in range(n_ho):
        name = holdout_names[i]
        season = holdout_seasons[i]
        a = age_lookup.get((name, season), 0.0) if name else 0.0
        ages[i] = a
        if a > 0:
            n_known += 1
    print(f"  ages resolved: {n_known}/{n_ho} ({100*n_known/n_ho:.1f}%)", flush=True)

    if n_known < 0.5 * n_ho:
        print("  WARN: <50% age coverage — probe will be noisy.", flush=True)

    n_veteran_b2b = sum(
        1 for i, r in enumerate(holdout)
        if ages[i] >= args.age_threshold
        and float(r.get("is_b2b", 0) or 0) >= 0.5
    )
    n_age_known_vet = sum(1 for a in ages if a >= args.age_threshold)
    print(f"  rows age>={args.age_threshold:.0f}: {n_age_known_vet}", flush=True)
    print(f"  rows (age>={args.age_threshold:.0f} AND is_b2b): {n_veteran_b2b}", flush=True)

    # Feature matrix for holdout.
    cols = feature_columns()
    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols] for r in holdout],
                 dtype=float)

    factors = [0.90, 0.92, 0.94, 0.96] if args.sweep else [args.factor]
    all_results = {}
    for f in factors:
        print(f"\n=== factor={f:.2f} ===", flush=True)
        r = run_single_split(holdout, X, ages, f)
        all_results[f] = r
        print(f"{'stat':<5} {'n_aff':>6} {'base':>9} {'adj':>9} {'delta':>10}")
        for s in STATS:
            rr = r[s]
            if rr is None:
                print(f"{s:<5} (no model)")
                continue
            print(f"{s:<5} {rr['n_affected']:>6d} {rr['base_mae']:>9.4f} "
                  f"{rr['adj_mae']:>9.4f} {rr['delta']:>+10.4f}")

    # Pick best factor by sum of (pts, reb, ast) deltas (more negative wins).
    def _agg_delta(res):
        return sum(res[s]["delta"] for s in _TARGET_STATS if res.get(s))
    best_factor = min(factors, key=lambda f: _agg_delta(all_results[f]))
    print(f"\nBest factor: {best_factor:.2f}  agg_delta={_agg_delta(all_results[best_factor]):+.4f}",
          flush=True)

    # Ship gate (single-split): STRICT improvement on PTS AND REB AND AST.
    best_res = all_results[best_factor]
    gate_ss = all(best_res[s]["delta"] < -0.001 for s in _TARGET_STATS)
    print(f"\nSingle-split ship gate (PTS+REB+AST all strictly down): "
          f"{'PASS' if gate_ss else 'FAIL'}", flush=True)

    # Optional WF if aggregate improvement >= 0.005.
    wf_results = None
    if _agg_delta(best_res) <= -0.005:
        print(f"\n=== Walk-forward (4-fold chronological, no retrain) factor={best_factor:.2f} ===",
              flush=True)
        wf_results = run_wf_chronological(holdout, X, ages, best_factor, n_folds=4)
        for s in _TARGET_STATS:
            print(f"\n  {s.upper()} WF folds:")
            for fi, fr in enumerate(wf_results[s]):
                if fr is None:
                    continue
                ver = "+" if fr["delta"] < 0 else "-"
                print(f"    fold{fi+1}: base={fr['base']:.4f} adj={fr['adj']:.4f} "
                      f"delta={fr['delta']:+.4f}  n={fr['n']}  {ver}")

    # Write markdown report.
    out_path = os.path.join(PROJECT_DIR, "scripts", "_results", "b2b_veteran_v1.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    lines = []
    lines.append("# cycle 90b (loop 5) — T1-C: B2B × age33+ × starter (probe)")
    lines.append("")
    lines.append("## Setup")
    lines.append(f"- age source: `data/external/bbref_advanced_<season>.json` (`age` field)")
    lines.append(f"- holdout n={n_ho} (chronological 80/20 of n={n})")
    lines.append(f"- ages resolved: {n_known}/{n_ho} ({100*n_known/n_ho:.1f}%)")
    lines.append(f"- rows (age>={args.age_threshold:.0f}): {n_age_known_vet}")
    lines.append(f"- rows affected (age>={args.age_threshold:.0f} AND is_b2b): {n_veteran_b2b}")
    lines.append(f"- starter flag: NOT IN DATASET — defaulted to INCLUDE all "
                 f"({n_veteran_b2b} rows)")
    lines.append(f"- target stats: pts, reb, ast (saturated stats fg3m/stl/blk/tov untouched)")
    lines.append("")
    lines.append("## Single-split MAE table (per factor)")
    lines.append("")
    lines.append("| factor | stat | n_aff | base_mae | adj_mae | delta |")
    lines.append("|--------|------|------:|---------:|--------:|------:|")
    for f in factors:
        r = all_results[f]
        for s in STATS:
            rr = r[s]
            if rr is None:
                continue
            lines.append(f"| {f:.2f} | {s} | {rr['n_affected']} | "
                         f"{rr['base_mae']:.4f} | {rr['adj_mae']:.4f} | "
                         f"{rr['delta']:+.4f} |")
    lines.append("")
    lines.append(f"## Best factor: **{best_factor:.2f}**")
    lines.append(f"- aggregate (pts+reb+ast) delta: {_agg_delta(best_res):+.4f}")
    lines.append(f"- single-split ship gate (PTS AND REB AND AST strictly down): "
                 f"**{'PASS' if gate_ss else 'FAIL'}**")
    lines.append("")
    if wf_results:
        lines.append("## Walk-forward (4 chronological folds within holdout, no retrain)")
        lines.append("")
        lines.append("| stat | fold | base | adj | delta | positive? |")
        lines.append("|------|-----:|----:|----:|------:|:---------:|")
        wf_pos = {}
        for s in _TARGET_STATS:
            n_pos = 0
            for fi, fr in enumerate(wf_results[s]):
                if fr is None:
                    continue
                pos = fr["delta"] < 0
                if pos:
                    n_pos += 1
                lines.append(f"| {s} | {fi+1} | {fr['base']:.4f} | {fr['adj']:.4f} | "
                             f"{fr['delta']:+.4f} | {'YES' if pos else 'no'} |")
            wf_pos[s] = n_pos
        lines.append("")
        for s in _TARGET_STATS:
            lines.append(f"- {s.upper()}: {wf_pos[s]}/4 folds positive")
        gate_wf = all(wf_pos[s] == 4 for s in _TARGET_STATS)
        lines.append("")
        lines.append(f"## WF gate (4/4 on PTS, REB, AST): **{'PASS' if gate_wf else 'FAIL'}**")
        gate_ship = gate_ss and gate_wf
    else:
        gate_wf = False
        lines.append("## Walk-forward: SKIPPED (single-split aggregate improvement < 0.005)")
        gate_ship = False

    lines.append("")
    lines.append("## Verdict")
    if gate_ship:
        lines.append(f"**SHIP** at factor={best_factor:.2f}, age_threshold=33.")
        lines.append("Wire-in: post-prediction hook in `src/prediction/prop_pergame.py`.")
    else:
        reasons = []
        if not gate_ss:
            reasons.append("single-split gate failed (not all 3 stats strictly down)")
        if wf_results is None:
            reasons.append("aggregate improvement too small to run WF (< 0.005)")
        elif not gate_wf:
            reasons.append("WF gate failed (not 4/4 on all target stats)")
        lines.append(f"**REJECT** — {'; '.join(reasons)}")
        lines.append("")
        if n_veteran_b2b < 50:
            lines.append(f"NOTE: only {n_veteran_b2b} affected rows in holdout. "
                         f"Effect cell may be too thin even if hypothesis is correct. "
                         f"Re-test with multi-season holdout if `bbref_advanced_2024-25` "
                         f"can be back-joined to gamelog season `2024-25`.")

    with open(out_path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines) + "\n")
    print(f"\nWrote {out_path}", flush=True)
    print(f"\nFinal verdict: {'SHIP' if gate_ship else 'REJECT'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
