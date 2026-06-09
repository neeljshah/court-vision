"""
build_scout_reports.py — Per-game scout report generator.

Synthesises 4 team atlases (C1+C2 tempo/spacing, C3 def intensity, C4 paint allowance)
+ matchup_grid (2 survived INT-63 interactions)
+ archetype_outlier_signals (INT-54)
+ player_development_v2 (INT-67, |dev|>=0.5)
+ defensive_schemes
→ one markdown file per game in vault/Intelligence/Scouts/
+ _Scout_Index.md

CLI:
    python scripts/build_scout_reports.py --date-range 2026-04-25:2026-05-29
    python scripts/build_scout_reports.py  # default: last 30 days from data max

ROOT = Path(__file__).resolve().parent.parent
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

# ─── paths ────────────────────────────────────────────────────────────────────
INTEL = ROOT / "data" / "intelligence"
VAULT_SCOUTS = ROOT / "vault" / "Intelligence" / "Scouts"
TEAMS_DIR = ROOT / "vault" / "Intelligence" / "Teams"
SCOUT_INDEX = ROOT / "vault" / "Intelligence" / "_Scout_Index.md"
SG_GLOB = "data/nba/season_games_*.json"


# ─── loaders ──────────────────────────────────────────────────────────────────

def _load_parquet(name: str) -> pd.DataFrame:
    p = INTEL / f"{name}.parquet"
    if not p.exists():
        print(f"  [WARN] missing: {p.name}", file=sys.stderr)
        return pd.DataFrame()
    return pd.read_parquet(p)


def _load_season_games() -> pd.DataFrame:
    import glob as _glob
    rows: list[dict] = []
    for fpath in _glob.glob(str(ROOT / SG_GLOB)):
        with open(fpath, encoding="utf-8") as fh:
            data = json.load(fh)
        rows.extend(data.get("rows", []))
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["game_date_dt"] = pd.to_datetime(df["game_date"])
    return df


# ─── helpers ──────────────────────────────────────────────────────────────────

LEAGUE_PRIOR = "league_prior"
CONFIDENCE_ORDER = ["high", "mixed", "low", LEAGUE_PRIOR, "skip"]


def _z_str(val: float | None) -> str:
    if val is None or pd.isna(val):
        return "—"
    # Avoid "-0.00" / "+-0.00" artifacts
    rounded = round(val, 2)
    if rounded == 0.0:
        return "+0.00"
    sign = "+" if rounded > 0 else ""
    return f"{sign}{rounded:.2f}"


def _tier_from_density(density: str | None) -> str:
    """Map data_density string to confidence tier."""
    if density is None:
        return LEAGUE_PRIOR
    d = str(density).lower()
    if d in ("high", "med"):
        return d if d != "med" else "mixed"
    if d == "low":
        return "low"
    return LEAGUE_PRIOR


def _best_tier(a: str, b: str) -> str:
    ai = CONFIDENCE_ORDER.index(a) if a in CONFIDENCE_ORDER else len(CONFIDENCE_ORDER)
    bi = CONFIDENCE_ORDER.index(b) if b in CONFIDENCE_ORDER else len(CONFIDENCE_ORDER)
    return CONFIDENCE_ORDER[min(ai, bi)]


def _get_team_scheme_tags(team: str, ds: pd.DataFrame) -> tuple[str, str]:
    """Return (dominant_tag, all_tags) for team from defensive_schemes."""
    row = ds[ds["team"] == team]
    if row.empty:
        return ("—", "—")
    r = row.iloc[0]
    return (str(r.get("dominant_tag", "—")), str(r.get("all_tags", "—")))


def _read_team_card_scheme(team: str) -> str | None:
    """Read dominant scheme tag from team card YAML front-matter or return None."""
    card = TEAMS_DIR / f"{team}.md"
    if not card.exists():
        return None
    with open(card, encoding="utf-8") as fh:
        text = fh.read(2000)
    # Try frontmatter dominant tag
    m = re.search(r"Dominant tag[:\s]+([A-Z ]+)", text)
    if m:
        return m.group(1).strip()
    return None


def _density_pct(mg_row: pd.Series) -> str:
    """Return density string for report header."""
    n_off = int(mg_row.get("n_games_offense_window", 0) or 0)
    n_def = int(mg_row.get("n_games_defense_window", 0) or 0)
    density = str(mg_row.get("data_density", LEAGUE_PRIOR)).lower()
    return f"{density} (off_n={n_off}, def_n={n_def})"


def _safe_float(v: Any) -> float | None:
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


# ─── per-game sections ────────────────────────────────────────────────────────

def _matchup_synopsis(
    game_row: dict,
    home_mg: pd.Series | None,
    away_mg: pd.Series | None,
) -> str:
    """One-line game header."""
    game_id = game_row["game_id"]
    game_date = game_row["game_date"]
    home = game_row["home_team"]
    away = game_row["away_team"]
    return (
        f"## Matchup Synopsis\n\n"
        f"**{away} @ {home}** — {game_date}  |  `{game_id}`\n"
    )


def _interaction_signals(home_mg: pd.Series | None, away_mg: pd.Series | None) -> str:
    """The 2 survived INT-63 interaction scalars."""
    lines = ["## INT-63 Interaction Signals (directional, not predictive)\n"]
    lines.append(
        "_Only 2 of 6 interaction definitions survived null control. "
        "Treat as directional context only — no predictive validation._\n"
    )

    def _side_row(label: str, mg: pd.Series | None) -> str:
        if mg is None:
            return f"| {label} | — | — |\n"
        mx1 = _safe_float(mg.get("mx_tempo_vs_opp_pace"))
        mx2 = _safe_float(mg.get("mx_offense_vs_defense_composite"))
        return f"| {label} | {_z_str(mx1)} | {_z_str(mx2)} |\n"

    lines.append(
        "| Side | mx_tempo_vs_opp_pace | mx_offense_vs_defense_composite |\n"
        "|------|---------------------|----------------------------------|\n"
    )
    home_team = home_mg["team_id"] if home_mg is not None else "HOME"
    away_team = away_mg["team_id"] if away_mg is not None else "AWAY"
    lines.append(_side_row(f"{home_team} OFF", home_mg))
    lines.append(_side_row(f"{away_team} OFF", away_mg))
    return "".join(lines) + "\n"


def _off_vs_def(
    off_team: str,
    def_team: str,
    off_mg: pd.Series | None,
    def_mg: pd.Series | None,
) -> str:
    """Home OFF vs Away DEF block (and reverse via calling twice)."""
    lines = [f"## {off_team} OFF vs {def_team} DEF\n\n"]
    lines.append("| Axis | OFF z | DEF z |\n")
    lines.append("|------|-------|-------|\n")

    pairs = [
        ("Tempo",           "off_tempo_z",                "def_pace_imposed_z"),
        ("Spacing",         "off_spacing_z",              "def_contested_shot_rate_z"),
        ("Paint dwell",     "off_paint_dwell_z",          "def_paint_attempts_allowed_z"),
        ("Transition share","off_transition_share_z",     "def_defender_distance_z"),
        ("Avg spacing",     "off_avg_spacing_z",          "def_catch_shoot_allowed_z"),
        ("Composite",       "off_tempo_spacing_z",        "def_intensity_z"),
    ]
    for label, off_col, def_col in pairs:
        off_v = _safe_float(off_mg.get(off_col)) if off_mg is not None else None
        def_v = _safe_float(def_mg.get(def_col)) if def_mg is not None else None
        lines.append(f"| {label} | {_z_str(off_v)} | {_z_str(def_v)} |\n")

    # Paint allowance from def side
    paint_z = _safe_float(def_mg.get("def_paint_pct_allowed_z")) if def_mg is not None else None
    threept_z = _safe_float(def_mg.get("def_3pt_pct_allowed_z")) if def_mg is not None else None
    lines.append(
        f"\n**{def_team} shot-mix allowed:** paint_z={_z_str(paint_z)}, "
        f"3pt_z={_z_str(threept_z)}\n"
    )
    return "".join(lines) + "\n"


def _tempo_spacing_forecast(home: str, away: str, home_mg: pd.Series | None, away_mg: pd.Series | None) -> str:
    lines = ["## Tempo + Spacing Forecast\n\n"]
    for team, mg in [(home, home_mg), (away, away_mg)]:
        if mg is None:
            lines.append(f"**{team}:** league_prior — no edge claim\n")
            continue
        tempo = _safe_float(mg.get("off_tempo_z"))
        spacing = _safe_float(mg.get("off_spacing_z"))
        composite = _safe_float(mg.get("off_tempo_spacing_z"))
        density = str(mg.get("data_density", LEAGUE_PRIOR))
        lines.append(
            f"**{team}:** tempo_z={_z_str(tempo)}, spacing_z={_z_str(spacing)}, "
            f"composite_z={_z_str(composite)} ({density})\n"
        )
    return "".join(lines) + "\n"


def _scheme_tags(home: str, away: str, ds: pd.DataFrame) -> str:
    lines = ["## Defensive Scheme Tags\n\n"]
    for team in [home, away]:
        dominant, all_tags = _get_team_scheme_tags(team, ds)
        lines.append(f"- **{team}:** {dominant} (all: {all_tags})\n")
    return "".join(lines) + "\n"


def _paint_asymmetry(home: str, away: str, home_mg: pd.Series | None, away_mg: pd.Series | None) -> str:
    lines = ["## Paint Allowance Asymmetry\n\n"]
    lines.append("| Team DEF | Paint Allowed z | 3PT Allowed z | Mid Allowed z | Deviation z |\n")
    lines.append("|----------|----------------|---------------|---------------|-------------|\n")
    for team, mg in [(home, home_mg), (away, away_mg)]:
        if mg is None:
            lines.append(f"| {team} | — | — | — | — |\n")
            continue
        paint = _z_str(_safe_float(mg.get("def_paint_pct_allowed_z")))
        threept = _z_str(_safe_float(mg.get("def_3pt_pct_allowed_z")))
        mid = _z_str(_safe_float(mg.get("def_mid_pct_allowed_z")))
        dev = _z_str(_safe_float(mg.get("def_shot_mix_deviation_z")))
        lines.append(f"| {team} | {paint} | {threept} | {mid} | {dev} |\n")
    return "".join(lines) + "\n"


def _cv_flagged_players(
    game_id: str,
    game_date: str,
    aos: pd.DataFrame,
    pdev: pd.DataFrame,
    pf: pd.DataFrame,
) -> str:
    """INT-54 outliers + INT-67 dev_score |dev|>=0.5 for players in this game."""
    lines = ["## CV-Flagged Players\n\n"]
    any_flag = False

    # INT-54: archetype outlier signals for this game
    if not aos.empty:
        game_flags = aos[aos["game_id"] == game_id]
        strong = game_flags[game_flags["flag_strong_outlier"] == True]
        if not strong.empty:
            any_flag = True
            lines.append("### INT-54 Archetype Outliers (strong_outlier=True)\n\n")
            for _, row in strong.iterrows():
                pid = int(row["player_id"])
                pname = _player_name(pid, pf)
                outlier_z = _z_str(_safe_float(row.get("outlier_z")))
                d_last5 = _z_str(_safe_float(row.get("d_last5")))
                dir3 = row.get("direction_top3", "{}")
                try:
                    dir_str = str(json.loads(dir3)) if isinstance(dir3, str) else str(dir3)
                except Exception:
                    dir_str = str(dir3)
                lines.append(
                    f"- **{pname}** (id={pid}): outlier_z={outlier_z}, d_last5={d_last5}, "
                    f"top dims: {dir_str[:120]}\n"
                )
            lines.append("\n")

    # INT-67: player_development_v2 for this game, |dev_score|>=0.5
    if not pdev.empty:
        dev_game = pdev[pdev["game_id"] == game_id]
        dev_game = dev_game[dev_game["dev_score"].abs() >= 0.5]
        if not dev_game.empty:
            any_flag = True
            lines.append("### INT-67 Development Signals (|dev_score|>=0.5)\n\n")
            for _, row in dev_game.iterrows():
                pid = int(row["player_id"])
                pname = str(row.get("player_name", _player_name(pid, pf)))
                dev = float(row["dev_score"])
                sign = "rising" if dev > 0 else "declining"
                top = str(row.get("top_trending", ""))[:80]
                lines.append(
                    f"- **{pname}** (id={pid}): dev_score={dev:+.3f} ({sign}), "
                    f"top driver: {top}\n"
                )
            lines.append("\n")

    if not any_flag:
        lines.append("_No CV-flagged players for this game._\n")

    return "".join(lines) + "\n"


def _player_name(pid: int, pf: pd.DataFrame) -> str:
    """Look up player name from player_fingerprints index."""
    if pf.empty or pid not in pf.index:
        return f"player_{pid}"
    row = pf.loc[pid]
    return str(row.get("player_name", f"player_{pid}"))


def _cv_coverage_block(
    game_id: str,
    home: str,
    away: str,
    home_mg: pd.Series | None,
    away_mg: pd.Series | None,
) -> str:
    lines = ["## CV Coverage / Confidence Tier\n\n"]
    for team, mg in [(home, home_mg), (away, away_mg)]:
        if mg is None:
            lines.append(f"- **{team}:** league_prior — no edge claim\n")
            continue
        density = str(mg.get("data_density", LEAGUE_PRIOR))
        n_off = int(mg.get("n_games_offense_window", 0) or 0)
        n_def = int(mg.get("n_games_defense_window", 0) or 0)
        lines.append(
            f"- **{team}:** density={density}, n_off_games={n_off}, n_def_games={n_def}\n"
        )
    return "".join(lines) + "\n"


def _is_all_league_prior(home_mg: pd.Series | None, away_mg: pd.Series | None) -> bool:
    """True if both teams are league_prior on all 4 atlas axes."""
    for mg in [home_mg, away_mg]:
        if mg is None:
            continue
        density = str(mg.get("data_density", LEAGUE_PRIOR)).lower()
        if density not in (LEAGUE_PRIOR, "league_prior"):
            return False
    # Also check if matchup_grid rows exist at all
    if home_mg is None and away_mg is None:
        return True
    return True


def _derive_confidence(home_mg: pd.Series | None, away_mg: pd.Series | None) -> str:
    h_tier = _tier_from_density(home_mg.get("data_density") if home_mg is not None else None)
    a_tier = _tier_from_density(away_mg.get("data_density") if away_mg is not None else None)
    return _best_tier(h_tier, a_tier)


def _density_pct_float(home_mg: pd.Series | None, away_mg: pd.Series | None) -> float:
    """Return mean data_density as 0-100 percentage for index."""
    vals = []
    density_map = {"high": 100.0, "med": 60.0, "low": 25.0, LEAGUE_PRIOR: 5.0, "league_prior": 5.0}
    for mg in [home_mg, away_mg]:
        if mg is None:
            vals.append(5.0)
            continue
        d = str(mg.get("data_density", LEAGUE_PRIOR)).lower()
        vals.append(density_map.get(d, 5.0))
    return sum(vals) / len(vals) if vals else 0.0


# ─── report assembler ─────────────────────────────────────────────────────────

def _build_report(
    game_row: dict,
    home_mg: pd.Series | None,
    away_mg: pd.Series | None,
    mg_home_off: pd.Series | None,
    mg_away_off: pd.Series | None,
    ds: pd.DataFrame,
    aos: pd.DataFrame,
    pdev: pd.DataFrame,
    pf: pd.DataFrame,
) -> tuple[str, str, float]:
    """
    Returns (markdown_content, confidence_tier, density_pct_float).
    home_mg  = matchup row where team_id=HOME (HOME OFF vs AWAY DEF)
    away_mg  = matchup row where team_id=AWAY (AWAY OFF vs HOME DEF)
    """
    game_id = game_row["game_id"]
    game_date = game_row["game_date"]
    home = game_row["home_team"]
    away = game_row["away_team"]

    # Skip rule: both teams league_prior AND no matchup_grid row
    both_prior = (home_mg is None and away_mg is None)
    if both_prior:
        confidence = "skip"
    else:
        confidence = _derive_confidence(home_mg, away_mg)

    if confidence == "skip":
        content = (
            f"---\n"
            f"game_id: {game_id}\n"
            f"matchup: {away} @ {home}\n"
            f"date: {game_date}\n"
            f"confidence: skip\n"
            f"---\n\n"
            f"# {away} @ {home} — {game_date}\n\n"
            f"_Skipped: both teams league_prior on all 4 atlas axes and no matchup_grid row._\n"
        )
        return content, "skip", 5.0

    density_pct = _density_pct_float(home_mg, away_mg)

    parts: list[str] = []
    # YAML front-matter
    parts.append(
        f"---\n"
        f"game_id: {game_id}\n"
        f"matchup: {away} @ {home}\n"
        f"date: {game_date}\n"
        f"confidence: {confidence}\n"
        f"density_pct: {density_pct:.0f}\n"
        f"---\n\n"
    )
    parts.append(f"# {away} @ {home} — {game_date}\n\n")
    parts.append(_matchup_synopsis(game_row, home_mg, away_mg))
    parts.append(_interaction_signals(home_mg, away_mg))
    parts.append(_off_vs_def(home, away, home_mg, away_mg))
    parts.append(_off_vs_def(away, home, away_mg, home_mg))
    parts.append(_tempo_spacing_forecast(home, away, home_mg, away_mg))
    parts.append(_scheme_tags(home, away, ds))
    parts.append(_paint_asymmetry(home, away, home_mg, away_mg))
    parts.append(_cv_flagged_players(game_id, game_date, aos, pdev, pf))
    parts.append(_cv_coverage_block(game_id, home, away, home_mg, away_mg))

    # Honest caveat footer
    parts.append(
        "---\n"
        "_Scout report: synthesis only, no predictive validation. "
        "league_prior zones = no edge claim. "
        "INT-63 interactions: directional only (2/6 survived null control)._\n"
    )

    return "".join(parts), confidence, density_pct


# ─── atomic write ─────────────────────────────────────────────────────────────

def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


# ─── index builder ────────────────────────────────────────────────────────────

def _build_index(entries: list[dict]) -> str:
    """Build _Scout_Index.md from list of dicts with keys: date, matchup, confidence, density_pct."""
    # Sort by date desc, keep newest 60
    entries_sorted = sorted(entries, key=lambda x: x["date"], reverse=True)[:60]
    lines = [
        "# Scout Index\n\n",
        "_Auto-generated by build_scout_reports.py. Last 60 games, date desc._\n\n",
        "| Date | Matchup | Confidence | Density % |\n",
        "|------|---------|------------|-----------|\n",
    ]
    for e in entries_sorted:
        lines.append(
            f"| {e['date']} | {e['matchup']} | {e['confidence']} | {e['density_pct']:.0f}% |\n"
        )
    return "".join(lines)


# ─── main ─────────────────────────────────────────────────────────────────────

def main(date_range: str | None = None) -> None:
    print("Loading atlases...")

    matchup_grid = _load_parquet("matchup_grid")
    defensive_schemes = _load_parquet("defensive_schemes")
    aos = _load_parquet("archetype_outlier_signals")
    pdev = _load_parquet("player_development_v2")
    pf = _load_parquet("player_fingerprints")
    sg_df = _load_season_games()

    if sg_df.empty:
        print("ERROR: no season_games rows loaded.", file=sys.stderr)
        sys.exit(1)

    if matchup_grid.empty:
        print("WARN: matchup_grid empty — all reports will be skip-tier.", file=sys.stderr)
    else:
        matchup_grid["game_date_dt"] = pd.to_datetime(matchup_grid["game_date"])

    # ── date range ────────────────────────────────────────────────────────────
    # Data max date (data is historical, ends at end of season)
    if not matchup_grid.empty:
        data_max_date = matchup_grid["game_date_dt"].max()
    else:
        data_max_date = sg_df["game_date_dt"].max()

    if date_range:
        parts = date_range.split(":")
        start_dt = pd.to_datetime(parts[0])
        end_dt = pd.to_datetime(parts[1]) if len(parts) > 1 else pd.Timestamp.now()
        # Clamp end to data availability
        if end_dt > data_max_date:
            print(
                f"[INFO] Requested end {end_dt.date()} > data max {data_max_date.date()}. "
                f"Clamping to {data_max_date.date()}."
            )
            end_dt = data_max_date
    else:
        # Default: last 30 days anchored to max date in data
        end_dt = data_max_date
        start_dt = end_dt - pd.Timedelta(days=30)

    print(f"Date range: {start_dt.date()} to {end_dt.date()}")

    # ── filter season_games ───────────────────────────────────────────────────
    games_in_range = sg_df[
        (sg_df["game_date_dt"] >= start_dt) & (sg_df["game_date_dt"] <= end_dt)
    ].copy()
    # Deduplicate by game_id
    games_in_range = games_in_range.drop_duplicates("game_id").sort_values("game_date_dt")
    print(f"Games in date range: {len(games_in_range)}")

    # ── index matchup_grid by (game_id, team_id) for fast lookup ──────────────
    mg_index: dict[tuple[str, str], pd.Series] = {}
    if not matchup_grid.empty:
        for _, row in matchup_grid.iterrows():
            mg_index[(str(row["game_id"]), str(row["team_id"]))] = row

    # ── output dir ────────────────────────────────────────────────────────────
    VAULT_SCOUTS.mkdir(parents=True, exist_ok=True)

    n_high = n_mixed = n_low = n_skip = 0
    index_entries: list[dict] = []

    for _, game_row in games_in_range.iterrows():
        game_id = str(game_row["game_id"])
        home = str(game_row["home_team"])
        away = str(game_row["away_team"])
        game_date = str(game_row["game_date"])

        # HOME offense vs AWAY defense
        home_mg = mg_index.get((game_id, home))
        # AWAY offense vs HOME defense
        away_mg = mg_index.get((game_id, away))

        content, confidence, density_pct = _build_report(
            game_row=game_row.to_dict(),
            home_mg=home_mg,
            away_mg=away_mg,
            mg_home_off=home_mg,
            mg_away_off=away_mg,
            ds=defensive_schemes,
            aos=aos,
            pdev=pdev,
            pf=pf,
        )

        # Write file
        fname = f"{game_date}_{away}@{home}.md"
        out_path = VAULT_SCOUTS / fname
        _atomic_write(out_path, content)

        # Tally
        if confidence == "high":
            n_high += 1
        elif confidence == "mixed":
            n_mixed += 1
        elif confidence == "low":
            n_low += 1
        else:
            n_skip += 1

        index_entries.append({
            "date": game_date,
            "matchup": f"{away} @ {home}",
            "confidence": confidence,
            "density_pct": density_pct,
        })

    # ── coverage gate ─────────────────────────────────────────────────────────
    n_total = len(games_in_range)
    n_non_trivial = n_high + n_mixed + n_low
    coverage_pct = (n_non_trivial / n_total * 100) if n_total > 0 else 0.0
    print(
        f"\nSummary: {n_total} games | "
        f"high={n_high} mixed={n_mixed} low={n_low} skip={n_skip}"
    )
    print(f"Non-trivial coverage: {n_non_trivial}/{n_total} = {coverage_pct:.1f}%")
    if n_total > 0 and coverage_pct < 80:
        print(
            f"[WARN] Coverage gate FAIL: {coverage_pct:.1f}% < 80%. "
            "Most games have sparse CV data — expected given tracker coverage.",
            file=sys.stderr,
        )

    # ── write index ───────────────────────────────────────────────────────────
    index_content = _build_index(index_entries)
    _atomic_write(SCOUT_INDEX, index_content)
    print(f"\nIndex written: {SCOUT_INDEX}")
    print(f"Scout reports: {VAULT_SCOUTS}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build per-game scout reports")
    parser.add_argument(
        "--date-range",
        type=str,
        default=None,
        help="YYYY-MM-DD:YYYY-MM-DD (default: last 30 days from data max date)",
    )
    args = parser.parse_args()
    main(date_range=args.date_range)
