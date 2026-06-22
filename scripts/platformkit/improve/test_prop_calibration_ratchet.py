"""Per-file tests for prop_calibration_ratchet (the PROPS calibration ratchet).

Proves the eval-gate machinery on synthetic settled-prop corpora:
  * load filters to PROPS ONLY (a game-ML row is invisible),
  * an INFORMATIVE but mis-calibrated (logit-shifted) prop model -> isotonic recal
    SHIPs (DM-significant, no regression) and the PLANTED NULL does NOT ship,
  * a corpus whose only "gain" is base-rate fitting (uninformative raw) -> the PLANTED
    NULL ships -> the cycle is REJECTED (the gate's overfit tripwire fires),
  * a well-calibrated model -> HOLD,
  * too few settled props -> INSUFFICIENT_DATA,
  * STRUCTURAL market-follow impossibility: the SHIP verdict + recal Brier are INVARIANT
    to market_prob (even an ORACLE market = the realized outcome changes nothing); the
    shrink-toward-market value is RECORDED as a transparency control but NEVER shipped.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/improve/test_prop_calibration_ratchet.py -q
"""
from __future__ import annotations

import json
import math
import random

import scripts.platformkit.improve.prop_calibration_ratchet as R


# --- synthetic corpus builders ---------------------------------------------

def _logit(p: float) -> float:
    return math.log(p / (1.0 - p))


def _sig(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def _row(sport, i, model_prob, market_prob, win):
    return {
        "sport": sport, "market_type": "prop", "status": "settled",
        "model_prob": round(float(model_prob), 6),
        "market_prob": (round(float(market_prob), 6) if market_prob is not None else None),
        "outcome": "win" if win else "loss",
        "ts": "2000-01-01T00:00:00.%06d" % i,  # zero-padded -> chronological string sort
        "bet_id": "prop|%s|%d" % (sport, i),
        "market": "prop|p%d|H|1.5|over" % i,
    }


def _biased(n, *, c=0.7, seed=0, market="true", sport="mlb"):
    """Informative model with a systematic, REMOVABLE logit-shift mis-calibration.
    The model still ranks correctly (better than a constant -> null can't ship) but the
    shift costs Brier; isotonic recal removes it -> a real, DM-significant SHIP.

    *market* only rewrites market_prob; the (t, model_prob, outcome) stream is IDENTICAL
    across modes (a separate RNG draws the noise market) so the recal -- which never
    reads market_prob -- is bit-identical across modes (used by the invariance test)."""
    rng = random.Random(seed)
    noise_rng = random.Random(seed + 101)   # independent -> never perturbs t/win/m
    rows = []
    for i in range(n):
        t = rng.uniform(0.12, 0.88)
        m = _sig(_logit(t) + c)            # monotone, informative, mis-calibrated
        win = 1 if rng.random() < t else 0
        noise_mp = noise_rng.random()      # drawn every row regardless of mode
        if market == "true":
            mp = t
        elif market == "oracle":
            mp = float(win)                # would massively help IF it leaked
        elif market == "noise":
            mp = noise_mp
        else:
            mp = None
        rows.append(_row(sport, i, m, mp, win))
    return rows


def _uninformative(n, *, base=0.72, seed=1, sport="mlb"):
    """Constant raw=0.5 (no info); any 'gain' is base-rate fitting -> planted null ships."""
    rng = random.Random(seed)
    return [_row(sport, i, 0.5, 0.5, 1 if rng.random() < base else 0) for i in range(n)]


def _calibrated(n, *, seed=2, sport="mlb"):
    """Well-calibrated near-0.5 discrete model -> nothing to fix -> HOLD."""
    rng = random.Random(seed)
    levels = [0.4, 0.5, 0.6]
    rows = []
    for i in range(n):
        t = rng.choice(levels)
        win = 1 if rng.random() < t else 0
        rows.append(_row(sport, i, t, t, win))
    return rows


def _write(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _run(tmp_path, rows, **kw):
    clv = tmp_path / "clv.jsonl"
    led = tmp_path / "prop_improve.jsonl"
    _write(clv, rows)
    return R.improve_cycle("mlb", clv_path=clv, ledger_path=led, **kw)


# --- load + readout --------------------------------------------------------

def test_load_filters_to_props_only(tmp_path):
    clv = tmp_path / "clv.jsonl"
    rows = [
        {"sport": "mlb", "market_type": "moneyline", "status": "settled",
         "model_prob": 0.6, "outcome": "win", "ts": "2000-01-01T00:00:00.000001"},
        _row("mlb", 1, 0.7, 0.6, 1),
    ]
    _write(clv, rows)
    out = R.load_settled_props("mlb", clv_path=clv)
    assert len(out) == 1
    assert out[0]["p_raw"] == 0.7 and out[0]["y"] == 1 and out[0]["p_market"] == 0.6


def test_readout_shapes_and_market_compare(tmp_path):
    clv = tmp_path / "clv.jsonl"
    _write(clv, _biased(80, seed=5))
    settled = R.load_settled_props("mlb", clv_path=clv)
    ro = R.honest_readout(settled)
    assert ro["n"] == 80 and ro["n_with_market"] == 80
    assert ro["raw_brier"] is not None and ro["market_brier"] is not None
    assert "calibration" in ro["note"]


# --- the ratchet verdicts --------------------------------------------------

def test_miscalibrated_model_ships_and_null_rejects(tmp_path):
    rec = _run(tmp_path, _biased(1500, c=0.7, seed=10), append=False)
    assert rec["verdict"] == "SHIP", rec.get("reason")
    assert rec["delta_brier"] > R.BRIER_IMPROVE_TOL
    assert rec["null_shipped"] is False            # planted null correctly rejected
    assert rec["dm_p"] < 0.05 and rec["dm_n"] >= 200


def test_base_rate_only_gain_trips_planted_null_reject(tmp_path):
    rec = _run(tmp_path, _uninformative(400, base=0.72, seed=3), append=False)
    assert rec["null_shipped"] is True             # null ships on a non-signal "gain"
    assert rec["verdict"] == "REJECT"
    assert "PLANTED NULL" in rec["reason"]


def test_well_calibrated_model_holds(tmp_path):
    rec = _run(tmp_path, _calibrated(900, seed=4), append=False)
    assert rec["verdict"] == "HOLD", rec.get("reason")
    assert rec["null_shipped"] is False


def test_cold_start_insufficient_data(tmp_path):
    rec = _run(tmp_path, _biased(10, seed=6), append=False)
    assert rec["verdict"] == "INSUFFICIENT_DATA"
    assert rec["n_settled"] == 10


# --- structural: the market-follow trap is impossible ----------------------

def test_ship_verdict_invariant_to_market_prob(tmp_path):
    """The shipped (recal) forecaster never reads market_prob -> SHIP verdict + recal
    Brier are IDENTICAL whether the market is the truth, an oracle (= realized outcome),
    or pure noise. The structural proof that market-following cannot influence what ships."""
    r_t = _run(tmp_path, _biased(1500, c=0.7, seed=20, market="true"), append=False)
    r_o = _run(tmp_path, _biased(1500, c=0.7, seed=20, market="oracle"), append=False)
    r_n = _run(tmp_path, _biased(1500, c=0.7, seed=20, market="noise"), append=False)
    assert r_t["verdict"] == r_o["verdict"] == r_n["verdict"] == "SHIP"
    assert r_t["recal_brier"] == r_o["recal_brier"] == r_n["recal_brier"]
    assert r_t["delta_brier"] == r_o["delta_brier"] == r_n["delta_brier"]


def test_market_shrink_is_recorded_but_never_shipped(tmp_path):
    """The shrink-toward-market value is RECORDED as a transparency control, but the
    SHIPPED candidate (recal) is computed without market info -> its Brier is invariant
    whether the market is present or stripped entirely."""
    rec = _run(tmp_path, _biased(1500, c=0.7, seed=21, market="true"), append=False)
    assert "market_shrink_brier" in rec and "market_shrink_delta_brier" in rec
    assert isinstance(rec["market_follow_safe"], bool)
    stripped = _run(tmp_path, _biased(1500, c=0.7, seed=21, market="none"), append=False)
    assert rec["recal_brier"] == stripped["recal_brier"]
    assert rec["verdict"] == stripped["verdict"] == "SHIP"


# --- ledger + multi-sport --------------------------------------------------

def test_append_writes_verdict_row(tmp_path):
    clv = tmp_path / "clv.jsonl"
    led = tmp_path / "prop_improve.jsonl"
    _write(clv, _biased(80, seed=7))
    R.improve_cycle("mlb", clv_path=clv, ledger_path=led, append=True)
    lines = [json.loads(x) for x in led.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(lines) == 1 and lines[0]["sport"] == "mlb"
    assert lines[0]["market_type"] == "prop"


def test_improve_all_covers_every_prop_sport(tmp_path):
    clv = tmp_path / "clv.jsonl"
    led = tmp_path / "prop_improve.jsonl"
    _write(clv, [])  # no props anywhere
    summary = R.improve_all(clv_path=clv, ledger_path=led, append=False)
    assert set(summary["verdicts"]) == set(R.PROP_SPORTS)
    assert all(v == "INSUFFICIENT_DATA" for v in summary["verdicts"].values())
