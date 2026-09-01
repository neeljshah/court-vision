from pathlib import Path

from scripts.platformkit.footage_content_gate import GateMetrics, decide, quarantine, screen_fail_open, summary


def _metrics(surface, border=0.0, cuts=0.0):
    return GateMetrics([1.0, 2.0, 3.0], surface, [border] * 3, cuts)


def test_rejects_only_clear_non_sport_and_quarantines_with_reason(tmp_path: Path):
    verdict = decide(_metrics([0.0, 0.0, 0.0], border=0.25))
    video = tmp_path / "studio.mp4"
    video.write_bytes(b"evidence")

    moved = quarantine(video, verdict, tmp_path / "quarantine")

    assert verdict.decision == "reject"
    assert moved.read_bytes() == b"evidence"
    assert 'composited_template_no_playing_surface' in moved.with_suffix(".mp4.json").read_text()


def test_ambiguous_material_fails_open_and_summary_is_ingest_only():
    real = decide(_metrics([0.18, 0.30, 0.22]))
    uncertain = decide(_metrics([0.02, 0.03, 0.01], cuts=0.8))

    assert real.decision == "accept"
    assert uncertain.decision == "review"
    assert summary([real, uncertain]) == {"accept": 1, "review": 1, "reject": 0}


def test_unreadable_clip_fails_open_as_review(tmp_path: Path):
    verdict = screen_fail_open(tmp_path / "missing.mp4", "tennis")

    assert verdict.decision == "review"
    assert verdict.reason.startswith("screen_unavailable_fail_open")
