"""ingame_atlas_corrector.py -- FLAGGED, leak-safe atlas correction for the IN-GAME
end-of-quarter projection (SHADOW path; default OFF / byte-identical no-op).

Background
----------
``scripts/loop/eval_atlas_lift_ingame.py`` proved that joining the leak-safe, as-of
atlas priors (``src/loop/atlas_features.join_atlas_features``) to the in-game
projection inputs and re-fitting a tiny XGB *corrector* reduces end-of-quarter MAE
-- a lot early (endQ1 PTS -0.627 MAE 3/3 folds; REB/AST/BLK also 3/3; endQ2 5/7).

This module packages that SAME logic as a *reusable corrector* that can post-process
the rows emitted by the in-game projector
(``scripts/predict_in_game.project_snapshot`` -> per-(player,stat)
``projected_final`` rows, or the live ``src/prediction/live_engine.project_from_snapshot``).
It does NOT duplicate the whole ablation harness: it imports the harness's
dataset-assembly + corrector-fit helpers and reuses them to TRAIN a corrector on the
leak-safe historical window, then APPLIES it to the live base rows.

Hard safety contract (matches the live-page shadow requirement)
---------------------------------------------------------------
  * Default OFF. ``is_enabled()`` reads env ``CV_INGAME_ATLAS`` (default "0"). When
    OFF, ``apply_atlas_correction`` is a *pure no-op pass-through*: it returns the
    exact same list object behaviour-identical to today. Nothing is imported, fit,
    or read in the disabled path.
  * Leak-safe: the atlas is joined as-of the SNAPSHOT date. The corrector is trained
    ONLY on historical rows strictly before the snapshot date, and the atlas features
    on every row (train and live) are looked up as-of that row's own date via the
    leak-guarded ``join_atlas_features`` / point-in-time store. No future intelligence
    can reach a past row.
  * Non-destructive: corrected rows are shallow copies; the only mutated field is
    ``projected_final`` (plus an additive ``atlas_corrected`` flag and
    ``projected_final_base`` provenance). Unknown (player,stat) keys, non-finite
    corrections, or any failure fall back to the untouched base value.

Enable / disable
----------------
    set CV_INGAME_ATLAS=1   (or "true"/"yes"/"on")  -> correction active
    set CV_INGAME_ATLAS=0   (default / unset / anything else) -> no-op pass-through
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]

# Truthy spellings for the gate flag.
_TRUTHY = {"1", "true", "yes", "on", "y", "t"}

# Mirror the eval harness's contract so live behaviour matches the validated retro.
STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
_BASE_COLS = ("proj", "cur", "period")
# Below this many historical rows for a stat we don't trust a fitted corrector and
# fall through to the raw projection for that stat.
_MIN_TRAIN_ROWS = 60


# ── flag ────────────────────────────────────────────────────────────────────────
def is_enabled() -> bool:
    """True iff the atlas in-game corrector is switched on via ``CV_INGAME_ATLAS``.

    Default is OFF: unset, empty, "0", or any non-truthy value disables the corrector
    and ``apply_atlas_correction`` becomes a pure pass-through. Truthy spellings
    ("1", "true", "yes", "on", ...) enable it. This is the single shadow-mode gate;
    the live projection default never changes while it is off.
    """
    return os.environ.get("CV_INGAME_ATLAS", "0").strip().lower() in _TRUTHY


# ── device ────────────────────────────────────────────────────────────────────
def _resolve_device(device_arg: str) -> str:
    if device_arg and device_arg != "auto":
        return device_arg
    try:
        import torch  # noqa: F401
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


# ── snapshot date ────────────────────────────────────────────────────────────────
def _snapshot_date(snapshot: Dict[str, Any], as_of: Optional[Any]) -> Optional[str]:
    """Resolve the ISO leak boundary for this snapshot (explicit as_of wins)."""
    cand = as_of
    if cand is None:
        cand = (snapshot.get("date") or snapshot.get("game_date")
                or snapshot.get("start_time") or snapshot.get("gameDate"))
    if cand is None:
        return None
    try:
        from src.loop.atlas_features import _to_iso
        return _to_iso(cand)
    except Exception:
        s = str(cand)
        return s[:10] if len(s) >= 10 else None


# ── harness reuse ────────────────────────────────────────────────────────────────
def _harness():
    """Import the validated ablation harness (reused, not duplicated)."""
    sdir = str(ROOT / "scripts")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if sdir not in sys.path:
        sys.path.insert(0, sdir)
    import scripts.loop.eval_atlas_lift_ingame as h  # type: ignore
    return h


@lru_cache(maxsize=8)
def _train_corrector(as_of_iso: str, device: str) -> Dict[str, Any]:
    """Fit per-stat base+atlas correctors on the leak-safe history before ``as_of``.

    Reuses the eval harness's dataset assembly (``build_ingame_rows``), atlas join,
    feature-matrix + imputation + ``_fit_predict`` helpers. Returns a dict the live
    path applies:
        {"by_stat": {stat: callable(proj, cur, period, atlas_dict) -> corrected},
         "atlas_cols": [...], "n_rows": int}

    Cached per (as_of, device) so a live poller fitting once per snapshot date is cheap.
    Any failure yields an empty model -> the caller falls back to the raw projection.
    """
    import numpy as np

    try:
        h = _harness()
    except Exception as exc:  # harness unavailable -> no correction
        return {"by_stat": {}, "atlas_cols": [], "n_rows": 0, "error": str(exc)}

    # Drive the harness's CPU/GPU switch exactly as its CLI does.
    try:
        h._XGB_DEVICE = device  # type: ignore[attr-defined]
    except Exception:
        pass

    atlas_join = h._load_atlas_join()

    # Build all historical leak-safe rows, then keep only those STRICTLY before the
    # live snapshot date (the corrector must never see the game it is correcting).
    try:
        rows_by_pt = h.build_ingame_rows(None, atlas_join)
    except Exception as exc:
        return {"by_stat": {}, "atlas_cols": [], "n_rows": 0, "error": str(exc)}

    hist: List[dict] = []
    for pt_rows in rows_by_pt.values():
        for r in pt_rows:
            d = str(r.get("date") or "")
            if d and d < as_of_iso:
                hist.append(r)

    atlas_cols = h._atlas_cols(hist)
    feat_cols = list(_BASE_COLS) + atlas_cols

    by_stat: Dict[str, Any] = {}
    for stat in STATS:
        srows = [r for r in hist if r.get("stat") == stat]
        if len(srows) < _MIN_TRAIN_ROWS:
            continue
        srows.sort(key=lambda r: (r.get("date"), r.get("game_id")))
        y = np.array([r["actual"] for r in srows], dtype=float)
        X = h._mat(srows, feat_cols)
        # Train-median imputation (returns the filled train matrix + per-col medians
        # baked into the closure for live imputation of the same columns).
        med = np.nanmedian(X, axis=0) if X.shape[1] else np.zeros(0)
        med = np.where(np.isnan(med), 0.0, med)

        def _fill(mat):
            out = mat.copy()
            idx = np.where(np.isnan(out))
            if idx[0].size:
                out[idx] = np.take(med, idx[1])
            return out

        Xf = _fill(X)
        try:
            import xgboost as xgb
            kwargs = dict(
                n_estimators=200, max_depth=3, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8, min_child_weight=8,
                reg_lambda=3.0, reg_alpha=0.5, random_state=42, n_jobs=-1,
                objective="reg:squarederror", eval_metric="mae",
            )
            if device == "cuda":
                kwargs["device"] = "cuda"
            try:
                model = xgb.XGBRegressor(**kwargs)
                model.fit(Xf, y, verbose=False)
            except Exception:
                kwargs.pop("device", None)
                model = xgb.XGBRegressor(**kwargs)
                model.fit(Xf, y, verbose=False)

            def _predict(vec, _m=model, _fill=_fill):
                arr = _fill(np.asarray(vec, dtype=float).reshape(1, -1))
                return float(_m.predict(arr)[0])
        except Exception:
            # Linear least-squares fallback (matches harness lstsq path).
            coef, *_ = np.linalg.lstsq(np.nan_to_num(Xf), y, rcond=None)

            def _predict(vec, _coef=coef):  # type: ignore[misc]
                return float(np.nan_to_num(np.asarray(vec, dtype=float)) @ _coef)

        by_stat[stat] = _predict

    return {"by_stat": by_stat, "atlas_cols": atlas_cols, "n_rows": len(hist)}


# ── live atlas lookup ────────────────────────────────────────────────────────────
def _atlas_for_player(player_id: Any, as_of_iso: str) -> Dict[str, Any]:
    """Leak-safe as-of atlas feature dict for one player (empty on any failure)."""
    try:
        from src.loop.atlas_features import atlas_feature_row
        return atlas_feature_row(player_id, as_of_iso, entity_type="player")
    except Exception:
        return {}


def _row_vector(proj: float, cur: float, period: float,
                atlas: Dict[str, Any], atlas_cols: List[str]) -> List[float]:
    """Assemble the [proj, cur, period, *atlas] vector for the trained corrector."""
    import math
    vec: List[float] = [proj, cur, period]
    for c in atlas_cols:
        v = atlas.get(c)
        if isinstance(v, bool):
            vec.append(float(v))
        elif isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)):
            vec.append(float(v))
        else:
            vec.append(float("nan"))  # imputed to train-median inside the corrector
    return vec


def _num(v: Any, default: float = 0.0) -> float:
    try:
        f = float(v)
        return f if f == f else default  # drop NaN
    except (TypeError, ValueError):
        return default


# ── public API ────────────────────────────────────────────────────────────────────
def apply_atlas_correction(
    snapshot: Dict[str, Any],
    base_rows: List[Dict[str, Any]],
    as_of: Optional[Any] = None,
    device: str = "auto",
) -> List[Dict[str, Any]]:
    """Return atlas-corrected per-(player,stat) rows, or ``base_rows`` unchanged.

    Args:
        snapshot:  the live snapshot dict (same shape ``project_snapshot`` consumes);
                   used for the leak boundary (its ``date``/``game_date``/``start_time``).
        base_rows: the projector's output rows, each at least
                   ``{player_id, stat, projected_final}`` (and ideally ``current``,
                   ``period``).
        as_of:     explicit ISO leak boundary; overrides the snapshot date when given.
        device:    "auto" (default), "cuda", or "cpu" for the corrector fit/predict.

    Behaviour:
        * If ``is_enabled()`` is False -> **pure no-op**: returns ``base_rows`` as-is.
        * If enabled -> trains (cached) per-stat base+atlas correctors on the leak-safe
          history strictly before the snapshot date and rewrites ``projected_final`` for
          every (player,stat) whose stat has a trusted corrector. Rows whose stat has no
          corrector, whose corrected value is non-finite, or that error out keep the
          original projection. Returns rows with the SAME (player,stat) keys, all with a
          finite ``projected_final``.

    The returned list is always safe to hand back to the live page; on any failure the
    original projection is preserved.
    """
    # Disabled -> byte-identical pass-through. Touch nothing.
    if not is_enabled():
        return base_rows
    if not base_rows:
        return base_rows

    as_of_iso = _snapshot_date(snapshot, as_of)
    if not as_of_iso:
        return base_rows  # no leak boundary -> cannot join atlas safely -> no-op

    dev = _resolve_device(device)
    try:
        model = _train_corrector(as_of_iso, dev)
    except Exception:
        return base_rows
    by_stat = model.get("by_stat") or {}
    atlas_cols = model.get("atlas_cols") or []
    if not by_stat:
        # Nothing trustworthy fitted (e.g. no leak-safe history) -> pass-through copies.
        return [dict(r) for r in base_rows]

    # Default period from the snapshot for rows that don't carry their own.
    snap_period = _num(snapshot.get("period"), 0.0)

    # Cache the per-player atlas lookup across this snapshot's rows.
    atlas_cache: Dict[Any, Dict[str, Any]] = {}

    out: List[Dict[str, Any]] = []
    for r in base_rows:
        nr = dict(r)
        stat = nr.get("stat")
        pid = nr.get("player_id")
        base_proj = _num(nr.get("projected_final"))
        corrector = by_stat.get(stat) if stat is not None else None
        if corrector is None or pid is None:
            out.append(nr)
            continue
        try:
            cur = _num(nr.get("current", nr.get("cur", 0.0)))
            period = _num(nr.get("period", snap_period), snap_period)
            atlas = atlas_cache.get(pid)
            if atlas is None:
                atlas = _atlas_for_player(pid, as_of_iso)
                atlas_cache[pid] = atlas
            vec = _row_vector(base_proj, cur, period, atlas, atlas_cols)
            corrected = corrector(vec)
            if corrected != corrected or corrected in (float("inf"), float("-inf")):
                out.append(nr)  # non-finite -> keep base
                continue
            nr["projected_final_base"] = base_proj
            nr["projected_final"] = float(corrected)
            nr["atlas_corrected"] = True
        except Exception:
            out.append(dict(r))  # any failure -> untouched base
            continue
        out.append(nr)
    return out


def clear_corrector_cache() -> None:
    """Drop the cached trained correctors (call after a fresh atlas/history build)."""
    _train_corrector.cache_clear()
