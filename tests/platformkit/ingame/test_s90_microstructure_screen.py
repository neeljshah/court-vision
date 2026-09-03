"""S90 per-file test -- pure logic only, CONSTRUCT (every case enumerated), no store read.

Run: python -m pytest tests/platformkit/ingame/test_s90_microstructure_screen.py -q
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.ingame import s90_microstructure_screen as s90


def test_stop_rule_below_bar_is_falsified():
    verdict = s90.stop_rule_verdict(18, bar=30)
    assert "FALSIFIED" in verdict or "INSUFFICIENT" in verdict
    assert "18" in verdict and "30" in verdict


def test_stop_rule_at_or_above_bar_is_buildable():
    assert s90.stop_rule_verdict(30, bar=30).startswith("BUILDABLE")
    assert s90.stop_rule_verdict(31, bar=30).startswith("BUILDABLE")


def _price_frame():
    # CONSTRUCT: every combination of series prefix x game suffix x market type is enumerated.
    return pd.DataFrame({
        "event_key": [
            "KXMLBGAME-26JUL011235CWSBAL", "KXMLBTOTAL-26JUL011235CWSBAL",       # both types: matched
            "KXMLBGAME-26JUL021400NYYBOS",                                       # only moneyline: not matched
            "KXMLBSPREAD-26JUL021400NYYBOS",                                     # spread present, total absent
            "KXWCGAME-26JUL01BELSEN", "KXWCSPREAD-26JUL01BELSEN", "KXWCTEAMTOTAL-26JUL01BELSEN",
        ],
        "market_type": ["moneyline", "total", "moneyline", "spread", "moneyline", "spread", "team_total"],
    })


def test_rekey_market_overlap_mlb_moneyline_total():
    result = s90.rekey_market_overlap(_price_frame(), {"moneyline", "total"})
    assert result["n_games_total"] == 3           # 3 distinct game suffixes
    assert result["n_games_matched"] == 1          # only CWSBAL carries both moneyline and total
    assert result["matched_game_suffixes_sample"] == ["26JUL011235CWSBAL"]


def test_rekey_market_overlap_soccer_all_three():
    result = s90.rekey_market_overlap(_price_frame(), {"moneyline", "spread", "team_total"})
    assert result["n_games_matched"] == 1
    assert "26JUL01BELSEN" in result["matched_game_suffixes_sample"]


def test_rekey_market_overlap_required_types_sorted_and_no_match_case():
    result = s90.rekey_market_overlap(_price_frame(), {"total", "spread"})
    assert result["required_types"] == ["spread", "total"]
    assert result["n_games_matched"] == 0          # no single game suffix carries both total and spread


def _demo() -> None:
    test_stop_rule_below_bar_is_falsified()
    test_stop_rule_at_or_above_bar_is_buildable()
    test_rekey_market_overlap_mlb_moneyline_total()
    test_rekey_market_overlap_soccer_all_three()
    test_rekey_market_overlap_required_types_sorted_and_no_match_case()
    print("test_s90_microstructure_screen demo OK")


if __name__ == "__main__":
    _demo()
