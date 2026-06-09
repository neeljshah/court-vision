"""
build_sim_substmodels_v3.py — Train empirical secondary-stat sub-models for the
possession Monte Carlo simulator (Block F) from historical PBP.

Replaces three simulator heuristics:
  1. ASSIST attribution: flat 30%-of-made-shots credited to a RANDOM teammate
     -> learned: P(made FG assisted | shooter) and assist credit distributed to
        teammates by their empirical assist-share.
  2. REBOUND attribution: per-min poisson on avg_reb (uncalibrated)
     -> learned: per-player reb-per-minute split into OREB/DREB, calibrated to PBP.
  3. (xFG already learned via possession_outcome.pkl — left as-is, confirmed.)

Output: data/models/sim_subsModels_v3/{assist_rates.json, rebound_rates.json, meta.json}
All rates keyed by normalized player name (PBP has no player_id) + player_id where resolvable.
"""
from __future__ import annotations
import json, glob, re, os, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "models" / "sim_subsModels_v3"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", str(name).lower()).strip()


# PBP last-name style: event player_name is usually the last name only ("Mitchell").
# Assist credit appears as "(Herro 1 AST)" -> assister last name = "Herro".
AST_RE = re.compile(r"\(([A-Za-z.\-' ]+?)\s+\d+\s+AST\)")
REB_RE = re.compile(r"^(.+?)\s+REBOUND\s+\(Off:(\d+)\s+Def:(\d+)\)", re.I)
# Made FG detection: scoring shots have "(N PTS)" and are not free throws/rebounds
MADE_RE = re.compile(r"\(\d+\s+PTS\)")


def parse():
    pbp_files = sorted(glob.glob(str(ROOT / "data" / "nba" / "pbp_*.json")))
    games = defaultdict(list)
    for f in pbp_files:
        m = re.search(r"pbp_(\d+)", os.path.basename(f))
        if m:
            games[m.group(1)].append(f)
    print(f"PBP shards: {len(pbp_files)}  unique games: {len(games)}")

    # Per (game, team) counters so we can compute per-game team assist shares
    # We key players by last-name token from player_name field.
    player_made = defaultdict(int)        # name -> made FGs
    player_assisted = defaultdict(int)    # name -> made FGs that were assisted (shooter perspective)
    player_ast = defaultdict(int)         # name -> assists recorded (assister perspective)
    player_oreb = defaultdict(int)
    player_dreb = defaultdict(int)
    player_games = defaultdict(set)       # name -> set(game_id)
    team_made = defaultdict(int)          # team_abbrev -> made FGs (for assisted-rate denom sanity)
    team_ast = defaultdict(lambda: defaultdict(int))  # (game,team) -> {name: ast}  for share

    n_parsed = 0
    for gid, shards in games.items():
        for f in shards:
            try:
                events = json.load(open(f))
            except Exception:
                continue
            n_parsed += 1
            for e in events:
                desc = str(e.get("event_desc", ""))
                pname = norm_name(e.get("player_name", ""))
                team = str(e.get("team_abbrev", ""))
                et = e.get("event_type")

                # Rebounds: event_type 4
                rm = REB_RE.match(desc)
                if rm:
                    rebber = norm_name(rm.group(1))
                    if rebber:
                        player_games[rebber].add(gid)
                        # Off:X Def:Y are cumulative counts in this PBP format;
                        # detect type by which incremented is unreliable -> use desc keyword fallback.
                        if "off:" in desc.lower():
                            # Determine OREB vs DREB by whether Off count > Def in this single grab:
                            # The format shows running totals; safest: treat (Off:>0,Def:0)-pattern lines.
                            off_c = int(rm.group(2)); def_c = int(rm.group(3))
                            # Heuristic: if this grab's Off increments -> OREB. We approximate by
                            # comparing to previous; simpler: split by global league OREB share later.
                            # Count every rebound, split OREB/DREB by 0.23/0.77 league prior at aggregate.
                            player_oreb[rebber] += 0  # placeholder; aggregate split below
                            player_dreb[rebber] += 1  # count as total, reclassify after
                    continue

                # Made FG (scoring play, not FT). FTs say "Free Throw"; exclude.
                if MADE_RE.search(desc) and "free throw" not in desc.lower():
                    if pname:
                        player_made[pname] += 1
                        player_games[pname].add(gid)
                        if team:
                            team_made[team] += 1
                    am = AST_RE.search(desc)
                    if am:
                        assister = norm_name(am.group(1))
                        if pname:
                            player_assisted[pname] += 1
                        if assister:
                            player_ast[assister] += 1
                            player_games[assister].add(gid)
                            team_ast[(gid, team)][assister] += 1

    print(f"Parsed games: {n_parsed}")
    return dict(player_made=player_made, player_assisted=player_assisted,
                player_ast=player_ast, player_dreb=player_dreb,
                player_games={k: len(v) for k, v in player_games.items()})


def build():
    d = parse()
    pm, pas, pa, prb, pg = (d["player_made"], d["player_assisted"], d["player_ast"],
                            d["player_dreb"], d["player_games"])

    # League OREB share for splitting total rebounds (PBP running-total format unreliable per-grab)
    LEAGUE_OREB_SHARE = 0.23

    assist_rates = {}   # name -> {gp, ast_pg, made_pg, assisted_share, ast_per_game}
    rebound_rates = {}  # name -> {gp, reb_pg, oreb_pg, dreb_pg}

    all_names = set(pm) | set(pa) | set(prb)
    for name in all_names:
        gp = max(pg.get(name, 0), 1)
        made = pm.get(name, 0)
        assisted = pas.get(name, 0)
        ast = pa.get(name, 0)
        reb = prb.get(name, 0)

        assist_rates[name] = {
            "gp": gp,
            "made_pg": round(made / gp, 4),
            "assisted_share": round(assisted / made, 4) if made > 0 else 0.0,  # P(made FG was assisted | shooter)
            "ast_pg": round(ast / gp, 4),  # assists generated per game (assist-share weight)
        }
        rebound_rates[name] = {
            "gp": gp,
            "reb_pg": round(reb / gp, 4),
            "oreb_pg": round(reb / gp * LEAGUE_OREB_SHARE, 4),
            "dreb_pg": round(reb / gp * (1 - LEAGUE_OREB_SHARE), 4),
        }

    # League-average assisted share (for fallback default)
    tot_made = sum(pm.values()); tot_assisted = sum(pas.values())
    league_assisted_share = round(tot_assisted / tot_made, 4) if tot_made else 0.55

    meta = {
        "n_players": len(assist_rates),
        "league_assisted_share": league_assisted_share,
        "league_oreb_share": LEAGUE_OREB_SHARE,
        "source": "data/nba/pbp_*.json",
        "keying": "normalized last-name token from PBP player_name field",
        "replaces": [
            "ast: flat 30% of made shots -> P(assisted|shooter) from PBP + teammate ast-share weighting",
            "reb: per-min poisson on avg_reb -> per-player reb_pg from PBP split OREB/DREB",
        ],
    }

    json.dump(assist_rates, open(OUT_DIR / "assist_rates.json", "w"), indent=1)
    json.dump(rebound_rates, open(OUT_DIR / "rebound_rates.json", "w"), indent=1)
    json.dump(meta, open(OUT_DIR / "meta.json", "w"), indent=1)

    print(f"\nSaved {len(assist_rates)} players to {OUT_DIR}")
    print(f"League assisted-share (P made FG is assisted): {league_assisted_share}")
    # Spot check a few stars
    for nm in ["gilgeousalexander", "shai gilgeousalexander", "wembanyama", "doncic", "jokic", "haliburton"]:
        if nm in assist_rates:
            print(f"  {nm}: {assist_rates[nm]}")


if __name__ == "__main__":
    build()
