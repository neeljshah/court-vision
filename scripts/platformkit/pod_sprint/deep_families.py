"""scripts.platformkit.pod_sprint.deep_families -- feature builders for prereg families
M/S/V/X (see DEEP_FEATURES_PREREG.md). Same walk-forward pass shape as gbm_nba_ml.py /
gbm_nba_enriched.py: row i's features depend only on games strictly BEFORE i. Reuses
(never edits) gbm_nba_ml's Elo/pace machinery -- _BASE_BUILD_FEATURES captured before any
patching, exactly like gbm_nba_enriched.py does.

M1 tank_gradient: games-back from the conference's 8th-best win% (as-of, from a static
    team->conference dict below) x (fraction of season elapsed past 0.7, else 0).
M2 seeding_stakes: NOT_BUILT -- clinch detection needs playoff bracket math this box
    corpus doesn't have on disk.
M3 season_phase: (avg of the two teams' games-played-this-season)/82, clipped [0,1], + square.
S1 three_in_four: count of a team's games (incl. this one) within a trailing 4-day window.
S2 road_trip_position: consecutive-away-games counter, 1-indexed, home team always 0.
S3 timezone: NOT_BUILT -- no venue-tz table on disk.
S4 b2b asymmetry: b2b_home_only / b2b_road_only interaction dummies -- NOT a duplicate of
    the base b2b_home/b2b_away flags (those already exist in every candidate's feature
    pool); this isolates the "only one side is on a b2b" cases.
V1 fg3_luck: trailing-10 3P% minus season-to-date 3P% (0.0 if fg3m/fg3a absent, or history
    thin -- premise-checked below).
V2 pythag_gap: trailing-10 (base model's own l10_wpct) minus expanding pythagorean
    expectation from season PF/PA, exponent 13.91.
V3 garbage_mov: ALTERNATE Elo pass, MOV capped at 20 -- a feature-set SWAP (see
    build_features_capped_mov), never combined additively with the others.
X1 pace_product: pace_home * pace_away, a static transform of two already-base columns.
X2/X3: NOT_BUILT -- rim-pressure/size-spacing percentile joins are Family-P-adjacent
    (need per-player profiles this harness doesn't build).
"""
from __future__ import annotations

from collections import deque
from typing import Dict, List

import numpy as np
import pandas as pd

from scripts.platformkit.models import gbm_nba_ml as g  # noqa: E402

_BASE_BUILD_FEATURES = g.build_features  # captured before any monkeypatch, reused below

# Static team->conference map (real NBA 30; All-Star placeholder rows in the box corpus
# -- STARS/STRIPES/WORLD -- are absent on purpose and read as unknown -> feature 0.0).
_CONFERENCE: Dict[str, str] = {
    "ATL": "E", "BOS": "E", "BKN": "E", "CHA": "E", "CHI": "E", "CLE": "E", "DET": "E",
    "IND": "E", "MIA": "E", "MIL": "E", "NYK": "E", "ORL": "E", "PHI": "E", "TOR": "E",
    "WAS": "E",
    "DAL": "W", "DEN": "W", "GSW": "W", "HOU": "W", "LAC": "W", "LAL": "W", "MEM": "W",
    "MIN": "W", "NOP": "W", "OKC": "W", "PHX": "W", "POR": "W", "SAC": "W", "SAS": "W",
    "UTA": "W",
}
_PYTHAG_EXP = 13.91
_MIN_ASOF_N = 3  # ponytail: same small floor gbm_nba_enriched uses; no tuning done


def _season_id(d: pd.Timestamp) -> int:
    """NBA season label = the year it starts in (Oct-Jul); Aug/Sep treated as the new season."""
    return d.year if d.month >= 8 else d.year - 1


def _tank(team: str, phase: float, wins: Dict[str, int], losses: Dict[str, int]) -> float:
    factor = max(0.0, phase - 0.7)
    conf = _CONFERENCE.get(team)
    if conf is None or factor == 0.0:
        return 0.0
    recs = []
    for t, c in _CONFERENCE.items():
        if c != conf:
            continue
        w, l = wins.get(t, 0), losses.get(t, 0)
        gp = w + l
        recs.append((w / gp if gp > 0 else 0.0, w, l))
    recs.sort(key=lambda r: -r[0])
    w8, l8 = (recs[7][1], recs[7][2]) if len(recs) >= 8 else (0, 0)
    w_t, l_t = wins.get(team, 0), losses.get(team, 0)
    games_back = ((w8 - w_t) + (l_t - l8)) / 2.0
    return max(0.0, games_back - 2.0) * factor


def _fg3_luck(trail: deque, season_m: float, season_a: float) -> float:
    if len(trail) < _MIN_ASOF_N:
        return 0.0
    tm = sum(x[0] for x in trail); ta = sum(x[1] for x in trail)
    if ta <= 0 or season_a <= 0:
        return 0.0
    return (tm / ta) - (season_m / season_a)


def _pythag_gap(l10_wpct: float, pf: float, pa: float) -> float:
    if pf <= 0 and pa <= 0:
        return 0.0
    exp = pf ** _PYTHAG_EXP / (pf ** _PYTHAG_EXP + pa ** _PYTHAG_EXP)
    return float(l10_wpct) - exp


def _deep_pass(box: pd.DataFrame, base_feat: pd.DataFrame) -> pd.DataFrame:
    """One shared walk-forward pass building M1/M3/S1/S2/S4/V1/V2, row-aligned with
    base_feat (both iterate box in the same order). X1 is added separately below (a
    static transform of two columns base_feat already has -- no extra state needed)."""
    h = box["home_abbr"].to_numpy(); a = box["away_abbr"].to_numpy()
    hp = box["home_pts"].to_numpy(float); ap = box["away_pts"].to_numpy(float)
    dates = pd.to_datetime(box["date"]).to_numpy()
    b2b_h = base_feat["b2b_home"].to_numpy(); b2b_a = base_feat["b2b_away"].to_numpy()
    l10_h = base_feat["l10_wpct_home"].to_numpy(); l10_a = base_feat["l10_wpct_away"].to_numpy()
    has_fg3 = {"home_fg3m", "home_fg3a", "away_fg3m", "away_fg3a"} <= set(box.columns)
    h3m = box["home_fg3m"].to_numpy(float) if has_fg3 else None
    h3a = box["home_fg3a"].to_numpy(float) if has_fg3 else None
    a3m = box["away_fg3m"].to_numpy(float) if has_fg3 else None
    a3a = box["away_fg3a"].to_numpy(float) if has_fg3 else None

    wins: Dict[str, int] = {}; losses: Dict[str, int] = {}; gp_season: Dict[str, int] = {}
    pf_season: Dict[str, float] = {}; pa_season: Dict[str, float] = {}
    fg3m_season: Dict[str, float] = {}; fg3a_season: Dict[str, float] = {}
    fg3_trail: Dict[str, deque] = {}; game_dates: Dict[str, deque] = {}
    road_streak: Dict[str, int] = {}
    cur_season = None
    rows: List[dict] = []

    for i in range(len(box)):
        ht, at = str(h[i]), str(a[i])
        d = pd.Timestamp(dates[i])
        sid = _season_id(d)
        if sid != cur_season:  # new NBA season -- standings/PF-PA/3P% reset league-wide
            wins.clear(); losses.clear(); gp_season.clear()
            pf_season.clear(); pa_season.clear(); fg3m_season.clear(); fg3a_season.clear()
            cur_season = sid
        for t in (ht, at):
            fg3_trail.setdefault(t, deque(maxlen=10))
            game_dates.setdefault(t, deque(maxlen=20))
            road_streak.setdefault(t, 0)

        gph, gpa = gp_season.get(ht, 0), gp_season.get(at, 0)
        phase = min(1.0, ((gph + gpa) / 2.0) / 82.0)

        rows.append({
            "m1_tank_gradient_home": _tank(ht, phase, wins, losses),
            "m1_tank_gradient_away": _tank(at, phase, wins, losses),
            "m3_season_phase": phase, "m3_season_phase_sq": phase * phase,
            "s1_three_in_four_home": float(sum(1 for gd in game_dates[ht] if (d - gd).days <= 3) + 1),
            "s1_three_in_four_away": float(sum(1 for gd in game_dates[at] if (d - gd).days <= 3) + 1),
            "s2_road_trip_position_home": 0.0,
            "s2_road_trip_position_away": float(road_streak[at] + 1),
            "s4_b2b_home_only": float(bool(b2b_h[i]) and not bool(b2b_a[i])),
            "s4_b2b_road_only": float(bool(b2b_a[i]) and not bool(b2b_h[i])),
            "v1_fg3_luck_home": _fg3_luck(fg3_trail[ht], fg3m_season.get(ht, 0.0), fg3a_season.get(ht, 0.0)),
            "v1_fg3_luck_away": _fg3_luck(fg3_trail[at], fg3m_season.get(at, 0.0), fg3a_season.get(at, 0.0)),
            "v2_pythag_gap_home": _pythag_gap(l10_h[i], pf_season.get(ht, 0.0), pa_season.get(ht, 0.0)),
            "v2_pythag_gap_away": _pythag_gap(l10_a[i], pf_season.get(at, 0.0), pa_season.get(at, 0.0)),
        })

        # state updates AFTER row i is emitted -- this game's own outcome never leaks in
        home_win = 1 if hp[i] > ap[i] else 0
        wins[ht] = wins.get(ht, 0) + home_win; losses[ht] = losses.get(ht, 0) + (1 - home_win)
        wins[at] = wins.get(at, 0) + (1 - home_win); losses[at] = losses.get(at, 0) + home_win
        gp_season[ht] = gph + 1; gp_season[at] = gpa + 1
        pf_season[ht] = pf_season.get(ht, 0.0) + hp[i]; pa_season[ht] = pa_season.get(ht, 0.0) + ap[i]
        pf_season[at] = pf_season.get(at, 0.0) + ap[i]; pa_season[at] = pa_season.get(at, 0.0) + hp[i]
        if has_fg3:
            fg3_trail[ht].append((h3m[i], h3a[i])); fg3_trail[at].append((a3m[i], a3a[i]))
            fg3m_season[ht] = fg3m_season.get(ht, 0.0) + h3m[i]; fg3a_season[ht] = fg3a_season.get(ht, 0.0) + h3a[i]
            fg3m_season[at] = fg3m_season.get(at, 0.0) + a3m[i]; fg3a_season[at] = fg3a_season.get(at, 0.0) + a3a[i]
        game_dates[ht].append(d); game_dates[at].append(d)
        road_streak[at] += 1; road_streak[ht] = 0

    return pd.DataFrame(rows)


def build_features_deep(box: pd.DataFrame) -> pd.DataFrame:
    """Base 15 leak-free features (reused, unmodified) + the M/S/V1/V2/X1 deep columns."""
    base = _BASE_BUILD_FEATURES(box)
    extra = _deep_pass(box, base)
    extra["x1_pace_product"] = base["pace_home"].to_numpy() * base["pace_away"].to_numpy()
    return pd.concat([base, extra], axis=1)


FAMILY_COLUMNS = {
    "M": ["m1_tank_gradient_home", "m1_tank_gradient_away", "m3_season_phase", "m3_season_phase_sq"],
    "S": ["s1_three_in_four_home", "s1_three_in_four_away", "s2_road_trip_position_home",
          "s2_road_trip_position_away", "s4_b2b_home_only", "s4_b2b_road_only"],
    "V": ["v1_fg3_luck_home", "v1_fg3_luck_away", "v2_pythag_gap_home", "v2_pythag_gap_away"],
    "X": ["x1_pace_product"],
}

NOT_BUILT = {
    "M2_seeding_stakes": "clinch detection needs playoff bracket math beyond this box corpus",
    "S3_timezone": "timezone delta needs a venue-tz table not present on disk",
    "X2_style": "rim-pressure/rim-protection percentile join is Family-P-adjacent (per-player profiles)",
    "X3_size_spacing": "size/spacing percentile join is Family-P-adjacent (per-player profiles)",
}


def build_features_capped_mov(box: pd.DataFrame, cap: float = 20.0) -> pd.DataFrame:
    """V3 garbage_mov -- SAME walk-forward shape/columns as g.build_features, only the Elo
    MOV update margin capped at `cap` (blowout tails stop buying extra Elo credit). Tested
    as a feature-set SWAP, never combined additively with the other families. g.build_features
    itself is never edited -- this is a second, independent pass reusing its constants."""
    elo: Dict[str, float] = {}; pace: Dict[str, float] = {}
    offp: Dict[str, float] = {}; defp: Dict[str, float] = {}
    last_date: Dict[str, pd.Timestamp] = {}
    form: Dict[str, deque] = {}
    h = box["home_abbr"].to_numpy(); a = box["away_abbr"].to_numpy()
    hp = box["home_pts"].to_numpy(float); ap = box["away_pts"].to_numpy(float)
    dates = pd.to_datetime(box["date"]).to_numpy()
    gp = 0.5 * (g._possessions(box, "home") + g._possessions(box, "away"))
    rows: List[dict] = []
    for i in range(len(box)):
        ht, at = str(h[i]), str(a[i])
        for t in (ht, at):
            elo.setdefault(t, g._INIT); pace.setdefault(t, g._PACE0)
            offp.setdefault(t, g._PPP0); defp.setdefault(t, g._PPP0)
            form.setdefault(t, deque(maxlen=10))
        d = pd.Timestamp(dates[i])
        rest_h = min(float((d - last_date[ht]).days), 10.0) if ht in last_date else 10.0
        rest_a = min(float((d - last_date[at]).days), 10.0) if at in last_date else 10.0
        rows.append({
            "date": d, "home_abbr": ht, "away_abbr": at,
            "elo_home": elo[ht], "elo_away": elo[at], "elo_diff": elo[ht] - elo[at],
            "pace_home": pace[ht], "pace_away": pace[at],
            "offp_home": offp[ht], "defp_home": defp[ht],
            "offp_away": offp[at], "defp_away": defp[at],
            "rest_home": rest_h, "rest_away": rest_a,
            "b2b_home": float(rest_h <= 1), "b2b_away": float(rest_a <= 1),
            "l10_wpct_home": (sum(form[ht]) / len(form[ht])) if form[ht] else 0.5,
            "l10_wpct_away": (sum(form[at]) / len(form[at])) if form[at] else 0.5,
            "home_win": 1.0 if hp[i] > ap[i] else 0.0,
        })
        s = rows[-1]["home_win"]
        ph = g._p_home(elo[ht], elo[at])
        elo_diff_signed = (elo[ht] - elo[at] + g._HFA) * (1 if s else -1)
        margin = min(abs(hp[i] - ap[i]), cap)                     # <-- the ONLY delta vs g.build_features
        mov = np.log(margin + 1.0) * (2.2 / (elo_diff_signed * 0.001 + 2.2))
        delta = g._K * mov * (s - ph)
        elo[ht] += delta; elo[at] -= delta
        p = gp[i]
        if np.isfinite(p) and p > 50:
            al = 0.05
            pace[ht] += al * (p - pace[ht]); pace[at] += al * (p - pace[at])
            offp[ht] += al * (hp[i] / p - offp[ht]); defp[ht] += al * (ap[i] / p - defp[ht])
            offp[at] += al * (ap[i] / p - offp[at]); defp[at] += al * (hp[i] / p - defp[at])
        form[ht].append(s); form[at].append(1.0 - s)
        last_date[ht] = d; last_date[at] = d
    return pd.DataFrame(rows)
