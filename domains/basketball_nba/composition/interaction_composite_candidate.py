"""domains.basketball_nba.composition.interaction_composite_candidate --
CANDIDATE ONLY, side-by-side evaluation. Wires the 2 REPLICATED interaction
terms from the interaction_factory ledger
(data/cache/intel_claims/interaction_factory_ledger.jsonl) into the v2
composite as an ADDITIONAL feature, evaluated against the plain v2 composite
using the SAME walk-forward harness lineup_quality_conditioner{,_v2}.py
already use (build_frame/fit_term/oos_delta/_verdict pattern). Nothing here
is wired into any default path or flag; this module is imported by nothing,
and only imports FROM composition (never the reverse).

REPLICATED interactions wired (both same-sign +1, cleared the interaction_
factory's K=6 Bonferroni promotion bar, alpha_fwer=0.008333, on same-season
replication -- interaction_factory_ledger.jsonl rows 21+24):
  halfcourt_efg x late_clock_efg  batch1 p=0.000585 eff=+0.005212 n=15697;
    replication_2024_25 p=0.007258 eff=+0.00427 n=16627 (< 0.008333 bar).
  halfcourt_efg x zone_efg_rim    batch1 p=0.003401 eff=+0.004833 n=14970;
    replication_2024_25 p=0.000795 eff=+0.00501 n=15437 (< 0.008333 bar).
Both attrs are already MAIN EFFECTS inside the v1/v2 composite basket
(equal-weight linear sum); the interaction_factory found the CROSS TERM
(product of their z-scores) predictive of player-level eFG beyond either
main effect, but every composite consumer so far only ever summed main
effects -- the cross term has ZERO consumers anywhere in this codebase
until this file.

PREREGISTERED (K=2, Bonferroni alpha=0.025, same convention as v1/v2):
  H1 'interaction term adds to the v2 composite': composite_diff_interact
     coefficient/p on TEST season (2025-26), model = base + composite_diff
     (v2, held fixed) + composite_diff_interact.
  H1 replication on TRAIN season (2024-25<-2023-24 profiles), same-sign
     required for REPLICATED (mirrors v1/v2's own H1-replication leg; 2
     seasons = 2 independent walk-forward groups, the established bar this
     ledger already uses for CONFIRMED/REPLICATED composite rows).
  SIDE-BY-SIDE: OOS walk-forward wRMSE, v2 composite alone vs v2 composite +
  interaction term (fit TRAIN, predict TEST, both formulas) -- delta>0 means
  the interaction term earns its keep beyond the composite already has.

Descriptive/calibration only. edge_claimed hard-wired False. A NULL is a
SUCCESS. NETWORK: zero. NOT wired into any default, no flag flips.
CLI:  python -m domains.basketball_nba.composition.interaction_composite_candidate
Test: python -m pytest domains/basketball_nba/composition/test_interaction_composite_candidate.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from domains.basketball_nba.composition.lineup_quality_conditioner import (
    ALPHA, LEDGER_PATH, MIN_OVERLAP_S, PLAYER_PROFILES, PRIOR_WINDOW,
    REPO_ROOT, TEAM_PROFILES, TEST_TAG, TRAIN_TAG, _BASE, _lineup_comp,
    _verdict, fit_term, load_team_strength,
)
from domains.basketball_nba.composition.lineup_quality_conditioner_v2 import (
    BASKET as BASKET_V2, build_segments_exact,
)
from domains.basketball_nba.composition import lineup_quality_conditioner_v2 as _v2

REPORT_PATH = REPO_ROOT / "data" / "frontend" / "ops" / "nba_interaction_composite_candidate.json"
METHOD = "interaction_composite_candidate_v1"

# (attr_a, attr_b, sign): sign taken from the REPLICATED interaction_factory
# ledger direction (both batches same-sign positive) -- cited, not fit here.
INTERACTION_PAIRS: Tuple[Tuple[str, str, int], ...] = (
    ("halfcourt_efg", "late_clock_efg", 1),
    ("halfcourt_efg", "zone_efg_rim", 1),
)


def load_player_interaction_composite(prior_window: str, path: Path = PLAYER_PROFILES,
                                      pairs: Tuple[Tuple[str, str, int], ...] = INTERACTION_PAIRS
                                      ) -> Dict[int, float]:
    """Per-player interaction composite = sum over `pairs` of
    sign * z(attr_a) * z(attr_b), z-scored across THIS prior window's player
    population (same as-of convention as load_player_composite -- a window's
    own-season value never leaks because the caller filters to the PRIOR
    window before this function ever sees the frame). A pair missing either
    attribute contributes 0 for every player, not a crash."""
    p = pd.read_parquet(path)
    p = p[p["window"] == prior_window]
    if p.empty:
        return {}
    wide = p.pivot_table(index="entity_id", columns="attribute", values="raw_value", aggfunc="first")
    z: Dict[str, pd.Series] = {}
    for attr in {a for pair in pairs for a in pair[:2]}:
        if attr not in wide.columns:
            continue
        col = wide[attr]
        sd = col.std(ddof=0)
        if sd == 0 or pd.isna(sd):
            continue
        z[attr] = (col - col.mean()) / sd
    out = pd.Series(0.0, index=wide.index)
    for a, b, sign in pairs:
        if a in z and b in z:
            out = out.add(sign * z[a] * z[b], fill_value=0.0)
    out.index = out.index.astype("int64")  # same overflow guard v1 uses
    return out.to_dict()


def build_frame(season_tag: str, stints_df: Optional[pd.DataFrame] = None,
                player_path: Path = PLAYER_PROFILES, team_path: Path = TEAM_PROFILES,
                games_df: Optional[pd.DataFrame] = None) -> Optional[pd.DataFrame]:
    """v2's exact-attribution segment frame + v2's composite_diff + one extra
    column: composite_diff_interact (the 2 REPLICATED cross terms)."""
    prior = PRIOR_WINDOW.get(season_tag)
    if prior is None:
        return None
    if stints_df is None:
        stints_df = pd.read_parquet(REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / f"stints_{season_tag}.parquet")
    comp, coverage = _v2.load_player_composite(prior, player_path, basket=BASKET_V2)
    icomp = load_player_interaction_composite(prior, player_path)
    strength = load_team_strength(prior, team_path)
    seg = build_segments_exact(stints_df, season_tag, games_df)
    if seg.empty:
        return seg
    seg = seg[seg["overlap_s"] >= MIN_OVERLAP_S].copy()
    seg["composite_diff"] = (seg["lineup_key_a"].map(lambda k: _lineup_comp(k, comp))
                             - seg["lineup_key_b"].map(lambda k: _lineup_comp(k, comp)))
    seg["composite_diff_interact"] = (seg["lineup_key_a"].map(lambda k: _lineup_comp(k, icomp))
                                      - seg["lineup_key_b"].map(lambda k: _lineup_comp(k, icomp)))
    seg["strength_diff"] = seg["team_id_a"].map(strength) - seg["team_id_b"].map(strength)
    seg["y"] = (seg["pts_a"] - seg["pts_b"]) / seg["overlap_s"] * 2880.0
    seg.attrs["coverage"] = coverage
    return seg


_MODEL_COLS = ["y", "score_margin_start", "time_remaining", "strength_diff",
              "composite_diff", "composite_diff_interact", "overlap_s", "game_id"]
_BASE_PLUS_COMPOSITE = _BASE + " + composite_diff"
_FULL = _BASE_PLUS_COMPOSITE + " + composite_diff_interact"


def oos_delta_vs_composite(train: pd.DataFrame, test: pd.DataFrame) -> Dict[str, Any]:
    """SIDE-BY-SIDE: v2 composite ALONE vs v2 composite + interaction term.
    delta>0 => adding the interaction term improves OOS margin prediction
    beyond the current (v2) composite alone."""
    tr = train.dropna(subset=_MODEL_COLS)
    te = test.dropna(subset=_MODEL_COLS)
    if len(tr) == 0 or len(te) == 0:
        return {"rmse_composite": None, "rmse_composite_plus_interact": None,
                "delta_rmse": None, "n_test": len(te)}

    def _wrmse(formula: str) -> float:
        res = smf.wls(formula, data=tr, weights=tr["overlap_s"]).fit()
        pred = res.predict(te)
        w = te["overlap_s"]
        return float(np.sqrt((w * (te["y"] - pred) ** 2).sum() / w.sum()))

    rc, rf = _wrmse(_BASE_PLUS_COMPOSITE), _wrmse(_FULL)
    return {"rmse_composite": rc, "rmse_composite_plus_interact": rf,
            "delta_rmse": rc - rf, "n_test": len(te)}


def run() -> Dict[str, Any]:
    train, test = build_frame(TRAIN_TAG), build_frame(TEST_TAG)
    cov_test = float(test.attrs.get("coverage", 0.0)) if test is not None else 0.0

    h1 = fit_term(test, _FULL, "composite_diff_interact")
    v1 = _verdict(h1["p"], h1["n"])
    side = oos_delta_vs_composite(train, test)
    h1r = fit_term(train, _FULL, "composite_diff_interact")
    sign_ref = None if h1["effect"] is None else (1 if h1["effect"] > 0 else -1)
    v1r = _verdict(h1r["p"], h1r["n"], sign_ref=sign_ref, effect=h1r["effect"])

    rows: List[Dict[str, Any]] = []
    for name, fit, verd in [
        ("H1_composite_plus_replicated_interactions", h1, v1),
        ("H1_composite_plus_replicated_interactions_replication_2024_25", h1r, v1r),
    ]:
        rows.append({
            "hypothesis": name, "sport": "nba", "atomic_unit": "lineup_segment_asof_exact",
            "method": METHOD, "season": f"walkforward_train_{TRAIN_TAG}_test_{TEST_TAG}",
            "n": fit["n"], "effect": fit["effect"], "p": fit["p"], "alpha_fwer": ALPHA,
            "term": "composite_diff_interact", "verdict": verd,
            "note": "candidate only, side-by-side vs v2 composite, not wired to any default",
            "edge_claimed": False,
        })

    report = {
        "method": METHOD, "generated_by": "domains/basketball_nba/composition/interaction_composite_candidate.py",
        "atomic_unit": "lineup_segment_asof_exact", "alpha_fwer_K2": ALPHA,
        "wired_interactions": [{"attr_a": a, "attr_b": b, "sign": s} for a, b, s in INTERACTION_PAIRS],
        "source_ledger": "data/cache/intel_claims/interaction_factory_ledger.jsonl",
        "walkforward": {"train_season": TRAIN_TAG, "train_prior_window": PRIOR_WINDOW[TRAIN_TAG],
                        "test_season": TEST_TAG, "test_prior_window": PRIOR_WINDOW[TEST_TAG],
                        "excluded_season": "2023_24 (no season_2022_23 prior profiles)"},
        "coverage_mean_test": cov_test,
        "H1": {"verdict": v1, **h1, "replication_2024_25": {"verdict": v1r, **h1r}},
        "side_by_side_oos": side,
        "edge_claimed": False,
        "candidate_only": True, "wired_to_default": False,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="ascii")
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return report


def main() -> int:
    rep = run()
    print(f"K=2 alpha_bonferroni={ALPHA:.4f}  interactions={len(INTERACTION_PAIRS)}  coverage_test={rep['coverage_mean_test']:.3f}")
    h1 = rep["H1"]
    print(f"  H1 [{h1['verdict']:>16}] composite_diff_interact: n={h1['n']} effect={h1['effect']} p={h1['p']}")
    print(f"     replication_2024_25 [{h1['replication_2024_25']['verdict']}]")
    side = rep["side_by_side_oos"]
    print(f"  side-by-side OOS wRMSE composite={side['rmse_composite']} "
          f"composite+interact={side['rmse_composite_plus_interact']} delta={side['delta_rmse']} (>0 helps)")
    print(f"  report -> {REPORT_PATH}  candidate_only={rep['candidate_only']} wired_to_default={rep['wired_to_default']}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
