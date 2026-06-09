"""test_full_system.py -- guards the COMPOSITION SPINE (scripts/team_system/full_system.py).

These tests assert the spine COMPOSES (does not reimplement) and runs the heavy
sim ONCE. They use a tiny synthetic GameSimResult stub so they never touch the
GPU / sim cache, and they monkeypatch prop_engine.run to (a) avoid a real sim and
(b) count invocations -- proving single-sim discipline.

honesty_class assertions guard the paper/serve contract: no real-money path.
"""
import os
import sys

import numpy as np
import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "scripts", "team_system"), os.path.join(_ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import full_system as fs  # noqa: E402


# ---------------------------------------------------------------------------
# Minimal GameSimResult stub (duck-typed: the fields the spine + downstream read)
# ---------------------------------------------------------------------------
class _StubResult:
    def __init__(self, n=600):
        rng = np.random.default_rng(7)
        self.home_tri = "NYK"
        self.away_tri = "SAS"
        self.home_total = rng.normal(112, 11, n)
        self.away_total = rng.normal(108, 11, n)
        self.home_win_prob = float((self.home_total > self.away_total).mean())
        self.players = {}
        specs = [(101, "NYK", 26.0), (102, "NYK", 14.0), (201, "SAS", 24.0), (202, "SAS", 9.0)]
        for pid, team, mu in specs:
            pts = np.clip(rng.normal(mu, 6, n), 0, None)
            reb = np.clip(rng.normal(mu * 0.32, 3, n), 0, None)
            ast = np.clip(rng.normal(mu * 0.28, 2.5, n), 0, None)
            samples = {
                "pts": pts, "reb": reb, "ast": ast,
                "stl": np.clip(rng.normal(1.1, 1, n), 0, None),
                "blk": np.clip(rng.normal(0.6, 0.9, n), 0, None),
                "tov": np.clip(rng.normal(2.2, 1.4, n), 0, None),
                "fg3m": np.clip(rng.normal(2.0, 1.6, n), 0, None),
                "ftm": np.clip(rng.normal(3.5, 2.2, n), 0, None),
                "fga": np.clip(rng.normal(mu * 0.7, 4, n), 0, None),
                "fgm": np.clip(rng.normal(mu * 0.38, 3, n), 0, None),
                "oreb": np.clip(rng.normal(1.2, 1.1, n), 0, None),
                "dreb": np.clip(rng.normal(mu * 0.22, 2.5, n), 0, None),
                "pf": np.clip(rng.normal(2.4, 1.3, n), 0, None),
            }
            self.players[pid] = {
                "name": f"P{pid}", "team": team,
                "mean": {k: float(v.mean()) for k, v in samples.items()},
                "q50": {"pts": float(np.median(pts))},
                "samples": samples,
            }


@pytest.fixture
def stub_result():
    return _StubResult()


@pytest.fixture
def patched_run(monkeypatch, stub_result):
    """Patch prop_engine.run to return the stub and count calls (single-sim proof)."""
    import prop_engine
    calls = {"n": 0}

    def _fake_run(home, away, nsims, asof, no_avail):
        calls["n"] += 1
        return stub_result

    monkeypatch.setattr(prop_engine, "run", _fake_run)
    # full_system imports `run` into its own namespace at call time (local import),
    # so patching prop_engine.run is sufficient.
    return calls


# ---------------------------------------------------------------------------
# Core composition + single-sim discipline
# ---------------------------------------------------------------------------
def test_system_predict_runs_sim_once(patched_run):
    out = fs.system_predict("NYK", "SAS", nsims=300)
    assert patched_run["n"] == 1, "the heavy sim must run exactly ONCE"


def test_system_predict_shape_and_honesty(patched_run):
    out = fs.system_predict("NYK", "SAS", nsims=300)
    assert out["honesty_class"] == "paper"
    assert out["matchup"] == "SAS@NYK"
    for key in ("ensemble", "sim_slate", "sportsbook", "sgp_edges",
                "proven_edge_card", "board_html", "degraded"):
        assert key in out
    # render not requested + gate off -> no board html
    assert out["board_html"] is None


def test_sim_slate_per_player(patched_run, stub_result):
    out = fs.system_predict("NYK", "SAS", nsims=300)
    sl = out["sim_slate"]
    assert isinstance(sl, dict) and len(sl) == len(stub_result.players)


def test_no_real_money_path():
    """The spine source must never reference real-money placement APIs."""
    src = open(fs.__file__, encoding="utf-8").read()
    for forbidden in ("log_bet", "record_clv", "bet_log.json", "golive", "place_bet"):
        assert forbidden not in src, f"spine must not touch real-money path: {forbidden}"


def test_spine_does_not_reimplement():
    """Spine must compose, not redefine, the downstream engines."""
    src = open(fs.__file__, encoding="utf-8").read()
    # it imports them rather than defining their public callables
    for imported in ("price_markets", "build_portfolio", "scan_sgp_edges",
                     "build_proven_edge_card", "player_props"):
        assert imported in src
    for redefine in ("def price_markets", "def build_portfolio", "def scan_sgp_edges",
                     "def build_proven_edge_card"):
        assert redefine not in src, f"spine must not reimplement {redefine}"


# ---------------------------------------------------------------------------
# Graceful degrade: a downstream module that raises must not crash the spine
# ---------------------------------------------------------------------------
def test_degrade_on_downstream_failure(patched_run, monkeypatch):
    import sgp_edge_scanner
    monkeypatch.setattr(sgp_edge_scanner, "scan_sgp_edges",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    out = fs.system_predict("NYK", "SAS", nsims=300)
    assert "sgp_edges" in out["degraded"]
    assert isinstance(out["sgp_edges"], str) and "unavailable" in out["sgp_edges"]
    # other sections still populated -> degrade is isolated
    assert isinstance(out["sim_slate"], dict)


def test_board_gate_default_off(patched_run, monkeypatch):
    monkeypatch.delenv("CV_FULL_SYSTEM_BOARD", raising=False)
    out = fs.system_predict("NYK", "SAS", nsims=300, render=False)
    assert out["board_html"] is None


# ---------------------------------------------------------------------------
# print_summary must not raise on either dict (incl. degraded)
# ---------------------------------------------------------------------------
def test_print_summary_predict(patched_run, capsys):
    out = fs.system_predict("NYK", "SAS", nsims=300)
    fs.print_summary(out)
    cap = capsys.readouterr().out
    assert "FULL SYSTEM (paper)" in cap and "honesty_class=paper" in cap


def test_live_replay_degrades_cleanly(monkeypatch):
    import live_replay_harness
    monkeypatch.setattr(live_replay_harness, "replay_game",
                        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("no pbp")))
    out = fs.system_live_replay("0042500401")
    assert out["honesty_class"] == "serve"
    assert out["n_steps"] == 0
    assert "live_replay" in out["degraded"]
    fs.print_summary(out)  # must not raise


def test_live_replay_summary_with_steps(monkeypatch):
    from live_replay_harness import ReplayStep
    step = ReplayStep(
        action_idx=300, period=4, clock_sec=0.0, elapsed_sec=2880.0, sec_remaining=0.0,
        home_score=110, away_score=105, proj_home_final=110.0, proj_away_final=105.0,
        home_win_prob=0.99, winprob_coherent=0.99, reprice_ms=1.0, coherent=True,
    )
    import live_replay_harness
    monkeypatch.setattr(live_replay_harness, "replay_game", lambda *a, **k: [step])
    out = fs.system_live_replay("0042500401")
    assert out["n_steps"] == 1
    assert out["final_step"]["home_score"] == 110
    assert isinstance(out["winprob_check"], float)
    fs.print_summary(out)
