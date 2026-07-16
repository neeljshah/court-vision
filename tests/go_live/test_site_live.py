"""Unit tests for scripts.go_live.site_live -- url parsing, state io, pid-verify.

Real network/process smoke test is run manually (see task); these cover the
pure logic with synthetic inputs, no live server/tunnel needed.
"""
from __future__ import annotations

import json

from scripts.go_live import site_live as sl


def test_read_write_clear_state(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "STATE_FILE", tmp_path / "state.json")
    assert sl.read_state() == {}
    sl.write_state({"url": "https://foo.trycloudflare.com", "next_pid": 123})
    assert sl.read_state() == {"url": "https://foo.trycloudflare.com", "next_pid": 123}
    sl.clear_state()
    assert sl.read_state() == {}


def test_read_state_survives_corrupt_json(tmp_path, monkeypatch):
    f = tmp_path / "state.json"
    f.write_text("{not json")
    monkeypatch.setattr(sl, "STATE_FILE", f)
    assert sl.read_state() == {}


def test_parse_tunnel_url_finds_url(tmp_path, monkeypatch):
    log = tmp_path / "cloudflared.log"
    log.write_text(
        "2026-07-15 some log line\n"
        "INFO Your quick Tunnel has been created! Visit it at: https://random-words-here.trycloudflare.com\n"
    )
    monkeypatch.setattr(sl, "TUNNEL_LOG", log)
    url = sl.parse_tunnel_url(timeout=1)
    assert url == "https://random-words-here.trycloudflare.com"


def test_parse_tunnel_url_times_out_when_absent(tmp_path, monkeypatch):
    log = tmp_path / "cloudflared.log"
    log.write_text("no url in here yet\n")
    monkeypatch.setattr(sl, "TUNNEL_LOG", log)
    assert sl.parse_tunnel_url(timeout=1) is None


def test_pid_cmdline_parses_wmic_format_list(monkeypatch):
    fake_output = "\n\nCommandLine=npx next start -p 3100\n\n\n"
    monkeypatch.setattr(sl.subprocess, "check_output", lambda *a, **k: fake_output)
    assert sl.pid_cmdline(4242) == "npx next start -p 3100"


def test_pid_cmdline_empty_when_process_gone(monkeypatch):
    def _raise(*a, **k):
        raise sl.subprocess.CalledProcessError(1, "wmic")
    monkeypatch.setattr(sl.subprocess, "check_output", _raise)
    assert sl.pid_cmdline(9999) == ""


def test_pid_matches_true_and_false(monkeypatch):
    monkeypatch.setattr(sl, "pid_cmdline", lambda pid: "C:\\...\\node.exe  next start -p 3100")
    assert sl.pid_matches(1, "next") is True
    assert sl.pid_matches(1, "cloudflared") is False


def test_kill_tracked_pid_refuses_mismatch(monkeypatch):
    monkeypatch.setattr(sl, "pid_matches", lambda pid, needle: False)
    calls = []
    monkeypatch.setattr(sl.subprocess, "run", lambda *a, **k: calls.append(a))
    assert sl.kill_tracked_pid(5555, "next") is False
    assert calls == []


def test_kill_tracked_pid_kills_on_match(monkeypatch):
    monkeypatch.setattr(sl, "pid_matches", lambda pid, needle: True)
    calls = []
    monkeypatch.setattr(sl.subprocess, "run", lambda *a, **k: calls.append(a) or None)
    assert sl.kill_tracked_pid(5555, "next") is True
    assert calls  # taskkill was invoked


def test_probe_url_ok_and_json_shape(monkeypatch):
    class _Resp:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(sl.urllib.request, "urlopen", lambda *a, **k: _Resp())
    ok, status = sl.probe_url("https://foo.trycloudflare.com")
    assert ok is True
    assert status == 200


if __name__ == "__main__":
    # ponytail: smallest runnable check without a test runner
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        sl.STATE_FILE = Path(d) / "state.json"
        sl.write_state({"a": 1})
        assert sl.read_state() == {"a": 1}
    print("test_site_live self-check: PASSED")
