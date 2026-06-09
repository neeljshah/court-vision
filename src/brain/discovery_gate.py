"""src/brain/discovery_gate.py — P7.0 / V3a: discovery step-0 corpus-verification gate.

Operationalizes RED-A §A1 (the keystone): BEFORE building a cross-season genetic/MI search over a new
grain, PRINT the per-season labeled-row counts and REFUSE the cross-season search when min(per-season
labeled n) < the gate_nmin floor. If blocked, the discovery engine runs a single enumerated
family_key-dedup pass classed single-season-research instead of a GA.

Read-only; pandas lazy-imported. DEFAULT-OFF: this is a gate the discovery engine calls, not a live path.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.dirname(os.path.dirname(_HERE))  # .../src
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from loop.gate_nmin import classify_power, effective_season_count, passes_n_min  # noqa: E402


def per_season_counts(df, season_col: str = "season", target_col: Optional[str] = None) -> Dict[str, int]:
    """Count rows per season label (blank/NaN seasons kept under key "" — they are unlabeled).

    If ``target_col`` is given, only rows with a non-null target are counted (a row with no realized
    outcome carries no cross-season signal).
    """
    if season_col not in getattr(df, "columns", []):
        return {}
    sub = df
    if target_col and target_col in df.columns:
        sub = df[df[target_col].notna()]
    counts: Dict[str, int] = {}
    for s, n in sub[season_col].value_counts(dropna=False).items():
        key = "" if (s is None or (isinstance(s, float) and s != s)) else str(s).strip()
        counts[key] = counts.get(key, 0) + int(n)
    return counts


def verify_corpus(source, grain: str, season_col: str = "season",
                  target_col: Optional[str] = None, floors: Optional[dict] = None) -> Dict[str, Any]:
    """Return a corpus power report. ``source`` may be a DataFrame or a parquet path."""
    if hasattr(source, "columns"):
        df = source
    else:
        import pandas as pd  # lazy
        df = pd.read_parquet(source)
    counts = per_season_counts(df, season_col, target_col)
    ok, reason = passes_n_min(counts, grain, floors)
    return {
        "grain": grain,
        "per_season": counts,
        "labeled_seasons": effective_season_count(counts),
        "passes_n_min": ok,
        "power_class": classify_power(counts, grain, floors),
        "reason": reason,
        "total_rows": int(getattr(df, "shape", (0,))[0]),
    }


def gate_discovery(grain: str, source, season_col: str = "season",
                   target_col: Optional[str] = None, floors: Optional[dict] = None) -> Dict[str, Any]:
    """Decide whether a cross-season GA search is permitted for this grain/corpus (RED-A §A1)."""
    rep = verify_corpus(source, grain, season_col, target_col, floors)
    cross = rep["power_class"] == "cross_season"
    rep["ga_allowed"] = cross
    rep["mode"] = "cross_season_GA" if cross else "single_season_enumerated_pass"
    rep["recommendation"] = (
        "OK: >=2 labeled seasons each above n_min; cross-season GA search permitted."
        if cross else
        "BLOCKED: single-season-effective. Run a single enumerated family_key-dedup pass classed "
        "single-season-research (RED-A A1); do NOT run a cross-season GA on a thin/one-season corpus."
    )
    return rep


def print_report(rep: Dict[str, Any]) -> str:
    """Human-readable per-season breakdown (RED-A's 'PRINT the per-season labeled-row count')."""
    lines = [
        f"[discovery step-0] grain={rep['grain']} total_rows={rep.get('total_rows')}",
        f"  per-season labeled counts: {rep['per_season']}",
        f"  labeled_seasons={rep['labeled_seasons']} passes_n_min={rep['passes_n_min']} "
        f"power_class={rep['power_class']}",
        f"  -> mode={rep.get('mode')}: {rep.get('recommendation')}",
    ]
    out = "\n".join(lines)
    print(out)
    return out
