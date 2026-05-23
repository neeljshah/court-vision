"""fetch_missing_nba_data.py — fill cached supporting-data gaps.

Audit (cycle 17, 2026-05-23) showed massive gaps in supporting NBA data that
forced multiple WinProb features to constant defaults across most seasons:

  Feature                   | Default | Source needed
  --------------------------+---------+---------------
  home/away_pnr_ppp         | 0.0     | synergy_offensive_all_{season}.json
  iso_matchup_edge          | 0.0     | synergy_offensive_all + synergy_defensive_all
  home/away_hustle_*_pg     | 0.0     | hustle_stats_{season}.json
  home/away_bench_net_rtg   | 0.0     | lineups/lineup_splits_{TEAM}_{SEASON}.json
  home/away_top_lineup_*    | 0.0     | same lineup files (via lineup_data module)

Only 2022-23 .. 2024-25 had synergy cached; only 2024-25 had hustle stats;
lineup data was 11 sparse files. For our 6-season training window, all
historical seasons (2018-19, 2020-21, 2021-22) were missing this signal.

This script pulls everything in one go via the patched nba_api:
  - synergy offensive + defensive (per play_type) per season
  - hustle stats player-level per season
  - leaguedashlineups (5-man, BasePlus) per season, split + written per-team

Run:
    python scripts/fetch_missing_nba_data.py
    python scripts/fetch_missing_nba_data.py --seasons 2018-19 2020-21
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import List

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data import nba_api_headers_patch  # noqa: F401, E402

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_LINEUPS_DIR = os.path.join(_NBA_CACHE, "lineups")
os.makedirs(_LINEUPS_DIR, exist_ok=True)

# Play types the model reads via _synergy_team_iso_ppp / _get_pnr_ppp.
_PLAY_TYPES = ["Isolation", "PRBallHandler", "PRRollMan", "Postup",
               "Spotup", "Handoff", "Transition", "Cut", "OffScreen",
               "Putbacks"]

_DEFAULT_SEASONS = ["2018-19", "2020-21", "2021-22",
                    "2022-23", "2023-24", "2024-25"]


def _slow():
    time.sleep(0.8)


def _normalise_row(r: dict) -> dict:
    """Lowercase keys + numeric coercion to match the existing cache format."""
    out = {}
    for k, v in r.items():
        kl = k.lower()
        try:
            out[kl] = float(v) if isinstance(v, (int, float)) else v
        except Exception:
            out[kl] = v
    return out


def fetch_synergy(season: str) -> int:
    """Fetch synergy offensive + defensive for all play types in a season.

    Writes:
      data/nba/synergy_offensive_all_{season}.json
      data/nba/synergy_defensive_all_{season}.json
    """
    from nba_api.stats.endpoints import synergyplaytypes
    for grouping in ["offensive", "defensive"]:
        out_path = os.path.join(
            _NBA_CACHE, f"synergy_{grouping}_all_{season}.json"
        )
        if os.path.exists(out_path):
            print(f"  [skip] synergy {grouping} {season} already cached")
            continue
        all_rows: list = []
        for play_type in _PLAY_TYPES:
            _slow()
            try:
                df = synergyplaytypes.SynergyPlayTypes(
                    season=season, season_type_all_star="Regular Season",
                    play_type_nullable=play_type,
                    type_grouping_nullable=grouping,
                    per_mode_simple="PerGame",
                ).get_data_frames()[0]
            except Exception as e:
                print(f"  [warn] synergy {grouping}/{play_type}/{season}: {e}")
                continue
            for _, r in df.iterrows():
                norm = _normalise_row(r.to_dict())
                # Existing cache uses "ppp"; the API returns "PPP" -> already
                # lowercased above. Also seed "play_type" key with original
                # spelling (existing _get_pnr_ppp checks "PRBallHandler").
                norm["play_type"] = play_type
                all_rows.append(norm)
        with open(out_path, "w") as f:
            json.dump(all_rows, f)
        print(f"  wrote {len(all_rows)} synergy rows -> "
              f"synergy_{grouping}_all_{season}.json")
    return 1


def fetch_hustle(season: str) -> int:
    """Pull leaguehustlestatsplayer per-player + write a list-of-dicts file.

    Writes: data/nba/hustle_stats_{season}.json (player-level, matches the
    existing format that _get_hustle_deflections reads).
    """
    out_path = os.path.join(_NBA_CACHE, f"hustle_stats_{season}.json")
    if os.path.exists(out_path):
        print(f"  [skip] hustle {season} already cached")
        return 0
    from nba_api.stats.endpoints import leaguehustlestatsplayer
    _slow()
    try:
        df = leaguehustlestatsplayer.LeagueHustleStatsPlayer(
            season=season, season_type_all_star="Regular Season",
            per_mode_time="PerGame",
        ).get_data_frames()[0]
    except Exception as e:
        print(f"  [warn] hustle {season}: {e}")
        return 0
    rows = [_normalise_row(r.to_dict()) for _, r in df.iterrows()]
    # Existing reader does r.get("deflections_pg"). API returns "DEFLECTIONS"
    # (per game already because per_mode_time=PerGame). Mirror it.
    for r in rows:
        if "deflections_pg" not in r and "deflections" in r:
            r["deflections_pg"] = r["deflections"]
    with open(out_path, "w") as f:
        json.dump(rows, f)
    print(f"  wrote {len(rows)} hustle rows -> hustle_stats_{season}.json")
    return len(rows)


def fetch_lineups(season: str) -> int:
    """leaguedashlineups (5-man, BasePlus) per season; split per-team.

    Writes one file per team:
      data/nba/lineups/lineup_splits_{TEAM}_{season}.json
    Each file is a list of lineup-row dicts compatible with
    _get_bench_net_rtg + lineup_data.get_top_lineups.
    """
    from nba_api.stats.endpoints import leaguedashlineups
    _slow()
    try:
        # Advanced measure gives NET_RATING/OFF_RATING/DEF_RATING/PACE/EFG_PCT
        # which the model uses; Base gives box-score counts (PTS/AST/...) but
        # not the rating columns _get_bench_net_rtg needs.
        df = leaguedashlineups.LeagueDashLineups(
            season=season, season_type_all_star="Regular Season",
            group_quantity=5, measure_type_detailed_defense="Advanced",
            per_mode_detailed="Per100Possessions",
        ).get_data_frames()[0]
    except Exception as e:
        print(f"  [warn] lineups {season}: {e}")
        return 0

    # Normalize + augment for downstream readers.
    rows = []
    for _, r in df.iterrows():
        d = _normalise_row(r.to_dict())
        d["lineup_size"] = 5
        # Two readers use these files:
        #   src.data.lineup_data.get_top_lineups  expects net_rating, minutes, lineup
        #   _get_bench_net_rtg                     expects net_rtg or NET_RATING, min
        # Write both spellings so both readers work.
        if "net_rating" in d and "net_rtg" not in d:
            d["net_rtg"] = d["net_rating"]
        if "min" in d and "minutes" not in d:
            d["minutes"] = d["min"]
        if "group_name" in d and "lineup" not in d:
            d["lineup"] = [p.strip() for p in str(d["group_name"]).split(" - ")]
        rows.append(d)

    by_team: dict = {}
    for r in rows:
        ta = str(r.get("team_abbreviation", "")).upper()
        if ta:
            by_team.setdefault(ta, []).append(r)

    written = 0
    for team, team_rows in by_team.items():
        out_path = os.path.join(
            _LINEUPS_DIR, f"lineup_splits_{team}_{season}.json"
        )
        with open(out_path, "w") as f:
            json.dump(team_rows, f)
        written += 1
    print(f"  wrote {written} per-team lineup files for {season} "
          f"({len(rows)} total lineups)")
    return written


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", default=_DEFAULT_SEASONS)
    ap.add_argument("--skip-synergy", action="store_true")
    ap.add_argument("--skip-hustle",  action="store_true")
    ap.add_argument("--skip-lineups", action="store_true")
    args = ap.parse_args()

    print(f"Missing-data fetcher for {args.seasons}")
    t0_total = time.time()
    for s in args.seasons:
        print(f"\n=== {s} ===", flush=True)
        t0 = time.time()
        if not args.skip_synergy:
            print(f"[synergy {s}]", flush=True)
            fetch_synergy(s)
        if not args.skip_hustle:
            print(f"[hustle {s}]", flush=True)
            fetch_hustle(s)
        if not args.skip_lineups:
            print(f"[lineups {s}]", flush=True)
            fetch_lineups(s)
        print(f"  {s} elapsed {time.time()-t0:.1f}s", flush=True)
    print(f"\nDONE in {time.time()-t0_total:.1f}s")


if __name__ == "__main__":
    main()
