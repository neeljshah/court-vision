"""domains.soccer_intl - national-team (international) soccer adapter.

Club soccer (domains/soccer) is league/club-only and cannot price World Cup
matches.  This sibling domain ingests the public martj42/international_results
corpus (national teams, 1872-present, neutral-site aware) and reuses the exact
EW goals-rate + Dixon-Coles Poisson scoreline math from domains/soccer to emit
BOTH a 1X2 moneyline (win/draw/loss) AND an O/U 2.5 surface for international
fixtures - including the 2026 World Cup (mostly neutral-site).

Honest: international pregame markets are efficient; this is a CALIBRATED
predictor (Brier/calibration), NOT a betting-edge product.  No $ edge claimed.
"""
