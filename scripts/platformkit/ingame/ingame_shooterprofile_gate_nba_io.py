"""scripts.platformkit.ingame.ingame_shooterprofile_gate_nba_io -- IO + conditioning-
variable plumbing for the H_A/H_B in-game gate (companion to
ingame_shooterprofile_gate_nba.py). Pre-registered in
docs/research/intel-layer/basketball_truth_spec.json ("ingame_hypotheses").
Splits data-loading + prior construction + state-building out of the gate driver
so each file stays <=300 LOC.

BRIDGE (new, needed here): linescores.parquet uses ESPN event_id + ESPN team
abbreviations (GS/NO/NY/SA/UTAH/WSH); player_boxscores.parquet uses NBA-stats
game_id + NBA-stats tricodes (GSW/NOP/NYK/SAS/UTA/WAS). No on-disk bridge table
exists for these two id spaces, so this module builds one by (home/away tricode,
date) after normalizing the divergent abbreviations. Restricted to the 2025-26
season window where both corpora overlap (2025-10-21 .. 2026-01-19).

CONDITIONING PRIORS (both season-level snapshots -- same honest caveat the spec
uses for the pregame indices in Section 3a: "stable style descriptors with a
season-level caveat", NOT per-game leak-free, since shooter_quality_v1/
scorer_quality_v1 and the scheme atlas are single as-of snapshots covering the
whole disk window). Carried into every verdict the gate emits.

  H_A hot_night : team's top (shooter_quality_v1, scorer_quality_v1) player among
                  that game's box lineup -> p0, ACTIVE only on hot-night games
                  (team eFG% that game exceeds its season-to-date mean by more
                  than the 60th-pct team-game eFG delta, threshold from TRAIN
                  fold only); off-condition states get neutral p0=0.5.
  H_B scheme_fit: offense top-scorer's `by_scheme` TS% vs the defending team's
                  dominant coverage scheme -> p0, ACTIVE only on top/bottom
                  TRAIN-fold tercile of scheme-fit; else neutral p0=0.5.

INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy/pandas + stdlib.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from domains.basketball_nba.quality_indices_score import run as run_quality_indices

_NEUTRAL_P0 = 0.5

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
LINESCORES = os.path.join(_REPO, "data", "domains", "basketball_nba", "linescores.parquet")
BOXSCORES = os.path.join(_REPO, "data", "domains", "basketball_nba", "player_boxscores.parquet")
VS_SCHEME = os.path.join(_REPO, "data", "cache", "atlas_player_vs_scheme_splits.parquet")
TEAM_DEF_SCHEME = os.path.join(_REPO, "data", "cache", "atlas_team_defensive_scheme.parquet")
OUT_DIR = os.path.join(_REPO, "data", "domains", "basketball_nba")

_REG_SEC = 2880.0
QSEC = {1: 2160.0, 2: 1440.0, 3: 720.0}
_QCOLS = ["home_q1", "home_q2", "home_q3", "home_q4",
          "away_q1", "away_q2", "away_q3", "away_q4"]

# ESPN -> NBA-stats tricode normalization (only the divergent ones need mapping).
_ESPN_TO_NBA = {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS",
                "UTAH": "UTA", "WSH": "WAS"}


def _norm_abbr(a: str) -> str:
    a = str(a).strip().upper()
    return _ESPN_TO_NBA.get(a, a)


def p_live_from_margin(score_diff: float, frac_elapsed: float) -> float:
    """BASE live win-prob from realized as-of margin only -- (margin,time), NO prior."""
    slope = 0.06 + 0.10 * float(frac_elapsed)
    return float(1.0 / (1.0 + np.exp(-slope * float(score_diff))))


def load_linescores(path: str = LINESCORES) -> pd.DataFrame:
    df = pd.read_parquet(path).dropna(subset=_QCOLS)
    return df.sort_values("date").reset_index(drop=True)


def load_boxscores(path: str = BOXSCORES) -> pd.DataFrame:
    return pd.read_parquet(path)


def bridge_games(lines: pd.DataFrame, box: pd.DataFrame) -> pd.DataFrame:
    """Join linescores (ESPN event_id) to player_boxscores (NBA game_id) on
    (home_tricode, away_tricode, date), normalizing divergent abbreviations.
    No on-disk id bridge exists for these two corpora; this is a deterministic,
    outcome-free join key, not a fitted model. One row per matched game."""
    lines = lines.copy()
    lines["home_nba"] = lines["home_abbr"].map(_norm_abbr)
    lines["away_nba"] = lines["away_abbr"].map(_norm_abbr)
    lines["_date"] = pd.to_datetime(lines["date"]).dt.normalize()

    home_box = (box[box["is_home"] == True]  # noqa: E712
                [["game_id", "date", "team"]].drop_duplicates())
    away_box = (box[box["is_home"] == False]  # noqa: E712
                [["game_id", "date", "team"]].drop_duplicates())
    home_box = home_box.rename(columns={"team": "home_nba"})
    away_box = away_box.rename(columns={"team": "away_nba"})
    home_box["_date"] = pd.to_datetime(home_box["date"]).dt.normalize()
    away_box["_date"] = pd.to_datetime(away_box["date"]).dt.normalize()
    box_games = home_box.merge(away_box[["game_id", "away_nba"]], on="game_id")

    merged = lines.merge(
        box_games[["game_id", "home_nba", "away_nba", "_date"]],
        on=["home_nba", "away_nba", "_date"], how="inner")
    return merged.drop_duplicates(subset=["event_id"]).reset_index(drop=True)


# ------------------------------------------------------------------- H_A prior
def team_top_quality_by_game(box: pd.DataFrame) -> Dict[Tuple, float]:
    """{(game_id, team): max(shooter_quality_v1, scorer_quality_v1)} over that
    game's box lineup, using the FROZEN spec quality indices (season-level
    snapshot, reused verbatim -- not re-derived here)."""
    res = run_quality_indices()
    shooter = res.shooter.set_index("player_id")["shooter_quality_v1"]
    scorer = res.scorer.set_index("player_id")["scorer_quality_v1"]
    q = pd.concat([shooter, scorer], axis=1).max(axis=1, skipna=True)
    out: Dict[Tuple, float] = {}
    for (gid, team), grp in box.groupby(["game_id", "team"]):
        vals = q.reindex(grp["player_id"]).dropna()
        if len(vals):
            out[(gid, team)] = float(vals.max())
    return out


def team_game_efg(box: pd.DataFrame) -> pd.DataFrame:
    """Per (game_id, team) realized eFG% from the box lineup for that game."""
    g = box.groupby(["game_id", "team", "date"], as_index=False).agg(
        fgm=("fgm", "sum"), fga=("fga", "sum"), fg3m=("fg3m", "sum"))
    g["efg_pct"] = (g["fgm"] + 0.5 * g["fg3m"]) / g["fga"].replace(0, pd.NA)
    return g


# ------------------------------------------------------------------- H_B prior
def _tag_to_key(tag: str) -> str:
    return str(tag).strip().lower().replace(" ", "_").replace("-", "_")


def team_dominant_scheme() -> Dict[str, str]:
    d = pd.read_parquet(TEAM_DEF_SCHEME)
    out = {}
    for _, r in d.iterrows():
        struct = r["coverage_scheme"]
        struct = json.loads(struct) if isinstance(struct, str) else (struct or {})
        out[str(r["team_tricode"])] = _tag_to_key(struct.get("dominant_tag", ""))
    return out


def player_scheme_ts(path: str = VS_SCHEME) -> Dict[int, Dict[str, float]]:
    """{player_id: {scheme_key: ts_pct}} parsed from by_scheme JSON structs."""
    vs = pd.read_parquet(path)
    out: Dict[int, Dict[str, float]] = {}
    for _, r in vs.iterrows():
        raw = r["by_scheme"]
        d = json.loads(raw) if isinstance(raw, str) else (raw or {})
        out[int(r["player_id"])] = {k: v.get("ts_pct") for k, v in d.items()
                                    if isinstance(v, dict)}
    return out


def offense_top_scorer_scheme_fit(box: pd.DataFrame, opp_scheme_key: str,
                                  scheme_ts: Dict[int, Dict[str, float]],
                                  quality_top: pd.Series) -> Optional[float]:
    """TS% of the offense's top-scorer (by scorer_quality_v1) against the
    opponent's dominant scheme, or None if unavailable (dropped, never imputed)."""
    if not len(box):
        return None
    q = quality_top.reindex(box["player_id"].tolist()).dropna()
    return scheme_ts.get(int(q.idxmax()), {}).get(opp_scheme_key) if len(q) else None


def write(verdict_dict: dict, name: str, out_dir: str = OUT_DIR) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name)
    with open(path, "w", encoding="ascii") as f:
        json.dump(verdict_dict, f, indent=2, sort_keys=True)
    return path


# ------------------------------------------------------------- state building
def _iter_sides(bridge):
    """Yield (game_id, event_id, team_side, opp_side, sign, home_win) per game
    side, shared by both layers' state builders (sign flips margin for the away
    side so score_diff/outcome are always from team_side's perspective)."""
    for r in bridge.itertuples(index=False):
        hc = np.cumsum([r.home_q1, r.home_q2, r.home_q3, r.home_q4])
        ac = np.cumsum([r.away_q1, r.away_q2, r.away_q3, r.away_q4])
        y = int(hc[-1] > ac[-1])
        for team_side, opp_side, sign in ((r.home_nba, r.away_nba, 1.0),
                                          (r.away_nba, r.home_nba, -1.0)):
            yield r.game_id, int(r.event_id), team_side, opp_side, sign, hc, ac, y


def _quarter_rows(eid, sign, hc, ac, y, extra: dict) -> List[dict]:
    """3 per-quarter-cut state rows (end-Q1/Q2/Q3) for one game side."""
    rows = []
    for q in (1, 2, 3):
        diff = float(hc[q - 1] - ac[q - 1]) * sign
        frac = 1.0 - QSEC[q] / _REG_SEC
        rows.append({
            "game_id": eid, "period": q, "seconds_remaining": QSEC[q],
            "score_diff": diff, "p_live": p_live_from_margin(diff, frac),
            "outcome": y if sign > 0 else 1 - y, **extra,
        })
    return rows


def build_states_hot_night(bridge, box, quality: Dict[Tuple, float], efg_df) -> List[dict]:
    """One state per (game, side, quarter-cut). p0 = team-on-offense's top
    quality when hot-night is TRUE for that team-game, else neutral 0.5.
    `cond_delta`/`cond_prior` carried per-state for the TRAIN-only gate."""
    efg_by_team_game = {(r.game_id, r.team): r.efg_pct for r in efg_df.itertuples(index=False)}
    running: Dict[str, List[float]] = {}
    std_mean: Dict[Tuple, float] = {}
    for r in efg_df.sort_values("date").itertuples(index=False):
        hist = running.setdefault(r.team, [])
        std_mean[(r.game_id, r.team)] = (sum(hist) / len(hist)) if hist else float("nan")
        hist.append(r.efg_pct)

    out: List[dict] = []
    for gid, eid, team_side, _, sign, hc, ac, y in _iter_sides(bridge):
        eg = efg_by_team_game.get((gid, team_side))
        base_mean = std_mean.get((gid, team_side))
        delta = (eg - base_mean) if (eg is not None and base_mean is not None
                                    and not np.isnan(base_mean)) else None
        extra = {"cond_delta": delta, "cond_prior": quality.get((gid, team_side)),
                 "team": team_side}
        out += _quarter_rows(eid, sign, hc, ac, y, extra)
    return out


def build_states_scheme_fit(bridge, box) -> List[dict]:
    """One state per (game, side, quarter-cut). cond_val = offense top-scorer's
    by_scheme TS% vs the defending team's dominant scheme (TRAIN-fold tercile
    gate applied downstream)."""
    def_scheme = team_dominant_scheme()
    scheme_ts = player_scheme_ts()
    scorer_q = run_quality_indices().scorer.set_index("player_id")["scorer_quality_v1"]

    out: List[dict] = []
    for gid, eid, team_side, opp_side, sign, hc, ac, y in _iter_sides(bridge):
        opp_scheme = def_scheme.get(opp_side)
        box_g = box[(box["game_id"] == gid) & (box["team"] == team_side)]
        fit_val = offense_top_scorer_scheme_fit(box_g, opp_scheme, scheme_ts, scorer_q) \
            if opp_scheme else None
        extra = {"cond_val": fit_val, "team": team_side}
        out += _quarter_rows(eid, sign, hc, ac, y, extra)
    return out


# ------------------------------------------------------------- TRAIN-only gating
def apply_hot_night_gate(states: List[dict], train_idx: List[int]):
    """Set p0 = cond_prior on hot-night states (delta > 60th-pct TRAIN threshold),
    neutral 0.5 elsewhere. Threshold computed on TRAIN states only (no test leak)."""
    deltas = [states[i]["cond_delta"] for i in train_idx
             if states[i]["cond_delta"] is not None]
    thresh = float(np.percentile(deltas, 60)) if deltas else float("inf")
    out = []
    for s in states:
        hot = (s["cond_delta"] is not None and s["cond_delta"] > thresh
              and s["cond_prior"] is not None)
        p0 = float(s["cond_prior"]) if hot else _NEUTRAL_P0
        out.append({**s, "p0": p0, "gated_on": bool(hot)})
    return out, thresh


def apply_scheme_tercile_gate(states: List[dict], train_idx: List[int]):
    """Set p0 = cond_val on top/bottom TRAIN-fold tercile states, neutral elsewhere."""
    vals = [states[i]["cond_val"] for i in train_idx if states[i]["cond_val"] is not None]
    if not vals:
        lo, hi = float("-inf"), float("inf")
    else:
        lo, hi = float(np.percentile(vals, 100.0 / 3)), float(np.percentile(vals, 200.0 / 3))
    out = []
    for s in states:
        v = s["cond_val"]
        gated = v is not None and (v <= lo or v >= hi)
        p0 = float(v) if gated else _NEUTRAL_P0
        out.append({**s, "p0": p0, "gated_on": bool(gated)})
    return out, (lo, hi)


# ------------------------------------------------------------- planted null
def shuffle_hot_night(states: List[dict], seed: int = 0) -> List[dict]:
    """PLANTED NULL: permute cond_prior assignment across teams (same game/period
    structure, cond_prior values shuffled) so any surviving lift is a flexibility
    artifact, not a real hot-night player-profile signal."""
    rng = np.random.RandomState(seed)
    priors = [s["cond_prior"] for s in states]
    perm = rng.permutation(len(priors))
    shuffled = [priors[i] for i in perm]
    return [{**s, "cond_prior": shuffled[i]} for i, s in enumerate(states)]


def shuffle_scheme_fit(states: List[dict], seed: int = 0) -> List[dict]:
    """PLANTED NULL: permute the opponent-scheme (cond_val) assignment."""
    rng = np.random.RandomState(seed)
    vals = [s["cond_val"] for s in states]
    perm = rng.permutation(len(vals))
    shuffled = [vals[i] for i in perm]
    return [{**s, "cond_val": shuffled[i]} for i, s in enumerate(states)]
