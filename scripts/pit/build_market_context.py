"""H4: pregame game TOTAL and |SPREAD| market-context substrate builder.

Builds data/cache/pit/market_context_2025_26.parquet keyed by (game_date, team)
with columns: total, abs_spread.

Sources: data/pregame_spreads.parquet — posted pregame ESPN lines, season
2025-10-21 .. 2026-05-25. Rows are (game_date, home_team, away_team,
home_spread, total, source, fetched_at). All rows have the same fetched_at
(single scrape of historical data), so there is NO expanding/shift leakage:
the total and spread are the posted pregame values — they ARE the pre-game
information a bettor has. No shift(1) needed.

Leak note: the fetched_at timestamp is a single scrape date (2026-05-24)
of season-wide posted lines. The values represent the posted opening/closing
market line — this is standard as-of-safe pregame info.

Output: (game_date, team, total, abs_spread) — one row per (date, team) for
both home and away sides of each game. 30 teams × ~206 dates.

Self-test: total in [180, 280], abs_spread in [0, 30].
Read-only except writing under data/cache/pit/.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPREADS_PATH = os.path.join(ROOT, "data", "pregame_spreads.parquet")
OUT_DIR = os.path.join(ROOT, "data", "cache", "pit")
OUT_PATH = os.path.join(OUT_DIR, "market_context_2025_26.parquet")

# ESPN abbreviation -> NBA API abbreviation used in intel_grade bets['opp']
# Bets use: GSW, NYK, NOP, SAS, UTA, WAS
# Spreads use: GS, NY, NO, SA, UTAH, WSH
ESPN_TO_NBA: dict[str, str] = {
    "GS": "GSW",
    "NY": "NYK",
    "NO": "NOP",
    "SA": "SAS",
    "UTAH": "UTA",
    "WSH": "WAS",
}


def load_spreads() -> pd.DataFrame:
    sp = pd.read_parquet(SPREADS_PATH)
    sp["game_date"] = pd.to_datetime(sp["game_date"]).dt.normalize()
    sp["home_spread"] = pd.to_numeric(sp["home_spread"], errors="coerce")
    sp["total"] = pd.to_numeric(sp["total"], errors="coerce")
    sp = sp.dropna(subset=["game_date", "home_team", "away_team", "home_spread", "total"])
    return sp


def _normalize_team(t: str) -> str:
    t = str(t).strip().upper()
    return ESPN_TO_NBA.get(t, t)


def build_market_context(sp: pd.DataFrame) -> pd.DataFrame:
    """Expand each game into 2 rows (one per team), keyed (game_date, team)."""
    rows = []
    for r in sp.itertuples(index=False):
        gdate = r.game_date
        home = _normalize_team(r.home_team)
        away = _normalize_team(r.away_team)
        total = float(r.total)
        abs_spread = abs(float(r.home_spread))
        rows.append({"game_date": gdate, "team": home, "total": total, "abs_spread": abs_spread})
        rows.append({"game_date": gdate, "team": away, "total": total, "abs_spread": abs_spread})
    mc = pd.DataFrame(rows)
    mc = mc.sort_values(["game_date", "team"]).reset_index(drop=True)
    # Drop any exact duplicates (should not occur in clean data)
    mc = mc.drop_duplicates(subset=["game_date", "team"], keep="first")
    return mc


def selftest(mc: pd.DataFrame) -> None:
    """Validate total in [180, 280] and abs_spread in [0, 30]."""
    assert mc["total"].notna().all(), "Some totals are NaN"
    assert mc["abs_spread"].notna().all(), "Some abs_spreads are NaN"
    out_of_range_total = mc[(mc["total"] < 180) | (mc["total"] > 280)]
    if len(out_of_range_total):
        print(f"  WARNING: {len(out_of_range_total)} rows with total outside [180,280]:")
        print(out_of_range_total.head())
    assert len(out_of_range_total) == 0, "Total out of [180,280] range"
    out_of_range_spread = mc[(mc["abs_spread"] < 0) | (mc["abs_spread"] > 30)]
    if len(out_of_range_spread):
        print(f"  WARNING: {len(out_of_range_spread)} rows with abs_spread outside [0,30]:")
        print(out_of_range_spread.head())
    assert len(out_of_range_spread) == 0, "abs_spread out of [0,30] range"
    print(f"  self-test PASSED: {len(mc):,} rows, "
          f"total [{mc['total'].min():.1f},{mc['total'].max():.1f}], "
          f"abs_spread [{mc['abs_spread'].min():.1f},{mc['abs_spread'].max():.1f}]")


def build() -> pd.DataFrame:
    print("[market_context] loading pregame_spreads.parquet ...")
    sp = load_spreads()
    print(f"  {len(sp):,} games, dates {sp['game_date'].min().date()} -> "
          f"{sp['game_date'].max().date()}, "
          f"total [{sp['total'].min():.1f},{sp['total'].max():.1f}], "
          f"home_spread [{sp['home_spread'].min():.1f},{sp['home_spread'].max():.1f}]")
    mc = build_market_context(sp)
    print(f"  {len(mc):,} (game_date, team) rows, "
          f"{mc['team'].nunique()} teams, "
          f"{mc['game_date'].nunique()} unique dates")
    selftest(mc)
    os.makedirs(OUT_DIR, exist_ok=True)
    mc.to_parquet(OUT_PATH, index=False)
    print(f"  wrote {OUT_PATH}")
    # Face-validity: late-season sample
    late = mc[mc["game_date"] >= "2026-03-01"]
    if len(late):
        print(f"  late-season (Mar 2026+) total mean={late['total'].mean():.1f}, "
              f"abs_spread mean={late['abs_spread'].mean():.1f}")
    return mc


if __name__ == "__main__":
    build()
