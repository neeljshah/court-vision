"""scripts.platformkit.ingame.ingame_refresh_corpora -- corpus I/O helpers for the
LIVING in-game refresh loop (companion to ingame_refresh_runner.py, kept <=300 LOC).

The refresh loop maintains its OWN two rolling corpora per sport
(<sport>_states__refresh_a/_b.parquet) so it NEVER mutates a human-curated historical
corpus in place. The gate/serve discovery globs <sport>_states__* so these are picked
up automatically alongside any seed corpora.

This module owns: the deterministic A/B split, the corpus paths, dedup-by-game_id
discovery, and the ATOMIC append (tmp + os.replace). Frozen-schema only; never
fabricates. ASCII; pandas + stdlib; <=300 LOC.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
from typing import Dict, List, Sequence

# The frozen in-game schema columns the gate/serve require.
FROZEN_COLS = ("sport", "game_id", "asof_idx", "state_diff", "frac_elapsed",
               "p0", "outcome")


def corpus_for(game_id: str) -> int:
    """Deterministic, stable A/B split: 0 or 1 from a hash of game_id.

    Stable across restarts (no RNG) so a game always lands in the SAME corpus,
    keeping the cross-corpus split balanced and leak-free.
    """
    h = hashlib.sha1(str(game_id).encode("ascii", "replace")).hexdigest()
    return int(h, 16) & 1


def corpus_paths(sport: str, *, state_dir: pathlib.Path) -> List[pathlib.Path]:
    """The two append-target refresh corpora for `sport`."""
    return [state_dir / f"{sport}_states__refresh_a.parquet",
            state_dir / f"{sport}_states__refresh_b.parquet"]


def existing_game_ids(paths: Sequence[pathlib.Path]) -> set:
    """Set of game_ids already on disk across the corpora (for dedup). Never raises."""
    import pandas as pd
    ids: set = set()
    for p in paths:
        if p.exists():
            try:
                ids |= set(
                    pd.read_parquet(p, columns=["game_id"])["game_id"].astype(str))
            except Exception:  # noqa: BLE001 -- a torn parquet must not crash the loop
                pass
    return ids


def _atomic_write_parquet(df, path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp.%d" % os.getpid())
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)  # atomic on POSIX + Windows


def append_states(rows_by_corpus: Dict[int, list],
                  paths: Sequence[pathlib.Path]) -> int:
    """Append new state rows to each corpus parquet atomically; return total appended."""
    import pandas as pd
    total = 0
    for idx, path in enumerate(paths):
        new_rows = rows_by_corpus.get(idx, [])
        if not new_rows:
            continue
        new_df = pd.DataFrame(new_rows)
        if path.exists():
            old = pd.read_parquet(path)
            merged = pd.concat([old, new_df], ignore_index=True)
        else:
            merged = new_df
        _atomic_write_parquet(merged, path)
        total += len(new_rows)
    return total


__all__ = [
    "FROZEN_COLS", "corpus_for", "corpus_paths", "existing_game_ids", "append_states",
]
