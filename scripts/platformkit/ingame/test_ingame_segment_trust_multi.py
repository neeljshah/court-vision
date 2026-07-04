"""Per-file tests for ingame_segment_trust_multi (offline; synthetic grade files;
injected outcome_fn -- no network, no real resolver I/O).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_segment_trust_multi.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame import ingame_segment_trust_multi as stm


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


def test_module_reuses_mlb_split_and_classify_helpers():
    from scripts.platformkit.ingame import ingame_segment_trust as st
    assert stm._st is st
    assert stm.N_CORPORA == st.N_CORPORA
    assert stm.MIN_CORPORA == st.MIN_CORPORA


def test_build_trust_for_sport_trusted_when_replicated(tmp_path):
    grade = tmp_path / "grade"
    outc = {}
    # 20 games -> the deterministic md5(gid) hash split lands enough in EACH
    # corpus to clear MIN_GAMES_PER_SEG (8) in both halves.
    for i in range(20):
        gid = "S%d" % i
        _write_game(grade, "soccer_intl", gid, 0.8, 0.55, state="minute=20 half=1")
        outc[gid] = 1
    doc = stm.build_trust_for_sport(
        "soccer_intl", grade_dir=grade, outcome_fn=lambda g: outc.get(g))
    assert doc["sport"] == "soccer_intl"
    assert doc["n_corpora"] == 2
    assert "H1" in doc["segments"]
    assert doc["edge_claimed"] is False


def test_build_trust_for_sport_neutral_when_thin(tmp_path):
    grade = tmp_path / "grade"
    outc = {}
    for i in range(3):  # below MIN_GAMES_PER_SEG in a single corpus, let alone split
        gid = "T%d" % i
        _write_game(grade, "tennis", gid, 0.8, 0.55, state="set=1")
        outc[gid] = 1
    doc = stm.build_trust_for_sport("tennis", grade_dir=grade, outcome_fn=lambda g: outc.get(g))
    assert doc["segments"]["S1"]["trust"] == "NEUTRAL"
    assert doc["trusted"] == []


def test_build_trust_all_measurement_only_flag_set(tmp_path, monkeypatch):
    grade = tmp_path / "grade"
    outc = {}
    for i in range(20):
        gid = "W%d" % i
        _write_game(grade, "wnba", gid, 0.8, 0.55, state="period=2")
        outc[gid] = 1

    _real_build = stm.build_trust_for_sport

    def _fake_build(sport, **kw):
        if sport == "wnba":
            return _real_build(sport, grade_dir=grade, outcome_fn=lambda g: outc.get(g))
        return {"sport": sport, "n_corpora": 0, "corpus_labeled": [], "segments": {},
                "trusted": [], "adverse": [], "edge_claimed": False}

    monkeypatch.setattr(stm, "build_trust_for_sport", _fake_build)
    doc = stm.build_trust_all(sports=["soccer_intl", "tennis", "wnba"])
    assert doc["measurement_only"] is True
    assert doc["edge_claimed"] is False
    assert set(doc["per_sport"].keys()) == {"soccer_intl", "tennis", "wnba"}


def test_no_floor_wiring_exported():
    # Binding: this module must never expose an execution-affecting floor
    # function -- that stays exclusively with the MLB-only ingame_segment_trust.
    assert "floor_for_segment" not in stm.__all__
    assert not hasattr(stm, "floor_for_segment")


def test_write_and_render(tmp_path):
    doc = stm.build_trust_all(sports=["soccer_intl"])
    out = tmp_path / "trust_multi.json"
    stm.write_doc(doc, out)
    assert out.exists()
    reloaded = json.loads(out.read_text())
    assert reloaded["component"] == stm.COMPONENT
    txt = stm.render(doc)
    assert "MULTI-SPORT" in txt and "MEASUREMENT ONLY" in txt
