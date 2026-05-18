"""Polymarket CLOB adapter (Polygon chain)."""
from __future__ import annotations
import requests
from .base import Book, Level

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"


class Polymarket:
    name = "polymarket"
    chain = "polygon"

    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout
        self._token_cache: dict[str, str] = {}

    def find_market(self, team_a: str, team_b: str) -> str | None:
        try:
            r = requests.get(
                f"{GAMMA}/markets",
                params={"q": team_a, "category": "sports", "active": "true", "limit": 20},
                timeout=self.timeout,
            )
            r.raise_for_status()
            markets = r.json()
            if isinstance(markets, dict):
                markets = markets.get("markets", [])
            ta, tb = team_a.lower(), team_b.lower()
            for m in markets:
                q = (m.get("question") or "").lower()
                if ta in q and tb in q:
                    for outcome in m.get("tokens") or []:
                        if ta in (outcome.get("outcome") or "").lower():
                            self._token_cache[m["id"]] = outcome["token_id"]
                            return m["id"]
        except Exception:
            pass
        return None

    def fetch_book(self, market_id: str, side: str = "YES") -> Book:
        book = Book(venue=self.name, market_id=market_id)
        token_id = self._token_cache.get(market_id)
        if not token_id:
            book.error = "token_id not resolved — call find_market first"
            return book
        try:
            r = requests.get(f"{CLOB}/book", params={"token_id": token_id}, timeout=self.timeout)
            r.raise_for_status()
            raw = r.json().get("asks") or []
            levels = sorted(
                (Level(price=float(a["price"]), size=float(a["size"])) for a in raw),
                key=lambda l: l.price,
            )
            book.asks = levels
        except Exception as e:
            book.error = str(e)
        return book

    def submit_order(self, market_id: str, size_usd: float, limit_price: float) -> dict:
        # NOTE: real impl signs an EIP-712 CLOB order via chain.PolygonWallet.
        # Stubbed read-only — router is an analysis tool, not a live trader.
        return {
            "venue": self.name,
            "chain": self.chain,
            "market_id": market_id,
            "size_usd": size_usd,
            "limit_price": limit_price,
            "status": "DRY_RUN",
            "sig": None,
        }
