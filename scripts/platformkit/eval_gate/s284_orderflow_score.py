"""S284 sealed Kalshi trade-occurrence calibration comparison."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import pyarrow.parquet as pq
from sklearn.linear_model import LogisticRegression

from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.eval_gate.s284_orderflow_traded import (
    CHECKPOINT_PATH, PRICE_PATH, ROOT, parse_checkpoint_ticker, parse_kalshi_event_key,
)
from scripts.platformkit.foundry.ingame_incumbent_nba import apply_incumbent

TOLERANCE_SECONDS = 60
BAR = 0.004


def _iso(stamp: int) -> str:
    return datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat()


def _file_meta(path: Path) -> dict:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
            "resolution": "parquet", "sha256": digest.hexdigest()}


def _event_triples() -> dict[str, tuple[str, str, str]]:
    """Read only native Kalshi event identifiers from the price store."""
    keys: set[str] = set()
    source = ds.dataset(PRICE_PATH, format="parquet")
    for batch in source.scanner(filter=ds.field("venue") == "kalshi",
                                columns=["event_key"]).to_batches():
        keys.update(str(value) for value in batch.column(0).to_pylist() if value is not None)
    return {key: parsed for key in keys if (parsed := parse_kalshi_event_key(key)) is not None}


def _checkpoint_rows(events: dict[str, tuple[str, str, str]]) -> tuple[dict[str, str], list[dict]]:
    """Read frozen checkpoints after the price-id scan and retain exact away-home games."""
    event_for_triple = {triple: key for key, triple in events.items()}
    game_event: dict[str, str] = {}
    rows: list[dict] = []
    source = pq.ParquetFile(CHECKPOINT_PATH)
    columns = ["game_id", "game_date", "ts", "market_prob", "margin", "game_clock_s",
               "outcome_home_win", "market_ticker"]
    for batch in source.iter_batches(columns=columns):
        for row in batch.to_pylist():
            triple = parse_checkpoint_ticker(str(row["market_ticker"]))
            event_key = event_for_triple.get(triple)
            if event_key is None or row["market_prob"] is None:
                continue
            game_id = str(row["game_id"])
            known = game_event.setdefault(game_id, event_key)
            assert known == event_key, "game matched multiple native Kalshi events"
            rows.append({"game": game_id, "game_date": str(row["game_date"]),
                         "checkpoint_ts": int(row["ts"]), "market": float(row["market_prob"]),
                         "margin": float(row["margin"]), "game_clock_s": float(row["game_clock_s"]),
                         "y": int(row["outcome_home_win"]), "event_key": event_key,
                         "away": triple[1], "home": triple[2]})
    return game_event, rows


def _event_ticks(event_keys: set[str]) -> dict[str, list[tuple[int, bool]]]:
    """Read native event ticks after checkpoints; side rows remain separate trade observations."""
    ticks: dict[str, list[tuple[int, bool]]] = defaultdict(list)
    source = ds.dataset(PRICE_PATH, format="parquet")
    for batch in source.scanner(filter=ds.field("venue") == "kalshi",
                                columns=["event_key", "ts", "traded"]).to_batches():
        for row in batch.to_pylist():
            key = str(row["event_key"])
            if key in event_keys and row["ts"] is not None:
                ticks[key].append((int(row["ts"]), bool(row["traded"])))
    for values in ticks.values():
        values.sort()
    return ticks


def _join_strictly_prior(checkpoints: list[dict], ticks: dict[str, list[tuple[int, bool]]]) -> list[dict]:
    """Attach the latest strictly-prior event flag and true-tick count in the fixed 60-second window."""
    grouped: dict[str, tuple[list[int], list[bool], list[int]]] = {}
    for key, values in ticks.items():
        stamps, latest_flag, true_per_stamp = [], [], []
        for stamp, flag in values:
            if stamps and stamps[-1] == stamp:
                latest_flag[-1] = latest_flag[-1] or flag
                true_per_stamp[-1] += int(flag)
            else:
                stamps.append(stamp)
                latest_flag.append(flag)
                true_per_stamp.append(int(flag))
        prefix = [0]
        for count in true_per_stamp:
            prefix.append(prefix[-1] + count)
        grouped[key] = stamps, latest_flag, prefix
    joined = []
    for row in checkpoints:
        stamps, flags, prefix = grouped.get(row["event_key"], ([], [], [0]))
        index = bisect_left(stamps, row["checkpoint_ts"]) - 1
        if index < 0 or row["checkpoint_ts"] - stamps[index] > TOLERANCE_SECONDS:
            continue
        lower = bisect_left(stamps, row["checkpoint_ts"] - TOLERANCE_SECONDS + 1)
        true_count = prefix[index + 1] - prefix[lower]
        joined.append({**row, "kalshi_asof_ts": stamps[index], "traded_any": int(flags[index]),
                       "trade_count_60s": int(true_count)})
    return joined


def _logit(value: float) -> float:
    clipped = min(max(value, 1e-6), 1.0 - 1e-6)
    return float(np.log(clipped / (1.0 - clipped)))


def _states(joined: list[dict]) -> tuple[list[dict], dict]:
    frame = pd.DataFrame(joined)
    frame["ts"] = frame["checkpoint_ts"].map(_iso)
    anchored = apply_incumbent(frame, "recal_null")
    states, metadata = [], {}
    for row in anchored.to_dict("records"):
        state_stamp = datetime.fromtimestamp(row["checkpoint_ts"], tz=timezone.utc) + timedelta(microseconds=1)
        stamp = state_stamp.isoformat()
        state = {"game_id": row["game"], "state_ts": stamp, "home": row["home"], "away": row["away"],
                 "outcome": int(row["y"]), "devig_close_prob": float(row["market"]),
                 "features": {"incumbent": float(row["p_e4"]), "traded_any": int(row["traded_any"]),
                              "trade_count_60s": int(row["trade_count_60s"])},
                 "feature_avail": {"incumbent": _iso(int(row["checkpoint_ts"])),
                                   "traded_any": _iso(int(row["kalshi_asof_ts"])),
                                   "trade_count_60s": _iso(int(row["kalshi_asof_ts"]))}}
        states.append(state)
        metadata[(state["game_id"], stamp)] = {"kalshi_asof_ts": int(row["kalshi_asof_ts"]),
                                                  "traded_any": int(row["traded_any"]),
                                                  "trade_count_60s": int(row["trade_count_60s"])}
    return states, metadata


def _predictor(candidate: bool):
    cache: dict[int, LogisticRegression | float] = {}

    def predict(train: list[dict], test: dict, _inside: bool) -> float:
        if not candidate:
            return float(test["features"]["incumbent"])
        key = id(train)
        model = cache.get(key)
        if model is None:
            x = np.array([[_logit(s["features"]["incumbent"]), s["features"]["traded_any"],
                           s["features"]["trade_count_60s"]] for s in train], dtype=float)
            y = np.array([s["outcome"] for s in train], dtype=int)
            model = float(y.mean()) if len(np.unique(y)) < 2 else LogisticRegression(
                C=1e6, solver="lbfgs", max_iter=1000).fit(x, y)
            cache[key] = model
        if isinstance(model, float):
            return model
        point = [[_logit(test["features"]["incumbent"]), test["features"]["traded_any"],
                  test["features"]["trade_count_60s"]]]
        return float(model.predict_proba(point)[0, 1])

    return predict


def _archive(base_records: list[dict], candidate_records: list[dict], metadata: dict) -> tuple[list[dict], dict]:
    base = {(r["split_id"], r["game_id"], r["ts"]): r for r in base_records}
    candidate = {(r["split_id"], r["game_id"], r["ts"]): r for r in candidate_records}
    assert base.keys() == candidate.keys(), "evaluator arms differ"
    by_state: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for key, candidate_row in candidate.items():
        base_row = base[key]
        assert base_row["y"] == candidate_row["y"], "evaluator outcomes differ"
        by_state[(key[1], key[2])].append({"p_recal_null": base_row["p_model"],
                                             "p_candidate": candidate_row["p_model"],
                                             "y": candidate_row["y"]})
    archived, game_improvements = [], defaultdict(list)
    for (game_id, stamp), records in sorted(by_state.items()):
        p_base = float(np.mean([r["p_recal_null"] for r in records]))
        p_candidate = float(np.mean([r["p_candidate"] for r in records]))
        outcome = int(records[0]["y"])
        loss_base, loss_candidate = (p_base - outcome) ** 2, (p_candidate - outcome) ** 2
        extra = metadata[(game_id, stamp)]
        archived.append({"game_id": game_id, "state_ts": stamp, "kalshi_asof_ts": _iso(extra["kalshi_asof_ts"]),
                         "traded_any": extra["traded_any"], "trade_count_60s": extra["trade_count_60s"],
                         "outcome": outcome, "n_evaluator_records": len(records), "p_recal_null": p_base,
                         "p_candidate": p_candidate, "loss_recal_null": loss_base,
                         "loss_candidate": loss_candidate, "improvement": loss_base - loss_candidate})
        game_improvements[game_id].append(loss_base - loss_candidate)
    values = np.array([np.mean(rows) for rows in game_improvements.values()], dtype=float)
    rng = np.random.default_rng(284)
    bootstrap = np.array([rng.choice(values, size=len(values), replace=True).mean() for _ in range(10000)])
    return archived, {"recal_null_brier": float(np.mean([r["loss_recal_null"] for r in archived])),
                      "candidate_brier": float(np.mean([r["loss_candidate"] for r in archived])),
                      "improvement": float(np.mean([r["improvement"] for r in archived])),
                      "game_clustered_ci95": [float(np.quantile(bootstrap, .025)), float(np.quantile(bootstrap, .975))],
                      "n_states": len(archived), "n_game_clusters": len(game_improvements), "bar": BAR}


def run(output_dir: Path) -> dict:
    """Run the preregistered comparison and write evaluator-derived archives."""
    events = _event_triples()
    game_event, checkpoints = _checkpoint_rows(events)
    joined = _join_strictly_prior(checkpoints, _event_ticks(set(game_event.values())))
    if len(set(row["game"] for row in joined)) < 30:
        raise RuntimeError("CLOSED AT LIMIT: fewer than 30 joined game clusters")
    states, metadata = _states(joined)
    if len(set(state["game_id"] for state in states)) < 30:
        raise RuntimeError("CLOSED AT LIMIT: fewer than 30 recal_null OOF game clusters")
    kwargs = {"n_groups": 8, "n_test_groups": 2, "embargo_days": 1, "strict_redaction": True}
    base_records = cpcv_evaluate(states, _predictor(False), **kwargs)
    candidate_records = cpcv_evaluate(states, _predictor(True), **kwargs)
    archived, summary = _archive(base_records, candidate_records, metadata)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "S284_orderflow_traded_2026-09-04_ticks.csv"
    with csv_path.open("w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(archived[0]))
        writer.writeheader(); writer.writerows(archived)
    payload = {"spec": "S284", "inputs": [_file_meta(PRICE_PATH), _file_meta(CHECKPOINT_PATH)],
               "join": {"ordering": "away_home", "strictly_prior": True,
                        "tolerance_seconds": TOLERANCE_SECONDS, "matched_game_clusters": len(game_event),
                        "joined_checkpoint_ticks": len(joined), "joined_game_clusters": len(set(r["game"] for r in joined)),
                        "recal_null_oof_game_clusters": summary["n_game_clusters"]},
               "summary": summary, "evaluator_records": {"recal_null": len(base_records),
                                                             "candidate": len(candidate_records)},
               "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (output_dir / "S284_orderflow_traded_2026-09-04.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="ascii", newline="\n")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="S284 sealed orderflow scorer")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    payload = run(args.output_dir)
    print(json.dumps(payload["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
