"""scripts.platformkit.omni.k_sweep_physical -- K physical dimension (NBA, S15.K1).

Mines age_curve_position, conditioning_trend, size_vs_role for the "physical"
coverage dimension from data/player_positions.parquet (anthropometrics) +
data/player_adv_stats.parquet (per-game minutes).

Premise-checked 2026-07-13: data/player_positions.parquet has FULL coverage
for all 559 active players -- height_inches, weight_lbs (6 nulls dataset-wide,
0 among active), birth_date, draft_year. Real age from birth_date is used
directly; this is richer than the task's fallback "years-of-service via
from_year" proxy, so that proxy path is unused here (kept as a documented
non-path, not built, per YAGNI -- add if a future roster source lacks
birth_date).

Three claim families:
1. age_curve_position (structural/DESCRIPTIVE): age as of the 2025-26 season
   anchor vs the player's archetype median age -- a snapshot fact like
   k_sweep_playprofile's descriptive basket, not a discovery test.
2. conditioning_trend (conditional/TESTED, discovery slice): OLS slope of
   monthly mean minutes over the 2024-25 season (entirely before the
   2025-10-01 reserve cutover, see k_sweep_nba.RESERVE_CUTOVER) for players
   with >=30 season games and >=3 distinct months. BH-adjusted.
3. size_vs_role (structural/DESCRIPTIVE): height/weight vs archetype median --
   snapshot, no test. INSUFFICIENT_DATA only if height/weight missing.

INVARIANTS: pandas + scipy + stdlib only. <=300 LOC. ASCII stdout. No $/edge.
Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_k_sweep_physical.py -q
"""
from __future__ import annotations

import pathlib

import pandas as pd
from scipy import stats as sps

from domains.basketball_nba import memory_atlas_archetypes as archetypes
from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_coverage as kc
from scripts.platformkit.omni.k_sweep_nba import BH_ALPHA, bh_adjust

_POSITIONS_SOURCE = pathlib.Path("data/player_positions.parquet")
_ADV_SOURCE = pathlib.Path("data/player_adv_stats.parquet")
_PREDS_DIR = pathlib.Path("data/omni/preds/k_sweep_physical_v1")
_LANE = "k_sweep_physical_v1"
_DIMENSION = "physical"

_SEASON_START, _SEASON_END = "2024-10-01", "2025-06-30"  # discovery slice
_AGE_ANCHOR = "2025-10-01"  # current-season snapshot date for age_curve_position
MIN_SEASON_GAMES = 30
MIN_MONTHS = 3
MIN_PRACTICAL_SLOPE_MIN = 1.0  # min/month of decline to be practically meaningful

_STATUS_PRIORITY = {"ESCALATED": 3, "MINED": 2, "INSUFFICIENT_DATA": 1}


def _load_positions(source=None) -> pd.DataFrame:
    cols = ["player_id", "position", "height_inches", "weight_lbs", "birth_date", "draft_year"]
    if isinstance(source, pd.DataFrame):
        return source[cols].copy()
    return pd.read_parquet(source if source is not None else _POSITIONS_SOURCE, columns=cols)


def _load_adv_stats(source=None) -> pd.DataFrame:
    cols = ["player_id", "game_date", "minutes"]
    if isinstance(source, pd.DataFrame):
        return source[cols].copy()
    return pd.read_parquet(source if source is not None else _ADV_SOURCE, columns=cols)


def _archetype_map() -> dict:
    stats_df = archetypes._build_stats(archetypes.DEFAULT_DATA_DIR)
    stats_df = stats_df.assign(archetype=stats_df.apply(archetypes._classify, axis=1))
    return dict(zip(stats_df["player_id"], stats_df["archetype"]))


def _archetype_medians(pos: pd.DataFrame, arche_map: dict, value_cols: list[str]) -> dict:
    """{archetype: {col: median}} pooled across whichever active players have both
    an archetype label and non-null value -- league->archetype pooling per spec."""
    df = pos.copy()
    df["archetype"] = df["player_id"].map(arche_map)
    out: dict = {}
    for arch, g in df.dropna(subset=["archetype"]).groupby("archetype"):
        out[arch] = {c: float(g[c].median()) for c in value_cols if g[c].notna().any()}
    return out


def _snapshot_claim(player_id: int, mechanism: str, value: float | None, archetype: str | None,
                     arche_median: float | None, unit: str) -> tuple[dict, str]:
    scope = {"sport": "nba", "entity_type": "player", "entity_ids": [int(player_id)], "context": mechanism}
    topic = f"physical.{mechanism}"
    if value is None:
        statement = f"NBA player {player_id} {mechanism}: INSUFFICIENT_DATA"
        effect = {"verdict": "INSUFFICIENT_DATA"}
        evidence = {"source": str(_POSITIONS_SOURCE), "reason": "missing anthropometric field on disk"}
        status = "INSUFFICIENT_DATA"
    else:
        statement = f"NBA player {player_id} {mechanism} = {value:.2f} {unit} ({_AGE_ANCHOR} snapshot)"
        effect = {"verdict": "DESCRIPTIVE", "raw_value": float(value)}
        evidence = {
            "archetype": archetype, "archetype_median": arche_median,
            "deviation_from_archetype": (float(value - arche_median) if arche_median is not None else None),
            "source": str(_POSITIONS_SOURCE), "as_of": _AGE_ANCHOR,
        }
        status = "MINED"
    claim = {
        "statement": statement, "type": "structural", "scope": scope, "topic": topic,
        "lifecycle": "screened", "effect": effect, "evidence": evidence,
        "provenance": {"created_by_lane": _LANE, "data_asof": _AGE_ANCHOR},
        "links": {"escalate_to_funnel": False},
    }
    return claim, status


def _mine_snapshot_mechanism(pos: pd.DataFrame, arche_map: dict, mechanism: str, col: str,
                              medians: dict, unit: str) -> tuple[list[dict], dict]:
    claims, status = [], {}
    for row in pos.itertuples():
        pid, arch = row.player_id, arche_map.get(row.player_id)
        value = getattr(row, col)
        arche_median = medians.get(arch, {}).get(col) if arch is not None else None
        claim, st = _snapshot_claim(pid, mechanism, None if pd.isna(value) else value, arch, arche_median, unit)
        claims.append(claim)
        status[pid] = st
    return claims, status


def _age_years(pos: pd.DataFrame) -> pd.Series:
    anchor = pd.Timestamp(_AGE_ANCHOR)
    birth = pd.to_datetime(pos["birth_date"])
    return (anchor - birth).dt.days / 365.25


def _conditioning_slopes(adv: pd.DataFrame) -> list[dict]:
    """Per player: OLS slope of monthly mean minutes over the 2024-25 season."""
    season = adv[(adv["game_date"] >= _SEASON_START) & (adv["game_date"] <= _SEASON_END)].copy()
    season["month"] = season["game_date"].dt.to_period("M")
    game_counts = season.groupby("player_id").size()
    eligible = set(game_counts[game_counts >= MIN_SEASON_GAMES].index)
    cells = []
    for pid, g in season[season["player_id"].isin(eligible)].groupby("player_id"):
        monthly = g.groupby("month")["minutes"].mean().sort_index()
        if len(monthly) < MIN_MONTHS:
            cells.append({"player_id": int(pid), "res": None, "n_games": int(len(g))})
            continue
        x = list(range(len(monthly)))
        slope, intercept, r, p, se = sps.linregress(x, monthly.values)
        cells.append({"player_id": int(pid), "n_games": int(len(g)), "n_months": len(monthly),
                      "res": {"slope": float(slope), "se": float(se), "p": float(p)}})
    return cells


def _conditioning_claim(cell: dict, p_adj: float | None) -> tuple[dict, bool]:
    pid = cell["player_id"]
    scope = {"sport": "nba", "entity_type": "player", "entity_ids": [pid], "context": "conditioning_trend"}
    topic = "physical.conditioning_trend"
    statement = f"NBA player {pid} conditioning_trend (monthly minutes slope, 2024-25 discovery)"
    if cell["res"] is None:
        claim = {
            "statement": statement, "type": "conditional", "scope": scope, "topic": topic,
            "lifecycle": "screened", "effect": {"verdict": "INSUFFICIENT_DATA"},
            "evidence": {"source": str(_ADV_SOURCE), "n_games": cell["n_games"],
                         "reason": f"< {MIN_MONTHS} distinct months with >= {MIN_SEASON_GAMES} season games"},
            "provenance": {"created_by_lane": _LANE, "data_asof": _SEASON_END},
            "links": {"escalate_to_funnel": False},
        }
        return claim, False
    res = cell["res"]
    escalate = p_adj is not None and p_adj < BH_ALPHA and abs(res["slope"]) >= MIN_PRACTICAL_SLOPE_MIN
    claim = {
        "statement": statement, "type": "conditional", "scope": scope, "topic": topic,
        "lifecycle": "proposed" if escalate else "screened",
        "effect": {"verdict": "TESTED", "slope_min_per_month": res["slope"], "n": cell["n_games"]},
        "evidence": {
            "p_value": res["p"], "p_adj_bh": p_adj, "n_months": cell["n_months"],
            "source": str(_ADV_SOURCE), "window": "season_2024_25",
            "knowability": "reserve-safe: entire window pre-2025-10-01 cutover",
        },
        "provenance": {"created_by_lane": _LANE, "data_asof": _SEASON_END},
        "links": {"escalate_to_funnel": escalate},
    }
    return claim, escalate


def _retain(df: pd.DataFrame, name: str, base_dir) -> None:
    preds_path = _PREDS_DIR if base_dir is None else pathlib.Path(base_dir) / _PREDS_DIR.name
    preds_path.mkdir(parents=True, exist_ok=True)
    df.to_parquet(preds_path / f"{name}.parquet", index=False)


def run_sweep(base_dir=None, positions_source=None, adv_source=None, players: pd.DataFrame | None = None) -> dict:
    pos = _load_positions(positions_source)
    adv = _load_adv_stats(adv_source)
    adv["game_date"] = pd.to_datetime(adv["game_date"])
    active = players if players is not None else kc.load_active_players()
    pos = pos[pos["player_id"].isin(active["player_id"])].copy()
    pos["age_years"] = _age_years(pos)

    arche_map = _archetype_map()
    medians = _archetype_medians(pos, arche_map, ["age_years", "height_inches", "weight_lbs"])

    claims: list[dict] = []
    player_status: dict[int, list[str]] = {}

    age_claims, age_status = _mine_snapshot_mechanism(pos, arche_map, "age_curve_position", "age_years", medians, "years")
    claims += age_claims
    for pid, st in age_status.items():
        player_status.setdefault(pid, []).append(st)

    for col, unit in (("height_inches", "in"), ("weight_lbs", "lb")):
        size_claims, size_status = _mine_snapshot_mechanism(pos, arche_map, f"size_vs_role_{col}", col, medians, unit)
        claims += size_claims
        for pid, st in size_status.items():
            player_status.setdefault(pid, []).append(st)

    _retain(pos[["player_id", "position", "height_inches", "weight_lbs", "age_years"]], "descriptive_snapshot", base_dir)

    slope_cells = _conditioning_slopes(adv)
    tested = [c for c in slope_cells if c["res"] is not None]
    adj = bh_adjust([c["res"]["p"] for c in tested])
    for c, a in zip(tested, adj):
        c["p_adj"] = a
    p_adj_map = {c["player_id"]: c["p_adj"] for c in tested}
    _retain(pd.DataFrame([
        {"player_id": c["player_id"], "slope": c["res"]["slope"] if c["res"] else None,
         "p": c["res"]["p"] if c["res"] else None, "p_adj": p_adj_map.get(c["player_id"])}
        for c in slope_cells
    ]), "conditioning_trend", base_dir)

    escalations = 0
    for cell in slope_cells:
        pid = cell["player_id"]
        claim, escalate = _conditioning_claim(cell, p_adj_map.get(pid))
        claims.append(claim)
        if escalate:
            escalations += 1
        status = "ESCALATED" if escalate else ("INSUFFICIENT_DATA" if cell["res"] is None else "MINED")
        player_status.setdefault(pid, []).append(status)

    claims_added, _ = cl.add_claims_batch(claims, base_dir=base_dir)

    for pid, statuses in player_status.items():
        best = max(statuses, key=lambda s: _STATUS_PRIORITY[s])
        try:
            kc.update_cell(pid, _DIMENSION, best, len(statuses), base_dir=base_dir)
        except KeyError:
            pass  # ponytail: player off the active-roster coverage matrix -- skip, not a failure

    metrics = kc.k5_metrics(base_dir=base_dir)
    insufficient_n = sum(1 for statuses in player_status.values() if all(s == "INSUFFICIENT_DATA" for s in statuses))
    return {
        "players_covered": len(player_status),
        "cells_mined": len(claims),
        "claims_added": claims_added,
        "insufficient_data_share": round(insufficient_n / len(player_status), 4) if player_status else 0.0,
        "bh_survivors": sum(1 for c in tested if c["p_adj"] < BH_ALPHA),
        "escalations": escalations,
        "k5_metrics": metrics,
    }


if __name__ == "__main__":
    result = run_sweep()
    for k, v in result.items():
        if k != "k5_metrics":
            print(f"[k_sweep_physical_v1] {k}: {v}")
    print(f"[k_sweep_physical_v1] k5_metrics: {result['k5_metrics']}")
