"""context_scout.py — deterministic per-game scout bundle assembly.

Funnel + vault -> ScoutBundle (plain JSON-serialisable dict).
NO LLM, NO network.  Pure function, leak-free (only season/recency snapshot,
asof-bounded injury feed, and pre-built matchup intel).

Public API
----------
    build_scout_bundle(home, away, asof=None, nsims=8000, _result=None) -> dict
    VALIDATED_KEYS  -- frozenset of spine keys the router may turn into mults

Py3.9, type hints.  honesty_class = "research".
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# ---------- path setup (mirrors build_matchup_resolution.py) ----------
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (_HERE, os.path.join(_ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

TS = os.path.join(_ROOT, "data", "cache", "team_system")
VAULT_TEAMS = os.path.join(_ROOT, "vault", "Intelligence", "Teams")
VAULT_PREV = os.path.join(_ROOT, "vault", "Intelligence", "Previews")

# ---------- validated-key discovery (runtime, from signal_effects.json) ----------
def _load_validated_keys(effects_path: str = None) -> frozenset:
    """Keys with status==wired_pregame and confidence==high."""
    fp = effects_path or os.path.join(TS, "signal_effects.json")
    try:
        data = json.load(open(fp, encoding="utf-8"))
    except Exception:
        return frozenset(("home_road", "rest_b2b", "pace_matchup", "opp_defense"))
    return frozenset(
        k for k, v in data.get("effects", {}).items()
        if v.get("status") == "wired_pregame" and v.get("confidence") == "high"
    )


VALIDATED_KEYS: frozenset = _load_validated_keys()


# ---------- helpers ----------
def _load_json(path: str) -> dict:
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}


def _pts_base(r: dict, recency_w: float = 0.6) -> float:
    rec = r.get("pts_pg_rec")
    if rec is not None and not (isinstance(rec, float) and np.isnan(rec)):
        return (1.0 - recency_w) * r.get("pts_pg", 0.0) + recency_w * rec
    return r.get("pts_pg", 0.0)


def _vault_team_snippet(tri: str) -> dict:
    """Read a Teams vault note and extract key signals (best-effort, returns {} on failure)."""
    path = os.path.join(VAULT_TEAMS, f"{tri}.md")
    if not os.path.exists(path):
        return {}
    try:
        txt = open(path, encoding="utf-8").read()
    except Exception:
        return {}
    snip: dict = {}
    for line in txt.splitlines():
        ll = line.lower()
        if "def_rtg" in ll or "def rtg" in ll or "defensive rating" in ll:
            snip.setdefault("def_note", line.strip()[:120])
        if "pace" in ll and ("slow" in ll or "fast" in ll or "poss" in ll):
            snip.setdefault("pace_note", line.strip()[:120])
        if "blowout" in ll:
            snip.setdefault("blowout_note", line.strip()[:120])
    return snip


def _war_room_snippet() -> dict:
    """Extract key signals from the War Room (best-effort)."""
    candidates = [
        os.path.join(VAULT_PREV, "NYK_SAS_Finals_WarRoom.md"),
        os.path.join(VAULT_PREV, "Finals_WarRoom.md"),
    ]
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            txt = open(path, encoding="utf-8").read()
        except Exception:
            continue
        snip: dict = {"found": True}
        for line in txt.splitlines():
            ll = line.lower()
            if "clutch" in ll and "net" in ll:
                snip.setdefault("clutch_line", line.strip()[:160])
            if "series" in ll and ("leads" in ll or "2-0" in ll or "1-0" in ll):
                snip.setdefault("series_state_line", line.strip()[:120])
            if "b2b" in ll or "back-to-back" in ll:
                snip.setdefault("b2b_line", line.strip()[:120])
        return snip
    return {}


# ---------- main assembly ----------
def build_scout_bundle(
    home: str,
    away: str,
    asof: Optional[str] = None,
    nsims: int = 8000,
    _result=None,
) -> Dict[str, Any]:
    """Assemble every deterministic number the context room needs.

    Parameters
    ----------
    home, away : tricode strings e.g. "NYK", "SAS"
    asof       : date string "YYYY-MM-DD"; caps injury feed lookup
    nsims      : sim count (only used if _result is None)
    _result    : pass an existing GameSimResult to avoid re-simulating

    Returns
    -------
    Plain JSON-serialisable dict with keys:
      home, away, asof, sim, spine, tiers, vault, avail, validated_keys
    Leak-free: only season+recency snapshot, asof-bounded injury feed, intel.
    """
    home, away = home.upper(), away.upper()

    # ---- availability (injury feed, asof-bounded) ----
    try:
        from availability import out_ids_for
        out_home = out_ids_for(home, asof)
        out_away = out_ids_for(away, asof)
    except Exception:
        out_home, out_away = set(), set()

    # ---- team models (with outs applied) ----
    from sim.basketball_sim import TeamModel, apply_context, _matchup_mult, RECENCY_W
    from sim.fast_sim import simulate_game_fast

    home_tm = TeamModel.from_cache(home, out_ids=out_home)
    away_tm = TeamModel.from_cache(away, out_ids=out_away)

    # ---- one sim (reuse if caller passes _result) ----
    if _result is not None:
        res = _result
    else:
        ctx = {"neutral_site": False}
        apply_context(home_tm, away_tm, ctx)
        res = simulate_game_fast(home_tm, away_tm, n_sims=nsims, seed=7,
                                 anchor=True, defense=True)

    home_mean = float(res.home_total.mean())
    away_mean = float(res.away_total.mean())
    home_wp = float(res.home_win_prob)
    engine_spread = home_mean - away_mean

    # ---- effect spine ----
    se_path = os.path.join(TS, "signal_effects.json")
    spine_raw = _load_json(se_path).get("effects", {})
    validated_keys: List[str] = sorted(VALIDATED_KEYS)
    spine_summary = {k: {"mag": spine_raw[k]["magnitude"], "status": spine_raw[k]["status"],
                         "confidence": spine_raw[k]["confidence"]}
                     for k in validated_keys if k in spine_raw}

    # ---- per-player effects (b2b_xfg, vs_strongD, etc.) ----
    pe_path = os.path.join(TS, "player_effects_full.parquet")
    player_spine: Dict[int, dict] = {}
    if os.path.exists(pe_path):
        try:
            pef = pd.read_parquet(pe_path).set_index("pid")
            for pid_int in pef.index:
                row = pef.loc[pid_int]
                player_spine[int(pid_int)] = {
                    "b2b_xfg": float(row.get("b2b_xfg", 1.0) or 1.0),
                    "vs_strongD_xfg": float(row.get("vs_strongD_xfg", 1.0) or 1.0),
                    "vs_weakD_xfg": float(row.get("vs_weakD_xfg", 1.0) or 1.0),
                    "fast_xfg": float(row.get("fast_xfg", 1.0) or 1.0),
                    "matchup_sensitivity": float(row.get("matchup_sensitivity", 0.0) or 0.0),
                }
        except Exception:
            pass

    # ---- team outcome tiers (from intel_outcome) ----
    outcome_path = os.path.join(_ROOT, "data", "cache", "intel_outcome", "team_matchup_outcome.json")
    outcome = _load_json(outcome_path)
    league_meta = outcome.get("league", {})
    team_cards = outcome.get("team_cards", {})
    home_card = team_cards.get(home, {})
    away_card = team_cards.get(away, {})
    tiers = {
        "home": {
            "srs": home_card.get("srs"),
            "total_tendency": home_card.get("total_tendency"),
            "blowout_game_pct": home_card.get("blowout_game_pct"),
            "close_game_pct": home_card.get("close_game_pct"),
            "b2b_margin_delta": home_card.get("b2b_margin_delta"),
        },
        "away": {
            "srs": away_card.get("srs"),
            "total_tendency": away_card.get("total_tendency"),
            "blowout_game_pct": away_card.get("blowout_game_pct"),
            "close_game_pct": away_card.get("close_game_pct"),
            "b2b_margin_delta": away_card.get("b2b_margin_delta"),
        },
        "league_home_margin": league_meta.get("home_court_margin_pts", 1.73),
        "baseline_total": league_meta.get("baseline_total", 231.0),
    }

    # ---- pace & defense from team models ----
    n_poss = int(round((home_tm.pace + away_tm.pace) / 2.0))
    sim_section = {
        "home_mean": home_mean,
        "away_mean": away_mean,
        "total_mean": home_mean + away_mean,
        "home_win_prob": home_wp,
        "engine_spread": engine_spread,
        "n_poss": n_poss,
        "home_pace": float(home_tm.pace),
        "away_pace": float(away_tm.pace),
        "home_def_rtg": float(home_tm.def_rtg),
        "away_def_rtg": float(away_tm.def_rtg),
        "home_rim_d": float(home_tm.rim_d),
        "away_rim_d": float(away_tm.rim_d),
        "home_perim_d": float(home_tm.perim_d),
        "away_perim_d": float(away_tm.perim_d),
        "home_ft_force": float(home_tm.ft_force),
        "away_ft_force": float(away_tm.ft_force),
        "home_tov_force": float(home_tm.tov_force),
        "away_tov_force": float(away_tm.tov_force),
    }

    # ---- per-player resolver (top-rotation only) ----
    rot_threshold = 15.0
    home_rot = {pid: home_tm.rate[pid] for pid in home_tm.rate
                if (home_tm.rate[pid].get("mpg") or 0) >= rot_threshold}
    away_rot = {pid: away_tm.rate[pid] for pid in away_tm.rate
                if (away_tm.rate[pid].get("mpg") or 0) >= rot_threshold}
    resolver_rows: Dict[str, dict] = {}
    for pid, r in list(home_rot.items()) + list(away_rot.items()):
        opp = away_tm if pid in home_rot else home_tm
        mdef = _matchup_mult(r, opp, True)
        base = _pts_base(r, RECENCY_W)
        resolver_rows[str(pid)] = {
            "name": r.get("player", str(pid)),
            "team": r.get("team", ""),
            "pts_base": round(base, 2),
            "matchup_mult": round(mdef, 4),
            "pts_proj": round(res.players[pid]["mean"]["pts"], 2) if pid in res.players else round(base * mdef, 2),
        }
        if int(pid) in player_spine:
            resolver_rows[str(pid)]["spine"] = player_spine[int(pid)]

    # ---- availability summary ----
    avail: dict = {
        "home_out_ids": sorted(out_home),
        "away_out_ids": sorted(out_away),
        "home_b2b": False,   # caller can override if context says B2B
        "away_b2b": False,
        "stale_feed_note": "injury feed asof-bounded; reload ~2h pre-tip for same-day scratches",
    }

    # ---- vault snippets ----
    vault: dict = {
        "home_team": _vault_team_snippet(home),
        "away_team": _vault_team_snippet(away),
        "war_room": _war_room_snippet(),
    }

    return {
        "home": home,
        "away": away,
        "asof": asof,
        "honesty_class": "research",
        "sim": sim_section,
        "spine": spine_summary,
        "tiers": tiers,
        "vault": vault,
        "avail": avail,
        "resolver": resolver_rows,
        "validated_keys": validated_keys,
    }
