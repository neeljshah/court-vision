"""GATE-A + FDR -- the single most important piece (MASTER_SYSTEM_BUILD section 4A).

At tens of thousands of candidates over a multi-day run, ~N x (false-positive-rate) "validate" by chance.
So the foundry's deliverable is the REJECTION machinery. This module provides:

  - Benjamini-Hochberg + Benjamini-Yekutieli (dependency-robust) FDR control over a p-value pool.
  - An APPEND-ONLY test-event log (every candidate ever tested, PASS and FAIL) at
    data/registry/signal_test_log/part-*.parquet -- this fixes signal_lab.py:87 which OVERWROTE the
    failure record (so a re-rolled family could quietly pass on a second try).
  - family-key anti-re-roll: a family that was already tested gets NO fresh independent test -- its prior
    p carries forward against the same budget (defeats the 'test until significant' leak that beats ANY FDR).
  - A PLANTED-NULL test (B5): feed a batch of pure-noise candidates; under the complete null, BH at alpha
    must keep the family-wise error P(>=1 false discovery) <= alpha. We measure that empirically over many
    null batches and assert it holds -- proof the FDR machinery actually controls error, not a claim.

  python scripts/team_system/signals/gates.py        # run the planted-null test (writes B5 marker)
"""
from __future__ import annotations
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from registry.store import REGISTRY_DIR, registry_lock  # noqa: E402

TEST_LOG_DIR = os.path.join(REGISTRY_DIR, "signal_test_log")
ALPHA = 0.05


# --------------------------------------------------------------------------- FDR procedures
def benjamini_hochberg(pvals, alpha: float = ALPHA) -> np.ndarray:
    """Return a boolean mask of rejections (discoveries) controlling FDR <= alpha (independence/PRDS)."""
    p = np.asarray(pvals, float)
    m = len(p)
    if m == 0:
        return np.array([], bool)
    order = np.argsort(p)
    ranked = p[order]
    thresh = alpha * (np.arange(1, m + 1) / m)
    below = ranked <= thresh
    k = np.nonzero(below)[0].max() + 1 if below.any() else 0
    mask = np.zeros(m, bool)
    if k > 0:
        mask[order[:k]] = True
    return mask


def benjamini_yekutieli(pvals, alpha: float = ALPHA) -> np.ndarray:
    """BH with the harmonic c(m) correction -> valid under ARBITRARY dependence (the safe default across
    correlated signal batches over a multi-day run)."""
    p = np.asarray(pvals, float)
    m = len(p)
    if m == 0:
        return np.array([], bool)
    cm = np.sum(1.0 / np.arange(1, m + 1))
    return benjamini_hochberg(p, alpha / cm)


# --------------------------------------------------------------------------- append-only test log
def _log_parts() -> list:
    if not os.path.isdir(TEST_LOG_DIR):
        return []
    return sorted(f for f in os.listdir(TEST_LOG_DIR) if f.startswith("part-") and f.endswith(".parquet"))


def test_log() -> pd.DataFrame:
    parts = _log_parts()
    if not parts:
        return pd.DataFrame(columns=["hash", "family_key", "definition", "p", "batch_id", "asof", "verdict"])
    return pd.concat([pd.read_parquet(os.path.join(TEST_LOG_DIR, p)) for p in parts], ignore_index=True)


def log_tests(rows: list) -> None:
    """Append an immutable batch of test events (NEVER overwrites -- the fix for signal_lab.py:87)."""
    if not rows:
        return
    os.makedirs(TEST_LOG_DIR, exist_ok=True)
    with registry_lock():
        seq = len(_log_parts())
        part = os.path.join(TEST_LOG_DIR, f"part-{seq:06d}-{int(time.time()*1000)%1000000:06d}.parquet")
        tmp = part + ".tmp"
        pd.DataFrame(rows).to_parquet(tmp, index=False)
        os.replace(tmp, part)


def family_seen(family_key: str) -> bool:
    """True if this family was already tested (anti-re-roll: no fresh independent test on the same data)."""
    log = test_log()
    return not log.empty and (log.family_key == family_key).any()


# --------------------------------------------------------------------------- GATE-A over a batch
def gate_a_batch(candidates: list, alpha: float = ALPHA, procedure: str = "by", batch_id: str = "") -> dict:
    """candidates: [{hash, family_key, definition, p}]. Families already in the test log do NOT get a fresh
    independent test -- their prior p carries forward (anti-re-roll). Applies the FDR procedure over the
    batch's effective p-values, logs every candidate (PASS+FAIL), and returns the survivors."""
    batch_id = batch_id or f"batch_{int(time.time())}"
    log = test_log()
    eff, rows = [], []
    for c in candidates:
        fk = c.get("family_key", "")
        if not log.empty and (log.family_key == fk).any():
            prior = float(log[log.family_key == fk].p.min())     # carry the prior p, no fresh test
            p = prior
            note = "carried (family already tested -- anti-re-roll)"
        else:
            p = float(c["p"])
            note = "fresh"
        eff.append(p)
        rows.append(dict(hash=c["hash"], family_key=fk, definition=str(c.get("definition", "")),
                         p=p, batch_id=batch_id, asof=time.strftime("%Y-%m-%dT%H:%M:%S"), verdict="tested"))
    mask = (benjamini_yekutieli if procedure == "by" else benjamini_hochberg)(eff, alpha)
    for i, r in enumerate(rows):
        r["verdict"] = "survived" if mask[i] else "rejected"
    log_tests(rows)
    survivors = [candidates[i] for i in range(len(candidates)) if mask[i]]
    return dict(n=len(candidates), n_survivors=int(mask.sum()), survivors=survivors, procedure=procedure)


# --------------------------------------------------------------------------- planted-null test (B5)
def _null_pvalues(n: int, rows: int, rng) -> np.ndarray:
    """n independent pure-noise features vs a pure-noise target -> n p-values that are U(0,1) under the
    complete null (a real Pearson test, not fabricated)."""
    from scipy import stats
    y = rng.standard_normal(rows)
    out = np.empty(n)
    for i in range(n):
        x = rng.standard_normal(rows)
        out[i] = stats.pearsonr(x, y)[1]
    return out


def planted_null_test(n: int = 200, batches: int = 200, rows: int = 400, alpha: float = ALPHA,
                      procedure: str = "bh", seed: int = 0) -> dict:
    """Under the complete null, BH/BY at alpha must keep FWER = P(>=1 false discovery) <= alpha. Measure it
    empirically across `batches` null batches and assert it holds (the proof FDR controls error)."""
    rng = np.random.default_rng(seed)
    proc = benjamini_hochberg if procedure == "bh" else benjamini_yekutieli
    any_disc, total_disc = 0, 0
    for _ in range(batches):
        p = _null_pvalues(n, rows, rng)
        mask = proc(p, alpha)
        d = int(mask.sum())
        total_disc += d
        any_disc += (d >= 1)
    fwer = any_disc / batches
    mean_disc = total_disc / batches
    # under the complete null BH controls FWER<=alpha; allow a small binomial slack
    tol = alpha + 3 * np.sqrt(alpha * (1 - alpha) / batches)
    ok = fwer <= tol
    return dict(planted_null_ok=bool(ok), procedure=procedure, n_per_batch=n, batches=batches,
                empirical_fwer=round(fwer, 4), alpha=alpha, tol=round(float(tol), 4),
                mean_false_discoveries=round(mean_disc, 4),
                detail=f"{procedure.upper()} alpha={alpha}: empirical FWER {fwer:.3f} <= tol {tol:.3f} "
                       f"({any_disc}/{batches} null batches had >=1 false discovery; mean FD {mean_disc:.3f})")


def main():
    print("=== PLANTED-NULL FDR TEST (B5) ===")
    res_bh = planted_null_test(procedure="bh")
    print("BH:", res_bh["detail"], "->", "PASS" if res_bh["planted_null_ok"] else "FAIL")
    res_by = planted_null_test(procedure="by")
    print("BY:", res_by["detail"], "->", "PASS" if res_by["planted_null_ok"] else "FAIL")
    ok = res_bh["planted_null_ok"] and res_by["planted_null_ok"]
    print(f"\nB5 FDR machinery: {'PASS' if ok else 'FAIL'}")
    if ok:
        from build_done_check import write_marker
        write_marker("B5_fdr", dict(planted_null_ok=True, detail=res_bh["detail"], by=res_by["detail"],
                                    asof="2026-06-08"))
        print("B5 marker written.")
    return ok


if __name__ == "__main__":
    main()
