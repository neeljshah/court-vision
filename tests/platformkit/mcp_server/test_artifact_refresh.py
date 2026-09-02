"""S24: per-file checks for the MCP artifact refresher.

Every write lands under tmp_path: the fake producers write into the tmp root and
the heartbeat/status go to a tmp out-dir. No real producer runs, no daemon starts.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

from scripts.platformkit.mcp_server import artifact_refresh as ar
from scripts.platformkit.mcp_server import artifact_tools

_STAMPS = itertools.count(1)


def _maker(rel: str):
    """A fake producer whose artifact stamp strictly advances on every call."""
    def _run(root: Path) -> None:
        path = Path(root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"generated_at": "2026-09-03T00:00:00.%06d+00:00" % next(_STAMPS)}),
            encoding="ascii")
    return _run


def _boom(root: Path) -> None:
    raise RuntimeError("producer exploded")


def _targets():
    return (ar.Target("good_a", ("out/a.json",), _maker("out/a.json")),
            ar.Target("good_b", ("out/b.json",), _maker("out/b.json")),
            ar.Target("broken", ("out/c.json",), _boom),
            ar.Target("no_prod", ("out/d.json",), None))


def _rows(record):
    return {row["name"]: row for row in record["targets"]}


def _lines(out_dir: Path):
    text = (out_dir / ar.HEARTBEAT_NAME).read_text(encoding="ascii")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_once_advances_and_writes_one_heartbeat(tmp_path):
    root, out = tmp_path / "repo", tmp_path / "cache"
    record = ar.refresh_once(root, out, _targets())
    rows = _rows(record)
    assert rows["good_a"]["status"] == "ok" and rows["good_a"]["advanced"]
    assert rows["good_b"]["status"] == "ok" and rows["good_b"]["advanced"]
    assert record["n_advanced"] == 2
    assert len(_lines(out)) == 1
    status = json.loads((out / ar.STATUS_NAME).read_text(encoding="ascii"))
    assert status["started_at"] == record["started_at"]


def test_three_consecutive_passes_are_monotone(tmp_path):
    root, out = tmp_path / "repo", tmp_path / "cache"
    records = [ar.refresh_once(root, out, _targets()) for _ in range(3)]
    assert len(_lines(out)) == 3
    for name in ("good_a", "good_b"):
        stamps = [_rows(rec)[name]["stamp_after"] for rec in records]
        assert stamps == sorted(stamps) and len(set(stamps)) == 3, (name, stamps)
        assert all(_rows(rec)[name]["advanced"] for rec in records)
    # the same target set every pass -- the monotone check cannot be satisfied by swapping it
    assert {tuple(sorted(_rows(rec))) for rec in records} == {
        ("broken", "good_a", "good_b", "no_prod")}


def test_failing_producer_is_recorded_not_raised(tmp_path):
    root, out = tmp_path / "repo", tmp_path / "cache"
    record = ar.refresh_once(root, out, _targets())
    broken = _rows(record)["broken"]
    assert broken["status"] == "FAILED" and broken["rc"] == 1
    assert "producer exploded" in broken["error"]
    assert not broken["advanced"]
    assert record["n_failed"] == 1
    assert record["n_advanced"] == 2  # the other rows still ran
    assert len(_lines(out)) == 1  # exactly one heartbeat line, not a half-written pass


def test_no_producer_is_named_never_advanced(tmp_path):
    root, out = tmp_path / "repo", tmp_path / "cache"
    record = ar.refresh_once(root, out, _targets())
    row = _rows(record)["no_prod"]
    assert row["status"] == "NO_PRODUCER" and row["rc"] is None and not row["advanced"]
    assert record["n_no_producer"] == 1
    # every target is counted exactly once -- no row is dropped from the denominator
    assert record["n_targets"] == 4
    assert (record["n_advanced"] + record["n_failed"] + record["n_no_producer"]
            + record["n_stale"]) == 4


def test_nothing_is_written_outside_tmp_path(tmp_path):
    root, out = tmp_path / "repo", tmp_path / "cache"
    ar.refresh_once(root, out, _targets())
    written = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert written == ["cache/artifact_refresh_heartbeat.jsonl",
                       "cache/artifact_refresh_status.json",
                       "repo/out/a.json", "repo/out/b.json"]
    assert not (ar.ROOT / "out" / "a.json").exists()


def test_every_mcp_artifact_tool_has_a_target():
    """Non-tautology guard: the table covers every tool, producer or not."""
    assert {t.name for t in ar.TARGETS} == {s["name"] for s in artifact_tools.tool_specs()}
    for target in ar.TARGETS:
        assert target.producer is not None or target.name == "tracking_program_status"


def test_module_starts_no_daemon_and_arms_no_task():
    text = Path(ar.__file__).read_text(encoding="utf-8")
    for forbidden in ("subprocess", "Popen", "os.system", "ProcSpec("):
        assert forbidden not in text, forbidden
    # the schtasks line is a documented STRING for the orchestrator, never executed
    assert "schtasks /Create" in ar.SCHTASKS
