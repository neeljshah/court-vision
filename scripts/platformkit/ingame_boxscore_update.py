"""S245 live NBA remaining-box distributions, evaluated only through CPCV."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate

REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "data/domains/basketball_nba/espn_nba_game_bridge.parquet"
QUARTER_BOX = REPO / "data/cache/quarter_box"
STATE_PATHS = (REPO / "data/cache/ingame/possession_states_2024_25.parquet",
               REPO / "data/cache/ingame/possession_states_2025_26.parquet")
GARBAGE = REPO / "data/intelligence/garbage_time_segments.parquet"
OUT = REPO / "docs/evidence/harness"
CHECKPOINTS = (("end_q1", 1, 2160), ("end_q2", 2, 1440), ("end_q3", 3, 720))
STATS = ("pts", "reb", "ast")
N_GROUPS, N_TEST_GROUPS, EMBARGO_DAYS = 8, 1, 1
BOOTSTRAP_SEED, BOOTSTRAP_REPS = 245, 10_000


def gaussian_crps(mu: np.ndarray, sigma: np.ndarray, observed: np.ndarray) -> np.ndarray:
    """Closed-form Normal CRPS, with its MAE point-mass limit."""
    mu, sigma, observed = (np.asarray(mu, float), np.asarray(sigma, float),
                           np.asarray(observed, float))
    out = np.abs(mu - observed)
    live = sigma > 1e-12
    z = (observed[live] - mu[live]) / sigma[live]
    cdf = 0.5 * (1.0 + np.vectorize(math.erf)(z / math.sqrt(2.0)))
    pdf = np.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
    out[live] = sigma[live] * (z * (2.0 * cdf - 1.0) + 2.0 * pdf - 1.0 / math.sqrt(math.pi))
    return out


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _margin_bin(value: float) -> str:
    absolute = abs(float(value))
    return "close" if absolute <= 5 else ("medium" if absolute <= 12 else "large")


def _quarter_rows(game_id: str, checkpoint: int) -> pd.DataFrame:
    """Build active-player remaining targets from q1-q4 JSON, with no q0 assumption."""
    quarters: dict[int, dict[str, dict]] = {}
    for period in range(1, 5):
        path = QUARTER_BOX / (game_id + "_q" + str(period) + ".json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if str(payload["game_id"]) != game_id or int(payload["period"]) != period:
            raise AssertionError("quarter-box identity mismatch for " + path.name)
        quarters[period] = {str(row["player_id"]): row for row in payload["players"]}
    active = set().union(*(set(quarters[p]) for p in range(1, checkpoint + 1)))
    rows = []
    for player_id in sorted(active):
        known = next(quarters[p][player_id] for p in range(1, checkpoint + 1)
                     if player_id in quarters[p])
        for stat in STATS:
            partial = sum(float(quarters[p].get(player_id, {}).get(stat, 0.0))
                          for p in range(1, checkpoint + 1))
            final = sum(float(quarters[p].get(player_id, {}).get(stat, 0.0))
                        for p in range(1, 5))
            rows.append({"player_id": player_id, "player": str(known.get("player_name", "")),
                         "team": str(known.get("team_abbreviation", "")), "stat": stat,
                         "partial": partial, "remaining": final - partial})
    return pd.DataFrame(rows)


def _state_snapshots() -> pd.DataFrame:
    """Read each permitted state store independently and select fixed-time snapshots."""
    bridge = pd.read_parquet(BRIDGE)
    bridge = bridge.loc[bridge["match_confidence"].astype(str).eq("exact")].copy()
    bridge["event_id"] = bridge["event_id"].astype(str)
    bridge["game_id"] = bridge["game_id"].astype(str)
    bridge = bridge.drop_duplicates("game_id")
    parts = []
    for path in STATE_PATHS:
        part = pd.read_parquet(path, columns=["game_id", "date", "seconds_remaining", "state_diff",
                                              "pace_so_far", "run_diff"])
        part["event_id"] = part["game_id"].astype(str)
        part = part.drop(columns=["game_id"])
        parts.append(part)
    states = pd.concat(parts, ignore_index=True).merge(
        bridge[["event_id", "game_id", "home_nba", "away_nba"]], on="event_id", how="inner",
        validate="many_to_one")
    garbage = pd.read_parquet(GARBAGE, columns=["game_id", "period", "game_clock_sec", "is_garbage_time"])
    garbage["game_id"] = garbage["game_id"].astype(str)
    available = {game for game in states["game_id"].unique() if all(
        (QUARTER_BOX / (game + "_q" + str(q) + ".json")).exists() for q in range(1, 5))}
    parts = []
    for label, period, seconds in CHECKPOINTS:
        snap = states.assign(distance=(states["seconds_remaining"].astype(float) - seconds).abs())
        snap = snap.sort_values(["game_id", "distance"], kind="stable").groupby("game_id", as_index=False).first()
        snap = snap.loc[snap["game_id"].isin(available)].copy()
        gt = garbage.loc[garbage["period"] == period].copy()
        gt["distance"] = gt["game_clock_sec"].astype(float).abs()
        gt = gt.sort_values(["game_id", "distance"], kind="stable").groupby("game_id", as_index=False).first()
        snap = snap.merge(gt[["game_id", "is_garbage_time"]], on="game_id", how="left", validate="one_to_one")
        snap["garbage_time"] = snap["is_garbage_time"].eq(True)
        snap["partition"] = np.where(snap["is_garbage_time"].isna(), "garbage-unavailable",
                                     np.where(snap["garbage_time"], "garbage-time", "non-garbage"))
        snap["checkpoint"], snap["period"] = label, period
        snap["key"] = snap["game_id"] + "|" + label
        snap["date"] = pd.to_datetime(snap["date"]).dt.date.astype(str)
        parts.append(snap[["key", "game_id", "checkpoint", "period", "date", "home_nba", "away_nba",
                           "state_diff", "pace_so_far", "run_diff", "garbage_time", "partition"]])
    out = pd.concat(parts, ignore_index=True).rename(columns={"home_nba": "home", "away_nba": "away",
        "state_diff": "margin", "pace_so_far": "pace"})
    if out["game_id"].nunique() != 1231:
        raise AssertionError("expected 1231 exact bridged games with q1-q4")
    return out


def build_states() -> tuple[list[dict], dict[str, pd.DataFrame], pd.DataFrame]:
    """Construct strict evaluator states and a separate immutable scoring-label table."""
    snapshots = _state_snapshots()
    labels: dict[str, pd.DataFrame] = {}
    states = []
    for row in snapshots.itertuples(index=False):
        labels[row.key] = _quarter_rows(row.game_id, row.period).assign(
            game_id=row.game_id, checkpoint=row.checkpoint, garbage_time=row.garbage_time,
            partition=row.partition, margin_bin=_margin_bin(row.margin))
    for game_id, game in snapshots.groupby("game_id", sort=True):
        row = game.iloc[0]
        states.append({"game_id": game_id, "state_ts": row["date"] + "T12:00:00",
                       "home": row["home"], "away": row["away"], "outcome": 0,
                       "features": {"checkpoint_count": float(len(game))},
                       "feature_avail": {"checkpoint_count": row["date"] + "T00:00:00"}})
    return states, labels, snapshots


def _parameters(train: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, float, float]:
    """Fit train-only unconditional and state-conditioned distribution parameters."""
    keys = ["checkpoint", "stat"]
    naive = train.groupby(keys)["remaining"].agg(["mean", "std", "count"])
    state_keys = keys + ["garbage_time", "margin_bin"]
    rate = train.assign(rate_mu=train["partial"] / train["elapsed_fraction"] * train["remaining_fraction"])
    rate["residual"] = rate["remaining"] - rate["rate_mu"]
    conditional = rate.groupby(state_keys)["residual"].agg(["mean", "std", "count"])
    return naive, conditional, float(train["remaining"].mean()), float(train["remaining"].std())


def _distribution(params: tuple[pd.DataFrame, pd.DataFrame, float, float], test: pd.DataFrame) -> pd.DataFrame:
    """Apply train-only parameters to one test game's as-of player observations."""
    naive, conditional, fallback_mu, fallback_sigma = params
    out = test.copy()
    keys = ["checkpoint", "stat"]
    state_keys = keys + ["garbage_time", "margin_bin"]
    out = out.join(naive.rename(columns={"mean": "naive_mu", "std": "naive_sigma", "count": "naive_n"}), on=keys)
    out = out.join(conditional.rename(columns={"mean": "resid_mu", "std": "model_sigma", "count": "model_n"}), on=state_keys)
    out["naive_mu"] = out["naive_mu"].fillna(fallback_mu)
    out["naive_sigma"] = out["naive_sigma"].fillna(fallback_sigma).fillna(1.0).clip(lower=1.0)
    out["model_sigma"] = out["model_sigma"].where(out["model_n"].fillna(0) >= 30, out["naive_sigma"])
    out["resid_mu"] = out["resid_mu"].where(out["model_n"].fillna(0) >= 30, 0.0).fillna(0.0)
    out["model_mu"] = out["partial"] / out["elapsed_fraction"] * out["remaining_fraction"] + out["resid_mu"]
    return out


def score() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Score all units inside the CPCV predictor callback; no local fold loop exists."""
    states, labels, snapshots = build_states()
    labels_by_game = {game: pd.concat([labels[game + "|" + label] for label, _, _ in CHECKPOINTS],
                                       ignore_index=True) for game in snapshots["game_id"].drop_duplicates()}
    all_labels = pd.concat(labels_by_game.values(), ignore_index=True)
    params_cache: dict[tuple[str, ...], dict[str, tuple[pd.DataFrame, pd.DataFrame, float, float]]] = {}
    scored: list[pd.DataFrame] = []
    fractions = {"end_q1": (0.25, 0.75), "end_q2": (0.50, 0.50), "end_q3": (0.75, 0.25)}

    def callback(train_states: list[dict], test_state: dict, _: bool) -> float:
        train_ids = tuple(sorted(row["game_id"] for row in train_states))
        if train_ids not in params_cache:
            train_all = all_labels.loc[all_labels["game_id"].isin(train_ids)].copy()
            params_cache[train_ids] = {}
            for label, elapsed_remaining in fractions.items():
                elapsed, remaining = elapsed_remaining
                train = train_all.loc[train_all["checkpoint"] == label].copy()
                train["elapsed_fraction"], train["remaining_fraction"] = elapsed, remaining
                params_cache[train_ids][label] = _parameters(train)
        for label, elapsed_remaining in fractions.items():
            elapsed, remaining = elapsed_remaining
            test = labels[test_state["game_id"] + "|" + label].copy()
            test["elapsed_fraction"], test["remaining_fraction"] = elapsed, remaining
            output = _distribution(params_cache[train_ids][label], test)
            output["model_crps"] = gaussian_crps(output["model_mu"], output["model_sigma"], output["remaining"])
            output["naive_crps"] = gaussian_crps(output["naive_mu"], output["naive_sigma"], output["remaining"])
            output["state_ts"] = test_state["state_ts"]
            output["train_games"] = len(train_states)
            scored.append(output)
        return 0.5

    records = cpcv_evaluate(states, callback, n_groups=N_GROUPS, n_test_groups=N_TEST_GROUPS,
                            embargo_days=EMBARGO_DAYS, strict_redaction=True)
    if len(records) != len(states) or len(scored) != len(states) * len(CHECKPOINTS):
        raise AssertionError("CPCV did not score every fixed checkpoint state")
    return pd.concat(scored, ignore_index=True), snapshots


def recompute_game_crps(series: pd.DataFrame, game_id: str) -> dict[str, float]:
    """Recompute both game-level CRPS means from the archived distribution parameters."""
    game = series.loc[series["game_id"].astype(str) == str(game_id)]
    return {"model": float(gaussian_crps(game["model_mu"], game["model_sigma"], game["remaining"]).mean()),
            "naive": float(gaussian_crps(game["naive_mu"], game["naive_sigma"], game["remaining"]).mean())}


def _bootstrap(values: np.ndarray) -> tuple[float, float]:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    draws = np.array([values[rng.integers(0, len(values), len(values))].mean() for _ in range(BOOTSTRAP_REPS)])
    return float(np.quantile(draws, .025)), float(np.quantile(draws, .975))


def summarize(series: pd.DataFrame) -> list[dict]:
    """Game-clustered table with garbage-time partitions retained separately."""
    rows = []
    for (checkpoint, partition), part in series.groupby(["checkpoint", "partition"], sort=True):
        game = part.groupby("game_id", sort=True)[["model_crps", "naive_crps"]].mean()
        delta = (game["model_crps"] - game["naive_crps"]).to_numpy(float)
        rows.append({"checkpoint": checkpoint, "partition": partition,
                     "n_games": int(len(game)), "state_conditioned_crps": float(game["model_crps"].mean()),
                     "naive_crps": float(game["naive_crps"].mean()), "difference": float(delta.mean()),
                     "difference_ci95": list(_bootstrap(delta))})
    return rows


def run(out_dir: Path = OUT) -> dict:
    """Write the reproducible S245 paired archive and summary, then print its fixed table."""
    series, snapshots = score()
    out_dir.mkdir(parents=True, exist_ok=True)
    paired = out_dir / "S245_attempt2_paired_losses_2026-09-04.csv.gz"
    summary_path = out_dir / "S245_attempt2_summary_2026-09-04.json"
    keep = ["game_id", "checkpoint", "player_id", "team", "stat", "partial", "remaining",
            "garbage_time", "partition", "margin_bin", "model_mu", "model_sigma", "naive_mu", "naive_sigma",
            "model_crps", "naive_crps", "state_ts", "train_games"]
    series[keep].to_csv(paired, index=False, compression="gzip", encoding="ascii")
    summary = {"preregistration": "docs/evidence/harness/S245_attempt2_prereg_2026-09-04.md",
               "prereg_sha256_payload": "cc75e0f963502c71825359598cd619c0c2667883e5c9fe6dedb110692d4536d5",
               "paired_archive": paired.relative_to(REPO).as_posix(),
               "paired_archive_sha256": _file_sha256(paired), "rows": int(len(series)),
               "games": int(series["game_id"].nunique()), "snapshot_states": int(len(snapshots)),
               "table": summarize(series), "route_sha256": _file_sha256(Path(__file__))}
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=OUT)
    args = parser.parse_args()
    summary = run(args.out_dir)
    for row in summary["table"]:
        print("%s %s n=%d state=%.6f naive=%.6f diff=%.6f ci=[%.6f,%.6f]" %
              (row["checkpoint"], row["partition"], row["n_games"], row["state_conditioned_crps"],
               row["naive_crps"], row["difference"], row["difference_ci95"][0], row["difference_ci95"][1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
