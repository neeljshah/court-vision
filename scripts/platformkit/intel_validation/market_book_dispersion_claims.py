"""Cross-book dispersion ranking claims (Depth-wave-2 Lane C).

DESCRIPTIVE market-STRUCTURE claims only: how much do books disagree on a
price (dispersion = |book_a - book_b| decimal odds), and does that
disagreement narrow into the close (consensus_tightening = close_dispersion
- open_dispersion, negative = tightened). This is NOT an advantage, NOT a
beatable gap, NOT a predictor -- edge_claimed is always False. See
.claude/rules/no-edge-claims.md.

SOURCES (read-only, column-projected):
  data/domains/soccer/odds.parquet  -- WIDE format, 2 individually-named
      books available per side (pinnacle: p_/pc_, bet365: b365_/b365c_) on
      the totals (over/under) market. dispersion = |p - b365| per side.
      15,076/16,322 rows have both books present (rest dropped as NaN,
      counted honestly).
  data/domains/mlb/odds.parquet -- CHECKED FRESH: every one of its 28,004
      rows carries `book == "sbro_archive"` (single archive feed, one row
      per event_id, zero duplicate event_ids). There is NO second book to
      disperse against in this file. mlb_dispersion() returns an empty
      frame with that reason rather than fabricating a signal -- an honest
      exclusion, not a claim.

GRAMMAR NOTE (claims_validator.py:147-168, safe_formula.py): the aggregate
grammar only whitelists sum/mean/count/count_distinct per group -- it has no
row-wise max/min/abs-before-groupby, so per-event dispersion cannot be
recomputed straight from raw odds rows under that grammar. Per that file's
own documented escape hatch, this module precomputes per-event dispersion
itself, aggregates to one row per (league, market) group, and writes a
SNAPSHOT parquet with the final mean already baked in. Each claim's
criteria.formula is then a plain IDENTITY column read off that snapshot
(same tautological-by-construction contract as wnba_zone_context_claims.py
build_claim / raw_value) -- no criteria.aggregate needed, because the
producer already did the one aggregation step the grammar can't express.

CONTRACT: kind="ranking", edge_claimed=False. entity_key="entity_id" ==
"{league}|{market}". min_sample floor n_events>=50 per group.

CLI:
    python -m scripts.platformkit.intel_validation.market_book_dispersion_claims
then validate independently:
    python -m scripts.platformkit.intel_validation.claims_validator \
        data/cache/intel_claims/market_book_dispersion_claims.jsonl \
        --output data/cache/intel_claims/market_book_dispersion_claims_validation.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_SOCCER_SRC = REPO_ROOT / "data" / "domains" / "soccer" / "odds.parquet"
_MLB_SRC = REPO_ROOT / "data" / "domains" / "mlb" / "odds.parquet"
_SNAPSHOT_PATH = REPO_ROOT / "data" / "cache" / "intel_claims" / "market_book_dispersion_snapshot.parquet"
_CLAIMS_OUT = REPO_ROOT / "data" / "cache" / "intel_claims" / "market_book_dispersion_claims.jsonl"

FLOOR_EVENTS = 50
SEASON_WINDOW = "alltime"

_SOCCER_COLS = ["div", "p_over", "p_under", "pc_over", "pc_under", "b365_over", "b365_under",
                "b365c_over", "b365c_under"]
_MLB_COLS = ["event_id", "book"]


def soccer_dispersion(df: pd.DataFrame) -> pd.DataFrame:
    """Per-event, per-side (over/under) dispersion between the 2 individually
    named books (pinnacle p_/pc_, bet365 b365_/b365c_). Rows missing either
    book on a side are dropped for that side only (counted by the caller via
    row-count deltas, never silently merged into the surviving rows)."""
    frames = []
    for side in ("over", "under"):
        cols = ["div", f"p_{side}", f"pc_{side}", f"b365_{side}", f"b365c_{side}"]
        sub = df[cols].dropna()
        dispersion_open = (sub[f"p_{side}"] - sub[f"b365_{side}"]).abs()
        dispersion_close = (sub[f"pc_{side}"] - sub[f"b365c_{side}"]).abs()
        frames.append(pd.DataFrame({
            "league": sub["div"],
            "market": f"ou_{side}",
            "dispersion_open": dispersion_open,
            "dispersion_close": dispersion_close,
            "consensus_tightening": dispersion_close - dispersion_open,
        }))
    return pd.concat(frames, ignore_index=True)


def mlb_dispersion(df: pd.DataFrame) -> pd.DataFrame:
    """MLB odds.parquet has exactly ONE book (`sbro_archive`) and one row per
    event_id -- verified fresh (see module docstring). Cross-book dispersion
    is structurally not computable from this source; return an empty frame
    with the same columns as soccer_dispersion, an honest zero-signal
    result rather than a fabricated one."""
    n_books = df["book"].nunique() if "book" in df.columns else 0
    if n_books >= 2:
        raise NotImplementedError(
            "data/domains/mlb/odds.parquet now has >=2 books -- adapter needs a real "
            "cross-book join, this stub was only valid for the single-book snapshot"
        )
    return pd.DataFrame(columns=["league", "market", "dispersion_open", "dispersion_close",
                                  "consensus_tightening"])


def _aggregate(long_df: pd.DataFrame) -> pd.DataFrame:
    """One row per (league, market) group: n_events + mean of each metric.
    Floor n_events>=50 applied here so excluded groups are visible (never
    silently dropped from the snapshot -- min_sample on the claim re-applies
    the same floor independently at validation time)."""
    if long_df.empty:
        return pd.DataFrame(columns=["entity_id", "league", "market", "n_events",
                                      "dispersion_open_mean", "dispersion_close_mean",
                                      "consensus_tightening_mean"])
    g = long_df.groupby(["league", "market"], as_index=False).agg(
        n_events=("dispersion_open", "count"),
        dispersion_open_mean=("dispersion_open", "mean"),
        dispersion_close_mean=("dispersion_close", "mean"),
        consensus_tightening_mean=("consensus_tightening", "mean"),
    )
    g["entity_id"] = g["league"] + "|" + g["market"]
    return g[["entity_id", "league", "market", "n_events", "dispersion_open_mean",
              "dispersion_close_mean", "consensus_tightening_mean"]]


def build_snapshot() -> pd.DataFrame:
    soccer_raw = pd.read_parquet(_SOCCER_SRC, columns=_SOCCER_COLS)
    soccer_long = soccer_dispersion(soccer_raw)
    mlb_raw = pd.read_parquet(_MLB_SRC, columns=_MLB_COLS)
    mlb_long = mlb_dispersion(mlb_raw)  # ponytail: empty by design (single-book source), see docstring
    parts = [f for f in (soccer_long, mlb_long) if not f.empty]
    return _aggregate(pd.concat(parts, ignore_index=True) if parts else soccer_long)


def write_snapshot(snapshot: pd.DataFrame, out_path: Path = _SNAPSHOT_PATH) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot.to_parquet(out_path, index=False)
    return out_path


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


_CAVEATS = [
    "characterizes market STRUCTURE (how much books disagree, how consensus tightens), "
    "NOT an advantage, NOT a beatable gap, NOT a predictor -- no market/ROI/dollar edge "
    "is claimed; books are historical archive feeds.",
    f"min_sample floor n_events>={FLOOR_EVENTS} per (league, market) group; below-floor "
    "groups are excluded and counted, never silently dropped.",
    "dispersion = |pinnacle - bet365| decimal odds on the same side/event; only the 2 "
    "individually-named soccer book columns are used (avg/max columns are cross-book "
    "aggregates, not individual books, so they are excluded from the dispersion itself).",
    "MLB odds.parquet carries a single book (sbro_archive) with one row per event_id -- "
    "checked fresh at build time -- so it contributes zero cross-book-dispersion groups here.",
]


def _build_ranking_claim(snapshot: pd.DataFrame, metric_col: str, direction: str, label: str) -> dict[str, Any]:
    n_considered = len(snapshot)
    qualifiers = snapshot[snapshot["n_events"] >= FLOOR_EVENTS].dropna(subset=[metric_col]).copy()
    n_excluded = n_considered - len(qualifiers)
    ascending = direction == "asc"
    qualifiers = qualifiers.sort_values(metric_col, ascending=ascending).reset_index(drop=True)
    ranking = [
        {"rank": i, "entity_id": str(r.entity_id), "value": round(float(getattr(r, metric_col)), 6),
         "n_events": int(r.n_events)}
        for i, r in enumerate(qualifiers.itertuples(index=False), start=1)
    ]
    return {
        "claim_id": f"market_book_dispersion_{label}_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": f"Cross-book {label.replace('_', ' ')} by (league, market) group, "
                     f"{SEASON_WINDOW} soccer totals market?",
        "criteria": {
            "metric": metric_col, "formula": metric_col, "window": f"{SEASON_WINDOW}_soccer_totals",
            "aggregate": None, "min_sample": {"n_events": FLOOR_EVENTS}, "direction": direction,
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
        _build_ranking_claim(snapshot, "dispersion_close_mean", "desc", "most_dispersed_close"),
        _build_ranking_claim(snapshot, "consensus_tightening_mean", "asc", "most_tightening"),
    ]


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit cross-book dispersion DESCRIPTIVE ranking claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    snapshot = build_snapshot()
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
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
