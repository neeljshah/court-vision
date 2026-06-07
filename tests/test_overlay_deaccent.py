"""Test CV_OVERLAY_DEACCENT gated fix in api/_predictions_overlay.py.

Bug (sweep API_ROUTERS, MEDIUM/LIVE): the overlay join keys are .strip().lower() with NO
accent-strip, while the parquet stores accented nba_api names ('Luka Dončić') and books send
ASCII ('Luka Doncic'). So accented stars get model_projection/edge/rec = None on the live slate
(and are dropped from model_total). Default OFF = byte-identical; ON de-accents both sides.
"""
import pytest

pd = pytest.importorskip("pandas")
from api import _predictions_overlay as ov


def _write(tmp_path, date, name):
    df = pd.DataFrame([{
        "player_name": name, "stat": "pts",
        "q10": 20.0, "q50": 27.39, "q90": 34.0, "sigma": 6.0, "team": "DAL",
    }])
    df.to_parquet(tmp_path / f"predictions_cache_{date}.parquet")


@pytest.fixture()
def _cache(tmp_path, monkeypatch):
    monkeypatch.setattr(ov, "_CACHE_DIR", tmp_path)
    ov._PRED_LOOKUP_CACHE.clear()
    yield tmp_path
    ov._PRED_LOOKUP_CACHE.clear()


def _prop():
    return [{"player": "Luka Doncic", "stat": "pts", "line": 25.5,
             "over_price": -110, "under_price": -110}]


def test_off_misses_accented_star(_cache, monkeypatch):
    monkeypatch.delenv("CV_OVERLAY_DEACCENT", raising=False)
    _write(_cache, "2026-01-01", "Luka Dončić")
    ov._PRED_LOOKUP_CACHE.clear()
    out = ov.overlay_predictions("2026-01-01", _prop())
    assert out[0]["model_projection"] is None  # ASCII book name misses accented parquet key


def test_on_matches_accented_star(_cache, monkeypatch):
    monkeypatch.setenv("CV_OVERLAY_DEACCENT", "1")
    _write(_cache, "2026-01-02", "Luka Dončić")
    ov._PRED_LOOKUP_CACHE.clear()
    out = ov.overlay_predictions("2026-01-02", _prop())
    assert out[0]["model_projection"] == pytest.approx(27.39, abs=1e-6)


def test_on_does_not_break_ascii_names(_cache, monkeypatch):
    monkeypatch.setenv("CV_OVERLAY_DEACCENT", "1")
    _write(_cache, "2026-01-03", "Jayson Tatum")
    ov._PRED_LOOKUP_CACHE.clear()
    out = ov.overlay_predictions("2026-01-03", [{"player": "Jayson Tatum", "stat": "pts",
                                                 "line": 25.5, "over_price": -110, "under_price": -110}])
    assert out[0]["model_projection"] == pytest.approx(27.39, abs=1e-6)
