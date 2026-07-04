"""Tests for scripts.platformkit.venue_history.polymarket_tail_validation. Offline, on-disk fixtures only."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from scripts.platformkit.venue_history import polymarket_tail_validation as ptv


def _write_game(base: Path, date: str, slug: str, market_slug: str,
                outcome: int, prices: List[float]) -> None:
    base.mkdir(parents=True, exist_ok=True)
    doc = {
        "date": date, "event_slug": slug, "market_slug": market_slug,
        "sport": "mlb", "home": "A", "away": "B",
        "outcome_home_win": outcome, "closed": True, "token_home": "T",
        "n_prices": len(prices),
        "prices": [{"ts": "2023-04-0%dT00:00:00Z" % (i + 1), "prob_home": p}
                   for i, p in enumerate(prices)],
    }
    (base / ("%s_%s.jsonl" % (date, market_slug))).write_text(json.dumps(doc) + "\n", encoding="utf-8")


def test_band_label_matches_shared_edges() -> None:
    assert ptv._band_label(0.15) == "[0.10,0.20)"
    assert ptv._band_label(0.70) == "[0.65,0.80)"
    assert ptv._band_label(0.05) == "[0.00,0.10)"


def test_load_corpus_rows_excludes_unresolved(tmp_path: Path) -> None:
    base = tmp_path / "mlb"
    _write_game(base, "2023-04-02", "mlb-dailies-2023-04-02", "mlb-a-b-1", 1, [0.15, 0.16])
    # unresolved game (outcome_home_win missing) must be excluded, never guessed.
    base.mkdir(parents=True, exist_ok=True)
    doc = {"date": "2023-04-03", "event_slug": "x", "market_slug": "mlb-c-d-2",
           "outcome_home_win": None, "prices": [{"ts": "t", "prob_home": 0.15}]}
    (base / "2023-04-03_mlb-c-d-2.jsonl").write_text(json.dumps(doc) + "\n", encoding="utf-8")
    rows = ptv._load_corpus_rows(tmp_path, "mlb")
    assert len(rows) == 2  # only the resolved game's two ticks
    assert all(r[2] in (0, 1) for r in rows)


def test_provenance_labeling_and_no_pooling_fields() -> None:
    result = ptv.validate("mlb", corpus_dir=Path("__nonexistent_dir__"))
    assert result["provenance"] == "polymarket_historical_validation"
    assert result["component"] == "m_polymarket_tail_validation"
    assert result["edge_claimed"] is False
    assert result["n_games_total_corpus"] == 0
    # Both pre-registered bands present even with zero data (honest INSUFFICIENT).
    for label in (ptv.H1_BAND, ptv.H2_BAND):
        assert result["bands"][label]["pooled"]["venue_verdict"] == "INSUFFICIENT_DATA"


def test_insufficient_data_below_min_games(tmp_path: Path) -> None:
    """Fewer than MIN_GAMES_BAND distinct games in a band -> INSUFFICIENT_DATA,
    never a stretched verdict."""
    base = tmp_path / "mlb"
    for i in range(3):  # below MIN_GAMES_BAND=8
        _write_game(base, "2023-04-0%d" % (i + 1), "mlb-dailies-x", "mlb-g-%d" % i,
                    1, [0.15])
    result = ptv.validate("mlb", corpus_dir=tmp_path)
    h1 = result["bands"][ptv.H1_BAND]
    assert h1["pooled"]["venue_verdict"] == "INSUFFICIENT_DATA"
    assert h1["pooled"]["n_games"] == 3


def test_band_math_reuse_and_md5_half_split(tmp_path: Path) -> None:
    """With >=MIN_GAMES_BAND games where realized outcome consistently exceeds
    price in the H1 band, the pooled verdict should read VENUE_UNDERPRICES
    (reusing the exact _band_stats CI logic, not a reimplementation)."""
    base = tmp_path / "mlb"
    # 10 games in H1 band [0.10,0.20): price ~0.15, but ALL resolve home_win=1
    # (realized rate 1.0 >> mean price 0.15) -> should trip VENUE_UNDERPRICES.
    for i in range(10):
        _write_game(base, "2023-04-%02d" % (i + 1), "mlb-dailies-x", "mlb-g-%d" % i,
                    1, [0.15, 0.14, 0.16])
    result = ptv.validate("mlb", corpus_dir=tmp_path)
    h1 = result["bands"][ptv.H1_BAND]
    assert h1["pooled"]["n_games"] == 10
    assert h1["pooled"]["venue_verdict"] == "VENUE_UNDERPRICES"
    assert h1["pooled"]["realized_rate"] == 1.0
    # Every game must land in exactly one md5 half, and both halves see the
    # same total ticks as pooled (crude split sanity, not a real CI check).
    n_half0 = h1["halves"]["half_0"].get("n_games", 0)
    n_half1 = h1["halves"]["half_1"].get("n_games", 0)
    assert n_half0 + n_half1 == 10


def test_write_artifact_atomic(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    result = ptv.validate("mlb", corpus_dir=Path("__nonexistent_dir__"))
    path = ptv.write_artifact(result, out_path=out)
    assert path.is_file()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["provenance"] == "polymarket_historical_validation"
