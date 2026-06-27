"""Per-file test: scripts.platformkit.pm_trading.auto_loop -- guarded steps.

Tests that:
  1. When one guarded step raises (e.g. line_tick), the others still run and
     their results land in the output dict (including scoreboard write).
  2. scoreboard.write_scoreboard is called each cycle and its result appears in
     out["scoreboard"].
  3. line_snapshot_daemon.poll_once is called (once per active sport) each cycle
     and its aggregated result appears in out["line_tick"].
  4. run_once returns even when ALL optional steps throw.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_auto_loop_steps.py -q
"""
from __future__ import annotations

import importlib
import types
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

# Capture the REAL _write_frontend_snapshots before the autouse fixture stubs the module
# attribute, so the direct unit tests below can exercise the genuine function (it still
# reads the live module globals, so per-test patches of _SNAPSHOT_SPORTS etc. apply).
import scripts.platformkit.pm_trading.auto_loop as _al_mod  # noqa: E402
_REAL_WRITE_SNAPSHOTS = _al_mod._write_frontend_snapshots


# ---------------------------------------------------------------------------
# Helpers: stub out the mandatory core steps (paper / grade / improve /
# grade_summary) so the tests focus on the new guarded steps.
# ---------------------------------------------------------------------------

def _core_stubs():
    """Return (paper_stub, grade_stub, improve_stub, summary_stub)."""
    return (
        MagicMock(return_value={"status": "ok", "n_recorded": 0}),
        MagicMock(return_value={"status": "ok"}),
        MagicMock(return_value={"status": "ok"}),
        MagicMock(return_value={"n": 0, "mean_clv_pct": None}),
    )


def _import_loop():
    """Fresh import of auto_loop (avoids cached module state across tests)."""
    import scripts.platformkit.pm_trading.auto_loop as mod
    return mod


@pytest.fixture(autouse=True)
def _stub_prop_steps():
    """Stub the prop place/settle steps (they hit the network) so these tests -- which
    focus on line_tick/scoreboard/ratchet -- stay fast + offline. A dedicated test below
    asserts the prop steps ARE wired into run_once."""
    import scripts.platformkit.pm_trading.auto_loop as mod
    with patch.object(mod, "_place_props",
                      MagicMock(return_value={"status": "ok", "n_placed": 0})), \
         patch.object(mod, "_place_pm_games",
                      MagicMock(return_value={"status": "ok", "placed": 0})), \
         patch.object(mod, "_place_ingame_props",
                      MagicMock(return_value={"status": "ok", "placed": 0})), \
         patch.object(mod, "_write_frontend_snapshots",
                      MagicMock(return_value={"mlb": "fresh"})), \
         patch.object(mod, "_settle_props",
                      MagicMock(return_value={"status": "ok", "n_settled_now": 0,
                                              "n_pending": 0})), \
         patch.object(mod, "_prop_improve",
                      MagicMock(return_value={"verdicts": {"mlb": "INSUFFICIENT_DATA"}})), \
         patch.object(mod, "_prop_history_improve",
                      MagicMock(return_value={"verdict": "HOLD", "source": "history",
                                              "n_rows": 0})):
        yield


# ---------------------------------------------------------------------------
# 1. line_tick throwing does NOT stop scoreboard from running
# ---------------------------------------------------------------------------

def test_line_tick_throw_does_not_stop_scoreboard():
    """A line_tick error is captured; scoreboard still runs and succeeds."""
    mod = _import_loop()
    paper_s, grade_s, improve_s, summary_s = _core_stubs()

    sb_result = {"status": "ok", "path": "/tmp/grade_summary.json"}
    line_tick_raises = MagicMock(side_effect=RuntimeError("feed down"))
    write_sb = MagicMock(return_value=sb_result)

    with patch.object(mod, "run_paper_cycle", paper_s), \
         patch.object(mod, "grade_open_bets", grade_s), \
         patch.object(mod, "improve_all", improve_s), \
         patch.object(mod, "grade_summary", summary_s), \
         patch.object(mod, "_line_tick", line_tick_raises), \
         patch.object(mod, "_write_scoreboard", write_sb):
        out = mod.run_once()

    assert "scoreboard" in out, "scoreboard key missing after line_tick error"
    assert out["scoreboard"] == sb_result
    # line_tick error is captured, not re-raised
    assert "line_tick" in out
    assert "error" in str(out["line_tick"].get("status", "")).lower() \
           or "error" in str(out["line_tick"].get("reason", "")).lower()


# ---------------------------------------------------------------------------
# 2. scoreboard throwing does NOT stop line_tick from running
# ---------------------------------------------------------------------------

def test_scoreboard_throw_does_not_stop_line_tick():
    """A scoreboard error is captured; line_tick still ran and its result is present."""
    mod = _import_loop()
    paper_s, grade_s, improve_s, summary_s = _core_stubs()

    lt_result = {"status": "ok", "sports": [{"sport": "nba", "status": "ok"}]}
    line_tick_ok = MagicMock(return_value=lt_result)
    write_sb_raises = MagicMock(side_effect=IOError("disk full"))

    with patch.object(mod, "run_paper_cycle", paper_s), \
         patch.object(mod, "grade_open_bets", grade_s), \
         patch.object(mod, "improve_all", improve_s), \
         patch.object(mod, "grade_summary", summary_s), \
         patch.object(mod, "_line_tick", line_tick_ok), \
         patch.object(mod, "_write_scoreboard", write_sb_raises):
        out = mod.run_once()

    assert "line_tick" in out
    assert out["line_tick"] == lt_result
    assert "scoreboard" in out
    # error is captured in the scoreboard slot
    assert "error" in str(out["scoreboard"].get("status", "")).lower() \
           or "error" in str(out["scoreboard"].get("reason", "")).lower()


# ---------------------------------------------------------------------------
# 3. scoreboard is written every cycle (normal path)
# ---------------------------------------------------------------------------

def test_scoreboard_written_each_cycle():
    """_write_scoreboard is called exactly once per run_once()."""
    mod = _import_loop()
    paper_s, grade_s, improve_s, summary_s = _core_stubs()

    sb_result = {"status": "ok", "path": "/tmp/gs.json"}
    write_sb = MagicMock(return_value=sb_result)
    lt_result = {"status": "ok", "sports": []}
    line_tick_ok = MagicMock(return_value=lt_result)

    with patch.object(mod, "run_paper_cycle", paper_s), \
         patch.object(mod, "grade_open_bets", grade_s), \
         patch.object(mod, "improve_all", improve_s), \
         patch.object(mod, "grade_summary", summary_s), \
         patch.object(mod, "_line_tick", line_tick_ok), \
         patch.object(mod, "_write_scoreboard", write_sb):
        out = mod.run_once()

    write_sb.assert_called_once()
    assert out["scoreboard"]["status"] == "ok"


# ---------------------------------------------------------------------------
# 4. poll_once called per sport in _line_tick (unit test of _line_tick itself)
# ---------------------------------------------------------------------------

def test_line_tick_calls_poll_once_per_sport():
    """_line_tick calls poll_once for each sport and aggregates results."""
    mod = _import_loop()
    sports = ("nba", "mlb")

    mock_poll = MagicMock(
        side_effect=lambda sport, **kw: {"sport": sport, "status": "ok", "logged": 2})

    # Patch the import inside _line_tick
    fake_daemon_mod = types.ModuleType("line_snapshot_daemon")
    fake_daemon_mod.poll_once = mock_poll  # type: ignore[attr-defined]

    import sys
    orig = sys.modules.get("scripts.platformkit.odds_provider.line_snapshot_daemon")
    sys.modules["scripts.platformkit.odds_provider.line_snapshot_daemon"] = fake_daemon_mod
    try:
        result = mod._line_tick(sports=sports)
    finally:
        if orig is None:
            del sys.modules["scripts.platformkit.odds_provider.line_snapshot_daemon"]
        else:
            sys.modules["scripts.platformkit.odds_provider.line_snapshot_daemon"] = orig

    assert result["status"] == "ok"
    assert len(result["sports"]) == len(sports)
    sport_names = {r["sport"] for r in result["sports"]}
    assert sport_names == set(sports)
    assert mock_poll.call_count == len(sports)


# ---------------------------------------------------------------------------
# 5. run_once completes when ALL optional steps throw
# ---------------------------------------------------------------------------

def test_run_once_survives_all_optional_steps_throwing():
    """run_once returns a dict even when both line_tick and scoreboard throw."""
    mod = _import_loop()
    paper_s, grade_s, improve_s, summary_s = _core_stubs()

    with patch.object(mod, "run_paper_cycle", paper_s), \
         patch.object(mod, "grade_open_bets", grade_s), \
         patch.object(mod, "improve_all", improve_s), \
         patch.object(mod, "grade_summary", summary_s), \
         patch.object(mod, "_line_tick",
                      MagicMock(side_effect=Exception("boom"))), \
         patch.object(mod, "_write_scoreboard",
                      MagicMock(side_effect=Exception("also boom"))):
        out = mod.run_once()

    # Core steps ran
    assert paper_s.called
    assert grade_s.called
    # Both error slots present, no exception propagated
    assert "line_tick" in out
    assert "scoreboard" in out
    assert isinstance(out, dict)


# ---------------------------------------------------------------------------
# 6. line_tick: a per-sport poll_once error is isolated (other sports still run)
# ---------------------------------------------------------------------------

def test_line_tick_isolates_per_sport_error():
    """When poll_once raises for one sport, the other sports still capture."""
    mod = _import_loop()
    sports = ("nba", "mlb", "soccer")

    call_count = {"n": 0}

    def _poll(sport, **kw):
        call_count["n"] += 1
        if sport == "mlb":
            raise ConnectionError("mlb feed down")
        return {"sport": sport, "status": "ok", "logged": 1}

    fake_daemon_mod = types.ModuleType("line_snapshot_daemon")
    fake_daemon_mod.poll_once = _poll  # type: ignore[attr-defined]

    import sys
    orig = sys.modules.get("scripts.platformkit.odds_provider.line_snapshot_daemon")
    sys.modules["scripts.platformkit.odds_provider.line_snapshot_daemon"] = fake_daemon_mod
    try:
        result = mod._line_tick(sports=sports)
    finally:
        if orig is None:
            del sys.modules["scripts.platformkit.odds_provider.line_snapshot_daemon"]
        else:
            sys.modules["scripts.platformkit.odds_provider.line_snapshot_daemon"] = orig

    # All three sports attempted
    assert call_count["n"] == 3
    # All three sport results present (error captured, not re-raised)
    assert len(result["sports"]) == 3
    mlb_rep = next(r for r in result["sports"] if r["sport"] == "mlb")
    assert "error" in mlb_rep.get("status", "").lower()
    ok_sports = [r for r in result["sports"] if r["sport"] != "mlb"]
    assert all(r["status"] == "ok" for r in ok_sports)


# ---------------------------------------------------------------------------
# 7. HONESTY: the dead ratchet step is gone -- the cycle reports only the steps
#    that actually run. The live self-improvement ratchet IS improve_all (step 3).
# ---------------------------------------------------------------------------

def test_no_dead_ratchet_step_in_cycle():
    """run_once must NOT emit a separate 'ratchet' key (the dead no-op is removed).

    The earlier _ratchet_tick imported a never-built
    scripts.platformkit.pm_trading.ratchet_candidate.pending_candidate provider and
    returned {"status":"no_candidate_provider"} every cycle -- advertising a step
    that never ran. The live ratchet is improve_all (out["improve"]).
    """
    mod = _import_loop()
    paper_s, grade_s, improve_s, summary_s = _core_stubs()

    lt_result = {"status": "ok", "sports": []}
    sb_result = {"status": "ok", "path": "/tmp/gs.json"}

    with patch.object(mod, "run_paper_cycle", paper_s), \
         patch.object(mod, "grade_open_bets", grade_s), \
         patch.object(mod, "improve_all", improve_s), \
         patch.object(mod, "grade_summary", summary_s), \
         patch.object(mod, "_line_tick", MagicMock(return_value=lt_result)), \
         patch.object(mod, "_write_scoreboard", MagicMock(return_value=sb_result)):
        out = mod.run_once()

    assert "ratchet" not in out, "dead ratchet step should be removed from the cycle"
    # The live self-improvement ratchet is step 3 (improve_all) and IS reported.
    assert improve_s.called
    assert "improve" in out
    # The dead helper itself must no longer exist on the module.
    assert not hasattr(mod, "_ratchet_tick"), "_ratchet_tick should be deleted"


def test_prop_steps_are_wired_into_run_once():
    """run_once must run place_props + settle_props as guarded steps and surface their
    results -- props execute independently in the live m1_paper loop."""
    mod = _import_loop()
    paper_s, grade_s, improve_s, summary_s = _core_stubs()
    place = MagicMock(return_value={"status": "ok", "n_placed": 3})
    settle = MagicMock(return_value={"status": "ok", "n_settled_now": 1, "n_pending": 2})
    with patch.object(mod, "run_paper_cycle", paper_s), \
         patch.object(mod, "grade_open_bets", grade_s), \
         patch.object(mod, "improve_all", improve_s), \
         patch.object(mod, "grade_summary", summary_s), \
         patch.object(mod, "_place_props", place), \
         patch.object(mod, "_settle_props", settle), \
         patch.object(mod, "_line_tick", MagicMock(return_value={"status": "ok", "sports": []})), \
         patch.object(mod, "_write_scoreboard", MagicMock(return_value={"status": "ok"})):
        out = mod.run_once()
    place.assert_called_once()
    settle.assert_called_once()
    assert out["place_props"]["n_placed"] == 3
    assert out["settle_props"]["n_settled_now"] == 1


def test_ingame_props_wired_into_run_once():
    """run_once runs the IN-GAME prop trader as a guarded step and surfaces its result --
    in-game props execute independently each cycle in the live m1_paper loop."""
    mod = _import_loop()
    paper_s, grade_s, improve_s, summary_s = _core_stubs()
    ingame = MagicMock(return_value={"status": "ok", "placed": 4, "live_games": 3,
                                     "channel": "paper_ingame_prop"})
    with patch.object(mod, "run_paper_cycle", paper_s), \
         patch.object(mod, "grade_open_bets", grade_s), \
         patch.object(mod, "improve_all", improve_s), \
         patch.object(mod, "grade_summary", summary_s), \
         patch.object(mod, "_place_ingame_props", ingame), \
         patch.object(mod, "_line_tick", MagicMock(return_value={"status": "ok", "sports": []})), \
         patch.object(mod, "_write_scoreboard", MagicMock(return_value={"status": "ok"})):
        out = mod.run_once()
    ingame.assert_called_once()
    assert out["place_ingame_props"]["placed"] == 4
    assert out["place_ingame_props"]["channel"] == "paper_ingame_prop"


def test_prop_improve_is_wired_into_run_once():
    """run_once must run the PROP calibration ratchet as a guarded step and surface its
    verdicts -- props 'get better' independently each cycle in the live m1_paper loop."""
    mod = _import_loop()
    paper_s, grade_s, improve_s, summary_s = _core_stubs()
    prop_improve = MagicMock(return_value={"verdicts": {"mlb": "SHIP"}})
    with patch.object(mod, "run_paper_cycle", paper_s), \
         patch.object(mod, "grade_open_bets", grade_s), \
         patch.object(mod, "improve_all", improve_s), \
         patch.object(mod, "grade_summary", summary_s), \
         patch.object(mod, "_prop_improve", prop_improve), \
         patch.object(mod, "_line_tick", MagicMock(return_value={"status": "ok", "sports": []})), \
         patch.object(mod, "_write_scoreboard", MagicMock(return_value={"status": "ok"})):
        out = mod.run_once()
    prop_improve.assert_called_once()
    assert out["prop_improve"]["verdicts"]["mlb"] == "SHIP"


def test_prop_history_improve_is_wired_into_run_once():
    """run_once must run the HISTORICAL prop backtest fold (props get better from OLD games,
    no live games needed) as a guarded step and surface its verdict."""
    mod = _import_loop()
    paper_s, grade_s, improve_s, summary_s = _core_stubs()
    hist = MagicMock(return_value={"verdict": "HOLD", "source": "history", "n_rows": 3000})
    with patch.object(mod, "run_paper_cycle", paper_s), \
         patch.object(mod, "grade_open_bets", grade_s), \
         patch.object(mod, "improve_all", improve_s), \
         patch.object(mod, "grade_summary", summary_s), \
         patch.object(mod, "_prop_history_improve", hist), \
         patch.object(mod, "_line_tick", MagicMock(return_value={"status": "ok", "sports": []})), \
         patch.object(mod, "_write_scoreboard", MagicMock(return_value={"status": "ok"})):
        out = mod.run_once()
    hist.assert_called_once()
    assert out["prop_history_improve"]["source"] == "history"
    assert out["prop_history_improve"]["n_rows"] == 3000


def test_snapshots_rebuild_when_missing(tmp_path):
    """A missing snapshot file triggers build_snapshot and is reported 'written'."""
    mod = _import_loop()
    import scripts.platformkit.frontend.snapshot_writer as sw
    build = MagicMock(return_value={"status": "ok"})
    with patch.object(sw, "DEFAULT_OUT_DIR", tmp_path), \
         patch.object(sw, "build_snapshot", build), \
         patch.object(mod, "_SNAPSHOT_SPORTS", ("mlb",)):
        out = _REAL_WRITE_SNAPSHOTS()
    build.assert_called_once_with("mlb")
    assert out["mlb"] == "written"


def test_snapshots_skip_fresh(tmp_path):
    """A recently-written snapshot is left alone (no rebuild) and reported 'fresh'."""
    mod = _import_loop()
    import scripts.platformkit.frontend.snapshot_writer as sw
    (tmp_path / "mlb.json").write_text("{}", encoding="ascii")  # just-written -> fresh
    build = MagicMock(return_value={"status": "ok"})
    with patch.object(sw, "DEFAULT_OUT_DIR", tmp_path), \
         patch.object(sw, "build_snapshot", build), \
         patch.object(mod, "_SNAPSHOT_SPORTS", ("mlb",)), \
         patch.object(mod, "_SNAPSHOT_MAX_AGE_SEC", 9999.0):
        out = _REAL_WRITE_SNAPSHOTS()
    build.assert_not_called()
    assert out["mlb"] == "fresh"


def test_snapshots_per_sport_error_isolated(tmp_path):
    """One sport's build raising never stops the other; the failure is captured per-sport."""
    mod = _import_loop()
    import scripts.platformkit.frontend.snapshot_writer as sw

    def _build(sport):
        if sport == "mlb":
            raise RuntimeError("feed down")
        return {"status": "ok"}

    with patch.object(sw, "DEFAULT_OUT_DIR", tmp_path), \
         patch.object(sw, "build_snapshot", MagicMock(side_effect=_build)), \
         patch.object(mod, "_SNAPSHOT_SPORTS", ("mlb", "soccer_intl")):
        out = _REAL_WRITE_SNAPSHOTS()
    assert out["mlb"].startswith("error:")
    assert out["soccer_intl"] == "written"


def test_snapshots_wired_into_run_once():
    """run_once runs the frontend-snapshot refresh as a guarded step and surfaces it."""
    mod = _import_loop()
    paper_s, grade_s, improve_s, summary_s = _core_stubs()
    snaps = MagicMock(return_value={"mlb": "written", "soccer_intl": "fresh"})
    with patch.object(mod, "run_paper_cycle", paper_s), \
         patch.object(mod, "grade_open_bets", grade_s), \
         patch.object(mod, "improve_all", improve_s), \
         patch.object(mod, "grade_summary", summary_s), \
         patch.object(mod, "_write_frontend_snapshots", snaps), \
         patch.object(mod, "_line_tick", MagicMock(return_value={"status": "ok", "sports": []})), \
         patch.object(mod, "_write_scoreboard", MagicMock(return_value={"status": "ok"})):
        out = mod.run_once()
    snaps.assert_called_once()
    assert out["snapshots"]["mlb"] == "written"


def test_print_cycle_has_no_ratchet_field(capsys):
    """The printed cycle summary must not advertise a 'ratchet=' field."""
    mod = _import_loop()
    out = {
        "summary": {"n": 0, "hit_rate": None, "mean_clv_pct": None},
        "paper": {"recorded": 0},
        "improve": {"status": "ok"},
        "line_tick": {"status": "ok"},
        "scoreboard": {"status": "ok"},
    }
    mod._print_cycle(out)
    printed = capsys.readouterr().out
    assert "ratchet" not in printed.lower()
    assert "improve=" in printed
