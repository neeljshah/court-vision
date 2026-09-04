"""S227: OOS CRPS and tail calibration for NBA in-game final-margin distributions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, Tuple

import numpy as np
import pandas as pd
from scipy.special import ndtr, ndtri

from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate

REPO = Path(__file__).resolve().parents[2]
CHECKPOINTS = REPO / "data" / "cache" / "inplay_odds" / "nba_checkpoints_full.parquet"
GARBAGE = REPO / "data" / "intelligence" / "garbage_time_segments.parquet"
DEFAULT_OUT = REPO / "docs" / "evidence" / "harness"
FROZEN_LADDER = (5, 10, 15, 20, 25, 30)
FIXED_SIGMA = 13.5
SIGMA_GRID = np.arange(3.0, 60.0 + 1e-9, 0.5)
MIN_CELL_TRAIN = 200
N_GROUPS, EMBARGO_DAYS = 5, 1
BOOTSTRAP_SEED, BOOTSTRAP_REPS = 227, 10_000


def gaussian_crps(mu: np.ndarray, scale: np.ndarray, observed: np.ndarray) -> np.ndarray:
    """Return CRPS for Normal(mu, scale), with a point-mass limit at zero scale."""
    mu, scale, observed = (np.asarray(mu, float), np.asarray(scale, float),
                           np.asarray(observed, float))
    out = np.abs(mu - observed)
    live = scale > 1e-12
    z = (observed[live] - mu[live]) / scale[live]
    phi = np.exp(-0.5 * z * z) / np.sqrt(2.0 * np.pi)
    out[live] = scale[live] * (z * (2.0 * ndtr(z) - 1.0) + 2.0 * phi - 1.0 / np.sqrt(np.pi))
    return out


def _distribution(frame: pd.DataFrame, sigma: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    r = frame["rem_fraction"].to_numpy(float)
    sigma = np.asarray(sigma, float)
    mu = frame["margin"].to_numpy(float) + sigma * ndtri(frame["p0_asof"].to_numpy(float)) * r
    return mu, sigma * np.sqrt(r)


def tail_probability(mu: np.ndarray, scale: np.ndarray, ladder: int) -> np.ndarray:
    """Return P(abs(final_margin) >= ladder) under each predictive distribution."""
    out = (ndtr((-float(ladder) - mu) / np.maximum(scale, 1e-12))
           + 1.0 - ndtr((float(ladder) - mu) / np.maximum(scale, 1e-12)))
    point = scale <= 1e-12
    out[point] = (np.abs(mu[point]) >= ladder).astype(float)
    return out


def _remaining_fraction(period: pd.Series, game_clock_s: pd.Series) -> np.ndarray:
    p, clock = period.to_numpy(int), game_clock_s.to_numpy(float)
    elapsed = np.where(p <= 4, (p - 1) * 12.0 + (720.0 - clock) / 60.0,
                       48.0 + (p - 5) * 5.0 + (300.0 - clock) / 60.0)
    rem_minutes = np.where(elapsed <= 48.0, 48.0 - elapsed,
                           5.0 - np.mod(elapsed - 48.0, 5.0))
    return np.maximum(rem_minutes, 0.0) / 48.0


def _cell(frame: pd.DataFrame) -> pd.Series:
    period = np.where(frame["period"].to_numpy(int) >= 4, "P4",
                      "P" + frame["period"].astype(int).astype(str))
    absolute = np.abs(frame["margin"].to_numpy(float))
    margin = np.where(absolute <= 5, "abs_margin_le5",
                      np.where(absolute <= 12, "abs_margin_6_12", "abs_margin_ge13"))
    rem = frame["rem_fraction"].to_numpy(float) * 48.0
    rem_bucket = np.where(rem > 12, "rem_gt12", np.where(rem > 6, "rem_6_12", "rem_le6"))
    return pd.Series(period + "|" + margin + "|" + rem_bucket, index=frame.index)


def load() -> Tuple[pd.DataFrame, Dict[str, int]]:
    columns = ["game_id", "game_date", "ts", "period", "game_clock_s", "score_home", "score_away",
               "margin", "market_prob", "outcome_home_win"]
    frame = pd.read_parquet(CHECKPOINTS, columns=columns)
    frame["game_id"] = frame["game_id"].astype(str)
    frame["ts"] = pd.to_datetime(frame["ts"], unit="s", utc=True)
    ordered = frame.sort_values(["game_id", "ts", "period", "game_clock_s"], kind="stable")
    last = ordered.groupby("game_id", sort=False).tail(1)[["game_id", "score_home", "score_away"]].copy()
    last["final_margin"] = last.pop("score_home") - last.pop("score_away")
    frame = frame.merge(last, on="game_id", how="left", validate="many_to_one")
    priors = ordered.groupby("game_id", sort=False).head(1)[["game_id", "market_prob"]].rename(
        columns={"market_prob": "p0_asof"})
    frame = frame.merge(priors, on="game_id", how="left", validate="many_to_one")
    frame["rem_fraction"] = _remaining_fraction(frame["period"], frame["game_clock_s"])
    frame["cell"] = _cell(frame)
    garbage = pd.read_parquet(GARBAGE, columns=["game_id", "is_garbage_time"])
    garbage["game_id"] = garbage["game_id"].astype(str)
    labels = garbage.groupby("game_id", sort=False)["is_garbage_time"].max().rename("garbage_time_label")
    frame = frame.merge(labels, on="game_id", how="left", validate="many_to_one")
    frame["garbage_time_label"] = frame["garbage_time_label"].astype("boolean").fillna(False).astype(bool)
    missing = int(frame["p0_asof"].isna().sum())
    if missing:
        raise AssertionError("unavailable p0_asof rows: %d" % missing)
    if frame["final_margin"].isna().any():
        raise AssertionError("unrecoverable final margin")
    return frame.sort_values(["game_date", "game_id", "ts"], kind="stable").reset_index(drop=True), {
        "ticks": int(len(frame)), "games": int(frame["game_id"].nunique()), "missing_p0_rows": missing,
        "garbage_time_labeled_games": int(frame.loc[frame["garbage_time_label"], "game_id"].nunique()),
    }


def _states(frame: pd.DataFrame) -> list[dict]:
    dates = frame.groupby("game_id", sort=False)["game_date"].first()
    return [{"game_id": game, "state_ts": str(date) + "T12:00:00", "home": "H_" + game,
             "away": "A_" + game, "features": {"game": 0.0},
             "feature_avail": {"game": str(date) + "T00:00:00"}, "outcome": 0}
            for game, date in dates.items()]


def _memberships(frame: pd.DataFrame) -> Dict[str, set[str]]:
    memberships: Dict[str, set[str]] = {}
    def record(train: list[dict], test: dict, _: bool) -> float:
        memberships[test["game_id"]] = {row["game_id"] for row in train}
        return 0.5
    records = cpcv_evaluate(_states(frame), record, n_groups=N_GROUPS, n_test_groups=1,
                            embargo_days=EMBARGO_DAYS, strict_redaction=True)
    assert len(records) == frame["game_id"].nunique() == len(memberships)
    game_date = frame.groupby("game_id", sort=False)["game_date"].first().astype("datetime64[ns]")
    for game, train_games in memberships.items():
        assert game not in train_games
        test_date = game_date.loc[game]
        assert all(abs((game_date.loc[t] - test_date).days) > EMBARGO_DAYS for t in train_games)
    return memberships


def _fit_sigma(train: pd.DataFrame) -> Dict[str, float]:
    fitted: Dict[str, float] = {}
    for cell, sub in train.groupby("cell", sort=True):
        if len(sub) < MIN_CELL_TRAIN:
            fitted[cell] = FIXED_SIGMA
            continue
        losses = []
        for sigma in SIGMA_GRID:
            mu, scale = _distribution(sub, np.full(len(sub), sigma))
            losses.append(float(gaussian_crps(mu, scale, sub["final_margin"].to_numpy(float)).mean()))
        fitted[cell] = float(SIGMA_GRID[int(np.argmin(losses))])
    return fitted


def score(frame: pd.DataFrame) -> pd.DataFrame:
    memberships = _memberships(frame)
    parts = []
    for game, train_games in memberships.items():
        test_games = [candidate for candidate, train in memberships.items() if train == train_games]
        if game != test_games[0]:
            continue
        train = frame[frame["game_id"].isin(train_games)]
        test = frame[frame["game_id"].isin(test_games)].copy()
        fitted = _fit_sigma(train)
        test["sigma_fixed"] = FIXED_SIGMA
        test["sigma_fitted"] = test["cell"].map(fitted).fillna(FIXED_SIGMA).to_numpy(float)
        for arm in ("fixed", "fitted"):
            mu, scale = _distribution(test, test["sigma_" + arm].to_numpy(float))
            test["loss_" + arm] = gaussian_crps(mu, scale, test["final_margin"].to_numpy(float))
            for ladder in FROZEN_LADDER:
                test["nominal_" + arm + "_" + str(ladder)] = tail_probability(mu, scale, ladder)
        parts.append(test)
    scored = pd.concat(parts, ignore_index=True)
    assert len(scored) == len(frame) and scored["game_id"].nunique() == frame["game_id"].nunique()
    return scored


def _bootstrap_ci(values: np.ndarray) -> Tuple[float, float]:
    rng, n = np.random.default_rng(BOOTSTRAP_SEED), len(values)
    means = np.empty(BOOTSTRAP_REPS)
    for i in range(BOOTSTRAP_REPS):
        means[i] = values[rng.integers(0, n, n)].mean()
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def summarize(scored: pd.DataFrame, coverage: Dict[str, int]) -> Tuple[pd.DataFrame, dict]:
    grouped = scored.groupby("game_id", sort=False)
    rows = []
    for game, sub in grouped:
        row = {"game_id": game, "timestamp": str(sub["ts"].min()), "n_ticks": int(len(sub)),
               "garbage_time_label": bool(sub["garbage_time_label"].iloc[0]),
               "crps_fixed": float(sub["loss_fixed"].mean()), "crps_fitted": float(sub["loss_fitted"].mean())}
        row["crps_difference_fixed_minus_fitted"] = row["crps_fixed"] - row["crps_fitted"]
        observed = np.abs(sub["final_margin"].to_numpy(float))
        for ladder in FROZEN_LADDER:
            row["empirical_" + str(ladder)] = float(np.mean(observed >= ladder))
            for arm in ("fixed", "fitted"):
                row["nominal_" + arm + "_" + str(ladder)] = float(sub["nominal_" + arm + "_" + str(ladder)].mean())
        rows.append(row)
    series = pd.DataFrame(rows)
    diff = series["crps_difference_fixed_minus_fitted"].to_numpy(float)
    tails = []
    for ladder in FROZEN_LADDER:
        empirical = float(series["empirical_" + str(ladder)].mean())
        for arm in ("fixed", "fitted"):
            nominal = float(series["nominal_" + arm + "_" + str(ladder)].mean())
            tails.append({"ladder": ladder, "arm": arm, "empirical_tail_rate": empirical,
                          "nominal_tail_rate": nominal, "coverage_gap": empirical - nominal,
                          "event_count": int((series["empirical_" + str(ladder)] * series["n_ticks"]).sum())})
    return series, {"coverage": coverage, "n_eff": int(len(series)), "crps_fixed": float(series["crps_fixed"].mean()),
                    "crps_fitted": float(series["crps_fitted"].mean()), "difference_fixed_minus_fitted": float(diff.mean()),
                    "difference_ci95": list(_bootstrap_ci(diff)), "tail_coverage": tails}


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    frame, coverage = load()
    scored = score(frame)
    series, summary = summarize(scored, coverage)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "S227_margin_tail_crps_2026-09-04_per_game.csv"
    json_path = out_dir / "S227_margin_tail_crps_2026-09-04_summary.json"
    series.to_csv(csv_path, index=False, encoding="ascii")
    summary.update({"preregistration": "docs/evidence/harness/S227_margin_tail_crps_prereg_2026-09-04.md",
                    "prereg_sha256_payload": "53915e8b77ccd7336a088b71052c325956bc4c62c0bda60679d5954c9c0b0eb7",
                    "per_game_series": str(csv_path), "frozen_ladder": list(FROZEN_LADDER),
                    "fixed_sigma": FIXED_SIGMA, "dropped_games": 0})
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="ascii")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    summary = run(args.out_dir)
    print("games %d ticks %d n_eff %d" % (summary["coverage"]["games"], summary["coverage"]["ticks"], summary["n_eff"]))
    print("crps fixed %.6f fitted %.6f diff %.6f ci95 %s" % (summary["crps_fixed"], summary["crps_fitted"], summary["difference_fixed_minus_fitted"], summary["difference_ci95"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
