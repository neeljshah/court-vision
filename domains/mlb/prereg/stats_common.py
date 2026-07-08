"""domains.mlb.prereg.stats_common -- tiny shared plumbing for the
preregistered coach-mechanism atomic tests (docs/research/coach_composition_
architecture_2026_07_08.md section (d)). NOT a new statistical framework:
statsmodels OLS/Logit for the interaction-term Wald test, and the EXISTING
FWER-tightening curve from scripts.platformkit.combo.fwer_budget (reused,
never reimplemented) for the trial-count-aware bar.

Calibration/measurement only -- edge_claimed is hard-wired False in every
ledger row. ASCII; <=300 LOC. Duplicated verbatim in domains/basketball_nba/prereg/ (a
sport-blind kernel/ helper is overkill for a ~70-line wrapper -- ponytail).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import statsmodels.formula.api as smf

from scripts.platformkit.combo.fwer_budget import DEFAULT_EPS, eps_eff

REPO_ROOT = Path(__file__).resolve().parents[3]
LEDGER_PATH = REPO_ROOT / "data" / "cache" / "intel_claims" / "prereg_hypothesis_ledger.jsonl"

SURVIVES = "SURVIVES_PREREG"
NULL = "NULL"
BLOCKED = "BLOCKED"


def alpha_fwer(k: int, eps: float = DEFAULT_EPS) -> float:
    """The SAME Bonferroni-on-eps curve combo_gate's L6 uses (eps / max(1,K)),
    reused verbatim as the multiplicity bar for this run's K tested hypotheses."""
    return eps_eff(eps, k)


def _interaction_term(params_index, sep: str = ":") -> Optional[str]:
    for name in params_index:
        if sep in name:
            return name
    return None


def fit_interaction(df, formula: str, kind: str = "ols") -> Dict[str, Any]:
    """Fit `formula` (must contain one `a:b` interaction term) via OLS or
    Logit and return the INTERACTION coefficient's effect size + p-value --
    the delta the doc's method calls for. Raises on a malformed formula
    (no interaction term found) rather than silently reporting a main effect."""
    model = smf.logit(formula, data=df) if kind == "logit" else smf.ols(formula, data=df)
    res = model.fit(disp=0) if kind == "logit" else model.fit()
    term = _interaction_term(res.params.index)
    if term is None:
        raise ValueError(f"no interaction term (':') in fitted params: {list(res.params.index)}")
    return {
        "term": term, "effect": float(res.params[term]), "p": float(res.pvalues[term]),
        "n": int(res.nobs),
    }


def fit_single(df, formula: str, kind: str = "logit") -> Dict[str, Any]:
    """Single-predictor variant for a hypothesis that names only ONE factor
    (no second named mechanism to interact with -- honest, not invented)."""
    model = smf.logit(formula, data=df) if kind == "logit" else smf.ols(formula, data=df)
    res = model.fit(disp=0) if kind == "logit" else model.fit()
    term = [n for n in res.params.index if n != "Intercept"][0]
    return {
        "term": term, "effect": float(res.params[term]), "p": float(res.pvalues[term]),
        "n": int(res.nobs),
    }


def verdict(p: float, alpha: float) -> str:
    return SURVIVES if p < alpha else NULL


def blocked_row(name: str, sport: str, atomic_unit: str, reason: str,
                method: str = "") -> Dict[str, Any]:
    return _row(name, sport, atomic_unit, n=0, effect=None, p=None, alpha_fwer=None,
                verdict_str=BLOCKED, note=reason, method=method)


def tested_row(name: str, sport: str, atomic_unit: str, fit: Dict[str, Any], alpha: float,
              method: str = "") -> Dict[str, Any]:
    v = verdict(fit["p"], alpha)
    note = "PROVISIONAL -- needs independent replication before belief" if v == SURVIVES else ""
    return _row(name, sport, atomic_unit, n=fit["n"], effect=fit["effect"], p=fit["p"],
                alpha_fwer=alpha, verdict_str=v, note=note, term=fit["term"], method=method)


# replication verdicts: a PROVISIONAL survivor tested again on an INDEPENDENT corpus
# (different season, same mechanism). Reuses `verdict`/alpha_fwer -- not a new stat.
REPLICATED = "REPLICATED"
FAILED_REPLICATION = "FAILED_REPLICATION"


def replication_row(name: str, sport: str, atomic_unit: str, fit: Dict[str, Any], alpha: float,
                    method: str) -> Dict[str, Any]:
    v = REPLICATED if verdict(fit["p"], alpha) == SURVIVES else FAILED_REPLICATION
    return _row(name, sport, atomic_unit, n=fit["n"], effect=fit["effect"], p=fit["p"],
                alpha_fwer=alpha, verdict_str=v, note="independent-season replication check",
                term=fit["term"], method=method)


def _row(name, sport, atomic_unit, n, effect, p, alpha_fwer, verdict_str, note="", term=None,
        method="") -> Dict[str, Any]:
    return {
        "hypothesis": name, "sport": sport, "atomic_unit": atomic_unit, "n": n,
        "effect": effect, "p": p, "alpha_fwer": alpha_fwer, "verdict": verdict_str,
        "term": term, "note": note, "edge_claimed": False, "method": method,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def append_ledger(rows: list[Dict[str, Any]], path: Path = LEDGER_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


__all__ = ["SURVIVES", "NULL", "BLOCKED", "REPLICATED", "FAILED_REPLICATION",
           "alpha_fwer", "fit_interaction", "fit_single", "verdict", "blocked_row",
           "tested_row", "replication_row", "append_ledger", "LEDGER_PATH"]
