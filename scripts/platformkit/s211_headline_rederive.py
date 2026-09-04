"""Archive S211's three calibration arms through the shared CPCV evaluator."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
_SEED = 21120260904
_BOOTSTRAPS = 10_000
_PREREG = "S211_ingame_headline_rederive_attempt_2_prereg_2026-09-04.md"
_SEAL = "E6CE4EEAEA909412EA52321E68B2F507295C05AC1576F6D16B1592CCCC9D913D"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _input_meta(path: Path) -> dict[str, Any]:
    return {"path": str(path), "bytes": path.stat().st_size, "resolution": "not_applicable"}


def _state(game_id: str, date: Any, home: str, away: str, outcome: float,
           checkpoint: int, home_score: int, away_score: int) -> dict[str, Any]:
    stamp = f"{date:%Y-%m-%d}T{checkpoint:02d}:00:00"
    available = f"{date:%Y-%m-%d}T00:00:00"
    return {
        "game_id": game_id, "state_ts": stamp, "home": home, "away": away,
        "outcome": int(outcome),
        "features": {"checkpoint": checkpoint, "home_score": home_score, "away_score": away_score},
        "feature_avail": {"checkpoint": available, "home_score": available, "away_score": available},
    }


def _nba_states() -> tuple[list[dict[str, Any]], dict[str, tuple[str, str]], list[dict[str, Any]]]:
    from scripts.platformkit.proof_nba import ingame_accuracy as nba

    path = nba._linescores_path(None)
    frame = nba._load(path)
    states, meta = [], {}
    for _, row in frame.iterrows():
        outcome = float(row["home_final"] > row["away_final"])
        for quarter, _ in nba._CHECKPOINTS:
            state_id = f"{row['event_id']}:{quarter}"
            states.append(_state(state_id, row["date"], str(row["home_abbr"]), str(row["away_abbr"]), outcome,
                                 quarter, int(sum(row[f"home_q{k}"] for k in range(1, quarter + 1))),
                                 int(sum(row[f"away_q{k}"] for k in range(1, quarter + 1)))))
            meta[state_id] = (str(row["event_id"]), f"{row['date']:%Y-%m-%d}")
    return states, meta, [_input_meta(path)]


def _mlb_states() -> tuple[list[dict[str, Any]], dict[str, tuple[str, str]], list[dict[str, Any]]]:
    import pandas as pd
    from scripts.platformkit.proof_mlb import ingame_accuracy as mlb

    root = mlb._corpus_from_env()
    games_path = (root / "games.parquet") if root else mlb._GAMES
    pitchers_path = (root / "pitchers.parquet") if root else mlb._PITCHERS
    games = pd.read_parquet(games_path)
    pitchers = pd.read_parquet(pitchers_path)[["event_id", "home_innings", "away_innings"]]
    frame = games.merge(pitchers, on="event_id", how="inner").sort_values(
        ["date", "game_seq", "event_id"]).reset_index(drop=True)
    states, meta = [], {}
    for _, row in frame.iterrows():
        home, away = mlb._parse_innings(row["home_innings"]), mlb._parse_innings(row["away_innings"])
        if home is None or away is None or sum(home) == sum(away):
            continue
        outcome = float(sum(home) > sum(away))
        for checkpoint in mlb._CHECKPOINTS:
            if len(home) < checkpoint or len(away) < checkpoint:
                continue
            state_id = f"{row['event_id']}:{checkpoint}"
            states.append(_state(state_id, row["date"], str(row["home_team"]), str(row["away_team"]), outcome,
                                 checkpoint, sum(home[:checkpoint]), sum(away[:checkpoint])))
            meta[state_id] = (str(row["event_id"]), f"{row['date']:%Y-%m-%d}")
    return states, meta, [_input_meta(games_path), _input_meta(pitchers_path)]


def _team_rates(train: list[dict[str, Any]]) -> dict[str, float]:
    wins: dict[str, float] = defaultdict(float)
    games: dict[str, int] = defaultdict(int)
    for row in train:
        win = float(row["outcome"])
        wins[row["home"]] += win
        wins[row["away"]] += 1.0 - win
        games[row["home"]] += 1
        games[row["away"]] += 1
    return {team: (wins[team] + 5.0) / (games[team] + 10) for team in games}


def _oos_triplets(states: list[dict[str, Any]], sport: str) -> list[dict[str, Any]]:
    """Score all arms inside shared symmetric-CPCV train/test views."""
    from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate

    if sport == "nba":
        from scipy.special import ndtri
        from scripts.platformkit.proof_nba import ingame_accuracy as route
        repricer, checkpoints = route.get_repricer("nba"), route._CHECKPOINTS
    else:
        from scripts.platformkit.proof_mlb import ingame_accuracy as route
        repricer, checkpoints = route.get_repricer("mlb"), route._CHECKPOINTS
    triplets: list[tuple[str, float, float, float]] = []
    last_train: list[dict[str, Any]] | None = None
    rates: dict[str, float] = {}
    score_cache: dict[tuple[int, int, int], float] = {}
    conditional_cache: dict[tuple[str, str, int, int, int, float], float] = {}

    def predict(train: list[dict[str, Any]], test: dict[str, Any], _: bool) -> float:
        nonlocal last_train, rates
        if train is not last_train:
            rates = _team_rates(train)
            last_train = train
        prior = float(np.clip((rates.get(test["home"], 0.5) + 1.0 - rates.get(test["away"], 0.5)) / 2.0,
                              0.01, 0.99))
        features = test["features"]
        checkpoint, home_score, away_score = (int(features[key]) for key in ("checkpoint", "home_score", "away_score"))
        score_key = (checkpoint, home_score, away_score)
        conditional_key = (test["home"], test["away"], checkpoint, home_score, away_score, prior)
        if sport == "nba":
            blind = {"mu_home": route._LEAGUE_MU, "mu_away": route._LEAGUE_MU}
            diff = float(ndtri(prior) * route._DEF_MARGIN_SIGMA)
            rated = {"mu_home": route._LEAGUE_MU + diff / 2.0, "mu_away": route._LEAGUE_MU - diff / 2.0}
            elapsed = dict(checkpoints)[checkpoint]
            if score_key not in score_cache:
                score_cache[score_key] = float(repricer.reprice(route.GameState(
                    "nba", elapsed, home_score, away_score, pregame_params=blind))["win_home"])
            if conditional_key not in conditional_cache:
                conditional_cache[conditional_key] = float(repricer.reprice(route.GameState(
                    "nba", elapsed, home_score, away_score, pregame_params=rated))["win_home"])
        else:
            lambdas = route._anchor_nb_tiesplit(route._LEAGUE_LAMBDA, route._LEAGUE_LAMBDA,
                                                 route._FALLBACK_R, route._FALLBACK_R, prior)
            if score_key not in score_cache:
                score_cache[score_key] = route._reprice_winhome(
                    repricer, home_score, away_score, checkpoint, route._LEAGUE_LAMBDA,
                    route._LEAGUE_LAMBDA, route._FALLBACK_R, route._FALLBACK_R)
            if conditional_key not in conditional_cache:
                conditional_cache[conditional_key] = route._reprice_winhome(
                    repricer, home_score, away_score, checkpoint, lambdas[0], lambdas[1],
                    route._FALLBACK_R, route._FALLBACK_R)
        score, conditional = score_cache[score_key], conditional_cache[conditional_key]
        triplets.append((test["game_id"], prior, score, conditional))
        return prior

    records = cpcv_evaluate(states, predict, n_groups=8, n_test_groups=2, embargo_days=1,
                            strict_redaction=True)
    assert len(records) == len(triplets), "CPCV output must align with every scored arm"
    return [
        {"state_id": record["game_id"], "static": static, "score": score, "conditional": conditional,
         "outcome": float(record["y"]), "split_id": record["split_id"]}
        for record, (state_id, static, score, conditional) in zip(records, triplets)
    ]


def _collapse(scored: list[dict[str, Any]], meta: dict[str, tuple[str, str]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in scored:
        game_id, timestamp = meta[row["state_id"]]
        item = grouped.setdefault(game_id, {"game_id": game_id, "timestamp": timestamp, "n_checkpoints": 0,
                                            "static_loss_sum": 0.0, "score_loss_sum": 0.0,
                                            "conditional_loss_sum": 0.0})
        item["n_checkpoints"] += 1
        for arm in ("static", "score", "conditional"):
            item[f"{arm}_loss_sum"] += (row[arm] - row["outcome"]) ** 2
    rows = []
    for item in grouped.values():
        for arm in ("static", "score", "conditional"):
            item[f"{arm}_loss_mean"] = item[f"{arm}_loss_sum"] / item["n_checkpoints"]
        rows.append(item)
    return sorted(rows, key=lambda row: (row["timestamp"], row["game_id"]))


def _briers(rows: list[dict[str, Any]]) -> dict[str, float]:
    count = sum(row["n_checkpoints"] for row in rows)
    return {arm: sum(row[f"{arm}_loss_sum"] for row in rows) / count for arm in ("static", "score", "conditional")}


def _shares(briers: dict[str, float]) -> dict[str, float]:
    total = briers["static"] - briers["conditional"]
    if total == 0.0:
        raise ValueError("static and conditional Brier are identical")
    return {"total_calibration_change": total, "score_only_share": (briers["static"] - briers["score"]) / total,
            "model_prior_contribution": briers["score"] - briers["conditional"],
            "model_prior_share": (briers["score"] - briers["conditional"]) / total}


def _cluster_interval(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if n < 30:
        return {"reported": False, "n_eff": n, "reason": "n_lt_30"}
    sums = np.array([
        [row["static_loss_sum"], row["score_loss_sum"], row["conditional_loss_sum"]]
        for row in rows
    ])
    counts = np.array([row["n_checkpoints"] for row in rows])
    rng, samples = np.random.default_rng(_SEED), np.empty(_BOOTSTRAPS)
    for start in range(0, _BOOTSTRAPS, 128):
        picked = rng.integers(0, n, size=(min(128, _BOOTSTRAPS - start), n))
        weighted = sums[picked].sum(axis=1) / counts[picked].sum(axis=1)[:, None]
        samples[start:start + len(picked)] = (weighted[:, 1] - weighted[:, 2]) / (weighted[:, 0] - weighted[:, 2])
    low, high = np.quantile(samples[np.isfinite(samples)], (0.025, 0.975))
    return {"reported": True, "n_eff": n, "method": "game_cluster_bootstrap_percentile", "seed": _SEED,
            "resamples": _BOOTSTRAPS, "lower": float(low), "upper": float(high)}


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def archive(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    sports: dict[str, Any] = {}
    for sport, collector in (("nba", _nba_states), ("mlb", _mlb_states)):
        states, meta, inputs = collector()
        rows = _collapse(_oos_triplets(states, sport), meta)
        briers = _briers(rows)
        series_name = f"S211_{sport}_per_game_losses_2026-09-04.csv"
        _write_csv(output_dir / series_name, rows)
        sports[sport] = {"game_path_count": len(rows), "checkpoint_count": sum(row["n_checkpoints"] for row in rows),
                         "brier": briers, "shares": _shares(briers), "prior_share_ci": _cluster_interval(rows),
                         "series_path": str(output_dir / series_name), "inputs": inputs}
    summary = {"schema_version": 2, "preregistration": _PREREG, "prereg_seal_sha256": _SEAL,
               "helper_sha256": _sha256(Path(__file__)), "evaluation": {"engine": "cpcv_evaluate",
               "n_groups": 8, "n_test_groups": 2, "symmetric_calendar_embargo_days": 1,
               "same_team_purge_hours": 48, "same_matchup_embargo_days": 3}, "sports": sports}
    (output_dir / "S211_ingame_headline_rederive_2026-09-04.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=_REPO / "docs" / "evidence" / "harness")
    summary = archive(parser.parse_args().output_dir)
    for sport, values in summary["sports"].items():
        print(f"{sport}: n={values['game_path_count']} checkpoints={values['checkpoint_count']}")
    print("S211 archive written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
