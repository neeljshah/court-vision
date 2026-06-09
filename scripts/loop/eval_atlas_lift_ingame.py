"""eval_atlas_lift_ingame.py -- does the atlas intelligence improve the IN-GAME
end-of-quarter projection?

The pregame ablation (``scripts/loop/eval_atlas_lift.py`` ->
``.planning/loop/atlas_lift.json``) showed that bulk-adding all 49 leak-safe atlas
features to the FULL prod *pergame* model only helps FG3M and hurts PTS/REB -- the
pregame prop model is at its feature ceiling. This is the IN-GAME analogue: does
joining the SAME leak-safe, as-of atlas priors to the IN-GAME projection inputs
reduce end-of-quarter projection error (per-stat MAE) at endQ1 / endQ2 / endQ3?

Why it might help MORE in-game than pregame: the live-state projection
(``predict_in_game.project_snapshot`` -- pace + foul + blowout + learned heads)
already captures *what has happened so far*, while the atlas priors describe a
player's stable *shape* (quarter fade, durability/minutes load). Combining a live
partial line with a durability/fade prior is plausibly complementary in a way that
adding a fade prior to a season-form pergame model is not.

=== Harness (honest, leak-safe, ablation vs the FULL in-game projection) ===
  * Snapshot reconstruction + actuals + game dating are reused verbatim from the
    validated retro harness ``scripts/retro_inplay_mae.py`` (v1): per-game end-of-Q
    snapshots are summed from ``data/player_quarter_stats.parquet`` and projected
    through ``predict_in_game.project_snapshot`` exactly as the retro does.
  * For each snapshot point (endQ1/endQ2/endQ3) and each (game, player, stat) we form
    a residual-correction row:
        base features   = [in_game_projected_final, current_cumulative, period]
        +atlas features = base + leak-safe atlas_* numeric leaves (as-of game date)
    target = full-game actual.
  * We fit two small XGB correctors (base vs base+atlas) on identical expanding-window
    chronological folds (prop_pergame fold scheme) and report
        delta = MAE(base+atlas) - MAE(base)      (NEGATIVE = atlas helps).
    The base corrector is the honest control: it can already re-weight the raw
    in-game projection, so any negative delta is *marginal* atlas information on top
    of the live state, not a free win from adding a learner.
  * It ALSO reports the raw in-game projection MAE (no corrector) as a sanity anchor.

=== LEAK-SAFETY / SAMPLE caveat (reported in the JSON, do not hide) ===
  The atlas parquets are a SINGLE current-state snapshot; the point-in-time store only
  holds historical as-of records for the sections built before today. In practice only
  TWO player sections carry an as-of stamp <= historical game dates
  (``durability_load`` & ``quarter_shape_fatigue``, stamped 2025-04-08), so atlas
  features only join leak-safely for games on/after that date -- ~55 of the 928 dated
  games in the quarter parquet. We therefore restrict the in-game ablation to that
  window and SAY SO. This is a small, section-limited sample: treat a negative delta as
  *suggestive*, not shipped, until more atlas sections carry historical as-of stamps.

Run:
    set NBA_OFFLINE=1
    python scripts/loop/eval_atlas_lift_ingame.py --device auto
    python scripts/loop/eval_atlas_lift_ingame.py --max-games 30 --splits 3
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")
os.environ.setdefault("NBA_OFFLINE", "1")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
SNAPSHOT_POINTS = ("endQ1", "endQ2", "endQ3")

# Atlas sections that actually carry a historical (<= game-date) as-of stamp and so
# can join leak-safely on past games. Measured 2026-05-31; everything else is stamped
# "today" and would leak on a historical row. The harness still DISCOVERS columns
# dynamically -- this constant is only used to annotate the report.
_HISTORICAL_ATLAS_SECTIONS = ("durability_load", "quarter_shape_fatigue")
# Atlas features only become as-of-valid on/after the earliest historical stamp.
_ATLAS_ASOF_FLOOR = "2025-04-08"

_XGB_DEVICE = "cpu"


# ── device ────────────────────────────────────────────────────────────────────
def _resolve_device(device_arg: str) -> str:
    if device_arg == "auto":
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"
    return device_arg


# ── atlas join (defensive import, mirrors the pregame eval) ─────────────────────
def _load_atlas_join():
    try:
        from src.loop.atlas_features import join_atlas_features  # type: ignore
        return join_atlas_features
    except Exception as exc:
        print(f"[ingame_lift] atlas_features unavailable ({exc}); atlas cols = none")
        return None


# ── XGB corrector (GPU with CPU fallback) ───────────────────────────────────────
def _fit_predict(X_tr, y_tr, X_ho) -> np.ndarray:
    """Train one small XGB regressor and predict the holdout.

    Kept deliberately small/regularised: the row counts here are tiny (~hundreds per
    fold) so a large model would just memorise. Mirrors the canonical CUDA fallback.
    """
    try:
        import xgboost as xgb
    except Exception:
        coef, *_ = np.linalg.lstsq(np.nan_to_num(X_tr), y_tr, rcond=None)
        return np.nan_to_num(X_ho) @ coef
    kwargs: Dict[str, Any] = dict(
        n_estimators=200, max_depth=3, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=8,
        reg_lambda=3.0, reg_alpha=0.5, random_state=42, n_jobs=-1,
        objective="reg:squarederror", eval_metric="mae",
    )
    if _XGB_DEVICE == "cuda":
        kwargs["device"] = "cuda"
    try:
        m = xgb.XGBRegressor(**kwargs)
        m.fit(X_tr, y_tr, verbose=False)
    except Exception:
        kwargs.pop("device", None)
        m = xgb.XGBRegressor(**kwargs)
        m.fit(X_tr, y_tr, verbose=False)
    return m.predict(X_ho)


def _impute(train: np.ndarray, *mats: np.ndarray) -> Tuple[np.ndarray, ...]:
    """Fill NaNs with per-column TRAIN medians (no leakage)."""
    if train.shape[1] == 0:
        return (train, *mats)
    med = np.nanmedian(train, axis=0)
    med = np.where(np.isnan(med), 0.0, med)

    def fill(a):
        out = a.copy()
        idx = np.where(np.isnan(out))
        out[idx] = np.take(med, idx[1])
        return out

    return tuple(fill(m) for m in (train, *mats))


def _fold_bounds(n: int, n_splits: int) -> List[Tuple[int, int]]:
    """Expanding-window (train_end, test_end) per fold (prop_pergame style)."""
    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    out: List[Tuple[int, int]] = []
    for i, frac in enumerate(fold_ends):
        tr_end = int(n * frac)
        te_end = n if i == n_splits - 1 else int(n * fold_ends[i + 1])
        out.append((tr_end, te_end))
    return out


# ── dataset assembly ────────────────────────────────────────────────────────────
def build_ingame_rows(max_games: Optional[int], atlas_join) -> Dict[str, List[dict]]:
    """Build per-snapshot residual-correction rows from the retro harness.

    Returns {snapshot_point: [row, ...]} where each row carries the in-game projection,
    the current cumulative value, the atlas_* numeric leaves (leak-safe as-of the game
    date), the full-game actual, and the game date (for chronological folding).

    Only games whose date is on/after the atlas as-of floor are kept (so atlas features
    can join leak-safely); games are sorted chronologically for the walk-forward.
    """
    import pandas as pd
    import scripts.retro_inplay_mae as v1  # validated snapshot/actuals/dating helpers

    qdf = pd.read_parquet(v1._QUARTER_PARQUET)
    all_games = sorted(qdf["game_id"].unique().tolist())

    # Date every game, keep only those in the leak-safe atlas window.
    dated: List[Tuple[str, str]] = []
    for gid in all_games:
        d = v1.find_game_date(gid, qdf)
        if d and d >= _ATLAS_ASOF_FLOOR:
            dated.append((gid, d))
    dated.sort(key=lambda gd: gd[1])  # chronological
    if max_games:
        dated = dated[:max_games]
    print(f"[ingame_lift] usable games (date>={_ATLAS_ASOF_FLOOR}): {len(dated)}")

    out: Dict[str, List[dict]] = {pt: [] for pt in SNAPSHOT_POINTS}
    for gid, gdate in dated:
        actuals = v1.actuals_for_game(gid, qdf)
        for pt in SNAPSHOT_POINTS:
            snap = v1.build_snapshot(gid, pt, qdf)
            if snap is None:
                continue
            # current cumulative value per (pid, stat) from the snapshot players.
            cur: Dict[Tuple[int, str], float] = {}
            for p in snap.get("players", []):
                try:
                    pid = int(p["player_id"])
                except Exception:
                    continue
                for s in STATS:
                    cur[(pid, s)] = float(p.get(s) or 0.0)
            # in-game projected finals.
            try:
                proj = v1.project_snapshot_to_finals(snap)
            except Exception:
                continue
            period = float(snap.get("period") or 0)
            for (pid, stat), pf in proj.items():
                actual = actuals.get((pid, stat))
                if actual is None:
                    continue
                out[pt].append({
                    "game_id": gid,
                    "date": gdate,
                    "player_id": pid,
                    "stat": stat,
                    "proj": float(pf),
                    "cur": float(cur.get((pid, stat), 0.0)),
                    "period": period,
                    "actual": float(actual),
                })

    # Join leak-safe atlas features per snapshot-point row list (keyed on game date).
    if atlas_join is not None:
        for pt in SNAPSHOT_POINTS:
            rows = out[pt]
            if not rows:
                continue
            try:
                atlas_join(rows, entity_type="player",
                           id_key="player_id", date_key="date")
            except Exception as exc:
                print(f"[ingame_lift] atlas join failed for {pt} ({exc})")
    return out


def _atlas_cols(rows: List[dict]) -> List[str]:
    seen: set = set()
    for r in rows:
        for k, v in r.items():
            if k.startswith("atlas_") and isinstance(v, (int, float)) \
                    and not isinstance(v, bool):
                seen.add(k)
    return sorted(seen)


def _mat(rows: List[dict], cols: List[str]) -> np.ndarray:
    return np.array([[_cell(r.get(c)) for c in cols] for r in rows], dtype=float)


def _cell(v: Any) -> float:
    if v is None or isinstance(v, bool):
        return float(v) if isinstance(v, bool) else float("nan")
    if isinstance(v, (int, float)):
        return float(v)
    return float("nan")


# ── ablation per (snapshot, stat) ───────────────────────────────────────────────
def eval_point(rows: List[dict], n_splits: int) -> Dict[str, Any]:
    """Ablate base vs base+atlas correctors per stat for one snapshot point.

    base cols  = [proj, cur, period]   (the in-game projection + live state)
    atlas cols = base + atlas_* leaves
    Also records the RAW in-game projection MAE (proj vs actual) on the same holdout
    rows as a no-corrector anchor.
    """
    atlas_cols = _atlas_cols(rows)
    base_cols = ["proj", "cur", "period"]
    per_stat: Dict[str, Any] = {}
    for stat in STATS:
        srows = [r for r in rows if r["stat"] == stat]
        # chronological order for the expanding window.
        srows.sort(key=lambda r: (r["date"], r["game_id"]))
        n = len(srows)
        if n < 60:  # too few to fold honestly
            per_stat[stat] = {"evaluated": False, "reason": f"n={n} < 60"}
            continue
        y = np.array([r["actual"] for r in srows], dtype=float)
        raw = np.array([r["proj"] for r in srows], dtype=float)
        Xb = _mat(srows, base_cols)
        Xa = _mat(srows, base_cols + atlas_cols)

        base_maes, aug_maes, raw_maes, deltas = [], [], [], []
        for tr_end, te_end in _fold_bounds(n, n_splits):
            if tr_end < 40 or te_end - tr_end < 10:
                continue
            sl_tr = slice(0, tr_end)
            sl_te = slice(tr_end, te_end)
            yb_tr, y_te = y[sl_tr], y[sl_te]
            Xb_tr, Xb_te = _impute(Xb[sl_tr], Xb[sl_te])
            Xa_tr, Xa_te = _impute(Xa[sl_tr], Xa[sl_te])
            pb = _fit_predict(Xb_tr, yb_tr, Xb_te)
            pa = _fit_predict(Xa_tr, yb_tr, Xa_te)
            mb = float(np.mean(np.abs(pb - y_te)))
            ma = float(np.mean(np.abs(pa - y_te)))
            base_maes.append(mb)
            aug_maes.append(ma)
            raw_maes.append(float(np.mean(np.abs(raw[sl_te] - y_te))))
            deltas.append(ma - mb)
        if not deltas:
            per_stat[stat] = {"evaluated": False, "reason": "no usable folds"}
            continue
        n_neg = sum(1 for d in deltas if d < 0)
        per_stat[stat] = {
            "evaluated": True,
            "n_rows": n,
            "raw_proj_mae_mean": float(np.mean(raw_maes)),
            "base_mae_mean": float(np.mean(base_maes)),
            "atlas_mae_mean": float(np.mean(aug_maes)),
            "delta_mae_mean": float(np.mean(deltas)),
            "deltas": deltas,
            "neg_folds": n_neg,
            "n_folds": len(deltas),
            "all_improve": bool(n_neg == len(deltas)),
        }
    return {
        "n_atlas_features": len(atlas_cols),
        "atlas_features": atlas_cols,
        "per_stat": per_stat,
    }


# ── reporting ───────────────────────────────────────────────────────────────────
def _markdown(result: Dict[str, Any]) -> str:
    L: List[str] = []
    L.append("# In-game atlas lift -- end-of-quarter projection ablation")
    L.append("")
    L.append(f"- run: {result['run_timestamp']}  device={result['device']}")
    L.append(f"- usable games (date >= {_ATLAS_ASOF_FLOOR}): "
             f"**{result['n_games']}**  (of {result['n_dated_total']} dated)")
    L.append(f"- leak-safe atlas sections in window: "
             f"{', '.join(_HISTORICAL_ATLAS_SECTIONS)}")
    L.append(f"- n_atlas_features joined: {result['n_atlas_features']}")
    L.append(f"- walk-forward splits: {result['n_splits']}  "
             f"wall: {result.get('wall_seconds')}s")
    L.append("")
    L.append("Delta = MAE(base+atlas) - MAE(base); **negative = atlas helps**. "
             "`raw` = in-game projection with no corrector (anchor); `base` = corrector "
             "on [proj, cur, period].")
    L.append("")
    for pt in SNAPSHOT_POINTS:
        blk = result["per_snapshot"].get(pt, {})
        ps = blk.get("per_stat", {})
        L.append(f"## {pt}  (atlas_features={blk.get('n_atlas_features', 0)})")
        L.append("")
        L.append("| stat | n | raw_mae | base_mae | atlas_mae | delta | folds neg |")
        L.append("|------|---|---------|----------|-----------|-------|-----------|")
        helped = evaluated = 0
        for stat in STATS:
            v = ps.get(stat, {})
            if not v.get("evaluated"):
                L.append(f"| {stat} | -- | -- | -- | -- | -- | {v.get('reason','n/a')} |")
                continue
            evaluated += 1
            d = v["delta_mae_mean"]
            if d < 0:
                helped += 1
            L.append(f"| {stat} | {v['n_rows']} | {v['raw_proj_mae_mean']:.4f} | "
                     f"{v['base_mae_mean']:.4f} | {v['atlas_mae_mean']:.4f} | "
                     f"{d:+.4f} | {v['neg_folds']}/{v['n_folds']} |")
        L.append("")
        L.append(f"**{pt}: atlas helps {helped}/{evaluated} evaluated stats.**")
        L.append("")
    L.append("## Caveat")
    L.append("")
    L.append(
        "Only 2 player atlas sections carry a historical as-of stamp, so this in-game "
        "ablation is a SMALL, SECTION-LIMITED sample (~55 games on/after "
        f"{_ATLAS_ASOF_FLOOR}). Negative deltas are SUGGESTIVE, not shipped. To test the "
        "full 49-feature atlas in-game, the remaining sections need historical as-of "
        "stamps in the point-in-time store (currently all stamped 'today' and dropped "
        "by the leak guard on past rows).")
    L.append("")
    return "\n".join(L)


def run(max_games: Optional[int], n_splits: int) -> Dict[str, Any]:
    atlas_join = _load_atlas_join()
    t0 = time.time()
    rows_by_pt = build_ingame_rows(max_games, atlas_join)

    # how many distinct usable games actually produced rows
    gids = set()
    for pt in SNAPSHOT_POINTS:
        for r in rows_by_pt[pt]:
            gids.add(r["game_id"])

    per_snapshot: Dict[str, Any] = {}
    max_atlas = 0
    for pt in SNAPSHOT_POINTS:
        res = eval_point(rows_by_pt[pt], n_splits)
        per_snapshot[pt] = res
        max_atlas = max(max_atlas, res["n_atlas_features"])

    # total dated (for context) -- cheap recompute via v1 not needed; record from build.
    return {
        "run_timestamp": datetime.now().isoformat(),
        "device": _XGB_DEVICE,
        "n_games": len(gids),
        "n_dated_total": 928,  # measured 2026-05-31 (full quarter parquet)
        "n_atlas_features": max_atlas,
        "n_splits": n_splits,
        "atlas_asof_floor": _ATLAS_ASOF_FLOOR,
        "historical_atlas_sections": list(_HISTORICAL_ATLAS_SECTIONS),
        "per_snapshot": per_snapshot,
        "wall_seconds": round(time.time() - t0, 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-games", type=int, default=None)
    ap.add_argument("--splits", type=int, default=3)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    global _XGB_DEVICE
    _XGB_DEVICE = _resolve_device(args.device)
    print(f"[ingame_lift] device={_XGB_DEVICE}  NBA_OFFLINE={os.environ.get('NBA_OFFLINE')}")

    result = run(args.max_games, args.splits)

    # persist
    out_json = args.out or os.path.join(
        PROJECT_DIR, ".planning", "loop", "atlas_ingame_lift.json")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    md_path = os.path.splitext(out_json)[0] + ".md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(_markdown(result))
    print(f"[ingame_lift] wrote {out_json}")
    print(f"[ingame_lift] wrote {md_path}")

    # console summary
    for pt in SNAPSHOT_POINTS:
        ps = result["per_snapshot"][pt]["per_stat"]
        helped = sum(1 for v in ps.values()
                     if v.get("evaluated") and v["delta_mae_mean"] < 0)
        ev = sum(1 for v in ps.values() if v.get("evaluated"))
        print(f"  {pt}: atlas helps {helped}/{ev} stats")
    return 0


if __name__ == "__main__":
    sys.exit(main())
