"""Line-history cross-book consensus claims (Depth-wave-3 final lane).

DESCRIPTIVE market-STRUCTURE claims from the raw scrape-capture archive at
data/cache/line_history/<sport>/<date>.jsonl -- NOT the odds.parquet archive
Lane C (market_book_dispersion_claims.py) already covers. Two axes, both
scoped to a BOUNDED recent window of day-files (never the full 257/151MB
per-sport archive):

  coverage_breadth    -- mean distinct books quoting per (game, market,
                          side, line) group, across ALL groups in the window.
  consensus_tightness -- mean spread (max odds - min odds) across books,
                          for groups with >=2 books only (single-book groups
                          contribute zero disagreement signal and are
                          excluded from this metric, counted honestly).

PREMISE GATE (checked fresh against 2026-07-16 day-files before building):
  tennis/2026-07-16.jsonl: 12,258 rows, 100% book=="pinnacle" -- a SINGLE
      SOURCE scrape, structurally no cross-book comparison is possible.
      Tennis is EXCLUDED (HONEST-REJECT), not silently zero-filled.
  soccer/2026-07-16.jsonl: 8,508 rows across 2 books (pinnacle 7560,
      espn:DraftKings 948) -- multi-book, buildable.
  soccer_intl/2026-07-16.jsonl: 3,462 rows across 3 books (pinnacle 1728,
      espn:DraftKings 870, kalshi 864) -- multi-book, buildable.

NEW vs Lane C (market_book_dispersion_claims.py): that module reads
data/domains/soccer/odds.parquet, a WIDE-format historical-CLOSE archive
fixed to exactly 2 named books (pinnacle, bet365) on the totals market only.
This module reads the INTRADAY SCRAPE-CAPTURE jsonl feed instead (row-per-
book-per-poll, all market types, book identities pinnacle/espn:DraftKings/
kalshi -- kalshi appears only here, not in odds.parquet), and adds
soccer_intl coverage Lane C never touched. Disjoint source, disjoint book
set, disjoint sport (soccer_intl) -- not a re-derivation of Lane C's axis.

GRAMMAR NOTE: same identity-formula-off-a-precomputed-snapshot pattern as
market_book_dispersion_claims.py (claims_validator.py:147-168 aggregate
grammar has no row-wise max/min-before-groupby; this module performs that
one aggregation itself and writes a snapshot whose columns the claim reads
by plain identity).

CONTRACT: kind="ranking", edge_claimed=False. entity_key="entity_id" ==
"{sport}|{market_type}". Streaming (line-by-line json.loads) day-file reads,
never a full-directory load; --window-days bounds how many recent day-files
per sport are read (default 14).

CAVEATS (also embedded per-claim): groups are NOT time-aligned to a single
instant -- a group spans every capture of that (game, market, side, line)
within the window, so spread reflects both cross-book disagreement AND
price movement across the window, not an instantaneous snapshot gap. This
characterizes scrape-feed coverage and consensus structure; it is NOT an
advantage or predictor; no market claim.

CLI:
    python -m scripts.platformkit.intel_validation.line_history_consensus_claims
then validate independently:
    python -m scripts.platformkit.intel_validation.claims_validator \
        data/cache/intel_claims/line_history_consensus_claims.jsonl \
        --output data/cache/intel_claims/line_history_consensus_claims_validation.json
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_LINE_HISTORY_DIR = REPO_ROOT / "data" / "cache" / "line_history"
_SNAPSHOT_PATH = REPO_ROOT / "data" / "cache" / "intel_claims" / "line_history_consensus_snapshot.parquet"
_CLAIMS_OUT = REPO_ROOT / "data" / "cache" / "intel_claims" / "line_history_consensus_claims.jsonl"

FLOOR_EVENTS = 50
DEFAULT_WINDOW_DAYS = 14
SEASON_WINDOW = "recent_window"
# tennis excluded: single-book (pinnacle-only) scrape feed, see module docstring
SPORTS = ("soccer", "soccer_intl")


def _recent_day_files(sport: str, window_days: int, base_dir: Path | None = None) -> list[Path]:
    """Sorted day-files for `sport`, capped to the last `window_days` --
    never globs/loads the whole per-sport directory into memory."""
    d = (base_dir or _LINE_HISTORY_DIR) / sport
    if not d.exists():
        return []
    files = sorted(p for p in d.glob("????-??-??.jsonl"))
    return files[-window_days:] if window_days > 0 else files


def stream_groups(sport: str, window_days: int = DEFAULT_WINDOW_DAYS,
                   base_dir: Path | None = None) -> dict[tuple, dict]:
    """Stream day-files line-by-line, accumulating per (game_id, market_type,
    side, line) group stats (book set + min/max odds) WITHOUT holding raw
    rows in memory -- O(n_groups) footprint, not O(n_rows)."""
    groups: dict[tuple, dict] = {}
    for path in _recent_day_files(sport, window_days, base_dir):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                odds = row.get("odds")
                book = row.get("book")
                market_type = row.get("market_type")
                if odds is None or book is None or market_type is None:
                    continue
                key = (row.get("game_id"), market_type, row.get("side"), row.get("line"))
                g = groups.get(key)
                if g is None:
                    groups[key] = {"books": {book}, "min_odds": odds, "max_odds": odds}
                    continue
                g["books"].add(book)
                if odds < g["min_odds"]:
                    g["min_odds"] = odds
                if odds > g["max_odds"]:
                    g["max_odds"] = odds
    return groups


def aggregate_sport(sport: str, groups: dict[tuple, dict]) -> list[dict[str, Any]]:
    """Roll per-group stats up to one row per market_type: coverage_breadth
    (mean n_books across ALL groups) + consensus_tightness (mean odds
    spread across multi-book groups only, floor applies to n_multibook)."""
    by_market: dict[str, dict[str, float]] = defaultdict(
        lambda: {"n_groups": 0, "n_books_sum": 0, "n_multibook": 0, "spread_sum": 0.0})
    for (_game_id, market_type, _side, _line), g in groups.items():
        b = by_market[market_type]
        n_books = len(g["books"])
        b["n_groups"] += 1
        b["n_books_sum"] += n_books
        if n_books >= 2:
            b["n_multibook"] += 1
            b["spread_sum"] += (g["max_odds"] - g["min_odds"])
    rows = []
    for market_type, b in by_market.items():
        rows.append({
            "sport": sport,
            "market_type": market_type,
            "n_events": int(b["n_groups"]),
            "n_multibook_events": int(b["n_multibook"]),
            "coverage_breadth_mean": (b["n_books_sum"] / b["n_groups"]) if b["n_groups"] else None,
            "consensus_tightness_mean": (b["spread_sum"] / b["n_multibook"]) if b["n_multibook"] else None,
        })
    return rows


def build_snapshot(window_days: int = DEFAULT_WINDOW_DAYS, base_dir: Path | None = None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for sport in SPORTS:
        groups = stream_groups(sport, window_days, base_dir)
        rows.extend(aggregate_sport(sport, groups))
    df = pd.DataFrame(rows, columns=["sport", "market_type", "n_events", "n_multibook_events",
                                      "coverage_breadth_mean", "consensus_tightness_mean"])
    df["entity_id"] = df["sport"] + "|" + df["market_type"]
    return df


def write_snapshot(snapshot: pd.DataFrame, out_path: Path = _SNAPSHOT_PATH) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot.to_parquet(out_path, index=False)
    return out_path


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


_CAVEATS = [
    "characterizes scrape-feed coverage and consensus structure (how many books "
    "quote an event, how much they disagree), NOT an advantage, NOT a beatable "
    "gap, NOT a predictor -- no market/ROI/dollar edge is claimed.",
    f"min_sample floor n_events>={FLOOR_EVENTS} (coverage) / n_multibook_events>="
    f"{FLOOR_EVENTS} (tightness) per (sport, market_type) group; below-floor "
    "groups are excluded and counted, never silently dropped.",
    "groups are NOT time-aligned to a single instant -- each group spans every "
    "capture of that (game, market, side, line) within the bounded window, so "
    "spread reflects cross-book disagreement AND price movement together.",
    "tennis excluded: its scrape feed is single-source (book==pinnacle only, "
    "checked fresh) -- no second book exists to compare against.",
    "disjoint from market_book_dispersion_claims.py (Lane C): that module reads "
    "the odds.parquet closing-price archive fixed to 2 named books on soccer "
    "totals only; this module reads the intraday scrape-capture feed across all "
    "market types, including soccer_intl and the kalshi book which odds.parquet "
    "does not carry.",
]


def _build_ranking_claim(snapshot: pd.DataFrame, metric_col: str, floor_col: str,
                          direction: str, label: str) -> dict[str, Any]:
    n_considered = len(snapshot)
    qualifiers = snapshot[snapshot[floor_col] >= FLOOR_EVENTS].dropna(subset=[metric_col]).copy()
    n_excluded = n_considered - len(qualifiers)
    ascending = direction == "asc"
    qualifiers = qualifiers.sort_values(metric_col, ascending=ascending).reset_index(drop=True)
    ranking = [
        {"rank": i, "entity_id": str(r.entity_id), "value": round(float(getattr(r, metric_col)), 6),
         "n_events": int(getattr(r, floor_col))}
        for i, r in enumerate(qualifiers.itertuples(index=False), start=1)
    ]
    return {
        "claim_id": f"line_history_consensus_{label}_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": f"Line-history {label.replace('_', ' ')} by (sport, market_type) group, "
                     f"{SEASON_WINDOW}?",
        "criteria": {
            "metric": metric_col, "formula": metric_col, "window": SEASON_WINDOW,
            "aggregate": None, "min_sample": {floor_col: FLOOR_EVENTS}, "direction": direction,
            "value_precision": 6, "entity_key": "entity_id",
        },
        "ranking": ranking,
        "source_files": [_rel(_SNAPSHOT_PATH)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": list(_CAVEATS),
    }


def build_all_claims(snapshot: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        _build_ranking_claim(snapshot, "coverage_breadth_mean", "n_events", "desc", "coverage_breadth"),
        _build_ranking_claim(snapshot, "consensus_tightness_mean", "n_multibook_events", "asc", "tightest_consensus"),
    ]


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit line-history cross-book consensus DESCRIPTIVE claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS,
                         help="most-recent day-files per sport to read (bounded, never full archive)")
    args = parser.parse_args(argv)

    snapshot = build_snapshot(window_days=args.window_days)
    snapshot_path = write_snapshot(snapshot)
    claims = build_all_claims(snapshot)
    out_path = write_claims(claims, Path(args.output))
    for c in claims:
        top = c["ranking"][0] if c["ranking"] else None
        print(f"{c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']} n_ranked={len(c['ranking'])} "
              f"top={top}")
    print(f"wrote snapshot ({len(snapshot)} groups) -> {snapshot_path}")
    print(f"wrote {len(claims)} claims -> {out_path}")
    try:
        import psutil
        rss_mb = psutil.Process().memory_info().rss / 1e6
        print(f"peak RSS (approx, current at end of run): {rss_mb:.1f} MB")
    except ImportError:
        pass
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
