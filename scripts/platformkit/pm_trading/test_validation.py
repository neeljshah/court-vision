"""Per-file tests for validation.py (the go-live gate harness).

Run: python -m pytest scripts/platformkit/pm_trading/test_validation.py -q
"""
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import validation as V  # noqa: E402


def test_make_scenario_shape_and_determinism():
    cfg = V.ValidationConfig(n_days=5, markets_per_day=4, edge=0.5)
    a = V.make_scenario(cfg)
    b = V.make_scenario(cfg)
    assert len(a) == 5 and all(len(d) == 4 for d in a)
    assert [m.true_prob for d in a for m in d] == [m.true_prob for d in b for m in d]
    # edge>0 => model leans off the line
    assert any(abs(m.model_prob - m.market_price) > 1e-6 for d in a for m in d)


def test_efficient_market_stands_down():
    r = V.run_validation(V.ValidationConfig(edge=0.0, n_days=20, markets_per_day=8))
    assert r["verdict"] == "NO_TRADES"      # model==line -> nothing fires
    assert r["net_paper_pnl"] == 0 and r["n_traded_markets"] == 0


def test_informative_edge_passes():
    r = V.run_validation(V.ValidationConfig(edge=0.6, n_days=20, markets_per_day=8))
    assert r["verdict"] == "PASS"
    assert r["net_paper_pnl"] > 0
    assert r["mean_clv_bps"] > 0 and r["pnl_ci95_low"] > 0
    assert r["n_traded_markets"] >= 30


def test_insufficient_data_when_few_markets():
    r = V.run_validation(V.ValidationConfig(edge=0.6, n_days=2, markets_per_day=3))
    assert r["verdict"] == "INSUFFICIENT_DATA"
    assert 0 < r["n_traded_markets"] < 30


def test_determinism_same_seed():
    c = V.ValidationConfig(edge=0.6, n_days=10, markets_per_day=5)
    assert V.run_validation(c)["net_paper_pnl"] == V.run_validation(c)["net_paper_pnl"]


def test_forward_predictions_logged_to_ledger():
    r = V.run_validation(V.ValidationConfig(edge=0.6, n_days=3, markets_per_day=4))
    assert r["forward_predictions_logged"] == 12  # read back via read_ledger reuse


def test_grade_verdict_note_is_honest():
    r = V.run_validation(V.ValidationConfig(edge=0.6, n_days=4, markets_per_day=4))
    assert "necessary, not sufficient" in r["note"]
    assert "HUMAN-CONFIRM" in r["note"] and "No edge is claimed" in r["note"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print("%d/%d green" % (len(fns), len(fns)))
