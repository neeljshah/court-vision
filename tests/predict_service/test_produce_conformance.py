"""predict_service leak-guard / eval-gate conformance test (honesty-critical).

Proves the NBA producer's PREGAME output is (a) structurally leak-free, (b) a
VERBATIM passthrough of the underlying build_result -- the producer introduces no
transform that could silently drift or leak a number -- and (c) consistent with
the eval-gate's leak-free contract, to the extent that contract is reachable
OFFLINE.

WHAT IS ASSERTED (real, offline, no network):
  * Every PredictionRecord.leak_guard == {"in_sample": False}: these are forward,
    out-of-sample predictions, never flagged in-sample.
  * pregame probs equal what build_result returned for the SAME inputs (verbatim;
    a controlled fake build_result lets us assert exact equality with no engine).
  * The eval-gate's OWN leak guard is live and enforcing: validate_golden passes
    on the frozen golden fixture, FIRES on an injected vintage leak, and the
    offline gate run is green with leaked=False on every scored corpus. The
    producer's in_sample=False stance is the same leak-free posture the gate
    enforces (no future-dated feature reaches a forward prediction).

WHAT IS HONESTLY SKIPPED (no fabrication, no false green):
  * A direct NUMERIC match of the producer's probabilities against the gate's
    scored golden reference. The gate scores a SYNTHETIC golden corpus over a
    DISJOINT feature space (strength/rest/home_edge) with no team-matchup entry
    point reachable offline; its real numeric forecaster is the --corpus /
    proof_nba path that needs heavy data (no network here). Feeding the
    producer's live matchups "through the gate" to compare numbers would require
    that heavy path -- so any numeric tolerance check here would be fabricated.
    We therefore assert the STRUCTURAL leak-free invariants both share and
    explicitly skip the heavy numeric comparison with this reason.

Per-file run only:
    python -m pytest tests/predict_service/test_produce_conformance.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest

from predict_service import produce, store
from predict_service.assemble import model_probs_from_pregame, pregame_probs_record

# The fake games tip on 2026-06-18/19; pin *now* just after the later tip so the
# stale-drop keeps this a live slate regardless of the real wall clock (these
# tests assert leak-free shape, not stale-drop timing).
_FIXED_NOW = datetime(2026, 6, 19, 2, 0, 0, tzinfo=timezone.utc)

# --- controlled offline build_result -------------------------------------- #
# Two NBA games with hand-set pregame probabilities. Because the producer copies
# the pregame block VERBATIM, the stored numbers must equal these exactly.
_GAMES = {
    ("Boston Celtics", "Los Angeles Lakers"): {"p_home_win": 0.6123, "p_away_win": 0.3877},
    ("Denver Nuggets", "Miami Heat"): {"p_home_win": 0.5410, "p_away_win": 0.4590},
}


def _fake_odds(sport: str) -> Dict[str, Any]:
    return {
        "sport": sport, "status": "ok", "as_of": "2026-06-18T18:00:00+00:00",
        "sources": {"fakebook": "ok"},
        "events": [
            {
                "event_id": "G1", "sport": sport,
                "home": "Boston Celtics", "away": "Los Angeles Lakers",
                "commence_time": "2026-06-18T23:30:00Z",
                "prices": {"bookA": {"home": 1.62, "away": 2.45, "draw": None}},
            },
            {
                "event_id": "G2", "sport": sport,
                "home": "Denver Nuggets", "away": "Miami Heat",
                "commence_time": "2026-06-19T01:00:00Z",
                "prices": {"bookA": {"home": 1.85, "away": 2.05, "draw": None}},
            },
        ],
    }


def _fake_schedule(sport: str) -> List[Dict[str, Any]]:
    return produce.games_from_odds(_fake_odds(sport))


def _fake_predict(sport: str, home: str, away: str) -> Dict[str, Any]:
    """Controlled build_result-shaped output for one matchup (no engine, offline)."""
    pre = dict(_GAMES[(home, away)])
    pre["honest_note"] = "calibration only; no $ edge"
    return {"sport": sport, "home": home, "away": away,
            "edge_claimed": False, "pregame": pre}


def _build():
    return produce.produce_sport(
        "nba", schedule_feed=_fake_schedule, odds_feed=_fake_odds,
        predict_fn=_fake_predict, now=_FIXED_NOW)


# --- (a) leak guard: every record is forward / OOS, never in-sample -------- #
def test_every_record_leak_guard_in_sample_false():
    env = _build()
    assert env.status == "ok" and env.predictions
    for rec in env.predictions:
        assert rec.leak_guard == {"in_sample": False}, rec.game_id


# --- (b) pregame probs equal build_result VERBATIM (no producer transform) -- #
def test_pregame_probs_equal_build_result_verbatim():
    env = _build()
    by_game = {(p.home, p.away): p for p in env.predictions}
    assert set(by_game) == set(_GAMES), "every fed matchup must produce a record"
    for (home, away), pre in _GAMES.items():
        rec = by_game[(home, away)]
        src = _fake_predict("nba", home, away)["pregame"]
        # the producer's record probs are exactly what assemble derives from the
        # SAME source block -- byte-for-byte, no transform introduced en route.
        assert rec.pregame_probs == pregame_probs_record(src), rec.game_id
        assert rec.pregame_probs["home_ml"] == pre["p_home_win"]
        assert rec.pregame_probs["away_ml"] == pre["p_away_win"]
        # edge model_prob on each side is the verbatim source prob too (no drift).
        src_probs = model_probs_from_pregame(src)
        for e in [e for e in env.edges if e.game_id == rec.game_id]:
            assert e.model_prob == round(float(src_probs[e.side]), 6), e.side


# --- leak-free posture survives the store round-trip ----------------------- #
def test_leak_guard_survives_store_round_trip(tmp_path):
    env = _build()
    store.save(env, out_dir=str(tmp_path))
    loaded = store.read_latest("nba", out_dir=str(tmp_path))
    assert loaded.status == "ok" and loaded.predictions
    for rec in loaded.predictions:
        assert rec.leak_guard == {"in_sample": False}, rec.game_id
    # no future-dated / fabricated field leaks onto an edge through persistence.
    for e in loaded.edges:
        d = e.to_dict()
        for banned in ("$edge", "dollar", "roi", "profit", "in_sample"):
            assert banned not in d


# --- (c) consistency with the eval-gate's LEAK-FREE contract (offline) ----- #
def _gate_modules():
    """Import the offline gate core, or skip if the editable install is absent."""
    try:
        from scripts.platformkit.eval_gate.golden_loader import load_golden
        from scripts.platformkit.eval_gate.schema import validate_golden
        from scripts.platformkit.eval_gate.run_gate import (
            run_gate_in_process, gate_exit_code)
        from scripts.platformkit.eval_gate.offline_predict import offline_predict_fn
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"eval gate not importable offline: {exc}")
    return (load_golden, validate_golden, run_gate_in_process,
            gate_exit_code, offline_predict_fn)


def test_eval_gate_leak_guard_is_live_and_green():
    """The gate we conform to is itself leak-enforcing AND green offline.

    This is the structural half of (c): we prove the gate's leak-free contract
    holds (validate_golden enforces vintage; the offline run is green with no
    leak). The producer's in_sample=False stance is the SAME leak-free posture.
    """
    (load_golden, validate_golden, run_gate_in_process,
     gate_exit_code, offline_predict_fn) = _gate_modules()

    states = load_golden()
    validate_golden(states)  # frozen golden fixture is leak-free + covers regimes

    # the gate's leak guard FIRES on an injected vintage leak (avail >= state_ts).
    bad = [dict(s) for s in states]
    bad[0] = dict(bad[0])
    bad[0]["feature_avail"] = dict(bad[0]["feature_avail"])
    a_feat = next(iter(bad[0]["feature_avail"]))
    bad[0]["feature_avail"][a_feat] = "2999-01-01T00:00:00"
    with pytest.raises(AssertionError) as ei:
        validate_golden(bad)
    assert "LEAK" in str(ei.value)

    # the offline gate is GREEN (exit 0) with leaked=False on every scored corpus.
    rows = run_gate_in_process(offline_predict_fn)
    assert gate_exit_code(rows) == 0
    scored = [r for r in rows if "n" in r]
    assert scored, "expected at least one scored corpus offline"
    for r in scored:
        assert r.get("leaked") is False, r["corpus"]


def test_producer_record_carries_no_leaky_vintage_field():
    """The producer's records never carry a future-dated feature/vintage that the
    gate's validate_golden would reject -- the structural analog of the gate's
    leak guard applied to producer output (it stores only a tipoff/produced_at and
    an in_sample flag, no feature_avail that could post-date the prediction)."""
    env = _build()
    for rec in env.predictions:
        d = rec.to_dict()
        # produced/tipoff are timestamps, not future-dated FEATURE-availability;
        # there is no feature_avail map on a record to violate the leak guard.
        assert "feature_avail" not in d
        assert d["leak_guard"] == {"in_sample": False}


def test_heavy_numeric_gate_match_is_honestly_skipped():
    """(c) numeric half -- SKIPPED with an explicit, honest reason.

    A direct numeric match of the producer's probabilities against the gate's
    scored reference is NOT honestly reachable offline: the gate scores a
    SYNTHETIC golden corpus over a disjoint feature space (strength/rest/
    home_edge) with no team-matchup entry point, and its real numeric forecaster
    is the --corpus / proof_nba path needing heavy data + network. Feeding the
    producer's live matchups through that path to compare numbers within a
    tolerance would be FABRICATED here. We assert the shared STRUCTURAL leak-free
    invariants (above) instead and skip the heavy comparison -- never a false
    green.
    """
    pytest.skip(
        "heavy numeric producer-vs-gate match needs the --corpus/proof_nba path "
        "(heavy data + network) over a feature space disjoint from the golden "
        "fixture; structural leak-free invariants asserted instead -- no fabrication")


if __name__ == "__main__":
    test_every_record_leak_guard_in_sample_false()
    test_pregame_probs_equal_build_result_verbatim()
    test_producer_record_carries_no_leaky_vintage_field()
    print("structural conformance checks passed (run under pytest for skips).")
