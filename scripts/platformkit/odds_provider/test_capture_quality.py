"""Per-file tests for capture_quality (NETWORK-FREE -- synthetic jsonl fixtures)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.platformkit.odds_provider.capture_quality import (
    GREEN, NO_DATA, REGRESSION, _provider_drops, load_status, measure, render,
    scoreboard, write_status)


def _row(game_id="g1", book="espn:DraftKings", odds=1.9, ts="2026-07-03T10:00:00+00:00"):
    return {"sport": "mlb", "game_id": game_id, "home": "A", "away": "B",
            "market_type": "moneyline", "side": "home", "line": None, "odds": odds,
            "book": book, "devigged_prob": None, "captured_at": ts,
            "commence_time": None}


def _write_day(base_dir: Path, sport: str, date_str: str, rows):
    d = base_dir / sport
    d.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r) for r in rows]
    (d / ("%s.jsonl" % date_str)).write_text("\n".join(lines) + ("\n" if lines else ""),
                                              encoding="utf-8")


def test_measure_missing_file_returns_zeros_with_no_file_flag(tmp_path):
    out = measure("mlb", "2026-07-03", base_dir=tmp_path)
    assert out["no_file"] is True
    assert out["n_rows"] == 0
    assert out["n_games"] == 0
    assert out["n_venues"] == 0
    assert out["max_gap_min"] is None


def test_measure_parses_real_schema_fields(tmp_path):
    rows = [_row(game_id="g1", book="espn:DraftKings"),
            _row(game_id="g1", book="pinnacle"),
            _row(game_id="g2", book="espn:DraftKings")]
    _write_day(tmp_path, "mlb", "2026-07-03", rows)
    out = measure("mlb", "2026-07-03", base_dir=tmp_path)
    assert out["no_file"] is False
    assert out["n_rows"] == 3
    assert out["n_games"] == 2
    assert out["n_venues"] == 2


def test_measure_corrupt_line_skipped_and_counted(tmp_path):
    d = tmp_path / "mlb"
    d.mkdir(parents=True)
    good = json.dumps(_row())
    (d / "2026-07-03.jsonl").write_text(good + "\n" + "{not json" + "\n", encoding="utf-8")
    out = measure("mlb", "2026-07-03", base_dir=tmp_path)
    assert out["n_rows"] == 1
    assert out["n_corrupt"] == 1


def test_measure_venues_per_game_math(tmp_path):
    rows = [_row(game_id="g1", book="a"), _row(game_id="g1", book="b"),
            _row(game_id="g1", book="c"), _row(game_id="g2", book="a")]
    _write_day(tmp_path, "mlb", "2026-07-03", rows)
    out = measure("mlb", "2026-07-03", base_dir=tmp_path)
    # g1 has 3 distinct venues, g2 has 1 -> mean = 2.0
    assert out["venues_per_game"] == 2.0


def test_measure_tail_share_math(tmp_path):
    # implied prob = 1/odds. odds=10.0 -> 0.10 (tail); odds=2.0 -> 0.50 (not tail);
    # odds=1.111 -> ~0.90 (tail).
    rows = [_row(game_id="g1", odds=10.0), _row(game_id="g1", odds=2.0),
            _row(game_id="g1", odds=1.1111111)]
    _write_day(tmp_path, "mlb", "2026-07-03", rows)
    out = measure("mlb", "2026-07-03", base_dir=tmp_path)
    assert abs(out["tail_share"] - (2.0 / 3.0)) < 1e-6


def test_measure_tail_share_ignores_unpriced_rows(tmp_path):
    bad = _row(odds=None)
    good = _row(odds=10.0)
    _write_day(tmp_path, "mlb", "2026-07-03", [bad, good])
    out = measure("mlb", "2026-07-03", base_dir=tmp_path)
    assert out["tail_share"] == 1.0  # only the priced row counts toward the denominator


def test_measure_max_gap_min(tmp_path):
    rows = [_row(ts="2026-07-03T10:00:00+00:00"),
            _row(ts="2026-07-03T10:05:00+00:00"),
            _row(ts="2026-07-03T10:35:00+00:00")]
    _write_day(tmp_path, "mlb", "2026-07-03", rows)
    out = measure("mlb", "2026-07-03", base_dir=tmp_path)
    assert out["max_gap_min"] == 30.0
    assert out["first_ts"].startswith("2026-07-03T10:00:00")
    assert out["last_ts"].startswith("2026-07-03T10:35:00")


def test_measure_max_gap_min_none_under_two_rows(tmp_path):
    _write_day(tmp_path, "mlb", "2026-07-03", [_row()])
    out = measure("mlb", "2026-07-03", base_dir=tmp_path)
    assert out["max_gap_min"] is None


def test_scoreboard_regression_on_rate_collapse(tmp_path):
    # Yesterday: full day of healthy capture (24h @ many rows/hr, >=3 games).
    yest_rows = []
    for h in range(24):
        for g in ("g1", "g2", "g3"):
            yest_rows.append(_row(game_id=g, book="espn:DraftKings",
                                   ts="2026-07-02T%02d:00:00+00:00" % h))
    _write_day(tmp_path, "mlb", "2026-07-02", yest_rows)
    # Today: only 1 row captured hours into the day -> collapsed rate.
    _write_day(tmp_path, "mlb", "2026-07-03", [_row(ts="2026-07-03T10:00:00+00:00")])
    now = datetime(2026, 7, 3, 12, 0, 0, tzinfo=timezone.utc)
    doc = scoreboard(("mlb",), now=now, base_dir=tmp_path)
    assert doc["by_sport"]["mlb"]["verdict"] == REGRESSION
    assert doc["overall"] == REGRESSION


def test_scoreboard_regression_on_venue_drop(tmp_path):
    yest_rows = [_row(game_id="g1", book=b, ts="2026-07-02T10:00:00+00:00")
                 for b in ("a", "b", "c", "d")]
    yest_rows += [_row(game_id="g2", book="a", ts="2026-07-02T11:00:00+00:00"),
                  _row(game_id="g3", book="b", ts="2026-07-02T12:00:00+00:00")]
    _write_day(tmp_path, "mlb", "2026-07-02", yest_rows)
    # Today: same-ish row count but only 1 distinct venue -> 3-venue drop.
    today_rows = [_row(game_id="g1", book="a", ts="2026-07-03T00:30:00+00:00")
                  for _ in range(20)]
    _write_day(tmp_path, "mlb", "2026-07-03", today_rows)
    now = datetime(2026, 7, 3, 1, 0, 0, tzinfo=timezone.utc)
    doc = scoreboard(("mlb",), now=now, base_dir=tmp_path)
    assert doc["by_sport"]["mlb"]["verdict"] == REGRESSION


def test_scoreboard_no_data_when_both_days_empty(tmp_path):
    now = datetime(2026, 7, 3, 12, 0, 0, tzinfo=timezone.utc)
    doc = scoreboard(("tennis",), now=now, base_dir=tmp_path)
    assert doc["by_sport"]["tennis"]["verdict"] == NO_DATA
    assert doc["overall"] == NO_DATA


def test_scoreboard_green_on_healthy_case(tmp_path):
    yest_rows = []
    for h in range(24):
        for g in ("g1", "g2", "g3"):
            yest_rows.append(_row(game_id=g, book="espn:DraftKings",
                                   ts="2026-07-02T%02d:00:00+00:00" % h))
    _write_day(tmp_path, "mlb", "2026-07-02", yest_rows)
    # Today: comparable rate so far (proportional to elapsed hours), same venues.
    today_rows = []
    for h in range(6):
        for g in ("g1", "g2", "g3"):
            today_rows.append(_row(game_id=g, book="espn:DraftKings",
                                    ts="2026-07-03T%02d:00:00+00:00" % h))
    _write_day(tmp_path, "mlb", "2026-07-03", today_rows)
    now = datetime(2026, 7, 3, 6, 30, 0, tzinfo=timezone.utc)
    doc = scoreboard(("mlb",), now=now, base_dir=tmp_path)
    assert doc["by_sport"]["mlb"]["verdict"] == GREEN
    assert doc["overall"] == GREEN


def test_write_status_and_load_status_round_trip(tmp_path):
    out_path = tmp_path / "capture_quality.json"
    doc = {"overall": GREEN, "sports": ["mlb"]}
    ok = write_status(doc, out_path=out_path, now=123.0)
    assert ok is True
    loaded = load_status(path=out_path)
    assert loaded["overall"] == GREEN
    assert loaded["component"] == "m_capture_quality"
    assert loaded["generated_at"] == 123.0


def test_load_status_missing_file_returns_none(tmp_path):
    assert load_status(path=tmp_path / "nope.json") is None


def test_write_status_never_raises_on_bad_path():
    class _Boom:
        def __truediv__(self, other):
            raise RuntimeError("bad path")
    ok = write_status({"overall": GREEN}, out_path=_Boom())
    assert ok is False


def test_render_is_ascii(tmp_path):
    _write_day(tmp_path, "mlb", "2026-07-03", [_row()])
    now = datetime(2026, 7, 3, 12, 0, 0, tzinfo=timezone.utc)
    doc = scoreboard(("mlb", "tennis"), now=now, base_dir=tmp_path)
    text = render(doc)
    assert text.encode("ascii")  # raises UnicodeEncodeError if not pure ASCII
    assert "CAPTURE QUALITY" in text
    assert "OVERALL:" in text


# ---------------------------------------------------------------------------
# Per-provider row-drop detection -- go-live defect B
# ---------------------------------------------------------------------------

def test_measure_buckets_rows_by_provider(tmp_path):
    rows = [_row(game_id="g1", book="espn:DraftKings"),
            _row(game_id="g1", book="pinnacle"),
            _row(game_id="g2", book="espn:FanDuel")]
    _write_day(tmp_path, "mlb", "2026-07-03", rows)
    out = measure("mlb", "2026-07-03", base_dir=tmp_path)
    # "espn:DraftKings" and "espn:FanDuel" both bucket under provider "espn".
    assert out["rows_by_provider"] == {"espn": 2, "pinnacle": 1}


def test_provider_drops_flags_a_provider_that_went_to_zero():
    yesterday = {"rows_by_provider": {"espn": 50, "pinnacle": 20}}
    today = {"rows_by_provider": {"espn": 48}}  # pinnacle absent entirely
    assert _provider_drops(today, yesterday) == ["pinnacle"]


def test_provider_drops_ignores_below_signal_threshold():
    # pinnacle had only 2 rows yesterday (< _MIN_PROVIDER_ROWS_FOR_SIGNAL=5) --
    # too little coverage to call a real drop.
    yesterday = {"rows_by_provider": {"espn": 50, "pinnacle": 2}}
    today = {"rows_by_provider": {"espn": 48}}
    assert _provider_drops(today, yesterday) == []


def test_provider_drops_ignores_provider_still_present():
    yesterday = {"rows_by_provider": {"espn": 50, "pinnacle": 20}}
    today = {"rows_by_provider": {"espn": 48, "pinnacle": 1}}  # still >0, not a drop
    assert _provider_drops(today, yesterday) == []


def test_provider_drops_filtered_by_expected_set():
    # A malformed/one-off "book" label that vanishes is never flagged when an
    # expected-provider allowlist is supplied and it is not on that list.
    yesterday = {"rows_by_provider": {"espn": 50, "weird_test_label": 10}}
    today = {"rows_by_provider": {"espn": 48}}
    assert _provider_drops(today, yesterday, expected={"espn", "pinnacle"}) == []
    assert _provider_drops(today, yesterday, expected=None) == ["weird_test_label"]


def test_scoreboard_regression_on_masked_provider_drop(tmp_path):
    """THE masked-aggregate case (module docstring PER-PROVIDER GAP): pinnacle
    (a single-venue provider) goes fully silent today while espn keeps the
    sport-level aggregate (rate, venue count) healthy enough that the OLD
    checks alone would stay GREEN -- only losing 1 of 2 venues (below the
    venue_drop>=2 threshold) at an unchanged aggregate rate. The new
    per-provider check must still catch it and name "pinnacle"."""
    yest_rows = []
    for h in range(24):
        for g in ("g1", "g2", "g3"):
            ts = "2026-07-02T%02d:00:00+00:00" % h
            yest_rows.append(_row(game_id=g, book="espn:DraftKings", ts=ts))
            yest_rows.append(_row(game_id=g, book="pinnacle", ts=ts))
    _write_day(tmp_path, "mlb", "2026-07-02", yest_rows)
    # Yesterday's combined hourly rate = 6 rows/hr (3 games x 2 venues).
    # Today: pinnacle produces ZERO rows; espn alone matches that same 6/hr
    # rate (2 espn rows/game/hr) so the rate-collapse check does NOT fire.
    today_rows = []
    for h in range(6):
        for g in ("g1", "g2", "g3"):
            ts = "2026-07-03T%02d:00:00+00:00" % h
            today_rows.append(_row(game_id=g, book="espn:DraftKings", ts=ts))
            today_rows.append(_row(game_id=g, book="espn:DraftKings", ts=ts))
    _write_day(tmp_path, "mlb", "2026-07-03", today_rows)
    now = datetime(2026, 7, 3, 6, 30, 0, tzinfo=timezone.utc)
    doc = scoreboard(("mlb",), now=now, base_dir=tmp_path)
    # Prove the OLD signals alone stay non-collapsing (the masking premise):
    # only 1 venue lost (2 -> 1, below the >=2 drop threshold).
    assert doc["by_sport"]["mlb"]["yesterday"]["n_venues"] == 2
    assert doc["by_sport"]["mlb"]["today"]["n_venues"] == 1
    # The new provider-drop check still fires and names the provider.
    assert doc["by_sport"]["mlb"]["verdict"] == REGRESSION
    assert doc["by_sport"]["mlb"]["provider_regression"] == ["pinnacle"]
    assert doc["overall"] == REGRESSION


def test_scoreboard_provider_regression_empty_on_healthy_case(tmp_path):
    # Sanity: the healthy-case fixture (both providers keep capturing) never
    # names a provider regression.
    yest_rows = []
    for h in range(24):
        for g in ("g1", "g2", "g3"):
            yest_rows.append(_row(game_id=g, book="espn:DraftKings",
                                   ts="2026-07-02T%02d:00:00+00:00" % h))
    _write_day(tmp_path, "mlb", "2026-07-02", yest_rows)
    today_rows = []
    for h in range(6):
        for g in ("g1", "g2", "g3"):
            today_rows.append(_row(game_id=g, book="espn:DraftKings",
                                    ts="2026-07-03T%02d:00:00+00:00" % h))
    _write_day(tmp_path, "mlb", "2026-07-03", today_rows)
    now = datetime(2026, 7, 3, 6, 30, 0, tzinfo=timezone.utc)
    doc = scoreboard(("mlb",), now=now, base_dir=tmp_path)
    assert doc["by_sport"]["mlb"]["verdict"] == GREEN
    assert doc["by_sport"]["mlb"]["provider_regression"] == []
