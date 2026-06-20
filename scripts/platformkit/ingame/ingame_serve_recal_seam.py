"""scripts.platformkit.ingame.ingame_serve_recal_seam -- do-no-harm serve-side shim.

Exposes recalibrate_served(p_home, frac_elapsed) that lazily loads
surfaces/nba_recal.json once and applies the persisted isotonic map per
time-bucket.  Returns exact identity passthrough when the file is absent or
empty so served behavior is unchanged until the producer ships a map.

This is the single seam that lets the proven Q4 ECE fix reach the live number
without editing gated src/ or kernel/.

DESIGN INVARIANTS (binding):
  * Identity-by-default: if nba_recal.json is absent, empty, malformed, or has
    no valid bucket, p_home is returned unchanged.  No drift in behaviour until
    the producer explicitly writes a SHIP/PARTIAL surface.
  * Lazy load, single load: the map is read from disk ONCE on first call and
    cached in a module-level slot.  Subsequent calls are pure in-memory.
  * Never raises: all IO / type / key errors fall back to identity.
  * No $ key: no monetary / dollar / roi / pnl field anywhere.
  * p stays in [0,1]: guaranteed by apply_recal (delegated to ingame_recal_apply).
  * Provenance string: return dict includes 'recal_provenance' recording which
    path was applied ('+recal(applied)') or why it was skipped
    ('+recal(identity:no-map)', '+recal(identity:bad-frac)',
    '+recal(identity:null-payload)').
  * Monotone iso order preserved: guaranteed by the interp in ingame_recal_apply.
  * <=300 LOC; ASCII-only; stdlib only (no numpy at module level).
  * Per-file test: test_ingame_serve_recal_seam.py.

USAGE (propose-against serve path -- never edit src/):
  from scripts.platformkit.ingame.ingame_serve_recal_seam import recalibrate_served
  # After blend_apply.apply_surface / serve_ingame produces p_home:
  result = recalibrate_served(p_home=0.63, frac_elapsed=0.74)
  # result['p_home'] is now recal-adjusted (or unchanged if no map)

RELOAD / TEST INJECTION:
  from scripts.platformkit.ingame.ingame_serve_recal_seam import reload_map
  reload_map(path="/tmp/my_test_nba_recal.json")  # force path override in tests
  reload_map(path=None)                            # reset to default / drop cache
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Lazy map cache (module-level, replaced by reload_map in tests)
# ---------------------------------------------------------------------------

_MAP_CACHE: Optional[Dict[str, Any]] = None  # sentinel: not yet loaded
_MAP_LOADED: bool = False                     # True once we have tried a load
_MAP_PATH_OVERRIDE: Optional[str] = None      # set by reload_map for tests


def _default_recal_path() -> str:
    """Return the default surfaces/nba_recal.json path relative to this file."""
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "surfaces",
        "nba_recal.json",
    )


def _load_map_from_path(path: str) -> Optional[Dict[str, Any]]:
    """Delegate to ingame_recal_apply.load_recal_map (pure read, never raises)."""
    from scripts.platformkit.ingame.ingame_recal_apply import load_recal_map
    return load_recal_map(path)


def _get_map() -> Optional[Dict[str, Any]]:
    """Return the cached recal map, loading it on first call."""
    global _MAP_CACHE, _MAP_LOADED
    if not _MAP_LOADED:
        path = _MAP_PATH_OVERRIDE if _MAP_PATH_OVERRIDE is not None else _default_recal_path()
        _MAP_CACHE = _load_map_from_path(path)
        _MAP_LOADED = True
    return _MAP_CACHE


# ---------------------------------------------------------------------------
# Public reload hook (for tests and operator overrides)
# ---------------------------------------------------------------------------

def reload_map(path: Optional[str] = None) -> None:
    """Force reload of the recal map from *path* (or default if None).

    Call with path=None to reset to the default surfaces/nba_recal.json on the
    next call to recalibrate_served.  Useful in tests to inject a synthetic map
    or to clear the cache after the producer writes a new surface.

    Never raises.
    """
    global _MAP_CACHE, _MAP_LOADED, _MAP_PATH_OVERRIDE
    _MAP_PATH_OVERRIDE = path  # None -> use default on next _get_map call
    if path is None:
        # Reset: next _get_map() will re-read the default
        _MAP_CACHE = None
        _MAP_LOADED = False
        return
    # Eagerly load so the caller can inspect the result
    _MAP_CACHE = _load_map_from_path(path)
    _MAP_LOADED = True


# ---------------------------------------------------------------------------
# Core shim
# ---------------------------------------------------------------------------

def recalibrate_served(
    p_home: float,
    frac_elapsed: Optional[float],
    *,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Apply the persisted isotonic recal map to p_home at frac_elapsed.

    Parameters
    ----------
    p_home : float
        Home-win probability from blend_apply / serve_ingame in [0, 1].
    frac_elapsed : float | None
        Fraction of regulation time elapsed (0.0 = start, 1.0 = end).
        None or non-finite triggers identity passthrough.
    extra : dict | None
        Optional extra keys to merge into the returned payload (pass-through
        from serve_ingame context).  Keys are copied AFTER recal -- caller
        must not include 'p_home' here (it will be overwritten).

    Returns
    -------
    dict with at minimum:
        p_home           : float in [0,1] -- recalibrated or original
        p_away           : float in [0,1] -- 1 - p_home
        recal_applied    : bool
        recal_bucket     : int | None
        recal_provenance : str -- audit string for the caller
    No dollar / roi / pnl key anywhere.

    Never raises.
    """
    try:
        # Guard: null payload
        if p_home is None:
            return _identity_result(
                p_home=0.5,
                provenance="+recal(identity:null-payload)",
                extra=extra,
            )

        # Guard: non-finite frac_elapsed
        _frac: Optional[float]
        try:
            _frac = float(frac_elapsed) if frac_elapsed is not None else None
        except (TypeError, ValueError):
            _frac = None

        if _frac is None or not _isfinite(_frac):
            return _identity_result(
                p_home=float(p_home) if p_home is not None else 0.5,
                provenance="+recal(identity:bad-frac)",
                extra=extra,
            )

        # Lazy-load the map
        recal_map = _get_map()

        if recal_map is None:
            return _identity_result(
                p_home=float(p_home),
                provenance="+recal(identity:no-map)",
                extra=extra,
            )

        # Build a minimal blend_result dict for apply_recal
        # remaining_frac = 1 - frac_elapsed (apply_recal derives frac_elapsed from it)
        remaining = max(0.0, min(1.0, 1.0 - _frac))
        blend_stub: Dict[str, Any] = {
            "p_home": float(p_home),
            "p_away": 1.0 - float(p_home),
            "remaining_frac": remaining,
        }
        if extra:
            # merge extra into stub so apply_recal passes them through
            for k, v in extra.items():
                if k not in ("p_home", "p_away", "remaining_frac"):
                    blend_stub[k] = v

        from scripts.platformkit.ingame.ingame_recal_apply import apply_recal
        out = apply_recal(blend_stub, recal_map)

        # Annotate provenance
        if out.get("recal_applied"):
            out["recal_provenance"] = "+recal(applied)"
        else:
            out["recal_provenance"] = "+recal(identity:no-map)"

        return out

    except Exception:  # noqa: BLE001 -- never raises
        # Absolute fallback: identity
        safe_p = 0.5
        try:
            safe_p = float(p_home) if p_home is not None else 0.5
        except (TypeError, ValueError):
            pass
        return _identity_result(safe_p, provenance="+recal(identity:no-map)", extra=extra)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _isfinite(x: float) -> bool:
    """True iff x is finite (avoids importing math at top level)."""
    import math
    return math.isfinite(x)


def _identity_result(
    p_home: float,
    provenance: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build an identity-passthrough result dict."""
    try:
        p = max(0.0, min(1.0, float(p_home)))
    except (TypeError, ValueError):
        p = 0.5
    out: Dict[str, Any] = {
        "p_home": p,
        "p_away": max(0.0, min(1.0, 1.0 - p)),
        "recal_applied": False,
        "recal_bucket": None,
        "recal_provenance": provenance,
    }
    if extra:
        for k, v in extra.items():
            if k not in out:
                out[k] = v
    return out


__all__ = [
    "recalibrate_served",
    "reload_map",
]
