"""domains.mlb.sp_velo_materialize -- REDESIGNED fatigue proxy materializer for the
in-game SP-fatigue gate (wave-30 lane 4 redesign; wave-29's pitch-count-tercile design
was NOT_TESTABLE -- the planted null matched the real improvement, an added-flexibility
artifact). This module swaps the proxy to WITHIN-START VELOCITY DECLINE computed from
REAL Statcast release_speed + a REAL per-pitcher identity (not the ESPN corpus's
staff-level pitch count, which has NO_SP_IDENTITY -- see
domains/mlb/ingest_sp_fatigue_prop_states.py).

SOURCES (both already on-disk, no new network calls):
  1. data/cache/statcast/statcast__<season>_overlap.parquet -- real per-pitch Statcast
     (release_speed, pitcher id, game_pk, inning_topbot) for EXACTLY the ESPN base's own
     game-dates (built by domains/mlb/acquire_statcast_overlap.py). 2022 + 2023 only.
  2. data/cache/ingame/mlb_pitch_states__<season>.parquet -- the PROVEN win-prob as-of
     state corpus (state_diff, frac_elapsed, p0, outcome) the wave-29 gate already used.

JOIN: Statcast has no shared game id with the ESPN corpus (game_pk int vs ESPN's
'YYYY-MM-DD-HOME-AWAY-N' string), so games are matched by (date, unordered normalized
team-pair) -- reusing domains.mlb.game_pk_bridge.GC_TO_PG_TEAM (the ESPN dialect matches
that map's "GC" side exactly: ARI/CUB/KAN/SDG/SFO/TAM/WAS/OAK). A date+team-pair key that
resolves to >1 game on either side (doubleheader) is AMBIGUOUS and dropped, never guessed.

STARTER ISOLATION: for each (game, pitching side) the STARTER is the pitcher of the
earliest inning-1 pitch (domains.mlb.acquire_statcast_sample._starter_for_side pattern,
reimplemented here to avoid a network-fetch-module import). Only that pitcher's own
pitches (in order) are used -- reliever pitches never enter the proxy.

VELO_DECLINE (the new proxy, replacing wave-29's velo_decline_vs_early / pitch-count
tercile): for the i-th pitch (0-indexed) of a starter's outing, once >=15 pitches have
been thrown,
    velo_decline = mean(release_speed, pitches[i-14:i+1])   (last 15, trailing, as-of)
                 - mean(release_speed, pitches[0:15])         (first 15 of the outing)
NEGATIVE = slower than the outing's opening 15 pitches = more fatigued (literal spec
formula: last-15 minus first-15, so velocity LOSS shows up as a negative number). AS-OF:
pitch i's value uses only pitches up to and including i (the trailing window), never a
future pitch, and the "first 15" baseline is fixed pitches 0..14 of THAT SAME outing
(known already once pitch 14 has been thrown) -- no cross-start or cross-game leakage.
Pitches before the 15th (index <14) get NaN (not enough of either window yet); the gate
module bands NaN to the least-fatigued tercile by convention, same rule as wave-29's io.

OUTPUT: one row per as-of PITCH-STATE for a matched starter's outing, attaching the
proven win-prob columns (state_diff, frac_elapsed, p0, outcome) from the ESPN row at the
SAME position (0-indexed) in that side's ESPN pitch sequence (sp_pitch_count_prior ==
this pitch's 0-indexed position) -- i.e. we only ever consume the ESPN rows that fall
within the starter's own pitch count, never a reliever's. Persisted as a consolidated
parquet with as_of/corpus_id columns (storage R5) under data/domains/mlb/.

HONESTY: if release_speed coverage in the matched overlap is too thin (see
MIN_COVERAGE), or the outing-eligible row count is too small, materialize() returns
status=BLOCKED with the measured coverage number -- no silent fallback to a weaker proxy.

PROPOSAL-ONLY: reads only data/cache/ (data store); writes only
data/domains/mlb/sp_velo_states.parquet. Never data/registry/, no flag, no $/edge.
ASCII only. <=300 LOC. ONLY reads real on-disk data, never fabricates a row.
CLI: python -m domains.mlb.sp_velo_materialize
"""
from __future__ import annotations

import argparse
import glob
import math
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from domains.mlb.game_pk_bridge import GC_TO_PG_TEAM

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_ESPN_DIR = os.path.join(_REPO, "data", "cache", "ingame")
_STATCAST_DIR = os.path.join(_REPO, "data", "cache", "statcast")
OUT = os.path.join(_REPO, "data", "domains", "mlb", "sp_velo_states.parquet")
CORPUS_ID = "sp_velo_materialize_v1"

_WINDOW = 15          # trailing/leading pitch-count window for the decline proxy.
MIN_COVERAGE = 0.60   # honest floor: release_speed non-null fraction in the join.
_SEASONS = (2022, 2023)


def _norm_team(code: object) -> str:
    s = str(code).strip().upper()
    return GC_TO_PG_TEAM.get(s, s)


def _pair_key(date_val: object, a: str, b: str) -> Tuple[str, Tuple[str, str]]:
    d = str(pd.to_datetime(date_val).date())
    return d, tuple(sorted((_norm_team(a), _norm_team(b))))


def match_games(espn: pd.DataFrame, statcast: pd.DataFrame) -> Dict[str, int]:
    """(date, team-pair) join espn.game_id -> statcast.game_pk. Ambiguous
    (doubleheader) keys on EITHER side are dropped -- never guessed."""
    e = espn.drop_duplicates("game_id")[["game_id", "date", "home_team", "away_team"]]
    s = statcast.drop_duplicates("game_pk")[["game_pk", "game_date", "home_team", "away_team"]]
    e_by_key: Dict[Tuple[str, Tuple[str, str]], List[str]] = {}
    for r in e.itertuples(index=False):
        e_by_key.setdefault(_pair_key(r.date, r.home_team, r.away_team), []).append(r.game_id)
    s_by_key: Dict[Tuple[str, Tuple[str, str]], List[int]] = {}
    for r in s.itertuples(index=False):
        s_by_key.setdefault(_pair_key(r.game_date, r.home_team, r.away_team), []).append(int(r.game_pk))
    out: Dict[str, int] = {}
    for k, gids in e_by_key.items():
        pks = s_by_key.get(k)
        if not pks or len(gids) > 1 or len(pks) > 1:
            continue  # unmatched or ambiguous (doubleheader) -- dropped, never guessed
        out[gids[0]] = pks[0]
    return out


def _starter_for_side(side_df: pd.DataFrame) -> Optional[int]:
    """Starter = pitcher of the earliest inning-1 pitch for this pitching side."""
    i1 = side_df[side_df["inning"] == 1]
    if i1.empty:
        return None
    i1 = i1.sort_values(["at_bat_number", "pitch_number"])
    return int(i1.iloc[0]["pitcher"])


def _velo_decline_series(velos: List[float], window: int = _WINDOW) -> List[float]:
    """AS-OF velo decline per pitch index i: mean(last `window` incl. i) minus
    mean(first `window` of the whole outing) -- literal spec formula (trailing minus
    early). NaN until i>=window-1 (not enough of either window). NEGATIVE = slower
    (more fatigued) than the outing's opening `window` pitches; the gate module bands
    the MOST-negative tercile as 'fatigued' (see ingame_sp_fatigue_velo_gate_mlb_io)."""
    n = len(velos)
    out = [float("nan")] * n
    finite0 = [v for v in velos[:window] if not math.isnan(v)]
    if len(finite0) < window:
        return out  # not enough clean pitches to fix an opening baseline at all
    early_mean = sum(finite0) / len(finite0)
    for i in range(window - 1, n):
        trail = [v for v in velos[i - window + 1:i + 1] if not math.isnan(v)]
        if len(trail) < window:
            continue
        out[i] = (sum(trail) / len(trail)) - early_mean
    return out


def _starter_rows(statcast_side: pd.DataFrame, sp: int) -> pd.DataFrame:
    sd = statcast_side[statcast_side["pitcher"] == sp].sort_values(
        ["inning", "at_bat_number", "pitch_number"])
    return sd.reset_index(drop=True)


def build_states(season: int, espn_dir: Optional[str] = None,
                  statcast_dir: Optional[str] = None) -> Tuple[pd.DataFrame, dict]:
    """One season -> (states_df, coverage_dict). states_df is empty if inputs absent."""
    edir = espn_dir or _ESPN_DIR
    sdir = statcast_dir or _STATCAST_DIR
    espn_fp = os.path.join(edir, f"mlb_pitch_states__{season}.parquet")
    sc_fp = os.path.join(sdir, f"statcast__{season}_overlap.parquet")
    cov = {"season": season, "espn_on_disk": os.path.exists(espn_fp),
           "statcast_on_disk": os.path.exists(sc_fp)}
    if not (cov["espn_on_disk"] and cov["statcast_on_disk"]):
        return pd.DataFrame(), cov
    espn = pd.read_parquet(espn_fp)
    sc = pd.read_parquet(sc_fp)
    cov["release_speed_coverage"] = round(float(sc["release_speed"].notna().mean()), 4)
    cov["pitcher_id_coverage"] = round(float(sc["pitcher"].notna().mean()), 4)

    game_map = match_games(espn, sc)  # espn.game_id -> statcast.game_pk
    cov["espn_games"] = int(espn["game_id"].nunique())
    cov["statcast_games"] = int(sc["game_pk"].nunique())
    cov["matched_games"] = len(game_map)

    rows: List[dict] = []
    n_starters_kept = 0
    for gid, pk in game_map.items():
        eg = espn[espn["game_id"] == gid].sort_values("asof_idx")
        sg = sc[sc["game_pk"] == pk]
        if eg.empty or sg.empty:
            continue
        for label_prefix, pitch_side, topbot in (("top", "home", "Top"), ("bottom", "away", "Bottom")):
            side_e = eg[eg["half_inning_label"].str.startswith(label_prefix)]
            side_s = sg[sg["inning_topbot"] == topbot]
            if side_e.empty or side_s.empty:
                continue
            sp = _starter_for_side(side_s)
            if sp is None:
                continue
            sd = _starter_rows(side_s, sp)
            velos = sd["release_speed"].astype(float).tolist()
            if len(velos) < _WINDOW:
                continue
            decline = _velo_decline_series(velos, window=_WINDOW)
            # sp_pitch_count_prior == this side's 0-indexed pitch position within the
            # ESPN sequence -- restrict to positions < n_pitches so ONLY the starter's
            # own pitches are consumed (never a reliever's, once the count exceeds it).
            side_e_idx = side_e.set_index("sp_pitch_count_prior")
            for i in range(len(sd)):
                if i not in side_e_idx.index:
                    continue
                er = side_e_idx.loc[i]
                if isinstance(er, pd.DataFrame):  # duplicate index guard, take first
                    er = er.iloc[0]
                v = decline[i]
                rows.append({
                    "game_id": str(gid), "game_pk": int(pk), "season": int(season),
                    "date": str(er["date"]), "pitch_side": pitch_side,
                    "proxy_pitcher": int(sp),
                    "pitch_index": int(i), "n_pitches_outing": int(len(sd)),
                    "release_speed": float(velos[i]) if not math.isnan(velos[i]) else float("nan"),
                    "velo_decline": float(v) if v is not None and not math.isnan(v) else float("nan"),
                    "state_diff": float(er["state_diff"]),
                    "frac_elapsed": float(er["frac_elapsed"]),
                    "p0": float(er["p0"]),
                    "outcome": int(er["outcome"]),
                })
            n_starters_kept += 1
    df = pd.DataFrame(rows)
    cov["n_starter_outings"] = n_starters_kept
    cov["n_states"] = int(len(df))
    cov["velo_decline_coverage"] = (round(float(df["velo_decline"].notna().mean()), 4)
                                     if not df.empty else 0.0)
    return df, cov


def materialize(seasons: Tuple[int, ...] = _SEASONS,
                 espn_dir: Optional[str] = None, statcast_dir: Optional[str] = None,
                 out: str = OUT) -> dict:
    """Build + persist the consolidated parquet across all requested seasons.
    Honest BLOCKED (not written) if release_speed coverage is below MIN_COVERAGE or
    no usable rows result -- never substitutes a weaker proxy silently."""
    frames: List[pd.DataFrame] = []
    per_season: List[dict] = []
    for season in seasons:
        df, cov = build_states(season, espn_dir=espn_dir, statcast_dir=statcast_dir)
        per_season.append(cov)
        if not df.empty:
            frames.append(df)
    if not frames:
        return {"status": "BLOCKED", "reason": "NO_USABLE_SEASON",
                "per_season": per_season}
    all_df = pd.concat(frames, ignore_index=True)
    raw_cov = float(np.mean([c.get("release_speed_coverage", 0.0) for c in per_season
                              if c.get("statcast_on_disk")])) if per_season else 0.0
    if raw_cov < MIN_COVERAGE:
        return {"status": "BLOCKED", "reason": "RELEASE_SPEED_COVERAGE_TOO_THIN",
                "release_speed_coverage": round(raw_cov, 4), "min_required": MIN_COVERAGE,
                "per_season": per_season}
    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    all_df["as_of"] = as_of
    all_df["corpus_id"] = CORPUS_ID
    os.makedirs(os.path.dirname(out), exist_ok=True)
    all_df.to_parquet(out, index=False)
    return {"status": "OK", "out": out, "n_states": int(len(all_df)),
            "n_starter_outings": int(sum(c.get("n_starter_outings", 0) for c in per_season)),
            "velo_decline_coverage": round(float(all_df["velo_decline"].notna().mean()), 4),
            "release_speed_coverage": round(raw_cov, 4),
            "per_season": per_season, "as_of": as_of}


def load(path: str = OUT) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_parquet(path)


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Materialize SP within-start velo-decline states.")
    ap.parse_args(argv)
    res = materialize()
    print(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["match_games", "build_states", "materialize", "load", "OUT", "CORPUS_ID",
           "MIN_COVERAGE", "_WINDOW"]
