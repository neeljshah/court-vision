"""Cross-reference the market-strength atlas with mechanism exposure sheets.

Reads ONLY files already written by the two verified showcase modules
(out/market_strength_atlas.json, out/mechanism_exposure.json) -- zero new
computation, zero new data. Answers "which mechanisms are live for the NBA
teams whose closing-market rating moved the most" as one descriptive join;
every row cites both source artifacts. No causal or predictive claim, no
edge/ROI language (see .claude/rules/no-edge-claims.md).

Also repackages the atlas build behind the AI_CONSUMER_CONTRACT envelope
(status/source_artifact/as_of/source_corpus) at data/cache/analytics/
strength_atlas.json, so a consumer does not have to parse the raw showcase
artifact's ad hoc shape.

Run: python -m scripts.platformkit.atlas_exposure_join
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SHOWCASE_OUT = REPO / "scripts" / "platformkit" / "analytics_showcase" / "out"
ATLAS_SRC = SHOWCASE_OUT / "market_strength_atlas.json"
EXPOSURE_SRC = SHOWCASE_OUT / "mechanism_exposure.json"
ATLAS_SOURCE_ARTIFACT = "scripts/platformkit/analytics_showcase/out/market_strength_atlas.json"
EXPOSURE_SOURCE_ARTIFACT = "scripts/platformkit/analytics_showcase/out/mechanism_exposure.json"
STRENGTH_ATLAS_CACHE = REPO / "data" / "cache" / "analytics" / "strength_atlas.json"
JOIN_OUT = REPO / "data" / "cache" / "analytics" / "atlas_exposure.json"
START_RATING = 1500.0  # walk_forward's per-team starting Elo rating in market_strength_atlas.py


def strength_atlas_cache(atlas: dict) -> dict:
    """Repackage the atlas build behind the AI_CONSUMER_CONTRACT envelope (status/source_artifact/as_of)."""
    sport_as_of = [row["as_of"] for row in atlas["sports"].values() if row.get("as_of")]
    return {
        "status": "ok" if sport_as_of else "no_data",
        "source_artifact": ATLAS_SOURCE_ARTIFACT,
        "as_of": max(sport_as_of) if sport_as_of else None,
        "source_corpus": {sport: row.get("source") for sport, row in atlas["sports"].items()},
        "edge_claimed": False,
        "generated_at": atlas["generated_at"],
        "sports": atlas["sports"],
    }


def team_deltas(sport_atlas: dict) -> dict[str, float]:
    """rating - START_RATING for every team the atlas ranked (its top_5 + bottom_5)."""
    if sport_atlas.get("status") != "ok":
        return {}
    ratings = sport_atlas["latest_ratings"]
    return {row["team"]: round(row["rating"] - START_RATING, 3)
            for row in ratings["top_5"] + ratings["bottom_5"]}


def team_mechanism_counts(game_sheets: list[dict]) -> dict[str, dict[str, int]]:
    """How many of this team's games (this corpus, this season) had each mechanism live."""
    counts: dict[str, dict[str, int]] = {}
    for sheet in game_sheets:
        for team in (sheet["home_team"], sheet["away_team"]):
            bucket = counts.setdefault(team, {})
            for exposure in sheet["exposures"]:
                bucket[exposure["mechanism"]] = bucket.get(exposure["mechanism"], 0) + 1
    return counts


def join_rows(atlas: dict, exposure: dict) -> list[dict]:
    """One row per atlas-ranked NBA team: its rating delta + season-wide live-mechanism game counts,
    largest-|delta| first."""
    deltas = team_deltas(atlas["sports"]["basketball_nba"])
    counts = team_mechanism_counts(exposure["game_sheets"])
    ordered = sorted(deltas.items(), key=lambda kv: -abs(kv[1]))
    return [{"team": team, "rating_delta_vs_start": delta,
             "live_mechanism_game_counts": counts.get(team, {})}
            for team, delta in ordered]


def build(atlas: dict | None = None, exposure: dict | None = None) -> dict:
    """Build the join artifact. Pass atlas/exposure dicts directly for tests; None reads out/ on disk."""
    atlas = atlas if atlas is not None else json.loads(ATLAS_SRC.read_text(encoding="utf-8"))
    exposure = exposure if exposure is not None else json.loads(EXPOSURE_SRC.read_text(encoding="utf-8"))
    rows = join_rows(atlas, exposure)
    as_of_candidates = [atlas["sports"]["basketball_nba"].get("as_of"), exposure.get("as_of")]
    return {
        "label": "DESCRIPTIVE_ONLY", "edge_claimed": False,
        "verdict": "Which mechanisms are live for the NBA teams whose closing-market rating moved the "
                   "most; a composition of two already-verified artifacts, no new computation and no "
                   "causal or predictive claim.",
        "source_artifact": [ATLAS_SOURCE_ARTIFACT, EXPOSURE_SOURCE_ARTIFACT],
        "as_of": max((v for v in as_of_candidates if v), default=None),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_teams": len(rows), "rows": rows,
    }


def main() -> dict:
    if not ATLAS_SRC.exists() or not EXPOSURE_SRC.exists():
        raise FileNotFoundError("run market_strength_atlas and mechanism_exposure first (see out/ paths above)")
    atlas = json.loads(ATLAS_SRC.read_text(encoding="utf-8"))
    exposure = json.loads(EXPOSURE_SRC.read_text(encoding="utf-8"))

    STRENGTH_ATLAS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    STRENGTH_ATLAS_CACHE.write_text(json.dumps(strength_atlas_cache(atlas), indent=2, ensure_ascii=True),
                                     encoding="ascii")
    result = build(atlas, exposure)
    JOIN_OUT.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="ascii")

    print("wrote", STRENGTH_ATLAS_CACHE)
    print("wrote", JOIN_OUT)
    print(json.dumps(result["rows"][:3], ensure_ascii=True))
    return result


if __name__ == "__main__":
    main()
