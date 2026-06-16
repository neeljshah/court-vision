"""Per-file tests for market_coverage.calibrate -- the per-market calibration engine.

Run ONLY this file (the full suite freezes the box):
  python -m pytest scripts/platformkit/market_coverage/test_calibrate.py -q

Guards the HONEST RAILS: no fabricated survivor on a matched close, BSS/DM gate the
beat verdict, price-only markets are CALIBRATED + needs-forward-CLV, and reliability
bins partition the predictions.
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.market_coverage import calibrate as C


def test_reliability_bins_partition():
    rng = np.random.default_rng(0)
    p = rng.uniform(size=500)
    y = (rng.uniform(size=500) < p).astype(float)
    rows = C.reliability_bins(p, y)
    assert sum(r["n"] for r in rows) == 500          # every prediction in exactly one bin
    for r in rows:
        assert 0.0 <= r["pred"] <= 1.0 and 0.0 <= r["obs"] <= 1.0
        assert r["sparse"] == (r["n"] < C.SPARSE_N)


def test_matched_close_is_efficient_not_a_survivor():
    """A well-calibrated model vs an equally-sharp close must read MARKET-EFFICIENT
    HERE -- never a fabricated SUGGESTIVE/edge survivor."""
    rng = np.random.default_rng(3)
    n = 400
    truth = rng.uniform(0.05, 0.95, n)
    y = (rng.uniform(size=n) < truth).astype(float)
    pm = np.clip(truth + rng.normal(0, 0.03, n), 1e-3, 1 - 1e-3)
    pc = np.clip(truth + rng.normal(0, 0.03, n), 1e-3, 1 - 1e-3)
    r = C.calibrate_market("test/ml", C.LIQ_LIQUID, pm, y, pc)
    assert r["edge_claimed"] is False
    assert r["verdict"] in (C.V_EFFICIENT, C.V_BEHIND)   # match or honest trail, never a beat
    assert abs(r["bss_vs_close"]) < 0.15                  # close to the close, not a blowout


def test_beat_requires_full_bar():
    """A genuinely sharper model on a soft line -> SUGGESTIVE, and ALWAYS flagged
    needs-forward-CLV (never a $ claim). Requires power + significance + lower Brier."""
    rng = np.random.default_rng(11)
    n = 600
    truth = rng.uniform(0.05, 0.95, n)
    y = (rng.uniform(size=n) < truth).astype(float)
    pm = np.clip(truth + rng.normal(0, 0.02, n), 1e-3, 1 - 1e-3)   # sharp model
    pc = np.full(n, float(y.mean()))                               # soft close = base rate
    r = C.calibrate_market("test/soft", C.LIQ_THIN, pm, y, pc)
    assert r["bss_vs_close"] > 0 and r["dm_clusters"] >= C.MIN_CLUSTERS
    assert r["verdict"] == C.V_SUGGESTIVE
    assert C.FLAG_FWD_CLV in r["flags"]                            # never a bare $ claim
    assert r["edge_claimed"] is False


def test_underpowered_beat_does_not_survive():
    """Same sharper model but too few clusters -> NOT a survivor (ABSTAIN/EFFICIENT),
    because the DM bar (N>=MIN_CLUSTERS) is not met."""
    rng = np.random.default_rng(11)
    n = 40
    truth = rng.uniform(0.05, 0.95, n)
    y = (rng.uniform(size=n) < truth).astype(float)
    pm = np.clip(truth + rng.normal(0, 0.02, n), 1e-3, 1 - 1e-3)
    pc = np.full(n, float(y.mean()))
    r = C.calibrate_market("test/thin", C.LIQ_THIN, pm, y, pc)
    assert r["dm_clusters"] < C.MIN_CLUSTERS
    assert r["verdict"] != C.V_SUGGESTIVE                          # cannot claim on tiny N


def test_price_only_market_is_calibrated_pending():
    """No local close -> CALIBRATED (no close to beat) + VALIDATION_PENDING + needs CLV."""
    rng = np.random.default_rng(5)
    n = 200
    pm = rng.uniform(0.05, 0.95, n)
    y = (rng.uniform(size=n) < pm).astype(float)
    r = C.calibrate_market("test/longshot", C.LIQ_NONE, pm, y, p_close=None)
    assert r["data_status"] == C.ST_FWD
    assert r["verdict"] == C.V_CALIB
    assert C.FLAG_FWD_CLV in r["flags"]
    assert "bss_vs_close" not in r                                 # nothing to beat


def test_all_seven_families_enumerated_and_priced():
    assert C.ENUMERATION == [
        "player-props-core", "player-props-combos", "team-quarter-half",
        "game-scenario-longshot", "sgp-correlation", "mlb-soccer-tennis",
        "ingame-micro",
    ]
    results = C.run_all(n=120)
    assert set(results) == set(C.ENUMERATION)
    for fam, rows in results.items():
        assert rows, f"{fam} priced no markets"
        for r in rows:
            assert r["edge_claimed"] is False                     # never a $ claim
            assert r["brier"] is not None
            # price-only families must carry the forward-CLV flag on every row.
            if not C.FAMILIES[fam]["has_local_close"]:
                assert C.FLAG_FWD_CLV in r["flags"]


def test_no_fabricated_survivor_on_fixture():
    """On the committed fixture the close is a genuine forecaster, so NO market may
    read SUGGESTIVE -- the scoreboard must not manufacture an edge."""
    results = C.run_all(n=240)
    survivors = [r for rows in results.values() for r in rows
                 if r["verdict"] == C.V_SUGGESTIVE]
    assert survivors == [], f"fabricated survivor(s): {[s['market'] for s in survivors]}"


def test_scoreboard_renders_ascii():
    lines = C.build_scoreboard(C.run_all(n=120))
    body = "\n".join(lines)
    assert body.isascii()
    assert "MARKET-EFFICIENT HERE" in body
    assert C.FLAG_FWD_CLV in body
    # The retracted numbers must never appear AS VALUES. Match whole tokens, not
    # bare substrings: a legitimate Brier like 0.1193 contains "0.119" as a prefix
    # but is NOT the retracted endQ3 figure, so a substring check false-positives.
    import re
    for bad in ("+18.38", "0.119", "+54", "78.11"):
        assert not re.search(r"(?<![\d.])" + re.escape(bad) + r"(?![\d])", body), \
            f"retracted value {bad!r} appears as a standalone token"
