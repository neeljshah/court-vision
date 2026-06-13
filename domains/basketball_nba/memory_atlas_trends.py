"""domains.basketball_nba.memory_atlas_trends — NBA archetype-season trend notes.

Emits vault/Sports/Basketball_NBA/Trends/:
  _Trends_Overview.md          cross-season archetype-share + efficiency summary
  Seasons/<season>_Archetypes.md  per-season breakdown (counts only, no names)

F5-clean: stdlib + pandas only.  No src.* / kernel.* / edge language.
Public API: build_trends(out_dir, data_dir=DEFAULT_DATA_DIR) -> list[pathlib.Path]
"""
from __future__ import annotations

import pathlib
from typing import Dict, List, Optional

import pandas as pd

from scripts.platformkit.atlas.obsidian_emit import write_note
from domains.basketball_nba.memory_atlas_archetypes import ARCHETYPES
from domains.basketball_nba.memory_atlas_seasons import (
    _load_player_archetype_stats,
    _load_team_season_agg,
    _compute_archetype_mix,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = _REPO_ROOT / "data"
DEFAULT_OUT = _REPO_ROOT / "vault" / "Sports" / "Basketball_NBA"
_ARCHETYPE_LABELS: List[str] = [a["label"] for a in ARCHETYPES]
_MIN_GAMES = 10

# ---------------------------------------------------------------------------
# Helpers + core trend computation
# ---------------------------------------------------------------------------


def _fmt(v: object, d: int = 1) -> str:
    try:
        return str(round(float(v), d))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "—"


def _build_archetype_table(mix_by_season: Dict[str, Dict[str, int]], seasons: List[str]) -> str:
    """Markdown table: archetype × season share (%)."""
    col_heads = " | ".join(f"{s}" for s in seasons)
    header = f"| Archetype | {col_heads} | Δ first→last |"
    sep_parts = ["---"] + ["---" for _ in seasons] + ["---"]
    separator = "| " + " | ".join(sep_parts) + " |"
    lines = [header, separator]

    for label in _ARCHETYPE_LABELS:
        totals = {s: sum(mix_by_season[s].values()) for s in seasons}
        shares = []
        for s in seasons:
            t = totals[s]
            c = mix_by_season[s].get(label, 0)
            shares.append((c / t * 100) if t else 0.0)

        share_cells = " | ".join(f"{sh:.1f}%" for sh in shares)
        if len(seasons) >= 2:
            delta_val = shares[-1] - shares[0]
            sign = "+" if delta_val >= 0 else "−"
            delta_cell = f"{sign}{abs(delta_val):.1f}pp"
        else:
            delta_cell = "—"
        lines.append(f"| {label} | {share_cells} | {delta_cell} |")

    return "\n".join(lines)


def _build_efficiency_table(team_agg: pd.DataFrame, seasons: List[str]) -> str:
    """Markdown table: median league efficiency metrics by season."""
    header = "| Season | Off Rtg | Def Rtg | Net Rtg | Pace | eFG% |"
    separator = "|--------|---------|---------|---------|------|------|"
    lines = [header, separator]

    for s in seasons:
        sub = team_agg[team_agg["season_label"] == s]
        if sub.empty:
            lines.append(f"| {s} | — | — | — | — | — |")
            continue
        off = sub["off_rtg"].median() if "off_rtg" in sub.columns else float("nan")
        dfr = sub["def_rtg"].median() if "def_rtg" in sub.columns else float("nan")
        net = off - dfr
        pace = sub["pace"].median() if "pace" in sub.columns else float("nan")
        efg = sub["efg_pct"].median() if "efg_pct" in sub.columns else float("nan")
        lines.append(
            f"| {s} | {_fmt(off)} | {_fmt(dfr)} | {_fmt(net)} | {_fmt(pace)} | {_fmt(efg, 3)} |"
        )

    return "\n".join(lines)


def _key_trends(mix_by_season: Dict[str, Dict[str, int]], seasons: List[str]) -> List[str]:
    """Return bullet-point strings describing the most notable archetype shifts."""
    if len(seasons) < 2:
        return ["- Insufficient seasons for trend comparison."]

    first, last = seasons[0], seasons[-1]
    t_first = sum(mix_by_season[first].values())
    t_last = sum(mix_by_season[last].values())

    bullets: List[str] = []
    for label in _ARCHETYPE_LABELS:
        if t_first == 0 or t_last == 0:
            continue
        sh_first = mix_by_season[first].get(label, 0) / t_first * 100
        sh_last = mix_by_season[last].get(label, 0) / t_last * 100
        delta = sh_last - sh_first
        if abs(delta) >= 1.0:
            direction = "rose" if delta > 0 else "fell"
            bullets.append(
                f"- **{label}** share {direction} {abs(delta):.1f}pp "
                f"({sh_first:.1f}% → {sh_last:.1f}%, {first}→{last})."
            )

    if not bullets:
        bullets.append("- No archetype share moved by ≥1pp across the period.")
    return sorted(bullets)


# ---------------------------------------------------------------------------
# Note renderers
# ---------------------------------------------------------------------------

def _render_overview(seasons: List[str], mix_by_season: Dict[str, Dict[str, int]], team_agg: pd.DataFrame) -> str:
    arch_table = _build_archetype_table(mix_by_season, seasons)
    eff_table = _build_efficiency_table(team_agg, seasons)
    trend_bullets = "\n".join(_key_trends(mix_by_season, seasons))

    season_links = " | ".join(f"[[Trends/Seasons/{s}_Archetypes|{s}]]" for s in seasons)

    return (
        "---\n"
        "tags:\n"
        "  - sport/nba\n"
        "  - atlas/trends\n"
        "---\n\n"
        "# NBA Archetype-Season Trends\n\n"
        f"[[Archetypes/_Archetypes_Index|Archetypes]] | {season_links} | [[_Index]]\n\n"
        "Cross-season view of how NBA playstyle-archetype prevalence and league efficiency "
        "shift over time. Counts only — no individual player names.\n\n"
        "## Key Trend Findings\n\n"
        f"{trend_bullets}\n\n"
        "## Archetype Share by Season (%)\n\n"
        f"{arch_table}\n\n"
        "## League Efficiency by Season (team median)\n\n"
        f"{eff_table}\n\n"
        "#sport/nba #atlas/trends #archetype\n"
    )


def _render_season_archetypes(season: str, mix: Dict[str, int], prev_mix: Optional[Dict[str, int]]) -> str:
    total = sum(mix.values())
    rows: List[str] = []
    for label in sorted(mix, key=lambda l: -mix[l]):
        count = mix[label]
        share = f"{count / total * 100:.1f}%" if total else "—"
        if prev_mix is not None:
            prev_total = sum(prev_mix.values())
            prev_share = (prev_mix.get(label, 0) / prev_total * 100) if prev_total else 0.0
            cur_share_f = (count / total * 100) if total else 0.0
            delta = cur_share_f - prev_share
            sign = "+" if delta >= 0 else "−"
            delta_cell = f"{sign}{abs(delta):.1f}pp"
        else:
            delta_cell = "—"
        rows.append(f"| {label} | {count} | {share} | {delta_cell} |")

    table_body = "\n".join(rows) if rows else "| — | 0 | — | — |"

    return (
        "---\n"
        f'season: "{season}"\n'
        "tags:\n"
        "  - sport/nba\n"
        "  - atlas/trends\n"
        "  - atlas/season\n"
        "---\n\n"
        f"# NBA Archetype Mix — {season}\n\n"
        "[[Trends/_Trends_Overview|Trends Overview]] | [[Archetypes/_Archetypes_Index|Archetypes]] | [[_Index]]\n\n"
        f"**Total player-seasons classified** (≥{_MIN_GAMES} games): {total}\n\n"
        "## Archetype Counts\n\n"
        "| Archetype | Count | Share | Δ vs prev season |\n"
        "|-----------|-------|-------|------------------|\n"
        f"{table_body}\n\n"
        "#sport/nba #atlas/trends #archetype\n"
    )


# ---------------------------------------------------------------------------
# File I/O + Public API
# ---------------------------------------------------------------------------

def _write(path: pathlib.Path, text: str) -> None:
    write_note(path, text)


def build_trends(
    out_dir: pathlib.Path,
    data_dir: Optional[pathlib.Path] = None,
    *,
    _team_df: Optional[pd.DataFrame] = None,
    _player_df: Optional[pd.DataFrame] = None,
) -> List[pathlib.Path]:
    """Write NBA archetype-season trend notes and return written paths.

    Parameters
    ----------
    out_dir:
        Root output directory (e.g. vault/Sports/Basketball_NBA).
        Trends/ sub-folder is created automatically.
    data_dir:
        Repo data/ directory.  Ignored when _team_df / _player_df are provided.
    _team_df:
        Optional override for team_advanced_stats (tests).
        Expected columns: team_tricode, season_label, off_rtg, def_rtg, pace, efg_pct.
    _player_df:
        Optional override for player archetype stats (tests).
        Expected columns mirror _load_player_archetype_stats output.
        Pass an empty DataFrame to suppress archetype section.
    """
    out_dir = pathlib.Path(out_dir)
    if data_dir is None:
        data_dir = DEFAULT_DATA_DIR

    # --- Load data ---
    team_agg = _team_df.copy() if _team_df is not None else _load_team_season_agg(pathlib.Path(data_dir))
    player_df = _player_df.copy() if _player_df is not None else _load_player_archetype_stats(pathlib.Path(data_dir))

    # --- Determine seasons ---
    seasons: List[str] = []
    if not team_agg.empty and "season_label" in team_agg.columns:
        seasons = sorted(team_agg["season_label"].unique())
    elif not player_df.empty and "season_label" in player_df.columns:
        seasons = sorted(player_df["season_label"].unique())

    trends_dir = out_dir / "Trends"
    written: List[pathlib.Path] = []

    if not seasons:
        # No data: write empty overview and return
        overview_path = trends_dir / "_Trends_Overview.md"
        _write(overview_path, "# NBA Archetype-Season Trends\n\nNo data available.\n")
        return [overview_path]

    # --- Compute archetype mix per season ---
    mix_by_season: Dict[str, Dict[str, int]] = {}
    for season in seasons:
        mix_by_season[season] = _compute_archetype_mix(player_df, season, min_games=_MIN_GAMES)

    # --- Per-season archetype notes ---
    prev_mix: Optional[Dict[str, int]] = None
    for season in seasons:
        note_text = _render_season_archetypes(season, mix_by_season[season], prev_mix)
        note_path = trends_dir / "Seasons" / f"{season}_Archetypes.md"
        _write(note_path, note_text)
        written.append(note_path)
        prev_mix = mix_by_season[season]

    # --- Overview note ---
    overview_text = _render_overview(seasons, mix_by_season, team_agg)
    overview_path = trends_dir / "_Trends_Overview.md"
    _write(overview_path, overview_text)
    written.append(overview_path)

    return written
