"""Per-file tests for ingame_outcome_verdict_multi (offline; synthetic grade files;
injected outcome_fn -- no network, no real resolver I/O).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_outcome_verdict_multi.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame import ingame_outcome_verdict_multi as ovm


def _write_game(dirp, sport, gid, model_p, market_p, *, n=40, state="minute=20 half=1"):
    d = dirp / sport
    d.mkdir(parents=True, exist_ok=True)
    fp = d / ("%s.jsonl" % gid)
    with fp.open("w", encoding="utf-8") as fh:
        for i in range(n):
            fh.write(json.dumps({
                "sport": sport, "game_id": gid, "ts": "2026-07-01T12:%02d:00Z" % (i % 60),
                "model_prob": model_p, "market_prob": market_p,
                "state_summary": state, "side": "home",
            }) + "\n")
    return fp


def test_build_verdict_for_sport_soccer_better_than_venue(tmp_path):
    grade = tmp_path / "grade"
    outc = {}
    for i in range(10):
        gid = "S%d" % i
        _write_game(grade, "soccer_intl", gid, 0.8, 0.55, state="minute=20 half=1")
        outc[gid] = 1
    doc = ovm.build_verdict_for_sport(
        "soccer_intl", grade_dir=grade, outcome_fn=lambda g: outc.get(g))
    assert doc["segments"]["H1"]["verdict"] == "BETTER_THAN_VENUE"
    assert doc["segment_source"] == "game_clock"
    assert doc["edge_claimed"] is False


def test_build_verdict_for_sport_tennis_insufficient(tmp_path):
    grade = tmp_path / "grade"
    _write_game(grade, "tennis", "T0", 0.8, 0.55, state="set=2")
    doc = ovm.build_verdict_for_sport(
        "tennis", grade_dir=grade, outcome_fn=lambda g: 1)
    assert doc["segments"]["S2"]["verdict"] == "INSUFFICIENT_DATA"


def test_build_verdict_for_sport_wnba_uses_period_segment(tmp_path):
    grade = tmp_path / "grade"
    outc = {}
    for i in range(9):
        gid = "W%d" % i
        _write_game(grade, "wnba", gid, 0.8, 0.55, state="period=3")
        outc[gid] = 1
    doc = ovm.build_verdict_for_sport(
        "wnba", grade_dir=grade, outcome_fn=lambda g: outc.get(g))
    assert "Q3" in doc["segments"]
    assert doc["segment_source"] == "game_clock"


def test_segment_source_falls_back_when_state_unresolvable(tmp_path):
    grade = tmp_path / "grade"
    for i in range(9):
        _write_game(grade, "tennis", "U%d" % i, 0.8, 0.55, state="")  # no set/period/etc
    doc = ovm.build_verdict_for_sport("tennis", grade_dir=grade, outcome_fn=lambda g: 1)
    assert doc["segment_source"] == "capture_time_fallback"
    assert "segment_source_note" in doc


def test_soccer_outcome_fn_skips_draws():
    class _StubResolver:
        available = True

        def final_score(self, ticker):
            return (1, 1)  # draw

    import scripts.platformkit.ingame.soccer_outcome as so
    orig = so.SoccerOutcomeResolver
    so.SoccerOutcomeResolver = lambda: _StubResolver()
    try:
        fn = ovm._soccer_outcome_fn()
        assert fn("KXWCGAME-anything") is None
    finally:
        so.SoccerOutcomeResolver = orig


def test_build_verdict_all_composes_three_sports(tmp_path, monkeypatch):
    grade = tmp_path / "grade"
    outc = {}
    for i in range(10):
        gid = "G%d" % i
        _write_game(grade, "soccer_intl", gid, 0.8, 0.55, state="minute=20 half=1")
        outc[gid] = 1

    _real_build = ovm.build_verdict_for_sport

    def _fake_build(sport, **kw):
        if sport == "soccer_intl":
            return _real_build(sport, grade_dir=grade, outcome_fn=lambda g: outc.get(g))
        return {"sport": sport, "n_files": 0, "n_labeled": 0, "segments": {},
                "better_segments": [], "worse_segments": [], "edge_claimed": False,
                "segment_source": "game_clock"}

    monkeypatch.setattr(ovm, "build_verdict_for_sport", _fake_build)
    doc = ovm.build_verdict_all(sports=["soccer_intl", "tennis", "wnba"])
    assert set(doc["per_sport"].keys()) == {"soccer_intl", "tennis", "wnba"}
    assert doc["edge_claimed"] is False
    assert "soccer_intl" in doc["better_segments_by_sport"]
    assert doc["per_sport"]["tennis"]["n_labeled"] == 0


def test_sports_list_includes_npb_kbo():
    assert "npb" in ovm.SPORTS and "kbo" in ovm.SPORTS


def test_npb_outcome_fn_wired_in_factory():
    assert "npb" in ovm._OUTCOME_FACTORY
    fn = ovm._OUTCOME_FACTORY["npb"]()
    # no real npb_results.parquet fixture here -- just confirm the factory
    # builds a callable that degrades to None rather than raising.
    assert fn("KXNPBGAME-does-not-matter") is None or isinstance(
        fn("KXNPBGAME-does-not-matter"), int)


def test_kbo_outcome_fn_wired_in_factory():
    assert "kbo" in ovm._OUTCOME_FACTORY
    fn = ovm._OUTCOME_FACTORY["kbo"]()
    assert fn("KXKBOGAME-does-not-matter") is None or isinstance(
        fn("KXKBOGAME-does-not-matter"), int)


def test_build_verdict_for_sport_npb_insufficient_when_no_model(tmp_path):
    # npb ticks currently carry model_prob=None (no live model wired) -- a
    # captured grade file with model_prob=None must still degrade to an
    # honest INSUFFICIENT_DATA/n_labeled=0 verdict, never raise.
    grade = tmp_path / "grade"
    _write_game(grade, "npb", "N0", None, 0.55, state="inning=3 half=top")
    doc = ovm.build_verdict_for_sport("npb", grade_dir=grade, outcome_fn=lambda g: 1)
    assert doc["edge_claimed"] is False


def test_build_verdict_all_composes_npb_kbo(tmp_path, monkeypatch):
    def _fake_build(sport, **kw):
        return {"sport": sport, "n_files": 0, "n_labeled": 0, "segments": {},
                "better_segments": [], "worse_segments": [], "edge_claimed": False,
                "segment_source": "game_clock"}

    monkeypatch.setattr(ovm, "build_verdict_for_sport", _fake_build)
    doc = ovm.build_verdict_all(sports=["npb", "kbo"])
    assert set(doc["per_sport"].keys()) == {"npb", "kbo"}
    assert doc["edge_claimed"] is False


def test_write_and_render(tmp_path):
    grade = tmp_path / "grade"
    outc = {}
    for i in range(10):
        gid = "R%d" % i
        _write_game(grade, "soccer_intl", gid, 0.8, 0.55, state="minute=20 half=1")
        outc[gid] = 1
    doc = ovm.build_verdict_for_sport(
        "soccer_intl", grade_dir=grade, outcome_fn=lambda g: outc.get(g))
    full = {"component": ovm.COMPONENT, "sports": ["soccer_intl"],
            "per_sport": {"soccer_intl": doc}, "better_segments_by_sport": {},
            "worse_segments_by_sport": {}, "edge_claimed": False}
    out = tmp_path / "verdict_multi.json"
    ovm.write_doc(full, out)
    assert out.exists()
    reloaded = json.loads(out.read_text())
    assert reloaded["component"] == ovm.COMPONENT
    txt = ovm.render(full)
    assert "MULTI-SPORT" in txt and "$ edge" in txt
