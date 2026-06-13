"""domains.basketball_nba.signal_catalog — Honest signal-discovery catalog for NBA.

Runs 8 candidate signals through the REAL gate (src.loop.gate.evaluate) via the
proven-leak-free NBAAdapter.feature_bundle seam.

CONTRACT — base columns (frozen; indices match adapter.feature_bundle output):
    base[:,0] = elo_home          base[:,1] = elo_away
    base[:,2] = elo_diff_hfa      base[:,3] = rest_days_home
    base[:,4] = rest_days_away    base[:,5] = home_b2b
    base[:,6] = away_b2b          base[:,7] = rolling_win10_home
    signal_col = p_home_elo (Elo P(home wins)); target = home win {0,1}

Each candidate derives a NEW signal_col from these columns ONLY — no additional
corpus reads.  Leak-freeness is inherited from the adapter (schedule-level corpus;
walk-forward Elo; rest/b2b computed in date order before update).

CORPUS SCOPE NOTE (honesty):
    This catalog operates on a schedule-level corpus (win/rest/b2b/Elo only).
    Box-score signals — including the reg-season AST edge documented in MEMORY.md —
    are NOT testable here because the corpus contains no box-score columns.
    AST/box-score signals are a future data extension that requires a separate
    game-box-score corpus joined to this schedule corpus.  Do NOT fabricate an AST
    signal from schedule-level data.

HONEST DISCIPLINE: expected verdicts are REJECT/DEFER (efficient market). A SHIP
verdict is flagged as a probable artifact; no edge is claimed.

F5: ZERO imports from domains.tennis / domains.soccer / domains.mlb /
    src.data / src.sim / src.tracking / src.pipeline.
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

# Base column indices (frozen contract — never change without updating adapter)
_IDX_ELO_HOME, _IDX_ELO_AWAY, _IDX_ELO_DIFF_HFA = 0, 1, 2
_IDX_REST_HOME, _IDX_REST_AWAY = 3, 4
_IDX_HOME_B2B, _IDX_AWAY_B2B = 5, 6
_IDX_WIN10_HOME = 7


def _derive_bundle(b: FeatureBundle, s: np.ndarray) -> FeatureBundle:
    """Re-export for backward compatibility (tests import this name)."""
    return _derive_bundle_impl(b, s)


# ---------------------------------------------------------------------------
# Candidate signals (8 total; each derived from base columns 0-7 only)
# ---------------------------------------------------------------------------

class EloIdentitySignal(Signal):
    """Expected gate verdict: REJECT. elo_diff_hfa identity — the Elo-with-HFA gap
    is exactly p_home_elo under a logistic transform; adding it as signal_col is
    fully redundant with the base matrix and already priced by closing lines."""
    name: str = "nba_elo_diff_hfa_identity"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="elo_diff_hfa identity: the Elo gap with HFA applied.",
            rationale="Redundant with base signal_col=p_home_elo; fully priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class AbsRestDiffSignal(Signal):
    """Expected gate verdict: REJECT. |rest_days_home - rest_days_away| — rest-diff
    magnitude discards direction; public schedule information; short NBA back-to-back
    cycles already priced into closing lines by sharp bettors."""
    name: str = "nba_abs_rest_diff"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        rh, ra = ctx.extra.get("rest_days_home"), ctx.extra.get("rest_days_away")
        return None if (rh is None or ra is None) else float(abs(float(rh) - float(ra)))

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="|rest_home - rest_away| measures schedule-fatigue magnitude.",
            rationale="Public schedule; magnitude only; NBA rest priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class RestDiffSignedSignal(Signal):
    """Expected gate verdict: REJECT. rest_days_home - rest_days_away — signed rest
    differential; NBA plays on compressed schedules with frequent b2b; public info
    fully captured in closing-line movement by sharp books."""
    name: str = "nba_rest_diff_signed"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        rh, ra = ctx.extra.get("rest_days_home"), ctx.extra.get("rest_days_away")
        return None if (rh is None or ra is None) else float(float(rh) - float(ra))

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="Signed rest differential (home - away) predicts home outcome.",
            rationale="NBA schedule public; rest diffs priced by closing line. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class HomeB2BIndicatorSignal(Signal):
    """Expected gate verdict: REJECT. home_b2b indicator (0/1) — binary flag for
    whether the home team is on a back-to-back; public schedule information; NBA
    books heavily adjust lines for b2b games; priced at opening."""
    name: str = "nba_home_b2b_indicator"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        v = ctx.extra.get("home_b2b")
        return None if v is None else float(bool(v))

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="home_b2b=1 flags home team on a back-to-back game.",
            rationale="Public schedule; NBA books open with b2b adjustment. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class AwayB2BIndicatorSignal(Signal):
    """Expected gate verdict: REJECT. away_b2b indicator (0/1) — binary flag for
    whether the away team is on a back-to-back; symmetric to home_b2b; public
    schedule information priced into NBA lines at market open."""
    name: str = "nba_away_b2b_indicator"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        v = ctx.extra.get("away_b2b")
        return None if v is None else float(bool(v))

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="away_b2b=1 flags away team on a back-to-back game.",
            rationale="Public schedule; symmetric to home_b2b; priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class RollingWin10HomeSignal(Signal):
    """Expected gate verdict: REJECT. rolling_win10_home — trailing 10-game win rate
    for the home team; public form signal; NBA books track recent team form and
    public bettors bet heavily on 'hot' teams; momentum fully priced."""
    name: str = "nba_rolling_win10_home"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        v = ctx.extra.get("rolling_win10_home")
        return None if v is None else float(v)

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="rolling_win10_home: home team trailing-10 win rate.",
            rationale="Public form; NBA momentum priced by closing line. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class EloMismatchMagnitudeSignal(Signal):
    """Expected gate verdict: REJECT. |elo_diff_hfa| — absolute Elo gap strips
    directionality; tells you how lopsided the matchup is but not who wins;
    non-directional transform already captured in the base matrix; priced."""
    name: str = "nba_elo_mismatch_magnitude"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="|elo_diff_hfa| measures absolute team-quality mismatch.",
            rationale="Non-directional; redundant with base; priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class RestBucketSignal(Signal):
    """Expected gate verdict: REJECT. min(rest_days_home, 3) bucketed rest for home
    team; caps at 3 since 3+ days rest is equivalent in NBA context; public schedule
    information; rest bucketing is a known sharp adjustment; priced at open."""
    name: str = "nba_rest_bucket_home"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        v = ctx.extra.get("rest_days_home")
        return None if v is None else float(min(float(v), 3.0))

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="min(rest_home, 3): bucketed home rest (3+ days equivalent).",
            rationale="Public schedule bucket; NBA rest-days priced at open. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


CATALOG_SIGNALS: Tuple[type, ...] = (
    EloIdentitySignal, AbsRestDiffSignal, RestDiffSignedSignal,
    HomeB2BIndicatorSignal, AwayB2BIndicatorSignal, RollingWin10HomeSignal,
    EloMismatchMagnitudeSignal, RestBucketSignal,
)


# ---------------------------------------------------------------------------
# Base-column transforms (no raw corpus reads; leak-freeness inherited)
# ---------------------------------------------------------------------------

def _compute_signal_col(signal_cls: type, base: np.ndarray) -> np.ndarray:
    """Derive signal_col from proven base matrix only (columns 0-7)."""
    elo_h = base[:, _IDX_ELO_HOME]; elo_a = base[:, _IDX_ELO_AWAY]
    elo_d = base[:, _IDX_ELO_DIFF_HFA]
    rh = base[:, _IDX_REST_HOME]; ra = base[:, _IDX_REST_AWAY]
    hb2b = base[:, _IDX_HOME_B2B]; ab2b = base[:, _IDX_AWAY_B2B]
    w10 = base[:, _IDX_WIN10_HOME]
    name = signal_cls.name  # type: ignore[attr-defined]
    if name == EloIdentitySignal.name:          return elo_d.copy()
    if name == AbsRestDiffSignal.name:          return np.abs(rh - ra)
    if name == RestDiffSignedSignal.name:       return rh - ra
    if name == HomeB2BIndicatorSignal.name:     return hb2b.astype(float)
    if name == AwayB2BIndicatorSignal.name:     return ab2b.astype(float)
    if name == RollingWin10HomeSignal.name:     return w10.copy()
    if name == EloMismatchMagnitudeSignal.name: return np.abs(elo_d)
    if name == RestBucketSignal.name:           return np.minimum(rh, 3.0)
    logger.warning("unknown signal '%s', returning zeros", name)
    return np.zeros(base.shape[0], dtype=float)


# ---------------------------------------------------------------------------
# Catalog runner — delegates to catalog_common
# ---------------------------------------------------------------------------

_HEADER_LINES = [
    "\n## Contract\nSignal columns derived from the **proven leak-free adapter bundle** "
    "(base cols: elo_home, elo_away, elo_diff_hfa, rest_days_home, rest_days_away, "
    "home_b2b, away_b2b, rolling_win10_home).  "
    "No raw corpus reads; leak-freeness inherited from `NBAAdapter.feature_bundle`.\n\n"
    "**Corpus scope:** schedule-level only.  Box-score signals (incl. the documented "
    "reg-season AST edge) are a future data extension — NOT testable at this layer.",
]


def run_catalog(
    adapter: Any,
    seasons: Sequence[int],
    out_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run every CATALOG_SIGNALS candidate through the real gate.

    Mirrors run_v3: bundle = adapter.feature_bundle(hyp, seasons);
    sig._gate_matrix = derived_bundle; evaluate(sig, device='cpu', n_splits=3).
    Returns {"ok": bool, "verdicts": list[dict]}. Writes markdown to out_path if given.
    SHIP verdicts are flagged loudly — probable artifact, no edge claimed.
    """
    return run_catalog_common(
        signal_classes=CATALOG_SIGNALS,
        adapter=adapter,
        seasons=seasons,
        compute_fn=_compute_signal_col,
        out_path=out_path,
        header_lines=_HEADER_LINES,
        extra_bundle_kwargs={},
        ship_log_prefix="NBA CATALOG",
    )


__all__ = [
    "EloIdentitySignal", "AbsRestDiffSignal", "RestDiffSignedSignal",
    "HomeB2BIndicatorSignal", "AwayB2BIndicatorSignal", "RollingWin10HomeSignal",
    "EloMismatchMagnitudeSignal", "RestBucketSignal",
    "CATALOG_SIGNALS", "run_catalog", "_compute_signal_col", "_derive_bundle",
]
