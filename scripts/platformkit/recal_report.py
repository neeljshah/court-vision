"""scripts/platformkit/recal_report.py — Raw vs. recalibrated ECE reliability report.

HONESTY NOTE — This is a RELIABILITY report, not an edge report.
Calibration != edge: better-calibrated probabilities do NOT imply beating the
closing line or a positive expected value.  See: feedback_accuracy_is_not_edge.md.

PURPOSE
-------
Surfaces the raw-vs-recalibrated ECE story for each sport in a single table,
making explicit that:
  - The soccer adapter carries RAW signal_col (ECE ~0.107) from its Poisson
    O/U model, because domains/soccer/calibration.py's walk_forward_calibrate
    is a STANDALONE module never wired into the live prediction path.
  - The walk-forward-recalibrated ECE (~0.008) is a RELIABILITY improvement
    that is NOT in the live signal_col.
  - Recalibration is NOT an edge.  ECE != CLV.  No edge is claimed.

IMPORTS
-------
Imports measure_sport_recal / measure_recal from scripts/platformkit/recalibration.py
(no reimplementation).  Does NOT touch any adapter, signal_col, or live path.
Does NOT import or edit calibration_conformance.py / recalibration.py — only
imports from them.

CLI
---
python scripts/platformkit/recal_report.py
  Prints the raw vs. recal'd ECE table per sport; graceful-SKIP for absent corpora.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

# Ensure repo root is importable when run as a script.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.recalibration import (  # noqa: E402
    CALIBRATION_NOTE,
    measure_recal,
    measure_sport_recal,
)

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

SPORTS: List[str] = ["tennis", "mlb", "soccer", "nba"]

HONESTY_FOOTER: str = (
    "recalibration improves reliability only; "
    "not in the live prediction path; "
    "calibration != edge; "
    "no edge claimed"
)

# Soccer-specific note: the raw ECE comes from the live signal_col; the
# recal'd ECE uses walk-forward isotonic regression (standalone, not wired).
_SOCCER_LIVE_PATH_NOTE: str = (
    "soccer raw ECE reflects live signal_col (Poisson O/U); "
    "recal'd ECE uses domains/soccer/calibration.py walk_forward_calibrate "
    "which is NOT wired into the adapter — reliability improvement only"
)


# ---------------------------------------------------------------------------
# Core report builder
# ---------------------------------------------------------------------------


def build_report(
    sports: Optional[List[str]] = None,
    min_history: int = 50,
    bins: int = 10,
) -> List[Dict[str, object]]:
    """Return a list of per-sport result dicts (raw_ece, recal_ece, delta, n, …).

    Each dict has keys:
        sport       str   — sport name
        n           int   — corpus size (0 when absent/skipped)
        raw_ece     float — ECE of the raw signal_col (the live value)
        recal_ece   float — ECE after walk-forward isotonic recalibration
        delta       float — raw_ece - recal_ece (positive = reliability gain)
        live_path   bool  — False: recalibration is NOT in the live signal_col
        note        str   — CALIBRATION_NOTE (no edge claim)
        skipped     bool  — True when corpus absent or adapter failed
        error       str   — reason if skipped, else empty string
        sport_note  str   — extra per-sport context (e.g. soccer standalone note)

    CALIBRATION != EDGE.  This function must not be used to claim a betting edge.
    """
    targets = list(sports) if sports is not None else SPORTS
    rows: List[Dict[str, object]] = []

    for sport in targets:
        result = measure_sport_recal(sport, min_history=min_history, bins=bins)
        err = result.get("error", "")
        n = result.get("n", 0)
        raw = result.get("raw_ece", float("nan"))
        rec = result.get("recal_ece", float("nan"))
        delta = result.get("delta", float("nan"))
        skipped = bool(err and n == 0)

        sport_note = _SOCCER_LIVE_PATH_NOTE if sport == "soccer" else ""

        rows.append({
            "sport": sport,
            "n": int(n),
            "raw_ece": float(raw),
            "recal_ece": float(rec),
            "delta": float(delta),
            "live_path": False,       # recalibration never wired into live signal_col
            "note": CALIBRATION_NOTE,
            "skipped": skipped,
            "error": str(err) if err else "",
            "sport_note": sport_note,
        })

    return rows


def format_report(rows: List[Dict[str, object]]) -> str:
    """Return a human-readable reliability table string.

    Includes the mandatory honesty note; uses no edge-claim language.
    """
    lines: List[str] = []

    header = (
        f"\n{'Sport':<10} {'N':>7} {'RawECE':>10} {'RecalECE':>10}"
        f" {'Delta':>8}  {'InLivePath':<12}  Interpretation"
    )
    sep = "-" * (len(header) - 1)   # -1 for leading \n in header

    lines.append("\nRaw vs. Walk-Forward-Recalibrated ECE — Reliability Report")
    lines.append(
        "NOTE: recalibration improves reliability only; "
        "not in the live prediction path; calibration != edge; no edge claimed"
    )
    lines.append(header)
    lines.append(sep)

    for r in rows:
        sport = str(r["sport"])
        if r["skipped"]:
            err_short = str(r["error"])[:70]
            lines.append(f"{sport:<10} [SKIP] {err_short}")
            continue

        n = int(r["n"])
        raw = float(r["raw_ece"])
        rec = float(r["recal_ece"])
        delta = float(r["delta"])
        in_live = "No"   # always No — recalibration is standalone

        def _f(v: float) -> str:
            try:
                return f"{v:10.4f}"
            except (TypeError, ValueError):
                return f"{'n/a':>10}"

        if abs(delta) < 0.002:
            interp = "no meaningful change (already well-calibrated)"
        elif delta > 0:
            interp = f"reliability gain {delta:.4f} (NOT in live path)"
        else:
            interp = f"slight ECE increase {abs(delta):.4f} (already well-calibrated)"

        lines.append(
            f"{sport:<10} {n:>7} {_f(raw)} {_f(rec)} {_f(delta)}"
            f"  {in_live:<12}  {interp}"
        )

    lines.append(sep)
    lines.append("")
    lines.append(f"REMINDER: {HONESTY_FOOTER}")
    lines.append(
        "Soccer note: raw ECE reflects live signal_col; "
        "recal'd ECE uses standalone walk_forward_calibrate — "
        "NOT wired into the adapter or gate."
    )
    lines.append("")
    lines.append(f"CALIBRATION NOTE: {CALIBRATION_NOTE}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# __main__ CLI
# ---------------------------------------------------------------------------


def _main() -> int:
    rows = build_report()
    print(format_report(rows))

    # Exit 1 only if every sport errored (all skipped = no corpora at all).
    all_skipped = all(bool(r["skipped"]) for r in rows)
    if all_skipped:
        print("[WARN] All sports skipped — no corpora available.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
