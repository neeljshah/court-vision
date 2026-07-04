"""Per-file tests for ingame_grading_multi_runner (injected fns, no real I/O).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_grading_multi_runner.py -q
"""
from __future__ import annotations

from scripts.platformkit.ingame import ingame_grading_multi_runner as runner


def test_tick_composes_both_steps(monkeypatch):
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)

    verdict_calls = []
    trust_calls = []

    def verdict_fn():
        verdict_calls.append(1)
        return {"tennis": {"n_labeled": 0, "better_segments": [], "worse_segments": []}}

    def trust_fn():
        trust_calls.append(1)
        return {"tennis": {"trusted": [], "adverse": []}}

    doc = runner.tick(now=1000.0, verdict_fn=verdict_fn, trust_fn=trust_fn,
                      label_refresh_fn=lambda: {})
    assert verdict_calls and trust_calls
    assert doc["component"] == "ingame_grading_multi"
    assert doc["edge_claimed"] is False
    assert doc["measurement_only"] is True
    assert doc["verdict_summary"]["tennis"]["n_labeled"] == 0
    assert doc["label_refresh_summary"] == {}


def test_tick_never_raises_when_a_step_fails(monkeypatch):
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)

    def _boom():
        raise RuntimeError("verdict exploded")

    doc = runner.tick(
        now=1000.0, verdict_fn=_boom,
        trust_fn=lambda: {"wnba": {"trusted": [], "adverse": []}},
        label_refresh_fn=lambda: {},
    )
    assert "error" in doc["verdict_summary"]
    assert doc["trust_summary"]["wnba"]["trusted"] == []


def test_tick_isolates_label_refresh_failure_from_verdict_and_trust(monkeypatch):
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)

    def _boom_refresh():
        raise RuntimeError("finals refresh exploded")

    doc = runner.tick(
        now=1000.0,
        verdict_fn=lambda: {"soccer_intl": {"n_labeled": 5}},
        trust_fn=lambda: {"soccer_intl": {"trusted": [], "adverse": []}},
        label_refresh_fn=_boom_refresh,
    )
    assert "error" in doc["label_refresh_summary"]
    assert doc["verdict_summary"]["soccer_intl"]["n_labeled"] == 5
    assert doc["trust_summary"]["soccer_intl"]["trusted"] == []


def test_tick_calls_label_refresh_step(monkeypatch):
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)
    calls = []

    def label_refresh_fn():
        calls.append(1)
        return {"soccer_intl_finals": {"n_fetched": 2, "error": None}}

    doc = runner.tick(
        now=1000.0, verdict_fn=lambda: {}, trust_fn=lambda: {},
        label_refresh_fn=label_refresh_fn,
    )
    assert calls == [1]
    assert doc["label_refresh_summary"]["soccer_intl_finals"]["n_fetched"] == 2


def test_default_label_refresh_fn_wraps_real_refresh_all_without_raising(monkeypatch):
    """When no label_refresh_fn is injected, tick() falls back to the real
    _run_label_refresh -- verify it delegates to label_finals_refresh.refresh_all
    (patched here to a no-network stub) and never raises."""
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)
    import scripts.platformkit.autonomy.label_finals_refresh as lfr
    monkeypatch.setattr(lfr, "refresh_all", lambda: {"stub": {"n_fetched": 0, "error": None}})

    doc = runner.tick(now=1000.0, verdict_fn=lambda: {}, trust_fn=lambda: {})
    assert doc["label_refresh_summary"] == {"stub": {"n_fetched": 0, "error": None}}


def test_run_stops_after_max_ticks(monkeypatch):
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)
    monkeypatch.setattr(runner, "tick", lambda **kw: {"verdict_summary": {}, "trust_summary": {}})
    ticks = runner.run(max_ticks=3, clock=lambda: 1.0, sleep=lambda s: None)
    assert ticks == 3


def test_heartbeat_component_name_matches_registered_spec():
    assert runner.HEARTBEAT_COMPONENT == "m36_ingame_grading_multi"


def test_default_interval_matches_m25_cadence():
    assert runner.DEFAULT_INTERVAL_SEC == 900.0


# --- LANE 5: freshness adjudication auto-wire -------------------------------

def test_freshness_runs_on_first_tick_and_every_nth(monkeypatch):
    """tick_no=1 and tick_no=1+N run the freshness step; tick_no=2 does not."""
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)
    calls = []

    def freshness_fn():
        calls.append(1)
        return {"outcome_verdict_freshness": {}, "freshness_cross_corpus": {}}

    doc1 = runner.tick(now=1000.0, verdict_fn=lambda: {}, trust_fn=lambda: {},
                       label_refresh_fn=lambda: {}, freshness_fn=freshness_fn, tick_no=1)
    doc2 = runner.tick(now=1000.0, verdict_fn=lambda: {}, trust_fn=lambda: {},
                       label_refresh_fn=lambda: {}, freshness_fn=freshness_fn, tick_no=2)
    doc33 = runner.tick(now=1000.0, verdict_fn=lambda: {}, trust_fn=lambda: {},
                        label_refresh_fn=lambda: {}, freshness_fn=freshness_fn,
                        tick_no=1 + runner.FRESHNESS_EVERY_N_TICKS)
    assert calls == [1, 1]
    assert "outcome_verdict_freshness" in doc1["freshness_summary"]
    assert doc2["freshness_summary"]["skipped_reason"] == "not_nth_tick"
    assert doc2["freshness_summary"]["tick_no"] == 2
    assert "outcome_verdict_freshness" in doc33["freshness_summary"]


def test_freshness_step_isolated_from_verdict_and_trust(monkeypatch):
    """A raising freshness step degrades to an error entry but never blocks
    verdict/trust, and never propagates out of tick()."""
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)

    def _boom_freshness():
        raise RuntimeError("freshness exploded")

    doc = runner.tick(
        now=1000.0, verdict_fn=lambda: {"mlb": {"n_labeled": 3}},
        trust_fn=lambda: {"mlb": {"trusted": [], "adverse": []}},
        label_refresh_fn=lambda: {}, freshness_fn=_boom_freshness, tick_no=1,
    )
    assert "error" in doc["freshness_summary"]
    assert doc["verdict_summary"]["mlb"]["n_labeled"] == 3
    assert doc["trust_summary"]["mlb"]["trusted"] == []


def test_verdict_and_trust_failures_do_not_block_freshness(monkeypatch):
    """Mirror-direction isolation: verdict/trust raising must not prevent the
    freshness step from running on a landing tick."""
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)

    def _boom():
        raise RuntimeError("boom")

    doc = runner.tick(
        now=1000.0, verdict_fn=_boom, trust_fn=_boom, label_refresh_fn=_boom,
        freshness_fn=lambda: {"outcome_verdict_freshness": {"ok": True}},
        tick_no=1,
    )
    assert doc["freshness_summary"]["outcome_verdict_freshness"] == {"ok": True}
    assert "error" in doc["verdict_summary"]
    assert "error" in doc["trust_summary"]
    assert "error" in doc["label_refresh_summary"]


def test_run_freshness_adjudications_isolates_each_sub_step(monkeypatch):
    """_run_freshness_adjudications: one sub-step raising must not block the
    other from populating its own key."""
    def _boom_ovf():
        raise RuntimeError("ovf exploded")

    def _ok_fcc():
        return {"overall_segment_verdict": {"I1": "NOT-REPLICATED"}}

    monkeypatch.setattr(runner, "_run_outcome_verdict_freshness", _boom_ovf)
    monkeypatch.setattr(runner, "_run_freshness_cross_corpus", _ok_fcc)
    out = runner._run_freshness_adjudications()
    assert "error" in out["outcome_verdict_freshness"]
    assert out["freshness_cross_corpus"]["overall_segment_verdict"]["I1"] == "NOT-REPLICATED"


def test_tick_without_tick_no_uses_module_counter(monkeypatch):
    """When tick_no is omitted, tick() advances the module-level _tick_counter
    so a real run() loop still gates correctly across successive calls."""
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)
    monkeypatch.setattr(runner, "_tick_counter", 0)
    calls = []

    def freshness_fn():
        calls.append(1)
        return {}

    for _ in range(runner.FRESHNESS_EVERY_N_TICKS + 1):
        runner.tick(now=1000.0, verdict_fn=lambda: {}, trust_fn=lambda: {},
                    label_refresh_fn=lambda: {}, freshness_fn=freshness_fn)
    # tick 1 and tick (N+1) both land -> 2 calls over N+1 ticks.
    assert calls == [1, 1]


def test_freshness_every_n_ticks_matches_2_to_4x_per_day_target():
    ticks_per_day = 86400.0 / runner.DEFAULT_INTERVAL_SEC
    runs_per_day = ticks_per_day / runner.FRESHNESS_EVERY_N_TICKS
    assert 2.0 <= runs_per_day <= 4.0
