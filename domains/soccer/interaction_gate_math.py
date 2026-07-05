"""domains.soccer.interaction_gate_math -- A1-S soccer interaction candidates
(S1 xg_pace_sot_regime, S2 xg_supremacy_sot_confirm) math companion.

PREREG_AMENDMENT_A1_2026-07-05.md "Family continuation A1-S": extends the V1
Family 3 (soccer_home_sot_replication_v1) budget with 2 INTERACTION terms on
the IDENTICAL base -- domains.soccer.ratings.walk_forward_goals Poisson
p_over25, over-2.5 target, same 6-league div split (E1/E0/SP1/I1/F1/D1),
expanding-window WF within league, no seam reselect. Mirrors
home_sot_replication_gate.py's build/fit/score shape exactly (never imports
it -- that module is at its LOC cap and owned by wave-1).

S1 soccer_xg_pace_sot_regime: tot_sot_l10 = home_sot_for_l10+away_sot_for_l10;
tot_xg = home_xg_for_asof+away_xg_for_asof; features =
[p_over25_logit, z(tot_sot_l10), z(tot_sot_l10)*1[tot_xg > league-median]]
(TRAIN-ONLY per-league-fold median).

S2 soccer_xg_supremacy_sot_confirm: net_sot_l10 = home_sot_for_l10 -
away_sot_for_l10; agree = 1[sign(net_sot_l10)==sign(diff_xg_supremacy_asof)];
features = [p_over25_logit, z(|diff_xg_supremacy_asof|),
z(|diff_xg_supremacy_asof|)*agree]. sot enters ONLY inside the interaction/
isolation term -- the CLOSED home_sot solo family is not re-gated.

Both candidates fall back to base prob when a row lacks an ingredient (S1:
tot_sot_l10 or tot_xg; S2: net_sot_l10 or diff_xg_supremacy_asof) via
stack_fit.score_with_fallback -- base/candidate score IDENTICAL row sets.

Calibration only; NO $/edge. No src.*/kernel.* imports; no domains.nba/mlb/
tennis imports (F5). ASCII; <=300 LOC.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.soccer.ratings import walk_forward_goals  # noqa: E402
from scripts.platformkit.combo import stack_fit as sf  # noqa: E402

_MATCHES = _REPO / "data" / "domains" / "soccer" / "matches.parquet"
_ASOF_FEATURES = _REPO / "data" / "domains" / "soccer" / "asof_features.parquet"
_ASOF_XG_PROXY = _REPO / "data" / "domains" / "soccer" / "asof_xg_proxy.parquet"
_ODDS = _REPO / "data" / "domains" / "soccer" / "odds.parquet"

LEAGUES: Tuple[str, ...] = ("E1", "E0", "SP1", "I1", "F1", "D1")
MIN_PRIOR = 5  # both teams need >= N strictly-prior matches (matches home_sot precedent)


def build_corpus() -> pd.DataFrame:
    """Poisson p_over25 (leak-free WF) LEFT-MERGED with asof_features +
    asof_xg_proxy on event_id -- the identical base construction the
    replication gate uses, extended with the xG-proxy join for S1/S2."""
    mdf = pd.read_parquet(_MATCHES)
    mdf["event_id"] = mdf["event_id"].astype(str)
    total_goals = (pd.to_numeric(mdf["fthg"], errors="coerce")
                   + pd.to_numeric(mdf["ftag"], errors="coerce"))
    mdf["target_over25"] = (total_goals >= 3).astype(float)
    mdf = mdf[total_goals.notna()].copy()

    wf = walk_forward_goals(mdf)
    wf["event_id"] = wf["event_id"].astype(str)
    wf["p_over25"] = np.clip(wf["p_over25"].astype(float), 1e-6, 1 - 1e-6)

    feats = pd.read_parquet(_ASOF_FEATURES)
    feats["event_id"] = feats["event_id"].astype(str)
    feats = feats.drop_duplicates("event_id", keep="first")
    xg = pd.read_parquet(_ASOF_XG_PROXY)
    xg["event_id"] = xg["event_id"].astype(str)
    xg = xg.drop_duplicates("event_id", keep="first")

    out = wf.merge(feats, on="event_id", how="left", suffixes=("", "_feat"))
    out = out.merge(xg, on="event_id", how="left", suffixes=("", "_xg"))
    return out


def _covered(df: pd.DataFrame, added_cols: Sequence[str]) -> pd.DataFrame:
    """MIN_PRIOR floor (home_sot precedent) AND every added column finite --
    base/candidate compared on the identical row set within each league."""
    home_n = df.get("home_n_prior", pd.Series(0, index=df.index)).fillna(0)
    away_n = df.get("away_n_prior", pd.Series(0, index=df.index)).fillna(0)
    ok = (home_n >= MIN_PRIOR) & (away_n >= MIN_PRIOR)
    for c in added_cols:
        ok &= df[c].notna()
    return df[ok].reset_index(drop=True)


def build_league_frame(league: str, full_corpus: pd.DataFrame,
                        added_cols: Sequence[str]) -> pd.DataFrame:
    """One league's covered, chronologically-sorted frame for a given candidate's
    required raw ingredient columns."""
    lf = full_corpus[full_corpus["div"] == league].sort_values("date").reset_index(drop=True)
    return _covered(lf, added_cols)


# --------------------------------------------------------------------------- #
# S1 soccer_xg_pace_sot_regime
# --------------------------------------------------------------------------- #

_S1_RAW: Tuple[str, ...] = ("home_sot_for_l10", "away_sot_for_l10",
                             "home_xg_for_asof", "away_xg_for_asof")


def s1_raw_ingredients(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    """(tot_sot_l10, tot_xg) raw columns, NaN-propagating (missing either half
    of a sum makes the sum NaN, matching the fallback contract)."""
    home_sot = df["home_sot_for_l10"]
    away_sot = df["away_sot_for_l10"]
    tot_sot = (home_sot + away_sot).where(home_sot.notna() & away_sot.notna())
    home_xg = df["home_xg_for_asof"]
    away_xg = df["away_xg_for_asof"]
    tot_xg = (home_xg + away_xg).where(home_xg.notna() & away_xg.notna())
    return tot_sot.to_numpy(float), tot_xg.to_numpy(float)


def s1_design(base_logit: np.ndarray, tot_sot_z: np.ndarray, tot_xg: np.ndarray,
              league_median_xg: float) -> np.ndarray:
    """[p_over25_logit, z(tot_sot_l10), z(tot_sot_l10)*1[tot_xg>median]]."""
    regime = (tot_xg > league_median_xg).astype(float)
    return sf.build_design([base_logit, tot_sot_z, tot_sot_z * regime])


def s1_fit(train: pd.DataFrame) -> Tuple[sf.LogisticFit, sf.StandardizerParams, float]:
    base_logit = sf.logit(train["p_over25"].to_numpy(float))
    tot_sot, tot_xg = s1_raw_ingredients(train)
    std = sf.fit_standardizer(tot_sot.reshape(-1, 1))
    tot_sot_z = sf.standardize(tot_sot.reshape(-1, 1), std)[:, 0]
    median_xg = float(np.nanmedian(tot_xg))  # TRAIN-ONLY per prereg
    X = s1_design(base_logit, tot_sot_z, tot_xg, median_xg)
    y = train["target_over25"].to_numpy(float)
    return sf.fit_logistic(X, y), std, median_xg


def s1_score(df: pd.DataFrame, fit: sf.LogisticFit, std: sf.StandardizerParams,
             median_xg: float, p_base: np.ndarray) -> np.ndarray:
    base_logit = sf.logit(df["p_over25"].to_numpy(float))
    tot_sot, tot_xg = s1_raw_ingredients(df)
    tot_sot_z = sf.standardize(tot_sot.reshape(-1, 1), std)[:, 0]
    X = s1_design(base_logit, tot_sot_z, tot_xg, median_xg)
    p_cand = sf.predict_proba(X, fit.weights)
    return sf.score_with_fallback([tot_sot, tot_xg], p_base, p_cand)


# --------------------------------------------------------------------------- #
# S2 soccer_xg_supremacy_sot_confirm
# --------------------------------------------------------------------------- #

_S2_RAW: Tuple[str, ...] = ("home_sot_for_l10", "away_sot_for_l10", "diff_xg_supremacy_asof")


def s2_raw_ingredients(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    """(net_sot_l10, diff_xg_supremacy_asof) raw columns."""
    home_sot = df["home_sot_for_l10"]
    away_sot = df["away_sot_for_l10"]
    net_sot = (home_sot - away_sot).where(home_sot.notna() & away_sot.notna())
    diff_xg_sup = df["diff_xg_supremacy_asof"]
    return net_sot.to_numpy(float), diff_xg_sup.to_numpy(float)


def s2_design(base_logit: np.ndarray, abs_diff_xg_z: np.ndarray,
              net_sot: np.ndarray, diff_xg_sup: np.ndarray) -> np.ndarray:
    """[p_over25_logit, z(|diff_xg_supremacy_asof|), z(|diff_xg_supremacy_asof|)*agree]
    where agree = 1[sign(net_sot_l10)==sign(diff_xg_supremacy_asof)]."""
    agree = (np.sign(net_sot) == np.sign(diff_xg_sup)).astype(float)
    return sf.build_design([base_logit, abs_diff_xg_z, abs_diff_xg_z * agree])


def s2_fit(train: pd.DataFrame) -> Tuple[sf.LogisticFit, sf.StandardizerParams]:
    base_logit = sf.logit(train["p_over25"].to_numpy(float))
    net_sot, diff_xg_sup = s2_raw_ingredients(train)
    abs_diff_xg = np.abs(diff_xg_sup)
    std = sf.fit_standardizer(abs_diff_xg.reshape(-1, 1))
    abs_diff_xg_z = sf.standardize(abs_diff_xg.reshape(-1, 1), std)[:, 0]
    X = s2_design(base_logit, abs_diff_xg_z, net_sot, diff_xg_sup)
    y = train["target_over25"].to_numpy(float)
    return sf.fit_logistic(X, y), std


def s2_score(df: pd.DataFrame, fit: sf.LogisticFit, std: sf.StandardizerParams,
             p_base: np.ndarray) -> np.ndarray:
    base_logit = sf.logit(df["p_over25"].to_numpy(float))
    net_sot, diff_xg_sup = s2_raw_ingredients(df)
    abs_diff_xg = np.abs(diff_xg_sup)
    abs_diff_xg_z = sf.standardize(abs_diff_xg.reshape(-1, 1), std)[:, 0]
    X = s2_design(base_logit, abs_diff_xg_z, net_sot, diff_xg_sup)
    p_cand = sf.predict_proba(X, fit.weights)
    return sf.score_with_fallback([net_sot, diff_xg_sup], p_base, p_cand)


# --------------------------------------------------------------------------- #
# Shared base scorer + expanding-window fit/score orchestration
# --------------------------------------------------------------------------- #

def fit_base(train: pd.DataFrame) -> sf.LogisticFit:
    X = sf.build_design([sf.logit(train["p_over25"].to_numpy(float))])
    return sf.fit_logistic(X, train["target_over25"].to_numpy(float))


def score_base(df: pd.DataFrame, fit: sf.LogisticFit) -> np.ndarray:
    X = sf.build_design([sf.logit(df["p_over25"].to_numpy(float))])
    return sf.predict_proba(X, fit.weights)


CANDIDATE_RAW: Dict[str, Tuple[str, ...]] = {"S1": _S1_RAW, "S2": _S2_RAW}
CANDIDATE_FITTERS = {"S1": s1_fit, "S2": s2_fit}
CANDIDATE_SCORERS = {"S1": s1_score, "S2": s2_score}


__all__ = [
    "LEAGUES", "MIN_PRIOR", "build_corpus", "build_league_frame",
    "s1_raw_ingredients", "s1_design", "s1_fit", "s1_score",
    "s2_raw_ingredients", "s2_design", "s2_fit", "s2_score",
    "fit_base", "score_base", "CANDIDATE_RAW", "CANDIDATE_FITTERS",
    "CANDIDATE_SCORERS", "_MATCHES", "_ASOF_FEATURES", "_ASOF_XG_PROXY", "_ODDS",
]
