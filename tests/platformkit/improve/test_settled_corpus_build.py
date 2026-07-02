"""Per-file test for scripts.platformkit.improve.settled_corpus_build.

Proves the mid-game settled-corpus producer is HONEST and MULTI-SPORT:
  - flattens a settled game's stateful ticks into the recal schema (p0/outcome/margin/
    period/seconds_remaining)
  - sport-aware state parsing: nba period/clock, mlb inning, soccer minute, tennis set
  - unsettled game (no home_win label) -> skipped (no fabricated outcome)
  - stateless ticks ("live") -> skipped
  - the produced corpus feeds ingame_recal_segments.segment_settled per sport
  - no $/roi/pnl key on the summary
"""
from __future__ import annotations

import json

from scripts.platformkit.improve import settled_corpus_build as scb
from scripts.platformkit.improve import ingame_recal_segments as rs


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _tick(sport, gid, ts, model_prob, state):
    return {"sport": sport, "game_id": gid, "ts": ts, "market_prob": 0.5,
            "model_prob": model_prob, "side": "home", "state_summary": state}


def _settle(sport, gid, home_win):
    return {"sport": sport, "game_id": gid, "ts": "z", "settled": True,
            "home_win": home_win, "state_summary": "FINAL"}


# --- parse_state -----------------------------------------------------------
def test_parse_state_per_sport():
    assert scb.parse_state("mlb", "home_score=7 away_score=1 inning=5 half=bottom") == (6.0, 5, 0.0)
    assert scb.parse_state("nba", "home_score=70 away_score=66 period=3 clock=250") == (4.0, 3, 250.0)
    assert scb.parse_state("soccer_intl", "home_score=1 away_score=0 minute=57") == (1.0, 57, 0.0)
    assert scb.parse_state("tennis", "home_score=2 away_score=1 set=3") == (1.0, 3, 0.0)
    assert scb.parse_state("mlb", "live") is None            # no score -> skip
    assert scb.parse_state("mlb", "home_score=3 away_score=1") is None   # no inning -> skip


# --- build_settled_corpus --------------------------------------------------
def test_build_corpus_mlb(tmp_path):
    gdir = tmp_path / "grade"
    rows = [_tick("mlb", "G1", "t%d" % i, 0.6,
                  "home_score=%d away_score=1 inning=%d half=top" % (i, min(i + 1, 9)))
            for i in range(6)]
    rows.append(_settle("mlb", "G1", 1.0))
    _write(gdir / "mlb" / "G1.jsonl", rows)
    summ = scb.build_settled_corpus("mlb", grade_dir=gdir, out_dir=tmp_path / "out")
    assert summ["n_games_settled"] == 1
    assert summ["n_corpus_rows"] == 6
    # corpus rows carry the recal schema
    corpus = [json.loads(l) for l in
              (tmp_path / "out" / "settled_mlb.jsonl").read_text().splitlines()]
    r0 = corpus[0]
    assert set(("p0", "outcome", "margin", "period", "seconds_remaining", "sport")) <= set(r0)
    assert r0["outcome"] == 1.0 and r0["p0"] == 0.6


def test_unsettled_game_skipped(tmp_path):
    gdir = tmp_path / "grade"
    rows = [_tick("mlb", "G1", "t%d" % i, 0.6,
                  "home_score=2 away_score=1 inning=3 half=top") for i in range(6)]
    # NO settle row -> no outcome -> whole game skipped
    _write(gdir / "mlb" / "G1.jsonl", rows)
    summ = scb.build_settled_corpus("mlb", grade_dir=gdir, out_dir=tmp_path / "out")
    assert summ["n_games_settled"] == 0
    assert summ["n_corpus_rows"] == 0


def test_stateless_ticks_skipped(tmp_path):
    gdir = tmp_path / "grade"
    rows = [_tick("mlb", "G1", "t%d" % i, 0.6, "live") for i in range(6)]
    rows.append(_settle("mlb", "G1", 0.0))
    _write(gdir / "mlb" / "G1.jsonl", rows)
    summ = scb.build_settled_corpus("mlb", grade_dir=gdir, out_dir=tmp_path / "out")
    assert summ["n_corpus_rows"] == 0       # settled but no parseable state -> empty


def test_no_dollar_keys(tmp_path):
    summ = scb.build_settled_corpus("nba", grade_dir=tmp_path / "none",
                                    out_dir=tmp_path / "out")
    for k in summ:
        assert not any(b in str(k).lower() for b in ("roi", "pnl", "stake", "$"))


# --- end-to-end into the sport-aware segmenter ----------------------------
def test_corpus_feeds_multisport_segmenter(tmp_path):
    gdir = tmp_path / "grade"
    # mlb game: early innings close margin, late innings blowout
    rows = []
    for i in range(12):
        inning = 2 if i < 6 else 8
        margin = 1 if i < 6 else 9
        rows.append(_tick("mlb", "G1", "t%d" % i, 0.55 + 0.01 * i,
                          "home_score=%d away_score=0 inning=%d half=top" % (margin, inning)))
    rows.append(_settle("mlb", "G1", 1.0))
    _write(gdir / "mlb" / "G1.jsonl", rows)
    scb.build_settled_corpus("mlb", grade_dir=gdir, out_dir=tmp_path / "out")
    corpus = [json.loads(l) for l in
              (tmp_path / "out" / "settled_mlb.jsonl").read_text().splitlines()]
    # mlb thresholds: close=runs<2, early=innings 1-5; blowout=runs>=5, late=innings 6-9
    early_close = rs.segment_settled(corpus, "close", "early", "any", sport="mlb")
    late_blow = rs.segment_settled(corpus, "blowout", "late", "any", sport="mlb")
    assert len(early_close) == 6 and len(late_blow) == 6
    # NBA thresholds would NOT bucket these (margin 1 run != nba close-by-points the same way,
    # but innings 2/8 are out of nba period 1-4) -> proves sport-awareness matters
    nba_late = rs.segment_settled(corpus, "blowout", "late", "scarce", sport="nba")
    assert len(nba_late) == 0
