"""domains.soccer.build_match_meta_full -- metadata-only expansion of match_meta
beyond the chain engine's original 2-corpus (A/B, 400-match) slice.

WHY: a SEPARATE full-repo pull (scripts.platformkit.data_frontier.statsbomb_open_full)
already downloaded 3,443+/4,235 StatsBomb open-data event files by match_id, but never
built match metadata (date/home/away/score/competition/season) for them. This script
closes that gap for METADATA ONLY -- it fetches every published (competition_id,
season_id) match-list (same cached/resumable/polite fetch_matches() already used by
domains.soccer.ingest_statsbomb_events), then keeps only matches whose event file is
ALREADY cached on disk (no new event-file network fetch here).

OUTPUT: data/cache/statsbomb/match_meta_full.parquet (match_id, match_date, home_team,
away_team, home_score, away_score, competition, season). The chain engine's existing
input data/cache/statsbomb/match_meta.parquet (corpus A/B) is untouched.

Resumable: fetch_matches()/_get_json() already skip-if-cached per (comp,season) file
(zero network on re-run). --max-seconds bounds wall-clock on a cold run; partial
coverage is reported honestly, not swallowed.

INVARIANTS: domains-only; ASCII; <=300 LOC; no $/edge claim (metadata builder only).
CLI: python -m domains.soccer.build_match_meta_full [--max-seconds S]
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from domains.soccer.ingest_statsbomb_events import fetch_competitions, fetch_matches

_REPO = Path(__file__).resolve().parents[2]
_CACHE = _REPO / "data" / "cache" / "statsbomb"
_EVENTS_DIR = _CACHE / "events"
_MATCHES_DIR = _CACHE / "matches"
_OUT = _CACHE / "match_meta_full.parquet"


def _label(name: str) -> str:
    """Descriptive competition/season label -> filesystem/columnar-safe string."""
    return "".join(c if c.isalnum() else "_" for c in str(name)).strip("_")


def _comp_season_pairs(competitions: List[dict]) -> List[Tuple[int, int, str, str]]:
    seen = set()
    pairs = []
    for c in competitions:
        key = (c["competition_id"], c["season_id"])
        if key in seen:
            continue
        seen.add(key)
        pairs.append((c["competition_id"], c["season_id"],
                      c.get("competition_name", "comp"), c.get("season_name", "season")))
    return pairs


def build(max_seconds: Optional[float] = None) -> Dict[str, object]:
    competitions = fetch_competitions()
    pairs = _comp_season_pairs(list(competitions))
    cached_events = {p.stem for p in _EVENTS_DIR.glob("*.json")} if _EVENTS_DIR.exists() else set()

    t0 = time.monotonic()
    stopped_reason = None
    rows: List[dict] = []
    per_comp_counts: Dict[str, int] = {}
    n_pairs_fetched = 0
    n_pairs_skipped_budget = 0

    for cid, sid, comp_name, season_name in pairs:
        cache_fp = _MATCHES_DIR / f"{cid}_{sid}.json"
        if not cache_fp.exists():
            if max_seconds is not None and (time.monotonic() - t0) > max_seconds:
                stopped_reason = "max_seconds"
                n_pairs_skipped_budget += 1
                continue
        matches = fetch_matches(cid, sid)
        n_pairs_fetched += 1
        label = f"{_label(comp_name)}_{_label(season_name)}"
        for m in matches:
            if m.get("home_score") is None or m.get("away_score") is None:
                continue
            mid = str(m["match_id"])
            if mid not in cached_events:
                continue  # metadata-only: never fetch a new event file here
            rows.append({
                "match_id": mid, "match_date": m.get("match_date", ""),
                "home_team": m["home_team"]["home_team_name"],
                "away_team": m["away_team"]["away_team_name"],
                "home_score": m["home_score"], "away_score": m["away_score"],
                "competition": label,
            })
            per_comp_counts[label] = per_comp_counts.get(label, 0) + 1

    df = pd.DataFrame(rows)
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_OUT, index=False)

    cov = {
        "competitions_published": len(pairs),
        "comp_season_pairs_fetched_this_run": n_pairs_fetched,
        "comp_season_pairs_skipped_budget": n_pairs_skipped_budget,
        "stopped_reason": stopped_reason,
        "matches_with_meta_and_cached_events": int(len(df)),
        "n_competitions_covered": len(per_comp_counts),
        "top_competitions_by_match_count": sorted(
            per_comp_counts.items(), key=lambda kv: -kv[1])[:15],
    }
    return cov


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Build full-coverage match_meta (metadata-only).")
    ap.add_argument("--max-seconds", type=float, default=None)
    a = ap.parse_args(argv)
    cov = build(max_seconds=a.max_seconds)
    import json
    print(json.dumps(cov, indent=2))
    return 0


__all__ = ["build", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
