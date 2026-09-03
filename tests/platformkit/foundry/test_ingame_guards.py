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
        assert str(parsed.dtype) == "datetime64[ns, UTC]"
        assert parsed.iloc[0] < parsed.iloc[1]
        assert parsed.iloc[0] == pd.Timestamp("2026-07-05T21:00:00", tz="UTC")
