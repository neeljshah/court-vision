"""Run S261 attempt 2's full CPCV calibration archive within a hard RSS limit."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import psutil

from scripts.platformkit import s261_ingame_headline_rederive_v2 as base
from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate

_REPO = Path(__file__).resolve().parents[2]
_PREREG = "S261_ingame_headline_rederive_v2_attempt2_prereg_2026-09-04.md"
_SEAL = "1DCB38B6CBB59694CD4A722AA843BE9694905ADC292B9A17ACE9F95D29E984FB"
_LIMIT_MB = 700.0


class MemoryLimit(RuntimeError):
    """Signal a declared fresh-process RSS limit before a sample fallback exists."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _rss_mb() -> float:
    return psutil.Process().memory_info().rss / (1024 * 1024)


def _memory(sport: str, phase: str) -> None:
    rss = _rss_mb()
    print(f"RSS sport={sport} phase={phase} rss_mb={rss:.3f}")
    if rss > _LIMIT_MB:
        print(f"MEMORY LIMIT sport={sport} rss_mb={rss:.3f} limit_mb={_LIMIT_MB:.0f}")
        raise MemoryLimit(sport)


def _route(sport: str) -> tuple[Any, Any, Any]:
    if sport == "nba":
        from scipy.special import ndtri
        from scripts.platformkit.proof_nba import ingame_accuracy as route
        return route, route.get_repricer("nba"), ndtri
    from scripts.platformkit.proof_mlb import ingame_accuracy as route
    return route, route.get_repricer("mlb"), None


def _state_rows(states: list[dict[str, Any]], meta: dict[str, tuple[str, str]], sport: str) -> list[dict[str, Any]]:
    """Stream each CPCV path into an archive-ready per-state paired-loss reducer."""
    route, repricer, ndtri = _route(sport)
    rates: dict[str, float] = {}
    last_train: list[dict[str, Any]] | None = None
    score_cache: dict[tuple[int, int, int], float] = {}
    pending: dict[str, tuple[float, float, float]] = {}
    reduced: dict[str, dict[str, Any]] = {}
    seen = 0

    def predict(train: list[dict[str, Any]], test: dict[str, Any], _: bool) -> float:
        nonlocal last_train, rates
        if train is not last_train:
            rates, last_train = base._team_rates(train), train
        prior = float(np.clip((rates.get(test["home"], .5) + 1.0 - rates.get(test["away"], .5)) / 2.0, .01, .99))
        checkpoint, home_score, away_score = (int(test["features"][key]) for key in
                                              ("checkpoint", "home_score", "away_score"))
        score_key = (checkpoint, home_score, away_score)
        if sport == "nba":
            blind = {"mu_home": route._LEAGUE_MU, "mu_away": route._LEAGUE_MU}
            diff = float(ndtri(prior) * route._DEF_MARGIN_SIGMA)
            rated = {"mu_home": route._LEAGUE_MU + diff / 2.0, "mu_away": route._LEAGUE_MU - diff / 2.0}
            if score_key not in score_cache:
                score_cache[score_key] = float(repricer.reprice(route.GameState(
                    "nba", dict(route._CHECKPOINTS)[checkpoint], home_score, away_score,
                    pregame_params=blind))["win_home"])
            conditional = float(repricer.reprice(route.GameState(
                "nba", dict(route._CHECKPOINTS)[checkpoint], home_score, away_score,
                pregame_params=rated))["win_home"])
        else:
            if score_key not in score_cache:
                score_cache[score_key] = route._reprice_winhome(
                    repricer, home_score, away_score, checkpoint, route._LEAGUE_LAMBDA,
                    route._LEAGUE_LAMBDA, route._FALLBACK_R, route._FALLBACK_R)
            lambdas = route._anchor_nb_tiesplit(route._LEAGUE_LAMBDA, route._LEAGUE_LAMBDA,
                                                 route._FALLBACK_R, route._FALLBACK_R, prior)
            conditional = route._reprice_winhome(repricer, home_score, away_score, checkpoint,
                                                 lambdas[0], lambdas[1], route._FALLBACK_R, route._FALLBACK_R)
        pending[test["game_id"]] = (prior, score_cache[score_key], conditional)
        return prior

    def consume(record: dict[str, Any]) -> None:
        nonlocal seen
        static, score, conditional = pending.pop(record["game_id"])
        state_id = str(record["game_id"])
        cluster_id, timestamp = meta[state_id]
        item = reduced.setdefault(state_id, {"state_id": state_id, "cluster_id": cluster_id,
            "timestamp": timestamp, "raw_checkpoint_count": 1, "path_evaluation_count": 0,
            "split_values": [], "static_loss_sum": 0.0, "score_loss_sum": 0.0,
            "conditional_loss_sum": 0.0})
        item["path_evaluation_count"] += 1
        item["split_values"].append(int(record["split_id"]))
        for arm, value in (("static", static), ("score", score), ("conditional", conditional)):
            item[f"{arm}_loss_sum"] += (value - float(record["y"])) ** 2
        seen += 1
        if seen % 10000 == 0:
            _memory(sport, "during")

    cpcv_evaluate(states, predict, n_groups=8, n_test_groups=2, embargo_days=1,
                  strict_redaction=True, record_consumer=consume, collect_records=False)
    assert not pending
    rows = []
    for item in reduced.values():
        item["split_ids"] = "|".join(str(value) for value in item.pop("split_values"))
        for arm in ("static", "score", "conditional"):
            item[f"{arm}_loss_sum"] /= item["path_evaluation_count"]
        rows.append(item)
    return sorted(rows, key=lambda row: (row["timestamp"], row["state_id"]))


def _sport_summary(sport: str, collector: Any, output_dir: Path) -> dict[str, Any]:
    _memory(sport, "before")
    states, meta, inputs, exclusions = collector()
    rows = _state_rows(states, meta, sport)
    _memory(sport, "after")
    path = output_dir / f"S261_{sport}_per_state_losses_attempt2_2026-09-04.csv"
    base._write_csv(path, rows)
    clusters, briers = base._clusters(rows), base._briers(rows)
    reread = base._briers(list(csv.DictReader(path.open(encoding="ascii"))))
    public_diffs, exact_diffs = base._public_diffs(sport, briers)
    return {"game_path_count": len(clusters), "checkpoint_count": sum(row["raw_checkpoint_count"] for row in rows),
            "cpcv_path_evaluation_count": sum(row["path_evaluation_count"] for row in rows), "brier": briers,
            "shares": base._shares(briers), "prior_share_ci": base._cluster_interval(clusters),
            "reproduction_abs_diff": {arm: abs(briers[arm] - reread[arm]) for arm in briers},
            "public_value_abs_diff": public_diffs, "public_value_abs_diff_exact": exact_diffs,
            "public_value_status": {arm: "NOT REPRODUCED" for arm in public_diffs},
            "series_path": str(path), "inputs": inputs, "exclusions": exclusions}


def archive(output_dir: Path) -> dict[str, Any]:
    """Archive every admitted full-corpus path, or fail with the declared limit."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sports = {"nba": _sport_summary("nba", base._nba_states, output_dir),
              "mlb": _sport_summary("mlb", base._mlb_states, output_dir)}
    return {"schema_version": 4, "run_scope": "full_local", "sample_game_path_limit": 0,
            "preregistration": _PREREG, "prereg_seal_sha256": _SEAL, "helper_sha256": _sha256(Path(__file__)),
            "route_sha256": {"s261_base": _sha256(Path(base.__file__)),
                             "cpcv_engine": _sha256(_REPO / "scripts/platformkit/eval_gate/cpcv_engine.py")},
            "evaluation": {"engine": "cpcv_evaluate", "n_groups": 8, "n_test_groups": 2,
                           "symmetric_calendar_embargo_days": 1, "same_team_purge_hours": 48,
                           "same_matchup_embargo_days": 3, "strict_redaction": True}, "sports": sports}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=_REPO / "docs/evidence/harness")
    args = parser.parse_args()
    try:
        summary = archive(args.output_dir)
    except MemoryLimit:
        return 2
    path = args.output_dir / "S261_ingame_headline_rederive_v2_attempt2_2026-09-04.json"
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    for sport, values in summary["sports"].items():
        print(f"{sport}: n_eff={values['game_path_count']} raw_checkpoints={values['checkpoint_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
