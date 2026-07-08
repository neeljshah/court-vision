"""Opponent scheme-concession fingerprint: per DEFENDING team, the shot diet
it allows -- built from every shot in the full-season play-by-play corpus
(data/cache/team_system/pbp/*.json, 1192 games 2025-26, liveData shape
verified on 0022500003.json).

For every shot action (actionType "2pt"/"3pt"), the shooting team is the
`teamId` on the action; the defense is simply the OTHER team_id present in
that game's actions (every game here has exactly 2 team_ids, verified).

ZONE: classify_zone (zone_geometry.py) from x/y court position -- NOT the
PBP `area` field, which is populated on only ~12% of shots in this corpus
(CDN-native files carry it; the ESPN-derived majority, a different schema
with a text `description` instead, carries area=None). Reading `area`
directly was this module's v1 and silently dropped ~88% of shots; see
zone_geometry.py's docstring for the fix and its calibration.

ASSISTED: a made shot carries `assistPersonId` when passed to on CDN-native
files (verified on 0022500003.json actionNumber 8); ESPN-derived files lack
that field but embed the same fact in `description` text, e.g. "Cason
Wallace makes 3-foot two point shot (Ajay Mitchell assists)" -- so assisted
= assistPersonId present OR "assist" in description.lower(), covering both
shapes. Unassisted makes and all misses have neither.

FASTBREAK/TRANSITION: the `qualifiers` list carries "fastbreak" on
CDN-native files ONLY -- ESPN-derived files have no `qualifiers` key and no
reliable text signal for it either (verified: zero "fast break" mentions in
a sampled ESPN-derived game's descriptions). share_fastbreak_allowed is
therefore UNDERCOUNTED wherever a defense's games skew ESPN-derived; this is
a real coverage gap, not a formula bug -- flagged in the claim's caveats.

FT-RATE ALLOWED: opponent FTA (freethrow actions, with the defense resolved
the same as shots) / that defense's n_shots_faced (2pt+3pt attempts allowed).

OUTPUT: data/cache/team_system/composition/concession_2025_26.parquet, one
row per team_id (the DEFENSE), with per-zone share/eFG-allowed columns plus
share_assisted_allowed, share_fastbreak_allowed, ft_rate_allowed.

NETWORK: zero. CLI: python -m domains.basketball_nba.composition.concession_profiles
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from domains.basketball_nba.composition.zone_geometry import ZONES, classify_zone
from domains.basketball_nba.lineups.pbp_lineups import _PBP_DIR

REPO_ROOT = Path(__file__).resolve().parents[3]
_OUT_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "composition" / "concession_2025_26.parquet"

_ASSIST_TEXT_RE = re.compile(r"assist", re.IGNORECASE)


def _is_assisted(a: dict[str, Any], made: bool) -> bool:
    if not made:
        return False
    if a.get("assistPersonId") is not None:
        return True
    return bool(_ASSIST_TEXT_RE.search(a.get("description", "")))


def load_game_shots(game_json: dict[str, Any]) -> pd.DataFrame:
    """One row per shot ATTEMPT with the DEFENDING team already resolved."""
    game_id = game_json["game"]["gameId"]
    actions = game_json["game"]["actions"]
    team_ids = sorted({a["teamId"] for a in actions if a.get("teamId")})
    rows = []
    for a in actions:
        if a.get("actionType") not in ("2pt", "3pt") or not a.get("teamId") or a.get("x") is None:
            continue
        offense = a["teamId"]
        defense = next((t for t in team_ids if t != offense), None)
        if defense is None:
            continue
        made = a.get("shotResult") == "Made"
        is_3 = a["actionType"] == "3pt"
        rows.append({
            "game_id": game_id, "offense_team_id": offense, "defense_team_id": defense,
            "zone": classify_zone(float(a["x"]), float(a["y"]), is_3), "made": int(made), "is_3": int(is_3),
            "fgm": int(made), "fg3m": int(made and is_3),
            "assisted": int(_is_assisted(a, made)),
            "fastbreak": int("fastbreak" in (a.get("qualifiers") or [])),
        })
    return pd.DataFrame(rows)


def load_game_fta(game_json: dict[str, Any]) -> pd.DataFrame:
    """One row per free-throw ATTEMPT, with the DEFENDING team resolved the
    same way as load_game_shots (the other team_id in the game)."""
    actions = game_json["game"]["actions"]
    team_ids = sorted({a["teamId"] for a in actions if a.get("teamId")})
    rows = []
    for a in actions:
        if a.get("actionType") == "freethrow" and a.get("teamId"):
            offense = a["teamId"]
            defense = next((t for t in team_ids if t != offense), None)
            if defense is not None:
                rows.append({"game_id": game_json["game"]["gameId"], "defense_team_id": defense})
    return pd.DataFrame(rows)


def aggregate_concession(shots_df: pd.DataFrame, fta_df: pd.DataFrame) -> pd.DataFrame:
    """Per defense_team_id: zone mix/eFG allowed + assisted/transition share + FT-rate allowed."""
    if shots_df.empty:
        return pd.DataFrame()

    overall = shots_df.groupby("defense_team_id").agg(
        n_shots_faced=("made", "size"),
        fgm_allowed=("fgm", "sum"), fg3m_allowed=("fg3m", "sum"),
        n_assisted_makes=("assisted", "sum"), n_makes=("made", "sum"),
        n_fastbreak=("fastbreak", "sum"),
    ).reset_index()
    overall["overall_efg_allowed"] = (overall["fgm_allowed"] + 0.5 * overall["fg3m_allowed"]) / overall["n_shots_faced"]
    overall["share_assisted_allowed"] = overall["n_assisted_makes"] / overall["n_makes"].replace(0, pd.NA)
    overall["share_fastbreak_allowed"] = overall["n_fastbreak"] / overall["n_shots_faced"]

    fta_counts = fta_df.groupby("defense_team_id").size().rename("fta").reset_index() if not fta_df.empty else pd.DataFrame(columns=["defense_team_id", "fta"])
    ft_rate = overall[["defense_team_id", "n_shots_faced"]].merge(fta_counts, on="defense_team_id", how="left").fillna({"fta": 0})
    ft_rate["ft_rate_allowed"] = ft_rate["fta"] / ft_rate["n_shots_faced"]

    zone_pivot = shots_df.groupby(["defense_team_id", "zone"]).agg(
        fga=("made", "size"), fgm=("fgm", "sum"), fg3m=("fg3m", "sum"),
    ).reset_index()
    zone_pivot["efg"] = (zone_pivot["fgm"] + 0.5 * zone_pivot["fg3m"]) / zone_pivot["fga"]

    out = overall[["defense_team_id", "n_shots_faced", "overall_efg_allowed", "share_assisted_allowed", "share_fastbreak_allowed"]].copy()
    out = out.merge(ft_rate[["defense_team_id", "ft_rate_allowed"]], on="defense_team_id", how="left")
    for z in ZONES:
        zdf = zone_pivot[zone_pivot["zone"] == z].set_index("defense_team_id")
        out[f"{z}_fga_allowed"] = out["defense_team_id"].map(zdf["fga"]).fillna(0).astype(int)
        out[f"{z}_efg_allowed"] = out["defense_team_id"].map(zdf["efg"])
        out[f"{z}_share_allowed"] = out[f"{z}_fga_allowed"] / out["n_shots_faced"]

    return out.sort_values("rim_efg_allowed").reset_index(drop=True)


def build_concession_table(pbp_dir: Path = _PBP_DIR, limit: int | None = None) -> pd.DataFrame:
    files = sorted(pbp_dir.glob("*.json"))
    if limit:
        files = files[:limit]
    shot_frames, fta_frames = [], []
    for fp in files:
        game_json = json.loads(fp.read_text(encoding="utf-8"))
        shot_frames.append(load_game_shots(game_json))
        fta_frames.append(load_game_fta(game_json))
    shots_df = pd.concat(shot_frames, ignore_index=True) if shot_frames else pd.DataFrame()
    fta_df = pd.concat(fta_frames, ignore_index=True) if fta_frames else pd.DataFrame()
    return aggregate_concession(shots_df, fta_df)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build NBA defense shot-concession profiles")
    parser.add_argument("--out", type=str, default=str(_OUT_PATH))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    table = build_concession_table(limit=args.limit)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out_path, index=False)
    print(f"defenses={len(table)} -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
