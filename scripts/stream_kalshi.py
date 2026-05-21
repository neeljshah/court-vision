"""CLI: stream Kalshi orderbook deltas to JSONL."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# allow running from repo root without install
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from venues.kalshi_reader import KalshiReader


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stream Kalshi orderbook to JSONL.")
    p.add_argument(
        "--tickers",
        nargs="*",
        default=[],
        metavar="TICKER",
        help="Market tickers to subscribe to. Omit to auto-discover.",
    )
    p.add_argument(
        "--out",
        default="data/external/odds_lines/kalshi",
        metavar="DIR",
        help="Output directory for kalshi_stream.jsonl.",
    )
    p.add_argument(
        "--max-messages",
        type=int,
        default=500,
        metavar="N",
        help="Stop after N WS messages.",
    )
    return p.parse_args()


async def _stream(tickers: list[str], out_dir: Path, max_messages: int) -> None:
    reader = KalshiReader()
    resolved_tickers = tickers

    if not resolved_tickers:
        markets = reader.list_markets(limit=20)
        resolved_tickers = [m["ticker"] for m in markets[:5] if "ticker" in m]
        if not resolved_tickers:
            print("No tickers found from list_markets. Exiting.", file=sys.stderr)
            return

    # Wrap ws loop so we can emit progress lines
    from venues.kalshi_reader import BASE_URL, WS_URL, VENUE  # noqa: PLC0415
    import aiohttp  # noqa: PLC0415
    from datetime import datetime, timezone  # noqa: PLC0415

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "kalshi_stream.jsonl"

    subscribe_msg = json.dumps({
        "id": 1,
        "cmd": "subscribe",
        "params": {
            "channels": ["orderbook_delta"],
            "market_tickers": resolved_tickers,
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
                            ticker_val = record.get("market_ticker", resolved_tickers[0] if resolved_tickers else "")
                            record["venue"] = VENUE
                            record["received_at"] = datetime.now(timezone.utc).isoformat()
                            fh.write(json.dumps(record) + "\n")
                            count += 1
                            print(f"venue=kalshi ticker={ticker_val} msg={count}/{max_messages}")
                            if count >= max_messages:
                                break
                        elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                            break
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # noqa: BLE001
        print(f"stream_kalshi: WS error — {exc}", file=sys.stderr)

    print(f"done — {count} messages logged to {out_path}")


def main() -> None:
    args = _parse_args()
    asyncio.run(_stream(args.tickers, Path(args.out), args.max_messages))


if __name__ == "__main__":
    main()
