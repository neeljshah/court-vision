"""Both bars, or it is not AHEAD (S14).

S14 is the ONLY bar-loosening change in the harness program. A within-family
Benjamini-Hochberg bar at q=0.05 is strictly LOOSER, for a hypothesis inside a
family of more than one member, than the global Bonferroni bar
`deflated_metrics.deflated_p(raw_p, k_cumulative)` that every trial has faced so
far. It ships under three conditions and this module enforces the second and
third of them:

  (i)   the families are FROZEN in docs/evidence/harness/FWER_FAMILIES_SPEC_2026-09-03.md,
        committed BEFORE the first family-relative trial. `load_families` pins that
        file by `git hash-object` and every verdict this module returns carries the
        blob id, so a verdict priced against an edited partition is self-evident.
  (ii)  every AHEAD prints BOTH bars and requires BOTH: `dual_bar_verdict` returns
        `global_pass` AND `family_pass` and sets AHEAD only when both are true.
  (iii) no past verdict is re-scored. TRUE BY CONSTRUCTION: `dual_bar_verdict` takes
        p-values as arguments and never opens the FWER charge ledger, the results
        DB, or any historical artifact. It cannot reach a recorded verdict, so it
        cannot restate one under the looser bar.

The global bar is UNCHANGED: `deflated_p`, `eps_eff`, `min_corpora_eff` and the
cumulative K are untouched, and K is still charged and reported on every trial.

Calibration bookkeeping only -- no dollar, ROI, profit or edge claim lives here.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional, Sequence

from scripts.platformkit.combo.fwer_budget import DEFAULT_Q, bh_within_family
from scripts.platformkit.eval_gate.deflated_metrics import deflated_p

SPEC_PATH = Path("docs/evidence/harness/FWER_FAMILIES_SPEC_2026-09-03.md")
DEFAULT_ALPHA = 0.05
_BLOCK = re.compile(r"^### fam: (\S+)\s*$", re.M)


@dataclass(frozen=True)
class Family:
    """One frozen FWER family. `members` are the modelable feature columns."""

    name: str
    sport: str
    horizon: str
    market: str
    features: int
    hypotheses: int
    sources: tuple
    members: tuple


@dataclass(frozen=True)
class FamiliesSpec:
    """The frozen partition, pinned by content."""

    spec_version: str
    q_within_family: float
    spec_path: str
    prereg_sha256: str
    families: tuple

    def get(self, name: str) -> Family:
        for family in self.families:
            if family.name == name:
                return family
        raise KeyError("family %r is not in %s (%d frozen families); a family invented "
                       "after the fact is not a family" % (name, self.spec_path,
                                                           len(self.families)))


def git_blob_id(path: Any) -> str:
    """Content pin identical to `git hash-object <path>`, tamper-evident without a clock.

    Duplicated from foundry/tiers.py rather than imported: importing it would make
    eval_gate depend on foundry, which already depends on eval_gate.
    """
    return subprocess.run(["git", "hash-object", str(path)], capture_output=True, text=True,
                          check=True).stdout.strip()


def _field(text: str, name: str) -> str:
    match = re.search(r"^\s*%s:\s*(.+?)\s*$" % name, text, re.M)
    if match is None:
        raise ValueError("families spec is missing field %r" % name)
    return match.group(1)


@lru_cache(maxsize=4)
def load_families(path: Any = SPEC_PATH) -> FamiliesSpec:
    """Read the FROZEN family partition. This never consults disk state or a corpus:
    the families are whatever the committed spec says they are, which is the point."""
    path = Path(path)
    text = path.read_text(encoding="ascii")
    head, *blocks = _BLOCK.split(text)
    families = []
    for name, body in zip(blocks[0::2], blocks[1::2]):
        members = tuple(m.strip() for m in _field(body, "members").split(",") if m.strip())
        family = Family(name, _field(body, "sport"), _field(body, "horizon"),
                        _field(body, "market"), int(_field(body, "features")),
                        int(_field(body, "hypotheses")),
                        tuple(s.strip() for s in _field(body, "sources").split(",")), members)
        if len(members) != family.features:
            raise ValueError("family %s declares %d features but enumerates %d members"
                             % (name, family.features, len(members)))
        families.append(family)
    if not families:
        raise ValueError("families spec %s froze no families" % path)
    return FamiliesSpec(_field(head, "spec_version"), float(_field(head, "q_within_family")),
                        path.as_posix(), git_blob_id(path), tuple(families))


def dual_bar_verdict(raw_p: float, k_global: int, family_p_values: Sequence[float],
                     q: float = DEFAULT_Q, alpha: float = DEFAULT_ALPHA,
                     family: Optional[str] = None, spec_path: Any = SPEC_PATH) -> dict:
    """Price ONE hypothesis against BOTH bars. AHEAD requires both; either failure blocks.

    `family_p_values` are the raw p-values of every scored member of this hypothesis'
    OWN frozen family, and `raw_p` must be one of them -- scoring a hypothesis against
    some other family's p-values is family shopping, so it raises rather than returns.

    Reads no ledger and no stored verdict: condition (iii), no re-scoring, holds by
    construction. Returns both bars, the verdict, and the frozen spec's content pin.
    """
    if not (0.0 <= raw_p <= 1.0):
        raise ValueError("raw_p must be in [0,1], got %r" % (raw_p,))
    if not (0.0 < alpha <= 1.0):
        raise ValueError("alpha must be in (0,1], got %r" % (alpha,))
    values = [float(p) for p in family_p_values]
    if not any(p == float(raw_p) for p in values):
        raise ValueError("raw_p %r is not among the %d family p-values; a hypothesis is "
                         "priced inside its OWN frozen family" % (raw_p, len(values)))
    spec = load_families(spec_path)
    if family is not None:
        spec.get(family)          # raises on a family invented after the fact
    bh = bh_within_family(values, q)
    index = next(i for i, p in enumerate(values) if p == float(raw_p))
    global_p = deflated_p(float(raw_p), int(k_global))
    global_pass = global_p < float(alpha)
    family_pass = bool(bh.rejected[index])
    blocked = [name for name, ok in (("global", global_pass), ("family", family_pass)) if not ok]
    return {
        "verdict": "AHEAD" if not blocked else "NOT AHEAD",
        "blocked_by": tuple(blocked),
        "raw_p": float(raw_p),
        "family": family,
        # bar 1 -- global Bonferroni over the cumulative charge ledger (UNCHANGED by S14)
        "k_global": int(k_global), "alpha": float(alpha),
        "deflated_p": global_p, "global_pass": global_pass,
        # bar 2 -- within-family Benjamini-Hochberg (the loosening, admissible only with bar 1)
        "q": float(q), "n_family": bh.n, "family_discoveries": bh.n_discoveries,
        "bh_adjusted_p": bh.adjusted[index], "bh_threshold": bh.threshold,
        "family_pass": family_pass,
        "families_spec_path": spec.spec_path, "families_spec_sha": spec.prereg_sha256,
        "families_spec_version": spec.spec_version, "n_families": len(spec.families),
    }


def render_bars(result: dict) -> str:
    """One ASCII line carrying BOTH bars -- what an AHEAD must print (condition ii)."""
    return ("verdict=%s blocked_by=%s raw_p=%.6g | GLOBAL k=%d deflated_p=%.6g alpha=%.4g "
            "pass=%s | FAMILY %s q=%.4g n=%d bh_adj_p=%.6g pass=%s | spec=%s@%s" % (
                result["verdict"], ",".join(result["blocked_by"]) or "-", result["raw_p"],
                result["k_global"], result["deflated_p"], result["alpha"], result["global_pass"],
                result["family"] or "-", result["q"], result["n_family"],
                result["bh_adjusted_p"], result["family_pass"],
                result["families_spec_version"], result["families_spec_sha"][:12]))
