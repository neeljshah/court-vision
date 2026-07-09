"""scripts.platformkit.interaction_factory.replicate_batch2b -- independent-
corpus replication of the batch-2b SURVIVES_PREREG_PROVISIONAL rows (task 39b
factory run, commit d7f4dbf2): 1 mlb_pa_attr_x_archetype candidate + 5
tennis_match_asof_self_cross candidates. Same discipline as the sibling
replicate_survivors.py (batch-1 nba_shot_offense_x_offense replication) --
flat K=6 Bonferroni across this fixed 6-candidate replication family, verdicts
upserted, ledger rows appended (never overwrites the batch-2b rows).

MLB: build_mlb_pa_archetype_frame + mlb_team_archetype_members are reused
verbatim; the independent corpus is savant_full__2024.parquet -- a fully
disjoint season from discovery's 2025 fit (runner._MLB_PA_YEAR), same
mlb_savant_source_for_year(year) path discovery itself uses.

TENNIS: REPLICATION_BLOCKED for all 5 candidates. asof_return.parquet /
asof_features.parquet / matches.parquet are single monolithic files (not
season-partitioned like the NBA/MLB corpora) spanning 2015-01-04 through
2025-12-17 in full -- and the discovery fit (build_tennis_match_frame) already
pooled the ENTIRE range in one fit (n=29181/30616 events). There is no
disjoint tennis match data on disk to refit on: no 2026 tennis season data has
landed, and re-fitting on any subset of the SAME rows discovery already saw is
not an independent corpus. This is an honest data-availability gap, not a
code gap -- recorded as REPLICATION_BLOCKED with the exact missing data, never
a fake pass.

CLI: python -m scripts.platformkit.interaction_factory.replicate_batch2b
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from scripts.platformkit.combo.fwer_budget import DEFAULT_EPS, eps_eff
from scripts.platformkit.interaction_factory import builders_task39b as T39B
from scripts.platformkit.interaction_factory import generator as GEN
from scripts.platformkit.interaction_factory import runner as IFR
from scripts.platformkit.io_atomic import append_jsonl_atomic, write_json_atomic

TEMPLATE_IDS = ("mlb_pa_attr_x_archetype", "tennis_match_asof_self_cross")
MLB_REPL_YEAR = "2024"
K_DECLARED = 6  # flat Bonferroni across this fixed 6-candidate replication family
ALPHA = eps_eff(DEFAULT_EPS, K_DECLARED)

VERDICTS_PATH = IFR.LEDGER_PATH.parent / "interaction_factory_replication_verdicts.json"

TENNIS_BLOCKED_NOTE = (
    "REPLICATION_BLOCKED: no independent-season tennis corpus on disk -- "
    "matches.parquet/asof_return.parquet/asof_features.parquet are single "
    "monolithic files (not season-partitioned) covering 2015-01-04..2025-12-17 "
    "in full, and the discovery fit already pooled that ENTIRE range "
    "(n=%d events used, tennis_asof_return_features corpus). No 2026 tennis "
    "match data has landed yet, so there is no disjoint out-of-sample corpus "
    "to refit on -- an honest data-availability gap, not a fake pass."
)


def _batch2b_survivors(ledger_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in ledger_rows
            if r.get("template_id") in TEMPLATE_IDS and r.get("verdict") == IFR.SURVIVES]


def _candidate_from_row(row: Dict[str, Any]) -> GEN.Candidate:
    tpl = GEN.TEMPLATES[row["template_id"]]
    return GEN.Candidate(
        candidate_id=row["candidate_id"], template_id=row["template_id"], sport=tpl["sport"],
        atomic_unit=tpl["atomic_unit"], outcome=tpl["outcome"],
        attr_a=row["attr_a"], attr_b=row["attr_b"], feature_builder=tpl["feature_builder"],
        entity_class=row.get("entity_class"),  # absent on old rows -> None, never guessed
    )


def _mlb_entity_class(candidate_id: str) -> Optional[str]:
    """candidate_id encodes '::class=<slug>' -- old rows have no entity_class
    field, so parse it back out of the id itself (same string this factory's
    own _candidate_id() built it with)."""
    marker = "::class="
    if marker not in candidate_id:
        return None
    tail = candidate_id.split(marker, 1)[1]
    return tail.split("::", 1)[0]


def verdict_for(discovery_effect: float, fit: Optional[Dict[str, Any]]) -> str:
    """Same pure rule as replicate_survivors.verdict_for: same sign + p<ALPHA
    -> REPLICATED; same sign, p>=ALPHA -> FAILED_REPLICATION_POWER_ANNOTATED;
    sign flip -> KILLED; unbuildable -> NOT_TESTABLE."""
    if fit is None:
        return "NOT_TESTABLE"
    same_sign = (fit["effect"] > 0) == (discovery_effect > 0) and fit["effect"] != 0
    if not same_sign:
        return "KILLED"
    return "REPLICATED" if fit["p"] < ALPHA else "FAILED_REPLICATION_POWER_ANNOTATED"


def _queue_promotion(row: Dict[str, Any], b0: Dict[str, Any]) -> None:
    """Best-effort SHIP-review queue push, same honesty-lint-gated human queue
    replicate_survivors._queue_promotion uses -- never blocks the ledger write."""
    hq_row = {
        "kind": "INTERACTION_SURVIVOR_REPLICATED", "template_id": row["template_id"],
        "candidate_id": row["candidate_id"], "replication_corpus": row["corpus"],
        "effect": row["effect"], "p": row["p"], "n": row["n"],
        "discovery_effect": b0["effect"], "discovery_p": b0["p"], "discovery_n": b0["n"],
        "note": "independent-corpus replication cleared the K=6 Bonferroni bar -- human review for promotion",
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


def _mlb_build(year: str) -> Optional[Dict[str, Any]]:
    source = IFR.mlb_savant_source_for_year(year)
    if not source.exists():
        return None
    cols = ["game_pk", "game_date", "at_bat_number", "pitch_number", "pitcher", "batter",
            "events", "description", "launch_speed", "home_team", "away_team", "inning_topbot"]
    pitch_df = pd.read_parquet(source, columns=cols)
    frame = T39B.build_mlb_pa_archetype_frame(pitch_df, ["BB_rate", "K_avoidance"])
    return {"frame": frame, "cluster": "pitcher", "corpus": "savant_full__%s_pa" % year, "kind": "logit",
            "archetype_members": T39B.mlb_team_archetype_members(), "entity_col": "team"}


def _fit_mlb(cand: GEN.Candidate, build: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if build is None:
        return None
    try:
        return IFR._fit_candidate(build, cand)  # noqa: SLF001 -- same fit runner discovery uses
    except Exception:  # noqa: BLE001 -- one candidate's fit failure isolates
        return None


def replicate(*, ledger_path: Optional[Path] = None, mlb_year: str = MLB_REPL_YEAR) -> List[Dict[str, Any]]:
    """Re-test the batch-2b provisional survivors on an independent corpus
    (MLB: a disjoint season) or record REPLICATION_BLOCKED (tennis: no
    disjoint corpus exists). Appends one ledger row per survivor and upserts
    the candidate_id -> latest-verdict summary file. Returns appended rows."""
    ledger_path = ledger_path or IFR.LEDGER_PATH
    existing = IFR._load_ledger(ledger_path)  # noqa: SLF001 -- same loader discovery uses
    survivors = _batch2b_survivors(existing)

    mlb_build = _mlb_build(mlb_year)
    out_rows: List[Dict[str, Any]] = []
    verdicts: Dict[str, Any] = {}

    for b0 in survivors:
        cand = _candidate_from_row(b0)
        if cand.entity_class is None and cand.template_id == "mlb_pa_attr_x_archetype":
            cand = GEN.Candidate(**{**cand.__dict__, "entity_class": _mlb_entity_class(cand.candidate_id)})

        if cand.template_id == "mlb_pa_attr_x_archetype":
            fit = _fit_mlb(cand, mlb_build)
            v = verdict_for(b0["effect"], fit)
            corpus = mlb_build["corpus"] if mlb_build else "unbuildable"
            note = "REPLICATION corpus=%s of batch2b candidate (discovery effect=%.6f p=%.4g n=%d)" % (
                corpus, b0["effect"], b0["p"], b0["n"])
        else:  # tennis_match_asof_self_cross -- no independent corpus available
            fit, v = None, "REPLICATION_BLOCKED"
            corpus = "unbuildable"
            note = TENNIS_BLOCKED_NOTE % b0["n"]

        row = {
            "candidate_id": cand.candidate_id, "template_id": cand.template_id, "sport": cand.sport,
            "atomic_unit": cand.atomic_unit, "outcome": cand.outcome,
            "attr_a": cand.attr_a, "attr_b": cand.attr_b, "term": "fa:fb",
            "k_declared": K_DECLARED, "cum_K": K_DECLARED, "verdict": v,
            "effect": round(fit["effect"], 6) if fit else None,
            "p": round(fit["p"], 6) if fit else None,
            "n": int(fit["n"]) if fit else 0,
            "alpha_fwer": round(ALPHA, 8), "corpus": corpus, "note": note,
            "edge_claimed": False, "computed_at": IFR._now(),  # noqa: SLF001
            "replication_of": b0["candidate_id"],
            "discovery_effect": b0["effect"], "discovery_p": b0["p"], "discovery_n": b0["n"],
        }
        if cand.entity_class is not None:
            row["entity_class"] = cand.entity_class
        append_jsonl_atomic(ledger_path, row)
        out_rows.append(row)
        verdicts[cand.candidate_id] = {"verdict": v, "corpus": corpus, "effect": row["effect"],
                                        "p": row["p"], "n": row["n"], "computed_at": row["computed_at"]}
        if v == "REPLICATED":
            _queue_promotion(row, b0)

    _upsert_verdicts(verdicts)
    return out_rows


def main() -> int:
    rows = replicate()
    if not rows:
        print("batch2b: no provisional survivors on record -- nothing to replicate")
        return 0
    for r in rows:
        print("%-72s %-32s effect=%s p=%s n=%d (discovery effect=%.4f p=%.4g n=%d)" % (
            r["candidate_id"][:72], r["verdict"],
            ("%.6f" % r["effect"]) if r["effect"] is not None else "--",
            ("%.4g" % r["p"]) if r["p"] is not None else "--", r["n"],
            r["discovery_effect"], r["discovery_p"], r["discovery_n"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["replicate", "verdict_for", "main", "TEMPLATE_IDS", "MLB_REPL_YEAR",
           "K_DECLARED", "ALPHA", "VERDICTS_PATH"]
