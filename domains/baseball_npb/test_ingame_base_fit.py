"""Per-file tests for domains.baseball_npb.ingame_base_fit(+_io) -- pure, offline,
synthetic games (never reads the real npb_results.parquet, so this runs fast and
does not depend on the live corpus). Real-corpus numbers (HONEST_NEGATIVE, no
params ever persisted) are recorded in
data/domains/npb/ingame_base_fit_verdict.json (produced by gate_and_persist()).

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/baseball_npb/test_ingame_base_fit.py -q
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from domains.baseball_npb import ingame_base_fit as f
from domains.baseball_npb import ingame_base_fit_io as io


def _synthetic_games(n=400, seed=7):
    """n games across 2 seasons, home_win skewed ~58% so the BASE has real signal to
    find (a home team that wins more, with a real final-margin distribution)."""
    rng = np.random.default_rng(seed)
    teams = ["Giants", "Tigers", "Carp", "Swallows", "BayStars", "Dragons"]
    rows = []
    start = dt.date(2023, 3, 1)
    for i in range(n):
        date = start + dt.timedelta(days=i // 4)
        season = date.year
        home, away = rng.choice(teams, size=2, replace=False)
        home_win_prob = 0.58
        home_win = 1.0 if rng.random() < home_win_prob else 0.0
        margin = rng.integers(1, 8) if home_win else -rng.integers(1, 8)
        home_score = max(0.0, 4.0 + margin / 2.0)
        away_score = max(0.0, 4.0 - margin / 2.0)
        rows.append({
            "date": date, "season": str(season), "home_team": str(home),
            "away_team": str(away), "home_score": home_score, "away_score": away_score,
            "home_win": home_win, "tied": False,
        })
    return pd.DataFrame(rows)


def _synthetic_games_with_ties(seed=3):
    df = _synthetic_games(n=60, seed=seed)
    df.loc[0, "home_win"] = np.nan
    df.loc[0, "tied"] = True
    return df


# --------------------------------------------------------------------------- io
def test_bridge_path_pinned_at_endpoints():
    rng = np.random.default_rng(1)
    path = io._bridge_path(final_diff=6.0, sigma=3.0, n=9, rng=rng)
    assert len(path) == 9
    assert path[-1] == 6.0  # frac=1.0 anchor is EXACT (the known final margin)


def test_bridge_path_variance_shrinks_toward_end():
    """Repeated bridge draws for the SAME final_diff should show LARGER spread at an
    early checkpoint than a late one (Brownian-bridge var ~ t*(1-t) is max at t=0.5
    and shrinks to 0 at t=1) -- this is the property that fixes the linear-ramp
    artifact (see module docstring: a ramp has ZERO spread at every checkpoint)."""
    draws_early, draws_late = [], []
    for seed in range(200):
        rng = np.random.default_rng(seed)
        path = io._bridge_path(final_diff=4.0, sigma=3.0, n=9, rng=rng)
        draws_early.append(path[0])   # frac=1/9
        draws_late.append(path[7])    # frac=8/9
    assert np.std(draws_early) > np.std(draws_late)


def test_synth_states_reproducible_across_calls():
    games = _synthetic_games(n=60)
    s1 = io.synth_states_for_split(games, games)
    s2 = io.synth_states_for_split(games, games)
    assert [s["state_diff"] for s in s1] == [s["state_diff"] for s in s2]


def test_synth_states_excludes_tied_games():
    games = _synthetic_games_with_ties()
    states = io.synth_states_for_split(games, games)
    gids = {s["game_id"] for s in states}
    tied_row = games.iloc[0]
    tied_gid = f"npb-{tied_row['date'].isoformat()}-{tied_row['away_team']}-{tied_row['home_team']}"
    assert tied_gid not in gids


def test_synth_states_schema_and_ranges():
    games = _synthetic_games(n=60)
    states = io.synth_states_for_split(games, games)
    assert len(states) == 60 * io.N_CHECKPOINTS  # _synthetic_games has no ties
    for s in states[:20]:
        assert 0.0 < s["frac_elapsed"] <= 1.0
        assert 0.0 <= s["p0"] <= 1.0
        assert s["outcome"] in (0, 1)


def test_p0_is_leak_free_not_using_own_outcome():
    """A single-game corpus (no prior history) must get p0 from the ELO_MEAN prior,
    not from its own home_win label -- i.e. p0 must not depend on which team won."""
    games_a = _synthetic_games(n=1, seed=1)
    games_a.loc[0, "home_win"] = 1.0
    games_b = games_a.copy()
    games_b.loc[0, "home_win"] = 0.0
    p0_a = io._p0_snapshots(games_a)
    p0_b = io._p0_snapshots(games_b)
    assert list(p0_a.values()) == list(p0_b.values())


# --------------------------------------------------------------------------- fit
def test_walk_forward_split_no_same_day_leak():
    games = _synthetic_games(n=200)
    train, eval_ = f.walk_forward_split(games, min_eval=50)
    assert len(eval_) >= 50
    train_max = pd.to_datetime(train["date"]).dt.date.max()
    eval_min = pd.to_datetime(eval_["date"]).dt.date.min()
    assert train_max < eval_min


def test_multi_start_fit_moves_off_init():
    games = _synthetic_games(n=300)
    states = io.synth_states_for_split(games, games)
    result = f.multi_start_fit(states)
    assert result["moved_off_init"] is True
    assert result["final_mse"] <= result["init_mse"]
    assert result["final_ab"] != result["init_ab"]


def test_fit_and_eval_end_to_end_shape():
    """Exercises the same pipeline fit_and_eval runs (split -> synth -> fit) directly
    on synthetic games, hermetically (no real-corpus file I/O)."""
    games = _synthetic_games(n=300)
    train, eval_ = f.walk_forward_split(games, min_eval=60)
    train_states = io.synth_states_for_split(train, games)
    eval_states = io.synth_states_for_split(eval_, games)
    fit_info = f.multi_start_fit(train_states)
    assert set(fit_info.keys()) == {"init_ab", "init_mse", "final_ab", "final_mse", "moved_off_init"}
    assert len(train_states) > 0 and len(eval_states) > 0


def test_gate_and_persist_never_writes_params_file(tmp_path, monkeypatch):
    """A coin-flip corpus (no real signal in state_diff at all -- pure noise outcome)
    must trip the degenerate guard and NOT write a params file."""
    rng = np.random.default_rng(0)
    rows = []
    start = dt.date(2023, 3, 1)
    for i in range(250):
        date = start + dt.timedelta(days=i // 4)
        home_win = 1.0 if rng.random() < 0.5 else 0.0
        rows.append({
            "date": date, "season": str(date.year), "home_team": "A", "away_team": "B",
            "home_score": 4.0, "away_score": 4.0, "home_win": home_win, "tied": False,
        })
    games = pd.DataFrame(rows)
    # tie every score 4-4 -> final_diff always 0 -> bridge pinned at (0,0) -> state_diff
    # carries ZERO signal about the coin-flip outcome -> guaranteed degenerate base.
    monkeypatch.setattr(f, "load_games", lambda root=None: games)
    result = f.gate_and_persist(root=tmp_path, min_eval=60)
    assert result["degenerate_check"]["degenerate"] is True
    assert result["verdict"] == "HONEST_NEGATIVE"
    assert "persisted_path" not in result
    assert not (tmp_path / "data" / "domains" / "npb" / "ingame_base_params.json").exists()


def test_gate_and_persist_writes_honest_verdict_artifact(tmp_path, monkeypatch):
    """Even on a real-signal corpus, gate_and_persist must write the VERDICT_PATH
    artifact (not the params file) and record the disqualification."""
    games = _synthetic_games(n=300)
    monkeypatch.setattr(f, "load_games", lambda root=None: games)
    result = f.gate_and_persist(root=tmp_path, min_eval=60)
    verdict_file = tmp_path / "data" / "domains" / "npb" / "ingame_base_fit_verdict.json"
    assert verdict_file.exists()
    assert not (tmp_path / "data" / "domains" / "npb" / "ingame_base_params.json").exists()
    assert result["verdict_persisted_path"] == str(verdict_file)


def test_pure_noise_control_passes_as_nondegenerate_proving_disqualification():
    """DECISIVE PROOF regression test: a corpus with ZERO real signal (coin-flip
    outcome, random margin) must still report control_passes_as_nondegenerate=True
    for this bridge synthesis -- this is exactly the artifact the blocking review
    found, and fit_and_eval must therefore always disqualify a real-corpus result."""
    games = _synthetic_games(n=300)
    ctrl = f.pure_noise_control(games, min_eval=60)
    assert ctrl["control_passes_as_nondegenerate"] is True
    assert ctrl["bss_vs_coin"] > 0


def test_fit_and_eval_always_disqualified_and_honest_negative(monkeypatch):
    """fit_and_eval on a real-signal synthetic corpus must still end up
    HONEST_NEGATIVE because the noise control disqualifies the bridge synthesis
    regardless of the real-corpus degenerate_check result."""
    games = _synthetic_games(n=300)
    monkeypatch.setattr(f, "load_games", lambda root=None: games)
    result = f.fit_and_eval(root=None, min_eval=60)
    assert result["disqualified_by_noise_control"] is True
    assert result["verdict"] == "HONEST_NEGATIVE"


def test_frac1_leak_decomposition_rises_toward_frac1():
    """The per-checkpoint BSS at frac=1.0 (k=9, the endpoint pin) must be higher than
    at the earliest checkpoint (k=1) -- the monotonic-rise signature of the leak."""
    games = _synthetic_games(n=300)
    train, eval_ = f.walk_forward_split(games, min_eval=100)
    train_states = io.synth_states_for_split(train, games)
    eval_states = io.synth_states_for_split(eval_, games)
    fit_info = f.multi_start_fit(train_states)
    ab = tuple(fit_info["final_ab"])
    decomp = f.frac1_leak_decomposition(eval_states, ab)
    assert decomp["k9"]["bss_vs_coin"] > decomp["k1"]["bss_vs_coin"]
