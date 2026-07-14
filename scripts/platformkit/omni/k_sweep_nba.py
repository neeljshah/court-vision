"""scripts.platformkit.omni.k_sweep_nba -- K program NBA bulk-mining sweep v1.

Mechanical conditional splits at parquet-scan cost (S15.K2: bulk mining, not
bespoke tests; no model fits). v1 scope: ONE dimension (reactions) x 3
mechanical conditions -- b2b vs 2+ rest days, home vs road, own high-foul vs
low-foul games. Stat: pts.

Sweep source (premise-checked 2026-07-13): data/cache/intel_claims/
nba_player_box_rate__career_to_date_snapshot.parquet -- 77,744 per-player-game
rows, 807 players, 2023-24..2025-26, has date/is_home/pf/pts/min.

Pooling (S8.6): league split first, then archetype split (via
domains.basketball_nba.memory_atlas_archetypes, import-only reuse), then
player-level splits where n >= MIN_SIDE_N per side; below the floor -> ledgered
INSUFFICIENT_DATA (still coverage, not failure). NEVER fits 500 players raw.

BH within this sweep batch; only BH survivors that also clear
MIN_PRACTICAL_EFFECT get escalate_to_funnel=true (lifecycle=proposed) -- the
funnel stays selective, the ledger stays complete. Row-level retention: the
filtered per-condition observation rows are written to data/omni/preds/
k_sweep_nba_v1/<condition>.parquet BEFORE any claim is ledgered.

INVARIANTS: pandas + scipy + stdlib only. <=300 LOC. ASCII stdout. Never
writes data/registry/. No $/edge claims.
"""
from __future__ import annotations

import pathlib

import pandas as pd
from scipy import stats as sps

from domains.basketball_nba import memory_atlas_archetypes as archetypes
from scripts.platformkit.omni import box_store_refresh as bsr
from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_coverage as kc

_SWEEP_SOURCE = pathlib.Path(
    "data/cache/intel_claims/nba_player_box_rate__career_to_date_snapshot.parquet"
)
_PREDS_DIR = pathlib.Path("data/omni/preds/k_sweep_nba_v1")
_LANE = "k_sweep_nba_v1"
_STAT = "pts"
_DIMENSION = "reactions"

TOP_N_PLAYERS = 559  # full active pool (K-NBA-1: v1's 200 cap, runtime confirmed cheap)
MIN_SIDE_N = 10              # pooling floor: below this, a player cell is INSUFFICIENT_DATA
BH_ALPHA = 0.05
MIN_PRACTICAL_EFFECT = 1.0   # points; escalation floor on top of BH survival

CONDITIONS = ("b2b_vs_rest", "home_vs_road", "high_foul_vs_low_foul")

# Reserve discipline (S15.K3): 2025-26 is reserve, never mined by default.
# Games dated on/after this cutover belong to the 2025-26 season.
RESERVE_CUTOVER = "2025-10-01"

_STATUS_PRIORITY = {"ESCALATED": 3, "MINED": 2, "INSUFFICIENT_DATA": 1}


def _load_sweep_frame(source=None, exclude_playoffs: bool = True) -> pd.DataFrame:
    """*source* is None (real run: full snapshot+playoff-extension via
    box_store_refresh.load_box_full), a path to the box-rate parquet, or
    (tests) a DataFrame. Playoff rows are excluded from conditional tests by
    default -- playoffs are a separate regime (precedent: pregame AST edge
    never mined on playoff rows); pass exclude_playoffs=False to mine them."""
    cols = ["player_id", "player_name", "game_id", "date", "is_home", "pf", "pts", "min"]
    if isinstance(source, pd.DataFrame):
        df = source.copy()
    elif source is None:
        df = bsr.load_box_full()
    else:
        df = pd.read_parquet(source, columns=cols)
    if exclude_playoffs and "is_playoffs" in df.columns:
        df = df[~df["is_playoffs"]].copy()
    df = df[cols].copy()
    df = df[df["min"] > 0].sort_values(["player_id", "date"]).reset_index(drop=True)
    df["rest_days"] = df.groupby("player_id")["date"].diff().dt.days - 1
    return df


def split_discovery_reserve(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Season-boundary split: discovery = 2023-24 + 2024-25 (date < cutover),
    reserve = 2025-26 (date >= cutover). Callers must pre-register on
    discovery before ever touching the reserve half (S15.K3)."""
    cutover = pd.Timestamp(RESERVE_CUTOVER)
    return df[df["date"] < cutover].copy(), df[df["date"] >= cutover].copy()


def remine_player_cell(df: pd.DataFrame, player_id: int, condition: str) -> dict | None:
    """Re-mine one player's Welch split for *condition* on *df* (caller slices
    to discovery or reserve rows first). Same shape as a per-cell record from
    _mine_condition; None if a side is empty. Reused by k_stage_b so the
    split/test math is never forked."""
    g = df[df["player_id"] == player_id]
    side_a, side_b, _, _ = _condition_labels(g, condition)
    return _welch_split(g.loc[side_a, _STAT], g.loc[side_b, _STAT])


def _archetype_map() -> dict:
    stats_df = archetypes._build_stats(archetypes.DEFAULT_DATA_DIR)
    stats_df = stats_df.assign(archetype=stats_df.apply(archetypes._classify, axis=1))
    return dict(zip(stats_df["player_id"], stats_df["archetype"]))


def _condition_labels(df: pd.DataFrame, condition: str):
    """Return (side_a_mask, side_b_mask, label_a, label_b); rows outside both excluded."""
    if condition == "b2b_vs_rest":
        return df["rest_days"] <= 0, df["rest_days"] >= 2, "b2b", "rest2plus"
    if condition == "home_vs_road":
        return df["is_home"] == 1, df["is_home"] == 0, "home", "road"
    if condition == "high_foul_vs_low_foul":
        return df["pf"] >= 4, df["pf"] <= 1, "high_foul", "low_foul"
    raise ValueError(f"unknown condition {condition!r}")


def _welch_split(a_vals: pd.Series, b_vals: pd.Series) -> dict | None:
    n_a, n_b = len(a_vals), len(b_vals)
    if n_a < 2 or n_b < 2:
        return None
    delta = float(a_vals.mean() - b_vals.mean())
    se = float((a_vals.var(ddof=1) / n_a + b_vals.var(ddof=1) / n_b) ** 0.5)
    _, p = sps.ttest_ind(a_vals, b_vals, equal_var=False)
    return {
        "delta": delta, "se": se, "ci_low": delta - 1.96 * se, "ci_high": delta + 1.96 * se,
        "n_a": n_a, "n_b": n_b, "p": float(p),
    }


def bh_adjust(pvals: list[float]) -> list[float]:
    """Benjamini-Hochberg adjusted p-values, same order as input."""
    n = len(pvals)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: pvals[i])
    adj = [0.0] * n
    running_min = 1.0
    for rank in range(n, 0, -1):
        i = order[rank - 1]
        running_min = min(running_min, pvals[i] * n / rank)
        adj[i] = running_min
    return adj


def _mine_condition(df: pd.DataFrame, condition: str, arche_map: dict, top_ids: set, base_dir) -> list[dict]:
    side_a, side_b, label_a, label_b = _condition_labels(df, condition)
    sub = df.copy()
    sub["side"] = pd.NA
    sub.loc[side_a, "side"] = label_a
    sub.loc[side_b, "side"] = label_b
    sub = sub[sub["side"].notna()].copy()

    # Row-level retention BEFORE any verdict is computed (S15.K2 binding).
    preds_path = _PREDS_DIR if base_dir is None else pathlib.Path(base_dir) / _PREDS_DIR.name
    preds_path.mkdir(parents=True, exist_ok=True)
    sub[["player_id", "player_name", "game_id", "date", "side", _STAT]].to_parquet(
        preds_path / f"{condition}.parquet", index=False
    )

    records = []
    a_vals, b_vals = sub.loc[sub["side"] == label_a, _STAT], sub.loc[sub["side"] == label_b, _STAT]
    res = _welch_split(a_vals, b_vals)
    if res:
        records.append({"level": "league", "key": None, "condition": condition, **res})

    sub["archetype"] = sub["player_id"].map(arche_map)
    for arch, g in sub.dropna(subset=["archetype"]).groupby("archetype"):
        res = _welch_split(g.loc[g["side"] == label_a, _STAT], g.loc[g["side"] == label_b, _STAT])
        if res:
            records.append({"level": "archetype", "key": arch, "condition": condition, **res})

    for pid, g in sub[sub["player_id"].isin(top_ids)].groupby("player_id"):
        a_vals, b_vals = g.loc[g["side"] == label_a, _STAT], g.loc[g["side"] == label_b, _STAT]
        n_a, n_b = len(a_vals), len(b_vals)
        if n_a < MIN_SIDE_N or n_b < MIN_SIDE_N:
            records.append({
                "level": "player", "key": int(pid), "condition": condition,
                "insufficient": True, "n_a": n_a, "n_b": n_b,
            })
        else:
            res = _welch_split(a_vals, b_vals)
            if res:
                records.append({"level": "player", "key": int(pid), "condition": condition, **res})
    return records


def _claim_for_cell(cell: dict, data_asof: str | None) -> tuple[dict, bool]:
    level, key, condition = cell["level"], cell["key"], cell["condition"]
    if level == "league":
        entity_type, entity_ids, label = "league", [], "league-wide"
    elif level == "archetype":
        entity_type, entity_ids, label = "archetype", [str(key)], f"archetype {key}"
    else:
        entity_type, entity_ids, label = "player", [int(key)], f"player {key}"
    statement = f"NBA {label} {_STAT} delta under {condition}"
    scope = {"sport": "nba", "entity_type": entity_type, "entity_ids": entity_ids, "context": condition}
    if cell.get("insufficient"):
        effect = {"verdict": "INSUFFICIENT_DATA"}
        evidence = {"n_a": cell["n_a"], "n_b": cell["n_b"], "floor": MIN_SIDE_N}
        escalate, lifecycle = False, "screened"
    else:
        escalate = cell["p_adj"] < BH_ALPHA and abs(cell["delta"]) >= MIN_PRACTICAL_EFFECT
        effect = {
            "verdict": "TESTED", "delta": cell["delta"], "ci_low": cell["ci_low"], "ci_high": cell["ci_high"],
            "n_a": cell["n_a"], "n_b": cell["n_b"], "stat": _STAT,
        }
        evidence = {"p_value": cell["p"], "p_adj_bh": cell["p_adj"], "source": str(_SWEEP_SOURCE)}
        lifecycle = "proposed" if escalate else "screened"
    claim = {
        "statement": statement, "type": "conditional", "scope": scope,
        "topic": f"reactions.{condition}", "lifecycle": lifecycle,
        "effect": effect, "evidence": evidence,
        "provenance": {"created_by_lane": _LANE, "data_asof": data_asof},
        "links": {"escalate_to_funnel": escalate},
    }
    return claim, escalate


def run_sweep(base_dir=None, source=None, top_n: int = TOP_N_PLAYERS, discovery_only: bool = True,
              exclude_playoffs: bool = True) -> dict:
    df = _load_sweep_frame(source, exclude_playoffs=exclude_playoffs)
    if discovery_only:
        df, _ = split_discovery_reserve(df)
    active_ids = set(kc.load_active_players()["player_id"])
    games_played = df[df["player_id"].isin(active_ids)].groupby("player_id").size()
    top_ids = set(games_played.sort_values(ascending=False).head(top_n).index)
    print(f"[k_sweep_nba_v1] cap: top {top_n} active players by games played "
          f"({len(top_ids)} selected of {len(active_ids)} active)")

    arche_map = _archetype_map()
    max_date = df["date"].max()
    data_asof = max_date.strftime("%Y-%m-%d") if pd.notna(max_date) else None

    all_cells: list[dict] = []
    for condition in CONDITIONS:
        all_cells.extend(_mine_condition(df, condition, arche_map, top_ids, base_dir))

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

    for pid, statuses in player_status.items():
        best = max(statuses, key=lambda s: _STATUS_PRIORITY[s])
        kc.update_cell(pid, _DIMENSION, best, len(statuses), base_dir=base_dir)

    metrics = kc.k5_metrics(base_dir=base_dir)
    insufficient_n = sum(1 for c in all_cells if c.get("insufficient"))
    return {
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
            print(f"[k_sweep_nba_v1] {k}: {v}")
    print(f"[k_sweep_nba_v1] k5_metrics: {result['k5_metrics']}")
