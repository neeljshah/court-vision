"""Per-file tests for label_finals_refresh (LANE 3 bounded finals-staleness
guard). All I/O is via tmp_path parquets + injected fetch_fn -- no network, no
real repo parquets touched.

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autonomy/test_label_finals_refresh.py -q
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from scripts.platformkit.autonomy.label_finals_refresh import (
    RefreshSpec,
    missing_dates,
    refresh_all,
    refresh_one,
)


def _write_parquet(path, dates):
    df = pd.DataFrame({"event_id": [str(i) for i in range(len(dates))], "date": dates})
    df["date"] = pd.to_datetime(df["date"])
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


# --------------------------------------------------------------------------- #
# missing_dates: the bounded-refresh computation
# --------------------------------------------------------------------------- #
def test_missing_dates_bootstraps_when_parquet_absent(tmp_path):
    spec = RefreshSpec(name="x", out_path=tmp_path / "nope.parquet",
                       fetch_fn=lambda dates, out_path: None, bootstrap_days=3)
    got = missing_dates(spec, today=dt.date(2026, 7, 3))
    assert got == ["20260701", "20260702", "20260703"]


def test_missing_dates_computes_gap_since_max_date(tmp_path):
    p = tmp_path / "finals.parquet"
    _write_parquet(p, ["2026-06-28"])
    spec = RefreshSpec(name="x", out_path=p, fetch_fn=lambda dates, out_path: None)
    got = missing_dates(spec, today=dt.date(2026, 7, 3))
    assert got == ["20260629", "20260630", "20260701", "20260702", "20260703"]


def test_missing_dates_empty_when_already_current(tmp_path):
    p = tmp_path / "finals.parquet"
    _write_parquet(p, ["2026-07-03"])
    spec = RefreshSpec(name="x", out_path=p, fetch_fn=lambda dates, out_path: None)
    got = missing_dates(spec, today=dt.date(2026, 7, 3))
    assert got == []


def test_missing_dates_caps_at_max_dates_per_tick(tmp_path):
    p = tmp_path / "finals.parquet"
    _write_parquet(p, ["2026-06-22"])  # a real 6-day-gap-shaped scenario
    spec = RefreshSpec(name="x", out_path=p, fetch_fn=lambda dates, out_path: None,
                       max_dates_per_tick=2)
    got = missing_dates(spec, today=dt.date(2026, 7, 3))
    assert got == ["20260623", "20260624"]  # oldest-first, capped, forward progress


def test_missing_dates_unreadable_parquet_falls_back_to_bootstrap(tmp_path):
    p = tmp_path / "garbage.parquet"
    p.write_bytes(b"not a real parquet file")
    spec = RefreshSpec(name="x", out_path=p, fetch_fn=lambda dates, out_path: None,
                       bootstrap_days=2)
    got = missing_dates(spec, today=dt.date(2026, 7, 3))
    assert got == ["20260702", "20260703"]


# --------------------------------------------------------------------------- #
# refresh_one: failure isolation
# --------------------------------------------------------------------------- #
def test_refresh_one_calls_fetch_fn_with_missing_dates(tmp_path):
    p = tmp_path / "finals.parquet"
    _write_parquet(p, ["2026-07-01"])
    calls = {}

    def fake_fetch(dates, out_path):
        calls["dates"] = dates
        calls["out_path"] = out_path

    spec = RefreshSpec(name="x", out_path=p, fetch_fn=fake_fetch)
    res = refresh_one(spec, today=dt.date(2026, 7, 3))
    assert calls["dates"] == ["20260702", "20260703"]
    assert calls["out_path"] == p
    assert res["n_fetched"] == 2 and res["error"] is None


def test_refresh_one_noop_when_nothing_missing_does_not_call_fetch(tmp_path):
    p = tmp_path / "finals.parquet"
    _write_parquet(p, ["2026-07-03"])
    called = {"n": 0}

    def fake_fetch(dates, out_path):
        called["n"] += 1

    spec = RefreshSpec(name="x", out_path=p, fetch_fn=fake_fetch)
    res = refresh_one(spec, today=dt.date(2026, 7, 3))
    assert called["n"] == 0
    assert res == {"name": "x", "fetched": [], "n_fetched": 0, "error": None}


def test_refresh_one_isolates_fetch_exception_never_raises(tmp_path):
    p = tmp_path / "finals.parquet"
    _write_parquet(p, ["2026-07-01"])

    def boom(dates, out_path):
        raise RuntimeError("network hiccup")

    spec = RefreshSpec(name="x", out_path=p, fetch_fn=boom)
    res = refresh_one(spec, today=dt.date(2026, 7, 3))  # must not raise
    assert res["n_fetched"] == 0
    assert res["fetched"] == []
    assert "network hiccup" in res["error"]


def test_refresh_one_isolates_missing_dates_exception_never_raises(tmp_path, monkeypatch):
    import scripts.platformkit.autonomy.label_finals_refresh as mod

    def boom_missing_dates(spec, today=None):
        raise RuntimeError("bad clock")

    monkeypatch.setattr(mod, "missing_dates", boom_missing_dates)
    spec = RefreshSpec(name="x", out_path=tmp_path / "y.parquet",
                       fetch_fn=lambda dates, out_path: None)
    res = mod.refresh_one(spec)
    assert res["n_fetched"] == 0
    assert "bad clock" in res["error"]


# --------------------------------------------------------------------------- #
# refresh_all: per-spec isolation across multiple specs
# --------------------------------------------------------------------------- #
def test_refresh_all_isolates_one_failing_spec_from_others(tmp_path):
    p_ok = tmp_path / "ok.parquet"
    _write_parquet(p_ok, ["2026-07-01"])
    p_bad = tmp_path / "bad.parquet"
    _write_parquet(p_bad, ["2026-07-01"])

    def fetch_ok(dates, out_path):
        pass

    def fetch_bad(dates, out_path):
        raise RuntimeError("boom")

    specs = [
        RefreshSpec(name="ok_spec", out_path=p_ok, fetch_fn=fetch_ok),
        RefreshSpec(name="bad_spec", out_path=p_bad, fetch_fn=fetch_bad),
    ]
    out = refresh_all(specs, today=dt.date(2026, 7, 3))
    assert out["ok_spec"]["error"] is None
    assert out["ok_spec"]["n_fetched"] == 2
    assert out["bad_spec"]["error"] is not None
    assert out["bad_spec"]["n_fetched"] == 0


def test_refresh_all_default_specs_shape():
    from scripts.platformkit.autonomy.label_finals_refresh import SPECS
    names = {s.name for s in SPECS}
    assert {"soccer_intl_finals", "mlb_espn_boxscores", "wnba_espn_scoreboard"} <= names
    for s in SPECS:
        assert s.max_dates_per_tick > 0
        assert callable(s.fetch_fn)


def test_refresh_all_never_raises_with_empty_specs_list():
    assert refresh_all([]) == {}
