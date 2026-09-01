"""Focused tests for the local-download / pod-track footage bridge."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.platformkit import footage_bridge


def test_thin_tracking_output_is_not_reported_as_tracked(monkeypatch, tmp_path):
    """A 103-row CSV is non-empty and useless; only the row count may pass it."""
    commands: list[str] = []

    def fake_ssh(command, timeout=7200):
        commands.append(command)
        if command.startswith("wc -l"):
            return subprocess.CompletedProcess(command, 0, stdout="103\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="done", stderr="")

    monkeypatch.setattr(footage_bridge, "_ssh", fake_ssh)
    monkeypatch.setattr(footage_bridge.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))

    status = footage_bridge.push_and_track(
        tmp_path / "kbo_01.mp4", {"game_id": "kbo_01", "sport": "kbo"})

    assert status.startswith("thin rows=103")
    # The video must be staged privately, never in data/footage where the pod
    # track_staged loop would delete it mid-transfer.
    assert any("data/footage_bridge/kbo_01.mp4" in c for c in commands)
    assert not any("/data/footage/kbo_01" in c for c in commands)
    # And the remote copy is always reclaimed.
    assert any(c.startswith("rm -f") for c in commands)


def test_remote_copy_deleted_even_when_tracking_raises(monkeypatch, tmp_path):
    removed: list[str] = []

    def fake_ssh(command, timeout=7200):
        if command.startswith("rm -f"):
            removed.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command.startswith("wc -l"):
            return subprocess.CompletedProcess(command, 0, stdout="0\n", stderr="")
        if "adapter_run" in command:
            raise RuntimeError("tracking exploded")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(footage_bridge, "_ssh", fake_ssh)
    monkeypatch.setattr(footage_bridge.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))

    try:
        footage_bridge.push_and_track(tmp_path / "npb_02.mp4",
                                      {"game_id": "npb_02", "sport": "npb"})
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected the tracking failure to propagate")
    assert removed, "pod disk must be reclaimed even when tracking raises"


def test_download_resolves_mkv_fallback_and_skips_fragments(monkeypatch, tmp_path):
    """yt-dlp falls back to .mkv; fragment files are not real artifacts."""
    monkeypatch.setattr(footage_bridge, "LOCAL_STAGE", tmp_path)
    monkeypatch.setattr(footage_bridge, "COOKIES", tmp_path / "absent.txt")

    def fake_run(command, **kwargs):
        (tmp_path / "g1.mp4-Frag511").write_bytes(b"x" * 999)
        (tmp_path / "g1.mkv").write_bytes(b"video")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(footage_bridge.subprocess, "run", fake_run)

    produced = footage_bridge.download_local(
        {"game_id": "g1", "url": "https://youtube.example/watch?v=1"})

    assert produced.name == "g1.mkv"


def test_queue_skips_already_tracked_and_records_ledger(monkeypatch, tmp_path):
    queue = tmp_path / "footage_queue_kbo.json"
    queue.write_text(json.dumps([
        {"sport": "kbo", "game_id": "done_01", "url": "u1"},
        {"sport": "kbo", "game_id": "todo_01", "url": "u2"},
    ]), encoding="utf-8")
    monkeypatch.setattr(footage_bridge, "LEDGER", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(footage_bridge, "LOCAL_STAGE", tmp_path / "stage")
    monkeypatch.setattr(footage_bridge, "tracked_row_counts",
                        lambda: {"done_01": 9000})
    monkeypatch.setattr(footage_bridge, "download_local",
                        lambda item: Path(tmp_path / "stage" / "todo_01.mp4"))
    monkeypatch.setattr(footage_bridge, "push_and_track",
                        lambda local, item: "tracked rows=9000")

    tracked = footage_bridge.run_queue(queue, limit=5)

    assert tracked == 1
    entries = [json.loads(line) for line
               in (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [entry["game_id"] for entry in entries] == ["todo_01"]


def test_row_counts_parsed_from_one_batched_probe(monkeypatch):
    """One ssh round trip for the whole corpus, not one per queue item."""
    calls = []

    def fake_ssh(command, timeout=7200):
        calls.append(command)
        return subprocess.CompletedProcess(
            command, 0, stderr="",
            stdout="  9000 kbo_01/tracking_data.csv\n"
                   "   103 kbo_02/tracking_data.csv\n"
                   "  9103 total\n")

    monkeypatch.setattr(footage_bridge, "_ssh", fake_ssh)

    counts = footage_bridge.tracked_row_counts()

    assert counts == {"kbo_01": 9000, "kbo_02": 103}
    assert len(calls) == 1


def test_grade_writes_report_and_maps_wnba_to_basketball(monkeypatch):
    """The run_clip path never graded itself; the bridge must grade every game."""
    sent = []

    def fake_ssh(command, timeout=7200):
        sent.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="passed\n", stderr="")

    monkeypatch.setattr(footage_bridge, "_ssh", fake_ssh)

    verdict = footage_bridge.grade("wnba_01", "wnba")

    assert verdict == "passed"
    # The harness has no "wnba" sport profile; it must be graded as basketball.
    assert "'basketball'" in sent[0]
    assert "data/tracking_reports/basketball" in sent[0]


def test_grade_reports_when_it_cannot_grade(monkeypatch):
    monkeypatch.setattr(footage_bridge, "_ssh", lambda command, timeout=7200:
                        subprocess.CompletedProcess(command, 1, stdout="",
                                                    stderr="boom"))

    assert footage_bridge.grade("kbo_01", "kbo").startswith("ungraded:")


def test_direct_cdn_url_skips_youtube_format_selectors(monkeypatch, tmp_path):
    """MLB's CDN mp4s have no formats; -f bv*+ba makes yt-dlp fail outright."""
    commands = []
    monkeypatch.setattr(footage_bridge, "LOCAL_STAGE", tmp_path)
    monkeypatch.setattr(footage_bridge, "COOKIES", tmp_path / "absent.txt")

    def fake_run(command, **kwargs):
        commands.append(command)
        (tmp_path / "mlb_01.mp4").write_bytes(b"video")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(footage_bridge.subprocess, "run", fake_run)

    footage_bridge.download_local({
        "game_id": "mlb_01",
        "url": "https://mlb-cuts-diamond.mlb.com/FORGE/x-asset_1280x720_59_4000K.mp4"})

    assert len(commands) == 1
    assert "-f" not in commands[0]


def test_youtube_url_still_uses_the_format_ladder(monkeypatch, tmp_path):
    commands = []
    monkeypatch.setattr(footage_bridge, "LOCAL_STAGE", tmp_path)
    monkeypatch.setattr(footage_bridge, "COOKIES", tmp_path / "absent.txt")

    def fake_run(command, **kwargs):
        commands.append(command)
        (tmp_path / "yt_01.mp4").write_bytes(b"video")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(footage_bridge.subprocess, "run", fake_run)

    footage_bridge.download_local(
        {"game_id": "yt_01", "url": "https://www.youtube.com/watch?v=ChxXA-7uyHk"})

    downloads = [c for c in commands if "--skip-download" not in c]
    assert "-f" in downloads[0]


def test_error_tail_skips_the_deprecation_banner():
    """yt-dlp leads with a Python deprecation warning; the real cause is later."""
    stderr = ("Deprecated Feature: Support for Python version 3.10 has been "
              "deprecated. Please update to Python 3.11 or above\n"
              "[youtube] abc: Downloading webpage\n"
              "ERROR: [youtube] abc: Video unavailable\n")

    assert footage_bridge._error_tail(stderr) == "ERROR: [youtube] abc: Video unavailable"


def test_error_tail_falls_back_to_last_meaningful_line():
    stderr = ("Deprecated Feature: Support for Python version 3.10 has been deprecated.\n"
              "Please update to Python 3.11 or above\n"
              "something actually broke\n")

    assert footage_bridge._error_tail(stderr) == "something actually broke"


def test_first_download_attempt_does_not_use_cookies(monkeypatch, tmp_path):
    """Cookies make yt-dlp pick the slow HLS tv client; try clean DASH first."""
    commands = []
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    monkeypatch.setattr(footage_bridge, "LOCAL_STAGE", tmp_path)
    monkeypatch.setattr(footage_bridge, "COOKIES", cookies)

    def fake_run(command, **kwargs):
        commands.append(command)
        (tmp_path / "g.mp4").write_bytes(b"video")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(footage_bridge.subprocess, "run", fake_run)

    footage_bridge.download_local(
        {"game_id": "g", "url": "https://www.youtube.com/watch?v=abc"})

    assert "--cookies" not in commands[0]


def test_output_flag_is_immediately_followed_by_its_filename(monkeypatch, tmp_path):
    """Splicing -f between -o and its value made yt-dlp treat "-f" as the name."""
    commands = []
    monkeypatch.setattr(footage_bridge, "LOCAL_STAGE", tmp_path)
    monkeypatch.setattr(footage_bridge, "COOKIES", tmp_path / "absent.txt")

    def fake_run(command, **kwargs):
        commands.append(command)
        (tmp_path / "g.mp4").write_bytes(b"video")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(footage_bridge.subprocess, "run", fake_run)

    footage_bridge.download_local(
        {"game_id": "g", "url": "https://www.youtube.com/watch?v=abc"})

    downloads = [c for c in commands if "--skip-download" not in c]
    assert downloads, "no download command was issued"
    for command in downloads:
        output_at = command.index("-o")
        assert command[output_at + 1].endswith("g.mp4")
        assert command[-1] == "https://www.youtube.com/watch?v=abc"
        # -f must carry a real selector, never a flag
        if "-f" in command:
            assert not command[command.index("-f") + 1].startswith("-")


def test_resolver_never_returns_an_unmerged_stream(monkeypatch, tmp_path):
    """game.f137.mp4 is video-only; shipping it as the game is silent corruption."""
    monkeypatch.setattr(footage_bridge, "LOCAL_STAGE", tmp_path)
    monkeypatch.setattr(footage_bridge, "COOKIES", tmp_path / "absent.txt")
    # video-only stream is the LARGEST file present, so size alone would pick it
    (tmp_path / "g.f137.mp4").write_bytes(b"x" * 5000)
    (tmp_path / "g.f299.mp4").write_bytes(b"x" * 3000)

    assert footage_bridge._resolve_download(tmp_path / "g.mp4") is None

    (tmp_path / "g.mkv").write_bytes(b"x" * 100)
    resolved = footage_bridge._resolve_download(tmp_path / "g.mp4")
    assert resolved is not None and resolved.name == "g.mkv"


def test_keeps_exactly_one_reference_clip_per_sport(monkeypatch, tmp_path):
    """Deleting every copy left tracking work unable to re-measure anything."""
    monkeypatch.setattr(footage_bridge, "REFERENCE_DIR", tmp_path / "reference")
    first = tmp_path / "tennis_01.mp4"
    first.write_bytes(b"video")

    assert footage_bridge.keep_reference(first, "tennis") is True
    assert (tmp_path / "reference" / "tennis.mp4").is_file()

    second = tmp_path / "tennis_02.mp4"
    second.write_bytes(b"video")
    # Only one per sport: the second is not kept, so the caller deletes it.
    assert footage_bridge.keep_reference(second, "tennis") is False
    assert second.is_file()


def test_staged_upload_renames_atomically_so_the_daemon_sees_no_partial(
        monkeypatch, tmp_path):
    """scp writes .part; only the rename publishes it. A direct scp lets the
    daemon pick up a half-transferred video -- the race that once fed the
    tracker a truncated file."""
    calls = []
    monkeypatch.setattr(footage_bridge.subprocess, "run",
                        lambda cmd, **k: calls.append(cmd)
                        or subprocess.CompletedProcess(cmd, 0, "", ""))
    monkeypatch.setattr(footage_bridge, "_ssh",
                        lambda cmd, **k: calls.append(cmd)
                        or subprocess.CompletedProcess(cmd, 0, "", ""))

    status = footage_bridge.push_staged(
        tmp_path / "t.mp4", {"game_id": "t9", "sport": "tennis"})

    scp = [c for c in calls if isinstance(c, list) and c[0] == "scp"][0]
    assert scp[-1].endswith("/tennis__t9.mp4.part")
    assert any(isinstance(c, str) and c.startswith("mv ") for c in calls)
    assert status == "staged"


def test_failed_rename_does_not_report_success_or_leave_a_part_file(
        monkeypatch, tmp_path):
    removed = []

    def fake_ssh(cmd, **kwargs):
        if cmd.startswith("mv "):
            return subprocess.CompletedProcess(cmd, 1, "", "no space left")
        removed.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(footage_bridge.subprocess, "run",
                        lambda cmd, **k: subprocess.CompletedProcess(cmd, 0, "", ""))
    monkeypatch.setattr(footage_bridge, "_ssh", fake_ssh)

    try:
        footage_bridge.push_staged(tmp_path / "t.mp4",
                                   {"game_id": "t9", "sport": "tennis"})
        raise AssertionError("a failed rename must not report staged")
    except RuntimeError as exc:
        assert "no space left" in str(exc)
    assert any(c.startswith("rm -f") and c.endswith(".part") for c in removed)


def test_decoupled_queue_keeps_a_reference_clip(monkeypatch, tmp_path):
    """Reference retention keyed on 'tracked'; decoupled runs return 'staged',
    so every reference clip would have been deleted instead of kept."""
    queue = tmp_path / "footage_queue_tennis.json"
    queue.write_text(json.dumps([{"game_id": "t1", "sport": "tennis",
                                  "url": "u"}]), encoding="utf-8")
    kept = []
    monkeypatch.setattr(footage_bridge, "tracked_row_counts", lambda: {})
    monkeypatch.setattr(footage_bridge, "download_local",
                        lambda item: tmp_path / "t1.mp4")
    monkeypatch.setattr(footage_bridge, "push_staged", lambda l, i: "staged")
    monkeypatch.setattr(footage_bridge, "keep_reference",
                        lambda l, s: kept.append(s) or True)
    monkeypatch.setattr(footage_bridge, "_record", lambda e: None)

    footage_bridge.run_queue(queue, limit=1, decouple=True)

    assert kept == ["tennis"]


def test_short_videos_are_never_sectioned():
    """A section starting at 10:00 downloads NOTHING from a highlight reel."""
    assert footage_bridge.plan_section(9 * 60) is None
    assert footage_bridge.plan_section(0) is None
    assert footage_bridge.plan_section(None) is None


def test_full_game_is_sectioned_to_the_frames_we_actually_track():
    section = footage_bridge.plan_section(85 * 60)

    assert section == "*00:10:00-00:26:00"


def test_section_start_scales_down_for_mid_length_videos():
    """15% in, so a 30-minute video does not start past its own midpoint."""
    assert footage_bridge.plan_section(30 * 60) == "*00:04:30-00:20:30"


def test_unparseable_duration_falls_back_to_whole_file(monkeypatch):
    monkeypatch.setattr(footage_bridge.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, "NA", ""))

    assert footage_bridge.probe_duration("https://youtu.be/x") == 0.0


def test_section_attempt_is_tried_first_and_falls_back_to_full_download(
        monkeypatch, tmp_path):
    """If sectioning fails the game must still be fetchable in full."""
    monkeypatch.setattr(footage_bridge, "LOCAL_STAGE", tmp_path)
    monkeypatch.setattr(footage_bridge, "probe_duration", lambda url: 85 * 60)
    seen = []

    def fake_run(command, **kwargs):
        seen.append(command)
        if "--download-sections" in command:
            raise subprocess.CalledProcessError(1, command, "", "ERROR: 403")
        (tmp_path / "g1.mp4").write_bytes(b"video")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(footage_bridge.subprocess, "run", fake_run)
    footage_bridge.download_local({"game_id": "g1", "sport": "tennis",
                                   "url": "https://youtu.be/x"})

    assert "--download-sections" in seen[0]
    assert "--download-sections" not in seen[-1]


def test_section_download_uses_the_web_client(monkeypatch, tmp_path):
    """ffmpeg gets 403 from the default client's URL; only web works."""
    monkeypatch.setattr(footage_bridge, "LOCAL_STAGE", tmp_path)
    monkeypatch.setattr(footage_bridge, "probe_duration", lambda url: 85 * 60)
    seen = []

    def fake_run(command, **kwargs):
        seen.append(command)
        (tmp_path / "g1.mp4").write_bytes(b"video")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(footage_bridge.subprocess, "run", fake_run)
    footage_bridge.download_local({"game_id": "g1", "sport": "tennis",
                                   "url": "https://youtu.be/x"})

    assert "youtube:player_client=web" in seen[0]


def test_direct_cdn_media_is_never_probed_for_duration(monkeypatch, tmp_path):
    """MLB CDN mp4s have no extractor; a duration probe just wastes a request."""
    monkeypatch.setattr(footage_bridge, "LOCAL_STAGE", tmp_path)
    monkeypatch.setattr(footage_bridge, "probe_duration",
                        lambda url: (_ for _ in ()).throw(
                            AssertionError("must not probe a direct file")))

    def fake_run(command, **kwargs):
        (tmp_path / "m1.mp4").write_bytes(b"video")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(footage_bridge.subprocess, "run", fake_run)
    footage_bridge.download_local({"game_id": "m1", "sport": "mlb",
                                   "url": "https://mlb-cuts-diamond.mlb.com/a.mp4"})
