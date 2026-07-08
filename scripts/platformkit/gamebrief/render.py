"""ASCII rendering of an assemble.py brief dict. <=120 cols, ASCII only (no
box-drawing/unicode -- this repo's console is cp1252). The JSON form is just
the dict assemble() already returned; this module only prints it readably.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Dict

_RULE = "=" * 100
_SUB = "-" * 100


def _ordinal(n: Any) -> str:
    if n is None:
        return "?"
    n = int(n)
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _ascii(s: str) -> str:
    """Fold to ASCII (e.g. Jokic for Jokic-with-diacritic) -- this repo's console
    is cp1252 and must never be handed a raw non-ASCII codepoint."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def _na_line(label: str, block: Dict[str, Any]) -> str:
    return f"  [{label}] not available -- {block.get('reason', 'no reason given')}"


def _team_section(team: str, block: Dict[str, Any]) -> str:
    lines = [_SUB, f"TEAM: {team}", _SUB]

    top3 = block.get("top3_fga_season_to_date") or []
    if top3:
        names = ", ".join(f"{p['player_name']} ({p['fga_season_to_date']:.0f} FGA)" for p in top3)
        lines.append(f"  Top-3 FGA (season-to-date, leak-free): {names}")
    else:
        lines.append("  Top-3 FGA: not available (no prior boxscore rows)")

    inj = block["injuries"]
    if inj["status"] == "ok":
        lines.append("  Injuries (latest status as-of game date):")
        for r in inj["reports"]:
            tag = " [TOP-3 FGA]" if r["is_top3_fga"] else ""
            lines.append(f"    - {r['player']} ({r['status']}){tag}: {r['detail']}")
            if r.get("usage_redistribution_note"):
                lines.append(f"        usage-redistribution: {r['usage_redistribution_note']}")
    else:
        lines.append(_na_line("Injuries", inj))

    news = block["news"]
    if news["status"] == "ok":
        lines.append("  Recent news:")
        for h in news["headlines"]:
            lines.append(f"    - {h}")
    else:
        lines.append(_na_line("News", news))

    grav = block["gravity"]
    if grav["status"] == "ok":
        leaders = "; ".join(f"{g['player_name']} ({g['gravity_proxy']:+.3f})" for g in grav["leaders"])
        lines.append(f"  Gravity leaders (teammate eFG on vs off court): {leaders}")
    else:
        lines.append(_na_line("Gravity", grav))

    syn = block["lineup_synergy"]
    if syn["status"] == "ok":
        for lu in syn["lineups"]:
            lines.append(
                f"  Top lineup [{lu['lineup_key']}] {lu['minutes']:.0f} min: "
                f"net {lu['net_per48']:+.1f}/48, synergy resid {lu['synergy_residual']:+.1f}")
    else:
        lines.append(_na_line("Lineup synergy", syn))

    oo = block["on_off"]
    if oo["status"] == "ok":
        swings = "; ".join(f"{p['player_name']} ({p['net_swing']:+.1f}/48 on-off)" for p in oo["players"])
        lines.append(f"  On/off net-rating swing: {swings}")
    else:
        lines.append(_na_line("On/off", oo))

    luck = block["shooting_luck_last5"]
    if luck["status"] == "ok":
        lines.append(
            f"  Shooting luck, last {luck['n_games']} games: "
            f"xPts {luck['avg_xpts']:.1f} vs actual {luck['avg_actual_pts']:.1f} "
            f"(luck {luck['avg_luck']:+.1f}/gm)")
    else:
        lines.append(_na_line("Shooting luck", luck))

    return "\n".join(lines)


def _concession_section(cm: Dict[str, Any]) -> str:
    lines = [_SUB, "CONCESSION MATCHUP", _SUB]
    if cm["status"] != "ok":
        lines.append(_na_line("Concession matchup", cm))
        return "\n".join(lines)
    for team, side in cm["sides"].items():
        if side["status"] != "ok":
            lines.append(f"  {team}: {_na_line('concession', side).strip()}")
            continue
        lines.append(
            f"  {team} concedes: overall eFG {side['overall_efg_allowed']:.3f} "
            f"(rank {side['overall_efg_allowed_rank_worst_to_best']}/{cm['league_size']} worst-to-best), "
            f"rim eFG {side['rim_efg_allowed']:.3f} "
            f"(rank {side['rim_efg_allowed_rank_worst_to_best']}/{cm['league_size']})")
    for team in cm["sides"]:
        opp = next((t for t in cm["sides"] if t != team), None)
        diet = cm.get("shot_diet", {}).get(team, {})
        if diet.get("status") != "ok":
            lines.append(f"  {team} shot diet: not available -- {diet.get('reason', 'no reason given')}")
            continue
        lines.append(
            f"  {team} takes {diet['rim_share']:.1%} of shots at rim "
            f"({_ordinal(diet['rim_share_rank_most_to_least'])}-most, season-to-date as-of); "
            f"{opp} concedes rank-{diet['opp_rim_efg_allowed_rank_worst_to_best'] or '?'} rim eFG")
        lines.append(
            f"  {team} takes {diet['fg3_share']:.1%} of shots from 3 "
            f"({_ordinal(diet['fg3_share_rank_most_to_least'])}-most, season-to-date as-of); "
            f"{opp} concedes rank-{diet['opp_fg3_efg_allowed_rank_worst_to_best'] or '?'} above-the-break-3 eFG")
    return "\n".join(lines)


def render(brief: Dict[str, Any]) -> str:
    if "error" in brief:
        return f"GAME BRIEF -- ERROR: {brief['error']}"

    m = brief["matchup"]
    elo = brief["elo_win_prob"]
    rest = brief["rest_and_schedule"]
    lines = [_RULE, f"GAME BRIEF: {m['away']} @ {m['home']}  ({m['date']}, game_id={m['game_id']})", _RULE]
    lines.append(
        f"Elo pregame win prob (leak-free walk-forward): "
        f"{m['home']} {elo['home_win_prob']:.1%} / {m['away']} {elo['away_win_prob']:.1%} "
        f"(n_prior_games={elo['n_prior_games_in_history']})")
    if rest["status"] == "ok":
        lines.append(
            f"Rest: {m['home']} {rest['rest_days_home']} day(s) rest "
            f"(b2b={rest['home_b2b']}) | {m['away']} {rest['rest_days_away']} day(s) rest "
            f"(b2b={rest['away_b2b']})")
    else:
        lines.append(_na_line("Rest/schedule", rest))

    lines.append(_team_section(m["home"], brief["teams"][m["home"]]))
    lines.append(_team_section(m["away"], brief["teams"][m["away"]]))
    lines.append(_concession_section(brief["concession_matchup"]))

    lines.append(_SUB)
    lines.append("HONESTY LABELS (verdict from data/cache/intel_claims/claim_weights.jsonl, or absence thereof):")
    for section, label in brief["honesty_labels"].items():
        lines.append(f"  {section}: {label}")
    lines.append(_RULE)
    return _ascii("\n".join(lines))
