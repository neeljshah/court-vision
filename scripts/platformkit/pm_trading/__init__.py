"""Prediction-market trading subsystem (PAPER-FIRST).

Turns the calibrated 4-sport model's probabilities into sized, risk-checked,
forward-validated orders on prediction-market EXCHANGES (Kalshi, Polymarket).

HONEST RAILS (see module docstrings):
  - PAPER-FIRST: everything runs end-to-end on PaperVenue with NO real keys.
  - NO real capital until a multi-week forward PAPER P&L + CLV record is
    positive AND survives the eval_gate. In-sample backtest is NOT enough.
  - Global ENABLED flag defaults OFF; go-live is HUMAN-CONFIRM only.
  - No fabricated edge/ROI. A losing strategy on paper is a recorded REJECT.

This package builds ONLY under scripts/platformkit/pm_trading/ and never
edits src/, kernel/, or api/ trees.
"""

ENABLED = False  # global live-trading kill flag; default OFF (paper only)
