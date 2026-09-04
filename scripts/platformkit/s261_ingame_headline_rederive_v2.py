"""Archive S261's CPCV calibration rederive with additive S211 aliases."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
_BOOTSTRAPS = 10_000
_SEED = 21120260904
_PREREG = "S261_ingame_headline_rederive_v2_prereg_2026-09-04.md"
_SEAL = "B18A747EA3E602AA56CA1DE23C4C5142874B8062D206104BEAFEA3E31C9C223A"
_EXCLUSIONS = {"invalid_inning": 2458, "tied_final_score": 2246}
_PUBLIC = {"nba": {"static": "0.209", "conditional": "0.159"},
           "mlb": {"static": "0.241", "conditional": "0.126"}}
_PUBLIC_DIFF_EXACT = {"nba": {"static": "0.00983250084408843", "conditional": "0.00424678066236500"},
                      "mlb": {"static": "0.00797282410431543", "conditional": "0.00199755953257377"}}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _input_meta(path: Path) -> dict[str, Any]:
    return {"path": str(path.resolve()), "bytes": path.stat().st_size,
            "resolution": "not_applicable_parquet"}


def _state(game_id: str, date: Any, home: str, away: str, outcome: float,
           checkpoint: int, home_score: int, away_score: int) -> dict[str, Any]:
    stamp = f"{date:%Y-%m-%d}T{checkpoint:02d}:00:00"
    available = f"{date:%Y-%m-%d}T00:00:00"
    return {"game_id": game_id, "state_ts": stamp, "home": home, "away": away,
            "outcome": int(outcome),
            "features": {"checkpoint": checkpoint, "home_score": home_score, "away_score": away_score},
            "feature_avail": {"checkpoint": available, "home_score": available,
                              "away_score": available}}


def _nba_states() -> tuple[list[dict[str, Any]], dict[str, tuple[str, str]], list[dict[str, Any]], dict[str, int]]:
    from scripts.platformkit.proof_nba import ingame_accuracy as nba

    path, frame = nba._linescores_path(None), nba._load(nba._linescores_path(None))
    states, meta = [], {}
    for _, row in frame.iterrows():
        outcome = float(row["home_final"] > row["away_final"])
        for checkpoint, _ in nba._CHECKPOINTS:
            state_id = f"{row['event_id']}:{checkpoint}"
            states.append(_state(state_id, row["date"], str(row["home_abbr"]), str(row["away_abbr"]), outcome,
                                 checkpoint, sum(row[f"home_q{k}"] for k in range(1, checkpoint + 1)),
                                 sum(row[f"away_q{k}"] for k in range(1, checkpoint + 1))))
            meta[state_id] = (str(row["event_id"]), f"{row['date']:%Y-%m-%d}")
    return states, meta, [_input_meta(path)], {"invalid_inning": 0, "tied_final_score": 0}


def _mlb_states() -> tuple[list[dict[str, Any]], dict[str, tuple[str, str]], list[dict[str, Any]], dict[str, int]]:
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
    exclusions = {"invalid_inning": 0, "tied_final_score": 0}
    for _, row in frame.iterrows():
        home, away = mlb._parse_innings(row["home_innings"]), mlb._parse_innings(row["away_innings"])
        if home is None or away is None:
            exclusions["invalid_inning"] += 1
            continue
        if sum(home) == sum(away):
            exclusions["tied_final_score"] += 1
            continue
        outcome = float(sum(home) > sum(away))
        for checkpoint in mlb._CHECKPOINTS:
            if len(home) < checkpoint or len(away) < checkpoint:
                continue
            state_id = f"{row['event_id']}:{checkpoint}"
            states.append(_state(state_id, row["date"], str(row["home_team"]), str(row["away_team"]), outcome,
                                 checkpoint, sum(home[:checkpoint]), sum(away[:checkpoint])))
            meta[state_id] = (str(row["event_id"]), f"{row['date']:%Y-%m-%d}")
    assert exclusions == _EXCLUSIONS, exclusions
    return states, meta, [_input_meta(games_path), _input_meta(pitchers_path)], exclusions


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
    """Compute every scored arm inside the shared purged CPCV callback."""
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
            rates, last_train = _team_rates(train), train
        prior = float(np.clip((rates.get(test["home"], .5) + 1.0 - rates.get(test["away"], .5)) / 2.0, .01, .99))
        checkpoint, home_score, away_score = (int(test["features"][key]) for key in
                                              ("checkpoint", "home_score", "away_score"))
        score_key = (checkpoint, home_score, away_score)
        conditional_key = (test["home"], test["away"], *score_key, prior)
        if sport == "nba":
            blind = {"mu_home": route._LEAGUE_MU, "mu_away": route._LEAGUE_MU}
            diff = float(ndtri(prior) * route._DEF_MARGIN_SIGMA)
            rated = {"mu_home": route._LEAGUE_MU + diff / 2.0, "mu_away": route._LEAGUE_MU - diff / 2.0}
            if score_key not in score_cache:
                score_cache[score_key] = float(repricer.reprice(route.GameState(
                    "nba", dict(checkpoints)[checkpoint], home_score, away_score, pregame_params=blind))["win_home"])
            if conditional_key not in conditional_cache:
                conditional_cache[conditional_key] = float(repricer.reprice(route.GameState(
                    "nba", dict(checkpoints)[checkpoint], home_score, away_score, pregame_params=rated))["win_home"])
        else:
            lambdas = route._anchor_nb_tiesplit(route._LEAGUE_LAMBDA, route._LEAGUE_LAMBDA,
                                                 route._FALLBACK_R, route._FALLBACK_R, prior)
            if score_key not in score_cache:
                score_cache[score_key] = route._reprice_winhome(repricer, *score_key, route._LEAGUE_LAMBDA,
                                                                 route._LEAGUE_LAMBDA, route._FALLBACK_R, route._FALLBACK_R)
            if conditional_key not in conditional_cache:
                conditional_cache[conditional_key] = route._reprice_winhome(repricer, *score_key, lambdas[0],
                                                                              lambdas[1], route._FALLBACK_R, route._FALLBACK_R)
        triplets.append((test["game_id"], prior, score_cache[score_key], conditional_cache[conditional_key]))
        return prior

    records = cpcv_evaluate(states, predict, n_groups=8, n_test_groups=2, embargo_days=1, strict_redaction=True)
    assert len(records) == len(triplets)
    return [{"state_id": record["game_id"], "static": static, "score": score,
             "conditional": conditional, "outcome": float(record["y"]), "split_id": record["split_id"]}
            for record, (_, static, score, conditional) in zip(records, triplets)]


def _state_losses(scored: list[dict[str, Any]], meta: dict[str, tuple[str, str]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in scored:
        grouped[row["state_id"]].append(row)
    rows = []
    for state_id, values in grouped.items():
        cluster_id, timestamp = meta[state_id]
        row: dict[str, Any] = {"state_id": state_id, "cluster_id": cluster_id, "timestamp": timestamp,
                               "raw_checkpoint_count": 1, "path_evaluation_count": len(values),
                               "split_ids": "|".join(str(item["split_id"]) for item in values)}
        for arm in ("static", "score", "conditional"):
            row[f"{arm}_loss_sum"] = sum((item[arm] - item["outcome"]) ** 2 for item in values) / len(values)
        rows.append(row)
    return sorted(rows, key=lambda row: (row["timestamp"], row["state_id"]))


def _briers(rows: list[dict[str, Any]]) -> dict[str, float]:
    count = sum(int(row["raw_checkpoint_count"]) for row in rows)
    return {arm: sum(float(row[f"{arm}_loss_sum"]) for row in rows) / count
            for arm in ("static", "score", "conditional")}


def _clusters(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = grouped.setdefault(row["cluster_id"], {"cluster_id": row["cluster_id"], "raw_checkpoint_count": 0,
                                                        "static_loss_sum": 0.0, "score_loss_sum": 0.0,
                                                        "conditional_loss_sum": 0.0})
        item["raw_checkpoint_count"] += row["raw_checkpoint_count"]
        for arm in ("static", "score", "conditional"):
            item[f"{arm}_loss_sum"] += row[f"{arm}_loss_sum"]
    return list(grouped.values())


def _shares(briers: dict[str, float]) -> dict[str, float]:
    total = briers["static"] - briers["conditional"]
    return {"total_calibration_change": total, "static_minus_conditional": total,
            "score_only_share": (briers["static"] - briers["score"]) / total,
            "model_prior_contribution": briers["score"] - briers["conditional"],
            "model_prior_share": (briers["score"] - briers["conditional"]) / total}


def _cluster_interval(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    sums = np.array([[row[f"{arm}_loss_sum"] for arm in ("static", "score", "conditional")] for row in rows])
    counts = np.array([row["raw_checkpoint_count"] for row in rows])
    rng, samples = np.random.default_rng(_SEED), np.empty(_BOOTSTRAPS)
    for start in range(0, _BOOTSTRAPS, 128):
        picked = rng.integers(0, n, size=(min(128, _BOOTSTRAPS - start), n))
        weighted = sums[picked].sum(axis=1) / counts[picked].sum(axis=1)[:, None]
        samples[start:start + len(picked)] = (weighted[:, 1] - weighted[:, 2]) / (weighted[:, 0] - weighted[:, 2])
    finite = samples[np.isfinite(samples)]
    return {"reported": True, "n_eff": n, "method": "game_cluster_bootstrap_percentile", "seed": _SEED,
            "resamples": _BOOTSTRAPS, "finite_resamples": int(len(finite)),
            "lower": float(np.quantile(finite, .025)), "upper": float(np.quantile(finite, .975))}


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _public_diffs(sport: str, briers: dict[str, float]) -> tuple[dict[str, float], dict[str, str]]:
    exact = _PUBLIC_DIFF_EXACT[sport]
    for arm, value in _PUBLIC[sport].items():
        observed = abs(Decimal(str(briers[arm])) - Decimal(value))
        assert abs(observed - Decimal(exact[arm])) <= Decimal("1e-12"), (sport, arm, observed)
    return {arm: float(value) for arm, value in exact.items()}, exact


def _even_game_sample(states: list[dict[str, Any]], meta: dict[str, tuple[str, str]], limit: int) -> list[dict[str, Any]]:
    if not limit:
        return states
    game_ids = list(dict.fromkeys(meta[row["game_id"]][0] for row in states))
    if limit >= len(game_ids):
        return states
    selected = {game_ids[index] for index in np.linspace(0, len(game_ids) - 1, limit, dtype=int)}
    return [row for row in states if meta[row["game_id"]][0] in selected]


def archive(output_dir: Path, *, validate_public: bool = True, sample_game_paths: int = 0) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    sports: dict[str, Any] = {}
    for sport, collector in (("nba", _nba_states), ("mlb", _mlb_states)):
        states, meta, inputs, exclusions = collector()
        states = _even_game_sample(states, meta, sample_game_paths)
        rows = _state_losses(_oos_triplets(states, sport), meta)
        clusters, briers = _clusters(rows), _briers(rows)
        label = "sample_" if sample_game_paths else ""
        path = output_dir / f"S261_{label}{sport}_per_state_losses_2026-09-04.csv"
        _write_csv(path, rows)
        reread = _briers(list(csv.DictReader(path.open(encoding="ascii"))))
        public_diffs, exact_diffs = (_public_diffs(sport, briers) if validate_public else
                                     ({}, _PUBLIC_DIFF_EXACT[sport]))
        sports[sport] = {"game_path_count": len(clusters),
                         "checkpoint_count": sum(row["raw_checkpoint_count"] for row in rows),
                         "cpcv_path_evaluation_count": sum(row["path_evaluation_count"] for row in rows),
                         "brier": briers, "shares": _shares(briers), "prior_share_ci": _cluster_interval(clusters),
                         "reproduction_abs_diff": {arm: abs(briers[arm] - reread[arm]) for arm in briers},
                         "public_value_abs_diff": public_diffs, "public_value_abs_diff_exact": exact_diffs,
                         "series_path": str(path), "inputs": inputs, "exclusions": exclusions}
    return {"schema_version": 3, "run_scope": "sample_scale_local" if sample_game_paths else "full_local",
            "sample_game_path_limit": sample_game_paths, "preregistration": _PREREG, "prereg_seal_sha256": _SEAL,
            "helper_sha256": _sha256(Path(__file__)), "evaluation": {"engine": "cpcv_evaluate", "n_groups": 8,
            "n_test_groups": 2, "symmetric_calendar_embargo_days": 1, "same_team_purge_hours": 48,
            "same_matchup_embargo_days": 3, "strict_redaction": True}, "sports": sports}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=_REPO / "docs" / "evidence" / "harness")
    parser.add_argument("--sample-game-paths", type=int, default=0)
    args = parser.parse_args()
    output = args.output_dir
    summary = archive(output, validate_public=not bool(args.sample_game_paths),
                      sample_game_paths=args.sample_game_paths)
    label = "_sample" if args.sample_game_paths else ""
    (output / f"S261_ingame_headline_rederive_v2{label}_2026-09-04.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    for sport, values in summary["sports"].items():
        print(f"{sport}: n_eff={values['game_path_count']} raw_checkpoints={values['checkpoint_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
