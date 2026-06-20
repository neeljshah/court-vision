"""scripts.platformkit.improve.fusion.meta_flex_fwer -- K counts FUSION flexibility.

Feature combos count K = #enumerated combo specs. FUSION adds a DIFFERENT, larger
multiplicity surface: a fused candidate is a CHOICE of (base-learner subset) x (meta
family) x (regime split) x (re-fusion map). Every such choice is a test; trying many
and keeping the lucky one is exactly how a meta-learner manufactures an in-sample win.
So the fusion FWER budget must count THAT product, persist it to a ledger, and make the
per-candidate alpha STRICTLY decrease as the meta-flexibility widens.

This module is the K-counting + alpha layer for the fusion lane. It REUSES the proven
bar-vs-K math (scripts.platformkit.combo.fwer_budget.eps_eff -- Bonferroni-on-eps) and
adds ONLY: the meta-flexibility K product, a Benjamini-Hochberg step-up over K DM
p-values, and a ledger round-trip that makes K non-recomputable DOWNWARD (R3: a
borderline candidate cannot be cleared by quietly shrinking K).

  meta_flex_k(n_base_subsets, n_meta_families, n_regime_splits, n_refusion_maps)
      = product of the four counts ACTUALLY tried this cycle (each clamped >=1).
  fusion_alpha(eps, K) = eps_eff(eps, K) = eps / max(1, K)   -- monotone decreasing in K.
  bh_threshold(p_values, eps)  -- BH step-up: the largest threshold any p clears.
  cumulative_k / persist_k / load_k  -- ledger round-trip (append-only running total).

K is read from the ledger, NEVER recomputed downward. Calibration, not edge; no $/ROI.
numpy-free (stdlib only); ASCII; <=300 LOC.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import List, Sequence

from scripts.platformkit.combo.fwer_budget import DEFAULT_EPS, cumulative_k, eps_eff

logger = logging.getLogger("meta_flex_fwer")

__all__ = [
    "DEFAULT_EPS", "meta_flex_k", "fusion_alpha", "bh_threshold",
    "cumulative_k", "persist_k", "load_k",
]


def meta_flex_k(n_base_subsets: int, n_meta_families: int,
                n_regime_splits: int, n_refusion_maps: int) -> int:
    """K = (#base subsets) x (#meta families) x (#regime splits) x (#re-fusion maps).

    Each factor is the number ACTUALLY tried this cycle (counted from enumerated spec
    ids upstream), clamped to >=1 so a degenerate single choice does not collapse K to 0
    and loosen the bar. This is the multiplicity the fusion search really faces; a wider
    search => larger K => stricter per-candidate alpha (fusion_alpha below).
    """
    factors = (n_base_subsets, n_meta_families, n_regime_splits, n_refusion_maps)
    k = 1
    for f in factors:
        k *= max(1, int(f))
    return int(k)


def fusion_alpha(eps: float, k: int) -> float:
    """Per-candidate FWER threshold for the fusion lane = eps / max(1, K).

    REUSES eps_eff (the proven Bonferroni-on-eps curve) -- the fusion code CONSUMES the
    bar and cannot override it. STRICTLY decreasing in K: a fused candidate clearing at
    K=1 must clear a far stricter bar once the meta-flexibility is wide.
    """
    return eps_eff(eps, k)


def bh_threshold(p_values: Sequence[float], eps: float = DEFAULT_EPS) -> float:
    """Benjamini-Hochberg step-up threshold over K DM p-values.

    Sort p ascending; the BH-significant cutoff is the largest p[i] with
    p[i] <= (i+1)/m * eps. Returns that cutoff (a p-value <= it is BH-significant), or
    0.0 when NOTHING clears (so no candidate passes -- the conservative, honest default).
    m = len(p_values) is the family size; a wider family lowers each step's bar, so BH,
    like Bonferroni, TIGHTENS as the search widens.
    """
    ps = sorted(float(p) for p in p_values)
    m = len(ps)
    if m == 0:
        return 0.0
    if not (0.0 < eps <= 1.0):
        raise ValueError(f"eps must be in (0,1], got {eps}")
    thresh = 0.0
    for i, p in enumerate(ps):
        if p <= (i + 1) / float(m) * eps:
            thresh = p  # step-up: remember the largest p that clears its rank bar
    return float(thresh)


def persist_k(ledger_path: str, family: str, new_deduped_k: int) -> int:
    """Append this cycle's new deduped K to the family's running total; return cumulative.

    Append-only + atomic: splitting a wide search into many tiny cycles can NEVER reset
    the budget (R3/R18). The stored value is the per-family cumulative K; the returned
    value is prior + new. Never recomputable downward -- a later call can only ADD.
    """
    prior = load_k(ledger_path, family)
    total = cumulative_k(prior, int(new_deduped_k))
    rec = {"family": str(family), "cumulative_k": int(total)}
    _atomic_append(ledger_path, rec)
    return int(total)


def load_k(ledger_path: str, family: str) -> int:
    """Read the family's current cumulative K from the append-only ledger (0 if absent).

    The LAST record for the family wins (append-only running total). A missing or
    malformed ledger reads as 0 -- a fresh start, never a silent loosening.
    """
    if not os.path.exists(ledger_path):
        return 0
    total = 0
    try:
        with open(ledger_path, "r", encoding="ascii") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:  # noqa: BLE001 -- a bad line never wedges the read
                    continue
                if str(rec.get("family")) == str(family):
                    total = int(rec.get("cumulative_k", total))
    except Exception as exc:  # noqa: BLE001 -- IO error -> conservative 0 (fresh start)
        logger.debug("load_k(%s) failed -> 0: %s", family, exc)
        return 0
    return int(max(0, total))


def _atomic_append(path: str, record: dict) -> None:
    """Append one JSON record durably (read-existing + atomic-replace; ASCII)."""
    lines: List[str] = []
    if os.path.exists(path):
        with open(path, "r", encoding="ascii") as fh:
            lines = [ln.rstrip("\n") for ln in fh if ln.strip()]
    lines.append(json.dumps(record, ensure_ascii=True, sort_keys=True))
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="ascii") as fh:
            fh.write("\n".join(lines) + "\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
