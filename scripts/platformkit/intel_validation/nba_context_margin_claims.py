"""NBA context-shooting axis 3: score-margin split (DESCRIPTIVE_ONLY).

Wires data/cache/atlas_player_score_margin_splits.parquet (540 rows; columns
player_id, leading, tied, trailing (JSON-string dicts w/ pts_pg, fga_pg,
fg3m_pg, ...), pace, shot_mix, _thresholds (leading>=+5/trailing<=-5),
_cv_fields, n, confidence, as_of='2026-05-31') into the
nba_context_shooting_defadj family: which players' usage (FGA/game) drops
most when leading vs trailing -- a descriptive "engagement collapses when
comfortable" label, not a forecast.

ATLAS IS A SNAPSHOT, NOT REFRESHABLE -- same mandatory caveat as axis 2 (see
CAVEAT_ATLAS_SNAPSHOT): 2024-25-era cut, do not apply to 2025-26 without
decay caution.

PREREGISTERED FLOOR (declared before scoring): n >= 20 (the atlas's own
reported sample-size column) AND both leading.fga_pg/trailing.fga_pg parse
to a non-null number.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.platformkit.intel_validation.nba_context_defadj_asof import name_lookup

REPO_ROOT = Path(__file__).resolve().parents[3]
_ATLAS_PATH = REPO_ROOT / "data" / "cache" / "atlas_player_score_margin_splits.parquet"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_SNAPSHOT = _OUT_DIR / "nba_context_margin_snapshot.parquet"

MIN_N = 20
CLAIM_ID = "nba_context_shooting_margin_usage_collapse_2024_25_era"
CAVEAT_ATLAS_SNAPSHOT = (
    "atlas 2024-25-era snapshot; not refreshable (NBA API blocked); do not apply to "
    "2025-26 without decay caution."
)


def _parse_struct(val: Any) -> dict:
    if isinstance(val, dict):
        return val
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return {}
    try:
        return json.loads(val)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _empty_claim() -> dict[str, Any]:
    return {
        "claim_id": CLAIM_ID, "kind": "ranking", "ranking": [], "n_considered": 0,
        "n_excluded_below_floor": 0, "criteria": {}, "source_files": [], "question": "",
        "computed_at": datetime.now(timezone.utc).isoformat(), "edge_claimed": False, "caveats": [],
    }


def build_claims(box: pd.DataFrame | None = None, atlas_path: Path = _ATLAS_PATH) -> list[dict[str, Any]]:
    if not atlas_path.exists():
        print(f"SKIP {CLAIM_ID}: atlas file not found ({atlas_path}) -- claim not emitted")
        return [_empty_claim()]
    atlas = pd.read_parquet(atlas_path)
    names = name_lookup(box) if box is not None else {}

    rows = []
    for r in atlas.itertuples(index=False):
        leading = _parse_struct(getattr(r, "leading", None))
        trailing = _parse_struct(getattr(r, "trailing", None))
        lead_fga = leading.get("fga_pg")
        trail_fga = trailing.get("fga_pg")
        if lead_fga is None or trail_fga is None:
            continue
        rows.append({
            "player_id": int(r.player_id),
            "player_name": names.get(int(r.player_id), str(r.player_id)),
            "n": int(getattr(r, "n", 0) or 0),
            "raw_value": float(trail_fga) - float(lead_fga),
        })
    snap = pd.DataFrame(rows)
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not snap.empty:
        snap.to_parquet(_SNAPSHOT, index=False)

    n_considered = int(len(snap))
    if n_considered == 0:
        print(f"SKIP {CLAIM_ID}: 0 rows parsed leading/trailing fga_pg -- claim not emitted")
        return [_empty_claim()]

    qualifiers = snap[snap["n"] >= MIN_N].copy()
    qualifiers = qualifiers.sort_values("raw_value", ascending=False).reset_index(drop=True)
    n_excluded = n_considered - int(len(qualifiers))

    ranking = [
        {"rank": i, "player_id": int(r.player_id), "player_name": str(r.player_name),
         "value": round(float(r.raw_value), 4), "n": int(r.n)}
        for i, r in enumerate(qualifiers.itertuples(index=False), start=1)
    ]
    return [{
        "claim_id": CLAIM_ID,
        "kind": "ranking",
        "question": "NBA (2024-25-era atlas): which players' shot volume (FGA/game) drops most when leading vs trailing?",
        "criteria": {
            "metric": "trailing_fga_pg_minus_leading_fga_pg", "formula": "raw_value",
            "window": "atlas_score_margin_splits_2024_25_era", "aggregate": None,
            "min_sample": {"n": MIN_N}, "direction": "desc", "value_precision": 4, "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [_rel(_SNAPSHOT)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            CAVEAT_ATLAS_SNAPSHOT,
            f"min_sample floor n>={MIN_N} (the atlas's own reported sample size).",
            "raw_value = trailing FGA/game minus leading FGA/game (>=+5 leading / <=-5 trailing per "
            "the atlas's own _thresholds); a positive value describes usage rising when trailing / "
            "collapsing when comfortable -- a descriptive label, not a forecast.",
            "DESCRIPTIVE_ONLY -- no forward/predictive test is possible over a single as-of snapshot; "
            "no forecasting/market claim.",
        ],
    }]
