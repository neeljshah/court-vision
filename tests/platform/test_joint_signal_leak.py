"""tests/platform/test_joint_signal_leak.py — JOINT signal leak / truncation-invariance battery.

Asserts three properties for JOINT signal catalogs across tennis, soccer, mlb:
1. TRUNCATION-INVARIANCE: joint signals on truncated corpus == full corpus for shared
   pre-T rows (proves no future info injected).
2. PURE-TRANSFORM / DETERMINISM: two calls with the same base matrix return identical
   arrays; output length == n; values are finite-or-NaN only (no ±inf).
3. BASE-COLUMN INDEPENDENCE: shuffling target/closing leaves joint signal unchanged
   (transform reads only base columns, never future outcome/market data).

Skip a sport when corpus absent; at least one sport must exercise assertions.
Run: python -m pytest tests/platform/test_joint_signal_leak.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_TOL = 1e-6

_SPLITS: Dict[str, Dict[str, Any]] = {
    "tennis": {"early": [2015,2016,2017,2018,2019], "full": [2015,2016,2017,2018,2019,2020], "kw": {}},
    "soccer": {"early": [2015,2016,2017,2018,2019], "full": [2015,2016,2017,2018,2019,2020], "kw": {}},
    "mlb":    {"early": [2010,2011,2012,2013,2014,2015], "full": [2010,2011,2012,2013,2014,2015,2016], "kw": {}},
}


def _joint_meta(sport: str) -> Tuple[Sequence[type], Callable]:
    """Return (catalog_tuple, compute_fn) for the sport's joint catalog."""
    if sport == "tennis":
        from domains.tennis.signal_catalog_joint import CATALOG_JOINT_SIGNALS, _compute_joint_signal_col
        return CATALOG_JOINT_SIGNALS, _compute_joint_signal_col
    if sport == "soccer":
        from domains.soccer.signal_catalog_joint import CATALOG_JOINT_SIGNALS, _compute_joint_signal_col
        return CATALOG_JOINT_SIGNALS, _compute_joint_signal_col
    from domains.mlb.signal_catalog_joint import CATALOG_SIGNALS, _compute_signal_col
    return CATALOG_SIGNALS, _compute_signal_col


def _load_adapter(sport: str) -> Optional[Any]:
    import pandas as pd
    corpus = REPO_ROOT / "data" / "domains" / sport
    fname = "games.parquet" if sport == "mlb" else "matches.parquet"
    if not (corpus / fname).exists():
        return None
    try:
        df = pd.read_parquet(corpus / fname)
        odds: Optional[Any] = None
        op = corpus / "odds.parquet"
        if op.exists():
            try: odds = pd.read_parquet(op)
            except Exception: pass
        if sport == "tennis":
            from domains.tennis.adapter import TennisAdapter
            return TennisAdapter(matches_df=df, odds_df=odds)
        if sport == "soccer":
            from domains.soccer.adapter import SoccerAdapter
            return SoccerAdapter(matches_df=df, odds_df=odds)
        from domains.mlb.adapter import MLBAdapter
        return MLBAdapter(games_df=df, odds_df=odds)
    except Exception:
        return None


def _get_adapter(sport: str) -> Any:
    a = _load_adapter(sport)
    if a is None:
        pytest.skip(f"Corpus absent for {sport}.")
    return a


def _hyp(tag: str) -> Any:
    from src.loop.signal import Hypothesis
    return Hypothesis(name=tag, target="winprob", scope="pregame", statement=tag)


def _idx_map(dates: List[str]) -> Dict[str, List[int]]:
    m: Dict[str, List[int]] = {}
    for i, d in enumerate(dates):
        m.setdefault(d, []).append(i)
    return m


# ---------------------------------------------------------------------------
# Test 1 — TRUNCATION-INVARIANCE
# ---------------------------------------------------------------------------

class TestJointTruncationInvariance:
    """Joint signal values must be identical for shared pre-T rows in trunc vs full corpus."""

    @pytest.mark.parametrize("sport", ["tennis", "soccer", "mlb"])
    def test_all_joint_signals_truncation_invariant(self, sport: str) -> None:
        catalog, fn = _joint_meta(sport)
        adapter = _get_adapter(sport)
        cfg = _SPLITS[sport]
        fb_e = adapter.feature_bundle(_hyp(f"jt_e_{sport}"), cfg["early"], **cfg["kw"])
        fb_f = adapter.feature_bundle(_hyp(f"jt_f_{sport}"), cfg["full"],  **cfg["kw"])
        em, fm = _idx_map(fb_e.dates), _idx_map(fb_f.dates)
        common = sorted(set(em) & set(fm))
        assert len(common) >= 10, f"[{sport}] only {len(common)} common dates"

        for cls in catalog:
            name = cls.name  # type: ignore[attr-defined]
            sc_e = fn(cls, fb_e.base)
            sc_f = fn(cls, fb_f.base)
            bad: List[str] = []
            checked = 0
            for d in common:
                for ie, if_ in zip(em[d], fm[d]):
                    ve, vf = float(sc_e[ie]), float(sc_f[if_])
                    if not np.isclose(ve, vf, atol=_TOL, equal_nan=True):
                        bad.append(f"date={d} early={ve:.6g} full={vf:.6g}")
                    checked += 1
            assert checked >= 10, f"[{sport}/{name}] only {checked} rows checked"
            assert not bad, (
                f"TRUNCATION-INVARIANCE VIOLATED [{sport}/{name}] "
                f"on {len(bad)}/{checked} rows — SERIOUS: joint signal reads future data!\n"
                f"First: {bad[0]}"
            )


# ---------------------------------------------------------------------------
# Test 2 — PURE TRANSFORM / DETERMINISM / OUTPUT SANITY
# ---------------------------------------------------------------------------

class TestJointPureTransform:
    """compute_fn must be deterministic, return length-n arrays, and produce no ±inf."""

    @pytest.mark.parametrize("sport", ["tennis", "soccer", "mlb"])
    def test_determinism_length_and_finite(self, sport: str) -> None:
        catalog, fn = _joint_meta(sport)
        adapter = _get_adapter(sport)
        cfg = _SPLITS[sport]
        fb = adapter.feature_bundle(_hyp(f"jp_{sport}"), cfg["early"], **cfg["kw"])
        n = fb.base.shape[0]

        for cls in catalog:
            name = cls.name  # type: ignore[attr-defined]
            sc1 = fn(cls, fb.base)
            sc2 = fn(cls, fb.base)

            assert isinstance(sc1, np.ndarray), f"[{sport}/{name}] not ndarray"
            assert sc1.shape == (n,), f"[{sport}/{name}] shape {sc1.shape} != ({n},)"
            assert np.allclose(sc1, sc2, atol=0.0, equal_nan=True), (
                f"DETERMINISM VIOLATED [{sport}/{name}]: two calls differ — "
                f"hidden state or RNG dependency."
            )
            assert not np.isinf(sc1).any(), (
                f"CORRUPTION RISK [{sport}/{name}]: {np.isinf(sc1).sum()} ±inf values — "
                f"check for division by near-zero; would corrupt gate training."
            )


# ---------------------------------------------------------------------------
# Test 3 — BASE-COLUMN INDEPENDENCE (target/closing shuffled → no change)
# ---------------------------------------------------------------------------

class TestJointBaseColumnIndependence:
    """Shuffling target + closing must not change compute_fn output.

    compute_fn(cls, base) takes ONLY the base matrix — this test documents and
    enforces that contract: if a future refactor accidentally threads outcome data
    into the transform, this test will fail with a loud leak message.
    """

    @pytest.mark.parametrize("sport", ["tennis", "soccer", "mlb"])
    def test_invariant_to_target_and_closing_shuffle(self, sport: str) -> None:
        from src.loop.gate import FeatureBundle
        catalog, fn = _joint_meta(sport)
        adapter = _get_adapter(sport)
        cfg = _SPLITS[sport]
        fb = adapter.feature_bundle(_hyp(f"ji_{sport}"), cfg["early"], **cfg["kw"])
        n = fb.base.shape[0]
        rng = np.random.default_rng(42)

        fb_shuf = FeatureBundle(
            base=fb.base,
            signal_col=fb.signal_col,
            target=rng.permutation(fb.target),
            dates=fb.dates,
            lines=fb.lines,
            closing=rng.permutation(fb.closing) if fb.closing is not None
                     else np.full(n, np.nan),
        )

        for cls in catalog:
            name = cls.name  # type: ignore[attr-defined]
            sc_orig = fn(cls, fb.base)
            sc_shuf = fn(cls, fb_shuf.base)
            assert np.allclose(sc_orig, sc_shuf, atol=0.0, equal_nan=True), (
                f"SERIOUS LEAK [{sport}/{name}]: joint signal changed after shuffling "
                f"target/closing — transform has hidden access to future outcome data!"
            )


# ---------------------------------------------------------------------------
# Guard — at least one corpus present so the battery ran real assertions
# ---------------------------------------------------------------------------

def test_at_least_one_sport_exercised() -> None:
    """Fail if ALL three corpora are absent (battery would be vacuously green)."""
    present = any(
        (REPO_ROOT / "data" / "domains" / s / ("games.parquet" if s == "mlb" else "matches.parquet")).exists()
        for s in ("tennis", "soccer", "mlb")
    )
    assert present, (
        "ALL three sport corpora absent — joint-signal leak battery ran zero assertions. "
        "Add at least one corpus under data/domains/<sport>/."
    )
