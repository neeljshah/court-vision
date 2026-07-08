"""Honesty labels for cited intelligence -- MATTERS_PROVISIONAL / NULL / UNTESTABLE
/ not-in-ledger, read straight from data/cache/intel_claims/claim_weights.jsonl
(the gate's own verdicts; this module never re-derives a verdict).
"""
from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Dict, List

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CLAIM_WEIGHTS = _REPO_ROOT / "data/cache/intel_claims/claim_weights.jsonl"

# section family -> claim_weights family name it maps to. Sections with no
# matching family (concession, shooting-luck) fall through to the "not in
# ledger" label below -- that absence is itself an honest signal.
FAMILY_BY_SECTION: Dict[str, str] = {
    "gravity": "nba_gravity_proxy_claims",
    "lineup_spacing": "nba_lineup_spacing_claims",
    "on_off": "nba_on_off_claims",
    "shooting": "nba_shooting_claims",
}


@functools.lru_cache(maxsize=1)
def _by_family() -> Dict[str, List[str]]:
    fams: Dict[str, List[str]] = {}
    if not _CLAIM_WEIGHTS.exists():
        return fams
    with open(_CLAIM_WEIGHTS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            fams.setdefault(d.get("family", ""), []).append(d.get("verdict", "UNKNOWN"))
    return fams


def label_for_family(family: str) -> str:
    """One-line honesty label for a claim_weights family (all rows collapsed)."""
    verdicts = _by_family().get(family)
    if not verdicts:
        return "NOT IN CLAIM LEDGER (untested by the gate)"
    uniq = sorted(set(verdicts))
    if len(uniq) == 1:
        return f"{uniq[0]} (gate: {len(verdicts)} row(s), family={family})"
    counts = ", ".join(f"{v}={verdicts.count(v)}" for v in uniq)
    return f"MIXED [{counts}] (family={family})"


def label_for_section(section: str) -> str:
    fam = FAMILY_BY_SECTION.get(section)
    if fam is None:
        return "NOT IN CLAIM LEDGER (untested by the gate)"
    return label_for_family(fam)
