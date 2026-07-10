"""domains.mlb.carryover_asof -- LEAK-FREE cross-game CARRYOVER as-of panel:
the starting pitcher's own PRIOR start's realized load (pitch count + rest
days), one season-year at a time.

Two attrs, both team-game diffs (home SP - away SP):
  sp_prior_pitch_count_asof -- pitch count of the SP's own immediately-PRIOR
      start (LAG-1, not a rolling mean) -- a fatigue-carryover proxy.
  sp_rest_days_asof          -- days between this start and that prior start.

Source: data/cache/statcast/savant_full__<year>.parquet (per-pitch Statcast,
2022-2025 incl. the 2025 season the profile-completeness lane's hitcoords work
extended coverage into) -- has individual pitcher identity, unlike the
ingame mlb_pitch_states corpus ingest_sp_fatigue_prop_states.py profiles
(team-side only, no SP id -- that class stays CLOSED, see knowledge memory).
The STARTER for each (game_pk, pitching side) is the pitcher who threw that
side's first pitch (sorted inning/outs/at_bat/pitch_number); pitch_count is
counted over ONLY that pitcher's own rows (excludes relievers).

ID BRIDGE (outcome-free): Statcast team codes are the SAME dialect as
domains.mlb.game_pk_bridge.GC_TO_PG_TEAM's VALUE side (verified on disk); the
inverse map bridges to games_current.parquet's dialect (2022-2026 coverage,
overlaps every savant_full year) via a (date, home, away) schedule key -- no
score/outcome column is read here, matching boxdetail_asof.py's discipline.
Unmatched games (all-star exhibitions, minor dialect gaps) are DROPPED, never
fabricated.

Output -> data/domains/mlb/carryover_asof__<year>.parquet keyed event_id.
Feeds the interaction_factory's mlb_carryover_self_cross template -- see
scripts/platformkit/interaction_factory/builders_carryover.py.
Expected gate verdict: NULL/small -- b2b/rest is already heavily priced; a
REJECT/NULL is a SUCCESS. No edge ever claimed.

PRIVATE: data/domains/mlb/ and data/cache/statcast/ are never tracked. No
src.*/kernel.*/other-domain imports (falsifier F5 compliance). ASCII only.
<=300 LOC. CLI: python -m domains.mlb.carryover_asof --year 2023
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from domains.mlb.game_pk_bridge import GC_TO_PG_TEAM

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SAVANT_DIR = _REPO_ROOT / "data" / "cache" / "statcast"
_GAMES_CURRENT = _REPO_ROOT / "data" / "domains" / "mlb" / "games_current.parquet"
_OUT_DIR = _REPO_ROOT / "data" / "domains" / "mlb"

# Inverse of GC_TO_PG_TEAM (games_current-dialect -> Statcast/PG-dialect): the
# ~22 franchises whose code is IDENTICAL in both dialects need no entry.
_PG_TO_GC = {v: k for k, v in GC_TO_PG_TEAM.items()}

_SIDE_COLS = ["sp_prior_pitch_count_asof", "sp_rest_days_asof", "n_prior"]
OUTPUT_COLS = [
    "event_id", "season",
    "home_sp_prior_pitch_count_asof", "away_sp_prior_pitch_count_asof", "sp_prior_pitch_count_diff_asof",
    "home_sp_rest_days_asof", "away_sp_rest_days_asof", "sp_rest_days_diff_asof",
    "home_n_prior", "away_n_prior",
]

_PITCH_COLS = ["game_pk", "game_date", "pitcher", "home_team", "away_team",
               "inning_topbot", "inning", "outs_when_up", "pitch_number", "at_bat_number"]


def savant_source_for_year(year: str) -> Path:
    return _SAVANT_DIR / f"savant_full__{year}.parquet"


def _canon_to_gc(code: object) -> str:
    s = str(code).strip().upper()
    return _PG_TO_GC.get(s, s)


def _pitching_team(pitch_df: pd.DataFrame) -> pd.Series:
    """Top half = visiting team bats -> HOME team pitches; Bot half -> AWAY pitches."""
    is_top = pitch_df["inning_topbot"].astype(str).str.strip().str.lower().eq("top")
    return pitch_df["home_team"].where(is_top, pitch_df["away_team"])


def build_starts(pitch_df: pd.DataFrame) -> pd.DataFrame:
    """One row per (game_pk, pitch_team) = the STARTER's own outing: pitcher id,
    n_pitches (his own pitches only, relievers excluded), date, home/away_team."""
    if pitch_df.empty:
        return pd.DataFrame(columns=["game_pk", "pitch_team", "pitcher", "n_pitches",
                                      "date", "home_team", "away_team"])
    d = pitch_df.copy()
    d["pitch_team"] = _pitching_team(d)
    d = d.sort_values(
        ["game_pk", "pitch_team", "inning", "outs_when_up", "at_bat_number", "pitch_number"],
        kind="mergesort")
    starter_map = (d.groupby(["game_pk", "pitch_team"], sort=False)["pitcher"].first()
                   .reset_index().rename(columns={"pitcher": "starter_id"}))
    d = d.merge(starter_map, on=["game_pk", "pitch_team"], how="left")
    d_starter = d[d["pitcher"] == d["starter_id"]]
    starts = d_starter.groupby(["game_pk", "pitch_team"], as_index=False).agg(
        pitcher=("pitcher", "first"), n_pitches=("pitcher", "size"),
        date=("game_date", "first"), home_team=("home_team", "first"), away_team=("away_team", "first"),
    )
    return starts


def _walk_forward_lag1(starts: pd.DataFrame) -> pd.DataFrame:
    """LAG-1 per pitcher (this year's file only -- season-scoped by construction):
    this start's feature = that SAME pitcher's immediately-PRIOR start's pitch
    count + days since. A pitcher's first start on-disk this year is NaN."""
    s = starts.copy()
    s["date"] = pd.to_datetime(s["date"])
    s = s.sort_values(["pitcher", "date", "game_pk"], kind="mergesort").reset_index(drop=True)
    g = s.groupby("pitcher", sort=False)
    s["sp_prior_pitch_count_asof"] = g["n_pitches"].shift(1)
    prior_date = g["date"].shift(1)
    s["sp_rest_days_asof"] = (s["date"] - prior_date).dt.days.astype(float)
    s["n_prior"] = g.cumcount()
    return s


def _pivot_to_games(starts: pd.DataFrame) -> pd.DataFrame:
    """Two starter-rows per game_pk -> one row with home/away/diff columns."""
    is_home = starts["pitch_team"] == starts["home_team"]
    home = starts[is_home]
    away = starts[~is_home]

    h = home[["game_pk", "date", "home_team", "away_team"] + _SIDE_COLS].rename(
        columns={c: f"home_{c}" for c in _SIDE_COLS})
    a = away[["game_pk"] + _SIDE_COLS].rename(columns={c: f"away_{c}" for c in _SIDE_COLS})
    out = h.merge(a, on="game_pk", how="outer")

    out["sp_prior_pitch_count_diff_asof"] = out["home_sp_prior_pitch_count_asof"] - out["away_sp_prior_pitch_count_asof"]
    out["sp_rest_days_diff_asof"] = out["home_sp_rest_days_asof"] - out["away_sp_rest_days_asof"]
    for side in ("home_n_prior", "away_n_prior"):
        out[side] = pd.to_numeric(out[side], errors="coerce").fillna(0).astype("int64")
    return out


def _bridge_to_event_id(out: pd.DataFrame, games_current: pd.DataFrame) -> pd.DataFrame:
    """Outcome-free schedule-key join: (date, home_team, away_team) canonicalized
    to games_current's dialect -> event_id. Unmatched rows dropped, never guessed."""
    df = out.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["_home_gc"] = df["home_team"].map(_canon_to_gc)
    df["_away_gc"] = df["away_team"].map(_canon_to_gc)

    gc = games_current[["event_id", "date", "home_team", "away_team", "season"]].copy()
    gc["date"] = pd.to_datetime(gc["date"])

    merged = df.merge(
        gc, left_on=["date", "_home_gc", "_away_gc"],
        right_on=["date", "home_team", "away_team"], how="inner", suffixes=("", "_gc"))
    return merged


def build_carryover_asof(
    year: str,
    pitch_df: Optional[pd.DataFrame] = None,
    games_current: Optional[pd.DataFrame] = None,
    out_path: Optional[str] = None,
) -> Path:
    """Build one season-year's leak-free SP carryover as-of parquet.

    Parameters
    ----------
    year: the savant_full__<year>.parquet season to load (default source path).
    pitch_df: per-pitch DataFrame (see _PITCH_COLS). If None, reads the default
        on-disk parquet for `year`.
    games_current: games_current.parquet-shaped DataFrame (event_id, date,
        home_team, away_team, season) used ONLY for the outcome-free schedule
        bridge. If None, reads the default on-disk parquet.
    out_path: output parquet path. If None, uses carryover_asof__<year>.parquet.
    """
    dest = Path(out_path) if out_path is not None else (_OUT_DIR / f"carryover_asof__{year}.parquet")

    if pitch_df is None:
        src = savant_source_for_year(year)
        if not src.exists():
            raise FileNotFoundError(f"savant_full__{year}.parquet not found at {src}.")
        pitch_df = pd.read_parquet(src, columns=_PITCH_COLS)
    if games_current is None:
        if not _GAMES_CURRENT.exists():
            raise FileNotFoundError(f"games_current.parquet not found at {_GAMES_CURRENT}.")
        games_current = pd.read_parquet(_GAMES_CURRENT)

    if len(pitch_df) == 0:
        out = pd.DataFrame(columns=OUTPUT_COLS)
    else:
        starts = build_starts(pitch_df)
        starts = _walk_forward_lag1(starts)
        pivoted = _pivot_to_games(starts)
        bridged = _bridge_to_event_id(pivoted, games_current)
        out = bridged.reindex(columns=OUTPUT_COLS)
        out = out.sort_values("event_id", kind="mergesort").reset_index(drop=True)

    dest.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(str(dest), index=False)
    return dest


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="savant_full__<year>.parquet -> leak-free SP LAG-1 carryover as-of "
                    "(pitch count, rest days)")
    ap.add_argument("--year", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    path = build_carryover_asof(args.year, out_path=args.out)
    df = pd.read_parquet(str(path))
    print(f"LEAK-FREE SP carryover as-of ({args.year}; LAG-1 pitch count + rest days).")
    print("NOT a market edge. b2b/rest is heavily priced -- expect NULL/small. Gate decides honestly next.")
    print(f"Wrote {path}  ({len(df)} game rows)")
    if len(df):
        print(df.dropna(subset=["sp_prior_pitch_count_diff_asof"]).head(3).to_string())
