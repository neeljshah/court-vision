"""scripts.platformkit.interaction_factory.replicate_survivors -- independent-
season replication of the batch-1 SURVIVES_PREREG_PROVISIONAL rows for
nba_shot_offense_x_offense, on the 2024-25 player-offense-events corpus.

Why a standalone path, not runner.run_batch(): GEN.next_batch dedupes by
candidate_id ALONE (not candidate_id+season) -- calling run_batch again with
these exact candidate_ids on the same ledger would just see them as
"already tested" and return nothing. Replication re-fits the SAME 6
candidates on a DIFFERENT season's frame directly via
runner.build_nba_offense_frame + runner._fit_candidate, and APPENDS its own
rows (the batch-1 rows are never touched).

K IS DECLARED AS 6 (exactly the batch-1 survivor count) with a FLAT
Bonferroni bar -- eps_eff(DEFAULT_EPS, 6) -- applied uniformly to all 6,
unlike batch-1's running sequential-tightening across its wider 20-candidate
search. This replication set is its own fixed, pre-declared family.

Verdicts:
  REPLICATED                        same sign, p < alpha
  FAILED_REPLICATION_POWER_ANNOTATED  same sign, p >= alpha (records n both
                                     seasons -- the equal-power lesson, not a
                                     kill)
  KILLED                            sign flip vs batch-1
  NOT_TESTABLE                      corpus/frame unbuildable for this season

CLI: python -m scripts.platformkit.interaction_factory.replicate_survivors
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from scripts.platformkit.combo.fwer_budget import DEFAULT_EPS, eps_eff
from scripts.platformkit.interaction_factory import generator as GEN
from scripts.platformkit.interaction_factory import runner as IFR
from scripts.platformkit.io_atomic import append_jsonl_atomic, write_json_atomic

TEMPLATE_ID = "nba_shot_offense_x_offense"
REPL_SEASON = "2024_25"
K_DECLARED = 6
ALPHA = eps_eff(DEFAULT_EPS, K_DECLARED)

VERDICTS_PATH = IFR.LEDGER_PATH.parent / "interaction_factory_replication_verdicts.json"


def _batch1_survivors(ledger_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in ledger_rows
            if r.get("template_id") == TEMPLATE_ID and r.get("verdict") == IFR.SURVIVES]


def _candidate_from_row(row: Dict[str, Any]) -> GEN.Candidate:
    tpl = GEN.TEMPLATES[TEMPLATE_ID]
    return GEN.Candidate(
        candidate_id=row["candidate_id"], template_id=TEMPLATE_ID, sport=tpl["sport"],
        atomic_unit=tpl["atomic_unit"], outcome=tpl["outcome"],
        attr_a=row["attr_a"], attr_b=row["attr_b"], feature_builder=tpl["feature_builder"],
    )


def verdict_for(batch1_effect: float, fit: Optional[Dict[str, Any]]) -> str:
    """Pure verdict rule -- same sign + p<ALPHA -> REPLICATED; same sign,
    p>=ALPHA -> FAILED_REPLICATION_POWER_ANNOTATED; sign flip -> KILLED;
    unbuildable -> NOT_TESTABLE."""
    if fit is None:
        return "NOT_TESTABLE"
    same_sign = (fit["effect"] > 0) == (batch1_effect > 0) and fit["effect"] != 0
    if not same_sign:
        return "KILLED"
    return "REPLICATED" if fit["p"] < ALPHA else "FAILED_REPLICATION_POWER_ANNOTATED"


def _queue_promotion(row: Dict[str, Any], b1: Dict[str, Any]) -> None:
    """SHIP-review row via the SAME honesty-lint-gated human queue autoloop
    uses for a fresh survivor -- best-effort, never blocks the ledger write."""
    hq_row = {
        "kind": "INTERACTION_SURVIVOR_REPLICATED", "template_id": TEMPLATE_ID,
        "candidate_id": row["candidate_id"], "replication_season": row["replication_season"],
        "effect": row["effect"], "p": row["p"], "n": row["n"],
        "batch1_effect": b1["effect"], "batch1_p": b1["p"], "batch1_n": b1["n"],
        "note": "independent-season replication cleared the K=6 Bonferroni bar -- human review for promotion",
        "edge_claimed": False,
    }
    try:
        from scripts.platformkit.autoloop import autoloop_runner as AR
        AR._queue(hq_row, None)  # noqa: SLF001 -- reuse the honesty-lint-gated queue writer
    except Exception:  # noqa: BLE001 -- queueing is best-effort
        pass


def _upsert_verdicts(new_verdicts: Dict[str, Any]) -> None:
    prev: Dict[str, Any] = {}
    if VERDICTS_PATH.exists():
        try:
            prev = json.loads(VERDICTS_PATH.read_text(encoding="ascii", errors="replace"))
        except Exception:  # noqa: BLE001 -- a corrupt prior file never blocks a fresh write
            prev = {}
    prev.update(new_verdicts)
    write_json_atomic(VERDICTS_PATH, prev, encoding="ascii")


def replicate(*, ledger_path: Optional[Path] = None, season: str = REPL_SEASON) -> List[Dict[str, Any]]:
    """Re-test the batch-1 survivors on `season`'s corpus. Appends one ledger
    row per survivor (never overwrites batch-1 rows) and upserts the
    candidate_id -> latest-verdict summary file. Returns the appended rows."""
    ledger_path = ledger_path or IFR.LEDGER_PATH
    existing = IFR._load_ledger(ledger_path)  # noqa: SLF001 -- same loader batch-1 uses
    survivors = _batch1_survivors(existing)
    attrs = sorted({r["attr_a"] for r in survivors} | {r["attr_b"] for r in survivors})

    source = IFR.nba_source_for_season(season)
    build = None
    if source.exists():
        frame = IFR.build_nba_offense_frame(pd.read_parquet(source), attrs)
        build = {"frame": frame, "cluster": "player_id", "corpus": "player_offense_events_%s" % season,
                 "kind": "ols"}

    out_rows: List[Dict[str, Any]] = []
    verdicts: Dict[str, Any] = {}
    for b1 in survivors:
        cand = _candidate_from_row(b1)
        fit = None
        if build is not None:
            try:
                fit = IFR._fit_candidate(build, cand)  # noqa: SLF001 -- same fit runner batch-1 uses
            except Exception:  # noqa: BLE001 -- one candidate's fit failure isolates
                fit = None
        v = verdict_for(b1["effect"], fit)
        row = {
            "candidate_id": cand.candidate_id, "template_id": TEMPLATE_ID, "sport": cand.sport,
            "atomic_unit": cand.atomic_unit, "outcome": cand.outcome,
            "attr_a": cand.attr_a, "attr_b": cand.attr_b, "term": "fa:fb",
            "k_declared": K_DECLARED, "cum_K": K_DECLARED, "verdict": v,
            "effect": round(fit["effect"], 6) if fit else None,
            "p": round(fit["p"], 6) if fit else None,
            "n": int(fit["n"]) if fit else 0,
            "alpha_fwer": round(ALPHA, 8), "corpus": build["corpus"] if build else "unbuildable",
            "note": "REPLICATION season=%s of batch1 candidate (batch1 effect=%.6f p=%.4g n=%d)" % (
                season, b1["effect"], b1["p"], b1["n"]),
            "edge_claimed": False, "computed_at": IFR._now(),  # noqa: SLF001
            "replication_of": b1["candidate_id"], "replication_season": season,
            "batch1_effect": b1["effect"], "batch1_p": b1["p"], "batch1_n": b1["n"],
        }
        append_jsonl_atomic(ledger_path, row)
        out_rows.append(row)
        verdicts[cand.candidate_id] = {"verdict": v, "season": season, "effect": row["effect"],
                                        "p": row["p"], "n": row["n"], "computed_at": row["computed_at"]}
        if v == "REPLICATED":
            _queue_promotion(row, b1)

    _upsert_verdicts(verdicts)
    return out_rows


def main() -> int:
    rows = replicate()
    if not rows:
        print("%s: no batch-1 survivors on record -- nothing to replicate" % TEMPLATE_ID)
        return 0
    for r in rows:
        print("%-58s %-32s effect=%s p=%s n=%d (batch1 effect=%.4f p=%.4g n=%d)" % (
            r["candidate_id"][:58], r["verdict"],
            ("%.6f" % r["effect"]) if r["effect"] is not None else "--",
            ("%.4g" % r["p"]) if r["p"] is not None else "--", r["n"],
            r["batch1_effect"], r["batch1_p"], r["batch1_n"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["replicate", "verdict_for", "main", "TEMPLATE_ID", "REPL_SEASON",
           "K_DECLARED", "ALPHA", "VERDICTS_PATH"]
