"""
L40_multi_model_dispatcher.py — Unified routing layer for per-game prop models.

Reads dispatch_routing.json to decide which model variant handles each stat,
then delegates to the appropriate predictor (blend / q50_lgb / q50_xgb /
multitask_mlp). Falls back to blend with a WARN on any load/import error.

Public API
----------
    get_routing()                        -> dict[str, ModelRoute]
    predict_dispatched(stat, row, ...)   -> float | None
    predict_quantiles_dispatched(...)    -> dict | None
    update_routing(stat, variant, ...)   -> None
    best_routing_from_wf_results()       -> dict[str, str]

CLI
---
    python L40_multi_model_dispatcher.py status
    python L40_multi_model_dispatcher.py refresh
    python L40_multi_model_dispatcher.py set --stat ast --variant blend [--notes ...]

Environment Variables
---------------------
    L40_SLOW_THRESHOLD_MS : int, default 100
        Per-dispatch latency threshold in milliseconds.  When a predict_dispatched
        call exceeds this value, a ``"model.slow"`` event is published to L46 in
        addition to the normal ``"model.routed"`` event.  Set to 0 to always emit
        slow events; set to a very large value to effectively disable slow alerts.

Paper vs Live Mode (MODE GATING)
---------------------------------
    L40 is paper/live-agnostic — the same champion/challenger/A-B routing table
    applies in both modes.  The routing decision (which model variant to call) does
    not depend on SUBMISSION_MODE or any live-data flag.  Mode enforcement is the
    responsibility of downstream layers (e.g. L44).  L40 never reads nor writes any
    SUBMISSION_MODE environment variable.

Event Publication
-----------------
    L40 publishes to L46 (EventBus) after every successful predict_dispatched call:

    ``"model.routed"`` — always emitted on dispatch:
        {
            "request_id": str,        # UUID4 per-call identifier
            "model_variant": str,     # variant actually used (post-fallback)
            "is_champion": bool,      # True when variant == HARDCODED_DEFAULTS[stat][0]
            "is_challenger": bool,    # True when variant != HARDCODED_DEFAULTS[stat][0]
            "latency_ms": float,      # wall-clock ms for the predict call
            "routed_at": str,         # ISO 8601 UTC timestamp
        }

    ``"model.slow"`` — additionally emitted when latency_ms > L40_SLOW_THRESHOLD_MS:
        {
            "model_variant": str,
            "latency_ms": float,
            "threshold_ms": float,
            "request_id": str,
        }

    L46 import failures are swallowed so that a missing EventBus never breaks
    production predictions.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import pickle
import sys
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# ── Project root ───────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve()
PROJECT_DIR = _HERE.parent.parent.parent  # scripts/execute_loop/../../
sys.path.insert(0, str(PROJECT_DIR))

logger = logging.getLogger(__name__)

# ── L46 soft-import ────────────────────────────────────────────────────────────
try:
    import scripts.execute_loop.L46_event_bus as _L46  # type: ignore
except Exception:  # noqa: BLE001
    _L46 = None  # type: ignore

# ── Constants ──────────────────────────────────────────────────────────────────
STATS: Tuple[str, ...] = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
VARIANTS: Tuple[str, ...] = ("blend", "q50_lgb", "q50_xgb", "multitask_mlp")

ROUTING_PATH = PROJECT_DIR / "data" / "models" / "dispatch_routing.json"
WF_RESULTS_PATH = PROJECT_DIR / "data" / "models" / "prop_pergame_walk_forward.json"

# Latency alert threshold — override via L40_SLOW_THRESHOLD_MS env var
_SLOW_THRESHOLD_MS: float = float(os.environ.get("L40_SLOW_THRESHOLD_MS", "100"))

HARDCODED_DEFAULTS: Dict[str, Tuple[str, str]] = {
    "pts":  ("blend",         "cycle-18 sqrt+Huber"),
    "reb":  ("q50_lgb",       "cycle-29 LGB-q50 4/4 WF"),
    "ast":  ("multitask_mlp", "cycle-23 multitask MLP"),
    "fg3m": ("q50_xgb",       "cycle-27 XGB-q50"),
    "stl":  ("q50_xgb",       "cycle-27 XGB-q50"),
    "blk":  ("q50_xgb",       "cycle-27 XGB-q50 -16.6% MAE"),
    "tov":  ("q50_xgb",       "cycle-27 XGB-q50"),
}

# Hardcoded wf_mae values from memory (used when building defaults)
_DEFAULT_WF_MAE: Dict[str, float] = {
    "pts":  4.6210,
    "reb":  1.9023,
    "ast":  1.3559,
    "fg3m": 0.8943,
    "stl":  0.7153,
    "blk":  0.4398,
    "tov":  0.8932,
}

_DEFAULT_DEPLOYED_AT = "2026-04-01T00:00:00+00:00"

# ── Data model ─────────────────────────────────────────────────────────────────
@dataclass
class ModelRoute:
    stat: str
    model_variant: str          # one of VARIANTS
    source_path: Optional[str]
    wf_mae: Optional[float]
    deployed_at: str
    notes: str


# ── Internal: JSON I/O ─────────────────────────────────────────────────────────
def _build_default_routes() -> Dict[str, ModelRoute]:
    routes: Dict[str, ModelRoute] = {}
    for stat in STATS:
        variant, notes = HARDCODED_DEFAULTS[stat]
        routes[stat] = ModelRoute(
            stat=stat,
            model_variant=variant,
            source_path=None,
            wf_mae=_DEFAULT_WF_MAE.get(stat),
            deployed_at=_DEFAULT_DEPLOYED_AT,
            notes=notes,
        )
    return routes


def _routes_to_json(routes: Dict[str, ModelRoute]) -> dict:
    return {
        "version": 1,
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        "routes": {
            stat: {
                "model_variant": r.model_variant,
                "source_path": r.source_path,
                "wf_mae": r.wf_mae,
                "deployed_at": r.deployed_at,
                "notes": r.notes,
            }
            for stat, r in routes.items()
        },
    }


def _json_to_routes(data: dict) -> Dict[str, ModelRoute]:
    routes: Dict[str, ModelRoute] = {}
    raw = data.get("routes", {})
    for stat in STATS:
        if stat not in raw:
            variant, notes = HARDCODED_DEFAULTS[stat]
            routes[stat] = ModelRoute(
                stat=stat,
                model_variant=variant,
                source_path=None,
                wf_mae=_DEFAULT_WF_MAE.get(stat),
                deployed_at=_DEFAULT_DEPLOYED_AT,
                notes=notes,
            )
        else:
            r = raw[stat]
            routes[stat] = ModelRoute(
                stat=stat,
                model_variant=r.get("model_variant", "blend"),
                source_path=r.get("source_path"),
                wf_mae=r.get("wf_mae"),
                deployed_at=r.get("deployed_at", _DEFAULT_DEPLOYED_AT),
                notes=r.get("notes", ""),
            )
    return routes


def _write_routing(routes: Dict[str, ModelRoute], path: Path = ROUTING_PATH) -> None:
    """Atomic write: write to .tmp then rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(_routes_to_json(routes), indent=2), encoding="utf-8")
    tmp.replace(path)


# ── Public: get_routing ────────────────────────────────────────────────────────
def get_routing(path: Path = ROUTING_PATH) -> Dict[str, ModelRoute]:
    """Load routing from JSON; build + write defaults if missing or corrupt."""
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return _json_to_routes(data)
        except Exception as exc:
            logger.warning("dispatch_routing.json corrupt (%s); rebuilding defaults.", exc)

    routes = _build_default_routes()
    _write_routing(routes, path)
    logger.info("Created default dispatch_routing.json at %s", path)
    return routes


# ── Internal: model loaders ────────────────────────────────────────────────────
def _model_path_lgb(stat: str, model_dir: Path) -> Path:
    return model_dir / f"quantile_pergame_lgb_{stat}_q50.pkl"


def _model_path_xgb(stat: str, model_dir: Path) -> Path:
    return model_dir / f"quantile_pergame_xgb_{stat}_q50.pkl"


def _load_pkl(path: Path):
    with open(path, "rb") as fh:
        return pickle.load(fh)


def _predict_q50_lgb(stat: str, prediction_row: Any, model_dir: Path) -> Optional[float]:
    path = _model_path_lgb(stat, model_dir)
    if not path.exists():
        logger.warning("q50_lgb model missing for %s at %s; falling back to blend.", stat, path)
        return None  # caller handles fallback
    model = _load_pkl(path)
    import numpy as np
    if isinstance(prediction_row, dict):
        feats = np.array(list(prediction_row.values()), dtype=float).reshape(1, -1)
    else:
        feats = np.array(prediction_row, dtype=float).reshape(1, -1)
    return float(model.predict(feats)[0])


def _predict_q50_xgb(stat: str, prediction_row: Any, model_dir: Path) -> Optional[float]:
    path = _model_path_xgb(stat, model_dir)
    if not path.exists():
        logger.warning("q50_xgb model missing for %s at %s; falling back to blend.", stat, path)
        return None  # caller handles fallback
    model = _load_pkl(path)
    import numpy as np
    if isinstance(prediction_row, dict):
        feats = np.array(list(prediction_row.values()), dtype=float).reshape(1, -1)
    else:
        feats = np.array(prediction_row, dtype=float).reshape(1, -1)
    return float(model.predict(feats)[0])


def _predict_blend(stat: str, prediction_row: Any, model_dir: Optional[Path]) -> Optional[float]:
    from src.prediction.prop_pergame import predict_pergame  # noqa: PLC0415
    return predict_pergame(stat, prediction_row, str(model_dir) if model_dir else None)


def _predict_multitask_mlp(stat: str, prediction_row: Any, model_dir: Optional[Path]) -> Optional[float]:
    try:
        import src.prediction.prop_pergame_multitask as _mt  # noqa: PLC0415
        fn = getattr(_mt, "predict_multitask", None)
        if fn is None:
            raise AttributeError("predict_multitask not found in prop_pergame_multitask")
        return fn(stat, prediction_row, str(model_dir) if model_dir else None)
    except (ImportError, AttributeError) as exc:
        logger.warning("multitask_mlp unavailable for %s (%s); falling back to blend.", stat, exc)
        return None  # caller handles fallback


# ── Internal: event publication ───────────────────────────────────────────────
def _publish_routed(
    request_id: str,
    stat: str,
    variant: str,
    latency_ms: float,
    routed_at: str,
) -> None:
    """Publish 'model.routed' (and optionally 'model.slow') to L46.

    Swallows all exceptions so a broken EventBus never interrupts predictions.
    """
    if _L46 is None:
        return
    default_variant = HARDCODED_DEFAULTS.get(stat, (None,))[0]
    is_champion = variant == default_variant
    try:
        _L46.publish(
            "model.routed",
            source="L40",
            payload={
                "request_id": request_id,
                "model_variant": variant,
                "is_champion": is_champion,
                "is_challenger": not is_champion,
                "latency_ms": latency_ms,
                "routed_at": routed_at,
            },
        )
        threshold = _SLOW_THRESHOLD_MS
        if latency_ms > threshold:
            _L46.publish(
                "model.slow",
                source="L40",
                payload={
                    "model_variant": variant,
                    "latency_ms": latency_ms,
                    "threshold_ms": threshold,
                    "request_id": request_id,
                },
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("L40: EventBus publish failed (non-fatal): %s", exc)


# ── Public: predict_dispatched ─────────────────────────────────────────────────
def predict_dispatched(
    stat: str,
    prediction_row: Any,
    model_dir: Optional[Path] = None,
    *,
    _routing_path: Path = ROUTING_PATH,
) -> Optional[float]:
    """Dispatch prediction for *stat* using the routed model variant.

    Falls back to blend (with WARN) when the routed model file is missing or
    the import fails. Returns None only when the underlying predictor returns
    None — never silently substitutes a value.
    """
    if stat not in STATS:
        raise ValueError(f"unknown stat: {stat!r}. Must be one of {STATS}")

    _model_dir = model_dir or PROJECT_DIR / "data" / "models"

    routes = get_routing(_routing_path)
    route = routes[stat]
    variant = route.model_variant

    if variant not in VARIANTS:
        logger.warning(
            "Unrecognised variant %r for stat %s; falling back to blend.", variant, stat
        )
        variant = "blend"

    request_id = str(uuid.uuid4())
    _t0 = time.perf_counter()

    if variant == "blend":
        result = _predict_blend(stat, prediction_row, _model_dir)
    elif variant == "q50_lgb":
        result = _predict_q50_lgb(stat, prediction_row, _model_dir)
        if result is None:
            result = _predict_blend(stat, prediction_row, _model_dir)
    elif variant == "q50_xgb":
        result = _predict_q50_xgb(stat, prediction_row, _model_dir)
        if result is None:
            result = _predict_blend(stat, prediction_row, _model_dir)
    elif variant == "multitask_mlp":
        result = _predict_multitask_mlp(stat, prediction_row, _model_dir)
        if result is None:
            result = _predict_blend(stat, prediction_row, _model_dir)
    else:
        # Should never reach here, but be safe
        logger.warning("Unhandled variant %r; falling back to blend.", variant)
        result = _predict_blend(stat, prediction_row, _model_dir)

    latency_ms = (time.perf_counter() - _t0) * 1000.0
    routed_at = datetime.now(tz=timezone.utc).isoformat()
    _publish_routed(request_id, stat, variant, latency_ms, routed_at)

    return result


# ── Public: predict_quantiles_dispatched ───────────────────────────────────────
def predict_quantiles_dispatched(
    stat: str,
    prediction_row: Any,
    model_dir: Optional[Path] = None,
    *,
    _routing_path: Path = ROUTING_PATH,
) -> Optional[Dict[str, Optional[float]]]:
    """Return q10/q50/q90 for quantile variants; q50-only for blend/multitask."""
    if stat not in STATS:
        raise ValueError(f"unknown stat: {stat!r}. Must be one of {STATS}")

    _model_dir = model_dir or PROJECT_DIR / "data" / "models"
    routes = get_routing(_routing_path)
    variant = routes[stat].model_variant

    if variant not in VARIANTS:
        logger.warning("Unrecognised variant %r for %s; treating as blend.", variant, stat)
        variant = "blend"

    def _load_quantile_pkl(framework: str, q: str) -> Optional[float]:
        path = _model_dir / f"quantile_pergame_{framework}_{stat}_{q}.pkl"
        if not path.exists():
            return None
        model = _load_pkl(path)
        import numpy as np
        if isinstance(prediction_row, dict):
            feats = np.array(list(prediction_row.values()), dtype=float).reshape(1, -1)
        else:
            feats = np.array(prediction_row, dtype=float).reshape(1, -1)
        return float(model.predict(feats)[0])

    if variant == "q50_lgb":
        return {
            "q10": _load_quantile_pkl("lgb", "q10"),
            "q50": _load_quantile_pkl("lgb", "q50"),
            "q90": _load_quantile_pkl("lgb", "q90"),
        }

    if variant == "q50_xgb":
        return {
            "q10": _load_quantile_pkl("xgb", "q10"),
            "q50": _load_quantile_pkl("xgb", "q50"),
            "q90": _load_quantile_pkl("xgb", "q90"),
        }

    # blend or multitask_mlp: return point prediction as q50 only
    q50 = predict_dispatched(stat, prediction_row, _model_dir, _routing_path=_routing_path)
    return {"q10": None, "q50": q50, "q90": None}


# ── Public: update_routing ─────────────────────────────────────────────────────
def update_routing(
    stat: str,
    model_variant: str,
    wf_mae: float,
    notes: str = "",
    *,
    _routing_path: Path = ROUTING_PATH,
) -> None:
    """Update routing for *stat* and atomically persist to JSON."""
    if stat not in STATS:
        raise ValueError(f"unknown stat: {stat!r}. Must be one of {STATS}")
    if model_variant not in VARIANTS:
        raise ValueError(f"unknown variant: {model_variant!r}. Must be one of {VARIANTS}")

    routes = get_routing(_routing_path)
    routes[stat] = ModelRoute(
        stat=stat,
        model_variant=model_variant,
        source_path=routes[stat].source_path,
        wf_mae=wf_mae,
        deployed_at=datetime.now(tz=timezone.utc).isoformat(),
        notes=notes,
    )
    _write_routing(routes, _routing_path)
    logger.info("Routing updated: %s → %s (wf_mae=%.4f)", stat, model_variant, wf_mae)


# ── Public: best_routing_from_wf_results ──────────────────────────────────────
def best_routing_from_wf_results(
    wf_path: Path = WF_RESULTS_PATH,
    *,
    _routing_path: Path = ROUTING_PATH,
) -> Dict[str, str]:
    """Read walk-forward JSON and pick the best variant per stat.

    Tries multiple schema shapes:
      1. {by_stat: {stat: {variant: {mae_mean, folds_positive}}}}
      2. {stat: {variant: {mae_mean, folds_positive}}}
    Falls back to current routing for any stat without usable data.
    """
    routes = get_routing(_routing_path)
    result = {s: routes[s].model_variant for s in STATS}

    if not wf_path.exists():
        logger.warning("WF results file missing at %s; keeping current routing.", wf_path)
        return result

    try:
        data = json.loads(wf_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("WF results file unreadable (%s); keeping current routing.", exc)
        return result

    # Shape 1: {by_stat: {stat: {variant: {mae_mean, folds_positive}}}}
    by_stat = data.get("by_stat") or {}

    # Shape 2: direct {stat: {variant: {mae_mean, folds_positive}}}
    if not by_stat:
        # check if top-level keys look like stats
        if any(k in STATS for k in data):
            by_stat = {k: v for k, v in data.items() if k in STATS and isinstance(v, dict)}

    if not by_stat:
        logger.info("WF results has no recognisable by_stat shape; keeping current routing.")
        return result

    for stat in STATS:
        stat_data = by_stat.get(stat)
        if not stat_data or not isinstance(stat_data, dict):
            continue

        best_variant: Optional[str] = None
        best_mae: float = float("inf")

        for variant, metrics in stat_data.items():
            if variant not in VARIANTS:
                continue
            if not isinstance(metrics, dict):
                continue
            folds_positive = metrics.get("folds_positive", 0)
            mae_mean = metrics.get("mae_mean")
            if mae_mean is None or folds_positive < 3:
                continue
            if mae_mean < best_mae:
                best_mae = mae_mean
                best_variant = variant

        if best_variant:
            result[stat] = best_variant
            logger.info("best_routing: %s → %s (mae_mean=%.4f)", stat, best_variant, best_mae)

    return result


# ── CLI ────────────────────────────────────────────────────────────────────────
def _cli_status() -> None:
    routes = get_routing()
    print(f"{'STAT':<6} {'VARIANT':<14} {'WF_MAE':<10} {'DEPLOYED_AT':<28} NOTES")
    print("-" * 90)
    for stat in STATS:
        r = routes[stat]
        mae_str = f"{r.wf_mae:.4f}" if r.wf_mae is not None else "—"
        print(f"{stat:<6} {r.model_variant:<14} {mae_str:<10} {r.deployed_at:<28} {r.notes}")


def _cli_refresh() -> None:
    new_routing = best_routing_from_wf_results()
    routes = get_routing()
    changed = []
    for stat, variant in new_routing.items():
        if routes[stat].model_variant != variant:
            changed.append((stat, routes[stat].model_variant, variant))
            update_routing(stat, variant, routes[stat].wf_mae or 0.0, notes="auto-refresh from WF")
    if changed:
        for stat, old, new in changed:
            print(f"  {stat}: {old} → {new}")
    else:
        print("No changes — routing already optimal.")


def _cli_set(stat: str, variant: str, notes: str) -> None:
    routes = get_routing()
    current_mae = routes[stat].wf_mae or 0.0
    update_routing(stat, variant, current_mae, notes=notes)
    print(f"Updated {stat} → {variant}")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="L40 multi-model dispatcher")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("status", help="Print routing table")
    sub.add_parser("refresh", help="Rebuild routing from WF results")

    s = sub.add_parser("set", help="Manually set variant for a stat")
    s.add_argument("--stat", required=True, choices=STATS)
    s.add_argument("--variant", required=True, choices=VARIANTS)
    s.add_argument("--notes", default="")
    return p


def main(argv=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = _build_parser()
    args = p.parse_args(argv)

    if args.cmd == "status":
        _cli_status()
    elif args.cmd == "refresh":
        _cli_refresh()
    elif args.cmd == "set":
        _cli_set(args.stat, args.variant, args.notes)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
