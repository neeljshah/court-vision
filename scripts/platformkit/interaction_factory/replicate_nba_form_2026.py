"""scripts.platformkit.interaction_factory.replicate_nba_form_2026 -- Sonnet
build-lane follow-on to replicate_nba_2026.py (77d0277a) and the form-template
judged haul (nba_form_self_cross / nba_form_state_conditioner, builders_form_
trajectory.py): replication worker for these 2 templates' 13 pending
SURVIVES_PREREG_PROVISIONAL rows (11 self_cross + 2 state_conditioner).

STEP 0 PREMISE CHECK (fresh reads, this lane): the task brief assumed a
season-based disjoint second corpus mirroring replicate_nba_2026.py's shape
("the 2024-25 slice of form_trajectory_asof.parquet"). Verified FALSE by
reading builders_form_trajectory.py + the live ledger + the source parquet:

  * builders_form_trajectory._read_form_and_poe() takes NO season parameter
    -- it reads form_trajectory_asof.parquet WHOLE and concats every
    player_offense_events_<season>.parquet that exists for the seasons found
    in it. 2022-23 rows are dropped (no matching POE file on disk), leaving
    2023-24 + 2024-25 + 2025-26 already POOLED into ONE frame at discovery
    time (confirmed via the ledger: corpus="form_trajectory_asof",
    n=40000/32618, matching runner.MAX_ROWS's deterministic
    sample(40000, random_state=0) cap on the pooled frame).
  * There is therefore no held-out season on disk: every buildable season was
    already inside the discovery fit's own sample space. Empirically checked
    for a representative survivor pair (l5_min x l5_ts_pct): of the 19643
    season==2024-25 rows eligible for that candidate's frame, 14254 (72.5%)
    were ALREADY drawn into the discovery-time sample(40000, random_state=0).
    Refitting on "season==2024-25" would be a majority-overlapping resplit of
    the SAME rows discovery already saw, not an independent corpus -- exactly
    what replicate_nba_2026.py's own docstring disclaims doing.
  * The source file is also static: form_trajectory_asof.parquet's max
    game_date (2026-05-24) matches the current season already fully covered
    by discovery's computed_at (2026-07-13, today) -- no new games have
    landed since the fit ran, so there is no temporal holdout either.

This is structurally identical to replicate_batch2b.py's tennis case (single
monolithic multi-season file, discovery already pooled the ENTIRE range) --
mirrored here, not invented: REPLICATION_BLOCKED for every pending candidate
in both templates, one shared worker call processes both (same "ran_shared"
dedupe shape batch2b's MLB+tennis pair already exercises), K_DECLARED is the
live pending count (honest, not a hardcoded family size since this family's
"K" is a data-availability statement, not a test threshold currently in use).

Verdicts: REPLICATION_BLOCKED only (recorded honestly, never a fake pass; if
a disjoint corpus ever lands -- e.g. a 2026-27 season build of both stores --
a future revision can add a real fit path the same way batch2b's MLB_REPL_YEARS
grew a 3rd corpus later).

CLI: python -m scripts.platformkit.interaction_factory.replicate_nba_form_2026
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.combo.fwer_budget import DEFAULT_EPS, eps_eff
from scripts.platformkit.interaction_factory import generator as GEN
from scripts.platformkit.interaction_factory import runner as IFR
from scripts.platformkit.clv_ledger_io import ledger_lock
from scripts.platformkit.io_atomic import append_jsonl_atomic, write_json_atomic

TEMPLATE_IDS = ("nba_form_self_cross", "nba_form_state_conditioner")

VERDICTS_PATH = IFR.LEDGER_PATH.parent / "interaction_factory_replication_verdicts.json"

BLOCKED_NOTE = (
    "REPLICATION_BLOCKED: no independent-season corpus on disk for %s -- "
    "form_trajectory_asof.parquet is a single monolithic file (2022-23 "
    "dropped for missing POE source, 2023-24/2024-25/2025-26 already pooled "
    "into ONE frame at discovery and capped via runner.MAX_ROWS's "
    "sample(40000, random_state=0)); refitting on any season subset "
    "majority-overlaps that same discovery sample (72.5%% measured for a "
    "representative candidate), so it is not an independent corpus. Honest "
    "data-availability gap, not a code gap (discovery n=%d)."
)


def _pending_survivors(ledger_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Latest-verdict SURVIVES_PREREG_PROVISIONAL rows across BOTH templates
    with no replication row anywhere in the ledger yet -- same join key
    (replication_of) every replicate_* worker and replication_job.py use."""
    latest: Dict[str, Dict[str, Any]] = {}
    for r in ledger_rows:
        if r.get("template_id") in TEMPLATE_IDS:
            latest[r["candidate_id"]] = r
    already = {r.get("replication_of") for r in ledger_rows if r.get("replication_of")}
    return [r for r in latest.values()
            if r.get("verdict") == IFR.SURVIVES and r["candidate_id"] not in already]


def _candidate_from_row(row: Dict[str, Any]) -> GEN.Candidate:
    tpl = GEN.TEMPLATES[row["template_id"]]
    return GEN.Candidate(
        candidate_id=row["candidate_id"], template_id=row["template_id"], sport=tpl["sport"],
        atomic_unit=tpl["atomic_unit"], outcome=tpl["outcome"],
        attr_a=row["attr_a"], attr_b=row["attr_b"], feature_builder=tpl["feature_builder"],
    )


def _upsert_verdicts(new_verdicts: Dict[str, Any]) -> None:
    prev: Dict[str, Any] = {}
    if VERDICTS_PATH.exists():
        try:
            prev = json.loads(VERDICTS_PATH.read_text(encoding="ascii", errors="replace"))
        except Exception:  # noqa: BLE001 -- a corrupt prior file never blocks a fresh write
            prev = {}
    prev.update(new_verdicts)
    write_json_atomic(VERDICTS_PATH, prev, encoding="ascii")


def replicate(*, ledger_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Re-test both form templates' pending survivors. No disjoint corpus
    exists for this family (module docstring) so every pending candidate is
    recorded REPLICATION_BLOCKED -- one ledger row per survivor, never
    overwriting the discovery row. K_DECLARED is the live pending count at
    call time (honest -- this family has no real test to threshold yet)."""
    ledger_path = ledger_path or IFR.LEDGER_PATH
    existing = IFR._load_ledger(ledger_path)  # noqa: SLF001 -- same loader discovery uses
    survivors = _pending_survivors(existing)
    k_declared = len(survivors)
    alpha = eps_eff(DEFAULT_EPS, k_declared) if k_declared else DEFAULT_EPS

    out_rows: List[Dict[str, Any]] = []
    verdicts: Dict[str, Any] = {}
    for b0 in survivors:
        cand = _candidate_from_row(b0)
        row = {
            "candidate_id": cand.candidate_id, "template_id": cand.template_id, "sport": cand.sport,
            "atomic_unit": cand.atomic_unit, "outcome": cand.outcome,
            "attr_a": cand.attr_a, "attr_b": cand.attr_b, "term": "fa:fb",
            "k_declared": k_declared, "cum_K": k_declared, "verdict": "REPLICATION_BLOCKED",
            "effect": None, "p": None, "n": 0,
            "alpha_fwer": round(alpha, 8), "corpus": "unbuildable",
            "note": BLOCKED_NOTE % (cand.template_id, b0["n"]),
            "edge_claimed": False, "computed_at": IFR._now(),  # noqa: SLF001
            "replication_of": b0["candidate_id"],
            "discovery_effect": b0["effect"], "discovery_p": b0["p"], "discovery_n": b0["n"],
        }
        with ledger_lock(ledger_path):  # judge NIT a1eff899: same-ledger writers must share the lock
            append_jsonl_atomic(ledger_path, row)
        out_rows.append(row)
        verdicts[cand.candidate_id] = {"verdict": "REPLICATION_BLOCKED", "corpus": "unbuildable",
                                        "effect": None, "p": None, "n": 0, "computed_at": row["computed_at"]}

    _upsert_verdicts(verdicts)
    return out_rows


def main() -> int:
    rows = replicate()
    if not rows:
        print("nba_form_*: no pending survivors on record -- nothing to replicate")
        return 0
    for r in rows:
        print("%-58s %-24s %s (discovery effect=%.6f p=%.4g n=%d)" % (
            r["candidate_id"][:58], r["verdict"], r["corpus"],
            r["discovery_effect"], r["discovery_p"], r["discovery_n"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["replicate", "main", "TEMPLATE_IDS", "VERDICTS_PATH", "BLOCKED_NOTE"]
