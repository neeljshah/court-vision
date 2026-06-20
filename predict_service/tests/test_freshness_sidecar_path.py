"""predict_service.tests.test_freshness_sidecar_path -- per-file test for the
freshness_sidecar path-resolution fix (be-freshness-path, iter2 P1).

Acceptance criteria (all must be GREEN):
  P1. env PREDICT_SERVICE_FRESHNESS_DIR set -> _sidecar_root() returns that value.
  P2. env unset -> _sidecar_root() does NOT return '.'; returns a repo-relative path.
  P3. repo-relative default contains 'inplay_history' or 'predict_service' (known dirs).
  P4. fresh sidecar fixture at resolved path -> feed_status ok=True, status='fresh'.
  P5. missing sidecar dir -> feed_status ok=False, status='missing'.
  P6. old source_ts (>max_age_sec) -> feed_status ok=False, status='stale'.
         stale-never-green: old sidecar NEVER reads ok=True.
  P7. rollup over [fresh, stale] sports -> ok=False, n_fresh=1, n_stale=1,
         status NOT 'ok' (monotone-DOWN: the stale member degrades the parent).
  P8. rollup over [fresh, fresh] -> ok=True (monotone-DOWN: all-fresh only).
  P9. No $ field in feed_status or feed_rollup output.
  P10. feed_status / feed_rollup NEVER raises on any input (garbage-in safe).
  P11. rollup over empty sports list -> ok=False (absence never asserted green).

Run (per-file only -- never run the full suite, it freezes the box)::
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/tests/test_freshness_sidecar_path.py -q
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

# Ensure repo root is on sys.path so imports resolve without an install.
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Import after path-fix.
import predict_service.freshness_sidecar as _fs  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts_ago(seconds: float) -> str:
    """ISO-8601 UTC timestamp *seconds* seconds in the past."""
    dt = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_sidecar(sport_dir: Path, source_ts: str) -> None:
    """Write a minimal _freshness.json sidecar under *sport_dir*."""
    sport_dir.mkdir(parents=True, exist_ok=True)
    payload = {"source_as_of": source_ts, "sport": sport_dir.name}
    (sport_dir / "_freshness.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _has_dollar_key(obj: Any) -> bool:
    """Recursively check for any key containing '$' (no $ P&L fields allowed)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if "$" in str(k):
                return True
            if _has_dollar_key(v):
                return True
    if isinstance(obj, list):
        return any(_has_dollar_key(i) for i in obj)
    return False


# ---------------------------------------------------------------------------
# P1: env override respected
# ---------------------------------------------------------------------------

def test_p1_env_override_respected(tmp_path, monkeypatch):
    """PREDICT_SERVICE_FRESHNESS_DIR in env -> _sidecar_root() returns that exact path."""
    target = str(tmp_path / "custom_freshness")
    monkeypatch.setenv("PREDICT_SERVICE_FRESHNESS_DIR", target)
    monkeypatch.delenv("PREDICT_SERVICE_STORE_DIR", raising=False)
    # Reload to pick up env changes (module-level cache is in __file__, not env).
    root = _fs._sidecar_root()
    assert root == target, (
        "P1: env PREDICT_SERVICE_FRESHNESS_DIR must override default; got %r" % root
    )


# ---------------------------------------------------------------------------
# P2: env unset -> NOT '.'
# ---------------------------------------------------------------------------

def test_p2_no_env_does_not_return_dot(monkeypatch):
    """Without any env var, _sidecar_root() must not return '.'."""
    monkeypatch.delenv("PREDICT_SERVICE_FRESHNESS_DIR", raising=False)
    monkeypatch.delenv("PREDICT_SERVICE_STORE_DIR", raising=False)
    root = _fs._sidecar_root()
    assert root != ".", (
        "P2: _sidecar_root() must not return '.' when env is unset; got %r" % root
    )
    assert os.path.isabs(root), (
        "P2: repo-relative default must be an absolute path; got %r" % root
    )


# ---------------------------------------------------------------------------
# P3: repo-relative default points into a known subdir
# ---------------------------------------------------------------------------

def test_p3_repo_relative_default_known_dir(monkeypatch):
    """Default path should contain 'inplay_history' or 'predict_service' (known dirs)."""
    monkeypatch.delenv("PREDICT_SERVICE_FRESHNESS_DIR", raising=False)
    monkeypatch.delenv("PREDICT_SERVICE_STORE_DIR", raising=False)
    root = _fs._sidecar_root()
    known = ("inplay_history", "predict_service")
    assert any(k in root for k in known), (
        "P3: repo-relative default should contain one of %s; got %r" % (known, root)
    )


# ---------------------------------------------------------------------------
# P4: fresh sidecar -> ok=True, status='fresh'
# ---------------------------------------------------------------------------

def test_p4_fresh_sidecar_reads_fresh(tmp_path, monkeypatch):
    """A sidecar with a recent source_ts at the resolved path must give ok=True."""
    monkeypatch.setenv("PREDICT_SERVICE_FRESHNESS_DIR", str(tmp_path))
    monkeypatch.delenv("PREDICT_SERVICE_STORE_DIR", raising=False)
    # Write a fresh sidecar (30 seconds old, well within default 900s max_age).
    _write_sidecar(tmp_path / "nba", _ts_ago(30))
    result = _fs.feed_status("nba")
    assert result["ok"] is True, (
        "P4: fresh sidecar must give ok=True; got %r" % result
    )
    assert result["status"] == "fresh", (
        "P4: fresh sidecar must give status='fresh'; got %r" % result
    )
    assert result["stale"] is False, "P4: stale must be False when ok=True"
    assert result["fresh"] is True, "P4: fresh must be True when ok=True"


# ---------------------------------------------------------------------------
# P5: missing sidecar -> ok=False, status='missing'
# ---------------------------------------------------------------------------

def test_p5_missing_sidecar_reads_missing(tmp_path, monkeypatch):
    """A sport dir with no _freshness.json must return ok=False status='missing'."""
    monkeypatch.setenv("PREDICT_SERVICE_FRESHNESS_DIR", str(tmp_path))
    monkeypatch.delenv("PREDICT_SERVICE_STORE_DIR", raising=False)
    # Do NOT create the sport dir or its sidecar.
    result = _fs.feed_status("tennis")
    assert result["ok"] is False, (
        "P5: missing sidecar must give ok=False; got %r" % result
    )
    assert result["status"] == "missing", (
        "P5: missing sidecar must give status='missing'; got %r" % result
    )
    assert result["stale"] is True, "P5: stale must be True when ok=False"


# ---------------------------------------------------------------------------
# P6: old source_ts -> stale, NEVER ok=True (stale-never-green)
# ---------------------------------------------------------------------------

def test_p6_old_sidecar_reads_stale_never_green(tmp_path, monkeypatch):
    """A sidecar with source_ts older than max_age_sec must read stale, never ok=True."""
    monkeypatch.setenv("PREDICT_SERVICE_FRESHNESS_DIR", str(tmp_path))
    monkeypatch.delenv("PREDICT_SERVICE_STORE_DIR", raising=False)
    # Write sidecar with source_ts 7200s old (2h); use tight max_age_sec=60.
    _write_sidecar(tmp_path / "mlb", _ts_ago(7200))
    result = _fs.feed_status("mlb", max_age_sec=60.0)
    assert result["ok"] is False, (
        "P6: stale sidecar must never give ok=True; got %r" % result
    )
    assert result["status"] == "stale", (
        "P6: stale sidecar must give status='stale'; got %r" % result
    )
    assert result["stale"] is True, "P6: stale flag must be True for old sidecar"
    assert result["fresh"] is False, "P6: fresh must be False for old sidecar"


# ---------------------------------------------------------------------------
# P7: rollup [fresh, stale] -> ok=False, monotone-DOWN
# ---------------------------------------------------------------------------

def test_p7_rollup_fresh_and_stale_degrades(tmp_path, monkeypatch):
    """Rollup with one fresh + one stale sport must give ok=False (monotone-DOWN)."""
    monkeypatch.setenv("PREDICT_SERVICE_FRESHNESS_DIR", str(tmp_path))
    monkeypatch.delenv("PREDICT_SERVICE_STORE_DIR", raising=False)
    # NBA: fresh (30s old, max_age 900s).
    _write_sidecar(tmp_path / "nba", _ts_ago(30))
    # Soccer: stale (7200s old, max_age 60s).
    _write_sidecar(tmp_path / "soccer", _ts_ago(7200))
    result = _fs.feed_rollup(["nba", "soccer"], max_age_sec=60.0)
    assert result["ok"] is False, (
        "P7: one stale feed must degrade rollup to ok=False; got %r" % result
    )
    assert result["status"] != "ok", (
        "P7: rollup status must not be 'ok' with a stale member; got %r" % result["status"]
    )
    assert result["n_fresh"] == 1, "P7: n_fresh must be 1 (nba is fresh at 900s max)"
    assert result["n_stale"] == 1, "P7: n_stale must be 1 (soccer is stale)"
    assert result.get("edge_claimed") is False, "P7: edge_claimed must be False"


# ---------------------------------------------------------------------------
# P8: rollup [fresh, fresh] -> ok=True
# ---------------------------------------------------------------------------

def test_p8_rollup_all_fresh_gives_ok(tmp_path, monkeypatch):
    """Rollup where every sport is fresh must give ok=True."""
    monkeypatch.setenv("PREDICT_SERVICE_FRESHNESS_DIR", str(tmp_path))
    monkeypatch.delenv("PREDICT_SERVICE_STORE_DIR", raising=False)
    _write_sidecar(tmp_path / "nba", _ts_ago(30))
    _write_sidecar(tmp_path / "mlb", _ts_ago(45))
    result = _fs.feed_rollup(["nba", "mlb"], max_age_sec=900.0)
    assert result["ok"] is True, (
        "P8: all-fresh rollup must give ok=True; got %r" % result
    )
    assert result["status"] == "ok", (
        "P8: all-fresh rollup status must be 'ok'; got %r" % result["status"]
    )
    assert result["n_fresh"] == 2, "P8: n_fresh must be 2"
    assert result["n_stale"] == 0, "P8: n_stale must be 0"


# ---------------------------------------------------------------------------
# P9: no $ field in any output
# ---------------------------------------------------------------------------

def test_p9_no_dollar_field_feed_status(tmp_path, monkeypatch):
    """feed_status output must contain no key or value with '$'."""
    monkeypatch.setenv("PREDICT_SERVICE_FRESHNESS_DIR", str(tmp_path))
    result = _fs.feed_status("nba")
    assert not _has_dollar_key(result), (
        "P9: feed_status must not emit any $ key/value; got %r" % result
    )


def test_p9_no_dollar_field_rollup(tmp_path, monkeypatch):
    """feed_rollup output must contain no key or value with '$'."""
    monkeypatch.setenv("PREDICT_SERVICE_FRESHNESS_DIR", str(tmp_path))
    result = _fs.feed_rollup(["nba", "mlb"])
    assert not _has_dollar_key(result), (
        "P9: feed_rollup must not emit any $ key/value; got %r" % result
    )


# ---------------------------------------------------------------------------
# P10: never raises on garbage input
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sport", [None, "", "   ", 0, object(), "\x00nba"])
def test_p10_feed_status_never_raises(sport):
    """feed_status must NEVER raise regardless of input."""
    try:
        result = _fs.feed_status(sport)  # type: ignore[arg-type]
        assert result.get("ok") in (True, False), (
            "P10: feed_status must return ok bool; got %r" % result
        )
    except Exception as exc:
        pytest.fail("P10: feed_status raised on input %r: %s" % (sport, exc))


@pytest.mark.parametrize("sports", [None, [], [None, ""], [42, object()]])
def test_p10_rollup_never_raises(sports):
    """feed_rollup must NEVER raise regardless of input."""
    try:
        result = _fs.feed_rollup(sports)  # type: ignore[arg-type]
        assert result.get("ok") in (True, False), (
            "P10: feed_rollup must return ok bool; got %r" % result
        )
    except Exception as exc:
        pytest.fail("P10: feed_rollup raised on input %r: %s" % (sports, exc))


# ---------------------------------------------------------------------------
# P11: rollup over empty sports list -> ok=False (never green)
# ---------------------------------------------------------------------------

def test_p11_empty_rollup_not_green():
    """Empty sports list must yield ok=False (no feeds cannot be asserted fresh)."""
    result = _fs.feed_rollup([])
    assert result["ok"] is False, (
        "P11: empty rollup must give ok=False; got %r" % result
    )
    assert result["n_feeds"] == 0, "P11: n_feeds must be 0 for empty input"
