"""A1 and parser tests for the additive S244 naive MLB scorer.

Run: python -m pytest tests/platformkit/test_mlb_batter_pitcher_line_dist.py -q -p no:cacheprovider
"""
from __future__ import annotations

import csv
import json
from math import ceil
from pathlib import Path

import pytest

from scripts.platformkit.mlb_batter_pitcher_line_dist import (
    read_settled_corpus,
    score_naive_clusters,
    summarize,
)


ARCHIVE_ROWS = Path("docs/evidence/harness/S244_attempt_2_naive_row_series_2026-09-04.csv")
ARCHIVE_CLUSTERS = Path("docs/evidence/harness/S244_attempt_2_naive_cluster_losses_2026-09-04.csv")
A1_CLUSTER_DATE = "2024-05-13"


def _independent_crps(samples: list[float], observed: float) -> float:
    left = sum(abs(sample - observed) for sample in samples) / len(samples)
    right = sum(abs(a - b) for a in samples for b in samples) / len(samples) ** 2
    return left - 0.5 * right


def _independent_pinball(samples: list[float], observed: float, quantile: float) -> float:
    ordered = sorted(samples)
    forecast = ordered[max(0, ceil(quantile * len(ordered)) - 1)]
    error = observed - forecast
    return max(quantile * error, (quantile - 1.0) * error)


def _fixture_row(player: str, stamp: str, observed: float, **extra: object) -> dict[str, object]:
    return {"prop_player": player, "ts": stamp, "realized_stat": observed, **extra}


def test_a1_recomputes_archived_cluster_crps_and_q10_pinball():
    with ARCHIVE_ROWS.open(newline="", encoding="utf-8") as handle:
        scored = [row for row in csv.DictReader(handle) if row["cluster_date"] == A1_CLUSTER_DATE]
    with ARCHIVE_CLUSTERS.open(newline="", encoding="utf-8") as handle:
        cluster = next(row for row in csv.DictReader(handle) if row["cluster_date"] == A1_CLUSTER_DATE)
    crps = []
    pinball_q10 = []
    for row in scored:
        samples = [float(value) for value in json.loads(row["forecast_samples_json"])]
        observed = float(row["observed"])
        crps.append(_independent_crps(samples, observed))
        pinball_q10.append(_independent_pinball(samples, observed, 0.10))
    assert len(scored) == int(cluster["n_rows"])
    assert sum(crps) / len(crps) == pytest.approx(float(cluster["naive_crps"]), abs=1e-12)
    assert sum(pinball_q10) / len(pinball_q10) == pytest.approx(
        float(cluster["naive_pinball_q10"]), abs=1e-12)


def test_mixed_prices_parse_and_naive_path_does_not_need_market_column(tmp_path: Path):
    mixed = tmp_path / "mixed.jsonl"
    mixed.write_text("\n".join(json.dumps(row) for row in [
        _fixture_row("p1", "2024-01-01T00:00:00", 1.0, market_prob=None),
        _fixture_row("p1", "2024-01-05T00:00:00", 2.0, market_prob=0.55),
    ]) + "\n", encoding="utf-8")
    parsed_mixed = read_settled_corpus(mixed)
    assert [row.market_prob for row in parsed_mixed] == [None, 0.55]

    no_market = tmp_path / "no_market.jsonl"
    no_market.write_text("\n".join(json.dumps(row) for row in [
        _fixture_row("p2", "2024-01-01T00:00:00", 1.0),
        _fixture_row("p2", "2024-01-05T00:00:00", 2.0),
    ]) + "\n", encoding="utf-8")
    parsed_no_market = read_settled_corpus(no_market)
    _, clusters = score_naive_clusters(parsed_no_market)
    assert summarize(parsed_no_market, clusters)["non_null_market_prob"] == 0
    assert sum(int(cluster["n_rows"]) for cluster in clusters) == 2
