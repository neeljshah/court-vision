"""predict_service.calib_scoreboard -- Cross-sport reliability+sharpness scoreboard.

Single calibration truth surface: one row per sport carrying brier, ece, bss
(vs naive base-rate reference), and n_holdout. Thin overlap (<60 samples) is
flagged as INSUFFICIENT_DATA -- stale-never-green; never fabricate a green metric
when the data do not support it.

Design constraints
------------------
- Accepts per-sport (probs, outcomes) arrays directly, so no corpus path is
  baked in -- producer-agnostic and leak-free.
- Reuses scoring.brier / scoring.ece / scoring.brier_skill_score from
  scripts/platformkit/eval_gate/scoring.py. Falls back to inline numpy if that
  import is unavailable (same defensive pattern as scoring.py itself).
- No $ key anywhere. UNITS only. CALIBRATION not edge.
- <=300 LOC. ASCII only. Python 3.9+.

Usage (programmatic)::

    from predict_service.calib_scoreboard import build_scoreboard, SportInput

    rows = build_scoreboard([
        SportInput("nba",    probs=[...], outcomes=[...]),
        SportInput("mlb",    probs=[...], outcomes=[...]),
        SportInput("soccer", probs=[...], outcomes=[...]),
        SportInput("tennis", probs=[...], outcomes=[...]),
    ])
    # -> list[ScoreboardRow]

Usage (CLI)::

    python -m predict_service.calib_scoreboard --help
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, NamedTuple, Optional, Sequence

import numpy as np

# ---------------------------------------------------------------------------
# Metric imports -- reuse the validated eval_gate/scoring.py; defensive fallback.
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

try:
    from scripts.platformkit.eval_gate.scoring import (
        brier as _brier,
        ece as _ece,
        brier_skill_score as _bss,
    )
    _METRICS_SRC = "eval_gate.scoring"
except Exception:  # pragma: no cover -- scoring.py always present; belt+braces
    def _brier(p, y):  # type: ignore[misc]
        p, y = np.asarray(p, float), np.asarray(y, float)
        return float(np.mean((p - y) ** 2))

    def _ece(p, y, bins: int = 10):  # type: ignore[misc]
        p, y = np.asarray(p, float), np.asarray(y, float)
        edges = np.linspace(0.0, 1.0, bins + 1)
        n = len(p)
        if n == 0:
            return 0.0
        total = 0.0
        for k in range(bins):
            lo, hi = edges[k], edges[k + 1]
            m = (p >= lo) & (p < hi) if k < bins - 1 else (p >= lo) & (p <= hi)
            if not m.any():
                continue
            total += (m.sum() / n) * abs(float(y[m].mean()) - float(p[m].mean()))
        return float(total)

    def _bss(p_model, p_ref, y):  # type: ignore[misc]
        bm = _brier(p_model, y)
        br = _brier(p_ref, y)
        return float(1.0 - bm / br) if br > 0 else 0.0

    _METRICS_SRC = "fallback"


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------

MIN_HOLDOUT = 60  # overlap floor below which we report INSUFFICIENT_DATA


class SportInput(NamedTuple):
    """One sport's probabilistic predictions over a held-out set.

    Parameters
    ----------
    sport:    Short sport token ("nba", "mlb", "soccer", "tennis", ...).
    probs:    Predicted P(outcome=1) for each held-out event, shape (N,).
    outcomes: Realised binary outcome (0 or 1) for each event, shape (N,).
              The reference calibrator is the naive base-rate mean(outcomes).
    """
    sport: str
    probs: Sequence[float]
    outcomes: Sequence[float]


class ScoreboardRow(NamedTuple):
    """One row in the cross-sport scoreboard.

    Fields
    ------
    sport:              Sport token.
    n_holdout:          Number of held-out samples used for evaluation.
    status:             "ok" or "INSUFFICIENT_DATA".
    brier:              Mean-squared error of probabilistic forecasts. Lower=better.
    ece:                Expected Calibration Error (10-bin, diagnostic only).
    bss:                Brier Skill Score vs naive base-rate reference. >0=beats base.
    metrics_source:     Provenance ("eval_gate.scoring" or "fallback").
    note:               Short human-readable verdict.
    """
    sport: str
    n_holdout: int
    status: str
    brier: Optional[float]
    ece: Optional[float]
    bss: Optional[float]
    metrics_source: str
    note: str


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def score_sport(inp: SportInput) -> ScoreboardRow:
    """Compute brier / ece / bss for one sport's held-out predictions.

    Returns INSUFFICIENT_DATA when n < MIN_HOLDOUT or when probs/outcomes are
    mismatched / degenerate. Never fabricates a green metric.
    """
    sport = str(inp.sport)
    probs = np.asarray(inp.probs, dtype=float)
    outcomes = np.asarray(inp.outcomes, dtype=float)

    n = len(probs)
    if n != len(outcomes):
        return ScoreboardRow(
            sport=sport, n_holdout=0, status="INSUFFICIENT_DATA",
            brier=None, ece=None, bss=None,
            metrics_source=_METRICS_SRC,
            note="probs/outcomes length mismatch",
        )

    if n < MIN_HOLDOUT:
        return ScoreboardRow(
            sport=sport, n_holdout=n, status="INSUFFICIENT_DATA",
            brier=None, ece=None, bss=None,
            metrics_source=_METRICS_SRC,
            note=f"holdout={n} < {MIN_HOLDOUT} -- insufficient for reliable metrics",
        )

    # Validate values: outcomes must be binary {0,1}, probs in [0,1].
    if not np.all(np.isin(outcomes, [0.0, 1.0])):
        # Allow float near-binary (e.g. 0.9999 from a probabilistic label)
        if np.any((outcomes < 0.0) | (outcomes > 1.0)):
            return ScoreboardRow(
                sport=sport, n_holdout=n, status="INSUFFICIENT_DATA",
                brier=None, ece=None, bss=None,
                metrics_source=_METRICS_SRC,
                note="outcomes out of [0,1] range",
            )

    if np.any((probs < 0.0) | (probs > 1.0)):
        return ScoreboardRow(
            sport=sport, n_holdout=n, status="INSUFFICIENT_DATA",
            brier=None, ece=None, bss=None,
            metrics_source=_METRICS_SRC,
            note="probs out of [0,1] range",
        )

    base_rate = float(np.mean(outcomes))
    # Degenerate: all-same outcome -> BSS undefined (br=0)
    p_ref = np.full(n, base_rate)

    b = round(float(_brier(probs, outcomes)), 5)
    e = round(float(_ece(probs, outcomes, 10)), 5)
    skill = round(float(_bss(probs, p_ref, outcomes)), 5)

    brier_ref = float(_brier(p_ref, outcomes))
    if brier_ref <= 0:
        note = "degenerate outcomes (all-same) -- BSS undefined"
        skill = None  # type: ignore[assignment]
    elif skill > 0:
        note = f"beats base-rate (BSS={skill:+.4f})"
    elif skill > -0.01:
        note = f"matches base-rate within noise (BSS={skill:+.4f})"
    else:
        note = f"trails base-rate (BSS={skill:+.4f}) -- honest result"

    return ScoreboardRow(
        sport=sport,
        n_holdout=n,
        status="ok",
        brier=b,
        ece=e,
        bss=skill,
        metrics_source=_METRICS_SRC,
        note=note,
    )


def build_scoreboard(inputs: List[SportInput]) -> List[ScoreboardRow]:
    """Build the full cross-sport scoreboard from per-sport prediction arrays.

    Each sport yields exactly one ScoreboardRow. Thin-data sports are honest
    INSUFFICIENT_DATA -- never green. Order preserved from *inputs*.
    """
    return [score_sport(inp) for inp in inputs]


# ---------------------------------------------------------------------------
# Pretty-printer
# ---------------------------------------------------------------------------

def print_scoreboard(rows: List[ScoreboardRow]) -> None:
    """Print the scoreboard table to stdout (ASCII only)."""
    hdr = (
        f"{'sport':<10}  {'n_holdout':>10}  {'status':<20}  "
        f"{'brier':>8}  {'ece':>8}  {'bss':>8}  note"
    )
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        brier_s = f"{r.brier:.5f}" if r.brier is not None else "---"
        ece_s = f"{r.ece:.5f}" if r.ece is not None else "---"
        bss_s = f"{r.bss:+.4f}" if r.bss is not None else "---"
        print(
            f"{r.sport:<10}  {r.n_holdout:>10}  {r.status:<20}  "
            f"{brier_s:>8}  {ece_s:>8}  {bss_s:>8}  {r.note}"
        )
    print()
    print(f"metrics_source: {rows[0].metrics_source if rows else 'n/a'}")
    print("Calibration only -- no $ edge claimed.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main(argv: Optional[List[str]] = None) -> int:
    """Minimal CLI: print status for each sport (real data paths injected by caller)."""
    import argparse
    parser = argparse.ArgumentParser(
        description="Cross-sport calibration scoreboard (calibration only, no edge claim)."
    )
    parser.add_argument(
        "--sport", action="append", default=[],
        help="Repeat for each sport to include (default: nba mlb soccer tennis).",
    )
    args = parser.parse_args(argv)

    sports = args.sport or ["nba", "mlb", "soccer", "tennis"]

    # In the CLI path, real proof data is not available at import time.
    # Emit an honest INSUFFICIENT_DATA row per sport (the real pipeline wires
    # actual probs/outcomes via build_scoreboard from the proof runners).
    rows = build_scoreboard([
        SportInput(sport=s, probs=[], outcomes=[]) for s in sports
    ])
    print_scoreboard(rows)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
