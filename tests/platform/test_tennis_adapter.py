"""tests/platform/test_tennis_adapter.py — Offline tests for the tennis adapter.

All tests run on synthetic in-memory data (no network, no torch, no heavy deps).
The suite verifies:
  1. feature_bundle() returns a gate-valid FeatureBundle (structural contract).
  2. The real gate.py accepts a tennis FeatureBundle via the injected-matrix seam
     (structural assertion — we check FeatureBundle field types, not run xgboost).
  3. The 3 signals are defined with target="winprob" and carry expected-verdict
     docstrings.
  4. F5 compliance: adapter/signals/config import ZERO basketball_nba / src.data
     modules (AST/grep check).

Run: python -m pytest tests/platform/test_tennis_adapter.py -q --timeout=150
"""
from __future__ import annotations

import ast
import datetime as dt
import importlib
import sys
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers: synthetic data factories
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]

SURFACES = ["Hard", "Clay", "Grass"]
ROUND_VALUES = ["R64", "R32", "QF", "SF", "F"]


def _make_matches(n: int = 200) -> pd.DataFrame:
    """Synthetic ATP match DataFrame with the Sackmann schema subset."""
    rng = np.random.default_rng(42)
    base_date = dt.date(2022, 1, 3)
    dates = [base_date + dt.timedelta(days=int(d)) for d in np.cumsum(rng.integers(1, 4, n))]
    player_ids = list(range(1, 21))  # 20 synthetic players

    rows = []
    for i, d in enumerate(dates):
        p1, p2 = rng.choice(player_ids, size=2, replace=False)
        surface = SURFACES[i % len(SURFACES)]
        winner = int(rng.integers(1, 3))  # 1 or 2
        best_of = 3 if i % 5 != 0 else 5
        rows.append(
            {
                "date": str(d),
                "tourney_id": f"2022-T{i % 10:03d}",
                "p1_id": int(p1),
                "p2_id": int(p2),
                "winner": winner,
                "surface": surface,
                "score": "6-4 6-3",
                "round": ROUND_VALUES[i % len(ROUND_VALUES)],
                "match_num": i,
                "best_of": best_of,
                "tour": "atp",
                "season": 2022,
                "event_id": f"{d}-T{i % 10:03d}-{p1}-{p2}",
                "retirement": False,
            }
        )
    return pd.DataFrame(rows)


def _make_odds(matches_df: pd.DataFrame) -> pd.DataFrame:
    """Synthetic odds DataFrame with the real odds.parquet schema.

    Columns match ingest_tennisdata.py anti-leak contract:
      p1/p2-ORIENTED prices: ps_p1, ps_p2, b365_p1, b365_p2  (use these)
      audit-only w/l prices: psw, psl, b365w, b365l           (never use for modelling)

    p1 = lower player_id per Sackmann convention (same as matches.parquet).
    The w/l columns are set from the match winner so they would leak — the
    oriented columns are outcome-blind.
    """
    rng = np.random.default_rng(7)
    rows = []
    for _, row in matches_df.iterrows():
        # Synthetic Pinnacle decimal odds keyed to p1/p2 (outcome-blind)
        p1_true = rng.uniform(0.35, 0.65)
        vig = 1.04
        ps_p1 = round(vig / p1_true, 2)
        ps_p2 = round(vig / (1.0 - p1_true), 2)
        b365_p1 = round(ps_p1 * 0.97, 2)
        b365_p2 = round(ps_p2 * 0.97, 2)

        # Audit-only w/l columns — derived from the actual winner (leak-prone,
        # kept only to mirror the real odds.parquet schema; NEVER read by adapter).
        winner = int(row["winner"])  # 1 = p1 won, 2 = p2 won
        if winner == 1:
            psw, psl = ps_p1, ps_p2
            b365w, b365l = b365_p1, b365_p2
        else:
            psw, psl = ps_p2, ps_p1
            b365w, b365l = b365_p2, b365_p1

        rows.append(
            {
                "event_id": row["event_id"],
                # Oriented (use these downstream)
                "ps_p1": ps_p1,
                "ps_p2": ps_p2,
                "b365_p1": b365_p1,
                "b365_p2": b365_p2,
                # Audit-only w/l (do NOT use for modelling)
                "psw": psw,
                "psl": psl,
                "b365w": b365w,
                "b365l": b365l,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def matches_df() -> pd.DataFrame:
    return _make_matches(200)


@pytest.fixture(scope="module")
def odds_df(matches_df: pd.DataFrame) -> pd.DataFrame:
    return _make_odds(matches_df)


@pytest.fixture(scope="module")
def adapter(matches_df: pd.DataFrame, odds_df: pd.DataFrame):
    """TennisAdapter wired with in-memory synthetic frames."""
    from domains.tennis.adapter import TennisAdapter

    return TennisAdapter(matches_df=matches_df, odds_df=odds_df)


# ---------------------------------------------------------------------------
# 1. feature_bundle structural contract
# ---------------------------------------------------------------------------


class TestFeatureBundle:
    """feature_bundle() must return a FeatureBundle satisfying the gate contract."""

    def test_returns_feature_bundle_instance(self, adapter) -> None:
        from src.loop.gate import FeatureBundle
        from src.loop.signal import Hypothesis

        hyp = Hypothesis(
            name="tennis_elo_baseline",
            target="winprob",
            scope="pregame",
            statement="Elo win prob predicts match outcome.",
        )
        fb = adapter.feature_bundle(hyp, seasons=[2022])
        assert isinstance(fb, FeatureBundle), "feature_bundle must return FeatureBundle"

    def test_base_is_2d_float_array(self, adapter) -> None:
        from src.loop.signal import Hypothesis

        hyp = Hypothesis(name="x", target="winprob", scope="pregame", statement="x")
        fb = adapter.feature_bundle(hyp, seasons=[2022])
        assert isinstance(fb.base, np.ndarray), "base must be numpy array"
        assert fb.base.ndim == 2, "base must be 2-dimensional (n, p)"
        assert fb.base.dtype == float or np.issubdtype(fb.base.dtype, np.floating)

    def test_signal_col_is_1d_float(self, adapter) -> None:
        from src.loop.signal import Hypothesis

        hyp = Hypothesis(name="x", target="winprob", scope="pregame", statement="x")
        fb = adapter.feature_bundle(hyp, seasons=[2022])
        assert isinstance(fb.signal_col, np.ndarray)
        assert fb.signal_col.ndim == 1
        assert fb.signal_col.shape[0] == fb.base.shape[0]

    def test_target_is_binary_winprob(self, adapter) -> None:
        """target must be binary {0.0, 1.0} for winprob classification."""
        from src.loop.signal import Hypothesis

        hyp = Hypothesis(name="x", target="winprob", scope="pregame", statement="x")
        fb = adapter.feature_bundle(hyp, seasons=[2022])
        unique = set(np.unique(fb.target))
        assert unique.issubset({0.0, 1.0}), f"winprob target must be binary; got {unique}"

    def test_dates_are_iso_strings(self, adapter) -> None:
        from src.loop.signal import Hypothesis

        hyp = Hypothesis(name="x", target="winprob", scope="pregame", statement="x")
        fb = adapter.feature_bundle(hyp, seasons=[2022])
        assert isinstance(fb.dates, list)
        assert len(fb.dates) == fb.base.shape[0]
        for d in fb.dates[:5]:
            dt.date.fromisoformat(d)  # must be valid ISO

    def test_dimensions_are_consistent(self, adapter) -> None:
        from src.loop.signal import Hypothesis

        hyp = Hypothesis(name="x", target="winprob", scope="pregame", statement="x")
        fb = adapter.feature_bundle(hyp, seasons=[2022])
        n = fb.base.shape[0]
        assert fb.signal_col.shape[0] == n
        assert fb.target.shape[0] == n
        assert len(fb.dates) == n

    def test_lines_and_closing_populated(self, adapter) -> None:
        """lines and closing must be non-None arrays when odds_df is injected."""
        from src.loop.signal import Hypothesis

        hyp = Hypothesis(name="x", target="winprob", scope="pregame", statement="x")
        fb = adapter.feature_bundle(hyp, seasons=[2022])
        assert fb.lines is not None, "lines must be populated when odds are available"
        assert fb.closing is not None, "closing must be populated when odds are available"
        assert isinstance(fb.lines, np.ndarray)
        assert isinstance(fb.closing, np.ndarray)
        n = fb.base.shape[0]
        assert fb.lines.shape[0] == n
        assert fb.closing.shape[0] == n

    def test_lines_are_valid_probabilities(self, adapter) -> None:
        """Devigged open/close probabilities must be in (0, 1)."""
        from src.loop.signal import Hypothesis

        hyp = Hypothesis(name="x", target="winprob", scope="pregame", statement="x")
        fb = adapter.feature_bundle(hyp, seasons=[2022])
        if fb.lines is not None:
            valid = fb.lines[~np.isnan(fb.lines)]
            assert np.all(valid > 0) and np.all(valid < 1), "lines must be probs in (0,1)"
        if fb.closing is not None:
            valid = fb.closing[~np.isnan(fb.closing)]
            assert np.all(valid > 0) and np.all(valid < 1), "closing must be probs in (0,1)"

    def test_base_has_5_features(self, adapter) -> None:
        """Base matrix must have 5 columns: elo_diff, surf_diff, best_of, rest_a, rest_b."""
        from src.loop.signal import Hypothesis

        hyp = Hypothesis(name="x", target="winprob", scope="pregame", statement="x")
        fb = adapter.feature_bundle(hyp, seasons=[2022])
        assert fb.base.shape[1] == 5, (
            f"Expected 5 base features; got {fb.base.shape[1]}"
        )

    def test_gate_matrix_seam_structural(self, adapter) -> None:
        """The gate's _build_feature_bundle picks up the injected _gate_matrix.

        We verify the structural contract without running XGBoost: inject the
        FeatureBundle into a mock signal._gate_matrix and confirm the gate's
        _build_feature_bundle resolver returns it unchanged.
        """
        from src.loop.gate import FeatureBundle, _build_feature_bundle
        from src.loop.signal import Hypothesis, Signal

        hyp = Hypothesis(name="y", target="winprob", scope="pregame", statement="y")
        fb = adapter.feature_bundle(hyp, seasons=[2022])

        class _MockSignal(Signal):
            name = "mock"
            target = "winprob"
            scope = "pregame"

            def build(self, ctx):
                return 0.5

            def hypothesis(self):
                return hyp

        sig = _MockSignal()
        sig._gate_matrix = fb  # type: ignore[attr-defined]

        resolved = _build_feature_bundle(sig, store=None)
        assert resolved is fb, "Gate must resolve injected _gate_matrix unchanged"
        assert isinstance(resolved, FeatureBundle)

    def test_min_rows_for_gate(self, adapter) -> None:
        """FeatureBundle must have at least _MIN_FOLD_ROWS (60) rows for folds."""
        from src.loop.gate import _MIN_FOLD_ROWS
        from src.loop.signal import Hypothesis

        hyp = Hypothesis(name="x", target="winprob", scope="pregame", statement="x")
        fb = adapter.feature_bundle(hyp, seasons=[2022])
        n = fb.base.shape[0]
        assert n >= _MIN_FOLD_ROWS, (
            f"FeatureBundle has only {n} rows; gate needs >= {_MIN_FOLD_ROWS}"
        )


# ---------------------------------------------------------------------------
# 2. Signal definitions
# ---------------------------------------------------------------------------


class TestSignalDefinitions:
    """The 3 signals must have target='winprob' and carry expected-verdict docs."""

    def test_all_signals_importable(self) -> None:
        from domains.tennis.signals import ALL_SIGNALS

        assert len(ALL_SIGNALS) == 3, f"Expected 3 signals; got {len(ALL_SIGNALS)}"

    def test_signal_names(self) -> None:
        from domains.tennis.signals import (
            FatigueRestSignal,
            H2HResidualSignal,
            SurfaceTransitionSignal,
        )

        assert FatigueRestSignal.name == "tennis_fatigue_rest"
        assert SurfaceTransitionSignal.name == "tennis_surface_transition"
        assert H2HResidualSignal.name == "tennis_h2h_residual"

    @pytest.mark.parametrize(
        "signal_cls",
        [
            "FatigueRestSignal",
            "SurfaceTransitionSignal",
            "H2HResidualSignal",
        ],
    )
    def test_target_is_winprob(self, signal_cls: str) -> None:
        mod = importlib.import_module("domains.tennis.signals")
        cls = getattr(mod, signal_cls)
        assert cls.target == "winprob", (
            f"{signal_cls}.target must be 'winprob'; got '{cls.target}'"
        )

    @pytest.mark.parametrize(
        "signal_cls",
        [
            "FatigueRestSignal",
            "SurfaceTransitionSignal",
            "H2HResidualSignal",
        ],
    )
    def test_scope_is_pregame(self, signal_cls: str) -> None:
        mod = importlib.import_module("domains.tennis.signals")
        cls = getattr(mod, signal_cls)
        assert cls.scope == "pregame"

    def test_expected_verdict_in_docstrings(self) -> None:
        """Each signal docstring must contain 'Expected gate verdict: REJECT'."""
        from domains.tennis.signals import (
            FatigueRestSignal,
            H2HResidualSignal,
            SurfaceTransitionSignal,
        )

        for cls in (FatigueRestSignal, SurfaceTransitionSignal, H2HResidualSignal):
            doc = cls.__doc__ or ""
            assert "Expected gate verdict:" in doc, (
                f"{cls.__name__} docstring must contain 'Expected gate verdict:'"
            )
            assert "REJECT" in doc, (
                f"{cls.__name__} docstring must contain 'REJECT' in expected verdict"
            )

    def test_hypothesis_expected_verdict_field(self) -> None:
        """Each signal's hypothesis() must have expected_verdict set."""
        from domains.tennis.signals import ALL_SIGNALS

        for cls in ALL_SIGNALS:
            sig = cls()
            hyp = sig.hypothesis()
            assert hyp.expected_verdict is not None, (
                f"{cls.__name__}.hypothesis().expected_verdict must not be None"
            )
            assert hyp.target == "winprob"

    def test_signal_build_returns_valid_output(self) -> None:
        """Signal.build() must return a valid SignalValue (float or None)."""
        from domains.tennis.signals import (
            FatigueRestSignal,
            H2HResidualSignal,
            SurfaceTransitionSignal,
        )

        base_ctx = {
            "decision_time": dt.datetime(2022, 6, 1, 12, 0),
        }

        # FatigueRestSignal
        from src.loop.signal import AsOfContext

        ctx = AsOfContext(
            decision_time=dt.datetime(2022, 6, 1, 12, 0),
            extra={"rest_days_a": 7.0, "rest_days_b": 2.0},
        )
        sig = FatigueRestSignal()
        val = sig.build(ctx)
        assert val is not None
        assert isinstance(val, float)
        assert sig.validate_output(val)

        # SurfaceTransitionSignal
        ctx2 = AsOfContext(
            decision_time=dt.datetime(2022, 6, 1, 12, 0),
            extra={"is_surface_transition": True},
        )
        sig2 = SurfaceTransitionSignal()
        val2 = sig2.build(ctx2)
        assert val2 == 1.0

        # H2HResidualSignal
        ctx3 = AsOfContext(
            decision_time=dt.datetime(2022, 6, 1, 12, 0),
            extra={"h2h_wins_a": 4, "h2h_total": 8, "elo_prob_a": 0.55},
        )
        sig3 = H2HResidualSignal()
        val3 = sig3.build(ctx3)
        assert val3 is not None
        assert isinstance(val3, float)

    def test_signal_build_returns_none_on_missing_data(self) -> None:
        """Signals must return None when required extra fields are absent."""
        from domains.tennis.signals import (
            FatigueRestSignal,
            H2HResidualSignal,
            SurfaceTransitionSignal,
        )
        from src.loop.signal import AsOfContext

        empty_ctx = AsOfContext(decision_time=dt.datetime(2022, 6, 1))

        for cls in (FatigueRestSignal, SurfaceTransitionSignal, H2HResidualSignal):
            sig = cls()
            val = sig.build(empty_ctx)
            assert val is None, (
                f"{cls.__name__}.build() must return None on missing extra data"
            )


# ---------------------------------------------------------------------------
# 3. F5 compliance — no basketball_nba / src.data imports
# ---------------------------------------------------------------------------

# Modules to audit for cross-domain imports
_ADAPTER_FILES = [
    REPO_ROOT / "domains" / "tennis" / "adapter.py",
    REPO_ROOT / "domains" / "tennis" / "signals.py",
    REPO_ROOT / "domains" / "tennis" / "config.py",
]

# Banned import patterns (F5 falsifier)
_BANNED_PREFIXES = (
    "domains.nba",
    "src.data",
    "src.sim",
    "src.tracking",
    "src.pipeline",
    "basketball_nba",
)


def _collect_imports(source: str) -> List[str]:
    """Return all top-level module names imported in ``source`` (AST walk)."""
    tree = ast.parse(source)
    names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
    return names


class TestF5Compliance:
    """Adapter/signals/config must import ZERO basketball_nba / src.data modules."""

    @pytest.mark.parametrize("filepath", _ADAPTER_FILES)
    def test_no_banned_imports(self, filepath: Path) -> None:
        source = filepath.read_text(encoding="utf-8")
        imports = _collect_imports(source)
        violations = [
            imp for imp in imports
            if any(imp == banned or imp.startswith(banned + ".")
                   for banned in _BANNED_PREFIXES)
        ]
        assert not violations, (
            f"{filepath.name} contains banned imports (F5 violation): {violations}"
        )

    def test_adapter_allowed_kernel_imports(self) -> None:
        """Adapter MAY import src.loop.gate and src.loop.signal (kernel seam)."""
        source = (REPO_ROOT / "domains" / "tennis" / "adapter.py").read_text(encoding="utf-8")
        imports = _collect_imports(source)
        kernel_seam = [i for i in imports if i.startswith("src.loop")]
        assert len(kernel_seam) > 0, (
            "adapter.py must import from src.loop (the proof mechanism)"
        )

    def test_signals_allowed_kernel_imports(self) -> None:
        """signals.py MAY import src.loop.signal (kernel seam)."""
        source = (REPO_ROOT / "domains" / "tennis" / "signals.py").read_text(encoding="utf-8")
        imports = _collect_imports(source)
        kernel_seam = [i for i in imports if i.startswith("src.loop")]
        assert len(kernel_seam) > 0, (
            "signals.py must import from src.loop.signal"
        )

    def test_config_imports_nothing_from_src(self) -> None:
        """config.py must import ZERO from src.*."""
        source = (REPO_ROOT / "domains" / "tennis" / "config.py").read_text(encoding="utf-8")
        imports = _collect_imports(source)
        src_imports = [i for i in imports if i.startswith("src.")]
        assert not src_imports, (
            f"config.py must not import from src.*; found: {src_imports}"
        )


# ---------------------------------------------------------------------------
# 4. TennisAdapter protocol methods (lightweight)
# ---------------------------------------------------------------------------


class TestAdapterMethods:
    """Lightweight checks on list_events / market_snapshot / outcome / baseline_prob."""

    def test_list_events_returns_list(self, adapter, matches_df) -> None:
        first_date = pd.to_datetime(matches_df["date"]).dt.date.iloc[0]
        events = adapter.list_events(first_date)
        assert isinstance(events, list)

    def test_list_events_event_ref_fields(self, adapter, matches_df) -> None:
        from domains.tennis.config import EventRef

        first_date = pd.to_datetime(matches_df["date"]).dt.date.iloc[0]
        events = adapter.list_events(first_date)
        if events:
            ev = events[0]
            assert isinstance(ev, EventRef)
            assert ev.sport == "tennis_atp"
            assert ev.entity_a
            assert ev.entity_b

    def test_market_snapshot_returns_snapshot_or_none(self, adapter, matches_df) -> None:
        from domains.tennis.config import EventRef

        first_date = pd.to_datetime(matches_df["date"]).dt.date.iloc[0]
        events = adapter.list_events(first_date)
        if events:
            snap = adapter.market_snapshot(events[0], kind="close")
            from domains.tennis.config import MarketSnapshot
            assert snap is None or isinstance(snap, MarketSnapshot)

    def test_baseline_probability_range(self, adapter, matches_df) -> None:
        """baseline_probability must be in (0, 1)."""
        first_date = pd.to_datetime(matches_df["date"]).dt.date.iloc[5]
        events = adapter.list_events(first_date)
        if events:
            p = adapter.baseline_probability(
                events[0], as_of=dt.datetime(first_date.year, first_date.month, first_date.day)
            )
            assert 0.0 < p < 1.0, f"baseline_probability out of range: {p}"

    def test_outcome_returns_outcome_or_none(self, adapter, matches_df) -> None:
        from domains.tennis.config import EventRef, Outcome

        first_date = pd.to_datetime(matches_df["date"]).dt.date.iloc[0]
        events = adapter.list_events(first_date)
        if events:
            out = adapter.outcome(events[0])
            assert out is None or isinstance(out, Outcome)

    def test_sport_id(self, adapter) -> None:
        assert adapter.sport == "tennis_atp"


# ---------------------------------------------------------------------------
# 5. Leak-regression: lines/closing must be P(p1), not P(winner)
# ---------------------------------------------------------------------------


class TestOddsLeakRegression:
    """Prove that lines/closing are outcome-blind P(p1), never P(winner).

    Key invariant (from ingest_tennisdata.py §Anti-Leak):
      _devig_prob reads ps_p1/ps_p2 (p1/p2-oriented) → P(p1 wins).
      The result must be < 0.5 when p1 is the underdog, regardless of whether
      p1 won or lost; and must be IDENTICAL for two rows with the same oriented
      prices but opposite winners.
    """

    def _make_single_odds_row(
        self,
        ps_p1: float,
        ps_p2: float,
    ) -> "pd.Series":
        """Build a minimal odds Series with oriented columns only."""
        return pd.Series({"ps_p1": ps_p1, "ps_p2": ps_p2})

    def test_p1_underdog_who_lost_gives_prob_below_half(self) -> None:
        """P(p1) < 0.5 when p1 is the underdog (ps_p1 > ps_p2), even if p1 lost.

        The winner column is not consulted at all — this tests that _devig_prob
        is purely outcome-blind.
        """
        from domains.tennis.adapter import _devig_prob

        # p1 is the underdog: higher decimal odds → lower implied probability
        # ps_p1=2.50 → imp ~0.40; ps_p2=1.55 → imp ~0.645; P(p1)~0.38
        row = self._make_single_odds_row(ps_p1=2.50, ps_p2=1.55)
        prob = _devig_prob(row, kind="close")
        assert not np.isnan(prob), "_devig_prob returned NaN on valid prices"
        assert prob < 0.5, (
            f"P(p1) should be < 0.5 for underdog p1 (ps_p1=2.50); got {prob:.4f}"
        )

    def test_same_oriented_prices_opposite_winners_give_identical_line(self) -> None:
        """Two rows with the same p1/p2 prices but different match outcomes must
        produce the exact same devigged P(p1) — proving no winner/loser leak.
        """
        from domains.tennis.adapter import _devig_prob

        ps_p1, ps_p2 = 2.10, 1.75  # fixed oriented prices

        # Row A: p1 LOST (winner=2); audit columns psw/psl would be SWAPPED
        row_p1_lost = pd.Series({
            "ps_p1": ps_p1, "ps_p2": ps_p2,
            "psw": ps_p2, "psl": ps_p1,   # audit-only; adapter must NOT read these
        })
        # Row B: p1 WON (winner=1); audit columns psw/psl match p1/p2
        row_p1_won = pd.Series({
            "ps_p1": ps_p1, "ps_p2": ps_p2,
            "psw": ps_p1, "psl": ps_p2,
        })

        prob_lost = _devig_prob(row_p1_lost, kind="close")
        prob_won = _devig_prob(row_p1_won, kind="close")

        assert prob_lost == prob_won, (
            f"_devig_prob must be outcome-blind: got {prob_lost:.6f} (p1 lost) "
            f"vs {prob_won:.6f} (p1 won) for identical oriented prices"
        )

    def test_market_snapshot_price_a_is_p1_price_not_winner_price(
        self, adapter, matches_df
    ) -> None:
        """market_snapshot.price_a must equal ps_p1 (p1's decimal odds), not
        the winner's decimal odds.  For a match where p1 LOST, the winner's
        price would be ps_p2 — so we confirm price_a != ps_p2 in that case.
        """
        from domains.tennis.config import EventRef

        # Find a match where p2 won (winner==2), so p1 lost
        p2_won = matches_df[matches_df["winner"] == 2]
        if p2_won.empty:
            pytest.skip("No p2-won matches in synthetic data (unlikely)")
        test_row = p2_won.iloc[0]
        event_id = test_row["event_id"]

        # Build a controlled odds frame for exactly this event
        ps_p1_val = 2.50   # p1 underdog
        ps_p2_val = 1.55   # p2 favourite
        controlled_odds = pd.DataFrame([{
            "event_id": event_id,
            "ps_p1": ps_p1_val,
            "ps_p2": ps_p2_val,
            "b365_p1": 2.40,
            "b365_p2": 1.50,
            "psw": ps_p2_val,   # audit: winner (p2) price
            "psl": ps_p1_val,   # audit: loser  (p1) price
            "b365w": 1.50,
            "b365l": 2.40,
        }])

        from domains.tennis.adapter import TennisAdapter
        local_adapter = TennisAdapter(
            matches_df=matches_df,
            odds_df=controlled_odds,
        )

        d = pd.to_datetime(test_row["date"]).date()
        events = local_adapter.list_events(d)
        target_events = [e for e in events if e.event_id == event_id]
        if not target_events:
            pytest.skip("list_events did not return the target event on its date")
        ev = target_events[0]

        snap = local_adapter.market_snapshot(ev, kind="close")
        assert snap is not None, "market_snapshot returned None for valid oriented prices"
        assert snap.price_a == pytest.approx(ps_p1_val), (
            f"price_a should be ps_p1={ps_p1_val} (p1's price), "
            f"not the winner's price={ps_p2_val}; got {snap.price_a}"
        )
        # price_b must be p2's price (the winner's price in this case)
        assert snap.price_b == pytest.approx(ps_p2_val), (
            f"price_b should be ps_p2={ps_p2_val}; got {snap.price_b}"
        )

    def test_feature_bundle_lines_consistent_across_opposite_winners(
        self, matches_df
    ) -> None:
        """For two synthetic matches with IDENTICAL oriented prices but opposite
        winners, the feature_bundle lines values must be identical (outcome-blind).
        """
        from domains.tennis.adapter import TennisAdapter
        from src.loop.signal import Hypothesis

        # Take two real match rows with opposite winners
        p1_won = matches_df[matches_df["winner"] == 1].iloc[0]
        p2_won = matches_df[matches_df["winner"] == 2].iloc[0]

        # Build a controlled odds frame: same oriented prices for both events
        fixed_ps_p1 = 2.10
        fixed_ps_p2 = 1.75
        controlled_odds = pd.DataFrame([
            {
                "event_id": p1_won["event_id"],
                "ps_p1": fixed_ps_p1, "ps_p2": fixed_ps_p2,
                "b365_p1": 2.0, "b365_p2": 1.70,
                "psw": fixed_ps_p1, "psl": fixed_ps_p2,  # p1 won → psw=p1 price
                "b365w": 2.0, "b365l": 1.70,
            },
            {
                "event_id": p2_won["event_id"],
                "ps_p1": fixed_ps_p1, "ps_p2": fixed_ps_p2,
                "b365_p1": 2.0, "b365_p2": 1.70,
                "psw": fixed_ps_p2, "psl": fixed_ps_p1,  # p2 won → psw=p2 price
                "b365w": 1.70, "b365l": 2.0,
            },
        ])

        local_adapter = TennisAdapter(matches_df=matches_df, odds_df=controlled_odds)

        # Use only the two specific seasons/dates to keep the bundle small
        date1 = pd.to_datetime(p1_won["date"]).year
        date2 = pd.to_datetime(p2_won["date"]).year
        seasons = list({date1, date2})

        hyp = Hypothesis(name="leak_check", target="winprob", scope="pregame",
                         statement="Leak regression.")
        fb = local_adapter.feature_bundle(hyp, seasons=seasons)

        # Extract lines for our two specific event_ids
        idx1 = fb.dates.index(str(pd.to_datetime(p1_won["date"]).date()))
        idx2 = fb.dates.index(str(pd.to_datetime(p2_won["date"]).date()))

        # Both lines values should be non-NaN
        assert not np.isnan(fb.lines[idx1]), "lines[p1_won] is NaN"
        assert not np.isnan(fb.lines[idx2]), "lines[p2_won] is NaN"

        # Same oriented prices → same devigged P(p1) regardless of winner
        assert fb.lines[idx1] == pytest.approx(fb.lines[idx2], abs=1e-6), (
            f"lines must be identical for same oriented prices regardless of winner; "
            f"p1_won={fb.lines[idx1]:.6f} p2_won={fb.lines[idx2]:.6f}"
        )


# ---------------------------------------------------------------------------
# 6. Config structural checks
# ---------------------------------------------------------------------------


class TestConfig:  # noqa: N801 — kept as section 6 to match file structure
    def test_sport_id(self) -> None:
        from domains.tennis.config import SPORT_ID

        assert SPORT_ID == "tennis_atp"

    def test_stat_registry_contains_winprob(self) -> None:
        from domains.tennis.config import STAT_REGISTRY

        assert "winprob" in STAT_REGISTRY

    def test_surfaces_non_empty(self) -> None:
        from domains.tennis.config import SURFACES

        assert len(SURFACES) >= 3

    def test_dataclasses_frozen(self) -> None:
        """EventRef, MarketSnapshot, Outcome must be frozen (immutable)."""
        from dataclasses import FrozenInstanceError
        from domains.tennis.config import EventRef

        ev = EventRef(
            sport="tennis_atp",
            event_id="test",
            start_time_utc=dt.datetime(2022, 6, 1),
            entity_a="1",
            entity_b="2",
        )
        # Direct attribute assignment must raise on a frozen dataclass
        with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
            ev.sport = "x"  # type: ignore[misc]

    def test_entity_schema(self) -> None:
        from domains.tennis.config import ENTITY_SCHEMA

        assert ENTITY_SCHEMA["entity_type"] == "player"
        assert ENTITY_SCHEMA["team"] is None
