"""NBA context-shooting axis 2: vs-defensive-scheme split (DESCRIPTIVE_ONLY).

Wires data/cache/atlas_player_vs_scheme_splits.parquet (701 rows; columns
player_id, by_scheme, best_scheme, worst_scheme,
scheme_ts_pct_best_minus_worst, n_games_total, value, _cv_fields, n,
confidence, as_of='2026-05-31') into the nba_context_shooting_defadj family:
which players' efficiency swings most between their best- and worst-scheme
matchups.

ATLAS IS A SNAPSHOT, NOT REFRESHABLE -- caveat is mandatory verbatim (see
CAVEAT below): this is a single as-of='2026-05-31' cut over the 2024-25 era
(NBA API blocked from re-mining it), so it is a 2024-25-era read only and is
NEVER applied to 2025-26 without an explicit decay caveat.

PREREGISTERED FLOOR (declared before scoring): n_games_total >= 20 -- the
atlas's own reported sample-size column, same order of magnitude as the
boxscore-side qualifying floors.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.platformkit.intel_validation.nba_context_defadj_asof import name_lookup

REPO_ROOT = Path(__file__).resolve().parents[3]
_ATLAS_PATH = REPO_ROOT / "data" / "cache" / "atlas_player_vs_scheme_splits.parquet"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_SNAPSHOT = _OUT_DIR / "nba_context_scheme_snapshot.parquet"

MIN_GAMES_TOTAL = 20
CLAIM_ID = "nba_context_shooting_scheme_ts_swing_2024_25_era"
CAVEAT_ATLAS_SNAPSHOT = (
    "atlas 2024-25-era snapshot; not refreshable (NBA API blocked); do not apply to "
    "2025-26 without decay caution."
)


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def build_claims(box: pd.DataFrame | None = None, atlas_path: Path = _ATLAS_PATH) -> list[dict[str, Any]]:
    if not atlas_path.exists():
        print(f"SKIP {CLAIM_ID}: atlas file not found ({atlas_path}) -- claim not emitted")
        return [{
            "claim_id": CLAIM_ID, "kind": "ranking", "ranking": [], "n_considered": 0,
            "n_excluded_below_floor": 0, "criteria": {}, "source_files": [], "question": "",
            "computed_at": datetime.now(timezone.utc).isoformat(), "edge_claimed": False, "caveats": [],
        }]
    atlas = pd.read_parquet(atlas_path)
    names = name_lookup(box) if box is not None else {}

    snap = atlas[["player_id", "n_games_total", "scheme_ts_pct_best_minus_worst",
                  "best_scheme", "worst_scheme"]].dropna(subset=["scheme_ts_pct_best_minus_worst"]).copy()
    snap["player_name"] = snap["player_id"].map(names).fillna(snap["player_id"].astype(str))
    snap = snap.rename(columns={"scheme_ts_pct_best_minus_worst": "raw_value"})
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    snap.to_parquet(_SNAPSHOT, index=False)

    n_considered = int(len(snap))
    qualifiers = snap[snap["n_games_total"] >= MIN_GAMES_TOTAL].copy()
    qualifiers = qualifiers.sort_values("raw_value", ascending=False).reset_index(drop=True)
    n_excluded = n_considered - int(len(qualifiers))

    ranking = [
        {"rank": i, "player_id": int(r.player_id), "player_name": str(r.player_name),
         "value": round(float(r.raw_value), 4), "n": int(r.n_games_total),
         "best_scheme": r.best_scheme, "worst_scheme": r.worst_scheme}
        for i, r in enumerate(qualifiers.itertuples(index=False), start=1)
    ]
    return [{
        "claim_id": CLAIM_ID,
        "kind": "ranking",
        "question": "NBA (2024-25-era atlas): which players' TS% swings most between their best- and worst-defensive-scheme matchups?",
        "criteria": {
            "metric": "scheme_ts_pct_best_minus_worst", "formula": "raw_value",
            "window": "atlas_vs_scheme_splits_2024_25_era", "aggregate": None,
            "min_sample": {"n_games_total": MIN_GAMES_TOTAL}, "direction": "desc",
            "value_precision": 4, "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [_rel(_SNAPSHOT)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            CAVEAT_ATLAS_SNAPSHOT,
            f"min_sample floor n_games_total>={MIN_GAMES_TOTAL} (the atlas's own reported sample size).",
            "DESCRIPTIVE_ONLY -- no forward/predictive test is possible over a single as-of snapshot; "
            "no forecasting/market claim.",
        ],
    }]
