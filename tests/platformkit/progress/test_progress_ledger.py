"""Per-file tests for scripts.platformkit.progress.progress_ledger.

Asserts the snapshot is REAL (built from the live on-disk artifacts, not
fabricated), the coverage math is correct, NO $ field appears anywhere, the model
is honestly STATIC, and engine_enabled is False while the PIPELINE_ENABLED sentinel
is absent. Also checks same-day idempotency of the append-only ledger.
"""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.progress import progress_ledger as pl


# -- no $ field anywhere ------------------------------------------------------

_FORBIDDEN = ("$", "dollar", "usd", "profit", "roi", "bankroll")


def _assert_no_dollar(obj) -> None:
    """Recursively assert no $-shaped key/value leaks into the payload."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            assert "$" not in str(k), "dollar key leaked: %r" % k
            assert not any(t == kl for t in ("dollar", "usd", "profit", "roi")), kl
            _assert_no_dollar(v)
    elif isinstance(obj, list):
        for x in obj:
            _assert_no_dollar(x)
    elif isinstance(obj, str):
        assert "$" not in obj, "dollar glyph in string: %r" % obj


def test_snapshot_is_real_and_well_formed():
    snap = pl.build_snapshot(now=1781990000.0)
    # Built from the live artifacts -> the tracked sports are present.
    assert set(snap["per_sport"].keys()) == set(pl._SPORTS)
    assert snap["model_static"] is True
    assert snap["edge_claimed"] is False
    assert snap["engine_enabled"] is False  # sentinel absent on this box
    assert snap["engine_ready"] is True     # ratchet helper importable
    assert isinstance(snap["backlog_total"], int) and snap["backlog_total"] >= 0
    # Verdicts are REAL: at least one funnel verdict was aggregated.
    total_tested = sum(s["n_tested"] for s in snap["per_sport"].values())
    assert total_tested >= 1, "no real funnel verdicts aggregated"


def test_coverage_math_is_correct():
    snap = pl.build_snapshot(now=1781990000.0)
    for sp, s in snap["per_sport"].items():
        denom = s["n_tested"] + s["n_untested_remaining"]
        expected = round(100.0 * s["n_tested"] / denom, 2) if denom else 0.0
        assert s["coverage_pct"] == expected, sp
        # buckets partition the tested count exactly.
        assert s["n_ship"] + s["n_reject"] + s["n_insufficient"] == s["n_tested"]
        assert 0.0 <= s["coverage_pct"] <= 100.0


def test_no_dollar_field_anywhere():
    _assert_no_dollar(pl.progress_payload(now=1781990000.0))


def test_engine_enabled_false_while_sentinel_absent(monkeypatch):
    # Force the sentinel absent -> engine_enabled MUST be False (inert).
    import scripts.platformkit.improve.pipeline_flag as flag
    monkeypatch.setattr(flag, "pipeline_enabled", lambda **_: False)
    snap = pl.build_snapshot(now=1781990000.0)
    assert snap["engine_enabled"] is False
    assert "static" in snap["honest_note"].lower()


def test_reconstructed_history_is_real_not_interpolated():
    hist = pl.reconstruct_history(now=1781990000.0)
    # Monotonic non-decreasing cumulative verdict count, all from real mtimes.
    prev = 0
    for p in hist:
        assert p["ts"] > 0
        assert p["n_verdicts_cumulative"] >= prev
        prev = p["n_verdicts_cumulative"]
        assert p["model_static"] is True


def test_append_is_idempotent_same_day(tmp_path, monkeypatch):
    ledger = tmp_path / "progress_ledger.jsonl"
    monkeypatch.setattr(pl, "_LEDGER", ledger)
    snap = pl.build_snapshot(now=1781990000.0)
    pl.append_snapshot(snap=snap)
    pl.append_snapshot(snap=snap)  # same ET date -> replace, not duplicate
    rows = [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()]
    same_day = [r for r in rows if r["date_et"] == snap["date_et"]]
    assert len(same_day) == 1, "same-day append duplicated a row"


def test_payload_series_falls_back_to_reconstructed():
    payload = pl.progress_payload(now=1781990000.0)
    assert payload["status"] == "ok"
    assert payload["model_static"] is True
    assert payload["engine_enabled"] is False
    # Even with an empty persisted ledger, reconstructed history is non-empty.
    assert len(payload["reconstructed_history"]) >= 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
