"""scripts.platformkit.omni.k_stage_b -- K stage-B family test + reserve
replication for K-NBA-1's escalations (S15.K3).

STEP 0 premise (2026-07-13): K-NBA-1's v1 sweep (k_sweep_nba) mined its 44
escalation_screened claims (27 distinct player-level cells) on the FULL box
store, including 2025-26 -- there is no clean, never-touched reserve left for
those escalations. This lane does not replicate them directly; it RE-MINES
each escalated player-level cell on the discovery slice only (2023-24 +
2024-25), pre-registers whichever discovery effects survive a fresh BH pass
+ the practical floor, and only THEN reads the 2025-26 reserve slice to grade
same-sign + nominal p<=0.05 replication. Reserve is read once, after every
pre-registration for this batch is already journaled -- never before.

Two-phase control flow enforces the ordering (not a convention, a fact about
what data exists in scope at each point):
  phase 1 -- discovery-only re-mine of all cells, BH within this batch,
             PRE-REGISTER survivors (lifecycle=family_pass). Reserve rows
             are never loaded during this phase.
  phase 2 -- reserve slice is sliced ONLY here, once, and only pre-registered
             candidates are re-tested against it. Verdict recorded via
             set_lifecycle on the prereg claim + a native_altitude verdict
             claim (ACCEPT=REPLICATED, REJECT=FAILED_REPLICATION).

Honest expectation: most pre-registered candidates FAIL replication on
reserve (winner's-curse attenuation from the original full-store mining) --
that is the norm, not a lane failure.

INVARIANTS: pandas/scipy + stdlib only. <=300 LOC. ASCII stdout. Never writes
data/registry/. No $/edge claims.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_k_stage_b.py -q
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

import pandas as pd

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_sweep_nba as ksn
from scripts.platformkit.omni import native_altitude as NA

_PREDS_DIR = pathlib.Path("data/omni/preds/k_stage_b_v1")
_LANE = "k_stage_b"
_ESCALATION_LIFECYCLE = "escalation_screened"

_META_STATEMENT = (
    "K sweeps must mine on discovery slices only (2023-24+2024-25 for the "
    "NBA box store); 2025-26 is reserve; v1 full-store escalations require "
    "re-mining before replication"
)


def ledger_reserve_discipline_meta(base_dir=None) -> str | None:
    """Ledger the S15.K3 meta claim once (idempotent: skips if its
    content-hashed claim_id is already in the ledger)."""
    scope = {"sport": "nba", "entity_type": "league", "entity_ids": [], "context": "reserve_discipline"}
    claim_id = cl.make_claim_id(_META_STATEMENT, scope)
    existing = set(cl.query(sport="nba", base_dir=base_dir)["claim_id"])
    if claim_id in existing:
        return None
    claim = {
        "statement": _META_STATEMENT, "type": "meta", "scope": scope,
        "topic": "reserve_discipline", "lifecycle": "accepted",
        "provenance": {"created_by_lane": _LANE},
        "review": {"judge": "fable", "one_line_rationale": "reserve contamination prevention"},
    }
    return cl.add_claim(claim, base_dir=base_dir)


def _escalated_player_cells(base_dir=None) -> list[dict]:
    """Every lifecycle=='escalation_screened' claim scoped to one player."""
    df = cl.query(sport="nba", lifecycle=_ESCALATION_LIFECYCLE, base_dir=base_dir)
    out = []
    for _, row in df.iterrows():
        scope = json.loads(row["scope_json"])
        if scope.get("entity_type") != "player":
            continue
        effect = json.loads(row["effect_json"])
        out.append({
            "parent_claim_id": row["claim_id"], "player_id": int(scope["entity_ids"][0]),
            "condition": scope.get("context"), "topic": row["topic"],
            "parent_delta": effect.get("delta"),
        })
    return out


def _write_cell_preds(df: pd.DataFrame, player_id: int, condition: str, slice_name: str, base_dir=None) -> None:
    """Row-level retention for one (player, condition, slice) cell -- computed
    on the player-filtered frame so the side masks align to it directly."""
    g = df[df["player_id"] == player_id].copy()
    side_a, side_b, label_a, label_b = ksn._condition_labels(g, condition)  # noqa: SLF001 -- reuse, not fork
    g["side"] = pd.NA
    g.loc[side_a, "side"] = label_a
    g.loc[side_b, "side"] = label_b
    g = g[g["side"].notna()][["player_id", "player_name", "game_id", "date", "side", ksn._STAT]]  # noqa: SLF001
    out_dir = (pathlib.Path(base_dir) / _PREDS_DIR.name) if base_dir is not None else _PREDS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    g.to_parquet(out_dir / f"{slice_name}_{player_id}_{condition}.parquet", index=False)


def _market_families_for(topic: str) -> list[str]:
    return ["props.minutes"] if "minutes" in topic else ["props.pts"]


def _prereg_claim(cell: dict, res: dict) -> dict:
    same_sign_expected = res["delta"] * cell["parent_delta"] >= 0
    statement = (
        f"NBA player {cell['player_id']} {ksn._STAT} delta under {cell['condition']}"  # noqa: SLF001
        " :: stage-B discovery re-mine"
    )
    scope = {"sport": "nba", "entity_type": "player", "entity_ids": [cell["player_id"]], "context": cell["condition"]}
    return {
        "statement": statement, "type": "effect", "scope": scope,
        "topic": cell["topic"], "lifecycle": "family_pass",
        "effect": {"verdict": "TESTED", "delta": res["delta"], "ci_low": res["ci_low"],
                   "ci_high": res["ci_high"], "n_a": res["n_a"], "n_b": res["n_b"], "stat": ksn._STAT},  # noqa: SLF001
        "evidence": {"expected_sign": "same_as_parent" if same_sign_expected else "opposite_of_parent",
                     "parent_delta": cell["parent_delta"], "discovery_delta": res["delta"],
                     "discovery_p_adj_bh": res["p_adj"], "discovery_n_a": res["n_a"], "discovery_n_b": res["n_b"]},
        "provenance": {"created_by_lane": _LANE},
        "links": {"parent_claims": [cell["parent_claim_id"]]},
    }


def run_stage_b(base_dir=None, source=None) -> dict[str, Any]:
    meta_id = ledger_reserve_discipline_meta(base_dir)
    cells = _escalated_player_cells(base_dir)

    df = ksn._load_sweep_frame(source)  # noqa: SLF001 -- reuse the same loader/columns k_sweep_nba uses
    discovery_df, _unused_reserve_ref = ksn.split_discovery_reserve(df)
    del _unused_reserve_ref  # phase 1 must never touch reserve rows

    # -- Phase 1: discovery-only re-mine + BH + pre-registration -------------
    remined: list[dict] = []
    for cell in cells:
        res = ksn.remine_player_cell(discovery_df, cell["player_id"], cell["condition"])
        if res is None or res["n_a"] < ksn.MIN_SIDE_N or res["n_b"] < ksn.MIN_SIDE_N:
            continue
        remined.append({**cell, **res})
        _write_cell_preds(discovery_df, cell["player_id"], cell["condition"], "discovery", base_dir)

    adj = ksn.bh_adjust([c["p"] for c in remined])
    for c, a in zip(remined, adj):
        c["p_adj"] = a

    preregistered: list[dict] = []
    for cell in remined:
        same_sign = cell["delta"] * cell["parent_delta"] >= 0
        if cell["p_adj"] < ksn.BH_ALPHA and abs(cell["delta"]) >= ksn.MIN_PRACTICAL_EFFECT and same_sign:
            claim = _prereg_claim(cell, cell)
            claim_id = cl.add_claim(claim, base_dir=base_dir)
            preregistered.append({**cell, "prereg_claim_id": claim_id})

    # -- Phase 2: reserve slice read ONLY now, only for pre-registered cells --
    _discovery_ref, reserve_df = ksn.split_discovery_reserve(df)
    del _discovery_ref

    replicated, failed = [], []
    for cand in preregistered:
        res_r = ksn.remine_player_cell(reserve_df, cand["player_id"], cand["condition"])
        _write_cell_preds(reserve_df, cand["player_id"], cand["condition"], "reserve", base_dir)
        is_replicated = bool(
            res_r is not None and res_r["n_a"] >= 2 and res_r["n_b"] >= 2
            and res_r["p"] <= 0.05 and res_r["delta"] * cand["delta"] >= 0
        )
        verdict = "ACCEPT" if is_replicated else "REJECT"
        lifecycle = "replicated" if is_replicated else "failed_replication"
        contract = NA.build_contract(
            signal_name=f"k_stage_b_player_{cand['player_id']}_{cand['condition']}", sport="nba",
            native_observable="shot_quality", metric="crps",
            baseline_model="discovery_slice_welch_split",
            market_families=_market_families_for(cand["topic"]), regime_scope="all", corpus="reserve_2025_26",
        )
        family = contract["market_families"][0]
        verdict_claim_ids = NA.record_verdicts(contract, {
            family: {"verdict": verdict, "delta": res_r["delta"] if res_r else None,
                      "ci_low": res_r["ci_low"] if res_r else None,
                      "ci_high": res_r["ci_high"] if res_r else None,
                      "n": (res_r["n_a"] + res_r["n_b"]) if res_r else None},
        }, base_dir=base_dir)
        cl.set_lifecycle(cand["prereg_claim_id"], lifecycle, review={
            "verdict_claim_id": verdict_claim_ids[0], "reserve_delta": res_r["delta"] if res_r else None,
            "reserve_p": res_r["p"] if res_r else None,
        }, base_dir=base_dir)
        (replicated if is_replicated else failed).append({**cand, "verdict_claim_id": verdict_claim_ids[0]})

    return {
        "meta_claim_id": meta_id,
        "escalated_player_cells": len(cells),
        "remined": len(remined),
        "preregistered": len(preregistered),
        "replicated": len(replicated),
        "failed_replication": len(failed),
        "replicated_claim_ids": [r["prereg_claim_id"] for r in replicated],
        "failed_claim_ids": [f["prereg_claim_id"] for f in failed],
    }


if __name__ == "__main__":
    out = run_stage_b()
    for k, v in out.items():
        print(f"[k_stage_b] {k}: {v}")


__all__ = ["run_stage_b", "ledger_reserve_discipline_meta"]
