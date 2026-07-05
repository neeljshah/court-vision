"""Pillar-snapshot writer for the quality-index ranking claims (split out of
quality_validity_gate_claims.py to stay under the 300-LOC/file cap).

quality_indices_score.score_index() already materializes one pillar_<PILLAR>
column per player -- the exact percentile-mean each DECLARED weight
multiplies (per-player pillar-dropout renormalization: weighted_sum /
available_weight). For a full-coverage row (coverage==1.0) that collapses to
a plain fixed-weight linear sum, so write_pillar_snapshot() writes those
already-materialized pillar columns to a flat parquet and
build_pillar_formula() declares criteria.formula as that literal sum.
claims_validator.py's whitelist grammar (safe_formula.py: + - * / () only)
then independently recomputes the SAME weighted sum straight from the
snapshot, with NO import of the producer and NO re-derivation of the
percentile ranks/atlas joins upstream of the pillars (which that grammar
cannot express at all -- no rank/percentile op, no cross-parquet join). The
claim's min_sample coverage>=1.0 floor keeps the claimed ranking to exactly
the rows this fixed-weight formula is arithmetically identical to
score_index() for; a row with a dropped pillar (coverage<1.0) renormalizes
over fewer terms, which this formula does not express and such rows are
excluded via the floor, not silently mis-scored.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

_SNAPSHOT_DIR = Path("data/cache/intel_claims")


def _snapshot_path(index_name: str) -> Path:
    return _SNAPSHOT_DIR / f"nba_{index_name}_quality_v1_pillar_snapshot.parquet"


def write_pillar_snapshot(ranking_df: pd.DataFrame, weights: dict, index_name: str) -> str:
    """Write player_id/player_name/games/coverage + one pillar_<P> column per
    weight key to a flat parquet -- exactly quality_indices_score.score_index()'s
    own output columns, already on this dataframe. Returns the repo-relative
    path string (POSIX separators) for use as a claim's source_files entry."""
    cols = ["player_id", "player_name", "games", "coverage"] + [f"pillar_{p}" for p in weights]
    out_path = _snapshot_path(index_name)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(ranking_df[cols], preserve_index=False), out_path)
    return str(out_path).replace("\\", "/")


def build_pillar_formula(weights: dict) -> str:
    """Literal fixed-weight sum over the snapshot's pillar_<P> columns --
    algebraically identical to score_index()'s weighted_sum/available_weight
    ONLY when available_weight==total_weight, i.e. coverage==1.0 (see module
    docstring for the coverage<1.0 case this deliberately does not attempt
    to recompute)."""
    return " + ".join(f"{w}*pillar_{p}" for p, w in weights.items())
