"""train_multitask_mlp_live.py -- tier3-9 (loop 5).

Trains :class:`src.prediction.multitask_mlp_live.MultitaskMLPLive` on the
per-game dataset (cycle-23 baseline corpus). Pre-game features come from
prop_pergame.build_pergame_dataset; live input is the zero-vector for
training (back-compat path -- live data isn't available retroactively for
every historical row, so the model learns the pre-game pathway first
and the live pathway sees zero-vectors until subsequent cycles backfill
real snapshots).

Chronological 80/20 split: earliest 80% train, latest 20% val. Writes
artifact to data/models/multitask_mlp_live.pt + meta JSON.

Usage:
    python scripts/train_multitask_mlp_live.py
    python scripts/train_multitask_mlp_live.py --max-rows 5000  (debug)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.prediction.multitask_mlp_live import (  # noqa: E402
    LIVE_DIM,
    LIVE_FEATURE_NAMES,
    MultitaskMLPLive,
    STATS,
    _invert_target_transform,
    build_live_vector,
    build_target_matrix,
)
from src.prediction.live_factors import foul_trouble_factor  # noqa: E402
from src.prediction.prop_pergame import (  # noqa: E402
    build_pergame_dataset,
    feature_columns,
)

_QPARQUET = os.path.join(PROJECT_DIR, "data", "player_quarter_stats.parquet")


def _safe_float(v) -> float:
    if v is None:
        return 0.0
    try:
        f = float(v)
        return 0.0 if f != f else f
    except (TypeError, ValueError):
        return 0.0


def _build_endq3_snapshot_from_q123(pq_rows) -> dict:
    """Aggregate Q1+Q2+Q3 into a snapshot matching LIVE_FEATURE_NAMES."""
    cur = {"pts": 0.0, "reb": 0.0, "ast": 0.0, "fg3m": 0.0,
           "stl": 0.0, "blk": 0.0, "tov": 0.0, "min": 0.0, "pf": 0.0}
    for r in pq_rows:
        try:
            p = int(r["period"])
        except (KeyError, TypeError, ValueError):
            continue
        if p < 1 or p > 3:
            continue
        for k in cur:
            cur[k] += _safe_float(r.get(k))
    return {
        "period": 4,
        "clock_min_remaining": 12.0,
        "period_share_played": 0.75,
        "current_pts": cur["pts"],
        "current_reb": cur["reb"],
        "current_ast": cur["ast"],
        "current_fg3m": cur["fg3m"],
        "current_stl": cur["stl"],
        "current_blk": cur["blk"],
        "current_tov": cur["tov"],
        "current_min": cur["min"],
        "current_pf": cur["pf"],
        "score_margin": 0.0,
        "foul_factor": foul_trouble_factor(cur["pf"], 4),
        "blow_factor": 1.0,
    }


def _build_live_lookup() -> dict:
    """Return (player_id, game_date_iso) -> live-vector dict using per-quarter parquet."""
    import json as _json
    import pandas as pd

    out = {}
    if not os.path.exists(_QPARQUET):
        print(f"  WARN: {_QPARQUET} missing; using zero-live for all training rows")
        return out

    # game_id -> game_date map
    nba_dir = os.path.join(PROJECT_DIR, "data", "nba")
    gid_to_date = {}
    if os.path.exists(nba_dir):
        for fn in sorted(os.listdir(nba_dir)):
            if not fn.startswith("season_games_") or not fn.endswith(".json"):
                continue
            try:
                payload = _json.load(open(os.path.join(nba_dir, fn), encoding="utf-8"))
            except Exception:
                continue
            for g in (payload.get("rows", payload) if isinstance(payload, dict) else payload) or []:
                gid = g.get("game_id") or g.get("GAME_ID")
                gd = g.get("game_date") or g.get("GAME_DATE")
                if gid and gd:
                    gid_to_date[str(gid).zfill(10)] = str(gd)[:10]
    print(f"  per-quarter live lookup: {len(gid_to_date)} games dated")

    qdf = pd.read_parquet(_QPARQUET)
    for gid in qdf["game_id"].unique():
        gdate = gid_to_date.get(str(gid).zfill(10))
        if not gdate:
            continue
        gdf = qdf[qdf["game_id"] == gid]
        for pid in gdf["player_id"].unique():
            try:
                pid_i = int(pid)
            except (TypeError, ValueError):
                continue
            pdf = gdf[gdf["player_id"] == pid].to_dict(orient="records")
            snap = _build_endq3_snapshot_from_q123(pdf)
            out[(pid_i, gdate)] = build_live_vector(snap)
    print(f"  per-quarter live lookup: {len(out)} (player, date) pairs")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-rows", type=int, default=None,
                    help="Cap dataset size for debugging")
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--batch-size", type=int, default=512)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--no-live-inject", action="store_true",
                    help="Disable synthesized live snapshot injection")
    args = ap.parse_args()

    t0 = time.time()
    print("  loading per-game dataset...")
    rows, feature_cols = build_pergame_dataset(min_prior=0)
    if not rows:
        print("  ERROR: empty dataset")
        return 2
    print(f"  rows={len(rows)} features={len(feature_cols)}")

    rows.sort(key=lambda r: r["date"])
    if args.max_rows and args.max_rows < len(rows):
        rows = rows[-args.max_rows:]
        print(f"  capped to last {args.max_rows} rows")

    n = len(rows)
    X_pre = np.array([[float(r.get(c, 0.0) or 0.0) for c in feature_cols]
                      for r in rows], dtype=np.float32)
    Y = build_target_matrix(rows)

    # Build X_live by joining per-quarter parquet endQ3 snapshots into the
    # per-game corpus. Rows without a per-quarter match remain zero-vectors
    # (back-compat path). Per cycle 89f T3-A spec: "Half of training samples
    # should ALSO include synthesized live features from cycle 91a's 550-game
    # per-quarter data".
    X_live = np.zeros((n, LIVE_DIM), dtype=np.float32)
    if not args.no_live_inject:
        print("  building per-quarter live lookup for training injection...")
        live_lookup = _build_live_lookup()
        n_matched = 0
        for i, r in enumerate(rows):
            try:
                pid_i = int(r.get("player_id") or 0)
            except (TypeError, ValueError):
                continue
            gdate = str(r.get("date") or "")[:10]
            if not (pid_i and gdate):
                continue
            v = live_lookup.get((pid_i, gdate))
            if v is not None:
                X_live[i] = v
                n_matched += 1
        print(f"  injected live snapshots into {n_matched}/{n} rows "
              f"({100.0 * n_matched / n:.1f}%)")
    y_raw = {s: np.array([float(r.get(f"target_{s}", 0.0)) for r in rows],
                         dtype=np.float32)
             for s in STATS}

    # Chronological 80/20.
    split = int(n * 0.8)
    X_pre_tr, X_pre_va = X_pre[:split], X_pre[split:]
    X_live_tr, X_live_va = X_live[:split], X_live[split:]
    Y_tr, Y_va = Y[:split], Y[split:]
    print(f"  split: train={len(X_pre_tr)}  val={len(X_pre_va)}")

    model = MultitaskMLPLive(pregame_dim=len(feature_cols), live_dim=LIVE_DIM)
    model.feature_names = list(feature_cols)
    print(f"  training (epochs<={args.epochs} batch={args.batch_size} lr={args.lr})...")
    t1 = time.time()
    model.fit(
        X_pre_tr, X_live_tr, Y_tr,
        X_pre_val=X_pre_va, X_live_val=X_live_va, Y_val=Y_va,
        epochs=args.epochs, batch_size=args.batch_size, lr=args.lr,
    )
    train_seconds = time.time() - t1
    print(f"  training done in {train_seconds:.1f}s")

    # Per-stat MAE on val (raw-count scale).
    preds_va = model.predict(X_pre_va, X_live_va, invert=True)
    print()
    print("  == VAL per-stat MAE (raw-count scale) ==")
    for j, s in enumerate(STATS):
        actual = y_raw[s][split:]
        pred = preds_va[:, j]
        mae = float(np.mean(np.abs(pred - actual)))
        bias = float(np.mean(pred - actual))
        print(f"    {s.upper():4s}  MAE={mae:.4f}  bias={bias:+.4f}")

    # Sanity: zero-live-input check (None vs explicit zero vector) -- must be
    # identical at inference (no model stochasticity).
    preds_zero_implicit = model.predict(X_pre_va, None, invert=True)
    preds_zero_explicit = model.predict(
        X_pre_va, np.zeros((len(X_pre_va), LIVE_DIM), dtype=np.float32),
        invert=True)
    delta = float(np.mean(np.abs(preds_zero_implicit - preds_zero_explicit)))
    print(f"  zero-implicit-vs-explicit MAE delta: {delta:.6f}  (must be 0)")

    # Show live-lift on val: predictions WITH live vector vs predictions
    # with zero vector. Confirms the live encoder pathway is alive.
    n_val_live_active = int((X_live_va.sum(axis=1) != 0.0).sum())
    if n_val_live_active > 0:
        preds_va_no_live = model.predict(
            X_pre_va, np.zeros((len(X_pre_va), LIVE_DIM), dtype=np.float32),
            invert=True)
        live_active_mask = (X_live_va.sum(axis=1) != 0.0)
        diff = np.abs(preds_va[live_active_mask] - preds_va_no_live[live_active_mask])
        print(f"  live pathway sanity: mean |pred_with - pred_without| over "
              f"{n_val_live_active} active rows = {float(diff.mean()):.4f} "
              "(>0 = live encoder learned)")

    model.save()
    print(f"  saved -> {os.path.relpath(model.MODEL_PATH if hasattr(model, 'MODEL_PATH') else 'data/models/multitask_mlp_live.pt', PROJECT_DIR)}")
    print(f"  total elapsed: {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
