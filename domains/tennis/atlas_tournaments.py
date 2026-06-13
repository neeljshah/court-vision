"""domains.tennis.atlas_tournaments — Obsidian tournament-intelligence atlas.

Adds a Tournaments dimension to the tennis graph:  per-tournament notes with
champion history, surface, editions, and finals detail, linked back to existing
player notes so [[wikilinks]] resolve across the graph.

Public API
----------
build_tournaments(out_dir, corpus_dir, min_editions) -> list[pathlib.Path]
    Emit Tournaments/_Tournaments_Index.md + one note per qualifying tournament.
    Idempotent (reruns overwrite).

F5-clean: stdlib + pandas only.  No src.* / kernel.* / other-domain imports.
No edge / betting language anywhere.

Sackmann data is CC BY-NC-SA — private research use only.
"""
from __future__ import annotations

import pathlib
import re
from typing import Optional

import pandas as pd

from domains.tennis.atlas_tournaments_render import render_all_tournaments

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

# ATP level codes → human-readable label (Sackmann convention)
LEVEL_LABELS: dict[str, str] = {
    "G": "Grand Slam",
    "M": "Masters 1000",
    "A": "ATP 500",
    "B": "ATP 250",
    "D": "Davis Cup",
    "F": "Tour Finals",
    "C": "Challenger",
    "S": "Satellite / ITF",
}

# Canonical level ordering for the index (most prestigious first)
LEVEL_ORDER: list[str] = ["G", "F", "M", "A", "B", "D", "C", "S"]

_SLUG_RE = re.compile(r"[^\w\s-]")
_SPACE_RE = re.compile(r"[\s]+")


def _slug(name: str) -> str:
    """Return a filesystem-safe slug (spaces → underscores, strip specials)."""
    s = _SLUG_RE.sub("", name).strip()
    return _SPACE_RE.sub("_", s)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_matches(corpus_dir: pathlib.Path) -> pd.DataFrame:
    """Load matches.parquet and normalise key columns."""
    df = pd.read_parquet(corpus_dir / "matches.parquet")
    df = df.copy()

    # Ensure required columns exist with safe defaults
    for col in ("tourney_name", "tourney_level", "surface", "round", "winner",
                 "p1_name", "p2_name", "date"):
        if col not in df.columns:
            df[col] = None

    df["date"] = df["date"].astype(str)

    # Extract year from date string (YYYY-MM-DD or YYYYMMDD or similar)
    def _year(d: str) -> Optional[int]:
        m = re.match(r"(\d{4})", str(d))
        return int(m.group(1)) if m else None

    df["year"] = df["date"].map(_year)
    return df


# ---------------------------------------------------------------------------
# Tournament-level aggregation
# ---------------------------------------------------------------------------

def _compute_tournament_stats(
    matches: pd.DataFrame,
    min_editions: int,
) -> dict[str, dict]:
    """Return a dict keyed by tourney_name with aggregated stats.

    Only tournaments with ≥ min_editions distinct years are included.
    """
    if matches.empty:
        return {}

    results: dict[str, dict] = {}

    grouped = matches.groupby("tourney_name", sort=False)

    for tname, tdf in grouped:
        tname = str(tname)

        # Edition = distinct calendar year
        years_present = sorted(
            {int(y) for y in tdf["year"].dropna().unique()},
        )
        n_editions = len(years_present)
        if n_editions < min_editions:
            continue

        # Level: most-common value across rows
        level_series = tdf["tourney_level"].dropna()
        level: str = str(level_series.mode().iloc[0]) if not level_series.empty else "?"

        # Surface: most-common non-null surface
        surf_series = tdf["surface"].dropna()
        surface: str = str(surf_series.mode().iloc[0]) if not surf_series.empty else "Unknown"

        # Best-of: most common
        bo_series = tdf["best_of"].dropna() if "best_of" in tdf.columns else pd.Series(dtype=float)
        best_of: int = int(bo_series.mode().iloc[0]) if not bo_series.empty else 3

        # Finals rows (round == 'F')
        finals = tdf[tdf["round"] == "F"].copy()

        # Champions: per year, the winner of the final
        champions_by_year: dict[int, str] = {}
        for _, frow in finals.iterrows():
            yr = frow["year"]
            if yr is None or pd.isna(yr):
                continue
            yr = int(yr)
            winner_code = str(frow.get("winner", "")).strip()
            p1_name = str(frow.get("p1_name", "")).strip()
            p2_name = str(frow.get("p2_name", "")).strip()
            if winner_code == "1" and p1_name:
                champions_by_year[yr] = p1_name
            elif winner_code == "2" and p2_name:
                champions_by_year[yr] = p2_name

        # Count titles per player
        from collections import Counter
        title_counts: Counter[str] = Counter(champions_by_year.values())

        # Recent finals (last 5 editions with a final)
        recent_finals_rows: list[dict] = []
        if not finals.empty:
            finals_sorted = finals[finals["year"].notna()].sort_values(
                "year", ascending=False
            )
            for _, frow in finals_sorted.head(5).iterrows():
                yr = frow["year"]
                if yr is None or pd.isna(yr):
                    continue
                recent_finals_rows.append(
                    {
                        "year": int(yr),
                        "p1": str(frow.get("p1_name", "?")),
                        "p2": str(frow.get("p2_name", "?")),
                        "winner": str(frow.get("winner", "")),
                        "score": str(frow.get("score", "")) if "score" in frow.index else "",
                    }
                )

        results[tname] = {
            "name": tname,
            "level": level,
            "level_label": LEVEL_LABELS.get(level, level),
            "surface": surface,
            "editions": n_editions,
            "span": f"{min(years_present)}–{max(years_present)}" if years_present else "n/a",
            "years": years_present,
            "best_of": best_of,
            "champions_by_year": champions_by_year,
            "title_counts": dict(title_counts.most_common()),
            "recent_finals": recent_finals_rows,
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
    """Generate Obsidian tournament notes and return written paths.

    Parameters
    ----------
    out_dir:
        Directory where notes are emitted (e.g. vault/Sports/Tennis/Tournaments/).
        Created if it does not exist.  Idempotent — reruns overwrite.
    corpus_dir:
        Directory containing matches.parquet.
        Defaults to data/domains/tennis/ relative to repo root.
    min_editions:
        Minimum distinct calendar years a tournament must appear in to get a note.
    _matches_df:
        Optional DataFrame override — used by tests to inject a synthetic fixture
        without touching disk.

    Returns
    -------
    list[pathlib.Path]
        All note files written (index + tournament notes).
    """
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if _matches_df is not None:
        matches = _matches_df.copy()
        # Ensure year column
        if "year" not in matches.columns:
            matches["date"] = matches["date"].astype(str)
            matches["year"] = matches["date"].str.extract(r"^(\d{4})")[0].apply(
                lambda v: int(v) if pd.notna(v) else None
            )
    else:
        matches = _load_matches(corpus_dir)

    tournament_stats = _compute_tournament_stats(matches, min_editions)

    return render_all_tournaments(
        out_dir=out_dir,
        tournament_stats=tournament_stats,
        level_order=LEVEL_ORDER,
        level_labels=LEVEL_LABELS,
    )
