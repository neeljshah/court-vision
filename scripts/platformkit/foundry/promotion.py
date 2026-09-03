"""The FROZEN promotion rule and the T1->T2 promotion itself, lifted out of foundry/tiers.py.

Split out under S59 purely so `tiers.py` stays inside the 300-LOC cap once the dual bar is
wired; the code is unchanged and `tiers` re-exports both names, so every existing importer
(`tiers.PromotionRule`, `tiers.promote`) keeps working byte-for-byte.

The width of a search is policy, not a measurement: it lives in
docs/evidence/harness/FACTORY_TIERS_SPEC_2026-09-03.md, pinned by `git hash-object`, so no
caller can widen the search without editing the spec and changing prereg_sha256.

Calibration bookkeeping only -- no dollar, ROI, profit or edge claim lives here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from scripts.platformkit.eval_gate.family_bars import git_blob_id

SPEC_PATH = Path("docs/evidence/harness/FACTORY_TIERS_SPEC_2026-09-03.md")


@dataclass(frozen=True)
class PromotionRule:
    """The promotion width is FROZEN in the spec file; it is never a function argument."""
    spec_version: str
    top_n: int
    group_by: tuple
    rank_by: str
    partition_seed: int
    alpha: float
    spec_path: str
    prereg_sha256: str

    @classmethod
    def from_spec(cls, path: Any = SPEC_PATH) -> "PromotionRule":
        path, text = Path(path), Path(path).read_text(encoding="ascii")

        def field(name: str) -> str:
            match = re.search(r"^\s*%s:\s*(\S+)\s*$" % name, text, re.M)
            if match is None:
                raise ValueError("spec %s is missing field %r" % (path, name))
            return match.group(1)

        return cls(field("spec_version"), int(field("top_n")), tuple(field("group_by").split(",")),
                   field("rank_by"), int(field("partition_seed")), float(field("alpha")),
                   path.as_posix(), git_blob_id(path))


def promote(t1_results: Sequence[Any], rule: PromotionRule,
            distinct_source_columns: bool = False) -> list:
    """Promote the rule's frozen top_n by T1 Brier improvement within ONE family/ISO-week group.

    The caller supplies the group (rule.group_by names it); the WIDTH comes only off the rule.

    S85 adds `distinct_source_columns` as an OPT-IN pick rule and nothing else: default False
    keeps the ranking byte-identical. S79 measured that in 6 of 12 families the top-5 by screen
    improvement are ONE source column at several `ew` halflives, so a k=5 combination spent its
    parameters on redundancy; with the flag ON the walk takes at most one hypothesis per source
    column, still in improvement order, so k picks come from k distinct columns. It changes which
    hypotheses are promoted, never how many, and never a bar.
    """
    screens = [r for r in t1_results if r.tier == "T1" and r.brier_model is not None]
    if len(screens) != len(t1_results):
        raise ValueError("promote takes T1 screens only; got %d non-T1 rows"
                         % (len(t1_results) - len(screens)))
    families = {r.family for r in screens}
    if len(families) > 1:
        raise ValueError("promote takes one %s group; got families %s"
                         % ("/".join(rule.group_by), sorted(families)))
    ranked = sorted(screens, key=lambda r: (r.brier_model - r.brier_close, r.hash))
    if not distinct_source_columns:
        return [r.hypothesis for r in ranked[:rule.top_n]]
    picked, seen = [], set()
    for result in ranked:
        column = result.hypothesis.feature
        if column not in seen and len(picked) < rule.top_n:
            seen.add(column)
            picked.append(result.hypothesis)
    return picked
