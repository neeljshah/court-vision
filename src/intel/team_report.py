"""team_report.py — synthesize ONE team's complete intelligence dossier.

Reads the 16 shipped ``data/cache/atlas_team_*.parquet`` sections (+ the
persistent team profile JSON when present) and ASSEMBLES them into one coherent,
deterministic dossier covering:

  1. offensive_identity   (offensive_scheme, halfcourt_offense, transition, pace)
  2. defensive_identity   (defensive_scheme, paint/3pt/transition D, TO forcing)
  3. rebounding           (rebounding_scheme)
  4. rotations            (rotation_patterns, bench_production, lineup_synergy)
  5. ft_foul_environment  (ft_foul_environment)
  6. clutch               (clutch_team)
  7. matchup_adjustments  (matchup_adjustments — in-series)
  8. strengths_weaknesses (percentile-ranked across all 30 teams)
  9. how_they_play        (deterministic narrative from the numbers)

DETERMINISTIC ONLY — rule/threshold classification + percentile ranks + key-stat
extraction. No LLM, no external feeds. Scales to all 30 teams at $0/team.

Every block stamps provenance (source sections), as_of, confidence, and the
overall dossier carries a completeness summary (which sections were present /
missing / low-confidence).

Usage (programmatic):
    from src.intel.team_report import build_team_report, build_all_team_reports
    dossier = build_team_report("OKC")

Usage (CLI, writes JSON to data/cache/profiles/teams/<TRI>_dossier.json):
    python scripts/intel/build_team_reports.py [--team OKC] [--no-write]
"""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "cache"
TEAMS_PROF_DIR = CACHE / "profiles" / "teams"
SCHEMA_VERSION = "1.0"

# The 16 shipped team atlas sections (file stem after ``atlas_team_``).
TEAM_SECTIONS = [
    "offensive_scheme", "halfcourt_offense", "pace_identity",
    "transition_halfcourt_splits", "defensive_scheme", "paint_defense",
    "three_pt_defense", "transition_defense", "turnover_forcing",
    "rebounding_scheme", "rotation_patterns", "bench_production",
    "lineup_synergy", "ft_foul_environment", "clutch_team",
    "matchup_adjustments",
]

CONF_ORDER = {"low": 0, "med": 1, "high": 2}


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _safe_read(path: Path) -> Optional[pd.DataFrame]:
    try:
        if path.exists():
            return pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        print(f"  WARN read {path.name}: {exc}")
    return None


def clean(v: Any) -> Any:
    """JSON-safe scalar: NaN/inf -> None, numpy -> python."""
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.ndarray,)):
        return [clean(x) for x in v.tolist()]
    if isinstance(v, (list, tuple)):
        return [clean(x) for x in v]
    if isinstance(v, dict):
        return {str(k): clean(x) for k, x in v.items()}
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def _coerce(v: Any) -> Any:
    """Atlas nested cells are stored as JSON strings — parse them to dict/list."""
    if isinstance(v, str):
        s = v.strip()
        if s and s[0] in "{[":
            try:
                return json.loads(s)
            except (json.JSONDecodeError, ValueError):
                return v
    return v


def _get(d: Any, *keys, default=None):
    """Nested dict get; returns default on any miss / non-dict / DEFER stub.

    Transparently parses JSON-string cells (atlas stores nested structs as str).
    """
    cur = d
    for k in keys:
        cur = _coerce(cur)
        if isinstance(cur, pd.Series):
            cur = cur[k] if k in cur.index else None
        elif isinstance(cur, dict):
            cur = cur.get(k)
        else:
            return default
    cur = _coerce(cur)
    if cur is None:
        return default
    # treat DEFER-only stubs as missing
    if isinstance(cur, dict) and set(cur.keys()) <= {"_note", "_source"}:
        return default
    return clean(cur)


def _is_real(d: Any) -> bool:
    """A nested atlas cell is 'real' if it's not just a DEFER stub."""
    if not isinstance(d, dict):
        return d is not None
    keys = set(d.keys())
    if keys <= {"_note", "_source"}:
        return False
    return any(not str(k).startswith("_") for k in keys)


# ---------------------------------------------------------------------------
# Atlas load + league percentile context
# ---------------------------------------------------------------------------

def load_team_atlases() -> dict[str, pd.DataFrame]:
    """Load every available team atlas section keyed by section name."""
    out: dict[str, pd.DataFrame] = {}
    for sec in TEAM_SECTIONS:
        df = _safe_read(CACHE / f"atlas_team_{sec}.parquet")
        if df is not None and "team_tricode" in df.columns:
            out[sec] = df
    return out


# (section, label, extractor, higher_is_better) — drives league percentile ranks.
# Extractor pulls a single comparable float from one atlas row.
_METRICS: list[tuple[str, str, Any, bool]] = [
    ("offensive_scheme", "off_rtg", lambda r: _get(r, "shot_diet", "off_rtg"), True),
    ("offensive_scheme", "efg_pct", lambda r: _get(r, "shot_diet", "efg_pct"), True),
    ("offensive_scheme", "pace", lambda r: _get(r, "pace", "pace_pg"), True),
    ("offensive_scheme", "ast_pct", lambda r: _get(r, "shot_diet", "ast_pct"), True),
    ("offensive_scheme", "tov_ratio", lambda r: _get(r, "shot_diet", "tov_ratio"), False),
    ("offensive_scheme", "transition_share_z",
     lambda r: _get(r, "tempo_spacing_cv", "team_transition_share_z"), True),
    ("offensive_scheme", "spacing_z",
     lambda r: _get(r, "tempo_spacing_cv", "team_avg_spacing_z"), True),
    ("halfcourt_offense", "halfcourt_efg", lambda r: _get(r, "efficiency", "efg_pct"), True),
    ("halfcourt_offense", "ts_pct", lambda r: _get(r, "efficiency", "ts_pct"), True),
    ("defensive_scheme", "def_rtg", lambda r: _get(r, "ratings_context", "def_rtg"), False),
    ("paint_defense", "rim_fg_pct_allowed",
     lambda r: _get(r, "rim_defense", "rim_fg_pct_allowed"), False),
    ("paint_defense", "paint_fg_pct_allowed",
     lambda r: _get(r, "rim_defense", "paint_fg_pct_allowed"), False),
    ("three_pt_defense", "opp_3p_pct_allowed",
     lambda r: _get(r, "opp_3pa_allowed", "opp_3p_pct_allowed"), False),
    ("three_pt_defense", "opp_3pa_rate_allowed",
     lambda r: _get(r, "opp_3pa_allowed", "opp_3pa_rate_allowed"), False),
    ("turnover_forcing", "opp_tov_pct_forced",
     lambda r: _get(r, "opp_tov", "opp_tov_pct_forced"), True),
    ("rebounding_scheme", "oreb_pct", lambda r: _get(r, "oreb_pct_mean"), True),
    ("rebounding_scheme", "dreb_pct", lambda r: _get(r, "dreb_pct_mean"), True),
    ("clutch_team", "clutch_net_rtg", lambda r: _get(r, "ratings", "net_rtg"), True),
    ("bench_production", "bench_net_rtg",
     lambda r: _get(r, "bench_net_rtg_section", "bench_net_rtg"), True),
    ("lineup_synergy", "top3_lineup_net", lambda r: _get(r, "top3_lineup_net_avg"), True),
    ("ft_foul_environment", "fta_pg", lambda r: _get(r, "ft_drawn", "fta_pg"), True),
    ("ft_foul_environment", "pf_pg", lambda r: _get(r, "fouls_committed", "pf_pg"), False),
    ("transition_defense", "opp_transition_pg",
     lambda r: _get(r, "transition_freq", "opp_transition_pg"), False),
]


def build_league_context(atlases: dict[str, pd.DataFrame]) -> dict[str, dict]:
    """For each metric build {team: {value, rank(1=best), pctile, n}}.

    Percentile is "goodness" (1.0 = best in league for that metric given
    higher_is_better polarity).  rank 1 = best team.
    """
    ctx: dict[str, dict] = {}
    for sec, label, fn, hib in _METRICS:
        df = atlases.get(sec)
        if df is None:
            continue
        vals: dict[str, float] = {}
        for _, row in df.iterrows():
            tri = row["team_tricode"]
            v = fn(row)
            if v is not None:
                vals[tri] = float(v)
        if len(vals) < 3:
            continue
        n = len(vals)
        # rank by goodness: best = highest if hib else lowest
        ordered = sorted(vals.items(), key=lambda kv: kv[1], reverse=hib)
        per_team = {}
        for i, (tri, v) in enumerate(ordered):
            rank = i + 1                       # 1 = best
            pctile = round(1.0 - i / (n - 1), 4) if n > 1 else 1.0  # 1=best,0=worst
            per_team[tri] = {"value": round(v, 4), "rank": rank,
                             "pctile": pctile, "n": n}
        ctx[f"{sec}.{label}"] = {"higher_is_better": hib, "label": label,
                                 "section": sec, "teams": per_team}
    return ctx


def _pctile_word(p: Optional[float]) -> str:
    if p is None:
        return "unknown"
    if p >= 0.90:
        return "elite"
    if p >= 0.70:
        return "strong"
    if p >= 0.40:
        return "average"
    if p >= 0.20:
        return "below-average"
    return "poor"


def _rank_str(entry: dict) -> str:
    return f"{entry['rank']}/{entry['n']}"


# ---------------------------------------------------------------------------
# Per-block builders.  Each returns (block_dict, prov_dict) or None.
# ---------------------------------------------------------------------------

def _row(atlases: dict, sec: str, tri: str) -> Optional[pd.Series]:
    df = atlases.get(sec)
    if df is None:
        return None
    g = df[df["team_tricode"] == tri]
    if g.empty:
        return None
    return g.iloc[0]


def _prov(rows: dict[str, Optional[pd.Series]]) -> dict:
    """Build a provenance stamp from the present source rows of a block."""
    present = {s: r for s, r in rows.items() if r is not None}
    if not present:
        return {"sources": [], "n": 0, "confidence": "low", "as_of": None,
                "missing_sections": list(rows)}
    confs = [str(r.get("confidence") or "low") for r in present.values()]
    # block confidence = lowest of its present sources (conservative)
    block_conf = min(confs, key=lambda c: CONF_ORDER.get(c, 0))
    ns = [int(r.get("n") or 0) for r in present.values() if r.get("n") is not None]
    as_ofs = [str(r.get("as_of")) for r in present.values()
              if r.get("as_of") is not None and str(r.get("as_of"))[:1].isdigit()]
    return {
        "sources": [f"atlas_team_{s}.parquet" for s in present],
        "n": max(ns) if ns else 0,
        "confidence": block_conf if block_conf in CONF_ORDER else "med",
        "as_of": max(as_ofs)[:10] if as_ofs else None,
        "missing_sections": [s for s in rows if s not in present],
    }


def block_offensive_identity(atlases, ctx, tri) -> Optional[tuple]:
    osc = _row(atlases, "offensive_scheme", tri)
    hc = _row(atlases, "halfcourt_offense", tri)
    pa = _row(atlases, "pace_identity", tri)
    th = _row(atlases, "transition_halfcourt_splits", tri)
    rows = {"offensive_scheme": osc, "halfcourt_offense": hc,
            "pace_identity": pa, "transition_halfcourt_splits": th}
    if all(r is None for r in rows.values()):
        return None
    d: dict[str, Any] = {}
    if osc is not None:
        d["pace_pg"] = _get(osc, "pace", "pace_pg")
        d["pace_identity"] = _get(osc, "pace", "pace_identity")
        d["off_rtg"] = _get(osc, "shot_diet", "off_rtg")
        d["efg_pct"] = _get(osc, "shot_diet", "efg_pct")
        d["ast_pct"] = _get(osc, "shot_diet", "ast_pct")
        d["tov_ratio"] = _get(osc, "shot_diet", "tov_ratio")
        d["pnr_ppp"] = _get(osc, "pnr", "pnr_ppp")
        d["drives_per_g"] = _get(osc, "drive_rate", "drives_per_g_mean")
        d["passes_per_g"] = _get(osc, "ball_movement", "passes_made_per_g_mean")
        d["transition_share_z"] = _get(osc, "tempo_spacing_cv", "team_transition_share_z")
        d["spacing_z"] = _get(osc, "tempo_spacing_cv", "team_avg_spacing_z")
    if hc is not None:
        d["halfcourt_play_mix"] = _get(hc, "play_mix")
        d["halfcourt_ppp_by_type"] = _get(hc, "ppp")
        d["halfcourt_ts_pct"] = _get(hc, "efficiency", "ts_pct")
    if pa is not None:
        d["secs_per_poss"] = _get(pa, "tempo", "secs_per_poss")
        d["ft_rate"] = _get(pa, "ft_rate_proxy", "ft_rate_l10")
    if th is not None:
        d["pbp_possession_mix"] = _get(th, "pbp_possession_mix")
        d["transition_share"] = clean(th.get("value"))
    # play-style tags
    tags = []
    pace_id = d.get("pace_identity")
    if pace_id:
        tags.append(f"{pace_id} pace")
    tz = d.get("transition_share_z")
    if tz is not None:
        if tz >= 0.5:
            tags.append("transition-heavy")
        elif tz <= -0.5:
            tags.append("halfcourt-grinding")
    sz = d.get("spacing_z")
    if sz is not None and sz >= 0.5:
        tags.append("high-spacing")
    elif sz is not None and sz <= -0.5:
        tags.append("compressed-spacing")
    # dominant halfcourt set
    pm = d.get("halfcourt_play_mix")
    if isinstance(pm, dict) and pm:
        freqs = {k.replace("_freq", ""): v for k, v in pm.items()
                 if k.endswith("_freq") and isinstance(v, (int, float))}
        if freqs:
            top = max(freqs, key=freqs.get)
            d["primary_halfcourt_set"] = top
            tags.append(f"{top}-primary")
    d["style_tags"] = tags
    return d, _prov(rows)


def block_defensive_identity(atlases, ctx, tri) -> Optional[tuple]:
    dsc = _row(atlases, "defensive_scheme", tri)
    pd_ = _row(atlases, "paint_defense", tri)
    tpd = _row(atlases, "three_pt_defense", tri)
    td = _row(atlases, "transition_defense", tri)
    tf = _row(atlases, "turnover_forcing", tri)
    rows = {"defensive_scheme": dsc, "paint_defense": pd_, "three_pt_defense": tpd,
            "transition_defense": td, "turnover_forcing": tf}
    if all(r is None for r in rows.values()):
        return None
    d: dict[str, Any] = {}
    if dsc is not None:
        d["coverage_scheme"] = _get(dsc, "coverage_scheme", "dominant_tag")
        d["all_scheme_tags"] = _get(dsc, "coverage_scheme", "all_tags")
        d["scheme_axes"] = _get(dsc, "scheme_axes")
        d["def_rtg"] = _get(dsc, "ratings_context", "def_rtg")
        d["switch_rate"] = _get(dsc, "switch_rate")
        tip = _get(dsc, "top_impact_players")
        if isinstance(tip, list):
            d["top_impact_players"] = [p.get("player_name") for p in tip[:3]
                                       if isinstance(p, dict)]
    if pd_ is not None:
        d["rim_fg_pct_allowed"] = _get(pd_, "rim_defense", "rim_fg_pct_allowed")
        d["paint_fg_pct_allowed"] = _get(pd_, "rim_defense", "paint_fg_pct_allowed")
        d["rim_freq_faced"] = _get(pd_, "rim_defense", "rim_freq_faced")
    if tpd is not None:
        d["opp_3p_pct_allowed"] = _get(tpd, "opp_3pa_allowed", "opp_3p_pct_allowed")
        d["opp_3pa_rate_allowed"] = _get(tpd, "opp_3pa_allowed", "opp_3pa_rate_allowed")
        d["def_rtg_trend"] = _get(tpd, "def_rating", "def_rtg_trend")
    if td is not None:
        d["opp_transition_pg"] = _get(td, "transition_freq", "opp_transition_pg")
        d["transition_d_fg_pct"] = _get(td, "positional_defense", "overall_d_fg_pct")
    if tf is not None:
        d["opp_tov_pct_forced"] = _get(tf, "opp_tov", "opp_tov_pct_forced")
        d["deflections_pg"] = _get(tf, "deflections", "defl_pg_proxy")
    # tags
    tags = []
    if d.get("coverage_scheme"):
        tags.append(str(d["coverage_scheme"]).lower())
    axes = d.get("scheme_axes") or {}
    if isinstance(axes, dict):
        if (axes.get("paint_protection_score") or 0) >= 0.3:
            tags.append("rim-protective")
        if (axes.get("perimeter_denial_score") or 0) >= 0.3:
            tags.append("perimeter-denial")
        if (axes.get("drop_score") or 0) >= 0.3:
            tags.append("drop-pnr")
    otf = d.get("opp_tov_pct_forced")
    if otf is not None and otf >= 0.15:
        tags.append("turnover-forcing")
    d["style_tags"] = tags
    return d, _prov(rows)


def block_rebounding(atlases, ctx, tri) -> Optional[tuple]:
    rb = _row(atlases, "rebounding_scheme", tri)
    if rb is None:
        return None
    d = {
        "oreb_pct": _get(rb, "oreb_pct_mean"),
        "dreb_pct": _get(rb, "dreb_pct_mean"),
        "oreb_pct_l10": _get(rb, "oreb_pct_l10"),
        "dreb_pct_l10": _get(rb, "dreb_pct_l10"),
        "oreb_rank": _get(rb, "oreb_pct_season_rank"),
        "dreb_rank": _get(rb, "dreb_pct_season_rank"),
        "crash_rate_z": _get(rb, "crash_rate_z"),
        "reb_identity": _get(rb, "reb_identity"),
    }
    tags = []
    if d.get("reb_identity"):
        tags.append(f"{d['reb_identity']}-rebounding")
    crz = d.get("crash_rate_z")
    if crz is not None:
        if crz >= 0.5:
            tags.append("offensive-glass-crasher")
        elif crz <= -0.5:
            tags.append("get-back-transition-prioritizer")
    d["style_tags"] = tags
    return d, _prov({"rebounding_scheme": rb})


def block_rotations(atlases, ctx, tri) -> Optional[tuple]:
    rp = _row(atlases, "rotation_patterns", tri)
    bp = _row(atlases, "bench_production", tri)
    ls = _row(atlases, "lineup_synergy", tri)
    rows = {"rotation_patterns": rp, "bench_production": bp, "lineup_synergy": ls}
    if all(r is None for r in rows.values()):
        return None
    d: dict[str, Any] = {}
    if rp is not None:
        d["starters"] = _get(rp, "starters", "lineup_names")
        d["n_unique_lineups"] = _get(rp, "depth", "n_unique_lineups")
        d["top3_min_share"] = _get(rp, "depth", "top3_min_share")
        d["lineup_churn_per_game"] = _get(rp, "rotation_stability", "lineup_churn_per_game")
        d["star_q4_min"] = _get(rp, "star_rest", "star_avg_q4_min")
        d["rotation_season"] = clean(rp.get("season_used"))
    if bp is not None:
        d["bench_min_share"] = _get(bp, "bench_minutes", "bench_min_share")
        d["bench_net_rtg"] = _get(bp, "bench_net_rtg_section", "bench_net_rtg")
        d["bench_depth"] = _get(bp, "bench_net_rtg_section", "bench_depth")
    if ls is not None:
        d["top_lineup_net"] = clean(ls.get("top_lineup_net"))
        d["top3_lineup_net_avg"] = clean(ls.get("top3_lineup_net_avg"))
        d["lineup_efg"] = clean(ls.get("lineup_efg"))
        d["lineup_ast_to"] = clean(ls.get("lineup_ast_to"))
        d["league_baseline_top3_net"] = clean(ls.get("league_baseline_top3_net"))
        combo = _coerce(ls.get("combo_5man"))
        if isinstance(combo, (list, np.ndarray)) and len(combo) > 0:
            best = combo[0]
            if isinstance(best, dict):
                d["best_5man"] = {"lineup": clean(best.get("lineup")),
                                  "net_rating": clean(best.get("net_rating"))}
    tags = []
    bms = d.get("bench_min_share")
    if bms is not None:
        if bms >= 0.42:
            tags.append("deep-bench")
        elif bms <= 0.32:
            tags.append("starter-heavy")
    churn = d.get("lineup_churn_per_game")
    if churn is not None:
        if churn <= 1.5:
            tags.append("stable-rotation")
        elif churn >= 3.0:
            tags.append("experimental-rotation")
    d["style_tags"] = tags
    return d, _prov(rows)


def block_ft_foul_environment(atlases, ctx, tri) -> Optional[tuple]:
    ff = _row(atlases, "ft_foul_environment", tri)
    if ff is None:
        return None
    d = {
        "fta_pg": _get(ff, "ft_drawn", "fta_pg"),
        "ftm_pg": _get(ff, "ft_drawn", "ftm_pg"),
        "ft_pct_drawn": _get(ff, "ft_drawn", "ft_pct_drawn"),
        "pf_pg": _get(ff, "fouls_committed", "pf_pg"),
        "pf_pg_z": _get(ff, "fouls_committed", "pf_pg_z"),
        "opp_fta_pg": _get(ff, "ft_allowed", "opp_fta_pg"),
        "fta_minus_opp_fta_pg": _get(ff, "ft_allowed", "fta_minus_opp_fta_pg"),
    }
    tags = []
    diff = d.get("fta_minus_opp_fta_pg")
    if diff is not None:
        if diff >= 2:
            tags.append("ft-advantage")
        elif diff <= -2:
            tags.append("ft-disadvantage")
    pfz = d.get("pf_pg_z")
    if pfz is not None:
        if pfz <= -0.5:
            tags.append("low-foul")
        elif pfz >= 0.5:
            tags.append("high-foul")
    d["style_tags"] = tags
    return d, _prov({"ft_foul_environment": ff})


def block_clutch(atlases, ctx, tri) -> Optional[tuple]:
    ct = _row(atlases, "clutch_team", tri)
    if ct is None:
        return None
    d = {
        "clutch_off_rtg": _get(ct, "ratings", "off_rtg"),
        "clutch_def_rtg": _get(ct, "ratings", "def_rtg"),
        "clutch_net_rtg": _get(ct, "ratings", "net_rtg"),
        "clutch_pace": _get(ct, "ratings", "pace"),
        "clutch_ft_rate": _get(ct, "ft_rate", "ft_rate_mean"),
    }
    tags = []
    net = d.get("clutch_net_rtg")
    if net is not None:
        if net >= 5:
            tags.append("strong-clutch")
        elif net <= -5:
            tags.append("weak-clutch")
    d["style_tags"] = tags
    return d, _prov({"clutch_team": ct})


def block_matchup_adjustments(atlases, ctx, tri) -> Optional[tuple]:
    ma = _row(atlases, "matchup_adjustments", tri)
    if ma is None:
        return None
    d = {
        "n_games_tracked": _get(ma, "adjustment_tendencies", "n_games_tracked"),
        "adjustment_frequency": _get(ma, "adjustment_tendencies", "adjustment_frequency"),
        "matchup_deviations": _get(ma, "matchup_deviations"),
        "imposed_cv_profile": _get(ma, "imposed_cv_profile"),
        "value": clean(ma.get("value")),
    }
    return d, _prov({"matchup_adjustments": ma})


# ---------------------------------------------------------------------------
# Strengths / Weaknesses (league percentile ranked)
# ---------------------------------------------------------------------------

_FRIENDLY = {
    "offensive_scheme.off_rtg": "offensive efficiency",
    "offensive_scheme.efg_pct": "shooting (eFG%)",
    "offensive_scheme.pace": "pace",
    "offensive_scheme.ast_pct": "ball movement (AST%)",
    "offensive_scheme.tov_ratio": "ball security (low TOV)",
    "offensive_scheme.transition_share_z": "transition volume",
    "offensive_scheme.spacing_z": "floor spacing",
    "halfcourt_offense.halfcourt_efg": "halfcourt shooting",
    "halfcourt_offense.ts_pct": "true shooting",
    "defensive_scheme.def_rtg": "defensive efficiency",
    "paint_defense.rim_fg_pct_allowed": "rim protection",
    "paint_defense.paint_fg_pct_allowed": "paint defense",
    "three_pt_defense.opp_3p_pct_allowed": "3pt% defense",
    "three_pt_defense.opp_3pa_rate_allowed": "3pt volume suppression",
    "turnover_forcing.opp_tov_pct_forced": "forcing turnovers",
    "rebounding_scheme.oreb_pct": "offensive rebounding",
    "rebounding_scheme.dreb_pct": "defensive rebounding",
    "clutch_team.clutch_net_rtg": "clutch net rating",
    "bench_production.bench_net_rtg": "bench production",
    "lineup_synergy.top3_lineup_net": "top-lineup synergy",
    "ft_foul_environment.fta_pg": "drawing fouls",
    "ft_foul_environment.pf_pg": "fouling discipline",
    "transition_defense.opp_transition_pg": "limiting opp transition",
}


def block_strengths_weaknesses(ctx, tri) -> Optional[tuple]:
    ranked = []
    for metric, info in ctx.items():
        entry = info["teams"].get(tri)
        if entry is None:
            continue
        ranked.append({
            "metric": metric,
            "label": _FRIENDLY.get(metric, info["label"]),
            "value": entry["value"],
            "rank": entry["rank"],
            "n": entry["n"],
            "pctile": entry["pctile"],
            "tier": _pctile_word(entry["pctile"]),
        })
    if not ranked:
        return None
    ranked.sort(key=lambda x: x["pctile"], reverse=True)
    strengths = [r for r in ranked if r["pctile"] >= 0.70][:6]
    weaknesses = [r for r in ranked if r["pctile"] <= 0.30][-6:]
    weaknesses.sort(key=lambda x: x["pctile"])
    d = {
        "strengths": strengths,
        "weaknesses": weaknesses,
        "all_ranks": ranked,
        "n_metrics_ranked": len(ranked),
    }
    prov = {"sources": ["league percentile across all metrics in ctx"],
            "n": ranked[0]["n"] if ranked else 0,
            "confidence": "high" if len(ranked) >= 10 else "med",
            "as_of": None, "missing_sections": []}
    return d, prov


# ---------------------------------------------------------------------------
# Deterministic "How <team> plays" narrative
# ---------------------------------------------------------------------------

def _fmt(v, pct=False, nd=1):
    if v is None:
        return "n/a"
    if pct:
        return f"{v*100:.{nd}f}%"
    return f"{v:.{nd}f}"


def build_narrative(blocks: dict, ctx: dict, tri: str) -> str:
    parts: list[str] = []
    off = blocks.get("offensive_identity", {}).get("data")
    dfn = blocks.get("defensive_identity", {}).get("data")
    reb = blocks.get("rebounding", {}).get("data")
    rot = blocks.get("rotations", {}).get("data")
    clu = blocks.get("clutch", {}).get("data")
    ff = blocks.get("ft_foul_environment", {}).get("data")
    sw = blocks.get("strengths_weaknesses", {}).get("data")

    # Offense sentence
    if off:
        pace_id = off.get("pace_identity") or "average-pace"
        ortg = off.get("off_rtg")
        ortg_rank = _get(ctx, "offensive_scheme.off_rtg", "teams", tri, "rank")
        seg = f"{tri} runs a {str(pace_id).lower()} offense"
        if ortg is not None:
            seg += f" ({_fmt(ortg)} off-rtg"
            if ortg_rank:
                seg += f", {ortg_rank} in the league"
            seg += ")"
        prim = off.get("primary_halfcourt_set")
        if prim:
            seg += f", leaning on {prim} as its primary halfcourt set"
        tt = off.get("transition_share_z")
        if tt is not None and tt >= 0.5:
            seg += ", and pushes tempo in transition"
        elif tt is not None and tt <= -0.5:
            seg += ", grinding most of its offense in the halfcourt"
        parts.append(seg + ".")

    # Defense sentence
    if dfn:
        scheme = dfn.get("coverage_scheme") or "a mixed coverage"
        drtg = dfn.get("def_rtg")
        drtg_rank = _get(ctx, "defensive_scheme.def_rtg", "teams", tri, "rank")
        seg = f"Defensively they play {str(scheme).lower()}"
        if drtg is not None:
            seg += f" ({_fmt(drtg)} def-rtg"
            if drtg_rank:
                seg += f", {drtg_rank}"
            seg += ")"
        rim = dfn.get("rim_fg_pct_allowed")
        if rim is not None:
            seg += f", allowing {_fmt(rim, pct=True)} at the rim"
        otf = dfn.get("opp_tov_pct_forced")
        if otf is not None and otf >= 0.15:
            seg += f" while forcing turnovers on {_fmt(otf, pct=True)} of possessions"
        parts.append(seg + ".")

    # Rebounding
    if reb and reb.get("reb_identity"):
        seg = (f"On the glass they are a {reb['reb_identity']} rebounding team "
               f"(OREB {_fmt(reb.get('oreb_pct'), pct=True)}, "
               f"DREB {_fmt(reb.get('dreb_pct'), pct=True)})")
        parts.append(seg + ".")

    # Rotations / bench
    if rot:
        bms = rot.get("bench_min_share")
        bnet = rot.get("bench_net_rtg")
        if bms is not None:
            depth_word = ("a deep bench" if bms >= 0.42
                          else "a starter-heavy rotation" if bms <= 0.32
                          else "a balanced rotation")
            seg = f"They run {depth_word} ({_fmt(bms, pct=True)} of minutes to reserves"
            if bnet is not None:
                seg += f", {_fmt(bnet)} bench net-rtg"
            seg += ")"
            parts.append(seg + ".")

    # FT / fouls
    if ff:
        diff = ff.get("fta_minus_opp_fta_pg")
        if diff is not None and abs(diff) >= 2:
            side = "winning" if diff > 0 else "losing"
            parts.append(f"They are {side} the free-throw battle by "
                         f"{_fmt(abs(diff))} attempts per game.")

    # Clutch
    if clu and clu.get("clutch_net_rtg") is not None:
        net = clu["clutch_net_rtg"]
        word = ("dangerous" if net >= 5 else "vulnerable" if net <= -5 else "roughly even")
        parts.append(f"In the clutch they are {word} ({_fmt(net)} net-rtg).")

    # Strengths / weaknesses tail
    if sw:
        st = [s["label"] for s in sw.get("strengths", [])[:3]]
        wk = [w["label"] for w in sw.get("weaknesses", [])[:3]]
        if st:
            parts.append("Biggest strengths: " + ", ".join(st) + ".")
        if wk:
            parts.append("Exploitable weaknesses: " + ", ".join(wk) + ".")

    return " ".join(parts) if parts else f"Insufficient data to characterize {tri}."


# ---------------------------------------------------------------------------
# Top-level assembly
# ---------------------------------------------------------------------------

_BLOCK_BUILDERS = [
    ("offensive_identity", block_offensive_identity),
    ("defensive_identity", block_defensive_identity),
    ("rebounding", block_rebounding),
    ("rotations", block_rotations),
    ("ft_foul_environment", block_ft_foul_environment),
    ("clutch", block_clutch),
    ("matchup_adjustments", block_matchup_adjustments),
]


def build_team_report(
    tri: str,
    atlases: Optional[dict] = None,
    ctx: Optional[dict] = None,
    build_date: Optional[str] = None,
) -> dict:
    """Assemble ONE team's full dossier. Pure function over the atlases."""
    if atlases is None:
        atlases = load_team_atlases()
    if ctx is None:
        ctx = build_league_context(atlases)
    build_date = build_date or date.today().isoformat()

    dossier: dict[str, Any] = {
        "team_tricode": tri,
        "schema_version": SCHEMA_VERSION,
        "last_built": build_date,
        "blocks": {},
    }
    blocks = dossier["blocks"]

    for name, fn in _BLOCK_BUILDERS:
        res = fn(atlases, ctx, tri)
        if res is None:
            blocks[name] = {"data": None, "provenance": None, "present": False}
        else:
            data, prov = res
            blocks[name] = {"data": data, "provenance": prov, "present": True}

    sw = block_strengths_weaknesses(ctx, tri)
    if sw is None:
        blocks["strengths_weaknesses"] = {"data": None, "provenance": None, "present": False}
    else:
        data, prov = sw
        blocks["strengths_weaknesses"] = {"data": data, "provenance": prov, "present": True}

    dossier["how_they_play"] = build_narrative(blocks, ctx, tri)

    # completeness summary
    expected = [n for n, _ in _BLOCK_BUILDERS] + ["strengths_weaknesses"]
    present = [n for n in expected if blocks.get(n, {}).get("present")]
    missing = [n for n in expected if n not in present]
    low_conf = [n for n in present
                if (blocks[n]["provenance"] or {}).get("confidence") == "low"]
    med_conf = [n for n in present
                if (blocks[n]["provenance"] or {}).get("confidence") == "med"]
    # collect newest as_of across blocks
    as_ofs = [(blocks[n]["provenance"] or {}).get("as_of") for n in present]
    as_ofs = [a for a in as_ofs if a and str(a)[:1].isdigit()]
    dossier["as_of_game_date"] = max(as_ofs)[:10] if as_ofs else None
    dossier["completeness"] = {
        "n_blocks_present": len(present),
        "n_blocks_expected": len(expected),
        "coverage_pct": round(100 * len(present) / len(expected), 1),
        "present": present,
        "missing": missing,
        "low_confidence_blocks": low_conf,
        "med_confidence_blocks": med_conf,
    }
    return dossier


def build_all_team_reports(build_date: Optional[str] = None) -> dict[str, dict]:
    atlases = load_team_atlases()
    ctx = build_league_context(atlases)
    tris: set[str] = set()
    for df in atlases.values():
        tris.update(df["team_tricode"].dropna().unique().tolist())
    return {tri: build_team_report(tri, atlases, ctx, build_date)
            for tri in sorted(tris)}
