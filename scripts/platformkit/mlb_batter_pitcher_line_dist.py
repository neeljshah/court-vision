"""Naive as-of MLB player-line distribution scoring for S244 attempt 2."""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil, isfinite
from pathlib import Path
from typing import Iterable


DEFAULT_CORPUS = Path("data/frontend/prop_history_corpus_mlb.jsonl")
DEFAULT_ROW_SERIES = Path("docs/evidence/harness/S244_attempt_2_naive_row_series_2026-09-04.csv")
DEFAULT_CLUSTER_SERIES = Path("docs/evidence/harness/S244_attempt_2_naive_cluster_losses_2026-09-04.csv")
QUANTILES = (0.10, 0.50, 0.90)


@dataclass(frozen=True)
class CorpusRow:
    """One required settled corpus record with a parsed score date."""

    row_index: int
    player: str
    score_date: date
    observed: float
    market_prob: object


def read_settled_corpus(path: Path) -> list[CorpusRow]:
    """Parse every JSONL record or fail instead of silently excluding a row."""
    rows: list[CorpusRow] = []
    with path.open("r", encoding="utf-8") as handle:
        for row_index, line in enumerate(handle, start=1):
            try:
                raw = json.loads(line)
                observed = float(raw["realized_stat"])
                if not isfinite(observed):
                    raise ValueError("non-finite realized_stat")
                rows.append(CorpusRow(
                    row_index=row_index,
                    player=str(raw["prop_player"]),
                    score_date=date.fromisoformat(str(raw["ts"])[:10]),
                    observed=observed,
                    market_prob=raw.get("market_prob"),
                ))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError("Unparseable corpus row {0}".format(row_index)) from exc
    if not rows:
        raise ValueError("Corpus is empty")
    return rows


def empirical_crps(samples: Iterable[float], observed: float) -> float:
    """Return empirical-distribution CRPS via its finite energy form."""
    values = [float(value) for value in samples]
    if not values:
        raise ValueError("CRPS needs at least one forecast sample")
    observation_term = sum(abs(value - observed) for value in values) / len(values)
    pairwise = sum(abs(left - right) for left in values for right in values)
    return observation_term - 0.5 * pairwise / (len(values) * len(values))


def lower_nearest_rank(samples: Iterable[float], quantile: float) -> float:
    """Return the preregistered lower nearest-rank empirical quantile."""
    values = sorted(float(value) for value in samples)
    if not values or not 0.0 < quantile < 1.0:
        raise ValueError("Quantile needs samples and q strictly between zero and one")
    return values[max(0, ceil(quantile * len(values)) - 1)]


def pinball(observed: float, forecast_quantile: float, quantile: float) -> float:
    """Return quantile pinball loss for one observed value and forecast."""
    error = observed - forecast_quantile
    return max(quantile * error, (quantile - 1.0) * error)


def _history_rows(rows: Iterable[CorpusRow]) -> list[CorpusRow]:
    """Retain every prior settled row, including distinct same-date games."""
    return sorted(rows, key=lambda row: (row.score_date, row.player, row.row_index))


def naive_callback(train_rows: Iterable[CorpusRow], scored_row: CorpusRow) -> tuple[list[float], bool]:
    """Produce every as-of forecast sample for one scored row.

    The fixed cold-start point mass is explicit rather than an unnamed skipped
    row.  All supplied training records must already satisfy the fold embargo.
    """
    samples = [row.observed for row in train_rows if row.player == scored_row.player]
    return (samples, False) if samples else ([0.0], True)


def score_naive_clusters(rows: list[CorpusRow], embargo_days: int = 3) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Score all date clusters with a past-only symmetric-embargo assertion."""
    if embargo_days <= 0:
        raise ValueError("embargo_days must be nonzero")
    by_date: dict[date, list[CorpusRow]] = defaultdict(list)
    for row in rows:
        by_date[row.score_date].append(row)
    history = _history_rows(rows)
    row_series: list[dict[str, object]] = []
    cluster_series: list[dict[str, object]] = []
    for score_date in sorted(by_date):
        scored = by_date[score_date]
        cutoff = score_date - timedelta(days=embargo_days + 1)
        train = [row for row in history if row.score_date <= cutoff]
        assert all(abs((train_row.score_date - test_row.score_date).days) > embargo_days
                   for train_row in train for test_row in scored), "symmetric embargo violation"
        cluster_losses = {"naive_crps": [], "naive_pinball_q10": [],
                          "naive_pinball_q50": [], "naive_pinball_q90": []}
        cold_starts = 0
        for scored_row in scored:
            samples, cold_start = naive_callback(train, scored_row)
            quantile_values = {q: lower_nearest_rank(samples, q) for q in QUANTILES}
            losses = {
                "naive_crps": empirical_crps(samples, scored_row.observed),
                "naive_pinball_q10": pinball(scored_row.observed, quantile_values[0.10], 0.10),
                "naive_pinball_q50": pinball(scored_row.observed, quantile_values[0.50], 0.50),
                "naive_pinball_q90": pinball(scored_row.observed, quantile_values[0.90], 0.90),
            }
            cold_starts += int(cold_start)
            for name, loss in losses.items():
                cluster_losses[name].append(loss)
            row_series.append({
                "cluster_date": score_date.isoformat(), "row_index": scored_row.row_index,
                "prop_player": scored_row.player, "observed": scored_row.observed,
                "forecast_samples_json": json.dumps(samples, separators=(",", ":")),
                "n_train_player": len(samples) if not cold_start else 0,
                "cold_start": int(cold_start), **losses,
            })
        cluster_series.append({
            "cluster_date": score_date.isoformat(), "n_rows": len(scored),
            "cold_start_rows": cold_starts,
            **{name: sum(values) / len(values) for name, values in cluster_losses.items()},
        })
    return row_series, cluster_series


def write_csv(rows: list[dict[str, object]], path: Path) -> None:
    """Write the complete additive evidence series with a stable header."""
    if not rows:
        raise ValueError("Cannot archive an empty evidence series")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: list[CorpusRow], clusters: list[dict[str, object]]) -> dict[str, int | float]:
    """Return fixed-corpus counts and macro cluster losses for the memo."""
    summary: dict[str, int | float] = {
        "total_rows": len(rows), "distinct_players": len({row.player for row in rows}),
        "non_null_market_prob": sum(row.market_prob is not None for row in rows),
        "cluster_count": len(clusters), "row_denominator": sum(int(row["n_rows"]) for row in clusters),
        "cold_start_rows": sum(int(row["cold_start_rows"]) for row in clusters),
    }
    for name in ("naive_crps", "naive_pinball_q10", "naive_pinball_q50", "naive_pinball_q90"):
        summary[name] = sum(float(row[name]) for row in clusters) / len(clusters)
    return summary


def main() -> None:
    """Parse, score, archive, and print the fixed naive-only S244 summary."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--row-series", type=Path, default=DEFAULT_ROW_SERIES)
    parser.add_argument("--cluster-series", type=Path, default=DEFAULT_CLUSTER_SERIES)
    args = parser.parse_args()
    rows = read_settled_corpus(args.corpus)
    row_series, cluster_series = score_naive_clusters(rows)
    write_csv(row_series, args.row_series)
    write_csv(cluster_series, args.cluster_series)
    for name, value in summarize(rows, cluster_series).items():
        print("{0}={1}".format(name.upper(), value))


if __name__ == "__main__":
    main()
