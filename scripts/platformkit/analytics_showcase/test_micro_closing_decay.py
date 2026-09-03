"""Focused paired-summary coverage for S195."""
from scripts.platformkit.analytics_showcase import micro_closing_decay as decay


def test_close_vs_first_paired_uses_the_shared_games_and_reports_zero_pairs(monkeypatch) -> None:
    snapshots = {
        "paired": [(6.0, 0.8), (0.25, 0.6)],
        "close_only": [(0.25, 0.9)],
    }
    monkeypatch.setattr(decay, "load_home_snapshots", lambda sport: (snapshots, "2026-01-01", {}))
    monkeypatch.setattr(decay, "load_outcomes", lambda sport: {"paired": 1, "close_only": 1})

    result = decay.analyze_sport("fixture")

    assert result["buckets"]["T-6h"]["n"] == 1
    assert result["buckets"]["close"]["n"] == 2
    assert result["close_vs_t24h_paired"] == {"n": 0}
    assert result["close_vs_first_paired"] == {
        "first_anchor": "T-6h",
        "n": 1,
        "brier_first_anchor": 0.04,
        "brier_close": 0.16,
        "brier_delta_first_anchor_minus_close": -0.12,
        "close_sharper": False,
        "underpowered": True,
    }
    assert "n_games=1" in decay.build_verdict({"fixture": result})
    assert "no paired games" in decay.build_verdict({"empty": {
        "close_vs_first_paired": {"first_anchor": "T-6h", "n": 0},
    }})
