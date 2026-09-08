"""S297 DNP-mixture minutes distribution scorer through the shared CPCV route."""
from __future__ import annotations

import hashlib
import json
import os
from bisect import bisect_left
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import psutil

from scripts.platformkit.eval_gate.cpcv_vector_distribution import cpcv_evaluate_vector_distributional

ROOT = Path(__file__).resolve().parents[2]
INPUT_ROOT = Path(os.environ.get("S297_INPUT_ROOT", str(ROOT / "data")))
SOURCES = (INPUT_ROOT / "domains/basketball_nba/player_boxscores.parquet",
           INPUT_ROOT / "cache/omni_box_refresh/nba_player_box_extension.parquet")
OUT = ROOT / "docs/evidence/harness"
PREREG = OUT / "S297_minutes_dnp_distribution_2026-09-07_prereg.md"
MEMO = OUT / "S297_minutes_dnp_distribution_2026-09-04.md"
SUMMARY = OUT / "S297_minutes_dnp_distribution_2026-09-07.json"
SCORES = OUT / "S297_minutes_dnp_distribution_2026-09-07_scores.csv"
LOSSES = OUT / "S297_minutes_dnp_distribution_2026-09-07_paired_losses.csv"
FOLDS = OUT / "S297_minutes_dnp_distribution_2026-09-07_folds.json"
N_DRAWS, N_GROUPS, EMBARGO_DAYS, POOL_WEIGHT, BOOTSTRAPS = 100, 5, 1, 20, 500


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rss(label: str) -> float:
    value = psutil.Process(os.getpid()).memory_info().rss / 1024**2
    print("RSS_MB {0} {1:.2f}".format(label, value), flush=True)
    return float(value)


def _seal() -> str:
    raw = PREREG.read_bytes().replace(b"\r\n", b"\n")
    prefix, suffix = raw.split(b"SEAL_SHA256:", 1)
    seal = suffix.splitlines()[0].strip().decode("ascii")
    if hashlib.sha256(prefix).hexdigest() != seal:
        raise AssertionError("S297 preregistration seal mismatch")
    return seal


def _read_source(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    reader = pq.ParquetFile(path)
    groups = [reader.read_row_group(index, columns=["game_id", "player_id", "date", "team", "min"])
              for index in range(reader.num_row_groups)]
    frame = pd.concat([group.to_pandas() for group in groups], ignore_index=True)
    return frame, {"path": (Path("data") / path.relative_to(INPUT_ROOT)).as_posix(),
                   "bytes": path.stat().st_size, "sha256": _sha(path),
                   "rows": len(frame), "row_groups": reader.num_row_groups,
                   "zero_minute_rows": int((frame["min"] == 0).sum()), "resolution": "none"}


def _load() -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    first, first_info = _read_source(SOURCES[0])
    second, second_info = _read_source(SOURCES[1])
    expected = ((77744, 326), (1023, 221))
    actual = tuple((info["rows"], info["zero_minute_rows"]) for info in (first_info, second_info))
    if actual != expected:
        raise AssertionError("S297 premise falsified: {0}".format(actual))
    frame = pd.concat([first, second], ignore_index=True).sort_values(
        ["date", "game_id", "player_id"], kind="stable").reset_index(drop=True)
    if frame.duplicated(["game_id", "player_id"]).any():
        raise AssertionError("duplicate recorded player-game key")
    return frame, [first_info, second_info]


def _states(frame: pd.DataFrame) -> list[dict[str, Any]]:
    states = []
    for row in frame.itertuples(index=False):
        stamp = pd.Timestamp(row.date).normalize() + pd.Timedelta(hours=12)
        states.append({"game_id": str(row.game_id), "state_ts": stamp.isoformat(),
                       "stable_key": "{0}|{1}".format(row.game_id, row.player_id),
                       "home": "player:{0}".format(row.player_id), "away": "team:{0}".format(row.team),
                       "features": {"minutes_prior": 0.0},
                       "feature_avail": {"minutes_prior": (stamp - pd.Timedelta(days=1)).isoformat()},
                       "player_id": int(row.player_id),
                       "outcome_vector": (float(row.min), float(row.min == 0))})
    if len({state["stable_key"] for state in states}) != len(states):
        raise AssertionError("one evaluator state per recorded player-game tick failed")
    return states


def _choice(values: list[tuple[float, str]], rng: np.random.Generator) -> tuple[float, str]:
    return values[int(rng.integers(0, len(values)))]


def _forecast(train: list[dict], tests: list[dict]) -> list[dict]:
    train = sorted(train, key=lambda state: state["state_ts"])
    stamps = [state["state_ts"] for state in train]
    by_player: dict[int, list[dict]] = {}
    for state in train:
        by_player.setdefault(state["player_id"], []).append(state)
    forecasts = []
    for test in tests:
        cutoff = bisect_left(stamps, test["state_ts"])
        history = train[:cutoff]
        positive = [(s["outcome_vector"][0], s["stable_key"]) for s in history if s["outcome_vector"][0] > 0]
        player_history = [s for s in by_player.get(test["player_id"], []) if s["state_ts"] < test["state_ts"]]
        player_positive = [(s["outcome_vector"][0], s["stable_key"]) for s in player_history
                           if s["outcome_vector"][0] > 0]
        p_league = (sum(s["outcome_vector"][1] for s in history) / len(history)) if history else 1.0
        p_player = (sum(s["outcome_vector"][1] for s in player_history) / len(player_history)) if player_history else p_league
        n_player = len(player_history)
        p_candidate = (n_player * p_player + POOL_WEIGHT * p_league) / (n_player + POOL_WEIGHT)
        seed = int(hashlib.sha256(("S297|" + test["stable_key"]).encode("ascii")).hexdigest()[:16], 16)
        rng = np.random.default_rng(seed)
        base, cand, base_keys, cand_keys = [], [], [], []
        for _ in range(N_DRAWS):
            if not positive or rng.random() < p_league:
                base.append(0.0); base_keys.append("ZERO")
            else:
                value, key = _choice(positive, rng); base.append(value); base_keys.append(key)
            if not positive or rng.random() < p_candidate:
                cand.append(0.0); cand_keys.append("ZERO")
            elif player_positive and rng.random() < 0.70:
                value, key = _choice(player_positive, rng); cand.append(value); cand_keys.append(key)
            else:
                value, key = _choice(positive, rng); cand.append(value); cand_keys.append(key)
        positive_values = [value for value, _ in player_positive] if player_positive else [value for value, _ in positive]
        positive_q = np.quantile(positive_values, [.10, .50, .90]).tolist() if positive_values else [0.0] * 3
        forecasts.append({"baseline": np.asarray(base), "candidate": np.asarray(cand),
                          "baseline_dnp_prob": float(p_league), "candidate_dnp_prob": float(p_candidate),
                          "candidate_positive_q": positive_q, "n_train_asof": len(history),
                          "n_player_asof": n_player, "asof_max_ts": history[-1]["state_ts"] if history else None,
                          "baseline_draw_keys": base_keys, "candidate_draw_keys": cand_keys})
    return forecasts


def _pinball(y: float, q: float, level: float) -> float:
    return float(max(level * (y - q), (level - 1.0) * (y - q)))


def _crps(samples: np.ndarray, y: float) -> float:
    return float(np.mean(np.abs(samples - y)) - .5 * np.mean(np.abs(samples[:, None] - samples[None, :])))


def _score(forecast: dict, outcome: Iterable[float]) -> dict[str, float]:
    minute, dnp = tuple(outcome)
    out: dict[str, float] = {}
    for arm in ("baseline", "candidate"):
        samples, probability = forecast[arm], forecast[arm + "_dnp_prob"]
        ordered = np.sort(samples)
        out[arm + "_minutes_crps"] = _crps(samples, minute)
        out[arm + "_dnp_brier"] = float((probability - dnp) ** 2)
        out[arm + "_dnp_logloss"] = float(-(dnp * np.log(max(probability, 1e-12)) +
                                            (1.0 - dnp) * np.log(max(1.0 - probability, 1e-12))))
        for level, index in ((.10, 9), (.50, 49), (.90, 89)):
            out[arm + "_pinball_q{0}".format(int(level * 100))] = _pinball(minute, float(ordered[index]), level)
        out[arm + "_inside80"] = float(ordered[9] <= minute <= ordered[89])
    return out


def _folds(records: list[dict]) -> dict[str, dict[str, Any]]:
    out = {}
    for split in sorted({record["split_id"] for record in records}):
        rows = [record for record in records if record["split_id"] == split]
        games = {record["game_id"] for record in rows}
        out[str(split)] = {"n_rows": len(rows), "n_held_out_games": len(games),
                           "min_date": min(row["ts"][:10] for row in rows),
                           "max_date": max(row["ts"][:10] for row in rows),
                           "status": "SCORED" if len(games) >= 30 else "INSUFFICIENT"}
    return out


def _summary(records: list[dict]) -> dict[str, Any]:
    score = pd.DataFrame([record["scores"] for record in records])
    game_id = pd.Series([record["game_id"] for record in records], name="game_id")
    names = [key[len("candidate_"):] for key in score if key.startswith("candidate_")]
    result: dict[str, Any] = {"n_rows": len(records), "n_game_clusters": int(game_id.nunique()), "metrics": {}}
    generator = np.random.default_rng(297)
    for name in names:
        delta = score["baseline_" + name] - score["candidate_" + name]
        # the point estimate is row-weighted, so the cluster bootstrap must be too (games hold 16-33 rows)
        totals = pd.DataFrame({"game_id": game_id, "delta": delta}).groupby("game_id", sort=True)["delta"].agg(["sum", "count"])
        sums, counts = totals["sum"].to_numpy(), totals["count"].to_numpy()
        draws = generator.integers(0, len(sums), size=(BOOTSTRAPS, len(sums)))
        boot = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
        result["metrics"][name] = {"baseline": float(score["baseline_" + name].mean()),
                                   "candidate": float(score["candidate_" + name].mean()),
                                   "improvement": float(delta.mean()),
                                   "improvement_ci95": [float(np.quantile(boot, .025)), float(np.quantile(boot, .975))]}
    return result


def _write(frame: pd.DataFrame, records: list[dict], inputs: list[dict[str, Any]], before: float, after: float,
           seal: str) -> dict[str, Any]:
    record_by_key = {record["stable_key"]: record for record in records}
    if len(record_by_key) != len(frame) or not all(record["evaluator_output"] for record in records):
        raise AssertionError("archive must derive every row from evaluator records")
    folds = _folds(records)
    kept = [record for record in records if folds[str(record["split_id"])]["status"] == "SCORED"]
    rows, losses = [], []
    for row in frame.itertuples(index=False):
        key, record = "{0}|{1}".format(row.game_id, row.player_id), record_by_key["{0}|{1}".format(row.game_id, row.player_id)]
        forecast = record["forecast"]
        quantiles = {arm: np.quantile(forecast[arm], [.10, .50, .90]) for arm in ("baseline", "candidate")}
        rows.append({"stable_key": key, "game_id": row.game_id, "player_id": row.player_id,
                     "date": str(pd.Timestamp(row.date).date()), "minutes": row.min, "dnp": int(row.min == 0),
                     "split_id": record["split_id"], "fold_status": folds[str(record["split_id"])]["status"],
                     "n_train_asof": forecast["n_train_asof"], "n_player_asof": forecast["n_player_asof"],
                     "asof_max_ts": forecast["asof_max_ts"], "baseline_dnp_probability": forecast["baseline_dnp_prob"],
                     "candidate_dnp_probability": forecast["candidate_dnp_prob"],
                     **{"{0}_q{1}".format(arm, level): float(quantiles[arm][index]) for arm in ("baseline", "candidate")
                        for index, level in enumerate((10, 50, 90))},
                     **{"candidate_positive_q{0}".format(level): float(forecast["candidate_positive_q"][index])
                        for index, level in enumerate((10, 50, 90))}})
        losses.append({"stable_key": key, "game_id": row.game_id, "player_id": row.player_id,
                       "date": str(pd.Timestamp(row.date).date()), "split_id": record["split_id"],
                       "fold_status": folds[str(record["split_id"])]["status"], **record["scores"]})
    pd.DataFrame(rows).to_csv(SCORES, index=False, lineterminator="\n")
    pd.DataFrame(losses).to_csv(LOSSES, index=False, lineterminator="\n")
    FOLDS.write_text(json.dumps(folds, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    summary = _summary(kept)
    summary.update({"gap_id": "S297", "preregistration": PREREG.relative_to(ROOT).as_posix(), "preregistration_seal": seal,
                    "inputs": inputs, "folds": folds, "rss_mb_before": before, "rss_mb_after": after,
                    "artifacts": {path.relative_to(ROOT).as_posix(): path.stat().st_size for path in (SCORES, LOSSES, FOLDS)},
                    "route_sha256": {path.relative_to(ROOT).as_posix(): _sha(path) for path in
                                     (Path(__file__), ROOT / "scripts/platformkit/eval_gate/cpcv_vector_distribution.py",
                                      ROOT / "scripts/platformkit/eval_gate/cpcv_engine.py",
                                      ROOT / "scripts/platformkit/eval_gate/walkforward.py",
                                      ROOT / "scripts/platformkit/eval_gate/state_key_guard.py",
                                      ROOT / "scripts/platformkit/cpcv.py")}})
    primary = summary["metrics"]["minutes_crps"]
    summary["verdict"] = "ACCEPT" if primary["improvement"] > 0 and primary["improvement_ci95"][0] > 0 else "NULL"
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    lines = ["# S297 minutes and DNP distribution (2026-09-04)", "", "## Result", "",
             "SINGLE-WINDOW calibration comparison. Improvement is baseline loss minus candidate loss; positive means candidate better.",
             "The primary unit is minutes CRPS. DNP Brier/log loss and pinball are secondary; the NBA in-game Brier bar does not apply.", "",
             "| Metric | Baseline | Candidate | Improvement | Paired game-cluster 95 pct CI |", "|---|---:|---:|---:|---|"]
    for name, metric in summary["metrics"].items():
        lines.append("| {0} | {1:.6f} | {2:.6f} | {3:.6f} | [{4:.6f}, {5:.6f}] |".format(
            name, metric["baseline"], metric["candidate"], metric["improvement"], *metric["improvement_ci95"]))
    lines += ["", "Verdict: {0}. Primary bar requires positive minutes-CRPS improvement with CI lower above zero.".format(summary["verdict"]),
              "", "## Folds", "", "| Split | Dates | Rows | Held-out games | Status |", "|---|---|---:|---:|---|"]
    for split, fold in folds.items():
        lines.append("| {0} | {1} .. {2} | {3} | {4} | {5} |".format(split, fold["min_date"], fold["max_date"], fold["n_rows"], fold["n_held_out_games"], fold["status"]))
    lines += ["", "## Provenance", "", "- Inputs, bytes, SHA-256, rows, and resolution are in the JSON summary.",
              "- Shared CPCV used one player-game state per tick, purging and a symmetric one-day embargo.",
              "- Scores CSV re-emits game_id/player_id/date, explicit DNP status, probabilities, mixture quantiles, and positive-minute quantiles.",
              "- Paired losses CSV derives only from evaluator records and retains the split/game/player/date keys.",
              "- RSS before/after and every exercised route hash are in the JSON summary.",
              "- Sandbox note: the orchestrator commits these files by explicit pathspec through lane_commit.",
              "", "## NOT VERIFIED", "", "- A second independent corpus or any AHEAD promotion; this is SINGLE-WINDOW only.",
              "- Missing roster records, because absent players have no record and are never made into DNP labels.",
              "- Live, deployment, or forward-operating behavior.",
              "- Whether the fixed pooling weight, sample count, or 70/30 mixture is optimal."]
    MEMO.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return summary


def main() -> None:
    seal, started, before = _seal(), perf_counter(), _rss("before")
    frame, inputs = _load()
    print("S297_PREMISE rows={0} games={1} zeros={2}".format(len(frame), frame.game_id.nunique(), int((frame["min"] == 0).sum())), flush=True)
    records = cpcv_evaluate_vector_distributional(_states(frame), _forecast, _score, n_groups=N_GROUPS,
        n_test_groups=1, embargo_days=EMBARGO_DAYS, strict_redaction=True, allow_keys=("stable_key", "player_id"))
    after, summary = _rss("after"), _write(frame, records, inputs, before, _rss("after_write"), seal)
    print("S297_COMPLETE rows={0} games={1} verdict={2} rss_mb={3:.2f} wall_seconds={4:.2f}".format(
        summary["n_rows"], summary["n_game_clusters"], summary["verdict"], after, perf_counter() - started), flush=True)


if __name__ == "__main__":
    main()
