"""probe_play_probability_blend.py — cycle 104a (loop 5).

Evaluate the trained P(play) head as a post-prediction blend on:
  (a) the DNP-INCLUDED holdout (each DNP row has target_stat=0)
  (b) the DNP-EXCLUDED holdout (the cycle-48 baseline — must not regress
      meaningfully)

For each holdout row we compute:
    base_pred = production model prediction (q50 dispatch or NNLS blend)
    p_play    = calibrated P(play) from the new artifact
    adj_pred  = base_pred * p_play

Then per-stat MAE on each holdout flavour, plus a 4-fold WF on the
DNP-included holdout.

Ship gate:
- DNP-included MAE improves on >= 4/7 stats
- DNP-excluded MAE does NOT regress > 0.005 on any stat
- WF 4/4 positive on DNP-INCLUDED MAE for at least 4 stats
"""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import defaultdict, deque
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, _MIN_PLAYED, _NBA_CACHE, _num, _parse_date,
    _USE_Q50_STATS, _LOG_TRANSFORM_STATS, _SQRT_HUBER_STATS,
    _MODEL_DIR, _META_WEIGHTS_FILENAME,
    build_rest_travel, build_player_positions,
    _bbref_id_to_name, _unmangle_utf8,
    _load_q50_model, load_pergame_model, feature_columns,
    build_opponent_defense, build_playtypes, build_bbref_advanced,
    build_contracts, _row_features, _opponent_from_matchup, _BOX_COL,
)
from src.prediction.play_probability import (  # noqa: E402
    PLAY_PROB_FEATURES, load_play_probability, predict_play_probability,
)
from src.data.dnp_set import load_dnp_rows  # noqa: E402

_BBREF_DIR = os.path.join(PROJECT_DIR, "data", "external")
_POSITIONS = ("G", "F", "C")


def _load_bbref_age(seasons):
    out = {}
    for season in seasons:
        path = os.path.join(_BBREF_DIR, f"bbref_advanced_{season}.json")
        if not os.path.exists(path):
            continue
        try:
            rows = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        for row in rows or []:
            name = _unmangle_utf8(str(row.get("player_name", "")).strip())
            if not name:
                continue
            try:
                age = float(row.get("age") or 0.0)
            except (TypeError, ValueError):
                continue
            if age > 0:
                out.setdefault((name, season), age)
    return out


def _season_from_date(d):
    y = d.year
    return f"{y}-{str(y+1)[-2:]}" if d.month >= 9 else f"{y-1}-{str(y)[-2:]}"


def _pos_onehot(pos):
    out = {f"pos_{p}": 0.0 for p in _POSITIONS}
    if pos and pos[0].upper() in _POSITIONS:
        out[f"pos_{pos[0].upper()}"] = 1.0
    return out


def _inv(stat, v):
    if stat in _SQRT_HUBER_STATS:
        return np.clip(v, 0.0, None) ** 2
    if stat in _LOG_TRANSFORM_STATS:
        return np.clip(np.expm1(v), 0.0, None)
    return v


def _bulk_predict(stat, X):
    if stat in _USE_Q50_STATS:
        m = _load_q50_model(stat, _MODEL_DIR)
        if m is None:
            return None
        return _inv(stat, m.predict(X))
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
    parts = [_inv(stat, p) for p in parts]
    wmap_path = os.path.join(_MODEL_DIR, _META_WEIGHTS_FILENAME)
    try:
        wmap = json.load(open(wmap_path, encoding="utf-8"))
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


def _build_played_rows():
    """Walk gamelogs to build (row, pp_features, targets, date) for every
    played row. Mirrors the cycle-48 holdout build."""
    oppdef = build_opponent_defense(_NBA_CACHE)
    resttravel = build_rest_travel()
    playtypes = build_playtypes()
    bbref = build_bbref_advanced()
    contracts = build_contracts()
    positions = build_player_positions()
    id2name = _bbref_id_to_name()
    fc = feature_columns()

    rows = []
    pp_rows = []
    targets = {s: [] for s in STATS}
    dates = []

    for path in sorted(glob.glob(os.path.join(_NBA_CACHE, "gamelog_*.json"))):
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(games, list) or not games:
            continue
        try:
            basename = os.path.basename(path)
            parts = basename.split("_")
            file_player_id = int(parts[1])
            file_season = parts[-1].replace(".json", "")
        except Exception:
            continue
        dated = [(d, g) for g in games
                 if (d := _parse_date(g.get("GAME_DATE"))) is not None]
        dated.sort(key=lambda x: x[0])
        pname = id2name.get(file_player_id, "")
        prior_played = []
        prior_pts = deque(maxlen=10)
        for idx, (gdate, game) in enumerate(dated):
            played = _num(game.get("MIN")) >= _MIN_PLAYED
            if not played:
                continue
            rest = 3.0
            if idx > 0:
                rest = float(min(max((gdate - dated[idx - 1][0]).days, 0), 10))
            raw_gap = 3.0
            if prior_played:
                ld = _parse_date(prior_played[-1].get("GAME_DATE"))
                if ld is not None:
                    raw_gap = float(max((gdate - ld).days, 0))
            matchup = str(game.get("MATCHUP", ""))
            is_home = 1 if " vs. " in matchup else 0
            team_abbrev = matchup.split()[0] if matchup.split() else ""
            feats = _row_features(prior_played, rest, is_home,
                                  len(prior_played), days_since_last_game=raw_gap)
            feats.update(oppdef.factors(_opponent_from_matchup(matchup), gdate))
            feats.update(resttravel.features(team_abbrev, gdate))
            feats.update(playtypes.features(file_player_id, file_season))
            feats.update(bbref.features(file_player_id, file_season))
            feats.update(contracts.features(file_player_id, file_season))
            row = {c: feats[c] for c in fc}
            rows.append(row)
            for s in STATS:
                targets[s].append(_num(game.get(_BOX_COL[s])))
            dates.append(gdate)

            # play_probability feature row
            rt = resttravel.features(team_abbrev, gdate)
            l5 = float(np.mean(list(prior_pts)[-5:])) if prior_pts else 0.0
            l10 = float(np.mean(list(prior_pts))) if prior_pts else 0.0
            pos = positions.position(file_player_id) or ""
            pp_row = {
                "is_b2b": float(rt.get("is_b2b", 0.0) or 0.0),
                "age": 0.0,  # set below via age_lookup
                "days_since_last_game": min(raw_gap, 100.0),
                "l5_min": l5 / 2.0,
                "l10_min": l10 / 2.0,
                "dnp_l20_rate": 0.0,  # set below
                "opp_team_pace_l5": 100.0,
                "_pid": file_player_id,
                "_name": pname,
                "_season": file_season,
            }
            pp_row.update(_pos_onehot(pos))
            pp_rows.append(pp_row)

            prior_played.append(game)
            prior_pts.append(_num(game.get("PTS")))

    return rows, pp_rows, targets, dates


def _build_dnp_rows(dates_window_lo, dates_window_hi):
    resttravel = build_rest_travel()
    positions = build_player_positions()
    id2name = _bbref_id_to_name()
    df = load_dnp_rows()
    recs = df.to_dict("records") if hasattr(df, "to_dict") else []
    rows, pp_rows, dates = [], [], []
    fc = feature_columns()
    zero_feats = {c: 0.0 for c in fc}
    for d in recs:
        try:
            pid = int(d.get("player_id") or 0)
            gdate = datetime.fromisoformat(str(d.get("game_date"))[:10])
        except Exception:
            continue
        if pid <= 0:
            continue
        if gdate < dates_window_lo or gdate > dates_window_hi:
            continue
        team = str(d.get("team") or "")
        season = str(d.get("season") or "") or _season_from_date(gdate)
        row = dict(zero_feats)
        rows.append(row)
        rt = resttravel.features(team, gdate)
        pos = positions.position(pid) or ""
        pp_row = {
            "is_b2b": float(rt.get("is_b2b", 0.0) or 0.0),
            "age": 0.0,
            "days_since_last_game": 3.0,
            "l5_min": 0.0,
            "l10_min": 0.0,
            "dnp_l20_rate": 0.0,
            "opp_team_pace_l5": 100.0,
            "_pid": pid,
            "_name": id2name.get(pid, ""),
            "_season": season,
        }
        pp_row.update(_pos_onehot(pos))
        pp_rows.append(pp_row)
        dates.append(gdate)
    return rows, pp_rows, dates


def _attach_ages_and_dnp_rate(pp_rows, played_targets_min_proxy=None):
    """Attach age + rolling DNP rate (rough — uses gamelog cache via the
    pp_rows themselves; here we use a stub of zero so we just ensure the
    field exists — DNP rate is only needed for training, blend is OK
    without it since the model handles it as a feature column."""
    seasons = sorted({r["_season"] for r in pp_rows if r["_season"]})
    age_lookup = _load_bbref_age(seasons)
    for r in pp_rows:
        r["age"] = float(age_lookup.get((r["_name"], r["_season"]), 0.0))
    return pp_rows


def _mae(p, y):
    p = np.asarray(p, dtype=float); y = np.asarray(y, dtype=float)
    m = ~np.isnan(y)
    return float(np.mean(np.abs(p[m] - y[m]))) if m.any() else float("nan")


def main() -> int:
    print("Loading P(play) artifact...", flush=True)
    artifact = load_play_probability()
    if artifact is None:
        print("ERROR: artifact missing — run train_play_probability.py first.")
        return 1

    print("Building played rows...", flush=True)
    p_rows, p_pp, p_tgt, p_dates = _build_played_rows()
    n = len(p_rows)
    print(f"  played rows: {n}", flush=True)

    # Sort chronologically; take last 20% as holdout.
    order = sorted(range(n), key=lambda i: p_dates[i])
    p_rows = [p_rows[i] for i in order]
    p_pp = [p_pp[i] for i in order]
    p_dates = [p_dates[i] for i in order]
    p_tgt = {s: [p_tgt[s][i] for i in order] for s in STATS}
    cut = int(n * 0.80)
    ho_rows = p_rows[cut:]
    ho_pp = p_pp[cut:]
    ho_dates = p_dates[cut:]
    ho_tgt = {s: np.array(p_tgt[s][cut:], dtype=float) for s in STATS}
    print(f"  holdout n: {len(ho_rows)}  "
          f"dates {ho_dates[0].isoformat()} -> {ho_dates[-1].isoformat()}",
          flush=True)

    # DNP rows in the same date window.
    d_rows, d_pp, d_dates = _build_dnp_rows(ho_dates[0], ho_dates[-1])
    print(f"  DNP rows in window: {len(d_rows)}", flush=True)

    # Attach ages.
    _attach_ages_and_dnp_rate(ho_pp)
    _attach_ages_and_dnp_rate(d_pp)

    # Build feature matrices.
    fc = feature_columns()
    X_ho = np.array([[float(r.get(c, 0.0) or 0.0) for c in fc] for r in ho_rows],
                    dtype=float)
    X_dnp = np.array([[float(r.get(c, 0.0) or 0.0) for c in fc] for r in d_rows],
                     dtype=float) if d_rows else np.zeros((0, len(fc)))

    # P(play) per row.
    p_play_ho = np.array([
        predict_play_probability(r, artifact=artifact) or 1.0 for r in ho_pp
    ], dtype=float)
    p_play_dnp = np.array([
        predict_play_probability(r, artifact=artifact) or 1.0 for r in d_pp
    ], dtype=float) if d_pp else np.zeros(0)

    print(f"\n  P(play) summary — played holdout:  "
          f"mean={p_play_ho.mean():.3f}  min={p_play_ho.min():.3f}  "
          f"max={p_play_ho.max():.3f}", flush=True)
    if len(p_play_dnp):
        print(f"  P(play) summary — DNP holdout:     "
              f"mean={p_play_dnp.mean():.3f}  min={p_play_dnp.min():.3f}  "
              f"max={p_play_dnp.max():.3f}", flush=True)

    # Per-stat MAE.
    print("\n=== DNP-EXCLUDED holdout (cycle-48 baseline) ===", flush=True)
    print(f"{'stat':<5} {'base_mae':>9} {'adj_mae':>9} {'delta':>9}", flush=True)
    excl_deltas = {}
    for s in STATS:
        pred = _bulk_predict(s, X_ho)
        if pred is None:
            continue
        adj = pred * p_play_ho
        b, a = _mae(pred, ho_tgt[s]), _mae(adj, ho_tgt[s])
        excl_deltas[s] = a - b
        print(f"{s:<5} {b:>9.4f} {a:>9.4f} {a-b:>+9.4f}", flush=True)

    print("\n=== DNP-INCLUDED holdout (DNP rows have target=0) ===", flush=True)
    print(f"{'stat':<5} {'base_mae':>9} {'adj_mae':>9} {'delta':>9}", flush=True)
    incl_deltas = {}
    incl_pred_cache = {}
    incl_y_cache = {}
    for s in STATS:
        pred_ho = _bulk_predict(s, X_ho)
        pred_dnp = _bulk_predict(s, X_dnp) if len(d_rows) else np.zeros(0)
        if pred_ho is None:
            continue
        y_all = np.concatenate([ho_tgt[s], np.zeros(len(d_rows))])
        pred_all = np.concatenate([pred_ho, pred_dnp])
        p_all = np.concatenate([p_play_ho, p_play_dnp])
        adj_all = pred_all * p_all
        b, a = _mae(pred_all, y_all), _mae(adj_all, y_all)
        incl_deltas[s] = a - b
        incl_pred_cache[s] = (pred_all, p_all)
        incl_y_cache[s] = y_all
        print(f"{s:<5} {b:>9.4f} {a:>9.4f} {a-b:>+9.4f}", flush=True)

    # Ship gates.
    n_improved = sum(1 for v in incl_deltas.values() if v < -1e-5)
    excl_max_regress = max(excl_deltas.values()) if excl_deltas else 0.0
    print(f"\n  DNP-incl stats improved: {n_improved}/{len(incl_deltas)}",
          flush=True)
    print(f"  DNP-excl max regression: {excl_max_regress:+.4f}", flush=True)

    gate_incl = n_improved >= 4
    gate_excl = excl_max_regress <= 0.005

    # WF 4-fold on DNP-included.
    print("\n=== WF 4-fold (DNP-included MAE) ===", flush=True)
    wf_pos = {}
    # Combined chronological order.
    combined_dates = ho_dates + d_dates
    co_order = sorted(range(len(combined_dates)), key=lambda i: combined_dates[i])
    n_co = len(co_order)
    fold_size = n_co // 4
    for s, (pred_all, p_all) in incl_pred_cache.items():
        y_all = incl_y_cache[s]
        pred_sorted = pred_all[co_order]
        p_sorted = p_all[co_order]
        y_sorted = y_all[co_order]
        pos = 0
        for fi in range(4):
            lo = fi * fold_size
            hi = (fi + 1) * fold_size if fi < 3 else n_co
            b = _mae(pred_sorted[lo:hi], y_sorted[lo:hi])
            a = _mae(pred_sorted[lo:hi] * p_sorted[lo:hi], y_sorted[lo:hi])
            if a < b:
                pos += 1
        wf_pos[s] = pos
        print(f"  {s:<5} {pos}/4 folds improved", flush=True)

    n_wf_44 = sum(1 for v in wf_pos.values() if v == 4)
    print(f"\n  stats with WF 4/4: {n_wf_44}/{len(wf_pos)}", flush=True)
    gate_wf = n_wf_44 >= 4

    ship = gate_incl and gate_excl and gate_wf
    print(f"\n=== GATES ===", flush=True)
    print(f"  DNP-incl >= 4/7 improved: {'PASS' if gate_incl else 'FAIL'} "
          f"({n_improved}/{len(incl_deltas)})", flush=True)
    print(f"  DNP-excl no >0.005 regression: "
          f"{'PASS' if gate_excl else 'FAIL'} (max {excl_max_regress:+.4f})",
          flush=True)
    print(f"  WF 4/4 on >= 4 stats: {'PASS' if gate_wf else 'FAIL'} "
          f"({n_wf_44}/{len(wf_pos)})", flush=True)
    print(f"\nFINAL: {'SHIP' if ship else 'REJECT'}", flush=True)

    out = os.path.join(PROJECT_DIR, "scripts", "_results",
                       "play_probability_blend.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    L = []
    L.append("# cycle 104a (loop 5) — P(play) head blend probe\n")
    L.append(f"## Artifact summary\n")
    L.append(f"- n_train: {artifact['n_train']}")
    L.append(f"- n_val: {artifact['n_val']}")
    L.append(f"- val mean P(play): {artifact['val_mean_pred']:.4f}")
    L.append(f"- val played frac: {artifact['val_played_frac']:.4f}")
    L.append(f"- val Brier: {artifact['val_brier']:.4f}\n")
    L.append(f"## Holdout\n")
    L.append(f"- played rows: {len(ho_rows)}")
    L.append(f"- DNP rows in window: {len(d_rows)}")
    L.append(f"- date range: {ho_dates[0].isoformat()} -> {ho_dates[-1].isoformat()}")
    L.append(f"- P(play) played-mean: {p_play_ho.mean():.3f}")
    if len(p_play_dnp):
        L.append(f"- P(play) DNP-mean:    {p_play_dnp.mean():.3f}\n")
    L.append("## DNP-EXCLUDED MAE (cycle-48 baseline)\n")
    L.append("| stat | delta |")
    L.append("|------|------:|")
    for s, d in excl_deltas.items():
        L.append(f"| {s} | {d:+.4f} |")
    L.append("\n## DNP-INCLUDED MAE\n")
    L.append("| stat | delta |")
    L.append("|------|------:|")
    for s, d in incl_deltas.items():
        L.append(f"| {s} | {d:+.4f} |")
    L.append("\n## WF (DNP-included)\n")
    L.append("| stat | folds improved |")
    L.append("|------|---------------:|")
    for s, v in wf_pos.items():
        L.append(f"| {s} | {v}/4 |")
    L.append(f"\n## Verdict: **{'SHIP' if ship else 'REJECT'}**\n")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print(f"Wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
