"""scripts.platformkit.interaction_factory.replicate_reserve -- R2: GENERIC
reserve-slice replication worker (RESERVED_CORPUS_SPEC.md). Unlike replicate_
nba_2026.py / replicate_survivors.py (one hand-wired worker per family, a
hand-picked disjoint season parquet), this worker serves ANY post-spec
survivor whose discovery-time ledger row carries a `reserved_corpus` name:
it rebuilds the SAME builder frame the discovery fit used (runner._BUILDERS
[tpl["feature_builder"]]), takes the RESERVE side of reserve.py's split (the
slice discovery excluded -- see reserve_slice() below), and refits the
candidate there via the same IFR._fit_candidate machinery discovery used.
Independence by construction, no per-family hand-wiring needed.

K IS DECLARED per run as len(pending) (flat Bonferroni over whatever this
tick's pending batch is -- same "declare K before running" discipline as
replicate_nba_2026's fixed K=2, just dynamic since this worker spans every
template rather than one).

STEP 0 premise (2026-07-13): zero ledger rows currently carry a non-null
reserved_corpus -- every registered builder's frame still lacks a season/
date column (chips pending). A real run today is an honest no-op; this
worker exists so the FIRST post-chip survivor gets replicated automatically,
zero human wiring required (RESERVED_CORPUS_SPEC.md's "ready before need").

Verdicts (identical vocabulary to replicate_nba_2026.py):
  REPLICATED                          same sign, p < alpha
  FAILED_REPLICATION_POWER_ANNOTATED  same sign, p >= alpha (power miss)
  KILLED                              sign flip vs discovery
  NOT_TESTABLE                        corpus/frame unbuildable / reserve empty

CLI: python -m scripts.platformkit.interaction_factory.replicate_reserve
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from scripts.platformkit.clv_ledger_io import ledger_lock
from scripts.platformkit.combo.fwer_budget import DEFAULT_EPS, eps_eff
from scripts.platformkit.interaction_factory import generator as GEN
from scripts.platformkit.interaction_factory import reserve as RESERVE
from scripts.platformkit.interaction_factory import runner as IFR
from scripts.platformkit.io_atomic import append_jsonl_atomic

TEMPLATE_ID = None  # generic worker -- not scoped to one template, see FAMILY_WORKERS lookup


def reserve_slice(frame: pd.DataFrame,
                   date_col_candidates: Tuple[str, ...] = RESERVE.DATE_COL_CANDIDATES,
                   ) -> Tuple[pd.DataFrame, Optional[str]]:
    """Complement of reserve.reserve_mask's discovery slice -- the RESERVE
    rows themselves (what discovery excluded). Same axis-detection rule
    reserve_mask uses so the two functions never disagree on which rows go
    where: discovery_frame and reserve_slice(frame) are disjoint and their
    union (as sets of rows) equals `frame` (see test_replicate_reserve.py's
    trap test)."""
    axis_col = next((c for c in date_col_candidates if c in frame.columns), None)
    if axis_col is None:
        return frame.iloc[0:0].reset_index(drop=True), None
    if axis_col == "season":
        seasons = sorted(frame[axis_col].dropna().unique())
        if len(seasons) < 2:
            return frame.iloc[0:0].reset_index(drop=True), None
        reserve_val = seasons[-2]  # most recent COMPLETE season -- same value reserve_mask excludes
        reserve = frame[frame[axis_col] == reserve_val].reset_index(drop=True)
        return reserve, str(reserve_val)
    # date-like axis (game_date/date) -> trailing 25% of rows, same stable sort reserve_mask uses.
    ordered = frame.sort_values(axis_col, kind="mergesort")
    cut = int(len(ordered) * 0.75)
    reserve = ordered.iloc[cut:].reset_index(drop=True)
    return reserve, "trailing_25pct_by_%s" % axis_col


def _pending_reserved_survivors(ledger_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Latest-verdict SURVIVES_PREREG_PROVISIONAL rows carrying a non-null
    reserved_corpus, with no replication row anywhere in the ledger yet --
    same replication_of join key every replicate_* worker uses."""
    latest: Dict[str, Dict[str, Any]] = {}
    for r in ledger_rows:
        cid = r.get("candidate_id")
        if cid:
            latest[cid] = r  # ledger append-order -- last write for a candidate_id wins
    already = {r.get("replication_of") for r in ledger_rows if r.get("replication_of")}
    return [r for r in latest.values()
            if r.get("verdict") == IFR.SURVIVES and r.get("reserved_corpus")
            and r["candidate_id"] not in already]


def _candidate_from_row(row: Dict[str, Any]) -> Optional[GEN.Candidate]:
    tpl = GEN.TEMPLATES.get(row["template_id"])
    if tpl is None:
        return None
    cid = row["candidate_id"]
    entity_class = cid.rsplit("::class=", 1)[1] if "::class=" in cid else None
    return GEN.Candidate(
        candidate_id=cid, template_id=row["template_id"], sport=tpl["sport"],
        atomic_unit=tpl["atomic_unit"], outcome=tpl["outcome"],
        attr_a=row["attr_a"], attr_b=row["attr_b"], feature_builder=tpl["feature_builder"],
        entity_class=entity_class,
    )


def verdict_for(discovery_effect: float, fit: Optional[Dict[str, Any]], alpha: float) -> str:
    """Pure verdict rule -- identical shape to replicate_nba_2026.verdict_for."""
    if fit is None:
        return "NOT_TESTABLE"
    same_sign = (fit["effect"] > 0) == (discovery_effect > 0) and fit["effect"] != 0
    if not same_sign:
        return "KILLED"
    return "REPLICATED" if fit["p"] < alpha else "FAILED_REPLICATION_POWER_ANNOTATED"


def replicate(*, ledger_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Re-test every pending reserved-corpus survivor on its own reserve
    slice. Appends one ledger row per survivor (never overwrites the
    discovery row). Groups pending rows by template_id so each template's
    frame is built once. Returns the appended rows."""
    ledger_path = ledger_path or IFR.LEDGER_PATH
    existing = IFR._load_ledger(ledger_path)  # noqa: SLF001 -- same loader discovery uses
    pending = _pending_reserved_survivors(existing)
    if not pending:
        return []
    k_declared = len(pending)
    alpha = eps_eff(DEFAULT_EPS, k_declared)

    by_tpl: Dict[str, List[Dict[str, Any]]] = {}
    for r in pending:
        by_tpl.setdefault(r["template_id"], []).append(r)

    out_rows: List[Dict[str, Any]] = []
    for tid, rows in by_tpl.items():
        tpl = GEN.TEMPLATES.get(tid)
        builder = IFR._BUILDERS.get(tpl["feature_builder"]) if tpl else None
        attrs = sorted({r["attr_a"] for r in rows} | {r["attr_b"] for r in rows})
        build = None
        if builder is not None and tpl is not None:
            try:
                build = builder(attrs, tpl)
            except Exception:  # noqa: BLE001 -- an unbuildable frame is NOT_TESTABLE, not a crash
                build = None
        reserve_frame, reserve_name = (None, None)
        if build is not None and build.get("frame") is not None:
            reserve_frame, reserve_name = reserve_slice(build["frame"])

        for row in rows:
            cand = _candidate_from_row(row)
            fit, corpus = None, "unbuildable"
            if cand is not None and build is not None and reserve_frame is not None and len(reserve_frame) > 0:
                rbuild = dict(build)
                rbuild["frame"] = reserve_frame
                corpus = "%s_reserve_%s" % (build["corpus"], reserve_name)
                rbuild["corpus"] = corpus
                try:
                    fit = IFR._fit_candidate(rbuild, cand)
                except Exception:  # noqa: BLE001 -- one candidate's fit failure isolates
                    fit = None
            v = verdict_for(row["effect"], fit, alpha)
            out_row = {
                "candidate_id": row["candidate_id"], "template_id": tid, "sport": row.get("sport"),
                "atomic_unit": row.get("atomic_unit"), "outcome": row.get("outcome"),
                "attr_a": row["attr_a"], "attr_b": row["attr_b"], "term": "fa:fb",
                "k_declared": k_declared, "cum_K": k_declared, "verdict": v,
                "effect": round(fit["effect"], 6) if fit else None,
                "p": round(fit["p"], 6) if fit else None,
                "n": int(fit["n"]) if fit else 0,
                "alpha_fwer": round(alpha, 8), "corpus": corpus,
                "note": "RESERVE-SLICE REPLICATION corpus=%s of discovery candidate "
                        "(discovery effect=%.6f p=%.4g n=%d)" % (
                            row.get("reserved_corpus"), row["effect"], row["p"], row["n"]),
                "edge_claimed": False, "computed_at": IFR._now(),  # noqa: SLF001
                "replication_of": row["candidate_id"], "replication_season": row.get("reserved_corpus"),
                "discovery_effect": row["effect"], "discovery_p": row["p"], "discovery_n": row["n"],
            }
            with ledger_lock(ledger_path):  # same shared lock every ledger writer uses
                append_jsonl_atomic(ledger_path, out_row)
            out_rows.append(out_row)
    return out_rows


def main() -> int:
    rows = replicate()
    if not rows:
        print("replicate_reserve: no pending reserved-corpus survivors on record -- nothing to replicate")
        return 0
    for r in rows:
        print("%-58s %-32s effect=%s p=%s n=%d (discovery effect=%.4f p=%.4g n=%d)" % (
            r["candidate_id"][:58], r["verdict"],
            ("%.6f" % r["effect"]) if r["effect"] is not None else "--",
            ("%.4g" % r["p"]) if r["p"] is not None else "--", r["n"],
            r["discovery_effect"], r["discovery_p"], r["discovery_n"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["replicate", "reserve_slice", "verdict_for", "main"]
