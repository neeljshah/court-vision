"""CLI: stream Polymarket order book to JSONL."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import aiohttp

from venues.polymarket_reader import PolymarketReader, WS_URL, VENUE


def _pick_token_ids(reader: PolymarketReader, n: int = 5) -> list[str]:
    markets = reader.list_markets()
    ids: list[str] = []
    for m in markets:
        tokens = m.get("tokens") or []
        if not tokens:
            continue
        ids.append(tokens[0]["token_id"])
        if len(ids) >= n:
            break
    return ids


async def _stream(
    token_ids: list[str], out_dir: Path, max_messages: int
) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "polymarket_stream.jsonl"
    subscribe_msg = json.dumps(
        {"type": "subscribe", "channel": "book", "assets_ids": token_ids}
    )
    count = 0
    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(WS_URL) as ws:
                await ws.send_str(subscribe_msg)
                with out_path.open("a", encoding="utf-8") as fh:
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                            except json.JSONDecodeError:
                                continue
                            data["venue"] = VENUE
                            data["received_at"] = datetime.now(timezone.utc).isoformat()
                            fh.write(json.dumps(data) + "\n")
                            count += 1
                            token_label = token_ids[0] if token_ids else "?"
                            print(
                                f"venue=polymarket token={token_label}"
                                f" msg={count}/{max_messages}"
                            )
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
        print(f"stream error: {exc}", file=sys.stderr)
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Stream Polymarket book to JSONL")
    parser.add_argument("--token-ids", nargs="+", default=[], metavar="ID")
    parser.add_argument(
        "--out",
        default="data/external/odds_lines/polymarket",
        metavar="DIR",
    )
    parser.add_argument("--max-messages", type=int, default=500, metavar="N")
    args = parser.parse_args()

    out_dir = Path(args.out)
    reader = PolymarketReader()

    token_ids: list[str] = args.token_ids
    if not token_ids:
        token_ids = _pick_token_ids(reader)
        if not token_ids:
            print("No token_ids found — aborting.", file=sys.stderr)
            sys.exit(1)

    n = asyncio.run(_stream(token_ids, out_dir, args.max_messages))
    print(f"done — {n} messages logged to {out_dir}/polymarket_stream.jsonl")


if __name__ == "__main__":
    main()
