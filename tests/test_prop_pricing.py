"""tests/test_prop_pricing.py — Phase 16 prop pricing engine tests.

Stubs: all marked skip until src/prediction/prop_pricing_engine.py is implemented.
"""
import pytest

try:
    from src.prediction.prop_pricing_engine import PropPricingEngine
    _IMPORT_OK = True
except ImportError:
    _IMPORT_OK = False

pytestmark = pytest.mark.skipif(not _IMPORT_OK, reason="prop_pricing_engine.py not yet implemented")


def test_roi():
    """Verify PropPricingEngine.backtest() returns dict with 'roi' as a float.

    Runs a mini-backtest on the last 20 games for the 'pts' stat. The returned
    dict must contain an 'roi' key that is a Python float (sign doesn't matter —
    this is just a type/schema check, not a profitability requirement).
    """
    engine = PropPricingEngine()
    result = engine.backtest(stat="pts", n_games=20)
    assert "roi" in result, "backtest result missing 'roi' key"
    assert isinstance(result["roi"], float), (
        f"roi must be a float, got {type(result['roi'])}"
    )


def test_distribution():
    """Verify PropPricingEngine.get_distribution() returns full percentile dict.

    Given LeBron James (player_id='2544') and stat='pts', the distribution
    method must return a dict with keys: 'mean', 'std', 'p10', 'p50', 'p90' —
    all Python floats. These represent the model's predictive distribution for
    the stat, used to price over/under lines.
    """
    engine = PropPricingEngine()
    dist = engine.get_distribution(player_id="2544", stat="pts")
    required_keys = {"mean", "std", "p10", "p50", "p90"}
    missing = required_keys - set(dist.keys())
    assert not missing, f"get_distribution result missing keys: {missing}"
    for key in required_keys:
        assert isinstance(dist[key], float), (
            f"dist['{key}'] must be float, got {type(dist[key])}"
        )
