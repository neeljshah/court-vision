"""scripts.platformkit.ceiling.asof_replication_core -- split schemes + gate
logic for the asof cross-corpus replication check (see asof_replication.py
for the CLI/writers and the full contract docstring).

SPLIT SCHEMES (mirrors ingame_segment_trust.py's md5 discipline + sp_adjust's
both-eras-same-sign discipline):
  (a) SEASON-ERA split: sort by date, first half of rows = era A, second half
      = era B.
  (b) md5 DATE-PARITY split: md5(event_id) even/odd -> two interleaved,
      deterministic sub-corpora (NOT builtin hash(), which is per-process
      randomized -- see ingame_segment_trust.py comment).
Each half is walk-forward evaluated STRICTLY WITHIN itself via the
candidate's own single-corpus _gate_once (70/30 time-ordered train/test) --
zero cross-boundary leakage.

CANDIDATE-ONLY / DEFAULT-OFF: imports the existing gate contracts read-only.
No flag flipped, no adapter touched, no src.*/kernel.*/api.* import.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple

import numpy as np
import pandas as pd

DM_P_THRESHOLD = 0.10   # per-sub-corpus significance bar for the replication count
MIN_SIGNIFICANT = 3     # of 4 sub-corpora must clear DM_P_THRESHOLD
MIN_ROWS_PER_HALF = 40  # minimum covered rows for a half to be usable


@dataclass(frozen=True)
class ReplicationSpec:
    sport: str
    signal: str
    feat_col: str
    build_frame: Callable[[], pd.DataFrame]
    gate_once: Callable[..., Dict]
    wave1_dm_p: float
    wave1_weight_sign: int   # sign(feat_weight) recorded in the wave-1 report


# --------------------------------------------------------------------------- #
# Candidate registry: name -> (build_frame(), gate_once(df, feat_col, train_frac))
# --------------------------------------------------------------------------- #

def _wta_frame() -> pd.DataFrame:
    from domains.tennis import asof_hold_wta_gate as wta
    return wta.build_candidate_frame()


def _wta_gate_once(df: pd.DataFrame, feat_col: str, train_frac: float) -> Dict:
    from domains.tennis import asof_hold_wta_gate as wta
    return wta._gate_once(df, feat_col=feat_col, train_frac=train_frac)


def _soccer_frame(feat_col: str) -> Callable[[], pd.DataFrame]:
    def _fn() -> pd.DataFrame:
        from domains.soccer import asof_features_gate as soc
        return soc.build_candidate_frame(feat_col=feat_col)
    return _fn


def _soccer_gate_once(df: pd.DataFrame, feat_col: str, train_frac: float) -> Dict:
    from domains.soccer import asof_features_gate as soc
    return soc._gate_once(df, feat_col=feat_col, train_frac=train_frac)


def registry() -> List[ReplicationSpec]:
    """The 3 wave-1 asof-reclaim survivors up for cross-corpus replication.
    wave1_dm_p values are the recorded single-corpus numbers from the lane
    brief (wta dm_p=0.0334; soccer sot dm_p=0.030; soccer shots dm_p=0.049) --
    used only for reporting context, not re-derived here."""
    return [
        ReplicationSpec(
            sport="tennis", signal="wta_hold_pct_diff_asof",
            feat_col="hold_pct_diff_asof", build_frame=_wta_frame,
            gate_once=_wta_gate_once, wave1_dm_p=0.0334, wave1_weight_sign=0,
        ),
        ReplicationSpec(
            sport="soccer", signal="soccer_diff_sot_for_asof",
            feat_col="diff_sot_for_asof", build_frame=_soccer_frame("diff_sot_for_asof"),
            gate_once=_soccer_gate_once, wave1_dm_p=0.030, wave1_weight_sign=0,
        ),
        ReplicationSpec(
            sport="soccer", signal="soccer_diff_shots_for_asof",
            feat_col="diff_shots_for_asof", build_frame=_soccer_frame("diff_shots_for_asof"),
            gate_once=_soccer_gate_once, wave1_dm_p=0.049, wave1_weight_sign=0,
        ),
    ]


# --------------------------------------------------------------------------- #
# Split schemes
# --------------------------------------------------------------------------- #

def season_era_split(df: pd.DataFrame, date_col: str = "date") -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Chronological halves by row count after date-sort: first half = era A
    (earlier seasons), second half = era B (later seasons).  Disjoint, no
    row shared between halves."""
    d = df.sort_values(date_col, kind="mergesort").reset_index(drop=True)
    n = len(d)
    mid = n // 2
    era_a = d.iloc[:mid].reset_index(drop=True)
    era_b = d.iloc[mid:].reset_index(drop=True)
    return era_a, era_b


def md5_parity_split(df: pd.DataFrame, id_col: str = "event_id") -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Deterministic md5(event_id) even/odd split.  Uses hashlib.md5 (NOT
    builtin hash(), which is per-process randomized via PYTHONHASHSEED and
    would make the split -- and thus the verdict -- non-reproducible run to
    run; mirrors ingame_segment_trust.py's discipline)."""
    ids = df[id_col].astype(str).values
    parity = np.array([int(hashlib.md5(i.encode("utf-8")).hexdigest(), 16) % 2 for i in ids])
    even = df.loc[parity == 0].sort_values("date", kind="mergesort").reset_index(drop=True)
    odd = df.loc[parity == 1].sort_values("date", kind="mergesort").reset_index(drop=True)
    return even, odd


# --------------------------------------------------------------------------- #
# Per-sub-corpus walk-forward gate (re-uses the candidate's own _gate_once,
# so leak discipline / Platt fit / DM clustering is IDENTICAL to wave 1;
# each half is evaluated strictly within itself)
# --------------------------------------------------------------------------- #

def _min_rows_ok(sub: pd.DataFrame, min_rows: int = MIN_ROWS_PER_HALF) -> bool:
    """A sub-corpus needs enough covered rows for a stable 70/30 WF split;
    below this it is INSUFFICIENT_DATA, not REJECT (honest, not conflated)."""
    return int(sub.get("_cov", pd.Series(dtype=bool)).sum()) >= min_rows


def _gate_sub_corpus(spec: ReplicationSpec, sub: pd.DataFrame) -> Dict:
    if not _min_rows_ok(sub):
        return {"verdict": "INSUFFICIENT_DATA", "n_cov_test": 0,
                "brier_delta": None, "dm_p": None, "feat_weight": None}
    try:
        res = spec.gate_once(sub, spec.feat_col, 0.70)
    except Exception as exc:  # robust: one bad half never kills the run
        return {"verdict": "ERROR", "error": str(exc)[:200],
                "brier_delta": None, "dm_p": None, "feat_weight": None}
    return res


def _scheme_verdict(halves: Dict[str, Dict]) -> Dict:
    """Reduce {name: gate_result} for one split scheme -> pass/fail summary."""
    usable = {k: v for k, v in halves.items() if v.get("verdict") not in ("INSUFFICIENT_DATA", "ERROR")}
    all_improve = bool(usable) and all((v.get("brier_delta") or 0) > 0 for v in usable.values())
    signs = {k: (1 if (v.get("feat_weight") or 0) > 0 else -1 if (v.get("feat_weight") or 0) < 0 else 0)
             for k, v in usable.items()}
    same_sign = len(set(signs.values())) == 1 and 0 not in signs.values() if usable else False
    return {"halves": halves, "all_improve": all_improve, "same_sign": same_sign,
            "n_usable": len(usable)}


# --------------------------------------------------------------------------- #
# Full replication run for one candidate
# --------------------------------------------------------------------------- #

def replicate_one(spec: ReplicationSpec) -> Dict:
    df = spec.build_frame()
    era_a, era_b = season_era_split(df)
    par_even, par_odd = md5_parity_split(df)

    era_a_res = _gate_sub_corpus(spec, era_a)
    era_b_res = _gate_sub_corpus(spec, era_b)
    par_even_res = _gate_sub_corpus(spec, par_even)
    par_odd_res = _gate_sub_corpus(spec, par_odd)

    era_scheme = _scheme_verdict({"era_a": era_a_res, "era_b": era_b_res})
    parity_scheme = _scheme_verdict({"parity_even": par_even_res, "parity_odd": par_odd_res})

    all_four = {"era_a": era_a_res, "era_b": era_b_res,
                "parity_even": par_even_res, "parity_odd": par_odd_res}
    usable_four = {k: v for k, v in all_four.items() if v.get("verdict") not in ("INSUFFICIENT_DATA", "ERROR")}
    n_significant = sum(1 for v in usable_four.values()
                        if v.get("dm_p") is not None and v["dm_p"] < DM_P_THRESHOLD)

    both_schemes_improve = era_scheme["all_improve"] and parity_scheme["all_improve"]
    both_schemes_same_sign = era_scheme["same_sign"] and parity_scheme["same_sign"]
    enough_data = len(usable_four) == 4
    replicates = bool(
        enough_data and both_schemes_improve and both_schemes_same_sign
        and n_significant >= MIN_SIGNIFICANT
    )

    if not enough_data:
        verdict, reason = "INCONCLUSIVE", (
            f"only {len(usable_four)}/4 sub-corpora had enough covered rows "
            f"(need >={MIN_ROWS_PER_HALF} covered rows per half) -- cannot adjudicate replication"
        )
    elif replicates:
        verdict, reason = "SHIP_REVIEW", (
            "REPLICATED: Brier improves + same-sign weight in both halves of "
            f"both schemes, dm_p<{DM_P_THRESHOLD} in {n_significant}/4 sub-corpora "
            "-- flagged for HUMAN queue, NOT wired anywhere"
        )
    else:
        reasons = []
        if not both_schemes_improve:
            reasons.append("Brier delta did not improve in every sub-corpus")
        if not both_schemes_same_sign:
            reasons.append("feature weight sign was not consistent within a scheme")
        if n_significant < MIN_SIGNIFICANT:
            reasons.append(f"only {n_significant}/4 sub-corpora cleared dm_p<{DM_P_THRESHOLD}")
        verdict, reason = "REJECT", "; ".join(reasons) if reasons else "replication bar not met"

    return {
        "sport": spec.sport, "signal": spec.signal, "feature": spec.feat_col,
        "wave1_dm_p": spec.wave1_dm_p,
        "n_rows_total": int(len(df)),
        "season_era_scheme": era_scheme,
        "md5_parity_scheme": parity_scheme,
        "n_significant_sub_corpora": n_significant,
        "verdict": verdict, "verdict_reason": reason,
    }
