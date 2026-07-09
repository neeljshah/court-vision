"""domains.mlb.pitch_engine.bullpen -- the RELIEVER / BULLPEN SEAM (pitch engine v2).

v1's game MC (game_sim.simulate_game) models the game's STARTER pitching all nine
innings -- its named worst bucket is inn7|home-lead OVER-PROJECTION (the away
offense keeps scoring late off a "tiring" starter that, in reality, was pulled for
fresh bullpen arms). This module supplies the three pieces the reliever-aware
simulator (game_sim_v2) needs, all fit EMPIRICALLY on the prior seasons, leak-free:

  * RemovalModel  -- discrete-inning hazard P(starter removed entering inning k |
                     k, pitcher lead-state) + a cumulative removed_by(k, lead) used
                     to initialise a mid-game snapshot (most starters are already
                     gone by inning 7). Score-state conditioned: a lead is protected
                     by the pen, which is exactly the inn7|home-lead mechanism.
  * RelieverPA    -- pooled reliever PA-event distribution keyed
                     (inning_bucket, batter_tier, freshness). inning_bucket is the
                     leverage / arm-class proxy: the arms that actually throw the
                     9th ARE the leverage-appropriate (closer) class, so the
                     empirical inning-bucket dist encodes reliever SELECTION without
                     an explicit arm-class model. Reuses the v1 8-way PA-event space.
  * reliever_cadence / bullpen_freshness -- WIRES the built-never-wired bullpen
                     relief-appearance chains (ingest_bullpen_relief_chains.py's
                     rest-day / appearances-in-trailing-window derivation), here
                     re-derived from Savant itself (leak-free, same-corpus) rather
                     than the era-disjoint player_gamelogs source. availability =
                     the freshness fraction of the arms a side actually used.

Starter identity (no explicit SP flag in Savant): the pitcher of a side's FIRST PA
(min at_bat_number for that inning_topbot) is that game's starter for the side;
every later distinct pitcher for the side is a relief appearance. Disclosed
heuristic (openers land on the "starter" side) -- not a fabricated appearance.

INVARIANTS: domains-only; ASCII; numpy/pandas; <=300 LOC; no src/kernel imports.
Tests: python -m pytest domains/mlb/pitch_engine/test_bullpen.py -q
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from domains.mlb.pitch_engine.corpus import PA_EVENTS
from domains.mlb.pitch_engine.pa_chain import _PA_IX

N_PA = len(PA_EVENTS)            # 8
N_INN = 10                       # index 0..9, inning capped at 9
N_LEAD = 3                       # 0 trailing, 1 tied, 2 leading (pitcher perspective)
N_BUCKET = 4                     # <=6, 7, 8, >=9
MIN_REMOVAL_INN = 5              # starters ~never pulled before the 5th
_HAZ_MIN = 25                    # min at-risk innings to trust a (inn,lead) hazard cell
_REL_MIN = 40                    # min PAs to trust a reliever dist cell


def inn_bucket(inn: int) -> int:
    return 0 if inn <= 6 else (1 if inn == 7 else (2 if inn == 8 else 3))


def inn_bucket_arr(inn: np.ndarray) -> np.ndarray:
    inn = np.asarray(inn)
    return np.where(inn <= 6, 0, np.where(inn == 7, 1, np.where(inn == 8, 2, 3)))


def _norm(v: np.ndarray) -> np.ndarray:
    s = v.sum()
    return v / s if s > 0 else np.ones_like(v) / len(v)


def _starter_map(pa: pd.DataFrame) -> Dict[tuple, int]:
    """(game_pk, side) -> starter pitcher id (pitcher of the side's first PA)."""
    idx = pa.groupby(["game_pk", "inning_topbot"])["at_bat_number"].idxmin()
    sub = pa.loc[idx]
    return {(int(g), str(s)): int(p)
            for g, s, p in zip(sub["game_pk"], sub["inning_topbot"], sub["pitcher"])}


def mark_context(pa: pd.DataFrame) -> pd.DataFrame:
    """Attach is_relief, lead_state (pitcher perspective) and inn_bucket to a PA frame.
    Uses the pre-PA home_score/away_score (load with cols incl. those)."""
    pa = pa.copy()
    smap = _starter_map(pa)
    keys = list(zip(pa["game_pk"].astype("int64"), pa["inning_topbot"].astype(str)))
    starter = np.array([smap.get(k, -1) for k in keys], dtype="int64")
    pa["is_relief"] = pa["pitcher"].astype("int64").to_numpy() != starter
    bot = pa["inning_topbot"].astype(str).to_numpy() == "Bot"     # home batting -> away pitches
    home_pre = pa["home_score"].to_numpy().astype(float)
    away_pre = pa["away_score"].to_numpy().astype(float)
    pit_lead = np.where(bot, away_pre - home_pre, home_pre - away_pre)
    pa["lead_state"] = np.where(pit_lead > 0, 2, np.where(pit_lead < 0, 0, 1)).astype(int)
    pa["inn_bucket"] = inn_bucket_arr(pa["inning"].to_numpy())
    return pa


class RemovalModel:
    """Discrete-inning starter-removal hazard, score-state conditioned."""

    def __init__(self, hazard: np.ndarray):
        self._h = hazard                              # [N_INN, N_LEAD] filled

    @classmethod
    def fit(cls, pa: pd.DataFrame) -> "RemovalModel":
        pa = pa if "is_relief" in pa.columns else mark_context(pa)
        first = (pa.sort_values("at_bat_number")
                   .groupby(["game_pk", "inning_topbot", "inning"], as_index=False)
                   .first())
        first["starter_began"] = ~first["is_relief"]
        rel_any = (first.groupby(["game_pk", "inning_topbot"])["is_relief"].any()
                        .rename("rel_any").reset_index())
        began = first[first["starter_began"]].copy()
        last_started = (began.groupby(["game_pk", "inning_topbot"])["inning"].max()
                             .rename("last_started").reset_index())
        d = began.merge(rel_any, on=["game_pk", "inning_topbot"]) \
                 .merge(last_started, on=["game_pk", "inning_topbot"])
        d["y"] = ((d["inning"] == d["last_started"]) & d["rel_any"]).astype(int)
        d["ic"] = np.clip(d["inning"].to_numpy(), 0, N_INN - 1)
        num = np.zeros((N_INN, N_LEAD)); den = np.zeros((N_INN, N_LEAD))
        np.add.at(num, (d["ic"].to_numpy(), d["lead_state"].to_numpy()), d["y"].to_numpy())
        np.add.at(den, (d["ic"].to_numpy(), d["lead_state"].to_numpy()), 1.0)
        inn_num = num.sum(1); inn_den = den.sum(1)
        g_haz = float(d["y"].mean()) if len(d) else 0.0
        haz = np.zeros((N_INN, N_LEAD))
        for k in range(N_INN):
            for L in range(N_LEAD):
                if den[k, L] >= _HAZ_MIN:
                    haz[k, L] = num[k, L] / den[k, L]
                elif inn_den[k] >= _HAZ_MIN:
                    haz[k, L] = inn_num[k] / inn_den[k]
                else:
                    haz[k, L] = g_haz
        haz[:MIN_REMOVAL_INN] = 0.0                   # gate: no early hooks
        return cls(haz)

    def hazard_vec(self, inn: np.ndarray, lead: np.ndarray) -> np.ndarray:
        ic = np.clip(np.asarray(inn), 0, N_INN - 1)
        return self._h[ic, np.asarray(lead)]

    def removed_by(self, inn: int, lead: int) -> float:
        """P(starter already gone entering inning `inn`), lead held constant."""
        ic = int(min(inn, N_INN - 1)); L = int(lead)
        surv = np.prod(1.0 - self._h[:ic, L]) if ic > 0 else 1.0
        return float(1.0 - surv)

    def summary(self) -> dict:
        return {"hazard_inn7": [round(float(x), 4) for x in self._h[7]],
                "hazard_inn8": [round(float(x), 4) for x in self._h[8]],
                "lead_order": "trailing,tied,leading"}


class RelieverPA:
    """Pooled reliever PA-event dist keyed (inn_bucket, LEVERAGE(lead_state),
    batter_tier, freshness). lead_state is the LEVERAGE the task asked for: a pen
    protecting a lead uses its best arms (more suppressive) vs mop-up when trailing.
    Backoff: (b,L,t,f) -> (b,L,t) -> (b,L) -> (b) -> global."""

    def __init__(self, full: Dict[tuple, np.ndarray], by_blt: Dict[tuple, np.ndarray],
                 by_bl: Dict[tuple, np.ndarray], by_b: Dict[int, np.ndarray],
                 glob: np.ndarray):
        self._full = full; self._by_blt = by_blt; self._by_bl = by_bl
        self._by_b = by_b; self._glob = glob

    @classmethod
    def fit(cls, pa: pd.DataFrame, tiers, cadence: pd.DataFrame) -> "RelieverPA":
        pa = pa if "is_relief" in pa.columns else mark_context(pa)
        rel = pa[pa["is_relief"]].copy()
        rel = rel.merge(cadence, on=["game_pk", "pitcher"], how="left")
        rel["fresh"] = (rel["apps_last_3d"].fillna(0.0) < 1.0).astype(int)
        rel["evix"] = rel["pa_evt"].map(_PA_IX)
        rel["tier"] = [tiers.tier(int(b), -1) for b in rel["batter"].to_numpy()]

        def _cnt(g):
            return _norm(np.bincount(g["evix"], minlength=N_PA).astype(float))
        glob = _cnt(rel)
        by_b = {int(b): _cnt(g) for b, g in rel.groupby("inn_bucket")}
        by_bl = {(int(b), int(L)): _cnt(g)
                 for (b, L), g in rel.groupby(["inn_bucket", "lead_state"])}
        by_blt = {(int(b), int(L), int(t)): _cnt(g)
                  for (b, L, t), g in rel.groupby(["inn_bucket", "lead_state", "tier"])
                  if len(g) >= _REL_MIN}
        full = {(int(b), int(L), int(t), int(f)): _cnt(g)
                for (b, L, t, f), g in
                rel.groupby(["inn_bucket", "lead_state", "tier", "fresh"])
                if len(g) >= _REL_MIN}
        return cls(full, by_blt, by_bl, by_b, glob)

    def probs(self, bucket: int, lead: int, tier: int, fresh: int) -> np.ndarray:
        v = self._full.get((int(bucket), int(lead), int(tier), int(fresh)))
        if v is not None:
            return v
        v = self._by_blt.get((int(bucket), int(lead), int(tier)))
        if v is not None:
            return v
        v = self._by_bl.get((int(bucket), int(lead)))
        if v is not None:
            return v
        return self._by_b.get(int(bucket), self._glob)

    def slot_matrix(self, batters, tiers, fresh_frac: float) -> np.ndarray:
        """[N_BUCKET, N_LEAD, 9, 8] reliever PA dists per (inn_bucket, leverage, slot),
        freshness folded in by the game-side fresh fraction."""
        m = np.zeros((N_BUCKET, N_LEAD, 9, N_PA))
        for b in range(N_BUCKET):
            for L in range(N_LEAD):
                for i in range(9):
                    bat = batters[i] if i < len(batters) else (batters[0] if batters else -1)
                    t = tiers.tier(int(bat), -1)
                    m[b, L, i] = (fresh_frac * self.probs(b, L, t, 1)
                                  + (1 - fresh_frac) * self.probs(b, L, t, 0))
        return m

    def summary(self) -> dict:
        return {"n_full_cells": len(self._full), "n_blt_cells": len(self._by_blt),
                "min_cell": _REL_MIN, "buckets": "<=6,7,8,>=9",
                "leverage": "lead_state trailing,tied,leading"}


def reliever_cadence(pa: pd.DataFrame) -> pd.DataFrame:
    """Per relief APPEARANCE: prior relief appearances in the trailing 3 days
    (leak-free -- own history only). Reuses the ingest_bullpen_relief_chains
    rolling derivation. Requires game_date in the frame."""
    pa = pa if "is_relief" in pa.columns else mark_context(pa)
    rel = pa[pa["is_relief"]].copy()
    app = rel.groupby(["game_pk", "pitcher"], as_index=False)["game_date"].first()
    app["game_date"] = pd.to_datetime(app["game_date"])
    app = app.sort_values(["pitcher", "game_date"]).set_index("game_date")
    roll = (app.groupby("pitcher")["game_pk"].rolling("3D").count()
               .reset_index(level=0, drop=True)) - 1.0
    app["apps_last_3d"] = roll
    return app.reset_index()[["game_pk", "pitcher", "apps_last_3d"]]


def bullpen_freshness(pa: pd.DataFrame, cadence: pd.DataFrame) -> Dict[tuple, float]:
    """(game_pk, side) -> fraction of the side's used relievers that were fresh
    (no relief appearance in the trailing 3 days). availability = this fraction."""
    pa = pa if "is_relief" in pa.columns else mark_context(pa)
    rel = pa[pa["is_relief"]].merge(cadence, on=["game_pk", "pitcher"], how="left")
    rel = rel.drop_duplicates(["game_pk", "inning_topbot", "pitcher"])
    rel["fresh"] = (rel["apps_last_3d"].fillna(0.0) < 1.0).astype(float)
    g = rel.groupby(["game_pk", "inning_topbot"])["fresh"].mean()
    return {(int(k[0]), str(k[1])): float(v) for k, v in g.items()}


__all__ = ["RemovalModel", "RelieverPA", "reliever_cadence", "bullpen_freshness",
           "mark_context", "inn_bucket", "inn_bucket_arr", "MIN_REMOVAL_INN",
           "N_BUCKET", "N_INN", "N_LEAD"]
