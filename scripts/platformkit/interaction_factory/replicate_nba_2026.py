"""scripts.platformkit.interaction_factory.replicate_nba_2026 -- independent-
season replication of the nba_shot_attr_x_state SURVIVES_PREREG_PROVISIONAL
rows (M21 gap: replication_job.py's own docstring names this family as
"has no replicate_*.py yet").

STEP 0 premise: discovery fit player_offense_events_2025_26.parquet
(runner._NBA_SOURCE / _NBA_CORPUS, n~14k rows per candidate). A genuine
INDEPENDENT second corpus already exists on disk -- different NBA seasons in
the SAME store, same shape as runner.nba_source_for_season already threads
for replicate_survivors.py's sibling template (nba_shot_offense_x_offense):
player_offense_events_2024_25.parquet (24808 rows, 564 players) and
player_offense_events_2023_24.parquet (22717 rows, 448 players) -- disjoint
games/rows, not a resplit of the discovery frame. This module mirrors
replicate_survivors.py's season-refit mechanism (same builder, same ledger
convention) rather than replicate_tennis_2026.py's date-bridge shape, since a
same-store prior season IS this family's disjoint corpus (no ESPN-bridge /
"unbuildable" gap here to work around).

K IS DECLARED AS 2 (exactly this family's pending-survivor count:
transition_efg__x__late_clock_efg, zone_efg_rim__x__late_clock_efg) with a
FLAT Bonferroni bar -- eps_eff(DEFAULT_EPS, 2) -- same convention as
replicate_survivors.py's flat K=6.

Verdicts (identical vocabulary to replicate_survivors.py):
  REPLICATED                          same sign, p < alpha
  FAILED_REPLICATION_POWER_ANNOTATED  same sign, p >= alpha (a power miss,
                                       not a kill -- records n both seasons)
  KILLED                              sign flip vs discovery
  NOT_TESTABLE                        corpus/frame unbuildable for this season

CLI: python -m scripts.platformkit.interaction_factory.replicate_nba_2026
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from scripts.platformkit.combo.fwer_budget import DEFAULT_EPS, eps_eff
from scripts.platformkit.interaction_factory import generator as GEN
from scripts.platformkit.interaction_factory import runner as IFR
from scripts.platformkit.clv_ledger_io import ledger_lock
from scripts.platformkit.io_atomic import append_jsonl_atomic, write_json_atomic

TEMPLATE_ID = "nba_shot_attr_x_state"
REPL_SEASON = "2024_25"
K_DECLARED = 2
ALPHA = eps_eff(DEFAULT_EPS, K_DECLARED)

VERDICTS_PATH = IFR.LEDGER_PATH.parent / "interaction_factory_replication_verdicts.json"


def _pending_survivors(ledger_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Latest-verdict SURVIVES_PREREG_PROVISIONAL rows for this template with
    no replication row anywhere in the ledger yet -- same join key
    replication_job.pending_survivors uses (replication_of), so a re-run
    never re-replicates an already-replicated candidate."""
    latest: Dict[str, Dict[str, Any]] = {}
    for r in ledger_rows:
        if r.get("template_id") == TEMPLATE_ID:
            latest[r["candidate_id"]] = r
    already = {r.get("replication_of") for r in ledger_rows if r.get("replication_of")}
    return [r for r in latest.values()
            if r.get("verdict") == IFR.SURVIVES and r["candidate_id"] not in already]


def _candidate_from_row(row: Dict[str, Any]) -> GEN.Candidate:
    tpl = GEN.TEMPLATES[TEMPLATE_ID]
    return GEN.Candidate(
        candidate_id=row["candidate_id"], template_id=TEMPLATE_ID, sport=tpl["sport"],
        atomic_unit=tpl["atomic_unit"], outcome=tpl["outcome"],
        attr_a=row["attr_a"], attr_b=row["attr_b"], feature_builder=tpl["feature_builder"],
    )


def verdict_for(discovery_effect: float, fit: Optional[Dict[str, Any]]) -> str:
    """Pure verdict rule -- identical shape to replicate_survivors.verdict_for."""
    if fit is None:
        return "NOT_TESTABLE"
    same_sign = (fit["effect"] > 0) == (discovery_effect > 0) and fit["effect"] != 0
    if not same_sign:
        return "KILLED"
    return "REPLICATED" if fit["p"] < ALPHA else "FAILED_REPLICATION_POWER_ANNOTATED"


def _queue_promotion(row: Dict[str, Any], b0: Dict[str, Any]) -> None:
    """SHIP-review row via the SAME honesty-lint-gated human queue every
    replicate_* worker uses -- best-effort, never blocks the ledger write."""
    hq_row = {
        "kind": "INTERACTION_SURVIVOR_REPLICATED", "template_id": TEMPLATE_ID,
        "candidate_id": row["candidate_id"], "replication_season": row["replication_season"],
        "effect": row["effect"], "p": row["p"], "n": row["n"],
        "discovery_effect": b0["effect"], "discovery_p": b0["p"], "discovery_n": b0["n"],
        "note": "independent-season replication cleared the K=2 Bonferroni bar -- human review for promotion",
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
    """Re-test this family's pending survivors on `season`'s corpus. Appends
    one ledger row per survivor (never overwrites the discovery row) and
    upserts the shared candidate_id -> latest-verdict summary file. Returns
    the appended rows."""
    ledger_path = ledger_path or IFR.LEDGER_PATH
    existing = IFR._load_ledger(ledger_path)  # noqa: SLF001 -- same loader discovery uses
    survivors = _pending_survivors(existing)
    attrs = sorted({r["attr_a"] for r in survivors} | {r["attr_b"] for r in survivors})

    source = IFR.nba_source_for_season(season)
    build = None
    if source.exists() and attrs:
        frame = IFR.build_nba_offense_frame(pd.read_parquet(source), attrs)
        build = {"frame": frame, "cluster": "player_id", "corpus": "player_offense_events_%s" % season,
                 "kind": "ols"}

    out_rows: List[Dict[str, Any]] = []
    verdicts: Dict[str, Any] = {}
    for b0 in survivors:
        cand = _candidate_from_row(b0)
        fit = None
        if build is not None:
            try:
                fit = IFR._fit_candidate(build, cand)  # noqa: SLF001 -- same fit runner discovery uses
            except Exception:  # noqa: BLE001 -- one candidate's fit failure isolates
                fit = None
        v = verdict_for(b0["effect"], fit)
        row = {
            "candidate_id": cand.candidate_id, "template_id": TEMPLATE_ID, "sport": cand.sport,
            "atomic_unit": cand.atomic_unit, "outcome": cand.outcome,
            "attr_a": cand.attr_a, "attr_b": cand.attr_b, "term": "fa:fb",
            "k_declared": K_DECLARED, "cum_K": K_DECLARED, "verdict": v,
            "effect": round(fit["effect"], 6) if fit else None,
            "p": round(fit["p"], 6) if fit else None,
            "n": int(fit["n"]) if fit else 0,
            "alpha_fwer": round(ALPHA, 8), "corpus": build["corpus"] if build else "unbuildable",
            "note": "REPLICATION season=%s of discovery candidate (discovery effect=%.6f p=%.4g n=%d)" % (
                season, b0["effect"], b0["p"], b0["n"]),
            "edge_claimed": False, "computed_at": IFR._now(),  # noqa: SLF001
            "replication_of": b0["candidate_id"], "replication_season": season,
            "discovery_effect": b0["effect"], "discovery_p": b0["p"], "discovery_n": b0["n"],
        }
        with ledger_lock(ledger_path):  # judge NIT a1eff899: same-ledger writers must share the lock
            append_jsonl_atomic(ledger_path, row)
        out_rows.append(row)
        verdicts[cand.candidate_id] = {"verdict": v, "season": season, "effect": row["effect"],
                                        "p": row["p"], "n": row["n"], "computed_at": row["computed_at"]}
        if v == "REPLICATED":
            _queue_promotion(row, b0)

    _upsert_verdicts(verdicts)
    return out_rows


def main() -> int:
    rows = replicate()
    if not rows:
        print("%s: no pending survivors on record -- nothing to replicate" % TEMPLATE_ID)
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


__all__ = ["replicate", "verdict_for", "main", "TEMPLATE_ID", "REPL_SEASON",
           "K_DECLARED", "ALPHA", "VERDICTS_PATH"]
