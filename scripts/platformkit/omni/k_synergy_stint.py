"""scripts.platformkit.omni.k_synergy_stint -- STINT-SYNERGY: stint-grain
teammate on/off synergy (the era-confound fix for k_synergy_era_control).

k_synergy_era_control's game-grain "with/without" proxy showed only 4/18 cells
survive era control -- because game-grain absence can still be a roster-era
change in disguise. Stint grain removes the confound BY CONSTRUCTION: a
possession's off_lineup_ids is the literal 5 players on the floor for THAT
possession, so "focal player A on, partner B off" is drawn from A's own
CURRENT team-game lineups, never a different team-era.

Outcome: sim2_possessions.parquet's `points` column is the OFFENSE's points on
that possession (team-level, not per-player attribution -- no shot-attribution
join exists at this grain). So the metric here is team offensive
points-per-possession (PPP) with the focal player on the floor, contrasting
partner-present vs partner-absent lineups -- a team-efficiency synergy
measure, not a restatement of the era-control lane's per-player-pts metric.
Cross-checked against era-control's 4 accepted pairs for DIRECTIONAL
agreement only (different outcome variable, same underlying pair).

Pooling (S15.K2 anti-explosion): pair candidates are enumerated ONLY from
actual off_lineup_ids co-occurrence (never the raw player x player product),
floored at MIN_SHARED_POSS shared on-court possessions before a pair is even
a candidate. Below floor -> INSUFFICIENT_DATA, never tested.

Two-phase contract (same as every K lane): discovery-only test on 2024-25 ->
BH within this batch -> pre-register survivors (family_pass) -> reserve
(2025-26) re-read ONLY for survivors, same on/off contrast -> replicated/
rejected. Non-survivors and INSUFFICIENT_DATA cells never touch the reserve
slice -- prereg strictly precedes the reserve read.

INVARIANTS: pandas + stdlib only. <=300 LOC. ASCII stdout. Never writes
data/registry/. No $/edge claims -- these are calibration mechanism claims.
Ledger: ONE add_claims_batch call at the very end of run().

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_k_synergy_stint.py -q
"""
from __future__ import annotations

import pathlib
from collections import Counter
from itertools import combinations

import numpy as np
import pandas as pd

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_sweep_nba as ksn
from scripts.platformkit.omni.lineup_possessions import POSSESSIONS_PATH, REPO_ROOT

_LANE = "k_synergy_stint"
_PREDS_DIR = pathlib.Path("data/omni/preds/k_synergy_stint_v1")
_HELD_META_CLAIM_ID = "da228ff5dc0e31d7"  # era-control family meta (game-grain confound)
_ERA_CONTROL_LANE = "k_synergy_era_control"

FIT_SEASON = "2024-25"
RESERVE_SEASON = "2025-26"

MIN_SHARED_POSS = 200   # candidate floor: on-court-together possessions required (task-stated)
MIN_WITHOUT_POSS = 30   # focal-on/partner-off possessions required before a direction is TESTED
MIN_PRACTICAL_EFFECT_PPP = 0.05  # ~5 pts/100 poss; judgment call, documented not tuned
RESERVE_MIN_ON = 20
RESERVE_MIN_OFF = 10


def _lineup_path(season: str) -> pathlib.Path:
    return REPO_ROOT / "data" / "omni" / "lineups" / f"possession_lineups_{season.replace('-', '_')}.parquet"


def load_joined(season: str, lineup_path=None, possessions_path=None) -> pd.DataFrame:
    """(game_id, off_lineup_ids, points) for one season -- lineup store joined
    to sim2_possessions on the recomputed possession_key (game_id + per-game
    cumcount), the same key lineup_possessions.py itself writes (verified
    identical order by SPINE-3)."""
    lineup_df = pd.read_parquet(lineup_path or _lineup_path(season))
    poss_df = pd.read_parquet(possessions_path or POSSESSIONS_PATH, columns=["game_id", "season", "points"])
    poss_df = poss_df[poss_df["season"] == season].reset_index(drop=True)
    poss_df["possession_key"] = (
        poss_df["game_id"].astype(str) + ":" + poss_df.groupby("game_id").cumcount().astype(str)
    )
    merged = lineup_df.merge(poss_df[["game_id", "possession_key", "points"]], on=["game_id", "possession_key"], how="inner")
    return merged[["game_id", "off_lineup_ids", "points"]].reset_index(drop=True)


def pair_on_counts(df: pd.DataFrame) -> Counter:
    """Counter of unordered (a, b) player-id pairs -> possessions where both
    were in the SAME off_lineup_ids (on-court together)."""
    counts: Counter = Counter()
    for ids_str in df["off_lineup_ids"]:
        ids = sorted(int(x) for x in ids_str.split(","))
        for pair in combinations(ids, 2):
            counts[pair] += 1
    return counts


def candidate_pairs(df: pd.DataFrame, floor: int = MIN_SHARED_POSS) -> list[tuple[int, int]]:
    return [pair for pair, n in pair_on_counts(df).items() if n >= floor]


def player_masks(df: pd.DataFrame, players: set[int]) -> dict[int, np.ndarray]:
    """One boolean membership array per player id (vectorized once, reused
    across every candidate direction touching that player -- avoids an
    O(pairs x rows) apply)."""
    id_lists = df["off_lineup_ids"].str.split(",")
    return {p: id_lists.apply(lambda ids, ps=str(p): ps in ids).astype(bool).to_numpy() for p in players}


def on_off_split(points: np.ndarray, masks: dict[int, np.ndarray], focal: int, partner: int) -> dict | None:
    """focal-on/partner-on ('with') vs focal-on/partner-off ('without') PPP
    split via Welch's t-test. None if the 'without' side is empty."""
    on_mask = masks[focal] & masks[partner]
    off_mask = masks[focal] & ~masks[partner]
    on_vals = pd.Series(points[on_mask])
    off_vals = pd.Series(points[off_mask])
    if len(off_vals) < 2:
        return None
    return ksn._welch_split(on_vals, off_vals)  # noqa: SLF001


def _cell_claim(focal: int, partner: int, lifecycle: str, verdict: str, evidence: dict,
                era_overlap: bool) -> dict:
    scope = {
        "sport": "nba", "entity_type": "player_pair", "entity_ids": [focal, partner],
        "context": {"grain": "stint", "condition": "with_without_teammate", "shared_poss_floor": MIN_SHARED_POSS},
        "market_families": ["props.pts"],
    }
    links = {"parent_claims": [_HELD_META_CLAIM_ID]} if era_overlap else {}
    return {
        "statement": f"NBA stint-grain teammate on/off {focal}/{partner} :: {verdict}",
        "type": "conditional", "scope": scope, "topic": "synergy.stint_grain.with_without_teammate",
        "lifecycle": lifecycle, "effect": {"verdict": verdict}, "evidence": evidence,
        "provenance": {"created_by_lane": _LANE}, "links": links,
    }


def _era_control_accepted_pairs(base_dir=None) -> set[frozenset[int]]:
    """Unordered pairs accepted (era_controlled, lifecycle=accepted) by
    k_synergy_era_control -- the 4 survivors this lane must cross-check."""
    import json
    df = cl.query(sport="nba", lifecycle="accepted", base_dir=base_dir)
    out: set[frozenset[int]] = set()
    for _, row in df.iterrows():
        prov = json.loads(row["provenance_json"])
        scope = json.loads(row["scope_json"])
        if prov.get("created_by_lane") != _ERA_CONTROL_LANE:
            continue
        ctx = scope.get("context") or {}
        if isinstance(ctx, dict) and ctx.get("era_controlled") and ctx.get("condition") == "with_without_teammate":
            out.add(frozenset(scope["entity_ids"]))
    return out


def _retain(rows: list[dict], name: str, base_dir=None) -> None:
    if not rows:
        return
    out_dir = (pathlib.Path(base_dir) / _PREDS_DIR.name) if base_dir is not None else _PREDS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(out_dir / f"{name}.parquet", index=False)


def run_stint_synergy(base_dir=None, discovery_df=None, reserve_df=None) -> dict:
    disc = discovery_df if discovery_df is not None else load_joined(FIT_SEASON)
    res = reserve_df if reserve_df is not None else load_joined(RESERVE_SEASON)

    candidates = candidate_pairs(disc, MIN_SHARED_POSS)
    era_pairs = _era_control_accepted_pairs(base_dir)

    directions: list[tuple[int, int]] = []
    for a, b in candidates:
        directions.append((a, b))
        directions.append((b, a))
    players = {p for d in directions for p in d}
    masks = player_masks(disc, players) if players else {}
    points = disc["points"].to_numpy()

    tested, insufficient, discovery_rows = [], [], []
    for focal, partner in directions:
        result = on_off_split(points, masks, focal, partner)
        overlap = frozenset((focal, partner)) in era_pairs
        if result is None or result["n_b"] < MIN_WITHOUT_POSS:
            insufficient.append((focal, partner, overlap))
            discovery_rows.append({"focal": focal, "partner": partner, "phase": "discovery",
                                    "delta": None, "p": None, "n_on": None, "n_off": None})
        else:
            tested.append({"focal": focal, "partner": partner, "overlap": overlap, **result})
            discovery_rows.append({"focal": focal, "partner": partner, "phase": "discovery",
                                    "delta": result["delta"], "p": result["p"],
                                    "n_on": result["n_a"], "n_off": result["n_b"]})
    _retain(discovery_rows, "discovery_cells", base_dir)

    for c, a in zip(tested, ksn.bh_adjust([c["p"] for c in tested])):
        c["p_adj"] = a

    survivors, bh_rejected = [], []
    for c in tested:
        if c["p_adj"] < ksn.BH_ALPHA and abs(c["delta"]) >= MIN_PRACTICAL_EFFECT_PPP:
            survivors.append(c)
        else:
            bh_rejected.append(c)

    replicated, reserve_rejected, reserve_rows = [], [], []
    res_points = res["points"].to_numpy()
    res_players = {p for c in survivors for p in (c["focal"], c["partner"])}
    res_masks = player_masks(res, res_players) if res_players else {}
    for c in survivors:
        focal, partner = c["focal"], c["partner"]
        if focal not in res_masks or partner not in res_masks:
            reserve_rejected.append({**c, "reason": "player_absent_reserve"})
            reserve_rows.append({"focal": focal, "partner": partner, "phase": "reserve",
                                  "delta": None, "p": None, "n_on": None, "n_off": None})
            continue
        r = on_off_split(res_points, res_masks, focal, partner)
        n_on = int((res_masks[focal] & res_masks[partner]).sum())
        if r is None or n_on < RESERVE_MIN_ON or r["n_b"] < RESERVE_MIN_OFF:
            reserve_rejected.append({**c, "reason": "insufficient_reserve_data"})
            reserve_rows.append({"focal": focal, "partner": partner, "phase": "reserve",
                                  "delta": r["delta"] if r else None, "p": r["p"] if r else None,
                                  "n_on": n_on, "n_off": r["n_b"] if r else None})
            continue
        reserve_rows.append({"focal": focal, "partner": partner, "phase": "reserve",
                              "delta": r["delta"], "p": r["p"], "n_on": n_on, "n_off": r["n_b"]})
        same_sign = r["delta"] * c["delta"] >= 0
        if same_sign and r["p"] <= 0.05:
            replicated.append({**c, "reserve": r})
        else:
            reserve_rejected.append({**c, "reserve": r, "reason": "reserve_fail"})
    _retain(reserve_rows, "reserve_cells", base_dir)

    claims = []
    for focal, partner, overlap in insufficient:
        claims.append(_cell_claim(focal, partner, "screened", "INSUFFICIENT_DATA",
                                   {"reason": "below_shared_or_without_floor"}, overlap))
    for c in bh_rejected:
        claims.append(_cell_claim(c["focal"], c["partner"], "rejected", "NOT_SIGNIFICANT_OR_SMALL_EFFECT",
                                   {"delta": c["delta"], "p": c["p"], "p_adj": c["p_adj"],
                                    "n_on": c["n_a"], "n_off": c["n_b"]}, c["overlap"]))
    for c in reserve_rejected:
        ev = {"delta": c["delta"], "p": c["p"], "p_adj": c["p_adj"], "n_on": c["n_a"], "n_off": c["n_b"],
              "reserve_reason": c["reason"]}
        if "reserve" in c:
            ev["reserve_delta"], ev["reserve_p"] = c["reserve"]["delta"], c["reserve"]["p"]
        claims.append(_cell_claim(c["focal"], c["partner"], "rejected", "RESERVE_FAIL", ev, c["overlap"]))
    for c in replicated:
        claims.append(_cell_claim(c["focal"], c["partner"], "replicated", "REPLICATED",
                                   {"delta": c["delta"], "p": c["p"], "p_adj": c["p_adj"],
                                    "n_on": c["n_a"], "n_off": c["n_b"],
                                    "reserve_delta": c["reserve"]["delta"], "reserve_p": c["reserve"]["p"]},
                                   c["overlap"]))
    added_count, added_ids = cl.add_claims_batch(claims, base_dir=base_dir)

    era_hits = {frozenset(p) for p in candidates if frozenset(p) in era_pairs}
    return {
        "candidate_pairs": len(candidates), "directions_tested": len(tested) + len(insufficient),
        "insufficient_data": len(insufficient), "bh_survivors": len(survivors),
        "bh_rejected": len(bh_rejected), "reserve_replicated": len(replicated),
        "reserve_rejected": len(reserve_rejected), "claims_added": added_count,
        "era_control_accepted_total": len(era_pairs),
        "era_control_pairs_reaching_candidate_floor": len(era_hits),
    }


if __name__ == "__main__":
    out = run_stint_synergy()
    for k, v in out.items():
        print(f"[k_synergy_stint] {k}: {v}")


__all__ = ["run_stint_synergy", "load_joined", "pair_on_counts", "candidate_pairs", "player_masks", "on_off_split"]
