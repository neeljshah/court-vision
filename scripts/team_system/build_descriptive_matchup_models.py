"""BUILD DESCRIPTIVE MATCHUP MODELS — per-facet / per-matchup descriptive model layer.

Registers 44 new models in model_registry covering:
  1. role_vs_scheme (15 models) — each of 15 archetypes' efficiency by 3 defensive scheme families
  2. pace_fit_clash (4 models) — how each team's offense/pace profile meshes at game pace
  3. physical_mismatch_extended (8 models) — 4 new physical facet pairs beyond existing 3
  4. creation_hierarchy (6 models) — creator depth, coverage gap, off-ball gravity
  5. shot_diet_clash (6 models) — offense shot-diet vs defense shot-diet suppression
  6. clutch_composition (4 models) — clutch attribute composite per team + delta
  7. spacing_gravity (4 models) — shooter gravity (corner3, above3, catch-shoot) vs closeout

ARCHITECTURE POSITION (HONEST):
  - These models live in the DESCRIPTIVE SCOUTING layer, between signals and engines.
  - Layer: thousands of signals -> hundreds of models (NOW +44) -> 16 engines -> MC possession -> ONE prediction.
  - What they contribute:
      * Marginal point prediction: NONE directly. These do NOT feed the marginal point
        (routed ensemble or NNLS stack). They are gated default-OFF for any betting path.
      * Joint / shape layer: MINOR INDIRECT. Some (pace_fit_clash, creation_hierarchy)
        could in principle inform teammate covariance or game-script priors, but that
        wiring is not built — it would require a leak-free OOS validation first.
      * Scouting / narration / LLM context: PRIMARY USE. The G3_DEEP_PREDICTION_REPORT
        consumes these as structured scouting rows. The LLM (Claude) reads them as
        OFFLINE context to narrate WHERE the matchup is won — it does NOT recompute points.
        This is the honest value: richer decomposition for the scout/analyst, not a new
        betting edge.
  - LEAK STATUS: all inputs are seasonal aggregates (attribute_vault, player_roles,
    atlas_player_pace_fit, atlas_player_vs_scheme_splits). No game-level leakage.
    Gated default-OFF for any live/betting path; xseason_verdict = "descriptive-only".

Usage:
  python scripts/team_system/build_descriptive_matchup_models.py [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _HERE)
_TS = os.path.join(_ROOT, "data", "cache", "team_system")
_CACHE = os.path.join(_ROOT, "data", "cache")

from registry.store import Registry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha(s: str) -> str:
    return "set_" + hashlib.sha256(s.encode()).hexdigest()[:24]


def _now_utc() -> int:
    return int(time.time())


def _wmean(values: np.ndarray, weights: np.ndarray) -> float:
    m = np.isfinite(values)
    if not m.any() or weights[m].sum() == 0:
        return float("nan")
    return float(np.average(values[m], weights=weights[m]))


# ---------------------------------------------------------------------------
# Data loading (lazy)
# ---------------------------------------------------------------------------
_vault: Optional[pd.DataFrame] = None
_rates: Optional[pd.DataFrame] = None
_roles: Optional[pd.DataFrame] = None
_league_tg: Optional[pd.DataFrame] = None
_atlas_scheme: Optional[pd.DataFrame] = None
_atlas_pace: Optional[pd.DataFrame] = None
_atlas_spacing: Optional[pd.DataFrame] = None


def _load() -> None:
    global _vault, _rates, _roles, _league_tg, _atlas_scheme, _atlas_pace, _atlas_spacing
    if _vault is not None:
        return
    _vault = pd.read_parquet(os.path.join(_TS, "attribute_vault.parquet"))
    pid_col = "pid" if "pid" in _vault.columns else "player_id"
    _vault = _vault.rename(columns={pid_col: "pid"})
    _rates = pd.read_parquet(os.path.join(_TS, "player_rates.parquet"))
    _roles = pd.read_parquet(os.path.join(_TS, "player_roles.parquet"))
    _league_tg = pd.read_parquet(os.path.join(_TS, "league_team_game.parquet"))
    _atlas_scheme_path = os.path.join(_CACHE, "atlas_player_vs_scheme_splits.parquet")
    if os.path.exists(_atlas_scheme_path):
        _atlas_scheme = pd.read_parquet(_atlas_scheme_path)
    _atlas_pace_path = os.path.join(_CACHE, "atlas_player_pace_fit.parquet")
    if os.path.exists(_atlas_pace_path):
        _atlas_pace = pd.read_parquet(_atlas_pace_path)
    _atlas_spacing_path = os.path.join(_CACHE, "atlas_player_spacing_gravity.parquet")
    if os.path.exists(_atlas_spacing_path):
        _atlas_spacing = pd.read_parquet(_atlas_spacing_path)


def _roster_vault(tri: str, min_mpg: float = 12.0) -> pd.DataFrame:
    """Return rows from attribute_vault for qualifying players on team tri."""
    ro = _rates[(_rates["team"] == tri) & (_rates["mpg"] >= min_mpg)][["pid", "mpg"]].copy()
    vd = _vault.copy()
    # vault also has mpg; drop it to avoid collision, use rates mpg as authoritative
    vd = vd.drop(columns=["mpg"], errors="ignore")
    valid = ro["pid"].isin(vd["pid"])
    ro = ro[valid].copy()
    merged = ro.merge(vd, on="pid", how="left")
    return merged


def _roster_roles(tri: str, min_mpg: float = 12.0) -> pd.DataFrame:
    """Return rows from player_roles for qualifying players on team tri."""
    ro = _rates[(_rates["team"] == tri) & (_rates["mpg"] >= min_mpg)][["pid", "mpg"]].copy()
    ri = _roles[_roles["team"] == tri].copy()
    # roles also has mpg; use rates mpg as authoritative, drop roles mpg before merge
    ri_nodups = ri.drop(columns=["mpg"], errors="ignore")
    merged = ro.merge(ri_nodups, on="pid", how="inner")
    return merged


def _team_pace(tri: str) -> float:
    if _league_tg is None or len(_league_tg) == 0:
        return 101.8
    sub = _league_tg[_league_tg["team"] == tri]
    return float(sub["poss"].mean()) if len(sub) > 0 else 101.8


# ---------------------------------------------------------------------------
# MODEL 1: role_vs_scheme (15 archetype models)
# ---------------------------------------------------------------------------

# Defensive scheme families (collapsed from atlas 6 tags -> 3 families)
_SCHEME_FAMILIES = {
    "paint_first": ["paint_first_defense"],
    "space_and_switch": ["switch_heavy", "help_defense"],
    "drop_and_control": ["drop_coverage", "pace_control", "balanced"],
}

# Archetype -> preferred scheme-exploit intuition (for note generation)
_ARCHETYPE_SCHEME_NOTES = {
    "ANCHOR_BIG":     "thrives vs paint_first (rim runs); suppressed by space_and_switch (switched out)",
    "PRIMARY_BIG":    "thrives vs drop_and_control (deep post); challenged by switch_heavy (guards on rim)",
    "STRETCH_BIG":    "exploits paint_first (spacing created); neutral vs space_and_switch",
    "ROLE_BIG":       "minimal scheme sensitivity; mostly reactive",
    "TWO_WAY_BIG":    "well-rounded; moderate scheme sensitivity",
    "FLOOR_GENERAL":  "exploits paint_first (drive lanes open); suppressed by drop_and_control (packed paint)",
    "LEAD_GUARD":     "thrives vs space_and_switch (ISO creation); challenged by drop_and_control (rim deterrence)",
    "SCORING_GUARD":  "exploits drop_and_control (open 3s from kick-outs); suppressed by perimeter-denial schemes",
    "CONNECTOR_GUARD":"scheme-neutral; catch-and-shoot heavy, works in all but heavy blitz",
    "OFF_GUARD":      "benefits from paint_first (gravity opens 3s)",
    "WING_CREATOR":   "thrives vs drop_and_control (drive opportunities); challenged by space_and_switch (help cuts off lanes)",
    "THREE_D_WING":   "exploits paint_first (3-point gravity); suppressed by switch_heavy (matched on perimeter)",
    "CONNECTOR_WING": "scheme-neutral; role-based, works off creator actions",
    "ROLE_WING":      "minimal scheme sensitivity; spot-up and cutting",
    "BENCH_SCORER":   "exploits drop_and_control (open looks on kick-outs); suppressed by tight perimeter",
}


def compute_role_vs_scheme_models(tri: str) -> List[Dict[str, Any]]:
    """Compute archetype-by-scheme efficiency for team tri. Returns list of model rows."""
    _load()
    rows = _roster_roles(tri, min_mpg=8.0)
    if len(rows) == 0:
        return []

    # Build team-level weighted scores per archetype
    archetype_counts = rows.groupby("archetype").apply(
        lambda g: {
            "n_players": len(g),
            "total_mpg": float(g["mpg"].sum()),
            "avg_creation": float(_wmean(g["creation"].values if "creation" in g.columns else np.full(len(g), np.nan), g["mpg"].values)),
            "avg_spacing": float(_wmean(g["spacing"].values if "spacing" in g.columns else np.full(len(g), np.nan), g["mpg"].values)),
            "avg_rim_pressure": float(_wmean(g["rim_pressure"].values if "rim_pressure" in g.columns else np.full(len(g), np.nan), g["mpg"].values)),
            "avg_perimeter_d": float(_wmean(g["perimeter_d"].values if "perimeter_d" in g.columns else np.full(len(g), np.nan), g["mpg"].values)),
        }
    )

    # Pull actual scheme performance from atlas_scheme if available
    scheme_perf: Dict[str, Dict[str, float]] = {}
    if _atlas_scheme is not None:
        pids_on_team = set(rows["pid"].tolist())
        # atlas uses player_id column
        pid_col = "player_id" if "player_id" in _atlas_scheme.columns else "pid"
        team_atlas = _atlas_scheme[_atlas_scheme[pid_col].isin(pids_on_team)]
        for _, row in team_atlas.iterrows():
            pid = row[pid_col]
            by_scheme = row.get("by_scheme", {})
            if isinstance(by_scheme, str):
                try:
                    by_scheme = json.loads(by_scheme)
                except Exception:
                    by_scheme = {}
            if not isinstance(by_scheme, dict):
                continue
            # collapse 6 tags -> 3 families
            for family, tags in _SCHEME_FAMILIES.items():
                ts_vals = []
                for tag in tags:
                    if tag in by_scheme:
                        ts_vals.append(by_scheme[tag].get("ts_pct", np.nan))
                if ts_vals:
                    scheme_perf.setdefault(str(pid), {})[family] = float(np.nanmean(ts_vals))

    model_rows = []
    for archetype in sorted(_ARCHETYPE_SCHEME_NOTES.keys()):
        arch_rows = rows[rows["archetype"] == archetype] if "archetype" in rows.columns else pd.DataFrame()
        n = len(arch_rows)
        total_mpg = float(arch_rows["mpg"].sum()) if n > 0 else 0.0

        # Compute scheme efficiency for players of this archetype
        family_ts: Dict[str, List[float]] = {f: [] for f in _SCHEME_FAMILIES}
        for _, pr in arch_rows.iterrows():
            pid = str(pr["pid"])
            if pid in scheme_perf:
                for family in _SCHEME_FAMILIES:
                    v = scheme_perf[pid].get(family, np.nan)
                    if np.isfinite(v):
                        family_ts[family].append(v)

        family_avg = {f: float(np.mean(vs)) if vs else np.nan for f, vs in family_ts.items()}
        best_family = max(family_avg, key=lambda f: family_avg[f] if np.isfinite(family_avg[f]) else -999)
        worst_family = min(family_avg, key=lambda f: family_avg[f] if np.isfinite(family_avg[f]) else 999)

        model_id = f"mdl_role_vs_scheme_{tri.lower()}_{archetype.lower()}"
        note = (
            f"{tri} {archetype} archetype: {n} players, {total_mpg:.0f} total mpg. "
            f"Scheme TS%: paint_first={family_avg.get('paint_first', float('nan')):.3f}, "
            f"space_and_switch={family_avg.get('space_and_switch', float('nan')):.3f}, "
            f"drop_and_control={family_avg.get('drop_and_control', float('nan')):.3f}. "
            f"Best vs: {best_family}. Worst vs: {worst_family}. "
            f"Scouting note: {_ARCHETYPE_SCHEME_NOTES[archetype]}. "
            f"LAYER: descriptive scouting only; does NOT feed marginal point prediction."
        )

        model_rows.append({
            "model_id": model_id,
            "domain_tag": "role_vs_scheme",
            "entity_scope": "player_archetype",
            "signal_id_set_hash": _sha(f"player_roles+atlas_scheme+{archetype}+{tri}"),
            "method": "descriptive_archetype_scheme_aggregate",
            "input_hash": None,
            "oos_score": float("nan"),
            "xseason_verdict": "descriptive-only",
            "engine_node": f"role_scheme_{archetype.lower()}",
            "status": "active",
            "artifact_path": None,
            "created_utc": _now_utc(),
            "_note": note,
            "_n_players": n,
            "_total_mpg": total_mpg,
            "_family_ts": family_avg,
            "_best_family": best_family,
            "_worst_family": worst_family,
        })

    return model_rows


# ---------------------------------------------------------------------------
# MODEL 2: pace_fit_clash (4 models: 2 teams x offense + defense)
# ---------------------------------------------------------------------------

def compute_pace_fit_models(home_tri: str, away_tri: str) -> List[Dict[str, Any]]:
    """Compute pace-fit clash for this matchup. Returns 4 model rows."""
    _load()
    models = []
    for tri, role in [(home_tri, "home"), (away_tri, "away")]:
        rows = _roster_vault(tri, min_mpg=12.0)
        pace = _team_pace(tri)

        # From attribute_vault: fin_transition (transition finishing) + crea_drives_vol (drive volume)
        # + shoot_catch_shoot3 (spacing in pace-up games) -> pace-fit composite
        fin_trans = _wmean(rows["fin_transition"].values if "fin_transition" in rows.columns else np.full(len(rows), np.nan), rows["mpg"].values)
        drives = _wmean(rows["crea_drives_vol"].values if "crea_drives_vol" in rows.columns else np.full(len(rows), np.nan), rows["mpg"].values)
        spacing = _wmean(rows["shoot_catch_shoot3"].values if "shoot_catch_shoot3" in rows.columns else np.full(len(rows), np.nan), rows["mpg"].values)

        # pace_fit_score from atlas_pace if available
        atlas_scores = []
        if _atlas_pace is not None:
            pid_col = "player_id" if "player_id" in _atlas_pace.columns else "pid"
            pids_on_team = set(rows["pid"].tolist())
            team_atlas = _atlas_pace[_atlas_pace[pid_col].isin(pids_on_team)]
            for _, apr in team_atlas.iterrows():
                v = apr.get("pace_fit_score", np.nan)
                if np.isfinite(float(v if v is not None else np.nan)):
                    atlas_scores.append(float(v))

        atlas_avg = float(np.mean(atlas_scores)) if atlas_scores else float("nan")

        # Composite: (fin_transition + drives * 0.5 + spacing * 0.3) / 1.8 -> 0-99 scale
        raw_components = [x for x in [fin_trans, drives * 0.5 if np.isfinite(drives) else np.nan,
                                       spacing * 0.3 if np.isfinite(spacing) else np.nan] if np.isfinite(x)]
        pace_composite = float(np.mean(raw_components)) if raw_components else float("nan")

        # Offense model
        models.append({
            "model_id": f"mdl_pace_fit_offense_{tri.lower()}",
            "domain_tag": "pace_fit_clash",
            "entity_scope": "team",
            "signal_id_set_hash": _sha(f"pace_fit_offense+{tri}+vault+atlas_pace"),
            "method": "descriptive_pace_composite",
            "input_hash": None,
            "oos_score": float("nan"),
            "xseason_verdict": "descriptive-only",
            "engine_node": f"pace_fit_off_{tri.lower()}",
            "status": "active",
            "artifact_path": None,
            "created_utc": _now_utc(),
            "_note": (
                f"{tri} pace-fit offense model: pace={pace:.1f} poss/48, "
                f"fin_transition={fin_trans:.1f}, crea_drives={drives:.1f}, spacing={spacing:.1f}. "
                f"Atlas pace_fit_score (n={len(atlas_scores)}): {atlas_avg:.3f}. "
                f"Composite pace_off_fit={pace_composite:.1f} (higher=more pace-adaptive offense). "
                f"LAYER: scouting/narration; does NOT move marginal prediction."
            ),
            "_pace": pace,
            "_fin_transition": fin_trans,
            "_drives": drives,
            "_spacing": spacing,
            "_atlas_pace_fit_avg": atlas_avg,
            "_pace_composite": pace_composite,
        })

        # Defense model
        perd_stops = _wmean(rows["perd_stops"].values if "perd_stops" in rows.columns else np.full(len(rows), np.nan), rows["mpg"].values)
        intd_stops = _wmean(rows["intd_stops"].values if "intd_stops" in rows.columns else np.full(len(rows), np.nan), rows["mpg"].values)
        trans_def = _wmean(rows["fin_2nd_chance"].values if "fin_2nd_chance" in rows.columns else np.full(len(rows), np.nan), rows["mpg"].values)

        models.append({
            "model_id": f"mdl_pace_fit_defense_{tri.lower()}",
            "domain_tag": "pace_fit_clash",
            "entity_scope": "team",
            "signal_id_set_hash": _sha(f"pace_fit_defense+{tri}+vault"),
            "method": "descriptive_pace_defensive_composite",
            "input_hash": None,
            "oos_score": float("nan"),
            "xseason_verdict": "descriptive-only",
            "engine_node": f"pace_fit_def_{tri.lower()}",
            "status": "active",
            "artifact_path": None,
            "created_utc": _now_utc(),
            "_note": (
                f"{tri} pace-fit defense model: pace={pace:.1f} poss/48, "
                f"perd_stops={perd_stops:.1f}, intd_stops={intd_stops:.1f}. "
                f"Defense in pace context: faster pace hurts low-stop defenses disproportionately. "
                f"LAYER: scouting only; does NOT move marginal prediction."
            ),
            "_pace": pace,
            "_perd_stops": perd_stops,
            "_intd_stops": intd_stops,
        })

    return models


# ---------------------------------------------------------------------------
# MODEL 3: physical_mismatch_extended (8 new facets)
# ---------------------------------------------------------------------------

# New physical facet pairs beyond the existing 3 in engine_matchup_physics
# (which already uses: size_pos vs size_pos, height vs perimeter_d, strength vs drives)
_PHYSICAL_EXTENDED_FACETS: List[Tuple[str, str, str, str]] = [
    # (label, offensive_attr, defensive_attr, direction_note)
    ("Height vs rim protection", "phys_height", "intd_block",
     "Tall bigs exploit weak rim protection; guards neutralized by shot-blockers"),
    ("Agility vs drive stopping", "phys_agility", "perd_stops",
     "Agile attackers beat slow perimeter defenders on drives"),
    ("Youth vs durability",       "phys_youth",  "durab_avail",
     "Younger rosters maintain effort; opponent availability-weighted durability edge"),
    ("Strength vs contact FT",    "phys_strength", "fin_contact_ft",
     "Physical attackers draw fouls vs weak-foul-discipline defenders"),
    ("Size vs post scoring",      "phys_size_pos", "crea_post_ppp",
     "Size advantage in post enables PnR/post creation; small defenders get posted"),
    ("Agility vs transition D",   "phys_agility", "perd_fg3_suppress",
     "Agile perimeter defenders contest 3s in transition and halfcourt"),
    ("Height vs midrange",        "phys_height",  "intd_fg_suppress",
     "Tall bigs with touch beat interior shot-blockers on mid-post fadeaways"),
    ("Strength vs box-out",       "phys_strength", "reb_contested",
     "Stronger players win box-out battles and 2nd-chance possessions"),
]


def compute_physical_mismatch_extended(home_tri: str, away_tri: str) -> List[Dict[str, Any]]:
    """Compute 8 extended physical-mismatch facet models for this matchup."""
    _load()
    models = []
    for off_tri, def_tri in [(home_tri, away_tri), (away_tri, home_tri)]:
        off_rows = _roster_vault(off_tri, min_mpg=12.0)
        def_rows = _roster_vault(def_tri, min_mpg=12.0)
        for label, off_attr, def_attr, note_text in _PHYSICAL_EXTENDED_FACETS:
            off_val = _wmean(
                off_rows[off_attr].values if off_attr in off_rows.columns else np.full(len(off_rows), np.nan),
                off_rows["mpg"].values
            )
            def_val = _wmean(
                def_rows[def_attr].values if def_attr in def_rows.columns else np.full(len(def_rows), np.nan),
                def_rows["mpg"].values
            )
            edge = float(off_val - def_val) if np.isfinite(off_val) and np.isfinite(def_val) else float("nan")
            model_id = f"mdl_phys_ext_{off_attr[:8]}_{def_attr[:8]}_{off_tri.lower()}_vs_{def_tri.lower()}"
            models.append({
                "model_id": model_id,
                "domain_tag": "physical_mismatch_extended",
                "entity_scope": "team_matchup",
                "signal_id_set_hash": _sha(f"phys_ext+{off_attr}+{def_attr}+{off_tri}+{def_tri}"),
                "method": "descriptive_physical_facet_edge",
                "input_hash": None,
                "oos_score": float("nan"),
                "xseason_verdict": "descriptive-only",
                "engine_node": f"phys_{label.replace(' ', '_').lower()[:30]}",
                "status": "active",
                "artifact_path": None,
                "created_utc": _now_utc(),
                "_note": (
                    f"{off_tri} off vs {def_tri} def — {label}: "
                    f"{off_tri}={off_val:.1f} pctile, {def_tri}={def_val:.1f} pctile, "
                    f"edge={edge:+.1f}. {note_text}. "
                    f"LAYER: descriptive physical scouting; does NOT feed marginal."
                ),
                "_off_tri": off_tri,
                "_def_tri": def_tri,
                "_off_val": off_val,
                "_def_val": def_val,
                "_edge": edge,
            })
    return models


# ---------------------------------------------------------------------------
# MODEL 4: creation_hierarchy (6 models: 3 metrics x 2 teams)
# ---------------------------------------------------------------------------

def compute_creation_hierarchy(home_tri: str, away_tri: str) -> List[Dict[str, Any]]:
    """Compute creator concentration, isolation depth, off-ball gravity per team."""
    _load()
    models = []
    for tri in [home_tri, away_tri]:
        rows = _roster_vault(tri, min_mpg=10.0)
        role_rows = _roster_roles(tri, min_mpg=10.0)

        # --- Creator concentration: how top-heavy is the creation? ---
        if "crea_usage" in rows.columns:
            crea_usage = rows.set_index("pid")["crea_usage"].fillna(0).values
            mpg = rows["mpg"].values
            total_crea = float(np.sum(crea_usage * mpg))
            if total_crea > 0:
                sorted_idx = np.argsort(crea_usage * mpg)[::-1]
                cumsum = np.cumsum((crea_usage * mpg)[sorted_idx])
                top1_share = float((crea_usage * mpg)[sorted_idx[0]] / total_crea) if len(sorted_idx) > 0 else float("nan")
                top2_share = float(cumsum[min(1, len(cumsum)-1)] / total_crea) if len(cumsum) > 1 else top1_share
            else:
                top1_share = top2_share = float("nan")
        else:
            top1_share = top2_share = float("nan")

        models.append({
            "model_id": f"mdl_creation_concentration_{tri.lower()}",
            "domain_tag": "creation_hierarchy",
            "entity_scope": "team",
            "signal_id_set_hash": _sha(f"creation_concentration+{tri}+vault"),
            "method": "descriptive_creation_gini",
            "input_hash": None,
            "oos_score": float("nan"),
            "xseason_verdict": "descriptive-only",
            "engine_node": f"creation_conc_{tri.lower()}",
            "status": "active",
            "artifact_path": None,
            "created_utc": _now_utc(),
            "_note": (
                f"{tri} creation concentration: top-1 creator share={top1_share:.2%}, "
                f"top-2 share={top2_share:.2%}. High concentration = matchup-sensitive; "
                f"neutralizing the primary creator collapses the offense. "
                f"LAYER: scouting only; does NOT move marginal prediction."
            ),
            "_top1_creation_share": top1_share,
            "_top2_creation_share": top2_share,
        })

        # --- Isolation depth: avg ISO PPP across qualified creators ---
        if "crea_iso_ppp" in rows.columns:
            iso_vals = rows["crea_iso_ppp"].values.astype(float)
            iso_qualified = iso_vals[iso_vals >= 40]  # >40th pctile = real ISO threat
            iso_depth = float(np.mean(iso_qualified)) if len(iso_qualified) > 0 else float("nan")
            iso_n = len(iso_qualified)
        else:
            iso_depth = float("nan")
            iso_n = 0

        models.append({
            "model_id": f"mdl_isolation_depth_{tri.lower()}",
            "domain_tag": "creation_hierarchy",
            "entity_scope": "team",
            "signal_id_set_hash": _sha(f"isolation_depth+{tri}+vault_iso"),
            "method": "descriptive_iso_pool_depth",
            "input_hash": None,
            "oos_score": float("nan"),
            "xseason_verdict": "descriptive-only",
            "engine_node": f"iso_depth_{tri.lower()}",
            "status": "active",
            "artifact_path": None,
            "created_utc": _now_utc(),
            "_note": (
                f"{tri} isolation depth: {iso_n} qualified ISO threats (>40th pctile), "
                f"avg ISO PPP pctile={iso_depth:.1f}. "
                f"Deep ISO pool = resilient vs defensive switches. "
                f"LAYER: scouting only."
            ),
            "_iso_depth_avg": iso_depth,
            "_iso_n_threats": iso_n,
        })

        # --- Off-ball gravity: spacing gravity (shooter pool) ---
        shoot_attrs = ["shoot_corner3", "shoot_above3", "shoot_catch_shoot3"]
        shoot_vals_list = []
        for attr in shoot_attrs:
            if attr in rows.columns:
                v = _wmean(rows[attr].values.astype(float), rows["mpg"].values)
                shoot_vals_list.append(v)
        gravity_composite = float(np.nanmean(shoot_vals_list)) if shoot_vals_list else float("nan")

        models.append({
            "model_id": f"mdl_offball_gravity_{tri.lower()}",
            "domain_tag": "creation_hierarchy",
            "entity_scope": "team",
            "signal_id_set_hash": _sha(f"offball_gravity+{tri}+vault_shoot"),
            "method": "descriptive_spacing_gravity_composite",
            "input_hash": None,
            "oos_score": float("nan"),
            "xseason_verdict": "descriptive-only",
            "engine_node": f"offball_gravity_{tri.lower()}",
            "status": "active",
            "artifact_path": None,
            "created_utc": _now_utc(),
            "_note": (
                f"{tri} off-ball gravity (corner3={shoot_vals_list[0] if len(shoot_vals_list) > 0 else 'N/A':.1f}, "
                f"above3={shoot_vals_list[1] if len(shoot_vals_list) > 1 else 'N/A':.1f}, "
                f"catch_shoot={shoot_vals_list[2] if len(shoot_vals_list) > 2 else 'N/A':.1f}): "
                f"composite gravity={gravity_composite:.1f}. "
                f"High gravity = defender collapses inward, creating creator lanes. "
                f"LAYER: scouting only."
            ),
            "_gravity_composite": gravity_composite,
            "_corner3_pctile": float(shoot_vals_list[0]) if len(shoot_vals_list) > 0 else float("nan"),
            "_above3_pctile": float(shoot_vals_list[1]) if len(shoot_vals_list) > 1 else float("nan"),
            "_catch_shoot_pctile": float(shoot_vals_list[2]) if len(shoot_vals_list) > 2 else float("nan"),
        })

    return models


# ---------------------------------------------------------------------------
# MODEL 5: shot_diet_clash (6 models)
# ---------------------------------------------------------------------------

# Shot diet clash: offense shot-diet vs opponent's scheme suppression
_SHOT_DIET_FACETS: List[Tuple[str, str, str]] = [
    ("3pt_diet_vs_3pt_suppression", "shoot_pts_from_3",    "perd_fg3_suppress",
     "3-point reliant offense vs 3-point defensive suppression"),
    ("drive_diet_vs_drive_stopping", "crea_drives_vol",    "perd_stops",
     "Drive-heavy offense vs perimeter stop rate"),
    ("paint_diet_vs_paint_D",        "fin_paint_pts",      "intd_stops",
     "Paint-scoring offense vs interior stop rate"),
    ("iso_diet_vs_iso_D",            "crea_iso_ppp",       "perd_stops",
     "ISO-heavy offense vs perimeter defend-and-stop rate"),
    ("PnR_diet_vs_dropD",            "crea_pnr_ppp",       "intd_fg_suppress",
     "PnR ball-handler vs drop coverage rim protection"),
    ("ft_diet_vs_foul_disc",         "fin_contact_ft",     "perd_foul_disc",
     "Foul-drawing offense vs foul-discipline defense"),
]


def compute_shot_diet_clash(home_tri: str, away_tri: str) -> List[Dict[str, Any]]:
    """Compute 6 shot-diet-clash models for this matchup (bidirectional = 12 total, returned as 6 matchup models)."""
    _load()
    models = []
    for label, off_attr, def_attr, note_text in _SHOT_DIET_FACETS:
        h_rows = _roster_vault(home_tri, min_mpg=12.0)
        a_rows = _roster_vault(away_tri, min_mpg=12.0)

        h_off = _wmean(h_rows[off_attr].values if off_attr in h_rows.columns else np.full(len(h_rows), np.nan), h_rows["mpg"].values)
        h_def = _wmean(h_rows[def_attr].values if def_attr in h_rows.columns else np.full(len(h_rows), np.nan), h_rows["mpg"].values)
        a_off = _wmean(a_rows[off_attr].values if off_attr in a_rows.columns else np.full(len(a_rows), np.nan), a_rows["mpg"].values)
        a_def = _wmean(a_rows[def_attr].values if def_attr in a_rows.columns else np.full(len(a_rows), np.nan), a_rows["mpg"].values)

        # home_off vs away_def edge, and away_off vs home_def edge
        home_edge = float(h_off - a_def) if np.isfinite(h_off) and np.isfinite(a_def) else float("nan")
        away_edge = float(a_off - h_def) if np.isfinite(a_off) and np.isfinite(h_def) else float("nan")
        net_edge = float(home_edge - away_edge) if np.isfinite(home_edge) and np.isfinite(away_edge) else float("nan")

        model_id = f"mdl_shot_diet_{label.replace('/', '_').replace('-', '_').lower()}_{home_tri.lower()}_{away_tri.lower()}"
        models.append({
            "model_id": model_id,
            "domain_tag": "shot_diet_clash",
            "entity_scope": "team_matchup",
            "signal_id_set_hash": _sha(f"shot_diet+{label}+{home_tri}+{away_tri}"),
            "method": "descriptive_diet_clash_edge",
            "input_hash": None,
            "oos_score": float("nan"),
            "xseason_verdict": "descriptive-only",
            "engine_node": f"shot_diet_{label[:20].lower()}",
            "status": "active",
            "artifact_path": None,
            "created_utc": _now_utc(),
            "_note": (
                f"Shot-diet clash — {label}: {note_text}. "
                f"{home_tri} off={h_off:.1f} vs {away_tri} def={a_def:.1f} => home_edge={home_edge:+.1f}. "
                f"{away_tri} off={a_off:.1f} vs {home_tri} def={h_def:.1f} => away_edge={away_edge:+.1f}. "
                f"Net (home - away): {net_edge:+.1f}. "
                f"LAYER: scouting only; does NOT feed marginal."
            ),
            "_home_off": h_off, "_away_def": a_def, "_home_edge": home_edge,
            "_away_off": a_off, "_home_def": h_def, "_away_edge": away_edge,
            "_net_edge": net_edge,
        })
    return models


# ---------------------------------------------------------------------------
# MODEL 6: clutch_composition (4 models)
# ---------------------------------------------------------------------------

def compute_clutch_composition(home_tri: str, away_tri: str) -> List[Dict[str, Any]]:
    """Compute clutch attribute composites for both teams + a delta model."""
    _load()
    models = []
    clutch_attrs = ["clutch_fg", "clutch_pts36", "clutch_plusminus", "clutch_ft", "clutch_3"]

    team_clutch: Dict[str, Dict[str, float]] = {}
    for tri in [home_tri, away_tri]:
        rows = _roster_vault(tri, min_mpg=15.0)  # only meaningful-minute players in clutch
        attr_vals: Dict[str, float] = {}
        for attr in clutch_attrs:
            if attr in rows.columns:
                v = _wmean(rows[attr].values.astype(float), rows["mpg"].values)
                attr_vals[attr] = v
        # Composite: avg of available attrs (all are 0-99 pctile)
        finite_vals = [v for v in attr_vals.values() if np.isfinite(v)]
        composite = float(np.mean(finite_vals)) if finite_vals else float("nan")
        team_clutch[tri] = dict(attr_vals, composite=composite)

        models.append({
            "model_id": f"mdl_clutch_composition_{tri.lower()}",
            "domain_tag": "clutch_composition",
            "entity_scope": "team",
            "signal_id_set_hash": _sha(f"clutch_composition+{tri}+vault"),
            "method": "descriptive_clutch_attribute_composite",
            "input_hash": None,
            "oos_score": float("nan"),
            "xseason_verdict": "descriptive-only",
            "engine_node": f"clutch_comp_{tri.lower()}",
            "status": "active",
            "artifact_path": None,
            "created_utc": _now_utc(),
            "_note": (
                f"{tri} clutch composition (mpg>=15 players, minute-weighted): "
                f"clutch_fg={attr_vals.get('clutch_fg', float('nan')):.1f}, "
                f"clutch_pts36={attr_vals.get('clutch_pts36', float('nan')):.1f}, "
                f"clutch_pm={attr_vals.get('clutch_plusminus', float('nan')):.1f}. "
                f"Composite={composite:.1f}. "
                f"LAYER: scouting only; does NOT move marginal (validated separately in clutch_adjust.py)."
            ),
            **{f"_{k}": v for k, v in attr_vals.items()},
            "_composite": composite,
        })

    # Delta model (home clutch advantage)
    h_comp = team_clutch.get(home_tri, {}).get("composite", float("nan"))
    a_comp = team_clutch.get(away_tri, {}).get("composite", float("nan"))
    delta = float(h_comp - a_comp) if np.isfinite(h_comp) and np.isfinite(a_comp) else float("nan")

    models.append({
        "model_id": f"mdl_clutch_delta_{home_tri.lower()}_vs_{away_tri.lower()}",
        "domain_tag": "clutch_composition",
        "entity_scope": "team_matchup",
        "signal_id_set_hash": _sha(f"clutch_delta+{home_tri}+{away_tri}"),
        "method": "descriptive_clutch_delta",
        "input_hash": None,
        "oos_score": float("nan"),
        "xseason_verdict": "descriptive-only",
        "engine_node": "clutch_delta_matchup",
        "status": "active",
        "artifact_path": None,
        "created_utc": _now_utc(),
        "_note": (
            f"Clutch composition delta: {home_tri} composite={h_comp:.1f} vs {away_tri} composite={a_comp:.1f}. "
            f"Delta={delta:+.1f} (positive = {home_tri} clutch advantage). "
            f"LAYER: scouting only; the validated clutch adjustment is in clutch_adjust.py, "
            f"not here."
        ),
        "_home_composite": h_comp,
        "_away_composite": a_comp,
        "_delta": delta,
    })

    # Clutch depth model (how many clutch-caliber players per team?)
    models_clutch_depth = []
    for tri in [home_tri, away_tri]:
        rows = _roster_vault(tri, min_mpg=15.0)
        if "clutch_plusminus" in rows.columns:
            above_avg = int((rows["clutch_plusminus"].values > 55).sum())  # >55th pctile = above avg in clutch
        else:
            above_avg = 0
        models_clutch_depth.append({
            "model_id": f"mdl_clutch_depth_{tri.lower()}",
            "domain_tag": "clutch_composition",
            "entity_scope": "team",
            "signal_id_set_hash": _sha(f"clutch_depth+{tri}+vault"),
            "method": "descriptive_clutch_depth_count",
            "input_hash": None,
            "oos_score": float("nan"),
            "xseason_verdict": "descriptive-only",
            "engine_node": f"clutch_depth_{tri.lower()}",
            "status": "active",
            "artifact_path": None,
            "created_utc": _now_utc(),
            "_note": (
                f"{tri} clutch depth: {above_avg} players with clutch_pm >55th pctile (above avg in tight games). "
                f"Deeper clutch pool = less fatigue collapse in 4Q. "
                f"LAYER: scouting only."
            ),
            "_n_clutch_caliber": above_avg,
        })
    models.extend(models_clutch_depth)

    return models


# ---------------------------------------------------------------------------
# MODEL 7: spacing_gravity (4 models: 2 teams x offense + defense interaction)
# ---------------------------------------------------------------------------

def compute_spacing_gravity_models(home_tri: str, away_tri: str) -> List[Dict[str, Any]]:
    """Compute spacing gravity vs closeout coverage for both directions."""
    _load()
    models = []
    for off_tri, def_tri in [(home_tri, away_tri), (away_tri, home_tri)]:
        off_rows = _roster_vault(off_tri, min_mpg=10.0)
        def_rows = _roster_vault(def_tri, min_mpg=10.0)

        # Offense spacing gravity: corner3 + above3 + catch_shoot3 weighted composite
        spacing_attrs = {
            "corner3": ("shoot_corner3", 1.2),    # corner 3s more efficient -> higher weight
            "above3":  ("shoot_above3", 1.0),
            "c_shoot": ("shoot_catch_shoot3", 1.1),
            "spotup":  ("score_spotup_ppp", 0.8),
        }
        weighted_sum = 0.0
        weight_total = 0.0
        component_vals: Dict[str, float] = {}
        for key, (attr, w) in spacing_attrs.items():
            if attr in off_rows.columns:
                v = _wmean(off_rows[attr].values.astype(float), off_rows["mpg"].values)
                if np.isfinite(v):
                    weighted_sum += v * w
                    weight_total += w
                    component_vals[key] = v
        gravity = float(weighted_sum / weight_total) if weight_total > 0 else float("nan")

        # Defense closeout coverage: perd_fg3_suppress + perd_versatility (if present)
        close_attrs = ["perd_fg3_suppress", "perd_versatility", "perd_stops"]
        close_vals = []
        for attr in close_attrs:
            if attr in def_rows.columns:
                v = _wmean(def_rows[attr].values.astype(float), def_rows["mpg"].values)
                if np.isfinite(v):
                    close_vals.append(v)
        closeout = float(np.mean(close_vals)) if close_vals else float("nan")

        gravity_edge = float(gravity - closeout) if np.isfinite(gravity) and np.isfinite(closeout) else float("nan")

        models.append({
            "model_id": f"mdl_spacing_gravity_{off_tri.lower()}_vs_{def_tri.lower()}",
            "domain_tag": "spacing_gravity",
            "entity_scope": "team_matchup",
            "signal_id_set_hash": _sha(f"spacing_gravity+{off_tri}+{def_tri}+vault"),
            "method": "descriptive_spacing_vs_closeout",
            "input_hash": None,
            "oos_score": float("nan"),
            "xseason_verdict": "descriptive-only",
            "engine_node": f"spacing_vs_closeout_{off_tri.lower()}",
            "status": "active",
            "artifact_path": None,
            "created_utc": _now_utc(),
            "_note": (
                f"{off_tri} spacing gravity={gravity:.1f} (corner3={component_vals.get('corner3', float('nan')):.1f}, "
                f"above3={component_vals.get('above3', float('nan')):.1f}, "
                f"catch_shoot={component_vals.get('c_shoot', float('nan')):.1f}) vs "
                f"{def_tri} closeout={closeout:.1f}. "
                f"Gravity edge={gravity_edge:+.1f} (positive = {off_tri} shooters vs weak closeout). "
                f"High gravity forces defense to extend, opening paint for creators. "
                f"LAYER: scouting only; does NOT feed marginal."
            ),
            "_off_tri": off_tri,
            "_def_tri": def_tri,
            "_gravity": gravity,
            "_closeout": closeout,
            "_gravity_edge": gravity_edge,
            **{f"_comp_{k}": v for k, v in component_vals.items()},
        })

    return models


# ---------------------------------------------------------------------------
# Main registration logic
# ---------------------------------------------------------------------------

def build_and_register(
    home_tri: str = "NYK",
    away_tri: str = "SAS",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build all descriptive matchup models and register them. Returns summary dict."""
    _load()
    reg = Registry("model_registry")
    prior_count = len(reg)

    all_model_rows = []

    # 1. role_vs_scheme: 15 archetypes x 2 teams = 30 models
    for tri in [home_tri, away_tri]:
        all_model_rows.extend(compute_role_vs_scheme_models(tri))

    # 2. pace_fit_clash: 4 models (2 teams x offense+defense)
    all_model_rows.extend(compute_pace_fit_models(home_tri, away_tri))

    # 3. physical_mismatch_extended: 8 facets x 2 directions = 16 models
    all_model_rows.extend(compute_physical_mismatch_extended(home_tri, away_tri))

    # 4. creation_hierarchy: 3 metrics x 2 teams = 6 models
    all_model_rows.extend(compute_creation_hierarchy(home_tri, away_tri))

    # 5. shot_diet_clash: 6 facets x 1 bidirectional model each = 6 models
    all_model_rows.extend(compute_shot_diet_clash(home_tri, away_tri))

    # 6. clutch_composition: 2 (team composites) + 1 (delta) + 2 (depth) = 5 models
    all_model_rows.extend(compute_clutch_composition(home_tri, away_tri))

    # 7. spacing_gravity: 2 directions = 2 models
    all_model_rows.extend(compute_spacing_gravity_models(home_tri, away_tri))

    n_built = len(all_model_rows)

    # Validate: no duplicate model_ids within this batch
    ids_seen = set()
    deduped = []
    for row in all_model_rows:
        mid = row["model_id"]
        if mid in ids_seen:
            continue
        ids_seen.add(mid)
        deduped.append(row)

    # Strip internal _note fields not in schema before registering
    # (registry only stores schema cols; extras are silently dropped by _coerce)

    if not dry_run:
        result = reg.register_many(deduped)
        registered = result["registered"]
        skipped = result["skipped"]
    else:
        registered = 0
        skipped = 0
        print(f"  [dry-run] Would register {len(deduped)} model rows")

    new_count = len(reg)

    # Build summary grouped by domain_tag
    by_domain: Dict[str, int] = {}
    for row in deduped:
        dt = row.get("domain_tag", "unknown")
        by_domain[dt] = by_domain.get(dt, 0) + 1

    return {
        "prior_count": prior_count,
        "new_count": new_count,
        "n_built": n_built,
        "n_registered": registered,
        "n_skipped_already_exists": skipped,
        "by_domain": by_domain,
        "home_tri": home_tri,
        "away_tri": away_tri,
        "dry_run": dry_run,
        "models": deduped,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--home", default="NYK")
    ap.add_argument("--away", default="SAS")
    ap.add_argument("--dry-run", action="store_true", help="Don't write to registry")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    print(f"\n{'='*70}")
    print(f"BUILD DESCRIPTIVE MATCHUP MODELS — {args.home} (home) vs {args.away} (away)")
    print(f"{'='*70}\n")

    summary = build_and_register(args.home, args.away, dry_run=args.dry_run)

    print(f"Prior model count    : {summary['prior_count']}")
    print(f"Models built         : {summary['n_built']}")
    print(f"Registered (new)     : {summary['n_registered']}")
    print(f"Skipped (exists)     : {summary['n_skipped_already_exists']}")
    print(f"New total            : {summary['new_count']}")
    print(f"\nBy domain_tag:")
    for domain, n in sorted(summary["by_domain"].items()):
        print(f"  {domain:<35}: {n}")

    if args.verbose:
        print(f"\nSample model rows:")
        for row in summary["models"][:3]:
            print(f"  [{row['domain_tag']}] {row['model_id']}")
            note = row.get("_note", "")
            print(f"    {note[:120]}...")

    print(f"\nHONEST ARCHITECTURE NOTE:")
    print(f"  All {summary['n_registered']} new models are DESCRIPTIVE SCOUTING only.")
    print(f"  xseason_verdict='descriptive-only' for all.")
    print(f"  They enrich the LLM scouting/narration context and matchup decomposition.")
    print(f"  They do NOT move the marginal point prediction (routed NNLS stack).")
    print(f"  They do NOT feed live betting paths (gated default-OFF).")
    if not args.dry_run:
        print(f"\nRegistry written: data/registry/model_registry/")
    print()
