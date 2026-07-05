# -*- coding: utf-8 -*-
"""scripts.platformkit.geo.soccer_altitude_gate_run -- GATE-RUN for the
soccer_intl pregame ALTITUDE layer (host-venue altitude_m, e.g. high-Andes
venues like La Paz/Quito) vs a Poisson-goals win-prob BASE.

MIRRORS scripts/platformkit/nba_travel_gate_run.py EXACTLY (same clustered-DM
both-directions gate, same proper-score unanimity, same planted-null control,
same degenerate-base guard, same >=100 games/fold floor) -- this is the ONE
non-trivial travel-adjacent mechanism worth a gate arm this wave (per the
program instruction: mlb/tennis gate arms skipped as expected-duplicate
REJECTs, not worth the compute).

BASE: domains.soccer_intl.ratings.walk_forward_goals gives leak-free PRE-match
Poisson lambdas (lam_home, lam_away) fit walk-forward, snapshot-before-update.
We derive P(home win) from those lambdas via the closed-form Skellam
distribution over goal difference (scipy.stats.skellam) -- a probability
read-off from an EXISTING leak-free rating, not new estimation. This is the
walk-forward-Elo-logit analog the NBA gate used for the basketball market.

+FEATURE: logistic on [skellam_logit, altitude_m_at_host_city] (host venue's
altitude in meters, from the SAME travel_scouting descriptor this module
also builds). Rows with no resolved venue_altitude_m are DROPPED, never
0-filled (an unresolved altitude is NOT the same as sea level).

HONEST A-PRIORI EXPECTATION (stated before running): REJECT -- soccer_intl
pregame markets are independently documented efficient (JOB_EVIDENCE_PACKET);
the NBA precedent already showed Elo+schedule subsumes travel/altitude-style
schedule quantities. Whatever the result, report it plainly.

PROPOSAL-ONLY: writes ONE verdict JSON to
data/frontend/funnel/soccer_altitude_gate.json -- NOT data/registry/, flips
NO flag, NO push. CALIBRATION only (held-out Brier/log-loss); NO $/ROI/edge
field; vs-close is UNPROVEN and never a feature. <=300 LOC; ASCII.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.geo.soccer_altitude_gate_math import (
    _EPS,
    _MIN_BSS,
    _MIN_GAMES_PER_FOLD,
    _NULL_COL,
    _RESULTS,
    build_corpus,
    direction as _direction,
    p_home_skellam,
    year_corpora as _year_corpora,
)

_REPO = Path(__file__).resolve().parents[3]
_OUT = _REPO / "data" / "frontend" / "funnel" / "soccer_altitude_gate.json"


def gate_one(corpora: List[Tuple[str, pd.DataFrame]], col: str,
             eps: float = _EPS) -> Dict[str, object]:
    pairs = []
    degen = False
    for i in range(len(corpora) - 1):
        (sa, A), (sb, B) = corpora[i], corpora[i + 1]
        a2b = _direction(A, B, col, eps=eps)
        b2a = _direction(B, A, col, eps=eps)
        if not (a2b.get("ok") and b2a.get("ok")):
            continue
        degen = degen or a2b["base_degenerate"] or b2a["base_degenerate"]
        replicated = bool(a2b["feat_wins"] and b2a["feat_wins"])
        pairs.append({"train_a": sa, "test_b": sb, "a_to_b": a2b, "b_to_a": b2a,
                      "replicated": replicated})
    if not pairs:
        verdict = "INSUFFICIENT_DATA"
    elif degen:
        verdict = "INVALID_BASE"
    elif any(p["replicated"] for p in pairs):
        verdict = "SHIP"
    elif any(p["a_to_b"]["feat_wins"] or p["b_to_a"]["feat_wins"] for p in pairs):
        verdict = "PARTIAL"
    else:
        verdict = "REJECT"
    cov = float(np.mean([c[col].notna().mean() for _, c in corpora])) if corpora else 0.0
    return {"column": col, "verdict": verdict, "pairs": pairs,
            "base_degenerate": degen, "coverage": round(cov, 4)}


@dataclass
class SoccerAltitudeGateVerdict:
    layer: str
    verdict: str
    n_corpora: int
    results: List[Dict[str, object]] = field(default_factory=list)
    planted_null: Dict[str, object] = field(default_factory=dict)
    null_rejects: bool = False
    caveats: List[str] = field(default_factory=list)
    vs_close: str = "UNPROVEN -- CALIBRATION only (held-out Brier/log-loss), NOT a market edge"
    proposal_only: bool = True

    def to_dict(self) -> Dict[str, object]:
        return {k: getattr(self, k) for k in
                ("layer", "verdict", "n_corpora", "results", "planted_null",
                 "null_rejects", "caveats", "vs_close", "proposal_only")}


def run(eps: float = _EPS) -> SoccerAltitudeGateVerdict:
    caveats = [
        "BASE = P(home win) via closed-form Skellam(lam_home,lam_away) read off "
        "domains.soccer_intl.ratings.walk_forward_goals (leak-free, snapshot-before-"
        "update Poisson rating). +FEATURE = logistic on [skellam_logit, altitude_m].",
        "altitude_m is the host-city elevation (static_v1 geo table); rows with an "
        "unresolved city are DROPPED, never 0-filled (a miss != sea level).",
        "Year-bucketed corpora (merged forward to >= %d games/fold); cross-corpus "
        "BOTH directions; DM clustered by (date,home,away); proper-score unanimity; "
        "degenerate-base guard (Skellam BASE must beat base-rate by >= %.3f BSS)."
        % (_MIN_GAMES_PER_FOLD, _MIN_BSS),
        "PLANTED-NULL pure-noise column through the IDENTICAL gate MUST REJECT.",
        "A-PRIORI STATED EXPECTATION (before running): REJECT -- soccer_intl pregame "
        "is documented efficient; NBA precedent showed schedule quantities are "
        "subsumed by the rating. NO $/ROI/edge field; vs-close UNPROVEN, never a feature.",
    ]
    if not _RESULTS.exists():
        return SoccerAltitudeGateVerdict("soccer_intl_altitude", "INSUFFICIENT_DATA", 0,
                                         caveats=caveats + ["results.parquet not on disk"])
    feat = build_corpus()
    corpora = _year_corpora(feat)
    n = len(corpora)
    if n < 2:
        return SoccerAltitudeGateVerdict("soccer_intl_altitude", "INSUFFICIENT_DATA", n,
                                         caveats=caveats + ["need >=2 independent year corpora"])

    results = [gate_one(corpora, "altitude_m", eps=eps)]
    null = gate_one(corpora, _NULL_COL, eps=eps)
    null_rejects = null["verdict"] in ("REJECT", "INVALID_BASE", "PARTIAL", "INSUFFICIENT_DATA")
    any_ship = any(r["verdict"] == "SHIP" for r in results)
    if not null_rejects:
        layer_verdict = "NOT_TESTABLE"
    elif any_ship:
        layer_verdict = "SHIP"
    else:
        layer_verdict = "REJECT"
    return SoccerAltitudeGateVerdict("soccer_intl_altitude", layer_verdict, n, results,
                                     {**null, "rejects": null_rejects}, null_rejects, caveats)


def write(v: SoccerAltitudeGateVerdict, out: Optional[Path] = None) -> str:
    dest = Path(out) if out is not None else _OUT
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="ascii") as f:
        json.dump(v.to_dict(), f, indent=2, sort_keys=True)
    return str(dest)


def _fmt_dir(tag: str, d: Dict[str, object]) -> str:
    return ("    %s: Brier %s -> %s (d %s)  LL %s -> %s  DM p=%s  base_BSS=%s "
            "degenerate=%s  feat_wins=%s" % (
                tag, d["brier_base"], d["brier_feat"], d["brier_delta"],
                d["logloss_base"], d["logloss_feat"], d["dm_p"],
                d["base_bss_vs_const"], d["base_degenerate"], d["feat_wins"]))


def _fmt_pair(p: Dict[str, object]) -> List[str]:
    return ["  pair %s<->%s replicated=%s" % (p["train_a"], p["test_b"], p["replicated"]),
            _fmt_dir("A->B", p["a_to_b"]), _fmt_dir("B->A", p["b_to_a"])]


def _report(v: SoccerAltitudeGateVerdict) -> str:
    lines = ["=" * 76,
             "SOCCER_INTL ALTITUDE LAYER GATE-RUN (pregame altitude vs Skellam win-prob base)",
             "=" * 76,
             "LAYER     : %s   VERDICT: %s" % (v.layer, v.verdict),
             "corpora   : %d independent year-bucket corpora" % v.n_corpora, "-" * 76]
    for r in v.results:
        lines.append("\nCOLUMN %-18s VERDICT: %s  (coverage %.3f)" % (
            r["column"], r["verdict"], r["coverage"]))
        for p in r["pairs"]:
            lines += _fmt_pair(p)
        if not r["pairs"]:
            lines.append("  (no scorable adjacent pair)")
    n = v.planted_null
    lines += ["\n" + "-" * 76,
              "PLANTED-NULL [%s]: verdict=%s  REJECTS=%s" % (
                  _NULL_COL, n.get("verdict"), v.null_rejects)]
    for p in n.get("pairs", []):
        lines += _fmt_pair(p)
    if not v.null_rejects:
        lines.append("  *** GATE UNTRUSTWORTHY: noise column did NOT reject. ***")
    else:
        lines.append("  null rejected as required -> the gate CAN fail a signal.")
    lines += ["-" * 76, "vs_close  : %s" % v.vs_close,
              "Calibration only; NO $/edge. REJECT-scouting is the honest, successful "
              "outcome; kept as SCOUTING, NEVER force-fed as a model feature.",
              "=" * 76]
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Gate the soccer_intl pregame altitude layer.")
    ap.add_argument("--eps", type=float, default=_EPS)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    v = run(eps=a.eps)
    print(_report(v))
    if not a.no_write:
        print("wrote %s" % write(v))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_corpus", "gate_one", "run", "write", "main",
           "_NULL_COL", "SoccerAltitudeGateVerdict"]
