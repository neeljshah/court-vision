"""scripts.platformkit.ingame.ingame_shooterprofile_gate_nba_io -- IO + conditioning-
variable plumbing for the H_A/H_B in-game gate (companion to
ingame_shooterprofile_gate_nba.py; basketball_truth_spec.json "ingame_hypotheses").
Splits data-loading/prior-construction/state-building out of the driver so
each file stays <=300 LOC.

BRIDGE (wave-34+, RE-TEST at 17x power): wave-33 built its own inline (tricode,
date) join against ONE hardcoded linescores file, capping the corpus at 74
games (2025-26 only). domains/basketball_nba/espn_nba_bridge.py now
generalizes the IDENTICAL join across every on-disk (linescores x box-season)
pairing and persists espn_nba_game_bridge.parquet -- 1299 games (1225 for
2024-25 + 74 for 2025-26). This module READS that bridge (load_bridge())
instead of duplicating the join; old inline bridge_games()/load_linescores()
are gone (see bridge module + its own test).

CONDITIONING PRIORS: season-level snapshots (shooter_quality_v1/
scorer_quality_v1 + scheme atlas), spec Section 3a caveat framing.
quality_indices_score.run() defaults to QUALIFY_SEASON="2024-25" -- fit on
2024-25 box data, so scoring vs 2024-25 games is IN-SAMPLE; for 2025-26 the
snapshot predates the season (frozen-prior caveat only). Driver reports
PER-SEASON verdicts, labeling 2024-25 as leaking, never pooled.

  H_A hot_night : team's top quality player -> p0, ACTIVE only on hot-night
                  games (team eFG% > season-to-date mean by 60th-pct TRAIN
                  delta); off-condition states get neutral p0=0.5.
  H_B scheme_fit: offense top-scorer's `by_scheme` TS% vs defense's dominant
                  coverage -> p0, ACTIVE only top/bottom TRAIN tercile; else 0.5.

INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy/pandas.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from domains.basketball_nba.espn_nba_bridge import OUT_PATH as BRIDGE_PATH
from domains.basketball_nba.quality_indices_score import run as run_quality_indices

_NEUTRAL_P0 = 0.5

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
BOXSCORES = os.path.join(_REPO, "data", "domains", "basketball_nba", "player_boxscores.parquet")
VS_SCHEME = os.path.join(_REPO, "data", "cache", "atlas_player_vs_scheme_splits.parquet")
TEAM_DEF_SCHEME = os.path.join(_REPO, "data", "cache", "atlas_team_defensive_scheme.parquet")
OUT_DIR = os.path.join(_REPO, "data", "domains", "basketball_nba")

_REG_SEC = 2880.0
QSEC = {1: 2160.0, 2: 1440.0, 3: 720.0}

# ESPN -> NBA-stats tricode normalization (only the divergent ones need mapping;
# kept here too since tests exercise it directly against the bridge's convention).
_ESPN_TO_NBA = {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS",
                "UTAH": "UTA", "WSH": "WAS"}


def _norm_abbr(a: str) -> str:
    a = str(a).strip().upper()
    return _ESPN_TO_NBA.get(a, a)


def p_live_from_margin(score_diff: float, frac_elapsed: float) -> float:
    """BASE live win-prob from realized as-of margin only -- (margin,time), NO prior."""
    slope = 0.06 + 0.10 * float(frac_elapsed)
    return float(1.0 / (1.0 + np.exp(-slope * float(score_diff))))


def load_boxscores(path: str = BOXSCORES) -> pd.DataFrame:
    return pd.read_parquet(path)


def load_bridge(path: str = BRIDGE_PATH, season: Optional[str] = None) -> pd.DataFrame:
    """Load the persisted wave-34 ESPN<->NBA game bridge (1299 exact-match
    games across 2024-25 + 2025-26), optionally restricted to one season.
    Replaces the wave-33 inline bridge_games() join -- same join key/logic,
    now built once and shared via domains.basketball_nba.espn_nba_bridge."""
    df = pd.read_parquet(path).sort_values("date").reset_index(drop=True)
    if season is not None:
        df = df[df["season"] == season].reset_index(drop=True)
    return df


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


def export_states_parquet(states: List[dict], layer: str, season: str,
                          out_dir: str = OUT_DIR) -> str:
    """Per-row harness-schema export (one row per state, layer/season tagged);
    audit/reuse artifact only, not part of the verdict itself."""
    df = pd.DataFrame(states)
    df["layer"], df["season"] = layer, season
    path = os.path.join(out_dir, f"ingame_hypothesis_{layer}_{season}_rows.parquet")
    df.to_parquet(path, index=False)
    return path


def load_prior_run(layer: str, out_dir: str = OUT_DIR) -> Optional[dict]:
    """Read the frozen wave-33 v1 verdict (74 games) before the v2 re-run overwrites it."""
    path = os.path.join(out_dir, f"ingame_hypothesis_{layer}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="ascii") as f:
        p = json.load(f)
    return {"corpus": "wave-33, 74 games (2025-26 only, hardcoded single-file bridge)",
            "verdict": p.get("verdict"), "metrics": p.get("metrics"),
            "planted_null": p.get("planted_null")}


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
