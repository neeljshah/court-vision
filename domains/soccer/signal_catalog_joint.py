"""domains.soccer.signal_catalog_joint — JOINT/interaction soccer signal candidates.

8 candidates combining ≥2 base columns. Mirrors _derive_bundle + run pattern
from signal_catalog.py. No new data reads; leak-freeness inherited from adapter.

CONTRACT — base columns (frozen; same as SoccerAdapter.feature_bundle):
    base[:,0]=lam_home  base[:,1]=lam_away  base[:,2]=lam_total
    base[:,3]=rest_days_home               base[:,4]=rest_days_away

HONEST: expected verdicts REJECT/DEFER. SHIP = probable artifact; no tuning;
no edge claimed. F5: no domains.nba/tennis/basketball_nba/src.data/sim/tracking.
PRIVATE: never committed to the public repo.
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple
import numpy as np
from src.loop.gate import FeatureBundle, evaluate  # noqa: F401 — AST-scanned by tests
from src.loop.signal import AsOfContext, Hypothesis, Signal, SignalValue
from scripts.platformkit.catalog_common import (
    derive_bundle as _derive_bundle_impl,
    run_catalog_common,
    write_catalog_report as _write_report_impl,
)

logger = logging.getLogger(__name__)
_IDX_LAM_HOME, _IDX_LAM_AWAY, _IDX_LAM_TOTAL, _IDX_REST_HOME, _IDX_REST_AWAY = 0, 1, 2, 3, 4


def _derive_bundle(b: FeatureBundle, s: np.ndarray) -> FeatureBundle:
    """Re-export for backward compatibility (tests import this name)."""
    return _derive_bundle_impl(b, s)


def _hyp(name: str, stmt: str, rat: str) -> Hypothesis:
    return Hypothesis(name=name, target="winprob", scope="pregame",
                      statement=stmt, rationale=rat,
                      source="seed", expected_verdict="REJECT", priority="P2")


# ---------------------------------------------------------------------------
# 8 JOINT candidates — each combines ≥2 base columns
# ---------------------------------------------------------------------------

class LamDiffRestDiffProductSignal(Signal):
    """(lam_home-lam_away)*(rest_home-rest_away) — attack advantage modulated by rest."""
    name: str = "soccer_lam_diff_x_rest_diff"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
    def build(self, ctx: AsOfContext) -> SignalValue:
        lh=ctx.extra.get("lam_home"); la=ctx.extra.get("lam_away")
        rh=ctx.extra.get("rest_days_home"); ra=ctx.extra.get("rest_days_away")
        if any(v is None for v in (lh,la,rh,ra)): return None
        return float(np.clip((float(lh)-float(la))*(float(rh)-float(ra)),-50.,50.))
    def hypothesis(self) -> Hypothesis:
        return _hyp(self.name,"(lam_home-lam_away)*(rest_home-rest_away).",
                    "Both components public; product adds no private info.")


class LamTotalAbsRestDiffSignal(Signal):
    """lam_total*|rest_diff| — high-scoring matches where rest gap is larger."""
    name: str = "soccer_lam_total_x_abs_rest_diff"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
    def build(self, ctx: AsOfContext) -> SignalValue:
        lt=ctx.extra.get("lam_total"); rh=ctx.extra.get("rest_days_home"); ra=ctx.extra.get("rest_days_away")
        if any(v is None for v in (lt,rh,ra)): return None
        return float(np.clip(float(lt)*abs(float(rh)-float(ra)),0.,60.))
    def hypothesis(self) -> Hypothesis:
        return _hyp(self.name,"lam_total*|rest_diff|: rest matters more in high-volume matches.",
                    "Higher-order public interaction; volume and schedule both priced.")


class LamRatioSignal(Signal):
    """lam_home/lam_away — ratio of expected goals; directional home-strength proxy."""
    name: str = "soccer_lam_ratio"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
    def build(self, ctx: AsOfContext) -> SignalValue:
        lh=ctx.extra.get("lam_home"); la=ctx.extra.get("lam_away")
        if lh is None or la is None or float(la)<0.05: return None
        return float(np.clip(float(lh)/float(la),0.1,10.))
    def hypothesis(self) -> Hypothesis:
        return _hyp(self.name,"lam_home/lam_away: ratio of predicted goals.",
                    "Monotone transform of existing signals; market-priced.")


class HighVolumeAttackImbalanceSignal(Signal):
    """(lam_total>2.5)*|lam_home-lam_away| — imbalance in high-scoring matches only."""
    name: str = "soccer_high_vol_attack_imbalance"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
    def build(self, ctx: AsOfContext) -> SignalValue:
        lh=ctx.extra.get("lam_home"); la=ctx.extra.get("lam_away"); lt=ctx.extra.get("lam_total")
        if any(v is None for v in (lh,la,lt)): return None
        return float(float(lt)>2.5)*abs(float(lh)-float(la))
    def hypothesis(self) -> Hypothesis:
        return _hyp(self.name,"(lam_total>2.5)*|lam_home-lam_away|: threshold*imbalance.",
                    "Both components priced into totals and spreads.")


class HomeAttackShareRestDiffSignal(Signal):
    """(lam_home/lam_total)*(rest_home-rest_away) — home attack share weighted by rest."""
    name: str = "soccer_home_share_x_rest_diff"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
    def build(self, ctx: AsOfContext) -> SignalValue:
        lh=ctx.extra.get("lam_home"); lt=ctx.extra.get("lam_total")
        rh=ctx.extra.get("rest_days_home"); ra=ctx.extra.get("rest_days_away")
        if any(v is None for v in (lh,lt,rh,ra)) or float(lt)<0.1: return None
        return float(np.clip((float(lh)/float(lt))*(float(rh)-float(ra)),-15.,15.))
    def hypothesis(self) -> Hypothesis:
        return _hyp(self.name,"(lam_home/lam_total)*(rest_diff): home share scaled by rest.",
                    "Composite of 3 public base cols; no private signal.")


class LamDiffSquaredSignal(Signal):
    """(lam_home-lam_away)^2 — non-linear strength gap; captures extreme mismatches."""
    name: str = "soccer_lam_diff_squared"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
    def build(self, ctx: AsOfContext) -> SignalValue:
        lh=ctx.extra.get("lam_home"); la=ctx.extra.get("lam_away")
        if lh is None or la is None: return None
        d=float(lh)-float(la); return float(min(d*d,25.))
    def hypothesis(self) -> Hypothesis:
        return _hyp(self.name,"(lam_home-lam_away)^2: squared goal diff.",
                    "Squared transform of market-priced spread.")


class SignedLamDiffRestDiffSignal(Signal):
    """sign(lam_diff)*rest_diff — goal-direction aligned with rest advantage."""
    name: str = "soccer_signed_lam_diff_x_rest_diff"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
    def build(self, ctx: AsOfContext) -> SignalValue:
        lh=ctx.extra.get("lam_home"); la=ctx.extra.get("lam_away")
        rh=ctx.extra.get("rest_days_home"); ra=ctx.extra.get("rest_days_away")
        if any(v is None for v in (lh,la,rh,ra)): return None
        return float(np.clip(float(np.sign(float(lh)-float(la)))*(float(rh)-float(ra)),-15.,15.))
    def hypothesis(self) -> Hypothesis:
        return _hyp(self.name,"sign(lam_diff)*(rest_diff): rest aligned with goal edge.",
                    "Public interaction of schedule and predicted margins.")


class LamWeightedRestDiffSignal(Signal):
    """(lam_total/2.5)*rest_diff — rest_diff weighted by relative scoring volume."""
    name: str = "soccer_rest_diff_lam_weighted"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
    def build(self, ctx: AsOfContext) -> SignalValue:
        lt=ctx.extra.get("lam_total"); rh=ctx.extra.get("rest_days_home"); ra=ctx.extra.get("rest_days_away")
        if any(v is None for v in (lt,rh,ra)) or float(lt)<0.1: return None
        return float(np.clip((float(lt)/2.5)*(float(rh)-float(ra)),-20.,20.))
    def hypothesis(self) -> Hypothesis:
        return _hyp(self.name,"(lam_total/2.5)*(rest_diff): rest scaled by volume.",
                    "Rescaled lam_total*rest_diff; both components priced.")


CATALOG_JOINT_SIGNALS: Tuple[type, ...] = (
    LamDiffRestDiffProductSignal, LamTotalAbsRestDiffSignal, LamRatioSignal,
    HighVolumeAttackImbalanceSignal, HomeAttackShareRestDiffSignal,
    LamDiffSquaredSignal, SignedLamDiffRestDiffSignal, LamWeightedRestDiffSignal,
)


# ---------------------------------------------------------------------------
# Base-column vector transforms (no raw corpus reads)
# ---------------------------------------------------------------------------

def _compute_joint_signal_col(signal_cls: type, base: np.ndarray) -> np.ndarray:
    """Derive signal_col from proven base matrix only (columns 0-4)."""
    lh=base[:,_IDX_LAM_HOME]; la=base[:,_IDX_LAM_AWAY]; lt=base[:,_IDX_LAM_TOTAL]
    rh=base[:,_IDX_REST_HOME]; ra=base[:,_IDX_REST_AWAY]; rd=rh-ra
    name=signal_cls.name  # type: ignore[attr-defined]
    if name==LamDiffRestDiffProductSignal.name:
        return np.clip((lh-la)*rd,-50.,50.)
    if name==LamTotalAbsRestDiffSignal.name:
        return np.clip(lt*np.abs(rd),0.,60.)
    if name==LamRatioSignal.name:
        safe=np.where(la<0.05,np.nan,la)
        return np.where(np.isnan(safe),np.nan,np.clip(lh/safe,0.1,10.))
    if name==HighVolumeAttackImbalanceSignal.name:
        return (lt>2.5).astype(float)*np.abs(lh-la)
    if name==HomeAttackShareRestDiffSignal.name:
        safe_lt=np.where(lt<0.1,np.nan,lt)
        share=np.where(np.isnan(safe_lt),np.nan,lh/safe_lt)
        return np.where(np.isnan(share),np.nan,np.clip(share*rd,-15.,15.))
    if name==LamDiffSquaredSignal.name:
        return np.minimum((lh-la)**2,25.)
    if name==SignedLamDiffRestDiffSignal.name:
        return np.clip(np.sign(lh-la)*rd,-15.,15.)
    if name==LamWeightedRestDiffSignal.name:
        safe_lt=np.where(lt<0.1,np.nan,lt)
        return np.where(np.isnan(safe_lt),np.nan,np.clip((safe_lt/2.5)*rd,-20.,20.))
    logger.warning("unknown joint signal '%s', returning zeros",name)
    return np.zeros(base.shape[0],dtype=float)


# ---------------------------------------------------------------------------
# Catalog runner — delegates to catalog_common
# ---------------------------------------------------------------------------

_JOINT_HEADER_LINES = [
    "\n## Contract",
    "Signal columns are **JOINT transforms** (≥2 base columns) from the proven "
    "leak-free adapter bundle: lam_home, lam_away, lam_total, rest_days_home, rest_days_away. "
    "No raw corpus reads; leak-freeness inherited from SoccerAdapter.feature_bundle.",
]

_JOINT_TITLE = (
    "# Honest JOINT signal catalog — soccer O/U-2.5. "
    "Markets are efficient; expected verdicts REJECT/DEFER. NO edge claimed."
)


def run_joint_catalog(
    adapter: Any, seasons: Sequence[int], out_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run CATALOG_JOINT_SIGNALS through the real gate. Returns {"ok":bool,"verdicts":list}.
    SHIP = probable artifact; NO edge claimed.
    """
    return run_catalog_common(
        signal_classes=CATALOG_JOINT_SIGNALS,
        adapter=adapter,
        seasons=seasons,
        compute_fn=_compute_joint_signal_col,
        out_path=out_path,
        header_lines=_JOINT_HEADER_LINES,
        title=_JOINT_TITLE,
        ship_log_prefix="JOINT CATALOG",
    )


__all__ = [
    "LamDiffRestDiffProductSignal","LamTotalAbsRestDiffSignal","LamRatioSignal",
    "HighVolumeAttackImbalanceSignal","HomeAttackShareRestDiffSignal",
    "LamDiffSquaredSignal","SignedLamDiffRestDiffSignal","LamWeightedRestDiffSignal",
    "CATALOG_JOINT_SIGNALS","_compute_joint_signal_col","_derive_bundle",
    "run_joint_catalog",
]
