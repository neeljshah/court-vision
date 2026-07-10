"""scripts.platformkit.interaction_factory.replicate_tennis_knowledge_2026 --
independent-corpus replication of the 2 wave-22 knowledge-sourced
tennis_match_asof_self_cross SURVIVES_PREREG_PROVISIONAL candidates
(avg_games_per_set_asof_diff x diff_break_pct_asof / x diff_return_won_asof,
ledger rows computed_at 2026-07-10T13:50:02, effects -0.047896/-0.040784,
n=29155/29153, discovery k_declared=2 -- same fixed 2-candidate family this
module replicates with, K_DECLARED=2).

CORPUS: same disjoint 2026 ESPN-bridge slice replicate_tennis_2026.py uses
(domains/tennis/matches_ext2026.parquet, 2026-01-02..2026-07-09, zero
event_id/date overlap with discovery's 2015-2025 fit) -- but that module's
frame lacks avg_games_per_set_asof_diff (asof_setdetail.parquet was never
extended to 2026). avg_games_per_set_asof_diff is built PURELY from each
match's own `score` string (domains/tennis/ingest_setdetail_states.py), not a
separate match_stats sidecar, and matches_ext2026's 2026 rows carry an empty
`score` (no set-level data landed) -- so build_asof_setdetail(matches_ext2026)
computes a leak-free as-of snapshot for every 2026 match from its players'
pre-2026 history (walk-forward, snapshot-before-update, same discipline as
asof_ext2026.py) while contributing zero new history from the empty scores.
Computed in-memory here (no new domain parquet needed -- build_asof_setdetail
takes the matches frame directly).

CLI: python -m scripts.platformkit.interaction_factory.replicate_tennis_knowledge_2026
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from domains.tennis.asof_ext2026 import FEATURES_EXT_OUT, MATCHES_EXT_OUT, RETURN_EXT_OUT
from domains.tennis.ingest_setdetail_states import build_asof_setdetail
from scripts.platformkit.combo.fwer_budget import DEFAULT_EPS, eps_eff
from scripts.platformkit.interaction_factory import builders_task39b as T39B
from scripts.platformkit.interaction_factory import runner as IFR
from scripts.platformkit.interaction_factory.replicate_batch2b import (
    _candidate_from_row, verdict_for, _upsert_verdicts, _queue_promotion,
)
from scripts.platformkit.io_atomic import append_jsonl_atomic

TENNIS_TEMPLATE = "tennis_match_asof_self_cross"
CORPUS_TAG = "tennis_asof_ext2026_espn_bridge_setdetail"
# This module's own fixed 2-candidate family (mirrors the discovery rows'
# own k_declared=2 for this knowledge-sourced mini-batch) -- NOT the 6-family
# K replicate_batch2b/replicate_tennis_2026 declared for the unrelated
# blind-search batch-2b candidates.
K_DECLARED = 2
ALPHA = eps_eff(DEFAULT_EPS, K_DECLARED)

_MATCH_COLS = ["event_id", "date", "tour", "tourney_id", "winner", "round",
               "match_num", "p1_id", "p2_id", "score", "surface", "retirement"]


def _knowledge_survivors(ledger_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Latest verdict per candidate_id, filtered to knowledge-sourced tennis
    SURVIVES rows not already replicated by this module (never re-fires an
    already-replicated candidate)."""
    latest: Dict[str, Dict[str, Any]] = {}
    for r in ledger_rows:
        if r.get("template_id") == TENNIS_TEMPLATE and r.get("hypothesis_source") == "knowledge":
            latest[r["candidate_id"]] = r
    already = {r["replication_of"] for r in ledger_rows if r.get("replication_of")}
    return [r for r in latest.values() if r.get("verdict") == IFR.SURVIVES and r["candidate_id"] not in already]


def _build_2026_frame(attrs: List[str]) -> pd.DataFrame:
    matches_ext = pd.read_parquet(MATCHES_EXT_OUT, columns=_MATCH_COLS)
    ret_ext = pd.read_parquet(RETURN_EXT_OUT)
    feats_ext = pd.read_parquet(FEATURES_EXT_OUT)
    setdetail_ext = build_asof_setdetail(matches_ext)
    frame = T39B.build_tennis_match_frame(matches_ext, ret_ext, feats_ext, attrs, setdetail=setdetail_ext)
    is_2026 = pd.to_datetime(matches_ext["date"]) >= "2026-01-01"
    return frame.loc[is_2026.to_numpy()].copy()


def replicate(*, ledger_path=None) -> List[Dict[str, Any]]:
    ledger_path = ledger_path or IFR.LEDGER_PATH
    existing = IFR._load_ledger(ledger_path)  # noqa: SLF001 -- same loader discovery uses
    survivors = _knowledge_survivors(existing)

    out_rows: List[Dict[str, Any]] = []
    verdicts: Dict[str, Any] = {}
    for b0 in survivors:
        cand = _candidate_from_row(b0)
        attrs = [cand.attr_a, cand.attr_b]
        frame_2026 = _build_2026_frame(attrs)
        build = {"frame": frame_2026, "cluster": "tourney_id", "kind": "logit"}
        fit = IFR._fit_candidate(build, cand)  # noqa: SLF001 -- same fit runner discovery uses
        v = verdict_for(b0["effect"], fit)
        corpus = CORPUS_TAG if fit else "unbuildable"
        n_2026 = len(frame_2026)
        note = (
            "REPLICATION corpus=%s (2026 ESPN-bridge matches + in-memory "
            "asof_setdetail rebuild, disjoint from discovery's 2015-2025 fit; "
            "n_candidate_rows=%d before dropna) of the wave-22 knowledge-sourced "
            "candidate (discovery effect=%.6f p=%.4g n=%d)" % (
                corpus, n_2026, b0["effect"], b0["p"], b0["n"])
            if fit else
            "STILL_BLOCKED even on the 2026 ESPN bridge: after requiring both "
            "players' diff_%s_asof/diff_%s_asof non-null and >=5 distinct "
            "tourney_id clusters, fewer than MIN_N=%d rows survive "
            "(n_candidate_rows=%d before dropna)." % (
                cand.attr_a, cand.attr_b, IFR.MIN_N, n_2026)
        )
        row = {
            "candidate_id": cand.candidate_id, "template_id": cand.template_id, "sport": cand.sport,
            "atomic_unit": cand.atomic_unit, "outcome": cand.outcome,
            "attr_a": cand.attr_a, "attr_b": cand.attr_b, "term": "fa:fb",
            "hypothesis_source": "knowledge",
            "k_declared": K_DECLARED, "cum_K": K_DECLARED,
            "verdict": v if fit else "STILL_BLOCKED",
            "effect": round(fit["effect"], 6) if fit else None,
            "p": round(fit["p"], 6) if fit else None,
            "n": int(fit["n"]) if fit else 0,
            "alpha_fwer": round(ALPHA, 8), "corpus": corpus, "note": note,
            "edge_claimed": False, "computed_at": IFR._now(),  # noqa: SLF001
            "replication_of": b0["candidate_id"],
            "discovery_effect": b0["effect"], "discovery_p": b0["p"], "discovery_n": b0["n"],
        }
        append_jsonl_atomic(ledger_path, row)
        out_rows.append(row)
        verdicts[cand.candidate_id] = {"verdict": row["verdict"], "corpus": corpus, "effect": row["effect"],
                                        "p": row["p"], "n": row["n"], "computed_at": row["computed_at"]}
        if v == "REPLICATED":
            _queue_promotion(row, b0)

    _upsert_verdicts(verdicts)
    return out_rows


def main() -> int:
    rows = replicate()
    if not rows:
        print("tennis_knowledge_2026: no knowledge-sourced provisional tennis survivors on record -- nothing to replicate")
        return 0
    for r in rows:
        print("%-72s %-32s effect=%s p=%s n=%d" % (
            r["candidate_id"][:72], r["verdict"],
            ("%.6f" % r["effect"]) if r["effect"] is not None else "--",
            ("%.4g" % r["p"]) if r["p"] is not None else "--", r["n"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["replicate", "main", "CORPUS_TAG", "K_DECLARED", "ALPHA"]
