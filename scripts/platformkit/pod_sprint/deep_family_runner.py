"""scripts.platformkit.pod_sprint.deep_family_runner -- family-by-family gate for the
DEEP_FEATURES_PREREG (M/S/V/X). Each family tested ALONE (added to the plain 15-feature
gbm_nba_ml baseline) through the SAME walk-forward folds/WIDE_GRID/paired-bootstrap gate
gbm_nba_enriched.py uses; V3 is tested as an alternate-Elo SWAP, not an addition (see
deep_families.build_features_capped_mov). Then greedy forward selection composes
CI-surviving ADDITIVE families only (V3's swap is never combined with them -- composing a
column-swap with column-additions is a different feature-engineering step the prereg
doesn't ask for). No family definition is edited after its first scored run here.

CLI: python -m scripts.platformkit.pod_sprint.deep_family_runner
"""
from __future__ import annotations

import json
import sys
from typing import Dict, List, Tuple

import numpy as np

from scripts.platformkit.models import gbm_nba_ml as g  # noqa: E402
from scripts.platformkit.pod_sprint import deep_families as df  # noqa: E402
from scripts.platformkit.pod_sprint.gbm_sweep import WIDE_GRID  # noqa: E402

_ARTIFACT = g._REPO / "data" / "domains" / "nba" / "deep_families_benchmark.json"


def _select(feat, pool_mask, features: List[str]) -> Tuple[dict, str]:
    saved_f, saved_g = g._FEATURES, g._GRID
    g._FEATURES, g._GRID = features, WIDE_GRID
    try:
        return g._select_hyperparams(feat, pool_mask)
    finally:
        g._FEATURES, g._GRID = saved_f, saved_g


def _run_folds(feat, m, folds, features: List[str]) -> Tuple[np.ndarray, dict, str]:
    """Select hyperparams once on fold0's train pool (same pattern as gbm_nba_enriched),
    then fit/predict across all folds -- returns the concatenated OOS predictions."""
    params, note = _select(feat, folds[0][0], features)
    p_all = []
    for train_mask, lo, hi in folds:
        tr, te = feat.loc[train_mask], m.iloc[lo:hi]
        model, _ = g._fit(tr[features], tr["home_win"], params)
        p_all.extend(np.clip(model.predict_proba(te[features])[:, 1], 1e-6, 1 - 1e-6))
    return np.array(p_all), params, note


def _verdict(delta: np.ndarray, label: str) -> Tuple[str, List[float]]:
    ci = [round(v, 4) for v in g._bootstrap_ci(delta)]
    tag = "SURVIVES" if ci[1] < 0 else "NULL"
    v = f"{label}: {tag} (delta {round(float(delta.mean()), 4)} CI{ci})"
    return v, ci


def run() -> Dict:
    box = g.load_box(g._NBA)
    deep_feat = df.build_features_deep(box)      # base 15 + all additive family columns
    capped_feat = df.build_features_capped_mov(box)  # V3's alternate Elo (swap, not additive)
    # join_market carries a feat's OWN column values through the merge -- m must be built
    # from deep_feat (not a separately-built plain frame) or the family columns vanish from
    # the test slices `te` pulled out of `m` below.
    m = g.join_market(deep_feat, g._NBA)
    m_capped = g.join_market(capped_feat, g._NBA)
    n = len(m)
    if n < 120 or len(m_capped) != n:
        return {"status": "data_limited", "n_overlap": n, "edge_claimed": False}
    # both joins are deterministic inner-merges of the SAME box against the SAME odds
    # parquet, sorted identically -- row-for-row alignment is required for the paired
    # bootstrap deltas below to compare the same held-out games.
    assert (m[["date", "home_abbr", "away_abbr"]].to_numpy()
            == m_capped[["date", "home_abbr", "away_abbr"]].to_numpy()).all(), \
        "plain and capped-MOV joins misaligned -- paired delta would compare different games"

    folds = g.make_folds(deep_feat, m, k=4)
    p_plain, plain_params, plain_note = _run_folds(deep_feat, m, folds, g._FEATURES)
    y_all, p_mkt_all = [], []
    for _, lo, hi in folds:
        te = m.iloc[lo:hi]
        y_all.extend(te["home_win"].to_numpy(float)); p_mkt_all.extend(te["p_market"].to_numpy(float))
    y_all, p_mkt_all = np.array(y_all), np.array(p_mkt_all)
    brier_plain = float(np.mean((p_plain - y_all) ** 2))
    brier_close = float(np.mean((p_mkt_all - y_all) ** 2))

    families: Dict[str, dict] = {}
    survivors: Dict[str, List[str]] = {}
    for fam_id, cols in df.FAMILY_COLUMNS.items():
        p_fam, params, note = _run_folds(deep_feat, m, folds, g._FEATURES + cols)
        delta = (p_fam - y_all) ** 2 - (p_plain - y_all) ** 2
        verdict, ci = _verdict(delta, fam_id)
        families[fam_id] = {
            "type": "additive", "columns": cols,
            "brier": round(float(np.mean((p_fam - y_all) ** 2)), 4),
            "delta_vs_plain_mean": round(float(delta.mean()), 4), "delta_vs_plain_95ci": ci,
            "verdict": verdict, "hyperparams": params, "selection_note": note,
        }
        if ci[1] < 0:
            survivors[fam_id] = cols

    p_v3, v3_params, v3_note = _run_folds(capped_feat, m_capped, folds, g._FEATURES)
    delta_v3 = (p_v3 - y_all) ** 2 - (p_plain - y_all) ** 2
    verdict_v3, ci_v3 = _verdict(delta_v3, "V3_garbage_mov")
    families["V3_garbage_mov"] = {
        "type": "swap (alternate Elo, MOV capped at 20)",
        "brier": round(float(np.mean((p_v3 - y_all) ** 2)), 4),
        "delta_vs_plain_mean": round(float(delta_v3.mean()), 4), "delta_vs_plain_95ci": ci_v3,
        "verdict": verdict_v3, "hyperparams": v3_params, "selection_note": v3_note,
    }

    # greedy forward selection over CI-surviving ADDITIVE families only
    selection_log: List[dict] = []
    current_cols: List[str] = []
    current_p = p_plain
    remaining = dict(survivors)
    while remaining:
        best_fam, best_mean, best_p, best_ci = None, 0.0, None, None
        for fam_id, cols in remaining.items():
            p_trial, _, _ = _run_folds(deep_feat, m, folds, g._FEATURES + current_cols + cols)
            delta = (p_trial - y_all) ** 2 - (current_p - y_all) ** 2
            ci = g._bootstrap_ci(delta)
            if ci[1] < 0 and float(delta.mean()) < best_mean:
                best_fam, best_mean, best_p, best_ci = fam_id, float(delta.mean()), p_trial, ci
        if best_fam is None:
            break
        selection_log.append({"added": best_fam, "delta_mean": round(best_mean, 4),
                               "ci": [round(v, 4) for v in best_ci]})
        current_cols += remaining.pop(best_fam)
        current_p = best_p

    if selection_log:
        final_verdict = (f"COMPOSED: {'+'.join(s['added'] for s in selection_log)} beats plain "
                          f"(final Brier {round(float(np.mean((current_p - y_all) ** 2)), 4)})")
    else:
        final_verdict = ("COMPOSED: NO SURVIVORS -- every family NULL vs plain features; "
                          "expected under market efficiency (team-grain aggregates largely "
                          "saturated per the enriched-GBM REJECT / live_edge memory)")

    return {
        "status": "ok", "edge_claimed": False, "n_overlap": n,
        "brier_plain": round(brier_plain, 4), "brier_close": round(brier_close, 4),
        "plain_hyperparams": plain_params, "plain_selection_note": plain_note,
        "families": families, "not_built": df.NOT_BUILT,
        "forward_selection": selection_log, "final_verdict": final_verdict,
        "honest_note": (
            "Each family tested ALONE (added to the plain 15-feature gbm_nba_ml baseline) "
            "through identical walk-forward folds + WIDE_GRID + paired bootstrap CI vs a "
            "PAIRED plain-feature model trained in-process on the same folds. V3 is a swap "
            "(alternate MOV-capped Elo), never combined with the additive families in forward "
            "selection. No $ edge claimed; nulls are honest REJECTs, not failures."),
    }


def _main() -> int:
    rep = run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: n_overlap={rep.get('n_overlap')}")
        return 0
    _ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    _ARTIFACT.write_text(json.dumps(rep, indent=2))
    print(f"=== DEEP FEATURES family gate (n={rep['n_overlap']}) ===")
    print(f"  Brier: close={rep['brier_close']} plain={rep['brier_plain']}")
    for r in rep["families"].values():
        print(f"  {r['verdict']}")
    for fam, why in rep["not_built"].items():
        print(f"  {fam}: NOT_BUILT -- {why}")
    print(f"  {rep['final_verdict']}")
    print(f"artifact -> {_ARTIFACT}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
