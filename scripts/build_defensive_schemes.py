"""
INT-12: Defensive Scheme Intelligence
Build per-team defensive scheme profiles from CV-derived opponent-imposed behavioral data.

Inputs:
  - data/intelligence/opponent_imposed_profiles.json  (INT-3)
  - data/intelligence/matchup_deviations.parquet      (INT-3)

Outputs:
  - data/intelligence/defensive_schemes.parquet  (consumed by team-card builder)
  - data/intelligence/scheme_indicators.json
  - vault/Intelligence/Defensive_Schemes.md       (atlas hub, links Teams/<TRI>)

Per-team defensive scheme detail is folded into each Teams/<TRI>.md note's
SCHEME-AUTO block by render_schemes_to_vault.py — no standalone Schemes/ files.
"""

import json
import os
import numpy as np
import pandas as pd
from datetime import date
from pathlib import Path

# ─── paths ────────────────────────────────────────────────────────────────────
# 2026-05-29 portability fix: use script-relative ROOT so this runs on RunPod too.
ROOT = Path(__file__).resolve().parent.parent
IMPOSED_JSON = ROOT / "data/intelligence/opponent_imposed_profiles.json"
MATCHUP_PARQUET = ROOT / "data/intelligence/matchup_deviations.parquet"
TEAM_ADV_STATS = ROOT / "data/team_advanced_stats.parquet"   # Bug-13: defrtg source
OUT_PARQUET = ROOT / "data/intelligence/defensive_schemes.parquet"
OUT_INDICATORS = ROOT / "data/intelligence/scheme_indicators.json"
ATLAS_MD = ROOT / "vault/Intelligence/Defensive_Schemes.md"
TODAY = date.today().isoformat()

# ─── Bug-13: team-quality residualization constants ───────────────────────────
# Weight applied to quality_z when subtracting from all scheme axes.
# Tuned so that teams +2σ worse than league avg (e.g. UTA) lose ~0.19 from
# every axis score, removing the "globally weak defense" signal.
_QUALITY_WEIGHT = 0.08
# PERIMETER DENIAL extra gate: contested_shot_rate imposed delta must be ≥ this.
# Ensures the team is actively contesting shots (scheme intent), not just
# allowing fewer 3-pt attempts due to pace/opponent self-selection.
_CONTESTED_THRESHOLD = -0.05
# Threshold for GENERIC_WEAK_DEFENSE label: quality_z > this value.
_WEAK_DEFENSE_Z_THRESHOLD = 1.5

# ─── known ground-truth for validation ────────────────────────────────────────
KNOWN_SCHEMES = {
    "BOS": {
        "desc": "Switch-heavy (Mazzulla system — switch everything, load up on contested mid-range)",
        "expected": {"drop_score": "negative", "perimeter_denial_score": "positive"},
    },
    "DEN": {
        "desc": "Drop coverage (Jokic stays near paint, allows long 2s)",
        "expected": {"drop_score": "positive"},
    },
    "MIN": {
        "desc": "Paint-protective (Gobert rim deterrent forces perimeter shots)",
        "expected": {"paint_protection_score": "positive"},
    },
    "MIA": {
        "desc": "Physical paint protection (Adebayo + zone tendencies)",
        "expected": {"paint_protection_score": "positive"},
    },
    "MEM": {
        "desc": "Aggressive switch + pressure (JJJ + Marcus Smart era intensity)",
        "expected": {"closeout_score": "positive", "perimeter_denial_score": "positive"},
    },
    "LAL": {
        "desc": "Mixed/inconsistent (roster flux, AD anchor but variable scheme)",
        "expected": {},  # No clear expected — mixed
    },
}

# ─── load data ────────────────────────────────────────────────────────────────
print("[INT-12] Loading imposed profiles ...")
with open(IMPOSED_JSON) as f:
    imposed = json.load(f)

print("[INT-12] Loading matchup deviations ...")
deviations = pd.read_parquet(MATCHUP_PARQUET)

# ─── Bug-13: build per-team quality_z from def_rtg ────────────────────────────
print("[INT-12] Building team defensive quality z-scores (Bug-13 residualization) ...")
_team_quality_z: dict[str, float] = {}
_defrtg_source = "team_advanced_stats.parquet (2024+ seasons)"
if TEAM_ADV_STATS.exists():
    _tas = pd.read_parquet(TEAM_ADV_STATS)
    _tas["season_year"] = _tas["game_date"].str[:4].astype(int)
    _recent = _tas[_tas["season_year"] >= 2024]
    _team_defrtg = _recent.groupby("team_tricode")["def_rtg"].mean()
    _league_mean = float(_team_defrtg.mean())
    _league_std = float(_team_defrtg.std())
    for _team, _drtg in _team_defrtg.items():
        _team_quality_z[str(_team)] = (_drtg - _league_mean) / _league_std
    print(f"  [Bug-13] Loaded def_rtg for {len(_team_quality_z)} teams "
          f"(league mean={_league_mean:.1f}, std={_league_std:.2f})")
    print(f"  [Bug-13] Quality z-scores — POR: {_team_quality_z.get('POR', 0):+.3f}, "
          f"UTA: {_team_quality_z.get('UTA', 0):+.3f} (positive = worse defense)")
else:
    print("  [Bug-13] WARNING: team_advanced_stats.parquet not found; quality residualization skipped")
    _defrtg_source = "UNAVAILABLE — residualization skipped"


# ─── STEP 1: Compute 6 scheme axis scores ─────────────────────────────────────
def get_feat(profile: dict, key: str, default: float = 0.0) -> float:
    return profile.get("imposed_deviations", {}).get(key, default)


def compute_axes(team: str, profile: dict) -> dict:
    d = profile.get("imposed_deviations", {})

    def f(key):
        return d.get(key, 0.0)

    # --- Axis 1: Drop vs Switch coverage ---
    # Drop: bigs stay near paint → opp has HIGH paint_dwell, LOW contested_shot_rate
    # Switch: → opp has LOW paint_dwell, HIGH contested_shot_rate
    # Score >0 = drop-leaning, <0 = switch-leaning
    drop_score = (f("paint_dwell_pct") - f("contested_shot_rate")) / 2.0

    # --- Axis 2: Paint Protection ---
    # Paint-protective: opp forced AWAY from paint → lower shot_zone_paint_pct
    # Also: higher contested_shot_rate on all shots (deters interior attempts)
    # Negative paint_pct = protecting paint; positive contested = tight defense
    # paint_pct going DOWN means defense is good (forcing away)
    paint_protection_score = (-f("shot_zone_paint_pct") + f("contested_shot_rate")) / 2.0

    # --- Axis 3: Perimeter Denial ---
    # Denying perimeter → opp has LOWER shot_zone_3pt_pct AND lower catch_shoot_pct
    perimeter_denial_score = (-f("shot_zone_3pt_pct") - f("catch_shoot_pct")) / 2.0

    # --- Axis 4: Pace Control ---
    # Controlling pace → opp shoots LATER in shot clock (higher avg_shot_clock means less pressure)
    # OR denying transitions (lower play_type_transition_pct)
    # We want: team FORCES late clocks (opp clock delta positive = team let them walk it up? No.)
    # avg_shot_clock_at_shot delta > 0 → opp shoots EARLY (defense less disruptive)
    # avg_shot_clock_at_shot delta < 0 → opp forced to shoot EARLIER (pressure)
    # Lower transition = team slows pace
    pace_control_score = (-f("avg_shot_clock_at_shot") - f("play_type_transition_pct")) / 2.0

    # --- Axis 5: Iso Force (forcing isolation) ---
    # Positive = opp runs more iso (team's help defense creates iso → or team forces iso by not helping?)
    # Here: higher iso_pct imposed means the defense channels everything through 1-on-1
    iso_force_score = f("play_type_isolation_pct")

    # --- Axis 6: Closeout Intensity ---
    # NOTE: CV audit flagged sign issues on defender_approach_speed
    # Higher avg_defender_distance = defenders playing off (soft closeouts)
    # Lower defender_approach_speed = slower closeouts (with caveat: sign may be inverted in raw CV)
    # We use positive closeout = active closeouts = lower defender_distance + positive approach_speed
    # (with explicit caveat that approach_speed may be inverted)
    closeout_score = (-f("avg_defender_distance") + f("defender_approach_speed")) / 2.0

    # ── Bug-13: team-quality residualization ──────────────────────────────────
    # Subtract quality_z * QUALITY_WEIGHT from every axis to remove the
    # "this team is just globally weak/strong at defense" confound.
    # quality_z > 0 = worse defense than league avg → penalizes all positive scores.
    # quality_z < 0 = better defense → slightly boosts scores (correct: their imposed
    # deviations are more likely to reflect scheme intent than sample noise).
    quality_z = _team_quality_z.get(team, 0.0)
    quality_correction = quality_z * _QUALITY_WEIGHT

    return {
        "drop_score": round(drop_score - quality_correction, 4),
        "paint_protection_score": round(paint_protection_score - quality_correction, 4),
        "perimeter_denial_score": round(perimeter_denial_score - quality_correction, 4),
        "pace_control_score": round(pace_control_score - quality_correction, 4),
        "iso_force_score": round(iso_force_score - quality_correction, 4),
        "closeout_score": round(closeout_score - quality_correction, 4),
        # Store raw (pre-residualization) perimeter denial and quality info for audit
        "perimeter_denial_raw": round(perimeter_denial_score, 4),
        "quality_z": round(quality_z, 3),
        "quality_correction": round(quality_correction, 4),
        # Store contested_shot_rate for the PERIMETER DENIAL gate
        "_contested_shot_rate": round(f("contested_shot_rate"), 4),
    }


# ─── STEP 2: Classify each team ───────────────────────────────────────────────
def classify_team(axes: dict) -> tuple[list[str], str]:
    tags = []
    d = axes["drop_score"]
    pp = axes["paint_protection_score"]
    pd_ = axes["perimeter_denial_score"]
    pc = axes["pace_control_score"]
    iso = axes["iso_force_score"]
    co = axes["closeout_score"]

    # Drop vs Switch
    if d > 0.10:
        tags.append("DROP COVERAGE")
    elif d < -0.10:
        tags.append("SWITCH HEAVY")

    # Paint protection
    if pp > 0.10:
        tags.append("PAINT-FIRST DEFENSE")

    # ── Bug-13: Perimeter denial — residualized + scheme-intent gate ──────────
    # Two conditions must BOTH pass:
    # 1. Residualized perimeter_denial_score > 0.10  (after defrtg quality correction)
    # 2. contested_shot_rate delta >= _CONTESTED_THRESHOLD  (actively contesting shots,
    #    not just allowing fewer 3s due to pace/opponent self-selection)
    # This prevents weak-defense teams (e.g. POR, UTA) from being tagged PERIMETER DENIAL
    # when opponents happen to take fewer 3s against them for non-scheme reasons.
    _contested = axes.get("_contested_shot_rate", 0.0)
    if pd_ > 0.10 and _contested >= _CONTESTED_THRESHOLD:
        tags.append("PERIMETER DENIAL")

    # Pace control
    if pc > 0.10:
        tags.append("PACE CONTROL")

    # Iso forcing
    if iso > 0.05:
        tags.append("ISO FORCE")
    elif iso < -0.05:
        tags.append("HELP DEFENSE")

    # Closeout
    if co > 0.05:
        tags.append("ACTIVE CLOSEOUTS")

    # ── Bug-13: Generic weak defense bucket ───────────────────────────────────
    # Teams that are significantly weaker than average defensively (quality_z > threshold)
    # but have no qualifying scheme tag get a GENERIC_WEAK_DEFENSE label instead of
    # BALANCED, so downstream models treat their "scheme" as noise rather than signal.
    quality_z = axes.get("quality_z", 0.0)
    if not tags and quality_z > _WEAK_DEFENSE_Z_THRESHOLD:
        tags = ["GENERIC_WEAK_DEFENSE"]
    elif not tags:
        tags = ["BALANCED"]

    dominant = tags[0]
    return tags, dominant


# ─── STEP 3: Get top affected players per team ────────────────────────────────
def get_top_players(team: str, n: int = 5) -> list[dict]:
    sub = deviations[deviations["opp_team"] == team].copy()
    # Filter out obvious sentinel outliers (maxZ > 100 likely CV artifact)
    sub = sub[sub["max_abs_z"] < 50]
    sub = sub.nlargest(n, "max_abs_z")
    results = []
    for _, row in sub.iterrows():
        flags = str(row.get("deviation_flags", ""))
        # Get top feature from deviation flags
        top_feat = ""
        if flags and flags != "nan":
            # Parse first flag
            parts = flags.split(",")
            if parts:
                top_feat = parts[0].strip()
        results.append({
            "player_name": row["player_name"],
            "max_abs_z": round(float(row["max_abs_z"]), 2),
            "top_feature": top_feat,
        })
    return results


# ─── STEP 4: Build full per-team records ──────────────────────────────────────
print("[INT-12] Computing scheme axes for all 30 teams ...")
records = []
scheme_details = {}

for team in sorted(imposed.keys()):
    profile = imposed[team]
    n_pg = profile["n_player_games_observed"]
    n_opp = profile["n_unique_opponents"]
    confidence = "high" if n_pg >= 25 else ("med" if n_pg >= 12 else "low")

    axes = compute_axes(team, profile)
    tags, dominant_tag = classify_team(axes)
    top_players = get_top_players(team)

    # Strip internal-only axes fields before writing to parquet
    _internal_keys = {"_contested_shot_rate"}
    axes_public = {k: v for k, v in axes.items() if k not in _internal_keys}

    records.append({
        "team": team,
        "n_opposing_player_games": n_pg,
        "n_unique_opponents": n_opp,
        "confidence": confidence,
        **axes_public,
        "dominant_tag": dominant_tag,
        "all_tags": "|".join(tags),
    })

    scheme_details[team] = {
        "axes": axes,
        "tags": tags,
        "dominant_tag": dominant_tag,
        "n_player_games": n_pg,
        "n_unique_opponents": n_opp,
        "confidence": confidence,
        "imposed_deviations": profile.get("imposed_deviations", {}),
        "top_players": top_players,
        "interpretation": profile.get("interpretation", ""),
    }

df_schemes = pd.DataFrame(records).set_index("team")
print(df_schemes[["n_opposing_player_games", "quality_z", "perimeter_denial_raw",
                   "perimeter_denial_score", "drop_score", "paint_protection_score",
                   "pace_control_score", "dominant_tag"]].to_string())
print("\n  [Bug-13] POR perimeter_denial: raw=%+.3f -> residualized=%+.3f | tag=%s" % (
    df_schemes.loc["POR", "perimeter_denial_raw"],
    df_schemes.loc["POR", "perimeter_denial_score"],
    df_schemes.loc["POR", "dominant_tag"],
))
print("  [Bug-13] UTA perimeter_denial: raw=%+.3f -> residualized=%+.3f | tag=%s" % (
    df_schemes.loc["UTA", "perimeter_denial_raw"],
    df_schemes.loc["UTA", "perimeter_denial_score"],
    df_schemes.loc["UTA", "dominant_tag"],
))


# ─── STEP 5: Validate against known schemes ───────────────────────────────────
print("\n[INT-12] Validating against known schemes ...")
validation_results = []

for team, known in KNOWN_SCHEMES.items():
    predicted_tags = scheme_details[team]["tags"]
    axes = scheme_details[team]["axes"]
    matches = []
    misses = []
    for axis_key, direction in known["expected"].items():
        val = axes.get(axis_key, 0)
        if direction == "positive":
            hit = val > 0
        elif direction == "negative":
            hit = val < 0
        else:
            hit = True
        label = f"{axis_key}={val:.3f} ({'OK' if hit else 'FAIL'} expected {direction})"
        if hit:
            matches.append(label)
        else:
            misses.append(label)

    match_pct = len(matches) / max(len(known["expected"]), 1)
    validation_results.append({
        "team": team,
        "known_desc": known["desc"],
        "predicted_tags": "|".join(predicted_tags),
        "matches": matches,
        "misses": misses,
        "match_pct": match_pct,
    })

    status = "MATCH" if match_pct >= 0.5 else ("PARTIAL" if match_pct > 0 else "MISS")
    print(f"  {team} ({status}): {known['desc'][:60]}")
    print(f"    Predicted: {predicted_tags}")
    for m in matches:
        print(f"    MATCH: {m}".encode('ascii', 'replace').decode('ascii'))
    for m in misses:
        print(f"    MISS:  {m}".encode('ascii', 'replace').decode('ascii'))

total_matches = sum(1 for v in validation_results if v["match_pct"] >= 0.5)
total_with_expected = sum(1 for v in validation_results if KNOWN_SCHEMES[v["team"]]["expected"])
print(f"\n  Validation: {total_matches}/{total_with_expected} teams match known schemes")


# ─── STEP 6: Save parquet + indicators JSON ────────────────────────────────────
print("\n[INT-12] Saving outputs ...")
df_schemes.reset_index().to_parquet(OUT_PARQUET, index=False)
print(f"  Saved parquet: {OUT_PARQUET}")

indicators = {
    "version": "v2",
    "date": TODAY,
    "bug13_residualization": {
        "applied": bool(_team_quality_z),
        "source": _defrtg_source,
        "quality_weight": _QUALITY_WEIGHT,
        "contested_threshold": _CONTESTED_THRESHOLD,
        "weak_defense_z_threshold": _WEAK_DEFENSE_Z_THRESHOLD,
        "description": (
            "Bug-13 fix: each scheme axis is residualized by subtracting "
            "(team_def_rtg - league_mean) / league_std * QUALITY_WEIGHT. "
            "PERIMETER DENIAL additionally requires contested_shot_rate >= "
            f"{_CONTESTED_THRESHOLD} to exclude teams where 3pt suppression "
            "reflects opponent self-selection rather than active scheme. "
            "Removes false PERIMETER DENIAL tags for globally weak defenses "
            "(POR, UTA)."
        ),
    },
    "methodology": {
        "drop_score": "(paint_dwell_pct - contested_shot_rate) / 2 - quality_correction [>0=drop, <0=switch]",
        "paint_protection_score": "(-shot_zone_paint_pct + contested_shot_rate) / 2 - quality_correction",
        "perimeter_denial_score": "(-shot_zone_3pt_pct - catch_shoot_pct) / 2 - quality_correction",
        "pace_control_score": "(-avg_shot_clock_at_shot - play_type_transition_pct) / 2 - quality_correction",
        "iso_force_score": "play_type_isolation_pct - quality_correction",
        "closeout_score": "(-avg_defender_distance + defender_approach_speed) / 2 - quality_correction [CAVEAT: approach_speed has sign issues]",
        "quality_correction": f"(team_def_rtg - league_mean) / league_std * {_QUALITY_WEIGHT} [source: {_defrtg_source}]",
    },
    "thresholds": {
        "DROP COVERAGE": "drop_score > 0.10",
        "SWITCH HEAVY": "drop_score < -0.10",
        "PAINT-FIRST DEFENSE": "paint_protection_score > 0.10",
        "PERIMETER DENIAL": f"perimeter_denial_score > 0.10 AND contested_shot_rate >= {_CONTESTED_THRESHOLD}",
        "PACE CONTROL": "pace_control_score > 0.10",
        "ISO FORCE": "iso_force_score > 0.05",
        "HELP DEFENSE": "iso_force_score < -0.05",
        "ACTIVE CLOSEOUTS": "closeout_score > 0.05",
        "GENERIC_WEAK_DEFENSE": f"no scheme tag matched AND quality_z > {_WEAK_DEFENSE_Z_THRESHOLD}",
    },
    "validation": {
        "total_match": total_matches,
        "total_testable": total_with_expected,
        "results": validation_results,
    },
    "teams": scheme_details,
}

with open(OUT_INDICATORS, "w", encoding="utf-8") as f:
    json.dump(indicators, f, indent=2)
print(f"  Saved indicators: {OUT_INDICATORS}")


# ─── STEP 7: Per-team scheme detail ───────────────────────────────────────────
# Per-team defensive scheme detail now lives inside each team note's SCHEME-AUTO
# block (folded in by render_schemes_to_vault.py) so each team is a single graph
# node. The v1 standalone Schemes/<TEAM>.md files are no longer written; this
# script still produces defensive_schemes.parquet (consumed by the team-card
# builder) and the Defensive_Schemes.md atlas below.
print("\n[INT-12] Per-team scheme detail folded into Teams/<TRI>.md by render_schemes (no standalone Schemes/ files)")


# ─── STEP 8: Main Atlas ────────────────────────────────────────────────────────
print("\n[INT-12] Writing Defensive_Schemes.md atlas ...")

# Rankings for notable contrasts
df_s = df_schemes.reset_index()
most_drop = df_s.nlargest(1, "drop_score").iloc[0]
most_switch = df_s.nsmallest(1, "drop_score").iloc[0]
most_paint = df_s.nlargest(1, "paint_protection_score").iloc[0]
most_perim = df_s.nlargest(1, "perimeter_denial_score").iloc[0]
most_pace = df_s.nlargest(1, "pace_control_score").iloc[0]

# Build team table
header = "| team | drop_score | paint_prot | perim_denial | pace_ctrl | iso_force | closeout | confidence | dominant_tag |\n"
header += "|------|-----------|-----------|-------------|----------|----------|---------|-----------|-------------|\n"
rows_str = ""
for _, row in df_s.sort_values("team").iterrows():
    rows_str += (
        f"| {row['team']} "
        f"| {row['drop_score']:+.3f} "
        f"| {row['paint_protection_score']:+.3f} "
        f"| {row['perimeter_denial_score']:+.3f} "
        f"| {row['pace_control_score']:+.3f} "
        f"| {row['iso_force_score']:+.3f} "
        f"| {row['closeout_score']:+.3f} "
        f"| {row['confidence']} "
        f"| {row['dominant_tag']} |\n"
    )

# Per-team links — point at the team note (scheme atlas is folded in there)
team_links = "\n".join(f"- [[Teams/{t}]]" for t in sorted(scheme_details.keys()))

# Tag distribution
from collections import Counter
all_tag_lists = [sd["tags"] for sd in scheme_details.values()]
flat_tags = [t for tl in all_tag_lists for t in tl]
tag_counts = Counter(flat_tags)
tag_dist = "\n".join(f"- {tag}: {count} teams" for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]))

# Validation summary table
val_table = "| team | predicted | known | match? |\n|------|-----------|-------|--------|\n"
for vr in validation_results:
    team = vr["team"]
    known_short = KNOWN_SCHEMES[team]["desc"][:55] + "..."
    match_sym = "[MATCH]" if vr["match_pct"] >= 0.5 else ("[PARTIAL]" if vr["match_pct"] > 0 else "[MISS]")
    val_table += f"| {team} | {vr['predicted_tags']} | {known_short} | {match_sym} |\n"

atlas_md_content = f"""# Defensive Scheme Atlas (INT-12)
*Generated: {TODAY} | Source: CV opponent-imposed behavioral profiles (INT-3)*

## Methodology

Each team's defensive scheme is inferred from how opposing players BEHAVE when playing against them — not from direct observation of the defense. If BOS opponents consistently shoot fewer 3-pointers and face tighter contests, that implies BOS denies the perimeter.

**Six scheme axes** (each a normalized composite score in σ units):

| Axis | Formula | +Score means | -Score means |
|------|---------|-------------|-------------|
| Drop vs Switch | (paint_dwell − contested_shot_rate) / 2 | DROP COVERAGE | SWITCH HEAVY |
| Paint Protection | (−shot_zone_paint_pct + contested_shot_rate) / 2 | Paint-protective | Paint-permissive |
| Perimeter Denial | (−shot_zone_3pt_pct − catch_shoot_pct) / 2 | Perimeter-denying | Perimeter-permissive |
| Pace Control | (−avg_shot_clock + −transition_pct) / 2 | Forces slower pace | Allows fast pace |
| Iso Force | play_type_isolation_pct | Forces 1-on-1 | Extra help defense |
| Closeout Intensity | (−avg_defender_distance + approach_speed) / 2 | Tight closeouts | Soft closeouts |

**Classification thresholds:** Any axis >0.10σ triggers a tag; axes <−0.10σ trigger inverse tags.

---

## Team Scheme Classifications

{header}{rows_str}

---

## Validation Against Known Schemes

{val_table}
**Validation result:** {total_matches}/{total_with_expected} testable teams matched known public schemes.
{"Methodology is directionally valid." if total_matches >= 3 else "Partial validation — interpret with caution." if total_matches >= 2 else "Low validation rate — axes may need recalibration."}

---

## Notable Scheme Contrasts

- **Most extreme DROP coverage:** {most_drop['team']} (drop_score = {most_drop['drop_score']:+.3f})
- **Most extreme SWITCH coverage:** {most_switch['team']} (drop_score = {most_switch['drop_score']:+.3f})
- **Most PAINT-PROTECTIVE:** {most_paint['team']} (paint_protection_score = {most_paint['paint_protection_score']:+.3f})
- **Most PERIMETER-DENYING:** {most_perim['team']} (perimeter_denial_score = {most_perim['perimeter_denial_score']:+.3f})
- **Most PACE-CONTROLLING:** {most_pace['team']} (pace_control_score = {most_pace['pace_control_score']:+.3f})

---

## Tag Distribution (30 teams)

{tag_dist}

---

## Per-Team Scheme Reports

{team_links}

---

## Caveats

- Per-team CV sample sizes range from {df_s['n_opposing_player_games'].min()} to {df_s['n_opposing_player_games'].max()} opposing player-games — small-sample teams have noisy scores
- Teams with <12 player-games (TOR={imposed['TOR']['n_player_games_observed']}, PHX={imposed['PHX']['n_player_games_observed']}) have LOW confidence tags
- Scheme classification derives from OPPOSING player behavior — cannot distinguish scheme intent from personnel limitations
- `defender_approach_speed` has known sign issues from CV pipeline audit — closeout_score should be interpreted with caution
- **ISSUE-022**: `defender_distance=200.0` sentinel values not nullified in ML; may inflate avg_defender_distance for some teams
- All scores are z-score composites of CV-derived features — they measure BEHAVIORAL IMPOSITION, not scheme quality
- A team's "DROP COVERAGE" tag could reflect great bigs who protect the paint (Jokic) OR poor perimeter defenders who can't switch

---

## How to Use This Atlas

1. **Matchup prep**: "MIN is PAINT-FIRST → opposing guards/wings will face more paint deterrence, should expect forced mid-range shots"
2. **Betting context**: If a player's archetype clashes with the opponent's dominant scheme → outlier game predictor
3. **Prop bets**: Bigs who thrive in the paint vs DROP COVERAGE teams may see suppressed paint touches vs SWITCH HEAVY teams
4. **Lineup construction**: "Which players thrive vs switch vs drop?" — cross-reference with player fingerprints
"""

with open(ATLAS_MD, "w", encoding="utf-8") as f:
    f.write(atlas_md_content)
print(f"  Written atlas: {ATLAS_MD}")

# ─── FINAL REPORT ─────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("INT-12 Defensive Scheme Intelligence — COMPLETE")
print("=" * 70)
print(f"  Teams classified: {len(scheme_details)} / 30")
high_conf = sum(1 for sd in scheme_details.values() if sd["confidence"] == "high")
med_conf = sum(1 for sd in scheme_details.values() if sd["confidence"] == "med")
low_conf = sum(1 for sd in scheme_details.values() if sd["confidence"] == "low")
print(f"  High confidence (25+ games): {high_conf}")
print(f"  Med confidence (12-24): {med_conf}")
print(f"  Low confidence (<12): {low_conf}")
print(f"\n  Validation: {total_matches}/{total_with_expected} known schemes confirmed")
print(f"\n  Outputs:")
print(f"    {OUT_PARQUET}")
print(f"    {OUT_INDICATORS}")
print(f"    {ATLAS_MD}")
print(f"    (per-team scheme folded into Teams/<TRI>.md by render_schemes — no standalone files)")
print(f"\n  Most extreme tags:")
print(f"    Drop: {most_drop['team']} ({most_drop['drop_score']:+.3f})")
print(f"    Switch: {most_switch['team']} ({most_switch['drop_score']:+.3f})")
print(f"    Paint-first: {most_paint['team']} ({most_paint['paint_protection_score']:+.3f})")
print(f"    Perimeter-denying: {most_perim['team']} ({most_perim['perimeter_denial_score']:+.3f})")
