"""Turn a claims family store into a per-entity numeric feature table.

Generic over families: every store in data/cache/intel_claims/ shares the
ranking[] contract documented in intel_query/claims_index.py -- each claim line
carries criteria.{metric, window, entity_key} plus a ranking[] of
{<entity_key>: id, value: float}. We expose the ranked metric value per entity
for each (metric, window) so the relevance gate can standardize and diff it.

LEAK NOTE: windows are SEASON-END aggregates. The gate only ever uses a
window whose season is STRICTLY PRIOR to the eval season (design (a) --
prior_season_claim_walkforward_v1). An unlabeled window ('current',
'career_to_date') returns season None and is refused by the gate.

ponytail: player-entity families are returned too, but they carry no
team/minutes in the payload, so the gate maps only entity_key=='team'
families. Upgrade path = roster+minutes join to aggregate players to teams.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[3]
CLAIMS_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"

# (metric, window) -> {entity_id: value}
FeatureTable = Dict[Tuple[str, str], Dict[str, float]]

_SEASON_RE = re.compile(r"(\d{4})[_-](\d{2})")


def window_to_season(window: Optional[str]) -> Optional[str]:
    """'season_2024_25' / '2024-25' -> '2024-25'; unlabeled -> None.

    Only PLAIN full-season windows qualify -- home/away/career splits return
    None so the gate never conditions on a partial-vintage slice."""
    if not window:
        return None
    w = window.strip().lower()
    if "home" in w or "away" in w or "career" in w:
        return None
    m = _SEASON_RE.search(w)
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}"


def load_family_features(family: str, claims_dir: Optional[Path] = None) -> Tuple[str, FeatureTable]:
    """Read `<family>.jsonl` -> (entity_key, {(metric, window): {entity: value}}).

    entity_key is taken from the first well-formed claim (families are
    homogeneous). Malformed lines are skipped (the store's own validation is
    the source of truth for VERIFIED; here we only need the numbers)."""
    claims_dir = claims_dir or CLAIMS_DIR
    path = claims_dir / f"{family}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"claims file not found: {path}")

    entity_key: Optional[str] = None
    table: FeatureTable = {}
    with open(path, "r", encoding="ascii", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            cr = row.get("criteria", {})
            ekey = cr.get("entity_key")
            if entity_key is None and ekey:
                entity_key = ekey   # capture even if this claim lacks a window
            metric = cr.get("metric")
            window = cr.get("window")
            ranking = row.get("ranking", [])
            if not (ekey and metric and window and ranking):
                continue
            values: Dict[str, float] = {}
            for r in ranking:
                ent = r.get(ekey)
                val = r.get("value")
                if ent is None or val is None:
                    continue
                values[str(ent)] = float(val)
            if values:
                table[(metric, window)] = values
    return (entity_key or "unknown"), table


def prior_season_metrics(table: FeatureTable, eval_season: str) -> Dict[str, Dict[str, float]]:
    """Select {metric: {entity: value}} for the season STRICTLY ONE BEFORE
    eval_season (leak-free design (a)). eval_season like '2025-26' -> looks for
    a window resolving to '2024-25'."""
    start = int(eval_season.split("-")[0])
    want = f"{start - 1:04d}-{(start) % 100:02d}"
    out: Dict[str, Dict[str, float]] = {}
    for (metric, window), values in table.items():
        if window_to_season(window) == want:
            out[metric] = values  # plain full-season only (splits already None)
    return out


if __name__ == "__main__":  # tiny self-check on a known team store
    ek, tbl = load_family_features("nba_team_box_rate")
    pri = prior_season_metrics(tbl, "2025-26")
    assert ek == "team", ek
    assert "team_pts_per_game" in pri and len(pri["team_pts_per_game"]) >= 20
    assert window_to_season("season_2024_25_home") is None
    assert window_to_season("2024-25") == "2024-25"
    print(f"OK entity_key={ek} prior_metrics={sorted(pri)}")
