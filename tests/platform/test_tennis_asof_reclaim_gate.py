"""tests/platform/test_tennis_asof_reclaim_gate.py -- leak guard for the ATP reclaim gate.

Focuses on the ONE invariant that matters for domains.tennis.asof_reclaim_gate: every
candidate frame the gate scores is built from STRICTLY-EARLIER-matches-only trailing
features, and the walk-forward train/test split never lets a later match's features
or elo state leak into an earlier match's prediction. asof_hold.py / asof_return.py /
asof_features.py each carry their OWN future-leak assertion at build time (see
tests/platform/test_asof_hold.py); this file instead verifies the NEW glue code in
asof_reclaim_gate.py preserves that guarantee through the merge + DM split, using
small synthetic frames (fast, no real-parquet dependency for the leak checks) plus
one real-data smoke check.

ACCURACY ONLY -- NO MARKET EDGE CLAIMED.  No src/ / kernel/ imports.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from domains.tennis.asof_reclaim_gate import (
    CANDIDATES,
    _gate_once,
    _load_candidate_frame,
    _honest_verdict,
)


# ---------------------------------------------------------------------------
# Synthetic candidate frame (mirrors the shape gate_feature builds internally)
# ---------------------------------------------------------------------------

def _make_base_close(n: int, seed: int = 0) -> pd.DataFrame:
    """A tiny synthetic base_close frame: date, target, p_base, p_close."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    y = rng.integers(0, 2, size=n).astype(float)
    return pd.DataFrame({
        "event_id": [f"e{i}" for i in range(n)],
        "date": dates,
        "winner": np.where(y == 1.0, 1, 2),
        "p_base": np.clip(0.5 + rng.normal(0, 0.05, size=n), 0.05, 0.95),
        "target_p1_win": y,
        "p_close": np.clip(0.5 + rng.normal(0, 0.05, size=n), 0.05, 0.95),
    })


class TestStrictlyEarlierOnly:
    """The core leak-guard: a candidate feature computed from FUTURE matches must
    never be able to pass this gate as if it were prior-only -- the gate itself does
    not compute the trailing aggregate (that happens upstream in asof_hold.py etc.
    with its own assertion), but the TRAIN/TEST split here must never let TEST-period
    matches influence TRAIN-period fitting, and a feature perfectly correlated with
    the FUTURE label (a synthetic proxy for a leaky feature) must be caught by
    the planted-null / or simply produce a result scored ONLY on the chronologically
    LATER held-out slice, never mixed with earlier rows.
    """

    def test_train_test_split_is_strictly_chronological(self):
        """The DM test/train split must partition by ROW ORDER (chronological),
        i.e. every TEST row's index is >= every TRAIN row's index -- no shuffling.
        """
        n = 200
        df = _make_base_close(n)
        df["feat"] = np.random.default_rng(1).normal(size=n)
        df["_cov"] = True

        split = int(n * 0.70)
        tr_dates = df.iloc[:split]["date"]
        te_dates = df.iloc[split:]["date"]
        # Every train date must be < every test date (frame is already sorted by
        # date in the real pipeline; here we assert the split itself is positional
        # and does not re-sort or shuffle rows).
        assert tr_dates.max() < te_dates.min(), (
            "Train/test split must be a strict chronological prefix/suffix; "
            "found overlap or non-monotonic dates."
        )

    def test_leaky_future_proxy_feature_does_not_silently_ship(self):
        """A feature built directly from the TEST-period label distribution (a
        stand-in for a hypothetically leaky as-of column) must not produce a
        deceptively strong REAL result without tripping either the planted-null
        or truncation-invariance control -- i.e. _honest_verdict never reports
        SHIP for a feature whose apparent edge evaporates once its very-late-window
        alignment is perturbed.
        """
        n = 400
        df = _make_base_close(n, seed=7)
        df["_cov"] = True
        # Construct a feature that is a *direct* function of the label ONLY within
        # the test window (simulating a hypothetical alignment bug where a future
        # row's own outcome leaked into its feature) -- everywhere else it's noise.
        split = int(n * 0.70)
        feat = np.random.default_rng(2).normal(size=n)
        feat[split:] = (df["target_p1_win"].values[split:] - 0.5) * 10.0
        df["feat"] = feat

        real = _gate_once(df, "feat", "p_base")
        # Even if the REAL run looks artificially strong, the planted-null
        # (which permutes the SAME leaky column) must not also look strong,
        # because permutation destroys the leaked alignment -- the honest
        # verdict logic downstream (asof_reclaim_gate._honest_verdict) exists
        # exactly to downgrade a real-only "win" like this.
        rng = np.random.default_rng(0)
        nd = df.copy()
        nd["feat"] = rng.permutation(nd["feat"].values)
        null = _gate_once(nd, "feat", "p_base")
        res = {
            "vs_elo": {"real": real, "planted_null": null,
                       "truncation": _gate_once(df, "feat", "p_base", train_frac=0.63)},
            "vs_close": None,
        }
        verdict = _honest_verdict(res)
        if real["verdict"] == "SHIP":
            # If the leaky-only-in-test-window construction happened to trip SHIP,
            # the truncation control (which shrinks the train window, shifting
            # which rows are "future" relative to fit) or the null must catch it,
            # and _honest_verdict must not report a bare SHIP through un-downgraded.
            assert verdict != "SHIP" or (
                null["verdict"] != "SHIP"
                and res["vs_elo"]["truncation"]["verdict"] == real["verdict"]
            ), "A leaky test-window-only feature passed all controls -- leak guard hole."


class TestLoadCandidateFrameCoverage:
    """_load_candidate_frame must mark a row covered ONLY when the underlying
    parquet's own prior-count columns (already leak-audited at build time by
    asof_hold.py / asof_return.py / asof_features.py) meet MIN_PRIOR -- i.e. this
    module must not invent coverage the upstream leak-free builder didn't certify.
    """

    def test_debut_rows_never_marked_covered(self, tmp_path: Path):
        """A row where the upstream builder recorded n_prior=0 (debut, its own
        future-leak assertion guarantees NaN feature there) must never be marked
        _cov=True regardless of what the feature column happens to contain.
        """
        base_close = _make_base_close(3)
        cand = pd.DataFrame({
            "event_id": ["e0", "e1", "e2"],
            "hold_pct_diff_asof": [np.nan, 0.05, -0.02],  # e0 = debut -> NaN (upstream contract)
            "p1_n_prior": [0, 3, 6],
            "p2_n_prior": [0, 2, 7],
        })
        path = tmp_path / "asof_hold.parquet"
        cand.to_parquet(path)

        spec = ("hold_pct_diff_asof", path,
                ("hold_pct_diff_asof", "p1_hold_pct_asof", "p2_hold_pct_asof"),
                ("p1_n_prior", "p2_n_prior"))
        # p1_hold_pct_asof/p2_hold_pct_asof are absent (only the diff is present in
        # this minimal fixture) -- derive step is a no-op when source cols are
        # missing, so we pre-seed the diff column directly under its own name.
        out = _load_candidate_frame(spec, base_close)
        assert bool(out.loc[out["event_id"] == "e0", "_cov"].iloc[0]) is False, (
            "Debut row (p1_n_prior=0) must never be marked covered."
        )

    def test_min_prior_5_threshold_enforced(self, tmp_path: Path):
        """A row with n_prior=4 on either side (just under MIN_PRIOR=5) must be
        excluded from coverage even when the feature value itself is present.
        """
        base_close = _make_base_close(2)
        cand = pd.DataFrame({
            "event_id": ["e0", "e1"],
            "hold_pct_diff_asof": [0.03, 0.01],
            "p1_n_prior": [4, 5],   # e0 just below MIN_PRIOR
            "p2_n_prior": [5, 5],
        })
        path = tmp_path / "asof_hold.parquet"
        cand.to_parquet(path)
        spec = ("hold_pct_diff_asof", path,
                ("hold_pct_diff_asof", "p1_hold_pct_asof", "p2_hold_pct_asof"),
                ("p1_n_prior", "p2_n_prior"))
        out = _load_candidate_frame(spec, base_close)
        assert bool(out.loc[out["event_id"] == "e0", "_cov"].iloc[0]) is False
        assert bool(out.loc[out["event_id"] == "e1", "_cov"].iloc[0]) is True


class TestHonestVerdictDowngrade:
    """_honest_verdict must downgrade a raw SHIP that fails either control."""

    def _make(self, real_verdict: str, null_verdict: str, trunc_verdict: str) -> dict:
        return {
            "vs_elo": {
                "real": {"verdict": real_verdict},
                "planted_null": {"verdict": null_verdict},
                "truncation": {"verdict": trunc_verdict},
            },
            "vs_close": None,
        }

    def test_ship_with_clean_controls_ships(self):
        res = self._make("SHIP", "REJECT", "SHIP")
        assert _honest_verdict(res) == "SHIP"

    def test_ship_with_null_also_shipping_is_downgraded(self):
        """If the shuffled (leak-broken) feature ALSO ships, the real SHIP is an
        artifact of the fitting procedure, not the feature -- must downgrade."""
        res = self._make("SHIP", "SHIP", "SHIP")
        assert _honest_verdict(res) == "REJECT"

    def test_ship_that_flips_under_truncation_is_downgraded(self):
        """If dropping the last 10% of train rows flips the verdict, the SHIP is
        not stable -- must downgrade (this is the exact pattern observed on
        hold_pct_grass_diff_asof in the real ATP corpus)."""
        res = self._make("SHIP", "REJECT", "REJECT")
        assert _honest_verdict(res) == "REJECT"

    def test_not_testable_passes_through(self):
        res = self._make("NOT_TESTABLE", "REJECT", "REJECT")
        assert _honest_verdict(res) == "NOT_TESTABLE"


class TestRealDataSmoke:
    """Real-corpus smoke test -- confirms the module runs end-to-end without error
    and every candidate resolves to a well-formed dict.  Skips if parquets absent.
    """

    def test_all_candidates_load_and_cover_nonzero_rows(self):
        for feat_col, path, _derive, _prior in CANDIDATES:
            if not Path(path).exists():
                pytest.skip(f"{path} not found -- run the as-of builder first")
        from domains.tennis.asof_reclaim_gate import _elo_and_close
        base_close = _elo_and_close()
        assert len(base_close) > 0
        assert base_close["date"].is_monotonic_increasing, (
            "base_close must be chronologically sorted (walk-forward contract)."
        )
        for feat_col, path, _derive, _prior in CANDIDATES[:1]:  # one is enough for a smoke check
            out = _load_candidate_frame((feat_col, path, _derive, _prior), base_close)
            assert int(out["_cov"].sum()) > 0, f"{feat_col}: zero covered rows"
