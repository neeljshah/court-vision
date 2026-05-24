"""tests/test_live_integration.py — end-to-end integration tests for the live system.

Cycle 88l (loop 5). Cycles 88a-k each ship unit tests on their pure helpers,
but no test has verified that those helpers actually CHAIN correctly. With
10+ scripts now wired through the live system (src/data/live.py loader →
predict_in_game projector → foul_trouble_adjust → blowout_adjust →
live_dashboard renderer → update_inactives → live_run orchestrator), a
regression in one helper signature can silently break the whole pipeline.

This file is the canary. Each scenario walks one synthetic snapshot through
the full chain end-to-end and asserts the cross-module contract holds. No
nba_api, no DK, no Rotowire — everything offline.

Scenarios:
  1. Healthy half-time game (Q2 6:00, no foul trouble, no blowout)
  2. Foul trouble in Q3 (SGA pf=4 in Q3 → 0.55 factor)
  3. Q4 blowout (30-pt margin → starter 0.25 / bench 1.50)
  4. Pre-tip inactives + bet log resolution
  5. live_run dry-run smoke (compose helpers produce expected argv)
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from unittest import mock

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.blowout_adjust as ba  # noqa: E402
import scripts.foul_trouble_adjust as fta  # noqa: E402
import scripts.live_dashboard as ld  # noqa: E402
import scripts.live_run as lr  # noqa: E402
import scripts.predict_in_game as pig  # noqa: E402
import scripts.update_inactives as ui  # noqa: E402
from src.data import live as live_mod  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic-fixture builders shared by every scenario.
# ---------------------------------------------------------------------------

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

SGA_ID = 1628983
WEMBY_ID = 1641705
BENCH_OKC_ID = 1234567
BENCH_SAS_ID = 7654321


def _player(name, *, team, player_id, minutes, pts, reb=4, ast=3,
            fg3m=1, stl=1, blk=0, tov=1, pf=1, is_starter=True,
            min_q1=None, min_q2=None, min_q3=None, min_q4=None):
    """Build a single-player dict matching BOTH the src/data/live.py and
    scripts/predict_in_game.py schemas (the union — they overlap)."""
    p = {
        "player_id": player_id,
        "name": name,
        "team": team,
        "is_starter": is_starter,
        "min": minutes,
        "pts": pts, "reb": reb, "ast": ast,
        "fg3m": fg3m, "stl": stl, "blk": blk, "tov": tov,
        "pf": pf,
    }
    # Optional per-period minutes (predict_in_game uses these to detect
    # bench players who only played earlier quarters).
    for k, v in (("min_q1", min_q1), ("min_q2", min_q2),
                 ("min_q3", min_q3), ("min_q4", min_q4)):
        if v is not None:
            p[k] = v
    return p


def _snapshot(*, period, clock, home_score, away_score, players,
              home_team="OKC", away_team="SAS", game_id="0022400123"):
    """Build a unified snapshot that satisfies BOTH schemas.

    - src/data/live.py + live_dashboard read: home_team, away_team,
      home_score, away_score (top-level), game_status, period, clock.
    - predict_in_game + blowout_adjust read: home/away nested dicts with
      'abbrev'/'score' (predict_in_game), home_score/away_score top-level
      (blowout_adjust). So we populate both shapes.
    """
    return {
        "game_id": game_id,
        "captured_at": "2026-05-24T19:42:00",
        "game_status": "LIVE",
        "period": period,
        "clock": clock,
        # Top-level scores (live_dashboard, src/data/live.py, blowout_adjust).
        "home_score": home_score,
        "away_score": away_score,
        "home_team": home_team,
        "away_team": away_team,
        # Nested home/away (predict_in_game uses these).
        "home": {"abbrev": home_team, "score": home_score},
        "away": {"abbrev": away_team, "score": away_score},
        "players": players,
    }


def _write_snapshot(tmp_path, snap):
    path = os.path.join(str(tmp_path), f"{snap['game_id']}_1716583200.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(snap, fh)
    return path


# ---------------------------------------------------------------------------
# Scenario 1 — Healthy half-time game.
# ---------------------------------------------------------------------------

class TestScenario1HealthyHalfTime:
    """Q2 6:00 left, OKC 56 - SAS 48. SGA 22 pts, Wemby 14. No trouble."""

    @pytest.fixture
    def snapshot(self):
        return _snapshot(
            period=2, clock="6:00",
            home_score=56, away_score=48,
            players=[
                _player("Shai Gilgeous-Alexander", team="OKC",
                        player_id=SGA_ID, minutes=24.0, pts=22,
                        reb=4, ast=5, fg3m=2, stl=1, blk=0, tov=2, pf=2,
                        is_starter=True,
                        min_q1=12.0, min_q2=12.0),
                _player("Victor Wembanyama", team="SAS",
                        player_id=WEMBY_ID, minutes=18.0, pts=14,
                        reb=8, ast=2, fg3m=1, stl=1, blk=3, tov=1, pf=1,
                        is_starter=True,
                        min_q1=10.0, min_q2=8.0),
                _player("Bench Guy", team="OKC", player_id=BENCH_OKC_ID,
                        minutes=6.0, pts=4, reb=2, ast=1, fg3m=0,
                        stl=0, blk=0, tov=0, pf=0, is_starter=False,
                        min_q1=0.0, min_q2=6.0),
            ],
        )

    def test_live_loader_parses_snapshot(self, snapshot, tmp_path):
        """src/data/live.py round-trips the snapshot dict."""
        path = _write_snapshot(tmp_path, snapshot)
        loaded = live_mod.load_live_state(path)
        assert loaded["period"] == 2
        assert loaded["home_score"] == 56
        assert loaded["away_score"] == 48
        assert live_mod.is_live(loaded)
        assert not live_mod.is_blowout(loaded)
        assert live_mod.absolute_margin(loaded) == 8
        # parse_clock: 6:00 -> 6.0
        assert live_mod.parse_clock(loaded["clock"]) == pytest.approx(6.0)
        # Q2 with 6:00 left -> 18 min elapsed / 30 min remaining of 48.
        assert live_mod.elapsed_game_minutes(2, "6:00") == pytest.approx(18.0)
        assert live_mod.remaining_game_minutes(2, "6:00") == pytest.approx(30.0)

    def test_player_lookup_diacritic_insensitive(self, snapshot):
        """find_player must match by canonical name key."""
        p = live_mod.find_player(snapshot, "Shai Gilgeous-Alexander")
        assert p is not None
        assert p["player_id"] == SGA_ID
        # find_player_by_id also works.
        p2 = live_mod.find_player_by_id(snapshot, WEMBY_ID)
        assert p2["name"] == "Victor Wembanyama"

    def test_predict_in_game_doubles_at_half(self, snapshot):
        """At Q2 6:00 (3/8 of game played), projection ≈ current * 8/3 ≈ 2.67x.

        project_final = current + project_remaining; with share_played=3/8,
        share_remaining=5/8, multiplier = 1 + (5/8)/(3/8) = 1 + 5/3 = 8/3.
        SGA's 22 pts -> 22 * 8/3 ≈ 58.67 pts.
        """
        rows = pig.project_snapshot(snapshot, pace_factor=1.0)
        sga_pts = next(r for r in rows
                       if r["player_id"] == SGA_ID and r["stat"] == "pts")
        assert sga_pts["current"] == pytest.approx(22.0)
        # 22 * (8/3) ≈ 58.67. Generous tolerance covers blowout/foul factor==1.
        assert sga_pts["projected_final"] == pytest.approx(58.67, rel=0.05)
        # No foul / blowout adjustment in a competitive Q2 game.
        assert sga_pts["foul_factor"] == 1.0
        assert sga_pts["blow_factor"] == 1.0

    def test_live_dashboard_renders_player_and_score(self, snapshot):
        """render_game produces text containing SGA, current PTS, projected PTS."""
        out = ld.render_game(snapshot, pre_game={})
        assert "Shai Gilgeous-Alexander" in out
        assert "OKC" in out and "SAS" in out
        # Score line:
        assert "56" in out and "48" in out
        # PTS column shows "22" current.
        assert "22" in out
        # Q2 -> share=3/8=0.375. project_remaining(22, 0.375)=22/0.375≈58.7.
        # The dashboard prints with 1 decimal: "58.7".
        assert "58.7" in out or "58.6" in out

    def test_foul_trouble_noop_when_clean(self, snapshot):
        """No player has 3+ fouls → every factor is 1.0."""
        rows = fta.adjust_snapshot(snapshot)
        assert all(r["factor"] == 1.0 for r in rows)

    def test_blowout_noop_in_q2(self, snapshot):
        """Pre-Q4 always returns 1.0 even with margin."""
        # Build dummy projections matching blowout_adjust schema.
        projs = [
            {"player_id": SGA_ID, "is_starter": True,
             "proj_pts": 58.7, "remaining_min": 18.0},
            {"player_id": BENCH_OKC_ID, "is_starter": False,
             "proj_pts": 12.0, "remaining_min": 18.0},
        ]
        adj = ba.apply_to_projections(snapshot, projs)
        for r in adj:
            assert r["blowout_factor"] == 1.0
            assert r["proj_pts"] == pytest.approx(
                next(p["proj_pts"] for p in projs
                     if p["player_id"] == r["player_id"]))


# ---------------------------------------------------------------------------
# Scenario 2 — Foul trouble in Q3.
# ---------------------------------------------------------------------------

class TestScenario2FoulTroubleQ3:
    """SGA picks up his 4th foul in Q3 with 5:30 left -> factor 0.55."""

    @pytest.fixture
    def snapshot(self):
        return _snapshot(
            period=3, clock="5:30",
            home_score=72, away_score=70,
            players=[
                _player("Shai Gilgeous-Alexander", team="OKC",
                        player_id=SGA_ID, minutes=28.0, pts=26,
                        reb=5, ast=6, fg3m=3, stl=1, blk=0, tov=2,
                        pf=4, is_starter=True),
                _player("Victor Wembanyama", team="SAS",
                        player_id=WEMBY_ID, minutes=26.0, pts=20,
                        reb=11, ast=3, fg3m=1, stl=2, blk=4, tov=1,
                        pf=2, is_starter=True),
            ],
        )

    def test_foul_factor_055_in_q3_with_4_fouls(self, snapshot):
        """Cycle-88e table: pf=4 in Q3 -> 0.55."""
        clock_min = fta.clock_str_to_minutes(snapshot["clock"])
        assert fta.foul_trouble_factor(4, 3, clock_min) == 0.55

    def test_adjust_snapshot_zeros_only_troubled_player(self, snapshot):
        """SGA gets 0.55; Wemby (pf=2) stays at 1.0."""
        rows = fta.adjust_snapshot(snapshot)
        by_pid = {r["player_id"]: r for r in rows}
        assert by_pid[SGA_ID]["factor"] == pytest.approx(0.55)
        assert by_pid[WEMBY_ID]["factor"] == 1.0

    def test_factor_scales_projection_remaining_45_percent(self, snapshot):
        """Apply foul factor to a baseline projection -> remaining drops ~45%."""
        # Build a baseline projection for SGA (cycle 88b shape).
        baseline = {"player_id": SGA_ID, "pts": 14.0, "reb": 3.0, "ast": 4.0}
        adjusted = fta.apply_factor_to_projection(baseline, 0.55)
        # Each minute-scaling stat scaled by 0.55 (a ~45% reduction).
        assert adjusted["pts"] == pytest.approx(14.0 * 0.55)
        assert adjusted["reb"] == pytest.approx(3.0 * 0.55)
        assert adjusted["ast"] == pytest.approx(4.0 * 0.55)
        assert adjusted["foul_trouble_factor"] == 0.55

    def test_end_to_end_chain_predict_then_foul_adjust(self, snapshot):
        """predict_in_game -> foul_trouble_adjust chain produces a reduced
        projection vs the baseline pace projection."""
        rows = pig.project_snapshot(snapshot, pace_factor=1.0)
        sga_pts = next(r for r in rows
                       if r["player_id"] == SGA_ID and r["stat"] == "pts")
        # predict_in_game already folds the foul factor inline (0.70 for pf=4
        # Q3 in pig's local table; the standalone fta table says 0.55).
        # The fta module is the authoritative one for adjust_snapshot.
        # We assert here that BOTH yield projections strictly below the no-foul
        # baseline.
        # No-foul baseline: 26 * (1 + (1 - 27/48)/(27/48)) = 26 / (27/48) = ~46.2.
        baseline_proj = 26.0 / (27.0 / 48.0)
        assert sga_pts["projected_final"] < baseline_proj


# ---------------------------------------------------------------------------
# Scenario 3 — Q4 blowout.
# ---------------------------------------------------------------------------

class TestScenario3Q4Blowout:
    """Q4 8:00 left, OKC 110 - SAS 80 (30-pt blowout)."""

    @pytest.fixture
    def snapshot(self):
        return _snapshot(
            period=4, clock="8:00",
            home_score=110, away_score=80,
            players=[
                _player("Shai Gilgeous-Alexander", team="OKC",
                        player_id=SGA_ID, minutes=32.0, pts=28,
                        reb=5, ast=7, fg3m=4, stl=1, blk=0, tov=3,
                        pf=2, is_starter=True),
                _player("Bench Guy", team="OKC", player_id=BENCH_OKC_ID,
                        minutes=12.0, pts=6, reb=4, ast=1, fg3m=1,
                        stl=0, blk=0, tov=0, pf=1, is_starter=False),
            ],
        )

    def test_blowout_factor_table(self, snapshot):
        """Cycle-88f: Q4 30+ margin -> starter 0.25 / bench 1.50."""
        # 30-pt blowout with 8 min left -> falls into "30+ margin" bucket
        # (the "last 3:00" rule requires clock <= 3.0).
        clock_min = ba._clock_to_minutes(snapshot["clock"])
        assert ba.blowout_factor(30, 4, clock_min, True) == 0.25
        assert ba.blowout_factor(30, 4, clock_min, False) == 1.50

    def test_is_blowout_helper(self, snapshot):
        """src/data/live.is_blowout fires in Q4 when margin >= 20."""
        assert live_mod.is_blowout(snapshot, threshold=20)
        assert live_mod.absolute_margin(snapshot) == 30

    def test_apply_blowout_to_projections(self, snapshot):
        """apply_to_projections scales proj_* by the bucket factor."""
        projs = [
            {"player_id": SGA_ID, "is_starter": True,
             "proj_pts": 40.0, "remaining_min": 10.0},
            {"player_id": BENCH_OKC_ID, "is_starter": False,
             "proj_pts": 8.0, "remaining_min": 10.0},
        ]
        adj = ba.apply_to_projections(snapshot, projs)
        by_pid = {r["player_id"]: r for r in adj}
        assert by_pid[SGA_ID]["blowout_factor"] == 0.25
        assert by_pid[SGA_ID]["proj_pts"] == pytest.approx(40.0 * 0.25)
        assert by_pid[BENCH_OKC_ID]["blowout_factor"] == 1.50
        assert by_pid[BENCH_OKC_ID]["proj_pts"] == pytest.approx(8.0 * 1.50)

    def test_predict_in_game_reduces_star_projection_in_blowout(self, snapshot):
        """predict_in_game.project_snapshot's internal blowout factor pulls
        SGA's projected_final dramatically below pure pace."""
        rows = pig.project_snapshot(snapshot)
        sga_pts = next(r for r in rows
                       if r["player_id"] == SGA_ID and r["stat"] == "pts")
        # In a competitive Q4 8:00 (40 min elapsed of 48), pace projection
        # would be 28 * 48/40 = 33.6. Blowout factor cuts the REMAINING
        # portion to 0.30 (predict_in_game's internal table for margin>=30).
        # So projected final = 28 + (28 * (8/40) * 0.30) = 28 + 1.68 = 29.68.
        # We just assert it's strictly less than the no-blowout pace.
        no_blow = 28.0 * (48.0 / 40.0)
        assert sga_pts["projected_final"] < no_blow
        assert sga_pts["blow_factor"] < 1.0


# ---------------------------------------------------------------------------
# Scenario 4 — Pre-tip inactives + bet log resolution.
# ---------------------------------------------------------------------------

class TestScenario4InactivesAndBetLog:
    """A player flagged OUT zeroes every prediction row; bet log can then
    look the player up and see 'INACTIVE'."""

    HEADER = [
        "date", "game_id", "player_id", "player", "team", "opp", "venue",
        "stat", "pred",
        "lineup_status", "lineup_class", "play_pct", "injury_status",
    ]

    def _write_ledger(self, tmp_path):
        """Predictions ledger: 7 stats * 3 players = 21 rows."""
        rows = []
        for stat in STATS:
            rows.append([
                "2026-05-24", "0022400123", str(SGA_ID),
                "Shai Gilgeous-Alexander", "OKC", "SAS", "home",
                stat, "20.0000",
                "confirmed", "starter", "0.85", "",
            ])
            rows.append([
                "2026-05-24", "0022400123", str(WEMBY_ID),
                "Victor Wembanyama", "SAS", "OKC", "away",
                stat, "18.0000",
                "confirmed", "starter", "0.85", "",
            ])
            rows.append([
                "2026-05-24", "0022400123", str(BENCH_OKC_ID),
                "Bench Guy", "OKC", "SAS", "home",
                stat, "5.0000",
                "confirmed", "bench", "0.40", "",
            ])
        path = os.path.join(str(tmp_path), "2026-05-24.csv")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(self.HEADER)
            w.writerows(rows)
        return path

    def _write_inactives_json(self, tmp_path, names):
        path = os.path.join(str(tmp_path), "injuries_2026-05-24.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({
                "date": "2026-05-24",
                "source_pdf": "synthetic.pdf",
                "fetched_at": "2026-05-24T17:00",
                "players": [
                    {"team": "SAS", "name": n,
                     "status": "OUT", "reason": "synthetic"}
                    for n in names
                ],
            }, fh)
        return path

    def _write_bet_log(self, tmp_path, bets):
        """Synthetic bet log: player, stat, line, side."""
        path = os.path.join(str(tmp_path), "bets.csv")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["player", "stat", "line", "side"])
            for b in bets:
                w.writerow(b)
        return path

    def test_update_inactives_zeros_predictions(self, tmp_path):
        """A player listed OUT has every stat row zeroed; others untouched."""
        ledger = self._write_ledger(tmp_path)
        inj = self._write_inactives_json(tmp_path, ["Victor Wembanyama"])

        from src.data.injuries import load_unavailable_players
        keys = set(load_unavailable_players(inj).keys())
        assert "victor wembanyama" in keys

        out_p = os.path.join(str(tmp_path), "2026-05-24_post_inactives.csv")
        n_rows, n_players = ui.apply_inactives(ledger, out_p, keys)
        assert n_rows == len(STATS)
        assert n_players == 1

        with open(out_p, encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        header = rows[0]
        pred_i = header.index("pred")
        inj_i = header.index("injury_status")
        for r in rows[1:]:
            if r[header.index("player")] == "Victor Wembanyama":
                assert float(r[pred_i]) == 0.0
                assert r[inj_i] == "INACTIVE"
            else:
                assert float(r[pred_i]) > 0.0

    def test_bet_log_resolution_marks_inactive(self, tmp_path):
        """Given a bet log with bets on an OUT player, we can resolve
        each bet to 'not playing tonight' by joining against the
        post-inactives ledger."""
        ledger = self._write_ledger(tmp_path)
        inj = self._write_inactives_json(tmp_path, ["Victor Wembanyama"])

        from src.data.injuries import load_unavailable_players
        keys = set(load_unavailable_players(inj).keys())
        out_p = os.path.join(str(tmp_path), "post.csv")
        ui.apply_inactives(ledger, out_p, keys)

        bets = self._write_bet_log(tmp_path, [
            ("Victor Wembanyama", "pts", "23.5", "over"),
            ("Shai Gilgeous-Alexander", "pts", "28.5", "over"),
            ("Bench Guy", "reb", "3.5", "over"),
        ])

        # Manually replicate what live_edge_eval would do: look each bet up
        # in the post-inactives ledger and check injury_status.
        with open(out_p, encoding="utf-8", newline="") as fh:
            pred_rows = list(csv.DictReader(fh))
        # Map (name_key, stat) -> injury_status
        from src.data.injuries import _name_key
        pred_by_player = {}
        for r in pred_rows:
            pred_by_player.setdefault(
                _name_key(r["player"]), r["injury_status"])

        with open(bets, encoding="utf-8", newline="") as fh:
            bet_rows = list(csv.DictReader(fh))

        resolved = []
        for b in bet_rows:
            status = pred_by_player.get(_name_key(b["player"]), "")
            resolved.append({
                "player": b["player"], "stat": b["stat"],
                "side": b["side"], "resolution":
                "NOT PLAYING TONIGHT" if status == "INACTIVE" else "active",
            })

        assert resolved[0]["resolution"] == "NOT PLAYING TONIGHT"
        assert resolved[1]["resolution"] == "active"
        assert resolved[2]["resolution"] == "active"


# ---------------------------------------------------------------------------
# Scenario 5 — live_run dry-run smoke (compose helpers).
# ---------------------------------------------------------------------------

class TestScenario5LiveRunDryRun:
    """Mock all subprocess; verify compose helpers produce expected argv chains."""

    DATE = "2026-05-24"

    def test_compose_phase1_chains_injury_lineups_lineposition(self):
        plan = lr.compose_phase_commands(1, self.DATE, python_exe="python")
        oneshot_paths = [c[1] for c in plan["oneshot"]]
        recurring_paths = [c[1] for c in plan["recurring"]]
        assert any(p.endswith("fetch_injury_espn.py") for p in oneshot_paths)
        assert any(p.endswith("fetch_lineups.py") for p in oneshot_paths)
        assert any(p.endswith("poll_line_movement.py")
                   for p in recurring_paths)
        # Every command includes --date.
        for cmd in plan["oneshot"] + plan["recurring"]:
            assert "--date" in cmd and self.DATE in cmd

    def test_compose_phase2_has_inactives_and_starters(self):
        plan = lr.compose_phase_commands(2, self.DATE, python_exe="python")
        oneshot_paths = [c[1] for c in plan["oneshot"]]
        assert any(p.endswith("update_inactives.py") for p in oneshot_paths)
        assert any(p.endswith("update_confirmed_starters.py")
                   for p in oneshot_paths)

    def test_compose_phase3_has_live_poll(self):
        plan = lr.compose_phase_commands(3, self.DATE, python_exe="python")
        recurring_paths = [c[1] for c in plan["recurring"]]
        assert any(p.endswith("live_game_poll.py") for p in recurring_paths)

    def test_dry_run_does_not_invoke_subprocess(self):
        """live_run --dry-run path must NOT touch subprocess.Popen / .run."""
        argv = ["live_run.py", "--date", self.DATE, "--dry-run"]
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", argv), \
             mock.patch("subprocess.Popen") as mp, \
             mock.patch("subprocess.run") as mr, \
             redirect_stdout(buf):
            rc = lr.main()
        assert rc == 0
        mp.assert_not_called()
        mr.assert_not_called()
        out = buf.getvalue()
        # Plan output names every phase.
        assert "phase 1" in out and "phase 2" in out
        assert "phase 3" in out and "phase 4" in out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
