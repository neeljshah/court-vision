"""SX Bet RFQ/maker-order adapter (SX Chain)."""
from __future__ import annotations
import requests
from .base import Book, Level

SX = "https://api.sx.bet"
_PCT_DENOM = 10 ** 20


def _pct_to_prob(pct: str) -> float:
    v = int(pct)
    return v / (v + _PCT_DENOM)


class SXBet:
    name = "sx_bet"
    chain = "sx"

    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout
        self._market_cache: dict[str, dict] = {}

    def find_market(self, team_a: str, team_b: str) -> str | None:
        try:
            r = requests.get(
                f"{SX}/markets/active",
                params={"sportId": 2, "pageSize": 100},
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
            markets = data.get("data", {}).get("markets") or data.get("data") or []
            ta, tb = team_a.lower(), team_b.lower()
            for m in markets:
                blob = " ".join([
                    m.get("teamOneName") or "",
                    m.get("teamTwoName") or "",
                    m.get("label") or "",
                ]).lower()
                if ta in blob and tb in blob:
                    h = m.get("marketHash")
                    self._market_cache[h] = m
                    return h
        except Exception:
            pass
        return None

    def fetch_book(self, market_id: str, side: str = "YES") -> Book:
        book = Book(venue=self.name, market_id=market_id)
        try:
            r = requests.get(
                f"{SX}/orders", params={"marketHashes": market_id}, timeout=self.timeout,
            )
            r.raise_for_status()
            orders = r.json().get("data") or []
            laker_orders = [o for o in orders if str(o.get("outcomeIndex", "")) == "0"]
            levels = sorted(
                (
                    Level(
                        price=_pct_to_prob(o["percentageOdds"]),
                        size=float(o.get("fillableAmount", 0)) / 1e6,  # USDC 6-dec
                    )
                    for o in laker_orders
                ),
                key=lambda l: l.price,
            )
            book.asks = levels
        except Exception as e:
            book.error = str(e)
        return book

    def submit_order(self, market_id: str, size_usd: float, limit_price: float) -> dict:
        # NOTE: real impl signs an SX-chain order (EIP-712) via chain.SXWallet.
        return {
            "venue": self.name,
            "chain": self.chain,
            "market_hash": market_id,
            "size_usd": size_usd,
            "limit_price": limit_price,
            "status": "DRY_RUN",
            "sig": None,
        }
