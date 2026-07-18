"""Per-file tests for inplay_capture_quality (NETWORK-FREE -- synthetic jsonl fixtures)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.platformkit.odds_provider.inplay_capture_quality import (
    DEFAULT_SPORTS, GREEN, NO_DATA, REGRESSION, completeness, load_status,
    measure_inplay, render, scoreboard_inplay, write_status)


def _row(game_id="g1", venue="kalshi", market_type="moneyline", prob=0.6,
         ts="2026-07-03T10:00:00Z", line=None):
    row = {"sport": "mlb", "game_id": game_id, "venue": venue,
           "market_type": market_type, "side": "home", "ticker": "TICK-%s" % game_id,
           "prob": prob, "ts": ts, "phase": "in_play", "source_ts": ts}
    if line is not None:
        row["line"] = line
    return row


def _write_day(base_dir: Path, sport: str, date_str: str, rows):
    d = base_dir / sport
    d.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r) for r in rows]
    (d / ("%s.jsonl" % date_str)).write_text("\n".join(lines) + ("\n" if lines else ""),
                                              encoding="utf-8")


def test_measure_missing_file_returns_zeros_with_no_file_flag(tmp_path):
    out = measure_inplay("mlb", "2026-07-03", base_dir=tmp_path)
    assert out["no_file"] is True
    assert out["n_rows"] == 0
    assert out["n_games"] == 0
    assert out["max_gap_min"] is None


def test_measure_parses_schema_with_and_without_line_field(tmp_path):
    rows = [_row(game_id="g1", venue="kalshi"),
            _row(game_id="g1", venue="kalshi", market_type="total", prob=0.55, line=8.5),
            _row(game_id="g2", venue="kalshi")]
    _write_day(tmp_path, "mlb", "2026-07-03", rows)
    out = measure_inplay("mlb", "2026-07-03", base_dir=tmp_path)
    assert out["no_file"] is False
    assert out["n_rows"] == 3
    assert out["n_games"] == 2
    assert out["n_market_types"] == 2
    assert out["rows_by_market_type"] == {"moneyline": 2, "total": 1}


def test_measure_corrupt_line_skipped_and_counted(tmp_path):
    d = tmp_path / "mlb"
    d.mkdir(parents=True)
    good = json.dumps(_row())
    (d / "2026-07-03.jsonl").write_text(good + "\n" + "{not json" + "\n", encoding="utf-8")
    out = measure_inplay("mlb", "2026-07-03", base_dir=tmp_path)
    assert out["n_rows"] == 1
    assert out["n_corrupt"] == 1


def test_tail_share_is_moneyline_only(tmp_path):
    # A "total" row at prob 0.05 (deep tail-looking) must NOT count toward tail_share.
    rows = [_row(game_id="g1", market_type="total", prob=0.05, line=8.5),
            _row(game_id="g1", market_type="moneyline", prob=0.10),
            _row(game_id="g1", market_type="moneyline", prob=0.50)]
    _write_day(tmp_path, "mlb", "2026-07-03", rows)
    out = measure_inplay("mlb", "2026-07-03", base_dir=tmp_path)
    # only 2 moneyline rows counted; 1 of them (0.10) is a tail -> 1/2
    assert abs(out["tail_share"] - 0.5) < 1e-9


def test_tail_share_guards_prob_bounds(tmp_path):
    rows = [_row(prob=0.0), _row(prob=1.0), _row(prob=None), _row(prob=0.9)]
    _write_day(tmp_path, "mlb", "2026-07-03", rows)
    out = measure_inplay("mlb", "2026-07-03", base_dir=tmp_path)
    # 0.0 and 1.0 excluded by the 0<prob<1 guard, None excluded by the float() guard;
    # only prob=0.9 counts, and it is a tail -> tail_share = 1.0
    assert out["tail_share"] == 1.0


def test_max_gap_over_distinct_ts(tmp_path):
    rows = [_row(ts="2026-07-03T10:00:00Z"), _row(ts="2026-07-03T10:00:00Z"),
            _row(ts="2026-07-03T10:05:00Z"), _row(ts="2026-07-03T10:35:00Z")]
    _write_day(tmp_path, "mlb", "2026-07-03", rows)
    out = measure_inplay("mlb", "2026-07-03", base_dir=tmp_path)
    assert out["max_gap_min"] == 30.0
    assert out["first_ts"].startswith("2026-07-03T10:00:00")
    assert out["last_ts"].startswith("2026-07-03T10:35:00")


def test_max_gap_none_under_two_distinct_ts(tmp_path):
    _write_day(tmp_path, "mlb", "2026-07-03", [_row(ts="2026-07-03T10:00:00Z"),
                                                _row(ts="2026-07-03T10:00:00Z")])
    out = measure_inplay("mlb", "2026-07-03", base_dir=tmp_path)
    assert out["max_gap_min"] is None


def test_median_ticks_per_game(tmp_path):
    rows = ([_row(game_id="g1", ts="2026-07-03T10:%02d:00Z" % i) for i in range(4)] +
            [_row(game_id="g2", ts="2026-07-03T11:%02d:00Z" % i) for i in range(2)])
    _write_day(tmp_path, "mlb", "2026-07-03", rows)
    out = measure_inplay("mlb", "2026-07-03", base_dir=tmp_path)
    assert out["median_ticks_per_game"] == 3.0  # median of [4, 2] -> 3.0


def _full_day_rows(sport_date, games=("g1", "g2", "g3"), with_total=False):
    rows = []
    for h in range(24):
        for g in games:
            rows.append(_row(game_id=g, ts="%sT%02d:00:00Z" % (sport_date, h)))
            if with_total:
                rows.append(_row(game_id=g, market_type="total", prob=0.5, line=8.5,
                                  ts="%sT%02d:00:30Z" % (sport_date, h)))
    return rows


def test_scoreboard_regression_on_rate_collapse(tmp_path):
    _write_day(tmp_path, "mlb", "2026-07-02", _full_day_rows("2026-07-02"))
    _write_day(tmp_path, "mlb", "2026-07-03", [_row(ts="2026-07-03T10:00:00Z")])
    now = datetime(2026, 7, 3, 12, 0, 0, tzinfo=timezone.utc)
    doc = scoreboard_inplay(("mlb",), now=now, base_dir=tmp_path)
    assert doc["by_sport"]["mlb"]["verdict"] == REGRESSION
    assert doc["overall"] == REGRESSION


def test_scoreboard_regression_on_market_type_drop(tmp_path):
    # Yesterday had total/spread rows too; today only moneyline despite live rows.
    _write_day(tmp_path, "mlb", "2026-07-02", _full_day_rows("2026-07-02", with_total=True))
    today_rows = [_row(game_id=g, ts="2026-07-03T%02d:00:00Z" % h)
                  for h in range(6) for g in ("g1", "g2", "g3")]
    _write_day(tmp_path, "mlb", "2026-07-03", today_rows)
    now = datetime(2026, 7, 3, 6, 30, 0, tzinfo=timezone.utc)
    doc = scoreboard_inplay(("mlb",), now=now, base_dir=tmp_path)
    assert doc["by_sport"]["mlb"]["verdict"] == REGRESSION


def test_scoreboard_no_data_when_both_days_empty(tmp_path):
    now = datetime(2026, 7, 3, 12, 0, 0, tzinfo=timezone.utc)
    doc = scoreboard_inplay(("tennis",), now=now, base_dir=tmp_path)
    assert doc["by_sport"]["tennis"]["verdict"] == NO_DATA
    assert doc["overall"] == NO_DATA


def test_scoreboard_green_on_healthy_case(tmp_path):
    _write_day(tmp_path, "mlb", "2026-07-02", _full_day_rows("2026-07-02"))
    today_rows = [_row(game_id=g, ts="2026-07-03T%02d:00:00Z" % h)
                  for h in range(6) for g in ("g1", "g2", "g3")]
    _write_day(tmp_path, "mlb", "2026-07-03", today_rows)
    now = datetime(2026, 7, 3, 6, 30, 0, tzinfo=timezone.utc)
    doc = scoreboard_inplay(("mlb",), now=now, base_dir=tmp_path)
    assert doc["by_sport"]["mlb"]["verdict"] == GREEN
    assert doc["overall"] == GREEN


def test_completeness_count_ratio_with_injected_scoreboard_ids(tmp_path):
    rows = [_row(game_id="g1"), _row(game_id="g2"), _row(game_id="g3")]
    _write_day(tmp_path, "mlb", "2026-07-03", rows)
    out = completeness("mlb", "2026-07-03", scoreboard_game_ids={"e1", "e2", "e3", "e4"},
                        base_dir=tmp_path)
    assert out["n_captured"] == 3
    assert out["n_available"] == 4
    assert out["count_ratio"] == 0.75


def test_completeness_count_ratio_capped_at_one(tmp_path):
    rows = [_row(game_id="g1"), _row(game_id="g2"), _row(game_id="g3")]
    _write_day(tmp_path, "mlb", "2026-07-03", rows)
    out = completeness("mlb", "2026-07-03", scoreboard_game_ids={"e1"}, base_dir=tmp_path)
    assert out["count_ratio"] == 1.0


def test_completeness_omits_when_no_scoreboard_ids_given(tmp_path):
    out = completeness("mlb", "2026-07-03", base_dir=tmp_path)
    assert out["n_available"] is None
    assert out["count_ratio"] is None


def test_write_status_and_load_status_round_trip(tmp_path):
    out_path = tmp_path / "inplay_capture_quality.json"
    doc = {"overall": GREEN, "sports": ["mlb"]}
    ok = write_status(doc, out_path=out_path, now=123.0)
    assert ok is True
    loaded = load_status(path=out_path)
    assert loaded["overall"] == GREEN
    assert loaded["component"] == "m_inplay_capture_quality"
    assert loaded["generated_at"] == 123.0


def test_load_status_missing_file_returns_none(tmp_path):
    assert load_status(path=tmp_path / "nope.json") is None


def test_write_status_never_raises_on_bad_path():
    class _Boom:
        def __truediv__(self, other):
            raise RuntimeError("bad path")
    ok = write_status({"overall": GREEN}, out_path=_Boom())
    assert ok is False


def test_default_sports_includes_wnba_and_npb():
    # golive_hardening_backlog #4: was missing wnba/npb, unlike feed_health.
    assert "wnba" in DEFAULT_SPORTS
    assert "npb" in DEFAULT_SPORTS


def test_measure_tracks_rows_by_provider(tmp_path):
    # golive_hardening_backlog #1: per-provider row floor -- inplay sibling
    # had zero rows_by_provider tracking at all.
    rows = [_row(venue="kalshi"), _row(venue="kalshi"), _row(venue="other")]
    _write_day(tmp_path, "mlb", "2026-07-03", rows)
    out = measure_inplay("mlb", "2026-07-03", base_dir=tmp_path)
    assert out["rows_by_provider"] == {"kalshi": 2, "other": 1}


def test_scoreboard_regression_on_provider_drop(tmp_path):
    # Yesterday kalshi had real coverage; today kalshi produced zero rows
    # despite another (non-expected) venue keeping the aggregate non-empty.
    yest_rows = _full_day_rows("2026-07-02")  # all venue="kalshi" by default
    _write_day(tmp_path, "mlb", "2026-07-02", yest_rows)
    today_rows = [_row(game_id="g1", venue="other", ts="2026-07-03T10:00:00Z")]
    _write_day(tmp_path, "mlb", "2026-07-03", today_rows)
    now = datetime(2026, 7, 3, 12, 0, 0, tzinfo=timezone.utc)
    doc = scoreboard_inplay(("mlb",), now=now, base_dir=tmp_path)
    assert doc["by_sport"]["mlb"]["verdict"] == REGRESSION
    assert "kalshi" in doc["by_sport"]["mlb"]["provider_regression"]


def test_render_is_ascii(tmp_path):
    _write_day(tmp_path, "mlb", "2026-07-03", [_row()])
    now = datetime(2026, 7, 3, 12, 0, 0, tzinfo=timezone.utc)
    doc = scoreboard_inplay(("mlb", "tennis"), now=now, base_dir=tmp_path)
    text = render(doc)
    assert text.encode("ascii")  # raises UnicodeEncodeError if not pure ASCII
    assert "IN-PLAY CAPTURE QUALITY" in text
    assert "OVERALL:" in text
