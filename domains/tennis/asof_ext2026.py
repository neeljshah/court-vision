"""domains.tennis.asof_ext2026 -- extend the as-of serve/return corpus through 2026
for REPLICATION purposes (gap ledger rank 5, fix-wave lane beta).

WHY THIS IS LEAK-FREE EVEN THOUGH 2026 HAS NO MATCH_STATS SIDECAR: asof_features.py
and asof_return.py compute each match's feature as the trailing (strictly-prior)
mean of a player's history BEFORE that match -- a match's own serve/return counts
are only used to UPDATE history for future matches, never to compute its own row.
domains/tennis/matches_2026.parquet (ESPN results bridge, 3125 rows, 2026-01-02..
2026-07-09) has a real outcome label (winner) but zero serve/return counts (no
match_stats.parquet sidecar for 2026 exists, and Sackmann's own source is 404 --
see docs/research/tennis_replication_2026-07-11.md). So 2026 matches CANNOT
contribute new history, but their AS-OF SNAPSHOT (built purely from 2015-2025
history) is fully computable -- exactly what independent-corpus replication needs:
features discovery never fit on, for outcomes discovery never fit on.

Concatenating matches.parquet (ends 2025-12-17) + matches_2026.parquet (starts
2026-01-02, disjoint event_id namespace, zero date overlap) and re-running the
existing build_asof_features / build_asof_return over the combined spine leaves
every PRE-2026 output row byte-identical (forward-only accumulation, nothing
retroactively changes) and adds a valid as-of row for each 2026 match.

Writes 3 new artifacts (never overwrites the production 30616-row files many
other modules assume a fixed row count for):
    data/domains/tennis/matches_ext2026.parquet
    data/domains/tennis/asof_features_ext2026.parquet
    data/domains/tennis/asof_return_ext2026.parquet

NETWORK: zero. Run: python -m domains.tennis.asof_ext2026
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.tennis.asof_features import build_asof_features
from domains.tennis.asof_return import build_asof_return

_ROOT = Path(__file__).resolve().parents[2]
_MATCHES = _ROOT / "data" / "domains" / "tennis" / "matches.parquet"
_MATCHES_2026 = _ROOT / "data" / "domains" / "tennis" / "matches_2026.parquet"
_MATCH_STATS = _ROOT / "data" / "domains" / "tennis" / "match_stats.parquet"

MATCHES_EXT_OUT = _ROOT / "data" / "domains" / "tennis" / "matches_ext2026.parquet"
FEATURES_EXT_OUT = _ROOT / "data" / "domains" / "tennis" / "asof_features_ext2026.parquet"
RETURN_EXT_OUT = _ROOT / "data" / "domains" / "tennis" / "asof_return_ext2026.parquet"


def build_matches_ext2026(matches: pd.DataFrame = None, matches_2026: pd.DataFrame = None,
                           out_path: Path = MATCHES_EXT_OUT) -> pd.DataFrame:
    """Concat the 2015-2025 Sackmann spine + the 2026 ESPN bridge (disjoint date
    ranges, same column contract -- verified 20/20 columns match). No dedup
    needed: 0 event_id overlap, 0 date overlap (2025-12-17 vs 2026-01-02)."""
    matches = matches if matches is not None else pd.read_parquet(_MATCHES)
    matches_2026 = matches_2026 if matches_2026 is not None else pd.read_parquet(_MATCHES_2026)
    combined = pd.concat([matches, matches_2026[matches.columns]], ignore_index=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(combined, preserve_index=False), out_path)
    return combined


def build_all(out_dir: Path = None) -> dict:
    """Build the 3 ext2026 artifacts; returns {name: (path, row_count)}."""
    matches_ext = build_matches_ext2026()
    match_stats = pd.read_parquet(_MATCH_STATS)
    feat_path = build_asof_features(match_stats=match_stats, matches=matches_ext, out_path=str(FEATURES_EXT_OUT))
    ret_path = build_asof_return(match_stats=match_stats, matches=matches_ext, out_path=str(RETURN_EXT_OUT))
    return {
        "matches_ext2026": (MATCHES_EXT_OUT, len(matches_ext)),
        "asof_features_ext2026": (feat_path, len(pd.read_parquet(feat_path))),
        "asof_return_ext2026": (ret_path, len(pd.read_parquet(ret_path))),
    }


def _main() -> None:
    result = build_all()
    for name, (path, n) in result.items():
        print(f"{name}: {n} rows -> {path}")


if __name__ == "__main__":
    _main()
