"""domains.tennis.atlas_tournaments — Obsidian tournament-intelligence atlas.

Emits name-free style-profile notes (surface, level, winner-archetype
distribution, upset tendency) for each qualifying tournament.  No individual
player names appear in output.

Public API: build_tournaments(out_dir, corpus_dir, min_editions) -> list[Path]
F5-clean: stdlib + pandas only.  No edge / betting language.
Sackmann data is CC BY-NC-SA — private research use only.
"""
from __future__ import annotations

import pathlib
import re
from typing import Optional

import pandas as pd

from domains.tennis.atlas_tournaments_render import render_all_tournaments
from scripts.platformkit.atlas.obsidian_emit import slug as _slug  # noqa: F401

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_CORPUS: pathlib.Path = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "domains" / "tennis"
)
DEFAULT_OUT: pathlib.Path = (
    pathlib.Path(__file__).resolve().parents[2]
    / "vault" / "Sports" / "Tennis" / "Tournaments"
)

LEVEL_LABELS: dict[str, str] = {
    "G": "Grand Slam", "M": "Masters 1000", "A": "ATP 500", "B": "ATP 250",
    "D": "Davis Cup",  "F": "Tour Finals",  "C": "Challenger", "S": "Satellite / ITF",
}

LEVEL_ORDER: list[str] = ["G", "F", "M", "A", "B", "D", "C", "S"]

# Surfaces where specialisation is most pronounced (used for archetype label)
_SPECIALIST_SURFACES: frozenset[str] = frozenset({"Clay", "Grass"})

# Canonical tournament name map: variant → canonical.
# Fixes case/spelling inconsistencies in source data that would otherwise emit
# two separate notes (and a dangling wikilink) for the same event.
_TOURNEY_NAME_CANON: dict[str, str] = {
    "Us Open":        "US Open",       # source data mixed-case for 2020-2025
    "Rio De Janeiro": "Rio de Janeiro", # source data title-case for 2023-2024
}


def _canonicalize_names(df: pd.DataFrame) -> pd.DataFrame:
    """Map known tourney_name variants to their canonical form (in place copy)."""
    df = df.copy()
    df["tourney_name"] = df["tourney_name"].map(
        lambda n: _TOURNEY_NAME_CANON.get(n, n) if isinstance(n, str) else n
    )
    return df


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_matches(corpus_dir: pathlib.Path) -> pd.DataFrame:
    """Load matches.parquet and normalise key columns."""
    df = pd.read_parquet(corpus_dir / "matches.parquet").copy()
    for col in ("tourney_name", "tourney_level", "surface", "round", "winner",
                "p1_name", "p2_name", "date"):
        if col not in df.columns:
            df[col] = None
    df["date"] = df["date"].astype(str)
    df = _canonicalize_names(df)

    def _year(d: str) -> Optional[int]:
        m = re.match(r"(\d{4})", str(d))
        return int(m.group(1)) if m else None

    df["year"] = df["date"].map(_year)
    return df


# ---------------------------------------------------------------------------
# Style-profile helpers
# ---------------------------------------------------------------------------

def _finalist_archetype(finalist_id: str, all_finals: pd.DataFrame) -> str:
    """Return 'surface-specialist' or 'all-court' (corpus-internal, name-free).

    A finalist who reached finals exclusively on one specialist surface is
    labelled 'surface-specialist'; one seen on multiple surfaces is 'all-court'.
    """
    fid = str(finalist_id).strip()
    if not fid or fid == "nan":
        return "all-court"
    mask = (all_finals["p1_id"].astype(str) == fid) | (
        all_finals["p2_id"].astype(str) == fid
    )
    surfaces = set(all_finals.loc[mask, "surface"].dropna().unique())
    return "surface-specialist" if (len(surfaces) == 1 and bool(surfaces & _SPECIALIST_SURFACES)) else "all-court"


def _compute_style_profile(finals: pd.DataFrame, all_finals: pd.DataFrame) -> dict:
    """Return name-free style metrics: archetype distribution + upset rate."""
    _empty = {"specialist_pct": 0.0, "allcourt_pct": 0.0, "unknown_pct": 100.0,
               "n_classified": 0, "upset_rate": None}
    if finals.empty:
        return _empty

    specialist = allcourt = unknown = 0
    for _, frow in finals.iterrows():
        code = str(frow.get("winner", "")).strip()
        if code == "1":
            wid = str(frow.get("p1_id", "")).strip()
        elif code == "2":
            wid = str(frow.get("p2_id", "")).strip()
        else:
            unknown += 1
            continue
        if _finalist_archetype(wid, all_finals) == "surface-specialist":
            specialist += 1
        else:
            allcourt += 1

    total = specialist + allcourt + unknown
    if total == 0:
        return _empty

    upset_rate: Optional[float] = None
    if "winner_rank" in finals.columns and "loser_rank" in finals.columns:
        ranked = finals[finals["winner_rank"].notna() & finals["loser_rank"].notna()]
        if not ranked.empty:
            upset_rate = round(float((ranked["winner_rank"] > ranked["loser_rank"]).sum()) / len(ranked), 3)

    return {
        "specialist_pct": round(100.0 * specialist / total, 1),
        "allcourt_pct":   round(100.0 * allcourt   / total, 1),
        "unknown_pct":    round(100.0 * unknown     / total, 1),
        "n_classified":   specialist + allcourt,
        "upset_rate":     upset_rate,
    }


# ---------------------------------------------------------------------------
# Tournament-level aggregation
# ---------------------------------------------------------------------------

def _compute_tournament_stats(matches: pd.DataFrame, min_editions: int) -> dict[str, dict]:
    """Aggregate per-tournament stats; no individual names in output."""
    if matches.empty:
        return {}

    all_finals = matches[matches["round"] == "F"].copy()
    results: dict[str, dict] = {}

    for tname, tdf in matches.groupby("tourney_name", sort=False):
        tname = str(tname)
        years_present = sorted({int(y) for y in tdf["year"].dropna().unique()})
        if len(years_present) < min_editions:
            continue

        level_s = tdf["tourney_level"].dropna()
        level = str(level_s.mode().iloc[0]) if not level_s.empty else "?"
        surf_s = tdf["surface"].dropna()
        surface = str(surf_s.mode().iloc[0]) if not surf_s.empty else "Unknown"
        bo_s = tdf["best_of"].dropna() if "best_of" in tdf.columns else pd.Series(dtype=float)
        best_of = int(bo_s.mode().iloc[0]) if not bo_s.empty else 3

        finals = tdf[tdf["round"] == "F"].copy()
        editions_with_final = int(finals["year"].dropna().nunique())
        n_editions = len(years_present)

        results[tname] = {
            "name": tname,
            "level": level,
            "level_label": LEVEL_LABELS.get(level, level),
            "surface": surface,
            "editions": n_editions,
            "editions_with_final": editions_with_final,
            "completion_rate": round(100.0 * editions_with_final / n_editions, 1) if n_editions else 0.0,
            "span": f"{min(years_present)}–{max(years_present)}" if years_present else "n/a",
            "years": years_present,
            "best_of": best_of,
            "style_profile": _compute_style_profile(finals, all_finals),
            "total_matches": len(tdf),
        }

    return results


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_tournaments(
    out_dir: pathlib.Path,
    corpus_dir: pathlib.Path = DEFAULT_CORPUS,
    min_editions: int = 3,
    *,
    _matches_df: Optional[pd.DataFrame] = None,
) -> list[pathlib.Path]:
    """Generate name-free Obsidian tournament style-profile notes.

    Parameters
    ----------
    out_dir:        Directory where notes are emitted.  Idempotent (reruns overwrite).
    corpus_dir:     Directory containing matches.parquet.
    min_editions:   Minimum distinct calendar years required for a note.
    _matches_df:    Optional DataFrame override for tests (no disk access).

    Returns
    -------
    list[pathlib.Path]
        All note files written (index + tournament notes).
    """
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if _matches_df is not None:
        matches = _canonicalize_names(_matches_df)
        if "year" not in matches.columns:
            matches["date"] = matches["date"].astype(str)
            matches["year"] = matches["date"].str.extract(r"^(\d{4})")[0].apply(
                lambda v: int(v) if pd.notna(v) else None
            )
    else:
        matches = _load_matches(corpus_dir)

    return render_all_tournaments(
        out_dir=out_dir,
        tournament_stats=_compute_tournament_stats(matches, min_editions),
        level_order=LEVEL_ORDER,
        level_labels=LEVEL_LABELS,
    )
