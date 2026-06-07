"""
render_schemes_to_vault.py
--------------------------
Render team scheme/identity atlas parquets into the team notes themselves so
each team is a single graph node (no separate Schemes/ cluster).

Writes:
  - vault/Intelligence/Teams/<TRI>.md   — upserts a <!-- SCHEME-AUTO --> block
    holding the full Scheme & Identity Atlas (one per team, 30 teams)
  - vault/Intelligence/_Scheme_Matrix.md — 30-team overview, links [[Teams/TRI]]

Safe to re-run — only touches the SCHEME-AUTO marker block inside each team
note (curated card content + ROSTER-AUTO block are preserved).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "cache"
DEFAULT_TEAMS = ROOT / "vault" / "Intelligence" / "Teams"
MATRIX_PATH = ROOT / "vault" / "Intelligence" / "_Scheme_Matrix.md"

# Marker block folded into each Teams/<TRI>.md note
SCHEME_START = "<!-- SCHEME-AUTO START -->"
SCHEME_END = "<!-- SCHEME-AUTO END -->"
ROSTER_START = "<!-- ROSTER-AUTO START -->"

# ---------------------------------------------------------------------------
# Parquet manifest: (filename, section title, primary_label_fn)
# ---------------------------------------------------------------------------
SCHEME_PARQUETS: list[tuple[str, str]] = [
    ("atlas_team_defensive_scheme.parquet",        "Defensive Scheme & Coverage"),
    ("atlas_team_offensive_scheme.parquet",         "Offensive Scheme"),
    ("atlas_team_rebounding_scheme.parquet",        "Rebounding Scheme"),
    ("atlas_team_pace_identity.parquet",            "Pace Identity"),
    ("atlas_team_paint_defense.parquet",            "Paint Defense"),
    ("atlas_team_three_pt_defense.parquet",         "3-Point Defense"),
    ("atlas_team_transition_defense.parquet",       "Transition Defense"),
    ("atlas_team_halfcourt_offense.parquet",        "Halfcourt Offense"),
    ("atlas_team_turnover_forcing.parquet",         "Turnover Forcing"),
    ("atlas_team_ft_foul_environment.parquet",      "FT / Foul Environment"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _j(val: Any) -> dict | list | Any:
    """Parse JSON string to dict/list if needed; return as-is otherwise."""
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, ValueError):
            return val
    return val


def _fmt(val: Any, dp: int = 3) -> str:
    """Format a value for markdown: floats to dp, dicts/lists as DEFER or inline."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    if isinstance(val, float):
        return f"{val:+.{dp}f}" if dp else f"{val:.3f}"
    if isinstance(val, dict):
        # If it's a DEFER note, say so briefly
        if "_note" in val and "DEFER" in str(val["_note"]):
            return "_DEFER_"
        # Otherwise just dump key scalars
        return str(val)[:120]
    return str(val)


def _note_is_defer(val: Any) -> bool:
    """Return True if the value represents a DEFER (not-yet-available) field."""
    d = _j(val)
    if isinstance(d, dict):
        return "_note" in d and "DEFER" in str(d.get("_note", ""))
    return False


def _safe_get(d: dict | Any, *keys: str, default: Any = None) -> Any:
    """Safely traverse a nested dict with dot-access keys."""
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
    return d


def _md_table(rows: list[tuple[str, str]], headers: tuple[str, str] = ("Field", "Value")) -> str:
    """Build a two-column markdown table."""
    lines = [f"| {headers[0]} | {headers[1]} |", "| --- | --- |"]
    for k, v in rows:
        lines.append(f"| {k} | {v} |")
    return "\n".join(lines)


def _fmt_float(v: Any, dp: int = 3, sign: bool = False) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    try:
        f = float(v)
        fmt = f"{f:+.{dp}f}" if sign else f"{f:.{dp}f}"
        return fmt
    except (TypeError, ValueError):
        return str(v)


# ---------------------------------------------------------------------------
# Per-dimension section renderers
# ---------------------------------------------------------------------------

def _section_defensive_scheme(row: pd.Series) -> str:
    lines: list[str] = []

    cs = _j(row.get("coverage_scheme"))
    if isinstance(cs, dict) and not _note_is_defer(cs):
        dominant = cs.get("dominant_tag", "?")
        all_tags = cs.get("all_tags", [])
        lines.append(f"**Primary coverage:** {dominant}")
        if all_tags:
            lines.append(f"**All tags:** {', '.join(all_tags)}")
        interp = cs.get("interpretation", "")
        if interp:
            lines.append(f"> {interp[:200]}")

    sa = _j(row.get("scheme_axes"))
    if isinstance(sa, dict):
        axis_rows = [
            ("Drop vs Switch",       _fmt_float(sa.get("drop_score"),        3, sign=True)),
            ("Paint Protection",     _fmt_float(sa.get("paint_protection_score"), 3, sign=True)),
            ("Perimeter Denial",     _fmt_float(sa.get("perimeter_denial_score"), 3, sign=True)),
            ("Pace Control",         _fmt_float(sa.get("pace_control_score"), 3, sign=True)),
            ("Iso Force",            _fmt_float(sa.get("iso_force_score"),    3, sign=True)),
            ("Closeout Intensity",   _fmt_float(sa.get("closeout_score"),     3, sign=True)),
        ]
        axis_rows = [(k, v) for k, v in axis_rows if v != "—"]
        if axis_rows:
            lines.append("")
            lines.append("**Scheme axes (z-scores):**")
            lines.append(_md_table(axis_rows, ("Axis", "Score")))

    imp = _j(row.get("imposed_deviations"))
    if isinstance(imp, dict):
        items = [(k, v) for k, v in imp.items()
                 if not k.startswith("_") and isinstance(v, (int, float))]
        items.sort(key=lambda x: abs(x[1]), reverse=True)
        if items:
            lines.append("")
            lines.append("**Imposed deviations on opponents (top features, σ):**")
            table_rows = [(k, _fmt_float(v, 3, sign=True)) for k, v in items[:8]]
            lines.append(_md_table(table_rows, ("Feature", "Δ (σ)")))

    rp = _j(row.get("rim_protection"))
    if isinstance(rp, dict) and not _note_is_defer(rp):
        rim_rows = [
            ("Opp paint% z",         _fmt_float(rp.get("opp_paint_pct_allowed_z"),       3, sign=True)),
            ("Opp 3pt% z",           _fmt_float(rp.get("opp_3pt_pct_allowed_z"),         3, sign=True)),
            ("Opp mid% z",           _fmt_float(rp.get("opp_mid_pct_allowed_z"),         3, sign=True)),
            ("Paint dwell% z",       _fmt_float(rp.get("opp_paint_dwell_pct_allowed_z"), 3, sign=True)),
            ("Shot mix deviation z", _fmt_float(rp.get("opp_shot_mix_deviation_z"),      3, sign=True)),
        ]
        rim_rows = [(k, v) for k, v in rim_rows if v != "—"]
        if rim_rows:
            lines.append("")
            lines.append("**Rim / paint protection (z-scores vs league):**")
            lines.append(_md_table(rim_rows, ("Metric", "z")))

    pp = _j(row.get("perimeter_pressure"))
    if isinstance(pp, dict) and not _note_is_defer(pp):
        pp_rows = [
            ("Contested shot rate z",         _fmt_float(pp.get("opp_contested_shot_rate_imposed_z"),  3, sign=True)),
            ("Avg defender distance z",       _fmt_float(pp.get("opp_avg_defender_distance_imposed_z"),3, sign=True)),
            ("Paint attempts allowed% z",     _fmt_float(pp.get("opp_paint_attempts_allowed_pct_z"),   3, sign=True)),
            ("Pace imposed z",                _fmt_float(pp.get("opp_pace_imposed_z"),                 3, sign=True)),
        ]
        pp_rows = [(k, v) for k, v in pp_rows if v != "—"]
        if pp_rows:
            lines.append("")
            lines.append("**Perimeter pressure (z-scores):**")
            lines.append(_md_table(pp_rows, ("Metric", "z")))

    rc = _j(row.get("ratings_context"))
    if isinstance(rc, dict):
        lines.append("")
        lines.append("**Ratings context:**")
        rc_rows = [
            ("DefRtg",   _fmt_float(rc.get("def_rtg"),   2)),
            ("Pace",     _fmt_float(rc.get("pace"),      2)),
            ("OReb%",    _fmt_float(rc.get("oreb_pct"),  3)),
            ("DReb%",    _fmt_float(rc.get("dreb_pct"),  3)),
            ("N games",  str(rc.get("n_games", "—"))),
        ]
        lines.append(_md_table([(k, v) for k, v in rc_rows if v != "—"], ("Metric", "Value")))

    tip = _j(row.get("top_impact_players"))
    if isinstance(tip, list) and tip:
        lines.append("")
        lines.append("**Top opposing players most affected:**")
        for p in tip[:5]:
            if isinstance(p, dict):
                name = p.get("player_name", "?")
                z = _fmt_float(p.get("max_abs_z"), 2)
                feat = p.get("top_feature", "")
                lines.append(f"- {name}: max |z| = {z} ({feat})")

    return "\n".join(lines)


def _section_offensive_scheme(row: pd.Series) -> str:
    lines: list[str] = []

    pace = _j(row.get("pace"))
    if isinstance(pace, dict):
        label = pace.get("pace_identity", "?")
        pg = _fmt_float(pace.get("pace_pg"), 2)
        lines.append(f"**Pace identity:** {label} (pace = {pg})")

    sd = _j(row.get("shot_diet"))
    if isinstance(sd, dict) and not _note_is_defer(sd):
        lines.append("")
        lines.append("**Shot diet / efficiency:**")
        sd_rows = [
            ("OffRtg",    _fmt_float(sd.get("off_rtg"),   2)),
            ("eFG%",      _fmt_float(sd.get("efg_pct"),   3)),
            ("TOV ratio", _fmt_float(sd.get("tov_ratio"), 2)),
            ("OReb%",     _fmt_float(sd.get("oreb_pct"),  3)),
            ("Ast%",      _fmt_float(sd.get("ast_pct"),   3)),
        ]
        lines.append(_md_table([(k, v) for k, v in sd_rows if v != "—"], ("Metric", "Value")))

    pnr = _j(row.get("pnr"))
    if isinstance(pnr, dict) and not _note_is_defer(pnr):
        pnr_ppp = _fmt_float(pnr.get("pnr_ppp"), 3)
        lines.append(f"\n**PNR PPP:** {pnr_ppp}")

    bm = _j(row.get("ball_movement"))
    if isinstance(bm, dict) and not _note_is_defer(bm):
        lines.append("")
        lines.append("**Ball movement:**")
        bm_rows = [
            ("Passes made/g",    _fmt_float(bm.get("passes_made_per_g_mean"), 2)),
            ("Ast-to-pass%",     _fmt_float(bm.get("ast_to_pass_pct"),       3)),
            ("Ast-to-pass% adj", _fmt_float(bm.get("ast_to_pass_pct_adj"),   3)),
        ]
        lines.append(_md_table([(k, v) for k, v in bm_rows if v != "—"], ("Metric", "Value")))

    dr = _j(row.get("drive_rate"))
    if isinstance(dr, dict) and not _note_is_defer(dr):
        lines.append("")
        lines.append("**Drive rate:**")
        dr_rows = [
            ("Drives/g",     _fmt_float(dr.get("drives_per_g_mean"), 2)),
            ("Drive FG%",    _fmt_float(dr.get("drive_fg_pct"),      3)),
            ("Drive pts%",   _fmt_float(dr.get("drive_pts_pct"),     3)),
            ("Drive ast%",   _fmt_float(dr.get("drive_ast_rate"),    3)),
        ]
        lines.append(_md_table([(k, v) for k, v in dr_rows if v != "—"], ("Metric", "Value")))

    ts = _j(row.get("tempo_spacing_cv"))
    if isinstance(ts, dict) and not _note_is_defer(ts):
        lines.append("")
        lines.append("**Tempo / spacing (CV-derived z-scores):**")
        ts_rows = [
            ("Tempo z",               _fmt_float(ts.get("team_tempo_z"),              3, sign=True)),
            ("Transition share z",    _fmt_float(ts.get("team_transition_share_z"),   3, sign=True)),
            ("Avg spacing z",         _fmt_float(ts.get("team_avg_spacing_z"),        3, sign=True)),
            ("Composite z",           _fmt_float(ts.get("team_tempo_spacing_composite_z"), 3, sign=True)),
        ]
        lines.append(_md_table([(k, v) for k, v in ts_rows if v != "—"], ("Metric", "z")))

    return "\n".join(lines)


def _section_rebounding(row: pd.Series) -> str:
    lines: list[str] = []

    reb_id = row.get("reb_identity", "—")
    lines.append(f"**Rebounding identity:** {reb_id}")

    reb_rows = [
        ("OReb% (season)",        _fmt_float(row.get("oreb_pct_mean"),          3)),
        ("OReb% (L10)",           _fmt_float(row.get("oreb_pct_l10"),           3)),
        ("DReb% (season)",        _fmt_float(row.get("dreb_pct_mean"),          3)),
        ("DReb% (L10)",           _fmt_float(row.get("dreb_pct_l10"),           3)),
        ("Crash rate z",          _fmt_float(row.get("crash_rate_z"),           3, sign=True)),
        ("DReb identity z",       _fmt_float(row.get("dreb_identity_z"),        3, sign=True)),
        ("OReb% season rank",     str(int(row["oreb_pct_season_rank"])) if pd.notna(row.get("oreb_pct_season_rank")) else "—"),
        ("DReb% season rank",     str(int(row["dreb_pct_season_rank"])) if pd.notna(row.get("dreb_pct_season_rank")) else "—"),
    ]
    reb_rows = [(k, v) for k, v in reb_rows if v not in ("—", "nan")]
    lines.append("")
    lines.append(_md_table(reb_rows, ("Metric", "Value")))

    return "\n".join(lines)


def _section_pace(row: pd.Series) -> str:
    lines: list[str] = []

    tempo = _j(row.get("tempo"))
    if isinstance(tempo, dict):
        label = tempo.get("pace_identity_label", "?")
        pg = _fmt_float(tempo.get("pace_pg"), 2)
        spp = _fmt_float(tempo.get("secs_per_poss"), 2)
        lines.append(f"**Pace label:** {label}")
        lines.append(f"**Pace (pg):** {pg}  |  **Secs/poss:** {spp}")

    eff = _j(row.get("efficiency"))
    if isinstance(eff, dict) and not _note_is_defer(eff):
        lines.append("")
        lines.append("**Efficiency:**")
        ef_rows = [
            ("OffRtg",    _fmt_float(eff.get("off_rtg"),   2)),
            ("eFG%",      _fmt_float(eff.get("efg_pct"),   3)),
            ("TOV ratio", _fmt_float(eff.get("tov_ratio"), 2)),
            ("OReb%",     _fmt_float(eff.get("oreb_pct"),  3)),
        ]
        lines.append(_md_table([(k, v) for k, v in ef_rows if v != "—"], ("Metric", "Value")))

    ft_rate = _j(row.get("ft_rate_proxy"))
    if isinstance(ft_rate, dict) and not _note_is_defer(ft_rate):
        ftr = _fmt_float(ft_rate.get("ft_rate_l10"), 3)
        lines.append(f"\n**FT rate (L10):** {ftr}")

    return "\n".join(lines)


def _section_paint_defense(row: pd.Series) -> str:
    lines: list[str] = []

    opa = _j(row.get("opp_paint_allowed"))
    if isinstance(opa, dict) and not _note_is_defer(opa):
        lines.append("**Paint zones allowed (z-scores vs league):**")
        oz_rows = [
            ("Opp paint% z",         _fmt_float(opa.get("opp_paint_pct_allowed_z"),       3, sign=True)),
            ("Opp 3pt% z",           _fmt_float(opa.get("opp_3pt_pct_allowed_z"),         3, sign=True)),
            ("Opp mid% z",           _fmt_float(opa.get("opp_mid_pct_allowed_z"),         3, sign=True)),
            ("Paint dwell% z",       _fmt_float(opa.get("opp_paint_dwell_pct_allowed_z"), 3, sign=True)),
            ("Shot mix deviation z", _fmt_float(opa.get("opp_shot_mix_deviation_z"),      3, sign=True)),
        ]
        oz_rows = [(k, v) for k, v in oz_rows if v != "—"]
        lines.append(_md_table(oz_rows, ("Metric", "z")))

    rd = _j(row.get("rim_defense"))
    if isinstance(rd, dict) and not _note_is_defer(rd):
        lines.append("")
        lines.append("**Rim defense:**")
        rd_rows = [
            ("Rim FG% allowed",       _fmt_float(rd.get("rim_fg_pct_allowed"),   3)),
            ("Rim FG% normal (exp)",  _fmt_float(rd.get("rim_normal_fg_pct"),    3)),
            ("Rim FG% vs normal",     _fmt_float(rd.get("rim_fg_pct_minus_normal"), 3, sign=True)),
            ("Rim freq faced",        _fmt_float(rd.get("rim_freq_faced"),       3)),
            ("Paint FG% allowed",     _fmt_float(rd.get("paint_fg_pct_allowed"), 3)),
        ]
        rd_rows = [(k, v) for k, v in rd_rows if v != "—"]
        lines.append(_md_table(rd_rows, ("Metric", "Value")))

    dr = _j(row.get("def_rtg"))
    if isinstance(dr, dict) and not _note_is_defer(dr):
        def_rtg = _fmt_float(dr.get("def_rtg"), 2)
        lines.append(f"\n**DefRtg:** {def_rtg}")

    return "\n".join(lines)


def _section_3pt_defense(row: pd.Series) -> str:
    lines: list[str] = []

    ta = _j(row.get("opp_3pa_allowed"))
    if isinstance(ta, dict) and not _note_is_defer(ta):
        pct = _fmt_float(ta.get("opp_3p_pct_allowed"),   3)
        pg  = _fmt_float(ta.get("opp_3pa_allowed_pg"),   1)
        pm  = _fmt_float(ta.get("opp_3p_pct_plusminus"), 3, sign=True)
        rate = _fmt_float(ta.get("opp_3pa_rate_allowed"), 3)
        lines.append(f"**Opp 3P%:** {pct}  |  **vs league avg:** {pm}  |  **3PA/g:** {pg}  |  **3PA rate:** {rate}")

    dr = _j(row.get("def_rating"))
    if isinstance(dr, dict) and not _note_is_defer(dr):
        lines.append("")
        dr_rows = [
            ("DefRtg",          _fmt_float(dr.get("def_rtg"),       2)),
            ("DefRtg L10",      _fmt_float(dr.get("def_rtg_last10"), 2)),
            ("DefRtg trend",    _fmt_float(dr.get("def_rtg_trend"),  2, sign=True)),
        ]
        lines.append(_md_table([(k, v) for k, v in dr_rows if v != "—"], ("Metric", "Value")))

    cl = _j(row.get("closeout"))
    if isinstance(cl, dict) and not _note_is_defer(cl):
        cz = _fmt_float(cl.get("opp_closeout_speed_z"), 3, sign=True)
        if cz != "—":
            lines.append(f"\n**Closeout speed z:** {cz}")

    return "\n".join(lines)


def _section_transition_defense(row: pd.Series) -> str:
    lines: list[str] = []

    de = _j(row.get("def_efficiency"))
    if isinstance(de, dict) and not _note_is_defer(de):
        lines.append("**Transition defense efficiency:**")
        de_rows = [
            ("DefRtg (mean)",     _fmt_float(de.get("def_rtg_mean"),    2)),
            ("Pace (mean)",       _fmt_float(de.get("pace_mean"),       2)),
            ("DReb% (mean)",      _fmt_float(de.get("dreb_pct_mean"),   3)),
            ("Possessions/g",     _fmt_float(de.get("possessions_pg"),  2)),
        ]
        de_rows = [(k, v) for k, v in de_rows if v != "—"]
        lines.append(_md_table(de_rows, ("Metric", "Value")))

    ot = _j(row.get("opp_tov"))
    if isinstance(ot, dict) and not _note_is_defer(ot):
        tov_pct = _fmt_float(ot.get("opp_tov_pct_mean"), 3)
        lines.append(f"\n**Opp TOV% (forced):** {tov_pct}")

    tf = _j(row.get("transition_freq"))
    if isinstance(tf, dict) and not _note_is_defer(tf):
        opp_tr = _fmt_float(tf.get("opp_transition_pg"), 2)
        lines.append(f"**Opp transition possessions/g:** {opp_tr}")

    pd_ = _j(row.get("positional_defense"))
    if isinstance(pd_, dict) and not _note_is_defer(pd_):
        lines.append("")
        lines.append("**Positional defense (season):**")
        pd_rows = [
            ("Overall opp FG%",          _fmt_float(pd_.get("overall_d_fg_pct"),        3)),
            ("Rim (<6ft) FG% allowed",   _fmt_float(pd_.get("rim_lt6_d_fg_pct"),        3)),
            ("Rim vs normal",            _fmt_float(pd_.get("rim_lt6_d_fg_pct_plusminus"), 3, sign=True)),
            ("Rim freq faced",           _fmt_float(pd_.get("rim_lt6_freq"),            3)),
        ]
        pd_rows = [(k, v) for k, v in pd_rows if v != "—"]
        lines.append(_md_table(pd_rows, ("Metric", "Value")))

    return "\n".join(lines)


def _section_halfcourt_offense(row: pd.Series) -> str:
    lines: list[str] = []

    eff = _j(row.get("efficiency"))
    if isinstance(eff, dict) and not _note_is_defer(eff):
        lines.append("**Halfcourt efficiency:**")
        ef_rows = [
            ("OffRtg",    _fmt_float(eff.get("off_rtg"),   2)),
            ("eFG%",      _fmt_float(eff.get("efg_pct"),   3)),
            ("TS%",       _fmt_float(eff.get("ts_pct"),    3)),
            ("TOV ratio", _fmt_float(eff.get("tov_ratio"), 2)),
            ("Pace",      _fmt_float(eff.get("pace"),      2)),
        ]
        lines.append(_md_table([(k, v) for k, v in ef_rows if v != "—"], ("Metric", "Value")))

    pm = _j(row.get("play_mix"))
    if isinstance(pm, dict) and not _note_is_defer(pm):
        lines.append("")
        lines.append("**Play type mix (frequency):**")
        pm_rows = [
            ("Spot-up",      _fmt_float(pm.get("spotup_freq"),   3)),
            ("PNR",          _fmt_float(pm.get("pnr_freq"),      3)),
            ("ISO",          _fmt_float(pm.get("iso_freq"),      3)),
            ("Cut",          _fmt_float(pm.get("cut_freq"),      3)),
            ("Handoff",      _fmt_float(pm.get("handoff_freq"),  3)),
            ("Off screen",   _fmt_float(pm.get("off_screen_freq"), 3)),
            ("Post",         _fmt_float(pm.get("post_freq"),     3)),
            ("PNR roll",     _fmt_float(pm.get("pnr_roll_freq"), 3)),
        ]
        lines.append(_md_table([(k, v) for k, v in pm_rows if v != "—"], ("Play type", "Freq")))

    ppp = _j(row.get("ppp"))
    if isinstance(ppp, dict) and not _note_is_defer(ppp):
        lines.append("")
        lines.append("**PPP by play type:**")
        ppp_rows = [
            ("Halfcourt (overall)", _fmt_float(ppp.get("hc_ppp"),        3)),
            ("Spot-up",             _fmt_float(ppp.get("spotup_ppp"),    3)),
            ("Cut",                 _fmt_float(ppp.get("cut_ppp"),       3)),
            ("Handoff",             _fmt_float(ppp.get("handoff_ppp"),   3)),
            ("PNR roll",            _fmt_float(ppp.get("pnr_roll_ppp"),  3)),
            ("Post",                _fmt_float(ppp.get("post_ppp"),      3)),
            ("ISO",                 _fmt_float(ppp.get("iso_ppp"),       3)),
            ("PNR",                 _fmt_float(ppp.get("pnr_ppp"),       3)),
        ]
        lines.append(_md_table([(k, v) for k, v in ppp_rows if v != "—"], ("Play type", "PPP")))

    bm = _j(row.get("ball_movement"))
    if isinstance(bm, dict) and not _note_is_defer(bm):
        lines.append("")
        lines.append("**Ball movement:**")
        bm_rows = [
            ("Drives/g",           _fmt_float(bm.get("drives_per_g_mean"),   2)),
            ("Drive FG%",          _fmt_float(bm.get("drive_fg_pct"),        3)),
            ("Passes made/g",      _fmt_float(bm.get("passes_made_per_g_mean"), 2)),
            ("Ast-to-pass%",       _fmt_float(bm.get("ast_to_pass_pct"),     3)),
        ]
        lines.append(_md_table([(k, v) for k, v in bm_rows if v != "—"], ("Metric", "Value")))

    return "\n".join(lines)


def _section_turnover_forcing(row: pd.Series) -> str:
    lines: list[str] = []

    ot = _j(row.get("opp_tov"))
    if isinstance(ot, dict) and not _note_is_defer(ot):
        forced = _fmt_float(ot.get("opp_tov_pct_forced"), 3)
        l10    = _fmt_float(ot.get("opp_tov_pct_l10"),    3)
        identity = ot.get("opp_tov_rate_identity", "?")
        lines.append(f"**Opp TOV% (season):** {forced}  |  **L10:** {l10}  |  **Identity:** {identity}")

    own = _j(row.get("own_tov"))
    if isinstance(own, dict) and not _note_is_defer(own):
        own_ratio = _fmt_float(own.get("own_tov_ratio"), 2)
        own_id    = own.get("own_tov_identity", "?")
        lines.append(f"**Own TOV ratio:** {own_ratio}  |  **Identity:** {own_id}")

    defl = _j(row.get("deflections"))
    if isinstance(defl, dict) and not _note_is_defer(defl):
        dp  = _fmt_float(defl.get("defl_pg_proxy"), 3)
        lines.append(f"**Deflections/g (proxy):** {dp}")

    pbp = _j(row.get("pbp_transition"))
    if isinstance(pbp, dict) and not _note_is_defer(pbp):
        tr = _fmt_float(pbp.get("transition_count_pg"), 2)
        lines.append(f"**Transition count/g (PBP):** {tr}")

    return "\n".join(lines)


def _section_ft_foul(row: pd.Series) -> str:
    lines: list[str] = []

    fc = _j(row.get("fouls_committed"))
    if isinstance(fc, dict) and not _note_is_defer(fc):
        pf_pg   = _fmt_float(fc.get("pf_pg"),    2)
        pf_l10  = _fmt_float(fc.get("pf_pg_l10"), 2)
        pf_z    = _fmt_float(fc.get("pf_pg_z"),  3, sign=True)
        lines.append(f"**PF/g:** {pf_pg}  |  **L10:** {pf_l10}  |  **z:** {pf_z}")

    ftd = _j(row.get("ft_drawn"))
    if isinstance(ftd, dict) and not _note_is_defer(ftd):
        fta_pg  = _fmt_float(ftd.get("fta_pg"),      2)
        ftm_pg  = _fmt_float(ftd.get("ftm_pg"),      2)
        ft_pct  = _fmt_float(ftd.get("ft_pct_drawn"), 3)
        lines.append(f"**FTA drawn/g:** {fta_pg}  |  **FTM/g:** {ftm_pg}  |  **FT%:** {ft_pct}")

    fta = _j(row.get("ft_allowed"))
    if isinstance(fta, dict) and not _note_is_defer(fta):
        opp_fta   = _fmt_float(fta.get("opp_fta_pg"),           2)
        net_fta   = _fmt_float(fta.get("fta_minus_opp_fta_pg"), 2, sign=True)
        lines.append(f"**Opp FTA allowed/g:** {opp_fta}  |  **Net FTA differential:** {net_fta}")

    oc = _j(row.get("officials_context"))
    if isinstance(oc, dict) and not _note_is_defer(oc):
        rc_foul_z = _fmt_float(oc.get("ref_crew_fouls_z"),  3, sign=True)
        rc_fta_z  = _fmt_float(oc.get("ref_crew_fta_z"),   3, sign=True)
        hw_adv    = _fmt_float(oc.get("home_win_pct_advantage"), 3, sign=True)
        lines.append(f"\n**Officials context (crew z-scores):** Fouls z = {rc_foul_z}  |  FTA z = {rc_fta_z}  |  HW% adv = {hw_adv}")

    pc = _j(row.get("pace_context"))
    if isinstance(pc, dict) and not _note_is_defer(pc):
        pace = _fmt_float(pc.get("pace"), 2)
        lines.append(f"**Pace context:** {pace}")

    return "\n".join(lines)


# Map section title -> renderer function
SECTION_RENDERERS = {
    "Defensive Scheme & Coverage": _section_defensive_scheme,
    "Offensive Scheme":            _section_offensive_scheme,
    "Rebounding Scheme":           _section_rebounding,
    "Pace Identity":               _section_pace,
    "Paint Defense":               _section_paint_defense,
    "3-Point Defense":             _section_3pt_defense,
    "Transition Defense":          _section_transition_defense,
    "Halfcourt Offense":           _section_halfcourt_offense,
    "Turnover Forcing":            _section_turnover_forcing,
    "FT / Foul Environment":       _section_ft_foul,
}


# ---------------------------------------------------------------------------
# Matrix headline extractors
# ---------------------------------------------------------------------------

def _headline_defensive(row: pd.Series) -> str:
    cs = _j(row.get("coverage_scheme"))
    if isinstance(cs, dict):
        return cs.get("dominant_tag", "?")
    return str(row.get("value", "?"))


def _headline_offensive(row: pd.Series) -> str:
    pace = _j(row.get("pace"))
    if isinstance(pace, dict):
        return pace.get("pace_identity", "?")
    return _fmt_float(row.get("value"), 1)


def _headline_rebounding(row: pd.Series) -> str:
    rib = row.get("reb_identity")
    if rib and str(rib) != "nan":
        return str(rib)
    return _fmt_float(row.get("oreb_pct_mean"), 3)


def _headline_pace(row: pd.Series) -> str:
    tempo = _j(row.get("tempo"))
    if isinstance(tempo, dict):
        return tempo.get("pace_identity_label", "?")
    return _fmt_float(row.get("value"), 1)


def _headline_paint_def(row: pd.Series) -> str:
    rd = _j(row.get("rim_defense"))
    if isinstance(rd, dict):
        fg = rd.get("rim_fg_pct_allowed")
        if fg is not None:
            return f"rim {_fmt_float(fg, 3)}"
    return _fmt_float(row.get("value"), 1)


def _headline_3pt_def(row: pd.Series) -> str:
    ta = _j(row.get("opp_3pa_allowed"))
    if isinstance(ta, dict):
        pct = ta.get("opp_3p_pct_allowed")
        pm  = ta.get("opp_3p_pct_plusminus")
        if pct is not None and pm is not None:
            return f"{_fmt_float(pct, 3)} ({_fmt_float(pm, 3, sign=True)} vs lg)"
    return _fmt_float(row.get("value"), 3)


def _headline_trans_def(row: pd.Series) -> str:
    de = _j(row.get("def_efficiency"))
    if isinstance(de, dict):
        rtg = de.get("def_rtg_mean")
        if rtg is not None:
            return f"DefRtg {_fmt_float(rtg, 1)}"
    return _fmt_float(row.get("value"), 1)


def _headline_halfcourt(row: pd.Series) -> str:
    ppp = _j(row.get("ppp"))
    if isinstance(ppp, dict):
        hc = ppp.get("hc_ppp")
        if hc is not None:
            return f"HC PPP {_fmt_float(hc, 3)}"
    return _fmt_float(row.get("value"), 3)


def _headline_tov(row: pd.Series) -> str:
    ot = _j(row.get("opp_tov"))
    if isinstance(ot, dict):
        identity = ot.get("opp_tov_rate_identity")
        forced   = ot.get("opp_tov_pct_forced")
        if identity and forced:
            return f"{identity} ({_fmt_float(forced, 3)})"
    return _fmt_float(row.get("value"), 3)


def _headline_ft(row: pd.Series) -> str:
    ftd = _j(row.get("ft_drawn"))
    if isinstance(ftd, dict):
        fta = ftd.get("fta_pg")
        if fta is not None:
            return f"FTA/g {_fmt_float(fta, 1)}"
    return _fmt_float(row.get("value"), 1)


HEADLINE_FNS = {
    "atlas_team_defensive_scheme.parquet":   _headline_defensive,
    "atlas_team_offensive_scheme.parquet":   _headline_offensive,
    "atlas_team_rebounding_scheme.parquet":  _headline_rebounding,
    "atlas_team_pace_identity.parquet":      _headline_pace,
    "atlas_team_paint_defense.parquet":      _headline_paint_def,
    "atlas_team_three_pt_defense.parquet":   _headline_3pt_def,
    "atlas_team_transition_defense.parquet": _headline_trans_def,
    "atlas_team_halfcourt_offense.parquet":  _headline_halfcourt,
    "atlas_team_turnover_forcing.parquet":   _headline_tov,
    "atlas_team_ft_foul_environment.parquet":_headline_ft,
}


# ---------------------------------------------------------------------------
# Load parquets
# ---------------------------------------------------------------------------

def _load_all() -> dict[str, pd.DataFrame]:
    """Load all scheme parquets; return dict keyed by filename."""
    loaded: dict[str, pd.DataFrame] = {}
    for fname, _ in SCHEME_PARQUETS:
        path = DATA / fname
        if path.exists():
            df = pd.read_parquet(path)
            df = df.set_index("team_tricode")
            loaded[fname] = df
        else:
            print(f"  [WARN] missing parquet: {fname}")
    return loaded


# ---------------------------------------------------------------------------
# Per-team note writer
# ---------------------------------------------------------------------------

def _upsert_scheme_block(note_path: Path, block: str) -> bool:
    """Insert/replace the SCHEME-AUTO block inside a team note.

    Replaces an existing block in place; otherwise inserts before the
    ROSTER-AUTO block if present, else appends. Curated card content and the
    roster block are left untouched. Returns False if the note is absent.
    """
    if not note_path.exists():
        return False
    text = note_path.read_text(encoding="utf-8")
    new_block = f"{SCHEME_START}\n\n{block.strip()}\n\n{SCHEME_END}"

    if SCHEME_START in text and SCHEME_END in text:
        pre = text[: text.index(SCHEME_START)]
        post = text[text.index(SCHEME_END) + len(SCHEME_END) :]
        text = pre + new_block + post
    elif ROSTER_START in text:
        idx = text.index(ROSTER_START)
        text = text[:idx].rstrip() + "\n\n" + new_block + "\n\n" + text[idx:]
    else:
        text = text.rstrip() + "\n\n" + new_block + "\n"

    note_path.write_text(text, encoding="utf-8")
    return True


def _build_scheme_block(tri: str, dfs: dict[str, pd.DataFrame]) -> str:
    """Render the Scheme & Identity Atlas body (sections as H3) for one team."""
    lines: list[str] = []
    lines.append("## Scheme & Identity Atlas")
    lines.append("")
    lines.append("*Auto-generated by render_schemes_to_vault.py — do not edit between SCHEME-AUTO markers*")
    lines.append("")

    for fname, section_title in SCHEME_PARQUETS:
        if fname not in dfs:
            continue
        df = dfs[fname]
        if tri not in df.index:
            continue
        row = df.loc[tri]

        renderer = SECTION_RENDERERS[section_title]
        body = renderer(row).strip()
        if not body:
            continue

        lines.append(f"### {section_title}")
        lines.append("")
        # Promote any H2 the renderer emits to H3 so it nests under the atlas.
        lines.append(body.replace("\n## ", "\n#### "))
        lines.append("")

        # Footer: provenance
        n = row.get("n", "?")
        conf = row.get("confidence", "?")
        as_of = row.get("as_of", "?")
        lines.append(f"*n={n} | confidence={conf} | as_of={as_of}*")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _write_team_note(tri: str, dfs: dict[str, pd.DataFrame], teams_dir: Path) -> bool:
    """Fold the scheme atlas into Teams/<TRI>.md. Returns True if written."""
    block = _build_scheme_block(tri, dfs)
    return _upsert_scheme_block(teams_dir / f"{tri}.md", block)


# ---------------------------------------------------------------------------
# Matrix note writer
# ---------------------------------------------------------------------------

def _write_matrix(teams: list[str], dfs: dict[str, pd.DataFrame], matrix_path: Path) -> None:
    col_names = [
        "Defensive",
        "Offensive",
        "Rebound",
        "Pace",
        "Paint Def",
        "3PT Def",
        "Trans Def",
        "HC Off",
        "TOV Force",
        "FT/Foul",
    ]

    fnames = [f for f, _ in SCHEME_PARQUETS]

    lines: list[str] = []
    lines.append("# Team Scheme Matrix — All 30 Teams")
    lines.append("")
    lines.append("*Auto-generated by render_schemes_to_vault.py — do not edit manually*")
    lines.append("")
    lines.append("Click any team link to open its note (scheme atlas is folded in).")
    lines.append("")

    # Header row
    header = "| Team | " + " | ".join(col_names) + " |"
    sep    = "| --- | " + " | ".join(["---"] * len(col_names)) + " |"
    lines.append(header)
    lines.append(sep)

    for tri in sorted(teams):
        cells = [f"[[Teams/{tri}]]"]
        for fname in fnames:
            if fname not in dfs or tri not in dfs[fname].index:
                cells.append("—")
            else:
                row = dfs[fname].loc[tri]
                hfn = HEADLINE_FNS.get(fname)
                cells.append(hfn(row) if hfn else "?")
        lines.append("| " + " | ".join(cells) + " |")

    lines.append("")
    lines.append("## Index — Team Notes")
    lines.append("")
    for tri in sorted(teams):
        lines.append(f"- [[Teams/{tri}]]")

    matrix_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Matrix written -> {matrix_path}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def render_all(teams_dir: Path | None = None, matrix_path: Path | None = None) -> None:
    """Fold the scheme atlas into each Teams/<TRI>.md + write the matrix overview."""
    if teams_dir is None:
        teams_dir = DEFAULT_TEAMS
    teams_dir = Path(teams_dir)
    if matrix_path is None:
        matrix_path = MATRIX_PATH
    matrix_path = Path(matrix_path)

    print(f"Loading parquets from {DATA} …")
    dfs = _load_all()

    # Collect all teams across all loaded parquets
    teams: set[str] = set()
    for df in dfs.values():
        teams.update(df.index.tolist())

    print(f"Found {len(teams)} teams across {len(dfs)} parquets.")

    coverage: dict[str, int] = {}
    for fname, df in dfs.items():
        coverage[fname] = len(df)

    for fname, n in coverage.items():
        status = "FULL" if n == 30 else f"PARTIAL ({n}/30)"
        print(f"  {fname}: {status}")

    print(f"\nFolding scheme blocks into team notes under {teams_dir} …")
    written = skipped = 0
    for tri in sorted(teams):
        if _write_team_note(tri, dfs, teams_dir):
            written += 1
        else:
            skipped += 1
            print(f"  [skip] {tri}.md missing — scheme block not folded in")

    print(f"  Folded scheme atlas into {written} team notes ({skipped} skipped).")
    _write_matrix(sorted(teams), dfs, matrix_path)
    print("Done.")


if __name__ == "__main__":
    render_all()
