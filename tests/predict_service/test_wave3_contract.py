"""Per-file tests: WAVE 3 prediction contract -- additive/non-breaking + honesty.

Run: python -m pytest tests/predict_service/test_wave3_contract.py -q

Covers:
  * contract bump 1.0.0 -> 1.1.0 is ADDITIVE (every 1.0.0 field intact, a 1.0.0
    snapshot round-trips, a 1.1.0 envelope parses under an old reader).
  * EdgeRow gains vs_close defaulting UNPROVEN (never PROVEN by default).
  * a merged number carries a PHASE label (phase='merged'), NOT a silent average.
  * the interval comes from HELD-OUT residuals only (None without them; widens
    with dispersion; leak-free).
  * NO $ / dollar / roi / pnl key anywhere on the new shapes.
"""
from __future__ import annotations

import json

from predict_service import attribution, phase_merge, surface, uncertainty
from predict_service.contracts import (
    PHASE_MERGED,
    PHASE_PREGAME,
    SCHEMA_VERSION,
    VS_CLOSE_PROVEN,
    VS_CLOSE_UNPROVEN,
    EdgeRow,
    Interval,
    ProbEstimate,
    Provenance,
    SnapshotEnvelope,
)


# --------------------------------------------------------------------------- #
# 1. Contract is additive / non-breaking.
# --------------------------------------------------------------------------- #
def test_schema_version_bumped_to_1_1_0():
    assert SCHEMA_VERSION == "1.1.0"


def test_edgerow_existing_fields_intact():
    """Every 1.0.0 EdgeRow field still exists and round-trips unchanged."""
    e = EdgeRow(game_id="g1", market_type="moneyline", side="home",
                model_prob=0.58, market_prob=0.52, ev=0.11, tier="B",
                book="bk", line=None, clv_is_proxy=True)
    d = e.to_dict()
    for k in ("game_id", "market_type", "side", "model_prob", "market_prob",
              "ev", "tier", "book", "line", "clv_is_proxy"):
        assert k in d
    assert EdgeRow.from_dict(d) == e


def test_edgerow_vs_close_defaults_unproven():
    e = EdgeRow(game_id="g", market_type="moneyline", side="home",
                model_prob=0.5, market_prob=0.5, ev=0.0)
    assert e.vs_close == VS_CLOSE_UNPROVEN
    # An unknown vs_close on read degrades to UNPROVEN, never PROVEN.
    e2 = EdgeRow.from_dict({"game_id": "g", "market_type": "moneyline",
                            "side": "home", "model_prob": 0.5,
                            "market_prob": 0.5, "ev": 0.0, "vs_close": "BOGUS"})
    assert e2.vs_close == VS_CLOSE_UNPROVEN


def test_old_reader_parses_new_envelope():
    """A 1.0.0-shaped reader (extra keys ignored) still parses a 1.1.0 envelope."""
    env = SnapshotEnvelope(sport="nba", generated_at="2026-06-19T00:00:00+00:00",
                           edges=[EdgeRow(game_id="g", market_type="moneyline",
                                          side="home", model_prob=0.5,
                                          market_prob=0.5, ev=0.0,
                                          vs_close=VS_CLOSE_PROVEN)])
    blob = json.dumps(env.to_dict())
    again = SnapshotEnvelope.from_dict(json.loads(blob))
    assert again == env
    # vs_close survives a true round-trip.
    assert again.edges[0].vs_close == VS_CLOSE_PROVEN


def test_v1_0_0_snapshot_round_trips_with_defaults():
    """A snapshot written WITHOUT vs_close (a 1.0.0 producer) parses cleanly."""
    raw = {
        "schema_version": "1.0.0", "sport": "nba",
        "generated_at": "2026-06-18T00:00:00+00:00", "status": "ok",
        "edges": [{"game_id": "g", "market_type": "moneyline", "side": "home",
                   "model_prob": 0.55, "market_prob": 0.5, "ev": 0.1}],
    }
    env = SnapshotEnvelope.from_dict(raw)
    assert env.status == "ok"
    assert env.edges[0].vs_close == VS_CLOSE_UNPROVEN  # additive default applied


# --------------------------------------------------------------------------- #
# 2. ProbEstimate / Provenance / Interval round-trip.
# --------------------------------------------------------------------------- #
def test_probestimate_round_trip():
    est = ProbEstimate(label="home_ml", prob=0.58,
                       provenance=Provenance(model="mc_sim", calibration="platt",
                                             phase=PHASE_PREGAME),
                       interval=Interval(lo=0.5, hi=0.66), side="home")
    again = ProbEstimate.from_dict(est.to_dict())
    assert again == est


def test_probestimate_interval_optional():
    est = ProbEstimate(label="home_ml", prob=0.6)
    d = est.to_dict()
    assert d["interval"] is None
    assert ProbEstimate.from_dict(d) == est


# --------------------------------------------------------------------------- #
# 3. A merged number is LABELLED by phase, never a silent average.
# --------------------------------------------------------------------------- #
def test_merged_carries_phase_label_not_average():
    pregame, ingame = 0.40, 0.72
    est = phase_merge.merged_estimate("home_ml", pregame, ingame)
    assert est is not None
    assert est.provenance.phase == PHASE_MERGED
    assert phase_merge.is_merged(est)
    # The merged number is the in-game (served) number, NOT the mean of the two.
    assert est.prob == 0.72
    assert est.prob != round((pregame + ingame) / 2.0, 6)


def test_pregame_only_is_not_labelled_merged():
    est = phase_merge.merged_estimate("home_ml", 0.55, None)
    assert est is not None
    assert est.provenance.phase == PHASE_PREGAME
    assert not phase_merge.is_merged(est)


def test_no_pregame_no_ingame_returns_none():
    assert phase_merge.merged_estimate("home_ml", None, None) is None


def test_attribution_phase_guarded():
    prov = attribution.provenance_for(model="m", phase="garbage")
    assert prov.phase == PHASE_PREGAME  # unknown phase -> pregame, never merged


# --------------------------------------------------------------------------- #
# 4. Interval is from HELD-OUT residuals only (leak-free).
# --------------------------------------------------------------------------- #
def test_interval_none_without_residuals():
    assert uncertainty.interval_from_residuals(0.5, None) is None
    assert uncertainty.interval_from_residuals(0.5, []) is None
    assert uncertainty.interval_from_residuals(0.5, [0.0, 0.0]) is None  # < min N


def test_interval_from_heldout_residuals():
    resid = [-0.2, -0.1, -0.05, 0.0, 0.0, 0.05, 0.1, 0.2, 0.15, -0.15]
    itv = uncertainty.interval_from_residuals(0.5, resid, level=0.80)
    assert itv is not None
    assert itv.method == "heldout_residual_quantile"
    assert 0.0 <= itv.lo <= 0.5 <= itv.hi <= 1.0


def test_interval_widens_with_dispersion():
    tight = [-0.02, -0.01, 0.0, 0.0, 0.0, 0.01, 0.02, 0.015, -0.015, 0.005]
    wide = [-0.3, -0.2, -0.1, 0.0, 0.0, 0.1, 0.2, 0.3, 0.25, -0.25]
    it_t = uncertainty.interval_from_residuals(0.5, tight)
    it_w = uncertainty.interval_from_residuals(0.5, wide)
    assert (it_w.hi - it_w.lo) > (it_t.hi - it_t.lo)


def test_interval_clamped_to_unit():
    resid = [0.4, 0.5, 0.6, 0.45, 0.55, 0.5, 0.48, 0.52, 0.5, 0.5]
    itv = uncertainty.interval_from_residuals(0.9, resid)
    assert itv is not None
    assert itv.hi <= 1.0 and itv.lo >= 0.0


# --------------------------------------------------------------------------- #
# 5. NO $ key anywhere on the new shapes.
# --------------------------------------------------------------------------- #
def _all_keys(obj):
    keys = set()

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                keys.add(str(k).lower())
                walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)
    walk(obj)
    return keys


def test_no_dollar_key_on_new_shapes():
    est = ProbEstimate(label="home_ml", prob=0.58,
                       provenance=Provenance(model="mc_sim", phase=PHASE_MERGED),
                       interval=Interval(lo=0.5, hi=0.66))
    keys = _all_keys(est.to_dict())
    for banned in ("pnl", "roi", "bankroll", "profit", "dollar", "dollars",
                   "usd", "stake", "edge"):
        assert banned not in keys, "banned $ key %r present" % banned


def test_surface_no_dollar_key_and_units_only():
    """build_surface output (even on an empty/unavailable store) carries no $ key."""
    body = surface.build_surface("nba", out_dir="__nonexistent_store_dir__")
    keys = _all_keys(body)
    for banned in ("pnl", "roi", "bankroll", "profit", "dollar", "dollars",
                   "usd", "stake"):
        assert banned not in keys
    assert body["edge_claimed"] is False
    assert body["real_money_enabled"] is False
