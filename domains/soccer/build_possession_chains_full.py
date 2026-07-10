"""domains.soccer.build_possession_chains_full -- full-volume (up to 4,235-match)
expansion of domains.soccer.prereg_possession_chains.build_possessions() beyond
the thin ~400-match corpus (data/cache/statsbomb/matches/*.json lookup). SOURCE:
same possession + xG extraction logic (possession groupby, xg = sum of shot
statsbomb_xg in the possession, shotless possessions kept as xg=0), but keyed
off data/cache/statsbomb/match_meta_full.parquet (built by
build_match_meta_full.py -- 3,961 matches with confirmed cached event files)
instead of the small matches/*.json corpus. Row schema is IDENTICAL to
prereg_possession_chains.build_possessions()'s output -- this is a full-corpus
drop-in source, not a new shape.

OUTPUT: data/cache/statsbomb/possession_chains_full.parquet (match_id,
possession, team_id, team_name, play_pattern, xg, year, pattern_group,
is_counter, team_matches).

Resumable: --max-seconds bounds wall-clock; match_ids already present in the
output parquet are skipped on re-run (never re-parses a done match), matching
build_match_meta_full.py's --max-seconds/skip-if-cached convention. Partial
coverage is reported honestly via a progress checkpoint json.

CLI: python -m domains.soccer.build_possession_chains_full [--max-seconds S]
Per-file test: python -m pytest domains/soccer/test_build_possession_chains_full.py -q
"""
from __future__ import annotations

import argparse
import itertools
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_CACHE = REPO_ROOT / "data" / "cache" / "statsbomb"
_EVENTS_DIR = _CACHE / "events"
_META_PATH = _CACHE / "match_meta_full.parquet"
_OUT = _CACHE / "possession_chains_full.parquet"
_PROGRESS = _CACHE / "possession_chains_full_progress.json"


def _pattern_group(name: Optional[str]) -> str:
    if name == "From Counter":
        return "counter"
    if name == "Regular Play":
        return "regular"
    return "set_piece_derived"  # From Corner/Free Kick/Throw In/Goal Kick/Keeper/Kick Off/Other


def _match_possessions(match_id: int, year: Optional[int], events_path: Path) -> List[dict]:
    """One row per (match_id, possession): team owning it, play_pattern, and
    summed shot xG (0 if no shot in the possession -- shotless possessions are
    rows, never dropped). Identical extraction to prereg_possession_chains."""
    with open(events_path, encoding="utf-8") as f:
        events = json.load(f)
    rows: List[dict] = []
    for poss_id, grp_iter in itertools.groupby(events, key=lambda e: e.get("possession")):
        if poss_id is None:
            continue
        grp = list(grp_iter)
        team = grp[0].get("possession_team") or {}
        team_id = team.get("id")
        if team_id is None:
            continue
        pattern = (grp[0].get("play_pattern") or {}).get("name")
        xg = sum(
            (e.get("shot") or {}).get("statsbomb_xg") or 0.0
            for e in grp if e.get("type", {}).get("name") == "Shot"
        )
        rows.append({
            "match_id": match_id, "possession": poss_id, "team_id": team_id,
            "team_name": team.get("name"), "play_pattern": pattern, "xg": float(xg), "year": year,
        })
    return rows


def build(
    events_dir: Path = _EVENTS_DIR, meta_path: Path = _META_PATH, out_path: Path = _OUT,
    progress_path: Path = _PROGRESS, max_seconds: Optional[float] = None,
    match_ids: Optional[Sequence[int]] = None,
) -> Dict[str, object]:
    meta = pd.read_parquet(meta_path)
    meta["match_id"] = meta["match_id"].astype(int)
    if match_ids is not None:
        meta = meta[meta["match_id"].isin(set(int(m) for m in match_ids))]
    meta_lookup = meta.set_index("match_id")["match_date"].to_dict()

    existing = pd.read_parquet(out_path) if out_path.exists() else pd.DataFrame()
    done_ids = set(existing["match_id"].unique().tolist()) if len(existing) else set()

    remaining = [mid for mid in meta_lookup if mid not in done_ids]
    t0 = time.monotonic()
    stopped_reason = None
    new_rows: List[dict] = []
    n_processed = 0
    n_missing_events = 0
    for mid in remaining:
        if max_seconds is not None and (time.monotonic() - t0) > max_seconds:
            stopped_reason = "max_seconds"
            break
        ev_path = events_dir / f"{mid}.json"
        if not ev_path.exists():
            n_missing_events += 1
            continue
        date = meta_lookup[mid]
        year = int(str(date)[:4]) if date else None
        new_rows.extend(_match_possessions(mid, year, ev_path))
        n_processed += 1

    new_df = pd.DataFrame(new_rows)
    combined = pd.concat([existing, new_df], ignore_index=True) if len(existing) else new_df
    if len(combined):
        combined["pattern_group"] = combined["play_pattern"].map(_pattern_group)
        combined["is_counter"] = (combined["pattern_group"] == "counter").astype(int)
        combined["team_matches"] = combined.groupby("team_id")["match_id"].transform("nunique")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_parquet(out_path, index=False)

    cov = {
        "matches_in_meta": len(meta_lookup),
        "matches_done_before_run": len(done_ids),
        "matches_processed_this_run": n_processed,
        "matches_missing_event_file": n_missing_events,
        "matches_done_total": int(combined["match_id"].nunique()) if len(combined) else 0,
        "possession_rows_total": int(len(combined)),
        "stopped_reason": stopped_reason,
    }
    progress_path.write_text(json.dumps(cov, indent=2), encoding="ascii")
    return cov


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Build full-corpus possession/xG chains (resumable).")
    ap.add_argument("--max-seconds", type=float, default=None)
    a = ap.parse_args(argv)
    cov = build(max_seconds=a.max_seconds)
    print(json.dumps(cov, indent=2))
    return 0


__all__ = ["build", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
