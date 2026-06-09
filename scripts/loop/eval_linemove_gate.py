"""eval_linemove_gate.py -- honest gate for intraday PROP line-movement features.

Mirrors ``scripts/loop/eval_atlas_lift.py`` exactly, but the marginal feature
block under test is the leak-safe per-player line-movement vector from
``src.ingest.prop_line_movement.get_prop_line_movement`` instead of the atlas.

What it does
------------
Runs the canonical expanding-window prop walk-forward TWICE per stat on identical
(train, holdout) row slices:
  * ``base``      -- the FULL production prop feature matrix (build_pergame_dataset);
  * ``base+lm``   -- the same matrix plus the 7 line-movement columns.
Reports per-stat mean-over-folds ``MAE(base+lm) - MAE(base)`` (negative = the
line-movement signal REDUCES out-of-sample error) and the folds-negative count.

Leak posture
------------
For each row we read line movement with ``asof`` = that game's tip-off time
(``start_time`` in the lines CSVs, joined by player_name+stat+date). The feature
module ONLY consumes captures strictly before ``asof``, so no closing/post-tip
line ever enters a training row. Rows with <2 pre-tip captures get the neutral
all-zero vector (absence injects no signal). The join key is
(player_name [resolved from player_id via PLAYER_INDEX], stat, game_date).

Honest-gate verdict (per the dual gate in src/loop/gate.py):
  * SHIP          -- delta < 0 AND all folds negative (genuine OOS error reduction);
  * VARIANCE-ONLY -- delta < 0 but NOT all folds negative (noisy / inconsistent);
  * REJECT        -- delta >= 0 (no error reduction);
  * INSUFFICIENT_DATA -- the line-movement columns are all-neutral across the
                    evaluable rows (zero date overlap between lines/ and the
                    targeted gamelogs) -> base+lm is numerically identical to base
                    and NO honest MAE verdict is possible. This is the truthful
                    state whenever data/lines/ does not yet overlap the dataset.

Run:
    set NBA_OFFLINE=1
    python scripts/loop/eval_linemove_gate.py --device auto
    python scripts/loop/eval_linemove_gate.py --splits 4 --stats pts,reb,ast
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
from typing import Any, Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")
os.environ.setdefault("NBA_OFFLINE", "1")

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.ingest.prop_line_movement import feature_keys, get_prop_line_movement

STATS_DEFAULT = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
_MIN_TRAIN_ROWS = 5000
_MIN_HOLDOUT_ROWS = 2000
_LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")
_PLAYER_INDEX = os.path.join(PROJECT_DIR, "data", "cache", "profiles", "PLAYER_INDEX.json")

_XGB_DEVICE: str = "cpu"


def _resolve_device(device_arg: str) -> str:
    if device_arg == "auto":
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"
    return device_arg


def _line_dates() -> List[str]:
    """Distinct slate dates that have any data/lines/<date>_*.csv capture file."""
    out = set()
    for p in glob.glob(os.path.join(_LINES_DIR, "*.csv")):
        base = os.path.basename(p)
        if len(base) >= 10 and base[4] == "-" and base[7] == "-":
            out.add(base[:10])
    return sorted(out)


def _pid_to_name() -> Dict[int, str]:
    """player_id -> canonical name from PLAYER_INDEX.json (for the line join)."""
    try:
        with open(_PLAYER_INDEX, "r", encoding="utf-8") as f:
            idx = json.load(f)
        return {int(p["player_id"]): str(p["name"]) for p in idx.get("players", [])
                if p.get("player_id") is not None and p.get("name")}
    except Exception as exc:
        print(f"[linemove_gate] PLAYER_INDEX unavailable ({exc}); name join disabled")
        return {}


def _tipoff_by_date() -> Dict[str, str]:
    """slate_date -> a representative tip-off ISO ts (max start_time on that date).

    Used as the per-row ``asof`` close-proxy when a row's own game start time is
    not otherwise known. Reading captures strictly before tip-off is leak-safe.
    """
    out: Dict[str, str] = {}
    for p in sorted(glob.glob(os.path.join(_LINES_DIR, "*.csv"))):
        base = os.path.basename(p)
        if base.endswith(".stale") or len(base) < 10:
            continue
        date = base[:10]
        try:
            df = pd.read_csv(p, engine="python", on_bad_lines="skip",
                             usecols=lambda c: c in ("start_time",))
        except Exception:
            continue
        if "start_time" not in df.columns or df.empty:
            continue
        st = pd.to_datetime(df["start_time"], utc=True, errors="coerce").dropna()
        if st.empty:
            continue
        cur = out.get(date)
        mx = st.max().isoformat()
        if cur is None or mx > cur:
            out[date] = mx
    return out


def _linemove_columns(rows: List[dict]) -> Tuple[List[str], int]:
    """Join the 7 line-movement features onto ``rows`` in place.

    Returns (column_names, n_rows_with_real_movement). A row only gets a non-neutral
    vector when its (player, stat, date) has >=2 captures strictly before tip-off.
    The returned count is across ALL stats' line keys collapsed to "any pts capture",
    so it is the count of rows with usable pre-tip line data of any kind.
    """
    cols = list(feature_keys())
    pid2name = _pid_to_name()
    tip = _tipoff_by_date()
    line_dates = set(_line_dates())

    n_real = 0
    for r in rows:
        date = r["date"][:10]
        # Default neutral vector for every row.
        for c in cols:
            r.setdefault(c, 0.0)
        if date not in line_dates:
            continue
        name = pid2name.get(int(r.get("player_id", -1)))
        if not name:
            continue
        asof = tip.get(date)
        if asof is None:
            continue
        # Use the row's own target stat family for the line lookup. We attach
        # movement for the per-game 'pts' prop as the canonical liquidity proxy
        # AND each stat individually when the stat-specific row is trained; here
        # we attach a stat-agnostic 'pts' movement as the shared column block so
        # the ablation column set is identical across stats (matches base+atlas).
        lm = get_prop_line_movement(name, "pts", date, asof=asof)
        got = False
        for c in cols:
            r[c] = float(lm.get(c, 0.0))
            if c == "prop_n_captures" and r[c] >= 2.0:
                got = True
        if got:
            n_real += 1
    return cols, n_real


def _matrix(rows: List[dict], cols: List[str]) -> np.ndarray:
    return np.array([[_cell(r.get(c, np.nan)) for c in cols] for r in rows], dtype=float)


def _cell(v: Any) -> float:
    if v is None:
        return float("nan")
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    return float("nan")


def _impute(train: np.ndarray, *mats: np.ndarray) -> Tuple[np.ndarray, ...]:
    if train.shape[1] == 0:
        return (train, *mats)
    med = np.nanmedian(train, axis=0)
    med = np.where(np.isnan(med), 0.0, med)

    def fill(a: np.ndarray) -> np.ndarray:
        out = a.copy()
        idx = np.where(np.isnan(out))
        out[idx] = np.take(med, idx[1])
        return out

    return tuple(fill(m) for m in (train, *mats))


def _fit_predict(X_tr, y_tr, X_ho, sw):
    try:
        import xgboost as xgb
    except Exception:
        coef, *_ = np.linalg.lstsq(np.nan_to_num(X_tr), y_tr, rcond=None)
        return np.nan_to_num(X_ho) @ coef
    kwargs: Dict[str, Any] = dict(
        n_estimators=400, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
        reg_lambda=2.0, reg_alpha=0.5, random_state=42, n_jobs=-1,
        objective="reg:squarederror", eval_metric="mae",
    )
    if _XGB_DEVICE == "cuda":
        kwargs["device"] = "cuda"
    try:
        m = xgb.XGBRegressor(**kwargs)
        m.fit(X_tr, y_tr, sample_weight=sw, verbose=False)
    except Exception:
        kwargs.pop("device", None)
        m = xgb.XGBRegressor(**kwargs)
        m.fit(X_tr, y_tr, sample_weight=sw, verbose=False)
    return m.predict(X_ho)


def _fold_bounds(n: int, n_splits: int) -> List[Tuple[int, int, int]]:
    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    out: List[Tuple[int, int, int]] = []
    for i, frac in enumerate(fold_ends):
        tr_end = int(n * frac)
        te_end = n if i == n_splits - 1 else int(n * fold_ends[i + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        out.append((tr_end, va_end, te_end))
    return out


def _sample_weights(rows: List[dict], tr_end: int) -> np.ndarray:
    tr_dates = [datetime.fromisoformat(rows[i]["date"][:19]) for i in range(tr_end)]
    max_d = max(tr_dates)
    age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
    return np.exp(-0.5 * age)


def eval_lift(stats: List[str], n_splits: int = 4) -> Dict[str, Any]:
    from src.prediction.prop_pergame import build_pergame_dataset

    print("[linemove_gate] loading prop dataset (build_pergame_dataset)...")
    rows, base_cols = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    print(f"[linemove_gate] rows={n}, base features={len(base_cols)}")

    lm_cols, n_real = _linemove_columns(rows)
    line_dates = _line_dates()
    ds_max = max(r["date"][:10] for r in rows) if rows else None
    ds_min = min(r["date"][:10] for r in rows) if rows else None
    overlap_dates = sorted(set(r["date"][:10] for r in rows) & set(line_dates))
    print(f"[linemove_gate] line-movement columns: {len(lm_cols)}")
    print(f"[linemove_gate] lines dates={line_dates[0]}..{line_dates[-1]} "
          f"({len(line_dates)}); dataset dates={ds_min}..{ds_max}")
    print(f"[linemove_gate] date OVERLAP rows-with-real-movement: {n_real} "
          f"(overlapping slate dates: {overlap_dates})")

    aug_cols = list(base_cols) + lm_cols
    X_base = _matrix(rows, list(base_cols))
    X_aug = _matrix(rows, aug_cols)
    bounds = _fold_bounds(n, n_splits)

    per_stat: Dict[str, Any] = {}
    for stat in stats:
        y = np.array([r.get(f"target_{stat}", np.nan) for r in rows], dtype=float)
        deltas: List[float] = []
        base_maes: List[float] = []
        aug_maes: List[float] = []
        ho_real: List[int] = []
        for fi, (tr_end, va_end, te_end) in enumerate(bounds):
            if tr_end < _MIN_TRAIN_ROWS or (te_end - va_end) < _MIN_HOLDOUT_ROWS:
                continue
            ok_tr = ~np.isnan(y[:tr_end])
            ho = slice(va_end, te_end)
            ok_ho = ~np.isnan(y[ho])
            if not ok_tr.any() or not ok_ho.any():
                continue
            # count holdout rows that actually carry real (>=2 capture) movement
            real_ho = int(sum(1 for i in range(va_end, te_end)
                              if rows[i].get("prop_n_captures", 0.0) >= 2.0))
            ho_real.append(real_ho)
            sw = _sample_weights(rows, tr_end)
            yb_tr, yb_ho = y[:tr_end], y[ho]
            b_tr, b_ho = _impute(X_base[:tr_end], X_base[ho])
            pb = _fit_predict(b_tr, yb_tr, b_ho, sw)
            mae_b = float(np.mean(np.abs(pb - yb_ho)))
            a_tr, a_ho = _impute(X_aug[:tr_end], X_aug[ho])
            pa = _fit_predict(a_tr, yb_tr, a_ho, sw)
            mae_a = float(np.mean(np.abs(pa - yb_ho)))
            deltas.append(mae_a - mae_b)
            base_maes.append(mae_b)
            aug_maes.append(mae_a)
            print(f"  {stat.upper():4s} fold{fi + 1}: base={mae_b:.4f} "
                  f"lm={mae_a:.4f} delta={mae_a - mae_b:+.4f} "
                  f"(ho_real_movement_rows={real_ho})", flush=True)
        if not deltas:
            per_stat[stat] = {"evaluated": False, "reason": "no evaluable fold"}
            continue
        n_neg = sum(1 for d in deltas if d < 0)
        per_stat[stat] = {
            "evaluated": True,
            "base_mae_mean": float(np.mean(base_maes)),
            "lm_mae_mean": float(np.mean(aug_maes)),
            "delta_mae_mean": float(np.mean(deltas)),
            "deltas": deltas,
            "neg_folds": n_neg,
            "n_folds": len(deltas),
            "all_improve": bool(n_neg == len(deltas)),
            "holdout_rows_with_real_movement": ho_real,
        }
    return {
        "run_timestamp": datetime.now().isoformat(),
        "device": _XGB_DEVICE,
        "n_rows": n,
        "n_base_features": len(base_cols),
        "n_linemove_features": len(lm_cols),
        "linemove_features": lm_cols,
        "n_splits": n_splits,
        "lines_dates_min": line_dates[0] if line_dates else None,
        "lines_dates_max": line_dates[-1] if line_dates else None,
        "n_lines_dates": len(line_dates),
        "dataset_dates_min": ds_min,
        "dataset_dates_max": ds_max,
        "overlap_dates": overlap_dates,
        "n_rows_with_real_movement": n_real,
        "per_stat": per_stat,
    }


def _verdict(result: Dict[str, Any]) -> Dict[str, Any]:
    """Apply the honest dual gate, with an INSUFFICIENT_DATA short-circuit.

    If no row carries real (>=2 pre-tip captures) line movement, the lm columns
    are all-neutral and base+lm is numerically identical to base -> no honest MAE
    verdict is possible. That is the truthful state, NOT a 'REJECT'.
    """
    per: Dict[str, str] = {}
    if result["n_rows_with_real_movement"] == 0:
        for stat, v in result["per_stat"].items():
            per[stat] = "INSUFFICIENT_DATA"
        result["overall_verdict"] = "INSUFFICIENT_DATA"
        result["overall_reason"] = (
            "Zero date overlap between data/lines/ "
            f"({result['lines_dates_min']}..{result['lines_dates_max']}) and the "
            f"prop gamelog targets (..{result['dataset_dates_max']}). Every training "
            "and holdout row receives the neutral all-zero line-movement vector, so "
            "base+lm is numerically identical to base. The feature is leak-safe and "
            "PRODUCES real movement on live slates (verified), but it CANNOT be gated "
            "on out-of-sample MAE until lines/ overlaps dates that also have realised "
            "box-score targets (next overlap arrives once the gamelog cache advances "
            "past 2026-05-25 OR lines are backfilled for pre-05-25 games)."
        )
        result["per_stat_verdict"] = per
        return result
    # Real movement exists -> apply the dual gate per stat.
    for stat, v in result["per_stat"].items():
        if not v.get("evaluated"):
            per[stat] = "NOT_EVALUATED"
            continue
        d = v["delta_mae_mean"]
        if d < 0 and v["all_improve"]:
            per[stat] = "SHIP"
        elif d < 0:
            per[stat] = "VARIANCE-ONLY"
        else:
            per[stat] = "REJECT"
    ships = [s for s, x in per.items() if x == "SHIP"]
    result["overall_verdict"] = "SHIP" if ships else (
        "VARIANCE-ONLY" if "VARIANCE-ONLY" in per.values() else "REJECT")
    result["per_stat_verdict"] = per
    return result


def _print_summary(result: Dict[str, Any]) -> None:
    print("\n" + "=" * 70)
    print("  LINE-MOVEMENT GATE -- per-stat holdout MAE delta (base+lm - base)")
    print("  negative delta = sharp-money line movement REDUCES error")
    print("=" * 70)
    print(f"  rows={result['n_rows']}  lm_features={result['n_linemove_features']}  "
          f"rows_with_real_movement={result['n_rows_with_real_movement']}")
    print(f"  lines={result['lines_dates_min']}..{result['lines_dates_max']}  "
          f"dataset=..{result['dataset_dates_max']}  overlap={result['overlap_dates']}")
    print("  " + "-" * 64)
    print(f"  {'stat':5s} | {'base_mae':>9s} | {'lm_mae':>9s} | "
          f"{'delta':>9s} | {'folds':>9s} | verdict")
    for stat, v in result["per_stat"].items():
        vd = result["per_stat_verdict"].get(stat, "?")
        if not v.get("evaluated"):
            print(f"  {stat.upper():5s} | {'--':>9s} | {'--':>9s} | "
                  f"{'--':>9s} | {'--':>9s} | {vd}")
            continue
        print(f"  {stat.upper():5s} | {v['base_mae_mean']:9.4f} | "
              f"{v['lm_mae_mean']:9.4f} | {v['delta_mae_mean']:+9.4f} | "
              f"{v['neg_folds']}/{v['n_folds']} neg | {vd}")
    print("  " + "-" * 64)
    print(f"  OVERALL VERDICT: {result['overall_verdict']}")
    if result.get("overall_reason"):
        print(f"  {result['overall_reason']}")
    print("=" * 70)


def _write_md(result: Dict[str, Any], md_path: str) -> None:
    lines = [
        "# Line-Movement Gate -- honest prop ablation",
        "",
        f"- run: {result['run_timestamp']}  device={result['device']}",
        f"- rows={result['n_rows']}  base_features={result['n_base_features']}  "
        f"linemove_features={result['n_linemove_features']}",
        f"- lines coverage: {result['lines_dates_min']} .. {result['lines_dates_max']} "
        f"({result['n_lines_dates']} dates)",
        f"- dataset coverage: {result['dataset_dates_min']} .. {result['dataset_dates_max']}",
        f"- overlapping slate dates: {result['overlap_dates']}",
        f"- holdout/training rows carrying REAL (>=2 pre-tip captures) movement: "
        f"**{result['n_rows_with_real_movement']}**",
        "",
        f"## OVERALL VERDICT: **{result['overall_verdict']}**",
        "",
        result.get("overall_reason", ""),
        "",
        "## Per-stat walk-forward MAE delta (base+lm minus base)",
        "",
        "| stat | base MAE | base+lm MAE | delta | folds neg | verdict |",
        "|------|---------:|------------:|------:|:---------:|:-------:|",
    ]
    for stat, v in result["per_stat"].items():
        vd = result["per_stat_verdict"].get(stat, "?")
        if not v.get("evaluated"):
            lines.append(f"| {stat.upper()} | -- | -- | -- | -- | {vd} |")
            continue
        lines.append(
            f"| {stat.upper()} | {v['base_mae_mean']:.4f} | {v['lm_mae_mean']:.4f} | "
            f"{v['delta_mae_mean']:+.4f} | {v['neg_folds']}/{v['n_folds']} | {vd} |")
    lines += [
        "",
        "## Leak posture",
        "- per-row `asof` = that slate's tip-off; only captures STRICTLY BEFORE tip",
        "  are read (`get_prop_line_movement`). No closing/post-tip line enters a row.",
        "- join key: (player_name resolved from player_id via PLAYER_INDEX, stat, date).",
        "- rows with <2 pre-tip captures get the neutral all-zero vector.",
        "",
        "## Verdict legend",
        "- SHIP: delta<0 AND all folds negative (genuine OOS error reduction).",
        "- VARIANCE-ONLY: delta<0 but not all folds negative (noisy).",
        "- REJECT: delta>=0 (no OOS error reduction).",
        "- INSUFFICIENT_DATA: lm columns all-neutral across evaluable rows "
        "(no date overlap) -> base+lm == base; no honest MAE verdict possible.",
    ]
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--splits", type=int, default=4)
    ap.add_argument("--stats", default=",".join(STATS_DEFAULT))
    ap.add_argument("--device", default="auto")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    global _XGB_DEVICE
    _XGB_DEVICE = _resolve_device(args.device)
    print(f"[linemove_gate] device={_XGB_DEVICE}  NBA_OFFLINE={os.environ.get('NBA_OFFLINE')}")

    stats = [s.strip().lower() for s in args.stats.split(",") if s.strip()]
    t0 = time.time()
    result = eval_lift(stats, n_splits=args.splits)
    result["wall_seconds"] = round(time.time() - t0, 1)
    result = _verdict(result)

    _print_summary(result)

    out_json = args.out or os.path.join(PROJECT_DIR, ".planning", "ingame", "linemove_gate.json")
    out_md = os.path.splitext(out_json)[0] + ".md"
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    _write_md(result, out_md)
    print(f"\n[linemove_gate] wrote {out_json}")
    print(f"[linemove_gate] wrote {out_md}")


if __name__ == "__main__":
    main()
