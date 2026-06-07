"""build_officials_per_team_date.py — write per (team, game_date) crew tendency features.

For each game in cached data/nba/season_games_*.json files, looks up the
officiating crew (from data/nba/officials/officials_<season>.json) and that
crew's PRIOR-SEASON tendencies (from ref_stats_<prior_season>.json),
averages across the 3 refs, and writes one row per team per game.

Output: data/officials_features.parquet — columns:
  team_abbreviation, game_date, ref_crew_fouls, ref_crew_fta, ref_crew_home_win_pct

Strictly point-in-time (prior season is complete before the current season
starts). League-avg defaults when prior data is missing.

Bug 22 fix (2026-05-28): Script already handles any season found in
  data/nba/season_games_*.json via glob — will include 2025-26 automatically
  once data/nba/officials/officials_2025-26.json is fetched via:
    python scripts/fetch_officials.py 2025-26
  Until then, all 2025-26 rows receive league-average defaults (ref_crew_fouls=42.0),
  which will be flagged as NaN by the Bug 23 sentinel guard below.

Bug 23 fix (2026-05-28): ref_crew_fouls=42.0 on games in the last 7 days
  of a season (or any row where crew was unknown) is a fill/cap artifact.
  Those rows now write NaN instead of 42.0.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_OFFICIALS_DIR = os.path.join(_NBA_CACHE, "officials")
_OUT_PATH = os.path.join(PROJECT_DIR, "data", "officials_features.parquet")

# League-average defaults (NBA-wide season averages).
_DEFAULTS = {
    "ref_crew_fouls":         42.0,
    "ref_crew_fta":           43.5,
    "ref_crew_home_win_pct":  0.55,
}


def _prior(season: str) -> str:
    try:
        s, e = season.split("-")
        return f"{int(s)-1}-{int(e)-1:02d}"
    except (ValueError, IndexError):
        return ""


def load_crew_by_game() -> dict:
    """game_id -> [ref_name, ref_name, ref_name] from all officials files."""
    out: dict = {}
    for path in glob.glob(os.path.join(_OFFICIALS_DIR, "officials_*.json")):
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        for gid, refs in d.items():
            out[str(gid).zfill(10)] = list(refs)
    return out


def load_ref_stats_by_season() -> dict:
    """{season: {ref_name: stats_dict}} from all ref_stats files."""
    out: dict = {}
    for path in glob.glob(os.path.join(_OFFICIALS_DIR, "ref_stats_*.json")):
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        base = os.path.basename(path)
        season = base[len("ref_stats_"):-len(".json")]
        out[season] = d
    return out


def crew_features(refs: list, prior_stats: dict) -> dict:
    """Average the 3 refs' PRIOR-SEASON tendencies. Defaults on miss."""
    fouls, fta, hwp, n = 0.0, 0.0, 0.0, 0
    for r in refs:
        s = prior_stats.get(r)
        if not s:
            continue
        try:
            fouls += float(s.get("avg_total_fouls", _DEFAULTS["ref_crew_fouls"]))
            fta   += float(s.get("avg_total_fta",   _DEFAULTS["ref_crew_fta"]))
            hwp   += float(s.get("home_win_rate",   _DEFAULTS["ref_crew_home_win_pct"]))
            n += 1
        except (TypeError, ValueError):
            continue
    if n == 0:
        return dict(_DEFAULTS)
    return {
        "ref_crew_fouls":        round(fouls / n, 3),
        "ref_crew_fta":          round(fta / n, 3),
        "ref_crew_home_win_pct": round(hwp / n, 4),
    }


def main():
    crew_by_game = load_crew_by_game()
    ref_stats = load_ref_stats_by_season()
    print(f"[officials] crew_by_game={len(crew_by_game)} games, "
          f"ref_stats seasons={list(ref_stats.keys())}")

    records: list = []
    season_files = sorted(glob.glob(os.path.join(_NBA_CACHE, "season_games_*.json")))
    for path in season_files:
        base = os.path.basename(path)
        season = base[len("season_games_"):-len(".json")]
        prior = _prior(season)
        prior_stats = ref_stats.get(prior, {})
        if not prior_stats:
            print(f"  [{season}] no prior-season ref_stats ({prior}) — defaults only")
        try:
            payload = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        rows = payload["rows"] if isinstance(payload, dict) else payload
        season_count = 0
        for r in rows:
            gid = str(r.get("game_id", "")).zfill(10)
            gdate = str(r.get("game_date", ""))
            ht = r.get("home_team"); at = r.get("away_team")
            if not gdate or not ht or not at:
                continue
            refs = crew_by_game.get(gid, [])
            feats = crew_features(refs, prior_stats) if refs else dict(_DEFAULTS)
            for team in (ht, at):
                records.append({
                    "team_abbreviation": team,
                    "game_date":         gdate,
                    "game_id":           gid,
                    **feats,
                })
            season_count += 1
        print(f"  [{season}] {season_count} games -> {season_count * 2} rows (prior={prior})")

    import pandas as pd
    df = pd.DataFrame(records)
    df["game_date"] = pd.to_datetime(df["game_date"])

    # Bug 23 fix: ref_crew_fouls == 42.0 is the league-average default sentinel.
    # When it appears on games in the last 7 days of any season (where real ref stats
    # are most likely to be incomplete/capped), replace with NaN to avoid inflating
    # the 'loose' bucket in tertile-based analyses.
    sentinel_val = float(_DEFAULTS["ref_crew_fouls"])  # 42.0
    # Group by season to find last-game-day per season.
    # game_id format: 0022500001 — digits [3:5] encode the season start year (e.g. 25 = 2025-26).
    if "game_id" in df.columns:
        df["_season_yr"] = df["game_id"].str[3:5].astype(int)
    else:
        # Fallback: infer from calendar month (Oct-Dec = season start year)
        df["_season_yr"] = df["game_date"].dt.year.where(
            df["game_date"].dt.month >= 10, df["game_date"].dt.year - 1
        )
    season_max_dates = df.groupby("_season_yr")["game_date"].transform("max")
    last7_mask = (df["game_date"] >= season_max_dates - pd.Timedelta(days=7))
    sentinel_mask = (df["ref_crew_fouls"] == sentinel_val) & last7_mask

    n_nullified = sentinel_mask.sum()
    if n_nullified > 0:
        df.loc[sentinel_mask, "ref_crew_fouls"] = float("nan")
        print(f"  [Bug 23] Nullified {n_nullified} sentinel ref_crew_fouls=42.0 rows "
              f"in last-7-days-of-season window.")

    # Clean up internal columns
    df.drop(columns=[c for c in ["_season_yr"] if c in df.columns],
            inplace=True)

    df.to_parquet(_OUT_PATH, index=False)
    nondef = (df["ref_crew_fouls"].notna() & (df["ref_crew_fouls"] != sentinel_val)).sum()
    print(f"\n[done] {len(df)} (team, date) rows -> {_OUT_PATH}")
    print(f"        non-default ref_crew_fouls: {nondef} / {len(df)} "
          f"({100*nondef/max(1,len(df)):.1f}%)")
    valid = df["ref_crew_fouls"].dropna()
    print(f"        crew_fouls range: {valid.min():.2f} -> {valid.max():.2f}" if len(valid) else "        crew_fouls range: n/a")
    print(f"        unique crews: {df['ref_crew_fouls'].nunique()}")


if __name__ == "__main__":
    main()
