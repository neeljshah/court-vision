"""scripts.research_harness.hypothesis_enumerator — Deterministic hypothesis coverage map.

Enumerates the finite, bounded candidate-signal space for each sport's leak-free
base columns (single-column transforms + pairwise joints) and cross-references which
candidates are ALREADY TESTED in the signal catalogs vs UNTESTED.

PURPOSE: systematic coverage tracking.  NO edge claims.  Quantifies search breadth.

Base columns sourced from catalog CONTRACT doc-strings:
  tennis         : domains/tennis/signal_catalog.py          (cols 0-4)
  soccer         : domains/soccer/signal_catalog.py          (cols 0-4)
  mlb            : domains/mlb/signal_catalog.py             (cols 0-5)
  basketball_nba : domains/basketball_nba/signal_catalog.py  (cols 0-7)

Candidate space (deterministic, finite):
  Single-col transforms: identity, sign, abs, square, threshold_bucket
  Pairwise joints: diff (a-b), ratio (a/b), product (a*b), interaction (a-b)/(1+|b|)

Usage:  python -m scripts.research_harness.hypothesis_enumerator
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

# ---------------------------------------------------------------------------
# Base-column constants (sourced from catalog CONTRACT blocks)
# ---------------------------------------------------------------------------

#: Source: domains/tennis/signal_catalog.py
TENNIS_BASE_COLS: Tuple[str, ...] = (
    "elo_diff", "surf_diff", "best_of", "rest_days_a", "rest_days_b",
)
#: Source: domains/soccer/signal_catalog.py
SOCCER_BASE_COLS: Tuple[str, ...] = (
    "lam_home", "lam_away", "lam_total", "rest_days_home", "rest_days_away",
)
#: Source: domains/mlb/signal_catalog.py
MLB_BASE_COLS: Tuple[str, ...] = (
    "elo_home", "elo_away", "elo_diff_hfa",
    "rest_days_home", "rest_days_away", "h2h_rate",
)
#: Source: domains/basketball_nba/signal_catalog.py
NBA_BASE_COLS: Tuple[str, ...] = (
    "elo_home", "elo_away", "elo_diff_hfa",
    "rest_days_home", "rest_days_away",
    "home_b2b", "away_b2b", "rolling_win10_home",
)

# NBA included: domains/basketball_nba/ adapter + signal_catalog(s) built this wave.
SPORT_BASE_COLS: Dict[str, Tuple[str, ...]] = {
    "tennis": TENNIS_BASE_COLS,
    "soccer": SOCCER_BASE_COLS,
    "mlb": MLB_BASE_COLS,
    "basketball_nba": NBA_BASE_COLS,
}

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SPORT_CATALOG_PATHS: Dict[str, List[Path]] = {
    "tennis": [
        _REPO_ROOT / "domains" / "tennis" / "signal_catalog.py",
        _REPO_ROOT / "domains" / "tennis" / "signal_catalog_joint.py",
    ],
    "soccer": [
        _REPO_ROOT / "domains" / "soccer" / "signal_catalog.py",
        _REPO_ROOT / "domains" / "soccer" / "signal_catalog_joint.py",
    ],
    "mlb": [
        _REPO_ROOT / "domains" / "mlb" / "signal_catalog.py",
        _REPO_ROOT / "domains" / "mlb" / "signal_catalog_joint.py",
    ],
    "basketball_nba": [
        _REPO_ROOT / "domains" / "basketball_nba" / "signal_catalog.py",
        _REPO_ROOT / "domains" / "basketball_nba" / "signal_catalog_joint.py",
    ],
}

# ---------------------------------------------------------------------------
# Transform definitions
# ---------------------------------------------------------------------------

SINGLE_TRANSFORMS: Tuple[str, ...] = (
    "identity", "sign", "abs", "square", "threshold_bucket",
)

PAIRWISE_JOINTS: Tuple[str, ...] = (
    "diff",        # a - b
    "ratio",       # a / b
    "product",     # a * b
    "interaction", # (a - b) / (1 + |b|)
)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    """A single enumerated hypothesis candidate."""

    sport: str
    kind: str          # "single" or "joint"
    transform: str     # e.g. "abs", "diff", "product"
    cols: Tuple[str, ...]  # (col,) for single; (col_a, col_b) for joint

    @property
    def name(self) -> str:
        """Canonical deterministic name."""
        return f"{self.sport}__{self.transform}__{'_x_'.join(self.cols)}"


@dataclass
class CoverageResult:
    """Coverage map for one sport."""

    sport: str
    candidates: List[Candidate] = field(default_factory=list)
    tested_names: List[str] = field(default_factory=list)
    tested_set: "set[str]" = field(default_factory=set)

    @property
    def n_enumerated(self) -> int:
        return len(self.candidates)

    @property
    def n_tested(self) -> int:
        return len(self.tested_set)

    @property
    def n_untested(self) -> int:
        return self.n_enumerated - self.n_tested

    @property
    def coverage_pct(self) -> float:
        if self.n_enumerated == 0:
            return 0.0
        return 100.0 * self.n_tested / self.n_enumerated


# ---------------------------------------------------------------------------
# Enumeration
# ---------------------------------------------------------------------------


def enumerate_candidates(sport: str, base_cols: Sequence[str]) -> List[Candidate]:
    """Return a deterministic, finite list of hypothesis candidates.

    Single-col: each col × each transform in SINGLE_TRANSFORMS.
    Pairwise joints: each combinations(cols,2) pair × each joint in PAIRWISE_JOINTS.
    Sorted alphabetically first to guarantee order across Python versions.
    """
    cols = tuple(sorted(set(base_cols)))
    out: List[Candidate] = []
    for col in cols:
        for tfm in SINGLE_TRANSFORMS:
            out.append(Candidate(sport=sport, kind="single", transform=tfm, cols=(col,)))
    for col_a, col_b in combinations(cols, 2):
        for jt in PAIRWISE_JOINTS:
            out.append(Candidate(sport=sport, kind="joint", transform=jt, cols=(col_a, col_b)))
    return out


# ---------------------------------------------------------------------------
# Coverage extraction — parse catalog source files (no heavy imports)
# ---------------------------------------------------------------------------

_NAME_RE = re.compile(r"""name\s*(?::\s*str)?\s*=\s*["']([^"']+)["']""")


def _names_from_path(path: Path) -> List[str]:
    """Extract all ``name = "..."`` string values from a catalog source file."""
    if not path.exists():
        return []
    try:
        src = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return _NAME_RE.findall(src)


def extract_tested_names(sport: str) -> List[str]:
    """Return deduplicated signal names found in this sport's catalog source files."""
    names: List[str] = []
    for p in SPORT_CATALOG_PATHS.get(sport, []):
        names.extend(_names_from_path(p))
    seen: set[str] = set()
    return [n for n in names if not (n in seen or seen.add(n))]  # type: ignore[func-returns-value]


# ---------------------------------------------------------------------------
# Matching: conservative — UNTESTED when uncertain
# ---------------------------------------------------------------------------


def _matched(candidate: Candidate, tested: Sequence[str]) -> bool:
    """Return True if the candidate is covered by any tested catalog signal name.

    1. Exact match on candidate.name.
    2. Substring heuristic: all col tokens (len>=3) AND transform keyword appear
       in the tested name (case-insensitive).
    """
    cn = candidate.name.lower()
    tfm = candidate.transform.lower()
    for tn in tested:
        tl = tn.lower()
        if cn == tl:
            return True
        if tfm in tl and all(c.lower() in tl for c in candidate.cols if len(c) >= 3):
            return True
    return False


# ---------------------------------------------------------------------------
# Main coverage computation
# ---------------------------------------------------------------------------


def compute_coverage(sport: str) -> CoverageResult:
    """Enumerate candidates and mark TESTED vs UNTESTED for one sport."""
    base_cols = SPORT_BASE_COLS.get(sport)
    if base_cols is None:
        raise ValueError(f"Unknown sport: {sport!r}. Known: {list(SPORT_BASE_COLS)}")
    candidates = enumerate_candidates(sport, base_cols)
    tested_names = extract_tested_names(sport)
    tested_set = {c.name for c in candidates if _matched(c, tested_names)}
    return CoverageResult(
        sport=sport, candidates=candidates,
        tested_names=tested_names, tested_set=tested_set,
    )


def compute_all_coverage() -> Dict[str, CoverageResult]:
    """Compute coverage for all known sports. Deterministic."""
    return {sport: compute_coverage(sport) for sport in sorted(SPORT_BASE_COLS)}


# ---------------------------------------------------------------------------
# Summary (no edge claims)
# ---------------------------------------------------------------------------


def format_summary(results: Dict[str, CoverageResult]) -> str:
    """Return a plain-text coverage table. Asserts nothing about signal value."""
    hdr = (
        f"{'Sport':<10} {'BaseCols':>8} {'Enumerated':>10} "
        f"{'Tested':>8} {'Untested':>9} {'Coverage%':>10}"
    )
    rows = [
        f"{sport:<10} {len(SPORT_BASE_COLS[sport]):>8} {r.n_enumerated:>10} "
        f"{r.n_tested:>8} {r.n_untested:>9} {r.coverage_pct:>9.1f}%"
        for sport, r in sorted(results.items())
    ]
    return "\n".join([
        "Hypothesis Coverage Map — systematic search tracking only.",
        "Measures search-space coverage; asserts nothing about signal value.",
        "", hdr, "-" * 60, *rows, "",
        "(Tested = NAME-MATCHED to a signal in the catalog source files — a",
        " conservative LOWER BOUND: catalogs test semantically-equivalent",
        " transforms under different names, so true coverage of meaningful",
        " transforms is far higher than these figures. UNTESTED here does NOT",
        " imply an opportunity: exhaustive prior search found markets EFFICIENT",
        " (every tested family REJECTs); coverage % = search breadth, not value.)",
    ])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Print per-sport coverage table to stdout."""
    print(format_summary(compute_all_coverage()))


if __name__ == "__main__":
    main()
