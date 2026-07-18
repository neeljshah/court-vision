"""Emit shooting-intel rankings as SHARED CLAIMS CONTRACT rows (JSONL).

Consumes domains/basketball_nba/player_intel_shooting.py only -- no other
model, no LLM recall. Each claim's "formula" is a literal pandas/column
expression over data/domains/basketball_nba/player_boxscores.parquet so an
independent validator can recompute it from source_files + criteria alone.

Outputs:
    data/cache/intel_claims/nba_shooting_claims.jsonl   (machine contract)
    data/cache/intel_claims/nba_shooting_answers.md      (human-readable)
"""
from __future__ import annotations

import json
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from domains.basketball_nba.player_intel_shooting import (
    BOXSCORE_PATH,
    COMPOSITE_WEIGHTS,
    LAST_N_GAMES,
    MIN_FG3A_PG_3PT_TABLE,
    MIN_FG3A_PG_COMPOSITE,
    MIN_FGA_PG_COMPOSITE,
    MIN_FGA_PG_EFF_TABLE,
    MIN_GAMES_COMPOSITE,
    compute_window_table,
    load_boxscores,
    rank_composite,
    rank_single_metric,
    window_rows,
)

CLAIMS_PATH = Path("data/cache/intel_claims/nba_shooting_claims.jsonl")
ANSWERS_PATH = Path("data/cache/intel_claims/nba_shooting_answers.md")

# Machine-executable aggregate expressions (whitelist grammar: sum/mean/count/
# count_distinct + arithmetic). Grouping is declared in criteria.aggregate,
# window slicing in criteria.window_spec -- together they make every claim
# mechanically recomputable by an independent validator.
COMPOSITE_FORMULA = (
    f"{COMPOSITE_WEIGHTS['ts_pct']}*(sum(pts)/(2*(sum(fga)+0.44*sum(fta))))"
    f" + {COMPOSITE_WEIGHTS['efg_pct']}*((sum(fgm)+0.5*sum(fg3m))/sum(fga))"
    f" + {COMPOSITE_WEIGHTS['ft_pct']}*(sum(ftm)/sum(fta))"
)

SINGLE_FORMULAS = {
    "fg3_pct": "sum(fg3m)/sum(fg3a)",
    "ts_pct": "sum(pts)/(2*(sum(fga)+0.44*sum(fta)))",
    "efg_pct": "(sum(fgm)+0.5*sum(fg3m))/sum(fga)",
}

# How each min_sample floor column is DERIVED per player from raw rows --
# mirrors _aggregate(): games = distinct game_ids, *_pg = total / games.
DERIVED_EXPRS = {
    "games": "count_distinct(game_id)",
    "fga_pg": "sum(fga)/count_distinct(game_id)",
    "fg3a_pg": "sum(fg3a)/count_distinct(game_id)",
}

VALUE_PRECISION = 4  # ranking values are rounded to this many decimal places


def _window_spec(window: str) -> dict:
    """Mechanically-reproducible window declaration (criteria.window_spec)."""
    if window == "last_20":
        return {"kind": "last_n_games", "n": LAST_N_GAMES, "order_by": "date",
                "season": None, "season_col": None}
    if window.startswith("season_"):
        return {"kind": "season", "season": window[len("season_"):],
                "season_col": "season", "n": None, "order_by": None}
    raise ValueError(f"unknown window: {window}")


ENTITY_KEY = "player_id"  # this module's ranking entity; other sports' claim
# producers pass their own (pitcher_id/team_id/...) -- see criteria.entity_key
# in scripts/platformkit/intel_validation/claims_validator.py.


def _aggregate_contract(min_sample: dict) -> dict:
    """criteria.aggregate: group key + derivation of every floor column."""
    return {
        "group_by": ENTITY_KEY,
        "derived": {col: DERIVED_EXPRS[col] for col in min_sample},
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ascii_name(name: str) -> str:
    """ASCII-safe transliteration (never lossy '?') so accented names (e.g.
    Bogdanovic, Jokic) stay readable in an ASCII-only console/file instead of
    being corrupted to '?'. NFKD-decompose then drop combining marks."""
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _ranking_rows(survivors: pd.DataFrame, value_col: str, top_n: int) -> list[dict]:
    out = []
    for i, row in survivors.head(top_n).iterrows():
        out.append({
            "rank": int(i) + 1,
            "player_id": int(row["player_id"]),
            "player_name": _ascii_name(str(row["player_name"])),
            "value": round(float(row[value_col]), 4),
            "n": int(row["games"]),
        })
    return out


def build_claims(df: pd.DataFrame, window: str, top_n: int = 10) -> list[dict]:
    table = compute_window_table(df, window)
    n_considered = int(len(table))
    claims = []
    computed_at = _now_iso()

    comp_survivors, comp_excluded = rank_composite(table)
    comp_caveats = list(_window_caveats(window, df))
    if len(comp_survivors) == 0:
        comp_caveats.append(
            f"EMPTY RESULT: 0 of {n_considered} players clear all composite floors "
            f"in this window (most commonly the games>={MIN_GAMES_COMPOSITE} floor "
            "on a partial/short window). This is an honest floor-driven exclusion, "
            "not a bug -- see n_excluded_below_floor."
        )
    comp_min_sample = {
        "games": MIN_GAMES_COMPOSITE,
        "fga_pg": MIN_FGA_PG_COMPOSITE,
        "fg3a_pg": MIN_FG3A_PG_COMPOSITE,
    }
    claims.append({
        "claim_id": f"nba_shooting_composite_{window}",
        "kind": "ranking",
        "question": f"Who are the top {top_n} best shooters (composite) in window={window}?",
        "criteria": {
            "metric": "composite",
            "formula": COMPOSITE_FORMULA,
            "window": window,
            "window_spec": _window_spec(window),
            "aggregate": _aggregate_contract(comp_min_sample),
            "min_sample": comp_min_sample,
            "direction": "desc",
            "value_precision": VALUE_PRECISION,
            "entity_key": ENTITY_KEY,
        },
        "ranking": _ranking_rows(comp_survivors, "composite", top_n),
        "source_files": [BOXSCORE_PATH],
        "computed_at": computed_at,
        "n_considered": n_considered,
        "n_excluded_below_floor": comp_excluded,
        "caveats": comp_caveats,
    })

    for metric, floor_label in (
        ("fg3_pct", f"fg3a_pg>={MIN_FG3A_PG_3PT_TABLE}"),
        ("ts_pct", f"fga_pg>={MIN_FGA_PG_EFF_TABLE}"),
        ("efg_pct", f"fga_pg>={MIN_FGA_PG_EFF_TABLE}"),
    ):
        survivors, excluded = rank_single_metric(table, metric)
        min_sample = (
            {"fg3a_pg": MIN_FG3A_PG_3PT_TABLE}
            if metric == "fg3_pct"
            else {"fga_pg": MIN_FGA_PG_EFF_TABLE}
        )
        claims.append({
            "claim_id": f"nba_shooting_{metric}_{window}",
            "kind": "ranking",
            "question": f"Top {top_n} by {metric} in window={window} (floor: {floor_label})",
            "criteria": {
                "metric": metric,
                "formula": SINGLE_FORMULAS[metric],
                "window": window,
                "window_spec": _window_spec(window),
                "aggregate": _aggregate_contract(min_sample),
                "min_sample": min_sample,
                "direction": "desc",
                "value_precision": VALUE_PRECISION,
                "entity_key": ENTITY_KEY,
            },
            "ranking": _ranking_rows(survivors, metric, top_n),
            "source_files": [BOXSCORE_PATH],
            "computed_at": computed_at,
            "n_considered": n_considered,
            "n_excluded_below_floor": excluded,
            "caveats": _window_caveats(window, df),
        })
    return claims


def _window_caveats(window: str, df: pd.DataFrame) -> list[str]:
    """Season-window caveats derive their row-count/date-range text from the
    ACTUAL rows on disk each run (never a hardcoded snapshot) -- a season
    that was partial when this file was last edited (e.g. 2025-26 mid-season)
    reads as full automatically once the boxscores parquet is refreshed,
    with no stale-caveat drift."""
    if window.startswith("season_"):
        rows = window_rows(df, window)
        n_rows = int(len(rows))
        if n_rows == 0:
            return [f"NO ROWS on disk for {window}."]
        date_min, date_max = rows["date"].min(), rows["date"].max()
        return [
            f"{n_rows} player-game rows on disk for {window} "
            f"({date_min.date()} to {date_max.date()})."
        ]
    if window == "last_20":
        return [
            f"Recency window = last {LAST_N_GAMES} games PLAYED per player (equal weight, "
            "not exponentially decayed), pooled across every season's rows on disk.",
            "Players who changed teams mid-window are pooled across teams (this module "
            "does not split by team).",
        ]
    return []


def write_claims(all_claims: list[dict]) -> None:
    CLAIMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CLAIMS_PATH, "w", encoding="ascii") as f:
        for c in all_claims:
            f.write(json.dumps(c, ensure_ascii=True) + "\n")


def write_answers_md(all_claims: list[dict]) -> None:
    lines = ["# NBA Shooting Intel -- Answers (auto-generated, do not hand-edit)", ""]
    lines.append(
        "Source: data/domains/basketball_nba/player_boxscores.parquet "
        "(raw per-player-per-game rows). Seasons on disk: 2024-25 (full), "
        "2025-26 (partial, through 2026-01-19)."
    )
    lines.append("")
    for c in all_claims:
        lines.append(f"## {c['question']}")
        lines.append(
            f"- window: `{c['criteria']['window']}` | metric: `{c['criteria']['metric']}` "
            f"| floor: `{c['criteria']['min_sample']}` | direction: {c['criteria']['direction']}"
        )
        lines.append(
            f"- n_considered={c['n_considered']} n_excluded_below_floor={c['n_excluded_below_floor']}"
        )
        for cav in c["caveats"]:
            lines.append(f"- CAVEAT: {cav}")
        lines.append("")
        lines.append("| rank | player | value | n games |")
        lines.append("|---|---|---|---|")
        for r in c["ranking"]:
            lines.append(f"| {r['rank']} | {r['player_name']} | {r['value']} | {r['n']} |")
        lines.append("")
    ANSWERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ANSWERS_PATH.write_text("\n".join(lines), encoding="ascii")


def run(windows: tuple[str, ...] = ("last_20", "season_2025-26", "season_2024-25"), top_n: int = 10) -> list[dict]:
    df = load_boxscores()
    all_claims: list[dict] = []
    for w in windows:
        all_claims.extend(build_claims(df, w, top_n=top_n))
    write_claims(all_claims)
    write_answers_md(all_claims)
    return all_claims


if __name__ == "__main__":
    claims = run()
    print(f"wrote {len(claims)} claims to {CLAIMS_PATH}")
    print(f"wrote human-readable answers to {ANSWERS_PATH}")
