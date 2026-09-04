"""Stream a read-only census of the available boxscore prop-line stores."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any
SPORT_ORDER = ("nba", "mlb", "soccer", "tennis")
SCORABLE_CLUSTER_MINIMUM = 30
MAX_SOURCE_FILE_BYTES = 300 * 1024 * 1024
DEFAULT_OUTPUT_DIR = Path("docs/evidence/harness/S240_boxscore_prop_census_2026-09-04")
DEFAULT_NBA_STORE = Path("data/cache/cv_fix/closing_props")
DEFAULT_JSONL_STORES = {sport: Path(f"data/frontend/prop_history_corpus_{sport}.jsonl") for sport in ("mlb", "soccer", "tennis")}
def _date_part(value: object) -> str | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    candidate = value[:10]
    return candidate if candidate[4:5] == "-" and candidate[7:8] == "-" else None
def _real_market_price(value: object) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    if isinstance(value, str):
        try:
            return math.isfinite(float(value.strip()))
        except ValueError:
            return False
    return False
def _empty_result(
    sport: str, source_path: Path, source_unit: str, source_exists: bool, price_field: str
) -> dict[str, Any]:
    return {
        "sport": sport,
        "source_path": source_path.as_posix(),
        "source_absolute_path": source_path.absolute().as_posix(),
        "source_exists": source_exists,
        "source_unit": source_unit,
        "store_bytes": 0,
        "source_count": 0,
        "tidy_row_count": 0,
        "distinct_player_count": 0,
        "distinct_stat_count": 0,
        "date_range": {"start": None, "end": None},
        "market_price_field": price_field,
        "market_price_null_count": 0,
        "market_price_observed_count": 0,
        "market_price_null_share": None,
        "market_price_null_share_denominator": 0,
        "real_market_price_row_count": 0,
        "real_market_price_source_count": 0,
        "game_cluster_count": 0,
        "real_market_price_cluster_count": 0,
        "real_market_price_cluster_denominator": 0,
        "real_market_price_cluster_basis": "closing_props JSON file" if sport == "nba" else "source date",
        "unparsed_source_count": 0,
        "verdict": "NOT SCORABLE",
        "blocking_count": "real_market_price_cluster_count=0; requires >=30",
    }


def _finish_result(
    result: dict[str, Any],
    players: set[str],
    stats: set[str],
    dates: set[str],
    game_clusters: set[str],
    priced_clusters: set[str],
) -> dict[str, Any]:
    result["distinct_player_count"] = len(players)
    result["distinct_stat_count"] = len(stats)
    result["date_range"] = {"start": min(dates) if dates else None, "end": max(dates) if dates else None}
    result["game_cluster_count"] = len(game_clusters)
    result["real_market_price_cluster_count"] = len(priced_clusters)
    result["real_market_price_cluster_denominator"] = len(game_clusters)
    denominator = result["market_price_null_share_denominator"]
    if denominator:
        result["market_price_null_share"] = result["market_price_null_count"] / denominator
    clusters = result["real_market_price_cluster_count"]
    if clusters >= SCORABLE_CLUSTER_MINIMUM:
        result["verdict"] = "SCORABLE"
        result["blocking_count"] = None
    else:
        result["blocking_count"] = f"real_market_price_cluster_count={clusters}; requires >=30"
    return result


def census_jsonl_store(sport: str, source_path: Path) -> dict[str, Any]:
    """Census one JSONL prop store by streaming it one input row at a time."""
    if not source_path.is_file():
        return _empty_result(sport, source_path, "rows", False, "market_prob")
    result = _empty_result(sport, source_path, "rows", True, "market_prob")
    result["store_bytes"] = source_path.stat().st_size
    players: set[str] = set()
    stats: set[str] = set()
    dates: set[str] = set()
    game_clusters: set[str] = set()
    priced_clusters: set[str] = set()
    with source_path.open("r", encoding="utf-8") as handle:
        for row_number, raw_line in enumerate(handle, start=1):
            result["source_count"] += 1
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                result["unparsed_source_count"] += 1
                continue
            if not isinstance(record, dict):
                result["unparsed_source_count"] += 1
                continue
            result["tidy_row_count"] += 1
            player, stat = record.get("prop_player"), record.get("prop_stat")
            date = _date_part(record.get("ts"))
            cluster = date or f"row-{row_number}"
            game_clusters.add(cluster)
            if player is not None:
                players.add(str(player))
            if stat is not None:
                stats.add(str(stat))
            if date is not None:
                dates.add(date)
            price = record.get("market_prob")
            result["market_price_null_share_denominator"] += 1
            if price is None:
                result["market_price_null_count"] += 1
            else:
                result["market_price_observed_count"] += 1
            if _real_market_price(price):
                result["real_market_price_row_count"] += 1
                result["real_market_price_source_count"] += 1
                priced_clusters.add(cluster)
    return _finish_result(result, players, stats, dates, game_clusters, priced_clusters)


def _nba_tidy_rows(payload: Mapping[str, Any], game: str) -> Iterator[dict[str, Any]]:
    for bookmaker in payload.get("bookmakers", []):
        if not isinstance(bookmaker, dict):
            continue
        for market in bookmaker.get("markets", []):
            if not isinstance(market, dict):
                continue
            timestamp = market.get("last_update") or bookmaker.get("last_update") or payload.get("commence_time")
            for outcome in market.get("outcomes", []):
                if not isinstance(outcome, dict):
                    continue
                yield {
                    "game": game,
                    "player": outcome.get("description"),
                    "outcome_name": outcome.get("name"),
                    "stat": market.get("key"),
                    "line": outcome.get("point"),
                    "price": outcome.get("price"),
                    "book": bookmaker.get("key"),
                    "timestamp": timestamp,
                }


def census_nba_store(source_path: Path, tidy_path: Path | None = None) -> dict[str, Any]:
    """Census NBA payloads one JSON file at a time and optionally write tidy rows."""
    if not source_path.is_dir():
        if tidy_path is not None:
            tidy_path.parent.mkdir(parents=True, exist_ok=True); tidy_path.write_text("", encoding="utf-8")
        return _empty_result("nba", source_path, "files", False, "price")
    result = _empty_result("nba", source_path, "files", True, "price")
    files = sorted(source_path.glob("*.json"))
    result["store_bytes"] = sum(item.stat().st_size for item in files)
    players: set[str] = set()
    stats: set[str] = set()
    dates: set[str] = set()
    game_clusters: set[str] = set()
    priced_clusters: set[str] = set()
    table = None
    if tidy_path is not None:
        tidy_path.parent.mkdir(parents=True, exist_ok=True)
        table = tidy_path.open("w", encoding="utf-8")
    try:
        for source_file in files:
            result["source_count"] += 1
            game = source_file.stem
            game_clusters.add(game)
            if source_file.stat().st_size > MAX_SOURCE_FILE_BYTES:
                result["unparsed_source_count"] += 1
                continue
            try:
                with source_file.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (OSError, json.JSONDecodeError):
                result["unparsed_source_count"] += 1
                continue
            if not isinstance(payload, dict):
                result["unparsed_source_count"] += 1
                continue
            date = _date_part(payload.get("commence_time"))
            if date is not None:
                dates.add(date)
            source_has_real_price = False
            for row in _nba_tidy_rows(payload, game):
                result["tidy_row_count"] += 1
                if table is not None:
                    table.write(json.dumps(row, separators=(",", ":")) + "\n")
                if row["player"] is not None:
                    players.add(str(row["player"]))
                if row["stat"] is not None:
                    stats.add(str(row["stat"]))
                price = row["price"]
                result["market_price_null_share_denominator"] += 1
                if price is None:
                    result["market_price_null_count"] += 1
                else:
                    result["market_price_observed_count"] += 1
                if _real_market_price(price):
                    result["real_market_price_row_count"] += 1
                    source_has_real_price = True
            if source_has_real_price:
                result["real_market_price_source_count"] += 1
                priced_clusters.add(game)
    finally:
        if table is not None:
            table.close()
    return _finish_result(result, players, stats, dates, game_clusters, priced_clusters)


def run_census(
    nba_store: Path = DEFAULT_NBA_STORE,
    jsonl_stores: Mapping[str, Path] = DEFAULT_JSONL_STORES,
    nba_tidy_path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Return the four-sport census without modifying any source store."""
    results = {"nba": census_nba_store(nba_store, nba_tidy_path)}
    for sport in ("mlb", "soccer", "tennis"):
        results[sport] = census_jsonl_store(sport, jsonl_stores[sport])
    return results


def write_artifacts(results: Mapping[str, Mapping[str, Any]], output_dir: Path) -> None:
    """Write deterministic per-sport counts and a combined summary table."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for sport in SPORT_ORDER:
        (output_dir / f"{sport}.json").write_text(
            json.dumps(results[sport], indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    summary_table = [
        {
            "sport": sport,
            "source_count": results[sport]["source_count"],
            "real_market_price_source_count": results[sport]["real_market_price_source_count"],
            "game_cluster_count": results[sport]["game_cluster_count"],
            "real_market_price_cluster_count": results[sport]["real_market_price_cluster_count"],
            "real_market_price_cluster_denominator": results[sport]["real_market_price_cluster_denominator"],
            "market_price_null_count": results[sport]["market_price_null_count"],
            "market_price_null_share_denominator": results[sport]["market_price_null_share_denominator"],
            "unparsed_source_count": results[sport]["unparsed_source_count"],
            "verdict": results[sport]["verdict"],
            "blocking_count": results[sport]["blocking_count"],
        }
        for sport in SPORT_ORDER
    ]
    (output_dir / "summary.json").write_text(
        json.dumps({"summary_table": summary_table}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _print_summary(results: Mapping[str, Mapping[str, Any]]) -> None:
    print("sport | source_count | price_sources | price_clusters | verdict")
    for sport in SPORT_ORDER:
        result = results[sport]
        print(
            f"{sport} | {result['source_count']} | {result['real_market_price_source_count']} | "
            f"{result['real_market_price_cluster_count']} | {result['verdict']}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the census and emit deterministic evidence artifacts outside data/."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nba-store", type=Path, default=DEFAULT_NBA_STORE)
    parser.add_argument("--mlb-store", type=Path, default=DEFAULT_JSONL_STORES["mlb"])
    parser.add_argument("--soccer-store", type=Path, default=DEFAULT_JSONL_STORES["soccer"])
    parser.add_argument("--tennis-store", type=Path, default=DEFAULT_JSONL_STORES["tennis"])
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    results = run_census(
        nba_store=args.nba_store,
        jsonl_stores={"mlb": args.mlb_store, "soccer": args.soccer_store, "tennis": args.tennis_store},
        nba_tidy_path=args.output_dir / "nba_tidy.jsonl",
    )
    write_artifacts(results, args.output_dir)
    _print_summary(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
