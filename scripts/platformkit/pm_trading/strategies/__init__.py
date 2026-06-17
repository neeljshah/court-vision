"""Trading strategies. Each emits SIZED, RISK-CHECKED orders via a RiskManager,
never raw size -- the risk gate is the only path to a venue.

  cross_market_arb -- lock the spread on the same contract across two venues.
  model_vs_market  -- trade our calibrated prob vs price, ONLY when the
                      eval_gate verdict says the model beats the close.
  market_maker     -- two-sided quotes on thin books, inventory-skewed.
"""
from .base import Strategy, TradeIntent
from .cross_market_arb import ArbOpportunity, CrossMarketArb
from .model_vs_market import ModelVsMarket
from .market_maker import MarketMaker

__all__ = [
    "Strategy",
    "TradeIntent",
    "CrossMarketArb",
    "ArbOpportunity",
    "ModelVsMarket",
    "MarketMaker",
]
