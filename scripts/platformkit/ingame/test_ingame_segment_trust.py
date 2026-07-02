"""Per-file tests for ingame_segment_trust (offline; synthetic grade files)."""
from __future__ import annotations

import json

from scripts.platformkit.ingame import ingame_segment_trust as st


def _write_game(dirp, gid, model_p, market_p, n=60, inning=7):
    d = dirp / "mlb"
    d.mkdir(parents=True, exist_ok=True)
    with (d / ("%s.jsonl" % gid)).open("w", encoding="utf-8") as fh:
        for i in range(n):
            fh.write(json.dumps({
                "sport": "mlb", "game_id": gid, "ts": "2026-06-30T20:%02d:00Z" % (i % 60),
                "model_prob": model_p, "market_prob": market_p,
                "state_summary": "home_score=3 away_score=1 inning=%d half=bottom" % inning,
                "side": "home",
            }) + "\n")


def test_classify_pure():
    assert st._classify(["BETTER_THAN_VENUE", "BETTER_THAN_VENUE"]) == "TRUSTED"
    assert st._classify(["WORSE_THAN_VENUE", "WORSE_THAN_VENUE"]) == "ADVERSE"
    # non-replicated -> NEUTRAL (the artifact guard)
    assert st._classify(["BETTER_THAN_VENUE", "MATCH"]) == "NEUTRAL"
    assert st._classify(["BETTER_THAN_VENUE", "INSUFFICIENT_DATA"]) == "NEUTRAL"  # <2 ruling
    assert st._classify(["MATCH", "MATCH"]) == "NEUTRAL"


def _ticker(day):
    # real MLB ticker so the corpus split is the deterministic DATE-PARITY path
    return "KXMLBGAME-26JUN%02d1920NYYBOS" % day


def test_build_trust_trusted_when_better_in_both(tmp_path):
    grade = tmp_path / "grade"
    for day in range(1, 25):  # days 1..24 -> exactly 12 even / 12 odd -> balanced split
        _write_game(grade, _ticker(day), 0.8, 0.55, n=60, inning=7)
    doc = st.build_trust(sport="mlb", grade_dir=grade, outcome_fn=lambda g: 1)
    assert doc["n_corpora"] == 2
    assert doc["segments"]["I7"]["trust"] == "TRUSTED", doc["segments"]["I7"]
    assert "I7" in doc["trusted"]
    assert doc["edge_claimed"] is False


def test_build_trust_adverse_when_worse_in_both(tmp_path):
    grade = tmp_path / "grade"
    for day in range(1, 25):  # model worse than venue everywhere; balanced date-parity split
        _write_game(grade, _ticker(day), 0.55, 0.8, n=60, inning=8)
    doc = st.build_trust(sport="mlb", grade_dir=grade, outcome_fn=lambda g: 1)
    assert doc["segments"]["I8"]["trust"] == "ADVERSE", doc["segments"]["I8"]
    assert "I8" in doc["adverse"]


def test_floor_adverse_suppresses(tmp_path, monkeypatch):
    trust_doc = {"sport": "mlb", "segments": {
        "I8": {"trust": "ADVERSE", "per_corpus": ["WORSE_THAN_VENUE", "WORSE_THAN_VENUE"]},
        "I7": {"trust": "TRUSTED", "per_corpus": ["BETTER_THAN_VENUE", "BETTER_THAN_VENUE"]},
        "I5": {"trust": "NEUTRAL", "per_corpus": ["MATCH", "MATCH"]},
    }}
    p = tmp_path / "trust.json"
    st.write_doc(trust_doc, p)
    monkeypatch.setenv(st.ENV_FLAG, "1")
    # ADVERSE -> strict floor (None); others -> relaxed unchanged
    assert st.floor_for_segment("mlb", "I8", 0.01, path=p) is None
    assert st.floor_for_segment("mlb", "I7", 0.01, path=p) == 0.01
    assert st.floor_for_segment("mlb", "I5", 0.01, path=p) == 0.01
    assert st.floor_for_segment("mlb", "I1", 0.01, path=p) == 0.01  # unknown seg -> relaxed


def test_floor_disabled_always_relaxed(tmp_path, monkeypatch):
    trust_doc = {"sport": "mlb", "segments": {
        "I8": {"trust": "ADVERSE", "per_corpus": ["WORSE_THAN_VENUE", "WORSE_THAN_VENUE"]}}}
    p = tmp_path / "trust.json"
    st.write_doc(trust_doc, p)
    monkeypatch.setenv(st.ENV_FLAG, "0")
    assert st.floor_for_segment("mlb", "I8", 0.01, path=p) == 0.01  # disabled -> no suppress


def test_floor_from_state_dict(tmp_path, monkeypatch):
    trust_doc = {"sport": "mlb", "segments": {
        "I8": {"trust": "ADVERSE", "per_corpus": ["WORSE_THAN_VENUE", "WORSE_THAN_VENUE"]}}}
    p = tmp_path / "trust.json"
    st.write_doc(trust_doc, p)
    monkeypatch.setenv(st.ENV_FLAG, "1")
    state = {"sport": "mlb", "inning": 8, "half": "bottom", "home_score": 3, "away_score": 1}
    assert st.floor_for_segment("mlb", state, 0.01, path=p) is None


def test_render_and_write(tmp_path):
    grade = tmp_path / "grade"
    for i in range(10):
        _write_game(grade, "R%d" % i, 0.8, 0.55, n=60, inning=6)
    doc = st.build_trust(sport="mlb", grade_dir=grade, outcome_fn=lambda g: 1)
    out = tmp_path / "trust_out.json"
    st.write_doc(doc, out)
    assert out.exists()
    txt = st.render(doc)
    assert "SEGMENT TRUST" in txt and "no $ edge" in txt
