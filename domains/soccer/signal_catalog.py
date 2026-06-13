"""domains.soccer.signal_catalog — Honest signal-discovery catalog for soccer.

Runs 7 candidate signals through the REAL gate (src.loop.gate.evaluate) via
the proven-leak-free SoccerAdapter.feature_bundle seam.

CONTRACT — base columns (frozen; indices match SoccerAdapter.feature_bundle):
    base[:,0]=lam_home  base[:,1]=lam_away  base[:,2]=lam_total
    base[:,3]=rest_days_home               base[:,4]=rest_days_away
    signal_col=p_over25  target=target_over25 ∈ {0.0,1.0}

Each candidate derives a NEW signal_col from base columns ONLY — no additional
corpus reads.  Leak-freeness inherited from the adapter (THIRD_DOMAIN_PROOF §3.1).
HONEST: expected verdicts REJECT/DEFER. SHIP = probable artifact; no edge claimed.
F5: ZERO imports from domains.nba/domains.tennis/src.data/src.sim/src.tracking.
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

_IDX_LAM_HOME, _IDX_LAM_AWAY, _IDX_LAM_TOTAL, _IDX_REST_HOME, _IDX_REST_AWAY = 0, 1, 2, 3, 4


def _derive_bundle(b: FeatureBundle, s: np.ndarray) -> FeatureBundle:
    return FeatureBundle(base=b.base, signal_col=s, target=b.target,
                         dates=b.dates, lines=b.lines, closing=b.closing)


def _hyp(name: str, stmt: str, rat: str, ev: str = "REJECT") -> Hypothesis:
    return Hypothesis(name=name, target="winprob", scope="pregame",
                      statement=stmt, rationale=rat,
                      source="seed", expected_verdict=ev, priority="P2")


# ---------------------------------------------------------------------------
# 7 candidate signals — pure transforms of base columns 0-4
# ---------------------------------------------------------------------------

class AttackingImbalanceSignal(Signal):
    """REJECT expected. |lam_home-lam_away| — non-directional; priced into lines."""
    name: str = "soccer_attacking_imbalance"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        lh, la = ctx.extra.get("lam_home"), ctx.extra.get("lam_away")
        return None if (lh is None or la is None) else float(abs(float(lh) - float(la)))

    def hypothesis(self) -> Hypothesis:
        return _hyp(self.name, "|lam_home-lam_away| measures scoring asymmetry.",
                    "Non-directional attacking disparity; priced into O/U lines.")


class LamTotalDeviationSignal(Signal):
    """REJECT expected. lam_total deviation from bundle mean — volume regime; priced."""
    name: str = "soccer_lam_total_deviation"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        lt = ctx.extra.get("lam_total")
        return None if lt is None else float(lt)

    def hypothesis(self) -> Hypothesis:
        return _hyp(self.name, "lam_total deviation from mean captures volume regime.",
                    "Volume extremes priced into closing totals lines.")


class SignedRestDiffSignal(Signal):
    """REJECT expected. rest_home-rest_away (signed) — public schedule info; priced."""
    name: str = "soccer_signed_rest_diff"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        rh, ra = ctx.extra.get("rest_days_home"), ctx.extra.get("rest_days_away")
        return None if (rh is None or ra is None) else float(float(rh) - float(ra))

    def hypothesis(self) -> Hypothesis:
        return _hyp(self.name, "Signed rest differential (home minus away).",
                    "Public schedule info; priced by sharp books at kickoff.")


class HomeAttackShareSignal(Signal):
    """REJECT expected. lam_home/lam_total — home share of expected goals; redundant with p_over25."""
    name: str = "soccer_home_attack_share"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        lh, lt = ctx.extra.get("lam_home"), ctx.extra.get("lam_total")
        if lh is None or lt is None or float(lt) < 0.1:
            return None
        return float(float(lh) / float(lt))

    def hypothesis(self) -> Hypothesis:
        return _hyp(self.name, "lam_home/lam_total — home attack share of expected totals.",
                    "Linear transform of p_over25 inputs; redundant. REJECT expected.")


class LamTotalRestInteractionSignal(Signal):
    """REJECT expected. lam_total*(rest_home-rest_away) — higher-order public interaction."""
    name: str = "soccer_lam_total_rest_interaction"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        lt = ctx.extra.get("lam_total")
        rh, ra = ctx.extra.get("rest_days_home"), ctx.extra.get("rest_days_away")
        if lt is None or rh is None or ra is None:
            return None
        return float(np.clip(float(lt) * (float(rh) - float(ra)), -30.0, 30.0))

    def hypothesis(self) -> Hypothesis:
        return _hyp(self.name, "lam_total * rest_diff: rest matters more in high-volume matches.",
                    "Higher-order public interaction; both components priced.")


class AbsRestDiffSignal(Signal):
    """REJECT or DEFER expected. |rest_home-rest_away| — magnitude loses direction; sparse."""
    name: str = "soccer_abs_rest_diff"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        rh, ra = ctx.extra.get("rest_days_home"), ctx.extra.get("rest_days_away")
        return None if (rh is None or ra is None) else float(abs(float(rh) - float(ra)))

    def hypothesis(self) -> Hypothesis:
        return _hyp(self.name, "|rest_home-rest_away| magnitude beyond signed diff.",
                    "Loses direction; sparse at extremes.", ev="REJECT or DEFER")


class LowScoringFlagSignal(Signal):
    """REJECT expected. Binary: lam_total<2.0 — sparse; redundant with p_over25."""
    name: str = "soccer_low_scoring_flag"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        lt = ctx.extra.get("lam_total")
        return None if lt is None else float(float(lt) < 2.0)

    def hypothesis(self) -> Hypothesis:
        return _hyp(self.name, "lam_total<2.0 flags low-scoring matches.",
                    "Redundant with p_over25; priced into lines.")


CATALOG_SIGNALS: Tuple[type, ...] = (
    AttackingImbalanceSignal, LamTotalDeviationSignal, SignedRestDiffSignal,
    HomeAttackShareSignal, LamTotalRestInteractionSignal, AbsRestDiffSignal,
    LowScoringFlagSignal,
)


# ---------------------------------------------------------------------------
# Base-column transforms (no raw corpus reads; leak-freeness inherited)
# ---------------------------------------------------------------------------

def _compute_signal_col(signal_cls: type, base: np.ndarray) -> np.ndarray:
    """Derive signal_col from proven base matrix only (columns 0-4)."""
    lh = base[:, _IDX_LAM_HOME]; la = base[:, _IDX_LAM_AWAY]
    lt = base[:, _IDX_LAM_TOTAL]
    rh = base[:, _IDX_REST_HOME]; ra = base[:, _IDX_REST_AWAY]; rd = rh - ra
    name = signal_cls.name  # type: ignore[attr-defined]
    if name == AttackingImbalanceSignal.name:      return np.abs(lh - la)
    if name == LamTotalDeviationSignal.name:
        return lt - float(np.nanmean(lt)) if lt.size > 0 else lt - 2.5
    if name == SignedRestDiffSignal.name:           return rd
    if name == HomeAttackShareSignal.name:
        safe = np.where(lt < 0.1, np.nan, lt)
        return np.where(np.isnan(safe), np.nan, lh / safe)
    if name == LamTotalRestInteractionSignal.name: return np.clip(lt * rd, -30.0, 30.0)
    if name == AbsRestDiffSignal.name:             return np.abs(rd)
    if name == LowScoringFlagSignal.name:          return (lt < 2.0).astype(float)
    logger.warning("unknown signal '%s', returning zeros", name)
    return np.zeros(base.shape[0], dtype=float)


# ---------------------------------------------------------------------------
# Catalog runner
# ---------------------------------------------------------------------------

def run_catalog(
    adapter: Any, seasons: Sequence[int], out_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run every CATALOG_SIGNALS candidate through the real gate.

    Mirrors run_v3: bundle=adapter.feature_bundle(hyp,seasons);
    sig._gate_matrix=derived_bundle; evaluate(sig,device="cpu",n_splits=3).
    Returns {"ok":bool,"verdicts":list[dict]}. Writes markdown to out_path.
    SHIP verdicts flagged loudly — probable artifact; NO edge claimed.
    """
    rows: List[Dict[str, Any]] = []
    for signal_cls in CATALOG_SIGNALS:
        name: str = signal_cls.name  # type: ignore[attr-defined]
        sig = signal_cls()
        expected = sig.hypothesis().expected_verdict or "REJECT"
        try:
            bb = adapter.feature_bundle(sig.hypothesis(), seasons)
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
        _write_report(rows, Path(out_path), list(seasons))
    return {"ok": ok, "verdicts": rows}


def _write_report(rows: List[Dict[str, Any]], out: Path, seasons: List[int]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    L: List[str] = [
        "# Honest signal catalog — markets are efficient; expected and observed "
        "verdicts are REJECT/DEFER. NO edge claimed.",
        f"\nGenerated: {_dt.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}  "
        f"Seasons: {seasons}   Signals: {len(rows)}",
        "\n## Contract\nSignal columns derived from the **proven leak-free adapter bundle** "
        "(base: lam_home, lam_away, lam_total, rest_days_home, rest_days_away).  "
        "No raw corpus reads; leak-freeness inherited from `SoccerAdapter.feature_bundle`.",
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
        for k in ("actual_verdict", "expected", "passed_expected", "n", "coverage",
                  "reason", "wf_folds", "wf_all_improve", "ablation_delta",
                  "ablation_pass", "null_pass", "calibration_ok", "clv", "p_value"):
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
    "AttackingImbalanceSignal", "LamTotalDeviationSignal", "SignedRestDiffSignal",
    "HomeAttackShareSignal", "LamTotalRestInteractionSignal", "AbsRestDiffSignal",
    "LowScoringFlagSignal", "CATALOG_SIGNALS", "run_catalog",
]
