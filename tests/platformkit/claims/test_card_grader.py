"""tests.platformkit.claims.test_card_grader -- pooled 4-condition verdict, synthetic fixtures."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.platformkit.claims import card_grader as cg
from scripts.platformkit.claims import card_registry as reg

TS = "2026-07-14T00:00:00Z"


@pytest.fixture(autouse=True)
def _isolated_cards_path(tmp_path, monkeypatch):
    monkeypatch.setattr(reg, "CARDS_PATH", tmp_path / "cards.jsonl")
    yield


def _register(scope="ingame", expected_sign="+", registered_ts=TS, trigger="quarter == 1"):
    cond = {"scope": scope, "window": "w", "trigger": trigger, "entity": "game"}
    res = reg.register(claim="c", condition=cond, mechanism="m",
                       expected_sign=expected_sign, expected_magnitude="small",
                       source="test", ts=registered_ts)
    assert res["ok"] is True, res
    return res["card_id"]


def _write_game(tmp_path, sport, game_id, date, card_id, *, n_fired, n_notfired,
                fired_model, fired_market, fired_y, ctrl_model, ctrl_market, ctrl_y):
    """One settled grade file for one game: n_fired FIRED ticks + n_notfired control ticks."""
    p = tmp_path / ("%s_%s.jsonl" % (sport, game_id))
    lines = []
    for i in range(n_fired):
        lines.append({"sport": sport, "game_id": game_id, "ts": "%sT%02d:00:00Z" % (date, i % 24),
                      "market_prob": fired_market, "model_prob": fired_model, "side": "home",
                      "claim_tags": {card_id: True}})
    for i in range(n_notfired):
        lines.append({"sport": sport, "game_id": game_id, "ts": "%sT%02d:00:00Z" % (date, i % 24),
                      "market_prob": ctrl_market, "model_prob": ctrl_model, "side": "home",
                      "claim_tags": {card_id: False}})
    p.write_text("\n".join(json.dumps(r) for r in lines), encoding="utf-8")
    return ("mlb", p), fired_y if n_fired else ctrl_y


def _make_files(tmp_path, card_id, *, n_games_per_half=6, rows_per_game=12,
                fired_model=0.9, fired_market=0.5, ctrl_model=0.5, ctrl_market=0.5,
                y=1.0, dates_a=("2026-07-01", "2026-07-02", "2026-07-03"),
                dates_b=("2026-07-08", "2026-07-09", "2026-07-10")):
    files = []
    outcomes = {}
    gi = 0
    for half_dates in (dates_a, dates_b):
        for g in range(n_games_per_half):
            date = half_dates[g % len(half_dates)]
            gid = "g%d" % gi
            gi += 1
            (sport, p), _ = _write_game(tmp_path, "mlb", gid, date, card_id,
                                        n_fired=rows_per_game, n_notfired=rows_per_game,
                                        fired_model=fired_model, fired_market=fired_market, fired_y=y,
                                        ctrl_model=ctrl_model, ctrl_market=ctrl_market, ctrl_y=y)
            files.append((sport, p))
            outcomes[gid] = y
    return files, (lambda sport, gid: outcomes.get(gid))


def test_all_four_conditions_pass_validates(tmp_path):
    cid = _register(expected_sign="+")
    files, ofn = _make_files(tmp_path, cid)
    card = reg.get_all_latest()[cid]
    result = cg.grade_card(card, files, outcome_fn=ofn)
    assert result["verdict"] == "VALIDATED", result
    assert result["detail"]["cond_sign_match"] is True
    assert result["detail"]["cond_beats_control"] is True
    assert result["detail"]["cond_game_clustered_significant"] is True


def test_sign_flip_between_halves_rejects(tmp_path):
    cid = _register(expected_sign="+")
    files_a, ofn_a = _make_files(tmp_path, cid, n_games_per_half=6,
                                 dates_a=("2026-07-01",), dates_b=("2026-08-01",))
    # half B: model UNDER market and y=0 -> CLV negative, opposite of expected_sign "+"
    files_b, ofn_b = _make_files(tmp_path, cid, n_games_per_half=6,
                                 fired_model=0.1, fired_market=0.5, y=0.0,
                                 dates_a=("2026-07-01",), dates_b=("2026-08-01",))
    # keep only half-A games from files_a and half-B games from files_b
    files = files_a[:6] + files_b[6:]

    def ofn(sport, gid):
        idx = int(gid[1:])
        return 1.0 if idx < 6 else 0.0

    card = reg.get_all_latest()[cid]
    result = cg.grade_card(card, files, outcome_fn=ofn)
    assert result["verdict"] == "REJECTED", result
    assert result["detail"]["cond_sign_match"] is False


def test_fired_not_better_than_control_rejects(tmp_path):
    cid = _register(expected_sign="+")
    # fired and control are IDENTICAL (model=market both halves) -> no improvement from firing
    files, ofn = _make_files(tmp_path, cid, fired_model=0.5, fired_market=0.5,
                             ctrl_model=0.5, ctrl_market=0.5, y=1.0)
    card = reg.get_all_latest()[cid]
    result = cg.grade_card(card, files, outcome_fn=ofn)
    assert result["verdict"] == "REJECTED", result
    assert result["detail"]["cond_beats_control"] is False


def test_below_min_fired_stays_open_accruing(tmp_path):
    cid = _register(expected_sign="+")
    files, ofn = _make_files(tmp_path, cid, n_games_per_half=2, rows_per_game=5)  # 10 fired/half < 60
    card = reg.get_all_latest()[cid]
    result = cg.grade_card(card, files, outcome_fn=ofn)
    assert result["verdict"] == "OPEN"
    assert "accruing" in result["reason"]


def test_no_settled_rows_honest_n_fired_zero(tmp_path):
    cid = _register(expected_sign="+")
    card = reg.get_all_latest()[cid]
    result = cg.grade_card(card, [], outcome_fn=lambda s, g: None)
    assert result["verdict"] == "OPEN"
    assert result["n_fired"] == 0


def test_pregame_scope_has_no_source_open_accruing(tmp_path):
    cid = _register(scope="pregame", trigger="expected_pace_pregame > 0", expected_sign="+")
    card = reg.get_all_latest()[cid]
    result = cg.grade_card(card, [], outcome_fn=lambda s, g: None)
    assert result["verdict"] == "OPEN"
    assert "no persisted claim_tags source" in result["reason"]


def test_game_clustering_pools_by_game_not_row(tmp_path):
    cid = _register(expected_sign="+")
    files, ofn = _make_files(tmp_path, cid, n_games_per_half=6, rows_per_game=12)
    card = reg.get_all_latest()[cid]
    result = cg.grade_card(card, files, outcome_fn=ofn)
    assert result["detail"]["half_a"]["n_fired"] == 6 * 12  # rows
    assert result["detail"]["half_a"]["n_games"] == 6  # clusters, not rows


def test_starved_closes_after_45_days_low_fire_rate(tmp_path):
    old_ts = "2026-05-01T00:00:00Z"  # >45 days before `now`
    cid = _register(expected_sign="+", registered_ts=old_ts)
    # 1 fired row out of 500 total -> fire_rate < 1%
    files, _ = _make_files(tmp_path, cid, n_games_per_half=1, rows_per_game=1)
    p = tmp_path / "mlb_bulk.jsonl"
    lines = [{"sport": "mlb", "game_id": "bulk", "ts": "2026-07-01T00:00:00Z",
             "market_prob": 0.5, "model_prob": 0.5, "claim_tags": {cid: False}} for _ in range(500)]
    p.write_text("\n".join(json.dumps(r) for r in lines), encoding="utf-8")
    files = files + [("mlb", p)]

    def ofn(sport, gid):
        return 1.0

    card = reg.get_all_latest()[cid]
    now = datetime(2026, 7, 14, tzinfo=timezone.utc)
    result = cg.grade_card(card, files, outcome_fn=ofn, now=now)
    assert result["verdict"] == "STARVED", result


def test_grade_all_peeks_closes_and_promotes(tmp_path, monkeypatch):
    monkeypatch.setattr(reg, "MAX_OPEN", 1)
    cid_open = _register(expected_sign="+")
    cid_queued = _register(expected_sign="+")
    assert reg.get_all_latest()[cid_open]["status"] == "OPEN"
    assert reg.get_all_latest()[cid_queued]["status"] == "QUEUED"

    # grade_all discovers via grade_dir/<sport>/*.jsonl; empty here (no capture cycle run) so
    # this exercises the honest n_fired=0 path -- but peek-lock fires unconditionally.
    empty_dir = tmp_path / "empty_grade"
    cg.grade_all(sports=["mlb"], grade_dir=empty_dir, ledger_path=tmp_path / "card_ledger.jsonl")
    latest = reg.get_all_latest()
    assert latest[cid_open]["outcomes_peeked"] is True

    # direct grade (real settled rows, injected outcome_fn) exercises VALIDATED -> close -> promote.
    files, ofn = _make_files(tmp_path, cid_open)
    card = latest[cid_open]
    result = cg.grade_card(card, files, outcome_fn=ofn)
    assert result["verdict"] == "VALIDATED"
    reg.close_card(cid_open, "VALIDATED", "test", TS)
    promoted = reg.promote_queued(TS)
    assert promoted == [cid_queued]
    assert reg.get_all_latest()[cid_queued]["status"] == "OPEN"


def test_ledger_append(tmp_path):
    cid = _register(expected_sign="+")
    files, ofn = _make_files(tmp_path, cid)
    card = reg.get_all_latest()[cid]
    result = cg.grade_card(card, files, outcome_fn=ofn)
    ledger = tmp_path / "card_ledger.jsonl"
    from scripts.platformkit.io_atomic import append_jsonl_atomic
    append_jsonl_atomic(ledger, result)
    rows = [json.loads(ln) for ln in ledger.read_text(encoding="ascii").splitlines() if ln.strip()]
    assert rows[0]["card_id"] == cid
    assert rows[0]["edge_claimed"] is False
