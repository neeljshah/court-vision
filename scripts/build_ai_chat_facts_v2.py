"""
build_ai_chat_facts_v2.py
Flat JSON fact-list (~1,700 facts) for Claude API tool-calls.
Produces:
  data/intelligence/ai_chat_facts_v2.json
  vault/Intelligence/AI_Chat_Facts_v2.md

DO NOT modify ai_chat_facts.json (v1) — additive merge only.
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# Atlas registry
# ---------------------------------------------------------------------------
ATLAS_REGISTRY = {
    # NEW (9)
    "defensive_schemes":       ROOT / "data/intelligence/defensive_schemes.parquet",
    "team_tempo_spacing":      ROOT / "data/intelligence/team_tempo_spacing.parquet",
    "opp_defensive_intensity": ROOT / "data/intelligence/opp_defensive_intensity.parquet",
    "opp_paint_allowance":     ROOT / "data/intelligence/opp_paint_allowance.parquet",
    "player_fingerprints":     ROOT / "data/intelligence/player_fingerprints.parquet",
    "matchup_grid":            ROOT / "data/intelligence/matchup_grid.parquet",
    "rolling_trends":          ROOT / "data/intelligence/rolling_trends.parquet",
    "archetype_outlier_signals": ROOT / "data/intelligence/archetype_outlier_signals.parquet",
    "compound_candidates":     ROOT / "data/intelligence/compound_candidates.parquet",
    # REUSED (5)
    "opp_normalized_cv":       ROOT / "data/intelligence/opp_normalized_cv.parquet",
    "per_player_confidence":   ROOT / "data/intelligence/per_player_confidence.parquet",
    "current_form_profiles":   ROOT / "data/intelligence/current_form_profiles.parquet",
    "streak_signatures":       ROOT / "data/intelligence/streak_signatures.parquet",
    "pair_chemistry":          ROOT / "data/intelligence/pair_chemistry.parquet",
}

EXPECTED_MIN_ROWS = {
    "defensive_schemes": 28,
    "team_tempo_spacing": 100,
    "opp_defensive_intensity": 100,
    "opp_paint_allowance": 100,
    "player_fingerprints": 50,
    "matchup_grid": 500,
    "rolling_trends": 10,
    "archetype_outlier_signals": 50,
    "compound_candidates": 5,
    "opp_normalized_cv": 50,
    "per_player_confidence": 20,
    "current_form_profiles": 20,
    "streak_signatures": 10,
    "pair_chemistry": 10,
}

V1_PATH = ROOT / "data/intelligence/ai_chat_facts.json"
V2_JSON_PATH = ROOT / "data/intelligence/ai_chat_facts_v2.json"
V2_MD_PATH = ROOT / "vault/Intelligence/AI_Chat_Facts_v2.md"

NOW_UTC = datetime.now(timezone.utc)
VALID_UNTIL = (NOW_UTC + timedelta(days=7)).isoformat()
MATCHUP_WINDOW_DAYS = 60  # extended: season ended Apr 12, need 60d window to capture recent games
MAX_MATCHUP_FACTS = 1200
JSON_SIZE_CAP = 5_000_000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha8(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:8]


def _load_atlases() -> dict:
    frames = {}
    versions = {}
    errors = []
    for name, path in ATLAS_REGISTRY.items():
        if not path.exists():
            errors.append(f"MISSING: {name} at {path}")
            continue
        df = pd.read_parquet(path)
        min_rows = EXPECTED_MIN_ROWS.get(name, 1)
        if len(df) < min_rows:
            errors.append(f"ROW COUNT TOO LOW: {name} has {len(df)} rows (expected >={min_rows})")
        frames[name] = df
        versions[name] = {
            "mtime": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
            "rows": len(df),
            "sha8": _sha8(path),
        }
    if errors:
        for e in errors:
            print(f"[WARN] {e}", file=sys.stderr)
    return frames, versions


def _rank_and_compare(series: pd.Series, ascending=False):
    """
    Returns dict keyed by series.index values:
      {idx: (value, rank, rank_of, percentile, comparable_top3)}
    rank=1 means best (highest if not ascending).
    comparable_top3: 3 items with closest value excluding self.
    """
    valid = series.dropna()
    n = len(valid)
    if n == 0:
        return {}
    ranked = valid.rank(ascending=ascending, method="min")
    result = {}
    for idx in valid.index:
        val = valid[idx]
        r = int(ranked[idx])
        pct = round(1.0 - (r - 1) / n, 3) if not ascending else round((r - 1) / n, 3)
        # comparable: closest other values
        dists = (valid.drop(index=idx) - val).abs().nsmallest(3)
        comparable = [str(i) for i in dists.index]
        result[idx] = {
            "value": round(float(val), 4),
            "rank": r,
            "rank_of": n,
            "percentile": pct,
            "comparable": comparable,
        }
    return result


def _conf(quality_z=None, n=None):
    if quality_z is not None:
        if abs(quality_z) < 0.5:
            return "low"
        if abs(quality_z) < 1.0:
            return "med"
        return "high"
    if n is not None:
        if n >= 30:
            return "high"
        if n >= 10:
            return "med"
        return "low"
    return "med"


# ---------------------------------------------------------------------------
# Team facts
# ---------------------------------------------------------------------------

def build_team_facts(frames: dict) -> list:
    facts = []

    ds = frames.get("defensive_schemes")
    ts = frames.get("team_tempo_spacing")
    odi = frames.get("opp_defensive_intensity")
    opa = frames.get("opp_paint_allowance")

    # Build latest-per-team for time-series atlases
    ts_latest = ts.sort_values("game_date").groupby("team_abbr").last().reset_index() if ts is not None else None
    odi_latest = odi.sort_values("game_date").groupby("team_id").last().reset_index() if odi is not None else None
    opa_latest = opa.sort_values("game_date").groupby("team_id").last().reset_index() if opa is not None else None

    # ---- 1. defensive_intensity (from opp_defensive_intensity) ----
    if odi_latest is not None and "opp_contested_shot_rate_imposed_z" in odi_latest.columns:
        col = "opp_contested_shot_rate_imposed_z"
        ranked = _rank_and_compare(odi_latest.set_index("team_id")[col], ascending=False)
        for team, meta in ranked.items():
            facts.append({
                "id": f"team.{team}.defensive_intensity",
                "category": "team",
                "subject": str(team),
                "key": "defensive_intensity",
                "value": meta["value"],
                "rank": meta["rank"],
                "rank_of": meta["rank_of"],
                "percentile": meta["percentile"],
                "comparable": meta["comparable"],
                "text": (
                    f"{team} defensive intensity (contested shot rate imposed on opponents): "
                    f"z={meta['value']:+.2f}, ranked {meta['rank']}/{meta['rank_of']} "
                    f"(top {int((1-meta['percentile'])*100+0.5)}% most intense)."
                ),
                "source_atlas": "opp_defensive_intensity",
                "source_row_keys": {"team_id": team},
                "confidence": _conf(quality_z=meta["value"]),
                "valid_until": VALID_UNTIL,
            })

    # ---- 2. paint_allowance ----
    if opa_latest is not None and "opp_paint_pct_allowed_z" in opa_latest.columns:
        col = "opp_paint_pct_allowed_z"
        ranked = _rank_and_compare(opa_latest.set_index("team_id")[col], ascending=False)
        for team, meta in ranked.items():
            facts.append({
                "id": f"team.{team}.paint_allowance",
                "category": "team",
                "subject": str(team),
                "key": "paint_allowance",
                "value": meta["value"],
                "rank": meta["rank"],
                "rank_of": meta["rank_of"],
                "percentile": meta["percentile"],
                "comparable": meta["comparable"],
                "text": (
                    f"{team} paint allowance (opponent paint shot pct imposed): "
                    f"z={meta['value']:+.2f}, ranked {meta['rank']}/{meta['rank_of']}."
                ),
                "source_atlas": "opp_paint_allowance",
                "source_row_keys": {"team_id": team},
                "confidence": _conf(quality_z=meta["value"]),
                "valid_until": VALID_UNTIL,
            })

    # ---- 3. tempo ----
    if ts_latest is not None and "team_tempo_z" in ts_latest.columns:
        col = "team_tempo_z"
        ranked = _rank_and_compare(ts_latest.set_index("team_abbr")[col], ascending=False)
        for team, meta in ranked.items():
            direction = "fast" if meta["value"] > 0 else "slow"
            facts.append({
                "id": f"team.{team}.tempo",
                "category": "team",
                "subject": str(team),
                "key": "tempo",
                "value": meta["value"],
                "rank": meta["rank"],
                "rank_of": meta["rank_of"],
                "percentile": meta["percentile"],
                "comparable": meta["comparable"],
                "text": (
                    f"{team} plays at a {direction} pace (tempo z={meta['value']:+.2f}), "
                    f"ranked {meta['rank']}/{meta['rank_of']} fastest."
                ),
                "source_atlas": "team_tempo_spacing",
                "source_row_keys": {"team_abbr": team},
                "confidence": "med",
                "valid_until": VALID_UNTIL,
            })

    # ---- 4. spacing ----
    if ts_latest is not None and "team_spacing_z" in ts_latest.columns:
        col = "team_spacing_z"
        ranked = _rank_and_compare(ts_latest.set_index("team_abbr")[col], ascending=False)
        for team, meta in ranked.items():
            direction = "wide" if meta["value"] > 0 else "condensed"
            facts.append({
                "id": f"team.{team}.spacing",
                "category": "team",
                "subject": str(team),
                "key": "spacing",
                "value": meta["value"],
                "rank": meta["rank"],
                "rank_of": meta["rank_of"],
                "percentile": meta["percentile"],
                "comparable": meta["comparable"],
                "text": (
                    f"{team} offense is {direction} (spacing z={meta['value']:+.2f}), "
                    f"ranked {meta['rank']}/{meta['rank_of']} widest."
                ),
                "source_atlas": "team_tempo_spacing",
                "source_row_keys": {"team_abbr": team},
                "confidence": "med",
                "valid_until": VALID_UNTIL,
            })

    # ---- 5. tempo_spacing_composite ----
    if ts_latest is not None and "team_tempo_spacing_composite_z" in ts_latest.columns:
        col = "team_tempo_spacing_composite_z"
        ranked = _rank_and_compare(ts_latest.set_index("team_abbr")[col], ascending=False)
        for team, meta in ranked.items():
            facts.append({
                "id": f"team.{team}.tempo_spacing_composite",
                "category": "team",
                "subject": str(team),
                "key": "tempo_spacing_composite",
                "value": meta["value"],
                "rank": meta["rank"],
                "rank_of": meta["rank_of"],
                "percentile": meta["percentile"],
                "comparable": meta["comparable"],
                "text": (
                    f"{team} tempo+spacing composite z={meta['value']:+.2f}, "
                    f"ranked {meta['rank']}/{meta['rank_of']} (higher = faster + wider)."
                ),
                "source_atlas": "team_tempo_spacing",
                "source_row_keys": {"team_abbr": team},
                "confidence": "med",
                "valid_until": VALID_UNTIL,
            })

    # ---- 6. scheme_tag + imposed_top_deviation ----
    if ds is not None:
        for _, row in ds.iterrows():
            team = row["team"]
            tag = str(row.get("dominant_tag", "UNKNOWN"))
            conf = str(row.get("confidence", "low"))
            n_opp = int(row.get("n_opposing_player_games", 0))
            # scheme_tag fact
            facts.append({
                "id": f"team.{team}.scheme_tag",
                "category": "team",
                "subject": str(team),
                "key": "scheme_tag",
                "value": tag,
                "rank": None,
                "rank_of": 30,
                "percentile": None,
                "comparable": [],
                "text": (
                    f"{team} primary defensive scheme: {tag} "
                    f"(confidence={conf}, n={n_opp} opposing player-games observed)."
                ),
                "source_atlas": "defensive_schemes",
                "source_row_keys": {"team": team},
                "confidence": conf if conf in ("high", "med", "low") else "med",
                "valid_until": VALID_UNTIL,
            })
            # imposed_top_deviation — largest absolute z deviation
            dev_cols = ["drop_score","paint_protection_score","perimeter_denial_score",
                        "pace_control_score","iso_force_score","closeout_score"]
            best_col = None
            best_val = 0.0
            for dc in dev_cols:
                if dc in row and pd.notna(row[dc]):
                    if abs(row[dc]) > abs(best_val):
                        best_val = float(row[dc])
                        best_col = dc
            if best_col:
                direction = "above" if best_val > 0 else "below"
                facts.append({
                    "id": f"team.{team}.imposed_top_deviation",
                    "category": "team",
                    "subject": str(team),
                    "key": "imposed_top_deviation",
                    "value": round(best_val, 4),
                    "rank": None,
                    "rank_of": None,
                    "percentile": None,
                    "comparable": [],
                    "text": (
                        f"{team}'s largest defensive dimension deviation is {best_col.replace('_',' ')} "
                        f"({best_val:+.2f}z, {direction} league average)."
                    ),
                    "source_atlas": "defensive_schemes",
                    "source_row_keys": {"team": team},
                    "confidence": conf if conf in ("high", "med", "low") else "med",
                    "valid_until": VALID_UNTIL,
                })

    return facts


# ---------------------------------------------------------------------------
# Player facts
# ---------------------------------------------------------------------------
_FINGERPRINT_FEATURES = [
    "paint_dwell_pct", "shot_zone_paint_pct", "shot_zone_mid_range_pct",
    "shot_zone_3pt_pct", "avg_shot_distance", "touches_per_game",
    "shots_per_possession", "possession_duration_avg", "second_chance_rate",
    "potential_assists", "preshot_velocity_peak", "defender_approach_speed",
    "play_type_transition_pct", "play_type_isolation_pct", "play_type_post_pct",
    "catch_shoot_pct", "avg_dribble_count", "contested_shot_rate",
    "avg_defender_distance",
]

_FEATURE_LABELS = {
    "paint_dwell_pct": "paint dwell pct",
    "shot_zone_paint_pct": "paint shot zone pct",
    "shot_zone_mid_range_pct": "mid-range zone pct",
    "shot_zone_3pt_pct": "3pt zone pct",
    "avg_shot_distance": "avg shot distance",
    "touches_per_game": "touches per game",
    "shots_per_possession": "shots per possession",
    "possession_duration_avg": "avg possession duration",
    "second_chance_rate": "second chance rate",
    "potential_assists": "potential assists",
    "preshot_velocity_peak": "pre-shot velocity",
    "defender_approach_speed": "defender approach speed",
    "play_type_transition_pct": "transition play pct",
    "play_type_isolation_pct": "isolation play pct",
    "play_type_post_pct": "post play pct",
    "catch_shoot_pct": "catch-and-shoot pct",
    "avg_dribble_count": "avg dribble count",
    "contested_shot_rate": "contested shot rate",
    "avg_defender_distance": "avg defender distance",
}

# higher = more active / more scoring oriented for these
_ASCENDING_LOW_IS_BAD = {
    "avg_defender_distance": True,   # higher = more open
    "avg_shot_distance": False,
}


def build_player_facts(frames: dict) -> list:
    facts = []
    fp = frames.get("player_fingerprints")
    if fp is None:
        return facts

    elig = fp[fp["n_cv_games"] >= 3].copy()
    # compute z-scores across eligible players
    for col in _FINGERPRINT_FEATURES:
        if col not in elig.columns:
            continue
        mu = elig[col].mean()
        sigma = elig[col].std()
        elig[col + "_z"] = (elig[col] - mu) / sigma if sigma > 0 else 0.0

    zcols = [c + "_z" for c in _FINGERPRINT_FEATURES if c + "_z" in elig.columns]

    # outlier signals (latest per player for outlier_z)
    aos = frames.get("archetype_outlier_signals")
    outlier_map = {}
    if aos is not None and len(aos) > 0:
        latest = aos.dropna(subset=["outlier_z"]).sort_values("game_date").groupby("player_id").last()
        for pid, row in latest.iterrows():
            outlier_map[str(int(pid))] = {
                "outlier_z": float(row["outlier_z"]),
                "flag": bool(row["flag_strong_outlier"]),
                "game_date": str(row["game_date"]),
            }

    for pid_val, row in elig.iterrows():
        pid = str(int(pid_val))
        player_name = str(row.get("player_name", pid))
        archetype = str(row.get("archetype_name", ""))
        n_games = int(row.get("n_cv_games", 0))
        conf = _conf(n=n_games)

        # collect z-scores that pass gate
        z_items = []
        for col in _FINGERPRINT_FEATURES:
            zcol = col + "_z"
            if zcol not in row.index:
                continue
            z = row[zcol]
            if pd.isna(z):
                continue
            if abs(z) >= 0.5:
                z_items.append((col, float(z)))

        # also include outlier flag
        out_info = outlier_map.get(pid)

        # if nothing to say and no outlier flag, skip
        if not z_items and (out_info is None or not out_info["flag"]):
            continue

        # sort by |z| desc, emit up to 4 facts per player
        z_items.sort(key=lambda x: abs(x[1]), reverse=True)
        emitted = 0
        for col, z in z_items[:4]:
            label = _FEATURE_LABELS.get(col, col)
            direction = "above" if z > 0 else "below"
            ascending_good = _ASCENDING_LOW_IS_BAD.get(col, False)
            if ascending_good:
                interp = "more open" if z > 0 else "more contested"
            else:
                interp = "higher than" if z > 0 else "lower than"
            facts.append({
                "id": f"player.{pid}.{col}",
                "category": "player",
                "subject": pid,
                "key": col,
                "value": round(row[col], 4) if col in row.index and pd.notna(row[col]) else None,
                "rank": None,
                "rank_of": len(elig),
                "percentile": None,
                "comparable": [],
                "text": (
                    f"{player_name} ({archetype}): {label} is {interp} league avg "
                    f"(z={z:+.2f}, n={n_games} CV games)."
                ),
                "source_atlas": "player_fingerprints",
                "source_row_keys": {"player_id": pid},
                "confidence": conf,
                "valid_until": VALID_UNTIL,
            })
            emitted += 1

        # outlier fact
        if out_info and out_info["flag"] and emitted < 4:
            oz = out_info["outlier_z"]
            facts.append({
                "id": f"player.{pid}.archetype_outlier",
                "category": "player",
                "subject": pid,
                "key": "archetype_outlier",
                "value": round(oz, 4),
                "rank": None,
                "rank_of": None,
                "percentile": None,
                "comparable": [],
                "text": (
                    f"{player_name} is a strong archetype outlier vs historical profile "
                    f"(outlier_z={oz:+.2f}, as of {out_info['game_date']})."
                ),
                "source_atlas": "archetype_outlier_signals",
                "source_row_keys": {"player_id": pid},
                "confidence": "high",
                "valid_until": VALID_UNTIL,
            })

    return facts


# ---------------------------------------------------------------------------
# Matchup facts
# ---------------------------------------------------------------------------

def build_matchup_facts(frames: dict) -> list:
    facts = []
    mg = frames.get("matchup_grid")
    if mg is None:
        return facts

    today_str = NOW_UTC.strftime("%Y-%m-%d")
    window_start = (NOW_UTC - timedelta(days=MATCHUP_WINDOW_DAYS)).strftime("%Y-%m-%d")
    future_end = (NOW_UTC + timedelta(days=7)).strftime("%Y-%m-%d")

    # filter: recent past + upcoming 7d
    recent = mg[(mg["game_date"] >= window_start) & (mg["game_date"] <= today_str)].copy()
    upcoming = mg[(mg["game_date"] > today_str) & (mg["game_date"] <= future_end)].copy()
    combined = pd.concat([recent, upcoming]).drop_duplicates()

    # filter non-trivial composites
    combined = combined[combined["mx_offense_vs_defense_composite"].abs() > 0.05].copy()
    # sort by |composite| desc
    combined["_abs_composite"] = combined["mx_offense_vs_defense_composite"].abs()
    combined = combined.sort_values("_abs_composite", ascending=False).head(MAX_MATCHUP_FACTS)

    for _, row in combined.iterrows():
        team = str(row["team_id"])
        opp = str(row["opp_team_id"])
        gdate = str(row["game_date"])
        comp = float(row["mx_offense_vs_defense_composite"])
        tempo_z = float(row.get("mx_tempo_vs_opp_pace", 0.0))
        is_home = bool(row.get("is_home", 0))
        density = str(row.get("data_density", "unknown"))

        direction = "favors offense" if comp > 0 else "favors defense"
        loc = "home" if is_home else "away"
        conf = "high" if density == "full" else ("med" if density == "partial" else "low")

        facts.append({
            "id": f"matchup.{gdate}.{team}.vs.{opp}",
            "category": "matchup",
            "subject": f"{team}_vs_{opp}",
            "key": "offense_vs_defense_composite",
            "value": round(comp, 4),
            "rank": None,
            "rank_of": None,
            "percentile": None,
            "comparable": [],
            "text": (
                f"{team} ({loc}) vs {opp} on {gdate}: matchup composite={comp:+.2f} ({direction}), "
                f"tempo_vs_pace={tempo_z:+.2f}, data_density={density}."
            ),
            "source_atlas": "matchup_grid",
            "source_row_keys": {"game_id": str(row.get("game_id", "")), "team_id": team},
            "confidence": conf,
            "valid_until": VALID_UNTIL,
        })

    return facts


# ---------------------------------------------------------------------------
# Trend facts
# ---------------------------------------------------------------------------

def build_trend_facts(frames: dict) -> list:
    facts = []
    rt = frames.get("rolling_trends")
    if rt is None:
        return facts

    # Cohort buckets
    cohort_map = {
        "HOT_BREAKOUT": [],
        "HOT": [],
        "COLD_DECLINE": [],
        "COLD": [],
        "STEADY": [],
    }
    for _, row in rt.iterrows():
        tag = str(row.get("trend_tag", "STEADY")).upper()
        name = str(row.get("player_name", ""))
        z = float(row.get("max_abs_z", 0.0))
        cohort_map.get(tag, cohort_map["STEADY"]).append((name, z))

    for bucket, players in cohort_map.items():
        if not players:
            continue
        players_sorted = sorted(players, key=lambda x: -x[1])
        names_str = ", ".join(p[0] for p in players_sorted[:8])
        count = len(players)
        facts.append({
            "id": f"trend.cohort.{bucket}",
            "category": "trend",
            "subject": bucket,
            "key": "trend_cohort",
            "value": count,
            "rank": None,
            "rank_of": len(rt),
            "percentile": None,
            "comparable": [],
            "text": (
                f"Trend cohort {bucket}: {count} player(s). "
                f"Top players: {names_str}."
            ),
            "source_atlas": "rolling_trends",
            "source_row_keys": {"trend_tag": bucket},
            "confidence": "med",
            "valid_until": VALID_UNTIL,
        })

    # Per-player trend facts (max_abs_z >= 0.8)
    trend_cols = [
        ("cvb_paint_time_pct_z", "paint time pct"),
        ("cvb_near_basket_pct_z", "near-basket pct"),
        ("cvb_avg_dist_to_basket_z", "dist to basket"),
        ("cvb_fatigue_score_z", "fatigue score"),
        ("cvb_avg_velocity_z", "avg velocity"),
        ("cvb_avg_defender_dist_z", "defender distance"),
        ("minutes_proxy_z", "minutes proxy"),
    ]

    _trend_seen_ids = set()
    _unknown_counter = 0
    for _, row in rt.iterrows():
        name = str(row.get("player_name", ""))
        tag = str(row.get("trend_tag", "STEADY"))
        if float(row.get("max_abs_z", 0.0)) < 0.8:
            continue
        pid_raw = row.get("player_id")
        if pd.notna(pid_raw):
            pid = str(int(pid_raw))
        else:
            _unknown_counter += 1
            pid = f"unknown_{_unknown_counter}"
        for col, label in trend_cols:
            if col not in row.index:
                continue
            z = row[col]
            if pd.isna(z) or abs(z) < 0.8:
                continue
            direction = "increasing" if z > 0 else "decreasing"
            fid = f"trend.player.{pid}.{col}"
            if fid in _trend_seen_ids:
                continue
            _trend_seen_ids.add(fid)
            facts.append({
                "id": fid,
                "category": "trend",
                "subject": pid,
                "key": col,
                "value": round(float(z), 4),
                "rank": None,
                "rank_of": None,
                "percentile": None,
                "comparable": [],
                "text": (
                    f"{name} trend ({tag}): {label} is {direction} "
                    f"(z={z:+.2f} recent vs prior)."
                ),
                "source_atlas": "rolling_trends",
                "source_row_keys": {"player_id": pid},
                "confidence": "med",
                "valid_until": VALID_UNTIL,
            })

    return facts


# ---------------------------------------------------------------------------
# Edge facts
# ---------------------------------------------------------------------------

def build_edge_facts(frames: dict) -> list:
    facts = []

    # From compound_candidates (WF-equivalent: win_rate >= 0.55, n >= 15)
    cc = frames.get("compound_candidates")
    if cc is not None:
        for _, row in cc.iterrows():
            wr = row.get("win_rate")
            n = int(row.get("n_games_matched", 0))
            if pd.isna(wr) or float(wr) < 0.55 or n < 15:
                continue
            name = str(row["candidate_name"])
            shift = float(row.get("mean_stat_shift_vs_base", 0.0))
            target = str(row.get("target_stat", ""))
            direction = str(row.get("direction", ""))
            z_stat = float(row["z_stat"]) if "z_stat" in row.index and pd.notna(row["z_stat"]) else 0.0
            conf = "high" if float(wr) >= 0.65 and n >= 30 else "med"
            facts.append({
                "id": f"edge.compound.{name.lower()}",
                "category": "edge",
                "subject": name,
                "key": "compound_signal",
                "value": round(float(wr), 4),
                "rank": None,
                "rank_of": None,
                "percentile": None,
                "comparable": [],
                "text": (
                    f"Compound signal {name}: {direction} {target} — "
                    f"win_rate={wr:.1%}, n={n}, mean_shift={shift:+.2f} vs base, z={z_stat:+.2f}."
                ),
                "source_atlas": "compound_candidates",
                "source_row_keys": {"candidate_name": name},
                "confidence": conf,
                "valid_until": VALID_UNTIL,
            })

    # From v9_unified_results verdicts
    v9_path = ROOT / "data/intelligence/v9_unified_results.json"
    if v9_path.exists():
        with open(v9_path, encoding="utf-8") as f:
            v9 = json.load(f)
        verdicts = v9.get("verdicts", {})
        for sig_key, verd in verdicts.items():
            rec = str(verd.get("deployment_recommendation", ""))
            if "SHIP" not in rec.upper():
                continue
            roi = float(verd.get("roi_flat_pct", 0.0))
            n = int(verd.get("n_real", 0))
            cons = str(verd.get("season_consistency", ""))
            facts.append({
                "id": f"edge.signal.{sig_key.lower()}",
                "category": "edge",
                "subject": sig_key,
                "key": "v9_shipped_signal",
                "value": round(roi, 4),
                "rank": None,
                "rank_of": None,
                "percentile": None,
                "comparable": [],
                "text": (
                    f"Shipped signal {sig_key}: roi_flat={roi:+.1f}%, n={n}, "
                    f"consistency={cons}, recommendation={rec}."
                ),
                "source_atlas": "v9_unified_results",
                "source_row_keys": {"signal": sig_key},
                "confidence": "med",
                "valid_until": VALID_UNTIL,
            })

    return facts


# ---------------------------------------------------------------------------
# Merge with v1
# ---------------------------------------------------------------------------

def _merge_with_v1(facts_v2: list) -> list:
    if not V1_PATH.exists():
        return facts_v2
    with open(V1_PATH, encoding="utf-8") as f:
        v1 = json.load(f)

    existing_ids = {f["id"] for f in facts_v2}
    v1_facts = []

    def _flatten(obj, category, subject):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (int, float, str, bool)) and v is not None:
                    fid = f"v1.{category}.{subject}.{k}"
                    if fid in existing_ids:
                        continue
                    v1_facts.append({
                        "id": fid,
                        "category": category,
                        "subject": str(subject),
                        "key": str(k),
                        "value": v,
                        "rank": None,
                        "rank_of": None,
                        "percentile": None,
                        "comparable": [],
                        "text": f"[v1 legacy] {subject} {k}: {v}",
                        "source_atlas": "v1_legacy",
                        "source_row_keys": {},
                        "confidence": "low",
                        "valid_until": VALID_UNTIL,
                    })

    # v1.players
    players_section = v1.get("players", {})
    if isinstance(players_section, dict):
        for pname, pdata in players_section.items():
            pid = str(pdata.get("player_id", pname))
            _flatten(pdata.get("fingerprint", {}), "player", pid)
    elif isinstance(players_section, list):
        for p in players_section:
            pid = str(p.get("player_id", ""))
            _flatten(p, "player", pid)

    # v1.teams
    teams_section = v1.get("teams", {})
    if isinstance(teams_section, dict):
        for tname, tdata in teams_section.items():
            _flatten(tdata, "team", tname)
    elif isinstance(teams_section, list):
        for t in teams_section:
            tname = str(t.get("team", t.get("team_id", "")))
            _flatten(t, "team", tname)

    return facts_v2 + v1_facts


# ---------------------------------------------------------------------------
# Natural language text override (ensure all facts have non-empty text)
# ---------------------------------------------------------------------------

def _ensure_text(facts: list) -> list:
    for f in facts:
        if not f.get("text"):
            f["text"] = (
                f"{f['subject']} {f['key']}: {f['value']} "
                f"(source={f['source_atlas']})."
            )
    return facts


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = [
    "id", "category", "subject", "key", "value",
    "rank", "rank_of", "percentile", "comparable",
    "text", "source_atlas", "source_row_keys", "confidence", "valid_until",
]
VALID_CATEGORIES = {"team", "player", "matchup", "trend", "edge"}
VALID_CONFIDENCES = {"high", "med", "low"}


def _validate(facts: list) -> bool:
    ok = True
    seen_ids = set()
    for i, f in enumerate(facts):
        for field in REQUIRED_FIELDS:
            if field not in f:
                print(f"[VALIDATION] Fact #{i} missing field '{field}': {f.get('id','?')}", file=sys.stderr)
                ok = False
        if f.get("category") not in VALID_CATEGORIES:
            print(f"[VALIDATION] Fact {f.get('id')} bad category={f.get('category')}", file=sys.stderr)
            ok = False
        if f.get("confidence") not in VALID_CONFIDENCES:
            print(f"[VALIDATION] Fact {f.get('id')} bad confidence={f.get('confidence')}", file=sys.stderr)
            ok = False
        fid = f.get("id")
        if fid in seen_ids:
            print(f"[VALIDATION] Duplicate id: {fid}", file=sys.stderr)
            ok = False
        seen_ids.add(fid)
    return ok


def _coverage_gates(facts: list) -> bool:
    team_subjects = {f["subject"] for f in facts if f["category"] == "team"}
    if len(team_subjects) < 30:
        print(f"[COVERAGE GATE FAIL] Only {len(team_subjects)} team subjects (need 30)", file=sys.stderr)
        return False
    return True


def _sanity_sample(facts: list):
    import random
    random.seed(42)
    for cat in ["team", "player", "matchup", "trend", "edge"]:
        pool = [f for f in facts if f["category"] == cat]
        sample = random.sample(pool, min(5, len(pool)))
        print(f"\n--- {cat} sample ({len(pool)} total) ---")
        for f in sample:
            print(f"  [{f['id']}] {f['text'][:120]}")


# ---------------------------------------------------------------------------
# Write markdown view
# ---------------------------------------------------------------------------

def _write_markdown(facts: list, versions: dict, counts: dict):
    V2_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# AI Chat Facts v2",
        f"",
        f"Generated: {NOW_UTC.isoformat()}",
        f"Valid until: {VALID_UNTIL}",
        f"Total facts: {len(facts)}",
        f"",
        "## Counts by category",
        "",
    ]
    for cat, n in sorted(counts.items()):
        lines.append(f"- **{cat}**: {n}")
    lines += ["", "## Atlas versions", ""]
    for name, info in sorted(versions.items()):
        lines.append(f"- **{name}**: {info['rows']} rows, sha8={info['sha8']}, mtime={info['mtime']}")
    lines += ["", "## Sample facts (5 per category)", ""]
    import random
    random.seed(42)
    for cat in ["team", "player", "matchup", "trend", "edge"]:
        pool = [f for f in facts if f["category"] == cat]
        sample = random.sample(pool, min(5, len(pool)))
        lines.append(f"### {cat}")
        for f in sample:
            lines.append(f"- `{f['id']}`: {f['text']}")
        lines.append("")
    lines += [
        "## Notes",
        "",
        "- `comparable` is univariate (per key); single-axis similarity by design.",
        "- `valid_until` is wall-clock (+7d from generation). Re-run after any atlas refresh.",
        "- Players with <3 CV games get 0 facts; handle 'not enough coverage' in AI Chat.",
        "- v1_legacy facts have confidence=low and source_atlas=v1_legacy.",
    ]
    with open(V2_MD_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"[build_ai_chat_facts_v2] Starting — {NOW_UTC.isoformat()}")

    print("Loading atlases...")
    frames, versions = _load_atlases()
    print(f"  Loaded {len(frames)}/{len(ATLAS_REGISTRY)} atlases")

    print("Building team facts...")
    team_facts = build_team_facts(frames)
    print(f"  {len(team_facts)} team facts")

    print("Building player facts...")
    player_facts = build_player_facts(frames)
    print(f"  {len(player_facts)} player facts")

    print("Building matchup facts...")
    matchup_facts = build_matchup_facts(frames)
    print(f"  {len(matchup_facts)} matchup facts")

    print("Building trend facts...")
    trend_facts = build_trend_facts(frames)
    print(f"  {len(trend_facts)} trend facts")

    print("Building edge facts...")
    edge_facts = build_edge_facts(frames)
    print(f"  {len(edge_facts)} edge facts")

    all_facts = team_facts + player_facts + matchup_facts + trend_facts + edge_facts

    print("Merging with v1 legacy...")
    all_facts = _merge_with_v1(all_facts)
    print(f"  Total after merge: {len(all_facts)} facts")

    all_facts = _ensure_text(all_facts)

    print("Validating...")
    schema_ok = _validate(all_facts)
    coverage_ok = _coverage_gates(all_facts)
    if not (schema_ok and coverage_ok):
        print("[ERROR] Validation failed — see stderr", file=sys.stderr)
        sys.exit(1)

    counts = {}
    for f in all_facts:
        counts[f["category"]] = counts.get(f["category"], 0) + 1

    _sanity_sample(all_facts)

    payload = {
        "version": 2,
        "generated_at": NOW_UTC.isoformat(),
        "atlas_versions": versions,
        "valid_until": VALID_UNTIL,
        "counts_by_category": counts,
        "facts": all_facts,
    }

    json_str = json.dumps(payload, ensure_ascii=False, indent=2)
    json_bytes = json_str.encode("utf-8")
    if len(json_bytes) > JSON_SIZE_CAP:
        print(f"[ERROR] JSON size {len(json_bytes):,} bytes exceeds {JSON_SIZE_CAP:,} cap", file=sys.stderr)
        sys.exit(1)

    V2_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(V2_JSON_PATH, "w", encoding="utf-8") as f:
        f.write(json_str)

    _write_markdown(all_facts, versions, counts)

    print(f"\n[DONE]")
    print(f"  Total facts: {len(all_facts)}")
    print(f"  By category: {counts}")
    print(f"  JSON size:   {len(json_bytes):,} bytes ({len(json_bytes)/1024/1024:.2f} MB)")
    print(f"  JSON path:   {V2_JSON_PATH}")
    print(f"  MD path:     {V2_MD_PATH}")
    print(f"  Atlases:     {len(versions)} pinned")


if __name__ == "__main__":
    main()
