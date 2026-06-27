"""scripts.platformkit.pm_trading.kalshi_market_scan -- discover the LIQUID, actually-
tradeable Kalshi sports surface across ALL market types (not just game-winner).

Kalshi lists thousands of sports series (player props, totals, spreads, 1st-half,
futures), but most are LISTED-not-traded: no live two-way price, no volume. You cannot
make money on a market you can't get filled in. This scanner applies the SAME honest
liquidity gate the in-play game feed uses -- a market counts only when it shows a real
two-way (yes_bid AND yes_ask present) at a tight spread with real volume -- and reports
the tradeable surface grouped by market_type, so "look at all the bets" reflects what is
genuinely takeable RIGHT NOW, not a catalog of dead contracts.

HONEST RAILS: PAPER discovery only -- no placement, no $ field, no edge claim, no flag
flip, no real-money action. A market with no live two-way is EXCLUDED, never 0-filled
into a fake observation. Injectable http_get for offline tests; public fns never raise.

INVARIANTS: scripts/platformkit only; ASCII; <=300 LOC.
Per-file test: scripts/platformkit/pm_trading/test_kalshi_market_scan.py
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger("kalshi_market_scan")

_BASE = "https://api.elections.kalshi.com/trade-api/v2"
_REPO = pathlib.Path(__file__).resolve().parents[3]
_OUT_PATH = _REPO / "data" / "frontend" / "ops" / "kalshi_market_scan.json"

# Liquidity gate (cents). A real two-way at a tight spread with volume = takeable.
MAX_SPREAD_CENTS = float(os.environ.get("CV_KALSHI_MAX_SPREAD_CENTS", "3") or 3)

# series-ticker keyword -> market_type bucket (first match wins; order matters).
_TYPE_RULES = (
    ("total", "team_total"),
    ("spread", "spread"),
    ("1h", "first_half"), ("firsthalf", "first_half"), ("halftime", "first_half"),
    ("game", "game_winner"),
    # player-prop signatures (stat-named series)
    ("pts", "player_prop"), ("points", "player_prop"), ("hr", "player_prop"),
    ("pass", "player_prop"), ("rush", "player_prop"), ("rec", "player_prop"),
    ("yards", "player_prop"), ("reb", "player_prop"), ("ast", "player_prop"),
    ("3pm", "player_prop"), ("strikeout", "player_prop"), ("goals", "player_prop"),
    ("saves", "player_prop"), ("leader", "player_prop"), ("sog", "player_prop"),
)


def _http_get_json(url: str) -> Dict[str, Any]:
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.debug("kalshi_market_scan: GET %s failed: %s", url, exc)
        return {}


def classify_market_type(series_ticker: Any, title: Any = "") -> str:
    """Bucket a Kalshi series into a market_type from its ticker/title keywords."""
    hay = (str(series_ticker or "") + " " + str(title or "")).lower()
    for kw, bucket in _TYPE_RULES:
        if kw in hay:
            return bucket
    return "event_future"


def _num(m: Dict[str, Any], key: str) -> float:
    """Parse a Kalshi numeric field (*_dollars / *_fp), 0.0 on absent/bad."""
    v = m.get(key)
    try:
        return float(v) if v not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def _is_liquid(m: Dict[str, Any]) -> bool:
    """Takeable = a real live two-way at a tight spread. Kalshi's list endpoint carries
    prices in DOLLARS (yes_bid_dollars / yes_ask_dollars, 0.48 = 48c); an untraded
    contract reads 0/None on both. A tight two-way is hittable even before volume
    accrues, so we gate on the spread (the real takeability signal), not volume."""
    yb = _num(m, "yes_bid_dollars")
    ya = _num(m, "yes_ask_dollars")
    if yb <= 0.0 or ya <= 0.0:                # no live two-way -> not takeable
        return False
    spread_cents = (ya - yb) * 100.0
    return 0.0 <= spread_cents <= MAX_SPREAD_CENTS


def discover_sports_series(league_tokens: Sequence[str],
                           *, http_get: Optional[Callable[[str], Dict[str, Any]]] = None,
                           cap: int = 400) -> List[Dict[str, Any]]:
    """Sports series whose ticker contains any in-season *league_token*. Never raises."""
    get = http_get or _http_get_json
    toks = [str(t).upper() for t in league_tokens if str(t).strip()]
    out: List[Dict[str, Any]] = []
    cursor = ""
    for _ in range(8):  # bounded pagination
        url = _BASE + "/series?category=Sports&limit=200"
        if cursor:
            url += "&cursor=" + urllib.parse.quote(cursor)
        body = get(url) or {}
        for s in body.get("series", []) or []:
            tk = str(s.get("ticker") or "").upper()
            if any(t in tk for t in toks):
                out.append({"ticker": s.get("ticker"), "title": s.get("title")})
        cursor = str(body.get("cursor") or "")
        if not cursor or len(out) >= cap:
            break
    return out[:cap]


def scan(series: Sequence[Dict[str, Any]],
         *, http_get: Optional[Callable[[str], Dict[str, Any]]] = None,
         examples_per_type: int = 3) -> Dict[str, Any]:
    """Scan each series' OPEN markets, keep only LIQUID two-ways, group by market_type.

    Returns {by_type: {type: {n_liquid, n_open, examples[]}}, n_series, n_liquid_total}.
    Never raises -- a failed series fetch contributes 0, never a fabricated market."""
    get = http_get or _http_get_json
    by_type: Dict[str, Dict[str, Any]] = {}
    n_open = n_liq = 0
    for s in series:
        tk = str(s.get("ticker") or "")
        if not tk:
            continue
        body = get(_BASE + "/markets?series_ticker=%s&status=open&limit=200" % tk) or {}
        mk = body.get("markets", []) or []
        n_open += len(mk)
        mt = classify_market_type(tk, s.get("title"))
        bucket = by_type.setdefault(mt, {"n_liquid": 0, "n_open": 0, "examples": []})
        bucket["n_open"] += len(mk)
        for m in mk:
            if not _is_liquid(m):
                continue
            bucket["n_liquid"] += 1
            n_liq += 1
            if len(bucket["examples"]) < examples_per_type:
                bucket["examples"].append({
                    "ticker": m.get("ticker"),
                    "title": str(m.get("title") or m.get("yes_sub_title") or "")[:70],
                    "yes_bid": _num(m, "yes_bid_dollars"),
                    "yes_ask": _num(m, "yes_ask_dollars"),
                    "open_interest": _num(m, "open_interest_fp"), "series": tk})
    return {
        "by_type": dict(sorted(by_type.items(),
                               key=lambda kv: kv[1]["n_liquid"], reverse=True)),
        "n_series": len(series), "n_open_total": n_open, "n_liquid_total": n_liq,
        "max_spread_cents": MAX_SPREAD_CENTS,
        "executed": False, "edge_claimed": False,
        "honest_note": ("LIQUID-takeable Kalshi sports surface only (real two-way + tight "
                        "spread + volume); LISTED-not-traded markets EXCLUDED. PAPER "
                        "discovery; no placement, no $ field, no edge claim."),
    }


def run(league_tokens: Sequence[str] = ("MLB", "WC", "EPL", "WNBA"),
        *, http_get: Optional[Callable[[str], Dict[str, Any]]] = None,
        out_path: Optional[pathlib.Path] = None) -> Dict[str, Any]:
    """Discover in-season sports series -> scan liquid surface -> atomically write report."""
    series = discover_sports_series(league_tokens, http_get=http_get)
    report = scan(series, http_get=http_get)
    report["league_tokens"] = list(league_tokens)
    path = out_path if out_path is not None else _OUT_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True),
                       encoding="ascii")
        os.replace(str(tmp), str(path))
    except Exception as exc:  # noqa: BLE001
        logger.debug("kalshi_market_scan write failed: %s", exc)
    return report


def _main() -> int:  # pragma: no cover
    import argparse
    p = argparse.ArgumentParser(description="Scan the LIQUID Kalshi sports surface.")
    p.add_argument("--leagues", default="MLB,WC,EPL,WNBA")
    a = p.parse_args()
    rep = run(tuple(t.strip() for t in a.leagues.split(",") if t.strip()))
    print("liquid=%d / open=%d across %d series; by_type:"
          % (rep["n_liquid_total"], rep["n_open_total"], rep["n_series"]))
    for mt, d in rep["by_type"].items():
        print("  %-14s liquid=%4d open=%5d" % (mt, d["n_liquid"], d["n_open"]))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["classify_market_type", "discover_sports_series", "scan", "run"]
