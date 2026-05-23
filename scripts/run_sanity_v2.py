"""Sanity checks for LiveWinProbV2."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.prediction.live_win_prob_v2 import LiveWinProbV2

m = LiveWinProbV2()
assert m._model is not None, "Model not loaded — run training first"

scenarios = [
    ("S1: Tipoff, equal teams, 0-0", dict(
        seconds_remaining=2880, score_margin_home=0.0,
        home_net_rtg_l10=0.0, away_net_rtg_l10=0.0,
        home_off_rtg_l10=110.0, away_off_rtg_l10=110.0,
        home_def_rtg_l10=110.0, away_def_rtg_l10=110.0,
        period=1, net_rtg_diff=0.0,
        home_form_l5=0.5, away_form_l5=0.5,
    ), "~0.50 (0.35-0.65)"),
    ("S2: 60s left, home +20", dict(
        seconds_remaining=60, score_margin_home=20.0, period=4,
    ), ">0.95"),
    ("S3: 60s left, home -20", dict(
        seconds_remaining=60, score_margin_home=-20.0, period=4,
    ), "<0.05"),
    ("S4: Tipoff, home net_rtg+5 better", dict(
        seconds_remaining=2880, score_margin_home=0.0,
        home_net_rtg_l10=5.0, away_net_rtg_l10=0.0,
        home_off_rtg_l10=115.0, away_off_rtg_l10=110.0,
        home_def_rtg_l10=110.0, away_def_rtg_l10=112.0,
        period=1, net_rtg_diff=5.0,
        home_form_l5=0.6, away_form_l5=0.5,
    ), "~0.62 (0.55-0.75)"),
]

all_pass = True
for label, state, expectation in scenarios:
    p = m.predict(state)
    print(f"{label}")
    print(f"  P(home wins) = {p:.4f}  expected {expectation}")
    print()

print("All sanity checks output above — verify manually against expected ranges.")
