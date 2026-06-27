"""Per-file test for predict_service.progress_router (W4 serve). NO full pytest."""
from __future__ import annotations

import json
import time

from predict_service import progress_router as pr


def _patch_series(monkeypatch, rows):
    monkeypatch.setattr(pr, "_series", lambda: list(rows))


def test_summary_ok_when_fresh(monkeypatch):
    fresh = {"ts": int(time.time()), "per_sport": {"nba": {"n_tested": 3, "n_ship": 0,
             "n_reject": 3, "n_insufficient": 0, "coverage_pct": 50.0}},
             "engine_enabled": False, "model_static": True,
             "backlog_total": 73, "backlog_remaining": 40}
    _patch_series(monkeypatch, [fresh])
    body = pr.progress_summary()
    assert body["status"] == "ok"
    assert body["model_static"] is True
    assert body["engine_enabled"] is False


def test_stale_never_green_when_old(monkeypatch):
    old = {"ts": int(time.time()) - pr.STALE_AFTER_SEC - 100, "per_sport": {}}
    _patch_series(monkeypatch, [old])
    body = pr.progress_summary()
    assert body["status"] == "stale"   # never a fabricated green
    assert body["engine_enabled"] is False
    assert body["edge_claimed"] is False


def test_stale_when_missing(monkeypatch):
    _patch_series(monkeypatch, [])
    for handler in (pr.progress_summary, pr.progress_coverage, pr.progress_verdicts):
        body = handler()
        assert body["status"] == "stale"


def test_readiness_enabled_false_when_sentinel_absent(monkeypatch):
    _patch_series(monkeypatch, [{"ts": int(time.time()), "engine_enabled": False}])
    body = pr.progress_readiness()
    assert body["ratchet_ready"] is True
    assert body["engine_enabled"] is False
    assert body["label"] == "ready-but-pending"


def test_no_dollar_field_in_any_response(monkeypatch):
    fresh = {"ts": int(time.time()), "per_sport": {"nba": {"n_tested": 1, "n_ship": 0,
             "n_reject": 1, "n_insufficient": 0}}, "engine_enabled": False}
    _patch_series(monkeypatch, [fresh])
    for handler in (pr.progress_summary, pr.progress_coverage, pr.progress_verdicts,
                    pr.progress_readiness, pr.progress_schedule):
        body = handler()
        # No $ as a data KEY (the honest 'no $ field' disclaimer note is excluded).
        assert not any("$" in str(k) for k in (body if isinstance(body, dict) else {}))
        if isinstance(body, dict):
            body = {k: v for k, v in body.items() if k != "note"}
        blob = json.dumps(body, default=str).lower()
        for tok in ("usd", "edge_dollars", "pnl", "roi", "bankroll", "profit"):
            assert tok not in blob, handler.__name__


def test_verdicts_reject_is_success(monkeypatch):
    fresh = {"ts": int(time.time()), "engine_enabled": False, "per_sport": {
        "nba": {"n_tested": 5, "n_ship": 1, "n_reject": 4, "n_insufficient": 0}}}
    _patch_series(monkeypatch, [fresh])
    body = pr.progress_verdicts()
    assert body["reject_is_success"] is True
    assert body["totals"]["reject"] == 4


def test_router_mount_smoke():
    """The router imports + mounts without breaking app boot (smoke import)."""
    from predict_service import extra_mounts

    class _App:
        def __init__(self):
            self.included = []

        def include_router(self, r):
            self.included.append(r)

        def get(self, *a, **k):
            def _d(fn):
                return fn
            return _d

    app = _App()
    extra_mounts.register(app)  # must not raise


if __name__ == "__main__":
    import sys

    class _MP:
        def setattr(self, obj, name, val):
            setattr(obj, name, val)

    mp = _MP()
    for fn in (test_summary_ok_when_fresh, test_stale_never_green_when_old,
               test_stale_when_missing, test_readiness_enabled_false_when_sentinel_absent,
               test_no_dollar_field_in_any_response, test_verdicts_reject_is_success):
        fn(mp)
        print("ok:", fn.__name__)
    test_router_mount_smoke()
    print("ok: test_router_mount_smoke")
    sys.exit(0)
