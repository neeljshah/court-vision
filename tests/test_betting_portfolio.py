"""
test_betting_portfolio.py — Unit tests for betting_portfolio.py and betting_edge.py.

Covers: kelly_corr (quarter-Kelly, 4% cap, drawdown halt, 20-bet cap, corr matrix),
        detect_arb, backtest_clv, CLV tracker synthetic data, bankroll Monte Carlo.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.prediction.betting_portfolio import (
    ArbOpportunity,
    Bet,
    MAX_BET_PCT,
    MAX_DRAWDOWN_PCT,
    MAX_OPEN_BETS,
    KELLY_FRACTION,
    _american_to_prob,
    _american_to_payout,
    check_drawdown_ok,
    detect_arb,
    kelly_corr,
)


# ── kelly_corr ────────────────────────────────────────────────────────────────

class TestKellyCorr:

    def test_quarter_kelly_applied(self) -> None:
        """Result must be <= full-Kelly * KELLY_FRACTION (quarter-Kelly by default)."""
        edge = 0.06
        odds = -110
        bankroll = 1000.0
        result = kelly_corr(edge, odds, bankroll)
        b = _american_to_payout(odds)
        implied = _american_to_prob(odds)
        win_prob = min(0.95, implied + edge)
        q = 1.0 - win_prob
        full_kelly = (win_prob * b - q) / b
        quarter_kelly_dollars = full_kelly * KELLY_FRACTION * bankroll
        assert result <= quarter_kelly_dollars + 0.01  # float tolerance

    def test_four_pct_cap(self) -> None:
        """No single bet exceeds 4% of bankroll regardless of edge."""
        bankroll = 5000.0
        result = kelly_corr(0.30, +200, bankroll)  # huge edge
        assert result <= bankroll * MAX_BET_PCT + 0.01

    def test_drawdown_halt(self) -> None:
        """Returns 0 when drawdown from bankroll_start exceeds MAX_DRAWDOWN_PCT (15%)."""
        bankroll_start = 1000.0
        bankroll_now = bankroll_start * (1.0 - MAX_DRAWDOWN_PCT - 0.01)  # just over limit
        result = kelly_corr(0.06, -110, bankroll_now, bankroll_start=bankroll_start)
        assert result == 0.0

    def test_no_drawdown_halt_at_safe_level(self) -> None:
        """Returns positive bet when drawdown is well within limit."""
        bankroll_start = 1000.0
        bankroll_now = 920.0  # 8% drawdown — well under 15%
        result = kelly_corr(0.06, -110, bankroll_now, bankroll_start=bankroll_start)
        assert result > 0.0

    def test_negative_edge_returns_zero(self) -> None:
        """Kelly returns 0 for a losing bet (negative edge)."""
        result = kelly_corr(-0.05, -110, 1000.0)
        assert result == 0.0

    def test_correlation_reduction(self) -> None:
        """High correlation penalty reduces bet size."""
        no_corr = kelly_corr(0.06, -110, 1000.0, corr_with_open=0.0, existing_exposure=0.0)
        high_corr = kelly_corr(0.06, -110, 1000.0, corr_with_open=0.9, existing_exposure=500.0)
        assert high_corr <= no_corr

    def test_max_open_bets_constant(self) -> None:
        """MAX_OPEN_BETS is 20 (enforced at portfolio level)."""
        assert MAX_OPEN_BETS == 20


# ── check_drawdown_ok ─────────────────────────────────────────────────────────

class TestDrawdownGuard:

    def test_ok_when_no_loss(self) -> None:
        assert check_drawdown_ok(1000.0, 1000.0) is True

    def test_ok_at_14_pct(self) -> None:
        assert check_drawdown_ok(1000.0, 860.0) is True  # 14% < 15%

    def test_halt_at_15_pct(self) -> None:
        assert check_drawdown_ok(1000.0, 849.0) is False  # 15.1% > 15%

    def test_zero_start_safe(self) -> None:
        assert check_drawdown_ok(0.0, -100.0) is True  # guard: zero start → True


# ── detect_arb ────────────────────────────────────────────────────────────────

class TestDetectArb:

    def test_detects_true_arb(self) -> None:
        """Cross-book arb where over+under implied probs < 1.0."""
        lines = {
            "BookA": {"LeBron_pts": (25.5, +115, -125)},  # over +115
            "BookB": {"LeBron_pts": (25.5, -130, +130)},  # under +130
        }
        arbs = detect_arb(lines)
        assert len(arbs) >= 1
        assert arbs[0].arb_pct > 0

    def test_no_arb_standard_market(self) -> None:
        """Standard -110/-110 market has no arb."""
        lines = {
            "BookA": {"LeBron_pts": (25.5, -110, -110)},
            "BookB": {"LeBron_pts": (25.5, -110, -110)},
        }
        arbs = detect_arb(lines)
        assert len(arbs) == 0

    def test_single_book_no_arb(self) -> None:
        """Can't arb with only one book."""
        lines = {"BookA": {"Curry_pts": (28.5, +110, -120)}}
        arbs = detect_arb(lines)
        assert len(arbs) == 0

    def test_sorted_by_arb_pct_desc(self) -> None:
        """Multiple arbs are sorted by arb_pct descending."""
        lines = {
            "B1": {"A_pts": (20.0, +120, -115), "B_pts": (10.0, +150, -120)},
            "B2": {"A_pts": (20.0, -110, +140), "B_pts": (10.0, -100, +170)},
        }
        arbs = detect_arb(lines)
        if len(arbs) >= 2:
            assert arbs[0].arb_pct >= arbs[1].arb_pct


# ── backtest_clv ──────────────────────────────────────────────────────────────

class TestBacktestClv:

    def test_returns_dict(self) -> None:
        """backtest_clv returns a dict (may have 'error' key if no data)."""
        from src.analytics.betting_edge import backtest_clv
        result = backtest_clv(seasons=["2024-25"])
        assert isinstance(result, dict)

    def test_result_has_expected_keys_or_error(self) -> None:
        """Either full result keys or 'error'/'n_games' sentinel."""
        from src.analytics.betting_edge import backtest_clv
        result = backtest_clv(seasons=["2024-25"])
        full_keys = {"mean_clv", "std_clv", "pct_positive_clv",
                     "pct_correct_winner", "mae_spread", "n_games"}
        has_full = full_keys.issubset(result.keys())
        has_error = "error" in result or result.get("n_games", 0) == 0
        assert has_full or has_error, f"Unexpected result keys: {list(result.keys())}"


# ── CLV tracker with synthetic data ──────────────────────────────────────────

class TestClvTracker:

    def test_clv_tracker_import(self) -> None:
        """scripts/clv_tracker.py is importable and exposes update_clv_log."""
        import importlib
        mod = importlib.import_module("scripts.clv_tracker")
        assert hasattr(mod, "update_clv_log"), "update_clv_log not found in clv_tracker"

    def test_update_clv_log_with_synthetic_data(self, tmp_path: Path) -> None:
        """update_clv_log writes entries to a JSON log and computes realized CLV."""
        import importlib
        mod = importlib.import_module("scripts.clv_tracker")

        log_path = tmp_path / "clv_test.json"
        entries = [
            {"bet_id": "b1", "stat": "pts", "direction": "over",
             "opening_line": 24.5, "closing_line": 25.5, "edge_pct": 0.04},
            {"bet_id": "b2", "stat": "reb", "direction": "under",
             "opening_line": 8.5,  "closing_line": 7.5,  "edge_pct": 0.03},
        ]
        mod.update_clv_log(entries, log_path=str(log_path))
        assert log_path.exists()
        data = json.loads(log_path.read_text())
        assert len(data) == 2
        # Both entries should have computed CLV
        for entry in data:
            assert "clv" in entry
            assert isinstance(entry["clv"], float)

    def test_realized_clv_direction_over(self, tmp_path: Path) -> None:
        """Over bet: positive CLV when closing > opening (line moved in our favour)."""
        import importlib
        mod = importlib.import_module("scripts.clv_tracker")

        log_path = tmp_path / "clv_over.json"
        entries = [{"bet_id": "b_over", "stat": "pts", "direction": "over",
                    "opening_line": 24.5, "closing_line": 26.0, "edge_pct": 0.05}]
        mod.update_clv_log(entries, log_path=str(log_path))
        data = json.loads(log_path.read_text())
        assert data[0]["clv"] > 0, "Over bet should have positive CLV when line moved up"


# ── Bankroll Monte Carlo simulator ───────────────────────────────────────────

class TestBankrollMonteCarlo:

    def test_import(self) -> None:
        """scripts/bankroll_simulator.py is importable."""
        import importlib
        mod = importlib.import_module("scripts.bankroll_simulator")
        assert hasattr(mod, "simulate_bankroll")

    def test_simulate_returns_metrics(self) -> None:
        """simulate_bankroll returns drawdown_pct, ruin_prob, and final_bankroll_median."""
        import importlib
        mod = importlib.import_module("scripts.bankroll_simulator")
        result = mod.simulate_bankroll(
            n_bets=100, edge_mean=0.04, edge_std=0.02,
            kelly_fraction=0.25, bankroll=1000.0, n_simulations=200,
            seed=42,
        )
        assert isinstance(result, dict)
        assert "ruin_prob" in result
        assert "max_drawdown_pct" in result
        assert "final_bankroll_median" in result
        assert 0.0 <= result["ruin_prob"] <= 1.0

    def test_ruin_prob_increases_with_negative_edge(self) -> None:
        """Negative-edge sequences should have higher ruin probability than positive-edge."""
        import importlib
        mod = importlib.import_module("scripts.bankroll_simulator")

        pos = mod.simulate_bankroll(100, edge_mean=0.05, edge_std=0.01,
                                    kelly_fraction=0.25, bankroll=1000.0,
                                    n_simulations=500, seed=0)
        neg = mod.simulate_bankroll(100, edge_mean=-0.03, edge_std=0.01,
                                    kelly_fraction=0.25, bankroll=1000.0,
                                    n_simulations=500, seed=0)
        assert neg["ruin_prob"] >= pos["ruin_prob"]


# ── Prop correlation matrix (EX-8 hygiene) ───────────────────────────────────

class TestPropCorrMatrixV2:
    """Verify prop_corr_matrix.json holds v2 (Ledoit-Wolf + Higham PSD) values.

    v1 bug: index//7 pivot correlated arbitrary adjacent rows → pts-tov=0.80.
    v2 fix: residual-based (predicted - actual) correlation → pts-tov≈0.13.
    """

    def _load(self) -> Dict[str, Dict[str, float]]:
        from src.prediction.betting_portfolio import _load_corr_matrix
        mat = _load_corr_matrix()
        assert mat, "prop_corr_matrix.json missing or empty"
        return mat

    def test_pts_tov_not_inflated(self) -> None:
        """pts-tov must be < 0.30 (v1 was 0.7976, v2 is ~0.1334)."""
        mat = self._load()
        pts_tov = mat["pts"]["tov"]
        assert pts_tov < 0.30, (
            f"pts-tov = {pts_tov:.4f} — still inflated (v1 value). "
            "EX-8 fix may not have been applied."
        )

    def test_diagonal_ones(self) -> None:
        """Every stat must correlate 1.0 with itself."""
        mat = self._load()
        for stat in mat:
            assert mat[stat][stat] == 1.0, f"Diagonal {stat} != 1.0"

    def test_symmetric(self) -> None:
        """Matrix must be symmetric (corr[a][b] == corr[b][a])."""
        mat = self._load()
        stats = list(mat.keys())
        for s in stats:
            for t in stats:
                assert abs(mat[s][t] - mat[t][s]) < 1e-6, (
                    f"Not symmetric: {s}-{t}={mat[s][t]:.4f} vs {t}-{s}={mat[t][s]:.4f}"
                )

    def test_v2_spot_check_values(self) -> None:
        """Spot-check known v2 values from the EX-8 audit memo (±0.001 tolerance)."""
        mat = self._load()
        expected = {
            ("pts", "reb"):  0.3071,
            ("pts", "ast"):  0.1817,
            ("pts", "fg3m"): 0.6665,
            ("pts", "stl"):  0.1642,
            ("pts", "blk"):  0.0994,
            ("pts", "tov"):  0.1334,
        }
        for (s, t), v in expected.items():
            got = mat[s][t]
            assert abs(got - v) < 0.001, (
                f"{s}-{t}: expected ~{v}, got {got:.4f}"
            )


# ── REAL-MONEY TRIAGE 2026-06-01 ─────────────────────────────────────────────
# Edit 1: bankroll-start drawdown-guard gate (CV_INFER_BANKROLL_START, default OFF)
# Edit 2: side-aware record_clv
# Edit 3: residual corr matrix graceful missing-actual fallback


class TestBankrollStartGate:
    """CV_INFER_BANKROLL_START gates the inferred-start drawdown activation.

    Default OFF must be byte-identical to the ORIGINAL behavior: a None
    bankroll_start SKIPS the drawdown guard (returns a positive stake even when
    realized PnL implies a deep drawdown).  ON activates the inferred guard.
    """

    def test_flag_off_skips_guard_none_start(self, monkeypatch) -> None:
        """OFF + None start: guard is skipped, positive stake returned
        (old behavior preserved even though the bet log is empty/irrelevant)."""
        monkeypatch.delenv("CV_INFER_BANKROLL_START", raising=False)
        # bankroll_now well below any plausible inferred start; with the flag
        # OFF and start=None the guard must NOT fire.
        result = kelly_corr(0.06, -110, 500.0)  # bankroll_start omitted (None)
        assert result > 0.0

    def test_flag_off_explicit_start_still_guards(self, monkeypatch) -> None:
        """OFF must NOT change behavior when caller passes an explicit start:
        an explicit over-limit drawdown still halts."""
        monkeypatch.delenv("CV_INFER_BANKROLL_START", raising=False)
        start = 1000.0
        now = start * (1.0 - MAX_DRAWDOWN_PCT - 0.01)
        assert kelly_corr(0.06, -110, now, bankroll_start=start) == 0.0

    def test_flag_on_activates_inferred_guard(self, monkeypatch, tmp_path) -> None:
        """ON + None start: a bet log whose realized PnL implies a deep
        drawdown halts betting (stake 0.0) where OFF would have bet."""
        import src.prediction.betting_portfolio as bp
        # Synthetic bet log: net realized PnL = -300 → inferred start = now+300.
        # now=700 → start=1000 → drawdown 30% > 15% → guard fires.
        fake_log = [
            {"result": "loss", "pnl": -300.0},
            {"result": "win", "pnl": 0.0},
        ]
        monkeypatch.setattr(bp, "_load_bet_log", lambda: fake_log)
        monkeypatch.setenv("CV_INFER_BANKROLL_START", "1")
        result = bp.kelly_corr(0.06, -110, 700.0)  # None start, flag ON
        assert result == 0.0, "inferred-start guard should halt on 30% drawdown"

    def test_flag_on_no_history_is_safe_noop(self, monkeypatch) -> None:
        """ON + empty bet log: inferred start == current bankroll → drawdown 0
        → guard passes → positive stake (safe no-op default)."""
        import src.prediction.betting_portfolio as bp
        monkeypatch.setattr(bp, "_load_bet_log", lambda: [])
        monkeypatch.setenv("CV_INFER_BANKROLL_START", "1")
        assert bp.kelly_corr(0.06, -110, 700.0) > 0.0


class TestRecordClvSideAware:
    """record_clv() must be side-aware: positive CLV = we locked a BETTER number
    than the close (matches clv_tracker.py::_compute_clv convention).

    Convention:
      OVER  bet: CLV = (closing - opening) / |opening|  → positive when line
                 moves UP (we hold the lower/easier number to clear).
      UNDER bet: CLV = (opening - closing) / |opening|  → positive when line
                 moves DOWN (we hold the higher/easier number to stay under).

    Example: bet OVER 22.5, close at 24.5 → CLV > 0 (we beat the close).
    """

    def _setup_log(self, monkeypatch, tmp_path, direction: str,
                   opening: float):
        import src.prediction.betting_portfolio as bp
        bet = {"bet_id": "t1", "direction": direction, "line": opening,
               "stat": "pts", "player_name": "X", "edge_pct": 0.05,
               "placed_at": 0.0, "closing_line": None, "clv": None}
        store = {"bets": [dict(bet)]}
        monkeypatch.setattr(bp, "_load_bet_log", lambda: store["bets"])
        monkeypatch.setattr(bp, "_save_bet_log",
                            lambda b: store.update(bets=b))
        # Redirect the CLV side-log to a temp path so we never touch real data.
        monkeypatch.setattr(bp, "_CLV_LOG", str(tmp_path / "clv.json"))
        return bp, store

    def test_over_positive_when_line_rises(self, monkeypatch, tmp_path) -> None:
        """Over bet: line moved UP → we hold the easier (lower) number → positive CLV."""
        bp, store = self._setup_log(monkeypatch, tmp_path, "over", 24.5)
        bp.record_clv("t1", 25.5)  # line moved UP → good for over (we beat close)
        assert store["bets"][0]["clv"] > 0

    def test_over_negative_when_line_drops(self, monkeypatch, tmp_path) -> None:
        """Over bet: line moved DOWN → close is easier than our number → negative CLV."""
        bp, store = self._setup_log(monkeypatch, tmp_path, "over", 24.5)
        bp.record_clv("t1", 23.5)  # line moved DOWN → bad for over (close beat us)
        assert store["bets"][0]["clv"] < 0

    def test_under_positive_when_line_drops(self, monkeypatch, tmp_path) -> None:
        """Under bet: line moved DOWN → we hold the easier (higher) number → positive CLV."""
        bp, store = self._setup_log(monkeypatch, tmp_path, "under", 8.5)
        bp.record_clv("t1", 7.5)  # line moved DOWN → good for under (we beat close)
        assert store["bets"][0]["clv"] > 0

    def test_under_negative_when_line_rises(self, monkeypatch, tmp_path) -> None:
        """Under bet: line moved UP → close is easier than our number → negative CLV."""
        bp, store = self._setup_log(monkeypatch, tmp_path, "under", 8.5)
        bp.record_clv("t1", 9.5)  # line moved UP → bad for under (close beat us)
        assert store["bets"][0]["clv"] < 0

    def test_over_under_signs_are_mirror(self, monkeypatch, tmp_path) -> None:
        """Same line movement gives opposite-sign CLV for over vs under."""
        bp_o, store_o = self._setup_log(monkeypatch, tmp_path, "over", 20.0)
        bp_o.record_clv("t1", 21.0)
        over_clv = store_o["bets"][0]["clv"]
        bp_u, store_u = self._setup_log(monkeypatch, tmp_path, "under", 20.0)
        bp_u.record_clv("t1", 21.0)
        under_clv = store_u["bets"][0]["clv"]
        assert abs(over_clv + under_clv) < 1e-9, "over/under CLV must be mirror"


class TestCorrMatrixMissingActual:
    """compute_prop_corr_matrix must NOT crash when rows lack 'actual'; it
    drops them and returns {} when <10 complete rows survive (graceful)."""

    def test_missing_actual_returns_empty_dict(self, tmp_path) -> None:
        from src.prediction.betting_portfolio import compute_prop_corr_matrix
        # Rows have predicted but NO actual → all dropped → empty result.
        rows = []
        for g in range(20):
            for s in ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]:
                rows.append({"stat": s, "predicted": 10.0,
                             "player_id": 1, "game_date": f"g{g}"})
        p = tmp_path / "resid.json"
        p.write_text(json.dumps(rows))
        result = compute_prop_corr_matrix(str(p))
        assert result == {}, "missing actual must yield graceful empty dict"

    def test_missing_file_returns_empty_dict(self, tmp_path) -> None:
        from src.prediction.betting_portfolio import compute_prop_corr_matrix
        result = compute_prop_corr_matrix(str(tmp_path / "does_not_exist.json"))
        assert result == {}

    def test_residual_corr_computes_when_actual_present(
        self, tmp_path, monkeypatch
    ) -> None:
        """With actual present and a real signal, corr matrix is built and
        captures the (predicted-actual) relationship (sanity: diag == 1.0).

        Redirect the OUTPUT path so this test never clobbers the real
        data/models/prop_corr_matrix.json artifact.
        """
        import random
        import src.prediction.betting_portfolio as bp
        monkeypatch.setattr(bp, "_CORR_MATRIX", str(tmp_path / "out.json"))
        rng = random.Random(0)
        stats = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
        rows = []
        for g in range(40):
            shared = rng.gauss(0, 1)
            for s in stats:
                resid = shared + rng.gauss(0, 1)
                rows.append({"stat": s, "predicted": 10.0 + resid,
                             "actual": 10.0, "player_id": 1,
                             "game_date": f"g{g}"})
        p = tmp_path / "resid_full.json"
        p.write_text(json.dumps(rows))
        result = bp.compute_prop_corr_matrix(str(p))
        assert result, "should build a matrix with actual present"
        assert all(result[s][s] == 1.0 for s in stats)
