"""scripts.platformkit.ingame.statcast_winprob_join -- LEAK-FREE join of the richer
Statcast per-pitch fields onto the proven ESPN in-game win-prob BASE, for the additive
win-prob gate. Closes the prior TIER3_BLOCKED now that an ESPN-overlapping, score-bearing
Statcast sample exists (data/cache/statcast/statcast__<season>_overlap.parquet).

BASE corpus  = data/cache/ingame/mlb_pitch_states__<season>.parquet (state_diff,
               frac_elapsed, p0, win/loss OUTCOME label, half_inning_label, game_id).
RICHER fields= release_spin_rate, estimated_woba_using_speedangle, release_speed -- live
               ONLY in the Statcast overlap parquet.

GAME JOIN: ESPN team codes -> Statcast codes via a small crosswalk; key = (date, home,
away). Every ESPN game in the opening windows joins (verified 396/396).

AS-OF (NO LEAK): per game, Statcast pitches are ordered chronologically (inning, topbot,
at_bat_number, pitch_number) and an EXPANDING mean of each richer field is computed.
Each ESPN state (which carries half_inning_label e.g. 'top1') is assigned the expanding
mean AS OF THE START of its half-inning -- i.e. aggregating ONLY pitches in STRICTLY
EARLIER half-innings. The current half-inning's pitches NEVER enter the feature, so the
feature cannot see the in-progress result. Pre-first-pitch states (no prior pitches) get
NaN -> a 0 shift downstream (never fabricated). The realized win/loss is the LABEL only.

Reads data/cache/ only; no registry write, no flag, no $/edge. ASCII; <=300 LOC.
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_ESPN_DIR = os.path.join(_REPO, "data", "cache", "ingame")
_STATCAST_DIR = os.path.join(_REPO, "data", "cache", "statcast")
_RICHER = ("release_spin_rate", "estimated_woba_using_speedangle", "release_speed")
# ESPN team code -> Statcast team code (only the 8 that differ).
_XW = {"ARI": "AZ", "CUB": "CHC", "KAN": "KC", "OAK": "ATH", "SDG": "SD",
       "SFO": "SF", "TAM": "TB", "WAS": "WSH"}
_HALF_RE = re.compile(r"^(top|bot)(\d+)$")


def _espn_path(season: int) -> str:
    return os.path.join(_ESPN_DIR, f"mlb_pitch_states__{season}.parquet")


def _statcast_path(season: int) -> str:
    return os.path.join(_STATCAST_DIR, f"statcast__{season}_overlap.parquet")


def has_overlap_corpus(season: int) -> bool:
    return os.path.exists(_espn_path(season)) and os.path.exists(_statcast_path(season))


def _xw(code: str) -> str:
    return _XW.get(str(code), str(code))


def _gkey_espn(df: pd.DataFrame) -> pd.Series:
    d = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return d + "|" + df["home_team"].map(_xw) + "|" + df["away_team"].map(_xw)


def _gkey_statcast(df: pd.DataFrame) -> pd.Series:
    d = pd.to_datetime(df["game_date"]).dt.strftime("%Y-%m-%d")
    return d + "|" + df["home_team"].astype(str) + "|" + df["away_team"].astype(str)


def _half_order(inning: int, topbot: str) -> int:
    """Monotone chronological rank of a half-inning: top before bot within an inning."""
    return inning * 2 + (0 if str(topbot).lower().startswith("top") else 1)


def _statcast_asof_by_half(sc_game: pd.DataFrame) -> Dict[int, Tuple[float, float, float]]:
    """Expanding mean of each richer field AS OF THE START of each half-inning (i.e. over
    pitches in STRICTLY earlier half-innings). Returns {half_rank -> (spin, woba, speed)}.
    Leak-free: a half-inning's own pitches are excluded from its own feature."""
    g = sc_game.copy()
    g["_hr"] = [_half_order(int(i), tb) for i, tb in
                zip(g["inning"], g["inning_topbot"])]
    g = g.sort_values(["_hr", "at_bat_number", "pitch_number"])
    out: Dict[int, Tuple[float, float, float]] = {}
    run_sum = {c: 0.0 for c in _RICHER}
    run_cnt = {c: 0 for c in _RICHER}
    prev_hr: Optional[int] = None
    for hr, sub in g.groupby("_hr", sort=True):
        # snapshot BEFORE adding this half-inning's pitches = as-of start of this half.
        out[int(hr)] = tuple(
            (run_sum[c] / run_cnt[c]) if run_cnt[c] else float("nan") for c in _RICHER
        )  # type: ignore[assignment]
        for c in _RICHER:
            vals = pd.to_numeric(sub[c], errors="coerce").to_numpy(dtype=float)
            fin = vals[np.isfinite(vals)]
            run_sum[c] += float(fin.sum())
            run_cnt[c] += int(fin.size)
        prev_hr = int(hr)
    return out


def _parse_half(label: str) -> Optional[int]:
    m = _HALF_RE.match(str(label).strip().lower())
    if not m:
        return None
    return _half_order(int(m.group(2)), m.group(1))


def build_joined_states(season: int) -> Tuple[List[dict], Dict[str, object]]:
    """Join richer Statcast as-of features onto ESPN BASE states. Returns (states, info).
    states carry the frozen base schema + spin/woba/speed (NaN where no prior pitch).
    Empty + info.reasons when the corpora/overlap are missing -- never 0-filled."""
    info: Dict[str, object] = {"season": season,
                               "espn_exists": os.path.exists(_espn_path(season)),
                               "statcast_exists": os.path.exists(_statcast_path(season))}
    if not (info["espn_exists"] and info["statcast_exists"]):
        info["overlap_games"] = 0
        info["reasons"] = ["NO_OVERLAP_CORPUS"]
        return [], info
    e = pd.read_parquet(_espn_path(season))
    s = pd.read_parquet(_statcast_path(season))
    e = e.copy()
    s = s.copy()
    e["gk"] = _gkey_espn(e)
    s["gk"] = _gkey_statcast(s)
    shared = set(e["gk"]) & set(s["gk"])
    info["espn_games"] = int(e["gk"].nunique())
    info["statcast_games"] = int(s["gk"].nunique())
    info["overlap_games"] = len(shared)
    if not shared:
        info["reasons"] = ["ZERO_OVERLAPPING_GAMES"]
        return [], info
    # per-game as-of half-inning lookup from Statcast.
    asof: Dict[str, Dict[int, Tuple[float, float, float]]] = {}
    for gk, sg in s[s["gk"].isin(shared)].groupby("gk", sort=False):
        asof[gk] = _statcast_asof_by_half(sg)
    states: List[dict] = []
    matched_rows = 0
    e = e[e["gk"].isin(shared)]
    for r in e.itertuples(index=False):
        gk = r.gk
        hr = _parse_half(r.half_inning_label)
        spin = woba = speed = float("nan")
        lut = asof.get(gk)
        if lut is not None and hr is not None and hr in lut:
            spin, woba, speed = lut[hr]
            matched_rows += 1
        fe = max(0.0, min(1.0, float(r.frac_elapsed)))
        states.append({
            "game_id": r.game_id, "state_diff": float(r.state_diff),
            "frac_elapsed": fe, "p0": float(r.p0), "outcome": int(r.outcome),
            "sc_spin": float(spin), "sc_woba": float(woba), "sc_speed": float(speed),
        })
    info["espn_states"] = len(states)
    info["matched_asof_rows"] = matched_rows
    info["richer_fields"] = list(_RICHER)
    return states, info


__all__ = ["build_joined_states", "has_overlap_corpus", "_RICHER", "_XW",
           "_statcast_asof_by_half", "_parse_half", "_half_order"]
