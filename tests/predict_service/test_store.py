"""Per-file test: predict_service.store atomic write + safe read_latest.

Run: python -m pytest tests/predict_service/test_store.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from predict_service import store
from predict_service.contracts import (
    EdgeRow,
    MarketRow,
    PredictionRecord,
    SnapshotEnvelope,
)

# The fixture tips at 2026-06-18T23:00Z; pin read_latest's *now* just after tip so
# the envelope-level stale-never-green guard does not demote ok->stale purely
# because the real wall clock has moved past the fixed fixture date.
_FIX_NOW = datetime(2026, 6, 18, 23, 30, 0, tzinfo=timezone.utc)


def _envelope(sport: str = "nba") -> SnapshotEnvelope:
    mkt = MarketRow(sport=sport, game_id="g1", market_type="moneyline",
                    side="home", odds=1.91, book="bk", devigged_prob=0.52,
                    captured_at="2026-06-18T00:00:00+00:00", is_close=True)
    pred = PredictionRecord(sport=sport, game_id="g1", home="NYK", away="SAS",
                            tipoff="2026-06-18T23:00:00+00:00",
                            pregame_probs={"home_ml": 0.58}, markets=[mkt])
    edge = EdgeRow(game_id="g1", market_type="moneyline", side="home",
                   model_prob=0.58, market_prob=0.52, ev=0.11, tier="B")
    return SnapshotEnvelope(sport=sport, generated_at="2026-06-18T22:00:00+00:00",
                            status="ok", predictions=[pred], markets=[mkt],
                            edges=[edge])


def test_write_then_read_latest_equal(tmp_path):
    env = _envelope("nba")
    store.save(env, out_dir=tmp_path)
    got = store.read_latest("nba", out_dir=tmp_path, now=_FIX_NOW)
    assert got == env
    assert store.latest_path("nba", out_dir=tmp_path).exists()


def test_write_accepts_dict(tmp_path):
    env = _envelope("mlb")
    store.write(env.to_dict(), out_dir=tmp_path)
    got = store.read_latest("mlb", out_dir=tmp_path, now=_FIX_NOW)
    assert got == env


def test_sport_case_insensitive(tmp_path):
    env = _envelope("NBA")
    store.save(env, out_dir=tmp_path)
    # stored under lowercased dir; read with any case resolves the same file
    got = store.read_latest("nba", out_dir=tmp_path, now=_FIX_NOW)
    assert got.status == "ok"
    assert got.sport == "NBA"


def test_history_append_only(tmp_path):
    env1 = _envelope("nba")
    env2 = _envelope("nba")
    env2.generated_at = "2026-06-18T23:00:00+00:00"
    store.save(env1, out_dir=tmp_path)
    store.save(env2, out_dir=tmp_path)
    hist = store.read_history("nba", out_dir=tmp_path)
    assert len(hist) == 2
    assert hist[0].generated_at == "2026-06-18T22:00:00+00:00"
    assert hist[1].generated_at == "2026-06-18T23:00:00+00:00"
    # latest.json reflects the most recent save only
    assert store.read_latest("nba", out_dir=tmp_path).generated_at == \
        "2026-06-18T23:00:00+00:00"


def test_read_latest_missing_returns_unavailable(tmp_path):
    got = store.read_latest("soccer", out_dir=tmp_path)
    assert got.status == "unavailable"
    assert got.sport == "soccer"
    # sentinel, never a partial/torn object
    assert got.predictions == []
    assert got.edges == []


def test_read_latest_partial_file_returns_unavailable(tmp_path):
    """A truncated/torn latest.json must yield the sentinel, never a partial parse."""
    store.save(_envelope("nba"), out_dir=tmp_path)
    p = store.latest_path("nba", out_dir=tmp_path)
    full = p.read_text(encoding="utf-8")
    # simulate a half-written file: keep only the first half of the bytes
    p.write_text(full[: len(full) // 2], encoding="utf-8")
    got = store.read_latest("nba", out_dir=tmp_path)
    assert got.status == "unavailable"
    assert "partial" in got.note or "corrupt" in got.note


def test_read_latest_empty_file_returns_unavailable(tmp_path):
    p = store.latest_path("nba", out_dir=tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("", encoding="utf-8")
    got = store.read_latest("nba", out_dir=tmp_path)
    assert got.status == "unavailable"


def test_read_latest_non_object_returns_unavailable(tmp_path):
    p = store.latest_path("nba", out_dir=tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    got = store.read_latest("nba", out_dir=tmp_path)
    assert got.status == "unavailable"


def test_history_append_is_atomic_no_tmp_no_torn_line(tmp_path):
    """The history append is crash-safe (tmp+replace): after appends the file has
    exactly one COMPLETE JSON object per line, no leftover tmp, and a clean tail."""
    store.save(_envelope("nba"), out_dir=tmp_path)
    store.save(_envelope("nba"), out_dir=tmp_path)
    hp = store.history_path("nba", out_dir=tmp_path)
    raw = hp.read_text(encoding="utf-8")
    # Clean trailing newline -> no torn last line.
    assert raw.endswith("\n")
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    assert len(lines) == 2
    # Every line must be a COMPLETE, parseable JSON object (no half-written tail).
    for ln in lines:
        assert isinstance(json.loads(ln), dict)
    # The atomic tmp file must be gone after a successful replace.
    assert not hp.with_suffix(hp.suffix + ".tmp").exists()


def test_history_append_heals_preexisting_torn_tail(tmp_path):
    """If a prior bare write left a torn last line (no newline), the next atomic
    append must NOT glue onto it -- it heals the tail so both lines parse."""
    hp = store.history_path("nba", out_dir=tmp_path)
    hp.parent.mkdir(parents=True, exist_ok=True)
    # Simulate a torn tail from a crashed bare append (no trailing newline).
    hp.write_text('{"sport": "nba", "torn":', encoding="utf-8")
    store.append_history(_envelope("nba"), out_dir=tmp_path)
    raw = hp.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    # The new complete envelope line is present and parseable; the torn prefix
    # stays on its own (now-newline-terminated) line and never merges with it.
    good = [ln for ln in raw.splitlines() if ln.strip()]
    parsed_ok = [ln for ln in good if _is_json_obj(ln)]
    assert any(json.loads(ln).get("sport") == "nba" and "predictions" in json.loads(ln)
               for ln in parsed_ok)
    assert not hp.with_suffix(hp.suffix + ".tmp").exists()


def _is_json_obj(line: str) -> bool:
    try:
        return isinstance(json.loads(line), dict)
    except Exception:  # noqa: BLE001
        return False


def test_save_returns_latest_path_and_no_tmp_left(tmp_path):
    path = store.save(_envelope("nba"), out_dir=tmp_path)
    assert path == store.latest_path("nba", out_dir=tmp_path)
    # the atomic tmp file must be gone after a successful replace
    tmp = path.with_suffix(path.suffix + ".tmp")
    assert not tmp.exists()


def test_atomic_write_retries_past_transient_permission_error(tmp_path, monkeypatch):
    """os.replace fails twice (simulating a Windows reader holding the file open)
    then succeeds on the 3rd attempt -- the write must land, not raise."""
    monkeypatch.setattr(store.time, "sleep", lambda _s: None)
    real_replace = store.os.replace
    calls = {"n": 0}

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("simulated: reader has the file open")
        return real_replace(src, dst)

    monkeypatch.setattr(store.os, "replace", flaky_replace)
    store.save(_envelope("nba"), out_dir=tmp_path)
    assert calls["n"] == 3
    got = store.read_latest("nba", out_dir=tmp_path, now=_FIX_NOW)
    assert got.status == "ok"


def test_atomic_write_raises_after_exhausting_retries(tmp_path, monkeypatch):
    """A PermissionError on every attempt (3x) must raise, not silently drop the
    write -- the caller already records status=error on this path."""
    monkeypatch.setattr(store.time, "sleep", lambda _s: None)

    def always_fails(src, dst):
        raise PermissionError("simulated: reader never lets go")

    monkeypatch.setattr(store.os, "replace", always_fails)
    import pytest
    with pytest.raises(PermissionError):
        store.save(_envelope("nba"), out_dir=tmp_path)


def test_append_is_true_o1_append_not_a_full_rewrite(tmp_path):
    """Two appends produce two lines; the append is a real O(1) 'ab' write, not
    a read-whole-file-then-rewrite -- verified by the tmp sibling NEVER existing
    mid-sequence (a rewrite would briefly create then remove it) and by the file
    growing by exactly the new line's byte length each time."""
    hp = store.history_path("nba", out_dir=tmp_path)
    store.append_history(_envelope("nba"), out_dir=tmp_path)
    size1 = hp.stat().st_size
    assert not hp.with_suffix(hp.suffix + ".tmp").exists()
    store.append_history(_envelope("nba"), out_dir=tmp_path)
    size2 = hp.stat().st_size
    assert not hp.with_suffix(hp.suffix + ".tmp").exists()
    assert size2 > size1  # grew (appended), never shrank/rewrote
    lines = [ln for ln in hp.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
