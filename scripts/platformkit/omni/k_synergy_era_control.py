"""scripts.platformkit.omni.k_synergy_era_control -- era-control test for the
18 held with_without_teammate / star_sits synergy cells (S15.K3 follow-up to
meta claim da228ff5dc0e31d7, 2026-07-14).

STEP 0 premise (verified this run against data/omni/claims/journal.jsonl):
exactly 18 claims are lifecycle in {replicated, family_pass}, scope.context in
{with_without_teammate, star_sits}, provenance.created_by_lane == 'k_stage_b'
(14 pair cells at 'replicated', 4 star_sits cells at 'family_pass' -- the 4
star_sits ones were held at family_pass alongside the 14, per meta
da228ff5dc0e31d7's review notes on each). That meta claim names the confound:
game-grain absence splits can proxy a ROSTER-ERA change (trade, long injury)
rather than teammate synergy.

Era control (operational proxy, per meta's own remediation ask): restrict
each with/without comparison to (a) team-seasons where BOTH players in the
pair actually shared a roster, and (b) within those team-seasons, "without"
games that fall in a SHORT absence window -- a run of <=MAX_ABSENCE_GAP
consecutive team-games where the other player is off the roster, bounded on
BOTH sides by games where they ARE on the roster. A run open at either
boundary (can't confirm a return -- or never returns, i.e. a trade/retirement)
is NOT short: those games are dropped, never counted as "without". A pair/
player with zero qualifying short-window games after this filter is honestly
NOT_TESTABLE_ERA_CONTROL -- the effect is inseparable from era with this
store's grain, not evidence for or against synergy.

Same math as k_sweep_synergy/k_stage_b, never forked: reuses
k_sweep_nba._welch_split + bh_adjust, k_sweep_synergy's discovery/reserve
split and MIN_ABSENCE_N/MIN_PRACTICAL_EFFECT floors. Two-phase contract
identical to k_stage_b: discovery-only era-controlled re-estimate -> BH within
this 18-cell batch -> pre-register survivors (family_pass) -> reserve
(2025-26) re-read ONLY for survivors, same era control -> accepted/rejected.
Non-survivors and NOT_TESTABLE cells never touch the reserve slice.

INVARIANTS: pandas/scipy + stdlib only. <=300 LOC. ASCII stdout. Never writes
data/registry/. No $/edge claims -- these are calibration mechanism claims.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_k_synergy_era_control.py -q
"""
from __future__ import annotations

import json
import pathlib

import pandas as pd

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_sweep_nba as ksn
from scripts.platformkit.omni import k_sweep_synergy as kss

_PREDS_DIR = pathlib.Path("data/omni/preds/k_synergy_era_v1")
_LANE = "k_synergy_era_control"
_HELD_META_CLAIM_ID = "da228ff5dc0e31d7"  # verified present in journal.jsonl at STEP 0
MAX_ABSENCE_GAP = 15  # team-games; short = injury/rest-night, not an era shift
_CONDITIONS = ("with_without_teammate", "star_sits")


def _short_absent_games(sched_ids: list, present_ids: set, max_gap: int = MAX_ABSENCE_GAP) -> set:
    """game_ids inside a bounded (both edges present) absent run of length
    <= max_gap. Boundary-touching runs (can't confirm the far edge) are
    treated as era, never short -- conservative by construction."""
    n = len(sched_ids)
    out: set = set()
    i = 0
    while i < n:
        if sched_ids[i] in present_ids:
            i += 1
            continue
        j = i
        while j < n and sched_ids[j] not in present_ids:
            j += 1
        if i > 0 and j < n and (j - i) <= max_gap:
            out.update(sched_ids[i:j])
        i = j
    return out


def era_control_pair(played: pd.DataFrame, a: int, b: int) -> dict | None:
    """Welch split of a's pts with/without b, restricted to team-seasons
    where both actually rostered together and to short bounded absence
    windows on the "without" side. None if no such window exists."""
    a_rows = played[played["player_id"] == a]
    b_rows = played[played["player_id"] == b]
    shared_ts = set(zip(a_rows["team"], a_rows["season"])) & set(zip(b_rows["team"], b_rows["season"]))
    if not shared_ts:
        return None
    with_ids: set = set()
    without_ids: set = set()
    for team, season in shared_ts:
        ts_mask = (played["team"] == team) & (played["season"] == season)
        sched = played.loc[ts_mask].drop_duplicates("game_id").sort_values("date")["game_id"].tolist()
        b_present = set(b_rows.loc[(b_rows["team"] == team) & (b_rows["season"] == season), "game_id"])
        short_absent = _short_absent_games(sched, b_present)
        a_ts = a_rows[(a_rows["team"] == team) & (a_rows["season"] == season)]
        with_ids.update(a_ts.loc[a_ts["game_id"].isin(b_present), "game_id"])
        without_ids.update(a_ts.loc[a_ts["game_id"].isin(short_absent), "game_id"])
    if not without_ids or not with_ids:
        return None
    with_vals = a_rows.loc[a_rows["game_id"].isin(with_ids), "pts"]
    without_vals = a_rows.loc[a_rows["game_id"].isin(without_ids), "pts"]
    return ksn._welch_split(with_vals, without_vals)


def era_control_star(played: pd.DataFrame, player_id: int) -> dict | None:
    """Same short-window control applied to star_sits: for each team-season
    the player shared with that season's star (kss's own top-mean-pts rule,
    never re-derived), keep only sit-games inside a short bounded absence
    run; best (largest-n) team-season wins, like k_stage_b's own re-mine."""
    means = played.groupby(["team", "season", "player_id"])["pts"].mean()
    stars = means.groupby(level=[0, 1]).idxmax()
    best = None
    for team, season, star_id in stars.values:
        if star_id == player_id:
            continue
        ts_rows = played[(played["team"] == team) & (played["season"] == season)]
        p_rows = ts_rows[ts_rows["player_id"] == player_id]
        if p_rows.empty:
            continue
        sched = ts_rows.drop_duplicates("game_id").sort_values("date")["game_id"].tolist()
        star_present = set(ts_rows.loc[ts_rows["player_id"] == star_id, "game_id"])
        short_absent = _short_absent_games(sched, star_present)
        sit_vals = p_rows.loc[p_rows["game_id"].isin(short_absent), "pts"]
        play_vals = p_rows.loc[p_rows["game_id"].isin(star_present), "pts"]
        if len(sit_vals) < kss.MIN_ABSENCE_N or len(play_vals) < kss.MIN_ABSENCE_N:
            continue
        res = ksn._welch_split(sit_vals, play_vals)
        if res and (best is None or res["n_a"] + res["n_b"] > best["n_a"] + best["n_b"]):
            best = res
    return best


def _held_cells(base_dir=None) -> list[dict]:
    """The 18 held cells: lifecycle in {replicated, family_pass}, context in
    {with_without_teammate, star_sits}, provenance.created_by_lane == 'k_stage_b'."""
    out: list[dict] = []
    for lc in ("replicated", "family_pass"):
        df = cl.query(sport="nba", lifecycle=lc, base_dir=base_dir)
        for _, row in df.iterrows():
            scope = json.loads(row["scope_json"])
            prov = json.loads(row["provenance_json"])
            effect = json.loads(row["effect_json"])
            if prov.get("created_by_lane") != "k_stage_b" or scope.get("context") not in _CONDITIONS:
                continue
            out.append({
                "claim_id": row["claim_id"], "condition": scope["context"],
                "entity_ids": scope.get("entity_ids") or [], "parent_delta": effect.get("delta"),
            })
    return out


def _remine(cell: dict, df: pd.DataFrame) -> dict | None:
    ids = cell["entity_ids"]
    if cell["condition"] == "with_without_teammate":
        return era_control_pair(df, ids[0], ids[1])
    return era_control_star(df, ids[0])


def _cell_claim(cell: dict, lifecycle: str, verdict: str, res: dict | None, reason: str | None,
                era_controlled: bool = False) -> dict:
    scope = {"sport": "nba", "entity_type": "player_pair" if cell["condition"] == "with_without_teammate" else "player",
              "entity_ids": cell["entity_ids"], "context": {"condition": cell["condition"]}}
    if era_controlled:
        scope["context"]["era_controlled"] = True
        scope["market_families"] = ["props.pts"]
    statement = f"NBA {cell['condition']} {cell['entity_ids']} era-controlled re-estimate :: {verdict}"
    effect = {"verdict": verdict}
    evidence = {"reason": reason} if reason else {
        "delta": res["delta"], "p": res["p"], "n_a": res["n_a"], "n_b": res["n_b"],
        "parent_delta": cell["parent_delta"], "max_absence_gap": MAX_ABSENCE_GAP,
    }
    links = {"parent_claims": [cell["claim_id"]]}
    if lifecycle == "rejected" and reason == "confound_explained":
        links["parent_claims"].append(_HELD_META_CLAIM_ID)
    return {
        "statement": statement, "type": "negative" if lifecycle == "rejected" else
        ("effect" if lifecycle == "accepted" else "meta"),
        "scope": scope, "topic": f"synergy.era_control.{cell['condition']}", "lifecycle": lifecycle,
        "effect": effect, "evidence": evidence,
        "provenance": {"created_by_lane": _LANE}, "links": links,
    }


def _retain(rows: list[dict], name: str, base_dir=None) -> None:
    if not rows:
        return
    out_dir = (pathlib.Path(base_dir) / _PREDS_DIR.name) if base_dir is not None else _PREDS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(out_dir / f"{name}.parquet", index=False)


def run_era_control(base_dir=None, source=None) -> dict:
    disc, res_slice = kss.split_discovery_reserve(kss._load_sweep_frame(source))  # noqa: SLF001
    disc = disc[disc["min"] > 0].copy()
    res_slice = res_slice[res_slice["min"] > 0].copy()

    cells = _held_cells(base_dir)
    not_testable, remined, all_rows = [], [], []
    for cell in cells:
        res = _remine(cell, disc)
        if res is None:
            claim = _cell_claim(cell, "screened", "NOT_TESTABLE_ERA_CONTROL", None,
                                 "no team-games in a short (<=15) bounded absence window; "
                                 "effect inseparable from roster era at this store's grain")
            cl.add_claim(claim, base_dir=base_dir)
            cl.set_lifecycle(cell["claim_id"], "screened",
                              review={"era_control_reason": "NOT_TESTABLE_ERA_CONTROL"}, base_dir=base_dir)
            not_testable.append(cell["claim_id"])
        else:
            remined.append({**cell, **res})
        all_rows.append({"claim_id": cell["claim_id"], "condition": cell["condition"],
                          "entity_ids": str(cell["entity_ids"]), "phase": "discovery",
                          "delta": res["delta"] if res else None, "p": res["p"] if res else None,
                          "n_a": res["n_a"] if res else None, "n_b": res["n_b"] if res else None})
    _retain(all_rows, "discovery_cells", base_dir)

    for c, a in zip(remined, ksn.bh_adjust([c["p"] for c in remined])):
        c["p_adj"] = a

    survivors, confound_explained = [], []
    for cell in remined:
        same_sign = cell["delta"] * (cell["parent_delta"] or 0.0) >= 0
        if cell["p_adj"] < ksn.BH_ALPHA and abs(cell["delta"]) >= kss.MIN_PRACTICAL_EFFECT and same_sign:
            claim = _cell_claim(cell, "family_pass", "TESTED", cell, None)
            claim_id = cl.add_claim(claim, base_dir=base_dir)
            survivors.append({**cell, "era_claim_id": claim_id})
        else:
            claim = _cell_claim(cell, "rejected", "CONFOUND_EXPLAINED", cell,
                                 "confound_explained" if same_sign else "sign_flip_under_era_control")
            cl.add_claim(claim, base_dir=base_dir)
            cl.set_lifecycle(cell["claim_id"], "rejected",
                              review={"era_control_reason": "CONFOUND_EXPLAINED",
                                       "meta_claim_id": _HELD_META_CLAIM_ID}, base_dir=base_dir)
            confound_explained.append(cell["claim_id"])

    accepted, reserve_failed, reserve_rows = [], [], []
    for cand in survivors:
        res_r = _remine(cand, res_slice)
        replicated = bool(res_r and res_r["n_a"] >= 2 and res_r["n_b"] >= 2
                          and res_r["p"] <= 0.05 and res_r["delta"] * cand["delta"] >= 0)
        reserve_rows.append({"claim_id": cand["claim_id"], "condition": cand["condition"],
                              "entity_ids": str(cand["entity_ids"]), "phase": "reserve",
                              "delta": res_r["delta"] if res_r else None, "p": res_r["p"] if res_r else None,
                              "n_a": res_r["n_a"] if res_r else None, "n_b": res_r["n_b"] if res_r else None})
        if replicated:
            claim = _cell_claim(cand, "accepted", "ACCEPT", res_r, None, era_controlled=True)
            cl.set_lifecycle(cand["era_claim_id"], "accepted",
                              review={"reserve_delta": res_r["delta"], "reserve_p": res_r["p"]}, base_dir=base_dir)
            cl.set_lifecycle(cand["claim_id"], "accepted",
                              review={"era_control_reason": "ACCEPT", "era_claim_id": cand["era_claim_id"]},
                              base_dir=base_dir)
            cl.add_claim(claim, base_dir=base_dir)
            accepted.append(cand["claim_id"])
        else:
            cl.set_lifecycle(cand["era_claim_id"], "rejected",
                              review={"reserve_delta": res_r["delta"] if res_r else None,
                                       "reserve_p": res_r["p"] if res_r else None}, base_dir=base_dir)
            cl.set_lifecycle(cand["claim_id"], "rejected",
                              review={"era_control_reason": "era_controlled_reserve_fail",
                                       "era_claim_id": cand["era_claim_id"]}, base_dir=base_dir)
            reserve_failed.append(cand["claim_id"])
    _retain(reserve_rows, "reserve_cells", base_dir)

    return {
        "held_total": len(cells), "controlled_testable": len(remined), "not_testable_era_control": len(not_testable),
        "control_survivors": len(survivors), "confound_explained": len(confound_explained),
        "reserve_accepted": len(accepted), "reserve_failed": len(reserve_failed),
        "by_condition": {
            cond: {"held": sum(1 for c in cells if c["condition"] == cond),
                   "not_testable": sum(1 for cid in not_testable
                                        for c in cells if c["claim_id"] == cid and c["condition"] == cond),
                   "confound_explained": sum(1 for cid in confound_explained
                                              for c in cells if c["claim_id"] == cid and c["condition"] == cond),
                   "accepted": sum(1 for cid in accepted
                                    for c in cells if c["claim_id"] == cid and c["condition"] == cond),
                   "reserve_failed": sum(1 for cid in reserve_failed
                                          for c in cells if c["claim_id"] == cid and c["condition"] == cond)}
            for cond in _CONDITIONS
        },
    }


if __name__ == "__main__":
    out = run_era_control()
    for k, v in out.items():
        print(f"[k_synergy_era_control] {k}: {v}")


__all__ = ["run_era_control", "era_control_pair", "era_control_star"]
