"""scripts.platformkit.omni.k_stage_b -- K stage-B family test + reserve
replication, generalized to ALL lifecycle='escalation_screened' claims across
every K-sweep lane (S15.K3 follow-up, 2026-07-13: was NBA-reactions-only v1).

STEP 0 premise (2026-07-13): 452 escalation_screened claims span 5 lanes
(k_sweep_nba_v1 reactions, k_sweep_opponent_v1 opp_def_tercile,
k_sweep_synergy_v1 with_without/star_sits, k_sweep_physical_v1
conditioning_trend, k_sweep_playprofile_v1 zone_efg_rim_stability). Same
two-phase contract as v1 (re-mine discovery -> BH -> pre-register -> read
reserve once -> verdict), generalized over a lane dispatch map. Re-mine reuses
each sweep's own split/test primitives (never forks the math); a lane
lacking a cell-granular export gets a thin wrapper below using the same math.
Unknown lane/entity_type/condition -> ledgered NOT_REPLICABLE with a reason,
never guessed.

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
from scipy import stats as sps

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_sweep_nba as ksn
from scripts.platformkit.omni import k_sweep_opponent as kso
from scripts.platformkit.omni import k_sweep_physical as ksp
from scripts.platformkit.omni import k_sweep_playprofile as kspp
from scripts.platformkit.omni import k_sweep_synergy as kss
from scripts.platformkit.omni import native_altitude as NA

_PREDS_DIR = pathlib.Path("data/omni/preds/k_stage_b_v2")
_LANE = "k_stage_b"
_ESCALATION_LIFECYCLE = "escalation_screened"
_WELCH_LANES = ("k_sweep_nba_v1", "k_sweep_opponent_v1", "k_sweep_synergy_v1")
# physical/playprofile escalations were already discovery-only; these are the
# 2025-26 windows re-mined for their reserve check (nba/opponent/synergy share
# ksn.RESERVE_CUTOVER via split_discovery_reserve instead).
_PHYS_RESERVE = (ksn.RESERVE_CUTOVER, "2099-01-01")
_PROF_RESERVE = ("season_2025_26", "last20_2025_26")

_KNOWN_CONDITIONS = {
    ("k_sweep_nba_v1", "player"): set(ksn.CONDITIONS),
    ("k_sweep_opponent_v1", "player"): {"opp_def_tercile"},
    ("k_sweep_synergy_v1", "player_pair"): {"with_without_teammate"},
    ("k_sweep_synergy_v1", "player"): {"star_sits"},
    ("k_sweep_physical_v1", "player"): {"conditioning_trend"},
    ("k_sweep_playprofile_v1", "player"): {"zone_efg_rim_stability"},
}
_MIN_PRACTICAL = {
    "k_sweep_nba_v1": ksn.MIN_PRACTICAL_EFFECT, "k_sweep_opponent_v1": ksn.MIN_PRACTICAL_EFFECT,
    "k_sweep_synergy_v1": kss.MIN_PRACTICAL_EFFECT, "k_sweep_physical_v1": ksp.MIN_PRACTICAL_SLOPE_MIN,
    "k_sweep_playprofile_v1": kspp.MIN_PRACTICAL_EFFECT_EFG,
}
_META_STATEMENT = (
    "K sweeps must mine on discovery slices only (2023-24+2024-25 for the "
    "NBA box store); 2025-26 is reserve; escalation_screened claims from any "
    "K-sweep lane require re-mining before replication (generalized 07-13)"
)

def ledger_reserve_discipline_meta(base_dir=None) -> str | None:
    """Ledger the S15.K3 meta claim once (idempotent by content-hash id)."""
    scope = {"sport": "nba", "entity_type": "league", "entity_ids": [], "context": "reserve_discipline"}
    claim_id = cl.make_claim_id(_META_STATEMENT, scope)
    if claim_id in set(cl.query(sport="nba", base_dir=base_dir)["claim_id"]):
        return None
    claim = {
        "statement": _META_STATEMENT, "type": "meta", "scope": scope,
        "topic": "reserve_discipline", "lifecycle": "accepted",
        "provenance": {"created_by_lane": _LANE},
        "review": {"judge": "fable", "one_line_rationale": "reserve contamination prevention"},
    }
    return cl.add_claim(claim, base_dir=base_dir)

def _escalated_cells(base_dir=None) -> list[dict]:
    """Every lifecycle=='escalation_screened' claim, any lane/entity_type."""
    df = cl.query(sport="nba", lifecycle=_ESCALATION_LIFECYCLE, base_dir=base_dir)
    out = []
    for _, row in df.iterrows():
        scope, effect, prov = (json.loads(row[f"{k}_json"]) for k in ("scope", "effect", "provenance"))
        out.append({
            "parent_claim_id": row["claim_id"], "lane": prov.get("created_by_lane"),
            "entity_type": scope.get("entity_type"), "entity_ids": scope.get("entity_ids"),
            "condition": scope.get("context"), "stat": scope.get("stat"), "topic": row["topic"],
            "parent_delta": effect.get("delta") or effect.get("slope_min_per_month"),
        })
    return out

def _is_known(cell: dict) -> bool:
    key = (cell["lane"], cell["entity_type"])
    return key in _KNOWN_CONDITIONS and cell["condition"] in _KNOWN_CONDITIONS[key]

def _load_frames(lane: str, sources: dict | None, base_dir=None):
    """(discovery_df, reserve_df) for *lane*, reusing its own loader/split."""
    src = (sources or {}).get(lane)
    if lane == "k_sweep_nba_v1":
        return ksn.split_discovery_reserve(ksn._load_sweep_frame(src))  # noqa: SLF001
    if lane == "k_sweep_opponent_v1":
        tier_src = (sources or {}).get(lane + "_tier")
        return ksn.split_discovery_reserve(kso._load_sweep_frame(src, tier_src))  # noqa: SLF001
    if lane == "k_sweep_synergy_v1":
        disc, res = kss.split_discovery_reserve(kss._load_sweep_frame(src))  # noqa: SLF001
        return disc[disc["min"] > 0].copy(), res[res["min"] > 0].copy()
    if lane == "k_sweep_physical_v1":
        adv = ksp._load_adv_stats(src)  # noqa: SLF001
        adv["game_date"] = pd.to_datetime(adv["game_date"])
        return adv, adv  # phase distinguished by the date window passed to the remine fn
    if lane == "k_sweep_playprofile_v1":
        profiles = kspp._load_profiles(src)  # noqa: SLF001
        return profiles, profiles  # phase distinguished by the window names used
    raise ValueError(f"no frame loader for lane {lane!r}")

# -- Thin per-cell re-mine wrappers: reuse each lane's split/test primitives.
def _remine_opponent(df: pd.DataFrame, player_id: int, stat: str) -> dict | None:
    g = df[df["player_id"] == player_id]
    side_a, side_b, _, _ = kso._condition_labels(g)  # noqa: SLF001
    return ksn._welch_split(g.loc[side_a, stat], g.loc[side_b, stat])  # noqa: SLF001

def _remine_star_sits(played: pd.DataFrame, player_id: int) -> dict | None:
    """Recompute each team-season's star (top mean pts, k_sweep_synergy's own
    rule) then split *player_id*'s pts on the star's absence; best (largest-n)
    cell wins if the player switched teams mid-window."""
    means = played.groupby(["team", "season", "player_id"])[kss._STAT].mean()  # noqa: SLF001
    best = None
    for team, season, star_id in means.groupby(level=[0, 1]).idxmax().values:
        if star_id == player_id:
            continue
        ts = played[(played["team"] == team) & (played["season"] == season)]
        g = ts[ts["player_id"] == player_id]
        if g.empty:
            continue
        absent = set(ts["game_id"]) - set(ts.loc[ts["player_id"] == star_id, "game_id"])
        sit, play = g.loc[g["game_id"].isin(absent), kss._STAT], g.loc[~g["game_id"].isin(absent), kss._STAT]  # noqa: SLF001
        if len(sit) < kss.MIN_ABSENCE_N or len(play) < kss.MIN_ABSENCE_N:
            continue
        res = ksn._welch_split(sit, play)  # noqa: SLF001
        if res and (best is None or res["n_a"] + res["n_b"] > best["n_a"] + best["n_b"]):
            best = res
    return best

def _remine_physical(adv: pd.DataFrame, player_id: int, start: str, end: str) -> dict | None:
    season = adv[(adv["game_date"] >= start) & (adv["game_date"] <= end) & (adv["player_id"] == player_id)]
    if len(season) < ksp.MIN_SEASON_GAMES:
        return None
    monthly = season.assign(month=season["game_date"].dt.to_period("M")).groupby("month")["minutes"].mean()
    if len(monthly) < ksp.MIN_MONTHS:
        return None
    slope, _i, _r, p, _se = sps.linregress(range(len(monthly)), monthly.sort_index().values)
    return {"delta": float(slope), "p": float(p), "n_a": len(season), "n_b": len(monthly)}

def _remine_playprofile(profiles: pd.DataFrame, player_id: int, baseline_window: str, recent_window: str) -> dict | None:
    attr = kspp._STABILITY_ATTR  # noqa: SLF001
    b = profiles[(profiles["entity_id"] == player_id) & (profiles["window"] == baseline_window) & (profiles["attribute"] == attr)]
    r = profiles[(profiles["entity_id"] == player_id) & (profiles["window"] == recent_window) & (profiles["attribute"] == attr)]
    if b.empty or r.empty:
        return None
    return kspp._two_prop_z(b.iloc[0].raw_value, b.iloc[0].n, r.iloc[0].raw_value, r.iloc[0].n)  # noqa: SLF001

def _remine_cell(cell: dict, df, phase: str) -> dict | None:
    lane, cond, etype, ids = cell["lane"], cell["condition"], cell["entity_type"], cell["entity_ids"]
    if lane == "k_sweep_nba_v1":
        return ksn.remine_player_cell(df, ids[0], cond)
    if lane == "k_sweep_opponent_v1":
        return _remine_opponent(df, ids[0], cell["stat"] or "pts")
    if lane == "k_sweep_synergy_v1" and etype == "player_pair":
        res, _with_b, _a_games = kss._with_without_split(df, ids[0], ids[1])  # noqa: SLF001
        return res
    if lane == "k_sweep_synergy_v1" and etype == "player":
        return _remine_star_sits(df, ids[0])
    if lane == "k_sweep_physical_v1":
        start, end = (ksp._SEASON_START, ksp._SEASON_END) if phase == "discovery" else _PHYS_RESERVE  # noqa: SLF001
        return _remine_physical(df, ids[0], start, end)
    if lane == "k_sweep_playprofile_v1":
        base_w, rec_w = (kspp._BASELINE_WINDOW, kspp._RECENT_WINDOW) if phase == "discovery" else _PROF_RESERVE  # noqa: SLF001
        return _remine_playprofile(df, ids[0], base_w, rec_w)
    return None

def _sufficient(lane: str, res: dict | None, floor: int) -> bool:
    if res is None:
        return False
    return res["n_a"] >= floor and res["n_b"] >= floor if lane in _WELCH_LANES else True

def _market_family(cell: dict) -> str:
    lane, cond = cell["lane"], cell["condition"]
    if lane == "k_sweep_nba_v1":
        return "ingame.props.pts" if cond == "high_foul_vs_low_foul" else "props.pts"
    if lane == "k_sweep_opponent_v1":
        return "props.minutes" if cell.get("stat") == "min" else "props.pts"
    if lane == "k_sweep_physical_v1":
        return "props.minutes"
    return "props.pts"  # synergy (teammate availability = injury-reportable) + playprofile

def _cell_claim(cell: dict, lifecycle: str, verdict: str, reason: str | None = None) -> dict:
    scope = {"sport": "nba", "entity_type": cell["entity_type"] or "unknown",
              "entity_ids": cell["entity_ids"] or [], "context": cell["condition"]}
    if cell.get("stat"):
        scope["stat"] = cell["stat"]
    tag = "NOT_REPLICABLE" if reason else "re-mine"
    statement = f"NBA {scope['entity_type']} {scope['entity_ids']} {cell['condition']} :: stage-B {tag}"
    effect = {"verdict": verdict}
    evidence = {"reason": reason} if reason else {
        "expected_sign": "same_as_parent" if cell["delta"] * (cell.get("parent_delta") or 0.0) >= 0 else "opposite_of_parent",
        "parent_delta": cell.get("parent_delta"), "discovery_delta": cell["delta"],
        "discovery_p_adj_bh": cell.get("p_adj"), "discovery_n_a": cell.get("n_a"), "discovery_n_b": cell.get("n_b"),
    }
    if not reason:
        effect.update(delta=cell["delta"], n_a=cell["n_a"], n_b=cell["n_b"])
    return {
        "statement": statement, "type": "effect", "scope": scope, "topic": cell["topic"], "lifecycle": lifecycle,
        "effect": effect, "evidence": evidence,
        "provenance": {"created_by_lane": _LANE, "source_lane": cell["lane"]},
        "links": {"parent_claims": [cell["parent_claim_id"]]},
    }

def _retain(records: list[dict], name: str, base_dir=None) -> None:
    if not records:
        return
    out_dir = (pathlib.Path(base_dir) / _PREDS_DIR.name) if base_dir is not None else _PREDS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    cols = ["parent_claim_id", "lane", "entity_type", "condition", "delta", "p", "n_a", "n_b"]
    pd.DataFrame(records)[cols].to_parquet(out_dir / f"{name}.parquet", index=False)

def run_stage_b(base_dir=None, source=None, sources: dict | None = None) -> dict[str, Any]:
    sources = dict(sources or {})
    if source is not None:
        sources.setdefault("k_sweep_nba_v1", source)  # back-compat with v1's single-lane callers

    meta_id = ledger_reserve_discipline_meta(base_dir)
    cells = _escalated_cells(base_dir)

    known, not_replicable = [], []
    for cell in cells:
        if _is_known(cell):
            known.append(cell)
        else:
            reason = f"lane={cell['lane']!r} entity_type={cell['entity_type']!r} condition={cell['condition']!r} not in dispatch map"
            not_replicable.append(_cell_claim(cell, "not_replicable", "NOT_REPLICABLE", reason))
    cl.add_claims_batch(not_replicable, base_dir=base_dir)

    # -- Phase 1: discovery-only re-mine + BH + pre-registration, per lane --
    frames: dict[str, tuple] = {}
    remined: list[dict] = []
    by_lane_screened: dict[str, int] = {}
    for cell in known:
        by_lane_screened[cell["lane"]] = by_lane_screened.get(cell["lane"], 0) + 1
        frames.setdefault(cell["lane"], _load_frames(cell["lane"], sources, base_dir))
        discovery_df, _reserve_ref = frames[cell["lane"]]
        del _reserve_ref  # phase 1 must never touch reserve rows
        res = _remine_cell(cell, discovery_df, "discovery")
        if _sufficient(cell["lane"], res, ksn.MIN_SIDE_N):
            remined.append({**cell, **res})

    for c, a in zip(remined, ksn.bh_adjust([c["p"] for c in remined])):
        c["p_adj"] = a

    prereg_claims, preregistered = [], []
    for cell in remined:
        same_sign = cell["delta"] * (cell["parent_delta"] or 0.0) >= 0
        if cell["p_adj"] < ksn.BH_ALPHA and abs(cell["delta"]) >= _MIN_PRACTICAL[cell["lane"]] and same_sign:
            claim = _cell_claim(cell, "family_pass", "TESTED")
            prereg_claims.append(claim)
            preregistered.append({**cell, "prereg_claim_id": cl.make_claim_id(claim["statement"], claim["scope"])})
    cl.add_claims_batch(prereg_claims, base_dir=base_dir)
    _retain(remined, "discovery_cells", base_dir)

    # -- Phase 2: reserve slice read ONLY now, only for pre-registered cells --
    replicated, failed, reserve_rows = [], [], []
    by_lane_result: dict[str, dict] = {}
    for cand in preregistered:
        _discovery_ref, reserve_df = frames[cand["lane"]]
        del _discovery_ref
        res_r = _remine_cell(cand, reserve_df, "reserve")
        is_replicated = bool(_sufficient(cand["lane"], res_r, 2) and res_r["p"] <= 0.05 and res_r["delta"] * cand["delta"] >= 0)
        verdict, lifecycle = ("ACCEPT", "replicated") if is_replicated else ("REJECT", "failed_replication")
        native_observable = "minutes_dist" if _market_family(cand) == "props.minutes" else "shot_quality"
        contract = NA.build_contract(
            signal_name=f"k_stage_b_{cand['entity_type']}_{cand['entity_ids']}_{cand['condition']}", sport="nba",
            native_observable=native_observable, metric="crps", baseline_model="discovery_slice_welch_split",
            market_families=[_market_family(cand)], regime_scope="all", corpus="reserve_2025_26",
        )
        verdict_claim_ids = NA.record_verdicts(contract, {
            contract["market_families"][0]: {"verdict": verdict, "delta": res_r["delta"] if res_r else None,
                                               "n": (res_r["n_a"] + res_r["n_b"]) if res_r else None},
        }, base_dir=base_dir)
        cl.set_lifecycle(cand["prereg_claim_id"], lifecycle, review={
            "verdict_claim_id": verdict_claim_ids[0], "reserve_delta": res_r["delta"] if res_r else None,
            "reserve_p": res_r["p"] if res_r else None,
        }, base_dir=base_dir)
        (replicated if is_replicated else failed).append({**cand, "verdict_claim_id": verdict_claim_ids[0]})
        lane_stat = by_lane_result.setdefault(cand["lane"], {"replicated": 0, "failed": 0})
        lane_stat["replicated" if is_replicated else "failed"] += 1
        reserve_rows.append({"parent_claim_id": cand["parent_claim_id"], "lane": cand["lane"],
                              "entity_type": cand["entity_type"], "condition": cand["condition"],
                              "delta": res_r["delta"] if res_r else None, "p": res_r["p"] if res_r else None,
                              "n_a": res_r["n_a"] if res_r else None, "n_b": res_r["n_b"] if res_r else None})
    _retain(reserve_rows, "reserve_cells", base_dir)

    return {
        "meta_claim_id": meta_id,
        "escalated_total": len(cells), "escalated_known": len(known), "escalated_not_replicable": len(not_replicable),
        "screened_by_lane": by_lane_screened,
        "remined": len(remined), "preregistered": len(preregistered),
        "replicated": len(replicated), "failed_replication": len(failed),
        "replicated_by_lane": {k: v["replicated"] for k, v in by_lane_result.items()},
        "failed_by_lane": {k: v["failed"] for k, v in by_lane_result.items()},
        "replicated_claim_ids": [r["prereg_claim_id"] for r in replicated],
        "failed_claim_ids": [f["prereg_claim_id"] for f in failed],
    }


if __name__ == "__main__":
    out = run_stage_b()
    for k, v in out.items():
        print(f"[k_stage_b] {k}: {v}")


__all__ = ["run_stage_b", "ledger_reserve_discipline_meta"]
