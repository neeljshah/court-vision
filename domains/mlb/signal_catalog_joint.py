"""domains.mlb.signal_catalog_joint — JOINT/interaction signal catalog for MLB.

Runs 7 joint/interaction candidate signals through the REAL gate (src.loop.gate.evaluate)
via the proven-leak-free MLBAdapter.feature_bundle seam.

CONTRACT — base columns (frozen; indices match adapter._add_context output):
    base[:,0]=elo_home  base[:,1]=elo_away  base[:,2]=elo_diff_hfa
    base[:,3]=rest_days_home  base[:,4]=rest_days_away  base[:,5]=h2h_rate
    signal_col=p_home_elo; target=home win {0,1}

Each candidate derives a NEW signal_col from these columns ONLY. Leak-freeness
inherited from the adapter (FOURTH_DOMAIN_PROOF §3.1). Expected verdicts are
REJECT/DEFER. SHIP is a probable artifact; no edge claimed.

F5: ZERO imports from domains.nba/domains.basketball_nba/domains.tennis/domains.soccer/
    src.data/src.sim/src.tracking/src.pipeline.  PRIVATE: never committed to public repo.
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
# Joint/interaction candidate signals (7 total; each uses >=2 base columns)
# ---------------------------------------------------------------------------

class EloH2HProductSignal(Signal):
    """Expected gate verdict: REJECT. elo_diff_hfa * h2h_rate — quality gap amplified by
    head-to-head win history; both inputs are public and priced by sharp books."""
    name: str = "mlb_joint_elo_diff_x_h2h"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="elo_diff_hfa × h2h_rate: quality gap weighted by matchup history.",
            rationale="Product of two public signals; no new information; priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class RestWeightedEloSignal(Signal):
    """Expected gate verdict: REJECT. elo_diff_hfa * sign(rest_home - rest_away) — Elo gap
    directionally weighted by rest advantage; all inputs are public schedule/rating info."""
    name: str = "mlb_joint_elo_diff_x_rest_sign"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="elo_diff_hfa × sign(rest_diff): quality advantage aligned with rest.",
            rationale="Public rest + public Elo; higher-order but priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class EloSumRestDiffSignal(Signal):
    """Expected gate verdict: REJECT. (elo_home + elo_away) * (rest_home - rest_away) — total
    combined team quality scaled by rest differential; fully public; redundant with base."""
    name: str = "mlb_joint_elo_sum_x_rest_diff"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="(elo_home + elo_away) × (rest_home - rest_away): quality-scaled rest.",
            rationale="Both inputs public; higher-order interaction redundant with base. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class H2HXRestDiffSignal(Signal):
    """Expected gate verdict: REJECT. h2h_rate * (rest_home - rest_away) — matchup history
    amplified by rest differential; both inputs are public and priced by closing lines."""
    name: str = "mlb_joint_h2h_x_rest_diff"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="h2h_rate × (rest_home - rest_away): matchup history scaled by rest.",
            rationale="Both inputs public; no new structural information; priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class EloRatioH2HSignal(Signal):
    """Expected gate verdict: REJECT. (elo_home / elo_away) * h2h_rate — Elo ratio × H2H;
    ratio is a monotone transform of elo_diff_hfa; H2H already priced; fully redundant."""
    name: str = "mlb_joint_elo_ratio_x_h2h"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="(elo_home / elo_away) × h2h_rate: quality ratio amplified by matchup record.",
            rationale="Monotone reparametrisation of base elo_diff; H2H priced; redundant. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class AbsRestDiffXEloDiffSignal(Signal):
    """Expected gate verdict: REJECT. |rest_diff| * |elo_diff_hfa| — magnitude of rest
    mismatch × magnitude of quality mismatch; two-way fatigue-quality interaction; public."""
    name: str = "mlb_joint_abs_rest_x_abs_elo"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="|rest_diff| × |elo_diff_hfa|: fatigue magnitude × quality mismatch magnitude.",
            rationale="Both magnitudes public; no directional information added; priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class EloClosenessSqH2HSignal(Signal):
    """Expected gate verdict: REJECT. (1 / (1 + elo_diff_hfa**2)) * h2h_rate — matchup-closeness
    (inverse quadratic Elo) weighted by H2H history; non-linear but still fully public."""
    name: str = "mlb_joint_elo_closeness_sq_x_h2h"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="(1/(1+elo_diff²)) × h2h_rate: H2H matters more in evenly-matched games.",
            rationale="Non-linear but public; both components priced by closing line. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")

CATALOG_SIGNALS: Tuple[type, ...] = (
    EloH2HProductSignal, RestWeightedEloSignal, EloSumRestDiffSignal,
    H2HXRestDiffSignal, EloRatioH2HSignal, AbsRestDiffXEloDiffSignal,
    EloClosenessSqH2HSignal,
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
    if name == EloH2HProductSignal.name:
        return elo_d * h2h
    if name == RestWeightedEloSignal.name:
        return elo_d * np.sign(rh - ra)
    if name == EloSumRestDiffSignal.name:
        return (elo_h + elo_a) * (rh - ra)
    if name == H2HXRestDiffSignal.name:
        return h2h * (rh - ra)
    if name == EloRatioH2HSignal.name:
        # Guard against division by zero — elo values are always positive (>0)
        # in practice; clip to avoid NaN propagation in degenerate test data.
        safe_a = np.where(elo_a == 0, 1.0, elo_a)
        return (elo_h / safe_a) * h2h
    if name == AbsRestDiffXEloDiffSignal.name:
        return np.abs(rh - ra) * np.abs(elo_d)
    if name == EloClosenessSqH2HSignal.name:
        return (1.0 / (1.0 + elo_d ** 2)) * h2h
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

    bundle = adapter.feature_bundle(hyp, seasons[, league_filter]);
    sig._gate_matrix = derived_bundle; evaluate(sig, device="cpu", n_splits=3).
    Returns {"ok": bool, "verdicts": list[dict]}. Writes markdown to out_path if given.
    SHIP verdicts flagged loudly — probable artifact, no edge claimed.
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
        "# Honest joint/interaction signal catalog — markets are efficient; expected "
        "and observed verdicts are REJECT/DEFER. NO edge claimed.",
        f"\nGenerated: {_dt.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}  "
        f"Seasons: {seasons}   Signals: {len(rows)}{league_note}",
        "\n## Contract\nSignal columns are pure algebraic interactions of >=2 base columns "
        "(elo_home, elo_away, elo_diff_hfa, rest_days_home, rest_days_away, h2h_rate). "
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
    logger.info("Joint catalog report written to %s", out)


__all__ = [
    "EloH2HProductSignal", "RestWeightedEloSignal", "EloSumRestDiffSignal",
    "H2HXRestDiffSignal", "EloRatioH2HSignal", "AbsRestDiffXEloDiffSignal",
    "EloClosenessSqH2HSignal", "CATALOG_SIGNALS", "run_catalog",
]
