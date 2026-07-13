"""scripts.platformkit.omni.funnel -- P4 screen->family->gate funnel (S8.3).

Thin orchestration over EXISTING machinery, never a fork of its math:
  A SCREEN  -- scripts.platformkit.interaction_factory.runner.run_batch (the
              factory's own cluster-robust fit + FWER-tightening verdict).
              Kills (NULL/NOT_TESTABLE) -> negative/meta claims. Row-level
              retention (the exact fit-input rows, not a re-derived score)
              written to data/omni/preds/<batch_id>/<signal>.parquet BEFORE
              the verdict claim is ledgered -- the REAUDIT lane proved
              aggregates-only makes re-scoring impossible; this is the fix.
  B FAMILY  -- Benjamini-Hochberg (statsmodels, off-the-shelf) over the
              batch's screen-survivor p-values; batch_overfit_est = mean BH
              q-value (expected false-discovery share if the whole batch
              shipped). Verdicts ledgered via a native_altitude contract
              BEFORE any reserve contact (pre-registration).
  C GATE    -- scripts.platformkit.interaction_factory.replicate_reserve (R2,
              the existing reserve-slice worker). This lane only assembles
              the evidence packet into a claim (lifecycle=replicated/rejected/
              screened) -- promotion to accepted is Fable-only (S3).

INVARIANTS: <=300 LOC. pandas/statsmodels (already a runner.py dependency).
ASCII stdout. No $/edge claims. Never writes data/registry/.
"""
from __future__ import annotations

import pathlib
from typing import Any, Dict, List, Optional

import pandas as pd
from statsmodels.stats.multitest import multipletests

from scripts.platformkit.interaction_factory import generator as GEN
from scripts.platformkit.interaction_factory import runner as IFR
from scripts.platformkit.interaction_factory import replicate_reserve as RR
from scripts.platformkit.omni import claims_ledger as CL
from scripts.platformkit.omni import claims_intake as CI
from scripts.platformkit.omni import native_altitude as NA

PREDS_DIR = pathlib.Path("data/omni/preds")

# Coarse template-outcome -> native_altitude observable/metric map. Best
# available mapping today, not a claim of precision -- a future lane can
# widen this table without touching the funnel's control flow.
_OBSERVABLE_BY_OUTCOME = {
    "efg": "shot_quality", "net_pts": "possession_outcome",
    "home_win": "game_winprob", "p1_win": "game_winprob",
}


def _safe_name(candidate_id: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in candidate_id)[:180]


def write_preds(batch_id: str, candidate_id: str, build: Optional[Dict[str, Any]],
                 row: Dict[str, Any], *, preds_dir: Optional[pathlib.Path] = None) -> pathlib.Path:
    """Persist the exact rows a candidate's fit consumed (or an empty marker
    frame if unbuildable) -- NOT a re-derived prediction, the raw fit input,
    which is enough to re-score later without re-fitting from scratch."""
    d = pathlib.Path(preds_dir) if preds_dir is not None else PREDS_DIR
    out_dir = d / batch_id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{_safe_name(candidate_id)}.parquet"
    frame = pd.DataFrame()
    if build is not None and build.get("frame") is not None:
        f = build["frame"]
        ca, cb, cl_col = "asof__" + row["attr_a"], "asof__" + row["attr_b"], build.get("cluster")
        cols = [c for c in ("y", ca, cb, cl_col) if c and c in f.columns]
        if cols:
            frame = f[cols].dropna().rename(columns={ca: "fa", cb: "fb", cl_col: "cluster"})
    frame.to_parquet(path, index=False)
    return path


def _kill_claim(row: Dict[str, Any], batch_id: str, *, base_dir=None) -> Optional[str]:
    verdict = row["verdict"]
    if verdict not in (IFR.NULL, IFR.NOT_TESTABLE):
        return None
    claim = {
        "statement": f"{row['candidate_id']} screen ({row['template_id']}): {verdict}",
        "type": "negative" if verdict == IFR.NULL else "meta",
        "scope": {"sport": row.get("sport"), "regime": "all", "market_families": []},
        "topic": row.get("outcome") or row["template_id"],
        "lifecycle": "rejected" if verdict == IFR.NULL else "screened",
        "effect": {"metric": "p", "size": row.get("effect"), "n": row.get("n")},
        "evidence": {"discovery_corpus": row.get("corpus"), "batch_id": batch_id},
        "provenance": {"created_by_lane": "P4_funnel_stage_a"},
        "links": {"signals": [row["candidate_id"]]},
    }
    return CL.add_claim(claim, base_dir=base_dir)


def stage_a_screen(template_id: str, k: int, batch_id: str, *, ledger_path=None,
                    base_dir=None, preds_dir=None) -> List[Dict[str, Any]]:
    """SCREEN: run the factory's own batch, retain row-level preds for every
    scored candidate, ledger a kill claim for NULL/NOT_TESTABLE. Returns one
    dict per row with verdict/effect/p/n + preds_path + kill_claim_id."""
    ledger_path = ledger_path or IFR.LEDGER_PATH
    rows = IFR.run_batch(template_id, k, ledger_path=ledger_path)
    tpl = GEN.TEMPLATES.get(template_id)
    builder = IFR._BUILDERS.get(tpl["feature_builder"]) if tpl else None  # noqa: SLF001
    build = None
    if builder is not None and rows:
        attrs = sorted({r["attr_a"] for r in rows} | {r["attr_b"] for r in rows})
        try:
            build = builder(attrs, tpl)
        except Exception:  # noqa: BLE001 -- unbuildable -> empty retention frame, not a crash
            build = None
    out = []
    for row in rows:
        preds_path = write_preds(batch_id, row["candidate_id"], build, row, preds_dir=preds_dir)
        kill_id = _kill_claim(row, batch_id, base_dir=base_dir)
        out.append({**row, "preds_path": str(preds_path), "kill_claim_id": kill_id})
    return out


def stage_b_family(screen_rows: List[Dict[str, Any]], batch_id: str, *,
                    alpha: float = 0.05, base_dir=None) -> List[Dict[str, Any]]:
    """FAMILY: Benjamini-Hochberg over screen survivors' p-values within this
    batch; batch_overfit_est = mean BH q-value. Pre-registers (name + sign +
    effect) to the ledger via a native_altitude contract BEFORE stage C is
    ever called (caller sequencing, not this function, guarantees "before
    reserve contact" -- run_funnel always calls B then C)."""
    survivors = [r for r in screen_rows if r["verdict"] == IFR.SURVIVES]
    if not survivors:
        return []
    pvals = [r["p"] for r in survivors]
    reject, qvals, _, _ = multipletests(pvals, alpha=alpha, method="fdr_bh")
    batch_overfit_est = float(sum(qvals) / len(qvals))
    out = []
    for row, passed, q in zip(survivors, reject, qvals):
        observable = _OBSERVABLE_BY_OUTCOME.get(row.get("outcome"), "possession_outcome")
        metric = "logloss" if row.get("outcome") in ("home_win", "p1_win") else "crps"
        contract = NA.build_contract(
            signal_name=row["candidate_id"], sport=row.get("sport") or "unknown",
            native_observable=observable, metric=metric,
            baseline_model=row["template_id"], market_families=[f"fam_{row['template_id']}"],
            regime_scope="all", corpus=row.get("corpus") or "discovery",
        )
        verdict = "ACCEPT" if bool(passed) else "REJECT"
        family = contract["market_families"][0]
        statement = (f"{contract['signal_name']} native-altitude {contract['metric']} "
                     f"vs {contract['baseline_model']} on {family}: {verdict}")
        claim = {
            "statement": statement,
            "type": NA._TYPE_BY_VERDICT[verdict],  # noqa: SLF001 -- reuse the P3 mapping table verbatim
            "scope": {"sport": contract["sport"], "regime": "all", "market_families": [family]},
            "topic": contract["native_observable"],
            "lifecycle": NA._LIFECYCLE_BY_VERDICT[verdict],  # noqa: SLF001
            "effect": {"metric": contract["metric"], "size": row.get("effect"),
                       "ci_low": None, "ci_high": None, "n": row.get("n")},
            "evidence": {"discovery_corpus": contract["corpus"], "p_disc": row.get("p"),
                         "batch_id": batch_id, "batch_overfit_est": round(batch_overfit_est, 6),
                         "scores": {"q_bh": round(float(q), 6)}},
            "provenance": {"created_by_lane": "P4_funnel_stage_b", "contract": contract},
            "links": {"market_families": [family]},
        }
        claim_id = CL.add_claim(claim, base_dir=base_dir)
        out.append({**row, "family_verdict": verdict, "q_bh": float(q),
                    "batch_overfit_est": batch_overfit_est, "prereg_claim_id": claim_id})
    return out


_GATE_LIFECYCLE = {"REPLICATED": "replicated", "FAILED_REPLICATION_POWER_ANNOTATED": "rejected",
                    "KILLED": "rejected", "NOT_TESTABLE": "screened"}
_GATE_TYPE = {"REPLICATED": "effect", "FAILED_REPLICATION_POWER_ANNOTATED": "negative",
              "KILLED": "negative", "NOT_TESTABLE": "meta"}


def stage_c_gate(family_rows: List[Dict[str, Any]], batch_id: str, *,
                  ledger_path=None, base_dir=None) -> List[Dict[str, Any]]:
    """GATE: call the EXISTING R2 reserve worker (global -- it processes every
    pending reserved-corpus survivor, not just this batch), then assemble one
    evidence-packet claim per family-pass candidate that this call resolved.
    A candidate the R2 pass didn't touch (no reserved_corpus, or worker still
    catching up) comes back QUEUED, not scored -- honest, not a crash."""
    passed = [r for r in family_rows if r.get("family_verdict") == "ACCEPT"]
    if not passed:
        return []
    rows = RR.replicate(ledger_path=ledger_path or IFR.LEDGER_PATH)
    by_cid = {r["candidate_id"]: r for r in rows}
    out = []
    for fr in passed:
        cid = fr["candidate_id"]
        r = by_cid.get(cid)
        if r is None:
            out.append({"candidate_id": cid, "gate_status": "QUEUED", "claim_id": None})
            continue
        verdict = r["verdict"]
        claim = {
            "statement": f"{cid} reserve-replication gate: {verdict}",
            "type": _GATE_TYPE[verdict],
            "scope": {"sport": r.get("sport"), "regime": "all", "market_families": []},
            "topic": r.get("template_id"),
            "lifecycle": _GATE_LIFECYCLE[verdict],
            "effect": {"metric": "p", "size": r.get("effect"), "n": r.get("n")},
            "evidence": {"reserve_corpus": r.get("corpus"), "p_disc": r.get("discovery_p"),
                         "p_repl": r.get("p"), "batch_id": batch_id},
            "provenance": {"created_by_lane": "P4_funnel_stage_c"},
            "links": {"signals": [cid], "parent_claims": [fr.get("prereg_claim_id")] if fr.get("prereg_claim_id") else []},
        }
        claim_id = CL.add_claim(claim, base_dir=base_dir)
        out.append({"candidate_id": cid, "gate_status": verdict, "claim_id": claim_id})
    return out


def run_funnel(template_id: str, k: int, batch_id: str, *, alpha: float = 0.05,
               ledger_path=None, base_dir=None, preds_dir=None) -> Dict[str, Any]:
    """A->B->C in sequence (the sequencing itself is the "pre-reg before
    reserve contact" guarantee -- stage_b always runs and ledgers before
    stage_c is invoked). Returns {screen, family, gate} row lists."""
    screen = stage_a_screen(template_id, k, batch_id, ledger_path=ledger_path,
                             base_dir=base_dir, preds_dir=preds_dir)
    family = stage_b_family(screen, batch_id, alpha=alpha, base_dir=base_dir)
    gate = stage_c_gate(family, batch_id, ledger_path=ledger_path, base_dir=base_dir)
    return {"screen": screen, "family": family, "gate": gate}


def generate_transfer_proposal(parent_claim: Dict[str, Any], *, sport: str = "basketball_nba",
                                base_dir=None) -> Dict[str, Any]:
    """Auto-generate one cross-sport transfer proposal from an existing
    ledgered claim (e.g. a tennis rest-x-return near-miss) into an NBA
    schedule-spot analog, routed through claims_intake so it survives the
    dead-family collision check. Enters stage A as a queued candidate (no
    NBA schedule-spot x return-analog builder is registered yet, so an
    honest run would land NOT_TESTABLE at screen -- that registration is a
    separate, human-scoped build, not this funnel's job)."""
    parent_id = parent_claim["claim_id"]
    proposal = {
        "statement": "nba schedule-spot (days_since_last_game) x defensive-return analog: proposed transfer",
        "type": "effect", "supporting_claim_ids": [parent_id],
        "scope": {"sport": sport, "regime": "all", "market_families": []},
        "topic": "schedule_spot_x_return_analog",
        "lifecycle": "proposed",
        "links": {"transfer_parents": [parent_id]},
        "provenance": {"created_by_lane": "P4_funnel_transfer_intake"},
    }
    return CI.intake_proposal(proposal, base_dir=base_dir)


__all__ = [
    "write_preds", "stage_a_screen", "stage_b_family", "stage_c_gate",
    "run_funnel", "generate_transfer_proposal", "PREDS_DIR",
]
