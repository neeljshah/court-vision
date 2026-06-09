"""Regression board for the autonomy + safety SPINE (MASTER_SYSTEM_BUILD section 6: every new
subsystem ships its own test). The spine is ADDITIVE -- it modifies no serve/golive/production path, so
"byte-identical when OFF" holds by construction (test_spine_is_additive asserts no import side effects).

  python -m pytest tests/test_spine.py -q
"""
import os
import sys
import tempfile

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "team_system"))


def test_ids_dedup_and_family():
    from registry.ids import signal_id, family_key
    a = dict(grain="possession", entity_scope="team", domain_tags=["transition", "pace"], source="pbp",
             formula_ast="off_to_share*ppp + 0.1000001", transform_chain=["rate"],
             asof_fn_name="asof_team", causal_sign=1)
    c = dict(a, formula_ast="ppp*off_to_share + 0.1", domain_tags=["pace", "transition"])  # equal
    b = dict(a, formula_ast="ppp + off_to_share")                                          # different
    assert signal_id(a) == signal_id(c)         # commutativity + order + float-quantize all dedup
    assert signal_id(a) != signal_id(b)
    f1 = dict(a, transform_chain=["roll_5"]); f2 = dict(a, transform_chain=["roll_10"])
    assert family_key(f1) == family_key(f2)     # same transform family, different window


def test_store_transactional_and_integrity(monkeypatch):
    import registry.store as S
    from registry.ids import signal_id
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr(S, "REGISTRY_DIR", tmp)
    monkeypatch.setattr(S, "_LOCK", os.path.join(tmp, ".lock"))
    r = S.Registry("signal_registry")
    row = dict(grain="possession", entity_scope="team", domain_tags=["transition"], source="pbp",
               formula_ast="a*b", transform_chain=["rate"], asof_fn="asof_t", causal_sign=1,
               status="proposed", builder="test")
    row["signal_id"] = signal_id(dict(row, asof_fn_name=row["asof_fn"]))
    rid = r.register(row)
    assert r.register(row) == rid and len(r) == 1            # dedup no-op
    r.update_status(rid, status="validated")
    assert r.get(rid)["status"] == "validated" and len(r) == 1

    # integrity: same id, different definition -> must raise
    bad = dict(r.get(rid), grain="player-game")
    pd.DataFrame([bad]).to_parquet(os.path.join(tmp, "signal_registry", "part-999999-000000.parquet"),
                                   index=False)
    with pytest.raises(RuntimeError):
        S.Registry("signal_registry")._assert_integrity()

    # transactional_write: bad validator must NOT touch the live file
    dest = os.path.join(tmp, "art.txt")
    assert S.transactional_write(dest, lambda p: open(p, "w").write("ok"),
                                 lambda p: (_ for _ in ()).throw(AssertionError()) if open(p).read() != "ok" else None)
    assert not S.transactional_write(dest, lambda p: open(p, "w").write("corrupt"),
                                     lambda p: (_ for _ in ()).throw(AssertionError("bad")))
    assert open(dest).read() == "ok"


def test_state_ledger_lever_lifecycle(monkeypatch):
    import autoloop.state as st
    tmp = tempfile.mkdtemp()
    for attr, fn in [("STATE_PATH", "state.json"), ("LEDGER_PATH", "led.parquet"),
                     ("RUN_LEDGER", "run.json"), ("PROC_LEDGER", "proc.json"), ("STOP_PATH", "STOP")]:
        monkeypatch.setattr(st, attr, os.path.join(tmp, fn))
    st.write_state(st.default_state())
    assert st.read_state()["phase"] == "BUILD"
    lid = st.lever_id("foundry", "transition", "grammar")
    assert not st.lever_barred(lid)
    st.claim_lever(1, "BUILD", "foundry", lid, agents=3, metric_before=9.1)
    assert st.lever_in_flight(lid)
    st.close_lever(1, "REJECTED", metric_after=9.1, delta=0.0, board="5/5")
    assert st.lever_barred(lid) and not st.lever_in_flight(lid)
    for i in range(2, 7):
        l2 = st.lever_id("f", f"t{i}", "m"); st.claim_lever(i, "BUILD", "f", l2); st.close_lever(i, "NULL", delta=0.0)
    assert st.stuck_tripwire(5) and st.frontier_exhausted("f", 3)
    st.bump_run_ledger(iters=1, subagent_calls=3); st.bump_run_ledger(iters=1, subagent_calls=2)
    rl = st.read_run_ledger(); assert rl["iters"] == 2 and rl["subagent_calls"] == 5


def test_guards_disk_and_ps1():
    import autoloop.guards as g
    assert isinstance(g.disk_ok(), bool)
    tmp = tempfile.mkdtemp()
    good = os.path.join(tmp, "ok.ps1")
    g.write_ps1(good, "Write-Output 'hello world'\n")
    ok, reasons = g.ps1_ok(good)
    assert ok, reasons
    with open(good, "rb") as f:
        assert f.read(3) == b"\xef\xbb\xbf"                 # BOM present
    with pytest.raises(ValueError):
        g.write_ps1(os.path.join(tmp, "bad.ps1"), "Write-Output 'em—dash'\n")  # non-ASCII refused


def test_cas_roundtrip_and_stale(monkeypatch):
    import cache.cas as c
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr(c, "CAS_ROOT", os.path.join(tmp, "cas"))
    inp = os.path.join(tmp, "in.txt"); open(inp, "w").write("v1")
    ih = c.input_hash([inp])
    df = pd.DataFrame({"x": [1, 2, 3]})
    c.put("nodeA", ih, df, builder="test")
    assert c.has("nodeA", ih)
    got = c.get("nodeA", ih)
    assert got is not None and list(got.x) == [1, 2, 3]
    open(inp, "w").write("v2-changed")                      # input bytes change
    ih2 = c.input_hash([inp])
    assert ih2 != ih and not c.has("nodeA", ih2)            # cache miss -> would recompute


def test_registry_batch_and_dedup(monkeypatch):
    import registry.store as S
    from registry.ids import signal_id
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr(S, "REGISTRY_DIR", tmp)
    monkeypatch.setattr(S, "_LOCK", os.path.join(tmp, ".lock"))
    r = S.Registry("signal_registry")
    rows = []
    for i in range(80):                       # >64 -> exercises the auto-compact under-lock (no deadlock)
        d = dict(grain="possession", entity_scope="team", domain_tags=[f"d{i}"], source="pbp",
                 formula_ast=f"x{i}*y", transform_chain=["rate"], asof_fn="a", asof_fn_name="a", causal_sign=1)
        d["signal_id"] = signal_id(d)
        rows.append(d)
    out = r.register_many(rows)
    assert out["registered"] == 80 and len(r) == 80
    assert r.register_many(rows)["registered"] == 0           # idempotent: all dup -> 0 new
    from registry.dedup import dedup_pass
    monkeypatch.setattr("registry.dedup.Registry", S.Registry)
    dd = dedup_pass("signal_registry")
    assert dd["n"] == 80 and len(dd["unmerged_pairs"]) == 0    # all distinct formulas -> clean


def test_memory_lint_runs():
    from memory_lint import lint
    rep = lint()
    for k in ("line_count", "broken_links", "stale_citations", "blocking", "reasons"):
        assert k in rep


def test_foundry_judge():
    from signals.judge import sign_sanity, engine_redundancy
    assert not sign_sanity(1, -1)[0]                      # declared + but measured - -> confound REJECT
    assert sign_sanity(1, 1)[0] and sign_sanity(0, -1)[0]  # consistent / undeclared -> ok
    assert not engine_redundancy("oreb", {"efg", "tov", "oreb", "ft"})[0]   # owned-node collision REJECT
    assert engine_redundancy("transition", {"efg", "oreb"})[0]              # not owned -> ok
    import numpy as np
    v = np.arange(100.0)
    assert not engine_redundancy("x", set(), v, v + 1e-6 * np.random.default_rng(0).standard_normal(100))[0]  # corr~1


def test_foundry_fdr_and_null():
    from signals.gates import benjamini_hochberg, benjamini_yekutieli, planted_null_test
    import numpy as np
    p = np.array([0.001, 0.002, 0.2, 0.5, 0.9])
    assert benjamini_hochberg(p, 0.05).sum() >= 1                 # the tiny p-values are discoveries
    assert benjamini_yekutieli(p, 0.05).sum() <= benjamini_hochberg(p, 0.05).sum()  # BY more conservative
    res = planted_null_test(n=40, batches=40, rows=200, procedure="bh", seed=1)
    assert res["planted_null_ok"], res["detail"]                  # FDR controls error under the null


def test_domain_model_eb_shrink():
    from models.domain_model import DomainModel
    # rich data -> the validated effect shows; thin data -> shrinks toward neutral 1.0
    rich = DomainModel("transition", "team", [dict(signal_id="sig_a", gateA_rel=-0.05, n=1000)])
    thin = DomainModel("transition", "team", [dict(signal_id="sig_a", gateA_rel=-0.05, n=5)])
    cr, ct = rich.component(), thin.component()
    assert cr["multiplier"] > 1.0 and cr["n_signals"] == 1
    assert ct["multiplier"] < cr["multiplier"]            # EB shrink pulls thin data toward neutral
    assert abs(ct["multiplier"] - 1.0) < abs(cr["multiplier"] - 1.0)
    assert DomainModel("transition", "team", []).component()["multiplier"] == 1.0   # no signal -> neutral
    # distinct (domain x scope x signal-set) MUST yield distinct model_ids (the empty-keys collision bug)
    a = DomainModel("transition", "team", [dict(signal_id="sig_x", gateA_rel=-0.02, n=100)]).model_id
    b = DomainModel("possession_origin", "team", [dict(signal_id="sig_x", gateA_rel=-0.02, n=100)]).model_id
    c = DomainModel("transition", "player", [dict(signal_id="sig_y", gateA_rel=-0.02, n=100)]).model_id
    assert len({a, b, c}) == 3 and all(i.startswith("mdl_") for i in (a, b, c))


def test_calibration_registry(monkeypatch):
    import registry.store as S
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr(S, "REGISTRY_DIR", tmp)
    monkeypatch.setattr(S, "_LOCK", os.path.join(tmp, ".lock"))
    creg = S.Registry("calibration_registry")
    creg.upsert(dict(key="prop:pts", shapeErr=2.91, coverage=78.4, reliability=0.971, n=14, updated_utc=0))
    row = creg.get("prop:pts")
    assert row is not None and row["shapeErr"] == 2.91 and row["reliability"] == 0.971
    creg.upsert(dict(key="prop:pts", shapeErr=3.50, coverage=79.0, reliability=0.965, n=14, updated_utc=1))
    assert creg.get("prop:pts")["shapeErr"] == 3.50 and len(creg) == 1   # supersede, not duplicate


def test_live_engine_hot_path_latency():
    import numpy as np
    from live_engine import replay_and_time, _state_mult_tensor, STATS
    # synthetic projection table (no sim) -> exercises ONLY the hot path
    P = 24
    table = dict(pids=list(range(P)), proj=np.abs(np.random.default_rng(0).standard_normal((P, len(STATS)))) * 10,
                 mult=_state_mult_tensor())
    r = replay_and_time(table, n_poss=220)
    assert r["ms_max"] < 500.0, r          # the 500ms/possession budget
    assert r["board_shape"] == [P, len(STATS)]


def test_ensemble_redundancy_weights():
    import numpy as np
    from ensemble.weights import redundancy_weights
    # 3 highly-correlated engines + 1 decorrelated -> the decorrelated one must get the MOST weight
    C = np.array([[1, .9, .9, .1], [.9, 1, .9, .1], [.9, .9, 1, .1], [.1, .1, .1, 1.0]])
    w = redundancy_weights(C)
    assert abs(w.sum() - 1.0) < 1e-9 and (w >= 0).all()        # valid non-negative distribution
    assert w[3] > w[0] and w[3] > w[1] and w[3] > w[2]          # decorrelated engine up-weighted


def test_cluster_lab_rejects_noise(monkeypatch, tmp_path):
    # composition must NOT manufacture signal from noise: random signals -> does-NOT-replicate (a planted null)
    import numpy as np
    from signals import cluster_lab
    rng = np.random.default_rng(0)
    rows = []
    for season in ("2022-23", "2023-24"):
        for g in range(60):
            for _ in range(40):
                rows.append(dict(gid=f"{season}_{g}", season=season, pts=int(rng.integers(0, 3)),
                                 period=int(rng.integers(1, 5)), grem=float(rng.uniform(0, 2880)),
                                 n1=rng.standard_normal(), n2=rng.standard_normal(), n3=rng.standard_normal()))
    import pandas as pd
    p = tmp_path / "noise.parquet"; pd.DataFrame(rows).to_parquet(p, index=False)
    r = cluster_lab.validate_cluster(str(p), base=["period", "grem"], signals=["n1", "n2", "n3"],
                                     domain="noise", scope="possession", register=False)
    assert r["verdict"] != "REPLICATES", r          # pure-noise cluster must not validate


def test_ingame_repricer_discretize_and_latency():
    import time
    import ingame_state_repricer as ir
    # discretization boundaries: quick clock -> bin 0, late -> high bin; close margin -> 0, blowout -> high
    assert ir._dur_b(3) < ir._dur_b(20) and ir._mar_b(1) < ir._mar_b(30)
    # a synthetic lookup gather must be sub-millisecond (the hot-path property), no real artifact needed
    rp = ir.LiveStateRepricer.__new__(ir.LiveStateRepricer)
    rp.base = 1.1
    rp.lut = {(1, 0, ir._dur_b(5), ir._mar_b(10), 0): 1.55}     # fastbreak cell
    assert rp.ppp(1, 0, 5, 10, 0) == 1.55                        # known state
    assert rp.ppp(0, 0, 14, 2, 1) == 1.1                         # unknown state -> base fallback
    t0 = time.perf_counter()
    for _ in range(5000):
        rp.ppp(1, 0, 5, 10, 0)
    assert (time.perf_counter() - t0) < 0.5                      # 5000 re-prices well under the 500ms/poss budget


def test_roadmap_cursor():
    import roadmap as rm
    s = rm.status()
    assert len(s["milestones"]) >= 10 and s["goal"]
    nxt = rm.next_milestone()
    assert nxt is not None and nxt["pickable"] and nxt["deps_done"]   # a buildable milestone exists
    # human-gated milestones (realmoney) must NEVER be returned as autonomously pickable
    rms = {m["id"]: m for m in s["milestones"]}
    assert not rms["V10"]["pickable"], "placement (realmoney_human) must never be loop-pickable"
    # a milestone with unsatisfied deps must not be pickable
    blocked = [m for m in s["milestones"] if not m["deps_done"]]
    assert all(not m["pickable"] for m in blocked)


def test_spine_is_additive():
    # importing the spine must have NO side effects on the real registry/state (no files written on import).
    before = set(os.listdir(os.path.join(ROOT, "data", "registry"))) if \
        os.path.isdir(os.path.join(ROOT, "data", "registry")) else set()
    import importlib
    for mod in ("registry.ids", "registry.store", "autoloop.state", "autoloop.guards",
                "autoloop.stop_run", "cache.cas", "memory_lint", "build_done_check"):
        importlib.import_module(mod)
    after = set(os.listdir(os.path.join(ROOT, "data", "registry"))) if \
        os.path.isdir(os.path.join(ROOT, "data", "registry")) else set()
    assert before == after, f"spine import created files: {after - before}"
