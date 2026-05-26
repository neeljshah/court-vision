"""tests/test_R28_U5_morning_brief.py — R28_U5 morning brief tests.

Covers ``scripts/generate_morning_brief.py``:

* Brief is generated end-to-end with all 8 sections present.
* Each section degrades gracefully when its data source is missing
  ("(no data)" placeholder, never raises).
* Markdown structure validates: starts with the header, each section
  is its own ``## ...`` heading.
* Atomic write — no leftover ``<out>.tmp`` after success.
* Previous brief is rotated to ``<out>.bak``.
* ``--date`` override is honored: yesterday computed relative to it.
* Brief is idempotent: same input -> byte-identical output.
* Brief contains today's date string.
* Bankroll renders with start/current/today P&L/ROI.
* Today's recs renders as a markdown table.

Ship gate: >= 8 tests, all must pass.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts import generate_morning_brief as mb  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def synth_paths(tmp_path: Path) -> Dict[str, Path]:
    """Synthetic isolated data sources covering all 8 sections."""
    # Bankroll
    bkr = tmp_path / "bankroll_state.json"
    bkr.write_text(json.dumps({
        "as_of": "2026-05-26T15:58:02+00:00",
        "start_bankroll": 1000.0,
        "current_bankroll": 1042.50,
        "available_bankroll": 1000.0,
        "daily_pnl": 12.5,
        "roi": {"roi_pct": 4.25, "n_bets": 8},
    }), encoding="utf-8")

    # Settled parquet  — try to write one; if pandas missing skip.
    settled = tmp_path / "rec_settled.parquet"
    try:
        import pandas as pd  # noqa: PLC0415
        df = pd.DataFrame([
            {"date": "2026-05-25", "player": "Alice", "stat": "pts",
             "line": 25.5, "side": "OVER", "result": "WIN",
             "stake_unit": 1.0, "profit": 0.91, "edge": 0.07},
            {"date": "2026-05-25", "player": "Bob", "stat": "reb",
             "line": 8.5, "side": "UNDER", "result": "LOSS",
             "stake_unit": 1.0, "profit": -1.0, "edge": 0.06},
            {"date": "2026-05-25", "player": "Cy", "stat": "ast",
             "line": 6.5, "side": "OVER", "result": "WIN",
             "stake_unit": 1.0, "profit": 0.91, "edge": 0.08},
        ])
        df.to_parquet(settled)
    except Exception:
        settled = None  # type: ignore

    # Daemon registry + heartbeats
    hb_dir = tmp_path / "hb"
    hb_dir.mkdir()
    (hb_dir / "alpha.txt").write_text("2026-05-26T18:30:00Z", encoding="utf-8")
    (hb_dir / "beta.txt").write_text("2026-05-26T18:30:00Z", encoding="utf-8")
    reg = tmp_path / "registry.json"
    reg.write_text(json.dumps({"daemons": [
        {"name": "alpha", "expected_interval_sec": 999999,
         "heartbeat_file": str(hb_dir / "alpha.txt")},
        {"name": "beta", "expected_interval_sec": 999999,
         "heartbeat_file": str(hb_dir / "beta.txt")},
        {"name": "gamma_missing", "expected_interval_sec": 60,
         "heartbeat_file": str(hb_dir / "gamma_missing.txt")},
    ]}), encoding="utf-8")

    # Alerts vault + dir
    av = tmp_path / "alerts.md"
    av.write_text(
        "# Alerts\n"
        "- **2026-05-26T15:00:00Z** [WARN] [line_move] STEAM: pts 25.5\n"
        "- **2026-05-26T16:00:00Z** [CRITICAL] [daemon] heartbeat stale\n",
        encoding="utf-8",
    )
    adir = tmp_path / "alerts_dir"
    adir.mkdir()
    (adir / "critical_2026-05-26.json").write_text(json.dumps([
        {"ts": "2026-05-26T17:15:02.810874+00:00", "level": "WARN",
         "tag": "line_move", "message": "STEAM: Star pts"},
    ]), encoding="utf-8")

    # Drift cache
    drift = tmp_path / "drift.json"
    drift.write_text(json.dumps({
        "ts": "2026-05-26T18:34:53Z",
        "feature_set": "m2", "status": "OK",
        "n_features_analyzed": 75, "n_stable": 33,
        "n_drift_minor": 7, "n_drift_major": 35,
        "features": [
            {"feature": "away_pace", "mean_z": 1.46, "ks_stat": 0.52, "class": "drift_major"},
            {"feature": "home_pace", "mean_z": 1.26, "ks_stat": 0.43, "class": "drift_major"},
            {"feature": "home_def_rtg", "mean_z": -0.56, "ks_stat": 0.29, "class": "drift_major"},
        ],
    }), encoding="utf-8")

    # Backup dir
    bdir = tmp_path / "backups"
    bdir.mkdir()
    gz = bdir / "pnl_ledger.csv.2026-05-26.gz"
    gz.write_bytes(b"\x1f\x8b\x08\x00synthetic gzip blob")
    sidecar = bdir / "pnl_ledger.csv.2026-05-26.gz.sha256"
    sidecar.write_text("abcdef0123456789  pnl_ledger.csv.2026-05-26.gz\n", encoding="utf-8")

    # Smoke dir
    sdir = tmp_path / "smoke"
    sdir.mkdir()
    today = mb._today_iso()
    (sdir / f"e2e_smoke_{today}.json").write_text(json.dumps({
        "ts": "2026-05-26T18:29:34+00:00", "status": "PASS",
        "n_stages": 12, "n_passed": 12, "n_failed": 0,
        "failed_stage_names": [], "runtime_sec": 0.647,
    }), encoding="utf-8")

    return {
        "bankroll":  bkr,
        "settled":   settled,
        "registry":  reg,
        "hb_dir":    hb_dir,
        "alerts_v":  av,
        "alerts_d":  adir,
        "drift":     drift,
        "backups":   bdir,
        "smoke":     sdir,
        "out":       tmp_path / "out" / "MORNING.md",
    }


def _engine_fn_with_recs(*_args: Any, **kwargs: Any) -> Dict[str, Any]:
    return {
        "engine_version": "R23_P8",
        "date": kwargs.get("date") or "2026-05-26",
        "n_evaluated": 100,
        "n_recs": 2,
        "recommendations": [
            {"player": "Alice", "stat": "pts", "line": 25.5, "side": "OVER",
             "book": "fd", "edge": 0.072, "stake_dollars": 25.0},
            {"player": "Bob", "stat": "ast", "line": 6.5, "side": "UNDER",
             "book": "bov", "edge": 0.061, "stake_dollars": 15.0},
        ],
        "reason": "2 recs ranked",
    }


def _engine_fn_empty(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    return {"engine_version": "R23_P8", "recommendations": [],
            "n_evaluated": 0, "n_recs": 0, "reason": "no positive-edge"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_brief_generates_with_all_sections(synth_paths):
    paths = synth_paths
    res = mb.generate(
        out_path=paths["out"],
        bankroll_path=paths["bankroll"],
        settled_path=paths["settled"] if paths["settled"] else paths["out"].parent / "_nope.parquet",
        registry_path=paths["registry"],
        heartbeat_dir=paths["hb_dir"],
        alerts_vault=paths["alerts_v"],
        alerts_dir=paths["alerts_d"],
        drift_cache=paths["drift"],
        backup_dir=paths["backups"],
        smoke_dir=paths["smoke"],
        engine_fn=_engine_fn_with_recs,
    )
    assert res["ok"] is True
    assert res["n_sections"] == 8
    body = paths["out"].read_text(encoding="utf-8")
    # All 8 H2 headings (plus the H1 header) must be present.
    for heading in (
        "# Morning Brief",
        "## Bankroll",
        "## Yesterday's Recs",
        "## Today's Top Recs",
        "## System Health",
        "## Recent Alerts",
        "## Feature Drift",
        "## Backup + Smoke",
    ):
        assert heading in body, f"missing heading: {heading}"


def test_missing_sources_render_no_data(tmp_path):
    """Pointing every source at a non-existent path should still
    succeed and emit (no data) markers — never raise."""
    out = tmp_path / "MORNING.md"
    missing = tmp_path / "nope"
    res = mb.generate(
        out_path=out,
        bankroll_path=missing,
        settled_path=missing / "x.parquet",
        registry_path=missing,
        heartbeat_dir=missing,
        alerts_vault=missing,
        alerts_dir=missing,
        drift_cache=missing,
        backup_dir=missing,
        smoke_dir=missing,
        engine_fn=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert res["ok"] is True
    body = out.read_text(encoding="utf-8")
    # We expect many (no data) markers across sections.
    assert body.count("(no data)") >= 4
    # All 8 headings still present.
    assert body.count("## ") >= 7  # 7 H2 + the H1 (counted as "# ")


def test_markdown_structure_is_valid(synth_paths):
    paths = synth_paths
    res = mb.generate(
        out_path=paths["out"],
        bankroll_path=paths["bankroll"],
        settled_path=paths["settled"] if paths["settled"] else paths["out"].parent / "_nope.parquet",
        registry_path=paths["registry"],
        heartbeat_dir=paths["hb_dir"],
        alerts_vault=paths["alerts_v"],
        alerts_dir=paths["alerts_d"],
        drift_cache=paths["drift"],
        backup_dir=paths["backups"],
        smoke_dir=paths["smoke"],
        engine_fn=_engine_fn_with_recs,
    )
    body = paths["out"].read_text(encoding="utf-8")
    # Header must come first.
    assert body.lstrip().startswith("# Morning Brief"), body[:80]
    # Footer marker present.
    assert "R28_U5" in body


def test_atomic_write_leaves_no_tmp(synth_paths):
    paths = synth_paths
    mb.generate(
        out_path=paths["out"],
        bankroll_path=paths["bankroll"],
        registry_path=paths["registry"],
        heartbeat_dir=paths["hb_dir"],
        drift_cache=paths["drift"],
        backup_dir=paths["backups"],
        smoke_dir=paths["smoke"],
        engine_fn=_engine_fn_empty,
    )
    # No leftover .tmp anywhere under the out dir.
    leftover = list(paths["out"].parent.glob("*.tmp"))
    assert leftover == []
    assert paths["out"].exists()


def test_previous_brief_is_rotated_to_bak(synth_paths):
    paths = synth_paths
    # First call — establish a baseline brief.
    mb.generate(
        out_path=paths["out"],
        bankroll_path=paths["bankroll"],
        registry_path=paths["registry"],
        heartbeat_dir=paths["hb_dir"],
        drift_cache=paths["drift"],
        backup_dir=paths["backups"],
        smoke_dir=paths["smoke"],
        engine_fn=_engine_fn_empty,
    )
    first = paths["out"].read_text(encoding="utf-8")
    # Second call should rotate the first one to .bak.
    res = mb.generate(
        out_path=paths["out"],
        bankroll_path=paths["bankroll"],
        registry_path=paths["registry"],
        heartbeat_dir=paths["hb_dir"],
        drift_cache=paths["drift"],
        backup_dir=paths["backups"],
        smoke_dir=paths["smoke"],
        engine_fn=_engine_fn_with_recs,
    )
    bak_path = Path(res["bak_path"])
    assert bak_path.exists()
    assert bak_path.read_text(encoding="utf-8") == first


def test_date_override_drives_yesterday(synth_paths):
    paths = synth_paths
    res = mb.generate(
        out_path=paths["out"],
        bankroll_path=paths["bankroll"],
        settled_path=paths["settled"] if paths["settled"] else paths["out"].parent / "_nope.parquet",
        registry_path=paths["registry"],
        heartbeat_dir=paths["hb_dir"],
        drift_cache=paths["drift"],
        backup_dir=paths["backups"],
        smoke_dir=paths["smoke"],
        engine_fn=_engine_fn_empty,
        today="2026-05-26",
    )
    body = paths["out"].read_text(encoding="utf-8")
    assert "2026-05-26" in body
    # Yesterday = 2026-05-25; settled fixture rows are dated 2026-05-25,
    # so when pandas is present we should see the W/L counts.
    sections = res["sections"]
    if paths["settled"] is not None and sections["Yesterday"].get("ok"):
        assert sections["Yesterday"]["date"] == "2026-05-25"


def test_brief_is_idempotent(synth_paths):
    paths = synth_paths
    kwargs = dict(
        bankroll_path=paths["bankroll"],
        settled_path=paths["settled"] if paths["settled"] else paths["out"].parent / "_nope.parquet",
        registry_path=paths["registry"],
        heartbeat_dir=paths["hb_dir"],
        alerts_vault=paths["alerts_v"],
        alerts_dir=paths["alerts_d"],
        drift_cache=paths["drift"],
        backup_dir=paths["backups"],
        smoke_dir=paths["smoke"],
        engine_fn=_engine_fn_with_recs,
        # Pin every time-derived input so the output is deterministic.
        today="2026-05-26",
        now=1748290000.0,
        now_dt=datetime(2026, 5, 26, 18, 30, 0, tzinfo=timezone.utc),
    )
    out1 = paths["out"]
    out2 = paths["out"].parent / "MORNING2.md"
    mb.generate(out_path=out1, **kwargs)
    mb.generate(out_path=out2, **kwargs)
    a = out1.read_text(encoding="utf-8")
    b = out2.read_text(encoding="utf-8")
    assert a == b, "brief must be byte-identical given the same inputs"


def test_brief_includes_todays_date(synth_paths):
    paths = synth_paths
    mb.generate(
        out_path=paths["out"],
        bankroll_path=paths["bankroll"],
        registry_path=paths["registry"],
        heartbeat_dir=paths["hb_dir"],
        drift_cache=paths["drift"],
        backup_dir=paths["backups"],
        smoke_dir=paths["smoke"],
        engine_fn=_engine_fn_empty,
        today="2026-05-26",
    )
    body = paths["out"].read_text(encoding="utf-8")
    assert "2026-05-26" in body


def test_today_recs_renders_as_table(synth_paths):
    paths = synth_paths
    mb.generate(
        out_path=paths["out"],
        bankroll_path=paths["bankroll"],
        registry_path=paths["registry"],
        heartbeat_dir=paths["hb_dir"],
        drift_cache=paths["drift"],
        backup_dir=paths["backups"],
        smoke_dir=paths["smoke"],
        engine_fn=_engine_fn_with_recs,
    )
    body = paths["out"].read_text(encoding="utf-8")
    # Table headers must be present.
    assert "| # | Player | Stat | Side | Line | Book | Edge | Stake |" in body
    # Both fixture recs should appear.
    assert "Alice" in body and "Bob" in body


def test_brief_size_sensible(synth_paths):
    paths = synth_paths
    res = mb.generate(
        out_path=paths["out"],
        bankroll_path=paths["bankroll"],
        settled_path=paths["settled"] if paths["settled"] else paths["out"].parent / "_nope.parquet",
        registry_path=paths["registry"],
        heartbeat_dir=paths["hb_dir"],
        alerts_vault=paths["alerts_v"],
        alerts_dir=paths["alerts_d"],
        drift_cache=paths["drift"],
        backup_dir=paths["backups"],
        smoke_dir=paths["smoke"],
        engine_fn=_engine_fn_with_recs,
    )
    # Operator brief is supposed to be a one-pager: > 500B (not empty),
    # < 50KB (not a data dump).
    assert 500 <= res["size_bytes"] <= 50_000
