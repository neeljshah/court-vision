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
composition weights -- ponytail: no team-id ingredient exists locally to make
this team-specific, so weights are LEAGUE-average composition, the ceiling of
this seam; upgrade path is a team_bullpen_tier covariate once team ids land).

v1/v2/bullpen.py stay byte-identical; this is additive-only, side-by-side.

INVARIANTS: domains-only; ASCII; numpy/pandas; <=300 LOC; no src/kernel imports.
Tests: python -m pytest domains/mlb/pitch_engine/test_bullpen_v3.py -q
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from domains.mlb.pitch_engine.pa_chain import _PA_IX
from domains.mlb.pitch_engine.bullpen import mark_context, N_BUCKET, N_LEAD

N_PA = 8
N_TIER = 3                       # 0 low-K, 1 mid, 2 high-K (composition tiers)
_REL_MIN = 40                    # min PAs to trust a (bucket,lead,tier) cell
_MIN_PITCHER_PA = 30             # min relief PAs (fit seasons) to trust a pitcher's own K-rate


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
    def fit(cls, pa: pd.DataFrame, ptiers: PitcherQualityTier) -> "RelieverPAv3":
        pa = pa if "is_relief" in pa.columns else mark_context(pa)
        rel = pa[pa["is_relief"]].copy()
        rel["evix"] = rel["pa_evt"].map(_PA_IX)
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


__all__ = ["PitcherQualityTier", "RelieverPAv3", "N_PA", "N_TIER"]
