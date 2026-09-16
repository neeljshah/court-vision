"""Per-file test for scripts/platformkit/segment_ingame_join.py.

Synthetic tick paths only -- no read of data/. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/test_segment_ingame_join.py -q
"""
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.segment_ingame_join import (  # noqa: E402
    GAP_HOURS, main, run_sport, segment_end, segment_file, select_segment,
    split_segments)


def tick(ts, home=None, away=None, inning=None, outcome=0.0, close_ts=None):
    if home is None:
        state = "live"
    else:
        state = "home_score=%.1f away_score=%.1f inning=%d" % (home, away, inning or 1)
    return {"sport": "mlb", "ts": ts, "state_summary": state, "outcome": outcome,
            "model_prob": 0.5, "market_prob": 0.5, "close_ts": close_ts or ts}


def test_single_game_is_one_segment():
    rows = [tick("2026-07-02T18:00:00Z", 0, 0, 1),
            tick("2026-07-02T19:00:00Z", 1, 0, 4),
            tick("2026-07-02T20:00:00Z", 3, 1, 9)]
    assert len(split_segments(rows)) == 1


def test_score_decrease_starts_a_new_segment():
    rows = [tick("2026-07-01T20:00:00Z", 2, 5, 9),
            tick("2026-07-01T22:00:00Z", 0, 0, 1)]
    assert len(split_segments(rows)) == 2


def test_clock_decrease_starts_a_new_segment():
    rows = [tick("2026-07-02T18:00:00Z", 1, 1, 8),
            tick("2026-07-02T19:00:00Z", 1, 1, 2)]
    assert len(split_segments(rows)) == 2


def test_long_wall_clock_gap_starts_a_new_segment():
    rows = [tick("2026-07-01T20:00:00Z", 0, 0, 1),
            tick("2026-07-02T20:00:00Z", 0, 0, 1)]
    assert len(split_segments(rows)) == 2
    # a delay shorter than the threshold does not split
    short = [tick("2026-07-02T18:00:00Z", 0, 0, 1),
             tick("2026-07-02T%02d:00:00Z" % (18 + int(GAP_HOURS) - 1), 0, 0, 2)]
    assert len(split_segments(short)) == 1


def test_stateless_ticks_never_break_and_join_the_open_segment():
    rows = [tick("2026-07-02T18:00:00Z", 0, 0, 1),
            tick("2026-07-02T18:10:00Z"),          # stateless
            tick("2026-07-02T18:20:00Z", 1, 0, 3)]
    segments = split_segments(rows)
    assert len(segments) == 1 and len(segments[0]) == 3


def test_segment_end_reads_the_last_stated_tick_not_a_trailing_stateless_one():
    rows = [tick("2026-07-02T18:00:00Z", 4, 1, 9), tick("2026-07-02T18:05:00Z")]
    side, when = segment_end(rows)
    assert side == "home"
    assert when.hour == 18 and when.minute == 0
    assert segment_end([tick("2026-07-02T18:00:00Z")]) is None


def test_select_keeps_the_label_agreeing_segment_not_the_last_one():
    # segment 0 ends away-up (agrees with outcome 0.0 AND close_ts); segment 1 is a
    # later game ending home-up. The naive "last segment" rule would pick the wrong one.
    close = "2026-07-01T23:00:00Z"
    early = [tick("2026-07-01T20:00:00Z", 0, 0, 1, 0.0, close),
             tick(close, 1, 6, 9, 0.0, close)]
    late = [tick("2026-07-02T20:00:00Z", 0, 0, 1, 0.0, close),
            tick("2026-07-02T23:00:00Z", 7, 2, 9, 0.0, close)]
    index, reason = select_segment([early, late], 0.0, segment_end(early)[1])
    assert index == 0 and reason == "label_agrees"


def test_close_ts_breaks_a_tie_between_two_agreeing_segments():
    close = "2026-07-02T23:00:00Z"
    a = [tick("2026-07-01T23:00:00Z", 5, 1, 9, 1.0, close)]
    b = [tick(close, 4, 2, 9, 1.0, close)]
    index, reason = select_segment([a, b], 1.0, segment_end(b)[1])
    assert index == 1 and reason == "label_agrees"


def test_tied_final_against_a_decisive_label_is_kept_but_flagged():
    seg = [tick("2026-07-02T20:00:00Z", 2, 2, 6, 1.0)]
    index, reason = select_segment([seg], 1.0, segment_end(seg)[1])
    assert index == 0 and reason == "label_indeterminate_truncated"


def test_label_disagreement_is_quarantined_not_guessed():
    seg = [tick("2026-07-02T20:00:00Z", 1, 4, 9, 1.0)]  # away up, label says home
    index, reason = select_segment([seg], 1.0, segment_end(seg)[1])
    assert index is None and reason == "label_disagrees"
    # an entirely stateless path has nothing to attribute
    index, reason = select_segment([[tick("2026-07-02T20:00:00Z")]], 1.0, None)
    assert index is None and reason == "no_stated_tick"


def test_close_ts_anchor_beats_an_earlier_agreeing_segment():
    """The regression this ordering exists for: segment 0 AGREES with the label but
    segment 1 is the game that settled and was truncated at a tied score. Ranking by
    label agreement first would keep the contaminated segment."""
    close = "2026-07-02T23:00:00Z"
    early = [tick("2026-07-01T22:00:00Z", 5, 1, 9, 1.0, close)]
    true = [tick(close, 3, 3, 7, 1.0, close)]
    index, reason = select_segment([early, true], 1.0, segment_end(true)[1])
    assert index == 1 and reason == "label_indeterminate_truncated"


def test_two_equidistant_segments_are_quarantined():
    close = "2026-07-02T21:00:00Z"
    a = [tick("2026-07-02T20:00:00Z", 5, 1, 9, 1.0, close)]
    b = [tick("2026-07-02T22:00:00Z", 4, 2, 9, 1.0, close)]
    index, reason = select_segment([a, b], 1.0, segment_end(a)[1].replace(hour=21))
    assert index is None and reason == "ambiguous_two_segments_equidistant"


def test_end_to_end_writes_one_game_with_an_audit_header(tmp_path):
    close = "2026-07-02T23:00:00Z"
    rows = [tick("2026-07-01T20:00:00Z", 0, 0, 1, 0.0, close),      # other game
            tick("2026-07-01T22:30:00Z", 8, 0, 9, 0.0, close),
            tick("2026-07-02T20:00:00Z", 0, 0, 1, 0.0, close),      # this game
            tick("2026-07-02T21:00:00Z"),                            # stateless
            tick(close, 1, 6, 9, 0.0, close)]
    src = tmp_path / "mlb"
    src.mkdir()
    (src / "KXMLBGAME-26JUL021235PITPHI.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    summary = run_sport(tmp_path, "mlb")
    assert summary["files_in"] == 1 and summary["files_kept"] == 1
    assert summary["ticks_in"] == 5 and summary["ticks_kept"] == 3
    assert summary["stateless_in"] == 1 and summary["stateless_kept"] == 1

    out = tmp_path / "mlb_segmented" / "KXMLBGAME-26JUL021235PITPHI.jsonl"
    kept = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(kept) == 3
    audit = kept[0]["segment_audit"]
    assert audit["segments_found"] == 2 and audit["segment_kept"] == 1
    assert audit["ticks_dropped"] == 2 and audit["reason"] == "label_agrees"
    assert "segment_audit" not in kept[1]  # header field, first row only
    assert kept[0]["outcome"] == 0.0 and kept[0]["model_prob"] == 0.5  # schema intact
    # the source corpus is untouched
    assert len((src / "KXMLBGAME-26JUL021235PITPHI.jsonl").read_text(
        encoding="utf-8").splitlines()) == 5


def test_quarantined_file_writes_nothing(tmp_path):
    src = tmp_path / "mlb"
    src.mkdir()
    (src / "KXMLBGAME-26JUL021235AAABBB.jsonl").write_text(
        json.dumps(tick("2026-07-02T20:00:00Z", 1, 4, 9, 1.0)) + "\n", encoding="utf-8")
    summary = run_sport(tmp_path, "mlb")
    assert summary["files_kept"] == 0 and summary["files_quarantined"] == 1
    assert summary["quarantined"][0]["reason"] == "label_disagrees"
    assert not (tmp_path / "mlb_segmented").exists()


def test_empty_file_is_quarantined(tmp_path):
    src = tmp_path / "mlb"
    src.mkdir()
    (src / "KXMLBGAME-26JUL021235EMPTY0.jsonl").write_text("", encoding="utf-8")
    result = segment_file(src / "KXMLBGAME-26JUL021235EMPTY0.jsonl")
    assert result["audit"]["reason"] == "empty_file" and result["rows"] == []


def test_cli_dry_run_writes_no_corpus(tmp_path):
    src = tmp_path / "mlb"
    src.mkdir()
    (src / "KXMLBGAME-26JUL021235PITPHI.jsonl").write_text(
        json.dumps(tick("2026-07-02T23:00:00Z", 1, 6, 9, 0.0)) + "\n", encoding="utf-8")
    out_json = tmp_path / "report.json"
    assert main(["--root", str(tmp_path), "--sport", "mlb", "--dry-run",
                 "--out-json", str(out_json)]) == 0
    assert not (tmp_path / "mlb_segmented").exists()
    report = json.loads(out_json.read_text(encoding="utf-8"))
    assert report["sports"][0]["files_kept"] == 1


def test_cli_reports_no_data_for_a_missing_root(tmp_path):
    assert main(["--root", str(tmp_path / "nope")]) == 2
