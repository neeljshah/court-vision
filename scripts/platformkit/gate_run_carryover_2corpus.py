"""scripts.platformkit.gate_run_carryover_2corpus -- 2-season-disjoint-corpus
gate for the C4 cross-game CARRYOVER interaction candidates (nba_carryover_
self_cross, mlb_carryover_self_cross), run through the REAL interaction_factory
fit (runner._fit_candidate: cluster-robust Wald p on the fa:fb interaction term,
Elo-controlled) -- NOT a reimplemented gate.

WHY A SEPARATE SCRIPT (not runner.run_batch twice): each template's registered
feature_builder reads ONE hardcoded default corpus (NBA: all seasons pooled in
one parquet; MLB: a single default year). This script re-fits the SAME
declared candidate on TWO season-disjoint slices directly via runner.
_fit_candidate -- the exact "same fit function, different corpus" pattern
interaction_factory.replicate_survivors already uses, never a reimplementation.

VERDICT (per sport, both directions, a FLAT Bonferroni bar over the declared
K=1 -- this is its own fixed, pre-declared family, not batch-1's sequential
tightening):
  SURVIVES_BOTH_CORPORA -- same sign, p<alpha in BOTH corpora (true replication).
  SURVIVES_ONE_CORPUS   -- p<alpha in exactly one (single-fold lift = artifact,
                           NOT a ship -- recorded honestly).
  NULL_BOTH             -- neither corpus's p clears the bar (the EXPECTED,
                           honest result -- b2b/rest is already heavily priced).
  NOT_TESTABLE          -- either corpus unbuildable (source parquet missing).

Appends ledger rows (one per corpus) to the SAME interaction_factory_ledger.jsonl
every other factory run writes -- skips a (candidate_id, corpus) pair already on
record (idempotent re-run). No $/ROI/edge anywhere; NULL_BOTH is a SUCCESS.

CLI: python -m scripts.platformkit.gate_run_carryover_2corpus
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from scripts.platformkit.combo.fwer_budget import DEFAULT_EPS, eps_eff
from scripts.platformkit.interaction_factory import builders_carryover as BC
from scripts.platformkit.interaction_factory import generator as GEN
from scripts.platformkit.interaction_factory import runner as IFR
from scripts.platformkit.clv_ledger_io import ledger_lock
from scripts.platformkit.io_atomic import append_jsonl_atomic

K_DECLARED = 1
ALPHA = eps_eff(DEFAULT_EPS, K_DECLARED)

NBA_TEMPLATE = "nba_carryover_self_cross"
MLB_TEMPLATE = "mlb_carryover_self_cross"
NBA_ATTRS = ["heavy_min_load_asof", "rest_days_asof"]
MLB_ATTRS = ["sp_prior_pitch_count_asof", "sp_rest_days_asof"]
NBA_SEASONS = ("2023-24", "2024-25")   # season-disjoint corpora A/B (carryover_asof.parquet's own season strings)
MLB_YEARS = ("2023", "2024")           # season-disjoint corpora A/B (separate savant_full__<year> files)


def _candidate(template_id: str) -> GEN.Candidate:
    cands = GEN.enumerate_candidates(template_id)
    assert len(cands) == 1, "carryover self-cross templates declare exactly 1 pair"
    return cands[0]


def nba_corpus_build(season: str) -> Optional[Dict[str, Any]]:
    """NBA carryover frame filtered to one season slice of the single pooled parquet."""
    if not BC._NBA_CARRYOVER_SOURCE.exists():
        return None
    asof = pd.read_parquet(BC._NBA_CARRYOVER_SOURCE)
    asof = asof[asof["season"] == season]
    if asof.empty:
        return None
    frame = IFR.build_nba_boxdetail_frame(NBA_ATTRS, asof)
    return {"frame": frame, "cluster": "game_id", "corpus": "carryover_asof[%s]" % season,
            "kind": "logit", "covariate": "p_base"}


def mlb_corpus_build(year: str) -> Optional[Dict[str, Any]]:
    """MLB carryover frame from that season-year's own carryover_asof__<year>.parquet."""
    source = BC.mlb_carryover_source_for_year(year)
    if not source.exists():
        return None
    asof = pd.read_parquet(source)
    if asof.empty:
        return None
    frame = BC.build_mlb_carryover_frame(MLB_ATTRS, asof)
    return {"frame": frame, "cluster": "event_id", "corpus": "carryover_asof[%s]" % year,
            "kind": "logit", "covariate": "p_base"}


def _fit_or_none(build: Optional[Dict[str, Any]], cand: GEN.Candidate) -> Optional[Dict[str, Any]]:
    if build is None:
        return None
    try:
        return IFR._fit_candidate(build, cand)  # noqa: SLF001 -- the SAME real fit every template uses
    except Exception:  # noqa: BLE001 -- one corpus's fit failure isolates, never crashes the gate
        return None


def combined_verdict(fit_a: Optional[Dict[str, Any]], fit_b: Optional[Dict[str, Any]]) -> str:
    if fit_a is None or fit_b is None:
        return "NOT_TESTABLE"
    a_survives = fit_a["p"] < ALPHA
    b_survives = fit_b["p"] < ALPHA
    same_sign = (fit_a["effect"] > 0) == (fit_b["effect"] > 0)
    if a_survives and b_survives and same_sign:
        return "SURVIVES_BOTH_CORPORA"
    if a_survives or b_survives:
        return "SURVIVES_ONE_CORPUS"
    return "NULL_BOTH"


def _per_corpus_verdict(fit: Optional[Dict[str, Any]]) -> str:
    if fit is None:
        return IFR.NOT_TESTABLE
    return IFR.SURVIVES if fit["p"] < ALPHA else IFR.NULL


def _ledger_row(cand: GEN.Candidate, corpus_tag: str, fit: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "candidate_id": cand.candidate_id, "template_id": cand.template_id, "sport": cand.sport,
        "atomic_unit": cand.atomic_unit, "outcome": cand.outcome,
        "attr_a": cand.attr_a, "attr_b": cand.attr_b, "term": fit["term"] if fit else None,
        "k_declared": K_DECLARED, "cum_K": K_DECLARED, "verdict": _per_corpus_verdict(fit),
        "effect": round(fit["effect"], 6) if fit else None, "p": round(fit["p"], 6) if fit else None,
        "n": int(fit["n"]) if fit else 0, "alpha_fwer": round(ALPHA, 8), "corpus": corpus_tag,
        "note": "2-season-disjoint-corpus carryover gate (C4 lane, depth-frontier item 4)",
        "edge_claimed": False, "computed_at": IFR._now(),  # noqa: SLF001
        "hypothesis_source": cand.hypothesis_source,
    }


def _already_recorded(ledger_rows, candidate_id: str, corpus_tag: str) -> bool:
    return any(r.get("candidate_id") == candidate_id and r.get("corpus") == corpus_tag for r in ledger_rows)


def gate_sport(template_id: str, corpus_a_tag: str, build_a: Optional[Dict[str, Any]],
               corpus_b_tag: str, build_b: Optional[Dict[str, Any]],
               *, ledger_path: Path = IFR.LEDGER_PATH) -> Dict[str, Any]:
    """Fit the ONE declared candidate on both corpora, append (or skip if
    already on record) one ledger row per corpus, return the combined verdict."""
    cand = _candidate(template_id)
    fit_a = _fit_or_none(build_a, cand)
    fit_b = _fit_or_none(build_b, cand)
    verdict = combined_verdict(fit_a, fit_b)

    existing = IFR._load_ledger(ledger_path)  # noqa: SLF001 -- same loader batch-1/replication use
    for tag, fit in ((corpus_a_tag, fit_a), (corpus_b_tag, fit_b)):
        if not _already_recorded(existing, cand.candidate_id, tag):
            with ledger_lock(ledger_path):  # judge NIT a1eff899: unlocked sibling = lost-update clobber
                append_jsonl_atomic(ledger_path, _ledger_row(cand, tag, fit))

    return {"template_id": template_id, "verdict": verdict, "alpha": ALPHA,
            "corpus_a": {"tag": corpus_a_tag, "fit": fit_a},
            "corpus_b": {"tag": corpus_b_tag, "fit": fit_b}}


def run(*, ledger_path: Path = IFR.LEDGER_PATH) -> Dict[str, Any]:
    nba = gate_sport(NBA_TEMPLATE, NBA_SEASONS[0], nba_corpus_build(NBA_SEASONS[0]),
                      NBA_SEASONS[1], nba_corpus_build(NBA_SEASONS[1]), ledger_path=ledger_path)
    mlb = gate_sport(MLB_TEMPLATE, MLB_YEARS[0], mlb_corpus_build(MLB_YEARS[0]),
                      MLB_YEARS[1], mlb_corpus_build(MLB_YEARS[1]), ledger_path=ledger_path)
    return {"nba": nba, "mlb": mlb}


def _fmt_fit(tag: str, fit: Optional[Dict[str, Any]]) -> str:
    if fit is None:
        return "  %s: unbuildable" % tag
    return "  %s: n=%d effect=%.6f p=%.4g" % (tag, fit["n"], fit["effect"], fit["p"])


def main() -> int:
    res = run()
    print("=" * 72)
    print("CROSS-GAME CARRYOVER -- 2-season-disjoint-corpus interaction_factory gate (C4)")
    print("=" * 72)
    for sport, r in res.items():
        print("\n%s  template=%s  VERDICT=%s (alpha=%.4g)" % (
            sport.upper(), r["template_id"], r["verdict"], r["alpha"]))
        print(_fmt_fit(r["corpus_a"]["tag"], r["corpus_a"]["fit"]))
        print(_fmt_fit(r["corpus_b"]["tag"], r["corpus_b"]["fit"]))
    print("\n(NULL_BOTH = honest success; b2b/rest is already heavily priced. No edge ever claimed.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run", "gate_sport", "combined_verdict", "nba_corpus_build", "mlb_corpus_build",
           "K_DECLARED", "ALPHA", "main"]
