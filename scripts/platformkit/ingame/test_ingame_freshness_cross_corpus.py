"""Per-file tests for ingame_freshness_cross_corpus (offline; synthetic grade
files; injected outcome_fn -- no network, no real resolver I/O).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_freshness_cross_corpus.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame import ingame_freshness_cross_corpus as xc


def _write_game_varying(dirp, sport, gid, model_p, market_probs, *, state="inning=7 half=bottom"):
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


def _stale_then_one_move(model_p=0.8, bad=0.2, n_stale=199):
    """One fresh good tick then a long stale run of a bad venue quote -- the same
    shape the freshness-control test module uses to demonstrate raw-vs-fresh_only
    divergence."""
    return [model_p] + [bad] * n_stale


def test_classify_worse_replicated_when_unanimous():
    assert xc._classify(["WORSE_THAN_VENUE", "WORSE_THAN_VENUE"]) == xc._WORSE_REPLICATED


def test_classify_not_replicated_when_split():
    assert xc._classify(["WORSE_THAN_VENUE", "MATCH"]) == xc._NOT_REPLICATED
    assert xc._classify(["WORSE_THAN_VENUE", "BETTER_THAN_VENUE"]) == xc._NOT_REPLICATED


def test_classify_insufficient_when_fewer_than_two_ruling():
    assert xc._classify(["WORSE_THAN_VENUE", "INSUFFICIENT_DATA"]) == xc._INSUFFICIENT
    assert xc._classify([None, "INSUFFICIENT_DATA"]) == xc._INSUFFICIENT
    assert xc._classify([]) == xc._INSUFFICIENT


def test_date_parity_split_is_disjoint_and_reuses_trust_helper(tmp_path):
    grade = tmp_path / "grade"
    files = []
    for i in range(6):
        gid = "KXMLBGAME-26JUN%02d1845PHIWSH" % (10 + i)
        fp = _write_game_varying(grade, "mlb", gid, 0.8,
                                  _stale_then_one_move())
        files.append(fp)
    halves = xc._split_for_scheme("date_parity", files, "mlb")
    assert len(halves) == 2
    all_files = set(halves[0]) | set(halves[1])
    assert all_files == set(files)
    assert not (set(halves[0]) & set(halves[1]))


def test_date_era_split_orders_early_late_and_disjoint(tmp_path):
    grade = tmp_path / "grade"
    files = []
    # 6 games spread over distinct days so the median split is well-defined.
    for i, day in enumerate([10, 11, 12, 20, 21, 22]):
        gid = "KXMLBGAME-26JUN%02d1845PHIWSH" % day
        fp = _write_game_varying(grade, "mlb", gid, 0.8, _stale_then_one_move())
        files.append(fp)
    halves = xc._split_date_era(files, "mlb")
    assert len(halves) == 2
    all_files = set(halves[0]) | set(halves[1])
    assert all_files == set(files)
    assert not (set(halves[0]) & set(halves[1]))
    # early half should contain the smaller-day tickers
    early_days = sorted(int(p.stem.split("JUN")[1][:2]) for p in halves[0])
    late_days = sorted(int(p.stem.split("JUN")[1][:2]) for p in halves[1])
    assert max(early_days) <= min(late_days)


def test_date_era_drops_unparsable_ids(tmp_path):
    grade = tmp_path / "grade"
    # non-ticker ids -> unparsable -> dropped from both halves, never raises.
    files = []
    for i in range(4):
        gid = "G%d" % i
        fp = _write_game_varying(grade, "mlb", gid, 0.8, _stale_then_one_move())
        files.append(fp)
    halves = xc._split_date_era(files, "mlb")
    assert halves == [[], []]


def test_build_report_never_raises_and_has_both_schemes(tmp_path):
    grade = tmp_path / "grade"
    outc = {}
    for i, day in enumerate([10, 11, 12, 20, 21, 22, 23, 24]):
        gid = "KXMLBGAME-26JUN%02d1845PHIWSH" % day
        _write_game_varying(grade, "mlb", gid, 0.8, _stale_then_one_move())
        outc[gid] = 1
    doc = xc.build_report(sport="mlb", grade_dir=grade,
                          outcome_fn=lambda g: outc.get(g),
                          min_games=1, min_ticks=1)
    assert doc["edge_claimed"] is False
    assert set(doc["schemes"].keys()) == set(xc.SPLIT_SCHEMES)
    for scheme_doc in doc["schemes"].values():
        assert scheme_doc["n_halves"] == 2
    assert set(doc["overall_segment_verdict"].keys()) == set(
        ["I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8", "I9", "UNK"])


def test_build_report_insufficient_when_no_labels(tmp_path):
    grade = tmp_path / "grade"
    for i, day in enumerate([10, 11]):
        gid = "KXMLBGAME-26JUN%02d1845PHIWSH" % day
        _write_game_varying(grade, "mlb", gid, 0.8, _stale_then_one_move())
    doc = xc.build_report(sport="mlb", grade_dir=grade, outcome_fn=lambda g: None)
    for scheme_doc in doc["schemes"].values():
        for sv in scheme_doc["segments"].values():
            assert sv["verdict"] == xc._INSUFFICIENT


def test_overall_conservative_when_schemes_disagree(monkeypatch):
    def _fake_split(scheme, files, sport):
        return [files[: len(files) // 2], files[len(files) // 2:]]
    monkeypatch.setattr(xc, "_split_for_scheme", _fake_split)

    def _fake_half(files, ofn, sport, eps, min_games, min_ticks):
        return {"n_files": 0, "n_labeled": 0, "n_ticks": 0, "n_fresh_ticks": 0,
                "fresh_share": None,
                "segments": {"I5": {"verdict": "WORSE_THAN_VENUE", "n_games": 5,
                                    "total_ticks": 50, "brier_delta": 0.01}}}
    monkeypatch.setattr(xc, "_fresh_only_verdict_for_half", _fake_half)
    doc = xc.build_report(sport="mlb", paths=[], outcome_fn=lambda g: 1)
    assert doc["overall_segment_verdict"]["I5"] == xc._WORSE_REPLICATED


def test_write_and_render(tmp_path):
    grade = tmp_path / "grade"
    outc = {}
    for i, day in enumerate([10, 11, 12, 20, 21, 22]):
        gid = "KXMLBGAME-26JUN%02d1845PHIWSH" % day
        _write_game_varying(grade, "mlb", gid, 0.8, _stale_then_one_move())
        outc[gid] = 1
    doc = xc.build_report(sport="mlb", grade_dir=grade,
                          outcome_fn=lambda g: outc.get(g),
                          min_games=1, min_ticks=1)
    out = tmp_path / "xc.json"
    xc.write_doc(doc, out)
    assert out.exists()
    reloaded = json.loads(out.read_text())
    assert reloaded["component"] == xc.COMPONENT
    txt = xc.render(doc)
    assert "cross-corpus adjudication" in txt
    assert "edge_claimed=False" in txt


def test_component_never_raises_on_bad_sport():
    doc = xc.build_report(sport="___nope___", paths=[], outcome_fn=lambda g: None)
    assert doc["edge_claimed"] is False
