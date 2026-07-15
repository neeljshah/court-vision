"""Per-file tests for supervisor.manifest / config / health.

Covers (with NO real process, socket, port, or wall clock):
  * manifest("default") / manifest("backend") are acyclic + topologically ordered
    (every dependency precedes its dependents); backend drops the node UI.
  * an injected CYCLIC depends_on graph is rejected with CycleError; an unknown
    depends_on name is also rejected.
  * readiness probes resolve with a FAKE fetcher + FAKE clock for all four kinds
    (none / tcp / http / heartbeat-fresh / heartbeat-stale / heartbeat-absent).
  * config.load_profile falls back safely on a missing / garbage profile and
    coerces include_ui -> backend.

Run ONLY this file:
  C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
    tests/supervisor/test_manifest.py -q
"""
from __future__ import annotations

import json

import pytest

from supervisor.config import load_profile
from supervisor.health import probe
from supervisor.manifest import (
    HEARTBEAT,
    HTTP,
    NONE,
    TCP,
    CycleError,
    ProcSpec,
    ReadinessSpec,
    RestartPolicy,
    manifest,
    topo_order,
)


# --------------------------------------------------------------------------- #
# manifest DAG: acyclic + topologically ordered
# --------------------------------------------------------------------------- #
def _assert_topo(specs):
    """Every depends_on name must appear earlier in the ordered list."""
    seen = set()
    names = [s.name for s in specs]
    assert len(names) == len(set(names)), "duplicate names in manifest"
    for s in specs:
        for dep in s.depends_on:
            assert dep in seen, "%s booted before its dep %s" % (s.name, dep)
        seen.add(s.name)


def test_default_manifest_is_acyclic_and_ordered():
    specs = manifest("default")
    assert {s.name for s in specs} == {
        "m1_producer", "m1_api_paper", "m1_api_boards", "m1_ui",
        "m1_paper", "m1_line_daemon", "m1_bankroll", "m6_ingame_loop",
        "m2_inplay", "m4_selfimprove", "m7_ingame_refresh",
        "m5_autonomy_monitor", "m8_ci_cadence", "m2_inplay_capture",
        # W12 new measurement-only daemons
        "m10_best_bets_compute", "m11_ingame_pred_tick",
        "m12_pm_paper_tick", "m13_props_pred_tick",
        # later measurement-only daemons (brain rebuild + settle + CLV/PM capture)
        "m14_brain_rebuild", "m15_prop_settle", "m16_prop_close_capture",
        "m17_kalshi_scan", "m18_pm_close_capture",
        # m19 -- ceiling asof-reclaim gate daemon (candidate-only, flips no flag)
        "m19_asof_reclaim",
        # m20 -- in-game CLV verdict daemon (continuous in-play-close anticipation)
        "m20_ingame_clv_verdict",
        # m21 -- in-game base-out anticipation trigger gate (candidate-only, flips no flag)
        "m21_ingame_baseout_gate",
        # m22 -- best-price scan daemon (continuous model-free +CLV gap scan, no bet)
        "m22_best_price_scan",
        # m23 -- scraped-line gap daemon (our own DK/FD/Pinnacle feed, freshness-gated)
        "m23_scraped_line_gaps",
        # m24 -- in-game placement funnel diagnostic (where in-game volume is lost)
        "m24_ingame_placement_funnel",
        # m25 -- in-game outcome-gated verdict (per-segment Brier vs truth, no bet)
        "m25_ingame_outcome_verdict",
        # m26 -- in-game segment-trust gate (cross-corpus proof-gated execution floor)
        "m26_ingame_segment_trust",
        # m27 -- in-game paper settle arm (settles open paper_ingame bets vs final score)
        "m27_ingame_paper_settle",
        # m29 -- output-freshness sentinel (GREEN/RED per readiness=NONE daemon m19-27;
        # read-only, no restart authority)
        "m29_output_freshness",
        # m30 -- feed-health sentinel (GREEN/RED per live odds-provider/sport probe;
        # read-only, no restart authority)
        "m30_feed_health",
        # m31 -- MLB pregame-context snapshotter (probables/weather/umps + injuries
        # + deterministic edge facts; snapshot-append, as-of vintages, no $)
        "m31_mlb_context",
        # m32 -- MLB context autogate (nightly SP-offset + weather-totals
        # re-gating vs the growing M31 corpus; verdicts only, no $)
        "m32_mlb_context_autogate",
        # m33 -- HTTP-readiness wedge reaper (kills a wedged PID on >=3
        # consecutive >10s HTTP timeouts while port stays listening AND
        # CPU>50% sustained >120s; supervisor relaunches, no $)
        "m33_http_wedge_reaper",
        # m34 -- per-daemon freshness SLA scoreboard (GREEN/RED/NA per
        # supervised daemon; missing table entry = NA, never GREEN; read-only)
        "m34_freshness_sla",
        # m35 -- cross-sport (tennis + soccer_intl/WC) in-play tail-band scan +
        # forward gate + tick-latency scoreboard; verdicts only, no $
        "m35_ingame_tail_multi",
        # m36 -- multi-sport in-game grading (soccer_intl/tennis/wnba outcome-
        # gated verdict + cross-corpus segment trust); measurement only, no $
        "m36_ingame_grading_multi",
        # m37 -- LANE 2 combined wave-10 enrichment tick (fotmob + gumbo +
        # book-depth, per-source failure-isolated); capture/measurement only, no $
        "m37_ingame_enrichment",
        # m38 -- the AUTOLOOP daemon (zero-LLM, sha-pinned standing-prereg
        # registry composing the P4 ratchet/reclaim-gate/claims-factory/FWER
        # harnesses verbatim; measurement/suppress-only, never promotes)
        "m38_autoloop",
        # m39 -- NBA injury-facts snapshotter (as-of vintages appended to the
        # injury_facts_<sport>.jsonl the gamebrief layer reads; knowledge only)
        "m39_injury_facts_nba",
        # m40 -- wedge restarter (reads m29 output-freshness REDs; supervisor
        # is the sole actor; no restart authority of its own)
        "m40_wedge_restarter",
        # m41 -- public betting-splits capture (sentiment-vs-price rows to
        # data/cache/public_splits/<league>/<date>.jsonl; capture only)
        "m41_public_splits",
        # m42 -- exec-quality daemon (min-age realized-CLV backfill + paper
        # digest/breaker refresh every 120s; measurement only)
        "m42_exec_quality",
        # m43 -- settlement-sweep daemon (retries the aged >=7d open paper
        # backlog via existing settlers; hourly; VOIDs unroutable rows only)
        "m43_settle_sweep",
    }
    _assert_topo(specs)
    # producer precedes the Auto-API which precedes the boards API which precedes UI.
    order = [s.name for s in specs]
    assert order.index("m1_producer") < order.index("m1_api_paper")
    assert order.index("m1_api_paper") < order.index("m1_api_boards")
    assert order.index("m1_api_boards") < order.index("m1_ui")


def test_backend_profile_drops_ui_and_stays_acyclic():
    specs = manifest("backend")
    names = {s.name for s in specs}
    assert "m1_ui" not in names
    assert all(s.kind != "node" for s in specs)
    # no surviving spec may depend on the removed UI.
    for s in specs:
        assert "m1_ui" not in s.depends_on
    # the always-on acquisition + self-improve daemons survive headless (they are
    # not node UIs and must stay supervised even without the front end).
    assert {"m1_line_daemon", "m2_inplay", "m4_selfimprove",
            "m7_ingame_refresh", "m5_autonomy_monitor"}.issubset(names)
    _assert_topo(specs)


def test_unknown_profile_falls_back_to_default():
    assert [s.name for s in manifest("does-not-exist")] == \
           [s.name for s in manifest("default")]


# --------------------------------------------------------------------------- #
# cyclic / dangling depends_on -> CycleError
# --------------------------------------------------------------------------- #
def test_injected_cycle_is_rejected():
    a = ProcSpec(name="a", kind="py", module="m.a", depends_on=["b"])
    b = ProcSpec(name="b", kind="py", module="m.b", depends_on=["a"])
    with pytest.raises(CycleError):
        topo_order([a, b])


def test_self_cycle_is_rejected():
    a = ProcSpec(name="a", kind="py", module="m.a", depends_on=["a"])
    with pytest.raises(CycleError):
        topo_order([a])


def test_unknown_dependency_is_rejected():
    a = ProcSpec(name="a", kind="py", module="m.a", depends_on=["ghost"])
    with pytest.raises(CycleError):
        topo_order([a])


def test_duplicate_name_is_rejected():
    a = ProcSpec(name="a", kind="py", module="m.a")
    a2 = ProcSpec(name="a", kind="py", module="m.b")
    with pytest.raises(CycleError):
        topo_order([a, a2])


def test_topo_order_simple_chain():
    a = ProcSpec(name="a", kind="py", module="m.a")
    b = ProcSpec(name="b", kind="py", module="m.b", depends_on=["a"])
    c = ProcSpec(name="c", kind="py", module="m.c", depends_on=["b"])
    out = [s.name for s in topo_order([c, b, a])]
    assert out == ["a", "b", "c"]


# --------------------------------------------------------------------------- #
# ProcSpec / RestartPolicy validation
# --------------------------------------------------------------------------- #
def test_procspec_rejects_bad_shape():
    with pytest.raises(ValueError):
        ProcSpec(name="x", kind="py")          # py needs a module
    with pytest.raises(ValueError):
        ProcSpec(name="x", kind="node")        # node needs a cmd
    with pytest.raises(ValueError):
        ProcSpec(name="x", kind="ruby", module="m")  # bad kind
    with pytest.raises(ValueError):
        ReadinessSpec(kind="ping")             # bad readiness kind


def test_restart_policy_backoff_is_capped_exponential():
    pol = RestartPolicy(max_retries=3, backoff_base_sec=2.0, backoff_cap_sec=10.0)
    assert pol.backoff_for(1) == 2.0
    assert pol.backoff_for(2) == 4.0
    assert pol.backoff_for(3) == 8.0
    assert pol.backoff_for(4) == 10.0          # capped
    assert pol.backoff_for(0) == 0.0
    assert not pol.exhausted(2)
    assert pol.exhausted(3)
    # forever-policy never exhausts.
    assert not RestartPolicy(max_retries=None).exhausted(9999)


# --------------------------------------------------------------------------- #
# readiness probes with fake fetcher + fake clock
# --------------------------------------------------------------------------- #
class _FakeFetcher:
    """Records requests; returns canned responses keyed by req['kind']."""

    def __init__(self, tcp_open=True, http_status=200):
        self.tcp_open = tcp_open
        self.http_status = http_status
        self.calls = []

    def __call__(self, req):
        self.calls.append(req)
        if req["kind"] == "tcp":
            return {"open": self.tcp_open}
        if req["kind"] == "http":
            return {"status": self.http_status}
        return {}


def _clock(t):
    return lambda: t


def test_probe_none_ready_if_alive():
    spec = ProcSpec(name="p", kind="py", module="m",
                    readiness=ReadinessSpec(kind=NONE))
    res = probe(spec, fetcher=None, clock=_clock(100.0))
    assert res["ready"] is True
    assert res["detail"]["kind"] == NONE


def test_probe_tcp_open_and_closed():
    spec = ProcSpec(name="p", kind="py", module="m", port=8098,
                    readiness=ReadinessSpec(kind=TCP))
    f_open = _FakeFetcher(tcp_open=True)
    assert probe(spec, fetcher=f_open, clock=_clock(0.0))["ready"] is True
    assert f_open.calls[0] == {"kind": "tcp", "host": "127.0.0.1",
                               "port": 8098, "timeout": 2.0}
    f_closed = _FakeFetcher(tcp_open=False)
    assert probe(spec, fetcher=f_closed, clock=_clock(0.0))["ready"] is False
    # no fetcher -> not ready, never raises.
    assert probe(spec, fetcher=None, clock=_clock(0.0))["ready"] is False


def test_probe_http_200_and_503():
    spec = ProcSpec(name="p", kind="py", module="m", port=8099,
                    readiness=ReadinessSpec(kind=HTTP, http_path="/health"))
    f_ok = _FakeFetcher(http_status=200)
    res = probe(spec, fetcher=f_ok, clock=_clock(0.0))
    assert res["ready"] is True
    assert f_ok.calls[0]["url"] == "http://127.0.0.1:8099/health"
    f_bad = _FakeFetcher(http_status=503)
    assert probe(spec, fetcher=f_bad, clock=_clock(0.0))["ready"] is False


def test_probe_fetcher_raise_is_caught():
    def boom(_req):
        raise RuntimeError("network down")

    spec = ProcSpec(name="p", kind="py", module="m", port=8099,
                    readiness=ReadinessSpec(kind=HTTP, http_path="/health"))
    res = probe(spec, fetcher=boom, clock=_clock(0.0))
    assert res["ready"] is False
    assert res["detail"]["reason"] == "fetcher_raised"


def test_probe_heartbeat_fresh_stale_absent(tmp_path):
    hb = tmp_path / "_heartbeat.json"
    hb.write_text(json.dumps({"updated_at": 1000.0}), encoding="utf-8")
    spec = ProcSpec(
        name="p", kind="py", module="m",
        readiness=ReadinessSpec(kind=HEARTBEAT,
                                heartbeat_path=str(hb), fresh_sec=120.0),
    )
    # 50s old -> fresh.
    res = probe(spec, fetcher=None, clock=_clock(1050.0))
    assert res["ready"] is True
    assert res["detail"]["age_sec"] == 50.0
    # 300s old -> stale.
    res = probe(spec, fetcher=None, clock=_clock(1300.0))
    assert res["ready"] is False
    assert res["detail"]["reason"] == "stale"
    # absent file -> not ready.
    spec_missing = ProcSpec(
        name="p", kind="py", module="m",
        readiness=ReadinessSpec(kind=HEARTBEAT,
                                heartbeat_path=str(tmp_path / "nope.json"),
                                fresh_sec=120.0),
    )
    res = probe(spec_missing, fetcher=None, clock=_clock(1050.0))
    assert res["ready"] is False
    assert res["detail"]["reason"] == "absent"


def test_probe_heartbeat_falls_back_to_mtime(tmp_path):
    """A heartbeat without updated_at uses file mtime; clock=None uses real time."""
    hb = tmp_path / "_heartbeat.json"
    hb.write_text(json.dumps({"note": "no updated_at here"}), encoding="utf-8")
    spec = ProcSpec(
        name="p", kind="py", module="m",
        readiness=ReadinessSpec(kind=HEARTBEAT,
                                heartbeat_path=str(hb), fresh_sec=3600.0),
    )
    # just-written file vs real now -> fresh.
    assert probe(spec)["ready"] is True


# --------------------------------------------------------------------------- #
# config: safe fallback + coercion
# --------------------------------------------------------------------------- #
def test_load_profile_missing_falls_back(tmp_path):
    prof = load_profile("ghost", boot_dir=tmp_path)
    assert prof.source == "fallback-missing"
    assert prof.profile == "default"
    assert [s.name for s in prof.specs()] == [s.name for s in manifest("default")]


def test_load_profile_garbage_falls_back(tmp_path):
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    prof = load_profile("broken", boot_dir=tmp_path)
    assert prof.source == "fallback-garbage"
    assert prof.profile == "default"


def test_load_profile_include_ui_false_maps_to_backend(tmp_path):
    (tmp_path / "head.json").write_text(
        json.dumps({"include_ui": False, "global_env": {"X": 1}}),
        encoding="utf-8",
    )
    prof = load_profile("head", boot_dir=tmp_path)
    assert prof.source == "file"
    assert prof.profile == "backend"
    assert prof.global_env == {"X": "1"}        # coerced to str
    assert all(s.kind != "node" for s in prof.specs())


def test_load_profile_explicit_profile_wins(tmp_path):
    (tmp_path / "p.json").write_text(
        json.dumps({"profile": "default", "log_dir": "  mylogs  "}),
        encoding="utf-8",
    )
    prof = load_profile("p", boot_dir=tmp_path)
    assert prof.profile == "default"
    assert prof.log_dir == "mylogs"


def test_load_profile_non_object_falls_back(tmp_path):
    (tmp_path / "arr.json").write_text("[1, 2, 3]", encoding="utf-8")
    prof = load_profile("arr", boot_dir=tmp_path)
    assert prof.source == "fallback-garbage"
    assert prof.profile == "default"
