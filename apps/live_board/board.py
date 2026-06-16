"""apps.live_board.board -- assemble the live multi-sport decision-support board.

For each normalized ESPN game (apps.live_board.espn_feed.fetch_games), resolve both
sides to our corpus ids (apps.live_board.name_maps.to_corpus_id) and:
  * BOTH sides in-corpus  -> OUR calibrated predict() (pregame) / predict_live() (live),
                             source 'model' / 'live-model'.
  * otherwise             -> devig the ESPN American moneylines to implied probs,
                             source 'market' / 'live-market' (still show the live score).
  * no model AND no usable market odds -> source 'unavailable' (score/clock only).

HONESTY (binding): this is DECISION SUPPORT, not a money machine. We show OUR calibrated
win-prob where in-corpus, devigged MARKET-implied otherwise, and badge the SOURCE per row.
We NEVER claim a $ edge / ROI / "beat the market". The note + footer make the source explicit.

Predictors are EXPENSIVE to build (soccer ~16s); _build_predictor already caches per sport,
and we build LAZILY -- only when a row actually resolves in-corpus.

Public API:
    build_board(sport, *, leagues=None) -> list[BoardRow dict]
INVARIANTS: never edit src/ or kernel/ or api/main.py; reuse predictor_jd; <=300 LOC; ASCII only.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from apps.live_board.espn_feed import fetch_games
from apps.live_board.name_maps import SUPPORTED_LEAGUES, to_corpus_id
from scripts.platformkit.predictor_jd import _build_predictor

# --------------------------------------------------------------------------
# Devig helpers (local, dependency-light). American moneyline -> implied prob,
# then normalize away the vig. 2-way for MLB/tennis ML, 3-way for soccer 1X2.
# --------------------------------------------------------------------------


def _american_to_decimal(odds: Any) -> Optional[float]:
    """American odds -> decimal. None/0/non-numeric -> None."""
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if o == 0.0:
        return None
    return 1.0 + o / 100.0 if o > 0 else 1.0 + 100.0 / abs(o)


def _implied(odds: Any) -> Optional[float]:
    """American odds -> raw (vigged) implied probability = 1/decimal."""
    dec = _american_to_decimal(odds)
    return (1.0 / dec) if dec and dec > 0.0 else None


def _devig(*american: Any) -> Optional[List[float]]:
    """Devig a set of American moneylines proportionally. Returns fair probs that
    sum to 1, or None if fewer than two usable prices are present."""
    imps = [_implied(o) for o in american]
    usable = [p for p in imps if p is not None]
    if len(usable) < 2:
        return None
    total = sum(usable)
    if total <= 0.0:
        return None
    # Keep each outcome's position; a missing price stays None (callers index by
    # position and tolerate None). Present prices normalize over the present total.
    return [None if p is None else p / total for p in imps]  # type: ignore[return-value]


# --------------------------------------------------------------------------
# Honest notes per source.
# --------------------------------------------------------------------------
_NOTES = {
    "model": "Our calibrated pregame win-prob (in-corpus). Markets efficient; no $ edge.",
    "live-model": ("Our calibrated in-game win-prob (in-corpus) from the live score. "
                   "A live book also sees the score; no $ edge."),
    "market": ("Out-of-corpus -> devigged MARKET-implied probability (book consensus), "
               "not our model. No $ edge claimed."),
    "live-market": ("Out-of-corpus -> devigged MARKET-implied probability from live odds "
                    "(book consensus), not our model. No $ edge claimed."),
    "unavailable": "No in-corpus model and no usable market odds -> live score/clock only.",
}


def _row(g: Dict[str, Any], **over: Any) -> Dict[str, Any]:
    """Build a BoardRow from a normalized feed game plus prediction overrides."""
    mkt = g.get("market") or {}
    row: Dict[str, Any] = {
        "sport": g.get("sport"),
        "league": g.get("league"),
        "state": g.get("state"),
        "start_time": g.get("start_time"),
        "home": g.get("home_name"),
        "away": g.get("away_name"),
        "home_score": g.get("home_score"),
        "away_score": g.get("away_score"),
        "clock_text": g.get("clock_text") or "",
        "win_home": None,
        "win_away": None,
        "draw": None,
        "total": mkt.get("total"),
        "market_odds": mkt.get("odds_text"),   # raw market line (always shown if present)
        "provider": mkt.get("provider"),
        "source": "unavailable",
        "market_implied": True,
        "note": _NOTES["unavailable"],
    }
    row.update(over)
    src = row.get("source", "unavailable")
    row["market_implied"] = src in ("market", "live-market", "unavailable")
    # If we have no probability but DO have a market line, say so honestly (not a dead end).
    if src == "unavailable" and row.get("market_odds"):
        row["note"] = "No in-corpus model; showing the raw market line (vig-included) + live score."
    else:
        row["note"] = _NOTES.get(src, _NOTES["unavailable"])
    return row


# --------------------------------------------------------------------------
# Per-sport model evaluation. Each returns (win_home, win_away, draw, total, source)
# or None to fall through to the market path. NEVER raises.
# --------------------------------------------------------------------------


def _safe(d: Any, key: str) -> Optional[float]:
    try:
        v = d.get(key)
        return None if v is None else float(v)
    except Exception:  # noqa: BLE001
        return None


def _model_mlb(pred: Any, g: Dict[str, Any], h: str, a: str):
    state = g.get("state")
    try:
        if state == "in" and g.get("period"):
            half = (g.get("half") or "top")
            half = half if half in ("top", "bottom") else "top"
            out = pred.predict_live(h, a, int(g["period"]), half,
                                    int(g.get("home_score") or 0),
                                    int(g.get("away_score") or 0))
            return (_safe(out, "p_home_win"), _safe(out, "p_away_win"), None, None,
                    "live-model")
        out = pred.predict(h, a)
        return (_safe(out, "p_home_win"), _safe(out, "p_away_win"), None,
                _safe(out, "expected_total"), "model")
    except Exception:  # noqa: BLE001
        return None


def _model_soccer(pred: Any, g: Dict[str, Any], h: str, a: str):
    state = g.get("state")
    try:
        if state == "in" and g.get("minute") is not None:
            out = pred.predict_live(h, a, float(g["minute"]),
                                    int(g.get("home_score") or 0),
                                    int(g.get("away_score") or 0))
            src = "live-model"
        else:
            out = pred.predict(h, a)
            src = "model"
        return (_safe(out, "p_home_win"), _safe(out, "p_away_win"),
                _safe(out, "p_draw"), None, src)
    except Exception:  # noqa: BLE001
        return None


def _model_tennis(pred: Any, g: Dict[str, Any], h: str, a: str):
    # Require both players resolve in the tennis corpus; else fall through.
    try:
        if pred._resolve(h) is None or pred._resolve(a) is None:  # noqa: SLF001
            return None
    except Exception:  # noqa: BLE001
        return None
    state = g.get("state")
    try:
        if state == "in":
            out = pred.predict_live(h, a, int(g.get("home_score") or 0),
                                    int(g.get("away_score") or 0))
            return (_safe(out, "p1_match_win"), _safe(out, "p2_match_win"), None, None,
                    "live-model")
        out = pred.predict(h, a)
        return (_safe(out, "p1_match_win"), _safe(out, "p2_match_win"), None, None,
                "model")
    except Exception:  # noqa: BLE001
        return None


_MODEL = {"mlb": _model_mlb, "soccer": _model_soccer, "tennis": _model_tennis}


def _market_row(g: Dict[str, Any]):
    """Devig the feed's American moneylines -> (win_home, win_away, draw, source)
    or None when no usable prices are present."""
    mkt = g.get("market") or {}
    ml_h, ml_a, draw = mkt.get("ml_home"), mkt.get("ml_away"), mkt.get("draw")
    live = g.get("state") == "in"
    src = "live-market" if live else "market"
    if draw is not None:  # 3-way (soccer)
        fair = _devig(ml_h, draw, ml_a)
        if fair is None:
            return None
        return (fair[0], fair[2], fair[1], src)
    fair = _devig(ml_h, ml_a)  # 2-way
    if fair is None:
        return None
    return (fair[0], fair[1], None, src)


# --------------------------------------------------------------------------
# Public entry point.
# --------------------------------------------------------------------------


def build_board(sport: str, *, leagues: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    """Assemble BoardRows for *sport*. Model where in-corpus, market-implied otherwise.

    NEVER raises: any per-game failure degrades that row (or skips it). Returns [] when
    the feed is empty/unavailable.
    """
    sport = (sport or "").lower()
    if leagues is None:
        leagues = SUPPORTED_LEAGUES.get(sport)

    try:
        games = fetch_games(sport, leagues=leagues)
    except Exception:  # noqa: BLE001
        games = []

    model_fn = _MODEL.get(sport)
    pred: Any = None
    pred_tried = False
    rows: List[Dict[str, Any]] = []

    for g in games or []:
        try:
            h_id = to_corpus_id(sport, g.get("home_name") or "")
            a_id = to_corpus_id(sport, g.get("away_name") or "")
        except Exception:  # noqa: BLE001
            h_id = a_id = None

        result = None
        if model_fn is not None and h_id and a_id:
            if not pred_tried:
                pred = _build_predictor(sport)  # cached; lazy build only when needed
                pred_tried = True
            if pred is not None:
                result = model_fn(pred, g, h_id, a_id)

        if result is not None:
            wh, wa, dr, tot, src = result
            mkt = g.get("market") or {}
            total = tot if tot is not None else mkt.get("total")
            rows.append(_row(g, win_home=wh, win_away=wa, draw=dr,
                             total=total, source=src))
            continue

        # Market-implied fallback (still shows live score/clock).
        m = _market_row(g)
        if m is not None:
            wh, wa, dr, src = m
            rows.append(_row(g, win_home=wh, win_away=wa, draw=dr, source=src))
        else:
            rows.append(_row(g))  # unavailable: score/clock only

    return rows


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse  # noqa: PLC0415
    import json  # noqa: PLC0415

    ap = argparse.ArgumentParser(description="Build the live decision-support board.")
    ap.add_argument("--sport", default="mlb")
    ap.add_argument("--leagues", default=None, help="comma-separated ESPN league slugs")
    a = ap.parse_args(argv)
    lg = a.leagues.split(",") if a.leagues else None
    t0 = time.time()
    rows = build_board(a.sport, leagues=lg)
    print(f"{a.sport}: {len(rows)} rows in {time.time() - t0:.1f}s")
    print(json.dumps(rows[:5], indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
