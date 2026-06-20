"""scripts.platformkit.ingame.market_set -- build a per-game live market set.

Pure function: given a reprice() output dict (repricer_router.reprice), assembles
a flat, self-describing per-game market set that the snapshot writer and the /api/live
endpoint serve.

HONEST + SAFE:
  * No dollar edge anywhere. edge_claimed is always False.
  * MAE wins from shrinking toward the current score are MEDIAN-vs-MEAN ARTIFACTS;
    we report variance (which must SHRINK as fraction_elapsed rises), not MAE.
  * An unavailable reprice -> a clean unavailable market set (no fabricated numbers).
  * 'basis' and '_honest_note' pass through from the repricer so the caller can see
    exactly what the number rests on.

INVARIANTS: pure (no I/O, no network, no side effects); <=300 LOC; ASCII-only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ---- constants ---------------------------------------------------------------

EDGE_CLAIMED = False  # binding invariant -- never set to True

_HONEST_NOTE = (
    "Live market set assembled from a freshness-blended in-game reprice. "
    "Variance shrinks as the game progresses (Q1 wide -> Q4 tight); "
    "this is a CALIBRATION measure, not a dollar edge. "
    "Whether the repriced number beats the close is a gate question "
    "(fit_w_surface / eval_gate), not asserted here."
)


# ---- helpers -----------------------------------------------------------------

def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def _clean_markets(raw: Any) -> List[Dict[str, Any]]:
    """Validate + copy per-market rows; skip malformed rows silently."""
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        if "market" not in row:
            continue
        if "prob" in row:
            try:
                out.append({"market": str(row["market"]),
                            "prob": _clamp01(float(row["prob"]))})
            except (TypeError, ValueError):
                pass
        elif "value" in row:
            try:
                out.append({"market": str(row["market"]),
                            "value": float(row["value"])})
            except (TypeError, ValueError):
                pass
    return out


def _clean_probs(raw: Any) -> Dict[str, float]:
    """Copy the win-prob block; empty dict if unavailable."""
    if not isinstance(raw, dict) or not raw:
        return {}
    out: Dict[str, float] = {}
    for k in ("p_home", "p_away", "w", "p_live"):
        v = raw.get(k)
        if v is not None:
            try:
                out[k] = _clamp01(float(v)) if k in ("p_home", "p_away", "p_live") \
                    else _clamp01(float(v))
            except (TypeError, ValueError):
                pass
    return out


# ---- public API --------------------------------------------------------------

def build(game_id: str, sport: str, reprice_output: Dict[str, Any], *,
          as_of: Optional[str] = None,
          game_meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build the per-game live market set from a reprice() output dict.

    Parameters
    ----------
    game_id : str
        Stable game id within the sport.
    sport : str
        Normalized platform sport id (e.g. "nba").  If reprice_output carries a
        'sport' field that differs from this argument, the reprice_output value
        wins (it was alias-resolved by the repricer).
    reprice_output : dict
        The dict returned by repricer_router.reprice().
    as_of : str, optional
        ISO timestamp string; defaults to UTC now.
    game_meta : dict, optional
        Optional extra keys to merge into the output (e.g. home_team/away_team,
        tipoff).  Keys must not collide with first-class fields; extras block wins.

    Returns
    -------
    dict -- the live market set (see module docstring for the canonical shape).
    Guaranteed keys: game_id, sport, status, available, basis, as_of, edge_claimed,
    probs, markets, variance, remaining_frac, _honest_note.
    Never raises.
    """
    try:
        return _build_inner(game_id, sport, reprice_output,
                            as_of=as_of, game_meta=game_meta)
    except Exception:  # pragma: no cover - defensive; pure fn must never raise
        return _unavailable(game_id, str(sport).lower(), "build error")


def _build_inner(game_id: str, sport: str, rp: Dict[str, Any],
                 as_of: Optional[str], game_meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    gid = str(game_id)
    ts = as_of if isinstance(as_of, str) and as_of else _utc_iso()
    available = bool(rp.get("available", False))
    rep_sport = str(rp.get("sport") or sport).lower()
    basis = str(rp.get("basis", "unavailable"))

    if not available:
        out = _unavailable(gid, rep_sport, str(rp.get("reason", "unavailable")))
        out["as_of"] = ts
        return out

    probs = _clean_probs(rp.get("probs"))
    markets = _clean_markets(rp.get("markets"))
    var = rp.get("variance")
    rem = rp.get("remaining_frac")

    variance: Optional[float] = None
    if var is not None:
        try:
            variance = max(0.0, float(var))
        except (TypeError, ValueError):
            pass

    remaining_frac: Optional[float] = None
    if rem is not None:
        try:
            remaining_frac = _clamp01(float(rem))
        except (TypeError, ValueError):
            pass

    out: Dict[str, Any] = {
        "game_id": gid,
        "sport": rep_sport,
        "status": "live",
        "available": True,
        "basis": basis,
        "as_of": ts,
        "edge_claimed": EDGE_CLAIMED,
        "probs": probs,
        "markets": markets,
        "variance": variance,
        "remaining_frac": remaining_frac,
        "_honest_note": str(rp.get("_honest_note") or _HONEST_NOTE),
    }

    # Merge optional game metadata (home_team, away_team, tipoff, etc.).
    if isinstance(game_meta, dict):
        _RESERVED = frozenset(out.keys())
        for k, v in game_meta.items():
            if k not in _RESERVED:
                out[k] = v

    return out


def _unavailable(game_id: str, sport: str, reason: str) -> Dict[str, Any]:
    """Clean unavailable sentinel -- no fabricated numbers."""
    return {
        "game_id": game_id,
        "sport": sport,
        "status": "unavailable",
        "available": False,
        "basis": "unavailable",
        "as_of": _utc_iso(),
        "edge_claimed": EDGE_CLAIMED,
        "probs": {},
        "markets": [],
        "variance": None,
        "remaining_frac": None,
        "reason": reason,
        "_honest_note": _HONEST_NOTE,
    }
