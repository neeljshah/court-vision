"""domains.mlb.pitch_engine.bullpen_v3 -- PITCHER-QUALITY-TIER composition seam
(pitch-engine v3 candidate, gate lane G1).

QUEUED FIX from the v2 REJECT (data/cache/intel_claims/prereg_hypothesis_ledger.jsonl,
hypothesis="mlb_pitch_engine_v2_bullpen_seam_inn7_m2_regression"): v2 pooled ALL
relievers together within (inn_bucket, lead_state) and REGRESSED the named
inn7|m2 bucket (uniformity_dev 0.1061 vs v1 0.0737). The session-report lesson
(docs/research/session_report_2026-07-10.md, "scoring-intensity" NULL) says the
apparent late-game effect is pitcher-QUALITY COMPOSITION (bullpen leverage
allocation), not starter-vs-reliever talent-as-margin-lever (that hypothesis is
the one v2 already tested and failed). Mechanism #29 (CONFIRMED,
domains/mlb/knowledge/mechanisms.md, "High-leverage strand prevention": pitcher
K-rate vs RISP strand-rate r=0.1863 p=0.0068 n=210, inn>=7 |margin|<=2) is the
CONFIRMED local signal the composition variable is built on.

This module adds the ONE axis v2 lacks: reliever_quality_tier (K-rate tertile,
fit STRICTLY on FIT_SEASONS relief PAs, own history only, min-sample gated) --
crossed with leverage (lead_state) and inn_bucket. The COMPOSITION variable
itself is `weight(tier | bucket, lead)`: the empirical fraction of PAs each
quality tier actually threw in that leverage state (elite/high-K arms protect
leads; low-K arms mop up) -- reconstructing the pooled distribution as a
tier-mixture with per-cell backoff (not one flat pooled histogram) is the
candidate mechanism for sharpening inn7|m2 without re-litigating talent-as-
margin (no per-pitcher identity is used at simulation time, only the fit-season
composition weights).

CORRECTION (was wrong): an earlier revision of this docstring claimed "no
team-id ingredient exists locally" to make composition team-specific. That was
false -- pitcher_team() below derives the pitching team per PA from Savant's
own home_team/away_team x inning_topbot (home pitches in the Top half, away
pitches in the Bot half; no separate team-id table needed). TeamBullpenTier
fits a TEAM-level K-rate tertile (own history, FIT_SEASONS only) as an
alternate composition axis; RelieverPAv3.fit(..., team_tiers=...) swaps the
per-pitcher tier for the per-team tier when passed. Default (team_tiers=None)
is byte-identical to the original per-pitcher behavior. Gated candidate:
see validate_v3_team.py.

v1/v2/bullpen.py stay byte-identical; this is additive-only, side-by-side.

INVARIANTS: domains-only; ASCII; numpy/pandas; <=300 LOC; no src/kernel imports.
Tests: python -m pytest domains/mlb/pitch_engine/test_bullpen_v3.py -q
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

from domains.mlb.pitch_engine.pa_chain import _PA_IX
from domains.mlb.pitch_engine.bullpen import mark_context, N_BUCKET, N_LEAD

N_PA = 8
N_TIER = 3                       # 0 low-K, 1 mid, 2 high-K (composition tiers)
_REL_MIN = 40                    # min PAs to trust a (bucket,lead,tier) cell
_MIN_PITCHER_PA = 30             # min relief PAs (fit seasons) to trust a pitcher's own K-rate
_MIN_TEAM_PA = 150               # min relief PAs (fit seasons) to trust a team's own K-rate


def pitcher_team(pa: pd.DataFrame) -> np.ndarray:
    """PITCHING team code per PA row, derived from Savant's own home_team/
    away_team x inning_topbot (home team pitches in the Top half, away team
    pitches in the Bot half) -- no separate team-id table needed. Caller must
    load home_team/away_team columns (not in corpus._PITCH_COLS by default)."""
    top = pa["inning_topbot"].astype(str).to_numpy() == "Top"
    return np.where(top, pa["home_team"].astype(str).to_numpy(),
                    pa["away_team"].astype(str).to_numpy())


def _norm(v: np.ndarray) -> np.ndarray:
    s = v.sum()
    return v / s if s > 0 else np.ones_like(v) / len(v)


def _tier3(v: float, lo: float, hi: float) -> int:
    return 0 if v < lo else (2 if v >= hi else 1)


class PitcherQualityTier:
    """Prior-season (FIT_SEASONS only) reliever K-rate tertile, own relief PAs.
    Unknown / thin-sample pitcher backs off to tier 1 (league-mid)."""

    def __init__(self, tiers: Dict[int, int], edges: tuple):
        self._t = tiers
        self._edges = edges

    @classmethod
    def fit(cls, pa: pd.DataFrame) -> "PitcherQualityTier":
        pa = pa if "is_relief" in pa.columns else mark_context(pa)
        rel = pa[pa["is_relief"]].copy()
        rel["is_k"] = (rel["pa_evt"] == "K").astype(float)
        agg = rel.groupby("pitcher").agg(k=("is_k", "mean"), n=("is_k", "size"))
        q = agg[agg["n"] >= _MIN_PITCHER_PA]["k"]
        lo, hi = (float(q.quantile(1 / 3)), float(q.quantile(2 / 3))) if len(q) >= 3 else (0.18, 0.24)
        tiers = {int(p): _tier3(k, lo, hi)
                 for p, k, n in agg.itertuples() if n >= _MIN_PITCHER_PA}
        return cls(tiers, (lo, hi))

    def tier(self, pitcher: int) -> int:
        return self._t.get(int(pitcher), 1)

    def summary(self) -> dict:
        return {"n_pitchers_tiered": len(self._t), "k_rate_edges": [round(x, 4) for x in self._edges]}


class TeamBullpenTier:
    """Prior-season (FIT_SEASONS only) TEAM-level reliever K-rate tertile, own
    relief PAs pooled by pitcher_team(). Alternate composition axis to
    PitcherQualityTier -- tests whether team-aggregate bullpen quality (rather
    than individual reliever K-rate) is the sharper conditioning variable.
    Unknown / thin-sample team backs off to tier 1 (league-mid)."""

    def __init__(self, tiers: Dict[str, int], edges: tuple):
        self._t = tiers
        self._edges = edges

    @classmethod
    def fit(cls, pa: pd.DataFrame) -> "TeamBullpenTier":
        pa = pa if "is_relief" in pa.columns else mark_context(pa)
        rel = pa[pa["is_relief"]].copy()
        rel["team"] = pitcher_team(rel)
        rel["is_k"] = (rel["pa_evt"] == "K").astype(float)
        agg = rel.groupby("team").agg(k=("is_k", "mean"), n=("is_k", "size"))
        q = agg[agg["n"] >= _MIN_TEAM_PA]["k"]
        lo, hi = (float(q.quantile(1 / 3)), float(q.quantile(2 / 3))) if len(q) >= 3 else (0.18, 0.24)
        tiers = {str(t): _tier3(k, lo, hi)
                 for t, k, n in agg.itertuples() if n >= _MIN_TEAM_PA}
        return cls(tiers, (lo, hi))

    def tier(self, team: str) -> int:
        return self._t.get(str(team), 1)

    def summary(self) -> dict:
        return {"n_teams_tiered": len(self._t), "k_rate_edges": [round(x, 4) for x in self._edges]}


class RelieverPAv3:
    """Reliever PA-event dist stratified by (inn_bucket, lead_state,
    reliever_quality_tier) -- the composition axis. Backoff per cell:
    (b,L,tier) -> (b,L) -> (b) -> global. `mixed_probs` reconstructs the
    (b,L)-level distribution as the empirical tier-MIXTURE (cell-density-
    adaptive backoff per tier) rather than one flat pooled histogram --
    this is the seam under test."""

    def __init__(self, cell, by_bl, by_b, glob, weight):
        self._cell = cell            # {(b,L,tier): [8]}
        self._by_bl = by_bl          # {(b,L): [8]}
        self._by_b = by_b            # {b: [8]}
        self._glob = glob            # [8]
        self._w = weight             # {(b,L): [N_TIER]} empirical tier composition

    @classmethod
    def fit(cls, pa: pd.DataFrame, ptiers: PitcherQualityTier,
            team_tiers: Optional["TeamBullpenTier"] = None) -> "RelieverPAv3":
        """team_tiers=None (default): composition axis is per-PITCHER K-rate
        tier (byte-identical to the original v3 behavior). team_tiers given:
        composition axis is per-TEAM K-rate tier instead (requires
        home_team/away_team columns on `pa` for pitcher_team())."""
        pa = pa if "is_relief" in pa.columns else mark_context(pa)
        rel = pa[pa["is_relief"]].copy()
        rel["evix"] = rel["pa_evt"].map(_PA_IX)
        if team_tiers is not None:
            rel["ptier"] = [team_tiers.tier(t) for t in pitcher_team(rel)]
        else:
            rel["ptier"] = [ptiers.tier(int(p)) for p in rel["pitcher"].to_numpy()]

        def _cnt(g):
            return _norm(np.bincount(g["evix"], minlength=N_PA).astype(float))

        glob = _cnt(rel)
        by_b = {int(b): _cnt(g) for b, g in rel.groupby("inn_bucket")}
        by_bl = {(int(b), int(L)): _cnt(g)
                 for (b, L), g in rel.groupby(["inn_bucket", "lead_state"])}
        cell = {(int(b), int(L), int(t)): _cnt(g)
                for (b, L, t), g in rel.groupby(["inn_bucket", "lead_state", "ptier"])
                if len(g) >= _REL_MIN}
        weight: Dict[tuple, np.ndarray] = {}
        for (b, L), g in rel.groupby(["inn_bucket", "lead_state"]):
            cnt = np.bincount(g["ptier"].to_numpy(), minlength=N_TIER).astype(float)
            weight[(int(b), int(L))] = _norm(cnt)
        return cls(cell, by_bl, by_b, glob, weight)

    def probs(self, bucket: int, lead: int, tier: int) -> np.ndarray:
        v = self._cell.get((int(bucket), int(lead), int(tier)))
        if v is not None:
            return v
        v = self._by_bl.get((int(bucket), int(lead)))
        if v is not None:
            return v
        return self._by_b.get(int(bucket), self._glob)

    def mixed_probs(self, bucket: int, lead: int) -> np.ndarray:
        """ponytail-documented ceiling (found gating the team-tier candidate,
        validate_v3_team.py): this is sum_t w[t]*P(x|bucket,lead,t) with w[t]
        the EXACT empirical tier fraction -- law of total probability -- so it
        is IDENTICAL to the plain pooled (bucket,lead) marginal (_by_bl) any
        time every (bucket,lead,tier) cell clears _REL_MIN (no backoff
        distortion). Verified empirically: team-tier and pitcher-tier fits
        produce byte-identical bucket_lead_matrix() output for inn7|leading
        (all 36 cells dense in the real corpus) even though their per-cell
        distributions and tier weights genuinely differ. The tiering VARIABLE
        is therefore inert for any well-populated cell -- upgrade path is
        conditioning simulate-time on the SPECIFIC simulated team's own tier
        (not one league-mixed matrix shared by both sides), not a different
        tier definition."""
        w = self._w.get((int(bucket), int(lead)))
        if w is None:
            return self._by_b.get(int(bucket), self._glob)
        out = np.zeros(N_PA)
        for t in range(N_TIER):
            out += w[t] * self.probs(bucket, lead, t)
        return out

    def bucket_lead_matrix(self) -> np.ndarray:
        """[N_BUCKET, N_LEAD, N_PA] mixed reliever dist, precomputed ONCE
        (no per-game / per-slot dependence -- v3 isolates the composition axis;
        ponytail: batter-tier and freshness interactions are a v4 seam, not
        re-added here so this stays a clean single-variable ablation vs v2)."""
        m = np.zeros((N_BUCKET, N_LEAD, N_PA))
        for b in range(N_BUCKET):
            for L in range(N_LEAD):
                m[b, L] = self.mixed_probs(b, L)
        return m

    def summary(self) -> dict:
        return {"n_cells": len(self._cell), "min_cell": _REL_MIN,
                "buckets": "<=6,7,8,>=9", "tiers": "0 low-K,1 mid,2 high-K",
                "composition_weight_inn7_leading": [
                    round(float(x), 4) for x in self._w.get((1, 2), np.zeros(N_TIER))]}


__all__ = ["PitcherQualityTier", "TeamBullpenTier", "RelieverPAv3", "N_PA", "N_TIER",
           "pitcher_team"]
