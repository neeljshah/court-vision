"""Emit S296 strict-prior full-boxscore distributional OOF evidence."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from bisect import bisect_left
from collections import defaultdict
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import psutil

from scripts.platformkit.eval_gate.cpcv_vector_distribution import cpcv_evaluate_vector_distributional
from scripts.platformkit.s292_preflight import preflight
from scripts.platformkit.s296_report import (  # re-exported so the scorer stays the single entry point
    DATE, FIELDS, MIN_FOLD_GAMES, PREREGS, ROOT, _fold_table, _seal, _sha, _summary, _write)

INPUT_ROOT = Path(os.environ.get("S296_INPUT_ROOT", str(ROOT / "data")))
SOURCES = (INPUT_ROOT / "domains/basketball_nba/player_boxscores.parquet",
           INPUT_ROOT / "cache/omni_box_refresh/nba_player_box_extension.parquet")
OOF = tuple(INPUT_ROOT / "cache" / name for name in ("pts_q50_oof_int95.parquet",
    "reb_q50_oof_int95.parquet", "ast_q50_oof_int95.parquet", "blk_q50_oof_int90.parquet"))
ROUTE = (Path(__file__), ROOT / "scripts/platformkit/s296_report.py",
         ROOT / "scripts/platformkit/s292_preflight.py",
         ROOT / "scripts/platformkit/eval_gate/cpcv_vector_distribution.py",
         ROOT / "scripts/platformkit/eval_gate/cpcv_engine.py")
N_SAMPLES, N_GROUPS, EMBARGO_DAYS = 25, 5, 1


def _rss(label: str) -> float:
    value = psutil.Process(os.getpid()).memory_info().rss / 1024**2
    print("RSS_MB {0} {1:.2f}".format(label, value), flush=True)
    return float(value)


def _premise(frame: pd.DataFrame) -> dict[str, Any]:
    """Recount the union before any fit: algebra, zero-minute and roster accounting."""
    violations = {
        "oreb_plus_dreb_ne_reb": int((frame.oreb + frame.dreb != frame.reb).sum()),
        "fgm_gt_fga": int((frame.fgm > frame.fga).sum()), "fg3m_gt_fg3a": int((frame.fg3m > frame.fg3a).sum()),
        "fg3m_gt_fgm": int((frame.fg3m > frame.fgm).sum()), "ftm_gt_fta": int((frame.ftm > frame.fta).sum()),
        "pts_identity_broken": int((2 * (frame.fgm - frame.fg3m) + 3 * frame.fg3m + frame.ftm != frame.pts).sum()),
        "negative_field": int((frame[list(FIELDS[:-1])] < 0).any(axis=1).sum())}
    per_team = frame.groupby(["game_id", "team"]).size()
    return {"n_rows": len(frame),
        "n_unique_player_games": int(frame.drop_duplicates(["game_id", "player_id"]).shape[0]),
        "n_games": int(frame.game_id.nunique()), "key_overlap_between_sources": 0,
        "source_algebra_violations": violations, "source_algebra_violations_total": sum(violations.values()),
        "missing_keyed_field_cells": int(frame[list(FIELDS)].isna().to_numpy().sum()),
        "observed_dnp_zero_minute_rows": int((frame["min"] == 0).sum()), "bench_rows": int((~frame.starter).sum()),
        "rows_per_game_team": {"min": int(per_team.min()), "median": float(per_team.median()),
            "max": int(per_team.max())},
        "missing_roster_records": ("NOT OBSERVABLE from these two sources: neither carries an as-of roster, so a "
            "player with no row leaves no key. Observed DNPs are rows with min == 0 and stay in every denominator; "
            "the per-game-team row-count distribution is the only quantification available."),
        "date_min": str(frame.date.min())[:10], "date_max": str(frame.date.max())[:10]}


def _load() -> tuple[pd.DataFrame, dict[str, Any]]:
    frames, inputs = [], {}
    for source in SOURCES:
        handle = pq.ParquetFile(source)
        frame = handle.read().to_pandas()
        frame["source_path"] = source.relative_to(INPUT_ROOT).as_posix()
        frames.append(frame)
        inputs[(Path("data") / source.relative_to(INPUT_ROOT)).as_posix()] = {"bytes": source.stat().st_size,
            "sha256": _sha(source), "rows": len(frame), "resolution": "none"}
    keys = [set(map(tuple, part[["game_id", "player_id"]].to_numpy())) for part in frames]
    if keys[0] & keys[1]:
        raise AssertionError("S296 premise source overlap failed")
    frame = pd.concat(frames, ignore_index=True).sort_values(["date", "game_id", "player_id"], kind="stable")
    if frame.duplicated(["game_id", "player_id"]).any() or len(frame) != 78767:
        raise AssertionError("S296 premise unique player-game binding failed")
    if frame.game_id.nunique() != 3645:
        raise AssertionError("S296 premise game binding failed")
    for source in OOF:
        handle = pq.ParquetFile(source)
        ids = handle.read_row_group(0, columns=["player_id", "date"]).slice(0, 3).to_pydict()
        inputs[(Path("data") / source.relative_to(INPUT_ROOT)).as_posix()] = {"bytes": source.stat().st_size,
            "sha256": _sha(source), "rows": handle.metadata.num_rows, "resolution": "none",
            "first3": list(zip(map(int, ids["player_id"]), map(str, ids["date"])))}
    return frame.reset_index(drop=True), inputs


def _states(frame: pd.DataFrame) -> list[dict]:
    records = []
    for row in frame.itertuples(index=False):
        stamp = pd.Timestamp(row.date).normalize() + pd.Timedelta(hours=12)
        key = "{0}|{1}".format(row.game_id, row.player_id)
        records.append({"game_id": str(row.game_id), "state_ts": stamp.isoformat(), "stable_key": key,
            "home": "player:{0}".format(row.player_id), "away": "team:{0}".format(row.team),
            "features": {"strict_prior_marker": 0.0},
            "feature_avail": {"strict_prior_marker": (stamp - pd.Timedelta(days=1)).isoformat()},
            "outcome_vector": tuple(float(getattr(row, field)) for field in FIELDS),
            "player_id": int(row.player_id)})
    if len({state["stable_key"] for state in records}) != len(records):
        raise AssertionError("duplicate stable player-game tick key")
    return records


def _draw(indices: list[int], seed_key: str) -> np.ndarray:
    if not indices:
        return np.full(N_SAMPLES, -1, dtype=int)
    seed = int(hashlib.sha256(seed_key.encode("ascii")).hexdigest()[:16], 16)
    return np.random.default_rng(seed).choice(np.asarray(indices), size=N_SAMPLES, replace=True)


def _fit_predict(train: list[dict], tests: list[dict]) -> list[dict]:
    train = sorted(train, key=lambda state: state["state_ts"])
    stamps = [state["state_ts"] for state in train]
    by_player: dict[int, list[int]] = defaultdict(list)
    player_stamps: dict[int, list[str]] = defaultdict(list)
    for index, state in enumerate(train):
        by_player[state["player_id"]].append(index)
        player_stamps[state["player_id"]].append(state["state_ts"])
    vectors = np.asarray([state["outcome_vector"] for state in train], dtype=float)
    zeros = np.zeros(len(FIELDS), dtype=float)
    scale = np.maximum(vectors.std(axis=0) if len(vectors) else np.ones(len(FIELDS)), 1e-9)
    forecasts = []
    for test in tests:
        cutoff = bisect_left(stamps, test["state_ts"])
        league = list(range(cutoff))
        player_cutoff = bisect_left(player_stamps.get(test["player_id"], []), test["state_ts"])
        player = by_player.get(test["player_id"], [])[:player_cutoff]
        candidate_idx = _draw(player or league, "candidate|" + test["stable_key"])
        baseline_idx = _draw(league, "baseline|" + test["stable_key"])
        candidate = np.vstack([zeros if index < 0 else vectors[index] for index in candidate_idx])
        baseline = np.vstack([zeros if index < 0 else vectors[index] for index in baseline_idx])
        forecasts.append({"candidate": candidate, "baseline": baseline, "scale": scale,
            "candidate_keys": ["ZERO" if index < 0 else train[index]["stable_key"] for index in candidate_idx],
            "baseline_keys": ["ZERO" if index < 0 else train[index]["stable_key"] for index in baseline_idx],
            "cold_start_zero": int(not league), "used_player_prior": int(bool(player))})
    return forecasts


def _pinball(y: float, q: float, level: float) -> float:
    return float(max(level * (y - q), (level - 1.0) * (y - q)))


def _energy(samples: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean(np.linalg.norm(samples - y, axis=1)) -
        .5 * np.mean(np.linalg.norm(samples[:, None, :] - samples[None, :, :], axis=2)))


def _coherent(vector: np.ndarray) -> bool:
    min_, pts, reb, oreb, dreb, ast, stl, blk, tov, fgm, fga, fg3m, fg3a, ftm, fta, pf, plus = vector
    return bool(min_ >= 0 and min(pts, reb, oreb, dreb, ast, stl, blk, tov, fgm, fga, fg3m, fg3a, ftm, fta, pf) >= 0
        and oreb + dreb == reb and fgm <= fga and fg3m <= fg3a and fg3m <= fgm and ftm <= fta
        and 2 * (fgm - fg3m) + 3 * fg3m + ftm == pts)


def _score(forecast: dict, outcome: Iterable[float]) -> dict[str, float]:
    result: dict[str, float] = {}
    y = np.asarray(tuple(outcome), dtype=float)
    scale = np.asarray(forecast["scale"], dtype=float)
    for arm in ("baseline", "candidate"):
        samples = forecast[arm]
        ordered = np.sort(samples, axis=0)
        for index, field in enumerate(FIELDS):
            values = ordered[:, index]
            low, mid, high, actual = float(values[2]), float(values[12]), float(values[22]), float(y[index])
            inside = float(low <= actual <= high)
            result[arm + "_" + field + "_crps"] = float(np.mean(np.abs(values - actual)) -
                0.5 * np.mean(np.abs(values[:, None] - values[None, :])))
            result[arm + "_" + field + "_pinball_q10"] = _pinball(actual, low, .10)
            result[arm + "_" + field + "_pinball_q50"] = _pinball(actual, mid, .50)
            result[arm + "_" + field + "_pinball_q90"] = _pinball(actual, high, .90)
            result[arm + "_" + field + "_inside80"] = inside
            result[arm + "_" + field + "_coverage_loss"] = (inside - .80) ** 2
            result[arm + "_" + field + "_below_q10"] = float(actual < low)
            result[arm + "_" + field + "_above_q90"] = float(actual > high)
            result[arm + "_" + field + "_atom_q10_eq_q90"] = float(low == high)
        result[arm + "_energy"] = _energy(samples, y)
        result[arm + "_energy_train_scaled"] = _energy(samples / scale, y / scale)
        result[arm + "_coherence_violation"] = float(any(not _coherent(sample) for sample in samples))
    return result


def main() -> None:
    _seal()
    started, before = perf_counter(), _rss("before")
    # The four S292 stores live only on the local box (three are absent on the pod and the fourth
    # is a 0-byte file there), so the preflight is measured locally and shipped in as JSON.
    argv = sys.argv[1:]
    shipped = (argv[argv.index("--preflight-json") + 1] if "--preflight-json" in argv
               else os.environ.get("S296_PREFLIGHT_JSON"))
    preflight_table = json.loads(Path(shipped).read_text(encoding="utf-8")) if shipped else preflight(INPUT_ROOT)
    print("S292_PREFLIGHT all_reproduced={0} falsified={1}".format(preflight_table["all_reproduced"],
        json.dumps(preflight_table["falsified"], sort_keys=True)), flush=True)
    if not preflight_table["all_reproduced"]:
        raise AssertionError("S292 preflight FALSIFIED; nothing is scored on an unreproduced count")
    frame, inputs = _load()
    premise = _premise(frame)
    print("S296_PREMISE " + json.dumps(premise, sort_keys=True), flush=True)
    if premise["source_algebra_violations_total"] or premise["missing_keyed_field_cells"]:
        raise AssertionError("S296 premise algebra or keyed-field bar failed")
    records = cpcv_evaluate_vector_distributional(_states(frame), _fit_predict, _score, n_groups=N_GROUPS,
        n_test_groups=1, embargo_days=EMBARGO_DAYS, strict_redaction=True, allow_keys=("stable_key", "player_id"))
    after = _rss("after")
    report = _write(frame, records, inputs, before, after, preflight_table, premise, ROUTE,
        {"embargo_days": EMBARGO_DAYS, "n_groups": N_GROUPS, "n_samples": N_SAMPLES,
         "min_fold_games": MIN_FOLD_GAMES, "date": DATE})
    print("S296_COMPLETE rows={0} games={1} rss_mb={2:.2f} wall_seconds={3:.2f}".format(report["n_rows"],
        report["n_game_clusters"], after, perf_counter() - started), flush=True)


if __name__ == "__main__":
    main()
