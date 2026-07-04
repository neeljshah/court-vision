"""Per-file tests for ingame_outcome_verdict_freshness (offline; synthetic grade
files; injected outcome_fn -- no network, no real resolver I/O).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_outcome_verdict_freshness.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame import ingame_outcome_verdict_freshness as ovf


def _write_game_varying(dirp, sport, gid, model_p, market_probs, *, state="inning=7 half=bottom"):
    """Write a grade file where market_prob is an explicit per-tick sequence (so we
    control the freshness/staleness pattern precisely)."""
    d = dirp / sport
    d.mkdir(parents=True, exist_ok=True)
    fp = d / ("%s.jsonl" % gid)
    with fp.open("w", encoding="utf-8") as fh:
        for i, mkt in enumerate(market_probs):
            fh.write(json.dumps({
                "sport": sport, "game_id": gid, "ts": "2026-07-01T12:%02d:00Z" % i,
                "model_prob": model_p, "market_prob": mkt,
                "state_summary": state, "side": "home",
            }) + "\n")
    return fp


def _write_game_constant(dirp, sport, gid, model_p, market_p, *, n=40, state="inning=7 half=bottom"):
    return _write_game_varying(dirp, sport, gid, model_p, [market_p] * n, state=state)


def test_raw_and_fresh_only_both_emitted_and_agree_when_all_fresh():
    # every tick's market_prob differs from the previous -> fresh_only == raw exactly.
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        grade = Path(td) / "grade"
        outc = {}
        for i in range(10):
            gid = "G%d" % i
            probs = [0.5 + 0.001 * j for j in range(40)]  # every tick moves
            _write_game_varying(grade, "mlb", gid, 0.8, probs)
            outc[gid] = 1
        doc = ovf.build_verdict_with_control(
            sport="mlb", grade_dir=grade, outcome_fn=lambda g: outc.get(g))
        seg = doc["segments"]["I7"]
        assert seg["raw"]["total_ticks"] == seg["fresh_only"]["total_ticks"]
        assert doc["fresh_share"] == 1.0
        assert "I7" not in doc["flipped_segments"]


def test_stale_run_reduces_fresh_tick_count():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        grade = Path(td) / "grade"
        outc = {}
        for i in range(10):
            gid = "G%d" % i
            # tick0 fresh, then a run of 9 stale repeats, one move, more stale.
            probs = [0.55] + [0.55] * 9 + [0.60] * 10
            _write_game_varying(grade, "mlb", gid, 0.8, probs)
            outc[gid] = 1
        doc = ovf.build_verdict_with_control(
            sport="mlb", grade_dir=grade, outcome_fn=lambda g: outc.get(g))
        assert doc["n_fresh_ticks"] < doc["n_ticks"]
        assert doc["fresh_share"] < 1.0


def test_stale_run_inflates_raw_delta_vs_fresh_only():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        grade = Path(td) / "grade"
        outc = {}
        for i in range(10):
            gid = "G%d" % i
            # one fresh good tick (0.8, matches model, outcome=1), then a long stale
            # run of a bad venue quote (0.2) repeated verbatim -- only the FIRST 0.2
            # tick is fresh (it differs from the preceding 0.8); the other 198 are
            # stale repeats and get excluded from fresh_only.
            probs = [0.8] + [0.2] * 199
            _write_game_varying(grade, "mlb", gid, 0.8, probs)
            outc[gid] = 1
        doc = ovf.build_verdict_with_control(
            sport="mlb", grade_dir=grade, outcome_fn=lambda g: outc.get(g),
            min_games=8, min_ticks=5)
        seg = doc["segments"]["I7"]
        # raw: dominated by 198 stale-bad-venue repeats -> model much better than venue.
        assert seg["raw"]["verdict"] == "BETTER_THAN_VENUE"
        assert seg["raw"]["total_ticks"] == 2000  # 10 games * 200 ticks
        # fresh_only: only 2 ticks/game (the two genuine quote changes) -> far fewer
        # stale-bad-venue repeats counted, so the magnitude of the model-vs-venue
        # delta shrinks substantially versus raw (the honest freshness-control effect).
        assert seg["fresh_only"]["total_ticks"] == 20  # 10 games * 2 fresh ticks
        assert abs(seg["fresh_only"]["brier_delta"]) < abs(seg["raw"]["brier_delta"])


def test_insufficient_when_fresh_ticks_too_thin():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        grade = Path(td) / "grade"
        outc = {}
        for i in range(10):
            gid = "G%d" % i
            # only the first tick is fresh; huge stale run after -> fresh_only ticks
            # per game = 1, total across 10 games = 10 < MIN_TICKS_PER_SEG (200).
            probs = [0.8] + [0.2] * 300
            _write_game_varying(grade, "mlb", gid, 0.8, probs)
            outc[gid] = 1
        doc = ovf.build_verdict_with_control(
            sport="mlb", grade_dir=grade, outcome_fn=lambda g: outc.get(g))
        seg = doc["segments"]["I7"]
        assert seg["fresh_only"]["verdict"] == "INSUFFICIENT_DATA"
        assert seg["raw"]["verdict"] != "INSUFFICIENT_DATA"
        assert "I7" in doc["flipped_segments"]


def test_mlb_in_control_sports_list():
    assert "mlb" in ovf.CONTROL_SPORTS
    assert "soccer_intl" in ovf.CONTROL_SPORTS


def test_build_all_composes_multiple_sports(monkeypatch):
    def _fake(sport, **kw):
        return {"sport": sport, "n_files": 0, "n_labeled": 0, "n_ticks": 0,
                "n_fresh_ticks": 0, "fresh_share": None, "segments": {},
                "flipped_segments": [], "edge_claimed": False}
    monkeypatch.setattr(ovf, "build_verdict_with_control", _fake)
    doc = ovf.build_all(sports=["mlb", "soccer_intl"])
    assert set(doc["per_sport"].keys()) == {"mlb", "soccer_intl"}
    assert doc["edge_claimed"] is False
    assert doc["flipped_segments_by_sport"] == {}


def test_write_and_render(tmp_path):
    grade = tmp_path / "grade"
    outc = {}
    for i in range(10):
        gid = "R%d" % i
        probs = [0.5 + 0.001 * j for j in range(40)]
        _write_game_varying(grade, "mlb", gid, 0.8, probs)
        outc[gid] = 1
    doc = ovf.build_verdict_with_control(
        sport="mlb", grade_dir=grade, outcome_fn=lambda g: outc.get(g))
    full = {"component": ovf.COMPONENT, "sports": ["mlb"], "per_sport": {"mlb": doc},
            "flipped_segments_by_sport": {}, "edge_claimed": False}
    out = tmp_path / "verdict_freshness.json"
    ovf.write_doc(full, out)
    assert out.exists()
    reloaded = json.loads(out.read_text())
    assert reloaded["component"] == ovf.COMPONENT
    txt = ovf.render(full)
    assert "QUOTE-FRESHNESS" in txt and "edge_claimed=False" in txt


def test_no_labeled_games_all_insufficient():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        grade = Path(td) / "grade"
        for i in range(5):
            _write_game_constant(grade, "mlb", "U%d" % i, 0.8, 0.55, n=40)
        doc = ovf.build_verdict_with_control(
            sport="mlb", grade_dir=grade, outcome_fn=lambda g: None)
        assert doc["n_labeled"] == 0
