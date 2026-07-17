"""MLB injury-recency ranking claims (depth-wave-1, lane 2).

Emits TWO full-population descriptive rankings over
data/domains/mlb/edge_facts_injuries.parquet (2,724 rows: fact_kind/sport/
subject_id/game_date/value_text/source/availability_ts/confidence):

  1. recency ranking: days_since_latest (ascending -- most recent first)
  2. fact-volume ranking: n_facts (descending -- most-covered first)

SNAPSHOT REFERENCE POINT: days_since_latest is measured against the
CORPUS max(game_date) (the latest fact date anywhere in the parquet), NOT
today's wall-clock date -- this makes the snapshot deterministic and
reproducible: the independent validator recomputes straight from the same
on-disk snapshot parquet and must agree byte-for-byte, which "today" would
break the day after this runs. Precedent: tennis_hold_claims.py's per-tour
snapshot parquet (data/cache/intel_claims/tennis_hold_snapshot_*.parquet)
feeding the SAME plain (non-aggregate) claims_validator.py formula path.

MIN-SAMPLE FLOOR: n_facts >= 2 -- a single injury-note mention is not a
"how much is being written about this player" signal; STATED explicitly in
each claim's min_sample, below-floor subjects counted in
n_excluded_below_floor, never silently dropped.

DESCRIPTIVE ONLY: a churn record of the injury-fact corpus, NOT an
availability forecast, NOT a market claim. edge_claimed is always False.

NETWORK: zero. Pure pandas over an already-materialized parquet.

CLI:
    python -m scripts.platformkit.intel_validation.mlb_injury_recency_claims
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[3]

_SOURCE = REPO_ROOT / "data" / "domains" / "mlb" / "edge_facts_injuries.parquet"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_SNAPSHOT_OUT = _OUT_DIR / "mlb_injury_recency_snapshot.parquet"
_CLAIMS_OUT = _OUT_DIR / "mlb_injury_recency_claims.jsonl"

MIN_N_FACTS = 2

_CAVEATS = [
    "recency is measured as-of the CORPUS snapshot (max game_date across all "
    "facts at build time), not today's wall-clock date -- deterministic and "
    "reproducible for the independent validator, not a live countdown.",
    "descriptive churn record of the injury-fact corpus only -- NOT an "
    "availability forecast, NOT a prediction the subject will play or sit.",
    f"min_sample floor n_facts>={MIN_N_FACTS} -- a single mention is not a "
    "meaningful coverage signal; below-floor subjects are counted in "
    "n_excluded_below_floor, never dropped from n_considered.",
    "no market/$ edge claimed.",
]


def build_snapshot() -> tuple[Path, pd.DataFrame]:
    """One row per subject_id: days_since_latest (vs corpus max game_date)
    and n_facts (total fact rows for that subject). Written to
    _SNAPSHOT_OUT so claims_validator.py recomputes from the SAME on-disk
    artifact, independent of this module."""
    facts = pd.read_parquet(_SOURCE)
    facts["game_date"] = pd.to_datetime(facts["game_date"])
    corpus_max = facts["game_date"].max()

    grouped = facts.groupby("subject_id", as_index=False).agg(
        latest_date=("game_date", "max"),
        n_facts=("game_date", "size"),
    )
    grouped["days_since_latest"] = (corpus_max - grouped["latest_date"]).dt.days
    grouped["n_facts"] = grouped["n_facts"].astype("int64")

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_cols = grouped[["subject_id", "days_since_latest", "n_facts"]].copy()
    pq.write_table(pa.Table.from_pandas(write_cols, preserve_index=False), _SNAPSHOT_OUT)
    return _SNAPSHOT_OUT, write_cols


def _rel_source(out_path: Path) -> str:
    return str(out_path.relative_to(REPO_ROOT)).replace("\\", "/")


def build_ranking_claims() -> list[dict[str, Any]]:
    out_path, snapshot = build_snapshot()
    n_considered = len(snapshot)
    n_excluded = int((snapshot["n_facts"] < MIN_N_FACTS).sum())
    qualifiers = snapshot[snapshot["n_facts"] >= MIN_N_FACTS].copy()
    rel_source = _rel_source(out_path)
    computed_at = datetime.now(timezone.utc).isoformat()

    def _rank(sorted_df: pd.DataFrame, value_col: str) -> list[dict[str, Any]]:
        ranking = []
        for i, row in enumerate(sorted_df.itertuples(index=False), start=1):
            ranking.append({
                "rank": i,
                "subject_id": str(row.subject_id),
                "value": round(float(getattr(row, value_col)), 4),
                "n": int(row.n_facts),
            })
        return ranking

    recency_sorted = qualifiers.sort_values("days_since_latest", ascending=True).reset_index(drop=True)
    recency_claim = {
        "claim_id": "mlb_injury_recency_days_since_latest",
        "kind": "ranking",
        "question": "Which MLB subjects have the most recent injury-fact coverage in the corpus snapshot?",
        "criteria": {
            "metric": "days_since_latest",
            "formula": "days_since_latest",
            "window": "corpus_snapshot",
            "min_sample": {"n_facts": MIN_N_FACTS},
            "direction": "asc",
            "value_precision": 4,
            "entity_key": "subject_id",
        },
        "ranking": _rank(recency_sorted, "days_since_latest"),
        "source_files": [rel_source],
        "computed_at": computed_at,
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": _CAVEATS,
    }

    volume_sorted = qualifiers.sort_values("n_facts", ascending=False).reset_index(drop=True)
    volume_claim = {
        "claim_id": "mlb_injury_recency_n_facts",
        "kind": "ranking",
        "question": "Which MLB subjects have the most injury-fact rows in the corpus snapshot?",
        "criteria": {
            "metric": "n_facts",
            "formula": "n_facts",
            "window": "corpus_snapshot",
            "min_sample": {"n_facts": MIN_N_FACTS},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "subject_id",
        },
        "ranking": _rank(volume_sorted, "n_facts"),
        "source_files": [rel_source],
        "computed_at": computed_at,
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": _CAVEATS,
    }

    return [recency_claim, volume_claim]


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit MLB injury-recency ranking claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims = build_ranking_claims()
    out_path = write_claims(claims, Path(args.output))
    for claim in claims:
        print(
            f"{claim['claim_id']}: n_considered={claim['n_considered']} "
            f"n_excluded_below_floor={claim['n_excluded_below_floor']} "
            f"top1={claim['ranking'][0] if claim['ranking'] else None}"
        )
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
