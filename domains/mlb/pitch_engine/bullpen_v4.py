"""domains.mlb.pitch_engine.bullpen_v4 -- PER-SIMULATED-TEAM reliever conditioning
AT SIMULATE TIME (pitch-engine v4 candidate, gate lane G1).

v3's mixed_probs (bullpen_v3.py) proved INERT: mixing reliever outcomes by a
quality-TIER weight (per-pitcher or per-team K-rate) reduces to the plain pooled
(bucket,lead) marginal by law of total probability whenever every tier cell clears
the min-sample floor -- verified byte-identical bucket_lead_matrix() output between
the pitcher-tier and team-tier candidates (validate_v3_team.py). The tiering
VARIABLE was inert; the real gap is that game_sim_v3 shares ONE league-mixed
matrix for BOTH simulated sides regardless of which specific team's bullpen is on
the mound.

v4 seam: condition the reliever PA-event distribution DIRECTLY on the SPECIFIC
simulated team's own (inn_bucket, lead_state) relief history -- no tier axis at
all -- falling back per-cell to the pooled (all-teams) marginal when that team's
own cell does not clear a min-sample floor. simulate_game_v3
(game_sim_v3.simulate_game_v3) ALREADY accepts two separate [N_BUCKET,N_LEAD,8]
matrices (rp_vs_away, rp_vs_home) -- reused verbatim, no new simulator; the only
change is what those two matrices ARE (the specific home/away team's own bullpen,
not one shared pooled table). See validate_v4.py for the gate.

INVARIANTS: domains-only; ASCII; numpy/pandas; <=300 LOC; no src/kernel imports.
Tests: python -m pytest domains/mlb/pitch_engine/test_bullpen_v4.py -q
"""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd

from domains.mlb.pitch_engine.pa_chain import _PA_IX
from domains.mlb.pitch_engine.bullpen import mark_context, N_BUCKET, N_LEAD
from domains.mlb.pitch_engine.bullpen_v3 import pitcher_team

N_PA = 8
# ponytail: same floor v3 used for (bucket,lead,tier) cells (_REL_MIN) -- a team
# has fewer relief PAs than the whole league so a per-team cell is thinner; keep
# the same bar rather than inventing a new one, tune later if fallback_frac is
# implausibly high or low.
_TEAM_MIN = 40


def _norm(v: np.ndarray) -> np.ndarray:
    s = v.sum()
    return v / s if s > 0 else np.ones_like(v) / len(v)


class TeamReliever:
    """Per-team [N_BUCKET,N_LEAD,N_PA] reliever PA-event matrices, own relief
    history only, backing off per-cell to the pooled ALL-TEAMS (bucket,lead)
    marginal when a team's own cell is thin (< _TEAM_MIN PAs)."""

    def __init__(self, cell: Dict[tuple, np.ndarray], by_bl: Dict[tuple, np.ndarray],
                 by_b: Dict[int, np.ndarray], glob: np.ndarray):
        self._cell = cell        # {(team,b,L): [N_PA]}
        self._by_bl = by_bl      # {(b,L): [N_PA]} pooled ALL-teams fallback
        self._by_b = by_b        # {b: [N_PA]}
        self._glob = glob        # [N_PA]

    @classmethod
    def fit(cls, pa: pd.DataFrame) -> "TeamReliever":
        pa = pa if "is_relief" in pa.columns else mark_context(pa)
        rel = pa[pa["is_relief"]].copy()
        rel["evix"] = rel["pa_evt"].map(_PA_IX)
        rel["team"] = pitcher_team(rel)

        def _cnt(g):
            return _norm(np.bincount(g["evix"], minlength=N_PA).astype(float))

        glob = _cnt(rel)
        by_b = {int(b): _cnt(g) for b, g in rel.groupby("inn_bucket")}
        by_bl = {(int(b), int(L)): _cnt(g)
                 for (b, L), g in rel.groupby(["inn_bucket", "lead_state"])}
        cell = {(str(t), int(b), int(L)): _cnt(g)
                for (t, b, L), g in rel.groupby(["team", "inn_bucket", "lead_state"])
                if len(g) >= _TEAM_MIN}
        return cls(cell, by_bl, by_b, glob)

    def team_matrix(self, team: str) -> Tuple[np.ndarray, int, int]:
        """(matrix[N_BUCKET,N_LEAD,N_PA], n_direct_cells, n_fallback_cells) for
        one team's own bullpen. Direct cell used when the team's own
        (bucket,lead) sample clears _TEAM_MIN; else falls back through the
        pooled (bucket,lead) -> (bucket) -> global marginal (all teams)."""
        m = np.zeros((N_BUCKET, N_LEAD, N_PA))
        n_direct = 0
        n_fallback = 0
        for b in range(N_BUCKET):
            for L in range(N_LEAD):
                v = self._cell.get((str(team), b, L))
                if v is not None:
                    m[b, L] = v
                    n_direct += 1
                else:
                    m[b, L] = self._by_bl.get((b, L), self._by_b.get(b, self._glob))
                    n_fallback += 1
        return m, n_direct, n_fallback

    def summary(self) -> dict:
        n_teams = len({t for t, _, _ in self._cell})
        return {"n_direct_cells_total": len(self._cell),
                "n_teams_with_any_direct_cell": n_teams,
                "min_cell": _TEAM_MIN, "cells_per_team": N_BUCKET * N_LEAD}


__all__ = ["TeamReliever", "N_PA"]
