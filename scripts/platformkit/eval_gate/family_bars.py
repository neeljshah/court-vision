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

S89 amends the partition ONCE, additively: two in-game ARM families are added because all
37 original families are feature grids, so no within-family bar existed for an in-game arm.
Nothing is removed and no bar moves; the pin goes 62702554f -> new and spec_version
s14-families-v1 -> s89-families-v2, which is exactly the tamper-evidence condition (i) is
for. Condition (iii) holds: the three charged in-game verdicts keep their own artifacts.

The global bar is UNCHANGED: `deflated_p`, `eps_eff`, `min_corpora_eff` and the
cumulative K are untouched, and K is still charged and reported on every trial.

Calibration bookkeeping only -- no dollar, ROI, profit or edge claim lives here.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional, Sequence

from statsmodels.stats.multitest import multipletests

from scripts.platformkit.combo.fwer_budget import DEFAULT_Q, BHResult, bh_within_family
from scripts.platformkit.eval_gate.deflated_metrics import deflated_p

SPEC_PATH = Path("docs/evidence/harness/FWER_FAMILIES_SPEC_2026-09-03.md")
LEDGER_PATH = Path("data/cache/eval_gate/backtest_fwer.jsonl")
DEFAULT_ALPHA = 0.05
# S89. Three in-game ARM trials were charged (k_cumulative 15, 16, 17) as families of one
# OUTSIDE the partition, before any arm family was frozen. This maps those historical
# strings onto the two new frozen families so within-family K counts them retroactively.
# The ledger is NEVER rewritten and no recorded verdict is re-scored: an alias only changes
# how a NAME resolves, and this module still prices the p-values its caller supplies.
FAMILY_ALIASES = {
    "ingame_mlb_arms": "ingame_arms_mlb",
    "ingame_mlb_clamp": "ingame_arms_mlb",
    "ingame_nba_halftime_asof": "ingame_arms_nba",
}
# The q-rule is a PREREG choice: it is declared per family in the frozen spec, never
# picked after the p-values are in. Both are computed and printed on every verdict.
Q_RULES = ("fdr_bh", "fdr_by")
DEFAULT_Q_RULE = "fdr_bh"
KINDS = ("grid", "arm", "tickgrid")
DEFAULT_KIND = "grid"
_BLOCK = re.compile(r"^### fam: (\S+)\s*$", re.M)


@dataclass(frozen=True)
class Family:
    """One frozen FWER family. `members` are the modelable feature columns.

    `q_rule` is OPTIONAL in the spec file and defaults to fdr_bh, so the frozen
    2026-09-03 partition (which declares none) keeps blob id 62702554f unchanged.
    """

    name: str
    sport: str
    horizon: str
    market: str
    features: int
    hypotheses: int
    sources: tuple
    members: tuple
    q_rule: str = DEFAULT_Q_RULE
    # S89. "grid": members are columns the 9-transform grammar enumerates. "arm": members
    # are whole predictors, which nothing transforms, so a feature enumerator SKIPS them.
    # S102. "tickgrid": members are BASE columns of a derived in-game grammar whose closed
    # construction rule lives in its own spec block, not in the 9-transform alphabet. Like
    # "arm" it is skipped by the pregame feature enumerator.
    kind: str = DEFAULT_KIND


@dataclass(frozen=True)
class FamiliesSpec:
    """The frozen partition, pinned by content."""

    spec_version: str
    q_within_family: float
    spec_path: str
    prereg_sha256: str
    families: tuple

    def get(self, name: str) -> Family:
        name = resolve_family(name)
        for family in self.families:
            if family.name == name:
                return family
        raise KeyError("family %r is not in %s (%d frozen families); a family invented "
                       "after the fact is not a family" % (name, self.spec_path,
                                                           len(self.families)))


def resolve_family(name: Optional[str]) -> Optional[str]:
    """The frozen family a (possibly historical) ledger family string belongs to (S89)."""
    return None if name is None else FAMILY_ALIASES.get(name, name)


def k_family(family: str, ledger_path: Any = LEDGER_PATH) -> int:
    """How many charges the ledger ALREADY carries for a frozen family, aliases resolved.

    READ-ONLY: it never appends, so it is not a charge and cannot move k_cumulative.
    `ledger.next_k_family` (the WRITE path) still matches the string exactly -- PROPOSED
    patch in docs/research/organization-sprint/ (eval_gate/ledger.py is token-locked).
    """
    target = resolve_family(family)
    path = Path(ledger_path)
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="ascii").splitlines() if line.strip()
               and resolve_family(json.loads(line).get("family")) == target)


def git_blob_id(path: Any) -> str:
    """Content pin identical to `git hash-object <path>`, tamper-evident without a clock.

    Duplicated from foundry/tiers.py rather than imported: importing it would make
    eval_gate depend on foundry, which already depends on eval_gate.
    """
    return subprocess.run(["git", "hash-object", str(path)], capture_output=True, text=True,
                          check=True).stdout.strip()


def _field(text: str, name: str, default: Optional[str] = None) -> str:
    match = re.search(r"^\s*%s:\s*(.+?)\s*$" % name, text, re.M)
    if match is None:
        if default is not None:
            return default
        raise ValueError("families spec is missing field %r" % name)
    return match.group(1)


def _by_within_family(p_values: Sequence[float], q: float) -> BHResult:
    """Benjamini-Yekutieli over ONE family -- BH's dependence-proof sibling, same shape.

    BH assumes PRDS; a family here is the correlated columns of one parquet, which is
    exactly where PRDS is not obvious. BY is valid under ARBITRARY dependence and is
    strictly more conservative, so printing both tells the reader how much of a verdict
    rests on the PRDS assumption. ponytail: not added to combo/fwer_budget.bh_within_family
    because that module is token-locked (docs/evidence/SHARED_MODULE_TOKEN.md).
    """
    if not (0.0 < q <= 1.0):
        raise ValueError("q must be in (0,1], got %r" % (q,))
    values = [float(p) for p in p_values]
    rejected, adjusted, _sidak, _bonf = multipletests(values, alpha=float(q), method="fdr_by")
    flags = tuple(bool(r) for r in rejected)
    hits = [p for p, flag in zip(values, flags) if flag]
    return BHResult(float(q), len(values), len(hits), flags,
                    tuple(float(a) for a in adjusted), max(hits) if hits else 0.0)


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
        q_rule = _field(body, "q_rule", DEFAULT_Q_RULE)
        if q_rule not in Q_RULES:
            raise ValueError("family %s declares q_rule %r; frozen choices are %s"
                             % (name, q_rule, list(Q_RULES)))
        kind = _field(body, "kind", DEFAULT_KIND)
        if kind not in KINDS:
            raise ValueError("family %s declares kind %r; frozen choices are %s"
                             % (name, kind, list(KINDS)))
        family = Family(name, _field(body, "sport"), _field(body, "horizon"),
                        _field(body, "market"), int(_field(body, "features")),
                        int(_field(body, "hypotheses")),
                        tuple(s.strip() for s in _field(body, "sources").split(",")), members,
                        q_rule, kind)
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
    # The DECIDING q-rule is read off the frozen spec BEFORE any p-value is seen; both
    # rules are computed and returned either way, so the reader sees what BY would say.
    q_rule = spec.get(family).q_rule if family is not None else DEFAULT_Q_RULE
    bh, by = bh_within_family(values, q), _by_within_family(values, q)
    deciding = bh if q_rule == "fdr_bh" else by
    index = next(i for i, p in enumerate(values) if p == float(raw_p))
    global_p = deflated_p(float(raw_p), int(k_global))
    global_pass = global_p < float(alpha)
    family_pass = bool(deciding.rejected[index])
    blocked = [name for name, ok in (("global", global_pass), ("family", family_pass)) if not ok]
    return {
        "q_rule": q_rule,
        "fdr_bh_adjusted_p": bh.adjusted[index], "fdr_bh_pass": bool(bh.rejected[index]),
        "fdr_bh_discoveries": bh.n_discoveries,
        "fdr_by_adjusted_p": by.adjusted[index], "fdr_by_pass": bool(by.rejected[index]),
        "fdr_by_discoveries": by.n_discoveries,
        "verdict": "AHEAD" if not blocked else "NOT AHEAD",
        "blocked_by": tuple(blocked),
        "raw_p": float(raw_p),
        "family": family,
        # bar 1 -- global Bonferroni over the cumulative charge ledger (UNCHANGED by S14)
        "k_global": int(k_global), "alpha": float(alpha),
        "deflated_p": global_p, "global_pass": global_pass,
        # bar 2 -- within-family Benjamini-Hochberg (the loosening, admissible only with bar 1)
        "q": float(q), "n_family": deciding.n, "family_discoveries": deciding.n_discoveries,
        "bh_adjusted_p": deciding.adjusted[index], "bh_threshold": deciding.threshold,
        "family_pass": family_pass,
        "families_spec_path": spec.spec_path, "families_spec_sha": spec.prereg_sha256,
        "families_spec_version": spec.spec_version, "n_families": len(spec.families),
    }


def render_bars(result: dict) -> str:
    """One ASCII line carrying BOTH bars -- what an AHEAD must print (condition ii).

    Both q-rules are printed whichever one decides, so nobody has to take the PRDS
    assumption on trust; `rule=` names the one the frozen spec chose beforehand.
    """
    return ("verdict=%s blocked_by=%s raw_p=%.6g | GLOBAL k=%d deflated_p=%.6g alpha=%.4g "
            "pass=%s | FAMILY %s q=%.4g n=%d bh_adj_p=%.6g pass=%s | rule=%s fdr_bh_adj_p=%.6g "
            "pass=%s fdr_by_adj_p=%.6g pass=%s | spec=%s@%s" % (
                result["verdict"], ",".join(result["blocked_by"]) or "-", result["raw_p"],
                result["k_global"], result["deflated_p"], result["alpha"], result["global_pass"],
                result["family"] or "-", result["q"], result["n_family"],
                result["bh_adjusted_p"], result["family_pass"],
                result["q_rule"], result["fdr_bh_adjusted_p"], result["fdr_bh_pass"],
                result["fdr_by_adjusted_p"], result["fdr_by_pass"],
                result["families_spec_version"], result["families_spec_sha"][:12]))


def frozen_family(name: str) -> Optional[Family]:
    """The frozen Family of that name, or None. A family invented after the fact is not one."""
    resolved = resolve_family(name)
    return next((f for f in load_families(SPEC_PATH).families if f.name == resolved), None)


def families_spec_sha() -> str:
    """The content pin of the frozen partition, for embedding beside prereg_sha256."""
    return load_families(SPEC_PATH).prereg_sha256


def charged_bars(raw_p: float, k_global: int, family: str, prior_p_values: Sequence[float],
                 alpha: float = DEFAULT_ALPHA, artifact_path: str = "") -> dict:
    """Price ONE charged trial against both bars and write them into its artifact JSON (S59).

    `prior_p_values` are the raw p-values already recorded for this frozen family; this
    trial's own `raw_p` is appended here, so a family's first trial is honestly a family
    of one rather than borrowing another family's p-values.
    """
    spec = load_families(SPEC_PATH)
    result = dual_bar_verdict(raw_p, k_global, list(prior_p_values) + [float(raw_p)],
                              q=spec.q_within_family, alpha=alpha, family=family)
    result["bars_line"] = render_bars(result)
    if artifact_path:
        path = Path(artifact_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, allow_nan=False, sort_keys=True), encoding="ascii")
    return result
