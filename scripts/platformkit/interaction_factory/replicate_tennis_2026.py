"""scripts.platformkit.interaction_factory.replicate_tennis_2026 -- genuine
independent-corpus refire of the 5 tennis_match_asof_self_cross candidates that
replicate_batch2b.py recorded REPLICATION_BLOCKED (gap ledger rank 5, fix-wave
lane beta, 2026-07-11).

That block was honest at the time: matches.parquet/asof_return.parquet/
asof_features.parquet were single monolithic files (2015-01-04..2025-12-17) and
no 2026 tennis data existed on disk. It has SINCE landed:
domains/tennis/matches_2026.parquet (ESPN results bridge, 3125 rows,
2026-01-02..2026-07-09, commit e3f96cae) -- a real, disjoint-date corpus with a
genuine outcome label (winner), though results-only (no ace/1stIn/2ndWon/bpFaced
counts -- no 2026 Sackmann match_stats.parquet sidecar exists, and Sackmann's own
GitHub source is 404, so this ceiling is now PERMANENT, not a "wait for more data"
gap).

The refire is still valid despite the missing match_stats: as-of features are
STRICTLY-PRIOR trailing means (a match's own stats never touch its own row --
see domains/tennis/asof_features.py), so a 2026 match's as-of snapshot is fully
computable from its players' pre-2026 history even though the match itself can't
extend that history further. domains/tennis/asof_ext2026.py builds this extended
corpus and confirms every pre-2026 row is byte-identical to the production files
(nothing retroactively changed) with 3125/3125 2026 matches getes their genuine
as-of features, 647 with BOTH players resolved to >=1 prior match (only n=647
enters the fit gate below matches's builder columns).

This intentionally does NOT touch replicate_batch2b.py (which correctly recorded
history as of that run) -- it appends fresh ledger rows with a distinct corpus tag
so both the original block and this later refire stay on the record.

CLI: python -m scripts.platformkit.interaction_factory.replicate_tennis_2026
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from domains.tennis.asof_ext2026 import FEATURES_EXT_OUT, MATCHES_EXT_OUT, RETURN_EXT_OUT
from scripts.platformkit.interaction_factory import builders_task39b as T39B
from scripts.platformkit.interaction_factory import runner as IFR
from scripts.platformkit.interaction_factory.replicate_batch2b import (
    TEMPLATE_IDS, _candidate_from_row, verdict_for, _upsert_verdicts, _queue_promotion,
    ALPHA, K_DECLARED,
)
from scripts.platformkit.clv_ledger_io import ledger_lock
from scripts.platformkit.io_atomic import append_jsonl_atomic

TENNIS_TEMPLATE = "tennis_match_asof_self_cross"
CORPUS_TAG = "tennis_asof_ext2026_espn_bridge"


def _tennis_blocked_rows(ledger_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The batch-2b tennis rows this refires: template match + latest verdict for
    each candidate_id is REPLICATION_BLOCKED (never re-blocks an already-REPLICATED
    or already-refired-by-this-module candidate)."""
    latest: Dict[str, Dict[str, Any]] = {}
    for r in ledger_rows:
        if r.get("template_id") == TENNIS_TEMPLATE:
            latest[r["candidate_id"]] = r
    return [r for r in latest.values() if r.get("verdict") == "REPLICATION_BLOCKED"
            and r.get("corpus") == "unbuildable"]


def _build_2026_frame(attrs: List[str]) -> pd.DataFrame:
    matches_ext = pd.read_parquet(MATCHES_EXT_OUT, columns=["event_id", "tourney_id", "winner", "date"])
    ret_ext = pd.read_parquet(RETURN_EXT_OUT)
    feats_ext = pd.read_parquet(FEATURES_EXT_OUT)
    frame = T39B.build_tennis_match_frame(matches_ext, ret_ext, feats_ext, attrs)
    is_2026 = pd.to_datetime(matches_ext["date"]) >= "2026-01-01"
    frame_2026 = frame.loc[is_2026.to_numpy()].copy()
    return frame_2026


def replicate(*, ledger_path: Path = None) -> List[Dict[str, Any]]:
    ledger_path = ledger_path or IFR.LEDGER_PATH
    existing = IFR._load_ledger(ledger_path)  # noqa: SLF001 -- same loader discovery uses
    blocked = _tennis_blocked_rows(existing)

    # b0 = the ORIGINAL discovery row (SURVIVES_PREREG_PROVISIONAL), needed for
    # discovery_effect/p/n on the appended row -- look it up by replication_of.
    # Filtered to the SURVIVES verdict specifically: candidate_id repeats across
    # ledger rows (discovery -> REPLICATION_BLOCKED -> this refire), and a plain
    # last-write-wins dict would pick up a later BLOCKED row (effect=None) instead.
    by_id = {r["candidate_id"]: r for r in existing
             if r.get("template_id") == TENNIS_TEMPLATE and r.get("verdict") == "SURVIVES_PREREG_PROVISIONAL"}
    out_rows: List[Dict[str, Any]] = []
    verdicts: Dict[str, Any] = {}

    for blocked_row in blocked:
        b0 = by_id.get(blocked_row["replication_of"], blocked_row)
        cand = _candidate_from_row(b0)
        attrs = [cand.attr_a, cand.attr_b]
        frame_2026 = _build_2026_frame(attrs)
        build = {"frame": frame_2026, "cluster": "tourney_id", "kind": "logit"}
        fit = IFR._fit_candidate(build, cand)  # noqa: SLF001 -- same fit runner discovery uses
        v = verdict_for(b0["effect"], fit)
        corpus = CORPUS_TAG if fit else "unbuildable"
        n_2026 = len(frame_2026)
        note = (
            "REPLICATION corpus=%s (2026 ESPN-bridge matches, disjoint from discovery's "
            "2015-2025 fit; n_candidate_rows=%d before dropna) of batch2b candidate "
            "(discovery effect=%.6f p=%.4g n=%d)" % (corpus, n_2026, b0["effect"], b0["p"], b0["n"])
            if fit else
            "STILL_BLOCKED even on the 2026 ESPN bridge: after requiring both players' "
            "diff_%s_asof/diff_%s_asof non-null and >=5 distinct tourney_id clusters, "
            "fewer than MIN_N=%d rows survive (n_candidate_rows=%d before dropna) -- "
            "matches_2026 resolves only 647/3125 matches to players with >=1 prior "
            "Sackmann-history match." % (cand.attr_a, cand.attr_b, IFR.MIN_N, n_2026)
        )
        row = {
            "candidate_id": cand.candidate_id, "template_id": cand.template_id, "sport": cand.sport,
            "atomic_unit": cand.atomic_unit, "outcome": cand.outcome,
            "attr_a": cand.attr_a, "attr_b": cand.attr_b, "term": "fa:fb",
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
        with ledger_lock(ledger_path):  # judge NIT a1eff899: same-ledger writers must share the lock
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
        print("tennis_2026: no REPLICATION_BLOCKED tennis rows on record -- nothing to refire")
        return 0
    for r in rows:
        print("%-72s %-32s effect=%s p=%s n=%d" % (
            r["candidate_id"][:72], r["verdict"],
            ("%.6f" % r["effect"]) if r["effect"] is not None else "--",
            ("%.4g" % r["p"]) if r["p"] is not None else "--", r["n"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["replicate", "main", "CORPUS_TAG"]
