"""Per-file tests for ingame_unk_backfill_verdict (offline; injected fixtures)."""
from __future__ import annotations

import json

from scripts.platformkit.ingame import ingame_unk_backfill_verdict as m
from scripts.platformkit.ingame import ingame_outcome_verdict as _ov


def _rows(ticker, ticks):
    """ticks: list of (ts, model_prob, market_prob)."""
    return [{"ts": ts, "model_prob": mp, "market_prob": kp, "state_summary": "live"}
            for ts, mp, kp in ticks]


def _make_games(n_games=10, n_ticks_per_game=30):
    """Enough games/ticks per segment to clear _ov's default MIN_GAMES/MIN_TICKS
    floors so verdicts are real, not INSUFFICIENT_DATA."""
    games = {}
    for i in range(n_games):
        ticker = "KXWCGAME-26JUN2%dAAABBB" % (i % 8)
        ticks = []
        for j in range(n_ticks_per_game):
            ts = "2026-06-2%dT17:%02d:00Z" % (i % 8, j % 60)
            mp = 0.5 + (0.01 * (j % 5))
            kp = 0.5
            ticks.append((ts, mp, kp))
        games[ticker] = _rows(ticker, ticks)
    return games


def _outcome_fn(_ticker):
    return 1  # every game resolves home_win=1 -> all games labeled


def test_build_verdict_no_sidecar_backfilled_is_placeholder(tmp_path, monkeypatch):
    grade_dir = tmp_path / "soccer_intl"
    grade_dir.mkdir()
    games = _make_games()
    for ticker, rows in games.items():
        (grade_dir / (ticker + ".jsonl")).write_text(
            "\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    missing_sidecar = tmp_path / "no_sidecar.json"
    doc = m.build_verdict(grade_dir, missing_sidecar, outcome_fn=_outcome_fn)
    assert doc["sidecar_present"] is False
    assert doc["backfilled"]["n_labeled"] == 0
    assert doc["raw"]["n_games"] == len(games)
    assert doc["edge_claimed"] is False


def test_build_verdict_raw_keeps_everything_in_unk(tmp_path):
    grade_dir = tmp_path / "soccer_intl"
    grade_dir.mkdir()
    games = _make_games()
    for ticker, rows in games.items():
        (grade_dir / (ticker + ".jsonl")).write_text(
            "\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    doc = m.build_verdict(grade_dir, tmp_path / "no_sidecar.json", outcome_fn=_outcome_fn)
    assert doc["raw"]["segment_order"] == ["UNK"]
    assert "UNK" in doc["raw"]["segments"]


def test_build_verdict_backfilled_splits_h1_h2(tmp_path):
    grade_dir = tmp_path / "soccer_intl"
    grade_dir.mkdir()
    games = _make_games(n_games=10, n_ticks_per_game=40)
    for ticker, rows in games.items():
        (grade_dir / (ticker + ".jsonl")).write_text(
            "\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    # Build a sidecar labeling the first half of each game's ticks H1, second half H2.
    per_game = {}
    for ticker, rows in games.items():
        labels = {}
        for idx, r in enumerate(rows):
            labels[r["ts"]] = "H1" if idx < len(rows) // 2 else "H2"
        per_game[ticker] = {"labels": labels}
    sidecar_doc = {"buffer_min": 10.0, "per_game": per_game}
    sidecar_path = tmp_path / "sidecar.json"
    sidecar_path.write_text(json.dumps(sidecar_doc), encoding="utf-8")

    doc = m.build_verdict(grade_dir, sidecar_path, outcome_fn=_outcome_fn)
    assert doc["sidecar_present"] is True
    assert doc["sidecar_buffer_min"] == 10.0
    assert set(doc["backfilled"]["segment_order"]) >= {"H1", "H2"}
    h1 = doc["backfilled"]["segments"]["H1"]
    h2 = doc["backfilled"]["segments"]["H2"]
    assert h1["total_ticks"] > 0 and h2["total_ticks"] > 0
    # raw variant must still exist and differ in shape (single UNK bucket).
    assert doc["raw"]["segment_order"] == ["UNK"]


def test_build_verdict_never_raises_on_bad_grade_dir():
    doc = m.build_verdict(grade_dir="not/a/real/dir")
    assert doc["edge_claimed"] is False
    assert "component" in doc


def test_segment_for_tick_raw_always_unk():
    row = {"ts": "2026-06-22T17:10:00Z"}
    sidecar = {"per_game": {"X": {"labels": {"2026-06-22T17:10:00Z": "H1"}}}}
    assert m._segment_for_tick("X", row, sidecar, "raw") == "UNK"
    assert m._segment_for_tick("X", row, None, "backfilled") == "UNK"


def test_segment_for_tick_backfilled_uses_sidecar_or_unk():
    sidecar = {"per_game": {"X": {"labels": {"2026-06-22T17:10:00Z": "H1"}}}}
    labeled_row = {"ts": "2026-06-22T17:10:00Z"}
    unlabeled_row = {"ts": "2026-06-22T99:99:00Z"}
    assert m._segment_for_tick("X", labeled_row, sidecar, "backfilled") == "H1"
    assert m._segment_for_tick("X", unlabeled_row, sidecar, "backfilled") == "UNK"


def test_render_contains_both_variants():
    doc = {
        "raw": {"n_games": 5, "n_labeled": 5, "segment_order": ["UNK"],
                "segments": {"UNK": {"verdict": "MATCH", "n_games": 5,
                                     "total_ticks": 100, "brier_delta": 0.001}}},
        "backfilled": {"n_games": 5, "n_labeled": 5, "segment_order": ["H1", "H2"],
                       "segments": {
                           "H1": {"verdict": "MATCH", "n_games": 5, "total_ticks": 50,
                                  "brier_delta": 0.002},
                           "H2": {"verdict": "MATCH", "n_games": 5, "total_ticks": 50,
                                  "brier_delta": -0.001}}},
    }
    out = m.render(doc)
    assert "VARIANT=raw" in out and "VARIANT=backfilled" in out
    assert "H1" in out and "H2" in out


def test_write_doc_roundtrip(tmp_path):
    path = tmp_path / "doc.json"
    doc = {"a": 1}
    written = m.write_doc(doc, path)
    assert written == path
    assert json.loads(path.read_text(encoding="utf-8")) == doc


def test_component_and_sport_constants():
    assert m.COMPONENT == "m_ingame_unk_backfill_verdict"
    assert m.SPORT == "soccer_intl"
