"""Additive charged-tier evidence plumbing kept outside the 300-line tiers module."""
from __future__ import annotations

from typing import Any, Callable, Optional, Sequence

import numpy as np

from scripts.platformkit.combo.fwer_budget import min_corpora_eff
from scripts.platformkit.eval_gate import scoring
from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.eval_gate.family_bars import charged_bars, families_spec_sha, frozen_family
from scripts.platformkit.eval_gate.pbo import cscv_pbo


def _archive(predict_fn: Callable, ids: Sequence[str], by_id: dict, key: str,
             clusters: Sequence[str], loss_model: np.ndarray, loss_close: np.ndarray,
             dm: Any, dm_test: Callable, n_eff: Callable) -> dict:
    """Q9 differential plus a home-team robustness view beside the primary clusters."""
    states = [by_id[event] for event in ids]
    home_ids = [str(state.get("home") or event) for state, event in zip(states, ids)]
    losses = loss_model - loss_close
    home_dm = dm_test(losses.tolist(), home_ids)
    archive = dict(getattr(predict_fn, "archive", dict)())
    archive.update(cluster_key=key, differential=[
        (event, state["state_ts"], cluster, float(model_loss), float(close_loss))
        for event, state, cluster, model_loss, close_loss in zip(
            ids, states, clusters, loss_model, loss_close)])
    archive["cluster_metrics"] = {
        key: {"cluster_key": key, "n_eff": float(n_eff(losses.tolist(), clusters)),
              "dm": float(dm.dm_stat), "n_clusters": len(set(clusters))},
        "home": {"cluster_key": "home", "n_eff": float(n_eff(losses.tolist(), home_ids)),
                 "dm": float(home_dm.dm_stat), "n_clusters": len(set(home_ids))},
    }
    return archive


def run_charged(tier: str, states: Sequence[dict], predict_fn: Callable, sport: str,
                ledger_path: Any, family: str, screened_n: Optional[int], n_corpora: int,
                rule: Any, digest: str, common: dict, results_db: Any, trial_prereg_sha256: Optional[str],
                *, result_factory: Callable, charge_tier: Callable, pooled_oof: Callable,
                cluster_ids: Callable, dm_test: Callable, n_eff: Callable) -> Any:
    """Run the existing charged protocol and attach only additive trial evidence."""
    if screened_n is None:
        raise ValueError("%s must print screened_n beside deflated_p (SF-2)" % tier)
    if frozen_family(family) is None:
        from scripts.platformkit.foundry.tiers import _UNSCORED

        return result_factory(verdict="NOT_IN_FROZEN_FAMILIES",
                              families_spec_sha256=families_spec_sha(), **_UNSCORED, **common)
    stamps = sorted(str(state["state_ts"])[:10] for state in states)
    charge = charge_tier(tier, ledger_path=ledger_path, family=family, hypothesis_hash=digest,
                         prereg_sha256=rule.prereg_sha256, trial_prereg_sha256=trial_prereg_sha256,
                         sport=sport, start=stamps[0], end=stamps[-1])
    k_global, k_family = int(charge["k_cumulative"]), charge.get("k_family")
    ids, model, close, y = pooled_oof(cpcv_evaluate(list(states), predict_fn))
    by_id = {str(state.get("event_id", state["game_id"])): state for state in states}
    key, clusters = cluster_ids([by_id[event] for event in ids], sport)
    loss_model, loss_close = (model - y) ** 2, (close - y) ** 2
    losses = loss_model - loss_close
    dm = dm_test(losses.tolist(), clusters)
    pbo = cscv_pbo(np.column_stack([model, close]), y, s_blocks=16).pbo
    brier_model, brier_close = scoring.brier(model, y), scoring.brier(close, y)
    prior = [] if results_db is None else list(results_db.family_p_values(family))
    bars = charged_bars(dm.p_value, k_global, family, prior, rule.alpha, common["artifact_path"])
    if not bars["global_pass"]:
        verdict = "MATCH"
    elif brier_model > brier_close:
        verdict = "BEHIND"
    elif tier == "T3" and n_corpora < min_corpora_eff(n_corpora, k_global):
        verdict = "SINGLE-WINDOW"
    elif not bars["family_pass"]:
        verdict = "MATCH"
    else:
        verdict = "AHEAD"
    archive = _archive(predict_fn, ids, by_id, key, clusters, loss_model, loss_close, dm, dm_test,
                       n_eff)
    return result_factory(n_eff=n_eff(losses.tolist(), clusters), brier_model=brier_model,
                          brier_close=brier_close, dm=dm.dm_stat, raw_p=dm.p_value, k_family=k_family,
                          k_global=k_global, deflated_p=bars["deflated_p"], pbo=pbo, verdict=verdict,
                          family_q=bars["q"], bh_passed=bars["family_pass"],
                          global_passed=bars["global_pass"], dual_verdict=bars["verdict"],
                          families_spec_sha256=bars["families_spec_sha"], archive=archive,
                          **{**common, "cluster_key": key, "n": len(ids)})
