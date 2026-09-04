"""S280 NBA cross-venue in-game calibration comparison."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pyarrow.dataset as ds
import pyarrow.parquet as pq
from sklearn.linear_model import LogisticRegression

from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate

ROOT = Path(__file__).resolve().parents[3]
PRICE_PATH = ROOT / "data/cache/inplay_odds/nba_price_series.parquet"
CHECKPOINT_PATH = ROOT / "data/cache/inplay_odds/nba_checkpoints_full.parquet"
BAR = 0.004
KALSHI_RE = re.compile(r"^KXNBA(?:GAME|SPREAD)-([0-9]{2}[A-Z]{3}[0-9]{2})([A-Z]{6})-")
POLY_RE = re.compile(r"^nba-([a-z]{3})-([a-z]{3})-([0-9]{4}-[0-9]{2}-[0-9]{2})$")


def parse_kalshi_id(ticker: str) -> tuple[str, str, str] | None:
    """Parse a Kalshi NBA ticker into ticker-date, away, and home."""
    match = KALSHI_RE.match(ticker)
    if match is None:
        return None
    game_date = datetime.strptime(match.group(1), "%y%b%d").date().isoformat()
    teams = match.group(2)
    return game_date, teams[:3], teams[3:]


def parse_polymarket_id(ticker: str) -> tuple[str, str, str] | None:
    """Parse a Polymarket NBA ticker into date, away, and home."""
    match = POLY_RE.match(ticker)
    if match is None:
        return None
    return match.group(3), match.group(1).upper(), match.group(2).upper()


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()


def _input_meta(path: Path) -> dict:
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
            "resolution": "parquet", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def load_overlap() -> tuple[list[dict], dict, list[dict]]:
    """Load every comparable tick from the two named stores, one store at a time."""
    price_file = ds.dataset(PRICE_PATH, format="parquet")
    events: dict[str, dict] = {}
    for batch in price_file.scanner(filter=ds.field("venue") == "kalshi",
                                    columns=["event_key", "ticker_or_slug", "market_type"]).to_batches():
        for row in batch.to_pylist():
            events.setdefault(str(row["event_key"]), row)
    parsed = {key: parse_kalshi_id(str(row["ticker_or_slug"])) for key, row in events.items()}
    games: dict[tuple[str, str, str], int] = {}
    game_teams: dict[int, tuple[str, str]] = {}
    checkpoint_file = pq.ParquetFile(CHECKPOINT_PATH)
    for batch in checkpoint_file.iter_batches(columns=["game_id", "market_ticker"]):
        for row in batch.to_pylist():
            triple = parse_polymarket_id(str(row["market_ticker"]))
            if triple is not None:
                games.setdefault(triple, int(row["game_id"]))
                game_teams[int(row["game_id"])] = (triple[1], triple[2])
    exact = {key for key, triple in parsed.items() if triple in games}
    comparable = {key for key in exact if events[key]["market_type"] == "moneyline"}
    prices: dict[str, list[tuple[int, float]]] = {}
    for batch in price_file.scanner(filter=ds.field("venue") == "kalshi",
                                    columns=["event_key", "side", "ts", "prob"]).to_batches():
        for row in batch.to_pylist():
            key = str(row["event_key"])
            if key in comparable and str(row["side"]) == parsed[key][2] and row["prob"] is not None:
                prices.setdefault(key, []).append((int(row["ts"]), float(row["prob"])))
    for values in prices.values():
        values.sort()
    price_stamps = {key: np.array([value[0] for value in values]) for key, values in prices.items()}
    event_by_game = {games[parsed[key]]: key for key in comparable if key in prices}
    states, missing_asof = [], 0
    for batch in checkpoint_file.iter_batches(
            columns=["game_id", "ts", "market_prob", "outcome_home_win"]):
        for row in batch.to_pylist():
            game_id = int(row["game_id"])
            key = event_by_game.get(game_id)
            if key is None or row["market_prob"] is None:
                continue
            stamp = int(row["ts"])
            index = np.searchsorted(price_stamps[key], stamp, side="right") - 1
            if index < 0:
                missing_asof += 1
                continue
            price_ts, home_prob = prices[key][index]
            state_stamp = datetime.fromtimestamp(stamp, tz=timezone.utc) + timedelta(microseconds=1)
            away, home = game_teams[game_id]
            states.append({
                "game_id": str(game_id), "state_ts": state_stamp.isoformat(), "home": home, "away": away,
                "outcome": int(row["outcome_home_win"]), "devig_close_prob": float(row["market_prob"]),
                "features": {"market_logit": _logit(float(row["market_prob"])),
                             "venue_disagreement": home_prob - float(row["market_prob"])},
                "feature_avail": {"market_logit": _iso(stamp), "venue_disagreement": _iso(price_ts)},
            })
    summary = {"kalshi_events_parsed": sum(value is not None for value in parsed.values()),
               "kalshi_events_total": len(events), "parsed_exact_overlap": len(exact),
               "exact_overlap_by_market_type": dict(Counter(events[key]["market_type"] for key in exact)),
               "scored_moneyline_games": len(event_by_game), "missing_asof_ticks": missing_asof,
               "checkpoint_ticks_with_asof_kalshi": len(states)}
    overlap_rows = []
    for key in sorted(events):
        triple = parsed[key]
        overlap_rows.append({"event_key": key, "ticker_or_slug": events[key]["ticker_or_slug"],
                             "market_type": events[key]["market_type"], "parsed_date": triple[0] if triple else "",
                             "away": triple[1] if triple else "", "home": triple[2] if triple else "",
                             "exact_checkpoint_overlap": key in exact,
                             "comparable_moneyline": key in comparable,
                             "checkpoint_game_id": games.get(triple, "") if triple else ""})
    return states, summary, overlap_rows


def _logit(value: float) -> float:
    clipped = min(max(value, 1e-6), 1.0 - 1e-6)
    return float(np.log(clipped / (1.0 - clipped)))


def _predictor(include_disagreement: bool):
    cache: dict[int, LogisticRegression | float] = {}

    def predict(train: list[dict], test: dict, _inside: bool) -> float:
        key = id(train)
        model = cache.get(key)
        if model is None:
            x = np.array([[s["features"]["market_logit"], s["features"]["venue_disagreement"]]
                          for s in train], dtype=float)
            x = x[:, :2] if include_disagreement else x[:, :1]
            y = np.array([s["outcome"] for s in train], dtype=int)
            model = float(y.mean()) if len(y) == 0 or len(np.unique(y)) < 2 else LogisticRegression(
                C=1e6, solver="lbfgs", max_iter=1000).fit(x, y)
            cache[key] = model
        if isinstance(model, float):
            return model
        point = np.array([[test["features"]["market_logit"], test["features"]["venue_disagreement"]]])
        return float(model.predict_proba(point[:, :2] if include_disagreement else point[:, :1])[0, 1])

    return predict


def _paired_records(states: list[dict]) -> list[dict]:
    kwargs = {"n_groups": 8, "n_test_groups": 2, "embargo_days": 1, "strict_redaction": True}
    null = cpcv_evaluate(states, _predictor(False), **kwargs)
    augmented = cpcv_evaluate(states, _predictor(True), **kwargs)
    lookup = {(state["game_id"], state["state_ts"]): state for state in states}
    joined = {(r["split_id"], r["game_id"], r["ts"]): r for r in null}
    result = []
    for row in augmented:
        base = joined[(row["split_id"], row["game_id"], row["ts"])]
        source = lookup[(row["game_id"], row["ts"])]
        checkpoint_ts = int(datetime.fromisoformat(row["ts"]).timestamp())
        kalshi_ts = int(datetime.fromisoformat(source["feature_avail"]["venue_disagreement"]).timestamp())
        result.append({"split_id": row["split_id"], "game_id": row["game_id"], "state_ts": row["ts"],
                       "checkpoint_ts": checkpoint_ts, "kalshi_ts": kalshi_ts,
                       "outcome": row["y"], "p_recal_null": base["p_model"],
                       "p_augmented": row["p_model"]})
    return result


def _summarize(records: list[dict]) -> tuple[list[dict], dict]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in records:
        grouped.setdefault((row["game_id"], row["state_ts"]), []).append(row)
    ticks = []
    for rows in grouped.values():
        first = rows[0]
        p_null = float(np.mean([row["p_recal_null"] for row in rows]))
        p_aug = float(np.mean([row["p_augmented"] for row in rows]))
        loss_null, loss_aug = (p_null - first["outcome"]) ** 2, (p_aug - first["outcome"]) ** 2
        ticks.append({**first, "n_evaluator_records": len(rows), "p_recal_null": p_null,
                      "p_augmented": p_aug, "loss_recal_null": loss_null, "loss_augmented": loss_aug,
                      "metric_augmented_minus_null": loss_aug - loss_null})
    per_game: dict[str, list[float]] = {}
    for row in ticks:
        per_game.setdefault(row["game_id"], []).append(row["metric_augmented_minus_null"])
    means = np.array([np.mean(values) for values in per_game.values()])
    rng, boots = np.random.default_rng(280), []
    for _ in range(10000):
        boots.append(float(rng.choice(means, size=len(means), replace=True).mean()))
    metric = float(np.mean([row["metric_augmented_minus_null"] for row in ticks]))
    result = {"metric_augmented_brier_minus_recal_null_brier": metric,
              "recal_null_brier": float(np.mean([row["loss_recal_null"] for row in ticks])),
              "augmented_brier": float(np.mean([row["loss_augmented"] for row in ticks])),
              "game_clustered_ci95": [float(np.quantile(boots, .025)), float(np.quantile(boots, .975))],
              "n_ticks": len(ticks), "n_game_clusters": len(per_game),
              "improvement_vs_null": -metric, "bar": BAR}
    return ticks, result


def run(output_dir: Path) -> dict:
    """Run the sealed S280 scorer and archive its evaluator-derived differential."""
    states, premise, overlap_rows = load_overlap()
    if premise["scored_moneyline_games"] < 30:
        raise RuntimeError("CLOSED AT LIMIT: %d comparable game clusters" % premise["scored_moneyline_games"])
    records = _paired_records(states)
    ticks, summary = _summarize(records)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "S280_ingame_cross_venue_disagreement_2026-09-04_ticks.csv"
    with csv_path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ticks[0]))
        writer.writeheader(); writer.writerows(ticks)
    overlap_path = output_dir / "S280_ingame_cross_venue_disagreement_2026-09-04_overlap.csv"
    with overlap_path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(overlap_rows[0]))
        writer.writeheader(); writer.writerows(overlap_rows)
    payload = {"spec": "S280", "inputs": [_input_meta(PRICE_PATH), _input_meta(CHECKPOINT_PATH)],
               "premise": premise, "summary": summary, "evaluator_records": len(records),
               "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (output_dir / "S280_ingame_cross_venue_disagreement_2026-09-04.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="ascii", newline="\n")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    payload = run(args.output_dir)
    print(json.dumps(payload["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
