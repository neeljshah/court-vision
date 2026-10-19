"""scripts.platformkit.eval_gate.mlb_frozen_vs_walkforward_elo_ingress -- S448 AMENDMENT 9(a)

AMENDMENT 8(b) fixed clean_games_asof() to slice per-row RECORDS by date before
any pandas DataFrame is (re)built -- but round-9 verification found both real
ingress branches in mlb_frozen_vs_walkforward_elo.py's _main() still handed it an
ALREADY-MATERIALISED pandas DataFrame (via pd.read_parquet()), at which point a
coercion across sources is already irreversible (a genuinely-int game_seq in one
source and a genuinely-float game_seq in another cannot share a single pandas
column without one of them losing its true type).

read_games_parquet() closes that gap for the --games-parquet override: it reads
each file via pyarrow's own to_pylist(), never pandas, and concatenates RECORD
LISTS (plain Python `+`) rather than tables/DataFrames -- so two independently,
cleanly-typed source files can never cross-contaminate each other's column dtype,
even though a single file's own column is (unavoidably, representationally) fixed
at whatever it was written with.
"""
from __future__ import annotations

from typing import List


def read_games_parquet(*paths) -> List[dict]:
    """Read one or more parquet files into ONE list of per-row records via
    pyarrow's to_pylist() -- never pd.read_parquet(), and never a table-level
    concatenation. Each file's own column type stays wholly independent of every
    other file's; only the Python-level record list is combined."""
    import pyarrow.parquet as pq  # noqa: PLC0415

    records: List[dict] = []
    for path in paths:
        records.extend(pq.read_table(path).to_pylist())
    return records
