"""scripts.platformkit.combo.combination_bind -- BIND families to the REAL in-game
corpora and RUN the enumerated combinations through the PROVEN combo gate.

This is the only module that touches a real corpus, and it touches it ONLY to MATERIALISE
a combination's detail column (a deterministic transform over already-leak-free detail
columns merged onto the base in-game state). It builds nothing that serves, fits nothing,
flips nothing, writes no data/registry/. The verdict is whatever combo_gate.gate_combo
returns -- this module CONSUMES the gate, never weakens it.

A combination = a single derived detail column on the (game_id, asof_idx) grid:
  COMB_DETAIL_x_DETAIL : col = a * b
  COMB_INTERACTION     : col = a * b            (op=mul)
                         col = a * sign(b)       (op=mul_sign)
  COMB_WEAK_ON_PROVEN  : col = weak * sign(state_diff)   (proven = the margin/time prior)
  COMB_REGIME          : col = base, ZEROED outside the regime bucket (run only in-state)
  COMB_RESID_ON_RESID  : col = outer with the inner-linear part regressed out (residual)
The derived column is handed to gate_detail_layer (inside gate_combo) which squashes it
to the p0 slot and gates BASE+detail vs BASE cross-corpus, both directions, DM-by-game.

The detail handles per sport are the name-stable leaf columns of the detail parquet; the
PROVEN prior is the base `state_diff` (margin) column the gate already fits. Per-sport
binding only enumerates sports with >=2 corpora (cross-corpus replication needs two).

Calibration, not edge; no $/ROI token anywhere. numpy + pandas + stdlib; ASCII; <=300 LOC.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.combo.combination_families import (
    CombinationSpec, all_combination_specs,
)
from scripts.platformkit.combo.combo_gate import gate_combo

log = logging.getLogger("combination_bind")
_REPO = Path(__file__).resolve().parents[3]
_ING = _REPO / "data" / "cache" / "ingame"

# Per sport: (base_a, detail_a, base_b, detail_b, [detail handles]). Two corpora each.
CORPORA: Dict[str, Tuple[str, str, str, str, Tuple[str, ...]]] = {
    "mlb": ("mlb_atbat_states__2022.parquet", "mlb_atbat_states__2022.parquet",
            "mlb_atbat_states__2023.parquet", "mlb_atbat_states__2023.parquet",
            ("runners", "outs", "base_run_value")),
    "nba": ("possession_states_2024_25.parquet", "possession_states_2024_25.parquet",
            "possession_states_2025_26.parquet", "possession_states_2025_26.parquet",
            ("pace_so_far", "run_diff", "poss_since_lead_change", "possessions_elapsed")),
    "soccer": ("soccer_states__combo_eng_ger.parquet",
               "soccer_cardstates__combo_eng_ger.parquet",
               "soccer_states__combo_esp_ita.parquet",
               "soccer_cardstates__combo_esp_ita.parquet",
               ("red_diff", "yellow_diff", "sub_count_diff", "shot_zone_diff")),
    "tennis": ("tennis_states__atp.parquet", "tennis_gamestate__atp.parquet",
               "tennis_states__wta.parquet", "tennis_gamestate__wta.parquet",
               ("games_diff_in_set", "sets_diff", "break_pts_converted_diff",
                "serve_holds_streak")),
}

_REGIME_FN = {  # regime bucket -> boolean mask over (state_diff, frac_elapsed)
    "lead_home": lambda sd, fe: sd > 0,
    "lead_away": lambda sd, fe: sd < 0,
    "tied": lambda sd, fe: sd == 0,
    "late_game": lambda sd, fe: fe >= 0.75,
}


def _load(name: str) -> pd.DataFrame:
    return pd.read_parquet(_ING / name)


def _merge(base: pd.DataFrame, detail: pd.DataFrame,
           handles: Tuple[str, ...]) -> pd.DataFrame:
    """Inner-merge detail handle cols + base onto (game_id, asof_idx); float handles."""
    base = base.copy()
    base["game_id"] = base["game_id"].astype(str)
    keep_detail = [c for c in handles if c in detail.columns]
    det = detail[["game_id", "asof_idx", *keep_detail]].copy()
    det["game_id"] = det["game_id"].astype(str)
    m = base.merge(det, on=["game_id", "asof_idx"], how="inner",
                   suffixes=("", "_det"))
    for c in keep_detail:
        col = c if c in m.columns else c + "_det"
        m[c] = pd.to_numeric(m[col], errors="coerce").astype(float)
    return m


def materialise_combo(m: pd.DataFrame, spec: CombinationSpec) -> Optional[np.ndarray]:
    """Deterministic detail column for a spec over a merged frame, or None if unbindable."""
    p = spec.params
    fam = spec.family

    def col(name: str) -> Optional[np.ndarray]:
        if name in m.columns:
            return m[name].to_numpy(dtype=float)
        return None

    if fam == "COMB_DETAIL_x_DETAIL":
        a, b = col(p["a"]), col(p["b"])
        return None if a is None or b is None else a * b
    if fam == "COMB_INTERACTION":
        a, b = col(p["a"]), col(p["b"])
        if a is None or b is None:
            return None
        return a * np.sign(b) if p.get("op") == "mul_sign" else a * b
    if fam == "COMB_WEAK_ON_PROVEN":
        w = col(p["weak"])
        sd = col("state_diff")
        if w is None or sd is None:
            return None
        return w * np.sign(sd)  # weak conditioned on the proven margin prior
    if fam == "COMB_REGIME":
        base = col(p["base"])
        sd, fe = col("state_diff"), col("frac_elapsed")
        if base is None or sd is None or fe is None:
            return None
        mask = _REGIME_FN[p["regime"]](sd, fe)
        return np.where(mask, base, 0.0)
    if fam == "COMB_RESID_ON_RESID":
        outer, inner = col(p["outer"]), col(p["inner"])
        if outer is None or inner is None:
            return None
        if inner.std() < 1e-12:
            return outer
        beta = float(np.cov(outer, inner)[0, 1] / np.var(inner))
        return outer - beta * inner  # outer's residual after the inner-linear part
    return None


def _detail_frame(m: pd.DataFrame, vals: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame({"game_id": m["game_id"].to_numpy(),
                         "asof_idx": m["asof_idx"].to_numpy(),
                         "detail": vals})


@dataclass
class BindRun:
    sport: str
    combo_id: str
    family: str
    signature: str
    verdict: str
    reason: str
    layer: str


def run_sport(sport: str, *, k: int, eps: float = 0.05,
              max_specs: Optional[int] = None) -> List[BindRun]:
    """Materialise + gate every enumerated combo for one sport. K is the live FWER count.

    Returns one BindRun per combo. The verdict is gate_combo's -- this consumes the gate.
    """
    cfg = CORPORA[sport]
    ba, da, bb, db, handles = cfg
    base_a, det_a = _load(ba), _load(da)
    base_b, det_b = _load(bb), _load(db)
    m_a = _merge(base_a, det_a, handles)
    m_b = _merge(base_b, det_b, handles)
    specs = all_combination_specs(sport, "home_win", handles)
    if max_specs is not None:
        specs = specs[:max_specs]
    runs: List[BindRun] = []
    for spec in specs:
        va = materialise_combo(m_a, spec)
        vb = materialise_combo(m_b, spec)
        if va is None or vb is None:
            runs.append(BindRun(sport, spec.combo_id, spec.family, spec.signature,
                                "REJECT", "unbindable: missing handle", "BIND"))
            continue
        det_fa = _detail_frame(m_a, va)
        det_fb = _detail_frame(m_b, vb)
        try:
            v = gate_combo(spec, m_a, det_fa, m_b, det_fb, combo_col="detail",
                           base_feature_cols=None, parity_ok=True, eps=eps,
                           K=k, n_corpora=2)
            runs.append(BindRun(sport, spec.combo_id, spec.family, spec.signature,
                                v.verdict, v.reason, v.layer))
        except Exception as exc:  # malformed combo -> conservative REJECT, never crash
            runs.append(BindRun(sport, spec.combo_id, spec.family, spec.signature,
                                "REJECT", f"gate error: {type(exc).__name__}", "ERR"))
    return runs


__all__ = ["CORPORA", "materialise_combo", "run_sport", "BindRun"]
