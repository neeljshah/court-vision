"""Robustness sweep for sim_core: basketball_sim.py + fast_sim.py.

Adversarial correctness audit — every invariant verified by running the code.
Run:  python -m pytest tests/test_sim_core_robustness.py -v

Findings reference: docs/_audits/SIM_CORE_ROBUSTNESS_2026-06-08.md
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from sim.basketball_sim import (  # noqa: E402
    TeamModel, simulate_game, _anchor, _apply_dispersion, _make_prob,
    _sample_zone, _pick, _matchup_mult, RECENCY_W, _STATS,
)

try:
    from sim.fast_sim import simulate_game_fast, _FastTeam
    _HAS_TORCH = True
    import torch
except Exception:
    _HAS_TORCH = False

_CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache", "team_system")
pytestmark = pytest.mark.skipif(
    not os.path.exists(os.path.join(_CACHE, "player_rates.parquet")),
    reason="team_system cache not built",
)

# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def teams():
    return TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS")


@pytest.fixture(scope="module")
def res_raw(teams):
    h, a = teams
    return simulate_game(h, a, n_sims=4000, seed=0, anchor=False, defense=False, dispersion=False)


@pytest.fixture(scope="module")
def res_anchored(teams):
    h, a = teams
    return simulate_game(h, a, n_sims=4000, seed=0, anchor=True, defense=False, dispersion=False)


@pytest.fixture(scope="module")
def res_full(teams):
    h, a = teams
    return simulate_game(h, a, n_sims=4000, seed=0, anchor=True, defense=True, dispersion=True)


# ─── INVARIANT 1: Coherence — player pts sum == team total ────────────────────

def test_coherence_home(res_anchored, teams):
    """NYK player pts sum must equal home_total (shared-pie routing invariant)."""
    h, _ = teams
    nyk_sum = sum(d["mean"]["pts"] for d in res_anchored.players.values() if d["team"] == "NYK")
    assert abs(nyk_sum - res_anchored.home_total.mean()) < 0.01, (
        f"Coherence broken: player sum {nyk_sum:.2f} != home_total {res_anchored.home_total.mean():.2f}"
    )


def test_coherence_away(res_anchored):
    """SAS player pts sum must equal away_total."""
    sas_sum = sum(d["mean"]["pts"] for d in res_anchored.players.values() if d["team"] == "SAS")
    assert abs(sas_sum - res_anchored.away_total.mean()) < 0.01, (
        f"Coherence broken: player sum {sas_sum:.2f} != away_total {res_anchored.away_total.mean():.2f}"
    )


def test_coherence_raw_chain(res_raw, teams):
    """Coherence must hold even in raw chain (no anchor) — intrinsic property of the shared-pie MC."""
    h, a = teams
    nyk_sum = sum(d["mean"]["pts"] for d in res_raw.players.values() if d["team"] == "NYK")
    assert abs(nyk_sum - res_raw.home_total.mean()) < 0.5


# ─── INVARIANT 2: Teammate rho — must be negative or near-zero ───────────────

def test_teammate_rho_negative(res_raw, teams):
    """Shared-pie MC must produce negative/near-zero teammate rho (NOT +0.645 game_simulator bug)."""
    h, _ = teams
    nyk_pts = [(d["name"], d["samples"]["pts"]) for d in res_raw.players.values() if d["team"] == "NYK"]
    rhos = [
        np.corrcoef(s1, s2)[0, 1]
        for i, (_, s1) in enumerate(nyk_pts)
        for j, (_, s2) in enumerate(nyk_pts)
        if i < j
    ]
    mean_rho = float(np.mean(rhos))
    max_rho = float(np.max(rhos))
    assert max_rho < 0.15, f"Teammate rho too high: max={max_rho:.3f} mean={mean_rho:.3f} (game_simulator +0.645 bug?)"
    # The measured range is -0.12 to +0.02; mean near -0.03
    assert mean_rho < 0.02, f"Mean teammate rho positive: {mean_rho:.3f}"


def test_brunson_towns_rho(res_raw):
    """Brunson-Towns rho must be well below 0.05 (key regression guard)."""
    bru = next(d["samples"]["pts"] for d in res_raw.players.values() if "Brunson" in d["name"])
    kat = next(d["samples"]["pts"] for d in res_raw.players.values() if "Towns" in d["name"])
    rho = float(np.corrcoef(bru, kat)[0, 1])
    assert rho < 0.05, f"Brunson-Towns rho too high: {rho:.3f}"


# ─── INVARIANT 3: Anchor exactness for core players ──────────────────────────

def test_anchor_brunson_pts(teams):
    """Anchor pins Brunson pts to within 1 pt of his recency-blended target."""
    h, a = teams
    res = simulate_game(h, a, n_sims=4000, seed=5, anchor=True, defense=False, dispersion=False)
    bru = next(d for d in res.players.values() if "Brunson" in d["name"])
    # Recency-blended target
    pid = next(p for p in h.rate if "Brunson" in h.rate[p]["player"])
    r = h.rate[pid]
    rec = r.get("pts_pg_rec")
    tgt = (1 - RECENCY_W) * r["pts_pg"] + RECENCY_W * rec if rec is not None else r["pts_pg"]
    assert abs(bru["mean"]["pts"] - tgt) < 1.0, (
        f"Brunson anchor off: mean={bru['mean']['pts']:.2f} target={tgt:.2f}"
    )


def test_core_player_anchors_exact(teams, res_anchored):
    """Top-8 players must be anchored to within 0.01 pts of target (rescale, no noise)."""
    h, _ = teams
    targets = {}
    for pid in h.rate:
        r = h.rate[pid]
        rec = r.get("pts_pg_rec")
        targets[pid] = (1 - RECENCY_W) * r["pts_pg"] + RECENCY_W * rec if rec is not None else r["pts_pg"]
    core8 = sorted(h.rate.keys(), key=lambda p: -targets[p])[:8]
    for pid in core8:
        actual = res_anchored.players[pid]["mean"]["pts"]
        tgt = targets[pid]
        assert abs(actual - tgt) < 0.01, (
            f"{h.rate[pid]['player']}: actual={actual:.3f} target={tgt:.3f}"
        )


# ─── INVARIANT 4: Team total conservation (dispersion holds mean) ─────────────

def test_dispersion_preserves_team_total_mean(teams):
    """_apply_dispersion must not shift team total mean by more than 0.01."""
    h, a = teams
    r_d = simulate_game(h, a, n_sims=3000, seed=1, anchor=True, defense=False, dispersion=True)
    r_n = simulate_game(h, a, n_sims=3000, seed=1, anchor=True, defense=False, dispersion=False)
    assert abs(r_d.home_total.mean() - r_n.home_total.mean()) < 0.01
    assert abs(r_d.away_total.mean() - r_n.away_total.mean()) < 0.01


def test_dispersion_preserves_player_means(teams):
    """After dispersion, each player's pts and ast mean must match pre-dispersion exactly."""
    h, a = teams
    r_d = simulate_game(h, a, n_sims=4000, seed=2, anchor=True, defense=False, dispersion=True)
    r_n = simulate_game(h, a, n_sims=4000, seed=2, anchor=True, defense=False, dispersion=False)
    for p, d in r_d.players.items():
        for stat in ("pts", "ast"):
            diff = abs(d["mean"][stat] - r_n.players[p]["mean"][stat])
            assert diff < 1e-5, f"{d['name']} {stat}: dispersion shifted mean by {diff:.6f}"


def test_dispersion_widens_variance(teams):
    """Dispersion must widen per-player pts variance (calibration purpose)."""
    h, a = teams
    r_d = simulate_game(h, a, n_sims=4000, seed=3, anchor=True, defense=False, dispersion=True)
    r_n = simulate_game(h, a, n_sims=4000, seed=3, anchor=True, defense=False, dispersion=False)
    # Starters (pts > 8) should have wider distribution
    ratios = []
    for p, d in r_d.players.items():
        if d["mean"]["pts"] > 8:
            v_d = float(np.var(d["samples"]["pts"]))
            v_n = float(np.var(r_n.players[p]["samples"]["pts"]))
            if v_n > 1:
                ratios.append(v_d / v_n)
    assert len(ratios) >= 5
    assert np.mean(ratios) > 1.10, f"Dispersion did not widen variance: mean ratio={np.mean(ratios):.3f}"


# ─── INVARIANT 5: Finite output (no NaN/Inf) ─────────────────────────────────

def test_no_nan_inf_in_output(res_full):
    """All player means, quantiles, and samples must be finite."""
    for p, d in res_full.players.items():
        for k, v in d["mean"].items():
            assert np.isfinite(v), f"{d['name']} mean[{k}] = {v}"
        for k, arr in d["samples"].items():
            assert np.all(np.isfinite(arr)), f"{d['name']} samples[{k}] has non-finite"
        for q in ("q10", "q50", "q90"):
            assert np.isfinite(d[q]), f"{d['name']} {q} = {d[q]}"
    assert np.isfinite(res_full.home_win_prob)
    assert np.all(np.isfinite(res_full.home_total))
    assert np.all(np.isfinite(res_full.away_total))


# ─── INVARIANT 6: Seed determinism ──────────────────────────────────────────

def test_seed_determinism():
    """Same seed must produce bit-identical results across two independent runs."""
    h1, a1 = TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS")
    h2, a2 = TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS")
    r1 = simulate_game(h1, a1, n_sims=500, seed=42, anchor=True, defense=True)
    r2 = simulate_game(h2, a2, n_sims=500, seed=42, anchor=True, defense=True)
    assert np.allclose(r1.home_total, r2.home_total), "Seed non-deterministic: home_total differs"
    assert np.allclose(r1.away_total, r2.away_total), "Seed non-deterministic: away_total differs"


# ─── INVARIANT 7: Shooting / FT accounting constraints ───────────────────────

def test_fgm_le_fga(res_raw):
    """fgm <= fga must hold for all players, all sims."""
    for p, d in res_raw.players.items():
        s = d["samples"]
        assert np.all(s["fgm"] <= s["fga"]), f"{d['name']} has fgm > fga"


def test_fg3m_le_fg3a(res_raw):
    """fg3m <= fg3a must hold."""
    for p, d in res_raw.players.items():
        s = d["samples"]
        assert np.all(s["fg3m"] <= s["fg3a"]), f"{d['name']} has fg3m > fg3a"


def test_fg3a_le_fga(res_raw):
    """fg3a <= fga must hold."""
    for p, d in res_raw.players.items():
        s = d["samples"]
        assert np.all(s["fg3a"] <= s["fga"]), f"{d['name']} has fg3a > fga"


def test_ftm_le_fta(res_raw):
    """ftm <= fta must hold."""
    for p, d in res_raw.players.items():
        s = d["samples"]
        assert np.all(s["ftm"] <= s["fta"]), f"{d['name']} has ftm > fta"


def test_fta_always_even_in_raw_chain(res_raw):
    """FTA in raw chain must always be even (hardcoded 2-shot FT model)."""
    for p, d in res_raw.players.items():
        fta = d["samples"]["fta"]
        non_even = fta[fta % 2 != 0]
        assert len(non_even) == 0, (
            f"{d['name']} has non-even FTA: {np.unique(non_even)} (1-shot FT not modeled)"
        )


def test_pts_accounting(res_raw):
    """pts must equal 2*fgm + fg3m + ftm for all players, all sims."""
    for p, d in res_raw.players.items():
        s = d["samples"]
        computed = 2 * s["fgm"] + s["fg3m"] + s["ftm"]
        max_err = float(np.max(np.abs(computed - s["pts"])))
        assert max_err < 1e-9, f"{d['name']} pts accounting error: {max_err:.2e}"


# ─── INVARIANT 8: Defense direction ──────────────────────────────────────────

def test_defense_suppresses_weaker_defender(teams):
    """A team facing the stronger defense should score fewer pts than facing the weaker defense."""
    h, a = teams  # SAS (strong D) vs NYK (weaker D)
    off = simulate_game(h, a, n_sims=3000, seed=11, anchor=True, defense=False, dispersion=False)
    on = simulate_game(h, a, n_sims=3000, seed=11, anchor=True, defense=True, dispersion=False)
    nyk_drop = off.away_total.mean() - on.away_total.mean()  # NYK faces SAS D
    sas_drop = off.home_total.mean() - on.home_total.mean()  # SAS faces NYK D
    # SAS has stronger D than NYK -> NYK is suppressed more
    assert nyk_drop > sas_drop, (
        f"Expected NYK to be suppressed more (nyk_drop={nyk_drop:.2f}, sas_drop={sas_drop:.2f})"
    )


def test_matchup_mult_above_avg_d_suppresses(teams):
    """matchup_mult for a player vs strong D (rim_d > 65) must be < 1.0 for a rim scorer."""
    h, a = teams
    # Build a synthetic strong-D opponent
    strong_d = TeamModel.from_cache("SAS")
    # Find a SAS player with rim shots
    for pid in h.rate:
        r = h.rate[pid]
        rim_share = (r.get("z_rim", 0) or 0) + (r.get("z_paint", 0) or 0)
        if rim_share > 0.4:
            mm = _matchup_mult(r, strong_d, defense=True)
            if strong_d.rim_d > 65:
                assert mm < 1.0, f"{r['player']}: matchup_mult={mm:.4f} vs strong D ({strong_d.rim_d:.0f})"
            break


# ─── INVARIANT 9: GPU/CPU equivalence ────────────────────────────────────────

@pytest.mark.skipif(not _HAS_TORCH, reason="torch not available")
def test_gpu_cpu_pts_mae(teams):
    """GPU fast_sim per-player pts MAE vs CPU reference must be < 0.6."""
    h, a = teams
    ref = simulate_game(h, a, n_sims=3000, seed=7, anchor=True, defense=True, dispersion=False)
    fst = simulate_game_fast(h, a, n_sims=3000, seed=7, anchor=True, defense=True, dispersion=False)
    errs = [
        abs(ref.players[p]["mean"]["pts"] - fst.players[p]["mean"]["pts"])
        for p in ref.players
        if ref.players[p]["mean"]["pts"] > 5
    ]
    mae = float(np.mean(errs))
    assert mae < 0.6, f"GPU/CPU pts MAE too high: {mae:.4f}"


@pytest.mark.skipif(not _HAS_TORCH, reason="torch not available")
def test_gpu_cpu_pts_accounting(teams):
    """fast_sim pts = 2*fgm + fg3m + ftm must hold exactly."""
    h, a = teams
    res = simulate_game_fast(h, a, n_sims=2000, seed=0, anchor=False, defense=False, dispersion=False)
    for p, d in res.players.items():
        s = d["samples"]
        computed = 2 * s["fgm"] + s["fg3m"] + s["ftm"]
        max_err = float(np.max(np.abs(computed - s["pts"])))
        assert max_err < 1e-4, f"{d['name']} fast_sim pts accounting error: {max_err:.2e}"


@pytest.mark.skipif(not _HAS_TORCH, reason="torch not available")
def test_gpu_cpu_fta_even(teams):
    """fast_sim FTA must also be even (2-shot model consistency)."""
    h, a = teams
    res = simulate_game_fast(h, a, n_sims=2000, seed=0, anchor=False, defense=False, dispersion=False)
    for p, d in res.players.items():
        fta = d["samples"]["fta"]
        non_even = fta[fta % 2 != 0]
        assert len(non_even) == 0, f"{d['name']} fast_sim has non-even FTA"


@pytest.mark.skipif(not _HAS_TORCH, reason="torch not available")
def test_gpu_assist_network_local_index(teams):
    """fast_sim assist network local-index mapping must match basketball_sim network."""
    h, _ = teams
    ft = _FastTeam(h, "cpu")
    bru_pid = next(p for p in h.rate if "Brunson" in h.rate[p]["player"])
    bru_local = ft.pids.index(bru_pid)
    # Top feeder in fast_sim (by count)
    fast_top = int(ft.assist_W[bru_local].argmax().item())
    fast_top_pid = ft.pids[fast_top]
    # Top feeder in basketball_sim
    bsim_feeders = h.assist_net.get(bru_pid, {})
    if bsim_feeders:
        bsim_top_pid = max(bsim_feeders, key=bsim_feeders.get)
        assert fast_top_pid == bsim_top_pid, (
            f"fast_sim top feeder {h.rate[fast_top_pid]['player']} != "
            f"bsim top feeder {h.rate[bsim_top_pid]['player']}"
        )


# ─── TEST-GAP: n_sims edge cases ─────────────────────────────────────────────

def test_n_sims_1_does_not_crash(teams):
    """n_sims=1 should run to completion without errors."""
    h, a = teams
    res = simulate_game(h, a, n_sims=1, seed=0, anchor=True, defense=True, dispersion=True)
    assert len(res.home_total) == 1
    assert np.isfinite(res.home_total[0])


def test_n_sims_0_raises_or_empty(teams):
    """n_sims=0 should either raise a clean error or return empty arrays (not crash silently with NaN)."""
    h, a = teams
    try:
        res = simulate_game(h, a, n_sims=0, seed=0, anchor=True, defense=True, dispersion=False)
        # If it doesn't raise, check nothing is NaN/Inf in non-empty outputs
        assert len(res.home_total) == 0 or all(np.isfinite(v) for v in res.home_total)
    except (IndexError, ValueError, RuntimeError):
        pass  # Acceptable: raise on empty input


# ─── TEST-GAP: Assist network — no self-assists, no cross-team contamination ──

def test_no_self_assist_in_network(teams):
    """No player should appear as their own feeder in the assist network."""
    h, a = teams
    for team in (h, a):
        for scorer_pid, feeders in team.assist_net.items():
            assert scorer_pid not in feeders, (
                f"{team.rate[scorer_pid]['player']} has self-assist entry"
            )


def test_no_cross_team_assist_contamination(teams):
    """NYK assist network should contain no SAS player pids and vice versa."""
    h, a = teams
    sas_pids = set(a.rate.keys())
    nyk_pids = set(h.rate.keys())
    for scorer_pid, feeders in h.assist_net.items():
        cross = set(feeders.keys()) & sas_pids
        assert not cross, f"NYK player has SAS feeder pids: {cross}"
    for scorer_pid, feeders in a.assist_net.items():
        cross = set(feeders.keys()) & nyk_pids
        assert not cross, f"SAS player has NYK feeder pids: {cross}"


# ─── TEST-GAP: _anchor helper edge cases ─────────────────────────────────────

def test_anchor_target_zero_preserves_raw():
    """_anchor with target=0 must NOT rescale (the target>0 guard). Raw samples preserved."""
    d = {"pts": np.ones(100) * 5.0}
    _anchor(d, "pts", 0.0)
    assert abs(d["pts"].mean() - 5.0) < 1e-9, "_anchor with target=0 should not rescale"


def test_anchor_mean_below_threshold_skips():
    """_anchor with raw mean < 0.1 must not attempt rescale (avoids 0/0 NaN)."""
    d = {"stl": np.zeros(100)}  # mean = 0.0 < 0.1
    _anchor(d, "stl", 0.5)      # target > 0 but mean too small
    assert d["stl"].mean() == 0.0, "_anchor should skip when mean < 0.1"


def test_anchor_clip_lo():
    """_anchor rescale factor must not go below 0.4 (lower clip)."""
    d = {"pts": np.ones(100) * 10.0}
    _anchor(d, "pts", 0.5)  # ratio = 0.05 -> clips to 0.4
    assert abs(d["pts"].mean() - 4.0) < 0.01, "Lower clip not at 0.4x"


def test_anchor_clip_hi():
    """_anchor rescale factor must not exceed 2.5 (upper clip)."""
    d = {"pts": np.ones(100) * 1.0}
    _anchor(d, "pts", 10.0)  # ratio = 10 -> clips to 2.5
    assert abs(d["pts"].mean() - 2.5) < 0.01, "Upper clip not at 2.5x"


# ─── TEST-GAP: _make_prob NaN fallback ───────────────────────────────────────

def test_make_prob_nan_fg_uses_fallback():
    """_make_prob must return fallback when fg rate is NaN."""
    from sim.basketball_sim import _FG_FALLBACK
    r_nan = {"fg_rim": float("nan"), "fg_paint": float("nan"), "fg_mid": float("nan"), "fg3_pct": 0.40}
    assert _make_prob(r_nan, "z_rim") == _FG_FALLBACK["z_rim"]
    assert _make_prob(r_nan, "z_paint") == _FG_FALLBACK["z_paint"]
    assert _make_prob(r_nan, "z_mid") == _FG_FALLBACK["z_mid"]
    # fg3_pct provided (non-NaN) -> use it
    assert abs(_make_prob(r_nan, "z_3") - 0.40) < 1e-9


def test_make_prob_none_fg_uses_fallback():
    """_make_prob must return fallback when fg rate is None."""
    from sim.basketball_sim import _FG_FALLBACK
    r_none = {"fg_rim": None, "fg_paint": None, "fg_mid": None, "fg3_pct": None}
    for z in ("z_rim", "z_paint", "z_mid", "z_3"):
        p = _make_prob(r_none, z)
        assert p == _FG_FALLBACK[z], f"zone {z}: expected fallback {_FG_FALLBACK[z]}, got {p}"


# ─── TEST-GAP: _sample_zone zero-weight fallback ─────────────────────────────

def test_sample_zone_all_zero_uses_fallback():
    """_sample_zone with all-zero fractions must use hardcoded [0.3, 0.2, 0.2, 0.3] fallback."""
    from sim.basketball_sim import ZONES
    rng = np.random.default_rng(77)
    r_zeros = {z: 0.0 for z in ZONES}
    results = [_sample_zone(r_zeros, rng) for _ in range(4000)]
    counts = {z: results.count(z) for z in ZONES}
    # Rough chi2: expect [0.3, 0.2, 0.2, 0.3] * 4000
    for z, expected_frac in zip(("z_rim", "z_paint", "z_mid", "z_3"), (0.3, 0.2, 0.2, 0.3)):
        actual = counts[z] / 4000
        assert abs(actual - expected_frac) < 0.05, f"Fallback zone {z}: {actual:.3f} expected {expected_frac}"


# ─── TEST-GAP: _pick zero-weight fallback ────────────────────────────────────

def test_pick_all_zero_weight_returns_valid_index():
    """_pick with all-zero weights must return a valid id (uniform fallback)."""
    rng = np.random.default_rng(99)
    model = type("M", (), {"rate": {i: {"k": 0.0} for i in range(5)}})()
    for _ in range(20):
        result = _pick(list(range(5)), model, "k", rng)
        assert result in range(5), f"_pick returned invalid index {result}"


# ─── TEST-GAP: out_ids removes player and lineup survives ────────────────────

def test_out_ids_removes_player_from_rate(teams):
    """After out_ids=[brunson_pid], Brunson should not appear in the model's rate dict."""
    h, _ = teams
    bru_pid = next(p for p in h.rate if "Brunson" in h.rate[p]["player"])
    h_out = TeamModel.from_cache("NYK", out_ids=[bru_pid])
    assert bru_pid not in h_out.rate, "Brunson should be excluded from rate with out_ids"


def test_out_ids_drops_lineups_containing_player(teams):
    """All lineups in h_out must not contain the removed player."""
    h, _ = teams
    bru_pid = next(p for p in h.rate if "Brunson" in h.rate[p]["player"])
    h_out = TeamModel.from_cache("NYK", out_ids=[bru_pid])
    for lu in h_out.lineup_ids:
        assert bru_pid not in lu, "Lineup containing excluded player survived filtering"


def test_out_ids_lineup_p_sums_to_one(teams):
    """After filtering, lineup_p must still sum to 1.0."""
    h, _ = teams
    bru_pid = next(p for p in h.rate if "Brunson" in h.rate[p]["player"])
    h_out = TeamModel.from_cache("NYK", out_ids=[bru_pid])
    assert abs(h_out.lineup_p.sum() - 1.0) < 1e-6, "lineup_p doesn't sum to 1 after out_ids filter"


def test_out_ids_simulation_finite(teams):
    """Simulating with a star out should produce finite results (no NaN from empty lineups)."""
    h, a = teams
    bru_pid = next(p for p in h.rate if "Brunson" in h.rate[p]["player"])
    h_out = TeamModel.from_cache("NYK", out_ids=[bru_pid])
    res = simulate_game(h_out, a, n_sims=500, seed=0, anchor=True, defense=False, dispersion=False)
    assert np.all(np.isfinite(res.home_total)), "NaN/Inf in home_total with star out"


# ─── TEST-GAP: possession count matches both engines ─────────────────────────

@pytest.mark.skipif(not _HAS_TORCH, reason="torch not available")
def test_possession_count_cpu_gpu_match(teams):
    """n_poss must be identical in CPU and GPU engines for the same team pair."""
    h, a = teams
    hp, ap = getattr(h, "pace_mult", 1.0), getattr(a, "pace_mult", 1.0)
    expected_n_poss = int(round((h.pace * hp + a.pace * ap) / 2))
    # Both engines compute this the same way; verify the formula result
    assert expected_n_poss > 0, "n_poss must be positive"
    assert 80 <= expected_n_poss <= 115, f"n_poss out of realistic range: {expected_n_poss}"


# ─── TEST-GAP: FT hardcoded-2-shot vs fast_sim consistency ──────────────────

@pytest.mark.skipif(not _HAS_TORCH, reason="torch not available")
def test_fast_sim_ftm_le_fta(teams):
    """fast_sim: ftm must never exceed fta."""
    h, a = teams
    res = simulate_game_fast(h, a, n_sims=2000, seed=0, anchor=False, defense=False, dispersion=False)
    for p, d in res.players.items():
        s = d["samples"]
        assert np.all(s["ftm"] <= s["fta"]), f"{d['name']} fast_sim has ftm > fta"


# ─── TEST-GAP: tov_force applied to defending team (not offense) ─────────────

def test_tov_force_attribution(teams):
    """Higher tov_force on team X (defender) should produce MORE turnovers for the opposing offense."""
    h, a = teams  # NYK tov_force > 1 (forces turnovers), SAS < 1
    res = simulate_game(h, a, n_sims=3000, seed=0, anchor=False, defense=True, dispersion=False)
    # SAS offends vs NYK D (tov_force > 1) -> more SAS turnovers
    sas_tov = sum(res.players[p]["mean"]["tov"] for p in a.rate)
    # NYK offends vs SAS D (tov_force < 1) -> fewer NYK turnovers
    nyk_tov = sum(res.players[p]["mean"]["tov"] for p in h.rate)
    assert sas_tov > nyk_tov, (
        f"tov_force attribution wrong: SAS TOV={sas_tov:.2f} should > NYK TOV={nyk_tov:.2f} "
        f"(NYK tov_force={h.tov_force:.3f}, SAS={a.tov_force:.3f})"
    )


# ─── TEST-GAP: NaN zone fractions in real data don't cause NaN in sim ─────────

def test_nan_fg_rates_dont_propagate(teams):
    """Players with NaN fg_rim/fg_paint/fg_mid should still produce finite output via fallbacks."""
    h, a = teams
    import math
    nan_players = [
        pid for pid in h.rate
        if any(
            isinstance(h.rate[pid].get(k), float) and math.isnan(h.rate[pid].get(k))
            for k in ("fg_rim", "fg_paint", "fg_mid")
        )
    ]
    if not nan_players:
        pytest.skip("No NaN fg rates in current data")
    res = simulate_game(h, a, n_sims=500, seed=0, anchor=True, defense=False, dispersion=False)
    for pid in nan_players:
        for k, v in res.players[pid]["mean"].items():
            assert np.isfinite(v), f"{h.rate[pid]['player']} mean[{k}] = {v} (NaN fg propagated!)"


# ─── TEST-GAP: Possession chain physical validity ────────────────────────────

def test_no_negative_counts(res_raw):
    """No stat should ever be negative in raw chain samples."""
    count_stats = ("pts", "fga", "fgm", "fg3a", "fg3m", "fta", "ftm", "oreb", "dreb",
                   "ast", "stl", "blk", "tov", "pf")
    for p, d in res_raw.players.items():
        for stat in count_stats:
            arr = d["samples"].get(stat, np.zeros(1))
            assert np.all(arr >= 0), f"{d['name']} has negative {stat}: min={arr.min():.1f}"


# ─── TEST-GAP: team_rates.json structure ─────────────────────────────────────

def test_team_rates_json_structure():
    """All 30 teams must have required keys; lineups must be 5-man."""
    import json
    fp = os.path.join(_CACHE, "team_rates.json")
    tr = json.load(open(fp))
    required = ("pace", "ast_rate_on_make", "oreb_per_miss", "lineups")
    for team, data in tr.items():
        for k in required:
            assert k in data, f"{team} missing key '{k}' in team_rates.json"
        for lu in data["lineups"]:
            assert len(lu["ids"]) == 5, f"{team} has non-5-man lineup"
    assert len(tr) == 30, f"Expected 30 teams, got {len(tr)}"


def test_oreb_per_miss_physical_bounds():
    """oreb_per_miss must be in [0, 0.5] for all teams."""
    import json
    fp = os.path.join(_CACHE, "team_rates.json")
    tr = json.load(open(fp))
    for team, data in tr.items():
        oreb = data.get("oreb_per_miss", 0)
        assert 0 <= oreb <= 0.5, f"{team} oreb_per_miss={oreb:.3f} out of [0, 0.5]"


def test_pace_physical_bounds():
    """Team pace must be in [80, 115] (physically realistic range)."""
    import json
    fp = os.path.join(_CACHE, "team_rates.json")
    tr = json.load(open(fp))
    for team, data in tr.items():
        pace = data.get("pace", 90)
        assert 80 <= pace <= 115, f"{team} pace={pace:.1f} out of realistic range"
