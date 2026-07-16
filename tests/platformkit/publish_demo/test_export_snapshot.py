"""Per-file test for scripts/platformkit/publish_demo/export_snapshot.py --
covers the three load-bearing bits: slug() staying in lockstep with the
client's snapshotPath(), the row cap, and the privacy gate refusing secrets."""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "platformkit" / "publish_demo"))

import export_snapshot as es  # noqa: E402


def test_slug_matches_client_convention():
    assert es.slug("/api/report/nba") == "api_report_nba.json"
    assert es.slug("/api/board/slate?sport=nba") == "api_board_slate_sport_nba.json"
    assert es.slug("api/ops/status") == "api_ops_status.json"


def test_cap_trail_rows_keeps_most_recent_n():
    rows = [{"i": i} for i in range(500)]
    payload = {"status": "ok", "trail": rows}
    out = es.cap_trail_rows(payload)
    assert len(out["trail"]) == es.TRAIL_CAP
    assert out["trail"][0]["i"] == 200  # last 300 of 0..499
    assert out["trail"][-1]["i"] == 499


def test_cap_trail_rows_noop_under_cap():
    payload = {"status": "ok", "predictions": [{"i": 1}]}
    out = es.cap_trail_rows(payload)
    assert out["predictions"] == [{"i": 1}]


@pytest.mark.parametrize(
    "bad_payload",
    [
        {"api_key": "x"},
        {"token": "abc123"},
        {"password": "hunter2"},
        {"nested": {"secret_token": "abc"}},
        {"reasons": [{"secret": "y"}]},
    ],
)
def test_privacy_gate_refuses_secret_like_keys(bad_payload):
    with pytest.raises(RuntimeError, match="privacy gate"):
        es.privacy_gate(bad_payload, "/api/whatever")


def test_privacy_gate_allows_honest_value_mentioning_secret():
    # A string VALUE that mentions "secret" (e.g. a governance reason quoting
    # an env var name) is NOT a leak -- only KEY names gate.
    payload = {
        "status": "ok",
        "reasons": ["no signing secret: set GOVERNANCE_REALMONEY_SECRET"],
    }
    es.privacy_gate(payload, "/api/whatever")  # must not raise


def test_privacy_gate_allows_clean_payload():
    payload = {"status": "ok", "generated_at": "2026-07-15T00:00:00Z"}
    es.privacy_gate(payload, "/api/whatever")  # must not raise


def test_exporter_write_applies_cap_and_gate(tmp_path):
    ex = es.Exporter(p5="http://x", boards="http://y", out_dir=tmp_path)
    rows = [{"i": i} for i in range(400)]
    ex.write("/api/paper/trail", {"status": "ok", "trail": rows})
    written = json.loads((tmp_path / "api_paper_trail.json").read_text())
    assert len(written["trail"]) == es.TRAIL_CAP
    assert "/api/paper/trail" in ex.written


def test_exporter_write_refuses_secret_payload(tmp_path):
    ex = es.Exporter(p5="http://x", boards="http://y", out_dir=tmp_path)
    with pytest.raises(RuntimeError, match="privacy gate"):
        ex.write("/api/whatever", {"api_key": "leak"})
    assert not (tmp_path / "api_whatever.json").exists()
