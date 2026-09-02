"""Cost tiers for the signal foundry: what a cheap screen may cost, what a verdict may claim.

Frozen prereg: docs/evidence/harness/FACTORY_TIERS_SPEC_2026-09-03.md, pinned by content
(`git hash-object`) into every TierResult and every charged ledger row as prereg_sha256.
T0/T1 are screens: charge_tier raises TierNotChargeable for them and a T1 verdict is the
non-finding "SCREEN". T2/T3 are charged, read a corpus partition DISJOINT from the rows the
screen selected on (SF-1), and since S59 decide on BOTH bars: a charged AHEAD needs the global
deflated p AND its frozen family's BH/BY bar. A family absent from the frozen FWER partition
is verdict NOT_IN_FROZEN_FAMILIES and is never charged. Calibration language only.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.combo.corpus_cache import SPORTS, load_gate_corpus
from scripts.platformkit.combo.fwer_budget import min_corpora_eff
from scripts.platformkit.eval_gate import scoring
from scripts.platformkit.eval_gate.backtest_runner import _charge_ledger
from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.family_bars import (charged_bars,  # noqa: F401 re-export
                                                       families_spec_sha, frozen_family,
                                                       git_blob_id)
from scripts.platformkit.eval_gate.pbo import cscv_pbo
from scripts.platformkit.eval_gate.walkforward import assert_vintage, walk_forward
from scripts.platformkit.foundry.grammar import Hypothesis, semantic_hash
# Re-exported so `tiers.PromotionRule` / `tiers.promote` keep resolving for every importer.
from scripts.platformkit.foundry.promotion import SPEC_PATH, PromotionRule, promote  # noqa: F401
from scripts.platformkit.ingame.gap_effective_n import design_effect, intraclass_correlation

TIERS = ("T0", "T1", "T2", "T3")
SCREEN_TIERS = ("T0", "T1")
CHARGED_TIERS = ("T2", "T3")
CLUSTER_KEYS = {"nba": "team", "mlb": "team", "soccer": "div", "tennis": "player"}
_CLUSTER_FIELDS = {"team": ("away", "home"), "div": ("div",), "player": ("p1_id", "home")}
_COVERAGE_FLOOR, _VINTAGE_SAMPLE = 0.8, 100
_EMPTY = dict(dm=None, raw_p=None, k_family=None, k_global=None, deflated_p=None, pbo=None)
# Nothing was scored: no metric, no bar, no charge. Used only by NOT_IN_FROZEN_FAMILIES.
_UNSCORED = dict(_EMPTY, brier_model=None, brier_close=None, n_eff=0.0)


class TierNotChargeable(RuntimeError):
    """A T0/T1 screen tried to reach the FWER ledger."""


class ScreenPartitionLeak(RuntimeError):
    """Rows handed to a tier are not on that tier's side of the screen/verdict partition."""


@dataclass(frozen=True)
class Partition:
    """One family's frozen screen/verdict split (SF-1); the two sides are disjoint."""
    basis: str
    seed: int
    screen_ids: frozenset
    verdict_ids: frozenset
    screen_sha256: str
    verdict_sha256: str

    def side(self, tier: str) -> frozenset:
        return self.screen_ids if tier in SCREEN_TIERS else self.verdict_ids


@dataclass(frozen=True)
class TierResult:
    """One tier call. Fields after artifact_path are the red-team prerequisites (SF-1/2/4/10)."""
    hash: str
    tier: str
    family: str
    corpus: str
    corpus_unit: str
    n: int
    n_eff: float
    brier_model: Optional[float]
    brier_close: Optional[float]
    dm: Optional[float]
    raw_p: Optional[float]
    k_family: Optional[int]
    k_global: Optional[int]
    deflated_p: Optional[float]
    pbo: Optional[float]
    verdict: str
    artifact_path: str
    screen_partition_sha256: str
    verdict_partition_sha256: str
    cluster_key: str
    screened_n: Optional[int]
    prereg_sha256: str
    spec_version: str
    hypothesis: Optional[Hypothesis] = None
    # S59 -- the second bar. AHEAD iff bh_passed AND global_passed; the frozen family
    # partition is pinned here beside prereg_sha256 so a stale partition is self-evident.
    family_q: Optional[float] = None
    bh_passed: Optional[bool] = None
    global_passed: Optional[bool] = None
    dual_verdict: str = ""
    families_spec_sha256: str = ""


def _event_id(state: dict) -> str:
    return str(state.get("event_id", state["game_id"]))


def _block(state: dict, basis: str) -> str:
    if basis == "corpus_unit":
        return str(state["corpus_unit"])
    stamp = datetime.fromisoformat(state["state_ts"]).isocalendar()
    return "%04d-W%02d" % (stamp[0], stamp[1])


def _sha(ids: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(sorted(ids)).encode("ascii")).hexdigest()


def partition_corpus(states: Sequence[dict], *, seed: int) -> Partition:
    """Split a corpus into disjoint SCREEN and VERDICT sides by corpus_unit or ISO-week block."""
    units = {str(s["corpus_unit"]) for s in states if s.get("corpus_unit") is not None}
    basis = "corpus_unit" if len(units) >= 2 else "iso_week"
    blocks = sorted({_block(s, basis) for s in states})
    assign = {block: (index + seed) % 2 for index, block in enumerate(blocks)}
    screen = frozenset(_event_id(s) for s in states if assign[_block(s, basis)] == 0)
    verdict = frozenset(_event_id(s) for s in states if assign[_block(s, basis)] == 1)
    if not screen or not verdict:
        raise ValueError("partition left a side empty over %d %s blocks" % (len(blocks), basis))
    if screen & verdict:
        raise ValueError("an event_id landed on both partition sides")
    return Partition(basis, seed, screen, verdict, _sha(screen), _sha(verdict))


def charge_tier(tier: str, *, ledger_path: Any, family: str, hypothesis_hash: str,
                prereg_sha256: str, sport: str, start: str, end: str) -> dict:
    """THE REFUSAL: the only path from this module to the FWER ledger. T0/T1 may never take it."""
    if tier not in CHARGED_TIERS:
        raise TierNotChargeable("tier %r is a cheap screen and may never consume K; only %s are "
                                "charged" % (tier, list(CHARGED_TIERS)))
    return _charge_ledger(Path(ledger_path), "foundry:%s" % hypothesis_hash[:16], sport, start, end,
                          family=family, hypothesis_hash=hypothesis_hash, tier=tier,
                          prereg_sha256=prereg_sha256)


def _cluster_ids(states: Sequence[dict], sport: str) -> tuple:
    """SF-10: event_id clustering is a no-op on pregame corpora; use the sport's declared key."""
    key = CLUSTER_KEYS.get(sport)
    if key is None:
        raise ValueError("no declared cluster key for sport %r (SF-10)" % sport)
    ids = []
    for state in states:
        value = next((state[f] for f in _CLUSTER_FIELDS[key] if state.get(f) is not None), None)
        if value is None:
            raise ValueError("state %s carries no %s cluster field" % (_event_id(state), key))
        ids.append(str(value))
    return key, ids


def _n_eff(losses: Sequence[float], cluster_ids: Sequence[str]) -> float:
    frame = pd.DataFrame({"cluster": list(cluster_ids), "loss": list(losses)})
    icc = intraclass_correlation(frame, game_column="cluster", loss_column="loss")
    mbar = max(1.0, len(frame) / max(1, frame["cluster"].nunique()))
    return float(len(frame) / design_effect(icc, mbar))


def _pooled_oof(records: Sequence[dict]) -> tuple:
    """Pool CPCV per-path predictions into one OOF series per event, in chronological order."""
    by_event: dict = {}
    for record in records:
        entry = by_event.setdefault(record["game_id"], {"ts": record["ts"], "p": [],
                                                        "close": record["p_close"], "y": record["y"]})
        entry["p"].append(record["p_model"])
    ordered = sorted(by_event.items(), key=lambda item: (item[1]["ts"], item[0]))
    return ([event for event, _ in ordered],
            np.array([float(np.mean(entry["p"])) for _, entry in ordered]),
            np.array([float(entry["close"]) for _, entry in ordered]),
            np.array([int(entry["y"]) for _, entry in ordered]))


def run_tier(hypothesis: Hypothesis, tier: str, *, states: Sequence[dict], predict_fn: Callable,
             ledger_path: Any, partition: Partition, rule: PromotionRule, family: str = "",
             screened_n: Optional[int] = None, n_corpora: int = 1,
             artifact_path: str = "", results_db: Any = None) -> TierResult:
    """Run one tier on rows that must already sit on that tier's side of the partition.

    `partition`/`predict_fn` are forced by the spec's field list (both partition sha256s are
    TierResult fields, SF-1; no Brier exists without a predictor). `results_db` is optional and
    read-only: it supplies the family's already-recorded raw p-values for the S59 family bar,
    and without it a charged trial is priced as a family of one.
    """
    if tier not in TIERS:
        raise ValueError("unknown tier %r" % tier)
    if not states:
        raise ValueError("tier %s got no rows" % tier)
    leaked = {_event_id(s) for s in states} - partition.side(tier)
    if leaked:
        raise ScreenPartitionLeak("%s got %d row(s) off its partition side (e.g. %s); a verdict "
                                  "scored on rows the screen selected on is a self-REJECT"
                                  % (tier, len(leaked), sorted(leaked)[0]))
    digest, sport = semantic_hash(hypothesis), hypothesis.sport
    units = sorted({str(s["corpus_unit"]) for s in states if s.get("corpus_unit") is not None})
    common = dict(hash=digest, tier=tier, family=family, corpus=sport, n=len(states),
                  corpus_unit=units[0] if len(units) == 1 else "", artifact_path=artifact_path,
                  screen_partition_sha256=partition.screen_sha256,
                  verdict_partition_sha256=partition.verdict_sha256,
                  cluster_key=CLUSTER_KEYS.get(sport, ""), screened_n=screened_n,
                  prereg_sha256=rule.prereg_sha256, spec_version=rule.spec_version,
                  hypothesis=hypothesis)
    if tier == "T0":
        if sport in SPORTS:
            load_gate_corpus(sport)                            # raises StaleCorpusError
        step = max(1, len(states) // _VINTAGE_SAMPLE)
        for state in list(states)[::step][:_VINTAGE_SAMPLE]:   # EVEN sample, never a head slice
            assert_vintage(state)
        filled = sum(1 for s in states
                     if s.get("features") and all(v is not None for v in s["features"].values()))
        return TierResult(n_eff=float(filled), brier_model=None, brier_close=None,
                          verdict="COVERED" if filled >= _COVERAGE_FLOOR * len(states)
                          else "UNCOVERED", **_EMPTY, **common)
    if tier == "T1":
        records = walk_forward(list(states), predict_fn).records
        y = [r["y"] for r in records]
        return TierResult(n_eff=float(len(states)), verdict="SCREEN", **_EMPTY, **common,
                          brier_model=scoring.brier([r["p_model"] for r in records], y),
                          brier_close=scoring.brier([r["p_close"] for r in records], y))
    return _run_charged(tier, states, predict_fn, sport, ledger_path, family, screened_n,
                        n_corpora, rule, digest, common, results_db)


def _run_charged(tier: str, states: Sequence[dict], predict_fn: Callable, sport: str,
                 ledger_path: Any, family: str, screened_n: Optional[int], n_corpora: int,
                 rule: PromotionRule, digest: str, common: dict,
                 results_db: Any = None) -> TierResult:
    if screened_n is None:
        raise ValueError("%s must print screened_n beside deflated_p (SF-2)" % tier)
    if frozen_family(family) is None:
        # No frozen family, no family bar, so no AHEAD is reachable -- and the refusal comes
        # BEFORE charge_tier, so an unfrozen family never consumes K silently.
        return TierResult(verdict="NOT_IN_FROZEN_FAMILIES",
                          families_spec_sha256=families_spec_sha(), **_UNSCORED, **common)
    stamps = sorted(str(s["state_ts"])[:10] for s in states)
    # Q2: the ledger row is appended BEFORE any metric, and K is read AT LAUNCH.
    charge = charge_tier(tier, ledger_path=ledger_path, family=family, hypothesis_hash=digest,
                         prereg_sha256=rule.prereg_sha256, sport=sport, start=stamps[0],
                         end=stamps[-1])
    k_global, k_family = int(charge["k_cumulative"]), charge.get("k_family")
    ids, model, close, y = _pooled_oof(cpcv_evaluate(list(states), predict_fn))
    by_id = {_event_id(s): s for s in states}
    key, cluster_ids = _cluster_ids([by_id[i] for i in ids], sport)
    losses = (model - y) ** 2 - (close - y) ** 2
    dm = diebold_mariano(losses.tolist(), cluster_ids)
    pbo = cscv_pbo(np.column_stack([model, close]), y, s_blocks=16).pbo
    brier_model, brier_close = scoring.brier(model, y), scoring.brier(close, y)
    prior = [] if results_db is None else list(results_db.family_p_values(family))
    bars = charged_bars(dm.p_value, k_global, family, prior, rule.alpha,
                        common["artifact_path"])
    if not bars["global_pass"]:
        verdict = "MATCH"
    elif brier_model > brier_close:
        verdict = "BEHIND"
    elif tier == "T3" and n_corpora < min_corpora_eff(n_corpora, k_global):
        verdict = "SINGLE-WINDOW"
    elif not bars["family_pass"]:
        verdict = "MATCH"                       # AHEAD needs BOTH bars; the family bar blocked
    else:
        verdict = "AHEAD"
    return TierResult(n_eff=_n_eff(losses.tolist(), cluster_ids), brier_model=brier_model,
                      brier_close=brier_close, dm=dm.dm_stat, raw_p=dm.p_value, k_family=k_family,
                      k_global=k_global, deflated_p=bars["deflated_p"], pbo=pbo, verdict=verdict,
                      family_q=bars["q"], bh_passed=bars["family_pass"],
                      global_passed=bars["global_pass"], dual_verdict=bars["verdict"],
                      families_spec_sha256=bars["families_spec_sha"],
                      **{**common, "cluster_key": key, "n": len(ids)})


