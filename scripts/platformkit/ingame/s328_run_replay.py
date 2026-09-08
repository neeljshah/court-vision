"""S328 finisher runner: wires the landed N arm and the S320_SUBSTITUTE arm into the
sealed s328_asof_replay module and drives the 313-state x 2-arm x 4-delay replay plus
the descriptive conclusion-survival comparison. Additive only; never edits the sealed
module, the prereg, or a landed file. Never refits: the N arm's frozen recalibration
(a, b) below is recovered by an exact algebraic solve against S310's own landed
`probabilities.csv` outputs (2 unknowns, verified on 74 independent points, max
residual 1.6e-13 in logit space) -- no LogisticRegression.fit call is made here.
"""
from __future__ import annotations

import hashlib
import math
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from domains.basketball_nba.ingame_adapter import CHECKPOINT_COLUMNS, _season as checkpoint_season
from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.ingame.s320_state_audit_attempt2 import latest_market
from scripts.platformkit.ingame.s328_asof_replay import replay, summary, write_replay

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "data/cache/inplay_odds/nba_checkpoints_full.parquet"
STATES = ROOT / "docs/evidence/harness/S320_timestamp_artifact_audit_2026-09-08b/states.csv"
STATES_SHA256 = "6f8f617e1701dc288338b8600de0f94eda34364d26187590c6934d38a2a88331"
OUT = ROOT / "docs/evidence/harness/S328_asof_join_falsification_2026-09-08"
EPS = 1e-15
N_COEF_2025_26 = (0.9374022892177405, 0.021210521231280095)  # S310 identity; 2024-25 is identity
BOOTSTRAPS, SEED = 2000, 328  # prereg silent on an S328-specific seed; 328 used, stated in the memo
CPCV_GROUPS, CPCV_TEST_GROUPS, CPCV_EMBARGO_DAYS = 4, 1, 1


def _lf_sha256(path: Path) -> str:
    raw = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(raw).hexdigest()


def verify_states() -> int:
    actual = _lf_sha256(STATES)
    assert actual == STATES_SHA256, "S320 states.csv sha256 mismatch: %s" % actual
    return STATES.stat().st_size


def _logit(p: float) -> float:
    p = min(max(p, EPS), 1.0 - EPS)
    return math.log(p / (1.0 - p))


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z)) if z >= 0 else math.exp(z) / (1.0 + math.exp(z))


def load_source() -> pd.DataFrame:
    """Column-projected, ASCII-safe read; precompute per-row ISO stamps once (not per builder call)."""
    frame = pd.read_parquet(SOURCE, columns=list(CHECKPOINT_COLUMNS))
    frame["game_id"] = frame["game_id"].astype(str)
    stamp = pd.to_datetime(frame["ts"], unit="s", utc=True)
    frame["iso_ts"] = stamp.map(lambda t: t.isoformat())
    frame["iso_prediction_at"] = (stamp + pd.Timedelta(microseconds=1)).map(lambda t: t.isoformat())
    # outcome known 1 day after the GAME's own final tick (not game_date, which can precede a
    # late-UTC tick for games that run past midnight UTC and would otherwise violate monotonicity)
    final_ts = frame.groupby("game_id")["ts"].transform("max")
    known_stamp = pd.to_datetime(final_ts, unit="s", utc=True) + pd.Timedelta(days=1)
    frame["iso_known_at"] = known_stamp.map(lambda t: t.isoformat())
    frame["season"] = frame["game_date"].map(checkpoint_season)
    return frame


def _market_lookup(source: pd.DataFrame) -> dict[tuple[str, int], float]:
    return dict(zip(zip(source.game_id, source.ts.astype(int)), source.market_prob.astype(float)))


def _target(state, lookup) -> SimpleNamespace:
    key = (str(state["game_id"]), int(state["ts"]))
    return SimpleNamespace(ts=int(state["ts"]), market_prob=float(lookup[key]))


def make_n_arm(lookup):
    """Landed S310/S309 grouped-CPCV null: latest-available market prob, recalibrated by the
    frozen (a, b) above for season 2025-26 states, identity for season 2024-25 states -- exactly
    S310's own landed behaviour, never refit here."""
    def arm(frame: pd.DataFrame, state, _loader) -> float:
        raw = latest_market(frame, _target(state, lookup))
        season = checkpoint_season(state["state_ts"])
        if season == "2024-25":
            return raw
        if season != "2025-26":
            raise ValueError("unexpected season %s for state %s" % (season, state["state_id"]))
        a, b = N_COEF_2025_26
        return _sigmoid(a * _logit(raw) + b)
    return arm


def make_substitute_arm(lookup):
    """S321 attempt 2 is not landed; substitute callback = raw latest market_prob (S320's M0)."""
    def arm(frame: pd.DataFrame, state, _loader) -> float:
        return latest_market(frame, _target(state, lookup))
    return arm


_UNKNOWN = ("home_team_id", "away_team_id", "line", "ml_source", "ml_time", "ml_probabilities")


def real_builder(frame: pd.DataFrame, _state) -> tuple[list[dict], list[dict]]:
    """Adapt an externally-joined frame subset into S323 contract features/labels."""
    features: list[dict] = []
    labels: list[dict] = []
    for index, row in enumerate(frame.itertuples(index=False)):
        key = "%s|%06d|home_win" % (row.game_id, index)
        market = float(row.market_prob)
        features.append({
            "sport": "basketball", "league": "NBA", "rule_version": "S328-replay",
            "game_id": row.game_id, "home_team_id": None, "away_team_id": None,
            "season": row.season, "corpus": "nba_checkpoints_full", "venue": str(row.venue),
            "target_id": "home_win", "line": None, "class_order": ("away", "home"),
            "settlement_rule": "home_win", "void_rule": "not_declared", "event_id": str(row.market_ticker),
            "sequence": index, "event_time": row.iso_ts, "received_at": row.iso_ts,
            "feature_available_at": row.iso_ts, "prediction_at": row.iso_prediction_at,
            "state": {"period": int(row.period), "clock_seconds": float(row.game_clock_s)},
            "score_home": int(row.score_home), "score_away": int(row.score_away),
            "status": "checkpoint", "unknown_flags": _UNKNOWN,
            "provenance": {"source": "nba_checkpoints_full"},
            "m0_source": "checkpoint_market_prob", "m0_time": row.iso_ts,
            "m0_probabilities": (1.0 - market, market), "ml_source": None, "ml_time": None,
            "ml_probabilities": None, "candidate_probabilities": (1.0 - market, market),
            "null_probabilities": (1.0 - market, market), "state_key": key, "exclusions": (),
            "weight": 1.0, "fold_id": "s328_replay", "input_hash": "s328_source",
            "code_hash": "s328_runner", "seal_hash": "s328_prereg",
            "maximum_feed_delay_seconds": 0,
            "features": {"market_prob": market, "margin": float(row.margin),
                        "period": float(row.period), "clock_seconds": float(row.game_clock_s)},
        })
        labels.append({"game_id": row.game_id, "target_id": "home_win", "state_key": key,
                       "outcome": int(row.outcome_home_win), "outcome_known_at": row.iso_known_at})
    return features, labels


def _bootstrap_ci(sums: np.ndarray, counts: np.ndarray, rng: np.random.Generator) -> tuple[float, float]:
    n = len(sums)
    draws = rng.integers(0, n, size=(BOOTSTRAPS, n))
    values = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
    return float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))


def _cpcv_states(group: pd.DataFrame, outcomes: dict[str, int]) -> list[dict]:
    """Turn external replay probabilities into vintage-checked shared-evaluator states."""
    wide = group.pivot(index="state_id", columns="arm", values="p_delay_probability").dropna()
    game_ids = group.drop_duplicates("state_id").set_index("state_id")["game_id"]
    state_times = group.drop_duplicates("state_id").set_index("state_id")["state_ts_s"]
    ordered = sorted(wide.index, key=lambda state_id: int(state_times[state_id]))
    states: list[dict] = []
    for index, state_id in enumerate(ordered):
        game_id, base_ts = str(game_ids[state_id]), int(state_times[state_id])
        available = pd.to_datetime(base_ts, unit="s", utc=True).isoformat()
        prediction = (pd.to_datetime(base_ts, unit="s", utc=True) + pd.Timedelta(microseconds=1)).isoformat()
        states.append({
            "game_id": game_id, "state_ts": prediction,
            "home": "home:%s" % game_id, "away": "away:%s" % game_id,
            "features": {"N": float(wide.loc[state_id, "N"]),
                         "S320_SUBSTITUTE": float(wide.loc[state_id, "S320_SUBSTITUTE"])},
            "feature_avail": {"N": available, "S320_SUBSTITUTE": available},
            "outcome": int(outcomes[game_id]),
            "cpcv_block": "block_%d" % (index * CPCV_GROUPS // len(ordered)),
        })
    return states


def _cpcv_pair(states: list[dict]) -> pd.DataFrame:
    """Score each frozen arm through the shared purged, symmetric-embargo evaluator."""
    def evaluate(arm: str) -> pd.DataFrame:
        records = cpcv_evaluate(
            states, lambda _train, test, _inside: float(test["features"][arm]),
            n_groups=CPCV_GROUPS, n_test_groups=CPCV_TEST_GROUPS,
            embargo_days=CPCV_EMBARGO_DAYS, strict_redaction=True,
            allow_keys=("cpcv_block",), group_key="cpcv_block", guard_state_keys=False,
        )
        return pd.DataFrame(records).rename(columns={"p_model": arm})

    baseline, candidate = evaluate("N"), evaluate("S320_SUBSTITUTE")
    keys = ["split_id", "game_id", "ts", "y"]
    return baseline[keys + ["N"]].merge(
        candidate[keys + ["S320_SUBSTITUTE"]], on=keys, validate="one_to_one",
    )


def survival_table(records: pd.DataFrame, outcomes: dict[str, int]) -> pd.DataFrame:
    """Descriptive paired Brier/log-loss survival through the shared CPCV evaluator."""
    rows = []
    for delay, group in records.groupby("delay_seconds"):
        states = _cpcv_states(group, outcomes)
        losses = _cpcv_pair(states)
        y = losses["y"].to_numpy(dtype=float)
        pb = losses["N"].to_numpy(dtype=float)
        pc = losses["S320_SUBSTITUTE"].to_numpy(dtype=float)
        pb_c, pc_c = np.clip(pb, EPS, 1 - EPS), np.clip(pc, EPS, 1 - EPS)
        losses["baseline_brier_loss"] = (pb - y) ** 2
        losses["candidate_brier_loss"] = (pc - y) ** 2
        losses["log_loss_baseline"] = -(y * np.log(pb_c) + (1 - y) * np.log(1 - pb_c))
        losses["log_loss_candidate"] = -(y * np.log(pc_c) + (1 - y) * np.log(1 - pc_c))
        clustered = losses.groupby("game_id").agg(
            brier_b_sum=("baseline_brier_loss", "sum"), brier_c_sum=("candidate_brier_loss", "sum"),
            log_b_sum=("log_loss_baseline", "sum"), log_c_sum=("log_loss_candidate", "sum"),
            n=("ts", "size"))
        rng = np.random.default_rng(SEED + int(delay))
        n_arr, brier_b, brier_c = clustered.n.to_numpy(), clustered.brier_b_sum.to_numpy(), clustered.brier_c_sum.to_numpy()
        log_b, log_c = clustered.log_b_sum.to_numpy(), clustered.log_c_sum.to_numpy()
        brier_delta_ci = _bootstrap_ci(brier_b - brier_c, n_arr, rng)
        log_delta_ci = _bootstrap_ci(log_b - log_c, n_arr, rng)
        brier_improve = float((brier_b.sum() - brier_c.sum()) / n_arr.sum())
        log_improve = float((log_b.sum() - log_c.sum()) / n_arr.sum())
        rows.append({
            "delay_seconds": int(delay), "n_states": int(len(states)),
            "n_cpcv_records_count": int(len(losses)),
            "n_game_clusters": int(len(clustered)),
            "baseline_brier_loss": float(losses.baseline_brier_loss.mean()),
            "candidate_brier_loss": float(losses.candidate_brier_loss.mean()),
            "brier_improvement": brier_improve, "brier_improvement_ci_low": brier_delta_ci[0],
            "brier_improvement_ci_high": brier_delta_ci[1],
            "baseline_log_loss": float(losses.log_loss_baseline.mean()),
            "candidate_log_loss": float(losses.log_loss_candidate.mean()),
            "log_improvement": log_improve, "log_improvement_ci_low": log_delta_ci[0],
            "log_improvement_ci_high": log_delta_ci[1],
        })
    table = pd.DataFrame(rows).sort_values("delay_seconds").reset_index(drop=True)
    zero_sign = np.sign(table.loc[table.delay_seconds.eq(0), "brier_improvement"].iloc[0])
    table["sign_survives_vs_delay0"] = (np.sign(table["brier_improvement"]) == zero_sign).astype(int)
    return table


def write_survival(table: pd.DataFrame, path: Path) -> None:
    output = table.copy()
    output["delay_seconds"] = output["delay_seconds"].astype(int).map("%06d".__mod__)
    output["n_states"] = output["n_states"].astype(int).map("%06d".__mod__)
    output["n_cpcv_records_count"] = output["n_cpcv_records_count"].astype(int).map("%06d".__mod__)
    output["n_game_clusters"] = output["n_game_clusters"].astype(int).map("%06d".__mod__)
    output["sign_survives_vs_delay0"] = output["sign_survives_vs_delay0"].astype(int).map("%06d".__mod__)
    output.to_csv(path, index=False, encoding="ascii", lineterminator="\n")


def run() -> dict:
    start = time.perf_counter()
    states_bytes = verify_states()
    source = load_source()
    lookup = _market_lookup(source)
    states = pd.read_csv(STATES)
    n_sealed = len(states)
    arms = {"N": make_n_arm(lookup), "S320_SUBSTITUTE": make_substitute_arm(lookup)}
    records = replay(source, states, arms, real_builder)
    OUT.mkdir(parents=True, exist_ok=True)
    write_replay(records, str(OUT / "replay.csv"))
    n_included = int(records.loc[records.arm.eq("N"), "state_id"].nunique())
    outcomes = dict(zip(source.game_id, source.outcome_home_win.astype(int)))
    survival = survival_table(records, outcomes)
    write_survival(survival, OUT / "survival.csv")
    elapsed = time.perf_counter() - start
    return {
        "states_bytes": states_bytes, "n_sealed": n_sealed, "n_included": n_included,
        "n_excluded": n_sealed - n_included, "summary": summary(records), "survival": survival,
        "elapsed_s": elapsed, "records": records,
    }


if __name__ == "__main__":
    result = run()
    print("n_sealed=%d n_included=%d n_excluded=%d elapsed_s=%.1f" %
          (result["n_sealed"], result["n_included"], result["n_excluded"], result["elapsed_s"]))
    print(result["summary"].to_string(index=False))
    print(result["survival"].to_string(index=False))
