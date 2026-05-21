"""Read-only Polymarket CLOB API client — REST + WebSocket."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
import requests

BASE_URL = "https://clob.polymarket.com"
WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/"
VENUE = "polymarket"


class PolymarketReader:
    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()

    def list_markets(self, next_cursor: str = "") -> list[dict]:
        """Return list of market dicts from /markets, optionally paginated."""
        url = f"{BASE_URL}/markets"
        params: dict = {}
        if next_cursor:
            params["next_cursor"] = next_cursor
        resp = self._session.get(url, params=params)
        resp.raise_for_status()
        return resp.json().get("data", [])

    def get_orderbook(self, token_id: str) -> dict:
        """Return the full order book dict for a given token_id."""
        resp = self._session.get(f"{BASE_URL}/book", params={"token_id": token_id})
        resp.raise_for_status()
        return resp.json()

    def stream_book(
        self,
        token_ids: list[str],
        out_dir: Path,
        max_messages: int = 1000,
    ) -> None:
        """Subscribe to WS book channel and write JSONL to out_dir."""
        asyncio.run(self._stream_async(token_ids, out_dir, max_messages))

    async def _stream_async(
        self,
        token_ids: list[str],
        out_dir: Path,
        max_messages: int,
    ) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "polymarket_stream.jsonl"
        subscribe_msg = json.dumps(
            {"type": "subscribe", "channel": "book", "assets_ids": token_ids}
        )
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(WS_URL) as ws:
                    await ws.send_str(subscribe_msg)
                    count = 0
                    with out_path.open("a", encoding="utf-8") as fh:
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    data = json.loads(msg.data)
                                except json.JSONDecodeError:
                                    continue
                                data["venue"] = VENUE
                                data["received_at"] = datetime.now(
                                    timezone.utc
                                ).isoformat()
                                fh.write(json.dumps(data) + "\n")
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
        except Exception as exc:
            print(f"stream_book error: {exc}", file=sys.stderr)
