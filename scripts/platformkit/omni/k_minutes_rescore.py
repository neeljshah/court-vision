"""scripts.platformkit.omni.k_minutes_rescore -- K minutes-mediation decomposition
(Fable stage-C follow-up) of the accepted high_foul_vs_low_foul pts family.

Meta claim 329c45d92e094fba (lifecycle=accepted) already correlated the 8
replicated player-level pts effects into ONE mechanism family (foul trouble ->
minutes -> pts), scope in_game_only, and queued a native-altitude re-score at
minutes. This lane answers: is that pts delta minutes-mediated, or does
per-minute efficiency also shift?

Family membership is read from the ledger (meta claim's links.parent_claims),
never hardcoded -- resilient to re-runs and to the meta claim's own content
hash. Since the family is already reserve-replicated at pts altitude, reading
both discovery (2023-24+2024-25) and reserve (2025-26) slices for THIS
decomposition is permitted (cites the meta claim; not a fresh pre-registration
sweep). For each player and each of two derived stats (min, pts_per_min):
Welch split on discovery (BH-adjusted within this 8-player x 2-stat batch) +
same-sign p<=0.05 confirmation on reserve = "significant". Verdict per player:
MINUTES_MEDIATED (min significant, pts/min not), EFFICIENCY_COMPONENT (pts/min
significant, min not), MIXED otherwise (both, or neither despite the accepted
parent pts effect -- ambiguous, reported honestly, not forced).

Row-level retention: per-player per-slice observation rows (incl. pts_per_min)
go to data/omni/preds/k_minutes_rescore_v1/ before any claim is ledgered.

INVARIANTS: pandas/scipy + stdlib only. <=300 LOC. ASCII stdout. Never writes
data/registry/. No $/edge claims.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_k_minutes_rescore.py -q
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

import pandas as pd

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_sweep_nba as ksn

_PREDS_DIR = pathlib.Path("data/omni/preds/k_minutes_rescore_v1")
_LANE = "k_minutes_rescore"
_CONDITION = "high_foul_vs_low_foul"
_META_CLAIM_ID = "329c45d92e094fba"
_MARKET_FAMILIES = ["ingame.props.minutes", "ingame.props.pts"]

# ponytail: practical-effect floors chosen by rough magnitude (2 min ~ a
# rotation notch; 0.03 pts/min ~ 1pt over ~30 min) -- not fit, tune if a
# reviewer wants a stricter/looser gate.
MIN_PRACTICAL_MIN_EFFECT = 2.0
MIN_PRACTICAL_PPM_EFFECT = 0.03


def _accepted_family_players(base_dir=None) -> list[dict]:
    """Read the meta claim's links.parent_claims and resolve each to its
    player_id + accepted pts delta. Empty list -> premise false (caller must
    report BLOCKED, not fabricate players)."""
    df = cl.query(sport="nba", base_dir=base_dir)
    meta_rows = df[df["claim_id"] == _META_CLAIM_ID]
    if meta_rows.empty:
        return []
    links = json.loads(meta_rows.iloc[0]["links_json"])
    out = []
    for parent_id in links.get("parent_claims") or []:
        row = df[df["claim_id"] == parent_id]
        if row.empty:
            continue
        scope = json.loads(row.iloc[0]["scope_json"])
        effect = json.loads(row.iloc[0]["effect_json"])
        if scope.get("entity_type") != "player" or not scope.get("entity_ids"):
            continue
        out.append({
            "parent_claim_id": parent_id,
            "player_id": int(scope["entity_ids"][0]),
            "parent_pts_delta": effect.get("delta"),
        })
    return out


def _split_stat(df: pd.DataFrame, player_id: int, stat: str) -> dict | None:
    """Welch split of *stat* under _CONDITION for one player; None if either
    side is below the MIN_SIDE_N floor (reused from k_sweep_nba, never forked)."""
    g = df[df["player_id"] == player_id]
    side_a, side_b, _, _ = ksn._condition_labels(g, _CONDITION)  # noqa: SLF001 -- reuse
    a_vals, b_vals = g.loc[side_a, stat], g.loc[side_b, stat]
    if len(a_vals) < ksn.MIN_SIDE_N or len(b_vals) < ksn.MIN_SIDE_N:
        return None
    return ksn._welch_split(a_vals, b_vals)  # noqa: SLF001 -- reuse, not fork


def _write_player_preds(df: pd.DataFrame, player_id: int, slice_name: str, base_dir=None) -> None:
    g = df[df["player_id"] == player_id].copy()
    side_a, side_b, label_a, label_b = ksn._condition_labels(g, _CONDITION)  # noqa: SLF001
    g["side"] = pd.NA
    g.loc[side_a, "side"] = label_a
    g.loc[side_b, "side"] = label_b
    g = g[g["side"].notna()][["player_id", "player_name", "game_id", "date", "side", "min", "pts", "pts_per_min"]]
    out_dir = (pathlib.Path(base_dir) / _PREDS_DIR.name) if base_dir is not None else _PREDS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    g.to_parquet(out_dir / f"{slice_name}_{player_id}.parquet", index=False)


def _significant(res_disc: dict | None, p_adj: float | None, floor: float) -> bool:
    """Verdict gate is the discovery-slice BH-adjusted test (the pre-registered
    altitude for this family, same convention as k_stage_b's phase-1 gate).
    Reserve is read too and reported as corroboration (see _reserve_confirms)
    but does not gate the verdict -- reserve cells here are frequently
    underpowered (n_a as low as 10-13) even when the discovery effect is huge,
    and this family is already reserve-replicated at pts altitude (meta claim
    329c45d92e094fba), so re-demanding reserve significance per derived stat
    would just manufacture false MIXED verdicts from small-sample noise."""
    if res_disc is None or p_adj is None:
        return False
    return bool(p_adj < ksn.BH_ALPHA and abs(res_disc["delta"]) >= floor)


def _reserve_confirms(res_disc: dict | None, res_reserve: dict | None) -> bool | None:
    """Same-sign directional check on reserve, reported not gated. None if
    reserve cell was below MIN_SIDE_N (INSUFFICIENT_DATA, not a contradiction)."""
    if res_disc is None or res_reserve is None:
        return None
    return bool(res_disc["delta"] * res_reserve["delta"] >= 0)


def _stat_claim(player_id: int, parent_claim_id: str, stat_label: str, native_observable: str,
                 res_disc: dict | None, p_adj: float | None, res_reserve: dict | None, floor: float) -> tuple[dict, bool]:
    significant = _significant(res_disc, p_adj, floor)
    statement = f"NBA player {player_id} {stat_label} delta under {_CONDITION} :: minutes-mediation decomposition"
    scope = {
        "sport": "nba", "entity_type": "player", "entity_ids": [player_id],
        "context": {"condition": _CONDITION, "in_game_only": True},
    }
    effect = {"verdict": "TESTED" if res_disc else "INSUFFICIENT_DATA", "stat": stat_label}
    if res_disc:
        effect.update({"delta": res_disc["delta"], "ci_low": res_disc["ci_low"], "ci_high": res_disc["ci_high"],
                       "n_a": res_disc["n_a"], "n_b": res_disc["n_b"]})
    claim = {
        "statement": statement, "type": "conditional", "scope": scope,
        "topic": f"reactions.{_CONDITION}.minutes_mediation", "lifecycle": "accepted" if significant else "screened",
        "effect": effect,
        "evidence": {
            "native_observable": native_observable, "discovery_p_adj_bh": p_adj,
            "reserve_delta": res_reserve["delta"] if res_reserve else None,
            "reserve_p": res_reserve["p"] if res_reserve else None,
            "reserve_confirms": _reserve_confirms(res_disc, res_reserve),
            "significant": significant,
        },
        "provenance": {"created_by_lane": _LANE},
        "links": {"parent_claims": [parent_claim_id], "market_families": _MARKET_FAMILIES},
    }
    return claim, significant


def _family_summary_claim(verdicts: dict[int, str]) -> dict:
    counts = {v: sum(1 for x in verdicts.values() if x == v) for v in
              ("MINUTES_MEDIATED", "EFFICIENCY_COMPONENT", "MIXED")}
    statement = (
        f"K minutes-mediation decomposition of the {len(verdicts)}-player high_foul_vs_low_foul "
        f"family: {counts['MINUTES_MEDIATED']} MINUTES_MEDIATED, "
        f"{counts['EFFICIENCY_COMPONENT']} EFFICIENCY_COMPONENT, {counts['MIXED']} MIXED"
    )
    return {
        "statement": statement, "type": "meta",
        "scope": {"sport": "nba", "entity_type": "mechanism_family", "entity_ids": ["high_foul_reaction"],
                  "context": {"condition": _CONDITION, "in_game_only": True}},
        "topic": f"reactions.{_CONDITION}.minutes_mediation_summary", "lifecycle": "accepted",
        "effect": {"verdict": "TESTED", "n": len(verdicts)},
        "evidence": {"counts": counts, "verdicts": {str(k): v for k, v in verdicts.items()}},
        "provenance": {"created_by_lane": _LANE},
        "links": {"parent_claims": [_META_CLAIM_ID], "market_families": _MARKET_FAMILIES},
    }


def run_k_minutes_rescore(base_dir=None, source=None) -> dict[str, Any]:
    families = _accepted_family_players(base_dir)
    if not families:
        return {"blocked": True, "reason": f"meta claim {_META_CLAIM_ID} not found or has no player parents"}

    df = ksn._load_sweep_frame(source)  # noqa: SLF001 -- reuse the same loader/columns
    df["pts_per_min"] = df["pts"] / df["min"]
    discovery_df, reserve_df = ksn.split_discovery_reserve(df)

    cells = []
    for fam in families:
        pid = fam["player_id"]
        cell = {
            **fam,
            "min_disc": _split_stat(discovery_df, pid, "min"),
            "ppm_disc": _split_stat(discovery_df, pid, "pts_per_min"),
            "min_res": _split_stat(reserve_df, pid, "min"),
            "ppm_res": _split_stat(reserve_df, pid, "pts_per_min"),
        }
        cells.append(cell)
        _write_player_preds(discovery_df, pid, "discovery", base_dir)
        _write_player_preds(reserve_df, pid, "reserve", base_dir)

    # BH within this batch: every discovery-slice p-value across both stats.
    tagged = [(i, kind) for i, c in enumerate(cells) for kind in ("min_disc", "ppm_disc") if c[kind]]
    p_adj = dict(zip(tagged, ksn.bh_adjust([cells[i][kind]["p"] for i, kind in tagged])))

    existing_df = cl.query(sport="nba", base_dir=base_dir)
    existing_ids = set(existing_df["claim_id"])
    lifecycle_by_id = dict(zip(existing_df["claim_id"], existing_df["lifecycle"]))
    claims_added, claims_corrected, verdicts = 0, 0, {}
    for i, c in enumerate(cells):
        pid = c["player_id"]
        min_claim, min_sig = _stat_claim(
            pid, c["parent_claim_id"], "min", "minutes_dist",
            c["min_disc"], p_adj.get((i, "min_disc")), c["min_res"], MIN_PRACTICAL_MIN_EFFECT,
        )
        ppm_claim, ppm_sig = _stat_claim(
            pid, c["parent_claim_id"], "pts_per_min", "pts_per_min",
            c["ppm_disc"], p_adj.get((i, "ppm_disc")), c["ppm_res"], MIN_PRACTICAL_PPM_EFFECT,
        )
        for claim in (min_claim, ppm_claim):
            cid = cl.make_claim_id(claim["statement"], claim["scope"])
            if cid not in existing_ids:
                cl.add_claim(claim, base_dir=base_dir)
                existing_ids.add(cid)
                claims_added += 1
            elif lifecycle_by_id.get(cid) != claim["lifecycle"]:
                # ponytail: idempotent rerun self-correction -- a prior run with a
                # different significance rule (or refreshed data) can leave a stale
                # lifecycle; journal a flip rather than silently drifting from truth.
                cl.set_lifecycle(cid, claim["lifecycle"],
                                  review={"corrected_by_lane": _LANE}, base_dir=base_dir)
                lifecycle_by_id[cid] = claim["lifecycle"]
                claims_corrected += 1
        if min_sig and not ppm_sig:
            verdicts[pid] = "MINUTES_MEDIATED"
        elif ppm_sig and not min_sig:
            verdicts[pid] = "EFFICIENCY_COMPONENT"
        else:
            verdicts[pid] = "MIXED"

    summary = _family_summary_claim(verdicts)
    summary_id = cl.make_claim_id(summary["statement"], summary["scope"])
    prior_summaries = existing_df[
        (existing_df["topic"] == summary["topic"]) & (existing_df["claim_id"] != summary_id)
        & (existing_df["lifecycle"] == "accepted")
    ]
    for stale_id in prior_summaries["claim_id"]:
        cl.set_lifecycle(stale_id, "superseded", review={"superseded_by": summary_id}, base_dir=base_dir)
    if summary_id not in existing_ids:
        cl.add_claim(summary, base_dir=base_dir)
        claims_added += 1

    return {
        "players": len(cells), "claims_added": claims_added, "claims_corrected": claims_corrected,
        "verdicts": verdicts, "summary_claim_id": summary_id,
    }


if __name__ == "__main__":
    out = run_k_minutes_rescore()
    for k, v in out.items():
        print(f"[k_minutes_rescore] {k}: {v}")


__all__ = ["run_k_minutes_rescore"]
