"""MIGRATE the legacy registries into the new content-hashed, sharded registries (B3).

Sources:
  - data/registry/signal_registry.parquet      (86 human-named catalog signals; status folded/deferred)
  - data/registry/signal_lab_registry.parquet   (21 signal_lab-tested signals with verdicts; 5 validated
                                                  incl. the 2 hand-written CAVEATs, 16 rejected)
  - scripts/team_system/engines/engine_*.py + possession_mc + clock_trajectory  (the 7 engines)

Every migrated row gets a content-hash id (registry.ids), so re-running is idempotent (dedup is structural).
The legacy human name is preserved in `legacy_name` for traceability (it is NOT part of the id). The 2 CAVEAT
signals are migrated as status='caveat' (engine-redundant / sign-confound) so the foundry's TRUST GATE (B4)
can later reproduce their auto-rejection. bet_wireable=False for every migrated signal -- a signal earns
wireability only by clearing GATE-X cross-season (section 4B), never by migration.

  python scripts/team_system/registry/migrate.py
"""
from __future__ import annotations
import glob
import os
import sys
import time

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from registry.ids import signal_id, engine_id, family_key  # noqa: E402
from registry.store import Registry, REGISTRY_DIR  # noqa: E402

CAVEATS = {"opp_position_defense_reb", "oreb_matchup"}     # the 2 hand-written CAVEAT auto-rejections
_NOW = int(time.time())

# legacy consumer -> honesty class (all leak-prone / scouting until they clear GATE-X cross-season)
_HONESTY = {"scouting": "SCOUTING", "corr-model": "SCOUTING", "point-model": "SCOUTING",
            "ingame": "SCOUTING", "sizing": "SCOUTING"}


def _grain_to_scope(grain: str) -> str:
    g = (grain or "").lower()
    if g.startswith("poss"):
        return "possession"
    if "player" in g:
        return "player"
    if "team" in g:
        return "team"
    if "lineup" in g:
        return "lineup"
    return "player"


def migrate_catalog(reg: Registry) -> int:
    p = os.path.join(REGISTRY_DIR, "signal_registry.parquet")
    if not os.path.exists(p):
        return 0
    df = pd.read_parquet(p)
    rows = []
    for r in df.to_dict("records"):
        defn = dict(grain=str(r.get("granularity") or "s"),
                    entity_scope=str(r.get("entity") or "player"),
                    domain_tags=[str(r.get("domain") or "misc")],
                    source=str(r.get("source") or "catalog"),
                    formula_ast=str(r.get("formula") or r.get("signal_id")),
                    transform_chain=[str(r.get("granularity") or "s")],
                    asof_fn=str(r.get("leak_rule") or "shift1"),
                    asof_fn_name=str(r.get("leak_rule") or "shift1"),
                    causal_sign=0)
        sid = signal_id(defn)
        row = dict(defn, signal_id=sid,
                   honesty_class=_HONESTY.get(str(r.get("consumer")), "SCOUTING"),
                   bet_wireable=False, status="proposed",
                   gateA_rel=None, gateA_fdr_q=None, gateX_verdict="N/A-not-tested",
                   judge_sign_ok=None, judge_engine_ortho=None, family_key=family_key(defn),
                   n=None, coverage_pct=r.get("coverage_pct"), created_utc=_NOW,
                   builder="migrate_catalog", artifact_path=None,
                   legacy_name=str(r.get("signal_id")), note=f"ev_tier={r.get('ev_tier')};consumer={r.get('consumer')}")
        rows.append(row)
    return reg.register_many(rows)["registered"]


def migrate_lab(reg: Registry) -> int:
    p = os.path.join(REGISTRY_DIR, "signal_lab_registry.parquet")
    if not os.path.exists(p):
        return 0
    df = pd.read_parquet(p)
    rows = []
    for r in df.to_dict("records"):
        name = str(r.get("name"))
        grain = str(r.get("grain") or "")
        defn = dict(grain="possession" if grain.startswith("poss") else grain or "player-game",
                    entity_scope=_grain_to_scope(grain),
                    domain_tags=[str(r.get("target") or "lab")],
                    source="signal_lab",
                    formula_ast=name,
                    transform_chain=["leak_free_5fold"],
                    asof_fn="leak_free_5fold_by_game",
                    asof_fn_name="leak_free_5fold_by_game",
                    causal_sign=0)
        sid = signal_id(defn)
        verdict = str(r.get("verdict"))
        status = ("caveat" if name in CAVEATS else
                  "validated" if verdict == "VALIDATED" else "rejected")
        # possession grain has a cross-season substrate; others are SCOUTING per substrate-honest policy
        honesty = "PROVEN-capable" if defn["grain"] == "possession" else "SCOUTING"
        row = dict(defn, signal_id=sid, honesty_class=honesty, bet_wireable=False, status=status,
                   gateA_rel=r.get("oos_rel"), gateA_fdr_q=None,
                   gateX_verdict="REPLICATES" if name == "shot_clock_leverage" else "N/A-not-run",
                   judge_sign_ok=(False if name == "opp_position_defense_reb" else None),
                   judge_engine_ortho=None, family_key=family_key(defn),
                   n=r.get("n"), coverage_pct=None, created_utc=_NOW, builder="migrate_lab",
                   artifact_path=None, legacy_name=name,
                   note=f"verdict={verdict}; {str(r.get('reason'))[:80]}")
        rows.append(row)
    return reg.register_many(rows)["registered"]


def migrate_engines(ereg: Registry) -> int:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    names = [os.path.basename(fp)[len("engine_"):-3]
             for fp in sorted(glob.glob(os.path.join(here, "engines", "engine_*.py")))]
    names += ["possession_mc", "clock_trajectory"]
    w = round(1.0 / len(names), 4)
    rows = []
    for nm in names:
        defn = dict(name=nm, consumes_models=[], method=nm)
        rows.append(dict(engine_id=engine_id(defn), name=nm, consumes_models=[], owns_nodes=[],
                         method=nm, reliability_weight=w, engine_corr=None, last_backtest_utc=None))
    return ereg.register_many(rows)["registered"]


def main():
    sig = Registry("signal_registry")
    eng = Registry("engine_registry")
    Registry("model_registry")          # create (schema-valid, empty until B7 domain router)
    Registry("calibration_registry")    # create (empty until B9 continual-calibration)
    nc = migrate_catalog(sig)
    nl = migrate_lab(sig)
    ne = migrate_engines(eng)
    print(f"migrated: {nc} catalog + {nl} lab signals -> signal_registry ({len(sig)} unique after hash-dedup); "
          f"{ne} engines -> engine_registry")
    from registry.dedup import dedup_pass
    dd = dedup_pass("signal_registry")
    print(f"dedup_pass: {dd['n']} rows / {dd['buckets']} buckets / {len(dd['unmerged_pairs'])} unmerged pairs "
          f"-> {'CLEAN' if not dd['unmerged_pairs'] else 'DUPLICATES'}")
    # status breakdown
    df = sig.all()
    print("signal status:", df.status.value_counts().to_dict())
    print("CAVEATs present:", sorted(df[df.status == "caveat"].legacy_name.tolist()))


if __name__ == "__main__":
    main()
