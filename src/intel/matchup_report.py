"""matchup_report.py — DESCRIPTIVE head-to-head intelligence for ONE game.

Given a home tricode + away tricode (+ optional resolved rosters), this module
ASSEMBLES the already-shipped player dossiers (``src.intel.player_report``) and
team dossiers (``src.intel.team_report``) into a single coherent *matchup*
report that DESCRIBES how the two units project to clash:

  * team_clash         — offensive identity vs the opposing defensive identity,
                         pace environment, rebounding battle, FT battle, clutch.
  * scheme_edges       — directional scheme advantages (e.g. one team forces
                         turnovers while the other is turnover-prone).
  * player_edges       — per-player skill-vs-team-weakness leans, percentile
                         anchored (e.g. an elite OREB big vs a poor DREB team).
  * key_players        — top dossier-ranked players on each side.

DESIGN CONSTRAINTS (per build spec):
  * USE EXISTING DATA ONLY — player/team dossiers + their atlas percentiles.
  * DETERMINISTIC — rule/threshold/percentile synthesis. NO LLM-per-game.
  * HONEST — this report is *descriptive* and leak-safe by nature. It explicitly
    does NOT emit a predicted point estimate or a claimed accuracy lift. The
    predictive hypotheses the matchup *implies* are produced separately by
    :mod:`src.intel.game_preview` and flagged as UNVALIDATED CANDIDATES for the
    honest gate; they are NOT applied to any model here.

Public API:
    build_matchup_report(home, away, home_roster=None, away_roster=None,
                         team_ctx=None) -> dict
    MatchupReportBuilder

Schema is documented on :func:`build_matchup_report`.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional, Tuple

from src.intel import team_report as _tr
from src.intel.player_report import build_player_report, league_percentile

SCHEMA_VERSION = "matchup_report/1.0"

# A player edge fires when one side's skill percentile is high AND the opposing
# team is weak at defending / contesting it (low team percentile = bad).
_STRONG_PCT = 75.0          # player must be >= this percentile in a skill
_TEAM_WEAK_PCT = 0.35       # opposing team pctile (goodness, 0=worst) <= this
_TEAM_STRONG_PCT = 0.65     # opposing team pctile >= this (suppresses the edge)


# --------------------------------------------------------------------------- #
# Skill (player) -> opposing-team-weakness (team metric) mapping.
# Each entry: player skill metric -> (team ctx metric, human label, side_note)
# The team metric uses team_report league-context "pctile" (1.0 = best defence).
# A LOW team pctile means the opponent is BAD at stopping this skill -> edge.
# --------------------------------------------------------------------------- #
_SKILL_VS_TEAM: List[Tuple[str, str, str]] = [
    # player metric,            opposing team ctx key,                     friendly skill
    ("oreb_rate", "rebounding_scheme.dreb_pct", "offensive rebounding vs their defensive glass"),
    ("total_reb_rate", "rebounding_scheme.dreb_pct", "rebounding vs their defensive glass"),
    ("pts_3pt_share", "three_pt_defense.opp_3p_pct_allowed", "three-point scoring vs their perimeter D"),
    ("catch_shoot_efg", "three_pt_defense.opp_3p_pct_allowed", "catch-and-shoot vs their perimeter D"),
    ("rim_protection", "paint_defense.rim_fg_pct_allowed", "rim protection vs their interior attack"),
    ("ft_generation", "ft_foul_environment.pf_pg", "foul drawing vs their fouling tendency"),
    ("ast_pts_created", "turnover_forcing.opp_tov_pct_forced", "playmaking vs their turnover pressure"),
    ("post_up_ppp", "paint_defense.paint_fg_pct_allowed", "post scoring vs their paint D"),
    ("transition_pts_share", "transition_defense.opp_transition_pg", "transition scoring vs their transition D"),
]

# For skills whose matching team metric is "lower is better" defensively
# (e.g. rim_fg_pct_allowed: high = they allow a lot = WEAK). team_report already
# folds polarity into pctile (1.0 = best defence), so a LOW pctile == weak.


def _f(v: Any) -> Optional[float]:
    """Coerce to float, else None (module-level numeric helper)."""
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _team_metric_pctile(team_ctx: Dict[str, Any], metric: str, tri: str) -> Optional[float]:
    info = team_ctx.get(metric)
    if not info:
        return None
    entry = info.get("teams", {}).get(tri)
    if not entry:
        return None
    return entry.get("pctile")


def _player_skill_value(pid: int, metric: str) -> Optional[float]:
    """Pull the single comparable scalar for a skill metric from the player atlas."""
    from src.intel.player_report import _atlas_row, _metric_specs  # local import
    specs = _metric_specs()
    if metric not in specs:
        return None
    sec, acc, _ = specs[metric]
    row = _atlas_row(sec, pid)
    if row is None:
        return None
    try:
        return acc(row)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Team clash
# --------------------------------------------------------------------------- #
def _team_block_data(dossier: Dict[str, Any], block: str) -> Dict[str, Any]:
    b = (dossier.get("blocks") or {}).get(block) or {}
    return b.get("data") or {}


def _build_team_clash(home_d: Dict, away_d: Dict, team_ctx: Dict,
                      home: str, away: str) -> Dict[str, Any]:
    h_off = _team_block_data(home_d, "offensive_identity")
    a_off = _team_block_data(away_d, "offensive_identity")
    h_def = _team_block_data(home_d, "defensive_identity")
    a_def = _team_block_data(away_d, "defensive_identity")
    h_reb = _team_block_data(home_d, "rebounding")
    a_reb = _team_block_data(away_d, "rebounding")
    h_ff = _team_block_data(home_d, "ft_foul_environment")
    a_ff = _team_block_data(away_d, "ft_foul_environment")
    h_cl = _team_block_data(home_d, "clutch")
    a_cl = _team_block_data(away_d, "clutch")

    def _num(v):
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    # --- pace / possession environment -------------------------------------
    h_pace = _num(h_off.get("pace_pg"))
    a_pace = _num(a_off.get("pace_pg"))
    proj_pace = None
    if h_pace is not None and a_pace is not None:
        proj_pace = round((h_pace + a_pace) / 2.0, 2)
    pace_env = "average"
    if proj_pace is not None:
        if proj_pace >= 101.5:
            pace_env = "fast"
        elif proj_pace <= 98.0:
            pace_env = "slow"
    pace = {
        "home_pace": h_pace, "away_pace": a_pace,
        "home_pace_identity": h_off.get("pace_identity"),
        "away_pace_identity": a_off.get("pace_identity"),
        "projected_pace": proj_pace,
        "pace_environment": pace_env,
        "_note": "projected_pace = simple mean of the two teams' season pace "
                 "(descriptive midpoint, NOT a possession-model output).",
    }

    # --- offense vs defense (each direction) -------------------------------
    def _matchup(off_team, off_d, def_team, def_d):
        return {
            "offense": off_team,
            "defense": def_team,
            "off_rtg": _num(off_d.get("off_rtg")),
            "off_efg": _num(off_d.get("efg_pct")),
            "def_rtg": _num(def_d.get("def_rtg")),
            "def_coverage_scheme": def_d.get("coverage_scheme"),
            "def_rim_fg_pct_allowed": _num(def_d.get("rim_fg_pct_allowed")),
            "def_opp_3p_pct_allowed": _num(def_d.get("opp_3p_pct_allowed")),
            "def_opp_tov_pct_forced": _num(def_d.get("opp_tov_pct_forced")),
        }

    # --- rebounding battle --------------------------------------------------
    reb_battle = {
        "home_oreb_pct": _num(h_reb.get("oreb_pct")),
        "home_dreb_pct": _num(h_reb.get("dreb_pct")),
        "away_oreb_pct": _num(a_reb.get("oreb_pct")),
        "away_dreb_pct": _num(a_reb.get("dreb_pct")),
        "home_reb_identity": h_reb.get("reb_identity"),
        "away_reb_identity": a_reb.get("reb_identity"),
    }
    # who controls the glass (oreb of one vs dreb of the other)
    if reb_battle["home_oreb_pct"] is not None and reb_battle["away_dreb_pct"] is not None:
        reb_battle["home_oreb_vs_away_dreb"] = round(
            reb_battle["home_oreb_pct"] - (1 - reb_battle["away_dreb_pct"]), 4)
    if reb_battle["away_oreb_pct"] is not None and reb_battle["home_dreb_pct"] is not None:
        reb_battle["away_oreb_vs_home_dreb"] = round(
            reb_battle["away_oreb_pct"] - (1 - reb_battle["home_dreb_pct"]), 4)

    # --- FT battle ----------------------------------------------------------
    ft_battle = {
        "home_fta_pg": _num(h_ff.get("fta_pg")),
        "away_fta_pg": _num(a_ff.get("fta_pg")),
        "home_pf_pg": _num(h_ff.get("pf_pg")),
        "away_pf_pg": _num(a_ff.get("pf_pg")),
    }

    # --- clutch -------------------------------------------------------------
    clutch = {
        "home_clutch_net_rtg": _num(h_cl.get("clutch_net_rtg")),
        "away_clutch_net_rtg": _num(a_cl.get("clutch_net_rtg")),
    }

    return {
        "pace_environment": pace,
        "home_offense_vs_away_defense": _matchup(home, h_off, away, a_def),
        "away_offense_vs_home_defense": _matchup(away, a_off, home, h_def),
        "rebounding_battle": reb_battle,
        "ft_battle": ft_battle,
        "clutch": clutch,
    }


# --------------------------------------------------------------------------- #
# Scheme edges (team-level directional advantages)
# --------------------------------------------------------------------------- #
def _build_scheme_edges(home_d: Dict, away_d: Dict, team_ctx: Dict,
                        home: str, away: str) -> List[Dict[str, Any]]:
    edges: List[Dict[str, Any]] = []

    def _g(metric, tri):
        return _team_metric_pctile(team_ctx, metric, tri)

    # (offense team, defense team) directional scheme clashes
    pairs = [
        # turnover pressure vs ball security
        ("turnover_forcing.opp_tov_pct_forced", "offensive_scheme.tov_ratio",
         "forces turnovers", "is turnover-prone", "turnover_pressure"),
        # offensive glass vs defensive glass
        ("rebounding_scheme.oreb_pct", "rebounding_scheme.dreb_pct",
         "crashes the offensive glass", "is weak on the defensive glass", "rebounding"),
        # rim attack vs rim protection
        ("offensive_scheme.off_rtg", "paint_defense.rim_fg_pct_allowed",
         "is efficient inside", "is soft at the rim", "rim_attack"),
        # 3pt volume vs perimeter denial
        ("offensive_scheme.spacing_z", "three_pt_defense.opp_3pa_rate_allowed",
         "spaces the floor", "lets up 3-point volume", "perimeter"),
    ]
    sides = [(home, away, "home_attacks_away"), (away, home, "away_attacks_home")]
    for off_t, def_t, direction in sides:
        for off_metric, def_metric, off_phrase, def_phrase, tag in pairs:
            off_p = _g(off_metric, off_t)
            def_p = _g(def_metric, def_t)
            if off_p is None or def_p is None:
                continue
            # off side strong AND def side weak -> directional edge
            if off_p >= _TEAM_STRONG_PCT and def_p <= _TEAM_WEAK_PCT:
                magnitude = round((off_p - 0.5) + (0.5 - def_p), 4)  # 0..1
                edges.append({
                    "type": "scheme",
                    "tag": tag,
                    "direction": direction,
                    "attacker": off_t,
                    "defender": def_t,
                    "description": f"{off_t} {off_phrase} while {def_t} {def_phrase}",
                    "attacker_pctile": round(off_p, 3),
                    "defender_pctile": round(def_p, 3),
                    "magnitude": magnitude,
                    "provenance": {"off_metric": off_metric, "def_metric": def_metric,
                                   "source": "team_report league context"},
                })
    edges.sort(key=lambda e: e["magnitude"], reverse=True)
    return edges


# --------------------------------------------------------------------------- #
# Player edges (skill vs opposing team weakness)
# --------------------------------------------------------------------------- #
def _build_player_edges(home_reports: Dict[int, Dict], away_reports: Dict[int, Dict],
                        team_ctx: Dict, home: str, away: str) -> List[Dict[str, Any]]:
    edges: List[Dict[str, Any]] = []

    def _scan(reports: Dict[int, Dict], own_team: str, opp_team: str):
        for pid, rep in reports.items():
            name = rep.get("player_name") or f"Player {pid}"
            # require a meaningful role: skip deep bench (low minutes / no usage block)
            role = ((rep.get("archetype_role") or {}).get("data") or {})
            mins = role.get("minutes_pg")
            if mins is not None and mins < 12:
                continue
            for skill_metric, team_metric, skill_label in _SKILL_VS_TEAM:
                val = _player_skill_value(pid, skill_metric)
                p_pct = league_percentile(skill_metric, val)
                if p_pct is None or p_pct < _STRONG_PCT:
                    continue
                t_pct = _team_metric_pctile(team_ctx, team_metric, opp_team)
                if t_pct is None:
                    continue
                if t_pct <= _TEAM_WEAK_PCT:
                    # player is strong AND the opponent is weak at containing it
                    magnitude = round((p_pct / 100.0 - 0.5) + (0.5 - t_pct), 4)
                    edges.append({
                        "type": "player",
                        "player_id": pid,
                        "player_name": name,
                        "team": own_team,
                        "vs_team": opp_team,
                        "skill": skill_label,
                        "skill_metric": skill_metric,
                        "player_percentile": round(p_pct, 1),
                        "opp_team_metric": team_metric,
                        "opp_team_pctile": round(t_pct, 3),
                        "magnitude": magnitude,
                        "description": (f"{name} ({own_team}) — {skill_label}: "
                                        f"{p_pct:.0f}th-pct skill into {opp_team} "
                                        f"({t_pct*100:.0f}th-pct unit)"),
                    })

    _scan(home_reports, home, away)
    _scan(away_reports, away, home)
    edges.sort(key=lambda e: e["magnitude"], reverse=True)
    return edges


# --------------------------------------------------------------------------- #
# Key players (top dossier-ranked per side)
# --------------------------------------------------------------------------- #
def _key_players(reports: Dict[int, Dict], team: str, top_n: int = 4) -> List[Dict[str, Any]]:
    scored: List[Tuple[float, Dict]] = []
    for pid, rep in reports.items():
        role = ((rep.get("archetype_role") or {}).get("data") or {})
        usage_pct = role.get("usage_pct_rank") or 0
        mins = role.get("minutes_pg") or 0
        # rank by a simple role-importance heuristic
        score = (usage_pct or 0) + (mins or 0)
        arch = (role.get("archetype") or {})
        sw = (rep.get("strengths_weaknesses") or {})
        scored.append((score, {
            "player_id": pid,
            "player_name": rep.get("player_name") or f"Player {pid}",
            "team": team,
            "archetype": arch.get("label"),
            "usage_pct_rank": role.get("usage_pct_rank"),
            "minutes_pg": role.get("minutes_pg"),
            "top_strengths": [s["label"] for s in sw.get("strengths", [])[:3]],
        }))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored[:top_n]]


# --------------------------------------------------------------------------- #
# Key INDIVIDUAL matchups (offensive player vs likely defender + scheme)
# --------------------------------------------------------------------------- #
# Rough positional ordering used to pair an offensive player to a likely
# defender on the opposing side (no game-level tracking matchup data exists, so
# this is a position/archetype heuristic — surfaced honestly as "likely").
_POS_ORDER = {"guard": 0, "guard-forward": 1, "forward-guard": 1,
              "forward": 2, "forward-center": 3, "center-forward": 3, "center": 4}


def _pos_rank(pos: Optional[str]) -> int:
    if not pos:
        return 2
    return _POS_ORDER.get(str(pos).lower(), 2)


def _player_def_signature(rep: Dict[str, Any]) -> Dict[str, Any]:
    """Pull an individual player's defensive identity from his dossier."""
    role = ((rep.get("archetype_role") or {}).get("data") or {})
    d = (rep.get("defense") or {}).get("data") or {}
    dp = d.get("defensive_profile") or {}
    rim = dp.get("rim_protection") or {}
    sb = dp.get("steal_block_rate") or {}
    sw = rep.get("strengths_weaknesses") or {}
    ranks = {r.get("metric"): r.get("percentile") for r in (sw.get("ranked") or [])}
    return {
        "player_id": rep.get("player_id"),
        "player_name": rep.get("player_name"),
        "position": role.get("position"),
        "archetype": (role.get("archetype") or {}).get("label"),
        "blk_pg": rim.get("blk_pg"),
        "stl_pg": sb.get("stl_pg"),
        "rim_protection_pct_rank": ranks.get("rim_protection"),
        "event_defense_pct_rank": ranks.get("stl_block_rate"),
    }


def _pair_likely_defender(off_rep: Dict[str, Any],
                          def_sigs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Nearest-position defender on the opposing side; tie-break by D quality."""
    if not def_sigs:
        return None
    off_pos = ((off_rep.get("archetype_role") or {}).get("data") or {}).get("position")
    target = _pos_rank(off_pos)
    best, best_key = None, None
    for ds in def_sigs:
        dist = abs(_pos_rank(ds.get("position")) - target)
        quality = max((ds.get("rim_protection_pct_rank") or 0),
                      (ds.get("event_defense_pct_rank") or 0))
        key = (dist, -quality)
        if best_key is None or key < best_key:
            best_key, best = key, ds
    return best


def _project_individual_edge(off_rep: Dict[str, Any],
                             defender: Optional[Dict[str, Any]],
                             opp_team_def: Dict[str, Any]) -> Dict[str, Any]:
    """Project an offensive player's edge vs his likely defender + the team scheme.

    Edge is from the OFFENSE player's perspective: + = advantage, - = tough spot.
    Uses team-level rim/perimeter D context (robust) plus the individual defender
    archetype/rank as a modifier (sparse, used only when present).
    """
    role = ((off_rep.get("archetype_role") or {}).get("data") or {})
    arch = (role.get("archetype") or {})
    tags = arch.get("tags") or []
    sc = (off_rep.get("scoring") or {}).get("data") or {}
    dist = sc.get("shot_distribution") or {}
    paint_share = _f(dist.get("pts_paint_share"))
    three_share = _f(dist.get("pts_3pt_share"))
    drives = _f((sc.get("creation") or {}).get("drives_per_game"))

    # opponent team D context: pctile 1.0 = elite D, <=0.30 = weak/exploitable
    opp_rim = opp_team_def.get("rim_strength_pctile")
    opp_three = opp_team_def.get("three_strength_pctile")
    dreb_weak = opp_team_def.get("dreb_weak")

    rim_rank = (defender or {}).get("rim_protection_pct_rank")
    evt_rank = (defender or {}).get("event_defense_pct_rank")

    score = 0.0
    factors: List[str] = []

    rim_attacker = ("paint_scorer" in tags) or (paint_share is not None and paint_share >= 0.45) \
        or (drives is not None and drives >= 12)
    if rim_attacker:
        if opp_rim is not None and opp_rim <= 0.30:
            score += 1.5
            factors.append("rim-attacker vs a bottom-tier rim-protecting defense (advantage)")
        elif opp_rim is not None and opp_rim >= 0.75:
            score -= 1.0
            factors.append("rim-attacker meets an elite rim-protecting defense (tough)")
        if rim_rank is not None and rim_rank >= 80:
            score -= 0.5
            factors.append("likely defender is an elite individual rim protector")
        elif rim_rank is not None and rim_rank <= 25:
            score += 0.5
            factors.append("likely defender offers little rim deterrence")

    floor_spacer = ("floor_spacer" in tags) or ("catch_and_shoot" in tags) \
        or (three_share is not None and three_share >= 0.40)
    if floor_spacer:
        if opp_three is not None and opp_three <= 0.30:
            score += 1.0
            factors.append("perimeter shooter vs a weak 3pt defense (advantage)")
        elif opp_three is not None and opp_three >= 0.75:
            score -= 0.75
            factors.append("perimeter shooter vs a strong 3pt defense (contained)")

    if ("self_creator" in tags) or ("high_usage" in tags):
        if evt_rank is not None and evt_rank <= 30:
            score += 0.75
            factors.append("shot creator vs a low-activity individual defender")
        elif evt_rank is not None and evt_rank >= 80:
            score -= 0.5
            factors.append("shot creator vs a high-activity (steal/block) defender")

    if "rebounder" in tags and dreb_weak:
        score += 0.75
        factors.append("strong rebounder vs a team that surrenders the defensive glass")

    score = max(-3.0, min(3.0, round(score, 2)))
    side = "offense" if score >= 1.0 else ("defense" if score <= -1.0 else "neutral")
    if not factors:
        factors.append("no decisive scheme/skill mismatch identified")
    return {"edge_score": score, "edge_side": side, "factors": factors}


def _team_def_context(def_dossier: Dict[str, Any]) -> Dict[str, Any]:
    """Distill a team dossier's defensive holes into matchup-ready flags."""
    sw = ((def_dossier.get("blocks") or {}).get("strengths_weaknesses") or {}).get("data") or {}
    ranks = {r["metric"]: r for r in (sw.get("all_ranks") or [])}

    def _p(metric: str) -> Optional[float]:
        r = ranks.get(metric)
        return None if r is None else _f(r.get("pctile"))

    rim_p = _p("paint_defense.rim_fg_pct_allowed")
    paint_p = _p("paint_defense.paint_fg_pct_allowed")
    three_p = _p("three_pt_defense.opp_3p_pct_allowed")
    dreb_p = _p("rebounding_scheme.dreb_pct")
    rim_strength = max([x for x in (rim_p, paint_p) if x is not None], default=None)
    return {
        "rim_strength_pctile": rim_strength,
        "three_strength_pctile": three_p,
        "dreb_pctile": dreb_p,
        "dreb_weak": (dreb_p is not None and dreb_p <= 0.30),
    }


def _build_individual_matchups(off_reports: Dict[int, Dict], off_team: str,
                               def_reports: Dict[int, Dict], def_dossier: Dict,
                               def_team: str, top_n: int = 8) -> List[Dict[str, Any]]:
    """For each rotation offensive player, pair a likely defender + project edge."""
    def_sigs = [_player_def_signature(r) for r in def_reports.values()]
    opp_def_ctx = _team_def_context(def_dossier)
    out: List[Dict[str, Any]] = []
    for pid, rep in off_reports.items():
        role = ((rep.get("archetype_role") or {}).get("data") or {})
        mins = role.get("minutes_pg")
        if mins is not None and mins < 10:
            continue
        defender = _pair_likely_defender(rep, def_sigs)
        proj = _project_individual_edge(rep, defender, opp_def_ctx)
        out.append({
            "offense_player": {
                "player_id": pid,
                "name": rep.get("player_name") or f"Player {pid}",
                "team": off_team,
                "archetype": (role.get("archetype") or {}).get("label"),
                "minutes_pg": mins,
            },
            "vs_team": def_team,
            "likely_defender": defender,
            "edge_score": proj["edge_score"],
            "edge_side": proj["edge_side"],
            "factors": proj["factors"],
        })
    out.sort(key=lambda e: abs(e["edge_score"]), reverse=True)
    return out[:top_n]


# --------------------------------------------------------------------------- #
# Pace / style interaction (who controls tempo, fast-vs-slow battle)
# --------------------------------------------------------------------------- #
_PACE_RANK = {"slow": 0, "below-average": 1, "average": 2, "moderate": 2,
              "above-average": 3, "fast": 4}


def _build_pace_battle(home_d: Dict, away_d: Dict, home: str, away: str) -> Dict[str, Any]:
    """Classify the fast-vs-slow tempo interaction and who projects to control it."""
    h_off = _team_block_data(home_d, "offensive_identity")
    a_off = _team_block_data(away_d, "offensive_identity")
    h_pace, h_id = _f(h_off.get("pace_pg")), h_off.get("pace_identity")
    a_pace, a_id = _f(a_off.get("pace_pg")), a_off.get("pace_identity")
    h_tz, a_tz = _f(h_off.get("transition_share_z")), _f(a_off.get("transition_share_z"))

    paces = [p for p in (h_pace, a_pace) if p is not None]
    proj_poss = round(sum(paces) / len(paces), 1) if paces else None

    def _r(idv):
        return None if not idv else _PACE_RANK.get(str(idv).lower())
    h_r, a_r = _r(h_id), _r(a_id)

    tempo_battle, controller, note = False, None, ""
    if h_r is not None and a_r is not None:
        gap = h_r - a_r
        if abs(gap) >= 2:
            tempo_battle = True
            controller = "contested"
            faster = home if gap > 0 else away
            slower = away if gap > 0 else home
            f_id = h_id if gap > 0 else a_id
            s_id = a_id if gap > 0 else h_id
            note = (f"Tempo clash: {faster} wants to run ({str(f_id).lower()}) while "
                    f"{slower} wants to slow it down ({str(s_id).lower()}); whoever "
                    f"imposes pace controls the game.")
        elif gap == 0:
            controller = "aligned"
            note = f"Both teams play a similar {str(h_id).lower()} tempo; no tempo battle."
        else:
            controller = home if gap > 0 else away
            note = f"Mild tempo edge to {controller}; not a decisive clash."
    elif h_pace is not None and a_pace is not None and abs(h_pace - a_pace) >= 3.0:
        tempo_battle = True
        controller = "contested"
        note = f"{home if h_pace>a_pace else away} plays materially faster; tempo contested."

    transition_note = None
    if h_tz is not None and a_tz is not None:
        if h_tz >= 0.5 and a_tz >= 0.5:
            transition_note = ("Both push in transition -> up-tempo, high-possession game.")
        elif h_tz <= -0.5 and a_tz <= -0.5:
            transition_note = ("Both grind in the halfcourt -> low-possession game.")

    return {
        "home": {"tricode": home, "pace_pg": h_pace, "pace_identity": h_id,
                 "transition_share_z": h_tz},
        "away": {"tricode": away, "pace_pg": a_pace, "pace_identity": a_id,
                 "transition_share_z": a_tz},
        "projected_possessions_estimate": proj_poss,
        "tempo_battle": tempo_battle,
        "tempo_controller": controller,
        "note": note,
        "transition_note": transition_note,
    }


# --------------------------------------------------------------------------- #
# Deterministic "How this game projects to play" narrative
# --------------------------------------------------------------------------- #
def _build_game_narrative(home: str, away: str, team_clash: Dict, scheme_edges: List,
                          individual: List, pace_battle: Dict) -> str:
    parts: List[str] = [f"{away} at {home}."]

    if pace_battle.get("note"):
        parts.append(pace_battle["note"])
    if pace_battle.get("transition_note"):
        parts.append(pace_battle["transition_note"])
    if pace_battle.get("projected_possessions_estimate") is not None:
        parts.append(f"Projected pace is roughly "
                     f"{pace_battle['projected_possessions_estimate']} possessions.")

    h_edges = [e for e in scheme_edges if e.get("attacker") == home]
    a_edges = [e for e in scheme_edges if e.get("attacker") == away]
    if h_edges:
        parts.append(f"On offense {home} can attack: {h_edges[0]['description']}.")
    if a_edges:
        parts.append(f"Going the other way, {away} can attack: {a_edges[0]['description']}.")

    decisive = [m for m in individual if m["edge_side"] == "offense"]
    if decisive:
        top = decisive[0]
        op = top["offense_player"]
        seg = f"The standout individual edge is {op['name']} ({op['archetype']})"
        if top.get("likely_defender") and top["likely_defender"].get("player_name"):
            seg += f" against {top['likely_defender']['player_name']}"
        seg += f": {top['factors'][0]}."
        parts.append(seg)

    reb = (team_clash or {}).get("rebounding_battle") or {}
    hov, aov = reb.get("home_oreb_vs_away_dreb"), reb.get("away_oreb_vs_home_dreb")
    if hov is not None and hov > 0.02:
        parts.append(f"{home} projects to win the offensive glass for extra possessions.")
    elif aov is not None and aov > 0.02:
        parts.append(f"{away} projects to win the offensive glass for extra possessions.")

    parts.append("This is a DESCRIPTIVE projection of how the styles interact, not a "
                 "validated bet; any predictive lean is emitted separately as an "
                 "unvalidated candidate for the walk-forward + shadow gate.")
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# Public entrypoint
# --------------------------------------------------------------------------- #
class MatchupReportBuilder:
    """Reusable builder; caches the team league context across many games."""

    def __init__(self) -> None:
        self._atlases = _tr.load_team_atlases()
        self._team_ctx = _tr.build_league_context(self._atlases)

    def build(self, home: str, away: str,
              home_roster: Optional[List[int]] = None,
              away_roster: Optional[List[int]] = None) -> Dict[str, Any]:
        return build_matchup_report(
            home, away, home_roster=home_roster, away_roster=away_roster,
            team_ctx=self._team_ctx, atlases=self._atlases)


def build_matchup_report(
    home: str,
    away: str,
    date: Optional[str] = None,
    home_roster: Optional[List[int]] = None,
    away_roster: Optional[List[int]] = None,
    team_ctx: Optional[Dict] = None,
    atlases: Optional[Dict] = None,
    max_player_reports: int = 14,
) -> Dict[str, Any]:
    """Assemble a DESCRIPTIVE head-to-head matchup report.

    Args:
        home, away: team tricodes (e.g. "OKC", "SAS").
        date: optional YYYY-MM-DD used for date-aware roster availability when
            rosters are auto-resolved.
        home_roster, away_roster: optional list of player_ids on each side. If
            omitted, the rosters are AUTO-RESOLVED (recent minutes, via
            game_preview.resolve_roster); the player-level blocks then build.
        team_ctx, atlases: optional pre-built team-report league context (reused
            across many games for speed).

    Returns a dict with this schema::

        {
          "schema_version": "matchup_report/1.0",
          "home": str, "away": str, "date": str|None, "label": "AWAY @ HOME",
          "generated_at": ISO date,
          "team_clash": {
              "pace_environment": {home_pace, away_pace, projected_pace,
                                   pace_environment, ...},
              "home_offense_vs_away_defense": {...},
              "away_offense_vs_home_defense": {...},
              "rebounding_battle": {...},
              "ft_battle": {...},
              "clutch": {...},
          },
          # (1) KEY INDIVIDUAL MATCHUPS — offense player vs likely defender,
          #     sorted by |edge_score| desc, BOTH directions:
          "key_individual_matchups": [
              {offense_player:{player_id,name,team,archetype,minutes_pg},
               vs_team:str, likely_defender:{player_id,name,position,archetype,
                   rim_protection_pct_rank,event_defense_pct_rank}|None,
               edge_score: float(-3..3),
               edge_side: "offense"|"defense"|"neutral",
               factors: [str...]}, ...
          ],
          # (2) SCHEME vs SCHEME — directional scheme advantages:
          "scheme_edges":  [ {type:"scheme", tag, direction, attacker, defender,
                              description, magnitude, ...} ... ],   # desc magnitude
          # player skill vs opposing-team-weakness leans:
          "player_edges":  [ {type:"player", player_id, player_name, team,
                              vs_team, skill, player_percentile,
                              opp_team_pctile, magnitude, description} ... ],
          # (3) PACE / STYLE — fast-vs-slow tempo interaction + controller:
          "pace_style": {home:{...}, away:{...},
                         projected_possessions_estimate: float|None,
                         tempo_battle: bool, tempo_controller: str|None,
                         note: str, transition_note: str|None},
          "key_players":   {home: [...], away: [...]},
          # (5) deterministic "How this game projects to play":
          "game_projection": str,
          "team_dossiers": {home: <team_report>, away: <team_report>},
          "completeness":  {home_team, away_team, n_home_players, n_away_players,
                            rosters_supplied, rosters_auto_resolved},
        }

    HONESTY: this report is purely DESCRIPTIVE — it carries NO predicted stat
    line and NO claimed accuracy lift. The quantitative predictive hypotheses the
    matchup implies are emitted SEPARATELY (and flagged for the walk-forward +
    shadow gate) by :mod:`src.intel.game_preview.predictive_candidates`.
    """
    if atlases is None:
        atlases = _tr.load_team_atlases()
    if team_ctx is None:
        team_ctx = _tr.build_league_context(atlases)

    home_d = _tr.build_team_report(home, atlases, team_ctx)
    away_d = _tr.build_team_report(away, atlases, team_ctx)

    # Build player dossiers for the supplied rosters (capped for cost).
    def _reports(roster: Optional[List[int]]) -> Dict[int, Dict]:
        out: Dict[int, Dict] = {}
        if not roster:
            return out
        for pid in roster[:max_player_reports]:
            try:
                out[int(pid)] = build_player_report(int(pid))
            except Exception:
                continue
        return out

    # Auto-resolve rosters when not supplied so the module is usable standalone
    # (given just home/away [+ date]). Resolution delegates to game_preview's
    # cache-backed resolver via a lazy import to avoid a hard import cycle.
    rosters_auto = False
    if home_roster is None or away_roster is None:
        try:
            from src.intel.game_preview import resolve_roster as _resolve_roster
            if home_roster is None:
                home_roster = _resolve_roster(home, date)
            if away_roster is None:
                away_roster = _resolve_roster(away, date)
            rosters_auto = True
        except Exception:
            pass

    home_reports = _reports(home_roster)
    away_reports = _reports(away_roster)

    team_clash = _build_team_clash(home_d, away_d, team_ctx, home, away)
    scheme_edges = _build_scheme_edges(home_d, away_d, team_ctx, home, away)
    player_edges = _build_player_edges(home_reports, away_reports, team_ctx, home, away)
    pace_battle = _build_pace_battle(home_d, away_d, home, away)
    # key INDIVIDUAL matchups — offensive player vs likely defender, both ways
    individual = (
        _build_individual_matchups(home_reports, home, away_reports, away_d, away)
        + _build_individual_matchups(away_reports, away, home_reports, home_d, home)
    )
    individual.sort(key=lambda e: abs(e["edge_score"]), reverse=True)
    game_projection = _build_game_narrative(home, away, team_clash, scheme_edges,
                                            individual, pace_battle)

    report: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "home": home,
        "away": away,
        "date": date,
        "label": f"{away} @ {home}",
        "generated_at": _dt.date.today().isoformat(),
        "team_clash": team_clash,
        "key_individual_matchups": individual,
        "scheme_edges": scheme_edges,
        "player_edges": player_edges,
        "pace_style": pace_battle,
        "key_players": {
            home: _key_players(home_reports, home),
            away: _key_players(away_reports, away),
        },
        "game_projection": game_projection,
        "team_dossiers": {home: home_d, away: away_d},
        "completeness": {
            "home_team_coverage_pct": (home_d.get("completeness") or {}).get("coverage_pct"),
            "away_team_coverage_pct": (away_d.get("completeness") or {}).get("coverage_pct"),
            "n_home_players": len(home_reports),
            "n_away_players": len(away_reports),
            "rosters_supplied": (bool(home_roster) and bool(away_roster)),
            "rosters_auto_resolved": rosters_auto,
        },
    }
    return report


if __name__ == "__main__":  # pragma: no cover
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Build a descriptive matchup report.")
    ap.add_argument("home")
    ap.add_argument("away")
    args = ap.parse_args()
    rep = build_matchup_report(args.home, args.away)
    print(json.dumps(rep, indent=2, default=str))
