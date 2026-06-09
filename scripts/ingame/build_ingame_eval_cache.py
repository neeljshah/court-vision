"""build_ingame_eval_cache.py — run the expensive in-game routed-ensemble eval
ONCE and dump a flat per-row projection table so every downstream intelligence
experiment re-scores in SECONDS instead of rebuilding ~2519 games + retraining
the v2 head each time.

This is the in-game analog of scripts/_pts_oof_harness.py. It faithfully REUSES
the real harness functions from scripts/ingame/eval_routed_ensemble.py (no
re-implementation of the projection) — it only swaps the MAE-accumulation step for
a row dump.

Output: data/cache/ingame_eval_cache.parquet — one row per
(game, fold, grid-bucket, player, stat) with the deployed baseline `routed`
projection, its components, the truth, and the game-state needed to condition any
intelligence adjustment (period, score_margin, game_remaining_sec, pf, cur_min).

Usage:
    # quick smoke (validates pipeline cheaply)
    python scripts/ingame/build_ingame_eval_cache.py --max-games 150
    # full production cache (run when CPU is free)
    python scripts/ingame/build_ingame_eval_cache.py --max-games 0
"""
from __future__ import annotations
import argparse, os, sys, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from scripts.ingame import eval_routed_ensemble as E          # noqa: E402
from scripts.ingame import eval_second_by_second as ESBS        # noqa: E402

_OUT = os.path.join("data", "cache", "ingame_eval_cache.parquet")


def _gstate(grow: dict) -> dict:
    hs = float(grow.get("home_score", 0) or 0); as_ = float(grow.get("away_score", 0) or 0)
    return {
        "period": int(grow.get("period", 0) or 0),
        "elapsed_sec_in_period": float(grow.get("elapsed_sec_in_period", 0) or 0),
        "game_remaining_sec": float(grow.get("game_remaining_sec", 0) or 0),
        "game_elapsed_sec": float(grow.get("game_elapsed_sec", 0) or 0),
        "home_score": hs, "away_score": as_, "score_margin": hs - as_,
    }


def build(max_games: int, folds: int, min_train: int, num_boost_round: int,
          device: str, out: str) -> str:
    import pandas as pd
    season_games = E.load_season_games()
    store = E.GamelogStore()
    all_ids = [g for g in E.discover_game_ids() if g in season_games]
    all_ids = [g for g in all_ids if E._parse_iso_date(season_games[g].get("game_date") or "")]
    all_ids.sort(key=lambda g: season_games[g]["game_date"])
    n_total = len(all_ids)
    if max_games and n_total > max_games:
        idx = np.linspace(0, n_total - 1, max_games).astype(int)
        sampled = [all_ids[i] for i in sorted(set(idx.tolist()))]
    else:
        sampled = all_ids
    print(f"[cache] {n_total} dated games; building {len(sampled)}", flush=True)

    old_sec, old_labels = E._patch_grid()
    records = []
    t0 = time.time()
    try:
        for i, gid in enumerate(sampled):
            try:
                rec = E.build_game_record(gid, season_games[gid], store)
                if rec is not None:
                    rec["_gid"] = gid
                    records.append(rec)
            except Exception:
                pass
            if (i + 1) % 100 == 0:
                print(f"  build {i+1}/{len(sampled)} ({len(records)} usable, {time.time()-t0:.0f}s)", flush=True)
    finally:
        ESBS.GRID_SEC, ESBS.GRID_LABELS = old_sec, old_labels
    records.sort(key=lambda r: r["game_date"])
    print(f"[cache] {len(records)} usable records ({time.time()-t0:.0f}s)", flush=True)

    uniq = sorted(set(r["game_date"] for r in records))
    chunks = np.array_split(np.array(uniq, dtype=object), folds + 1)
    fold_test_dates = [set(chunks[k].tolist()) for k in range(1, folds + 1)]
    dev = device if device != "auto" else E._select_device("cuda")
    print(f"[cache] xgb device={dev}", flush=True)

    rows = []
    for fold_i, test_dates in enumerate(fold_test_dates):
        train_recs = [r for r in records if r["game_date"] < min(test_dates)]
        test_recs = [r for r in records if r["game_date"] in test_dates]
        if len(train_recs) < min_train or not test_recs:
            continue
        df_tr = E._assemble_player_frame(train_recs)
        proj_v2, _ = E.train_player_lines_v2(
            df_tr, features=E.FEATURES_V2_PACE, walk_forward=False,
            num_boost_round=num_boost_round, device=dev, save=False)
        print(f"[cache] fold {fold_i}: train={len(train_recs)} test={len(test_recs)}", flush=True)
        for r in test_recs:
            store_r = r["store"]; gid = r.get("_gid") or r.get("game_id") or ""
            gdate = r["game_date"]
            for t, gd in r["grids"].items():
                grow = gd["game"]; bucket = E.EXTENDED_GRID_LABELS.get(t)
                if bucket is None:
                    continue
                gs = _gstate(grow)
                for (_team, _ln), prow in gd["players"].items():
                    pid = prow.get("player_id")
                    if pid is None or pid not in r["player_finals"]:
                        continue
                    lab = r["player_finals"][pid]
                    if lab.get("min", 0) <= 0:
                        continue
                    pf = float(prow.get("pf", 0) or 0)
                    snap = E.baseline_player_snapshot(prow, grow, pf)
                    l5 = store_r.l5_prior(pid, gdate)
                    v2row = E._build_v2_row(prow, grow, l5)
                    v2_out = proj_v2.project(v2row)
                    for s in E.PLAYER_STATS:
                        cur = float(prow.get(s, 0) or 0)
                        snap_v = float(snap[s]); v2_v = float(v2_out[s])
                        comp = {"snapshot": snap_v, "v2": v2_v}
                        l5_v = float(l5[s]) if (l5 and s in l5) else None
                        if l5_v is not None:
                            comp["pregame_l5"] = max(cur, l5_v)
                        routed = max(cur, E._blend_from_components(s, t, comp))
                        rows.append({
                            "game_id": str(gid), "game_date": gdate, "fold": fold_i,
                            "t": int(t), "bucket": bucket, "player_id": int(pid),
                            "team": _team, "stat": s, "cur": cur, "routed": float(routed),
                            "snapshot": snap_v, "v2": v2_v,
                            "l5": (l5_v if l5_v is not None else np.nan),
                            "truth": float(lab[s]), "pf": pf,
                            "cur_min": float(prow.get("min", 0) or 0), **gs,
                        })
    if not rows:
        raise SystemExit(
            f"[cache] NO rows produced — likely too few games ({len(records)}) for "
            f"min_train={min_train}. Use a larger --max-games or smaller --min-train.")
    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"[cache] wrote {out}: {len(df):,} rows, {df['game_id'].nunique()} games, "
          f"stats={sorted(df['stat'].unique())}, buckets={sorted(df['bucket'].unique())}", flush=True)
    # sanity: base routed MAE per stat (the bar every adjustment must beat)
    for s in sorted(df["stat"].unique()):
        d = df[df["stat"] == s]
        print(f"   {s:5s} base routed MAE={float((d['routed']-d['truth']).abs().mean()):.4f}  n={len(d)}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=0, help="0 = all games (full cache)")
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--min-train", type=int, default=200)
    ap.add_argument("--num-boost-round", type=int, default=300)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--out", default=_OUT)
    a = ap.parse_args()
    build(a.max_games, a.folds, a.min_train, a.num_boost_round, a.device, a.out)
