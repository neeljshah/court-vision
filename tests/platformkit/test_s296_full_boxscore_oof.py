"""Focused S296 tests: seals, strict priors, key uniqueness, sample identities, replay."""

import hashlib

import numpy as np

from scripts.platformkit import full_boxscore_oof as s296
from scripts.platformkit.eval_gate.cpcv_vector_distribution import cpcv_evaluate_vector_distributional

# FIELDS order: min pts reb oreb dreb ast stl blk tov fgm fga fg3m fg3a ftm fta pf plus_minus
IDX = {field: index for index, field in enumerate(s296.FIELDS)}


def _vector(value: float, plus: float = None) -> tuple[float, ...]:
    """One coherent box line: every make is a 2-pointer, so pts = 2*value and oreb+dreb = reb."""
    return (10.0 + value, 2 * value, value, 0.0, value, 0.0, 0.0, 0.0, 0.0, value, value,
            0.0, 0.0, 0.0, 0.0, 0.0, -value if plus is None else plus)


def _state(index: int, player: int, day: int, vector) -> dict:
    return {"game_id": "g{0}".format(index), "state_ts": "2024-01-{0:02d}T12:00:00".format(day),
            "stable_key": "g{0}|{1}".format(index, player), "home": "player:{0}".format(player),
            "away": "team:X", "features": {"prior": 0.0},
            "feature_avail": {"prior": "2023-12-01T12:00:00"}, "player_id": player,
            "outcome_vector": vector}


def test_s296_all_prereg_seals_hold() -> None:
    for prereg in s296.PREREGS:
        raw = prereg.read_bytes().replace(b"\r\n", b"\n")
        prefix, suffix = raw.split(b"SEAL_SHA256:", 1)
        assert hashlib.sha256(prefix).hexdigest() == suffix.splitlines()[0].strip().decode("ascii"), prereg.name


def test_s296_truncation_unseen_player_and_dnp() -> None:
    train = [
        {"state_ts": "2024-01-01T12:00:00", "player_id": 7, "stable_key": "past", "outcome_vector": _vector(1)},
        {"state_ts": "2024-03-01T12:00:00", "player_id": 7, "stable_key": "future", "outcome_vector": _vector(99)},
    ]
    seen = s296._fit_predict(train, [{"state_ts": "2024-02-01T12:00:00", "player_id": 7, "stable_key": "t1"}])[0]
    assert set(seen["candidate_keys"]) == {"past"} and set(seen["baseline_keys"]) == {"past"}
    assert seen["used_player_prior"] == 1 and seen["cold_start_zero"] == 0

    unseen = s296._fit_predict(train, [{"state_ts": "2024-02-01T12:00:00", "player_id": 999, "stable_key": "t2"}])[0]
    assert set(unseen["candidate_keys"]) == {"past"}, "unseen player falls back to the strict-prior league prefix"
    assert unseen["used_player_prior"] == 0 and unseen["cold_start_zero"] == 0

    empty = s296._fit_predict(train, [{"state_ts": "2023-06-01T12:00:00", "player_id": 7, "stable_key": "t3"}])[0]
    assert set(empty["candidate_keys"]) == {"ZERO"} and empty["cold_start_zero"] == 1

    dnp = tuple(0.0 for _ in s296.FIELDS)
    scored = s296._score(seen, dnp)
    assert scored["candidate_min_crps"] >= 0.0 and scored["candidate_pts_inside80"] in (0.0, 1.0)


def test_s296_sample_identities_and_signed_plus_minus() -> None:
    train = [_state(index, 7, index + 1, _vector(float(index + 1), plus=-3.0 * (index + 1))) for index in range(4)]
    forecast = s296._fit_predict(train, [{"state_ts": "2024-01-09T12:00:00", "player_id": 7, "stable_key": "t"}])[0]
    for arm in ("candidate", "baseline"):
        samples = forecast[arm]
        assert samples.shape == (s296.N_SAMPLES, len(s296.FIELDS))
        # identities are checked ON SAMPLES, never on marginal quantiles
        assert np.all(samples[:, IDX["fgm"]] <= samples[:, IDX["fga"]])
        assert np.all(samples[:, IDX["fg3m"]] <= samples[:, IDX["fg3a"]])
        assert np.all(samples[:, IDX["ftm"]] <= samples[:, IDX["fta"]])
        assert np.all(samples[:, IDX["oreb"]] + samples[:, IDX["dreb"]] == samples[:, IDX["reb"]])
        assert np.all(2 * (samples[:, IDX["fgm"]] - samples[:, IDX["fg3m"]]) + 3 * samples[:, IDX["fg3m"]]
                      + samples[:, IDX["ftm"]] == samples[:, IDX["pts"]])
        assert np.all(samples[:, IDX["plus_minus"]] < 0), "plus_minus stays signed, never clipped at zero"
        assert all(s296._coherent(sample) for sample in samples)
    assert s296._score(forecast, _vector(2.0, plus=-6.0))["candidate_coherence_violation"] == 0.0


def test_s296_endpoint_atom_accounting_and_scaled_energy() -> None:
    samples = np.vstack([_vector(float(value)) for value in range(1, 26)])
    forecast = {"candidate": samples, "baseline": samples, "scale": np.ones(len(s296.FIELDS)),
                "candidate_keys": ["x"] * 25, "baseline_keys": ["x"] * 25, "cold_start_zero": 0,
                "used_player_prior": 1}
    for outcome, expect in ((_vector(1.0), 0), (_vector(13.0), 1), (_vector(25.0), 2)):
        score = s296._score(forecast, outcome)
        parts = [score["candidate_pts_" + name] for name in ("below_q10", "inside80", "above_q90")]
        assert sum(parts) == 1.0, "each state is below q10, inside, or above q90 exactly once"
        assert parts[expect] == 1.0
    atoms = s296._score(forecast, _vector(5.0))
    assert atoms["candidate_oreb_atom_q10_eq_q90"] == 1.0, "a constant field is a degenerate discrete atom"
    assert atoms["candidate_pts_atom_q10_eq_q90"] == 0.0

    scaled = {**forecast, "candidate": samples * 4.0, "baseline": samples * 4.0,
              "scale": np.full(len(s296.FIELDS), 4.0)}
    plain = s296._score(forecast, _vector(7.0))["candidate_energy_train_scaled"]
    assert abs(s296._score(scaled, tuple(4.0 * value for value in _vector(7.0)))["candidate_energy_train_scaled"]
               - plain) < 1e-9, "train-scaled energy is invariant to a common unit change"


def test_s296_key_uniqueness_fold_and_score_replay() -> None:
    states = [_state(index, 7 + index % 3, index + 1, _vector(float(index + 1))) for index in range(12)]
    records = cpcv_evaluate_vector_distributional(
        states, s296._fit_predict, s296._score, n_groups=3, n_test_groups=1, embargo_days=1,
        strict_redaction=True, allow_keys=("stable_key", "player_id"),
    )
    assert len(records) == len(states)
    assert len({record["stable_key"] for record in records}) == len(states), "one record per player-game key"
    assert {record["split_id"] for record in records} == {0, 1, 2}, "every fold is scored independently"

    summary = s296._summary(records)
    assert summary["n_rows"] == len(states)
    for name in ("pts_crps", "energy", "energy_train_scaled"):
        replay_c = float(np.mean([record["scores"]["candidate_" + name] for record in records]))
        replay_b = float(np.mean([record["scores"]["baseline_" + name] for record in records]))
        assert abs(summary["metrics"][name]["candidate"] - replay_c) < 1e-12
        assert abs(summary["metrics"][name]["improvement"] - (replay_b - replay_c)) < 1e-12
    replay_cov = float(np.mean([record["scores"]["candidate_pts_inside80"] for record in records]))
    assert abs(summary["coverage"]["pts"]["candidate"] - replay_cov) < 1e-12
    assert summary["coverage"]["pts"]["nominal"] == 0.80
    assert s296._fold_table(records)["0"]["status"] == "NOT SCORABLE", "a 4-game fold is below the 30-game bar"
