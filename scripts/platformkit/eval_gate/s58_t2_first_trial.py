"""S58 T2 #1 -- the factory's FIRST end-to-end charged T2 (a pipeline proof, not a fishing trip).

Prereg docs/evidence/harness/S58_T2_FIRST_PREREG_2026-09-03.md, sealed and committed ALONE
before any verdict-side metric; its SHA-256 is PREREG_SHA256 below and is checked before the
charge (Q1). The charge is the factory path only: tiers.run_tier("T2") -> charge_tier ->
_charge_ledger, appended before any metric, K read off the row (Q2). The verdict of record
is the TierResult verdict (dual bar, S59) made stricter by the prereg's four AHEAD conditions.
Calibration language only: MATCH / BEHIND are successes.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Sequence

import numpy as np

from scripts.platformkit.eval_gate import scoring
from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.replication_gate import replication_fields
from scripts.platformkit.foundry import results_db, screen_predictor, tiers
from scripts.platformkit.foundry.grammar import Hypothesis, semantic_hash
from scripts.platformkit.foundry.screen_predictor import RealScreenPredictor

ROOT = Path(__file__).resolve().parents[3]
PREREG_PATH = ROOT / "docs/evidence/harness/S58_T2_FIRST_PREREG_2026-09-03.md"
PREREG_SHA256 = "7125552f4c772e15c05057a5beaf460b1dc152496007cd20ea14c521f893cc30"
HYPOTHESIS = Hypothesis(sport="soccer", feature="diff_shots_for_asof", transform="ew",
                        params=(("halflife", 10),), conditioning=frozenset(), horizon="pregame",
                        market="total", family="soccer_gate")
EXPECTED_HASH = "d65df2a95aeb0f49265445cbaf8be51284f37454538f55fc338412e16ec71936"
FAMILY, SCREENED_N, BAR = "soccer_gate", 82, 0.004
EXPECTED = dict(states=16322, screen=7656, verdict=8666,
                screen_sha="5c8d63970b08ce971b4c92a476d978596e68e082d888ffc7491ad712e6323873",
                verdict_sha="3ea2e582304ea727f0f922f5b43bb8c799fd55299f28ec2b9e908204abc4e72b")
LEDGER = ROOT / "data/cache/eval_gate/backtest_fwer.jsonl"
SCREENS_DB = ROOT / "data/cache/eval_gate/s58_screens/soccer.sqlite"
OUT = ROOT / "data/cache/eval_gate/s58_t2_first_soccer_gate_2026-09-03"
CSV_FIELDS = ("event_id", "ts", "div", "home", "away", "p_model", "p_close", "y",
              "loss_model", "loss_close", "d")


class PerPathPredictor:
    """Compatibility adapter retaining the original trial archive shape for historic reruns."""

    def __init__(self, feature: str) -> None:
        self.feature, self._key, self._inner, self.paths = feature, None, None, []

    def __call__(self, train: Sequence[dict], test: dict, select_inside: bool) -> float:
        key = (id(train), len(train), train[0]["game_id"] if train else "",
               train[-1]["game_id"] if train else "")
        if key != self._key:
            self._key, self._inner = key, RealScreenPredictor(self.feature)
            self.paths.append(self._inner.fits)
        return self._inner(train, test, select_inside)

    def archive(self) -> dict:
        return {"predictor": "real_logistic_v1 (fresh per CPCV path)", "feature": self.feature,
                "n_paths": len(self.paths), "fits": [p[0] if p else None for p in self.paths]}


def seal_check(path: Path = PREREG_PATH, expected: str = PREREG_SHA256) -> str:
    """SHA-256 of the prereg with newlines normalised to LF (autocrlf-proof); raises on drift."""
    got = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    if got != expected:
        raise RuntimeError("prereg seal mismatch: %s != %s" % (got, expected))
    return got


def build() -> tuple:
    """Verdict-side states with the feature bound; STEP 0 counts and both shas asserted."""
    states, table, incumbent = screen_predictor.corpus_states("soccer")
    rule = tiers.PromotionRule.from_spec(tiers.SPEC_PATH)
    part = tiers.partition_corpus(states, seed=rule.partition_seed)
    verdict = [s for s in states if s["game_id"] in part.verdict_ids]
    got = dict(states=len(states), screen=len(part.screen_ids), verdict=len(verdict),
               screen_sha=part.screen_sha256, verdict_sha=part.verdict_sha256)
    if got != EXPECTED or part.screen_ids & part.verdict_ids:
        raise RuntimeError("STEP 0 drift, nothing charged: %s" % got)
    served, inner = screen_predictor.ScreenBinder("soccer", verdict, table, len(verdict), incumbent)(HYPOTHESIS)
    return served, rule, part, inner.feature


def _ledger_state(path: Path) -> tuple:
    data = path.read_bytes() if path.exists() else b""
    return data.count(b"\n"), hashlib.md5(data).hexdigest()


def _unit(model, close, y, clusters) -> dict:
    d = (close - y) ** 2 - (model - y) ** 2             # d > 0 = model better
    dm = diebold_mariano((-d).tolist(), clusters)       # tiers' orientation: model - close
    bm, bc = scoring.brier(model, y), scoring.brier(close, y)
    return dict(n=int(len(y)), brier_model=bm, brier_close=bc, improvement=bc - bm,
                ci_lo=-dm.ci95[1], ci_hi=-dm.ci95[0], raw_p=dm.p_value, dm_stat=dm.dm_stat,
                n_clusters=dm.n_clusters, n_eff=tiers._n_eff((-d).tolist(), clusters))


def run_trial(ledger_path: Path = LEDGER, db_path: Path = SCREENS_DB, out: Path = OUT) -> dict:
    seal = seal_check()
    if semantic_hash(HYPOTHESIS) != EXPECTED_HASH:
        raise RuntimeError("hypothesis hash drift")
    served, rule, part, feature = build()
    before = _ledger_state(ledger_path)
    with results_db.ResultsDB(db_path) as db:
        prior_n = len(db.family_p_values(FAMILY))
        result = tiers.run_tier(HYPOTHESIS, "T2", states=served, predict_fn=RealScreenPredictor(feature),
                                ledger_path=ledger_path, partition=part, rule=rule, family=FAMILY,
                                screened_n=SCREENED_N, results_db=db,
                                artifact_path=str(out) + "_bars.json", trial_prereg_sha256=seal)
        db.record(dict(hash=result.hash, tier="T2", corpus="soccer", corpus_unit="",
                       corpus_sha=part.verdict_sha256[:16], n=result.n, n_eff=result.n_eff,
                       brier_model=result.brier_model, brier_close=result.brier_close,
                       dm_stat=result.dm, raw_p=result.raw_p, k_family=result.k_family,
                       k_global=result.k_global, deflated_p=result.deflated_p, pbo=result.pbo,
                       verdict=result.verdict, artifact_path=str(out) + ".json",
                       prereg_sha256=result.prereg_sha256, run_at=None))
    after = _ledger_state(ledger_path)
    if after[0] != before[0] + 1:
        raise RuntimeError("ledger rows %d -> %d, expected exactly one charge" % (before[0], after[0]))
    k = int(result.k_global)
    # REPRODUCTION (A2) + the differential (Q9): an independent second CPCV run must match.
    predictor = RealScreenPredictor(feature)
    ids, model, close, y = tiers._pooled_oof(cpcv_evaluate(list(served), predictor))
    by_id = {s["game_id"]: s for s in served}
    rows = [by_id[i] for i in ids]
    _, divs = tiers._cluster_ids(rows, "soccer")
    pooled = _unit(model, close, y, divs)
    for mine, theirs in ((pooled["brier_model"], result.brier_model),
                         (pooled["brier_close"], result.brier_close), (pooled["dm_stat"], result.dm)):
        if abs(mine - theirs) > 1e-9:
            raise RuntimeError("reproduction failed: %r vs %r" % (mine, theirs))
    units = {}
    for div in sorted(set(divs)):
        mask = np.array([c == div for c in divs])
        units[div] = _unit(model[mask], close[mask], y[mask], [r["home"] for r, m in zip(rows, mask) if m])
    conditions = dict(improvement=pooled["improvement"] >= BAR, dm_ci=pooled["ci_lo"] > 0,
                      deflated_p=result.deflated_p < rule.alpha, family_bar=bool(result.bh_passed))
    verdict = result.verdict
    if verdict == "AHEAD" and not all(conditions.values()):
        verdict = "MATCH"                         # the prereg bar is stricter than the factory's
    n_corpora = sum(1 for u in units.values() if u["improvement"] >= BAR and u["ci_lo"] > 0)
    replication = replication_fields(verdict, n_corpora, k)
    d = (close - y) ** 2 - (model - y) ** 2
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(str(out) + "_perevent.csv", "w", newline="", encoding="ascii") as fh:
        fh.write("# prereg_sha256=%s k_launch=%d\n" % (seal, k))
        writer = csv.writer(fh)
        writer.writerow(CSV_FIELDS)
        for r, i, pm, pc, yy, dd in zip(rows, ids, model, close, y, d):
            writer.writerow([i, r["state_ts"], r["div"], r["home"], r["away"], pm, pc, int(yy),
                             (pm - yy) ** 2, (pc - yy) ** 2, dd])
    trial = dict(
        prereg_sha256=seal, hypothesis_hash=result.hash, family=FAMILY, screened_n=SCREENED_N,
        family_prior_raw_p_n=prior_n, family_n_used=prior_n + 1, k_launch=k, k_family=result.k_family,
        ledger_before=before, ledger_after=after, tier_verdict=result.verdict, dual_verdict=result.dual_verdict,
        verdict=verdict, conditions=conditions, bar=BAR, alpha=rule.alpha, replication=replication,
        pooled=pooled, units=units, deflated_p=result.deflated_p, raw_p=result.raw_p, pbo=result.pbo,
        n_eff_div=result.n_eff, cluster_key=result.cluster_key, n=result.n,
        screen_partition_sha256=result.screen_partition_sha256,
        verdict_partition_sha256=result.verdict_partition_sha256,
        tiers_spec_pin=result.prereg_sha256, families_spec_sha256=result.families_spec_sha256,
        family_q=result.family_q, bh_passed=result.bh_passed, global_passed=result.global_passed,
        archive=predictor.archive(),
        tick_informative=dict(grain="event (one row per match)", n_events=int(result.n),  # S87
                              n_informative=int(result.n), n_eff=float(result.n_eff),
                              note="S87: event grain -- one row per match, so no tick can repeat the previous quote; the informative-tick filter does not apply and n_events IS n_informative."))
    Path(str(out) + ".json").write_text(json.dumps(trial, allow_nan=False, indent=1, sort_keys=True),
                                        encoding="ascii")
    return trial


if __name__ == "__main__":
    t = run_trial()
    print(json.dumps({k: t[k] for k in ("verdict", "tier_verdict", "conditions", "k_launch", "pooled",
                                        "replication", "family_n_used", "deflated_p", "pbo")}, indent=1))
    for div, u in t["units"].items():
        print(div, json.dumps(u))
