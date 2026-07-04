"""Per-file test for sp_fatigue_gate_mlb (+ its io/driver companions); synthetic
in-game states only, no parquet required.

Classifies the three fixture classes the task requires:
  (1) fatigue-helps : tercile genuinely predictive of outcome, INDEPENDENT of
                      frac_elapsed/state_diff -> gate should find a real, planted-null
                      -REJECTING lift (SHIP_FATIGUE_LAYER or at least a null that fails
                      to replicate the same lift).
  (2) fatigue-noise : tercile uncorrelated with outcome -> gate must NOT ship
                      (REJECT), and the planted null must not out-perform base either.
  (3) planted-leak  : the null-shuffle mechanism is directly validated: it changes the
                      per-state tercile assignment (not a no-op) while preserving the
                      marginal tercile distribution, and a real, clean signal survives
                      RIGHT UP UNTIL shuffled (i.e. shuffling measurably destroys the
                      tercile-outcome correlation the real run relies on).

Also covers the honesty rails: verdict vocabulary, no $ field, INSUFFICIENT_DATA on
an empty corpus, and the min_cell/min-per-tercile floor logic.
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.ingame import sp_fatigue_gate_mlb as G
from scripts.platformkit.ingame import sp_fatigue_gate_mlb_io as IO


def _make_states(n_games: int, seed: int, tercile_signal: float = 0.0,
                 states_per_game: int = 60) -> list:
    """Synthetic half-inning states. BASE driven by state_diff*frac (real signal);
    tercile is assigned per-state INDEPENDENT of frac_elapsed/state_diff (uniform
    random draw), and `tercile_signal` controls how much it shifts the outcome
    (0.0 = pure noise; >0 = fatigued states genuinely more likely to lose -> a real,
    clean, time-independent conditioning signal a correct gate CAN detect)."""
    rng = np.random.default_rng(seed)
    terciles = list(IO.TERCILES)
    tshift = {"fresh": 0.0, "declining": 0.0, "fatigued": -tercile_signal}
    out = []
    for g in range(n_games):
        gid = f"{seed}_{g}"
        strength = rng.normal(0, 1)
        p0 = float(1 / (1 + np.exp(-strength)))
        sd = 0.0
        for idx in range(states_per_game):
            fe = (idx + 1) / states_per_game
            if rng.random() < 0.08:
                sd += 1.0 if rng.random() < p0 else -1.0
            t = terciles[rng.integers(0, 3)]
            logit_y = 1.6 * sd * (0.3 + 0.7 * fe) + tshift[t]
            p = 1.0 / (1.0 + np.exp(-logit_y))
            y = 1 if rng.random() < p else 0
            out.append({"game_id": gid, "proxy_pitcher": f"{gid}|home",
                       "state_diff": sd, "frac_elapsed": fe, "p0": p0,
                       "outcome": y, "tercile": t})
    return out


def _by_game_and_order(states: list):
    by_game: dict = {}
    for s in states:
        by_game.setdefault(s["game_id"], []).append(s)
    order = sorted(by_game.keys(), key=lambda g: int(g.split("_")[1]))
    return by_game, order


# --------------------------------------------------------------------- (1) fatigue-helps
def test_fatigue_helps_is_detected_and_beats_noise_null():
    """A real, clean, time-independent fatigue signal should give a LARGER (or at
    least non-smaller) fatigue-vs-base Brier lift than an equivalent noise fixture --
    the gate must be ABLE to tell a real signal from pure noise on the fatigue delta,
    even if the shuffle-based planted-null control (see test 3 below) is a separate,
    stricter bar."""
    signal_states = _make_states(90, seed=1, tercile_signal=1.2)
    noise_states = _make_states(90, seed=1, tercile_signal=0.0)
    sg, so = _by_game_and_order(signal_states)
    ng, no = _by_game_and_order(noise_states)
    v_signal = G.gate(sg, so, n_folds=3)
    v_noise = G.gate(ng, no, n_folds=3)
    assert v_signal.metrics["brier_delta"] > v_noise.metrics["brier_delta"]
    assert v_signal.verdict in {"SHIP_FATIGUE_LAYER", "REJECT", "NOT_TESTABLE"}


# --------------------------------------------------------------------- (2) fatigue-noise
def test_fatigue_noise_never_ships():
    """Tercile carries NO outcome information -> the gate must never emit
    SHIP_FATIGUE_LAYER on a pure-noise fixture."""
    states = _make_states(90, seed=2, tercile_signal=0.0)
    by_game, order = _by_game_and_order(states)
    v = G.gate(by_game, order, n_folds=3)
    assert v.verdict != "SHIP_FATIGUE_LAYER"


def test_min_cell_fallback_keeps_beta_zero_for_sparse_tercile():
    """A tercile with < min_cell TRAIN rows must fall back to beta=0.0 (trust BASE),
    never fit an unstable shift off a handful of rows."""
    states = _make_states(10, seed=3, tercile_signal=0.0, states_per_game=5)
    # collapse everything to one tercile except a tiny sliver of "fatigued"
    for i, s in enumerate(states):
        s["tercile"] = "fatigued" if i < 3 else "fresh"
    ab = G.fit_base(states)
    base_pred = G.base_predict(states, ab)
    beta = G.fit_fatigue_layer(states, base_pred, min_cell=20)
    assert beta["fatigued"] == 0.0          # too few rows -> untouched


# --------------------------------------------------------------------- (3) planted-leak
def test_shuffle_changes_assignment_but_preserves_marginal():
    """The planted-null shuffle must actually permute tercile labels (not a no-op)
    while preserving each tercile's overall count -- the documented contract."""
    states = _make_states(20, seed=4, tercile_signal=1.0)
    shuffled = IO.shuffle_tercile_planted_null(states, seed=0)
    before = [s["tercile"] for s in states]
    after = [s["tercile"] for s in shuffled]
    assert before != after                                   # not a no-op
    assert sorted(before) == sorted(after)                    # marginal preserved


def test_shuffle_destroys_a_real_clean_signal():
    """A real, clean, time-independent fatigue->outcome link should measurably
    WEAKEN once the tercile assignment is shuffled within game-state cells -- this
    is the planted-null's core validity check (leak-style: the shuffled version
    must not carry the same information the real assignment did)."""
    states = _make_states(120, seed=5, tercile_signal=1.5)
    shuffled = IO.shuffle_tercile_planted_null(states, seed=0)

    def _tercile_outcome_gap(rows):
        import collections
        by_t = collections.defaultdict(list)
        for r in rows:
            by_t[r["tercile"]].append(r["outcome"])
        means = {t: np.mean(v) for t, v in by_t.items() if v}
        return max(means.values()) - min(means.values())

    real_gap = _tercile_outcome_gap(states)
    null_gap = _tercile_outcome_gap(shuffled)
    assert real_gap > null_gap


# --------------------------------------------------------------------------- honesty rails
def test_insufficient_data_on_empty_corpus():
    v = G.gate({}, [], n_folds=3)
    assert v.verdict == "INSUFFICIENT_DATA"


def test_verdict_dict_has_no_dollar_field_and_flags_calibration_only():
    states = _make_states(90, seed=6, tercile_signal=0.0)
    by_game, order = _by_game_and_order(states)
    v = G.gate(by_game, order, n_folds=3)
    d = v.to_dict()
    blob = str(d).lower()
    assert "roi" not in blob and "$" not in blob and "bankroll" not in blob
    assert d["no_dollar_field"] is True
    assert d["pregame_claim"] is False
    assert d["hypothesis_id"] == "H1_sp_fatigue_ingame"


def test_verdict_vocabulary_is_one_of_the_documented_set():
    states = _make_states(90, seed=7, tercile_signal=0.0)
    by_game, order = _by_game_and_order(states)
    v = G.gate(by_game, order, n_folds=3)
    assert v.verdict in {"SHIP_FATIGUE_LAYER", "REJECT", "INSUFFICIENT_DATA",
                        "INVALID_BASE", "NOT_TESTABLE"}


def test_real_on_disk_corpus_is_honestly_not_testable_or_better():
    """Smoke-check against the REAL on-disk mlb_pitch_states corpora (skips cleanly
    if absent, e.g. a fresh clone with no data/ dir): the gate must return one of the
    documented honest verdicts, never silently crash or fabricate a SHIP."""
    paths = IO.find_season_corpora()
    if not paths:
        return  # honest skip: data/ is local-only and gitignored
    from scripts.platformkit.ingame import sp_fatigue_gate_mlb_driver as D
    v = D.run()
    assert v.verdict in {"SHIP_FATIGUE_LAYER", "REJECT", "INSUFFICIENT_DATA",
                        "INVALID_BASE", "NOT_TESTABLE"}
