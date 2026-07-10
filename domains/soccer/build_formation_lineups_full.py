"""domains.soccer.build_formation_lineups_full -- full-volume (up to
4,235-match) expansion of domains.soccer.claims_formation's Starting XI
extraction beyond the thin ~400-match corpus (data/cache/statsbomb/matches/
*.json lookup, which only carries team_id). SOURCE: data/cache/statsbomb/
events/{match_id}.json "Starting XI" events (tactics.formation + tactics.
lineup per side), keyed off data/cache/statsbomb/match_meta_full.parquet
(built by build_match_meta_full.py -- 3,961 matches, home/away as TEAM NAME
strings, no team_id) instead of the small matches/*.json corpus. Home/away
side is resolved by matching the Starting XI event's team.name against meta's
home_team/away_team (both sourced from the same StatsBomb API, so names match
exactly -- no fuzzy join).

OUTPUT: data/cache/statsbomb/formation_lineups_full.parquet, one row per
(match_id, team, starting player): match_id, match_date, competition, team_id,
team_name, is_home, formation, player_id, player_name, jersey_number,
position_id, position_name. Formation is denormalized onto every player row
(one team fields a single formation per match) -- simplest shape for both a
per-match-per-team formation read (groupby + first) and a lineup read.

Resumable: --max-seconds bounds wall-clock; match_ids already present in the
output parquet are skipped on re-run, matching build_match_meta_full.py's
--max-seconds/skip-if-cached convention.

CLI: python -m domains.soccer.build_formation_lineups_full [--max-seconds S]
Per-file test: python -m pytest domains/soccer/test_build_formation_lineups_full.py -q
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_CACHE = REPO_ROOT / "data" / "cache" / "statsbomb"
_EVENTS_DIR = _CACHE / "events"
_META_PATH = _CACHE / "match_meta_full.parquet"
_OUT = _CACHE / "formation_lineups_full.parquet"
_PROGRESS = _CACHE / "formation_lineups_full_progress.json"


def _fmt_formation(code: int) -> str:
    """statsbomb tactics.formation is a bare int like 4231 -> "4-2-3-1"."""
    return "-".join(str(code))


def _match_lineups(match_id: int, meta_row: dict, events_path: Path) -> List[dict]:
    """One row per starting player, both sides, for one match. Skips a side
    whose Starting XI event has no formation/lineup or whose team.name does
    not resolve to meta's home_team/away_team (never guesses a side)."""
    with open(events_path, encoding="utf-8") as f:
        events = json.load(f)
    rows: List[dict] = []
    for e in events:
        if e.get("type", {}).get("name") != "Starting XI":
            continue
        tactics = e.get("tactics") or {}
        formation = tactics.get("formation")
        lineup = tactics.get("lineup") or []
        if formation is None or not lineup:
            continue
        team = e.get("team") or {}
        team_id, team_name = team.get("id"), team.get("name")
        if team_name == meta_row.get("home_team"):
            is_home = 1
        elif team_name == meta_row.get("away_team"):
            is_home = 0
        else:
            continue  # team name didn't resolve against meta -- skip, don't guess
        for slot in lineup:
            player = slot.get("player") or {}
            position = slot.get("position") or {}
            rows.append({
                "match_id": match_id, "match_date": meta_row.get("match_date"),
                "competition": meta_row.get("competition"), "team_id": team_id,
                "team_name": team_name, "is_home": is_home, "formation": _fmt_formation(formation),
                "player_id": player.get("id"), "player_name": player.get("name"),
                "jersey_number": slot.get("jersey_number"),
                "position_id": position.get("id"), "position_name": position.get("name"),
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
    meta_lookup = meta.set_index("match_id").to_dict("index")

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
        new_rows.extend(_match_lineups(mid, meta_lookup[mid], ev_path))
        n_processed += 1

    new_df = pd.DataFrame(new_rows)
    combined = pd.concat([existing, new_df], ignore_index=True) if len(existing) else new_df
    if len(combined):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_parquet(out_path, index=False)

    cov = {
        "matches_in_meta": len(meta_lookup),
        "matches_done_before_run": len(done_ids),
        "matches_processed_this_run": n_processed,
        "matches_missing_event_file": n_missing_events,
        "matches_done_total": int(combined["match_id"].nunique()) if len(combined) else 0,
        "lineup_rows_total": int(len(combined)),
        "stopped_reason": stopped_reason,
    }
    progress_path.write_text(json.dumps(cov, indent=2), encoding="ascii")
    return cov


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Build full-corpus formation + starting lineup rows (resumable).")
    ap.add_argument("--max-seconds", type=float, default=None)
    a = ap.parse_args(argv)
    cov = build(max_seconds=a.max_seconds)
    print(json.dumps(cov, indent=2))
    return 0


__all__ = ["build", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
