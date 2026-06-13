"""domains.mlb.signal_catalog — Honest signal-discovery catalog for MLB.

Runs 7 candidate signals through the REAL gate (src.loop.gate.evaluate) via the
proven-leak-free MLBAdapter.feature_bundle seam.

CONTRACT — base columns (frozen; indices match adapter._add_context output):
    base[:,0] = elo_home        base[:,1] = elo_away
    base[:,2] = elo_diff_hfa    base[:,3] = rest_days_home
    base[:,4] = rest_days_away  base[:,5] = h2h_rate
    signal_col = p_home_elo (Elo P(home wins)); target = home win {0,1}

Each candidate derives a NEW signal_col from these columns ONLY — no additional
corpus reads. Leak-freeness is inherited from the adapter (FOURTH_DOMAIN_PROOF §3.1).

HONEST DISCIPLINE: expected verdicts are REJECT/DEFER (efficient market). A SHIP
verdict is flagged as a probable artifact; no edge is claimed.

F5: ZERO imports from domains.nba/domains.basketball_nba/domains.tennis/domains.soccer/
    src.data/src.sim/src.tracking/src.pipeline.
PRIVATE: never committed to the public repo.
"""
from __future__ import annotations

import datetime as _dt
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from src.loop.gate import FeatureBundle, evaluate
from src.loop.signal import AsOfContext, GateResult, Hypothesis, Signal, SignalValue

logger = logging.getLogger(__name__)

# Base column indices (frozen contract — never change without updating adapter)
_IDX_ELO_HOME, _IDX_ELO_AWAY, _IDX_ELO_DIFF_HFA = 0, 1, 2
_IDX_REST_HOME, _IDX_REST_AWAY, _IDX_H2H_RATE = 3, 4, 5


def _derive_bundle(b: FeatureBundle, s: np.ndarray) -> FeatureBundle:
    return FeatureBundle(base=b.base, signal_col=s, target=b.target,
                         dates=b.dates, lines=b.lines, closing=b.closing)


# ---------------------------------------------------------------------------
# Candidate signals (7 total; each derived from base columns 0-5 only)
# ---------------------------------------------------------------------------

class EloMismatchMagnitudeSignal(Signal):
    """Expected gate verdict: REJECT. |elo_diff_hfa| — mismatch magnitude strips directionality;
    non-directional transform already captured by the base matrix; fully priced by sharp books."""
    name: str = "mlb_elo_mismatch_magnitude"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="|elo_diff_hfa| measures absolute team-quality mismatch.",
            rationale="Non-directional transform; redundant with base; priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class H2HResidualSignal(Signal):
    """Expected gate verdict: REJECT. h2h_rate - 0.5 — head-to-head advantage residual vs
    null prior; H2H history is public and fully priced by closing-line markets."""
    name: str = "mlb_h2h_residual"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        h2h = ctx.extra.get("h2h_rate")
        return None if h2h is None else float(float(h2h) - 0.5)

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="h2h_rate - 0.5 measures home H2H advantage above the null prior.",
            rationale="Public H2H history; priced by sharp books. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class RestDiffSignedSignal(Signal):
    """Expected gate verdict: REJECT. rest_days_home - rest_days_away — signed rest differential;
    MLB plays near-daily so the mass of rest diffs is near zero; fully public schedule info."""
    name: str = "mlb_rest_diff_signed"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        rh, ra = ctx.extra.get("rest_days_home"), ctx.extra.get("rest_days_away")
        return None if (rh is None or ra is None) else float(float(rh) - float(ra))

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="Signed rest differential (home - away) predicts home outcome.",
            rationale="MLB near-daily schedule; rest diffs near 0; public; priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class AbsRestDiffSignal(Signal):
    """Expected gate verdict: REJECT. |rest_home - rest_away| — rest-diff magnitude; discards
    direction; even less information than signed; public schedule info already priced."""
    name: str = "mlb_abs_rest_diff"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        rh, ra = ctx.extra.get("rest_days_home"), ctx.extra.get("rest_days_away")
        return None if (rh is None or ra is None) else float(abs(float(rh) - float(ra)))

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="|rest_home - rest_away| measures schedule fatigue magnitude.",
            rationale="Magnitude only; MLB schedule public; priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class EloDiffXH2HInteractionSignal(Signal):
    """Expected gate verdict: REJECT. elo_diff_hfa * h2h_rate — Elo quality × H2H interaction;
    higher-order public combination; both inputs already captured by the base matrix."""
    name: str = "mlb_elo_diff_x_h2h"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="elo_diff_hfa × h2h_rate: quality advantage amplified by matchup history.",
            rationale="Higher-order public interaction; both inputs priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class EloHomeAdvantageSignal(Signal):
    """Expected gate verdict: REJECT. elo_home - elo_away (no HFA) — raw Elo gap without
    the home-field offset; functionally redundant with elo_diff_hfa; fully priced."""
    name: str = "mlb_elo_home_advantage"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="elo_home - elo_away (no HFA) measures raw team quality gap.",
            rationale="Redundant with base elo_diff_hfa; no new information; priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class RestDiffXEloDiffInteractionSignal(Signal):
    """Expected gate verdict: REJECT. (rest_home - rest_away) * 1/(1+|elo_diff_hfa|) — rest
    advantage weighted by matchup closeness; higher-order public interaction; priced."""
    name: str = "mlb_rest_diff_x_elo_closeness"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="(rest_diff) × 1/(1+|elo_diff_hfa|): rest matters more in close matchups.",
            rationale="Higher-order interaction; both public; priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


CATALOG_SIGNALS: Tuple[type, ...] = (
    EloMismatchMagnitudeSignal, H2HResidualSignal, RestDiffSignedSignal,
    AbsRestDiffSignal, EloDiffXH2HInteractionSignal, EloHomeAdvantageSignal,
    RestDiffXEloDiffInteractionSignal,
)


# ---------------------------------------------------------------------------
# Base-column transforms (no raw corpus reads; leak-freeness inherited)
# ---------------------------------------------------------------------------

def _compute_signal_col(signal_cls: type, base: np.ndarray) -> np.ndarray:
    """Derive signal_col from proven base matrix only (columns 0-5)."""
    elo_h = base[:, _IDX_ELO_HOME]; elo_a = base[:, _IDX_ELO_AWAY]
    elo_d = base[:, _IDX_ELO_DIFF_HFA]
    rh = base[:, _IDX_REST_HOME]; ra = base[:, _IDX_REST_AWAY]
    h2h = base[:, _IDX_H2H_RATE]
    name = signal_cls.name  # type: ignore[attr-defined]
    if name == EloMismatchMagnitudeSignal.name:          return np.abs(elo_d)
    if name == H2HResidualSignal.name:                   return h2h - 0.5
    if name == RestDiffSignedSignal.name:                return rh - ra
    if name == AbsRestDiffSignal.name:                   return np.abs(rh - ra)
    if name == EloDiffXH2HInteractionSignal.name:        return elo_d * h2h
    if name == EloHomeAdvantageSignal.name:              return elo_h - elo_a
    if name == RestDiffXEloDiffInteractionSignal.name:   return (rh - ra) / (1.0 + np.abs(elo_d))
    logger.warning("unknown signal '%s', returning zeros", name)
    return np.zeros(base.shape[0], dtype=float)


# ---------------------------------------------------------------------------
# Catalog runner
# ---------------------------------------------------------------------------

def run_catalog(
    adapter: Any,
    seasons: Sequence[int],
    out_path: Optional[Path] = None,
    league_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """Run every CATALOG_SIGNALS candidate through the real gate.

    Mirrors run_v3: bundle = adapter.feature_bundle(hyp, seasons[, league_filter]);
    sig._gate_matrix = derived_bundle; evaluate(sig, device="cpu", n_splits=3).
    Returns {"ok": bool, "verdicts": list[dict]}. Writes markdown to out_path if given.
    SHIP verdicts are flagged loudly — probable artifact, no edge claimed.
    """
    rows: List[Dict[str, Any]] = []
    for signal_cls in CATALOG_SIGNALS:
        name: str = signal_cls.name  # type: ignore[attr-defined]
        sig = signal_cls()
        expected = sig.hypothesis().expected_verdict or "REJECT"
        try:
            kw: Dict[str, Any] = {"seasons": seasons}
            if league_filter is not None:
                kw["league_filter"] = league_filter
            bb = adapter.feature_bundle(sig.hypothesis(), **kw)
        except Exception as exc:
            rows.append({"name": name, "expected": expected, "actual_verdict": "BUNDLE_ERROR",
                         "passed_expected": False, "n": 0, "coverage": 0.0, "reason": str(exc)})
            continue
        n = bb.base.shape[0]
        sc = _compute_signal_col(signal_cls, bb.base)
        coverage = float(np.sum(~np.isnan(sc))) / max(n, 1)
        sig._gate_matrix = _derive_bundle(bb, sc)  # type: ignore[attr-defined]
        try:
            r: GateResult = evaluate(sig, device="cpu", n_splits=3)
        except Exception as exc:
            rows.append({"name": name, "expected": expected, "actual_verdict": "GATE_ERROR",
                         "passed_expected": False, "n": n, "coverage": coverage, "reason": str(exc)})
            continue
        actual = r.verdict.value
        exp_set = {v.strip() for v in expected.split(" or ")}
        passed = actual in exp_set or actual in {"REJECT", "DEFER"}
        if actual == "SHIP":
            logger.warning("CATALOG SHIP FLAG '%s': probable artifact. NO edge claimed.", name)
        rows.append({"name": name, "expected": expected, "actual_verdict": actual,
                     "passed_expected": passed, "n": n, "coverage": round(coverage, 3),
                     "reason": r.reason, "wf_folds": r.wf_folds,
                     "wf_all_improve": r.wf_all_improve, "ablation_delta": r.ablation_delta,
                     "ablation_pass": r.ablation_pass, "null_pass": r.null_pass,
                     "calibration_ok": r.calibration_ok, "clv": r.clv, "p_value": r.p_value})
    ok = all(r["passed_expected"] for r in rows)
    if out_path is not None:
        _write_report(rows, Path(out_path), list(seasons), league_filter)
    return {"ok": ok, "verdicts": rows}


def _write_report(
    rows: List[Dict[str, Any]], out: Path, seasons: List[int],
    league_filter: Optional[str] = None,
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    league_note = f"  League: {league_filter}" if league_filter else ""
    L: List[str] = [
        "# Honest signal catalog — markets are efficient; expected and observed "
        "verdicts are REJECT/DEFER. NO edge claimed.",
        f"\nGenerated: {_dt.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}  "
        f"Seasons: {seasons}   Signals: {len(rows)}{league_note}",
        "\n## Contract\nSignal columns derived from the **proven leak-free adapter bundle** "
        "(base cols: elo_home, elo_away, elo_diff_hfa, rest_days_home, rest_days_away, h2h_rate).  "
        "No raw corpus reads; leak-freeness inherited from `MLBAdapter.feature_bundle`.",
        "\n## Verdict table\n",
        "| Signal | Expected | Actual | Passed | N | Coverage | Reason |",
        "|--------|----------|--------|--------|---|----------|--------|",
    ]
    ships: List[str] = []
    for r in rows:
        L.append(f"| {r['name']} | {r['expected']} | {r['actual_verdict']} "
                 f"| {'YES' if r['passed_expected'] else 'NO'} | {r.get('n','?')} "
                 f"| {r.get('coverage','?')} "
                 f"| {str(r.get('reason',''))[:80].replace('|','/')} |")
        if r["actual_verdict"] == "SHIP":
            ships.append(r["name"])
    L.append("\n## Gate detail\n")
    for r in rows:
        L.append(f"### {r['name']}")
        for k in ("actual_verdict", "expected", "passed_expected", "n", "coverage", "reason",
                  "wf_folds", "wf_all_improve", "ablation_delta", "ablation_pass",
                  "null_pass", "calibration_ok", "clv", "p_value"):
            if k in r:
                L.append(f"- **{k}:** {r[k]}")
        L.append("")
    if ships:
        L += ["\n## !! SHIP FLAGS — probable artifacts — DO NOT claim edge\n"]
        for nm in ships:
            L.append(f"- **{nm}**: SHIP — artifact-hunt required.")
    L.append("\n---\n_PRIVATE research. No edge claimed. REJECT = honest success._")
    out.write_text("\n".join(L), encoding="utf-8")
    logger.info("Catalog report written to %s", out)


__all__ = [
    "EloMismatchMagnitudeSignal", "H2HResidualSignal", "RestDiffSignedSignal",
    "AbsRestDiffSignal", "EloDiffXH2HInteractionSignal", "EloHomeAdvantageSignal",
    "RestDiffXEloDiffInteractionSignal", "CATALOG_SIGNALS", "run_catalog",
]
