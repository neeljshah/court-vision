"""Unit tests for pinnacle_gate.strip_vig — verifies textbook no-vig conversion."""
import pytest
from src.data.pinnacle_gate import american_to_implied, strip_vig


class TestAmericanToImplied:
    def test_even_money(self):
        assert american_to_implied(100) == pytest.approx(0.5, rel=1e-4)

    def test_minus_110(self):
        # -110 → 110/210 ≈ 0.5238
        assert american_to_implied(-110) == pytest.approx(110 / 210, rel=1e-4)

    def test_plus_110(self):
        # +110 → 100/210 ≈ 0.4762
        assert american_to_implied(110) == pytest.approx(100 / 210, rel=1e-4)

    def test_heavy_favourite(self):
        # -200 → 200/300 = 0.6667
        assert american_to_implied(-200) == pytest.approx(2 / 3, rel=1e-4)


class TestStripVig:
    def test_balanced_juice_110(self):
        """Textbook: -110/-110 → 50/50, vig ≈ 4.76%."""
        result = strip_vig(-110, -110)
        assert result["over_prob"] == pytest.approx(0.5, abs=1e-4)
        assert result["under_prob"] == pytest.approx(0.5, abs=1e-4)
        assert result["vig"] == pytest.approx(110 / 210 * 2 - 1.0, abs=1e-4)

    def test_probs_sum_to_one(self):
        result = strip_vig(-110, -110)
        assert result["over_prob"] + result["under_prob"] == pytest.approx(1.0, abs=1e-6)

    def test_asymmetric_odds(self):
        """-130/+110 — over is favoured; after vig removal over_prob > 0.5."""
        result = strip_vig(-130, 110)
        assert result["over_prob"] > 0.5
        assert result["over_prob"] + result["under_prob"] == pytest.approx(1.0, abs=1e-6)
        assert result["vig"] > 0

    def test_even_money_no_vig(self):
        """Even money lines (+100/+100) carry no vig."""
        result = strip_vig(100, 100)
        assert result["over_prob"] == pytest.approx(0.5, abs=1e-4)
        assert result["vig"] == pytest.approx(0.0, abs=1e-6)

    def test_plus110_minus110(self):
        """+110/-110 — under is favoured."""
        result = strip_vig(110, -110)
        assert result["over_prob"] < 0.5
        assert result["under_prob"] > 0.5

    def test_vig_always_nonnegative(self):
        """Vig is a margin added by the book — should never be negative."""
        for pair in [(-110, -110), (-120, +100), (-130, +110), (100, 100)]:
            result = strip_vig(*pair)
            assert result["vig"] >= 0
