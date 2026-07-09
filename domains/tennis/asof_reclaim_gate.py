"""domains.tennis.asof_reclaim_gate -- ATP as-of RECLAIM gate (hold% / return / form).

Reclaims the three already-built, already-leak-free ATP as-of parquets flagged in
docs/research/ceiling/ONDISK_RECLAIM_TARGETS.md (#3): asof_hold.parquet (per-surface
trailing hold% + svpts-won%), asof_return.parquet (return-won% + break% diffs),
asof_features.parquet (serve/return FORM diffs).  Runs each candidate through the SAME
single-corpus walk-forward Diebold-Mariano gate the WTA companion reclaim uses
(domains.tennis.asof_hold_wta_gate, itself modelled on the NBA ast_rate_diff_asof /
MLB sp_ra_diff_asof reclaim template), extended to ALSO score against the DEVIGGED
CLOSE where odds coverage supports it (84.2% via ps_p1/ps_p2 or b365_p1/b365_p2 --
domains.tennis.adapter_helpers._devig_prob).

CANDIDATE-ONLY / DEFAULT-OFF: reads the parquets additively; does NOT touch
TennisAdapter.feature_bundle, signal_catalog.py, or any predictor/flag.  Verdict is
CALIBRATION (held-out Brier), never $ or ROI.  A REJECT/NULL is an HONEST SUCCESS.

LEAK-FREE: Elo via domains.tennis.elo_walkforward.walk_forward_elo (snapshot-before-
update, the SAME function elo.py re-exports / TennisAdapter uses); every candidate
column is itself a strict-prior trailing aggregate with its own future-leak assertion
already enforced at build time.  NaN feature -> 0 (neutral) after standardizing on
TRAIN stats; DM computed on COVERED rows only (both players >= MIN_PRIOR strictly-
prior matches).

WHY SINGLE-CORPUS: matches.parquet is the ATP tour spine (30,616 rows) -- distinct
from the WTA gate's wta_matches.parquet (11,270 rows, separate players/elo state); we
never mix ATP/WTA rows here (prior honesty rail).  Robustness comes from the
PLANTED-NULL control (a shuffled feature must collapse) and TRUNCATION-INVARIANCE
(drop the last 10% of train rows -> verdict must not flip).

Reporting / CLI / verdict-JSON persistence lives in the sibling module
asof_reclaim_gate_report.py (LOC-split); this module is pure gate math.
No src.*/kernel.* imports.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from domains.tennis.adapter_helpers import _devig_prob
from domains.tennis.asof_reclaim_gate_fit import brier, fit_2feature, logit, platt_fit, sigmoid
from domains.tennis.elo_walkforward import walk_forward_elo
from scripts.platformkit.eval_gate.dm_test import diebold_mariano

_REPO = Path(__file__).resolve().parents[2]
_MATCHES = _REPO / "data/domains/tennis/matches.parquet"
_ODDS = _REPO / "data/domains/tennis/odds.parquet"
_ASOF_HOLD = _REPO / "data/domains/tennis/asof_hold.parquet"
_ASOF_RETURN = _REPO / "data/domains/tennis/asof_return.parquet"
_ASOF_FEATURES = _REPO / "data/domains/tennis/asof_features.parquet"

MIN_PRIOR = 5          # both players need >= N strictly-prior matches for "covered"
TRAIN_FRAC = 0.70      # leak-free time split (first 70% train, last 30% score)
EPS = 0.05             # DM significance threshold
BSS_MIN = 0.0          # base must carry non-degenerate skill vs the base rate

# (candidate feature name, source parquet, [(out_diff_col, p1_col, p2_col), ...] or
#  None when the parquet already ships the diff_* column directly, min_prior cols)
_CandidateSpec = Tuple[str, Path, Optional[Tuple[str, str, str]], Tuple[str, str]]

CANDIDATES: Tuple[_CandidateSpec, ...] = (
    # --- asof_hold.parquet: overall + per-surface hold% diffs (derived; no diff_* shipped) ---
    ("hold_pct_diff_asof", _ASOF_HOLD,
     ("hold_pct_diff_asof", "p1_hold_pct_asof", "p2_hold_pct_asof"),
     ("p1_n_prior", "p2_n_prior")),
    ("hold_pct_hard_diff_asof", _ASOF_HOLD,
     ("hold_pct_hard_diff_asof", "p1_hold_pct_hard_asof", "p2_hold_pct_hard_asof"),
     ("p1_n_prior", "p2_n_prior")),
    ("hold_pct_clay_diff_asof", _ASOF_HOLD,
     ("hold_pct_clay_diff_asof", "p1_hold_pct_clay_asof", "p2_hold_pct_clay_asof"),
     ("p1_n_prior", "p2_n_prior")),
    ("hold_pct_grass_diff_asof", _ASOF_HOLD,
     ("hold_pct_grass_diff_asof", "p1_hold_pct_grass_asof", "p2_hold_pct_grass_asof"),
     ("p1_n_prior", "p2_n_prior")),
    # --- asof_hold.parquet: svpts-won% overall + per-surface (NEVER gated before --
    # utilization_matrix_2026_07_10.md flagged these as built-but-unconsumed siblings
    # of hold_pct, which the gate above already covers) ---
    ("svpts_won_diff_asof", _ASOF_HOLD,
     ("svpts_won_diff_asof", "p1_svpts_won_asof", "p2_svpts_won_asof"),
     ("p1_n_prior", "p2_n_prior")),
    ("svpts_won_hard_diff_asof", _ASOF_HOLD,
     ("svpts_won_hard_diff_asof", "p1_svpts_won_hard_asof", "p2_svpts_won_hard_asof"),
     ("p1_n_prior", "p2_n_prior")),
    ("svpts_won_clay_diff_asof", _ASOF_HOLD,
     ("svpts_won_clay_diff_asof", "p1_svpts_won_clay_asof", "p2_svpts_won_clay_asof"),
     ("p1_n_prior", "p2_n_prior")),
    ("svpts_won_grass_diff_asof", _ASOF_HOLD,
     ("svpts_won_grass_diff_asof", "p1_svpts_won_grass_asof", "p2_svpts_won_grass_asof"),
     ("p1_n_prior", "p2_n_prior")),
    # --- asof_return.parquet: ships diff_* columns directly ---
    ("diff_return_won_asof", _ASOF_RETURN, None,
     ("return_won_n_prior", "return_won_n_prior")),  # per-metric prior cols; see NOTE below
    ("diff_break_pct_asof", _ASOF_RETURN, None,
     ("break_pct_n_prior", "break_pct_n_prior")),
    # --- asof_features.parquet (serve/return FORM diffs): ships diff_* + shared p1/p2_n_prior ---
    ("diff_1st_win_asof", _ASOF_FEATURES, None, ("p1_n_prior", "p2_n_prior")),
    ("diff_ace_rate_asof", _ASOF_FEATURES, None, ("p1_n_prior", "p2_n_prior")),
    ("diff_2nd_win_asof", _ASOF_FEATURES, None, ("p1_n_prior", "p2_n_prior")),
    ("diff_bp_saved_asof", _ASOF_FEATURES, None, ("p1_n_prior", "p2_n_prior")),
)
# asof_return.parquet's n_prior cols are PER-METRIC/per-side (p1_return_won_n_prior,
# p1_break_pct_n_prior, ...); the tuples above store the metric-specific base name
# and _load_candidate_frame expands it into the correct p1_/p2_ pair (see below).


# --------------------------------------------------------------------------- #
# Frame construction (ATP-only; never mixes in wta_matches.parquet rows)
# --------------------------------------------------------------------------- #

def _elo_and_close(matches: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Leak-free ATP Elo P(p1) + devigged close, keyed event_id, chrono-sorted."""
    mm = matches.copy() if isinstance(matches, pd.DataFrame) else pd.read_parquet(_MATCHES)
    mm = mm[mm["winner"].notna()].reset_index(drop=True)
    wf = walk_forward_elo(mm)

    odds = pd.read_parquet(_ODDS)
    _cols = ["event_id", "ps_p1", "ps_p2", "b365_p1", "b365_p2"]
    odds_sel = odds[[c for c in _cols if c in odds.columns]].drop_duplicates(
        "event_id", keep="first")
    wf = wf.merge(odds_sel, on="event_id", how="left")

    out = wf[["event_id", "date", "winner", "win_prob_p1"]].rename(
        columns={"win_prob_p1": "p_base"})
    out["target_p1_win"] = (out["winner"].astype(float) == 1.0).astype(float)
    out["p_close"] = wf.apply(lambda r: _devig_prob(r, kind="close"), axis=1)
    return out.sort_values("date").reset_index(drop=True)


def _load_candidate_frame(spec: _CandidateSpec, base_close: pd.DataFrame) -> pd.DataFrame:
    """Left-merge ONE candidate feature (+ its prior-count cols) onto base_close."""
    feat_col, path, derive, prior_base = spec
    df = pd.read_parquet(path)

    if derive is not None:
        diff_col, p1_col, p2_col = derive
        if p1_col in df.columns and p2_col in df.columns:
            df = df.copy()
            df[diff_col] = pd.to_numeric(df[p1_col], errors="coerce") - pd.to_numeric(
                df[p2_col], errors="coerce")
        elif diff_col not in df.columns:
            raise KeyError(
                f"_load_candidate_frame: cannot derive '{diff_col}' -- source "
                f"columns '{p1_col}'/'{p2_col}' are missing from {path} and "
                f"'{diff_col}' is not already present as a direct column."
            )
        # else: diff_col already present directly (e.g. a pre-computed fixture) --
        # use it as-is rather than overwriting with a derivation we cannot perform.

    p1_prior_base, p2_prior_base = prior_base
    # asof_return's prior cols are metric-prefixed (p1_return_won_n_prior); asof_hold
    # and asof_features share a single p1_n_prior/p2_n_prior pair. Resolve whichever
    # the parquet actually has.
    if p1_prior_base in df.columns:
        p1_prior_col, p2_prior_col = p1_prior_base, p2_prior_base
    else:
        p1_prior_col, p2_prior_col = f"p1_{p1_prior_base}", f"p2_{p2_prior_base}"

    keep = ["event_id", feat_col, p1_prior_col, p2_prior_col]
    keep = [c for c in keep if c in df.columns]
    df = df[keep].drop_duplicates("event_id", keep="first")

    out = base_close.merge(df, on="event_id", how="left")
    out["_cov"] = (
        out.get(p1_prior_col, pd.Series(0, index=out.index)).fillna(0) >= MIN_PRIOR
    ) & (
        out.get(p2_prior_col, pd.Series(0, index=out.index)).fillna(0) >= MIN_PRIOR
    ) & out[feat_col].notna()
    return out


# --------------------------------------------------------------------------- #
# One single-corpus walk-forward DM gate (vs a chosen baseline column)
# --------------------------------------------------------------------------- #

def _gate_once(
    df: pd.DataFrame, feat_col: str, base_col: str,
    train_frac: float = TRAIN_FRAC, eps: float = EPS,
) -> Dict:
    """Single-corpus 70/30 walk-forward DM gate: base_col alone vs base_col+feature."""
    n = len(df)
    split = int(n * train_frac)
    tr, te = df.iloc[:split], df.iloc[split:]
    # base_col coverage (e.g. p_close is sparser than p_base) is enforced later via
    # the `cov` mask on the TEST rows; TRAIN rows with a missing base_col fall back
    # to 0.5 (neutral logit) below so the Platt/2-feature fits never see a NaN.

    y_tr = tr["target_p1_win"].values.astype(float)
    y_te = te["target_p1_win"].values.astype(float)

    lz_tr = logit(tr[base_col].fillna(0.5).values.astype(float))
    lz_te = logit(te[base_col].fillna(0.5).values.astype(float))
    f_tr = tr[feat_col].values.astype(float)
    f_te = te[feat_col].values.astype(float)
    m, s = float(np.nanmean(f_tr)), max(float(np.nanstd(f_tr)), 1e-8)
    fz_tr = np.nan_to_num((f_tr - m) / s)
    fz_te = np.nan_to_num((f_te - m) / s)

    wb, bb_ = platt_fit(lz_tr, y_tr)
    p_base = sigmoid(wb * lz_te + bb_)
    p_cand, w2 = fit_2feature(lz_tr, fz_tr, y_tr, lz_te, fz_te)

    # Coverage: candidate feature present AND base_col present on the test row.
    cov = (te["_cov"].values.astype(bool)) & te[base_col].notna().values
    if cov.sum() == 0:
        return {
            "n_cov_test": 0, "brier_base": None, "brier_cand": None,
            "brier_delta": None, "dm_stat": None, "dm_p": None,
            "feat_weight": round(float(w2), 5), "base_bss": None,
            "base_degenerate": True, "verdict": "NOT_TESTABLE",
        }
    yb = y_te[cov]
    br_base = brier(yb, p_base[cov])
    br_cand = brier(yb, p_cand[cov])
    d = (p_base[cov] - yb) ** 2 - (p_cand[cov] - yb) ** 2
    dm = diebold_mariano(d, te["event_id"].astype(str).values[cov])

    base_rate = float(np.mean(y_tr))
    br_const = brier(yb, np.full_like(yb, base_rate))
    bss = (br_const - br_base) / br_const if br_const > 0 else 0.0
    degen = bss < BSS_MIN
    beats = bool((br_cand < br_base) and (dm.p_value < eps) and not degen)
    return {
        "n_cov_test": int(cov.sum()), "brier_base": round(br_base, 6),
        "brier_cand": round(br_cand, 6), "brier_delta": round(br_base - br_cand, 6),
        "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
        "feat_weight": round(float(w2), 5), "base_bss": round(bss, 5),
        "base_degenerate": degen, "verdict": "SHIP" if beats else "REJECT",
    }


def _planted_null(df: pd.DataFrame, feat_col: str, base_col: str, seed: int = 0) -> Dict:
    """Shuffle the feature column (break its match alignment) -> must collapse."""
    rng = np.random.default_rng(seed)
    nd = df.copy()
    nd[feat_col] = rng.permutation(nd[feat_col].values)
    return _gate_once(nd, feat_col, base_col)


def _gate_vs_baseline(df: pd.DataFrame, feat_col: str, base_col: str, seed: int = 0) -> Dict:
    """REAL + planted-null + truncation-invariance for one (feature, baseline) pair."""
    real = _gate_once(df, feat_col, base_col)
    null = _planted_null(df, feat_col, base_col, seed=seed)
    trunc = _gate_once(df, feat_col, base_col, train_frac=TRAIN_FRAC * 0.90)
    return {"real": real, "planted_null": null, "truncation": trunc}


# --------------------------------------------------------------------------- #
# Top-level: gate ALL candidates vs Elo AND vs the devigged close
# --------------------------------------------------------------------------- #

def gate_feature(feat_col: str, spec: _CandidateSpec, seed: int = 0) -> Dict:
    """Gate ONE ATP as-of candidate vs p_base (Elo) and vs p_close (devigged)."""
    base_close = _elo_and_close()
    df = _load_candidate_frame(spec, base_close)
    n = len(df)
    cov_total = int(df["_cov"].sum())
    close_cov = int((df["_cov"] & df["p_close"].notna()).sum())

    vs_elo = _gate_vs_baseline(df, feat_col, "p_base", seed=seed)
    vs_close = (
        _gate_vs_baseline(df, feat_col, "p_close", seed=seed)
        if close_cov >= 50 else None
    )
    return {
        "feature": feat_col, "n_rows": n, "cov_total": cov_total,
        "cov_pct": round(100.0 * cov_total / max(n, 1), 1),
        "close_cov_total": close_cov, "vs_elo": vs_elo, "vs_close": vs_close,
    }


def run_all(seed: int = 0) -> List[Dict]:
    """Gate every candidate in CANDIDATES; return one result dict per candidate."""
    return [gate_feature(spec[0], spec, seed=seed) for spec in CANDIDATES]


def _honest_verdict(res: Dict) -> str:
    """Reduce one candidate's vs_elo/vs_close results to ONE honest label."""
    ve = res["vs_elo"]["real"]
    if ve["verdict"] == "NOT_TESTABLE":
        return "NOT_TESTABLE"
    null_ok = res["vs_elo"]["planted_null"]["verdict"] != "SHIP"
    trunc_ok = res["vs_elo"]["truncation"]["verdict"] == ve["verdict"]
    if ve["verdict"] == "SHIP" and null_ok and trunc_ok:
        return "SHIP"
    if ve["verdict"] == "SHIP" and not (null_ok and trunc_ok):
        return "REJECT"  # SHIP that fails a control is an artifact, not a ship
    return "REJECT"


__all__ = [
    "CANDIDATES", "gate_feature", "run_all", "_honest_verdict",
    "_elo_and_close", "_load_candidate_frame", "_gate_once", "_gate_vs_baseline",
]
