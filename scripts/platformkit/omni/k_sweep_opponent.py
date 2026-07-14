"""scripts.platformkit.omni.k_sweep_opponent -- K opponent-dimension sweep (NBA).

Mines the "opponent" coverage dimension (S15 DIMENSIONS tuple already reserves
this slot) via the ORPHAN-1 as-of conditioner data/omni/signals_asof/
team_offdef_asof.parquet: opponent's PRIOR-SEASON defensive rating, joined
onto player-games by (opp tricode, season), split into elite/mid/weak
defense terciles. Both the opp-team-tricode and prior-season rating are
PREGAME-KNOWABLE -- schedule and last season's rating are known before tip
(never mid-game state).

Premise check (2026-07-13): nba_player_box_rate__career_to_date_snapshot.parquet
already carries team + opp tricode columns per game (verified 77,744 rows);
team_offdef_asof.parquet covers all 30 tricodes for 2022-23..2025-26, so the
join key exists cleanly -- no BLOCKED gap here.

Second condition (defense_matchup_asof, opponent primary-defender archetype)
is SKIPPED: that frame keys on def_player_id (an individual defender), and
the box-score source has no per-game "who guarded whom" column -- there is no
clean join key from player-game rows to a specific opposing defender. One
clean condition (opp_def_tercile) beats a mushy defender-matchup join.

Pooling/BH/row-retention pattern reused verbatim from k_sweep_nba.py (S8.6 +
S15.K2): league -> archetype -> player, MIN_SIDE_N floor, BH within batch,
escalate_to_funnel only for BH survivors clearing MIN_PRACTICAL_EFFECT.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_k_sweep_opponent.py -q
"""
from __future__ import annotations

import pathlib

import pandas as pd

from domains.basketball_nba import memory_atlas_archetypes as archetypes
from scripts.platformkit.omni import box_store_refresh as bsr
from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_coverage as kc
from scripts.platformkit.omni.k_sweep_nba import (
    BH_ALPHA,
    MIN_PRACTICAL_EFFECT,
    MIN_SIDE_N,
    TOP_N_PLAYERS,
    _welch_split,
    bh_adjust,
    split_discovery_reserve,
)

_SWEEP_SOURCE = pathlib.Path(
    "data/cache/intel_claims/nba_player_box_rate__career_to_date_snapshot.parquet"
)
_TEAM_OFFDEF_ASOF = pathlib.Path("data/omni/signals_asof/team_offdef_asof.parquet")
_PREDS_DIR = pathlib.Path("data/omni/preds/k_sweep_opponent_v1")
_LANE = "k_sweep_opponent_v1"
_DIMENSION = "opponent"
_CONDITION = "opp_def_tercile"
_STATS = ("pts", "min")
_TIERS = ("elite_def", "mid_def", "weak_def")

MIN_JOIN_RATE = 0.95  # honest-shortfall threshold, not a hard failure


def _team_tier_asof(source=None) -> pd.DataFrame:
    """Per-season elite/mid/weak tercile of asof__def_rtg across the 30 teams
    (lower def_rtg = better defense -> elite_def)."""
    if isinstance(source, pd.DataFrame):
        asof = source.copy()
    else:
        src = source if source is not None else _TEAM_OFFDEF_ASOF
        asof = pd.read_parquet(src, columns=["team_tricode", "season", "asof__def_rtg"])
    asof = asof.dropna(subset=["asof__def_rtg"]).copy()

    def _tier(g: pd.Series) -> pd.Series:
        try:
            return pd.qcut(g, 3, labels=_TIERS, duplicates="drop")
        except ValueError:
            return pd.Series(["mid_def"] * len(g), index=g.index)

    asof["opp_tier"] = asof.groupby("season")["asof__def_rtg"].transform(_tier)
    return asof[["team_tricode", "season", "asof__def_rtg", "opp_tier"]]


def _load_sweep_frame(source=None, tier_source=None, exclude_playoffs: bool = True) -> pd.DataFrame:
    """*source* is None (real run: full snapshot+playoff-extension via
    box_store_refresh.load_box_full), a path to the box-rate parquet, or
    (tests) a DataFrame. Playoff rows excluded from conditional tests by
    default -- separate regime (see k_sweep_nba._load_sweep_frame docstring)."""
    cols = ["player_id", "player_name", "game_id", "date", "season", "team", "opp", "is_home", "pts", "min"]
    if isinstance(source, pd.DataFrame):
        df = source.copy()
    elif source is None:
        df = bsr.load_box_full()
    else:
        df = pd.read_parquet(source, columns=cols)
    if exclude_playoffs and "is_playoffs" in df.columns:
        df = df[~df["is_playoffs"]].copy()
    df = df[cols].copy()
    df = df[df["min"] > 0].reset_index(drop=True)
    tier = _team_tier_asof(tier_source)
    merged = df.merge(
        tier, left_on=["opp", "season"], right_on=["team_tricode", "season"], how="left"
    )
    return merged.drop(columns=["team_tricode"])


def _condition_labels(df: pd.DataFrame):
    """Top vs bottom opponent-defense tercile; mid_def and unjoined rows excluded."""
    return df["opp_tier"] == "elite_def", df["opp_tier"] == "weak_def", "vs_elite_def", "vs_weak_def"


def _archetype_map() -> dict:
    stats_df = archetypes._build_stats(archetypes.DEFAULT_DATA_DIR)
    stats_df = stats_df.assign(archetype=stats_df.apply(archetypes._classify, axis=1))
    return dict(zip(stats_df["player_id"], stats_df["archetype"]))


def _mine(df: pd.DataFrame, arche_map: dict, top_ids: set, base_dir) -> list[dict]:
    side_a, side_b, label_a, label_b = _condition_labels(df)
    sub = df.copy()
    sub["side"] = pd.NA
    sub.loc[side_a, "side"] = label_a
    sub.loc[side_b, "side"] = label_b
    sub = sub[sub["side"].notna()].copy()

    # Row-level retention BEFORE any verdict is computed (S15.K2 binding).
    preds_path = _PREDS_DIR if base_dir is None else pathlib.Path(base_dir) / _PREDS_DIR.name
    preds_path.mkdir(parents=True, exist_ok=True)
    sub[["player_id", "player_name", "game_id", "date", "opp", "side", "pts", "min"]].to_parquet(
        preds_path / f"{_CONDITION}.parquet", index=False
    )

    sub["archetype"] = sub["player_id"].map(arche_map)
    records: list[dict] = []
    for stat in _STATS:
        a_vals, b_vals = sub.loc[sub["side"] == label_a, stat], sub.loc[sub["side"] == label_b, stat]
        res = _welch_split(a_vals, b_vals)
        if res:
            records.append({"level": "league", "key": None, "stat": stat, **res})

        for arch, g in sub.dropna(subset=["archetype"]).groupby("archetype"):
            res = _welch_split(g.loc[g["side"] == label_a, stat], g.loc[g["side"] == label_b, stat])
            if res:
                records.append({"level": "archetype", "key": arch, "stat": stat, **res})

        for pid, g in sub[sub["player_id"].isin(top_ids)].groupby("player_id"):
            a_vals, b_vals = g.loc[g["side"] == label_a, stat], g.loc[g["side"] == label_b, stat]
            n_a, n_b = len(a_vals), len(b_vals)
            if n_a < MIN_SIDE_N or n_b < MIN_SIDE_N:
                records.append({
                    "level": "player", "key": int(pid), "stat": stat,
                    "insufficient": True, "n_a": n_a, "n_b": n_b,
                })
            else:
                res = _welch_split(a_vals, b_vals)
                if res:
                    records.append({"level": "player", "key": int(pid), "stat": stat, **res})
    return records


def _claim_for_cell(cell: dict, data_asof: str | None) -> tuple[dict, bool]:
    level, key, stat = cell["level"], cell["key"], cell["stat"]
    if level == "league":
        entity_type, entity_ids, label = "league", [], "league-wide"
    elif level == "archetype":
        entity_type, entity_ids, label = "archetype", [str(key)], f"archetype {key}"
    else:
        entity_type, entity_ids, label = "player", [int(key)], f"player {key}"
    statement = f"NBA {label} {stat} delta vs elite-def vs weak-def opponents ({_CONDITION})"
    scope = {
        "sport": "nba", "entity_type": entity_type, "entity_ids": entity_ids,
        "context": _CONDITION, "stat": stat,
    }
    if stat == "pts":
        scope["market_families"] = ["props.pts"]
    if cell.get("insufficient"):
        effect = {"verdict": "INSUFFICIENT_DATA"}
        evidence = {"n_a": cell["n_a"], "n_b": cell["n_b"], "floor": MIN_SIDE_N}
        escalate, lifecycle = False, "screened"
    else:
        escalate = cell["p_adj"] < BH_ALPHA and abs(cell["delta"]) >= MIN_PRACTICAL_EFFECT
        effect = {
            "verdict": "TESTED", "delta": cell["delta"], "ci_low": cell["ci_low"], "ci_high": cell["ci_high"],
            "n_a": cell["n_a"], "n_b": cell["n_b"], "stat": stat,
        }
        evidence = {
            "p_value": cell["p"], "p_adj_bh": cell["p_adj"], "source": str(_SWEEP_SOURCE),
            "knowability": "pregame-knowable: opponent tricode + prior-season def_rtg both known before tip",
        }
        lifecycle = "proposed" if escalate else "screened"
    claim = {
        "statement": statement, "type": "conditional", "scope": scope,
        "topic": f"opponent.{_CONDITION}.{stat}", "lifecycle": lifecycle,
        "effect": effect, "evidence": evidence,
        "provenance": {"created_by_lane": _LANE, "data_asof": data_asof},
        "links": {"escalate_to_funnel": escalate},
    }
    return claim, escalate


def run_sweep(base_dir=None, source=None, tier_source=None, top_n: int = TOP_N_PLAYERS,
              discovery_only: bool = True, exclude_playoffs: bool = True) -> dict:
    df = _load_sweep_frame(source, tier_source, exclude_playoffs=exclude_playoffs)
    join_rate = round(float(df["opp_tier"].notna().mean()), 4) if len(df) else 0.0
    if discovery_only:
        df, _ = split_discovery_reserve(df)
    active_ids = set(kc.load_active_players()["player_id"])
    games_played = df[df["player_id"].isin(active_ids)].groupby("player_id").size()
    top_ids = set(games_played.sort_values(ascending=False).head(top_n).index)

    arche_map = _archetype_map()
    max_date = df["date"].max()
    data_asof = max_date.strftime("%Y-%m-%d") if pd.notna(max_date) else None

    all_cells = _mine(df, arche_map, top_ids, base_dir)

    tested = [c for c in all_cells if "p" in c]
    adj = bh_adjust([c["p"] for c in tested])
    for c, a in zip(tested, adj):
        c["p_adj"] = a
    batch_overfit_est = BH_ALPHA * len(tested)

    cells_and_claims = [(cell, *_claim_for_cell(cell, data_asof)) for cell in all_cells]
    claims_added, _added_ids = cl.add_claims_batch(
        [claim for _, claim, _ in cells_and_claims], base_dir=base_dir
    )
    escalations, player_status = 0, {}
    for cell, _claim, escalate in cells_and_claims:
        if escalate:
            escalations += 1
        if cell["level"] == "player":
            status = "ESCALATED" if escalate else ("INSUFFICIENT_DATA" if cell.get("insufficient") else "MINED")
            player_status.setdefault(cell["key"], []).append(status)

    priority = {"ESCALATED": 3, "MINED": 2, "INSUFFICIENT_DATA": 1}
    for pid, statuses in player_status.items():
        best = max(statuses, key=lambda s: priority[s])
        kc.update_cell(pid, _DIMENSION, best, len(statuses), base_dir=base_dir)

    metrics = kc.k5_metrics(base_dir=base_dir)
    insufficient_n = sum(1 for c in all_cells if c.get("insufficient"))
    return {
        "join_rate": join_rate,
        "join_rate_ok": join_rate >= MIN_JOIN_RATE,
        "players_covered": len(player_status),
        "cells_mined": len(all_cells),
        "claims_added": claims_added,
        "insufficient_data_share": round(insufficient_n / len(all_cells), 4) if all_cells else 0.0,
        "bh_survivors": sum(1 for c in tested if c["p_adj"] < BH_ALPHA),
        "escalations": escalations,
        "batch_overfit_est": round(batch_overfit_est, 4),
        "top_n_players_capped": top_n,
        "k5_metrics": metrics,
    }


if __name__ == "__main__":
    result = run_sweep()
    for k, v in result.items():
        if k != "k5_metrics":
            print(f"[k_sweep_opponent_v1] {k}: {v}")
    print(f"[k_sweep_opponent_v1] k5_metrics: {result['k5_metrics']}")
