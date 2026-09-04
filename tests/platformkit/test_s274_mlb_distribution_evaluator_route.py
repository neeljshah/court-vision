"""Focused tests for S274's shared distributional evaluator adapter."""
from __future__ import annotations

import hashlib
import random
from pathlib import Path

from scripts.platformkit import mlb_batter_pitcher_line_dist_cpcv as s274
from scripts.platformkit.mlb_batter_pitcher_line_dist import read_settled_corpus


ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/evidence/harness/S274_mlb_distribution_evaluator_route_prereg_2026-09-04.md"


def test_seeded_fixture_has_exact_distribution_losses():
    rng = random.Random(274)
    samples = [float(rng.randrange(6)) for _ in range(3)]
    outcome = float(rng.randrange(6))
    assert samples == [1.0, 3.0, 2.0]
    assert outcome == 3.0
    losses = s274.distribution_losses(samples, outcome)
    assert losses == {
        "crps": 0.5555555555555556,
        "pinball_q10": 0.2,
        "pinball_q50": 0.5,
        "pinball_q90": 0.0,
    }


def test_prereg_seal_and_real_corpus_structure_only():
    normalized = PREREG.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    marker = b"S274_PREREG_SEAL_SHA256="
    prefix, declared = normalized.split(marker, 1)
    assert hashlib.sha256(prefix).hexdigest() == declared.splitlines()[0].decode("ascii")

    rows = read_settled_corpus(ROOT / s274.CORPUS)
    states, index_by_game = s274.build_states(rows)
    assert len(rows) == len(index_by_game) == 3000
    assert len({row.score_date for row in rows}) == 777
    assert len(states) == 3001
    assert s274.EMBARGO_DAYS == 3
    summary, paired = s274.score(rows)
    assert summary["row_count"] == len(paired) == 3000
    assert summary["cluster_count"] == len({row["cluster_date"] for row in paired}) == 777
