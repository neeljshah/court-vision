"""scripts.platformkit.omni.k_sweep_synergy -- K synergy dimension sweep v1 (S15.K1).

Two conditions, both bounded by ACTUAL roster co-occurrence (never the raw
500x500 league pair product -- S15.K2):

  with_without_teammate -- for teammate pairs (A, B) who shared >=MIN_PAIR_GAMES
    team-games in the discovery slice, player A's pts in games B also played
    vs games B did not (both rows drawn from the same team roster per game_id).
    This is game-grain "with/without", NOT stint-grain on/off -- honest ceiling;
    upgrade path is a real stint store if one ever lands (none found at
    premise-check time: data/cache/profiles/nba_lineup_profiles.parquet and
    data/cache/signals/lineup_5man.parquet are SEASON-grain, no per-game stint
    id; data/cache/intel_claims/nba_boxscore_agg_snapshot.parquet has no team
    column, can't build rosters).

  star_sits -- each team-season's top-mean-pts player (the "star"); every
    other rostered teammate's pts delta in games the star sat (game_id absent
    from the star's played set for that team-season) vs games the star played,
    floored at >=5 games per side.

Sweep source (premise-checked 2026-07-13): data/cache/intel_claims/
nba_player_box_rate__career_to_date_snapshot.parquet -- 77,744 per-player-game
rows, has team/game_id/date/min/pts -- the only on-disk NBA store with BOTH a
team column (roster reconstruction) and per-game grain (on/off-style splits).

Pooling (S8.6, matches k_sweep_nba): league level pools all qualifying-pair
instances; archetype level pools by player A's (pair) / teammate's (star_sits)
archetype via domains.basketball_nba.memory_atlas_archetypes (import-only);
pair/player cells only above floors, else ledgered INSUFFICIENT_DATA (still
coverage). BH within this sweep batch; survivors clearing MIN_PRACTICAL_EFFECT
get escalate_to_funnel=true for M26. Row-level retention BEFORE any claim is
ledgered: data/omni/preds/k_sweep_synergy_v1/<condition>.parquet.

Teammate availability is pregame-knowable (injury reports) so with_without/
star_sits claims carry scope.market_families=['props.pts'] -- this links the
synergy dimension to the health/injury dimension for the funnel.

INVARIANTS: pandas + stdlib only. <=300 LOC. ASCII stdout. Never writes
data/registry/. No $/edge claims.
"""
from __future__ import annotations

import pathlib
from itertools import combinations

import pandas as pd

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_coverage as kc
from scripts.platformkit.omni.k_sweep_nba import (
    RESERVE_CUTOVER,
    _archetype_map,
    _welch_split,
    bh_adjust,
)

_SWEEP_SOURCE = pathlib.Path(
    "data/cache/intel_claims/nba_player_box_rate__career_to_date_snapshot.parquet"
)
_PREDS_DIR = pathlib.Path("data/omni/preds/k_sweep_synergy_v1")
_LANE = "k_sweep_synergy_v1"
_STAT = "pts"
_DIMENSION = "synergy"

TOP_N_PLAYERS = 200
MIN_PAIR_GAMES = 30   # pair floor: shared team-games required before a pair is TESTED
MIN_ABSENCE_N = 5     # star-sits floor: games required on EACH side of the split
BH_ALPHA = 0.05
MIN_PRACTICAL_EFFECT = 1.0

CONDITIONS = ("with_without_teammate", "star_sits")
_STATUS_PRIORITY = {"ESCALATED": 3, "MINED": 2, "INSUFFICIENT_DATA": 1}


def _load_sweep_frame(source=None) -> pd.DataFrame:
    cols = ["game_id", "date", "season", "team", "player_id", "player_name", "min", _STAT]
    if isinstance(source, pd.DataFrame):
        df = source[cols].copy()
    else:
        df = pd.read_parquet(source if source is not None else _SWEEP_SOURCE, columns=cols)
    return df.reset_index(drop=True)


def split_discovery_reserve(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cutover = pd.Timestamp(RESERVE_CUTOVER)
    return df[df["date"] < cutover].copy(), df[df["date"] >= cutover].copy()


def _pair_counts(played: pd.DataFrame) -> dict[tuple[int, int], int]:
    """Co-occurrence counts over ACTUAL (team, game_id) rosters only -- bounded
    by real roster size (~13 players/game), never the full player x player
    cross product."""
    counts: dict[tuple[int, int], int] = {}
    for _, roster in played.groupby(["team", "game_id"])["player_id"]:
        for a, b in combinations(sorted(set(roster)), 2):
            counts[(a, b)] = counts.get((a, b), 0) + 1
    return counts


def _with_without_split(played: pd.DataFrame, a: int, b: int):
    a_games = played[played["player_id"] == a]
    b_keys = set(zip(played.loc[played["player_id"] == b, "team"],
                      played.loc[played["player_id"] == b, "game_id"]))
    with_b = pd.Series(list(zip(a_games["team"], a_games["game_id"])), index=a_games.index).isin(b_keys)
    return _welch_split(a_games.loc[with_b, _STAT], a_games.loc[~with_b, _STAT]), with_b, a_games


def _mine_with_without(played: pd.DataFrame, arche_map: dict, top_ids: set, base_dir) -> list[dict]:
    pairs = {k: n for k, n in _pair_counts(played).items() if k[0] in top_ids and k[1] in top_ids}
    records: list[dict] = []
    rows_out: list[pd.DataFrame] = []
    for (a, b), n_shared in pairs.items():
        if n_shared < MIN_PAIR_GAMES:
            records.append({"level": "pair", "key": (a, b), "condition": "with_without_teammate",
                             "insufficient": True, "n_a": n_shared, "n_b": 0})
            continue
        res, with_b, a_games = _with_without_split(played, a, b)
        if res is None:
            records.append({"level": "pair", "key": (a, b), "condition": "with_without_teammate",
                             "insufficient": True, "n_a": n_shared, "n_b": 0})
            continue
        records.append({"level": "pair", "key": (a, b), "condition": "with_without_teammate", **res})
        obs = a_games[["player_id", "game_id", "date", _STAT]].copy()
        obs["teammate_id"] = b
        obs["side"] = with_b.map({True: "with", False: "without"})
        rows_out.append(obs)

    if rows_out:
        sub = pd.concat(rows_out, ignore_index=True)
        for level_key, g in [("league", sub)] + [
            (arch, sub[sub["player_id"].map(arche_map) == arch])
            for arch in sub["player_id"].map(arche_map).dropna().unique()
        ]:
            res = _welch_split(g.loc[g["side"] == "with", _STAT], g.loc[g["side"] == "without", _STAT])
            if res:
                level = "league" if level_key == "league" else "archetype"
                records.append({"level": level, "key": None if level == "league" else level_key,
                                 "condition": "with_without_teammate", **res})
        preds_path = _PREDS_DIR if base_dir is None else pathlib.Path(base_dir) / _PREDS_DIR.name
        preds_path.mkdir(parents=True, exist_ok=True)
        sub.to_parquet(preds_path / "with_without_teammate.parquet", index=False)
    return records


def _mine_star_sits(played: pd.DataFrame, arche_map: dict, top_ids: set, base_dir) -> list[dict]:
    means = played.groupby(["team", "season", "player_id"])[_STAT].mean()
    stars = means.groupby(level=[0, 1]).idxmax()
    records: list[dict] = []
    rows_out: list[pd.DataFrame] = []
    for team, season, star_id in stars.values:
        ts = played[(played["team"] == team) & (played["season"] == season)]
        absent_games = set(ts["game_id"]) - set(ts.loc[ts["player_id"] == star_id, "game_id"])
        for pid, g in ts[ts["player_id"] != star_id].groupby("player_id"):
            if pid not in top_ids:
                continue
            sit = g.loc[g["game_id"].isin(absent_games), _STAT]
            play = g.loc[~g["game_id"].isin(absent_games), _STAT]
            base = {"level": "player", "key": int(pid), "condition": "star_sits",
                    "star_id": int(star_id), "team": team, "season": season}
            if len(sit) < MIN_ABSENCE_N or len(play) < MIN_ABSENCE_N:
                records.append({**base, "insufficient": True, "n_a": len(sit), "n_b": len(play)})
                continue
            res = _welch_split(sit, play)
            if res:
                records.append({**base, **res})
                obs = g[["player_id", "game_id", "date", _STAT]].copy()
                obs["side"] = obs["game_id"].isin(absent_games).map({True: "star_sat", False: "star_played"})
                obs["star_id"] = star_id
                rows_out.append(obs)

    if rows_out:
        sub = pd.concat(rows_out, ignore_index=True)
        for level_key, g in [("league", sub)] + [
            (arch, sub[sub["player_id"].map(arche_map) == arch])
            for arch in sub["player_id"].map(arche_map).dropna().unique()
        ]:
            res = _welch_split(g.loc[g["side"] == "star_sat", _STAT], g.loc[g["side"] == "star_played", _STAT])
            if res:
                level = "league" if level_key == "league" else "archetype"
                records.append({"level": level, "key": None if level == "league" else level_key,
                                 "condition": "star_sits", **res})
        preds_path = _PREDS_DIR if base_dir is None else pathlib.Path(base_dir) / _PREDS_DIR.name
        preds_path.mkdir(parents=True, exist_ok=True)
        sub.to_parquet(preds_path / "star_sits.parquet", index=False)
    return records


def _claim_for_cell(cell: dict, data_asof: str | None) -> tuple[dict, bool]:
    level, condition = cell["level"], cell["condition"]
    if level == "league":
        entity_type, entity_ids, label = "league", [], "league-wide"
    elif level == "archetype":
        entity_type, entity_ids, label = "archetype", [str(cell["key"])], f"archetype {cell['key']}"
    elif level == "pair":
        a, b = cell["key"]
        entity_type, entity_ids, label = "player_pair", [int(a), int(b)], f"players {a}/{b}"
    else:
        entity_type, entity_ids, label = "player", [int(cell["key"])], f"player {cell['key']}"
    statement = f"NBA {label} {_STAT} delta under {condition}"
    scope = {"sport": "nba", "entity_type": entity_type, "entity_ids": entity_ids, "context": condition,
              "market_families": ["props.pts"]}  # teammate availability is pregame-knowable (injury reports)
    if cell.get("insufficient"):
        effect = {"verdict": "INSUFFICIENT_DATA"}
        evidence = {"n_a": cell["n_a"], "n_b": cell["n_b"],
                    "floor": MIN_PAIR_GAMES if level == "pair" else MIN_ABSENCE_N}
        escalate, lifecycle = False, "screened"
    else:
        escalate = cell["p_adj"] < BH_ALPHA and abs(cell["delta"]) >= MIN_PRACTICAL_EFFECT
        effect = {"verdict": "TESTED", "delta": cell["delta"], "ci_low": cell["ci_low"],
                  "ci_high": cell["ci_high"], "n_a": cell["n_a"], "n_b": cell["n_b"], "stat": _STAT}
        evidence = {"p_value": cell["p"], "p_adj_bh": cell["p_adj"], "source": str(_SWEEP_SOURCE)}
        lifecycle = "proposed" if escalate else "screened"
    claim = {
        "statement": statement, "type": "conditional", "scope": scope,
        "topic": f"synergy.{condition}", "lifecycle": lifecycle,
        "effect": effect, "evidence": evidence,
        "provenance": {"created_by_lane": _LANE, "data_asof": data_asof},
        "links": {"escalate_to_funnel": escalate},
    }
    return claim, escalate


def run_sweep(base_dir=None, source=None, top_n: int = TOP_N_PLAYERS, discovery_only: bool = True) -> dict:
    df = _load_sweep_frame(source)
    if discovery_only:
        df, _ = split_discovery_reserve(df)
    played = df[df["min"] > 0]
    active_ids = set(kc.load_active_players()["player_id"])
    games_played = played[played["player_id"].isin(active_ids)].groupby("player_id").size()
    top_ids = set(games_played.sort_values(ascending=False).head(top_n).index)
    print(f"[k_sweep_synergy_v1] cap: top {top_n} active players by games played "
          f"({len(top_ids)} selected of {len(active_ids)} active)")

    arche_map = _archetype_map()
    max_date = df["date"].max()
    data_asof = max_date.strftime("%Y-%m-%d") if pd.notna(max_date) else None

    all_cells = _mine_with_without(played, arche_map, top_ids, base_dir)
    all_cells += _mine_star_sits(played, arche_map, top_ids, base_dir)

    tested = [c for c in all_cells if "p" in c]
    adj = bh_adjust([c["p"] for c in tested])
    for c, a in zip(tested, adj):
        c["p_adj"] = a
    batch_overfit_est = BH_ALPHA * len(tested)

    cells_and_claims = [(cell, *_claim_for_cell(cell, data_asof)) for cell in all_cells]
    claims_added, _ = cl.add_claims_batch(
        [claim for _, claim, _ in cells_and_claims], base_dir=base_dir
    )
    escalations, player_status = 0, {}
    for cell, _claim, escalate in cells_and_claims:
        if escalate:
            escalations += 1
        status = "ESCALATED" if escalate else ("INSUFFICIENT_DATA" if cell.get("insufficient") else "MINED")
        if cell["level"] == "pair":
            for pid in cell["key"]:
                if pid in top_ids:
                    player_status.setdefault(pid, []).append(status)
        elif cell["level"] == "player":
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
            print(f"[k_sweep_synergy_v1] {k}: {v}")
    print(f"[k_sweep_synergy_v1] k5_metrics: {result['k5_metrics']}")
