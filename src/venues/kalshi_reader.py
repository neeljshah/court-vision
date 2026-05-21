"""Read-only Kalshi API client — REST + WebSocket."""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
import requests

BASE_URL = "https://trading-api.kalshi.com/trade-api/v2"
WS_URL = "wss://trading-api.kalshi.com/trade-api/ws/v2"
VENUE = "kalshi"


class KalshiReader:
    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()

    def list_markets(self, limit: int = 100, status: str = "open") -> list[dict]:
        """Return open markets from the Kalshi REST API."""
        url = f"{BASE_URL}/markets"
        resp = self._session.get(url, params={"limit": limit, "status": status})
        resp.raise_for_status()
        return resp.json().get("markets", [])

    def get_orderbook(self, ticker: str) -> dict:
        """Return the orderbook for a single market ticker."""
        url = f"{BASE_URL}/markets/{ticker}/orderbook"
        resp = self._session.get(url)
        resp.raise_for_status()
        data = resp.json()
        return data.get("orderbook", data)

    async def stream_orderbook(
        self,
        tickers: list[str],
        out_dir: Path,
        max_messages: int = 1000,
    ) -> None:
        """Connect to Kalshi WS, write orderbook deltas as JSONL to out_dir."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "kalshi_stream.jsonl"

        subscribe_msg = json.dumps({
            "id": 1,
            "cmd": "subscribe",
            "params": {
                "channels": ["orderbook_delta"],
                "market_tickers": tickers,
            },
        })

        count = 0
        try:
            async with aiohttp.ClientSession() as ws_session:
                async with ws_session.ws_connect(WS_URL) as ws:
                    await ws.send_str(subscribe_msg)
                    with out_path.open("a", encoding="utf-8") as fh:
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                record = json.loads(msg.data)
                                record["venue"] = VENUE
                                record["received_at"] = (
                                    datetime.now(timezone.utc).isoformat()
                                )
                                fh.write(json.dumps(record) + "\n")
                                count += 1
                                if count >= max_messages:
                                    break
                            elif msg.type in (
                                aiohttp.WSMsgType.ERROR,
                                aiohttp.WSMsgType.CLOSED,
                            ):
                                break
        except KeyboardInterrupt:
            pass
        except Exception as exc:  # noqa: BLE001
            print(f"kalshi_reader: WS error — {exc}", file=sys.stderr)
