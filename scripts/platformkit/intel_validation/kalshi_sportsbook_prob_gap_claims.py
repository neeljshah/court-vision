"""Kalshi-vs-sportsbook implied-probability gap claims (kalshi_sportsbook_prob_gap).

DESCRIPTIVE market-structure claims only: for the SAME (game_id, market_type,
side, line) group, how far apart is kalshi's devigged implied probability
from the devigged sportsbook CONSENSUS (mean of every non-kalshi book quoting
that group)? This is NOT an advantage, NOT a beatable gap, NOT a predictor --
edge_claimed is always False, and every claim's caveats say so plainly. See
.claude/rules/no-edge-claims.md.

SOURCE: data/cache/line_history/<sport>/<date>.jsonl -- the SAME intraday
scrape-capture archive line_value_dispersion_claims.py / line_history_
consensus_claims.py already read (one row per book per poll, `devigged_prob`
precomputed per row -- no devig math performed here). STREAMED line-by-line
per day-file with a bounded --window-days (never a full-directory load; see
the LAPTOP RAM RULE in CLAUDE.md). For each (game_id, market_type, side,
line) group, the LAST devigged_prob seen per book within the window is kept
(one value per book, so a chatty book's own repeated captures never distort
the gap). A group only contributes a gap if it has BOTH a kalshi quote AND
>=1 non-kalshi book quote; groups with only kalshi, or with no kalshi at all,
carry no cross-venue gap and are excluded from the metric entirely (counted
honestly, never zero-filled).

gap = kalshi_prob - mean(non_kalshi_book_probs)  (signed: positive = kalshi
runs higher than the sportsbook consensus). abs_gap = abs(gap).

EVIDENCE NOTE: this worktree is isolated -- data/ is absent here, so the
sport/book distribution cannot be checked fresh in this session (unlike the
sibling modules' 2026-07-16 premise gates, which were built in a session
that had data/ present). SPORTS are discovered dynamically from whatever
subdirectories exist under data/cache/line_history/ at run time rather than
hardcoded, so this module makes no unverified claim about which sports carry
a kalshi feed -- a sport/market with zero kalshi-vs-book groups simply
produces zero rows and is excluded by the floor, same honest-empty idiom as
tennis in line_value_dispersion_claims.py. The real run (and real sport/book
counts) happens on the RunPod post-merge.

GRAMMAR NOTE: mean-of-per-book-then-diff is not expressible in claims_
validator's per-group aggregate grammar (sum/mean/count/count_distinct only
-- claims_validator.py:105, safe_formula.py:105). Same escape hatch as
line_value_dispersion_claims.py: this module performs the one non-
whitelisted aggregation step itself (group-then-diff, then mean per market)
and writes a snapshot parquet with the result already baked in; each claim's
criteria.formula is then a plain IDENTITY column read off that snapshot
(aggregate=None).

CONTRACT: kind="ranking", edge_claimed=False. entity_key="entity_id" ==
"{sport}|{market_type}". min_sample floor n_events>=50 per group (n_events
here counts only kalshi-vs-book comparable groups).

CLI:
    python -m scripts.platformkit.intel_validation.kalshi_sportsbook_prob_gap_claims
then validate independently:
    python -m scripts.platformkit.intel_validation.claims_validator \
        data/cache/intel_claims/kalshi_sportsbook_prob_gap_claims.jsonl \
        --output data/cache/intel_claims/kalshi_sportsbook_prob_gap_claims_validation.json
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
_SNAPSHOT_PATH = REPO_ROOT / "data" / "cache" / "intel_claims" / "kalshi_sportsbook_prob_gap_snapshot.parquet"
_CLAIMS_OUT = REPO_ROOT / "data" / "cache" / "intel_claims" / "kalshi_sportsbook_prob_gap_claims.jsonl"

FLOOR_EVENTS = 50
DEFAULT_WINDOW_DAYS = 14
SEASON_WINDOW = "recent_window"
KALSHI_BOOK = "kalshi"


def _discover_sports(base_dir: Path | None = None) -> list[str]:
    """Sport subdirectories present under the line_history dir -- discovered,
    never hardcoded, so this module asserts nothing about which sports carry
    a kalshi feed (see EVIDENCE NOTE in module docstring)."""
    d = base_dir or _LINE_HISTORY_DIR
    if not d.exists():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir())


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
    wins (a book quoted twice contributes ONE value)."""
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
    """Roll kalshi-vs-book-comparable groups up to one row per market_type:
    n_events (comparable group count), mean_gap (signed, kalshi minus
    sportsbook consensus), mean_abs_gap. Groups without both a kalshi quote
    and >=1 non-kalshi quote carry no gap and are excluded here, never
    zero-filled (honest-empty idiom, same as line_value_dispersion_claims.py
    single-book exclusion)."""
    by_market: dict[str, list[float]] = defaultdict(list)
    for (_game_id, market_type, _side, _line), book_probs in groups.items():
        if KALSHI_BOOK not in book_probs:
            continue
        book_vals = [v for b, v in book_probs.items() if b != KALSHI_BOOK]
        if not book_vals:
            continue
        gap = book_probs[KALSHI_BOOK] - float(np.mean(book_vals))
        by_market[market_type].append(gap)
    rows = []
    for market_type, gaps in by_market.items():
        arr = np.array(gaps, dtype=float)
        rows.append({
            "sport": sport,
            "market_type": market_type,
            "n_events": len(arr),
            "mean_gap": float(arr.mean()),
            "mean_abs_gap": float(np.abs(arr).mean()),
        })
    return rows


def build_snapshot(window_days: int = DEFAULT_WINDOW_DAYS, base_dir: Path | None = None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for sport in _discover_sports(base_dir):
        groups = stream_groups(sport, window_days, base_dir)
        rows.extend(aggregate_sport(sport, groups))
    df = pd.DataFrame(rows, columns=["sport", "market_type", "n_events", "mean_gap", "mean_abs_gap"])
    df["entity_id"] = df["sport"] + "|" + df["market_type"]
    return df


def write_snapshot(snapshot: pd.DataFrame, out_path: Path = _SNAPSHOT_PATH) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot.to_parquet(out_path, index=False)
    return out_path


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


_CAVEATS = [
    "descriptive cross-venue probability gap, not a tradable signal -- "
    "characterizes how far kalshi's implied probability sits from the "
    "sportsbook consensus for the same event; not an advantage, not a "
    "beatable gap, not a predictor -- no market/roi/dollar edge is claimed.",
    f"min_sample floor n_events>={FLOOR_EVENTS} kalshi-vs-book comparable "
    "groups per (sport, market_type) group; below-floor groups are "
    "excluded and counted, never silently dropped.",
    "gap = kalshi devigged_prob - mean(non-kalshi book devigged_probs), "
    "using the LAST capture per book within the bounded window (one value "
    "per book, so a single book's own price movement never inflates the "
    "cross-venue gap).",
    "groups without both a kalshi quote and at least one non-kalshi book "
    "quote have no cross-venue gap and are excluded entirely, not "
    "zero-filled.",
    "sports/markets are discovered from data/cache/line_history/ at run "
    "time, not hardcoded -- a sport with no kalshi feed simply contributes "
    "zero comparable groups and drops out at the floor (see EVIDENCE NOTE, "
    "module docstring: this worktree has no data/ to check fresh).",
]


def _build_ranking_claim(snapshot: pd.DataFrame, metric_col: str, label: str) -> dict[str, Any]:
    n_considered = len(snapshot)
    qualifiers = snapshot[snapshot["n_events"] >= FLOOR_EVENTS].dropna(subset=[metric_col]).copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers = qualifiers.sort_values(metric_col, ascending=False).reset_index(drop=True)
    ranking = [
        {"rank": i, "entity_id": str(r.entity_id), "value": round(float(getattr(r, metric_col)), 6),
         "n_events": int(r.n_events)}
        for i, r in enumerate(qualifiers.itertuples(index=False), start=1)
    ]
    return {
        "claim_id": f"kalshi_sportsbook_prob_gap_{label}_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": f"Kalshi-vs-sportsbook implied-probability {label.replace('_', ' ')} by "
                     f"(sport, market_type) group, {SEASON_WINDOW}?",
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
    claims = [
        _build_ranking_claim(snapshot, "mean_abs_gap", "widest_abs_gap"),
        _build_ranking_claim(snapshot, "mean_gap", "signed_gap"),
    ]
    # An empty ranking means nothing cleared the floor -- claiming nothing is
    # not a claim, skip emission honestly (domains/mlb/profiles/claims.py
    # build_all_claims idiom) rather than shipping an UNVERIFIABLE row.
    kept = [c for c in claims if c["ranking"]]
    for c in claims:
        if not c["ranking"]:
            print(f"SKIP {c['claim_id']}: 0 of {c['n_considered']} groups clear "
                  f"min_sample floor -- claim not emitted")
    return kept


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit kalshi-vs-sportsbook prob-gap DESCRIPTIVE claims")
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
    if not claims:
        print("no claims cleared the floor -- nothing to validate")
        return 0

    from scripts.platformkit.intel_validation.validate_store import validate_and_write
    result = validate_and_write(str(out_path))
    print(f"validation: {result['n_verified']}/{result['n_claims']} verified, "
          f"{result['n_mismatch']} mismatch, {result['n_unverifiable']} unverifiable "
          f"-> {result['out']}")
    return 0 if (result["n_mismatch"] == 0 and result["n_unverifiable"] == 0) else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
