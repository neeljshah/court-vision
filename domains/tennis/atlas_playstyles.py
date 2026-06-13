"""domains.tennis.atlas_playstyles — Playstyle/archetype atlas generator for tennis.

Clusters the player population into playstyle archetypes using real corpus data.
Archetype definitions live in atlas_playstyle_specs.py.

Public API: build_playstyles(out_dir, corpus_dir) -> list[pathlib.Path]

F5-clean: stdlib + numpy + pandas + domains.tennis.* only.
No edge / betting language. No individual player names in emitted notes.
Sackmann data is CC BY-NC-SA — private research use only.
"""
from __future__ import annotations

import pathlib
from collections import defaultdict
from typing import Dict, List, Optional

import pandas as pd

from domains.tennis.atlas_playstyle_specs import (
    ALL_COURT_MAX_SPREAD, ARCHETYPES, ArchetypeSpec,
    CLAY_SPECIALIST_DELTA, GS_DELTA, GS_MIN_MATCHES,
    GRASS_SPECIALIST_DELTA, HARD_SPECIALIST_DELTA,
    HEIGHT_BIG_SERVER, JOURNEYMAN_WIN_RATE_UPPER,
    MIN_MATCHES, MIN_SURFACE_MATCHES,
)

DEFAULT_CORPUS: pathlib.Path = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "domains" / "tennis"
)


def _load_corpus(corpus_dir: pathlib.Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    matches = pd.read_parquet(corpus_dir / "matches.parquet").copy()
    matches["date"] = matches["date"].astype(str)
    pp = corpus_dir / "players.parquet"
    players = pd.read_parquet(pp) if pp.exists() else pd.DataFrame(
        columns=["player_id", "full_name", "hand", "height"]
    )
    return matches, players


def _compute_stats(matches: pd.DataFrame, players: pd.DataFrame) -> pd.DataFrame:
    """Return one row per player with surface win-rates, bo5/bo3, height, hand."""
    surf_t: dict[tuple[int, str], int] = defaultdict(int)
    surf_w: dict[tuple[int, str], int] = defaultdict(int)
    bo5_t: dict[int, int] = defaultdict(int)
    bo5_w: dict[int, int] = defaultdict(int)
    bo3_t: dict[int, int] = defaultdict(int)
    bo3_w: dict[int, int] = defaultdict(int)
    tot: dict[int, int] = defaultdict(int)
    w: dict[int, int] = defaultdict(int)

    for _, r in matches.iterrows():
        p1, p2 = int(r["p1_id"]), int(r["p2_id"])
        winner = int(r["winner"])
        surf = str(r.get("surface", "Unknown"))
        bo = int(r.get("best_of", 3))
        for pid, is_p1 in [(p1, True), (p2, False)]:
            won = (winner == 1 and is_p1) or (winner == 2 and not is_p1)
            tot[pid] += 1; w[pid] += int(won)
            surf_t[(pid, surf)] += 1; surf_w[(pid, surf)] += int(won)
            (bo5_t if bo == 5 else bo3_t)[pid] += 1
            (bo5_w if bo == 5 else bo3_w)[pid] += int(won)

    hmap: dict[int, Optional[float]] = {}
    handmap: dict[int, str] = {}
    if not players.empty:
        for _, pr in players.iterrows():
            pid = int(pr["player_id"])
            h = pr.get("height")
            hmap[pid] = float(h) if pd.notna(h) else None
            handmap[pid] = str(pr.get("hand", "U"))

    rows: list[dict] = []
    for pid in tot:
        n = tot[pid]
        if n < MIN_MATCHES:
            continue
        row: dict = {"player_id": pid, "total_matches": n, "ov_wr": w[pid] / n,
                     "height": hmap.get(pid), "hand": handmap.get(pid, "U")}
        for s in ("Hard", "Clay", "Grass"):
            st = surf_t.get((pid, s), 0); sw = surf_w.get((pid, s), 0)
            row[f"{s.lower()}_m"] = st
            row[f"{s.lower()}_wr"] = sw / st if st >= MIN_SURFACE_MATCHES else None
        b5t, b5w_ = bo5_t[pid], bo5_w[pid]
        b3t, b3w_ = bo3_t[pid], bo3_w[pid]
        row["bo5_wr"] = b5w_ / b5t if b5t >= GS_MIN_MATCHES else None
        row["bo3_wr"] = b3w_ / b3t if b3t >= GS_MIN_MATCHES else None
        rows.append(row)

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _ok(v: object) -> bool:
    """True when v is not None/NaN."""
    return v is not None and not (isinstance(v, float) and pd.isna(v))


def _assign_archetypes(stats: pd.DataFrame) -> Dict[str, int]:
    """Return {slug: count}; each player assigned to first matching archetype."""
    counts: dict[str, int] = {a.slug: 0 for a in ARCHETYPES}
    if stats.empty:
        return counts
    median_ov = stats["ov_wr"].median()

    for _, r in stats.iterrows():
        ov = float(r["ov_wr"])
        hw = r.get("hard_wr"); cw = r.get("clay_wr"); gw = r.get("grass_wr")
        b5 = r.get("bo5_wr"); b3 = r.get("bo3_wr")
        ht = r.get("height"); hand = str(r.get("hand", "U"))
        slug = None

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
            if len(wrs) == 3 and (max(wrs) - min(wrs)) < ALL_COURT_MAX_SPREAD and ov >= median_ov:  # type: ignore[type-var]
                slug = "All_Court_Baseliner"
            else:
                slug = "Journeyman"

        counts[slug] += 1

    return counts


def _corpus_medians(stats: pd.DataFrame) -> dict:
    """Corpus-wide median surface win-rates for note bodies."""
    out: dict = {}
    if stats.empty:
        return out
    for s in ("hard", "clay", "grass"):
        vals = stats[f"{s}_wr"].dropna() if f"{s}_wr" in stats.columns else pd.Series([], dtype=float)
        out[f"median_{s}_wr"] = round(float(vals.median()) * 100, 1) if len(vals) > 0 else None
    if "bo5_wr" in stats.columns:
        vals = stats["bo5_wr"].dropna()
        out["median_bo5_wr"] = round(float(vals.median()) * 100, 1) if len(vals) > 0 else None
    return out


def _p(v: Optional[float]) -> str:
    return f"{v:.1f}%" if v is not None else "n/a"


def _render_archetype(
    spec: ArchetypeSpec, count: int, total: int, md: dict, out_dir: pathlib.Path
) -> pathlib.Path:
    """Write <slug>.md; return path."""
    pct = round(count / total * 100, 1) if total > 0 else 0.0
    tag_yaml = "\n".join(f"  - {t}" for t in spec.tags)
    lines = [
        "---", f"archetype: {spec.name}", f"player_count: {count}",
        f"corpus_share_pct: {pct}", "tags:", tag_yaml, "---", "",
        f"# {spec.name}", "",
        "[[Playstyles/_Playstyles_Index|← Playstyle Index]] | [[_Index|← Tennis Index]]", "",
        "## Description", spec.description, "",
        "## Stat Signature (definition thresholds)", "```", spec.stat_signature, "```", "",
        "## Population",
        f"- **Players in archetype:** {count} ({pct}% of qualifying corpus)",
        f"- **Qualifying corpus total:** {total} players (≥{MIN_MATCHES} matches)", "",
        "## Surface Tendencies",
        f"- **Pattern:** {spec.surface_tendency}",
        f"- **Median Hard win-rate (corpus):** {_p(md.get('median_hard_wr'))}",
        f"- **Median Clay win-rate (corpus):** {_p(md.get('median_clay_wr'))}",
        f"- **Median Grass win-rate (corpus):** {_p(md.get('median_grass_wr'))}",
        f"- **Median Best-of-5 win-rate (corpus):** {_p(md.get('median_bo5_wr'))}", "",
        "---", " ".join(f"#{t}" for t in spec.tags),
    ]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{spec.slug}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _render_index(counts: Dict[str, int], total: int, out_dir: pathlib.Path) -> pathlib.Path:
    """Write _Playstyles_Index.md; return path."""
    table = "\n".join(
        f"| [[Playstyles/{s.slug}|{s.name}]] | {counts.get(s.slug,0)} | "
        f"{round(counts.get(s.slug,0)/total*100,1) if total>0 else 0}% |"
        for s in ARCHETYPES
    )
    lines = [
        "---", "type: playstyle-index",
        f"total_qualifying_players: {total}", f"archetype_count: {len(ARCHETYPES)}",
        "tags:", "  - sport/tennis", "  - playstyle", "  - atlas/index", "---", "",
        "# Tennis Playstyle Archetypes", "",
        "[[_Index|← Tennis Index]] | [[_Hub|← Hub]]", "",
        (f"Population of {total} players (≥{MIN_MATCHES} matches) "
         f"clustered into {len(ARCHETYPES)} archetypes by real corpus statistics."), "",
        "## Archetype Summary", "", "| Archetype | Players | Share |", "|---|---|---|", table, "",
        "## Notes",
        ("- Archetypes assigned by priority order; each player counted once.\n"
         "- Thresholds derived from corpus win-rate distributions (delta ≥7–8 pp vs overall).\n"
         "- No individual player names appear in any note in this section."), "",
        "---", "#sport/tennis #playstyle #atlas/index",
    ]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "_Playstyles_Index.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def build_playstyles(
    out_dir: pathlib.Path,
    corpus_dir: Optional[pathlib.Path] = None,
    *,
    _matches_df: Optional[pd.DataFrame] = None,
    _players_df: Optional[pd.DataFrame] = None,
) -> List[pathlib.Path]:
    """Cluster players into playstyle archetypes and emit Obsidian notes.

    Parameters
    ----------
    out_dir:
        Directory where notes are emitted. Created if missing.
    corpus_dir:
        Path to data/domains/tennis/. Defaults to repo-relative default.
    _matches_df / _players_df:
        Optional DataFrame overrides for unit tests (no filesystem reads).
    """
    if corpus_dir is None:
        corpus_dir = DEFAULT_CORPUS
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if _matches_df is not None:
        matches = _matches_df.copy()
        players = _players_df if _players_df is not None else pd.DataFrame(
            columns=["player_id", "full_name", "hand", "height"]
        )
    else:
        matches, players = _load_corpus(pathlib.Path(corpus_dir))

    stats = _compute_stats(matches, players)
    total = len(stats)
    counts = _assign_archetypes(stats)
    md = _corpus_medians(stats)

    written: List[pathlib.Path] = [
        _render_archetype(spec, counts.get(spec.slug, 0), total, md, out_dir)
        for spec in ARCHETYPES
    ]
    written.append(_render_index(counts, total, out_dir))
    return written
