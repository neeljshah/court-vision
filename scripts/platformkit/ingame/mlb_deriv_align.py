"""scripts.platformkit.ingame.mlb_deriv_align -- PURE alignment helpers for the MLB
in-play totals/run-line derivative channel (inplay_derivative_mlb.py).

Answers ONE question per Kalshi total/spread tick: does the MLB negbinom repricer
surface (domains.mlb.repricer.MLBRepricer.reprice -> negbinom_engine.markets_from_
matrix_nb) cover this tick's LINE, and if so what is the model's fair prob for the
SAME proposition the tick's YES side quotes?

COVERAGE (binding, no extrapolation):
  * total: the repricer only computes over/under at the FIXED grid
    domains.mlb.repricer._TOTAL_LINES (6.5/7.5/8.5/9.5/10.5). A tick line inside
    [6.5, 10.5] is served by LINEAR INTERPOLATION between the two bracketing grid
    lines (or an exact grid hit needs no interpolation); a line outside that range
    is an HONEST SKIP (reason="no_coverage") -- never extrapolated.
  * spread (run-line): the repricer computes exactly ONE line, home -1.5 / away
    +1.5 (rl_home_minus15 / rl_away_plus15). A tick whose |line| != 1.5 is an
    HONEST SKIP (reason="no_coverage") -- the repricer has no other run-line to
    compare against. This is a real, documented coverage gap (see this module's
    caller's final report), not a bug.

SIDE CONVENTION (binding, documented so a reviewer can audit alignment):
  * total: Kalshi's YES side is assumed OVER unless the tick's `side` label
    contains the substring "under" (best-effort parse of yes_sub_title/title,
    see inplay_kalshi._side_label). model_prob is flipped to match whichever
    proposition the tick's own YES side actually quotes, so market_prob (the
    tick's raw YES prob) and model_prob are ALWAYS aligned to the SAME event.
  * spread: the tick's `side` label is matched against the resolved home/away
    team display name (case-insensitive substring, either direction, mirrors
    inplay_capture_loop._team_in_legs). No match -> HONEST SKIP
    (reason="no_side_match"), never guessed.

Never raises; PURE (no file/network IO); <=300 LOC.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from domains.mlb.repricer import _TOTAL_LINES as _GRID  # reuse, never re-declare

_SPREAD_LINE = 1.5  # the ONLY run-line domains.mlb.repricer computes (rl_home_minus15)
_GRID_SORTED: Tuple[float, ...] = tuple(sorted(_GRID))

# MLB Kalshi ticker team-code blob: "...-25JUL18NYYBOS[-...]" -> ("NYY","BOS"). Only
# the well-known 3+3 shape is handled; anything else -> None (never guessed). Mirrors
# kalshi_series_spec._TICKER_DATE_RE's date parse, extended to the team-code tail.
_TICKER_TEAMS_RE = re.compile(r"-\d{2}[A-Z]{3}\d{2}([A-Z]{6})")


def ticker_team_codes(ref: Any) -> Optional[Tuple[str, str]]:
    """The two 3-letter team codes embedded in an MLB Kalshi ticker, or None.

    Best-effort, MLB-specific (see module docstring). Never raises."""
    try:
        m = _TICKER_TEAMS_RE.search(str(ref or "").upper())
        if not m:
            return None
        blob = m.group(1)
        return blob[:3], blob[3:]
    except (TypeError, ValueError):
        return None


def _fmt(line: float) -> str:
    return f"{line:g}"


def interp_over_prob(surface: Dict[str, Any], line: float) -> Optional[float]:
    """Fair P(total > line) from *surface* (markets_from_matrix_nb's over_X keys).

    Exact grid hit -> that key directly. Otherwise LINEARLY INTERPOLATES between the
    two bracketing grid lines. line outside [min(grid), max(grid)] -> None (honest,
    never extrapolated). Never raises."""
    try:
        ln = float(line)
    except (TypeError, ValueError):
        return None
    if ln < _GRID_SORTED[0] or ln > _GRID_SORTED[-1]:
        return None
    for i in range(len(_GRID_SORTED) - 1):
        lo, hi = _GRID_SORTED[i], _GRID_SORTED[i + 1]
        if lo <= ln <= hi:
            if ln == lo:
                return _as_float(surface.get(f"over_{_fmt(lo)}"))
            if ln == hi:
                return _as_float(surface.get(f"over_{_fmt(hi)}"))
            po_lo, po_hi = surface.get(f"over_{_fmt(lo)}"), surface.get(f"over_{_fmt(hi)}")
            if po_lo is None or po_hi is None:
                return None
            w = (ln - lo) / (hi - lo)
            return float(po_lo) * (1.0 - w) + float(po_hi) * w
    return None  # unreachable given the range guard above; defensive


def _as_float(v: Any) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _name_match(label: str, team: str) -> bool:
    lab, t = str(label or "").strip().lower(), str(team or "").strip().lower()
    if not lab or not t:
        return False
    return lab in t or t in lab


def align_tick(tick: Dict[str, Any], surface: Dict[str, Any],
               home_name: str, away_name: str) -> Optional[Dict[str, Any]]:
    """Align ONE liquid Kalshi total/spread tick to the repricer surface.

    Returns {"market_type","line","logical_side","market_prob","model_prob"} or
    None (honest skip -- no coverage / no side match / bad tick). "logical_side" is
    "over"|"under" for a total tick, "home_favorite"|"away_dog" for a spread tick;
    it always names the SAME proposition market_prob and model_prob are both about.
    Never raises."""
    try:
        mt = str(tick.get("market_type") or "")
        line = tick.get("line")
        market_prob = tick.get("prob")
        if line is None or market_prob is None:
            return None
        if mt == "total":
            model_over = interp_over_prob(surface, float(line))
            if model_over is None:
                return None
            side_label = str(tick.get("side") or "").lower()
            if "under" in side_label:
                return {"market_type": "total", "line": float(line),
                        "logical_side": "under", "market_prob": float(market_prob),
                        "model_prob": 1.0 - model_over}
            return {"market_type": "total", "line": float(line),
                    "logical_side": "over", "market_prob": float(market_prob),
                    "model_prob": model_over}
        if mt == "spread":
            if abs(abs(float(line)) - _SPREAD_LINE) > 1e-6:
                return None
            rl_home = surface.get("rl_home_minus15")
            rl_away = surface.get("rl_away_plus15")
            if rl_home is None or rl_away is None:
                return None
            side_label = str(tick.get("side") or "")
            if _name_match(side_label, home_name):
                return {"market_type": "spread", "line": _SPREAD_LINE,
                        "logical_side": "home_favorite", "market_prob": float(market_prob),
                        "model_prob": float(rl_home)}
            if _name_match(side_label, away_name):
                return {"market_type": "spread", "line": _SPREAD_LINE,
                        "logical_side": "away_dog", "market_prob": float(market_prob),
                        "model_prob": float(rl_away)}
            return None
        return None
    except (TypeError, ValueError):
        return None


def market_key(market_type: str, line: float, logical_side: str) -> str:
    """Ledger `market` string: e.g. "total_8.5_over" / "spread_1.5_home_favorite"."""
    return f"{market_type}_{_fmt(line)}_{logical_side}"


def ledger_side(logical_side: str) -> str:
    """Map logical_side -> the ledger's required {"home","away"} schema field.

    Convention (documented, never fed through the moneyline grader): "over" /
    "home_favorite" -> "home"; "under" / "away_dog" -> "away". This is a
    BOOKKEEPING convention for this channel only -- settlement in
    inplay_derivative_mlb.py reads `market` (not this literal team-side meaning)
    to compute the real total/run-line outcome."""
    return "home" if logical_side in ("over", "home_favorite") else "away"


__all__ = ["ticker_team_codes", "interp_over_prob", "align_tick", "market_key",
           "ledger_side"]
