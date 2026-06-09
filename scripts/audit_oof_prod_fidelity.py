"""audit_oof_prod_fidelity.py — Does what we VALIDATE (cached OOF) equal what we
SERVE (prod predict_pergame on persisted artifacts)?

Core question (FIDELITY): the pregame quality we measure lives in
data/cache/pregame_oof.parquet (scripts/cache_pergame_oof.py trains FRESH per
WF fold, 3-way NNLS blend). Production src.prediction.prop_pergame.predict_pergame
loads PERSISTED artifacts and slices cols[:n_features_in_]. If these diverge,
improvements measured on the OOF may NOT reach the served prediction.

This script, for a representative held-out sample of (player_id, game_date)
rows in the OOF:
  1. Rebuilds the per-game feature row (build_pergame_dataset, same recipe the
     trainer used) and matches it back to the OOF row on (player_id, date).
  2. Calls predict_pergame(stat, row) [PERSISTED-artifact path] under
     CV_BBREF_REORDER_FIX OFF and ON (two child processes — flag is read at
     import).
  3. Reports per-stat: mean|prod-oof|, corr(prod, oof), and MAE_prod vs MAE_oof
     vs actual — i.e. is the SERVED prediction a faithful proxy of the VALIDATED
     one, and does the bbref slot-misalignment degrade prod?

Usage
-----
    # produce the per-row prod predictions for one flag state (child invocation)
    python scripts/audit_oof_prod_fidelity.py --emit --flag 0 --sample 4000
    python scripts/audit_oof_prod_fidelity.py --emit --flag 1 --sample 4000
    # orchestrate both + write the report table
    python scripts/audit_oof_prod_fidelity.py --run --sample 4000
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import warnings
from typing import Dict, List, Optional

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

OOF_PATH = os.path.join(PROJECT_DIR, "data", "cache", "pregame_oof.parquet")
TMP_DIR = os.path.join(PROJECT_DIR, "data", "cache", "_fidelity_tmp")
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]


def _build_row_index():
    """Build {(player_id, date_iso10): feature_row_dict} from build_pergame_dataset.

    The trainer's exact recipe. Keyed (player_id, date[:10]) so we can match OOF
    rows. Dataset rows carry player_id + 'date'; (player_id, date, stat) was
    verified unique in the OOF so no cartesian risk.
    """
    from src.prediction.prop_pergame import build_pergame_dataset  # noqa: PLC0415
    rows, fc = build_pergame_dataset(min_prior=0)
    idx: Dict[tuple, dict] = {}
    for r in rows:
        pid = int(r.get("player_id", 0))
        d = str(r.get("date", ""))[:10]
        idx[(pid, d)] = r
    return idx, fc


def emit(flag: str, sample: int, seed: int = 7) -> None:
    """Child invocation: with CV_BBREF_REORDER_FIX=<flag> already set in env,
    compute predict_pergame for a deterministic sample of OOF rows and dump a
    parquet of per-(row,stat) prod predictions to TMP_DIR.
    """
    import pandas as pd  # noqa: PLC0415
    from src.prediction.prop_pergame import predict_pergame  # noqa: PLC0415

    oof = pd.read_parquet(OOF_PATH)
    # one representative row per (player_id, game_date) — sample on the unique
    # keys so all 7 stats for a sampled row are evaluated.
    keys = oof[["player_id", "game_date"]].drop_duplicates().reset_index(drop=True)
    rng = np.random.default_rng(seed)
    take = min(sample, len(keys))
    sel = keys.iloc[rng.choice(len(keys), size=take, replace=False)].reset_index(drop=True)
    sel_set = set((int(r.player_id), str(r.game_date)[:10]) for r in sel.itertuples())

    print(f"[emit flag={flag}] building dataset row index ...", flush=True)
    idx, fc = _build_row_index()
    print(f"[emit flag={flag}] dataset rows indexed: {len(idx)}; sampled keys: {len(sel_set)}", flush=True)

    recs: List[dict] = []
    n_missing_row = 0
    for (pid, d) in sel_set:
        row = idx.get((pid, d))
        if row is None:
            n_missing_row += 1
            continue
        for stat in STATS:
            try:
                p = predict_pergame(stat, row)
            except Exception as exc:  # noqa: BLE001
                p = None
            recs.append({"player_id": pid, "game_date": d, "stat": stat,
                         "prod_pred": (float(p) if p is not None else np.nan)})
    os.makedirs(TMP_DIR, exist_ok=True)
    out = os.path.join(TMP_DIR, f"prod_flag{flag}.parquet")
    pd.DataFrame(recs).to_parquet(out, index=False)
    print(f"[emit flag={flag}] wrote {out}  rows={len(recs)} missing_dataset_row={n_missing_row}", flush=True)


def _stat_table(merged, pred_col: str) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for stat in STATS:
        s = merged[merged["stat"] == stat].dropna(subset=[pred_col, "oof_pred", "actual"])
        if len(s) == 0:
            continue
        prod = s[pred_col].to_numpy(float)
        oof = s["oof_pred"].to_numpy(float)
        act = s["actual"].to_numpy(float)
        with np.errstate(all="ignore"):
            corr = float(np.corrcoef(prod, oof)[0, 1]) if len(s) > 2 else float("nan")
        out[stat] = {
            "n": int(len(s)),
            "mean_abs_prod_minus_oof": float(np.mean(np.abs(prod - oof))),
            "median_abs_prod_minus_oof": float(np.median(np.abs(prod - oof))),
            "corr_prod_oof": corr,
            "mae_prod_vs_actual": float(np.mean(np.abs(prod - act))),
            "mae_oof_vs_actual": float(np.mean(np.abs(oof - act))),
            "mean_prod": float(np.mean(prod)),
            "mean_oof": float(np.mean(oof)),
            "mean_actual": float(np.mean(act)),
        }
    return out


def run(sample: int) -> None:
    import pandas as pd  # noqa: PLC0415
    py = sys.executable
    env_base = dict(os.environ)
    for flag in ("0", "1"):
        out = os.path.join(TMP_DIR, f"prod_flag{flag}.parquet")
        env = dict(env_base)
        env["CV_BBREF_REORDER_FIX"] = flag
        print(f"\n=== child: emit flag={flag} ===", flush=True)
        subprocess.run(
            [py, os.path.abspath(__file__), "--emit", "--flag", flag,
             "--sample", str(sample)],
            check=True, env=env, cwd=PROJECT_DIR,
        )

    oof = pd.read_parquet(OOF_PATH)
    oof["game_date"] = oof["game_date"].astype(str).str[:10]
    p0 = pd.read_parquet(os.path.join(TMP_DIR, "prod_flag0.parquet"))
    p1 = pd.read_parquet(os.path.join(TMP_DIR, "prod_flag1.parquet"))
    p0 = p0.rename(columns={"prod_pred": "prod_off"})
    p1 = p1.rename(columns={"prod_pred": "prod_on"})

    m = oof.merge(p0, on=["player_id", "game_date", "stat"], how="inner")
    m = m.merge(p1, on=["player_id", "game_date", "stat"], how="inner")

    tbl_off = _stat_table(m, "prod_off")
    tbl_on = _stat_table(m, "prod_on")

    result = {
        "n_merged_rows_total": int(len(m)),
        "sample_keys": int(sample),
        "flag_off": tbl_off,
        "flag_on": tbl_on,
    }
    os.makedirs(TMP_DIR, exist_ok=True)
    with open(os.path.join(TMP_DIR, "fidelity_result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    # ── pretty print ──
    print("\n\n================ OOF <-> PROD FIDELITY ================")
    print(f"merged (row,stat) pairs: {len(m)}\n")
    hdr = (f"{'stat':4s} {'n':>6s} | {'|prod-oof|':>10s} {'corr':>6s} | "
           f"{'MAE_prod':>8s} {'MAE_oof':>8s} {'dProd-Oof':>9s} | "
           f"{'mean_prod':>9s} {'mean_oof':>8s} {'mean_act':>8s}")
    for label, tbl in [("FLAG OFF (legacy/live-default)", tbl_off),
                       ("FLAG ON (CV_BBREF_REORDER_FIX=1)", tbl_on)]:
        print(f"\n--- {label} ---")
        print(hdr)
        for stat in STATS:
            r = tbl.get(stat)
            if not r:
                continue
            print(f"{stat:4s} {r['n']:6d} | {r['mean_abs_prod_minus_oof']:10.4f} "
                  f"{r['corr_prod_oof']:6.3f} | {r['mae_prod_vs_actual']:8.4f} "
                  f"{r['mae_oof_vs_actual']:8.4f} "
                  f"{r['mae_prod_vs_actual']-r['mae_oof_vs_actual']:+9.4f} | "
                  f"{r['mean_prod']:9.3f} {r['mean_oof']:8.3f} {r['mean_actual']:8.3f}")

    # ── bbref ON-vs-OFF delta on PROD ──
    print("\n\n========= bbref fix effect on PROD (ON vs OFF) =========")
    print(f"{'stat':4s} {'n':>6s} | {'MAE_off':>8s} {'MAE_on':>8s} {'dMAE(on-off)':>12s} "
          f"{'%MAE':>7s} | {'mean|on-off|':>12s}")
    for stat in STATS:
        s = m[m["stat"] == stat].dropna(subset=["prod_off", "prod_on", "actual"])
        if len(s) == 0:
            continue
        off = s["prod_off"].to_numpy(float)
        on = s["prod_on"].to_numpy(float)
        act = s["actual"].to_numpy(float)
        mae_off = float(np.mean(np.abs(off - act)))
        mae_on = float(np.mean(np.abs(on - act)))
        dmae = mae_on - mae_off
        pct = (dmae / mae_off * 100.0) if mae_off else float("nan")
        print(f"{stat:4s} {len(s):6d} | {mae_off:8.4f} {mae_on:8.4f} {dmae:+12.4f} "
              f"{pct:+6.2f}% | {float(np.mean(np.abs(on-off))):12.4f}")
    print("\n(negative dMAE(on-off) => ON is MORE accurate on the persisted-artifact serve path)")
    print(f"\nwrote {os.path.join(TMP_DIR, 'fidelity_result.json')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--flag", default="0")
    ap.add_argument("--sample", type=int, default=4000)
    args = ap.parse_args()
    if args.emit:
        emit(args.flag, args.sample)
    elif args.run:
        run(args.sample)
    else:
        ap.print_help()
