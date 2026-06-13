"""domains.tennis.atlas_style_trends — Style-era trends atlas for tennis.

Computes how the share of each playstyle archetype (and the surface mix) shifts
year by year across the corpus.  Emits Obsidian-compatible Markdown notes.

Public API: build_style_trends(out_dir, corpus_dir) -> list[pathlib.Path]

F5-clean: stdlib + numpy + pandas + domains.tennis.* only.
No edge / betting language.  No individual player names in emitted notes.
"""
from __future__ import annotations

import pathlib
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import pandas as pd

from domains.tennis.atlas_playstyle_specs import (
    ALL_COURT_MAX_SPREAD, ARCHETYPES,
    CLAY_SPECIALIST_DELTA, GS_DELTA, GS_MIN_MATCHES,
    GRASS_SPECIALIST_DELTA, HARD_SPECIALIST_DELTA,
    HEIGHT_BIG_SERVER, MIN_MATCHES, MIN_SURFACE_MATCHES,
)
from scripts.platformkit.atlas.obsidian_emit import write_note as _write

DEFAULT_CORPUS: pathlib.Path = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "domains" / "tennis"
)
_SLUG_ORDER: List[str] = [a.slug for a in ARCHETYPES]
_SLUG_LABEL: Dict[str, str] = {a.slug: a.name for a in ARCHETYPES}
_ABBREV: Dict[str, str] = {
    "Clay_Court_Specialist": "Clay", "Fast_Court_Big_Server": "BigSrv",
    "All_Court_Baseliner": "AllCrt", "Left_Handed_Specialist": "LeftH",
    "Grand_Slam_Performer": "GSlam", "Hard_Court_Specialist": "Hard",
    "Grass_Court_Specialist": "Grass", "Journeyman": "Jrny",
}


def _ok(v: object) -> bool:
    return v is not None and not (isinstance(v, float) and pd.isna(v))


def _year_col(m: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(m["date"].astype(str), errors="coerce").dt.year


def _load_corpus(corpus_dir: pathlib.Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    matches = pd.read_parquet(corpus_dir / "matches.parquet").copy()
    matches["date"] = matches["date"].astype(str)
    pp = corpus_dir / "players.parquet"
    players = (pd.read_parquet(pp) if pp.exists()
               else pd.DataFrame(columns=["player_id", "full_name", "hand", "height"]))
    return matches, players


def _player_maps(players: pd.DataFrame) -> Tuple[dict, dict]:
    hmap: dict[int, Optional[float]] = {}
    handmap: dict[int, str] = {}
    for _, pr in players.iterrows():
        pid = int(pr["player_id"])
        h = pr.get("height")
        hmap[pid] = float(h) if pd.notna(h) else None
        handmap[pid] = str(pr.get("hand", "U"))
    return hmap, handmap


# ---------------------------------------------------------------------------
# Core analytics
# ---------------------------------------------------------------------------

def _compute_stats_for_year(
    matches: pd.DataFrame, players: pd.DataFrame, year: int
) -> pd.DataFrame:
    """Per-player career stats for players active in *year*."""
    yc = _year_col(matches)
    active_ids: set[int] = set(
        matches.loc[yc == year, "p1_id"].astype(int).tolist()
        + matches.loc[yc == year, "p2_id"].astype(int).tolist()
    )
    if not active_ids:
        return pd.DataFrame()
    subset = matches[matches["p1_id"].astype(int).isin(active_ids)
                     | matches["p2_id"].astype(int).isin(active_ids)]
    surf_t: dict = defaultdict(int); surf_w: dict = defaultdict(int)
    bo5_t: dict = defaultdict(int); bo5_w: dict = defaultdict(int)
    bo3_t: dict = defaultdict(int); bo3_w: dict = defaultdict(int)
    tot: dict = defaultdict(int); w: dict = defaultdict(int)
    for _, r in subset.iterrows():
        p1, p2, winner = int(r["p1_id"]), int(r["p2_id"]), int(r["winner"])
        surf, bo = str(r.get("surface", "Unknown")), int(r.get("best_of", 3))
        for pid, is_p1 in [(p1, True), (p2, False)]:
            if pid not in active_ids:
                continue
            won = (winner == 1 and is_p1) or (winner == 2 and not is_p1)
            tot[pid] += 1; w[pid] += int(won)
            surf_t[(pid, surf)] += 1; surf_w[(pid, surf)] += int(won)
            (bo5_t if bo == 5 else bo3_t)[pid] += 1
            (bo5_w if bo == 5 else bo3_w)[pid] += int(won)
    hmap, handmap = _player_maps(players) if not players.empty else ({}, {})
    rows: list[dict] = []
    for pid in active_ids:
        n = tot.get(pid, 0)
        if n < MIN_MATCHES:
            continue
        ov = w[pid] / n
        row: dict = {"player_id": pid, "total_matches": n, "ov_wr": ov,
                     "height": hmap.get(pid), "hand": handmap.get(pid, "U")}
        for s in ("Hard", "Clay", "Grass"):
            st = surf_t.get((pid, s), 0); sw = surf_w.get((pid, s), 0)
            row[f"{s.lower()}_m"] = st
            row[f"{s.lower()}_wr"] = sw / st if st >= MIN_SURFACE_MATCHES else None
        b5t, b5w_ = bo5_t[pid], bo5_w[pid]; b3t, b3w_ = bo3_t[pid], bo3_w[pid]
        row["bo5_wr"] = b5w_ / b5t if b5t >= GS_MIN_MATCHES else None
        row["bo3_wr"] = b3w_ / b3t if b3t >= GS_MIN_MATCHES else None
        rows.append(row)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _assign_archetypes(stats: pd.DataFrame) -> Dict[str, int]:
    counts: dict[str, int] = {a.slug: 0 for a in ARCHETYPES}
    if stats.empty:
        return counts
    median_ov = stats["ov_wr"].median()
    for _, r in stats.iterrows():
        ov = float(r["ov_wr"])
        hw, cw, gw = r.get("hard_wr"), r.get("clay_wr"), r.get("grass_wr")
        b5, b3 = r.get("bo5_wr"), r.get("bo3_wr")
        ht, hand = r.get("height"), str(r.get("hand", "U"))
        if _ok(cw) and float(cw) - ov >= CLAY_SPECIALIST_DELTA and (  # type: ignore[arg-type]
            not _ok(hw) or float(cw) > float(hw)) and (  # type: ignore[arg-type]
                not _ok(gw) or float(cw) > float(gw)):  # type: ignore[arg-type]
            slug = "Clay_Court_Specialist"
        elif _ok(ht) and float(ht) >= HEIGHT_BIG_SERVER and (  # type: ignore[arg-type]
            (_ok(hw) and float(hw) - ov >= HARD_SPECIALIST_DELTA) or  # type: ignore[arg-type]
                (_ok(gw) and _ok(cw) and float(gw) > float(cw))):  # type: ignore[arg-type]
            slug = "Fast_Court_Big_Server"
        elif hand == "L":
            slug = "Left_Handed_Specialist"
        elif _ok(b5) and _ok(b3) and float(b5) - float(b3) >= GS_DELTA:  # type: ignore[arg-type]
            slug = "Grand_Slam_Performer"
        elif _ok(hw) and float(hw) - ov >= HARD_SPECIALIST_DELTA and (  # type: ignore[arg-type]
                not _ok(cw) or float(hw) > float(cw)):  # type: ignore[arg-type]
            slug = "Hard_Court_Specialist"
        elif _ok(gw) and float(gw) - ov >= GRASS_SPECIALIST_DELTA and (  # type: ignore[arg-type]
                not _ok(cw) or float(gw) > float(cw)):  # type: ignore[arg-type]
            slug = "Grass_Court_Specialist"
        else:
            wrs = [x for x in [hw, cw, gw] if _ok(x)]
            slug = ("All_Court_Baseliner"
                    if len(wrs) == 3 and (max(wrs) - min(wrs)) < ALL_COURT_MAX_SPREAD  # type: ignore[type-var]
                    and ov >= median_ov else "Journeyman")
        counts[slug] += 1
    return counts


def _surface_mix_by_year(matches: pd.DataFrame) -> Dict[int, Dict[str, float]]:
    m2 = matches.copy(); m2["_year"] = _year_col(matches)
    return {int(yr): ({s: round(len(g[g["surface"] == s]) / len(g) * 100, 1)
                       for s in ("Hard", "Clay", "Grass")} if len(g) else {})
            for yr, g in m2.groupby("_year")}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _table(header: List[str], data_rows: List[List[str]]) -> str:
    w = max(7, max(len(h) for h in header) + 1)
    sep = "+" + "+".join(["-" * (w + 2)] * len(header)) + "+"
    def row(cells: List[str]) -> str:
        return "| " + " | ".join(f"{c:>{w}}" for c in cells) + " |"
    return "\n".join([sep, row(header), sep]
                     + [row(r) for r in data_rows] + [sep])


def _ascii_archetype_table(rows: List[Tuple[int, Dict[str, int], int]]) -> str:
    heads = ["Year"] + [_ABBREV.get(s, s[:6]) for s in _SLUG_ORDER]
    data = [[str(yr)] + [f"{counts.get(s, 0) / total * 100:.1f}%" if total else "0.0%"
                         for s in _SLUG_ORDER]
            for yr, counts, total in rows]
    return _table(heads, data)


def _ascii_surface_table(surf_by_year: Dict[int, Dict[str, float]], years: List[int]) -> str:
    heads = ["Year", "Hard", "Clay", "Grass"]
    data = [[str(yr)] + [f"{surf_by_year.get(yr, {}).get(s, 0.0):.1f}%"
                         for s in ("Hard", "Clay", "Grass")] for yr in years]
    return _table(heads, data)


def _trend_summary(rows: List[Tuple[int, Dict[str, int], int]]) -> str:
    if len(rows) < 2: return "Insufficient years to compute trends."
    fy, fc, ft = rows[0]; ly, lc, lt = rows[-1]
    if ft == 0 or lt == 0: return "Insufficient data for trend summary."
    deltas = sorted([(lc.get(s, 0) / lt * 100 - fc.get(s, 0) / ft * 100, s) for s in _SLUG_ORDER],
                    key=lambda x: abs(x[0]), reverse=True)
    delta, slug = deltas[0]
    return (f"Largest shift {fy}–{ly}: **{_SLUG_LABEL.get(slug, slug)}** share is "
            f"{'rising' if delta > 0 else 'falling'} ({delta:+.1f} pp).")


_KEY = ("> Column key: Clay=Clay Specialist · BigSrv=Fast-Court Big Server · "
        "AllCrt=All-Court Baseliner · LeftH=Left-Handed Specialist · "
        "GSlam=Grand Slam Performer · Hard=Hard-Court Specialist · "
        "Grass=Grass-Court Specialist · Jrny=Journeyman")
_NOTES = ("- Archetype assignment uses the same priority-ordered thresholds as "
          "[[Playstyles/_Playstyles_Index]]; each active player counted once per year.\n"
          "- Career statistics (not just that year's matches) determine archetype "
          "classification; the series is stable across small yearly samples.\n"
          "- No individual player names appear anywhere in this note or the Trends section.\n"
          "- 2020 sample is reduced due to the COVID-shortened season.")


def _render_overview(
    rows: List[Tuple[int, Dict[str, int], int]],
    surf_by_year: Dict[int, Dict[str, float]],
    years: List[int], out_dir: pathlib.Path,
) -> pathlib.Path:
    yr = f"{years[0]}–{years[-1]}" if years else "n/a"
    body = (f"---\ntype: style-trends\nyear_range: \"{yr}\"\n"
            f"years_covered: {len(years)}\ntags:\n"
            "  - sport/tennis\n  - trends\n  - playstyle\n  - atlas/index\n---\n\n"
            "# Tennis Style-Era Trends\n\n"
            "[[Playstyles/_Playstyles_Index|← Playstyle Index]] | [[_Index|← Tennis Index]]\n\n"
            f"How archetype prevalence shifts year by year ({yr}).  "
            f"Active = ≥1 match that year and ≥{MIN_MATCHES} career matches.\n\n"
            f"## Trend Summary\n\n{_trend_summary(rows)}\n\n"
            f"## Archetype Share by Year (%)\n\n```\n{_ascii_archetype_table(rows)}\n```\n\n"
            f"{_KEY}\n\n"
            f"## Surface Mix by Year (% of matches)\n\n```\n{_ascii_surface_table(surf_by_year, years)}\n```\n\n"
            f"## Notes\n{_NOTES}\n\n---\n#sport/tennis #trends #playstyle #atlas/index\n")
    return _write(out_dir / "_Style_Trends_Overview.md", body)


def _render_year_note(
    year: int, counts: Dict[str, int], total: int,
    surf: Dict[str, float], out_dir: pathlib.Path,
) -> pathlib.Path:
    table = "\n".join(
        f"| {_SLUG_LABEL.get(s, s)} | {counts.get(s, 0)} | "
        + (f"{counts.get(s, 0) / total * 100:.1f}%" if total else "0.0%") + " |"
        for s in _SLUG_ORDER)
    body = (f"---\nyear: {year}\nactive_qualifying_players: {total}\n"
            "type: style-trends-year\ntags:\n  - sport/tennis\n  - trends\n  - playstyle\n---\n\n"
            f"# Tennis Style Trends — {year}\n\n"
            "[[_Style_Trends_Overview|← Overview]] | [[Playstyles/_Playstyles_Index|← Playstyle Index]]\n\n"
            f"Active qualifying players (≥{MIN_MATCHES} career matches): **{total}**\n\n"
            f"## Archetype Distribution\n\n| Archetype | Count | Share |\n|---|---|---|\n{table}\n\n"
            "## Surface Mix (matches this year)\n\n"
            f"- Hard: {surf.get('Hard', 0.0):.1f}%\n"
            f"- Clay: {surf.get('Clay', 0.0):.1f}%\n"
            f"- Grass: {surf.get('Grass', 0.0):.1f}%\n\n"
            "---\n#sport/tennis #trends #playstyle\n")
    return _write(out_dir / f"{year}.md", body)


def build_style_trends(
    out_dir: pathlib.Path,
    corpus_dir: Optional[pathlib.Path] = None,
    *,
    _matches_df: Optional[pd.DataFrame] = None,
    _players_df: Optional[pd.DataFrame] = None,
) -> List[pathlib.Path]:
    """Compute playstyle archetype prevalence by year; emit Obsidian Markdown notes.

    out_dir: Trends/ destination (created if missing).
    corpus_dir: data/domains/tennis/ (repo default if None).
    _matches_df / _players_df: fixture overrides for tests.
    Returns list of written paths (per-year notes + overview).
    """
    if corpus_dir is None:
        corpus_dir = DEFAULT_CORPUS
    out_dir = pathlib.Path(out_dir)
    if _matches_df is not None:
        matches = _matches_df.copy()
        players = (_players_df if _players_df is not None
                   else pd.DataFrame(columns=["player_id", "full_name", "hand", "height"]))
    else:
        matches, players = _load_corpus(pathlib.Path(corpus_dir))
    years = sorted(_year_col(matches).dropna().astype(int).unique().tolist())
    surf_by_year = _surface_mix_by_year(matches)
    rows: List[Tuple[int, Dict[str, int], int]] = []
    written: List[pathlib.Path] = []
    for year in years:
        stats = _compute_stats_for_year(matches, players, year)
        counts = _assign_archetypes(stats)
        rows.append((year, counts, len(stats)))
        written.append(_render_year_note(year, counts, len(stats), surf_by_year.get(year, {}), out_dir))
    written.append(_render_overview(rows, surf_by_year, years, out_dir))
    return written
