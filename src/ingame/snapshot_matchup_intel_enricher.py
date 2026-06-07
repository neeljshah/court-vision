"""snapshot_matchup_intel_enricher.py — CV_INGAME_MATCHUP_INTEL: per-player
in-game SCORER calibration correction.

WHAT THIS IS (and what it is NOT)
---------------------------------
The mission hypothesis was a *matchup/scheme*-specific scorer adjustment (who is
guarding the scorer, opponent defensive scheme). That hypothesis was **measured
and REJECTED** on the 600-game endQ1/Q2/Q3 residual corpus
(`scripts/ingame/analyze_scorer_residuals.py`):

  * opponent-scheme TS-delta vs the scorer's remaining-pts residual:
    corr = -0.0095, favorable-vs-unfavorable mean-resid gap = 0.04 pts -> NOISE.
  * anchor-defender coverage PPP (coverage_faced_matrix_2025-26) vs residual:
    corr = -0.05, and the player-pair PPP is dominated by tiny-sample (<=4
    partial-possession) zeros -> too sparse to drive an in-game adjustment.

What the SAME residual analysis *did* surface is a real, large, persistent,
player-SPECIFIC structure the generic routed ensemble misses:

  * The generic per-minute extrapolation has a **stable per-player calibration
    bias** for SCORING. Split-half stability of the per-player remaining-pts
    residual = **0.746** (vs the ~0.06 noise floor of prior naive per-player
    in-game work). Subtracting the GLOBAL mean bias from everyone HURTS
    (+0.6..+1.8% MAE); only the player-SPECIFIC deviation helps. Leave-one-game-
    out AND chronological walk-forward both improve held-out pts MAE
    (~-1.2% LOGO, -0.77% chrono).

So this enricher applies a leak-free, shrunk, per-player in-game scorer-bias
correction to the *remaining* pts / fg3m projection. The name keeps the mission's
``CV_INGAME_MATCHUP_INTEL`` flag; the honest mechanism is per-player calibration,
documented in ``docs/_audits/INGAME_MATCHUP_INTEL.md``.

LEAK SAFETY
-----------
The per-player bias table MUST be built from games STRICTLY BEFORE the snapshot's
game (walk-forward) — exactly like the v2 head / team ridge in the routed harness
are fit on train-dates < test. The table is passed in (offline experiment) or
loaded from a committed artifact (live). The current game's actual NEVER enters
the bias. With no table entry for a player (rookie / cold start) the row is
untouched -> graceful no-op, never projects from the test game's own outcome.

Correction direction
---------------------
``bias[pid][stat]`` = mean of (projected_final - actual_final) over the player's
PRIOR games at endQ1/Q2/Q3. A POSITIVE bias means the projector historically
OVER-projects this player -> we SUBTRACT ``shrink * bias`` from the projection.
The correction is applied to the *remaining* portion only (it shifts the final,
which is current_so_far + remaining; we never let the final drop below current).

Byte-identical guarantee
------------------------
With ``CV_INGAME_MATCHUP_INTEL`` unset / "0" / "false", ``apply_matchup_intel``
returns the rows list UNCHANGED — no mutations, no added keys.

Public API
----------
``apply_matchup_intel(snap, rows, *, bias_table=None)``
    Post-projection row mutator (same signature family as ``apply_onoff_tilt``).
``correct_value(projected_final, current_so_far, bias, shrink)``
    Pure scalar corrector (unit-testable, no I/O).
``load_bias_table(path)`` / ``build_bias_table(records, ...)``
    Artifact load / offline walk-forward builder helpers.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_FLAG_ENV = "CV_INGAME_MATCHUP_INTEL"

# Only SCORING stats — the residual analysis only found stable, exploitable
# per-player bias for pts and fg3m. REB/AST are deliberately untouched.
CORRECT_STATS: Tuple[str, ...] = ("pts", "fg3m")

# Shrinkage on the per-player bias estimate. 0.4 was the held-out optimum on both
# the LOGO and chronological splits (flat across 0.3-0.5; degrades past 0.6).
DEFAULT_SHRINK: float = 0.4

# Minimum prior-game count before a player's bias is trusted (else no-op).
DEFAULT_MIN_GAMES: int = 4

_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
_DEFAULT_TABLE_PATH: Path = (
    _PROJECT_ROOT / "data" / "cache" / "ingame_scorer_bias.json"
)


def _flag_on() -> bool:
    return os.environ.get(_FLAG_ENV, "0").strip().lower() in ("1", "true", "yes")


# --------------------------------------------------------------------------- #
# Pure corrector
# --------------------------------------------------------------------------- #
def correct_value(
    projected_final: float,
    current_so_far: float,
    bias: float,
    shrink: float = DEFAULT_SHRINK,
) -> float:
    """Subtract the shrunk per-player bias from the projection.

    ``bias`` > 0 means the projector OVER-projects this player historically, so we
    lower the projection. The result is floored at ``current_so_far`` (a final can
    never be below what already happened).
    """
    adj = float(projected_final) - float(shrink) * float(bias)
    return max(float(current_so_far), adj)


# --------------------------------------------------------------------------- #
# Bias-table artifact I/O
# --------------------------------------------------------------------------- #
def load_bias_table(path: Optional[Path] = None) -> Dict[int, Dict[str, float]]:
    """Load ``{player_id: {stat: bias}}`` from a committed JSON artifact.

    Returns {} if the file is absent / malformed (-> enricher is a graceful
    no-op even when ON). JSON keys are strings; coerced back to int pids.
    """
    p = Path(path) if path is not None else _DEFAULT_TABLE_PATH
    if not p.exists():
        return {}
    try:
        with open(p, encoding="utf-8") as fh:
            raw = json.load(fh)
    except Exception:
        return {}
    out: Dict[int, Dict[str, float]] = {}
    for pid_s, stats in (raw.get("bias") or raw).items():
        try:
            pid = int(pid_s)
        except (TypeError, ValueError):
            continue
        if not isinstance(stats, dict):
            continue
        clean = {}
        for s, v in stats.items():
            if s in CORRECT_STATS and v is not None:
                try:
                    clean[s] = float(v)
                except (TypeError, ValueError):
                    continue
        if clean:
            out[pid] = clean
    return out


def build_bias_table(
    rows: List[dict],
    min_games: int = DEFAULT_MIN_GAMES,
) -> Dict[int, Dict[str, float]]:
    """Build ``{pid: {stat: bias}}`` from residual rows (offline / walk-forward).

    Each input row must be ``{player_id, game_id, stat, resid}`` where
    ``resid = projected_final - actual_final``. The caller is responsible for
    passing ONLY rows from games that precede the target (walk-forward / LOGO):
    this function does no date filtering, it just averages.

    A player's bias for a stat is the mean residual over their games (averaged at
    the game level first so a player's many endQ1/Q2/Q3 rows in one game don't
    over-weight that game), retained only if seen in >= ``min_games`` games.
    """
    # pid -> stat -> game_id -> [resid]
    acc: Dict[int, Dict[str, Dict[str, List[float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list)))
    for r in rows:
        try:
            pid = int(r["player_id"])
            stat = str(r["stat"])
            if stat not in CORRECT_STATS:
                continue
            acc[pid][stat][str(r["game_id"])].append(float(r["resid"]))
        except (KeyError, TypeError, ValueError):
            continue
    out: Dict[int, Dict[str, float]] = {}
    for pid, by_stat in acc.items():
        rec: Dict[str, float] = {}
        for stat, by_game in by_stat.items():
            if len(by_game) < min_games:
                continue
            game_means = [sum(v) / len(v) for v in by_game.values()]
            rec[stat] = sum(game_means) / len(game_means)
        if rec:
            out[pid] = rec
    return out


# --------------------------------------------------------------------------- #
# Public entry point — post-projection row mutator
# --------------------------------------------------------------------------- #
def apply_matchup_intel(
    snap: dict,
    rows: List[dict],
    *,
    bias_table: Optional[Dict[int, Dict[str, float]]] = None,
    shrink: float = DEFAULT_SHRINK,
    table_path: Optional[Path] = None,
) -> List[dict]:
    """Apply the per-player in-game scorer-bias correction (post-projection hook).

    **When ``CV_INGAME_MATCHUP_INTEL`` is OFF** (default): returns ``rows``
    UNCHANGED — byte-identical, no key mutations.

    **When ON:**
    For each row where ``stat`` in {pts, fg3m} and the player has a trusted bias
    entry, ``projected_final`` is lowered by ``shrink * bias`` (floored at the
    player's current accumulation). A diagnostic ``scorer_bias_applied`` field is
    stamped (non-destructive). Rows for players with no table entry, non-scoring
    stats, or missing projection are untouched.

    Args:
        snap: canonical snapshot dict (read-only).
        rows: projection rows (mutated in place for corrected players).
        bias_table: in-memory ``{pid: {stat: bias}}`` (offline experiment passes
            its walk-forward table here). If None, loaded from ``table_path`` /
            the default committed artifact.
        shrink: shrinkage on the bias (default 0.4, the held-out optimum).
        table_path: override artifact path (tests).
    """
    if not _flag_on():
        return rows   # byte-identical when OFF

    table = bias_table if bias_table is not None else load_bias_table(table_path)
    if not table:
        return rows   # no artifact -> safe no-op

    for r in rows:
        try:
            stat = r.get("stat")
            if stat not in CORRECT_STATS:
                continue
            pid_raw = r.get("player_id")
            if pid_raw is None:
                continue
            pid = int(pid_raw)
            rec = table.get(pid)
            if not rec or stat not in rec:
                continue
            proj = r.get("projected_final")
            if proj is None:
                continue
            cur = _current_so_far(r, stat)
            new = correct_value(float(proj), cur, rec[stat], shrink)
            r["projected_final"] = new
            if "scorer_bias_applied" not in r:
                r["scorer_bias_applied"] = float(shrink) * float(rec[stat])
        except Exception:
            continue   # per-row safety net
    return rows


def _current_so_far(row: dict, stat: str) -> float:
    """Best-effort current accumulation for the floor.

    Live-engine rows carry the current value under ``current`` or ``<stat>_so_far``
    or ``current_<stat>``; fall back to 0.0 (never raises the floor above proj).
    """
    for k in ("current", f"{stat}_so_far", f"p_{stat}_so_far", f"current_{stat}",
              "so_far"):
        v = row.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return 0.0


__all__ = [
    "apply_matchup_intel",
    "correct_value",
    "load_bias_table",
    "build_bias_table",
    "CORRECT_STATS",
    "DEFAULT_SHRINK",
    "DEFAULT_MIN_GAMES",
]
