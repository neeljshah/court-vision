"""Per-file test for scripts.platformkit.autoloop.shadow_settle_job.

Acceptance criteria:
1. Spec parse: a valid shadow_spec parses; a missing/invalid one names EXACTLY
   which fields are absent (no guessed defaults).
2. Forward-only leak test: grade rows at or BEFORE the ledger row's as-of are
   NEVER read into the metric -- only strictly-after rows count.
3. Promote / demote / unspecified paths: powered + bar met -> PROMOTE_CANDIDATE;
   powered + bar missed -> DEMOTED; no spec -> exactly ONE SHADOW_UNSPECIFIED.
4. rung8 integration: the wired shadow calls the real module's power math and
   ticks/promotes off the injected join count.
5. mlb_crps / soccer_chain wired shadows: both new-data-readiness watchers
   tick/promote off injected counts against their real on-disk baselines, and
   never raise against the real (un-injected) artifact paths.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/autoloop/test_shadow_settle_job.py -q
"""
from __future__ import annotations

import json
import os
import time

from scripts.platformkit.autoloop import shadow_settle_job as SSJ

AS_OF = "2026-07-01T00:00:00+00:00"
_NO_RUNG8 = lambda: (0, 0, [])  # noqa: E731 -- keeps unit tests off the real corpus


def _grade_row(ts, game, model, market, outcome):
    return {"sport": "mlb", "game_id": game, "ts": ts, "model_prob": model,
            "market_prob": market, "outcome": outcome, "edge_claimed": False}


def _spec_row(bar_op="<=", bar_value=-0.0001, min_n=2, **over):
    row = {"hypothesis": "h1", "sport": "mlb", "verdict": "MATTERS_PROVISIONAL",
           "computed_at": AS_OF, "edge_claimed": False,
           "shadow_spec": {"metric": "brier_model_minus_market",
                           "corpus": "ingame_grade_joined/mlb",
                           "bar": {"op": bar_op, "value": bar_value}, "min_n": min_n}}
    row.update(over)
    return row


def _env(tmp_path, ledger_rows, grade_rows):
    lpath = tmp_path / "prereg_hypothesis_ledger.jsonl"
    lpath.write_text("".join(json.dumps(r) + "\n" for r in ledger_rows), encoding="utf-8")
    groot = tmp_path / "grade"
    (groot / "mlb").mkdir(parents=True)
    (groot / "mlb" / "GAME.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in grade_rows), encoding="utf-8")
    return ({"prereg_hypothesis_ledger": (lpath, "hypothesis")},
            tmp_path / "shadow.jsonl", groot, lpath)


def _shadow_rows(spath):
    if not spath.is_file():
        return []
    return [json.loads(l) for l in spath.read_text(encoding="utf-8").splitlines() if l.strip()]


# 1. spec parse ---------------------------------------------------------------
def test_parse_spec_valid():
    spec, missing = SSJ.parse_spec(_spec_row())
    assert missing == []
    assert spec["metric"] == "brier_model_minus_market"


def test_parse_spec_names_exactly_whats_missing():
    _spec, missing = SSJ.parse_spec({"hypothesis": "h", "verdict": "MATTERS_PROVISIONAL"})
    assert len(missing) == 1 and missing[0].startswith("shadow_spec (")

    bad = _spec_row()
    bad["shadow_spec"] = {"metric": "made_up_metric", "corpus": "wrong_root/mlb",
                          "bar": {"op": "!=", "value": 1}}  # min_n absent too
    del bad["computed_at"]
    _spec, missing = SSJ.parse_spec(bad)
    joined = " | ".join(missing)
    for field in ("shadow_spec.metric", "shadow_spec.corpus", "shadow_spec.bar",
                  "shadow_spec.min_n", "computed_at"):
        assert field in joined


# 2. forward-only leak test ----------------------------------------------------
def test_forward_filter_never_reads_at_or_before_asof(tmp_path):
    grade = [
        _grade_row("2026-06-30T23:59:59Z", "G_BEFORE", 0.9, 0.5, 1.0),
        _grade_row("2026-07-01T00:00:00Z", "G_AT_ASOF", 0.9, 0.5, 1.0),  # == as-of exactly
        _grade_row("2026-07-02T00:00:00Z", "G_AFTER", 0.9, 0.5, 1.0),
    ]
    led, spath, groot, _lp = _env(tmp_path, [_spec_row(min_n=1)], grade)
    out = SSJ.run_shadow_settle({}, ledgers=led, shadow_path=spath, grade_root=groot,
                                rung8_join_fn=_NO_RUNG8)
    assert out["status"] == "ran"
    ticks = [r for r in _shadow_rows(spath) if r["kind"] == "SHADOW_TICK" and r["key"] == "h1"]
    assert len(ticks) == 1
    assert ticks[0]["n_forward"] == 1  # ONLY the strictly-after game counted


# 3a. promote path --------------------------------------------------------------
def test_promote_candidate_when_powered_and_bar_met(tmp_path):
    grade = [_grade_row("2026-07-0%dT01:00:00Z" % d, "G%d" % d, 0.9, 0.5, 1.0) for d in (2, 3, 4)]
    led, spath, groot, _lp = _env(tmp_path, [_spec_row(bar_op="<=", bar_value=-0.0001, min_n=3)], grade)
    out = SSJ.run_shadow_settle({}, ledgers=led, shadow_path=spath, grade_root=groot,
                                rung8_join_fn=_NO_RUNG8)
    assert out["appended"]["PROMOTE_CANDIDATE"] == 1
    promo = [r for r in _shadow_rows(spath) if r["kind"] == "PROMOTE_CANDIDATE" and r["key"] == "h1"]
    assert promo[0]["powered"] is True and promo[0]["value"] < 0
    assert "stays human" in promo[0]["note"]


# 3b. demote path ---------------------------------------------------------------
def test_demoted_when_powered_and_bar_missed(tmp_path):
    grade = [_grade_row("2026-07-0%dT01:00:00Z" % d, "G%d" % d, 0.1, 0.5, 1.0) for d in (2, 3, 4)]
    led, spath, groot, _lp = _env(tmp_path, [_spec_row(bar_op="<=", bar_value=-0.0001, min_n=3)], grade)
    out = SSJ.run_shadow_settle({}, ledgers=led, shadow_path=spath, grade_root=groot,
                                rung8_join_fn=_NO_RUNG8)
    assert out["appended"]["DEMOTED"] == 1
    assert out["appended"]["PROMOTE_CANDIDATE"] == 0
    ticks = [r for r in _shadow_rows(spath) if r["kind"] == "SHADOW_TICK" and r["key"] == "h1"]
    assert ticks[0]["powered"] is True


def test_underpowered_gets_tick_only(tmp_path):
    grade = [_grade_row("2026-07-02T01:00:00Z", "G2", 0.9, 0.5, 1.0)]
    led, spath, groot, _lp = _env(tmp_path, [_spec_row(min_n=50)], grade)
    out = SSJ.run_shadow_settle({}, ledgers=led, shadow_path=spath, grade_root=groot,
                                rung8_join_fn=_NO_RUNG8)
    h1 = [r for r in _shadow_rows(spath) if r["key"] == "h1"]
    assert [r["kind"] for r in h1] == ["SHADOW_TICK"]  # underpowered: tick only
    assert h1[0]["powered"] is False
    assert out["appended"]["PROMOTE_CANDIDATE"] == 0 and out["appended"]["DEMOTED"] == 0


# 3c. unspecified path (exactly once) -------------------------------------------
def test_unspecified_row_appended_exactly_once(tmp_path):
    row = {"hypothesis": "h_nospec", "sport": "nba", "verdict": "SURVIVES_PREREG_PROVISIONAL",
           "computed_at": AS_OF, "edge_claimed": False}
    led, spath, groot, lpath = _env(tmp_path, [row], [])
    watermarks: dict = {}
    out = SSJ.run_shadow_settle(watermarks, ledgers=led, shadow_path=spath, grade_root=groot,
                                rung8_join_fn=_NO_RUNG8)
    assert out["appended"]["SHADOW_UNSPECIFIED"] == 1
    unspec = [r for r in _shadow_rows(spath) if r["kind"] == "SHADOW_UNSPECIFIED"]
    assert "missing:" in unspec[0]["note"] and "shadow_spec" in unspec[0]["note"]

    # bump the ledger mtime -> due again, but the same row is NOT re-reported
    os.utime(lpath, (time.time() + 10, time.time() + 10))
    out2 = SSJ.run_shadow_settle(watermarks, ledgers=led, shadow_path=spath, grade_root=groot,
                                 rung8_join_fn=_NO_RUNG8)
    assert out2["status"] == "ran"
    assert out2["appended"]["SHADOW_UNSPECIFIED"] == 0
    assert len([r for r in _shadow_rows(spath) if r["kind"] == "SHADOW_UNSPECIFIED"]) == 1


# watermark gate ----------------------------------------------------------------
def test_watermark_skips_when_nothing_changed(tmp_path):
    led, spath, groot, _lp = _env(tmp_path, [_spec_row()], [])
    watermarks: dict = {}
    assert SSJ.run_shadow_settle(watermarks, ledgers=led, shadow_path=spath, grade_root=groot,
                                 rung8_join_fn=_NO_RUNG8)["status"] == "ran"
    assert SSJ.run_shadow_settle(watermarks, ledgers=led, shadow_path=spath, grade_root=groot,
                                 rung8_join_fn=_NO_RUNG8)["status"] == "skipped"


# 4. rung8 integration ------------------------------------------------------------
def test_rung8_wired_shadow_ticks_and_promotes_off_module_math(tmp_path):
    from domains.mlb.ingame.rung8_state import rung8_power as RP
    n_req = RP.required_n(RP._DELTA_GRID[1], RP._SIGMA_GRID[1])  # module's own mid-of-range
    led, spath, groot, _lp = _env(tmp_path, [], [])
    out = SSJ.run_shadow_settle({}, ledgers=led, shadow_path=spath, grade_root=groot,
                                rung8_join_fn=lambda: (200, int(n_req) + 1, []))
    assert out["rung8"]["status"] == "ticked" and out["rung8"]["powered"] is True
    kinds = {r["kind"] for r in _shadow_rows(spath) if r["key"] == "rung8_bullpen_pitchcount_conditioning"}
    assert kinds == {"SHADOW_TICK", "PROMOTE_CANDIDATE"}


def test_rung8_real_module_smoke(tmp_path):
    """Real join path (no injection): must never raise out of the job -- it
    either ticks off the real corpus or records an honest error/skip."""
    led, spath, groot, _lp = _env(tmp_path, [], [])
    out = SSJ.run_shadow_settle({}, ledgers=led, shadow_path=spath, grade_root=groot)
    assert out["rung8"]["status"] in {"ticked", "unchanged", "terminal", "error"}


# 5. mlb_crps + soccer_chain wired shadows (both provisionals M09 now carries) ---
def test_mlb_crps_shadow_promotes_when_new_files_reach_min_n(tmp_path):
    import pytest
    from scripts.platformkit.autoloop import shadow_settle_wired as SSW
    baseline = SSW._mlb_crps_baseline()
    if baseline is None:
        pytest.skip("no real crps_market/last_run_ingame_mlb.json baseline on this box")
    led, spath, groot, _lp = _env(tmp_path, [], [])
    out = SSJ.run_shadow_settle({}, ledgers=led, shadow_path=spath, grade_root=groot,
                                rung8_join_fn=_NO_RUNG8,
                                mlb_crps_n_avail_fn=lambda: baseline["n_game_files"] + baseline["min_n"],
                                soccer_eligible_n_fn=lambda: 0)
    assert out["mlb_crps"]["status"] == "ticked" and out["mlb_crps"]["powered"] is True
    kinds = {r["kind"] for r in _shadow_rows(spath) if r["key"] == SSW.MLB_CRPS_KEY[1]}
    assert kinds == {"SHADOW_TICK", "PROMOTE_CANDIDATE"}
    promo = [r for r in _shadow_rows(spath) if r["kind"] == "PROMOTE_CANDIDATE" and r["key"] == SSW.MLB_CRPS_KEY[1]]
    assert "stays human" in promo[0]["note"]


def test_soccer_chain_shadow_underpowered_with_no_new_matches(tmp_path):
    import pytest
    from scripts.platformkit.autoloop import shadow_settle_wired as SSW
    baseline = SSW._soccer_chain_baseline()
    if baseline is None:
        pytest.skip("no real soccer_chain_engine_v1_full_power.json baseline on this box")
    led, spath, groot, _lp = _env(tmp_path, [], [])
    out = SSJ.run_shadow_settle({}, ledgers=led, shadow_path=spath, grade_root=groot,
                                rung8_join_fn=_NO_RUNG8,
                                mlb_crps_n_avail_fn=lambda: 0,
                                soccer_eligible_n_fn=lambda: baseline["n_matches_total"])
    assert out["soccer_chain"]["status"] == "ticked" and out["soccer_chain"]["powered"] is False
    kinds = {r["kind"] for r in _shadow_rows(spath) if r["key"] == SSW.SOCCER_CHAIN_KEY[1]}
    assert kinds == {"SHADOW_TICK"}


def test_wired_shadows_real_smoke(tmp_path):
    """Real artifact paths (no injection): must never raise out of the job."""
    led, spath, groot, _lp = _env(tmp_path, [], [])
    out = SSJ.run_shadow_settle({}, ledgers=led, shadow_path=spath, grade_root=groot)
    assert out["mlb_crps"]["status"] in {"ticked", "unchanged", "terminal", "no_baseline", "error"}
    assert out["soccer_chain"]["status"] in {"ticked", "unchanged", "terminal", "no_baseline", "error"}
