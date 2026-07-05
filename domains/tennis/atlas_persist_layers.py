"""domains.tennis.atlas_persist_layers -- two more persisted atlas layers
(lane tennis-persist, program v3): scouting briefs + per-surface serve splits.

Kept in a SEPARATE file from atlas_persist.py purely on the <=300 LOC-per-file
rail (atlas_persist.py is already at its own wave-33 budget). Same package,
same conventions: REUSE the existing atlas builders/parsers, never
re-derive their aggregation logic; stamp as_of/corpus_id provenance at write.

Public API:
    persist_scouting(out_path, vault_tennis_dir=None, as_of=None) -> PersistResult
    persist_surface_splits(out_path, corpus_dir=None, as_of=None) -> PersistResult

persist_scouting() re-parses atlas_scouting's ALREADY-WRITTEN Style_Matchups
vault notes via atlas_scouting's OWN _parse_matchup_note helper -- no
recompute of the underlying clustering/win-rate logic. Gracefully empty
(never raises) if the vault briefs have not been built yet.

persist_surface_splits() computes per-player per-surface descriptive serve
aggregates (ace rate, first-serve-in %, double-fault rate on hard/clay/grass)
by joining matches.parquet's `surface` column to match_stats.parquet's
per-match p{1,2}_ace_rate / p{1,2}_1st_in_pct / p{1,2}_df_rate columns (the
SAME sidecar domains.tennis.asof_features already reads) and taking the
plain mean per (player, surface). This is a full-career DESCRIPTIVE
aggregate -- no trailing/as-of walk-forward ordering claim is made, unlike
asof_features.py's leak-free trailing means.

F5-clean: stdlib + numpy + pandas + domains.tennis.* only.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
from typing import Optional

import pandas as pd

from domains.tennis.atlas_persist import CORPUS_ID, PersistResult
from domains.tennis.atlas_playstyles import DEFAULT_CORPUS
from domains.tennis.atlas_scouting import _DEFAULT_VAULT as SCOUTING_DEFAULT_VAULT
from domains.tennis.atlas_scouting import _parse_matchup_note, _read

# Source-suffix -> output-column-name for the three per-surface serve metrics.
# Values come straight from match_stats.parquet (the same sidecar
# asof_features.py reads) -- no re-derivation from raw ace/svpt counts.
_SURFACE_METRICS: tuple[tuple[str, str], ...] = (
    ("ace_rate", "ace_rate"),
    ("1st_in_pct", "first_serve_in_pct"),
    ("df_rate", "double_fault_rate"),
)
MIN_SURFACE_SPLIT_MATCHES: int = 10  # same order of magnitude as atlas_playstyle_specs.MIN_SURFACE_MATCHES


def _corpus_max_date(matches: pd.DataFrame) -> str:
    """The corpus's own max match date (NOT wall-clock) -- used as built_at so
    the manifest is reproducible from a fixed corpus snapshot."""
    dates = pd.to_datetime(matches["date"], errors="coerce")
    if dates.notna().any():
        return dates.max().date().isoformat()
    return "unknown"


def persist_scouting(
    out_path: pathlib.Path,
    vault_tennis_dir: Optional[pathlib.Path] = None,
    as_of: Optional[str] = None,
) -> PersistResult:
    """Re-parse atlas_scouting's ALREADY-WRITTEN Style_Matchups vault notes
    (via its own _parse_matchup_note helper -- no recompute of the underlying
    win-rate/surface stats) into one row per archetype-pair scouting brief,
    and persist to parquet with provenance columns.

    Gracefully returns a zero-row PersistResult (never raises) if the vault
    Style_Matchups directory has not been built yet -- an honest empty layer,
    not a crash, since this layer's source depends on atlas_h2h.build_h2h
    (and atlas_scouting.build_scouting) having already been run.
    """
    if vault_tennis_dir is None:
        vault_tennis_dir = SCOUTING_DEFAULT_VAULT
    vault_tennis_dir = pathlib.Path(vault_tennis_dir)
    matchups_dir = vault_tennis_dir / "Style_Matchups"

    rows: list[dict] = []
    if matchups_dir.is_dir():
        for pair_path in sorted(matchups_dir.glob("*.md")):
            if pair_path.name.startswith("_"):
                continue
            text = _read(pair_path)
            if not text:
                continue
            parsed = _parse_matchup_note(text)
            if not parsed.get("archetype_a") or not parsed.get("archetype_b"):
                continue
            row = dict(parsed)
            row["pair_file"] = pair_path.name
            row["surfaces"] = json.dumps(row.get("surfaces") or {}, ensure_ascii=True)
            rows.append(row)

    stats = pd.DataFrame(rows)
    as_of = as_of or dt.date.today().isoformat()
    stats["as_of"] = as_of
    stats["corpus_id"] = CORPUS_ID

    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    stats.to_parquet(out_path, index=False)

    return PersistResult(out_path=out_path, row_count=len(stats), columns=list(stats.columns))


def persist_surface_splits(
    out_path: pathlib.Path,
    corpus_dir: Optional[pathlib.Path] = None,
    as_of: Optional[str] = None,
) -> PersistResult:
    """Per-player full-career descriptive per-surface serve aggregates: ace
    rate, first-serve-in %, double-fault rate on hard/clay/grass.

    One row per (player_id, surface) with columns: player_id, surface,
    n_matches, ace_rate, first_serve_in_pct, double_fault_rate, as_of,
    corpus_id. Below-MIN_SURFACE_SPLIT_MATCHES cells are DROPPED from this
    parquet (the claims producer re-applies its own floor and reports
    exclusions against the FULL joined population; this persistence layer
    only omits noise-cells that would never be rankable regardless).
    """
    if corpus_dir is None:
        corpus_dir = DEFAULT_CORPUS
    corpus_dir = pathlib.Path(corpus_dir)
    matches = pd.read_parquet(corpus_dir / "matches.parquet").copy()
    match_stats = pd.read_parquet(corpus_dir / "match_stats.parquet")

    matches["date"] = matches["date"].astype(str)
    joined = matches.merge(match_stats, on="event_id", how="inner", suffixes=("", "_ms"))

    long_frames: list[pd.DataFrame] = []
    for side in ("p1", "p2"):
        keep = ["surface", f"{side}_id"]
        rename = {f"{side}_id": "player_id"}
        for src_suf, out_name in _SURFACE_METRICS:
            col = f"{side}_{src_suf}"
            if col in joined.columns:
                keep.append(col)
                rename[col] = out_name
        sub = joined[keep].rename(columns=rename)
        long_frames.append(sub)
    long_df = pd.concat(long_frames, ignore_index=True)
    long_df["player_id"] = pd.to_numeric(long_df["player_id"], errors="coerce")
    long_df = long_df.dropna(subset=["player_id"])
    long_df["player_id"] = long_df["player_id"].astype("int64")

    metric_cols = [out_name for _, out_name in _SURFACE_METRICS if out_name in long_df.columns]
    agg = long_df.groupby(["player_id", "surface"], as_index=False).agg(
        n_matches=("surface", "size"), **{c: (c, "mean") for c in metric_cols}
    )
    agg = agg[agg["n_matches"] >= MIN_SURFACE_SPLIT_MATCHES].reset_index(drop=True)
    for c in metric_cols:
        agg[c] = agg[c].round(4)

    as_of = as_of or _corpus_max_date(matches)
    agg["as_of"] = as_of
    agg["corpus_id"] = CORPUS_ID

    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    agg.to_parquet(out_path, index=False)

    return PersistResult(out_path=out_path, row_count=len(agg), columns=list(agg.columns))


if __name__ == "__main__":
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    cache_dir = repo_root / "data" / "cache" / "tennis_atlas"

    r1 = persist_scouting(cache_dir / "scouting.parquet")
    print(f"scouting.parquet: {r1.row_count} rows, {len(r1.columns)} cols -> {r1.out_path}")

    r2 = persist_surface_splits(cache_dir / "surface_splits.parquet")
    print(f"surface_splits.parquet: {r2.row_count} rows, {len(r2.columns)} cols -> {r2.out_path}")
