"""replay.json room: market-tick replay for 2-3 finished MLB games.
pyarrow allowed here only, column-pruned reads only. Never fabricates a
model probability -- if the event_id join to paper_predictions.jsonl finds
no match, pregame/in-game model probs ship null with an honest note.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pyarrow.compute as pc
import pyarrow.parquet as pq

from scripts.platformkit.showcase.common import FRONTEND, REPO, read_jsonl, receipt, unavailable

PRICE_SERIES = REPO / "data" / "cache" / "inplay_odds" / "mlb_price_series.parquet"
PAPER_PREDICTIONS = FRONTEND / "paper_predictions.jsonl"
COLUMNS = ["event_key", "ticker_or_slug", "market_type", "side", "ts", "prob",
           "game_date", "result_where_known"]
MAX_TICKS = 500
MAX_GAMES = 3


def _load_candidate_rows() -> Any | None:
    if not PRICE_SERIES.exists():
        return None
    tbl = pq.ParquetFile(PRICE_SERIES).read(columns=COLUMNS)
    mask = pc.and_(pc.equal(tbl.column("market_type"), "moneyline"),
                    pc.equal(tbl.column("side"), "home"))
    mask = pc.and_(mask, pc.and_(pc.is_valid(tbl.column("result_where_known")),
                                   pc.not_equal(tbl.column("result_where_known"), "")))
    sub = tbl.filter(mask)
    return sub if sub.num_rows else None


def _pick_games(sub) -> list[str]:
    """Rank ticker_or_slug groups by tick count, return top MAX_GAMES ids."""
    counts: dict[str, int] = {}
    for slug in sub.column("ticker_or_slug").to_pylist():
        if not slug or "dailies" in slug:
            continue
        counts[slug] = counts.get(slug, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    return [slug for slug, _ in ranked[:MAX_GAMES]]


def _downsample(rows: list[dict]) -> list[dict]:
    rows = sorted(rows, key=lambda r: r["ts"])
    if len(rows) <= MAX_TICKS:
        return rows
    step = len(rows) / MAX_TICKS
    idx = sorted({int(i * step) for i in range(MAX_TICKS)})
    return [rows[i] for i in idx]


def _game_label(slug: str) -> tuple[str, str, str]:
    """slug like 'mlb-stl-cin-2026-05-22' -> (team_a, team_b, date)."""
    parts = slug.split("-")
    team_a, team_b = parts[1].upper(), parts[2].upper()
    game_date = "-".join(parts[3:6])
    return team_a, team_b, game_date


def _paper_event_ids(sport: str) -> set[str]:
    """event_ids present in paper_predictions.jsonl for this sport (for the
    honest join attempt described in SPEC v1.1)."""
    ids = set()
    for row in read_jsonl(PAPER_PREDICTIONS):
        if row.get("sport") == sport and row.get("event_id"):
            ids.add(str(row["event_id"]))
    return ids


def build() -> dict:
    sub = _load_candidate_rows()
    if sub is None:
        return unavailable(f"no usable rows in {PRICE_SERIES}")

    game_slugs = _pick_games(sub)
    if not game_slugs:
        return unavailable("no finished-game groups found in price series")

    event_keys = sub.column("event_key").to_pylist()
    ticker_slugs = sub.column("ticker_or_slug").to_pylist()
    ts_col = sub.column("ts").to_pylist()
    prob_col = sub.column("prob").to_pylist()
    result_col = sub.column("result_where_known").to_pylist()
    game_date_col = sub.column("game_date").to_pylist()

    by_slug: dict[str, list[dict]] = {slug: [] for slug in game_slugs}
    for ek, slug, ts, prob, result, gdate in zip(
            event_keys, ticker_slugs, ts_col, prob_col, result_col, game_date_col):
        if slug not in by_slug:
            continue
        by_slug[slug].append({"ts": ts, "prob": prob, "result": result,
                               "event_key": ek, "game_date": gdate})

    paper_event_ids = _paper_event_ids("mlb")
    join_ok_games: list[str] = []
    join_note = ("model tick overlay: v2 -- event_id join to paper_predictions.jsonl "
                 "found no match (price series keys are venue slugs, e.g. "
                 "'mlb-stl-cin-2026-05-22'; paper_predictions.jsonl uses numeric "
                 "event ids); pregame/in-game model probs unavailable")

    games: dict[str, dict] = {}
    asof = date.today().isoformat()
    for slug in game_slugs:
        rows = _downsample(by_slug[slug])
        if not rows:
            continue
        team_a, team_b, game_date = _game_label(slug)
        results = {r["result"] for r in rows}
        outcome = results.pop() if len(results) == 1 else "MIXED"
        event_key = rows[0]["event_key"]
        if event_key in paper_event_ids:
            join_ok_games.append(slug)

        ticks = [{"t": r["ts"], "prob_market": r["prob"],
                  "prob_static": None, "prob_conditional": None} for r in rows]

        games[slug] = {
            "game": {"sport": "mlb", "label": f"{team_a} @ {team_b}",
                     "date": game_date, "result": outcome,
                     "pregame_prob": None, "pregame_note": join_note},
            "ticks": ticks,
            "receipt": receipt(
                claim=f"MLB in-play market probability series for {team_a} @ {team_b} "
                      f"({game_date}), {len(ticks)} ticks (downsampled)",
                value=len(ticks), label="MEASURED", artifact=PRICE_SERIES, asof=asof),
        }

    if not games:
        return unavailable("candidate games had no usable ticks after downsampling")

    notes = [join_note]
    if join_ok_games:
        notes.append(f"model tick overlay joined for: {', '.join(join_ok_games)}")

    return {"index": {"game_ids": list(games), "notes": notes}, "games": games}
