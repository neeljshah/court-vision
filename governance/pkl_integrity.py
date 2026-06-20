"""governance.pkl_integrity -- model registration + n_features_in integrity gate.

Registers trained model artifacts in an append-only ``model_registry.jsonl`` and
verifies that a pkl's ``n_features_in_`` matches what was recorded at registration.

WHY THIS EXISTS: a feature wired into training but absent at inference silently
reads 0.0 -- a permanent Brier regression.  We block promotion of any artifact
where pkl.n_features_in_ disagrees with the registry meta.

register_model(meta) -- appends to model_registry.jsonl; BLOCKS on n-mismatch vs
  optional feature_catalog_n.
integrity_check(path_or_meta) -- loads pkl.n_features_in_ when reachable; notes a
  structural skip when offline.  n-mismatch -> ok=False (never raises).

MODEL_REGISTRY_PATH: data/frontend/governance/model_registry.jsonl (gitignored).

DECISION-ONLY: never authorises a bet.  Never writes data/registry/.  No flag.
<=300 LOC; ASCII; no secrets.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Reuse the lock-guarded append primitive so the registry gets the same
# concurrency guarantees as the CLV ledger.
import scripts.platformkit.clv_ledger_io as _ledger_io

# ---------------------------------------------------------------------------
# Registry path (local-only; gitignored via data/)
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_REGISTRY_PATH: Path = (
    _REPO_ROOT / "data" / "frontend" / "governance" / "model_registry.jsonl"
)

REGISTRY_VERSION = "model_registry.v1"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_registry(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Read all intact registry rows. Missing file -> []. Never raises."""
    target = Path(path) if path is not None else MODEL_REGISTRY_PATH
    if not target.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with target.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return rows
    return rows


def _try_load_n_features(model_path: Path) -> Tuple[Optional[int], str]:
    """Attempt to read pkl.n_features_in_ from a sklearn-style model.

    Returns (n_features_in, status_note) where status_note describes what
    happened.  NEVER raises -- a missing or unloadable pkl is a structural gap,
    not a hard error, so we return (None, note) and let the caller decide.
    """
    if not model_path.exists():
        return None, "pkl not found at %s (offline / not yet built)" % model_path
    try:
        import pickle  # stdlib; safe for read-only load of local artifacts
        with model_path.open("rb") as fh:
            obj = pickle.load(fh)
        n = getattr(obj, "n_features_in_", None)
        if n is None:
            return None, "pkl loaded but has no n_features_in_ attribute"
        return int(n), "pkl loaded OK"
    except Exception as exc:
        return None, "pkl load failed: %s" % str(exc)[:200]


def _validate_meta(meta: Dict[str, Any]) -> List[str]:
    """Structural validation of a registration meta dict. Returns error strings."""
    errors: List[str] = []
    for required in ("model_id", "n_features_in", "kind"):
        if not meta.get(required):
            errors.append("missing required field: %r" % required)
    n = meta.get("n_features_in")
    if n is not None:
        try:
            if int(n) < 0:
                errors.append("n_features_in must be >= 0, got %r" % n)
        except (TypeError, ValueError):
            errors.append("n_features_in must be an integer, got %r" % type(n).__name__)
    # If a feature_catalog count is provided, it must match n_features_in.
    catalog_n = meta.get("feature_catalog_n")
    if catalog_n is not None and n is not None:
        try:
            if int(catalog_n) != int(n):
                errors.append(
                    "n_features_in=%d does not match feature_catalog_n=%d -- "
                    "BLOCKED: train/inference parity mismatch" % (int(n), int(catalog_n))
                )
        except (TypeError, ValueError):
            errors.append("feature_catalog_n must be an integer")
    return errors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class IntegrityError(Exception):
    """Raised when a model fails the n_features_in integrity check."""


def register_model(
    meta: Dict[str, Any],
    *,
    registry_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Register a trained model artifact in the model_registry.jsonl.

    *meta* MUST contain:
      - ``model_id``      -- unique identifier for this artifact (str)
      - ``n_features_in`` -- feature width the model was trained on (int >= 0)
      - ``kind``          -- model family / sport-blind key (str)

    Optional fields in *meta*:
      - ``feature_catalog_n`` -- expected count from the feature catalog; if
                                  provided and != n_features_in, registration is
                                  BLOCKED with IntegrityError.
      - ``model_path``        -- path to the pkl (str); recorded but not loaded
                                  at registration time.
      - any other provenance keys (corpora, scores, seeds, ...)

    Returns the complete registry record dict (includes timestamp + version).
    Raises IntegrityError when validation fails (n-mismatch, missing required
    fields).  The registry write itself uses the lock-guarded append_row.
    """
    errors = _validate_meta(meta)
    if errors:
        raise IntegrityError(
            "register_model BLOCKED: %s" % "; ".join(errors)
        )
    record: Dict[str, Any] = {
        "registry_version": REGISTRY_VERSION,
        "registered_at": _now_iso(),
        "model_id": str(meta["model_id"]),
        "kind": str(meta["kind"]),
        "n_features_in": int(meta["n_features_in"]),
        "model_path": str(meta.get("model_path") or ""),
        "meta": {k: v for k, v in meta.items()
                 if k not in ("model_id", "kind", "n_features_in", "model_path")},
    }
    target = Path(registry_path) if registry_path is not None else MODEL_REGISTRY_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    _ledger_io.append_row(record, path=target)
    return record


def integrity_check(
    model_path_or_meta: "str | Path | Dict[str, Any]",
    *,
    registry_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Verify a pkl or meta dict against the model registry.

    Accepts:
      - a filesystem path (str or Path) to a pkl artifact, OR
      - a meta dict (must contain ``model_id`` + ``n_features_in``).

    Logic:
      1. Resolve the model_id and the expected n_features_in from the registry
         (the LAST registered record for that model_id wins, most-recent-wins
         convention -- a retrain increments the expected width).
      2. If a pkl path is reachable, load its n_features_in_ attribute and
         compare against the registry record.  A mismatch BLOCKS.
      3. If the pkl is offline / unavailable, record that gap (structural skip)
         but do not block -- the meta check is still performed.
      4. If a meta dict is passed instead of a path, compare the dict's
         n_features_in against the registry.

    Returns a result dict:
      {
        "ok": bool,                   -- False iff an n-mismatch was found
        "model_id": str | None,
        "expected_n": int | None,     -- from the registry
        "observed_n": int | None,     -- from the pkl or meta
        "pkl_loaded": bool,           -- True iff the pkl was actually loaded
        "pkl_status": str,            -- what happened during pkl load attempt
        "structural_skip": bool,      -- True when pkl was absent / unloadable
        "reasons": [str, ...],        -- why ok=False (empty iff ok=True)
        "registry_version": str,
      }
    Never raises.
    """
    out: Dict[str, Any] = {
        "ok": True,
        "model_id": None,
        "expected_n": None,
        "observed_n": None,
        "pkl_loaded": False,
        "pkl_status": "not attempted",
        "structural_skip": False,
        "reasons": [],
        "registry_version": REGISTRY_VERSION,
    }

    # --- resolve inputs -------------------------------------------------------
    is_path = isinstance(model_path_or_meta, (str, Path))
    meta_dict: Optional[Dict[str, Any]] = None
    pkl_path: Optional[Path] = None
    observed_n: Optional[int] = None

    if is_path:
        pkl_path = Path(model_path_or_meta)
        # Infer model_id from stem; caller can override via a wrapper.
        out["model_id"] = pkl_path.stem
    else:
        meta_dict = dict(model_path_or_meta)  # type: ignore[arg-type]
        out["model_id"] = str(meta_dict.get("model_id") or "")
        raw_n = meta_dict.get("n_features_in")
        if raw_n is not None:
            try:
                observed_n = int(raw_n)
            except (TypeError, ValueError):
                out["reasons"].append(
                    "meta n_features_in is not an integer: %r" % raw_n)
                out["ok"] = False
        out["pkl_status"] = "meta dict provided, no pkl path"

    # --- registry lookup ------------------------------------------------------
    registry = _load_registry(registry_path)
    model_id = out["model_id"]
    expected_n: Optional[int] = None
    for row in reversed(registry):  # most-recent-wins
        if str(row.get("model_id") or "") == model_id:
            try:
                expected_n = int(row["n_features_in"])
            except (KeyError, TypeError, ValueError):
                pass
            break
    out["expected_n"] = expected_n

    if expected_n is None and model_id:
        out["reasons"].append(
            "model_id %r not found in registry -- unregistered artifact" % model_id)
        out["ok"] = False

    # --- pkl load (when a path was given) -------------------------------------
    if pkl_path is not None:
        n_from_pkl, status = _try_load_n_features(pkl_path)
        out["pkl_status"] = status
        if n_from_pkl is not None:
            out["pkl_loaded"] = True
            observed_n = n_from_pkl
        else:
            out["structural_skip"] = True

    out["observed_n"] = observed_n

    # --- n-mismatch check -----------------------------------------------------
    if expected_n is not None and observed_n is not None:
        if observed_n != expected_n:
            out["reasons"].append(
                "n_features_in MISMATCH: pkl/meta says %d, registry says %d -- "
                "BLOCKED: promote this artifact only after retraining with the "
                "current feature catalog" % (observed_n, expected_n)
            )
            out["ok"] = False

    if out["reasons"]:
        out["ok"] = False

    return out


__all__ = [
    "MODEL_REGISTRY_PATH",
    "REGISTRY_VERSION",
    "IntegrityError",
    "register_model",
    "integrity_check",
]
