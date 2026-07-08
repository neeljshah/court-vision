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

entity_key is resolved PER (metric, window), not once for the whole family:
a family's claims can mix entity_key spellings across metrics -- e.g.
nba_fit_ingredient_claims has archetype metrics keyed 'pid' (player) while
vacancy_share is keyed 'team_posgroup' (a composite 'MIL|GUARD' string).
Capturing a single family-level entity_key from the first claim row used to
force every OTHER metric through that one mapping -- a silent zero-match
UNTESTABLE for any metric whose real key differed. relevance_gate.run_family
now dispatches each metric's own (entity_key, values) independently.

PAIR-KEYED families (entity_key is a list, e.g. ['player_id','team_id'] for
nba_on_off_claims/nba_gravity_proxy_claims, ['team_id','lineup_key'] for
nba_lineup_spacing_claims): a bare dict.get(list) is a TypeError (unhashable
list), so these are resolved explicitly. If the pair contains 'team_id' the
ranked metric is averaged across that team's pair entries per (metric,
window) and folded into the ordinary entity_key=='team' path. Otherwise the
metric is simply not stored (no team mapping to fall back to) -- caught by
relevance_gate's catch-all dispatch as a clean UNTESTABLE, never a raise.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

from scripts.platformkit.gamebrief.team_ids import TEAM_ID_TO_ABBR

REPO_ROOT = Path(__file__).resolve().parents[3]
CLAIMS_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"

# (metric, window) -> (entity_key, {entity_id: value})
FeatureTable = Dict[Tuple[str, str], Tuple[str, Dict[str, float]]]

_SEASON_RE = re.compile(r"(\d{4})[_-](\d{2})")


_PLAIN_YEAR_RE = re.compile(r"^year_(\d{4})$")


def window_to_season(window: Optional[str], style: str = "split") -> Optional[str]:
    """'season_2024_25' / '2024-25' -> '2024-25' (style='split', NBA); or
    'year_2024' -> '2024' (style='plain', mlb/soccer/tennis -- single
    calendar-year seasons). Unlabeled -> None.

    Only PLAIN full-season windows qualify -- home/away/career/surface/
    division splits ('year_2024_clay', 'season_2024_25_home') return None so
    the gate never conditions on a partial-vintage slice."""
    if not window:
        return None
    w = window.strip().lower()
    if "home" in w or "away" in w or "career" in w:
        return None
    if style == "plain":
        m = _PLAIN_YEAR_RE.fullmatch(w)
        return m.group(1) if m else None
    m = _SEASON_RE.search(w)
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}"


def _resolve_entity_key(ekey) -> str:
    """A single-string entity_key passes through unchanged. A pair-list
    entity_key (e.g. ['player_id','team_id']) resolves to 'team' if it names
    team_id (aggregation handled by _team_paired_values below), else to a
    'pair_no_team:<keys>' marker -- a plain string, so it stays hashable for
    every downstream `entity_key == ...` / `entity_key in {...}` check."""
    if isinstance(ekey, list):
        return "team" if "team_id" in ekey else f"pair_no_team:{','.join(map(str, ekey))}"
    return str(ekey)


def _team_paired_values(ranking) -> Dict[str, float]:
    """Pair-keyed ranking (entity_key contains 'team_id'): mean the ranked
    metric's value across all pair entries sharing a team_id, for this one
    (metric, window) claim. Works whether the OTHER pair key is a player
    (nba_on_off/gravity_proxy: mean over that team's rostered players) or a
    lineup (nba_lineup_spacing: mean over that team's tracked lineups).

    Numeric NBA franchise ids (1610612xxx) are remapped to tricodes here --
    the gate's games_df keys teams by tricode (BOS/DEN), so leaving raw ids
    silently zeroes every fdiff (a fake NULL, not a tested one)."""
    sums: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    for r in ranking:
        team = r.get("team_id")
        val = r.get("value")
        if team is None or val is None:
            continue
        key = TEAM_ID_TO_ABBR.get(team, str(team)) if isinstance(team, int) else str(team)
        sums[key] = sums.get(key, 0.0) + float(val)
        counts[key] = counts.get(key, 0) + 1
    return {k: sums[k] / counts[k] for k in sums}


def load_family_features(family: str, claims_dir: Optional[Path] = None) -> FeatureTable:
    """Read `<family>.jsonl` -> {(metric, window): (entity_key, {entity: value})}.

    entity_key is resolved per claim line (see module docstring -- a family's
    metrics can carry different keys) and always a plain string (see
    _resolve_entity_key), never the raw list a pair-keyed family carries.
    Malformed lines are skipped (the store's own validation is the source of
    truth for VERIFIED; here we only need the numbers)."""
    claims_dir = claims_dir or CLAIMS_DIR
    path = claims_dir / f"{family}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"claims file not found: {path}")

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
            metric = cr.get("metric")
            window = cr.get("window")
            ranking = row.get("ranking", [])
            if not (ekey and metric and window and ranking):
                continue
            if isinstance(ekey, list):
                if "team_id" not in ekey:
                    continue   # pair-keyed, no team mapping -- clean UNTESTABLE downstream, not a raise
                values = _team_paired_values(ranking)
            else:
                values = {}
                for r in ranking:
                    ent = r.get(ekey)
                    val = r.get("value")
                    if ent is None or val is None:
                        continue
                    values[str(ent)] = float(val)
            if values:
                table[(metric, window)] = (_resolve_entity_key(ekey), values)
    return table


def prior_season_metrics(table: FeatureTable, eval_season: str,
                          style: str = "split") -> Dict[str, Tuple[str, Dict[str, float]]]:
    """Select {metric: (entity_key, {entity: value})} for the season STRICTLY
    ONE BEFORE eval_season (leak-free design (a)). style='split': '2025-26' ->
    looks for a window resolving to '2024-25' (NBA). style='plain': '2026' ->
    '2025' (mlb/soccer/tennis, single calendar-year seasons)."""
    if style == "plain":
        want = str(int(eval_season) - 1)
    else:
        start = int(eval_season.split("-")[0])
        want = f"{start - 1:04d}-{(start) % 100:02d}"
    out: Dict[str, Tuple[str, Dict[str, float]]] = {}
    for (metric, window), (entity_key, values) in table.items():
        if window_to_season(window, style) == want:
            out[metric] = (entity_key, values)  # plain full-season only (splits already None)
    return out


if __name__ == "__main__":  # tiny self-check on a known team store
    tbl = load_family_features("nba_team_box_rate")
    pri = prior_season_metrics(tbl, "2025-26")
    assert "team_pts_per_game" in pri
    ek, vals = pri["team_pts_per_game"]
    assert ek == "team", ek
    assert len(vals) >= 20
    assert window_to_season("season_2024_25_home") is None
    assert window_to_season("2024-25") == "2024-25"
    assert window_to_season("year_2024", "plain") == "2024"
    assert window_to_season("year_2024_clay", "plain") is None
    assert prior_season_metrics({("m", "year_2024"): ("team", {"x": 1.0})}, "2025", "plain") \
        == {"m": ("team", {"x": 1.0})}
    print(f"OK entity_key={ek} prior_metrics={sorted(pri)}")
