"""domains.mlb.acquire_statcast_sample -- BOUNDED keyless Statcast acquisition for
the SP-fatigue K-prop gate (solves NO_SEASON_OVERLAP + NO_SP_IDENTITY).

WHY: the on-disk K source (player_gamelogs.parquet) is 2026-only and the ESPN pitch
parquet has NO pitcher_id / no SP-reliever boundary. baseballsavant (keyless; the same
source pybaseball.statcast wraps) carries per-pitch pitcher + batter + events
(strikeout etc -> real per-start K BY STARTER) + release_speed + release_spin_rate +
estimated_woba + pitch_type. This module BOUNDED-acquires a sample across TWO seasons,
caches raw per-pitch parquet to data/cache/statcast/, and derives a clean per-(game,
pitcher) STARTER table with a leak-free per-start K LABEL keyed to the STARTER.

BOUNDED + POLITE (do NOT pull whole seasons -- millions of rows):
  * fetch ONE day at a time via the keyless CSV export, with a delay between calls;
  * a small list of date windows per season (a few weeks), enough for the gate
    (>=150 starter-starts/season with >=2 prior starts), NOT the full season;
  * cache each raw day; skip days already cached (idempotent, re-runnable).

LEAK-FREE STARTER ISOLATION: the STARTER for a (game_pk, pitching-side) is the pitcher
who threw the FIRST pitch of inning 1 for that side (earliest at_bat_number/pitch_number
in inning 1). The start's K LABEL = count of events=='strikeout' charged to THAT pitcher
in THAT game. Fatigue features use ONLY pitches in that outing (decline slope, early
velo, mix entropy, spin) -- start N's own pitches never enter start N's PROFILE (the
profile/shift1 step lives in ingest_sp_fatigue_prop_states; here we emit per-start rows).

WRITES ONLY data/cache/statcast/ (the data store). NEVER data/registry/, NO sentinel,
NO flag, NO $/edge. ASCII-only; <=300 LOC. Per-file test in tests/.
CLI: python -m domains.mlb.acquire_statcast_sample --season 2023 --days 18
"""
from __future__ import annotations

import argparse
import io
import logging
import math
import time
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests

log = logging.getLogger(__name__)
_REPO = Path(__file__).resolve().parents[2]
_CACHE = _REPO / "data" / "cache" / "statcast"
_URL = "https://baseballsavant.mlb.com/statcast_search/csv"
_HDR = {"User-Agent": "Mozilla/5.0 (research; bounded SP-fatigue sample)"}
_DELAY_S = 4.0  # polite delay between day fetches
_BREAKING = frozenset({"SL", "CU", "KC", "ST", "SV", "CS", "SC", "FS", "FO"})
_EARLY_N = 5
# columns we keep from the 119-col raw export (the gate-relevant subset).
# score + post_* columns added so an OVERLAP sample can carry a run-diff win-prob base
# / outcome label and join onto the ESPN base; launch_speed added for completeness.
_KEEP = ["game_pk", "game_date", "inning", "inning_topbot", "at_bat_number",
         "pitch_number", "pitcher", "batter", "events", "release_speed",
         "release_spin_rate", "estimated_woba_using_speedangle", "pitch_type",
         "balls", "strikes", "outs_when_up", "home_team", "away_team",
         "home_score", "away_score", "bat_score", "post_home_score",
         "post_away_score", "launch_speed"]
# season -> start dates of the (bounded) windows; total `days` is split across them.
# CONTIGUOUS windows (not scattered) so a starter (pitches ~every 5 days) recurs
# >=3 times -> yields starts with >=2 prior starts for a leak-free profile.
_WINDOWS = {
    2022: ["2022-05-02", "2022-07-04"],
    2023: ["2023-05-01", "2023-07-03"],
}


# --------------------------------------------------------------------------- #
# Bounded keyless fetch (one day at a time, cached, idempotent).
# --------------------------------------------------------------------------- #
def _day_csv(day: str, timeout: int = 90) -> Optional[pd.DataFrame]:
    """Fetch one game-date of pitcher details from the keyless savant CSV export."""
    params = {"all": "true", "type": "details", "game_date_gt": day,
              "game_date_lt": day, "min_pitches": "0", "min_results": "0",
              "group_by": "name", "sort_col": "pitches", "player_type": "pitcher",
              "min_pas": "0"}
    r = requests.get(_URL, params=params, headers=_HDR, timeout=timeout)
    if r.status_code != 200 or len(r.content) < 200:
        log.warning("day %s HTTP %s bytes %s", day, r.status_code, len(r.content))
        return None
    df = pd.read_csv(io.StringIO(r.text), low_memory=False)
    keep = [c for c in _KEEP if c in df.columns]
    return df[keep].copy()


def _date_range(start: str, n_days: int) -> List[str]:
    d0 = pd.Timestamp(start)
    return [(d0 + pd.Timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n_days)]


def acquire_season(season: int, days: int = 18, delay_s: float = _DELAY_S,
                   cache_dir: Optional[Path] = None) -> pd.DataFrame:
    """BOUNDED-acquire a season sample: a few windows x `days`, cache per day, concat.

    Idempotent: a cached per-day parquet is reused, no re-fetch. Returns the raw
    per-pitch frame (kept-column subset) for the season sample.
    """
    cdir = Path(cache_dir) if cache_dir else _CACHE
    raw_dir = cdir / "raw_days"
    raw_dir.mkdir(parents=True, exist_ok=True)
    starts = _WINDOWS.get(season, [f"{season}-05-01"])
    per_window = max(1, math.ceil(days / len(starts)))
    parts: List[pd.DataFrame] = []
    for ws in starts:
        for day in _date_range(ws, per_window):
            fp = raw_dir / f"day__{day}.parquet"
            if fp.exists():
                parts.append(pd.read_parquet(fp))
                continue
            df = _day_csv(day)
            if df is None or df.empty:
                time.sleep(delay_s)
                continue
            df.to_parquet(fp, index=False)
            parts.append(df)
            log.info("fetched %s rows=%d", day, len(df))
            time.sleep(delay_s)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, ignore_index=True)
    out = out[pd.to_datetime(out["game_date"]).dt.year == season].reset_index(drop=True)
    return out




# --------------------------------------------------------------------------- #
# Starter isolation + per-start fatigue features + leak-free K LABEL.
# --------------------------------------------------------------------------- #
def _ols_slope(y: List[float]) -> float:
    pts = [(i, v) for i, v in enumerate(y) if not (v is None or math.isnan(v))]
    if len(pts) < 2:
        return float("nan")
    n = float(len(pts))
    sx = sum(p[0] for p in pts)
    sy = sum(p[1] for p in pts)
    sxx = sum(p[0] * p[0] for p in pts)
    sxy = sum(p[0] * p[1] for p in pts)
    den = n * sxx - sx * sx
    return (n * sxy - sx * sy) / den if den else float("nan")


def _entropy(types: List[str]) -> float:
    counts: Dict[str, int] = {}
    for t in types:
        if t and t != "nan":
            counts[t] = counts.get(t, 0) + 1
    tot = sum(counts.values())
    if not tot:
        return float("nan")
    return -sum((c / tot) * math.log(c / tot) for c in counts.values())


def _starter_for_side(side_df: pd.DataFrame) -> Optional[int]:
    """Starter = pitcher of the earliest inning-1 pitch for this pitching side."""
    i1 = side_df[side_df["inning"] == 1]
    if i1.empty:
        return None
    i1 = i1.sort_values(["at_bat_number", "pitch_number"])
    return int(i1.iloc[0]["pitcher"])


def build_starter_table(pitch_df: pd.DataFrame, season: int) -> pd.DataFrame:
    """One row per (game_pk, pitching-side, STARTER) with leak-free per-start K + fatigue.

    pitching side: inning_topbot 'Top' -> away batting -> HOME team pitching, and vice
    versa. pitch_team is the staff's team (join key for the prior-N profile). label_k is
    the start's strikeout total CHARGED TO THE STARTER ONLY (events=='strikeout' on the
    starter's pitches) -- a LABEL, never a feature.
    """
    if pitch_df.empty:
        return pd.DataFrame()
    df = pitch_df.copy()
    df["pitch_team"] = df.apply(
        lambda r: r["home_team"] if str(r["inning_topbot"]).startswith("Top")
        else r["away_team"], axis=1)
    rows: List[dict] = []
    for gpk, g in df.groupby("game_pk", sort=False):
        for tb, side in g.groupby("inning_topbot", sort=False):
            sp = _starter_for_side(side)
            if sp is None:
                continue
            sd = side[side["pitcher"] == sp].sort_values(
                ["inning", "at_bat_number", "pitch_number"])
            if sd.empty:
                continue
            velos = sd["release_speed"].astype(float).tolist()
            finite = [v for v in velos if not math.isnan(v)]
            early = [v for v in velos[:_EARLY_N] if not math.isnan(v)]
            spins = sd["release_spin_rate"].astype(float).tolist()
            spin_f = [s for s in spins if not math.isnan(s)]
            types = [str(t) for t in sd["pitch_type"].tolist()]
            brk = sum(1 for t in types if t in _BREAKING)
            label_k = int((sd["events"] == "strikeout").sum())
            rows.append({
                "season": season, "game_id": int(gpk), "date": str(sd["game_date"].iloc[0]),
                "pitcher": sp, "pitch_team": sd["pitch_team"].iloc[0],
                "pitch_side": "home" if str(tb).startswith("Top") else "away",
                "n_pitches": int(len(sd)),
                "innings_pitched": int(sd["inning"].nunique()),
                "mean_velo": (sum(finite) / len(finite)) if finite else float("nan"),
                "mean_early_velo": (sum(early) / len(early)) if early else float("nan"),
                "velo_decline_slope": _ols_slope(velos),
                "mean_spin": (sum(spin_f) / len(spin_f)) if spin_f else float("nan"),
                "pitch_mix_entropy": _entropy(types),
                "frac_breaking": (brk / len(types)) if types else float("nan"),
                "label_k": label_k,  # LABEL ONLY -- never a feature
            })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["date", "game_id", "pitch_side"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Orchestration.
# --------------------------------------------------------------------------- #
def run_season(season: int, days: int = 18, cache_dir: Optional[Path] = None) -> dict:
    """Acquire -> write raw sample parquet -> derive + write starter table. Report stats."""
    cdir = Path(cache_dir) if cache_dir else _CACHE
    cdir.mkdir(parents=True, exist_ok=True)
    raw = acquire_season(season, days=days, cache_dir=cdir)
    if raw.empty:
        return {"season": season, "status": "INSUFFICIENT_DATA", "raw_rows": 0}
    raw_fp = cdir / f"statcast__{season}_sample.parquet"
    raw.to_parquet(raw_fp, index=False)
    starters = build_starter_table(raw, season)
    st_fp = cdir / f"starter_table__{season}.parquet"
    starters.to_parquet(st_fp, index=False)
    # per-pitcher prior-start count (>=2 priors -> profile-eligible)
    eligible = 0
    if not starters.empty:
        cnt = starters.groupby("pitcher").cumcount()
        eligible = int((cnt >= 2).sum())
    nn = {c: round(float(raw[c].notna().mean()), 3) for c in
          ["pitcher", "events", "release_speed", "release_spin_rate",
           "estimated_woba_using_speedangle"] if c in raw.columns}
    return {"season": season, "status": "OK", "raw_rows": int(len(raw)),
            "raw_parquet": str(raw_fp), "starter_parquet": str(st_fp),
            "starter_starts": int(len(starters)),
            "starts_with_2plus_priors": eligible,
            "unique_starters": int(starters["pitcher"].nunique()) if not starters.empty else 0,
            "nonnull": nn}


def _main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Bounded keyless Statcast SP-fatigue sample.")
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--days", type=int, default=18)
    a = ap.parse_args(argv)
    res = run_season(a.season, days=a.days)
    print(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["acquire_season", "build_starter_table", "run_season",
           "_starter_for_side", "_ols_slope", "_entropy",
           "_day_csv", "_KEEP", "_DELAY_S", "_CACHE", "_REPO"]
