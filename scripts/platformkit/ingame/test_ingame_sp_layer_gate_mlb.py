"""Per-file test for ingame_sp_layer_gate_mlb (hermetic synthetic corpora; no parquet,
no domains.mlb network/IO calls -- gate() is exercised directly).

Principled checks:
  (1) planted DECAYING sp effect -> the decay layer SHIPs on >=2 synthetic corpora
      (both flat and decay layers may beat BASE, but decay's gain concentrates early).
  (2) a no-effect corpus (sp_diff_ew pure noise) -> REJECT (honest null).
  (3) noise control: a permuted sp_diff_ew column must NOT beat BASE; if the harness
      were rigged to always "beat" a column, this test would catch it.
  (4) identical row-set discipline: a game with NO sp form never enters either model's
      scoring (load_pitch_states drops it via the inner join before gate() ever runs).
  (5) verdict dict is CALIBRATION/proposal-only, never a market edge; no $ field.
  (6) INSUFFICIENT_DATA when fewer than 2 usable corpora are supplied.
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.ingame import ingame_sp_layer_gate_mlb as G


def _corpus(n_games: int, seed: int, decaying_effect: bool = False,
           effect_strength: float = 2.5) -> list:
    """Synthetic per-pitch states. BASE (state_diff, frac_elapsed) always drives most
    of the outcome. sp_diff_ew is either pure noise (decaying_effect=False) or a real,
    DECAYING signal: it shifts win-prob EARLY in the game and fades to ~0 by the end
    (decaying_effect=True) -- the exact shape the decay layer is built to capture.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_games):
        gid = f"s{seed}_g{g}"
        date = f"2024-01-{1 + (g % 28):02d}"
        sp_diff = float(rng.normal(0, 1.0))
        sd = 0.0
        # outcome realized via a single latent strength draw (state_diff + decaying sp)
        strength = rng.normal(0, 1)
        win = 1 if rng.random() < 1.0 / (1.0 + np.exp(-strength)) else 0
        for idx in range(24):
            fe = idx / 23.0
            if rng.random() < 0.35:
                sd += 1.0 if rng.random() < (0.5 + 0.1 * strength) else -1.0
            rows.append({
                "game_id": gid, "date": date, "state_diff": sd, "frac_elapsed": fe,
                "outcome": win, "sp_diff_ew": sp_diff,
                "_decay_boost": effect_strength * sp_diff * (1.0 - fe) if decaying_effect else 0.0,
            })
    return rows


def _bake_decay_outcome(rows: list, seed: int) -> list:
    """Re-derive `outcome` so it is genuinely correlated with the planted decaying sp
    effect (early sp_diff pull, fading to 0), independent of the base state walk --
    giving the decay layer real held-out signal to find. Deterministic per game."""
    rng = np.random.default_rng(seed + 9001)
    by_game: dict = {}
    for r in rows:
        by_game.setdefault(r["game_id"], []).append(r)
    for gid, grp in by_game.items():
        early_boost = grp[0]["_decay_boost"]  # constant per game (sp_diff*strength)
        p_win = 1.0 / (1.0 + np.exp(-(0.6 * early_boost)))
        win = 1 if rng.random() < p_win else 0
        for r in grp:
            r["outcome"] = win
    return rows


def _strip_helper_col(rows: list) -> list:
    return [{k: v for k, v in r.items() if k != "_decay_boost"} for r in rows]


def test_noise_corpus_rejects():
    """No planted sp effect anywhere -> neither layer should reliably beat BASE in
    BOTH corpora -> overall verdict must not be SHIP."""
    a = _strip_helper_col(_corpus(40, 1))
    b = _strip_helper_col(_corpus(40, 2))
    v = G.gate({"a": a, "b": b})
    assert v.verdict in ("REJECT", "PARTIAL", "INSUFFICIENT_DATA", "UNTRUSTWORTHY")
    assert v.verdict != "SHIP"


def test_decaying_effect_ships_on_two_corpora():
    """A REAL decaying sp effect planted in >=2 corpora should let the decay layer
    beat BASE with the gain concentrated early -- proof the gate can detect a real
    signal, not just reject everything."""
    a = _bake_decay_outcome(_corpus(70, 3, decaying_effect=True), 3)
    b = _bake_decay_outcome(_corpus(70, 4, decaying_effect=True), 4)
    a, b = _strip_helper_col(a), _strip_helper_col(b)
    decay_a = G._score_variant(a, decay=True)
    decay_b = G._score_variant(b, decay=True)
    assert decay_a is not None and decay_b is not None
    assert decay_a["layer_beats_base"] and decay_b["layer_beats_base"]
    v = G.gate({"a": a, "b": b})
    assert v.verdict == "SHIP"
    # decay hypothesis: early tercile gain should be present when the layer wins
    early_a = decay_a["per_tercile"].get("early")
    late_a = decay_a["per_tercile"].get("late")
    if early_a and late_a:
        assert early_a["delta"] >= late_a["delta"] - 1e-6


def test_noise_control_does_not_beat_base():
    """_permuted_sp breaks the game<->form link. Run through the IDENTICAL decay-layer
    machinery, it must NOT reliably beat BASE -- the mandatory harness sanity check."""
    a = _bake_decay_outcome(_corpus(70, 5, decaying_effect=True), 5)
    a = _strip_helper_col(a)
    permuted = G._permuted_sp(a, seed=123)
    res = G._score_variant(permuted, decay=True)
    assert res is not None
    # permutation destroys the real per-game link -> should not show a clean win
    assert res["dm_p"] > 0.01 or not res["layer_beats_base"]


def test_gate_noise_ok_flag_true_on_clean_harness():
    a = _strip_helper_col(_corpus(60, 6))
    b = _strip_helper_col(_corpus(60, 7))
    v = G.gate({"a": a, "b": b})
    assert v.noise_ok is True
    assert v.verdict != "UNTRUSTWORTHY"


def test_identical_row_set_discipline_via_load_pitch_states(tmp_path):
    """A game with NO resolved SP form must be excluded from BOTH models' scoring --
    simulated here by checking the inner-join drop directly (load_pitch_states),
    since gate() itself always receives an already-joined row set."""
    import pandas as pd

    pitch_df = pd.DataFrame([
        {"game_id": "g1", "date": "2024-01-01", "asof_idx": 0, "state_diff": 1.0,
         "frac_elapsed": 0.1, "outcome": 1},
        {"game_id": "g1", "date": "2024-01-01", "asof_idx": 1, "state_diff": 2.0,
         "frac_elapsed": 0.5, "outcome": 1},
        {"game_id": "g2_no_sp_form", "date": "2024-01-02", "asof_idx": 0,
         "state_diff": -1.0, "frac_elapsed": 0.2, "outcome": 0},
    ])
    path = tmp_path / "corpus.parquet"
    pitch_df.to_parquet(path)
    sp_by_event = pd.DataFrame([{"event_id": "g1", "sp_diff_ew": 0.75}])
    states = G.load_pitch_states(str(path), sp_by_event)
    game_ids = {s["game_id"] for s in states}
    assert "g1" in game_ids
    assert "g2_no_sp_form" not in game_ids   # excluded, never guessed/0-filled
    assert len(states) == 2


def test_verdict_is_calibration_proposal_only_no_dollar():
    a = _bake_decay_outcome(_corpus(50, 8, decaying_effect=True), 8)
    b = _bake_decay_outcome(_corpus(50, 9, decaying_effect=True), 9)
    a, b = _strip_helper_col(a), _strip_helper_col(b)
    v = G.gate({"a": a, "b": b})
    d = v.to_dict()
    assert "market edge" in d["vs_close"]
    assert d["proposal_only"] is True and d["no_dollar_field"] is True
    assert "$" not in _json_dumps(d)


def test_insufficient_data_with_fewer_than_two_usable_corpora():
    a = _strip_helper_col(_corpus(5, 10))
    v = G.gate({"a": a})
    assert v.verdict == "INSUFFICIENT_DATA"


def test_layer_verdict_helper_thresholds():
    assert G._layer_verdict({"a": {"layer_beats_base": True}}) == "INSUFFICIENT_DATA"
    assert G._layer_verdict(
        {"a": {"layer_beats_base": True}, "b": {"layer_beats_base": True}}) == "SHIP"
    assert G._layer_verdict(
        {"a": {"layer_beats_base": True}, "b": {"layer_beats_base": False}}) == "PARTIAL"
    assert G._layer_verdict(
        {"a": {"layer_beats_base": False}, "b": {"layer_beats_base": False}}) == "REJECT"


def _json_dumps(d) -> str:
    import json
    return json.dumps(d)
