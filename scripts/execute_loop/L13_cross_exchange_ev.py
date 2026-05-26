"""L13_cross_exchange_ev.py — Cross-Exchange EV Engine (PAPER MODE).

Compares model-implied probabilities against live exchange quotes to find
positive-EV opportunities across books. No HTTP, no order submission —
pure function of CSV/JSON inputs.

Public API
----------
    ExchangeQuote           dataclass
    EVOpportunity           dataclass
    find_ev_opportunities(model_predictions, quotes, min_ev_pct,
                          source, market_id, exchanges) -> list[EVOpportunity]
    shop_best_price(side, quotes_for_market) -> ExchangeQuote
    load_quotes_from_snapshot(snapshot_csv_path) -> list[ExchangeQuote]
    fetch_quotes_from_paper_clients(market_id, exchanges, player, stat, line)
        -> dict[str, list[ExchangeQuote]]

CLI
---
    python L13_cross_exchange_ev.py find --snapshot path.csv --model preds.json [--min-ev 2.0]
    python L13_cross_exchange_ev.py rank --snapshot path.csv --model preds.json --top 20

Paper vs Live Mode (MODE GATING)
---------------------------------
This module is paper/live-mode-agnostic. It composes lower layers (L9-L12)
which control paper-vs-live behaviour individually. This module contains no
live API calls of its own — it only normalises orderbook data returned by
those clients.

Live mode for downstream calls is enabled only when the per-exchange env var
(e.g. KALSHI_LIVE_ENABLED=1) is set on the underlying client; this module
defers to those defaults.

Environment Variables
---------------------
None. This module reads no environment variables directly. All paper/live
gating is delegated to the L9-L12 exchange clients it composes.
"""
from __future__ import annotations

import argparse
import csv
import importlib
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exchange registry — maps name -> (module_path, get_orderbook_fn_name, normalizer_fn)
# ---------------------------------------------------------------------------

_EXCHANGE_REGISTRY: dict[str, tuple[str, str, str]] = {
    "kalshi":      ("scripts.execute_loop.L09_kalshi_client",    "get_orderbook", "_normalize_kalshi"),
    "polymarket":  ("scripts.execute_loop.L10_polymarket_client", "get_orderbook", "_normalize_polymarket"),
    "sporttrade":  ("scripts.execute_loop.L11_sporttrade_client", "get_orderbook", "_normalize_sporttrade"),
    "prophet":     ("scripts.execute_loop.L12_prophet_client",    "get_orderbook", "_normalize_prophet"),
}

# ---------------------------------------------------------------------------
# Odds math helpers
# ---------------------------------------------------------------------------

def american_to_decimal(p: int) -> float:
    """Convert American odds integer to decimal multiplier (stake included)."""
    if p > 0:
        return 1.0 + (p / 100.0)
    return 1.0 + (100.0 / abs(p))


def prob_to_american(p: float) -> int:
    """Convert win probability [0,1] to American odds integer."""
    if p >= 0.5:
        return int(round(-100.0 * p / (1.0 - p)))
    return int(round(100.0 * (1.0 - p) / p))


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ExchangeQuote:
    """A single price quote from one book for one side of a player prop."""

    book: str
    market: str
    player: str
    stat: str
    side: str        # "OVER" | "UNDER"
    line: float
    price: int       # American odds, e.g. -110 or +120
    liquidity: float
    ts: str          # ISO-8601 timestamp


@dataclass
class EVOpportunity:
    """A positive-EV bet opportunity identified by the engine."""

    market: str
    player: str
    stat: str
    side: str
    best_quote: ExchangeQuote
    model_prob: float
    ev_per_dollar: float
    fair_price: int         # American odds where implied prob == model_prob
    all_quotes: list[ExchangeQuote] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _parse_price(raw) -> Optional[int]:
    """Parse American odds from int, float, or string. Returns None on error."""
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    if isinstance(raw, str):
        try:
            return int(raw.strip())
        except ValueError:
            log.warning("Unparseable price value '%s' — skipping quote", raw)
            return None
    log.warning("Unexpected price type %s for value '%s' — skipping quote", type(raw), raw)
    return None


def shop_best_price(side: str, quotes_for_market: list[ExchangeQuote]) -> ExchangeQuote:
    """Return the quote with the highest decimal payout for the backer.

    Tie-break: highest liquidity DESC.

    Parameters
    ----------
    side:
        "OVER" or "UNDER" — used only for logging; caller is responsible
        for pre-filtering to the correct side.
    quotes_for_market:
        Non-empty list of ExchangeQuote (all positive liquidity, same side).

    Returns
    -------
    ExchangeQuote with the best (highest) decimal payout.
    """
    if not quotes_for_market:
        raise ValueError(f"shop_best_price received empty list for side={side}")

    def _sort_key(q: ExchangeQuote):
        return (american_to_decimal(q.price), q.liquidity)

    return max(quotes_for_market, key=_sort_key)


# ---------------------------------------------------------------------------
# EV calculation
# ---------------------------------------------------------------------------

_PROB_WARN_HIGH = 0.99
_PROB_WARN_LOW  = 0.01


def find_ev_opportunities(
    model_predictions: dict,
    quotes: list[ExchangeQuote],
    min_ev_pct: float = 2.0,
    *,
    source: str = "snapshot",
    market_id: Optional[str] = None,
    exchanges: Optional[List[str]] = None,
) -> list[EVOpportunity]:
    """Identify positive-EV opportunities by comparing model probs to market quotes.

    Parameters
    ----------
    model_predictions:
        {(player, stat): {"p_over": float, "p_under": float}}
    quotes:
        All available ExchangeQuote objects (any book/side mix).
        Ignored when source="paper_clients" (quotes are fetched internally).
    min_ev_pct:
        Minimum EV percentage (ev_per_dollar * 100) to include in results.
    source:
        "snapshot" (default, v1 behaviour) — use the *quotes* argument directly.
        "paper_clients" — soft-import L09-L12 clients and fetch live orderbooks.
    market_id:
        Required when source="paper_clients"; passed to each exchange client.
    exchanges:
        Which exchanges to query when source="paper_clients".
        Defaults to all registered exchanges (kalshi, polymarket, sporttrade, prophet).

    Returns
    -------
    List of EVOpportunity sorted by ev_per_dollar DESC.
    """
    if source == "paper_clients":
        if not market_id:
            raise ValueError("market_id must be provided when source='paper_clients'")
        # Derive player/stat/line from the first prediction key if available
        first_player, first_stat = ("", "")
        first_line = 0.0
        for (p, s) in model_predictions.keys():
            first_player, first_stat = p, s
            break
        client_quotes = fetch_quotes_from_paper_clients(
            market_id=market_id,
            exchanges=exchanges,
            player=first_player,
            stat=first_stat,
            line=first_line,
        )
        quotes = [q for qs in client_quotes.values() for q in qs]
    opportunities: list[EVOpportunity] = []

    for (player, stat), probs in model_predictions.items():
        for side in ("OVER", "UNDER"):
            prob_key = "p_" + side.lower()
            model_prob = probs.get(prob_key)

            if model_prob is None:
                log.warning("No %s probability for (%s, %s) — skipping", prob_key, player, stat)
                continue

            # Guard: extreme probabilities suggest model error
            if model_prob > _PROB_WARN_HIGH or model_prob < _PROB_WARN_LOW:
                log.warning(
                    "model_prob=%.4f out of safe range [%.2f, %.2f] for (%s, %s, %s) — skipping",
                    model_prob, _PROB_WARN_LOW, _PROB_WARN_HIGH, player, stat, side,
                )
                continue

            # Filter quotes to this (player, stat, side) with positive liquidity
            relevant = [
                q for q in quotes
                if q.player == player
                and q.stat == stat
                and q.side == side
                and q.liquidity > 0
            ]

            if not relevant:
                log.warning(
                    "No liquid quotes for (%s, %s, %s) — skipping",
                    player, stat, side,
                )
                continue

            best = shop_best_price(side, relevant)
            payout = american_to_decimal(best.price)

            # EV = E[profit] per $1 risked
            # Win: receive (payout - 1), lose: -1
            ev_per_dollar = model_prob * (payout - 1.0) - (1.0 - model_prob)
            ev_pct = ev_per_dollar * 100.0

            if ev_pct >= min_ev_pct:
                fair_price = prob_to_american(model_prob)
                opportunities.append(
                    EVOpportunity(
                        market=best.market,
                        player=player,
                        stat=stat,
                        side=side,
                        best_quote=best,
                        model_prob=model_prob,
                        ev_per_dollar=ev_per_dollar,
                        fair_price=fair_price,
                        all_quotes=relevant,
                    )
                )

    opportunities.sort(key=lambda o: o.ev_per_dollar, reverse=True)
    return opportunities


# ---------------------------------------------------------------------------
# CSV snapshot loader
# ---------------------------------------------------------------------------

# Expected CSV columns (order flexible; header required)
_REQUIRED_COLS = {"book", "market", "player", "stat", "side", "line", "price", "liquidity", "ts"}


def load_quotes_from_snapshot(snapshot_csv_path: str) -> list[ExchangeQuote]:
    """Parse a CSV snapshot file into a list of ExchangeQuote objects.

    Rows with unparseable price or non-positive liquidity are skipped with WARN.

    CSV schema (header required):
        book,market,player,stat,side,line,price,liquidity,ts
    """
    path = Path(snapshot_csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Snapshot CSV not found: {path}")

    quotes: list[ExchangeQuote] = []

    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)

        # Validate columns
        if reader.fieldnames is None:
            raise ValueError(f"CSV appears empty: {path}")
        missing = _REQUIRED_COLS - set(reader.fieldnames)
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")

        for row_num, row in enumerate(reader, start=2):  # 1-indexed; row 1 is header
            price_raw = row.get("price", "")
            price = _parse_price(price_raw)
            if price is None:
                log.warning("Row %d: skipping due to invalid price '%s'", row_num, price_raw)
                continue

            try:
                liquidity = float(row["liquidity"])
            except (ValueError, KeyError):
                log.warning("Row %d: skipping due to invalid liquidity '%s'", row_num, row.get("liquidity"))
                continue

            try:
                line = float(row["line"])
            except (ValueError, KeyError):
                log.warning("Row %d: skipping due to invalid line '%s'", row_num, row.get("line"))
                continue

            side = row.get("side", "").strip().upper()
            if side not in ("OVER", "UNDER"):
                log.warning("Row %d: unknown side '%s' — skipping", row_num, row.get("side"))
                continue

            quotes.append(
                ExchangeQuote(
                    book=row["book"].strip(),
                    market=row["market"].strip(),
                    player=row["player"].strip(),
                    stat=row["stat"].strip(),
                    side=side,
                    line=line,
                    price=price,
                    liquidity=liquidity,
                    ts=row["ts"].strip(),
                )
            )

    log.info("Loaded %d quotes from %s", len(quotes), path)
    return quotes


# ---------------------------------------------------------------------------
# Per-exchange normalizers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_kalshi(
    orderbook: dict,
    market_id: str,
    player: str,
    stat: str,
    line: float,
) -> list[ExchangeQuote]:
    """Convert Kalshi orderbook {yes_bids, yes_asks, no_bids, no_asks} to ExchangeQuotes.

    Kalshi prices are cents (1-99).  Implied prob = price / 100.
    American odds: prob >= 0.5 → -100*p/(1-p), else +100*(1-p)/p.
    yes side → OVER, no side → UNDER.
    """
    quotes: list[ExchangeQuote] = []
    ts = _now_iso()

    def _cents_to_american(cents: int) -> int:
        p = max(1, min(99, int(cents))) / 100.0
        return prob_to_american(p)

    # yes_bids → best price a backer can sell YES at
    for level in orderbook.get("yes_bids", []):
        price_cents, qty = (level[0], level[1]) if isinstance(level, (list, tuple)) else (level.get("price", 50), level.get("size", 0))
        quotes.append(ExchangeQuote(
            book="kalshi",
            market=market_id,
            player=player,
            stat=stat,
            side="OVER",
            line=line,
            price=_cents_to_american(price_cents),
            liquidity=float(qty),
            ts=ts,
        ))

    # no_bids → UNDER side
    for level in orderbook.get("no_bids", []):
        price_cents, qty = (level[0], level[1]) if isinstance(level, (list, tuple)) else (level.get("price", 50), level.get("size", 0))
        quotes.append(ExchangeQuote(
            book="kalshi",
            market=market_id,
            player=player,
            stat=stat,
            side="UNDER",
            line=line,
            price=_cents_to_american(price_cents),
            liquidity=float(qty),
            ts=ts,
        ))

    return quotes


def _normalize_polymarket(
    orderbook,
    market_id: str,
    player: str,
    stat: str,
    line: float,
) -> list[ExchangeQuote]:
    """Convert PolyOrderbook (bids/asks as [{"price": usdc_float, "size": float}]) to ExchangeQuotes.

    Polymarket prices are USDC per share (0,1).  Implied prob = price.
    Best ask represents the taker's cost to go OVER; best bid → UNDER proxy.
    We emit one OVER quote (best ask) and one UNDER quote (1 - best ask).
    """
    quotes: list[ExchangeQuote] = []
    ts = _now_iso()

    # PolyOrderbook dataclass or plain dict both support attribute/key access
    if hasattr(orderbook, "asks"):
        asks = orderbook.asks
        bids = orderbook.bids
    else:
        asks = orderbook.get("asks", [])
        bids = orderbook.get("bids", [])

    def _usdc_to_american(price_usdc: float) -> int:
        p = max(0.01, min(0.99, float(price_usdc)))
        return prob_to_american(p)

    if asks:
        best_ask = asks[0]
        price_usdc = best_ask.get("price", 0.5) if isinstance(best_ask, dict) else best_ask
        size = best_ask.get("size", 0.0) if isinstance(best_ask, dict) else 0.0
        quotes.append(ExchangeQuote(
            book="polymarket",
            market=market_id,
            player=player,
            stat=stat,
            side="OVER",
            line=line,
            price=_usdc_to_american(price_usdc),
            liquidity=float(size),
            ts=ts,
        ))
        # UNDER implied by complement
        quotes.append(ExchangeQuote(
            book="polymarket",
            market=market_id,
            player=player,
            stat=stat,
            side="UNDER",
            line=line,
            price=_usdc_to_american(1.0 - float(price_usdc)),
            liquidity=float(size),
            ts=ts,
        ))

    return quotes


def _normalize_sporttrade(
    orderbook: dict,
    market_id: str,
    player: str,
    stat: str,
    line: float,
) -> list[ExchangeQuote]:
    """Convert Sporttrade orderbook {bids: [[price, qty], ...], asks: ...} to ExchangeQuotes.

    Sporttrade prices are cents (1-99).  back side → OVER at best ask; lay → UNDER.
    """
    quotes: list[ExchangeQuote] = []
    ts = _now_iso()

    def _cents_to_american(price: float) -> int:
        p = max(0.01, min(0.99, float(price) / 100.0))
        return prob_to_american(p)

    # Best ask = cheapest price to buy (OVER)
    asks = orderbook.get("asks", [])
    if asks:
        level = asks[0]
        price_raw, qty = (level[0], level[1]) if isinstance(level, (list, tuple)) else (level.get("price", 50), level.get("size", 0))
        quotes.append(ExchangeQuote(
            book="sporttrade",
            market=market_id,
            player=player,
            stat=stat,
            side="OVER",
            line=line,
            price=_cents_to_american(price_raw),
            liquidity=float(qty),
            ts=ts,
        ))

    # Best bid = highest price to sell (UNDER complement)
    bids = orderbook.get("bids", [])
    if bids:
        level = bids[0]
        price_raw, qty = (level[0], level[1]) if isinstance(level, (list, tuple)) else (level.get("price", 50), level.get("size", 0))
        # Complement: if bid is 55 cents, UNDER implied prob = 1 - 0.55 = 0.45
        p_complement = max(0.01, min(0.99, 1.0 - float(price_raw) / 100.0))
        quotes.append(ExchangeQuote(
            book="sporttrade",
            market=market_id,
            player=player,
            stat=stat,
            side="UNDER",
            line=line,
            price=prob_to_american(p_complement),
            liquidity=float(qty),
            ts=ts,
        ))

    return quotes


def _normalize_prophet(
    orderbook: dict,
    market_id: str,
    player: str,
    stat: str,
    line: float,
) -> list[ExchangeQuote]:
    """Convert Prophet orderbook {bids: [[decimal, qty], ...], asks: ...} to ExchangeQuotes.

    Prophet prices are decimal odds (1.01 – 100.0).
    Best ask (lowest decimal) → OVER; best bid (highest decimal) → UNDER.
    Decimal to American: dec >= 2.0 → +(dec-1)*100, else → -100/(dec-1).
    """
    quotes: list[ExchangeQuote] = []
    ts = _now_iso()

    def _decimal_to_american(dec: float) -> int:
        dec = max(1.01, float(dec))
        if dec >= 2.0:
            return int(round((dec - 1.0) * 100.0))
        return int(round(-100.0 / (dec - 1.0)))

    asks = orderbook.get("asks", [])
    if asks:
        level = asks[0]
        dec_raw, qty = (level[0], level[1]) if isinstance(level, (list, tuple)) else (level.get("price", 2.0), level.get("size", 0))
        quotes.append(ExchangeQuote(
            book="prophet",
            market=market_id,
            player=player,
            stat=stat,
            side="OVER",
            line=line,
            price=_decimal_to_american(dec_raw),
            liquidity=float(qty),
            ts=ts,
        ))

    bids = orderbook.get("bids", [])
    if bids:
        level = bids[0]
        dec_raw, qty = (level[0], level[1]) if isinstance(level, (list, tuple)) else (level.get("price", 2.0), level.get("size", 0))
        quotes.append(ExchangeQuote(
            book="prophet",
            market=market_id,
            player=player,
            stat=stat,
            side="UNDER",
            line=line,
            price=_decimal_to_american(dec_raw),
            liquidity=float(qty),
            ts=ts,
        ))

    return quotes


# Map normalizer name strings to actual functions
_NORMALIZER_MAP: dict[str, object] = {
    "_normalize_kalshi":     _normalize_kalshi,
    "_normalize_polymarket": _normalize_polymarket,
    "_normalize_sporttrade": _normalize_sporttrade,
    "_normalize_prophet":    _normalize_prophet,
}


# ---------------------------------------------------------------------------
# Paper-client quote fetcher
# ---------------------------------------------------------------------------

def fetch_quotes_from_paper_clients(
    market_id: str,
    exchanges: list[str] | None = None,
    player: str = "",
    stat: str = "",
    line: float = 0.0,
) -> dict[str, list[ExchangeQuote]]:
    """Fetch orderbooks from paper-mode exchange clients and normalize to ExchangeQuotes.

    Soft-imports each exchange module via importlib; skips on any failure with WARN.

    Parameters
    ----------
    market_id:
        Exchange-specific market identifier passed to each client's get_orderbook.
    exchanges:
        Which exchanges to query.  Defaults to all registered exchanges.
    player, stat, line:
        Metadata forwarded to normalizers for ExchangeQuote construction.

    Returns
    -------
    dict mapping exchange name -> list[ExchangeQuote] for successful fetches only.
    """
    if exchanges is None:
        exchanges = list(_EXCHANGE_REGISTRY.keys())

    result: dict[str, list[ExchangeQuote]] = {}

    for name in exchanges:
        if name not in _EXCHANGE_REGISTRY:
            log.warning("fetch_quotes_from_paper_clients: unknown exchange %r — skipping", name)
            continue

        module_path, fn_name, normalizer_name = _EXCHANGE_REGISTRY[name]
        normalizer = _NORMALIZER_MAP.get(normalizer_name)

        try:
            mod = importlib.import_module(module_path)
            get_ob = getattr(mod, fn_name)
            orderbook = get_ob(market_id)
            if normalizer is None:
                log.warning("No normalizer found for %r — skipping", name)
                continue
            quotes = normalizer(orderbook, market_id, player, stat, line)  # type: ignore[operator]
            result[name] = quotes
            log.debug("fetch_quotes_from_paper_clients: %s → %d quote(s)", name, len(quotes))
        except Exception as exc:
            log.warning(
                "fetch_quotes_from_paper_clients: %s failed (%s: %s) — skipping",
                name, type(exc).__name__, exc,
            )

    return result


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

_TSV_HEADER = "\t".join([
    "rank", "player", "stat", "side", "book", "line", "price",
    "fair_price", "model_prob", "ev_pct", "liquidity",
])


def _format_tsv(opportunities: list[EVOpportunity]) -> str:
    rows = [_TSV_HEADER]
    for i, opp in enumerate(opportunities, start=1):
        q = opp.best_quote
        rows.append("\t".join([
            str(i),
            opp.player,
            opp.stat,
            opp.side,
            q.book,
            str(q.line),
            (f"+{q.price}" if q.price > 0 else str(q.price)),
            (f"+{opp.fair_price}" if opp.fair_price > 0 else str(opp.fair_price)),
            f"{opp.model_prob:.4f}",
            f"{opp.ev_per_dollar * 100:.2f}%",
            f"{q.liquidity:.0f}",
        ]))
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_predictions(model_path: str) -> dict:
    """Load model predictions JSON: {"{player}|{stat}": {"p_over": ..., "p_under": ...}}
    Keys may use pipe or tuple representation."""
    path = Path(model_path)
    if not path.exists():
        raise FileNotFoundError(f"Model predictions file not found: {path}")

    with path.open(encoding="utf-8") as fh:
        raw = json.load(fh)

    preds: dict = {}
    for key, val in raw.items():
        if "|" in key:
            player, stat = key.split("|", 1)
        elif "," in key:
            parts = key.strip("()").split(",")
            player, stat = parts[0].strip().strip("'\""), parts[1].strip().strip("'\"")
        else:
            log.warning("Unrecognised key format '%s' in predictions JSON — skipping", key)
            continue
        preds[(player.strip(), stat.strip())] = val

    return preds


def _cmd_find(args: argparse.Namespace) -> None:
    quotes = load_quotes_from_snapshot(args.snapshot)
    preds = _load_predictions(args.model)
    opps = find_ev_opportunities(preds, quotes, min_ev_pct=args.min_ev)
    if not opps:
        print("No EV opportunities found above {:.1f}%".format(args.min_ev))
        return
    print(_format_tsv(opps))


def _cmd_rank(args: argparse.Namespace) -> None:
    quotes = load_quotes_from_snapshot(args.snapshot)
    preds = _load_predictions(args.model)
    opps = find_ev_opportunities(preds, quotes, min_ev_pct=0.0)
    top = opps[: args.top]
    if not top:
        print("No opportunities found.")
        return
    print(_format_tsv(top))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="L13_cross_exchange_ev",
        description="Cross-Exchange EV Engine (paper mode — no HTTP, no orders)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    find_p = sub.add_parser("find", help="Find all opportunities above min-ev threshold")
    find_p.add_argument("--snapshot", required=True, help="Path to quotes CSV")
    find_p.add_argument("--model", required=True, help="Path to model predictions JSON")
    find_p.add_argument("--min-ev", type=float, default=2.0, help="Min EV%% (default 2.0)")
    find_p.set_defaults(func=_cmd_find)

    rank_p = sub.add_parser("rank", help="Rank top-N opportunities (ignores min-ev filter)")
    rank_p.add_argument("--snapshot", required=True, help="Path to quotes CSV")
    rank_p.add_argument("--model", required=True, help="Path to model predictions JSON")
    rank_p.add_argument("--top", type=int, default=20, help="Number of results (default 20)")
    rank_p.set_defaults(func=_cmd_rank)

    return parser


def main(argv=None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s [L13] %(message)s",
        stream=sys.stderr,
    )
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
