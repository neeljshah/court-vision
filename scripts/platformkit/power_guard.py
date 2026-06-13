"""scripts.platformkit.power_guard — Per-season statistical-power guard.

Wraps src.loop.gate_nmin pure functions at the HARNESS/INTAKE layer so that
thin second-season "cross-season survivors" cannot be claimed.

Design authority: ARCHITECTURE §2 + RED_A §A5.

INVARIANT: this module ONLY imports from src.loop.gate_nmin (read-only).
It does NOT edit src/, kernel/, or src/loop/gate.py.

Public API
----------
power_check(dates, target, per_season_min=None) -> dict
    Compute per-season labeled-n, call gate_nmin.passes_n_min /
    classify_power, return structured result dict.

guard_catalog_rows(rows, bundle_dates, bundle_target) -> rows
    Annotate each catalog result row with power_check; if power fails,
    downgrade claimability of non-REJECT verdicts WITHOUT changing the gate
    verdict.  The guard is an ADDITIONAL honest filter — never loosens.

CLI (module main): print a demo power classification table.

F5: ZERO imports from domains.* / src.data / src.sim / src.tracking.
Never edits src/ or kernel/.
"""
from __future__ import annotations

import re
import sys
from typing import Any, Dict, List, Optional, Sequence

# ---------------------------------------------------------------------------
# Read-only import from the canonical pure-function module.
# We delegate ALL math; we do NOT reimplement classify_power / passes_n_min.
# ---------------------------------------------------------------------------
from src.loop.gate_nmin import (
    DEFAULT_FLOORS,
    classify_power,
    effective_season_count,
    passes_n_min,
)

__all__ = ["power_check", "guard_catalog_rows"]

# ---------------------------------------------------------------------------
# Season-year parsing helpers
# ---------------------------------------------------------------------------

_SEASON_RE = re.compile(
    r"(\d{4})-(\d{2})"   # e.g. "2024-25"  →  year 2024  (standard NBA label)
    r"|(\d{4})"          # e.g. "2024"      →  year 2024
)


def _parse_season_from_date(date_str: str) -> str:
    """Return a canonical season label from an ISO-date string.

    NBA convention: "2024-25" means games played Aug 2024 – Jun 2025.
    We bucket by the *calendar year* of the date so games in calendar-year
    2025 fall in season "2024-25" and games in calendar-year 2024 fall in
    season "2023-24".

    Strategy: parse the 4-digit calendar year from the date string, then
    subtract 1 if the month is Aug–Dec (new season not yet started in July
    of that year).  The guard is conservative: if parsing fails we assign
    the date to an empty (unlabeled) bucket, which gate_nmin treats as
    non-evidence.
    """
    if not date_str or not isinstance(date_str, str):
        return ""
    # Try YYYY-MM-DD or YYYY-MM or YYYY
    m = re.search(r"(\d{4})-(\d{2})(?:-\d{2})?", date_str)
    if m:
        year = int(m.group(1))
        month = int(m.group(2))
        # Oct/Nov/Dec belong to the *next* season start (same as NBA convention)
        # e.g. 2024-10-01 → season "2024-25"
        # e.g. 2025-01-15 → season "2024-25"
        # e.g. 2025-10-01 → season "2025-26"
        if month >= 10:
            return f"{year}-{str(year + 1)[-2:]}"
        else:
            return f"{year - 1}-{str(year)[-2:]}"
    # Bare year
    m2 = re.search(r"(\d{4})", date_str)
    if m2:
        year = int(m2.group(1))
        return f"{year - 1}-{str(year)[-2:]}"
    return ""


def _season_counts_from_dates(dates: Sequence[str]) -> Dict[str, int]:
    """Group dates by season label and count rows per season."""
    counts: Dict[str, int] = {}
    for d in dates:
        label = _parse_season_from_date(d)
        counts[label] = counts.get(label, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# power_check
# ---------------------------------------------------------------------------

def power_check(
    dates: Sequence[str],
    target: Sequence[Any],
    per_season_min: Optional[int] = None,
    grain: str = "player_game",
) -> Dict[str, Any]:
    """Compute per-season statistical-power classification for a bundle.

    Parameters
    ----------
    dates:
        ISO date strings (one per row), e.g. ``["2024-11-01", "2025-02-14", ...]``.
        Used to bucket rows into NBA seasons.
    target:
        Target array (one per row).  Used for n-parity checks; we do NOT compute
        any statistics from it here — the gate owns that.
    per_season_min:
        Override the per-season minimum row count.  If None, uses
        ``DEFAULT_FLOORS["player_game"]`` (3,000).  Callers running on smaller
        grains should pass the appropriate floor (e.g. 82 for sim_lever_games).
    grain:
        Grain name forwarded to ``gate_nmin.passes_n_min`` / ``classify_power``.
        Must be a key in DEFAULT_FLOORS or a custom floor is set via per_season_min.

    Returns
    -------
    dict with keys:
        per_season_n   : {season_label: row_count}
        min_season_n   : int — smallest per-labeled-season count
        n_seasons      : int — number of distinct labeled seasons
        power_class    : "OK" | "THIN" | "RESEARCH"
            OK       → classify_power == "cross_season" (passes floor, ≥2 seasons)
            THIN     → ≥2 seasons but min_n < floor (fails passes_n_min)
            RESEARCH → effective_season_count < 2 (single-season effective)
        passes         : bool — True iff power_class == "OK"
        note           : human-readable reason string from passes_n_min
    """
    n_rows = len(dates)
    if len(target) != n_rows:
        raise ValueError(
            f"dates ({n_rows}) and target ({len(target)}) must have the same length"
        )

    # Build season → count mapping
    season_counts = _season_counts_from_dates(dates)

    # Resolve floors dict: honour per_season_min override
    floors: Optional[Dict[str, int]] = None
    if per_season_min is not None:
        floors = {**DEFAULT_FLOORS, grain: per_season_min}

    # Delegate to gate_nmin pure functions (no math here)
    passes_bool, note = passes_n_min(season_counts, grain, floors)
    power_cls_raw = classify_power(season_counts, grain, floors)  # "cross_season" | "single_season_effective"
    eff_seasons = effective_season_count(season_counts)

    # Translate to the guard's three-way classification
    labeled = {k: v for k, v in season_counts.items() if k and k.strip()}
    min_n = min(labeled.values()) if labeled else 0

    if power_cls_raw == "cross_season":
        power_class = "OK"
    elif eff_seasons >= 2:
        # ≥2 seasons present but floor not met → THIN (data exists, just thin)
        power_class = "THIN"
    else:
        # Single-season or no labeled seasons
        power_class = "RESEARCH"

    return {
        "per_season_n": season_counts,
        "min_season_n": min_n,
        "n_seasons": eff_seasons,
        "power_class": power_class,
        "passes": passes_bool and power_cls_raw == "cross_season",
        "note": note,
    }


# ---------------------------------------------------------------------------
# guard_catalog_rows
# ---------------------------------------------------------------------------

def guard_catalog_rows(
    rows: List[Dict[str, Any]],
    bundle_dates: Sequence[str],
    bundle_target: Sequence[Any],
    per_season_min: Optional[int] = None,
    grain: str = "player_game",
) -> List[Dict[str, Any]]:
    """Annotate catalog result rows with power_check; downgrade claimability.

    The guard is an ADDITIONAL honest filter — it NEVER loosens the gate's
    own verdict.  It only adds metadata and sets ``power_blocked=True`` when
    statistical power is insufficient for a cross-season claim.

    Parameters
    ----------
    rows:
        List of verdict dicts as returned by ``run_catalog_common``.
        Each dict should have at least ``"actual_verdict"`` and ``"name"``.
    bundle_dates:
        ISO date strings for the bundle (shared across all signals in catalog).
    bundle_target:
        Target array for the bundle (used for length-parity checks).
    per_season_min:
        Override floor.  Forwarded to ``power_check``.
    grain:
        Grain name forwarded to ``power_check``.

    Returns
    -------
    Same list of rows, each annotated with:
        power_check    : full dict from power_check()
        power_blocked  : bool — True when power fails for a non-REJECT verdict
        power_note     : human-readable explanation of the block (or None)

    Gate's own verdict fields (actual_verdict, wf_folds, etc.) are NEVER
    modified.  Only claimability metadata is added.
    """
    result = power_check(bundle_dates, bundle_target, per_season_min, grain)
    power_ok = result["passes"]

    annotated: List[Dict[str, Any]] = []
    for row in rows:
        row = dict(row)  # shallow copy — don't mutate caller's list
        row["power_check"] = result

        verdict = row.get("actual_verdict", "")
        # Only flag non-REJECT, non-error verdicts as power_blocked
        if not power_ok and verdict not in ("REJECT", "DEFER", "BUNDLE_ERROR", "GATE_ERROR"):
            row["power_blocked"] = True
            row["power_note"] = (
                f"Cross-season claim blocked — power_class={result['power_class']} "
                f"(min_season_n={result['min_season_n']:,}, "
                f"n_seasons={result['n_seasons']}): {result['note']}"
            )
        else:
            row["power_blocked"] = False
            row["power_note"] = None

        annotated.append(row)

    return annotated


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

def _demo() -> None:
    print("power_guard demo — statistical-power classification\n")
    print(f"DEFAULT_FLOORS = {DEFAULT_FLOORS}\n")

    scenarios = [
        ("Thin second season (below floor)", ["2024-11-01"] * 4000 + ["2025-11-01"] * 50, 3_000, "player_game"),
        ("Balanced two seasons (both above floor)", ["2024-11-01"] * 4000 + ["2025-11-01"] * 3500, 3_000, "player_game"),
        ("Single season only", ["2024-11-01"] * 10000, 3_000, "player_game"),
        ("Sim-lever games — 4 games only", ["2025-01-10"] * 4, 82, "sim_lever_games"),
    ]

    for label, dates, floor, grain in scenarios:
        target = [0.0] * len(dates)
        result = power_check(dates, target, per_season_min=floor, grain=grain)
        print(f"  Scenario: {label}")
        print(f"    grain={grain!r}  floor={floor}  n_total={len(dates)}")
        print(f"    per_season_n  = {result['per_season_n']}")
        print(f"    n_seasons     = {result['n_seasons']}")
        print(f"    min_season_n  = {result['min_season_n']:,}")
        print(f"    power_class   = {result['power_class']}")
        print(f"    passes        = {result['passes']}")
        print(f"    note          = {result['note']}")
        print()


if __name__ == "__main__":
    _demo()
