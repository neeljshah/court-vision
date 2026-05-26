"""Batch-rebuild jersey_name_map.json for all tracked games using CommonTeamRoster.

ORIGIN: Rescued from root-level `.tmp_rebuild_jersey_maps.py` on 2026-05-25
during dead-file cleanup (see docs/_audit_dead_files_2026-05-25.md Section 1).
This is the only on-disk copy of the v10 batch jersey-map rebuild logic — the
canonical `scripts/rebuild_jersey_maps.py` referenced in `.tmp_memory_v10.sh`
was never created. Kept as a maintenance utility for re-segmenting jersey maps
when the per-game `_by_team` structure needs to be regenerated from rosters.

NOTE: Hard-coded `/workspace/nba-ai-system/...` paths reflect its RunPod
origin. Adjust DATA_TRACKING / CACHE_PATH to your environment before running.

Strategy:
1. Read each game's tracking_data.csv to find the 2 team_abbrevs + their color labels (green/white).
2. Call CommonTeamRoster per unique team (cached) to get {jersey_num: player_name} for that team's 2024-25 roster.
3. For each game, build _by_team = {color_label: {jersey_str: name}} from the 2 teams' rosters.
4. Write jersey_name_map.json with both the legacy flat dict (first-write-wins) and _by_team.

Run once. Future tracker runs will overwrite via player_resolver.py (post-v9 patch).
"""
import csv
import json
import time
from pathlib import Path

DATA_TRACKING = Path("/workspace/nba-ai-system/data/tracking")
CACHE_PATH = Path("/workspace/nba-ai-system/data/nba/team_roster_jerseys_2024-25.json")
SEASON = "2024-25"

# Load existing roster cache if it exists
if CACHE_PATH.exists():
    team_roster_cache = json.loads(CACHE_PATH.read_text())
    print(f"loaded roster cache: {len(team_roster_cache)} teams")
else:
    team_roster_cache = {}

def get_team_roster(team_abbrev: str) -> dict:
    """Return {jersey_str: name} for given team's 2024-25 roster."""
    if team_abbrev in team_roster_cache:
        return team_roster_cache[team_abbrev]
    # Need team_id for the API
    from nba_api.stats.static import teams as nba_teams
    t = nba_teams.find_team_by_abbreviation(team_abbrev)
    if not t:
        print(f"  WARN: unknown abbrev {team_abbrev}")
        team_roster_cache[team_abbrev] = {}
        return {}
    from nba_api.stats.endpoints import commonteamroster
    time.sleep(0.6)
    try:
        roster = commonteamroster.CommonTeamRoster(team_id=t["id"], season=SEASON).get_data_frames()[0]
    except Exception as e:
        print(f"  ERR roster {team_abbrev}: {e}")
        team_roster_cache[team_abbrev] = {}
        return {}
    result = {}
    for _, row in roster.iterrows():
        jersey = str(row.get("NUM", "")).strip()
        name = str(row.get("PLAYER", "")).strip()
        if jersey and name:
            result[jersey] = name
    team_roster_cache[team_abbrev] = result
    print(f"  fetched {team_abbrev}: {len(result)} jersey entries")
    return result


def game_abbrev_to_color(game_dir: Path) -> dict:
    """Read tracking_data and derive {abbrev: color_label}."""
    tracking = game_dir / "tracking_data.csv"
    if not tracking.exists():
        return {}
    abbrev_to_color = {}
    with open(tracking) as f:
        for i, row in enumerate(csv.DictReader(f)):
            ta = row.get("team_abbrev", "").strip()
            tc = row.get("team", "").strip()
            if ta and tc and ta not in abbrev_to_color:
                abbrev_to_color[ta] = tc
                if len(abbrev_to_color) >= 2:
                    break
            if i > 50000:
                break
    return abbrev_to_color


game_dirs = sorted([d for d in DATA_TRACKING.iterdir() if d.is_dir()])
print(f"found {len(game_dirs)} game dirs")

n_built = 0
n_skipped = 0
n_errors = 0
for gd in game_dirs:
    map_path = gd / "jersey_name_map.json"
    abbrev_to_color = game_abbrev_to_color(gd)
    if len(abbrev_to_color) < 2:
        n_skipped += 1
        continue
    by_team = {}
    flat = {}
    for abbrev, color in abbrev_to_color.items():
        roster = get_team_roster(abbrev)
        if not roster:
            continue
        by_team[color] = roster.copy()
        # Flat: first-write-wins (legacy fallback for old consumers)
        for jersey, name in roster.items():
            if jersey not in flat:
                flat[jersey] = name
    if not by_team:
        n_errors += 1
        continue
    flat["_by_team"] = by_team
    try:
        # Backup once before overwriting
        bak = gd / "jersey_name_map.json.bak_rebuild"
        if map_path.exists() and not bak.exists():
            bak.write_bytes(map_path.read_bytes())
        map_path.write_text(json.dumps(flat, indent=2, ensure_ascii=False))
        n_built += 1
    except Exception as e:
        print(f"  ERR write {gd.name}: {e}")
        n_errors += 1

# Persist roster cache
CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
CACHE_PATH.write_text(json.dumps(team_roster_cache, indent=2, ensure_ascii=False))

print()
print(f"=== DONE ===")
print(f"  built: {n_built}")
print(f"  skipped (no team data in tracking): {n_skipped}")
print(f"  errors: {n_errors}")
print(f"  team-roster cache entries: {len(team_roster_cache)}")
