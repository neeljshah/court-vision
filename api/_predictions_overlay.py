"""_predictions_overlay.py — overlay model projections + EV onto consolidated props.

Reads predictions_cache_<date>.parquet (cols: player_name, stat, q10, q50, q90, sigma).
Adds per-prop: model_projection, model_interval, model_p_over, market_p_over,
edge_pct, rec_side, kelly_pct. Falls back to None when parquet absent.
"""
from __future__ import annotations

import logging
import math
import os
import unicodedata
from pathlib import Path
from typing import Optional

import time as _time

log = logging.getLogger(__name__)


def _norm_name(s) -> str:
    """Join-key normalizer. Default (CV_OVERLAY_DEACCENT unset/0) = byte-identical
    legacy `.strip().lower()`. When CV_OVERLAY_DEACCENT=1, also strip diacritics so
    the ASCII book spelling ('luka doncic') matches the accented parquet key
    ('luka dončić'). Sweep API_ROUTERS: the overlay join is the lone name path that
    forgot the _strip_accents bridge the rest of the pipeline applies, nulling the
    model overlay (projection/edge/rec/kelly) for accented stars on the live slate.
    """
    base = str(s or "").strip().lower()
    if os.environ.get("CV_OVERLAY_DEACCENT", "0") == "1":
        return unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    return base

_ROOT = Path(__file__).resolve().parent.parent
_CACHE_DIR = _ROOT / "data" / "cache"

# ── prediction lookup cache ───────────────────────────────────────────────────
# Keyed by date → (loaded_at, lookup_dict).  The parquet is ~100KB and changes
# only when predict_slate.py runs (typically once per day), so 60s TTL is safe.
_PRED_LOOKUP_CACHE: dict[str, tuple[float, dict]] = {}
_PRED_LOOKUP_TTL = 60.0

# Confidence floor from risk_controls.RiskConfig defaults.
_MIN_P_HIT = 0.55
_MIN_EDGE_PP = 4.0
_KELLY_CAP = 0.04   # 4% max per risk_controls.max_bet_pct


# ── math helpers ──────────────────────────────────────────────────────────────

def _american_to_implied(odds: int) -> float:
    """Single-side implied probability (includes vig)."""
    o = float(odds)
    return (100.0 / (o + 100.0)) if o >= 0 else (-o / (-o + 100.0))


def _devig_two_way(over_odds: Optional[int], under_odds: Optional[int]) -> Optional[float]:
    """Strip vig from two-way market. Returns no-vig p_over, or None if prices missing."""
    if over_odds is None or under_odds is None:
        return None
    po = _american_to_implied(over_odds)
    pu = _american_to_implied(under_odds)
    total = po + pu
    if total <= 0:
        return None
    return po / total


def _p_over_from_normal(projection: float, sigma: float, line: float) -> float:
    """P(outcome > line) using normal approximation with given sigma.

    Clamps to [0.01, 0.99] so the edge calc stays sane near extremes.
    """
    if sigma <= 0:
        return 1.0 if projection > line else 0.0
    z = (line - projection) / sigma
    # standard normal CDF via math.erfc
    p = 0.5 * math.erfc(z / math.sqrt(2))
    return max(0.01, min(0.99, p))


def _kelly(p: float, odds: int) -> float:
    """Full Kelly fraction. Returns 0 if EV is negative."""
    if odds >= 0:
        b = odds / 100.0
    else:
        b = 100.0 / abs(odds)
    q = 1.0 - p
    if b <= 0:
        return 0.0
    k = (b * p - q) / b
    return max(0.0, min(_KELLY_CAP, k))


def _best_two_way(prop: dict) -> tuple[Optional[int], Optional[int]]:
    """Best over + best under prices across all books for a prop."""
    best_o: Optional[int] = None
    best_u: Optional[int] = None
    for b in prop.get("books", []):
        o = b.get("over_price")
        u = b.get("under_price")
        if o is not None and (best_o is None or o > best_o):
            best_o = o
        if u is not None and (best_u is None or u > best_u):
            best_u = u
    return best_o, best_u


# ── prediction cache loader ───────────────────────────────────────────────────

def _load_predictions(date: str) -> dict[tuple[str, str], dict]:
    """Load parquet → lookup dict keyed by (player_name_lower, stat).

    Cached for 60s per date — the parquet read (pandas + disk I/O) is the
    dominant cost when predictions_cache exists and props overlap ~500 rows.
    Returns empty dict (graceful degradation) if file missing or unreadable.
    """
    cached = _PRED_LOOKUP_CACHE.get(date)
    if cached is not None and _time.time() - cached[0] < _PRED_LOOKUP_TTL:
        return cached[1]

    path = _CACHE_DIR / f"predictions_cache_{date}.parquet"
    if not path.exists():
        log.debug("predictions_cache_%s.parquet not found — overlay disabled", date)
        # Cache the empty result so we don't hammer the filesystem on every request.
        _PRED_LOOKUP_CACHE[date] = (_time.time(), {})
        return {}
    try:
        import pandas as pd
        df = pd.read_parquet(path)
    except Exception as exc:
        log.warning("Failed to read %s: %s", path.name, exc)
        _PRED_LOOKUP_CACHE[date] = (_time.time(), {})
        return {}

    required_cols = {"player_name", "stat", "q50"}
    missing = required_cols - set(df.columns)
    if missing:
        log.warning("predictions parquet missing columns %s — overlay disabled", missing)
        _PRED_LOOKUP_CACHE[date] = (_time.time(), {})
        return {}

    lookup: dict[tuple[str, str], dict] = {}
    for _, row in df.iterrows():
        try:
            key = (_norm_name(row["player_name"]), str(row["stat"]).strip().lower())
            q50 = float(row["q50"]) if row["q50"] == row["q50"] else None   # NaN guard
            q10 = float(row["q10"]) if "q10" in row and row["q10"] == row["q10"] else None
            q90 = float(row["q90"]) if "q90" in row and row["q90"] == row["q90"] else None
            sigma = float(row["sigma"]) if "sigma" in row and row["sigma"] == row["sigma"] else None
            team = str(row["team"]).strip().upper() if "team" in row and row["team"] == row["team"] else None
            lookup[key] = {"q50": q50, "q10": q10, "q90": q90, "sigma": sigma, "team": team}
        except Exception:
            continue
    log.debug("Loaded %d prediction rows for %s", len(lookup), date)
    _PRED_LOOKUP_CACHE[date] = (_time.time(), lookup)
    return lookup


# ── public API ────────────────────────────────────────────────────────────────

def overlay_predictions(date: str, props: list[dict]) -> list[dict]:
    """For each prop, attach model_projection, model_interval, edge_pct, rec_side, kelly_pct.

    Falls back to None overlays when predictions parquet missing or player absent.
    Never raises — any exception per-row is caught and results in None overlay.
    """
    preds = _load_predictions(date)

    enriched = []
    for prop in props:
        out = dict(prop)  # shallow copy — preserve all existing fields

        # Default: no overlay
        out.update({
            "model_projection": None,
            "model_interval": None,
            "model_p_over": None,
            "market_p_over": None,
            "edge_pct": None,
            "rec_side": None,
            "kelly_pct": None,
        })

        if not preds:
            enriched.append(out)
            continue

        try:
            player_key = _norm_name(prop.get("player", ""))
            stat_key = prop.get("stat", "").strip().lower()
            pred = preds.get((player_key, stat_key))
            if pred is None:
                enriched.append(out)
                continue

            q50: Optional[float] = pred.get("q50")
            q10: Optional[float] = pred.get("q10")
            q90: Optional[float] = pred.get("q90")
            sigma: Optional[float] = pred.get("sigma")
            line: Optional[float] = prop.get("line")

            if q50 is not None:
                out["model_projection"] = round(q50, 2)
            if q10 is not None and q90 is not None:
                out["model_interval"] = [round(q10, 2), round(q90, 2)]
            # Carry team abbreviation from parquet so _build_model_total can split
            # home/away pts without a separate player→team lookup.
            team = pred.get("team")
            if team:
                out["model_team"] = str(team).upper()

            # Model P(OVER) — requires projection + sigma + line
            if q50 is not None and sigma is not None and sigma > 0 and line is not None:
                p_over = _p_over_from_normal(q50, sigma, line)
                out["model_p_over"] = round(p_over, 4)

            # Market P(OVER) — devig best two-way
            best_o, best_u = _best_two_way(prop)
            market_p = _devig_two_way(best_o, best_u)
            if market_p is not None:
                out["market_p_over"] = round(market_p, 4)

            # Edge
            model_p = out.get("model_p_over")
            if model_p is not None and market_p is not None:
                edge = (model_p - market_p) * 100.0   # percentage points
                out["edge_pct"] = round(edge, 2)

                # Recommendation: only when edge is large enough AND p_hit threshold met
                edge_abs = abs(edge)
                if edge > 0 and model_p >= _MIN_P_HIT and edge_abs >= _MIN_EDGE_PP:
                    out["rec_side"] = "OVER"
                    if best_o is not None:
                        out["kelly_pct"] = round(_kelly(model_p, best_o) * 100, 2)
                elif edge < 0:
                    p_under = 1.0 - model_p
                    if p_under >= _MIN_P_HIT and edge_abs >= _MIN_EDGE_PP:
                        out["rec_side"] = "UNDER"
                        if best_u is not None:
                            out["kelly_pct"] = round(_kelly(p_under, best_u) * 100, 2)

        except Exception as exc:
            log.debug("overlay error for %s %s: %s", prop.get("player"), prop.get("stat"), exc)

        enriched.append(out)

    return enriched
