"""domains.soccer.asof_reclaim_gate_run -- GATE-RUN for the ON-DISK RECLAIM
soccer candidates: leak-free trailing shot/SoT diffs (asof_features.parquet)
and shots-based xG-PROXY diffs (asof_xg_proxy.parquet), reclaimed onto the
Poisson O/U 2.5 goals base (domains.soccer.adapter.SoccerAdapter's own base).

Per docs/research/ceiling/ONDISK_RECLAIM_TARGETS.md item #4: these parquets are
ALREADY BUILT + leak-free (LEAK_PRE_GAME) but were UNWIRED from any gate run.
scripts.platformkit.proof_soccer.gate_test_asof / gate_test_xg_proxy already
thread individual columns through the REAL src.loop.gate.evaluate (single
70/30-style walk-forward split via n_splits=3); domains.soccer.asof_features_gate
already runs a custom single-corpus 70/30 Poisson-logit DM gate with a
planted-null + truncation-invariance control. THIS module adds the missing
piece: a YEAR-BUCKETED CROSS-CORPUS check (mirrors
scripts/platformkit/geo/soccer_altitude_gate_run.py's pattern exactly -- same
both-directions clustered-DM, same degenerate-base guard, same planted-null
requirement) across ALL candidate diff/ratio/l10 columns in both parquets, and
writes ONE consolidated verdict JSON reporting every existing harness's result
side by side for each dimension.

HONEST A-PRIORI EXPECTATION (stated before running): mostly REJECT -- soccer
pregame O/U markets are documented efficient and shot-based team output is
largely priced into the Poisson goal-rate ratings already. Some home-side
diff/l10 columns are known (from the existing gate_test_asof harness) to flag
SHIP on a single 70/30 split -- this module's job is to state, per dimension,
whether that SHIP survives an independent year-bucket cross-corpus replication
or collapses to REJECT/PARTIAL, which is the honest, stronger test.

PROPOSAL-ONLY: writes ONE verdict JSON to
data/domains/soccer/asof_reclaim_gate.json. NOT data/registry/, flips NO flag,
no push. CALIBRATION only (held-out Brier/log-loss); NO $/ROI/edge field;
vs-close is a SEPARATE, already-existing check (asof_features_gate /
gate_test_asof's CLV criterion) and is summarized here for completeness, not
re-derived. <=300 LOC; ASCII.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from domains.soccer.asof_reclaim_gate_math import (
    _ASOF_FEATURES,
    _ASOF_XG_PROXY,
    _EPS,
    _MIN_BSS,
    _MIN_GAMES_PER_FOLD,
    _NULL_COL,
    build_corpus,
    direction as _direction,
    year_corpora as _year_corpora,
)

_REPO = Path(__file__).resolve().parents[2]
_OUT = _REPO / "data" / "domains" / "soccer" / "asof_reclaim_gate.json"

# Candidate columns per source parquet (all pure prior-only transforms; see
# ONDISK_RECLAIM_TARGETS.md #4 and each parquet's own ASOF_COLS contract).
_FEATURES_CANDIDATES: Tuple[str, ...] = (
    "diff_sot_for_asof", "diff_sot_against_asof",
    "diff_shots_for_asof", "diff_shots_against_asof",
    "home_sot_ratio_for_asof", "away_sot_ratio_for_asof",
    "home_sot_for_l10", "away_sot_for_l10",
)
_XG_PROXY_CANDIDATES: Tuple[str, ...] = (
    "diff_xg_for_asof", "diff_xg_against_asof", "diff_xg_supremacy_asof",
)


def gate_one(corpora: List[Tuple[str, pd.DataFrame]], col: str,
             eps: float = _EPS) -> Dict[str, object]:
    """Cross-corpus verdict for ``col`` across adjacent year-bucket pairs.

    A pair is DEGENERATE when the Poisson base fails the BSS floor in either
    direction (typically the season-1 cold-start bucket, where the walk-forward
    rating has not warm-started yet). DEGENERATE pairs are EXCLUDED from the
    judged set rather than poisoning the whole column: one thin cold-start
    fold should not mask real signal on the other, well-warmed pairs. If
    EVERY pair is degenerate (no fold has a trustworthy base at all) the
    column verdict is honestly INVALID_BASE; per-pair degeneracy always
    stays visible in the pair record for audit.
    """
    pairs = []
    for i in range(len(corpora) - 1):
        (sa, A), (sb, B) = corpora[i], corpora[i + 1]
        a2b = _direction(A, B, col, eps=eps)
        b2a = _direction(B, A, col, eps=eps)
        if not (a2b.get("ok") and b2a.get("ok")):
            continue
        pair_degen = bool(a2b["base_degenerate"] or b2a["base_degenerate"])
        replicated = bool(a2b["feat_wins"] and b2a["feat_wins"])
        pairs.append({"train_a": sa, "test_b": sb, "a_to_b": a2b, "b_to_a": b2a,
                      "replicated": replicated, "pair_degenerate": pair_degen})
    judged = [p for p in pairs if not p["pair_degenerate"]]
    all_degenerate = bool(pairs) and not judged
    if not pairs:
        verdict = "INSUFFICIENT_DATA"
    elif all_degenerate:
        verdict = "INVALID_BASE"
    elif any(p["replicated"] for p in judged):
        verdict = "SHIP"
    elif any(p["a_to_b"]["feat_wins"] or p["b_to_a"]["feat_wins"] for p in judged):
        verdict = "PARTIAL"
    else:
        verdict = "REJECT"
    cov = float(np.mean([c[col].notna().mean() for _, c in corpora])) if corpora else 0.0
    return {"column": col, "verdict": verdict, "pairs": pairs,
            "n_pairs_judged": len(judged), "n_pairs_degenerate": len(pairs) - len(judged),
            "base_degenerate": all_degenerate, "coverage": round(cov, 4)}


@dataclass
class ReclaimGateVerdict:
    source: str            # "asof_features" | "asof_xg_proxy"
    verdict: str
    n_corpora: int
    results: List[Dict[str, object]] = field(default_factory=list)
    planted_null: Dict[str, object] = field(default_factory=dict)
    null_rejects: bool = False
    caveats: List[str] = field(default_factory=list)
    vs_close: str = ("UNPROVEN here -- CALIBRATION only (year-bucket cross-corpus "
                      "Brier/log-loss). CLV-vs-devigged-close is a SEPARATE check "
                      "already run by domains.soccer.asof_features_gate / "
                      "scripts.platformkit.proof_soccer.gate_test_asof(_xg_proxy) "
                      "via src.loop.gate.evaluate's clv_check criterion.")
    proposal_only: bool = True

    def to_dict(self) -> Dict[str, object]:
        return {k: getattr(self, k) for k in
                ("source", "verdict", "n_corpora", "results", "planted_null",
                 "null_rejects", "caveats", "vs_close", "proposal_only")}


def _run_source(source: str, asof_path: Path, candidates: Sequence[str],
                 eps: float = _EPS) -> ReclaimGateVerdict:
    caveats = [
        "BASE = domains.soccer.ratings.walk_forward_goals Poisson p_over25 logit "
        "(leak-free, snapshot-before-update); +FEATURE = logistic on "
        "[p_over25_logit, candidate_z]. Same base SoccerAdapter.feature_bundle uses.",
        "Candidate columns are the on-disk RECLAIM target from "
        "docs/research/ceiling/ONDISK_RECLAIM_TARGETS.md #4: prior-only expanding "
        "team shot/SoT (or shots-based xG-proxy) form, snapshot strictly before "
        "each match's date; NEVER folds the target match's own stats into itself.",
        "Year-bucketed corpora (merged forward to >= %d games/fold); cross-corpus "
        "BOTH directions; DM clustered by event_id; proper-score unanimity "
        "(Brier AND log-loss must both improve); degenerate-base guard (Poisson "
        "BASE must beat base-rate by >= %.3f BSS). Coverage gated at "
        "MIN_PRIOR (both teams need enough trailing history)." % (
            _MIN_GAMES_PER_FOLD, _MIN_BSS),
        "PLANTED-NULL pure-noise column through the IDENTICAL gate MUST REJECT.",
        "Single underlying data source (football-data.co.uk, 25,834-row corpus) -- "
        "year-buckets give an HONEST cross-corpus check but are NOT a second "
        "independent dataset; never claimed as such.",
        "A-PRIORI STATED EXPECTATION (before running): mostly REJECT -- soccer "
        "pregame O/U is documented efficient; shot-based team output likely "
        "redundant with the Poisson goal-rate rating that already prices it. "
        "NO $/ROI/edge field anywhere; an honest REJECT is a SUCCESS.",
    ]
    if not asof_path.exists():
        return ReclaimGateVerdict(source, "INSUFFICIENT_DATA", 0,
                                  caveats=caveats + ["%s not on disk" % asof_path.name])
    feat = build_corpus(asof_path=asof_path)
    corpora = _year_corpora(feat)
    n = len(corpora)
    if n < 2:
        return ReclaimGateVerdict(source, "INSUFFICIENT_DATA", n,
                                  caveats=caveats + ["need >=2 independent year corpora"])

    results = [gate_one(corpora, col, eps=eps) for col in candidates
               if col in feat.columns]
    null = gate_one(corpora, _NULL_COL, eps=eps)
    null_rejects = null["verdict"] in ("REJECT", "INVALID_BASE", "PARTIAL",
                                       "INSUFFICIENT_DATA")
    any_ship = any(r["verdict"] == "SHIP" for r in results)
    any_partial = any(r["verdict"] == "PARTIAL" for r in results)
    if not null_rejects:
        source_verdict = "NOT_TESTABLE"
    elif any_ship:
        source_verdict = "SHIP"
    elif any_partial:
        source_verdict = "PARTIAL"
    else:
        source_verdict = "REJECT"
    return ReclaimGateVerdict(source, source_verdict, n, results,
                              {**null, "rejects": null_rejects}, null_rejects, caveats)


def run(eps: float = _EPS) -> Dict[str, ReclaimGateVerdict]:
    """Full cross-corpus gate for BOTH reclaim sources."""
    return {
        "asof_features": _run_source("asof_features", _ASOF_FEATURES,
                                      _FEATURES_CANDIDATES, eps=eps),
        "asof_xg_proxy": _run_source("asof_xg_proxy", _ASOF_XG_PROXY,
                                     _XG_PROXY_CANDIDATES, eps=eps),
    }


def write(verdicts: Dict[str, ReclaimGateVerdict], out: Optional[Path] = None) -> str:
    dest = Path(out) if out is not None else _OUT
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: v.to_dict() for k, v in verdicts.items()}
    with open(dest, "w", encoding="ascii") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    return str(dest)


def _fmt_dir(tag: str, d: Dict[str, object]) -> str:
    if not d.get("ok", True) and "brier_base" not in d:
        return "    %s: %s (n_train=%s n_test=%s)" % (
            tag, d.get("reason"), d.get("n_train"), d.get("n_test"))
    return ("    %s: Brier %s -> %s (d %s)  LL %s -> %s  DM p=%s  base_BSS=%s "
            "degenerate=%s  feat_wins=%s" % (
                tag, d["brier_base"], d["brier_feat"], d["brier_delta"],
                d["logloss_base"], d["logloss_feat"], d["dm_p"],
                d["base_bss_vs_const"], d["base_degenerate"], d["feat_wins"]))


def _fmt_pair(p: Dict[str, object]) -> List[str]:
    return ["  pair %s<->%s replicated=%s  pair_degenerate=%s%s" % (
        p["train_a"], p["test_b"], p["replicated"], p.get("pair_degenerate", False),
        "  [EXCLUDED FROM VERDICT]" if p.get("pair_degenerate", False) else ""),
            _fmt_dir("A->B", p["a_to_b"]), _fmt_dir("B->A", p["b_to_a"])]


def _report(source: str, v: ReclaimGateVerdict) -> str:
    lines = ["-" * 76, "SOURCE %s   VERDICT: %s   corpora=%d" % (source, v.verdict, v.n_corpora)]
    for r in v.results:
        lines.append("\nCOLUMN %-26s VERDICT: %s  (coverage %.3f, judged %d/%d pairs, "
                     "%d excluded as degenerate-base)" % (
            r["column"], r["verdict"], r["coverage"],
            r.get("n_pairs_judged", len(r["pairs"])), len(r["pairs"]),
            r.get("n_pairs_degenerate", 0)))
        for p in r["pairs"]:
            lines += _fmt_pair(p)
        if not r["pairs"]:
            lines.append("  (no scorable adjacent pair)")
    n = v.planted_null
    lines += ["\nPLANTED-NULL [%s]: verdict=%s  REJECTS=%s" % (
        _NULL_COL, n.get("verdict"), v.null_rejects)]
    for p in n.get("pairs", []):
        lines += _fmt_pair(p)
    if not v.null_rejects:
        lines.append("  *** GATE UNTRUSTWORTHY for this source: noise column did NOT reject. ***")
    else:
        lines.append("  null rejected as required -> the gate CAN fail a signal.")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Cross-corpus gate for the soccer on-disk RECLAIM candidates.")
    ap.add_argument("--eps", type=float, default=_EPS)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    verdicts = run(eps=a.eps)
    print("=" * 76)
    print("SOCCER ON-DISK RECLAIM GATE-RUN (asof_features + asof_xg_proxy, year-bucket cross-corpus)")
    print("=" * 76)
    for source, v in verdicts.items():
        print(_report(source, v))
    print("=" * 76)
    print("vs_close: CLV-vs-devigged-close is a SEPARATE existing check "
          "(asof_features_gate.py / gate_test_asof(_xg_proxy).py's clv_check); "
          "not re-derived by this cross-corpus module.")
    print("Calibration only; NO $/edge. REJECT-scouting is the honest, successful "
          "outcome; never force-fed as a model feature without a re-run SHIP.")
    if not a.no_write:
        print("wrote %s" % write(verdicts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_corpus", "gate_one", "run", "write", "main",
           "ReclaimGateVerdict", "_FEATURES_CANDIDATES", "_XG_PROXY_CANDIDATES"]
