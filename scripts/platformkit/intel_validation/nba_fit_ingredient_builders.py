"""Builder functions for nba_fit_ingredient_claims.py (split out to respect the
<=300 LOC/file rail -- the entrypoint had grown to 350 lines). Pure move, zero
behavior change: constants + the three build_*_claim() functions + their two
small helpers live here; nba_fit_ingredient_claims.py imports them back and
keeps build_all_claims/write_claims/main.

See nba_fit_ingredient_claims.py's module docstring for the full spec
(families a/b/c, leak discipline, window-stamp rationale).
"""
from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[3]

_PLAYER_ROLES = REPO_ROOT / "data" / "cache" / "team_system" / "player_roles.parquet"
_SCHEME_COVERAGE = REPO_ROOT / "data" / "cache" / "team_system" / "scheme_coverage.parquet"
_PLAYER_BOXSCORES = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"

# Claim window stamps -- see nba_fit_ingredient_claims.py's docstring for the
# per-family vintage evidence (why each is career_to_date / a real season).
ARCHETYPE_WINDOW = "career_to_date"
SCHEME_IDENTITY_SEASON = "2025-26"
ROLE_VACANCY_SEASON = "2024-25"

_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_VACANCY_SNAPSHOT = _OUT_DIR / "nba_fit_role_vacancy_snapshot.parquet"

# (a) minutes-based floor: below ~10 mpg a player's attribute signal is
# garbage-time noise, not a stable rotation role -- 431/507 (85%) clear it.
MIN_MPG = 10.0
MIN_TEAM_POSGROUP_N = 3  # (c) min qualifying player-rows per (team, posgroup)

_ATTRIBUTE_COLS = (
    "posgroup", "archetype", "creation", "playmaking", "spacing",
    "rim_pressure", "rebounding", "rim_protect", "perimeter_d", "self_create",
    "usage_pct", "scorer_pct",
)


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)


def _ascii_summary(d: dict[str, Any] | None) -> dict[str, Any] | None:
    """ASCII-fold any string values for stdout display only (cp1252 console
    rail) -- mirrors intel_query/ask.py's _ascii_name. Stored claim rows are
    untouched; json.dumps already ensure_ascii-escapes them on write."""
    if d is None:
        return None
    out = dict(d)
    for k, v in out.items():
        if isinstance(v, str):
            decomposed = unicodedata.normalize("NFKD", v)
            out[k] = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return out


# (a) player archetype/attribute profile ------------------------------------

def build_archetype_claim() -> dict[str, Any]:
    df = pd.read_parquet(_PLAYER_ROLES)
    n_considered = len(df)
    qualifiers = df[df["mpg"] >= MIN_MPG].copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers = qualifiers.sort_values("usage_pct", ascending=False).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        entry = {
            "rank": i,
            "pid": int(row.pid),
            "player_name": str(row.player),
            "value": round(float(row.usage_pct), 4),
            "n": None,  # season aggregate, not a repeated-trial sample
            "team": str(row.team),
        }
        for col in _ATTRIBUTE_COLS:
            v = getattr(row, col)
            entry[col] = round(float(v), 4) if isinstance(v, float) else v
        ranking.append(entry)

    rel_source = str(_PLAYER_ROLES.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": "nba_fit_archetype_profile_current",
        "kind": "ranking",
        "question": "What is each qualifying player's archetype/attribute profile (current)?",
        "criteria": {
            "metric": "usage_pct",
            "formula": "usage_pct",
            "window": ARCHETYPE_WINDOW,  # see constant comment above
            "min_sample": {"mpg": MIN_MPG},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "pid",
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            f"FULL POPULATION above stated minutes floor mpg>={MIN_MPG} (garbage-time-noise "
            "floor, not a top-N cap); below-floor players counted in n_excluded_below_floor, "
            "never silently dropped. Attribute scores are season-to-date descriptive profile "
            "scores (0-1 scaled), not a prediction of future performance.",
            "SCOUTING/descriptive composition only -- no predictive or market/$ edge claimed.",
        ],
    }


# (b) team scheme identity ---------------------------------------------------

def build_scheme_identity_claim() -> dict[str, Any]:
    # every team_scheme row is one real team with a defined identity -- no
    # floor to apply (n_obs already reflects the sample the builder used).
    df = pd.read_parquet(_SCHEME_COVERAGE)
    team_rows = df[df["row_type"] == "team_scheme"].copy()
    n_considered = len(team_rows)
    n_excluded = 0
    team_rows = team_rows.sort_values("wf_ppp_allowed_z", ascending=False).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(team_rows.itertuples(index=False), start=1):
        ranking.append({
            "rank": i,
            "team": str(row.team),
            "value": round(float(row.wf_ppp_allowed_z), 4),
            "n": int(row.n_obs) if pd.notna(row.n_obs) else None,
            "dominant_tag": str(row.dominant_tag) if pd.notna(row.dominant_tag) else None,
            "best_scheme": str(row.best_scheme) if pd.notna(row.best_scheme) else None,
            "confidence": str(row.confidence) if pd.notna(row.confidence) else None,
        })

    rel_source = str(_SCHEME_COVERAGE.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": "nba_fit_team_scheme_identity_current",
        "kind": "ranking",
        "question": "What is each team's dominant defensive scheme identity (current)?",
        "criteria": {
            "metric": "wf_ppp_allowed_z",
            "formula": "wf_ppp_allowed_z",
            "window": SCHEME_IDENTITY_SEASON,
            "min_sample": {},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "team",
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            "FULL POPULATION: all 30 NBA teams have a team_scheme row in this cache artifact "
            "(scripts/team_system/'s builder is human-gated and untouched by this lane; this "
            "module only READS the already-materialized cache). dominant_tag/best_scheme are "
            "the actual scheme-identity strings; wf_ppp_allowed_z is the ranked numeric metric "
            "the validator recomputes, carried alongside for a concrete per-team value.",
            "SCOUTING/descriptive scheme label only -- no predictive or market/$ edge claimed.",
        ],
    }


# (c) role vacancy per team x posgroup ---------------------------------------

def build_role_vacancy_snapshot() -> tuple[Path, pd.DataFrame]:
    """Join box scores to posgroup; compute is_below_median = pts_per_min
    below the LEAGUE-WIDE median for that posgroup (not per-team, so
    vacancy_share stays comparable across teams); materialize one row per
    (player_id, team) to _VACANCY_SNAPSHOT, keyed by a single composite
    team_posgroup string column -- the aggregate contract's recompute_
    aggregate() only supports a single hashable group_by column, so
    "team|posgroup" (not a [team, posgroup] list) is the entity id the
    validator groups by to independently re-derive vacancy_share =
    mean(is_below_median). Returns (path, snapshot_df)."""
    box = pd.read_parquet(_PLAYER_BOXSCORES)
    if "season" in box.columns:
        box = box[box["season"].astype(str) == ROLE_VACANCY_SEASON]  # see constant comment above
    roles = pd.read_parquet(_PLAYER_ROLES)[["pid", "posgroup"]].drop_duplicates(subset=["pid"])

    per_player_team = box.groupby(["player_id", "team"], as_index=False).agg(
        min_sum=("min", "sum"), pts_sum=("pts", "sum")
    )
    per_player_team = per_player_team[per_player_team["min_sum"] > 0].copy()
    per_player_team["pts_per_min"] = per_player_team["pts_sum"] / per_player_team["min_sum"]

    joined = per_player_team.merge(
        roles, left_on="player_id", right_on="pid", how="inner"
    ).drop(columns=["pid"])
    posgroup_median = joined.groupby("posgroup")["pts_per_min"].median()
    joined["posgroup_median_pts_per_min"] = joined["posgroup"].map(posgroup_median)
    joined["is_below_median"] = (
        joined["pts_per_min"] < joined["posgroup_median_pts_per_min"]
    ).astype("int64")
    joined["team_posgroup"] = joined["team"] + "|" + joined["posgroup"]

    snapshot = joined[
        ["player_id", "team", "posgroup", "team_posgroup", "min_sum", "pts_per_min",
         "is_below_median"]
    ].reset_index(drop=True)
    _write_parquet(snapshot, _VACANCY_SNAPSHOT)
    return _VACANCY_SNAPSHOT, snapshot


def build_role_vacancy_claim() -> dict[str, Any]:
    out_path, snapshot = build_role_vacancy_snapshot()

    vacancy = snapshot.groupby(["team_posgroup", "team", "posgroup"], as_index=False).agg(
        vacancy_share=("is_below_median", "mean"), n_players=("is_below_median", "count")
    )
    n_considered = len(vacancy)
    qualifying = vacancy[vacancy["n_players"] >= MIN_TEAM_POSGROUP_N].copy()
    n_excluded = n_considered - len(qualifying)
    qualifying = qualifying.sort_values("vacancy_share", ascending=False).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(qualifying.itertuples(index=False), start=1):
        ranking.append({
            "rank": i,
            "team_posgroup": str(row.team_posgroup),
            "value": round(float(row.vacancy_share), 4),
            "n": int(row.n_players),
            "team": str(row.team),
            "posgroup": str(row.posgroup),
        })

    rel_source = str(out_path.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": "nba_fit_role_vacancy_by_team_posgroup_current",
        "kind": "ranking",
        "question": "Which team x posgroup slots are held mostly by below-median producers (current)?",
        "criteria": {
            "metric": "vacancy_share",
            "formula": "mean(is_below_median)",
            "window": ROLE_VACANCY_SEASON,
            "min_sample": {"n_players": MIN_TEAM_POSGROUP_N},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "team_posgroup",
            "aggregate": {
                "group_by": "team_posgroup",
                "derived": {"n_players": "count(is_below_median)"},
            },
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            "DEFINITION (this module's own descriptive metric, see build_role_vacancy_snapshot "
            "docstring): vacancy_share = share of a team's posgroup minute-holders below the "
            "LEAGUE-WIDE median pts-per-minute for that posgroup. Higher = more of that team's "
            f"minutes at that posgroup went to below-median producers. FULL POPULATION: every "
            f"team_posgroup pair with >= {MIN_TEAM_POSGROUP_N} qualifying player-rows gets a "
            "row; pairs below floor counted in n_excluded_below_floor, never silently dropped.",
            "SCOUTING/descriptive proxy only -- not a prediction of future vacancy or "
            "performance, no market/$ edge claimed.",
        ],
    }
