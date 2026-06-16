"""Per-file test for run_capture.py -- the START-THE-CLOCK runner (DRY-RUN smoke).

Asserts the runner's load-bearing forward-capture contract WITHOUT any network or secret:
  - one DRY-RUN tick polls the MockFeed, archives the tape to a tmp data dir, and logs the
    pregame prediction to a tmp ledger with a forward pred_ts (the vintage clock);
  - the logged ledger row carries pred_ts + calibrated_prob copied VERBATIM (no LLM number);
  - the DRY RUN banner is printed and names the env switch + 'WIRE A REAL FEED';
  - re-running the SAME tick is idempotent (archive sha + ledger pred_id collapse);
  - when the real-feed env key IS set the runner selects RealFeed, whose poll() raises
    NotImplementedError (no live call) -- the clock only starts when a human wires it;
  - NO $ / ROI / edge field appears in any tick summary.

Hermetic: tmp dirs for both the archive and the ledger; MockFeed is deterministic; the loop
sleep + print are injected so nothing waits and output is captured. ASCII only.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

_HERE = pathlib.Path(__file__).resolve()
_FC = _HERE.parents[1]                         # scripts/platformkit/forward_capture
_PKIT = _FC.parent                             # scripts/platformkit
for _p in (_FC, _PKIT / "ledger"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import run_capture as rc          # noqa: E402
import capture as cap             # noqa: E402
from ledger import read_ledger    # noqa: E402  the EXISTING X3 ledger, READ-ONLY here


_BANNED = ("edge", "roi", "ev", "stake", "units", "kelly", "dollar", "profit")


def _dirs(tmp_path):
    return str(tmp_path / "archive"), str(tmp_path / "ledger")


def test_dry_run_tick_archives_and_logs(tmp_path):
    """One DRY-RUN tick: snapshots archived + pregame prediction logged with pred_ts."""
    arch, led = _dirs(tmp_path)
    s = rc.run_tick(predictions=rc._DRY_PREDICTIONS, quotes=rc._DRY_QUOTES,
                    archive_dir=arch, ledger_dir=led, model_version="testsha")
    assert s["feed"] == "mock"                                   # DRY RUN feed
    assert s["snapshots_archived"] == len(rc._DRY_QUOTES)
    assert s["predictions_logged"] == 1 and len(s["pred_ids"]) == 1
    assert s["pred_ts"]                                          # the vintage clock was stamped
    # the prediction landed in the EXISTING ledger with pred_ts + verbatim calibrated_prob
    df = read_ledger(base_dir=led)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["pred_id"] == s["pred_ids"][0]
    assert row["pred_ts"] == s["pred_ts"]
    assert float(row["calibrated_prob"]) == 0.55                # copied verbatim, not authored
    assert row["devig_close_prob"] is None or str(row["devig_close_prob"]) == "None" \
        or row["devig_close_prob"] != row["devig_close_prob"]   # ungraded (None/NaN) at log time
    # honesty: no $ / edge field anywhere in the tick summary
    for k in s:
        assert str(k).lower() not in _BANNED


def test_tick_is_idempotent(tmp_path):
    """Re-running the SAME tick double-logs nothing: archive sha + ledger pred_id collapse."""
    arch, led = _dirs(tmp_path)
    rc.run_tick(predictions=rc._DRY_PREDICTIONS, quotes=rc._DRY_QUOTES,
                archive_dir=arch, ledger_dir=led, model_version="testsha")
    rc.run_tick(predictions=rc._DRY_PREDICTIONS, quotes=rc._DRY_QUOTES,
                archive_dir=arch, ledger_dir=led, model_version="testsha")
    df = read_ledger(base_dir=led)
    assert len(df) == 1                                         # idempotent ledger row
    import archive as arc_mod                                   # noqa: E402
    snaps = arc_mod.read_archive("nba", base_dir=arch)
    assert len(snaps) == len(rc._DRY_QUOTES)                    # idempotent archive (no dupes)


def test_dry_run_banner_prints_switch(tmp_path, monkeypatch):
    """The DRY RUN banner is printed once and names the env switch + WIRE A REAL FEED."""
    monkeypatch.delenv(cap.REAL_FEED_ENV, raising=False)        # ensure no real feed
    arch, led = _dirs(tmp_path)
    out_lines = []
    rc.run_loop(predictions=rc._DRY_PREDICTIONS, quotes=rc._DRY_QUOTES, interval=0.0,
                max_ticks=1, archive_dir=arch, ledger_dir=led, dry_run=True,
                sleep=lambda *_: None, out=out_lines.append)
    blob = "\n".join(out_lines)
    assert "DRY RUN" in blob
    assert "WIRE A REAL FEED" in blob
    assert cap.REAL_FEED_ENV in blob
    assert "tick=0" in blob                                     # one tick summary printed


def test_loop_runs_finite_and_logs_each_tick(tmp_path):
    """run_loop honours max_ticks, archives each tick, and never sleeps in the test."""
    arch, led = _dirs(tmp_path)
    slept = []
    summaries = rc.run_loop(predictions=[], quotes=rc._DRY_QUOTES, interval=5.0,
                            max_ticks=3, archive_dir=arch, ledger_dir=led, dry_run=True,
                            sleep=lambda s: slept.append(s), out=lambda *_: None)
    assert len(summaries) == 3
    assert slept == [5.0, 5.0]                                  # slept between, not after last
    assert all(x["snapshots_archived"] == len(rc._DRY_QUOTES) for x in summaries)


def test_real_feed_selected_when_key_set_and_raises(tmp_path, monkeypatch):
    """With the env key set the runner selects RealFeed; its poll() raises (no live call)."""
    monkeypatch.setenv(cap.REAL_FEED_ENV, "DUMMY_TEST_KEY_NOT_A_REAL_SECRET")
    assert cap.has_real_feed() is True
    feed = cap.build_feed(quotes=rc._DRY_QUOTES)
    assert feed.name == "real"
    arch, led = _dirs(tmp_path)
    with pytest.raises(NotImplementedError):
        rc.run_tick(quotes=rc._DRY_QUOTES, archive_dir=arch, ledger_dir=led,
                    model_version="testsha")                   # RealFeed.poll() raises


def test_main_dry_run_smoke(tmp_path, monkeypatch, capsys):
    """End-to-end --once main(): DRY RUN, archives + logs, prints the banner, exits 0."""
    monkeypatch.delenv(cap.REAL_FEED_ENV, raising=False)
    arch, led = _dirs(tmp_path)
    code = rc.main(["--once", "--archive-dir", arch, "--ledger-dir", led])
    assert code == 0
    captured = capsys.readouterr().out
    assert "DRY RUN" in captured
    assert len(read_ledger(base_dir=led)) == 1                 # the DRY-RUN prediction logged
