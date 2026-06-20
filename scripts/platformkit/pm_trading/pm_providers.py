"""pm_providers.py -- PMProvider base + Kalshi/Polymarket adapters.

Split from live_feed.py (LOC discipline; live_feed.py was 475 lines).
Exports: PMProvider, KalshiPMProvider, PolymarketPMProvider,
         _default_pm_providers, _odds_event_to_pm_market,
         _single_binary_to_pm_market.

live_feed.py imports everything it needs from here.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional, Sequence

logger = logging.getLogger(__name__)

_DEFAULT_SPORTS = ("nba", "mlb", "soccer", "soccer_intl", "tennis")


def _odds_event_to_pm_market(ev: Any, sport: str,
                              venue: str = "") -> Optional[dict]:
    """OddsEvent -> PMProvider row (binary_title=None for two-leg), or None.

    venue is stamped onto the row so downstream coercion (_coerce_row in
    pm_paper_tick_runner) can validate it without separate provider bookkeeping.
    """
    try:
        prices = ev.prices.get(ev.source, {})
        dec_home = prices.get("home")
        if dec_home is None or float(dec_home) <= 1.0:
            return None
        pm_prob = round(1.0 / float(dec_home), 6)
        if not (0.0 < pm_prob < 1.0):
            return None
        row: dict = {"market_id": str(ev.event_id), "sport": sport,
                     "home": str(ev.home), "away": str(ev.away),
                     "pm_prob": pm_prob, "binary_title": None}
        if venue:
            row["venue"] = str(venue).strip().lower()
        return row
    except Exception:  # noqa: BLE001
        return None


def _single_binary_to_pm_market(
    market_id: str, sport: str, title: str, yes_prob: float,
    venue: str = "",
) -> Optional[dict]:
    """Single 'Will TEAM win?' YES contract -> partial row; home/away/pm_prob
    resolved later in active_pairs. None when yes_prob outside (0,1).

    venue is stamped so pm_paper_tick_runner._coerce_row can validate it.
    """
    if not (0.0 < yes_prob < 1.0):
        return None
    row: dict = {"market_id": str(market_id), "sport": str(sport),
                 "home": None, "away": None, "pm_prob": None,
                 "binary_title": str(title), "binary_yes_prob": float(yes_prob)}
    if venue:
        row["venue"] = str(venue).strip().lower()
    return row


def _fetch_pm_markets(provider_cls_path: str, sports: Sequence[str],
                      http_get: Any, venue: str = "") -> List[dict]:
    """Shared fetch loop for Kalshi and Polymarket PM provider adapters.

    Imports *provider_cls_path* lazily (e.g.
    "scripts.platformkit.odds_provider.kalshi:KalshiProvider"), calls
    provider.fetch(sport) for each sport in *sports*, converts each OddsEvent
    to a PM market row.  Degrades to [] on any error (never raises, never
    fabricates).

    venue is forwarded to _odds_event_to_pm_market so every row carries the
    source name ("kalshi" or "polymarket"), enabling _coerce_row downstream to
    validate venue without extra bookkeeping.
    """
    mod_path, cls_name = provider_cls_path.rsplit(":", 1)
    try:
        import importlib
        mod = importlib.import_module(mod_path)
        cls = getattr(mod, cls_name)
        from scripts.platformkit.odds_provider.http_cache import http_get_json
        from scripts.platformkit.odds_provider.base import is_unavailable
    except Exception as exc:
        logger.debug("%s import failed: %s", cls_name, exc)
        return []
    provider = cls(http_get=(http_get or http_get_json), use_cache=False)
    out: List[dict] = []
    for sport in sports:
        try:
            result = provider.fetch(sport)
            if is_unavailable(result):
                continue
            for ev in result:
                row = _odds_event_to_pm_market(ev, sport, venue=venue)
                if row is not None:
                    out.append(row)
        except Exception as exc:  # noqa: BLE001 -- degrade per-sport
            logger.debug("%s sport=%s error: %s", cls_name, sport, exc)
    return out


class PMProvider:
    """Source of live PM market prices.  fetch_markets() -> list of dicts.
    Each dict: market_id, sport, home, away, pm_prob float[0,1].
    Returns [] when no live markets exist.  Subclass or inject in tests."""
    def fetch_markets(self) -> List[dict]:
        return []


class KalshiPMProvider(PMProvider):
    """Keyless Kalshi public-market feed adapted to PMProvider shape.

    No auth required.  Degrades to [] on any failure.  *http_get* injectable
    for offline tests.
    """

    def __init__(self, sports: Sequence[str] = _DEFAULT_SPORTS,
                 http_get: Any = None) -> None:
        self._sports = list(sports)
        self._http_get = http_get

    def fetch_markets(self) -> List[dict]:
        return _fetch_pm_markets(
            "scripts.platformkit.odds_provider.kalshi:KalshiProvider",
            self._sports, self._http_get, venue="kalshi")


class PolymarketPMProvider(PMProvider):
    """Best-effort Polymarket Gamma feed adapted to PMProvider shape.

    No auth required.  Degrades to [] on any failure.  *http_get* injectable
    for offline tests.

    Emits BOTH two-leg rows (via _odds_event_to_pm_market) AND single-sided
    YES/NO binary rows (via _single_binary_to_pm_market).  The binary rows carry
    home=None/away=None/pm_prob=None and binary_title+binary_yes_prob; they are
    routed through Path-4 (title matching) in active_pairs().  Path-4 gates
    futures/championship/series contracts so a season-long YES price is never
    compared to a single-game model prob.
    """

    def __init__(self, sports: Sequence[str] = _DEFAULT_SPORTS,
                 http_get: Any = None) -> None:
        self._sports = list(sports)
        self._http_get = http_get

    def fetch_markets(self) -> List[dict]:
        try:
            import importlib
            mod = importlib.import_module(
                "scripts.platformkit.odds_provider.polymarket")
            PolymarketProvider = getattr(mod, "PolymarketProvider")
            from scripts.platformkit.odds_provider.http_cache import http_get_json
            from scripts.platformkit.odds_provider.base import is_unavailable
        except Exception as exc:
            logger.debug("PolymarketPMProvider import failed: %s", exc)
            return []
        http = self._http_get or http_get_json
        provider = PolymarketProvider(http_get=http, use_cache=False)
        out: List[dict] = []
        for sport in self._sports:
            try:
                result = provider.fetch_with_binaries(sport)
                if is_unavailable(result):
                    continue
                events, binaries = result
                for ev in events:
                    row = _odds_event_to_pm_market(ev, sport, venue="polymarket")
                    if row is not None:
                        out.append(row)
                # YES/NO binary rows already in PM-row shape from parse_market_binary;
                # stamp venue="polymarket" if not already set.
                for b in binaries:
                    if not b.get("venue"):
                        b = dict(b)
                        b["venue"] = "polymarket"
                    out.append(b)
            except Exception as exc:  # noqa: BLE001 -- degrade per-sport
                logger.debug("PolymarketPMProvider sport=%s error: %s", sport, exc)
        return out


def _default_pm_providers() -> List[PMProvider]:
    """Return the live Kalshi + Polymarket PM providers (keyless, no auth).

    Both are real REST feeds.  On NBA offseason / no live games they return []
    (honest empty).  No fabricated rows; no $ fields.
    """
    return [KalshiPMProvider(), PolymarketPMProvider()]


__all__ = [
    "PMProvider", "KalshiPMProvider", "PolymarketPMProvider",
    "_default_pm_providers", "_odds_event_to_pm_market",
    "_single_binary_to_pm_market",
]
