"""L13_cross_exchange_ev.py — Cross-Exchange EV Engine (PAPER MODE).

Compares model-implied probabilities against live exchange quotes to find
positive-EV opportunities across books. No HTTP, no order submission —
pure function of CSV/JSON inputs.

Public API
----------
    ExchangeQuote           dataclass
    EVOpportunity           dataclass
    find_ev_opportunities(model_predictions, quotes, min_ev_pct) -> list[EVOpportunity]
    shop_best_price(side, quotes_for_market) -> ExchangeQuote
    load_quotes_from_snapshot(snapshot_csv_path) -> list[ExchangeQuote]

CLI
---
    python L13_cross_exchange_ev.py find --snapshot path.csv --model preds.json [--min-ev 2.0]
    python L13_cross_exchange_ev.py rank --snapshot path.csv --model preds.json --top 20
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

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
) -> list[EVOpportunity]:
    """Identify positive-EV opportunities by comparing model probs to market quotes.

    Parameters
    ----------
    model_predictions:
        {(player, stat): {"p_over": float, "p_under": float}}
    quotes:
        All available ExchangeQuote objects (any book/side mix).
    min_ev_pct:
        Minimum EV percentage (ev_per_dollar * 100) to include in results.

    Returns
    -------
    List of EVOpportunity sorted by ev_per_dollar DESC.
    """
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
