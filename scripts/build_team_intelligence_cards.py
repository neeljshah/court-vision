"""
build_team_intelligence_cards.py
Synthesizes 4 shipped atlases into 30 per-team markdown intelligence cards.

Atlases:
  C3: opp_defensive_intensity  (keyed on team_id = abbr, season)
  C4: opp_paint_allowance      (keyed on team_id = abbr, season)
  TTS: team_tempo_spacing      (keyed on team_id = abbr, has team_abbr bridge)
  SCH: defensive_schemes       (1 row per team, keyed on 'team' = abbr)
"""

from pathlib import Path
import json, warnings
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data" / "intelligence"
TEAMS_DIR = ROOT / "vault" / "Intelligence" / "Teams"
INDEX_PATH = ROOT / "vault" / "Intelligence" / "_Team_Index.md"
ATLAS_PATH = ROOT / "vault" / "Intelligence" / "Team_Atlas.md"
PLAYER_JSON = ROOT / "data" / "nba" / "player_full_2024-25.json"

TODAY = "2026-05-29"
CURRENT_SEASON = "2025-26"
PRIOR_SEASON = "2024-25"

# Auto-generated marker blocks owned by other writers — preserved across rewrites
# so re-running this card builder never wipes the folded scheme atlas or roster.
PRESERVED_BLOCKS = [
    ("<!-- SCHEME-AUTO START -->", "<!-- SCHEME-AUTO END -->"),
    ("<!-- ROSTER-AUTO START -->", "<!-- ROSTER-AUTO END -->"),
]


def _preserve_blocks(note_path: Path, new_card: str) -> str:
    """Re-attach marker blocks from an existing note onto a freshly built card.

    The card builder rewrites the whole note; the SCHEME-AUTO block (folded in by
    render_schemes_to_vault.py) and ROSTER-AUTO block (export_player_playstyle_to_vault.py)
    are owned elsewhere, so we carry them forward verbatim instead of dropping them.
    """
    if not note_path.exists():
        return new_card
    old = note_path.read_text(encoding="utf-8")
    out = new_card.rstrip()
    for start, end in PRESERVED_BLOCKS:
        if start in old and end in old and start not in out:
            block = old[old.index(start) : old.index(end) + len(end)]
            out = out + "\n\n" + block.strip()
    return out + "\n"

# ---------- scheme tag → matchup note mapping ----------
SCHEME_MATCHUP = {
    "SWITCH HEAVY": (
        "Switches across all picks; mid-range and contested 3s rise for opponents."
    ),
    "DROP COVERAGE": (
        "Big stays paint-side; opponents see clean mid-range and high paint rate."
    ),
    "PERIMETER DENIAL": (
        "Forces opponents off the arc; mid-range and rim attempts spike."
    ),
    "PAINT-FIRST DEFENSE": (
        "Walls off rim; opponents driven to mid + 3PT volume."
    ),
    "PACE CONTROL": (
        "Slows possessions deliberately; favors half-court specialists."
    ),
    "ISO FORCE": (
        "Funnels ball-handlers into isolation; team-shot creation drops."
    ),
    "ACTIVE CLOSEOUTS": (
        "Aggressive closeouts; kick-out 3PT attempts and mid-range pull-ups open."
    ),
    "HELP DEFENSE": (
        "Rotates early into the lane; corners and skip passes create open looks."
    ),
    "GENERIC_WEAK_DEFENSE": (
        "No clear scheme identity; opponents shoot their natural profile."
    ),
    "BALANCED": (
        "Balanced defensive approach; no dominant tendency skewing opponent shot mix."
    ),
}


def load_atlases():
    c3 = pd.read_parquet(DATA_DIR / "opp_defensive_intensity.parquet")
    c4 = pd.read_parquet(DATA_DIR / "opp_paint_allowance.parquet")
    tts = pd.read_parquet(DATA_DIR / "team_tempo_spacing.parquet")
    sch = pd.read_parquet(DATA_DIR / "defensive_schemes.parquet")
    return c3, c4, tts, sch


def build_team_id_abbr_map(tts):
    """tts has both team_id and team_abbr — use as bridge. team_id IS the abbr here."""
    bridge = tts.drop_duplicates(subset=["team_id", "team_abbr"])[
        ["team_id", "team_abbr"]
    ].set_index("team_id")["team_abbr"].to_dict()
    return bridge


def last_row(df, team, season_col="season"):
    """Return the last (most recent) row for a team in the current season."""
    sub = df[(df.iloc[:, 0] == team) & (df[season_col] == CURRENT_SEASON)]
    if sub.empty:
        return None
    return sub.sort_values("game_date").iloc[-1]


def season_mean_z(df, team, z_cols):
    """Season-average z-scores for current season."""
    sub = df[(df.iloc[:, 0] == team) & (df["season"] == CURRENT_SEASON)]
    if sub.empty:
        return {c: np.nan for c in z_cols}
    return {c: sub[c].mean() for c in z_cols}


def league_rank(df, team, col, season):
    """Rank (1=best intensity, i.e. highest z) among all teams for final row."""
    last_rows = df[df["season"] == season].sort_values("game_date").groupby(
        df.columns[0]
    ).last().reset_index()
    if col not in last_rows.columns:
        return "N/A"
    vals = last_rows[[df.columns[0], col]].dropna()
    if team not in vals[df.columns[0]].values:
        return "N/A"
    rank = int(vals[col].rank(ascending=False, method="min")[
        vals[df.columns[0]] == team
    ].values[0])
    return f"{rank}/30"


def impute_median(arr, all_vals):
    """Replace NaN with column median of all_vals."""
    med = np.nanmedian(all_vals)
    return np.where(np.isnan(arr), med, arr)


def build_knn(c3, c4, tts):
    """
    Compute 2 k-NN dicts:
      def_neighbors[team] = [n1, n2, n3]   (defensive intensity, drop closeout)
      tempo_neighbors[team] = [n1, n2, n3] (tempo/spacing)
    Returns (def_neighbors, tempo_neighbors, warnings_list)
    """
    teams = sorted(c3[c3["season"] == CURRENT_SEASON].iloc[:, 0].unique())

    # --- defensive vector ---
    def_cols = [
        "opp_contested_shot_rate_imposed_z",
        "opp_avg_defender_distance_imposed_z",
        "opp_paint_attempts_allowed_pct_z",
        "opp_pace_imposed_z",
        "opp_catch_shoot_allowed_pct_z",
        # opp_closeout_speed_imposed_z DROPPED (Bug 35 nulls)
    ]
    last_c3 = (
        c3[c3["season"] == CURRENT_SEASON]
        .sort_values("game_date")
        .groupby("team_id")
        .last()
        .reset_index()
    )
    last_c3 = last_c3.set_index("team_id")

    def_mat = []
    for t in teams:
        row = last_c3.loc[t, def_cols].values.astype(float) if t in last_c3.index else np.full(len(def_cols), np.nan)
        def_mat.append(row)
    def_mat = np.array(def_mat)
    for j in range(def_mat.shape[1]):
        def_mat[:, j] = impute_median(def_mat[:, j], def_mat[:, j])

    # --- tempo vector ---
    tempo_cols = [
        "team_possession_duration_z",
        "team_transition_share_z",
        "team_avg_spacing_z",
        "team_paint_dwell_z",
    ]
    last_tts = (
        tts.sort_values("game_date")
        .groupby("team_id")
        .last()
        .reset_index()
        .set_index("team_id")
    )
    tempo_mat = []
    for t in teams:
        row = last_tts.loc[t, tempo_cols].values.astype(float) if t in last_tts.index else np.full(len(tempo_cols), np.nan)
        tempo_mat.append(row)
    tempo_mat = np.array(tempo_mat)
    for j in range(tempo_mat.shape[1]):
        tempo_mat[:, j] = impute_median(tempo_mat[:, j], tempo_mat[:, j])

    def euclidean_knn(mat, teams, k=3):
        neighbors = {}
        n = len(teams)
        for i, t in enumerate(teams):
            dists = []
            for j, other in enumerate(teams):
                if i == j:
                    continue
                d = np.sqrt(np.sum((mat[i] - mat[j]) ** 2))
                dists.append((d, other))
            dists.sort()
            neighbors[t] = [x[1] for x in dists[:k]]
        return neighbors

    def_neighbors = euclidean_knn(def_mat, teams, k=3)
    tempo_neighbors = euclidean_knn(tempo_mat, teams, k=3)

    # Symmetry check: for A→B in nearest-3, assert A in B's nearest-5
    knn5_def = euclidean_knn(def_mat, teams, k=5)
    knn5_tempo = euclidean_knn(tempo_mat, teams, k=5)
    warn_list = []
    for a in teams:
        for b in def_neighbors[a]:
            if a not in knn5_def[b]:
                warn_list.append(f"DEF kNN asymmetry: {a}->{b} but {a} not in {b}'s nearest-5")
        for b in tempo_neighbors[a]:
            if a not in knn5_tempo[b]:
                warn_list.append(f"TEMPO kNN asymmetry: {a}->{b} but {a} not in {b}'s nearest-5")

    return def_neighbors, tempo_neighbors, warn_list


def top_dim_c4(row_c4):
    """Return the highest |z| dimension label and value from C4."""
    dims = {
        "opp_paint_pct_allowed_z": "paint-attempt share",
        "opp_3pt_pct_allowed_z": "3PT volume",
        "opp_mid_pct_allowed_z": "mid-range volume",
        "opp_paint_dwell_pct_allowed_z": "paint dwell share",
    }
    best, best_val = None, 0.0
    for col, label in dims.items():
        v = row_c4.get(col, np.nan)
        if pd.notna(v) and abs(v) > abs(best_val):
            best, best_val = label, v
    if best is None:
        return "overall shot mix", 0.0
    return best, best_val


def matchup_note(scheme_row, c4_row):
    dominant = scheme_row.get("dominant_tag", "")
    note = SCHEME_MATCHUP.get(dominant, "")
    if not note:
        # Fallback: join all_tags
        tags = str(scheme_row.get("all_tags", "")).split("|")
        note = " | ".join(t.strip() for t in tags if t.strip())

    # Shot-mix line from C4
    dim_label, dim_z = top_dim_c4(c4_row)
    direction = "above" if dim_z > 0 else "below"
    note += f" Allows {direction}-average {dim_label} (z={dim_z:+.2f} vs league)."
    return note


def tempo_label(tempo_z):
    if tempo_z > 0.75:
        return "high-pace"
    elif tempo_z < -0.75:
        return "slow-pace"
    return "average tempo"


def spacing_label(spacing_z):
    if spacing_z > 0.75:
        return "wide-spacing"
    elif spacing_z < -0.75:
        return "compressed"
    return "balanced"


def fmt_z(v, prec=3):
    if pd.isna(v):
        return "N/A"
    return f"{v:+.{prec}f}"


def write_team_card(
    team, c3, c4, tts, sch_row,
    def_neighbors, tempo_neighbors,
    all_c3_last, all_c4_last, all_tts_last
):
    abbr = team

    # --- last-row snapshots ---
    row_c3 = last_row(c3, team)
    row_c4 = last_row(c4, team)
    row_tts_df = tts[tts["team_id"] == team].sort_values("game_date")
    row_tts = row_tts_df.iloc[-1] if not row_tts_df.empty else None

    # --- determine density tier (take worst of c3/c4) ---
    density_priority = {"league_prior": 0, "low": 1, "med": 2}
    densities = []
    if row_c3 is not None:
        densities.append(row_c3.get("data_density", "league_prior"))
    if row_c4 is not None:
        densities.append(row_c4.get("data_density", "league_prior"))
    if row_tts is not None:
        densities.append(row_tts.get("data_density", "low"))
    tier = min(densities, key=lambda x: density_priority.get(x, -1)) if densities else "league_prior"

    # --- n_cv_games ---
    n_cv = int(row_c3["n_games_window"]) if row_c3 is not None and pd.notna(row_c3.get("n_games_window")) else 0

    # --- seasons covered ---
    seasons = sorted(set(
        list(c3[c3["team_id"] == team]["season"].unique()) +
        list(c4[c4["team_id"] == team]["season"].unique())
    ))

    # --- C3 metrics ---
    c3_z_cols = [
        "opp_contested_shot_rate_imposed_z",
        "opp_avg_defender_distance_imposed_z",
        "opp_paint_attempts_allowed_pct_z",
        "opp_pace_imposed_z",
        "opp_catch_shoot_allowed_pct_z",
        "opp_defensive_intensity_z",
    ]
    c3_last_vals = {c: (row_c3[c] if row_c3 is not None else np.nan) for c in c3_z_cols}
    c3_means = season_mean_z(c3, team, c3_z_cols)

    # C3 league ranks (last row, current season)
    def_intensity_rank = league_rank(c3, team, "opp_defensive_intensity_z", CURRENT_SEASON)

    # --- C4 metrics ---
    c4_z_cols = [
        "opp_paint_pct_allowed_z",
        "opp_3pt_pct_allowed_z",
        "opp_mid_pct_allowed_z",
        "opp_paint_dwell_pct_allowed_z",
        "opp_shot_mix_deviation_z",
    ]
    c4_last_vals = {c: (row_c4[c] if row_c4 is not None else np.nan) for c in c4_z_cols}
    c4_means = season_mean_z(c4, team, c4_z_cols)

    # --- TTS metrics ---
    tts_tempo_z = row_tts["team_tempo_z"] if row_tts is not None else np.nan
    tts_spacing_z = row_tts["team_spacing_z"] if row_tts is not None else np.nan
    tts_composite_z = row_tts["team_tempo_spacing_composite_z"] if row_tts is not None else np.nan
    t_label = tempo_label(tts_tempo_z if pd.notna(tts_tempo_z) else 0.0)
    s_label = spacing_label(tts_spacing_z if pd.notna(tts_spacing_z) else 0.0)

    # --- Scheme ---
    dominant_tag = str(sch_row.get("dominant_tag", "N/A"))
    all_tags = str(sch_row.get("all_tags", "N/A"))
    sch_confidence = str(sch_row.get("confidence", "N/A"))
    drop_score = sch_row.get("drop_score", np.nan)
    paint_score = sch_row.get("paint_protection_score", np.nan)
    perim_score = sch_row.get("perimeter_denial_score", np.nan)
    pace_score = sch_row.get("pace_control_score", np.nan)
    iso_score = sch_row.get("iso_force_score", np.nan)
    closeout_score = sch_row.get("closeout_score", np.nan)

    # --- matchup note ---
    c4_row_dict = dict(c4_last_vals)
    sch_row_dict = dict(sch_row)
    mn = matchup_note(sch_row_dict, c4_row_dict)

    # --- k-NN ---
    def_nn = def_neighbors.get(team, [])
    tempo_nn = tempo_neighbors.get(team, [])

    # --- low coverage callout ---
    low_coverage = tier in ("low", "league_prior")

    # --- build markdown ---
    lines = []

    # frontmatter
    lines.append("---")
    lines.append(f"team_abbr: {abbr}")
    lines.append(f"team_id: {abbr}")
    lines.append(f"seasons_covered: {json.dumps(seasons)}")
    lines.append(f"last_updated: {TODAY}")
    lines.append(
        "atlases_referenced: [opp_defensive_intensity, opp_paint_allowance, team_tempo_spacing, defensive_schemes]"
    )
    lines.append(f"n_cv_games: {n_cv}")
    lines.append(f"data_density_tier: {tier}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {abbr} — Team Intelligence Card")
    lines.append("")

    if low_coverage:
        lines.append(
            "> **Low CV coverage** — values are league-prior shrunk; treat scheme tag as low-confidence."
        )
        lines.append("")

    # Section 1: Defensive Profile (C3)
    lines.append("## Defensive Profile (C3)")
    lines.append("")
    lines.append(f"| Metric | Last-Row z | Season-Avg z |")
    lines.append(f"|--------|-----------|--------------|")
    dim_labels = {
        "opp_contested_shot_rate_imposed_z": "Contested Shot Rate",
        "opp_avg_defender_distance_imposed_z": "Avg Defender Distance",
        "opp_paint_attempts_allowed_pct_z": "Paint Attempts Allowed %",
        "opp_pace_imposed_z": "Pace Imposed",
        "opp_catch_shoot_allowed_pct_z": "Catch-and-Shoot Allowed %",
        "opp_defensive_intensity_z": "**Composite Intensity**",
    }
    for col, label in dim_labels.items():
        lines.append(
            f"| {label} | {fmt_z(c3_last_vals[col])} | {fmt_z(c3_means[col])} |"
        )
    lines.append("")
    lines.append(f"- **League rank (composite intensity):** {def_intensity_rank}")
    lines.append(f"- **n_games_window:** {n_cv}")
    lines.append(f"- **Data density:** {tier}")
    lines.append("")

    # Section 2: Defensive Shot-Mix (C4)
    lines.append("## Defensive Shot-Mix (C4)")
    lines.append("")
    lines.append(f"| Metric | Last-Row z | Season-Avg z |")
    lines.append(f"|--------|-----------|--------------|")
    c4_dim_labels = {
        "opp_paint_pct_allowed_z": "Paint Attempts Allowed %",
        "opp_3pt_pct_allowed_z": "3PT Attempts Allowed %",
        "opp_mid_pct_allowed_z": "Mid-Range Allowed %",
        "opp_paint_dwell_pct_allowed_z": "Paint Dwell Allowed %",
        "opp_shot_mix_deviation_z": "**Shot-Mix Deviation**",
    }
    for col, label in c4_dim_labels.items():
        lines.append(
            f"| {label} | {fmt_z(c4_last_vals[col])} | {fmt_z(c4_means[col])} |"
        )
    top_dim_lbl, top_dim_val = top_dim_c4(c4_row_dict)
    lines.append("")
    lines.append(f"- **Top deviation dimension:** {top_dim_lbl} (z={fmt_z(top_dim_val)})")
    lines.append("")

    # Section 3: Scheme Tag
    lines.append("## Scheme Tag")
    lines.append("")
    lines.append(f"- **Dominant tag:** {dominant_tag}")
    lines.append(f"- **All tags:** {all_tags}")
    lines.append(f"- **Confidence:** {sch_confidence}")
    lines.append("")
    lines.append("| Score | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| Drop Coverage | {fmt_z(drop_score)} |")
    lines.append(f"| Paint Protection | {fmt_z(paint_score)} |")
    lines.append(f"| Perimeter Denial | {fmt_z(perim_score)} |")
    lines.append(f"| Pace Control | {fmt_z(pace_score)} |")
    lines.append(f"| ISO Force | {fmt_z(iso_score)} |")
    lines.append(f"| Active Closeouts | {fmt_z(closeout_score)} |")
    lines.append("")

    # Section 4: Offensive Tempo & Spacing
    lines.append("## Offensive Tempo & Spacing (C1+C2)")
    lines.append("")
    tts_z_cols = [
        "team_possession_duration_z",
        "team_transition_share_z",
        "team_tempo_z",
        "team_avg_spacing_z",
        "team_paint_dwell_z",
        "team_spacing_z",
        "team_tempo_spacing_composite_z",
    ]
    tts_labels = {
        "team_possession_duration_z": "Possession Duration",
        "team_transition_share_z": "Transition Share",
        "team_tempo_z": "**Tempo**",
        "team_avg_spacing_z": "Avg Spacing",
        "team_paint_dwell_z": "Paint Dwell",
        "team_spacing_z": "**Spacing**",
        "team_tempo_spacing_composite_z": "**Composite**",
    }
    lines.append("| Metric | Last-Row z |")
    lines.append("|--------|-----------|")
    for col, label in tts_labels.items():
        val = row_tts[col] if row_tts is not None and col in row_tts.index else np.nan
        lines.append(f"| {label} | {fmt_z(val)} |")
    lines.append("")
    lines.append(f"- **Profile:** {t_label}, {s_label}")
    lines.append(
        f"- **Composite z:** {fmt_z(tts_composite_z)} "
        f"(tempo z={fmt_z(tts_tempo_z)}, spacing z={fmt_z(tts_spacing_z)})"
    )
    lines.append("")

    # Section 5: Comparable Teams
    lines.append("## Comparable Teams")
    lines.append("")
    lines.append("**Nearest 3 by defensive intensity (C3):**")
    for nn in def_nn:
        lines.append(f"- [[Teams/{nn}]]")
    lines.append("")
    lines.append("**Nearest 3 by tempo/spacing (C1+C2):**")
    for nn in tempo_nn:
        lines.append(f"- [[Teams/{nn}]]")
    lines.append("")

    # Section 6: Matchup Notes
    lines.append("## Matchup Notes")
    lines.append("")
    lines.append(mn)
    lines.append("")

    # Section 7: CV Coverage
    lines.append("## CV Coverage")
    lines.append("")
    lines.append(f"- **n_cv_games:** {n_cv}")
    lines.append(f"- **data_density_tier:** {tier}")
    lines.append(f"- **Last updated:** {TODAY}")
    lines.append(f"- **Seasons in atlas:** {', '.join(seasons)}")
    lines.append("")

    return "\n".join(lines)


def build_index(team_cards, sch):
    """Build _Team_Index.md grouped by dominant_tag."""
    tag_teams = {}
    for team in team_cards:
        row = sch[sch["team"] == team]
        if row.empty:
            tag = "UNKNOWN"
        else:
            tag = str(row.iloc[0]["dominant_tag"])
        tag_teams.setdefault(tag, []).append(team)

    lines = ["# Team Intelligence Index", "", f"*Last updated: {TODAY}*", ""]
    lines.append("30 teams grouped by dominant defensive scheme tag.")
    lines.append("")
    for tag in sorted(tag_teams.keys()):
        lines.append(f"## {tag}")
        for t in sorted(tag_teams[tag]):
            lines.append(f"- [[Teams/{t}]]")
        lines.append("")
    return "\n".join(lines)


def _histogram(values, label, bins=5):
    """Simple text histogram."""
    values = [v for v in values if pd.notna(v)]
    if not values:
        return f"  {label}: no data\n"
    mn, mx = min(values), max(values)
    if mn == mx:
        return f"  {label}: all={mn:.3f}\n"
    width = (mx - mn) / bins
    counts = [0] * bins
    for v in values:
        idx = min(int((v - mn) / width), bins - 1)
        counts[idx] += 1
    out = f"  {label} [{mn:.2f} … {mx:.2f}]:\n"
    for i, c in enumerate(counts):
        lo = mn + i * width
        hi = lo + width
        bar = "#" * c
        out += f"    [{lo:+.2f},{hi:+.2f}): {bar} ({c})\n"
    return out


def build_atlas(c3, c4, tts, sch, def_neighbors, tempo_neighbors):
    """Build Team_Atlas.md with leaderboards and distribution histograms."""
    # Gather last-row values per team for current season
    last_c3 = (
        c3[c3["season"] == CURRENT_SEASON]
        .sort_values("game_date")
        .groupby("team_id")
        .last()
        .reset_index()
    )
    last_c4 = (
        c4[c4["season"] == CURRENT_SEASON]
        .sort_values("game_date")
        .groupby("team_id")
        .last()
        .reset_index()
    )
    last_tts = tts.sort_values("game_date").groupby("team_id").last().reset_index()

    def topbot(df, col, label, n=3):
        sub = df[[df.columns[0], col]].dropna()
        if sub.empty:
            return f"  {label}: no data\n"
        ranked = sub.sort_values(col, ascending=False).reset_index(drop=True)
        top = ranked.head(n)
        bot = ranked.tail(n).iloc[::-1]
        out = f"  **{label}**\n"
        out += f"  Top {n}: " + ", ".join(
            f"{row[df.columns[0]]} ({row[col]:+.3f})" for _, row in top.iterrows()
        ) + "\n"
        out += f"  Bottom {n}: " + ", ".join(
            f"{row[df.columns[0]]} ({row[col]:+.3f})" for _, row in bot.iterrows()
        ) + "\n"
        return out

    lines = [
        "# Team Atlas",
        "",
        f"*Last updated: {TODAY} — Season {CURRENT_SEASON}*",
        "",
        "Synthesized from 4 atlases: opp_defensive_intensity (C3), opp_paint_allowance (C4), team_tempo_spacing (C1+C2), defensive_schemes.",
        "",
        "---",
        "",
        "## Leaderboards",
        "",
        "### Defensive Intensity (C3)",
    ]
    lines.append(topbot(last_c3, "opp_defensive_intensity_z", "Composite Intensity"))
    lines.append(topbot(last_c3, "opp_contested_shot_rate_imposed_z", "Contested Shot Rate"))
    lines.append(topbot(last_c3, "opp_paint_attempts_allowed_pct_z", "Paint Attempts Allowed"))
    lines.append("")
    lines.append("### Shot-Mix Deviation (C4)")
    lines.append(topbot(last_c4, "opp_shot_mix_deviation_z", "Shot-Mix Deviation"))
    lines.append(topbot(last_c4, "opp_3pt_pct_allowed_z", "3PT Allowed"))
    lines.append(topbot(last_c4, "opp_paint_pct_allowed_z", "Paint Allowed"))
    lines.append("")
    lines.append("### Tempo (C1+C2)")
    lines.append(topbot(last_tts, "team_tempo_z", "Tempo"))
    lines.append(topbot(last_tts, "team_spacing_z", "Spacing"))
    lines.append(topbot(last_tts, "team_tempo_spacing_composite_z", "Composite Tempo+Spacing"))
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## League Distributions (text histograms)")
    lines.append("")
    lines.append("```")
    lines.append(_histogram(last_c3["opp_defensive_intensity_z"].tolist(), "Defensive Intensity z"))
    lines.append(_histogram(last_c4["opp_shot_mix_deviation_z"].tolist(), "Shot-Mix Deviation z"))
    lines.append(_histogram(last_tts["team_tempo_z"].tolist(), "Tempo z"))
    lines.append(_histogram(last_tts["team_spacing_z"].tolist(), "Spacing z"))
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Scheme Tag Distribution")
    lines.append("")
    tag_counts = sch["dominant_tag"].value_counts()
    for tag, cnt in tag_counts.items():
        lines.append(f"- {tag}: {cnt} teams")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Wikilink Map")
    lines.append("")
    lines.append("All 30 team cards: [[_Team_Index]]")
    lines.append("")
    teams = sorted(last_c3["team_id"].unique())
    lines.append(", ".join(f"[[Teams/{t}]]" for t in teams))
    lines.append("")

    return "\n".join(lines)


def main():
    print("Loading atlases...")
    c3, c4, tts, sch = load_atlases()

    print("Building team_id->abbr map...")
    id_abbr = build_team_id_abbr_map(tts)
    teams = sorted(c3[c3["season"] == CURRENT_SEASON]["team_id"].unique())
    print(f"Teams ({len(teams)}): {teams}")

    print("Computing k-NN...")
    def_neighbors, tempo_neighbors, knn_warns = build_knn(c3, c4, tts)

    if knn_warns:
        print(f"\nk-NN reciprocity warnings ({len(knn_warns)}):")
        for w in knn_warns:
            print(f"  WARN: {w.replace(chr(8594), '->')}")
    else:
        print("k-NN reciprocity: no violations")

    # Precompute last rows for rank computation
    last_c3_all = (
        c3[c3["season"] == CURRENT_SEASON]
        .sort_values("game_date")
        .groupby("team_id")
        .last()
        .reset_index()
    )
    last_c4_all = (
        c4[c4["season"] == CURRENT_SEASON]
        .sort_values("game_date")
        .groupby("team_id")
        .last()
        .reset_index()
    )
    last_tts_all = tts.sort_values("game_date").groupby("team_id").last().reset_index()

    # Create Teams directory
    TEAMS_DIR.mkdir(parents=True, exist_ok=True)

    print("\nWriting team cards...")
    density_dist = {}
    n_cv_list = []
    for team in teams:
        sch_row = sch[sch["team"] == team]
        sch_row_dict = dict(sch_row.iloc[0]) if not sch_row.empty else {}
        card = write_team_card(
            team, c3, c4, tts, sch_row_dict,
            def_neighbors, tempo_neighbors,
            last_c3_all, last_c4_all, last_tts_all
        )
        out_path = TEAMS_DIR / f"{team}.md"
        out_path.write_text(_preserve_blocks(out_path, card), encoding="utf-8")

        # collect stats
        row_c3 = last_row(c3, team)
        tier = "league_prior"
        densities = []
        row_c4 = last_row(c4, team)
        row_tts_df = tts[tts["team_id"] == team].sort_values("game_date")
        row_tts = row_tts_df.iloc[-1] if not row_tts_df.empty else None
        density_priority = {"league_prior": 0, "low": 1, "med": 2}
        if row_c3 is not None:
            densities.append(row_c3.get("data_density", "league_prior"))
        if row_c4 is not None:
            densities.append(row_c4.get("data_density", "league_prior"))
        if row_tts is not None:
            densities.append(row_tts.get("data_density", "low"))
        tier = min(densities, key=lambda x: density_priority.get(x, -1)) if densities else "league_prior"
        density_dist[tier] = density_dist.get(tier, 0) + 1

        n_cv = int(row_c3["n_games_window"]) if row_c3 is not None and pd.notna(row_c3.get("n_games_window")) else 0
        n_cv_list.append(n_cv)

        print(f"  Wrote {out_path.name}  (density={tier}, n_cv={n_cv})")

    # Build index and atlas LAST
    print("\nWriting _Team_Index.md...")
    index_md = build_index(teams, sch)
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(index_md, encoding="utf-8")

    print("Writing Team_Atlas.md...")
    atlas_md = build_atlas(c3, c4, tts, sch, def_neighbors, tempo_neighbors)
    ATLAS_PATH.write_text(atlas_md, encoding="utf-8")

    # Validation assertions
    print("\n--- Validation ---")
    card_count = len(list(TEAMS_DIR.glob("*.md")))
    assert card_count == 30, f"FAIL: expected 30 cards, got {card_count}"
    print(f"PASS: {card_count} team cards exist")

    # Frontmatter check
    missing_density = []
    for p in TEAMS_DIR.glob("*.md"):
        text = p.read_text(encoding="utf-8")
        if "data_density_tier" not in text:
            missing_density.append(p.name)
    assert not missing_density, f"FAIL: cards missing data_density_tier: {missing_density}"
    print("PASS: all cards contain data_density_tier")

    assert INDEX_PATH.exists() and INDEX_PATH.stat().st_size > 0, "FAIL: _Team_Index.md missing or empty"
    assert ATLAS_PATH.exists() and ATLAS_PATH.stat().st_size > 0, "FAIL: Team_Atlas.md missing or empty"
    print("PASS: _Team_Index.md and Team_Atlas.md exist and non-empty")

    # Summary
    median_n = float(np.median(n_cv_list)) if n_cv_list else 0
    league_prior_count = density_dist.get("league_prior", 0)
    print(f"\n=== Summary ===")
    print(f"Teams written: {card_count}")
    print(f"Median n_games_window: {median_n:.0f}")
    print(f"Density distribution: {density_dist}")
    print(f"league_prior teams: {league_prior_count}")
    print(f"k-NN reciprocity warnings: {len(knn_warns)}")
    print(f"_Team_Index.md: {INDEX_PATH}")
    print(f"Team_Atlas.md: {ATLAS_PATH}")
    print("Done.")


if __name__ == "__main__":
    main()
