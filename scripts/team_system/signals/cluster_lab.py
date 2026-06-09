"""CLUSTER LAB -- the reusable COMPOSITION validator (MASTER_SYSTEM_BUILD section 4B, generalized).

The user's principle, made a first-class loop capability: a signal that REJECTS alone can carry real signal
in a CLUSTER (a domain model). This validates a cluster as ONE cross-season unit and registers the survivor
as a model -- so the agentic loop can keep discovering compositional models automatically instead of by hand.

For a (corpus, base, domain, scope, signal-list):
  - measure each signal's OOS lift ALONE (the marginal gate) and the CLUSTER's lift, per season (leak-free,
    5-fold-by-game RMSE on the target);
  - VERDICT REPLICATES iff the cluster lifts > noise floor in >= 2 independent seasons (the cross-season bar);
  - the cluster is ONE FDR-counted test (model_id = hash of its signal set) -- you can't free-roll combos;
  - on REPLICATES, register the model in model_registry (engine_node = where it plugs into an engine).

  from signals.cluster_lab import validate_cluster
  validate_cluster("data/cache/team_system/legacy_possessions.parquet",
                   base=["period","grem"], signals=["poss_dur","after_to","dead_ball","abs_margin","had_oreb"],
                   domain="possession_origin", scope="possession", engine_node="origin_state_ppp")
"""
from __future__ import annotations
import math
import os
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from registry.ids import content_hash, model_id  # noqa: E402
from registry.store import Registry  # noqa: E402

NOISE_FLOOR = 0.002


def _oos(S, feats, target, seed=0):
    g = np.array(sorted(S.gid.unique())); np.random.default_rng(seed).shuffle(g)
    e = []
    for fold in np.array_split(g, 5):
        te = S[S.gid.isin(fold)]; tr = S[~S.gid.isin(fold)]
        m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05, max_iter=250,
                                          min_samples_leaf=80, random_state=seed)
        m.fit(tr[feats], tr[target])
        e.append(math.sqrt(np.mean((m.predict(te[feats]) - te[target].values) ** 2)))
    return float(np.mean(e))


def validate_cluster(corpus_path, base, signals, domain, scope, engine_node="",
                     target="pts", seasons=("2022-23", "2023-24"), min_games=50,
                     register=True, method="cluster_hgb_oos") -> dict:
    D = pd.read_parquet(corpus_path)
    if target == "pts" and "pts" in D.columns:
        n_before = len(D)
        D = D[D.pts <= 4]
        n_after = len(D)
        if n_before > 0 and n_after < n_before:
            print(f"  [cluster_lab] NOTE: pts>4 filter removed {n_before - n_after}/{n_before} rows "
                  f"({100*(n_before-n_after)/n_before:.1f}%). Verdict reflects possessions with pts<=4 only.")
    feats_all = base + signals
    per_season, singles = {}, {s: [] for s in signals}
    cluster_rels = []
    # PSEUDO-REPLICATION GUARD (default ON): a corpus WITHOUT a `season` column (or with only one
    # distinct season among the requested `seasons`) makes every loop iteration score the SAME rows,
    # producing identical `cluster_rel` values that fake "REPLICATES N/N" from ONE dataset evaluated N
    # times -- violating the documented "REPLICATES needs >=2 INDEPENDENT seasons" invariant. We require a
    # real `season` column with >=2 of the requested seasons actually present before any REPLICATES verdict.
    # Set CV_CLUSTER_ALLOW_PSEUDO=1 to restore the legacy (unsafe) behavior.
    _allow_pseudo = os.environ.get("CV_CLUSTER_ALLOW_PSEUDO") == "1"
    _has_season = "season" in D.columns
    _seasons_present = set(D["season"].unique()) & set(seasons) if _has_season else set()
    _pseudo_blocked = (not _allow_pseudo) and (not _has_season or len(_seasons_present) < 2)
    for season in seasons:
        S = D[D.season == season] if "season" in D.columns else D
        if "gid" not in S.columns or S.gid.nunique() < min_games:
            per_season[season] = dict(verdict="skip-fewgames"); continue
        b = _oos(S, base, target)
        for s in signals:
            singles[s].append((_oos(S, base + [s], target) - b) / b)
        rel = (_oos(S, feats_all, target) - b) / b
        cluster_rels.append(rel)
        per_season[season] = dict(base_rmse=round(b, 4), cluster_rel=round(rel, 4))
    n_repl = sum(1 for r in cluster_rels if r < -NOISE_FLOOR)
    if _pseudo_blocked:
        # not enough INDEPENDENT seasons -> cannot certify cross-season replication
        verdict = "insufficient-seasons"
    else:
        verdict = "REPLICATES" if n_repl >= 2 else ("single-season" if n_repl == 1 else "does-NOT-replicate")
    # which signals are dead-alone but lift in-cluster (the composition value)
    dead_alone = [s for s in signals if all(r > -NOISE_FLOOR for r in singles[s]) and singles[s]]
    best_single = min((min(v) for v in singles.values() if v), default=0.0)
    cluster_best = min(cluster_rels) if cluster_rels else 0.0
    out = dict(domain=domain, scope=scope, signals=signals, verdict=verdict, n_replicate=n_repl,
               cluster_rels=[round(r, 4) for r in cluster_rels], best_single=round(best_single, 4),
               cluster_beats_best_single=bool(cluster_best < best_single),
               dead_alone_but_lift_in_cluster=dead_alone, per_season=per_season,
               independent_seasons=sorted(_seasons_present), pseudo_replication_blocked=bool(_pseudo_blocked))
    if register and verdict == "REPLICATES":
        sigset = sorted(signals)
        mid = model_id(dict(domain_tag=domain, entity_scope=scope, signal_id_set=sigset, method=method))
        Registry("model_registry").register(dict(
            model_id=mid, domain_tag=domain, entity_scope=scope,
            signal_id_set_hash=content_hash(dict(s=sigset), ("s",), "set"), method=method,
            input_hash=None, oos_score=round(cluster_best, 4),
            xseason_verdict=f"REPLICATES {n_repl}/{len(seasons)} ({out['cluster_rels']}); dead-alone-in-cluster={dead_alone}",
            engine_node=engine_node, status="validated", artifact_path=None, created_utc=0))
        out["registered_model_id"] = mid
    return out


def _print(r):
    print(f"=== CLUSTER LAB: {r['domain']}/{r['scope']}  signals={r['signals']} ===")
    for s, v in r["per_season"].items():
        print(f"  {s}: cluster_rel {v.get('cluster_rel')}")
    print(f"  verdict: {r['verdict']} ({r['n_replicate']} seasons); cluster {r['cluster_rels']} "
          f"beats best single ({r['best_single']}): {r['cluster_beats_best_single']}")
    print(f"  dead-alone-but-lift-in-cluster: {r['dead_alone_but_lift_in_cluster']}")
    if r.get("registered_model_id"):
        print(f"  REGISTERED model {r['registered_model_id']} -> {r['domain']} (engine_node)")


if __name__ == "__main__":
    r = validate_cluster("data/cache/team_system/legacy_possessions.parquet",
                         base=["period", "grem"],
                         signals=["poss_dur", "after_to", "dead_ball", "abs_margin", "had_oreb"],
                         domain="possession_origin", scope="possession", engine_node="origin_state_ppp",
                         register=False)
    _print(r)
