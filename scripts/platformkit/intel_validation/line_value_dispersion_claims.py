"""Cross-book implied-probability dispersion claims (line_value_dispersion).

DESCRIPTIVE market-microstructure claims only: how much do books DISAGREE on
the devigged implied probability of the same (game, market_type, side, line)
within a bounded recent window? This is NOT an advantage, NOT a beatable gap,
NOT a predictor -- edge_claimed is always False, and every claim's caveats
state plainly: "descriptive dispersion, not a tradable signal". See
.claude/rules/no-edge-claims.md.

SOURCE: data/cache/line_history/<sport>/<date>.jsonl -- the intraday
scrape-capture archive (one row per book per poll), STREAMED line-by-line
per day-file with a bounded --window-days (never a full-directory load; see
the LAPTOP RAM RULE in CLAUDE.md). For each (game_id, market_type, side,
line) group, the LAST devigged_prob seen per book within the window is kept
(one value per book -- a chatty book's own repeated captures never inflate
the spread, only genuinely distinct books contribute). dispersion =
max(prob) - min(prob) across those per-book values, for groups with >=2
books only (single-book groups have no cross-book comparison and are
excluded from dispersion entirely, counted honestly).

PREMISE GATE (checked fresh against 2026-07-16 day-files before building):
  mlb:          7,496 rows / 4 books (kalshi 4770, fanduel 1368, pinnacle
                954, espn:DraftKings 404) -- multi-book, buildable. NOTE:
                this is the line_history SCRAPE feed, disjoint from
                odds.parquet's single-book sbro_archive (see
                market_book_dispersion_claims.py) -- kalshi-vs-book IS
                present here.
  wnba:         7,692 rows / 4 books (espn:DraftKings 2514, kalshi 1792,
                fanduel 1712, pinnacle 1674) -- multi-book, buildable.
  soccer:       8,508 rows / 2 books (pinnacle 7560, espn:DraftKings 948)
                -- multi-book, buildable.
  soccer_intl:  3,462 rows / 3 books (pinnacle 1728, espn:DraftKings 870,
                kalshi 864) -- multi-book, buildable.
  tennis:       12,258 rows, 100% book=="pinnacle" -- SINGLE SOURCE, no
                cross-book comparison possible. EXCLUDED (honest-reject,
                same finding as line_history_consensus_claims.py), not
                silently zero-filled. Any (sport, market_type) that
                contributes zero multi-book groups falls out of the
                snapshot the same way -- no special-casing needed beyond
                the SPORTS allowlist below.

GRAMMAR NOTE: median/p90 are NOT in claims_validator's per-group aggregate
grammar (sum/mean/count/count_distinct only -- claims_validator.py:105,
safe_formula.py:105). Same escape hatch as market_book_dispersion_claims.py
/ line_history_consensus_claims.py: this module performs the one
non-whitelisted aggregation step itself (median, p90) and writes a snapshot
parquet with the result already baked in; each claim's criteria.formula is
then a plain IDENTITY column read off that snapshot (aggregate=None).

CONTRACT: kind="ranking", edge_claimed=False. entity_key="entity_id" ==
"{sport}|{market_type}". min_sample floor n_events>=50 per group (n_events
here counts only multi-book groups -- the ones dispersion is computed from).

CLI:
    python -m scripts.platformkit.intel_validation.line_value_dispersion_claims
then validate independently:
    python -m scripts.platformkit.intel_validation.claims_validator \
        data/cache/intel_claims/line_value_dispersion_claims.jsonl \
        --output data/cache/intel_claims/line_value_dispersion_claims_validation.json
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_LINE_HISTORY_DIR = REPO_ROOT / "data" / "cache" / "line_history"
_SNAPSHOT_PATH = REPO_ROOT / "data" / "cache" / "intel_claims" / "line_value_dispersion_snapshot.parquet"
_CLAIMS_OUT = REPO_ROOT / "data" / "cache" / "intel_claims" / "line_value_dispersion_claims.jsonl"

FLOOR_EVENTS = 50
DEFAULT_WINDOW_DAYS = 14
SEASON_WINDOW = "recent_window"
# tennis excluded: single-book (pinnacle-only) scrape feed, see module docstring
SPORTS = ("mlb", "wnba", "soccer", "soccer_intl")


def _recent_day_files(sport: str, window_days: int, base_dir: Path | None = None) -> list[Path]:
    """Sorted day-files for `sport`, capped to the last `window_days` --
    never globs/loads the whole per-sport directory into memory."""
    d = (base_dir or _LINE_HISTORY_DIR) / sport
    if not d.exists():
        return []
    files = sorted(p for p in d.glob("????-??-??.jsonl"))
    return files[-window_days:] if window_days > 0 else files


def stream_groups(sport: str, window_days: int = DEFAULT_WINDOW_DAYS,
                   base_dir: Path | None = None) -> dict[tuple, dict[str, float]]:
    """Stream day-files line-by-line -> {(game_id, market_type, side, line):
    {book: latest devigged_prob}}. Last capture per book WITHIN the window
    wins (a book quoted twice contributes ONE value, so its own price drift
    over the window can never masquerade as cross-book disagreement).
    O(n_groups * n_books) footprint, not O(n_rows)."""
    groups: dict[tuple, dict[str, float]] = {}
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
                prob = row.get("devigged_prob")
                book = row.get("book")
                market_type = row.get("market_type")
                if prob is None or book is None or market_type is None:
                    continue
                key = (row.get("game_id"), market_type, row.get("side"), row.get("line"))
                groups.setdefault(key, {})[book] = prob
    return groups


def aggregate_sport(sport: str, groups: dict[tuple, dict[str, float]]) -> list[dict[str, Any]]:
    """Roll multi-book groups up to one row per market_type: n_events (multi-
    book group count), n_books_mean, median/p90 cross-book prob dispersion.
    Single-book groups carry no cross-book signal and are excluded here,
    same honest-empty spirit as market_book_dispersion_claims.py's
    mlb_dispersion (never fabricated, never silently zero-filled)."""
    by_market: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for (_game_id, market_type, _side, _line), book_probs in groups.items():
        n_books = len(book_probs)
        if n_books < 2:
            continue
        vals = list(book_probs.values())
        by_market[market_type].append((n_books, max(vals) - min(vals)))
    rows = []
    for market_type, items in by_market.items():
        n_books_arr = np.array([i[0] for i in items], dtype=float)
        disp_arr = np.array([i[1] for i in items], dtype=float)
        rows.append({
            "sport": sport,
            "market_type": market_type,
            "n_events": len(items),
            "n_books_mean": float(n_books_arr.mean()),
            "median_prob_dispersion": float(np.median(disp_arr)),
            "p90_prob_dispersion": float(np.percentile(disp_arr, 90)),
        })
    return rows


def build_snapshot(window_days: int = DEFAULT_WINDOW_DAYS, base_dir: Path | None = None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for sport in SPORTS:
        groups = stream_groups(sport, window_days, base_dir)
        rows.extend(aggregate_sport(sport, groups))
    df = pd.DataFrame(rows, columns=["sport", "market_type", "n_events", "n_books_mean",
                                      "median_prob_dispersion", "p90_prob_dispersion"])
    df["entity_id"] = df["sport"] + "|" + df["market_type"]
    return df


def write_snapshot(snapshot: pd.DataFrame, out_path: Path = _SNAPSHOT_PATH) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot.to_parquet(out_path, index=False)
    return out_path


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


_CAVEATS = [
    "descriptive dispersion, not a tradable signal -- characterizes how much "
    "books disagree on implied probability; not an advantage, not a "
    "beatable gap, not a predictor -- no market/roi/dollar edge is claimed.",
    f"min_sample floor n_events>={FLOOR_EVENTS} multi-book groups per "
    "(sport, market_type) group; below-floor groups are excluded and "
    "counted, never silently dropped.",
    "dispersion = max(devigged_prob) - min(devigged_prob) across books, "
    "using the LAST capture per book within the bounded window (one value "
    "per book, so a single book's own price movement never inflates "
    "cross-book spread).",
    "groups with fewer than 2 distinct books quoting have no cross-book "
    "comparison and are excluded from dispersion entirely, not zero-filled.",
    "tennis excluded: its line_history scrape feed is single-source "
    "(book==pinnacle only, checked fresh) -- no second book exists to "
    "compare against.",
]


def _build_ranking_claim(snapshot: pd.DataFrame, metric_col: str, label: str) -> dict[str, Any]:
    n_considered = len(snapshot)
    qualifiers = snapshot[snapshot["n_events"] >= FLOOR_EVENTS].dropna(subset=[metric_col]).copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers = qualifiers.sort_values(metric_col, ascending=False).reset_index(drop=True)
    ranking = [
        {"rank": i, "entity_id": str(r.entity_id), "value": round(float(getattr(r, metric_col)), 6),
         "n_events": int(r.n_events), "n_books_mean": round(float(r.n_books_mean), 3)}
        for i, r in enumerate(qualifiers.itertuples(index=False), start=1)
    ]
    return {
        "claim_id": f"line_value_dispersion_{label}_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": f"Cross-book implied-probability {label.replace('_', ' ')} by (sport, "
                     f"market_type) group, {SEASON_WINDOW}?",
        "criteria": {
            "metric": metric_col, "formula": metric_col, "window": SEASON_WINDOW,
            "aggregate": None, "min_sample": {"n_events": FLOOR_EVENTS}, "direction": "desc",
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
        _build_ranking_claim(snapshot, "median_prob_dispersion", "median_dispersion"),
        _build_ranking_claim(snapshot, "p90_prob_dispersion", "p90_dispersion"),
    ]


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit cross-book implied-prob dispersion DESCRIPTIVE claims")
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
