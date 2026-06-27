"""Per-file test: regime_experts -- NAME-stable labels + graceful-degrade collapse."""
from __future__ import annotations

from scripts.platformkit.improve.fusion.regime_experts import (
    GLOBAL, REGIME_NAMES, assign_regime, is_degenerate_split, regime_split,
)


def test_regime_names_are_not_cluster_ids():
    for name in REGIME_NAMES:
        assert not name.startswith("c") or name in ("close",)  # 'close' is a NAME, not c<digit>
        assert "kmeans" not in name and "cluster" not in name


def test_assign_regime_uses_state_names():
    assert assign_regime(2.0, 0.3) == "close"
    assert assign_regime(20.0, 0.3) == "blowout"
    assert assign_regime(7.0, 0.3) == "mid"
    assert assign_regime(2.0, 0.9) == "late"      # late overrides margin
    assert assign_regime(float("nan"), 0.3) == GLOBAL


def test_underpowered_regime_pools_into_global():
    # 40 'close' rows (powered) + 3 'blowout' rows (under-powered -> pooled to GLOBAL)
    regimes = ["close"] * 40 + ["blowout"] * 3
    split = regime_split(regimes, min_rows=30)
    assert "close" in split and len(split["close"]) == 40
    assert "blowout" not in split          # under-powered -> graceful-degrade
    assert len(split[GLOBAL]) == 3         # pooled into the global blend


def test_single_regime_split_is_degenerate():
    # all rows in one powered regime -> only that regime survives -> degenerate
    split = regime_split(["close"] * 50, min_rows=10)
    assert is_degenerate_split(split) is True


def test_multi_regime_split_is_not_degenerate():
    split = regime_split(["close"] * 40 + ["blowout"] * 40, min_rows=10)
    assert is_degenerate_split(split) is False


def test_unknown_label_pools_to_global():
    split = regime_split(["close"] * 40 + ["mystery"] * 5, min_rows=10)
    assert "mystery" not in split
    assert len(split[GLOBAL]) == 5
