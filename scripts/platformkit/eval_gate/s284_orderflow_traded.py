"""S284 NBA Kalshi order-flow premise census; no score is run by this module."""
from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pyarrow.dataset as ds
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[3]
PRICE_PATH = ROOT / "data/cache/inplay_odds/nba_price_series.parquet"
CHECKPOINT_PATH = ROOT / "data/cache/inplay_odds/nba_checkpoints_full.parquet"
KALSHI_RE = re.compile(r"^KXNBAGAME-([0-9]{2}[A-Z]{3}[0-9]{2})([A-Z]{6})$")
POLY_RE = re.compile(r"^nba-([a-z]{3})-([a-z]{3})-([0-9]{4}-[0-9]{2}-[0-9]{2})$")
ORDERINGS = ("away_home", "home_away")


def parse_kalshi_event_key(event_key: str) -> tuple[str, str, str] | None:
    """Return (date, away, home) from one native Kalshi NBA event key."""
    match = KALSHI_RE.match(event_key)
    if match is None:
        return None
    date = datetime.strptime(match.group(1), "%y%b%d").date().isoformat()
    teams = match.group(2)
    return date, teams[:3], teams[3:]


def parse_checkpoint_ticker(ticker: str) -> tuple[str, str, str] | None:
    """Return (date, away, home) from one frozen Polymarket checkpoint ticker."""
    match = POLY_RE.match(ticker)
    if match is None:
        return None
    return match.group(3), match.group(1).upper(), match.group(2).upper()


def _ordered(triple: tuple[str, str, str], ordering: str) -> tuple[str, str, str]:
    date, away, home = triple
    return (date, away, home) if ordering == "away_home" else (date, home, away)


def enumerate_overlaps(events: dict[str, tuple[str, str, str]],
                       games: dict[str, tuple[str, str, str]]) -> tuple[list[dict], dict]:
    """Enumerate both declared team orderings and their full date-offset census."""
    by_pair: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for game_id, (date, away, home) in games.items():
        by_pair[(away, home)].append((date, game_id))
    rows, summary = [], {}
    for ordering in ORDERINGS:
        offsets, matches = Counter(), set()
        for event_key, triple in sorted(events.items()):
            date, away, home = _ordered(triple, ordering)
            candidate_ids = []
            for checkpoint_date, game_id in by_pair.get((away, home), []):
                offset = (datetime.fromisoformat(checkpoint_date).date()
                          - datetime.fromisoformat(date).date()).days
                offsets[offset] += 1
                if offset == 0:
                    candidate_ids.append(game_id)
                    matches.add(game_id)
            rows.append({"ordering": ordering, "event_key": event_key,
                         "kalshi_date": triple[0], "kalshi_away": triple[1],
                         "kalshi_home": triple[2],
                         "checkpoint_game_ids_at_zero_offset": ";".join(sorted(candidate_ids))})
        summary[ordering] = {"game_cluster_overlap": len(matches),
                             "date_offset_distribution": dict(sorted(offsets.items()))}
    return rows, summary


def measure_premise() -> tuple[list[dict], dict]:
    """Scan named stores separately, retaining only parser inputs and whole-set flag counts."""
    event_keys: set[str] = set()
    price_file = ds.dataset(PRICE_PATH, format="parquet")
    for batch in price_file.scanner(filter=ds.field("venue") == "kalshi",
                                    columns=["event_key"]).to_batches():
        for value in batch.column(0).to_pylist():
            if value is not None:
                event_keys.add(str(value))
    events = {key: parsed for key in event_keys
              if (parsed := parse_kalshi_event_key(key)) is not None}

    games: dict[str, tuple[str, str, str]] = {}
    traded_total = traded_true = 0
    checkpoint_file = pq.ParquetFile(CHECKPOINT_PATH)
    for batch in checkpoint_file.iter_batches(columns=["game_id", "market_ticker", "traded"]):
        game_ids, tickers, traded = (column.to_pylist() for column in batch.columns)
        for game_id, ticker, flag in zip(game_ids, tickers, traded):
            traded_total += 1
            traded_true += int(bool(flag))
            parsed = parse_checkpoint_ticker(str(ticker))
            if parsed is not None:
                games.setdefault(str(game_id), parsed)
    rows, orderings = enumerate_overlaps(events, games)
    best = max(ORDERINGS, key=lambda key: orderings[key]["game_cluster_overlap"])
    summary = {"price_store": {"path": PRICE_PATH.relative_to(ROOT).as_posix(),
                                "bytes": PRICE_PATH.stat().st_size,
                                "kalshi_event_keys": len(event_keys),
                                "parsed_kalshi_event_keys": len(events)},
               "checkpoint_store": {"path": CHECKPOINT_PATH.relative_to(ROOT).as_posix(),
                                    "bytes": CHECKPOINT_PATH.stat().st_size,
                                    "rows": traded_total, "traded_true": traded_true,
                                    "traded_false": traded_total - traded_true,
                                    "parsed_game_clusters": len(games)},
               "orderings": orderings, "best_ordering": best,
               "best_game_cluster_overlap": orderings[best]["game_cluster_overlap"]}
    return rows, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="S284 premise census only")
    parser.add_argument("--census-csv", type=Path, required=True)
    args = parser.parse_args()
    rows, summary = measure_premise()
    args.census_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.census_csv.open("w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(summary)


if __name__ == "__main__":
    main()
