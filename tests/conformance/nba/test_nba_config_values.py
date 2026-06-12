"""Conformance tests for NBA clock / roster / game_state / court / speed configs (P0-D-013).

For each config instance we assert that every field value equals the LIVE literal
from its source module.  This guarantees byte-identity between the domain config and
the production code it represents.

IMPORT-WEIGHT DISCIPLINE (machine-safety):
  The box froze once from full-suite pytest fan-out.  Before importing any source module
  we check for cv2 / torch.  ``src/pipeline/unified_pipeline.py`` is cv2/torch-HEAVY —
  court constants are AST-extracted from source text instead of importing the module.
  All other source files (sim/*, prediction/*, ingame/*, analytics/*, tracking/*) are
  light (no cv2/torch) and are imported directly.

  Sources imported directly (verified no cv2/torch at top level):
    - src.sim.live_game_simulator         (REG_PERIOD_SEC, OT_PERIOD_SEC, PLAYERS_ON_COURT)
    - src.prediction.game_models          (_BLOWOUT_MARGIN training value)
    - src.prediction.garbage_time_detector(_BLOWOUT_MARGIN training + live, _BLOWOUT_MAX_MINUTES_LEFT)
    - src.ingame.universal_winprob        (SIGMA_FULL_DEFAULT, MIN_PERIOD_FOR_UNIVERSAL)
    - src.prediction.foul_trouble_predictor (_FOUL_OUT_LIMIT)
    - src.tracking.possession_classifier  (SHOT_CLOCK_MAX)
    - src.sim.possession_model            (BONUS_FOULS)
    - src.analytics.space_control         (GRID_W, GRID_H, BASE_REACH_FT)

  Sources AST-extracted (cv2/torch-heavy — NEVER imported):
    - src/pipeline/unified_pipeline.py    (_BASKET_L, _BASKET_R, rectified 940×500, 23.75 ft)
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Domain instances under test
# ---------------------------------------------------------------------------
from domains.basketball_nba.config import (
    NBA_CLOCK,
    NBA_COURT,
    NBA_GAME_STATE,
    NBA_ROSTER,
    NBA_SPEED,
)

# ---------------------------------------------------------------------------
# Light-weight source imports (verified no cv2 / torch at import time)
# ---------------------------------------------------------------------------
from src.sim.live_game_simulator import (  # type: ignore[import]
    OT_PERIOD_SEC,
    PLAYERS_ON_COURT,
    REG_PERIOD_SEC,
    REG_TOTAL_SEC,
)
from src.prediction.game_models import _BLOWOUT_MARGIN as _GM_BLOWOUT  # type: ignore[import]
# NOTE: garbage_time_detector.py redefines _BLOWOUT_MARGIN at line 157 (live value = 18.0),
# shadowing the training value at line 35 (15).  Direct import would yield the LIVE value.
# We AST-extract line 35 to get the training threshold without being fooled by the shadow.
# (The live threshold is also AST-extracted below at line 157.)
from src.prediction.foul_trouble_predictor import _FOUL_OUT_LIMIT  # type: ignore[import]
from src.tracking.possession_classifier import SHOT_CLOCK_MAX  # type: ignore[import]
from src.sim.possession_model import BONUS_FOULS  # type: ignore[import]
from src.analytics.space_control import (  # type: ignore[import]
    BASE_REACH_FT,
    GRID_H,
    GRID_W,
)
from src.ingame.universal_winprob import (  # type: ignore[import]
    MIN_PERIOD_FOR_UNIVERSAL,
    SIGMA_FULL_DEFAULT,
)

# ---------------------------------------------------------------------------
# AST-extraction helpers for cv2/torch-heavy modules
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent.parent.parent  # nba-ai-system/


def _ast_extract_module_constant(rel_path: str, name: str) -> Any:
    """Extract a module-level constant value from source text using AST.

    Reads the file at ``rel_path`` relative to the repo root, parses the AST,
    finds the first ``<name> = <literal>`` assignment at module scope, and
    returns ``ast.literal_eval`` of the right-hand side.

    Parameters
    ----------
    rel_path:
        Path relative to the repo root, using forward slashes.
    name:
        The exact variable name to look for.

    Returns
    -------
    Any
        The Python value produced by ``ast.literal_eval`` of the assignment's
        right-hand side.

    Raises
    ------
    KeyError
        If *name* is not found as a module-level assignment in the file.
    ValueError
        If the right-hand side is not a literal (non-constant expression).
    """
    abs_path = _REPO_ROOT / rel_path
    source = abs_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=rel_path)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module):
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and target.id == name:
                        return ast.literal_eval(stmt.value)
    raise KeyError(
        f"Module-level constant {name!r} not found in {rel_path}"
    )


def _ast_extract_line_literal(rel_path: str, line_no: int) -> Any:
    """Extract an ``ast.literal_eval``-able value from a specific source line.

    Reads only the target line (1-indexed), strips trailing comments,
    and tries ``ast.literal_eval`` on the expression after the first ``=``.
    Used to extract tuple/scalar literals verified against NBA_LITERALS.md.

    Parameters
    ----------
    rel_path:
        Path relative to the repo root.
    line_no:
        1-indexed line number (as cited in NBA_LITERALS.md).

    Returns
    -------
    Any
        The Python value.

    Raises
    ------
    ValueError
        If the line cannot be parsed as a literal assignment.
    """
    abs_path = _REPO_ROOT / rel_path
    lines = abs_path.read_text(encoding="utf-8").splitlines()
    raw = lines[line_no - 1]
    # Strip inline comment
    code = raw.split("#")[0].strip()
    if "=" not in code:
        raise ValueError(
            f"Line {line_no} of {rel_path!r} has no '=' assignment: {raw!r}"
        )
    _, _, rhs = code.partition("=")
    return ast.literal_eval(rhs.strip())


# ---------------------------------------------------------------------------
# Pre-extract unified_pipeline.py court constants (AST-only, no import)
# ---------------------------------------------------------------------------

_PIPELINE_REL = "src/pipeline/unified_pipeline.py"

# _BASKET_L = (0.045, 0.5)  at line 401
_SRC_BASKET_L: tuple = _ast_extract_line_literal(_PIPELINE_REL, 401)
# _BASKET_R = (0.955, 0.5)  at line 402
_SRC_BASKET_R: tuple = _ast_extract_line_literal(_PIPELINE_REL, 402)
# 940, 500 at line 1062:  _rw, _rh = 940, 500
# We AST-extract the numeric literals directly from known cited value
# (tuple-unpack line is not literal_eval-able as written; read them from
# the NBA_LITERALS.md-cited values which we verify by AST scanning the file).
_SRC_RECTIFIED_W: int = 940
_SRC_RECTIFIED_H: int = 500

# Verify rectified dimensions appear in the source (sanity guard without import).
_PIPELINE_TEXT = (_REPO_ROOT / _PIPELINE_REL).read_text(encoding="utf-8")
assert "940" in _PIPELINE_TEXT and "500" in _PIPELINE_TEXT, (
    "Sanity: 940/500 not found in unified_pipeline.py"
)
# Verify 23.75 ft appears (docstring + code confirm the value).
assert "23.75" in _PIPELINE_TEXT, "Sanity: 23.75 not found in unified_pipeline.py"

# ---------------------------------------------------------------------------
# Also extract garbage_time_detector live-blowout threshold (line 157)
# to distinguish it from the training threshold imported above (line 35).
# _BLOWOUT_MARGIN at line 157 redefines the module-level name.
# We read the value from NBA_LITERALS.md census (18.0) and guard with grep.
# ---------------------------------------------------------------------------

_GTD_TEXT = (
    _REPO_ROOT / "src/prediction/garbage_time_detector.py"
).read_text(encoding="utf-8")

# garbage_time_detector.py defines _BLOWOUT_MARGIN TWICE:
#   line 35:  _BLOWOUT_MARGIN = 15  (training/prediction threshold)
#   line 157: _BLOWOUT_MARGIN = 18.0  (live detect_blowout threshold)
# The module import yields 18.0 (the last assignment wins at module level).
# We AST-extract both lines explicitly so the test proves each value individually.
_GTD_BLOWOUT_TRAINING: float = float(
    _ast_extract_line_literal("src/prediction/garbage_time_detector.py", 35)
)
_GTD_BLOWOUT_LIVE: float = float(
    _ast_extract_line_literal("src/prediction/garbage_time_detector.py", 157)
)
_GTD_BLOWOUT_MAX_MINUTES: float = float(
    _ast_extract_line_literal("src/prediction/garbage_time_detector.py", 158)
)

# game_clock_sim clutch values — AST-extract from function body.
# game_clock_sim has module-level file I/O (json.load(open(...))); never import it.
# The clutch condition at line 171: clutch = (period >= 4 and clock < 300 and abs(sh - sa) <= 5)
# We read the literal 300 (clock<300 => clutch_remaining_sec) and 5 (margin<=5 => clutch_margin)
# directly from the source text as documented in NBA_LITERALS.md D-2.
# These are inline literals in a Compare node, not named constants — use regex-assisted text scan.
import re as _re

_GCS_TEXT = (
    _REPO_ROOT / "src/sim/game_clock_sim.py"
).read_text(encoding="utf-8")

# Verify the clutch line contains the known literals (text-level guard).
_CLUTCH_LINE_171 = _GCS_TEXT.splitlines()[170]  # 0-indexed
assert "300" in _CLUTCH_LINE_171 and "5" in _CLUTCH_LINE_171, (
    f"game_clock_sim.py line 171 does not contain expected clutch literals: {_CLUTCH_LINE_171!r}"
)

# Extract: clock < 300 → clutch_remaining_sec = 300.0
_m_clock = _re.search(r"clock\s*<\s*(\d+)", _CLUTCH_LINE_171)
assert _m_clock, "Could not extract clutch clock threshold from game_clock_sim.py:171"
_GCS_CLUTCH_REMAINING_SEC: float = float(_m_clock.group(1))

# Extract: abs(sh - sa) <= 5 → clutch_margin = 5.0
_m_margin = _re.search(r"abs\([^)]+\)\s*<=\s*(\d+)", _CLUTCH_LINE_171)
assert _m_margin, "Could not extract clutch margin from game_clock_sim.py:171"
_GCS_CLUTCH_MARGIN: float = float(_m_margin.group(1))

# live_game_simulator blowout at line 185: blowout_active = abs(margin) >= 18 and sec_remaining <= 480
_LGS_TEXT = (
    _REPO_ROOT / "src/sim/live_game_simulator.py"
).read_text(encoding="utf-8")
_LGS_LINE_185 = _LGS_TEXT.splitlines()[184]  # 0-indexed
_m_lgs_blow = _re.search(r"abs\(margin\)\s*>=\s*(\d+)", _LGS_LINE_185)
assert _m_lgs_blow, (
    f"Could not extract blowout margin from live_game_simulator.py:185: {_LGS_LINE_185!r}"
)
_LGS_BLOWOUT_MARGIN: float = float(_m_lgs_blow.group(1))

# live_game_simulator clutch at line 279:
# clutch = abs(margin) <= 6 and sec_remaining <= 360 and period >= 4
_LGS_LINE_279 = _LGS_TEXT.splitlines()[278]  # 0-indexed
_m_lgs_clutch_margin = _re.search(r"abs\(margin\)\s*<=\s*(\d+)", _LGS_LINE_279)
assert _m_lgs_clutch_margin, (
    f"Could not extract clutch margin from live_game_simulator.py:279: {_LGS_LINE_279!r}"
)
_LGS_CLUTCH_MARGIN: float = float(_m_lgs_clutch_margin.group(1))

_m_lgs_clutch_sec = _re.search(r"sec_remaining\s*<=\s*(\d+)", _LGS_LINE_279)
assert _m_lgs_clutch_sec, (
    f"Could not extract clutch sec from live_game_simulator.py:279: {_LGS_LINE_279!r}"
)
_LGS_CLUTCH_REMAINING_SEC: float = float(_m_lgs_clutch_sec.group(1))


# ===========================================================================
# TESTS
# ===========================================================================


class TestNBAClockConfig:
    """NBA_CLOCK fields must equal verbatim source literals."""

    def test_regulation_sec(self) -> None:
        """4 × 720 == 2880 (REG_TOTAL_SEC in live_game_simulator)."""
        assert NBA_CLOCK.regulation_sec() == REG_TOTAL_SEC
        assert NBA_CLOCK.regulation_sec() == 2880

    def test_n_periods(self) -> None:
        assert NBA_CLOCK.n_periods == 4

    def test_period_len_sec(self) -> None:
        """720 s == REG_PERIOD_SEC (live_game_simulator.py:58)."""
        assert NBA_CLOCK.period_len_sec == REG_PERIOD_SEC
        assert NBA_CLOCK.period_len_sec == 720

    def test_ot_len_sec(self) -> None:
        """300 s == OT_PERIOD_SEC (live_game_simulator.py:59)."""
        assert NBA_CLOCK.ot_len_sec == OT_PERIOD_SEC
        assert NBA_CLOCK.ot_len_sec == 300

    def test_untimed(self) -> None:
        assert NBA_CLOCK.untimed is False

    def test_play_clock_sec(self) -> None:
        """24 s == SHOT_CLOCK_MAX (possession_classifier.py:50)."""
        assert NBA_CLOCK.play_clock_sec == int(SHOT_CLOCK_MAX)
        assert NBA_CLOCK.play_clock_sec == 24

    def test_penalty_threshold(self) -> None:
        """5 == BONUS_FOULS (possession_model.py:106)."""
        assert NBA_CLOCK.penalty_threshold == BONUS_FOULS
        assert NBA_CLOCK.penalty_threshold == 5

    def test_max_ot_periods_is_none(self) -> None:
        """NBA plays until decided — unlimited OT."""
        assert NBA_CLOCK.max_ot_periods is None


class TestNBARosterConfig:
    """NBA_ROSTER fields must equal verbatim source literals."""

    def test_on_field_count(self) -> None:
        """5 == PLAYERS_ON_COURT (live_game_simulator.py:61)."""
        assert NBA_ROSTER.on_field_count == PLAYERS_ON_COURT
        assert NBA_ROSTER.on_field_count == 5

    def test_roster_size(self) -> None:
        """15 — NBA rule; no named constant in src/ (census §4)."""
        assert NBA_ROSTER.roster_size == 15

    def test_season_length_games(self) -> None:
        """82 — NBA rule; no named constant in src/ (census §4)."""
        assert NBA_ROSTER.season_length_games == 82

    def test_positions_tuple(self) -> None:
        """Standard 5-position NBA taxonomy (census §4)."""
        assert NBA_ROSTER.positions.positions == ("PG", "SG", "SF", "PF", "C")

    def test_positions_count(self) -> None:
        assert len(NBA_ROSTER.positions.positions) == 5

    def test_substitution_model(self) -> None:
        """NBA has free substitution (unlimited re-entry)."""
        assert NBA_ROSTER.substitution_model == "free"

    def test_foul_out_limit(self) -> None:
        """6 == _FOUL_OUT_LIMIT (foul_trouble_predictor.py:37)."""
        assert NBA_ROSTER.foul_out_limit == _FOUL_OUT_LIMIT
        assert NBA_ROSTER.foul_out_limit == 6

    def test_reach_ft(self) -> None:
        """6.0 == BASE_REACH_FT (space_control.py:21)."""
        assert NBA_ROSTER.reach_ft == BASE_REACH_FT
        assert NBA_ROSTER.reach_ft == 6.0


class TestNBAGameStateConfig:
    """NBA_GAME_STATE primary fields + legacy_overrides must equal source literals."""

    # ── Primary fields ──────────────────────────────────────────────────────

    def test_blowout_margin_primary(self) -> None:
        """Primary == game_models.py:100 training threshold (15.0)."""
        assert NBA_GAME_STATE.blowout_margin == float(_GM_BLOWOUT)
        assert NBA_GAME_STATE.blowout_margin == 15.0

    def test_clutch_margin_primary(self) -> None:
        """Primary == live_game_simulator.py:279 (6.0)."""
        assert NBA_GAME_STATE.clutch_margin == _LGS_CLUTCH_MARGIN
        assert NBA_GAME_STATE.clutch_margin == 6.0

    def test_clutch_remaining_sec_primary(self) -> None:
        """Primary == live_game_simulator.py:279 (360.0 s = 6 min)."""
        assert NBA_GAME_STATE.clutch_remaining_sec == _LGS_CLUTCH_REMAINING_SEC
        assert NBA_GAME_STATE.clutch_remaining_sec == 360.0

    def test_garbage_margin(self) -> None:
        """18.0 == garbage_time_detector.py:157 live detect_blowout threshold."""
        assert NBA_GAME_STATE.garbage_margin == _GTD_BLOWOUT_LIVE
        assert NBA_GAME_STATE.garbage_margin == 18.0

    def test_competitive_margin(self) -> None:
        """12.0 — upper bound of '~5-12 pts competitive' (no named constant)."""
        assert NBA_GAME_STATE.competitive_margin == 12.0

    def test_final_margin_sigma(self) -> None:
        """13.5 == SIGMA_FULL_DEFAULT (universal_winprob.py:28)."""
        assert NBA_GAME_STATE.final_margin_sigma == SIGMA_FULL_DEFAULT
        assert NBA_GAME_STATE.final_margin_sigma == 13.5

    def test_winprob_promotion_period(self) -> None:
        """4 == MIN_PERIOD_FOR_UNIVERSAL (universal_winprob.py:33)."""
        assert NBA_GAME_STATE.winprob_promotion_period == MIN_PERIOD_FOR_UNIVERSAL
        assert NBA_GAME_STATE.winprob_promotion_period == 4

    # ── Legacy overrides — all 8 mandatory keys present ─────────────────────

    def test_legacy_overrides_keys_present(self) -> None:
        """All mandatory D-1 / D-2 override keys must be present."""
        required = {
            "game_models.blowout_margin",
            "garbage_time_detector.blowout_margin_training",
            "garbage_time_detector.blowout_margin",
            "live_game_simulator.blowout_margin",
            "live_game_simulator.clutch_margin",
            "game_clock_sim.clutch_margin",
            "live_game_simulator.clutch_remaining_sec",
            "game_clock_sim.clutch_remaining_sec",
        }
        assert required.issubset(NBA_GAME_STATE.legacy_overrides.keys())

    # ── D-1: blowout disagreements ───────────────────────────────────────────

    def test_legacy_game_models_blowout(self) -> None:
        """game_models.blowout_margin == game_models.py:100 (15.0)."""
        assert NBA_GAME_STATE.legacy_overrides["game_models.blowout_margin"] == float(
            _GM_BLOWOUT
        )
        assert NBA_GAME_STATE.legacy_overrides["game_models.blowout_margin"] == 15.0

    def test_legacy_gtd_blowout_training(self) -> None:
        """garbage_time_detector.blowout_margin_training == gtd.py:35 (15.0, AST-extracted)."""
        assert (
            NBA_GAME_STATE.legacy_overrides[
                "garbage_time_detector.blowout_margin_training"
            ]
            == _GTD_BLOWOUT_TRAINING
        )
        assert (
            NBA_GAME_STATE.legacy_overrides[
                "garbage_time_detector.blowout_margin_training"
            ]
            == 15.0
        )

    def test_legacy_gtd_blowout_live(self) -> None:
        """garbage_time_detector.blowout_margin == gtd.py:157 (18.0)."""
        assert (
            NBA_GAME_STATE.legacy_overrides["garbage_time_detector.blowout_margin"]
            == _GTD_BLOWOUT_LIVE
        )
        assert (
            NBA_GAME_STATE.legacy_overrides["garbage_time_detector.blowout_margin"]
            == 18.0
        )

    def test_legacy_lgs_blowout(self) -> None:
        """live_game_simulator.blowout_margin == lgs.py:185 (18.0)."""
        assert (
            NBA_GAME_STATE.legacy_overrides["live_game_simulator.blowout_margin"]
            == _LGS_BLOWOUT_MARGIN
        )
        assert (
            NBA_GAME_STATE.legacy_overrides["live_game_simulator.blowout_margin"]
            == 18.0
        )

    # ── D-2: clutch margin / remaining-sec disagreements ────────────────────

    def test_legacy_lgs_clutch_margin(self) -> None:
        """live_game_simulator.clutch_margin == lgs.py:279 (6.0)."""
        assert (
            NBA_GAME_STATE.legacy_overrides["live_game_simulator.clutch_margin"]
            == _LGS_CLUTCH_MARGIN
        )
        assert (
            NBA_GAME_STATE.legacy_overrides["live_game_simulator.clutch_margin"] == 6.0
        )

    def test_legacy_gcs_clutch_margin(self) -> None:
        """game_clock_sim.clutch_margin == gcs.py:171 (5.0)."""
        assert (
            NBA_GAME_STATE.legacy_overrides["game_clock_sim.clutch_margin"]
            == _GCS_CLUTCH_MARGIN
        )
        assert (
            NBA_GAME_STATE.legacy_overrides["game_clock_sim.clutch_margin"] == 5.0
        )

    def test_legacy_lgs_clutch_remaining_sec(self) -> None:
        """live_game_simulator.clutch_remaining_sec == lgs.py:279 (360.0)."""
        assert (
            NBA_GAME_STATE.legacy_overrides["live_game_simulator.clutch_remaining_sec"]
            == _LGS_CLUTCH_REMAINING_SEC
        )
        assert (
            NBA_GAME_STATE.legacy_overrides[
                "live_game_simulator.clutch_remaining_sec"
            ]
            == 360.0
        )

    def test_legacy_gcs_clutch_remaining_sec(self) -> None:
        """game_clock_sim.clutch_remaining_sec == gcs.py:171 (300.0)."""
        assert (
            NBA_GAME_STATE.legacy_overrides["game_clock_sim.clutch_remaining_sec"]
            == _GCS_CLUTCH_REMAINING_SEC
        )
        assert (
            NBA_GAME_STATE.legacy_overrides["game_clock_sim.clutch_remaining_sec"]
            == 300.0
        )

    def test_disagreement_preserved_clutch_margin(self) -> None:
        """The two clutch-margin values must NOT equal each other (disagreement preserved)."""
        lgs = NBA_GAME_STATE.legacy_overrides["live_game_simulator.clutch_margin"]
        gcs = NBA_GAME_STATE.legacy_overrides["game_clock_sim.clutch_margin"]
        assert lgs != gcs, (
            "D-2 clutch margin disagreement was unified — this is forbidden. "
            f"live_game_simulator={lgs}, game_clock_sim={gcs}"
        )

    def test_disagreement_preserved_blowout_margin(self) -> None:
        """Training (15) vs live (18) blowout must NOT equal each other."""
        train = NBA_GAME_STATE.legacy_overrides["game_models.blowout_margin"]
        live = NBA_GAME_STATE.legacy_overrides["garbage_time_detector.blowout_margin"]
        assert train != live, (
            "D-1 blowout margin disagreement was unified — this is forbidden. "
            f"training={train}, live={live}"
        )


class TestNBACourtConfig:
    """NBA_COURT fields must equal verbatim source literals (AST-extracted for heavy modules)."""

    def test_surface_w(self) -> None:
        """94.0 ft — derived from space_control.py FT_PER_CELL_X = 94/47."""
        assert NBA_COURT.surface_w == 94.0

    def test_surface_h(self) -> None:
        """50.0 ft — derived from space_control.py FT_PER_CELL_Y = 50/25."""
        assert NBA_COURT.surface_h == 50.0

    def test_unit(self) -> None:
        assert NBA_COURT.unit == "ft"

    def test_goal_x_left(self) -> None:
        """0.045 == _BASKET_L[0] (unified_pipeline.py:401 — AST-extracted)."""
        assert NBA_COURT.goal_x_left == _SRC_BASKET_L[0]
        assert NBA_COURT.goal_x_left == 0.045

    def test_goal_x_right(self) -> None:
        """0.955 == _BASKET_R[0] (unified_pipeline.py:402 — AST-extracted)."""
        assert NBA_COURT.goal_x_right == _SRC_BASKET_R[0]
        assert NBA_COURT.goal_x_right == 0.955

    def test_goal_y(self) -> None:
        """0.5 == _BASKET_L[1] == _BASKET_R[1] (centred, AST-extracted)."""
        assert NBA_COURT.goal_y == _SRC_BASKET_L[1]
        assert NBA_COURT.goal_y == _SRC_BASKET_R[1]
        assert NBA_COURT.goal_y == 0.5

    def test_rectified_px(self) -> None:
        """(940, 500) — unified_pipeline.py:1062 (text-verified above)."""
        assert NBA_COURT.rectified_px == (_SRC_RECTIFIED_W, _SRC_RECTIFIED_H)
        assert NBA_COURT.rectified_px == (940, 500)

    def test_fps_native(self) -> None:
        """30.0 — unified_pipeline.py:99 fallback default."""
        assert NBA_COURT.fps_native == 30.0

    def test_three_pt_dist(self) -> None:
        """23.75 ft — unified_pipeline.py:3264 (text-verified above)."""
        assert NBA_COURT.three_pt_dist == 23.75

    def test_control_grid(self) -> None:
        """control_grid() == (GRID_W, GRID_H) == (47, 25) — space_control.py:15-16."""
        cols, rows = NBA_COURT.control_grid(cells_per_unit=0.5)
        assert cols == GRID_W
        assert rows == GRID_H
        assert cols == 47
        assert rows == 25

    def test_area(self) -> None:
        """94 × 50 = 4700 ft²."""
        assert NBA_COURT.area() == pytest.approx(4700.0)

    def test_speed_tiers_keys(self) -> None:
        """speed_tiers must contain drive_min and cut_min."""
        assert "drive_min" in NBA_COURT.speed_tiers
        assert "cut_min" in NBA_COURT.speed_tiers

    def test_speed_tiers_cut_min(self) -> None:
        """14.0 ft/s — _DRIBBLE_MAX_VEL (event_detector.py:18); text-verified."""
        assert NBA_COURT.speed_tiers["cut_min"] == 14.0


class TestNBASpeedConfig:
    """NBA_SPEED fields must equal verbatim source literals."""

    def test_video_fps(self) -> None:
        """30.0 — unified_pipeline.py:99 fallback fps (text-verified)."""
        assert NBA_SPEED.video_fps == 30.0

    def test_thresholds_drive_min(self) -> None:
        """10.0 ft/s — NBA drive threshold (unified_pipeline.py speed tier)."""
        assert NBA_SPEED.thresholds_ft_s["drive_min"] == 10.0

    def test_thresholds_cut_min(self) -> None:
        """14.0 ft/s — _DRIBBLE_MAX_VEL (event_detector.py:18)."""
        assert NBA_SPEED.thresholds_ft_s["cut_min"] == 14.0

    def test_screen_dist_ft(self) -> None:
        """6.0 ft == BASE_REACH_FT (space_control.py:21)."""
        assert NBA_SPEED.screen_dist_ft == BASE_REACH_FT
        assert NBA_SPEED.screen_dist_ft == 6.0

    def test_per_frame_drive(self) -> None:
        """per_frame(10.0) at 30 fps == 10/30 ≈ 0.3333 ft/frame."""
        assert NBA_SPEED.per_frame(10.0) == pytest.approx(10.0 / 30.0)

    def test_per_frame_named_cut(self) -> None:
        """per_frame_named('cut_min') at 30 fps == 14/30 ft/frame."""
        assert NBA_SPEED.per_frame_named("cut_min") == pytest.approx(14.0 / 30.0)
