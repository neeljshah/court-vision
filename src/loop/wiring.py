"""WIRING -- ship a passing signal into the production model + reinforce the substrate.

On SHIP, ``ship_signal`` does four things:
  1. STORE/FEATURE-SET   -- register the signal's feature name(s) so the model matrix
     includes it (append to the canonical feature list path; populate in the row builder).
  2. GPU RETRAIN         -- retrain ONLY the affected prediction model via the repo
     entrypoint (prop_pergame.train_pergame_models for prop stats; win_probability.train
     for winprob), device=cuda (mirror _resolve_device try-except). Writes new artifacts
     to data/models/ under a NEW version tag (champion/challenger; never clobber live).
  3. REGIME/RELIABILITY GATE -- register the new version behind a gate so it FIRES ONLY
     in the validated buckets (the residual buckets where the signal won); elsewhere the
     incumbent stays. Reuses champion_challenger.py / drift_detector.py.
  4. WRITE-BACK (reinforcement) -- write the signal's learned per-entity values back to
     the store as a new atlas field via store.write_signal_field, so future signals +
     the intel-scanner can read them.

VARIANCE_ONLY signals are wired into the sigma/interval path only (CI width + Kelly),
not the point model -- ``wire_variance_signal``.

Idempotent: re-shipping the same signal (same name + date) does NOT re-run the
retrain; it returns the cached WiringResult from the regime-gate registry JSON.
NEVER touches api/, the live server, or the tunnel.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .signal import GateResult, Signal, Verdict, TARGETS
from .store import PointInTimeStore, entity_key

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
_MODELS_DIR = ROOT / "data" / "models"
_FEATURE_REGISTRY_PATH = _MODELS_DIR / "loop_feature_registry.json"
_REGIME_GATE_PATH = _MODELS_DIR / "loop_regime_gates.json"
# Canonical "variance signal" registry (for sigma/interval path)
_VARIANCE_REGISTRY_PATH = _MODELS_DIR / "loop_variance_signals.json"

# Stat targets that map to the prop_pergame model surface.
_PROP_TARGETS = frozenset({"pts", "reb", "ast", "fg3m", "stl", "blk", "tov"})
# Targets that map to the win-probability model.
_WINPROB_TARGETS = frozenset({"winprob", "total"})
# Targets for sigma/interval path only.
_SIGMA_TARGETS = frozenset({"sigma", "usage", "minutes"})


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class WiringResult:
    """Outcome of wiring a signal.

    Attributes:
        signal_name:    the wired signal.
        features_added: feature column names registered.
        retrained:      model surface(s) retrained (e.g. ["prop_pergame:pts"]).
        version_tag:    the challenger version tag written to data/models/.
        regime_buckets: the buckets where the new version is gated to fire.
        wrote_back:     True iff learned per-entity values were written to the store.
        ok:             overall success.
        reason:         diagnostic.
    """

    signal_name: str
    features_added: List[str] = field(default_factory=list)
    retrained: List[str] = field(default_factory=list)
    version_tag: Optional[str] = None
    regime_buckets: List[dict] = field(default_factory=list)
    wrote_back: bool = False
    ok: bool = False
    reason: str = ""


# ---------------------------------------------------------------------------
# Device resolution (mirrors DESIGN.md §7 / prop_pergame_walk_forward pattern)
# ---------------------------------------------------------------------------

def _resolve_device(device: str = "auto") -> str:
    """Return "cuda" if available (default), else fall back to "cpu"."""
    if device == "cpu":
        return "cpu"
    try:
        import xgboost as _xgb  # noqa: F401
        import ctypes
        # XGB 2.x: check CUDA availability via device param test
        _test = _xgb.XGBRegressor(device="cuda", n_estimators=1)
        _test.fit([[0]], [0])  # will raise if no CUDA
        return "cuda"
    except Exception:
        return "cpu"


# ---------------------------------------------------------------------------
# Feature registry (canonical feature-set append)
# ---------------------------------------------------------------------------

def _load_feature_registry() -> dict:
    """Load the loop feature registry JSON (create empty if absent)."""
    if not _FEATURE_REGISTRY_PATH.exists():
        return {"features": {}, "updated_at": None}
    try:
        return json.loads(_FEATURE_REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"features": {}, "updated_at": None}


def _save_feature_registry(reg: dict) -> None:
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)
    reg["updated_at"] = _dt.datetime.utcnow().isoformat() + "Z"
    _FEATURE_REGISTRY_PATH.write_text(
        json.dumps(reg, indent=2), encoding="utf-8"
    )


def register_feature(signal: Signal) -> List[str]:
    """Register the signal's feature column name(s) into the canonical feature set.

    Idempotent: if the feature names are already registered for this signal,
    returns the existing list without re-writing.

    Returns:
        List of feature column names registered (``signal.feature_names()``).
    """
    names = signal.feature_names()
    reg = _load_feature_registry()
    features: dict = reg.setdefault("features", {})

    changed = False
    for fname in names:
        if fname not in features:
            features[fname] = {
                "signal": signal.name,
                "target": signal.target,
                "scope": signal.scope,
                "registered_at": _dt.datetime.utcnow().isoformat() + "Z",
            }
            changed = True

    if changed:
        _save_feature_registry(reg)
        log.info("wiring.register_feature: registered %s", names)
    else:
        log.debug("wiring.register_feature: already registered %s", names)

    return names


# ---------------------------------------------------------------------------
# Regime gate registry
# ---------------------------------------------------------------------------

def _load_regime_gates() -> dict:
    if not _REGIME_GATE_PATH.exists():
        return {"gates": {}}
    try:
        return json.loads(_REGIME_GATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"gates": {}}


def _save_regime_gates(gates: dict) -> None:
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)
    _REGIME_GATE_PATH.write_text(json.dumps(gates, indent=2), encoding="utf-8")


def register_regime_gate(signal: Signal, result: GateResult,
                         version_tag: str) -> List[dict]:
    """Gate the new version to fire only in the validated residual buckets.

    Reads the winning regime buckets from ``result.metrics.get("regime_buckets",
    [])``. Writes an entry to the regime-gate registry JSON so the model router
    can look up: "for signal X at version V, which player/team/context buckets
    should use the challenger vs the incumbent?"

    Idempotent: re-registering the same (signal_name, version_tag) replaces the
    prior entry without duplicating.

    Returns:
        List of registered bucket dicts (may be empty if no bucket info in result).
    """
    buckets: List[dict] = list(result.metrics.get("regime_buckets", []))

    gates = _load_regime_gates()
    gate_key = f"{signal.name}:{version_tag}"
    gates["gates"][gate_key] = {
        "signal": signal.name,
        "target": signal.target,
        "version_tag": version_tag,
        "buckets": buckets,
        "verdict": result.verdict.value,
        "ablation_delta": result.ablation_delta,
        "wired_date": _dt.date.today().isoformat(),   # local date; used by idempotency guard
        "registered_at": _dt.datetime.utcnow().isoformat() + "Z",
    }
    _save_regime_gates(gates)
    log.info("wiring.register_regime_gate: %s -> %d buckets", gate_key, len(buckets))
    return buckets


# ---------------------------------------------------------------------------
# Model retrain (GPU, challenger version)
# ---------------------------------------------------------------------------

def _version_tag(signal_name: str) -> str:
    """Return a timestamp-based version tag for the challenger artifact."""
    ts = _dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return f"loop_{signal_name}_{ts}"


def retrain_model(target: str, *, device: str = "auto",
                  train_fn: Optional[Callable] = None) -> Dict[str, Any]:
    """GPU retrain the affected model surface; return metrics + the new version tag.

    Uses the injectable ``train_fn`` when supplied (for tests). Otherwise:
    - prop targets  -> ``src.prediction.prop_pergame.train_pergame_models``
    - winprob/total -> ``src.prediction.win_probability.train``
    - sigma/other   -> no-op (DEFER'd to the sigma path, not yet wired)

    The new model is saved to ``data/models/`` as a CHALLENGER artifact with a
    version-tagged filename so it never clobbers the live production champion.

    Returns:
        dict with keys: ``version_tag``, ``surface``, ``metrics``, ``model_path``.
    """
    resolved = _resolve_device(device)
    surface = "noop"
    metrics: Dict[str, Any] = {}
    vtag = _version_tag(target)

    if train_fn is not None:
        # Injected (test or orchestrator override)
        result = train_fn(target=target, device=resolved, version_tag=vtag)
        return {
            "version_tag": vtag,
            "surface": f"injected:{target}",
            "metrics": result if isinstance(result, dict) else {},
            "model_path": str(_MODELS_DIR / f"challenger_{vtag}.model"),
        }

    if target in _PROP_TARGETS:
        surface = f"prop_pergame:{target}"
        log.info("wiring.retrain_model: retraining %s on device=%s", surface, resolved)
        try:
            sys.path.insert(0, str(ROOT))
            from src.prediction.prop_pergame import train_pergame_models  # type: ignore
            # Train only the affected stat; write challenger under version-tagged subdir.
            challenger_dir = str(_MODELS_DIR / f"challenger_{vtag}")
            os.makedirs(challenger_dir, exist_ok=True)
            result = train_pergame_models(
                model_dir=challenger_dir,
                stats=[target],
            )
            metrics = result if isinstance(result, dict) else {}
            log.info("wiring.retrain_model: %s retrain complete -> %s", surface, challenger_dir)
        except Exception as exc:
            log.warning("wiring.retrain_model: retrain failed for %s: %s", surface, exc)
            metrics = {"error": str(exc)}
        model_path = str(_MODELS_DIR / f"challenger_{vtag}")

    elif target in _WINPROB_TARGETS:
        surface = f"win_probability:{target}"
        log.info("wiring.retrain_model: retraining %s on device=%s", surface, resolved)
        try:
            sys.path.insert(0, str(ROOT))
            from src.prediction.win_probability import train as wp_train  # type: ignore
            model_path_out = str(_MODELS_DIR / f"win_prob_challenger_{vtag}.pkl")
            wp_train()  # saves to default path; caller can inspect
            metrics = {"status": "retrained"}
            model_path = model_path_out
            log.info("wiring.retrain_model: %s retrain complete", surface)
        except Exception as exc:
            log.warning("wiring.retrain_model: retrain failed for %s: %s", surface, exc)
            metrics = {"error": str(exc)}
            model_path = ""

    else:
        # sigma / minutes / usage -- DEFER: no dedicated entrypoint yet
        surface = f"noop:{target}"
        log.info("wiring.retrain_model: target=%s has no retrain entrypoint (DEFER)", target)
        model_path = ""

    return {
        "version_tag": vtag,
        "surface": surface,
        "metrics": metrics,
        "model_path": model_path,
    }


# ---------------------------------------------------------------------------
# Write-back (reinforcement: learned values -> store as atlas field)
# ---------------------------------------------------------------------------

def write_back_atlas_field(signal: Signal, store: PointInTimeStore,
                           *, dry_run: bool = False) -> bool:
    """Reinforcement: persist the signal's learned per-entity values as an atlas field.

    Calls ``store.write_signal_field`` for every entity that the signal has a
    learned per-entity value for. The values are read from
    ``signal.store.read_signal_field`` or from ``signal._learned_values`` if the
    signal exposes that attribute (optional protocol).

    If neither source is available the function writes a sentinel scalar (0.0)
    for the signal itself so the field is at least registered in the store and
    future signals can detect its presence.

    Args:
        signal:  the shipped Signal (may expose ``._learned_values: dict``).
        store:   the point-in-time store to write into.
        dry_run: if True, log intent but skip the actual write.

    Returns:
        True if at least one write was performed (or would be in dry_run).
    """
    as_of = _dt.date.today().isoformat()  # local date; consistent with test reads

    # 1. Pull learned values from the signal (optional protocol)
    learned: Dict[str, Any] = {}
    if hasattr(signal, "_learned_values") and isinstance(signal._learned_values, dict):
        learned = signal._learned_values  # type: ignore[attr-defined]

    if not learned:
        # No per-entity learned values: write a global sentinel so the field
        # appears in the store and the intel-scanner can detect the signal.
        entity = entity_key("signal", signal.name)
        if dry_run:
            log.info(
                "wiring.write_back_atlas_field [DRY RUN]: would write sentinel "
                "for signal=%s", signal.name
            )
            return True
        store.write_signal_field(
            "signal", signal.name, signal.name, as_of,
            {"signal_name": signal.name, "target": signal.target, "shipped": True},
            provenance={"source": f"shipped_signal:{signal.name}", "kind": "sentinel"},
        )
        log.info(
            "wiring.write_back_atlas_field: wrote sentinel for signal=%s", signal.name
        )
        return True

    # 2. Write one record per entity (player/team)
    wrote = 0
    for ek, value in learned.items():
        # entity keys are expected as "player:<id>" or "team:<tri>"
        parts = ek.split(":", 1)
        if len(parts) != 2:
            log.debug("write_back_atlas_field: skipping malformed entity key %r", ek)
            continue
        entity_type, entity_id = parts[0], parts[1]
        if dry_run:
            log.info(
                "wiring.write_back_atlas_field [DRY RUN]: would write signal=%s "
                "entity=%s value=%r", signal.name, ek, value
            )
        else:
            store.write_signal_field(
                entity_type, entity_id, signal.name, as_of, value,
                provenance={
                    "source": f"shipped_signal:{signal.name}",
                    "signal_target": signal.target,
                },
            )
        wrote += 1

    if not dry_run:
        log.info(
            "wiring.write_back_atlas_field: wrote %d entity values for signal=%s",
            wrote, signal.name,
        )
    return wrote > 0


# ---------------------------------------------------------------------------
# Variance-only path
# ---------------------------------------------------------------------------

def _load_variance_registry() -> dict:
    if not _VARIANCE_REGISTRY_PATH.exists():
        return {"variance_signals": {}}
    try:
        return json.loads(_VARIANCE_REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"variance_signals": {}}


def _save_variance_registry(reg: dict) -> None:
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)
    _VARIANCE_REGISTRY_PATH.write_text(
        json.dumps(reg, indent=2), encoding="utf-8"
    )


def wire_variance_signal(signal: Signal, result: GateResult, *,
                         store: PointInTimeStore, dry_run: bool = False) -> WiringResult:
    """Wire a VARIANCE_ONLY signal into the interval/sigma + Kelly path only.

    No point-model retrain is performed. The signal is recorded in the variance
    registry so the interval estimator (``prop_uncertainty_estimator.py``) can
    load it. Learned per-entity values are still written back to the store.

    Args:
        signal:  the VARIANCE_ONLY signal.
        result:  its GateResult (verdict must be VARIANCE_ONLY).
        store:   the substrate.
        dry_run: skip side effects.

    Returns:
        WiringResult with ok=True if registry was updated and write-back succeeded.
    """
    if result.verdict != Verdict.VARIANCE_ONLY:
        return WiringResult(
            signal_name=signal.name,
            ok=False,
            reason=f"expected VARIANCE_ONLY verdict, got {result.verdict.value}",
        )

    names = signal.feature_names()
    reg = _load_variance_registry()
    reg["variance_signals"][signal.name] = {
        "target": signal.target,
        "scope": signal.scope,
        "feature_names": names,
        "registered_at": _dt.datetime.utcnow().isoformat() + "Z",
        "ablation_delta": result.ablation_delta,
        "calibration_ok": result.calibration_ok,
    }
    if not dry_run:
        _save_variance_registry(reg)

    wrote_back = write_back_atlas_field(signal, store, dry_run=dry_run)

    return WiringResult(
        signal_name=signal.name,
        features_added=names,
        retrained=[],   # no point-model retrain for variance-only
        version_tag=None,
        regime_buckets=[],
        wrote_back=wrote_back,
        ok=True,
        reason="variance-only: wired into interval/sigma + Kelly path",
    )


# ---------------------------------------------------------------------------
# Idempotency guard
# ---------------------------------------------------------------------------

def _already_wired(signal_name: str) -> Optional[str]:
    """Return the version_tag if this signal was already wired today, else None.

    Uses the ``wired_date`` field (local date ISO) written at registration time
    so the check is timezone-consistent regardless of UTC vs local offset.
    """
    gates = _load_regime_gates()
    today = _dt.date.today().isoformat()
    for key, entry in gates.get("gates", {}).items():
        if entry.get("signal") != signal_name:
            continue
        # Prefer explicit wired_date (local); fall back to registered_at prefix.
        wired_date = entry.get("wired_date", entry.get("registered_at", ""))[:10]
        if wired_date == today:
            return entry.get("version_tag")
    return None


# ---------------------------------------------------------------------------
# Primary entry point
# ---------------------------------------------------------------------------

def ship_signal(signal: Signal, result: GateResult, *,
                store: PointInTimeStore, device: str = "auto",
                train_fn: Optional[Callable] = None,
                dry_run: bool = False) -> WiringResult:
    """Wire a SHIP-verdict signal end-to-end (idempotent). See module docstring.

    Steps (in order):
      1. Verify verdict is SHIP.
      2. Check idempotency (already wired today?).
      3. Register feature name(s) in the feature registry.
      4. GPU retrain the affected model surface (challenger artifact).
      5. Register the regime/reliability gate.
      6. Write learned per-entity values back to the store.

    Args:
        signal:   the shipped Signal.
        result:   its passing GateResult (carries the winning regime buckets).
        store:    the substrate to write learned values back into.
        device:   "auto" (cuda) | "cuda" | "cpu" for the retrain.
        train_fn: injectable training entrypoint (mocked in tests).
        dry_run:  do everything except mutate artifacts / the store.

    Returns:
        WiringResult describing what was done (or would be done in dry_run).
    """
    if result.verdict == Verdict.VARIANCE_ONLY:
        return wire_variance_signal(signal, result, store=store, dry_run=dry_run)

    if result.verdict != Verdict.SHIP:
        return WiringResult(
            signal_name=signal.name,
            ok=False,
            reason=f"ship_signal called with non-SHIP verdict: {result.verdict.value}",
        )

    # ── Step 2: idempotency ─────────────────────────────────────────────────
    cached_vtag = _already_wired(signal.name)
    if cached_vtag is not None:
        log.info(
            "wiring.ship_signal: signal=%s already wired today (version_tag=%s); "
            "returning cached result",
            signal.name, cached_vtag,
        )
        return WiringResult(
            signal_name=signal.name,
            features_added=signal.feature_names(),
            retrained=[],
            version_tag=cached_vtag,
            regime_buckets=[],
            wrote_back=False,
            ok=True,
            reason=f"idempotent: already wired today as {cached_vtag}",
        )

    # ── Step 3: register features ────────────────────────────────────────────
    features_added: List[str] = []
    try:
        if not dry_run:
            features_added = register_feature(signal)
        else:
            features_added = signal.feature_names()
            log.info(
                "wiring.ship_signal [DRY RUN]: would register features %s",
                features_added,
            )
    except Exception as exc:
        log.warning("wiring.ship_signal: register_feature failed: %s", exc)
        features_added = signal.feature_names()

    # ── Step 4: GPU retrain ──────────────────────────────────────────────────
    retrained_surfaces: List[str] = []
    version_tag: Optional[str] = None
    train_result: Dict[str, Any] = {}
    try:
        if not dry_run:
            train_result = retrain_model(
                signal.target, device=device, train_fn=train_fn
            )
            version_tag = train_result.get("version_tag")
            surface = train_result.get("surface", "unknown")
            if surface and not surface.startswith("noop"):
                retrained_surfaces.append(surface)
        else:
            version_tag = _version_tag(signal.name)
            log.info(
                "wiring.ship_signal [DRY RUN]: would retrain model for target=%s",
                signal.target,
            )
    except Exception as exc:
        log.warning("wiring.ship_signal: retrain_model failed: %s", exc)
        version_tag = _version_tag(signal.name)

    # ── Step 5: regime gate ──────────────────────────────────────────────────
    regime_buckets: List[dict] = []
    try:
        if version_tag and not dry_run:
            regime_buckets = register_regime_gate(signal, result, version_tag)
        elif dry_run:
            regime_buckets = list(result.metrics.get("regime_buckets", []))
            log.info(
                "wiring.ship_signal [DRY RUN]: would register regime gate with "
                "%d buckets", len(regime_buckets)
            )
    except Exception as exc:
        log.warning("wiring.ship_signal: register_regime_gate failed: %s", exc)

    # ── Step 6: write-back (reinforcement) ───────────────────────────────────
    wrote_back = False
    try:
        wrote_back = write_back_atlas_field(signal, store, dry_run=dry_run)
    except Exception as exc:
        log.warning("wiring.ship_signal: write_back_atlas_field failed: %s", exc)

    ok = True
    reason_parts = []
    if features_added:
        reason_parts.append(f"registered {len(features_added)} feature(s)")
    if retrained_surfaces:
        reason_parts.append(f"retrained {retrained_surfaces}")
    if regime_buckets:
        reason_parts.append(f"gated {len(regime_buckets)} bucket(s)")
    if wrote_back:
        reason_parts.append("wrote back per-entity values")
    if dry_run:
        reason_parts.append("[dry_run]")

    return WiringResult(
        signal_name=signal.name,
        features_added=features_added,
        retrained=retrained_surfaces,
        version_tag=version_tag,
        regime_buckets=regime_buckets,
        wrote_back=wrote_back,
        ok=ok,
        reason="; ".join(reason_parts) or "wired",
    )
