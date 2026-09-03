"""S124/S125: the label-blindness guard and the UTC stamp parse. ASCII only.

Run: python -m pytest tests/platformkit/foundry/test_ingame_guards.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.foundry import ingame_guards as G

_KEYS = ["game", "timestamp", "_row_id"]


def _src(n: int = 60) -> pd.DataFrame:
    """A causal tick source that ALSO carries the tick's own label, as a leaky corpus would."""
    rng = np.random.default_rng(0)
    return pd.DataFrame([{"game": "G%d" % (i % 4), "timestamp": "2026-07-05T%02d:%02d:00Z"
                          % (i // 10, (i % 10) * 6), "_row_id": i, "state": float(i % 7),
                          "y": float(i % 4 < 2)} for i in range(n)]).assign(
        noise=rng.normal(size=n))


def _blind(src: pd.DataFrame) -> pd.DataFrame:
    """A builder that reads only as-of state -- never the label."""
    return src[_KEYS].assign(x=src["state"].to_numpy())


def _label_reader(src: pd.DataFrame) -> pd.DataFrame:
    """The S124 leak: the tick's OWN label, jittered past `_fit`'s MIN_UNIQUE brake."""
    return src[_KEYS].assign(x=src["y"].to_numpy() + src["noise"].to_numpy() * 0.05)


def test_a_blind_builder_passes_both_guards():
    src = _src()
    assert G.assert_label_blind(src, _blind) == ["y"]
    assert len(G.assert_tick_asof(src, _blind, probes=4)) == 4


def test_a_same_tick_label_reader_is_refused():
    """The S124 reproduction: this builder is TRUNCATION-INVARIANT and passed before."""
    src = _src()
    for k in (10, 30, 50):        # invariant under src[:k+1] -- the old guard could not see it
        assert _label_reader(src.iloc[:k + 1]).iloc[k]["x"] == _label_reader(src).iloc[k]["x"]
    with pytest.raises(G.TickTimeLeak) as exc:
        G.assert_tick_asof(src, _label_reader, probes=4)
    assert "own tick's label" in str(exc.value) and "x" in str(exc.value)


def test_a_later_tick_reader_still_raises_the_original_way():
    def peeks(src: pd.DataFrame) -> pd.DataFrame:
        return src[_KEYS].assign(x=src["state"].shift(-1).to_numpy())

    with pytest.raises(G.TickTimeLeak) as exc:
        G.assert_tick_asof(_src(), peeks, probes=3)
    assert "later than its own tick" in str(exc.value)


def test_no_label_in_the_source_checks_nothing_and_says_so():
    """The production path: `causal_source` carries no label, so the guard is a NO-OP there
    and must report that honestly rather than pass silently."""
    src = _src().drop(columns=["y"])
    assert G.assert_label_blind(src, _blind) == []
    labels = [float(i % 2) for i in range(len(src))]
    assert G.assert_label_blind(src, _blind, labels=labels) == ["outcome"]
    with pytest.raises(G.TickTimeLeak):
        G.assert_label_blind(src, lambda s: s[_KEYS].assign(x=s["outcome"].to_numpy()),
                             labels=labels)


def test_utc_stamps_orders_the_three_spellings_identically():
    """S125: ' ' (0x20) sorts before 'T' (0x54), so string order is not time order."""
    early, late = pd.Timestamp("2026-07-05T21:00:00"), pd.Timestamp("2026-07-06T01:00:00")
    assert str(early) < "2026-07-05T01:00:00Z"   # the defect: 21:00 reads as BEFORE the 01:00 cut
    for fmt in (lambda s: s.strftime("%Y-%m-%dT%H:%M:%SZ"), str, lambda s: s.isoformat()):
        parsed = G.utc_stamps([fmt(early), fmt(late)])
        assert isinstance(parsed.dtype, pd.DatetimeTZDtype)   # pandas 3 parses to [us, UTC]
        assert str(parsed.dtype.tz) == "UTC"
        assert parsed.iloc[0] < parsed.iloc[1]
        assert parsed.iloc[0] == pd.Timestamp("2026-07-05T21:00:00", tz="UTC")


def _served(n_games: int = 6, ticks: int = 20):
    """(x, y) at tick grain: `y` is the game outcome, constant within a game."""
    rng = np.random.default_rng(3)
    y = np.repeat((np.arange(n_games) % 2).astype(float), ticks)
    return rng.normal(size=n_games * ticks), y


def test_the_frozen_grammar_path_is_a_pure_no_op_and_an_ad_hoc_name_is_refused():
    frozen = {"state_diff": "score_diff", "outs": "outs"}
    assert G.gate_features(frozen, frozen) == []
    assert G.gate_features({"outs": "outs"}, frozen) == []
    with pytest.raises(G.AdHocFeature) as exc:
        G.gate_features({"outs": "outs", "mine": "x"}, frozen)
    assert "mine" in str(exc.value) and "allow_adhoc=True" in str(exc.value)
    assert G.gate_features({"mine": "x"}, frozen, allow_adhoc=True) == ["mine"]


def test_a_materialised_same_tick_label_reader_is_refused_on_the_served_path():
    """S124: `assert_label_blind` cannot bind on an already-built column -- this is the rule
    that does. The column IS the tick's label, so every value determines it exactly."""
    x, y = _served()
    with pytest.raises(G.TickTimeLeak) as exc:
        G.assert_column_blind(y, y, "label_now")
    assert "reads its own tick's label" in str(exc.value) and "label_now" in str(exc.value)
    with pytest.raises(G.TickTimeLeak):          # an INVERTED label is the same leak
        G.assert_column_blind(1.0 - y, y, "inverted_label")


def test_the_rule_does_not_bind_on_an_honest_column_and_says_so():
    x, y = _served()
    assert G.assert_column_blind(x, y, "state") is False                 # continuous: 120 > 2
    flag = np.repeat([0.0, 1.0, 0.0, 1.0, 1.0, 0.0], 20)                 # 2 values that do NOT
    assert G.assert_column_blind(flag, y, "flag") is True                # determine the label
    assert G.assert_column_blind(np.zeros(len(y)), y, "const") is True   # 1 value, 2 labels
