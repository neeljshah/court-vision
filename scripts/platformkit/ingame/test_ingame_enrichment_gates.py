"""Per-file tests for ingame_enrichment_gates (GATE A: soccer xG conditioning
judge + shared Brier-delta core).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_enrichment_gates.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame import ingame_enrichment_gates as g


def _rows_better(n_games: int = 40, ticks_per_game: int = 10):
    """Synthetic rows where the enriched model is CLEARLY better calibrated
    (enriched prob near truth, baseline biased away) for every game -- should
    yield BETTER_THAN_BASELINE in both md5 halves given enough games."""
    rows = []
    for i in range(n_games):
        gid = "game_%d" % i
        y = 1.0 if i % 2 == 0 else 0.0
        for _t in range(ticks_per_game):
            rows.append({
                "game_id": gid, "y": y,
                "model_prob": 0.5,          # baseline: uninformative
                "model_prob_enriched": (0.9 if y == 1.0 else 0.1),  # enriched: near-truth
            })
    return rows


def _rows_worse(n_games: int = 40, ticks_per_game: int = 10):
    """Enriched model WORSE than baseline (biased away from truth)."""
    rows = []
    for i in range(n_games):
        gid = "game_%d" % i
        y = 1.0 if i % 2 == 0 else 0.0
        for _t in range(ticks_per_game):
            rows.append({
                "game_id": gid, "y": y,
                "model_prob": (0.9 if y == 1.0 else 0.1),  # baseline: near-truth
                "model_prob_enriched": 0.5,                 # enriched: uninformative
            })
    return rows


def test_judge_enrichment_better_both_halves():
    judged = g.judge_enrichment(_rows_better())
    assert judged["overall_verdict"] == "BETTER_THAN_BASELINE"
    assert judged["half0"]["verdict"] == "BETTER_THAN_BASELINE"
    assert judged["half1"]["verdict"] == "BETTER_THAN_BASELINE"


def test_judge_enrichment_worse_flags_worse():
    judged = g.judge_enrichment(_rows_worse())
    assert judged["overall_verdict"] == "WORSE_THAN_BASELINE"


def test_judge_enrichment_insufficient_below_min_games():
    judged = g.judge_enrichment(_rows_better(n_games=2, ticks_per_game=5))
    assert judged["overall_verdict"] == "INSUFFICIENT_FORWARD"


def test_judge_enrichment_skips_rows_missing_enriched_field():
    """A row with model_prob_enriched=None (honest gap, e.g. pre-integration
    or a fetch/match miss) must be SKIPPED, never imputed to 0 or baseline."""
    rows = [{"game_id": "g1", "y": 1.0, "model_prob": 0.5, "model_prob_enriched": None}] * 50
    judged = g.judge_enrichment(rows)
    assert judged["n_ticks"] == 0
    assert judged["overall_verdict"] == "INSUFFICIENT_FORWARD"


def test_run_gate_a_writes_pending_when_no_rows(tmp_path):
    """No production row source exists yet (fotmob join is a future lane) --
    run_gate_a must honestly emit PENDING/INSUFFICIENT with n=0, never fabricate."""
    out = tmp_path / "verdict.json"
    doc = g.run_gate_a(rows_fn=lambda: [], verdict_out=out)
    assert doc["verdict"] == "INSUFFICIENT_FORWARD"
    assert doc["n_games"] == 0
    assert doc["edge_claimed"] is False
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk["gate"] == "A_soccer_xg"
    assert on_disk["pre_registered_at"] == g.GATE_A_PRE_REGISTERED_AT
    assert on_disk["edge_claimed"] is False


def test_run_gate_a_default_rows_fn_never_raises_and_is_a_list():
    """LANE 4: the real default row source is now wired to
    enrichment_rows_soccer.build_rows (an as-of join over real captured
    data). It must never raise and must always return a list -- real
    overlap between soccer_intl grade ticks and fotmob sidecars may be
    thin or zero right now, so this does NOT assert emptiness, only the
    never-raises/list-shape contract."""
    rows = g._default_rows_soccer_xg()
    assert isinstance(rows, list)


def test_pre_registered_at_stamp_is_frozen_before_data_existed():
    """Binding invariant: the stamp is a frozen string constant, not derived
    from wall-clock time (so re-importing this module never re-stamps it)."""
    assert g.GATE_A_PRE_REGISTERED_AT == "2026-07-05T04:00:00Z"


def test_run_gate_a_confirmed_with_synthetic_better_rows(tmp_path):
    out = tmp_path / "verdict.json"
    doc = g.run_gate_a(rows_fn=_rows_better, verdict_out=out)
    assert doc["verdict"] == "BETTER_THAN_BASELINE"
    assert doc["n_games"] > 0
