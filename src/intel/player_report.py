"""Player intelligence dossier synthesizer (ARM-B read side).

This module ASSEMBLES the 28 ``atlas_player_*.parquet`` sections plus the
persistent profile-factory JSON (``data/cache/profiles/players/<id>.json``) into
ONE coherent descriptive dossier per player. It does NOT build new intelligence
and does NOT call any external feed -- it reads what the loop already shipped and
synthesizes a structured ``report`` dict + a human-readable narrative.

Design constraints (per build spec):
  * USE EXISTING DATA ONLY -- atlas parquets + profile factory. No external feeds.
  * NO LLM-per-player. The narrative ("How <player> plays") is generated
    DETERMINISTICALLY from the numbers via rule/threshold-based classification,
    percentile-ranked strengths/weaknesses, and key-stat extraction. Scales to
    ~1200 players at $0/player.
  * Leak-safety is NOT a concern (this is descriptive current-state intelligence),
    but every section carries provenance ``{source, n, confidence, as_of}`` and the
    report carries a ``data_completeness`` score; missing / low-confidence sections
    are flagged explicitly.

Public API:
    build_player_report(player_id, ...) -> dict       # structured report + narrative
    PlayerReportBuilder                                # reusable (caches league percentiles)
    league_percentile(metric, value)                  # convenience

Schema of the returned report dict is documented in :func:`build_player_report`.
"""
from __future__ import annotations

import datetime as _dt
import functools
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
_ROOT = Path(__file__).resolve().parent.parent.parent  # repo root (src/intel/ -> repo)
_ATLAS_DIR = _ROOT / "data" / "cache"
_PROFILES_DIR = _ROOT / "data" / "cache" / "profiles" / "players"
_PLAYER_INDEX = _ROOT / "data" / "cache" / "profiles" / "PLAYER_INDEX.json"

SCHEMA_VERSION = "player_report/1.0"

# The 28 atlas player sections this synthesizer reads.
ATLAS_SECTIONS: Tuple[str, ...] = (
    "shot_profile", "scoring_creation", "playmaking_network", "rebounding_profile",
    "usage_role", "quarter_shape_fatigue", "foul_tendency", "matchup_splits",
    "situational_splits", "form_streak_dynamics", "spacing_gravity", "durability_load",
    "ft_profile", "turnover_profile", "pace_fit", "pick_and_roll_profile",
    "isolation_profile", "post_up_profile", "catch_shoot_vs_pullup", "clutch_scoring",
    "shot_clock_scoring", "score_margin_splits", "vs_scheme_splits", "rest_b2b_splits",
    "monthly_form", "foul_drawing", "transition_scoring", "defensive_profile",
)

# Sections grouped into report blocks (drives the narrative + completeness scoring).
_REPORT_BLOCKS = {
    "archetype_role": ["usage_role"],
    "scoring": [
        "shot_profile", "scoring_creation", "pick_and_roll_profile", "isolation_profile",
        "post_up_profile", "catch_shoot_vs_pullup", "shot_clock_scoring",
        "transition_scoring",
    ],
    "playmaking": ["playmaking_network"],
    "rebounding": ["rebounding_profile"],
    "defense": ["defensive_profile", "foul_tendency", "foul_drawing"],
    "situational": [
        "clutch_scoring", "quarter_shape_fatigue", "rest_b2b_splits",
        "score_margin_splits", "vs_scheme_splits", "monthly_form", "situational_splits",
        "matchup_splits", "pace_fit", "ft_profile",
    ],
    "consistency_durability": ["form_streak_dynamics", "durability_load", "spacing_gravity"],
}

_CONF_ORDER = {"low": 0, "med": 1, "high": 2, None: -1}


# --------------------------------------------------------------------------- #
# Coercion helpers (atlas struct fields are sometimes dicts, sometimes JSON str)
# --------------------------------------------------------------------------- #
def _as_dict(v: Any) -> Dict[str, Any]:
    """Coerce a nested atlas field into a plain dict (handles JSON-string structs)."""
    if v is None:
        return {}
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    # pandas/pyarrow struct -> mapping
    try:
        return dict(v)
    except Exception:
        return {}


def _num(v: Any) -> Optional[float]:
    """Coerce to float or return None (NaN -> None)."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _round(v: Any, nd: int = 3) -> Optional[float]:
    f = _num(v)
    return None if f is None else round(f, nd)


def _safe(d: Dict[str, Any], *keys: str) -> Any:
    """Nested get; returns None on any miss."""
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


# --------------------------------------------------------------------------- #
# Percentile engine -- ranks a player across the league using the atlas parquets.
# Metrics are (section, accessor) pairs reduced to one scalar per player.
# --------------------------------------------------------------------------- #
# Each metric: name -> (atlas_section, extractor(row_dict) -> Optional[float], higher_is_better)
def _metric_specs() -> Dict[str, Tuple[str, Any, bool]]:
    return {
        "usage_rate":        ("usage_role", lambda r: _num(r.get("usage_rate")), True),
        "ast_pct":           ("usage_role", lambda r: _num(r.get("ast_pct")), True),
        "pie":               ("usage_role", lambda r: _num(r.get("pie_mean")), True),
        "on_off_impact":     ("usage_role", lambda r: _num(r.get("on_off_net_diff")), True),
        "minutes_pg":        ("usage_role", lambda r: _num(r.get("minutes_pg")), True),
        "ast_pts_created":   ("playmaking_network", lambda r: _num(r.get("ast_pts_created")), True),
        "potential_ast":     ("playmaking_network", lambda r: _num(r.get("potential_ast")), True),
        "ast_to_tov":        ("playmaking_network", lambda r: _num(r.get("ast_to_tov")), True),
        "passes_made":       ("playmaking_network", lambda r: _num(r.get("passes_made")), True),
        "total_reb_rate":    ("rebounding_profile", lambda r: _num(r.get("total_reb_rate_mean")), True),
        "oreb_rate":         ("rebounding_profile", lambda r: _num(r.get("oreb_rate_mean")), True),
        "dreb_rate":         ("rebounding_profile", lambda r: _num(r.get("dreb_rate_mean")), True),
        "box_outs_pg":       ("rebounding_profile", lambda r: _num(r.get("box_outs_per_game")), True),
        "catch_shoot_efg":   ("scoring_creation", lambda r: _num(r.get("catch_shoot_efg")), True),
        "drives_pg":         ("scoring_creation", lambda r: _num(r.get("drives_per_game")), True),
        "pts_3pt_share":     ("scoring_creation", lambda r: _num(r.get("pts_3pt_share")), True),
        "pts_paint_share":   ("scoring_creation", lambda r: _num(r.get("pts_paint_share")), True),
        "unassisted_2pm":    ("scoring_creation", lambda r: _num(r.get("unassisted_share_2pm")), True),
        "transition_pts_share": ("scoring_creation", lambda r: _num(r.get("transition_pts_share")), True),
        "spacing_gravity":   ("spacing_gravity", lambda r: _num(r.get("gravity_score")), True),
        "post_up_freq":      ("post_up_profile", lambda r: _num(r.get("post_up_freq_pct")), True),
        "post_up_ppp":       ("post_up_profile", lambda r: _num(r.get("post_up_ppp")), True),
        "ft_generation":     ("foul_drawing", lambda r: _num(_safe(_as_dict(r.get("ft_generation")), "fta_per_game"))
                                              if _as_dict(r.get("ft_generation")) else None, True),
        "rim_protection":    ("defensive_profile", lambda r: _num(_safe(_as_dict(r.get("rim_protection")), "blk_pg"))
                                              if _as_dict(r.get("rim_protection")) else None, True),
        "stl_block_rate":    ("defensive_profile", lambda r: _num(_safe(_as_dict(r.get("steal_block_rate")), "stl_pg"))
                                              if _as_dict(r.get("steal_block_rate")) else None, True),
        # foul_rate: lower is better (defensive discipline)
        "foul_rate":         ("defensive_profile", lambda r: _num(_safe(_as_dict(r.get("foul_rate")), "pf_pg"))
                                              if _as_dict(r.get("foul_rate")) else None, False),
        # consistency: scoring CV (lower CV == more consistent == "better")
        "reb_consistency_cv": ("rebounding_profile", lambda r: _num(r.get("reb_consistency_cv")), False),
    }


@functools.lru_cache(maxsize=64)
def _percentile_table() -> Dict[str, np.ndarray]:
    """Build sorted league-wide value arrays for each percentile metric.

    Cached per-process. Each array is the sorted (ascending) non-null values across
    all players in the corresponding atlas section, used for empirical-CDF ranking.
    """
    specs = _metric_specs()
    # group accessors by section so each parquet is read once
    by_section: Dict[str, List[str]] = {}
    for name, (sec, _, _) in specs.items():
        by_section.setdefault(sec, []).append(name)

    table: Dict[str, List[float]] = {n: [] for n in specs}
    for sec, names in by_section.items():
        df = _load_atlas_section(sec)
        if df is None or df.empty:
            continue
        records = df.to_dict("records")
        for rec in records:
            for name in names:
                _, acc, _ = specs[name]
                try:
                    v = acc(rec)
                except Exception:
                    v = None
                if v is not None:
                    table[name].append(v)
    return {n: np.sort(np.asarray(v, dtype=float)) for n, v in table.items() if v}


def league_percentile(metric: str, value: Optional[float]) -> Optional[float]:
    """Empirical-CDF percentile (0-100) of ``value`` for ``metric`` across the league.

    Returns None if the metric is unknown or value is None. Orientation
    (higher-is-better vs lower-is-better) is applied so that 99 always means
    "elite at this skill".
    """
    if value is None:
        return None
    specs = _metric_specs()
    if metric not in specs:
        return None
    arr = _percentile_table().get(metric)
    if arr is None or arr.size == 0:
        return None
    # fraction of players at or below value
    rank = float(np.searchsorted(arr, value, side="right")) / float(arr.size)
    pct = rank * 100.0
    higher_better = specs[metric][2]
    if not higher_better:
        pct = 100.0 - pct
    return round(pct, 1)


# --------------------------------------------------------------------------- #
# Atlas / profile loaders (cached per-process)
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=64)
def _load_atlas_section(section: str) -> Optional[pd.DataFrame]:
    path = _ATLAS_DIR / f"atlas_player_{section}.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def _atlas_row(section: str, player_id: int) -> Optional[Dict[str, Any]]:
    df = _load_atlas_section(section)
    if df is None or "player_id" not in df.columns:
        return None
    sub = df[df["player_id"] == player_id]
    if sub.empty:
        return None
    return sub.iloc[0].to_dict()


def _load_profile(player_id: int) -> Optional[Dict[str, Any]]:
    path = _PROFILES_DIR / f"{player_id}.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _section_prov(row: Optional[Dict[str, Any]], section: str) -> Dict[str, Any]:
    """Extract {source, n, confidence, as_of} for one atlas section row."""
    if row is None:
        return {"source": f"atlas_player_{section}.parquet", "n": 0,
                "confidence": None, "as_of": None, "present": False}
    n = row.get("n")
    try:
        n = int(n) if n is not None and not (isinstance(n, float) and math.isnan(n)) else 0
    except Exception:
        n = 0
    return {
        "source": f"atlas_player_{section}.parquet",
        "n": n,
        "confidence": row.get("confidence"),
        "as_of": str(row.get("as_of")) if row.get("as_of") is not None else None,
        "present": True,
    }


# --------------------------------------------------------------------------- #
# Block builders -- each returns (data_dict, prov_dict)
# --------------------------------------------------------------------------- #
def _pct(metric: str, value: Optional[float]) -> Optional[float]:
    return league_percentile(metric, value)


def _build_archetype_role(pid: int, prof: Optional[Dict]) -> Tuple[Dict, Dict]:
    row = _atlas_row("usage_role", pid)
    prov = _section_prov(row, "usage_role")
    bio = _safe(prof or {}, "sections", "bio") or {}
    position = bio.get("position")
    data: Dict[str, Any] = {
        "position": position,
        "usage_rate": _round(row.get("usage_rate")) if row else None,
        "usage_tier": row.get("usage_tier") if row else None,
        "minutes_pg": _round(row.get("minutes_pg"), 1) if row else None,
        "ast_pct": _round(row.get("ast_pct")) if row else None,
        "pie_mean": _round(row.get("pie_mean")) if row else None,
        "on_off_net_diff": _round(row.get("on_off_net_diff"), 1) if row else None,
        "creator_role": row.get("creator_role") if row else None,
        "usage_pct_rank": _pct("usage_rate", _num(row.get("usage_rate"))) if row else None,
        "ast_pct_rank": _pct("ast_pct", _num(row.get("ast_pct"))) if row else None,
        "impact_pct_rank": _pct("on_off_impact", _num(row.get("on_off_net_diff"))) if row else None,
    }
    data["archetype"] = _classify_archetype(pid, prof, row)
    return data, prov


def _build_scoring(pid: int, prof: Optional[Dict]) -> Tuple[Dict, Dict]:
    sc = _atlas_row("scoring_creation", pid)
    sp = _atlas_row("shot_profile", pid)
    pnr = _atlas_row("pick_and_roll_profile", pid)
    iso = _atlas_row("isolation_profile", pid)
    post = _atlas_row("post_up_profile", pid)
    cspu = _atlas_row("catch_shoot_vs_pullup", pid)
    sclock = _atlas_row("shot_clock_scoring", pid)
    trans = _atlas_row("transition_scoring", pid)

    data: Dict[str, Any] = {}
    if sc:
        data["shot_distribution"] = {
            "pts_paint_share": _round(sc.get("pts_paint_share")),
            "pts_3pt_share": _round(sc.get("pts_3pt_share")),
            "pts_midrange_share": _round(sc.get("pts_midrange_share")),
            "pts_ft_share": _round(sc.get("pts_ft_share")),
        }
        data["creation"] = {
            "unassisted_share_2pm": _round(sc.get("unassisted_share_2pm")),
            "assisted_share_2pm": _round(sc.get("assisted_share_2pm")),
            "unassisted_share_3pm": _round(sc.get("unassisted_share_3pm")),
            "drives_per_game": _round(sc.get("drives_per_game"), 1),
            "catch_shoot_efg": _round(sc.get("catch_shoot_efg")),
            "transition_pts_share": _round(sc.get("transition_pts_share")),
            "halfcourt_pts_share": _round(sc.get("halfcourt_pts_share")),
        }
        data["self_creation_pct_rank"] = _pct("unassisted_2pm", _num(sc.get("unassisted_share_2pm")))
        data["catch_shoot_pct_rank"] = _pct("catch_shoot_efg", _num(sc.get("catch_shoot_efg")))
    if cspu:
        data["catch_shoot_vs_pullup"] = {
            "catch_shoot": _round(_safe(_as_dict(cspu.get("catch_shoot")), "fga_per_g")),
            "pull_up": _round(_safe(_as_dict(cspu.get("pull_up")), "fga_per_g")),
        }
    if pnr:
        h = _as_dict(pnr.get("handler"))
        rm = _as_dict(pnr.get("roll_man"))
        data["pick_and_roll"] = {
            "handler_freq": _round(h.get("freq_pct")) if h else None,
            "roll_man_freq": _round(rm.get("freq_pct")) if rm else None,
        }
    if iso:
        data["isolation"] = {
            "freq": _round(_safe(_as_dict(iso.get("frequency")), "iso_freq_pct"))
            if _as_dict(iso.get("frequency")) else None,
            "fg_pct": _round(iso.get("fg_pct_iso")),
        }
    if post:
        data["post_up"] = {
            "freq_pct": _round(post.get("post_up_freq_pct")),
            "ppp": _round(post.get("post_up_ppp")),
            "freq_pct_rank": _pct("post_up_freq", _num(post.get("post_up_freq_pct"))),
        }
    if sclock:
        data["shot_clock"] = {
            "early": _round(_safe(_as_dict(sclock.get("early")), "fga_pg")),
            "late": _round(_safe(_as_dict(sclock.get("late")), "fga_pg")),
        }
    if trans:
        data["transition"] = {
            "leak_out_tendency": trans.get("leak_out_tendency"),
        }

    # provenance is a sub-map over the contributing sections
    prov = {
        "scoring_creation": _section_prov(sc, "scoring_creation"),
        "shot_profile": _section_prov(sp, "shot_profile"),
        "pick_and_roll_profile": _section_prov(pnr, "pick_and_roll_profile"),
        "isolation_profile": _section_prov(iso, "isolation_profile"),
        "post_up_profile": _section_prov(post, "post_up_profile"),
        "catch_shoot_vs_pullup": _section_prov(cspu, "catch_shoot_vs_pullup"),
        "shot_clock_scoring": _section_prov(sclock, "shot_clock_scoring"),
        "transition_scoring": _section_prov(trans, "transition_scoring"),
    }
    return data, prov


def _build_playmaking(pid: int, prof: Optional[Dict]) -> Tuple[Dict, Dict]:
    pm = _atlas_row("playmaking_network", pid)
    prov = _section_prov(pm, "playmaking_network")
    if not pm:
        return {}, prov
    data = {
        "passes_made": _round(pm.get("passes_made"), 1),
        "potential_ast": _round(pm.get("potential_ast"), 1),
        "ast_pts_created": _round(pm.get("ast_pts_created"), 1),
        "ast_ratio": _round(pm.get("ast_ratio"), 1),
        "ast_to_tov": _round(pm.get("ast_to_tov"), 2),
        "secondary_ast": _round(pm.get("secondary_ast"), 1),
        "pnr_bh_poss_fraction": _round(pm.get("pnr_bh_poss_fraction")),
        "ast_pts_created_rank": _pct("ast_pts_created", _num(pm.get("ast_pts_created"))),
        "potential_ast_rank": _pct("potential_ast", _num(pm.get("potential_ast"))),
        "ast_to_tov_rank": _pct("ast_to_tov", _num(pm.get("ast_to_tov"))),
    }
    return data, prov


def _build_rebounding(pid: int, prof: Optional[Dict]) -> Tuple[Dict, Dict]:
    rb = _atlas_row("rebounding_profile", pid)
    prov = _section_prov(rb, "rebounding_profile")
    if not rb:
        return {}, prov
    data = {
        "total_reb_rate": _round(rb.get("total_reb_rate_mean")),
        "oreb_rate": _round(rb.get("oreb_rate_mean")),
        "dreb_rate": _round(rb.get("dreb_rate_mean")),
        "oreb_dreb_ratio": _round(rb.get("oreb_dreb_ratio")),
        "box_outs_per_game": _round(rb.get("box_outs_per_game"), 2),
        "total_reb_rate_rank": _pct("total_reb_rate", _num(rb.get("total_reb_rate_mean"))),
        "oreb_rate_rank": _pct("oreb_rate", _num(rb.get("oreb_rate_mean"))),
    }
    return data, prov


def _build_defense(pid: int, prof: Optional[Dict]) -> Tuple[Dict, Dict]:
    dp = _atlas_row("defensive_profile", pid)
    ft = _atlas_row("foul_tendency", pid)
    fd = _atlas_row("foul_drawing", pid)
    data: Dict[str, Any] = {}
    if dp:
        data["defensive_profile"] = {
            "rim_protection": _as_dict(dp.get("rim_protection")) or None,
            "steal_block_rate": _as_dict(dp.get("steal_block_rate")) or None,
            "foul_rate": _as_dict(dp.get("foul_rate")) or None,
            "on_off_drtg": _as_dict(dp.get("on_off_drtg")) or None,
        }
    else:
        # fall back to profile-factory defense_allowed (matchup-based) if atlas absent
        da = _safe(prof or {}, "sections", "defense_allowed")
        if da:
            data["defense_allowed_fallback"] = {
                "fg_pct_allowed": _round(da.get("fg_pct_allowed")),
                "fg3_pct_allowed": _round(da.get("fg3_pct_allowed")),
                "blocks_matchup": da.get("blocks_matchup"),
                "n_games": da.get("n_games"),
                "_source": "profile_factory.defense_allowed (atlas defensive_profile absent)",
            }
    if ft:
        data["foul_tendency"] = {
            "early_trouble": _as_dict(ft.get("early_trouble")) or None,
            "foul_out_risk": _as_dict(ft.get("foul_out_risk")) or None,
        }
    if fd:
        data["foul_drawing"] = {
            "ft_generation": _as_dict(fd.get("ft_generation")) or None,
            "and_one": _as_dict(fd.get("and_one")) or None,
        }
    prov = {
        "defensive_profile": _section_prov(dp, "defensive_profile"),
        "foul_tendency": _section_prov(ft, "foul_tendency"),
        "foul_drawing": _section_prov(fd, "foul_drawing"),
    }
    return data, prov


def _build_situational(pid: int, prof: Optional[Dict]) -> Tuple[Dict, Dict]:
    clutch = _atlas_row("clutch_scoring", pid)
    qsf = _atlas_row("quarter_shape_fatigue", pid)
    rb2b = _atlas_row("rest_b2b_splits", pid)
    smargin = _atlas_row("score_margin_splits", pid)
    vsch = _atlas_row("vs_scheme_splits", pid)
    mform = _atlas_row("monthly_form", pid)
    sit = _atlas_row("situational_splits", pid)
    # previously unwired sections (2a fix)
    ftrow = _atlas_row("ft_profile", pid)
    msplit = _atlas_row("matchup_splits", pid)
    tov = _atlas_row("turnover_profile", pid)
    pfit = _atlas_row("pace_fit", pid)

    data: Dict[str, Any] = {}
    if clutch:
        data["clutch"] = {
            "scoring": _as_dict(clutch.get("scoring")) or None,
            "pbp_clutch": _as_dict(clutch.get("pbp_clutch")) or None,
        }
    if qsf:
        data["quarter_shape"] = {
            "q4_vs_early_ratio": _round(qsf.get("q4_vs_early_ratio")),
            "q4_fade_abs": _round(qsf.get("q4_fade_abs"), 2),
            "b2b_pts_delta": _round(qsf.get("b2b_pts_delta"), 2),
            "b2b_decay_ratio": _round(qsf.get("b2b_decay_ratio")),
        }
    if rb2b:
        data["rest_b2b"] = {
            "b2b": _as_dict(rb2b.get("b2b")) or None,
            "two_plus": _as_dict(rb2b.get("two_plus")) or None,
        }
    if smargin:
        data["score_margin"] = {
            "leading": _as_dict(smargin.get("leading")) or None,
            "trailing": _as_dict(smargin.get("trailing")) or None,
        }
    if vsch:
        data["vs_scheme"] = {
            "best_scheme": vsch.get("best_scheme"),
            "worst_scheme": vsch.get("worst_scheme"),
            "scheme_ts_spread": _round(vsch.get("scheme_ts_pct_best_minus_worst")),
        }
    if mform:
        data["monthly_form"] = _as_dict(mform.get("summary")) or None
    if sit:
        data["home_road"] = _as_dict(sit.get("home_road")) or None

    # --- ft_profile (was silently omitted) ---
    if ftrow:
        stab = _as_dict(ftrow.get("stability"))
        att = _as_dict(ftrow.get("attempts"))
        hc = _as_dict(ftrow.get("hack_candidate"))
        cft = _as_dict(ftrow.get("clutch_ft"))
        data["ft_profile"] = {
            "ft_pct": _round(stab.get("ft_pct"), 3) if stab else None,
            "ft_pct_l10": _round(stab.get("ft_pct_l10"), 3) if stab else None,
            "fta_pg": _round(att.get("fta_pg"), 2) if att else None,
            "pct_pts_from_ft": _round(att.get("pct_pts_from_ft"), 3) if att else None,
            "hack_flag": hc.get("hack_flag") if hc else None,
            "clutch_ft_pct": _round(cft.get("clutch_ft_pct"), 3) if cft else None,
        }

    # --- matchup_splits (was silently omitted) ---
    if msplit:
        nd = _as_dict(msplit.get("vs_notable_defenders"))
        # surface top notable defender by partial_possessions
        top_def = None
        if nd:
            best = max(
                ((v.get("def_player_name"), v.get("partial_possessions"),
                  _round(v.get("off_fg_pct"), 3))
                 for v in nd.values() if isinstance(v, dict)),
                key=lambda t: t[1] if t[1] is not None else 0.0,
                default=None,
            )
            if best and best[0]:
                top_def = {"defender": best[0], "partial_poss": _round(best[1], 1),
                           "off_fg_pct_vs": best[2]}
        data["matchup_splits"] = {
            "top_notable_defender": top_def,
            "inferred_position": msplit.get("inferred_position"),
        }

    # --- turnover_profile (was silently omitted) ---
    if tov:
        sr = _as_dict(tov.get("season_rate"))
        bq = _as_dict(tov.get("by_quarter"))
        data["turnover_profile"] = {
            "tov_pg": _round(sr.get("tov_pg"), 2) if sr else None,
            "q4_tov_pg": _round(bq.get("q4_tov_pg"), 2) if bq else None,
            "q4_tov_share": _round(bq.get("q4_share_of_daily_tov"), 3) if bq else None,
        }

    # --- pace_fit (was silently omitted) ---
    if pfit:
        data["pace_fit"] = {
            "pace_preference": pfit.get("pace_preference"),
            "pace_fit_score": _round(pfit.get("pace_fit_score"), 3),
            "ts_pace_delta": _round(pfit.get("ts_pace_delta"), 3),
            "net_rtg_pace_delta": _round(pfit.get("net_rtg_pace_delta"), 2),
            "efg_pace_delta": _round(pfit.get("efg_pace_delta"), 3),
        }

    prov = {
        "clutch_scoring": _section_prov(clutch, "clutch_scoring"),
        "quarter_shape_fatigue": _section_prov(qsf, "quarter_shape_fatigue"),
        "rest_b2b_splits": _section_prov(rb2b, "rest_b2b_splits"),
        "score_margin_splits": _section_prov(smargin, "score_margin_splits"),
        "vs_scheme_splits": _section_prov(vsch, "vs_scheme_splits"),
        "monthly_form": _section_prov(mform, "monthly_form"),
        "situational_splits": _section_prov(sit, "situational_splits"),
        # newly wired
        "ft_profile": _section_prov(ftrow, "ft_profile"),
        "matchup_splits": _section_prov(msplit, "matchup_splits"),
        "turnover_profile": _section_prov(tov, "turnover_profile"),
        "pace_fit": _section_prov(pfit, "pace_fit"),
    }
    return data, prov


def _build_consistency_durability(pid: int, prof: Optional[Dict]) -> Tuple[Dict, Dict]:
    fsd = _atlas_row("form_streak_dynamics", pid)
    dl = _atlas_row("durability_load", pid)
    sg = _atlas_row("spacing_gravity", pid)
    rb = _atlas_row("rebounding_profile", pid)
    data: Dict[str, Any] = {}
    # consistency: use count_distribution dispersion from profile + reb CV from atlas
    cd = _safe(prof or {}, "sections", "count_distributions", "dist")
    if cd and isinstance(cd, dict):
        disp = {k: _round(_safe(cd, k, "dispersion"), 2) for k in ("pts", "reb", "ast")
                if isinstance(cd.get(k), dict)}
        data["count_dispersion"] = disp or None
    if rb:
        data["reb_consistency_cv"] = _round(rb.get("reb_consistency_cv"))
    if fsd:
        data["form_summary"] = _as_dict(fsd.get("summary")) or None
    if dl:
        data["durability"] = {
            "age_years": _round(dl.get("age_years"), 1),
            "seasons_in_league": _round(dl.get("seasons_in_league"), 0),
            "minutes_per_game_mean": _round(dl.get("minutes_per_game_mean"), 1),
            "high_minutes_game_rate": _round(dl.get("high_minutes_game_rate")),
            "injury_dnp_rate": _round(dl.get("injury_dnp_rate")),
            "current_availability": dl.get("current_availability"),
        }
    if sg:
        data["spacing_gravity"] = {
            "gravity_score": _round(sg.get("gravity_score")),
            "gravity_pct_rank": _pct("spacing_gravity", _num(sg.get("gravity_score"))),
        }
    prov = {
        "form_streak_dynamics": _section_prov(fsd, "form_streak_dynamics"),
        "durability_load": _section_prov(dl, "durability_load"),
        "spacing_gravity": _section_prov(sg, "spacing_gravity"),
    }
    return data, prov


# --------------------------------------------------------------------------- #
# CV behavioral block (step 2b) — surfaces non-null CV slots from atlas rows.
# Confidence is always capped at "med" (CV coverage is thin; descriptive only).
# --------------------------------------------------------------------------- #
def _build_cv_behavioral(pid: int, prof: Optional[Dict]) -> Tuple[Dict, Dict]:
    """Collect any non-null CV slot values stored in atlas_player_* parquets.

    Each atlas section whose row for this player carries a ``_cv_fields`` JSON
    column is scanned.  Any slot whose ``value`` is not None is surfaced under
    ``slots[section][slot_name]`` along with its ``unit`` if present.  The
    ``_cv_meta`` sub-key (written by the CV branch) is promoted to
    ``provenance_meta[section]`` when present.

    Returns:
        ({
            "slots": {section: {slot_name: {"value": ..., "unit": ...}}},
            "provenance_meta": {section: {source, n_games, confidence, as_of, ...}},
            "provenance_note": str,
        }, prov_map)

    If no non-null slots exist for this player the ``slots`` dict is empty
    (common — only ~223 players have any CV fills as of 2026-05-31).
    """
    # Only the 3 sections that currently have any fills; auto-grows as CV improves
    # by scanning ALL ATLAS_SECTIONS that have a _cv_fields column.
    slots: Dict[str, Dict[str, Any]] = {}
    prov_meta: Dict[str, Any] = {}

    for sec in ATLAS_SECTIONS:
        row = _atlas_row(sec, pid)
        if row is None:
            continue
        cv_raw = row.get("_cv_fields")
        if not cv_raw:
            continue
        cv = _as_dict(cv_raw)
        if not cv:
            continue
        # Collect non-null non-meta slots
        sec_slots: Dict[str, Any] = {}
        for k, v in cv.items():
            if k.startswith("_"):
                # _cv_meta -> provenance_meta
                if k == "_cv_meta" and isinstance(v, dict):
                    meta = dict(v)
                    # cap confidence at med (CV coverage is thin)
                    if _CONF_ORDER.get(meta.get("confidence"), -1) > _CONF_ORDER["med"]:
                        meta["confidence"] = "med"
                    prov_meta[sec] = meta
                continue
            slot_d = v if isinstance(v, dict) else {}
            val = slot_d.get("value")
            if val is not None:
                sec_slots[k] = {
                    "value": _round(val) if isinstance(val, (int, float)) else val,
                    "unit": slot_d.get("unit"),
                }
        if sec_slots:
            slots[sec] = sec_slots

    data: Dict[str, Any] = {}
    if slots:
        data = {
            "slots": slots,
            "provenance_meta": prov_meta,
            "provenance_note": (
                "season-aggregate CV, descriptive only, confidence capped at med"
            ),
        }

    prov: Dict[str, Any] = {
        "source": "atlas_player_*._cv_fields (player_cv_per_player.parquet)",
        "n_sections_with_fills": len(slots),
        "confidence": "med" if slots else None,
        "as_of": max(
            (m.get("as_of", "") for m in prov_meta.values()), default=None
        ) or None,
        "present": bool(slots),
    }
    return data, prov


# --------------------------------------------------------------------------- #
# Deterministic archetype classification (rule/threshold based)
# --------------------------------------------------------------------------- #
def _classify_archetype(pid: int, prof: Optional[Dict], usage_row: Optional[Dict]) -> Dict[str, Any]:
    """Rule-based playstyle label. NO LLM -- pure thresholds on the numbers.

    Returns {label, secondary, tags, basis}. Designed to read correctly across
    bigs / guards / wings (e.g. Jokic -> 'Playmaking Big', a low-usage high-CS
    wing -> '3&D Wing').
    """
    bio = _safe(prof or {}, "sections", "bio") or {}
    position = (bio.get("position") or "").lower()
    is_big = "center" in position or "forward-center" in position or "c" == position
    is_guard = "guard" in position

    sc = _atlas_row("scoring_creation", pid) or {}
    pm = _atlas_row("playmaking_network", pid) or {}
    rb = _atlas_row("rebounding_profile", pid) or {}
    dp = _atlas_row("defensive_profile", pid) or {}

    usage = _num((usage_row or {}).get("usage_rate"))
    ast_pct = _num((usage_row or {}).get("ast_pct"))
    ast_pts_created = _num(pm.get("ast_pts_created"))
    cs_efg = _num(sc.get("catch_shoot_efg"))
    pts_3pt_share = _num(sc.get("pts_3pt_share"))
    pts_paint_share = _num(sc.get("pts_paint_share"))
    unassisted_2pm = _num(sc.get("unassisted_share_2pm"))
    reb_rate = _num(rb.get("total_reb_rate_mean"))
    cs_3pa = _num(sc.get("catch_shoot_3pa_per_g"))

    tags: List[str] = []
    basis: List[str] = []

    # Percentile-anchored thresholds where available, else absolute fallbacks.
    usage_rank = _pct("usage_rate", usage)
    ast_rank = _pct("ast_pct", ast_pct)
    astc_rank = _pct("ast_pts_created", ast_pts_created)
    reb_rank = _pct("total_reb_rate", reb_rate)
    csefg_rank = _pct("catch_shoot_efg", cs_efg)

    high_usage = usage_rank is not None and usage_rank >= 70
    low_usage = usage_rank is not None and usage_rank <= 40
    high_playmaking = (ast_rank is not None and ast_rank >= 75) or (astc_rank is not None and astc_rank >= 80)
    high_reb = reb_rank is not None and reb_rank >= 80
    high_cs = (csefg_rank is not None and csefg_rank >= 60) and (cs_3pa is not None and cs_3pa >= 2.0)
    self_creator = unassisted_2pm is not None and unassisted_2pm >= 0.55
    floor_spacer = pts_3pt_share is not None and pts_3pt_share >= 0.40
    paint_dominant = pts_paint_share is not None and pts_paint_share >= 0.50

    if high_playmaking:
        tags.append("high_playmaking")
        basis.append(f"ast_pct_rank={ast_rank} ast_pts_created_rank={astc_rank}")
    if high_usage:
        tags.append("high_usage")
        basis.append(f"usage_rank={usage_rank}")
    if low_usage:
        tags.append("low_usage")
        basis.append(f"usage_rank={usage_rank}")
    if high_reb:
        tags.append("rebounder")
        basis.append(f"reb_rate_rank={reb_rank}")
    if high_cs:
        tags.append("catch_and_shoot")
        basis.append(f"cs_efg_rank={csefg_rank} cs_3pa={cs_3pa}")
    if self_creator:
        tags.append("self_creator")
    if floor_spacer:
        tags.append("floor_spacer")
    if paint_dominant:
        tags.append("paint_scorer")
    if is_big:
        tags.append("big")
    if is_guard:
        tags.append("guard")

    # ---- primary label decision tree (ordered, most-specific first) ----
    label = "Role Player"
    if is_big and high_playmaking:
        label = "Playmaking Big"
    elif is_big and high_reb and high_usage:
        label = "Dominant Two-Way Big"
    elif is_big and paint_dominant and high_usage:
        label = "Interior Scoring Big"
    elif is_big and high_reb:
        label = "Rebounding Big"
    elif is_big:
        label = "Stretch Big" if floor_spacer else "Big"
    elif high_usage and high_playmaking:
        label = "Primary Initiator / Lead Guard"
    elif high_usage and self_creator:
        label = "High-Usage Shot Creator"
    elif high_playmaking:
        label = "Playmaking Guard"
    elif low_usage and high_cs:
        label = "3&D Wing"
    elif low_usage and floor_spacer:
        label = "Floor-Spacing Specialist"
    elif high_cs:
        label = "Movement Shooter"
    elif high_usage:
        label = "High-Usage Scorer"

    secondary = None
    if label != "3&D Wing" and low_usage and high_cs:
        secondary = "3&D"
    elif high_reb and "Big" not in label:
        secondary = "Rebounder"
    elif floor_spacer and "Spac" not in label and "Stretch" not in label:
        secondary = "Floor Spacer"

    return {
        "label": label,
        "secondary": secondary,
        "tags": tags,
        "basis": basis,
    }


# --------------------------------------------------------------------------- #
# Strengths / weaknesses (percentile-ranked across the league)
# --------------------------------------------------------------------------- #
# Skill metrics surfaced to the user with friendly labels.
_SKILL_METRICS: List[Tuple[str, str]] = [
    ("usage_rate", "Offensive usage / volume"),
    ("ast_pct", "Playmaking (assist rate)"),
    ("ast_pts_created", "Points created by passing"),
    ("ast_to_tov", "Ball security (assist-to-turnover)"),
    ("total_reb_rate", "Total rebounding"),
    ("oreb_rate", "Offensive rebounding"),
    ("catch_shoot_efg", "Catch-and-shoot efficiency"),
    ("pts_3pt_share", "Three-point scoring share"),
    ("unassisted_2pm", "Self-creation"),
    ("transition_pts_share", "Transition scoring"),
    ("spacing_gravity", "Off-ball gravity / spacing"),
    ("post_up_ppp", "Post-up efficiency"),
    ("rim_protection", "Rim protection"),
    ("stl_block_rate", "Steals + blocks (event defense)"),
    ("on_off_impact", "On/off net-rating impact"),
    ("pie", "All-around impact (PIE)"),
    ("foul_rate", "Foul discipline"),
    ("reb_consistency_cv", "Game-to-game consistency"),
]


def _strengths_weaknesses(pid: int, blocks: Dict[str, Tuple[Dict, Dict]]) -> Dict[str, Any]:
    """Rank the player across league percentiles; surface top strengths/weaknesses."""
    specs = _metric_specs()
    ranked: List[Dict[str, Any]] = []
    for metric, label in _SKILL_METRICS:
        if metric not in specs:
            continue
        sec, acc, _ = specs[metric]
        row = _atlas_row(sec, pid)
        if row is None:
            continue
        try:
            val = acc(row)
        except Exception:
            val = None
        pct = league_percentile(metric, val)
        if pct is None:
            continue
        ranked.append({"metric": metric, "label": label, "value": _round(val, 3),
                       "percentile": pct})
    ranked.sort(key=lambda d: d["percentile"], reverse=True)
    strengths = [r for r in ranked if r["percentile"] >= 75][:6]
    weaknesses = [r for r in reversed(ranked) if r["percentile"] <= 30][:5]
    return {"ranked": ranked, "strengths": strengths, "weaknesses": weaknesses}


# --------------------------------------------------------------------------- #
# Data completeness scoring
# --------------------------------------------------------------------------- #
def _completeness(provenance: Dict[str, Any]) -> Dict[str, Any]:
    """Fraction of the 28 atlas sections present, weighted by confidence."""
    present = 0
    high = 0
    low_or_missing: List[str] = []
    seen: Dict[str, str] = {}  # section -> confidence
    # provenance is nested per block; flatten to per-section confidence
    def _walk(p: Any):
        if isinstance(p, dict):
            if "source" in p and "present" in p:
                src = p["source"].replace("atlas_player_", "").replace(".parquet", "")
                seen[src] = (p.get("confidence") if p.get("present") else None)
            else:
                for v in p.values():
                    _walk(v)
    _walk(provenance)
    for sec in ATLAS_SECTIONS:
        conf = seen.get(sec)
        if conf is not None:
            present += 1
            if conf == "high":
                high += 1
            elif conf in ("low", None):
                low_or_missing.append(sec)
        else:
            low_or_missing.append(sec)
    n = len(ATLAS_SECTIONS)
    score = round((present + high) / (2 * n), 3)  # present=0.5, +0.5 if high-conf
    return {
        "score": score,
        "sections_present": present,
        "sections_total": n,
        "sections_high_conf": high,
        "low_or_missing_sections": low_or_missing,
    }


# --------------------------------------------------------------------------- #
# Deterministic "How <player> plays" narrative (3-5 sentences, rule-generated)
# --------------------------------------------------------------------------- #
def _pct_word(p: Optional[float]) -> str:
    if p is None:
        return ""
    if p >= 95:
        return "elite"
    if p >= 85:
        return "excellent"
    if p >= 70:
        return "above-average"
    if p >= 45:
        return "average"
    if p >= 25:
        return "below-average"
    return "poor"


def _build_narrative(report: Dict[str, Any]) -> str:
    name = report.get("player_name") or f"Player {report['player_id']}"
    arch = _safe(report, "archetype_role", "data", "archetype") or {}
    label = arch.get("label", "Role Player")
    secondary = arch.get("secondary")
    role = report["archetype_role"]["data"]
    sc = report["scoring"]["data"]
    pm = report["playmaking"]["data"]
    rb = report["rebounding"]["data"]
    sw = report["strengths_weaknesses"]

    sents: List[str] = []

    # Sentence 1 -- archetype + usage + minutes
    usage_pct = role.get("usage_pct_rank")
    mins = role.get("minutes_pg")
    tier = role.get("usage_tier")
    s1 = f"{name} is a {label.lower()}"
    if secondary:
        s1 += f" with a {secondary.lower()} secondary role"
    bits = []
    if tier:
        _tier_phrase = {
            "primary": "a primary-option role",
            "secondary": "a secondary-option role",
            "rotation": "a rotation role",
            "bench": "a bench role",
            "low": "a low-usage role",
        }.get(tier, f"a {tier} role")
        bits.append(_tier_phrase)
    if usage_pct is not None:
        bits.append(f"{_pct_word(usage_pct)} offensive volume ({usage_pct:.0f}th pct)")
    if mins:
        bits.append(f"{mins:.0f} minutes per game")
    if bits:
        s1 += " in " + ", ".join(bits)
    sents.append(s1 + ".")

    # Sentence 2 -- how he scores
    if sc:
        dist = sc.get("shot_distribution", {}) or {}
        cre = sc.get("creation", {}) or {}
        paint = dist.get("pts_paint_share")
        three = dist.get("pts_3pt_share")
        unas = cre.get("unassisted_share_2pm")
        scoring_bits = []
        if paint is not None and paint >= 0.45:
            scoring_bits.append(f"scores mostly in the paint ({paint*100:.0f}% of points)")
        elif three is not None and three >= 0.40:
            scoring_bits.append(f"is a perimeter-oriented scorer ({three*100:.0f}% of points from three)")
        if unas is not None:
            if unas >= 0.55:
                scoring_bits.append("creates the bulk of his own looks off the dribble")
            elif unas <= 0.35:
                scoring_bits.append("scores largely off assisted, catch-and-shoot/finishing looks")
        cs_rank = sc.get("catch_shoot_pct_rank")
        if cs_rank is not None and cs_rank >= 70:
            scoring_bits.append(f"is an {_pct_word(cs_rank)} catch-and-shoot threat")
        if scoring_bits:
            sents.append(f"He {'; '.join(scoring_bits)}.")

    # Sentence 3 -- playmaking / rebounding signature
    sig_bits = []
    if pm:
        astc_rank = pm.get("ast_pts_created_rank")
        a2t = pm.get("ast_to_tov")
        if astc_rank is not None and astc_rank >= 75:
            sig_bits.append(f"an {_pct_word(astc_rank)} passer (creates {pm.get('ast_pts_created')} pts/g, {astc_rank:.0f}th pct)")
        if a2t is not None and a2t >= 2.5 and astc_rank is not None and astc_rank >= 60:
            sig_bits.append(f"protects the ball well (A/TO {a2t})")
    if rb:
        reb_rank = rb.get("total_reb_rate_rank")
        if reb_rank is not None and reb_rank >= 80:
            sig_bits.append(f"an {_pct_word(reb_rank)} rebounder ({reb_rank:.0f}th pct)")
    if sig_bits:
        sents.append("He is " + ", and ".join(sig_bits) + ".")

    # Sentence 4 -- top strengths
    strengths = sw.get("strengths", [])
    if strengths:
        names = [s["label"].lower() for s in strengths[:3]]
        sents.append("His standout strengths are " + ", ".join(names) + ".")

    # Sentence 5 -- key weakness / caveat
    weaknesses = sw.get("weaknesses", [])
    if weaknesses:
        w = weaknesses[0]
        sents.append(f"The clearest relative weakness is {w['label'].lower()} ({w['percentile']:.0f}th pct).")

    return " ".join(sents[:5])


# --------------------------------------------------------------------------- #
# Public entrypoint
# --------------------------------------------------------------------------- #
class PlayerReportBuilder:
    """Reusable builder. Holds no per-player state; league percentile tables are
    cached at module level so constructing many reports is cheap.
    """

    def build(self, player_id: int) -> Dict[str, Any]:
        return build_player_report(player_id)


def build_player_report(player_id: int) -> Dict[str, Any]:
    """Synthesize one player's complete intelligence dossier.

    Returns a dict with this schema::

        {
          "schema_version": "player_report/1.0",
          "player_id": int,
          "player_name": str | None,
          "generated_at": ISO date str,
          "as_of": str | None,                 # latest as_of across atlas sections
          # ---- report blocks: each {"data": {...}, "provenance": {...}} ----
          "archetype_role":          {"data", "provenance"},   # incl. data.archetype
          "scoring":                 {"data", "provenance"},
          "playmaking":              {"data", "provenance"},
          "rebounding":              {"data", "provenance"},
          "defense":                 {"data", "provenance"},
          "situational":             {"data", "provenance"},  # ft_profile/matchup_splits/
                                                              # turnover_profile/pace_fit wired
          "consistency_durability":  {"data", "provenance"},
          "cv_behavioral":           {"data", "provenance"},  # non-null CV slots from atlas
                                                              # _cv_fields; empty if none
          # ---- league-relative ranking ----
          "strengths_weaknesses": {
              "ranked":     [{metric,label,value,percentile}...],  # desc by percentile
              "strengths":  [...top >=75th pct...],
              "weaknesses": [...bottom <=30th pct...],
          },
          "data_completeness": {
              "score": float, "sections_present": int, "sections_total": int,
              "sections_high_conf": int, "low_or_missing_sections": [str...],
          },
          "narrative": str,   # deterministic 3-5 sentence "How <player> plays"
        }

    Every block carries ``provenance`` with ``{source, n, confidence, as_of,
    present}`` so the caller can see exactly which atlas section backs each fact
    and skip / discount missing or low-confidence sections.
    """
    pid = int(player_id)
    prof = _load_profile(pid)
    player_name = (prof or {}).get("player_name")

    builders = {
        "archetype_role": _build_archetype_role,
        "scoring": _build_scoring,
        "playmaking": _build_playmaking,
        "rebounding": _build_rebounding,
        "defense": _build_defense,
        "situational": _build_situational,
        "consistency_durability": _build_consistency_durability,
        "cv_behavioral": _build_cv_behavioral,
    }

    report: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "player_id": pid,
        "player_name": player_name,
        "generated_at": _dt.date.today().isoformat(),
    }

    all_prov: Dict[str, Any] = {}
    as_ofs: List[str] = []
    for block, fn in builders.items():
        data, prov = fn(pid, prof)
        report[block] = {"data": data, "provenance": prov}
        all_prov[block] = prov

    # collect as_of dates across all sections
    def _collect_asof(p: Any):
        if isinstance(p, dict):
            if "as_of" in p and p.get("as_of"):
                as_ofs.append(str(p["as_of"]))
            for v in p.values():
                if isinstance(v, dict):
                    _collect_asof(v)
    _collect_asof(all_prov)
    report["as_of"] = max(as_ofs) if as_ofs else None

    # strengths / weaknesses + completeness
    report["strengths_weaknesses"] = _strengths_weaknesses(pid, {})
    report["data_completeness"] = _completeness(all_prov)

    # deterministic narrative
    report["narrative"] = _build_narrative(report)
    return report


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
if __name__ == "__main__":  # pragma: no cover
    import argparse

    ap = argparse.ArgumentParser(description="Build a player intelligence dossier.")
    ap.add_argument("player_id", type=int, help="NBA player id (e.g. 203999 = Jokic)")
    ap.add_argument("--narrative-only", action="store_true")
    args = ap.parse_args()
    rep = build_player_report(args.player_id)
    if args.narrative_only:
        print(rep["narrative"])
    else:
        print(json.dumps(rep, indent=2, default=str))
