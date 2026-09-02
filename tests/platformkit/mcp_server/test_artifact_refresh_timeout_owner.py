"""S77: ONE owner for the producer wall cap, and a TIMEOUT that kills its writer.

Before this row `artifact_refresh.PRODUCER_TIMEOUT_SEC` was an independent 120.0
while `intelligence_producers.PRODUCER_TIMEOUT_S` was 900.0, the CLI had no flag,
and a timeout abandoned a daemon thread whose subprocess kept writing -- a CLI
pass reported 5 TIMEOUT / 0 advanced for five producers that all completed.
"""
import argparse
import subprocess
import time

import pytest

from scripts.platformkit.mcp_server import artifact_refresh as ar
from scripts.platformkit.mcp_server import intelligence_producers as ip


def _cli_default(flag):
    """The argparse default the CLI would use, read from main()'s own parser."""
    captured = {}
    real_parse = argparse.ArgumentParser.parse_args

    def spy(self, argv=None, namespace=None):
        captured["parser"] = self
        raise SystemExit(0)

    argparse.ArgumentParser.parse_args = spy
    try:
        with pytest.raises(SystemExit):
            ar.main(["--dry-run"])
    finally:
        argparse.ArgumentParser.parse_args = real_parse
    for action in captured["parser"]._actions:
        if flag in action.option_strings:
            return action.default
    raise AssertionError(flag + " is not a CLI flag")


def test_one_owner_and_default_is_the_shared_constant():
    assert ar.PRODUCER_TIMEOUT_SEC is ip.PRODUCER_TIMEOUT_S
    assert ip.PRODUCER_TIMEOUT_S >= 900.0
    assert _cli_default("--timeout-sec") == ar.PRODUCER_TIMEOUT_SEC


def test_cli_honours_the_flag(tmp_path, monkeypatch):
    """--timeout-sec reaches refresh_once, and refresh_once reaches _run_producer."""
    seen = []

    def spy(producer, root, timeout_sec):
        seen.append(timeout_sec)
        return 0, None, False

    monkeypatch.setattr(ar, "_run_producer", spy)
    monkeypatch.setattr(ar, "TARGETS", (ar.Target("t", (), lambda root: None),))
    rc = ar.main(["--once", "--root", str(tmp_path), "--out-dir", str(tmp_path / "o"),
                  "--timeout-sec", "7.5"])
    assert rc == 0
    assert seen == [7.5]


def test_timeout_kills_the_child_no_orphan(tmp_path):
    """A slow SUBPROCESS producer is killed by the wall cap, not abandoned."""
    script = tmp_path / "slow_producer.py"
    marker = tmp_path / "wrote_after_timeout.txt"
    script.write_text(
        "import time\n"
        "time.sleep(20)\n"
        "open(r'{0}', 'w').write('the abandoned writer still ran')\n".format(marker),
        encoding="ascii")
    producer = ip._runner(script.name)

    started = time.time()
    rc, error, timed_out = ar._run_producer(producer, tmp_path, timeout_sec=1.0)
    wall = time.time() - started

    assert timed_out is True and rc == 1
    assert "wall cap" in error
    assert wall < 15.0, "the cap did not fire ({0:.1f}s)".format(wall)
    proc = producer.proc
    assert proc is not None and proc.poll() is not None, "child survived the TIMEOUT"
    time.sleep(2.0)
    assert not marker.exists(), "the killed producer still wrote its artifact"


def test_runner_kills_on_its_own_cap(tmp_path):
    """The producer-side cap kills too, so a direct caller leaves no orphan."""
    script = tmp_path / "slow2.py"
    script.write_text("import time\ntime.sleep(20)\n", encoding="ascii")
    producer = ip._runner(script.name)
    producer.timeout_sec = 1.0
    with pytest.raises(subprocess.TimeoutExpired):
        producer(tmp_path)
    assert producer.proc.poll() is not None


def test_runner_still_reports_a_failing_producer(tmp_path):
    script = tmp_path / "bad.py"
    script.write_text("import sys\nsys.stderr.write('boom\\n')\nsys.exit(3)\n", encoding="ascii")
    producer = ip._runner(script.name)
    rc, error, timed_out = ar._run_producer(producer, tmp_path, timeout_sec=60.0)
    assert (rc, timed_out) == (1, False)
    assert "rc=3" in error and "boom" in error
