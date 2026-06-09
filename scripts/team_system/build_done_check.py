"""BUILD-DONE CHECKLIST (MASTER_SYSTEM_BUILD section 7.1) -- the machine-checkable gate that decides
when PHASE=BUILD may flip to PHASE=IMPROVE. Prints `BUILD-DONE: PASS` (exit 0) only when EVERY box
B1..B12 passes; otherwise lists the failing items so the loop knows exactly what scaffold is left.

Cheap structural checks run by default; heavy checks (the board, cross_season) run with --full or read a
cached marker written by the subsystem that owns them (data/registry/build_checks/<id>.json). A subsystem
writes its marker only after it has validated itself -- so the gate trusts markers but they are earned.

  python scripts/team_system/build_done_check.py            # fast structural pass
  python scripts/team_system/build_done_check.py --full     # also runs the board + cross_season
"""
from __future__ import annotations
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
MARKERS = os.path.join(ROOT, "data", "registry", "build_checks")
PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


def _marker(name: str):
    p = os.path.join(MARKERS, f"{name}.json")
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return None
    return None


def write_marker(name: str, obj: dict) -> None:
    os.makedirs(MARKERS, exist_ok=True)
    tmp = os.path.join(MARKERS, f"{name}.json.tmp")
    json.dump(obj, open(tmp, "w", encoding="utf-8"), indent=2, default=str)
    os.replace(tmp, os.path.join(MARKERS, f"{name}.json"))


# ---- individual checks: each returns (status, detail) ----
def b1_board(full: bool):
    if not full:
        m = _marker("B1_board")
        if m and m.get("passed") == 5:
            return PASS, f"cached 5/5 ({m.get('asof','?')})"
        return SKIP, "run --full (or no cached board marker)"
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/test_sim_engine.py", "-q"],
                       cwd=ROOT, capture_output=True, text=True, timeout=600)
    out = r.stdout + r.stderr
    passed = "5 passed" in out
    if passed:
        write_marker("B1_board", dict(passed=5))
    return (PASS if passed else FAIL), out.strip().splitlines()[-1] if out.strip() else "no output"


def b2_engines(full: bool):
    eng = sorted(glob.glob(os.path.join(HERE, "engines", "engine_*.py")))
    sims_ok = True
    sys.path.insert(0, os.path.join(ROOT, "src"))
    for mod in ("sim.basketball_sim", "sim.fast_sim", "sim.game_clock_sim"):
        try:
            __import__(mod)
        except Exception:
            sims_ok = False
    have = len(eng) + (2 if sims_ok else 0)
    loadable = 0
    import importlib.util
    for fp in eng:
        try:
            spec = importlib.util.spec_from_file_location(os.path.basename(fp)[:-3], fp)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            if hasattr(m, "predict"):
                loadable += 1
        except Exception:
            pass
    ok = have >= 7 and loadable == len(eng) and sims_ok
    return (PASS if ok else FAIL), f"{loadable}/{len(eng)} analytic engines load + 2 sim engines={sims_ok} -> {have} total"


def b3_registries(full: bool):
    """All 4 registries present + schema-valid; every row content-hashed; dedup clean. signal+engine must
    be POPULATED here; model_registry is B7's deliverable and calibration_registry is B9's (created now)."""
    try:
        from registry.store import Registry
        from registry.dedup import dedup_pass
    except Exception as e:
        return FAIL, f"registry import failed: {str(e)[:80]}"
    present, counts = [], {}
    for name in ("signal_registry", "model_registry", "engine_registry", "calibration_registry"):
        d = os.path.join(ROOT, "data", "registry", name)
        if os.path.isdir(d):                 # Registry(name).__init__ created the dir (schema-valid)
            present.append(name)
            counts[name] = len(Registry(name))
    sig = Registry("signal_registry")
    ids = sig.all()[sig.id_col] if len(sig) else []
    hashed = len(sig) > 0 and all(isinstance(i, str) and i.startswith("sig_") for i in ids) and \
        len(set(ids)) == len(ids)
    dd = dedup_pass("signal_registry")
    clean = len(dd["unmerged_pairs"]) == 0
    ok = (len(present) == 4 and counts.get("signal_registry", 0) > 0 and
          counts.get("engine_registry", 0) > 0 and hashed and clean)
    return (PASS if ok else FAIL), (f"4/4 present; signals={counts.get('signal_registry')} "
            f"(hashed={hashed}), engines={counts.get('engine_registry')}, "
            f"models={counts.get('model_registry')}, calib={counts.get('calibration_registry')}; "
            f"dedup unmerged={len(dd['unmerged_pairs'])}")


def b4_trust_gate(full: bool):
    m = _marker("B4_trust_gate")
    if m and m.get("reproduced_both"):
        return PASS, f"foundry reproduced both CAVEAT auto-rejections ({m.get('detail','')})"
    return FAIL, "foundry TRUST GATE not yet passed (must auto-reject opp_position_defense_reb + oreb_matchup)"


def b5_fdr(full: bool):
    m = _marker("B5_fdr")
    if m and m.get("planted_null_ok"):
        return PASS, f"planted-null FDR test passed ({m.get('detail','')})"
    return FAIL, "FDR (BH/alpha-investing) + planted-null test not yet wired"


def b6_cross_season(full: bool):
    if not full:
        m = _marker("B6_cross_season")
        if m and m.get("ok"):
            return PASS, f"cached: {m.get('detail','')}"
        return SKIP, "run --full (or no cached cross_season marker)"
    try:
        from cross_season import possession
        pd_res = possession("poss_dur")
        # poss_dur should REPLICATE ~ -2% both seasons; after_to ~ 0 (the known-good control)
        seasons = pd_res.get("seasons", {})
        rels = [s.get("rel") for s in seasons.values() if "rel" in s]
        ok = pd_res.get("verdict") == "REPLICATES" and all(r is not None and r < -0.015 for r in rels)
        detail = f"poss_dur verdict={pd_res.get('verdict')} rels={[round(r,4) for r in rels]}"
        if ok:
            write_marker("B6_cross_season", dict(ok=True, detail=detail))
        return (PASS if ok else FAIL), detail
    except Exception as e:
        return FAIL, f"cross_season error: {str(e)[:100]}"


def b7_domain_router(full: bool):
    m = _marker("B7_domain_router")
    dom = os.path.join(ROOT, "data", "registry", "domain_registry")
    has_dom = os.path.isdir(dom) and bool(glob.glob(os.path.join(dom, "part-*.parquet")))
    if m and m.get("routed_ok") and has_dom:
        return PASS, f"domain router live ({m.get('detail','')})"
    return FAIL, f"domain_registry present={has_dom}; >=3 validated signals routed + >=1 engine consuming not confirmed"


def b8_ensemble(full: bool):
    m = _marker("B8_ensemble_weights")
    if m and m.get("method") and m.get("method") != "equal":
        return PASS, f"reliability-weighted ensemble fitted (method={m.get('method')})"
    return FAIL, "ensemble still equal-weight (BLOCKED until a leak-free cross-season reliability backtest exists)"


def b9_calibration(full: bool):
    m = _marker("B9_calibration_loop")
    if m and m.get("delta_row_appended"):
        return PASS, f"continual-calibration loop ran ({m.get('detail','')})"
    return FAIL, "update.py->learn_ledger continual-calibration delta not yet recorded"


def b10_ingame(full: bool):
    m = _marker("B10_live_latency")
    if m and m.get("ms_per_poss") is not None and m["ms_per_poss"] < 500 and m.get("no_llm"):
        return PASS, f"in-game fast path {m['ms_per_poss']:.0f}ms/poss, no LLM in loop"
    return FAIL, "in-game fast path <500ms/possession not yet measured"


def b11_state(full: bool):
    try:
        from autoloop.state import read_state, ledger_df
        s = read_state()
        led = ledger_df()
        ok = bool(s) and s.get("phase") in ("BUILD", "IMPROVE") and led is not None
        return (PASS if ok else FAIL), f"state.json phase={s.get('phase')}, ledger {len(led)} rows"
    except Exception as e:
        return FAIL, f"state spine error: {str(e)[:80]}"


def b12_memory(full: bool):
    try:
        from memory_lint import lint
        rep = lint()
        ok = not rep["blocking"]
        return (PASS if ok else FAIL), (f"clean ({rep['line_count']} lines)" if ok
                                        else "; ".join(rep["reasons"]))
    except Exception as e:
        return FAIL, f"memory_lint error: {str(e)[:80]}"


CHECKS = [
    ("B1", "Board green (5/5)", b1_board),
    ("B2", "Engines load + fuse (>=7)", b2_engines),
    ("B3", "Sharded registries schema-valid", b3_registries),
    ("B4", "Foundry TRUST GATE (2 CAVEATs)", b4_trust_gate),
    ("B5", "FDR wired + planted-null", b5_fdr),
    ("B6", "Cross-season bar reproduces", b6_cross_season),
    ("B7", "Domain router live", b7_domain_router),
    ("B8", "Reliability-weighted ensemble", b8_ensemble),
    ("B9", "Continual-calibration loop", b9_calibration),
    ("B10", "In-game fast path <500ms", b10_ingame),
    ("B11", "State + ledger spine", b11_state),
    ("B12", "Memory not corrupting", b12_memory),
]


def run(full: bool = False) -> dict:
    results = {}
    for bid, label, fn in CHECKS:
        try:
            status, detail = fn(full)
        except Exception as e:
            status, detail = FAIL, f"exception: {str(e)[:100]}"
        results[bid] = dict(label=label, status=status, detail=detail)
    return results


def main():
    full = "--full" in sys.argv
    results = run(full)
    print(f"=== BUILD-DONE CHECKLIST {'(--full)' if full else '(fast; --full runs board+cross_season)'} ===\n")
    n_pass = 0
    for bid, label, _ in CHECKS:
        r = results[bid]
        mark = {PASS: "[x]", FAIL: "[ ]", SKIP: "[~]"}[r["status"]]
        print(f"{mark} {bid:4s} {label:34s} {r['status']:4s}  {r['detail']}")
        if r["status"] == PASS:
            n_pass += 1
    allp = n_pass == len(CHECKS)
    print(f"\nBUILD-DONE: {'PASS' if allp else 'FAIL'}  ({n_pass}/{len(CHECKS)} green)")
    if not allp:
        todo = [bid for bid, _, _ in CHECKS if results[bid]["status"] != PASS]
        print(f"remaining: {', '.join(todo)}")
    sys.exit(0 if allp else 1)


if __name__ == "__main__":
    main()
